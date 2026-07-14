from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import hospitality


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("cash", "cash"),
        ("Efectivo", "cash"),
        ("transfer", "transfer"),
        ("Transferencia", "transfer"),
        ("card", "card"),
        ("Tarjeta", "card"),
    ],
)
def test_closing_payment_method_accepts_recordable_methods(value, expected):
    assert hospitality._closing_payment_method(value) == expected


@pytest.mark.parametrize("value", [None, "", "other", "Otro", "bitcoin"])
def test_closing_payment_method_is_required_and_rejects_other(value):
    with pytest.raises(HTTPException) as error:
        hospitality._closing_payment_method(value)

    assert error.value.status_code == 422
    assert "efectivo" in str(error.value.detail).lower()


@pytest.mark.asyncio
async def test_close_table_endpoint_rejects_missing_payment(monkeypatch):
    company_id = uuid.uuid4()
    order_id = uuid.uuid4()
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
    monkeypatch.setattr(hospitality, "_ensure_storage", AsyncMock())
    monkeypatch.setattr(
        hospitality,
        "_fetch_order",
        AsyncMock(return_value={"id": str(order_id), "status": "entregado", "table_key": "mesa 6"}),
    )

    with pytest.raises(HTTPException) as error:
        await hospitality.close_hospitality_order(company_id, order_id, None, db)

    assert error.value.status_code == 422
    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_close_table_endpoint_persists_selected_payment(monkeypatch):
    company_id = uuid.uuid4()
    order_id = uuid.uuid4()
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
    saved = {
        "id": str(order_id),
        "status": "cerrado",
        "table_key": "mesa 6",
        "payment_method": "transfer",
    }
    monkeypatch.setattr(hospitality, "_ensure_storage", AsyncMock())
    monkeypatch.setattr(
        hospitality,
        "_fetch_order",
        AsyncMock(side_effect=[{"id": str(order_id), "status": "entregado", "table_key": "mesa 6"}, saved]),
    )
    monkeypatch.setattr(hospitality, "_close_table_access_if_idle", AsyncMock())

    response = await hospitality.close_hospitality_order(
        company_id,
        order_id,
        hospitality.HospitalityCloseIn(payment_method="Transferencia"),
        db,
    )

    assert response["order"]["payment_method"] == "transfer"
    assert db.execute.await_args.args[1]["payment_method"] == "transfer"
    db.commit.assert_awaited_once()
