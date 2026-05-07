from pathlib import Path

path = Path("app/api/v1/endpoints/bots.py")
text = path.read_text(encoding="utf-8-sig")

old = '''            if command == "/start":
                await _send_telegram_message(
                    token,
                    chat_id,
                    f"🆔 Tu Telegram ID es: {telegram_user_id or 'NO_DETECTADO'}\\n\\n"
                    "Entrega este número a la persona encargada para completar tu registro en CLONEXA.",
                )
'''

new = '''            if command == "/start" and employee is None:
                await _send_telegram_message(
                    token,
                    chat_id,
                    f"🆔 Tu Telegram ID es: {telegram_user_id or 'NO_DETECTADO'}\\n\\n"
                    "Entrega este número a la persona encargada para completar tu registro en CLONEXA.",
                )
'''

if old not in text:
    raise SystemExit("No encontré bloque exacto de Telegram ID /start. No modifiqué nada.")

text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")

print("PATCH_OK: Telegram ID solo se envía si el empleado NO está vinculado.")
