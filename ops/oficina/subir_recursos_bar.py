"""Sube los personajes y animaciones de Mixamo del bar aprobado al bucket PRIVADO de Clonexa.

Los archivos de Mixamo NO pueden estar en el repositorio (es publico y la licencia prohibe redistribuirlos
sueltos). Viven fuera del repo (p. ej. Desktop/clonexa-assets/oficina-bar/procesados) y se suben con este
guion a  oficina/bar/v1/{personajes|animaciones}/<archivo>.glb  + oficina/bar/v1/manifest.json.
El backend los sirve solo con sesion de Admin V2 (app/services/oficina_bar.py).

Uso (las variables CLONEXA_BUCKET_* las pone Railway; el guion nunca las imprime):
    railway run --service=-clonexa-backend py -3.11 ops/oficina/subir_recursos_bar.py "C:/ruta/procesados"
    ... --dry-run   solo revisa y muestra lo que subiria.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.services import brand_media  # noqa: E402
from app.services import oficina_bar as obar  # noqa: E402

KINDS = ("personajes", "animaciones")


def collect(folder: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for kind in KINDS:
        for f in sorted((folder / kind).glob("*.glb")):
            name = f"{kind}/{f.name}"
            if not obar.valid_name(name):
                raise SystemExit(f"Nombre no valido: {name}")
            data = f.read_bytes()
            if data[:4] != b"glTF" or len(data) > obar.FILE_MAX:
                raise SystemExit(f"No es un .glb valido o pesa mas de {obar.FILE_MAX // 1024 // 1024} MB: {name}")
            out[name] = data
    if not out:
        raise SystemExit(f"No hay .glb en {folder}/personajes ni {folder}/animaciones")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("carpeta", help="carpeta 'procesados' (con personajes/ y animaciones/)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    files = collect(Path(args.carpeta))
    manifest = {"version": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
                "files": {n: {"bytes": len(d), "sha": hashlib.sha256(d).hexdigest()} for n, d in files.items()}}
    total = sum(len(d) for d in files.values())
    for n, d in files.items():
        print(f"  {n}  {len(d) / 1024:.0f} KB")
    print(f"{len(files)} archivos, {total / 1024 / 1024:.2f} MB")
    if args.dry_run:
        return
    store = brand_media.S3Backend()
    for n, d in files.items():
        store.put(obar.PREFIX + n, d, content_type="model/gltf-binary", private=True)
    store.put(obar.MANIFEST_KEY, json.dumps(manifest, indent=1).encode("utf-8"), content_type="application/json", private=True)
    back = json.loads(store.get(obar.MANIFEST_KEY))
    assert back["files"] == manifest["files"], "el manifiesto leido no coincide"
    print(f"Subido a {obar.PREFIX} (bucket privado). Version {manifest['version']}.")


if __name__ == "__main__":
    main()
