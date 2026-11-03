"""Migracion 024z contra Postgres REAL (pgserver) partiendo de la tabla vieja de 024x.

El deploy 1beeeae9 fallo porque 024z asumia que work_location_perimeters no existia: su
CREATE TABLE IF NOT EXISTS no hizo nada y el indice pidio una columna inexistente. Aqui se
corre la 024x real, se deja una fila vieja y se aplica 024z: debe funcionar, repetirse sin
error y conservar la fila. Si pgserver no esta instalado, se salta.
"""
from __future__ import annotations

import importlib.util
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

pgserver = pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.services import work_location_geo as geo  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
VOLTAGE = "f1e8f774-f052-49ca-880a-268805f07db0"
OTHER = "11111111-1111-4111-8111-111111111111"
# Columnas leidas de produccion el 2026-11-03, con alembic en 024y.
PROD_COLUMNS = ["id", "company_id", "work_location_id", "perimeter_id", "created_at"]
BASE_SCHEMA = """
CREATE TABLE companies (id uuid PRIMARY KEY, name text NOT NULL);
CREATE TABLE modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text UNIQUE NOT NULL);
CREATE TABLE company_modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid REFERENCES companies(id),
  module_id uuid REFERENCES modules(id), enabled boolean DEFAULT true, settings jsonb DEFAULT '{}'::jsonb);
CREATE TABLE employees (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL REFERENCES companies(id),
  full_name varchar(200), role varchar(80), status varchar(40) DEFAULT 'active')
"""


def _statements(filename: str, direction: str = "upgrade") -> list[str]:
    spec = importlib.util.spec_from_file_location(f"m_{filename}", ROOT / "migrations" / "versions" / f"{filename}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out: list[str] = []
    module.op = SimpleNamespace(execute=lambda sql: out.append(str(sql)))
    getattr(module, direction)()
    return out


async def _run(conn, statements) -> None:
    for stmt in statements:
        await conn.execute(text(stmt))


async def _columns(conn, table: str = "work_location_perimeters") -> list[str]:
    rows = await conn.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = :t ORDER BY ordinal_position
    """), {"t": table})
    return [r[0] for r in rows]


@pytest.fixture(scope="module")
def pg_url():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="cx_pg_024z_"), cleanup_mode="stop")
    yield server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)


@pytest.fixture()
async def old_db(pg_url):
    """Base limpia en el esquema de produccion antes de 024z, con una fila vieja."""
    engine = create_async_engine(pg_url)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await _run(conn, [s for s in BASE_SCHEMA.split(";") if s.strip()])
        for cid, name in ((VOLTAGE, "VOLTAGE"), (OTHER, "Otra")):
            await conn.execute(text("INSERT INTO companies (id, name) VALUES (CAST(:i AS uuid), :n)"), {"i": cid, "n": name})
        await _run(conn, _statements("024x_work_locations"))
        place = (await conn.execute(text("SELECT id::text FROM work_locations WHERE name = 'Virginia'"))).scalar()
        legacy = str(uuid.uuid4())
        row = (await conn.execute(text("""
            INSERT INTO work_location_perimeters (company_id, work_location_id, perimeter_id)
            VALUES (CAST(:c AS uuid), CAST(:l AS uuid), CAST(:p AS uuid)) RETURNING id::text, created_at
        """), {"c": VOLTAGE, "l": place, "p": legacy})).one()
    yield SimpleNamespace(engine=engine, place=place, legacy_perimeter=legacy, legacy_id=row[0], legacy_created=row[1],
                          maker=async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False))
    await engine.dispose()


async def _switch_on(conn, company: str) -> None:
    await conn.execute(text("INSERT INTO modules (code) VALUES ('reports') ON CONFLICT DO NOTHING"))
    await conn.execute(text("""
        INSERT INTO company_modules (company_id, module_id, settings)
        SELECT CAST(:c AS uuid), id, '{"reports_board": true}'::jsonb FROM modules WHERE code = 'reports'
    """), {"c": company})


def test_revision_corta_y_no_crea_ni_borra_la_tabla_vieja():
    src = (ROOT / "migrations" / "versions" / "024z_reports_board.py").read_text(encoding="utf-8")
    upgrade = src.split("def upgrade")[1].split("def downgrade")[0].upper()
    assert "CREATE TABLE IF NOT EXISTS WORK_LOCATION_PERIMETERS" not in upgrade, "esa sentencia no hace nada sobre la tabla de 024x"
    for verb in ("DROP TABLE", "DROP COLUMN", "DELETE FROM", "TRUNCATE"):
        assert verb not in upgrade, verb
    downgrade = src.split("def downgrade")[1].upper()
    assert "DROP TABLE IF EXISTS WORK_LOCATION_PERIMETERS" not in downgrade, "la tabla es de 024x"
    assert len("024z_reports_board") <= 32


async def test_024x_deja_el_mismo_esquema_que_produccion(old_db):
    async with old_db.engine.connect() as conn:
        assert await _columns(conn) == PROD_COLUMNS


async def test_024z_corre_dos_veces_sobre_la_tabla_vieja_sin_perder_la_fila(old_db):
    for _ in range(2):  # idempotente
        async with old_db.engine.begin() as conn:
            await _run(conn, _statements("024z_reports_board"))
    async with old_db.engine.connect() as conn:
        assert await _columns(conn) == PROD_COLUMNS + ["name", "latitude", "longitude", "radius_m", "created_by", "updated_at"]
        assert "location_id" in await _columns(conn, "work_location_supervisors")
        row = (await conn.execute(text("SELECT id::text, company_id::text, work_location_id::text, perimeter_id::text, created_at, radius_m, latitude FROM work_location_perimeters"))).all()
        assert [tuple(r) for r in row] == [(old_db.legacy_id, VOLTAGE, old_db.place, old_db.legacy_perimeter, old_db.legacy_created, 300, None)]
        index = (await conn.execute(text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_work_location_perimeters_place'"))).scalar()
        assert "(company_id, work_location_id)" in index


async def test_la_unicidad_de_la_geocerca_vieja_sigue_y_los_nulos_caben(old_db):
    async with old_db.engine.begin() as conn:
        await _run(conn, _statements("024z_reports_board"))
    with pytest.raises(IntegrityError):
        async with old_db.engine.begin() as conn:
            await conn.execute(text("""
                INSERT INTO work_location_perimeters (company_id, work_location_id, perimeter_id)
                VALUES (CAST(:c AS uuid), CAST(:l AS uuid), CAST(:p AS uuid))
            """), {"c": VOLTAGE, "l": old_db.place, "p": old_db.legacy_perimeter})
    async with old_db.engine.begin() as conn:
        for name in ("A", "B"):
            await conn.execute(text("""
                INSERT INTO work_location_perimeters (company_id, work_location_id, name, latitude, longitude)
                VALUES (CAST(:c AS uuid), CAST(:l AS uuid), :n, 1, 1)
            """), {"c": VOLTAGE, "l": old_db.place, "n": name})


async def test_el_board_guarda_lee_y_mide_sin_tocar_la_fila_vieja(old_db):
    async with old_db.engine.begin() as conn:
        await _run(conn, _statements("024z_reports_board"))
        await _switch_on(conn, VOLTAGE)
        emp = (await conn.execute(text("""
            INSERT INTO employees (company_id, full_name, role, work_location_id)
            VALUES (CAST(:c AS uuid), 'Persona Inventada', 'supervisor', CAST(:l AS uuid)) RETURNING id::text
        """), {"c": VOLTAGE, "l": old_db.place})).scalar()
    async with old_db.maker() as db:
        assert await geo.perimeters_by_place(db, VOLTAGE) == {}, "la fila vieja no tiene centro: no es perimetro del Board"
        assert await geo.stamp_or_none(db, VOLTAGE, emp, 38.9, -77.0) is None
        body = {"perimeters": [{"name": "Bodega", "latitude": 38.9, "longitude": -77.0, "radius_m": 300},
                               {"name": "Patio", "latitude": 38.95, "longitude": -77.1}], "supervisors": [emp]}
        for _ in range(2):  # guardar otra vez reemplaza, no duplica
            saved = await geo.save_place(db, VOLTAGE, old_db.place, body, actor="dueno@voltage")
        assert [p["name"] for p in saved["perimeters"]] == ["Bodega", "Patio"] and saved["perimeters"][1]["radius_m"] == 300
        assert [s["employee_id"] for s in saved["supervisors"]] == [emp]
        assert (await geo.stamp_or_none(db, VOLTAGE, emp, 38.9, -77.0))["matched_perimeter_name"] == "Bodega"
        assert (await geo.stamp_or_none(db, VOLTAGE, emp, 10.0, 10.0))["gps_status"] == "outside"
        await geo.save_place(db, VOLTAGE, old_db.place, {"perimeters": [], "supervisors": []}, actor="dueno@voltage")
        assert await geo.perimeters_by_place(db, VOLTAGE) == {}
        left = (await db.execute(text("SELECT id::text FROM work_location_perimeters"))).scalars().all()
        assert left == [old_db.legacy_id], "vaciar el lugar no borra la fila vieja"


async def test_el_lugar_de_otra_empresa_no_se_puede_guardar_ni_leer(old_db):
    async with old_db.engine.begin() as conn:
        await _run(conn, _statements("024z_reports_board"))
    async with old_db.maker() as db:
        with pytest.raises(geo.Invalid):
            await geo.save_place(db, OTHER, old_db.place, {"perimeters": [{"name": "X", "latitude": 1, "longitude": 1}], "supervisors": []}, actor="otra")
        await db.rollback()
        await geo.save_place(db, VOLTAGE, old_db.place, {"perimeters": [{"name": "X", "latitude": 1, "longitude": 1}], "supervisors": []}, actor="dueno")
        assert await geo.perimeters_by_place(db, OTHER) == {}


async def test_downgrade_vuelve_a_024x_conserva_la_fila_y_se_puede_subir_otra_vez(old_db):
    async with old_db.engine.begin() as conn:
        await _run(conn, _statements("024z_reports_board"))
    async with old_db.maker() as db:
        await geo.save_place(db, VOLTAGE, old_db.place, {"perimeters": [{"name": "X", "latitude": 1, "longitude": 1}], "supervisors": []}, actor="dueno")
    for _ in range(2):  # idempotente
        async with old_db.engine.begin() as conn:
            await _run(conn, _statements("024z_reports_board", "downgrade"))
    async with old_db.engine.connect() as conn:
        assert await _columns(conn) == PROD_COLUMNS
        assert await _columns(conn, "work_location_supervisors") == []
        ids = (await conn.execute(text("SELECT id::text FROM work_location_perimeters"))).scalars().all()
        assert ids == [old_db.legacy_id]
    async with old_db.engine.begin() as conn:
        await _run(conn, _statements("024z_reports_board"))
    async with old_db.engine.connect() as conn:
        assert "latitude" in await _columns(conn)
