"""Cocina en 3 columnas (Pedido nuevo -> Preparando -> Listo) + Entregado.

The chain runs through Hospitality's REAL update_hospitality_order_status
(its real pendiente -> alistando -> entregado -> cerrado transition map) and
the caja's REAL close_hospitality_order, against a small in-memory fake of
hospitality_orders. Only I/O is faked (row storage, inventory deduction,
table access), never the transition rules -- so a "Transicion no permitida"
regression fails here exactly like it failed in production.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import json
import re
import uuid

from fastapi import HTTPException
import pytest

from app.api.v1.endpoints import hospitality, waiter_ordering


COMPANY_ID = uuid.uuid4()


def _user(role: str, name: str):
    return SimpleNamespace(id=uuid.uuid4(), full_name=name, role=role, settings_json={})


class FakeOrdersDb:
    """Just enough of hospitality_orders for the kitchen/caja flow."""

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    def add(self, table="Mesa 4", waiter=None, status="pendiente", created_minutes_ago=5, company_id=COMPANY_ID):
        order_id = str(uuid.uuid4())
        self.rows[order_id] = {
            "id": order_id,
            "company_id": str(company_id),
            "table_number": table,
            "table_key": table.lower(),
            "order_type": "table",
            "source": "table_manual",
            "status": status,
            "items": [{"id": "line_1", "name": "Pollo 1/2", "quantity": 1, "station": "parrilla", "subtotal": 20000}],
            "total": 20000,
            "metadata": {"waiter": {"id": str(waiter.id), "name": waiter.full_name}} if waiter else {},
            "created_at": datetime.now(timezone.utc) - timedelta(minutes=created_minutes_ago),
            "archived_at": None,
        }
        return uuid.UUID(order_id)

    def payload(self, order_id) -> dict:
        row = self.rows.get(str(order_id))
        if not row or row["company_id"] != str(COMPANY_ID):
            raise HTTPException(status_code=404, detail="pedido_no_encontrado")
        return hospitality._payload(copy.deepcopy(row))

    def _result(self, rows=None, rowcount=0):
        rows = rows or []
        mappings = SimpleNamespace(all=lambda: rows, first=lambda: rows[0] if rows else None)
        return SimpleNamespace(mappings=lambda: mappings, rowcount=rowcount)

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        params = params or {}
        row = self.rows.get(str(params.get("order_id")))
        if row and row["company_id"] != str(params.get("company_id")):
            row = None  # never cross tenants

        status_update = re.search(r"SET status = '(\w+)'", sql)
        if status_update and "UPDATE hospitality_orders" in sql:
            if row:
                row["status"] = status_update.group(1)
            return self._result(rowcount=1 if row else 0)

        if "jsonb_set" in sql:
            if not row:
                return self._result(rowcount=0)
            kitchen = row["metadata"].setdefault("kitchen", {})
            if ":user_id" in sql and (kitchen.get("notice") or {}).get("waiter_id") != params["user_id"]:
                return self._result(rowcount=0)
            kitchen.update(json.loads(params["patch"]))
            return self._result(rowcount=1)

        if "status IN ('entregado', 'cerrado')" in sql:  # column "Listo"
            rows = [
                copy.deepcopy(r) for r in self.rows.values()
                if r["company_id"] == params["company_id"]
                and r["status"] in {"entregado", "cerrado"}
                and r["metadata"].get("kitchen", {}).get("ready_at")
                and not r["metadata"].get("kitchen", {}).get("delivered_at")
                and r["created_at"] >= params["since"]
            ]
            return self._result(sorted(rows, key=lambda r: r["created_at"]))

        if "'delivered_at' AS timestamptz" in sql:  # historial del dia
            rows = [
                copy.deepcopy(r) for r in self.rows.values()
                if r["company_id"] == params["company_id"]
                and r["metadata"].get("kitchen", {}).get("delivered_at")
                and datetime.fromisoformat(r["metadata"]["kitchen"]["delivered_at"]) >= params["since"]
            ]
            return self._result(rows)

        if "'notice'->>'waiter_id' = :user_id" in sql:  # avisos del mesero
            rows = [
                {"id": r["id"], "table_number": r["table_number"], "metadata": copy.deepcopy(r["metadata"])}
                for r in self.rows.values()
                if r["company_id"] == params["company_id"]
                and (r["metadata"].get("kitchen", {}).get("notice") or {}).get("waiter_id") == params["user_id"]
                and r["metadata"]["kitchen"].get("ready_at")
                and not r["metadata"]["kitchen"].get("waiter_seen_at")
                and r["status"] != "cancelado"
            ]
            return self._result(rows)

        raise AssertionError(f"unexpected SQL in test fake: {sql[:120]}")

    def active_orders(self):
        rows = [
            self.payload(oid) for oid, r in self.rows.items()
            if r["company_id"] == str(COMPANY_ID) and r["status"] in {"pendiente", "alistando", "entregado"}
        ]
        return {"orders": sorted(rows, key=lambda o: o["created_at"], reverse=True)}


def install_fake_orders(monkeypatch, fake=None):
    """Wire the in-memory hospitality_orders fake into hospitality and
    waiter_ordering (shared with the caja direct-sale tests)."""
    fake = fake or FakeOrdersDb()

    async def fetch_order(_db, company_id, order_id):
        assert company_id == COMPANY_ID
        return fake.payload(order_id)

    async def lock_order(_db, company_id, order_id):
        try:
            return fake.payload(order_id)
        except HTTPException:
            return None

    monkeypatch.setattr(hospitality, "_ensure_storage", AsyncMock())
    monkeypatch.setattr(hospitality, "_deduct_inventory", AsyncMock())
    monkeypatch.setattr(hospitality, "_close_table_access_if_idle", AsyncMock(return_value=False))
    monkeypatch.setattr(hospitality, "_fetch_order", fetch_order)
    monkeypatch.setattr(waiter_ordering, "_fetch_order", fetch_order)
    monkeypatch.setattr(waiter_ordering, "_lock_order_for_edit", lock_order)
    monkeypatch.setattr(
        waiter_ordering, "list_hospitality_orders",
        AsyncMock(side_effect=lambda *_a, **_k: fake.active_orders()),
    )
    monkeypatch.setattr(
        waiter_ordering, "_module_settings",
        AsyncMock(return_value={"kitchen_board_columns": True}),
    )
    return fake


@pytest.fixture
def db(monkeypatch):
    return install_fake_orders(monkeypatch)


async def _board(db, cook):
    return await waiter_ordering.waiter_ordering_kitchen_board(COMPANY_ID, db=db, user=cook)


def _ids(column):
    return [c["order_id"] for c in column]


@pytest.mark.asyncio
async def test_full_chain_nuevo_preparando_listo_entregado_without_transition_errors(db):
    mesero = _user("mesero", "Laura")
    cook = _user("cocina", "Pedro")
    order_id = db.add(waiter=mesero)

    board = await _board(db, cook)
    assert _ids(board["columns"]["nuevo"]) == [str(order_id)]
    assert board["counts"] == {"nuevo": 1, "preparando": 0, "listo": 0}

    await waiter_ordering.start_waiter_order(COMPANY_ID, order_id, db=db, _user=cook)
    assert db.rows[str(order_id)]["status"] == "alistando"
    board = await _board(db, cook)
    assert _ids(board["columns"]["preparando"]) == [str(order_id)]
    assert board["counts"] == {"nuevo": 0, "preparando": 1, "listo": 0}

    await waiter_ordering.mark_waiter_order_ready(COMPANY_ID, order_id, db=db, user=cook)
    assert db.rows[str(order_id)]["status"] == "entregado"
    board = await _board(db, cook)
    assert _ids(board["columns"]["listo"]) == [str(order_id)]
    assert board["counts"] == {"nuevo": 0, "preparando": 0, "listo": 1}

    await waiter_ordering.mark_waiter_order_delivered(COMPANY_ID, order_id, db=db, user=cook)
    board = await _board(db, cook)
    assert board["counts"] == {"nuevo": 0, "preparando": 0, "listo": 0}
    kitchen = db.rows[str(order_id)]["metadata"]["kitchen"]
    assert kitchen["delivered_by"]["name"] == "Pedro"


@pytest.mark.asyncio
async def test_comanda_lista_straight_from_pendiente_walks_through_alistando(db):
    """The production bug: COMANDA LISTA on a pendiente order raised
    "Transicion no permitida: pendiente -> entregado"."""
    cook = _user("cocina", "Pedro")
    order_id = db.add(waiter=_user("mesero", "Laura"))

    result = await waiter_ordering.mark_waiter_order_ready(COMPANY_ID, order_id, db=db, user=cook)

    assert result["order"]["status"] == "entregado"
    assert db.rows[str(order_id)]["metadata"]["kitchen"]["ready_at"]


@pytest.mark.asyncio
async def test_comanda_lista_twice_is_idempotent_and_notifies_once(db):
    cook = _user("cocina", "Pedro")
    order_id = db.add(waiter=_user("mesero", "Laura"))
    await waiter_ordering.mark_waiter_order_ready(COMPANY_ID, order_id, db=db, user=cook)
    first_ready_at = db.rows[str(order_id)]["metadata"]["kitchen"]["ready_at"]

    await waiter_ordering.mark_waiter_order_ready(COMPANY_ID, order_id, db=db, user=cook)

    assert db.rows[str(order_id)]["status"] == "entregado"
    assert db.rows[str(order_id)]["metadata"]["kitchen"]["ready_at"] == first_ready_at


@pytest.mark.asyncio
async def test_the_mesero_who_took_the_order_gets_mesa_x_lista_para_llevar(db):
    laura = _user("mesero", "Laura")
    other_waiter = _user("mesero", "Juan")
    cook = _user("cocina", "Pedro")
    order_id = db.add(table="Mesa 7", waiter=laura)
    db.add(table="Mesa 2", waiter=other_waiter)

    before = await waiter_ordering.waiter_ready_notices(COMPANY_ID, db=db, user=laura)
    assert before["avisos"] == []

    await waiter_ordering.start_waiter_order(COMPANY_ID, order_id, db=db, _user=cook)
    await waiter_ordering.mark_waiter_order_ready(COMPANY_ID, order_id, db=db, user=cook)

    avisos = (await waiter_ordering.waiter_ready_notices(COMPANY_ID, db=db, user=laura))["avisos"]
    assert [a["message"] for a in avisos] == ["Mesa 7 lista para llevar"]
    assert avisos[0]["order_id"] == str(order_id)
    # Only the mesero who took it -- never another waiter.
    assert (await waiter_ordering.waiter_ready_notices(COMPANY_ID, db=db, user=other_waiter))["avisos"] == []

    await waiter_ordering.dismiss_waiter_ready_notice(COMPANY_ID, order_id, db=db, user=laura)
    assert (await waiter_ordering.waiter_ready_notices(COMPANY_ID, db=db, user=laura))["avisos"] == []


@pytest.mark.asyncio
async def test_another_waiter_cannot_dismiss_someone_elses_notice(db):
    laura = _user("mesero", "Laura")
    order_id = db.add(waiter=laura)
    await waiter_ordering.mark_waiter_order_ready(COMPANY_ID, order_id, db=db, user=_user("cocina", "Pedro"))

    with pytest.raises(HTTPException) as exc:
        await waiter_ordering.dismiss_waiter_ready_notice(COMPANY_ID, order_id, db=db, user=_user("mesero", "Juan"))
    assert exc.value.status_code == 404
    assert len((await waiter_ordering.waiter_ready_notices(COMPANY_ID, db=db, user=laura))["avisos"]) == 1


def test_ready_message_does_not_double_the_word_mesa():
    assert waiter_ordering._table_ready_message("Mesa 3") == "Mesa 3 lista para llevar"
    assert waiter_ordering._table_ready_message("3") == "Mesa 3 lista para llevar"


@pytest.mark.asyncio
async def test_delivered_comanda_leaves_the_board_but_the_caja_can_still_charge_it(db):
    cook = _user("cocina", "Pedro")
    order_id = db.add(waiter=_user("mesero", "Laura"))
    await waiter_ordering.start_waiter_order(COMPANY_ID, order_id, db=db, _user=cook)
    await waiter_ordering.mark_waiter_order_ready(COMPANY_ID, order_id, db=db, user=cook)
    await waiter_ordering.mark_waiter_order_delivered(COMPANY_ID, order_id, db=db, user=cook)

    # Entregar NO cierra ni cobra: sigue abierta para la caja.
    assert db.rows[str(order_id)]["status"] == "entregado"
    assert str(order_id) not in _ids((await _board(db, cook))["comandas"])

    closed = await hospitality.close_hospitality_order(
        COMPANY_ID, order_id, hospitality.HospitalityCloseIn(payment_method="efectivo"), db=db,
    )
    assert closed["order"]["status"] == "cerrado"


@pytest.mark.asyncio
async def test_delivered_comandas_are_kept_in_the_day_history(db):
    cook = _user("cocina", "Pedro")
    order_id = db.add(table="Mesa 9", waiter=_user("mesero", "Laura"))
    await waiter_ordering.mark_waiter_order_ready(COMPANY_ID, order_id, db=db, user=cook)
    await waiter_ordering.mark_waiter_order_delivered(COMPANY_ID, order_id, db=db, user=cook)

    history = await waiter_ordering.waiter_ordering_kitchen_delivered_today(COMPANY_ID, db=db, user=cook)

    assert [(c["order_id"], c["table_number"]) for c in history["comandas"]] == [(str(order_id), "Mesa 9")]
    assert history["comandas"][0]["delivered_at"]


@pytest.mark.asyncio
async def test_charged_before_delivered_stays_in_listo_until_the_kitchen_delivers(db):
    cook = _user("cocina", "Pedro")
    order_id = db.add(waiter=_user("mesero", "Laura"))
    await waiter_ordering.mark_waiter_order_ready(COMPANY_ID, order_id, db=db, user=cook)
    await hospitality.close_hospitality_order(
        COMPANY_ID, order_id, hospitality.HospitalityCloseIn(payment_method="efectivo"), db=db,
    )

    assert _ids((await _board(db, cook))["columns"]["listo"]) == [str(order_id)]
    await waiter_ordering.mark_waiter_order_delivered(COMPANY_ID, order_id, db=db, user=cook)
    assert (await _board(db, cook))["columns"]["listo"] == []
    assert db.rows[str(order_id)]["status"] == "cerrado"


@pytest.mark.asyncio
async def test_cannot_deliver_a_comanda_that_is_not_ready_yet(db):
    cook = _user("cocina", "Pedro")
    order_id = db.add(waiter=_user("mesero", "Laura"))
    await waiter_ordering.start_waiter_order(COMPANY_ID, order_id, db=db, _user=cook)

    with pytest.raises(HTTPException) as exc:
        await waiter_ordering.mark_waiter_order_delivered(COMPANY_ID, order_id, db=db, user=cook)
    assert exc.value.status_code == 409
    assert db.rows[str(order_id)]["status"] == "alistando"


@pytest.mark.asyncio
async def test_each_column_lists_the_oldest_comanda_first(db):
    cook = _user("cocina", "Pedro")
    mesero = _user("mesero", "Laura")
    newer = db.add(table="Mesa 1", waiter=mesero, created_minutes_ago=2)
    older = db.add(table="Mesa 2", waiter=mesero, created_minutes_ago=30)
    middle = db.add(table="Mesa 3", waiter=mesero, created_minutes_ago=10)

    board = await _board(db, cook)
    assert _ids(board["columns"]["nuevo"]) == [str(older), str(middle), str(newer)]

    for order_id in (newer, older):
        await waiter_ordering.start_waiter_order(COMPANY_ID, order_id, db=db, _user=cook)
    board = await _board(db, cook)
    assert _ids(board["columns"]["preparando"]) == [str(older), str(newer)]
    assert _ids(board["columns"]["nuevo"]) == [str(middle)]


@pytest.mark.asyncio
async def test_start_on_an_order_already_past_nuevo_is_a_conflict(db):
    cook = _user("cocina", "Pedro")
    order_id = db.add(waiter=_user("mesero", "Laura"))
    await waiter_ordering.mark_waiter_order_ready(COMPANY_ID, order_id, db=db, user=cook)

    with pytest.raises(HTTPException) as exc:
        await waiter_ordering.start_waiter_order(COMPANY_ID, order_id, db=db, _user=cook)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_new_kitchen_endpoints_are_off_for_a_company_without_the_switch(db, monkeypatch):
    monkeypatch.setattr(waiter_ordering, "_module_settings", AsyncMock(return_value={}))
    cook = _user("cocina", "Pedro")
    mesero = _user("mesero", "Laura")
    order_id = db.add(waiter=mesero)

    board = await _board(db, cook)
    assert board["columns_enabled"] is False
    assert "columns" not in board

    for call in (
        waiter_ordering.start_waiter_order(COMPANY_ID, order_id, db=db, _user=cook),
        waiter_ordering.mark_waiter_order_delivered(COMPANY_ID, order_id, db=db, user=cook),
        waiter_ordering.waiter_ordering_kitchen_delivered_today(COMPANY_ID, db=db, user=cook),
        waiter_ordering.dismiss_waiter_ready_notice(COMPANY_ID, order_id, db=db, user=mesero),
    ):
        with pytest.raises(HTTPException) as exc:
            await call
        assert exc.value.status_code == 404
    assert (await waiter_ordering.waiter_ready_notices(COMPANY_ID, db=db, user=mesero))["avisos"] == []
    assert db.rows[str(order_id)]["status"] == "pendiente"


@pytest.mark.asyncio
async def test_the_ready_fix_also_works_with_the_switch_off(db, monkeypatch):
    """The transition bug fix is not behind the switch."""
    monkeypatch.setattr(waiter_ordering, "_module_settings", AsyncMock(return_value={}))
    order_id = db.add(waiter=_user("mesero", "Laura"))

    result = await waiter_ordering.mark_waiter_order_ready(COMPANY_ID, order_id, db=db, user=_user("cocina", "Pedro"))

    assert result["order"]["status"] == "entregado"


def test_every_new_endpoint_requires_a_server_side_session():
    """No new route may be reachable without the cocina/mesero dependency."""
    from fastapi.params import Depends as DependsParam
    import inspect

    expected = {
        waiter_ordering.start_waiter_order: waiter_ordering._require_cocina,
        waiter_ordering.mark_waiter_order_ready: waiter_ordering._require_cocina,
        waiter_ordering.mark_waiter_order_delivered: waiter_ordering._require_cocina,
        waiter_ordering.waiter_ordering_kitchen_delivered_today: waiter_ordering._require_cocina,
        waiter_ordering.waiter_ready_notices: waiter_ordering._require_mesero,
        waiter_ordering.dismiss_waiter_ready_notice: waiter_ordering._require_mesero,
    }
    for endpoint, dependency in expected.items():
        deps = [
            p.default.dependency for p in inspect.signature(endpoint).parameters.values()
            if isinstance(p.default, DependsParam)
        ]
        assert dependency in deps, endpoint.__name__
