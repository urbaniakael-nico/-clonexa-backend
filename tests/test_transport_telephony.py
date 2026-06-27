import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.transport_telephony import _normalize_phone, _optional_uuid, _phone_type


def test_normalizes_colombian_numbers() -> None:
    assert _normalize_phone("321 555 0199") == "+573215550199"
    assert _normalize_phone("+57 601 357 2779") == "+576013572779"


def test_classifies_colombian_mobile_and_landline() -> None:
    assert _phone_type("+573215550199") == "mobile"
    assert _phone_type("+576013572779") == "landline"


def test_rejects_incomplete_numbers() -> None:
    assert _normalize_phone("555-01") == ""
    assert _phone_type("") == "unknown"


def test_rejects_invalid_optional_uuid_as_bad_request() -> None:
    with pytest.raises(HTTPException) as error:
        _optional_uuid("not-a-row-id", "batch_row_id_invalid")
    assert error.value.status_code == 400
    assert error.value.detail == "batch_row_id_invalid"
