"""Facturacion de Clonexa a sus clientes (empresas registradas; las demos no facturan).

Reglas (puras, probadas sin base):
- Cuota N = mes de inicio + (N-1). Ventana de pago: del dia `pay_day_from` al
  `pay_day_to` de ese mes; fecha limite = `pay_day_to`.
- Valor de la cuota N = el del tramo que contiene N (desde el mes N hasta el
  mes M; el ultimo tramo puede quedar abierto).
- Estado: anulada > pagada (pagos validados >= valor) > en mora (despues de
  la fecha limite) > en ventana (dentro de la ventana; "vence en N dias") >
  pendiente. Solo avisa: nunca suspende ni bloquea nada.
- Comprobantes: numero de una secuencia de Postgres (nunca se repite ni se
  reutiliza). Anular un pago marca su comprobante como anulado; no se borra.
- No se guardan numeros de tarjeta ni de cuentas: una referencia con 13 o
  mas digitos seguidos se rechaza.
Toda consulta filtra por company_id.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

TZ = ZoneInfo("America/Bogota")
STATUSES = ("vigente", "pausado", "terminado")
METHODS = {"transferencia": "Transferencia", "efectivo": "Efectivo", "consignacion": "Consignación", "nequi": "Nequi",
           "daviplata": "Daviplata", "tarjeta": "Tarjeta", "otro": "Otro"}
INSTALLMENT_LABELS = {"pendiente": "Pendiente", "en_ventana": "En ventana de pago", "pagada": "Pagada", "en_mora": "En mora", "anulada": "Anulada"}
MONTHS_ES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
AHEAD = 2  # cuotas futuras que se muestran en el calendario
WARN_DAYS = 3
_CARD_LIKE = re.compile(r"\d{13,}")


class BillingInvalid(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


class BillingConflict(Exception):
    """Accion imposible en el estado actual."""


def today_bogota() -> date:
    return datetime.now(TZ).date()


def money(value: Any) -> Decimal:
    try:
        d = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise BillingInvalid("valor", "debe ser un número") from None
    if d < 0 or d > Decimal("1000000000000"):
        raise BillingInvalid("valor", "fuera de rango")
    return d


def period_label(period: date) -> str:
    return f"{MONTHS_ES[period.month - 1].capitalize()} {period.year}"


def receipt_code(number: int) -> str:
    return f"CX-{int(number):06d}"


# ------------------------------------------------------------- reglas puras ---
def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def tier_amount(tiers: list[dict], seq: int) -> Decimal:
    for t in sorted(tiers, key=lambda t: t["month_from"]):
        if t["month_from"] <= seq and (t.get("month_to") is None or seq <= t["month_to"]):
            return Decimal(str(t["amount"]))
    return Decimal("0")


def schedule_for(contract: dict, tiers: list[dict], upto: date) -> list[dict]:
    """Cuotas desde la primera hasta el periodo de `upto` (incluido)."""
    first = date(contract["start_date"].year, contract["start_date"].month, 1)
    last = date(upto.year, upto.month, 1)
    out, seq = [], 1
    period = first
    while period <= last and seq <= 600:
        out.append({"seq": seq, "period": period, "amount": tier_amount(tiers, seq),
                    "due_from": period.replace(day=int(contract["pay_day_from"])), "due_date": period.replace(day=int(contract["pay_day_to"]))})
        seq += 1
        period = add_months(first, seq - 1)
    return out


def status_of(inst: dict, validated: Decimal, today: date) -> dict:
    """{status, days_late, days_left} de una cuota."""
    if inst.get("voided"):
        return {"status": "anulada", "days_late": 0, "days_left": None}
    amount = Decimal(str(inst["amount"]))
    if validated >= amount and (amount > 0 or validated > 0):
        return {"status": "pagada", "days_late": 0, "days_left": None}
    if amount == 0:
        return {"status": "pagada", "days_late": 0, "days_left": None}
    if today > inst["due_date"]:
        return {"status": "en_mora", "days_late": (today - inst["due_date"]).days, "days_left": None}
    if inst["due_from"] <= today <= inst["due_date"]:
        return {"status": "en_ventana", "days_late": 0, "days_left": (inst["due_date"] - today).days}
    return {"status": "pendiente", "days_late": 0, "days_left": (inst["due_date"] - today).days}


def validate_contract(raw: dict, types: set[str]) -> dict:
    if not isinstance(raw, dict):
        raise BillingInvalid("contrato", "datos inválidos")
    ctype = str(raw.get("contract_type") or "").strip()
    if ctype not in types:
        raise BillingInvalid("contract_type", "tipo de contrato no permitido")
    try:
        start = date.fromisoformat(str(raw.get("start_date") or ""))
    except ValueError:
        raise BillingInvalid("start_date", "fecha inválida (AAAA-MM-DD)") from None
    def whole(name: str, low: int, high: int, default: Optional[int] = None) -> int:
        value = raw.get(name, default)
        if isinstance(value, bool) or value in (None, ""):
            raise BillingInvalid(name, "falta")
        try:
            n = int(value)
        except (TypeError, ValueError):
            raise BillingInvalid(name, "debe ser un número entero") from None
        if not low <= n <= high:
            raise BillingInvalid(name, f"fuera de rango ({low} a {high})")
        return n
    day_from, day_to = whole("pay_day_from", 1, 28), whole("pay_day_to", 1, 28)
    if day_to < day_from:
        raise BillingInvalid("pay_day_to", "el día hasta no puede ser antes del día desde")
    currency = str(raw.get("currency") or "COP").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise BillingInvalid("currency", "moneda de 3 letras (COP, USD…)")
    status = str(raw.get("status") or "vigente")
    if status not in STATUSES:
        raise BillingInvalid("status", "estado no permitido")
    notes = str(raw.get("notes") or "").strip()
    if len(notes) > 2000:
        raise BillingInvalid("notes", "máximo 2000 caracteres")
    tiers_raw = raw.get("tiers")
    if not isinstance(tiers_raw, list) or not 1 <= len(tiers_raw) <= 12:
        raise BillingInvalid("tiers", "entre 1 y 12 tramos de precio")
    tiers, expected = [], 1
    for i, t in enumerate(sorted(tiers_raw, key=lambda t: int((t or {}).get("month_from") or 0))):
        if not isinstance(t, dict):
            raise BillingInvalid(f"tiers[{i}]", "tramo inválido")
        frm = int(t.get("month_from") or 0)
        to = t.get("month_to")
        to = None if to in (None, "") else int(to)
        if frm != expected:
            raise BillingInvalid(f"tiers[{i}].month_from", f"los tramos van seguidos desde el mes 1 (se esperaba el mes {expected})")
        if to is not None and to < frm:
            raise BillingInvalid(f"tiers[{i}].month_to", "el mes hasta no puede ser antes del mes desde")
        if to is None and i != len(tiers_raw) - 1:
            raise BillingInvalid(f"tiers[{i}].month_to", "solo el último tramo puede quedar abierto")
        tiers.append({"month_from": frm, "month_to": to, "amount": money(t.get("amount"))})
        expected = (to or frm) + 1
    if tiers[-1]["month_to"] is not None:
        raise BillingInvalid("tiers", "el último tramo debe quedar abierto (\"en adelante\")")
    return {"contract_type": ctype, "start_date": start, "min_months": whole("min_months", 0, 120, 0), "currency": currency,
            "pay_day_from": day_from, "pay_day_to": day_to, "notes": notes, "status": status, "tiers": tiers}


def validate_payment(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise BillingInvalid("pago", "datos inválidos")
    method = str(raw.get("method") or "").strip()
    if method not in METHODS:
        raise BillingInvalid("method", "medio de pago no permitido")
    reference = str(raw.get("reference") or "").strip()
    if len(reference) > 60:
        raise BillingInvalid("reference", "máximo 60 caracteres")
    if _CARD_LIKE.search(re.sub(r"[\s.-]", "", reference)):
        raise BillingInvalid("reference", "no escribas números de tarjeta ni de cuentas bancarias; usa el código de la transacción")
    note = str(raw.get("note") or "").strip()
    if len(note) > 500:
        raise BillingInvalid("note", "máximo 500 caracteres")
    if _CARD_LIKE.search(re.sub(r"[\s.-]", "", note)):
        raise BillingInvalid("note", "no escribas números de tarjeta ni de cuentas bancarias")
    try:
        paid_on = date.fromisoformat(str(raw.get("paid_on") or ""))
    except ValueError:
        raise BillingInvalid("paid_on", "fecha inválida (AAAA-MM-DD)") from None
    amount = money(raw.get("amount"))
    if amount <= 0:
        raise BillingInvalid("amount", "el valor debe ser mayor que cero")
    try:
        inst = str(uuid.UUID(str(raw.get("installment_id"))))
    except (ValueError, TypeError):
        raise BillingInvalid("installment_id", "cuota inválida") from None
    return {"installment_id": inst, "amount": amount, "paid_on": paid_on, "method": method, "reference": reference, "note": note}


# ------------------------------------------------------------------- base ---
def _row(r: Any) -> dict:
    return dict(r) if r is not None else None


async def contract_types(db: AsyncSession, active_only: bool = True) -> list[dict]:
    rows = (await db.execute(text(f"""
        SELECT code, label, active FROM billing_contract_types {"WHERE active IS TRUE" if active_only else ""} ORDER BY sort, label
    """))).mappings().all()
    return [dict(r) for r in rows]


async def add_contract_type(db: AsyncSession, label: str) -> dict:
    label = str(label or "").strip()
    if not 2 <= len(label) <= 80:
        raise BillingInvalid("label", "entre 2 y 80 caracteres")
    code = re.sub(r"[^a-z0-9]+", "_", label.lower().encode("ascii", "ignore").decode()).strip("_")[:40] or "tipo"
    await db.execute(text("""
        INSERT INTO billing_contract_types (code, label, sort) VALUES (:c, :l, 50)
        ON CONFLICT (code) DO UPDATE SET label = EXCLUDED.label, active = true
    """), {"c": code, "l": label})
    await db.commit()
    return {"code": code, "label": label}


async def registered_companies(db: AsyncSession) -> list[dict]:
    """Empresas que facturan: registradas y no archivadas (las demos no)."""
    from app.services.company_kind import REGISTERED, resolve_kind

    rows = (await db.execute(text("""
        SELECT id::text AS id, name, slug, status, settings_json FROM companies
        WHERE LOWER(COALESCE(status, '')) NOT IN ('archived', 'deleted') ORDER BY name
    """))).mappings().all()
    return [{"id": r["id"], "name": r["name"], "slug": r["slug"], "status": r["status"]} for r in rows
            if resolve_kind(r["id"], r["settings_json"]) == REGISTERED]


async def is_registered(db: AsyncSession, company_id: str) -> bool:
    return any(c["id"] == company_id for c in await registered_companies(db))


async def get_contract(db: AsyncSession, company_id: str) -> Optional[dict]:
    row = (await db.execute(text("""
        SELECT id::text AS id, company_id::text AS company_id, contract_type, start_date, min_months, currency, pay_day_from, pay_day_to,
               notes, status, created_at, updated_at
        FROM billing_contracts WHERE company_id = CAST(:c AS uuid)
    """), {"c": company_id})).mappings().first()
    if not row:
        return None
    contract = dict(row)
    tiers = (await db.execute(text("""
        SELECT month_from, month_to, amount FROM billing_price_tiers WHERE contract_id = CAST(:k AS uuid) ORDER BY month_from
    """), {"k": contract["id"]})).mappings().all()
    contract["tiers"] = [{"month_from": t["month_from"], "month_to": t["month_to"], "amount": Decimal(str(t["amount"]))} for t in tiers]
    return contract


async def save_contract(db: AsyncSession, company_id: str, raw: dict) -> dict:
    data = validate_contract(raw, {t["code"] for t in await contract_types(db)})
    row = (await db.execute(text("""
        INSERT INTO billing_contracts (company_id, contract_type, start_date, min_months, currency, pay_day_from, pay_day_to, notes, status)
        VALUES (CAST(:c AS uuid), :t, :s, :m, :cur, :df, :dt, :n, :st)
        ON CONFLICT (company_id) DO UPDATE SET contract_type = EXCLUDED.contract_type, start_date = EXCLUDED.start_date,
            min_months = EXCLUDED.min_months, currency = EXCLUDED.currency, pay_day_from = EXCLUDED.pay_day_from,
            pay_day_to = EXCLUDED.pay_day_to, notes = EXCLUDED.notes, status = EXCLUDED.status, updated_at = now()
        RETURNING id::text AS id
    """), {"c": company_id, "t": data["contract_type"], "s": data["start_date"], "m": data["min_months"], "cur": data["currency"],
           "df": data["pay_day_from"], "dt": data["pay_day_to"], "n": data["notes"], "st": data["status"]})).mappings().first()
    contract_id = row["id"]
    await db.execute(text("DELETE FROM billing_price_tiers WHERE contract_id = CAST(:k AS uuid)"), {"k": contract_id})
    for t in data["tiers"]:
        await db.execute(text("""
            INSERT INTO billing_price_tiers (contract_id, month_from, month_to, amount) VALUES (CAST(:k AS uuid), :f, :t, :a)
        """), {"k": contract_id, "f": t["month_from"], "t": t["month_to"], "a": t["amount"]})
    await db.commit()
    await sync_installments(db, company_id, today_bogota(), rebuild_unpaid=True)
    return await get_contract(db, company_id)


async def _validated_by_installment(db: AsyncSession, company_id: str) -> dict[str, Decimal]:
    rows = (await db.execute(text("""
        SELECT installment_id::text AS iid, COALESCE(SUM(amount), 0) AS total FROM billing_payments
        WHERE company_id = CAST(:c AS uuid) AND status = 'validado' GROUP BY installment_id
    """), {"c": company_id})).mappings().all()
    return {r["iid"]: Decimal(str(r["total"])) for r in rows}


async def sync_installments(db: AsyncSession, company_id: str, today: date, rebuild_unpaid: bool = False) -> None:
    """Crea las cuotas que faltan (hasta el mes actual + AHEAD) y, si el
    contrato cambio, recalcula las que no tienen pagos validados."""
    contract = await get_contract(db, company_id)
    if not contract:
        return
    existing = {r["seq"]: dict(r) for r in (await db.execute(text("""
        SELECT id::text AS id, seq FROM billing_installments WHERE contract_id = CAST(:k AS uuid)
    """), {"k": contract["id"]})).mappings().all()}
    paid = await _validated_by_installment(db, company_id)
    upto = add_months(today.replace(day=1), AHEAD) if contract["status"] == "vigente" else today.replace(day=1)
    if contract["status"] == "terminado":
        upto = (contract["updated_at"].astimezone(TZ).date() if contract.get("updated_at") else today).replace(day=1)
    for inst in schedule_for(contract, contract["tiers"], upto):
        current = existing.get(inst["seq"])
        params = {"c": company_id, "k": contract["id"], "s": inst["seq"], "p": inst["period"], "a": inst["amount"],
                  "f": inst["due_from"], "d": inst["due_date"]}
        if current is None:
            await db.execute(text("""
                INSERT INTO billing_installments (company_id, contract_id, seq, period, amount, due_from, due_date)
                VALUES (CAST(:c AS uuid), CAST(:k AS uuid), :s, :p, :a, :f, :d) ON CONFLICT (contract_id, seq) DO NOTHING
            """), params)
        elif rebuild_unpaid and current["id"] not in paid:
            await db.execute(text("""
                UPDATE billing_installments SET period = :p, amount = :a, due_from = :f, due_date = :d
                WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid)
            """), {**params, "i": current["id"]})
    await db.commit()


async def installments(db: AsyncSession, company_id: str, today: date) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT id::text AS id, seq, period, amount, due_from, due_date, voided, status FROM billing_installments
        WHERE company_id = CAST(:c AS uuid) ORDER BY seq
    """), {"c": company_id})).mappings().all()
    paid = await _validated_by_installment(db, company_id)
    out = []
    for r in rows:
        inst = dict(r)
        validated = paid.get(inst["id"], Decimal("0"))
        st = status_of(inst, validated, today)
        out.append({**inst, **st, "validated": validated, "stored_status": inst["status"]})
    return out


async def refresh_statuses(db: AsyncSession, company_id: Optional[str] = None, today: Optional[date] = None) -> int:
    """Guarda el estado calculado (ciclo diario). Devuelve cuantas cambiaron."""
    today = today or today_bogota()
    companies = [company_id] if company_id else [c["id"] for c in await registered_companies(db)]
    changed = 0
    for cid in companies:
        await sync_installments(db, cid, today)
        for inst in await installments(db, cid, today):
            if inst["status"] != inst["stored_status"]:
                await db.execute(text("UPDATE billing_installments SET status = :s WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid)"),
                                 {"s": inst["status"], "i": inst["id"], "c": cid})
                changed += 1
    await db.commit()
    return changed


def current_installment(items: list[dict], today: date) -> Optional[dict]:
    month = today.replace(day=1)
    return next((i for i in items if i["period"] == month), None)


def summarize(contract: Optional[dict], items: list[dict], today: date) -> dict:
    """Estado del mes, proxima fecha, meses cumplidos del minimo y alertas."""
    if not contract:
        return {"has_contract": False, "state": "sin_contrato", "alerts": []}
    month = current_installment(items, today)
    overdue = [i for i in items if i["status"] == "en_mora"]
    upcoming = next((i for i in items if i["status"] in ("pendiente", "en_ventana")), None)
    done = sum(1 for i in items if i["period"] <= today.replace(day=1) and not i.get("voided"))
    alerts = [{"kind": "mora", "text": f"Cuota de {period_label(i['period'])} en mora: {i['days_late']} día(s) de atraso", "days": i["days_late"]} for i in overdue]
    if month and month["status"] == "en_ventana" and month["days_left"] is not None and month["days_left"] <= WARN_DAYS:
        alerts.append({"kind": "vence", "text": f"La cuota de {period_label(month['period'])} vence en {month['days_left']} día(s)" if month["days_left"] else
                       f"La cuota de {period_label(month['period'])} vence hoy", "days": month["days_left"]})
    if overdue:
        state = "en_mora"
    elif month and month["status"] == "en_ventana":
        state = "en_ventana"
    else:
        state = "al_dia"
    return {"has_contract": True, "state": state, "month": month, "next": upcoming, "overdue": overdue, "alerts": alerts,
            "months_done": done, "min_months": contract["min_months"],
            "days_late": max((i["days_late"] for i in overdue), default=0)}


# ----------------------------------------------------------------- pagos ---
async def register_payment(db: AsyncSession, company_id: str, raw: dict, actor: str) -> dict:
    data = validate_payment(raw)
    inst = (await db.execute(text("""
        SELECT id::text AS id, voided FROM billing_installments WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid)
    """), {"i": data["installment_id"], "c": company_id})).mappings().first()
    if not inst:
        raise BillingInvalid("installment_id", "la cuota no es de esta empresa")
    if inst["voided"]:
        raise BillingConflict("La cuota está anulada.")
    row = (await db.execute(text("""
        INSERT INTO billing_payments (company_id, installment_id, amount, paid_on, method, reference, note, created_by)
        VALUES (CAST(:c AS uuid), CAST(:i AS uuid), :a, :p, :m, :r, :n, :by) RETURNING id::text AS id
    """), {"c": company_id, "i": data["installment_id"], "a": data["amount"], "p": data["paid_on"], "m": data["method"],
           "r": data["reference"], "n": data["note"], "by": actor[:200]})).mappings().first()
    await db.commit()
    return {"id": row["id"], **data}


async def validate_payment_and_issue(db: AsyncSession, company_id: str, payment_id: str, actor: str) -> dict:
    """por_validar -> validado y comprobante con el siguiente numero de la
    secuencia. Atomico: dos validaciones del mismo pago no generan dos."""
    row = (await db.execute(text("""
        UPDATE billing_payments SET status = 'validado', validated_by = :by, validated_at = now()
        WHERE id = CAST(:p AS uuid) AND company_id = CAST(:c AS uuid) AND status = 'por_validar'
        RETURNING id::text AS id
    """), {"p": payment_id, "c": company_id, "by": actor[:200]})).mappings().first()
    if not row:
        await db.rollback()
        raise BillingConflict("El pago no existe en esta empresa o ya no está por validar.")
    receipt = (await db.execute(text("""
        INSERT INTO billing_receipts (company_id, payment_id) VALUES (CAST(:c AS uuid), CAST(:p AS uuid))
        RETURNING id::text AS id, number
    """), {"c": company_id, "p": payment_id})).mappings().first()
    await db.commit()
    await refresh_statuses(db, company_id)
    return {"payment_id": payment_id, "receipt_id": receipt["id"], "number": int(receipt["number"]), "code": receipt_code(receipt["number"])}


async def void_payment(db: AsyncSession, company_id: str, payment_id: str, reason: str, actor: str) -> dict:
    reason = str(reason or "").strip()
    if len(reason) < 5:
        raise BillingInvalid("reason", "escribe el motivo (mínimo 5 caracteres)")
    row = (await db.execute(text("""
        UPDATE billing_payments SET status = 'anulado', void_reason = :r, voided_by = :by, voided_at = now()
        WHERE id = CAST(:p AS uuid) AND company_id = CAST(:c AS uuid) AND status = 'validado'
        RETURNING id::text AS id
    """), {"p": payment_id, "c": company_id, "r": reason[:500], "by": actor[:200]})).mappings().first()
    if not row:
        await db.rollback()
        raise BillingConflict("Solo se anula un pago validado de esta empresa.")
    rec = (await db.execute(text("""
        UPDATE billing_receipts SET status = 'anulado', voided_at = now(), void_reason = :r
        WHERE payment_id = CAST(:p AS uuid) AND company_id = CAST(:c AS uuid) RETURNING number
    """), {"p": payment_id, "c": company_id, "r": reason[:500]})).mappings().first()
    await db.commit()
    await refresh_statuses(db, company_id)
    return {"payment_id": payment_id, "code": receipt_code(rec["number"]) if rec else None}


async def payments(db: AsyncSession, company_id: str, limit: int = 200) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT p.id::text AS id, p.installment_id::text AS installment_id, p.amount, p.paid_on, p.method, p.reference, p.note, p.status,
               p.created_by, p.created_at, p.validated_by, p.validated_at, p.void_reason, p.voided_at,
               r.id::text AS receipt_id, r.number AS receipt_number, r.status AS receipt_status, i.period
        FROM billing_payments p
        JOIN billing_installments i ON i.id = p.installment_id AND i.company_id = p.company_id
        LEFT JOIN billing_receipts r ON r.payment_id = p.id AND r.company_id = p.company_id
        WHERE p.company_id = CAST(:c AS uuid) ORDER BY p.created_at DESC LIMIT :n
    """), {"c": company_id, "n": limit})).mappings().all()
    return [dict(r) for r in rows]


async def receipt(db: AsyncSession, company_id: str, receipt_id: str) -> Optional[dict]:
    try:
        rid = str(uuid.UUID(str(receipt_id)))
    except ValueError:
        return None
    row = (await db.execute(text("""
        SELECT r.id::text AS id, r.number, r.status, r.storage_key, r.created_at, r.voided_at, r.void_reason,
               p.amount, p.paid_on, p.method, p.reference, p.validated_at, p.validated_by, i.period, i.seq,
               c.id::text AS company_id, c.name AS company_name, c.slug AS company_slug, k.currency
        FROM billing_receipts r
        JOIN billing_payments p ON p.id = r.payment_id AND p.company_id = r.company_id
        JOIN billing_installments i ON i.id = p.installment_id AND i.company_id = r.company_id
        JOIN billing_contracts k ON k.id = i.contract_id AND k.company_id = r.company_id
        JOIN companies c ON c.id = r.company_id
        WHERE r.id = CAST(:r AS uuid) AND r.company_id = CAST(:c AS uuid)
    """), {"r": rid, "c": company_id})).mappings().first()
    return dict(row) if row else None


async def set_receipt_key(db: AsyncSession, company_id: str, receipt_id: str, key: str) -> None:
    await db.execute(text("UPDATE billing_receipts SET storage_key = :k WHERE id = CAST(:r AS uuid) AND company_id = CAST(:c AS uuid)"),
                     {"k": key, "r": receipt_id, "c": company_id})
    await db.commit()


# ---------------------------------------------------------- contratos PDF ---
MAX_PDF_BYTES = 10 * 1024 * 1024


def is_pdf(raw: bytes) -> bool:
    """PDF real por su firma (%PDF-) y su cierre (%%EOF), no por la extension."""
    return bool(raw) and raw[:5] == b"%PDF-" and b"%%EOF" in raw[-2048:]


def contract_file_key(company_id: str, file_id: str) -> str:
    return f"billing/{uuid.UUID(company_id)}/contracts/{uuid.UUID(file_id)}.pdf"


def receipt_key(company_id: str, number: int) -> str:
    return f"billing/{uuid.UUID(company_id)}/receipts/{receipt_code(number)}.pdf"


async def add_contract_file(db: AsyncSession, company_id: str, raw: bytes, name: str, actor: str, put) -> dict:
    if len(raw) > MAX_PDF_BYTES:
        raise BillingInvalid("archivo", "el contrato pesa más de 10 MB")
    if not is_pdf(raw):
        raise BillingInvalid("archivo", "solo se acepta un PDF real")
    file_id = str(uuid.uuid4())
    version = int((await db.execute(text("SELECT COALESCE(MAX(version), 0) + 1 FROM billing_contract_files WHERE company_id = CAST(:c AS uuid)"),
                                   {"c": company_id})).scalar() or 1)
    await put(contract_file_key(company_id, file_id), raw)
    await db.execute(text("UPDATE billing_contract_files SET is_current = false WHERE company_id = CAST(:c AS uuid)"), {"c": company_id})
    await db.execute(text("""
        INSERT INTO billing_contract_files (id, company_id, version, size_bytes, original_name, created_by)
        VALUES (CAST(:i AS uuid), CAST(:c AS uuid), :v, :s, :n, :by)
    """), {"i": file_id, "c": company_id, "v": version, "s": len(raw), "n": re.sub(r"[^\w .()-]", "_", name or "contrato.pdf")[:200], "by": actor[:200]})
    await db.commit()
    return {"id": file_id, "version": version, "size_bytes": len(raw)}


async def contract_files(db: AsyncSession, company_id: str) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT id::text AS id, version, size_bytes, original_name, is_current, created_by, created_at FROM billing_contract_files
        WHERE company_id = CAST(:c AS uuid) ORDER BY version DESC
    """), {"c": company_id})).mappings().all()
    return [dict(r) for r in rows]


async def contract_file(db: AsyncSession, company_id: str, file_id: str) -> Optional[dict]:
    try:
        fid = str(uuid.UUID(str(file_id)))
    except ValueError:
        return None
    row = (await db.execute(text("""
        SELECT id::text AS id, version, original_name FROM billing_contract_files WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid)
    """), {"i": fid, "c": company_id})).mappings().first()
    return dict(row) if row else None


# ------------------------------------------------------------- tableros ---
async def company_view(db: AsyncSession, company_id: str, today: Optional[date] = None) -> dict:
    today = today or today_bogota()
    await sync_installments(db, company_id, today)
    contract = await get_contract(db, company_id)
    items = await installments(db, company_id, today) if contract else []
    return {"contract": contract, "installments": items, "summary": summarize(contract, items, today),
            "payments": await payments(db, company_id), "files": await contract_files(db, company_id)}


async def board(db: AsyncSession, today: Optional[date] = None) -> dict:
    """Tarjetas por empresa, indicadores y datos de las graficas."""
    today = today or today_bogota()
    month = today.replace(day=1)
    cards, kpis = [], {"collected_month": Decimal("0"), "due_month": Decimal("0"), "overdue": Decimal("0"), "expected_monthly": Decimal("0")}
    months = [add_months(month, -i) for i in range(11, -1, -1)]
    series = {m: {"expected": Decimal("0"), "collected": Decimal("0")} for m in months}
    by_company, by_type = [], {}
    # Recaudado = pagos validados, por el mes (Bogota) en que se validaron.
    collected_rows = (await db.execute(text("""
        SELECT p.company_id::text AS cid, p.validated_at, p.amount FROM billing_payments p
        WHERE p.status = 'validado' AND p.validated_at >= :since
    """), {"since": datetime.combine(months[0], datetime.min.time(), tzinfo=TZ) - timedelta(days=1)})).mappings().all()
    collected: dict = {}
    for r in collected_rows:
        m = r["validated_at"].astimezone(TZ).date().replace(day=1)
        collected[(r["cid"], m)] = collected.get((r["cid"], m), Decimal("0")) + Decimal(str(r["amount"]))
    types = {t["code"]: t["label"] for t in await contract_types(db, active_only=False)}
    for company in await registered_companies(db):
        cid = company["id"]
        await sync_installments(db, cid, today)
        contract = await get_contract(db, cid)
        items = await installments(db, cid, today) if contract else []
        s = summarize(contract, items, today)
        cur = s.get("month")
        if contract:
            if contract["status"] == "vigente":
                kpis["expected_monthly"] += tier_amount(contract["tiers"], cur["seq"]) if cur else Decimal("0")
            label = types.get(contract["contract_type"], contract["contract_type"])
            by_type[label] = by_type.get(label, 0) + 1
            for i in items:
                if i["period"] in series and not i.get("voided"):
                    series[i["period"]]["expected"] += Decimal(str(i["amount"]))
                if i["status"] == "en_mora":
                    kpis["overdue"] += Decimal(str(i["amount"])) - i["validated"]
            if cur and cur["status"] in ("pendiente", "en_ventana"):
                kpis["due_month"] += Decimal(str(cur["amount"])) - cur["validated"]
        total_company = Decimal("0")
        for m in months:
            v = collected.get((cid, m), Decimal("0"))
            series[m]["collected"] += v
            total_company += v
        kpis["collected_month"] += collected.get((cid, month), Decimal("0"))
        by_company.append({"name": company["name"], "collected": total_company})
        cards.append({"company": company, "contract": contract and {k: contract[k] for k in ("contract_type", "status", "currency", "min_months", "pay_day_from", "pay_day_to", "start_date")},
                      "type_label": types.get(contract["contract_type"], contract["contract_type"]) if contract else "",
                      "summary": s, "has_file": False})
    files = (await db.execute(text("SELECT DISTINCT company_id::text AS cid FROM billing_contract_files"))).mappings().all()
    with_file = {r["cid"] for r in files}
    for card in cards:
        card["has_file"] = card["company"]["id"] in with_file
    return {"today": today, "kpis": kpis, "cards": cards,
            "charts": {"by_month": [{"month": m, "label": period_label(m), **series[m]} for m in months],
                       "by_company": sorted(by_company, key=lambda x: -x["collected"]),
                       "by_type": [{"label": k, "count": v} for k, v in sorted(by_type.items(), key=lambda kv: -kv[1])]}}


async def alerts(db: AsyncSession, today: Optional[date] = None) -> list[dict]:
    """Alertas de mora y de "vence en N dias" para el Centro de mando."""
    today = today or today_bogota()
    out = []
    for company in await registered_companies(db):
        contract = await get_contract(db, company["id"])
        if not contract:
            continue
        s = summarize(contract, await installments(db, company["id"], today), today)
        for a in s["alerts"]:
            out.append({"company_id": company["id"], "company_name": company["name"], **a})
    return out
