"""Oficina 3D contra Postgres REAL (pgserver) y la app completa.

- 401 sin sesion en la pagina, sus archivos y todos los endpoints.
- Con sesion: pisos = empresas REGISTRADAS reales (no demos ni archivadas), cada una con su plantilla;
  15 agentes con estados de n8n simulados; n8n caido -> gris "sin datos".
- Personal: quien inicia turno aparece en su puesto, en pausa con ⏸, al cerrar desaparece; VOLTAGE con
  mas de 5 en una operacion muestra "+N"; privacidad "solo cargo".
- Representantes sin cifras de dinero; dia del bar 18:00-04:00 (pedido de las 02:00 cuenta, el de las
  17:00 no); restaurante: pedidos, en cocina y domicilios del dia.
- Editor: guardar, recargar y ver el cambio (cuerpo y peinado); las subidas de imagen/modelo responden 410 y
  lo ya guardado no sale; orden de pisos y plantilla guardados.
- Fase 1.5: copia viva de The Time Machine con sus mesas reales (mesa nueva aparece sola), eventos simulados
  (mesa abierta/cerrada, pedido nuevo/entregado, cancion, juego, turno, pausa), modo arquitecto que guarda y
  recarga, marca del Estudio de marca (o paleta neutra con aviso), recursos con cache larga y nada de dinero.
- Migracion aditiva e idempotente (dos veces seguidas).
"""
from __future__ import annotations

import asyncio
import importlib
import json
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

pgserver = pytest.importorskip("pgserver")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import app.main as app_main  # noqa: E402
from app.api.deps import get_db  # noqa: E402
from app.services import brand_media  # noqa: E402
from app.services import oficina as of  # noqa: E402
from app.web import admin_v2_routes, oficina_routes  # noqa: E402
from tests.test_menu_video_hospitality_pg import MemoryBucket  # noqa: E402

VELVET = "d63cf68c-be5b-4a30-aee4-341973018db1"
ASADERO = "7625872c-f941-4479-a27b-f8443be953c5"
TTM = "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4"
VOLTAGE = "f1e8f774-f052-49ca-880a-268805f07db0"
NUEVA = "0b0b0b0b-1111-4222-8333-444455556666"
DEMO = "0d0d0d0d-1111-4222-8333-444455556666"
ARCHIVADA = "0a0a0a0a-1111-4222-8333-444455556666"
API = "/admin-v2/api/oficina"

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (id uuid PRIMARY KEY, name text NOT NULL, slug text, status text DEFAULT 'active',
  settings_json jsonb DEFAULT '{}'::jsonb, timezone text, created_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text UNIQUE NOT NULL, name text, category text);
CREATE TABLE IF NOT EXISTS company_modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid REFERENCES companies(id) ON DELETE CASCADE,
  module_id uuid REFERENCES modules(id), enabled boolean DEFAULT true, settings jsonb DEFAULT '{}'::jsonb);
CREATE TABLE IF NOT EXISTS work_locations (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL REFERENCES companies(id),
  name varchar(80) NOT NULL, timezone varchar(64) NOT NULL DEFAULT 'America/Bogota');
CREATE TABLE IF NOT EXISTS employees (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL REFERENCES companies(id),
  full_name varchar(200), role varchar(80), status varchar(40) DEFAULT 'active', telegram_user_id varchar(120),
  work_location_id uuid NULL REFERENCES work_locations(id));
CREATE TABLE IF NOT EXISTS workforce_attendance_status (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, employee_id uuid NOT NULL,
  status varchar(40), last_event_type varchar(80), last_event_at timestamptz, check_in_at timestamptz, check_out_at timestamptz, updated_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS workforce_attendance_events (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, employee_id uuid,
  event_type varchar(80) NOT NULL, payload_json jsonb NOT NULL DEFAULT '{}'::jsonb, occurred_at timestamptz NOT NULL DEFAULT now(), created_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS hospitality_orders (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, table_key varchar(120) NOT NULL DEFAULT 'mesa',
  table_number varchar(120) NULL, order_type varchar(40) NOT NULL DEFAULT 'table', status varchar(40) NOT NULL DEFAULT 'pendiente', total numeric(14,2) NOT NULL DEFAULT 0,
  items jsonb NOT NULL DEFAULT '[]'::jsonb, archived_at timestamptz NULL, cancelled_at timestamptz NULL, closed_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NULL);
CREATE TABLE IF NOT EXISTS hospitality_song_requests (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, status varchar(20) DEFAULT 'pendiente',
  song text NOT NULL DEFAULT '', customer_name text NOT NULL DEFAULT '', archived_at timestamptz NULL, created_at timestamptz NOT NULL DEFAULT now(),
  table_number varchar(120) NOT NULL DEFAULT 'Mesa', playing_at timestamptz NULL);
CREATE TABLE IF NOT EXISTS hospitality_table_access (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, table_key text NOT NULL,
  table_number text, access_code text, status text, activated_at timestamptz DEFAULT now(), expires_at timestamptz);
CREATE TABLE IF NOT EXISTS hospitality_table_guests (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, access_id uuid NOT NULL,
  table_key varchar(120) NOT NULL, account_id varchar(120) NOT NULL, guest_number integer NOT NULL, name varchar(180) NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS loyalty_game_rounds (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, kind varchar(12) NOT NULL,
  status varchar(14) NOT NULL DEFAULT 'registration', prize varchar(160) NOT NULL DEFAULT '', started_at timestamptz, ends_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS company_brand_themes (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, status text NOT NULL, tokens jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS wa_contacts (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), stage varchar(20) NOT NULL DEFAULT 'nuevo', last_message_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now())
"""


def _migration(name: str) -> list[str]:
    statements: list[str] = []

    class Op:
        def execute(self, sql):
            statements.append(str(sql))

    module = importlib.import_module(f"migrations.versions.{name}")
    module.op = Op()
    module.upgrade()
    return statements


@pytest.fixture(scope="module")
def pg_url():
    folder = tempfile.mkdtemp(prefix="cx_pg_oficina_")
    server = pgserver.get_server(folder, cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url, poolclass=NullPool)
        async with engine.begin() as conn:
            for stmt in [s for s in SCHEMA.split(";") if s.strip()] + _migration("023b_admin_audit_log") + _migration("025j_oficina") * 2 + _migration("025k_oficina_real") * 2 + _migration("025l_oficina_bar") * 2 + _migration("025m_oficina_pisos") * 2:
                await conn.execute(text(stmt))
        await engine.dispose()

    asyncio.run(setup())
    yield url


def _run(url: str, sql: str, params: dict | None = None):
    async def go():
        engine = create_async_engine(url, poolclass=NullPool)
        async with engine.begin() as conn:
            result = await conn.execute(text(sql), params or {})
            rows = [dict(r) for r in result.mappings().all()] if result.returns_rows else None
        await engine.dispose()
        return rows
    return asyncio.run(go())


def flow(name, status="success", minutes=60, active=True, running=False):
    at = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    return {"name": name, "active": active, "running": running, "today_runs": 2, "today_errors": 1 if status == "error" else 0,
            "last": {"status": status, "started_at": at, "stopped_at": at}, "last_ok_at": at if status == "success" else None}


N8N_OK = {"ok": True, "workflows": [flow("Nexa - Bot de comandos", running=True), flow("Nexa - Plan B", minutes=5),
                                    flow("Nexa - Correos", status="error", minutes=3), flow("Nexa - Leads DEMO", active=False)],
          "recent": [], "calendar": {"ok": True, "ready": 2, "approved": 1, "week_pieces": 3, "next": None,
                                     "ready_items": [{"fecha": "12/11/2026", "formato": "Reel", "tema": "Domicilios"}]},
          "ideas": {"ok": True, "pending": 4, "items": ["Turnos"]}, "report": {"ok": False}}


@pytest.fixture
def client(pg_url, monkeypatch):
    for t in ("oficina_personajes", "oficina_pisos", "hospitality_orders", "hospitality_song_requests", "hospitality_table_access",
              "hospitality_table_guests", "loyalty_game_rounds", "company_brand_themes", "workforce_attendance_events",
              "workforce_attendance_status", "employees", "work_locations", "company_modules", "companies"):
        _run(pg_url, f"DELETE FROM {t}")

    def maker():
        engine = create_async_engine(pg_url, poolclass=NullPool)
        return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def db_dep():
        async with maker()() as session:
            yield session

    state = {"n8n": N8N_OK}

    async def fetch(url, secret):
        if state["n8n"] is None:
            raise RuntimeError("n8n caido")
        return json.loads(json.dumps(state["n8n"]))

    monkeypatch.setenv(of.ENV_URL, "https://n8n.test/webhook/oficina-estado")
    monkeypatch.setenv(of.ENV_SECRET, "s" * 40)
    monkeypatch.setattr(of.N8N, "fetch", fetch)
    monkeypatch.setattr(admin_v2_routes, "_session_secret", lambda: b"k" * 32)
    oficina_routes.reset_cache()
    bucket = MemoryBucket()
    brand_media.set_backend(bucket)
    app_main.app.dependency_overrides[get_db] = db_dep
    c = TestClient(app_main.app)
    c.state = state
    c.bucket = bucket
    yield c
    app_main.app.dependency_overrides.pop(get_db, None)
    brand_media.set_backend(None)
    oficina_routes.reset_cache()


def _session(monkeypatch, ok=True):
    monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=ok))


def _seed(url):
    now = datetime.now(timezone.utc)
    rows = [(VELVET, "Velvet", "active", {}, "America/Bogota", 1), (ASADERO, "ASADERO EL SOCIO", "active", {}, "America/Bogota", 2),
            (TTM, "The Time Machine", "active", {}, "America/Bogota", 3), (VOLTAGE, "VOLTAGE", "active", {"kind": "registrada"}, "America/New_York", 4),
            (NUEVA, "Nueva Empresa", "active", {"kind": "registrada"}, "America/Bogota", 5), (DEMO, "Brasa & Maíz (demo)", "active", {"kind": "demo"}, "America/Bogota", 6),
            (ARCHIVADA, "Vieja", "archived", {"kind": "registrada"}, "America/Bogota", 7)]
    for cid, name, status, settings, tz, n in rows:
        _run(url, "INSERT INTO companies (id, name, status, settings_json, timezone, created_at) VALUES (CAST(:i AS uuid), :n, :s, CAST(:j AS jsonb), :tz, :c)",
             {"i": cid, "n": name, "s": status, "j": json.dumps(settings), "tz": tz, "c": now - timedelta(days=100 - n)})
    return now


def _employee(url, cid, name, role, place=None):
    return _run(url, """INSERT INTO employees (company_id, full_name, role, work_location_id) VALUES (CAST(:c AS uuid), :n, :r, CAST(:p AS uuid)) RETURNING id::text""",
                {"c": cid, "n": name, "r": role, "p": place})[0]["id"]


def _open(url, cid, eid, started, status="working"):
    _run(url, """INSERT INTO workforce_attendance_status (company_id, employee_id, status, last_event_type, last_event_at, check_in_at)
                 VALUES (CAST(:c AS uuid), CAST(:e AS uuid), :s, 'check_in', :t, :t)""", {"c": cid, "e": eid, "s": status, "t": started})
    _run(url, """INSERT INTO workforce_attendance_events (company_id, employee_id, event_type, occurred_at) VALUES (CAST(:c AS uuid), CAST(:e AS uuid), 'check_in', :t)""",
         {"c": cid, "e": eid, "t": started})


def _estado(client):
    oficina_routes.reset_db_cache()
    r = client.get(f"{API}/estado")
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------ 401
def test_sin_sesion_todo_es_401(client, monkeypatch):
    _session(monkeypatch, False)
    page = client.get("/admin-v2plus/oficina", follow_redirects=False)
    assert page.status_code == 303 and page.headers["location"] == "/admin-v2plus/login"
    for method, url in [("GET", "/admin-v2plus/oficina/app.js"), ("GET", "/admin-v2plus/oficina/vendor/three/build/three.module.js"),
                        ("GET", f"{API}/estado"), ("GET", f"{API}/personajes"), ("PUT", f"{API}/personajes"),
                        ("POST", f"{API}/personajes/archivo?clave=rep&tipo=cara&company_id={VELVET}"), ("DELETE", f"{API}/personajes/archivo?clave=rep&tipo=cara"),
                        ("GET", f"{API}/archivos/clonexa/{'a' * 32}.png?e=1&s=x"), ("PUT", f"{API}/pisos/orden"), ("PUT", f"{API}/pisos/{VELVET}"),
                        ("GET", "/admin-v2plus/oficina/real.js"), ("GET", "/admin-v2plus/oficina/real_reglas.js"),
                        ("GET", "/admin-v2plus/oficina/recursos/manifest.json"), ("GET", "/admin-v2plus/oficina/recursos/modelos/mesa.glb"),
                        ("GET", "/admin-v2plus/oficina/vendor/three/examples/jsm/postprocessing/GTAOPass.js"),
                        ("GET", f"{API}/pisos/{TTM}/vivo"), ("PUT", f"{API}/pisos/{TTM}/distribucion"), ("DELETE", f"{API}/pisos/{TTM}/distribucion"),
                        ("GET", f"{API}/marca/{TTM}/logo")]:
        r = client.request(method, url, content=b"\x89PNG\r\n\x1a\n" if method == "POST" else None)
        assert r.status_code == 401, (method, url, r.status_code)


# ------------------------------------------------------------------ edificio
def test_edificio_con_las_empresas_registradas_reales(client, pg_url, monkeypatch):
    _session(monkeypatch)
    _seed(pg_url)
    page = client.get("/admin-v2plus/oficina")
    assert page.status_code == 200 and "script-src 'self' 'sha256-" in page.headers["content-security-policy"]
    data = _estado(client)
    names = [f["name"] for f in data["floors"]]
    assert names == ["Velvet", "ASADERO EL SOCIO", "The Time Machine", "VOLTAGE", "Nueva Empresa"], "ni demos ni archivadas"
    tpl = {f["name"]: (f["template"], f["template_source"]) for f in data["floors"]}
    assert tpl == {"Velvet": ("taller", "auto"), "ASADERO EL SOCIO": ("restaurante", "auto"), "The Time Machine": ("bar", "auto"),
                   "VOLTAGE": ("campo", "auto"), "Nueva Empresa": ("general", "sin_deducir")}
    assert next(f for f in data["floors"] if f["name"] == "Nueva Empresa")["needs_template"] is True
    assert data["cast"] == {"agents": 15, "reps": 5, "templates": 8, "on_shift": 0, "by_floor": [{"name": n, "on_shift": 0} for n in names]}
    states = {a["id"]: a["state"] for a in data["agents"]}
    assert states["asistente"] == "work" and states["planb"] == "work" and states["correos"] == "err" and states["comunidad"] == "train"
    assert states["tiktok"] == "nodata" and states["lector"] == "nodata", "flujos que n8n no devolvio: sin datos"
    assert data["approvals"]["pieces_count"] == 2 and data["ideas"]["pending"] == 4
    # n8n caido: todos los agentes en gris
    client.state["n8n"] = None
    of.N8N.reset()
    down = _estado(client)
    assert down["n8n"]["ok"] is False and {a["state"] for a in down["agents"] if a["id"] != "director"} == {"nodata"}
    # una empresa nueva aparece sola con su piso y su representante
    _run(pg_url, "INSERT INTO companies (id, name, settings_json) VALUES (CAST(:i AS uuid), 'Recién llegada', '{\"kind\": \"registrada\"}')", {"i": str(uuid.uuid4())})
    assert "Recién llegada" in [f["name"] for f in _estado(client)["floors"]]


def test_persona_entra_en_pausa_y_sale_al_cerrar_turno(client, pg_url, monkeypatch):
    _session(monkeypatch)
    now = _seed(pg_url)
    ana = _employee(pg_url, ASADERO, "Ana María Pérez Gómez", "mesero")
    luis = _employee(pg_url, ASADERO, "Luis Gómez", "cocina")
    _open(pg_url, ASADERO, ana, now - timedelta(hours=2))
    _open(pg_url, ASADERO, luis, now - timedelta(minutes=30), status="on_break")
    floor = next(f for f in _estado(client)["floors"] if f["company_id"] == ASADERO)
    staff = {p["label"]: p for p in floor["staff"]["visible"]}
    assert set(staff) == {"Ana P. · Mesero", "Luis G. · Cocina"} and staff["Luis G. · Cocina"]["paused"] is True
    assert staff["Ana P. · Mesero"]["uniform"] == "mesero"
    assert "Pérez" not in json.dumps(floor) and ana not in json.dumps(floor), "ni apellido completo ni id"
    _run(pg_url, "UPDATE workforce_attendance_status SET status = 'off', check_out_at = now() WHERE employee_id = CAST(:e AS uuid)", {"e": ana})
    floor = next(f for f in _estado(client)["floors"] if f["company_id"] == ASADERO)
    assert [p["label"] for p in floor["staff"]["visible"]] == ["Luis G. · Cocina"], "al cerrar turno sale del piso"
    # solo el cargo
    assert client.put(f"{API}/pisos/{ASADERO}", json={"privacidad": "cargo"}).status_code == 200
    floor = next(f for f in _estado(client)["floors"] if f["company_id"] == ASADERO)
    assert [p["label"] for p in floor["staff"]["visible"]] == ["Cocina"] and "Luis" not in json.dumps(floor)


def test_voltage_mas_de_5_muestra_mas_n(client, pg_url, monkeypatch):
    _session(monkeypatch)
    now = _seed(pg_url)
    va = _run(pg_url, "INSERT INTO work_locations (company_id, name, timezone) VALUES (CAST(:c AS uuid), 'Virginia', 'America/New_York') RETURNING id::text", {"c": VOLTAGE})[0]["id"]
    al = _run(pg_url, "INSERT INTO work_locations (company_id, name, timezone) VALUES (CAST(:c AS uuid), 'Alabama', 'America/Chicago') RETURNING id::text", {"c": VOLTAGE})[0]["id"]
    for i in range(8):
        _open(pg_url, VOLTAGE, _employee(pg_url, VOLTAGE, f"Tecnico Virginia {i}", "tecnico", va), now - timedelta(hours=1))
    for i in range(2):
        _open(pg_url, VOLTAGE, _employee(pg_url, VOLTAGE, f"Tecnico Alabama {i}", "tecnico", al), now - timedelta(hours=1))
    eid = _employee(pg_url, VOLTAGE, "Fuera Perimetro", "tecnico", al)
    _run(pg_url, """INSERT INTO workforce_attendance_events (company_id, employee_id, event_type, payload_json, occurred_at)
                    VALUES (CAST(:c AS uuid), CAST(:e AS uuid), 'check_in', '{"punch_location": {"gps_status": "outside"}}', now())""", {"c": VOLTAGE, "e": eid})
    floor = next(f for f in _estado(client)["floors"] if f["company_id"] == VOLTAGE)
    ops = {o["name"]: o for o in floor["staff"]["ops"]}
    assert ops["Virginia"]["total"] == 8 and len(ops["Virginia"]["visible"]) == 5 and ops["Virginia"]["extra"] == 3
    assert ops["Alabama"]["extra"] == 0 and floor["staff"]["extra"] == 3
    kpis = dict((k, v) for k, v in floor["kpis"])
    assert kpis["En turno · Alabama / Virginia"] == "2 · 8" and kpis["Fuera de perímetro"] == "1"
    assert kpis["Sin conectar"] == "—", "sin Horario de la semana no se inventa"


def test_representantes_sin_dinero_y_dia_del_bar(client, pg_url, monkeypatch):
    _session(monkeypatch)
    _seed(pg_url)
    tz = ZoneInfo("America/Bogota")
    now = datetime(2026, 11, 12, 2, 30, tzinfo=tz).astimezone(timezone.utc)  # 02:30: sigue la jornada que abrio el 11 a las 18:00
    monkeypatch.setattr(oficina_routes, "_now", lambda: now)
    at = lambda d, h, m=0: datetime(2026, 11, d, h, m, tzinfo=tz).astimezone(timezone.utc)  # noqa: E731
    for moment, status in ((at(12, 2), "cerrado"), (at(11, 23), "entregado"), (at(11, 17), "cerrado"), (at(11, 22), "cancelado")):
        _run(pg_url, "INSERT INTO hospitality_orders (company_id, table_key, status, total, created_at) VALUES (CAST(:c AS uuid), :k, :s, 987654.32, :t)",
             {"c": TTM, "k": f"mesa-{moment.hour}", "s": status, "t": moment})
    for moment in (at(11, 21), at(12, 1), at(11, 16)):
        _run(pg_url, "INSERT INTO hospitality_song_requests (company_id, created_at) VALUES (CAST(:c AS uuid), :t)", {"c": TTM, "t": moment})
    for kind, status in (("table", "alistando"), ("domicilio", "pendiente"), ("table", "cerrado")):
        _run(pg_url, "INSERT INTO hospitality_orders (company_id, order_type, status, total, created_at) VALUES (CAST(:c AS uuid), :k, :s, 123456.78, :t)",
             {"c": ASADERO, "k": kind, "s": status, "t": now - timedelta(minutes=5)})
    data = _estado(client)
    tm = next(f for f in data["floors"] if f["company_id"] == TTM)
    bar = dict((k, v) for k, v in tm["kpis"])
    assert bar == {"Mesas abiertas": "1", "Pedidos a barra": "2", "Canciones pedidas": "2", "Personal en turno": "0"}, "17:00 y 16:00 no son de la jornada"
    assert tm["lines"] == ["Jornada 18:00–04:00: 11/11 18:00 a 12/11 04:00"]
    asadero = dict((k, v) for k, v in next(f for f in data["floors"] if f["company_id"] == ASADERO)["kpis"])
    assert asadero == {"Pedidos del día": "3", "En cocina ahora": "2", "Domicilios del día": "1", "Personal en turno": "0"}
    text_out = json.dumps(data)
    assert "987654" not in text_out and "123456" not in text_out and "$" not in json.dumps([f["kpis"] for f in data["floors"]])


# ------------------------------------------------------------------ editor y pisos
def test_editor_guarda_recarga_y_ya_no_carga_archivos(client, pg_url, monkeypatch):
    _session(monkeypatch)
    _seed(pg_url)
    r = client.put(f"{API}/personajes", json={"clave": "agente:ventas", "nombre": "Nexa Ventas Pro", "estilo": "lego", "color_ropa": "#112233",
                                              "cuerpo": "robusto", "peinado": "rizado", "accesorio": "delantal"})
    assert r.status_code == 200, r.text
    body = client.get(f"{API}/personajes").json()
    saved = next(i for i in body["items"] if i["clave"] == "agente:ventas")
    assert (saved["nombre"], saved["estilo"], saved["color_ropa"], saved["cuerpo"], saved["peinado"], saved["accesorio"]) == \
        ("Nexa Ventas Pro", "lego", "#112233", "robusto", "rizado", "delantal") and saved["company_id"] is None
    assert body["options"]["accesorio"] == ["none", "audifonos", "gafas", "gorra", "casco", "chaleco", "delantal", "corbata"]
    assert client.put(f"{API}/personajes", json={"clave": "agente:ventas", "estilo": "anime"}).json()["item"]["nombre"] == "Nexa Ventas Pro"
    assert client.put(f"{API}/personajes", json={"clave": "agente:ventas", "estilo": "modelo"}).status_code == 422
    assert client.put(f"{API}/personajes", json={"clave": "agente:ventas", "accesorio": "capa"}).status_code == 422
    assert client.put(f"{API}/personajes", json={"clave": "rep", "company_id": VELVET, "nombre": "Rep. Velvet"}).status_code == 200
    assert client.put(f"{API}/personajes", json={"clave": "rep", "company_id": DEMO, "nombre": "x"}).status_code == 404, "solo registradas"
    assert client.put(f"{API}/personajes", json={"clave": "rep", "nombre": "x"}).status_code == 422
    assert client.put(f"{API}/personajes", json={"clave": "agente:batman", "nombre": "x"}).status_code == 404
    # subidas desactivadas (410) y nada llega al bucket
    png = b"\x89PNG\r\n\x1a\n" + b"\0" * 200
    for method, url in (("POST", f"{API}/personajes/archivo?clave=agente:ventas&tipo=cara"), ("POST", f"{API}/personajes/archivo?clave=agente:ventas&tipo=modelo"),
                        ("DELETE", f"{API}/personajes/archivo?clave=agente:ventas&tipo=cara"), ("GET", f"{API}/archivos/clonexa/{'a' * 32}.png?e=1&s=x")):
        r = client.request(method, url, content=png if method == "POST" else None)
        assert r.status_code == 410, (method, url, r.status_code)
    assert not client.bucket.objects
    # lo ya cargado se conserva en la base pero no se muestra
    _run(pg_url, "UPDATE oficina_personajes SET cara_key = 'oficina/clonexa/x.png', modelo_key = 'oficina/clonexa/y.glb', estilo = 'modelo' WHERE clave = 'agente:ventas'")
    saved = next(i for i in client.get(f"{API}/personajes").json()["items"] if i["clave"] == "agente:ventas")
    assert not [k for k in saved if k.endswith("_url") or k.endswith("_key")] and saved["estilo"] == "", "no se usa ni se muestra"
    assert _run(pg_url, "SELECT cara_key FROM oficina_personajes WHERE clave = 'agente:ventas'")[0]["cara_key"] == "oficina/clonexa/x.png", "no se borra"


def test_orden_y_plantilla_de_los_pisos(client, pg_url, monkeypatch):
    _session(monkeypatch)
    _seed(pg_url)
    order = [VOLTAGE, TTM, VELVET, ASADERO, NUEVA]
    assert client.put(f"{API}/pisos/orden", json={"company_ids": order}).status_code == 200
    assert client.put(f"{API}/pisos/orden", json={"company_ids": [VELVET, DEMO]}).status_code == 422, "una demo no es piso"
    assert client.put(f"{API}/pisos/{NUEVA}", json={"plantilla": "taller"}).status_code == 200
    assert client.put(f"{API}/pisos/{NUEVA}", json={"plantilla": "nave espacial"}).status_code == 422
    data = _estado(client)
    assert [f["company_id"] for f in data["floors"]] == order
    nueva = next(f for f in data["floors"] if f["company_id"] == NUEVA)
    assert (nueva["template"], nueva["template_source"], nueva["needs_template"]) == ("taller", "manual", False)


def test_otras_empresas_sin_cambios_en_sus_paneles():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for name in ("client.js", "client.html", "mini_panel.js", "hospitality_order.js", "carta_app.js"):
        path = root / "app/web" / name
        if path.exists():
            body = path.read_text(encoding="utf-8")
            assert "/admin-v2/api/oficina" not in body and "admin-v2plus/oficina" not in body, name
    registry = json.loads((root / "app/services/switch_registry.json").read_text(encoding="utf-8"))
    assert not [s for s in registry["switches"] if "oficina" in s["key"]], "no hay interruptor nuevo: no es de ninguna empresa"


# ------------------------------------------------------------------ fase 1.5: piso realista de The Time Machine
def _qr_tables(url, cid, count):
    mod = _run(url, "INSERT INTO modules (code, name) VALUES ('qr', 'QR') ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name RETURNING id::text")[0]["id"]
    _run(url, "DELETE FROM company_modules WHERE company_id = CAST(:c AS uuid) AND module_id = CAST(:m AS uuid)", {"c": cid, "m": mod})
    _run(url, "INSERT INTO company_modules (company_id, module_id, enabled, settings) VALUES (CAST(:c AS uuid), CAST(:m AS uuid), true, CAST(:s AS jsonb))",
         {"c": cid, "m": mod, "s": json.dumps({"qr_config": {"table_count": count, "max_capacity": 40}})})


def _vivo(client, cid=TTM, rev=""):
    oficina_routes.reset_live_cache()
    r = client.get(f"{API}/pisos/{cid}/vivo" + (f"?rev={rev}" if rev else ""))
    assert r.status_code == 200, r.text
    return r.json()


MONEY_KEYS = ("total", "price", "precio", "subtotal", "amount", "monto", "valor", "venta", "sales", "ticket", "cash", "propina", "cuenta")


def _no_money(obj, where=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "total" and "staff" in where and isinstance(v, (int, type(None))):
                continue  # personas en turno (conteo), no dinero
            assert not any(m in str(k).lower() for m in MONEY_KEYS), f"campo de dinero {where}.{k}"
            _no_money(v, f"{where}.{k}")
    elif isinstance(obj, list):
        for v in obj:
            _no_money(v, where)


def test_ttm_realista_por_migracion_y_las_demas_clasicas(client, pg_url, monkeypatch):
    _session(monkeypatch)
    _seed(pg_url)
    for stmt in _migration("025k_oficina_real") * 2:   # con The Time Machine ya registrada (como en produccion)
        _run(pg_url, stmt)
    rows = {r["company_id"]: r["estilo"] for r in _run(pg_url, "SELECT company_id::text AS company_id, estilo FROM oficina_pisos")}
    assert rows == {TTM: "realista"}, "solo The Time Machine; las demas quedan como hoy (sin fila = clasico)"
    floors = {f["company_id"]: f for f in _estado(client)["floors"]}
    assert floors[TTM]["style"] == "realista" and floors[TTM]["brand"]["source"] == "neutra"
    assert {floors[c]["style"] for c in (VELVET, ASADERO, VOLTAGE, NUEVA)} == {"clasico"} and all(floors[c]["brand"] is None for c in (VELVET, ASADERO, VOLTAGE, NUEVA))
    # el interruptor se apaga y se enciende desde la ficha (solo plantillas con motor realista)
    assert client.put(f"{API}/pisos/{TTM}", json={"estilo": "clasico"}).status_code == 200
    assert next(f for f in _estado(client)["floors"] if f["company_id"] == TTM)["style"] == "clasico"
    assert client.put(f"{API}/pisos/{TTM}", json={"estilo": "dorado"}).status_code == 422
    assert client.put(f"{API}/pisos/{VELVET}", json={"estilo": "realista"}).status_code == 200
    assert next(f for f in _estado(client)["floors"] if f["company_id"] == VELVET)["style"] == "clasico", "el taller aun no tiene motor realista"
    assert client.get(f"{API}/pisos/{VELVET}/vivo").status_code == 409


def test_copia_viva_con_las_mesas_reales_y_eventos(client, pg_url, monkeypatch):
    _session(monkeypatch)
    now = _seed(pg_url)
    _qr_tables(pg_url, TTM, 10)
    snap = _vivo(client)
    labels = [t["label"] for t in snap["tables"]]
    assert labels == [f"Mesa {i}" for i in range(1, 11)], "las 10 mesas reales de su QR"
    assert sorted(k for k in snap["layout"]["items"] if k.startswith("mesa:")) == sorted(f"mesa:Mesa {i}" for i in range(1, 11))
    assert {"barra", "dj", "pantalla", "entrada", "caja", "personal"} <= set(snap["layout"]["items"])
    assert not any(t["open"] for t in snap["tables"]) and snap["orders"] == [] and snap["game"] is None
    # mesa abierta con 3 personas registradas
    acc = _run(pg_url, """INSERT INTO hospitality_table_access (company_id, table_key, table_number, status, activated_at, expires_at)
                          VALUES (CAST(:c AS uuid), 'mesa-7', 'Mesa 7', 'active', now(), now() + interval '3 hours') RETURNING id::text""", {"c": TTM})[0]["id"]
    for n in (1, 2, 3):
        _run(pg_url, """INSERT INTO hospitality_table_guests (company_id, access_id, table_key, account_id, guest_number, name)
                        VALUES (CAST(:c AS uuid), CAST(:a AS uuid), 'mesa-7', :n, :g, 'Laura')""", {"c": TTM, "a": acc, "n": f"acc{n}", "g": n})
    # pedido nuevo a barra con 3 productos (cantidades 2 + 1) y precios que NUNCA deben salir
    items = [{"name": "Cerveza", "quantity": 2, "unit_price": 987654, "subtotal": 1975308}, {"name": "Coctel", "quantity": 1, "unit_price": 55555}]
    oid = _run(pg_url, """INSERT INTO hospitality_orders (company_id, table_key, table_number, status, total, items, created_at, updated_at)
                          VALUES (CAST(:c AS uuid), 'mesa-7', 'Mesa 7', 'pendiente', 987654.32, CAST(:i AS jsonb), now(), now()) RETURNING id::text""",
               {"c": TTM, "i": json.dumps(items)})[0]["id"]
    _run(pg_url, "INSERT INTO hospitality_song_requests (company_id, song, customer_name, status) VALUES (CAST(:c AS uuid), 'La Bicicleta', 'Pedro Pérez', 'pendiente')", {"c": TTM})
    _run(pg_url, "INSERT INTO loyalty_game_rounds (company_id, kind, status) VALUES (CAST(:c AS uuid), 'trivia', 'playing')", {"c": TTM})
    barman = _employee(pg_url, TTM, "Carlos Andrés Ruiz", "Barman")
    mesera = _employee(pg_url, TTM, "Diana López", "Mesera")
    _open(pg_url, TTM, barman, now - timedelta(hours=1))
    _open(pg_url, TTM, mesera, now - timedelta(hours=1))
    s2 = _vivo(client)
    m7 = next(t for t in s2["tables"] if t["label"] == "Mesa 7")
    assert m7["open"] is True and m7["guests"] == 3
    assert [(o["table"], o["state"], o["items"]) for o in s2["orders"]] == [("Mesa 7", "nuevo", 3)]
    assert [x["title"] for x in s2["songs"]] == ["La Bicicleta"] and s2["game"]["kind"] == "trivia" and s2["game"]["label"] == "Trivia"
    tasks = {p["uniform"]: p["task"] for p in s2["staff"]["people"]}
    assert tasks["barman"] == "Preparando 3 productos · Mesa 7" and tasks["mesero"] == "Atendiendo 1 mesa"
    dumped = json.dumps(s2)
    for leak in ("987654", "1975308", "55555", "Pedro", "Laura", "Ruiz", "Cerveza", oid):
        assert leak not in dumped, leak
    _no_money(s2)
    # misma copia -> "same"; pedido entregado -> cambia
    assert client.get(f"{API}/pisos/{TTM}/vivo?rev={s2['rev']}").json() == {"ok": True, "same": True, "rev": s2["rev"]}
    _run(pg_url, "UPDATE hospitality_orders SET status = 'entregado', updated_at = now() WHERE id = CAST(:o AS uuid)", {"o": oid})
    s3 = _vivo(client, rev=s2["rev"])
    assert s3.get("same") is None and s3["orders"][0]["state"] == "entregado"
    assert {p["uniform"]: p["task"] for p in s3["staff"]["people"]}["mesero"] == "Llevando pedido · Mesa 7"
    # pausa y mesa cerrada; mesa nueva en Clonexa aparece sola
    _run(pg_url, "UPDATE workforce_attendance_status SET status = 'on_break' WHERE employee_id = CAST(:e AS uuid)", {"e": mesera})
    _run(pg_url, "UPDATE hospitality_table_access SET status = 'closed'")
    _run(pg_url, "UPDATE hospitality_orders SET archived_at = now()")
    _qr_tables(pg_url, TTM, 11)
    s4 = _vivo(client)
    assert not any(t["open"] for t in s4["tables"]) and len(s4["tables"]) == 11 and "mesa:Mesa 11" in s4["layout"]["items"]
    assert next(p for p in s4["staff"]["people"] if p["uniform"] == "mesero")["task"] == "En pausa · café"
    # cierra turno -> se va
    _run(pg_url, "UPDATE workforce_attendance_status SET status = 'off' WHERE employee_id = CAST(:e AS uuid)", {"e": barman})
    assert [p["uniform"] for p in _vivo(client)["staff"]["people"]] == ["mesero"]


def test_modo_arquitecto_guarda_recarga_y_acomoda(client, pg_url, monkeypatch):
    _session(monkeypatch)
    _seed(pg_url)
    _qr_tables(pg_url, TTM, 4)
    auto = _vivo(client)["layout"]
    assert auto["custom"] is False
    r = client.put(f"{API}/pisos/{TTM}/distribucion", json={"items": {"mesa:Mesa 1": [2.5, 1.25, 0.785], "barra": [-6, -4, 0], "dj": [999, -999, 0]}})
    assert r.status_code == 200, r.text
    lay = _vivo(client)["layout"]
    W, D = lay["room"]["W"], lay["room"]["D"]
    assert lay["custom"] is True and lay["items"]["mesa:Mesa 1"] == [2.5, 1.25, 0.785] and lay["items"]["barra"] == [-6, -4, 0]
    assert lay["items"]["dj"] == [W / 2, -D / 2, 0], "fuera del salon se ajusta al borde"
    assert lay["items"]["mesa:Mesa 2"] == auto["items"]["mesa:Mesa 2"], "lo no movido queda en su puesto automatico"
    for bad in ({"items": {"mesa:Mesa 99": [0, 0, 0]}}, {"items": {"cohete": [0, 0, 0]}}, {"items": {"barra": [0, "x", 0]}}, {"nada": 1}):
        assert client.put(f"{API}/pisos/{TTM}/distribucion", json=bad).status_code == 422, bad
    _qr_tables(pg_url, TTM, 5)
    assert "mesa:Mesa 5" in _vivo(client)["layout"]["items"], "mesa nueva aparece sola sin perder lo guardado"
    assert client.delete(f"{API}/pisos/{TTM}/distribucion").status_code == 200
    again = _vivo(client)["layout"]
    assert again["custom"] is False and again["items"]["mesa:Mesa 1"] != [2.5, 1.25, 0.785]


def test_marca_del_estudio_y_paleta_neutra_con_aviso(client, pg_url, monkeypatch):
    from app.services import brand_theme as bt

    _session(monkeypatch)
    _seed(pg_url)
    _qr_tables(pg_url, TTM, 3)
    neutral = _vivo(client)["brand"]
    assert neutral["source"] == "neutra" and neutral["warning"] == "⚠ Configura la marca en el Estudio de marca" and neutral["logo_url"] == ""
    assert client.get(f"{API}/marca/{TTM}/logo").status_code == 404
    tokens = bt.make_tokens(bt.palette("#1d0b4f", "#e11d48", "#0b0b10", "#f5f5f5"))
    _run(pg_url, "INSERT INTO company_brand_themes (company_id, status, tokens) VALUES (CAST(:c AS uuid), 'published', CAST(:t AS jsonb))",
         {"c": TTM, "t": json.dumps(tokens)})
    b = _vivo(client)["brand"]
    assert b["source"] == "estudio" and b["warning"] is None and b["colors"]["primary"] == "#1d0b4f" and b["colors"]["secondary"] == "#e11d48"
    assert bt.contrast(b["accent"], "#0f0c11") >= 3.0 and b["accent"] != "#1d0b4f", "el morado oscuro se aclara para leerse como neon"
    # el cambio de marca llega en el siguiente refresco (estado del edificio incluido)
    tokens2 = bt.make_tokens(bt.palette("#16a34a", "#111827", "#0b0b10", "#f5f5f5"))
    _run(pg_url, "UPDATE company_brand_themes SET tokens = CAST(:t AS jsonb) WHERE company_id = CAST(:c AS uuid)", {"c": TTM, "t": json.dumps(tokens2)})
    assert _vivo(client)["brand"]["colors"]["primary"] == "#16a34a"
    _run(pg_url, "INSERT INTO oficina_pisos (company_id, estilo) VALUES (CAST(:c AS uuid), 'realista') ON CONFLICT (company_id) DO UPDATE SET estilo = 'realista'", {"c": TTM})
    assert next(f for f in _estado(client)["floors"] if f["company_id"] == TTM)["brand"]["colors"]["primary"] == "#16a34a"
    # logo del panel inicial (data:image PNG) cuando el estudio no tiene logo
    png = b"\x89PNG\r\n\x1a\n" + b"\0" * 40
    legacy = {"branding": {"primary_color": "#ff5500", "logo_url": "data:image/png;base64," + __import__("base64").b64encode(png).decode()}}
    _run(pg_url, "UPDATE companies SET settings_json = CAST(:s AS jsonb) WHERE id = CAST(:c AS uuid)", {"c": TTM, "s": json.dumps(legacy)})
    b = _vivo(client)["brand"]
    assert b["logo_url"].startswith(f"{API}/marca/{TTM}/logo?v=")
    got = client.get(b["logo_url"])
    assert got.status_code == 200 and got.content == png and got.headers["content-type"] == "image/png"
    _run(pg_url, "DELETE FROM company_brand_themes")
    b = _vivo(client)["brand"]
    assert b["source"] == "panel" and b["colors"]["primary"] == "#ff5500" and b["warning"], "sin estudio: colores del panel inicial y el aviso"


def test_dia_del_bar_cerrado_y_recursos_con_cache_larga(client, pg_url, monkeypatch):
    _session(monkeypatch)
    _seed(pg_url)
    _qr_tables(pg_url, TTM, 2)
    tz = ZoneInfo("America/Bogota")
    monkeypatch.setattr(oficina_routes, "_now", lambda: datetime(2026, 11, 12, 11, 0, tzinfo=tz).astimezone(timezone.utc))
    biz = _vivo(client)["business"]
    assert biz == {"open": False, "lights": "low", "sign": "Cerrado · abre 18:00", "activity_off_hours": False, "hours": "18:00–04:00"}
    monkeypatch.setattr(oficina_routes, "_now", lambda: datetime(2026, 11, 12, 1, 0, tzinfo=tz).astimezone(timezone.utc))
    assert _vivo(client)["business"]["open"] is True
    man = client.get("/admin-v2plus/oficina/recursos/manifest.json")
    assert man.status_code == 200 and "modelos/mesa.glb" in man.json()["files"]
    glb = client.get("/admin-v2plus/oficina/recursos/modelos/mesa.glb")
    assert glb.status_code == 200 and glb.content[:4] == b"glTF" and glb.headers["cache-control"] == "private, max-age=31536000, immutable"
    assert client.get("/admin-v2plus/oficina/recursos/../oficina_routes.py").status_code == 404
    assert client.get("/admin-v2plus/oficina/recursos/modelos/otro.glb").status_code == 404
    page = client.get("/admin-v2plus/oficina")
    assert "'wasm-unsafe-eval'" in page.headers["content-security-policy"] and "'unsafe-eval'" not in page.headers["content-security-policy"].replace("'wasm-unsafe-eval'", "")


def test_ninguna_respuesta_de_la_oficina_trae_dinero(client, pg_url, monkeypatch):
    _session(monkeypatch)
    now = _seed(pg_url)
    _qr_tables(pg_url, TTM, 3)
    _run(pg_url, "INSERT INTO hospitality_orders (company_id, table_key, table_number, status, total, items, created_at) VALUES (CAST(:c AS uuid), 'mesa-1', 'Mesa 1', 'alistando', 777777.77, CAST(:i AS jsonb), now())",
         {"c": TTM, "i": json.dumps([{"quantity": 1, "unit_price": 777777, "subtotal": 777777}])})
    _open(pg_url, TTM, _employee(pg_url, TTM, "Ana Caja", "Cajera"), now - timedelta(hours=1))
    for body in (_estado(client), _vivo(client), client.get(f"{API}/personajes").json()):
        _no_money(body)
        assert "777777" not in json.dumps(body)


# ------------------------------------------------------------------ bar aprobado (Mixamo, bucket privado)
def _fake_glb(tag: str) -> bytes:
    body = json.dumps({"asset": {"version": "2.0"}, "nodes": [{"name": tag}]}).encode()
    body += b" " * (-len(body) % 4)
    return b"glTF" + (2).to_bytes(4, "little") + (20 + len(body)).to_bytes(4, "little") + len(body).to_bytes(4, "little") + b"JSON" + body


def _upload_bar(bucket, names=("personajes/Ch01_nonPBR.glb", "animaciones/Idle.glb")):
    import hashlib

    from app.services import oficina_bar as obar

    files = {}
    for n in names:
        data = _fake_glb(n)
        bucket.put(obar.PREFIX + n, data)
        files[n] = {"bytes": len(data), "sha": hashlib.sha256(data).hexdigest()}
    bucket.put(obar.MANIFEST_KEY, json.dumps({"version": "t", "files": files}).encode())
    oficina_routes.reset_cache()
    return files


def test_bar_sin_sesion_401_en_pagina_api_y_recursos_del_bucket(client, monkeypatch):
    _upload_bar(client.bucket)
    _session(monkeypatch, False)
    for url in ("/admin-v2plus/oficina/bar.js", "/admin-v2plus/oficina/bar_reglas.js", "/admin-v2plus/oficina/bar/manifest.json",
                "/admin-v2plus/oficina/bar/personajes/Ch01_nonPBR.glb", "/admin-v2plus/oficina/bar/animaciones/Idle.glb", f"{API}/pisos/{TTM}/vivo"):
        r = client.get(url)
        assert r.status_code == 401, (url, r.status_code)
        assert b"glTF" not in r.content


def test_bar_recursos_privados_con_sesion_cache_y_huella(client, monkeypatch):
    _session(monkeypatch)
    files = _upload_bar(client.bucket)
    man = client.get("/admin-v2plus/oficina/bar/manifest.json")
    assert man.status_code == 200 and man.json()["files"] == files and man.headers["cache-control"].startswith("no-store")
    r = client.get("/admin-v2plus/oficina/bar/personajes/Ch01_nonPBR.glb")
    assert r.status_code == 200 and r.content[:4] == b"glTF" and r.headers["content-type"] == "model/gltf-binary"
    assert r.headers["cache-control"] == "private, max-age=31536000, immutable" and r.headers["etag"] == f'"{files["personajes/Ch01_nonPBR.glb"]["sha"]}"'
    # en memoria: aunque el bucket se caiga, lo ya leido se sirve
    client.bucket.objects.pop("oficina/bar/v1/personajes/Ch01_nonPBR.glb")
    assert client.get("/admin-v2plus/oficina/bar/personajes/Ch01_nonPBR.glb").status_code == 200
    # fuera de la lista blanca o con ruta rara: 404; huella alterada: 503 (nunca se sirve)
    for bad in ("personajes/Otro.glb", "personajes/Ch01-nonPBR.glb", "texturas/x.webp", "personajes/Ch01_nonPBR.fbx"):
        assert client.get(f"/admin-v2plus/oficina/bar/{bad}").status_code == 404, bad
    client.bucket.put("oficina/bar/v1/animaciones/Idle.glb", b"glTF" + b"0" * 40)
    assert client.get("/admin-v2plus/oficina/bar/animaciones/Idle.glb").status_code == 503
    # bucket sin manifiesto: 503 claro (el piso abre sin personas)
    client.bucket.objects.clear()
    oficina_routes.reset_cache()
    assert client.get("/admin-v2plus/oficina/bar/manifest.json").status_code == 503
    js = client.get("/admin-v2plus/oficina/bar.js")
    assert js.status_code == 200 and "openBar" in js.text


def test_bar_encendido_solo_en_ttm_por_migracion_y_otras_sin_cambios(client, pg_url, monkeypatch):
    _session(monkeypatch)
    _seed(pg_url)
    for stmt in _migration("025k_oficina_real") + _migration("025l_oficina_bar") * 2 + _migration("025m_oficina_pisos") * 2:
        _run(pg_url, stmt)
    rows = {r["company_id"]: r["estilo"] for r in _run(pg_url, "SELECT company_id::text AS company_id, estilo FROM oficina_pisos")}
    assert rows == {TTM: "bar", VELVET: "aprobado", ASADERO: "aprobado", VOLTAGE: "aprobado"}, "bar solo TTM; pisos aprobados (025m) solo sus 3 empresas"
    floors = {f["company_id"]: f for f in _estado(client)["floors"]}
    assert floors[TTM]["style"] == "bar" and floors[TTM]["brand"] is not None
    assert {floors[c]["style"] for c in (VELVET, ASADERO, VOLTAGE)} == {"aprobado"}
    assert floors[NUEVA]["style"] == "clasico" and floors[NUEVA]["brand"] is None, "una empresa nueva no ve nada nuevo"
    assert client.put(f"{API}/pisos/{VELVET}", json={"estilo": "bar"}).status_code == 200
    assert next(f for f in _estado(client)["floors"] if f["company_id"] == VELVET)["style"] == "clasico", "el taller no tiene bar"
    assert client.put(f"{API}/pisos/{TTM}", json={"estilo": "realista"}).status_code == 200
    assert next(f for f in _estado(client)["floors"] if f["company_id"] == TTM)["style"] == "realista"


def test_bar_pantalla_de_canciones_con_datos_y_sin_datos(client, pg_url, monkeypatch):
    _session(monkeypatch)
    _seed(pg_url)
    _qr_tables(pg_url, TTM, 10)
    assert _vivo(client)["song_screen"] == {"now": None, "queue": []}, "sin pedidas: la pantalla invita a pedir"
    now = datetime.now(timezone.utc)
    for i, (song, table, status, cust) in enumerate([("Noche de salsa", "Mesa 4", "sonando", "Ana Gómez"), ("Luces de neón", "Mesa 7", "pendiente", "Pedro"),
                                                      ("Volver a bailar", "Barra 3", "pendiente", "Luis"), ("Ritmo de medianoche", "Mesa 2", "pendiente", "Eva"),
                                                      ("La cuarta en cola", "Mesa 1", "pendiente", "Sara"), ("Ya sonó", "Mesa 5", "reproducida", "Tom")]):
        _run(pg_url, """INSERT INTO hospitality_song_requests (company_id, song, customer_name, status, table_number, created_at, playing_at)
                        VALUES (CAST(:c AS uuid), :s, :n, :st, :t, :at, :p)""",
             {"c": TTM, "s": song, "n": cust, "st": status, "t": table, "at": now - timedelta(minutes=30 - i), "p": now - timedelta(minutes=2) if status == "sonando" else None})
    snap = _vivo(client)
    sc = snap["song_screen"]
    assert sc["now"]["title"] == "Noche de salsa" and sc["now"]["table"] == "Mesa 4" and sc["now"]["since"]
    assert sc["queue"] == [{"title": "Luces de neón", "table": "Mesa 7"}, {"title": "Volver a bailar", "table": "Barra · silla 3"},
                           {"title": "Ritmo de medianoche", "table": "Mesa 2"}], "las siguientes 3, la más antigua primero"
    dumped = json.dumps(snap)
    for leak in ("Ana", "Pedro", "Luis", "Gómez"):
        assert leak not in dumped, "nunca el nombre del cliente"
    _no_money(snap)
