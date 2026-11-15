"""Biblioteca del Modo constructor (consola v2+, solo Admin V2): catalogo de objetos e importacion de modelos 3D.

- Catalogo: tabla constructor_catalogo (sembrada por 025u con app/services/constructor_catalogo.json). Estados:
  'publicado' (aparece en el constructor de TODAS las empresas), 'revision' (subido, espera la aprobacion del dueno),
  'fase2' (personajes o archivos con esqueleto: guardados, todavia no entran al constructor), 'rechazado'.
- Subir: GLB, GLTF, FBX, OBJ o ZIP (max 50 MB). Se valida el tipo REAL (bytes, no la extension), el ZIP es seguro
  (sin rutas absolutas ni "..", sin ejecutables, sin enlaces, limite de archivos y de tamano descomprimido) y se
  convierte con constructor_glb (centrado, apoyado, escala real, WebP 1024, miniatura). Licencia obligatoria.
- Archivos: bucket PRIVADO (prefijo constructor/catalogo/), nunca Postgres; se sirven solo con sesion valida.
- Poly Haven: buscador con su API publica (modelos CC0) con User-Agent propio (condiciones de su API) e
  importacion al mismo flujo.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import re
import stat
import time
import zipfile
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import constructor_glb as cg

MAX_UPLOAD = 50 * 1024 * 1024
MAX_UNZIPPED = 200 * 1024 * 1024
MAX_ZIP_FILES = 400
PREFIX = "constructor/catalogo/"
SEED = Path(__file__).resolve().parent / "constructor_catalogo.json"
CATEGORIES = ("barra", "sonido", "neveras", "mesas", "pantallas", "cocina", "caja", "taller", "oficina", "tienda", "bodega", "luces",
              "decoracion", "exterior", "banos")
CATEGORY_LABEL = {"barra": "Barra", "sonido": "Sonido", "neveras": "Neveras", "mesas": "Mesas y asientos", "pantallas": "Pantallas",
                  "cocina": "Cocina", "caja": "Caja", "taller": "Taller", "oficina": "Oficina y call center", "tienda": "Tienda",
                  "bodega": "Bodega y campo", "luces": "Luces", "decoracion": "Decoración", "exterior": "Exterior", "banos": "Baños"}
LICENSES = {"cc0": "CC0 1.0", "ccby": "CC-BY 4.0", "mixamo": "Mixamo (uso en el producto, no redistribuible)", "propia": "Propia"}
CONNECTABLE = ("ninguno", "mesa", "puesto", "escritorio", "caja", "pantalla")
STATES = ("publicado", "revision", "fase2", "rechazado")
EXEC_EXT = re.compile(r"\.(exe|dll|bat|cmd|sh|ps1|js|mjs|vbs|jar|msi|com|scr|py|php|html?|svg|so|dylib|app)$", re.I)
ALLOWED_IN_ZIP = re.compile(r"\.(glb|gltf|bin|obj|mtl|fbx|png|jpe?g|webp|ktx2|txt|md|license)$", re.I)
SLUG_RE = re.compile(r"[^a-z0-9]+")
POLYHAVEN = "https://api.polyhaven.com"
POLYHAVEN_HOSTS = ("dl.polyhaven.org", "dl.polyhaven.com", "cdn.polyhaven.com")
USER_AGENT = "Clonexa-Constructor/1.0"


class Rejected(ValueError):
    pass


# ------------------------------------------------------------------ catalogo
def seed_items() -> list[dict]:
    out = []
    for it in json.loads(SEED.read_text(encoding="utf-8"))["items"]:
        rec = it.get("o") == "recurso"
        out.append({"id": it["id"], "nombre": it["n"], "categoria": it["c"], "zonas": it.get("z", []), "origen": "recurso" if rec else "clonexa",
                    "forma": it["f"], "archivo": it.get("a"), "medidas": {"w": it["s"][0], "d": it["s"][1], "h": it["s"][2]},
                    "variantes": it.get("v", []), "conectable": it.get("k"), "capa": it.get("l", "muebles"), "icono": it.get("i"),
                    "licencia": "CC0 1.0" if rec else "Propio (Clonexa)", "fuente": it.get("src") or ("Poly Haven" if rec else "Clonexa · generado por código"),
                    "autor": it.get("au") or ("" if rec else "Clonexa"), "atribucion": None, "estado": "publicado", "bytes": 0, "poligonos": 0})
    return out


COLS = ("id, nombre, categoria, zonas, origen, forma, archivo, miniatura, medidas, variantes, conectable, capa, icono, licencia, fuente, autor, "
        "atribucion, estado, bytes, poligonos, notas, created_at")


def _out(r: Any) -> dict:
    d = dict(r)
    for k in ("zonas", "medidas", "variantes"):
        if isinstance(d.get(k), str):
            d[k] = json.loads(d[k])
    if d.get("created_at") is not None and not isinstance(d["created_at"], str):
        d["created_at"] = d["created_at"].isoformat()
    return d


async def catalog(db: AsyncSession, states: tuple[str, ...] = ("publicado",)) -> list[dict]:
    try:
        rows = (await db.execute(text(f"SELECT {COLS} FROM constructor_catalogo WHERE estado = ANY(:s) ORDER BY categoria, nombre"),
                                 {"s": list(states)})).mappings().all()
    except Exception:
        await db.rollback()
        return [x for x in seed_items() if x["estado"] in states]
    return [_out(r) for r in rows]


async def item(db: AsyncSession, item_id: str) -> Optional[dict]:
    r = (await db.execute(text(f"SELECT {COLS} FROM constructor_catalogo WHERE id = :i"), {"i": item_id})).mappings().first()
    return _out(r) if r else None


def sizes(items: list[dict]) -> dict[str, dict]:
    return {x["id"]: {**(x.get("medidas") or {}), "conectable": x.get("conectable")} for x in items}


def stats(items: list[dict]) -> dict:
    by: dict[str, int] = {}
    for x in items:
        by[x["categoria"]] = by.get(x["categoria"], 0) + 1
    return {"total": len(items), "por_categoria": by, "bytes": sum(int(x.get("bytes") or 0) for x in items)}


# ------------------------------------------------------------------ validacion de archivos subidos
def sniff(name: str, raw: bytes) -> str:
    """Tipo REAL del archivo por sus bytes (la extension solo desempata gltf/obj, que son texto)."""
    if raw[:4] == b"glTF":
        return "glb"
    if raw[:4] == b"PK\x03\x04":
        return "zip"
    if raw[:21] == b"Kaydara FBX Binary  \x00":
        return "fbx"
    head = raw[:4096].lstrip()
    low = name.lower()
    if low.endswith(".gltf") and head.startswith(b"{") and b'"asset"' in raw[:200_000]:
        return "gltf"
    if low.endswith(".obj") and _looks_obj(raw[:65536]):
        return "obj"
    if low.endswith(".fbx") and (head.startswith(b";") or b"FBXHeaderExtension" in raw[:4096]):
        return "fbx"
    raise Rejected("El archivo no es un modelo 3D válido (GLB, GLTF, FBX, OBJ o ZIP).")


def _looks_obj(head: bytes) -> bool:
    try:
        txt = head.decode("utf-8")
    except UnicodeDecodeError:
        return False
    lines = [ln.split()[0] for ln in txt.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    return bool(lines) and all(tok in ("v", "vt", "vn", "f", "g", "o", "s", "usemtl", "mtllib", "l", "vp") for tok in lines[:200]) and "v" in lines


def safe_unzip(raw: bytes) -> dict[str, bytes]:
    """ZIP seguro: sin rutas absolutas, '..', unidades de Windows ni enlaces; sin ejecutables ni tipos no esperados;
    limite de archivos, de tamano descomprimido y de razon de compresion (bombas)."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise Rejected("El ZIP está dañado.") from None
    infos = zf.infolist()
    if len(infos) > MAX_ZIP_FILES:
        raise Rejected("El ZIP tiene demasiados archivos.")
    out: dict[str, bytes] = {}
    total = 0
    for info in infos:
        name = info.filename.replace("\\", "/")
        if info.is_dir():
            continue
        parts = name.split("/")
        if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or ".." in parts or any(p.startswith("~") for p in parts):
            raise Rejected(f"El ZIP tiene una ruta peligrosa ({name[:60]}).")
        mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(mode):
            raise Rejected("El ZIP tiene enlaces simbólicos.")
        if EXEC_EXT.search(name):
            raise Rejected(f"El ZIP tiene un archivo no permitido ({parts[-1][:40]}).")
        if parts[-1].startswith(".") or "__MACOSX" in parts:
            continue
        if not ALLOWED_IN_ZIP.search(name):
            raise Rejected(f"El ZIP tiene un tipo de archivo no permitido ({parts[-1][:40]}).")
        if info.file_size > MAX_UNZIPPED or (info.compress_size and info.file_size / max(info.compress_size, 1) > 200):
            raise Rejected("El ZIP parece una bomba de compresión.")
        total += info.file_size
        if total > MAX_UNZIPPED:
            raise Rejected("El ZIP descomprimido pasa de 200 MB.")
        data = zf.read(info)
        if len(data) != info.file_size:
            raise Rejected("El ZIP está dañado.")
        out[name] = data
    if not out:
        raise Rejected("El ZIP está vacío.")
    return out


def convert(name: str, raw: bytes, height: Optional[float], width: Optional[float]) -> cg.Prepared:
    """Archivo subido -> Prepared (GLB listo + miniatura). Lanza Rejected con un mensaje para la pantalla."""
    if not raw:
        raise Rejected("Archivo vacío.")
    if len(raw) > MAX_UPLOAD:
        raise Rejected("El archivo pasa de 50 MB.")
    kind = sniff(name, raw)
    try:
        if kind == "zip":
            files = safe_unzip(raw)
            main = _main_file(files)
            base = main.rsplit("/", 1)[0] if "/" in main else ""
            k = sniff(main.rsplit("/", 1)[-1], files[main])
            return _convert_one(k, files[main], files, base, height, width)
        return _convert_one(kind, raw, {}, "", height, width)
    except cg.Bad as error:
        raise Rejected(str(error)) from None
    except (struct_error(), ValueError, KeyError, IndexError, TypeError, zipfile.BadZipFile) as error:
        if isinstance(error, Rejected):
            raise
        raise Rejected("No se pudo leer el modelo: el archivo está dañado o usa un formato no soportado.") from None


def struct_error() -> type:
    import struct

    return struct.error


def _main_file(files: dict[str, bytes]) -> str:
    for ext in (".glb", ".gltf", ".fbx", ".obj"):
        found = sorted((k for k in files if k.lower().endswith(ext)), key=lambda k: (k.count("/"), len(k)))
        if found:
            return found[0]
    raise Rejected("El ZIP no trae un modelo (GLB, GLTF, FBX u OBJ).")


def _convert_one(kind: str, raw: bytes, files: dict[str, bytes], base: str, height: Optional[float], width: Optional[float]) -> cg.Prepared:
    if kind == "glb":
        return cg.prepare(cg.Gltf.from_glb(raw), height, width)
    if kind == "gltf":
        return cg.prepare(cg.Gltf.from_gltf(raw, files, base), height, width)
    if kind == "obj":
        return cg.prepare(cg.Gltf.from_glb(cg.obj_to_glb(raw, files, base)), height, width)
    if kind == "fbx":
        glb, rigged = cg.fbx_to_glb(raw)
        return cg.prepare(cg.Gltf.from_glb(glb), height, width, rigged=rigged)
    raise Rejected("Formato no soportado.")


# ------------------------------------------------------------------ formulario (obligatorio)
def clean_form(f: dict) -> dict:
    name = str(f.get("nombre") or "").strip()
    if not (2 <= len(name) <= 60):
        raise Rejected("Escribe el nombre del objeto (2 a 60 caracteres).")
    cat = f.get("categoria")
    if cat not in CATEGORIES:
        raise Rejected("Elige la categoría.")
    zones = f.get("zonas") or []
    if isinstance(zones, str):
        zones = [z for z in zones.split(",") if z]
    from app.services.constructor_plano import ZONE_KINDS

    if not zones or any(z not in ZONE_KINDS for z in zones):
        raise Rejected("Elige al menos una zona sugerida.")
    con = f.get("conectable") or "ninguno"
    if con not in CONNECTABLE:
        raise Rejected("Tipo conectable no válido.")
    lic = f.get("licencia")
    if lic not in LICENSES:
        raise Rejected("Sin licencia no se publica: elige la licencia del modelo.")
    src = str(f.get("fuente") or "").strip()
    if lic != "propia" and not re.match(r"^https://[^\s]{4,300}$", src):
        raise Rejected("Escribe la URL de la fuente (https://...).")
    attribution = str(f.get("atribucion") or "").strip()
    if lic == "ccby" and len(attribution) < 3:
        raise Rejected("CC-BY exige la atribución (autor y obra).")
    h, w = _measure(f.get("alto")), _measure(f.get("ancho"))
    if not h and not w:
        raise Rejected("Escribe el alto o el ancho real del objeto (en metros).")
    return {"nombre": name, "categoria": cat, "zonas": zones[:8], "conectable": None if con == "ninguno" else con, "licencia": LICENSES[lic],
            "licencia_clave": lic, "fuente": src[:300] or None, "autor": str(f.get("autor") or "").strip()[:120] or None,
            "atribucion": attribution[:300] or None, "alto": h, "ancho": w}


def _measure(v: Any) -> Optional[float]:
    if v in (None, ""):
        return None
    try:
        f = float(str(v).replace(",", "."))
    except ValueError:
        raise Rejected("Medida no válida.") from None
    if not (0.02 <= f <= 15):
        raise Rejected("La medida real debe estar entre 0,02 y 15 metros.")
    return f


def new_id(name: str, raw_sha: str) -> str:
    slug = SLUG_RE.sub("_", name.lower().encode("ascii", "ignore").decode()).strip("_")[:30] or "objeto"
    return f"sub_{slug}_{raw_sha[:6]}"


# ------------------------------------------------------------------ bucket privado
def keys_for(item_id: str, sha: str) -> tuple[str, str]:
    return f"{PREFIX}{item_id}/{sha[:16]}.glb", f"{PREFIX}{item_id}/{sha[:16]}.webp"


def put(key: str, data: bytes, content_type: str) -> None:
    from app.services import brand_media

    brand_media.put_private(key, data, content_type)


def get(key: str) -> bytes:
    from app.services import brand_media

    return brand_media.backend().get(key)


async def store(db: AsyncSession, form: dict, prep: cg.Prepared, raw_sha: str, actor: str) -> dict:
    item_id = new_id(form["nombre"], raw_sha)
    glb_key, thumb_key = keys_for(item_id, hashlib.sha256(prep.glb).hexdigest())
    await asyncio.to_thread(put, glb_key, prep.glb, "model/gltf-binary")
    await asyncio.to_thread(put, thumb_key, prep.thumb, "image/webp")
    estado = "fase2" if prep.rigged else "revision"
    notes = "; ".join(prep.warnings + (["Tiene esqueleto: queda para la fase 2 (personajes)."] if prep.rigged else []) +
                      ["Sin compresión meshopt (pendiente)."])
    await db.execute(text("""
        INSERT INTO constructor_catalogo (id, nombre, categoria, zonas, origen, forma, archivo, miniatura, medidas, variantes, conectable, capa, icono,
                                          licencia, fuente, autor, atribucion, estado, bytes, poligonos, notas, creado_por)
        VALUES (:id, :n, :c, CAST(:z AS jsonb), 'bucket', 'glb', :a, :m, CAST(:med AS jsonb), '[]'::jsonb, :k, 'muebles', '📦',
                :lic, :src, :au, :at, :e, :b, :p, :notas, :who)
        ON CONFLICT (id) DO UPDATE SET archivo = EXCLUDED.archivo, miniatura = EXCLUDED.miniatura, medidas = EXCLUDED.medidas, bytes = EXCLUDED.bytes,
            poligonos = EXCLUDED.poligonos, estado = EXCLUDED.estado, notas = EXCLUDED.notas, updated_at = now()
    """), {"id": item_id, "n": form["nombre"], "c": form["categoria"], "z": json.dumps(form["zonas"]), "a": glb_key, "m": thumb_key,
           "med": json.dumps(prep.size), "k": form["conectable"], "lic": form["licencia"], "src": form["fuente"], "au": form["autor"],
           "at": form["atribucion"], "e": estado, "b": len(prep.glb) + len(prep.thumb), "p": prep.tris, "notas": notes[:500], "who": actor[:120]})
    await db.commit()
    return {"id": item_id, "estado": estado, "tris": prep.tris, "size": prep.size, "bytes": len(prep.glb), "warnings": prep.warnings,
            "rigged": prep.rigged}


async def set_state(db: AsyncSession, item_id: str, state: str, actor: str) -> bool:
    if state not in ("publicado", "rechazado"):
        raise Rejected("Estado no válido.")
    cur = await item(db, item_id)
    if not cur or cur["origen"] != "bucket":
        return False
    if cur["estado"] == "fase2" and state == "publicado":
        raise Rejected("Los personajes y modelos con esqueleto quedan para la fase 2.")
    if state == "publicado" and not cur.get("licencia"):
        raise Rejected("Sin licencia no se publica.")
    await db.execute(text("""UPDATE constructor_catalogo SET estado = :s, aprobado_por = :a, aprobado_at = now(), updated_at = now() WHERE id = :i"""),
                     {"s": state, "a": actor[:120], "i": item_id})
    await db.commit()
    return True


# ------------------------------------------------------------------ Poly Haven (API publica, modelos CC0)
_PH: dict[str, tuple[float, Any]] = {}
PH_TTL = 3600.0


async def _ph_get(url: str, client: Any = None) -> Any:
    import httpx

    hit = _PH.get(url)
    if hit and time.monotonic() - hit[0] < PH_TTL:
        return hit[1]
    async with (client or httpx.AsyncClient(timeout=20, headers={"User-Agent": USER_AGENT}, follow_redirects=False)) as c:
        r = await c.get(url, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        data = r.json()
    _PH[url] = (time.monotonic(), data)
    return data


async def polyhaven_search(q: str, client: Any = None) -> list[dict]:
    data = await _ph_get(f"{POLYHAVEN}/assets?t=models", client)
    words = [w for w in re.split(r"\s+", (q or "").lower().strip()) if w]
    out = []
    for aid, a in (data or {}).items():
        hay = " ".join([aid, str(a.get("name", "")), " ".join(a.get("tags") or []), " ".join(a.get("categories") or [])]).lower()
        if all(w in hay for w in words):
            out.append({"id": aid, "nombre": a.get("name") or aid, "categorias": a.get("categories") or [], "autores": list((a.get("authors") or {}).keys()),
                        "miniatura": a.get("thumbnail_url"), "url": f"https://polyhaven.com/a/{aid}", "licencia": "CC0 1.0"})
    out.sort(key=lambda x: x["nombre"])
    return out[:60]


def _ph_url_ok(url: str) -> bool:
    from urllib.parse import urlparse

    u = urlparse(str(url or ""))
    return u.scheme == "https" and u.hostname in POLYHAVEN_HOSTS


async def polyhaven_fetch(asset_id: str, client: Any = None) -> tuple[bytes, dict[str, bytes], str, dict]:
    """Descarga el glTF 1k de un modelo (y sus texturas) -> (gltf, archivos, base, info). Solo hosts de Poly Haven."""
    import httpx

    if not re.match(r"^[A-Za-z0-9_\-]{2,80}$", asset_id or ""):
        raise Rejected("Modelo de Poly Haven no válido.")
    info = await _ph_get(f"{POLYHAVEN}/info/{asset_id}", client)
    files = await _ph_get(f"{POLYHAVEN}/files/{asset_id}", client)
    if (info or {}).get("type") not in (2, None):
        raise Rejected("Ese recurso de Poly Haven no es un modelo.")
    g = ((files or {}).get("gltf") or {})
    res = g.get("1k") or g.get("2k") or (next(iter(g.values())) if g else None)
    main = (res or {}).get("gltf")
    if not main or not _ph_url_ok(main.get("url")):
        raise Rejected("Ese modelo no tiene glTF descargable en Poly Haven.")
    out: dict[str, bytes] = {}
    total = 0
    async with (client or httpx.AsyncClient(timeout=60, headers={"User-Agent": USER_AGENT}, follow_redirects=False)) as c:
        async def fetch(url: str) -> bytes:
            nonlocal total
            if not _ph_url_ok(url):
                raise Rejected("Poly Haven devolvió un enlace fuera de su dominio.")
            r = await c.get(url, headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            total += len(r.content)
            if total > MAX_UPLOAD * 2:
                raise Rejected("El modelo de Poly Haven es demasiado pesado.")
            return r.content
        gltf = await fetch(main["url"])
        for rel, meta in (main.get("include") or {}).items():
            if ".." in rel.split("/") or rel.startswith("/"):
                raise Rejected("Ruta no válida en Poly Haven.")
            out[rel] = await fetch(meta["url"])
    meta = {"nombre": (info or {}).get("name") or asset_id, "autor": ", ".join((info or {}).get("authors", {}).keys()) or None,
            "fuente": f"https://polyhaven.com/a/{asset_id}"}
    return gltf, out, "", meta


def convert_gltf(gltf: bytes, files: dict[str, bytes], height: Optional[float], width: Optional[float]) -> cg.Prepared:
    try:
        return cg.prepare(cg.Gltf.from_gltf(gltf, files, ""), height, width)
    except cg.Bad as error:
        raise Rejected(str(error)) from None


__all__ = ["catalog", "convert", "clean_form", "store", "set_state", "polyhaven_search", "polyhaven_fetch", "sniff", "safe_unzip"]
