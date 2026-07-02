from __future__ import annotations

import asyncio
import os
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from twilio.base.exceptions import TwilioRestException
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from twilio.request_validator import RequestValidator
from twilio.rest import Client
from twilio.twiml.voice_response import Dial, VoiceResponse

from app.api.deps import WRITE_ROLES, get_db, require_company_user_for_tenant, require_enabled_module
from app.api.v1.endpoints.transport_calls import ensure_transport_calls_storage
from app.models.auth import CompanyUser
from app.models.core import Company
from app.web.admin_v2_routes import _active_session as active_admin_v2_session
from app.web.admin_v2_routes import _active_company_preview as active_admin_company_preview

router = APIRouter()

TELEPHONY_MANAGER_ROLES = {
    "company_admin", "admin_empresa", "manager", "gerencia", "gerente", "management", "supervisor",
}
BLOCKED_CONSENT_STATUSES = {"denied", "revoked"}
ALLOWED_CONSENT_STATUSES = {"unknown", "granted", "denied", "revoked"}


class TelephonyConfigurationIn(BaseModel):
    outgoing_numbers: list[str] = Field(default_factory=list, max_length=10)
    default_campaign: str | None = Field(default="General", max_length=120)
    strict_consent: bool = True
    auto_whatsapp_documents: bool = False


class TelephonyConsentIn(BaseModel):
    consent_status: str = Field(default="unknown", max_length=30)
    do_not_call: bool = False
    source: str | None = Field(default="crm", max_length=60)
    notes: str | None = Field(default="", max_length=600)


class TelephonyPreflightIn(BaseModel):
    phone: str = Field(..., max_length=80)
    batch_row_id: str | None = Field(default="", max_length=80)
    campaign_code: str | None = Field(default="", max_length=120)


def _clean(value: Any, limit: int = 255) -> str:
    return str(value or "").strip()[:limit]


def _normalize_phone(value: Any) -> str:
    raw = _clean(value, 80)
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("57") and len(digits) >= 12:
        return f"+{digits}"
    if len(digits) == 10:
        return f"+57{digits}"
    if raw.startswith("+") and 8 <= len(digits) <= 15:
        return f"+{digits}"
    return ""


def _phone_type(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    national = digits[2:] if digits.startswith("57") else digits
    if len(national) == 10 and national.startswith("3"):
        return "mobile"
    if len(national) == 10 and national.startswith("60"):
        return "landline"
    return "unknown"


def _settings(company: Company) -> dict[str, Any]:
    store = dict(company.settings_json or {})
    raw = store.get("transport_telephony") if isinstance(store.get("transport_telephony"), dict) else {}
    env_numbers = [number for number in (_normalize_phone(item) for item in os.getenv("TWILIO_OUTGOING_NUMBERS", "").split(",")) if number]
    stored_numbers = raw.get("outgoing_numbers") if isinstance(raw.get("outgoing_numbers"), list) else []
    numbers = stored_numbers or env_numbers
    return {
        "outgoing_numbers": list(dict.fromkeys(filter(None, (_normalize_phone(item) for item in numbers))))[:10],
        "default_campaign": _clean(raw.get("default_campaign") or "General", 120),
        "strict_consent": bool(raw.get("strict_consent", True)),
        "auto_whatsapp_documents": bool(raw.get("auto_whatsapp_documents", False)),
    }


def _twilio_runtime() -> dict[str, str]:
    return {
        "account_sid": _clean(os.getenv("TWILIO_ACCOUNT_SID"), 80),
        "auth_token": _clean(os.getenv("TWILIO_AUTH_TOKEN"), 160),
        "api_key_sid": _clean(os.getenv("TWILIO_API_KEY_SID"), 80),
        "api_key_secret": _clean(os.getenv("TWILIO_API_KEY_SECRET"), 160),
        "twiml_app_sid": _clean(os.getenv("TWILIO_TWIML_APP_SID"), 80),
    }


def _runtime_ready(runtime: dict[str, str]) -> bool:
    return all(runtime.get(key) for key in ("account_sid", "auth_token", "api_key_sid", "api_key_secret", "twiml_app_sid"))


def _public_base(request: Request) -> str:
    configured = _clean(os.getenv("CLONEXA_PUBLIC_BASE_URL") or os.getenv("PUBLIC_BASE_URL"), 500).rstrip("/")
    return configured or str(request.base_url).rstrip("/")


def _identity(user: CompanyUser) -> str:
    return f"clx_{str(user.id).replace('-', '')}"


def _identity_user_id(value: Any) -> str:
    raw = _clean(value, 180)
    if raw.startswith("client:"):
        raw = raw.split(":", 1)[1]
    if not raw.startswith("clx_"):
        return ""
    compact = raw[4:]
    if not re.fullmatch(r"[0-9a-fA-F]{32}", compact):
        return ""
    return str(uuid.UUID(compact))


def _optional_uuid(value: Any, detail: str = "id_invalid") -> str:
    raw = _clean(value, 80)
    if not raw:
        return ""
    try:
        return str(uuid.UUID(raw))
    except (TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(status_code=400, detail=detail) from exc


async def _company(db: AsyncSession, company_id: uuid.UUID) -> Company:
    company = (await db.execute(select(Company).where(Company.id == company_id))).scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="company_not_found")
    return company


async def _telephony_user(
    company_id: uuid.UUID,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> CompanyUser:
    return await require_company_user_for_tenant(
        db,
        authorization,
        company_id,
        allowed_roles=WRITE_ROLES,
        module_codes="transport_calls",
    )


async def _telephony_manager(
    company_id: uuid.UUID,
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> CompanyUser | None:
    if await active_admin_v2_session(request, db) or active_admin_company_preview(request, company_id):
        await require_enabled_module(db, company_id, "transport_calls")
        return None
    return await require_company_user_for_tenant(
        db,
        authorization,
        company_id,
        allowed_roles=TELEPHONY_MANAGER_ROLES,
        module_codes="transport_calls",
    )


async def ensure_transport_telephony_storage(db: AsyncSession) -> None:
    await ensure_transport_calls_storage(db)
    for statement in [
        "ALTER TABLE transport_call_logs ADD COLUMN IF NOT EXISTS twilio_parent_call_sid VARCHAR(120) NOT NULL DEFAULT ''",
        "ALTER TABLE transport_call_logs ADD COLUMN IF NOT EXISTS campaign_code VARCHAR(120) NOT NULL DEFAULT ''",
        "ALTER TABLE transport_call_logs ADD COLUMN IF NOT EXISTS caller_number VARCHAR(80) NOT NULL DEFAULT ''",
        "ALTER TABLE transport_call_logs ADD COLUMN IF NOT EXISTS phone_type VARCHAR(30) NOT NULL DEFAULT 'unknown'",
        "ALTER TABLE transport_call_logs ADD COLUMN IF NOT EXISTS price_amount NUMERIC(14,6) NOT NULL DEFAULT 0",
        "ALTER TABLE transport_call_logs ADD COLUMN IF NOT EXISTS price_currency VARCHAR(12) NOT NULL DEFAULT 'USD'",
        "ALTER TABLE transport_call_logs ADD COLUMN IF NOT EXISTS consent_status VARCHAR(30) NOT NULL DEFAULT 'unknown'",
        "ALTER TABLE transport_call_logs ADD COLUMN IF NOT EXISTS do_not_call BOOLEAN NOT NULL DEFAULT false",
        "ALTER TABLE transport_call_batches ADD COLUMN IF NOT EXISTS campaign_code VARCHAR(120) NOT NULL DEFAULT ''",
        "ALTER TABLE transport_call_batch_rows ADD COLUMN IF NOT EXISTS campaign_code VARCHAR(120) NOT NULL DEFAULT ''",
        "ALTER TABLE transport_call_batch_rows ADD COLUMN IF NOT EXISTS phone_type VARCHAR(30) NOT NULL DEFAULT 'unknown'",
        "ALTER TABLE transport_call_batch_rows ADD COLUMN IF NOT EXISTS consent_status VARCHAR(30) NOT NULL DEFAULT 'unknown'",
        "ALTER TABLE transport_call_batch_rows ADD COLUMN IF NOT EXISTS do_not_call BOOLEAN NOT NULL DEFAULT false",
        "CREATE INDEX IF NOT EXISTS ix_transport_call_logs_campaign ON transport_call_logs(company_id, campaign_code, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_transport_call_logs_parent_sid ON transport_call_logs(company_id, twilio_parent_call_sid)",
    ]:
        await db.execute(text(statement))
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS transport_telephony_numbers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL,
            phone_number VARCHAR(80) NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT true,
            last_used_at TIMESTAMPTZ NULL,
            call_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(company_id, phone_number)
        )
    """))
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS transport_call_consents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL,
            phone VARCHAR(80) NOT NULL,
            phone_type VARCHAR(30) NOT NULL DEFAULT 'unknown',
            consent_status VARCHAR(30) NOT NULL DEFAULT 'unknown',
            do_not_call BOOLEAN NOT NULL DEFAULT false,
            source VARCHAR(60) NOT NULL DEFAULT 'crm',
            notes TEXT NOT NULL DEFAULT '',
            updated_by VARCHAR(180) NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(company_id, phone)
        )
    """))


async def _sync_numbers(db: AsyncSession, company_id: uuid.UUID, numbers: list[str]) -> None:
    for number in numbers:
        await db.execute(text("""
            INSERT INTO transport_telephony_numbers(company_id, phone_number, enabled)
            VALUES (CAST(:company_id AS uuid), :phone, true)
            ON CONFLICT(company_id, phone_number)
            DO UPDATE SET enabled = true, updated_at = now()
        """), {"company_id": str(company_id), "phone": number})
    await db.execute(text("""
        UPDATE transport_telephony_numbers
        SET enabled = false, updated_at = now()
        WHERE company_id = CAST(:company_id AS uuid)
          AND NOT (phone_number = ANY(CAST(:numbers AS text[])))
    """), {"company_id": str(company_id), "numbers": numbers})


async def _next_number(db: AsyncSession, company_id: uuid.UUID, numbers: list[str]) -> str:
    await _sync_numbers(db, company_id, numbers)
    result = await db.execute(text("""
        SELECT id, phone_number
        FROM transport_telephony_numbers
        WHERE company_id = CAST(:company_id AS uuid)
          AND enabled IS TRUE
        ORDER BY last_used_at NULLS FIRST, call_count ASC, phone_number ASC
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    """), {"company_id": str(company_id)})
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=503, detail="No hay numeros de salida habilitados.")
    await db.execute(text("""
        UPDATE transport_telephony_numbers
        SET last_used_at = now(), call_count = call_count + 1, updated_at = now()
        WHERE id = CAST(:id AS uuid)
    """), {"id": str(row["id"])})
    return str(row["phone_number"])


async def _consent(db: AsyncSession, company_id: uuid.UUID, phone: str) -> dict[str, Any]:
    result = await db.execute(text("""
        SELECT * FROM transport_call_consents
        WHERE company_id = CAST(:company_id AS uuid) AND phone = :phone
        LIMIT 1
    """), {"company_id": str(company_id), "phone": phone})
    row = result.mappings().first()
    if not row:
        return {"phone": phone, "phone_type": _phone_type(phone), "consent_status": "unknown", "do_not_call": False}
    data = dict(row)
    for key, value in list(data.items()):
        if isinstance(value, (datetime, uuid.UUID, Decimal)):
            data[key] = str(value)
    return data


async def _save_consent(
    db: AsyncSession,
    company_id: uuid.UUID,
    phone: str,
    payload: TelephonyConsentIn,
    updated_by: str,
) -> dict[str, Any]:
    consent_status = _clean(payload.consent_status, 30).lower()
    if consent_status not in ALLOWED_CONSENT_STATUSES:
        raise HTTPException(status_code=400, detail="consent_status_invalid")
    await db.execute(text("""
        INSERT INTO transport_call_consents(
            company_id, phone, phone_type, consent_status, do_not_call, source, notes, updated_by
        ) VALUES (
            CAST(:company_id AS uuid), :phone, :phone_type, :consent_status, :do_not_call, :source, :notes, :updated_by
        )
        ON CONFLICT(company_id, phone)
        DO UPDATE SET phone_type = EXCLUDED.phone_type,
                      consent_status = EXCLUDED.consent_status,
                      do_not_call = EXCLUDED.do_not_call,
                      source = EXCLUDED.source,
                      notes = EXCLUDED.notes,
                      updated_by = EXCLUDED.updated_by,
                      updated_at = now()
    """), {
        "company_id": str(company_id),
        "phone": phone,
        "phone_type": _phone_type(phone),
        "consent_status": consent_status,
        "do_not_call": bool(payload.do_not_call),
        "source": _clean(payload.source or "crm", 60),
        "notes": _clean(payload.notes, 600),
        "updated_by": _clean(updated_by, 180),
    })
    await db.execute(text("""
        UPDATE transport_call_batch_rows
        SET phone_type = :phone_type,
            consent_status = :consent_status,
            do_not_call = :do_not_call,
            updated_at = now()
        WHERE company_id = CAST(:company_id AS uuid) AND phone = :phone
    """), {
        "company_id": str(company_id), "phone": phone, "phone_type": _phone_type(phone),
        "consent_status": consent_status, "do_not_call": bool(payload.do_not_call),
    })
    await db.commit()
    return await _consent(db, company_id, phone)


def _validate_webhook(request: Request, form: dict[str, Any], runtime: dict[str, str]) -> None:
    if os.getenv("TWILIO_VALIDATE_SIGNATURES", "true").strip().lower() in {"0", "false", "no"}:
        return
    signature = request.headers.get("x-twilio-signature", "")
    public_url = f"{_public_base(request)}{request.url.path}"
    if request.url.query:
        public_url = f"{public_url}?{request.url.query}"
    if not signature or not RequestValidator(runtime["auth_token"]).validate(public_url, form, signature):
        raise HTTPException(status_code=403, detail="twilio_signature_invalid")


@router.get("/companies/{company_id}/configuration")
async def telephony_configuration(
    company_id: uuid.UUID,
    request: Request,
    _: CompanyUser = Depends(_telephony_manager),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_transport_telephony_storage(db)
    company = await _company(db, company_id)
    settings = _settings(company)
    runtime = _twilio_runtime()
    await _sync_numbers(db, company_id, settings["outgoing_numbers"])
    await db.commit()
    return {
        "ok": True,
        "configured": _runtime_ready(runtime) and bool(settings["outgoing_numbers"]),
        "credentials_ready": _runtime_ready(runtime),
        "settings": settings,
        "voice_url": f"{_public_base(request)}/api/v1/transport-telephony/voice",
        "status_url": f"{_public_base(request)}/api/v1/transport-telephony/companies/{company_id}/status",
        "missing": [
            env_name for key, env_name in {
                "account_sid": "TWILIO_ACCOUNT_SID",
                "auth_token": "TWILIO_AUTH_TOKEN",
                "api_key_sid": "TWILIO_API_KEY_SID",
                "api_key_secret": "TWILIO_API_KEY_SECRET",
                "twiml_app_sid": "TWILIO_TWIML_APP_SID",
            }.items() if not runtime.get(key)
        ],
    }


@router.put("/companies/{company_id}/configuration")
async def update_telephony_configuration(
    company_id: uuid.UUID,
    payload: TelephonyConfigurationIn,
    request: Request,
    _: CompanyUser = Depends(_telephony_manager),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_transport_telephony_storage(db)
    company = await _company(db, company_id)
    numbers = list(dict.fromkeys(filter(None, (_normalize_phone(item) for item in payload.outgoing_numbers))))[:10]
    store = dict(company.settings_json or {})
    store["transport_telephony"] = {
        "outgoing_numbers": numbers,
        "default_campaign": _clean(payload.default_campaign or "General", 120),
        "strict_consent": bool(payload.strict_consent),
        "auto_whatsapp_documents": bool(payload.auto_whatsapp_documents),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    company.settings_json = store
    await _sync_numbers(db, company_id, numbers)
    await db.commit()
    return await telephony_configuration(company_id, request, _, db)


@router.get("/companies/{company_id}/token")
async def telephony_token(
    company_id: uuid.UUID,
    user: CompanyUser = Depends(_telephony_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_transport_telephony_storage(db)
    company = await _company(db, company_id)
    runtime = _twilio_runtime()
    settings = _settings(company)
    if not _runtime_ready(runtime):
        raise HTTPException(status_code=503, detail="Twilio no esta configurado en Railway.")
    if not settings["outgoing_numbers"]:
        raise HTTPException(status_code=503, detail="No hay numeros de salida configurados para la empresa.")
    identity = _identity(user)
    token = AccessToken(
        runtime["account_sid"],
        runtime["api_key_sid"],
        runtime["api_key_secret"],
        identity=identity,
        ttl=3600,
    )
    token.add_grant(VoiceGrant(
        outgoing_application_sid=runtime["twiml_app_sid"],
        incoming_allow=False,
        outgoing_application_params={"company_id": str(company_id)},
    ))
    return {"ok": True, "token": token.to_jwt(), "identity": identity, "expires_in": 3600}


@router.put("/companies/{company_id}/consents/{phone}")
async def update_telephony_consent(
    company_id: uuid.UUID,
    phone: str,
    payload: TelephonyConsentIn,
    user: CompanyUser = Depends(_telephony_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_transport_telephony_storage(db)
    normalized = _normalize_phone(phone)
    if not normalized:
        raise HTTPException(status_code=400, detail="phone_invalid")
    current = await _consent(db, company_id, normalized)
    manager = _clean(user.role, 80).lower() in TELEPHONY_MANAGER_ROLES
    requested_status = _clean(payload.consent_status, 30).lower()
    if not manager and bool(current.get("do_not_call")) and not payload.do_not_call:
        raise HTTPException(status_code=403, detail="Solo supervision puede retirar un bloqueo No llamar.")
    if not manager and current.get("consent_status") in BLOCKED_CONSENT_STATUSES and requested_status == "granted":
        raise HTTPException(status_code=403, detail="Solo supervision puede reactivar un consentimiento rechazado o revocado.")
    consent = await _save_consent(db, company_id, normalized, payload, user.full_name or user.email)
    return {"ok": True, "consent": consent}


@router.post("/companies/{company_id}/preflight")
async def telephony_preflight(
    company_id: uuid.UUID,
    payload: TelephonyPreflightIn,
    _: CompanyUser = Depends(_telephony_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_transport_telephony_storage(db)
    company = await _company(db, company_id)
    phone = _normalize_phone(payload.phone)
    if not phone:
        raise HTTPException(status_code=400, detail="Numero invalido. Usa formato +57 o diez digitos.")
    consent = await _consent(db, company_id, phone)
    batch_row_id = _optional_uuid(payload.batch_row_id, "batch_row_id_invalid")
    if batch_row_id:
        batch_consent = (await db.execute(text("""
            SELECT phone_type, consent_status, do_not_call, campaign_code
            FROM transport_call_batch_rows
            WHERE company_id = CAST(:company_id AS uuid) AND id = CAST(:row_id AS uuid)
            LIMIT 1
        """), {"company_id": str(company_id), "row_id": batch_row_id})).mappings().first()
        if batch_consent:
            consent["do_not_call"] = bool(consent.get("do_not_call")) or bool(batch_consent.get("do_not_call"))
            if consent.get("consent_status") == "unknown" and batch_consent.get("consent_status"):
                consent["consent_status"] = batch_consent.get("consent_status")
            if consent.get("phone_type") == "unknown" and batch_consent.get("phone_type"):
                consent["phone_type"] = batch_consent.get("phone_type")
    settings = _settings(company)
    allowed = not bool(consent.get("do_not_call")) and consent.get("consent_status") not in BLOCKED_CONSENT_STATUSES
    if settings["strict_consent"]:
        allowed = allowed and consent.get("consent_status") == "granted"
    return {
        "ok": True,
        "allowed": allowed,
        "phone": phone,
        "phone_type": consent.get("phone_type") or _phone_type(phone),
        "consent": consent,
        "campaign_code": _clean(payload.campaign_code or ((batch_consent or {}).get("campaign_code") if batch_row_id else "") or settings["default_campaign"], 120),
        "reason": "allowed" if allowed else "consent_required_or_do_not_call",
    }


@router.post("/voice")
async def telephony_voice(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    runtime = _twilio_runtime()
    if not _runtime_ready(runtime):
        raise HTTPException(status_code=503, detail="twilio_runtime_incomplete")
    form = {key: str(value) for key, value in (await request.form()).items()}
    _validate_webhook(request, form, runtime)
    try:
        company_id = uuid.UUID(_clean(form.get("company_id") or form.get("CompanyId"), 80))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="company_id_invalid") from exc
    await ensure_transport_telephony_storage(db)
    company = await _company(db, company_id)
    user_id = _identity_user_id(form.get("From"))
    user = (
        await db.execute(select(CompanyUser).where(
            CompanyUser.id == uuid.UUID(user_id),
            CompanyUser.company_id == company_id,
        ))
    ).scalar_one_or_none() if user_id else None
    if not user:
        raise HTTPException(status_code=403, detail="voice_identity_not_allowed")
    phone = _normalize_phone(form.get("To"))
    if not phone:
        raise HTTPException(status_code=400, detail="phone_invalid")
    consent = await _consent(db, company_id, phone)
    batch_row_id = _optional_uuid(form.get("BatchRowId"), "batch_row_id_invalid")
    if batch_row_id:
        batch_consent = (await db.execute(text("""
            SELECT phone_type, consent_status, do_not_call, campaign_code
            FROM transport_call_batch_rows
            WHERE company_id = CAST(:company_id AS uuid) AND id = CAST(:row_id AS uuid)
            LIMIT 1
        """), {"company_id": str(company_id), "row_id": batch_row_id})).mappings().first()
        if batch_consent:
            consent["do_not_call"] = bool(consent.get("do_not_call")) or bool(batch_consent.get("do_not_call"))
            if consent.get("consent_status") == "unknown" and batch_consent.get("consent_status"):
                consent["consent_status"] = batch_consent.get("consent_status")
            if consent.get("phone_type") == "unknown" and batch_consent.get("phone_type"):
                consent["phone_type"] = batch_consent.get("phone_type")
    settings = _settings(company)
    allowed = not bool(consent.get("do_not_call")) and consent.get("consent_status") not in BLOCKED_CONSENT_STATUSES
    if settings["strict_consent"]:
        allowed = allowed and consent.get("consent_status") == "granted"
    response = VoiceResponse()
    if not allowed:
        response.say("La llamada fue bloqueada por la politica de consentimiento.", language="es-CO")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")
    caller_number = await _next_number(db, company_id, settings["outgoing_numbers"])
    parent_sid = _clean(form.get("CallSid"), 120)
    if not parent_sid:
        raise HTTPException(status_code=400, detail="call_sid_missing")
    mini_panel = user.settings_json.get("mini_panel") if isinstance(user.settings_json, dict) else {}
    employee_id = _clean((mini_panel or {}).get("employee_id"), 80)
    employee = None
    if employee_id:
        employee = (await db.execute(text("SELECT full_name FROM employees WHERE id = CAST(:id AS uuid) AND company_id = CAST(:company_id AS uuid)"), {"id": employee_id, "company_id": str(company_id)})).mappings().first()
    advisor_name = _clean((employee or {}).get("full_name") or user.full_name or user.email, 180)
    campaign = _clean(form.get("CampaignCode") or ((batch_consent or {}).get("campaign_code") if batch_row_id else "") or settings["default_campaign"], 120)
    customer_name = _clean(form.get("CustomerName"), 180)
    await db.execute(text("""
        INSERT INTO transport_call_logs(
            company_id, advisor_name, advisor_status, customer_name, phone, call_direction,
            call_status, result, source, twilio_call_sid, twilio_parent_call_sid, batch_row_id,
            campaign_code, caller_number, phone_type, consent_status, do_not_call, created_at, updated_at
        ) SELECT
            CAST(:company_id AS uuid), :advisor_name, 'in_call', :customer_name, :phone, 'outbound',
            'pending', 'follow_up', 'twilio', CAST(:parent_sid AS varchar(120)),
            CAST(:parent_sid AS varchar(120)), CAST(NULLIF(:batch_row_id, '') AS uuid),
            :campaign, :caller_number, :phone_type, :consent_status, :do_not_call, now(), now()
        WHERE NOT EXISTS (
            SELECT 1 FROM transport_call_logs
            WHERE company_id = CAST(:company_id AS uuid)
              AND (
                CAST(twilio_call_sid AS varchar(120)) = CAST(:parent_sid AS varchar(120))
                OR CAST(twilio_parent_call_sid AS varchar(120)) = CAST(:parent_sid AS varchar(120))
              )
        )
    """), {
        "company_id": str(company_id), "advisor_name": advisor_name, "customer_name": customer_name,
        "phone": phone, "parent_sid": parent_sid, "batch_row_id": batch_row_id, "campaign": campaign,
        "caller_number": caller_number, "phone_type": consent.get("phone_type") or _phone_type(phone),
        "consent_status": consent.get("consent_status") or "unknown", "do_not_call": bool(consent.get("do_not_call")),
    })
    await db.commit()
    status_url = f"{_public_base(request)}/api/v1/transport-telephony/companies/{company_id}/status"
    dial = Dial(caller_id=caller_number, answer_on_bridge=True)
    dial.number(
        phone,
        status_callback=status_url,
        status_callback_event="initiated ringing answered completed",
        status_callback_method="POST",
    )
    response.append(dial)
    return Response(content=str(response), media_type="application/xml")


async def _fetch_twilio_cost(runtime: dict[str, str], call_sid: str) -> tuple[float, str]:
    try:
        call = await asyncio.to_thread(Client(runtime["account_sid"], runtime["auth_token"]).calls(call_sid).fetch)
        return abs(float(call.price or 0)), _clean(call.price_unit or "USD", 12).upper()
    except (TwilioRestException, ValueError, TypeError):
        return 0.0, "USD"


@router.post("/companies/{company_id}/status")
async def telephony_status(company_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    runtime = _twilio_runtime()
    if not runtime.get("auth_token"):
        raise HTTPException(status_code=503, detail="twilio_auth_missing")
    form = {key: str(value) for key, value in (await request.form()).items()}
    _validate_webhook(request, form, runtime)
    await ensure_transport_telephony_storage(db)
    child_sid = _clean(form.get("CallSid"), 120)
    parent_sid = _clean(form.get("ParentCallSid"), 120)
    if not child_sid:
        raise HTTPException(status_code=400, detail="call_sid_missing")
    raw_status = _clean(form.get("CallStatus"), 40).lower()
    call_status = "pending" if raw_status in {"queued", "initiated", "ringing", "in-progress"} else ("missed" if raw_status in {"busy", "failed", "no-answer", "canceled", "cancelled"} else "completed")
    duration = max(0, int(float(form.get("CallDuration") or form.get("Duration") or 0)))
    price_amount = 0.0
    price_currency = "USD"
    if call_status == "completed" and child_sid:
        price_amount, price_currency = await _fetch_twilio_cost(runtime, child_sid)
    result = await db.execute(text("""
        UPDATE transport_call_logs
        SET twilio_call_sid = COALESCE(NULLIF(CAST(:child_sid AS varchar(120)), ''), CAST(twilio_call_sid AS varchar(120))),
            twilio_parent_call_sid = COALESCE(NULLIF(CAST(:parent_sid AS varchar(120)), ''), CAST(twilio_parent_call_sid AS varchar(120))),
            call_status = CAST(:call_status AS varchar(40)),
            advisor_status = CASE WHEN CAST(:call_status AS varchar(40)) = 'pending' THEN 'in_call' ELSE 'available' END,
            duration_seconds = CASE WHEN CAST(:duration AS integer) > 0 THEN CAST(:duration AS integer) ELSE duration_seconds END,
            price_amount = CASE WHEN CAST(:price_amount AS numeric) > 0 THEN CAST(:price_amount AS numeric) ELSE price_amount END,
            price_currency = CAST(:price_currency AS varchar(12)),
            updated_at = now()
        WHERE company_id = CAST(:company_id AS uuid)
          AND (
            (CAST(:parent_sid AS varchar(120)) <> '' AND CAST(twilio_parent_call_sid AS varchar(120)) = CAST(:parent_sid AS varchar(120)))
            OR (CAST(:parent_sid AS varchar(120)) <> '' AND CAST(twilio_call_sid AS varchar(120)) = CAST(:parent_sid AS varchar(120)))
            OR CAST(twilio_call_sid AS varchar(120)) = CAST(:child_sid AS varchar(120))
          )
        RETURNING id, batch_row_id
    """), {
        "company_id": str(company_id), "child_sid": child_sid, "parent_sid": parent_sid,
        "call_status": call_status, "duration": duration, "price_amount": price_amount, "price_currency": price_currency,
    })
    updated_call = result.mappings().first()
    if updated_call and updated_call.get("batch_row_id"):
        await db.execute(text("""
            UPDATE transport_call_batch_rows
            SET call_direction = 'outbound', call_status = CAST(:call_status AS varchar(40)),
                duration_seconds = CASE WHEN CAST(:duration AS integer) > 0 THEN CAST(:duration AS integer) ELSE duration_seconds END,
                twilio_call_sid = COALESCE(NULLIF(CAST(:child_sid AS varchar(120)), ''), CAST(twilio_call_sid AS varchar(120))),
                price_amount = CASE WHEN CAST(:price_amount AS numeric) > 0 THEN CAST(:price_amount AS numeric) ELSE price_amount END,
                price_currency = CAST(:price_currency AS varchar(12)), updated_at = now()
            WHERE company_id = CAST(:company_id AS uuid) AND id = CAST(:row_id AS uuid)
        """), {
            "company_id": str(company_id), "row_id": str(updated_call["batch_row_id"]),
            "call_status": call_status, "duration": duration, "child_sid": child_sid,
            "price_amount": price_amount, "price_currency": price_currency,
        })
    await db.commit()
    return {"ok": True, "updated": bool(updated_call), "status": call_status}


@router.post("/companies/{company_id}/sync-costs")
async def sync_telephony_costs(
    company_id: uuid.UUID,
    _: CompanyUser = Depends(_telephony_manager),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    runtime = _twilio_runtime()
    if not runtime.get("account_sid") or not runtime.get("auth_token"):
        raise HTTPException(status_code=503, detail="Twilio no esta configurado.")
    await ensure_transport_telephony_storage(db)
    result = await db.execute(text("""
        SELECT id::text, twilio_call_sid
        FROM transport_call_logs
        WHERE company_id = CAST(:company_id AS uuid)
          AND source = 'twilio'
          AND call_status = 'completed'
          AND price_amount = 0
          AND TRIM(twilio_call_sid) <> ''
        ORDER BY updated_at DESC
        LIMIT 100
    """), {"company_id": str(company_id)})
    updated = 0
    for row in result.mappings().all():
        price, currency = await _fetch_twilio_cost(runtime, str(row["twilio_call_sid"]))
        if price <= 0:
            continue
        await db.execute(text("UPDATE transport_call_logs SET price_amount=:price, price_currency=:currency, updated_at=now() WHERE id=CAST(:id AS uuid)"), {"price": price, "currency": currency, "id": str(row["id"])})
        updated += 1
    await db.commit()
    return {"ok": True, "updated": updated}
