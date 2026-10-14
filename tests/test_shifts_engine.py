"""Turnos (modulo shifts): reglas, armado de la malla y candidatos (funciones puras).

- El armado cumple TODAS las reglas duras (cobertura, descanso contando la semana
  anterior, dias libres, dias seguidos, tope semanal y noches seguidas).
- Reparte noches y fines de semana con diferencia maxima de 1.
- Si no alcanza la gente marca el hueco sin romper reglas. Es determinista.
- Candidatos: nunca alguien que rompa descanso, tope, dias seguidos o rol; 2 a 5
  ordenados; el intercambio valida a las dos personas.
"""
from __future__ import annotations

import itertools
import random
from datetime import date, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.services import shifts_engine as eng

CHI = ZoneInfo("America/Chicago")
WEEK = date(2026, 10, 12)  # lunes
M = eng.Template("m", "M", "Mañana", time(6), time(14), "#f59e0b")
TA = eng.Template("t", "T", "Tarde", time(14), time(22), "#3b82f6")
N = eng.Template("n", "N", "Noche", time(22), time(6), "#7c3aed")
TPLS = [M, TA, N]
TMAP = {t.id: t for t in TPLS}
RULES = eng.Rules(min_rest_hours=12, days_off_per_week=1, max_consecutive_days=6, weekly_cap_minutes=40 * 60, max_consecutive_nights=3)


def ops(n: int, role: str = "operario", prefix: str = "o") -> list[eng.Employee]:
    return [eng.Employee(f"{prefix}{i}", f"{role.title()} {i}", role) for i in range(1, n + 1)]


def full(role: str = "operario", n: int = 1) -> dict:
    return {(t.id, role): n for t in TPLS}


def assert_hard_rules(employees, plan_or_week, rules=RULES, previous=None, coverage=None):
    week = plan_or_week.assignments if hasattr(plan_or_week, "assignments") else plan_or_week
    sched = {**(previous or {}), **week}
    for e in employees:
        assert eng.violations(e.id, sched, TMAP, rules, WEEK, CHI) == [], (e.name, sorted((d, t) for (x, d), t in week.items() if x == e.id))
    # nadie con dos turnos el mismo dia y nadie fuera de su rol
    roles = {e.id: e.role for e in employees}
    for (eid, d), tid in week.items():
        assert eid in roles
        if coverage:
            assert coverage.get((tid, roles[eid]), 0) > 0, "solo se asigna donde el rol tiene cobertura"


def test_full_week_meets_coverage_and_every_hard_rule():
    team = ops(5)
    plan = eng.build_week(team, TPLS, RULES, full(), {}, WEEK, CHI)
    assert plan.gaps == []
    an = eng.analyze(team, TPLS, RULES, full(), {}, plan.assignments, WEEK, CHI)
    assert an["coverage_ok"] and an["rest_ok"]
    assert_hard_rules(team, plan, coverage=full())
    for day in eng.week_days(WEEK):
        for t in TPLS:
            assert sum(1 for e in team if plan.assignments.get((e.id, day)) == t.id) == 1


@pytest.mark.parametrize("people,need", [(5, 1), (6, 1), (7, 1), (9, 2), (10, 2), (12, 2)])
def test_nights_and_weekends_spread_with_max_difference_one(people, need):
    team = ops(people)
    plan = eng.build_week(team, TPLS, RULES, full(n=need), {}, WEEK, CHI)
    assert plan.gaps == []
    an = eng.analyze(team, TPLS, RULES, full(n=need), {}, plan.assignments, WEEK, CHI)
    nights = [f["nights"] for f in an["fairness"]]
    weekends = [f["weekends"] for f in an["fairness"]]
    assert max(nights) - min(nights) <= 1, nights
    assert max(weekends) - min(weekends) <= 1, weekends
    assert_hard_rules(team, plan)


def test_not_enough_people_marks_the_gap_and_breaks_nothing():
    team = ops(2)
    plan = eng.build_week(team, TPLS, RULES, full(), {}, WEEK, CHI)
    assert plan.gaps, "con 2 personas no se cubren 3 turnos diarios"
    assert all(g["missing"] >= 1 and g["role"] == "operario" for g in plan.gaps)
    assert_hard_rules(team, plan)
    an = eng.analyze(team, TPLS, RULES, full(), {}, plan.assignments, WEEK, CHI)
    assert not an["coverage_ok"] and an["rest_ok"]
    assert {(g["date"], g["template_id"]) for g in an["gaps"]} == {(g["date"], g["template_id"]) for g in plan.gaps}


def test_missing_role_is_a_gap_too():
    team = ops(5)
    cov = {**full(), ("n", "supervisor"): 1}
    plan = eng.build_week(team, TPLS, RULES, cov, {}, WEEK, CHI)
    assert len([g for g in plan.gaps if g["role"] == "supervisor"]) == 7


def test_deterministic_regardless_of_input_order():
    team = ops(7)
    a = eng.build_week(team, TPLS, RULES, full(), {}, WEEK, CHI)
    b = eng.build_week(list(reversed(team)), list(reversed(TPLS)), RULES, dict(reversed(list(full().items()))), {}, WEEK, CHI)
    assert a.assignments == b.assignments and a.gaps == b.gaps


def test_previous_week_counts_for_rest_consecutive_days_and_nights():
    team = ops(5)
    prev_sunday = WEEK - timedelta(days=1)
    # o1 hizo noche el domingo (termina lunes 06:00): no puede entrar lunes 06:00 ni 14:00.
    # o2 trabajo 6 dias seguidos hasta el domingo: el lunes queda libre.
    # o3 hizo 3 noches seguidas hasta el domingo: el lunes no hace noche.
    previous = {("o1", prev_sunday): "n"}
    previous.update({("o2", prev_sunday - timedelta(days=i)): "m" for i in range(6)})
    previous.update({("o3", prev_sunday - timedelta(days=i)): "n" for i in range(3)})
    plan = eng.build_week(team, TPLS, RULES, full(), previous, WEEK, CHI)
    assert plan.assignments.get(("o1", WEEK)) not in {"m", "t"}
    assert ("o2", WEEK) not in plan.assignments
    assert plan.assignments.get(("o3", WEEK)) != "n"
    assert_hard_rules(team, plan, previous=previous)


def test_soft_rule_rotates_against_previous_week():
    team = ops(6)
    first = eng.build_week(team, TPLS, RULES, full(), {}, WEEK, CHI).assignments
    previous = {(e, d - timedelta(days=7)): t for (e, d), t in first.items()}
    second = eng.build_week(team, TPLS, RULES, full(), previous, WEEK, CHI).assignments
    same = sum(1 for (e, d), t in second.items() if first.get((e, d)) == t)
    assert same < len(second), "la semana siguiente no copia la anterior"


def test_random_scenarios_never_break_a_hard_rule():
    rnd = random.Random(7)
    for _ in range(40):
        team = ops(rnd.randint(1, 9)) + ops(rnd.randint(0, 3), "supervisor", "s")
        rules = eng.Rules(min_rest_hours=rnd.choice([8, 11, 12, 16]), days_off_per_week=rnd.choice([0, 1, 2]), max_consecutive_days=rnd.choice([3, 5, 6]),
                          weekly_cap_minutes=rnd.choice([24, 36, 40, 48]) * 60, max_consecutive_nights=rnd.choice([1, 2, 3]))
        cov = {(t.id, r): rnd.choice([0, 1, 1, 2]) for t, r in itertools.product(TPLS, ["operario", "supervisor"])}
        prev = {(e.id, WEEK - timedelta(days=d)): rnd.choice(["m", "t", "n"]) for e in team for d in range(1, 8) if rnd.random() < .6}
        plan = eng.build_week(team, TPLS, rules, cov, prev, WEEK, CHI)
        prev_ok = {e.id for e in team if not eng.violations(e.id, prev, TMAP, rules, WEEK - timedelta(days=7), CHI)}
        sched = {**prev, **plan.assignments}
        for e in team:
            if e.id in prev_ok:
                assert eng.violations(e.id, sched, TMAP, rules, WEEK, CHI) == []
        an = eng.analyze(team, TPLS, rules, cov, prev, plan.assignments, WEEK, CHI)
        assert {(g["date"], g["template_id"], g["role"]) for g in an["gaps"]} == {(g["date"], g["template_id"], g["role"]) for g in plan.gaps}


def test_night_shift_counts_for_the_day_it_starts_and_dst_is_respected():
    assert N.night and N.minutes == 480
    start, end = eng.bounds(N, date(2026, 10, 31), CHI)  # sabado; el domingo 1 nov termina el horario de verano
    assert start.astimezone(CHI).date() == date(2026, 10, 31) and end.astimezone(CHI).date() == date(2026, 11, 1)
    assert (end - start).total_seconds() == 9 * 3600, "esa noche dura una hora mas en el reloj real"
    assert eng.hm(2400) == "40 h 00 min" and eng.hm(125) == "2 h 05 min"


# ------------------------------------------------------------------ candidatos
def _published_week():
    team = ops(6)
    plan = eng.build_week(team, TPLS, RULES, full(), {}, WEEK, CHI)
    return team, dict(plan.assignments)


def test_candidates_never_break_rest_cap_consecutive_or_role_and_are_ordered():
    team, sched = _published_week()
    team = team + [eng.Employee("x1", "Sofía Supervisora", "supervisor")]
    stats = {e.id: {"attendance": i, "punctuality": i, "changes": 0} for i, e in enumerate(team)}
    checked = 0
    for (eid, day), tid in sorted(sched.items()):
        out = eng.candidates((eid, day), team, TPLS, RULES, sched, WEEK, CHI, stats)
        assert 0 <= len(out["candidates"]) <= 5
        assert out["enough"] == (len(out["candidates"]) >= 2)
        keys = [(c["week_minutes"], -c["attendance"], -c["punctuality"], c["changes"]) for c in out["candidates"]]
        assert keys == sorted(keys), "menos horas, mejor asistencia y puntualidad, menos cambios"
        for c in out["candidates"]:
            assert c["role"] == "operario" and c["employee_id"] != eid
            trial = dict(sched)
            if c["kind"] == "cover":
                assert (c["employee_id"], day) not in sched
                del trial[(eid, day)]
                trial[(c["employee_id"], day)] = tid
            else:
                trial[(eid, day)], trial[(c["employee_id"], day)] = sched[(c["employee_id"], day)], tid
                assert eng.violations(eid, trial, TMAP, RULES, WEEK, CHI) == [], "el intercambio valida a quien pide"
            assert eng.violations(c["employee_id"], trial, TMAP, RULES, WEEK, CHI) == []
        assert any(d["employee_id"] == "x1" and d["reasons"] == ["role"] for d in out["discarded"])
        checked += 1
    assert checked == len(sched)


def test_swap_is_discarded_when_it_breaks_the_requester():
    a, b = eng.Employee("a", "Ana", "operario"), eng.Employee("b", "Beto", "operario")
    tue = WEEK + timedelta(days=1)
    # Ana: lunes noche (termina martes 06:00) y martes noche. Beto: martes manana.
    # Cruzar el martes dejaria a Ana entrando a las 06:00 tras salir a las 06:00: sin descanso.
    sched = {("a", WEEK): "n", ("a", tue): "n", ("b", tue): "m"}
    out = eng.candidates(("a", tue), [a, b], TPLS, RULES, sched, WEEK, CHI)
    assert out["candidates"] == [] and not out["enough"]
    assert out["discarded"] == [{"employee_id": "b", "name": "Beto", "reasons": ["rest"]}]


def test_fewer_than_two_valid_candidates_is_reported_not_invented():
    team = ops(2)
    sched = {("o1", WEEK): "m"}
    out = eng.candidates(("o1", WEEK), team, TPLS, eng.Rules(weekly_cap_minutes=40 * 60), sched, WEEK, CHI)
    assert len(out["candidates"]) == 1 and out["enough"] is False


def test_cap_blocks_a_cover():
    team = ops(2)
    sched = {("o1", WEEK): "m"}
    sched.update({("o2", WEEK + timedelta(days=i)): "t" for i in range(1, 6)})  # o2 ya tiene 40 h
    out = eng.candidates(("o1", WEEK), team, TPLS, RULES, sched, WEEK, CHI)
    assert out["candidates"] == [] and out["discarded"][0]["reasons"] == ["cap"]
