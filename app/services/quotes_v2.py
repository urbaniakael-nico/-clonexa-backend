"""Cotizaciones y cuentas de cobro v2 (interruptor quotes_v2 del modulo de cotizaciones;
hoy solo Velvet).

Sigue el codigo de siempre (mini_panel_quotes): misma tabla, numeracion CT/CB,
mismos items, descuentos, retencion (no resta del total), pago y PDF. Lo nuevo:

- Origen "Desde produccion" (cuenta de cobro): trae las PRENDAS CERRADAS del
  periodo por referencia y talla. Cada cierre queda ligado a la cuenta en
  quote_closure_charges (un cierre solo en UNA cuenta vigente, indice unico
  parcial); archivar la cuenta lo libera. Un cierre ya cobrado no vuelve a salir.
- Valor por prenda: reference_op_settings.value_per_garment; si no hay,
  product_references.unit_price; si no hay, se escribe a mano.
- Clientes: los de los documentos anteriores (por documento o nombre).
- Pago: el metodo y los datos del ultimo documento.
- Firmas NUEVAS en el bucket (zona privada billing/{empresa}/signatures/...);
  en Postgres solo la clave.
- Pagada: metadata.paid_at en una cuenta de cobro (cobrado vs por cobrar).
Todo por company_id.
"""
from __future__ import annotations

import base64
import io
import json
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

SWITCH = "quotes_v2"
PANEL = "client"  # los documentos del portal (los mismos que lee el Cierre de dia)
ORIGINS = ("production", "references", "manual")
FILTERS = ("active", "paid", "archived", "all")
SIGNATURE_MAX_BYTES = 600 * 1024
SIGNATURE_MAX_PX = 1200


class QuoteError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return fallback
    return value if isinstance(value, type(fallback)) else fallback


def _mpq():
    from app.api.v1.endpoints import mini_panel_quotes

    return mini_panel_quotes


async def is_on(db: AsyncSession, company_id: Any) -> bool:
    rows = (await db.execute(text("""
        SELECT lower(m.code) AS code, cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id::text = :c AND cm.enabled IS TRUE
    """), {"c": str(company_id)})).mappings().all()
    aliases = _mpq().QUOTE_ALIASES
    return any(r["code"] in aliases and _json(r["settings"], {}).get(SWITCH) is True for r in rows)


def _tz() -> str:
    from app.services import company_locale

    return company_locale.current_zone().key


# ---------------------------------------------------------------- valor por prenda
async def unit_values(db: AsyncSession, company_id: str) -> dict[str, dict]:
    """{group_key: {value, source}}: orden operacional, luego precio de la referencia."""
    from app.services.references_v2 import group_key

    out: dict[str, dict] = {}
    for r in (await db.execute(text("SELECT name, COALESCE(unit_price, 0) AS p FROM product_references WHERE company_id = :c"),
                               {"c": company_id})).mappings().all():
        k = group_key(r["name"])
        price = float(r["p"] or 0)
        if price > 0 and price > out.get(k, {}).get("value", 0):
            out[k] = {"value": price, "source": "reference"}
    for r in (await db.execute(text("""
        SELECT group_key, value_per_garment FROM reference_op_settings WHERE company_id = :c AND value_per_garment > 0
    """), {"c": company_id})).mappings().all():
        out[r["group_key"]] = {"value": float(r["value_per_garment"]), "source": "op_order"}
    return out


def pick_value(values: dict[str, dict], key: str) -> dict:
    item = values.get(key)
    return dict(item) if item else {"value": None, "source": "manual"}


# ---------------------------------------------------------------- desde produccion
async def _closures(db: AsyncSession, company_id: str, start: Optional[date] = None, end: Optional[date] = None,
                    ids: Optional[list[str]] = None) -> list[dict]:
    where, params = ["c.company_id = :c"], {"c": company_id, "tz": _tz()}
    if start and end:
        where.append("(c.closed_at AT TIME ZONE CAST(:tz AS text))::date BETWEEN :s AND :e")
        params.update(s=start, e=end)
    if ids is not None:
        where.append("c.id = ANY(:ids)")
        params["ids"] = list(ids)
    return [dict(r) for r in (await db.execute(text(f"""
        SELECT c.id, COALESCE(c.reference_id, '') AS reference_id, COALESCE(c.reference_name, '') AS reference_name,
               COALESCE(c.size, '') AS size, COALESCE(c.quantity_finished, 0) AS quantity,
               (c.closed_at AT TIME ZONE CAST(:tz AS text))::date AS day,
               ch.quote_id AS charged_quote_id, q.quote_number AS charged_number
        FROM reference_production_closures c
        LEFT JOIN quote_closure_charges ch ON ch.company_id::text = c.company_id AND ch.closure_id = c.id AND ch.released_at IS NULL
        LEFT JOIN mini_panel_quotes q ON q.id = ch.quote_id AND q.company_id::text = c.company_id
        WHERE {' AND '.join(where)} ORDER BY c.closed_at
    """), params)).mappings().all()]


def group_closures(closures: list[dict], names: dict[str, str], values: dict[str, dict]) -> dict:
    """Puro: cierres sin cobrar agrupados por referencia (tallas, cantidad, ids) y
    los ya cobrados por documento (para el aviso "N prendas ya cobradas en CB-...")."""
    from app.services.references_v2 import group_key, size_key

    mpq = _mpq()
    groups: dict[str, dict] = {}
    charged: dict[str, int] = {}
    for c in closures:
        qty = int(c["quantity"] or 0)
        if qty <= 0:
            continue
        if c.get("charged_quote_id"):
            doc = mpq._account_number_from_quote_number(c.get("charged_number"))
            charged[doc] = charged.get(doc, 0) + qty
            continue
        ref = names.get(str(c["reference_id"])) or {}
        k = ref.get("key") or group_key(c["reference_name"])
        g = groups.setdefault(k, {"key": k, "name": ref.get("name") or c["reference_name"], "sizes": {}, "quantity": 0, "closure_ids": []})
        size = str(c["size"] or "").strip().upper() or "—"
        g["sizes"][size] = g["sizes"].get(size, 0) + qty
        g["quantity"] += qty
        g["closure_ids"].append(str(c["id"]))
    lines = []
    for g in sorted(groups.values(), key=lambda x: x["name"].lower()):
        v = pick_value(values, g["key"])
        sizes = [{"size": s, "quantity": q} for s, q in sorted(g["sizes"].items(), key=lambda kv: size_key(kv[0]))]
        lines.append({**g, "sizes": sizes, "unit_price": v["value"], "price_source": v["source"],
                      "description": f"{g['name']} · " + " / ".join(f"{s['size']} {s['quantity']}" for s in sizes)})
    return {"lines": lines, "already_charged": [{"document": d, "quantity": q} for d, q in sorted(charged.items())],
            "already_charged_total": sum(charged.values())}


async def _ref_names(db: AsyncSession, company_id: str) -> dict[str, dict]:
    from app.services.references_v2 import group_key

    rows = (await db.execute(text("SELECT id, name FROM product_references WHERE company_id = :c"), {"c": company_id})).mappings().all()
    return {str(r["id"]): {"key": group_key(r["name"]), "name": r["name"]} for r in rows}


async def from_production(db: AsyncSession, company_id: str, start: date, end: date) -> dict:
    closures = await _closures(db, company_id, start, end)
    out = group_closures(closures, await _ref_names(db, company_id), await unit_values(db, company_id))
    out["period"] = {"from": start.isoformat(), "to": end.isoformat()}
    return out


# ---------------------------------------------------------------- desde referencias
async def reference_options(db: AsyncSession, company_id: str) -> list[dict]:
    from app.services import references_v2

    values = await unit_values(db, company_id)
    out = []
    for g in await references_v2.reference_groups(db, company_id):
        lines = [x for x in g["lines"] if x.get("reference_id") and not x.get("archived")]
        if not lines:
            continue
        v = pick_value(values, g["key"])
        out.append({"key": g["key"], "name": g["name"], "active": any(x.get("bot_active") for x in lines),
                    "sizes": [{"size": x["size"], "meta": x["meta"], "pending": x["pending"]} for x in lines],
                    "unit_price": v["value"], "price_source": v["source"]})
    return sorted(out, key=lambda x: (not x["active"], x["name"].lower()))


# ---------------------------------------------------------------- clientes y pago
async def clients(db: AsyncSession, company_id: str) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT DISTINCT ON (lower(COALESCE(NULLIF(trim(client_document), ''), trim(client_name))))
               client_name, COALESCE(client_document, '') AS client_document, COALESCE(client_phone, '') AS client_phone,
               COALESCE(client_address, '') AS client_address, COALESCE(client_email, '') AS client_email, created_at
        FROM mini_panel_quotes WHERE company_id = CAST(:c AS uuid) AND trim(COALESCE(client_name, '')) <> ''
        ORDER BY lower(COALESCE(NULLIF(trim(client_document), ''), trim(client_name))), created_at DESC
    """), {"c": company_id})).mappings().all()
    return sorted(({k: r[k] for k in ("client_name", "client_document", "client_phone", "client_address", "client_email")} for r in rows),
                  key=lambda x: x["client_name"].lower())


async def defaults(db: AsyncSession, company_id: str) -> dict:
    last = (await db.execute(text("""
        SELECT payment FROM mini_panel_quotes WHERE company_id = CAST(:c AS uuid) AND payment IS NOT NULL
        ORDER BY created_at DESC LIMIT 1
    """), {"c": company_id})).mappings().first()
    payment = _json(last["payment"], {}) if last else {}
    sig = await saved_signature(db, company_id)
    return {"payment": {k: payment.get(k, "") for k in ("method", "name", "detail", "data")} if payment else None,
            "signature": {"id": sig["id"]} if sig else None, "clients": await clients(db, company_id)}


# ---------------------------------------------------------------- numeracion
async def next_number(db: AsyncSession, company_id: str, year: Optional[int] = None) -> str:
    """La MISMA regla de mini_panel_quotes: CT-AAAA-NNNN (la cuenta de cobro es CB-...)."""
    year = year or datetime.now(timezone.utc).year
    rows = (await db.execute(text("""
        SELECT quote_number FROM mini_panel_quotes WHERE company_id = CAST(:c AS uuid) AND (quote_number LIKE :a OR quote_number LIKE :b)
    """), {"c": company_id, "a": f"CT-{year}-%", "b": f"COT-{year}-%"})).scalars().all()
    top = 0
    for raw in rows:
        try:
            top = max(top, int(str(raw).split("-")[-1]))
        except ValueError:
            continue
    return f"CT-{year}-{top + 1:04d}"


# ---------------------------------------------------------------- crear
def totals(items: list[dict], discounts: list[dict]) -> dict:
    """Misma regla actual (mini_panel_quotes): descuentos restan, la retencion NO resta del total."""
    mpq = _mpq()
    clean_items, subtotal = mpq._sanitize_items([mpq.QuoteItemIn(**{k: i.get(k) for k in ("description", "quantity", "unit_price", "reference_id", "sku") if i.get(k) is not None})
                                                 for i in items])
    clean_disc, discount_total = mpq._sanitize_discounts([mpq.QuoteDiscountIn(**d) for d in (discounts or [])], subtotal)
    retention = round(sum(d["value"] for d in clean_disc if d.get("kind") == "retention"), 2)
    return {"items": clean_items, "discounts": clean_disc, "subtotal": subtotal, "discount_total": discount_total,
            "retention": retention, "total": round(max(0.0, subtotal - discount_total), 2)}


async def create(db: AsyncSession, company_id: str, body: dict, actor: str, user_id: Optional[str] = None) -> dict:
    mpq = _mpq()
    origin = body.get("origin") if body.get("origin") in ORIGINS else "manual"
    client = body.get("client") or {}
    name = str(client.get("name") or "").strip()[:220]
    if not name:
        raise QuoteError(422, "El nombre o razón social del cliente es obligatorio.")
    lines = [x for x in (body.get("lines") or []) if isinstance(x, dict)][:200]
    if not lines:
        raise QuoteError(422, "Agrega al menos una línea.")

    closure_ids: list[str] = []
    if origin == "production":
        wanted = sorted({str(i) for x in lines for i in (x.get("closure_ids") or [])})
        found = {str(c["id"]): c for c in await _closures(db, company_id, ids=wanted)} if wanted else {}
        if len(found) != len(wanted):
            raise QuoteError(422, "Algunos cierres no son de esta empresa.")
        taken = [c for c in found.values() if c["charged_quote_id"]]
        if taken:
            raise QuoteError(409, f"{sum(int(c['quantity']) for c in taken)} prendas ya se cobraron en "
                                  f"{mpq._account_number_from_quote_number(taken[0]['charged_number'])}. Vuelve a cargar el periodo.")
        for x in lines:  # la cantidad de una linea de produccion es la de sus cierres (no la que mande la pantalla)
            ids = [str(i) for i in (x.get("closure_ids") or [])]
            if ids:
                x["quantity"] = sum(int(found[i]["quantity"]) for i in ids)
                closure_ids += ids
    for x in lines:
        if x.get("unit_price") in (None, ""):
            raise QuoteError(422, f"Falta el valor por prenda de {x.get('description') or 'una línea'}.")

    t = totals(lines, body.get("discounts") or [])
    for clean, raw in zip(t["items"], [x for x in lines if str(x.get("description") or "").strip()]):
        if raw.get("sizes"):
            clean["sizes"] = [{"size": str(s.get("size") or "")[:20], "quantity": int(s.get("quantity") or 0)} for s in raw["sizes"]][:20]
        if raw.get("key"):
            clean["reference_key"] = str(raw["key"])[:120]
        if raw.get("closure_ids"):
            clean["closures"] = len(raw["closure_ids"])
    p = body.get("payment") or {}
    payment = mpq._payment_payload(mpq.QuotePaymentIn(**{k: p.get(k) for k in ("detail", "name", "method", "data") if p.get(k) is not None}))
    signature_id = None
    if body.get("signature_id"):
        sig = await saved_signature(db, company_id, body["signature_id"])
        if not sig:
            raise QuoteError(422, "Firma no encontrada.")
        signature_id = sig["id"]
    period = body.get("period") if origin == "production" and isinstance(body.get("period"), dict) else None
    metadata = {"quotes_v2": {"origin": origin, "closures": len(closure_ids), "period": period, "signature_id": signature_id}}
    account = origin == "production" or body.get("document_type") == "account"
    created_by = None
    try:
        created_by = str(uuid.UUID(str(user_id))) if user_id else None
    except ValueError:
        created_by = None

    for _attempt in range(3):
        number = await next_number(db, company_id)
        try:
            row = (await db.execute(text("""
                INSERT INTO mini_panel_quotes (company_id, panel_type, quote_number, client_name, client_document, client_address, client_phone,
                    client_email, items, discounts, payment, notes, signature_data_url, subtotal, discount_total, total, status, converted_at,
                    created_by, created_by_label, metadata, created_at, updated_at)
                VALUES (CAST(:c AS uuid), :panel, :num, :name, :doc, :addr, :phone, :email, CAST(:items AS jsonb), CAST(:disc AS jsonb),
                    CAST(:pay AS jsonb), :notes, NULL, :sub, :dt, :total, :status, CASE WHEN :account THEN now() END,
                    CAST(:by AS uuid), :label, CAST(:meta AS jsonb), now(), now())
                RETURNING id::text
            """), {"c": company_id, "panel": PANEL, "num": number, "name": name, "doc": str(client.get("document") or "")[:80] or None,
                   "addr": str(client.get("address") or "")[:260] or None, "phone": str(client.get("phone") or "")[:80] or None,
                   "email": str(client.get("email") or "")[:180] or None, "items": json.dumps(t["items"], ensure_ascii=False),
                   "disc": json.dumps(t["discounts"], ensure_ascii=False), "pay": json.dumps(payment, ensure_ascii=False),
                   "notes": str(body.get("notes") or "")[:2500] or None, "sub": t["subtotal"], "dt": t["discount_total"], "total": t["total"],
                   "status": "converted" if account else "issued", "account": account, "by": created_by, "label": actor[:180],
                   "meta": json.dumps(metadata, ensure_ascii=False)})).scalar_one()
            for cid_ in closure_ids:
                await db.execute(text("""
                    INSERT INTO quote_closure_charges (company_id, quote_id, closure_id, quantity, created_by)
                    VALUES (CAST(:c AS uuid), CAST(:q AS uuid), :cl, :n, :by)
                """), {"c": company_id, "q": row, "cl": cid_, "n": int(found[cid_]["quantity"]), "by": actor[:200]})
            await db.commit()
            return await get(db, company_id, row)
        except IntegrityError as exc:
            await db.rollback()
            if "quote_closure_charges" in str(exc.orig) or "ux_quote_closure_charges_live" in str(exc):
                raise QuoteError(409, "Otra cuenta de cobro tomó estas prendas. Vuelve a cargar el periodo.") from None
            continue  # numero repetido por otra creacion al mismo tiempo: siguiente
    raise QuoteError(409, "No se pudo numerar el documento. Intenta de nuevo.")


# ---------------------------------------------------------------- leer y acciones
async def _row(db: AsyncSession, company_id: str, quote_id: str):
    try:
        qid = str(uuid.UUID(str(quote_id)))
    except ValueError:
        return None
    return (await db.execute(text("""
        SELECT q.*, (SELECT count(*) FROM quote_closure_charges ch WHERE ch.quote_id = q.id AND ch.company_id = q.company_id
                     AND ch.released_at IS NULL) AS charged_closures
        FROM mini_panel_quotes q WHERE q.id = CAST(:q AS uuid) AND q.company_id = CAST(:c AS uuid)
    """), {"q": qid, "c": company_id})).mappings().first()


def payload(row) -> dict:
    out = _mpq()._quote_payload(row)
    meta = out.get("metadata") or {}
    out["paid_at"] = meta.get("paid_at")
    out["origin"] = (meta.get("quotes_v2") or {}).get("origin") or "legacy"
    out["charged_closures"] = int(row["charged_closures"] or 0) if "charged_closures" in row.keys() else 0
    out["retention"] = round(sum(float(d.get("value") or 0) for d in out.get("discounts") or [] if d.get("kind") == "retention"), 2)
    out.pop("signature_data_url", None)
    return out


async def get(db: AsyncSession, company_id: str, quote_id: str) -> dict:
    row = await _row(db, company_id, quote_id)
    if not row:
        raise QuoteError(404, "Documento no encontrado.")
    return payload(row)


async def archive(db: AsyncSession, company_id: str, quote_id: str) -> dict:
    """Archiva (o anula) y libera los cierres que tenia cobrados."""
    row = await _row(db, company_id, quote_id)
    if not row:
        raise QuoteError(404, "Documento no encontrado.")
    await db.execute(text("""
        UPDATE mini_panel_quotes SET status = 'archived', archived_at = now(), updated_at = now()
        WHERE id = CAST(:q AS uuid) AND company_id = CAST(:c AS uuid)
    """), {"q": str(row["id"]), "c": company_id})
    await db.execute(text("""
        UPDATE quote_closure_charges SET released_at = now(), released_reason = 'archived'
        WHERE quote_id = CAST(:q AS uuid) AND company_id = CAST(:c AS uuid) AND released_at IS NULL
    """), {"q": str(row["id"]), "c": company_id})
    await db.commit()
    return await get(db, company_id, str(row["id"]))


async def convert(db: AsyncSession, company_id: str, quote_id: str) -> dict:
    row = await _row(db, company_id, quote_id)
    if not row or row["status"] == "archived":
        raise QuoteError(404, "Documento no encontrado.")
    await db.execute(text("""
        UPDATE mini_panel_quotes SET status = 'converted', converted_at = COALESCE(converted_at, now()), updated_at = now()
        WHERE id = CAST(:q AS uuid) AND company_id = CAST(:c AS uuid) AND status <> 'archived'
    """), {"q": str(row["id"]), "c": company_id})
    await db.commit()
    return await get(db, company_id, str(row["id"]))


async def mark_paid(db: AsyncSession, company_id: str, quote_id: str, actor: str, paid: bool = True) -> dict:
    row = await _row(db, company_id, quote_id)
    if not row or row["status"] != "converted":
        raise QuoteError(409, "Solo una cuenta de cobro vigente se marca como pagada.")
    patch = {"paid_at": datetime.now(timezone.utc).isoformat(), "paid_by": actor[:180]} if paid else {"paid_at": None, "paid_by": None}
    await db.execute(text("""
        UPDATE mini_panel_quotes SET metadata = COALESCE(metadata, '{}'::jsonb) || CAST(:m AS jsonb), updated_at = now()
        WHERE id = CAST(:q AS uuid) AND company_id = CAST(:c AS uuid)
    """), {"m": json.dumps(patch), "q": str(row["id"]), "c": company_id})
    await db.commit()
    return await get(db, company_id, str(row["id"]))


def bucket_of(doc: dict) -> str:
    if doc["status"] == "archived":
        return "archived"
    if doc["status"] == "converted" and doc.get("paid_at"):
        return "paid"
    return "active"


async def history(db: AsyncSession, company_id: str, q: str = "", filt: str = "active", limit: int = 200) -> dict:
    rows = (await db.execute(text("""
        SELECT q.*, (SELECT count(*) FROM quote_closure_charges ch WHERE ch.quote_id = q.id AND ch.company_id = q.company_id
                     AND ch.released_at IS NULL) AS charged_closures
        FROM mini_panel_quotes q WHERE q.company_id = CAST(:c AS uuid) AND q.panel_type = :p
        ORDER BY q.created_at DESC LIMIT 2000
    """), {"c": company_id, "p": PANEL})).mappings().all()
    docs = [payload(r) for r in rows]
    needle = " ".join(str(q or "").lower().split())
    if needle:
        docs = [d for d in docs if needle in " ".join(str(d.get(k) or "") for k in ("client_name", "client_document", "quote_number", "account_number")).lower()]
    sums = {b: {"count": 0, "amount": 0.0} for b in ("active", "paid", "archived")}
    for d in docs:
        s = sums[bucket_of(d)]
        s["count"] += 1
        s["amount"] = round(s["amount"] + float(d["total"] or 0), 2)
    shown = docs if filt == "all" else [d for d in docs if bucket_of(d) == (filt if filt in FILTERS else "active")]
    return {"documents": shown[:limit], "totals": sums}


async def report(db: AsyncSession, company_id: str, start: date, end: date) -> dict:
    """Cobrado, por cobrar y por cliente en el periodo (fecha del documento, zona de la empresa)."""
    rows = (await db.execute(text("""
        SELECT client_name, COALESCE(client_document, '') AS client_document, status, total, metadata
        FROM mini_panel_quotes WHERE company_id = CAST(:c AS uuid) AND panel_type = :p AND status <> 'archived'
          AND (created_at AT TIME ZONE CAST(:tz AS text))::date BETWEEN :s AND :e
    """), {"c": company_id, "p": PANEL, "tz": _tz(), "s": start, "e": end})).mappings().all()
    return summarize([dict(r) for r in rows], start, end)


def summarize(rows: list[dict], start: date, end: date) -> dict:
    by_client: dict[str, dict] = {}
    out = {"quoted": 0.0, "billed": 0.0, "collected": 0.0, "pending": 0.0}
    for r in rows:
        meta = _json(r.get("metadata"), {})
        total = float(r["total"] or 0)
        key = (r["client_document"] or r["client_name"] or "").strip().lower()
        c = by_client.setdefault(key, {"client_name": r["client_name"], "client_document": r["client_document"],
                                       "quoted": 0.0, "billed": 0.0, "collected": 0.0, "pending": 0.0})
        if r["status"] == "converted":
            fields = ("billed", "collected") if meta.get("paid_at") else ("billed", "pending")
        else:
            fields = ("quoted",)
        for f in fields:
            c[f] = round(c[f] + total, 2)
            out[f] = round(out[f] + total, 2)
    return {"period": {"from": start.isoformat(), "to": end.isoformat()}, **out,
            "by_client": sorted(by_client.values(), key=lambda x: (-x["billed"], -x["quoted"], x["client_name"].lower()))}


# ---------------------------------------------------------------- firmas (bucket)
def _signature_png(data_url: str) -> bytes:
    from PIL import Image

    from app.services import brand_media

    raw_text = str(data_url or "")
    if not raw_text.startswith("data:image/") or "," not in raw_text:
        raise QuoteError(422, "La firma debe ser una imagen.")
    try:
        raw = base64.b64decode(raw_text.split(",", 1)[1], validate=False)
    except ValueError:
        raise QuoteError(422, "La firma no se pudo leer.") from None
    if len(raw) > SIGNATURE_MAX_BYTES * 4 or brand_media.sniff(raw) is None:
        raise QuoteError(422, "La firma debe ser PNG, JPG o WebP y pesar menos de 2 MB.")
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception:  # noqa: BLE001
        raise QuoteError(422, "La firma no se pudo leer.") from None
    img = img.convert("RGBA")
    img.thumbnail((SIGNATURE_MAX_PX, SIGNATURE_MAX_PX))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)  # sin metadatos
    out = buf.getvalue()
    if len(out) > SIGNATURE_MAX_BYTES:
        raise QuoteError(422, "La firma es demasiado grande.")
    return out


async def save_signature(db: AsyncSession, company_id: str, data_url: str, actor: str) -> dict:
    from app.services import brand_media

    png = _signature_png(data_url)
    if not brand_media.configured():
        raise QuoteError(503, "El almacenamiento de firmas no está disponible.")
    sid = str(uuid.uuid4())
    key = f"billing/{uuid.UUID(company_id)}/signatures/{sid}.png"
    try:
        brand_media.put_private(key, png, "image/png")
    except brand_media.StorageUnavailable as exc:
        raise QuoteError(503, str(exc)) from None
    await db.execute(text("""
        INSERT INTO quote_signatures (id, company_id, storage_key, content_type, size_bytes, created_by)
        VALUES (CAST(:i AS uuid), CAST(:c AS uuid), :k, 'image/png', :n, :by)
    """), {"i": sid, "c": company_id, "k": key, "n": len(png), "by": actor[:200]})
    await db.commit()
    return {"id": sid}


async def saved_signature(db: AsyncSession, company_id: str, signature_id: Optional[str] = None) -> Optional[dict]:
    params = {"c": company_id}
    where = "company_id = CAST(:c AS uuid) AND archived_at IS NULL"
    if signature_id:
        try:
            params["i"] = str(uuid.UUID(str(signature_id)))
        except ValueError:
            return None
        where += " AND id = CAST(:i AS uuid)"
    row = (await db.execute(text(f"SELECT id::text AS id, storage_key FROM quote_signatures WHERE {where} ORDER BY created_at DESC LIMIT 1"),
                            params)).mappings().first()
    return dict(row) if row else None


async def signature_bytes(db: AsyncSession, company_id: str, signature_id: Optional[str]) -> Optional[bytes]:
    from app.services import brand_media

    sig = await saved_signature(db, company_id, signature_id) if signature_id else None
    if not sig or not brand_media.configured():
        return None
    try:
        return brand_media.backend().get(sig["storage_key"])
    except brand_media.StorageUnavailable:
        return None


async def pdf(db: AsyncSession, company_id: str, quote_id: str, document_type: Optional[str], company: dict) -> tuple[bytes, str]:
    """El MISMO PDF de siempre (_build_quote_pdf); la firma sale del bucket en memoria."""
    mpq = _mpq()
    row = await _row(db, company_id, quote_id)
    if not row:
        raise QuoteError(404, "Documento no encontrado.")
    quote = mpq._quote_payload(row)
    sig_id = (_json(row["metadata"], {}).get("quotes_v2") or {}).get("signature_id")
    raw = await signature_bytes(db, company_id, sig_id)
    if raw:
        quote["signature_data_url"] = "data:image/png;base64," + base64.b64encode(raw).decode()
    doc_type = mpq._document_type_for_pdf(document_type, quote)
    return mpq._build_quote_pdf(quote, company, doc_type), f"{mpq._document_number_for_pdf(quote, doc_type)}.pdf"
