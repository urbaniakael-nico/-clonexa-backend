"""Referencias v2 contra Postgres REAL con asyncpg (pgserver).

- Contrato del bot: bot-options, sizes, el listado, el resumen y las consultas
  directas del bot de Velvet devuelven EXACTAMENTE lo mismo antes y despues de
  la migracion 024e, de clasificar y de registrar movimientos.
- Aislamiento por empresa, clasificar solo toca tres columnas, crear desde el
  catalogo produce las mismas filas que la creacion actual, el balance cuadra
  y anular saca del balance sin borrar.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import tempfile
import uuid

import pytest

pgserver = pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.api.v1.endpoints import references_v1 as refs  # noqa: E402
from app.api.v1.endpoints import velvet_bot_v1 as vbot  # noqa: E402
from app.services import references_v2 as rv2  # noqa: E402
from tests.test_brand_pg import BASE_SCHEMA  # noqa: E402


def _migration_024e() -> list[str]:
    statements: list[str] = []

    class Op:
        def execute(self, sql):
            statements.append(str(sql))

    module = importlib.import_module("migrations.versions.024e_reference_cuts")
    module.op = Op()
    module.upgrade()
    return statements


@pytest.fixture(scope="module")
def pg_url():
    folder = tempfile.mkdtemp(prefix="cx_pg_refs_")
    server = pgserver.get_server(folder, cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            for stmt in [s for s in BASE_SCHEMA.split(";") if s.strip()]:
                await conn.execute(text(stmt))
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as db:  # las tablas de siempre, como las crea la app hoy
            await refs.ensure_storage(db)
            # La tabla de cierres que lee el resumen (production_v1.ensure_storage pide pgcrypto).
            await db.execute(text("""CREATE TABLE IF NOT EXISTS reference_production_closures (id text PRIMARY KEY, company_id text NOT NULL,
                employee_id text NOT NULL, employee_name text NULL, telegram_user_id text NULL, reference_id text NULL, reference_name text NOT NULL,
                size text NOT NULL, quantity_finished integer NOT NULL DEFAULT 0, notes text NULL, closed_at timestamptz NOT NULL DEFAULT now(),
                source_channel text NOT NULL DEFAULT 'telegram', created_at timestamptz NOT NULL DEFAULT now())"""))
            await db.commit()
        await engine.dispose()

    asyncio.run(setup())
    yield url


async def _engine(url):
    engine = create_async_engine(url)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _migrate(url):
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        for stmt in _migration_024e():
            await conn.execute(text(stmt))
    await engine.dispose()


async def _company(db, name: str) -> str:
    cid = str(uuid.uuid4())
    await db.execute(text("INSERT INTO companies (id, name, slug, settings_json) VALUES (CAST(:i AS uuid), :n, :s, '{}'::jsonb)"),
                     {"i": cid, "n": name, "s": name.lower()})
    await db.execute(text("INSERT INTO modules (code, name, category) VALUES ('references', 'Referencias', 'x') ON CONFLICT (code) DO NOTHING"))
    await db.execute(text("""INSERT INTO company_modules (company_id, module_id, enabled, settings)
        SELECT CAST(:i AS uuid), id, true, '{}'::jsonb FROM modules WHERE code = 'references'"""), {"i": cid})
    await db.commit()
    return cid


async def _snapshot(db, cid: str) -> str:
    """Todo lo que lee el bot y la pantalla de siempre, serializado."""
    out = {
        "bot_options": await refs.bot_reference_options(company_id=cid, db=db),
        "sizes_pant": await refs.bot_reference_sizes(company_id=cid, name="PANT SET", db=db),
        "sizes_mystic": await refs.bot_reference_sizes(company_id=cid, name="Mystic pant", db=db),
        "list": await refs.list_references(company_id=cid, q=None, date_from=None, date_to=None, bot_active=None, channel=None, db=db),
        "summary": await refs.references_summary(company_id=cid, db=db),
        "bot_refs": await vbot._references(db, cid),
    }
    first = out["bot_refs"][0]["id"]
    out["bot_sizes"] = await vbot._sizes_by_reference_id(db, company_id=cid, reference_id=first)
    return json.dumps(out, sort_keys=True, default=str)


@pytest.mark.asyncio
async def test_everything_on_real_postgres(pg_url):
    engine, maker = await _engine(pg_url)
    async with maker() as db:
        velvet = await _company(db, "VelvetPrueba")
        other = await _company(db, "Otra")
        # Datos como los de Velvet hoy, creados con la logica de siempre
        made = {}
        for payload in [{"name": "PANT SET", "category": "", "size": "10", "color": "Marfil", "initial_quantity": 30},
                        {"name": "PANT SET", "category": "", "size": "12", "color": "Marfil", "initial_quantity": 20, "channel": "system"},
                        {"name": "Mystic pant", "category": "", "size": "4, 6, 8, 10, 12", "color": "", "initial_quantity": 114},
                        {"name": "Mystic jacket", "category": "Superior", "size": "SM, MI", "color": "Marfil", "initial_quantity": 126}]:
            made[(payload["name"], payload["size"])] = (await refs.create_reference(velvet, payload, db))["id"]
        await db.execute(text("""INSERT INTO reference_production_closures (id, company_id, employee_id, reference_id, reference_name, size, quantity_finished)
            VALUES ('c1', :c, 'e1', :r, 'Mystic pant', '4, 6, 8, 10, 12', 114)"""), {"c": velvet, "r": made[("Mystic pant", "4, 6, 8, 10, 12")]})
        intruder = (await refs.create_reference(other, {"name": "Ajena", "size": "M", "initial_quantity": 5}, db))["id"]
        await db.commit()
        before = await _snapshot(db, velvet)

    await _migrate(pg_url)  # 024e: columnas opcionales y tabla nueva
    async with maker() as db:
        nulls = (await db.execute(text("SELECT COUNT(*) FROM product_references WHERE gender IS NULL AND body_part IS NULL AND garment_type IS NULL"))).scalar()
        assert nulls == 5, "las referencias actuales quedan sin clasificar"
        assert await _snapshot(db, velvet) == before, "la migracion no cambia nada de lo que lee el bot"

        # Clasificar: solo las tres columnas
        pant10 = made[("PANT SET", "10")]
        row_before = dict((await db.execute(text("SELECT * FROM product_references WHERE id = :r"), {"r": pant10})).mappings().first())
        await rv2.classify(db, velvet, pant10, {"gender": "mujer", "body_part": "inferior", "garment_type": "pantalon"})
        row_after = dict((await db.execute(text("SELECT * FROM product_references WHERE id = :r"), {"r": pant10})).mappings().first())
        changed = {k for k in row_after if row_after[k] != row_before[k]}
        assert changed == {"gender", "body_part", "garment_type"}
        with pytest.raises(rv2.Invalid):
            await rv2.classify(db, velvet, intruder, {"gender": "mujer", "body_part": "superior", "garment_type": "top"})
        with pytest.raises(rv2.Invalid):
            await rv2.classify(db, velvet, pant10, {"gender": "mujer", "body_part": "superior", "garment_type": "pantalon"})

        # Movimientos: ingreso 30 + 20, novedades 1 + 2, despliegue 1 (como en el diseño)
        pant12 = made[("PANT SET", "12")]
        today = "2026-10-06"
        saved = await rv2.add_movements(db, velvet, [
            {"reference_id": pant10, "kind": "ingreso", "size": "10", "quantity": 30, "event_date": today},
            {"reference_id": pant12, "kind": "ingreso", "size": "12", "quantity": 20, "event_date": today},
            {"reference_id": pant12, "kind": "novedad", "section": "corte", "size": "12", "quantity": 1, "note": "Pieza mal cortada en talla 12", "event_date": today},
            {"reference_id": pant10, "kind": "novedad", "section": "bordado", "quantity": 2, "note": "Falta el logo", "event_date": today},
            {"reference_id": pant10, "kind": "despliegue", "size": "10", "quantity": 1, "event_date": today},
        ], "Ana")
        b = await rv2.balance(db, velvet, pant12)
        assert (b["received"], b["novelty"], b["deployed"], b["available"]) == (50, 3, 1, 46), "el balance es de toda la referencia"
        assert b["by_section"]["corte"] == 1 and b["by_section"]["bordado"] == 2
        assert len(b["log"]) == 5
        assert await _snapshot(db, velvet) == before, "novedades y envios no cambian meta, producido ni lo que ve el bot"

        # Anular: sale del balance y queda en el historial
        dep = next(m for m in saved if m["kind"] == "despliegue")
        assert await rv2.void_movement(db, other, dep["id"], "no es mio", "x") is False, "otra empresa no anula"
        assert await rv2.void_movement(db, velvet, dep["id"], "Se registró dos veces", "Ana") is True
        assert await rv2.void_movement(db, velvet, dep["id"], "otra vez", "Ana") is False, "ya anulado"
        b = await rv2.balance(db, velvet, pant10)
        assert (b["deployed"], b["available"]) == (0, 47) and len(b["log"]) == 5
        voided = next(m for m in b["log"] if m["id"] == dep["id"])
        assert voided["voided_at"] is not None and voided["void_reason"] == "Se registró dos veces"
        assert (await db.execute(text("SELECT COUNT(*) FROM reference_cut_movements"))).scalar() == 5, "nada se borra"

        # Aislamiento
        with pytest.raises(rv2.Invalid):
            await rv2.add_movements(db, velvet, [{"reference_id": intruder, "kind": "ingreso", "size": "M", "quantity": 1, "event_date": today}], "Ana")
        await db.rollback()
        assert await rv2.balance(db, velvet, intruder) is None
        assert await rv2.balance(db, other, pant10) is None
        assert (await rv2.board_extras(db, other)).keys() == {intruder}

        # Estado: sugerencias (no aplicadas), tallas combinadas y nota de despliegue
        ex = await rv2.board_extras(db, velvet)
        mystic = ex[made[("Mystic pant", "4, 6, 8, 10, 12")]]
        assert mystic["combined_sizes"] and not mystic["classified"] and mystic["suggestion"]["garment_type"] == "pantalon"
        jacket = ex[made[("Mystic jacket", "SM, MI")]]
        assert jacket["suggestion"]["garment_type"] == "chaqueta" and jacket["gender"] is None, "sugerir no clasifica"
        assert ex[pant10]["classified"] and ex[pant10]["deployed"] is None, "el envio anulado ya no sale como nota"
    await engine.dispose()


@pytest.mark.asyncio
async def test_catalog_create_makes_the_same_rows_as_today(pg_url):
    engine, maker = await _engine(pg_url)
    await _migrate(pg_url)
    async with maker() as db:
        a = await _company(db, "Hoy")
        b = await _company(db, "Catalogo")
        for size, qty in (("4", 30), ("6", 20)):
            await refs.create_reference(a, {"name": "PANT SET", "category": "Pantalón", "size": size, "color": "Marfil", "initial_quantity": qty, "channel": "bot"}, db)
        result = await refs.v2_catalog_create(b, {"name": "PANT SET", "color": "Marfil", "gender": "mujer", "body_part": "inferior",
                                                  "garment_type": "pantalon", "bot_visible": True,
                                                  "sizes": [{"size": "6", "quantity": 20}, {"size": "4", "quantity": 30}]}, actor="t", db=db)
        assert result["count"] == 2 and result["summary"]["total"] == 50
        cols = "name, category, size, color, sku, unit_price, initial_quantity, (activation_date IS NOT NULL) AS active, bot_active, system_active, channel, archived"
        q = f"SELECT {cols} FROM product_references WHERE company_id = :c ORDER BY size"
        today_rows = [dict(r) for r in (await db.execute(text(q), {"c": a})).mappings().all()]
        catalog_rows = [dict(r) for r in (await db.execute(text(q), {"c": b})).mappings().all()]
        assert today_rows == catalog_rows, "mismas filas que la creacion actual"
        classified = (await db.execute(text("SELECT DISTINCT gender, body_part, garment_type FROM product_references WHERE company_id = :c"), {"c": b})).all()
        assert classified == [("mujer", "inferior", "pantalon")]
        assert [o["name"] for o in (await refs.bot_reference_options(company_id=b, db=db))["items"]] == ["PANT SET"], "el bot la ve igual"
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as dup:
            await refs.v2_catalog_create(b, {"name": "PANT SET", "color": "Marfil", "gender": "mujer", "body_part": "inferior", "garment_type": "pantalon",
                                             "sizes": [{"size": "8", "quantity": 5}, {"size": "4", "quantity": 1}]}, actor="t", db=db)
        assert dup.value.status_code == 409
        assert (await db.execute(text("SELECT COUNT(*) FROM product_references WHERE company_id = :c"), {"c": b})).scalar() == 2, "todas o ninguna"
        counts = await rv2.catalog_counts(db, b)
        assert counts["mujer"]["parts"]["inferior"] == 1 and counts["mujer"]["garments"]["pantalon"] == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_cut_in_size_without_reference_and_create_it_later(pg_url):
    """Caso real: PANT SET se creo en 4 y 6; llega corte en 8 y 12."""
    from fastapi import HTTPException

    engine, maker = await _engine(pg_url)
    await _migrate(pg_url)
    async with maker() as db:
        v = await _company(db, "VelvetTallas")
        other = await _company(db, "OtraTallas")
        made = await refs.v2_catalog_create(v, {"name": "PANT SET", "color": "Marfil", "gender": "mujer", "body_part": "inferior", "garment_type": "pantalon",
                                                "bot_visible": True, "sizes": [{"size": "6", "quantity": 20}, {"size": "4", "quantity": 30}]}, actor="t", db=db)
        anchor = made["items"][0]["id"]
        bot_before = json.dumps([await refs.bot_reference_options(company_id=v, db=db), await refs.bot_reference_sizes(company_id=v, name="PANT SET", db=db),
                                 await vbot._references(db, v)], sort_keys=True, default=str)
        count = lambda: db.execute(text("SELECT COUNT(*) FROM product_references WHERE company_id = :c"), {"c": v})
        await rv2.add_movements(db, v, [
            {"reference_id": anchor, "kind": "ingreso", "size": "8", "quantity": 6, "event_date": "2026-10-06"},
            {"reference_id": anchor, "kind": "ingreso", "size": "12", "quantity": 3, "event_date": "2026-10-06"},
            {"reference_id": anchor, "kind": "ingreso", "size": "4", "quantity": 8, "event_date": "2026-09-16"},
            {"reference_id": anchor, "kind": "despliegue", "size": "8", "quantity": 1, "event_date": "2026-10-06"}], "Ana")
        assert (await count()).scalar() == 2, "recibir corte en una talla nueva NO crea la referencia sola"
        b = await rv2.balance(db, v, anchor)
        assert b["existing_sizes"] == ["4", "6"] and b["catalog_sizes"] == ["4", "6", "8", "10", "12", "14", "16"]
        orphans = sorted(m["size"] for m in b["log"] if m["size_without_reference"])
        assert orphans == ["12", "8", "8"], "talla sin referencia"
        assert b["received"] == 17 and [(str(d["date"]), d["quantity"]) for d in b["received_by_date"]] == [("2026-09-16", 8), ("2026-10-06", 9)]
        assert sum(d["quantity"] for d in b["received_by_date"]) == b["received"], "suma por fecha = total recibido"
        # Crear referencia en talla 8: misma referencia, meta 0, NO visible para el bot
        created = await refs.v2_add_size(v, anchor, {"size": "8"}, actor="t", db=db)
        assert created["bot_active"] is False
        row = (await db.execute(text("SELECT name, category, color, size, initial_quantity, bot_active, gender, body_part, garment_type FROM product_references WHERE id = :i"),
                                {"i": created["item"]["id"]})).mappings().first()
        assert dict(row) == {"name": "PANT SET", "category": "Pantalón", "color": "Marfil", "size": "8", "initial_quantity": 0, "bot_active": False,
                             "gender": "mujer", "body_part": "inferior", "garment_type": "pantalon"}
        bot_after = json.dumps([await refs.bot_reference_options(company_id=v, db=db), await refs.bot_reference_sizes(company_id=v, name="PANT SET", db=db),
                                await vbot._references(db, v)], sort_keys=True, default=str)
        assert bot_after == bot_before, "el bot ve lo mismo hasta que la enciendan"
        b = await rv2.balance(db, v, anchor)
        assert sorted(m["size"] for m in b["log"] if m["size_without_reference"]) == ["12"], "los cortes de la talla 8 quedan asociados a ella"
        ex = await rv2.board_extras(db, v)
        assert ex[created["item"]["id"]]["deployed"]["quantity"] == 1 and ex[anchor]["deployed"] is None, "la nota de Bombón va en la talla 8"
        moved = (await db.execute(text("SELECT COUNT(*) FROM reference_cut_movements WHERE company_id = :c AND reference_id = :r"), {"c": v, "r": anchor})).scalar()
        assert moved == 4, "ningún movimiento guardado cambia"
        with pytest.raises(HTTPException) as dup:
            await refs.v2_add_size(v, anchor, {"size": "8"}, actor="t", db=db)
        assert dup.value.status_code == 409
        with pytest.raises(HTTPException) as bad:
            await refs.v2_add_size(v, anchor, {"size": "XL"}, actor="t", db=db)
        assert bad.value.status_code == 422, "solo tallas de la prenda"
        with pytest.raises(HTTPException) as foreign:
            await refs.v2_add_size(other, anchor, {"size": "10"}, actor="t", db=db)
        assert foreign.value.status_code == 404, "otra empresa no ve ni crea en esta referencia"
    await engine.dispose()


def test_size_order_follows_the_catalog():
    sizes = ["12", "10", "8", "6", "4", "XL", "S", "M", "XS", "XXL", "L", "ML", "SM", "4, 6, 8, 10, 12"]
    assert sorted(sizes, key=rv2.size_key) == ["4", "4, 6, 8, 10, 12", "6", "8", "10", "12", "XS", "S", "SM", "M", "ML", "L", "XL", "XXL"]
