"""Turnos (modulo shifts): reglas, armado de la malla y candidatos. Funciones puras.

Reglas duras (nunca se rompen): cobertura minima por rol y turno, horas minimas
entre turnos (contando la semana anterior), dias libres por semana, maximo de
dias seguidos, tope de horas por semana y maximo de noches seguidas.
Reglas blandas (desempatan): repartir parejo noches y fines de semana, rotar
respecto a la semana anterior y no cambiar de turno todos los dias.
Si no alcanza la gente, NO se rompe ninguna regla: el hueco queda marcado.
Todo es determinista: mismos datos, misma malla.
Un turno que cruza la medianoche cuenta para el dia en que empieza.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

WEEKDAYS_ES = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


@dataclass(frozen=True)
class Template:
    id: str
    code: str
    name: str
    start: time
    end: time
    color: str = "#3b82f6"
    active: bool = True

    @property
    def night(self) -> bool:
        return self.end <= self.start

    @property
    def minutes(self) -> int:
        a = self.start.hour * 60 + self.start.minute
        b = self.end.hour * 60 + self.end.minute
        return (b - a) % (24 * 60) or 24 * 60


@dataclass(frozen=True)
class Employee:
    id: str
    name: str
    role: str
    telegram: bool = False


@dataclass(frozen=True)
class Rules:
    min_rest_hours: int = 12
    days_off_per_week: int = 1
    max_consecutive_days: int = 6
    weekly_cap_minutes: int = 48 * 60
    max_consecutive_nights: int = 3
    response_hours: float = 2.0


@dataclass
class Plan:
    assignments: dict = field(default_factory=dict)  # (employee_id, date) -> template_id
    gaps: list = field(default_factory=list)


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def week_days(week_start: date) -> list[date]:
    return [week_start + timedelta(days=i) for i in range(7)]


def bounds(t: Template, day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Inicio y fin del turno en UTC (la hora local de la empresa respeta el horario
    de verano; en Python restar dos horas con la misma zona ignora ese salto)."""
    start = datetime.combine(day, t.start, tzinfo=tz)
    end_day = day + timedelta(days=1) if t.night else day
    end = datetime.combine(end_day, t.end, tzinfo=tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def hm(minutes: int) -> str:
    m = max(0, int(minutes))
    return f"{m // 60} h {m % 60:02d} min"


# ----------------------------------------------------------------- reglas duras
def violations(emp_id: str, sched: dict, templates: dict, rules: Rules, week_start: date, tz: ZoneInfo) -> list[str]:
    """Razones por las que la semana de esta persona rompe una regla dura
    (mirando tambien la semana anterior). Vacio = cumple todo."""
    reasons: list[str] = []
    days = sorted(d for (e, d) in sched if e == emp_id and week_start - timedelta(days=7) <= d <= week_start + timedelta(days=6))
    shifts = [(d, templates[sched[(emp_id, d)]]) for d in days if sched[(emp_id, d)] in templates]
    # Descanso entre turnos.
    for (d1, t1), (d2, t2) in zip(shifts, shifts[1:]):
        _, end1 = bounds(t1, d1, tz)
        start2, _ = bounds(t2, d2, tz)
        if (start2 - end1).total_seconds() < rules.min_rest_hours * 3600:
            reasons.append("rest")
            break
    week = [(d, t) for d, t in shifts if d >= week_start]
    # Tope semanal y dias libres.
    if sum(t.minutes for _, t in week) > rules.weekly_cap_minutes:
        reasons.append("cap")
    if len(week) > 7 - rules.days_off_per_week:
        reasons.append("days_off")
    # Dias y noches seguidas (contando la semana anterior).
    run = best = nights = best_n = 0
    prev: Optional[date] = None
    for d, t in shifts:
        run = run + 1 if prev is not None and d - prev == timedelta(days=1) else 1
        nights = (nights + 1 if prev is not None and d - prev == timedelta(days=1) else 1) if t.night else 0
        best, best_n, prev = max(best, run), max(best_n, nights), d
    if best > rules.max_consecutive_days:
        reasons.append("consecutive_days")
    if best_n > rules.max_consecutive_nights:
        reasons.append("consecutive_nights")
    return reasons


# ----------------------------------------------------------------- armar la malla
def build_week(employees: list[Employee], templates: list[Template], rules: Rules, coverage: dict, previous: dict,
               week_start: date, tz: ZoneInfo) -> Plan:
    """Borrador de la semana. coverage: {(template_id, role): minimo}. previous:
    {(employee_id, date): template_id} de la semana anterior (para descanso,
    dias y noches seguidas y la rotacion)."""
    tmap = {t.id: t for t in templates if t.active}
    order = sorted((t for t in tmap.values()), key=lambda t: (t.start, t.code, t.id))
    sched = dict(previous)
    plan = Plan()
    nights = {e.id: 0 for e in employees}
    weekends = {e.id: 0 for e in employees}
    minutes = {e.id: 0 for e in employees}
    by_role: dict[str, list[Employee]] = {}
    for e in employees:
        by_role.setdefault(e.role, []).append(e)
    for day in week_days(week_start):
        weekend = day.weekday() >= 5
        for t in order:
            for role in sorted({r for (tid, r), n in coverage.items() if tid == t.id and n > 0}):
                need = int(coverage[(t.id, role)])
                taken = sum(1 for e in by_role.get(role, []) if sched.get((e.id, day)) == t.id)
                pool = [e for e in by_role.get(role, []) if (e.id, day) not in sched]

                def score(e: Employee) -> tuple:
                    last_week = previous.get((e.id, day - timedelta(days=7)))
                    yesterday = sched.get((e.id, day - timedelta(days=1)))
                    return (
                        nights[e.id] if t.night else 0,            # noches parejas
                        weekends[e.id] if weekend else 0,         # fines de semana parejos
                        minutes[e.id],                            # horas parejas
                        1 if last_week == t.id else 0,            # rotar respecto a la semana anterior
                        1 if yesterday and yesterday != t.id else 0,  # no cambiar de turno cada dia
                        e.name.lower(), e.id,
                    )

                for e in sorted(pool, key=score):
                    if taken >= need:
                        break
                    sched[(e.id, day)] = t.id
                    if violations(e.id, sched, tmap, rules, week_start, tz):
                        del sched[(e.id, day)]
                        continue
                    taken += 1
                    plan.assignments[(e.id, day)] = t.id
                    minutes[e.id] += t.minutes
                    nights[e.id] += 1 if t.night else 0
                    weekends[e.id] += 1 if weekend else 0
                if taken < need:
                    plan.gaps.append({"date": day.isoformat(), "template_id": t.id, "template": t.name, "role": role, "missing": need - taken})
    return plan


def analyze(employees: list[Employee], templates: list[Template], rules: Rules, coverage: dict, previous: dict, week: dict,
            week_start: date, tz: ZoneInfo) -> dict:
    """Problemas de la semana (cobertura y descansos) y reparto de noches y fines de semana."""
    tmap = {t.id: t for t in templates}
    sched = {**previous, **week}
    gaps = []
    for day in week_days(week_start):
        for (tid, role), need in sorted(coverage.items()):
            if need <= 0 or tid not in tmap or not tmap[tid].active:
                continue
            have = sum(1 for e in employees if e.role == role and week.get((e.id, day)) == tid)
            if have < need:
                gaps.append({"date": day.isoformat(), "template_id": tid, "template": tmap[tid].name, "role": role, "missing": need - have})
    rest = [{"employee_id": e.id, "name": e.name, "reasons": r} for e in employees if (r := violations(e.id, sched, tmap, rules, week_start, tz))]
    fairness = []
    for e in employees:
        mine = [(d, tmap[tid]) for (eid, d), tid in week.items() if eid == e.id and tid in tmap]
        fairness.append({"employee_id": e.id, "name": e.name, "role": e.role, "nights": sum(1 for _, t in mine if t.night),
                         "weekends": sum(1 for d, _ in mine if d.weekday() >= 5), "minutes": sum(t.minutes for _, t in mine)})
    return {"gaps": gaps, "rest": rest, "fairness": fairness, "coverage_ok": not gaps, "rest_ok": not rest}


# ----------------------------------------------------------------- cambio de turno
REASON_ES = {"rest": "sin descanso", "cap": "pasa el tope", "days_off": "sin día libre", "consecutive_days": "días seguidos",
             "consecutive_nights": "noches seguidas", "role": "otro rol", "same": "es la misma persona", "same_shift": "ya tiene ese turno"}


def candidates(assignment: tuple, employees: list[Employee], templates: list[Template], rules: Rules, sched: dict, week_start: date,
               tz: ZoneInfo, stats: Optional[dict] = None, limit: int = 5) -> dict:
    """Candidatos para el turno (empleado, dia): "cubre" (esta libre) o
    "intercambio" (se cruzan turnos), del mismo rol y cumpliendo todas las reglas
    duras DESPUES del cambio. Orden: menos horas en la semana, mejor asistencia,
    mejor puntualidad y menos cambios recientes. stats: {id: {"attendance", "punctuality", "changes"}}."""
    emp_id, day = assignment
    tmap = {t.id: t for t in templates}
    tid = sched[(emp_id, day)]
    me = next(e for e in employees if e.id == emp_id)
    stats = stats or {}
    valid, discarded = [], []
    for c in sorted(employees, key=lambda e: (e.name.lower(), e.id)):
        if c.id == emp_id:
            continue
        if c.role != me.role:
            discarded.append({"employee_id": c.id, "name": c.name, "reasons": ["role"]})
            continue
        other = sched.get((c.id, day))
        trial = dict(sched)
        if other is None:
            kind = "cover"
            del trial[(emp_id, day)]
            trial[(c.id, day)] = tid
            bad = violations(c.id, trial, tmap, rules, week_start, tz)
        elif other == tid:
            discarded.append({"employee_id": c.id, "name": c.name, "reasons": ["same_shift"]})
            continue
        else:
            kind = "swap"
            trial[(emp_id, day)], trial[(c.id, day)] = other, tid
            bad = sorted(set(violations(c.id, trial, tmap, rules, week_start, tz)) | set(violations(emp_id, trial, tmap, rules, week_start, tz)))
        if bad:
            discarded.append({"employee_id": c.id, "name": c.name, "reasons": bad})
            continue
        week_minutes = sum(tmap[t].minutes for (e, d), t in trial.items() if e == c.id and d >= week_start and t in tmap)
        st = stats.get(c.id, {})
        valid.append({"employee_id": c.id, "name": c.name, "role": c.role, "kind": kind, "swap_template_id": other if kind == "swap" else None,
                      "week_minutes": week_minutes, "attendance": int(st.get("attendance", 0)), "punctuality": int(st.get("punctuality", 0)),
                      "changes": int(st.get("changes", 0)), "telegram": c.telegram})
    valid.sort(key=lambda v: (v["week_minutes"], -v["attendance"], -v["punctuality"], v["changes"], v["name"].lower(), v["employee_id"]))
    for v in valid:
        v["reasons"] = [f"{hm(v['week_minutes'])} en la semana", f"{v['attendance']} días con asistencia (30 días)",
                        f"{v['punctuality']} entradas a tiempo (30 días)", f"{v['changes']} cambios recientes"]
    picked = valid[:limit]
    return {"candidates": picked, "discarded": discarded, "enough": len(picked) >= 2}
