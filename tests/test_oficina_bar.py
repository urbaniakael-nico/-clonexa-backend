"""Oficina 3D · bar aprobado de The Time Machine (personajes de Mixamo en el bucket privado).

- NINGUN archivo de Mixamo en git (el repo es publico y la licencia prohibe redistribuirlos): ni .fbx, ni .glb con
  huesos "mixamorig" o animacion "mixamo.com", ni sus nombres (ChNN_nonPBR.glb, Remy.glb). .gitignore los excluye.
- LICENCIAS.md: Mixamo = uso dentro del producto, no redistribuible, en el bucket privado; Quaternius retirado.
- Migracion 025l: id de 32 caracteres o menos, solo enciende The Time Machine.
- Servicio de recursos: lista blanca, huella sha256, cache en memoria, bucket caido -> Unavailable.
- Pantalla de canciones (funcion pura) y desde donde se pidio (mesa o puesto de barra), sin nombres de clientes.
- Motor del bar: solo el propio backend (sin CDN), sin estilos ni manejadores en linea; transiciones suaves.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest

from app.services import brand_media
from app.services import oficina_bar as obar
from app.services import oficina_data as od
from app.services import oficina_vivo as ov

ROOT = Path(__file__).resolve().parents[1]
MIXAMO_NAME = re.compile(r"(^|/)(Ch\d{2}_nonPBR|Remy)\.glb$|\.fbx$", re.I)


def _tracked() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git no disponible")
    return [p for p in out.decode("utf-8", "replace").split("\0") if p]


def _glb_json(raw: bytes) -> dict:
    if raw[:4] != b"glTF":
        return {}
    return json.loads(raw[20:20 + int.from_bytes(raw[12:16], "little")])


def is_mixamo(name: str, raw: bytes) -> bool:
    if MIXAMO_NAME.search(name):
        return True
    if not name.lower().endswith(".glb"):
        return False
    try:
        j = _glb_json(raw)
    except ValueError:
        return False
    nodes = " ".join(str(n.get("name", "")) for n in j.get("nodes", []))
    return "mixamorig" in nodes or any(a.get("name") == "mixamo.com" for a in j.get("animations", []))


def test_ningun_archivo_de_mixamo_en_git():
    found = [p for p in _tracked() if (p.lower().endswith((".glb", ".fbx"))) and (ROOT / p).exists() and is_mixamo(p, (ROOT / p).read_bytes())]
    assert found == [], f"archivos de Mixamo en el repo publico (licencia: no redistribuibles): {found}"


def test_el_detector_reconoce_un_archivo_de_mixamo():
    def glb(nodes, anims=()):
        body = json.dumps({"asset": {"version": "2.0"}, "nodes": [{"name": n} for n in nodes], "animations": [{"name": a} for a in anims]}).encode()
        body += b" " * (-len(body) % 4)
        return b"glTF" + (2).to_bytes(4, "little") + (20 + len(body)).to_bytes(4, "little") + len(body).to_bytes(4, "little") + b"JSON" + body
    assert is_mixamo("x/otro.glb", glb(["mixamorig12:Hips"]))
    assert is_mixamo("x/baile.glb", glb(["Root"], ["mixamo.com"]))
    assert is_mixamo("a/Ch21_nonPBR.glb", b"") and is_mixamo("a/Remy.glb", b"") and is_mixamo("a/b/Walking.fbx", b"")
    assert not is_mixamo("modelos/mesa.glb", glb(["Table"]))


def test_gitignore_excluye_los_recursos_de_mixamo():
    probes = ["clonexa-assets/oficina-bar/procesados/personajes/Ch01_nonPBR.glb", "algo/Walking.fbx", "x/Ch07_nonPBR.glb", "Remy.glb",
              "mixamo personajes/Ch01.fbx"]
    try:
        out = subprocess.run(["git", "check-ignore", "--no-index", *probes], cwd=ROOT, capture_output=True, text=True).stdout.splitlines()
    except OSError:
        pytest.skip("git no disponible")
    assert sorted(out) == sorted(probes)
    assert subprocess.run(["git", "check-ignore", "-q", "--no-index", "app/web/oficina/recursos/modelos/mesa.glb"], cwd=ROOT).returncode == 1, "los CC0 siguen versionados"


def test_licencias_mixamo_no_redistribuible_y_quaternius_retirado():
    lic = (ROOT / "docs/oficina/LICENCIAS.md").read_text(encoding="utf-8")
    assert "Mixamo" in lic and "No redistribuible" in lic and "Bucket privado" in lic and "subir_recursos_bar.py" in lic
    assert "CC0" in lic and "MIT" in lic
    assert "`personajes/superhero" not in lic and "retiraron" in lic
    assert not list((ROOT / "app/web/oficina/recursos").glob("personajes/*")), "los cuerpos de Quaternius (sin ropa) salieron del piso"


def test_migracion_025l_corta_y_solo_the_time_machine():
    src = (ROOT / "migrations/versions/025l_oficina_bar.py").read_text(encoding="utf-8")
    rev = re.search(r'^revision = "([^"]+)"', src, re.M).group(1)
    assert len(rev) <= 32 and re.search(r'^down_revision = "025k_oficina_real"', src, re.M)
    assert src.count("21a3065e-38ee-4fc3-96ed-ae1707a3b8e4") == 1 and "'bar'" in src


def test_estilo_bar_solo_con_plantilla_bar():
    assert od.floor_style({"estilo": "bar"}, "bar") == "bar"
    assert od.floor_style({"estilo": "bar"}, "taller") == "clasico"
    assert od.floor_style({"estilo": "realista"}, "bar") == "realista"
    assert od.floor_style({}, "bar") == "clasico"
    assert "bar" in ov.STYLES_FLOOR


class Bucket:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.gets = 0

    def get(self, key):
        self.gets += 1
        if key not in self.objects:
            raise brand_media.StorageUnavailable("no existe")
        return self.objects[key]


@pytest.fixture
def bucket():
    b = Bucket()
    brand_media.set_backend(b)
    obar.reset()
    yield b
    brand_media.set_backend(None)
    obar.reset()


def test_recursos_del_bucket_lista_blanca_huella_y_cache(bucket):
    data = b"glTF" + b"\x02\x00\x00\x00" + b"x" * 64
    bucket.objects[obar.PREFIX + "personajes/Ch01_nonPBR.glb"] = data
    bucket.objects[obar.MANIFEST_KEY] = json.dumps({"version": "1", "files": {
        "personajes/Ch01_nonPBR.glb": {"bytes": len(data), "sha": hashlib.sha256(data).hexdigest()},
        "../secreto.glb": {"bytes": 1, "sha": "0" * 64}, "personajes/sin_huella.glb": {"bytes": 3}}}).encode()
    man = asyncio.run(obar.manifest())
    assert list(man["files"]) == ["personajes/Ch01_nonPBR.glb"], "solo nombres válidos y con huella"
    got = asyncio.run(obar.read("personajes/Ch01_nonPBR.glb"))
    assert got == (data, hashlib.sha256(data).hexdigest())
    n = bucket.gets
    asyncio.run(obar.read("personajes/Ch01_nonPBR.glb"))
    assert bucket.gets == n, "la segunda vez sale de la memoria"
    assert asyncio.run(obar.read("personajes/Otro.glb")) is None and asyncio.run(obar.read("../x.glb")) is None
    obar.reset()
    bucket.objects[obar.PREFIX + "personajes/Ch01_nonPBR.glb"] = b"glTF" + b"y" * 68
    with pytest.raises(obar.Unavailable):
        asyncio.run(obar.read("personajes/Ch01_nonPBR.glb"))
    bucket.objects.clear()
    obar.reset()
    with pytest.raises(obar.Unavailable):
        asyncio.run(obar.manifest())


def test_pantalla_de_canciones_y_desde_donde():
    tables = [f"Mesa {i}" for i in range(1, 11)]
    assert ov.song_place("Mesa 4", tables) == "Mesa 4"
    assert ov.song_place("mesa-7", tables) == "Mesa 7"
    assert ov.song_place("Barra 3", tables) == "Barra · silla 3" and ov.song_place("barra", tables) == "Barra"
    assert ov.song_place("Barcelona", tables) == "Barcelona" and ov.song_place("", tables) == ""
    items = [{"title": "A", "state": "pendiente", "at": "2026-11-11T22:00:00", "table": "Mesa 1"},
             {"title": "B", "state": "sonando", "at": "2026-11-11T21:00:00", "playing_at": "2026-11-11T22:05:00", "table": "Mesa 4"},
             {"title": "C", "state": "pendiente", "at": "2026-11-11T21:30:00", "table": "Barra · silla 3"},
             {"title": "D", "state": "reproducida", "at": "2026-11-11T20:00:00", "table": "Mesa 2"},
             {"title": "E", "state": "pendiente", "at": "2026-11-11T22:10:00", "table": "Mesa 5"},
             {"title": "F", "state": "pendiente", "at": "2026-11-11T22:20:00", "table": "Mesa 6"}]
    sc = ov.song_screen(items)
    assert sc["now"] == {"title": "B", "table": "Mesa 4", "since": "2026-11-11T22:05:00"}
    assert [q["title"] for q in sc["queue"]] == ["C", "A", "E"]
    assert ov.song_screen([]) == {"now": None, "queue": []}


def test_motor_del_bar_sin_cdn_sin_codigo_en_linea_y_con_transiciones():
    from app.web import oficina_routes as routes

    bar = (ROOT / "app/web/oficina/oficina_bar.js").read_text(encoding="utf-8")
    rules = (ROOT / "app/web/oficina/oficina_bar_rules.js").read_text(encoding="utf-8")
    for imp in re.findall(r"^import .* from '([^']+)';$", bar, re.M):
        assert imp == "three" or imp == "/admin-v2plus/oficina/bar_reglas.js" or "examples/jsm/" + imp.removeprefix("three/addons/") in routes.THREE, imp
    assert "import " not in rules
    for body in (bar, rules):
        assert not re.search(r"https?://", body), "sin CDN ni URL externas"
        assert ' style="' not in body and not re.search(r"<[a-z][^>]*\son[a-z]+=", body, re.I)
    assert "crossFadeTo" in bar and "AnimationMixer" in bar and "SkeletonUtils" in bar
    assert "UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), .4, .45, .92)" in bar, "brillo suave como bar.html"
    assert "'/admin-v2plus/oficina/bar/'" in bar, "los .glb de Mixamo solo por la ruta con sesión"
    assert routes.ASSETS["bar.js"][0] == "oficina/oficina_bar.js" and routes.ASSETS["bar_reglas.js"][0] == "oficina/oficina_bar_rules.js"
    app_js = (ROOT / "app/web/oficina/oficina_app.js").read_text(encoding="utf-8")
    assert "import('/admin-v2plus/oficina/bar.js')" in app_js, "el bar se carga solo al abrir ese piso"
