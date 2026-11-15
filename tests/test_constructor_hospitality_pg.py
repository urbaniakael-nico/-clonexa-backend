"""MODO CONSTRUCTOR (fase 1) y BIBLIOTECA 3D contra Postgres REAL (pgserver) y la app completa.

- 401 sin sesion en paginas (al ingreso), API y archivos; ningun cliente ve el constructor.
- Empresa A no ve ni edita planos/objetos de B (consola: cada empresa su borrador; visor del cliente: solo su plano).
- Plano: primer borrador = plantilla de su piso + lo guardado con "Editar distribucion"; autoguardado; validacion
  estricta; versiones publicadas, historial y restaurar; exportar/importar .clonexa.json (y rechazo de invalidos).
- Publicar cambia el piso en vivo (Oficina 3D y Negocio en vivo 3D) SOLO con el interruptor de la empresa; el
  borrador nunca. Empresas sin plano: su piso de siempre.
- Conexiones: una entidad real -> un objeto; mesa conectada con su QR real en la copia viva; avisos.
- Biblioteca: GLB, OBJ, ZIP y FBX se convierten, escalan y generan miniatura; ZIP malicioso y archivo falso
  rechazados; sin licencia no se publica; esqueleto -> fase 2; importacion desde Poly Haven (simulada).
- Estilo Humano/Caricatura: cambia solo el estilo, nunca posiciones ni conexiones.
"""
from __future__ import annotations

import importlib
import io
import json
import struct
import zipfile

import numpy as np
import pytest

pytest.importorskip("pgserver")

from tests.test_oficina_hospitality_pg import API, TTM, VELVET, ASADERO, NUEVA, _qr_tables, _run, _session, client, pg_url  # noqa: E402,F401
from tests.test_live3d_hospitality_pg import USERS, _bearer, _enter, _user, db  # noqa: E402,F401
from app.services import constructor_biblioteca as cb  # noqa: E402
from app.services import constructor_glb as cg  # noqa: E402
from app.services import constructor_plano as cp  # noqa: E402
from app.services import live3d as l3  # noqa: E402
from app.web import oficina_routes  # noqa: E402

CAPI = "/admin-v2/api/constructor"


def _migrate(url):
    class Bind:
        def execute(self, clause, params=None):
            _run(url, str(clause), params or {})

    class Op:
        def execute(self, sql):
            _run(url, str(sql))

        def get_bind(self):
            return Bind()

    mod = importlib.import_module("migrations.versions.025u_constructor")
    mod.op = Op()
    mod.upgrade()


@pytest.fixture
def cdb(db, monkeypatch):
    for _ in range(2):   # aditiva e idempotente
        _migrate(db)
    _run(db, "DELETE FROM constructor_planos")
    _run(db, "DELETE FROM constructor_catalogo WHERE origen = 'bucket'")
    _session(monkeypatch, True)
    oficina_routes.reset_cache()
    return db


def _state(client, cid):
    r = client.get(f"{CAPI}/empresas/{cid}")
    assert r.status_code == 200, r.text
    return r.json()


def _put(client, cid, plan):
    return client.put(f"{CAPI}/empresas/{cid}/borrador", json={"plano": plan})


# ------------------------------------------------------------------ migracion y catalogo
def test_migracion_catalogo_e_interruptores_apagados(client, cdb):
    n = _run(cdb, "SELECT count(*) AS n FROM constructor_catalogo")[0]["n"]
    assert n == len(cb.seed_items()) >= 120, "catalogo inicial sembrado una sola vez (idempotente)"
    cats = {r["categoria"] for r in _run(cdb, "SELECT DISTINCT categoria FROM constructor_catalogo")}
    assert cats == set(cb.CATEGORIES)
    assert _run(cdb, "SELECT count(*) AS n FROM constructor_catalogo WHERE licencia IS NULL OR licencia = ''")[0]["n"] == 0, "todo con licencia"
    recursos = _run(cdb, "SELECT id, licencia, fuente FROM constructor_catalogo WHERE origen = 'recurso'")
    assert recursos and all(r["licencia"] == "CC0 1.0" and r["fuente"].startswith("https://polyhaven.com/a/") for r in recursos)
    cols = {r["column_name"]: r["column_default"] for r in _run(cdb, "SELECT column_name, column_default FROM information_schema.columns WHERE table_name = 'oficina_pisos'")}
    assert "false" in cols["usa_plano"].lower() and "humano" in cols["estilo_escena"]


def test_sin_sesion_todo_401_y_paginas_al_ingreso(client, cdb, monkeypatch):
    _session(monkeypatch, False)
    for path in ("/admin-v2plus/constructor", "/admin-v2plus/constructor/vista", "/admin-v2plus/biblioteca", "/admin-v2plus/creditos-3d"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/admin-v2plus/login", path
    for name in ("constructor.js", "constructor_reglas.js", "constructor_vista.js", "plano.js", "plano_objetos.js", "biblioteca.js", "constructor.css"):
        assert client.get(f"/admin-v2plus/oficina/{name}").status_code == 401, name
    calls = [("get", f"{CAPI}/empresas/{TTM}"), ("put", f"{CAPI}/empresas/{TTM}/borrador"), ("post", f"{CAPI}/empresas/{TTM}/publicar"),
             ("post", f"{CAPI}/empresas/{TTM}/restaurar"), ("get", f"{CAPI}/empresas/{TTM}/versiones/1"), ("post", f"{CAPI}/empresas/{TTM}/plantilla"),
             ("get", f"{CAPI}/empresas/{TTM}/exportar"), ("post", f"{CAPI}/empresas/{TTM}/importar"), ("put", f"{CAPI}/empresas/{TTM}/ajustes"),
             ("get", f"{CAPI}/catalogo"), ("post", f"{CAPI}/biblioteca/subir"), ("post", f"{CAPI}/biblioteca/revision/x_y/aprobar"),
             ("get", f"{CAPI}/biblioteca/polyhaven"), ("post", f"{CAPI}/biblioteca/polyhaven/chair"), ("get", f"{API}/catalogo/sub_x.glb"),
             ("get", f"{API}/pisos/{TTM}/plano")]
    for method, path in calls:
        r = getattr(client, method)(path)
        assert r.status_code == 401, (method, path, r.status_code)
    assert _run(cdb, "SELECT count(*) AS n FROM constructor_planos")[0]["n"] == 0, "nada se crea sin sesion"


# ------------------------------------------------------------------ borrador, autoguardado, versiones
def test_primer_borrador_migra_editar_distribucion_y_mesas_reales(client, cdb):
    _qr_tables(cdb, ASADERO, 6)
    _run(cdb, """INSERT INTO oficina_pisos (company_id, plantilla, distribucion) VALUES (CAST(:c AS uuid), 'restaurante', CAST(:d AS jsonb))
                 ON CONFLICT (company_id) DO UPDATE SET plantilla = EXCLUDED.plantilla, distribucion = EXCLUDED.distribucion""",
         {"c": ASADERO, "d": json.dumps({"piso": {"plantilla": "restaurante", "items": {"mesa:Mesa 2": [-3.0, 1.5, 0]}}})})
    st = _state(client, ASADERO)
    plan = st["draft"]["plano"]
    mesas = {o["conexion"]["id"]: o for o in plan["objetos"] if o.get("conexion") and o["conexion"]["tipo"] == "mesa"}
    assert sorted(mesas) == [f"Mesa {i}" for i in range(1, 7)], "las mesas reales se conectan solas"
    assert (mesas["Mesa 2"]["x"], mesas["Mesa 2"]["z"]) == (7.0, 9.0), "la posicion guardada con el modo arquitecto se respeta"
    assert st["published"] is None and st["usa_plano"] is False and st["estilo_escena"] == "humano"
    assert [e["id"] for e in st["entities"]["mesa"]] == [f"Mesa {i}" for i in range(1, 7)]
    assert _run(cdb, "SELECT estado, version FROM constructor_planos WHERE company_id = CAST(:c AS uuid)", {"c": ASADERO}) == [{"estado": "borrador", "version": 1}]


def test_autoguardado_validacion_versiones_y_restaurar(client, cdb):
    plan = _state(client, TTM)["draft"]["plano"]
    plan["objetos"][0]["x"] = 3.3
    r = _put(client, TTM, plan)
    assert r.status_code == 200 and r.json()["version"] == 1
    assert _state(client, TTM)["draft"]["plano"]["objetos"][0]["x"] == 3.3, "autoguardado"
    bad = json.loads(json.dumps(plan))
    bad["objetos"][0]["asset"] = "sims_sofa"
    assert _put(client, TTM, bad).status_code == 422, "modelo fuera del catalogo"
    bad = json.loads(json.dumps(plan))
    bad["objetos"][0]["hack"] = 1
    assert _put(client, TTM, bad).status_code == 422, "campos desconocidos"
    bad = json.loads(json.dumps(plan))
    bad["aberturas"].append({"id": "zz", "pared": "no-existe", "tipo": "puerta", "pos": 1})
    assert _put(client, TTM, bad).status_code == 422
    bad = json.loads(json.dumps(plan))
    mesas = [o for o in bad["objetos"] if (o.get("conexion") or {}).get("tipo") == "mesa"]
    mesas[1]["conexion"] = dict(mesas[0]["conexion"])
    r = _put(client, TTM, bad)
    assert r.status_code == 422 and "ya está conectada" in r.json()["detail"], "una entidad real solo se conecta a un objeto"
    # publicar v1, cambiar, publicar v2, restaurar v1
    r = client.post(f"{CAPI}/empresas/{TTM}/publicar", json={})
    assert r.status_code == 200 and r.json()["version"] == 1 and r.json()["usa_plano"] is False, "publicar no enciende sin pedirlo"
    plan["objetos"][0]["x"] = 5.5
    assert _put(client, TTM, plan).json()["version"] == 2, "el borrador apunta a la version siguiente"
    assert client.post(f"{CAPI}/empresas/{TTM}/publicar", json={}).json()["version"] == 2
    hist = _state(client, TTM)["history"]
    assert [h["version"] for h in hist] == [2, 1]
    assert client.get(f"{CAPI}/empresas/{TTM}/versiones/1").json()["plano"]["objetos"][0]["x"] == 3.3
    st = client.post(f"{CAPI}/empresas/{TTM}/restaurar", json={"version": 1}).json()
    assert st["draft"]["plano"]["objetos"][0]["x"] == 3.3 and st["draft"]["version"] == 3
    assert client.post(f"{CAPI}/empresas/{TTM}/restaurar", json={"version": 99}).status_code == 404


def test_exportar_importar_en_otra_empresa_y_rechazo(client, cdb):
    plan = _state(client, TTM)["draft"]["plano"]
    r = client.get(f"{CAPI}/empresas/{TTM}/exportar")
    assert r.status_code == 200 and ".clonexa.json" in r.headers["content-disposition"]
    doc = r.json()
    assert doc["formato"] == "clonexa.plano" and doc["version_esquema"] == 1 and len(doc["plano"]["objetos"]) == len(plan["objetos"])
    st = client.post(f"{CAPI}/empresas/{VELVET}/importar", content=r.content, headers={"Content-Type": "application/json"})
    assert st.status_code == 200, st.text
    imported = st.json()["draft"]["plano"]
    assert len(imported["objetos"]) == len(plan["objetos"]) and all(o["conexion"] is None for o in imported["objetos"]), "las conexiones no viajan"
    assert _state(client, TTM)["draft"]["plano"] == plan, "la empresa de origen no cambia"
    for raw in (b"no es json", json.dumps({"formato": "otro"}).encode(), json.dumps({**doc, "extra": 1}).encode(),
                json.dumps({**doc, "plano": {**doc["plano"], "objetos": [{"id": "o1", "asset": "silla", "x": "a", "z": 1}]}}).encode(),
                json.dumps({**doc, "version_esquema": 9}).encode()):
        assert client.post(f"{CAPI}/empresas/{VELVET}/importar", content=raw).status_code == 422


def test_empresa_a_no_ve_ni_edita_lo_de_b(client, cdb):
    a = _state(client, TTM)["draft"]["plano"]
    b = _state(client, VELVET)["draft"]["plano"]
    a["objetos"] = a["objetos"][:3]
    assert _put(client, TTM, a).status_code == 200
    assert _state(client, VELVET)["draft"]["plano"] == b, "guardar A no toca B"
    rows = _run(cdb, "SELECT company_id::text AS c, jsonb_array_length(plano->'objetos') AS n FROM constructor_planos WHERE estado = 'borrador' ORDER BY c")
    assert {r["c"]: r["n"] for r in rows}[TTM] == 3 and {r["c"]: r["n"] for r in rows}[VELVET] == len(b["objetos"])
    assert client.get(f"{CAPI}/empresas/00000000-0000-0000-0000-000000000000").status_code == 404


# ------------------------------------------------------------------ en vivo: publicado vs borrador
def test_publicar_cambia_el_piso_en_vivo_y_el_borrador_no(client, cdb):
    _qr_tables(cdb, TTM, 10)
    plan = _state(client, TTM)["draft"]["plano"]
    estado = client.get(f"{API}/estado").json()
    floors = {f["company_id"]: f for f in estado["floors"]}
    assert all(f["plano"] is None for f in floors.values()), "nadie tiene plano en vivo al empezar"
    before = {cid: (f["style"], f["template"]) for cid, f in floors.items()}
    assert client.get(f"{API}/pisos/{TTM}/plano").status_code == 404, "sin publicar no hay plano en vivo"
    v = client.post(f"{CAPI}/empresas/{TTM}/publicar", json={"encender": True}).json()
    assert v["version"] == 1 and v["usa_plano"] is True
    oficina_routes.reset_cache()
    floors = {f["company_id"]: f for f in client.get(f"{API}/estado").json()["floors"]}
    assert floors[TTM]["plano"] == 1, "la Oficina 3D abre el piso del plano"
    assert all(floors[c]["plano"] is None and (floors[c]["style"], floors[c]["template"]) == before[c] for c in floors if c != TTM), "las demas siguen igual"
    live = client.get(f"{API}/pisos/{TTM}/plano").json()
    assert live["version"] == 1 and len(live["plano"]["objetos"]) == len(plan["objetos"])
    # el borrador cambia y lo publicado NO
    plan["objetos"] = plan["objetos"][:2]
    _put(client, TTM, plan)
    assert len(client.get(f"{API}/pisos/{TTM}/plano").json()["plano"]["objetos"]) == len(live["plano"]["objetos"]), "el borrador nunca se ve en vivo"
    assert len(client.get(f"{API}/pisos/{TTM}/plano?borrador=1").json()["plano"]["objetos"]) == 2, "la vista del constructor si ve el borrador"
    # copia viva: lleva la version del plano y las mesas reales (mesa conectada con su QR)
    _run(cdb, """INSERT INTO hospitality_table_access (company_id, table_key, table_number, status, activated_at, expires_at)
                 VALUES (CAST(:c AS uuid), 'mesa-4', 'Mesa 4', 'active', now(), now() + interval '3 hours')""", {"c": TTM})
    oficina_routes.reset_live_cache()
    snap = client.get(f"{API}/pisos/{TTM}/vivo").json()
    assert snap["plano"] == 1 and snap["estilo_escena"] == "humano"
    m4 = next(t for t in snap["tables"] if t["label"] == "Mesa 4")
    assert m4["open"] is True
    con = [o for o in live["plano"]["objetos"] if (o.get("conexion") or {}).get("id") == "Mesa 4"]
    assert len(con) == 1, "la mesa 4 real esta conectada a un objeto del plano: el motor la enciende"
    # apagar el interruptor: vuelve el piso de siempre
    assert client.put(f"{CAPI}/empresas/{TTM}/ajustes", json={"usa_plano": False}).json()["usa_plano"] is False
    oficina_routes.reset_cache()
    assert {f["company_id"]: f for f in client.get(f"{API}/estado").json()["floors"]}[TTM]["plano"] is None


def test_visor_del_cliente_solo_su_plano_publicado(client, cdb):
    _user(cdb, TTM, "company_admin", "ttm-owner")
    _state(client, TTM)
    client.post(f"{CAPI}/empresas/{TTM}/publicar", json={"encender": True})
    root = _enter(client, TTM, "ttm-owner")
    piso = client.get(root + "api/piso").json()
    assert piso["floor"]["plano"] == 1
    r = client.get(root + f"api/pisos/{TTM}/plano")
    assert r.status_code == 200 and r.json()["version"] == 1
    assert all(x["url"].startswith(root) for x in r.json()["catalogo"] if x.get("url")), "los modelos salen de la ruta firmada de su empresa"
    assert client.get(root + f"api/pisos/{VELVET}/plano").status_code == 403, "nunca el plano de otra empresa"
    assert client.get(root + "plano.js").status_code == 200 and client.get(root + "plano_objetos.js").status_code == 200
    assert client.get(root + "constructor.js").status_code == 404, "el constructor no existe para el cliente"
    assert client.get(root + "api/catalogo/sub_no_existe.glb").status_code == 404
    client.cookies.clear()
    assert client.get(root + f"api/pisos/{TTM}/plano").status_code == 401


def test_estilo_caricatura_no_mueve_nada(client, cdb):
    st = _state(client, TTM)
    client.post(f"{CAPI}/empresas/{TTM}/publicar", json={"encender": True})
    a = client.get(f"{API}/pisos/{TTM}/plano").json()
    r = client.put(f"{CAPI}/empresas/{TTM}/ajustes", json={"estilo_escena": "caricatura"})
    assert r.status_code == 200 and r.json()["estilo_escena"] == "caricatura"
    b = client.get(f"{API}/pisos/{TTM}/plano").json()
    assert a["estilo"] == "humano" and b["estilo"] == "caricatura"
    assert a["plano"] == b["plano"], "mismo plano: posiciones y conexiones intactas"
    assert _state(client, TTM)["draft"]["plano"] == st["draft"]["plano"]
    assert client.put(f"{CAPI}/empresas/{TTM}/ajustes", json={"estilo_escena": "sims"}).status_code == 422
    assert client.put(f"{CAPI}/empresas/{VELVET}/ajustes", json={"usa_plano": True}).status_code == 409, "sin version publicada no se enciende"


def test_plantillas_distintas_y_validas(client, cdb):
    sigs = set()
    for key in cp.TEMPLATES:
        st = client.post(f"{CAPI}/empresas/{NUEVA}/plantilla", json={"plantilla": key}).json()
        plan = st["draft"]["plano"]
        assert len(plan["objetos"]) >= 20, key
        sigs.add((plan["sala"]["ancho"], plan["sala"]["fondo"], tuple(sorted({o["asset"] for o in plan["objetos"]}))[:6]))
    assert len(sigs) == len(cp.TEMPLATES), "cada plantilla es distinta"
    assert client.post(f"{CAPI}/empresas/{NUEVA}/plantilla", json={"plantilla": "sims"}).status_code == 422


# ------------------------------------------------------------------ biblioteca
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


FORM = {"nombre": "Silla prueba", "categoria": "mesas", "zonas": ["salon"], "conectable": "ninguno", "licencia": "cc0", "fuente": "https://polyhaven.com/a/x", "alto": "0.9"}


def _upload(client, name, raw, **over):
    data = {**FORM, **over}
    return client.post(f"{CAPI}/biblioteca/subir", files={"archivo": (name, raw, "application/octet-stream")},
                       data={k: v for k, v in data.items()})


def test_biblioteca_convierte_glb_obj_zip_fbx_y_aprueba(client, cdb):
    r = _upload(client, "cubo.glb", _cube_glb())
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["estado"] == "revision" and abs(j["size"]["h"] - 0.9) < 1e-6 and j["tris"] == 3
    row = _run(cdb, "SELECT archivo, miniatura, bytes, licencia FROM constructor_catalogo WHERE id = :i", {"i": j["id"]})[0]
    glb = client.bucket.get(row["archivo"])
    g = cg.Gltf.from_glb(glb)
    pts = np.concatenate([t.reshape(-1, 3) for t, _ in cg.triangles(g)])
    assert abs(pts[:, 1].min()) < 1e-6 and abs(pts[:, 1].max() - 0.9) < 1e-6, "apoyado en el piso y a la medida real"
    assert abs((pts[:, 0].min() + pts[:, 0].max()) / 2) < 1e-6, "centrado"
    assert client.bucket.get(row["miniatura"])[:4] == b"RIFF", "miniatura WebP"
    assert client.get(f"{API}/catalogo/{j['id']}.glb").status_code == 200
    assert j["id"] not in {x["id"] for x in client.get(f"{CAPI}/catalogo").json()["items"]}, "en revision no sale en el constructor"
    assert client.post(f"{CAPI}/biblioteca/revision/{j['id']}/aprobar").json()["estado"] == "publicado"
    assert j["id"] in {x["id"] for x in client.get(f"{CAPI}/catalogo").json()["items"]}, "aprobado: catalogo de todas las empresas"
    obj = b"mtllib a.mtl\nv 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nusemtl r\nf 1 2 3 4\n"
    assert _upload(client, "a.obj", obj, ancho="1.2", alto="").json()["size"]["w"] == pytest.approx(1.2)
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("modelo/a.obj", obj)
        zf.writestr("modelo/a.mtl", "newmtl r\nKd 0.2 0.6 0.2\n")
    assert _upload(client, "m.zip", z.getvalue(), nombre="Zip prueba").status_code == 200
    f = _upload(client, "c.fbx", _fbx(), nombre="Fbx prueba")
    assert f.status_code == 200 and f.json()["estado"] == "revision", f.text
    rig = _upload(client, "p.fbx", _fbx(limb=True), nombre="Personaje")
    assert rig.json()["estado"] == "fase2" and rig.json()["rigged"] is True, "personajes con esqueleto: fase 2"
    r = client.post(f"{CAPI}/biblioteca/revision/{rig.json()['id']}/aprobar")
    assert r.status_code == 422, "fase 2 no entra al constructor todavia"


def test_biblioteca_rechaza_zip_malicioso_falso_y_sin_licencia(client, cdb):
    for name in ("../evil.obj", "/abs.obj", "C:/win.obj", "ok/run.exe", "ok/x.js", "a/../../b.obj"):
        z = io.BytesIO()
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr(name, b"v 0 0 0\n")
        r = _upload(client, "m.zip", z.getvalue())
        assert r.status_code == 422, name
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("a.obj", b"#" * (30 * 1024 * 1024))
    assert _upload(client, "b.zip", bomb.getvalue()).status_code == 422, "bomba de compresion"
    for name, raw in (("x.glb", b"MZ\x90\x00" + b"\x00" * 100), ("x.fbx", b"hola"), ("x.obj", b"<html>no</html>"), ("x.gltf", b"{}")):
        assert _upload(client, name, raw).status_code == 422, name
    assert "licencia" in _upload(client, "c.glb", _cube_glb(), licencia="").json()["detail"].lower()
    assert _upload(client, "c.glb", _cube_glb(), licencia="ccby", atribucion="").status_code == 422, "CC-BY exige atribucion"
    assert _upload(client, "c.glb", _cube_glb(), alto="", ancho="").status_code == 422, "medida real obligatoria"
    assert _run(cdb, "SELECT count(*) AS n FROM constructor_catalogo WHERE origen = 'bucket'")[0]["n"] == 0


def test_polyhaven_buscar_e_importar_simulado(client, cdb, monkeypatch):
    gltf_doc, buf = _gltf_with_buffer()
    calls = []

    async def fake_get(url, client_=None):
        calls.append(url)
        if url.endswith("/assets?t=models"):
            return {"wooden_chair": {"name": "Wooden Chair", "tags": ["chair"], "categories": ["furniture"], "authors": {"Ana": "All"}}}
        if "/info/" in url:
            return {"type": 2, "name": "Wooden Chair", "authors": {"Ana": "All"}}
        return {"gltf": {"1k": {"gltf": {"url": "https://dl.polyhaven.org/x/chair.gltf", "include": {"chair.bin": {"url": "https://dl.polyhaven.org/x/chair.bin"}}}}}}

    class FakeResp:
        def __init__(self, content):
            self.content = content

        def raise_for_status(self):
            pass

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def get(self, url, headers=None):
            assert headers and headers["User-Agent"] == cb.USER_AGENT, "User-Agent propio (condiciones de la API)"
            return FakeResp(json.dumps(gltf_doc).encode() if url.endswith(".gltf") else buf)

    monkeypatch.setattr(cb, "_ph_get", fake_get)
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", lambda **k: FakeClient())
    r = client.get(f"{CAPI}/biblioteca/polyhaven?q=chair")
    assert r.status_code == 200 and r.json()["items"][0]["licencia"] == "CC0 1.0"
    r = client.post(f"{CAPI}/biblioteca/polyhaven/wooden_chair", json={"categoria": "mesas", "zonas": ["salon"], "conectable": "ninguno", "alto": "0.85"})
    assert r.status_code == 200, r.text
    row = _run(cdb, "SELECT licencia, fuente, autor, estado FROM constructor_catalogo WHERE id = :i", {"i": r.json()["id"]})[0]
    assert row == {"licencia": "CC0 1.0", "fuente": "https://polyhaven.com/a/wooden_chair", "autor": "Ana", "estado": "revision"}
    assert not cb._ph_url_ok("https://evil.example/x.gltf") and cb._ph_url_ok("https://dl.polyhaven.org/a.gltf")


def _gltf_with_buffer():
    pos = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0]], dtype=np.float32).tobytes()
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}], "buffers": [{"uri": "chair.bin", "byteLength": len(pos)}],
           "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(pos)}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3", "min": [0, 0, 0], "max": [1, 1, 0]}]}
    return doc, pos


# ------------------------------------------------------------------ reglas puras del servidor
def test_avisos_cruces_puertas_y_sin_conectar():
    items = cb.seed_items()
    sizes = cb.sizes(items)
    plan = cp.template("bar", ["Mesa 1"])
    plan["objetos"].append({**plan["objetos"][-1], "id": "dup", "conexion": None})
    door = plan["aberturas"][0]
    w = next(x for x in plan["paredes"] if x["id"] == door["pared"])
    L = ((w["x2"] - w["x1"]) ** 2 + (w["z2"] - w["z1"]) ** 2) ** 0.5
    dx, dz = w["x1"] + (w["x2"] - w["x1"]) / L * door["pos"], w["z1"] + (w["z2"] - w["z1"]) / L * door["pos"]
    plan["objetos"].append({"id": "tapa", "asset": "sofa", "x": dx, "z": dz - 0.5, "rot": 0, "escala": 1, "color": None, "variante": None,
                            "capa": "muebles", "conexion": None, "texto": None})
    clean = cp.clean_plan(plan, {x["id"] for x in items})
    warn = cp.warnings(clean, sizes, {"mesa": [{"id": "Mesa 1", "label": "Mesa 1"}, {"id": "Mesa 9", "label": "Mesa 9"}]})
    assert any("dup" in c for c in warn["cruces"]), "dos objetos encima"
    assert any(p[0] == "tapa" for p in warn["puertas"]), "objeto que tapa la puerta"
    assert "dup" in warn["sin_conectar"] and warn["mesas_sin_objeto"] == ["Mesa 9"]


def test_ningun_endpoint_nuevo_sin_guardia():
    from app.web import constructor_routes as cr

    for route in cr.router.routes:
        path = route.path
        if path.startswith("/admin-v2/api/"):
            assert route.dependencies, f"{path} sin GUARD"
        else:
            assert path.startswith("/admin-v2plus/"), path
