"""CRM VELVET-LAB contra Postgres REAL (pgserver) con la migracion 024p_crm_lab.

- PIN: correcto entra; incorrecto descuenta intentos; 5 fallos -> 5 minutos de
  bloqueo (aun con el PIN correcto); sin PIN -> "Pide tu PIN al administrador".
- Turno: Iniciar / Pausa / Reanudar / Fin con las MISMAS funciones del bot y
  source_channel = crm_lab; un segundo Iniciar no duplica.
- Referencias: una sesion abierta por el bot se continua y se cambia desde el CRM
  sin duplicar (nunca dos activas); Cerrar prendas valida el pendiente de la talla
  y pide confirmacion si lo supera.
- Las filas del CRM son identicas a las del bot salvo el canal, asi Nomina y
  Produccion dan lo mismo vengan de donde vengan.
- Todo queda en la bitacora; nada de otra empresa se toca.
"""
from __future__ import annotations

import asyncio
import importlib
import tempfile
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

pgserver = pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.api.v1.endpoints import company_bots_v1 as bot  # noqa: E402
from app.api.v1.endpoints import references_v1 as refs  # noqa: E402
from app.services import crm_lab as svc  # noqa: E402
from app.services import references_v2 as rv2  # noqa: E402
from tests.test_brand_pg import BASE_SCHEMA  # noqa: E402

# Columnas como en produccion (las que usan el bot y el CRM).
EXTRA_SCHEMA = """
CREATE TABLE IF NOT EXISTS employees (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL REFERENCES companies(id),
  full_name varchar(180) NOT NULL, status varchar(30) NOT NULL DEFAULT 'active', employee_type varchar(50) NOT NULL DEFAULT 'operator',
  role varchar(80) NOT NULL DEFAULT 'operator', telegram_user_id varchar(120) NULL);
CREATE TABLE IF NOT EXISTS workforce_attendance_events (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL REFERENCES companies(id),
  employee_id uuid NOT NULL REFERENCES employees(id), event_type varchar(80) NOT NULL, event_label varchar(180) NOT NULL, employee_name varchar(180),
  employee_role varchar(80), status_after varchar(40) NOT NULL, source varchar(80) NOT NULL DEFAULT 'client', notes text,
  created_at timestamptz NOT NULL DEFAULT now(), module_code varchar(80) NOT NULL DEFAULT 'workforce', source_channel varchar(80) NOT NULL DEFAULT 'client',
  source_ref varchar(180), detail text, payload_json jsonb NOT NULL DEFAULT '{}'::jsonb, metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  occurred_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS workforce_attendance_status (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL REFERENCES companies(id),
  employee_id uuid NOT NULL REFERENCES employees(id), status varchar(40) NOT NULL DEFAULT 'not_started', last_event_type varchar(80),
  last_event_at timestamptz, updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE (company_id, employee_id))
"""


def _migration(name: str) -> list[str]:
    statements: list[str] = []

    class Op:
        def execute(self, sql):
            statements.append(str(sql))

    module = importlib.import_module(f"migrations.versions.{name}")
    module.op = Op()
    module.upgrade()
    assert len(module.revision) <= 32
    return statements


@pytest.fixture(scope="module")
def pg_url():
    folder = tempfile.mkdtemp(prefix="cx_pg_crm_")
    server = pgserver.get_server(folder, cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            for stmt in [s for s in (BASE_SCHEMA + ";" + EXTRA_SCHEMA).split(";") if s.strip()]:
                await conn.execute(text(stmt))
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as db:  # las tablas del bot y de referencias, como las crea la app
            real = db.execute

            async def no_ext(stmt, *args, **kwargs):  # pgserver no trae pgcrypto; gen_random_uuid ya es nativo
                if "CREATE EXTENSION" in str(stmt):
                    return None
                return await real(stmt, *args, **kwargs)

            db.execute = no_ext
            await bot.ensure_company_bot_storage(db)
            db.execute = real
            await refs.ensure_storage(db)
            await db.commit()
        async with engine.begin() as conn:
            for stmt in _migration("024e_reference_cuts") + _migration("024g_ref_op_order") + _migration("024h_ref_change_log") + _migration("024p_crm_lab") + _migration("024p_crm_lab"):  # 024p idempotente
                await conn.execute(text(stmt))
        await engine.dispose()

    asyncio.run(setup())
    yield url


def run(url, fn):
    async def go():
        engine = create_async_engine(url)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with maker() as db:
                return await fn(db)
        finally:
            await engine.dispose()

    return asyncio.run(go())


async def company(db, name: str, on: bool = True) -> str:
    cid = str(uuid.uuid4())
    await db.execute(text("INSERT INTO companies (id, name, slug, settings_json) VALUES (CAST(:i AS uuid), :n, :s, '{}'::jsonb)"),
                     {"i": cid, "n": name, "s": name.lower() + cid[:4]})
    await db.execute(text("INSERT INTO modules (code, name, category) VALUES ('references', 'Referencias', 'x') ON CONFLICT (code) DO NOTHING"))
    await db.execute(text("""INSERT INTO company_modules (company_id, module_id, enabled, settings)
        SELECT CAST(:i AS uuid), id, true, CAST(:s AS jsonb) FROM modules WHERE code = 'references'"""),
                     {"i": cid, "s": '{"crm_velvet_lab": true}' if on else "{}"})
    await db.commit()
    return cid


async def employee(db, cid: str, name: str, telegram: str = "") -> str:
    eid = (await db.execute(text("""INSERT INTO employees (company_id, full_name, telegram_user_id) VALUES (CAST(:c AS uuid), :n, NULLIF(:t, ''))
        RETURNING id::text"""), {"c": cid, "n": name, "t": telegram})).scalar_one()
    await db.commit()
    return eid


async def reference(db, cid: str, name: str, sizes=("S", "M", "L"), cut: int = 10) -> dict:
    ids = {}
    for size in sizes:
        rid = str(uuid.uuid4())
        await db.execute(text("""INSERT INTO product_references (id, company_id, name, size, initial_quantity, bot_active)
            VALUES (:i, :c, :n, :s, 0, true)"""), {"i": rid, "c": cid, "n": name, "s": size})
        ids[size] = rid
    await db.commit()
    await rv2.add_movements(db, cid, [{"reference_id": ids[s], "kind": "ingreso", "size": s, "quantity": cut, "event_date": date.today().isoformat()}
                                      for s in sizes], "prueba")
    await rv2.sync_meta(db, cid, "prueba")  # meta = suma de los cortes (como Referencias v2)
    return ids


def code(exc_info) -> str:
    return exc_info.value.code


# ---------------------------------------------------------------- PIN
def test_pin_correcto_incorrecto_y_bloqueo(pg_url):
    async def go(db):
        cid = await company(db, "VelvetPin")
        ana = await employee(db, cid, "Ana")
        with pytest.raises(svc.CrmError) as e:
            await svc.check_pin(db, cid, ana, "1234")
        assert code(e) == "sin_pin" and e.value.status == 403, "sin PIN: pide tu PIN al administrador"
        with pytest.raises(svc.CrmError) as e:
            await svc.set_pin(db, cid, ana, "12a4", "dueña")
        assert code(e) == "pin_de_4_digitos"
        await svc.set_pin(db, cid, ana, "2468", "dueña")
        stored = (await db.execute(text("SELECT pin_hash FROM employee_crm_pins WHERE employee_id::text = :e"), {"e": ana})).scalar_one()
        assert "2468" not in stored and stored.startswith("$2"), "solo el hash"
        assert (await svc.check_pin(db, cid, ana, "2468"))["employee_id"] == ana
        for left in (4, 3, 2, 1):
            with pytest.raises(svc.CrmError) as e:
                await svc.check_pin(db, cid, ana, "0000")
            assert code(e) == "pin_incorrecto" and e.value.extra["left"] == left
        with pytest.raises(svc.CrmError) as e:
            await svc.check_pin(db, cid, ana, "0000")
        assert code(e) == "pin_bloqueado" and e.value.status == 423 and e.value.extra["seconds"] == 300
        with pytest.raises(svc.CrmError) as e:
            await svc.check_pin(db, cid, ana, "2468")
        assert code(e) == "pin_bloqueado", "bloqueado aun con el PIN correcto"
        later = datetime.now(timezone.utc) + timedelta(minutes=5, seconds=2)
        assert (await svc.check_pin(db, cid, ana, "2468", now=later))["employee_id"] == ana, "a los 5 minutos vuelve a entrar"
        # reiniciar el PIN desbloquea y cambia el PIN
        await svc.set_pin(db, cid, ana, "1357", "dueña")
        with pytest.raises(svc.CrmError):
            await svc.check_pin(db, cid, ana, "2468")
        assert (await svc.check_pin(db, cid, ana, "1357"))["employee_id"] == ana
        status = await svc.pin_status(db, cid)
        assert status[ana]["has_pin"] is True
        log = (await db.execute(text("SELECT action, count(*) FROM crm_lab_log WHERE company_id::text = :c GROUP BY 1"), {"c": cid})).all()
        assert dict(log)["pin_fallido"] == 6 and dict(log)["pin_asignado"] == 2
        await svc.clear_pin(db, cid, ana, "dueña")
        with pytest.raises(svc.CrmError) as e:
            await svc.check_pin(db, cid, ana, "1357")
        assert code(e) == "sin_pin"

    run(pg_url, go)


def test_pin_y_colaborador_de_otra_empresa(pg_url):
    async def go(db):
        a = await company(db, "VelvetA")
        b = await company(db, "OtraB")
        eb = await employee(db, b, "Beto")
        with pytest.raises(svc.CrmError) as e:
            await svc.set_pin(db, a, eb, "1111", "dueña de A")
        assert e.value.status == 404, "no se asigna PIN a un colaborador de otra empresa"
        await svc.set_pin(db, b, eb, "1111", "dueña de B")
        with pytest.raises(svc.CrmError) as e:
            await svc.check_pin(db, a, eb, "1111")
        assert e.value.status == 404
        assert eb not in await svc.pin_status(db, a)

    run(pg_url, go)


def test_token_del_colaborador_es_de_esa_empresa():
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    token = svc.employee_token(a, "e1", "CRM")
    assert svc.employee_from_token(a, token) == "e1"
    for bad in (lambda: svc.employee_from_token(b, token), lambda: svc.employee_from_token(a, "basura"), lambda: svc.employee_from_token(a, "")):
        with pytest.raises(svc.CrmError) as e:
            bad()
        assert e.value.status == 401
    assert svc.EMPLOYEE_TOKEN_MINUTES <= 5, "el token corto vence rapido"


# ---------------------------------------------------------------- turno
def test_turno_con_las_mismas_funciones_del_bot(pg_url):
    async def go(db):
        cid = await company(db, "VelvetTurno")
        ana = await employee(db, cid, "Ana")
        refs_ = await reference(db, cid, "PANT SET")
        out = await svc.act(db, cid, ana, "start_shift", {}, "CRM VELVET-LAB", "10.0.0.1", "tab-1")
        assert out["status"] == "working"
        with pytest.raises(svc.CrmError) as e:
            await svc.act(db, cid, ana, "start_shift", {}, "CRM", "", "")
        assert code(e) == "turno_ya_iniciado", "un segundo Iniciar no duplica"
        await db.rollback()
        assert (await svc.act(db, cid, ana, "pause", {}, "CRM"))["status"] == "on_break"
        with pytest.raises(svc.CrmError):
            await svc.act(db, cid, ana, "pause", {}, "CRM")
        await db.rollback()
        assert (await svc.act(db, cid, ana, "resume", {}, "CRM"))["status"] == "working"
        await svc.act(db, cid, ana, "start_reference", {"reference_id": refs_["M"]}, "CRM")
        out = await svc.act(db, cid, ana, "end_shift", {}, "CRM")
        assert out["status"] == "sin_turno" and out["reference"] is None
        events = (await db.execute(text("""SELECT event_type, status_after, source, source_channel, source_ref, metadata_json->>'source' AS ms,
            metadata_json->>'ip' AS ip FROM workforce_attendance_events WHERE employee_id::text = :e ORDER BY occurred_at, created_at"""), {"e": ana})).mappings().all()
        assert [(r["event_type"], r["status_after"]) for r in events] == [
            ("check_in", "working"), ("break_start", "on_break"), ("break_end", "working"), ("check_out", "checked_out")]
        assert {r["source"] for r in events} == {"crm_lab"} and {r["source_channel"] for r in events} == {"crm_lab"}
        assert events[0]["source_ref"] == "crm_lab:check_in" and events[0]["ms"] == "crm_lab" and events[0]["ip"] == "10.0.0.1"
        sess = (await db.execute(text("SELECT status, source_channel, ended_at FROM reference_work_sessions WHERE employee_id = :e"), {"e": ana})).mappings().all()
        assert [(s["status"], s["source_channel"]) for s in sess] == [("ended_with_shift", "crm_lab")] and sess[0]["ended_at"]
        actions = (await db.execute(text("SELECT action, panel_user, device FROM crm_lab_log WHERE employee_id::text = :e ORDER BY created_at"), {"e": ana})).all()
        assert [a[0] for a in actions] == ["start_shift", "pause", "resume", "start_reference", "end_shift"]
        assert actions[0][1] == "CRM VELVET-LAB" and actions[0][2] == "tab-1", "quien, cuando y desde donde"
        with pytest.raises(svc.CrmError) as e:
            await svc.act(db, cid, ana, "start_reference", {"reference_id": refs_["M"]}, "CRM")
        assert code(e) == "inicia_tu_turno"

    run(pg_url, go)


def test_sesion_del_bot_se_continua_y_cambia_sin_duplicar(pg_url):
    async def go(db):
        cid = await company(db, "VelvetBot")
        ana = await employee(db, cid, "Ana", telegram="555")
        pant = await reference(db, cid, "PANT SET")
        jacket = await reference(db, cid, "Mystic jacket", sizes=("S",))
        emp = await bot.employee_by_telegram(db, cid, "555")
        # El bot inicia turno y referencia (como hoy)
        await bot.insert_attendance_event(db, company_id=cid, employee=emp, event_type="check_in", event_label="Inicio de turno", status_after="working")
        await bot.open_reference_session(db, company_id=cid, employee=emp, telegram_user_id="555",
                                         reference={"id": pant["S"], "name": "PANT SET", "size": "S"}, close_status="closed_by_new_start")
        await db.commit()
        person = await svc.person(db, cid, ana)
        assert person["status"] == "working" and person["reference"]["name"] == "PANT SET", "el CRM ve la sesion del bot"
        assert {s["size"] for s in person["sizes"]} == {"S", "M", "L"}
        with pytest.raises(svc.CrmError) as e:
            await svc.act(db, cid, ana, "start_shift", {}, "CRM")
        assert code(e) == "turno_ya_iniciado", "el turno del bot sigue, no se abre otro"
        await db.rollback()
        with pytest.raises(svc.CrmError) as e:
            await svc.act(db, cid, ana, "switch_reference", {"reference_id": pant["S"]}, "CRM")
        assert code(e) == "ya_en_esa_referencia"
        await db.rollback()
        out = await svc.act(db, cid, ana, "switch_reference", {"reference_id": jacket["S"]}, "CRM")
        assert out["reference"]["name"] == "Mystic jacket"
        rows = (await db.execute(text("SELECT reference_name, status, source_channel FROM reference_work_sessions WHERE employee_id = :e ORDER BY started_at"),
                                 {"e": ana})).all()
        assert [tuple(r) for r in rows] == [("PANT SET", "switched", "telegram"), ("Mystic jacket", "active", "crm_lab")]
        active = (await db.execute(text("SELECT count(*) FROM reference_work_sessions WHERE employee_id = :e AND status = 'active'"), {"e": ana})).scalar_one()
        assert active == 1, "nunca dos sesiones activas"
        ev = (await db.execute(text("""SELECT detail, metadata_json->>'previous_reference_name' FROM workforce_attendance_events
            WHERE employee_id::text = :e AND event_type = 'reference_switch'"""), {"e": ana})).one()
        assert ev[0] == "Cambio de referencia: PANT SET → Mystic jacket" and ev[1] == "PANT SET", "el mismo evento que deja el bot"
        # y el bot ve la sesion abierta por el CRM
        assert (await bot.active_reference_session(db, cid, ana))["reference_name"] == "Mystic jacket"
        # Fin de turno desde el bot cierra la del CRM
        await bot.insert_attendance_event(db, company_id=cid, employee=emp, event_type="check_out", event_label="Fin", status_after="checked_out")
        await bot.close_active_reference_session(db, cid, ana, "ended_with_shift")
        await db.commit()
        assert (await svc.person(db, cid, ana))["status"] == "sin_turno"

    run(pg_url, go)


def test_cerrar_prendas_valida_el_pendiente_de_la_talla(pg_url):
    async def go(db):
        cid = await company(db, "VelvetCierre")
        ana = await employee(db, cid, "Ana")
        pant = await reference(db, cid, "PANT SET", cut=10)
        await svc.act(db, cid, ana, "start_shift", {"reference_id": pant["M"]}, "CRM")
        person = await svc.person(db, cid, ana)
        assert person["reference"]["name"] == "PANT SET", "Iniciar turno con referencia inicial"
        assert {s["size"]: s["pending"] for s in person["sizes"]} == {"S": 10, "M": 10, "L": 10}
        out = await svc.act(db, cid, ana, "close", {"size_reference_id": pant["M"], "quantity": 4}, "CRM")
        assert {s["size"]: s["pending"] for s in out["sizes"]}["M"] == 6
        with pytest.raises(svc.CrmError) as e:
            await svc.act(db, cid, ana, "close", {"size_reference_id": pant["M"], "quantity": 7}, "CRM")
        assert code(e) == "supera_el_pendiente" and e.value.extra == {"pending": 6}
        await db.rollback()
        for bad in (0, -1, "x", None):
            with pytest.raises(svc.CrmError) as e:
                await svc.act(db, cid, ana, "close", {"size_reference_id": pant["M"], "quantity": bad}, "CRM")
            assert code(e) == "cantidad_invalida"
            await db.rollback()
        out = await svc.act(db, cid, ana, "close", {"size_reference_id": pant["M"], "quantity": 7, "confirm": True}, "CRM")
        assert {s["size"]: s["pending"] for s in out["sizes"]}["M"] == 0
        closures = (await db.execute(text("""SELECT size, quantity_finished, source_channel, reference_name, telegram_user_id FROM reference_production_closures
            WHERE employee_id = :e ORDER BY closed_at, created_at"""), {"e": ana})).all()
        assert [tuple(c) for c in closures] == [("M", 4, "crm_lab", "PANT SET", ""), ("M", 7, "crm_lab", "PANT SET", "")]
        detail = (await db.execute(text("SELECT detail FROM crm_lab_log WHERE employee_id::text = :e AND action = 'close' ORDER BY created_at"), {"e": ana})).scalars().all()
        assert detail[-1].endswith("(pendiente 6, confirmado)")
        # Produccion (referencias v2) cuenta las prendas del CRM igual que las del bot
        groups = await rv2.reference_groups(db, cid)
        m = next(line for g in groups for line in g["lines"] if line.get("reference_id") == pant["M"])
        assert m["produced"] == 11

    run(pg_url, go)


def test_filas_del_crm_iguales_a_las_del_bot_salvo_el_canal(pg_url):
    """Nomina y Produccion leen estas tablas sin filtrar por canal: misma secuencia,
    mismas filas (tipo, estado, referencia, talla, cantidad)."""
    async def go(db):
        cid = await company(db, "VelvetIgual")
        tele = await employee(db, cid, "Por bot", telegram="777")
        crm = await employee(db, cid, "Por CRM")
        pant = await reference(db, cid, "PANT SET")
        emp = await bot.employee_by_telegram(db, cid, "777")
        ref_m = await bot.reference_by_id(db, cid, pant["M"])
        await bot.insert_attendance_event(db, company_id=cid, employee=emp, event_type="check_in", event_label="Inicio de turno", status_after="working")
        await bot.open_reference_session(db, company_id=cid, employee=emp, telegram_user_id="777", reference=ref_m, close_status="closed_by_new_start")
        await bot.save_production_close(db, company_id=cid, employee=emp, telegram_user_id="777", reference=ref_m, quantity_finished=3)
        await bot.insert_attendance_event(db, company_id=cid, employee=emp, event_type="check_out", event_label="Finalización de turno", status_after="checked_out")
        await bot.close_active_reference_session(db, cid, tele, "ended_with_shift")
        await db.commit()
        await svc.act(db, cid, crm, "start_shift", {}, "CRM")
        await svc.act(db, cid, crm, "start_reference", {"reference_id": pant["M"]}, "CRM")
        await svc.act(db, cid, crm, "close", {"size_reference_id": pant["M"], "quantity": 3}, "CRM")
        await svc.act(db, cid, crm, "end_shift", {}, "CRM")

        async def shape(eid):
            ev = (await db.execute(text("""SELECT event_type, status_after, module_code FROM workforce_attendance_events WHERE employee_id::text = :e
                ORDER BY occurred_at, created_at"""), {"e": eid})).all()
            se = (await db.execute(text("SELECT reference_id, reference_name, status FROM reference_work_sessions WHERE employee_id = :e"), {"e": eid})).all()
            cl = (await db.execute(text("SELECT reference_id, reference_name, size, quantity_finished FROM reference_production_closures WHERE employee_id = :e"),
                                   {"e": eid})).all()
            st = await bot.workforce_status(db, cid, eid)
            return [tuple(r) for r in ev], [tuple(r) for r in se], [tuple(r) for r in cl], st

        assert await shape(tele) == await shape(crm)

    run(pg_url, go)


def test_tablero_en_vivo_y_lista(pg_url):
    async def go(db):
        cid = await company(db, "VelvetVivo")
        other = await company(db, "OtraVivo")
        ana = await employee(db, cid, "Ana")
        bea = await employee(db, cid, "Bea")
        await employee(db, cid, "Caro")
        await employee(db, other, "Ajena")
        pant = await reference(db, cid, "PANT SET")
        await svc.set_pin(db, cid, ana, "1234", "dueña")
        await svc.act(db, cid, ana, "start_shift", {"reference_id": pant["S"]}, "CRM")
        await svc.act(db, cid, bea, "start_shift", {}, "CRM")
        await svc.act(db, cid, bea, "pause", {}, "CRM")
        board = await svc.team(db, cid)
        assert board["working"] == 1 and board["paused"] == 1
        by = {p["name"]: p for p in board["people"]}
        assert set(by) == {"Ana", "Bea", "Caro"}, "solo esa empresa"
        assert by["Ana"]["status"] == "working" and by["Ana"]["reference_name"] == "PANT SET" and by["Ana"]["elapsed_minutes"] == 0
        assert by["Ana"]["has_pin"] is True and by["Caro"]["has_pin"] is False
        assert by["Bea"]["status"] == "on_break" and by["Caro"]["status"] == "sin_turno"
        assert [p["name"] for p in board["live"]] == ["Ana", "Bea"]
        for p in board["people"]:
            assert not any("per_person" in k or "productiv" in k for k in p), "nunca metricas por persona"
        refs_ = await svc.references(db, cid)
        assert [r["name"] for r in refs_] == ["PANT SET"]

    run(pg_url, go)


def test_interruptor_apagado(pg_url):
    async def go(db):
        on = await company(db, "VelvetOn")
        off = await company(db, "OtraOff", on=False)
        assert await svc.is_on(db, on) is True
        assert await svc.is_on(db, off) is False
        await db.execute(text("""UPDATE company_modules SET enabled = false WHERE company_id::text = :c"""), {"c": on})
        await db.commit()
        assert await svc.is_on(db, on) is False, "con el modulo apagado tampoco"

    run(pg_url, go)
