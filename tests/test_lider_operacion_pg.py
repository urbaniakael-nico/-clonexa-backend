"""Lider de operacion contra Postgres REAL (pgserver), con rutas y guardia reales: el lider de
Alabama ve solo Alabama; Virginia, Nomina, tarifas y escrituras = 403; el Supervisor de otra
operacion o quien no es Supervisor no entra; bloqueo por intentos; la consola crea solo con
Supervisores de esa operacion. Datos inventados: tests/fixtures/reports_board_seed.py."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI

pgserver = pytest.importorskip("pgserver")

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

import app.main as app_main  # noqa: E402
from app.api.deps import get_db  # noqa: E402
from app.api.v1.endpoints import company_users as cu  # noqa: E402
from app.api.v1.router import api_router  # noqa: E402
from app.models.auth import CompanyUser  # noqa: E402
from app.services import auth_service  # noqa: E402
from app.services import lider_operacion as svc  # noqa: E402
from app.web import brand_inject  # noqa: E402
from app.web.client_routes import _leader_html  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("reports_board_seed", ROOT / "tests" / "fixtures" / "reports_board_seed.py")
seedmod = importlib.util.module_from_spec(spec)
sys.modules["reports_board_seed"] = seedmod
spec.loader.exec_module(seedmod)
NOW, START, END = seedmod.NOW, seedmod.START, seedmod.END
ALABAMA_PEOPLE = {"Alma Ruiz", "Elena Gómez", "Felipe Soto", "Gabriel Luna", "Helena Ríos", "Iván Mena"}
MONEY = ("gross", "net_amount", "hourly_rate", "rate_pending", "amount", "deduction", "document")


@pytest.fixture(scope="module")
def pg_url():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="cx_pg_lo_"), cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await seedmod.create_schema(conn)
            await conn.run_sync(lambda sync: CompanyUser.__table__.create(sync))
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
    """Una empresa, sus operaciones, el cliente HTTP y una sesion de Admin V2 que se enciende a mano."""
    import app.web.admin_v2_routes as admin_routes

    admin = SimpleNamespace(on=False)
    monkeypatch.setattr(admin_routes, "_active_session", AsyncMock(side_effect=lambda *_: admin.on))
    monkeypatch.setattr(cu, "active_admin_v2_session", AsyncMock(side_effect=lambda *_: admin.on))
    monkeypatch.setattr(cu, "_cx_company_or_404_019d", AsyncMock(side_effect=lambda _db, cid: SimpleNamespace(id=cid, name="VOLTAGE")))

    async with maker() as db:
        real = db.execute

        async def no_ext(stmt, *args, **kwargs):  # pgserver no trae pgcrypto; gen_random_uuid ya es nativo
            if "CREATE EXTENSION" in str(stmt):
                return None
            return await real(stmt, *args, **kwargs)

        db.execute = no_ext
        ids = await seedmod.seed(db)
        ids["alma"] = await seedmod.person(db, ids["company"], "Alma Ruiz", "AL-900", ids["al"], role="Supervisor", email="alma@voltage.test")

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
        yield SimpleNamespace(ids=ids, cid=ids["company"], client=client, admin=admin, maker=maker)


async def _create(w, place, employee, username, password="clave-segura-1"):
    w.admin.on = True
    try:
        return await w.client.post(f"/api/v1/lider-operacion/consola/companies/{w.cid}/lideres",
                                   json={"work_location_id": place, "employee_id": employee, "username": username, **({"password": password} if password else {})})
    finally:
        w.admin.on = False


async def _login(w, username, lugar, password="clave-segura-1"):
    return await w.client.post(f"/api/v1/companies/{w.cid}/mini-panel-login", json={"username": username, "password": password, "panel_type": "lider_operacion", "lugar": lugar})


async def _alabama(w):
    created = await _create(w, w.ids["al"], w.ids["alma"], "alma.lider")
    assert created.status_code == 200, created.text
    res = await _login(w, "alma.lider", "alabama")
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _panel(w, tail):
    return f"/api/v1/lider-operacion/companies/{w.cid}/{tail}"


@pytest.mark.asyncio
async def test_lider_de_alabama_ve_solo_alabama(world):
    w = world
    auth = await _alabama(w)

    crm = await w.client.get(_panel(w, "crm"), headers=auth)
    assert crm.status_code == 200, crm.text
    body = crm.json()
    assert body["operation"]["name"] == "Alabama" and body["operation"]["accent"] == 1 and body["operation"]["abbr"] == "CT"
    assert {p["name"] for p in body["people"]} == ALABAMA_PEOPLE
    names = [p["name"] for p in body["people"]]
    assert names == sorted(names, key=svc.reports_board.sort_key), "lista A-Z"
    assert not (w.ids["va"] in crm.text or "Bruno" in crm.text or "Virginia" in crm.text)
    for word in MONEY + ("lat", "lng"):
        assert f'"{word}"' not in crm.text, word

    rep = await w.client.get(_panel(w, "reportes"), params={"start": START.isoformat(), "end": END.isoformat()}, headers=auth)
    assert rep.status_code == 200, rep.text
    board = rep.json()
    assert [o["name"] for o in board["operations"]] == ["Alabama"] and board["operations"][0]["color"] == 1
    assert {p["name"] for p in board["operations"][0]["people"]} == ALABAMA_PEOPLE
    assert board["scope"]["limited"] is True and board["can_manage"] is False
    assert "Virginia" not in rep.text and "Sin lugar" not in rep.text
    for word in MONEY:
        assert word not in rep.text, word
    # La linea de tiempo sigue completa: mismas horas que el Board de gerencia.
    felipe = next(p for p in board["operations"][0]["people"] if p["name"] == "Felipe Soto")
    assert felipe["payable"] == 2640 and felipe["overtime"] == 240 and felipe["days"][0]["shifts"]

    live = await w.client.get(_panel(w, "reportes"), params={"part": "live"}, headers=auth)
    assert set(live.json()["clocks"]) == {w.ids["al"]} and w.ids["bruno"] not in live.json()["people"]

    home = await w.client.get(_panel(w, "inicio"), headers=auth)
    assert home.status_code == 200, home.text
    data = home.json()
    assert data["me"]["name"] == "Alma Ruiz" and data["operation"]["name"] == "Alabama" and data["crm"]["total"] == len(ALABAMA_PEOPLE)


@pytest.mark.asyncio
async def test_inicio_y_crm_con_hora_fija(world):
    w = world
    async with w.maker() as db:
        place = next(p for p in await svc.places(db, w.cid) if p["id"] == w.ids["al"])
        crm = await svc.crm(db, w.cid, place, now=NOW)
        people = {p["name"]: p for p in crm["people"]}
        assert people["Gabriel Luna"]["state"] == "to_confirm" and people["Gabriel Luna"]["minutes"] > 0
        assert people["Helena Ríos"]["state"] == "to_confirm"
        assert people["Alma Ruiz"]["state"] == "no_shift" and people["Alma Ruiz"]["last_mark"] is None
        assert people["Gabriel Luna"]["last_mark"]["a"] == "CT"
        assert crm["counts"]["to_confirm"] == 2 and crm["counts"]["total"] == 6

        user = SimpleNamespace(settings_json={"mini_panel": {"employee_id": w.ids["alma"]}}, full_name="Alma Ruiz")
        home = await svc.inicio(db, w.cid, user, place, now=NOW)
        assert home["reports"]["week"] == {"start": "2026-11-01", "end": "2026-11-07"}
        assert home["reports"]["hours_minutes"] > 0 and home["reports"]["alerts"] >= 2
        assert home["operation"]["local_time"] == "12:00"


@pytest.mark.asyncio
async def test_virginia_nomina_tarifas_y_escrituras_403(world):
    w = world
    auth = await _alabama(w)
    for query in ({"work_location_id": w.ids["va"]}, {"lugar": "virginia"}, {"lugar": "VA"}):
        for tail in ("crm", "inicio", "reportes"):
            res = await w.client.get(_panel(w, tail), params=query, headers=auth)
            assert res.status_code == 403, f"{tail} {query}: {res.status_code}"
            assert "Alabama" in res.json()["detail"]
    cid = w.cid
    for method, path in [
        ("GET", f"/api/v1/reports-board/companies/{cid}"),
        ("GET", f"/api/v1/reports-board/companies/{cid}/marks.csv"),
        ("GET", f"/api/v1/work-locations/companies/{cid}/board"),
        ("GET", f"/api/v1/us-payroll/companies/{cid}"),
        ("GET", f"/api/v1/payroll/companies/{cid}/period"),
        ("GET", f"/api/v1/employees?company_id={cid}"),
        ("POST", f"/api/v1/work-locations/companies/{cid}/assign"),
        ("PUT", f"/api/v1/reports-board/companies/{cid}/places/{w.ids['al']}"),
        ("PUT", f"/api/v1/work-locations/companies/{cid}/locations"),
        ("POST", f"/api/v1/companies/{cid}/mini-panel-change-password?panel_type=lider_operacion"),
        ("GET", f"/api/v1/companies/{cid}/mini-panel-session?panel_type=lider_operacion"),
        ("POST", f"/api/v1/lider-operacion/consola/companies/{cid}/lideres"),
    ]:
        res = await w.client.request(method, path, headers=auth, json={} if method != "GET" else None)
        assert res.status_code == 403, f"{method} {path}: {res.status_code}"
    # Su salida si funciona, y despues la sesion ya no sirve.
    assert (await w.client.post("/api/v1/auth/logout", headers=auth)).status_code == 200
    assert (await w.client.get(_panel(w, "crm"), headers=auth)).status_code in (401, 403)


@pytest.mark.asyncio
async def test_quien_no_cumple_no_entra(world):
    w = world
    assert (await _create(w, w.ids["va"], w.ids["sofia"], "sofia.lider")).status_code == 200
    assert (await _create(w, w.ids["al"], w.ids["alma"], "alma.lider")).status_code == 200

    # Lider de Virginia en el enlace de Alabama, y al reves.
    res = await _login(w, "sofia.lider", "alabama")
    assert res.status_code == 403 and res.json()["detail"] == "Este panel es solo para el líder de Alabama"
    res = await _login(w, "alma.lider", "virginia")
    assert res.status_code == 403 and res.json()["detail"] == "Este panel es solo para el líder de Virginia"
    # Clave mala, usuario desconocido y enlace sin operacion no revelan nada.
    assert (await _login(w, "alma.lider", "alabama", "otra-clave")).status_code == 401
    assert (await _login(w, "nadie", "alabama")).status_code == 401
    assert (await _login(w, "alma.lider", "texas")).status_code == 400

    # Usuario de la empresa que no es lider, con su clave correcta.
    async with w.maker() as db:
        db.add(CompanyUser(company_id=UUID(w.cid), email="ventas@voltage.test", password_hash=auth_service.hash_password("clave-segura-1"), full_name="Ventas",
                           role="operator", status="active", must_change_password=False, failed_login_attempts=0,
                           settings_json={"mini_panel": {"enabled": True, "type": "sales", "username": "ventas1", "employee_id": w.ids["alma"]}}))
        await db.commit()
    res = await _login(w, "ventas1", "alabama")
    assert res.status_code == 403 and res.json()["detail"] == "Este panel es solo para el líder de Alabama"
    assert (await _login(w, "ventas1", "alabama", "mala")).status_code == 401


@pytest.mark.asyncio
async def test_pierde_el_acceso_de_inmediato_si_cambia_de_rol_o_de_lugar(world):
    w = world
    auth = await _alabama(w)
    assert (await w.client.get(_panel(w, "crm"), headers=auth)).status_code == 200

    async def employee(sql):
        async with w.maker() as db:
            await db.execute(text(sql), {"e": w.ids["alma"], "v": w.ids["va"], "a": w.ids["al"]})
            await db.commit()

    await employee("UPDATE employees SET role = 'operario' WHERE id = CAST(:e AS uuid)")
    res = await w.client.get(_panel(w, "crm"), headers=auth)
    assert res.status_code == 403 and res.json()["detail"] == "Este panel es solo para el líder de Alabama"
    assert (await _login(w, "alma.lider", "alabama")).status_code == 403

    await employee("UPDATE employees SET role = 'supervisor', work_location_id = CAST(:v AS uuid) WHERE id = CAST(:e AS uuid)")
    assert (await w.client.get(_panel(w, "crm"), headers=auth)).status_code == 403, "trasladada a Virginia"

    # Vale tambien estar en la lista de supervisores del lugar, con rol Supervisor.
    async with w.maker() as db:
        await db.execute(text("INSERT INTO work_location_supervisors (company_id, location_id, employee_id) VALUES (CAST(:c AS uuid), CAST(:a AS uuid), CAST(:e AS uuid))"),
                         {"c": w.cid, "a": w.ids["al"], "e": w.ids["alma"]})
        await db.commit()
    assert (await w.client.get(_panel(w, "crm"), headers=auth)).status_code == 200

    await employee("UPDATE employees SET status = 'inactive' WHERE id = CAST(:e AS uuid)")
    assert (await w.client.get(_panel(w, "crm"), headers=auth)).status_code == 403


@pytest.mark.asyncio
async def test_bloqueo_por_intentos_y_portal(world):
    w = world
    assert (await _create(w, w.ids["al"], w.ids["alma"], "alma.lider")).status_code == 200
    for _ in range(5):
        assert (await _login(w, "alma.lider", "alabama", "mala")).status_code == 401
    res = await _login(w, "alma.lider", "alabama")
    assert res.status_code == 403 and res.json()["detail"] == "Usuario temporalmente bloqueado."

    async with w.maker() as db:
        user = next(u for u in (await db.execute(select(CompanyUser).where(CompanyUser.company_id == UUID(w.cid)))).scalars() if auth_service.is_leader_user(u))
        user.locked_until = auth_service.utc_now() - timedelta(minutes=1)
        email = user.email
        await db.commit()
    assert (await _login(w, "alma.lider", "alabama")).status_code == 200, "pasado el bloqueo entra"

    # El correo interno no sirve en el portal: ni con la clave correcta.
    res = await w.client.post("/api/v1/auth/login", json={"email": email, "password": "clave-segura-1"})
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_interruptores_apagados(world):
    w = world
    auth = await _alabama(w)

    async def board(value):
        async with w.maker() as db:
            await db.execute(text("""UPDATE company_modules SET settings = settings || CAST(:s AS jsonb)
                                     WHERE company_id = CAST(:c AS uuid) AND module_id = (SELECT id FROM modules WHERE code = 'reports')"""),
                             {"c": w.cid, "s": json.dumps({"reports_board": value})})
            await db.commit()

    await board(False)
    assert (await w.client.get(_panel(w, "crm"), headers=auth)).status_code == 404
    assert (await _login(w, "alma.lider", "alabama")).status_code == 403
    w.admin.on = True
    assert (await w.client.get(f"/api/v1/lider-operacion/consola/companies/{w.cid}")).status_code == 404
    w.admin.on = False
    await board(True)
    assert (await w.client.get(_panel(w, "crm"), headers=auth)).status_code == 200


@pytest.mark.asyncio
async def test_otra_empresa_no_se_mezcla(world):
    w = world
    auth = await _alabama(w)
    async with w.maker() as db:
        other = await seedmod.company(db, "OTRA", board=True)
        await seedmod.place(db, other, "Alabama", "AL", "America/Chicago", 1)
    res = await w.client.get(f"/api/v1/lider-operacion/companies/{other}/crm", headers=auth)
    assert res.status_code == 403
    res = await w.client.post(f"/api/v1/companies/{other}/mini-panel-login", json={"username": "alma.lider", "password": "clave-segura-1", "panel_type": "lider_operacion", "lugar": "alabama"})
    assert res.status_code == 401, "los usuarios se buscan solo dentro de la empresa"


@pytest.mark.asyncio
async def test_consola(world):
    w = world
    url = f"/api/v1/lider-operacion/consola/companies/{w.cid}"
    assert (await w.client.get(url)).status_code == 401, "sin sesion"
    assert (await w.client.get(url, headers={"Authorization": "Bearer x"})).status_code == 403
    assert (await w.client.post(f"{url}/lideres", json={"work_location_id": w.ids["al"], "employee_id": w.ids["alma"], "username": "abc"})).status_code == 401

    w.admin.on = True
    data = (await w.client.get(url)).json()
    w.admin.on = False
    assert [p["name"] for p in data["places"]] == ["Virginia", "Alabama"], "de este a oeste"
    assert [p["accent"] for p in data["places"]] == [0, 1]
    va, al = data["places"]
    assert va["link"] == f"/mini-panel/login?company_id={w.cid}&type=lider_operacion&lugar=virginia"
    assert al["link"] == f"/mini-panel/login?company_id={w.cid}&type=lider_operacion&lugar=alabama"
    assert [s["name"] for s in va["supervisors"]] == ["Sofía Mora"] and [s["name"] for s in al["supervisors"]] == ["Alma Ruiz"], "solo Supervisores de ESA operacion"

    # Otra operacion, sin rol Supervisor, usuario y clave invalidos.
    assert (await _create(w, w.ids["va"], w.ids["alma"], "alma.lider")).status_code == 422
    assert (await _create(w, w.ids["al"], w.ids["felipe"], "felipe.lider")).status_code == 422
    assert (await _create(w, w.ids["al"], w.ids["alma"], "x")).status_code == 422
    assert (await _create(w, w.ids["al"], w.ids["alma"], "alma.lider", "corta")).status_code == 422

    # Clave escrita: nunca vuelve en la respuesta. Clave generada: una sola vez.
    typed = await _create(w, w.ids["al"], w.ids["alma"], "Alma.Lider", "clave-segura-1")
    assert typed.status_code == 200 and "temporary_password" not in typed.json() and "clave-segura-1" not in typed.text
    assert typed.json()["leader"]["username"] == "alma.lider"
    made = await _create(w, w.ids["va"], w.ids["sofia"], "sofia.lider", None)
    assert made.status_code == 200 and len(made.json()["temporary_password"]) >= 8
    assert (await _login(w, "sofia.lider", "virginia", made.json()["temporary_password"])).status_code == 200

    assert (await _create(w, w.ids["va"], w.ids["sofia"], "alma.lider")).status_code == 409, "usuario repetido"
    assert (await _create(w, w.ids["al"], w.ids["alma"], "otra.alma")).status_code == 409, "ya es lider"

    async with w.maker() as db:
        users = [u for u in (await db.execute(select(CompanyUser).where(CompanyUser.company_id == UUID(w.cid)))).scalars() if auth_service.is_leader_user(u)]
    assert {u.role for u in users} == {"lider_operacion"} and all(u.password_hash != "clave-segura-1" for u in users)
    w.admin.on = True
    listed = (await w.client.get(url)).json()["places"]
    w.admin.on = False
    assert [l["username"] for l in listed[1]["leaders"]] == ["alma.lider"] and listed[1]["leaders"][0]["valid"] is True


@pytest.mark.asyncio
async def test_clave_del_lider_solo_desde_la_consola(world):
    w = world
    made = await _create(w, w.ids["al"], w.ids["alma"], "alma.lider")
    uid = made.json()["leader"]["user_id"]
    url = f"/api/v1/companies/{w.cid}/mini-panel-users/{uid}/reset-password"
    assert (await w.client.post(url)).status_code == 401, "sin sesion no se cambia"
    w.admin.on = True
    res = await w.client.post(url)
    w.admin.on = False
    assert res.status_code == 200 and res.json()["temporary_password"]


@pytest.mark.asyncio
async def test_pantalla_de_ingreso(world, monkeypatch):
    w = world
    monkeypatch.setattr(brand_inject, "published_theme", AsyncMock(return_value=None))
    page = ROOT / "app" / "web" / "lider_operacion.html"

    def boot(resp):
        raw = resp.body.decode("utf-8").split("window.__CX_LIDER__=", 1)[1].split(";</script>", 1)[0]
        return json.loads(raw)

    async with w.maker() as db:
        good = boot(await _leader_html(page, db, w.cid, "alabama"))
        assert good["ok"] is True and good["name"] == "Alabama" and good["accent"] == 1 and good["abbr"] == "CT"
        assert boot(await _leader_html(page, db, w.cid, "texas")) == {"ok": False}
        assert boot(await _leader_html(page, db, "no-es-uuid", "alabama")) == {"ok": False}
        off = await seedmod.company(db, "SIN BOARD", board=False)
        await seedmod.place(db, off, "Alabama", "AL", "America/Chicago", 1)
        assert boot(await _leader_html(page, db, off, "alabama")) == {"ok": False}
