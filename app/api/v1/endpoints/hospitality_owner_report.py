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

Acceso (049U): SOLO el dueño (cuenta de la empresa o rol dueño/owner/
propietario, la misma definicion que el arqueo de caja) o Admin V2. Un
administrador, gerente, cajero o mesero que entre por la direccion directa
recibe 403: margen, costos y venta por mesero son del dueño.

049U: /live (el bloque de HOY, el portal lo pide cada pocos segundos) y
/alerts (lo que hay que resolver, con el enlace a donde se resuelve).
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

from app.api.deps import get_db, require_company_user_for_tenant, require_enabled_module
from app.api.v1.endpoints.hospitality import (
    _hospitality_company_identity,
    _hsp_company_report_settings,
    _hsp_report_logo_reader,
    _hsp_report_zone,
)
from app.services import owner_report as engine
from app.services import restock
from app.services import sales_ledger
from app.services.cash_count import OWNER_ROLES as CASH_OWNER_ROLES
from app.web.admin_v2_routes import _active_session as active_admin_v2_session

router = APIRouter()

MODULE_CODE = "waiter_ordering"
# Quien ve Reportes. Las empresas con el interruptor de Reportes del dueño
# (049U: hoy ASADERO, el mismo interruptor por empresa que Carta) lo abren SOLO
# para el dueño; las demas (The Time Machine) siguen con dueño o gerente.
LEGACY_OWNER_ROLES = {"company_admin", "admin_empresa", "manager", "gerencia", "gerente", "dueno", "dueño", "owner", "propietario"}
OWNER_ROLES = set(CASH_OWNER_ROLES)  # company_admin, admin_empresa, dueño, owner, propietario


async def owner_only(db: AsyncSession, company_id: uuid.UUID) -> bool:
    """049U: el interruptor por empresa de los Reportes del dueño."""
    from app.api.v1.endpoints import carta as carta_endpoint

    return await carta_endpoint.carta_enabled(db, company_id)


async def require_owner_report(
    company_id: uuid.UUID, request: Request,
    authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db),
) -> str:
    await require_enabled_module(db, company_id, MODULE_CODE)
    if await active_admin_v2_session(request, db):
        return "Admin V2"
    roles = OWNER_ROLES if await owner_only(db, company_id) else LEGACY_OWNER_ROLES
    user = await require_company_user_for_tenant(db, authorization, company_id, allowed_roles=roles)
    return str(getattr(user, "full_name", "") or "Dueño")


async def require_owner_only(
    company_id: uuid.UUID, request: Request,
    authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db),
) -> str:
    """Los endpoints nuevos (HOY y alertas) son del dueño en todas las empresas."""
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
    by_charge = await sales_ledger.enabled(db, company_id)
    orders, closures = await _orders_between(db, cid, window_start, window_end, by_charge=by_charge)
    inventory = {str(r["id"]): dict(r) for r in (await db.execute(text("""
        SELECT id, COALESCE(NULLIF(name, ''), name_reference, sku) AS name, entry_price, sale_price, current_stock, status,
               avg_cost, units_per_purchase, item_type, consumption_unit
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
    cash_counts = []
    if details and await _table_exists(db, "cash_counts"):
        # 049I: historico de faltantes y sobrantes por cajero (arqueos del periodo).
        cash_counts = [dict(r) for r in (await db.execute(text("""
            SELECT cashier_name, COUNT(*) AS counts,
                   COALESCE(SUM(-difference) FILTER (WHERE difference < 0), 0) AS shortage,
                   COALESCE(SUM(difference) FILTER (WHERE difference > 0), 0) AS surplus,
                   COUNT(*) FILTER (WHERE difference < 0) AS shortages
            FROM cash_counts
            WHERE company_id = CAST(:company_id AS uuid) AND created_at >= :start AND created_at < :end
            GROUP BY cashier_name ORDER BY 3 DESC
        """), {"company_id": cid, "start": period_start, "end": period_end})).mappings().all()]
    report = engine.Report(orders=orders, closures=closures, inventory=inventory, portions=portions, tz=tz,
                           period=chosen, business_day=business_day, sessions=sessions, confirmed_ends=confirmed,
                           by_charge=by_charge)
    # 049M: gastos fijos (Inventario > Gastos fijos) del periodo y del anterior.
    from app.api.v1.endpoints.fixed_expenses import fixed_expenses_for_period

    fixed = await fixed_expenses_for_period(db, company_id, chosen["start"], chosen["end"])
    fixed_prev = await fixed_expenses_for_period(db, company_id, chosen["prev_start"], chosen["prev_end"])
    # 049T: con Carta, el inventario de Reportes sale del mismo calculo que Stock
    # y Proximas compras (saldos en dinero y consumo real de los movimientos).
    from app.api.v1.endpoints import carta as carta_endpoint

    stock = None
    if await carta_endpoint.carta_enabled(db, company_id):
        stock = (await carta_endpoint.load_insumos(db, company_id), await carta_endpoint.load_usage(db, company_id))
    return {"report": report, "period": chosen, "tz": tz_name, "cash_counts": cash_counts, "fixed": fixed, "fixed_prev": fixed_prev,
            "stock": stock}


def _period_payload(period: dict) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in period.items()}


async def _summary(ctx: dict) -> dict:
    report = ctx["report"]
    kpis = report.kpis()
    statement = engine.income_statement(kpis, ctx.get("fixed") or {"total": 0}, ctx.get("fixed_prev") or {"total": 0})
    kpis["cards"].insert(4, engine.profit_card(statement))
    return engine.public({
        "period": _period_payload(ctx["period"]),
        "timezone": ctx["tz"],
        "kpis": kpis,
        "income_statement": statement,
        "readings": report.readings(kpis=kpis, inventory=restock.report_inventory(*ctx["stock"]) if ctx.get("stock") else None),
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
        "inventory": restock.report_inventory(*ctx["stock"]) if ctx.get("stock") else report.inventory_report(),
        "cash_counts": [{"cashier_name": r["cashier_name"], "counts": int(r["counts"]), "shortages": int(r["shortages"]),
                         "shortage": r["shortage"], "surplus": r["surplus"]} for r in ctx.get("cash_counts") or []],
    })


# ----------------------------------------------------- 049U: HOY y alertas ---
async def _orders_between(db: AsyncSession, cid: str, start: datetime, end: datetime, *,
                          by_charge: bool = False) -> tuple[list[dict], list[dict]]:
    if by_charge:
        # 049Z: creados o cobrados en la ventana, igual que el panel de caja.
        return await sales_ledger.load_orders(db, cid, start, end), []
    orders = [dict(r) for r in (await db.execute(text("""
        SELECT id, created_at, updated_at, closed_at, cancelled_at, archived_at, status, order_type, source,
               table_key, table_number, payment_method, total, items, metadata, inventory_deducted
        FROM hospitality_orders
        WHERE company_id = CAST(:company_id AS uuid) AND created_at >= :start AND created_at < :end
    """), {"company_id": cid, "start": start, "end": end})).mappings().all()]
    closures = [dict(r) for r in (await db.execute(text("""
        SELECT id, opened_at, closed_at, order_ids
        FROM hospitality_day_closures
        WHERE company_id = CAST(:company_id AS uuid) AND closed_at >= :start AND closed_at < :end
    """), {"company_id": cid, "start": start, "end": end + timedelta(days=2)})).mappings().all()]
    return orders, closures


async def _inventory_and_portions(db: AsyncSession, cid: str) -> tuple[dict, dict]:
    inventory = {str(r["id"]): dict(r) for r in (await db.execute(text("""
        SELECT id, COALESCE(NULLIF(name, ''), name_reference, sku) AS name, entry_price, sale_price, current_stock, status,
               avg_cost, units_per_purchase, item_type, consumption_unit
        FROM inventory_items
        WHERE company_id = CAST(:company_id AS uuid) AND COALESCE(status, 'active') NOT IN ('archived', 'deleted')
    """), {"company_id": cid})).mappings().all()}
    portions = {}
    if await _table_exists(db, "hospitality_product_portions"):
        portions = {str(r["inventory_item_id"]): dict(r) for r in (await db.execute(text("""
            SELECT inventory_item_id, product_group_key AS group_key, group_label, portion_label
            FROM hospitality_product_portions WHERE company_id = CAST(:company_id AS uuid)
        """), {"company_id": cid})).mappings().all()}
    return inventory, portions


async def _live(db: AsyncSession, company_id: uuid.UUID, now: datetime | None = None) -> dict:
    settings = await _hsp_company_report_settings(db, company_id)
    if settings is None:
        raise HTTPException(status_code=404, detail="company_not_found")
    tz_name, business_day = settings
    tz = _hsp_report_zone(tz_name)
    now = now or datetime.now(timezone.utc)
    today = _today(tz, business_day)
    cid = str(company_id)
    by_charge = await sales_ledger.enabled(db, company_id)
    inventory, portions = await _inventory_and_portions(db, cid)
    period = engine.today_period(today)
    start = datetime.combine(period["prev_start"] - timedelta(days=1), time.min, tz).astimezone(timezone.utc)
    orders, closures = await _orders_between(db, cid, start, now + timedelta(days=1), by_charge=by_charge)
    report = engine.Report(orders=orders, closures=closures, inventory=inventory, portions=portions, tz=tz,
                           period=period, business_day=business_day, now=now, by_charge=by_charge)
    block = engine.live_block(report, now)
    block["last_close"] = None
    if not block["has_sales"]:
        # sin operacion hoy: el cierre del ultimo dia con ventas, con su fecha
        last = (await db.execute(text("""
            SELECT id, created_at FROM hospitality_orders
            WHERE company_id = CAST(:company_id AS uuid) AND created_at < :before
              AND LOWER(COALESCE(status, '')) NOT IN ('cancelado', 'cancelled', 'canceled', 'merma')
            ORDER BY created_at DESC LIMIT 1
        """), {"company_id": cid, "before": datetime.combine(today, time.min, tz).astimezone(timezone.utc)})).mappings().first()
        if last and last.get("created_at"):
            around = engine.aware(last["created_at"])
            day_orders, day_closures = await _orders_between(db, cid, around - timedelta(days=2), around + timedelta(days=2),
                                                             by_charge=by_charge)
            resolve = (sales_ledger.day_resolver(tz, business_day) if by_charge
                       else engine.jornada_resolver(day_orders, day_closures, tz, business_day))
            last_order = next((o for o in day_orders if str(o.get("id")) == str(last.get("id"))), None)
            day = (resolve(last_order) if last_order else None) or around.astimezone(tz).date()
            day_report = engine.Report(orders=day_orders, closures=day_closures, inventory=inventory, portions=portions, tz=tz,
                                       period={**engine.today_period(day), "label": "Último cierre"}, business_day=business_day, now=now,
                                       by_charge=by_charge)
            block["last_close"] = engine.day_close(day_report)
    block["generated_at"] = now.isoformat()
    block["timezone"] = tz_name
    return block


@router.get("/companies/{company_id}/owner-report/live")
async def owner_report_live(company_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                            _actor: str = Depends(require_owner_only)) -> dict:
    """El bloque de HOY: el portal lo pide cada pocos segundos."""
    return engine.public(await _live(db, company_id))


@router.get("/companies/{company_id}/owner-report/alerts")
async def owner_report_alerts(company_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                              _actor: str = Depends(require_owner_only)) -> dict:
    """Lo que hay que resolver, cada uno con el enlace a donde se resuelve."""
    settings = await _hsp_company_report_settings(db, company_id)
    if settings is None:
        raise HTTPException(status_code=404, detail="company_not_found")
    tz_name, business_day = settings
    tz = _hsp_report_zone(tz_name)
    now = datetime.now(timezone.utc)
    cid = str(company_id)
    alerts: list[dict] = []
    from app.api.v1.endpoints import carta as carta_endpoint

    carta_on = await carta_endpoint.carta_enabled(db, company_id)
    # 1. productos sin precio de entrada en lo vendido de los ultimos 7 dias
    week = engine.resolve_period("7d", _today(tz, business_day))
    inventory, portions = await _inventory_and_portions(db, cid)
    start = datetime.combine(week["start"] - timedelta(days=1), time.min, tz).astimezone(timezone.utc)
    by_charge = await sales_ledger.enabled(db, company_id)
    orders, closures = await _orders_between(db, cid, start, now + timedelta(days=1), by_charge=by_charge)
    week_report = engine.Report(orders=orders, closures=closures, inventory=inventory, portions=portions, tz=tz,
                                period=week, business_day=business_day, now=now, by_charge=by_charge)
    costing = week_report.kpis()["costing"]
    if costing["uncosted"]:
        alerts.append({"kind": "uncosted", "severity": "bad",
                       "title": f"{len(costing['uncosted'])} producto(s) sin precio de entrada: el margen está incompleto",
                       "detail": f"{engine.money_text(costing['uncosted_sales'])} vendidos en los últimos 7 días no tienen costo.",
                       "items": [p["name"] for p in costing["uncosted"]],
                       "link": {"module": "carta" if carta_on else "inventory",
                                "label": "Completar en Carta" if carta_on else "Cargar en Inventario"}})
    # 2. insumos por agotarse y 3. platos por debajo del costo (con Carta)
    if carta_on:
        insumos = await carta_endpoint.load_insumos(db, company_id)
        plan = restock.plan(insumos, await carta_endpoint.load_usage(db, company_id), {}, 3)
        soon = [r for r in plan["buy"] if r["reason"] in {"agotado", "bajo_minimo"} or (r["days_left"] is not None and r["days_left"] <= 3)]
        if soon:
            alerts.append({"kind": "restock", "severity": "warn",
                           "title": f"{len(soon)} insumo(s) agotado(s) o por agotarse",
                           "detail": "Agotados, bajo el mínimo o que se acaban en 3 días o menos al ritmo actual.",
                           "items": [r["name"] for r in soon],
                           "link": {"module": "inventory", "mode": "compras", "label": "Ver Próximas compras"}})
        carta = await carta_endpoint._carta_payload(db, company_id)
        below = [d for d in carta["items"] if d.get("below_cost") and d.get("active")]
        if below:
            alerts.append({"kind": "below_cost", "severity": "bad",
                           "title": f"{len(below)} plato(s) por debajo del costo",
                           "detail": "Se venden por menos de lo que cuestan sus ingredientes.",
                           "items": [f"{d['name']} ({engine.money_text(d['price'])} vs costo {engine.money_text(d['cost'])})" for d in below],
                           "link": {"module": "carta", "label": "Revisar en Carta"}})
    # 4. mesas abiertas hace mucho
    live = await _live(db, company_id, now)
    if live["long_open_tables"]:
        alerts.append({"kind": "long_tables", "severity": "warn",
                       "title": f"{len(live['long_open_tables'])} mesa(s) abierta(s) hace más de {engine.LONG_TABLE_MINUTES // 60} horas",
                       "detail": "Puede ser una cuenta que se olvidó cerrar.",
                       "items": [f"{t['table']} · {t['minutes'] // 60} h {t['minutes'] % 60} min · {engine.money_text(t['total'])}"
                                 for t in live["long_open_tables"]],
                       "link": {"module": "orders", "label": "Ver mesas"}})
    return engine.public({"alerts": alerts, "generated_at": now.isoformat()})


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
        c.drawString(x + 8, y - 10, fit(card["label"], 8, box_w - 16))
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
