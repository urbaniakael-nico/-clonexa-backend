from pathlib import Path

path = Path("app/api/v1/endpoints/bots.py")
src = path.read_text(encoding="utf-8-sig")

if "BOT_FLOW_03A_SQL_ONLY_BRIDGE" in src:
    print("BOT_FLOW_03A_SQL_ONLY already applied")
    raise SystemExit(0)

marker = "def _menu_keyboard("
if marker not in src:
    raise SystemExit("No encontré def _menu_keyboard.")

helper = r'''

# CLONEXA BOT_FLOW_03A_SQL_ONLY_BRIDGE
async def _tenant_flow_company_id_from_bot_identity_sql(db: AsyncSession, bot_obj: Any) -> str:
    """
    SQL-only bridge:
    - NO lee bot.company_id
    - NO lee bot.id
    - usa identidad SQLAlchemy del objeto y luego consulta SQL plano.
    """
    try:
        from sqlalchemy import inspect as sa_inspect

        identity = sa_inspect(bot_obj).identity
        if not identity:
            return ""

        bot_instance_id = str(identity[0])

        result = await db.execute(
            text("""
                SELECT company_id::text AS company_id
                FROM company_bot_instances
                WHERE id::text = :bot_instance_id
                LIMIT 1
            """),
            {"bot_instance_id": bot_instance_id},
        )

        row = result.mappings().first()
        return str(row["company_id"] or "") if row else ""

    except Exception:
        return ""


async def _tenant_flow_employee_by_telegram_sql(
    db: AsyncSession,
    *,
    company_id: str,
    telegram_user_id: str,
) -> dict[str, str] | None:
    result = await db.execute(
        text("""
            SELECT
                id::text AS employee_id,
                COALESCE(full_name, '') AS employee_name
            FROM employees
            WHERE company_id::text = :company_id
              AND telegram_user_id::text = :telegram_user_id
              AND lower(COALESCE(status, 'active')) IN ('active', 'activo')
            LIMIT 1
        """),
        {
            "company_id": str(company_id),
            "telegram_user_id": str(telegram_user_id),
        },
    )

    row = result.mappings().first()

    if not row:
        return None

    return {
        "employee_id": str(row["employee_id"] or ""),
        "employee_name": str(row["employee_name"] or ""),
    }


async def _tenant_flow_status_sql(
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
            "company_id": str(company_id),
            "employee_id": str(employee_id),
        },
    )

    row = result.mappings().first()

    if not row:
        return "sin_turno"

    raw = str(row["status"] or "sin_turno").strip().lower()

    if raw in {"checked_out", "not_started"}:
        return "sin_turno"

    return raw


async def _tenant_flow_enabled_codes_sql(db: AsyncSession, company_id: str) -> set[str]:
    result = await db.execute(
        text("""
            SELECT lower(m.code) AS code
            FROM company_modules cm
            JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id::text = :company_id
              AND COALESCE(cm.enabled, true) IS TRUE
              AND COALESCE(m.is_active, true) IS TRUE
        """),
        {"company_id": str(company_id)},
    )

    return {str(row[0]).lower() for row in result.all()}


async def _tenant_flow_start_prompt_sql_only_bridge(
    db: AsyncSession,
    *,
    bot: CompanyBotInstance,
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

    if raw not in {
        "clx:cmd:entrada",
        "/entrada",
        "/inicio",
        "/inicio_turno",
        "entrada",
        "inicio",
        "iniciar turno",
    }:
        return None

    company_id_value = await _tenant_flow_company_id_from_bot_identity_sql(db, bot)

    if not company_id_value:
        return None

    enabled_modules = await _tenant_flow_enabled_codes_sql(db, company_id_value)

    if not {"references", "ref", "referencias"}.intersection(enabled_modules):
        return None

    employee_row = await _tenant_flow_employee_by_telegram_sql(
        db,
        company_id=company_id_value,
        telegram_user_id=telegram_user_id,
    )

    if not employee_row:
        return None

    employee_id_value = employee_row["employee_id"]
    employee_name_value = employee_row["employee_name"]

    status_key = await _tenant_flow_status_sql(
        db,
        company_id=company_id_value,
        employee_id=employee_id_value,
    )

    if status_key in {"working", "on_break"}:
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
            "source": "telegram_sql_only_start_prompt",
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

target = '''    if command and not command.startswith("/") and telegram_user_id:
        pending_material = await _get_pending_material_request(db,
'''

if target not in src:
    raise SystemExit("No encontré bloque pending_material. No inserto puente.")

interceptor = '''    tenant_flow_start_prompt_result = await _tenant_flow_start_prompt_sql_only_bridge(
        db,
        bot=bot,
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

print("BOT_FLOW_03A_SQL_ONLY_BRIDGE_OK")
