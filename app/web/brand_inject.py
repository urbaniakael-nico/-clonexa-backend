"""Tema de la empresa en TODO lo que abre un cliente o un empleado (049Z).

Link de domicilios, QR de la carta, QR de mesa, mini paneles y sus pantallas
de ingreso salian con los colores genericos de CLONEXA: el tema de Admin V2
solo llegaba a los mini paneles despues de iniciar sesion. Ahora el servidor
incrusta el tema de la empresa en el HTML de esas paginas (ningun endpoint
nuevo: es la misma pagina de siempre) y hsp_brand.js lo aplica desde el
primer pintado.

Solo con el interruptor "brand_everywhere" del modulo waiter_ordering (hoy
ASADERO). Sin el, la pagina sale exactamente igual que antes. Solo se
incrustan los colores, la fuente y el logo publicos de la marca.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

FLAG = "brand_everywhere"
BRAND_KEYS = (
    "logo_url", "primary_color", "secondary_color", "background_color", "text_color", "font_family",
    "theme_mode", "mode", "gradient_from", "gradient_to", "gradient_angle",
)
BRAND_SCRIPT = '<script src="/client-static/hsp_brand.js?v=049Z_BRAND"></script>'
log = logging.getLogger("clonexa.brand_inject")


def _uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value or "").strip())
    except (TypeError, ValueError):
        return None


async def company_brand(db: AsyncSession, company_id: Any) -> dict | None:
    """Los colores de marca de la empresa si tiene el interruptor, o None."""
    cid = _uuid(company_id)
    if cid is None:
        return None
    try:
        row = (await db.execute(text("""
            SELECT cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id = CAST(:company_id AS uuid) AND LOWER(m.code) = 'waiter_ordering' AND cm.enabled IS TRUE
            LIMIT 1
        """), {"company_id": str(cid)})).mappings().first()
        settings = (row or {}).get("settings") or {}
        if isinstance(settings, str):
            settings = json.loads(settings or "{}")
        if not isinstance(settings, dict) or settings.get(FLAG) is not True:
            return None
        from app.api.v1.endpoints.companies import _get_company_or_404, _read_company_branding

        branding = _read_company_branding(await _get_company_or_404(db, cid))
    except Exception:
        log.exception("brand lookup failed company=%s", cid)
        try:
            await db.rollback()
        except Exception:
            pass
        return None
    out = {key: branding.get(key) for key in BRAND_KEYS if branding.get(key) not in (None, "")}
    return out or None


def inject(html: str, branding: dict | None) -> str:
    """El HTML con el tema incrustado antes de </head> (y hsp_brand.js si la
    pagina no lo cargaba). Sin marca, el HTML tal cual."""
    if not branding or "</head>" not in html:
        return html
    payload = json.dumps(branding, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    tags = f"<script>window.__CX_BRAND__={payload};</script>"
    if "hsp_brand.js" not in html:
        tags += BRAND_SCRIPT
    return html.replace("</head>", f"  {tags}\n</head>", 1)


# ---------------------------------------------------------------- Fase 4 ---
# Estudio de marca: si la empresa tiene una marca PUBLICADA, el ingreso y los
# mini paneles (mesero, cocina, caja) la reciben: sus colores por el mismo
# window.__CX_BRAND__ que ya entiende hsp_brand.js, y el CSS del generador
# propio (brand_theme.css_for, que escapa y revalida todo) en un <style> al
# final del <body> (fuera del <head>: hsp_brand.js no lo repinta). Sin marca
# publicada, la pagina sale EXACTAMENTE como antes (inject de siempre).
THEME_PAGES = frozenset({"hsp_waiter.html", "hsp_kitchen.html", "hsp_cashier.html"})
LITE_SCRIPT = '<script src="/client-static/brand_lite.js?v=FASE4"></script>'


async def published_theme(db: AsyncSession, company_id: Any) -> dict | None:
    cid = _uuid(company_id)
    if cid is None:
        return None
    from app.services import brand_store

    return await brand_store.published_tokens(db, str(cid))


def inject_theme(html: str, tokens: dict, company_id: str) -> str:
    """El HTML con la marca publicada. Si algo falla, el HTML de siempre."""
    from app.services import brand_theme

    if "</head>" not in html or "</body>" not in html:
        return html
    try:
        css = brand_theme.css_for(tokens, company_id)
        branding = brand_theme.branding_for_panels(tokens, company_id)
    except Exception:
        log.exception("marca publicada invalida company=%s; se sirve la de siempre", company_id)
        return html
    html = inject(html, branding)
    html = html.replace("</head>", f"  {LITE_SCRIPT}\n</head>", 1)
    safe = css.replace("</", "<\/")
    return html.replace("</body>", f'  <style id="cxBrandTheme">{safe}</style>\n</body>', 1)


async def render(html: str, db: AsyncSession, company_id: Any, file_name: str) -> str:
    """Lo que sirve _branded_html: la marca publicada en las paginas del
    alcance de esta fase; si no hay, exactamente lo de antes."""
    if file_name in THEME_PAGES:
        tokens = await published_theme(db, company_id)
        if tokens:
            return inject_theme(html, tokens, str(_uuid(company_id)))
    return inject(html, await company_brand(db, company_id))
