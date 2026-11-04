"""Links cortos /c/CODIGO (049Y).

Los links de los mini paneles (/mini-panel/caja?company_id=<uuid>) y el de
domicilios que se manda a los clientes eran larguisimos y daban desconfianza.
Con el interruptor "short_links" del modulo waiter_ordering (hoy solo
ASADERO) se reparten links cortos que redirigen al panel de siempre; los
links largos siguen funcionando igual.

- Mini paneles: tabla short_links (codigo -> ruta interna). La ruta no es
  secreta (es la misma pagina de ingreso de siempre) y solo se aceptan rutas
  /mini-panel de la propia empresa: nunca una redireccion a otro sitio.
- Domicilios: el codigo corto ES el codigo de un solo uso del cliente. No se
  guarda en claro: se busca por su hash en whatsapp_delivery_sessions, igual
  que hoy, y se redirige a /domicilio?c=<empresa>&s=<codigo>.
"""
from __future__ import annotations

import json
import re
import secrets
import time
import uuid
from collections import deque
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

FLAG = "short_links"
# Sin 0/O, 1/I/L: se dictan y se copian sin confusiones.
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
PANEL_CODE_LENGTH = 6
# Codigo de domicilio: credencial de un solo uso que vence en minutos;
# 10 caracteres de 31 (~49 bits) no se pueden adivinar a fuerza bruta.
DELIVERY_CODE_LENGTH = 10
# Lider de operacion: 8 caracteres de 31 (~39 bits) mas el limite de intentos de abajo.
LEADER_CODE_LENGTH = 8
# Probar codigos al azar: 20 fallos en 10 minutos desde una IP y esa IP recibe 429 hasta que
# envejezcan. Solo cuentan los fallos: un restaurante entero por la misma IP no se bloquea por usar
# sus links. Un solo worker (scripts/start.sh), igual que los demas limites en memoria.
MISS_LIMIT = 20
MISS_WINDOW_SECONDS = 600
CODE_RE = re.compile(rf"^[{ALPHABET}]{{4,16}}$")


class MissLimiter:
    def __init__(self, limit: int = MISS_LIMIT, window: float = MISS_WINDOW_SECONDS):
        self.limit, self.window = limit, window
        self.hits: dict[str, deque] = {}

    def _recent(self, key: str, now: float) -> deque:
        hits = self.hits.get(key)
        if hits is None:
            return deque()
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if not hits:
            self.hits.pop(key, None)
        return hits

    def blocked(self, key: str, now: float | None = None) -> bool:
        return len(self._recent(key, time.monotonic() if now is None else now)) >= self.limit

    def note(self, key: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self._recent(key, now)
        if len(self.hits) > 20000:  # nunca crece sin limite
            for old in list(self.hits)[:10000]:
                self.hits.pop(old, None)
        self.hits.setdefault(key, deque()).append(now)


MISSES = MissLimiter()


def client_ip(request: Any) -> str:
    """La IP que puso el proxy de Railway. La primera de X-Forwarded-For la escribe el cliente:
    con ella bastaria cambiarla en cada intento para saltarse el limite."""
    headers = request.headers
    real = str(headers.get("x-real-ip") or "").strip()
    forwarded = [part.strip() for part in str(headers.get("x-forwarded-for") or "").split(",") if part.strip()]
    client = getattr(request, "client", None)
    return (real or (forwarded[-1] if forwarded else "") or (client.host if client else "") or "?")[:64]


def new_code(length: int = PANEL_CODE_LENGTH) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def clean_code(value: Any) -> str:
    code = str(value or "").strip().upper()
    return code if CODE_RE.match(code) else ""


async def enabled(db: AsyncSession, company_id: Any) -> bool:
    try:
        row = (await db.execute(text("""
            SELECT cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id = CAST(:company_id AS uuid) AND LOWER(m.code) = 'waiter_ordering' AND cm.enabled IS TRUE
            LIMIT 1
        """), {"company_id": str(company_id)})).mappings().first()
    except Exception:
        await db.rollback()
        return False
    raw = (row or {}).get("settings") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except ValueError:
            return False
    return isinstance(raw, dict) and raw.get(FLAG) is True


def panel_target(company_id: Any, path_or_url: str) -> str:
    """La ruta interna de un link de mini panel de ESTA empresa, o "" si no
    lo es (otra empresa, otro sitio, otra pagina)."""
    try:
        parts = urlsplit(str(path_or_url or "").strip())
    except ValueError:
        return ""
    path = parts.path.rstrip("/")
    if not (path == "/mini-panel" or path.startswith("/mini-panel/")) or ".." in path or "//" in path:
        return ""
    if not re.fullmatch(r"/mini-panel(/[a-z0-9_]+){0,2}", path):
        return ""
    query = parse_qs(parts.query, keep_blank_values=False)
    if [str(v) for v in query.get("company_id", [])] != [str(company_id)]:
        return ""
    allowed = {k: v[0] for k, v in query.items() if k in {"company_id", "type"} and v}
    if "type" in allowed and not re.fullmatch(r"[a-z0-9_]{1,40}", allowed["type"]):
        return ""
    # Lider de operacion: la operacion es parte del destino.
    lugar = (query.get("lugar") or [""])[0]
    if allowed.get("type") == "lider_operacion" and re.fullmatch(r"[a-z0-9-]{1,80}", lugar):
        allowed["lugar"] = lugar
    return f"{path}?{urlencode(allowed)}"


async def panel_links(db: AsyncSession, company_id: uuid.UUID, targets: list[str], length: int = PANEL_CODE_LENGTH) -> dict[str, str]:
    """Codigo corto (el mismo siempre) para cada ruta de mini panel."""
    out: dict[str, str] = {}
    for target in targets:
        row = (await db.execute(text("""
            SELECT code FROM short_links WHERE company_id = CAST(:c AS uuid) AND target = :t LIMIT 1
        """), {"c": str(company_id), "t": target})).mappings().first()
        if row:
            out[target] = str(row["code"])
            continue
        for _attempt in range(5):
            code = new_code(length)
            inserted = (await db.execute(text("""
                INSERT INTO short_links (code, company_id, kind, target) VALUES (:code, CAST(:c AS uuid), 'mini_panel', :t)
                ON CONFLICT DO NOTHING RETURNING code
            """), {"code": code, "c": str(company_id), "t": target})).mappings().first()
            if inserted:
                out[target] = code
                break
            again = (await db.execute(text("""
                SELECT code FROM short_links WHERE company_id = CAST(:c AS uuid) AND target = :t LIMIT 1
            """), {"c": str(company_id), "t": target})).mappings().first()
            if again:  # otra pestaña lo creo al mismo tiempo
                out[target] = str(again["code"])
                break
    await db.commit()
    return out


async def resolve(db: AsyncSession, code: str) -> str:
    """La ruta interna a la que lleva un codigo corto, o ""."""
    code = clean_code(code)
    if not code:
        return ""
    row = (await db.execute(text("SELECT company_id, target FROM short_links WHERE code = :code LIMIT 1"),
                            {"code": code})).mappings().first()
    if row:
        target = panel_target(row["company_id"], row["target"])
        return target
    if len(code) == DELIVERY_CODE_LENGTH:
        from app.services.whatsapp_delivery import token_hash

        session = (await db.execute(text("""
            SELECT company_id FROM whatsapp_delivery_sessions WHERE token_hash = :h AND kind = 'link' LIMIT 1
        """), {"h": token_hash(code)})).mappings().first()
        if session:
            return f"/domicilio?{urlencode({'c': str(session['company_id']), 's': code})}"
    return ""
