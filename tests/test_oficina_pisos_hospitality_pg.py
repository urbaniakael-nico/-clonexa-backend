"""Oficina 3D · pisos aprobados contra Postgres REAL (pgserver) y la app completa, con datos simulados.

- 401 sin sesion: copia viva de Clonexa y de los pisos, motores nuevos y Typing.glb del bucket privado.
- Velvet: abrir turno -> aparece cosiendo con su referencia; pausa -> cafe con minutos; cerrar -> se va.
- Asadero: mesa con QR activo/libre, comandas en cocina con su tiempo, domicilio en camino con barrio, sin dinero.
- VOLTAGE: maximo 5 por operacion + '+N', fuera de perimetro por el GPS real, sin horario guardado -> None.
- Clonexa: agentes con su area, flujo nuevo de n8n y bot de Telegram como trabajadores nuevos, empresas de hoy,
  tesoreria sin datos (sin la tabla) y nunca montos.
- Editor: genero Hombre/Mujer guarda y recarga; una empresa sin el interruptor no tiene copia viva (409).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("pgserver")

from tests.test_oficina_hospitality_pg import (  # noqa: E402,F401
    API, ASADERO, NUEVA, TTM, VELVET, VOLTAGE, N8N_OK, _employee, _no_money, _open, _qr_tables, _run, _seed, _session, client, flow, pg_url,
)
from tests.test_oficina_hospitality_pg import _upload_bar  # noqa: E402
from app.web import oficina_routes  # noqa: E402

EXTRA = """
CREATE TABLE IF NOT EXISTS reference_work_sessions (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id text NOT NULL, employee_id text NOT NULL,
  reference_id text, reference_name text, started_at timestamptz DEFAULT now(), ended_at timestamptz, status text DEFAULT 'active');
CREATE TABLE IF NOT EXISTS employee_crm_pins (company_id uuid NOT NULL, employee_id uuid NOT NULL);
CREATE TABLE IF NOT EXISTS company_bot_instances (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, channel varchar(40) NOT NULL DEFAULT 'telegram',
  name varchar(180), bot_username varchar(180), bot_token_encrypted text, status varchar(40) NOT NULL DEFAULT 'configured', last_error text);
ALTER TABLE hospitality_orders ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb
"""


@pytest.fixture
def db(pg_url, client):
    for stmt in [s for s in EXTRA.split(";") if s.strip()]:
        _run(pg_url, stmt)
    for t in ("reference_work_sessions", "employee_crm_pins", "company_bot_instances"):
        _run(pg_url, f"DELETE FROM {t}")
    _seed(pg_url)
    for cid in (VELVET, ASADERO, VOLTAGE):
        _run(pg_url, "INSERT INTO oficina_pisos (company_id, estilo) VALUES (CAST(:c AS uuid), 'aprobado') ON CONFLICT (company_id) DO UPDATE SET estilo = 'aprobado'", {"c": cid})
    _run(pg_url, "INSERT INTO oficina_ajustes (clave, valor) VALUES ('piso_clonexa', 'aprobado') ON CONFLICT (clave) DO UPDATE SET valor = 'aprobado'")
    return pg_url


def _vivo(client, cid):
    oficina_routes.reset_cache()
    r = client.get(f"{API}/pisos/{cid}/vivo")
    assert r.status_code == 200, r.text
    snap = r.json()
    _no_money(snap)
    return snap


def test_pisos_aprobados_401_sin_sesion(client, monkeypatch):
    _upload_bar(client.bucket)
    _session(monkeypatch, False)
    for url in (f"{API}/clonexa/vivo", f"{API}/pisos/{VELVET}/vivo", f"{API}/pisos/{ASADERO}/vivo", f"{API}/pisos/{VOLTAGE}/vivo",
                "/admin-v2plus/oficina/mixamo.js", "/admin-v2plus/oficina/pisos_reglas.js", "/admin-v2plus/oficina/clonexa.js", "/admin-v2plus/oficina/taller.js",
                "/admin-v2plus/oficina/restaurante.js", "/admin-v2plus/oficina/campo.js", "/admin-v2plus/oficina/bar/animaciones/Typing.glb"):
        r = client.get(url)
        assert r.status_code == 401, (url, r.status_code)
        assert b"glTF" not in r.content


def test_velvet_turno_pausa_y_cierre(client, db, monkeypatch):
    _session(monkeypatch)
    now = datetime.now(timezone.utc)
    kriss = _employee(db, VELVET, "KRISS MARTINEZ", "operario")
    laura = _employee(db, VELVET, "Laura Gómez", "operaria")
    snap = _vivo(client, VELVET)
    assert snap["template"] == "taller" and snap["style"] == "aprobado" and snap["people"] == [] and snap["machines"] == 6
    assert snap["board"]["lot"] is None and snap["board"]["week"] is None, "sin producción en la base: —"
    _open(db, VELVET, kriss, now - timedelta(hours=2))
    _run(db, "INSERT INTO reference_work_sessions (company_id, employee_id, reference_id, reference_name, started_at) VALUES (:c, :e, 'r1', 'REF 210', :t)",
         {"c": VELVET, "e": kriss, "t": now - timedelta(minutes=50)})
    snap = _vivo(client, VELVET)
    assert [(p["label"], p["status"], p["reference"], p["first"]) for p in snap["people"]] == [("Kriss M. · Operario", "working", "REF 210", "Kriss")]
    _open(db, VELVET, laura, now - timedelta(hours=1), status="on_break")
    _run(db, "INSERT INTO workforce_attendance_events (company_id, employee_id, event_type, occurred_at) VALUES (CAST(:c AS uuid), CAST(:e AS uuid), 'break_start', :t)",
         {"c": VELVET, "e": laura, "t": now - timedelta(minutes=10)})
    snap = _vivo(client, VELVET)
    paused = next(p for p in snap["people"] if p["status"] == "paused")
    assert paused["label"] == "Laura G. · Operaria" and 9 <= paused["paused_min"] <= 11 and paused["reference"] is None
    assert snap["board"]["on_shift"] == 1 and snap["board"]["paused"] == 1
    _run(db, "UPDATE workforce_attendance_status SET status = 'off' WHERE employee_id = CAST(:e AS uuid)", {"e": kriss})
    snap = _vivo(client, VELVET)
    assert [p["status"] for p in snap["people"]] == ["paused"], "cierra turno -> se va"


def test_asadero_mesas_cocina_y_domicilios(client, db, monkeypatch):
    _session(monkeypatch)
    now = datetime.now(timezone.utc)
    _qr_tables(db, ASADERO, 6)
    _run(db, "INSERT INTO hospitality_table_access (company_id, table_key, table_number, status, activated_at) VALUES (CAST(:c AS uuid), 'mesa-1', 'Mesa 1', 'active', :t)",
         {"c": ASADERO, "t": now - timedelta(minutes=20)})
    _run(db, """INSERT INTO hospitality_orders (company_id, table_key, table_number, status, items, total, created_at)
                VALUES (CAST(:c AS uuid), 'mesa-2', 'Mesa 2', 'alistando', CAST(:i AS jsonb), 52000, :t)""",
         {"c": ASADERO, "i": json.dumps([{"name": "Churrasco", "quantity": 2, "unit_price": 26000}]), "t": now - timedelta(minutes=6)})
    _run(db, """INSERT INTO hospitality_orders (company_id, table_key, table_number, order_type, status, items, total, metadata, created_at)
                VALUES (CAST(:c AS uuid), 'dom', 'Domicilio 3F2A', 'domicilio', 'entregado', '[]'::jsonb, 30000, CAST(:m AS jsonb), :t)""",
         {"c": ASADERO, "m": json.dumps({"delivery": {"barrio": "Kennedy", "customer_name": "Cliente Secreto", "customer_phone": "3001234567", "dispatched_at": now.isoformat()}}),
          "t": now - timedelta(minutes=30)})
    snap = _vivo(client, ASADERO)
    tables = {t["label"]: t for t in snap["tables"]}
    assert tables["Mesa 1"]["open"] is True and tables["Mesa 3"]["open"] is False
    assert tables["Mesa 2"]["open"] is True and tables["Mesa 2"]["plates"] == 1, "pedido abierto: platos en la mesa"
    assert snap["kitchen"][0]["label"] == "Mesa 2" and snap["kitchen"][0]["detail"] == "2 productos" and 5 <= snap["kitchen"][0]["minutes"] <= 7
    assert snap["deliveries"][0]["state"] == "camino" and snap["deliveries"][0]["barrio"] == "Kennedy" and snap["on_the_way"]
    body = json.dumps(snap)
    assert "Cliente Secreto" not in body and "3001234567" not in body and "52000" not in body and "30000" not in body, "sin datos del cliente ni dinero"


def test_voltage_mas_n_y_fuera_de_perimetro(client, db, monkeypatch):
    _session(monkeypatch)
    now = datetime.now(timezone.utc)
    al = _run(db, "INSERT INTO work_locations (company_id, name, timezone) VALUES (CAST(:c AS uuid), 'Alabama', 'America/Chicago') RETURNING id::text", {"c": VOLTAGE})[0]["id"]
    _run(db, "INSERT INTO work_locations (company_id, name, timezone) VALUES (CAST(:c AS uuid), 'Virginia', 'America/New_York')", {"c": VOLTAGE})
    ids = [_employee(db, VOLTAGE, f"Tecnico {i}", "Técnico", al) for i in range(6)] + [_employee(db, VOLTAGE, "Noel Ramos", "Supervisor", al)]
    for e in ids:
        _open(db, VOLTAGE, e, now - timedelta(hours=1))
    _run(db, """INSERT INTO workforce_attendance_events (company_id, employee_id, event_type, payload_json, occurred_at)
                VALUES (CAST(:c AS uuid), CAST(:e AS uuid), 'check_in', CAST(:p AS jsonb), :t)""",
         {"c": VOLTAGE, "e": ids[2], "p": json.dumps({"punch_location": {"gps_status": "outside"}}), "t": now - timedelta(minutes=30)})
    snap = _vivo(client, VOLTAGE)
    op = next(o for o in snap["ops"] if o["name"] == "Alabama")
    assert op["on"] == 7 and len(op["people"]) == 5 and op["extra"] == 2
    assert op["outside"] == 1 and any(p["outside"] for p in op["people"]) and op["people"][0]["role"] == "supervisor"
    assert op["scheduled"] is None and op["missing"] is None and op["cut"] is None, "sin horario ni avisos: —"
    assert snap["on_shift"] == 7


def test_clonexa_trabajadores_reales_y_nuevos(client, db, monkeypatch):
    _session(monkeypatch)
    client.state["n8n"] = {**N8N_OK, "workflows": N8N_OK["workflows"] + [flow("Nexa - Reels nuevos", minutes=2)]}
    _run(db, "INSERT INTO company_bot_instances (company_id, channel, name, bot_token_encrypted) VALUES (CAST(:c AS uuid), 'telegram', 'Bot', 'secreto-cifrado')", {"c": VOLTAGE})
    oficina_routes.reset_cache()
    r = client.get(f"{API}/clonexa/vivo")
    assert r.status_code == 200, r.text
    snap = r.json()
    by = {w["id"]: w for w in snap["workers"]}
    assert by["contenido"]["area"] == "marketing" and by["planb"]["state"] == "work" and by["correos"]["state"] == "err"
    extra = [w for w in snap["workers"] if w.get("extra")]
    assert [(w["name"], w["area"]) for w in extra] == [("Nexa - Reels nuevos", "marketing")], "un flujo nuevo aparece solo en su área"
    bots = [w for w in snap["workers"] if w.get("bot")]
    assert [w["name"] for w in bots] == ["Bot VOLTAGE"] and "secreto" not in json.dumps(snap)
    assert {c["name"] for c in snap["companies"]} >= {"Velvet", "ASADERO EL SOCIO", "The Time Machine", "VOLTAGE"}
    assert snap["treasury"] is None, "sin Facturación en la base: sin datos (nunca inventado)"
    assert snap["approvals"]["pieces"] == 2 and snap["map"] is None
    assert client.get(f"{API}/estado").json()["clonexa_style"] == "aprobado"
    same = client.get(f"{API}/clonexa/vivo?rev={snap['rev']}").json()
    assert same == {"ok": True, "same": True, "rev": snap["rev"]}, "cambios incrementales"


def test_editor_genero_guarda_y_recarga_y_otras_empresas_sin_cambios(client, db, monkeypatch):
    _session(monkeypatch)
    key = "persona:" + "a" * 12
    r = client.put(f"{API}/personajes", json={"clave": key, "company_id": VELVET, "genero": "hombre", "personaje": "Ch42_nonPBR", "barba": "no"})
    assert r.status_code == 200, r.text
    item = next(i for i in client.get(f"{API}/personajes").json()["items"] if i["clave"] == key)
    assert (item["genero"], item["personaje"], item["barba"]) == ("hombre", "Ch42_nonPBR", "no")
    assert client.put(f"{API}/personajes", json={"clave": key, "company_id": VELVET, "genero": "mujer", "barba": "si"}).status_code == 422
    ceo = client.put(f"{API}/personajes", json={"clave": "agente:director", "barba": "no", "color_pelo": "#c0c0c0"})
    assert ceo.status_code == 200 and ceo.json()["item"]["barba"] == "no"
    oficina_routes.reset_cache()
    assert client.get(f"{API}/pisos/{NUEVA}/vivo").status_code == 409, "una empresa sin el interruptor no tiene piso aprobado"
    assert client.get(f"{API}/pisos/{TTM}/vivo").json()["template"] == "bar", "The Time Machine sigue con su bar"
