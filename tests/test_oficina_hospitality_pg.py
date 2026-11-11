"""Oficina 3D contra Postgres REAL (pgserver) y la app completa.

- 401 sin sesion en la pagina, sus archivos y todos los endpoints.
- Con sesion: pisos = empresas REGISTRADAS reales (no demos ni archivadas), cada una con su plantilla;
  15 agentes con estados de n8n simulados; n8n caido -> gris "sin datos".
- Personal: quien inicia turno aparece en su puesto, en pausa con ⏸, al cerrar desaparece; VOLTAGE con
  mas de 5 en una operacion muestra "+N"; privacidad "solo cargo".
- Representantes sin cifras de dinero; dia del bar 18:00-04:00 (pedido de las 02:00 cuenta, el de las
  17:00 no); restaurante: pedidos, en cocina y domicilios del dia.
- Editor: guardar, recargar y ver el cambio; archivo con tipo falso (415) o muy grande (413) rechazado;
  archivo real al bucket (en memoria) y servido con enlace firmado; orden de pisos y plantilla guardados.
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
  order_type varchar(40) NOT NULL DEFAULT 'table', status varchar(40) NOT NULL DEFAULT 'pendiente', total numeric(14,2) NOT NULL DEFAULT 0,
  archived_at timestamptz NULL, cancelled_at timestamptz NULL, closed_at timestamptz NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS hospitality_song_requests (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, status varchar(20) DEFAULT 'pendiente',
  created_at timestamptz NOT NULL DEFAULT now());
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
            for stmt in [s for s in SCHEMA.split(";") if s.strip()] + _migration("023b_admin_audit_log") + _migration("025j_oficina") * 2:
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
    for t in ("oficina_personajes", "oficina_pisos", "hospitality_orders", "hospitality_song_requests", "workforce_attendance_events",
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
                        ("GET", f"{API}/archivos/clonexa/{'a' * 32}.png?e=1&s=x"), ("PUT", f"{API}/pisos/orden"), ("PUT", f"{API}/pisos/{VELVET}")]:
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
def test_editor_guarda_recarga_y_rechaza_archivos_falsos(client, pg_url, monkeypatch):
    _session(monkeypatch)
    _seed(pg_url)
    r = client.put(f"{API}/personajes", json={"clave": "agente:ventas", "nombre": "Nexa Ventas Pro", "estilo": "lego", "color_ropa": "#112233"})
    assert r.status_code == 200, r.text
    items = client.get(f"{API}/personajes").json()["items"]
    saved = next(i for i in items if i["clave"] == "agente:ventas")
    assert saved["nombre"] == "Nexa Ventas Pro" and saved["estilo"] == "lego" and saved["color_ropa"] == "#112233" and saved["company_id"] is None
    assert client.put(f"{API}/personajes", json={"clave": "agente:ventas", "estilo": "anime"}).json()["item"]["nombre"] == "Nexa Ventas Pro"
    assert client.put(f"{API}/personajes", json={"clave": "rep", "company_id": VELVET, "nombre": "Rep. Velvet"}).status_code == 200
    assert client.put(f"{API}/personajes", json={"clave": "rep", "company_id": DEMO, "nombre": "x"}).status_code == 404, "solo registradas"
    assert client.put(f"{API}/personajes", json={"clave": "rep", "nombre": "x"}).status_code == 422
    assert client.put(f"{API}/personajes", json={"clave": "agente:batman", "nombre": "x"}).status_code == 404
    url = f"{API}/personajes/archivo?clave=agente:ventas&tipo=cara"
    assert client.post(url, content=b"<svg onload=alert(1)>", headers={"Content-Type": "image/png"}).status_code == 415
    assert client.post(url, content=b"\x89PNG\r\n\x1a\n" + b"\0" * (2 * 1024 * 1024)).status_code == 413
    assert client.post(f"{API}/personajes/archivo?clave=agente:ventas&tipo=modelo", content=b"\x89PNG\r\n\x1a\n" + b"\0" * 50).status_code == 415
    assert not client.bucket.objects, "nada rechazado llega al bucket"
    png = b"\x89PNG\r\n\x1a\n" + b"\0" * 200
    r = client.post(url, content=png, headers={"Content-Type": "image/png"})
    assert r.status_code == 200, r.text
    link = r.json()["item"]["cara_url"]
    assert link.startswith(f"{API}/archivos/clonexa/") and "?e=" in link
    key = next(iter(client.bucket.objects))
    assert key.startswith("oficina/clonexa/") and key.endswith(".png") and client.bucket.objects[key] == png
    got = client.get(link)
    assert got.status_code == 200 and got.content == png and got.headers["content-type"] == "image/png"
    assert client.get(link.split("&s=")[0] + "&s=" + "0" * 32).status_code == 404, "firma mala"
    stored = _run(pg_url, "SELECT cara_key, archivos_bytes FROM oficina_personajes WHERE clave = 'agente:ventas'")[0]
    assert stored["cara_key"] == key and stored["archivos_bytes"] == len(png)
    assert client.delete(url).status_code == 200 and not client.bucket.objects


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
