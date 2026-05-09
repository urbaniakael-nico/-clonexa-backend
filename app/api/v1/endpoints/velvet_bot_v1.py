from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urljoin

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()

VELVET_BOT_TOKEN_ENV = "VELVET_BOT_TOKEN"
VELVET_BOT_ADMIN_SECRET_ENV = "VELVET_BOT_ADMIN_SECRET"
VELVET_BOT_WEBHOOK_SECRET_ENV = "VELVET_BOT_WEBHOOK_SECRET"
PUBLIC_BASE_URL_ENV = "PUBLIC_BASE_URL"


def _token() -> str:
    token = os.getenv(VELVET_BOT_TOKEN_ENV, "").strip()
    if not token:
        raise HTTPException(status_code=500, detail="VELVET_BOT_TOKEN no configurado.")
    return token


def _admin_secret() -> str:
    return os.getenv(VELVET_BOT_ADMIN_SECRET_ENV, "").strip()


def _webhook_secret() -> str:
    return os.getenv(VELVET_BOT_WEBHOOK_SECRET_ENV, "").strip()


def _public_base_url() -> str:
    value = os.getenv(PUBLIC_BASE_URL_ENV, "").strip()
    if not value:
        value = "https://clonexa-backend-production.up.railway.app"
    return value.rstrip("/")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _is_int(value: str) -> bool:
    value = _clean(value)
    return value.isdigit() and int(value) >= 0


async def _tg_post(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    token = _token()
    url = f"https://api.telegram.org/bot{token}/{method}"

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, json=payload)
        data = response.json()

    if not data.get("ok"):
        raise HTTPException(status_code=502, detail={"telegram_error": data})

    return data


async def _send_message(
    chat_id: str | None,
    text_value: str,
    reply_markup: dict[str, Any] | None = None,
) -> None:
    if not chat_id:
        return

    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text_value,
    }

    if reply_markup:
        payload["reply_markup"] = reply_markup

    await _tg_post("sendMessage", payload)


async def _answer_callback(callback_query_id: str | None) -> None:
    if not callback_query_id:
        return

    try:
        await _tg_post("answerCallbackQuery", {"callback_query_id": callback_query_id})
    except Exception:
        pass


def _extract_update(update: dict[str, Any]) -> dict[str, Any]:
    callback = update.get("callback_query")

    if isinstance(callback, dict):
        from_user = callback.get("from") or {}
        message = callback.get("message") or {}
        chat = message.get("chat") or {}

        return {
            "update_id": update.get("update_id"),
            "is_callback": True,
            "callback_query_id": _clean(callback.get("id")),
            "telegram_user_id": _clean(from_user.get("id")),
            "telegram_username": from_user.get("username"),
            "first_name": from_user.get("first_name"),
            "chat_id": _clean(chat.get("id")),
            "text": _clean(callback.get("data")),
        }

    message = update.get("message") or update.get("edited_message") or {}
    from_user = message.get("from") or {}
    chat = message.get("chat") or {}

    return {
        "update_id": update.get("update_id"),
        "is_callback": False,
        "callback_query_id": None,
        "telegram_user_id": _clean(from_user.get("id")),
        "telegram_username": from_user.get("username"),
        "first_name": from_user.get("first_name"),
        "chat_id": _clean(chat.get("id")),
        "text": _clean(message.get("text")),
    }


async def _ensure_storage(db: AsyncSession) -> None:
    await db.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto";'))

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS velvet_bot_v1_pending_actions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL,
            telegram_user_id varchar(120) NOT NULL,
            telegram_username varchar(180) NULL,
            employee_id uuid NULL,
            action varchar(80) NOT NULL,
            payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            expires_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_velvet_bot_v1_pending UNIQUE (company_id, telegram_user_id, action)
        )
    """))

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS reference_work_sessions (
            id text PRIMARY KEY,
            company_id text NOT NULL,
            employee_id text NOT NULL,
            employee_name text NULL,
            telegram_user_id text NULL,
            reference_id text NULL,
            reference_name text NOT NULL,
            started_at timestamptz NOT NULL DEFAULT now(),
            ended_at timestamptz NULL,
            duration_minutes numeric NOT NULL DEFAULT 0,
            status text NOT NULL DEFAULT 'active',
            source_channel text NOT NULL DEFAULT 'telegram',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS reference_production_closures (
            id text PRIMARY KEY,
            company_id text NOT NULL,
            employee_id text NOT NULL,
            employee_name text NULL,
            telegram_user_id text NULL,
            reference_id text NULL,
            reference_name text NOT NULL,
            size text NOT NULL,
            quantity_finished integer NOT NULL DEFAULT 0,
            notes text NULL,
            closed_at timestamptz NOT NULL DEFAULT now(),
            source_channel text NOT NULL DEFAULT 'telegram',
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """))


async def _employee_by_telegram(
    db: AsyncSession,
    *,
    company_id: str,
    telegram_user_id: str,
) -> dict[str, Any] | None:
    result = await db.execute(
        text("""
            SELECT
                id::text AS employee_id,
                COALESCE(full_name, '') AS employee_name,
                COALESCE(role, '') AS employee_role,
                COALESCE(status, '') AS status
            FROM employees
            WHERE company_id::text = :company_id
              AND telegram_user_id::text = :telegram_user_id
              AND lower(COALESCE(status, 'active')) IN ('active', 'activo')
            LIMIT 1
        """),
        {
            "company_id": company_id,
            "telegram_user_id": telegram_user_id,
        },
    )

    row = result.mappings().first()
    return dict(row) if row else None


async def _status(
    db: AsyncSession,
    *,
    company_id: str,
    employee_id: str,
) -> str:
    result = await db.execute(
        text("""
            SELECT COALESCE(status, 'sin_turno') AS status
            FROM workforce_attendance_status
            WHERE company_id::text = :company_id
              AND employee_id::text = :employee_id
            LIMIT 1
        """),
        {
            "company_id": company_id,
            "employee_id": employee_id,
        },
    )

    row = result.mappings().first()

    if not row:
        return "sin_turno"

    value = _clean(row["status"]).lower()

    if value in {"checked_out", "not_started"}:
        return "sin_turno"

    return value or "sin_turno"


async def _references(db: AsyncSession, company_id: str) -> list[dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT
                min(id)::text AS id,
                name,
                count(*) AS sizes_count
            FROM product_references
            WHERE company_id = :company_id
              AND bot_active IS TRUE
            GROUP BY name
            ORDER BY name ASC
            LIMIT 50
        """),
        {"company_id": company_id},
    )

    return [dict(row) for row in result.mappings().all()]


async def _reference_by_id(
    db: AsyncSession,
    *,
    company_id: str,
    reference_id: str,
) -> dict[str, Any] | None:
    result = await db.execute(
        text("""
            SELECT id::text AS id, name, size
            FROM product_references
            WHERE company_id = :company_id
              AND id = :reference_id
              AND bot_active IS TRUE
            LIMIT 1
        """),
        {
            "company_id": company_id,
            "reference_id": reference_id,
        },
    )

    row = result.mappings().first()
    return dict(row) if row else None


async def _sizes_by_reference_id(
    db: AsyncSession,
    *,
    company_id: str,
    reference_id: str,
) -> list[dict[str, Any]]:
    ref = await _reference_by_id(db, company_id=company_id, reference_id=reference_id)

    if not ref:
        return []

    result = await db.execute(
        text("""
            SELECT id::text AS id, name, size
            FROM product_references
            WHERE company_id = :company_id
              AND lower(name) = lower(:name)
              AND bot_active IS TRUE
            ORDER BY size ASC
            LIMIT 50
        """),
        {
            "company_id": company_id,
            "name": ref["name"],
        },
    )

    return [dict(row) for row in result.mappings().all()]


def _keyboard(rows: list[list[dict[str, Any]]]) -> dict[str, Any]:
    return {"inline_keyboard": rows}


def _main_menu(status: str) -> dict[str, Any]:
    if status == "sin_turno":
        return _keyboard([
            [{"text": "▶️ Iniciar turno", "callback_data": "velvet:start"}],
        ])

    if status == "on_break":
        return _keyboard([
            [
                {"text": "✅ Retornar", "callback_data": "velvet:resume"},
                {"text": "🏁 Finalizar turno", "callback_data": "velvet:end"},
            ],
        ])

    return _keyboard([
        [
            {"text": "☕ Pausa", "callback_data": "velvet:pause"},
            {"text": "🏁 Finalizar turno", "callback_data": "velvet:end"},
        ],
        [
            {"text": "🔁 Cambiar referencia", "callback_data": "velvet:switch"},
            {"text": "✅ Cerrar referencia", "callback_data": "velvet:close"},
        ],
    ])


def _references_keyboard(refs: list[dict[str, Any]], prefix: str) -> dict[str, Any]:
    rows = []

    for ref in refs:
        rows.append([{
            "text": _clean(ref.get("name"))[:60],
            "callback_data": f"{prefix}:{ref.get('id')}",
        }])

    return _keyboard(rows)


def _sizes_keyboard(sizes: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []

    for item in sizes:
        rows.append([{
            "text": _clean(item.get("size"))[:60],
            "callback_data": f"velvet:close_size:{item.get('id')}",
        }])

    return _keyboard(rows)


async def _insert_attendance_event(
    db: AsyncSession,
    *,
    company_id: str,
    employee: dict[str, Any],
    event_type: str,
    event_label: str,
    status_after: str,
    detail: str = "",
) -> None:
    await db.execute(
        text("""
            INSERT INTO workforce_attendance_events (
                company_id,
                employee_id,
                event_type,
                event_label,
                employee_name,
                employee_role,
                status_after,
                source,
                source_channel,
                source_ref,
                module_code,
                detail,
                metadata_json,
                occurred_at,
                created_at
            )
            VALUES (
                CAST(:company_id AS uuid),
                CAST(:employee_id AS uuid),
                :event_type,
                :event_label,
                :employee_name,
                :employee_role,
                :status_after,
                'telegram',
                'telegram',
                :source_ref,
                'workforce',
                :detail,
                CAST(:metadata_json AS jsonb),
                now(),
                now()
            )
        """),
        {
            "company_id": company_id,
            "employee_id": employee["employee_id"],
            "event_type": event_type,
            "event_label": event_label,
            "employee_name": employee["employee_name"],
            "employee_role": employee.get("employee_role") or "",
            "status_after": status_after,
            "source_ref": f"velvet_bot_v1:{event_type}",
            "detail": detail,
            "metadata_json": json.dumps({"source": "velvet_bot_v1"}, ensure_ascii=False),
        },
    )

    await db.execute(
        text("""
            INSERT INTO workforce_attendance_status (
                company_id,
                employee_id,
                status,
                last_event_type,
                last_event_at,
                updated_at
            )
            VALUES (
                CAST(:company_id AS uuid),
                CAST(:employee_id AS uuid),
                :status,
                :event_type,
                now(),
                now()
            )
            ON CONFLICT (company_id, employee_id)
            DO UPDATE SET
                status = EXCLUDED.status,
                last_event_type = EXCLUDED.last_event_type,
                last_event_at = EXCLUDED.last_event_at,
                updated_at = now()
        """),
        {
            "company_id": company_id,
            "employee_id": employee["employee_id"],
            "status": status_after,
            "event_type": event_type,
        },
    )


async def _open_reference_session(
    db: AsyncSession,
    *,
    company_id: str,
    employee: dict[str, Any],
    telegram_user_id: str,
    reference: dict[str, Any],
    close_status: str,
) -> None:
    await db.execute(
        text("""
            UPDATE reference_work_sessions
            SET
                ended_at = now(),
                duration_minutes = GREATEST(EXTRACT(EPOCH FROM (now() - started_at)) / 60.0, 0),
                status = :close_status,
                updated_at = now()
            WHERE company_id = :company_id
              AND employee_id = :employee_id
              AND status = 'active'
        """),
        {
            "company_id": company_id,
            "employee_id": employee["employee_id"],
            "close_status": close_status,
        },
    )

    await db.execute(
        text("""
            INSERT INTO reference_work_sessions (
                id,
                company_id,
                employee_id,
                employee_name,
                telegram_user_id,
                reference_id,
                reference_name,
                started_at,
                status,
                source_channel,
                created_at,
                updated_at
            )
            VALUES (
                gen_random_uuid()::text,
                :company_id,
                :employee_id,
                :employee_name,
                :telegram_user_id,
                :reference_id,
                :reference_name,
                now(),
                'active',
                'telegram',
                now(),
                now()
            )
        """),
        {
            "company_id": company_id,
            "employee_id": employee["employee_id"],
            "employee_name": employee["employee_name"],
            "telegram_user_id": telegram_user_id,
            "reference_id": reference["id"],
            "reference_name": reference["name"],
        },
    )


async def _close_active_reference_session(
    db: AsyncSession,
    *,
    company_id: str,
    employee_id: str,
    status: str,
) -> None:
    await db.execute(
        text("""
            UPDATE reference_work_sessions
            SET
                ended_at = now(),
                duration_minutes = GREATEST(EXTRACT(EPOCH FROM (now() - started_at)) / 60.0, 0),
                status = :status,
                updated_at = now()
            WHERE company_id = :company_id
              AND employee_id = :employee_id
              AND status = 'active'
        """),
        {
            "company_id": company_id,
            "employee_id": employee_id,
            "status": status,
        },
    )


async def _set_pending_total(
    db: AsyncSession,
    *,
    company_id: str,
    employee: dict[str, Any],
    telegram_user_id: str,
    telegram_username: str | None,
    reference: dict[str, Any],
) -> None:
    await db.execute(
        text("""
            INSERT INTO velvet_bot_v1_pending_actions (
                company_id,
                telegram_user_id,
                telegram_username,
                employee_id,
                action,
                payload_json,
                expires_at,
                updated_at
            )
            VALUES (
                CAST(:company_id AS uuid),
                :telegram_user_id,
                :telegram_username,
                CAST(:employee_id AS uuid),
                'close_reference_total',
                CAST(:payload_json AS jsonb),
                now() + interval '45 minutes',
                now()
            )
            ON CONFLICT (company_id, telegram_user_id, action)
            DO UPDATE SET
                telegram_username = EXCLUDED.telegram_username,
                employee_id = EXCLUDED.employee_id,
                payload_json = EXCLUDED.payload_json,
                expires_at = EXCLUDED.expires_at,
                updated_at = now()
        """),
        {
            "company_id": company_id,
            "telegram_user_id": telegram_user_id,
            "telegram_username": telegram_username,
            "employee_id": employee["employee_id"],
            "payload_json": json.dumps(reference, ensure_ascii=False),
        },
    )


async def _get_pending_total(
    db: AsyncSession,
    *,
    company_id: str,
    telegram_user_id: str,
) -> dict[str, Any] | None:
    result = await db.execute(
        text("""
            SELECT payload_json
            FROM velvet_bot_v1_pending_actions
            WHERE company_id::text = :company_id
              AND telegram_user_id = :telegram_user_id
              AND action = 'close_reference_total'
              AND (expires_at IS NULL OR expires_at > now())
            ORDER BY updated_at DESC
            LIMIT 1
        """),
        {
            "company_id": company_id,
            "telegram_user_id": telegram_user_id,
        },
    )

    row = result.mappings().first()

    if not row:
        return None

    payload = row["payload_json"]

    if isinstance(payload, str):
        return json.loads(payload)

    return dict(payload)


async def _clear_pending_total(
    db: AsyncSession,
    *,
    company_id: str,
    telegram_user_id: str,
) -> None:
    await db.execute(
        text("""
            DELETE FROM velvet_bot_v1_pending_actions
            WHERE company_id::text = :company_id
              AND telegram_user_id = :telegram_user_id
              AND action = 'close_reference_total'
        """),
        {
            "company_id": company_id,
            "telegram_user_id": telegram_user_id,
        },
    )


async def _save_production_close(
    db: AsyncSession,
    *,
    company_id: str,
    employee: dict[str, Any],
    telegram_user_id: str,
    reference: dict[str, Any],
    quantity_finished: int,
) -> None:
    await db.execute(
        text("""
            INSERT INTO reference_production_closures (
                id,
                company_id,
                employee_id,
                employee_name,
                telegram_user_id,
                reference_id,
                reference_name,
                size,
                quantity_finished,
                closed_at,
                source_channel,
                created_at
            )
            VALUES (
                gen_random_uuid()::text,
                :company_id,
                :employee_id,
                :employee_name,
                :telegram_user_id,
                :reference_id,
                :reference_name,
                :size,
                :quantity_finished,
                now(),
                'telegram',
                now()
            )
        """),
        {
            "company_id": company_id,
            "employee_id": employee["employee_id"],
            "employee_name": employee["employee_name"],
            "telegram_user_id": telegram_user_id,
            "reference_id": reference["id"],
            "reference_name": reference["name"],
            "size": reference["size"],
            "quantity_finished": quantity_finished,
        },
    )


@router.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "velvet_bot_v1",
        "token_configured": bool(os.getenv(VELVET_BOT_TOKEN_ENV, "").strip()),
    }


@router.post("/set-webhook/{company_id}")
async def set_webhook(
    company_id: str,
    admin_secret: str = Query(...),
) -> dict[str, Any]:
    expected = _admin_secret()

    if not expected or admin_secret != expected:
        raise HTTPException(status_code=403, detail="admin_secret inválido.")

    webhook_url = f"{_public_base_url()}/api/v1/velvet-bot-v1/webhook/{company_id}"

    payload: dict[str, Any] = {
        "url": webhook_url,
        "allowed_updates": ["message", "callback_query"],
        "drop_pending_updates": True,
    }

    secret = _webhook_secret()
    if secret:
        payload["secret_token"] = secret

    result = await _tg_post("setWebhook", payload)

    return {
        "ok": True,
        "webhook_url": webhook_url,
        "telegram": result,
    }


@router.post("/webhook/{company_id}")
async def webhook(
    company_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_telegram_bot_api_secret_token: str | None = Header(None),
) -> dict[str, Any]:
    secret = _webhook_secret()

    if secret and x_telegram_bot_api_secret_token != secret:
        raise HTTPException(status_code=403, detail="webhook secret inválido.")

    await _ensure_storage(db)

    update = await request.json()
    info = _extract_update(update)

    telegram_user_id = info["telegram_user_id"]
    telegram_username = info["telegram_username"]
    chat_id = info["chat_id"]
    text_value = info["text"]
    callback_query_id = info["callback_query_id"]

    if callback_query_id:
        await _answer_callback(callback_query_id)

    if not telegram_user_id:
        return {"ok": True, "ignored": "missing_telegram_user_id"}

    employee = await _employee_by_telegram(
        db,
        company_id=company_id,
        telegram_user_id=telegram_user_id,
    )

    if not employee:
        await _send_message(
            chat_id,
            f"No encontré un empleado activo vinculado a este Telegram.\nTelegram ID: {telegram_user_id}",
        )
        return {"ok": True, "handled": "not_linked"}

    pending = await _get_pending_total(
        db,
        company_id=company_id,
        telegram_user_id=telegram_user_id,
    )

    if pending and not text_value.startswith("/") and not text_value.startswith("velvet:"):
        if not _is_int(text_value):
            await _send_message(chat_id, "Escribe solo el número total terminado.")
            return {"ok": True, "handled": "invalid_total"}

        quantity = int(text_value)

        await _save_production_close(
            db,
            company_id=company_id,
            employee=employee,
            telegram_user_id=telegram_user_id,
            reference=pending,
            quantity_finished=quantity,
        )

        await _clear_pending_total(
            db,
            company_id=company_id,
            telegram_user_id=telegram_user_id,
        )

        await db.commit()

        status = await _status(db, company_id=company_id, employee_id=employee["employee_id"])

        await _send_message(
            chat_id,
            f"✅ Producción cerrada: {pending['name']} / {pending['size']} / total {quantity}.",
            reply_markup=_main_menu(status),
        )

        return {"ok": True, "handled": "production_closed"}

    raw = _clean(text_value)
    raw_lower = raw.lower()

    if raw_lower in {"/start", "start", "menu", "/menu"}:
        status = await _status(db, company_id=company_id, employee_id=employee["employee_id"])
        await _send_message(
            chat_id,
            f"Hola {employee['employee_name']} 👋\nEmpresa: Velvet\n\nSelecciona una acción:",
            reply_markup=_main_menu(status),
        )
        return {"ok": True, "handled": "menu"}

    if raw_lower == "velvet:start":
        refs = await _references(db, company_id)

        if not refs:
            await _send_message(chat_id, "No hay referencias activas para bot.")
            return {"ok": True, "handled": "references_empty"}

        await _send_message(
            chat_id,
            "🧵 Selecciona la referencia para iniciar turno.",
            reply_markup=_references_keyboard(refs, "velvet:start_ref"),
        )
        return {"ok": True, "handled": "start_reference_prompt"}

    if raw_lower.startswith("velvet:start_ref:"):
        reference_id = raw.split(":", 2)[2]
        ref = await _reference_by_id(db, company_id=company_id, reference_id=reference_id)

        if not ref:
            await _send_message(chat_id, "Referencia no encontrada o inactiva.")
            return {"ok": True, "handled": "reference_missing"}

        await _insert_attendance_event(
            db,
            company_id=company_id,
            employee=employee,
            event_type="check_in",
            event_label="Inicio de turno",
            status_after="working",
            detail=f"Referencia inicial: {ref['name']}",
        )

        await _open_reference_session(
            db,
            company_id=company_id,
            employee=employee,
            telegram_user_id=telegram_user_id,
            reference=ref,
            close_status="closed_by_new_start",
        )

        await db.commit()

        await _send_message(
            chat_id,
            f"✅ Turno iniciado en referencia: {ref['name']}.",
            reply_markup=_main_menu("working"),
        )
        return {"ok": True, "handled": "shift_started_with_reference"}

    if raw_lower == "velvet:pause":
        await _insert_attendance_event(
            db,
            company_id=company_id,
            employee=employee,
            event_type="break_start",
            event_label="Pausa",
            status_after="on_break",
        )

        await db.commit()

        await _send_message(chat_id, "☕ Pausa registrada.", reply_markup=_main_menu("on_break"))
        return {"ok": True, "handled": "pause"}

    if raw_lower == "velvet:resume":
        await _insert_attendance_event(
            db,
            company_id=company_id,
            employee=employee,
            event_type="break_end",
            event_label="Retorno",
            status_after="working",
        )

        await db.commit()

        await _send_message(chat_id, "✅ Retomaste labores.", reply_markup=_main_menu("working"))
        return {"ok": True, "handled": "resume"}

    if raw_lower == "velvet:switch":
        refs = await _references(db, company_id)
        await _send_message(
            chat_id,
            "🔁 Selecciona la nueva referencia.",
            reply_markup=_references_keyboard(refs, "velvet:switch_ref"),
        )
        return {"ok": True, "handled": "switch_prompt"}

    if raw_lower.startswith("velvet:switch_ref:"):
        reference_id = raw.split(":", 2)[2]
        ref = await _reference_by_id(db, company_id=company_id, reference_id=reference_id)

        if not ref:
            await _send_message(chat_id, "Referencia no encontrada o inactiva.")
            return {"ok": True, "handled": "reference_missing"}

        await _open_reference_session(
            db,
            company_id=company_id,
            employee=employee,
            telegram_user_id=telegram_user_id,
            reference=ref,
            close_status="switched",
        )

        await db.commit()

        await _send_message(
            chat_id,
            f"🔁 Cambio de referencia registrado: {ref['name']}.",
            reply_markup=_main_menu("working"),
        )
        return {"ok": True, "handled": "reference_switched"}

    if raw_lower == "velvet:close":
        refs = await _references(db, company_id)
        await _send_message(
            chat_id,
            "✅ Selecciona la referencia que vas a cerrar.",
            reply_markup=_references_keyboard(refs, "velvet:close_ref"),
        )
        return {"ok": True, "handled": "close_reference_prompt"}

    if raw_lower.startswith("velvet:close_ref:"):
        reference_id = raw.split(":", 2)[2]
        sizes = await _sizes_by_reference_id(db, company_id=company_id, reference_id=reference_id)

        if not sizes:
            await _send_message(chat_id, "No hay tallas activas para esa referencia.")
            return {"ok": True, "handled": "sizes_empty"}

        await _send_message(
            chat_id,
            "📏 Selecciona la talla.",
            reply_markup=_sizes_keyboard(sizes),
        )
        return {"ok": True, "handled": "size_prompt"}

    if raw_lower.startswith("velvet:close_size:"):
        reference_id = raw.split(":", 2)[2]
        ref = await _reference_by_id(db, company_id=company_id, reference_id=reference_id)

        if not ref:
            await _send_message(chat_id, "Referencia/talla no encontrada o inactiva.")
            return {"ok": True, "handled": "reference_size_missing"}

        await _set_pending_total(
            db,
            company_id=company_id,
            employee=employee,
            telegram_user_id=telegram_user_id,
            telegram_username=telegram_username,
            reference=ref,
        )

        await db.commit()

        await _send_message(chat_id, f"🔢 Escribe el total terminado para {ref['name']} / talla {ref['size']}.")
        return {"ok": True, "handled": "total_prompt"}

    if raw_lower == "velvet:end":
        await _insert_attendance_event(
            db,
            company_id=company_id,
            employee=employee,
            event_type="check_out",
            event_label="Finalización de turno",
            status_after="checked_out",
        )

        await _close_active_reference_session(
            db,
            company_id=company_id,
            employee_id=employee["employee_id"],
            status="ended_with_shift",
        )

        await _clear_pending_total(
            db,
            company_id=company_id,
            telegram_user_id=telegram_user_id,
        )

        await db.commit()

        await _send_message(chat_id, "🏁 Turno finalizado.", reply_markup=_main_menu("sin_turno"))
        return {"ok": True, "handled": "shift_ended"}

    status = await _status(db, company_id=company_id, employee_id=employee["employee_id"])

    await _send_message(
        chat_id,
        "Selecciona una acción:",
        reply_markup=_main_menu(status),
    )

    return {"ok": True, "handled": "fallback_menu"}
