"""Corregir producido, renombrar y cerrar por talla contra Postgres real (interruptor reference_lifecycle).

- Dreamy Jacket S: 28 -> 0 con doble confirmacion, sin borrar nada, con historial.
- Producido > recibido: el portal pide confirmar; el bot avisa y no registra sin aprobacion.
- Renombrar: una sola referencia por nombre viejo y nuevo, historial intacto, nombre duplicado rechazado.
- Cerrar por talla: cuenta, motivo, referencia cerrada fuera de "en proceso" y del bot, reabrir.
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
        for stmt in _migration("025d_ref_lifecycle") + _migration("025d_ref_lifecycle"):  # idempotente
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
async def test_cerrar_todas_las_tallas_cierra_la_referencia_y_reabrir_la_devuelve(pg_url, monkeypatch):
    engine, maker = await _all_setup(pg_url)
    _no_team(monkeypatch)
    await _rates(monkeypatch)
    async with maker() as db:
        cid = await _company(db, f"close{uuid.uuid4().hex[:6]}")
        await _on(db, cid)
        s, m = await _lote(db, cid)
        key = rv2.group_key("Lote")
        day = (date(2026, 10, 1), date(2026, 10, 31), date(2026, 10, 31))

        ins = await production_v2.insights(db, cid, *day)
        assert [lot["name"] for lot in ins["lots_in_process"]] == ["Lote"] and ins["lots_closed"] == [] and ins["lifecycle"] is True
        lot = ins["lots_in_process"][0]
        assert lot["total_seconds"] == 9 * 3600 and lot["period_seconds"] == 9 * 3600 and lot["people"][0]["name"] == "KRIS"

        # Menos de lo recibido: motivo obligatorio.
        with pytest.raises(life.LifecycleError) as reason:
            await life.close_size(db, cid, {"key": key, "size": "S", "closed_qty": 40, "confirm": True}, WHO)
        assert reason.value.code == "motivo_requerido" and reason.value.extra["received"] == 44
        with pytest.raises(life.LifecycleError):
            await life.close_size(db, cid, {"key": key, "size": "S", "closed_qty": 40, "reason_code": "otro", "confirm": True}, WHO)  # otro sin detalle
        with pytest.raises(life.LifecycleError):
            await life.close_size(db, cid, {"key": key, "size": "S", "closed_qty": 40, "reason_code": "merma"}, WHO)  # sin confirmar

        out = await life.close_size(db, cid, {"key": key, "size": "S", "closed_qty": 40, "reason_code": "merma", "confirm": True}, WHO)
        assert out["reference_closed"] is False
        assert await _bot_active(db, cid, s["id"]) is False, "el bot deja de ofrecer esa talla"
        assert await _bot_active(db, cid, m["id"]) is True
        assert [x["size"] for x in await bots.sizes_by_reference_id(db, cid, m["id"])] == ["M"]
        with pytest.raises(life.LifecycleError) as again:
            await life.close_size(db, cid, {"key": key, "size": "S", "closed_qty": 40, "reason_code": "merma", "confirm": True}, WHO)
        assert again.value.code == "ya_cerrada"
        with pytest.raises(refs.HTTPException) as show:
            await refs.update_reference(cid, s["id"], {"channel": "bot"}, db)
        assert show.value.status_code == 409 and show.value.detail["code"] == "talla_cerrada"

        # Sesion abierta: no se puede cerrar la ultima talla.
        now = datetime(2026, 10, 30, 13, tzinfo=timezone.utc)
        await _session(db, cid, "Lote", m["id"], now, None, emp="e2", person="TATA", status="active")
        with pytest.raises(life.LifecycleError) as open_session:
            await life.close_size(db, cid, {"key": key, "size": "M", "closed_qty": 14, "confirm": True}, WHO)
        assert open_session.value.code == "sesiones_abiertas" and open_session.value.extra["people"] == ["TATA"]
        await db.execute(text("UPDATE reference_work_sessions SET ended_at = :e, status = 'switched' WHERE company_id = :c AND ended_at IS NULL"), {"e": now + timedelta(hours=1), "c": cid})
        await db.commit()

        out = await life.close_size(db, cid, {"key": key, "size": "M", "closed_qty": 14, "confirm": True}, WHO)
        assert out["reference_closed"] is True
        assert await vbot._references(db, cid) == [], "el bot deja de ofrecerla"
        assert (await life.state(db, cid))[key]["status"] == "closed"

        ins = await production_v2.insights(db, cid, *day)
        assert ins["lots_in_process"] == [] and [lot["name"] for lot in ins["lots_closed"]] == ["Lote"]
        acc = ins["lots_closed"][0]["account"]
        assert acc["status"] == "closed" and acc["totals"]["closed_qty"] == 54 and acc["totals"]["seconds"] == 10 * 3600
        assert sum(x["seconds"] for x in acc["sizes"]) == acc["totals"]["seconds"] and sum(x["labor"] for x in acc["sizes"]) == acc["totals"]["labor"] == 100000.0
        assert {x["size"]: x["diff_received"] for x in acc["sizes"]} == {"S": -4, "M": 0}
        assert acc["allocation"] == "repartido por cantidad"
        pdf = production_v2.build_pdf(ins, {"name": "Velvet"})
        assert pdf[:4] == b"%PDF"

        # Reabrir: doble confirmacion y motivo; todo vuelve y queda la auditoria.
        with pytest.raises(life.LifecycleError):
            await life.reopen(db, cid, {"key": key, "size": "S", "reason": "faltó contar", "confirm": True}, WHO)
        with pytest.raises(life.LifecycleError):
            await life.reopen(db, cid, {"key": key, "size": "S", "reason": "", "confirm": True, "confirm_final": True}, WHO)
        await life.reopen(db, cid, {"key": key, "size": "S", "reason": "faltó contar", "confirm": True, "confirm_final": True}, WHO)
        assert await _bot_active(db, cid, s["id"]) is True and await _bot_active(db, cid, m["id"]) is False
        st = (await life.state(db, cid))[key]
        assert st["status"] == "open" and st["reopened"][0]["reason"] == "faltó contar" and st["reopened"][0]["actor"] == WHO
        ins = await production_v2.insights(db, cid, *day)
        assert [lot["name"] for lot in ins["lots_in_process"]] == ["Lote"] and ins["lots_closed"] == []

        await life.reopen(db, cid, {"key": key, "reason": "reabrir toda", "confirm": True, "confirm_final": True}, WHO)
        assert await _bot_active(db, cid, m["id"]) is True and (await life.state(db, cid))[key]["closes"] == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_guardia_del_bot_rechaza_una_talla_cerrada(pg_url):
    engine, maker = await _all_setup(pg_url)
    async with maker() as db:
        cid = await _company(db, f"cl2{uuid.uuid4().hex[:6]}")
        await _on(db, cid)
        s, _ = await _lote(db, cid)
        await life.close_size(db, cid, {"key": rv2.group_key("Lote"), "size": "S", "closed_qty": 44, "confirm": True}, WHO)
        assert "ya está cerrada" in await life.bot_close_guard(db, cid, {"id": s["id"]}, 1, EMP)
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
    assert _migration_024g()
