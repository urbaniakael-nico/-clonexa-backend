"""Nomina con normativa laboral colombiana (049A): motor de calculo puro.

No toca la base: recibe los parametros de ley por año (tabla
payroll_co_params, editable desde Admin V2), los intervalos trabajados de
cada empleado (turnos de mesero, cocina y caja, ya sin pausas) y devuelve el
desglose: horas por tipo, a que valor, recargos, extras, auxilio, aportes del
empleado y del empleador y provisiones.

Ningun valor legal esta fijo aqui: el salario minimo, el auxilio, la jornada
semanal, los porcentajes y sus fechas de cambio salen de `params_by_year`.
Lo unico calculado en codigo es el calendario de festivos (Ley 51 de 1983 y
Pascua), que es una regla y no un valor.

Formato de una fila de parametros por año:
    {"params": {...valores vigentes desde el 1 de enero...},
     "changes": [{"from": "2026-07-15", "weekly_hours": 42}, ...]}
El valor vigente para una fecha = params del año de esa fecha + los cambios
con from <= fecha.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

MONEY = Decimal("0.01")

# Claves de parametros que el motor necesita y su descripcion (Admin V2 arma
# el formulario con esto). Los valores viven en la base, no aqui.
PARAM_FIELDS: list[tuple[str, str, str]] = [
    ("smmlv", "Salario minimo mensual (SMMLV)", "money"),
    ("transport_allowance", "Auxilio de transporte mensual", "money"),
    ("transport_cap_smmlv", "Tope del auxilio (en SMMLV)", "number"),
    ("weekly_hours", "Jornada maxima semanal (horas)", "number"),
    ("monthly_hours_per_weekly_hour", "Horas al mes por hora semanal (divisor del valor hora)", "number"),
    ("daily_ordinary_hours", "Horas ordinarias por jornada diaria", "number"),
    ("night_start", "Inicio de la franja nocturna (HH:MM)", "time"),
    ("night_end", "Fin de la franja nocturna (HH:MM)", "time"),
    ("night_pct", "Recargo nocturno %", "number"),
    ("extra_day_pct", "Hora extra diurna %", "number"),
    ("extra_night_pct", "Hora extra nocturna %", "number"),
    ("sunday_holiday_pct", "Recargo dominical y festivo %", "number"),
    ("max_extra_daily_hours", "Maximo de horas extra al dia", "number"),
    ("max_extra_weekly_hours", "Maximo de horas extra a la semana", "number"),
    ("health_employee_pct", "Salud empleado %", "number"),
    ("pension_employee_pct", "Pension empleado %", "number"),
    ("fsp_min_smmlv", "Fondo de Solidaridad Pensional desde (SMMLV)", "number"),
    ("fsp_brackets", "Tabla FSP [[desde SMMLV, %], ...]", "json"),
    ("pension_employer_pct", "Pension empleador %", "number"),
    ("health_employer_pct", "Salud empleador %", "number"),
    ("exoneration_max_smmlv", "Exoneracion de salud/SENA/ICBF para salarios menores a (SMMLV)", "number"),
    ("arl_pct_by_level", "ARL % por nivel de riesgo {\"1\": ..., \"5\": ...}", "json"),
    ("ccf_pct", "Caja de compensacion %", "number"),
    ("icbf_pct", "ICBF %", "number"),
    ("sena_pct", "SENA %", "number"),
    ("severance_pct", "Cesantias %", "number"),
    ("severance_interest_pct", "Intereses de cesantias %", "number"),
    ("service_bonus_pct", "Prima de servicios %", "number"),
    ("vacation_pct", "Vacaciones %", "number"),
    ("extra_holidays", "Festivos adicionales [\"AAAA-MM-DD\", ...]", "json"),
]
PARAM_KEYS = {key for key, _label, _kind in PARAM_FIELDS}
REQUIRED_KEYS = PARAM_KEYS - {"extra_holidays"}

# Tipos de hora. (clave, etiqueta, es_extra, es_nocturna, es_dominical)
HOUR_TYPES: list[tuple[str, str, bool, bool, bool]] = [
    ("ord_day", "Ordinaria diurna", False, False, False),
    ("ord_night", "Ordinaria nocturna", False, True, False),
    ("ord_sun_day", "Dominical/festiva diurna", False, False, True),
    ("ord_sun_night", "Dominical/festiva nocturna", False, True, True),
    ("ext_day", "Extra diurna", True, False, False),
    ("ext_night", "Extra nocturna", True, True, False),
    ("ext_sun_day", "Extra diurna dominical/festiva", True, False, True),
    ("ext_sun_night", "Extra nocturna dominical/festiva", True, True, True),
]
HOUR_TYPE_LABELS = {key: label for key, label, *_ in HOUR_TYPES}


class ParamsMissing(ValueError):
    """No hay parametros de ley cargados para el año pedido."""


def _dec(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))


def money(value: Any) -> Decimal:
    return _dec(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def _pct(value: Any) -> Decimal:
    return _dec(value) / Decimal(100)


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _as_time(value: Any) -> time:
    if isinstance(value, time):
        return value
    hours, minutes = str(value or "00:00").split(":")[:2]
    return time(int(hours) % 24, int(minutes))


# ------------------------------------------------------------ festivos ---
def _easter(year: int) -> date:
    """Domingo de Pascua (algoritmo anonimo gregoriano)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _next_monday(value: date) -> date:
    return value + timedelta(days=(7 - value.weekday()) % 7)


def colombian_holidays(year: int) -> set[date]:
    """Festivos nacionales de Colombia (Ley 51 de 1983, "Ley Emiliani")."""
    fixed = {date(year, 1, 1), date(year, 5, 1), date(year, 7, 20), date(year, 8, 7), date(year, 12, 8), date(year, 12, 25)}
    moved = {_next_monday(date(year, month, day)) for month, day in
             [(1, 6), (3, 19), (6, 29), (8, 15), (10, 12), (11, 1), (11, 11)]}
    easter = _easter(year)
    holy = {easter - timedelta(days=3), easter - timedelta(days=2)}
    # Ascension (+39), Corpus Christi (+60), Sagrado Corazon (+68): al lunes siguiente.
    easter_moved = {_next_monday(easter + timedelta(days=offset)) for offset in (39, 60, 68)}
    return fixed | moved | holy | easter_moved


# ---------------------------------------------------------- parametros ---
def validate_year_row(row: dict) -> list[str]:
    """Errores de una fila de parametros (vacio si esta bien)."""
    errors: list[str] = []
    params = row.get("params") if isinstance(row.get("params"), dict) else None
    if params is None:
        return ["params debe ser un objeto"]
    for key in sorted(REQUIRED_KEYS - set(params)):
        errors.append(f"falta {key}")
    for key in sorted(set(params) - PARAM_KEYS):
        errors.append(f"clave desconocida {key}")
    changes = row.get("changes") or []
    if not isinstance(changes, list):
        return errors + ["changes debe ser una lista"]
    for change in changes:
        if not isinstance(change, dict) or "from" not in change:
            errors.append("cada cambio necesita from")
            continue
        try:
            _as_date(change["from"])
        except Exception:
            errors.append(f"fecha invalida {change.get('from')}")
        for key in set(change) - {"from"} - PARAM_KEYS:
            errors.append(f"clave desconocida en cambio {key}")
    return errors


class ParamResolver:
    """Valor vigente de cada parametro para una fecha."""

    def __init__(self, params_by_year: dict[int, dict]):
        self._rows = {int(year): row for year, row in (params_by_year or {}).items()}
        self._cache: dict[date, dict] = {}

    def years(self) -> list[int]:
        return sorted(self._rows)

    def for_date(self, day: date) -> dict:
        if day in self._cache:
            return self._cache[day]
        row = self._rows.get(day.year)
        if not row:
            raise ParamsMissing(f"No hay parametros de ley cargados para {day.year}. Cargalos en Admin V2.")
        values = dict(row.get("params") or {})
        for change in sorted(row.get("changes") or [], key=lambda c: str(c.get("from"))):
            if _as_date(change["from"]) <= day:
                values.update({k: v for k, v in change.items() if k != "from"})
        self._cache[day] = values
        return values

    def holidays(self, year: int) -> set[date]:
        extra = set()
        row = self._rows.get(year) or {}
        for raw in (row.get("params") or {}).get("extra_holidays") or []:
            try:
                extra.add(_as_date(raw))
            except Exception:
                continue
        return colombian_holidays(year) | extra


def carry_forward(row: dict, new_year: int) -> dict:
    """Plantilla para un año nuevo: los valores con que termino el año
    anterior pasan a ser la base, y los cambios con fecha del año nuevo (o
    posteriores) se conservan. El administrador ajusta SMMLV y auxilio."""
    last = ParamResolver({new_year - 1: row}).for_date(date(new_year - 1, 12, 31))
    params = {k: v for k, v in last.items() if k != "extra_holidays"}
    changes = [c for c in (row.get("changes") or []) if _as_date(c["from"]).year >= new_year]
    return {"params": params, "changes": changes}


def hourly_value(monthly_salary: Decimal, values: dict) -> Decimal:
    """Valor de la hora ordinaria: salario / (jornada semanal x horas al mes por hora semanal)."""
    monthly_hours = _dec(values["weekly_hours"]) * _dec(values["monthly_hours_per_weekly_hour"])
    if monthly_hours <= 0:
        return Decimal("0")
    return _dec(monthly_salary) / monthly_hours


# ------------------------------------------------------- clasificacion ---
def _is_night(moment: datetime, values: dict) -> bool:
    start, end = _as_time(values["night_start"]), _as_time(values["night_end"])
    now = moment.time()
    if start <= end:
        return start <= now < end
    return now >= start or now < end


def _week_key(day: date) -> date:
    return day - timedelta(days=day.weekday())


def classify_intervals(
    intervals: Iterable[tuple[datetime, datetime]],
    resolver: ParamResolver,
    pay_from: date,
    pay_to: date,
) -> dict:
    """Clasifica minuto a minuto los intervalos trabajados (hora local, sin
    pausas) de UN empleado.

    - Jornada diaria y semana (lunes a domingo) se cuentan por la fecha de
      inicio del turno; las horas pasan a extra cuando se supera la jornada
      diaria o la semanal vigente ese dia.
    - Nocturno y dominical/festivo dependen de la fecha y hora real de cada
      minuto, y el valor de la hora es el vigente ese dia.
    - Solo se pagan los minutos entre pay_from y pay_to; los de antes (misma
      semana) cuentan para el tope semanal.
    """
    daily_ord: dict[date, int] = defaultdict(int)
    daily_ext: dict[date, int] = defaultdict(int)
    weekly_ord: dict[date, int] = defaultdict(int)
    weekly_ext: dict[date, int] = defaultdict(int)
    minutes: dict[tuple[str, date], int] = defaultdict(int)  # (tipo, fecha del minuto)
    worked_days: set[date] = set()
    holidays_cache: dict[int, set[date]] = {}

    def values_for(day: date) -> dict:
        # Dias fuera del periodo (la semana anterior, o la madrugada despues
        # del cierre) solo cuentan para los topes; si su año no tiene
        # parametros se usan los del borde del periodo.
        if day < pay_from or day > pay_to:
            try:
                return resolver.for_date(day)
            except ParamsMissing:
                return resolver.for_date(pay_from if day < pay_from else pay_to)
        return resolver.for_date(day)

    for start, end in sorted(intervals, key=lambda item: item[0]):
        start = start.replace(second=0, microsecond=0)
        end = end.replace(second=0, microsecond=0)
        if end <= start:
            continue
        journey = start.date()
        week = _week_key(journey)
        cursor = start
        while cursor < end:
            day = cursor.date()
            values = values_for(day)
            day_limit = int(_dec(values["daily_ordinary_hours"]) * 60)
            week_limit = int(_dec(values["weekly_hours"]) * 60)
            is_extra = daily_ord[journey] >= day_limit or weekly_ord[week] >= week_limit
            if is_extra:
                daily_ext[journey] += 1
                weekly_ext[week] += 1
            else:
                daily_ord[journey] += 1
                weekly_ord[week] += 1
            if pay_from <= day <= pay_to:
                if day.year not in holidays_cache:
                    holidays_cache[day.year] = resolver.holidays(day.year)
                sunday = day.weekday() == 6 or day in holidays_cache[day.year]
                night = _is_night(cursor, values)
                kind = ("ext_" if is_extra else "ord_") + ("sun_" if sunday else "") + ("night" if night else "day")
                minutes[(kind, day)] += 1
                worked_days.add(day)
            cursor += timedelta(minutes=1)

    alerts: list[dict] = []
    for journey, extra in sorted(daily_ext.items()):
        if not (pay_from <= journey <= pay_to):
            continue
        max_daily = int(_dec(resolver.for_date(journey)["max_extra_daily_hours"]) * 60)
        if extra > max_daily:
            alerts.append({
                "kind": "extra_daily",
                "date": journey.isoformat(),
                "extra_minutes": extra,
                "limit_minutes": max_daily,
                "message": f"{journey.isoformat()}: {extra / 60:g} h extra en el dia (maximo legal {max_daily / 60:g} h).",
            })
    for week, extra in sorted(weekly_ext.items()):
        week_end = week + timedelta(days=6)
        if week_end < pay_from or week > pay_to:
            continue
        max_weekly = int(_dec(resolver.for_date(max(week, pay_from))["max_extra_weekly_hours"]) * 60)
        if extra > max_weekly:
            alerts.append({
                "kind": "extra_weekly",
                "date": week.isoformat(),
                "extra_minutes": extra,
                "limit_minutes": max_weekly,
                "message": f"Semana del {week.isoformat()}: {extra / 60:g} h extra (maximo legal {max_weekly / 60:g} h).",
            })
    return {"minutes": dict(minutes), "worked_days": sorted(worked_days), "alerts": alerts}


def _multiplier(kind: str, values: dict) -> Decimal:
    extra = kind.startswith("ext_")
    night = kind.endswith("night")
    sunday = "_sun_" in kind
    factor = Decimal(1)
    if extra:
        factor += _pct(values["extra_night_pct"] if night else values["extra_day_pct"])
    elif night:
        factor += _pct(values["night_pct"])
    if sunday:
        factor += _pct(values["sunday_holiday_pct"])
    return factor


def _pct_label(kind: str, values: dict) -> str:
    parts = []
    extra, night, sunday = kind.startswith("ext_"), kind.endswith("night"), "_sun_" in kind
    if extra:
        parts.append(f"extra {'nocturna' if night else 'diurna'} {_dec(values['extra_night_pct' if night else 'extra_day_pct']):g}%")
    elif night:
        parts.append(f"nocturno {_dec(values['night_pct']):g}%")
    if sunday:
        parts.append(f"dominical/festivo {_dec(values['sunday_holiday_pct']):g}%")
    return " + ".join(parts) or "sin recargo"


# ------------------------------------------------------------- empleado ---
def liquidate_employee(
    *,
    intervals: Iterable[tuple[datetime, datetime]],
    monthly_salary: Any,
    resolver: ParamResolver,
    pay_from: date,
    pay_to: date,
    arl_level: int = 1,
    exonerated: bool = False,
    other_deductions: Any = 0,
) -> dict:
    """Liquidacion de un empleado para el periodo [pay_from, pay_to].

    Sin salario configurado no se asume ninguno: las horas se clasifican
    igual, pero todo valor queda en 0 y la fila sale marcada salary_missing.
    """
    salary = max(_dec(monthly_salary), Decimal("0"))
    salary_missing = salary <= 0
    ref = resolver.for_date(pay_to)
    smmlv = _dec(ref["smmlv"])
    classified = classify_intervals(intervals, resolver, pay_from, pay_to)

    # Lineas del desglose: una por (tipo de hora, valor de la hora, %).
    grouped: dict[tuple, dict] = {}
    for (kind, day), count in classified["minutes"].items():
        values = resolver.for_date(day)
        base_hour = hourly_value(salary, values)
        factor = _multiplier(kind, values)
        key = (kind, money(base_hour), factor)
        line = grouped.setdefault(key, {
            "type": kind,
            "label": HOUR_TYPE_LABELS[kind],
            "surcharge": _pct_label(kind, values),
            "factor": factor,
            "base_hour_value": money(base_hour),
            "hour_value": money(base_hour * factor),
            "minutes": 0,
            "exact_amount": Decimal("0"),
            "from": day,
            "to": day,
        })
        line["minutes"] += count
        line["exact_amount"] += base_hour * factor * Decimal(count) / Decimal(60)
        line["from"] = min(line["from"], day)
        line["to"] = max(line["to"], day)

    order = {key: index for index, (key, *_rest) in enumerate(HOUR_TYPES)}
    lines = sorted(grouped.values(), key=lambda item: (order[item["type"]], item["from"]))
    hours_by_type = {key: 0 for key, *_ in HOUR_TYPES}
    earned = Decimal("0")
    extras_amount = Decimal("0")
    for line in lines:
        line["amount"] = money(line.pop("exact_amount"))
        line["hours"] = float(Decimal(line["minutes"]) / Decimal(60))
        line["factor"] = float(line["factor"])
        line["from"] = line["from"].isoformat()
        line["to"] = line["to"].isoformat()
        hours_by_type[line["type"]] += line["minutes"]
        earned += line["amount"]
        if line["type"].startswith("ext_"):
            extras_amount += line["amount"]

    # Auxilio de transporte: por dia trabajado, si el salario no pasa el tope.
    transport = Decimal("0")
    transport_applies = not salary_missing and salary <= _dec(ref["transport_cap_smmlv"]) * smmlv
    if transport_applies:
        for day in classified["worked_days"]:
            transport += _dec(resolver.for_date(day)["transport_allowance"]) / Decimal(30)
    transport = money(transport)

    # Bases: el auxilio NO entra en aportes ni vacaciones; SI en prima y cesantias.
    contribution_base = money(earned)
    benefits_base = money(earned + transport)
    vacation_base = money(earned - extras_amount)

    salary_in_smmlv = salary / smmlv if smmlv else Decimal("0")
    fsp_pct = Decimal("0")
    if salary_in_smmlv >= _dec(ref["fsp_min_smmlv"]):
        for threshold, pct in sorted(ref.get("fsp_brackets") or [], key=lambda b: _dec(b[0])):
            if salary_in_smmlv >= _dec(threshold):
                fsp_pct = _dec(pct)
    exoneration = bool(exonerated) and salary_in_smmlv < _dec(ref["exoneration_max_smmlv"])
    arl_table = ref.get("arl_pct_by_level") or {}
    arl_pct = _dec(arl_table.get(str(int(arl_level or 1)), arl_table.get("1", 0)))

    def part(label: str, pct: Any, base: Decimal, note: str = "") -> dict:
        return {"label": label, "pct": float(_dec(pct)), "base": base, "amount": money(base * _pct(pct)), "note": note}

    employee_parts = [
        part("Salud empleado", ref["health_employee_pct"], contribution_base),
        part("Pension empleado", ref["pension_employee_pct"], contribution_base),
    ]
    if fsp_pct:
        employee_parts.append(part("Fondo de Solidaridad Pensional", fsp_pct, contribution_base))
    employer_parts = [
        part("Pension empleador", ref["pension_employer_pct"], contribution_base),
        part("Salud empleador", 0 if exoneration else ref["health_employer_pct"], contribution_base,
             "Exonerado (art. 114-1 E.T.)" if exoneration else ""),
        part(f"ARL nivel {int(arl_level or 1)}", arl_pct, contribution_base),
        part("Caja de compensacion", ref["ccf_pct"], contribution_base),
        part("ICBF", 0 if exoneration else ref["icbf_pct"], contribution_base, "Exonerado" if exoneration else ""),
        part("SENA", 0 if exoneration else ref["sena_pct"], contribution_base, "Exonerado" if exoneration else ""),
    ]
    provisions = [
        part("Cesantias", ref["severance_pct"], benefits_base, "Base incluye auxilio de transporte"),
        part("Intereses de cesantias", ref["severance_interest_pct"], benefits_base, "Base incluye auxilio de transporte"),
        part("Prima de servicios", ref["service_bonus_pct"], benefits_base, "Base incluye auxilio de transporte"),
        part("Vacaciones", ref["vacation_pct"], vacation_base, "Base sin auxilio ni horas extra"),
    ]

    employee_total = sum((p["amount"] for p in employee_parts), Decimal("0"))
    other = Decimal("0") if salary_missing else money(other_deductions)
    gross = money(earned + transport)
    net = money(gross - employee_total - other)
    return {
        "monthly_salary": money(salary),
        "salary_missing": salary_missing,
        "lines": lines,
        "minutes_by_type": hours_by_type,
        "regular_minutes": sum(v for k, v in hours_by_type.items() if k.startswith("ord_")),
        "extra_minutes": sum(v for k, v in hours_by_type.items() if k.startswith("ext_")),
        "worked_days": len(classified["worked_days"]),
        "alerts": classified["alerts"],
        "earned_amount": money(earned),
        "extras_amount": money(extras_amount),
        "transport_allowance": transport,
        "transport_applies": transport_applies,
        "contribution_base": contribution_base,
        "benefits_base": benefits_base,
        "vacation_base": vacation_base,
        "employee_deductions": employee_parts,
        "employee_deductions_total": money(employee_total),
        "other_deductions": other,
        "employer_contributions": employer_parts,
        "employer_contributions_total": money(sum((p["amount"] for p in employer_parts), Decimal("0"))),
        "provisions": provisions,
        "provisions_total": money(sum((p["amount"] for p in provisions), Decimal("0"))),
        "gross_amount": gross,
        "discount_amount": money(employee_total + other),
        "net_amount": net,
    }


def subtract_breaks(
    start: datetime, end: datetime, breaks: list[tuple[datetime, datetime]], missing_break_seconds: int = 0,
) -> list[tuple[datetime, datetime]]:
    """Intervalo trabajado menos sus pausas. Si hay segundos de pausa sin
    hora registrada, se ubican a mitad del turno."""
    pieces = [(start, end)]
    cuts = sorted((max(b0, start), min(b1, end)) for b0, b1 in breaks if b1 > b0)
    if missing_break_seconds > 0 and end > start:
        middle = start + (end - start) / 2
        half = timedelta(seconds=missing_break_seconds / 2)
        cuts.append((max(start, middle - half), min(end, middle + half)))
    for cut_start, cut_end in cuts:
        if cut_end <= cut_start:
            continue
        next_pieces = []
        for p0, p1 in pieces:
            if cut_end <= p0 or cut_start >= p1:
                next_pieces.append((p0, p1))
                continue
            if cut_start > p0:
                next_pieces.append((p0, cut_start))
            if cut_end < p1:
                next_pieces.append((cut_end, p1))
        pieces = next_pieces
    return [p for p in pieces if p[1] > p[0]]
