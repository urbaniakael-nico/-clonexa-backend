"""Oficina 3D · prepara los recursos realistas (CC0) que sirve el backend.

Uso (una vez, en el PC del dueño o en CI; no corre en produccion):
    py -3.11 ops/oficina/preparar_recursos.py --gltf-transform <ruta a gltf-transform(.cmd)>

1. Baja de Poly Haven (API publica, todo CC0) los modelos, texturas y el HDRI de RECURSOS.
2. Comprime los modelos con gltf-transform: meshopt + texturas WebP de 1024 px como maximo.
3. Pasa las texturas PBR a WebP (1024 px) con Pillow.
4. Si existe C:/Users/valef/Desktop/clonexa-assets/ con los paquetes CC0 de Quaternius
   (Universal Base Characters y Universal Animation Library, ver docs/oficina/LICENCIAS.md),
   copia y comprime los personajes y las animaciones que pide PERSONAJES.
5. Escribe app/web/oficina/recursos/manifest.json (archivo -> bytes, sha256, fuente y licencia).

Nada de esto pasa por Postgres: son archivos estaticos del repo servidos con sesion de Admin V2.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "app" / "web" / "oficina" / "recursos"
ASSETS_DIR = Path("C:/Users/valef/Desktop/clonexa-assets")
API = "https://api.polyhaven.com"
UA = {"User-Agent": "clonexa-oficina-recursos/1.0"}

# clave -> (id de Poly Haven, autor) ; todos CC0 1.0
MODELOS = {
    "taburete": "bar_chair_round_01",
    "mesa": "round_wooden_table_01",
    "silla": "gallinera_chair",
    "sofa": "Sofa_01",
    "botellas": "wine_bottles_01",
    "lampara": "hanging_industrial_lamp",
    "planta": "potted_plant_04",
    "caja": "CashRegister_01",
    "barril": "wine_barrel_01",
}
TEXTURAS = {
    "piso": "herringbone_parquet",
    "pared": "dark_brick_wall",
    "tela": "velour_velvet",
    "cuero": "leather_red_02",
    "metal": "metal_plate",
    "madera": "wood_table_001",
    "concreto": "concrete_floor_02",
}
HDRI = "warm_bar"
# Se repiten muchas veces en el piso (40 sillas, 6 taburetes, botellas): se simplifican para la meta de FPS.
SIMPLIFY = {"silla": 0.18, "taburete": 0.25, "botellas": 0.2, "lampara": 0.3, "planta": 0.35, "mesa": 0.5, "barril": 0.4, "caja": 0.5}
MAPS = {"diff": "Diffuse", "nor_gl": "nor_gl", "arm": "arm"}

# Personajes (Quaternius, CC0). Se buscan por nombre dentro de los .zip de clonexa-assets.
PERSONAJES = {
    "zip_personajes": "Universal Base Characters[Standard].zip",
    "zip_animaciones": "Universal Animation Library[Standard].zip",
    # archivo (sin extension, en "Base Characters/Godot - UE": mismo esqueleto que la libreria de animaciones) -> nombre servido
    "cuerpos": {"Superhero_Male_FullBody": "superhero_male", "Superhero_Female_FullBody": "superhero_female"},
}


def get_json(url: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def info(asset: str) -> dict:
    d = get_json(f"{API}/info/{asset}")
    return {"id": asset, "name": d.get("name") or asset, "authors": sorted((d.get("authors") or {}).keys()),
            "url": f"https://polyhaven.com/a/{asset}", "license": "CC0 1.0"}


def run(cmd: list[str]) -> None:
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


def model(key: str, asset: str, tmp: Path, gt: str) -> dict:
    files = get_json(f"{API}/files/{asset}")["gltf"]["1k"]["gltf"]
    base = tmp / asset
    download(files["url"], base / Path(files["url"]).name)
    for rel, meta in files["include"].items():
        download(meta["url"], base / rel)
    src = base / Path(files["url"]).name
    dest = OUT / "modelos" / f"{key}.glb"
    dest.parent.mkdir(parents=True, exist_ok=True)
    ratio = SIMPLIFY.get(key)
    simp = ["--simplify", "true", "--simplify-ratio", str(ratio), "--simplify-error", "0.002"] if ratio else ["--simplify", "false"]
    size = "512" if key in ("silla", "taburete", "botellas", "lampara", "planta") else "1024"
    run([gt, "optimize", str(src), str(dest), "--compress", "meshopt", "--texture-compress", "webp", "--texture-size", size, *simp])
    return info(asset)


def texture(key: str, asset: str, tmp: Path) -> dict:
    from PIL import Image

    files = get_json(f"{API}/files/{asset}")
    for short, name in MAPS.items():
        entry = (files.get(name) or files.get(short) or {}).get("1k", {}).get("jpg")
        if not entry:
            continue
        src = tmp / f"{asset}_{short}.jpg"
        download(entry["url"], src)
        dest = OUT / "texturas" / f"{key}_{short}.webp"
        dest.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as im:
            im = im.convert("RGB")
            im.thumbnail((1024, 1024))
            im.save(dest, "WEBP", quality=78, method=6)
    return info(asset)


def hdri(tmp: Path) -> dict:
    entry = get_json(f"{API}/files/{HDRI}")["hdri"]["1k"]["hdr"]
    dest = OUT / "hdri" / f"{HDRI}_1k.hdr"
    download(entry["url"], dest)
    return info(HDRI)


def characters(tmp: Path, gt: str) -> dict:
    """Personajes y animaciones de Quaternius si el dueño ya los dejo en clonexa-assets."""
    zp, za = ASSETS_DIR / PERSONAJES["zip_personajes"], ASSETS_DIR / PERSONAJES["zip_animaciones"]
    if not zp.exists() or not za.exists():
        print("Personajes: faltan los .zip de Quaternius en", ASSETS_DIR, "(el piso usa los personajes de respaldo)")
        return {}
    out: dict = {}
    for zpath, kind in ((zp, "personaje"), (za, "animaciones")):
        target = tmp / kind
        with zipfile.ZipFile(zpath) as z:
            z.extractall(target)
        fix_uris(target)
        glbs = sorted(target.rglob("*.glb")) + sorted(target.rglob("*.gltf"))
        if kind == "animaciones":
            # la version sin "root motion" (_RM): el motor mueve a la persona por su cuenta
            pick = [g for g in glbs if g.stem.lower().startswith("ual") and not g.stem.lower().endswith("_rm")][:1]
            names = {"animaciones": pick}
        else:
            names = {out: [g for g in glbs if g.stem == stem and "godot - ue" in g.as_posix().lower()][:1] for stem, out in PERSONAJES["cuerpos"].items()}
        for name, found in names.items():
            if not found:
                print("Personajes: no encontre", name, "en", zpath.name)
                continue
            dest = OUT / "personajes" / f"{name.lower()}.glb"
            dest.parent.mkdir(parents=True, exist_ok=True)
            run([gt, "optimize", str(found[0]), str(dest), "--compress", "meshopt", "--texture-compress", "webp", "--texture-size", "1024",
                 "--simplify", "false"])
            out[name.lower()] = {"id": found[0].stem, "name": found[0].stem, "authors": ["Quaternius"], "license": "CC0 1.0",
                                 "url": "https://quaternius.com/packs/" + ("universalanimationlibrary.html" if kind == "animaciones" else "universalbasecharacters.html")}
    return out


def fix_uris(folder: Path) -> None:
    """El paquete de Quaternius nombra algunas texturas "X_png.png" pero trae "X.png": se corrige el .gltf (copia temporal)."""
    for g in folder.rglob("*.gltf"):
        data = json.loads(g.read_text(encoding="utf-8"))
        changed = False
        for img in data.get("images") or []:
            uri = img.get("uri") or ""
            if uri and not (g.parent / uri).exists() and (g.parent / uri.replace("_png.png", ".png")).exists():
                img["uri"] = uri.replace("_png.png", ".png")
                changed = True
        if changed:
            g.write_text(json.dumps(data), encoding="utf-8")


def manifest(sources: dict) -> dict:
    files = {}
    for p in sorted(OUT.rglob("*")):
        if p.is_file() and p.name != "manifest.json":
            rel = p.relative_to(OUT).as_posix()
            data = p.read_bytes()
            files[rel] = {"bytes": len(data), "sha": hashlib.sha256(data).hexdigest()[:12]}
    return {"version": 1, "templates": {"bar": sorted(files)}, "files": files, "sources": sources}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gltf-transform", required=True)
    ap.add_argument("--solo-personajes", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    old = json.loads((OUT / "manifest.json").read_text(encoding="utf-8")) if (OUT / "manifest.json").exists() else {}
    sources = dict(old.get("sources") or {})
    with tempfile.TemporaryDirectory(prefix="cx_ofi_") as t:
        tmp = Path(t)
        if not a.solo_personajes:
            for key, asset in MODELOS.items():
                sources[f"modelos/{key}.glb"] = model(key, asset, tmp, a.gltf_transform)
            for key, asset in TEXTURAS.items():
                meta = texture(key, asset, tmp)
                for short in MAPS:
                    sources[f"texturas/{key}_{short}.webp"] = meta
            sources[f"hdri/{HDRI}_1k.hdr"] = hdri(tmp)
        for name, meta in characters(tmp, a.gltf_transform).items():
            sources[f"personajes/{name}.glb"] = meta
    m = manifest(sources)
    m["sources"] = {k: v for k, v in sources.items() if k in m["files"]}
    (OUT / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(f["bytes"] for f in m["files"].values())
    print(f"Listo: {len(m['files'])} archivos, {total / 1024 / 1024:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
