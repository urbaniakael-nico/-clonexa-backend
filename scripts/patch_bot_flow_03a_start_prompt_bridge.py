from pathlib import Path

path = Path("app/api/v1/endpoints/bots.py")
src = path.read_text(encoding="utf-8-sig")

if "BOT_FLOW_03A_START_PROMPT_BRIDGE" in src:
    print("BOT_FLOW_03A already applied")
    raise SystemExit(0)

marker = "def _menu_keyboard("
if marker not in src:
    raise SystemExit("No encontré def _menu_keyboard.")

helper = r'''

# CLONEXA BOT_FLOW_03A_START_PROMPT_BRIDGE
async def _tenant_flow_enabled_codes_sql(db: AsyncSession, company_id: str) -> set[str]:
    result = await db.execute(
        text("""
            SELECT lower(m.code) AS code
            FROM company_modules cm
            JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id::text = :company_id
              AND cm.enabled IS TRUE
              AND m.is_active IS TRUE
        """),
        {"company_id": str(company_id)},
    )
    return {str(row[0]).lower() for row in result.all()}


async def _tenant_flow_start_prompt_bridge(
    db: AsyncSession,
    *,
    bot: CompanyBotInstance,
    employee: Employee,
    current: WorkforceAttendanceStatus | None,
    token: str,
    chat_id: str | None,
    update: dict[str, Any],
    text_value: str | None,
    command: str | None,
    telegram_user_id: str,
    username: str | None,
    language: str,
    send_replies: bool,
) -> TelegramBotPollItem | None:
    raw = str(text_value or command or "").strip().lower()

    if raw not in {"clx:cmd:entrada", "/entrada", "/inicio", "/inicio_turno", "entrada", "inicio", "iniciar turno"}:
        return None

    status_key = _current_status_key(current)

    if status_key not in {"sin_turno", "not_started", "checked_out"}:
        return None

    company_id_value = str(bot.company_id)
    employee_id_value = str(employee.id)
    employee_name_value = str(employee.full_name or "")

    enabled_modules = await _tenant_flow_enabled_codes_sql(db, company_id_value)

    if not {"references", "ref", "referencias"}.intersection(enabled_modules):
        return None

    from app.services.bot_flows.base import BotFlowContext
    from app.services.bot_flow_resolver import bot_flow_resolver

    ctx = BotFlowContext(
        company_id=company_id_value,
        employee_id=employee_id_value,
        employee_name=employee_name_value,
        telegram_user_id=str(telegram_user_id),
        telegram_username=username,
        language=language,
        status_key="sin_turno",
        enabled_modules=enabled_modules,
    )

    result = await bot_flow_resolver.handle(
        db,
        ctx,
        {
            "text": "clx:cmd:entrada",
            "source": "telegram_bridge_start_prompt",
        },
    )

    if not result.handled:
        return None

    if send_replies and result.reply_text:
        await _send_telegram_message(
            token,
            chat_id,
            result.reply_text,
            reply_markup=result.reply_markup,
        )

    return TelegramBotPollItem(
        update_id=update.get("update_id"),
        ok=result.ok,
        action=result.action or "tenant_flow_start_prompt",
        message=result.reply_text or result.message or "",
        employee_id=employee_id_value,
        employee_name=employee_name_value,
        event_created=False,
        telegram_user_id=telegram_user_id,
        telegram_username=username,
    )

'''

src = src.replace(marker, helper + "\n" + marker, 1)

target = "    command_config = TELEGRAM_COMMANDS.get(command)\n"
if target not in src:
    raise SystemExit("No encontré command_config = TELEGRAM_COMMANDS.get(command).")

interceptor = '''    tenant_flow_start_prompt_result = await _tenant_flow_start_prompt_bridge(
        db,
        bot=bot,
        employee=employee,
        current=current,
        token=token,
        chat_id=chat_id,
        update=update,
        text_value=text_value,
        command=command,
        telegram_user_id=telegram_user_id,
        username=username,
        language=language,
        send_replies=send_replies,
    )
    if tenant_flow_start_prompt_result is not None:
        return tenant_flow_start_prompt_result

'''

src = src.replace(target, interceptor + target, 1)

path.write_text(src, encoding="utf-8")
print("BOT_FLOW_03A_START_PROMPT_BRIDGE_OK")
