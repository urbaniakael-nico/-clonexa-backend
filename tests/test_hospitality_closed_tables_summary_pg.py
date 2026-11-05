"""Total de "Mesas cerradas hoy" (barman_music_layout) contra Postgres REAL (pgserver).

El panel solo carga 220 pedidos: el servidor debe sumar TODOS los cierres desde el
último "Generar cierre", sin mezclar empresas, y solo con el interruptor y sesión.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import uuid
from decimal import Decimal

import pytest

pgserver = pytest.importorskip("pgserver")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import app.main as app_main  # noqa: E402
from app.api.deps import get_db  # noqa: E402
from app.api.v1.endpoints import hospitality as hsp  # noqa: E402
from app.api.v1.endpoints.companies import require_admin_v2_or_tenant_company_user  # noqa: E402

SCHEMA = [
    "CREATE TABLE companies (id uuid PRIMARY KEY, name text, status text DEFAULT 'active')",
    "CREATE TABLE modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text UNIQUE NOT NULL)",
    """CREATE TABLE company_modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid, module_id uuid,
       enabled boolean DEFAULT true, settings jsonb DEFAULT '{}'::jsonb, updated_at timestamptz DEFAULT now())""",
    """CREATE TABLE hospitality_orders (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL,
       table_number varchar(120) NOT NULL, table_key varchar(120) NOT NULL, status varchar(40) NOT NULL,
       total numeric(14,2) NOT NULL DEFAULT 0, archived_at timestamptz NULL)""",
]
TTM, OTRA, APAGADA, MODULO_OFF = (str(uuid.uuid4()) for _ in range(4))


def _run(url: str, statements: list[tuple[str, dict]]):
    async def go():
        engine = create_async_engine(url, poolclass=NullPool)
        async with engine.begin() as conn:
            for sql, params in statements:
                await conn.execute(text(sql), params)
        await engine.dispose()
    asyncio.run(go())


@pytest.fixture(scope="module")
def pg_url():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="cx_pg_barman_"), cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)
    seed = [(sql, {}) for sql in SCHEMA]
    seed.append(("INSERT INTO modules (code) VALUES ('qr')", {}))
    for company, enabled, settings in (
        (TTM, True, {"barman_music_layout": True}),
        (OTRA, True, {"barman_music_layout": True}),
        (APAGADA, True, {"qr_bar_menu": True}),
        (MODULO_OFF, False, {"barman_music_layout": True}),
    ):
        seed.append(("INSERT INTO companies (id, name) VALUES (:id, 'x')", {"id": company}))
        seed.append((
            """INSERT INTO company_modules (company_id, module_id, enabled, settings)
               SELECT :id, id, :enabled, CAST(:settings AS jsonb) FROM modules WHERE code = 'qr'""",
            {"id": company, "enabled": enabled, "settings": json.dumps(settings)},
        ))
    order = "INSERT INTO hospitality_orders (company_id, table_number, table_key, status, total, archived_at) VALUES (:c, :n, :k, :s, :t, :a)"
    # 300 cierres en 60 mesas: más de los 220 pedidos que carga el panel.
    for i in range(300):
        table = i % 60
        seed.append((order, {"c": TTM, "n": f"Mesa {table}", "k": f"mesa {table}", "s": "cerrado", "t": Decimal("1000.10"), "a": None}))
    for status_name, total in (("pendiente", 7), ("alistando", 7), ("entregado", 7), ("cancelado", 7)):
        seed.append((order, {"c": TTM, "n": "Mesa 0", "k": "mesa 0", "s": status_name, "t": total, "a": None}))
    seed.append((order, {"c": OTRA, "n": "Mesa 1", "k": "mesa 1", "s": "cerrado", "t": 555, "a": None}))
    seed.append((order, {"c": APAGADA, "n": "Mesa 1", "k": "mesa 1", "s": "cerrado", "t": 555, "a": None}))
    seed.append((order, {"c": MODULO_OFF, "n": "Mesa 1", "k": "mesa 1", "s": "cerrado", "t": 555, "a": None}))
    _run(url, seed)
    # Ya pasó por "Generar cierre": no cuenta. Se inserta aparte con fecha del servidor.
    _run(url, [("""INSERT INTO hospitality_orders (company_id, table_number, table_key, status, total, archived_at)
                   VALUES (:c, 'Mesa 99', 'mesa 99', 'cerrado', 999999, now())""", {"c": TTM})])
    yield url


@pytest.fixture
def client(pg_url):
    hsp._storage_ready = True

    async def db_dep():
        engine = create_async_engine(pg_url, poolclass=NullPool)
        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
            yield session
        await engine.dispose()

    app_main.app.dependency_overrides[get_db] = db_dep
    c = TestClient(app_main.app)
    yield c
    app_main.app.dependency_overrides.pop(get_db, None)
    app_main.app.dependency_overrides.pop(require_admin_v2_or_tenant_company_user, None)


def _login():
    app_main.app.dependency_overrides[require_admin_v2_or_tenant_company_user] = lambda: None


def _url(company: str) -> str:
    return f"/api/v1/hospitality/companies/{company}/closed-tables-summary"


def test_hospitality_resumen_exige_sesion(client):
    assert client.get(_url(TTM)).status_code in {401, 403}


def test_hospitality_resumen_suma_todos_los_cierres_sin_limite_de_220(client):
    _login()
    body = client.get(_url(TTM)).json()
    assert body["orders"] == 300
    assert body["tables"] == 60
    assert body["total"] == 300030.0, "300 x 1000,10; sin abiertos, cancelados ni archivados"


def test_hospitality_resumen_no_mezcla_empresas(client):
    _login()
    body = client.get(_url(OTRA)).json()
    assert (body["tables"], body["orders"], body["total"]) == (1, 1, 555.0)
    assert body["company_id"] == OTRA


@pytest.mark.parametrize("company", [APAGADA, MODULO_OFF])
def test_hospitality_resumen_solo_con_el_interruptor(client, company):
    _login()
    response = client.get(_url(company))
    assert response.status_code == 404
    assert "total" not in response.json()


def test_hospitality_resumen_queda_en_cero_tras_generar_cierre(client, pg_url):
    _login()
    # Lo que hace _create_day_closure con los pedidos de la empresa.
    _run(pg_url, [("UPDATE hospitality_orders SET archived_at = now() WHERE company_id = :c AND archived_at IS NULL", {"c": OTRA})])
    body = client.get(_url(OTRA)).json()
    assert (body["tables"], body["orders"], body["total"]) == (0, 0, 0.0)


def test_hospitality_resumen_agrupa_las_mesas_igual_que_el_panel():
    key = hsp._closed_table_key
    assert key("mesa 4", "Mesa 4") == key("Mesa-4", None) == "mesa_4"
    assert key("", "Terraza Niño") == "terraza_nino"
    assert key(None, None) == "mesa"
    assert key("---", None) == "cuenta"
