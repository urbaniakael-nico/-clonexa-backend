"""Carta QR nueva (057C): lo que necesita la pantalla del cliente, en una sola
respuesta y sin datos internos (nunca costos ni existencias).

- Marca: la MISMA que ve el portal (crm_lab.theme: marca publicada del Estudio
  de marca o, sin ella, la guardada; fondo con branding_background) y el logo
  y nombre del panel inicial (loyalty_games.brand -> panel_logo).
- Platos: los de la Carta (carta_inventory_lite), solo los disponibles (un
  plato agotado u oculto no aparece), con foto y, con carta_video, su clip.
- Categorias: su imagen o, si no tiene, la portada/foto de su primer plato.
- "Lo mas pedido": ventas reales de los ultimos 30 dias de ESA empresa; sin
  ventas, los platos con video (o con foto).
- Opciones del plato: SOLO las que la Carta ya tiene (termino de coccion y
  notas rapidas de su categoria, porciones). No se inventa nada.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("clonexa.carta_app")

# Los mismos terminos de coccion del mesero (hsp_menu_kit.js TERM_STOPS).
TERMS = ["Crudo", "Medio", "3/4", "Bien cocinado"]
TOP_LIMIT = 8


async def top_sellers(db: AsyncSession, company_id: Any, limit: int = 20) -> list[str]:
    """Ids de plato mas vendidos en los ultimos 30 dias (cantidad), de ESA empresa."""
    try:
        async with db.begin_nested():
            rows = (await db.execute(text("""
                SELECT COALESCE(NULLIF(line->>'menu_item_id', ''), NULLIF(line->>'product_id', ''), NULLIF(line->>'inventory_item_id', '')) AS id,
                       SUM(CASE WHEN COALESCE(line->>'quantity', '') ~ '^[0-9]+(\\.[0-9]+)?$' THEN (line->>'quantity')::numeric ELSE 1 END) AS qty
                FROM hospitality_orders o, jsonb_array_elements(CASE WHEN jsonb_typeof(o.items) = 'array' THEN o.items ELSE '[]'::jsonb END) AS line
                WHERE o.company_id = CAST(:c AS uuid) AND o.created_at > now() - interval '30 days' AND o.cancelled_at IS NULL
                GROUP BY 1 ORDER BY 2 DESC LIMIT :n
            """), {"c": str(company_id), "n": limit})).mappings().all()
    except Exception as exc:  # sin tabla de pedidos o un dato raro: sin ranking
        log.warning("carta app: sin ventas para lo mas pedido: %s", type(exc).__name__)
        return []
    return [str(r["id"]) for r in rows if r.get("id")]


async def _locale(db: AsyncSession, company_id: str) -> dict:
    """Moneda e idioma de la empresa (Ajustes Fase A); por defecto pesos en español."""
    from app.services import company_locale

    loc = await company_locale.get_company_locale(db, company_id)
    return {"currency": loc.get("currency") or "COP", "language": loc.get("language") or "es", "decimals": loc.get("decimals", 0)}


async def payload(db: AsyncSession, company_id: Any) -> dict:
    from app.api.v1.endpoints import carta as carta_api
    from app.api.v1.endpoints.crm_lab import theme as portal_theme
    from app.api.v1.endpoints.loyalty_games import brand as panel_brand
    from app.services import menu_video

    cid = str(uuid.UUID(str(company_id)))
    video = await menu_video.video_on(db, cid)
    items = await carta_api.carta_inventory_lite(db, cid)
    categories = await carta_api.load_categories(db, cid)
    images = await carta_api._image_versions(db, cid)
    try:
        brand = await panel_brand(db, cid)
    except Exception:
        await db.rollback()
        brand = {}
    if not brand.get("name"):
        name = (await db.execute(text("SELECT name FROM companies WHERE id = CAST(:c AS uuid)"), {"c": cid})).scalar()
        brand = {**brand, "name": name or ""}
    try:
        theme = await portal_theme(db, uuid.UUID(cid))
    except Exception:
        await db.rollback()
        theme = {}

    products = []
    for item in items:
        if not item.get("active"):
            continue  # agotado u oculto: no aparece en la carta del cliente
        portions = bool(item.get("allows_portions"))
        products.append({
            "id": item["id"], "name": item.get("name") or "", "price": float(item.get("price") or 0),
            "description": item.get("description") or "",
            "category_key": item.get("category_key") or "otros", "category_label": item.get("category_label") or "OTROS",
            "subcategory_label": item.get("subcategory_label") or "",
            "photo_url": item.get("photo_url") or "",
            "gallery_urls": [u for u in item.get("gallery_urls") or [] if isinstance(u, str)][:6],
            "video_url": item.get("video_url") or "" if video else "",
            "poster_url": item.get("poster_url") or "" if video else "",
            "requires_term": bool(item.get("requires_term")),
            "quick_notes": [n for n in item.get("quick_notes") or [] if isinstance(n, str)][:8],
            "allows_portions": portions,
        })

    def cover(key: str) -> str:
        for p in products:
            if p["category_key"] == key and (p["poster_url"] or p["photo_url"]):
                return p["poster_url"] or p["photo_url"]
        return ""

    cats = []
    tops = [c for c in categories if not c.get("parent_id")]
    for top in tops:
        count = sum(1 for p in products if p["category_key"] == top["id"])
        if not count:
            continue
        image = (f"/api/v1/companies/{cid}/waiter-ordering/products/{top['id']}/image?v={images[top['id']]}"
                 if top["id"] in images else cover(top["id"]))
        cats.append({"key": top["id"], "label": top["label"], "count": count, "image_url": image})
    loose = sum(1 for p in products if p["category_key"] not in {c["key"] for c in cats})
    if loose:
        cats.append({"key": "otros", "label": "OTROS", "count": loose, "image_url": cover("otros")})
        for p in products:
            if p["category_key"] not in {c["key"] for c in cats}:
                p["category_key"], p["category_label"] = "otros", "OTROS"

    available = {p["id"] for p in products}
    top_ids = [i for i in await top_sellers(db, cid) if i in available][:TOP_LIMIT]
    top_source = "ventas"
    if not top_ids:
        with_media = [p["id"] for p in products if p["video_url"]] or [p["id"] for p in products if p["photo_url"]]
        top_ids, top_source = with_media[:TOP_LIMIT], "video" if video else "foto"

    return {
        "company": {"id": cid, "name": brand.get("name") or "", "logo_url": brand.get("logo_url") or ""},
        "theme": theme, "video": video, "terms": TERMS,
        "categories": cats, "products": products, "top": top_ids, "top_source": top_source,
        "locale": await _locale(db, cid),
    }
