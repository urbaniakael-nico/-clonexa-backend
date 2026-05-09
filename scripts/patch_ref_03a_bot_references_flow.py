from pathlib import Path
import re

path = Path("app/api/v1/endpoints/bots.py")
src = path.read_text(encoding="utf-8-sig")

if "REF_03A_BOT_REFERENCES_FLOW" in src:
    print("REF_03A already applied")
    raise SystemExit(0)

# Imports defensivos.
if "import json" not in src:
    src = src.replace("import asyncio\n", "import asyncio\nimport json\n", 1)

# ---------------------------------------------------------------------
# 1) Helpers References Bot
# ---------------------------------------------------------------------
helpers = r'''

# CLONEXA REF_03A_BOT_REFERENCES_FLOW
def _references_enabled_from_codes(enabled_modules: set[str] | list[str] | tuple[str, ...] | None) -> bool:
    codes = {str(code or "").strip().lower() for code in (enabled_modules or [])}
    return bool(codes.intersection({"references", "ref", "referencias"}))


def _ref_txt(language: str, key: str, **kwargs: Any) -> str:
    lang = (language or "es").lower()
    data = {
        "es": {
            "pick_start": "🧵 Selecciona la referencia para iniciar turno.",
            "pick_switch": "🔁 Selecciona la nueva referencia activa.",
            "pick_close": "✅ Selecciona la referencia que vas a cerrar.",
            "pick_size": "📏 Selecciona la talla.",
            "ask_total": "🔢 Escribe el total terminado para {name} / talla {size}.",
            "no_refs": "No hay referencias activas para bot en este momento.",
            "started": "✅ Turno iniciado en referencia: {name}.",
            "switched": "🔁 Cambio de referencia registrado: {name}.",
            "closed": "✅ Producción cerrada: {name} / {size} / total {qty}.",
            "invalid_total": "Escribe solo el número total terminado.",
            "must_start": "Primero debes iniciar turno.",
            "btn_switch": "🔁 Cambiar referencia",
            "btn_close": "✅ Cerrar referencia",
        },
        "en": {
            "pick_start": "🧵 Select the reference to start your shift.",
            "pick_switch": "🔁 Select the new active reference.",
            "pick_close": "✅ Select the reference to close.",
            "pick_size": "📏 Select size.",
            "ask_total": "🔢 Type the finished total for {name} / size {size}.",
            "no_refs": "There are no bot-active references right now.",
            "started": "✅ Shift started on reference: {name}.",
            "switched": "🔁 Reference change saved: {name}.",
            "closed": "✅ Production closed: {name} / {size} / total {qty}.",
            "invalid_total": "Type only the finished total number.",
            "must_start": "You must start your shift first.",
            "btn_switch": "🔁 Change reference",
            "btn_close": "✅ Close reference",
        },
        "fr": {
            "pick_start": "🧵 Sélectionnez la référence pour commencer le service.",
            "pick_switch": "🔁 Sélectionnez la nouvelle référence active.",
            "pick_close": "✅ Sélectionnez la référence à clôturer.",
            "pick_size": "📏 Sélectionnez la taille.",
            "ask_total": "🔢 Écrivez le total terminé pour {name} / taille {size}.",
            "no_refs": "Aucune référence active dans le bot pour le moment.",
            "started": "✅ Service démarré sur la référence : {name}.",
            "switched": "🔁 Changement de référence enregistré : {name}.",
            "closed": "✅ Production clôturée : {name} / {size} / total {qty}.",
            "invalid_total": "Écrivez seulement le nombre total terminé.",
            "must_start": "Vous devez d’abord commencer le service.",
            "btn_switch": "🔁 Changer référence",
            "btn_close": "✅ Clôturer référence",
        },
    }
    template = data.get(lang, data["es"]).get(key, key)
    return template.format(**kwargs)


async def _ensure_reference_bot_storage(db: AsyncSession) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS product_references (
            id text PRIMARY KEY,
            company_id text NOT NULL,
            name text NOT NULL,
            size text NOT NULL,
            initial_quantity integer NOT NULL DEFAULT 0,
            activation_date timestamptz NULL,
            bot_active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS reference_work_sessions (
            id text PRIMARY KEY,
            company_id text NOT NULL,
            employee_id text NOT NULL,
            employee_name text NULL,
            telegram_user_id text NULL,
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
        CREATE INDEX IF NOT EXISTS ix_reference_work_sessions_company_employee_status
        ON reference_work_sessions (company_id, employee_id, status)
    """))

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS reference_production_closures (
            id text PRIMARY KEY,
            company_id text NOT NULL,
            employee_id text NOT NULL,
            employee_name text NULL,
            telegram_user_id text NULL,
            reference_name text NOT NULL,
            size text NOT NULL,
            quantity_finished integer NOT NULL DEFAULT 0,
            notes text NULL,
            closed_at timestamptz NOT NULL DEFAULT now(),
            source_channel text NOT NULL DEFAULT 'telegram',
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """))

    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_reference_production_closures_company_ref_size
        ON reference_production_closures (company_id, reference_name, size)
    """))


async def _reference_bot_options(db: AsyncSession, company_id: Any) -> list[dict[str, Any]]:
    await _ensure_reference_bot_storage(db)
    result = await db.execute(
        text("""
            SELECT
                min(id) AS id,
                name,
                count(*) AS sizes_count
            FROM product_references
            WHERE company_id = :company_id
              AND bot_active IS TRUE
            GROUP BY name
            ORDER BY name ASC
            LIMIT 50
        """),
        {"company_id": str(company_id)},
    )
    return [dict(row) for row in result.mappings().all()]


async def _reference_by_id(db: AsyncSession, company_id: Any, reference_id: str) -> dict[str, Any] | None:
    await _ensure_reference_bot_storage(db)
    result = await db.execute(
        text("""
            SELECT id, name, size, initial_quantity, bot_active
            FROM product_references
            WHERE company_id = :company_id
              AND id = :id
              AND bot_active IS TRUE
            LIMIT 1
        """),
        {"company_id": str(company_id), "id": str(reference_id)},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def _reference_sizes_by_name(db: AsyncSession, company_id: Any, name: str) -> list[dict[str, Any]]:
    await _ensure_reference_bot_storage(db)
    result = await db.execute(
        text("""
            SELECT id, name, size, initial_quantity, bot_active
            FROM product_references
            WHERE company_id = :company_id
              AND lower(name) = lower(:name)
              AND bot_active IS TRUE
            ORDER BY size ASC
            LIMIT 50
        """),
        {"company_id": str(company_id), "name": str(name)},
    )
    return [dict(row) for row in result.mappings().all()]


def _reference_options_keyboard(items: list[dict[str, Any]], prefix: str) -> dict[str, Any]:
    keyboard = []
    for item in items:
        label = str(item.get("name") or "").strip()
        if not label:
            continue
        keyboard.append([{
            "text": label[:60],
            "callback_data": f"{prefix}:{item.get('id')}",
        }])
    return {"inline_keyboard": keyboard}


def _reference_sizes_keyboard(items: list[dict[str, Any]]) -> dict[str, Any]:
    keyboard = []
    for item in items:
        label = str(item.get("size") or "").strip()
        if not label:
            continue
        keyboard.append([{
            "text": label[:60],
            "callback_data": f"clx:ref:close_size:{item.get('id')}",
        }])
    return {"inline_keyboard": keyboard}


async def _close_active_reference_session(
    db: AsyncSession,
    *,
    company_id: Any,
    employee_id: Any,
    status: str = "closed",
) -> None:
    await _ensure_reference_bot_storage(db)
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
            "company_id": str(company_id),
            "employee_id": str(employee_id),
            "status": status,
        },
    )


async def _open_reference_session(
    db: AsyncSession,
    *,
    company_id: Any,
    employee_id: Any,
    employee_name: str | None,
    telegram_user_id: str | None,
    reference_name: str,
) -> None:
    await _ensure_reference_bot_storage(db)
    await _close_active_reference_session(
        db,
        company_id=company_id,
        employee_id=employee_id,
        status="switched",
    )
    await db.execute(
        text("""
            INSERT INTO reference_work_sessions (
                id,
                company_id,
                employee_id,
                employee_name,
                telegram_user_id,
                reference_name,
                started_at,
                status,
                source_channel,
                created_at,
                updated_at
            )
            VALUES (
                :id,
                :company_id,
                :employee_id,
                :employee_name,
                :telegram_user_id,
                :reference_name,
                now(),
                'active',
                'telegram',
                now(),
                now()
            )
        """),
        {
            "id": str(uuid4()),
            "company_id": str(company_id),
            "employee_id": str(employee_id),
            "employee_name": employee_name,
            "telegram_user_id": telegram_user_id,
            "reference_name": reference_name,
        },
    )


async def _set_pending_reference_close_total(
    db: AsyncSession,
    *,
    company_id: Any,
    telegram_user_id: str,
    telegram_username: str | None,
    employee_id: Any,
    payload: dict[str, Any],
) -> None:
    await ensure_bot_storage(db)
    await db.execute(
        text("""
            INSERT INTO company_telegram_pending_actions (
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
                :company_id,
                :telegram_user_id,
                :telegram_username,
                :employee_id,
                'reference_close_total',
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
            "company_id": str(company_id),
            "telegram_user_id": str(telegram_user_id),
            "telegram_username": telegram_username,
            "employee_id": str(employee_id),
            "payload_json": json.dumps(payload, ensure_ascii=False),
        },
    )


async def _get_pending_reference_close_total(
    db: AsyncSession,
    *,
    company_id: Any,
    telegram_user_id: str,
) -> dict[str, Any] | None:
    await ensure_bot_storage(db)
    result = await db.execute(
        text("""
            SELECT id, employee_id, payload_json, expires_at
            FROM company_telegram_pending_actions
            WHERE company_id = :company_id
              AND telegram_user_id = :telegram_user_id
              AND action = 'reference_close_total'
              AND (expires_at IS NULL OR expires_at > now())
            ORDER BY updated_at DESC
            LIMIT 1
        """),
        {"company_id": str(company_id), "telegram_user_id": str(telegram_user_id)},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def _clear_pending_reference_close_total(
    db: AsyncSession,
    *,
    company_id: Any,
    telegram_user_id: str,
) -> None:
    await db.execute(
        text("""
            DELETE FROM company_telegram_pending_actions
            WHERE company_id = :company_id
              AND telegram_user_id = :telegram_user_id
              AND action = 'reference_close_total'
        """),
        {"company_id": str(company_id), "telegram_user_id": str(telegram_user_id)},
    )


async def _save_reference_production_close(
    db: AsyncSession,
    *,
    company_id: Any,
    employee_id: Any,
    employee_name: str | None,
    telegram_user_id: str | None,
    reference_name: str,
    size: str,
    quantity_finished: int,
) -> None:
    await _ensure_reference_bot_storage(db)
    await db.execute(
        text("""
            INSERT INTO reference_production_closures (
                id,
                company_id,
                employee_id,
                employee_name,
                telegram_user_id,
                reference_name,
                size,
                quantity_finished,
                closed_at,
                source_channel,
                created_at
            )
            VALUES (
                :id,
                :company_id,
                :employee_id,
                :employee_name,
                :telegram_user_id,
                :reference_name,
                :size,
                :quantity_finished,
                now(),
                'telegram',
                now()
            )
        """),
        {
            "id": str(uuid4()),
            "company_id": str(company_id),
            "employee_id": str(employee_id),
            "employee_name": employee_name,
            "telegram_user_id": telegram_user_id,
            "reference_name": reference_name,
            "size": size,
            "quantity_finished": int(quantity_finished),
        },
    )


def _ref_poll_item(
    *,
    update_id: Any,
    action: str,
    message: str,
    employee: Employee,
    telegram_user_id: str,
    telegram_username: str | None,
) -> TelegramBotPollItem:
    return TelegramBotPollItem(
        update_id=update_id,
        ok=True,
        action=action,
        message=message,
        employee_id=employee.id,
        employee_name=employee.full_name,
        event_created=True,
        telegram_user_id=telegram_user_id,
        telegram_username=telegram_username,
    )


async def _send_reference_pick_list(
    db: AsyncSession,
    *,
    token: str,
    chat_id: str | None,
    company_id: Any,
    language: str,
    message_key: str,
    callback_prefix: str,
) -> bool:
    refs = await _reference_bot_options(db, company_id)

    if not refs:
        await _send_telegram_message(token, chat_id, _ref_txt(language, "no_refs"))
        return False

    await _send_telegram_message(
        token,
        chat_id,
        _ref_txt(language, message_key),
        reply_markup=_reference_options_keyboard(refs, callback_prefix),
    )
    return True


async def _handle_reference_flow(
    db: AsyncSession,
    *,
    bot: CompanyBotInstance,
    company: Any,
    employee: Employee,
    current: WorkforceAttendanceStatus | None,
    token: str,
    chat_id: str | None,
    update: dict[str, Any],
    update_id: Any,
    message: dict[str, Any] | None,
    text_value: str | None,
    command: str | None,
    telegram_user_id: str,
    username: str | None,
    language: str,
    callback_query_id: str | None,
    send_replies: bool,
) -> TelegramBotPollItem | None:
    enabled_modules = await _enabled_module_codes(db, bot.company_id)

    if not _references_enabled_from_codes(enabled_modules):
        return None

    raw = str(text_value or command or "").strip()
    raw_lower = raw.lower()
    status_key = _current_status_key(current)

    pending = await _get_pending_reference_close_total(
        db,
        company_id=bot.company_id,
        telegram_user_id=telegram_user_id,
    )

    if pending and raw and not raw_lower.startswith("clx:"):
        qty_text = raw.strip()

        if not qty_text.isdigit() or int(qty_text) < 0:
            if send_replies:
                await _send_telegram_message(token, chat_id, _ref_txt(language, "invalid_total"))
            return _ref_poll_item(
                update_id=update_id,
                action="reference_close_total_invalid",
                message="invalid_total",
                employee=employee,
                telegram_user_id=telegram_user_id,
                telegram_username=username,
            )

        payload = pending.get("payload_json") or {}

        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}

        reference_name = str(payload.get("reference_name") or "").strip()
        size = str(payload.get("size") or "").strip()
        qty = int(qty_text)

        await _save_reference_production_close(
            db,
            company_id=bot.company_id,
            employee_id=employee.id,
            employee_name=employee.full_name,
            telegram_user_id=telegram_user_id,
            reference_name=reference_name,
            size=size,
            quantity_finished=qty,
        )
        await _clear_pending_reference_close_total(
            db,
            company_id=bot.company_id,
            telegram_user_id=telegram_user_id,
        )
        await db.commit()

        msg = _ref_txt(language, "closed", name=reference_name, size=size, qty=qty)

        if send_replies:
            await _send_telegram_message(token, chat_id, msg)
            await _send_dynamic_menu(db, token=token, chat_id=chat_id, company=company, employee=employee, language=language)

        return _ref_poll_item(
            update_id=update_id,
            action="reference_production_closed",
            message=msg,
            employee=employee,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    if callback_query_id and raw_lower.startswith("clx:ref:"):
        await _answer_callback_query(token, callback_query_id)

    start_commands = {"/entrada", "/inicio", "/inicio_turno", "entrada", "inicio", "iniciar turno"}

    # Inicio de turno con References: primero referencia, luego registra entrada.
    if (str(command or "").lower() in start_commands or raw_lower in start_commands) and not raw_lower.startswith("clx:ref:start:"):
        if status_key not in {"sin_turno", "checked_out", "not_started"}:
            return None

        if send_replies:
            await _send_reference_pick_list(
                db,
                token=token,
                chat_id=chat_id,
                company_id=bot.company_id,
                language=language,
                message_key="pick_start",
                callback_prefix="clx:ref:start",
            )

        return _ref_poll_item(
            update_id=update_id,
            action="reference_start_prompt",
            message="reference_start_prompt",
            employee=employee,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    if raw_lower.startswith("clx:ref:start:"):
        reference_id = raw.split(":", 3)[3]
        ref = await _reference_by_id(db, bot.company_id, reference_id)

        if not ref:
            if send_replies:
                await _send_telegram_message(token, chat_id, _ref_txt(language, "no_refs"))
            return _ref_poll_item(
                update_id=update_id,
                action="reference_start_missing",
                message="reference_missing",
                employee=employee,
                telegram_user_id=telegram_user_id,
                telegram_username=username,
            )

        command_config = TELEGRAM_COMMANDS["/entrada"]
        created, message_text = await _create_bot_attendance_event(
            db,
            bot=bot,
            employee=employee,
            update=update,
            message=message,
            command="/entrada",
            args="",
            command_config=command_config,
            language=language,
        )

        await _open_reference_session(
            db,
            company_id=bot.company_id,
            employee_id=employee.id,
            employee_name=employee.full_name,
            telegram_user_id=telegram_user_id,
            reference_name=str(ref["name"]),
        )
        await db.commit()

        msg = _ref_txt(language, "started", name=str(ref["name"]))

        if send_replies:
            await _send_telegram_message(token, chat_id, msg)
            await _send_dynamic_menu(db, token=token, chat_id=chat_id, company=company, employee=employee, language=language)

        return _ref_poll_item(
            update_id=update_id,
            action="reference_shift_started",
            message=msg if created else message_text,
            employee=employee,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    if raw_lower in {"clx:ref:switch", "cambio referencia", "/cambio_referencia"}:
        if status_key not in {"working", "on_break"}:
            if send_replies:
                await _send_telegram_message(token, chat_id, _ref_txt(language, "must_start"))
            return _ref_poll_item(
                update_id=update_id,
                action="reference_switch_denied",
                message="must_start",
                employee=employee,
                telegram_user_id=telegram_user_id,
                telegram_username=username,
            )

        if send_replies:
            await _send_reference_pick_list(
                db,
                token=token,
                chat_id=chat_id,
                company_id=bot.company_id,
                language=language,
                message_key="pick_switch",
                callback_prefix="clx:ref:switch",
            )

        return _ref_poll_item(
            update_id=update_id,
            action="reference_switch_prompt",
            message="reference_switch_prompt",
            employee=employee,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    if raw_lower.startswith("clx:ref:switch:"):
        reference_id = raw.split(":", 3)[3]
        ref = await _reference_by_id(db, bot.company_id, reference_id)

        if not ref:
            if send_replies:
                await _send_telegram_message(token, chat_id, _ref_txt(language, "no_refs"))
            return _ref_poll_item(
                update_id=update_id,
                action="reference_switch_missing",
                message="reference_missing",
                employee=employee,
                telegram_user_id=telegram_user_id,
                telegram_username=username,
            )

        await _open_reference_session(
            db,
            company_id=bot.company_id,
            employee_id=employee.id,
            employee_name=employee.full_name,
            telegram_user_id=telegram_user_id,
            reference_name=str(ref["name"]),
        )
        await db.commit()

        msg = _ref_txt(language, "switched", name=str(ref["name"]))

        if send_replies:
            await _send_telegram_message(token, chat_id, msg)
            await _send_dynamic_menu(db, token=token, chat_id=chat_id, company=company, employee=employee, language=language)

        return _ref_poll_item(
            update_id=update_id,
            action="reference_switched",
            message=msg,
            employee=employee,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    if raw_lower in {"clx:ref:close", "cerrar referencia", "/cerrar_referencia", "cerrar produccion", "cerrar producción"}:
        if status_key not in {"working", "on_break"}:
            if send_replies:
                await _send_telegram_message(token, chat_id, _ref_txt(language, "must_start"))
            return _ref_poll_item(
                update_id=update_id,
                action="reference_close_denied",
                message="must_start",
                employee=employee,
                telegram_user_id=telegram_user_id,
                telegram_username=username,
            )

        if send_replies:
            await _send_reference_pick_list(
                db,
                token=token,
                chat_id=chat_id,
                company_id=bot.company_id,
                language=language,
                message_key="pick_close",
                callback_prefix="clx:ref:close_ref",
            )

        return _ref_poll_item(
            update_id=update_id,
            action="reference_close_prompt",
            message="reference_close_prompt",
            employee=employee,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    if raw_lower.startswith("clx:ref:close_ref:"):
        reference_id = raw.split(":", 3)[3]
        ref = await _reference_by_id(db, bot.company_id, reference_id)

        if not ref:
            if send_replies:
                await _send_telegram_message(token, chat_id, _ref_txt(language, "no_refs"))
            return _ref_poll_item(
                update_id=update_id,
                action="reference_close_missing",
                message="reference_missing",
                employee=employee,
                telegram_user_id=telegram_user_id,
                telegram_username=username,
            )

        sizes = await _reference_sizes_by_name(db, bot.company_id, str(ref["name"]))

        if send_replies:
            await _send_telegram_message(
                token,
                chat_id,
                _ref_txt(language, "pick_size"),
                reply_markup=_reference_sizes_keyboard(sizes),
            )

        return _ref_poll_item(
            update_id=update_id,
            action="reference_size_prompt",
            message="reference_size_prompt",
            employee=employee,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    if raw_lower.startswith("clx:ref:close_size:"):
        reference_id = raw.split(":", 3)[3]
        ref = await _reference_by_id(db, bot.company_id, reference_id)

        if not ref:
            if send_replies:
                await _send_telegram_message(token, chat_id, _ref_txt(language, "no_refs"))
            return _ref_poll_item(
                update_id=update_id,
                action="reference_size_missing",
                message="reference_missing",
                employee=employee,
                telegram_user_id=telegram_user_id,
                telegram_username=username,
            )

        payload = {
            "reference_id": str(ref["id"]),
            "reference_name": str(ref["name"]),
            "size": str(ref["size"]),
        }

        await _set_pending_reference_close_total(
            db,
            company_id=bot.company_id,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
            employee_id=employee.id,
            payload=payload,
        )
        await db.commit()

        msg = _ref_txt(language, "ask_total", name=str(ref["name"]), size=str(ref["size"]))

        if send_replies:
            await _send_telegram_message(token, chat_id, msg)

        return _ref_poll_item(
            update_id=update_id,
            action="reference_total_prompt",
            message=msg,
            employee=employee,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    return None

'''

marker = "def _menu_keyboard("
if marker not in src:
    raise SystemExit("No encontré def _menu_keyboard para insertar helpers REF-03A.")

src = src.replace(marker, helpers + "\n" + marker, 1)

# ---------------------------------------------------------------------
# 2) Botones References dentro del menú dinámico.
# ---------------------------------------------------------------------
if "clx:ref:switch" not in src:
    return_marker = '    return {"inline_keyboard": rows}\n'
    if return_marker not in src:
        raise SystemExit("No encontré return de _menu_keyboard.")

    injection = '''    if _references_enabled_from_codes(enabled_modules) and status_key == "working":
        rows.append([
            {"text": _ref_txt(language, "btn_switch"), "callback_data": "clx:ref:switch"},
            {"text": _ref_txt(language, "btn_close"), "callback_data": "clx:ref:close"},
        ])

'''
    src = src.replace(return_marker, injection + return_marker, 1)

# ---------------------------------------------------------------------
# 3) Interceptor antes de ejecutar TELEGRAM_COMMANDS normal.
# ---------------------------------------------------------------------
interceptor = '''    ref_flow_result = await _handle_reference_flow(
        db,
        bot=bot,
        company=company,
        employee=employee,
        current=current,
        token=token,
        chat_id=chat_id,
        update=update,
        update_id=update_id,
        message=message,
        text_value=text_value,
        command=command,
        telegram_user_id=telegram_user_id,
        username=username,
        language=language,
        callback_query_id=callback_query_id,
        send_replies=send_replies,
    )
    if ref_flow_result is not None:
        return ref_flow_result

'''

if "ref_flow_result = await _handle_reference_flow" not in src:
    target = "    command_config = TELEGRAM_COMMANDS.get(command)\n"

    if target not in src:
        target = "    if command not in TELEGRAM_COMMANDS:\n"

    if target not in src:
        raise SystemExit("No encontré punto seguro antes de TELEGRAM_COMMANDS para insertar interceptor REF-03A.")

    src = src.replace(target, interceptor + target, 1)

path.write_text(src, encoding="utf-8")
print("REF_03A_BOT_REFERENCES_FLOW_OK")
