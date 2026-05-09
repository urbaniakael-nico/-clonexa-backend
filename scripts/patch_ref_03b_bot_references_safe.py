from pathlib import Path
import re

path = Path("app/api/v1/endpoints/bots.py")
src = path.read_text(encoding="utf-8-sig")

if "REF_03B_BOT_REFERENCES_SAFE_INTEGRATION" in src:
    print("REF_03B already applied")
    raise SystemExit(0)

if "import json" not in src:
    src = src.replace("import asyncio\n", "import asyncio\nimport json\n", 1)

helpers = r'''

# CLONEXA REF_03B_BOT_REFERENCES_SAFE_INTEGRATION
def _ref_enabled(enabled_modules):
    codes = {str(code or "").strip().lower() for code in (enabled_modules or [])}
    return bool(codes.intersection({"references", "ref", "referencias"}))


def _ref_txt(language, key, **kwargs):
    lang = _lang(language)
    texts = {
        "es": {
            "pick_start": "🧵 Selecciona la referencia para iniciar turno.",
            "pick_switch": "🔁 Selecciona la nueva referencia.",
            "pick_close": "✅ Selecciona la referencia que vas a cerrar.",
            "pick_size": "📏 Selecciona la talla.",
            "ask_total": "🔢 Escribe el total terminado para {name} / talla {size}.",
            "no_refs": "No hay referencias activas para bot.",
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
            "pick_switch": "🔁 Select the new reference.",
            "pick_close": "✅ Select the reference to close.",
            "pick_size": "📏 Select size.",
            "ask_total": "🔢 Type the finished total for {name} / size {size}.",
            "no_refs": "There are no bot-active references.",
            "started": "✅ Shift started on reference: {name}.",
            "switched": "🔁 Reference change saved: {name}.",
            "closed": "✅ Production closed: {name} / {size} / total {qty}.",
            "invalid_total": "Type only the finished total number.",
            "must_start": "You must start your shift first.",
            "btn_switch": "🔁 Change reference",
            "btn_close": "✅ Close reference",
        },
        "fr": {
            "pick_start": "🧵 Sélectionnez la référence pour commencer.",
            "pick_switch": "🔁 Sélectionnez la nouvelle référence.",
            "pick_close": "✅ Sélectionnez la référence à clôturer.",
            "pick_size": "📏 Sélectionnez la taille.",
            "ask_total": "🔢 Écrivez le total terminé pour {name} / taille {size}.",
            "no_refs": "Aucune référence active dans le bot.",
            "started": "✅ Service démarré sur la référence : {name}.",
            "switched": "🔁 Changement de référence enregistré : {name}.",
            "closed": "✅ Production clôturée : {name} / {size} / total {qty}.",
            "invalid_total": "Écrivez seulement le nombre total terminé.",
            "must_start": "Vous devez d’abord commencer le service.",
            "btn_switch": "🔁 Changer référence",
            "btn_close": "✅ Clôturer référence",
        },
    }
    template = texts.get(lang, texts["es"]).get(key, key)
    return template.format(**kwargs)


async def _ref_ensure_storage(db):
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


async def _ref_options(db, company_id):
    result = await db.execute(
        text("""
            SELECT min(id) AS id, name, count(*) AS sizes_count
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


async def _ref_by_id(db, company_id, reference_id):
    result = await db.execute(
        text("""
            SELECT id, name, size
            FROM product_references
            WHERE company_id = :company_id
              AND id = :reference_id
              AND bot_active IS TRUE
            LIMIT 1
        """),
        {"company_id": str(company_id), "reference_id": str(reference_id)},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def _ref_sizes_by_name(db, company_id, name):
    result = await db.execute(
        text("""
            SELECT id, name, size
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


def _ref_keyboard(items, prefix):
    rows = []
    for item in items:
        name = str(item.get("name") or "").strip()
        ref_id = str(item.get("id") or "").strip()
        if name and ref_id:
            rows.append([{"text": name[:60], "callback_data": f"{prefix}:{ref_id}"}])
    return {"inline_keyboard": rows}


def _ref_size_keyboard(items):
    rows = []
    for item in items:
        size = str(item.get("size") or "").strip()
        ref_id = str(item.get("id") or "").strip()
        if size and ref_id:
            rows.append([{"text": size[:60], "callback_data": f"clx:ref:close_size:{ref_id}"}])
    return {"inline_keyboard": rows}


async def _ref_close_active_session(db, company_id, employee_id, status):
    await _ref_ensure_storage(db)
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
        {"company_id": str(company_id), "employee_id": str(employee_id), "status": status},
    )


async def _ref_open_session(db, company_id, employee_id, employee_name, telegram_user_id, reference_id, reference_name, close_status):
    await _ref_close_active_session(db, company_id, employee_id, close_status)

    await db.execute(
        text("""
            INSERT INTO reference_work_sessions (
                id, company_id, employee_id, employee_name, telegram_user_id,
                reference_id, reference_name, started_at, status, source_channel,
                created_at, updated_at
            )
            VALUES (
                gen_random_uuid()::text, :company_id, :employee_id, :employee_name,
                :telegram_user_id, :reference_id, :reference_name, now(), 'active',
                'telegram', now(), now()
            )
        """),
        {
            "company_id": str(company_id),
            "employee_id": str(employee_id),
            "employee_name": employee_name,
            "telegram_user_id": telegram_user_id,
            "reference_id": reference_id,
            "reference_name": reference_name,
        },
    )


async def _ref_set_pending_total(db, company_id, telegram_user_id, telegram_username, employee_id, payload):
    await ensure_bot_storage(db)
    await db.execute(
        text("""
            INSERT INTO company_telegram_pending_actions (
                company_id, telegram_user_id, telegram_username, employee_id,
                action, payload_json, expires_at, updated_at
            )
            VALUES (
                :company_id, :telegram_user_id, :telegram_username, :employee_id,
                'reference_close_total', CAST(:payload_json AS jsonb),
                now() + interval '45 minutes', now()
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


async def _ref_get_pending_total(db, company_id, telegram_user_id):
    await ensure_bot_storage(db)
    result = await db.execute(
        text("""
            SELECT id, employee_id, payload_json
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


async def _ref_clear_pending_total(db, company_id, telegram_user_id):
    await db.execute(
        text("""
            DELETE FROM company_telegram_pending_actions
            WHERE company_id = :company_id
              AND telegram_user_id = :telegram_user_id
              AND action = 'reference_close_total'
        """),
        {"company_id": str(company_id), "telegram_user_id": str(telegram_user_id)},
    )


async def _ref_save_production_close(db, company_id, employee_id, employee_name, telegram_user_id, reference_id, reference_name, size, quantity_finished):
    await _ref_ensure_storage(db)
    await db.execute(
        text("""
            INSERT INTO reference_production_closures (
                id, company_id, employee_id, employee_name, telegram_user_id,
                reference_id, reference_name, size, quantity_finished,
                closed_at, source_channel, created_at
            )
            VALUES (
                gen_random_uuid()::text, :company_id, :employee_id, :employee_name,
                :telegram_user_id, :reference_id, :reference_name, :size,
                :quantity_finished, now(), 'telegram', now()
            )
        """),
        {
            "company_id": str(company_id),
            "employee_id": str(employee_id),
            "employee_name": employee_name,
            "telegram_user_id": telegram_user_id,
            "reference_id": reference_id,
            "reference_name": reference_name,
            "size": size,
            "quantity_finished": int(quantity_finished),
        },
    )


def _ref_poll_item(update_id, ok, action, message, employee_id, employee_name, telegram_user_id, telegram_username, event_created=True):
    return TelegramBotPollItem(
        update_id=update_id,
        ok=ok,
        action=action,
        message=message,
        employee_id=employee_id,
        employee_name=employee_name,
        event_created=event_created,
        telegram_user_id=telegram_user_id,
        telegram_username=telegram_username,
    )


async def _ref_send_pick_list(db, token, chat_id, company_id, language, message_key, prefix):
    refs = await _ref_options(db, company_id)
    if not refs:
        await _send_telegram_message(token, chat_id, _ref_txt(language, "no_refs"))
        return False

    await _send_telegram_message(
        token,
        chat_id,
        _ref_txt(language, message_key),
        reply_markup=_ref_keyboard(refs, prefix),
    )
    return True


async def _ref_send_menu(db, token, chat_id, company_id, employee_id, language, enabled_modules, status_key):
    rows = []

    if status_key in {"not_started", "checked_out"}:
        status_key = "sin_turno"

    if status_key == "sin_turno":
        rows.append([{"text": _txt(language, "btn_start_shift"), "callback_data": "clx:cmd:entrada"}])
        rows.append([{"text": _txt(language, "btn_language"), "callback_data": "clx:language"}])
    elif status_key == "on_break":
        rows.append([
            {"text": _txt(language, "btn_resume"), "callback_data": "clx:cmd:reanudar"},
            {"text": _txt(language, "btn_end_shift"), "callback_data": "clx:cmd:salida"},
        ])
        rows.append([{"text": _txt(language, "btn_language"), "callback_data": "clx:language"}])
    else:
        rows.append([
            {"text": _txt(language, "btn_break"), "callback_data": "clx:cmd:pausa"},
            {"text": _txt(language, "btn_end_shift"), "callback_data": "clx:cmd:salida"},
        ])
        if _ref_enabled(enabled_modules):
            rows.append([
                {"text": _ref_txt(language, "btn_switch"), "callback_data": "clx:ref:switch"},
                {"text": _ref_txt(language, "btn_close"), "callback_data": "clx:ref:close"},
            ])
        rows.append([{"text": _txt(language, "btn_language"), "callback_data": "clx:language"}])

    await _send_telegram_message(
        token,
        chat_id,
        _txt(language, "menu_next"),
        reply_markup={"inline_keyboard": rows},
    )


async def _ref_handle_bot_flow(
    db,
    *,
    bot,
    employee,
    current,
    token,
    chat_id,
    update,
    message,
    text_value,
    command,
    telegram_user_id,
    username,
    language,
    callback_query_id,
    send_replies,
):
    company_id_value = str(bot.company_id)
    employee_id_value = str(employee.id)
    employee_name_value = str(employee.full_name or "")
    status_key = _current_status_key(current)
    enabled_modules = await _enabled_module_codes(db, bot.company_id)

    if not _ref_enabled(enabled_modules):
        return None

    update_id = update.get("update_id")
    raw = str(text_value or command or "").strip()
    raw_lower = raw.lower()
    command_lower = str(command or "").lower()

    pending = await _ref_get_pending_total(db, company_id_value, telegram_user_id)

    if pending and raw and not raw.startswith("/") and not raw_lower.startswith("clx:"):
        qty_text = raw.strip()

        if not qty_text.isdigit() or int(qty_text) < 0:
            if send_replies:
                await _send_telegram_message(token, chat_id, _ref_txt(language, "invalid_total"))
            return _ref_poll_item(update_id, False, "reference_close_total_invalid", "invalid_total", employee_id_value, employee_name_value, telegram_user_id, username, False)

        payload = pending.get("payload_json") or {}
        if isinstance(payload, str):
            payload = json.loads(payload)

        qty = int(qty_text)
        reference_id = str(payload.get("reference_id") or "")
        reference_name = str(payload.get("reference_name") or "")
        size = str(payload.get("size") or "")

        await _ref_save_production_close(db, company_id_value, employee_id_value, employee_name_value, telegram_user_id, reference_id, reference_name, size, qty)
        await _ref_clear_pending_total(db, company_id_value, telegram_user_id)
        await db.commit()

        msg = _ref_txt(language, "closed", name=reference_name, size=size, qty=qty)
        if send_replies:
            await _send_telegram_message(token, chat_id, msg)
            await _ref_send_menu(db, token, chat_id, company_id_value, employee_id_value, language, enabled_modules, status_key)

        return _ref_poll_item(update_id, True, "reference_production_closed", msg, employee_id_value, employee_name_value, telegram_user_id, username)

    if callback_query_id and raw_lower.startswith("clx:ref:"):
        await _answer_callback_query(token, callback_query_id)

    start_commands = {"/entrada", "/inicio", "/inicio_turno", "entrada", "inicio", "iniciar turno", "clx:cmd:entrada"}
    end_commands = {"/salida", "/finalizar", "/finalizar_turno", "salida", "finalizar", "finalizar turno", "clx:cmd:salida"}

    if command_lower in start_commands or raw_lower in start_commands:
        if status_key in {"working", "on_break"}:
            return None

        if send_replies:
            await _ref_send_pick_list(db, token, chat_id, company_id_value, language, "pick_start", "clx:ref:start")

        return _ref_poll_item(update_id, True, "reference_start_prompt", "reference_start_prompt", employee_id_value, employee_name_value, telegram_user_id, username, False)

    if raw_lower.startswith("clx:ref:start:"):
        reference_id = raw.split(":", 3)[3]
        ref = await _ref_by_id(db, company_id_value, reference_id)

        if not ref:
            if send_replies:
                await _send_telegram_message(token, chat_id, _ref_txt(language, "no_refs"))
            return _ref_poll_item(update_id, False, "reference_start_missing", "reference_missing", employee_id_value, employee_name_value, telegram_user_id, username, False)

        created, message_text = await _create_bot_attendance_event(
            db,
            bot=bot,
            employee=employee,
            update=update,
            message=message,
            command="/entrada",
            args="",
            command_config=TELEGRAM_COMMANDS["/entrada"],
            language=language,
        )

        await _ref_open_session(db, company_id_value, employee_id_value, employee_name_value, telegram_user_id, str(ref["id"]), str(ref["name"]), "closed_by_new_start")
        await db.commit()

        msg = _ref_txt(language, "started", name=str(ref["name"]))
        if send_replies:
            await _send_telegram_message(token, chat_id, msg)
            await _ref_send_menu(db, token, chat_id, company_id_value, employee_id_value, language, enabled_modules, "working")

        return _ref_poll_item(update_id, created, "reference_shift_started", msg if created else message_text, employee_id_value, employee_name_value, telegram_user_id, username)

    if raw_lower in {"clx:ref:switch", "cambio referencia", "/cambio_referencia"}:
        if status_key not in {"working", "on_break"}:
            if send_replies:
                await _send_telegram_message(token, chat_id, _ref_txt(language, "must_start"))
            return _ref_poll_item(update_id, False, "reference_switch_denied", "must_start", employee_id_value, employee_name_value, telegram_user_id, username, False)

        if send_replies:
            await _ref_send_pick_list(db, token, chat_id, company_id_value, language, "pick_switch", "clx:ref:switch")

        return _ref_poll_item(update_id, True, "reference_switch_prompt", "reference_switch_prompt", employee_id_value, employee_name_value, telegram_user_id, username, False)

    if raw_lower.startswith("clx:ref:switch:"):
        reference_id = raw.split(":", 3)[3]
        ref = await _ref_by_id(db, company_id_value, reference_id)

        if not ref:
            if send_replies:
                await _send_telegram_message(token, chat_id, _ref_txt(language, "no_refs"))
            return _ref_poll_item(update_id, False, "reference_switch_missing", "reference_missing", employee_id_value, employee_name_value, telegram_user_id, username, False)

        await _ref_open_session(db, company_id_value, employee_id_value, employee_name_value, telegram_user_id, str(ref["id"]), str(ref["name"]), "switched")
        await db.commit()

        msg = _ref_txt(language, "switched", name=str(ref["name"]))
        if send_replies:
            await _send_telegram_message(token, chat_id, msg)
            await _ref_send_menu(db, token, chat_id, company_id_value, employee_id_value, language, enabled_modules, status_key)

        return _ref_poll_item(update_id, True, "reference_switched", msg, employee_id_value, employee_name_value, telegram_user_id, username)

    if raw_lower in {"clx:ref:close", "cerrar referencia", "/cerrar_referencia", "cerrar produccion", "cerrar producción"}:
        if status_key not in {"working", "on_break"}:
            if send_replies:
                await _send_telegram_message(token, chat_id, _ref_txt(language, "must_start"))
            return _ref_poll_item(update_id, False, "reference_close_denied", "must_start", employee_id_value, employee_name_value, telegram_user_id, username, False)

        if send_replies:
            await _ref_send_pick_list(db, token, chat_id, company_id_value, language, "pick_close", "clx:ref:close_ref")

        return _ref_poll_item(update_id, True, "reference_close_prompt", "reference_close_prompt", employee_id_value, employee_name_value, telegram_user_id, username, False)

    if raw_lower.startswith("clx:ref:close_ref:"):
        reference_id = raw.split(":", 3)[3]
        ref = await _ref_by_id(db, company_id_value, reference_id)

        if not ref:
            if send_replies:
                await _send_telegram_message(token, chat_id, _ref_txt(language, "no_refs"))
            return _ref_poll_item(update_id, False, "reference_close_missing", "reference_missing", employee_id_value, employee_name_value, telegram_user_id, username, False)

        sizes = await _ref_sizes_by_name(db, company_id_value, str(ref["name"]))

        if send_replies:
            await _send_telegram_message(token, chat_id, _ref_txt(language, "pick_size"), reply_markup=_ref_size_keyboard(sizes))

        return _ref_poll_item(update_id, True, "reference_size_prompt", "reference_size_prompt", employee_id_value, employee_name_value, telegram_user_id, username, False)

    if raw_lower.startswith("clx:ref:close_size:"):
        reference_id = raw.split(":", 3)[3]
        ref = await _ref_by_id(db, company_id_value, reference_id)

        if not ref:
            if send_replies:
                await _send_telegram_message(token, chat_id, _ref_txt(language, "no_refs"))
            return _ref_poll_item(update_id, False, "reference_size_missing", "reference_missing", employee_id_value, employee_name_value, telegram_user_id, username, False)

        await _ref_set_pending_total(
            db,
            company_id_value,
            telegram_user_id,
            username,
            employee_id_value,
            {"reference_id": str(ref["id"]), "reference_name": str(ref["name"]), "size": str(ref["size"])},
        )
        await db.commit()

        msg = _ref_txt(language, "ask_total", name=str(ref["name"]), size=str(ref["size"]))
        if send_replies:
            await _send_telegram_message(token, chat_id, msg)

        return _ref_poll_item(update_id, True, "reference_total_prompt", msg, employee_id_value, employee_name_value, telegram_user_id, username, False)

    if command_lower in end_commands or raw_lower in end_commands:
        if status_key not in {"working", "on_break"}:
            return None

        created, message_text = await _create_bot_attendance_event(
            db,
            bot=bot,
            employee=employee,
            update=update,
            message=message,
            command="/salida",
            args="",
            command_config=TELEGRAM_COMMANDS["/salida"],
            language=language,
        )

        await _ref_close_active_session(db, company_id_value, employee_id_value, "ended_with_shift")
        await _ref_clear_pending_total(db, company_id_value, telegram_user_id)
        await db.commit()

        msg = _txt(language, "shift_ended")
        if send_replies:
            await _send_telegram_message(token, chat_id, msg)
            await _ref_send_menu(db, token, chat_id, company_id_value, employee_id_value, language, enabled_modules, "sin_turno")

        return _ref_poll_item(update_id, created, "check_out", msg if created else message_text, employee_id_value, employee_name_value, telegram_user_id, username)

    return None

'''

marker = "def _menu_keyboard("
if marker not in src:
    raise SystemExit("No encontré def _menu_keyboard.")

src = src.replace(marker, helpers + "\n" + marker, 1)

target = "    command_config = TELEGRAM_COMMANDS.get(command)\n"
if target not in src:
    raise SystemExit("No encontré command_config = TELEGRAM_COMMANDS.get(command).")

interceptor = '''    ref_flow_result = await _ref_handle_bot_flow(
        db,
        bot=bot,
        employee=employee,
        current=current,
        token=token,
        chat_id=chat_id,
        update=update,
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

src = src.replace(target, interceptor + target, 1)

path.write_text(src, encoding="utf-8")
print("REF_03B_BOT_REFERENCES_SAFE_INTEGRATION_OK")
