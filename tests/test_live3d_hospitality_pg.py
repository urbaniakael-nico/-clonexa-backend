"""NEGOCIO EN VIVO 3D (modulo live3d) contra Postgres REAL (pgserver) y la app completa.

- Migracion 025o aditiva e idempotente: modulo en el catalogo, encendido SOLO en The Time Machine.
- Modulo apagado: el panel no trae la tarjeta y el acceso da 403. Encendido: el visor abre SOLO su piso.
- Prueba cruzada: la empresa A nunca ve datos ni recursos de B (ni con su cookie ni con su token).
- Rol fuera de "Quien lo ve": 403; con "roles elegidos", el rol elegido entra.
- 401/403 en el visor y sus recursos (motor, three, CC0, Mixamo, copia viva) sin sesion o con el modulo apagado.
- Copia viva COMPARTIDA: N pantallas de la misma empresa = 1 construccion (consulta) por TTL; consumo cuenta
  pantallas y bytes.
- Modo arquitecto por empresa (pisos aprobados) guarda y recarga; acomodar automatico; tarjeta de la consola
  (una sola fuente con la Oficina 3D) con auditoria; modo TV y modo liviano llegan al visor.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from types import SimpleNamespace

import pytest

pytest.importorskip("pgserver")

from fastapi import HTTPException  # noqa: E402

from tests.test_oficina_hospitality_pg import (  # noqa: E402,F401
    API, TTM, VELVET, ASADERO, _migration, _run, _seed, _session, client, pg_url,
)
from tests.test_oficina_hospitality_pg import _upload_bar  # noqa: E402
from app.services import auth_service  # noqa: E402
from app.services import live3d as l3  # noqa: E402
from app.web import live3d_routes  # noqa: E402

EXTRA = """
ALTER TABLE modules ADD COLUMN IF NOT EXISTS description text;
ALTER TABLE modules ADD COLUMN IF NOT EXISTS is_active boolean DEFAULT true;
ALTER TABLE modules ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now();
ALTER TABLE modules ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();
ALTER TABLE company_modules ADD COLUMN IF NOT EXISTS activated_at timestamptz;
ALTER TABLE company_modules ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now();
ALTER TABLE company_modules ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();
CREATE TABLE IF NOT EXISTS company_users (id uuid PRIMARY KEY, company_id uuid NOT NULL, role varchar(64) NOT NULL, status varchar(32) NOT NULL DEFAULT 'active')
"""
USERS = {}


@pytest.fixture
def db(pg_url, client, monkeypatch):
    for stmt in [s for s in EXTRA.split(";") if s.strip()]:
        _run(pg_url, stmt)
    _run(pg_url, "CREATE TABLE IF NOT EXISTS oficina_ajustes (clave varchar(40) PRIMARY KEY, valor varchar(40) NOT NULL DEFAULT '', updated_at timestamptz NOT NULL DEFAULT now())")
    _run(pg_url, "DELETE FROM company_users")
    _seed(pg_url)
    for _ in range(2):   # aditiva e idempotente
        for stmt in _migration("025o_live3d"):
            _run(pg_url, stmt)
    _run(pg_url, "DELETE FROM live3d_consumo")
    USERS.clear()

    async def fake_user(db_, token):
        u = USERS.get(token)
        if not u:
            raise HTTPException(status_code=401, detail="Token inválido.")
        return u
    monkeypatch.setattr(auth_service, "get_current_company_user", fake_user)
    l3.reset()
    _session(monkeypatch, False)
    return pg_url


def _user(url, cid, role, token):
    uid = str(uuid.uuid4())
    _run(url, "INSERT INTO company_users (id, company_id, role, status) VALUES (CAST(:i AS uuid), CAST(:c AS uuid), :r, 'active')", {"i": uid, "c": cid, "r": role})
    USERS[token] = SimpleNamespace(id=uuid.UUID(uid), company_id=uuid.UUID(cid), role=role, settings_json={})
    return uid


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _enter(client, cid, token):
    """Panel -> acceso (ticket) -> cookie -> visor. Devuelve la raiz firmada del visor."""
    r = client.get(f"/api/v1/live3d/companies/{cid}/acceso", headers=_bearer(token))
    assert r.status_code == 200, r.text
    r2 = client.get(r.json()["url"], follow_redirects=False)
    assert r2.status_code == 303, r2.text
    root = r2.headers["location"]
    assert root.startswith(f"/panel/negocio-en-vivo/r/{cid}/")
    return root


def test_migracion_modulo_solo_en_ttm(client, db):
    rows = _run(db, "SELECT c.id::text AS id, cm.enabled FROM company_modules cm JOIN modules m ON m.id = cm.module_id JOIN companies c ON c.id = cm.company_id WHERE m.code = 'live3d'")
    assert rows == [{"id": TTM, "enabled": True}], "solo The Time Machine (piloto)"
    mod = _run(db, "SELECT category, name FROM modules WHERE code = 'live3d'")
    assert mod == [{"category": "Complementos", "name": "Negocio en vivo 3D"}]
    assert _run(db, "SELECT count(*) AS n FROM modules WHERE code = 'live3d'")[0]["n"] == 1, "idempotente"


def test_apagado_403_y_sin_tarjeta(client, db):
    _user(db, VELVET, "company_admin", "velvet-owner")
    r = client.get(f"/api/v1/live3d/companies/{VELVET}/panel", headers=_bearer("velvet-owner"))
    assert r.status_code == 200 and r.json()["live3d"] is None and r.json()["classic"] is False, "la tarjeta 3D no aparece"
    assert client.get(f"/api/v1/live3d/companies/{VELVET}/acceso", headers=_bearer("velvet-owner")).status_code == 403
    assert client.get(f"/panel/negocio-en-vivo?company_id={VELVET}", follow_redirects=False).status_code == 401
    assert client.get(f"/api/v1/live3d/companies/{VELVET}/panel").status_code == 401, "nunca sin sesion"


def test_encendido_abre_solo_su_piso_con_todo_protegido(client, db):
    _upload_bar(client.bucket)
    _user(db, TTM, "company_admin", "ttm-owner")
    info = client.get(f"/api/v1/live3d/companies/{TTM}/panel", headers=_bearer("ttm-owner")).json()
    assert info["live3d"]["noun"] == "bar"
    root = _enter(client, TTM, "ttm-owner")
    page = client.get(root)
    assert page.status_code == 200 and "script-src 'self' 'sha256-" in page.headers["content-security-policy"]
    assert f'"/admin-v2plus/oficina/":"{root}"' in page.text, "los motores salen de la ruta firmada de su empresa"
    piso = client.get(root + "api/piso").json()
    assert piso["floor"]["company_id"] == TTM and piso["floor"]["name"] == "The Time Machine" and piso["admin"] is False
    assert piso["tv"] is True and piso["lite"] is None, "modo TV permitido y liviano automatico por defecto"
    vivo = client.get(root + f"api/pisos/{TTM}/vivo?s=pantalla00001")
    assert vivo.status_code == 200 and vivo.json()["template"] == "bar"
    body = vivo.text
    for other in ("Velvet", "ASADERO", "VOLTAGE", VELVET, ASADERO):
        assert other not in body, "nada de otras empresas"
    for path in ("bar.js", "mixamo.js", "vivo3d.js", "arquitecto.js", "vendor/three/build/three.module.js", "recursos/manifest.json", "bar/manifest.json",
                 "bar/animaciones/Idle.glb"):
        assert client.get(root + path).status_code == 200, path
    for admin_only in ("app.js", "clonexa.js", "recepcion.js"):
        assert client.get(root + admin_only).status_code == 404, "ni el edificio, ni Clonexa, ni la recepcion"
    # sin la cookie del visor: todo 401
    client.cookies.clear()
    for path in ("", "api/piso", f"api/pisos/{TTM}/vivo", "bar.js", "vendor/three/build/three.module.js", "recursos/manifest.json", "bar/animaciones/Idle.glb"):
        r = client.get(root + path)
        assert r.status_code == 401, (path, r.status_code)
        assert b"glTF" not in r.content


def test_prueba_cruzada_a_nunca_ve_b(client, db):
    _upload_bar(client.bucket)
    _user(db, TTM, "company_admin", "ttm-owner")
    _user(db, VELVET, "company_admin", "velvet-owner")
    # token de Velvet pidiendo el piso de TTM
    assert client.get(f"/api/v1/live3d/companies/{TTM}/acceso", headers=_bearer("velvet-owner")).status_code == 403
    root = _enter(client, TTM, "ttm-owner")
    # la cookie de TTM no sirve para la copia viva ni el logo de otra empresa
    assert client.get(root + f"api/pisos/{VELVET}/vivo").status_code == 403
    assert client.get(root + f"api/marca/{VELVET}/logo").status_code == 403
    # la ruta firmada de TTM con el id de Velvet: firma mala -> 404; la de Velvet sin su cookie -> 401
    sig = root.rstrip("/").split("/")[-1]
    assert client.get(f"/panel/negocio-en-vivo/r/{VELVET}/{sig}/api/piso").status_code == 404
    assert client.get(live3d_routes.root_of(VELVET) + "api/piso").status_code == 401
    personajes = client.get(root + "api/personajes").json()["items"]
    assert all(x["company_id"] in (TTM, None) for x in personajes)


def test_rol_fuera_de_quien_lo_ve_403_y_roles_elegidos(client, db, monkeypatch):
    _user(db, TTM, "mesero", "ttm-mesero")
    _user(db, TTM, "administrador", "ttm-admin")
    assert client.get(f"/api/v1/live3d/companies/{TTM}/acceso", headers=_bearer("ttm-mesero")).status_code == 403
    assert client.get(f"/api/v1/live3d/companies/{TTM}/acceso", headers=_bearer("ttm-admin")).status_code == 200, "dueño y administradores (por defecto)"
    _session(monkeypatch, True)
    r = client.put(f"/admin-v2/api/companies/{TTM}/live3d", json={"audience": "dueno"})
    assert r.status_code == 200 and r.json()["audience"] == "dueno"
    _session(monkeypatch, False)
    assert client.get(f"/api/v1/live3d/companies/{TTM}/acceso", headers=_bearer("ttm-admin")).status_code == 403, "solo el dueño"
    _session(monkeypatch, True)
    assert client.put(f"/admin-v2/api/companies/{TTM}/live3d", json={"audience": "roles", "roles": ["Mesero"]}).status_code == 200
    _session(monkeypatch, False)
    assert client.get(f"/api/v1/live3d/companies/{TTM}/acceso", headers=_bearer("ttm-mesero")).status_code == 200
    assert client.get(f"/api/v1/live3d/companies/{TTM}/acceso", headers=_bearer("ttm-admin")).status_code == 403


def test_apagar_corta_el_visor_abierto(client, db, monkeypatch):
    _user(db, TTM, "company_admin", "ttm-owner")
    root = _enter(client, TTM, "ttm-owner")
    assert client.get(root + "api/piso").status_code == 200
    _session(monkeypatch, True)
    r = client.put(f"/admin-v2/api/companies/{TTM}/live3d", json={"enabled": False})
    assert r.status_code == 200 and r.json()["enabled"] is False
    _session(monkeypatch, False)
    assert client.get(root + "api/piso").status_code == 403
    assert client.get(root + f"api/pisos/{TTM}/vivo").status_code == 403
    assert client.get(f"/panel/negocio-en-vivo?company_id={TTM}", follow_redirects=False).status_code == 403
    assert client.get(f"/api/v1/live3d/companies/{TTM}/panel", headers=_bearer("ttm-owner")).json()["live3d"] is None


def test_copia_viva_compartida_y_consumo(client, db, monkeypatch):
    _user(db, TTM, "company_admin", "ttm-owner")
    root = _enter(client, TTM, "ttm-owner")
    for i in range(6):   # 6 pantallas de la misma empresa
        assert client.get(root + f"api/pisos/{TTM}/vivo?s=pantalla{i:05d}").status_code == 200
    assert l3.STATS[TTM]["builds"] == 1, "N pantallas = 1 consulta por TTL"
    # la oficina de la consola usa la MISMA copia (no consulta otra vez)
    _session(monkeypatch, True)
    assert client.get(f"{API}/pisos/{TTM}/vivo").status_code == 200
    assert l3.STATS[TTM]["builds"] == 1
    # vencido el TTL: una sola consulta nueva
    l3._LIVE[TTM] = (l3._LIVE[TTM][0] - l3.LIVE_TTL - 1, l3._LIVE[TTM][1])
    for i in range(3):
        client.get(root + f"api/pisos/{TTM}/vivo?s=pantalla{i:05d}")
    assert l3.STATS[TTM]["builds"] == 2
    card = client.get(f"/admin-v2/api/companies/{TTM}/live3d").json()
    assert card["usage"]["screens"] == 6 and card["usage"]["month_bytes"] > 0
    asyncio.run(_flush(db))
    saved = _run(db, "SELECT bytes, pantallas_max FROM live3d_consumo WHERE company_id = CAST(:c AS uuid)", {"c": TTM})
    assert saved and saved[0]["bytes"] > 0 and saved[0]["pantallas_max"] == 6, "medido de verdad y guardado por mes"


async def _flush(url):
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(url, poolclass=NullPool)
    async with AsyncSession(engine) as s:
        await l3.flush(s, TTM, force=True)
    await engine.dispose()


def test_copia_viva_concurrente_una_sola_construccion():
    l3.reset()
    calls = []

    async def build():
        calls.append(1)
        await asyncio.sleep(0.05)
        return {"rev": "x"}

    async def go():
        return await asyncio.gather(*[l3.shared_live("c1", build) for _ in range(10)])
    out = asyncio.run(go())
    assert len(calls) == 1 and all(o == {"rev": "x"} for o in out)


def test_arquitecto_por_empresa_guarda_recarga_y_acomoda(client, db, monkeypatch):
    _session(monkeypatch, True)
    _run(db, "INSERT INTO hospitality_table_access (company_id, table_key, table_number, status) VALUES (CAST(:c AS uuid), 'mesa-1', 'Mesa 1', 'closed')", {"c": TTM})
    body = {"items": {"dj": [5.0, -4.0, 1.57], "pista": [3.0, -3.0, 0], "planta:1": [-6.0, 4.0, 0]}}
    r = client.put(f"{API}/pisos/{TTM}/distribucion", json=body)
    assert r.status_code == 200, r.text
    vivo = client.get(f"{API}/pisos/{TTM}/vivo").json()
    assert vivo["arch"]["dj"] == [5.0, -4.0, 1.57] and vivo["arch"]["planta:1"] == [-6.0, 4.0, 0.0]
    assert client.put(f"{API}/pisos/{TTM}/distribucion", json={"items": {"maquina:1": [0, 0, 0]}}).status_code == 422, "objetos de otro piso"
    assert client.put(f"{API}/pisos/{TTM}/distribucion", json={"items": {"dj": [1e9, 0, 0]}}).json()["arch"]["dj"][0] == l3.ARCH_LIMIT
    assert client.delete(f"{API}/pisos/{TTM}/distribucion").status_code == 200
    assert client.get(f"{API}/pisos/{TTM}/vivo").json()["arch"] == {}, "acomodar automatico"


def test_tarjeta_de_la_consola_una_sola_fuente(client, db, monkeypatch):
    _session(monkeypatch, False)
    assert client.get(f"/admin-v2/api/companies/{TTM}/live3d").status_code == 401
    assert client.put(f"/admin-v2/api/companies/{TTM}/live3d", json={"tv": False}).status_code == 401
    assert client.get("/admin-v2plus-live3d.js").status_code == 401
    _session(monkeypatch, True)
    from app.services import admin_audit

    audit = []
    monkeypatch.setattr(admin_audit, "attach_detail", lambda request, **d: audit.append(d))
    card = client.get(f"/admin-v2/api/companies/{TTM}/live3d").json()
    assert card["enabled"] is True and card["template"] == "bar" and card["has_engine"] is True and card["privacy"] == "nombre"
    assert [o["key"] for o in card["options"]["templates"]] == ["taller", "restaurante", "bar", "campo", "general"]
    r = client.put(f"/admin-v2/api/companies/{TTM}/live3d", json={"privacidad": "cargo", "tv": False, "lite": "siempre"})
    assert r.status_code == 200 and r.json()["privacy"] == "cargo" and r.json()["tv"] is False and r.json()["lite"] == "siempre"
    estado = client.get(f"{API}/estado").json()
    assert next(f for f in estado["floors"] if f["company_id"] == TTM)["privacy"] == "cargo", "la Oficina 3D usa la misma fila"
    assert client.put(f"/admin-v2/api/companies/{TTM}/live3d", json={"plantilla": "nada"}).status_code == 422
    assert client.put(f"/admin-v2/api/companies/{TTM}/live3d", json={"roles": ["<script>"]}).status_code == 422
    # Velvet: encender desde la tarjeta deja su piso con motor aprobado
    r = client.put(f"/admin-v2/api/companies/{VELVET}/live3d", json={"enabled": True})
    assert r.json()["enabled"] is True and r.json()["has_engine"] is True and r.json()["style"] == "aprobado"
    abrir = client.post(f"/admin-v2/api/companies/{TTM}/live3d/abrir")
    assert abrir.status_code == 200 and abrir.json()["url"].startswith("/panel/negocio-en-vivo/v/")
    # "Abrir como el cliente": exactamente el visor del cliente (modo TV y liviano de la tarjeta)
    root = client.get(abrir.json()["url"], follow_redirects=False).headers["location"]
    piso = client.get(root + "api/piso").json()
    assert piso["admin"] is True and piso["tv"] is False and piso["lite"] == "1"
    assert {"live3d": VELVET, "encendido": "si", "campos": "estilo"} in audit, "interruptor con auditoria"
    assert any(a.get("live3d") == TTM and "privacidad" in a.get("campos", "") for a in audit)


def test_vista_previa_al_bucket_no_a_postgres(client, db):
    _user(db, TTM, "company_admin", "ttm-owner")
    root = _enter(client, TTM, "ttm-owner")
    assert client.post(root + "api/vista", content=b"no es jpeg").status_code == 422
    jpeg = b"\xff\xd8\xff\xe0" + b"0" * 2000
    assert client.post(root + "api/vista", content=jpeg).json() == {"ok": True}
    assert client.post(root + "api/vista", content=jpeg).json().get("skipped") is True, "a lo sumo una cada 10 min"
    assert l3.preview_key(TTM) in client.bucket.objects, "bucket privado"
    r = client.get(f"/api/v1/live3d/companies/{TTM}/vista.jpg", headers=_bearer("ttm-owner"))
    assert r.status_code == 200 and r.content == jpeg


def test_firmas():
    secret = b"s" * 32
    t = l3.sign(secret, "ticket", {"c": TTM, "k": "c", "u": "x", "e": 9999999999})
    assert l3.verify(secret, "ticket", t)["c"] == TTM
    assert l3.verify(secret, "cookie", t) is None, "un ticket no sirve como cookie"
    assert l3.verify(b"o" * 32, "ticket", t) is None
    assert l3.verify(secret, "ticket", t[:-2] + "aa") is None
    assert l3.verify(secret, "ticket", l3.sign(secret, "ticket", {"c": TTM, "k": "c", "e": 1})) is None, "vencido"
    assert l3.role_allowed("company_admin", "dueno", []) and not l3.role_allowed("administrador", "dueno", [])
    assert l3.role_allowed("Administrador", "dueno_admin", []) and not l3.role_allowed("mesero", "dueno_admin", [])
    assert l3.role_allowed("mesero", "roles", ["mesero"]) and l3.link_sig(secret, TTM) != l3.link_sig(secret, VELVET)
    assert json.dumps(l3.clean_arch({"items": {"mesa:Mesa 1": [1, 2, 3]}}, "bar", ["Mesa 1"]))
