"""Horario de la semana (interruptor work_schedule, 071A) contra Postgres REAL (pgserver).

- Horario 1 y 2 por operacion, selector por persona, copia a la semana siguiente, dia puntual
  solo en su semana, Virginia (ET) y Alabama (CT).
- Bot: aviso 15 min despues de SU salida (no antes, no dos veces), Finalizar ahora, Sigo
  trabajando con motivo y repregunta a las 2 h, sin respuesta 30 min -> Fuera de horario y un solo
  aviso al supervisor (al dueño si no hay supervisor); turnos viejos quedan Fuera de horario en
  silencio.
- Cierre en el portal: cualquier turno abierto, motivo y confirmacion obligatorios, hora editada,
  auditoria con el horario usado; en el panel del lider solo salida programada u hora actual.
- Otra empresa (sin el interruptor): todo igual que antes.
Si pgserver no esta instalado, se salta."""
from __future__ import annotations

import importlib
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

pytest.importorskip("pgserver")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.api.v1.endpoints import bots  # noqa: E402
from app.api.v1.endpoints import open_shifts as routes  # noqa: E402
from app.api.v1.endpoints import payroll as core  # noqa: E402
from app.api.v1.endpoints import work_schedule as ws_routes  # noqa: E402
from app.services import ddl_once, lider_pin, open_shift_alert  # noqa: E402
from app.services import work_schedule as ws  # noqa: E402
from tests.test_bot_punch_open_shift_pg import _company, _employee, _open_shift, _prime_checks, pg_url  # noqa: E402,F401

UTC = timezone.utc
WEEK = date(2026, 11, 9)  # lunes
MONDAY_END_VA = datetime(2026, 11, 9, 22, 0, tzinfo=UTC)  # 5:00 p. m. ET
OWNER = {"role": "owner", "name": "Dueña VOLTAGE", "user_id": None, "can_edit": True}
SETTINGS = {"open_shift_alert": True, "work_locations": True, "work_schedule": True}
H1 = {"days": [0, 1, 2, 3, 4], "start": "07:00", "end": "17:00", "lunch_start": "12:00", "lunch_end": "13:00"}
H2 = {"days": [0, 1, 2, 3, 4, 5], "start": "09:00", "end": "19:00"}


def _sql_025e() -> list[str]:
    out: list[str] = []

    class Op:
        def execute(self, sql):
            out.append(str(sql))

    module = importlib.import_module("migrations.versions.025e_work_schedule")
    module.op = Op()
    module.upgrade()
    return out


@pytest.fixture()
async def maker(pg_url):  # noqa: F811
    engine = create_async_engine(pg_url, pool_size=20, max_overflow=10)
    ddl_once.reset()
    await _prime_checks()
    async with engine.begin() as conn:
        for _ in range(2):  # idempotente: correrla dos veces no falla
            for stmt in _sql_025e():
                await conn.execute(text(stmt))
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ddl_once.reset()
    await engine.dispose()


async def _place(db, cid: str, name: str, tz: str) -> str:
    pid = (await db.execute(text("INSERT INTO work_locations (company_id, name, timezone) VALUES (CAST(:c AS uuid), :n, :t) RETURNING id::text"),
                            {"c": cid, "n": name, "t": tz})).scalar()
    await db.commit()
    return pid


async def _setup(maker, settings=SETTINGS):
    cid = str(uuid.uuid4())
    async with maker() as db:
        await _company(db, cid, settings)
        va = await _place(db, cid, "Virginia", "America/New_York")
        al = await _place(db, cid, "Alabama", "America/Chicago")
    return cid, va, al


class Outbox:
    def __init__(self):
        self.sent: list[tuple[str, str, dict | None]] = []

    async def send(self, chat, message, reply_markup=None):
        self.sent.append((chat, message, reply_markup))

    async def language_of(self, tg):
        return "en" if tg.startswith("9") else "es"

    def to(self, chat):
        return [m for c, m, _ in self.sent if c == chat]


async def _run(db, cid, now, box):
    return await ws.run_company(db, cid, send=box.send, language_of=box.language_of, now=now)


async def _closes(db, cid):
    rows = (await db.execute(text("""
        SELECT employee_name, end_at, note, closed_by, reason_code, reason_detail, schedule_json, closed_via
        FROM shift_manual_closes WHERE company_id = CAST(:c AS uuid) ORDER BY closed_at, end_at
    """), {"c": cid})).mappings().all()
    return [dict(r) for r in rows]


# ------------------------------------------------------------ 1) horario de la semana
async def test_horario_1_y_2_selector_copia_semana_siguiente_y_dia_puntual(maker):
    cid, va, al = await _setup(maker)
    async with maker() as db:
        empty = await ws.week(db, cid, va, WEEK)
        assert not empty["configured"] and empty["slots"][0]["start"] == "07:00", "sin guardar: ejemplo para llenar, sin preguntar a nadie"
        friday = {**H1, "overrides": {"2026-11-13": {"start": "07:00", "end": "13:00"}}}
        saved = await ws.save_week(db, cid, va, WEEK, [friday, H2], actor="Dueña", actor_user_id=None)
        assert saved["source"] == "week" and [s["name"] for s in saved["slots"]] == ["Horario 1", "Horario 2"]
        nxt = await ws.week(db, cid, va, WEEK + timedelta(days=7))
        assert nxt["configured"] and nxt["source"] == "copied" and nxt["copied_from"] == "2026-11-09", "la semana siguiente copia sola"
        assert nxt["slots"][0]["overrides"] == {}, "el viernes puntual era solo de esa semana"
        far = await ws.week(db, cid, va, WEEK + timedelta(days=28))
        assert far["source"] == "copied" and len(far["slots"]) == 2
        changed = await ws.save_week(db, cid, va, WEEK + timedelta(days=7), [{**H1, "end": "16:00"}], actor="Dueña", actor_user_id=None)
        assert changed["source"] == "week" and len(changed["slots"]) == 1
        assert (await ws.week(db, cid, va, WEEK))["slots"][1]["start"] == "09:00", "cambiar una semana no toca la anterior"
        assert not (await ws.week(db, cid, al, WEEK))["configured"], "Alabama tiene su propio horario"

        ana = await _employee(db, cid, "Ana Virginia", tg="101", place=va)
        beto = await _employee(db, cid, "Beto Virginia", tg="102", place=va)
        assert await ws.set_employee_slot(db, cid, beto, 2, actor="Dueña") == 2
        with pytest.raises(ws.Invalid):
            await ws.set_employee_slot(db, cid, beto, 0, actor="Dueña")
        with pytest.raises(ws.Invalid):
            await ws.set_employee_slot(db, cid, str(uuid.uuid4()), 1, actor="Dueña")
        people = {p["name"]: p["slot"] for p in await ws.location_people(db, cid, va)}
        assert people == {"Ana Virginia": 1, "Beto Virginia": 2}, "por defecto Horario 1"

        # cada persona se evalua con SU horario
        await _open_shift(db, cid, ana, datetime(2026, 11, 9, 12, 0, tzinfo=UTC))
        await _open_shift(db, cid, beto, datetime(2026, 11, 9, 14, 0, tzinfo=UTC))
        marks = await ws.flags(db, cid, datetime(2026, 11, 9, 20, 0, tzinfo=UTC))
        assert marks[ana]["scheduled_end_at"] == "2026-11-09T22:00:00Z" and marks[ana]["scheduled_end_label"] == "5:00 p. m."
        assert marks[beto]["scheduled_end_at"] == "2026-11-10T00:00:00Z" and marks[beto]["slot_name"] == "Horario 2"


async def test_alabama_usa_la_hora_central(maker):
    cid, _va, al = await _setup(maker)
    async with maker() as db:
        await ws.save_week(db, cid, al, WEEK, [H1], actor="Dueña", actor_user_id=None)
        carla = await _employee(db, cid, "Carla Alabama", tg="201", place=al)
        await _open_shift(db, cid, carla, datetime(2026, 11, 9, 13, 0, tzinfo=UTC))  # 7:00 a. m. CT
        marks = await ws.flags(db, cid, datetime(2026, 11, 9, 20, 0, tzinfo=UTC))
        assert marks[carla]["scheduled_end_at"] == "2026-11-09T23:00:00Z", "5:00 p. m. CT = 23:00 UTC"


# ------------------------------------------------------------ 2) aviso del bot
async def test_aviso_a_los_15_min_sigo_trabajando_repregunta_y_fuera_de_horario_con_aviso_unico(maker):
    cid, va, _al = await _setup(maker)
    async with maker() as db:
        await ws.save_week(db, cid, va, WEEK, [H1], actor="Dueña", actor_user_id=None)
        ana = await _employee(db, cid, "Ana", tg="101", place=va)
        dan = await _employee(db, cid, "Dan", tg="901", place=va)
        sup = await _employee(db, cid, "Sofía Supervisora", role="supervisor", tg="501", place=va)
        await _employee(db, cid, "Dueño", role="owner", tg="601")
        start = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
        for eid in (ana, dan):
            await _open_shift(db, cid, eid, start)
        box = Outbox()
        await _run(db, cid, MONDAY_END_VA + timedelta(minutes=14), box)
        assert box.sent == [], "antes de los 15 min no pregunta"
        await _run(db, cid, MONDAY_END_VA + timedelta(minutes=15), box)
        assert box.to("101") == ["⏰ Tu turno terminó a las 5:00 p. m. ¿Ya saliste?"]
        assert box.to("901") == ["⏰ Your shift ended at 5:00 PM. Did you already leave?"], "en el idioma de cada persona"
        assert box.sent[0][2] == ws.prompt_keyboard("es")
        await _run(db, cid, MONDAY_END_VA + timedelta(minutes=20), box)
        assert len(box.sent) == 2, "una sola vez"

        # Ana: Sigo trabajando + motivo -> se repregunta a las 2 h
        t = MONDAY_END_VA + timedelta(minutes=25)
        assert await ws.answer(db, cid, ana, "reason", now=t)
        assert await ws.save_reason(db, cid, ana, "ok", now=t) is None, "motivo muy corto"
        saved = await ws.save_reason(db, cid, ana, "Termino el pedido de Lowe's", now=t)
        assert saved["next_ask_at"] == "2026-11-10T00:25:00Z", "se repregunta en 2 h"

        # Dan: sin respuesta 30 min -> Fuera de horario y UN aviso al supervisor de su operacion
        await _run(db, cid, MONDAY_END_VA + timedelta(minutes=45), box)
        assert len(box.to("501")) == 1 and "Fuera de horario" in box.to("501")[0] and "Dan" in box.to("501")[0]
        assert box.to("601") == [], "hay supervisor: el dueño no recibe"
        marks = await ws.flags(db, cid, MONDAY_END_VA + timedelta(minutes=46))
        assert marks[dan]["out_of_schedule"] and not marks[ana]["out_of_schedule"]
        assert marks[ana]["reason"] == "Termino el pedido de Lowe's"

        # 2 h despues del motivo: Ana recibe otra pregunta; no responde -> Fuera de horario, aviso al supervisor
        await _run(db, cid, t + timedelta(hours=2) - timedelta(minutes=1), box)
        assert len(box.to("101")) == 1
        await _run(db, cid, t + timedelta(hours=2), box)
        assert len(box.to("101")) == 2, "repregunta a las 2 h"
        await _run(db, cid, t + timedelta(hours=2, minutes=31), box)
        assert len(box.to("501")) == 2 and "Ana" in box.to("501")[1]
        # nada mas para nadie
        before = len(box.sent)
        await _run(db, cid, t + timedelta(hours=6), box)
        assert len(box.sent) == before, "el aviso al supervisor es una sola vez por turno"
        assert sup


async def test_sin_supervisor_avisa_al_dueno_y_turnos_viejos_quedan_en_silencio(maker):
    cid, va, al = await _setup(maker)
    async with maker() as db:
        for place in (va, al):
            await ws.save_week(db, cid, place, WEEK, [H1], actor="Dueña", actor_user_id=None)
        await _employee(db, cid, "Dueño", role="owner", tg="601")
        hector = await _employee(db, cid, "Hector", tg="301", place=al)
        eva = await _employee(db, cid, "Eva", tg="302", place=va)
        await _open_shift(db, cid, hector, datetime(2026, 11, 9, 13, 0, tzinfo=UTC))  # lunes, 53 h despues
        await _open_shift(db, cid, eva, datetime(2026, 11, 11, 12, 0, tzinfo=UTC))
        box = Outbox()
        now = datetime(2026, 11, 11, 18, 0, tzinfo=UTC)
        stats = await _run(db, cid, now, box)
        assert stats["silent"] == 1 and box.sent == [], "un turno de hace dias no dispara mensajes"
        assert (await ws.flags(db, cid, now))[hector]["out_of_schedule"], "pero queda Fuera de horario para cerrarlo"
        await _run(db, cid, datetime(2026, 11, 11, 22, 15, tzinfo=UTC), box)
        await _run(db, cid, datetime(2026, 11, 11, 22, 46, tzinfo=UTC), box)
        assert len(box.to("302")) == 1 and len(box.to("601")) == 1, "sin supervisor: el rol dueño, una vez"
        assert box.to("301") == []


async def test_botones_del_bot_finalizar_ahora_y_sigo_trabajando(maker, monkeypatch):
    cid, va, _al = await _setup(maker)
    async with maker() as db:
        await ws.save_week(db, cid, va, WEEK, [H1], actor="Dueña", actor_user_id=None)
        ana = await _employee(db, cid, "Ana", tg="101", place=va)
        await _open_shift(db, cid, ana, datetime(2026, 11, 9, 12, 0, tzinfo=UTC))
        await _run(db, cid, MONDAY_END_VA + timedelta(minutes=16), Outbox())
        sent: list[str] = []

        async def fake_send(_token, _chat, message, **_kw):
            sent.append(message)

        async def fake_find(_db, _cid, _tg, _user):
            return SimpleNamespace(id=uuid.UUID(ana), full_name="Ana")

        monkeypatch.setattr(bots, "_send_telegram_message", fake_send)
        monkeypatch.setattr(bots, "_find_employee_by_telegram", fake_find)
        bot = SimpleNamespace(company_id=uuid.UUID(cid))
        common = {"bot": bot, "token": "t", "telegram_user_id": "101", "username": None, "chat_id": "101", "language": "es", "send_replies": True}

        item, nxt = await bots._work_schedule_gate_071A(db, update={"update_id": 1, "callback_query": {}}, text_value=ws.CALLBACK_FINISH, **common)
        assert item is None and nxt == "clx:cmd:salida", "Finalizar ahora sigue el flujo normal de Finalizar"
        item, _ = await bots._work_schedule_gate_071A(db, update={"update_id": 2, "callback_query": {}}, text_value=ws.CALLBACK_WORKING, **common)
        assert item.action == "work_schedule_reason_requested" and sent[-1] == ws.tr("es", "why")
        item, _ = await bots._work_schedule_gate_071A(db, update={"update_id": 3, "message": {}}, text_value="Inventario de bodega", **common)
        assert item.action == "work_schedule_reason_saved" and sent[-1] == ws.tr("es", "thanks")
        item, nxt = await bots._work_schedule_gate_071A(db, update={"update_id": 4, "message": {}}, text_value="hola", **common)
        assert item is None and nxt == "hola", "sin motivo pendiente el texto sigue como siempre"
        assert (await ws.flags(db, cid, MONDAY_END_VA + timedelta(minutes=30)))[ana]["reason"] == "Inventario de bodega"


# ------------------------------------------------------------ 3) cerrar turnos con motivo
async def test_portal_cierra_cualquier_turno_con_motivo_doble_confirmacion_y_auditoria(maker):
    cid, va, _al = await _setup(maker)
    now = datetime.now(UTC)
    async with maker() as db:
        await ws.save_week(db, cid, va, ws.week_start(now.date()), [{**H1, "days": [0, 1, 2, 3, 4, 5, 6]}], actor="Dueña", actor_user_id=None)
        short = await _employee(db, cid, "Turno Corto", tg="111", place=va)
        await _open_shift(db, cid, short, now - timedelta(hours=2))
        listed = await routes.get_open_shifts(uuid.UUID(cid), who=OWNER, db=db)
        assert listed["schedule_mode"] and [s["employee_name"] for s in listed["shifts"]] == ["Turno Corto"], "cualquier turno abierto, no solo > 15 h"
        assert [r["code"] for r in listed["reasons"]] == ["olvido", "salida_real", "otro"]
        row = listed["shifts"][0]
        assert row["default_end_at"] and not row["out_of_schedule"]
        end = (now - timedelta(minutes=30)).replace(microsecond=0)
        for body, msg in (({"end_at": end.isoformat(), "reason_code": "olvido"}, "Confirma"),
                          ({"end_at": end.isoformat(), "confirmed": True}, "motivo"),
                          ({"end_at": end.isoformat(), "confirmed": True, "reason_code": "otro", "reason_detail": "x"}, "detalle")):
            with pytest.raises(HTTPException) as exc:
                await routes.post_close(uuid.UUID(cid), uuid.UUID(short), body=body, who=OWNER, db=db)
            assert exc.value.status_code == 422 and msg in exc.value.detail
        done = await routes.post_close(uuid.UUID(cid), uuid.UUID(short), body={"end_at": end.isoformat(), "confirmed": True, "reason_code": "salida_real",
                                                                              "reason_detail": "la vio el supervisor"}, who=OWNER, db=db)
        assert done["ok"] and done["closed"]["end_at"] == end.isoformat().replace("+00:00", "Z"), "hora editada por el dueño"
        audit = (await _closes(db, cid))[-1]
        assert audit["reason_code"] == "salida_real" and audit["closed_via"] == "portal" and audit["closed_by"] == "Dueña VOLTAGE"
        assert audit["note"] == "Salida real confirmada · la vio el supervisor"
        schedule = audit["schedule_json"] if isinstance(audit["schedule_json"], dict) else json.loads(audit["schedule_json"])
        assert schedule["slot_name"] == "Horario 1" and schedule["timezone"] == "America/New_York"
        ev = (await db.execute(text("""
            SELECT occurred_at, payload_json FROM workforce_attendance_events WHERE company_id = CAST(:c AS uuid) AND event_type = 'check_out'
        """), {"c": cid})).mappings().first()
        payload = ev["payload_json"] if isinstance(ev["payload_json"], dict) else json.loads(ev["payload_json"])
        assert ev["occurred_at"] == end and payload["manual_close"] and payload["closed_by"] == "Dueña VOLTAGE", "Nómina y Reportes leen esta salida"
        assert payload["note"] == "Salida real confirmada · la vio el supervisor", "Reportes: Cerrado por <nombre> · <motivo>"
        verification = await core._cx_verification_context_049D(db, cid)
        assert core._cx_check_shift_049D(verification, "attendance", str(uuid.uuid4()), now - timedelta(hours=2), end, False)[0] == "pay"


async def test_lider_solo_cierra_fuera_de_horario_con_salida_programada_u_hora_actual(maker):
    cid, va, al = await _setup(maker)
    async with maker() as db:
        await ws.save_week(db, cid, va, WEEK, [H1], actor="Dueña", actor_user_id=None)
        ana = await _employee(db, cid, "Ana", tg="101", place=va)
        beto = await _employee(db, cid, "Beto", tg="102", place=va)
        other = await _employee(db, cid, "De Alabama", tg="103", place=al)
        for eid in (ana, beto, other):
            await _open_shift(db, cid, eid, datetime(2026, 11, 9, 12, 0, tzinfo=UTC))
        await _run(db, cid, MONDAY_END_VA + timedelta(minutes=15), Outbox())
        now = MONDAY_END_VA + timedelta(minutes=50)
        await _run(db, cid, now, Outbox())  # Ana y Beto quedan Fuera de horario
        place = {"id": va, "name": "Virginia", "timezone": "America/New_York"}
        leader = {"name": "Líder Virginia", "user_id": None}
        ok = {"confirmed": True, "reason_code": "olvido"}
        cases = [({**ok, "choice": "otra"}, ana, 422), ({"choice": "now", "reason_code": "olvido"}, ana, 422),
                 ({**ok, "choice": "now", "end_at": "2026-11-09T21:00:00Z"}, other, 403)]
        for body, who, status in cases:
            with pytest.raises(lider_pin.Denied) as exc:
                await lider_pin.close_out_of_schedule(db, cid, place, leader, who, body, now=now)
            assert exc.value.status == status
        done = await lider_pin.close_out_of_schedule(db, cid, place, leader, ana, {**ok, "choice": "scheduled", "end_at": "2026-11-09T20:00:00Z"}, now=now)
        assert done["at"].startswith("17:00"), "la salida programada, nunca la hora que mande el navegador"
        done = await lider_pin.close_out_of_schedule(db, cid, place, leader, beto, {**ok, "choice": "now"}, now=now)
        assert done["at"].startswith("17:50")
        audits = await _closes(db, cid)
        assert [a["closed_via"] for a in audits] == ["lider", "lider"] and audits[0]["end_at"] == MONDAY_END_VA
        assert audits[1]["end_at"] == now and audits[0]["closed_by"] == "Líder Virginia"


async def test_lider_no_cierra_un_turno_que_no_esta_fuera_de_horario(maker):
    cid, va, _al = await _setup(maker)
    async with maker() as db:
        await ws.save_week(db, cid, va, WEEK, [H1], actor="Dueña", actor_user_id=None)
        ana = await _employee(db, cid, "Ana", tg="101", place=va)
        await _open_shift(db, cid, ana, datetime(2026, 11, 9, 12, 0, tzinfo=UTC))
        with pytest.raises(lider_pin.Denied) as exc:
            await lider_pin.close_out_of_schedule(db, cid, {"id": va, "name": "Virginia", "timezone": "America/New_York"}, {"name": "L", "user_id": None}, ana,
                                                  {"confirmed": True, "reason_code": "olvido", "choice": "now"}, now=MONDAY_END_VA - timedelta(hours=1))
        assert exc.value.status == 409


# ------------------------------------------------------------ 4) otras empresas
async def test_otra_empresa_sin_interruptor_sigue_igual(maker):
    cid, va, _al = await _setup(maker, {"open_shift_alert": True, "work_locations": True})
    async with maker() as db:
        assert not await ws.is_on(db, cid)
        assert cid not in await ws.companies_on(db)
        ana = await _employee(db, cid, "Ana", tg="101", place=va)
        await _open_shift(db, cid, ana, datetime.now(UTC) - timedelta(hours=2))
        listed = await routes.get_open_shifts(uuid.UUID(cid), who=OWNER, db=db)
        assert "schedule_mode" not in listed and listed["shifts"] == [], "sigue mostrando solo los turnos que pasan el limite"
        with pytest.raises(HTTPException) as exc:
            await routes.post_close(uuid.UUID(cid), uuid.UUID(ana), body={"end_at": datetime.now(UTC).isoformat(), "note": "Olvidó finalizar"}, who=OWNER, db=db)
        assert exc.value.status_code == 400, "un turno corto sigue sin poder cerrarse"
        assert await open_shift_alert.alert_hours(db, cid) == 12
        req = SimpleNamespace(cookies={}, headers={})

        async def no_admin(*_a, **_k):
            return None

        import app.web.admin_v2_routes as admin

        orig = admin._active_session
        admin._active_session = no_admin
        try:
            with pytest.raises(HTTPException) as exc:
                await ws_routes.actor(uuid.UUID(cid), req, authorization=None, db=db)
            assert exc.value.status_code in (401, 403), "sin sesion no entra"
        finally:
            admin._active_session = orig


# ------------------------------------------------------------ 072A: con whatsapp_group_reports, a los 30 min
async def test_aviso_a_los_30_min_con_avisos_whatsapp_uno_por_persona(maker):
    cid, va, _al = await _setup(maker)
    async with maker() as db:
        await ws.save_week(db, cid, va, WEEK, [H1], actor="Dueña", actor_user_id=None)
        ana = await _employee(db, cid, "Ana", tg="101", place=va)
        dan = await _employee(db, cid, "Dan", tg="901", place=va)
        for eid in (ana, dan):
            await _open_shift(db, cid, eid, datetime(2026, 11, 9, 12, 0, tzinfo=UTC))
        box = Outbox()

        async def run(minutes):
            return await ws.run_company(db, cid, send=box.send, language_of=box.language_of,
                                        now=MONDAY_END_VA + timedelta(minutes=minutes), prompt_after=ws.GROUP_REPORTS_PROMPT_MINUTES)

        await run(15)
        await run(29)
        assert box.sent == [], "con el corte de salida a los 30 min, el bot no pregunta antes"
        await run(30)
        assert box.to("101") == ["⏰ Tu turno terminó a las 5:00 p. m. ¿Ya saliste?"] and len(box.to("901")) == 1
        await run(31)
        await run(40)
        assert len(box.sent) == 2, "un solo aviso por persona"
