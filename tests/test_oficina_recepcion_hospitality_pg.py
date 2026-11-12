"""Oficina 3D · Recepcion con Nexa contra Postgres REAL (pgserver) y la app completa, con datos SIMULADOS.

- 401 sin sesion: copia viva de la recepcion, su motor, los gestos y la pagina.
- 409 sin el interruptor (oficina_ajustes.piso_recepcion); la migracion 025n lo enciende y es idempotente.
- Cada estado sale de los datos reales: WhatsApp nuevo / activo / esperando / demo / sin respuesta; prospecto que
  respondio o solo abrio la landing; Leads DEMO y correos desde n8n; 9+ interesados -> 8 visibles y "+N".
- Sin interesados: solo Nexa "Esperando visitas" y "Sin visitas hoy".
- PRIVACIDAD: ni telefono, ni correo, ni nombre de la persona, ni el texto de sus mensajes en la respuesta.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("pgserver")

from tests.test_oficina_hospitality_pg import (  # noqa: E402,F401
    API, N8N_OK, _migration, _run, _session, client, pg_url,
)
from app.web import oficina_routes  # noqa: E402

PHONE, EMAIL, PERSON = "573001234567", "maria.lopez@gmail.com", "María López"
SECRET_TEXT = "mi cédula es 1012345678"


@pytest.fixture
def rdb(pg_url, client):
    # el esquema base de la oficina trae una wa_contacts minima: aqui va la real de la migracion 024w
    if not _run(pg_url, "SELECT 1 FROM information_schema.columns WHERE table_name = 'wa_contacts' AND column_name = 'business_type'"):
        _run(pg_url, "DROP TABLE IF EXISTS wa_messages")
        _run(pg_url, "DROP TABLE IF EXISTS wa_contacts CASCADE")
    for name in ("024w_nexa_whatsapp", "025i_prospecting", "025n_oficina_recepcion", "025n_oficina_recepcion"):
        for stmt in _migration(name):
            _run(pg_url, stmt)
    for t in ("wa_messages", "wa_contacts", "prospect_contacts", "prospects"):
        _run(pg_url, f"DELETE FROM {t}")
    _run(pg_url, "INSERT INTO oficina_ajustes (clave, valor) VALUES ('piso_recepcion', 'aprobado') ON CONFLICT (clave) DO UPDATE SET valor = 'aprobado'")
    return pg_url


def _wa(db, n, *, first, last, msgs, stage="calificado", business="restaurante", city="Suba", demo_at=None, pain="", paused=False):
    now = datetime.now(timezone.utc)
    cid = _run(db, """INSERT INTO wa_contacts (wa_id, profile_name, business_type, city, main_pain, email, stage, nexa_paused, first_message_at,
                        last_message_at, last_inbound_at, last_preview, demo_at)
                      VALUES (:w, :p, :b, :c, :pain, :e, :s, :np, :f, :l, :li, :prev, :d) RETURNING id::text""",
               {"w": f"{PHONE}{n}", "p": PERSON, "b": business, "c": city, "pain": pain, "e": EMAIL, "s": stage, "np": paused,
                "f": now - timedelta(minutes=first), "l": now - timedelta(minutes=last),
                "li": now - timedelta(minutes=min(m for d, m, _ in msgs if d == "in")) if any(d == "in" for d, _, _ in msgs) else None,
                "prev": SECRET_TEXT, "d": demo_at})[0]["id"]
    for d, minutes, body in msgs:
        _run(db, "INSERT INTO wa_messages (contact_id, direction, body, created_at) VALUES (CAST(:c AS uuid), :d, :b, :t)",
             {"c": cid, "d": d, "b": body, "t": now - timedelta(minutes=minutes)})
    return cid


def _prospect(db, n, *, replied=None, opened=None, demo=None, test=False):
    now = datetime.now(timezone.utc)
    ago = lambda m: None if m is None else now - timedelta(minutes=m)  # noqa: E731
    return _run(db, """INSERT INTO prospects (place_id, code, unsub_token, name, business_type, neighborhood, phone, email, is_test, replied_at, opened_at, demo_at)
                       VALUES (:pl, :code, :tok, :name, 'panaderia', 'Fontibón', :ph, :em, :t, :r, :o, :d) RETURNING id::text""",
                {"pl": f"place-{n}", "code": f"C{n:04d}", "tok": f"tok-{n}" + "x" * 20, "name": f"Panes del Barrio {n}", "ph": f"+57 601 555 00{n:02d}",
                 "em": f"ventas{n}@panes.co", "t": test, "r": ago(replied), "o": ago(opened), "d": demo})[0]["id"]


def _vivo(client):
    oficina_routes.reset_cache()
    r = client.get(f"{API}/recepcion/vivo")
    assert r.status_code == 200, r.text
    return r.json()


def _private(snap):
    blob = json.dumps(snap, ensure_ascii=False)
    for bad in (PHONE, EMAIL, PERSON, "María", "López", SECRET_TEXT, "1012345678", "@gmail", "601 555", "@panes.co", "ventas1@"):
        assert bad not in blob, bad


def test_recepcion_401_sin_sesion(client, monkeypatch):
    _session(monkeypatch, False)
    for url in (f"{API}/recepcion/vivo", "/admin-v2plus/oficina/recepcion.js", "/admin-v2plus/oficina/gestos.js"):
        r = client.get(url)
        assert r.status_code == 401, (url, r.status_code)
        assert b"Nexa" not in r.content
    page = client.get("/admin-v2plus/oficina", follow_redirects=False)
    assert page.status_code == 303


def test_sin_interruptor_409_y_estado_lo_anuncia(client, rdb, monkeypatch):
    _session(monkeypatch)
    _run(rdb, "DELETE FROM oficina_ajustes WHERE clave = 'piso_recepcion'")
    oficina_routes.reset_cache()
    assert client.get(f"{API}/recepcion/vivo").status_code == 409
    oficina_routes.reset_db_cache()
    assert client.get(f"{API}/estado").json()["reception_style"] == "clasico"
    _run(rdb, "INSERT INTO oficina_ajustes (clave, valor) VALUES ('piso_recepcion', 'aprobado')")
    oficina_routes.reset_db_cache()
    assert client.get(f"{API}/estado").json()["reception_style"] == "aprobado"


def test_sin_interesados_solo_nexa(client, rdb, monkeypatch):
    _session(monkeypatch)
    client.state["n8n"] = {**N8N_OK, "reception": {"ok": True, "leads": [], "mail": []}}
    snap = _vivo(client)
    assert snap["visitors"] == [] and snap["empty"] is True and snap["interesados"] == 0 and snap["plus"] == 0
    assert snap["nexa"] == {"state": "idle", "text": "Esperando visitas"}
    assert snap["sources"] == {"whatsapp": 0, "prospeccion": 0, "leads_demo": 0, "correos": 0, "demos": 0}


def test_cada_estado_con_datos_reales_simulados_y_privacidad(client, rdb, monkeypatch):
    _session(monkeypatch)
    now = datetime.now(timezone.utc)
    new = _wa(rdb, 1, first=1, last=1, msgs=[("in", 1, "hola, cuánto vale la carta en video?")])
    talking = _wa(rdb, 2, first=40, last=3, msgs=[("in", 4, "me interesa la nómina"), ("out", 3, "claro")], business="taller de confección", city="Kennedy")
    waiting = _wa(rdb, 3, first=50, last=7, msgs=[("out", 20, "hola"), ("in", 7, "precio y demo por favor")], business="bar", city="Chapinero", paused=True, stage="pidio_persona")
    demo = _wa(rdb, 4, first=300, last=200, msgs=[("in", 210, "demo"), ("out", 200, "listo")], stage="demo_agendada", demo_at=now + timedelta(days=1))
    idle = _wa(rdb, 5, first=600, last=500, msgs=[("in", 510, "info"), ("out", 500, "te cuento")])
    _wa(rdb, 6, first=60 * 30, last=60 * 30, msgs=[("in", 60 * 30, "viejo")])                      # de ayer: no sale
    _wa(rdb, 7, first=30, last=5, msgs=[("in", 5, "no gracias")], stage="no_interesado")          # no interesado: no sale
    replied = _prospect(rdb, 1, replied=45, opened=90)
    landing = _prospect(rdb, 2, opened=15)
    _prospect(rdb, 3, opened=10, test=True)                                                        # de prueba: no sale
    client.state["n8n"] = {**N8N_OK, "reception": {"ok": True,
        "leads": [{"ref": "lead:a", "at": (now - timedelta(minutes=12)).isoformat(), "channel": "instagram", "state": "nuevo", "topics": ["precio", "demo"]}],
        "mail": [{"ref": "correo:b", "at": (now - timedelta(hours=25)).isoformat(), "channel": "correo", "state": "pendiente", "topics": ["carta_video"]}]}}
    snap = _vivo(client)
    _private(snap)
    by = {v["link"]["id"] if v.get("link") else v["channel"]: v for v in snap["visitors"]}
    assert by[new]["state"] == "new" and by[new]["topic"] == "Carta video y precio" and by[new]["channel"] == "WhatsApp"
    assert by[talking]["state"] == "talking" and by[talking]["business"] == "Taller" and by[talking]["zone"] == "Kennedy"
    assert by[waiting]["state"] == "waiting" and 6 <= by[waiting]["wait_min"] <= 8 and by[waiting]["tag"]["color"] == "#f59e0b"
    assert by[waiting]["tag"]["head"] == "Bar · Chapinero" and "espera" in by[waiting]["tag"]["small"]
    assert by[demo]["state"] == "demo" and by[demo]["demo"] and by[demo]["tag"]["color"] == "#a855f7"
    assert by[idle]["state"] == "idle" and by[idle]["tag"]["color"] == "#94a3b8"
    assert by[replied]["state"] == "waiting" and by[replied]["channel"] == "Correo · prospección" and by[replied]["business"].startswith("Panadería Panes del Barrio")
    assert by[landing]["state"] == "idle" and by[landing]["topic"] == "Abrió la landing" and by[landing]["link"] == {"type": "mapa", "id": landing}
    assert by["Instagram · DEMO"]["state"] == "waiting" and by["Instagram · DEMO"]["topic"] == "Precio y demo" and by["Instagram · DEMO"]["link"] is None
    assert snap["interesados"] == 8 and snap["plus"] == 0 and len(snap["screen"]) == 8
    assert by[new]["link"] == {"type": "nexa", "id": new}, "tocar abre la conversación en Conversaciones Nexa"
    assert snap["nexa"]["state"] == "talking" and snap["nexa"]["text"].startswith("Atendiendo: ")
    assert snap["sources"] == {"whatsapp": 5, "prospeccion": 2, "leads_demo": 1, "correos": 0, "demos": 1}, "el correo de hace 25 h ya no es de hoy"
    order = [v["state"] for v in snap["visitors"]]
    assert order[:2] == ["talking", "new"]
    # misma rev -> {"same": true}
    r = client.get(f"{API}/recepcion/vivo?rev={snap['rev']}")
    assert r.json() == {"ok": True, "same": True, "rev": snap["rev"]}


def test_mas_de_8_muestra_mas_n(client, rdb, monkeypatch):
    _session(monkeypatch)
    for i in range(11):
        _wa(rdb, 20 + i, first=100 + i, last=60 + i, msgs=[("in", 61 + i, "info"), ("out", 60 + i, "ok")])
    client.state["n8n"] = {**N8N_OK, "reception": {"ok": True, "leads": [], "mail": []}}
    snap = _vivo(client)
    assert snap["interesados"] == 11 and len(snap["visitors"]) == 8 and snap["plus"] == 3
    _private(snap)


def test_n8n_caido_las_fuentes_de_la_base_siguen(client, rdb, monkeypatch):
    _session(monkeypatch)
    _wa(rdb, 40, first=20, last=2, msgs=[("in", 3, "hola"), ("out", 2, "hola!")])
    client.state["n8n"] = None
    snap = _vivo(client)
    assert snap["sources"]["leads_demo"] is None and snap["sources"]["correos"] is None, "n8n caído: sin datos (no se inventa)"
    assert snap["sources"]["whatsapp"] == 1 and snap["visitors"][0]["state"] == "talking"
