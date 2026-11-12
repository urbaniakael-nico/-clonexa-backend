"""Oficina 3D · pisos aprobados (025m): reglas puras del servidor.

- Migracion 025m: id de 32 caracteres o menos; enciende SOLO Velvet, Asadero y VOLTAGE (+ el piso Clonexa).
- Interruptor: 'aprobado' solo con plantilla taller/restaurante/campo; otras empresas sin cambios.
- Editor: genero Hombre/Mujer, personaje de ese genero, tunica, barba (solo hombres).
- Copias vivas: lo que no existe queda en None ("—"), nunca un numero de ejemplo; Tesoreria sin montos.
- Typing.glb entra por la lista blanca del bucket privado; nunca al repo.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services import oficina as of
from app.services import oficina_bar as obar
from app.services import oficina_data as od
from app.services import oficina_pisos as opi
from app.services import oficina_vivo as ov

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 11, 18, 0, tzinfo=timezone.utc)


def test_migracion_025m_corta_y_solo_sus_empresas():
    src = (ROOT / "migrations/versions/025m_oficina_pisos.py").read_text(encoding="utf-8")
    rev = re.search(r'^revision = "([^"]+)"', src, re.M).group(1)
    assert len(rev) <= 32 and re.search(r'^down_revision = "025l_oficina_bar"', src, re.M)
    ids = set(re.findall(r'"([0-9a-f-]{36})"', src))
    assert ids == {"d63cf68c-be5b-4a30-aee4-341973018db1", "7625872c-f941-4479-a27b-f8443be953c5", "f1e8f774-f052-49ca-880a-268805f07db0"}
    assert "21a3065e" not in src, "The Time Machine no cambia"
    assert "'aprobado'" in src and "oficina_ajustes" in src and "ADD COLUMN IF NOT EXISTS" in src


def test_interruptor_aprobado_solo_en_plantillas_con_motor():
    for t in ("taller", "restaurante", "campo"):
        assert od.floor_style({"estilo": "aprobado"}, t) == "aprobado"
    assert od.floor_style({"estilo": "aprobado"}, "general") == "clasico"
    assert od.floor_style({"estilo": "aprobado"}, "bar") == "clasico", "el bar sigue con su motor"
    assert od.floor_style({}, "taller") == "clasico", "apagado por defecto"
    assert od.floor_style({"estilo": "bar"}, "bar") == "bar"
    assert "aprobado" in ov.STYLES_FLOOR


def test_editor_genero_personaje_tunica_y_barba():
    assert of.clean_character({"genero": "hombre", "personaje": "Ch42_nonPBR", "tunica": "si", "barba": "si", "color_barba": "#AA3300"}) == \
        {"genero": "hombre", "personaje": "Ch42_nonPBR", "tunica": "si", "barba": "si", "color_barba": "#aa3300"}
    assert of.clean_character({"genero": "mujer", "personaje": "Ch21_nonPBR"}) == {"genero": "mujer", "personaje": "Ch21_nonPBR"}
    assert of.clean_character({"genero": "", "personaje": ""}) == {"genero": "", "personaje": ""}, "vacío = automático"
    for bad in ({"genero": "otro"}, {"personaje": "Batman"}, {"genero": "mujer", "personaje": "Remy"}, {"genero": "mujer", "barba": "si"},
                {"tunica": "quizas"}, {"color_barba": "rojo"}):
        with pytest.raises(of.Rejected):
            of.clean_character(bad)
    assert of.MIXAMO_BY_GENDER["hombre"] == ("Remy", "Ch01_nonPBR", "Ch06_nonPBR", "Ch42_nonPBR", "Ch17_nonPBR")
    assert of.MIXAMO_BY_GENDER["mujer"] == ("Ch07_nonPBR", "Ch21_nonPBR", "Ch22_nonPBR")
    assert {"genero", "personaje", "tunica", "barba", "color_barba"} <= set(od.CHAR_COLS)


def test_velvet_tablero_sin_datos_es_raya_y_con_datos_real():
    assert opi.machines_for(2) == 6 and opi.machines_for(9) == 9 and opi.machines_for(40) == 12 and opi.machines_for(None) == 6
    assert opi.week_series(None, date(2026, 11, 11)) is None, "sin la tabla: sin datos, no ceros"
    wk = opi.week_series([{"day": date(2026, 11, 9), "n": 18}, {"day": date(2026, 11, 10), "n": 26}], date(2026, 11, 11))
    assert [d["n"] for d in wk] == [18, 26, 0, None, None, None, None], "días que no llegan: None"
    people = [{"status": "working"}, {"status": "working"}, {"status": "paused"}]
    empty = opi.taller_board(None, people, None, None, None)
    assert empty["lot"] is None and empty["made"] is None and empty["next_send"] is None and empty["hours"] is None
    assert empty["on_shift"] == 2 and empty["paused"] == 1
    full = opi.taller_board({"name": "REF 210", "meta": 80, "closed": 20, "days_open": 3}, people, "2:10 h", wk, {"status": "ok", "value": 5, "to_send": 7})
    assert (full["lot"], full["made"], full["meta"], full["percent"], full["day"], full["sent"], full["to_send"], full["week_sum"]) == ("REF 210", 20, 80, 25, 3, 5, 7, 44)
    assert opi.paused_minutes((NOW - timedelta(minutes=12)).isoformat(), NOW) == 12 and opi.paused_minutes(None, NOW) is None
    team = {"live": [{"employee_id": "e1", "name": "KRISS MARTINEZ", "role": "operario", "status": "working", "reference_name": "REF 210"},
                     {"employee_id": "e2", "name": "Laura Gómez", "role": "operaria", "status": "on_break", "paused_since": (NOW - timedelta(minutes=9)).isoformat()}]}
    out = opi.taller_people(team, "nombre", NOW)
    assert out[0]["label"] == "Kriss M. · Operario" and out[0]["first"] == "Kriss" and out[0]["reference"] == "REF 210"
    assert out[1]["status"] == "paused" and out[1]["paused_min"] == 9 and out[1]["reference"] is None
    assert opi.taller_people(team, "cargo", NOW)[0]["label"] == "Operario" and opi.taller_people(team, "cargo", NOW)[0]["first"] == "", "solo cargo: sin nombre"
    assert out[0]["key"] == of.staff_out([{"employee_id": "e1"}], "taller", "nombre")["visible"][0]["key"], "misma clave que el editor"


def test_asadero_domicilios_y_tiempos():
    assert opi.delivery_state("pendiente", {}) == "cocina" and opi.delivery_state("alistando", None) == "cocina"
    assert opi.delivery_state("entregado", {"delivery": {"dispatched_at": "2026-11-11T17:00:00Z"}}) == "camino"
    assert opi.delivery_state("alistando", {"delivery": {"dispatched_at": "2026-11-11T17:00:00Z"}}) == "camino"
    assert opi.delivery_state("entregado", {"delivery": {}}) == "listo"
    assert opi.delivery_state("cerrado", {"delivery": {"dispatched_at": "x"}}) == "entregado"
    assert opi.minutes_since((NOW - timedelta(minutes=6)).isoformat(), NOW) == 6 and opi.minutes_since(None, NOW) is None


def test_voltage_max_5_mas_n_fuera_de_perimetro_y_cargos():
    ops = [{"id": "va", "name": "Virginia", "timezone": "America/New_York"}, {"id": "al", "name": "Alabama", "timezone": "America/Chicago"}]
    shifts = [{"employee_id": f"e{i}", "employee_name": f"Tec {i}", "employee_role": "Técnico", "status": "working", "work_location_id": "al"} for i in range(7)]
    shifts += [{"employee_id": "sup", "employee_name": "Noel R", "employee_role": "Supervisor", "status": "working", "work_location_id": "al"},
               {"employee_id": "w", "employee_name": "Ana B", "employee_role": "Almacenista", "status": "on_break", "work_location_id": "va"}]
    outside = {opi.person_key("e3")}
    res = opi.campo_ops(ops, shifts, outside, {"al": (12, 2)}, {"al": {"kind": "entrada", "at": "06:30", "status": "enviado"}}, "nombre")
    al = next(o for o in res if o["id"] == "al"); va = next(o for o in res if o["id"] == "va")
    assert al["on"] == 8 and len(al["people"]) == 5 and al["extra"] == 3, "máximo 5 visibles + '+N'"
    assert al["people"][0]["role"] == "supervisor" and any(p["outside"] for p in al["people"]), "supervisor y fuera de perímetro siempre se ven"
    assert al["outside"] == 1 and (al["scheduled"], al["missing"]) == (12, 2)
    assert va["scheduled"] is None and va["missing"] is None and va["cut"] is None, "sin horario ni corte: —"
    assert va["people"][0]["role"] == "almacen" and va["people"][0]["paused"] is True
    assert opi.campo_role("Líder de operación") == "supervisor" and opi.campo_role("Bodega") == "almacen" and opi.campo_role("") == "tecnico"
    tz = od._zone("America/Chicago")
    assert opi.cut_out({"kind": "checkout", "at": "2026-11-11T23:00:00+00:00", "status": "sent"}, tz) == {"kind": "salida", "at": "17:00", "status": "enviado"}
    assert opi.cut_out({"kind": "checkin", "at": None, "status": "failed"}, tz)["status"] == "falló" and opi.cut_out(None, tz) is None


def test_clonexa_tesoreria_sin_montos_flujos_nuevos_y_salud():
    assert opi.treasury_state(None) == {"state": "sin_contrato", "text": "Sin contrato"}
    assert opi.treasury_state({"has_contract": True, "state": "al_dia"}) == {"state": "al_dia", "text": "Al día"}
    assert opi.treasury_state({"has_contract": True, "state": "en_ventana", "month": {"days_left": 3}})["text"] == "Vence en 3 días"
    assert opi.treasury_state({"has_contract": True, "state": "en_ventana", "month": {"days_left": 0}})["text"] == "Vence hoy"
    v = opi.treasury_state({"has_contract": True, "state": "en_mora", "days_late": 4, "overdue": [{"amount": 900000}]})
    assert v == {"state": "vencido", "text": "Vencido · 4 días"} and "900" not in str(v), "nunca montos"
    flows = [{"name": "Nexa - Plan B", "active": True}, {"name": "Oficina - Estado", "active": True},
             {"name": "Nexa - Reels nuevos", "active": True}, {"name": "VOLTAGE recordatorios", "active": True}, {"name": "Prospección Medellín", "active": True},
             {"name": "Viejo", "active": False}]
    extra = opi.extra_workers({"ok": True, "workflows": flows}, NOW)
    assert [(w["name"], w["area"]) for w in extra] == [("Nexa - Reels nuevos", "marketing"), ("VOLTAGE recordatorios", "bots"), ("Prospección Medellín", "ventas")]
    assert opi.extra_workers({"ok": False}, NOW) == []
    assert opi.health(NOW - timedelta(minutes=30), NOW) == "ok" and opi.health(NOW - timedelta(hours=30), NOW) == "warn"
    assert opi.health(NOW - timedelta(days=5), NOW) == "bad" and opi.health(None, NOW) == "nodata"
    cards = opi.company_cards([{"company_id": "x", "name": "Velvet", "template": "taller", "template_label": "Taller", "kpis": [["Personas en turno", "3"], ["Horas", "—"], ["Lote", "R"]],
                                "last_activity_at": None}], NOW)
    assert cards == [{"company_id": "x", "name": "Velvet", "template": "taller", "label": "Taller", "kpis": [["Personas en turno", "3"], ["Horas", "—"]], "health": "nodata"}]
    assert opi.prospect_map(None) is None and opi.prospect_map([]) == {"points": [], "zones": [], "count": 0}
    m = opi.prospect_map([{"lat": 4.6, "lng": -74.1, "status": "respondio", "zone": "Kennedy"}, {"lat": 4.7, "lng": -74.0, "status": "", "zone": "Kennedy"}])
    assert m["count"] == 2 and m["zones"] == ["Kennedy"] and m["points"][0][2] == "respondio"
    assert set(of.AGENT_AREA) == set(of.AGENT_IDS) and set(of.AGENT_AREA.values()) <= set(opi.AREAS)


def test_las_claves_de_la_copia_viva_pasan_el_filtro_de_dinero():
    snap = ov.without_money({"kitchen_count": 3, "on_shift": 4, "board": {"week_sum": 9, "sent": 2, "to_send": 1}, "total": 5, "precio": 1})
    assert snap == {"kitchen_count": 3, "on_shift": 4, "board": {"week_sum": 9, "sent": 2, "to_send": 1}}


def test_typing_por_la_lista_blanca_y_motores_registrados():
    from app.web import oficina_routes as routes

    assert obar.valid_name("animaciones/Typing.glb")
    for name, file in (("mixamo.js", "oficina_mixamo.js"), ("pisos_reglas.js", "oficina_pisos_rules.js"), ("clonexa.js", "oficina_clonexa.js"),
                       ("taller.js", "oficina_taller.js"), ("restaurante.js", "oficina_restaurante.js"), ("campo.js", "oficina_campo.js")):
        assert routes.ASSETS[name][0] == "oficina/" + file and (ROOT / "app/web" / routes.ASSETS[name][0]).exists()
    for js in ("oficina_mixamo.js", "oficina_clonexa.js", "oficina_taller.js", "oficina_restaurante.js", "oficina_campo.js"):
        body = (ROOT / "app/web/oficina" / js).read_text(encoding="utf-8")
        for imp in re.findall(r"^import .* from '([^']+)';$", body, re.M):
            assert imp == "three" or imp.startswith("/admin-v2plus/oficina/") or "examples/jsm/" + imp.removeprefix("three/addons/") in routes.THREE, (js, imp)
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "Typing" not in [p.stem for p in (ROOT / "app").rglob("*.glb")]
    assert gi, "el .gitignore sigue excluyendo Mixamo (ver test_oficina_bar)"
