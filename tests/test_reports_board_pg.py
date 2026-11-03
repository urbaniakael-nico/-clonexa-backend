"""Board de gerencia (interruptor reports_board) contra Postgres REAL (pgserver): mismas horas
que Nomina, chip en vivo, linea de tiempo, alertas, supervisor con su operacion, perimetros
(guardar, sugerencia sin guardar, recalculo sin cambiar horas), PDF y CSV, sesion y aislamiento
entre empresas. Datos inventados: tests/fixtures/reports_board_seed.py. Si pgserver no esta
instalado, se salta."""
from __future__ import annotations

import asyncio
import csv
import importlib.util
import io
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import HTTPException

pgserver = pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.api.v1.endpoints import bots  # noqa: E402
from app.api.v1.endpoints import payroll as core  # noqa: E402
from app.api.v1.endpoints import reports_board as api  # noqa: E402
from app.services import reports_board as svc  # noqa: E402
from app.services import reports_board_export as export  # noqa: E402
from app.services import us_payroll  # noqa: E402
from app.services import work_location_geo as geo  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("reports_board_seed", ROOT / "tests" / "fixtures" / "reports_board_seed.py")
seedmod = importlib.util.module_from_spec(spec)
sys.modules["reports_board_seed"] = seedmod
spec.loader.exec_module(seedmod)
from tests.test_reports_v2 import pdf_text  # noqa: E402

NOW, START, END, VA_POINT, FAR_POINT = seedmod.NOW, seedmod.START, seedmod.END, seedmod.VA_POINT, seedmod.FAR_POINT


@pytest.fixture(scope="module")
def pg_url():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="cx_pg_rb_"), cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await seedmod.create_schema(conn)
        await engine.dispose()

    asyncio.run(setup())
    yield url


@pytest.fixture()
async def maker(pg_url):
    engine = create_async_engine(pg_url)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


async def _board(db, ids, **kw):
    return await svc.build(db, ids["company"], START, END, now=NOW, **kw)


def _people(board):
    return {p["id"]: p for o in board["operations"] for p in o["people"]}


def _op(board, name):
    return next(o for o in board["operations"] if o["name"] == name)


@pytest.mark.asyncio
async def test_dos_operaciones_az_y_horas_iguales_a_nomina(maker):
    async with maker() as db:
        ids = await seedmod.seed(db)
        board = await _board(db, ids)
        assert [o["name"] for o in board["operations"]] == ["Virginia", "Alabama", "Sin lugar asignado"], "de este a oeste; Sin lugar solo si hay"
        assert [o["abbr"] for o in board["operations"][:2]] == ["ET", "CT"]
        # A-Z sin tildes: Ángela va antes que Bruno.
        assert [p["name"] for p in _op(board, "Virginia")["people"]] == ["Ángela Núñez", "Bruno Díaz", "Carla Peña", "Diego Ruiz", "Sofía Mora"]
        assert [p["name"] for p in _op(board, "Alabama")["people"]] == ["Elena Gómez", "Felipe Soto", "Gabriel Luna", "Helena Ríos", "Iván Mena"]
        # La MISMA funcion de Nomina, persona por persona.
        nomina = await core.calculate_period_snapshot(db, UUID(ids["company"]), START, END)
        rows = {str(r["employee_id"]): r["us"] for r in nomina["rows"]}
        people = _people(board)
        assert set(rows) == {eid for eid, p in people.items() if p["payable"]}
        for eid, us in rows.items():
            p = people[eid]
            assert (p["connected"], p["pause"], p["payable"], p["regular"], p["overtime"], p["days_worked"]) == (
                us["connected_minutes"], us["pause_minutes"], us["payable_minutes"], us["regular_minutes"], us["overtime_minutes"], us["days_worked"])
        # Caso de ejemplo: 9 h 40 en turno, 54 min de pausa, 8 h 46 pagables.
        a = people[ids["angela"]]
        assert (a["connected"], a["pause"], a["payable"]) == (580, 54, 526)
        # Overtime solo por encima de 40 h en la semana.
        f = people[ids["felipe"]]
        assert (f["payable"], f["regular"], f["overtime"]) == (2640, 2400, 240)
        assert board["figures"]["payable"] == nomina["totals"]["payable_minutes"]
        # Reportes no muestra valores de pago, aunque la persona tenga tarifa.
        dump = json.dumps(board, default=str)
        for word in ("gross", "net_amount", "hourly_rate", "rate_pending", "amount", "deduction"):
            assert word not in dump, word


@pytest.mark.asyncio
async def test_chip_en_vivo(maker):
    async with maker() as db:
        ids = await seedmod.seed(db)
        board = await _board(db, ids)
        people = _people(board)
        assert people[ids["bruno"]]["now"]["state"] == "working" and people[ids["bruno"]]["now"]["minutes"] == 280, "5 h menos 20 min de pausa"
        assert people[ids["carla"]]["now"]["state"] == "on_break" and people[ids["carla"]]["now"]["minutes"] == 20
        assert people[ids["diego"]]["now"]["state"] == "no_shift"
        assert people[ids["gabriel"]]["now"]["state"] == "to_confirm" and people[ids["gabriel"]]["now"]["over_limit"] is True, "abierto 15 h"
        assert people[ids["helena"]]["now"]["state"] == "to_confirm", "cerrado con 15 h"
        va = _op(board, "Virginia")["figures"]
        assert (va["working"], va["on_break"], va["no_shift"]) == (1, 1, 3)
        al = _op(board, "Alabama")["figures"]
        assert al["to_confirm"] == 2 and al["held"] == 1 and al["open_over"] == 1
        # Un turno abierto no suma horas, igual que en Nomina.
        assert people[ids["bruno"]]["payable"] == 0
        # La misma lectura en la llamada liviana de cada 60 s.
        live = await svc.live_block(db, ids["company"], now=NOW)
        assert live["people"][ids["bruno"]]["minutes"] == 280 and live["people"][ids["diego"]]["state"] == "no_shift"
        assert set(live["clocks"]) == {ids["va"], ids["al"]}
        assert live["clocks"][ids["va"]]["local_time"] == "13:00" and live["clocks"][ids["al"]]["local_time"] == "12:00"
        # Quien termino hoy no dice "Sin turno hoy".
        late = await svc.live_block(db, ids["company"], now=seedmod.T("11-04T23:30"))
        assert late["people"][ids["ivan"]]["state"] == "done"


@pytest.mark.asyncio
async def test_linea_de_tiempo(maker):
    async with maker() as db:
        ids = await seedmod.seed(db)
        people = _people(await _board(db, ids))
        # Pausas, materiales y nota de cierre, en hora local.
        day = people[ids["angela"]]["days"][0]
        assert day["date"] == "2026-11-02"
        s = day["shifts"][0]
        assert (s["in"]["t"], s["in"]["a"], s["in"]["s"]) == ("06:45", "ET", "unconfigured"), "sin perimetro en el lugar"
        assert (s["pauses"][0]["start"]["t"], s["pauses"][0]["end"]["t"], s["pauses"][0]["minutes"]) == ("10:35", "11:29", 54)
        assert s["out"]["t"] == "16:25" and s["out"]["lat"] == VA_POINT[0]
        assert next(n for n in s["notes"] if n["kind"] == "summary")["text"] == seedmod.SUMMARY
        assert day["materials"][0]["what"] == "Cable 6 AWG" and day["materials"][0]["t"] == "11:40" and day["materials"][0]["qty"] == 3
        assert (day["connected"], day["pause"], day["payable"]) == (580, 54, 526)
        assert people[ids["angela"]]["materials"] == 1 and people[ids["angela"]]["notes"] == 1
        assert people[ids["angela"]]["last_mark"]["t"] == "16:25"
        # Cierre por supervisor: quien, hora puesta y nota; su salida no pide ubicacion.
        ivan = people[ids["ivan"]]["days"][0]["shifts"][0]
        assert ivan["manual"]["by"] == "Sofía Mora" and ivan["manual"]["note"] == "Olvidó marcar la salida"
        assert ivan["out"]["t"] == "17:00" and ivan["out"]["s"] is None
        assert ivan["in"]["s"] == "none", "entrada sin ubicacion"
        # Turno abierto: en la linea de tiempo, sin sumar al dia.
        bruno = people[ids["bruno"]]["days"][0]
        assert bruno["shifts"][0]["state"] == "running" and bruno["shifts"][0]["out"] is None and bruno["payable"] == 0
        carla = people[ids["carla"]]["days"][0]["shifts"][0]
        assert carla["pauses"][0]["auto"] is True and carla["pauses"][0]["end"] is None
        # Por confirmar: se ve, no suma.
        held = people[ids["helena"]]["days"][0]
        assert held["shifts"][0]["state"] == "held" and held["payable"] == 0
        assert people[ids["helena"]]["notes"] == 1


@pytest.mark.asyncio
async def test_alertas(maker):
    async with maker() as db:
        ids = await seedmod.seed(db)
        await geo.save_place(db, ids["company"], ids["al"], {"perimeters": [{"name": "Patio", "latitude": VA_POINT[0], "longitude": VA_POINT[1]}], "supervisors": []}, "dueño")
        await seedmod.ev(db, ids["company"], ids["felipe"], "check_in", seedmod.T("11-05T12:00"), point=FAR_POINT)
        await seedmod.ev(db, ids["company"], ids["felipe"], "check_out", seedmod.T("11-05T13:00"), point=VA_POINT)
        await db.commit()
        await geo.recalculate(db, ids["company"], ids["al"])
        board = await _board(db, ids)
        alerts = _op(board, "Alabama")["alerts"]
        kinds = {(a["kind"], a["employee"]) for a in alerts}
        assert ("outside", "Felipe Soto") in kinds, "marcacion fuera de perimetro"
        assert ("no_location", "Elena Gómez") in kinds, "marcacion sin ubicacion"
        assert ("to_confirm", "Helena Ríos") in kinds, "turno de mas de 12 h"
        assert ("to_confirm", "Gabriel Luna") in kinds, "abierto mas de 12 h"
        assert ("near_overtime", "Elena Gómez") in kinds, "38 h en la semana (36 o mas)"
        assert all(a.get("t") and a.get("a") in ("CT", "ET") for a in alerts), "cada alerta con su hora"
        out = next(a for a in alerts if a["kind"] == "outside")
        assert (out["mark"], out["t"], out["a"]) == ("Entrada", "06:00", "CT")
        people = _people(board)
        assert people[ids["felipe"]]["outside"] == 1
        # La salida que puso un supervisor no es una alerta de "sin ubicacion" (solo su entrada).
        ivan = [a for a in alerts if a["employee"] == "Iván Mena"]
        assert [(a["kind"], a["mark"]) for a in ivan] == [("no_location", "Entrada")]
        # Valor configurable por empresa.
        await geo.save_near_ot(db, ids["company"], 39)
        board = await _board(db, ids)
        assert ("near_overtime", "Elena Gómez") not in {(a["kind"], a["employee"]) for a in _op(board, "Alabama")["alerts"]}
        assert board["near_ot_minutes"] == 39 * 60
        with pytest.raises(geo.Invalid):
            await geo.save_near_ot(db, ids["company"], 500)


@pytest.mark.asyncio
async def test_supervisor_ve_solo_su_operacion(maker, monkeypatch):
    async with maker() as db:
        ids = await seedmod.seed(db)
        import app.api.deps as deps
        import app.web.admin_v2_routes as admin

        monkeypatch.setattr(admin, "_active_session", AsyncMock(return_value=None))
        request = SimpleNamespace()

        async def who_for(role, email="", name=""):
            monkeypatch.setattr(deps, "require_company_user_for_tenant", AsyncMock(return_value=SimpleNamespace(role=role, email=email, full_name=name, id=None)))
            return await api.actor(UUID(ids["company"]), request, "Bearer x", db)

        # Con lugar (por correo): solo Virginia, tambien en el Board y en los archivos.
        who = await who_for("supervisor", "SOFIA@voltage.test", "Otra")
        assert who["places"] == [ids["va"]] and who["no_place"] is False
        board = await svc.build(db, ids["company"], START, END, now=NOW, places=who["places"])
        assert [o["name"] for o in board["operations"]] == ["Virginia"]
        assert "Elena" not in export.build_marks_csv(board) and "Elena" not in json.dumps(board, default=str)
        live = await svc.live_block(db, ids["company"], places=who["places"], now=NOW)
        assert ids["elena"] not in live["people"] and ids["bruno"] in live["people"]
        # Si figura como supervisor de otro lugar, tambien lo ve.
        await geo.save_place(db, ids["company"], ids["al"], {"perimeters": [], "supervisors": [ids["sofia"]]}, "dueño")
        assert set((await who_for("supervisor", "sofia@voltage.test"))["places"]) == {ids["va"], ids["al"]}
        # Sin lugar: ve las dos y queda marcado.
        who = await who_for("supervisor", "nadie@voltage.test", "Nadie")
        assert who["places"] is None and who["no_place"] is True
        # Dueno, admin y gerencia: todas. Otro rol: 403 aunque tenga sesion.
        for role in ("company_admin", "gerencia", "Dueño"):
            who = await who_for(role)
            assert who["places"] is None and who["no_place"] is False
        with pytest.raises(HTTPException) as exc:
            await who_for("operator")
        assert exc.value.status_code == 403
        # Perimetros: solo dueno / admin.
        with pytest.raises(HTTPException) as exc:
            api.manager({"role": "gerencia"})
        assert exc.value.status_code == 403
        assert api.manager({"role": "company_admin"})["role"] == "company_admin"
        # Apagado: 404 para todos.
        other = await seedmod.company(db, "Otra", board=False)
        monkeypatch.setattr(deps, "require_company_user_for_tenant", AsyncMock(return_value=SimpleNamespace(role="company_admin", email="", full_name="", id=None)))
        with pytest.raises(HTTPException) as exc:
            await api.actor(UUID(other), request, "Bearer x", db)
        assert exc.value.status_code == 404


def test_toda_ruta_exige_sesion_y_esta_registrada():
    routes = list(api.router.routes)
    assert len(routes) == 9
    for r in routes:
        calls = [d.call for d in r.dependant.dependencies]
        assert api.actor in calls or api.manager in calls, f"{r.path} sin sesion"
    from app.api.v1 import router as v1

    paths = {getattr(r, "path", "") for r in v1.api_router.routes}
    assert "/reports-board/companies/{company_id}" in paths


def test_interruptor_registrado_y_apagado_por_defecto():
    from app.services import switch_registry

    sw = next(s for s in switch_registry.registry()["switches"] if s["key"] == "reports_board")
    assert sw["module"] == "reports" and sw["delicate"] is True
    assert {d["key"] for d in sw["depends_on"]} == {"us_payroll", "work_locations"}


@pytest.mark.asyncio
async def test_perimetros_guardar_sugerir_y_recalcular(maker):
    async with maker() as db:
        ids = await seedmod.seed(db)
        other = await seedmod.company(db, "Otra", board=False)
        before = await _board(db, ids)
        assert _op(before, "Virginia")["perimeter_missing"] is True
        assert _op(before, "Sin lugar asignado")["perimeter_missing"] is False, "sin aviso: no es un lugar"

        # Sugerencia: calcula y NO guarda nada.
        out = await geo.suggestion(db, ids["company"], ids["va"], now=seedmod.T("11-05T18:00"))
        assert out["saved"] is False and out["suggestion"]["latitude"] == VA_POINT[0] and out["suggestion"]["marks"] == 3
        assert out["suggestion"]["p90_m"] == 0
        assert (await db.execute(text("SELECT count(*) FROM work_location_perimeters WHERE company_id = CAST(:c AS uuid)"), {"c": ids["company"]})).scalar() == 0
        none = await geo.suggestion(db, ids["company"], ids["va"], now=seedmod.T("12-30T18:00"))
        assert none["suggestion"] is None

        # Guardar: validaciones, radio 300 por defecto, solo de esta empresa.
        for bad in ([{"name": "x", "latitude": 95, "longitude": 0}], [{"name": "x", "latitude": 1, "longitude": 1, "radius_m": 5}], [{"name": "x", "latitude": "", "longitude": 1}]):
            with pytest.raises(geo.Invalid):
                await geo.save_place(db, ids["company"], ids["va"], {"perimeters": bad, "supervisors": []}, "dueño")
        with pytest.raises(geo.Invalid):
            await geo.save_place(db, other, ids["va"], {"perimeters": [], "supervisors": []}, "dueño")
        await db.rollback()
        with pytest.raises(geo.Invalid):
            await geo.save_place(db, ids["company"], ids["va"], {"perimeters": [], "supervisors": [str(UUID(int=1))]}, "dueño")
        await db.rollback()
        with pytest.raises(geo.Invalid):
            await geo.recalculate(db, ids["company"], ids["va"])
        saved = await geo.save_place(db, ids["company"], ids["va"], {"perimeters": [{"name": "Bodega", "latitude": VA_POINT[0], "longitude": VA_POINT[1]}, {"name": "Patio", "latitude": 38.0, "longitude": -77.0, "radius_m": 500}],
                                                                     "supervisors": [ids["sofia"]]}, "dueño")
        assert [p["radius_m"] for p in saved["perimeters"]] == [300, 500] and saved["supervisors"][0]["name"] == "Sofía Mora"
        board = await _board(db, ids)
        va = _op(board, "Virginia")
        assert va["perimeter_missing"] is False and va["supervisors"] == ["Sofía Mora"]
        # Las marcas viejas siguen "Sin perimetro": nada cambio solo.
        s = _people(board)[ids["angela"]]["days"][0]["shifts"][0]
        assert s["in"]["s"] == "unconfigured"

        # Marca nueva por el bot: dentro / fuera; con el lugar sin perimetro, como siempre.
        inside = await bots._validate_gps_location_for_company(db, company_id=UUID(ids["company"]), latitude=VA_POINT[0], longitude=VA_POINT[1], employee_id=ids["bruno"])
        assert inside["gps_status"] == "inside" and inside["matched_perimeter_name"] == "Bodega" and inside["geo_source"] == "place"
        outside = await bots._validate_gps_location_for_company(db, company_id=UUID(ids["company"]), latitude=FAR_POINT[0], longitude=FAR_POINT[1], employee_id=ids["bruno"])
        assert outside["gps_status"] == "outside" and outside["gps_status_label"] == "Fuera de perímetro"
        sin = await bots._validate_gps_location_for_company(db, company_id=UUID(ids["company"]), latitude=VA_POINT[0], longitude=VA_POINT[1], employee_id=ids["elena"])
        assert sin["gps_status"] == "unconfigured" and "geo_source" not in sin
        await db.commit()

        # Recalcular marcas viejas: cambia el estado, NO las horas ni la hora de la marca.
        await seedmod.ev(db, ids["company"], ids["diego"], "check_in", seedmod.T("11-04T13:00"), point=FAR_POINT)
        await seedmod.ev(db, ids["company"], ids["diego"], "check_out", seedmod.T("11-04T14:00"))
        await db.commit()
        times = "SELECT id::text, occurred_at, latitude FROM workforce_attendance_events WHERE company_id = CAST(:c AS uuid) ORDER BY id"
        t0 = [tuple(r) for r in (await db.execute(text(times), {"c": ids["company"]})).all()]
        hours = await core.calculate_period_snapshot(db, UUID(ids["company"]), START, END)
        result = await geo.recalculate(db, ids["company"], ids["va"])
        assert result["updated"] > 0 and result["outside"] == 1 and result["no_location"] == 1
        assert [tuple(r) for r in (await db.execute(text(times), {"c": ids["company"]})).all()] == t0
        again = await core.calculate_period_snapshot(db, UUID(ids["company"]), START, END)
        assert again["totals"] == hours["totals"]
        assert [r["us"]["payable_minutes"] for r in again["rows"]] == [r["us"]["payable_minutes"] for r in hours["rows"]]
        board = await _board(db, ids)
        people = _people(board)
        s = people[ids["angela"]]["days"][0]["shifts"][0]
        assert s["in"]["s"] == "inside" and s["in"]["n"] == "Bodega"
        assert people[ids["diego"]]["outside"] == 1 and people[ids["diego"]]["no_location"] == 1
        # Alabama no se toco.
        assert _people(board)[ids["elena"]]["days"][-1]["shifts"][0]["in"]["s"] == "unconfigured"
        # Quitar todos los perimetros: otra vez Sin perimetro.
        await geo.save_place(db, ids["company"], ids["va"], {"perimeters": [], "supervisors": []}, "dueño")
        assert _people(await _board(db, ids))[ids["angela"]]["days"][0]["shifts"][0]["in"]["s"] == "unconfigured"


@pytest.mark.asyncio
async def test_recalculo_respeta_el_lugar_de_ese_dia(maker):
    async with maker() as db:
        ids = await seedmod.seed(db)
        # Jaime estaba en Virginia y hoy no tiene lugar: sus marcas viejas son de Virginia.
        await db.execute(text("""INSERT INTO work_location_changes (company_id, employee_id, from_location_id, to_location_id, changed_at)
                                 VALUES (CAST(:c AS uuid), CAST(:e AS uuid), CAST(:v AS uuid), NULL, :at)"""),
                         {"c": ids["company"], "e": ids["jaime"], "v": ids["va"], "at": seedmod.T("11-04T00:00")})
        await db.commit()
        await geo.save_place(db, ids["company"], ids["va"], {"perimeters": [{"name": "Bodega", "latitude": VA_POINT[0], "longitude": VA_POINT[1]}], "supervisors": []}, "dueño")
        await geo.recalculate(db, ids["company"], ids["va"])
        row = (await db.execute(text("""SELECT payload_json FROM workforce_attendance_events WHERE employee_id = CAST(:e AS uuid) AND event_type = 'check_in'"""), {"e": ids["jaime"]})).scalar()
        assert row["punch_location"]["gps_status"] == "inside" and row["geo_source"] == "place"


@pytest.mark.asyncio
async def test_apagado_el_bot_y_nomina_no_cambian(maker):
    async with maker() as db:
        cid = await seedmod.company(db, "Otra", board=False)
        pid = await seedmod.place(db, cid, "Sede", "SD", "America/Chicago", 1)
        eid = await seedmod.person(db, cid, "Otra Persona", "OT-1", pid)
        await db.execute(text("INSERT INTO work_location_perimeters (company_id, location_id, name, latitude, longitude) VALUES (CAST(:c AS uuid), CAST(:l AS uuid), 'x', 1, 1)"), {"c": cid, "l": pid})
        await db.commit()
        out = await bots._validate_gps_location_for_company(db, company_id=UUID(cid), latitude=1.0, longitude=1.0, employee_id=eid)
        assert out["gps_status"] == "unconfigured" and "geo_source" not in out, "sin el interruptor manda lo de siempre"
        assert await geo.is_on(db, cid) is False
        await seedmod.shift(db, cid, eid, "11-02T12:00", "11-02T20:00")
        snap = await us_payroll.snapshot(db, cid, START, END)
        assert "week_totals" not in snap["us_payroll"], "sin board=True, el snapshot de Nomina es el de siempre"


@pytest.mark.asyncio
async def test_csv_y_pdf(maker):
    async with maker() as db:
        ids = await seedmod.seed(db)
        board = await _board(db, ids)
        rows = list(csv.reader(io.StringIO(export.build_marks_csv(board).lstrip("﻿"))))
        assert rows[0] == ["operacion", "empleado", "documento", "fecha", "hora_local", "tipo", "latitud", "longitud", "perimetro", "nota"]
        mine = [r for r in rows[1:] if r[1] == "Ángela Núñez"]
        assert [(r[3], r[4], r[5]) for r in mine] == [("2026-11-02", "06:45 ET", "Entrada"), ("2026-11-02", "10:35 ET", "Pausa"), ("2026-11-02", "11:29 ET", "Retomar"), ("2026-11-02", "16:25 ET", "Salida")]
        assert mine[0][0] == "Virginia (ET)" and mine[0][2] == "VA-100" and mine[0][6] == str(VA_POINT[0]) and mine[0][8] == "Sin perímetro" and mine[0][9] == ""
        assert mine[3][9] == seedmod.SUMMARY
        iv = [r for r in rows[1:] if r[1] == "Iván Mena"]
        assert iv[0][8] == "Sin ubicación" and iv[1][8] == "" and iv[1][9] == "Olvidó marcar la salida"
        notes = list(csv.reader(io.StringIO(export.build_notes_csv(board).lstrip("﻿"))))
        assert notes[0] == ["operacion", "empleado", "fecha", "hora", "texto"]
        assert ["Virginia (ET)", "Ángela Núñez", "2026-11-02", "16:25 ET", seedmod.SUMMARY] in notes
        # Un texto no puede volverse formula en Excel.
        assert export.safe_cell("=1+1") == "'=1+1" and export.safe_cell("rack 9") == "rack 9"

        pdf = export.build_pdf(board)
        assert pdf.startswith(b"%PDF")
        assert b"/MediaBox [ 0 0 792 612 ]" in pdf, "carta horizontal"
        words = pdf_text(pdf)
        for needle in ("Board de gerencia", "Virginia (ET)", "Alabama (CT)", "Ángela Núñez", "Iván Mena", "rack 9", "Alertas", "Notas de cierre", "Perímetro sin configurar"):
            assert needle in words, needle
        for banned in ("Tarifa", "Bruto", "Neto", "$"):
            assert banned not in words, banned
        # Tabla A-Z dentro de cada operacion.
        table = words[words.index("Empleado"):]
        assert table.index("Ángela Núñez") < table.index("Bruno Díaz") < table.index("Sofía Mora")


def test_reglas_puras():
    assert svc.sort_key('"Eduardo Lores') == "eduardo lores" and svc.sort_key("Ángela") < svc.sort_key("Bruno")
    assert geo.distance_m(38.9, -77.0, 38.9, -77.0) == 0
    assert 290 < geo.distance_m(38.9, -77.0, 38.9027, -77.0) < 310
    inside = geo.classify(38.9, -77.0, [{"id": "a", "name": "A", "latitude": 38.9, "longitude": -77.0, "radius_m": 300}])
    assert inside["gps_status"] == "inside" and inside["matched_perimeter_name"] == "A"
    # 2 marcas lejanas no mueven el punto medio (mediana).
    center = geo.suggest_center([(38.9, -77.0)] * 8 + [(40.0, -80.0), (41.0, -82.0)])
    assert center["latitude"] == 38.9 and center["longitude"] == -77.0 and center["marks"] == 10
    assert geo.suggest_center([]) is None
    assert geo.near_ot_minutes({}) == 36 * 60 and geo.near_ot_minutes({geo.NEAR_OT_KEY: 30}) == 1800 and geo.near_ot_minutes({geo.NEAR_OT_KEY: "x"}) == 2160
    with pytest.raises(ValueError):
        svc.parse_period(END, START, END)
    with pytest.raises(ValueError):
        svc.parse_period(START, seedmod.date(2027, 8, 1), END)
