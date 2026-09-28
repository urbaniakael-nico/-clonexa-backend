"""Gastos fijos (049M): lo que se paga y no es mercancia.

Servicios publicos (agua, luz, gas, internet), arriendo y otros gastos (aseo,
mantenimiento, fumigacion y conceptos propios de cada empresa). Cada registro
es de un MES; la tabla mes a mes suma por concepto y en total, y el estado de
resultados de Reportes descuenta la parte de cada mes que cae en el periodo.
"""
from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

MONEY = Decimal("0.01")
GROUPS = {"servicios": "Servicios públicos", "arriendo": "Arriendo", "otros": "Otros gastos"}
PRESET_CONCEPTS = [
    ("agua", "Agua", "servicios"),
    ("luz", "Luz", "servicios"),
    ("gas", "Gas", "servicios"),
    ("internet", "Internet", "servicios"),
    ("arriendo", "Arriendo", "arriendo"),
    ("aseo", "Aseo", "otros"),
    ("mantenimiento", "Mantenimiento", "otros"),
    ("fumigacion", "Fumigación", "otros"),
]


def dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else 0))
    except Exception:
        return Decimal("0")


def money(value: Any) -> Decimal:
    return dec(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def concept_key(label: Any) -> str:
    text = unicodedata.normalize("NFKD", str(label or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")[:60]


def parse_month(value: Any) -> date:
    """"2026-09" o "2026-09-15" -> date(2026, 9, 1)."""
    text = str(value or "").strip()
    match = re.match(r"^(\d{4})-(\d{1,2})", text)
    if not match:
        raise ValueError("mes_invalido")
    year, month = int(match.group(1)), int(match.group(2))
    if not (2000 <= year <= 2100 and 1 <= month <= 12):
        raise ValueError("mes_invalido")
    return date(year, month, 1)


def month_label(month: date) -> str:
    return month.strftime("%Y-%m")


def shift_month(month: date, delta: int) -> date:
    index = month.year * 12 + month.month - 1 + delta
    return date(index // 12, index % 12 + 1, 1)


def months_back(until: date, count: int) -> list[date]:
    return [shift_month(until, -offset) for offset in range(count - 1, -1, -1)]


def monthly_table(records: Iterable[dict], months: list[date], concepts: dict[str, dict]) -> dict:
    """Filas por concepto con el valor de cada mes, total por concepto, total
    por mes y el cambio del ultimo mes contra el anterior (¿cuanto subio la
    luz?)."""
    keys = [month_label(m) for m in months]
    rows: dict[str, dict] = {}
    for record in records:
        month = month_label(record["month"])
        if month not in keys:
            continue
        key = record["concept_key"]
        concept = concepts.get(key) or {"label": record.get("concept_label") or key, "group": record.get("group_key") or "otros"}
        row = rows.setdefault(key, {"concept_key": key, "label": concept["label"], "group": concept["group"],
                                    "by_month": {k: Decimal("0") for k in keys}})
        row["by_month"][month] += dec(record["amount"])
    order = {key: index for index, key in enumerate(concepts)}
    out_rows = []
    for row in sorted(rows.values(), key=lambda r: (list(GROUPS).index(r["group"]) if r["group"] in GROUPS else 9,
                                                    order.get(r["concept_key"], 999), r["label"])):
        values = [row["by_month"][k] for k in keys]
        last, previous = (values[-1], values[-2]) if len(values) >= 2 else (values[-1] if values else Decimal("0"), Decimal("0"))
        out_rows.append({
            "concept_key": row["concept_key"], "label": row["label"], "group": row["group"],
            "by_month": {k: float(money(v)) for k, v in zip(keys, values)},
            "total": float(money(sum(values, Decimal("0")))),
            "change_pct": float(((last - previous) / previous * 100).quantize(Decimal("0.1"))) if previous > 0 else None,
        })
    by_month = {k: float(money(sum((dec(r["by_month"][k]) for r in out_rows), Decimal("0")))) for k in keys}
    return {"months": keys, "rows": out_rows, "totals_by_month": by_month,
            "total": float(money(sum((dec(v) for v in by_month.values()), Decimal("0"))))}


def prorated(records: Iterable[dict], start: date, end: date) -> dict:
    """Parte de los gastos fijos que corresponde a [start, end]: cada gasto
    mensual se reparte por dias (una semana de septiembre lleva 7/30 del
    arriendo de septiembre)."""
    by_concept: dict[str, dict] = {}
    total = Decimal("0")
    for record in records:
        month = record["month"]
        days = calendar.monthrange(month.year, month.month)[1]
        month_end = date(month.year, month.month, days)
        lo, hi = max(month, start), min(month_end, end)
        if hi < lo:
            continue
        share = dec(record["amount"]) * Decimal((hi - lo).days + 1) / Decimal(days)
        total += share
        row = by_concept.setdefault(record["concept_key"], {"concept_key": record["concept_key"],
                                                            "label": record.get("concept_label") or record["concept_key"],
                                                            "group": record.get("group_key") or "otros", "amount": Decimal("0")})
        row["amount"] += share
    rows = [{**r, "amount": float(money(r["amount"]))} for r in sorted(by_concept.values(), key=lambda r: -r["amount"])]
    return {"total": money(total), "by_concept": rows}
