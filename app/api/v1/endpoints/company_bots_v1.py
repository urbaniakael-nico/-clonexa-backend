from __future__ import annotations

import json
import os
import secrets
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.endpoints.bots import decrypt_token

router = APIRouter()


def clean(value: Any) -> str:
    return str(value or "").strip()


def public_base_url() -> str:
    return os.getenv("PUBLIC_BASE_URL", "https://clonexa-backend-production.up.railway.app").rstrip("/")


async def ensure_company_bot_storage(db: AsyncSession) -> None:
    await db.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto";'))

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS company_bot_instances (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            channel varchar(40) NOT NULL DEFAULT 'telegram',
            name varchar(180) NULL,
            bot_username varchar(180) NULL,
            bot_token_encrypted text NULL,
            token_mask varchar(80) NULL,
            status varchar(40) NOT NULL DEFAULT 'configured',
            last_validated_at timestamptz NULL,
            last_error text NULL,
            config_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_company_bot_instances_company_channel UNIQUE (company_id, channel)
        )
    """))

    await db.execute(text("""
        ALTER TABLE company_bot_instances
        ADD COLUMN IF NOT EXISTS config_json jsonb NOT NULL DEFAULT '{}'::jsonb
    """))

    await db.execute(text("""
        ALTER TABLE company_bot_instances
        ADD COLUMN IF NOT EXISTS last_error text NULL
    """))

    await db.execute(text("""
        ALTER TABLE company_bot_instances
        ADD COLUMN IF NOT EXISTS last_validated_at timestamptz NULL
    """))

    await db.execute(text("""
        ALTER TABLE company_bot_instances
        ADD COLUMN IF NOT EXISTS status varchar(40) NOT NULL DEFAULT 'configured'
    """))

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


async def active_modules(db: AsyncSession, company_id: str) -> set[str]:
    result = await db.execute(
        text("""
            SELECT lower(m.code) AS code
            FROM company_modules cm
            JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id::text = :company_id
              AND COALESCE(cm.enabled, true) IS TRUE
              AND COALESCE(m.is_active, true) IS TRUE
        """),
        {"company_id": company_id},
    )
    return {str(row[0]).lower() for row in result.all()}


def infer_flow_code(modules: set[str]) -> str:
    if "references" in modules and "workforce" in modules:
        return "velvet_references"
    return "base"


async def bot_config_row(db: AsyncSession, company_id: str) -> dict[str, Any] | None:
    await ensure_company_bot_storage(db)

    result = await db.execute(
        text("""
            SELECT
                id::text AS id,
                company_id::text AS company_id,
                channel,
                name,
                bot_username,
                bot_token_encrypted,
                token_mask,
                status,
                last_validated_at::text AS last_validated_at,
                last_error,
                config_json
            FROM company_bot_instances
            WHERE company_id::text = :company_id
              AND channel = 'telegram'
            LIMIT 1
        """),
        {"company_id": company_id},
    )

    row = result.mappings().first()
    return dict(row) if row else None


def public_config(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {
            "configured": False,
            "ok": False,
            "status": "not_configured",
        }

    config_json = row.get("config_json") or {}
    if isinstance(config_json, str):
        try:
            config_json = json.loads(config_json)
        except Exception:
            config_json = {}

    return {
        "configured": bool(row.get("bot_token_encrypted")),
        "ok": str(row.get("status") or "") != "error",
        "id": row.get("id"),
        "company_id": row.get("company_id"),
        "channel": row.get("channel") or "telegram",
        "name": row.get("name"),
        "bot_username": row.get("bot_username"),
        "masked_token": row.get("token_mask"),
        "status": row.get("status") or "configured",
        "last_validated_at": row.get("last_validated_at"),
        "last_error": row.get("last_error"),
        "flow_code": config_json.get("flow_code"),
        "webhook_mode": config_json.get("webhook_mode"),
        "webhook_url": config_json.get("webhook_url"),
    }


async def telegram_post(token: str, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(f"https://api.telegram.org/bot{token}/{method}", json=payload)

    data = response.json()

    if not data.get("ok"):
        raise HTTPException(status_code=502, detail={"telegram_error": data})

    return data


async def send_message(token: str, chat_id: str | None, text_value: str, reply_markup: dict[str, Any] | None = None) -> None:
    if not chat_id:
        return

    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text_value,
    }

    if reply_markup:
        payload["reply_markup"] = reply_markup

    await telegram_post(token, "sendMessage", payload)


async def answer_callback(token: str, callback_query_id: str | None) -> None:
    if not callback_query_id:
        return

    try:
        await telegram_post(token, "answerCallbackQuery", {"callback_query_id": callback_query_id})
    except Exception:
        pass


def extract_update(update: dict[str, Any]) -> dict[str, Any]:
    callback = update.get("callback_query")

    if isinstance(callback, dict):
        from_user = callback.get("from") or {}
        message = callback.get("message") or {}
        chat = message.get("chat") or {}

        return {
            "update_id": update.get("update_id"),
            "callback_query_id": clean(callback.get("id")),
            "telegram_user_id": clean(from_user.get("id")),
            "telegram_username": from_user.get("username"),
            "chat_id": clean(chat.get("id")),
            "text": clean(callback.get("data")),
        }

    message = update.get("message") or update.get("edited_message") or {}
    from_user = message.get("from") or {}
    chat = message.get("chat") or {}

    return {
        "update_id": update.get("update_id"),
        "callback_query_id": None,
        "telegram_user_id": clean(from_user.get("id")),
        "telegram_username": from_user.get("username"),
        "chat_id": clean(chat.get("id")),
        "text": clean(message.get("text")),
    }


async def employee_by_telegram(db: AsyncSession, company_id: str, telegram_user_id: str) -> dict[str, Any] | None:
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


async def workforce_status(db: AsyncSession, company_id: str, employee_id: str) -> str:
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

    value = clean(row["status"]).lower()
    if value in {"checked_out", "not_started"}:
        return "sin_turno"

    return value or "sin_turno"


def keyboard(rows: list[list[dict[str, Any]]]) -> dict[str, Any]:
    return {"inline_keyboard": rows}


def main_menu(status: str) -> dict[str, Any]:
    if status == "sin_turno":
        return keyboard([[{"text": "▶️ Iniciar turno", "callback_data": "velvet:start"}]])

    if status == "on_break":
        return keyboard([
            [
                {"text": "✅ Retornar", "callback_data": "velvet:resume"},
                {"text": "🏁 Finalizar turno", "callback_data": "velvet:end"},
            ]
        ])

    return keyboard([
        [
            {"text": "☕ Pausa", "callback_data": "velvet:pause"},
            {"text": "🏁 Finalizar turno", "callback_data": "velvet:end"},
        ],
        [
            {"text": "🔁 Cambiar referencia", "callback_data": "velvet:switch"},
            {"text": "✅ Cerrar referencia", "callback_data": "velvet:close"},
        ],
    ])


async def references(db: AsyncSession, company_id: str) -> list[dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT min(id)::text AS id, name, count(*) AS sizes_count
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


async def reference_by_id(db: AsyncSession, company_id: str, reference_id: str) -> dict[str, Any] | None:
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


async def sizes_by_reference_id(db: AsyncSession, company_id: str, reference_id: str) -> list[dict[str, Any]]:
    ref = await reference_by_id(db, company_id, reference_id)
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


def references_keyboard(refs: list[dict[str, Any]], prefix: str) -> dict[str, Any]:
    return keyboard([
        [{"text": clean(ref.get("name"))[:60], "callback_data": f"{prefix}:{ref.get('id')}"}]
        for ref in refs
    ])


def sizes_keyboard(items: list[dict[str, Any]]) -> dict[str, Any]:
    return keyboard([
        [{"text": clean(item.get("size"))[:60], "callback_data": f"velvet:close_size:{item.get('id')}"}]
        for item in items
    ])


async def insert_attendance_event(
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
            "source_ref": f"company_bot_v1:{event_type}",
            "detail": detail,
            "metadata_json": json.dumps({"source": "company_bot_v1"}, ensure_ascii=False),
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


async def open_reference_session(
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
            SET ended_at = now(),
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


async def close_active_reference_session(db: AsyncSession, company_id: str, employee_id: str, status: str) -> None:
    await db.execute(
        text("""
            UPDATE reference_work_sessions
            SET ended_at = now(),
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


async def set_pending_total(
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


async def get_pending_total(db: AsyncSession, company_id: str, telegram_user_id: str) -> dict[str, Any] | None:
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


async def clear_pending_total(db: AsyncSession, company_id: str, telegram_user_id: str) -> None:
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


async def save_production_close(
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


async def handle_velvet_references(
    *,
    db: AsyncSession,
    token: str,
    company_id: str,
    update: dict[str, Any],
) -> dict[str, Any]:
    info = extract_update(update)

    telegram_user_id = info["telegram_user_id"]
    telegram_username = info["telegram_username"]
    chat_id = info["chat_id"]
    text_value = info["text"]
    callback_query_id = info["callback_query_id"]

    if callback_query_id:
        await answer_callback(token, callback_query_id)

    if not telegram_user_id:
        return {"ok": True, "ignored": "missing_telegram_user_id"}

    employee = await employee_by_telegram(db, company_id, telegram_user_id)

    if not employee:
        await send_message(
            token,
            chat_id,
            f"No encontré un empleado activo vinculado a este Telegram.\nTelegram ID: {telegram_user_id}",
        )
        return {"ok": True, "handled": "not_linked"}

    pending = await get_pending_total(db, company_id, telegram_user_id)

    if pending and not text_value.startswith("/") and not text_value.startswith("velvet:"):
        if not text_value.isdigit() or int(text_value) < 0:
            await send_message(token, chat_id, "Escribe solo el número total terminado.")
            return {"ok": True, "handled": "invalid_total"}

        quantity = int(text_value)

        await save_production_close(
            db,
            company_id=company_id,
            employee=employee,
            telegram_user_id=telegram_user_id,
            reference=pending,
            quantity_finished=quantity,
        )

        await clear_pending_total(db, company_id, telegram_user_id)
        await db.commit()

        status = await workforce_status(db, company_id, employee["employee_id"])

        await send_message(
            token,
            chat_id,
            f"✅ Producción cerrada: {pending['name']} / {pending['size']} / total {quantity}.",
            reply_markup=main_menu(status),
        )

        return {"ok": True, "handled": "production_closed"}

    raw_lower = clean(text_value).lower()

    if raw_lower in {"/start", "start", "menu", "/menu"}:
        status = await workforce_status(db, company_id, employee["employee_id"])
        await send_message(
            token,
            chat_id,
            f"Hola {employee['employee_name']} 👋\nEmpresa: Velvet\n\nSelecciona una acción:",
            reply_markup=main_menu(status),
        )
        return {"ok": True, "handled": "menu"}

    if raw_lower == "velvet:start":
        refs = await references(db, company_id)

        if not refs:
            await send_message(token, chat_id, "No hay referencias activas para bot.")
            return {"ok": True, "handled": "references_empty"}

        await send_message(
            token,
            chat_id,
            "🧵 Selecciona la referencia para iniciar turno.",
            reply_markup=references_keyboard(refs, "velvet:start_ref"),
        )
        return {"ok": True, "handled": "start_reference_prompt"}

    if raw_lower.startswith("velvet:start_ref:"):
        reference_id = raw_lower.split(":", 2)[2]
        ref = await reference_by_id(db, company_id, reference_id)

        if not ref:
            await send_message(token, chat_id, "Referencia no encontrada o inactiva.")
            return {"ok": True, "handled": "reference_missing"}

        await insert_attendance_event(
            db,
            company_id=company_id,
            employee=employee,
            event_type="check_in",
            event_label="Inicio de turno",
            status_after="working",
            detail=f"Referencia inicial: {ref['name']}",
        )

        await open_reference_session(
            db,
            company_id=company_id,
            employee=employee,
            telegram_user_id=telegram_user_id,
            reference=ref,
            close_status="closed_by_new_start",
        )

        await db.commit()

        await send_message(
            token,
            chat_id,
            f"✅ Turno iniciado en referencia: {ref['name']}.",
            reply_markup=main_menu("working"),
        )
        return {"ok": True, "handled": "shift_started_with_reference"}

    if raw_lower == "velvet:pause":
        await insert_attendance_event(
            db,
            company_id=company_id,
            employee=employee,
            event_type="break_start",
            event_label="Pausa",
            status_after="on_break",
        )
        await db.commit()
        await send_message(token, chat_id, "☕ Pausa registrada.", reply_markup=main_menu("on_break"))
        return {"ok": True, "handled": "pause"}

    if raw_lower == "velvet:resume":
        await insert_attendance_event(
            db,
            company_id=company_id,
            employee=employee,
            event_type="break_end",
            event_label="Retorno",
            status_after="working",
        )
        await db.commit()
        await send_message(token, chat_id, "✅ Retomaste labores.", reply_markup=main_menu("working"))
        return {"ok": True, "handled": "resume"}

    if raw_lower == "velvet:switch":
        refs = await references(db, company_id)
        await send_message(token, chat_id, "🔁 Selecciona la nueva referencia.", reply_markup=references_keyboard(refs, "velvet:switch_ref"))
        return {"ok": True, "handled": "switch_prompt"}

    if raw_lower.startswith("velvet:switch_ref:"):
        reference_id = raw_lower.split(":", 2)[2]
        ref = await reference_by_id(db, company_id, reference_id)

        if not ref:
            await send_message(token, chat_id, "Referencia no encontrada o inactiva.")
            return {"ok": True, "handled": "reference_missing"}

        await open_reference_session(
            db,
            company_id=company_id,
            employee=employee,
            telegram_user_id=telegram_user_id,
            reference=ref,
            close_status="switched",
        )

        await db.commit()

        await send_message(token, chat_id, f"🔁 Cambio de referencia registrado: {ref['name']}.", reply_markup=main_menu("working"))
        return {"ok": True, "handled": "reference_switched"}

    if raw_lower == "velvet:close":
        refs = await references(db, company_id)
        await send_message(token, chat_id, "✅ Selecciona la referencia que vas a cerrar.", reply_markup=references_keyboard(refs, "velvet:close_ref"))
        return {"ok": True, "handled": "close_reference_prompt"}

    if raw_lower.startswith("velvet:close_ref:"):
        reference_id = raw_lower.split(":", 2)[2]
        sizes = await sizes_by_reference_id(db, company_id, reference_id)

        if not sizes:
            await send_message(token, chat_id, "No hay tallas activas para esa referencia.")
            return {"ok": True, "handled": "sizes_empty"}

        await send_message(token, chat_id, "📏 Selecciona la talla.", reply_markup=sizes_keyboard(sizes))
        return {"ok": True, "handled": "size_prompt"}

    if raw_lower.startswith("velvet:close_size:"):
        reference_id = raw_lower.split(":", 2)[2]
        ref = await reference_by_id(db, company_id, reference_id)

        if not ref:
            await send_message(token, chat_id, "Referencia/talla no encontrada o inactiva.")
            return {"ok": True, "handled": "reference_size_missing"}

        await set_pending_total(
            db,
            company_id=company_id,
            employee=employee,
            telegram_user_id=telegram_user_id,
            telegram_username=telegram_username,
            reference=ref,
        )

        await db.commit()

        await send_message(token, chat_id, f"🔢 Escribe el total terminado para {ref['name']} / talla {ref['size']}.")
        return {"ok": True, "handled": "total_prompt"}

    if raw_lower == "velvet:end":
        await insert_attendance_event(
            db,
            company_id=company_id,
            employee=employee,
            event_type="check_out",
            event_label="Finalización de turno",
            status_after="checked_out",
        )

        await close_active_reference_session(db, company_id, employee["employee_id"], "ended_with_shift")
        await clear_pending_total(db, company_id, telegram_user_id)
        await db.commit()

        await send_message(token, chat_id, "🏁 Turno finalizado.", reply_markup=main_menu("sin_turno"))
        return {"ok": True, "handled": "shift_ended"}

    status = await workforce_status(db, company_id, employee["employee_id"])
    await send_message(token, chat_id, "Selecciona una acción:", reply_markup=main_menu(status))
    return {"ok": True, "handled": "fallback_menu"}


@router.post("/companies/{company_id}/telegram/activate-webhook")
async def activate_company_telegram_webhook(
    company_id: str,
    request: Request,
    payload: dict[str, Any] | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_company_bot_storage(db)

    row = await bot_config_row(db, company_id)

    if not row or not row.get("bot_token_encrypted"):
        raise HTTPException(status_code=400, detail="Primero guarda el token del bot.")

    token = decrypt_token(row.get("bot_token_encrypted"))

    if not token:
        raise HTTPException(status_code=400, detail="Token Telegram vacío o inválido.")

    modules = await active_modules(db, company_id)
    requested_flow = clean((payload or {}).get("flow_code"))
    flow_code = requested_flow or infer_flow_code(modules)

    if flow_code != "velvet_references":
        raise HTTPException(status_code=400, detail=f"Flujo no soportado todavía: {flow_code}")

    webhook_secret = secrets.token_urlsafe(32)
    webhook_url = f"{public_base_url()}/api/v1/company-bots-v1/telegram/webhook/{company_id}"

    me = await telegram_post(token, "getMe", {})
    bot_user = me.get("result") or {}
    bot_username = clean(bot_user.get("username"))

    set_webhook_payload = {
        "url": webhook_url,
        "allowed_updates": ["message", "callback_query"],
        "drop_pending_updates": True,
        "secret_token": webhook_secret,
    }

    telegram_result = await telegram_post(token, "setWebhook", set_webhook_payload)

    config_json = {
        "flow_code": flow_code,
        "webhook_mode": "dedicated",
        "webhook_url": webhook_url,
        "webhook_secret": webhook_secret,
    }

    await db.execute(
        text("""
            UPDATE company_bot_instances
            SET
                bot_username = :bot_username,
                status = 'active',
                last_validated_at = now(),
                last_error = NULL,
                config_json = COALESCE(config_json, '{}'::jsonb) || CAST(:config_json AS jsonb),
                updated_at = now()
            WHERE company_id::text = :company_id
              AND channel = 'telegram'
        """),
        {
            "company_id": company_id,
            "bot_username": bot_username,
            "config_json": json.dumps(config_json, ensure_ascii=False),
        },
    )

    await db.commit()

    fresh = await bot_config_row(db, company_id)
    response = public_config(fresh)
    response["telegram"] = telegram_result
    return response


@router.post("/telegram/webhook/{company_id}")
async def company_telegram_webhook(
    company_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_telegram_bot_api_secret_token: str | None = Header(None),
) -> dict[str, Any]:
    await ensure_company_bot_storage(db)

    row = await bot_config_row(db, company_id)

    if not row or not row.get("bot_token_encrypted"):
        return {"ok": True, "ignored": "bot_not_configured"}

    config_json = row.get("config_json") or {}
    if isinstance(config_json, str):
        try:
            config_json = json.loads(config_json)
        except Exception:
            config_json = {}

    expected_secret = clean(config_json.get("webhook_secret"))

    if expected_secret and x_telegram_bot_api_secret_token != expected_secret:
        raise HTTPException(status_code=403, detail="webhook secret inválido.")

    token = decrypt_token(row.get("bot_token_encrypted"))
    flow_code = clean(config_json.get("flow_code"))

    update = await request.json()

    if flow_code == "velvet_references":
        return await handle_velvet_references(
            db=db,
            token=token,
            company_id=company_id,
            update=update,
        )

    return {
        "ok": True,
        "ignored": "unsupported_flow",
        "flow_code": flow_code,
    }


@router.get("/companies/{company_id}/telegram/status")
async def company_telegram_webhook_status(
    company_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await bot_config_row(db, company_id)
    return public_config(row)
