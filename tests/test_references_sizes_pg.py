"""Referencias v2 · meta = suma de los cortes y conversion de tallas S, M, L (Postgres real).

- Meta de una talla = suma de sus cortes vigentes; anular un corte la baja; una
  talla sin cortes conserva su meta; todo queda en la bitacora (revertible).
- Conversion: SM -> S, ML -> M, MI -> M; XL queda en "revisar"; dos filas en la
  misma talla se unen (suma meta y producido, mueve movimientos y cierres, la
  que sobra se archiva); si la suma por referencia no cuadra, no se aplica.
- Revertir el lote deja todo como estaba.
- Bot: listar referencias, elegir talla, reportar produccion y ver el pendiente
  siguen funcionando con S, M, L.
- Otra empresa sin references_v2: registrar cortes no le cambia la meta.
"""
from __future__ import annotations

import importlib
import uuid

import pytest

pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402

from app.api.v1.endpoints import references_v1 as refs  # noqa: E402
from app.api.v1.endpoints import velvet_bot_v1 as vbot  # noqa: E402
from app.services import references_v2 as rv2  # noqa: E402
from tests.test_references_op_order_pg import _migration_024g, _switch  # noqa: E402
from tests.test_references_v2_pg import _company, _engine, _migrate, pg_url  # noqa: E402,F401

ACTOR = "Prueba"


def _migration(name: str) -> list[str]:
    statements: list[str] = []

    class Op:
        def execute(self, sql):
            statements.append(str(sql))

    module = importlib.import_module(f"migrations.versions.{name}")
    module.op = Op()
    module.upgrade()
    return statements


async def _setup(url):
    await _migrate(url)
    engine, maker = await _engine(url)
    async with engine.begin() as conn:
        for stmt in _migration_024g() + _migration("024h_ref_change_log"):
            await conn.execute(text(stmt))
    return engine, maker


async def _ref(db, cid, name, size, meta=0, color="", body="superior", garment="chaqueta", channel="bot"):
    row = await refs.create_reference(cid, {"name": name, "category": "Superior", "size": size, "color": color, "initial_quantity": meta, "channel": channel}, db)
    if body:
        await rv2.classify(db, cid, row["id"], {"gender": "mujer", "body_part": body, "garment_type": garment})
    return row


async def _meta(db, cid, rid):
    return (await db.execute(text("SELECT initial_quantity FROM product_references WHERE company_id = :c AND id = :i"), {"c": cid, "i": rid})).scalar()


async def _cut(cid, rid, size, qty, actor=ACTOR, db=None):
    return await refs.v2_add_movements(cid, {"items": [{"reference_id": rid, "kind": "ingreso", "size": size, "quantity": qty, "event_date": "2026-10-10"}]},
                                       actor=actor, db=db)


@pytest.mark.asyncio
async def test_meta_is_the_sum_of_live_cuts(pg_url):
    engine, maker = await _setup(pg_url)
    async with maker() as db:
        cid = await _company(db, f"Vel{uuid.uuid4().hex[:6]}")
        other = await _company(db, f"Otra{uuid.uuid4().hex[:6]}")
        await _switch(db, cid, True)
        s = await _ref(db, cid, "Koi Jacket", "S", meta=8)
        m = await _ref(db, cid, "Koi Jacket", "M", meta=10)
        quiet = await _ref(db, cid, "Charms", "S", meta=50)
        await _cut(cid, s["id"], "S", 12, db=db)
        await _cut(cid, s["id"], "S", 5, db=db)
        await _cut(cid, s["id"], "M", 7, db=db)  # registrado en la fila S, talla M: es de M
        assert await _meta(db, cid, s["id"]) == 17 and await _meta(db, cid, m["id"]) == 7
        assert await _meta(db, cid, quiet["id"]) == 50, "sin cortes conserva su meta"
        moves = await rv2.movements_for(db, cid, [s["id"]])
        five = next(x for x in moves if x["quantity"] == 5)
        await refs.v2_void_movement(cid, five["id"], {"reason": "doble"}, actor=ACTOR, db=db)
        assert await _meta(db, cid, s["id"]) == 12, "anular un corte baja la meta"
        logged = (await db.execute(text("SELECT count(*) FROM reference_change_log WHERE company_id = :c AND reason = 'meta_cortes'"), {"c": cid})).scalar()
        assert logged >= 3, "cada cambio queda en la bitacora"
        # Producido y pendiente siguen saliendo igual: pendiente = meta - producido.
        await db.execute(text("""INSERT INTO reference_production_closures (id, company_id, employee_id, reference_id, reference_name, size, quantity_finished)
            VALUES (:i, :c, 'e1', :r, 'Koi Jacket', 'S', 4)"""), {"i": str(uuid.uuid4()), "c": cid, "r": s["id"]})
        await db.commit()
        row = next(x for x in (await refs.references_summary(company_id=cid, db=db))["by_reference_size"] if x["id"] == s["id"])
        assert (row["initial_quantity"], row["finished_quantity"], row["pending_quantity"]) == (12, 4, 8)

        # Otra empresa sin references_v2: registrar un corte no toca su meta.
        o = await _ref(db, other, "Koi Jacket", "S", meta=8)
        await rv2.add_movements(db, other, [{"reference_id": o["id"], "kind": "ingreso", "size": "S", "quantity": 30, "event_date": "2026-10-10"}], ACTOR)
        await refs.v2_add_movements(other, {"items": [{"reference_id": o["id"], "kind": "ingreso", "size": "S", "quantity": 1, "event_date": "2026-10-10"}]}, actor=ACTOR, db=db)
        assert await _meta(db, other, o["id"]) == 8

        # "Igualar meta a lo recibido": antes/despues y luego aplicar.
        await db.execute(text("UPDATE product_references SET initial_quantity = 99 WHERE id = :i"), {"i": s["id"]})
        await db.commit()
        key = rv2.group_key("Koi Jacket")
        preview = await refs.v2_meta_sync(cid, {"key": key}, actor=ACTOR, db=db)
        assert preview["applied"] is False and [(c["size"], c["old_meta"], c["new_meta"]) for c in preview["changes"]] == [("S", 99, 12)]
        assert await _meta(db, cid, s["id"]) == 99, "la vista previa no escribe"
        done = await refs.v2_meta_sync(cid, {"key": key, "apply": True}, actor=ACTOR, db=db)
        assert done["applied"] and await _meta(db, cid, s["id"]) == 12
        await rv2.revert_batch(db, cid, done["batch_id"])
        assert await _meta(db, cid, s["id"]) == 99, "se puede revertir"
    await engine.dispose()


def test_size_rule():
    assert [rv2.convert_size(x) for x in ["SM", "ML", "MI", "S", "M", "L", "LXL", "sm ", "XL", "XS", "XXL", "4", "Única", "#"]] == \
        ["S", "M", "M", "S", "M", "L", "L", "S", None, None, None, None, None, None]
    assert rv2.group_key("Lucky Coat") == rv2.group_key("  lucky  COAT ", "verde oliva"), "por nombre: el color no separa"


@pytest.mark.asyncio
async def test_conversion_merge_review_revert_and_bot(pg_url):
    engine, maker = await _setup(pg_url)
    async with maker() as db:
        cid = await _company(db, f"Vel{uuid.uuid4().hex[:6]}")
        other = await _company(db, f"Otra{uuid.uuid4().hex[:6]}")
        await _switch(db, cid, True)
        aurora = await _ref(db, cid, "Aurora Azul", "SM", meta=0, color="Azul")
        dreamy_sm = await _ref(db, cid, "Dreamy Jacket", "SM", meta=122, channel="system")
        dreamy_ml = await _ref(db, cid, "Dreamy Jacket", "ML", meta=60)
        mystic = await _ref(db, cid, "Mystic jacket", "SM,MI", meta=126, color="Marfil")
        koi_sm = await _ref(db, cid, "Koi Jacket", "SM", meta=8)
        koi_s = await _ref(db, cid, "Koi Jacket", "S", meta=5)
        big = await _ref(db, cid, "Petal Top", "XL", meta=3)
        maricas = await _ref(db, cid, "Maricas", "ML", meta=54, body=None)
        pant = await _ref(db, cid, "PANT SET", "10", meta=30, body="inferior", garment="pantalon")
        mine = await _ref(db, other, "Koi Jacket", "SM", meta=8)
        await rv2.add_movements(db, cid, [{"reference_id": aurora["id"], "kind": "ingreso", "size": "S", "quantity": 26, "event_date": "2026-10-06"},
                                          {"reference_id": aurora["id"], "kind": "ingreso", "size": "M", "quantity": 10, "event_date": "2026-10-06"},
                                          {"reference_id": koi_sm["id"], "kind": "ingreso", "size": "SM", "quantity": 8, "event_date": "2026-10-06"},
                                          {"reference_id": dreamy_ml["id"], "kind": "despliegue", "size": "ML", "quantity": 1, "event_date": "2026-10-06"}], ACTOR)
        for rid, name, size, qty in [(dreamy_sm["id"], "Dreamy Jacket", "SM", 28), (koi_sm["id"], "Koi Jacket", "SM", 8), (koi_s["id"], "Koi Jacket", "S", 2),
                                     (mystic["id"], "Mystic jacket", "SM,Ml", 126)]:
            await db.execute(text("""INSERT INTO reference_production_closures (id, company_id, employee_id, reference_id, reference_name, size, quantity_finished)
                VALUES (:i, :c, 'e1', :r, :n, :s, :q)"""), {"i": str(uuid.uuid4()), "c": cid, "r": rid, "n": name, "s": size, "q": qty})
        await db.commit()
        before = await rv2._group_totals(db, cid)

        dry = await rv2.convert_sizes(db, cid, ACTOR, apply=False)
        assert dry["ok"] and not dry["applied"]
        assert (await db.execute(text("SELECT size FROM product_references WHERE id = :i"), {"i": aurora["id"]})).scalar() == "SM", "dry-run no escribe"
        renames = {(c["name"], c["old_size"]): c["new_size"] for c in dry["plan"]["renames"]}
        assert renames == {("Aurora Azul", "SM"): "S", ("Dreamy Jacket", "SM"): "S", ("Dreamy Jacket", "ML"): "M", ("Maricas", "ML"): "M"}, "Koi SM se une a Koi S (no se renombra)"
        review = {(r["name"], r["size"]) for r in dry["plan"]["review"]}
        assert review == {("Petal Top", "XL"), ("Mystic jacket", "SM,MI")}, "XL y la fila SM,MI (S y M sin saber el reparto) quedan en revisar"
        assert [(m["name"], m["from_id"], m["into_id"]) for m in dry["plan"]["merges"]] == [("Koi Jacket", koi_sm["id"], koi_s["id"])]

        done = await rv2.convert_sizes(db, cid, ACTOR, apply=True)
        assert done["applied"] and done["ok"] and done["mismatch"] == []
        sizes = dict((await db.execute(text("SELECT id, size FROM product_references WHERE company_id = :c"), {"c": cid})).all())
        assert sizes[aurora["id"]] == "S" and sizes[dreamy_sm["id"]] == "S" and sizes[dreamy_ml["id"]] == "M" and sizes[maricas["id"]] == "M"
        assert sizes[mystic["id"]] == "SM,MI" and sizes[big["id"]] == "XL" and sizes[pant["id"]] == "10", "revisar e inferiores no cambian"
        # Union: suma meta y producido, mueve movimientos y cierres; la que sobra queda archivada y sin bot.
        loser = (await db.execute(text("SELECT archived, bot_active FROM product_references WHERE id = :i"), {"i": koi_sm["id"]})).one()
        assert tuple(loser) == (True, False)
        assert await _meta(db, cid, koi_s["id"]) == 13
        koi_moves = await rv2.movements_for(db, cid, [koi_s["id"]])
        assert [(m["size"], m["quantity"]) for m in koi_moves] == [("S", 8)], "el corte SM pasa a la fila S con talla S"
        finished, _ = await rv2.finished_by_reference(db, cid)
        assert finished[koi_s["id"]] == 10
        after = await rv2._group_totals(db, cid)
        assert after == before, "meta y producido por referencia: antes = despues"
        # Movimientos de las filas convertidas con talla vieja pasan a la nueva.
        dreamy_moves = await rv2.movements_for(db, cid, [dreamy_ml["id"]])
        assert [m["size"] for m in dreamy_moves] == ["M"]
        # La otra empresa no cambia.
        assert (await db.execute(text("SELECT size FROM product_references WHERE id = :i"), {"i": mine["id"]})).scalar() == "SM"

        # Bot: lista, tallas, cierre de produccion y pendiente con S, M, L.
        options = await refs.bot_reference_options(company_id=cid, db=db)
        assert any("Aurora Azul" in str(o) for o in (options.get("items") or options.get("options") or [options]))
        sizes_bot = await refs.bot_reference_sizes(company_id=cid, name="Dreamy Jacket", db=db)
        bot_sizes = {str(x.get("size") if isinstance(x, dict) else x) for x in (sizes_bot.get("sizes") or sizes_bot.get("items") or [])}
        assert bot_sizes == {"M"}, "el bot ve la talla nueva M (la S de Dreamy no es visible para el bot); ya no SM ni ML"
        closed = await refs.flow_close_production(cid, {"employee_id": "e9", "reference_name": "Dreamy Jacket", "size": "M", "quantity_finished": 5}, db=db)
        assert closed["size"] == "M" and closed["reference_id"] == dreamy_ml["id"]
        row = next(x for x in (await refs.references_summary(company_id=cid, db=db))["by_reference_size"] if x["id"] == dreamy_ml["id"])
        assert (row["size"], row["initial_quantity"], row["finished_quantity"], row["pending_quantity"]) == ("M", 60, 5, 55)
        vrefs = await vbot._references(db, cid)
        assert all(r.get("size") != "SM" for r in vrefs if str(r.get("name", "")).startswith("Dreamy"))

        # Revertir: todo vuelve.
        reverted = await rv2.revert_batch(db, cid, done["batch_id"])
        assert reverted > 0
        sizes = dict((await db.execute(text("SELECT id, size FROM product_references WHERE company_id = :c"), {"c": cid})).all())
        assert sizes[aurora["id"]] == "SM" and sizes[koi_sm["id"]] == "SM" and sizes[dreamy_ml["id"]] == "ML"
        loser = (await db.execute(text("SELECT archived, bot_active FROM product_references WHERE id = :i"), {"i": koi_sm["id"]})).one()
        assert tuple(loser) == (False, True)
        assert [m["size"] for m in await rv2.movements_for(db, cid, [koi_sm["id"]])] == ["SM"]
    await engine.dispose()
