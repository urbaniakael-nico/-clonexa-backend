"""Produccion v2 (interruptor production_v2): un solo calculo para pantalla y PDF.

- Seis cifras del equipo; "Sin datos aun" con su motivo cuando no hay datos.
- Lotes en proceso, cerradas vs enviadas por semana/mes, tiempo del equipo por
  referencia (participacion que suma 100 %) y alertas.
- Nunca nada por persona.
- Contra Postgres real: mismas tablas del bot y del CRM, solo esa empresa.
- Rutas: dueno/admin y el interruptor (404 apagado).
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.services import production_v2 as svc
from app.services.references_v2 import group_key
from tests.test_crm_lab_pg import company, employee, pg_url, reference, run  # noqa: F401  (fixture de Postgres real)

TODAY = date(2026, 10, 19)


def group(name, meta, produced, received=None, bot=True, lines=None):
    return {"key": group_key(name), "name": name, "meta": meta, "produced": produced, "pending": max(meta - produced, 0),
            "received": meta if received is None else received,
            "lines": lines or [{"size": "M", "meta": meta, "produced": produced, "pending": max(meta - produced, 0), "bot_active": bot, "reference_id": f"{name}-M",
                        "received": meta if received is None else received}]}


def base(**over):
    groups = over.pop("groups", [group("PANT SET", 30, 30), group("Choco-fresa", 58, 10)])
    args = dict(start=date(2026, 10, 13), end=TODAY, today=TODAY, groups=groups,
                key_by_id={f"{g['name']}-M": g["key"] for g in groups}, moves=[], closures=[], first_session={}, last_session={},
                team_seconds=0, time_by_ref=[], live={"working": 0, "paused": 0, "live": []}, labor_gross=None)
    args.update(over)
    return svc.build(**args)


def test_sin_datos_con_su_motivo():
    out = base()
    k = out["kpis"]
    assert k["workshop_now"]["status"] == "ok" and k["workshop_now"]["value"] == 0
    for key, reason in [("closed", "Aún no hay cierres registrados."), ("sent", "Aún no hay envíos a Bombón registrados en Referencias."),
                        ("days_per_lot", "Ningún lote se completó en el periodo."), ("team_hours_per_garment", "Sin prendas cerradas en el periodo."),
                        ("labor_per_garment", "Sin prendas cerradas en el periodo.")]:
        assert k[key] == {"status": "sin_datos", "value": None, "reason": reason}, key


def test_seis_cifras_del_equipo():
    pant, choco = "PANT SET-M", "Choco-fresa-M"
    out = base(
        moves=[{"reference_id": pant, "kind": "ingreso", "quantity": 30, "event_date": date(2026, 10, 1)},
               {"reference_id": pant, "kind": "despliegue", "quantity": 20, "event_date": date(2026, 10, 16)},
               {"reference_id": choco, "kind": "ingreso", "quantity": 58, "event_date": date(2026, 10, 14)}],
        closures=[{"key": group_key("PANT SET"), "quantity": 18, "day": date(2026, 10, 15)},
                  {"key": group_key("PANT SET"), "quantity": 12, "day": date(2026, 10, 2)},
                  {"key": group_key("Choco-fresa"), "quantity": 10, "day": date(2026, 10, 17)}],
        first_session={group_key("PANT SET"): date(2026, 9, 30)}, team_seconds=14 * 3600,
        time_by_ref=[{"key": group_key("PANT SET"), "name": "PANT SET", "seconds": 4 * 3600, "active": 0},
                     {"key": group_key("Choco-fresa"), "name": "Choco-fresa", "seconds": 10 * 3600, "active": 2}],
        live={"working": 2, "paused": 1, "live": [{"name": "Ana", "status": "working", "reference_name": "Choco-fresa", "elapsed_minutes": 30},
                                                  {"name": "Bea", "status": "working", "reference_name": "Choco-fresa", "elapsed_minutes": 5},
                                                  {"name": "Caro", "status": "on_break", "reference_name": None, "elapsed_minutes": 3}]},
        labor_gross=840000.0)
    k = out["kpis"]
    assert k["workshop_now"] == {"status": "ok", "value": 3, "working": 2, "paused": 1, "lots": 1}
    assert k["closed"] == {"status": "ok", "value": 28, "lots": 2}, "solo las del periodo"
    assert k["sent"] == {"status": "ok", "value": 20, "to_send": 10 + 10}, "PANT SET 30-20 y Choco-fresa 10-0"
    assert k["days_per_lot"] == {"status": "ok", "value": 16.0, "lots": 1}, "PANT SET: 30 sep (primera sesion) a 15 oct"
    assert k["team_hours_per_garment"]["value"] == 30.0, "14 h de equipo / 28 prendas = 30 min"
    assert k["labor_per_garment"]["value"] == 30000.0
    lots = out["lots_in_process"]
    assert [lot["name"] for lot in lots] == ["Choco-fresa"], "PANT SET ya está completo"
    assert lots[0]["working_now"] == 2 and lots[0]["team_seconds"] == 36000 and lots[0]["pending"] == 48
    share = out["team_time"]["by_reference"]
    assert [r["name"] for r in share] == ["Choco-fresa", "PANT SET"]
    assert round(sum(r["percent"] for r in share)) == 100
    assert out["series"] == [{"bucket": "2026-10-12", "closed": 28, "sent": 20}, {"bucket": "2026-10-19", "closed": 0, "sent": 0}]


def test_nada_por_persona():
    import json

    out = base(live={"working": 1, "paused": 0, "live": [{"name": "Ana", "status": "working", "reference_name": "PANT SET", "elapsed_minutes": 9}]},
               closures=[{"key": group_key("PANT SET"), "quantity": 5, "day": TODAY}], team_seconds=3600)
    raw = json.dumps(out, default=str).lower()
    for word in ("per_person", "por persona", "productiv", "employee_id", "operator", "per_unit", "per_garment_person"):
        assert word not in raw, word
    lot = out["lots_in_process"][0] if out["lots_in_process"] else {}
    for p in lot.get("people", []):
        assert set(p) == {"name", "seconds"}, "por persona solo horas (participacion), nunca prendas"
    assert set(out["live"][0]) == {"name", "status", "reference", "since", "elapsed_minutes"}, "en vivo: quién está y en qué, sin cifras por persona"


def test_alertas():
    """Las cuatro pedidas: lote lento (mas dias que el promedio y avance bajo), novedades
    abiertas por seccion, referencia activa sin tiempo hace 5+ dias y cerradas sin enviar."""
    ids = {"Hecho-M": group_key("Hecho"), "Lento-M": group_key("Lento"), "Quieto-M": group_key("Quieto")}
    out = base(groups=[group("Hecho", 10, 10), group("Lento", 40, 4), group("Quieto", 20, 5)], key_by_id=ids,
               moves=[{"reference_id": "Hecho-M", "kind": "ingreso", "quantity": 10, "event_date": TODAY - timedelta(days=12)},
                      {"reference_id": "Lento-M", "kind": "ingreso", "quantity": 40, "event_date": TODAY - timedelta(days=25)},
                      {"reference_id": "Lento-M", "kind": "novedad", "section": "bordado", "size": "M", "quantity": 2, "event_date": TODAY},
                      {"reference_id": "Quieto-M", "kind": "novedad", "section": "bordado", "size": "M", "quantity": 1, "event_date": TODAY},
                      {"reference_id": "Lento-M", "kind": "despliegue", "quantity": 1, "event_date": TODAY}],
               closures=[{"key": group_key("Hecho"), "quantity": 10, "day": TODAY - timedelta(days=3)},
                         {"key": group_key("Lento"), "quantity": 4, "day": TODAY - timedelta(days=1)}],
               last_session={group_key("Quieto"): TODAY - timedelta(days=6), group_key("Lento"): TODAY},
               live={"working": 1, "paused": 0, "live": [{"name": "Ana", "status": "working", "reference_name": "Lento", "elapsed_minutes": 13 * 60}]})
    kinds = {a["kind"]: a for a in out["alerts"]}
    assert kinds["long_session"]["reference"] == "Lento"
    assert kinds["slow_lot"]["reference"] == "Lento" and kinds["slow_lot"]["days"] == 26 and kinds["slow_lot"]["avg"] == 10.0
    assert kinds["open_news"] == {"kind": "open_news", "level": "warning", "reference": "Lento, Quieto", "section": "bordado", "quantity": 3}
    assert kinds["no_recent_time"]["reference"] == "Quieto" and kinds["no_recent_time"]["days"] == 6
    assert [a["reference"] for a in out["alerts"] if a["kind"] == "not_sent"] == ["Hecho", "Lento"]
    assert {a["kind"] for a in out["alerts"]} == {"long_session", "slow_lot", "open_news", "no_recent_time", "not_sent"}
    lento = next(lot for lot in out["lots_in_process"] if lot["name"] == "Lento")
    assert lento["late"] is True
    for a in out["alerts"]:
        assert svc.alert_text(a) and "{" not in svc.alert_text(a)


def test_detalle_del_lote_y_horas_del_equipo():
    out = base(groups=[group("Choco-fresa", 58, 10)], key_by_id={"Choco-fresa-M": group_key("Choco-fresa")},
               moves=[{"reference_id": "Choco-fresa-M", "kind": "ingreso", "size": "M", "quantity": 30, "event_date": date(2026, 10, 14)},
                      {"reference_id": "Choco-fresa-M", "kind": "ingreso", "size": "M", "quantity": 28, "event_date": date(2026, 10, 15)},
                      {"reference_id": "Choco-fresa-M", "kind": "novedad", "section": "taller", "size": "M", "quantity": 2, "event_date": date(2026, 10, 15)}],
               time_by_ref=[{"key": group_key("Choco-fresa"), "name": "Choco-fresa", "seconds": 5 * 3600, "active": 0}],
               time_by_person=[{"key": group_key("Choco-fresa"), "person": "Bea", "seconds": 3600},
                               {"key": group_key("Choco-fresa"), "person": "Ana", "seconds": 4 * 3600}])
    lot = out["lots_in_process"][0]
    assert lot["cuts"] == [{"date": "2026-10-14", "sizes": [{"size": "M", "quantity": 30}], "quantity": 30},
                           {"date": "2026-10-15", "sizes": [{"size": "M", "quantity": 28}], "quantity": 28}]
    assert lot["news"] == [{"section": "taller", "quantity": 2}]
    assert lot["team"] == ["Ana", "Bea"] and lot["people"][0] == {"name": "Ana", "seconds": 14400}
    assert lot["sizes"][0]["received"] == 58 and lot["sizes"][0]["pending"] == 48
    share = out["team_time"]["by_reference"][0]
    assert sum(p["seconds"] for p in share["people"]) == share["seconds"], "la barra apilada suma el tiempo del equipo"


def test_periodos():
    assert svc.period("week", TODAY) == (date(2026, 10, 19), TODAY)
    assert svc.period("month", TODAY) == (date(2026, 10, 1), TODAY)
    assert svc.period("quarter", TODAY) == (date(2026, 10, 1), TODAY)
    assert svc.period("quarter", date(2026, 8, 5)) == (date(2026, 7, 1), date(2026, 8, 5))
    assert svc.period("custom", TODAY, "2026-10-10", "2026-09-01") == (date(2026, 9, 1), date(2026, 10, 10))
    with pytest.raises(ValueError):
        svc.period("custom", TODAY, "2025-01-01", "2026-10-01")
    with pytest.raises(ValueError):
        svc.period("custom", TODAY, "x", "y")
    weeks, by_month = svc.buckets(date(2026, 9, 1), date(2026, 10, 19))
    assert not by_month and weeks[0] == date(2026, 8, 31)
    months, by_month = svc.buckets(date(2026, 1, 1), date(2026, 10, 19))
    assert by_month and len(months) == 10


def test_pdf_con_y_sin_datos():
    for out in (base(), base(closures=[{"key": group_key("PANT SET"), "quantity": 5, "day": TODAY}], team_seconds=3600, labor_gross=50000.0)):
        pdf = svc.build_pdf(out, {"name": "VELVET"})
        assert pdf.startswith(b"%PDF") and pdf.count(b"/Type /Page") >= 1 and len(pdf) > 2500


def test_tablero_contra_postgres_real(pg_url):  # noqa: F811
    from app.services import crm_lab

    async def go(db):
        from zoneinfo import ZoneInfo

        from app.services import company_locale

        company_locale.CURRENT_TZ.set(ZoneInfo("UTC"))  # pgserver no trae la base de zonas horarias
        cid = await company(db, "VelvetTablero")
        other = await company(db, "OtraTablero")
        ana = await employee(db, cid, "Ana")
        await employee(db, other, "Ajena")
        pant = await reference(db, cid, "PANT SET", cut=10)
        await reference(db, other, "PANT SET", cut=99)
        await crm_lab.act(db, cid, ana, "start_shift", {"reference_id": pant["M"]}, "CRM")
        await crm_lab.act(db, cid, ana, "close", {"size_reference_id": pant["M"], "quantity": 4}, "CRM")
        await db.execute(text("""INSERT INTO reference_cut_movements (company_id, reference_id, kind, size, quantity, event_date, created_by)
            VALUES (:c, :r, 'despliegue', 'M', 3, CURRENT_DATE, 'prueba')"""), {"c": cid, "r": pant["M"]})
        await db.commit()
        today = datetime.now(timezone.utc).date()
        out = await svc.insights(db, cid, today - timedelta(days=6), today, today)
        k = out["kpis"]
        assert k["workshop_now"]["value"] == 1 and k["workshop_now"]["lots"] == 1
        assert k["closed"]["value"] == 4 and k["sent"]["value"] == 3 and k["sent"]["to_send"] == 1
        lot = out["lots_in_process"][0]
        assert lot["name"] == "PANT SET" and lot["meta"] == 30 and lot["closed"] == 4 and lot["working_now"] == 1
        assert out["live"][0]["reference"] == "PANT SET"
        assert out["data_check"]["closures_total"] == 1, "solo esa empresa"

    run(pg_url, go)


# ---------------------------------------------------------------- rutas
@pytest.mark.asyncio
async def test_rutas_dueno_admin_e_interruptor(monkeypatch):
    import app.api.v1.endpoints.companies as companies
    from app.api.v1.endpoints import production_v2 as api

    cid = uuid.uuid4()
    req = SimpleNamespace(headers={}, cookies={}, client=None)
    monkeypatch.setattr(companies, "require_admin_v2_or_tenant_company_admin", AsyncMock(side_effect=HTTPException(status_code=403, detail="role_not_allowed")))
    with pytest.raises(HTTPException) as e:
        await api.owner(cid, req, "Bearer x", db=None)
    assert e.value.status_code == 403
    monkeypatch.setattr(companies, "require_admin_v2_or_tenant_company_admin", AsyncMock(return_value=None))
    monkeypatch.setattr(svc, "is_on", AsyncMock(return_value=False))
    with pytest.raises(HTTPException) as e:
        await api.owner(cid, req, "Bearer x", db=None)
    assert e.value.status_code == 404
    monkeypatch.setattr(svc, "is_on", AsyncMock(return_value=True))
    assert await api.owner(cid, req, "Bearer x", db=None) is None
    for r in api.router.routes:
        assert api.owner in [d.call for d in r.dependant.dependencies], f"{r.path} sin sesión"
