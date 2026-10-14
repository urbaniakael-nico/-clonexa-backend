"""El logo del panel inicial de la empresa: UNA sola regla para todo lo que
debe verse igual al portal (Reportes v2 en pantalla y en PDF, Turnos).

Igual que client.js: con marca PUBLICADA del Estudio de marca
(brand_store.published_tokens -> brand_theme.branding_for_portal) manda su logo,
aunque este vacio (en el portal reemplaza al de siempre); sin marca publicada,
el logo de la experiencia de la empresa (companies._read_company_branding, lo
que devuelve /companies/{id}/experience).
"""
from __future__ import annotations

import base64
import re
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

_MEDIA = re.compile(r"^/brand-media/([0-9a-fA-F-]{36})/([0-9a-fA-F-]{36})\.webp$")


async def panel_logo(db: AsyncSession, company_id: Any) -> dict:
    """{"url": ..., "source": "published" | "experience" | "none"}."""
    from app.services import brand_store, brand_theme

    cid = str(company_id)
    tokens = await brand_store.published_tokens(db, cid)
    if tokens:
        try:
            url = brand_theme.branding_for_portal(tokens, cid).get("logo_url") or ""
        except Exception:
            url = ""
        return {"url": url, "source": "published" if url else "none"}
    try:
        from app.api.v1.endpoints.companies import _get_company_or_404, _read_company_branding

        branding = _read_company_branding(await _get_company_or_404(db, company_id))
        url = str(branding.get("logo_url") or "").strip()
    except Exception:
        url = ""
    return {"url": url, "source": "experience" if url else "none"}


async def panel_logo_bytes(db: AsyncSession, company_id: Any, url: Optional[str] = None) -> Optional[bytes]:
    """Los bytes del logo del panel (para el PDF): la imagen del Estudio de marca
    se lee directo de su almacenamiento; un data: URL se decodifica."""
    url = url if url is not None else (await panel_logo(db, company_id))["url"]
    if not url:
        return None
    m = _MEDIA.match(url)
    if m and m.group(1).lower() == str(company_id).lower():
        from app.services import brand_media

        try:
            return await brand_media.read(db, str(company_id), m.group(2))
        except Exception:
            return None
    if url.startswith("data:image/"):
        try:
            return base64.b64decode(url.split(",", 1)[1])
        except Exception:
            return None
    return None
