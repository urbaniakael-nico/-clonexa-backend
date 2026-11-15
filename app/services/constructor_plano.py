"""MODO CONSTRUCTOR (fase 1): el PLANO del local de cada empresa, a escala, con versiones.

Esquema del plano: docs/constructor/PLANO.md (JSON en metros; origen arriba a la izquierda de la sala, x hacia la
derecha, z hacia abajo; rotacion en grados). Este modulo tiene las reglas puras (validacion estricta, avisos,
plantillas, exportar/importar) y el acceso a la base (borrador con autoguardado, versiones publicadas, restaurar).

- Tabla constructor_planos: una fila 'borrador' por empresa (se autoguarda) y una fila 'publicado' por cada
  "Publicar en vivo" (version 1, 2, 3...). El historial son las publicadas; "restaurar" copia una al borrador.
- La version PUBLICADA mas reciente dibuja el piso de la empresa (Oficina 3D y Negocio en vivo 3D) solo si el
  interruptor de la empresa oficina_pisos.usa_plano esta encendido (apagado por defecto). El borrador nunca se ve.
- Todo cerrado por company_id.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import uuid
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

FORMATO = "clonexa.plano"
ESQUEMA = 1
HISTORY_MAX = 40
MAX_OBJECTS = 400
MAX_WALLS = 160
MAX_OPENINGS = 80
MAX_FLOORS = 60
MAX_ZONES = 40
MAX_POINTS = 48
MAX_BYTES = 400_000
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
ASSET_RE = re.compile(r"^[a-z0-9_-]{2,60}$")

WALL_MATERIALS = ("pintura", "ladrillo", "ladrillo_blanco", "concreto", "listones", "panel_negro", "azulejo", "vidrio", "papel_tapiz", "piedra")
WALL_LABEL = {"pintura": "Pintura lisa", "ladrillo": "Ladrillo", "ladrillo_blanco": "Ladrillo blanco", "concreto": "Concreto",
              "listones": "Madera en listones", "panel_negro": "Panel negro brillante", "azulejo": "Azulejo de cocina", "vidrio": "Vidrio",
              "papel_tapiz": "Papel tapiz", "piedra": "Piedra"}
FLOOR_MATERIALS = ("madera_clara", "madera_oscura", "baldosa_blanca", "ajedrez", "concreto_pulido", "epoxico", "alfombra", "negro_brillante", "deck", "cesped")
FLOOR_LABEL = {"madera_clara": "Madera clara", "madera_oscura": "Madera oscura", "baldosa_blanca": "Baldosa blanca", "ajedrez": "Baldosa ajedrez",
               "concreto_pulido": "Concreto pulido", "epoxico": "Epóxico", "alfombra": "Alfombra", "negro_brillante": "Negro brillante",
               "deck": "Deck de madera", "cesped": "Césped"}
DOORS = ("puerta", "puerta_doble", "puerta_vidrio", "corrediza", "cortina_metalica", "vaiven")
WINDOWS = ("ventana", "ventanal", "vitrina")
OPENINGS = DOORS + WINDOWS
OPENING_LABEL = {"puerta": "Puerta sencilla", "puerta_doble": "Puerta doble", "puerta_vidrio": "Puerta de vidrio", "corrediza": "Puerta corrediza",
                 "cortina_metalica": "Cortina metálica", "vaiven": "Vaivén de cocina", "ventana": "Ventana", "ventanal": "Ventanal", "vitrina": "Vitrina"}
OPENING_SIZE = {"puerta": (0.9, 2.1, 0), "puerta_doble": (1.6, 2.2, 0), "puerta_vidrio": (1.0, 2.2, 0), "corrediza": (1.8, 2.2, 0),
                "cortina_metalica": (3.0, 2.6, 0), "vaiven": (0.9, 2.0, 0), "ventana": (1.2, 1.2, 0.9), "ventanal": (3.0, 1.9, 0.4), "vitrina": (2.4, 2.2, 0.15)}
SCENE_STYLES = ("humano", "caricatura")
LAYERS = ("piso", "muebles", "decoracion", "techo", "pared")
ZONE_KINDS = ("salon", "barra", "cocina", "caja", "bodega", "oficina", "terraza", "banos", "pista", "produccion", "recepcion", "otra")
ZONE_LABEL = {"salon": "Salón", "barra": "Barra", "cocina": "Cocina", "caja": "Caja", "bodega": "Bodega", "oficina": "Oficina",
              "terraza": "Terraza", "banos": "Baños", "pista": "Pista", "produccion": "Producción", "recepcion": "Recepción", "otra": "Otra"}
CONNECT_KINDS = ("mesa", "puesto", "escritorio", "caja", "pantalla")
SCREENS = {"canciones": "Canciones pedidas", "comandas": "Comandas en cocina", "domicilios": "Domicilios",
           "produccion": "Tablero de producción", "turno": "Personal en turno", "logo": "Logo de la empresa", "texto": "Texto fijo"}
CASH_DESKS = {"caja-1": "Caja principal", "caja-2": "Caja 2"}
STATIONS_MAX = 40
TEMPLATES = ("bar", "restaurante", "taller", "callcenter", "bodega", "oficina")
TEMPLATE_LABEL = {"bar": "Bar", "restaurante": "Restaurante", "taller": "Taller", "callcenter": "Call center", "bodega": "Bodega", "oficina": "Oficina"}


class Rejected(ValueError):
    pass


# ------------------------------------------------------------------ validacion estricta (pura)
def _num(v: Any, lo: float, hi: float, what: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise Rejected(f"{what}: debe ser un número.")
    f = float(v)
    if not math.isfinite(f) or f < lo or f > hi:
        raise Rejected(f"{what}: fuera de rango ({lo} a {hi}).")
    return round(f, 3)


def _id(v: Any, what: str, seen: set[str]) -> str:
    if not isinstance(v, str) or not ID_RE.match(v):
        raise Rejected(f"{what}: identificador no válido.")
    if v in seen:
        raise Rejected(f"{what}: identificador repetido ({v}).")
    seen.add(v)
    return v


def _color(v: Any, what: str, default: Optional[str] = None) -> Optional[str]:
    if v is None or v == "":
        return default
    if not isinstance(v, str) or not COLOR_RE.match(v):
        raise Rejected(f"{what}: color no válido (usa #rrggbb).")
    return v.lower()


def _text(v: Any, n: int, what: str) -> str:
    if v is None:
        return ""
    if not isinstance(v, str) or len(v) > n or any(ord(ch) < 32 for ch in v):
        raise Rejected(f"{what}: texto no válido (máximo {n} caracteres).")
    return v.strip()


def _list(v: Any, n: int, what: str) -> list:
    if v is None:
        return []
    if not isinstance(v, list):
        raise Rejected(f"{what}: debe ser una lista.")
    if len(v) > n:
        raise Rejected(f"{what}: máximo {n}.")
    return v


def _only(d: Any, keys: set[str], what: str) -> dict:
    if not isinstance(d, dict):
        raise Rejected(f"{what}: formato no válido.")
    extra = set(d) - keys
    if extra:
        raise Rejected(f"{what}: campos desconocidos ({', '.join(sorted(extra))[:80]}).")
    return d


def _points(v: Any, W: float, D: float, what: str) -> list[list[float]]:
    pts = _list(v, MAX_POINTS, what)
    if len(pts) < 3:
        raise Rejected(f"{what}: el polígono necesita al menos 3 puntos.")
    out = []
    for p in pts:
        if not isinstance(p, list) or len(p) != 2:
            raise Rejected(f"{what}: punto no válido.")
        out.append([_num(p[0], -0.5, W + 0.5, what), _num(p[1], -0.5, D + 0.5, what)])
    return out


def clean_plan(raw: Any, assets: Optional[set[str]] = None) -> dict:
    """Valida un plano completo (lo que guarda el editor o un .clonexa.json importado). Rechaza todo lo que no
    conoce: campos extra, ids repetidos, aberturas en paredes que no existen, assets fuera del catalogo, una misma
    entidad real conectada a dos objetos."""
    if not isinstance(raw, dict):
        raise Rejected("El plano debe ser un objeto JSON.")
    if len(json.dumps(raw, default=str)) > MAX_BYTES:
        raise Rejected("El plano es demasiado grande.")
    _only(raw, {"formato", "version_esquema", "sala", "paredes", "aberturas", "pisos", "zonas", "objetos", "meta"}, "Plano")
    if raw.get("formato", FORMATO) != FORMATO:
        raise Rejected("No es un plano de Clonexa.")
    if raw.get("version_esquema", ESQUEMA) != ESQUEMA:
        raise Rejected("Versión de plano no soportada.")
    sala = _only(raw.get("sala"), {"ancho", "fondo", "alto"}, "Sala")
    W, D = _num(sala.get("ancho"), 3, 60, "Ancho de la sala"), _num(sala.get("fondo"), 3, 60, "Fondo de la sala")
    H = _num(sala.get("alto", 3.2), 2.2, 8, "Alto de la sala")
    out: dict[str, Any] = {"formato": FORMATO, "version_esquema": ESQUEMA, "sala": {"ancho": W, "fondo": D, "alto": H},
                           "paredes": [], "aberturas": [], "pisos": [], "zonas": [], "objetos": []}
    seen: set[str] = set()
    walls: dict[str, float] = {}
    for w in _list(raw.get("paredes"), MAX_WALLS, "Paredes"):
        _only(w, {"id", "x1", "z1", "x2", "z2", "grosor", "alto", "color", "material"}, "Pared")
        wid = _id(w.get("id"), "Pared", seen)
        x1, z1 = _num(w.get("x1"), -0.5, W + 0.5, "Pared"), _num(w.get("z1"), -0.5, D + 0.5, "Pared")
        x2, z2 = _num(w.get("x2"), -0.5, W + 0.5, "Pared"), _num(w.get("z2"), -0.5, D + 0.5, "Pared")
        length = math.hypot(x2 - x1, z2 - z1)
        if length < 0.1:
            raise Rejected("Pared demasiado corta.")
        mat = w.get("material", "pintura")
        if mat not in WALL_MATERIALS:
            raise Rejected("Material de pared no válido.")
        walls[wid] = length
        out["paredes"].append({"id": wid, "x1": x1, "z1": z1, "x2": x2, "z2": z2, "grosor": _num(w.get("grosor", 0.15), 0.05, 0.6, "Grosor"),
                               "alto": _num(w.get("alto", H), 0.3, 8, "Alto de pared"), "color": _color(w.get("color"), "Pared", "#d8cfc4"), "material": mat})
    for a in _list(raw.get("aberturas"), MAX_OPENINGS, "Puertas y ventanas"):
        _only(a, {"id", "pared", "tipo", "pos", "ancho", "alto", "base"}, "Abertura")
        aid = _id(a.get("id"), "Abertura", seen)
        if a.get("pared") not in walls:
            raise Rejected("Una puerta o ventana no está en una pared del plano.")
        if a.get("tipo") not in OPENINGS:
            raise Rejected("Tipo de abertura no válido.")
        dw, dh, db = OPENING_SIZE[a["tipo"]]
        width = _num(a.get("ancho", dw), 0.4, 6, "Ancho de abertura")
        pos = _num(a.get("pos"), 0, walls[a["pared"]], "Posición de la abertura")
        if pos - width / 2 < -0.01 or pos + width / 2 > walls[a["pared"]] + 0.01:
            raise Rejected("La puerta o ventana se sale de su pared.")
        base = 0.0 if a["tipo"] in DOORS else _num(a.get("base", db), 0, 3, "Altura de la ventana")
        out["aberturas"].append({"id": aid, "pared": a["pared"], "tipo": a["tipo"], "pos": pos, "ancho": width,
                                 "alto": _num(a.get("alto", dh), 0.3, 4, "Alto de abertura"), "base": base})
    zones: set[str] = set()
    for z in _list(raw.get("zonas"), MAX_ZONES, "Zonas"):
        _only(z, {"id", "nombre", "tipo", "puntos"}, "Zona")
        zid = _id(z.get("id"), "Zona", seen)
        kind = z.get("tipo", "otra")
        if kind not in ZONE_KINDS:
            raise Rejected("Tipo de zona no válido.")
        zones.add(zid)
        out["zonas"].append({"id": zid, "nombre": _text(z.get("nombre"), 30, "Nombre de zona") or ZONE_LABEL[kind], "tipo": kind,
                             "puntos": _points(z.get("puntos"), W, D, "Zona")})
    for f in _list(raw.get("pisos"), MAX_FLOORS, "Pisos"):
        _only(f, {"id", "zona", "puntos", "material", "color"}, "Piso")
        fid = _id(f.get("id"), "Piso", seen)
        if f.get("material", "madera_clara") not in FLOOR_MATERIALS:
            raise Rejected("Material de piso no válido.")
        if f.get("zona") not in (None, "") and f.get("zona") not in zones:
            raise Rejected("Un piso apunta a una zona que no existe.")
        out["pisos"].append({"id": fid, "zona": f.get("zona") or None, "puntos": _points(f.get("puntos"), W, D, "Piso"),
                             "material": f.get("material", "madera_clara"), "color": _color(f.get("color"), "Piso", "#8a5a36")})
    used: dict[str, str] = {}
    for o in _list(raw.get("objetos"), MAX_OBJECTS, "Objetos"):
        _only(o, {"id", "asset", "x", "z", "rot", "escala", "color", "variante", "capa", "conexion", "texto", "y"}, "Objeto")
        oid = _id(o.get("id"), "Objeto", seen)
        asset = o.get("asset")
        if not isinstance(asset, str) or not ASSET_RE.match(asset) or (assets is not None and asset not in assets):
            raise Rejected(f"El objeto {oid} usa un modelo que no está en el catálogo.")
        layer = o.get("capa", "muebles")
        if layer not in LAYERS:
            raise Rejected("Capa no válida.")
        item = {"id": oid, "asset": asset, "x": _num(o.get("x"), -1, W + 1, "Posición x"), "z": _num(o.get("z"), -1, D + 1, "Posición z"),
                "rot": round(_num(o.get("rot", 0), -720, 720, "Rotación") % 360, 1), "escala": _num(o.get("escala", 1), 0.2, 5, "Escala"),
                "color": _color(o.get("color"), "Color del objeto"), "variante": _text(o.get("variante"), 30, "Variante") or None,
                "capa": layer, "conexion": None, "texto": _text(o.get("texto"), 40, "Texto") or None}
        if o.get("y") is not None:
            item["y"] = _num(o.get("y"), 0, 8, "Altura")
        con = o.get("conexion")
        if con is not None:
            _only(con, {"tipo", "id"}, "Conexión")
            if con.get("tipo") not in CONNECT_KINDS or not isinstance(con.get("id"), str) or not (0 < len(con["id"]) <= 80):
                raise Rejected("Conexión no válida.")
            key = f"{con['tipo']}:{con['id']}"
            if key in used:
                raise Rejected(f"{con['id']} ya está conectada a otro objeto ({used[key]}).")
            used[key] = oid
            item["conexion"] = {"tipo": con["tipo"], "id": con["id"]}
        out["objetos"].append(item)
    return out


def plan_hash(plan: dict) -> str:
    return hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


# ------------------------------------------------------------------ exportar / importar
def export_doc(plan: dict, company_name: str, version: Optional[int]) -> dict:
    return {"formato": FORMATO, "version_esquema": ESQUEMA, "exportado_de": str(company_name or "")[:80], "version": version,
            "plano": plan}


def import_doc(raw: bytes, assets: set[str]) -> dict:
    """Archivo .clonexa.json -> plano limpio. Las conexiones NO viajan (las entidades reales son de la empresa de
    origen): se quitan y el plano entra como borrador sin conectar."""
    if not raw or len(raw) > MAX_BYTES * 2:
        raise Rejected("Archivo vacío o demasiado grande.")
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise Rejected("El archivo no es un JSON válido.") from None
    if not isinstance(doc, dict) or doc.get("formato") != FORMATO or not isinstance(doc.get("plano"), dict):
        raise Rejected("El archivo no es un plano de Clonexa (.clonexa.json).")
    _only(doc, {"formato", "version_esquema", "exportado_de", "version", "plano"}, "Archivo")
    if doc.get("version_esquema") != ESQUEMA:
        raise Rejected("Versión de plano no soportada.")
    plan = clean_plan(doc["plano"], assets)
    for o in plan["objetos"]:
        o["conexion"] = None
    return plan


# ------------------------------------------------------------------ avisos (puros; el editor usa la misma regla en JS)
def footprint(obj: dict, sizes: dict[str, dict]) -> tuple[float, float]:
    s = sizes.get(obj["asset"]) or {"w": 0.6, "d": 0.6}
    k = float(obj.get("escala") or 1)
    return float(s.get("w") or 0.6) * k, float(s.get("d") or 0.6) * k


def _corners(o: dict, sizes: dict) -> list[tuple[float, float]]:
    w, d = footprint(o, sizes)
    a = math.radians(o.get("rot") or 0)
    c, s = math.cos(a), math.sin(a)
    return [(o["x"] + dx * c - dz * s, o["z"] + dx * s + dz * c) for dx, dz in ((-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2))]


def _overlap(a: list, b: list) -> bool:
    """Separacion de ejes (SAT) entre dos rectangulos girados."""
    for poly in (a, b):
        for i in range(4):
            x1, z1 = poly[i]
            x2, z2 = poly[(i + 1) % 4]
            nx, nz = z2 - z1, x1 - x2
            pa = [nx * x + nz * z for x, z in a]
            pb = [nx * x + nz * z for x, z in b]
            if max(pa) <= min(pb) + 1e-6 or max(pb) <= min(pa) + 1e-6:
                return False
    return True


def door_box(plan: dict, opening: dict, depth: float = 0.9) -> Optional[list]:
    wall = next((w for w in plan["paredes"] if w["id"] == opening["pared"]), None)
    if not wall or opening["tipo"] not in DOORS:
        return None
    L = math.hypot(wall["x2"] - wall["x1"], wall["z2"] - wall["z1"]) or 1
    ux, uz = (wall["x2"] - wall["x1"]) / L, (wall["z2"] - wall["z1"]) / L
    cx, cz = wall["x1"] + ux * opening["pos"], wall["z1"] + uz * opening["pos"]
    hw = opening["ancho"] / 2
    nx, nz = -uz, ux
    return [(cx - ux * hw - nx * depth, cz - uz * hw - nz * depth), (cx + ux * hw - nx * depth, cz + uz * hw - nz * depth),
            (cx + ux * hw + nx * depth, cz + uz * hw + nz * depth), (cx - ux * hw + nx * depth, cz - uz * hw + nz * depth)]


def warnings(plan: dict, sizes: dict[str, dict], entities: Optional[dict] = None) -> dict:
    """Objetos que se cruzan, objetos que tapan una puerta, objetos conectables sin conectar y mesas reales sin
    objeto. Capas 'techo', 'pared' y 'piso' no chocan con muebles."""
    solid = [o for o in plan["objetos"] if o.get("capa", "muebles") == "muebles"]
    boxes = {o["id"]: _corners(o, sizes) for o in solid}
    cross = []
    for i, a in enumerate(solid):
        for b in solid[i + 1:]:
            if _overlap(boxes[a["id"]], boxes[b["id"]]):
                cross.append([a["id"], b["id"]])
    doors = []
    for op in plan["aberturas"]:
        box = door_box(plan, op)
        if box:
            doors += [[o["id"], op["id"]] for o in solid if _overlap(boxes[o["id"]], box)]
    unconnected = [o["id"] for o in plan["objetos"] if (sizes.get(o["asset"]) or {}).get("conectable") and not o.get("conexion")]
    missing = []
    if entities:
        linked = {(o["conexion"]["tipo"], o["conexion"]["id"]) for o in plan["objetos"] if o.get("conexion")}
        missing = [e["label"] for e in entities.get("mesa", []) if ("mesa", e["id"]) not in linked]
    return {"cruces": cross[:50], "puertas": doors[:50], "sin_conectar": unconnected, "mesas_sin_objeto": missing}


# ------------------------------------------------------------------ plantillas (armadas con el catalogo, basadas en los pisos actuales)
def _rect(W: float, D: float, H: float, color: str = "#d8cfc4", material: str = "pintura") -> list[dict]:
    """Cuatro paredes: w1 arriba (fondo), w2 derecha, w3 abajo (frente/entrada), w4 izquierda."""
    pts = [(0, 0), (W, 0), (W, D), (0, D)]
    return [{"id": f"w{i + 1}", "x1": pts[i][0], "z1": pts[i][1], "x2": pts[(i + 1) % 4][0], "z2": pts[(i + 1) % 4][1],
             "grosor": 0.15, "alto": H, "color": color, "material": material} for i in range(4)]


def _zone(zid: str, kind: str, x1: float, z1: float, x2: float, z2: float, name: Optional[str] = None) -> dict:
    return {"id": zid, "nombre": name or ZONE_LABEL[kind], "tipo": kind, "puntos": [[x1, z1], [x2, z1], [x2, z2], [x1, z2]]}


class _Builder:
    def __init__(self, W: float, D: float, H: float = 3.2, wall: str = "#d8cfc4", wall_mat: str = "pintura"):
        self.plan = {"formato": FORMATO, "version_esquema": ESQUEMA, "sala": {"ancho": W, "fondo": D, "alto": H},
                     "paredes": _rect(W, D, H, wall, wall_mat), "aberturas": [], "pisos": [], "zonas": [], "objetos": []}
        self.n = 0

    def obj(self, asset: str, x: float, z: float, rot: float = 0, **kw: Any) -> dict:
        self.n += 1
        o = {"id": f"o{self.n}", "asset": asset, "x": round(x, 2), "z": round(z, 2), "rot": rot, "escala": 1, "color": None,
             "variante": None, "capa": kw.pop("capa", "muebles"), "conexion": None, "texto": None}
        o.update(kw)
        self.plan["objetos"].append(o)
        return o

    def wall(self, x1: float, z1: float, x2: float, z2: float, material: str = "pintura", color: str = "#d8cfc4", alto: Optional[float] = None, grosor: float = 0.12) -> str:
        wid = f"w{len(self.plan['paredes']) + 1}"
        self.plan["paredes"].append({"id": wid, "x1": x1, "z1": z1, "x2": x2, "z2": z2, "grosor": grosor,
                                     "alto": alto or self.plan["sala"]["alto"], "color": color, "material": material})
        return wid

    def paint(self, wall: str, material: str, color: str) -> None:
        for w in self.plan["paredes"]:
            if w["id"] == wall:
                w["material"], w["color"] = material, color

    def zone(self, zid: str, kind: str, x1: float, z1: float, x2: float, z2: float, material: str, color: str, name: Optional[str] = None) -> None:
        self.plan["zonas"].append(_zone(zid, kind, x1, z1, x2, z2, name))
        self.plan["pisos"].append({"id": "p" + zid, "zona": zid, "puntos": [[x1, z1], [x2, z1], [x2, z2], [x1, z2]], "material": material, "color": color})

    def opening(self, wall: str, kind: str, pos: float, width: Optional[float] = None) -> None:
        dw, dh, db = OPENING_SIZE[kind]
        self.plan["aberturas"].append({"id": f"a{len(self.plan['aberturas']) + 1}", "pared": wall, "tipo": kind, "pos": pos,
                                       "ancho": width or dw, "alto": dh, "base": db})


def _grid(n: int, x0: float, z0: float, cols: int, dx: float, dz: float) -> list[tuple[float, float]]:
    return [(x0 + (i % cols) * dx, z0 + (i // cols) * dz) for i in range(n)]


def template(kind: str, tables: Optional[list[str]] = None, arch: Optional[dict] = None) -> dict:
    """Plantilla de piso armada con objetos del catalogo (cada una distinta: materiales, puertas y muebles propios).
    tables: mesas reales de la empresa (se conectan solas en orden). arch: posiciones guardadas del modo arquitecto
    ({clave: [x, z, giro]} en coordenadas centradas del piso aprobado), que se respetan: asi "Editar distribucion"
    migra lo ya guardado."""
    if kind not in TEMPLATES:
        raise Rejected("Plantilla no válida.")
    tables = list(tables or [])
    arch = arch or {}
    if kind == "bar":
        b = _Builder(22, 14, 3.4, "#9a3b2e", "ladrillo")
        b.paint("w4", "panel_negro", "#141018")
        b.zone("salon", "salon", 0, 0, 22, 14, "madera_oscura", "#4a2c1d")
        b.zone("barra", "barra", 0, 0, 5, 14, "negro_brillante", "#151018")
        b.zone("pista", "pista", 15, 1.2, 20.5, 6, "epoxico", "#2a1238")
        b.opening("w3", "puerta_doble", 11)
        b.opening("w3", "ventanal", 17, 4)
        b.obj("barra_l", 2.6, 4, 90)
        b.obj("barra_recta", 1.8, 9.5, 90, variante="larga")
        b.obj("contrabarra", 0.3, 6.5, 90, capa="pared")
        b.obj("nevera_bebidas", 0.6, 12.6, 90)
        for i in range(8):
            b.obj("taburete", 3.0 if i < 3 else 3.0, 2.2 + i * 1.15, color="#c47a3a")
        b.obj("cabina_dj", 18, 0.8)
        b.obj("parlante", 15.6, 0.6)
        b.obj("parlante", 20.6, 0.6)
        b.obj("pista_led", 17.75, 3.6, capa="piso")
        b.obj("logo_pared", 8.5, 0.12, 0, capa="pared")
        b.obj("neon", 5.6, 0.12, 0, capa="pared", texto="Night Bar")
        b.obj("tv_pared", 12, 0.15, 0, capa="pared", conexion={"tipo": "pantalla", "id": "canciones"})
        b.obj("caja_registradora", 3.5, 12.6, 0, conexion={"tipo": "caja", "id": "caja-1"})
        b.obj("datafono", 3.9, 12.4, capa="decoracion")
        b.obj("sofa_lounge", 18.5, 12.9, 180)
        b.obj("mesa_centro", 18.5, 11.6)
        b.obj("mesa_alta", 15.5, 8.2)
        b.obj("mesa_alta", 18.2, 8.2)
        for p in ((21.2, 7.6), (21.2, 10.6), (13.6, 13.2)):
            b.obj("planta_grande", *p)
        for x in (8, 11, 14):
            b.obj("lampara_colgante", x, 6, capa="techo")
        b.obj("tira_led", 2.6, 0.1, 0, capa="pared", color="#ec4899")
        spots = _grid(max(len(tables), 9), 7.2, 3.4, 3, 2.7, 3.2)
        _tables(b, tables, spots, "mesa_redonda_4", arch, (11, 7))
        return b.plan
    if kind == "restaurante":
        b = _Builder(20, 15, 3.2, "#efe6d8")
        b.zone("salon", "salon", 0, 5, 14, 15, "ajedrez", "#f4efe6")
        b.zone("cocina", "cocina", 0, 0, 12, 5, "baldosa_blanca", "#e5e5e5")
        b.zone("caja", "caja", 12, 0, 20, 5, "madera_clara", "#b98a5a")
        b.zone("terraza", "terraza", 14, 5, 20, 15, "deck", "#8a6440")
        b.paint("w1", "azulejo", "#ffffff")
        k = b.wall(0, 5, 9, 5, "azulejo", "#ffffff", 3.2)
        b.wall(14, 5, 14, 9, "vidrio", "#bfe3ff", 3.2, 0.06)
        b.opening(k, "vaiven", 4.5)
        b.opening("w3", "puerta_vidrio", 7)
        b.opening("w2", "corrediza", 10)
        b.opening("w4", "ventana", 10)
        b.obj("estufa", 1.4, 0.6)
        b.obj("parrilla", 3.4, 0.6)
        b.obj("campana", 2.4, 0.6, capa="techo")
        b.obj("freidora", 5, 0.6)
        b.obj("horno", 6.2, 0.6)
        b.obj("meson_cocina", 8.4, 0.6)
        b.obj("lavaplatos", 10.5, 0.6)
        b.obj("nevera_industrial", 11.2, 2.2, 270)
        b.obj("meson_corto", 5, 3.2)
        b.obj("pase_platos", 10.5, 4.6)
        b.obj("pantalla_cocina", 6, 4.9, 180, capa="pared", conexion={"tipo": "pantalla", "id": "comandas"})
        b.obj("caja_registradora", 16, 2.6, 0, conexion={"tipo": "caja", "id": "caja-1"})
        b.obj("vitrina_postres", 13.5, 2.6, 90)
        b.obj("tv_pared", 16, 0.15, 0, capa="pared", conexion={"tipo": "pantalla", "id": "domicilios"})
        b.obj("moto_domicilios", 19, 3.2)
        b.obj("logo_pared", 7, 14.85, 180, capa="pared")
        b.obj("reloj", 3, 14.9, 180, capa="pared")
        b.obj("cuadro", 0.1, 8, 90, capa="pared")
        b.obj("mesa_butacas", 1.2, 12.5, 90)
        b.obj("mesa_butacas", 1.2, 9.6, 90)
        for i, (x, z) in enumerate(((16, 7.5), (18.4, 7.5), (16, 10.6), (18.4, 10.6))):
            b.obj("mesa_sombrilla", x, z, color="#dc2626")
        b.obj("jardinera", 17, 14.4)
        spots = _grid(max(len(tables), 8), 4.6, 6.8, 4, 2.6, 2.8)
        _tables(b, tables, spots, "mesa_cuadrada_4", arch, (10, 7.5))
        return b.plan
    if kind == "taller":
        b = _Builder(24, 14, 3.8, "#cfd3d8", "concreto")
        b.zone("produccion", "produccion", 0, 0, 24, 10, "epoxico", "#5f7f8f")
        b.zone("bodega", "bodega", 0, 10, 10, 14, "concreto_pulido", "#8d8f94")
        b.zone("oficina", "oficina", 16, 10, 24, 14, "madera_clara", "#b98a5a")
        o = b.wall(16, 10, 24, 10, "vidrio", "#bfe3ff", 3.8, 0.06)
        b.opening(o, "puerta_vidrio", 2)
        b.opening("w3", "cortina_metalica", 13)
        b.opening("w1", "ventanal", 6, 4)
        b.opening("w1", "ventanal", 18, 4)
        for i, (x, z) in enumerate(_grid(12, 2.4, 2.4, 6, 3.2, 3.0)):
            px, pz = _from_arch(arch.get(f"maquina:{i}"), (x, z), (12, 7))
            b.obj("maquina_plana" if i % 4 else "fileteadora", px, pz, 0, conexion={"tipo": "puesto", "id": f"puesto-{i + 1}"})
        b.obj("mesa_corte", 12, 8.6, 0, conexion={"tipo": "puesto", "id": "puesto-13"})
        b.obj("plancha_industrial", 20.5, 8.6, 0, conexion={"tipo": "puesto", "id": "puesto-14"})
        b.obj("tv_grande", 12, 0.15, 0, capa="pared", conexion={"tipo": "pantalla", "id": "produccion"})
        b.obj("maniqui", 22.8, 1.2)
        b.obj("maniqui", 22.8, 2.4)
        for i in range(3):
            b.obj("estante_lotes", 1.2 + i * 2.3, 13.5)
            b.obj("perchero", 1.2 + i * 2.3, 11.2, color=("#7c3aed", "#db2777", "#0f766e")[i])
        b.obj("rollos_tela", 8.6, 11.2)
        b.obj("carro_transporte", 8.6, 13.2)
        b.obj("escritorio_pc", 19, 12)
        b.obj("silla_ergonomica", 19, 12.8, 180)
        b.obj("archivador", 23.4, 13.4)
        b.obj("logo_pared", 20, 13.85, 180, capa="pared")
        b.obj("reloj", 3, 0.1, 0, capa="pared")
        for x in (4, 8, 12, 16, 20):
            b.obj("riel_luces", x, 5, capa="techo")
        return b.plan
    if kind == "callcenter":
        b = _Builder(18, 12, 3.0, "#e9eef5")
        b.paint("w1", "papel_tapiz", "#1e3a5f")
        b.zone("oficina", "oficina", 0, 0, 18, 9, "alfombra", "#3b4a63")
        b.zone("recepcion", "recepcion", 0, 9, 18, 12, "baldosa_blanca", "#e5e7eb")
        j = b.wall(12, 0, 12, 4, "vidrio", "#bfe3ff", 3.0, 0.06)
        b.opening("w3", "puerta_vidrio", 9)
        b.opening("w2", "ventanal", 6, 4)
        for row in range(2):
            for i in range(5):
                x, z = 1.4 + i * 2.0, 2.2 + row * 3.4
                b.obj("escritorio_fila", x, z)
                b.obj("silla_ergonomica", x, z + 0.8, 180)
            b.obj("division", 5.4, 2.2 + row * 3.4 + 0.45)
        b.obj("sala_juntas", 15, 2)
        b.obj("tablero_grande", 15, 0.1, 0, capa="pared")
        b.obj("tv_grande", 6, 0.15, 0, capa="pared", conexion={"tipo": "pantalla", "id": "turno"})
        b.obj("recepcion_mostrador", 9, 10.4)
        b.obj("logo_pared", 9, 11.85, 180, capa="pared")
        b.obj("sofa", 2.5, 11.1)
        b.obj("dispensador_agua", 17.4, 8.4)
        b.obj("casilleros", 16.8, 6, 270)
        for p in ((0.6, 11.4), (17.4, 11.4), (11.4, 6.6)):
            b.obj("planta_grande", *p)
        return b.plan
    if kind == "bodega":
        b = _Builder(26, 16, 6.0, "#bfc4c9", "concreto")
        b.zone("bodega", "bodega", 0, 0, 26, 16, "concreto_pulido", "#7d8085")
        b.zone("oficina", "oficina", 20, 0, 26, 4, "baldosa_blanca", "#e5e7eb", "Despacho")
        b.wall(20, 4, 26, 4, "vidrio", "#bfe3ff", 2.6, 0.06)
        b.opening("w3", "cortina_metalica", 8, 4)
        b.opening("w3", "cortina_metalica", 15, 4)
        b.opening("w2", "puerta", 6)
        for row in range(3):
            for i in range(4):
                b.obj("rack_alto" if row == 0 else "rack", 2.4 + i * 4.4, 1.2 + row * 4.2, color=("#1d4ed8", "#f59e0b", "#475569")[row])
        for i in range(5):
            b.obj("estiba", 3 + i * 3.4, 13.6)
        b.obj("montacargas", 20, 10, 90)
        b.obj("conos", 12, 15.2)
        b.obj("herramientas", 25.9, 8, 270, capa="pared")
        b.obj("casilleros", 25.6, 12, 270)
        b.obj("escritorio_pc", 23, 2)
        b.obj("silla_ergonomica", 23, 2.8, 180)
        b.obj("tv_pared", 23, 0.15, 0, capa="pared", conexion={"tipo": "pantalla", "id": "turno"})
        b.obj("canecas", 19, 15.4)
        return b.plan
    b = _Builder(16, 12, 3.0, "#f1f3f5")
    b.paint("w1", "listones", "#b98a5a")
    b.zone("oficina", "oficina", 0, 0, 16, 8.5, "madera_clara", "#c49a6c")
    b.zone("recepcion", "recepcion", 0, 8.5, 16, 12, "baldosa_blanca", "#e8e6e1")
    b.zone("banos", "banos", 13, 8.5, 16, 12, "baldosa_blanca", "#d9e2ec")
    w = b.wall(13, 8.5, 13, 12, "azulejo", "#ffffff", 3.0)
    b.opening(w, "puerta", 1.6)
    b.opening("w3", "puerta_vidrio", 7)
    b.opening("w4", "ventana", 3)
    b.opening("w4", "ventana", 6)
    for i, (x, z) in enumerate(_grid(6, 2.4, 2.2, 3, 3.8, 3.2)):
        b.obj("escritorio_pc", x, z)
        b.obj("silla_ergonomica", x, z + 0.75, 180)
    b.obj("sala_juntas", 13.5, 2.2, 90)
    b.obj("tablero_grande", 15.9, 2.2, 270, capa="pared")
    b.obj("recepcion_mostrador", 6.5, 10)
    b.obj("sofa", 2, 11.3)
    b.obj("mesa_centro", 2, 10.3)
    b.obj("logo_pared", 6.5, 11.85, 180, capa="pared")
    b.obj("sanitario", 15.4, 11.4, 270)
    b.obj("lavamanos", 15.6, 9.2, 270)
    b.obj("espejo", 15.95, 9.2, 270, capa="pared")
    b.obj("palma", 11.8, 11.2)
    b.obj("cuadro", 0.1, 4, 90, capa="pared")
    b.obj("lampara_pie", 0.6, 11.4)
    return b.plan


def _from_arch(saved: Any, default: tuple[float, float], center: tuple[float, float]) -> tuple[float, float]:
    """Posicion guardada del modo arquitecto (coordenadas centradas del piso aprobado) -> metros del plano."""
    if isinstance(saved, (list, tuple)) and len(saved) >= 2:
        try:
            x, z = float(saved[0]) + center[0], float(saved[1]) + center[1]
            if math.isfinite(x) and math.isfinite(z):
                return round(x, 2), round(z, 2)
        except (TypeError, ValueError):
            pass
    return default


def _tables(b: _Builder, tables: list[str], spots: list, asset: str, arch: dict, center: tuple[float, float]) -> None:
    for i, spot in enumerate(spots):
        label = tables[i] if i < len(tables) else None
        x, z = _from_arch(arch.get(f"mesa:{label}") if label else None, spot, center)
        b.obj(asset, x, z, 0, conexion={"tipo": "mesa", "id": label} if label else None)


TEMPLATE_FOR_FLOOR = {"bar": "bar", "restaurante": "restaurante", "taller": "taller", "campo": "callcenter", "general": "oficina"}


def first_draft(floor_template: str, tables: list[str], distribucion: Any) -> dict:
    """Primer borrador de una empresa sin plano: la plantilla de su piso + lo que ya tenia guardado en "Editar
    distribucion" (modo arquitecto: distribucion.piso.items de los pisos aprobados o distribucion.items del bar)."""
    dist = distribucion if isinstance(distribucion, dict) else {}
    arch: dict = {}
    piso = dist.get("piso")
    if isinstance(piso, dict) and isinstance(piso.get("items"), dict):
        arch = dict(piso["items"])
    elif isinstance(dist.get("items"), dict):
        arch = dict(dist["items"])
    return template(TEMPLATE_FOR_FLOOR.get(floor_template, "oficina"), tables, arch)


# ------------------------------------------------------------------ base de datos (siempre por company_id)
def _row(r: Any) -> dict:
    d = dict(r)
    if isinstance(d.get("plano"), str):
        d["plano"] = json.loads(d["plano"])
    return d


async def draft(db: AsyncSession, cid: str) -> Optional[dict]:
    r = (await db.execute(text("""SELECT id::text AS id, version, estado, plano, creado_por, updated_at FROM constructor_planos
        WHERE company_id = CAST(:c AS uuid) AND estado = 'borrador' LIMIT 1"""), {"c": cid})).mappings().first()
    return _row(r) if r else None


async def published(db: AsyncSession, cid: str) -> Optional[dict]:
    r = (await db.execute(text("""SELECT id::text AS id, version, estado, plano, creado_por, created_at FROM constructor_planos
        WHERE company_id = CAST(:c AS uuid) AND estado = 'publicado' ORDER BY version DESC LIMIT 1"""), {"c": cid})).mappings().first()
    return _row(r) if r else None


async def last_version(db: AsyncSession, cid: str) -> int:
    v = (await db.execute(text("SELECT COALESCE(MAX(version), 0) FROM constructor_planos WHERE company_id = CAST(:c AS uuid) AND estado = 'publicado'"),
                          {"c": cid})).scalar()
    return int(v or 0)


async def history(db: AsyncSession, cid: str) -> list[dict]:
    rows = (await db.execute(text("""SELECT version, creado_por, created_at, nota, jsonb_array_length(COALESCE(plano->'objetos', '[]'::jsonb)) AS objetos
        FROM constructor_planos WHERE company_id = CAST(:c AS uuid) AND estado = 'publicado' ORDER BY version DESC LIMIT :n"""),
                            {"c": cid, "n": HISTORY_MAX})).mappings().all()
    return [{**dict(r), "created_at": r["created_at"].isoformat() if r["created_at"] else None} for r in rows]


async def save_draft(db: AsyncSession, cid: str, plan: dict, actor: str) -> dict:
    """Autoguardado: una sola fila 'borrador' por empresa (indice unico parcial)."""
    version = await last_version(db, cid) + 1
    await db.execute(text("""
        INSERT INTO constructor_planos (id, company_id, version, estado, plano, creado_por, created_at, updated_at)
        VALUES (CAST(:id AS uuid), CAST(:c AS uuid), :v, 'borrador', CAST(:p AS jsonb), :a, now(), now())
        ON CONFLICT (company_id) WHERE estado = 'borrador'
        DO UPDATE SET plano = EXCLUDED.plano, version = EXCLUDED.version, creado_por = EXCLUDED.creado_por, updated_at = now()
    """), {"id": str(uuid.uuid4()), "c": cid, "v": version, "p": json.dumps(plan), "a": actor[:120]})
    await db.commit()
    return {"version": version, "hash": plan_hash(plan)}


async def publish(db: AsyncSession, cid: str, plan: dict, actor: str, note: str = "") -> int:
    version = await last_version(db, cid) + 1
    await db.execute(text("""
        INSERT INTO constructor_planos (id, company_id, version, estado, plano, creado_por, nota, created_at, updated_at)
        VALUES (CAST(:id AS uuid), CAST(:c AS uuid), :v, 'publicado', CAST(:p AS jsonb), :a, :n, now(), now())
    """), {"id": str(uuid.uuid4()), "c": cid, "v": version, "p": json.dumps(plan), "a": actor[:120], "n": note[:200]})
    # el borrador sigue (ahora apunta a la version siguiente) y el historial guarda las ultimas HISTORY_MAX
    await db.execute(text("UPDATE constructor_planos SET version = :v, plano = CAST(:p AS jsonb), updated_at = now() WHERE company_id = CAST(:c AS uuid) AND estado = 'borrador'"),
                     {"c": cid, "v": version + 1, "p": json.dumps(plan)})
    await db.execute(text("""DELETE FROM constructor_planos WHERE company_id = CAST(:c AS uuid) AND estado = 'publicado' AND version <= :cut"""),
                     {"c": cid, "cut": version - HISTORY_MAX})
    await db.commit()
    return version


async def version_plan(db: AsyncSession, cid: str, version: int) -> Optional[dict]:
    r = (await db.execute(text("""SELECT plano FROM constructor_planos WHERE company_id = CAST(:c AS uuid) AND estado = 'publicado' AND version = :v"""),
                          {"c": cid, "v": int(version)})).scalar()
    if r is None:
        return None
    return json.loads(r) if isinstance(r, str) else r


async def uses_plan(db: AsyncSession, cid: str) -> bool:
    try:
        v = (await db.execute(text("SELECT usa_plano FROM oficina_pisos WHERE company_id = CAST(:c AS uuid)"), {"c": cid})).scalar()
    except Exception:
        await db.rollback()
        return False
    return v is True


async def set_uses_plan(db: AsyncSession, cid: str, on: bool, actor: str) -> None:
    await db.execute(text("""
        INSERT INTO oficina_pisos (company_id, usa_plano, updated_by) VALUES (CAST(:c AS uuid), :on, :a)
        ON CONFLICT (company_id) DO UPDATE SET usa_plano = EXCLUDED.usa_plano, updated_by = EXCLUDED.updated_by, updated_at = now()
    """), {"c": cid, "on": bool(on), "a": actor[:120]})
    await db.commit()


async def live_plan(db: AsyncSession, cid: str) -> Optional[dict]:
    """El plano que se VE (Oficina 3D y Negocio en vivo 3D): la ultima version publicada, solo con el interruptor
    de la empresa encendido. None = la empresa sigue con su piso de siempre."""
    if not await uses_plan(db, cid):
        return None
    try:
        row = await published(db, cid)
    except Exception:
        await db.rollback()
        return None
    return {"version": row["version"], "plano": row["plano"]} if row else None


async def live_versions(db: AsyncSession, ids: list[str]) -> dict[str, int]:
    """Version publicada en vivo por empresa (una consulta, para la lista de pisos)."""
    if not ids:
        return {}
    try:
        rows = (await db.execute(text("""
            SELECT p.company_id::text AS c, MAX(p.version) AS v FROM constructor_planos p
            JOIN oficina_pisos o ON o.company_id = p.company_id AND o.usa_plano IS TRUE
            WHERE p.estado = 'publicado' AND p.company_id::text = ANY(:ids) GROUP BY p.company_id
        """), {"ids": ids})).mappings().all()
    except Exception:
        await db.rollback()
        return {}
    return {r["c"]: int(r["v"]) for r in rows}


# ------------------------------------------------------------------ entidades reales de ESA empresa (para "Conectar a")
async def entities(db: AsyncSession, cid: str) -> dict[str, list[dict]]:
    from app.services import carta_links

    out: dict[str, list[dict]] = {k: [] for k in CONNECT_KINDS}
    try:
        out["mesa"] = [{"id": t, "label": f"{t} · QR"} for t in await carta_links.mesa_labels(db, cid)]
    except Exception:
        await db.rollback()
    out["puesto"] = [{"id": f"puesto-{i}", "label": f"Puesto / máquina {i}"} for i in range(1, STATIONS_MAX + 1)]
    try:
        rows = (await db.execute(text("""SELECT id::text AS id, full_name, role FROM employees WHERE company_id = CAST(:c AS uuid)
            AND LOWER(COALESCE(status, 'active')) = 'active' ORDER BY full_name LIMIT 300"""), {"c": cid})).mappings().all()
        out["escritorio"] = [{"id": r["id"], "label": f"{(r['full_name'] or '').split(' ')[0]} · {r['role'] or ''}".strip(" ·")} for r in rows]
    except Exception:
        await db.rollback()
    out["caja"] = [{"id": k, "label": v} for k, v in CASH_DESKS.items()]
    out["pantalla"] = [{"id": k, "label": v} for k, v in SCREENS.items()]
    return out


def for_engine(plan: dict) -> dict:
    """Lo que recibe el motor 3D: las conexiones a escritorios llevan la huella de la persona (la misma de la copia
    viva) y nunca el id real del empleado."""
    out = copy.deepcopy(plan)
    for o in out.get("objetos", []):
        con = o.get("conexion")
        if con and con.get("tipo") == "escritorio":
            con["id"] = hashlib.sha256(f"{con['id']}".encode()).hexdigest()[:12]
    return out


__all__ = ["clean_plan", "template", "first_draft", "warnings", "export_doc", "import_doc", "entities", "live_plan"]
