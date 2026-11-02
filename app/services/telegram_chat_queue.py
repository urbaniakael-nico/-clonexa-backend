"""Updates de Telegram de un mismo chat EN ORDEN, uno a la vez (060A, todas las empresas).

- Un candado en memoria por (empresa, chat): los updates de un chat esperan su turno
  (asyncio.Lock atiende en el orden en que llegaron); los demas chats no esperan.
  El servidor corre UN solo proceso (scripts/start.sh: uvicorn sin --workers), asi
  que el candado en memoria basta y no ocupa conexiones de la base mientras espera.
- Si Postgres aborta por concurrencia (deadlock 40P01, serializacion 40001,
  lock_not_available 55P03), se reintenta hasta 2 veces con una sesion nueva.
- El error real queda en el log: tipo, tipo de asyncpg, SQLSTATE, mensaje corto,
  update_id, tipo de update, usuario de Telegram. Nunca el token ni el cuerpo.
"""
from __future__ import annotations

import asyncio
import contextlib
import re
from typing import Any, AsyncIterator, Awaitable, Callable

CONCURRENCY_SQLSTATES = {"40P01", "40001", "55P03"}
MAX_RETRIES = 2
RETRY_DELAY_SECONDS = 0.25

_LOCKS: dict[str, asyncio.Lock] = {}
_USERS: dict[str, int] = {}


def _message(update: dict[str, Any]) -> dict[str, Any]:
    for key in ("message", "edited_message"):
        if isinstance(update.get(key), dict):
            return update[key]
    callback = update.get("callback_query")
    if isinstance(callback, dict):
        return callback.get("message") or {}
    return {}


def chat_id_of(update: dict[str, Any]) -> str:
    callback = update.get("callback_query") if isinstance(update.get("callback_query"), dict) else None
    chat = (_message(update).get("chat") or {}).get("id")
    if chat is None and callback:
        chat = (callback.get("from") or {}).get("id")
    return str(chat if chat is not None else "")


def user_id_of(update: dict[str, Any]) -> str:
    callback = update.get("callback_query") if isinstance(update.get("callback_query"), dict) else None
    source = callback if callback else _message(update)
    value = (source.get("from") or {}).get("id")
    return str(value if value is not None else "")


def update_kind(update: dict[str, Any]) -> str:
    """message.text | message.location | edited_message.location | callback_query | ..."""
    if isinstance(update.get("callback_query"), dict):
        return "callback_query"
    for key in ("message", "edited_message"):
        msg = update.get(key)
        if isinstance(msg, dict):
            for part in ("location", "text", "contact", "photo", "web_app_data"):
                if part in msg:
                    return f"{key}.{part}"
            return f"{key}.other"
    return "other"


def is_action(update: dict[str, Any]) -> bool:
    """Lo que la persona toco o escribio (y espera respuesta). Una actualizacion de
    la ubicacion en vivo (edited_message) no lo es."""
    return update_kind(update) in {"callback_query", "message.text", "message.location", "message.contact", "message.web_app_data"}


def sqlstate_of(exc: BaseException) -> str:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        for attr in ("sqlstate", "pgcode"):
            value = getattr(current, attr, None)
            if isinstance(value, str) and value:
                return value
        current = getattr(current, "orig", None) or current.__cause__ or current.__context__
    return ""


def is_concurrency_error(exc: BaseException) -> bool:
    if sqlstate_of(exc) in CONCURRENCY_SQLSTATES:
        return True
    text_value = str(exc).lower()
    return "deadlock detected" in text_value or "could not serialize access" in text_value


_SECRETS = re.compile(r"(bot\d+:[\w-]{20,}|postgres(?:ql)?(?:\+\w+)?://\S+)", re.I)


def describe_error(exc: BaseException) -> dict[str, str]:
    orig = getattr(exc, "orig", None)
    driver = getattr(orig, "__cause__", None) or orig
    message = str(driver or exc).split("\n[SQL:")[0]
    message = _SECRETS.sub("[oculto]", re.sub(r"\s+", " ", message)).strip()[:300]
    return {
        "type": type(exc).__name__,
        "driver_type": type(driver).__name__ if driver is not None else "",
        "sqlstate": sqlstate_of(exc),
        "message": message,
    }


@contextlib.asynccontextmanager
async def chat_turn(key: str) -> AsyncIterator[None]:
    lock = _LOCKS.get(key)
    if lock is None:
        lock = _LOCKS[key] = asyncio.Lock()
    _USERS[key] = _USERS.get(key, 0) + 1
    try:
        async with lock:
            yield
    finally:
        _USERS[key] -= 1
        if _USERS[key] <= 0:  # sin nadie esperando: no se acumulan candados
            _USERS.pop(key, None)
            _LOCKS.pop(key, None)


async def run_in_order(key: str, work: Callable[[], Awaitable[Any]], *, retries: int = MAX_RETRIES,
                       on_retry: Callable[[int, BaseException], Any] | None = None) -> Any:
    """Corre `work` con el turno del chat; reintenta solo errores de concurrencia."""
    async with chat_turn(key):
        attempt = 0
        while True:
            try:
                return await work()
            except Exception as exc:
                if attempt >= retries or not is_concurrency_error(exc):
                    raise
                attempt += 1
                if on_retry is not None:
                    on_retry(attempt, exc)
                await asyncio.sleep(RETRY_DELAY_SECONDS * attempt)


def pending_chats() -> int:
    """Solo pruebas / diagnostico."""
    return len(_LOCKS)
