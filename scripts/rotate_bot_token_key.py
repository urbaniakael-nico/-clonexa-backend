"""Rotacion de la clave que cifra los tokens de bots (company_bot_instances).

Uso (dentro del contenedor del backend, con las variables de produccion):
  python -m scripts.rotate_bot_token_key check      # getMe de todos los bots, no escribe
  python -m scripts.rotate_bot_token_key reencrypt  # re-cifra con la clave primaria y
                                                    # confirma solo si TODOS responden getMe

Nunca imprime tokens: solo empresa, usuario del bot y resultado.
"""
import asyncio
import sys

import httpx
from sqlalchemy import text

from app.api.v1.endpoints import bots
from app.core.database import async_session_maker

ROWS_SQL = """
    SELECT b.id, b.company_id, c.slug, b.channel, b.bot_username, b.status, b.bot_token_encrypted
    FROM company_bot_instances b
    JOIN companies c ON c.id = b.company_id
    WHERE b.bot_token_encrypted IS NOT NULL
    ORDER BY c.slug, b.channel
"""


async def get_me(client: httpx.AsyncClient, token: str) -> tuple[bool, str]:
    try:
        response = await client.get(f"https://api.telegram.org/bot{token}/getMe")
        data = response.json()
    except Exception as exc:  # red, json
        return False, type(exc).__name__
    if response.status_code == 200 and data.get("ok"):
        return True, "@" + str((data.get("result") or {}).get("username") or "?")
    return False, f"HTTP {response.status_code}"


async def check_rows(rows) -> list[str]:
    """Descifra y llama getMe por cada fila; devuelve las fallas."""
    failures = []
    async with httpx.AsyncClient(timeout=15) as client:
        for row in rows:
            label = f"{row.slug} / {row.channel} / {row.bot_username or '-'} ({row.status})"
            try:
                token = bots.decrypt_token(row.bot_token_encrypted)
            except Exception as exc:
                failures.append(label)
                print(f"FALLA descifrar  {label}: {type(exc).__name__}")
                continue
            if row.channel != "telegram":
                print(f"OK descifra      {label} (no es Telegram, sin getMe)")
                continue
            ok, detail = await get_me(client, token)
            primary = "clave nueva" if bots.token_uses_primary_key(row.bot_token_encrypted) else "clave anterior"
            print(f"{'OK' if ok else 'FALLA'} getMe {detail:<24} {label} [{primary}]")
            if not ok:
                failures.append(label)
    return failures


async def main(mode: str) -> int:
    async with async_session_maker() as db:
        rows = (await db.execute(text(ROWS_SQL))).all()
        print(f"{len(rows)} bots con token guardado")
        if mode == "check":
            failures = await check_rows(rows)
            print("TODOS RESPONDEN" if not failures else f"{len(failures)} FALLAS")
            return 0 if not failures else 1

        # reencrypt: todo en una transaccion; si un bot falla, rollback.
        for row in rows:
            stored = row.bot_token_encrypted
            if stored.startswith("fernet:"):
                new_value = bots.reencrypt_token(stored)
            else:  # b64: o texto plano heredado -> pasa a fernet
                new_value = bots.encrypt_token(bots.decrypt_token(stored))
            await db.execute(
                text("UPDATE company_bot_instances SET bot_token_encrypted = :v WHERE id = :id AND company_id = :c"),
                {"v": new_value, "id": row.id, "c": row.company_id},
            )
        rows_after = (await db.execute(text(ROWS_SQL))).all()
        failures = await check_rows(rows_after)
        not_primary = [r.slug for r in rows_after if not bots.token_uses_primary_key(r.bot_token_encrypted)]
        if failures or not_primary:
            await db.rollback()
            print(f"ROLLBACK: {len(failures)} fallas getMe, {len(not_primary)} sin clave nueva. No se cambio nada.")
            return 1
        await db.commit()
        print(f"COMMIT: {len(rows_after)} tokens re-cifrados con la clave nueva y todos responden getMe")
        return 0


if __name__ == "__main__":
    mode = (sys.argv[1:] or ["check"])[0]
    if mode not in {"check", "reencrypt"}:
        sys.exit("uso: python -m scripts.rotate_bot_token_key check|reencrypt")
    sys.exit(asyncio.run(main(mode)))
