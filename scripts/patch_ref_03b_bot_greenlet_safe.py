from pathlib import Path
import re

path = Path("app/api/v1/endpoints/bots.py")
src = path.read_text(encoding="utf-8-sig")

if "REF_03A_BOT_REFERENCES_FLOW" not in src:
    raise SystemExit("No encontré REF_03A_BOT_REFERENCES_FLOW. No aplico REF-03B.")

if "REF_03B_GREENLET_SAFE_FIX" in src:
    print("REF_03B already applied")
    raise SystemExit(0)

start = src.index("# CLONEXA REF_03A_BOT_REFERENCES_FLOW")
end = src.index("def _menu_keyboard(", start)

before = src[:start]
block = src[start:end]
after = src[end:]

# 1) Reemplazar _ref_poll_item para no leer employee.id/full_name después de commit.
pattern = r'''def _ref_poll_item\(
.*?
\) -> TelegramBotPollItem:
.*?
    \)
'''

replacement = r'''def _ref_poll_item(
    *,
    update_id: Any,
    action: str,
    message: str,
    employee: Employee | None = None,
    employee_id_value: Any | None = None,
    employee_name_value: str | None = None,
    telegram_user_id: str,
    telegram_username: str | None,
) -> TelegramBotPollItem:
    # REF_03B_GREENLET_SAFE_FIX:
    # Nunca leer atributos ORM expirados después de db.commit().
    safe_employee_id = employee_id_value
    safe_employee_name = employee_name_value

    if employee is not None:
        if safe_employee_id is None:
            safe_employee_id = getattr(employee, "_clx_safe_employee_id", None)
        if safe_employee_name is None:
            safe_employee_name = getattr(employee, "_clx_safe_employee_name", None)

    if safe_employee_id is None and employee is not None:
        try:
            safe_employee_id = employee.id
        except Exception:
            safe_employee_id = None

    if safe_employee_name is None and employee is not None:
        try:
            safe_employee_name = employee.full_name
        except Exception:
            safe_employee_name = ""

    return TelegramBotPollItem(
        update_id=update_id,
        ok=True,
        action=action,
        message=message,
        employee_id=safe_employee_id,
        employee_name=safe_employee_name or "",
        event_created=True,
        telegram_user_id=telegram_user_id,
        telegram_username=telegram_username,
    )
'''

block, count = re.subn(pattern, replacement, block, count=1, flags=re.DOTALL)

if count != 1:
    raise SystemExit("No pude reemplazar _ref_poll_item.")

# 2) Dentro del flujo REF, usar snapshots seguros.
block = block.replace("employee_id=employee.id", "employee_id=employee_id_value")
block = block.replace("employee_name=employee.full_name", "employee_name=employee_name_value")

# 3) Insertar snapshot al inicio de _handle_reference_flow.
needle = '''    enabled_modules = await _enabled_module_codes(db, bot.company_id)
'''

insert = '''    # REF_03B_GREENLET_SAFE_FIX:
    # Snapshot antes de cualquier commit para evitar lazy-load async fuera de greenlet.
    employee_id_value = str(employee.id)
    employee_name_value = str(employee.full_name or "")

    try:
        setattr(employee, "_clx_safe_employee_id", employee_id_value)
        setattr(employee, "_clx_safe_employee_name", employee_name_value)
    except Exception:
        pass

    enabled_modules = await _enabled_module_codes(db, bot.company_id)
'''

if needle not in block:
    raise SystemExit("No encontré punto para insertar snapshot greenlet-safe.")

block = block.replace(needle, insert, 1)

# 4) Después de commit, no mandar menú con employee/company posiblemente expirados.
menu_call_regex = r'''^(\s*)await _send_dynamic_menu\(db, token=token, chat_id=chat_id, company=company, employee=employee, language=language\)'''

def fresh_menu(match):
    indent = match.group(1)
    return f'''{indent}fresh_employee = await _find_employee_by_telegram(db, bot.company_id, telegram_user_id, username)
{indent}fresh_company = await ensure_company_exists(db, bot.company_id)
{indent}if fresh_employee is not None and fresh_company is not None:
{indent}    await _send_dynamic_menu(
{indent}        db,
{indent}        token=token,
{indent}        chat_id=chat_id,
{indent}        company=fresh_company,
{indent}        employee=fresh_employee,
{indent}        language=language,
{indent}    )'''

block, menu_count = re.subn(menu_call_regex, fresh_menu, block, flags=re.MULTILINE)

if menu_count < 1:
    raise SystemExit("No encontré llamadas _send_dynamic_menu dentro de REF para blindar.")

src = before + block + after
path.write_text(src, encoding="utf-8")

print("REF_03B_GREENLET_SAFE_OK")
print("MENU_CALLS_PATCHED:", menu_count)
