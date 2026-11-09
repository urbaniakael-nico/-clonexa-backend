"""Recepcion inicial de una referencia (interruptor reference_lifecycle; hoy solo Velvet) (077A).

- Al crear una referencia, la cantidad de cada talla es su meta Y su RECEPCION INICIAL: un ingreso
  normal en reference_cut_movements (origin 'recepcion_inicial', fecha de creacion). Por eso sube al
  instante el Recibido en Balance, tarjeta, cortes por fecha del editor y Produccion (todos leen los
  mismos ingresos). La bitacora registra "Referencia creada" (reference_events).
- Un corte posterior se suma como siempre. Si tiene la misma talla, fecha y cantidad que la
  recepcion inicial, se pregunta antes de guardar (posible doble conteo).
- La recepcion inicial se corrige con motivo y doble confirmacion: el ingreso original se anula
  (no se borra) y queda uno nuevo con la cantidad correcta, mas el evento con antes y despues.
- Datos existentes (backfill): solo las referencias SIN ningun ingreso reciben su recepcion inicial
  con la meta y la fecha de creacion ('carga_inicial', con lote); todas reciben "Referencia creada"
  con su fecha real. Correr dos veces no duplica nada. Todo filtra por company_id.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import references_v2 as rv2

INITIAL = "recepcion_inicial"
BACKFILL = "carga_inicial"
ORIGINS = (INITIAL, BACKFILL)
BACKFILL_ACTOR = "Carga inicial automática"


class ReceptionError(Exception):
    def __init__(self, code: str, message: str, status: int = 422, **extra: Any):
        super().__init__(message)
        self.code, self.message, self.status, self.extra = code, message, status, extra


def _local_date(value: datetime, tz) -> Any:
    return value.astimezone(tz).date() if tz is not None else value.date()


async def _event(db: AsyncSession, company_id: str, key: str, kind: str, actor: str, at: Optional[datetime] = None, reference_id: Optional[str] = None,
                 detail: Optional[dict] = None, batch_id: Optional[str] = None) -> None:
    await db.execute(text("""
        INSERT INTO reference_events (company_id, ref_key, reference_id, kind, actor, detail, batch_id, at)
        VALUES (:c, :k, :r, :kind, :by, CAST(:d AS jsonb), CAST(:b AS uuid), COALESCE(CAST(:at AS timestamptz), now()))
    """), {"c": company_id, "k": key, "r": reference_id, "kind": kind, "by": (actor or "—")[:200], "d": json.dumps(detail or {}, ensure_ascii=False),
           "b": batch_id, "at": at})


async def _has_created(db: AsyncSession, company_id: str, key: str) -> bool:
    return bool((await db.execute(text("""
        SELECT 1 FROM reference_events WHERE company_id = :c AND ref_key = :k AND kind = 'creada' AND voided_at IS NULL LIMIT 1
    """), {"c": company_id, "k": key})).first())


# ---------------------------------------------------------------- al crear
async def on_create(db: AsyncSession, company_id: str, created: list[dict], actor: str, tz) -> list[dict]:
    """created: filas recien creadas {id, name, size, initial_quantity, created_at}. Llamar SOLO con el
    interruptor encendido. Devuelve los ingresos de recepcion inicial que quedaron."""
    if not created:
        return []
    key = rv2.group_key(created[0]["name"])
    now = datetime.now().astimezone()
    if not await _has_created(db, company_id, key):
        await _event(db, company_id, key, "creada", actor, now, detail={"name": created[0]["name"], "sizes": [r["size"] for r in created]})
    out = []
    day = _local_date(now, tz)
    for r in created:
        qty = int(r.get("initial_quantity") or 0)
        if qty <= 0 or rv2.combined_sizes(r["size"]):
            continue
        row = (await db.execute(text("""
            INSERT INTO reference_cut_movements (company_id, reference_id, kind, section, size, quantity, note, event_date, created_by, origin)
            VALUES (:c, :r, 'ingreso', NULL, :z, :q, 'Recepción inicial', :d, :by, :o) RETURNING id::text
        """), {"c": company_id, "r": r["id"], "z": r["size"], "q": qty, "d": day, "by": actor[:200], "o": INITIAL})).scalar()
        out.append({"id": row, "size": r["size"], "quantity": qty, "event_date": day})
    await db.commit()
    return out


# ---------------------------------------------------------------- posible doble conteo
async def duplicates(db: AsyncSession, company_id: str, items: list) -> list[dict]:
    """Ingresos nuevos con la misma talla, fecha y cantidad que una recepcion inicial vigente de la misma referencia."""
    clean = [rv2.validate_movement(i) for i in items] if isinstance(items, list) else []
    ins = [m for m in clean if m["kind"] == "ingreso" and m["size"]]
    if not ins:
        return []
    rows = [dict(r) for r in (await db.execute(text("SELECT id, name FROM product_references WHERE company_id = :c"), {"c": company_id})).mappings().all()]
    key_of = {r["id"]: rv2.group_key(r["name"]) for r in rows}
    initial = [dict(r) for r in (await db.execute(text("""
        SELECT reference_id, size, quantity, event_date FROM reference_cut_movements
        WHERE company_id = :c AND kind = 'ingreso' AND voided_at IS NULL AND origin = ANY(CAST(:o AS text[]))
    """), {"c": company_id, "o": list(ORIGINS)})).mappings().all()]
    out = []
    for m in ins:
        k = key_of.get(m["reference_id"])
        hit = next((x for x in initial if key_of.get(x["reference_id"]) == k and rv2._fold(x["size"]).strip() == rv2._fold(m["size"]).strip()
                    and x["event_date"] == m["event_date"] and int(x["quantity"]) == m["quantity"]), None)
        if hit:
            out.append({"size": m["size"], "quantity": m["quantity"], "event_date": m["event_date"].isoformat()})
    return out


# ---------------------------------------------------------------- corregir la recepcion inicial
async def correct_initial(db: AsyncSession, company_id: str, payload: dict, actor: str) -> dict:
    try:
        mid = str(uuid.UUID(str(payload.get("movement_id") or "")))
    except ValueError:
        raise ReceptionError("no_encontrada", "Recepción inicial no encontrada.", 404) from None
    raw = payload.get("new_value")
    if isinstance(raw, bool):
        raise ReceptionError("cantidad_invalida", "Nuevo valor: escribe un número entero.")
    try:
        after = int(str(raw).strip())
    except (TypeError, ValueError):
        raise ReceptionError("cantidad_invalida", "Nuevo valor: escribe un número entero.") from None
    if not 0 <= after <= rv2.MAX_QTY:
        raise ReceptionError("cantidad_invalida", f"Nuevo valor: debe estar entre 0 y {rv2.MAX_QTY}.")
    reason = str(payload.get("reason") or "").strip()[:300]
    if len(reason) < 3:
        raise ReceptionError("motivo_requerido", "Escribe el motivo de la corrección.")
    if payload.get("confirm") is not True or payload.get("confirm_final") is not True:
        raise ReceptionError("doble_confirmacion", "La corrección necesita las dos confirmaciones.")
    row = (await db.execute(text("""
        SELECT m.id::text AS id, m.reference_id, m.size, m.quantity, m.event_date, m.origin, pr.name
        FROM reference_cut_movements m JOIN product_references pr ON pr.id = m.reference_id AND pr.company_id::text = m.company_id
        WHERE m.company_id = :c AND m.id = CAST(:i AS uuid) AND m.kind = 'ingreso' AND m.voided_at IS NULL AND m.origin = ANY(CAST(:o AS text[]))
        FOR UPDATE OF m
    """), {"c": company_id, "i": mid, "o": list(ORIGINS)})).mappings().first()
    if not row:
        raise ReceptionError("no_encontrada", "Esa recepción inicial ya no está vigente.", 404)
    before = int(row["quantity"])
    if after == before:
        raise ReceptionError("sin_cambio", "El nuevo valor es igual al actual.")
    note = f"Corregido {before} -> {after}: {reason}"[:300]
    await db.execute(text("""
        UPDATE reference_cut_movements SET voided_at = now(), voided_by = :by, void_reason = :why WHERE company_id = :c AND id = CAST(:i AS uuid)
    """), {"by": actor[:200], "why": note, "c": company_id, "i": mid})
    new_id = None
    if after > 0:
        new_id = (await db.execute(text("""
            INSERT INTO reference_cut_movements (company_id, reference_id, kind, section, size, quantity, note, event_date, created_by, origin)
            VALUES (:c, :r, 'ingreso', NULL, :z, :q, :n, :d, :by, :o) RETURNING id::text
        """), {"c": company_id, "r": row["reference_id"], "z": row["size"], "q": after, "n": f"Recepción inicial corregida: {reason}"[:500], "d": row["event_date"],
               "by": actor[:200], "o": row["origin"]})).scalar()
    await _event(db, company_id, rv2.group_key(row["name"]), "recepcion_corregida", actor, reference_id=row["reference_id"],
                 detail={"size": row["size"], "before": before, "after": after, "reason": reason, "movement_id": mid, "new_movement_id": new_id})
    await db.commit()
    return {"ok": True, "size": row["size"], "before": before, "after": after, "movement_id": new_id}


# ---------------------------------------------------------------- bitacora
async def events_for(db: AsyncSession, company_id: str, key: str) -> list[dict]:
    if not (await db.execute(text("SELECT to_regclass('public.reference_events')"))).scalar():
        return []
    rows = (await db.execute(text("""
        SELECT kind, actor, detail, at FROM reference_events WHERE company_id = :c AND ref_key = :k AND voided_at IS NULL ORDER BY at
    """), {"c": company_id, "k": key})).mappings().all()
    out = []
    for r in rows:
        detail = r["detail"] if isinstance(r["detail"], dict) else json.loads(r["detail"] or "{}")
        out.append({"kind": r["kind"], "actor": r["actor"], "detail": detail, "at": r["at"]})
    return out


# ---------------------------------------------------------------- datos existentes
async def backfill(db: AsyncSession, company_id: str, tz, apply: bool = False) -> dict:
    """Plan (y con apply, carga) para las referencias existentes. Idempotente."""
    rows = [dict(r) for r in (await db.execute(text("""
        SELECT id, name, size, COALESCE(initial_quantity, 0) AS meta, COALESCE(archived, false) AS archived, created_at
        FROM product_references WHERE company_id = :c
    """), {"c": company_id})).mappings().all()]
    with_cuts = {r["reference_id"] for r in (await db.execute(text("""
        SELECT DISTINCT reference_id FROM reference_cut_movements WHERE company_id = :c AND kind = 'ingreso'
    """), {"c": company_id})).mappings().all()}
    created_keys = {r["ref_key"] for r in (await db.execute(text("""
        SELECT DISTINCT ref_key FROM reference_events WHERE company_id = :c AND kind = 'creada' AND voided_at IS NULL
    """), {"c": company_id})).mappings().all()}
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(rv2.group_key(r["name"]), []).append(r)
    batch = str(uuid.uuid4())
    plan = {"receptions": [], "created_events": [], "skipped_combined": [], "with_cuts": []}
    for key, own in sorted(groups.items(), key=lambda kv: rv2._fold(kv[1][0]["name"])):
        active = [r for r in own if not r["archived"]]
        if not active:
            continue
        name = active[0]["name"]
        first = min(r["created_at"] for r in own if r["created_at"] is not None) if any(r["created_at"] for r in own) else None
        if key not in created_keys:
            plan["created_events"].append({"key": key, "name": name, "at": first})
        if any(r["id"] in with_cuts for r in own):
            plan["with_cuts"].append(name)
            continue
        for r in sorted(active, key=lambda x: rv2.size_key(x["size"])):
            if int(r["meta"]) <= 0:
                continue
            if rv2.combined_sizes(r["size"]):
                plan["skipped_combined"].append({"name": name, "size": r["size"], "meta": int(r["meta"])})
                continue
            plan["receptions"].append({"key": key, "reference_id": r["id"], "name": name, "size": r["size"], "quantity": int(r["meta"]),
                                       "event_date": _local_date(r["created_at"], tz) if r["created_at"] else None})
    if apply:
        for e in plan["created_events"]:
            await _event(db, company_id, e["key"], "creada", BACKFILL_ACTOR, e["at"], detail={"name": e["name"], "origin": BACKFILL}, batch_id=batch)
        for x in plan["receptions"]:
            await db.execute(text("""
                INSERT INTO reference_cut_movements (company_id, reference_id, kind, section, size, quantity, note, event_date, created_by, origin, batch_id)
                VALUES (:c, :r, 'ingreso', NULL, :z, :q, 'Recepción inicial (carga inicial automática)', COALESCE(:d, CURRENT_DATE), :by, :o, CAST(:b AS uuid))
            """), {"c": company_id, "r": x["reference_id"], "z": x["size"], "q": x["quantity"], "d": x["event_date"], "by": BACKFILL_ACTOR, "o": BACKFILL, "b": batch})
        await db.commit()
    return {"batch_id": batch if apply and (plan["receptions"] or plan["created_events"]) else None, "applied": apply, **plan}


async def undo_backfill(db: AsyncSession, company_id: str, batch_id: str) -> dict:
    """Anula (no borra) lo que cargo un lote: ingresos anulados y eventos marcados."""
    moves = await db.execute(text("""
        UPDATE reference_cut_movements SET voided_at = now(), voided_by = :by, void_reason = 'Carga inicial deshecha'
        WHERE company_id = :c AND batch_id = CAST(:b AS uuid) AND voided_at IS NULL
    """), {"c": company_id, "b": batch_id, "by": BACKFILL_ACTOR})
    events = await db.execute(text("""
        UPDATE reference_events SET voided_at = now() WHERE company_id = :c AND batch_id = CAST(:b AS uuid) AND voided_at IS NULL
    """), {"c": company_id, "b": batch_id})
    await db.commit()
    return {"movements": moves.rowcount, "events": events.rowcount}
