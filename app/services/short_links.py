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
import uuid
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
CODE_RE = re.compile(rf"^[{ALPHABET}]{{4,16}}$")


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
    return f"{path}?{urlencode(allowed)}"


async def panel_links(db: AsyncSession, company_id: uuid.UUID, targets: list[str]) -> dict[str, str]:
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
            code = new_code()
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
