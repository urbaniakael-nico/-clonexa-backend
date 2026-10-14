"""Reportes v2 (interruptor reports_v2; hoy solo VOLTAGE).

- Interruptor apagado: export.pdf sale igual que siempre y se descarga
  (Content-Disposition attachment); el acceso no cambia (sin sesion, como hoy).
- ?disposition=inline lo abre en el navegador.
- Con reports_v2: PDF carta con "Pagina X de Y", en el idioma de la empresa.
- Las cifras salen del payload; la alerta de horas usa el limite semanal de la empresa.
- Acceso: 403 para supervisor, logistica y operario; pasa el dueno y el director.
"""
from __future__ import annotations

import base64
import re
import uuid
import zlib
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import reports
from app.services import company_locale as cl
from app.services import reports_v2

CHI = ZoneInfo("America/Chicago")
CID = uuid.UUID("76974191-1dc6-4eb4-9b19-7d1e9ad82946")


def payload() -> dict:
    shift = lambda d, reg, ext: {"start": f"2026-10-{d}T13:00:00+00:00", "end": f"2026-10-{d}T23:00:00+00:00", "regular_minutes": reg, "extra_minutes": ext, "gross_amount": 100}  # noqa: E731
    return {
        "company": {"name": "VOLTAGE", "slug": "urban__demo", "logo_url": ""},
        "filters": {"start": "2026-10-05T05:00:00+00:00", "end": "2026-10-12T04:59:59+00:00"},
        "summary": {
            "period": {"start": "2026-10-05T05:00:00+00:00", "end": "2026-10-12T04:59:59+00:00"},
            "employees": {"active": 3}, "attendance": {"active_now": 1, "paused_now": 1},
            "gps": {"outside": 2}, "inventory": {"low_stock": 2, "zero_stock": 1},
            "payroll": {"regular_minutes": 2700, "extra_minutes": 120, "net_amount": 812.5},
        },
        "details": {
            "employees": [{"id": "e1", "full_name": "Nicolás Gómez", "role": "Supervisor", "status": "active"},
                          {"id": "e2", "full_name": "Luis Logística", "role": "Logística", "status": "active"},
                          {"id": "e3", "full_name": "Olga Operaria", "role": "Operario", "status": "active"}],
            "payroll": [{"employee_id": "e1", "employee_name": "Nicolás Gómez", "regular_minutes": 2700, "extra_minutes": 120, "net_amount": 812.5,
                         "shifts": [shift("05", 540, 60), shift("06", 540, 60), shift("07", 540, 0), shift("08", 540, 0), shift("09", 540, 0)]}],
            "gps": [{"employee_id": "e2", "employee_name": "Luis Logística", "gps_status": "outside", "occurred_at": "2026-10-06T15:00:00+00:00"}],
            "materials": [{"order_number": "MAT-1", "material_name": "Cable", "quantity": 3, "unit": "m", "employee_name": "Nicolás Gómez", "status": "delivered",
                           "requested_at": "2026-10-01T15:00:00+00:00", "delivered_at": "2026-10-02T15:00:00+00:00"},
                          {"order_number": "MAT-2", "material_name": "Rack", "quantity": 1, "employee_name": "Nicolás Gómez", "status": "pending"},
                          {"order_number": "MAT-3", "material_name": "Switch", "quantity": 1, "employee_name": "Olga Operaria", "status": "returned",
                           "delivered_at": "2026-10-02T15:00:00+00:00"}],
            "inventory_items": [{"name": "Cable UTP", "current_stock": 0, "min_stock": 10, "status": "active"},
                                {"name": "Conector", "current_stock": 3, "min_stock": 20, "status": "active"},
                                {"name": "Canaleta", "current_stock": 50, "min_stock": 5, "status": "active"}],
            "attendance": [{"employee_id": "e1", "event_type": "check_in", "occurred_at": "2026-10-11T14:00:00+00:00"}],
            "employee_summary": [{"employee_id": "e1", "gps_fuera": 0, "materiales": 2}, {"employee_id": "e2", "gps_fuera": 1, "material_entregado": 2}],
        },
    }


NOW = datetime(2026, 10, 11, 20, 0, tzinfo=timezone.utc)
CODES = {"e1": "supervisor", "e2": "inventario", "e3": "operario"}


def test_figures_come_from_the_payload_and_weekly_alert_uses_the_company_limit():
    ins = reports_v2.build_insights(payload(), CHI, 40 * 60, NOW, CODES)
    f = ins["figures"]
    assert (f["in_shift"], f["active"], f["regular_minutes"], f["extra_minutes"], f["net"], f["gps_outside"], f["low_stock"], f["zero_stock"]) == (2, 3, 2700, 120, 812.5, 2, 2, 1)
    assert f["materials_pending"] == 2, "MAT-1 entregada sin devolver y MAT-2 pendiente"
    kinds = [a["kind"] for a in ins["alerts"]]
    assert kinds.count("weekly_hours") == 1 and kinds.count("gps_outside") == 1 and kinds.count("stale_delivery") == 1 and kinds.count("zero_stock") == 1
    weekly = next(a for a in ins["alerts"] if a["kind"] == "weekly_hours")
    assert weekly["minutes"] == 2820 and weekly["limit"] == 2400 and weekly["week"] == "2026-10-05"
    assert not [a for a in reports_v2.build_insights(payload(), CHI, 48 * 60, NOW, CODES)["alerts"] if a["kind"] == "weekly_hours"], "con 48 h no hay alerta"
    assert [(d["date"], d["regular"], d["extra"]) for d in ins["hours_by_day"][:2]] == [("2026-10-05", 540, 60), ("2026-10-06", 540, 60)]
    assert {k: len(v) for k, v in ins["materials"].items()} == {"requested": 3, "delivered": 2, "consigned": 0, "returned": 1}
    assert [(i["material"], i["label"]) for i in ins["inventory_low"]] == [("Cable UTP", "zero"), ("Conector", "low")]
    people = {p["employee_id"]: p for p in ins["people"]}
    assert people["e1"]["state"] == "working" and people["e1"]["orders_requested"] == 2 and people["e1"]["deliveries"] is None
    assert people["e2"]["deliveries"] == 2 and people["e2"]["orders_requested"] is None and people["e2"]["gps_outside"] == 1
    assert reports_v2.hm(2820) == "47 h 00 min" and reports_v2.hm(65) == "1 h 05 min"


def pdf_text(raw: bytes) -> str:
    chunks = [raw]
    for stream in re.findall(rb"stream\r?\n(.*?)\r?\n?endstream", raw, re.S):
        for decode in (zlib.decompress, lambda b: zlib.decompress(base64.a85decode(b.strip().removesuffix(b"~>")))):
            try:
                chunks.append(decode(stream))
                break
            except Exception:
                pass
    out = []
    for chunk in chunks:
        for m in re.findall(rb"\(((?:[^()\\]|\\.)*)\)\s*Tj", chunk):
            t = re.sub(rb"\\([()\\])", rb"\1", m)
            t = re.sub(rb"\\(\d{3})", lambda x: bytes([int(x.group(1), 8)]), t)
            out.append(t.decode("cp1252", "replace"))
    return " | ".join(out)


def build(locale: dict) -> bytes:
    tokens = cl.use(locale)
    try:
        p = payload()
        return reports_v2.build_pdf(p, reports_v2.build_insights(p, CHI, 2400, NOW, CODES), CHI)
    finally:
        cl.reset(tokens)


def test_pdf_letter_with_page_x_of_y_in_spanish_and_english():
    es = build({"currency": "COP", "timezone": "America/Chicago", "language": "es"})
    en = build({"currency": "USD", "timezone": "America/Chicago", "language": "en"})
    assert b"/MediaBox [ 0 0 612 792 ]" in es, "tamaño carta"
    t_es, t_en = pdf_text(es), pdf_text(en)
    for s in ["Reporte general", "Cifras del periodo", "En turno ahora", "Horas por día", "Alertas", "Materiales", "Inventario bajo mínimo", "Personal", "Página 1 de"]:
        assert s in t_es, s
    for s in ["General report", "Period figures", "On shift now", "Hours per day", "Alerts", "Materials", "Inventory below minimum", "Staff", "Page 1 of",
              "Clock-in outside the perimeter", "Material at zero: Cable UTP", "Delivered", "Zero", "$812.50", "Oct 5, 2026"]:
        assert s in t_en, s
    assert "47 h 00 min" in t_es and "$ 813" in t_es, "horas X h YY min y pesos en español"


class Db:
    async def execute(self, *a, **k):
        raise AssertionError("no se usa")


@pytest.mark.asyncio
async def test_export_pdf_inline_vs_attachment_and_same_pdf_when_switch_is_off(monkeypatch):
    monkeypatch.setattr(reports, "build_report_payload", AsyncMock(return_value=payload()))
    monkeypatch.setattr(reports, "build_report_pdf_bytes", lambda p, d: b"%PDF-v1")
    monkeypatch.setattr(reports_v2, "is_on", AsyncMock(return_value=False))
    args = dict(preset="7d", start_date=None, end_date=None, employee_id=None, module=None, status=None, search=None, detail="all", db=Db(), _access=None)
    res = await reports.export_report_pdf(CID, disposition=None, **args)
    assert res.headers["content-disposition"].startswith("attachment;"), "por defecto sigue descargando"
    body = b"".join([chunk async for chunk in res.body_iterator])
    assert body == b"%PDF-v1", "otra empresa: el PDF de siempre"
    res = await reports.export_report_pdf(CID, disposition="inline", **args)
    assert res.headers["content-disposition"].startswith("inline;")
    monkeypatch.setattr(reports_v2, "is_on", AsyncMock(return_value=True))
    monkeypatch.setattr(reports_v2, "weekly_limit_minutes", AsyncMock(return_value=2400))
    monkeypatch.setattr(reports_v2, "role_codes", AsyncMock(return_value=CODES))
    res = await reports.export_report_pdf(CID, disposition="inline", **args)
    body = b"".join([chunk async for chunk in res.body_iterator])
    assert body.startswith(b"%PDF") and b"/MediaBox [ 0 0 612 792 ]" in body, "reports_v2: PDF carta nuevo"


@pytest.mark.asyncio
@pytest.mark.parametrize("role,allowed", [("supervisor", False), ("inventario", False), ("logistica", False), ("operario", False),
                                          ("company_admin", True), ("admin_empresa", True), ("dueno", True), ("gerencia", True), ("director", True)])
async def test_access_only_owner_and_director_when_switch_is_on(monkeypatch, role, allowed):
    from app.api import deps
    from app.web import admin_v2_routes

    monkeypatch.setattr(reports_v2, "is_on", AsyncMock(return_value=True))
    monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=False))
    monkeypatch.setattr(deps, "require_company_user_for_tenant", AsyncMock(return_value=SimpleNamespace(role=role)))
    if allowed:
        assert await reports.require_reports_access_053c(CID, SimpleNamespace(), "Bearer x", Db()) is None
    else:
        with pytest.raises(HTTPException) as denied:
            await reports.require_reports_access_053c(CID, SimpleNamespace(), "Bearer x", Db())
        assert denied.value.status_code == 403 and denied.value.detail == "Reportes es solo del dueño y del director"


@pytest.mark.asyncio
async def test_other_companies_keep_todays_access(monkeypatch):
    from app.api import deps

    monkeypatch.setattr(reports_v2, "is_on", AsyncMock(return_value=False))
    monkeypatch.setattr(deps, "require_company_user_for_tenant", AsyncMock(side_effect=AssertionError("no se pide sesion")))
    assert await reports.require_reports_access_053c(CID, SimpleNamespace(), None, Db()) is None


def test_all_four_routes_are_guarded_and_switch_is_registered():
    import inspect

    for fn in (reports.general_report, reports.employee_report, reports.export_report_pdf, reports.export_report_csv):
        assert "_access" in inspect.signature(fn).parameters, fn.__name__
    from app.services import switch_registry

    sw = next(s for s in switch_registry.registry()["switches"] if s["key"] == "reports_v2")
    assert sw["module"] == "reports" and sw["delicate"] is True


# ---------------------------------------------------------------- logo del panel (parte 1)
PNG_1PX = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def _logo_env(monkeypatch, published: bool):
    """Marca publicada (Estudio de marca) o, sin ella, el logo de la experiencia de siempre."""
    from app.api.v1.endpoints import companies
    from app.services import brand_media, brand_store, brand_theme

    img = "11111111-2222-3333-4444-555555555555"
    monkeypatch.setattr(brand_store, "published_tokens", AsyncMock(return_value={"logo": img} if published else None))
    monkeypatch.setattr(brand_theme, "branding_for_portal", lambda tokens, cid: {"logo_url": f"/brand-media/{cid}/{tokens['logo']}.webp"})
    monkeypatch.setattr(brand_media, "read", AsyncMock(return_value=PNG_1PX))
    monkeypatch.setattr(companies, "_get_company_or_404", AsyncMock(return_value=SimpleNamespace()))
    old = "data:image/png;base64," + base64.b64encode(PNG_1PX).decode()
    monkeypatch.setattr(companies, "_read_company_branding", lambda company: {"logo_url": old})
    return f"/brand-media/{CID}/{img}.webp", old


@pytest.mark.asyncio
@pytest.mark.parametrize("published", [True, False])
async def test_screen_and_pdf_use_the_home_panel_logo(monkeypatch, published):
    from app.services import panel_logo

    new, old = _logo_env(monkeypatch, published)
    expected = new if published else old
    assert (await panel_logo.panel_logo(Db(), CID)) == {"url": expected, "source": "published" if published else "experience"}
    monkeypatch.setattr(reports_v2, "is_on", AsyncMock(return_value=True))
    monkeypatch.setattr(reports_v2, "weekly_limit_minutes", AsyncMock(return_value=2400))
    monkeypatch.setattr(reports_v2, "role_codes", AsyncMock(return_value=CODES))
    # Pantalla: el payload de /general lleva el logo del panel (no el de company_branding).
    screen = await reports._with_insights_053c(Db(), CID, payload())
    assert screen["company"]["logo_url"] == expected
    # PDF: el lector de logo recibe esos mismos bytes y la imagen queda dentro del PDF.
    seen = []
    real_reader = reports.report_pdf_logo_reader
    monkeypatch.setattr(reports, "report_pdf_logo_reader", lambda src: seen.append(src) or real_reader(src))
    monkeypatch.setattr(reports, "build_report_payload", AsyncMock(return_value=payload()))
    args = dict(preset="7d", start_date=None, end_date=None, employee_id=None, module=None, status=None, search=None, detail="all", db=Db(), _access=None)
    res = await reports.export_report_pdf(CID, disposition="inline", **args)
    body = b"".join([chunk async for chunk in res.body_iterator])
    assert seen and base64.b64decode(seen[0].split(",", 1)[1]) == PNG_1PX
    assert b"/Subtype /Image" in body


@pytest.mark.asyncio
async def test_published_brand_without_logo_shows_no_logo_like_the_portal(monkeypatch):
    from app.services import brand_theme, panel_logo

    _logo_env(monkeypatch, True)
    monkeypatch.setattr(brand_theme, "branding_for_portal", lambda tokens, cid: {"logo_url": ""})
    assert await panel_logo.panel_logo(Db(), CID) == {"url": "", "source": "none"}
