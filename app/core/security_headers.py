"""Cabeceras de seguridad para TODAS las respuestas (todas las empresas).

Middleware ASGI puro: solo agrega cabeceras al empezar la respuesta. Nunca
lee el cuerpo, nunca cambia el código de estado y nunca bloquea: si algo
falla al armar las cabeceras, la respuesta sale igual que antes.

- X-Content-Type-Options: nosniff
- Referrer-Policy: strict-origin-when-cross-origin
- X-Frame-Options: SAMEORIGIN, EXCEPTO la WebApp de Telegram (/webapp/...):
  Telegram Web (web.telegram.org) la abre dentro de un iframe de otro origen
  y SAMEORIGIN la dejaria en blanco. Los iframes propios de Clonexa (vista
  previa e impresion en client.js, hsp_cashier.js, sale_document.js,
  mini_panel.js) usan srcdoc, blob: o data:, que no dependen de esta cabecera.
- Content-Security-Policy SOLO en /admin-v2plus*: el resto de la plataforma
  usa scripts y estilos en linea (ver docs/seguridad_fase2.md).

Si una ruta ya puso su propia cabecera, se respeta.
"""
from __future__ import annotations

import logging

log = logging.getLogger("clonexa.security_headers")

FRAME_EXEMPT_PREFIXES = ("/webapp/",)

CONSOLE_PLUS_CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' https:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'self'",
])


def is_console_plus(path: str) -> bool:
    return path == "/admin-v2plus" or path.startswith("/admin-v2plus/") or path.startswith("/admin-v2plus.") \
        or path.startswith("/admin-v2plus-")


def headers_for(path: str) -> list[tuple[bytes, bytes]]:
    headers = [
        (b"x-content-type-options", b"nosniff"),
        (b"referrer-policy", b"strict-origin-when-cross-origin"),
    ]
    if not path.startswith(FRAME_EXEMPT_PREFIXES):
        headers.append((b"x-frame-options", b"SAMEORIGIN"))
    if is_console_plus(path):
        headers.append((b"content-security-policy", CONSOLE_PLUS_CSP.encode("ascii")))
    return headers


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path") or "")

        async def send_with_headers(message):
            if message.get("type") == "http.response.start":
                try:
                    present = {bytes(k).lower() for k, _ in message.get("headers") or []}
                    extra = [(k, v) for k, v in headers_for(path) if k not in present]
                    if extra:
                        message = {**message, "headers": [*(message.get("headers") or []), *extra]}
                except Exception as exc:  # nunca bloquear una respuesta valida
                    log.warning("No se pudieron agregar cabeceras de seguridad: %s", exc)
            await send(message)

        await self.app(scope, receive, send_with_headers)
