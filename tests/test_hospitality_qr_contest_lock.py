from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest

from app.api.v1.endpoints import hospitality


class MappingResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


def future(hours=2):
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def past(hours=2):
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def test_persistent_table_access_remains_active_after_legacy_expiration():
    payload = hospitality._table_access_payload(
        {
            "status": "active",
            "table_key": "mesa 4",
            "table_number": "Mesa 4",
            "access_code": "ABCDE",
            "activated_at": past(24),
            "expires_at": past(12),
            "closes_with_table": True,
        },
        include_code=True,
    )

    assert payload["active"] is True
    assert payload["access_code"] == "ABCDE"
    assert payload["expires_at"] == ""
    assert payload["closes_with_table"] is True


@pytest.mark.asyncio
async def test_activating_an_active_table_reuses_the_same_key(monkeypatch):
    company_id = uuid.uuid4()
    existing = {
        "status": "active",
        "table_key": "mesa 4",
        "table_number": "Mesa 4",
        "access_code": "ABCDE",
        "activated_at": past(1),
        "expires_at": past(1),
        "closes_with_table": True,
    }
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
    monkeypatch.setattr(hospitality, "_ensure_storage", AsyncMock())
    monkeypatch.setattr(hospitality, "_company_exists", AsyncMock(return_value=True))
    monkeypatch.setattr(hospitality, "_fetch_active_table_access", AsyncMock(return_value=existing))

    response = await hospitality.activate_hospitality_table_access(
        company_id,
        hospitality.HospitalityTableAccessIn(table="Mesa 4"),
        db,
    )

    assert response["reused"] is True
    assert response["access"]["access_code"] == "ABCDE"
    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_table_access_stays_open_while_the_table_has_active_orders():
    db = SimpleNamespace(execute=AsyncMock(return_value=ScalarResult(1)))

    await hospitality._close_table_access_if_idle(db, uuid.uuid4(), "Mesa 4")

    assert db.execute.await_count == 1


@pytest.mark.asyncio
async def test_table_access_closes_after_the_last_order_is_closed():
    db = SimpleNamespace(execute=AsyncMock(side_effect=[ScalarResult(0), SimpleNamespace()]))

    await hospitality._close_table_access_if_idle(db, uuid.uuid4(), "Mesa 4")

    assert db.execute.await_count == 2
    statement = str(db.execute.await_args_list[1].args[0])
    assert "SET status = 'closed'" in statement


def campaign_row(company_id, campaign_id, campaign_type):
    return {
        "id": campaign_id,
        "company_id": company_id,
        "campaign_type": campaign_type,
        "status": "active",
        "starts_at": past(1),
        "registration_ends_at": future(1),
        "ends_at": future(2),
        "vote_mode": "yes_no",
        "options": [{"key": "yes", "label": "Si"}, {"key": "no", "label": "No"}],
    }


def assert_immutable_insert(db):
    statement = str(db.execute.await_args_list[1].args[0])
    assert "ON CONFLICT (campaign_id, table_key)" in statement
    assert "DO NOTHING" in statement
    assert "DO UPDATE" not in statement


@pytest.mark.asyncio
async def test_consumption_contest_registration_cannot_be_modified(monkeypatch):
    company_id = uuid.uuid4()
    campaign_id = uuid.uuid4()
    row = campaign_row(company_id, campaign_id, "consumption")
    db = SimpleNamespace(execute=AsyncMock(side_effect=[MappingResult(row), SimpleNamespace()]), commit=AsyncMock())
    monkeypatch.setattr(hospitality, "_ensure_storage", AsyncMock())
    monkeypatch.setattr(hospitality, "_loyalty_response", AsyncMock(return_value={"ok": True}))

    await hospitality.join_loyalty_campaign(
        company_id,
        campaign_id,
        hospitality.HospitalityLoyaltyParticipantIn(table="Mesa 4", team_name="Equipo original", accepted=True),
        db,
    )

    assert_immutable_insert(db)


@pytest.mark.asyncio
async def test_score_prediction_cannot_be_modified(monkeypatch):
    company_id = uuid.uuid4()
    campaign_id = uuid.uuid4()
    row = campaign_row(company_id, campaign_id, "score_pool")
    db = SimpleNamespace(execute=AsyncMock(side_effect=[MappingResult(row), SimpleNamespace()]), commit=AsyncMock())
    monkeypatch.setattr(hospitality, "_ensure_storage", AsyncMock())
    monkeypatch.setattr(hospitality, "_require_table_access", AsyncMock())
    monkeypatch.setattr(hospitality, "_active_loyalty_campaign", AsyncMock(return_value=None))
    monkeypatch.setattr(hospitality, "_loyalty_response", AsyncMock(return_value={"ok": True}))

    await hospitality.submit_loyalty_score_prediction(
        company_id,
        campaign_id,
        hospitality.HospitalityScorePredictionIn(
            table="Mesa 4", team_name="Equipo original", score_a=2, score_b=1, access_code="ABCDE"
        ),
        db,
    )

    assert_immutable_insert(db)


@pytest.mark.asyncio
async def test_vote_response_cannot_be_modified(monkeypatch):
    company_id = uuid.uuid4()
    campaign_id = uuid.uuid4()
    row = campaign_row(company_id, campaign_id, "vote_poll")
    db = SimpleNamespace(execute=AsyncMock(side_effect=[MappingResult(row), SimpleNamespace()]), commit=AsyncMock())
    monkeypatch.setattr(hospitality, "_ensure_storage", AsyncMock())
    monkeypatch.setattr(hospitality, "_require_table_access", AsyncMock())
    monkeypatch.setattr(hospitality, "_active_loyalty_campaign", AsyncMock(return_value=None))
    monkeypatch.setattr(hospitality, "_loyalty_response", AsyncMock(return_value={"ok": True}))

    await hospitality.submit_loyalty_vote_poll(
        company_id,
        campaign_id,
        hospitality.HospitalityVoteSubmissionIn(
            table="Mesa 4", voter_name="Cliente original", answer_key="yes", access_code="ABCDE"
        ),
        db,
    )

    assert_immutable_insert(db)
