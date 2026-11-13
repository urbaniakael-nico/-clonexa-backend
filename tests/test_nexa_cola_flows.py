"""n8n "Nexa - Cola asistida" mas liviano (sin red): solo 2 mensajes programados al dia (L-V 8:30 y 17:00), un
mensaje con "Abrir la cola" en vez de uno por negocio, y los callbacks viejos (pa:/pv:) siguen funcionando.
"Nexa - Prospeccion" no avisa por Telegram si hoy no busco. WhatsApp ventas ya no menciona el nombre del dueno.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "n8n"))

import nexa_prospeccion_flows as npf  # noqa: E402

CRED = {"httpHeaderAuth": {"id": "x", "name": "Nexa backend (X-Nexa-Token)"}}


def _flow():
    return npf.flow_cola(CRED, "secreto-de-prueba")


def test_solo_dos_mensajes_programados_al_dia():
    f = _flow()
    triggers = [n for n in f.nodes if "schedule" in n["type"].lower() or "cron" in n["type"].lower()]
    assert sorted(n["name"] for n in triggers) == ["L-V 17:00", "L-V 8:30"]
    text = str(triggers)
    assert "30 8 * * 1-5" in text and "0 17 * * 1-5" in text
    names = {n["name"] for n in f.nodes}
    assert "Telegram: negocio" not in names and "Uno por negocio" not in names, "ya no un mensaje por negocio"
    tg_scheduled = {n["name"] for n in f.nodes if n["type"] == "n8n-nodes-base.telegram"} & {"Telegram: cola de hoy", "Telegram: resumen"}
    assert tg_scheduled == {"Telegram: cola de hoy", "Telegram: resumen"}
    assert f.conns["L-V 8:30"]["main"][0][0]["node"] == "Cola de hoy"
    assert f.conns["L-V 17:00"]["main"][0][0]["node"] == "Resumen del día"


def test_mensaje_de_la_manana_con_boton_abrir_la_cola():
    f = _flow()
    node = next(n for n in f.nodes if n["name"] == "Telegram: cola de hoy")
    btn = node["parameters"]["inlineKeyboard"]["rows"][0]["row"]["buttons"][0]
    assert btn["text"] == "Abrir la cola ➜" and btn["additionalFields"] == {"url": "={{ $json.url }}"}
    be = next(n for n in f.nodes if n["name"] == "Cola de hoy")
    assert be["parameters"]["url"].endswith("/n8n/assisted/morning")
    assert next(n for n in f.nodes if n["name"] == "Resumen del día")["parameters"]["url"].endswith("/n8n/assisted/summary")


def test_callbacks_viejos_siguen_funcionando():
    f = _flow()
    names = {n["name"] for n in f.nodes}
    assert {"Botón de la cola", "¿Visita?", "Registrar visita", "Acción de la cola", "Resultado", "Editar mensaje", "Telegram: texto para copiar"} <= names
    accion = next(n for n in f.nodes if n["name"] == "Acción de la cola")
    assert accion["parameters"]["url"].endswith("/n8n/assisted/action")
    assert "Ruta (backend)" in names, "la ruta de visitas sigue"
    # el Bot de comandos sigue mandando pa:/pv: a este sub-flujo
    src = (ROOT / "ops" / "n8n" / "nexa_prospeccion_flows.py").read_text(encoding="utf-8")
    assert "(ns === 'pa' || ns === 'pv') ? 'asistida'" in src


def test_prospeccion_no_avisa_si_no_busco():
    f = npf.flow_prospeccion(CRED, "s")
    code = next(n for n in f.nodes if n["name"] == "Mensaje")["parameters"]["jsCode"]
    assert "if (r.sin_busqueda === true && !opts.prueba && !errs.length) return [];" in code


def test_whatsapp_ventas_sin_el_nombre_del_dueno():
    assert "Nicol" not in (ROOT / "ops" / "n8n" / "nexa_whatsapp_flow.py").read_text(encoding="utf-8")


def test_parche_de_whatsapp_reemplaza_solo_el_nombre():
    import nexa_cola_hoy_flows as ch
    src = (ROOT / "ops" / "n8n" / "nexa_whatsapp_flow.py").read_text(encoding="utf-8")
    old_like = {"nodes": [{"name": "Preparar", "parameters": {"jsCode": "sin_horarios: 'Estos días la agenda está llena. Nicolás, del equipo de Clonexa, te escribe para cuadrar la demo.', x: 'Nicolás from Clonexa will confirm the time shortly.'"}}],
                "connections": {"A": {"main": []}}}
    out = ch.patch_wa_names(old_like)
    code = out["nodes"][0]["parameters"]["jsCode"]
    assert "Nicol" not in code and "Alguien del equipo de Clonexa te escribe para cuadrar la demo." in code
    assert "Someone from the Clonexa team will confirm the time shortly." in code and out["connections"] == old_like["connections"]
    assert all(new in src for _, new in ch.WA_REPLACE), "la fuente ya tiene el texto nuevo"
