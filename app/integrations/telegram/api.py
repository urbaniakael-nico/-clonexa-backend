"""Llamadas salientes a la API de Telegram (todas las empresas).

- TELEGRAM_API_BASE cambia el destino (por defecto https://api.telegram.org),
  por ejemplo a un proxy; TELEGRAM_PROXY_KEY, si existe, viaja como cabecera
  X-Proxy-Key.
- Timeouts cortos (conexion 5 s, lectura 10 s) y un reintento con conexion nueva
  si la red falla (ReadTimeout, ConnectError, ConnectTimeout, RemoteProtocolError).
- Los avisos nunca llevan el token ni la URL: solo el metodo y el tipo de error.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("clonexa.telegram_api")

DEFAULT_TELEGRAM_API_BASE = "https://api.telegram.org"
TELEGRAM_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
TELEGRAM_RETRYABLE_ERRORS = (
    httpx.ReadTimeout,
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.RemoteProtocolError,
)


def telegram_api_base() -> str:
    return (os.getenv("TELEGRAM_API_BASE") or "").strip().rstrip("/") or DEFAULT_TELEGRAM_API_BASE


def telegram_method_url(token: str, method: str) -> str:
    return f"{telegram_api_base()}/bot{token}/{method}"


def telegram_file_url(token: str, file_path: str) -> str:
    return f"{telegram_api_base()}/file/bot{token}/{str(file_path).lstrip('/')}"


def telegram_headers() -> dict[str, str]:
    proxy_key = (os.getenv("TELEGRAM_PROXY_KEY") or "").strip()
    return {"X-Proxy-Key": proxy_key} if proxy_key else {}


async def telegram_call(
    token: str,
    method: str,
    *,
    payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    http_method: str = "POST",
    timeout: httpx.Timeout | float | None = None,
) -> httpx.Response:
    """Una llamada a Telegram con un reintento; si ambos intentos fallan por red,
    registra un aviso corto y relanza la excepcion de httpx."""
    url = telegram_method_url(token, method)
    for attempt in (1, 2):
        try:
            async with httpx.AsyncClient(timeout=timeout or TELEGRAM_TIMEOUT) as client:
                return await client.request(http_method, url, json=payload, params=params, headers=telegram_headers())
        except TELEGRAM_RETRYABLE_ERRORS as exc:
            if attempt == 2:
                logger.warning("Telegram %s sin respuesta tras 1 reintento (%s)", method, type(exc).__name__)
                raise
            logger.warning("Telegram %s fallo (%s); reintento con conexion nueva", method, type(exc).__name__)
    raise RuntimeError("unreachable")  # pragma: no cover
