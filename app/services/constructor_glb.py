"""Biblioteca del Modo constructor: conversion y preparacion de modelos 3D en el servidor, en Python puro
(numpy + Pillow; sin binarios externos).

Entrada: GLB, GLTF (+ .bin y texturas, dentro de un ZIP o con data URIs), OBJ (+ .mtl y texturas) o FBX binario.
Salida (Prepared): un GLB listo para el catalogo:
- centrado en x/z y apoyado en el piso (y = 0), escalado a la medida REAL que pidio el formulario (alto o ancho);
- texturas re-codificadas a WebP de maximo 1024 px (EXT_texture_webp, que three.js lee);
- conteo de triangulos (aviso desde WARN_TRIS, rechazo desde MAX_TRIS);
- esqueleto detectado (skins / huesos FBX) -> "para fase 2" (personajes: no entran al constructor todavia);
- miniatura WebP 256 px dibujada por software (proyeccion isometrica, sombreado plano, pintor por profundidad).
La compresion meshopt NO se aplica aqui (necesita gltfpack/meshoptimizer, pendientes de aprobar como dependencia).
"""
from __future__ import annotations

import io
import json
import math
import struct
import zlib
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
from PIL import Image, ImageDraw

MAX_TRIS = 400_000
WARN_TRIS = 60_000
TEX_MAX = 1024
THUMB = 256


class Bad(ValueError):
    pass


@dataclass
class Prepared:
    glb: bytes
    thumb: bytes
    tris: int
    size: dict
    rigged: bool
    warnings: list[str] = field(default_factory=list)
    textures: int = 0


# ------------------------------------------------------------------ lectura glTF
COMP = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


def parse_glb(raw: bytes) -> tuple[dict, bytes]:
    if len(raw) < 20 or raw[:4] != b"glTF":
        raise Bad("No es un GLB válido.")
    _magic, version, length = struct.unpack_from("<4sII", raw, 0)
    if version != 2 or length > len(raw):
        raise Bad("GLB no soportado (solo glTF 2.0).")
    off, doc, binary = 12, None, b""
    while off + 8 <= length:
        clen, ctype = struct.unpack_from("<II", raw, off)
        chunk = raw[off + 8: off + 8 + clen]
        if ctype == 0x4E4F534A:
            doc = json.loads(chunk.decode("utf-8"))
        elif ctype == 0x004E4942:
            binary = bytes(chunk)
        off += 8 + clen + ((4 - clen % 4) % 4 if clen % 4 else 0)
    if not isinstance(doc, dict):
        raise Bad("GLB sin JSON.")
    return doc, binary


def _data_uri(uri: str) -> Optional[bytes]:
    if uri.startswith("data:"):
        import base64

        head, _, body = uri.partition(",")
        return base64.b64decode(body) if ";base64" in head else body.encode()
    return None


class Gltf:
    """glTF en memoria: doc + buffers resueltos (GLB, data URIs o archivos del ZIP)."""

    def __init__(self, doc: dict, buffers: list[bytes], files: Optional[dict[str, bytes]] = None):
        self.doc, self.buffers, self.files = doc, buffers, files or {}

    @classmethod
    def from_glb(cls, raw: bytes) -> "Gltf":
        doc, binary = parse_glb(raw)
        bufs = []
        for b in doc.get("buffers", []):
            bufs.append(binary if "uri" not in b else (_data_uri(b["uri"]) or b""))
        return cls(doc, bufs)

    @classmethod
    def from_gltf(cls, raw: bytes, files: dict[str, bytes], base: str = "") -> "Gltf":
        try:
            doc = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise Bad("El .gltf no es JSON válido.") from None
        bufs = []
        for b in doc.get("buffers", []):
            uri = b.get("uri", "")
            data = _data_uri(uri) if uri else None
            if data is None:
                data = files.get(_join(base, uri))
            if data is None:
                raise Bad(f"Falta el archivo {uri} que pide el .gltf.")
            bufs.append(data)
        for img in doc.get("images", []):
            uri = img.get("uri")
            if uri and not uri.startswith("data:") and _join(base, uri) not in files:
                raise Bad(f"Falta la textura {uri} que pide el .gltf.")
        return cls(doc, bufs, {k: v for k, v in files.items()} | {"__base__": base.encode()})

    def view(self, i: int) -> bytes:
        bv = self.doc["bufferViews"][i]
        buf = self.buffers[bv.get("buffer", 0)]
        start = bv.get("byteOffset", 0)
        return buf[start: start + bv["byteLength"]]

    def accessor(self, i: int) -> np.ndarray:
        acc = self.doc["accessors"][i]
        dt = np.dtype(COMP[acc["componentType"]])
        n, count = NCOMP[acc["type"]], acc["count"]
        if "bufferView" not in acc:
            arr = np.zeros((count, n), dtype=np.float32)
        else:
            bv = self.doc["bufferViews"][acc["bufferView"]]
            data = self.view(acc["bufferView"])
            off = acc.get("byteOffset", 0)
            stride = bv.get("byteStride") or dt.itemsize * n
            if stride == dt.itemsize * n:
                arr = np.frombuffer(data, dtype=dt, count=count * n, offset=off).reshape(count, n)
            else:
                arr = np.lib.stride_tricks.as_strided(np.frombuffer(data, dtype=np.uint8, offset=off), shape=(count, stride),
                                                      strides=(stride, 1)) if count else np.zeros((0, stride), np.uint8)
                arr = np.ascontiguousarray(arr[:, : dt.itemsize * n]).view(dt).reshape(count, n)
            arr = arr.astype(np.float32) if dt != np.float32 else arr.astype(np.float32, copy=True)
            if acc.get("normalized") and dt != np.float32:
                arr = arr / float(np.iinfo(dt).max)
        return arr

    def image_bytes(self, i: int) -> Optional[bytes]:
        img = self.doc["images"][i]
        if "bufferView" in img:
            return self.view(img["bufferView"])
        uri = img.get("uri", "")
        return _data_uri(uri) or self.files.get(_join(self.files.get("__base__", b"").decode(), uri))


def _join(base: str, uri: str) -> str:
    from urllib.parse import unquote

    parts = [p for p in (base + "/" + unquote(uri)).replace("\\", "/").split("/") if p and p != "."]
    out: list[str] = []
    for p in parts:
        if p == "..":
            if out:
                out.pop()
        else:
            out.append(p)
    return "/".join(out)


def _quat(q: list[float]) -> np.ndarray:
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]], dtype=np.float64)


def node_matrix(n: dict) -> np.ndarray:
    if "matrix" in n:
        return np.array(n["matrix"], dtype=np.float64).reshape(4, 4).T
    m = np.eye(4)
    m[:3, :3] = _quat(n.get("rotation", [0, 0, 0, 1])) * np.array(n.get("scale", [1, 1, 1]))
    m[:3, 3] = n.get("translation", [0, 0, 0])
    return m


def triangles(g: Gltf) -> list[tuple[np.ndarray, tuple[float, float, float]]]:
    """[(triangulos Nx3x3 en mundo, color base)] de la escena por defecto."""
    doc = g.doc
    scenes = doc.get("scenes") or [{"nodes": [i for i in range(len(doc.get("nodes", [])))]}]
    roots = scenes[doc.get("scene", 0)].get("nodes", [])
    out = []
    colors = [_mat_color(g, i) for i in range(len(doc.get("materials", [])))]
    stack = [(r, np.eye(4)) for r in roots]
    seen = 0
    while stack:
        i, parent = stack.pop()
        seen += 1
        if seen > 20000:
            raise Bad("La escena tiene demasiados nodos.")
        node = doc["nodes"][i]
        world = parent @ node_matrix(node)
        if "mesh" in node:
            for prim in doc["meshes"][node["mesh"]].get("primitives", []):
                if prim.get("mode", 4) != 4 or "POSITION" not in prim.get("attributes", {}):
                    continue
                pos = g.accessor(prim["attributes"]["POSITION"])[:, :3].astype(np.float64)
                pos = (np.c_[pos, np.ones(len(pos))] @ world.T)[:, :3]
                idx = g.accessor(prim["indices"]).astype(np.int64).ravel() if "indices" in prim else np.arange(len(pos))
                idx = idx[: len(idx) // 3 * 3]
                if len(idx) and idx.max() >= len(pos):
                    raise Bad("Índices fuera de rango en el modelo.")
                col = colors[prim["material"]] if "material" in prim and prim["material"] < len(colors) else (0.75, 0.75, 0.75)
                out.append((pos[idx].reshape(-1, 3, 3), col))
        stack += [(c, world) for c in node.get("children", [])]
    return out


def _mat_color(g: Gltf, i: int) -> tuple[float, float, float]:
    m = g.doc["materials"][i]
    pbr = m.get("pbrMetallicRoughness", {})
    f = pbr.get("baseColorFactor", [1, 1, 1, 1])
    col = np.array(f[:3], dtype=np.float64)
    tex = pbr.get("baseColorTexture")
    if tex is not None:
        try:
            src = _tex_source(g.doc["textures"][tex["index"]])
            raw = g.image_bytes(src) if src is not None else None
            if raw:
                im = Image.open(io.BytesIO(raw)).convert("RGB").resize((8, 8))
                col = col * (np.asarray(im, dtype=np.float64).reshape(-1, 3).mean(0) / 255.0)
        except Exception:
            pass
    return tuple(float(c) for c in np.clip(col, 0, 1))


def _tex_source(t: dict) -> Optional[int]:
    ext = t.get("extensions") or {}
    for k in ("EXT_texture_webp", "KHR_texture_basisu", "MSFT_texture_dds"):
        if k in ext and "source" in ext[k]:
            return ext[k]["source"]
    return t.get("source")


# ------------------------------------------------------------------ escritura GLB
def write_glb(doc: dict, binary: bytes) -> bytes:
    doc = dict(doc)
    doc["buffers"] = [{"byteLength": len(binary)}] if binary else []
    js = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)
    binary += b"\x00" * ((4 - len(binary) % 4) % 4)
    total = 12 + 8 + len(js) + (8 + len(binary) if binary else 0)
    out = struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<II", len(js), 0x4E4F534A) + js
    if binary:
        out += struct.pack("<II", len(binary), 0x004E4942) + binary
    return out


def repack(g: Gltf, root_matrix: np.ndarray) -> tuple[bytes, int]:
    """Un solo buffer: todas las bufferViews copiadas, texturas a WebP <= 1024, la escena colgada de un nodo raiz con
    la transformacion de centrado y escala. Devuelve (glb, texturas)."""
    doc = json.loads(json.dumps(g.doc))
    blob = bytearray()
    new_views = []
    for i, bv in enumerate(doc.get("bufferViews", [])):
        data = g.view(i)
        while len(blob) % 4:
            blob.append(0)
        nbv = {k: v for k, v in bv.items() if k not in ("buffer", "byteOffset")}
        nbv.update(buffer=0, byteOffset=len(blob), byteLength=len(data))
        blob += data
        new_views.append(nbv)
    doc["bufferViews"] = new_views
    count = 0
    webp_used = False
    for i, img in enumerate(doc.get("images", [])):
        raw = g.image_bytes(i)
        if not raw:
            continue
        try:
            im = Image.open(io.BytesIO(raw))
            im.load()
        except Exception:
            raise Bad("Una textura del modelo no es una imagen válida.") from None
        if max(im.size) > TEX_MAX:
            im.thumbnail((TEX_MAX, TEX_MAX), Image.LANCZOS)
        im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=82, method=4)
        data = buf.getvalue()
        while len(blob) % 4:
            blob.append(0)
        new_views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)})
        blob += data
        doc["images"][i] = {"bufferView": len(new_views) - 1, "mimeType": "image/webp", **({"name": img["name"]} if "name" in img else {})}
        count += 1
        webp_used = True
    if webp_used:
        for t in doc.get("textures", []):
            src = _tex_source(t)
            t.pop("source", None)
            ext = {k: v for k, v in (t.get("extensions") or {}).items() if k not in ("EXT_texture_webp", "KHR_texture_basisu", "MSFT_texture_dds")}
            if src is not None:
                ext["EXT_texture_webp"] = {"source": src}
            t["extensions"] = ext
        for key in ("extensionsUsed", "extensionsRequired"):
            doc[key] = sorted(set(doc.get(key, [])) - {"KHR_texture_basisu", "MSFT_texture_dds"} | {"EXT_texture_webp"})
    for key in ("extensionsUsed", "extensionsRequired"):
        unsupported = {"KHR_draco_mesh_compression"} & set(doc.get(key, []))
        if unsupported:
            raise Bad("El modelo usa compresión Draco: expórtalo sin Draco.")
    scenes = doc.get("scenes") or [{"nodes": list(range(len(doc.get("nodes", []))))}]
    s = doc.get("scene", 0)
    doc.setdefault("nodes", []).append({"name": "clonexa_raiz", "matrix": [float(v) for v in root_matrix.T.ravel()],
                                        "children": list(scenes[s].get("nodes", []))})
    doc["scenes"] = [{"nodes": [len(doc["nodes"]) - 1]}]
    doc["scene"] = 0
    doc.pop("animations", None) if not doc.get("skins") else None
    doc["asset"] = {"version": "2.0", "generator": "Clonexa constructor"}
    return write_glb(doc, bytes(blob)), count


def mesh_glb(parts: list[dict]) -> bytes:
    """GLB desde triangulos sueltos: parts = [{"tris": Nx3x3, "color": (r,g,b), "uv": Nx3x2|None, "image": bytes|None}]."""
    doc: dict[str, Any] = {"asset": {"version": "2.0", "generator": "Clonexa constructor"}, "scene": 0, "scenes": [{"nodes": [0]}],
                           "nodes": [{"mesh": 0}], "meshes": [{"primitives": []}], "materials": [], "accessors": [], "bufferViews": []}
    blob = bytearray()

    def add(arr: np.ndarray, kind: str, target: Optional[int] = None) -> int:
        while len(blob) % 4:
            blob.append(0)
        data = arr.astype(np.float32).tobytes()
        doc["bufferViews"].append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data), **({"target": target} if target else {})})
        blob.extend(data)
        acc = {"bufferView": len(doc["bufferViews"]) - 1, "componentType": 5126, "count": len(arr), "type": kind}
        if kind == "VEC3":
            acc["min"], acc["max"] = arr.min(0).tolist(), arr.max(0).tolist()
        doc["accessors"].append(acc)
        return len(doc["accessors"]) - 1

    for part in parts:
        tris = np.asarray(part["tris"], dtype=np.float64)
        if not len(tris):
            continue
        n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        attrs = {"POSITION": add(tris.reshape(-1, 3), "VEC3", 34962), "NORMAL": add(np.repeat(n, 3, axis=0), "VEC3", 34962)}
        mat: dict[str, Any] = {"pbrMetallicRoughness": {"baseColorFactor": [*part.get("color", (0.8, 0.8, 0.8)), 1.0], "metallicFactor": 0.0, "roughnessFactor": 0.8},
                               "doubleSided": True}
        if part.get("uv") is not None and part.get("image"):
            attrs["TEXCOORD_0"] = add(np.asarray(part["uv"], dtype=np.float64).reshape(-1, 2) * [1, -1] + [0, 1], "VEC2", 34962)
            while len(blob) % 4:
                blob.append(0)
            doc["bufferViews"].append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(part["image"])})
            blob.extend(part["image"])
            doc.setdefault("images", []).append({"bufferView": len(doc["bufferViews"]) - 1, "mimeType": "image/png"})
            doc.setdefault("textures", []).append({"source": len(doc["images"]) - 1})
            mat["pbrMetallicRoughness"]["baseColorTexture"] = {"index": len(doc["textures"]) - 1}
        doc["materials"].append(mat)
        doc["meshes"][0]["primitives"].append({"attributes": attrs, "material": len(doc["materials"]) - 1})
    if not doc["meshes"][0]["primitives"]:
        raise Bad("El modelo no tiene geometría.")
    return write_glb(doc, bytes(blob))


def _png(raw: Optional[bytes]) -> Optional[bytes]:
    if not raw:
        return None
    try:
        im = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        return None
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


# ------------------------------------------------------------------ OBJ
def obj_to_glb(raw: bytes, files: dict[str, bytes], base: str = "") -> bytes:
    try:
        lines = raw.decode("utf-8", "replace").splitlines()
    except Exception:
        raise Bad("OBJ no legible.") from None
    v: list[list[float]] = []
    vt: list[list[float]] = []
    groups: dict[str, dict[str, list]] = {}
    cur = "__default__"
    mtllibs: list[str] = []
    for ln in lines:
        p = ln.strip().split()
        if not p or p[0].startswith("#"):
            continue
        try:
            if p[0] == "v":
                v.append([float(p[1]), float(p[2]), float(p[3])])
            elif p[0] == "vt":
                vt.append([float(p[1]), float(p[2]) if len(p) > 2 else 0.0])
            elif p[0] == "usemtl":
                cur = " ".join(p[1:])
            elif p[0] == "mtllib":
                mtllibs.append(" ".join(p[1:]))
            elif p[0] == "f":
                refs = []
                for tok in p[1:]:
                    parts = tok.split("/")
                    vi = int(parts[0])
                    ti = int(parts[1]) if len(parts) > 1 and parts[1] else None
                    refs.append((vi - 1 if vi > 0 else len(v) + vi, (ti - 1 if ti > 0 else len(vt) + ti) if ti else None))
                g = groups.setdefault(cur, {"t": [], "uv": []})
                for k in range(1, len(refs) - 1):
                    tri = (refs[0], refs[k], refs[k + 1])
                    g["t"].append([v[r[0]] for r in tri])
                    g["uv"].append([vt[r[1]] if r[1] is not None and r[1] < len(vt) else [0.0, 0.0] for r in tri])
        except (ValueError, IndexError):
            raise Bad("El OBJ tiene una línea dañada.") from None
        if len(v) > 3_000_000:
            raise Bad("El OBJ es demasiado grande.")
    mats = {}
    for lib in mtllibs:
        data = files.get(_join(base, lib))
        if data:
            mats.update(_mtl(data.decode("utf-8", "replace"), files, base))
    parts = []
    for name, g in groups.items():
        m = mats.get(name, {})
        parts.append({"tris": np.array(g["t"]), "color": m.get("kd", (0.8, 0.8, 0.8)), "uv": np.array(g["uv"]) if m.get("image") else None,
                      "image": m.get("image")})
    return mesh_glb(parts)


def _mtl(text_: str, files: dict[str, bytes], base: str) -> dict:
    out: dict[str, dict] = {}
    cur = None
    for ln in text_.splitlines():
        p = ln.strip().split()
        if not p:
            continue
        if p[0] == "newmtl":
            cur = out.setdefault(" ".join(p[1:]), {})
        elif cur is not None and p[0] == "Kd" and len(p) >= 4:
            try:
                cur["kd"] = tuple(max(0.0, min(1.0, float(x))) for x in p[1:4])
            except ValueError:
                pass
        elif cur is not None and p[0] == "map_Kd":
            cur["image"] = _png(files.get(_join(base, p[-1])))
    return out


# ------------------------------------------------------------------ FBX binario (geometria, materiales simples y huesos)
def fbx_to_glb(raw: bytes) -> tuple[bytes, bool]:
    if raw[:21] != b"Kaydara FBX Binary  \x00":
        if raw[:200].lstrip().startswith(b";") or b"FBXHeaderExtension" in raw[:2000]:
            raise Bad("FBX de texto (ASCII) no soportado: expórtalo como FBX binario o GLB.")
        raise Bad("No es un FBX válido.")
    version = struct.unpack_from("<I", raw, 23)[0]
    wide = version >= 7500
    nodes, _ = _fbx_nodes(raw, 27, len(raw), wide, 0)
    top = {n[0]: n for n in nodes}
    objects = top.get("Objects")
    if not objects:
        raise Bad("El FBX no tiene objetos.")
    geoms: dict[int, dict] = {}
    models: dict[int, dict] = {}
    mats: dict[int, tuple] = {}
    rigged = False
    for name, props, children in objects[2]:
        oid = props[0] if props else None
        kind = props[2] if len(props) > 2 else b""
        ch = {c[0]: c for c in children}
        if name == "Geometry" and kind == b"Mesh" and "Vertices" in ch and "PolygonVertexIndex" in ch:
            geoms[oid] = {"v": np.asarray(ch["Vertices"][1][0], dtype=np.float64).reshape(-1, 3),
                          "i": np.asarray(ch["PolygonVertexIndex"][1][0], dtype=np.int64)}
        elif name == "Model":
            models[oid] = _fbx_props(ch.get("Properties70"))
            if kind == b"LimbNode":
                rigged = True
        elif name == "Material":
            p = _fbx_props(ch.get("Properties70"))
            col = p.get(b"DiffuseColor") or p.get(b"Diffuse")
            mats[oid] = tuple(float(x) for x in col[:3]) if col else (0.8, 0.8, 0.8)
        elif name == "Deformer" and kind in (b"Skin", b"Cluster"):
            rigged = True
        elif name == "NodeAttribute" and kind == b"LimbNode":
            rigged = True
    parent: dict[int, int] = {}
    geom_model: dict[int, int] = {}
    model_mat: dict[int, int] = {}
    for name, props, _c in (top.get("Connections") or (None, None, []))[2]:
        if name != "C" or len(props) < 3 or props[0] != b"OO":
            continue
        child, par = props[1], props[2]
        if child in geoms and par in models:
            geom_model[child] = par
        elif child in models and par in models:
            parent[child] = par
        elif child in mats and par in models:
            model_mat.setdefault(par, child)
    parts = []
    for gid, gdat in geoms.items():
        verts, idx = gdat["v"], gdat["i"]
        mid = geom_model.get(gid)
        m = np.eye(4)
        k = mid
        depth = 0
        while k is not None and depth < 64:
            m = _fbx_local(models.get(k, {})) @ m
            k = parent.get(k)
            depth += 1
        pts = (np.c_[verts, np.ones(len(verts))] @ m.T)[:, :3]
        tris = []
        poly: list[int] = []
        for raw_i in idx.tolist():
            if raw_i < 0:
                poly.append(-raw_i - 1)
                for t in range(1, len(poly) - 1):
                    tris.append((poly[0], poly[t], poly[t + 1]))
                poly = []
            else:
                poly.append(raw_i)
        if not tris:
            continue
        tri = np.asarray(tris, dtype=np.int64)
        if tri.max() >= len(pts):
            raise Bad("Índices fuera de rango en el FBX.")
        parts.append({"tris": pts[tri], "color": mats.get(model_mat.get(mid), (0.8, 0.8, 0.8))})
    if not parts:
        raise Bad("El FBX no tiene mallas.")
    return mesh_glb(parts), rigged


def _fbx_local(p: dict) -> np.ndarray:
    t = p.get(b"Lcl Translation", (0, 0, 0))
    r = [math.radians(float(x)) for x in p.get(b"Lcl Rotation", (0, 0, 0))]
    s = p.get(b"Lcl Scaling", (1, 1, 1))
    cx, sx, cy, sy, cz, sz = math.cos(r[0]), math.sin(r[0]), math.cos(r[1]), math.sin(r[1]), math.cos(r[2]), math.sin(r[2])
    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    m = np.eye(4)
    m[:3, :3] = (rz @ ry @ rx) * np.array([float(x) for x in s[:3]])
    m[:3, 3] = [float(x) for x in t[:3]]
    return m


def _fbx_props(node: Optional[tuple]) -> dict:
    out = {}
    for name, props, _c in (node[2] if node else []):
        if name == "P" and props and isinstance(props[0], bytes):
            out[props[0]] = props[4:]
    return out


def _fbx_nodes(raw: bytes, off: int, end: int, wide: bool, depth: int) -> tuple[list, int]:
    if depth > 32:
        raise Bad("FBX demasiado anidado.")
    out = []
    head = 25 if wide else 13
    while off + head <= end:
        if wide:
            end_off, nprops, _plen, nlen = struct.unpack_from("<QQQB", raw, off)
        else:
            end_off, nprops, _plen, nlen = struct.unpack_from("<IIIB", raw, off)
        if end_off == 0:
            off += head
            break
        if end_off > len(raw) or end_off <= off:
            raise Bad("FBX dañado.")
        name = raw[off + head: off + head + nlen].decode("latin-1")
        p = off + head + nlen
        props = []
        for _ in range(min(nprops, 100000)):
            val, p = _fbx_prop(raw, p)
            props.append(val)
        children, _ = _fbx_nodes(raw, p, end_off, wide, depth + 1) if p < end_off else ([], p)
        out.append((name, props, children))
        off = end_off
    return out, off


ARR = {"f": ("f", 4), "d": ("d", 8), "l": ("q", 8), "i": ("i", 4), "b": ("b", 1)}


def _fbx_prop(raw: bytes, p: int) -> tuple[Any, int]:
    t = chr(raw[p])
    p += 1
    if t == "Y":
        return struct.unpack_from("<h", raw, p)[0], p + 2
    if t == "C":
        return bool(raw[p]), p + 1
    if t == "I":
        return struct.unpack_from("<i", raw, p)[0], p + 4
    if t == "F":
        return struct.unpack_from("<f", raw, p)[0], p + 4
    if t == "D":
        return struct.unpack_from("<d", raw, p)[0], p + 8
    if t == "L":
        return struct.unpack_from("<q", raw, p)[0], p + 8
    if t in ARR:
        n, enc, clen = struct.unpack_from("<III", raw, p)
        p += 12
        data = raw[p: p + clen]
        if enc == 1:
            if n * ARR[t][1] > 400_000_000:
                raise Bad("FBX demasiado grande.")
            data = zlib.decompress(data)
        if len(data) < n * ARR[t][1]:
            raise Bad("FBX dañado.")
        return list(struct.unpack_from(f"<{n}{ARR[t][0]}", data)), p + clen
    if t in ("S", "R"):
        n = struct.unpack_from("<I", raw, p)[0]
        return raw[p + 4: p + 4 + n], p + 4 + n
    raise Bad("FBX con un dato desconocido.")


# ------------------------------------------------------------------ preparar (centrar, apoyar, escalar, miniatura)
def prepare(g: Gltf, height: Optional[float] = None, width: Optional[float] = None, rigged: bool = False) -> Prepared:
    used = set(g.doc.get("extensionsUsed") or []) | set(g.doc.get("extensionsRequired") or [])
    if "EXT_meshopt_compression" in used:
        raise Bad("El modelo ya viene comprimido con meshopt: súbelo sin comprimir (GLB normal, GLTF, FBX u OBJ).")
    if "KHR_draco_mesh_compression" in used:
        raise Bad("El modelo usa compresión Draco: expórtalo sin Draco.")
    parts = triangles(g)
    if not parts:
        raise Bad("El modelo no tiene geometría visible.")
    tris = int(sum(len(t) for t, _ in parts))
    if tris > MAX_TRIS:
        raise Bad(f"El modelo tiene {tris:,} triángulos (máximo {MAX_TRIS:,}). Simplifícalo antes de subirlo.".replace(",", "."))
    allp = np.concatenate([t.reshape(-1, 3) for t, _ in parts])
    lo, hi = allp.min(0), allp.max(0)
    ext = hi - lo
    if not np.all(np.isfinite(ext)) or ext.max() <= 0:
        raise Bad("El modelo no tiene tamaño.")
    if height:
        s = float(height) / max(ext[1], 1e-6)
    elif width:
        s = float(width) / max(ext[0], ext[2], 1e-6)
    else:
        raise Bad("Escribe el alto o el ancho real del objeto.")
    root = np.eye(4)
    root[:3, :3] *= s
    root[:3, 3] = [-(lo[0] + hi[0]) / 2 * s, -lo[1] * s, -(lo[2] + hi[2]) / 2 * s]
    rigged = rigged or bool(g.doc.get("skins"))
    glb, ntex = repack(g, root)
    warn = []
    if tris > WARN_TRIS:
        warn.append(f"Modelo pesado: {tris:,} triángulos (recomendado menos de {WARN_TRIS:,}).".replace(",", "."))
    world = [(np.c_[t.reshape(-1, 3), np.ones(t.size // 3)] @ root.T)[:, :3].reshape(-1, 3, 3) for t, _ in parts]
    size = {"w": round(float(ext[0] * s), 3), "h": round(float(ext[1] * s), 3), "d": round(float(ext[2] * s), 3)}
    return Prepared(glb=glb, thumb=thumbnail(list(zip(world, [c for _, c in parts]))), tris=tris, size=size, rigged=rigged,
                    warnings=warn, textures=ntex)


def thumbnail(parts: list[tuple[np.ndarray, tuple]], px: int = THUMB, budget: int = 40_000) -> bytes:
    """Miniatura por software: vista isometrica 3/4, luz direccional, pintor por profundidad (sin GPU)."""
    tris = np.concatenate([t for t, _ in parts])
    cols = np.concatenate([np.tile(np.array(c, dtype=np.float64), (len(t), 1)) for t, c in parts])
    if len(tris) > budget:
        pick = np.linspace(0, len(tris) - 1, budget).astype(np.int64)
        tris, cols = tris[pick], cols[pick]
    az, el = math.radians(-35), math.radians(28)
    ca, sa, ce, se = math.cos(az), math.sin(az), math.cos(el), math.sin(el)
    rot = np.array([[ca, 0, -sa], [sa * se, ce, ca * se], [sa * ce, -se, ca * ce]])
    v = tris.reshape(-1, 3) @ rot.T
    v = v.reshape(-1, 3, 3)
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    light = np.array([0.4, 0.8, 0.45])
    light /= np.linalg.norm(light)
    shade = 0.35 + 0.65 * np.abs(n @ light)
    rgb = np.clip(cols * shade[:, None], 0, 1)
    xy = v[:, :, :2]
    lo, hi = xy.reshape(-1, 2).min(0), xy.reshape(-1, 2).max(0)
    big = px * 2
    scale = (big * 0.84) / max(float((hi - lo).max()), 1e-6)
    center = (lo + hi) / 2
    pts = (xy - center) * scale * np.array([1, -1]) + big / 2
    order = np.argsort(v[:, :, 2].mean(1))[::-1]
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    for i in order.tolist():
        c = tuple(int(x * 255) for x in rgb[i]) + (255,)
        dr.polygon([tuple(p) for p in pts[i].tolist()], fill=c)
    im = im.resize((px, px), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=80, method=4)
    return buf.getvalue()
