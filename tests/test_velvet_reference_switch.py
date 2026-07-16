from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints import company_bots_v1


def switch_update(reference_id: str = "ref-b") -> dict:
    return {
        "update_id": 778899,
        "callback_query": {
            "id": "callback-1",
            "from": {"id": 12345, "username": "operator"},
            "message": {"chat": {"id": 12345}},
            "data": f"velvet:switch_ref:{reference_id}",
        },
    }


@pytest.mark.asyncio
async def test_reference_switch_creates_visible_workforce_event(monkeypatch):
    db = SimpleNamespace(commit=AsyncMock())
    employee = {
        "employee_id": "employee-1",
        "employee_name": "Operaria",
        "employee_role": "Operador",
    }
    previous = {
        "id": "session-a",
        "reference_id": "ref-a",
        "reference_name": "Referencia A",
    }
    new_reference = {
        "id": "ref-b",
        "name": "Referencia B",
        "size": "SM",
    }

    monkeypatch.setattr(company_bots_v1, "answer_callback", AsyncMock())
    monkeypatch.setattr(company_bots_v1, "employee_by_telegram", AsyncMock(return_value=employee))
    monkeypatch.setattr(company_bots_v1, "get_pending_total", AsyncMock(return_value=None))
    monkeypatch.setattr(company_bots_v1, "reference_by_id", AsyncMock(return_value=new_reference))
    monkeypatch.setattr(company_bots_v1, "active_reference_session", AsyncMock(return_value=previous))
    open_session = AsyncMock()
    insert_event = AsyncMock()
    send_message = AsyncMock()
    monkeypatch.setattr(company_bots_v1, "open_reference_session", open_session)
    monkeypatch.setattr(company_bots_v1, "insert_attendance_event", insert_event)
    monkeypatch.setattr(company_bots_v1, "workforce_status", AsyncMock(return_value="working"))
    monkeypatch.setattr(company_bots_v1, "send_message", send_message)

    response = await company_bots_v1.handle_velvet_references(
        db=db,
        token="token",
        company_id="company-1",
        update=switch_update(),
    )

    assert response["handled"] == "reference_switched"
    open_session.assert_awaited_once()
    insert_event.assert_awaited_once()
    event = insert_event.await_args.kwargs
    assert event["event_type"] == "reference_switch"
    assert event["event_label"] == "Cambio de referencia"
    assert event["status_after"] == "working"
    assert event["detail"] == "Cambio de referencia: Referencia A → Referencia B"
    assert event["metadata"]["reference_id"] == "ref-b"
    assert event["metadata"]["reference_name"] == "Referencia B"
    assert event["metadata"]["previous_reference_id"] == "ref-a"
    assert event["metadata"]["previous_reference_name"] == "Referencia A"
    assert event["metadata"]["previous_reference_session_id"] == "session-a"
    assert event["metadata"]["telegram_update_id"] == "778899"
    assert event["source_ref"] == "company_bot_v1:reference_switch:778899"
    db.commit.assert_awaited_once()
    assert "Referencia B" in send_message.await_args.args[2]


@pytest.mark.asyncio
async def test_reference_switch_to_same_active_reference_is_noop(monkeypatch):
    db = SimpleNamespace(commit=AsyncMock())
    employee = {
        "employee_id": "employee-1",
        "employee_name": "Operaria",
        "employee_role": "Operador",
    }
    current = {
        "id": "session-a",
        "reference_id": "ref-a",
        "reference_name": "Referencia A",
    }
    reference = {
        "id": "ref-a",
        "name": "Referencia A",
        "size": "SM",
    }

    monkeypatch.setattr(company_bots_v1, "answer_callback", AsyncMock())
    monkeypatch.setattr(company_bots_v1, "employee_by_telegram", AsyncMock(return_value=employee))
    monkeypatch.setattr(company_bots_v1, "get_pending_total", AsyncMock(return_value=None))
    monkeypatch.setattr(company_bots_v1, "reference_by_id", AsyncMock(return_value=reference))
    monkeypatch.setattr(company_bots_v1, "active_reference_session", AsyncMock(return_value=current))
    monkeypatch.setattr(company_bots_v1, "workforce_status", AsyncMock(return_value="working"))
    open_session = AsyncMock()
    insert_event = AsyncMock()
    send_message = AsyncMock()
    monkeypatch.setattr(company_bots_v1, "open_reference_session", open_session)
    monkeypatch.setattr(company_bots_v1, "insert_attendance_event", insert_event)
    monkeypatch.setattr(company_bots_v1, "send_message", send_message)

    response = await company_bots_v1.handle_velvet_references(
        db=db,
        token="token",
        company_id="company-1",
        update=switch_update("ref-a"),
    )

    assert response["handled"] == "reference_unchanged"
    open_session.assert_not_awaited()
    insert_event.assert_not_awaited()
    db.commit.assert_not_awaited()
    assert "Ya estás trabajando" in send_message.await_args.args[2]
