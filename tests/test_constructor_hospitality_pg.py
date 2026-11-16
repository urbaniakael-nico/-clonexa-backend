"""BIBLIOTECA 3D (Modo constructor + Personajes, prototipo aprobado) contra Postgres REAL (pgserver) y la app completa.

- 401 sin sesión en páginas (al ingreso), módulos, API y archivos; las rutas viejas de la fase 1 redirigen.
- Empresa A nunca ve ni edita diseños, personajes ni uniformes de B; el visor del cliente solo su plano publicado.
- Planos de la fase 1 convertidos al JSON del prototipo (migración 025v, aditiva e idempotente).
- Diseños por empresa: autoguardado con validación estricta, miniatura al bucket (no a Postgres), publicar en vivo,
  versiones y restaurar, borrar; importar .clonexa.json validado en el servidor.
- Equipo = Personal real + personaje en oficina_personajes (sin duplicar); uniformes; "Aplicar Estudio de marca".
- Conexiones: solo entidades reales de ESA empresa, una entidad -> un objeto, del tipo correcto.
- Biblioteca: GLB, OBJ, ZIP y FBX se convierten en el servidor y quedan en revisión; aprobados entran al catálogo.
"""
from __future__ import annotations

import base64
import importlib
import io
import json
import struct
import zipfile

import numpy as np
import pytest

pytest.importorskip("pgserver")

from tests.test_oficina_hospitality_pg import API, TTM, VELVET, ASADERO, NUEVA, _employee, _qr_tables, _run, _session, client, pg_url  # noqa: E402,F401
from tests.test_live3d_hospitality_pg import USERS, _enter, _user, db  # noqa: E402,F401
from app.services import constructor_glb as cg  # noqa: E402
from app.services import constructor_v2 as c2  # noqa: E402
from app.web import oficina_routes  # noqa: E402

B = "/admin-v2/api/b3d"
JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 200).decode()


class _Op:
    def __init__(self, url):
        self.url = url

    def execute(self, sql):
        _run(self.url, str(sql))

    def get_bind(self):
        url = self.url

        class Bind:
            def execute(self, clause, params=None):
                return _run(url, str(clause), params or {})
        return Bind()


def _migrate(url, name):
    mod = importlib.import_module(f"migrations.versions.{name}")
    mod.op = _Op(url)
    mod.upgrade()


@pytest.fixture
def cdb(db, monkeypatch):
    _migrate(db, "025u_constructor")
    for _ in range(2):   # aditiva e idempotente
        _migrate(db, "025v_biblioteca3d")
    for t in ("constructor_planos", "constructor_uniformes"):
        _run(db, f"DELETE FROM {t}")
    _run(db, "DELETE FROM constructor_catalogo WHERE origen = 'bucket'")
    _run(db, "CREATE TABLE IF NOT EXISTS inventory_items (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, sku text, name text, category text, current_stock numeric DEFAULT 0, min_stock numeric DEFAULT 0, status text DEFAULT 'active')")
    _run(db, "DELETE FROM inventory_items")
    _session(monkeypatch, True)
    oficina_routes.reset_cache()
    return db


def _plan(**over):
    p = {"name": "Mi bar", "room": {"w": 14, "d": 10, "h": 3.4}, "floor": {"mat": "madera_oscura", "color": "#5b3a26"},
         "walls": {k: {"mat": "ladrillo", "color": "#8a4130"} for k in "nsew"}, "openings": [{"id": "a1", "wall": "s", "pos": .5, "type": "puerta"}],
         "objects": [{"id": "o1", "item": "mesa_redonda", "x": -2, "z": 1, "rot": 0, "conn": "mesa:Mesa 1"},
                     {"id": "o2", "item": "neon", "x": 0, "z": -4.88, "rot": 0, "text": "Hola", "color": "#ff2d95"},
                     {"id": "o3", "item": "tv_pared", "x": 2, "z": -4.88, "rot": 0, "screen": "Canciones pedidas", "conn": "pantalla:canciones"},
                     {"id": "o4", "item": "sofa", "x": 4, "z": 3, "rot": 180}],
         "people": []}
    p.update(over)
    return p


def _state(client, cid):
    r = client.get(f"{B}/empresas/{cid}")
    assert r.status_code == 200, r.text
    return r.json()


def _save(client, cid, did, plan, **extra):
    return client.put(f"{B}/empresas/{cid}/disenos/{did}", json={"name": plan.get("name"), "plan": plan, **extra})


# ------------------------------------------------------------------ seguridad
def test_sin_sesion_todo_401_y_paginas_al_ingreso(client, cdb, monkeypatch):
    _session(monkeypatch, False)
    for path in ("/admin-v2plus/biblioteca3d/", "/admin-v2plus/biblioteca3d/constructor", "/admin-v2plus/biblioteca3d/personajes",
                 "/admin-v2plus/biblioteca3d", "/admin-v2plus/constructor", "/admin-v2plus/constructor/vista", "/admin-v2plus/biblioteca", "/admin-v2plus/creditos-3d"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/admin-v2plus/login", path
    for name in ("core.js", "store.js", "editor.js", "people.js", "home.js", "char.js", "app.css"):
        assert client.get(f"/admin-v2plus/oficina/b3d/{name}").status_code == 401, name
    assert client.get("/admin-v2plus/oficina/plano.js").status_code == 401
    calls = [("get", f"{B}/empresas"), ("get", f"{B}/empresas/{TTM}"), ("put", f"{B}/empresas/{TTM}/estilo"), ("put", f"{B}/empresas/{TTM}/disenos/d1"),
             ("delete", f"{B}/empresas/{TTM}/disenos/d1"), ("post", f"{B}/empresas/{TTM}/disenos/d1/publicar"), ("get", f"{B}/empresas/{TTM}/disenos/d1/versiones"),
             ("get", f"{B}/empresas/{TTM}/disenos/d1/versiones/1"), ("get", f"{B}/empresas/{TTM}/disenos/d1/miniatura.jpg"), ("post", f"{B}/empresas/{TTM}/importar"),
             ("put", f"{B}/empresas/{TTM}/equipo/abcdefabcdef"), ("put", f"{B}/empresas/{TTM}/uniformes"), ("post", f"{B}/empresas/{TTM}/aplicar-marca"),
             ("post", f"{B}/biblioteca/subir"), ("post", f"{B}/biblioteca/x_y/aprobar"), ("get", f"{API}/catalogo/sub_x.glb"), ("get", f"{API}/pisos/{TTM}/plano")]
    for method, path in calls:
        r = getattr(client, method)(path)
        assert r.status_code == 401, (method, path, r.status_code)
    assert _run(cdb, "SELECT count(*) AS n FROM constructor_planos")[0]["n"] == 0, "nada se crea sin sesión"


def test_paginas_con_sesion_rutas_viejas_y_csp(client, cdb):
    r = client.get("/admin-v2plus/biblioteca3d/")
    assert r.status_code == 200 and "Biblioteca 3D" in r.text and "unsafe-inline" in r.headers["content-security-policy"].split("style-src")[1].split(";")[0]
    assert "script-src 'self' 'sha256-" in r.headers["content-security-policy"] and "'unsafe-inline'" not in r.headers["content-security-policy"].split("script-src")[1].split(";")[0]
    for page in ("constructor", "personajes"):
        html = client.get(f"/admin-v2plus/biblioteca3d/{page}").text
        assert "onclick=" not in html and "/admin-v2plus/oficina/b3d/" in html, page
    r = client.get(f"/admin-v2plus/constructor?empresa={TTM}", follow_redirects=False)
    assert r.headers["location"] == f"/admin-v2plus/biblioteca3d/constructor?empresa={TTM}"
    assert client.get("/admin-v2plus/biblioteca", follow_redirects=False).headers["location"] == "/admin-v2plus/biblioteca3d/constructor?lib=1"
    assert client.get("/admin-v2plus/oficina/b3d/editor.js").status_code == 200
    assert client.get("/admin-v2plus/oficina/b3d/../oficina_routes.py").status_code == 404
    assert client.get("/admin-v2plus/oficina/vendor/three/examples/jsm/controls/OrbitControls.js").status_code == 200


# ------------------------------------------------------------------ empresas, estilo y diseños
def test_empresas_con_marca_y_estado_por_empresa(client, cdb):
    _qr_tables(cdb, TTM, 6)
    items = client.get(f"{B}/empresas").json()["items"]
    ttm = next(x for x in items if x["id"] == TTM)
    assert len(ttm["brand"]) == 4 and all(c.startswith("#") for c in ttm["brand"]) and ttm["neon"]
    st = _state(client, TTM)
    assert st["style"] == "human" and st["designs"] == []
    assert [e["id"] for e in st["entities"]["mesa"]] == [f"mesa:Mesa {i}" for i in range(1, 7)], "mesas QR reales"
    assert [u["name"] for u in st["uniforms"]] == ["Barra", "Caja", "Cocina", "Salón"], "la primera vez: los 4 uniformes del prototipo"
    assert client.put(f"{B}/empresas/{TTM}/estilo", json={"style": "toon"}).json()["style"] == "toon"
    assert _state(client, TTM)["style"] == "toon" and _state(client, VELVET)["style"] == "human", "estilo por empresa"
    assert client.put(f"{B}/empresas/{TTM}/estilo", json={"style": "sims"}).status_code == 422
    assert client.get(f"{B}/empresas/00000000-0000-0000-0000-000000000000").status_code == 404


def test_autoguardado_validacion_publicar_versiones_y_borrar(client, cdb):
    _qr_tables(cdb, TTM, 6)
    r = _save(client, TTM, "d1", _plan(), thumb=JPEG)
    assert r.status_code == 200, r.text
    assert r.json()["thumb"].startswith(f"{B}/empresas/{TTM}/disenos/d1/miniatura.jpg")
    key = _run(cdb, "SELECT miniatura FROM constructor_planos WHERE diseno_id = 'd1'")[0]["miniatura"]
    assert key.startswith(f"constructor/miniaturas/{TTM}/") and key in client.bucket.objects, "miniatura al bucket privado, no a Postgres"
    assert client.get(r.json()["thumb"]).content[:3] == b"\xff\xd8\xff"
    bad = [_plan(objects=[{"id": "x", "item": "dragon", "x": 0, "z": 0, "rot": 0}]),
           _plan(objects=[{"id": "x", "item": "sofa", "x": 0, "z": 0, "rot": 0, "hack": 1}]),
           _plan(objects=[{"id": "x", "item": "sofa", "x": 0, "z": 0, "rot": 0, "conn": "mesa:Mesa 1"}]),
           _plan(objects=[{"id": "x", "item": "mesa_2", "x": 0, "z": 0, "rot": 0, "conn": "mesa:Mesa 1"}, {"id": "y", "item": "mesa_alta", "x": 2, "z": 0, "rot": 0, "conn": "mesa:Mesa 1"}]),
           _plan(objects=[{"id": "x", "item": "mesa_2", "x": 0, "z": 0, "rot": 0, "conn": "caja:caja-1"}]),
           _plan(room={"w": 400, "d": 10, "h": 3}), _plan(inner=[{"id": "m", "x1": 0, "z1": 0, "x2": 3, "z2": 0, "kind": "torre"}]),
           _plan(inner=[{"id": "m", "x1": 0, "z1": 0, "x2": 3, "z2": 0, "kind": "alto", "door": {"pos": .5, "width": .9, "type": "portal"}}]), _plan(floor={"mat": "oro", "color": "#ffffff"}), _plan(people=[{"id": "p", "pid": "Laura", "x": 0, "z": 0, "rot": 0, "clip": "idle"}])]
    for b in bad:
        assert _save(client, TTM, "d1", b).status_code == 422, b["objects"][:1]
    assert client.put(f"{B}/empresas/{TTM}/disenos/d1", json={"plan": _plan(), "thumb": "data:image/jpeg;base64,PGh0bWw+"}).status_code == 422
    st = _state(client, TTM)
    assert [d["id"] for d in st["designs"]] == ["d1"] and st["designs"][0]["version"] == 0 and not st["designs"][0]["live"]
    assert st["designs"][0]["plan"]["objects"][0]["conn"] == "mesa:Mesa 1"
    muros = [{"id": "m1", "x1": -3, "z1": 0, "x2": 2, "z2": 0, "kind": "alto", "mat": "ladrillo", "color": "#8a4130", "door": {"pos": .3, "width": .9, "type": "puerta"}},
             {"id": "m2", "x1": 4, "z1": -4, "x2": 4, "z2": 0, "kind": "vidrio", "color": "#bfe6ff", "door": None},
             {"id": "m3", "x1": 0, "z1": 3, "x2": 3, "z2": 3, "kind": "media", "h": 1.1, "door": None}]
    assert _save(client, TTM, "d1", _plan(inner=muros)).status_code == 200
    assert [w["kind"] for w in _state(client, TTM)["designs"][0]["plan"]["inner"]] == ["alto", "vidrio", "media"], "campo inner guardado"
    # publicar en vivo: versión 1, interruptor de ESA empresa
    assert client.post(f"{B}/empresas/{TTM}/disenos/d1/publicar").json()["version"] == 1
    p2 = _plan(name="Mi bar 2")
    p2["objects"].append({"id": "o9", "item": "planta", "x": 5, "z": -3, "rot": 45})
    _save(client, TTM, "d1", p2)
    assert client.post(f"{B}/empresas/{TTM}/disenos/d1/publicar").json()["version"] == 2
    vs = client.get(f"{B}/empresas/{TTM}/disenos/d1/versiones").json()["items"]
    assert [v["n"] for v in vs] == [2, 1]
    v1 = client.get(f"{B}/empresas/{TTM}/disenos/d1/versiones/1").json()["plan"]
    assert len(v1["objects"]) == 4, "restaurar trae la versión 1"
    st = _state(client, TTM)
    assert st["designs"][0]["live"] and st["designs"][0]["version"] == 2
    row = _run(cdb, "SELECT usa_plano, plano_diseno FROM oficina_pisos WHERE company_id = CAST(:c AS uuid)", {"c": TTM})[0]
    assert row == {"usa_plano": True, "plano_diseno": "d1"}
    assert not _run(cdb, "SELECT 1 FROM oficina_pisos WHERE company_id = CAST(:c AS uuid) AND usa_plano", {"c": VELVET}), "solo la empresa que publicó"
    eng = client.get(f"{API}/pisos/{TTM}/plano").json()
    assert eng["version"] == 2 and len(eng["plano"]["objects"]) == 5 and eng["estilo"] == "humano"
    # segundo diseño y borrar el que está en vivo -> la empresa vuelve a su piso
    _save(client, TTM, "d2", _plan(name="Otro"))
    assert len(_state(client, TTM)["designs"]) == 2
    assert client.delete(f"{B}/empresas/{TTM}/disenos/d1").status_code == 200
    assert client.get(f"{API}/pisos/{TTM}/plano").status_code == 404
    assert [d["id"] for d in _state(client, TTM)["designs"]] == ["d2"]
    assert client.delete(f"{B}/empresas/{TTM}/disenos/d1").status_code == 404


def test_empresa_a_nunca_ve_ni_edita_lo_de_b(client, cdb):
    _qr_tables(cdb, TTM, 3)
    _save(client, TTM, "solo-ttm", _plan())
    client.post(f"{B}/empresas/{TTM}/disenos/solo-ttm/publicar")
    assert _state(client, VELVET)["designs"] == []
    assert client.get(f"{B}/empresas/{VELVET}/disenos/solo-ttm/versiones").json()["items"] == []
    assert client.get(f"{B}/empresas/{VELVET}/disenos/solo-ttm/versiones/1").status_code == 404
    assert client.post(f"{B}/empresas/{VELVET}/disenos/solo-ttm/publicar").status_code == 404
    assert client.delete(f"{B}/empresas/{VELVET}/disenos/solo-ttm").status_code == 404
    assert client.get(f"{B}/empresas/{VELVET}/disenos/solo-ttm/miniatura.jpg").status_code == 404
    assert len(_state(client, TTM)["designs"]) == 1, "lo de TTM sigue intacto"
    # personajes y uniformes por empresa
    e = _employee(cdb, TTM, "Laura Marcela Gómez", "cajera")
    pid = c2.person_key(e)
    look = {"toon": {"hair": "afro", "hairColor": "#141414"}, "human": {"base": "Ch22_nonPBR", "topColor": "#f20b6d", "topStyle": "liso"}, "uniform": None, "custom": True, "area": "Caja"}
    assert client.put(f"{B}/empresas/{TTM}/equipo/{pid}", json=look).status_code == 200
    assert not [p for p in _state(client, VELVET)["team"] if p["id"] == pid]
    client.put(f"{B}/empresas/{TTM}/uniformes", json={"items": [{"id": "u-x", "name": "Solo TTM", "desc": "", "toon": {}, "human": {}}]})
    assert "Solo TTM" not in [u["name"] for u in _state(client, VELVET)["uniforms"]]
    # el conector de mesas de B no se puede usar en A (la entidad no existe en A): el motor la descarta
    p = _plan(objects=[{"id": "m", "item": "mesa_2", "x": 0, "z": 0, "rot": 0, "conn": "mesa:Mesa 99"}])
    _save(client, VELVET, "v1", p)
    client.post(f"{B}/empresas/{VELVET}/disenos/v1/publicar")
    assert "conn" not in client.get(f"{API}/pisos/{VELVET}/plano").json()["plano"]["objects"][0]


# ------------------------------------------------------------------ equipo, personajes y uniformes
def test_equipo_real_personaje_sin_duplicar_y_privacidad(client, cdb):
    e1 = _employee(cdb, TTM, "Andrés Felipe Pérez", "barman")
    _employee(cdb, TTM, "Sofía Ramírez", "mesera")
    # personaje del editor viejo: se conserva en el nuevo
    _run(cdb, "INSERT INTO oficina_personajes (company_id, clave, color_ropa, personaje, genero) VALUES (CAST(:c AS uuid), :k, '#112233', 'Ch06_nonPBR', 'hombre')",
         {"c": TTM, "k": "persona:" + c2.person_key(e1)})
    team = {p["name"]: p for p in _state(client, TTM)["team"]}
    assert set(team) == {"Andrés F.", "Sofía R."}, "nombre corto con la privacidad actual"
    a = team["Andrés F."]
    assert a["area"] == "Barra" and a["shift"] == "Sin turno abierto" and a["real"]
    assert a["human"]["base"] == "Ch06_nonPBR" and a["human"]["topColor"] == "#112233", "migrado del editor viejo"
    look = {"toon": {**a["toon"], "beard": "corta"}, "human": {**a["human"], "topColor": "#00ff00", "acc": {"casco": True}}, "uniform": "u-barra", "custom": True,
            "area": "Barra", "name": a["name"]}
    assert client.put(f"{B}/empresas/{TTM}/equipo/{a['id']}", json=look).status_code == 200
    rows = _run(cdb, "SELECT look, color_ropa FROM oficina_personajes WHERE company_id = CAST(:c AS uuid) AND clave = :k", {"c": TTM, "k": "persona:" + a["id"]})
    assert len(rows) == 1 and rows[0]["color_ropa"] == "#00ff00", "misma fila, sin duplicar; el piso de siempre ve el color"
    assert rows[0]["look"]["human"]["acc"] == {}, "en Humano no hay accesorios sueltos"
    a2 = next(p for p in _state(client, TTM)["team"] if p["id"] == a["id"])
    assert a2["custom"] and a2["uniform"] == "u-barra" and a2["toon"]["beard"] == "corta"
    for bad in ({"toon": {"hair": "mohicano"}}, {"human": {"base": "Batman"}}, {"toon": {"x": 1}}, {"area": "Marte"}):
        assert client.put(f"{B}/empresas/{TTM}/equipo/{a['id']}", json=bad).status_code == 422, bad
    _run(cdb, "UPDATE oficina_pisos SET privacidad = 'cargo' WHERE company_id = CAST(:c AS uuid)", {"c": TTM})
    _run(cdb, "INSERT INTO oficina_pisos (company_id, privacidad) VALUES (CAST(:c AS uuid), 'cargo') ON CONFLICT (company_id) DO UPDATE SET privacidad = 'cargo'", {"c": TTM})
    assert "Mesera" in {p["name"] for p in _state(client, TTM)["team"]}, "con privacidad 'solo cargo' no sale el nombre"
    # Nuevo personaje (no ligado al Personal)
    assert client.put(f"{B}/empresas/{TTM}/equipo/0123456789ab", json={"name": "Nueva persona", "area": "Salón", "role": "Mesero/a", "toon": {}, "human": {}}).status_code == 200
    extra = next(p for p in _state(client, TTM)["team"] if p["id"] == "0123456789ab")
    assert not extra["real"] and extra["name"] == "Nueva persona"


def test_uniformes_y_aplicar_estudio_de_marca(client, cdb):
    from app.services import brand_theme as bt

    _run(cdb, """INSERT INTO company_brand_themes (company_id, status, tokens) VALUES (CAST(:c AS uuid), 'published', CAST(:t AS jsonb))""",
         {"c": TTM, "t": json.dumps(bt.make_tokens(bt.palette("#112233", "#445566", "#000000", "#fafafa")))})
    brand = next(x for x in client.get(f"{B}/empresas").json()["items"] if x["id"] == TTM)["brand"]
    assert brand[:2] == ["#112233", "#445566"], "colores reales del Estudio de marca"
    e = _employee(cdb, TTM, "Mateo Gil", "barman")
    pid = c2.person_key(e)
    client.put(f"{B}/empresas/{TTM}/equipo/{pid}", json={"toon": {"hair": "corto"}, "human": {"base": "Remy"}, "uniform": "u-barra", "custom": True, "area": "Barra"})
    plan = _plan(objects=[{"id": "n", "item": "neon", "x": 0, "z": -4.88, "rot": 0, "text": "x"}, {"id": "s", "item": "sofa", "x": 2, "z": 2, "rot": 0},
                          {"id": "c", "item": "caja", "x": -3, "z": 2, "rot": 0}, {"id": "b", "item": "barra_recta", "x": -5, "z": 0, "rot": 90}])
    _save(client, TTM, "d1", plan)
    client.post(f"{B}/empresas/{TTM}/disenos/d1/publicar")
    r = client.post(f"{B}/empresas/{TTM}/aplicar-marca")
    assert r.status_code == 200 and r.json()["objects"] == 4 and r.json()["uniforms"] == 4, r.text
    st = _state(client, TTM)
    objs = {o["id"]: o for o in st["designs"][0]["plan"]["objects"]}
    assert objs["n"]["color"] == "#112233" and objs["n"]["text"] == "The Time Machine"[:24]
    assert objs["s"]["color"] == "#445566" and objs["c"]["color"] == brand[2] and objs["b"]["color3"] == "#112233"
    assert st["uniforms"][0]["toon"]["topColor"] == "#112233" and st["uniforms"][1]["toon"]["topColor"] == "#445566"
    me = next(p for p in st["team"] if p["id"] == pid)
    assert me["toon"]["topColor"] == "#112233" and me["toon"]["hair"] == "corto", "uniforme: cambia la ropa, conserva el pelo"
    v1 = client.get(f"{B}/empresas/{TTM}/disenos/d1/versiones/1").json()["plan"]
    assert next(o for o in v1["objects"] if o["id"] == "n")["text"] == "x", "queda como cambio del borrador: se restaura en Versiones"
    assert client.put(f"{B}/empresas/{TTM}/uniformes", json={"items": [{"id": "u", "name": "", "toon": {}, "human": {}}]}).status_code == 422


# ------------------------------------------------------------------ fase 1 -> prototipo (migración 025v)
V1 = {"formato": "clonexa.plano", "version_esquema": 1, "sala": {"ancho": 20, "fondo": 10, "alto": 3.4},
      "paredes": [{"id": "w1", "x1": 0, "z1": 0, "x2": 20, "z2": 0, "grosor": .15, "alto": 3.4, "color": "#9a3b2e", "material": "ladrillo"},
                  {"id": "w2", "x1": 20, "z1": 0, "x2": 20, "z2": 10, "grosor": .15, "alto": 3.4, "color": "#d8cfc4", "material": "listones"},
                  {"id": "w3", "x1": 20, "z1": 10, "x2": 0, "z2": 10, "grosor": .15, "alto": 3.4, "color": "#d8cfc4", "material": "pintura"},
                  {"id": "w4", "x1": 0, "z1": 10, "x2": 0, "z2": 0, "grosor": .15, "alto": 3.4, "color": "#141018", "material": "panel_negro"},
                  {"id": "w5", "x1": 5, "z1": 0, "x2": 5, "z2": 4, "grosor": .1, "alto": 3.4, "color": "#ffffff", "material": "vidrio"}],
      "aberturas": [{"id": "a1", "pared": "w3", "tipo": "puerta_doble", "pos": 5, "ancho": 1.6, "alto": 2.2, "base": 0},
                    {"id": "a2", "pared": "w2", "tipo": "cortina_metalica", "pos": 2.5, "ancho": 3, "alto": 2.6, "base": 0}],
      "pisos": [{"id": "p", "zona": None, "puntos": [[0, 0], [20, 0], [20, 10], [0, 10]], "material": "baldosa_blanca", "color": "#eeeeee"}],
      "zonas": [], "objetos": [
          {"id": "o1", "asset": "mesa_redonda_4", "x": 4, "z": 6, "rot": 90, "escala": 1, "color": "#c47a3a", "variante": None, "capa": "muebles", "conexion": {"tipo": "mesa", "id": "Mesa 2"}, "texto": None},
          {"id": "o2", "asset": "escritorio_fila", "x": 12, "z": 5, "rot": 0, "escala": 1, "color": None, "variante": None, "capa": "muebles", "conexion": {"tipo": "escritorio", "id": "emp-1"}, "texto": None},
          {"id": "o3", "asset": "neon", "x": 10, "z": .1, "rot": 0, "escala": 1, "color": None, "variante": None, "capa": "pared", "conexion": None, "texto": "Night Bar"},
          {"id": "o4", "asset": "barril", "x": 2, "z": 2, "rot": 0, "escala": 1, "color": None, "variante": None, "capa": "muebles", "conexion": None, "texto": None},
          {"id": "o5", "asset": "montacargas", "x": 15, "z": 8, "rot": 0, "escala": 1, "color": None, "variante": None, "capa": "muebles", "conexion": None, "texto": None},
          {"id": "o6", "asset": "tv_pared", "x": 16, "z": .15, "rot": 0, "escala": 1, "color": None, "variante": None, "capa": "pared", "conexion": {"tipo": "pantalla", "id": "comandas"}, "texto": None}]}


def test_migracion_convierte_planos_de_la_fase_1(client, cdb):
    import uuid as _u
    _run(cdb, "INSERT INTO constructor_planos (id, company_id, version, estado, plano) VALUES (CAST(:i AS uuid), CAST(:c AS uuid), 1, 'publicado', CAST(:p AS jsonb))",
         {"i": str(_u.uuid4()), "c": ASADERO, "p": json.dumps(V1)})
    _run(cdb, "INSERT INTO constructor_planos (id, company_id, version, estado, plano) VALUES (CAST(:i AS uuid), CAST(:c AS uuid), 2, 'borrador', CAST(:p AS jsonb))",
         {"i": str(_u.uuid4()), "c": ASADERO, "p": json.dumps(V1)})
    _run(cdb, "INSERT INTO oficina_pisos (company_id, usa_plano) VALUES (CAST(:c AS uuid), TRUE) ON CONFLICT (company_id) DO UPDATE SET usa_plano = TRUE", {"c": ASADERO})
    for _ in range(2):
        _migrate(cdb, "025v_biblioteca3d")
    rows = _run(cdb, "SELECT diseno_id, plano FROM constructor_planos WHERE company_id = CAST(:c AS uuid)", {"c": ASADERO})
    assert {r["diseno_id"] for r in rows} == {"principal"}
    p = rows[0]["plano"]
    assert c2.clean_plan(p, {"barril": {}}) == p, "el plano convertido es un plano válido del prototipo"
    assert p["room"] == {"w": 20.0, "d": 10.0, "h": 3.4} and p["floor"]["mat"] == "baldosa"
    assert p["walls"]["n"]["mat"] == "ladrillo" and p["walls"]["e"]["mat"] == "madera" and p["walls"]["w"]["mat"] == "panel"
    ops = {o["type"]: o for o in p["openings"]}
    assert ops["puerta_doble"]["wall"] == "s" and ops["puerta_doble"]["pos"] == .75, "w3 va de derecha a izquierda"
    assert ops["cortina"]["wall"] == "e" and ops["cortina"]["pos"] == .25
    objs = {o["id"]: o for o in p["objects"]}
    assert objs["o1"]["item"] == "mesa_redonda" and (objs["o1"]["x"], objs["o1"]["z"]) == (-6.0, 1.0) and objs["o1"]["rot"] == 270.0
    assert objs["o1"]["conn"] == "mesa:Mesa 2" and objs["o2"]["conn"] == "emp:" + c2.person_key("emp-1")
    assert objs["o3"]["text"] == "Night Bar" and objs["o4"]["item"] == "barril", "Poly Haven conserva su id"
    assert "o5" not in objs, "lo que no existe en el catálogo nuevo se deja fuera"
    assert p["inner"] == [{"id": "w5", "x1": -5.0, "z1": -5.0, "x2": -5.0, "z2": -1.0, "kind": "vidrio", "door": None, "t": 0.1, "color": "#ffffff"}], "las paredes interiores no se pierden"
    assert objs["o6"]["conn"] == "pantalla:comandas" and objs["o6"]["screen"] == "Comandas en cocina"
    st = _state(client, ASADERO)
    assert st["designs"][0]["id"] == "principal" and st["designs"][0]["live"] and st["designs"][0]["version"] == 1
    assert client.get(f"{API}/pisos/{ASADERO}/plano").json()["version"] == 1


def test_025w_recupera_los_muros_interiores_de_los_2_borradores(client, cdb):
    import uuid as _u
    _migrate(cdb, "025w_b3d_muros")   # sin borradores: no hace nada
    base = {"name": "Mi local", "floor": {"mat": "baldosa", "color": "#eeeeee"}, "walls": {k: {"mat": "pintura", "color": "#e7e2f0"} for k in "nsew"},
            "openings": [{"id": "a2", "wall": "s", "pos": .35, "type": "puerta_vidrio"}], "objects": [], "people": []}
    for cid, room in ((ASADERO, {"w": 20, "d": 15, "h": 3.2}), (VELVET, {"w": 30, "d": 14, "h": 3.8})):
        _run(cdb, "INSERT INTO constructor_planos (id, company_id, diseno_id, version, estado, plano) VALUES (CAST(:i AS uuid), CAST(:c AS uuid), 'principal', 1, 'borrador', CAST(:p AS jsonb))",
             {"i": str(_u.uuid4()), "c": cid, "p": json.dumps({**base, "room": room})})
    for _ in range(2):
        _migrate(cdb, "025w_b3d_muros")
    a = _state(client, ASADERO)["designs"][0]["plan"]
    assert [(w["kind"], (w["door"] or {}).get("type")) for w in a["inner"]] == [("alto", "puerta"), ("vidrio", None)], "cocina con vaivén y vidrio de la terraza"
    assert c2.clean_plan(a) == a
    assert _state(client, VELVET)["designs"][0]["plan"]["inner"] == [], "si el local cambió de medida, no se toca"


# ------------------------------------------------------------------ importar
def test_importar_validado_en_el_servidor(client, cdb):
    doc = _plan(people=[{"id": "p", "pid": "abcdefabcdef", "x": 0, "z": 0, "rot": 0, "clip": "idle"}])
    doc["objects"].append({"id": "zz", "item": "dragon", "x": 0, "z": 0, "rot": 0})
    r = client.post(f"{B}/empresas/{VELVET}/importar", content=json.dumps(doc))
    assert r.status_code == 200, r.text
    p = r.json()["plan"]
    assert p["people"] == [] and all("conn" not in o for o in p["objects"]) and "dragon" not in {o["item"] for o in p["objects"]}
    assert client.post(f"{B}/empresas/{VELVET}/importar", content=b"<html>").status_code == 422
    assert client.post(f"{B}/empresas/{VELVET}/importar", content=json.dumps({"a": 1})).status_code == 422
    v1 = client.post(f"{B}/empresas/{VELVET}/importar", content=json.dumps({"formato": "clonexa.plano", "version_esquema": 1, "plano": V1}))
    assert v1.status_code == 200 and v1.json()["plan"]["room"]["w"] == 20, "también los .clonexa.json de la fase 1"


# ------------------------------------------------------------------ en vivo
def test_visor_del_cliente_solo_su_plano_publicado(client, cdb):
    _user(cdb, TTM, "company_admin", "ttm-owner")
    _save(client, TTM, "d1", _plan())
    client.post(f"{B}/empresas/{TTM}/disenos/d1/publicar")
    root = _enter(client, TTM, "ttm-owner")
    assert client.get(root + "api/piso").json()["floor"]["plano"] == 1
    r = client.get(root + f"api/pisos/{TTM}/plano")
    assert r.status_code == 200 and r.json()["version"] == 1 and "looks" in r.json()
    assert client.get(root + f"api/pisos/{VELVET}/plano").status_code == 403, "nunca el plano de otra empresa"
    for name in ("room.js", "char.js", "catalog.js", "core.js"):
        assert client.get(root + "b3d/" + name).status_code == 200, name
    for name in ("store.js", "editor.js", "people.js", "home.js"):
        assert client.get(root + "b3d/" + name).status_code == 404, "el guardado de la consola no existe para el cliente"
    assert client.get(root + "plano.js").status_code == 200
    client.cookies.clear()
    assert client.get(root + f"api/pisos/{TTM}/plano").status_code == 401


def test_estilo_no_mueve_nada_y_nevera_con_inventario(client, cdb):
    _save(client, TTM, "d1", _plan())
    client.post(f"{B}/empresas/{TTM}/disenos/d1/publicar")
    a = client.get(f"{API}/pisos/{TTM}/plano").json()
    client.put(f"{B}/empresas/{TTM}/estilo", json={"style": "toon"})
    b = client.get(f"{API}/pisos/{TTM}/plano").json()
    assert a["estilo"] == "humano" and b["estilo"] == "caricatura" and a["plano"] == b["plano"]
    _run(cdb, "INSERT INTO inventory_items (company_id, sku, name, category, current_stock, min_stock) VALUES (CAST(:c AS uuid), 'a', 'Club', 'Cervezas', 1, 5), (CAST(:c AS uuid), 'b', 'Aguila', 'Cervezas', 20, 5)", {"c": TTM})
    st = _state(client, TTM)
    assert {"id": "inv:Cervezas", "label": "Inventario · Cervezas"} in st["entities"]["inventario"]
    from app.services import constructor_v2 as svc
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

    async def go():
        eng = create_async_engine(cdb)
        async with AsyncSession(eng) as s:
            out = await svc.inventory_live(s, TTM)
        await eng.dispose()
        return out
    assert asyncio.run(go()) == {"Cervezas": {"items": 2, "low": 1}}


def test_ningun_endpoint_nuevo_sin_guardia():
    from app.web import constructor_routes as cr

    for r in cr.router.routes:
        if r.path.startswith("/admin-v2/api/"):
            assert any("session_required" in str(getattr(d, "dependency", d)) for d in r.dependant.dependencies) or r.dependencies, r.path


# ------------------------------------------------------------------ biblioteca (subir y revisar)

def _cube_glb():
    t = np.array([[[0, 0, 0], [2, 0, 0], [2, 4, 0]], [[0, 0, 0], [2, 4, 0], [0, 4, 0]], [[0, 0, 1], [2, 0, 1], [2, 4, 1]]], dtype=float)
    return cg.mesh_glb([{"tris": t, "color": (0.8, 0.1, 0.1)}])


def _fbx(limb=False):
    def prop(t, v):
        if t == "L":
            return b"L" + struct.pack("<q", v)
        if t == "S":
            return b"S" + struct.pack("<I", len(v)) + v
        if t == "D":
            return b"D" + struct.pack("<d", v)
        if t in "di":
            data = struct.pack(f"<{len(v)}{t}", *v)
            return t.encode() + struct.pack("<III", len(v), 0, len(data)) + data

    def node(name, props, children, off):
        body = b"".join(props)
        head = 13 + len(name)
        kids = b""
        cur = off + head + len(body)
        for ch in children:
            enc = ch(cur + len(kids))
            kids += enc
        if children:
            kids += b"\x00" * 13
        end = off + head + len(body) + len(kids)
        return struct.pack("<IIIB", end, len(props), len(body), len(name)) + name.encode() + body + kids

    verts = [0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0]
    geo = lambda off: node("Geometry", [prop("L", 10), prop("S", b"Geo\x00\x01Geometry"), prop("S", b"Mesh")],
                           [lambda o: node("Vertices", [prop("d", verts)], [], o), lambda o: node("PolygonVertexIndex", [prop("i", [0, 1, 2, -4])], [], o)], off)
    model = lambda off: node("Model", [prop("L", 20), prop("S", b"Cubo\x00\x01Model"), prop("S", b"LimbNode" if limb else b"Mesh")], [], off)
    objects = lambda off: node("Objects", [], [geo, model], off)
    conns = lambda off: node("Connections", [], [lambda o: node("C", [prop("S", b"OO"), prop("L", 10), prop("L", 20)], [], o)], off)
    out = b"Kaydara FBX Binary  \x00\x1a\x00" + struct.pack("<I", 7400)
    for n in (objects, conns):
        out += n(len(out))
    return out + b"\x00" * 13


FORM = {"nombre": "Silla prueba", "categoria": "mesas", "licencia": "cc0", "fuente": "https://polyhaven.com/a/x", "alto": "0.9"}


def _upload(client, name, raw, **over):
    data = {**FORM, **over}
    return client.post(f"{B}/biblioteca/subir", files={"archivo": (name, raw, "application/octet-stream")}, data=data)


def test_biblioteca_asistente_convierte_glb_obj_zip_fbx_y_aprueba(client, cdb):
    r = _upload(client, "cubo.glb", _cube_glb())
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["estado"] == "revision" and abs(j["size"]["h"] - 0.9) < 1e-6
    assert j["id"] in {x["id"] for x in j["review"]} and j["id"] not in {x["id"] for x in j["catalog"]}, "en revisión no sale en el catálogo"
    row = _run(cdb, "SELECT archivo, miniatura FROM constructor_catalogo WHERE id = :i", {"i": j["id"]})[0]
    assert client.bucket.get(row["miniatura"])[:4] == b"RIFF"
    assert client.get(f"{API}/catalogo/{j['id']}.glb").status_code == 200
    ok = client.post(f"{B}/biblioteca/{j['id']}/aprobar").json()
    m = next(x for x in ok["catalog"] if x["id"] == j["id"])
    assert m["cat"] == "mesas" and m["url"].endswith(".glb?v=" + m["url"].split("?v=")[1]) and m["license"] == "CC0 1.0"
    assert j["id"] in {x["id"] for x in _state(client, VELVET)["catalog"]}, "aprobado: catálogo de todas las empresas en su carpeta"
    assert _save(client, VELVET, "g", _plan(objects=[{"id": "g1", "item": j["id"], "x": 0, "z": 0, "rot": 0}])).status_code == 200
    deco = _upload(client, "cubo2.glb", _cube_glb(), nombre="Deco", categoria="deco").json()
    assert next(x for x in deco["review"] if x["id"] == deco["id"])["cat"] == "deco", "carpeta del prototipo <-> categoría de la biblioteca"
    obj = b"mtllib a.mtl\nv 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nusemtl r\nf 1 2 3 4\n"
    assert _upload(client, "a.obj", obj, nombre="Obj").status_code == 200
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("modelo/a.obj", obj)
        zf.writestr("modelo/a.mtl", "newmtl r\nKd 0.2 0.6 0.2\n")
    assert _upload(client, "m.zip", z.getvalue(), nombre="Zip prueba").status_code == 200
    f = _upload(client, "c.fbx", _fbx(), nombre="Fbx prueba")
    assert f.status_code == 200 and f.json()["estado"] == "revision", f.text
    assert client.post(f"{B}/biblioteca/{f.json()['id']}/rechazar").json()["estado"] == "rechazado"
    assert client.post(f"{B}/biblioteca/no_existe/aprobar").status_code == 404


def test_biblioteca_rechaza_malicioso_falso_y_sin_licencia(client, cdb):
    for name in ("../evil.obj", "ok/run.exe", "a/../../b.obj"):
        z = io.BytesIO()
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr(name, b"v 0 0 0\n")
        assert _upload(client, "m.zip", z.getvalue()).status_code == 422, name
    for name, raw in (("x.glb", b"MZ\x90\x00" + b"\x00" * 100), ("x.fbx", b"hola"), ("x.obj", b"<html>no</html>")):
        assert _upload(client, name, raw).status_code == 422, name
    assert "licencia" in _upload(client, "c.glb", _cube_glb(), licencia="").json()["detail"].lower()
    assert _upload(client, "c.glb", _cube_glb(), licencia="ccby").status_code == 422, "CC-BY exige atribución"
    assert _upload(client, "c.glb", _cube_glb(), licencia="ccby", atribucion="Silla · https://x").status_code == 200
    assert _upload(client, "c.glb", _cube_glb(), fuente="").status_code == 422, "sin fuente no se publica"
    assert _upload(client, "c.glb", _cube_glb(), categoria="cohetes").status_code == 422
