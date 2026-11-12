"""Oficina 3D · Recepcion con Nexa: reglas puras (estados, orden, +N, etiquetas y privacidad).

- Cada estado: talking (Nexa respondiendo / activa en 10 min), new (recien llegado), waiting (espera N min),
  demo (agendada, fecha y hora), idle (sin respuesta / solo abrio la landing).
- Maximo 8 visibles y "+N"; sin interesados -> Nexa "Esperando visitas" y "Sin visitas hoy".
- Etiqueta "<tipo de negocio> · <zona> · <tema> · <canal>" sin telefono, correo ni nombre de la persona.
- Ningun dato de ejemplo de la referencia en el codigo.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.services import oficina_recepcion as rc

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)   # jueves 10:00 en Bogota


def m(minutes: float) -> datetime:
    return NOW - timedelta(minutes=minutes)


def wa(**kw):
    base = dict(first_at=m(120), last_at=m(60), last_dir="out", last_in=m(61), last_out=m(60), demo_at=None, stage="calificado", paused=False)
    base.update(kw)
    return rc.wa_state(NOW, **base)


def test_estados_de_whatsapp():
    assert wa(first_at=m(1), last_at=m(1), last_dir="in", last_in=m(1), last_out=None) == ("new", None), "recien llegado: entra caminando"
    assert wa(last_at=m(0.3), last_dir="in", last_in=m(0.3), last_out=m(5)) == ("talking", None), "Nexa respondiendo ahora"
    assert wa(last_at=m(4), last_dir="out", last_in=m(5), last_out=m(4)) == ("talking", None), "conversacion activa en 10 min"
    assert wa(last_at=m(7), last_dir="in", last_in=m(7), last_out=m(30)) == ("waiting", 7), "espera respuesta: N min"
    assert wa(last_at=m(0.5), last_dir="in", last_in=m(0.5), last_out=m(9), stage="pidio_persona") == ("waiting", 0), "pidio una persona: espera"
    assert wa(last_at=m(90), demo_at=NOW + timedelta(days=1), stage="demo_agendada") == ("demo", None)
    assert wa(last_at=m(90)) == ("idle", None), "Nexa respondio y la persona no ha vuelto: gris"


def test_estados_de_prospeccion_y_n8n():
    assert rc.prospect_state(NOW, replied_at=m(30), opened_at=m(60), demo_at=None, answered_at=None) == ("waiting", 30)
    assert rc.prospect_state(NOW, replied_at=m(30), opened_at=None, demo_at=None, answered_at=m(10)) == ("idle", None), "ya se le respondio"
    assert rc.prospect_state(NOW, replied_at=None, opened_at=m(20), demo_at=None, answered_at=None) == ("idle", None), "solo abrio la landing"
    assert rc.prospect_state(NOW, replied_at=m(30), opened_at=None, demo_at=NOW + timedelta(hours=3), answered_at=None)[0] == "demo"
    assert rc.n8n_state(NOW, {"at": m(1).isoformat(), "state": "nuevo"}) == ("new", None)
    assert rc.n8n_state(NOW, {"at": m(3).isoformat(), "state": "nuevo"}) == ("waiting", 3)
    assert rc.n8n_state(NOW, {"at": m(3).isoformat(), "state": "respondido"}) == ("idle", None)


def test_demo_con_dia_y_hora_de_bogota():
    assert rc.demo_label(datetime(2026, 11, 13, 15, 0, tzinfo=timezone.utc)) == "vie 10:00"
    assert rc.demo_label(None) is None


def test_temas_negocio_y_limpieza_sin_datos_personales():
    assert rc.topic_label(rc.topic_keys("Hola! cuánto cuesta? quiero una demo")) == "Precio y demo"
    assert rc.topic_label(rc.topic_keys("quiero la carta en video para el local")) == "Carta video"
    assert rc.topic_label(rc.topic_keys("hola")) == "Consulta"
    assert rc.business_label("Pizzería") == "Restaurante"
    assert rc.business_label("") == "Interesado"
    dirty = "Calle 3 #45-10 juan.perez@gmail.com +57 300 123 4567 @juanito"
    clean = rc.scrub(dirty, 60)
    for bad in ("@", "gmail", "300", "4567", "juanito"):
        assert bad not in clean, (bad, clean)


def v(i, state, minutes=1, **kw):
    return {"id": f"v{i}", "kind": "wa", "state": state, "wait_min": kw.get("wait"), "demo": kw.get("demo"), "business": kw.get("business", "Restaurante"),
            "zone": kw.get("zone"), "topic": kw.get("topic", "Precio"), "channel": "WhatsApp", "at": m(minutes).isoformat(), "link": None}


def test_orden_maximo_8_y_mas_n():
    vs = [v(i, s, minutes=i) for i, s in enumerate(["idle", "waiting", "talking", "demo", "new", "idle", "waiting", "talking", "idle", "idle", "waiting"])]
    out = rc.arrange(vs)
    assert out["interesados"] == 11 and out["plus"] == 3 and len(out["visitors"]) == 8 and len(out["screen"]) == 8
    order = [x["state"] for x in out["visitors"]]
    assert order == sorted(order, key=lambda s: rc.ORDER[s]), "hablando, nuevos, en espera, demos, sin respuesta"
    assert out["nexa"]["state"] == "talking" and out["nexa"]["text"].startswith("Atendiendo: ")


def test_sin_interesados_solo_nexa():
    out = rc.arrange([])
    assert out == {"visitors": [], "interesados": 0, "plus": 0, "screen": [], "nexa": {"state": "idle", "text": "Esperando visitas"}, "empty": True}


def test_etiqueta_y_colores_por_estado():
    t = rc.visitor_tag(v(1, "waiting", wait=3, business="Bar", zone="Chapinero", topic="Precio y demo"))
    assert t == {"head": "Bar · Chapinero", "small": "Precio y demo · WhatsApp · espera 3 min", "color": "#f59e0b"}
    assert rc.visitor_tag(v(2, "demo", demo="vie 10:00"))["small"].endswith("Demo agendada vie 10:00")
    assert rc.visitor_tag(v(2, "demo"))["color"] == "#a855f7"
    assert rc.visitor_tag(v(3, "idle"))["color"] == "#94a3b8"
    assert rc.visitor_tag(v(4, "talking"))["color"] == "#22c55e"
    rows = rc.screen_rows([v(5, "waiting", wait=4), v(6, "talking"), {**v(7, "idle"), "kind": "landing"}])
    assert [r["state"] for r in rows] == ["En espera · 4 min", "Nexa respondiendo", "Abrió la landing"]


def test_items_de_n8n_sin_usuario_ni_texto():
    n8n = {"ok": True, "reception": {"ok": True, "leads": [{"ref": "lead:x", "at": m(5).isoformat(), "channel": "instagram", "state": "nuevo", "topics": ["precio", "demo"],
                                                            "usuario": "@alguien", "texto": "mi numero 3001234567"}],
                                     "mail": [{"ref": "correo:y", "at": m(400).isoformat(), "channel": "correo", "state": "pendiente", "topics": ["carta_video"]},
                                              {"ref": "correo:z", "at": m(60 * 30).isoformat(), "channel": "correo", "state": "pendiente", "topics": []}]}}
    leads, mail = rc._n8n_items(NOW, n8n)
    assert [(x["channel"], x["topic"], x["state"], x["wait_min"]) for x in leads] == [("Instagram · DEMO", "Precio y demo", "waiting", 5)]
    assert [(x["channel"], x["topic"]) for x in mail] == [("Correo", "Carta video")], "solo las ultimas 24 h"
    assert "alguien" not in str(leads) and "3001234567" not in str(leads)
    assert rc._n8n_items(NOW, {"ok": False}) == (None, None), "n8n caido: sin datos (no se inventa)"


def test_codigo_sin_datos_de_ejemplo_de_la_referencia():
    samples = ("Kennedy", "Quiero la carta video", "Techo", "Castilla", "Timiza", "Panadería · Timiza", "Bar · Techo", "vie 10:00\"", "3 min'")
    for f in ("app/services/oficina_recepcion.py", "app/web/oficina/oficina_recepcion.js"):
        src = (ROOT / f).read_text(encoding="utf-8")
        for s in samples[:5]:
            assert s not in src, (f, s)
