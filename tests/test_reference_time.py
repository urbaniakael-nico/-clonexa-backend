"""Tiempo por referencia en un periodo (app.services.reference_time): la regla unica.

Ventana de Bogota (00:00 de Desde a 23:59:59 de Hasta), trabajado = conectado - pausas,
recortado a la ventana (sesiones, turnos y pausas que cruzan el borde se recortan),
sin contar doble al cambiar de referencia, "Sin referencia" aparte, sesion abierta
hasta "ahora" solo si el periodo incluye hoy, y ampliar el periodo NUNCA reduce.
Datos ficticios.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.services import reference_time as rt

BOG = ZoneInfo("America/Bogota")
NOW = datetime(2026, 10, 30, 15, 0, tzinfo=BOG).astimezone(timezone.utc)  # hoy: 30 oct, 3:00 p. m. en Bogota


def B(day: int, hour: int, minute: int = 0, month: int = 10) -> datetime:
    """Hora de Bogota -> UTC."""
    return datetime(2026, month, day, hour, minute, tzinfo=BOG).astimezone(timezone.utc)


def shift(start, end, *breaks):
    return {"start": start, "end": end, "breaks": list(breaks)}


def sess(who, ref, start, end):
    return {"employee_id": who, "reference_name": ref, "started_at": start, "ended_at": end}


def calc(a: int, b: int, shifts, sessions, now=NOW, month=10):
    return rt.compute(start=date(2026, month, a), end=date(2026, month, b), now=now, shifts=shifts, sessions=sessions)


H = 3600


def test_window_is_bogota_midnight_to_midnight():
    lo, hi = rt.window(date(2026, 10, 15), date(2026, 10, 28))
    assert lo == datetime(2026, 10, 15, 5, 0, tzinfo=timezone.utc), "00:00 en Bogota = 05:00 UTC"
    assert hi == datetime(2026, 10, 29, 5, 0, tzinfo=timezone.utc), "hasta las 23:59:59 del 28 incluido"


def test_session_inside_shift_minus_pauses():
    r = calc(20, 20, {"ana": [shift(B(20, 8), B(20, 17), (B(20, 12), B(20, 13)))]}, [sess("ana", "Choco-fresa", B(20, 8), B(20, 17))])
    assert r["by_reference"] == {"Choco-fresa": 8 * H}, "9 h conectada - 1 h de pausa"
    assert r["worked"] == {"ana": 8 * H} and r["no_reference"] == 0


def test_session_crossing_midnight_splits_by_day():
    data = ({"ana": [shift(B(20, 20), B(21, 4))]}, [sess("ana", "Choco-fresa", B(20, 20), B(21, 4))])
    assert calc(20, 20, *data)["by_reference"]["Choco-fresa"] == 4 * H, "20:00 a 24:00 del 20"
    assert calc(21, 21, *data)["by_reference"]["Choco-fresa"] == 4 * H, "00:00 a 04:00 del 21"
    assert calc(20, 21, *data)["by_reference"]["Choco-fresa"] == 8 * H


def test_session_crossing_start_and_end_of_period_is_clipped():
    data = ({"ana": [shift(B(14, 20), B(15, 6)), shift(B(28, 18), B(29, 3))]},
            [sess("ana", "Choco-fresa", B(14, 20), B(15, 6)), sess("ana", "Choco-fresa", B(28, 18), B(29, 3))])
    r = calc(15, 28, *data)
    assert r["by_reference"]["Choco-fresa"] == 6 * H + 6 * H, "00:00-06:00 del 15 y 18:00-24:00 del 28"


def test_pause_crossing_the_border_is_clipped_too():
    data = ({"ana": [shift(B(20, 20), B(21, 6), (B(20, 23), B(21, 1)))]}, [sess("ana", "Dreamy Jacket", B(20, 20), B(21, 6))])
    assert calc(20, 20, *data)["by_reference"]["Dreamy Jacket"] == 3 * H, "20:00-23:00 (la pausa 23:00-24:00 no cuenta)"
    assert calc(21, 21, *data)["by_reference"]["Dreamy Jacket"] == 5 * H, "01:00-06:00 (la pausa 00:00-01:00 no cuenta)"


def test_open_session_counts_until_now_only_if_the_period_includes_today():
    data = ({"ana": [shift(B(30, 8), None)]}, [sess("ana", "Choco-fresa", B(30, 8), None)])
    assert calc(30, 30, *data)["by_reference"]["Choco-fresa"] == 7 * H, "8:00 a las 3:00 p. m. (ahora)"
    assert calc(15, 29, *data)["by_reference"] == {}, "el periodo no incluye hoy"
    assert calc(30, 31, *data)["by_reference"]["Choco-fresa"] == 7 * H, "nunca despues de ahora"
    open_pause = calc(30, 30, {"ana": [shift(B(30, 8), None, (B(30, 14), None))]}, [sess("ana", "Choco-fresa", B(30, 8), None)])
    assert open_pause["by_reference"]["Choco-fresa"] == 6 * H, "la pausa abierta corre hasta ahora"


def test_reference_switch_mid_shift_never_counts_twice():
    shifts = {"ana": [shift(B(20, 8), B(20, 16))]}
    # la primera sesion quedo "abierta" hasta las 16 en el registro, pero a las 12 empezo otra: manda la nueva
    r = calc(20, 20, shifts, [sess("ana", "Choco-fresa", B(20, 8), B(20, 16)), sess("ana", "Aurora Cafe", B(20, 12), B(20, 16))])
    assert r["by_reference"] == {"Choco-fresa": 4 * H, "Aurora Cafe": 4 * H}
    assert sum(r["by_reference"].values()) == r["total_worked"] == 8 * H
    assert any(a["kind"] == "sesiones_solapadas" for a in r["anomalies"])


def test_time_without_reference_is_shown_apart_and_sums_match():
    shifts = {"ana": [shift(B(20, 8), B(20, 16))], "eva": [shift(B(20, 9), B(20, 13))]}
    r = calc(20, 20, shifts, [sess("ana", "Choco-fresa", B(20, 10), B(20, 14)), sess("eva", "Choco-fresa", B(20, 9), B(20, 13))])
    assert r["by_person"]["ana"] == {"Choco-fresa": 4 * H, rt.NO_REFERENCE: 4 * H}
    assert r["by_reference"] == {"Choco-fresa": 8 * H, rt.NO_REFERENCE: 4 * H} and r["no_reference"] == 4 * H
    assert sum(r["by_reference"].values()) == r["total_worked"] == 12 * H, "referencias + sin referencia = trabajado de todos"
    for who, refs in r["by_person"].items():
        assert sum(refs.values()) == r["worked"][who], "la suma por persona = su trabajado"


def test_session_outside_the_shift_does_not_count_and_is_listed():
    r = calc(20, 20, {"ana": [shift(B(20, 8), B(20, 12))]}, [sess("ana", "Choco-fresa", B(20, 8), B(20, 15))])
    assert r["by_reference"] == {"Choco-fresa": 4 * H}
    out = [a for a in r["anomalies"] if a["kind"] == "sesion_fuera_de_turno"]
    assert out and out[0]["seconds"] == 3 * H


def test_timezone_borders():
    late = B(28, 23, 30)  # 23:30 del 28 en Bogota = 04:30 UTC del 29
    data = ({"ana": [shift(late, late + timedelta(hours=1))]}, [sess("ana", "Choco-fresa", late, late + timedelta(hours=1))])
    assert calc(28, 28, *data)["by_reference"]["Choco-fresa"] == 30 * 60, "23:30-24:00 es del 28 en Bogota, aunque en UTC ya sea el 29"
    assert calc(29, 29, *data)["by_reference"]["Choco-fresa"] == 30 * 60
    assert calc(27, 27, *data)["by_reference"] == {}


def test_widening_the_period_never_reduces_any_time():
    rng = random.Random(1026)
    people = ["ana", "eva", "kim"]
    refs = ["Choco-fresa", "Dreamy Jacket", "Aurora Cafe"]
    for _ in range(25):
        shifts, sessions = {}, []
        for who in people:
            for day in range(10, 31):
                if rng.random() < 0.3:
                    continue
                start = B(day, rng.randint(5, 20), rng.choice((0, 15, 30, 45)))
                end = None if day == 30 and rng.random() < 0.5 else start + timedelta(minutes=rng.randint(60, 11 * 60))
                pauses = []
                if rng.random() < 0.6:
                    p0 = start + timedelta(minutes=rng.randint(10, 200))
                    pauses.append((p0, None if rng.random() < 0.1 else p0 + timedelta(minutes=rng.randint(5, 90))))
                shifts.setdefault(who, []).append(shift(start, end, *pauses))
                t = start - timedelta(minutes=rng.randint(0, 30))
                for _k in range(rng.randint(1, 3)):
                    e = None if rng.random() < 0.15 else t + timedelta(minutes=rng.randint(20, 400))
                    sessions.append(sess(who, rng.choice(refs), t, e))
                    t = t + timedelta(minutes=rng.randint(30, 300))
        base = calc(15, 28, shifts, sessions)
        for b in (29, 30, 31):
            wider = calc(15, b, shifts, sessions)
            for ref, secs in base["by_reference"].items():
                assert wider["by_reference"].get(ref, 0) >= secs, f"{ref}: 15-28 {secs} > 15-{b} {wider['by_reference'].get(ref, 0)}"
            for who, mine in base["by_person"].items():
                for ref, secs in mine.items():
                    assert wider["by_person"].get(who, {}).get(ref, 0) >= secs
            assert sum(wider["by_reference"].values()) == wider["total_worked"]
        earlier = calc(10, 28, shifts, sessions)
        for ref, secs in base["by_reference"].items():
            assert earlier["by_reference"].get(ref, 0) >= secs, "ampliar hacia atras tampoco reduce"


def test_no_activity_after_day_x_gives_the_same_time():
    data = ({"ana": [shift(B(20, 8), B(20, 16))]}, [sess("ana", "Choco-fresa", B(20, 8), B(20, 16))])
    assert calc(15, 28, *data)["by_reference"] == calc(15, 30, *data)["by_reference"] == {"Choco-fresa": 8 * H}


def test_shift_pairing_like_payroll_and_odd_records_listed():
    ev = lambda kind, at: {"employee_id": "ana", "kind": kind, "at": at}  # noqa: E731
    shifts, odd = rt.build_shifts([
        ev("check_in", B(20, 8)), ev("break_start", B(20, 12)), ev("check_out", B(20, 17)),  # pausa sin retorno: la cierra la salida
        ev("break_end", B(21, 7)),  # retorno sin turno
        ev("check_in", B(21, 8)), ev("break_end", B(21, 9)), ev("break_start", B(21, 10)), ev("break_start", B(21, 10, 5)),
        ev("break_end", B(21, 10, 30)), ev("check_out", B(21, 16)),
        ev("check_in", B(22, 8)), ev("check_in", B(23, 8)),  # entrada sin salida: la reemplaza la siguiente (como la Nomina)
    ], NOW)
    s = shifts["ana"]
    assert [(x["start"], x["end"]) for x in s] == [(B(20, 8), B(20, 17)), (B(21, 8), B(21, 16)), (B(23, 8), None)]
    assert s[0]["breaks"] == [(B(20, 12), B(20, 17))] and s[1]["breaks"] == [(B(21, 10), B(21, 10, 30))]
    kinds = sorted(a["kind"] for a in odd)
    assert kinds == sorted(["pausa_sin_fin", "break_end_fuera_de_turno", "retorno_sin_pausa", "pausa_repetida", "entrada_sin_salida",
                            "turno_sin_cierre"])
    worked = rt.worked_intervals(s[:2], NOW)
    assert rt._seconds(worked) == 4 * H + (8 * H - 30 * 60)


# ---------------------------------------------------------- Postgres real ---
pgserver = pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402

from tests.test_crm_lab_pg import company, employee, pg_url, run  # noqa: E402,F401  (fixture de Postgres real)


async def _event(db, cid, eid, kind, at):
    await db.execute(text("""INSERT INTO workforce_attendance_events (company_id, employee_id, event_type, event_label, status_after, occurred_at, created_at)
        VALUES (CAST(:c AS uuid), CAST(:e AS uuid), :k, :k, 'x', :at, :at)"""), {"c": cid, "e": eid, "k": kind, "at": at})


async def _session(db, cid, eid, ref, start, end):
    await db.execute(text("""INSERT INTO reference_work_sessions (id, company_id, employee_id, employee_name, reference_name, started_at, ended_at, status)
        VALUES (gen_random_uuid()::text, :c, :e, 'x', :r, :s, :t, :st)"""), {"c": cid, "e": eid, "r": ref, "s": start, "t": end, "st": "ended_with_shift" if end else "active"})


def test_load_against_real_tables_only_that_company_and_switch(pg_url, monkeypatch):  # noqa: F811
    from app.api.v1.endpoints import production_v1 as prod
    from app.services import production_v2

    async def go(db):
        cid = await company(db, "VelvetTiempo")
        other = await company(db, "OtraTiempo")
        ana = await employee(db, cid, "Ana")
        ajena = await employee(db, other, "Ajena")
        for who, c in ((ana, cid), (ajena, other)):
            await _event(db, c, who, "check_in", B(20, 8))
            await _event(db, c, who, "break_start", B(20, 12))
            await _event(db, c, who, "break_end", B(20, 13))
            await _event(db, c, who, "check_out", B(20, 17))
        await _session(db, cid, ana, "Choco-fresa", B(20, 8), B(20, 11))
        await _session(db, cid, ana, "Aurora Cafe", B(20, 11), B(20, 17))
        await _session(db, other, ajena, "Choco-fresa", B(20, 8), B(20, 17))
        await db.commit()
        r = await rt.load(db, cid, date(2026, 10, 15), date(2026, 10, 28), now=NOW)
        assert r["by_reference"] == {"Choco-fresa": 3 * H, "Aurora Cafe": 5 * H}, "solo esa empresa; la pausa 12-13 no cuenta"
        assert r["names"][ana] == "Ana" and ajena not in r["names"]
        wider = await rt.load(db, cid, date(2026, 10, 15), date(2026, 10, 30), now=NOW)
        assert wider["by_reference"] == r["by_reference"]
        # Produccion: solo las empresas con production_v2 usan la regla nueva; las demas siguen igual
        calls = []

        async def legacy_marker(db_, c, a, b):
            calls.append(c)
            return {"time_by_reference": []}

        monkeypatch.setattr(production_v2, "is_on", lambda db_, c: _async(c == cid))
        out = await prod.sessions_summary(db, cid, date(2026, 10, 15), date(2026, 10, 28))
        assert out["query_strategy"] == "reference_time" and out["payroll_cap_applied"] is False
        assert {t["reference_name"]: t["total_effective_seconds"] for t in out["time_by_reference"]} == {"Choco-fresa": 3 * H, "Aurora Cafe": 5 * H}
        assert out["total_effective_seconds_period"] == 8 * H
        monkeypatch.setattr(prod, "_prod_sessions_summary_reference_time", legacy_marker)
        legacy = await prod.sessions_summary(db, other, date(2026, 10, 15), date(2026, 10, 28))
        assert calls == [] and legacy.get("query_strategy") != "reference_time", "sin production_v2: el calculo de siempre"

    run(pg_url, go)


async def _async(value):
    return value
