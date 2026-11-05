"""Tiempo de una referencia (068A): nunca baja al ampliar el rango y el total es fijo.

El caso real: en Velvet, Choco-fresa daba 214:27 / 214:59 / 218:33 / 212:28 segun la fecha final
(27, 28, 29, 30 de octubre), porque el tope de nomina repartia en proporcion. La regla nueva no
mira el rango para calcular los tramos de cada sesion. tests/fixtures/velvet_choco_fresa.json trae
los datos reales de esas personas, anonimizados.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.api.v1.endpoints import payroll as core
from app.services import quotes_v2
from app.services import reference_lifecycle as life
from app.services import reference_time as rt
from app.services.references_v2 import group_key

BOG = ZoneInfo("America/Bogota")
DATA = json.loads((Path(__file__).parent / "fixtures" / "velvet_choco_fresa.json").read_text(encoding="utf-8"))
KIND = {"check_in": "check_in", "break_start": "break_start", "break_end": "break_end", "check_out": "check_out"}


def dt(value):
    return datetime.fromisoformat(value) if isinstance(value, str) else value


def classify(ev):
    return KIND.get(ev["type"], "other")


def verification(closures=None, hours=12.0):
    return {"closures": closures or {}, "limit_seconds": hours * 3600}


def shifts_of(events, closures=None, cutoff=lambda e: False, hours=12.0):
    return rt.build_shifts(events, classify, core._cx_check_shift_049D, cutoff, verification(closures, hours))


def real_items():
    events = [{**e, "occurred_at": dt(e["occurred_at"])} for e in DATA["events"]]
    closures = {(c["source"], c["session_ref"]): c | {"real_end_at": dt(c["real_end_at"])} for c in DATA["closures"]}
    shifts = shifts_of(events, closures, hours=DATA["limit_hours"])
    sessions = [{**s, "started_at": dt(s["started_at"]), "ended_at": dt(s["ended_at"]) if s["ended_at"] else None} for s in DATA["sessions"]]
    return rt.resolve_sessions(sessions, shifts, group_key)


def choco(items, start, end):
    lo, hi = rt.period_bounds(start, end, BOG)
    return rt.summarize([i for i in items if i["key"] == group_key("Choco-fresa")], lo, hi)[group_key("Choco-fresa")]


def hours_minutes(seconds):
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}"


def test_choco_fresa_real_nunca_baja_y_el_total_es_fijo():
    items = real_items()
    start = date(2026, 10, 15)
    seen = {d: choco(items, start, date(2026, 10, d)) for d in (27, 28, 29, 30)}
    assert [hours_minutes(seen[d]["period_seconds"]) for d in (27, 28, 29, 30)] == ["210:51", "210:51", "214:46", "214:46"]
    assert {hours_minutes(s["total_seconds"]) for s in seen.values()} == {"215:39"}, "el total no depende del filtro"
    for summary in seen.values():
        assert summary["total_seconds"] == sum(p["total_seconds"] for p in summary["people"]), "total = suma por operario"
        assert summary["period_seconds"] == sum(p["period_seconds"] for p in summary["people"]), "periodo = suma por operario"
        assert summary["unclosed"] == []
    # La parte fuera del periodo es la sesion del 14 de octubre (0:53).
    assert hours_minutes(seen[30]["total_seconds"] - seen[30]["period_seconds"]) == "0:53"


def test_choco_fresa_real_ningun_rango_creciente_baja():
    items = real_items()
    for start in (date(2026, 10, 14), date(2026, 10, 15), date(2026, 10, 20)):
        previous = -1
        for n in range(0, 25):
            value = choco(items, start, start + timedelta(days=n))["period_seconds"]
            assert value >= previous, f"bajo con {start} + {n} dias"
            previous = value


def test_otras_referencias_no_mueven_el_tiempo_de_choco_fresa():
    """El origen de la fluctuacion: horas en OTRAS referencias le bajaban la cifra por el tope."""
    items = real_items()
    base = choco(items, date(2026, 10, 15), date(2026, 10, 30))
    other = [i for i in items if i["key"] == group_key("Choco-fresa")]
    assert choco(other, date(2026, 10, 15), date(2026, 10, 30))["period_seconds"] == base["period_seconds"]


def test_horas_de_cada_persona_coinciden_con_la_hora_real_confirmada():
    """El turno olvidado del 20-oct (salida 08:14 del dia siguiente) vale hasta la hora real confirmada, no 21 horas."""
    items = [i for i in real_items() if i["key"] == group_key("Choco-fresa")]
    long_one = next(i for i in items if (i["ended"] - i["started"]) > timedelta(hours=20))
    assert hours_minutes(int(rt.overlap_seconds(long_one["segments"]))) == "6:18"


# ---------------------------------------------------------------- reglas puras
UTC = timezone.utc


def at(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC)


def session(emp="A", ref="Lote", start=None, end=None, status="closed"):
    return {"employee_id": emp, "employee_name": emp, "reference_name": ref, "started_at": start, "ended_at": end, "status": status}


def ev(emp, kind, when, ident=None):
    return {"id": ident or f"{emp}-{kind}-{when.isoformat()}", "employee_id": emp, "type": kind, "occurred_at": when}


def test_descuenta_las_pausas_dentro_de_la_sesion():
    shifts = shifts_of([ev("A", "check_in", at(5, 13)), ev("A", "break_start", at(5, 15)), ev("A", "break_end", at(5, 16)), ev("A", "check_out", at(5, 21))])
    items = rt.resolve_sessions([session(start=at(5, 13), end=at(5, 21))], shifts, group_key)
    assert rt.overlap_seconds(items[0]["segments"]) == 7 * 3600


def test_sesion_abierta_sale_sin_cerrar_y_no_suma():
    shifts = shifts_of([ev("A", "check_in", at(5, 13))])
    items = rt.resolve_sessions([session(start=at(5, 13), end=None, status="active")], shifts, group_key)
    out = rt.summarize(items, None, None)[group_key("Lote")]
    assert out["total_seconds"] == 0 and out["unclosed"][0]["reason"] == rt.OPEN


def test_turno_retenido_no_suma_hasta_que_se_confirma():
    long_shift = [ev("A", "check_in", at(5, 13), "in1"), ev("A", "check_out", at(6, 13), "out1")]
    items = rt.resolve_sessions([session(start=at(5, 13), end=at(6, 13))], shifts_of(long_shift), group_key)
    assert rt.overlap_seconds(items[0]["segments"]) == 0 and items[0]["unclosed"] == rt.HOLD
    confirmed = {("attendance", "in1"): {"status": "confirmed", "real_end_at": at(5, 21)}}
    items = rt.resolve_sessions([session(start=at(5, 13), end=at(6, 13))], shifts_of(long_shift, confirmed), group_key)
    assert rt.overlap_seconds(items[0]["segments"]) == 8 * 3600 and items[0]["unclosed"] is None


def test_en_un_turno_retenido_el_tramo_con_cambio_real_si_cuenta():
    long_shift = [ev("A", "check_in", at(5, 13)), ev("A", "check_out", at(6, 13))]
    sessions = [session(ref="Primera", start=at(5, 13), end=at(5, 15)), session(ref="Olvidada", start=at(5, 15), end=at(6, 13))]
    items = {i["name"]: i for i in rt.resolve_sessions(sessions, shifts_of(long_shift), group_key)}
    assert rt.overlap_seconds(items["Primera"]["segments"]) == 2 * 3600 and items["Primera"]["unclosed"] is None
    assert rt.overlap_seconds(items["Olvidada"]["segments"]) == 0 and items["Olvidada"]["unclosed"] == rt.HOLD


def test_sesiones_duplicadas_de_la_misma_persona_cuentan_una_vez():
    items = rt.resolve_sessions([session(start=at(5, 13), end=at(5, 17)), session(start=at(5, 13), end=at(5, 17)), session(start=at(5, 15), end=at(5, 19))], {}, group_key)
    assert rt.summarize(items, None, None)[group_key("Lote")]["total_seconds"] == 6 * 3600


def test_sesion_que_cruza_la_medianoche_de_bogota_se_parte_en_el_limite():
    # 22:00 a 02:00 hora de Bogota del 10 al 11 de octubre.
    items = rt.resolve_sessions([session(start=at(11, 3), end=at(11, 7))], {}, group_key)
    lo, hi = rt.period_bounds(date(2026, 10, 10), date(2026, 10, 10), BOG)
    assert rt.summarize(items, lo, hi)[group_key("Lote")]["period_seconds"] == 2 * 3600
    lo, hi = rt.period_bounds(date(2026, 10, 11), date(2026, 10, 11), BOG)
    assert rt.summarize(items, lo, hi)[group_key("Lote")]["period_seconds"] == 2 * 3600


def test_entrada_sin_salida_no_deja_un_turno_abierto_para_siempre():
    shifts = shifts_of([ev("A", "check_in", at(5, 13)), ev("A", "check_in", at(6, 13)), ev("A", "check_out", at(6, 21))])
    items = rt.resolve_sessions([session(start=at(6, 13), end=at(6, 21))], shifts, group_key)
    assert rt.overlap_seconds(items[0]["segments"]) == 8 * 3600, "no cuenta doble con el turno olvidado"


# ---------------------------------------------------------------- cuentas por talla
GROUP = {"key": "lote", "name": "Lote", "lines": [
    {"size": "S", "reference_id": "s", "meta": 44, "received": 44, "produced": 40, "pending": 4, "bot_active": False},
    {"size": "M", "reference_id": "m", "meta": 14, "received": 14, "produced": 14, "pending": 0, "bot_active": False},
]}


def closes(*rows):
    return [{"size": z, "closed_qty": q, "reason_code": c, "reason_note": None, "closed_at": at(20, 15), "actor": "Dueña"} for z, q, c in rows]


def test_cuenta_por_talla_total_es_la_suma_y_se_reparte_por_cantidad():
    time_info = {"total_seconds": 54 * 3600 + 7, "first": "2026-10-15T12:00:00+00:00"}
    acc = life.accounts(GROUP, closes(("S", 40, "merma"), ("M", 14, None)), time_info, {"status": "ok", "amount": 540000.5, "missing": []}, BOG)
    sizes = {s["size"]: s for s in acc["sizes"]}
    assert acc["status"] == "closed" and acc["allocation"] == "repartido por cantidad"
    assert sizes["S"]["seconds"] == 40 * 3600 + 5 or sizes["S"]["seconds"] == 40 * 3600 + 6
    assert sum(s["seconds"] for s in acc["sizes"]) == acc["totals"]["seconds"] == time_info["total_seconds"], "no se pierde ni un segundo"
    assert acc["totals"]["labor"] == 540000.5 and round(sum(s["labor"] for s in acc["sizes"]), 2) == 540000.5
    assert sizes["S"]["diff_received"] == -4 and sizes["S"]["diff_meta"] == -4 and sizes["S"]["reason_label"] == "Merma"
    assert sizes["S"]["days"] == 6 and acc["totals"]["closed_qty"] == 54 and acc["totals"]["days"] == 6


def test_sin_valor_hora_la_mano_de_obra_queda_pendiente():
    acc = life.accounts(GROUP, closes(("S", 40, None)), {"total_seconds": 3600}, {"status": "pendiente", "amount": None, "missing": ["KRIS"]}, BOG)
    assert acc["status"] == "open" and acc["labor_status"] == "pendiente" and acc["labor_missing"] == ["KRIS"]
    assert acc["sizes"][0]["labor_per_garment"] is None and acc["totals"]["labor_per_garment"] is None


def test_por_prenda_se_calcula_con_prendas_cerradas():
    labor = {"status": "ok", "amount": 540000.0, "missing": []}
    info = {"total_seconds": 72600, "first": "2026-10-15T12:00:00+00:00"}  # el caso Dreamy: 20 h 10 entre 1 h de producido daba cifras enganosas
    none = life.accounts(GROUP, [], info, labor, BOG)
    assert none["totals"]["minutes_per_garment"] is None and none["totals"]["labor_per_garment"] is None, "sin cerradas no hay cifra"
    assert all(s["minutes_per_garment"] is None and s["labor_per_garment"] is None for s in none["sizes"])
    partial = life.accounts(GROUP, closes(("S", 40, "merma")), info, labor, BOG)
    sizes = {s["size"]: s for s in partial["sizes"]}
    assert partial["totals"]["minutes_per_garment"] == sizes["S"]["minutes_per_garment"] == round(sizes["S"]["seconds"] / 40 / 60, 1)
    assert partial["totals"]["labor_per_garment"] == sizes["S"]["labor_per_garment"]
    assert sizes["M"]["minutes_per_garment"] is None, "una talla abierta no tiene cifra por prenda"
    assert partial["totals"]["seconds"] == 72600, "el total de horas sigue siendo la suma de todas las tallas"


def test_labor_of_usa_el_valor_de_cada_persona_y_avisa_si_falta():
    items = [{"employee_id": "a", "person": "A", "segments": [(at(5, 13), at(5, 15))]}, {"employee_id": "b", "person": "B", "segments": [(at(5, 13), at(5, 14))]}]
    month = date(2026, 10, 1)
    assert life.labor_of(items, {month: {"a": 10000 / 3600, "b": 20000 / 3600}}, BOG) == {"status": "ok", "amount": 40000.0, "missing": []}
    assert life.labor_of(items, {month: {"a": 10000 / 3600}}, BOG)["missing"] == ["B"]


def test_former_names_sigue_la_cadena_y_no_repite():
    history = [{"old_key": "a", "new_key": "b", "old_name": "A", "new_name": "B", "created_at": at(1, 1)},
               {"old_key": "b", "new_key": "c", "old_name": "B", "new_name": "C", "created_at": at(2, 1)},
               {"old_key": "x", "new_key": "y", "old_name": "X", "new_name": "Y", "created_at": at(2, 2)}]
    assert life.former_names(history, "c", "C") == ["B", "A"]
    assert life.former_names(history, "y", "Y") == ["X"]


# ---------------------------------------------------------------- cotizaciones
def test_una_correccion_resta_de_lo_que_aun_no_se_ha_cobrado():
    base = [{"id": "1", "reference_id": "r", "reference_name": "Dreamy", "size": "S", "quantity": 28, "source_channel": "telegram"}]
    names = {"r": {"key": "dreamy", "name": "Dreamy"}}
    assert quotes_v2.group_closures(base, names, {})["lines"][0]["quantity"] == 28
    fixed = base + [{"id": "2", "reference_id": "r", "reference_name": "Dreamy", "size": "S", "quantity": -28, "source_channel": "correccion"}]
    assert quotes_v2.group_closures(fixed, names, {})["lines"] == [], "28 -> 0 ya no aparece por cobrar"
    other = base + [{"id": "3", "reference_id": "r", "reference_name": "Dreamy", "size": "S", "quantity": -5, "source_channel": "telegram"}]
    assert quotes_v2.group_closures(other, names, {})["lines"][0]["quantity"] == 28, "sin correccion, igual que siempre"
