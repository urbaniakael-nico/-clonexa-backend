"""Avisos automaticos por WhatsApp (whatsapp_group_reports, 072A) contra Postgres REAL (pgserver).

Reloj simulado: lunes 9 nov 2026. Virginia = ET (UTC-5), Alabama = CT (UTC-6); Horario 1 y 2 con
horas distintas en cada operacion.
- Cortes a entrada+30 y salida+30 de cada franja, listas correctas (conectados, ⏸ en pausa, no
  conectados, ya cerraron, siguen conectados con horas), sin directores ni dueños, ES + EN.
- Sin duplicados al volver a correr (reinicio / redeploy = misma base).
- Sabado/domingo solo si hay horario o alguien inicio turno.
- Timesheet: supervisor diario, grupo semanal el viernes, recordatorio de las 9:00 solo si no llego.
- Resumen diario y totales del lunes (regulares y extra FLSA por persona).
- Modo prueba: nada sale a grupos, supervisor ni dueños. Envio con reintentos y 3-6 s entre mensajes.
- Webhook sin cabecera secreta -> 401; configuracion e historial solo dueño/admin; otras empresas igual.
- Telegram "¿Ya saliste?" a los 30 min con el interruptor, a los 15 sin el; uno por persona.
Si pgserver no esta instalado, se salta."""
from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import sys
import tempfile
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

pgserver = pytest.importorskip("pgserver")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.api.v1.endpoints import group_reports as routes  # noqa: E402
from app.services import group_reports as gr  # noqa: E402
from app.services import work_schedule as ws  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("reports_board_seed_gr", ROOT / "tests" / "fixtures" / "reports_board_seed.py")
seed = importlib.util.module_from_spec(spec)
sys.modules["reports_board_seed_gr"] = seed
spec.loader.exec_module(seed)

UTC = timezone.utc
T = seed.T
MONDAY = date(2026, 11, 9)
H1_VA = {"days": [0, 1, 2, 3, 4], "start": "07:00", "end": "15:30"}
H2_VA = {"days": [0, 1, 2, 3, 4], "start": "09:00", "end": "18:00"}
H1_AL = {"days": [0, 1, 2, 3, 4], "start": "06:00", "end": "14:30"}
H2_AL = {"days": [0, 1, 2, 3, 4], "start": "08:00", "end": "17:00"}
OWN, MAIL = "13460000000", "clonexa@example.test"
GROUP_VA, GROUP_AL = "120363000000000001@g.us", "120363000000000002@g.us"
NOEL, OWNER_A, OWNER_J = "17030000001", "17030000002", "17030000003"


def _sql(name: str, only_create: bool = False) -> list[str]:
    out: list[str] = []
    module = importlib.import_module(f"migrations.versions.{name}")
    module.op = SimpleNamespace(execute=lambda sql: out.append(str(sql)))
    module.upgrade()
    return [s for s in out if not only_create or s.strip().upper().startswith("CREATE")]


@pytest.fixture(scope="module")
def pg_url():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="cx_pg_gr_"), cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await seed.create_schema(conn)
            for _ in range(2):  # idempotente: correrla dos veces no falla
                for stmt in _sql("025e_work_schedule", only_create=True) + _sql("025h_wa_group_reports"):
                    await conn.execute(text(stmt))
        await engine.dispose()

    asyncio.run(setup())
    yield url


@pytest.fixture()
async def maker(pg_url):
    engine = create_async_engine(pg_url)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


async def _switch(db, cid: str, on: bool = True, extra: dict | None = None) -> None:
    settings = {"work_locations": True, "work_schedule": True, **({gr.KEY: True} if on else {}), **(extra or {})}
    await db.execute(text("""
        UPDATE company_modules SET settings = CAST(:s AS jsonb)
         WHERE company_id = CAST(:c AS uuid) AND module_id = (SELECT id FROM modules WHERE code = 'workforce')
    """), {"c": cid, "s": json.dumps(settings)})
    await db.commit()


async def _company(db, *, schedules: bool = True, test_mode: bool = True) -> dict:
    cid = await seed.company(db, "VOLTAGE", board=False)
    await _switch(db, cid)
    va = await seed.place(db, cid, "Virginia", "VA", "America/New_York", 1)
    al = await seed.place(db, cid, "Alabama", "AL", "America/Chicago", 2)
    if schedules:
        await ws.save_week(db, cid, va, MONDAY, [H1_VA, H2_VA], actor="Dueña", actor_user_id=None)
        await ws.save_week(db, cid, al, MONDAY, [H1_AL, H2_AL], actor="Dueña", actor_user_id=None)
    await gr.save_config(db, cid, {
        "test_mode": test_mode, "own_number": OWN, "clonexa_email": MAIL,
        "operations": [{"location_id": va, "group_jid": GROUP_VA, "group_name": "VOLTAGE Virginia"},
                       {"location_id": al, "group_jid": GROUP_AL, "group_name": "VOLTAGE Alabama"}],
        "supervisor": {"name": "Noel Dubon", "phone": NOEL, "email": "noel@example.test", "location_id": al},
        "owners": [{"name": "Adriana", "phone": OWNER_A, "email": "adriana@example.test"}, {"name": "Javier", "phone": OWNER_J, "email": "javier@example.test"}],
        "weekly_location_id": va,
    }, actor="Dueña")
    return {"company": cid, "va": va, "al": al}


async def _people(db, ids: dict) -> dict:
    cid, va, al = ids["company"], ids["va"], ids["al"]
    p = {
        "ana": await seed.person(db, cid, "Ana Ruiz", None, va), "beto": await seed.person(db, cid, "Beto Vega", None, va),
        "carlos": await seed.person(db, cid, "Carlos Paz", None, va), "dora": await seed.person(db, cid, "Dora Luz", None, va),
        "director": await seed.person(db, cid, "Diana Directora", None, va, role="director"),
        "owner": await seed.person(db, cid, "Dueño Uno", None, va, role="owner"),
        "elena": await seed.person(db, cid, "Elena Gómez", None, al), "felipe": await seed.person(db, cid, "Felipe Soto", None, al),
        "gabo": await seed.person(db, cid, "Gabo Mena", None, al),
    }
    await ws.set_employee_slot(db, cid, p["dora"], 2, actor="Dueña")
    await ws.set_employee_slot(db, cid, p["gabo"], 2, actor="Dueña")
    # lunes 9: Ana entra 7:05 ET y sale 15:35; Beto entra 7:10 y queda en pausa; Carlos no viene;
    # Dora (H2) 9:02 a 18:01; Elena (AL H1) 6:01 a 14:35 CT; Gabo (AL H2) 8:00 CT y sigue abierto.
    await seed.shift(db, cid, p["ana"], "11-09T12:05", "11-09T20:35")
    await seed.shift(db, cid, p["beto"], "11-09T12:10", None, pause=("11-09T12:20", None))
    await seed.shift(db, cid, p["dora"], "11-09T14:02", "11-09T23:01")
    await seed.shift(db, cid, p["elena"], "11-09T12:01", "11-09T20:35")
    await seed.shift(db, cid, p["gabo"], "11-09T14:00", None)
    return p


async def _notices(db, cid: str) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT n.dedupe_key, n.kind, d.channel, d.destination, d.target, d.subject, d.body, d.attachments, d.status, d.test
        FROM wa_report_notices n JOIN wa_report_deliveries d ON d.notice_id = n.id
        WHERE n.company_id = CAST(:c AS uuid) ORDER BY n.id, d.id
    """), {"c": cid})).mappings().all()
    return [dict(r) for r in rows]


async def _delivery_id(db, cid: str, kind: str, op: str) -> int:
    return int((await db.execute(text("""
        SELECT id FROM wa_report_deliveries WHERE company_id = CAST(:c AS uuid) AND kind = :k AND body LIKE :b ORDER BY id LIMIT 1
    """), {"c": cid, "k": kind, "b": f"%{op}%"})).scalar())


def _bodies(rows, kind):
    return [r["body"] for r in rows if r["kind"] == kind]


# ------------------------------------------------------------ 1) cortes de entrada y salida
@pytest.mark.asyncio
async def test_cortes_por_franja_listas_textos_y_sin_duplicados(maker):
    async with maker() as db:
        ids = await _company(db)
        p = await _people(db, ids)
        cid = ids["company"]
        assert sum((await gr.plan_company(db, cid, T("11-09T12:29"))).values()) == 0, "antes de entrada + 30 no sale nada"
        stats = await gr.plan_company(db, cid, T("11-09T12:30"))
        assert stats["checkin"] == 2, "Virginia H1 (7:30 ET) y Alabama H1 (6:30 CT) caen a las 12:30 UTC"
        rows = await _notices(db, cid)
        va = next(b for b in _bodies(rows, "checkin") if "Virginia" in b)
        assert va == ("[PRUEBA] *VOLTAGE · Virginia · Horario 1 · Entrada*\n"
                      "Lun 09/11 · 7:30 a. m. ET\n"
                      "\n"
                      "❌ *Sin conectar / Not connected (1):*\n"
                      "1. Carlos Paz\n"
                      "\n"
                      "✅ Conectados / Connected: 2 de 3\n"
                      "⏸️ En pausa / On break: 1"), va
        card_row = next(r for r in rows if r["kind"] == "checkin" and "Virginia" in r["body"])
        card = card_row["attachments"][0]
        assert card["kind"] == "card_png" and card["mimetype"] == "image/png" and card_row["channel"] == "whatsapp"
        assert card["card"]["connected"] == [["Ana Ruiz", False], ["Beto Vega", True]] and card["card"]["missing"] == ["Carlos Paz"]
        assert card["card"]["subtitle"] == "Lunes 09/11 · Entrada 7:00 a. m. ET · Corte 7:30 a. m."
        png, name, mime = await gr.render_file(db, cid, {"kind": "card_png", "d": await _delivery_id(db, cid, "checkin", "Virginia"), "i": 0})
        assert png.startswith(b"\x89PNG") and mime == "image/png" and name.startswith("corte_entrada_virginia_2026-11-09")
        with pytest.raises(LookupError):
            await gr.render_file(db, cid, {"kind": "card_png", "d": 999999, "i": 0})
        assert "Diana" not in va and "Dueño" not in va and "Dora" not in va, "sin directores ni dueños; Dora es del Horario 2"
        al = next(b for b in _bodies(rows, "checkin") if "Alabama" in b)
        assert "6:30 a. m. CT" in al and "Connected: 1 de 2" in al and "1. Felipe Soto" in al

        # reiniciar / redesplegar = volver a correr contra la misma base: nada se repite
        for minute in ("11-09T12:30", "11-09T12:31", "11-09T12:59"):
            assert sum((await gr.plan_company(db, cid, T(minute))).values()) == 0
        assert len(_bodies(await _notices(db, cid), "checkin")) == 2

        assert (await gr.plan_company(db, cid, T("11-09T14:30")))["checkin"] == 2, "Horario 2: 9:30 ET y 8:30 CT"
        rows = await _notices(db, cid)
        va2 = next(b for b in _bodies(rows, "checkin") if "Horario 2" in b and "Virginia" in b)
        assert "9:30 a. m. ET" in va2 and "🎉 *Todos conectados / Everyone is clocked in*" in va2 and "Connected: 1 de 1" in va2

        assert (await gr.plan_company(db, cid, T("11-09T21:00")))["checkout"] == 2, "salida H1: 16:00 ET y 15:00 CT"
        out = next(b for b in _bodies(await _notices(db, cid), "checkout") if "Virginia" in b)
        assert out == ("[PRUEBA] *VOLTAGE · Virginia · Horario 1 · Salida*\n"
                       "Lun 09/11 · 4:00 p. m. ET\n"
                       "\n"
                       "⚠️ *Siguen conectados / Still clocked in (1):*\n"
                       "1. Beto Vega · 8 h 50 min\n"
                       "\n"
                       "✅ Ya cerraron / Clocked out: 1 de 2"), out
        assert all(r["target"] in (OWN, MAIL) for r in await _notices(db, cid)), "modo prueba: todo a mi numero"


@pytest.mark.asyncio
async def test_fin_de_semana_solo_con_horario_o_turno(maker):
    async with maker() as db:
        ids = await _company(db)
        p = await _people(db, ids)
        cid = ids["company"]
        assert sum((await gr.plan_company(db, cid, T("11-14T12:30"))).values()) == 0, "sabado sin horario ni turnos: nada"
        await seed.shift(db, cid, p["carlos"], "11-14T12:10", None)
        stats = await gr.plan_company(db, cid, T("11-14T12:31"))
        assert stats["checkin"] == 1, "alguien de Virginia H1 inicio turno el sabado: sale el corte"
        body = next(b for b in _bodies(await _notices(db, cid), "checkin") if "Sáb 14/11" in b)
        assert "Connected: 1 de 3" in body and "*VOLTAGE · Virginia · Horario 1 · Entrada*" in body
        # Saturday con horario programado en Alabama H2 (dias 0-5)
        await ws.save_week(db, cid, ids["al"], MONDAY, [H1_AL, {**H2_AL, "days": [0, 1, 2, 3, 4, 5]}], actor="Dueña", actor_user_id=None)
        assert (await gr.plan_company(db, cid, T("11-14T14:30")))["checkin"] == 1, "sabado programado: sale aunque nadie haya entrado"


# ------------------------------------------------------------ 2) timesheet
@pytest.mark.asyncio
async def test_recordatorios_de_timesheet_y_el_de_las_9_solo_si_no_llego(maker):
    async with maker() as db:
        ids = await _company(db, test_mode=False)
        await _people(db, ids)
        cid = ids["company"]
        stats = await gr.plan_company(db, cid, T("11-09T23:30"))
        assert stats["ts_daily"] == 1 and stats["ts_weekly"] == 0, "lunes: Noel si, el grupo de Virginia solo el viernes"
        rows = await _notices(db, cid)
        noel = next(r for r in rows if r["kind"] == "ts_daily")
        assert noel["target"] == NOEL and noel["channel"] == "whatsapp" and not noel["body"].startswith("[PRUEBA]")
        assert noel["body"].count("\n") == 1 and noel["body"].startswith("📸 Hola, recuerda enviar la foto del timesheet de hoy (Alabama)")
        assert "📸 Hi, please send today's timesheet photo (Alabama)" in noel["body"] and "clonexa@example.test" in noel["body"]
        # martes 9:00 CT (15:00 UTC): no llego la foto -> un solo recordatorio mas
        assert (await gr.plan_company(db, cid, T("11-10T14:59")))["ts_followup"] == 0
        assert (await gr.plan_company(db, cid, T("11-10T15:00")))["ts_followup"] == 1
        assert (await gr.plan_company(db, cid, T("11-10T15:20")))["ts_followup"] == 0, "uno solo"
        follow = next(r for r in await _notices(db, cid) if r["kind"] == "ts_followup")
        assert follow["target"] == NOEL and "📸 Aún no llega el timesheet del Lun 09/11 (Alabama)" in follow["body"]

        # viernes: grupo de Virginia; la foto llega -> sabado 9:00 ET no hay recordatorio
        stats = await gr.plan_company(db, cid, T("11-13T23:30"))
        assert stats["ts_weekly"] == 1 and stats["ts_daily"] == 1
        weekly = next(r for r in await _notices(db, cid) if r["kind"] == "ts_weekly")
        assert weekly["target"] == GROUP_VA and "📸 Hola equipo Virginia: recuerden enviar la foto del timesheet de la semana" in weekly["body"]
        await gr.received(db, cid, {"location_id": ids["va"], "source": "whatsapp", "sender": GROUP_VA, "file_name": "ts.jpg",
                                    "drive_url": "https://drive.google.com/file/d/x"}, now=T("11-13T23:50"))
        assert (await gr.plan_company(db, cid, T("11-14T14:00")))["ts_followup"] == 0, "sabado 9:00 ET: la foto de Virginia ya llego"
        assert (await gr.plan_company(db, cid, T("11-14T15:00")))["ts_followup"] == 1, "sabado 9:00 CT: la de Noel (viernes) no"
        follows = [r for r in await _notices(db, cid) if r["kind"] == "ts_followup"]
        assert [r["target"] for r in follows] == [NOEL, NOEL], "ninguno al grupo de Virginia"


# ------------------------------------------------------------ 3) resumen diario y totales de la semana
@pytest.mark.asyncio
async def test_resumen_diario_a_duenos(maker):
    async with maker() as db:
        ids = await _company(db, test_mode=False)
        await _people(db, ids)
        cid = ids["company"]
        assert (await gr.plan_company(db, cid, T("11-09T23:29")))["owners_daily"] == 0
        assert (await gr.plan_company(db, cid, T("11-09T23:30")))["owners_daily"] == 1, "30 min despues de la ultima salida (18:00 ET / 17:00 CT)"
        rows = [r for r in await _notices(db, cid) if r["kind"] == "owners_daily"]
        assert [(r["channel"], r["target"]) for r in rows] == [("whatsapp", OWNER_A), ("whatsapp", OWNER_J),
                                                               ("email", "adriana@example.test,javier@example.test")]
        body = rows[0]["body"]
        assert body.startswith("📊 *VOLTAGE · Resumen del día*\nLunes 09/11 · Daily summary\n\n"), body
        assert ("📍 *Virginia (ET)*\n👥 3 personas · ⏱️ 17 h 29 min cerradas\n🔄 1 en curso (10 min acumuladas)\n"
                "⚠️ 1 turno sigue abierto") in body, body
        assert "📍 *Alabama (CT)*\n👥 2 personas · ⏱️ 8 h 34 min cerradas\n🔄 1 en curso (9 h 30 min acumuladas)" in body, body
        assert "⏱️ 0 min" not in body and "*Total:* 5 personas · 26 h 03 min cerradas · 🔄 2 en curso (9 h 40 min)" in body, body
        mail = rows[2]
        assert mail["subject"].startswith("VOLTAGE · Planilla del día") and json.loads(json.dumps(mail["attachments"]))[0]["kind"] == "daily_pdf"
        assert mail["body"].startswith(gr.HTML_MARK) and "<table" in mail["body"] and "Horas cerradas" in mail["body"] and "9 h 40 min" in mail["body"]
        sent = gr.payload({**mail, "id": 1, "notice_id": 1, "attempts": 1, "company_id": cid}, "VOLTAGE", T("11-09T23:31"))
        assert sent["html"] is True and sent["text"].startswith("<div") and not sent["text"].startswith(gr.HTML_MARK)
        content, name, mime = await gr.render_file(db, cid, {"kind": "daily_pdf", "from": "2026-11-09", "to": "2026-11-09"})
        assert content.startswith(b"%PDF") and mime == "application/pdf"


@pytest.mark.asyncio
async def test_totales_del_lunes_regulares_y_extra_por_persona(maker):
    async with maker() as db:
        ids = await _company(db, schedules=False, test_mode=False)
        cid = ids["company"]
        felipe = await seed.person(db, cid, "Felipe Soto", None, ids["al"])
        ana = await seed.person(db, cid, "Ana Ruiz", None, ids["va"])
        gabo = await seed.person(db, cid, "Gabo Mena", None, ids["al"])
        hugo = await seed.person(db, cid, "Hugo Paz", None, ids["al"])
        iris = await seed.person(db, cid, "Iris Luna", None, ids["al"])
        for d in ("10", "11", "12", "13"):  # Felipe 44 h (4 extra), Gabo 46 h (6), Hugo 42 h (2), Iris 41 h (1)
            await seed.shift(db, cid, felipe, f"11-{d}T12:00", f"11-{d}T23:00")
            await seed.shift(db, cid, gabo, f"11-{d}T12:00", f"11-{d}T23:30")
            await seed.shift(db, cid, hugo, f"11-{d}T12:00", f"11-{d}T22:30")
            await seed.shift(db, cid, iris, f"11-{d}T12:00", f"11-{d}T22:15")
        await seed.shift(db, cid, ana, "11-10T12:00", "11-10T20:00")
        assert (await gr.plan_company(db, cid, T("11-16T12:59")))["weekly_totals"] == 0
        assert (await gr.plan_company(db, cid, T("11-16T13:00")))["weekly_totals"] == 1, "lunes 8:00 ET"
        assert (await gr.plan_company(db, cid, T("11-16T13:30")))["weekly_totals"] == 0
        rows = [r for r in await _notices(db, cid) if r["kind"] == "weekly_totals"]
        assert not [r for r in rows if r["target"] in (GROUP_VA, GROUP_AL)], "074A: los totales nunca van a los grupos"
        assert [(r["channel"], r["target"]) for r in rows] == [("whatsapp", OWNER_A), ("whatsapp", OWNER_J),
                                                               ("email", "adriana@example.test,javier@example.test")]
        owner = next(r for r in rows if r["target"] == OWNER_A)["body"]
        assert owner == ("📊 *VOLTAGE · Semana 08/11 – 14/11*\n"
                         "📍 Virginia: 1 persona · 8 h (0 h extra)\n"
                         "📍 Alabama: 4 personas · 173 h (13 h extra)\n"
                         "⚠️ Más horas extra: Gabo Mena 6 h, Felipe Soto 4 h, Hugo Paz 2 h\n"
                         "📎 Detalle por persona en PDF y Excel en tu correo / Details by person in your email"), owner
        assert "Iris" not in owner and "1." not in owner, "sin lista por persona: solo el top 3"
        mail = next(r for r in rows if r["channel"] == "email")
        assert [a["kind"] for a in mail["attachments"]] == ["weekly_pdf", "weekly_xlsx"]
        assert mail["body"].startswith(gr.HTML_MARK) and "<table" in mail["body"] and all(n in mail["body"] for n in ("Felipe Soto", "Iris Luna", "Ana Ruiz"))
        xlsx, name, _ = await gr.render_file(db, cid, {"kind": "weekly_xlsx", "from": "2026-11-08", "to": "2026-11-14"})
        from openpyxl import load_workbook
        import io

        sheet = load_workbook(io.BytesIO(xlsx)).active
        values = [[c.value for c in row] for row in sheet.iter_rows(min_row=4)]
        felipe_row = next(v for v in values if v[1] == "Felipe Soto")
        assert felipe_row[0] == "Alabama" and felipe_row[8:] == [2640, 2400, 240]


# ------------------------------------------------------------ 4) modo prueba, envio y reintentos
@pytest.mark.asyncio
async def test_modo_prueba_nada_sale_a_destinos_reales_y_envio_con_reintentos(maker, monkeypatch):
    monkeypatch.setenv(gr.ENV_SECRET, "secreto-de-prueba")
    async with maker() as db:
        ids = await _company(db, test_mode=True)
        await _people(db, ids)
        cid = ids["company"]
        for minute in ("11-09T12:30", "11-09T14:30", "11-09T21:00", "11-09T23:30"):
            await gr.plan_company(db, cid, T(minute))
        rows = await _notices(db, cid)
        real = {GROUP_VA, GROUP_AL, NOEL, OWNER_A, OWNER_J, "adriana@example.test", "javier@example.test"}
        assert rows and not any(r["target"] in real or any(x in r["target"] for x in real) for r in rows), "nada a grupos, Noel ni dueños"
        assert all(r["body"].startswith("[PRUEBA] ") or (r["body"].startswith(gr.HTML_MARK) and "<b>[PRUEBA]</b>" in r["body"]) for r in rows)
        assert all(r["subject"].startswith("[PRUEBA] ") for r in rows if r["channel"] == "email")

        sent, gaps = [], []
        clock = {"now": T("11-09T23:31")}

        async def ok_sender(data):
            sent.append(data)
            return True, None

        async def sleep(s):
            gaps.append(s)

        n = await gr.deliver_company(db, cid, sender=ok_sender, sleep=sleep, now_fn=lambda: clock["now"], limit=100)
        assert n == len(rows) == len(sent)
        assert all(3.0 <= g <= 6.0 for g in gaps) and len(gaps) == n - 1, "3 a 6 s entre mensajes"
        mail = next(d for d in sent if d["channel"] == "email" and d["kind"] == "owners_daily")
        assert mail["attempt"] == 1 and mail["max_attempts"] == 3
        assert mail["to"] == [MAIL] and mail["attachments"][0]["url"].split("/files/")[1]
        token = mail["attachments"][0]["url"].split("/files/")[1]
        assert gr.unsign("secreto-de-prueba", token, clock["now"])["k"] == "daily_pdf"
        assert gr.unsign("secreto-de-prueba", token, clock["now"] + timedelta(hours=3)) is None, "enlace de corta duracion"
        assert gr.unsign("otro", token, clock["now"]) is None
        assert await gr.deliver_company(db, cid, sender=ok_sender, sleep=sleep, now_fn=lambda: clock["now"]) == 0, "lo enviado no se repite"

        # reintentos: falla 3 veces -> "fallido" en el historial
        await gr.send_test(db, cid, "ts_daily", now=clock["now"])
        calls = []

        async def bad_sender(data):
            calls.append(data["delivery_id"])
            return False, "n8n respondió 500"

        assert await gr.deliver_company(db, cid, sender=bad_sender, sleep=sleep, now_fn=lambda: clock["now"]) == 1
        assert await gr.deliver_company(db, cid, sender=bad_sender, sleep=sleep, now_fn=lambda: clock["now"]) == 0, "espera antes de reintentar"
        for minutes in (3, 20):
            clock["now"] += timedelta(minutes=minutes)
            assert await gr.deliver_company(db, cid, sender=bad_sender, sleep=sleep, now_fn=lambda: clock["now"]) == 1
        clock["now"] += timedelta(hours=1)
        assert await gr.deliver_company(db, cid, sender=bad_sender, sleep=sleep, now_fn=lambda: clock["now"]) == 0, "3 intentos y para"
        assert len(set(calls)) == 1 and len(calls) == 3
        items = await gr.history(db, cid)
        assert items[0]["status"] == "failed" and items[0]["error"] == "n8n respondió 500" and items[0]["test"]
        assert {"sent"} == {i["status"] for i in items[1:]}


@pytest.mark.asyncio
async def test_enviar_prueba_ahora_va_a_mi_numero_aunque_el_modo_prueba_este_apagado(maker):
    async with maker() as db:
        ids = await _company(db, test_mode=False)
        await _people(db, ids)
        cid = ids["company"]
        for kind in gr.KINDS:
            out = await gr.send_test(db, cid, kind, now=T("11-09T23:40"))
            assert out["deliveries"] >= 1
        rows = await _notices(db, cid)
        assert {r["target"] for r in rows} <= {OWN, MAIL} and all(r["test"] for r in rows)
        # las pruebas no cuentan como el aviso real del dia
        assert (await gr.plan_company(db, cid, T("11-09T23:30")))["owners_daily"] == 1
        with pytest.raises(gr.Invalid):
            await gr.send_test(db, cid, "no_existe")


# ------------------------------------------------------------ 5) entradas desde n8n
@pytest.mark.asyncio
async def test_clasificar_fotos_respuesta_automatica_y_recibidas(maker):
    async with maker() as db:
        ids = await _company(db, test_mode=False)
        cid = ids["company"]
        await seed.person(db, cid, "Vera Virginia", None, ids["va"], email="vera@example.test")
        now = T("11-09T23:45")
        c = await gr.classify(db, cid, {"channel": "whatsapp", "jid": f"{NOEL}@s.whatsapp.net", "has_media": True}, now)
        assert c["action"] == "save" and c["location_id"] == ids["al"] and c["operation"] == "Alabama" and c["date"] == "2026-11-09"
        assert c["reply"] == {"to": NOEL, "text": "Recibida ✅ / Received ✅"}
        assert (await gr.classify(db, cid, {"channel": "whatsapp", "jid": f"{NOEL}@s.whatsapp.net", "has_media": False}, now))["action"] == "ignore"
        c = await gr.classify(db, cid, {"channel": "whatsapp", "jid": GROUP_VA, "has_media": True}, now)
        assert c["action"] == "save" and c["location_id"] == ids["va"] and c["reply"]["to"] == GROUP_VA
        for body in ({"channel": "whatsapp", "jid": GROUP_AL, "has_media": True}, {"channel": "whatsapp", "jid": GROUP_VA, "has_media": False},
                     {"channel": "whatsapp", "jid": f"{OWNER_A}@s.whatsapp.net"}, {"channel": "whatsapp", "jid": "15550009999@s.whatsapp.net", "from_me": True}):
            assert (await gr.classify(db, cid, body, now))["action"] == "ignore", body
        stranger = {"channel": "whatsapp", "jid": "15550009999@s.whatsapp.net", "has_media": False}
        first = await gr.classify(db, cid, stranger, now)
        assert first["action"] == "autoreply" and first["reply"]["to"] == "15550009999" and "solo envía reportes de VOLTAGE" in first["reply"]["text"]
        assert (await gr.classify(db, cid, stranger, now + timedelta(hours=2)))["action"] == "ignore", "una vez al dia por persona"
        assert (await gr.classify(db, cid, stranger, now + timedelta(days=1)))["action"] == "autoreply"
        mail = await gr.classify(db, cid, {"channel": "email", "from_email": "Vera <vera@example.test>", "subject": "hoja", "has_media": True}, now)
        assert mail["action"] == "save" and mail["location_id"] == ids["va"]
        assert (await gr.classify(db, cid, {"channel": "email", "from_email": "x@example.test", "subject": "Timesheet Alabama", "has_media": True}, now))["location_id"] == ids["al"]
        assert (await gr.classify(db, cid, {"channel": "email", "from_email": "x@example.test", "subject": "factura", "has_media": True}, now))["action"] == "ignore"
        await gr.received(db, cid, {"location_id": ids["al"], "source": "whatsapp", "sender": NOEL, "file_name": "ts.jpg", "drive_url": "https://drive.google.com/x"})
        items = await gr.history(db, cid)
        assert items[0]["kind_label"] == "Timesheet recibido" and items[0]["status"] == "received" and "Alabama" in items[0]["destination"]
        assert await gr.deliver_company(db, cid, sender=None, sleep=None, limit=5) == 0, "lo recibido nunca se envia"
        # modo prueba: las respuestas tambien van a mi numero
        cfg = await gr.get_config(db, cid)
        await gr.save_config(db, cid, {**cfg, "test_mode": True}, actor="Dueña")
        c = await gr.classify(db, cid, {"channel": "whatsapp", "jid": f"{NOEL}@s.whatsapp.net", "has_media": True}, now)
        assert c["reply"] == {"to": OWN, "text": "[PRUEBA] Recibida ✅ / Received ✅"}


# ------------------------------------------------------------ 6) acceso y otras empresas
@pytest.mark.asyncio
async def test_acceso_secreto_roles_y_otras_empresas(maker, monkeypatch):
    monkeypatch.setenv(gr.ENV_SECRET, "secreto-de-prueba")
    with pytest.raises(HTTPException) as exc:
        routes.machine(None)
    assert exc.value.status_code == 401, "webhook sin cabecera secreta -> 401"
    with pytest.raises(HTTPException) as exc:
        routes.machine("otro")
    assert exc.value.status_code == 401
    assert routes.machine("secreto-de-prueba") is True
    monkeypatch.setenv(gr.ENV_SECRET, "")
    with pytest.raises(HTTPException):
        routes.machine("")
    async with maker() as db:
        ids = await _company(db)
        cid = ids["company"]
        other = await seed.company(db, "Otra", board=False)
        assert await gr.companies_on(db) and other not in await gr.companies_on(db) and cid in await gr.companies_on(db)
        req = SimpleNamespace(cookies={}, headers={})
        import app.api.deps as deps
        import app.web.admin_v2_routes as admin

        async def no_admin(*_a, **_k):
            return None

        role = {"value": "supervisor", "company": cid}

        async def fake_user(db_, authorization, company_id, **_k):
            if not authorization:
                raise HTTPException(status_code=401, detail="no")
            if str(company_id) != role["company"]:
                raise HTTPException(status_code=403, detail="tenant_not_allowed")
            return SimpleNamespace(role=role["value"], full_name="X")

        monkeypatch.setattr(admin, "_active_session", no_admin)
        monkeypatch.setattr(deps, "require_company_user_for_tenant", fake_user)
        with pytest.raises(HTTPException) as exc:
            await routes.owner(uuid.UUID(cid), req, authorization=None, db=db)
        assert exc.value.status_code == 401
        with pytest.raises(HTTPException) as exc:
            await routes.owner(uuid.UUID(cid), req, authorization="Bearer t", db=db)
        assert exc.value.status_code == 403, "supervisor no ve configuracion ni historial"
        role["value"] = "company_admin"
        assert (await routes.owner(uuid.UUID(cid), req, authorization="Bearer t", db=db))["role"] == "company_admin"
        role["company"] = other
        with pytest.raises(HTTPException) as exc:
            await routes.owner(uuid.UUID(other), req, authorization="Bearer t", db=db)
        assert exc.value.status_code == 404, "otra empresa sin el interruptor"
        with pytest.raises(HTTPException) as exc:
            await routes.owner(uuid.UUID(cid), req, authorization="Bearer t", db=db)
        assert exc.value.status_code == 403, "usuario de otra empresa"
        await _switch(db, cid, on=False)
        assert await gr.companies_on(db) == [] or cid not in await gr.companies_on(db)


def test_configuracion_se_valida_en_el_servidor():
    locs = {"a", "b"}
    with pytest.raises(gr.Invalid):
        gr.clean_config({"operations": [{"location_id": "zzz"}]}, locs)
    with pytest.raises(gr.Invalid):
        gr.clean_config({"operations": [{"location_id": "a", "group_jid": "no-es-grupo"}]}, locs)
    with pytest.raises(gr.Invalid):
        gr.clean_config({"own_number": "12"}, locs)
    with pytest.raises(gr.Invalid):
        gr.clean_config({"owners": [{"email": "malo"}]}, locs)
    with pytest.raises(gr.Invalid):
        gr.clean_config({"totals_tz": "Mars/Base"}, locs)
    cfg = gr.clean_config({"own_number": "+1 (555) 000-1234", "test_mode": None}, locs)
    assert cfg["own_number"] == "15550001234" and cfg["test_mode"] is True, "modo prueba encendido salvo que se apague explicitamente"
    assert gr.clean_config({"test_mode": False}, locs)["test_mode"] is False
    assert gr.last_saturday(date(2026, 11, 16)) == date(2026, 11, 14)
    assert gr.last_saturday(date(2026, 11, 14)) == date(2026, 11, 7), "un sabado: la semana anterior completa"


# ------------------------------------------------------------ 7) Telegram a los 30 min
class Outbox:
    def __init__(self):
        self.sent = []

    async def send(self, chat, message, reply_markup=None):
        self.sent.append((chat, message))

    async def language_of(self, tg):
        return "es"


def test_telegram_ya_saliste_a_los_30_min_con_el_interruptor(monkeypatch):
    """run_all pasa 30 min con whatsapp_group_reports y 15 sin el; run_company pregunta una vez."""
    seen = {}

    async def fake_run_company(db, cid, *, send, language_of, now=None, prompt_after=ws.PROMPT_AFTER_MINUTES):
        seen[cid] = prompt_after
        return {}

    async def fake_companies(db):
        return ["on", "off"]

    async def fake_is_on(db, cid):
        return cid == "on"

    async def fake_token(db, cid):
        return None

    from app.services import bot_punch_gps

    monkeypatch.setattr(ws, "run_company", fake_run_company)
    monkeypatch.setattr(ws, "companies_on", fake_companies)
    monkeypatch.setattr(gr, "is_on", fake_is_on)
    monkeypatch.setattr(bot_punch_gps, "bot_token", fake_token)
    asyncio.run(ws.run_all(SimpleNamespace(rollback=lambda: None)))
    assert seen == {"on": 30, "off": 15}


# ------------------------------------------------------------ 074A: a los grupos nunca horas
def test_mensaje_semanal_numeros_grandes_y_sin_extras():
    assert gr.hours_round(1240 * 60 + 20) == "1.240 h" and gr.hours_round(52 * 60 - 10) == "52 h" and gr.hours_round(0) == "0 h"


@pytest.mark.asyncio
async def test_grupos_solo_cortes_y_timesheet_en_dia_y_semana_completos(maker):
    async with maker() as db:
        ids = await _company(db, test_mode=False)
        await _people(db, ids)
        cid = ids["company"]
        minutes = [T(f"11-{d}T{h}") for d in ("09", "10", "13", "14", "16") for h in ("12:30", "13:00", "14:30", "15:00", "21:00", "23:30")]
        for now in minutes:
            await gr.plan_company(db, cid, now)
        for kind in gr.KINDS:
            await gr.send_test(db, cid, kind, now=T("11-16T13:10"))
        rows = await _notices(db, cid)
        to_groups = {r["kind"] for r in rows if r["target"] in (GROUP_VA, GROUP_AL) or r["destination"].startswith("Grupo")}
        assert to_groups and to_groups <= set(gr.GROUP_KINDS), to_groups
        assert {"weekly_totals", "owners_daily", "ts_daily"}.isdisjoint(to_groups)
        for r in rows:
            if r["target"] in (GROUP_VA, GROUP_AL) or r["destination"].startswith("Grupo"):
                assert "acumuladas" not in r["body"] and "extra" not in r["body"] and "cerradas" not in r["body"], r["body"]
        # candado: aunque alguien arme un envio a grupo de otro tipo, no se crea
        group = gr.recipients(await gr.get_config(db, cid), "group", (await gr.operations(db, cid, await gr.get_config(db, cid)))[0])
        nid = await gr.claim(db, cid, "candado:prueba", "owners_daily", location_id=None, day=MONDAY, slot=0,
                             deliveries=gr._deliveries(group, "📊 horas"))
        n = (await db.execute(text("SELECT count(*) FROM wa_report_deliveries WHERE notice_id = :n"), {"n": nid})).scalar()
        assert n == 0
