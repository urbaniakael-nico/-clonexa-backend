"""Reportes para el dueño del restaurante (049G).

Solo para empresas con waiter_ordering (hoy ASADERO EL SOCIO): es el mismo
interruptor que define a los restaurantes con mesero, cocina y caja, asi que
no hay un segundo modulo de reportes que pueda quedar activo a medias.

Rendimiento: el reporte se pide en dos llamadas que el portal hace a la vez.
- /summary: indicadores con variacion, lecturas y aviso de costeo (pedidos
  del periodo y del anterior + inventario). Se pinta primero.
- /details: graficas, carta, equipo, cocina, operacion e inventario (suma
  los turnos). Se pinta cuando llega.
Cada consulta filtra por company_id y un rango de created_at con indice
(migracion 021v), y el periodo tiene un tope de 93 dias.

Acceso: dueño/gerente de la empresa o Admin V2 (no el rol "administrador",
igual que Nomina: margen y venta por mesero son informacion sensible).
"""
from __future__ import annotations

import io
import uuid
from datetime import date as calendar_date
from datetime import datetime, time, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ADMIN_ROLES, get_db, require_company_user_for_tenant, require_enabled_module
from app.api.v1.endpoints.hospitality import (
    _hospitality_company_identity,
    _hsp_company_report_settings,
    _hsp_report_logo_reader,
    _hsp_report_zone,
)
from app.services import owner_report as engine
from app.web.admin_v2_routes import _active_session as active_admin_v2_session

router = APIRouter()

MODULE_CODE = "waiter_ordering"
OWNER_ROLES = ADMIN_ROLES | {"manager", "gerencia", "gerente", "dueno", "dueño", "owner", "propietario"}


async def require_owner_report(
    company_id: uuid.UUID, request: Request,
    authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db),
) -> str:
    await require_enabled_module(db, company_id, MODULE_CODE)
    if await active_admin_v2_session(request, db):
        return "Admin V2"
    user = await require_company_user_for_tenant(db, authorization, company_id, allowed_roles=OWNER_ROLES)
    return str(getattr(user, "full_name", "") or "Dueño")


async def _table_exists(db: AsyncSession, name: str) -> bool:
    result = await db.execute(text("SELECT to_regclass(:name) IS NOT NULL AS exists"), {"name": f"public.{name}"})
    row = result.mappings().first()
    return bool(row and row.get("exists"))


def _today(tz, business_day: dict | None) -> calendar_date:
    now = datetime.now(timezone.utc).astimezone(tz)
    if business_day and business_day.get("overnight") and now.time() < business_day["close"]:
        return now.date() - timedelta(days=1)
    return now.date()


async def _context(db: AsyncSession, company_id: uuid.UUID, period: str, start, end, *, details: bool) -> dict:
    settings = await _hsp_company_report_settings(db, company_id)
    if settings is None:
        raise HTTPException(status_code=404, detail="company_not_found")
    tz_name, business_day = settings
    tz = _hsp_report_zone(tz_name)
    try:
        chosen = engine.resolve_period(period, _today(tz, business_day), start, end)
    except ValueError as exc:
        detail = "El periodo no puede pasar de 93 días." if str(exc) == "periodo_muy_largo" else "Periodo inválido."
        raise HTTPException(status_code=400, detail=detail) from exc

    # Pedidos creados desde el dia antes del periodo anterior hasta dos dias
    # despues del final: cubre las jornadas que cruzan la medianoche.
    window_start = datetime.combine(chosen["prev_start"] - timedelta(days=1), time.min, tz).astimezone(timezone.utc)
    window_end = datetime.combine(chosen["end"] + timedelta(days=2), time.min, tz).astimezone(timezone.utc)
    cid = str(company_id)
    orders = [dict(r) for r in (await db.execute(text("""
        SELECT id, created_at, updated_at, closed_at, cancelled_at, archived_at, status, order_type, source,
               table_key, table_number, payment_method, total, items, metadata, inventory_deducted
        FROM hospitality_orders
        WHERE company_id = CAST(:company_id AS uuid) AND created_at >= :start AND created_at < :end
    """), {"company_id": cid, "start": window_start, "end": window_end})).mappings().all()]
    closures = [dict(r) for r in (await db.execute(text("""
        SELECT id, opened_at, closed_at, order_ids
        FROM hospitality_day_closures
        WHERE company_id = CAST(:company_id AS uuid) AND closed_at >= :start AND closed_at < :end
    """), {"company_id": cid, "start": window_start, "end": window_end + timedelta(days=2)})).mappings().all()]
    inventory = {str(r["id"]): dict(r) for r in (await db.execute(text("""
        SELECT id, COALESCE(NULLIF(name, ''), name_reference, sku) AS name, entry_price, sale_price, current_stock, status
        FROM inventory_items
        WHERE company_id = CAST(:company_id AS uuid) AND COALESCE(status, 'active') NOT IN ('archived', 'deleted')
    """), {"company_id": cid})).mappings().all()}
    portions = {}
    if await _table_exists(db, "hospitality_product_portions"):
        portions = {str(r["inventory_item_id"]): dict(r) for r in (await db.execute(text("""
            SELECT inventory_item_id, product_group_key AS group_key, group_label, portion_label
            FROM hospitality_product_portions WHERE company_id = CAST(:company_id AS uuid)
        """), {"company_id": cid})).mappings().all()}
    sessions, confirmed = [], {}
    if details:
        period_start = datetime.combine(chosen["start"], time.min, tz).astimezone(timezone.utc)
        period_end = datetime.combine(chosen["end"] + timedelta(days=1), time.min, tz).astimezone(timezone.utc)
        sessions = [dict(r) for r in (await db.execute(text("""
            SELECT id, user_id, employee_id, panel_type, status, started_at, ended_at, active_seconds,
                   break_seconds, active_started_at, closed_reason
            FROM mini_panel_work_sessions
            WHERE company_id = CAST(:company_id AS uuid) AND panel_type = 'mesero'
              AND started_at >= :start AND started_at < :end
        """), {"company_id": cid, "start": period_start, "end": period_end})).mappings().all()]
        if await _table_exists(db, "workforce_session_closures"):
            confirmed = {str(r["session_ref"]): r["real_end_at"] for r in (await db.execute(text("""
                SELECT session_ref, real_end_at FROM workforce_session_closures
                WHERE company_id = CAST(:company_id AS uuid) AND source = 'mini_panel' AND status = 'confirmed'
            """), {"company_id": cid})).mappings().all()}
    report = engine.Report(orders=orders, closures=closures, inventory=inventory, portions=portions, tz=tz,
                           period=chosen, business_day=business_day, sessions=sessions, confirmed_ends=confirmed)
    return {"report": report, "period": chosen, "tz": tz_name}


def _period_payload(period: dict) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in period.items()}


async def _summary(ctx: dict) -> dict:
    report = ctx["report"]
    kpis = report.kpis()
    return engine.public({
        "period": _period_payload(ctx["period"]),
        "timezone": ctx["tz"],
        "kpis": kpis,
        "readings": report.readings(kpis=kpis),
        "busiest_weekday": report.busiest_weekday(),
    })


async def _details(ctx: dict) -> dict:
    report = ctx["report"]
    return engine.public({
        "period": _period_payload(ctx["period"]),
        "daily": report.daily(),
        "heatmap": report.heatmap(),
        "menu": report.menu(),
        "team": report.team(),
        "kitchen": report.kitchen(),
        "operations": report.operations(),
        "inventory": report.inventory_report(),
    })


@router.get("/companies/{company_id}/owner-report/summary")
async def owner_report_summary(
    company_id: uuid.UUID, period: str = Query(default="7d"),
    start: calendar_date | None = None, end: calendar_date | None = None,
    db: AsyncSession = Depends(get_db), _actor: str = Depends(require_owner_report),
) -> dict:
    return await _summary(await _context(db, company_id, period, start, end, details=False))


@router.get("/companies/{company_id}/owner-report/details")
async def owner_report_details(
    company_id: uuid.UUID, period: str = Query(default="7d"),
    start: calendar_date | None = None, end: calendar_date | None = None,
    db: AsyncSession = Depends(get_db), _actor: str = Depends(require_owner_report),
) -> dict:
    return await _details(await _context(db, company_id, period, start, end, details=True))


@router.get("/companies/{company_id}/owner-report/pdf")
async def owner_report_pdf(
    company_id: uuid.UUID, period: str = Query(default="7d"),
    start: calendar_date | None = None, end: calendar_date | None = None,
    db: AsyncSession = Depends(get_db), _actor: str = Depends(require_owner_report),
) -> StreamingResponse:
    ctx = await _context(db, company_id, period, start, end, details=True)
    data = {**await _summary(ctx), **await _details(ctx)}
    company = await _hospitality_company_identity(db, company_id)
    pdf = build_owner_report_pdf(company, data)
    name = f"reporte_{data['period']['start']}_{data['period']['end']}.pdf"
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ------------------------------------------------------------------ PDF ---
def _fmt(value: Any, kind: str = "money") -> str:
    if value is None:
        return "—"
    if kind == "money":
        return engine.money_text(value)
    if kind == "pct":
        return f"{float(value):.1f}%"
    return f"{value}"


def build_owner_report_pdf(company: dict, data: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    width, height = letter
    c = canvas.Canvas(buffer, pagesize=letter)
    margin = 36
    dark, muted, line = colors.HexColor("#111827"), colors.HexColor("#64748b"), colors.HexColor("#d8dee9")
    good, bad = colors.HexColor("#15803d"), colors.HexColor("#b91c1c")
    logo = _hsp_report_logo_reader(company.get("logo_url"))
    period = data["period"]
    state = {"y": 0.0, "page": 0}

    def fit(value: Any, size: float, max_w: float, font: str = "Helvetica") -> str:
        s = " ".join(str(value or "").split())
        while s and stringWidth(s, font, size) > max_w:
            s = s[:-2] + "…" if len(s) > 2 else ""
        return s

    def new_page() -> None:
        if state["page"]:
            c.showPage()
        state["page"] += 1
        c.setFillColor(dark)
        c.rect(0, height - 70, width, 70, stroke=0, fill=1)
        if logo is not None:
            try:
                c.drawImage(logo, margin, height - 62, width=54, height=54, preserveAspectRatio=True, mask="auto")
            except Exception:
                pass
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 15)
        c.drawString(margin + 64, height - 34, fit(company.get("name") or "Empresa", 15, 300, "Helvetica-Bold"))
        c.setFont("Helvetica", 9)
        c.drawString(margin + 64, height - 50, f"Reporte del negocio · {period['label']} · {period['start']} a {period['end']}")
        c.setFont("Helvetica", 8)
        c.setFillColor(muted)
        c.drawString(margin, 20, "CLONEXA Reportes · margen estimado con el precio de entrada del inventario")
        c.drawRightString(width - margin, 20, f"Página {state['page']}")
        state["y"] = height - 92

    def need(h: float) -> None:
        if state["y"] - h < 40:
            new_page()

    def title(text_: str) -> None:
        need(30)
        c.setFillColor(dark)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(margin, state["y"], text_)
        state["y"] -= 16

    def table(headers: list[str], rows: list[list[Any]], widths: list[float]) -> None:
        need(18)
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(muted)
        x = margin
        for head, w in zip(headers, widths):
            c.drawString(x, state["y"], head)
            x += w
        state["y"] -= 12
        c.setFont("Helvetica", 8)
        for row in rows:
            need(12)
            c.setFillColor(dark)
            x = margin
            for cell, w in zip(row, widths):
                c.drawString(x, state["y"], fit(cell, 8, w - 4))
                x += w
            c.setStrokeColor(line)
            c.line(margin, state["y"] - 3, width - margin, state["y"] - 3)
            state["y"] -= 12
        state["y"] -= 8

    new_page()
    cards = data["kpis"]["cards"]
    box_w = (width - 2 * margin - 10) / 3
    for index, card in enumerate(cards):
        col, row = index % 3, index // 3
        x = margin + col * (box_w + 5)
        y = state["y"] - row * 52
        c.setStrokeColor(line)
        c.roundRect(x, y - 44, box_w, 46, 6, stroke=1, fill=0)
        c.setFillColor(muted)
        c.setFont("Helvetica", 8)
        c.drawString(x + 8, y - 10, card["label"])
        c.setFillColor(dark)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(x + 8, y - 28, _fmt(card["value"], card["kind"]))
        change = card.get("change_pct")
        if change is not None:
            positive = (change >= 0) == (card.get("better") == "up")
            c.setFillColor(good if positive else bad)
            c.setFont("Helvetica", 8)
            c.drawString(x + 8, y - 40, f"{'+' if change >= 0 else ''}{change:.1f}% vs periodo anterior")
    state["y"] -= 52 * ((len(cards) + 2) // 3) + 6
    costing = data["kpis"]["costing"]
    if not costing["complete"]:
        c.setFillColor(bad)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(margin, state["y"], f"Margen incompleto: {costing['uncosted_count']} producto(s) sin precio de entrada "
                                         f"({engine.money_text(costing['uncosted_sales'])} de venta sin costo).")
        state["y"] -= 16
    if data.get("readings"):
        title("Lecturas del periodo")
        c.setFont("Helvetica", 9)
        for reading in data["readings"]:
            need(14)
            c.setFillColor(dark)
            c.drawString(margin + 6, state["y"], fit(f"• {reading}", 9, width - 2 * margin - 6))
            state["y"] -= 13
        state["y"] -= 6
    daily = data["daily"]
    title(f"Venta por día ({daily['idle_days']} días sin operación en el periodo)")
    table(["Día", "Fecha", "Pedidos", "Venta", "Margen"],
          [[d["weekday"], d["date"], d["orders"], _fmt(d["sales"]), _fmt(d["margin"])] for d in daily["table"]],
          [90, 90, 70, 110, 110])
    menu = data["menu"]
    title("Análisis de carta")
    labels = {"estrella": "Estrella", "vaca": "Vaca", "enigma": "Enigma", "perro": "Perro"}
    table(["Producto", "Unidades", "Venta", "Costo", "Margen/u", "Margen total", "Cuadrante"],
          [[p["name"], p["units_text"], _fmt(p["sales"]), _fmt(p["cost"]) if p["costed"] else "Sin costo",
            _fmt(p["margin_unit"]), _fmt(p["margin_total"]), labels.get(p.get("quadrant"), "—")] for p in menu["products"][:40]],
          [150, 60, 70, 70, 60, 70, 60])
    team = data["team"]
    if team["waiters"]:
        title("Equipo")
        table(["Mesero", "Venta", "Mesas", "Ticket", "Horas", "Venta/hora"],
              [[w["name"], _fmt(w["sales"]), w["tables"], _fmt(w["ticket"]), w["hours"], _fmt(w["sales_per_hour"])]
               for w in team["waiters"]], [140, 90, 60, 90, 60, 90])
    ops = data["operations"]
    title("Operación")
    table(["Canal", "Venta", "Cuentas", "Ticket"],
          [[ch["label"], _fmt(ch["sales"]), ch["accounts"], _fmt(ch["ticket"])] for ch in ops["channels"]], [160, 110, 80, 110])
    table(["Método de pago", "Venta"], [[p["label"], _fmt(p["sales"])] for p in ops["payments"]], [160, 110])
    inv = data["inventory"]
    title(f"Inventario: valor actual {engine.money_text(inv['value'])}")
    if inv["buy_today"]:
        table(["Comprar hoy", "Existencia", "Venta diaria", "Días de cobertura"],
              [[r["name"], r["stock"], r["daily"], r["days"]] for r in inv["buy_today"]], [180, 90, 90, 100])
    c.save()
    return buffer.getvalue()
