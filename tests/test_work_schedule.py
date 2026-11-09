"""Horario de la semana (interruptor work_schedule, 071A): reglas puras, sin base de datos.

Horario 1 y 2, dia puntual distinto, ET / CT, turno de noche, entrada despues de la salida,
textos del bot en el idioma de la persona, motivo obligatorio del cierre, hora por defecto,
rutas del panel del lider y el interruptor registrado. El almuerzo nunca se descuenta: solo las
pausas marcadas (us_time no cambia)."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services import lider_operacion, us_time
from app.services import work_schedule as ws

ROOT = Path(__file__).resolve().parents[1]
WEEK = date(2026, 11, 9)  # lunes
UTC = timezone.utc


def _slots():
    return ws.clean_slots([
        {"days": [0, 1, 2, 3, 4], "start": "07:00", "end": "17:00", "lunch_start": "12:00", "lunch_end": "13:00",
         "overrides": {"2026-11-13": {"start": "07:00", "end": "13:00"}, "2026-11-11": {"off": True}, "2026-11-20": {"off": True}}},
        {"days": [1, 2, 3, 4, 5], "start": "09:00", "end": "19:00"},
    ], WEEK)


def test_semana_empieza_el_lunes():
    assert ws.week_start(date(2026, 11, 15)) == WEEK  # domingo -> lunes anterior
    assert ws.week_start(date(2026, 11, 9)) == WEEK
    assert ws.parse_week("2026-11-12", date(2026, 1, 1)) == WEEK
    with pytest.raises(ws.Invalid):
        ws.parse_week("mañana", date(2026, 1, 1))


def test_horario_1_y_2_con_dia_puntual_de_esa_semana_solamente():
    slots = _slots()
    assert [s["name"] for s in slots] == ["Horario 1", "Horario 2"]
    assert set(slots[0]["overrides"]) == {"2026-11-13", "2026-11-11"}, "un dia de otra semana se descarta"
    one, two = slots
    assert ws.day_plan(one, date(2026, 11, 10))["end"] == "17:00"
    assert ws.day_plan(one, date(2026, 11, 13)) == {"start": "07:00", "end": "13:00", "special": True}, "viernes distinto"
    assert ws.day_plan(one, date(2026, 11, 11)) is None, "miercoles libre esa semana"
    assert ws.day_plan(one, date(2026, 11, 14)) is None, "sabado no trabaja"
    assert ws.day_plan(two, date(2026, 11, 14))["start"] == "09:00", "Horario 2 si trabaja el sabado"
    assert ws.day_plan(two, date(2026, 11, 9)) is None
    assert ws.slot_of(slots, 2) is two and ws.slot_of(slots, 9) is one and ws.slot_of(slots, None) is one
    days = ws.week_days(one, WEEK)
    assert [d["label"] for d in days][:5] == ["7:00 a. m. – 5:00 p. m.", "7:00 a. m. – 5:00 p. m.", "Libre", "7:00 a. m. – 5:00 p. m.", "7:00 a. m. – 1:00 p. m."]
    assert days[4]["special"] and days[2]["special"] and not days[0]["special"]


@pytest.mark.parametrize("raw,field", [
    ([], "slots"),
    ([{"days": [], "start": "07:00", "end": "17:00"}], "slots"),
    ([{"days": [0], "start": "7", "end": "17:00"}], "slots"),
    ([{"days": [0], "start": "07:00", "end": "07:00"}], "slots"),
    ([{"days": [0], "start": "07:00", "end": "17:00", "lunch_start": "12:00"}], "slots"),
    ([{"days": [0], "start": "07:00", "end": "17:00", "lunch_start": "13:00", "lunch_end": "12:00"}], "slots"),
    ([{"days": [9], "start": "07:00", "end": "17:00"}], "slots"),
    ([{"days": [0], "start": "07:00", "end": "17:00"}] * 7, "slots"),
])
def test_horario_invalido(raw, field):
    with pytest.raises(ws.Invalid) as exc:
        ws.clean_slots(raw, WEEK)
    assert exc.value.field == field


def test_salida_programada_en_la_hora_local_et_y_ct():
    one = _slots()[0]
    # lunes 10 nov 2026: EST = UTC-5, CST = UTC-6
    va_in = datetime(2026, 11, 10, 12, 2, tzinfo=UTC)  # 7:02 a. m. ET
    al_in = datetime(2026, 11, 10, 13, 0, tzinfo=UTC)  # 7:00 a. m. CT
    assert ws.scheduled_end(one, va_in, "America/New_York") == datetime(2026, 11, 10, 22, 0, tzinfo=UTC)
    assert ws.scheduled_end(one, al_in, "America/Chicago") == datetime(2026, 11, 10, 23, 0, tzinfo=UTC)
    assert ws.scheduled_end(one, datetime(2026, 11, 13, 12, 0, tzinfo=UTC), "America/New_York") == datetime(2026, 11, 13, 18, 0, tzinfo=UTC), "dia puntual 1 p. m."
    assert ws.scheduled_end(one, datetime(2026, 11, 11, 12, 0, tzinfo=UTC), "America/New_York") is None, "dia libre: no pregunta"
    assert ws.scheduled_end(one, datetime(2026, 11, 10, 23, 30, tzinfo=UTC), "America/New_York") is None, "entro despues de su salida"
    night = {"days": [0, 1, 2, 3, 4], "start": "22:00", "end": "06:00", "overrides": {}}
    assert ws.scheduled_end(night, datetime(2026, 11, 10, 3, 0, tzinfo=UTC), "America/New_York") == datetime(2026, 11, 10, 11, 0, tzinfo=UTC), "sale al otro dia"


def test_horas_y_textos_del_bot_en_cada_idioma():
    assert ws.clock_label("17:00") == "5:00 p. m." and ws.clock_label("07:05") == "7:05 a. m." and ws.clock_label("12:00") == "12:00 p. m."
    assert ws.clock_label("17:00", "en") == "5:00 PM" and ws.clock_label("00:30", "en") == "12:30 AM"
    assert ws.clock_label("17:00", "fr") == "17 h 00"
    assert ws.local_clock(datetime(2026, 11, 10, 22, 0, tzinfo=UTC), "America/New_York") == "5:00 p. m."
    assert ws.local_clock(datetime(2026, 11, 10, 23, 0, tzinfo=UTC), "America/Chicago", "en") == "5:00 PM"
    assert ws.tr("es", "ask", time="5:00 p. m.") == "⏰ Tu turno terminó a las 5:00 p. m. ¿Ya saliste?"
    assert ws.tr("es", "closed", time="5:00 p. m.", name="Ana") == "Tu turno fue cerrado a las 5:00 p. m. por Ana."
    assert "Your shift ended at 5:00 PM" in ws.tr("en", "ask", time="5:00 PM")
    assert ws.tr("xx", "btn_finish") == "Finalizar ahora", "idioma desconocido: español"
    for lang in ("es", "en", "fr"):
        kb = ws.prompt_keyboard(lang)["inline_keyboard"][0]
        assert [b["callback_data"] for b in kb] == [ws.CALLBACK_FINISH, ws.CALLBACK_WORKING]
        assert set(ws.TEXTS[lang]) == set(ws.TEXTS["es"])
    assert ws.prompt_keyboard("es")["inline_keyboard"][0][1]["text"] == "Sigo trabajando"


def test_motivo_obligatorio_y_hora_por_defecto():
    assert ws.close_reason({"reason_code": "olvido"}) == ("olvido", "", "Olvidó finalizar")
    assert ws.close_reason({"reason_code": "salida_real", "reason_detail": " lo  vio el supervisor "})[2] == "Salida real confirmada · lo vio el supervisor"
    assert ws.close_reason({"reason_code": "otro", "reason_detail": "se fue enfermo"})[2] == "Otro: se fue enfermo"
    for body in ({}, {"reason_code": "x"}, {"reason_code": "otro", "reason_detail": "no"}):
        with pytest.raises(ws.Invalid):
            ws.close_reason(body)
    now = datetime(2026, 11, 10, 23, 0, tzinfo=UTC)
    end = datetime(2026, 11, 10, 22, 0, tzinfo=UTC)
    assert ws.default_end(end, now) == end, "ya paso: la salida programada"
    assert ws.default_end(end + timedelta(hours=2), now) == now, "aun no llega: la hora actual"
    assert ws.default_end(None, now) == now


def test_solo_cuentan_las_pausas_marcadas_nunca_el_almuerzo():
    start = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
    end = start + timedelta(hours=10)
    no_break = us_time.compute([{"employee_id": "e", "start": start, "end": end, "breaks": [], "tz": "America/New_York"}])[0]["split"]
    assert (no_break["connected"], no_break["pause"], no_break["payable"]) == (600, 0, 600), "sin pausa marcada no se descuenta almuerzo"
    marked = us_time.compute([{"employee_id": "e", "start": start, "end": end, "tz": "America/New_York",
                               "breaks": [(start + timedelta(hours=6, minutes=10), start + timedelta(hours=6, minutes=40))]}])[0]["split"]
    assert (marked["pause"], marked["payable"]) == (30, 570), "solo la pausa marcada, a cualquier hora"
    src = (ROOT / "app/services/work_schedule.py").read_text(encoding="utf-8")
    assert "lunch" not in (ROOT / "app/services/us_time.py").read_text(encoding="utf-8")
    assert "breaks" not in src, "el horario nunca toca las pausas"


def test_rutas_del_lider_lectura_horario_y_escritura_cerrar():
    base = "/api/v1/lider-operacion/companies/c1"
    assert lider_operacion.request_allowed("GET", f"{base}/horario")
    assert lider_operacion.request_allowed("POST", f"{base}/crm/e1/cerrar")
    assert not lider_operacion.request_allowed("PUT", f"{base}/horario"), "el lider no edita el horario"
    assert not lider_operacion.request_allowed("GET", "/api/v1/work-schedule/companies/c1/locations/l1"), "ni las rutas del portal"
    assert not lider_operacion.request_allowed("POST", f"{base}/crm/e1/cerrar/otra")


def test_interruptor_registrado_y_migracion_corta():
    registry = json.loads((ROOT / "app/services/switch_registry.json").read_text(encoding="utf-8"))
    entry = next(s for s in registry["switches"] if s["key"] == "work_schedule")
    assert entry["module"] == "workforce" and entry["delicate"] is True
    assert {d["key"] for d in entry["depends_on"]} == {"work_locations", "open_shift_alert"}
    migration = (ROOT / "migrations/versions/025e_work_schedule.py").read_text(encoding="utf-8")
    assert 'revision = "025e_work_schedule"' in migration and len("025e_work_schedule") <= 32
    assert 'down_revision = "025d_ref_lifecycle"' in migration
    assert "IF NOT EXISTS" in migration and "DROP TABLE" not in migration.split("def downgrade")[0], "aditiva"
