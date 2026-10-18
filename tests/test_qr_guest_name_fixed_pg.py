"""Nombre FIJO del invitado del QR (interruptor qr_welcome_name) contra Postgres REAL.

- Con nombre puesto, renombrar desde el QR responde 409 (aunque se llame directo).
- Con el nombre por defecto se agrega UNA vez; la segunda da 409.
- Un pedido nunca se bloquea: si trae otro nombre se usa el fijo.
- Solo el bar (dueno, admin o barman) corrige: bitacora (anterior, nuevo, quien,
  cuando) y se ve en el QR, la barra, la cocina, los retos y Reportes. Otro rol: 403.
- Sin el interruptor el QR renombra como siempre.
"""
from __future__ import annotations

import importlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

pgserver = pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402

from app.api.v1.endpoints import hospitality as hsp  # noqa: E402
from app.api.v1.endpoints import waiter_ordering  # noqa: E402
from app.services import loyalty_retos as svc  # noqa: E402
from tests.test_loyalty_end_cancel_qr_name_pg import _account, _qr_company, _qr_order  # noqa: E402
from tests.test_loyalty_retos_pg import _session, env, pg_url  # noqa: E402,F401


async def _log_table(db):
    module = importlib.import_module("migrations.versions.024o_qr_guest_name_log")
    statements: list[str] = []
    module.op = SimpleNamespace(execute=lambda q: statements.append(str(q)))
    module.upgrade()
    for stmt in statements:
        await db.execute(text(stmt))
    await db.commit()
    assert len(module.revision) <= 32 and module.down_revision == "024n_loyalty_cancel"


def _req():
    return SimpleNamespace(base_url="https://bar.test/", headers={}, client=SimpleNamespace(host="1.1.1.1"))


async def _rows(db, cid):
    rows = (await db.execute(text("SELECT * FROM hospitality_orders WHERE company_id::text = :c ORDER BY created_at"), {"c": cid})).mappings().all()
    return [dict(r) for r in rows]


def _meta(row):
    return row["metadata"] if isinstance(row["metadata"], dict) else json.loads(row["metadata"])


@pytest.mark.asyncio
async def test_name_is_fixed_once_set_and_default_can_be_added_once(pg_url):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _qr_company(db, welcome=True)
        u = uuid.UUID(cid)
        first = await hsp.get_hospitality_table_account(u, _account("Nicolas"), db)
        assert first["guest"] == {"name": "Nicolas", "display_name": "Nicolas", "named": True}
        assert (await hsp.get_hospitality_table_account(u, _account("Nicolas"), db))["guest"]["name"] == "Nicolas", "el mismo nombre no es un cambio"
        assert (await hsp.get_hospitality_table_account(u, _account(""), db))["guest"]["named"] is True, "sin nombre: conserva el fijo"
        with pytest.raises(HTTPException) as exc:
            await hsp.get_hospitality_table_account(u, _account("Otro nombre"), db)
        assert exc.value.status_code == 409 and exc.value.detail == "nombre_fijo", "renombrar desde el QR (directo al endpoint) da 409"
        await db.rollback()
        # Un pedido con otro nombre no se bloquea: usa el fijo.
        await _qr_order(db, cid, "Intruso")
        assert (await _rows(db, cid))[-1]["customer_name"] == "Nicolas"
        # "Ahora no": nombre por defecto; puede agregarlo UNA vez.
        skip = await hsp.get_hospitality_table_account(u, _account("", "qr_account_b"), db)
        assert skip["guest"] == {"name": "", "display_name": "Persona 2", "named": False}
        added = await hsp.get_hospitality_table_account(u, _account("Laura", "qr_account_b"), db)
        assert added["guest"]["named"] is True and added["guest"]["name"] == "Laura"
        with pytest.raises(HTTPException) as exc:
            await hsp.get_hospitality_table_account(u, _account("Laurita", "qr_account_b"), db)
        assert exc.value.status_code == 409, "la segunda vez da 409"
        await db.rollback()
    await engine.dispose()


@pytest.mark.asyncio
async def test_without_the_switch_the_qr_renames_as_always(pg_url):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _qr_company(db, welcome=False)
        u = uuid.UUID(cid)
        a = await hsp.get_hospitality_table_account(u, _account("Nicolas"), db)
        assert "guest" not in a
        await hsp.get_hospitality_table_account(u, _account("Nico"), db)
        name = (await db.execute(text("SELECT name FROM hospitality_table_guests WHERE company_id::text = :c"), {"c": cid})).scalar()
        assert name == "Nico", "sin el interruptor se cambia como siempre"
        with pytest.raises(HTTPException) as exc:
            await hsp.qr_guests_config(u, db, {"role": "admin", "name": "x"})
        assert exc.value.status_code == 404
        with pytest.raises(HTTPException) as exc:
            await hsp.rename_qr_guest(u, hsp.HospitalityGuestRenameIn(table="Mesa 4", account_id="qr_account_a", name="X"), db, {"role": "admin", "name": "x"})
        assert exc.value.status_code == 404
    await engine.dispose()


@pytest.mark.asyncio
async def test_the_bar_fixes_a_guest_name_everywhere_with_a_log(pg_url, monkeypatch):
    from app.api import deps
    from app.web import admin_v2_routes

    engine, maker = await _session(pg_url)
    async with maker() as db:
        await _log_table(db)
        cid = await _qr_company(db, welcome=True)
        u = uuid.UUID(cid)
        await hsp.get_hospitality_table_account(u, _account("Nicolsa"), db)
        await _qr_order(db, cid, "")
        await _qr_order(db, cid, "")
        # Un pedido de esta sesion ya cerrado tambien se corrige (Reportes).
        first_id = (await _rows(db, cid))[0]["id"]
        await db.execute(text("UPDATE hospitality_orders SET status = 'cerrado' WHERE id = :i"), {"i": first_id})
        # Un reto de la mesa con el nombre anterior.
        now = datetime.now(timezone.utc)
        reto = await svc.create(db, cid, {"type": "consumption", "prize": "Ron", "registration_ends_at": (now + timedelta(minutes=30)).isoformat(),
                                          "starts_at": (now + timedelta(minutes=30)).isoformat(), "ends_at": (now + timedelta(hours=2)).isoformat()}, "dueno")
        await hsp.join_loyalty_campaign(u, uuid.UUID(reto["id"]), hsp.HospitalityLoyaltyParticipantIn(table="Mesa 4", team_name="Nicolsa"), db)
        await db.commit()
        # Permisos: el bar si; otro rol 403.
        monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=False))
        for role, ok in (("company_admin", True), ("barman", True), ("mesero", False), ("operario", False)):
            monkeypatch.setattr(deps, "require_company_user_for_tenant", AsyncMock(return_value=SimpleNamespace(role=role, email=f"{role}@bar", settings_json={})))
            monkeypatch.setattr(hsp, "require_company_user_for_tenant", deps.require_company_user_for_tenant)
            if ok:
                assert (await hsp._qr_guest_editor(u, _req(), "Bearer x", db))["role"] in ("admin", "barman")
            else:
                with pytest.raises(HTTPException) as exc:
                    await hsp._qr_guest_editor(u, _req(), "Bearer x", db)
                assert exc.value.status_code == 403
        assert (await hsp.qr_guests_config(u, db, {"role": "barman", "name": "barman@bar"}))["ok"] is True
        out = await hsp.rename_qr_guest(u, hsp.HospitalityGuestRenameIn(table="Mesa 4", account_id="qr_account_a", name="<b>Nicolás</b>"), db,
                                        {"role": "barman", "name": "barman@bar"})
        assert out["changed"] is True and out["name"] == "Nicolás" and out["old_name"] == "Nicolsa" and out["orders"] == 2
        log = (await db.execute(text("SELECT old_name, new_name, changed_by, changed_at, account_id FROM hospitality_guest_name_log WHERE company_id::text = :c"),
                                {"c": cid})).mappings().all()
        assert len(log) == 1 and log[0]["old_name"] == "Nicolsa" and log[0]["new_name"] == "Nicolás" and log[0]["changed_by"] == "barman@bar" and log[0]["changed_at"]
        # QR: el invitado ve el nombre corregido (y sigue fijo para el).
        qr = await hsp.get_hospitality_table_account(u, _account(""), db)
        assert qr["guest"]["name"] == "Nicolás"
        with pytest.raises(HTTPException):
            await hsp.get_hospitality_table_account(u, _account("Nicolsa"), db)
        await db.rollback()
        rows = await _rows(db, cid)
        for row in rows:
            people = row["people"] if isinstance(row["people"], list) else json.loads(row["people"])
            assert row["customer_name"] == "Nicolás" and people[0]["name"] == "Nicolás" and _meta(row)["guest_name"] == "Nicolás", "barra y Reportes"
        open_row = next(r for r in rows if r["status"] != "cerrado")
        assert waiter_ordering._comanda(hsp._payload(open_row), set())["guest_name"] == "Nicolás", "cocina"
        event = hsp._hsp_event_payload([hsp._payload(r) for r in rows], event_id="e", event_type="qr", location="Mesa 4")
        assert event["guest_names"] == ["Nicolás"]
        team = (await db.execute(text("SELECT team_name FROM hospitality_loyalty_participants WHERE company_id::text = :c"), {"c": cid})).scalar()
        assert team == "Nicolás", "retos de la mesa"
        same = await hsp.rename_qr_guest(u, hsp.HospitalityGuestRenameIn(table="Mesa 4", account_id="qr_account_a", name="Nicolás"), db, {"role": "admin", "name": "d"})
        assert same["changed"] is False
        with pytest.raises(HTTPException) as exc:
            await hsp.rename_qr_guest(u, hsp.HospitalityGuestRenameIn(table="Mesa 4", account_id="no-existe", name="X"), db, {"role": "admin", "name": "d"})
        assert exc.value.status_code == 404
        with pytest.raises(HTTPException) as exc:
            await hsp.rename_qr_guest(u, hsp.HospitalityGuestRenameIn(table="Mesa 4", account_id="qr_account_a", name="<>"), db, {"role": "admin", "name": "d"})
        assert exc.value.status_code == 422
    await engine.dispose()


def test_rename_routes_need_the_bar_session():
    for r in hsp.router.routes:
        if "/qr-guests/" in r.path:
            assert hsp._qr_guest_editor in [d.call for d in r.dependant.dependencies], r.path
