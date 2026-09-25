"""Reportes para el dueño (049G), restaurantes con waiter_ordering.

Margen con precio de entrada (y aviso de lo que falta costear), porciones,
mapa de calor por jornada, cuadrantes de la carta, venta por hora trabajada
con turnos reales, las cuatro correcciones, lecturas, PDF y acceso.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.api import deps
from app.api.deps import get_db
from app.api.v1.endpoints import hospitality_owner_report as endpoint
from app.services import owner_report as engine

BOG = ZoneInfo("America/Bogota")
POLLO, PAPA, GASEOSA, SOPA, CUARTO, ENTERO, SINCOSTO = (str(uuid.uuid4()) for _ in range(7))
INVENTORY = {
    POLLO: {"name": "POLLO Asado", "entry_price": 20000, "current_stock": 10},
    PAPA: {"name": "Papa salada", "entry_price": 1000, "current_stock": 2},
    GASEOSA: {"name": "Gaseosa", "entry_price": 2500, "current_stock": 40},
    SOPA: {"name": "Sopa", "entry_price": 3000, "current_stock": 0},
    CUARTO: {"name": "Cuarto de pollo broster", "entry_price": 0, "current_stock": 5},
    ENTERO: {"name": "Pollo broster entero", "entry_price": 24000, "current_stock": 3},
    SINCOSTO: {"name": "Limonada", "entry_price": 0, "current_stock": 9},
}
PORTIONS = {
    CUARTO: {"group_key": "broster", "group_label": "Pollo broster", "portion_label": "1/4"},
    ENTERO: {"group_key": "broster", "group_label": "Pollo broster", "portion_label": "1"},
}


def local(day: str, hh: int, mm: int = 0) -> datetime:
    return datetime.fromisoformat(day).replace(hour=hh, minute=mm, tzinfo=BOG).astimezone(timezone.utc)


def item(item_id, qty, subtotal, label="", station="parrilla", created=None, ready=None):
    row = {"inventory_item_id": item_id, "name": INVENTORY[item_id]["name"], "quantity": qty, "subtotal": subtotal,
           "station": station, "created_at": created.isoformat() if created else None,
           "ready_at": ready.isoformat() if ready else None}
    if label:
        row["quantity_label"] = label
    return row


def order(created, items, total=None, *, status="cerrado", table="Mesa 1", order_type="table", waiter="w1",
          waiter_name="Ana", payment="cash", closed=None, metadata=None, archived=True):
    meta = {"waiter": {"id": waiter, "name": waiter_name}, **(metadata or {})}
    return {"id": str(uuid.uuid4()), "created_at": created, "closed_at": closed or created + timedelta(minutes=50),
            "cancelled_at": created + timedelta(minutes=5) if status == "cancelado" else None, "updated_at": created,
            "archived_at": created if archived else None, "status": status, "order_type": order_type, "source": "table_manual",
            "table_key": table.lower(), "table_number": table, "payment_method": payment,
            "total": total if total is not None else sum(i["subtotal"] for i in items), "items": items,
            "metadata": meta, "inventory_deducted": True}


def period(kind="custom", start=date(2026, 9, 1), end=date(2026, 9, 21)):
    return engine.resolve_period(kind, date(2026, 9, 25), start, end)


def report(orders, closures=None, per=None, **kwargs):
    return engine.Report(orders=orders, closures=closures or [], inventory=INVENTORY, portions=PORTIONS, tz=BOG,
                         period=per or period(), **kwargs)


# ----------------------------------------------------------- margen ---
def test_hospitality_owner_report_margin_uses_entry_price_and_flags_uncosted():
    orders = [order(local("2026-09-10", 13), [item(POLLO, 1, 40000), item(GASEOSA, 2, 10000), item(SINCOSTO, 1, 6000)])]
    kpis = report(orders).kpis()
    cards = {c["key"]: c for c in kpis["cards"]}
    assert cards["sales"]["value"] == 56000
    # costo: pollo 20.000 + 2 gaseosas 5.000 = 25.000 sobre 50.000 de venta costeada
    assert cards["margin"]["value"] == 25000
    assert cards["cost_pct"]["value"] == 50
    costing = kpis["costing"]
    assert costing["complete"] is False and costing["uncosted_count"] == 1
    assert costing["uncosted"] == [{"name": "Limonada", "sales": 6000.0}]
    assert costing["uncosted_sales"] == 6000


def test_hospitality_owner_report_portion_cost_is_the_fraction_actually_deducted():
    # Boton 1/4 sobre POLLO Asado: el inventario descuenta 0.25 pollos -> 0.25 x 20.000.
    quarter = report([order(local("2026-09-10", 13), [item(POLLO, 0.25, 12000, label="1/4")])]).kpis()
    assert {c["key"]: c for c in quarter["cards"]}["margin"]["value"] == 12000 - 5000
    # Porcion propia sin precio de entrada: 1/4 x el precio de entrada del entero del grupo, marcado derivado.
    broster = report([order(local("2026-09-10", 13), [item(CUARTO, 2, 20000)])]).kpis()
    assert {c["key"]: c for c in broster["cards"]}["margin"]["value"] == 20000 - 2 * 6000
    assert broster["costing"]["derived"] == ["Pollo broster"] and broster["costing"]["complete"] is True


def test_hospitality_owner_report_merma_counts_its_cost_and_cancellation_does_not():
    merma = order(local("2026-09-10", 20), [item(POLLO, 1, 40000)], status="cancelado",
                  metadata={"loss": True, "inventory_was_deducted": True})
    cancel = order(local("2026-09-10", 20, 30), [item(GASEOSA, 1, 5000)], status="cancelado",
                   metadata={"loss": True, "inventory_was_deducted": False})
    sale = order(local("2026-09-10", 13), [item(GASEOSA, 1, 5000)])
    kpis = report([merma, cancel, sale]).kpis()
    assert kpis["losses"] == {"cancelled_total": 5000.0, "cancelled_count": 1, "merma_total": 40000.0,
                              "merma_cost": 20000.0, "merma_count": 1}
    assert {c["key"]: c for c in kpis["cards"]}["sales"]["value"] == 5000


def test_hospitality_owner_report_changes_vs_previous_equivalent_period():
    per = period("7d")
    assert (per["start"], per["end"], per["prev_start"], per["prev_end"]) == (
        date(2026, 9, 19), date(2026, 9, 25), date(2026, 9, 12), date(2026, 9, 18))
    month = period("month")
    assert (month["prev_start"], month["prev_end"]) == (date(2026, 8, 1), date(2026, 8, 25))
    orders = [order(local("2026-09-20", 13), [item(GASEOSA, 2, 12000)]),
              order(local("2026-09-13", 13), [item(GASEOSA, 2, 10000)])]
    sales = {c["key"]: c for c in report(orders, per=per).kpis()["cards"]}["sales"]
    assert sales["previous"] == 10000 and sales["change_pct"] == 20.0
    with pytest.raises(ValueError):
        engine.resolve_period("custom", date(2026, 9, 25), date(2026, 1, 1), date(2026, 9, 1))


# ------------------------------------------------------- jornada ---
def test_hospitality_owner_report_heatmap_puts_sales_in_the_jornada_day_and_real_hour():
    # Jornada del viernes 18/09 que abre a las 6 p.m. y un pedido a la 1 a.m. del sabado.
    opened = local("2026-09-18", 18)
    late = order(local("2026-09-19", 1), [item(GASEOSA, 1, 5000)])
    early = order(opened, [item(GASEOSA, 1, 7000)])
    closure = {"id": "c1", "opened_at": opened, "order_ids": [late["id"], early["id"]]}
    rep = report([late, early], closures=[closure])
    cells = {(c["weekday"], c["hour"]): c["sales"] for c in rep.heatmap()["cells"]}
    assert cells == {(4, 1): 5000.0, (4, 18): 7000.0}, "viernes (4), no sabado: la venta es de esa jornada"
    assert rep.heatmap()["hours"] == [18, 1], "la madrugada va al final de la fila"
    # Con horario configurado (18:00 a 04:00) tambien cae en el viernes.
    hours = {"open": time(18), "close": time(4), "overnight": True}
    rep2 = report([order(local("2026-09-19", 2), [item(GASEOSA, 1, 5000)])], business_day=hours)
    assert rep2.heatmap()["cells"][0]["weekday"] == 4


# ------------------------------------------------------ carta ---
def test_hospitality_owner_report_menu_quadrants():
    orders = []
    day = local("2026-09-10", 13)
    # Estrella: mucho y deja mucho | Vaca: mucho, deja poco | Enigma: poco, deja mucho | Perro: poco, poco.
    orders += [order(day, [item(POLLO, 1, 45000)]) for _ in range(10)]      # margen 25.000 c/u
    orders += [order(day, [item(GASEOSA, 1, 3000)]) for _ in range(12)]     # margen 500 c/u
    orders += [order(day, [item(SOPA, 1, 30000)]) for _ in range(2)]        # margen 27.000 c/u
    orders += [order(day, [item(PAPA, 1, 1500)]) for _ in range(1)]         # margen 500 c/u
    menu = report(orders).menu()
    quadrants = {p["name"]: p["quadrant"] for p in menu["products"]}
    assert quadrants == {"POLLO Asado": "estrella", "Gaseosa": "vaca", "Sopa": "enigma", "Papa salada": "perro"}
    pollo = next(p for p in menu["products"] if p["name"] == "POLLO Asado")
    assert pollo["margin_unit"] == 25000 and pollo["margin_total"] == 250000 and pollo["cost"] == 200000
    assert report(orders[:3]).menu()["thresholds"] is None, "con menos de 3 productos no clasifica"


# ------------------------------------------------ correcciones ---
def test_hospitality_owner_report_fix_a_busiest_weekday_needs_three_repeats():
    one = report([order(local("2026-09-16", 13), [item(GASEOSA, 1, 693000)])]).busiest_weekday()
    assert one == {"enough": False, "message": "Datos insuficientes, se necesitan al menos 3 semanas"}
    saturdays = [order(local(d, 13), [item(GASEOSA, 1, 9000)]) for d in ("2026-09-05", "2026-09-12", "2026-09-19")]
    tuesdays = [order(local(d, 13), [item(GASEOSA, 1, 3000)]) for d in ("2026-09-01", "2026-09-08", "2026-09-15")]
    busy = report(saturdays + tuesdays).busiest_weekday()
    assert busy["enough"] and busy["weekday"] == "Sábado" and busy["days"] == 3 and busy["average"] == 9000
    readings = report(saturdays + tuesdays).readings()
    assert "El sábado vendes 3 veces lo del martes." in readings


def test_hospitality_owner_report_fix_b_whole_units_and_portion_breakdown():
    day = local("2026-09-10", 13)
    orders = [order(day, [item(POLLO, 0.25, 12000, label="1/4")]), order(day, [item(POLLO, 0.25, 12000, label="1/4")]),
              order(day, [item(POLLO, 0.5, 22000, label="1/2")]), order(day, [item(POLLO, 1, 40000)])]
    pollo = report(orders).menu()["products"][0]
    assert pollo["units_text"] == "2", "2 de 1/4 + 1/2 + 1 entero = 2 pollos"
    assert pollo["portions_text"] == "2 de 1/4, 1 de 1/2, 1 entero"
    three_quarters = report(orders[:3] + [order(day, [item(POLLO, 0.75, 30000, label="3/4")])]).menu()["products"][0]
    assert three_quarters["units_text"] == "1 y 3/4"
    merged = report([order(day, [item(POLLO, 0.5, 24000, label="1/4")])]).menu()["products"][0]
    assert merged["portions_text"] == "2 de 1/4" and merged["units_text"] == "1/2", "dos 1/4 unidos en una linea"


def test_hospitality_owner_report_fix_c_only_days_with_sales_and_idle_count():
    per = engine.resolve_period("custom", date(2026, 9, 25), date(2026, 9, 1), date(2026, 9, 14))
    daily = report([order(local("2026-09-10", 13), [item(GASEOSA, 1, 5000)])], per=per).daily()
    assert len(daily["days"]) == 14 and [d["date"] for d in daily["table"]] == ["2026-09-10"]
    assert daily["idle_days"] == 13


def test_hospitality_owner_report_fix_d_tables_and_deliveries_are_separate():
    day = local("2026-09-10", 13)
    ops = report([
        order(day, [item(GASEOSA, 1, 5000)], table="Mesa 3"),
        order(day, [item(POLLO, 1, 40000)], table="Juan · Calle 5", order_type="domicilio", payment="transfer"),
    ]).operations()
    assert [t["name"] for t in ops["top_tables"]] == ["Mesa 3"]
    assert [d["name"] for d in ops["top_deliveries"]] == ["Juan · Calle 5"]
    assert {c["channel"]: c["sales"] for c in ops["channels"]} == {"domicilio": 40000.0, "mesa": 5000.0}
    assert {p["label"]: p["sales"] for p in ops["payments"]} == {"Transferencia": 40000.0, "Efectivo": 5000.0}


# ------------------------------------------------------ equipo ---
def test_hospitality_owner_report_sales_per_hour_use_real_shifts():
    day = local("2026-09-10", 13)
    orders = [order(day, [item(POLLO, 1, 40000)], waiter="ana", waiter_name="Ana", table="Mesa 1"),
              order(day, [item(POLLO, 1, 40000)], waiter="beto", waiter_name="Beto", table="Mesa 2"),
              order(day, [item(POLLO, 1, 40000)], waiter="beto", waiter_name="Beto", table="Mesa 3")]
    cut_id = str(uuid.uuid4())
    sessions = [
        {"id": str(uuid.uuid4()), "user_id": "ana", "status": "finished", "started_at": local("2026-09-10", 12),
         "active_seconds": 2 * 3600, "break_seconds": 0, "closed_reason": ""},
        {"id": str(uuid.uuid4()), "user_id": "beto", "status": "finished", "started_at": local("2026-09-10", 12),
         "active_seconds": 8 * 3600, "break_seconds": 0, "closed_reason": ""},
        # Turno cortado por el sistema sin hora real: no cuenta.
        {"id": cut_id, "user_id": "ana", "status": "finished", "started_at": local("2026-09-11", 12),
         "active_seconds": 12 * 3600, "break_seconds": 0, "closed_reason": "corte_diario"},
    ]
    team = report(orders, sessions=sessions).team()
    rows = {w["name"]: w for w in team["waiters"]}
    assert rows["Ana"]["hours"] == 2 and rows["Ana"]["sales_per_hour"] == 20000
    assert rows["Beto"]["hours"] == 8 and rows["Beto"]["sales_per_hour"] == 10000 and rows["Beto"]["tables"] == 2
    assert [w["name"] for w in team["waiters"]] == ["Ana", "Beto"], "gana quien vende mas por hora, no el de mas horas"
    assert team["excluded_hours"] == 12
    confirmed = report(orders, sessions=sessions, confirmed_ends={cut_id: local("2026-09-11", 16)}).team()
    assert {w["name"]: w for w in confirmed["waiters"]}["Ana"]["hours"] == 6


def test_hospitality_owner_report_kitchen_times():
    start = local("2026-09-10", 13)
    orders = [order(start, [item(POLLO, 1, 40000, station="parrilla", created=start, ready=start + timedelta(minutes=25)),
                            item(GASEOSA, 1, 5000, station="bebidas", created=start, ready=start + timedelta(minutes=2))]),
              order(start, [item(POLLO, 1, 40000, station="parrilla", created=start, ready=start + timedelta(minutes=15))])]
    kitchen = report(orders).kitchen()
    pollo = next(p for p in kitchen["products"] if p["name"] == "POLLO Asado")
    assert pollo["avg_minutes"] == 20 and pollo["max_minutes"] == 25
    assert kitchen["stations"][0]["name"] == "parrilla" and kitchen["slow_pct"] == 50.0


def test_hospitality_owner_report_inventory_coverage_and_buy_list():
    per = engine.resolve_period("custom", date(2026, 9, 25), date(2026, 9, 1), date(2026, 9, 10))
    orders = [order(local("2026-09-05", 13), [item(PAPA, 10, 15000)]), order(local("2026-09-06", 13), [item(GASEOSA, 5, 15000)])]
    inv = report(orders, per=per).inventory_report()
    assert inv["buy_today"] == [{"name": "Papa salada", "stock": 2.0, "daily": 1.0, "days": 2.0}]
    assert "Limonada" in [r["name"] for r in inv["idle"]]
    assert inv["value"] == 10 * 20000 + 2 * 1000 + 40 * 2500 + 3 * 24000
    assert inv["uncosted_items"] == 2
    assert "Se acaban en menos de 3 días: Papa salada." in report(orders, per=per).readings()


def test_hospitality_owner_report_readings_only_with_enough_data():
    single = report([order(local("2026-09-10", 13), [item(GASEOSA, 1, 5000)])], per=period("custom", date(2026, 9, 10), date(2026, 9, 10)))
    for reading in single.readings():
        assert "veces" not in reading and "cancelaron" not in reading
    losses = [order(local("2026-09-10", 20, m), [item(GASEOSA, 1, 5000)], status="cancelado",
                    metadata={"inventory_was_deducted": False}) for m in (1, 10, 20)]
    readings = report(losses + [order(local("2026-09-10", 13), [item(GASEOSA, 1, 5000)])]).readings()
    assert "Se cancelaron $15.000 en 3 pedidos, casi todo entre las 8 p.m. y las 9 p.m." in readings


def test_hospitality_owner_report_pdf_is_generated():
    orders = [order(local("2026-09-10", 13), [item(POLLO, 1, 40000), item(SINCOSTO, 1, 6000)])]
    rep = report(orders)
    kpis = rep.kpis()
    data = engine.public({"period": {"label": "Personalizado", "start": "2026-09-01", "end": "2026-09-21"},
                          "kpis": kpis, "readings": rep.readings(kpis=kpis), "daily": rep.daily(), "menu": rep.menu(),
                          "team": rep.team(), "operations": rep.operations(), "inventory": rep.inventory_report()})
    pdf = endpoint.build_owner_report_pdf({"name": "ASADERO EL SOCIO", "logo_url": ""}, data)
    assert pdf.startswith(b"%PDF") and len(pdf) > 1500


# ------------------------------------------------------ acceso ---
ASADERO = "7625872c-f941-4479-a27b-f8443be953c5"
VELVET = str(uuid.uuid4())
USERS = {
    "dueno": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(ASADERO), role="dueno", full_name="Dueño", email=""),
    "administrador": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(ASADERO), role="administrador", full_name="Adm", email=""),
    "velvet": SimpleNamespace(id=uuid.uuid4(), company_id=uuid.UUID(VELVET), role="company_admin", full_name="V", email=""),
}


class Db:
    def __init__(self):
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        p = params or {}
        cid = str(p.get("company_id", ""))
        rows = []
        if "FROM company_modules cm JOIN modules m" in sql:
            rows = [{"code": "waiter_ordering"}] if cid == ASADERO else []
        elif sql.startswith("SELECT name, slug, timezone, settings_json FROM companies"):
            rows = [{"name": "ASADERO EL SOCIO", "slug": "asadero", "timezone": "America/Bogota", "settings_json": {}}]
        elif sql.startswith("SELECT timezone, settings_json FROM companies"):
            rows = [{"timezone": "America/Bogota", "settings_json": {}}]
        elif "FROM hospitality_orders" in sql:
            rows = [order(local("2026-09-24", 13), [item(POLLO, 1, 40000)])]
        elif "FROM inventory_items" in sql:
            rows = [{"id": k, **v, "sale_price": 0, "status": "active"} for k, v in INVENTORY.items()]
        elif sql.startswith("SELECT to_regclass"):
            rows = [{"exists": False}]
        elif "FROM hospitality_day_closures" in sql or "FROM mini_panel_work_sessions" in sql:
            rows = []
        else:
            raise AssertionError(f"SQL no esperado: {sql[:120]}")
        return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows, first=lambda: rows[0] if rows else None),
                               fetchall=lambda: [SimpleNamespace(_mapping=r) for r in rows])


client = TestClient(app_main.app)


@pytest.fixture
def api(monkeypatch):
    async def get_user(_db, token):
        user = USERS.get(token)
        if not user:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Token requerido.")
        return user

    async def fake_db():
        yield Db()

    monkeypatch.setattr(deps, "get_current_company_user", get_user)
    monkeypatch.setattr(endpoint, "active_admin_v2_session", AsyncMock(return_value=False))
    monkeypatch.setattr(app_main, "_clonexa_access_policy_for_company", AsyncMock(return_value=None))
    monkeypatch.setattr(app_main, "_clonexa_company_is_archived", AsyncMock(return_value=False))
    monkeypatch.setattr(app_main, "_clonexa_auth_audit_enabled", lambda: False)
    app_main.app.dependency_overrides[get_db] = fake_db
    yield
    app_main.app.dependency_overrides.pop(get_db, None)


def get(company, part, token=None, query="period=custom&start=2026-09-20&end=2026-09-25"):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.get(f"/api/v1/hospitality/companies/{company}/owner-report/{part}?{query}", headers=headers)


@pytest.mark.parametrize("part", ["summary", "details", "pdf"])
def test_hospitality_owner_report_requires_owner_session_and_waiter_ordering(api, part):
    assert get(ASADERO, part).status_code == 401
    assert get(ASADERO, part, "administrador").status_code == 403
    other = get(ASADERO, part, "velvet")
    assert other.status_code == 403 and "tenant_not_allowed" in other.text
    no_module = get(VELVET, part, "velvet")
    assert no_module.status_code == 403 and "module_not_enabled_for_tenant" in no_module.text, "otra empresa: nada"
    assert get(ASADERO, part, "dueno").status_code == 200


def test_hospitality_owner_report_summary_and_details_payloads(api):
    summary = get(ASADERO, "summary", "dueno").json()
    assert {c["key"] for c in summary["kpis"]["cards"]} == {"sales", "accounts", "ticket", "margin", "cost_pct", "losses"}
    assert "_raw" not in summary["kpis"]
    details = get(ASADERO, "details", "dueno").json()
    assert set(details) >= {"daily", "heatmap", "menu", "team", "kitchen", "operations", "inventory"}
    too_long = get(ASADERO, "summary", "dueno", "period=custom&start=2026-01-01&end=2026-09-25")
    assert too_long.status_code == 400 and "93 días" in too_long.text


def test_hospitality_owner_report_menu_counts_each_portion_sold_for_popularity():
    """12 cuartos de pollo son 12 platos vendidos (3 pollos): el pollo es popular."""
    day = local("2026-09-10", 13)
    orders = [order(day, [item(POLLO, 0.25, 12000, label="1/4")]) for _ in range(12)]
    orders += [order(day, [item(GASEOSA, 1, 3000)]) for _ in range(4)]
    orders += [order(day, [item(SOPA, 1, 30000)]) for _ in range(1)]
    menu = report(orders).menu()
    pollo = next(p for p in menu["products"] if p["name"] == "POLLO Asado")
    assert pollo["units_text"] == "3" and pollo["sold"] == 12 and pollo["portions_text"] == "12 de 1/4"
    assert pollo["margin_unit"] == 12000 - 5000, "margen por cuarto vendido"
    assert pollo["quadrant"] in {"estrella", "vaca"}, "popular por las porciones vendidas"
