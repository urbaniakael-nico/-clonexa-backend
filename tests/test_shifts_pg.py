"""Turnos (modulo shifts) contra Postgres REAL (pgserver) con la migracion 024i.

- Armar (borrador determinista), rearmar reemplaza solo el borrador, publicar
  manda la semana por bot y una semana publicada no se rearma.
- Cambio de turno: aceptar (se aplica a la malla y avisa a los tres); rechazar
  -> siguiente; vencer (calculado desde la base) -> siguiente; lista agotada ->
  sin cubrir con alerta al supervisor; respuesta a mano registrada.
- Permisos en el servidor: operario y logistica 403; el director ve pero no crea
  cambios; el supervisor (tambien por mini panel ligado a Personal) si.
- Modulo apagado (otra empresa): 404 y nada de la otra empresa se ve.
- Bot: "Mis turnos" y los botones solo con el modulo activo; los menus de
  supervisor y almacenista quedan iguales.
"""
from __future__ import annotations

import asyncio
import importlib
import tempfile
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

pgserver = pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.api.v1.endpoints import bots  # noqa: E402
from app.api.v1.endpoints import shifts_v1 as api  # noqa: E402
from app.services import shifts as svc  # noqa: E402
from tests.test_brand_pg import BASE_SCHEMA  # noqa: E402

WEEK = date(2026, 10, 12)
EXTRA_SCHEMA = """
ALTER TABLE companies ADD COLUMN IF NOT EXISTS timezone text;
CREATE TABLE IF NOT EXISTS company_core_settings (company_id uuid PRIMARY KEY, currency text, timezone text, language text);
CREATE TABLE IF NOT EXISTS employees (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, full_name text, role text,
  employee_type text, status text DEFAULT 'active', telegram_user_id text);
CREATE TABLE IF NOT EXISTS workforce_attendance_events (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid, employee_id uuid,
  event_type text, occurred_at timestamptz);
CREATE TABLE IF NOT EXISTS company_telegram_user_preferences (company_id uuid, telegram_user_id text, language text)
"""


def _migration() -> list[str]:
    statements: list[str] = []

    class Op:
        def execute(self, sql):
            statements.append(str(sql))

    module = importlib.import_module("migrations.versions.024i_shifts_v1")
    module.op = Op()
    module.upgrade()
    assert len(module.revision) <= 32
    return statements


@pytest.fixture(scope="module")
def pg_url():
    folder = tempfile.mkdtemp(prefix="cx_pg_shifts_")
    server = pgserver.get_server(folder, cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            for stmt in [s for s in (BASE_SCHEMA + ";" + EXTRA_SCHEMA).split(";") if s.strip()]:
                await conn.execute(text(stmt))
            for stmt in _migration():
                await conn.execute(text(stmt))
            for stmt in _migration():  # idempotente
                await conn.execute(text(stmt))
        await engine.dispose()

    asyncio.run(setup())
    yield url


class Outbox:
    def __init__(self):
        self.sent: list[dict] = []

    async def __call__(self, token, chat_id, text_value, reply_markup=None):
        self.sent.append({"chat": chat_id, "text": text_value, "markup": reply_markup})

    def to(self, chat):
        return [m for m in self.sent if m["chat"] == chat]


@pytest.fixture()
def outbox(monkeypatch):
    from app.services import panel_logo

    box = Outbox()
    monkeypatch.setattr(bots, "_send_telegram_message", box)
    # El logo del panel tiene su propia prueba (test_reports_v2); aqui la base no trae las tablas de marca.
    monkeypatch.setattr(panel_logo, "panel_logo", AsyncMock(return_value={"url": "/brand-media/x/y.webp", "source": "published"}))
    monkeypatch.setattr(svc, "_bot", AsyncMock(return_value="TOKEN"))
    return box


async def _session(url):
    engine = create_async_engine(url)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _company(db, name: str, on: bool) -> str:
    cid = str(uuid.uuid4())
    await db.execute(text("INSERT INTO companies (id, name, slug, settings_json) VALUES (CAST(:i AS uuid), :n, :s, CAST(:j AS jsonb))"),
                     {"i": cid, "n": name, "s": name.lower(), "j": '{"client_settings": {"payroll": {"ordinary_hours_limit": 40}}}'})
    await db.execute(text("INSERT INTO company_core_settings (company_id, currency, timezone, language) VALUES (CAST(:i AS uuid), 'USD', 'America/Chicago', 'es')"),
                     {"i": cid})
    await db.execute(text("INSERT INTO modules (code, name, category) VALUES ('shifts', 'Turnos', 'core') ON CONFLICT (code) DO NOTHING"))
    await db.execute(text("""INSERT INTO company_modules (company_id, module_id, enabled, settings)
        SELECT CAST(:i AS uuid), id, :on, '{}'::jsonb FROM modules WHERE code = 'shifts'"""), {"i": cid, "on": on})
    await db.commit()
    return cid


async def _employee(db, cid, name, role, tg=None, status="active") -> str:
    return (await db.execute(text("""INSERT INTO employees (company_id, full_name, role, status, telegram_user_id)
        VALUES (CAST(:c AS uuid), :n, :r, :s, :t) RETURNING id::text"""), {"c": cid, "n": name, "r": role, "s": status, "t": tg})).scalar()


async def _setup_company(db, on=True):
    cid = await _company(db, f"Demo{uuid.uuid4().hex[:6]}", on)
    people = {}
    for i in range(1, 6):
        people[f"op{i}"] = await _employee(db, cid, f"Operario {i}", "operario", f"tg{i}" if i <= 3 else None)
    people["sup"] = await _employee(db, cid, "Nico Supervisor", "supervisor", "tgS")
    people["dir"] = await _employee(db, cid, "Diana Directora", "gerencia")
    people["log"] = await _employee(db, cid, "Luis Logística", "inventario")
    people["gone"] = await _employee(db, cid, "Ex Operario", "operario", status="inactive")
    await db.commit()
    await svc.ensure_defaults(db, cid)
    tpls = await svc.templates(db, cid)
    await svc.save_config(db, cid, {
        "templates": [{"id": t.id, "name": t.name, "code": t.code, "start": t.start.strftime("%H:%M"), "end": t.end.strftime("%H:%M"), "color": t.color} for t in tpls],
        "rules": {"min_rest_hours": 12, "days_off_per_week": 1, "max_consecutive_days": 6, "weekly_hours_cap": None, "max_consecutive_nights": 3, "response_hours": 2},
        "coverage": [{"template_id": t.id, "role": "operario", "min": 1} for t in tpls],
    }, "dueno@demo")
    return cid, people


@pytest.mark.asyncio
async def test_build_publish_and_full_change_flow(pg_url, outbox):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid, p = await _setup_company(db)
        rules, raw = await svc.rules(db, cid)
        assert raw["default_weekly_hours_cap"] == 40 and rules.weekly_cap_minutes == 2400, "tope = el de Personal/nomina"
        emps = await svc.employees(db, cid)
        assert p["gone"] not in {e.id for e in emps}, "solo empleados activos"

        first = await svc.build_draft(db, cid, WEEK + timedelta(days=3))  # cualquier dia: arma desde el lunes
        view = await svc.week_view(db, cid, WEEK)
        assert view["status"] == "draft" and first["gaps"] == [] and view["analysis"]["coverage_ok"] and view["analysis"]["rest_ok"]
        rows1 = sorted((a["employee_id"], a["work_date"], a["template_id"]) for a in view["assignments"])
        await svc.build_draft(db, cid, WEEK)
        rows2 = sorted((a["employee_id"], a["work_date"], a["template_id"]) for a in (await svc.week_view(db, cid, WEEK))["assignments"])
        assert rows1 == rows2, "rearmar reemplaza el borrador con el mismo resultado"
        assert {r[0] for r in rows1} <= {p[f"op{i}"] for i in range(1, 6)}

        sent = await svc.publish(db, cid, WEEK)
        assert sent["sent"] == 3 and sorted(sent["without_bot"]) == ["Operario 4", "Operario 5"]
        assert outbox.to("tg1") and "Tus turnos de la semana" in outbox.to("tg1")[0]["text"]
        with pytest.raises(svc.Invalid):
            await svc.build_draft(db, cid, WEEK)
        assert (await svc.week_view(db, cid, WEEK))["status"] == "published"
        mine = await svc.my_week_text(db, cid, p["op1"], "en", WEEK + timedelta(days=2))
        assert mine.startswith("📅 Your shifts for the week of")

        # Cambio de turno con al menos 3 candidatos.
        assignments = (await svc.week_view(db, cid, WEEK))["assignments"]
        target = None
        for a in assignments:
            prop = await svc.proposal(db, cid, a["id"])
            if len(prop["candidates"]) >= 3:
                target, cands = a, prop["candidates"]
                break
        assert target, "hay un turno con 3 o mas candidatos"
        assert 2 <= len(cands) <= 5 and all(c["role"] == "operario" for c in cands)
        made = await svc.create_change(db, cid, target["id"], "sup@demo")
        with pytest.raises(svc.Invalid):
            await svc.create_change(db, cid, target["id"], "sup@demo")
        outbox.sent.clear()
        ch = await svc.start(db, cid, made["id"])
        assert ch["status"] == "waiting" and ch["current_index"] == 0
        stored = await svc.change(db, cid, made["id"])
        assert stored["deadline_at"] is not None and abs((stored["deadline_at"] - datetime.now(timezone.utc)) - timedelta(hours=2)) < timedelta(minutes=1)

        # Rechazo -> siguiente candidato y aviso al supervisor.
        await svc.respond(db, cid, made["id"], cands[0]["employee_id"], 0, False, via="bot")
        stored = await svc.change(db, cid, made["id"])
        assert stored["status"] == "waiting" and stored["current_index"] == 1
        assert any("se le propone a" in m["text"] for m in outbox.to("tgS"))
        # Una respuesta vieja (posicion 0) ya no vale.
        assert (await svc.respond(db, cid, made["id"], cands[0]["employee_id"], 0, True, via="bot"))["ok"] is False

    # Vencimiento: se calcula desde la base (otra sesion, como tras un reinicio).
    async with maker() as db:
        assert await svc.expire_due(db, datetime.now(timezone.utc)) == 0, "aun no vence"
        assert await svc.expire_due(db, datetime.now(timezone.utc) + timedelta(hours=2, minutes=1)) == 1
        stored = await svc.change(db, cid, made["id"])
        assert stored["current_index"] == 2 and [e["kind"] for e in stored["log"]][-2:] == ["expired", "offered"]

        # Acepta el tercero: la malla cambia y se avisa a quien pidio, al candidato y al supervisor.
        before = {(a["employee_id"], a["work_date"]): a["template_id"] for a in (await svc.week_view(db, cid, WEEK))["assignments"]}
        outbox.sent.clear()
        res = await svc.respond(db, cid, made["id"], cands[2]["employee_id"], 2, True, via="bot")
        assert res == {"ok": True, "result": "accepted"}
        after = {(a["employee_id"], a["work_date"]): a["template_id"] for a in (await svc.week_view(db, cid, WEEK))["assignments"]}
        day = target["work_date"]
        assert after[(cands[2]["employee_id"], day)] == target["template_id"]
        if cands[2]["kind"] == "cover":
            assert (target["employee_id"], day) not in after, "quien pidio queda libre ese dia"
        else:
            assert after[(target["employee_id"], day)] == before[(cands[2]["employee_id"], day)]
        assert (await svc.week_view(db, cid, WEEK))["analysis"]["rest_ok"], "despues del cambio se cumplen las reglas"
        assert (await svc.change(db, cid, made["id"]))["status"] == "accepted"
        assert any("Cambio confirmado" in m["text"] for m in outbox.to("tgS"))

        # Lista agotada -> sin cubrir con alerta al supervisor (respuestas registradas a mano).
        other = None
        for a in (await svc.week_view(db, cid, WEEK))["assignments"]:
            if a["id"] != target["id"] and len((await svc.proposal(db, cid, a["id"]))["candidates"]) >= 2:
                other = a
                break
        ch2 = await svc.create_change(db, cid, other["id"], "sup@demo")
        await svc.start(db, cid, ch2["id"])
        outbox.sent.clear()
        for i, c in enumerate(ch2["candidates"]):
            assert (await svc.respond(db, cid, ch2["id"], c["employee_id"], i, False, via="manual", actor="sup@demo"))["ok"]
        done = await svc.change(db, cid, ch2["id"])
        assert done["uncovered"] is True and done["status"] == "rejected" and done["log"][-1]["kind"] == "uncovered"
        assert any(e.get("via") == "manual" and e.get("by") == "sup@demo" for e in done["log"])
        assert any("quedó sin cubrir" in m["text"] for m in outbox.to("tgS"))
    await engine.dispose()


@pytest.mark.asyncio
async def test_permissions_module_off_and_tenant_isolation(pg_url, outbox, monkeypatch):
    from app.api import deps
    from app.web import admin_v2_routes

    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid, p = await _setup_company(db)
        other, _ = await _setup_company(db, on=False)
        monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=False))
        req = SimpleNamespace()

        async def who(role, company=cid, settings=None):
            monkeypatch.setattr(deps, "require_company_user_for_tenant", AsyncMock(return_value=SimpleNamespace(role=role, email=f"{role}@x", settings_json=settings or {})))
            return await api.actor(uuid.UUID(company), req, "Bearer x", db)

        for role in ["operario", "inventario", "logistica", "otro"]:
            with pytest.raises(HTTPException) as exc:
                await who(role)
            assert exc.value.status_code == 403
        # Mini panel ligado a Personal: manda el rol del empleado.
        with pytest.raises(HTTPException):
            await who("mini_panel", settings={"mini_panel": {"employee_id": p["op1"]}})
        assert (await who("mini_panel", settings={"mini_panel": {"employee_id": p["sup"]}}))["role"] == "supervisor"
        assert (await who("mini_panel", settings={"mini_panel": {"employee_id": p["dir"]}}))["role"] == "director"
        assert (await who("company_admin"))["role"] == "owner"

        director = await who("gerencia")
        ctx = await api.context(uuid.UUID(cid), director, db)
        assert ctx["can"]["create_change"] is False and ctx["role"] == "director" and ctx["logo_url"] == "/brand-media/x/y.webp"
        await api.build(uuid.UUID(cid), WEEK.isoformat(), director, db)
        await api.publish(uuid.UUID(cid), WEEK.isoformat(), director, db)
        a = (await svc.week_view(db, cid, WEEK))["assignments"][0]
        with pytest.raises(HTTPException) as exc:
            await api.create_change(uuid.UUID(cid), {"assignment_id": a["id"]}, director, db)
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException) as exc:
            await api.proposal(uuid.UUID(cid), {"assignment_id": a["id"]}, director, db)
        assert exc.value.status_code == 403
        sup = await who("supervisor")
        made = await api.create_change(uuid.UUID(cid), {"assignment_id": a["id"], "send": True}, sup, db)
        assert made["status"] in {"waiting", "rejected"}

        # Sin sesion: 401 (lo da la dependencia de siempre).
        monkeypatch.setattr(deps, "require_company_user_for_tenant", AsyncMock(side_effect=HTTPException(status_code=401)))
        with pytest.raises(HTTPException) as exc:
            await api.actor(uuid.UUID(cid), req, None, db)
        assert exc.value.status_code == 401
        # Modulo apagado: 404 aunque sea el dueno.
        with pytest.raises(HTTPException) as exc:
            await who("company_admin", company=other)
        assert exc.value.status_code == 404
        # Nada de una empresa se ve desde la otra.
        assert await svc.change(db, other, made["id"]) is None
        assert await svc.list_changes(db, other) == []
        assert (await svc.week_view(db, other, WEEK))["assignments"] == []
        with pytest.raises(svc.Invalid):
            await svc.proposal(db, other, a["id"])
        assert await svc.module_on(db, cid) and not await svc.module_on(db, other)
    await engine.dispose()


@pytest.mark.asyncio
async def test_bot_my_shifts_and_buttons_only_with_module(pg_url, outbox, monkeypatch):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid, p = await _setup_company(db)
        other, q = await _setup_company(db, on=False)
        # "Mis turnos" muestra la semana EN CURSO (zona de la empresa): se publica esa.
        from zoneinfo import ZoneInfo

        today = datetime.now(ZoneInfo("America/Bogota")).date()
        this_week = today - timedelta(days=today.weekday())
        await svc.build_draft(db, cid, this_week)
        await svc.publish(db, cid, this_week)
        employee = SimpleNamespace(id=uuid.UUID(p["op1"]), full_name="Operario 1")
        monkeypatch.setattr(bots, "_find_employee_by_telegram", AsyncMock(return_value=employee))
        bot = SimpleNamespace(company_id=uuid.UUID(cid))
        outbox.sent.clear()
        item = await bots._process_shift_update(db, bot=bot, token="T", update_id=1, text_value="clx:shift:mine", language="fr",
                                                telegram_user_id="tg1", username=None, chat_id="tg1", send_replies=True)
        assert item.action == "shift_mine" and outbox.sent[-1]["text"].startswith("📅 Tes services de la semaine du")
        assert (await svc.employee_contact(db, cid, p["op1"]))["lang"] == "fr", "el idioma del celular queda para los avisos"
        # Boton de una propuesta que ya no existe: "ya no esta vigente".
        item = await bots._process_shift_update(db, bot=bot, token="T", update_id=2, text_value=f"clx:shift:yes:{uuid.uuid4()}:0", language="es",
                                                telegram_user_id="tg1", username=None, chat_id="tg1", send_replies=True)
        assert item.action == "shift_reply" and outbox.sent[-1]["text"] == svc.st("es", "gone")
        # Otra empresa sin el modulo: no responde turnos.
        monkeypatch.setattr(bots, "_find_employee_by_telegram", AsyncMock(return_value=SimpleNamespace(id=uuid.UUID(q["op1"]), full_name="x")))
        outbox.sent.clear()
        item = await bots._process_shift_update(db, bot=SimpleNamespace(company_id=uuid.UUID(other)), token="T", update_id=3, text_value="clx:shift:mine",
                                                language="es", telegram_user_id="tg1", username=None, chat_id="tg1", send_replies=True)
        assert item.action == "shift_ignored" and outbox.sent == []
    await engine.dispose()


def _cb(keyboard):
    return [b["callback_data"] for row in keyboard["inline_keyboard"] for b in row]


@pytest.mark.parametrize("role", ["supervisor", "inventario"])
@pytest.mark.parametrize("status", ["sin_turno", "on_break", "working"])
def test_supervisor_and_storekeeper_menus_stay_the_same(role, status):
    employee = SimpleNamespace(role=role, employee_type=None)
    base = {"core", "workforce", "bots", "materials", "inventory", "gps"}
    before = bots._menu_keyboard("es", base, status, employee)
    after = bots._menu_keyboard("es", base | {"shifts"}, status, employee)
    assert "clx:shift:mine" not in _cb(before), "sin el modulo, el menu de siempre"
    assert [c for c in _cb(after) if c != "clx:shift:mine"] == _cb(before), "con el modulo solo se agrega Mis turnos"
    assert _cb(after).count("clx:shift:mine") == 1 and _cb(after)[-1] == "clx:language"
    expected = {"sin_turno": ["clx:cmd:entrada", "clx:language"], "on_break": ["clx:cmd:reanudar", "clx:cmd:salida", "clx:language"],
                "working": ["clx:cmd:pausa", "clx:cmd:salida", "clx:cmd:material", "clx:cmd:ubicacion", "clx:language"]}[status]
    assert _cb(before) == expected
    assert bots.MATERIAL_REQUEST_ALLOWED_ROLES == {"admin", "admin_empresa", "supervisor", "inventario", "inventory"}


def test_routes_are_guarded_and_module_is_in_the_catalog():
    from app.api.v1.endpoints.module_catalog_v1 import MODULE_CATALOG_ES

    assert MODULE_CATALOG_ES["shifts"]["badge"] == "TRN" and MODULE_CATALOG_ES["shifts"]["layer"] == "operativo"
    routes = [r for r in api.router.routes]
    assert len(routes) >= 10
    for r in routes:
        deps_ = [d.call for d in r.dependant.dependencies]
        assert api.actor in deps_, f"{r.path} sin sesion"
    from app.api.v1 import router as v1

    paths = {getattr(r, "path", "") for r in v1.api_router.routes}
    assert "/turnos/companies/{company_id}/week" in paths
    assert "/shifts/start" in paths, "las rutas de turnos de siempre siguen"


@pytest.mark.asyncio
@pytest.mark.parametrize("data", ["clx:shift:mine", "clx:shift:no:abc:1", "/turnos"])
async def test_every_telegram_update_reaches_the_shifts_handler(monkeypatch, data):
    """Polling y webhooks pasan por _process_telegram_update -> 052C -> Turnos."""
    handler = AsyncMock(return_value=SimpleNamespace(action="shift_mine"))
    monkeypatch.setattr(bots, "_process_shift_update", handler)
    monkeypatch.setattr(bots, "_get_user_language", AsyncMock(return_value="es"))
    monkeypatch.setattr(bots, "_answer_callback_query", AsyncMock())
    sender = {"id": 99, "language_code": "en"}
    if data.startswith("/"):
        update = {"update_id": 1, "message": {"chat": {"id": 5}, "from": sender, "text": data}}
    else:
        update = {"update_id": 1, "callback_query": {"id": "cb", "from": sender, "data": data, "message": {"chat": {"id": 5}}}}
    item = await bots._process_telegram_update_052C(None, bot=SimpleNamespace(company_id=uuid.uuid4()), token="T", update=update, send_replies=False)
    assert item.action == "shift_mine" and handler.await_args.kwargs["text_value"] == data
