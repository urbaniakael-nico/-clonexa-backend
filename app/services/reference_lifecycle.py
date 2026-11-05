"""Vida de una referencia (interruptor reference_lifecycle del modulo references; hoy solo Velvet) (068A).

- Corregir producido con doble confirmacion: nada se borra; una fila de compensacion en
  reference_production_closures hace que todas las pantallas cuadren, y queda el registro.
- Renombrar: el nombre nuevo se escribe en toda la referencia y en sus copias (sesiones, cierres...),
  en una sola transaccion, con su historial. Por eso bot, reportes y PDF muestran el nombre actual.
- Cerrar por talla: el estado "cerrada" se deriva de los cierres vigentes, nunca se guarda aparte.
  Cerrar una talla apaga su bot_active; reabrir lo devuelve como estaba.
- Producido > recibido: el portal pide confirmar; el bot avisa y deja una solicitud para aprobar.

El tiempo no se reparte por talla porque el bot registra la sesion por referencia, sin talla:
se muestra "repartido por cantidad". Todo filtra por company_id.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import reference_time as rt
from app.services import references_v2 as rv2

MODULE = "references"
SWITCH = "reference_lifecycle"
CORRECTION_CHANNEL = "correccion"
APPROVED_CHANNEL = "aprobado_portal"
REASONS = {"merma": "Merma", "defecto": "Defecto", "devolucion": "Devolución", "otro": "Otro"}
MAX_QTY = rv2.MAX_QTY
# Tablas con copia del nombre: (tabla, columna del nombre). Todas se filtran por empresa.
NAME_COPIES = ("reference_work_sessions", "reference_production_closures", "reference_cycle_resets", "mini_panel_sales_records",
               "reference_produced_corrections", "reference_produced_requests")
KEY_COPIES = (("reference_op_settings", "group_key"), ("reference_op_items", "group_key"), ("reference_size_closes", "ref_key"),
              ("reference_produced_corrections", "ref_key"), ("reference_produced_requests", "ref_key"))


class LifecycleError(Exception):
    def __init__(self, code: str, message: str, status: int = 422, **extra: Any):
        super().__init__(message)
        self.code, self.message, self.status, self.extra = code, message, status, extra


async def is_on(db: AsyncSession, company_id: Any) -> bool:
    row = (await db.execute(text("""
        SELECT cm.enabled, cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id::text = :c AND lower(m.code) = :m LIMIT 1
    """), {"c": str(company_id), "m": MODULE})).mappings().first()
    if not row or not row["enabled"]:
        return False
    settings = row["settings"]
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except ValueError:
            return False
    return isinstance(settings, dict) and settings.get(SWITCH) is True


def _int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise LifecycleError("cantidad_invalida", f"{field}: escribe un número entero.")
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise LifecycleError("cantidad_invalida", f"{field}: escribe un número entero.") from None
    if number < 0 or number > MAX_QTY:
        raise LifecycleError("cantidad_invalida", f"{field}: debe estar entre 0 y {MAX_QTY}.")
    return number


def _text(value: Any, limit: int = 300) -> str:
    return str(value or "").strip()[:limit]


async def _group(db: AsyncSession, company_id: str, key: str) -> dict:
    group = next((g for g in await rv2.reference_groups(db, company_id) if g["key"] == key), None)
    if not group:
        raise LifecycleError("no_encontrada", "Referencia no encontrada.", 404)
    return group


def _same_size(a: Any, b: Any) -> bool:
    return rv2._fold(a).strip() == rv2._fold(b).strip()


def closable_lines(group: dict) -> list[dict]:
    """Las tallas que cuentan para cerrar: con fila o con cortes recibidos (las mismas que muestra Produccion)."""
    return [line for line in group["lines"] if line.get("reference_id") or line.get("received")]


def _line(group: dict, size: Any) -> Optional[dict]:
    return next((line for line in group["lines"] if _same_size(line["size"], size)), None)


# ---------------------------------------------------------------- corregir producido
async def correct_produced(db: AsyncSession, company_id: str, payload: dict, actor: str) -> dict:
    reference_id = _text(payload.get("reference_id"), 80)
    row = await rv2.reference(db, company_id, reference_id)
    if not row:
        raise LifecycleError("no_encontrada", "Referencia no encontrada.", 404)
    after = _int(payload.get("new_value"), "Nuevo valor")
    reason = _text(payload.get("reason"))
    if len(reason) < 3:
        raise LifecycleError("motivo_requerido", "Escribe el motivo de la corrección.")
    if payload.get("confirm") is not True or payload.get("confirm_final") is not True:
        raise LifecycleError("doble_confirmacion", "La corrección necesita las dos confirmaciones.")
    group = await _group(db, company_id, rv2.key_of(row))
    line = next((x for x in group["lines"] if x.get("reference_id") == reference_id), None)
    if not line:
        raise LifecycleError("no_encontrada", "Esa talla está archivada.", 409)
    before = int(line["produced"])
    if payload.get("expected_before") is not None and _int(payload.get("expected_before"), "Valor actual") != before:
        raise LifecycleError("valor_cambio", f"El producido cambió mientras corregías; ahora es {before}. Revisa e intenta de nuevo.", 409, produced=before)
    if after == before:
        raise LifecycleError("sin_cambio", "El nuevo valor es igual al actual.")
    received = int(line.get("received") or 0)
    if received > 0 and after > received and payload.get("accept_over_received") is not True:
        raise LifecycleError("supera_lo_recibido", f"{after} supera lo recibido ({received}). Confirma si es correcto.", 409, received=received)
    delta = after - before
    # Una baja se fecha en el ultimo cierre del ciclo, asi el periodo de ese cierre queda neto.
    # Un aumento son prendas nuevas: hoy. created_at siempre dice cuando se hizo.
    closed_at = None
    if delta < 0:
        closed_at = (await db.execute(text("""
            SELECT max(c.closed_at) FROM reference_production_closures c
            JOIN product_references pr ON pr.id = c.reference_id AND pr.company_id = c.company_id
            WHERE c.company_id = :c AND c.reference_id = :r AND c.quantity_finished > 0
              AND (pr.activation_date IS NULL OR c.closed_at >= pr.activation_date)
        """), {"c": company_id, "r": reference_id})).scalar()
    closure_id = str(uuid.uuid4())
    await db.execute(text("""
        INSERT INTO reference_production_closures (id, company_id, employee_id, employee_name, telegram_user_id, reference_id, reference_name, size,
            quantity_finished, notes, closed_at, source_channel, created_at)
        VALUES (:id, :c, '', 'Corrección', '', :r, :n, :z, :q, :notes, COALESCE(CAST(:at AS timestamptz), now()), :ch, now())
    """), {"id": closure_id, "c": company_id, "r": reference_id, "n": row["name"], "z": row["size"], "q": delta,
           "notes": f"Corregido {before} -> {after}: {reason}"[:500], "at": closed_at, "ch": CORRECTION_CHANNEL})
    await db.execute(text("""
        INSERT INTO reference_produced_corrections (company_id, reference_id, ref_key, reference_name, size, before_qty, after_qty, reason, closure_id, actor)
        VALUES (:c, :r, :k, :n, :z, :b, :a, :why, :cl, :by)
    """), {"c": company_id, "r": reference_id, "k": group["key"], "n": row["name"], "z": line["size"], "b": before, "a": after,
           "why": reason, "cl": closure_id, "by": actor[:200]})
    await db.commit()
    return {"ok": True, "reference_id": reference_id, "size": line["size"], "before": before, "after": after, "received": received, "over_received": received > 0 and after > received}


# ---------------------------------------------------------------- producido > recibido
async def _line_numbers(db: AsyncSession, company_id: str, reference_id: str) -> Optional[tuple[dict, dict]]:
    row = await rv2.reference(db, company_id, reference_id)
    if not row:
        return None
    group = next((g for g in await rv2.reference_groups(db, company_id) if g["key"] == rv2.key_of(row)), None)
    line = next((x for x in group["lines"] if x.get("reference_id") == reference_id), None) if group else None
    return (group, line) if line else None


async def size_is_closed(db: AsyncSession, company_id: str, key: str, size: Any) -> bool:
    return bool((await db.execute(text("""
        SELECT 1 FROM reference_size_closes WHERE company_id = :c AND ref_key = :k AND lower(size) = lower(:z) AND reopened_at IS NULL LIMIT 1
    """), {"c": company_id, "k": key, "z": str(size or "")})).first())


async def bot_close_guard(db: AsyncSession, company_id: str, reference: dict, quantity: int, employee: dict, telegram_user_id: str = "",
                          source_channel: str = "telegram") -> Optional[str]:
    """Antes de que el bot guarde un cierre. None: se registra normal (y con interruptor apagado,
    siempre). Texto: NO se registra; se avisa a la persona y, si supera lo recibido, queda una
    solicitud para aprobar en el portal. Sin cortes registrados no hay contra que comparar."""
    if not await is_on(db, company_id):
        return None
    reference_id = str(reference.get("id") or "")
    found = await _line_numbers(db, company_id, reference_id)
    if not found:
        return None
    group, line = found
    reference["name"] = group["name"]  # el nombre actual, aunque lo hayan cambiado mientras escribia
    if await size_is_closed(db, company_id, group["key"], line["size"]):
        return f"⚠️ La talla {line['size']} de {group['name']} ya está cerrada. No registré {quantity}."
    received, produced = int(line.get("received") or 0), int(line["produced"])
    if received <= 0 or produced + int(quantity) <= received:
        return None
    await db.execute(text("""
        INSERT INTO reference_produced_requests (company_id, reference_id, ref_key, reference_name, size, quantity, received, produced,
            employee_id, employee_name, telegram_user_id, source_channel)
        VALUES (:c, :r, :k, :n, :z, :q, :rec, :prod, :e, :en, :t, :ch)
    """), {"c": company_id, "r": reference_id, "k": group["key"], "n": group["name"], "z": line["size"], "q": int(quantity), "rec": received, "prod": produced,
           "e": str(employee.get("employee_id") or ""), "en": employee.get("employee_name"), "t": telegram_user_id or "", "ch": source_channel[:20]})
    return (f"⚠️ {group['name']} / talla {line['size']}: recibido {received}, ya producido {produced}. "
            f"{quantity} más supera lo recibido, así que no lo registré. Quedó pendiente de aprobación en el portal.")


async def decide_request(db: AsyncSession, company_id: str, request_id: str, approve: bool, actor: str) -> dict:
    try:
        rid = str(uuid.UUID(str(request_id)))
    except ValueError:
        raise LifecycleError("no_encontrada", "Solicitud no encontrada.", 404) from None
    row = (await db.execute(text("""
        SELECT * FROM reference_produced_requests WHERE company_id = :c AND id = CAST(:i AS uuid) AND status = 'pending' FOR UPDATE
    """), {"c": company_id, "i": rid})).mappings().first()
    if not row:
        raise LifecycleError("no_encontrada", "Esa solicitud ya fue resuelta.", 404)
    closure_id = None
    if approve:
        ref = await rv2.reference(db, company_id, row["reference_id"])
        if not ref:
            raise LifecycleError("no_encontrada", "La referencia ya no existe.", 409)
        if await size_is_closed(db, company_id, row["ref_key"], ref["size"]):
            raise LifecycleError("talla_cerrada", "Esa talla ya está cerrada; reábrela para aprobar.", 409)
        closure_id = str(uuid.uuid4())
        await db.execute(text("""
            INSERT INTO reference_production_closures (id, company_id, employee_id, employee_name, telegram_user_id, reference_id, reference_name, size,
                quantity_finished, notes, closed_at, source_channel, created_at)
            VALUES (:id, :c, :e, :en, :t, :r, :n, :z, :q, :notes, now(), :ch, now())
        """), {"id": closure_id, "c": company_id, "e": row["employee_id"], "en": row["employee_name"], "t": row["telegram_user_id"] or "", "r": row["reference_id"],
               "n": ref["name"], "z": ref["size"], "q": row["quantity"], "notes": f"Aprobado por {actor}: supera lo recibido"[:500], "ch": APPROVED_CHANNEL})
    await db.execute(text("""
        UPDATE reference_produced_requests SET status = :s, decided_by = :by, decided_at = now(), closure_id = :cl
        WHERE company_id = :c AND id = CAST(:i AS uuid)
    """), {"s": "approved" if approve else "rejected", "by": actor[:200], "cl": closure_id, "c": company_id, "i": rid})
    await db.commit()
    return {"ok": True, "status": "approved" if approve else "rejected"}


# ---------------------------------------------------------------- renombrar
def former_names(history: list[dict], key: str, current_name: str) -> list[str]:
    """Todos los nombres que tuvo la referencia, siguiendo la cadena hacia atras (del mas reciente al mas viejo)."""
    keys = {key}
    names: list[str] = []
    for item in sorted(history, key=lambda h: h["created_at"], reverse=True):
        if item["new_key"] in keys:
            keys.add(item["old_key"])
            if item["old_name"] not in names and item["old_name"] != current_name:
                names.append(item["old_name"])
    return names


async def _history(db: AsyncSession, company_id: str) -> list[dict]:
    return [dict(r) for r in (await db.execute(text("""
        SELECT old_key, new_key, old_name, new_name, actor, created_at FROM reference_name_history WHERE company_id = :c ORDER BY created_at
    """), {"c": company_id})).mappings().all()]


async def rename(db: AsyncSession, company_id: str, payload: dict, actor: str) -> dict:
    key = _text(payload.get("key"), 200)
    new_name = " ".join(str(payload.get("new_name") or "").split())[:120]
    if payload.get("confirm") is not True:
        raise LifecycleError("confirmacion", "Confirma el cambio de nombre.")
    if len(new_name) < 2:
        raise LifecycleError("nombre_invalido", "Escribe el nombre nuevo.")
    rows = [dict(r) for r in (await db.execute(text("SELECT id, name, COALESCE(archived, false) AS archived FROM product_references WHERE company_id = :c"), {"c": company_id})).mappings().all()]
    own = [r for r in rows if rv2.group_key(r["name"]) == key]
    if not own:
        raise LifecycleError("no_encontrada", "Referencia no encontrada.", 404)
    active = [r for r in own if not r["archived"]]
    old_name = (active or own)[0]["name"]
    new_key = rv2.group_key(new_name)
    if not new_key:
        raise LifecycleError("nombre_invalido", "Escribe el nombre nuevo.")
    if new_name == old_name and all(r["name"] == new_name for r in own):
        raise LifecycleError("sin_cambio", "Ese ya es el nombre de la referencia.")
    if new_key != key:
        taken = [r for r in rows if rv2.group_key(r["name"]) == new_key]
        if taken:
            state = "archivada" if all(r["archived"] for r in taken) else "activa"
            raise LifecycleError("nombre_duplicado", f"Ya existe una referencia {state} llamada {taken[0]['name']}. Usa otro nombre.", 409)
    ids = [r["id"] for r in own]
    changed: dict[str, int] = {}
    try:
        await db.execute(text("""
            UPDATE product_references SET name = :n, updated_at = now() WHERE company_id = :c AND id = ANY(CAST(:ids AS text[]))
        """), {"n": new_name, "c": company_id, "ids": ids})
        for table in NAME_COPIES:
            if not (await db.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{table}"})).scalar():
                continue
            distinct = (await db.execute(text(f"SELECT DISTINCT reference_name FROM {table} WHERE company_id::text = :c"), {"c": company_id})).scalars().all()
            names = [n for n in distinct if n is not None and rv2.group_key(n) == key]
            result = await db.execute(text(f"""
                UPDATE {table} SET reference_name = :n
                WHERE company_id::text = :c AND reference_name <> :n AND (reference_name = ANY(CAST(:names AS text[])) OR reference_id = ANY(CAST(:ids AS text[])))
            """), {"n": new_name, "c": company_id, "names": names, "ids": ids})
            if result.rowcount:
                changed[table] = result.rowcount
        if new_key != key:
            for table, column in KEY_COPIES:
                if not (await db.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{table}"})).scalar():
                    continue
                result = await db.execute(text(f"UPDATE {table} SET {column} = :new WHERE company_id::text = :c AND {column} = :old"),
                                          {"new": new_key, "old": key, "c": company_id})
                if result.rowcount:
                    changed[table] = changed.get(table, 0) + result.rowcount
        await db.execute(text("""
            INSERT INTO reference_name_history (company_id, old_key, new_key, old_name, new_name, rows_changed, actor)
            VALUES (:c, :ok, :nk, :on, :nn, CAST(:rows AS jsonb), :by)
        """), {"c": company_id, "ok": key, "nk": new_key, "on": old_name, "nn": new_name, "rows": json.dumps(changed), "by": actor[:200]})
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise LifecycleError("nombre_duplicado", "Dos tallas quedarían iguales con ese nombre. Revisa las tallas o usa otro nombre.", 409) from None
    return {"ok": True, "key": new_key, "old_name": old_name, "name": new_name, "rows_changed": changed}


async def search(db: AsyncSession, company_id: str, q: str) -> list[dict]:
    """Por nombre actual o cualquier nombre anterior: cada referencia una sola vez, con su nombre actual."""
    def loose(value: Any) -> str:  # "Choco Fresa" encuentra "Choco-fresa"
        return re.sub(r"[^a-z0-9]", "", rv2.group_key(value)) or rv2.group_key(value)

    needle = loose(q)
    if not needle:
        return []
    history = await _history(db, company_id)
    out = []
    for g in await rv2.reference_groups(db, company_id):
        before = former_names(history, g["key"], g["name"])
        if any(needle in loose(n) for n in (g["name"], *before)):
            out.append({"key": g["key"], "name": g["name"], "former_names": before})
    return out


# ---------------------------------------------------------------- cerrar por talla
async def _open_sessions(db: AsyncSession, company_id: str, key: str) -> list[str]:
    rows = (await db.execute(text("""
        SELECT reference_name, employee_name FROM reference_work_sessions
        WHERE company_id = :c AND (ended_at IS NULL OR lower(COALESCE(status, '')) = 'active')
    """), {"c": company_id})).mappings().all()
    return sorted({str(r["employee_name"] or "—") for r in rows if rv2.group_key(r["reference_name"]) == key})


async def _live_closes(db: AsyncSession, company_id: str, key: Optional[str] = None) -> list[dict]:
    return [dict(r) for r in (await db.execute(text("""
        SELECT id::text AS id, ref_key, size, reference_id, closed_qty, meta, received, reason_code, reason_note, prev_bot_active, prev_channel, actor, closed_at
        FROM reference_size_closes WHERE company_id = :c AND reopened_at IS NULL AND (CAST(:k AS text) IS NULL OR ref_key = :k) ORDER BY closed_at
    """), {"c": company_id, "k": key})).mappings().all()]


async def close_size(db: AsyncSession, company_id: str, payload: dict, actor: str) -> dict:
    key, size = _text(payload.get("key"), 200), _text(payload.get("size"), 60)
    if payload.get("confirm") is not True:
        raise LifecycleError("confirmacion", "Confirma el cierre de la talla.")
    qty = _int(payload.get("closed_qty"), "Cantidad cerrada")
    group = await _group(db, company_id, key)
    line = _line(group, size)
    if not line or line not in closable_lines(group):
        raise LifecycleError("no_encontrada", "Esa talla no existe en la referencia.", 404)
    if await size_is_closed(db, company_id, key, line["size"]):
        raise LifecycleError("ya_cerrada", f"La talla {line['size']} ya está cerrada.", 409)
    received = int(line.get("received") or 0)
    code, note = _text(payload.get("reason_code"), 20) or None, _text(payload.get("reason_note"))
    if qty < received:
        if code not in REASONS:
            raise LifecycleError("motivo_requerido", f"Cerraste menos de lo recibido ({qty} de {received}). Elige el motivo.", received=received)
        if code == "otro" and len(note) < 3:
            raise LifecycleError("motivo_requerido", "Escribe el motivo.")
    elif code not in REASONS:
        code = None
    pending = [x for x in closable_lines(group) if x is not line]
    closes = await _live_closes(db, company_id, key)
    last = all(any(_same_size(c["size"], x["size"]) for c in closes) for x in pending)
    if last:
        people = await _open_sessions(db, company_id, key)
        if people:
            raise LifecycleError("sesiones_abiertas", f"Hay sesiones sin cerrar en esta referencia: {', '.join(people)}. Ciérralas antes de cerrar la última talla.", 409, people=people)
    prev = line.get("bot_active") if line.get("reference_id") else None
    prev_channel = None
    if line.get("reference_id"):
        prev_channel = (await db.execute(text("SELECT channel FROM product_references WHERE company_id = :c AND id = :i"),
                                         {"c": company_id, "i": line["reference_id"]})).scalar()
    try:
        await db.execute(text("""
            INSERT INTO reference_size_closes (company_id, ref_key, size, reference_id, closed_qty, meta, received, reason_code, reason_note, prev_bot_active, prev_channel, actor)
            VALUES (:c, :k, :z, :r, :q, :m, :rec, :code, :note, :prev, :ch, :by)
        """), {"c": company_id, "k": key, "z": line["size"], "r": line.get("reference_id"), "q": qty, "m": int(line["meta"]), "rec": received,
               "code": code, "note": note or None, "prev": prev, "ch": prev_channel, "by": actor[:200]})
    except IntegrityError:
        await db.rollback()
        raise LifecycleError("ya_cerrada", f"La talla {line['size']} ya está cerrada.", 409) from None
    if line.get("reference_id") and prev:
        await db.execute(text("""
            UPDATE product_references SET bot_active = false, channel = 'system', system_active = true, updated_at = now() WHERE company_id = :c AND id = :i
        """), {"c": company_id, "i": line["reference_id"]})
    await db.commit()
    return {"ok": True, "size": line["size"], "closed_qty": qty, "reference_closed": last}


async def reopen(db: AsyncSession, company_id: str, payload: dict, actor: str) -> dict:
    """Reabre una talla (size) o toda la referencia (sin size), con doble confirmacion y motivo."""
    key, size = _text(payload.get("key"), 200), _text(payload.get("size"), 60)
    reason = _text(payload.get("reason"))
    if payload.get("confirm") is not True or payload.get("confirm_final") is not True:
        raise LifecycleError("doble_confirmacion", "Reabrir necesita las dos confirmaciones.")
    if len(reason) < 3:
        raise LifecycleError("motivo_requerido", "Escribe el motivo para reabrir.")
    closes = await _live_closes(db, company_id, key)
    targets = [c for c in closes if not size or _same_size(c["size"], size)]
    if not targets:
        raise LifecycleError("no_encontrada", "No hay cierre vigente para reabrir.", 404)
    for c in targets:
        await db.execute(text("""
            UPDATE reference_size_closes SET reopened_at = now(), reopened_by = :by, reopen_reason = :why WHERE company_id = :co AND id = CAST(:i AS uuid)
        """), {"by": actor[:200], "why": reason, "co": company_id, "i": c["id"]})
        if c["reference_id"] and c["prev_bot_active"]:
            await db.execute(text("""
                UPDATE product_references SET bot_active = true, channel = :ch, system_active = :sys, updated_at = now() WHERE company_id = :co AND id = :i
            """), {"ch": c["prev_channel"] or "bot", "sys": (c["prev_channel"] or "bot") != "bot", "co": company_id, "i": c["reference_id"]})
    await db.commit()
    return {"ok": True, "reopened": [c["size"] for c in targets]}


async def guard_patch(db: AsyncSession, company_id: str, current: dict, new_name: str, new_bot_active: bool) -> None:
    """El PATCH de siempre no puede saltarse el historial de nombres ni reactivar en el bot una talla cerrada."""
    if new_name != current.get("name"):
        raise LifecycleError("usa_cambiar_nombre", "Usa el botón Cambiar nombre: así se conserva el historial.", 409)
    if new_bot_active and await size_is_closed(db, company_id, rv2.group_key(current.get("name")), current.get("size")):
        raise LifecycleError("talla_cerrada", "Esa talla está cerrada; reábrela para mostrarla en el bot.", 409)


# ---------------------------------------------------------------- cuentas por talla
def allocate(total: int, weights: list[int]) -> list[int]:
    """Reparte en proporcion a las prendas, sin perder ni un segundo (mayor residuo).
    Sin prendas en ninguna talla, por partes iguales."""
    if not weights:
        return []
    weights = weights if sum(weights) > 0 else [1] * len(weights)
    whole = sum(weights)
    shares = [total * w / whole for w in weights]
    out = [int(s) for s in shares]
    for i in sorted(range(len(shares)), key=lambda n: (out[n] - shares[n], n))[: total - sum(out)]:
        out[i] += 1
    return out


def _local_day(value: Any, tz) -> Optional[date]:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.astimezone(tz).date() if isinstance(value, datetime) else None


def accounts(group: dict, closes: list[dict], time_info: Optional[dict], labor: Optional[dict], tz) -> dict:
    """La cuenta de cada talla y el total (suma de las tallas). Funcion pura.

    labor: {"status": ok|pendiente, "amount", "missing": [...]}; sin valor hora -> "Pendiente"."""
    lines = closable_lines(group)
    total_seconds = int((time_info or {}).get("total_seconds") or 0)
    first = _local_day((time_info or {}).get("first"), tz)
    live = {rv2._fold(c["size"]).strip(): c for c in closes}
    qty_of = [int(live[rv2._fold(x["size"]).strip()]["closed_qty"]) if rv2._fold(x["size"]).strip() in live else int(x["produced"]) for x in lines]
    secs = allocate(total_seconds, qty_of)
    labor_ok = bool(labor and labor.get("status") == "ok")
    amount = float(labor["amount"]) if labor_ok else 0.0
    cents = allocate(round(amount * 100), qty_of) if labor_ok else [0] * len(lines)
    rows = []
    for line, qty, seconds, money_cents in zip(lines, qty_of, secs, cents):
        c = live.get(rv2._fold(line["size"]).strip())
        closed_day = _local_day(c["closed_at"], tz) if c else None
        received, meta = int(line.get("received") or 0), int(line["meta"])
        rows.append({
            "size": line["size"], "reference_id": line.get("reference_id"), "meta": meta, "received": received, "produced": int(line["produced"]),
            "closed": bool(c), "closed_qty": int(c["closed_qty"]) if c else None, "diff_meta": int(c["closed_qty"]) - meta if c else None,
            "diff_received": int(c["closed_qty"]) - received if c else None, "reason_code": c["reason_code"] if c else None,
            "reason_label": REASONS.get(c["reason_code"]) if c and c["reason_code"] else None, "reason_note": c["reason_note"] if c else None,
            "closed_at": c["closed_at"].isoformat() if c and isinstance(c["closed_at"], datetime) else None, "closed_by": c["actor"] if c else None,
            "days": (closed_day - first).days + 1 if closed_day and first else None, "seconds": seconds,
            # Por prenda solo con prendas CERRADAS; una talla abierta no tiene cifra.
            "minutes_per_garment": round(seconds / qty / 60, 1) if c and qty > 0 else None,
            "labor": money_cents / 100 if labor_ok else None, "labor_per_garment": round(money_cents / 100 / qty, 2) if c and labor_ok and qty > 0 else None,
        })
    closed_total = sum(q for q, r in zip(qty_of, rows) if r["closed"])
    garments = sum(qty_of)
    closed_seconds = sum(r["seconds"] for r in rows if r["closed"])
    closed_cents = sum(cent for cent, r in zip(cents, rows) if r["closed"])
    is_closed = bool(lines) and all(r["closed"] for r in rows)
    days = [r["days"] for r in rows if r["days"]]
    return {
        "sizes": rows, "allocation": "repartido por cantidad", "status": "closed" if is_closed else "open", "closed_sizes": sum(1 for r in rows if r["closed"]), "total_sizes": len(rows),
        "labor_status": labor.get("status") if labor else "pendiente", "labor_missing": (labor or {}).get("missing") or [],
        "totals": {"closed_qty": closed_total, "garments": garments, "meta": sum(r["meta"] for r in rows), "received": sum(r["received"] for r in rows),
                   "seconds": sum(r["seconds"] for r in rows), "labor": round(sum(cents) / 100, 2) if labor_ok else None, "days": max(days) if days else None,
                   "minutes_per_garment": round(closed_seconds / closed_total / 60, 1) if closed_total > 0 else None,
                   "labor_per_garment": round(closed_cents / 100 / closed_total, 2) if labor_ok and closed_total > 0 else None},
    }


# ---------------------------------------------------------------- mano de obra
async def month_rates(db: AsyncSession, company_id: str, months: set[date]) -> dict[date, dict[str, float]]:
    """Valor de la hora de cada persona en cada mes: bruto de nomina / minutos pagados, con el mismo
    calculo de Nomina (calculate_period_snapshot). Sin valor hora o sin nomina, no aparece (Pendiente)."""
    from app.api.v1.endpoints.payroll import calculate_period_snapshot

    out: dict[date, dict[str, float]] = {}
    for month in sorted(months):
        next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        rates: dict[str, float] = {}
        try:
            snapshot = await calculate_period_snapshot(db, uuid.UUID(str(company_id)), month, next_month - timedelta(days=1))
            for row in snapshot.get("rows") or []:
                minutes = float(row.get("regular_minutes") or 0) + float(row.get("extra_minutes") or 0)
                gross = float(row.get("gross_amount") or 0)
                if minutes > 0 and gross > 0:
                    rates[str(row.get("employee_id"))] = gross / minutes / 60
        except Exception:  # noqa: BLE001 - sin nomina esa parte queda "Pendiente"
            await db.rollback()
        out[month] = rates
    return out


def _segment_month(segment: rt.Segment, tz) -> date:
    return segment[0].astimezone(tz).date().replace(day=1)


def months_of(items: list[dict], tz, lo: Optional[datetime] = None, hi: Optional[datetime] = None) -> set[date]:
    return {_segment_month(seg, tz) for it in items for seg in it["segments"] if rt.overlap_seconds([seg], lo, hi) > 0}


def labor_of(items: list[dict], rates: dict[date, dict[str, float]], tz, lo: Optional[datetime] = None, hi: Optional[datetime] = None) -> dict:
    """Mano de obra = horas de cada operario en la referencia × su valor hora de ese mes."""
    amount, missing = 0.0, set()
    for it in items:
        for seg in it["segments"]:
            seconds = rt.overlap_seconds([seg], lo, hi)
            if seconds <= 0:
                continue
            rate = rates.get(_segment_month(seg, tz), {}).get(it["employee_id"])
            if rate is None:
                missing.add(it["person"])
            else:
                amount += seconds * rate
    if missing:
        return {"status": "pendiente", "amount": None, "missing": sorted(missing)}
    return {"status": "ok", "amount": round(amount, 2), "missing": []}


# ---------------------------------------------------------------- estado (pantallas)
async def state(db: AsyncSession, company_id: str, groups: Optional[list[dict]] = None) -> dict[str, dict]:
    """{key: nombres anteriores, historial, correcciones, cierres, solicitudes y estado}. Sin calculos de nomina."""
    groups = groups if groups is not None else await rv2.reference_groups(db, company_id)
    history = await _history(db, company_id)
    closes = await _live_closes(db, company_id)
    corrections = [dict(r) for r in (await db.execute(text("""
        SELECT ref_key, reference_id, size, before_qty, after_qty, reason, actor, created_at FROM reference_produced_corrections WHERE company_id = :c ORDER BY created_at DESC
    """), {"c": company_id})).mappings().all()]
    reopened = [dict(r) for r in (await db.execute(text("""
        SELECT ref_key, size, closed_qty, reopened_at, reopened_by, reopen_reason FROM reference_size_closes
        WHERE company_id = :c AND reopened_at IS NOT NULL ORDER BY reopened_at DESC
    """), {"c": company_id})).mappings().all()]
    requests = [dict(r) for r in (await db.execute(text("""
        SELECT id::text AS id, ref_key, reference_id, size, quantity, received, produced, employee_name, created_at
        FROM reference_produced_requests WHERE company_id = :c AND status = 'pending' ORDER BY created_at
    """), {"c": company_id})).mappings().all()]
    out: dict[str, dict] = {}
    for g in groups:
        k = g["key"]
        own = [c for c in closes if c["ref_key"] == k]
        lines = closable_lines(g)
        out[k] = {
            "former_names": former_names(history, k, g["name"]),
            "renames": [{"old_name": h["old_name"], "new_name": h["new_name"], "actor": h["actor"], "at": _iso(h["created_at"])} for h in reversed(history) if h["new_key"] == k],
            "corrections": [{"reference_id": c["reference_id"], "size": c["size"], "before": c["before_qty"], "after": c["after_qty"], "reason": c["reason"], "actor": c["actor"], "at": _iso(c["created_at"])}
                            for c in corrections if c["ref_key"] == k],
            "closes": [{"size": c["size"], "closed_qty": c["closed_qty"], "reason_code": c["reason_code"], "actor": c["actor"], "at": _iso(c["closed_at"])} for c in own],
            "reopened": [{"size": r["size"], "closed_qty": r["closed_qty"], "reason": r["reopen_reason"], "actor": r["reopened_by"], "at": _iso(r["reopened_at"])}
                         for r in reopened if r["ref_key"] == k],
            "requests": [{"id": r["id"], "size": r["size"], "quantity": r["quantity"], "received": r["received"], "produced": r["produced"], "employee": r["employee_name"], "at": _iso(r["created_at"])}
                         for r in requests if r["ref_key"] == k],
            "status": "closed" if lines and all(any(_same_size(c["size"], x["size"]) for c in own) for x in lines) else "open",
        }
    return out


def _iso(value: Any) -> Optional[str]:
    return value.isoformat() if isinstance(value, (datetime, date)) else value


async def account(db: AsyncSession, company_id: str, key: str, tz) -> dict:
    group = await _group(db, company_id, key)
    items = [it for it in await rt.load(db, company_id) if it["key"] == key]
    info = rt.summarize(items, None, None).get(key)
    rates = await month_rates(db, company_id, months_of(items, tz))
    labor = labor_of(items, rates, tz)
    result = accounts(group, await _live_closes(db, company_id, key), info, labor, tz)
    return {"key": key, "name": group["name"], "time": _time_public(info), **result}


def _time_public(info: Optional[dict]) -> dict:
    info = info or {}
    return {"total_seconds": int(info.get("total_seconds") or 0), "people": info.get("people") or [], "unclosed": info.get("unclosed") or [],
            "first": info.get("first"), "last": info.get("last")}


# ---------------------------------------------------------------- Produccion v2
async def production_bundle(db: AsyncSession, company_id: str, groups: list[dict], start: date, end: date, tz) -> dict:
    """Todo lo que Produccion necesita ANTES de armar el tablero (ver production_v2.insights)."""
    items = await rt.load(db, company_id)
    lo, hi = rt.period_bounds(start, end, tz)
    summary = rt.summarize(items, lo, hi)
    st = await state(db, company_id, groups)
    return {"items": items, "lo": lo, "hi": hi, "summary": summary, "state": st, "tz": tz,
            "closed_keys": {k for k, v in st.items() if v["status"] == "closed"},
            "time_by_ref": [{"key": k, "name": v["name"], "seconds": v["period_seconds"], "active": 0} for k, v in summary.items()],
            "time_by_person": [{"key": k, "person": p["name"], "seconds": p["period_seconds"]} for k, v in summary.items() for p in v["people"]],
            "team_seconds": sum(v["period_seconds"] for v in summary.values())}


async def decorate_insights(db: AsyncSession, company_id: str, out: dict, bundle: dict, groups: list[dict]) -> dict:
    """Agrega al tablero las dos cifras por lote, las cuentas por talla y las referencias cerradas."""
    tz, items, summary, st = bundle["tz"], bundle["items"], bundle["summary"], bundle["state"]
    lo, hi = bundle["lo"], bundle["hi"]
    all_lots = out.pop("all_lots", [])
    by_group = {g["key"]: g for g in groups}
    closed_lots = [lot for lot in all_lots if lot["key"] in bundle["closed_keys"]]
    visible = out["lots_in_process"] + closed_lots
    visible_keys = {lot["key"] for lot in visible}
    closes = await _live_closes(db, company_id)
    needed = months_of([it for it in items if it["key"] in visible_keys], tz) | months_of(items, tz, lo, hi)
    rates = await month_rates(db, company_id, needed)
    for lot in visible:
        k = lot["key"]
        info = summary.get(k)
        own = [it for it in items if it["key"] == k]
        lot["total_seconds"] = int((info or {}).get("total_seconds") or 0)
        lot["period_seconds"] = int((info or {}).get("period_seconds") or 0)
        lot["unclosed"] = (info or {}).get("unclosed") or []
        lot["people"] = (info or {}).get("people") or []
        lot["team"] = [p["name"] for p in lot["people"]]
        lot["former_names"] = (st.get(k) or {}).get("former_names") or []
        lot["corrections"] = (st.get(k) or {}).get("corrections") or []
        lot["account"] = accounts(by_group[k], [c for c in closes if c["ref_key"] == k], info, labor_of(own, rates, tz), tz)
    closed_lots.sort(key=lambda lot: max((s["closed_at"] or "" for s in lot["account"]["sizes"]), default=""), reverse=True)
    out["lots_closed"] = closed_lots
    out["unclosed_sessions"] = sum(len(v["unclosed"]) for v in summary.values())
    out["lifecycle"] = True
    kpi = out["kpis"]
    closed_period = (kpi.get("closed") or {}).get("value") or 0
    if closed_period > 0:
        labor = labor_of(items, rates, tz, lo, hi)
        if labor["status"] == "pendiente":
            kpi["labor_per_garment"] = {"status": "pendiente", "value": None, "reason": "Falta valor hora: " + ", ".join(labor["missing"])}
        elif labor["amount"] > 0:
            kpi["labor_per_garment"] = {"status": "ok", "value": round(labor["amount"] / closed_period, 2), "labor": labor["amount"]}
    return out


# ---------------------------------------------------------------- utilidades de cierre de bot en CRM
async def over_limit(db: AsyncSession, company_id: str, reference_id: str) -> Optional[int]:
    """Cuanto cabe todavia segun lo recibido (para la tableta); None sin interruptor o sin cortes."""
    if not await is_on(db, company_id):
        return None
    found = await _line_numbers(db, company_id, reference_id)
    if not found:
        return None
    _, line = found
    received = int(line.get("received") or 0)
    return max(received - int(line["produced"]), 0) if received > 0 else None
