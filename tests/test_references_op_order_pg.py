"""Referencias v2 · tarjeta unica y orden operacional, contra Postgres REAL.

- Referencia = nombre + color (sin importar mayusculas, tildes ni espacios),
  la MISMA agrupacion en Cortes (balance), Orden operacional y Estado.
- Aurora Azul: fila solo en SM y cortes en S (26) y M (10) -> tarjeta S, SM,
  M con recibido 36; % = producido / 36.
- Crear las tallas "solo corte" las deja con meta 0 y NO visibles para el bot.
- Orden operacional: valor por prenda, items, reorden y borrado; con
  references_v2 apagado no responde; otra empresa no ve ni escribe nada.
- El bot no cambia: bot-options, sizes, listado y resumen identicos.
"""
from __future__ import annotations

import asyncio
import importlib
import uuid

import pytest

pytest.importorskip("pgserver")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.api.v1.endpoints import references_v1 as refs  # noqa: E402
from app.services import references_v2 as rv2  # noqa: E402
from tests.test_references_v2_pg import _company, _engine, _migrate, _snapshot, pg_url  # noqa: E402,F401

ACTOR = "Prueba"


def _migration_024g() -> list[str]:
    statements: list[str] = []

    class Op:
        def execute(self, sql):
            statements.append(str(sql))

    module = importlib.import_module("migrations.versions.024g_ref_op_order")
    module.op = Op()
    module.upgrade()
    return statements


async def _setup(url):
    await _migrate(url)
    engine, maker = await _engine(url)
    async with engine.begin() as conn:
        for stmt in _migration_024g():
            await conn.execute(text(stmt))
    return engine, maker


async def _switch(db, cid: str, on: bool) -> None:
    await db.execute(text("""UPDATE company_modules SET settings = CAST(:s AS jsonb)
        WHERE company_id = CAST(:c AS uuid)"""), {"c": cid, "s": '{"references_v2": true}' if on else "{}"})
    await db.commit()


async def _ref(db, cid, **payload) -> dict:
    return await refs.create_reference(cid, {"category": "Chaqueta", "initial_quantity": 0, **payload}, db)


@pytest.mark.asyncio
async def test_aurora_azul_single_card_cuts_and_state_agree(pg_url):
    engine, maker = await _setup(pg_url)
    async with maker() as db:
        velvet = await _company(db, f"Velvet{uuid.uuid4().hex[:6]}")
        await _switch(db, velvet, True)
        sm = await _ref(db, velvet, name="Aurora Azul 💙", size="SM", color="Azul", channel="bot")
        await rv2.add_movements(db, velvet, [
            {"reference_id": sm["id"], "kind": "ingreso", "size": "S", "quantity": 26, "event_date": "2026-10-06"},
            {"reference_id": sm["id"], "kind": "ingreso", "size": "M", "quantity": 10, "event_date": "2026-10-06"},
        ], ACTOR)
        await db.execute(text("""INSERT INTO reference_production_closures (id, company_id, employee_id, reference_id, reference_name, size, quantity_finished)
            VALUES (:i, :c, 'e1', :r, 'Aurora Azul 💙', 'SM', 9)"""), {"i": str(uuid.uuid4()), "c": velvet, "r": sm["id"]})
        await db.commit()

        groups = (await refs.v2_groups(velvet, actor=ACTOR, db=db))["groups"]
        card = next(g for g in groups if g["name"].startswith("Aurora Azul"))
        assert [ln["size"] for ln in card["lines"]] == ["S", "SM", "M"], "orden del catalogo"
        assert [ln["solo_corte"] for ln in card["lines"]] == [True, False, True]
        assert card["received"] == 36 and card["produced"] == 9 and card["percent"] == 25.0
        assert [ln["received"] for ln in card["lines"]] == [26, 0, 10]
        assert all(ln["anchor_id"] == sm["id"] for ln in card["lines"] if ln["solo_corte"])
        # Cortes (balance) y Orden operacional dan los mismos numeros.
        balance = await rv2.balance(db, velvet, sm["id"])
        assert balance["received"] == 36 and {ln["size"] for ln in card["lines"]} >= set(balance["per_size"])
        order = await refs.v2_op_order(velvet, key=card["key"], size="", actor=ACTOR, db=db)
        assert [(s["size"], s["received"]) for s in order["calc"]["per_size"]] == [("S", 26), ("SM", 0), ("M", 10)]
        assert order["calc"]["received"] == 36 and order["calc"]["percent"] == 25.0

        # Crear las tallas "solo corte": meta 0 y NO visibles para el bot.
        for size in card["solo_corte"]:
            made = await refs.v2_add_size(velvet, sm["id"], {"size": size}, actor=ACTOR, db=db)
            assert made["bot_active"] is False
        card = next(g for g in (await refs.v2_groups(velvet, actor=ACTOR, db=db))["groups"] if g["name"].startswith("Aurora Azul"))
        assert [ln["solo_corte"] for ln in card["lines"]] == [False, False, False]
        assert [(ln["size"], ln["meta"], ln["bot_active"], ln["received"]) for ln in card["lines"]] == [
            ("S", 0, False, 26), ("SM", 0, True, 0), ("M", 0, False, 10)], "los cortes quedan con su talla"
    await engine.dispose()


@pytest.mark.asyncio
async def test_name_and_color_ignore_case_spaces_and_accents(pg_url):
    engine, maker = await _setup(pg_url)
    async with maker() as db:
        cid = await _company(db, f"Agr{uuid.uuid4().hex[:6]}")
        await _switch(db, cid, True)
        a = await _ref(db, cid, name="Aurora Cafe", size="SM", color="Café", category="Superior")
        await _ref(db, cid, name="  aurora  CAFE ", size="ML", color="cafe", category="Chaqueta")
        await _ref(db, cid, name="Aurora Cafe", size="SM", color="Negro")
        groups = (await refs.v2_groups(cid, actor=ACTOR, db=db))["groups"]
        cafe = [g for g in groups if rv2.group_key(g["name"], g["color"]) == rv2.group_key("aurora cafe", "cafe")]
        assert len(groups) == 2 and len(cafe) == 1 and [ln["size"] for ln in cafe[0]["lines"]] == ["SM", "ML"]
        balance = await rv2.balance(db, cid, a["id"])
        assert sorted(r["size"] for r in balance["group"]) == ["ML", "SM"], "Cortes usa la misma agrupacion"
    await engine.dispose()


@pytest.mark.asyncio
async def test_operational_order_writes_switch_isolation_and_bot_contract(pg_url):
    engine, maker = await _setup(pg_url)
    async with maker() as db:
        velvet = await _company(db, f"Vel{uuid.uuid4().hex[:6]}")
        other = await _company(db, f"Otra{uuid.uuid4().hex[:6]}")
        for size in ("10", "12"):
            await refs.create_reference(velvet, {"name": "PANT SET", "category": "", "size": size, "color": "Marfil", "initial_quantity": 30}, db)
        await refs.create_reference(velvet, {"name": "Mystic pant", "category": "", "size": "4, 6, 8, 10, 12", "color": "", "initial_quantity": 114}, db)
        s = await _ref(db, velvet, name="Aurora Azul 💙", size="S", color="Azul", channel="bot")
        await _ref(db, velvet, name="Aurora Azul 💙", size="M", color="Azul", channel="bot")
        await rv2.add_movements(db, velvet, [
            {"reference_id": s["id"], "kind": "ingreso", "size": "S", "quantity": 26, "event_date": "2026-10-06"},
            {"reference_id": s["id"], "kind": "ingreso", "size": "M", "quantity": 10, "event_date": "2026-10-06"},
        ], ACTOR)
        before = await _snapshot(db, velvet)

        # Apagado: nada responde.
        with pytest.raises(HTTPException) as off:
            await refs.v2_groups(velvet, actor=ACTOR, db=db)
        assert off.value.status_code == 403
        await _switch(db, velvet, True)
        await _switch(db, other, True)
        key = next(g["key"] for g in (await refs.v2_groups(velvet, actor=ACTOR, db=db))["groups"] if g["name"].startswith("Aurora"))

        await refs.v2_op_value(velvet, {"key": key, "value_per_garment": "24000"}, actor=ACTOR, db=db)
        for name, h, m, size in [("Corte", 0, 25, ""), ("Costura", 1, 0, "Todas"), ("Botones", 0, 27, ""), ("Bolsillo", 0, 5, "m")]:
            out = await refs.v2_op_add_item(velvet, {"key": key, "name": name, "hours": h, "minutes": m, "size": size}, actor=ACTOR, db=db)
        calc = out["calc"]
        assert calc["minutes"] == 112 and calc["order_label"] == "68h 02m"
        assert [i["size"] for i in calc["items"]] == ["", "", "", "M"], "la talla se guarda como la de la referencia"
        corte = calc["items"][0]
        assert (corte["percent"], corte["value"]) == (22.3, 5357.0)
        assert sum(i["value"] or 0 for i in calc["items"]) == 24000
        m_view = await refs.v2_op_order(velvet, key=key, size="M", actor=ACTOR, db=db)
        assert m_view["calc"]["minutes"] == 117 and sum(i["value"] or 0 for i in m_view["calc"]["items"]) == 24000

        with pytest.raises(HTTPException) as bad:
            await refs.v2_op_add_item(velvet, {"key": key, "name": "X", "hours": 0, "minutes": 5, "size": "XL"}, actor=ACTOR, db=db)
        assert bad.value.status_code == 422, "solo tallas de la referencia"

        ids = [i["id"] for i in calc["items"]]
        out = await refs.v2_op_reorder(velvet, {"key": key, "ids": list(reversed(ids))}, actor=ACTOR, db=db)
        assert [i["name"] for i in out["calc"]["items"]] == ["Bolsillo", "Botones", "Costura", "Corte"]
        out = await refs.v2_op_update_item(velvet, ids[0], {"key": key, "name": "Corte y trazo", "hours": 0, "minutes": 30, "size": ""}, actor=ACTOR, db=db)
        assert out["calc"]["minutes"] == 117
        out = await refs.v2_op_delete_item(velvet, ids[3], key=key, view="", actor=ACTOR, db=db)
        assert [i["name"] for i in out["calc"]["items"]] == ["Botones", "Costura", "Corte y trazo"]

        # Otra empresa: no ve la referencia de Velvet ni puede escribir en ella.
        assert (await refs.v2_groups(other, actor=ACTOR, db=db))["groups"] == []
        for call in (lambda: refs.v2_op_order(other, key=key, size="", actor=ACTOR, db=db),
                     lambda: refs.v2_op_value(other, {"key": key, "value_per_garment": 1}, actor=ACTOR, db=db),
                     lambda: refs.v2_op_add_item(other, {"key": key, "name": "X", "minutes": 5}, actor=ACTOR, db=db),
                     lambda: refs.v2_op_delete_item(other, ids[1], key=key, view="", actor=ACTOR, db=db)):
            with pytest.raises(HTTPException) as denied:
                await call()
            assert denied.value.status_code == 404
        still = await refs.v2_op_order(velvet, key=key, size="", actor=ACTOR, db=db)
        assert len(still["calc"]["items"]) == 3 and still["settings"]["value_per_garment"] == 24000

        # El bot no cambia.
        assert await _snapshot(db, velvet) == before
    await engine.dispose()


def test_migration_is_additive_and_id_fits():
    module = importlib.import_module("migrations.versions.024g_ref_op_order")
    assert len(module.revision) <= 32 and module.down_revision == "024f_closure_note"
    sql = " ".join(_migration_024g()).upper()
    assert "DROP" not in sql and "ALTER TABLE" not in sql and "PRODUCT_REFERENCES" not in sql
    assert asyncio.iscoroutinefunction(rv2.reference_groups)
