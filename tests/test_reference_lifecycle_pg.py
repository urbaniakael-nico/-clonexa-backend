"""Corregir producido, renombrar y cerrar por talla contra Postgres real (interruptor reference_lifecycle).

- Dreamy Jacket S: 28 -> 0 con doble confirmacion, sin borrar nada, con historial.
- Producido > recibido: el portal pide confirmar; el bot avisa y no registra sin aprobacion.
- Renombrar: una sola referencia por nombre viejo y nuevo, historial intacto, nombre duplicado rechazado.
- Terminar ciclo: suma a producido, baja pendiente, historial, nada se oculta; cierres viejos -> ciclos
  (Dreamy Jacket S activa con 52); un corte en una referencia recien creada se ve en todas partes.
- Otra empresa sin el interruptor: nada cambia.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402

from app.api.v1.endpoints import company_bots_v1 as bots  # noqa: E402
from app.api.v1.endpoints import references_v1 as refs  # noqa: E402
from app.api.v1.endpoints import velvet_bot_v1 as vbot  # noqa: E402
from app.services import company_locale, crm_lab, production_v2  # noqa: E402
from app.services import reference_lifecycle as life  # noqa: E402
from app.services import references_v2 as rv2  # noqa: E402
from tests.test_references_op_order_pg import _migration_024g  # noqa: E402
from tests.test_references_sizes_pg import _migration, _setup  # noqa: E402
from tests.test_references_v2_pg import _company, pg_url  # noqa: E402,F401

BOG = ZoneInfo("America/Bogota")
WHO = "Dueña"
EMP = {"employee_id": "e1", "employee_name": "KRIS"}


async def _all_setup(url):
    company_locale.CURRENT_TZ.set(ZoneInfo("UTC"))  # pgserver no trae la base de zonas horarias
    engine, maker = await _setup(url)
    async with engine.begin() as conn:
        for stmt in _migration("025d_ref_lifecycle") + _migration("025d_ref_lifecycle") + _migration("025f_ref_cycles") + _migration("025f_ref_cycles"):  # idempotente
            await conn.execute(text(stmt))
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS reference_work_sessions (id text PRIMARY KEY, company_id text NOT NULL, employee_id text NOT NULL,
            employee_name text NULL, telegram_user_id text NULL, reference_id text NULL, reference_name text NOT NULL, started_at timestamptz NOT NULL DEFAULT now(),
            ended_at timestamptz NULL, duration_minutes numeric NOT NULL DEFAULT 0, status text NOT NULL DEFAULT 'active', source_channel text NOT NULL DEFAULT 'telegram',
            created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now())"""))
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS workforce_attendance_events (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, employee_id uuid NULL,
            event_type text, event_label text, status_after text, detail text, payload_json jsonb, metadata_json jsonb, occurred_at timestamptz, created_at timestamptz DEFAULT now())"""))
    return engine, maker


async def _on(db, cid, on=True):
    settings = '{"references_v2": true, "reference_lifecycle": true}' if on else '{"references_v2": true}'
    await db.execute(text("UPDATE company_modules SET settings = CAST(:s AS jsonb) WHERE company_id = CAST(:c AS uuid)"), {"c": cid, "s": settings})
    await db.commit()


async def _ref(db, cid, name, size, meta=0):
    row = await refs.create_reference(cid, {"name": name, "category": "Superior", "size": size, "color": "", "initial_quantity": meta, "channel": "bot"}, db)
    # El ciclo empezo antes de los cierres de prueba.
    await db.execute(text("UPDATE product_references SET activation_date = :d WHERE id = :i"), {"d": datetime(2026, 1, 1, tzinfo=timezone.utc), "i": row["id"]})
    await db.commit()
    return row


async def _cut(db, cid, rid, size, qty):
    await rv2.add_movements(db, cid, [{"reference_id": rid, "kind": "ingreso", "size": size, "quantity": qty, "event_date": "2026-10-10"}], WHO)


async def _closure(db, cid, rid, name, size, qty, when="2026-05-23 18:09:03+00"):
    await db.execute(text("""INSERT INTO reference_production_closures (id, company_id, employee_id, employee_name, reference_id, reference_name, size, quantity_finished, closed_at)
        VALUES (:i, :c, 'e1', 'KRIS', :r, :n, :z, :q, :w)"""), {"i": str(uuid.uuid4()), "c": cid, "r": rid, "n": name, "z": size, "q": qty, "w": datetime.fromisoformat(when.replace("+00", "+00:00"))})
    await db.commit()


async def _session(db, cid, name, rid, start, end, emp="e1", person="KRIS", status="ended_with_shift"):
    await db.execute(text("""INSERT INTO reference_work_sessions (id, company_id, employee_id, employee_name, reference_id, reference_name, started_at, ended_at, status)
        VALUES (:i, :c, :e, :p, :r, :n, :s, :f, :st)"""), {"i": str(uuid.uuid4()), "c": cid, "e": emp, "p": person, "r": rid, "n": name, "s": start, "f": end, "st": status})
    await db.commit()


async def _produced(db, cid, rid):
    return (await rv2.finished_by_reference(db, cid))[0][rid]


async def _bot_active(db, cid, rid):
    return (await db.execute(text("SELECT bot_active FROM product_references WHERE company_id = :c AND id = :i"), {"c": cid, "i": rid})).scalar()


def fix(cid, rid, value, **extra):
    return {"reference_id": rid, "new_value": value, "reason": "se metió por error", "confirm": True, "confirm_final": True, **extra}


# ---------------------------------------------------------------- corregir producido
@pytest.mark.asyncio
async def test_dreamy_jacket_28_a_0_con_doble_confirmacion_sin_borrar_nada(pg_url):
    engine, maker = await _all_setup(pg_url)
    async with maker() as db:
        cid = await _company(db, f"velvet{uuid.uuid4().hex[:6]}")
        await _on(db, cid)
        s = await _ref(db, cid, "Dreamy Jacket", "S", 132)
        await _cut(db, cid, s["id"], "S", 132)
        await _closure(db, cid, s["id"], "Dreamy Jacket", "SM", 28)
        assert await _produced(db, cid, s["id"]) == 28

        for missing in ({"confirm": False}, {"confirm_final": False}, {"reason": ""}):
            with pytest.raises(life.LifecycleError):
                await life.correct_produced(db, cid, {**fix(cid, s["id"], 0), **missing}, WHO)
        assert await _produced(db, cid, s["id"]) == 28, "sin las dos confirmaciones y el motivo no cambia nada"
        with pytest.raises(life.LifecycleError) as stale:
            await life.correct_produced(db, cid, fix(cid, s["id"], 0, expected_before=27), WHO)
        assert stale.value.code == "valor_cambio"

        out = await life.correct_produced(db, cid, fix(cid, s["id"], 0, expected_before=28), WHO)
        assert out["before"] == 28 and out["after"] == 0 and await _produced(db, cid, s["id"]) == 0

        rows = (await db.execute(text("""SELECT quantity_finished, source_channel, closed_at, created_at, notes FROM reference_production_closures
            WHERE company_id = :c ORDER BY quantity_finished DESC"""), {"c": cid})).mappings().all()
        assert [r["quantity_finished"] for r in rows] == [28, -28], "el cierre original sigue ahi"
        assert rows[1]["source_channel"] == life.CORRECTION_CHANNEL and rows[1]["closed_at"] == rows[0]["closed_at"], "neto en el periodo del cierre"
        assert rows[1]["created_at"] > rows[1]["closed_at"], "created_at dice cuando se corrigio"

        st = (await life.state(db, cid))[rv2.group_key("Dreamy Jacket")]
        assert st["corrections"][0] == {**st["corrections"][0], "size": "S", "before": 28, "after": 0, "actor": WHO, "reason": "se metió por error"}

        group = next(g for g in await rv2.reference_groups(db, cid) if g["name"] == "Dreamy Jacket")
        assert group["produced"] == 0 and group["pending"] == 132
    await engine.dispose()


@pytest.mark.asyncio
async def test_correccion_que_supera_lo_recibido_pide_confirmar(pg_url):
    engine, maker = await _all_setup(pg_url)
    async with maker() as db:
        cid = await _company(db, f"corr{uuid.uuid4().hex[:6]}")
        await _on(db, cid)
        s = await _ref(db, cid, "Lote", "S", 10)
        await _cut(db, cid, s["id"], "S", 10)
        with pytest.raises(life.LifecycleError) as over:
            await life.correct_produced(db, cid, fix(cid, s["id"], 12), WHO)
        assert over.value.code == "supera_lo_recibido" and over.value.status == 409 and over.value.extra["received"] == 10
        out = await life.correct_produced(db, cid, fix(cid, s["id"], 12, accept_over_received=True), WHO)
        assert out["over_received"] is True and await _produced(db, cid, s["id"]) == 12
    await engine.dispose()


# ---------------------------------------------------------------- bot: no mas de lo recibido sin aprobacion
@pytest.mark.asyncio
async def test_bot_no_registra_mas_de_lo_recibido_hasta_que_el_portal_apruebe(pg_url):
    engine, maker = await _all_setup(pg_url)
    async with maker() as db:
        cid = await _company(db, f"bot{uuid.uuid4().hex[:6]}")
        await _on(db, cid)
        s = await _ref(db, cid, "Lote", "S", 10)
        await _cut(db, cid, s["id"], "S", 10)
        await _closure(db, cid, s["id"], "Lote", "S", 8)
        ref = {"id": s["id"], "name": "Lote", "size": "S"}

        assert await life.bot_close_guard(db, cid, dict(ref), 2, EMP) is None, "hasta lo recibido: normal"
        warning = await life.bot_close_guard(db, cid, dict(ref), 3, EMP, "123")
        assert "no lo registré" in warning and "recibido 10" in warning
        await db.commit()
        assert await _produced(db, cid, s["id"]) == 8
        request = (await life.state(db, cid))[rv2.group_key("Lote")]["requests"][0]
        assert request["quantity"] == 3 and request["employee"] == "KRIS"

        await life.decide_request(db, cid, request["id"], False, WHO)
        assert await _produced(db, cid, s["id"]) == 8, "rechazado: no se registra"
        with pytest.raises(life.LifecycleError):
            await life.decide_request(db, cid, request["id"], True, WHO)

        await life.bot_close_guard(db, cid, dict(ref), 5, EMP)
        await db.commit()
        request = (await life.state(db, cid))[rv2.group_key("Lote")]["requests"][0]
        await life.decide_request(db, cid, request["id"], True, WHO)
        assert await _produced(db, cid, s["id"]) == 13, "aprobado: queda registrado"
        assert (await life.state(db, cid))[rv2.group_key("Lote")]["requests"] == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_bot_con_el_interruptor_apagado_no_cambia(pg_url):
    engine, maker = await _all_setup(pg_url)
    async with maker() as db:
        cid = await _company(db, f"off{uuid.uuid4().hex[:6]}")
        s = await _ref(db, cid, "Lote", "S", 10)
        await _cut(db, cid, s["id"], "S", 10)
        assert await life.bot_close_guard(db, cid, {"id": s["id"]}, 500, EMP) is None
        assert await life.over_limit(db, cid, s["id"]) is None
        assert not (await db.execute(text("SELECT 1 FROM reference_produced_requests WHERE company_id = :c"), {"c": cid})).first()
    await engine.dispose()


# ---------------------------------------------------------------- renombrar
@pytest.mark.asyncio
async def test_renombrar_conserva_todo_y_busca_por_cualquier_nombre(pg_url):
    engine, maker = await _all_setup(pg_url)
    async with maker() as db:
        cid = await _company(db, f"ren{uuid.uuid4().hex[:6]}")
        other = await _company(db, f"ren2{uuid.uuid4().hex[:6]}")
        await _on(db, cid)
        s, m = await _ref(db, cid, "Choco-fresa", "S", 44), await _ref(db, cid, "Choco-fresa", "M", 14)
        foreign = await _ref(db, other, "Choco-fresa", "S", 1)
        await _cut(db, cid, s["id"], "S", 44)
        await _closure(db, cid, s["id"], "Choco-fresa", "S", 4)
        await _closure(db, other, foreign["id"], "Choco-fresa", "S", 1)
        start = datetime(2026, 10, 15, 13, tzinfo=timezone.utc)
        await _session(db, cid, "Choco-fresa", s["id"], start, start + timedelta(hours=8))
        await _session(db, cid, "CHOCO-fresa", "", start + timedelta(days=1), start + timedelta(days=1, hours=2))  # copia sin id, otro formato
        await _session(db, other, "Choco-fresa", foreign["id"], start, start + timedelta(hours=1))
        await rv2.add_op_item(db, cid, rv2.group_key("Choco-fresa"), {"name": "Costura", "minutes": 30, "size": ""}, WHO)
        old_key = rv2.group_key("Choco-fresa")
        before = await life.account(db, cid, old_key, BOG)

        with pytest.raises(life.LifecycleError):
            await life.rename(db, cid, {"key": old_key, "new_name": "Choco nuevo"}, WHO)  # sin confirmar
        out = await life.rename(db, cid, {"key": old_key, "new_name": "Choco nuevo", "confirm": True}, WHO)
        new_key = out["key"]
        assert new_key == rv2.group_key("Choco nuevo") and out["old_name"] == "Choco-fresa"
        assert out["rows_changed"]["reference_work_sessions"] == 2 and out["rows_changed"]["reference_production_closures"] == 1

        # Historial intacto: mismas horas, tallas, cortes, producido y orden operacional.
        after = await life.account(db, cid, new_key, BOG)
        assert after["time"]["total_seconds"] == before["time"]["total_seconds"] == 10 * 3600
        group = next(g for g in await rv2.reference_groups(db, cid) if g["key"] == new_key)
        assert group["name"] == "Choco nuevo" and {x["size"] for x in group["lines"]} == {"S", "M"} and group["produced"] == 4 and group["received"] == 44
        assert len(await rv2.op_items(db, cid, new_key)) == 1
        assert not (await db.execute(text("SELECT 1 FROM reference_work_sessions WHERE company_id = :c AND reference_name <> 'Choco nuevo'"), {"c": cid})).first()

        # Busqueda: por nombre viejo y nuevo trae la MISMA referencia una sola vez.
        for q in ("choco-fresa", "Choco Fresa", "choco nuevo", "CHOCO"):
            found = await life.search(db, cid, q)
            assert [(x["key"], x["name"], x["former_names"]) for x in found] == [(new_key, "Choco nuevo", ["Choco-fresa"])], q

        # Bot y reportes con el nombre actual.
        assert {r["name"] for r in await vbot._references(db, cid)} == {"Choco nuevo"}
        assert (await db.execute(text("SELECT DISTINCT reference_name FROM reference_production_closures WHERE company_id = :c"), {"c": cid})).scalars().all() == ["Choco nuevo"]

        # Historial de nombres; una segunda vez encadena.
        await life.rename(db, cid, {"key": new_key, "new_name": "Choco tres", "confirm": True}, WHO)
        st = (await life.state(db, cid))[rv2.group_key("Choco tres")]
        assert st["former_names"] == ["Choco nuevo", "Choco-fresa"] and st["renames"][0]["new_name"] == "Choco tres" and st["renames"][0]["actor"] == WHO
        assert [x["name"] for x in await life.search(db, cid, "choco-fresa")] == ["Choco tres"]

        # La otra empresa, intacta.
        assert (await db.execute(text("SELECT name FROM product_references WHERE company_id = :c"), {"c": other})).scalars().all() == ["Choco-fresa"]
        assert (await db.execute(text("SELECT reference_name FROM reference_work_sessions WHERE company_id = :c"), {"c": other})).scalars().all() == ["Choco-fresa"]
        assert (await db.execute(text("SELECT reference_name FROM reference_production_closures WHERE company_id = :c"), {"c": other})).scalars().all() == ["Choco-fresa"]
        assert m["id"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_nombre_duplicado_rechazado_y_el_patch_no_se_salta_el_historial(pg_url):
    engine, maker = await _all_setup(pg_url)
    async with maker() as db:
        cid = await _company(db, f"dup{uuid.uuid4().hex[:6]}")
        await _on(db, cid)
        a = await _ref(db, cid, "Garden verde", "S", 1)
        await _ref(db, cid, "Aurora Azul", "S", 1)
        archived = await _ref(db, cid, "Vieja", "S", 1)
        await db.execute(text("UPDATE product_references SET archived = true WHERE id = :i"), {"i": archived["id"]})
        await db.commit()
        for taken in ("Aurora Azul", "aurora  azúl", "AURORAAZUL", "Vieja"):
            with pytest.raises(life.LifecycleError) as dup:
                await life.rename(db, cid, {"key": rv2.group_key("Garden verde"), "new_name": taken, "confirm": True}, WHO)
            assert dup.value.code == "nombre_duplicado" and dup.value.status == 409, taken
        same = await life.rename(db, cid, {"key": rv2.group_key("Garden verde"), "new_name": "GARDEN verde", "confirm": True}, WHO)
        assert same["name"] == "GARDEN verde", "cambiar solo mayusculas si se puede"

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as patch:
            await refs.update_reference(cid, a["id"], {"name": "Otro"}, db)
        assert patch.value.status_code == 409 and patch.value.detail["code"] == "usa_cambiar_nombre"
    await engine.dispose()


# ---------------------------------------------------------------- cerrar por talla
async def _lote(db, cid):
    s, m = await _ref(db, cid, "Lote", "S", 44), await _ref(db, cid, "Lote", "M", 14)
    await _cut(db, cid, s["id"], "S", 44)
    await _cut(db, cid, m["id"], "M", 14)
    await _closure(db, cid, s["id"], "Lote", "S", 40, "2026-10-20 15:00+00")
    await _closure(db, cid, m["id"], "Lote", "M", 14, "2026-10-20 15:00+00")
    start = datetime(2026, 10, 15, 13, tzinfo=timezone.utc)
    await _session(db, cid, "Lote", s["id"], start, start + timedelta(hours=9))
    return s, m


def _no_team(monkeypatch):
    async def team(db, company_id, now=None):
        return {"working": 0, "paused": 0, "live": []}

    monkeypatch.setattr(crm_lab, "team", team)


async def _rates(monkeypatch, value=10000 / 3600):
    async def rates(db, company_id, months):
        return {month: {"e1": value, "e2": value} for month in months}

    monkeypatch.setattr(life, "month_rates", rates)


@pytest.mark.asyncio
async def test_terminar_ciclo_suma_a_producido_baja_pendiente_y_no_oculta_nada(pg_url, monkeypatch):
    engine, maker = await _all_setup(pg_url)
    _no_team(monkeypatch)
    await _rates(monkeypatch)
    async with maker() as db:
        cid = await _company(db, f"cyc{uuid.uuid4().hex[:6]}")
        await _on(db, cid)
        s, m = await _lote(db, cid)
        key = rv2.group_key("Lote")
        day = (date(2026, 10, 1), date(2026, 10, 31), date(2026, 10, 31))
        assert await _produced(db, cid, s["id"]) == 40

        for bad in ({"quantity": 0}, {"quantity": "x"}, {"quantity": -3}, {"confirm": False}):
            with pytest.raises(life.LifecycleError):
                await life.finish_cycle(db, cid, {"key": key, "size": "S", "quantity": 4, "confirm": True, **bad}, WHO)
        assert await _produced(db, cid, s["id"]) == 40, "sin cantidad valida ni confirmacion no cambia nada"
        with pytest.raises(life.LifecycleError) as stale:
            await life.finish_cycle(db, cid, {"key": key, "size": "S", "quantity": 4, "confirm": True, "expected_before": 39}, WHO)
        assert stale.value.code == "valor_cambio"

        out = await life.finish_cycle(db, cid, {"key": key, "size": "S", "quantity": 4, "confirm": True, "expected_before": 40}, WHO)
        assert out["produced"] == 44 and out["pending"] == 0 and out["quantity"] == 4
        assert await _produced(db, cid, s["id"]) == 44, "se SUMA a lo producido"
        line = next(x for g in await rv2.reference_groups(db, cid) if g["key"] == key for x in g["lines"] if x["size"] == "S")
        assert line["produced"] == 44 and line["pending"] == 0
        await life.finish_cycle(db, cid, {"key": key, "size": "M", "quantity": 6, "confirm": True}, WHO)
        assert await _produced(db, cid, m["id"]) == 20

        st = (await life.state(db, cid))[key]
        assert [(c["size"], c["quantity"], c["actor"]) for c in st["cycles"]] == [("M", 6, WHO), ("S", 4, WHO)], "historial de la talla"
        assert st["status"] == "open" and st["closes"] == []
        # Nada se cierra ni se oculta: el bot sigue igual y la referencia sigue en proceso.
        assert await _bot_active(db, cid, s["id"]) is True and await _bot_active(db, cid, m["id"]) is True
        assert [x["size"] for x in await bots.sizes_by_reference_id(db, cid, m["id"])] == ["M", "S"], "las dos tallas siguen en el bot"
        assert await life.bot_close_guard(db, cid, {"id": s["id"]}, 0, EMP) is None
        ins = await production_v2.insights(db, cid, *day)
        assert ins["lifecycle"] is True and ins["lots_closed"] == [], "ninguna referencia queda cerrada"

        # Cerrar talla ya no existe.
        with pytest.raises(life.LifecycleError) as gone:
            await life.close_size(db, cid, {"key": key, "size": "S", "closed_qty": 4, "reason_code": "entrega", "confirm": True}, WHO)
        assert gone.value.code == "usa_terminar_ciclo" and gone.value.status == 410

        # Total de la referencia con Producido: horas y mano de obra por prenda.
        acc = await life.account(db, cid, key, ZoneInfo("UTC"))
        t = acc["totals"]
        assert (t["meta"], t["received"], t["produced"], t["pending"]) == (58, 58, 64, 0)
        assert t["seconds"] == 9 * 3600 and t["minutes_per_garment"] == round(9 * 3600 / 64 / 60, 1)
        assert t["labor_per_garment"] == round(90000 / 64, 2)
        assert acc["status"] == "open" and acc["closed_sizes"] == 0

        # Renombrar lleva el historial de ciclos.
        await life.rename(db, cid, {"key": key, "new_name": "Lote Nuevo", "confirm": True}, WHO)
        assert len((await life.state(db, cid))[rv2.group_key("Lote Nuevo")]["cycles"]) == 2
    await engine.dispose()


def test_cuenta_sin_producido_muestra_raya():
    group = {"lines": [{"size": "S", "reference_id": "a", "meta": 10, "received": 10, "produced": 0}]}
    acc = life.accounts(group, [], {"total_seconds": 3600}, {"status": "ok", "amount": 5000.0}, ZoneInfo("UTC"))
    assert acc["totals"]["minutes_per_garment"] is None and acc["totals"]["labor_per_garment"] is None
    assert acc["sizes"][0]["minutes_per_garment"] is None and acc["sizes"][0]["pending"] == 10


async def _close_row(db, cid, key, size, rid, qty, actor, at, reopened=False, prev_bot=False, channel="system", reason="entrega"):
    await db.execute(text("""INSERT INTO reference_size_closes (company_id, ref_key, size, reference_id, closed_qty, meta, received, reason_code, prev_bot_active, prev_channel, actor, closed_at,
        reopened_at, reopened_by, reopen_reason) VALUES (:c, :k, :z, :r, :q, 0, 0, :why, :pb, :ch, :a, :at, :ro, :rb, :rr)"""),
                     {"c": cid, "k": key, "z": size, "r": rid, "q": qty, "why": reason, "pb": prev_bot, "ch": channel, "a": actor, "at": at,
                      "ro": at + timedelta(minutes=10) if reopened else None, "rb": "Admin V2" if reopened else None, "rr": "error de cierre" if reopened else None})
    await db.commit()


@pytest.mark.asyncio
async def test_cierres_guardados_pasan_a_ciclos_y_dreamy_s_queda_activa_con_52(pg_url):
    engine, maker = await _all_setup(pg_url)
    async with maker() as db:
        cid = await _company(db, f"dreamy{uuid.uuid4().hex[:6]}")
        await _on(db, cid)
        s = await _ref(db, cid, "Dreamy Jacket", "S", 132)
        m = await _ref(db, cid, "Dreamy Jacket", "M", 80)
        await _cut(db, cid, s["id"], "S", 132)
        await _cut(db, cid, m["id"], "M", 80)
        await _closure(db, cid, s["id"], "Dreamy Jacket", "SM", 28)
        await _closure(db, cid, m["id"], "Dreamy Jacket", "ML", 10)
        await life.correct_produced(db, cid, fix(cid, s["id"], 0, expected_before=28), "Admin V2")
        await db.execute(text("UPDATE product_references SET bot_active = false, channel = 'system' WHERE id = :i"), {"i": s["id"]})
        await db.commit()
        key = rv2.group_key("Dreamy Jacket")
        at = datetime(2026, 11, 9, 14, 33, 29, tzinfo=timezone.utc)  # 9 nov 09:33 en Bogota
        await _close_row(db, cid, key, "S", s["id"], 52, "Admin V2", at, reopened=True)
        # Otra referencia con un cierre VIGENTE que apago el bot: queda activa y vuelve al bot.
        x = await _ref(db, cid, "Otra", "L", 10)
        await _close_row(db, cid, rv2.group_key("Otra"), "L", x["id"], 9, "Velvet Admin", at, prev_bot=True, channel="both", reason="cierre_ciclo")
        await db.execute(text("UPDATE product_references SET bot_active = false, channel = 'system' WHERE id = :i"), {"i": x["id"]})
        await db.commit()
        assert await life.size_is_closed(db, cid, rv2.group_key("Otra"), "L") is True

        await db.commit()  # sin transaccion abierta: la migracion necesita la tabla
        async with engine.begin() as conn:  # la migracion, dos veces: no duplica nada
            for stmt in _migration("025f_ref_cycles") + _migration("025f_ref_cycles"):
                await conn.execute(text(stmt))

        assert await _produced(db, cid, s["id"]) == 52
        line = next(x for g in await rv2.reference_groups(db, cid) if g["key"] == key for x in g["lines"] if x["size"] == "S")
        assert (line["produced"], line["pending"]) == (52, 80)
        st = (await life.state(db, cid))[key]
        assert st["status"] == "open" and st["closes"] == [] and st["reopened"] == []
        assert [(c["size"], c["quantity"], c["actor"], c["reason_label"]) for c in st["cycles"]] == [("S", 52, "Admin V2", "Entrega")]
        assert datetime.fromisoformat(st["cycles"][0]["at"]) == at
        assert [(c["before"], c["after"], c["reason"]) for c in st["corrections"]] == [(28, 0, "se metió por error")], "la corrección se mantiene"
        assert await _bot_active(db, cid, s["id"]) is False, "S estaba oculta del bot por su interruptor: se queda igual"

        assert await life.size_is_closed(db, cid, rv2.group_key("Otra"), "L") is False
        assert await _bot_active(db, cid, x["id"]) is True, "el cierre vigente habia apagado el bot: vuelve"
        assert await _produced(db, cid, x["id"]) == 9
        rows = (await db.execute(text("SELECT converted_at IS NOT NULL AS done, converted_cycle_id IS NOT NULL AS cyc, closed_qty, reopened_at IS NOT NULL AS ro FROM reference_size_closes WHERE company_id = :c ORDER BY closed_qty"),
                                 {"c": cid})).mappings().all()
        assert [(r["done"], r["cyc"], r["closed_qty"]) for r in rows] == [(True, True, 9), (True, True, 52)], "los originales quedan, marcados como convertidos"
        n = (await db.execute(text("SELECT count(*) FROM reference_finished_cycles WHERE company_id = :c"), {"c": cid})).scalar()
        assert n == 2
        src = (await db.execute(text("SELECT source_channel, employee_name, closed_at FROM reference_production_closures WHERE company_id = :c AND quantity_finished = 52"), {"c": cid})).mappings().one()
        assert src["source_channel"] == life.CYCLE_CHANNEL and src["employee_name"] == "Admin V2" and src["closed_at"] == at
    await engine.dispose()


@pytest.mark.asyncio
async def test_corte_en_referencia_recien_creada_se_ve_en_balance_tarjeta_editor_y_produccion(pg_url, monkeypatch):
    engine, maker = await _all_setup(pg_url)
    _no_team(monkeypatch)
    async with maker() as db:
        cid = await _company(db, f"roj{uuid.uuid4().hex[:6]}")
        await _on(db, cid)
        out = await refs.v2_catalog_create(cid, {"name": "rojita medium", "color": "rojo", "gender": "mujer", "body_part": "superior", "garment_type": "chaqueta",
                                                 "sizes": [{"size": "S", "quantity": 46}, {"size": "M", "quantity": 25}]}, actor=WHO, db=db)
        s, m = (next(r for r in out["items"] if r["size"] == z) for z in ("S", "M"))
        today = date.today().isoformat()
        items = [{"reference_id": s["id"], "kind": "ingreso", "size": "S", "quantity": 40, "event_date": today},
                 {"reference_id": m["id"], "kind": "ingreso", "size": "M", "quantity": 22, "event_date": today},
                 {"reference_id": s["id"], "kind": "novedad", "section": "corte", "quantity": 2, "note": "manchadas", "event_date": today},
                 {"reference_id": s["id"], "kind": "despliegue", "size": "S", "quantity": 1, "event_date": today}]
        saved = await refs.v2_add_movements(cid, {"items": items}, actor=WHO, db=db)
        assert saved["count"] == 4
        bal = await rv2.balance(db, cid, s["id"])
        assert (bal["received"], bal["novelty"], bal["deployed"], bal["available"]) == (62, 2, 1, 59)
        assert {x["kind"] for x in bal["log"]} == {"ingreso", "novedad", "despliegue"} and not any(x["size_without_reference"] for x in bal["log"])
        g = next(x for x in await rv2.reference_groups(db, cid) if x["key"] == rv2.group_key("rojita medium"))
        assert {x["size"]: x["received"] for x in g["lines"]} == {"S": 40, "M": 22} and g["received"] == 62
        assert g["cuts_by_date"][0]["total"] == 62 and {x["size"]: x["quantity"] for x in g["cuts_by_date"][0]["sizes"]} == {"S": 40, "M": 22}
        ins = await production_v2.insights(db, cid, date.today(), date.today(), date.today())
        assert any(lot["name"] == "rojita medium" for lot in ins["lots_in_process"])

        # Talla que la referencia no tiene: aviso claro antes de guardar; con confirmacion se guarda.
        with pytest.raises(refs.HTTPException) as warn:
            await refs.v2_add_movements(cid, {"items": [{"reference_id": s["id"], "kind": "ingreso", "size": "L", "quantity": 5, "event_date": today}]}, actor=WHO, db=db)
        assert warn.value.status_code == 409 and warn.value.detail["code"] == "talla_sin_referencia"
        assert "rojita medium no tiene talla L" in warn.value.detail["message"]
        assert (await rv2.balance(db, cid, s["id"]))["received"] == 62, "sin confirmar no se guarda"
        await refs.v2_add_movements(cid, {"items": [{"reference_id": s["id"], "kind": "ingreso", "size": "L", "quantity": 5, "event_date": today}], "confirm_new_sizes": True}, actor=WHO, db=db)
        assert (await rv2.balance(db, cid, s["id"]))["received"] == 67

        # Otra empresa (sin reference_lifecycle): igual que siempre, sin aviso.
        other = await _company(db, f"oth{uuid.uuid4().hex[:6]}")
        await _on(db, other, on=False)
        r = await _ref(db, other, "Blusa", "S", 5)
        await refs.v2_add_movements(other, {"items": [{"reference_id": r["id"], "kind": "ingreso", "size": "XL", "quantity": 3, "event_date": today}]}, actor=WHO, db=db)
        assert (await rv2.balance(db, other, r["id"]))["received"] == 3
    await engine.dispose()


@pytest.mark.asyncio
async def test_sin_interruptor_produccion_no_cambia(pg_url, monkeypatch):
    engine, maker = await _all_setup(pg_url)
    _no_team(monkeypatch)
    captured = {}
    original = production_v2.build

    def spy(**kwargs):
        captured.update(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(production_v2, "build", spy)
    async with maker() as db:
        cid = await _company(db, f"off2{uuid.uuid4().hex[:6]}")
        await _lote(db, cid)
        ins = await production_v2.insights(db, cid, date(2026, 10, 1), date(2026, 10, 31), date(2026, 10, 31))
        assert "lifecycle" not in ins and "lots_closed" not in ins and "all_lots" not in ins
        assert captured.get("closed_lot_keys") is None
        assert "account" not in ins["lots_in_process"][0]
    await engine.dispose()


def test_revision_id_cabe_en_alembic():
    from migrations.versions import __path__  # noqa: F401
    import importlib

    module = importlib.import_module("migrations.versions.025d_ref_lifecycle")
    assert len(module.revision) <= 32 and module.down_revision == "025c_lider_v2"
    cycles = importlib.import_module("migrations.versions.025f_ref_cycles")
    assert len(cycles.revision) <= 32 and cycles.down_revision == "025e_work_schedule"
    assert _migration_024g()
