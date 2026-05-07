from pathlib import Path
import re

path = Path("app/api/v1/endpoints/bots.py")
text = path.read_text(encoding="utf-8-sig")

def must_replace(old: str, new: str, label: str) -> None:
    global text
    if old not in text:
        raise SystemExit(f"No encontré bloque para: {label}")
    text = text.replace(old, new, 1)

# Ensure json import
if "import json\n" not in text:
    if "from __future__ import annotations\n" in text:
        text = text.replace("from __future__ import annotations\n", "from __future__ import annotations\nimport json\n", 1)
    else:
        text = "import json\n" + text

# Make _txt fallback to Spanish/default if a key is missing in EN/FR
old_txt = '''def _txt(language: str | None, key: str, **kwargs: Any) -> str:
    lang = _lang(language)
    template = BOT_TEXTS.get(lang, BOT_TEXTS[DEFAULT_LANGUAGE]).get(key, key)
    return template.format(**kwargs)
'''
new_txt = '''def _txt(language: str | None, key: str, **kwargs: Any) -> str:
    lang = _lang(language)
    template = BOT_TEXTS.get(lang, BOT_TEXTS[DEFAULT_LANGUAGE]).get(key)
    if template is None:
        template = BOT_TEXTS[DEFAULT_LANGUAGE].get(key, key)
    return template.format(**kwargs)
'''
if old_txt in text:
    text = text.replace(old_txt, new_txt, 1)

# Add Spanish text keys. EN/FR fallback to default if not present.
if '"end_shift_summary_prompt"' not in text:
    must_replace(
        '        "shift_ended": "🏁 Turno finalizado.",\n',
        '        "shift_ended": "🏁 Turno finalizado.",\n'
        '        "end_shift_summary_prompt": "🏁 Para finalizar turno, por favor resume tu gestión de hoy.\\n\\nEscribe tu resumen en un solo mensaje.",\n'
        '        "end_shift_summary_saved": "📝 Resumen de gestión guardado en el cierre de jornada.",\n'
        '        "end_shift_summary_required": "Para cerrar la jornada necesito tu resumen de gestión de hoy.",\n',
        "BOT_TEXTS end shift summary"
    )

# Insert pending end-shift helpers before material storage helpers.
helpers_marker = "\n\nasync def _ensure_material_requests_storage(db: AsyncSession) -> None:\n"
helpers = r'''

async def _set_pending_end_shift_summary(
    db: AsyncSession,
    *,
    company_id: UUID,
    telegram_user_id: str,
    telegram_username: str | None,
    employee_id: UUID,
    chat_id: str | None,
    language: str,
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
                'end_shift_summary',
                CAST(:payload_json AS jsonb),
                now() + interval '90 minutes',
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
            "payload_json": json.dumps(
                {
                    "chat_id": chat_id,
                    "language": _lang(language),
                    "reason": "end_shift_summary_required",
                }
            ),
        },
    )


async def _get_pending_end_shift_summary(
    db: AsyncSession,
    *,
    company_id: UUID,
    telegram_user_id: str,
) -> dict[str, Any] | None:
    await ensure_bot_storage(db)
    result = await db.execute(
        text("""
            SELECT id, employee_id, payload_json, expires_at
            FROM company_telegram_pending_actions
            WHERE company_id = :company_id
              AND telegram_user_id = :telegram_user_id
              AND action = 'end_shift_summary'
              AND (expires_at IS NULL OR expires_at > now())
            ORDER BY updated_at DESC
            LIMIT 1
        """),
        {"company_id": str(company_id), "telegram_user_id": str(telegram_user_id)},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def _clear_pending_end_shift_summary(
    db: AsyncSession,
    *,
    company_id: UUID,
    telegram_user_id: str,
) -> None:
    await db.execute(
        text("""
            DELETE FROM company_telegram_pending_actions
            WHERE company_id = :company_id
              AND telegram_user_id = :telegram_user_id
              AND action = 'end_shift_summary'
        """),
        {"company_id": str(company_id), "telegram_user_id": str(telegram_user_id)},
    )


async def _process_end_shift_summary_text(
    db: AsyncSession,
    *,
    bot: CompanyBotInstance,
    token: str,
    update: dict[str, Any],
    message: dict[str, Any],
    telegram_user_id: str,
    username: str | None,
    chat_id: str | None,
    text_value: str,
    language: str,
    send_replies: bool,
) -> TelegramBotPollItem | None:
    pending = await _get_pending_end_shift_summary(
        db,
        company_id=bot.company_id,
        telegram_user_id=telegram_user_id,
    )
    if pending is None:
        return None

    summary = (text_value or "").strip()

    if not summary or summary.startswith("/") or summary.startswith("clx:"):
        if send_replies:
            await _send_telegram_message(token, chat_id, _txt(language, "end_shift_summary_prompt"))
        return TelegramBotPollItem(
            update_id=update.get("update_id"),
            ok=False,
            action="end_shift_summary_required",
            message=_txt(language, "end_shift_summary_required"),
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    employee = None
    pending_employee_id = pending.get("employee_id")
    if pending_employee_id:
        try:
            employee = await db.get(Employee, UUID(str(pending_employee_id)))
        except Exception:
            employee = None

    if employee is None:
        employee = await _find_employee_by_telegram(db, bot.company_id, telegram_user_id, username)

    employee_status = str(getattr(employee, "status", "") or "").lower() if employee is not None else ""
    if employee is None or str(employee.company_id) != str(bot.company_id) or employee_status not in {"active", "activo"}:
        await _clear_pending_end_shift_summary(
            db,
            company_id=bot.company_id,
            telegram_user_id=telegram_user_id,
        )
        await db.commit()
        if send_replies:
            await _send_telegram_message(
                token,
                chat_id,
                _txt(language, "not_linked", telegram_user_id=telegram_user_id),
                reply_markup=_language_keyboard(),
            )
        return TelegramBotPollItem(
            update_id=update.get("update_id"),
            ok=False,
            action="not_linked",
            message="Empleado no vinculado.",
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

    command_config = TELEGRAM_COMMANDS["/salida"]
    created, message_text = await _create_bot_attendance_event(
        db,
        bot=bot,
        employee=employee,
        update=update,
        message=message,
        command="/salida",
        args=summary,
        command_config=command_config,
        language=language,
    )

    await _clear_pending_end_shift_summary(
        db,
        company_id=bot.company_id,
        telegram_user_id=telegram_user_id,
    )
    await db.commit()

    if send_replies:
        company = await ensure_company_exists(db, bot.company_id)
        await _send_telegram_message(
            token,
            chat_id,
            f"{message_text}\n\n{_txt(language, 'end_shift_summary_saved')}",
        )
        await _send_dynamic_menu(
            db,
            token=token,
            chat_id=chat_id,
            company=company,
            employee=employee,
            language=language,
        )

    return TelegramBotPollItem(
        update_id=update.get("update_id"),
        ok=created,
        action="check_out",
        message=message_text,
        employee_id=employee.id,
        employee_name=employee.full_name,
        event_created=created,
        telegram_user_id=telegram_user_id,
        telegram_username=username,
    )
'''

if helpers_marker not in text:
    raise SystemExit("No encontré marcador para insertar helpers end_shift_summary.")

if "_set_pending_end_shift_summary" not in text:
    text = text.replace(helpers_marker, helpers + helpers_marker, 1)

# Process pending summary text before material text.
old_pending_block = '''    if command and not command.startswith("/") and telegram_user_id:
        pending_material = await _get_pending_material_request(db, company_id=bot.company_id, telegram_user_id=telegram_user_id)
'''
new_pending_block = '''    if command and not command.startswith("/") and telegram_user_id:
        end_shift_summary_result = await _process_end_shift_summary_text(
            db,
            bot=bot,
            token=token,
            update=update,
            message=message,
            telegram_user_id=telegram_user_id,
            username=username,
            chat_id=chat_id,
            text_value=text_value,
            language=language,
            send_replies=send_replies,
        )
        if end_shift_summary_result is not None:
            return end_shift_summary_result

        pending_material = await _get_pending_material_request(db, company_id=bot.company_id, telegram_user_id=telegram_user_id)
'''
if old_pending_block in text and "_process_end_shift_summary_text(\n            db," not in text:
    text = text.replace(old_pending_block, new_pending_block, 1)

# Require summary before creating /salida event when command has no args.
main_create_block = '''    created, message_text = await _create_bot_attendance_event(
        db,
        bot=bot,
        employee=employee,
        update=update,
        message=message,
        command=command,
        args=args,
        command_config=command_config,
        language=language,
    )
    await db.commit()
'''
summary_gate = '''    if command_config.get("turn_action") == "end_shift" and not args:
        await _set_pending_end_shift_summary(
            db,
            company_id=bot.company_id,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
            employee_id=employee.id,
            chat_id=chat_id,
            language=language,
        )
        await db.commit()

        if callback_query_id:
            await _answer_callback_query(token, callback_query_id, _txt(language, "end_shift_summary_required"))

        if send_replies:
            await _send_telegram_message(token, chat_id, _txt(language, "end_shift_summary_prompt"))

        return TelegramBotPollItem(
            update_id=update_id,
            ok=True,
            action="end_shift_summary_requested",
            message=_txt(language, "end_shift_summary_required"),
            employee_id=employee.id,
            employee_name=employee.full_name,
            event_created=False,
            telegram_user_id=telegram_user_id,
            telegram_username=username,
        )

'''
if main_create_block not in text:
    raise SystemExit("No encontré bloque principal de creación de evento para insertar gate de resumen.")

if "action=\"end_shift_summary_requested\"" not in text:
    text = text.replace(main_create_block, summary_gate + main_create_block, 1)

path.write_text(text, encoding="utf-8")
print("PATCH_OK: end shift summary required before closing jornada")
