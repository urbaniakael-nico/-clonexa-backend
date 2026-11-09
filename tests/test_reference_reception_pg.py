"""Recepcion inicial al crear una referencia (reference_lifecycle, solo Velvet) contra Postgres real.

- Crear con S 46 / M 25: Balance Recibido 71 y Disponible 71 al instante; tarjeta, editor y Produccion
  con lo mismo; bitacora con "Referencia creada" y la recepcion inicial.
- Un corte posterior suma con su movimiento; misma talla, fecha y cantidad pide confirmar.
- Cambiar la meta no cambia lo recibido; corregir la recepcion inicial pide motivo y doble confirmacion.
- Carga de datos existentes: solo las referencias sin cortes; dos veces no duplica; se puede anular.
- Otra empresa sin el interruptor: igual que siempre.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("pgserver")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.api.v1.endpoints import reference_lifecycle as life_routes  # noqa: E402
from app.api.v1.endpoints import references_v1 as refs  # noqa: E402
from app.services import production_v2, reference_reception as rec  # noqa: E402
from app.services import references_v2 as rv2  # noqa: E402
from tests.test_reference_lifecycle_pg import _all_setup, _no_team, _on, _ref, _cut  # noqa: E402
from tests.test_references_sizes_pg import _migration  # noqa: E402
from tests.test_references_v2_pg import _company, pg_url  # noqa: E402,F401

WHO = "Dueña"
BOG = ZoneInfo("America/Bogota")


async def _setup(url):
    engine, maker = await _all_setup(url)
    async with engine.begin() as conn:
        for stmt in _migration("025g_ref_initial_cut") + _migration("025g_ref_initial_cut"):  # idempotente
            await conn.execute(text(stmt))
    return engine, maker


async def _create(db, cid, name="rojita medium", sizes=(("S", 46), ("M", 25))):
    out = await refs.v2_catalog_create(cid, {"name": name, "color": "rojo", "gender": "mujer", "body_part": "superior", "garment_type": "chaqueta",
                                             "sizes": [{"size": z, "quantity": q} for z, q in sizes]}, actor=WHO, db=db)
    return {r["size"]: r for r in out["items"]}


def _group(groups, name):
    return next(g for g in groups if g["key"] == rv2.group_key(name))


@pytest.mark.asyncio
async def test_crear_referencia_es_meta_y_recepcion_inicial_al_instante(pg_url, monkeypatch):
    engine, maker = await _setup(pg_url)
    _no_team(monkeypatch)
    async with maker() as db:
        cid = await _company(db, f"rec{uuid.uuid4().hex[:6]}")
        await _on(db, cid)
        rows = await _create(db, cid)
        bal = await rv2.balance(db, cid, rows["S"]["id"])
        assert (bal["received"], bal["available"]) == (71, 71)
        init = [m for m in bal["log"] if m["origin"] == rec.INITIAL]
        assert sorted((m["size"], m["quantity"], m["created_by"]) for m in init) == [("M", 25, WHO), ("S", 46, WHO)]
        assert [e["kind"] for e in bal["events"]] == ["creada"] and bal["events"][0]["actor"] == WHO
        g = _group(await rv2.reference_groups(db, cid), "rojita medium")
        assert {x["size"]: (x["meta"], x["received"]) for x in g["lines"]} == {"S": (46, 46), "M": (25, 25)}, "tarjeta: meta y recibido"
        assert g["cuts_by_date"][0]["total"] == 71, "cortes por fecha del editor"
        today = date.today()
        ins = await production_v2.insights(db, cid, today, today, today)
        lot = next(x for x in ins["lots_in_process"] if x["name"] == "rojita medium")
        assert lot["received"] == 71

        # Corte posterior: suma, con su propio movimiento.
        later = [{"reference_id": rows["S"]["id"], "kind": "ingreso", "size": "S", "quantity": 10, "event_date": today.isoformat()}]
        await refs.v2_add_movements(cid, {"items": later}, actor=WHO, db=db)
        assert (await rv2.balance(db, cid, rows["S"]["id"]))["received"] == 81

        # Misma talla, fecha y cantidad que la recepcion inicial: pregunta antes de contar dos veces.
        same = [{"reference_id": rows["S"]["id"], "kind": "ingreso", "size": "S", "quantity": 46, "event_date": today.isoformat()}]
        with pytest.raises(HTTPException) as dup:
            await refs.v2_add_movements(cid, {"items": same}, actor=WHO, db=db)
        assert dup.value.status_code == 409 and dup.value.detail["code"] == "posible_duplicado"
        assert "S ya tiene recepción inicial de 46" in dup.value.detail["message"] and "corte nuevo (sumar) o el mismo (no sumar)" in dup.value.detail["message"]
        assert (await rv2.balance(db, cid, rows["S"]["id"]))["received"] == 81, "sin confirmar no suma"
        await refs.v2_add_movements(cid, {"items": same, "confirm_duplicate": True}, actor=WHO, db=db)
        assert (await rv2.balance(db, cid, rows["S"]["id"]))["received"] == 127, "confirmado como corte nuevo, suma"
    await engine.dispose()


@pytest.mark.asyncio
async def test_cambiar_meta_no_cambia_recibido_y_corregir_recepcion_pide_motivo_y_doble_confirmacion(pg_url):
    engine, maker = await _setup(pg_url)
    async with maker() as db:
        cid = await _company(db, f"fix{uuid.uuid4().hex[:6]}")
        await _on(db, cid)
        rows = await _create(db, cid, "Blusa roja", (("S", 46), ("M", 25)))
        await refs.update_reference(cid, rows["S"]["id"], {"initial_quantity": 60}, db)
        bal = await rv2.balance(db, cid, rows["S"]["id"])
        assert bal["received"] == 71
        assert {x["size"]: x["received"] for x in _group(await rv2.reference_groups(db, cid), "Blusa roja")["lines"]} == {"S": 46, "M": 25}, "la meta no toca lo recibido"

        mid = next(m["id"] for m in bal["log"] if m["origin"] == rec.INITIAL and m["size"] == "S")
        ok = {"movement_id": mid, "new_value": 40, "reason": "se contó mal", "confirm": True, "confirm_final": True}
        for missing in ({"confirm_final": False}, {"reason": ""}, {"new_value": "x"}):
            with pytest.raises(rec.ReceptionError):
                await rec.correct_initial(db, cid, {**ok, **missing}, WHO)
        out = await life_routes.initial_reception_correction(uuid.UUID(cid), ok, who=WHO, db=db)
        assert (out["before"], out["after"]) == (46, 40)
        bal = await rv2.balance(db, cid, rows["S"]["id"])
        assert bal["received"] == 65
        old = next(m for m in bal["log"] if m["id"] == mid)
        assert old["voided_at"] is not None and "Corregido 46 -> 40: se contó mal" in old["void_reason"], "el original queda anulado, no se borra"
        fixed = [e for e in bal["events"] if e["kind"] == "recepcion_corregida"]
        assert fixed and fixed[0]["detail"]["before"] == 46 and fixed[0]["detail"]["after"] == 40 and fixed[0]["actor"] == WHO
        with pytest.raises(rec.ReceptionError):
            await rec.correct_initial(db, cid, ok, WHO)  # ya no esta vigente
    await engine.dispose()


@pytest.mark.asyncio
async def test_carga_de_datos_existentes_solo_sin_cortes_y_dos_veces_no_duplica(pg_url):
    engine, maker = await _setup(pg_url)
    async with maker() as db:
        cid = await _company(db, f"bf{uuid.uuid4().hex[:6]}")
        await _on(db, cid)
        sin = (await _ref(db, cid, "Charms", "S", 50), await _ref(db, cid, "Charms", "M", 20))
        con = (await _ref(db, cid, "Dreamy Jacket", "S", 132), await _ref(db, cid, "Dreamy Jacket", "M", 80))
        await _cut(db, cid, con[0]["id"], "S", 132)
        zero = await _ref(db, cid, "Aurora Cafe", "S", 0)
        combo = await _ref(db, cid, "Mystic pant", "4, 6, 8", 30)
        when = datetime(2026, 7, 10, 19, 57, tzinfo=timezone.utc)
        await db.execute(text("UPDATE product_references SET created_at = :w WHERE company_id = :c"), {"w": when, "c": cid})
        await db.commit()

        dry = await rec.backfill(db, cid, BOG)
        assert dry["batch_id"] is None and not (await db.execute(text("SELECT count(*) FROM reference_events WHERE company_id = :c"), {"c": cid})).scalar()
        assert [(x["name"], x["size"], x["quantity"]) for x in dry["receptions"]] == [("Charms", "S", 50), ("Charms", "M", 20)]
        assert dry["with_cuts"] == ["Dreamy Jacket"] and [x["size"] for x in dry["skipped_combined"]] == ["4, 6, 8"]

        out = await rec.backfill(db, cid, BOG, apply=True)
        assert out["batch_id"]
        bal = await rv2.balance(db, cid, sin[0]["id"])
        assert bal["received"] == 70 and all(m["origin"] == rec.BACKFILL and m["created_by"] == rec.BACKFILL_ACTOR for m in bal["log"])
        assert {str(m["event_date"])[:10] for m in bal["log"]} == {"2026-07-10"}, "fecha de creacion"
        assert bal["events"][0]["kind"] == "creada" and bal["events"][0]["at"] == when
        dreamy = await rv2.balance(db, cid, con[0]["id"])
        assert dreamy["received"] == 132, "lo recibido de una referencia con cortes no se toca"
        assert [e["kind"] for e in dreamy["events"]] == ["creada"] and dreamy["events"][0]["at"] == when
        assert (await rv2.balance(db, cid, zero["id"]))["received"] == 0
        assert (await rv2.balance(db, cid, combo["id"]))["received"] == 0

        again = await rec.backfill(db, cid, BOG, apply=True)
        assert again["receptions"] == [] and again["created_events"] == [] and again["batch_id"] is None, "dos veces no duplica"
        assert (await rv2.balance(db, cid, sin[0]["id"]))["received"] == 70

        undo = await rec.undo_backfill(db, cid, out["batch_id"])
        assert undo["movements"] == 2 and (await rv2.balance(db, cid, sin[0]["id"]))["received"] == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_otra_empresa_sin_interruptor_no_cambia(pg_url):
    engine, maker = await _setup(pg_url)
    async with maker() as db:
        cid = await _company(db, f"off{uuid.uuid4().hex[:6]}")
        await _on(db, cid, on=False)
        rows = await _create(db, cid, "Otra", (("S", 46),))
        bal = await rv2.balance(db, cid, rows["S"]["id"])
        assert bal["received"] == 0 and bal["log"] == [] and bal["events"] == [], "sin el interruptor: solo meta, como siempre"
        today = date.today().isoformat()
        same = [{"reference_id": rows["S"]["id"], "kind": "ingreso", "size": "S", "quantity": 46, "event_date": today}]
        await refs.v2_add_movements(cid, {"items": same}, actor=WHO, db=db)
        assert (await rv2.balance(db, cid, rows["S"]["id"]))["received"] == 46
    await engine.dispose()


def test_revision_id_cabe_en_alembic():
    import importlib

    module = importlib.import_module("migrations.versions.025g_ref_initial_cut")
    assert len(module.revision) <= 32 and module.down_revision == "025f_ref_cycles"
