from pathlib import Path

path = Path("app/api/v1/endpoints/bots.py")
text = path.read_text(encoding="utf-8-sig")

old = '''def _telegram_message(update: dict[str, Any]) -> dict[str, Any] | None:
    message = update.get("message") or update.get("edited_message")
    if isinstance(message, dict):
        return message
    callback = update.get("callback_query")
    if isinstance(callback, dict) and isinstance(callback.get("message"), dict):
        return callback["message"]
    return None
'''

new = '''def _telegram_message(update: dict[str, Any]) -> dict[str, Any] | None:
    message = update.get("message") or update.get("edited_message")
    if isinstance(message, dict):
        return message

    callback = update.get("callback_query")
    if isinstance(callback, dict) and isinstance(callback.get("message"), dict):
        # CLONEXA 019C-L1:
        # Telegram callback_query.message.from usually belongs to the bot.
        # Legacy paths that call _telegram_identity(message) must see the real user.
        callback_message = dict(callback["message"])

        callback_from = callback.get("from") or {}
        if isinstance(callback_from, dict) and callback_from:
            callback_message["from"] = callback_from

        callback_data = str(callback.get("data") or "").strip()
        if callback_data:
            callback_message["text"] = callback_data

        return callback_message

    return None
'''

if old not in text:
    raise SystemExit("No encontré bloque exacto _telegram_message para parchear. No modifiqué nada.")

text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
print("PATCH_OK: _telegram_message callback identity fixed")
