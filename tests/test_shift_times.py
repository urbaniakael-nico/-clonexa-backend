"""Definicion unica de tiempos del turno (CRM VELVET-LAB, nomina y bot)."""
from datetime import datetime, timedelta, timezone

from app.services import shift_times

T0 = datetime(2026, 10, 26, 22, 0, tzinfo=timezone.utc)


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


def test_trabajado_es_conectado_menos_pausas_y_cruza_medianoche():
    breaks = [(at(30), at(45)), (at(90), at(110))]
    out = shift_times.shift_times(T0, breaks, end=at(240), now=at(300))
    assert out == {"connected_seconds": 240 * 60, "pause_seconds": 35 * 60, "worked_seconds": 205 * 60}
    assert at(240).date() != T0.date()


def test_pausa_abierta_cuenta_hasta_ahora():
    out = shift_times.shift_times(T0, [(at(10), at(20)), (at(50), None)], now=at(60))
    assert out == {"connected_seconds": 3600, "pause_seconds": 20 * 60, "worked_seconds": 40 * 60}


def test_trabajado_en_un_tramo_descuenta_solo_las_pausas_dentro():
    breaks = [(at(0), at(10)), (at(55), at(70))]
    assert shift_times.worked_seconds_between(at(5), at(60), breaks, now=at(100)) == (55 - 5 - 5) * 60
    assert shift_times.worked_seconds_between(at(60), at(60), breaks, now=at(100)) == 0


def test_minutos_para_la_nomina_siempre_cuadran():
    out = shift_times.shift_minutes(T0, at(630), 30 * 60 + 29)
    assert out == {"connected_minutes": 630, "pause_minutes": 30, "worked_minutes": 600}
    assert out["worked_minutes"] == out["connected_minutes"] - out["pause_minutes"]
    assert shift_times.shift_minutes(T0, at(10), 99999)["worked_minutes"] == 0
