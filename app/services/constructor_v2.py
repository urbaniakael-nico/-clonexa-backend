"""BIBLIOTECA 3D (Modo constructor + Personajes, prototipo aprobado): reglas puras y acceso a la base, POR EMPRESA.

El plano es el JSON del prototipo (app/web/oficina/b3d/*.js, docs/constructor/PLANO.md):
  {name, room{w,d,h}, floor{mat,color}, walls{n,s,e,w: {mat,color}}, openings[{id,wall,pos,type,width?,color?}],
   objects[{id,item,x,z,rot,color?,color2?,color3?,text?,screen?,products?,conn?}], people[{id,pid,x,z,rot,clip}]}
en metros con el origen en el CENTRO del local (x a la derecha, z hacia el frente) y el giro en grados.

- Varios diseños por empresa ("Tus diseños"): constructor_planos.diseno_id. Cada diseño tiene UNA fila 'borrador'
  (autoguardado) y una fila 'publicado' por cada "Publicar en vivo" (sus "Versiones").
- En vivo se ve la última versión publicada del diseño en vivo (oficina_pisos.plano_diseno), solo con el interruptor
  de la empresa oficina_pisos.usa_plano (apagado por defecto; "Publicar en vivo" lo enciende para ESA empresa).
- Los planos de la fase 1 (formato con "sala", paredes por segmentos) se convierten con from_v1 (migración 025v y,
  por si quedara alguno, al leer).
- Equipo = módulo Personal real (employees) + su personaje en oficina_personajes (clave persona:<huella>, columna look).
- Uniformes por empresa: constructor_uniformes.
- Las conexiones son claves de entidades reales DE ESA EMPRESA ("mesa:Mesa 3", "emp:<huella>", "caja:caja-1"...).
Todo cerrado por company_id.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import secrets
import uuid
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

FORMATO = "clonexa.plano"
ESQUEMA = 2
HISTORY_MAX = 20            # el prototipo guarda las últimas 20 versiones por diseño
DESIGNS_MAX = 30
MAX_OBJECTS = 400
MAX_PEOPLE = 200
MAX_OPENINGS = 60
MAX_BYTES = 400_000
THUMB_MAX = 160_000
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
ITEM_RE = re.compile(r"^[a-z0-9_-]{2,60}$")
PID_RE = re.compile(r"^[0-9a-f]{12}$")

WALLS = ("pintura", "ladrillo", "ladrillo_blanco", "concreto", "madera", "panel", "azulejo", "vidrio", "tapiz", "piedra")
FLOORS = ("madera_clara", "madera_oscura", "baldosa", "ajedrez", "concreto", "epoxico", "alfombra", "negro", "deck", "cesped")
OPENINGS = ("puerta", "puerta_doble", "puerta_vidrio", "corrediza", "cortina", "vaiven", "ventana", "ventanal", "vitrina")
SCREENS = ("Logo de la empresa", "Canciones pedidas", "Comandas en cocina", "Domicilios", "Tablero de producción", "Partido / TV")
PRODUCTS = ("Gaseosas", "Cervezas", "Agua", "Variado")
CLIPS = ("idle", "walk", "sit", "work", "dance")
STYLES = {"human": "humano", "toon": "caricatura"}          # prototipo -> oficina_pisos.estilo_escena
CATS = ("barra", "neveras", "mesas", "pantallas", "sonido", "luces", "cocina", "caja", "deco", "taller", "oficina", "bodega", "banos")
CAT_FROM_V1 = {"decoracion": "deco", "exterior": "deco", "tienda": "bodega"}
CAT_TO_V1 = {"deco": "decoracion"}
CONN_PREFIX = {"mesa": "mesa", "puesto": "puesto", "escritorio": "emp", "caja": "caja", "pantalla": "pantalla", "inventario": "inv", "sonido": "sonido"}

# Catálogo del prototipo (app/web/oficina/b3d/catalog.js): id -> (carpeta, ancho, fondo, conectable, de pared, propiedades).
# tests/b3d_catalogo.test.cjs comprueba que esta tabla y catalog.js digan lo mismo.
ITEMS: dict[str, tuple] = {k: tuple(v) for k, *v in [
    ["barra_recta", "barra", 2.4, 0.75, "", 0, ""], ["barra_l", "barra", 2.6, 2.6, "", 0, ""], ["isla", "barra", 2.2, 1.2, "", 0, ""],
    ["contrabarra", "barra", 2.4, 0.4, "", 0, ""], ["taburete", "barra", 0.45, 0.45, "", 0, ""], ["taburete_alto", "barra", 0.5, 0.5, "", 0, ""],
    ["nevera_bebidas", "neveras", 0.9, 0.7, "inventario", 0, "products"], ["nevera_doble", "neveras", 1.5, 0.7, "inventario", 0, "products"],
    ["nevera_industrial", "neveras", 1.3, 0.75, "", 0, ""], ["congelador", "neveras", 1.4, 0.7, "", 0, ""],
    ["mesa_redonda", "mesas", 2, 2, "mesa", 0, ""], ["mesa_cuadrada", "mesas", 1.9, 1.9, "mesa", 0, ""], ["mesa_2", "mesas", 0.8, 1.6, "mesa", 0, ""],
    ["mesa_larga", "mesas", 2.4, 1.9, "mesa", 0, ""], ["mesa_alta", "mesas", 0.8, 0.8, "mesa", 0, ""], ["silla", "mesas", 0.5, 0.5, "", 0, ""],
    ["butaca", "mesas", 1.6, 2.2, "mesa", 0, ""], ["sofa", "mesas", 2.2, 0.95, "", 0, ""], ["mesa_centro", "mesas", 1, 0.6, "", 0, ""],
    ["puff", "mesas", 0.5, 0.5, "", 0, ""], ["tv_pared", "pantallas", 1.8, 0.2, "pantalla", 1, "screen"],
    ["tv_pedestal", "pantallas", 1, 0.6, "pantalla", 0, "screen"], ["tablero", "pantallas", 3.2, 0.2, "pantalla", 1, "screen"],
    ["cabina_dj", "sonido", 1.8, 0.75, "sonido", 0, ""], ["parlante", "sonido", 0.6, 0.55, "", 0, ""], ["pista_led", "sonido", 3, 2.4, "", 0, ""],
    ["lampara", "luces", 0.6, 0.6, "", 0, ""], ["foco", "luces", 0.5, 0.5, "", 0, ""], ["tira_led", "luces", 2.4, 0.1, "", 0, ""],
    ["neon", "luces", 2, 0.2, "", 1, "text"], ["estufa", "cocina", 1, 0.7, "puesto", 0, ""], ["parrilla", "cocina", 1.2, 0.8, "puesto", 0, ""],
    ["freidora", "cocina", 0.6, 0.7, "", 0, ""], ["horno", "cocina", 0.9, 0.75, "", 0, ""], ["campana", "cocina", 1.4, 0.8, "", 1, ""],
    ["meson", "cocina", 1.6, 0.7, "", 0, ""], ["lavaplatos", "cocina", 1.2, 0.7, "", 0, ""], ["pase", "cocina", 1.8, 0.5, "", 0, ""],
    ["caja", "caja", 1.2, 0.6, "caja", 0, ""], ["mostrador", "caja", 2, 0.7, "", 0, ""], ["planta", "deco", 0.6, 0.6, "", 0, ""],
    ["planta_alta", "deco", 0.6, 0.6, "", 0, ""], ["cuadro", "deco", 1, 0.1, "", 1, ""], ["tapete", "deco", 2.4, 1.6, "", 0, ""],
    ["reloj", "deco", 0.5, 0.1, "", 1, ""], ["espejo", "deco", 0.8, 0.1, "", 1, ""], ["jardinera", "deco", 1.6, 0.5, "", 0, ""],
    ["maquina_plana", "taller", 1.2, 1.3, "puesto", 0, ""], ["fileteadora", "taller", 1.1, 1.3, "puesto", 0, ""],
    ["mesa_corte", "taller", 2.6, 1.3, "puesto", 0, ""], ["rollos", "taller", 1.2, 0.6, "", 0, ""], ["perchero", "taller", 1.4, 0.5, "", 0, ""],
    ["maniqui", "taller", 0.5, 0.5, "", 0, ""], ["estante_lotes", "taller", 1.8, 0.5, "", 0, ""],
    ["escritorio", "oficina", 1.4, 1.4, "escritorio", 0, ""], ["silla_ergo", "oficina", 0.6, 0.6, "", 0, ""], ["division", "oficina", 1.5, 0.1, "", 0, ""],
    ["mesa_juntas", "oficina", 3.2, 2, "", 0, ""], ["archivador", "oficina", 0.5, 0.6, "", 0, ""], ["rack", "bodega", 2, 0.8, "", 0, ""],
    ["estiba", "bodega", 1.2, 1, "", 0, ""], ["casilleros", "bodega", 1.5, 0.5, "", 0, ""], ["conos", "bodega", 0.8, 0.5, "", 0, ""],
    ["sanitario", "banos", 0.5, 0.7, "", 0, ""], ["lavamanos", "banos", 0.6, 0.45, "", 0, ""],
]}

# Personajes: claves que guarda el editor (people.js) y sus reglas.
HUMAN_BASES = ("Ch22_nonPBR", "Ch21_nonPBR", "Ch07_nonPBR", "Remy", "Ch42_nonPBR", "Ch01_nonPBR", "Ch06_nonPBR", "Ch17_nonPBR")
FEMALE_BASES = ("Ch22_nonPBR", "Ch21_nonPBR", "Ch07_nonPBR")
MALE_BASES = ("Remy", "Ch42_nonPBR", "Ch01_nonPBR", "Ch06_nonPBR", "Ch17_nonPBR")
TOON_OPTS = {"body": ("delgado", "medio", "robusto"), "eyes": ("redondos", "felices", "grandes"), "brows": ("normal", "gruesas", "finas"),
             "mouth": ("sonrisa", "abierta", "seria"),
             "hair": ("rapado", "corto", "crespo", "afro", "largo", "ondulado", "mono", "cola", "trenzas", "calvo"),
             "beard": ("ninguna", "corta", "larga", "bigote", "candado"), "top": ("camiseta", "camisa", "polo", "chaqueta", "blazer", "buzo", "chef"),
             "bottom": ("jean", "pantalon", "short", "falda"), "complete": ("ninguno", "vestido", "overol"), "shoes": ("tenis", "zapatos", "botas", "tacones")}
TOON_COLORS = ("skin", "hairColor", "beardColor", "topColor", "innerColor", "bottomColor", "completeColor", "shoesColor", "accColor")
TOON_NUMS = {"height": (0.85, 1.15), "hairLen": (0, 1), "hairVol": (0, 1)}
TOON_BOOLS = ("blush", "freckles")
TOON_ACC = ("gorra", "casco", "gorro_chef", "diadema", "gafas", "delantal", "chaleco", "reloj", "aretes")
HUMAN_COLORS = ("skinTint", "hairColor", "topColor", "bottomColor", "shoesColor", "beardColor", "accColor")
HUMAN_OPTS = {"topStyle": ("original", "liso"), "beard": ("ninguna", "corta", "larga")}
AREAS = ("Barra", "Salón", "Cocina", "Caja", "Bodega", "Oficina", "Producción", "Campo", "Domicilios")
AREA_BY_UNIFORM = {"barman": "Barra", "dj": "Barra", "mesero": "Salón", "cocina": "Cocina", "caja": "Caja", "costura": "Producción",
                   "tecnico": "Campo", "domiciliario": "Domicilios"}
TEMPLATE_FOR_FLOOR = {"bar": "bar", "restaurante": "restaurante", "taller": "taller", "campo": "bodega", "general": "oficina"}
SCREEN_FEEDS = {"canciones": "Canciones pedidas", "comandas": "Comandas en cocina", "domicilios": "Domicilios",
                "produccion": "Tablero de producción", "turno": "Personal en turno", "logo": "Logo de la empresa"}
CASH_DESKS = {"caja-1": "Caja principal", "caja-2": "Caja 2"}
STATIONS_MAX = 40


class Rejected(ValueError):
    pass


# ------------------------------------------------------------------ validación estricta del plano (pura)
def _num(v: Any, lo: float, hi: float, what: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise Rejected(f"{what}: debe ser un número.")
    f = float(v)
    if not math.isfinite(f) or f < lo or f > hi:
        raise Rejected(f"{what}: fuera de rango ({lo} a {hi}).")
    return round(f, 3)


def _id(v: Any, what: str, seen: set) -> str:
    if not isinstance(v, str) or not ID_RE.match(v):
        raise Rejected(f"{what}: identificador no válido.")
    if v in seen:
        raise Rejected(f"{what}: identificador repetido ({v}).")
    seen.add(v)
    return v


def _color(v: Any, what: str) -> Optional[str]:
    if v is None or v == "":
        return None
    if not isinstance(v, str) or not COLOR_RE.match(v):
        raise Rejected(f"{what}: color no válido (usa #rrggbb).")
    return v.lower()


def _text(v: Any, n: int, what: str) -> str:
    if v is None:
        return ""
    if not isinstance(v, str) or len(v) > n or any(ord(ch) < 32 for ch in v):
        raise Rejected(f"{what}: texto no válido (máximo {n} caracteres).")
    return v.strip()


def _only(d: Any, keys: set, what: str) -> dict:
    if not isinstance(d, dict):
        raise Rejected(f"{what}: formato no válido.")
    extra = set(d) - keys
    if extra:
        raise Rejected(f"{what}: campos desconocidos ({', '.join(sorted(extra))[:80]}).")
    return d


def _list(v: Any, n: int, what: str) -> list:
    if v is None:
        return []
    if not isinstance(v, list):
        raise Rejected(f"{what}: debe ser una lista.")
    if len(v) > n:
        raise Rejected(f"{what}: máximo {n}.")
    return v


def conn_kind(item: str, glb: Optional[dict] = None) -> str:
    if item in ITEMS:
        return ITEMS[item][3]
    return (glb or {}).get(item, {}).get("conn") or ""


def clean_plan(raw: Any, glb: Optional[dict] = None) -> dict:
    """Valida un plano del prototipo (lo que autoguarda el constructor o un .clonexa.json importado). Rechaza lo que
    no conoce: campos extra, ids repetidos, objetos fuera del catálogo, una misma entidad real en dos objetos, una
    conexión de otro tipo (una mesa a una caja). glb: modelos aprobados de la Biblioteca {id: {conn}}."""
    glb = glb or {}
    if not isinstance(raw, dict):
        raise Rejected("El plano debe ser un objeto JSON.")
    if len(json.dumps(raw, default=str)) > MAX_BYTES:
        raise Rejected("El plano es demasiado grande.")
    _only(raw, {"name", "room", "floor", "walls", "openings", "objects", "people", "formato", "version_esquema"}, "Plano")
    room = _only(raw.get("room"), {"w", "d", "h"}, "Local")
    W, D = _num(room.get("w"), 4, 40, "Ancho del local"), _num(room.get("d"), 4, 40, "Fondo del local")
    H = _num(room.get("h", 3.4), 2.4, 6.5, "Alto del local")
    fl = _only(raw.get("floor"), {"mat", "color"}, "Piso")
    if fl.get("mat") not in FLOORS:
        raise Rejected("Material de piso no válido.")
    walls = _only(raw.get("walls"), {"n", "s", "e", "w"}, "Paredes")
    out: dict = {"name": _text(raw.get("name"), 60, "Nombre") or "Mi local", "room": {"w": W, "d": D, "h": H},
                 "floor": {"mat": fl["mat"], "color": _color(fl.get("color"), "Piso") or "#c8a27a"}, "walls": {}, "openings": [], "objects": [], "people": []}
    for k in ("n", "s", "e", "w"):
        wc = _only(walls.get(k) or walls.get("n"), {"mat", "color"}, "Pared")
        if wc.get("mat") not in WALLS:
            raise Rejected("Material de pared no válido.")
        out["walls"][k] = {"mat": wc["mat"], "color": _color(wc.get("color"), "Pared") or "#e7e2f0"}
    seen: set = set()
    for o in _list(raw.get("openings"), MAX_OPENINGS, "Puertas y ventanas"):
        _only(o, {"id", "wall", "pos", "type", "width", "color"}, "Puerta o ventana")
        if o.get("wall") not in ("n", "s", "e", "w") or o.get("type") not in OPENINGS:
            raise Rejected("Puerta o ventana no válida.")
        item = {"id": _id(o.get("id"), "Puerta o ventana", seen), "wall": o["wall"], "pos": _num(o.get("pos"), 0, 1, "Posición en la pared"), "type": o["type"]}
        if o.get("width") is not None:
            item["width"] = _num(o.get("width"), 0.5, 4.5, "Ancho de la puerta o ventana")
        if _color(o.get("color"), "Color de la puerta"):
            item["color"] = o["color"].lower()
        out["openings"].append(item)
    used: dict = {}
    for o in _list(raw.get("objects"), MAX_OBJECTS, "Objetos"):
        _only(o, {"id", "item", "x", "z", "rot", "color", "color2", "color3", "text", "screen", "products", "conn"}, "Objeto")
        oid = _id(o.get("id"), "Objeto", seen)
        it = o.get("item")
        if not isinstance(it, str) or not ITEM_RE.match(it) or (it not in ITEMS and it not in glb):
            raise Rejected(f"El objeto {oid} no está en el catálogo.")
        item = {"id": oid, "item": it, "x": _num(o.get("x"), -W / 2 - 1, W / 2 + 1, "Posición x"), "z": _num(o.get("z"), -D / 2 - 1, D / 2 + 1, "Posición z"),
                "rot": round(_num(o.get("rot", 0) or 0, -720, 720, "Giro") % 360, 1)}
        for k in ("color", "color2", "color3"):
            if _color(o.get(k), "Color del objeto"):
                item[k] = o[k].lower()
        if o.get("text") not in (None, ""):
            item["text"] = _text(o.get("text"), 24, "Texto del letrero")
        if o.get("screen") not in (None, ""):
            if o["screen"] not in SCREENS:
                raise Rejected("Contenido de pantalla no válido.")
            item["screen"] = o["screen"]
        if o.get("products") not in (None, ""):
            if o["products"] not in PRODUCTS:
                raise Rejected("Productos de la nevera no válidos.")
            item["products"] = o["products"]
        con = o.get("conn")
        if con not in (None, ""):
            con = _text(con, 90, "Conexión")
            kind = conn_kind(it, glb)
            if not kind or not con.startswith(CONN_PREFIX[kind] + ":"):
                raise Rejected(f"El objeto {oid} no se puede conectar a ese dato.")
            if con in used:
                raise Rejected("Ese dato real ya está conectado a otro objeto.")
            used[con] = oid
            item["conn"] = con
        out["objects"].append(item)
    for p in _list(raw.get("people"), MAX_PEOPLE, "Personas"):
        _only(p, {"id", "pid", "x", "z", "rot", "clip"}, "Persona")
        if not isinstance(p.get("pid"), str) or not PID_RE.match(p["pid"]):
            raise Rejected("Persona del equipo no válida.")
        if p.get("clip", "idle") not in CLIPS:
            raise Rejected("Acción de la persona no válida.")
        out["people"].append({"id": _id(p.get("id"), "Persona", seen), "pid": p["pid"], "x": _num(p.get("x"), -W / 2 - 1, W / 2 + 1, "Posición x"),
                              "z": _num(p.get("z"), -D / 2 - 1, D / 2 + 1, "Posición z"), "rot": round(_num(p.get("rot", 0) or 0, -720, 720, "Giro") % 360, 1),
                              "clip": p.get("clip", "idle")})
    return out


def plan_hash(plan: dict) -> str:
    return hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


def import_doc(raw: bytes, glb: dict) -> dict:
    """.clonexa.json (exportado por el prototipo o por Clonexa) -> plano limpio. Las conexiones y las personas NO viajan:
    son datos reales de la empresa de origen."""
    if not raw or len(raw) > MAX_BYTES * 2:
        raise Rejected("Archivo vacío o demasiado grande.")
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise Rejected("Ese archivo no es un plano válido de Clonexa") from None
    if isinstance(doc, dict) and doc.get("formato") == FORMATO and isinstance(doc.get("plano"), dict):
        doc = doc["plano"]                        # exportado por la fase 1
    if not isinstance(doc, dict):
        raise Rejected("Ese archivo no es un plano válido de Clonexa")
    if "sala" in doc:
        doc = from_v1(doc)
    if not doc.get("room") or not doc.get("walls") or not doc.get("floor") or not isinstance(doc.get("objects"), list):
        raise Rejected("Ese archivo no es un plano válido de Clonexa")
    doc = dict(doc)
    doc["objects"] = [{k: v for k, v in o.items() if k != "conn"} for o in doc["objects"] if isinstance(o, dict)
                      and (o.get("item") in ITEMS or o.get("item") in glb)]
    doc["people"] = []
    for o in doc["objects"]:
        if not isinstance(o.get("id"), str) or not ID_RE.match(o["id"]):
            o["id"] = secrets.token_hex(4)
    return clean_plan(doc, glb)


# ------------------------------------------------------------------ fase 1 -> prototipo
WALL_FROM_V1 = {"listones": "madera", "panel_negro": "panel", "papel_tapiz": "tapiz"}
FLOOR_FROM_V1 = {"baldosa_blanca": "baldosa", "concreto_pulido": "concreto", "negro_brillante": "negro"}
OPENING_FROM_V1 = {"cortina_metalica": "cortina"}
ITEM_FROM_V1 = {
    "barra_isla": "isla", "sofa_lounge": "sofa", "parlante_pared": "parlante", "nevera": "nevera_bebidas", "vitrina_postres": "nevera_bebidas",
    "mesa_redonda_4": "mesa_redonda", "mesa_cuadrada_4": "mesa_cuadrada", "mesa_6": "mesa_larga", "mesa_butacas": "butaca", "butaca": "silla",
    "sillon": "puff", "banca": "silla", "tv_grande": "tv_pared", "pantalla_cocina": "tv_pared", "proyector": "tablero", "horno_lena": "horno",
    "meson_cocina": "meson", "meson_corto": "meson", "pase_platos": "pase", "estante_ollas": "meson", "caja_registradora": "caja",
    "plancha_industrial": "mesa_corte", "rollos_tela": "rollos", "carro_transporte": "estiba", "escritorio_pc": "escritorio",
    "escritorio_fila": "escritorio", "silla_ergonomica": "silla_ergo", "sala_juntas": "mesa_juntas", "tablero_grande": "tablero",
    "recepcion_mostrador": "mostrador", "gondola": "rack", "gondola_punta": "rack", "rack_alto": "rack", "cajas": "estiba",
    "estanteria": "rack", "lampara_colgante": "lampara", "lampara_pie": "foco", "logo_pared": "tv_pared", "planta_grande": "planta_alta",
    "planta_pequena": "planta", "palma": "planta_alta", "biombo": "division", "mesa_terraza": "mesa_cuadrada", "mesa_sombrilla": "mesa_redonda",
    "banca_exterior": "silla", "orinal": "sanitario",
}
SCREEN_FROM_V1 = {"canciones": "Canciones pedidas", "comandas": "Comandas en cocina", "domicilios": "Domicilios",
                  "produccion": "Tablero de producción", "logo": "Logo de la empresa"}


def person_key(employee_id: Any) -> str:
    return hashlib.sha256(f"{employee_id}".encode()).hexdigest()[:12]


def _wall_side(w: dict, W: float, D: float) -> Optional[tuple[str, bool]]:
    """Pared de la fase 1 (segmento) -> lado del local del prototipo (n/e/s/w) y si va al revés. Las paredes
    interiores no existen en el prototipo: se dejan fuera."""
    e = 0.3
    x1, z1, x2, z2 = w["x1"], w["z1"], w["x2"], w["z2"]
    if abs(z1) < e and abs(z2) < e:
        return "n", x1 > x2
    if abs(z1 - D) < e and abs(z2 - D) < e:
        return "s", x1 > x2
    if abs(x1) < e and abs(x2) < e:
        return "w", z1 > z2
    if abs(x1 - W) < e and abs(x2 - W) < e:
        return "e", z1 > z2
    return None


def from_v1(v1: dict, glb_ids: Optional[set] = None) -> dict:
    """Plano de la fase 1 -> plano del prototipo (pura). Posiciones al centro del local, giro con el mismo sentido
    visual (la fase 1 giraba al revés), materiales y aberturas por lado, objetos al modelo equivalente del catálogo
    nuevo (los 9 de Poly Haven y los subidos conservan su id), conexiones a claves de entidades reales."""
    glb_ids = set(glb_ids or ())
    sala = v1.get("sala") or {}
    W = min(40.0, max(4.0, float(sala.get("ancho") or 14)))
    D = min(40.0, max(4.0, float(sala.get("fondo") or 10)))
    H = min(6.5, max(2.4, float(sala.get("alto") or 3.4)))
    out: dict = {"name": "Mi local", "room": {"w": W, "d": D, "h": H}, "floor": {"mat": "madera_clara", "color": "#c8a27a"},
                 "walls": {}, "openings": [], "objects": [], "people": []}
    pisos = sorted(v1.get("pisos") or [], key=lambda f: -_area(f.get("puntos") or []))
    if pisos:
        mat = FLOOR_FROM_V1.get(pisos[0].get("material"), pisos[0].get("material"))
        out["floor"] = {"mat": mat if mat in FLOORS else "madera_clara", "color": pisos[0].get("color") or "#c8a27a"}
    sides: dict = {}
    for w in v1.get("paredes") or []:
        try:
            side = _wall_side(w, float(sala.get("ancho") or W), float(sala.get("fondo") or D))
        except (TypeError, KeyError):
            side = None
        if not side or side[0] in out["walls"]:
            continue
        mat = WALL_FROM_V1.get(w.get("material"), w.get("material"))
        out["walls"][side[0]] = {"mat": mat if mat in WALLS else "pintura", "color": w.get("color") or "#e7e2f0"}
        sides[w.get("id")] = (side[0], side[1], math.hypot(w["x2"] - w["x1"], w["z2"] - w["z1"]) or 1)
    for k in ("n", "s", "e", "w"):
        out["walls"].setdefault(k, {"mat": "pintura", "color": "#e7e2f0"})
    for i, a in enumerate(v1.get("aberturas") or []):
        sd = sides.get(a.get("pared"))
        kind = OPENING_FROM_V1.get(a.get("tipo"), a.get("tipo"))
        if not sd or kind not in OPENINGS:
            continue
        side, rev, L = sd
        frac = float(a.get("pos") or 0) / L
        if rev:   # en el prototipo "pos" crece con x (n/s) o con z (e/w)
            frac = 1 - frac
        o = {"id": f"a{i + 1}", "wall": side, "pos": round(min(0.98, max(0.02, frac)), 3), "type": kind}
        if a.get("ancho"):
            o["width"] = round(min(4.5, max(0.5, float(a["ancho"]))), 2)
        out["openings"].append(o)
    used: set = set()
    for i, ob in enumerate(v1.get("objetos") or []):
        asset = ob.get("asset")
        item = asset if asset in ITEMS or asset in glb_ids else ITEM_FROM_V1.get(asset)
        if not item or (item not in ITEMS and item not in glb_ids):
            continue
        x = round(min(W / 2 + 1, max(-W / 2 - 1, float(ob.get("x") or 0) - W / 2)), 3)
        z = round(min(D / 2 + 1, max(-D / 2 - 1, float(ob.get("z") or 0) - D / 2)), 3)
        o = {"id": str(ob.get("id") or f"o{i + 1}")[:40], "item": item, "x": x, "z": z, "rot": round((-(float(ob.get("rot") or 0))) % 360, 1)}
        if ob.get("color"):
            o["color"] = ob["color"]
        if item == "neon" and ob.get("texto"):
            o["text"] = str(ob["texto"])[:24]
        if asset == "logo_pared":
            o["screen"] = "Logo de la empresa"
        con = ob.get("conexion") or {}
        key = _conn_from_v1(con, item)
        if key and key not in used:
            used.add(key)
            o["conn"] = key
            if con.get("tipo") == "pantalla" and SCREEN_FROM_V1.get(con.get("id")):
                o["screen"] = SCREEN_FROM_V1[con["id"]]
        out["objects"].append(o)
    return out


def _conn_from_v1(con: dict, item: str) -> Optional[str]:
    t, cid = con.get("tipo"), str(con.get("id") or "")
    kind = conn_kind(item)
    if not t or not cid or not kind:
        return None
    if t == "mesa" and kind == "mesa":
        return f"mesa:{cid}"
    if t == "puesto" and kind == "puesto":
        n = cid.split("-")[-1]
        return f"puesto:{n}" if n.isdigit() else None
    if t == "escritorio" and kind == "escritorio":
        return f"emp:{person_key(cid)}"
    if t == "caja" and kind == "caja" and cid in CASH_DESKS:
        return f"caja:{cid}"
    if t == "pantalla" and kind == "pantalla" and cid in SCREEN_FEEDS:
        return f"pantalla:{cid}"
    return None


def _area(pts: list) -> float:
    try:
        return abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))) / 2
    except (TypeError, IndexError):
        return 0.0


def ensure_v2(plan: Any, glb_ids: Optional[set] = None) -> dict:
    if isinstance(plan, str):
        plan = json.loads(plan)
    if isinstance(plan, dict) and "sala" in plan:
        return from_v1(plan, glb_ids)
    return plan if isinstance(plan, dict) else {}


# ------------------------------------------------------------------ "Aplicar Estudio de marca a todo" (mismas reglas del prototipo)
def apply_brand_to_plan(plan: dict, brand: list[str], neon: str) -> int:
    p1, p2, dk, lt = brand
    n = 0
    for o in plan.get("objects") or []:
        it = o.get("item") or ""
        if it == "neon":
            o["color"], o["text"] = p1, (neon or "")[:24]
            n += 1
        if it == "tira_led":
            o["color"] = p2
            n += 1
        if it == "pista_led":
            o["color"], o["color2"], o["color3"] = p1, p2, lt
            n += 1
        if it in ("sofa", "puff", "tapete"):
            o["color"] = p2
            n += 1
        if it == "cabina_dj":
            o["color"], o["color2"] = dk, p1
            n += 1
        if re.match(r"^barra_|isla", it):
            o["color3"] = p1
            n += 1
        if it == "contrabarra":
            o["color2"] = p2
            n += 1
        if re.match(r"^tv|tablero", it):
            o["color2"] = p1
        if re.match(r"^mesa_(redonda|cuadrada|2|larga)|butaca", it):
            o["color2"] = p1
            n += 1
        if it in ("caja", "mostrador"):
            o["color"] = dk
            n += 1
    return n


def apply_brand_to_uniforms(uniforms: list[dict], brand: list[str]) -> None:
    p1, p2 = brand[0], brand[1]
    for i, u in enumerate(uniforms):
        col = p2 if i % 2 else p1
        toon, human = u.setdefault("toon", {}), u.setdefault("human", {})
        if toon.get("top") != "chef":
            toon["topColor"] = col
        if (toon.get("acc") or {}).get("delantal"):
            toon["accColor"] = p1
        if human.get("topColor") and human.get("topColor") != "#ffffff":
            human["topColor"] = col


def brand_colors(b: dict) -> list[str]:
    """Estudio de marca -> [Principal, Secundario, Oscuro, Claro] del prototipo."""
    c = (b or {}).get("colors") or {}

    def ok(v: Any, d: str) -> str:
        return v.lower() if isinstance(v, str) and COLOR_RE.match(v) else d

    bg, text_ = ok(c.get("background"), "#111111"), ok(c.get("text"), "#ffffff")
    dark, light = (bg, text_) if _lum(bg) <= _lum(text_) else (text_, bg)
    return [ok(c.get("primary"), "#f20b6d"), ok(c.get("secondary"), "#7c3aed"), dark, light]


def _lum(h: str) -> float:
    r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
    return 0.299 * r + 0.587 * g + 0.114 * b


# ------------------------------------------------------------------ personajes y uniformes (puros)
def clean_toon(v: Any) -> dict:
    if not isinstance(v, dict):
        raise Rejected("Personaje no válido.")
    out: dict = {}
    for k, val in v.items():
        if k in TOON_OPTS:
            if val not in TOON_OPTS[k]:
                raise Rejected(f"Opción no válida ({k}).")
            out[k] = val
        elif k in TOON_COLORS:
            c = _color(val, "Color")
            if c:
                out[k] = c
        elif k in TOON_NUMS:
            lo, hi = TOON_NUMS[k]
            out[k] = _num(val, lo, hi, k)
        elif k in TOON_BOOLS:
            out[k] = bool(val)
        elif k == "acc":
            if not isinstance(val, dict) or any(a not in TOON_ACC for a in val):
                raise Rejected("Accesorio no válido.")
            out["acc"] = {a: True for a, on in val.items() if on}
        else:
            raise Rejected(f"Campo desconocido del personaje ({str(k)[:20]}).")
    return out


def clean_human(v: Any) -> dict:
    if not isinstance(v, dict):
        raise Rejected("Personaje no válido.")
    out: dict = {}
    for k, val in v.items():
        if k == "base":
            if val not in HUMAN_BASES:
                raise Rejected("Persona base no válida.")
            out["base"] = val
        elif k in HUMAN_COLORS:
            if val in (None, ""):
                out[k] = ""
            else:
                out[k] = _color(val, "Color")
        elif k in HUMAN_OPTS:
            if val not in HUMAN_OPTS[k]:
                raise Rejected(f"Opción no válida ({k}).")
            out[k] = val
        elif k == "acc":
            # en Humano no hay accesorios sueltos (decisión del dueño): siempre vacío
            out["acc"] = {}
        else:
            raise Rejected(f"Campo desconocido del personaje ({str(k)[:20]}).")
    return out


def clean_uniforms(raw: Any) -> list[dict]:
    items = _list(raw, 40, "Uniformes")
    out, seen = [], set()
    for u in items:
        _only(u, {"id", "name", "desc", "toon", "human"}, "Uniforme")
        uid = _id(u.get("id"), "Uniforme", seen)
        name = _text(u.get("name"), 40, "Nombre del uniforme")
        if not name:
            raise Rejected("Ponle nombre al uniforme.")
        out.append({"id": uid, "name": name, "desc": _text(u.get("desc"), 80, "Descripción"),
                    "toon": clean_toon(u.get("toon") or {}), "human": clean_human(u.get("human") or {})})
    return out


def default_uniforms() -> list[dict]:
    return [
        {"id": "u-barra", "name": "Barra", "desc": "Camisa negra + delantal", "toon": {"top": "camiseta", "topColor": "#18181b", "bottom": "pantalon", "bottomColor": "#4b5563", "complete": "ninguno", "acc": {"delantal": True}, "accColor": "#f20b6d"}, "human": {"topColor": "#111111", "topStyle": "liso", "bottomColor": "#1f1f24"}},
        {"id": "u-caja", "name": "Caja", "desc": "Chaqueta + jean", "toon": {"top": "chaqueta", "topColor": "#d59f2a", "innerColor": "#ffffff", "bottom": "jean", "bottomColor": "#2c4a7c", "complete": "ninguno"}, "human": {"topColor": "#d59f2a", "topStyle": "liso", "bottomColor": "#2c4a7c"}},
        {"id": "u-cocina", "name": "Cocina", "desc": "Chaqueta de chef + gorro", "toon": {"top": "chef", "bottom": "pantalon", "bottomColor": "#1f2937", "complete": "ninguno", "acc": {"gorro_chef": True}}, "human": {"topColor": "#ffffff", "topStyle": "liso", "bottomColor": "#1f2937"}},
        {"id": "u-salon", "name": "Salón", "desc": "Buzo de la marca", "toon": {"top": "buzo", "topColor": "#7c3aed", "bottom": "pantalon", "bottomColor": "#111827", "complete": "ninguno"}, "human": {"topColor": "#7c3aed", "topStyle": "liso", "bottomColor": "#111827"}},
    ]


def clean_look(body: Any) -> dict:
    """Lo que guarda el editor de una persona: {name?, area?, toon, human, uniform, custom}."""
    _only(body, {"name", "area", "toon", "human", "uniform", "custom", "role", "shift"}, "Personaje")
    area = body.get("area") or ""
    if area and area not in AREAS:
        raise Rejected("Área no válida.")
    uni = body.get("uniform")
    if uni not in (None, "") and (not isinstance(uni, str) or not ID_RE.match(uni)):
        raise Rejected("Uniforme no válido.")
    return {"name": _text(body.get("name"), 40, "Nombre"), "area": area, "toon": clean_toon(body.get("toon") or {}),
            "human": clean_human(body.get("human") or {}), "uniform": uni or None, "custom": bool(body.get("custom"))}


def legacy_columns(look: dict) -> dict:
    """El personaje nuevo también escribe las columnas del editor viejo: los pisos de siempre (bar, aprobados) siguen
    viendo el mismo color de ropa, pelo y persona base."""
    h = look.get("human") or {}
    base = h.get("base") or ""
    return {"color_ropa": h.get("topColor") or "", "color_pantalon": h.get("bottomColor") or "", "color_pelo": h.get("hairColor") or "",
            "personaje": base, "genero": ("mujer" if base in FEMALE_BASES else "hombre") if base else "",
            "barba": {"corta": "corta", "larga": "larga"}.get(h.get("beard") or "", ""), "color_barba": h.get("beardColor") or "",
            "nombre": (look.get("name") or "")[:80], "rol": (look.get("area") or "")[:40]}


def look_from_legacy(row: dict) -> tuple[dict, dict]:
    """Personaje guardado con el editor viejo de la oficina -> partes del prototipo (lo que se conserva)."""
    toon, human = {}, {}
    if row.get("personaje") in HUMAN_BASES:
        human["base"] = row["personaje"]
    elif row.get("genero") == "mujer":
        human["base"] = "Ch22_nonPBR"
    elif row.get("genero") == "hombre":
        human["base"] = "Remy"
    for src, dst in (("color_ropa", "topColor"), ("color_pantalon", "bottomColor"), ("color_pelo", "hairColor")):
        if COLOR_RE.match(row.get(src) or ""):
            human[dst] = row[src].lower()
            toon[dst] = row[src].lower()
    if human.get("topColor"):
        human["topStyle"] = "liso"
    if COLOR_RE.match(row.get("color_piel") or ""):
        toon["skin"] = row["color_piel"].lower()
    if row.get("barba") in ("corta", "larga"):
        human["beard"] = toon["beard"] = row["barba"]
        if COLOR_RE.match(row.get("color_barba") or ""):
            human["beardColor"] = toon["beardColor"] = row["color_barba"].lower()
    return toon, human


def area_for(role: Any, template: str) -> str:
    from app.services import oficina as of

    return AREA_BY_UNIFORM.get(of.uniform_for(role, template), "Oficina" if template in ("general",) else "Salón")


def shift_text(on: bool) -> str:
    return "En turno ahora" if on else "Sin turno abierto"


# ------------------------------------------------------------------ base de datos: diseños (siempre por company_id)
def _row(r: Any) -> dict:
    d = dict(r)
    if isinstance(d.get("plano"), str):
        d["plano"] = json.loads(d["plano"])
    return d


async def designs(db: AsyncSession, cid: str, glb_ids: Optional[set] = None) -> list[dict]:
    rows = (await db.execute(text("""SELECT diseno_id, nombre, version, plano, miniatura, updated_at FROM constructor_planos
        WHERE company_id = CAST(:c AS uuid) AND estado = 'borrador' ORDER BY updated_at DESC LIMIT :n"""), {"c": cid, "n": DESIGNS_MAX})).mappings().all()
    pubs = {r["diseno_id"]: int(r["v"]) for r in (await db.execute(text("""SELECT diseno_id, MAX(version) AS v FROM constructor_planos
        WHERE company_id = CAST(:c AS uuid) AND estado = 'publicado' GROUP BY diseno_id"""), {"c": cid})).mappings().all()}
    live = await live_design(db, cid)
    out = []
    for r in rows:
        d = _row(r)
        out.append({"id": d["diseno_id"], "name": d["nombre"] or "Mi local", "plan": ensure_v2(d["plano"], glb_ids), "version": pubs.get(d["diseno_id"], 0),
                    "live": d["diseno_id"] == live, "updated": int(d["updated_at"].timestamp() * 1000) if d.get("updated_at") else 0,
                    "thumb_key": d.get("miniatura")})
    return out


async def live_design(db: AsyncSession, cid: str) -> Optional[str]:
    try:
        r = (await db.execute(text("SELECT usa_plano, plano_diseno FROM oficina_pisos WHERE company_id = CAST(:c AS uuid)"), {"c": cid})).mappings().first()
    except Exception:
        await db.rollback()
        return None
    if not r or r["usa_plano"] is not True:
        return None
    if r["plano_diseno"]:
        return r["plano_diseno"]
    found = (await db.execute(text("""SELECT diseno_id FROM constructor_planos WHERE company_id = CAST(:c AS uuid) AND estado = 'publicado'
        ORDER BY version DESC LIMIT 1"""), {"c": cid})).scalar()
    return found


async def design_exists(db: AsyncSession, cid: str, did: str) -> bool:
    return bool((await db.execute(text("""SELECT 1 FROM constructor_planos WHERE company_id = CAST(:c AS uuid) AND diseno_id = :d AND estado = 'borrador'"""),
                                  {"c": cid, "d": did})).scalar())


async def count_designs(db: AsyncSession, cid: str) -> int:
    return int((await db.execute(text("SELECT count(*) FROM constructor_planos WHERE company_id = CAST(:c AS uuid) AND estado = 'borrador'"),
                                 {"c": cid})).scalar() or 0)


async def save_design(db: AsyncSession, cid: str, did: str, name: str, plan: dict, actor: str, thumb_key: Optional[str] = None) -> dict:
    """Autoguardado: una fila 'borrador' por diseño (índice único parcial (company_id, diseno_id))."""
    await db.execute(text("""
        INSERT INTO constructor_planos (id, company_id, diseno_id, nombre, version, estado, plano, miniatura, creado_por, created_at, updated_at)
        VALUES (CAST(:id AS uuid), CAST(:c AS uuid), :d, :n, 0, 'borrador', CAST(:p AS jsonb), :m, :a, now(), now())
        ON CONFLICT (company_id, diseno_id) WHERE estado = 'borrador'
        DO UPDATE SET plano = EXCLUDED.plano, nombre = EXCLUDED.nombre, creado_por = EXCLUDED.creado_por,
                      miniatura = COALESCE(EXCLUDED.miniatura, constructor_planos.miniatura), updated_at = now()
    """), {"id": str(uuid.uuid4()), "c": cid, "d": did, "n": (name or "Mi local")[:60], "p": json.dumps(plan), "m": thumb_key, "a": actor[:120]})
    await db.commit()
    return {"id": did, "hash": plan_hash(plan)}


async def delete_design(db: AsyncSession, cid: str, did: str) -> bool:
    live = await live_design(db, cid)
    n = (await db.execute(text("DELETE FROM constructor_planos WHERE company_id = CAST(:c AS uuid) AND diseno_id = :d"), {"c": cid, "d": did})).rowcount
    if live == did:   # el diseño en vivo se borró: la empresa vuelve a su piso de siempre
        await db.execute(text("UPDATE oficina_pisos SET usa_plano = FALSE, plano_diseno = NULL, updated_at = now() WHERE company_id = CAST(:c AS uuid)"), {"c": cid})
    await db.commit()
    return bool(n)


async def publish(db: AsyncSession, cid: str, did: str, plan: dict, actor: str) -> int:
    v = int((await db.execute(text("""SELECT COALESCE(MAX(version), 0) FROM constructor_planos WHERE company_id = CAST(:c AS uuid)
        AND diseno_id = :d AND estado = 'publicado'"""), {"c": cid, "d": did})).scalar() or 0) + 1
    await db.execute(text("""
        INSERT INTO constructor_planos (id, company_id, diseno_id, nombre, version, estado, plano, creado_por, created_at, updated_at)
        SELECT CAST(:id AS uuid), CAST(:c AS uuid), :d, nombre, :v, 'publicado', CAST(:p AS jsonb), :a, now(), now() FROM constructor_planos
        WHERE company_id = CAST(:c AS uuid) AND diseno_id = :d AND estado = 'borrador'
    """), {"id": str(uuid.uuid4()), "c": cid, "d": did, "v": v, "p": json.dumps(plan), "a": actor[:120]})
    await db.execute(text("""DELETE FROM constructor_planos WHERE company_id = CAST(:c AS uuid) AND diseno_id = :d AND estado = 'publicado'
        AND version <= :cut"""), {"c": cid, "d": did, "cut": v - HISTORY_MAX})
    await db.execute(text("""
        INSERT INTO oficina_pisos (company_id, usa_plano, plano_diseno, updated_by) VALUES (CAST(:c AS uuid), TRUE, :d, :a)
        ON CONFLICT (company_id) DO UPDATE SET usa_plano = TRUE, plano_diseno = EXCLUDED.plano_diseno, updated_by = EXCLUDED.updated_by, updated_at = now()
    """), {"c": cid, "d": did, "a": actor[:120]})
    await db.commit()
    return v


async def versions(db: AsyncSession, cid: str, did: str) -> list[dict]:
    rows = (await db.execute(text("""SELECT version, created_at FROM constructor_planos WHERE company_id = CAST(:c AS uuid) AND diseno_id = :d
        AND estado = 'publicado' ORDER BY version DESC LIMIT :n"""), {"c": cid, "d": did, "n": HISTORY_MAX})).mappings().all()
    return [{"n": int(r["version"]), "date": int(r["created_at"].timestamp() * 1000) if r["created_at"] else 0} for r in rows]


async def version_plan(db: AsyncSession, cid: str, did: str, n: int, glb_ids: Optional[set] = None) -> Optional[dict]:
    r = (await db.execute(text("""SELECT plano FROM constructor_planos WHERE company_id = CAST(:c AS uuid) AND diseno_id = :d AND estado = 'publicado'
        AND version = :v"""), {"c": cid, "d": did, "v": int(n)})).scalar()
    return ensure_v2(r, glb_ids) if r is not None else None


async def draft_plan(db: AsyncSession, cid: str, did: str, glb_ids: Optional[set] = None) -> Optional[dict]:
    r = (await db.execute(text("""SELECT plano FROM constructor_planos WHERE company_id = CAST(:c AS uuid) AND diseno_id = :d AND estado = 'borrador'"""),
                          {"c": cid, "d": did})).scalar()
    return ensure_v2(r, glb_ids) if r is not None else None


async def live_plan(db: AsyncSession, cid: str, glb_ids: Optional[set] = None) -> Optional[dict]:
    """El plano que se VE (Oficina 3D y Negocio en vivo 3D): la última versión publicada del diseño en vivo, solo con el
    interruptor de la empresa. None = la empresa sigue con su piso de siempre."""
    try:
        did = await live_design(db, cid)
        if not did:
            return None
        r = (await db.execute(text("""SELECT version, plano FROM constructor_planos WHERE company_id = CAST(:c AS uuid) AND diseno_id = :d
            AND estado = 'publicado' ORDER BY version DESC LIMIT 1"""), {"c": cid, "d": did})).mappings().first()
    except Exception:
        await db.rollback()
        return None
    return {"version": int(r["version"]), "plano": ensure_v2(r["plano"], glb_ids), "diseno": did} if r else None


async def live_versions(db: AsyncSession, ids: list[str]) -> dict[str, int]:
    """Versión en vivo por empresa (una consulta, para la lista de pisos de la oficina)."""
    if not ids:
        return {}
    try:
        rows = (await db.execute(text("""
            SELECT p.company_id::text AS c, MAX(p.version) AS v FROM constructor_planos p
            JOIN oficina_pisos o ON o.company_id = p.company_id AND o.usa_plano IS TRUE
            WHERE p.estado = 'publicado' AND p.company_id::text = ANY(:ids)
              AND (o.plano_diseno IS NULL OR p.diseno_id = o.plano_diseno) GROUP BY p.company_id
        """), {"ids": ids})).mappings().all()
    except Exception:
        await db.rollback()
        return {}
    return {r["c"]: int(r["v"]) for r in rows}


async def style(db: AsyncSession, cid: str) -> str:
    try:
        v = (await db.execute(text("SELECT estilo_escena FROM oficina_pisos WHERE company_id = CAST(:c AS uuid)"), {"c": cid})).scalar()
    except Exception:
        await db.rollback()
        v = None
    return "toon" if v == "caricatura" else "human"


async def set_style(db: AsyncSession, cid: str, mode: str, actor: str) -> None:
    await db.execute(text("""INSERT INTO oficina_pisos (company_id, estilo_escena, updated_by) VALUES (CAST(:c AS uuid), :e, :a)
        ON CONFLICT (company_id) DO UPDATE SET estilo_escena = EXCLUDED.estilo_escena, updated_by = EXCLUDED.updated_by, updated_at = now()"""),
                     {"c": cid, "e": STYLES[mode], "a": actor[:120]})
    await db.commit()


# ------------------------------------------------------------------ uniformes
async def uniforms(db: AsyncSession, cid: str) -> list[dict]:
    rows = (await db.execute(text("""SELECT id, nombre, descripcion, toon, human FROM constructor_uniformes WHERE company_id = CAST(:c AS uuid)
        ORDER BY orden, created_at"""), {"c": cid})).mappings().all()
    if not rows:
        seeded = (await db.execute(text("SELECT b3d_uniformes FROM oficina_pisos WHERE company_id = CAST(:c AS uuid)"), {"c": cid})).scalar()
        if seeded is not True:   # la primera vez: los 4 uniformes del prototipo (luego se pueden borrar)
            await save_uniforms(db, cid, default_uniforms(), "semilla")
            return default_uniforms()
        return []
    out = []
    for r in rows:
        t, h = r["toon"], r["human"]
        out.append({"id": r["id"], "name": r["nombre"], "desc": r["descripcion"] or "", "toon": json.loads(t) if isinstance(t, str) else (t or {}),
                    "human": json.loads(h) if isinstance(h, str) else (h or {})})
    return out


async def save_uniforms(db: AsyncSession, cid: str, items: list[dict], actor: str) -> None:
    await db.execute(text("DELETE FROM constructor_uniformes WHERE company_id = CAST(:c AS uuid)"), {"c": cid})
    for i, u in enumerate(items):
        await db.execute(text("""INSERT INTO constructor_uniformes (company_id, id, nombre, descripcion, toon, human, orden, updated_by)
            VALUES (CAST(:c AS uuid), :i, :n, :d, CAST(:t AS jsonb), CAST(:h AS jsonb), :o, :a)"""),
                         {"c": cid, "i": u["id"], "n": u["name"], "d": u.get("desc") or "", "t": json.dumps(u.get("toon") or {}), "h": json.dumps(u.get("human") or {}),
                          "o": i, "a": actor[:120]})
    await db.execute(text("""INSERT INTO oficina_pisos (company_id, b3d_uniformes, updated_by) VALUES (CAST(:c AS uuid), TRUE, :a)
        ON CONFLICT (company_id) DO UPDATE SET b3d_uniformes = TRUE"""), {"c": cid, "a": actor[:120]})
    await db.commit()


# ------------------------------------------------------------------ equipo: módulo Personal real + su personaje
async def _employees(db: AsyncSession, cid: str) -> list[dict]:
    try:
        return [dict(r) for r in (await db.execute(text("""SELECT id::text AS id, full_name, role FROM employees WHERE company_id = CAST(:c AS uuid)
            AND LOWER(COALESCE(status, 'active')) = 'active' ORDER BY full_name LIMIT 300"""), {"c": cid})).mappings().all()]
    except Exception:
        await db.rollback()
        return []


async def _looks(db: AsyncSession, cid: str) -> dict[str, dict]:
    try:
        rows = (await db.execute(text("""SELECT clave, nombre, rol, look, color_ropa, color_pantalon, color_pelo, color_piel, personaje, genero,
            barba, color_barba FROM oficina_personajes WHERE company_id = CAST(:c AS uuid) AND clave LIKE 'persona:%'"""), {"c": cid})).mappings().all()
    except Exception:
        await db.rollback()
        return {}
    out = {}
    for r in rows:
        d = dict(r)
        if isinstance(d.get("look"), str):
            d["look"] = json.loads(d["look"])
        out[d["clave"].split(":", 1)[1]] = d
    return out


async def team(db: AsyncSession, cid: str, template: str, privacy: str, on_shift: set) -> list[dict]:
    from app.services import oficina as of

    looks = await _looks(db, cid)
    out = []
    for e in await _employees(db, cid):
        key = person_key(e["id"])
        row = looks.pop(key, None) or {}
        look = row.get("look") or {}
        short = of.short_name(e["full_name"])
        name = (privacy != "cargo" and short) or of.role_label(e["role"])
        if look:
            toon, human = look.get("toon") or {}, look.get("human") or {}
        else:
            toon, human = look_from_legacy(row)
        out.append({"id": key, "name": look.get("name") or name, "role": of.role_label(e["role"]), "area": look.get("area") or area_for(e["role"], template),
                    "shift": shift_text(e["id"] in on_shift), "custom": bool(look.get("custom")), "toon": toon, "human": human,
                    "uniform": look.get("uniform"), "real": True})
    for key, row in looks.items():   # "Nuevo personaje" (no ligado al Personal) que se creó en el editor
        look = row.get("look") or {}
        if not look.get("extra"):
            continue
        out.append({"id": key, "name": look.get("name") or row.get("nombre") or "Nueva persona", "role": look.get("role") or "Mesero/a",
                    "area": look.get("area") or "Salón", "shift": look.get("shift") or "Turno noche", "custom": bool(look.get("custom")),
                    "toon": look.get("toon") or {}, "human": look.get("human") or {}, "uniform": look.get("uniform"), "real": False})
    return out


async def real_keys(db: AsyncSession, cid: str) -> set[str]:
    return {person_key(e["id"]) for e in await _employees(db, cid)}


async def save_person(db: AsyncSession, cid: str, pid: str, look: dict, actor: str) -> None:
    cols = legacy_columns(look)
    await db.execute(text("""
        INSERT INTO oficina_personajes (company_id, clave, look, nombre, rol, color_ropa, color_pantalon, color_pelo, personaje, genero, barba, color_barba, updated_by)
        VALUES (CAST(:c AS uuid), :k, CAST(:l AS jsonb), :nombre, :rol, :color_ropa, :color_pantalon, :color_pelo, :personaje, :genero, :barba, :color_barba, :a)
        ON CONFLICT ((COALESCE(company_id::text, '')), clave) DO UPDATE SET look = EXCLUDED.look, nombre = EXCLUDED.nombre, rol = EXCLUDED.rol,
            color_ropa = EXCLUDED.color_ropa, color_pantalon = EXCLUDED.color_pantalon, color_pelo = EXCLUDED.color_pelo, personaje = EXCLUDED.personaje,
            genero = EXCLUDED.genero, barba = EXCLUDED.barba, color_barba = EXCLUDED.color_barba, updated_by = EXCLUDED.updated_by, updated_at = now()
    """), {"c": cid, "k": f"persona:{pid}", "l": json.dumps(look), "a": actor[:120], **cols})
    await db.commit()


async def looks_for_engine(db: AsyncSession, cid: str) -> dict[str, dict]:
    """Personaje de cada persona (por su huella) para el motor en vivo: solo toon/human, nunca nombres."""
    out = {}
    for key, row in (await _looks(db, cid)).items():
        look = row.get("look") or {}
        toon, human = (look.get("toon") or {}, look.get("human") or {}) if look else look_from_legacy(row)
        out[key] = {"toon": toon, "human": human}
    return out


# ------------------------------------------------------------------ entidades reales de ESA empresa (Conectar)
async def entities(db: AsyncSession, cid: str, privacy: str) -> dict[str, list[dict]]:
    from app.services import carta_links
    from app.services import oficina as of

    out: dict[str, list[dict]] = {k: [] for k in CONN_PREFIX}
    try:
        out["mesa"] = [{"id": f"mesa:{t}", "label": t} for t in await carta_links.mesa_labels(db, cid)]
    except Exception:
        await db.rollback()
    emps = await _employees(db, cid)
    out["puesto"] = [{"id": f"puesto:{i}", "label": f"Puesto {i}"} for i in range(1, min(STATIONS_MAX, max(12, len(emps))) + 1)]
    labels: dict[str, int] = {}
    for e in emps:
        base = (privacy != "cargo" and of.short_name(e["full_name"])) or of.role_label(e["role"])
        labels[base] = labels.get(base, 0) + 1
        out["escritorio"].append({"id": f"emp:{person_key(e['id'])}", "label": base if labels[base] == 1 else f"{base} ({labels[base]})"})
    out["caja"] = [{"id": f"caja:{k}", "label": v} for k, v in CASH_DESKS.items()]
    out["pantalla"] = [{"id": f"pantalla:{k}", "label": f"Pantalla · {v}"} for k, v in SCREEN_FEEDS.items()]
    try:
        cats = (await db.execute(text("""SELECT DISTINCT COALESCE(NULLIF(TRIM(category), ''), 'General') AS c FROM inventory_items
            WHERE company_id = CAST(:c AS uuid) AND LOWER(COALESCE(status, 'active')) = 'active' ORDER BY 1 LIMIT 40"""), {"c": cid})).scalars().all()
        out["inventario"] = [{"id": f"inv:{c[:60]}", "label": f"Inventario · {c}"} for c in cats]
    except Exception:
        await db.rollback()
    out["sonido"] = [{"id": "sonido:canciones", "label": "Canciones pedidas"}]
    return out


async def inventory_live(db: AsyncSession, cid: str) -> dict[str, dict]:
    """Inventario real por categoría para la nevera conectada: productos activos y cuántos están en su mínimo o debajo."""
    try:
        rows = (await db.execute(text("""SELECT COALESCE(NULLIF(TRIM(category), ''), 'General') AS c, count(*) AS n,
            count(*) FILTER (WHERE COALESCE(current_stock, 0) <= COALESCE(min_stock, 0)) AS low FROM inventory_items
            WHERE company_id = CAST(:c AS uuid) AND LOWER(COALESCE(status, 'active')) = 'active' GROUP BY 1 ORDER BY 1 LIMIT 40"""), {"c": cid})).mappings().all()
    except Exception:
        await db.rollback()
        return {}
    return {str(r["c"])[:60]: {"items": int(r["n"]), "low": int(r["low"])} for r in rows}


def for_engine(plan: dict, entity_ids: Optional[set] = None) -> dict:
    """Plano para el motor en vivo: sin nombres de personas (las personas del plano y los escritorios van por huella) y
    solo conexiones que existen hoy en ESA empresa."""
    out = copy.deepcopy(plan)
    if entity_ids is not None:
        for o in out.get("objects", []):
            if o.get("conn") and o["conn"] not in entity_ids and not o["conn"].startswith(("puesto:", "caja:", "pantalla:", "sonido:")):
                o.pop("conn", None)
    return out


def new_person_key() -> str:
    return secrets.token_hex(6)


__all__ = ["clean_plan", "from_v1", "import_doc", "apply_brand_to_plan", "team", "entities", "live_plan", "uniforms"]
