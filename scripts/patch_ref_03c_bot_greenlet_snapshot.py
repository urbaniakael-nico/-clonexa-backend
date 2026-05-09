from pathlib import Path

path = Path("app/api/v1/endpoints/bots.py")
src = path.read_text(encoding="utf-8-sig")

if "REF_03B_BOT_REFERENCES_SAFE_INTEGRATION" not in src:
    raise SystemExit("No existe REF_03B en bots.py. No aplico REF_03C.")

if "REF_03C_GREENLET_SNAPSHOT_FIX" in src:
    print("REF_03C already applied")
    raise SystemExit(0)

insert_before = "async def _ref_handle_bot_flow("
helper = r'''
# CLONEXA REF_03C_GREENLET_SNAPSHOT_FIX
def _ref_safe_attr(obj, attr, default=None):
    try:
        return getattr(obj, attr)
    except Exception:
        return default


async def _ref_safe_snapshot(db, *, bot, employee, current, telegram_user_id, username):
    # Refrescar ORM dentro del contexto async antes de leer atributos.
    for obj in (bot, employee, current):
        if obj is None:
            continue
        try:
            await db.refresh(obj)
        except Exception:
            pass

    company_id_value = _ref_safe_attr(bot, "company_id") or _ref_safe_attr(employee, "company_id")
    employee_id_value = _ref_safe_attr(employee, "id")
    employee_name_value = _ref_safe_attr(employee, "full_name") or ""

    # Fallback SQL plano si el ORM sigue expirado.
    if not company_id_value or not employee_id_value:
        try:
            row_result = await db.execute(
                text("""
                    SELECT
                        id::text AS employee_id,
                        company_id::text AS company_id,
                        COALESCE(full_name, '') AS employee_name
                    FROM employees
                    WHERE telegram_user_id::text = :telegram_user_id
                    LIMIT 1
                """),
                {"telegram_user_id": str(telegram_user_id)},
            )
            row = row_result.mappings().first()
            if row:
                company_id_value = company_id_value or row["company_id"]
                employee_id_value = employee_id_value or row["employee_id"]
                employee_name_value = employee_name_value or row["employee_name"]
        except Exception:
            pass

    company_id_value = str(company_id_value or "")
    employee_id_value = str(employee_id_value or "")
    employee_name_value = str(employee_name_value or "")

    if not company_id_value or not employee_id_value:
        raise RuntimeError("ref_snapshot_failed: company_id/employee_id missing")

    try:
        fresh_current = await _get_current_attendance_status(
            db,
            UUID(company_id_value),
            UUID(employee_id_value),
        )
        status_key = _current_status_key(fresh_current)
    except Exception:
        try:
            status_key = _current_status_key(current)
        except Exception:
            status_key = "sin_turno"

    enabled_modules = await _enabled_module_codes(db, UUID(company_id_value))

    return company_id_value, employee_id_value, employee_name_value, status_key, enabled_modules


'''

if insert_before not in src:
    raise SystemExit("No encontré async def _ref_handle_bot_flow.")

src = src.replace(insert_before, helper + insert_before, 1)

old = '''    company_id_value = str(bot.company_id)
    employee_id_value = str(employee.id)
    employee_name_value = str(employee.full_name or "")
    status_key = _current_status_key(current)
    enabled_modules = await _enabled_module_codes(db, bot.company_id)
'''

new = '''    company_id_value, employee_id_value, employee_name_value, status_key, enabled_modules = await _ref_safe_snapshot(
        db,
        bot=bot,
        employee=employee,
        current=current,
        telegram_user_id=telegram_user_id,
        username=username,
    )
'''

if old not in src:
    raise SystemExit("No encontré bloque ORM inseguro para reemplazar.")

src = src.replace(old, new, 1)

# Antes de llamar _create_bot_attendance_event refrescamos bot/employee dentro del contexto async.
src = src.replace(
'''        created, message_text = await _create_bot_attendance_event(
            db,
            bot=bot,
            employee=employee,''',
'''        try:
            await db.refresh(bot)
            await db.refresh(employee)
        except Exception:
            pass

        created, message_text = await _create_bot_attendance_event(
            db,
            bot=bot,
            employee=employee,''',
    2
)

path.write_text(src, encoding="utf-8")
print("REF_03C_GREENLET_SNAPSHOT_FIX_OK")
