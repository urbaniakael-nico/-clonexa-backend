import io
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from openpyxl import Workbook

from app.api.v1.endpoints.transport_calls import _csv_rows, _uploaded_call_rows
from app.api.v1.endpoints.transport_telephony import _normalize_phone, _optional_uuid, _phone_type, _settings


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


def test_company_with_empty_numbers_uses_railway_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWILIO_OUTGOING_NUMBERS", "+16184378317")
    company = SimpleNamespace(settings_json={"transport_telephony": {"outgoing_numbers": []}})
    assert _settings(company)["outgoing_numbers"] == ["+16184378317"]


def test_excel_semicolon_csv_is_supported() -> None:
    rows = _csv_rows("cliente;telefono;contrato\nCliente Demo;+573001112233;TEST-001\n")
    assert rows == [{"cliente": "Cliente Demo", "telefono": "+573001112233", "contrato": "TEST-001"}]


def test_xlsx_call_base_is_supported() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["cliente", "telefono", "contrato"])
    sheet.append(["Cliente Excel", "+573001112233", "TEST-XLSX"])
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()

    rows = _uploaded_call_rows(output.getvalue(), "base_llamadas.xlsx")

    assert rows == [{"cliente": "Cliente Excel", "telefono": "+573001112233", "contrato": "TEST-XLSX"}]


def test_invalid_call_base_returns_controlled_validation_error() -> None:
    with pytest.raises(ValueError, match="Formato no compatible"):
        _uploaded_call_rows(b"not a spreadsheet", "base_llamadas.pdf")


def test_call_base_requires_at_least_one_phone() -> None:
    with pytest.raises(ValueError, match="columna telefono"):
        _uploaded_call_rows(b"cliente,contrato\nCliente Demo,TEST-001\n", "base_llamadas.csv")
