"""Enlace corto del Lider de operacion: un codigo de 8 por operacion que lleva a SU ingreso (con
Postgres real), los largos siguen, codigo invalido con aviso y limite a quien prueba al azar."""
from __future__ import annotations

import asyncio
import importlib.util
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.services import short_links as sl
from app.web.client_routes import register_client_portal

ROOT = Path(__file__).resolve().parents[1]
VOLTAGE = "f1e8f774-f052-49ca-880a-268805f07db0"
OTHER = "d63cf68c-be5b-4a30-aee4-341973018db1"


def _migration():
    spec = importlib.util.spec_from_file_location("m025b", ROOT / "migrations" / "versions" / "025b_lider_short_links.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def request(headers=None, host="9.9.9.9"):
    return SimpleNamespace(headers=headers or {}, client=SimpleNamespace(host=host))


# ------------------------------------------------------------------ reglas puras
def test_destino_conserva_la_operacion_solo_del_lider():
    long = f"/mini-panel/login?company_id={VOLTAGE}&type=lider_operacion&lugar=alabama"
    assert sl.panel_target(VOLTAGE, long) == long
    assert sl.panel_target(VOLTAGE, f"/mini-panel/login?company_id={VOLTAGE}&type=sales&lugar=alabama") == f"/mini-panel/login?company_id={VOLTAGE}&type=sales"
    assert "lugar" not in sl.panel_target(VOLTAGE, f"/mini-panel/login?company_id={VOLTAGE}&type=lider_operacion&lugar=https://evil.com")
    assert sl.panel_target(OTHER, long) == "", "nunca otra empresa"


def test_codigo_de_ocho_sin_caracteres_confusos():
    codes = {sl.new_code(sl.LEADER_CODE_LENGTH) for _ in range(200)}
    assert len(codes) == 200
    assert all(len(c) == 8 and sl.clean_code(c) == c and not set(c) & set("01OIL") for c in codes)
    assert len(sl.new_code()) == sl.PANEL_CODE_LENGTH, "los demas links no cambian"


def test_limite_solo_con_fallos_y_vuelve_a_abrir():
    limit = sl.MissLimiter(limit=3, window=100)
    for i in range(3):
        assert not limit.blocked("a", now=float(i))
        limit.note("a", now=float(i))
    assert limit.blocked("a", now=5.0) and not limit.blocked("b", now=5.0)
    assert not limit.blocked("a", now=101.5), "envejecen los primeros fallos"
    assert sl.MISS_LIMIT == 20 and sl.MISS_WINDOW_SECONDS == 600


def test_la_ip_no_se_puede_falsear_desde_el_cliente():
    assert sl.client_ip(request({"x-real-ip": "1.1.1.1", "x-forwarded-for": "6.6.6.6, 1.1.1.1"})) == "1.1.1.1"
    assert sl.client_ip(request({"x-forwarded-for": "6.6.6.6, 2.2.2.2"})) == "2.2.2.2", "la ultima la puso el proxy"
    assert sl.client_ip(request()) == "9.9.9.9"


def test_migracion_dos_codigos_validos_y_revision_corta():
    m = _migration()
    assert len(m.revision) <= 32 and m.down_revision == "025a_attendance_adjustments"
    assert set(m.LINKS) == {"virginia", "alabama"} and len(set(m.LINKS.values())) == 2
    assert all(len(c) == 8 and sl.clean_code(c) == c for c in m.LINKS.values())
    # Sin company_id ni nada legible en el codigo.
    assert all(VOLTAGE[:8].upper() not in c for c in m.LINKS.values())


# ------------------------------------------------------------------ la ruta /c/CODIGO
@pytest.fixture()
def route(monkeypatch):
    table = {"GOODCODE": f"/mini-panel/login?company_id={VOLTAGE}&type=lider_operacion&lugar=alabama"}
    resolver = AsyncMock(side_effect=lambda _db, code: table.get(code, ""))
    monkeypatch.setattr(sl, "resolve", resolver)
    monkeypatch.setattr(sl, "MISSES", sl.MissLimiter(limit=20, window=600))
    app = FastAPI()
    register_client_portal(app)

    async def no_db():
        yield SimpleNamespace(rollback=AsyncMock())

    app.dependency_overrides[get_db] = no_db
    return SimpleNamespace(client=TestClient(app, follow_redirects=False), resolver=resolver)


def test_codigo_bueno_redirige_y_malo_avisa(route):
    good = route.client.get("/c/GOODCODE")
    assert good.status_code == 302 and "lugar=alabama" in good.headers["location"] and good.headers["cache-control"] == "no-store"
    bad = route.client.get("/c/ZZZZZZZZ")
    assert bad.status_code == 404 and "Este link no existe o ya no sirve" in bad.text


def test_probar_al_azar_termina_en_429_y_el_bueno_tampoco_se_distingue(route):
    headers = {"x-real-ip": "5.5.5.5"}
    for i in range(20):
        assert route.client.get(f"/c/AAAAAA{i:02d}", headers=headers).status_code == 404
    calls = route.resolver.await_count
    blocked = route.client.get("/c/GOODCODE", headers=headers)
    assert blocked.status_code == 429 and "Demasiados intentos" in blocked.text and "Too many attempts" in blocked.text and blocked.headers["retry-after"] == "600"
    assert route.resolver.await_count == calls, "bloqueada, no consulta"
    # Cambiar la X-Forwarded-For no ayuda, y otra IP sigue normal.
    spoof = route.client.get("/c/AAAAAA99", headers={**headers, "x-forwarded-for": "7.7.7.7"})
    assert spoof.status_code == 429
    assert route.client.get("/c/GOODCODE", headers={"x-real-ip": "6.6.6.6"}).status_code == 302


def test_usar_un_link_bueno_no_cuenta_ni_una_falla_de_la_base(route):
    headers = {"x-real-ip": "5.5.5.5"}
    for _ in range(50):
        assert route.client.get("/c/GOODCODE", headers=headers).status_code == 302
    route.resolver.side_effect = RuntimeError("base caida")
    for _ in range(30):
        assert route.client.get("/c/GOODCODE", headers=headers).status_code == 404


# ------------------------------------------------------------------ con Postgres real
pgserver = pytest.importorskip("pgserver")


@pytest.fixture(scope="module")
def pg_url():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.models.auth import CompanyUser
    from tests.test_lider_operacion_pg import seedmod

    server = pgserver.get_server(tempfile.mkdtemp(prefix="cx_pg_ls_"), cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await seedmod.create_schema(conn)
            await conn.run_sync(lambda sync: CompanyUser.__table__.create(sync))
            await conn.execute(text("""
                CREATE TABLE short_links (code varchar(16) PRIMARY KEY, company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE, kind varchar(20) NOT NULL DEFAULT 'mini_panel',
                  target varchar(500) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), CONSTRAINT uq_short_links_target UNIQUE (company_id, target))"""))
        await engine.dispose()

    asyncio.run(setup())
    yield url


@pytest.mark.asyncio
async def test_migracion_consola_y_redireccion_real(pg_url, monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    import app.web.admin_v2_routes as admin_routes
    from app.api.v1.router import api_router
    from tests.test_lider_operacion_pg import seedmod

    engine = create_async_engine(pg_url)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(admin_routes, "_active_session", AsyncMock(return_value=True))
    monkeypatch.setattr(sl, "MISSES", sl.MissLimiter())

    # La empresa aun no existe: la migracion no inserta nada ni falla.
    m = _migration()
    statements = []
    m.op = SimpleNamespace(execute=statements.append)
    m.upgrade()

    async def migrate():
        async with engine.begin() as conn:
            for stmt in statements:
                await conn.execute(text(stmt))

    await migrate()
    async with maker() as db:
        assert (await db.execute(text("SELECT count(*) FROM short_links"))).scalar() == 0
        ids = await seedmod.seed(db, cid=VOLTAGE)
    await migrate()
    await migrate()  # repetirla no duplica

    async def override():
        async with maker() as session:
            yield session

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    register_client_portal(app)
    app.dependency_overrides[get_db] = override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", follow_redirects=False) as client:
        places = (await client.get(f"/api/v1/lider-operacion/consola/companies/{VOLTAGE}")).json()["places"]
        by_name = {p["name"]: p for p in places}
        # La consola muestra los MISMOS codigos de la migracion, sin crear otros.
        assert by_name["Virginia"]["short_link"] == f"/c/{m.LINKS['virginia']}"
        assert by_name["Alabama"]["short_link"] == f"/c/{m.LINKS['alabama']}"
        for name, lugar in (("Virginia", "virginia"), ("Alabama", "alabama")):
            res = await client.get(by_name[name]["short_link"])
            assert res.status_code == 302 and res.headers["location"] == by_name[name]["link"]
            assert res.headers["location"].endswith(f"&type=lider_operacion&lugar={lugar}")
            assert VOLTAGE not in by_name[name]["short_link"], "sin company_id visible"
        assert (await client.get(f"/c/{m.LINKS['virginia'].lower()}")).status_code == 302, "sin distinguir mayusculas"
        assert (await client.get("/c/ZZZZZZZZ")).status_code == 404

        # Una operacion nueva recibe un codigo de 8 al abrir la consola, y siempre el mismo.
        async with maker() as db:
            await seedmod.place(db, VOLTAGE, "Texas", "TX", "America/Chicago", 3)
        first = {p["name"]: p for p in (await client.get(f"/api/v1/lider-operacion/consola/companies/{VOLTAGE}")).json()["places"]}["Texas"]["short_link"]
        again = {p["name"]: p for p in (await client.get(f"/api/v1/lider-operacion/consola/companies/{VOLTAGE}")).json()["places"]}["Texas"]["short_link"]
        assert first == again and len(first) == len("/c/") + 8
        assert UUID(ids["company"]) == UUID(VOLTAGE)
    await engine.dispose()
