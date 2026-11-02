"""Lugares de trabajo (interruptor work_locations) contra Postgres REAL (pgserver)
con la migracion 024x.

- Migracion aditiva e idempotente: siembra Virginia/Alabama solo para VOLTAGE,
  los empleados quedan "Sin asignar" y sus datos (descuento 2) no cambian.
- Asignar (uno y varios) deja historial de traslados con quien y cuando; el
  descuento 2 guardado no cambia; location_on() responde el lugar por fecha.
- Administrar lugares: renombrar, ordenar, desactivar; nunca borra.
- CRM Campo agrupado: conteos por lugar, orden, supervisores, perimetro, Sin
  asignar, tiempo trabajado = conectado - pausas.
- Permisos en el servidor (401/403/404) y aislamiento entre empresas.
Si pgserver no esta instalado (p. ej. en Railway) la prueba se salta.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

pgserver = pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.api.v1.endpoints import work_locations as api  # noqa: E402
from app.services import work_locations as svc  # noqa: E402
from tests.test_brand_pg import BASE_SCHEMA  # noqa: E402

VOLTAGE = "f1e8f774-f052-49ca-880a-268805f07db0"
URBANIA_OLD = "76974191-1dc6-4eb4-9b19-7d1e9ad82946"
EXTRA_SCHEMA = """
ALTER TABLE modules ADD COLUMN IF NOT EXISTS is_active boolean DEFAULT true;
CREATE TABLE IF NOT EXISTS employees (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL REFERENCES companies(id), full_name varchar(200),
  role varchar(80) DEFAULT 'operator', employee_type varchar(50) DEFAULT 'operator', status varchar(30) DEFAULT 'active', telegram_user_id varchar(80),
  hourly_rate_regular numeric DEFAULT 0, deduction_1 numeric DEFAULT 0, deduction_2 numeric DEFAULT 0);
CREATE TABLE IF NOT EXISTS workforce_attendance_status (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid, employee_id uuid, status varchar(40),
  last_event_type varchar(40), last_event_at timestamptz);
-- Igual que produccion (2026-11-01): la tabla de eventos NO tiene telegram_user_id.
CREATE TABLE IF NOT EXISTS workforce_attendance_events (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid, employee_id uuid,
  event_type varchar(40), event_label varchar(80), employee_name varchar(200), employee_role varchar(80), status_after varchar(40),
  source varchar(40), notes text, created_at timestamptz DEFAULT now(), module_code varchar(40), source_channel varchar(40),
  source_ref varchar(120), bot_instance_id uuid, detail text, payload_json jsonb, metadata_json jsonb, latitude numeric,
  longitude numeric, evidence_url text, occurred_at timestamptz);
CREATE TABLE IF NOT EXISTS company_gps_perimeters (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid, slot integer, name varchar(80),
  latitude_min numeric, latitude_max numeric, longitude_min numeric, longitude_max numeric, is_active boolean DEFAULT true)
"""


def _migration() -> list[str]:
    statements: list[str] = []

    class Op:
        def execute(self, sql):
            statements.append(str(sql))

    module = importlib.import_module("migrations.versions.024x_work_locations")
    module.op = Op()
    module.upgrade()
    assert len(module.revision) <= 32 and module.down_revision == "024w_nexa_whatsapp"
    return statements


@pytest.fixture(scope="module")
def pg_url():
    folder = tempfile.mkdtemp(prefix="cx_pg_wl_")
    server = pgserver.get_server(folder, cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            for stmt in [s for s in (BASE_SCHEMA + ";" + EXTRA_SCHEMA).split(";") if s.strip()]:
                await conn.execute(text(stmt))
            # Empresas antes de migrar, con un empleado ya guardado (descuento 2 = 40).
            for cid, name in ((VOLTAGE, "VOLTAGE"), (URBANIA_OLD, "VOLTAGE (archivada)")):
                await conn.execute(text("INSERT INTO companies (id, name) VALUES (CAST(:i AS uuid), :n)"), {"i": cid, "n": name})
            await conn.execute(text("INSERT INTO employees (company_id, full_name, deduction_2) VALUES (CAST(:c AS uuid), 'Antes de migrar', 40)"), {"c": VOLTAGE})
            for stmt in _migration():
                await conn.execute(text(stmt))
            for stmt in _migration():  # idempotente
                await conn.execute(text(stmt))
        await engine.dispose()

    asyncio.run(setup())
    yield url


async def _session(url):
    engine = create_async_engine(url)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _module(db, cid: str, code: str, settings: dict | None = None, enabled: bool = True) -> None:
    mid = (await db.execute(text("SELECT id::text FROM modules WHERE code = :c"), {"c": code})).scalar()
    if not mid:
        mid = (await db.execute(text("INSERT INTO modules (code, name) VALUES (:c, :c) RETURNING id::text"), {"c": code})).scalar()
    await db.execute(text("DELETE FROM company_modules WHERE company_id = CAST(:c AS uuid) AND module_id = CAST(:m AS uuid)"), {"c": cid, "m": mid})
    await db.execute(text("INSERT INTO company_modules (company_id, module_id, enabled, settings) VALUES (CAST(:c AS uuid), CAST(:m AS uuid), :e, CAST(:s AS jsonb))"),
                     {"c": cid, "m": mid, "e": enabled, "s": json.dumps(settings or {})})


async def _company(db, *, on: bool, name: str = "Otra") -> str:
    cid = str(uuid.uuid4())
    await db.execute(text("INSERT INTO companies (id, name) VALUES (CAST(:i AS uuid), :n)"), {"i": cid, "n": name})
    await _module(db, cid, "workforce", {"workforce_v2": True, **({"work_locations": True} if on else {})})
    await _module(db, cid, "crm")
    await _module(db, cid, "gps")
    await db.commit()
    return cid


async def _emp(db, cid: str, name: str, role: str = "operario", d2: float = 0, status: str = "active") -> str:
    return (await db.execute(text("""INSERT INTO employees (company_id, full_name, role, employee_type, deduction_2, status)
        VALUES (CAST(:c AS uuid), :n, :r, :r, :d, :s) RETURNING id::text"""), {"c": cid, "n": name, "r": role, "d": d2, "s": status})).scalar()


async def _places(db, cid: str) -> dict[str, str]:
    return {loc["name"]: loc["id"] for loc in await svc.list_locations(db, cid)}


async def test_migration_seeds_only_voltage_and_keeps_data(pg_url):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        rows = (await db.execute(text("SELECT company_id::text, name, code, timezone, is_active, sort_order FROM work_locations ORDER BY sort_order"))).all()
        assert [tuple(r) for r in rows] == [(VOLTAGE, "Virginia", "VA", "America/New_York", True, 1), (VOLTAGE, "Alabama", "AL", "America/Chicago", True, 2)], "una sola vez y solo VOLTAGE"
        old = (await db.execute(text("SELECT deduction_2, work_location_id FROM employees WHERE full_name = 'Antes de migrar'"))).one()
        assert float(old[0]) == 40 and old[1] is None, "dato guardado intacto y Sin asignar"
        for table in ("work_location_changes", "work_location_perimeters"):
            assert (await db.execute(text(f"SELECT count(*) FROM {table}"))).scalar() == 0
    await engine.dispose()


async def test_assign_history_and_deduction2_unchanged(pg_url):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        await _module(db, VOLTAGE, "workforce", {"workforce_v2": True, "work_locations": True})
        await db.commit()
        places = await _places(db, VOLTAGE)
        a = await _emp(db, VOLTAGE, "Ana Traslado", d2=125.5)
        b = await _emp(db, VOLTAGE, "Beto Multiple")
        c = await _emp(db, VOLTAGE, "Caro Multiple")
        await db.commit()

        out = await svc.assign(db, VOLTAGE, [a], places["Virginia"], actor="dueno@voltage", source="personal_form")
        assert out["changed"] == 1
        out = await svc.assign(db, VOLTAGE, [a, b, c], places["Alabama"], actor="dueno@voltage", source="personal_multiple")
        assert out == {"changed": 3, "unchanged": 0, "work_location_id": places["Alabama"]}
        again = await svc.assign(db, VOLTAGE, [b, c], places["Alabama"], actor="x")
        assert again["changed"] == 0 and again["unchanged"] == 2, "sin cambio no hay traslado"

        d2 = (await db.execute(text("SELECT deduction_2 FROM employees WHERE id = CAST(:e AS uuid)"), {"e": a})).scalar()
        assert float(d2) == 125.5, "asignar lugar no toca el descuento 2"
        hist = await svc.history(db, VOLTAGE, a)
        assert [(h["from_name"], h["to_name"], h["changed_by"]) for h in hist] == [("Virginia", "Alabama", "dueno@voltage"), (None, "Virginia", "dueno@voltage")]
        assert hist[0]["changed_at"].endswith("Z")

        raw = (await db.execute(text("""SELECT from_location_id::text AS from_location_id, to_location_id::text AS to_location_id, changed_at
            FROM work_location_changes WHERE employee_id = CAST(:e AS uuid)"""), {"e": a})).mappings().all()
        changes = [dict(r) for r in raw]
        first = min(r["changed_at"] for r in changes)
        assert svc.location_on(changes, places["Alabama"], first - timedelta(seconds=1)) is None, "antes del primer traslado: sin lugar"
        assert svc.location_on(changes, places["Alabama"], datetime.now(timezone.utc) + timedelta(minutes=1)) == places["Alabama"]

        # Quitar el lugar (Sin asignar) tambien deja traslado.
        assert (await svc.assign(db, VOLTAGE, [c], None, actor="x"))["changed"] == 1
        assign = await svc.assignments(db, VOLTAGE)
        assert assign[a] == places["Alabama"] and assign[c] is None

        # Aislamiento: empleado de otra empresa o lugar de otra empresa -> rechazo, sin cambios.
        other = await _company(db, on=True)
        foreign = await _emp(db, other, "Ajena")
        await db.commit()
        with pytest.raises(svc.Invalid):
            await svc.assign(db, VOLTAGE, [a, foreign], places["Virginia"], actor="x")
        await db.rollback()
        await svc.save_locations(db, other, {"locations": [{"name": "Texas", "timezone": "America/Chicago"}]})
        texas = (await _places(db, other))["Texas"]
        with pytest.raises(svc.Invalid):
            await svc.assign(db, VOLTAGE, [a], texas, actor="x")
        await db.rollback()
        assert (await svc.assignments(db, VOLTAGE))[a] == places["Alabama"]
        assert foreign not in await svc.assignments(db, VOLTAGE)
        assert await svc.history(db, other, a) == [], "el historial de VOLTAGE no se ve desde otra empresa"
    await engine.dispose()


async def test_manage_locations_rename_order_deactivate_never_delete(pg_url):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _company(db, on=True, name="Gestion")
        await svc.save_locations(db, cid, {"locations": [{"name": "Uno", "code": "u-1", "timezone": "America/New_York"}, {"name": "Dos", "timezone": "America/Chicago"}]})
        p = await _places(db, cid)
        e = await _emp(db, cid, "Persona")
        await db.commit()
        await svc.assign(db, cid, [e], p["Dos"], actor="x")
        saved = await svc.save_locations(db, cid, {"locations": [
            {"id": p["Dos"], "name": "Dos renombrado", "timezone": "America/Denver", "is_active": False},
            {"id": p["Uno"], "name": "Uno", "code": "U1", "timezone": "America/New_York"},
        ]})
        assert [(l["name"], l["sort_order"], l["is_active"], l["timezone"]) for l in saved] == [
            ("Dos renombrado", 1, False, "America/Denver"), ("Uno", 2, True, "America/New_York")]
        assert saved[1]["code"] == "U1"
        assert (await svc.assignments(db, cid))[e] == p["Dos"], "desactivar no quita a nadie"
        with pytest.raises(svc.Invalid):
            await svc.assign(db, cid, [e], p["Dos"], actor="x")  # desactivado: no se ofrece
        for bad in ({"locations": [{"id": p["Uno"], "name": "Uno", "timezone": "America/New_York", "is_active": False}]},
                    {"locations": [{"name": "A1", "timezone": "Mars/Base"}]},
                    {"locations": [{"name": "Rep", "timezone": "America/Chicago"}, {"name": "rep", "timezone": "America/Chicago"}]},
                    {"locations": [{"id": str(uuid.uuid4()), "name": "Ajeno", "timezone": "America/Chicago"}]},
                    {"locations": [{"name": "Dos renombrado", "timezone": "America/Chicago"}]}):
            with pytest.raises(svc.Invalid):
                await svc.save_locations(db, cid, bad)
            await db.rollback()
        assert len(await svc.list_locations(db, cid)) == 2, "nunca se borra un lugar"
    await engine.dispose()


async def test_board_groups_counts_order_and_worked_time(pg_url):
    engine, maker = await _session(pg_url)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    async with maker() as db:
        cid = await _company(db, on=True, name="Tablero")
        await svc.save_locations(db, cid, {"locations": [{"name": "Virginia", "code": "VA", "timezone": "America/New_York"},
                                                         {"name": "Alabama", "code": "AL", "timezone": "America/Chicago"}]})
        p = await _places(db, cid)
        ids = {}
        for name, role in (("Zoe Sup", "supervisor"), ("Andres", "operario"), ("Bea Pausa", "operario"), ("Carlos Libre", "operario"),
                           ("Dani AL", "operario"), ("Sin Lugar", "operario")):
            ids[name] = await _emp(db, cid, name, role=role)
        await _emp(db, cid, "Archivado", status="archived")
        await db.commit()
        await svc.assign(db, cid, [ids["Zoe Sup"], ids["Andres"], ids["Bea Pausa"], ids["Carlos Libre"]], p["Virginia"], actor="x")
        await svc.assign(db, cid, [ids["Dani AL"]], p["Alabama"], actor="x")

        async def status(name, st, at):
            await db.execute(text("INSERT INTO workforce_attendance_status (company_id, employee_id, status, last_event_type, last_event_at) VALUES (CAST(:c AS uuid), CAST(:e AS uuid), :s, '', :a)"),
                             {"c": cid, "e": ids[name], "s": st, "a": at})

        async def event(name, kind, at, lat=None, lng=None):
            await db.execute(text("INSERT INTO workforce_attendance_events (company_id, employee_id, event_type, occurred_at, latitude, longitude) VALUES (CAST(:c AS uuid), CAST(:e AS uuid), :k, :a, :la, :lo)"),
                             {"c": cid, "e": ids[name], "k": kind, "a": at, "la": lat, "lo": lng})

        await status("Andres", "working", now - timedelta(hours=2))
        await event("Andres", "check_in", now - timedelta(hours=2))
        await status("Zoe Sup", "working", now - timedelta(hours=1))
        await event("Zoe Sup", "check_in", now - timedelta(hours=1))
        await event("Zoe Sup", "gps_location", now - timedelta(minutes=5), 37.5, -77.4)
        await status("Bea Pausa", "on_break", now - timedelta(minutes=30))
        await event("Bea Pausa", "check_in", now - timedelta(hours=3))
        await event("Bea Pausa", "break_start", now - timedelta(minutes=30))
        await status("Carlos Libre", "checked_out", now - timedelta(hours=5))
        await event("Andres", "gps_location", now - timedelta(minutes=3), 10.0, 10.0)
        await db.execute(text("INSERT INTO company_gps_perimeters (company_id, slot, name, latitude_min, latitude_max, longitude_min, longitude_max) VALUES (CAST(:c AS uuid), 1, 'Planta VA', 37, 38, -78, -77)"), {"c": cid})
        await db.commit()

        board = await svc.board(db, cid, now_value=now)
        groups = {g["name"]: g for g in board["groups"]}
        assert [g["name"] for g in board["groups"]] == ["Virginia", "Alabama", "Sin asignar"]
        va = groups["Virginia"]
        assert va["timezone"] == "America/New_York" and va["supervisors"] == ["Zoe Sup"]
        assert va["counts"] == {"total": 4, "working": 2, "on_break": 1, "no_shift": 1, "in_perimeter": 1}
        assert [r["employee_name"] for r in va["people"]] == ["Andres", "Zoe Sup", "Bea Pausa", "Carlos Libre"], "trabajando, en pausa, sin turno; alfabetico"
        rows = {r["employee_name"]: r for r in va["people"]}
        assert rows["Andres"]["core"]["shift_effective_seconds"] == 7200
        assert rows["Bea Pausa"]["core"]["shift_effective_seconds"] == 9000, "conectado - pausas"
        assert rows["Zoe Sup"]["gps_place"] == "inside" and rows["Andres"]["gps_place"] == "outside" and rows["Carlos Libre"]["gps_place"] == "none"
        assert groups["Alabama"]["counts"]["total"] == 1 and groups["Alabama"]["counts"]["no_shift"] == 1
        assert [r["employee_name"] for r in groups["Sin asignar"]["people"]] == ["Sin Lugar"], "nadie se pierde; archivados no salen"
        s = board["summary"]
        assert (s["employees_total"], s["active_now"], s["on_break"], s["gps_inside"]) == (6, 2, 1, 1), "la suma de arriba"
        assert "gps" in board["active_modules"] and "crm" in board["active_modules"]

        # Lugar desactivado con gente: su seccion sigue; sin gente desaparece.
        await svc.save_locations(db, cid, {"locations": [{"id": p["Virginia"], "name": "Virginia", "timezone": "America/New_York"},
                                                         {"id": p["Alabama"], "name": "Alabama", "timezone": "America/Chicago", "is_active": False}]})
        names = [g["name"] for g in (await svc.board(db, cid, now_value=now))["groups"]]
        assert names == ["Virginia", "Alabama", "Sin asignar"]
        await svc.save_locations(db, cid, {"locations": [{"id": p["Virginia"], "name": "Virginia", "timezone": "America/New_York"},
                                                         {"id": p["Alabama"], "name": "Alabama", "timezone": "America/Chicago", "is_active": True}]})
        # Rapidez: 100 personas con el mismo numero fijo de consultas.
        for i in range(94):
            await _emp(db, cid, f"Masa {i:03d}")
        await db.commit()
        start = datetime.now()
        big = await svc.board(db, cid, now_value=now)
        assert sum(g["counts"]["total"] for g in big["groups"]) == 100
        assert (datetime.now() - start).total_seconds() < 3
    await engine.dispose()


async def test_permissions_switch_off_and_tenant(pg_url, monkeypatch):
    from app.api import deps
    from app.web import admin_v2_routes

    engine, maker = await _session(pg_url)
    async with maker() as db:
        on = await _company(db, on=True, name="Con lugares")
        off = await _company(db, on=False, name="Sin lugares")
        monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=False))
        req = SimpleNamespace()

        async def who(role, company=on):
            monkeypatch.setattr(deps, "require_company_user_for_tenant", AsyncMock(return_value=SimpleNamespace(role=role, email=f"{role}@x", full_name=role, id=uuid.uuid4())))
            return await api.actor(uuid.UUID(company), req, "Bearer x", db)

        for role in ("mesero", "cocina", "caja", "mini_panel", ""):
            with pytest.raises(HTTPException) as exc:
                await who(role)
            assert exc.value.status_code == 403, role
        owner = await who("company_admin")
        sup = await who("supervisor")
        op = await who("operario")
        got = await api.get_locations(uuid.UUID(on), owner, db)
        assert got["can_manage"] is True and got["can_assign"] is True
        got = await api.get_locations(uuid.UUID(on), sup, db)
        assert got["can_manage"] is False and got["can_assign"] is True
        got = await api.get_locations(uuid.UUID(on), op, db)
        assert got["can_manage"] is False and got["can_assign"] is False
        with pytest.raises(HTTPException) as exc:
            await api.put_locations(uuid.UUID(on), {"locations": [{"name": "X1", "timezone": "America/Chicago"}]}, sup, db)
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException) as exc:
            await api.post_assign(uuid.UUID(on), {"employee_ids": [str(uuid.uuid4())], "work_location_id": None}, op, db)
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException) as exc:
            await api.put_locations(uuid.UUID(on), {"locations": [{"name": "X1", "timezone": "Nope/Zone"}]}, owner, db)
        assert exc.value.status_code == 422
        assert (await api.put_locations(uuid.UUID(on), {"locations": [{"name": "Virginia", "timezone": "America/New_York"}]}, owner, db))["ok"]

        # Interruptor apagado: 404 aunque sea el dueno.
        with pytest.raises(HTTPException) as exc:
            await who("company_admin", company=off)
        assert exc.value.status_code == 404
        # Sin sesion: 401; otra empresa: 403 (las da la dependencia de siempre).
        monkeypatch.setattr(deps, "require_company_user_for_tenant", AsyncMock(side_effect=HTTPException(status_code=401)))
        with pytest.raises(HTTPException) as exc:
            await api.actor(uuid.UUID(on), req, None, db)
        assert exc.value.status_code == 401
        monkeypatch.setattr(deps, "require_company_user_for_tenant", AsyncMock(side_effect=HTTPException(status_code=403, detail="tenant_not_allowed")))
        with pytest.raises(HTTPException) as exc:
            await api.actor(uuid.UUID(on), req, "Bearer otra", db)
        assert exc.value.status_code == 403
        # Admin V2 entra como dueno.
        monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=True))
        assert (await api.actor(uuid.UUID(on), req, None, db))["role"] == "owner"
    await engine.dispose()
