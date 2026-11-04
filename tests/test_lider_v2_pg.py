"""Lider de operacion v2 contra Postgres REAL (pgserver), con rutas y guardia reales: PIN en Workforce,
Marcar con PIN (misma funcion del bot, origen panel_pin), el lider finaliza turnos y los dos PDF."""
from __future__ import annotations

import asyncio
import importlib.util
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI

pgserver = pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.schema import CreateColumn  # noqa: E402

import app.main as app_main  # noqa: E402
from app.api.deps import get_db  # noqa: E402
from app.api.v1.endpoints import bots  # noqa: E402
from app.api.v1.endpoints import company_users as cu  # noqa: E402
from app.api.v1.router import api_router  # noqa: E402
from app.models.auth import CompanyUser  # noqa: E402
from app.models.core import Employee  # noqa: E402
from app.models.workforce_attendance import WorkforceAttendanceEvent, WorkforceAttendanceStatus  # noqa: E402
from app.services import auth_service, bot_punch_gps, ddl_once, lider_pdf, lider_pin, us_payroll  # noqa: E402
from tests.test_reports_v2 import pdf_text  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("reports_board_seed", ROOT / "tests" / "fixtures" / "reports_board_seed.py")
seedmod = importlib.util.module_from_spec(spec)
sys.modules["reports_board_seed"] = seedmod
spec.loader.exec_module(seedmod)
POINT = {"latitude": 32.3, "longitude": -86.3, "accuracy": 12.0}
UTC = timezone.utc
PEPPER = "clave-de-prueba-solo-para-estas-pruebas-0123456789"


@pytest.fixture(autouse=True)
def pepper(monkeypatch):
    monkeypatch.setenv("PIN_PEPPER", PEPPER)


def _statements(filename: str) -> list[str]:
    path = ROOT / "migrations" / "versions" / filename
    module_spec = importlib.util.spec_from_file_location(f"migration_{filename[:4]}", path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    out: list[str] = []
    module.op = SimpleNamespace(execute=lambda sql: out.append(str(sql)))
    module.upgrade()
    return out


@pytest.fixture(scope="module")
def pg_url():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="cx_pg_lv2_"), cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    def _add_missing(sync, model) -> None:
        """El escenario del Board trae tablas recortadas: se completan con las columnas del modelo."""
        have = {r[0] for r in sync.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"), {"t": model.__tablename__})}
        dialect = sync.dialect
        for column in model.__table__.columns:
            if column.name not in have:
                ddl = str(CreateColumn(column).compile(dialect=dialect)).replace(" NOT NULL", "")
                sync.execute(text(f"ALTER TABLE {model.__tablename__} ADD COLUMN {ddl}"))

    async def setup():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await seedmod.create_schema(conn)
            await conn.run_sync(lambda sync: CompanyUser.__table__.create(sync))
            await conn.run_sync(lambda sync: WorkforceAttendanceStatus.__table__.create(sync))
            await conn.run_sync(_add_missing, WorkforceAttendanceEvent)
            await conn.run_sync(_add_missing, Employee)
            for stmt in [s for s in _statements("024y_open_shift_alert.py") if "shift_manual_closes" in s] + _statements("025c_lider_v2.py"):
                await conn.execute(text(stmt))
        await engine.dispose()

    asyncio.run(setup())
    yield url


@pytest.fixture()
async def maker(pg_url):
    engine = create_async_engine(pg_url)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture()
async def world(maker, monkeypatch):
    import app.web.admin_v2_routes as admin_routes

    admin = SimpleNamespace(on=False)
    monkeypatch.setattr(admin_routes, "_active_session", AsyncMock(side_effect=lambda *_: admin.on))
    monkeypatch.setattr(cu, "active_admin_v2_session", AsyncMock(side_effect=lambda *_: admin.on))
    monkeypatch.setattr(cu, "_cx_company_or_404_019d", AsyncMock(side_effect=lambda _db, cid: SimpleNamespace(id=cid, name="VOLTAGE")))
    monkeypatch.setattr(lider_pdf, "company_logo", AsyncMock(return_value=None))
    sent: list[tuple] = []
    monkeypatch.setattr(bots, "_send_telegram_message", AsyncMock(side_effect=lambda token, chat, message, **_: sent.append((chat, message))))
    monkeypatch.setattr(bots, "_get_user_language", AsyncMock(side_effect=lambda _db, _cid, tg: "en" if tg == "777" else "es"))
    monkeypatch.setattr(bot_punch_gps, "bot_token", AsyncMock(return_value="tok"))
    ddl_once._READY.clear()  # cada modulo de pruebas tiene su propia base: lo verificado aqui no vale alla

    async with maker() as db:
        ids = await seedmod.seed(db)
        cid = ids["company"]
        ids["alma"] = await seedmod.person(db, cid, "Alma Ruiz", "AL-900", ids["al"], role="Supervisor", email="alma@voltage.test")
        ids["noa"] = await seedmod.person(db, cid, "Noa Prado", "AL-901", ids["al"])
        ids["zoe"] = await seedmod.person(db, cid, "Zoe Mar", "AL-902", ids["al"])
        ids["vera"] = await seedmod.person(db, cid, "Vera Sol", "VA-901", ids["va"])
        await db.execute(text("UPDATE employees SET telegram_user_id = '777' WHERE id = CAST(:e AS uuid)"), {"e": ids["zoe"]})
        await db.execute(text("INSERT INTO workforce_session_policy (company_id, alert_after_hours) VALUES (CAST(:c AS uuid), 15)"), {"c": cid})
        await db.commit()

    async def override():
        async with maker() as session:
            real_execute = session.execute

            async def quiet(stmt, *args, **kwargs):
                if "CREATE EXTENSION" in str(stmt):
                    return None
                return await real_execute(stmt, *args, **kwargs)

            session.execute = quiet
            yield session

    app = FastAPI()
    app.middleware("http")(app_main._clonexa_leader_guard)
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        w = SimpleNamespace(ids=ids, cid=cid, client=client, admin=admin, maker=maker, sent=sent)
        w.auth = await _leader(w)
        yield w
    ddl_once._READY.clear()


async def _leader(w, place="al", employee="alma", username="alma.lider", lugar="alabama") -> dict:
    w.admin.on = True
    made = await w.client.post(f"/api/v1/lider-operacion/consola/companies/{w.cid}/lideres",
                               json={"work_location_id": w.ids[place], "employee_id": w.ids[employee], "username": username, "password": "clave-segura-1"})
    w.admin.on = False
    assert made.status_code == 200, made.text
    res = await w.client.post(f"/api/v1/companies/{w.cid}/mini-panel-login", json={"username": username, "password": "clave-segura-1", "panel_type": "lider_operacion", "lugar": lugar})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _panel(w, tail: str) -> str:
    return f"/api/v1/lider-operacion/companies/{w.cid}/{tail}"


def _pins(w, tail: str) -> str:
    return f"/api/v1/lider-operacion/workforce/companies/{w.cid}/{tail}"


async def _new_pin(w, who: str) -> str:
    w.admin.on = True
    res = await w.client.post(_pins(w, f"employees/{w.ids[who]}/pin"))
    w.admin.on = False
    assert res.status_code == 200, res.text
    return res.json()["pin"]


async def _punch(w, pin: str, action: str, *, auth=None, summary=None, where=POINT):
    return await w.client.post(_panel(w, "pin/marcar"), headers=auth or w.auth, json={"pin": pin, "action": action, "summary": summary, **(where or {})})


async def _rows(w, sql: str, **params) -> list[dict]:
    async with w.maker() as db:
        return [dict(r) for r in (await db.execute(text(sql), {"c": w.cid, **params})).mappings().all()]


async def _events(w, who: str, channel: str | None = None) -> list[dict]:
    extra = "AND source_channel = :ch" if channel else ""
    return await _rows(w, f"""SELECT event_type, source, source_channel, detail, latitude, longitude, occurred_at, payload_json, source_ref FROM workforce_attendance_events
                              WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid) AND event_type <> 'gps_location' {extra} ORDER BY occurred_at""",
                       e=w.ids[who], ch=channel)


async def _open_since(w, who: str, hours: float, status: str = "working") -> None:
    """Un turno abierto hace `hours` horas, con evento y estado como lo deja el bot."""
    at = datetime.now(UTC) - timedelta(hours=hours)
    async with w.maker() as db:
        await seedmod.ev(db, w.cid, w.ids[who], "check_in", at, point=seedmod.VA_POINT)
        if status == "on_break":
            await seedmod.ev(db, w.cid, w.ids[who], "break_start", at + timedelta(minutes=5), point=seedmod.VA_POINT)
        await db.execute(text("""INSERT INTO workforce_attendance_status (company_id, employee_id, status, last_event_type, last_event_at, check_in_at, updated_at)
                                 VALUES (CAST(:c AS uuid), CAST(:e AS uuid), :s, 'check_in', :at, :at, :at)"""), {"c": w.cid, "e": w.ids[who], "s": status, "at": at})
        await db.commit()


# ------------------------------------------------------------------ Workforce
@pytest.mark.asyncio
async def test_generar_se_ve_una_vez_con_hash_y_auditoria(world):
    w = world
    assert (await w.client.get(_pins(w, "pins"))).status_code == 401, "sin sesion"
    assert (await w.client.post(_pins(w, f"employees/{w.ids['noa']}/pin"))).status_code == 401
    assert (await w.client.get(_pins(w, "pins"), headers=w.auth)).status_code == 403, "el lider no los ve"
    assert (await w.client.post(_pins(w, f"employees/{w.ids['noa']}/pin"), headers=w.auth)).status_code == 403, "ni los genera"
    assert (await w.client.delete(_pins(w, f"employees/{w.ids['noa']}/pin"), headers=w.auth)).status_code == 403

    pin = await _new_pin(w, "noa")
    assert re.fullmatch(r"[0-9]{4}", pin) and not lider_pin.weak(pin)
    stored = await _rows(w, "SELECT pin_hash, created_by FROM employee_punch_pins WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid)", e=w.ids["noa"])
    assert len(stored) == 1 and stored[0]["pin_hash"] == lider_pin.pin_hash(w.cid, pin) and pin not in stored[0]["pin_hash"] and len(stored[0]["pin_hash"]) == 64

    w.admin.on = True
    listing = await w.client.get(_pins(w, "pins"))
    w.admin.on = False
    assert listing.status_code == 200 and listing.json()["employees"][w.ids["noa"]] == {"has_pin": True, "has_telegram": False}
    assert listing.json()["employees"][w.ids["zoe"]] == {"has_pin": False, "has_telegram": True}
    assert pin not in listing.text and stored[0]["pin_hash"] not in listing.text, "nunca vuelve a salir"

    w.admin.on = True
    assert (await w.client.delete(_pins(w, f"employees/{w.ids['noa']}/pin"))).json()["removed"] is True
    assert (await w.client.delete(_pins(w, f"employees/{w.ids['noa']}/pin"))).json()["removed"] is False
    w.admin.on = False
    audit = await _rows(w, "SELECT action, actor FROM employee_punch_pin_audit WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid) ORDER BY at", e=w.ids["noa"])
    assert [a["action"] for a in audit] == ["generated", "removed"] and all(a["actor"] == "Admin V2" for a in audit)
    res = await w.client.post(_panel(w, "pin/verificar"), headers=w.auth, json={"pin": pin})
    assert res.status_code == 422, "el PIN quitado ya no sirve"


@pytest.mark.asyncio
async def test_unico_por_empresa_aunque_salga_repetido(world, monkeypatch):
    w = world
    sequence = iter([4827, 4827, 3961])
    monkeypatch.setattr(lider_pin.secrets, "randbelow", lambda _n: next(sequence))
    assert await _new_pin(w, "noa") == "4827"
    assert await _new_pin(w, "zoe") == "3961", "4827 ya es de otra persona"
    rows = await _rows(w, "SELECT pin_hash FROM employee_punch_pins WHERE company_id = CAST(:c AS uuid)")
    assert len({r["pin_hash"] for r in rows}) == 2
    with pytest.raises(Exception):  # la base misma lo impide
        async with w.maker() as db:
            await db.execute(text("UPDATE employee_punch_pins SET pin_hash = :h WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid)"),
                             {"h": lider_pin.pin_hash(w.cid, "4827"), "c": w.cid, "e": w.ids["zoe"]})


@pytest.mark.asyncio
async def test_generar_exige_lugar_y_persona_de_la_empresa(world):
    w = world
    w.admin.on = True
    assert (await w.client.post(_pins(w, f"employees/{w.ids['jaime']}/pin"))).status_code == 422, "sin lugar de trabajo"
    assert (await w.client.post(_pins(w, f"employees/{w.ids['company']}/pin"))).status_code == 404
    w.admin.on = False


def test_el_hash_usa_pin_pepper_y_no_el_secreto_jwt(monkeypatch):
    first = lider_pin.pin_hash("a", "4827")
    monkeypatch.setattr(auth_service, "get_jwt_secret", lambda: "otro-secreto-jwt")
    monkeypatch.setenv("SECRET_KEY", "otro-secreto-jwt")
    monkeypatch.setenv("JWT_SECRET_KEY", "otro-secreto-jwt")
    assert lider_pin.pin_hash("a", "4827") == first, "rotar el JWT no invalida los PIN"
    source = (ROOT / "app" / "services" / "lider_pin.py").read_text(encoding="utf-8")
    assert "get_jwt_secret" not in source and "auth_service" not in source
    monkeypatch.setenv("PIN_PEPPER", PEPPER + "-otra")
    assert lider_pin.pin_hash("a", "4827") != first


@pytest.mark.parametrize("value", [None, "", "corta"])
def test_sin_pin_pepper_no_hay_respaldo(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("PIN_PEPPER")
    else:
        monkeypatch.setenv("PIN_PEPPER", value)
    with pytest.raises(lider_pin.Denied) as e:
        lider_pin.pin_hash("a", "4827")
    assert e.value.status == 503


@pytest.mark.asyncio
async def test_sin_pin_pepper_ni_genera_ni_marca_ni_cuenta_fallos(world, monkeypatch):
    w = world
    pin = await _new_pin(w, "noa")
    monkeypatch.delenv("PIN_PEPPER")
    w.admin.on = True
    assert (await w.client.post(_pins(w, f"employees/{w.ids['zoe']}/pin"))).status_code == 503
    w.admin.on = False
    res = await w.client.post(_panel(w, "pin/verificar"), headers=w.auth, json={"pin": pin})
    assert res.status_code == 503 and pin not in res.text
    assert (await _punch(w, pin, "start")).status_code == 503
    assert await _events(w, "noa") == []
    assert await _rows(w, "SELECT 1 FROM lider_pin_attempts WHERE company_id = CAST(:c AS uuid)") == [], "la falta de clave no bloquea a nadie"
    assert await _rows(w, "SELECT 1 FROM employee_punch_pins WHERE employee_id = CAST(:e AS uuid)", e=w.ids["zoe"]) == []
    monkeypatch.setenv("PIN_PEPPER", PEPPER)
    assert (await w.client.post(_panel(w, "pin/verificar"), headers=w.auth, json={"pin": pin})).status_code == 200


def test_el_hash_depende_de_la_empresa_y_la_clave():
    assert lider_pin.pin_hash("a", "4827") != lider_pin.pin_hash("b", "4827")
    assert lider_pin.pin_hash("A", "4827") == lider_pin.pin_hash("a", "4827")
    for pin in ("0000", "7777", "1234", "6789", "4321", "9876"):
        assert lider_pin.weak(pin), pin
    for pin in ("4827", "1357"):
        assert not lider_pin.weak(pin), pin
    for bad in ("123", "12345", "12a4", "", None, 1234):
        assert not lider_pin.well_formed(bad)


# ------------------------------------------------------------------ PIN en el panel
@pytest.mark.asyncio
async def test_pin_correcto_incorrecto_y_de_otra_operacion(world):
    w = world
    pin = await _new_pin(w, "noa")
    other = await _new_pin(w, "vera")
    ok = await w.client.post(_panel(w, "pin/verificar"), headers=w.auth, json={"pin": pin})
    assert ok.status_code == 200, ok.text
    assert ok.json()["employee"] == {"name": "Noa Prado", "role": "operario", "state": "no_shift", "actions": ["start"]}
    wrong = "0000" if pin != "0000" else "1111"
    bad = await w.client.post(_panel(w, "pin/verificar"), headers=w.auth, json={"pin": wrong})
    assert bad.status_code == 422 and bad.json()["detail"] == "PIN incorrecto. Intentos restantes: 4."
    away = await w.client.post(_panel(w, "pin/verificar"), headers=w.auth, json={"pin": other})
    assert away.status_code == 422 and away.json()["detail"] == "Este PIN no es de Alabama"
    assert "Vera" not in away.text, "no dice de quien es"
    # Nadie marca con un PIN de otra operacion.
    assert (await _punch(w, other, "start")).status_code == 422
    assert await _events(w, "vera") == []
    # Inactivo: su PIN deja de servir.
    async with w.maker() as db:
        await db.execute(text("UPDATE employees SET status = 'inactive' WHERE id = CAST(:e AS uuid)"), {"e": w.ids["noa"]})
        await db.commit()
    assert (await w.client.post(_panel(w, "pin/verificar"), headers=w.auth, json={"pin": pin})).status_code == 422


@pytest.mark.asyncio
async def test_bloqueo_5_intentos_15_minutos_por_lider_y_operacion(world):
    w = world
    pin = await _new_pin(w, "noa")
    other = await _new_pin(w, "vera")
    used = {pin, other}
    wrong = [p for p in ("1357", "2468", "3579", "4680", "5791") if p not in used][:4]
    wrong += [other]  # el PIN de otra operacion tambien cuenta: si no, se podrian adivinar sin limite
    for attempt, guess in enumerate(wrong, 1):
        res = await w.client.post(_panel(w, "pin/verificar"), headers=w.auth, json={"pin": guess})
        if attempt < 5:
            assert res.status_code == 422, f"intento {attempt}: {res.text}"
        else:
            assert res.status_code == 423 and res.json()["detail"] == "Demasiados intentos. Este equipo queda bloqueado 15 min."
    # Bloqueado: ni el PIN correcto entra ni se puede marcar.
    assert (await w.client.post(_panel(w, "pin/verificar"), headers=w.auth, json={"pin": pin})).status_code == 423
    assert (await _punch(w, pin, "start")).status_code == 423
    assert await _events(w, "noa") == []
    # Otra operacion y otro lider no quedan bloqueados.
    sofia = await _leader(w, "va", "sofia", "sofia.lider", "virginia")
    assert (await w.client.post(_panel(w, "pin/verificar"), headers=sofia, json={"pin": other})).status_code == 200
    # Pasados los 15 minutos vuelve a contar desde cero.
    async with w.maker() as db:
        await db.execute(text("UPDATE lider_pin_attempts SET locked_until = now() - interval '1 minute', first_failure_at = now() - interval '16 minutes' WHERE company_id = CAST(:c AS uuid)"), {"c": w.cid})
        await db.commit()
    assert (await w.client.post(_panel(w, "pin/verificar"), headers=w.auth, json={"pin": pin})).status_code == 200
    again = await w.client.post(_panel(w, "pin/verificar"), headers=w.auth, json={"pin": wrong[0]})
    assert again.json()["detail"] == "PIN incorrecto. Intentos restantes: 4."


@pytest.mark.asyncio
async def test_un_acierto_no_borra_los_fallos(world):
    w = world
    pin = await _new_pin(w, "noa")
    wrong = [p for p in ("1357", "2468", "3579", "4680", "5791") if p != pin]
    for guess in wrong[:4]:
        assert (await w.client.post(_panel(w, "pin/verificar"), headers=w.auth, json={"pin": guess})).status_code == 422
    assert (await w.client.post(_panel(w, "pin/verificar"), headers=w.auth, json={"pin": pin})).status_code == 200
    assert (await w.client.post(_panel(w, "pin/verificar"), headers=w.auth, json={"pin": wrong[0]})).status_code == 423


@pytest.mark.asyncio
@pytest.mark.parametrize("where", [None, {"latitude": None, "longitude": None}, {"latitude": 95, "longitude": -86}, {"latitude": 0, "longitude": 0}])
async def test_sin_ubicacion_no_marca(world, where):
    w = world
    pin = await _new_pin(w, "noa")
    res = await _punch(w, pin, "start", where=where)
    assert res.status_code == 422 and res.json()["detail"] == "Activa la ubicación de este equipo"
    assert await _events(w, "noa") == []
    assert await _rows(w, "SELECT 1 FROM workforce_attendance_status WHERE employee_id = CAST(:e AS uuid)", e=w.ids["noa"]) == []


@pytest.mark.asyncio
async def test_marcar_con_pin_todo_el_turno_y_se_ve_en_crm_reportes_y_nomina(world):
    w = world
    pin = await _new_pin(w, "noa")
    before = datetime.now(UTC)
    res = await _punch(w, pin, "start")
    assert res.status_code == 200, res.text
    assert res.json()["name"] == "Noa Prado" and re.fullmatch(r"\d\d:\d\d C[SD]?T", res.json()["at"])

    async def actions():
        return (await w.client.post(_panel(w, "pin/verificar"), headers=w.auth, json={"pin": pin})).json()["employee"]

    assert await actions() == {"name": "Noa Prado", "role": "operario", "state": "working", "actions": ["pause", "end"]}
    # Las mismas reglas del bot: no se inicia dos veces ni se retoma sin pausa.
    assert (await _punch(w, pin, "start")).status_code == 409
    assert (await _punch(w, pin, "resume")).status_code == 409
    assert (await _punch(w, pin, "pause")).status_code == 200
    assert (await actions())["state"] == "on_break" and (await actions())["actions"] == ["resume", "end"]
    assert (await _punch(w, pin, "resume")).status_code == 200

    missing = await _punch(w, pin, "end", summary="   ")
    assert missing.status_code == 422 and missing.json()["detail"] == "Escribe el resumen de la jornada."
    done = await _punch(w, pin, "end", summary="Rack 4 terminado")
    assert done.status_code == 200, done.text
    for word in ("$", "USD", "Ordinarias", "projected", "pay", "Regular"):
        assert word not in done.text, "el equipo del lider no ve pagos"

    events = await _events(w, "noa")
    assert [e["event_type"] for e in events] == ["check_in", "break_start", "break_end", "check_out"]
    for event in events:
        assert event["source"] == "panel_pin" and event["source_channel"] == "panel_pin" and event["source_ref"].startswith("panel_pin:")
        assert float(event["latitude"]) == POINT["latitude"] and float(event["longitude"]) == POINT["longitude"]
        assert before - timedelta(seconds=5) <= event["occurred_at"] <= datetime.now(UTC) + timedelta(seconds=5), "hora del servidor"
        assert event["payload_json"]["panel_leader"] == "Alma Ruiz" and event["payload_json"]["punch_location"]["device"] == "leader"
    assert events[-1]["detail"] == "Rack 4 terminado"
    status = (await _rows(w, "SELECT status, check_out_at FROM workforce_attendance_status WHERE employee_id = CAST(:e AS uuid)", e=w.ids["noa"]))[0]
    assert status["status"] == "checked_out" and status["check_out_at"]
    gps = await _rows(w, "SELECT source_channel FROM workforce_attendance_events WHERE employee_id = CAST(:e AS uuid) AND event_type = 'gps_location'", e=w.ids["noa"])
    assert len(gps) == 4 and {g["source_channel"] for g in gps} == {"panel_pin"}, "el CRM del portal ve su ubicacion"

    # La prueba corre en segundos y un turno de 0 minutos no cuenta: se abre el turno hacia atras.
    async with w.maker() as db:
        for kind, back in (("check_in", "3 hours"), ("break_start", "2 hours"), ("break_end", "90 minutes")):
            await db.execute(text(f"UPDATE workforce_attendance_events SET occurred_at = occurred_at - interval '{back}' WHERE employee_id = CAST(:e AS uuid) AND event_type = :k"), {"e": w.ids["noa"], "k": kind})
        await db.commit()

    crm = (await w.client.get(_panel(w, "crm"), headers=w.auth)).json()
    noa = next(p for p in crm["people"] if p["name"] == "Noa Prado")
    assert noa["origin"] == "pin" and noa["last_mark"]["o"] == "pin" and noa["last_mark"]["k"] == "out" and noa["can_finish"] is False

    day = datetime.now(UTC).date()
    rep = (await w.client.get(_panel(w, "reportes"), params={"start": (day - timedelta(days=1)).isoformat(), "end": (day + timedelta(days=1)).isoformat()}, headers=w.auth)).json()
    person = next(p for p in rep["operations"][0]["people"] if p["name"] == "Noa Prado")
    shift = person["days"][0]["shifts"][0]
    assert shift["in"]["o"] == "pin" and shift["out"]["o"] == "pin" and shift["pauses"][0]["start"]["o"] == "pin"
    assert [n["text"] for n in rep["operations"][0]["notes"] if n["employee"] == "Noa Prado"] == ["Rack 4 terminado"]

    async with w.maker() as db:
        snap = await us_payroll.snapshot(db, w.cid, day - timedelta(days=1), day + timedelta(days=1), employee_id=w.ids["noa"])
    view = snap["rows"][0]["shifts"][0]["us"]
    assert view["check_in"]["origin"] == "pin" and view["check_out"]["origin"] == "pin", "Nomina"
    assert not view["manual_close"]


@pytest.mark.asyncio
async def test_crm_y_board_no_se_caen_si_alguien_marco_en_este_mismo_minuto(world):
    w = world
    pin = await _new_pin(w, "noa")
    assert (await _punch(w, pin, "start")).status_code == 200
    crm = await w.client.get(_panel(w, "crm"), headers=w.auth)
    assert crm.status_code == 200, crm.text
    noa = next(p for p in crm.json()["people"] if p["name"] == "Noa Prado")
    assert noa["state"] == "working" and noa["minutes"] == 0 and noa["can_finish"] is True
    assert (await w.client.get(_panel(w, "inicio"), headers=w.auth)).status_code == 200
    assert (await w.client.get(_panel(w, "reportes"), params={"part": "live"}, headers=w.auth)).status_code == 200
    # Pausa en el mismo minuto tambien.
    assert (await _punch(w, pin, "pause")).status_code == 200
    crm = await w.client.get(_panel(w, "crm"), headers=w.auth)
    assert next(p for p in crm.json()["people"] if p["name"] == "Noa Prado")["state"] == "on_break"


@pytest.mark.asyncio
async def test_pin_de_turno_del_bot_y_pendiente_limpiado(world):
    """Quien empezo por el bot puede terminar con PIN; lo que dejo a medias en el bot no vuelve a cerrar."""
    w = world
    await _open_since(w, "zoe", 2)
    pin = await _new_pin(w, "zoe")
    async with w.maker() as db:
        real_execute = db.execute

        async def quiet(stmt, *args, **kwargs):  # pgserver no trae pgcrypto
            return None if "CREATE EXTENSION" in str(stmt) else await real_execute(stmt, *args, **kwargs)

        db.execute = quiet
        await bots.ensure_bot_storage(db)
        await db.execute(text("""INSERT INTO company_telegram_pending_actions (company_id, telegram_user_id, employee_id, action, payload_json, updated_at)
                                 VALUES (CAST(:c AS uuid), '777', CAST(:e AS uuid), 'end_shift_summary', '{}'::jsonb, now())"""), {"c": w.cid, "e": w.ids["zoe"]})
        await db.commit()
    assert (await _punch(w, pin, "end", summary="Cierre con PIN")).status_code == 200
    assert await _rows(w, "SELECT 1 FROM company_telegram_pending_actions WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid)", e=w.ids["zoe"]) == []


# ------------------------------------------------------------------ el lider finaliza
@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["working", "on_break"])
async def test_lider_finaliza_ahora_con_auditoria_y_aviso(world, status):
    w = world
    await _open_since(w, "zoe", 3, status)
    crm = (await w.client.get(_panel(w, "crm"), headers=w.auth)).json()
    zoe = next(p for p in crm["people"] if p["name"] == "Zoe Mar")
    assert zoe["state"] == status and zoe["can_finish"] is True and zoe["since"]

    before = datetime.now(UTC)
    # Cualquier hora que mande el navegador se ignora: no existe ese campo.
    res = await w.client.post(_panel(w, f"crm/{w.ids['zoe']}/finalizar"), headers=w.auth, json={**POINT, "end_at": "2020-01-01T00:00:00Z", "occurred_at": "2020-01-01T00:00:00Z"})
    assert res.status_code == 200, res.text
    assert res.json()["name"] == "Zoe Mar" and res.json()["original_status"] == status and res.json()["notified"] is True

    out = (await _events(w, "zoe", "cerrado_por_lider"))
    assert len(out) == 1 and out[0]["event_type"] == "check_out" and out[0]["source"] == "cerrado_por_lider"
    assert before - timedelta(seconds=5) <= out[0]["occurred_at"] <= datetime.now(UTC) + timedelta(seconds=5), "hora = ahora"
    assert float(out[0]["latitude"]) == POINT["latitude"] and out[0]["payload_json"]["closed_by"] == "Alma Ruiz" and out[0]["payload_json"]["closed_by_leader"] is True
    state = (await _rows(w, "SELECT status, break_started_at, check_out_at FROM workforce_attendance_status WHERE employee_id = CAST(:e AS uuid)", e=w.ids["zoe"]))[0]
    assert state["status"] == "checked_out" and state["break_started_at"] is None
    audit = await _rows(w, "SELECT closed_by, closed_by_user_id, original_status, end_at, attendance_event_id FROM shift_manual_closes WHERE company_id = CAST(:c AS uuid) AND employee_id = CAST(:e AS uuid)", e=w.ids["zoe"])
    assert len(audit) == 1 and audit[0]["closed_by"] == "Alma Ruiz" and audit[0]["closed_by_user_id"] and audit[0]["original_status"] == status and audit[0]["attendance_event_id"]
    assert len(w.sent) == 1 and w.sent[0][0] == "777"
    assert re.fullmatch(r"Your shift was ended by your lead at \d\d:\d\d C[SD]?T\.", w.sent[0][1]), "en su idioma"

    day = datetime.now(UTC).date()
    rep = (await w.client.get(_panel(w, "reportes"), params={"start": (day - timedelta(days=1)).isoformat(), "end": (day + timedelta(days=1)).isoformat()}, headers=w.auth)).json()
    person = next(p for p in rep["operations"][0]["people"] if p["name"] == "Zoe Mar")
    shift = next(s for d in person["days"] for s in d["shifts"])
    assert shift["out"]["o"] == "lider" and shift["manual"]["by"] == "Alma Ruiz" and shift["out"]["s"] is None, "la ubicacion del lider no es alerta de la persona"
    if status == "on_break":
        assert shift["pauses"][0]["auto"] is True and shift["pause"] > 170, "la pausa se cerro en el mismo momento"
    assert shift["state"] == "ok", "turno de menos del limite: suma en Nomina"

    again = await w.client.post(_panel(w, f"crm/{w.ids['zoe']}/finalizar"), headers=w.auth, json=POINT)
    assert again.status_code == 409 and "turno abierto" in again.json()["detail"]


@pytest.mark.asyncio
async def test_finalizar_en_espanol_y_sin_telegram(world):
    w = world
    await _open_since(w, "noa", 1)
    res = await w.client.post(_panel(w, f"crm/{w.ids['noa']}/finalizar"), headers=w.auth, json=POINT)
    assert res.status_code == 200 and res.json()["notified"] is False and w.sent == []
    await _open_since_again(w, "noa")
    async with w.maker() as db:
        await db.execute(text("UPDATE employees SET telegram_user_id = '555' WHERE id = CAST(:e AS uuid)"), {"e": w.ids["noa"]})
        await db.commit()
    assert (await w.client.post(_panel(w, f"crm/{w.ids['noa']}/finalizar"), headers=w.auth, json=POINT)).json()["notified"] is True
    assert re.fullmatch(r"Tu turno fue finalizado por tu líder a las \d\d:\d\d C[SD]?T\.", w.sent[0][1])


async def _open_since_again(w, who: str) -> None:
    at = datetime.now(UTC) - timedelta(minutes=30)
    async with w.maker() as db:
        await seedmod.ev(db, w.cid, w.ids[who], "check_in", at)
        await db.execute(text("UPDATE workforce_attendance_status SET status = 'working', check_in_at = :at WHERE employee_id = CAST(:e AS uuid)"), {"e": w.ids[who], "at": at})
        await db.commit()


@pytest.mark.asyncio
async def test_si_el_aviso_falla_el_turno_igual_queda_cerrado(world, monkeypatch):
    w = world
    await _open_since(w, "zoe", 1)
    monkeypatch.setattr(bots, "_send_telegram_message", AsyncMock(side_effect=RuntimeError("telegram caido")))
    res = await w.client.post(_panel(w, f"crm/{w.ids['zoe']}/finalizar"), headers=w.auth, json=POINT)
    assert res.status_code == 200 and res.json()["notified"] is False
    assert (await _rows(w, "SELECT status FROM workforce_attendance_status WHERE employee_id = CAST(:e AS uuid)", e=w.ids["zoe"]))[0]["status"] == "checked_out"


@pytest.mark.asyncio
async def test_finalizar_solo_su_operacion_menos_del_limite_y_con_ubicacion(world):
    w = world
    # Otra operacion
    await _open_since(w, "vera", 2)
    res = await w.client.post(_panel(w, f"crm/{w.ids['vera']}/finalizar"), headers=w.auth, json=POINT)
    assert res.status_code == 403 and res.json()["detail"] == "Esa persona no es de Alabama."
    assert (await _events(w, "vera", "cerrado_por_lider")) == []
    # Otra empresa: ni la encuentra
    assert (await w.client.post(f"/api/v1/lider-operacion/companies/{w.ids['va']}/crm/{w.ids['noa']}/finalizar", headers=w.auth, json=POINT)).status_code == 403
    # Sin ubicacion
    await _open_since(w, "noa", 2)
    res = await w.client.post(_panel(w, f"crm/{w.ids['noa']}/finalizar"), headers=w.auth, json={})
    assert res.status_code == 422 and res.json()["detail"] == "Activa la ubicación de este equipo"
    # Sin turno
    assert (await w.client.post(_panel(w, f"crm/{w.ids['alma']}/finalizar"), headers=w.auth, json=POINT)).status_code == 409
    # Mas de 15 h: por confirmar, no aparece el boton y el servidor tampoco deja
    await _open_since(w, "zoe", 16)
    crm = (await w.client.get(_panel(w, "crm"), headers=w.auth)).json()
    zoe = next(p for p in crm["people"] if p["name"] == "Zoe Mar")
    assert zoe["state"] == "to_confirm" and zoe["can_finish"] is False and crm["limit_hours"] == 15
    res = await w.client.post(_panel(w, f"crm/{w.ids['zoe']}/finalizar"), headers=w.auth, json=POINT)
    assert res.status_code == 409 and "supera 15 horas" in res.json()["detail"]
    assert (await _events(w, "zoe", "cerrado_por_lider")) == [] and w.sent == []


@pytest.mark.asyncio
@pytest.mark.parametrize("method,tail", [
    ("POST", "pin/generar"), ("POST", "crm/{e}/confirmar"), ("POST", "crm/{e}/finalizar/hora"), ("PUT", "crm/{e}/finalizar"), ("PATCH", "pin/marcar"), ("DELETE", "pin/marcar"),
    ("GET", "pin/marcar"), ("POST", "inicio"), ("POST", "reportes"),
])
async def test_cualquier_otra_escritura_es_403(world, method, tail):
    w = world
    res = await w.client.request(method, _panel(w, tail.format(e=w.ids["noa"])), headers=w.auth, json={} if method != "GET" else None)
    assert res.status_code == 403 and res.json()["detail"] == auth_service.LEADER_ONLY_DETAIL


@pytest.mark.asyncio
async def test_escrituras_de_horas_siguen_cerradas_para_el_lider(world):
    w = world
    cid = w.cid
    for method, path in [
        ("POST", f"/api/v1/open-shifts/companies/{cid}/close"),
        ("POST", f"/api/v1/employees/{w.ids['noa']}/attendance"),
        ("PATCH", f"/api/v1/employees/{w.ids['noa']}"),
        ("POST", f"/api/v1/payroll/companies/{cid}/closures"),
        ("POST", f"/api/v1/us-payroll/companies/{cid}/rates"),
    ]:
        res = await w.client.request(method, path, headers=w.auth, json={})
        assert res.status_code == 403, f"{method} {path}: {res.status_code}"


@pytest.mark.asyncio
async def test_interruptor_apagado_y_sin_sesion(world):
    w = world
    pin = await _new_pin(w, "noa")
    assert (await w.client.post(_panel(w, "pin/verificar"), json={"pin": pin})).status_code == 401
    assert (await w.client.post(_panel(w, "pin/marcar"), json={"pin": pin})).status_code == 401
    assert (await w.client.post(_panel(w, f"crm/{w.ids['noa']}/finalizar"), json=POINT)).status_code == 401
    assert (await w.client.get(_panel(w, "crm/lista.pdf"))).status_code == 401
    assert (await w.client.get(_panel(w, "reportes/export.pdf"))).status_code == 401
    async with w.maker() as db:
        await db.execute(text("""UPDATE company_modules SET settings = settings || '{"reports_board": false}'::jsonb
                                 WHERE company_id = CAST(:c AS uuid) AND module_id = (SELECT id FROM modules WHERE code = 'reports')"""), {"c": w.cid})
        await db.commit()
    assert (await w.client.post(_panel(w, "pin/verificar"), headers=w.auth, json={"pin": pin})).status_code == 404
    w.admin.on = True
    assert (await w.client.get(_pins(w, "pins"))).status_code == 404, "otras empresas no ven nada de PIN"
    w.admin.on = False


# ------------------------------------------------------------------ PDF
def _png() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (0, 46, 138)).save(buf, "PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_pdf_lista_de_asistencia(world, monkeypatch):
    w = world
    await _open_since(w, "zoe", 2)
    pin = await _new_pin(w, "noa")
    assert (await _punch(w, pin, "start")).status_code == 200
    monkeypatch.setattr(lider_pdf, "company_logo", AsyncMock(return_value=_png()))
    res = await w.client.get(_panel(w, "crm/lista.pdf"), headers=w.auth)
    assert res.status_code == 200 and res.headers["content-type"] == "application/pdf" and "no-store" in res.headers["cache-control"]
    pdf = res.content
    assert pdf.startswith(b"%PDF") and b"/MediaBox [ 0 0 612 792 ]" in pdf, "carta vertical"
    assert b"/Subtype /Image" in pdf, "membrete con el logo"
    words = pdf_text(pdf)
    for needle in ("Lista de asistencia · Alabama", "Conexión al momento", "Líder: Alma Ruiz", "Generado por Clonexa", "Trabajando", "Sin turno", "NOMBRE", "ROL", "ESTADO", "ORIGEN", "ENTRADA", "TIEMPO", "FIRMA",
                   "Noa Prado", "Zoe Mar", "PIN", "App", "VOLTAGE · Alabama · Lista de asistencia", "Página 1 de 1"):
        assert needle in words, needle
    for banned in ("Virginia", "Bruno", "Ángela", "$", "Tarifa", "Bruto", "Neto"):
        assert banned not in words, banned
    assert words.index("Alma Ruiz", words.index("NOMBRE")) < words.index("Elena Gómez") < words.index("Noa Prado") < words.index("Zoe Mar"), "A-Z"


def test_pdf_lista_colores_paginas_y_sin_logo():
    now = datetime(2026, 11, 5, 15, 22, tzinfo=UTC)
    people = [{"id": str(i), "name": f"Persona {i:03d} con un nombre bastante largo para partirse en dos líneas", "role": "Operario", "state": s, "origin": "pin" if i % 2 else "app", "since": "05:49", "minutes": 213}
              for i, s in zip(range(70), ["working", "on_break", "to_confirm", "no_shift"] * 18)]
    crm = {"operation": {"name": "Alabama", "timezone": "America/Chicago", "abbr": "CT"}, "counts": {"working": 18, "on_break": 18, "to_confirm": 17, "no_shift": 17}, "people": people}
    pdf = lider_pdf.build_attendance_pdf(crm, company="VOLTAGE", leader="Noel", logo=None, now=now, limit_hours=15, lang="es")
    words = pdf_text(pdf)
    assert "Página 1 de " in words and re.search(r"Página (\d+) de \1", words), "cuenta bien las paginas"
    assert words.count("NOMBRE") >= 2, "repite el encabezado de la tabla"
    assert "jueves 05 nov 2026 · 09:22 CT" in words, "hora local de la operacion"
    assert "+15 h" in words and "3 h 33" in words
    english = pdf_text(lider_pdf.build_attendance_pdf(crm, company="VOLTAGE", leader="Noel", logo=b"no-es-imagen", now=now, limit_hours=15, lang="en"))
    for needle in ("Attendance list · Alabama", "Working", "On break", "To confirm", "No shift", "SIGNATURE", "Page 1 of", "Lead: Noel", "Thursday 05 Nov 2026"):
        assert needle in english, needle


def test_pdf_logo_webp_transparente_del_estudio_de_marca():
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGBA", (16, 16), (0, 46, 138, 120)).save(buf, "WEBP")
    crm = {"operation": {"name": "Alabama", "timezone": "America/Chicago", "abbr": "CT"}, "counts": {}, "people": []}
    pdf = lider_pdf.build_attendance_pdf(crm, company="VOLTAGE", leader="Noel", logo=buf.getvalue(), now=datetime(2026, 11, 5, 15, 22, tzinfo=UTC), limit_hours=15)
    assert b"/Subtype /Image" in pdf


def test_notas_agrupadas_y_alertas():
    notes = [{"employee": "Bruno", "at": "2026-11-03T10:00", "text": "b2"}, {"employee": "Ángela", "at": "2026-11-03T10:00", "text": "a2"}, {"employee": "Ángela", "at": "2026-11-01T10:00", "text": "a1"}, {"employee": "Bruno", "at": "2026-11-02T10:00", "text": "b1"}]
    grouped = lider_pdf.notes_by_person(notes)
    assert [g[0] for g in grouped] == ["Ángela", "Bruno"]
    assert [n["text"] for n in grouped[0][1]] == ["a1", "a2"] and [n["text"] for n in grouped[1][1]] == ["b1", "b2"]
    t = lider_pdf.texts("es")
    base = {"employee": "Ana", "d": "2026-11-04", "t": "09:00", "a": "CT"}
    assert lider_pdf.alert_line({**base, "kind": "outside", "mark": "Entrada"}, t) == "Fuera de perímetro: Ana · mié 04 nov 09:00 CT (Entrada)"
    assert lider_pdf.alert_line({**base, "kind": "to_confirm", "minutes": 900, "open": True}, t) == "Turno abierto 15 h 00: Ana · mié 04 nov 09:00 CT"
    assert lider_pdf.alert_line({**base, "kind": "near_overtime", "minutes": 2200}, lider_pdf.texts("en")) == "Near overtime (36 h 40 this week): Ana · Wed 04 Nov 09:00 CT"
    assert lider_pdf.period_text("2026-11-01", "2026-11-07", t) == "dom 01 nov – sáb 07 nov 2026"
    assert lider_pdf.period_text("2026-11-01", "2026-11-01", t) == "dom 01 nov 2026"


@pytest.mark.asyncio
async def test_pdf_reporte_del_lider_ordenado_y_solo_su_operacion(world):
    w = world
    res = await w.client.get(_panel(w, "reportes/export.pdf"), params={"start": seedmod.START.isoformat(), "end": seedmod.END.isoformat()}, headers=w.auth)
    assert res.status_code == 200, res.text
    pdf = res.content
    assert b"/MediaBox [ 0 0 612 792 ]" in pdf
    words = pdf_text(pdf)
    order = ["Reporte · Alabama", "1 · Cifras del periodo", "2 · Personal (A-Z)", "3 · Notas de cierre (por persona y fecha)", "4 · Alertas del periodo"]
    positions = [words.index(o) for o in order]
    assert positions == sorted(positions), "el orden del reporte"
    for needle in ("Líder: Alma Ruiz", "Generado por Clonexa", "dom 01 nov – sáb 07 nov 2026 · hora CT", "PAGABLES", "OVERTIME", "Felipe Soto", "Turno largo en el rack 4", "Olvidó marcar la salida", "Página 1 de"):
        assert needle in words, needle
    for banned in ("Virginia", "Ángela", "Bruno", "$", "Tarifa", "Bruto", "Neto", "AL-100", "documento"):
        assert banned not in words, banned
    section = words[words.index("2 · Personal (A-Z)"):words.index("3 · Notas")]
    assert section.index("Elena Gómez") < section.index("Felipe Soto") < section.index("Helena Ríos") < section.index("Iván Mena"), "A-Z"
    english = await w.client.get(_panel(w, "reportes/export.pdf"), params={"start": seedmod.START.isoformat(), "end": seedmod.END.isoformat(), "lang": "en"}, headers=w.auth)
    assert "Report · Alabama" in pdf_text(english.content) and "2 · Staff (A-Z)" in pdf_text(english.content)
    assert (await w.client.get(_panel(w, "reportes/export.pdf"), params={"work_location_id": w.ids["va"]}, headers=w.auth)).status_code == 403
