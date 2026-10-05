"""Estudio de marca · tokens, validacion y generador (Fase 4 y etapa 2).

Nada de CSS libre: los tokens son solo colores hex, numeros con rango y
opciones de listas cerradas, validados aqui con claves estrictas (una clave
desconocida se rechaza). La marca llega a una pagina SOLO por css_for(), que
arma cada valor con un formateador propio y al final verifica que el
resultado no tenga nada fuera de lo esperado.

tokens = {
  "theme": {colors{9}, font{family, size?, heading_weight?}, radius, shadow, glow, logo,
            panels: bool,                      # aplicar la marca a restaurante y mini paneles
            portal: {background_style, card_style, theme_mode, gradient_from, gradient_to, gradient_extra, gradient_angle}},
  "backgrounds": {"general": Fondo, <pantalla del registro>: Fondo | {"inherit": true} | {"own": true}},
  "components": {tipo: Estilo},          # tipos de brand_registry.json
  "pieces": {pieza: Estilo},             # piezas de brand_registry.json
}
Fondo   = {base: Relleno, image: null | {id, mode, size, position, opacity}, veil: null | {gradient, darken, blur, opacity}}
Relleno = {kind: "solid", color} | {kind: "gradient", gradient: {type, angle, stops[2..3]{color, at}}}
          | {kind: "preset"}   (solo la base de un fondo: el estilo de fondo del portal, theme.portal.background_style)
"own"   = la pantalla conserva el fondo de su panel (no se pinta nada).
Estilo  = {fill?, border?{width,color}, glow?, shadow?, radius?, text?{color,weight,size}, hover?, active?}
"""
from __future__ import annotations

import colorsys
import copy
import io
import json
import re
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from app.services import portal_base_css as portal_css

REGISTRY_PATH = Path(__file__).resolve().parent.parent / "web" / "brand_registry.json"
COLOR_KEYS = ("primary", "secondary", "background", "surface", "text", "text_muted", "success", "warning", "danger")
FONTS = ("Inter", "Manrope", "Sora", "Space Grotesk", "Rajdhani", "Orbitron", "Poppins", "Montserrat", "Sistema")
PORTAL_FONTS = FONTS[:-1]
IMAGE_MODES = ("cover", "watermark", "pattern")
POSITIONS = ("center", "top", "bottom", "left", "right", "top left", "top right", "bottom left", "bottom right")
PAGES = ("portal", "login", "panels", "mini")
MAX_TOKENS_BYTES = 64 * 1024
MAX_VERSIONS = 10
_HEX = re.compile(r"^#[0-9a-f]{6}$")
_SHORT_HEX = re.compile(r"^#[0-9a-f]{3}$")
_SAFE_SELECTOR = re.compile(r"^[a-z0-9 .:_\-\[\]=()#,]+$", re.IGNORECASE)
# Valores por defecto de normalizeBranding() en client.js.
PORTAL_DEFAULT = {"background_style": "aurora_boreal", "card_style": "glass_premium", "theme_mode": "dark",
                  "gradient_from": "#ff2bd6", "gradient_to": "#00ff88", "gradient_extra": "#050509", "gradient_angle": 135}


class BrandInvalid(ValueError):
    def __init__(self, path: str, message: str):
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


# ---------------------------------------------------------------- registro ---
@lru_cache(maxsize=1)
def registry() -> dict:
    data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    families = set(data["families"])
    for screen, spec in data["screens"].items():
        if not re.match(r"^[a-z_]+$", screen) or spec["family"] not in families or spec["page"] not in PAGES:
            raise ValueError(f"pantalla invalida {screen}")
        for sel in spec["scope"]:
            if not _SAFE_SELECTOR.match(sel):
                raise ValueError(f"selector inseguro {sel}")
        for prefix in spec["prefixes"]:
            if not re.match(r"^[a-z0-9]+$", prefix):
                raise ValueError(f"prefijo invalido {prefix}")
    for kind, spec in data["types"].items():
        if not re.match(r"^[a-z_]+$", kind):
            raise ValueError(f"tipo invalido {kind}")
        for sel in spec["selectors"]:
            if not _SAFE_SELECTOR.match(sel):
                raise ValueError(f"selector inseguro {sel}")
    keys = set()
    for piece in data["pieces"]:
        if not re.match(r"^[a-z]+\.[a-z_]+$", piece["key"]) or piece["screen"] not in data["screens"] or piece["type"] not in data["types"]:
            raise ValueError(f"pieza invalida {piece}")
        if piece.get("selector") and not _SAFE_SELECTOR.match(piece["selector"]):
            raise ValueError(f"selector inseguro {piece['selector']}")
        if piece["key"] in keys:
            raise ValueError(f"pieza repetida {piece['key']}")
        keys.add(piece["key"])
    return data


def screen_keys() -> tuple[str, ...]:
    return tuple(registry()["screens"])


def screens_of(page: str) -> list[str]:
    return [k for k, s in registry()["screens"].items() if s["page"] == page]


def piece_keys() -> set[str]:
    return {p["key"] for p in registry()["pieces"]}


def type_keys() -> set[str]:
    return set(registry()["types"])


def keeps_own_background(spec: dict) -> bool:
    """Pantallas que pueden conservar su fondo de siempre: los paneles y el
    ingreso del portal (hoy es el de Clonexa para todas las empresas)."""
    return spec["family"] != "portal" or spec["page"] == "login"


def portal_piece_selectors() -> dict[str, str]:
    """Pieza -> selector, para marcarlas al vuelo en el portal (client.js)."""
    reg = registry()
    portal = {k for k, s in reg["screens"].items() if s["family"] == "portal"}
    return {p["key"]: p["selector"] for p in reg["pieces"] if p["screen"] in portal and p.get("selector")}


# --------------------------------------------------------------- validacion ---
def _obj(value: Any, path: str, allowed: set[str], required: tuple[str, ...] = ()) -> dict:
    if not isinstance(value, dict):
        raise BrandInvalid(path, "debe ser un objeto")
    extra = sorted(set(value) - allowed)
    if extra:
        raise BrandInvalid(f"{path}.{extra[0]}", "clave no permitida")
    for key in required:
        if key not in value:
            raise BrandInvalid(f"{path}.{key}", "falta")
    return value


def color(value: Any, path: str) -> str:
    text = value.strip().lower() if isinstance(value, str) else ""
    if _SHORT_HEX.match(text):
        text = "#" + "".join(c * 2 for c in text[1:])
    if not _HEX.match(text):
        raise BrandInvalid(path, "debe ser un color hex (#rrggbb)")
    return text


def number(value: Any, path: str, low: float, high: float, integer: bool = True) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        raise BrandInvalid(path, "debe ser un número")
    if value < low or value > high:
        raise BrandInvalid(path, f"fuera de rango ({low} a {high})")
    return int(round(value)) if integer else round(float(value), 2)


def choice(value: Any, path: str, options: tuple[str, ...]) -> str:
    if not isinstance(value, str) or value not in options:
        raise BrandInvalid(path, "opción no permitida")
    return value


def boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise BrandInvalid(path, "debe ser sí o no")
    return value


def image_id(value: Any, path: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise BrandInvalid(path, "imagen inválida") from None


def gradient(value: Any, path: str) -> dict:
    g = _obj(value, path, {"type", "angle", "stops"}, ("type", "stops"))
    stops = g["stops"]
    if not isinstance(stops, list) or not 2 <= len(stops) <= 3:
        raise BrandInvalid(f"{path}.stops", "debe tener 2 o 3 colores")
    clean = []
    for i, stop in enumerate(stops):
        s = _obj(stop, f"{path}.stops[{i}]", {"color", "at"}, ("color", "at"))
        clean.append({"color": color(s["color"], f"{path}.stops[{i}].color"), "at": number(s["at"], f"{path}.stops[{i}].at", 0, 100)})
    clean.sort(key=lambda s: s["at"])
    return {"type": choice(g["type"], f"{path}.type", ("linear", "radial")),
            "angle": number(g.get("angle", 180), f"{path}.angle", 0, 360), "stops": clean}


def fill(value: Any, path: str, allow_preset: bool = False) -> dict:
    f = _obj(value, path, {"kind", "color", "gradient"}, ("kind",))
    kind = choice(f["kind"], f"{path}.kind", ("solid", "gradient", "preset") if allow_preset else ("solid", "gradient"))
    if kind == "preset":
        return {"kind": "preset"}
    if kind == "solid":
        return {"kind": "solid", "color": color(f.get("color"), f"{path}.color")}
    return {"kind": "gradient", "gradient": gradient(f.get("gradient"), f"{path}.gradient")}


def background(value: Any, path: str, allow_inherit: bool, allow_own: bool = False) -> dict:
    b = _obj(value, path, {"inherit", "own", "base", "image", "veil"})
    if allow_inherit and b.get("inherit") is True:
        return {"inherit": True}
    if allow_own and b.get("own") is True:
        return {"own": True}
    if b.get("inherit") not in (False, None):
        raise BrandInvalid(f"{path}.inherit", "solo una pantalla puede heredar")
    if b.get("own") not in (False, None):
        raise BrandInvalid(f"{path}.own", "solo un panel conserva su fondo propio")
    out: dict[str, Any] = {"base": fill(b.get("base"), f"{path}.base", allow_preset=True), "image": None, "veil": None}
    if b.get("image") is not None:
        im = _obj(b["image"], f"{path}.image", {"id", "mode", "size", "position", "opacity"}, ("id", "mode"))
        out["image"] = {"id": image_id(im["id"], f"{path}.image.id"), "mode": choice(im["mode"], f"{path}.image.mode", IMAGE_MODES),
                        "size": number(im.get("size", 40), f"{path}.image.size", 5, 100),
                        "position": choice(im.get("position", "center"), f"{path}.image.position", POSITIONS),
                        "opacity": number(im.get("opacity", 100), f"{path}.image.opacity", 0, 100)}
    if b.get("veil") is not None:
        v = _obj(b["veil"], f"{path}.veil", {"gradient", "darken", "blur", "opacity"}, ("gradient",))
        out["veil"] = {"gradient": gradient(v["gradient"], f"{path}.veil.gradient"), "darken": number(v.get("darken", 0), f"{path}.veil.darken", 0, 90),
                       "blur": number(v.get("blur", 0), f"{path}.veil.blur", 0, 20), "opacity": number(v.get("opacity", 60), f"{path}.veil.opacity", 0, 100)}
    return out


_STATE_KEYS = {"fill", "border", "glow", "shadow", "text"}


def _style_props(s: dict, path: str) -> dict:
    out: dict[str, Any] = {}
    if "fill" in s:
        out["fill"] = fill(s["fill"], f"{path}.fill")
    if "border" in s:
        b = _obj(s["border"], f"{path}.border", {"width", "color"})
        out["border"] = {"width": number(b.get("width", 1), f"{path}.border.width", 0, 6),
                         **({"color": color(b["color"], f"{path}.border.color")} if "color" in b else {})}
    if "glow" in s:
        out["glow"] = number(s["glow"], f"{path}.glow", 0, 100)
    if "shadow" in s:
        out["shadow"] = number(s["shadow"], f"{path}.shadow", 0, 100)
    if "radius" in s:
        out["radius"] = number(s["radius"], f"{path}.radius", 0, 40)
    if "text" in s:
        t = _obj(s["text"], f"{path}.text", {"color", "weight", "size"})
        out["text"] = {**({"color": color(t["color"], f"{path}.text.color")} if "color" in t else {}),
                       **({"weight": number(t["weight"], f"{path}.text.weight", 100, 900) // 100 * 100} if "weight" in t else {}),
                       **({"size": number(t["size"], f"{path}.text.size", 10, 32)} if "size" in t else {})}
    return out


def style(value: Any, path: str) -> dict:
    s = _obj(value, path, {"fill", "border", "glow", "shadow", "radius", "text", "hover", "active"})
    out = _style_props(s, path)
    for state in ("hover", "active"):
        if state in s:
            st = _obj(s[state], f"{path}.{state}", _STATE_KEYS)
            out[state] = _style_props(st, f"{path}.{state}")
    return out


def _portal(value: Any) -> dict:
    p = _obj(value if value is not None else {}, "theme.portal", set(PORTAL_DEFAULT))
    return {
        "background_style": choice(p.get("background_style", PORTAL_DEFAULT["background_style"]), "theme.portal.background_style", portal_css.BACKGROUND_STYLES),
        "card_style": choice(p.get("card_style", PORTAL_DEFAULT["card_style"]), "theme.portal.card_style", portal_css.CARD_STYLES),
        "theme_mode": choice(p.get("theme_mode", PORTAL_DEFAULT["theme_mode"]), "theme.portal.theme_mode", portal_css.THEME_MODES),
        "gradient_from": color(p.get("gradient_from", PORTAL_DEFAULT["gradient_from"]), "theme.portal.gradient_from"),
        "gradient_to": color(p.get("gradient_to", PORTAL_DEFAULT["gradient_to"]), "theme.portal.gradient_to"),
        "gradient_extra": color(p.get("gradient_extra", PORTAL_DEFAULT["gradient_extra"]), "theme.portal.gradient_extra"),
        "gradient_angle": number(p.get("gradient_angle", PORTAL_DEFAULT["gradient_angle"]), "theme.portal.gradient_angle", 0, 360),
    }


def validate(tokens: Any) -> dict:
    """Tokens limpios o BrandInvalid con la ruta del primer error."""
    raw = json.dumps(tokens, ensure_ascii=False) if not isinstance(tokens, str) else tokens
    if len(raw.encode("utf-8")) > MAX_TOKENS_BYTES:
        raise BrandInvalid("tokens", "demasiado grande")
    t = _obj(tokens, "tokens", {"theme", "backgrounds", "components", "pieces"}, ("theme", "backgrounds"))
    th = _obj(t["theme"], "theme", {"colors", "font", "radius", "shadow", "glow", "logo", "panels", "portal"}, ("colors", "font"))
    colors = _obj(th["colors"], "theme.colors", set(COLOR_KEYS), COLOR_KEYS)
    font = _obj(th["font"], "theme.font", {"family", "size", "heading_weight"}, ("family",))
    theme = {
        "colors": {k: color(colors[k], f"theme.colors.{k}") for k in COLOR_KEYS},
        "font": {"family": choice(font["family"], "theme.font.family", FONTS),
                 "size": number(font["size"], "theme.font.size", 12, 22) if font.get("size") is not None else None,
                 "heading_weight": number(font["heading_weight"], "theme.font.heading_weight", 400, 900) // 100 * 100 if font.get("heading_weight") is not None else None},
        "radius": number(th.get("radius", 14), "theme.radius", 0, 32),
        "shadow": number(th.get("shadow", 30), "theme.shadow", 0, 100),
        "glow": number(th.get("glow", 0), "theme.glow", 0, 100),
        "logo": image_id(th["logo"], "theme.logo") if th.get("logo") else None,
        # Marcas creadas antes de la etapa 2 se aplicaban a los paneles: se respeta.
        "panels": boolean(th.get("panels", True), "theme.panels"),
        "portal": _portal(th.get("portal")),
    }
    reg = registry()
    bg = _obj(t["backgrounds"], "backgrounds", {"general", *reg["screens"]}, ("general",))
    backgrounds = {"general": background(bg["general"], "backgrounds.general", allow_inherit=False)}
    for screen, spec in reg["screens"].items():
        backgrounds[screen] = background(bg.get(screen, {"inherit": True}), f"backgrounds.{screen}", allow_inherit=True,
                                         allow_own=keeps_own_background(spec))
    comps = _obj(t.get("components", {}), "components", type_keys())
    pieces = _obj(t.get("pieces", {}), "pieces", piece_keys())
    return {"theme": theme, "backgrounds": backgrounds,
            "components": {k: style(v, f"components.{k}") for k, v in sorted(comps.items())},
            "pieces": {k: style(v, f"pieces.{k}") for k, v in sorted(pieces.items())}}


def image_ids(tokens: dict) -> set[str]:
    out = set()
    if tokens["theme"].get("logo"):
        out.add(tokens["theme"]["logo"])
    for bg in tokens["backgrounds"].values():
        if bg.get("image"):
            out.add(bg["image"]["id"])
    return out


def without_images(tokens: dict) -> dict:
    """Copia para otra empresa: nunca lleva imagenes de esta."""
    out = copy.deepcopy(tokens)
    out["theme"]["logo"] = None
    for bg in out["backgrounds"].values():
        if "image" in bg:
            bg["image"] = None
    return out


# ------------------------------------------------------------------ colores ---
def _rgb(hex_color: str) -> tuple[int, int, int]:
    return int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def mix(a: str, b: str, t: float) -> str:
    x, y = _rgb(a), _rgb(b)
    return _hex(tuple(x[i] + (y[i] - x[i]) * t for i in range(3)))


def luminance(hex_color: str) -> float:
    def ch(c: int) -> float:
        v = c / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(hex_color)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def on_color(bg: str) -> str:
    return "#ffffff" if contrast("#ffffff", bg) >= contrast("#111111", bg) else "#111111"


# ---------------------------------------------------------- tokens base ---
def _solid(c: str) -> dict:
    return {"kind": "solid", "color": c}


def _grad(a: str, b: str, angle: int = 135, kind: str = "linear", c: Optional[str] = None) -> dict:
    stops = [{"color": a, "at": 0}, {"color": b, "at": 100}] if not c else [{"color": a, "at": 0}, {"color": b, "at": 55}, {"color": c, "at": 100}]
    return {"kind": "gradient", "gradient": {"type": kind, "angle": angle, "stops": stops}}


def make_tokens(colors: dict, *, font: str = "Inter", radius: int = 14, shadow: int = 30, glow: int = 0, base: Optional[dict] = None,
                logo: Optional[str] = None, components: Optional[dict] = None, panels: bool = True, portal: Optional[dict] = None,
                screens_own: bool = False, font_size: Optional[int] = 15, heading_weight: Optional[int] = 700) -> dict:
    reg = registry()
    screens = {k: ({"own": True} if screens_own and keeps_own_background(s) else {"inherit": True}) for k, s in reg["screens"].items()}
    return validate({
        "theme": {"colors": colors, "font": {"family": font, "size": font_size, "heading_weight": heading_weight}, "radius": radius,
                  "shadow": shadow, "glow": glow, "logo": logo, "panels": panels, "portal": portal or {}},
        "backgrounds": {"general": {"base": base or _solid(colors["background"]), "image": None, "veil": None}, **screens},
        "components": components or {}, "pieces": {},
    })


def palette(primary: str, secondary: str, background: str, text: Optional[str] = None) -> dict:
    text = text or on_color(background)
    return {"primary": primary, "secondary": secondary, "background": background, "surface": mix(background, text, 0.06),
            "text": text, "text_muted": mix(text, background, 0.4), "success": "#22c55e", "warning": "#f59e0b", "danger": "#ef4444"}


CLONEXA_DEFAULT = palette("#f72585", "#7209b7", "#080712", "#f5f3ff")


def templates() -> list[dict]:
    """Plantillas de arranque (reemplazan el borrador, previa confirmacion)."""
    fut = palette("#00e5ff", "#a855f7", "#05060f", "#e6fbff")
    cla = palette("#8b1e2d", "#c9a227", "#f7f1e8", "#2b1d16")
    mini = palette("#111827", "#6b7280", "#ffffff", "#111827")
    osc = palette("#e3122f", "#9d17ff", "#0b0507", "#f4eef0")
    return [
        {"key": "futurista", "label": "Futurista", "tokens": make_tokens(fut, font="Orbitron", radius=10, shadow=40, glow=60,
            base=_grad("#05060f", "#0b1640", 160, c="#1a0633"), portal={"card_style": "neon_border", "theme_mode": "dark"},
            components={"boton_principal": {"fill": _grad("#00e5ff", "#a855f7", 120), "glow": 60, "radius": 10, "text": {"color": "#05060f", "weight": 800},
                                             "hover": {"glow": 90}, "active": {"glow": 30}},
                        "tarjeta": {"border": {"width": 1, "color": "#1e3a8a"}, "glow": 25, "radius": 10}})},
        {"key": "clasico", "label": "Clásico", "tokens": make_tokens(cla, font="Montserrat", radius=8, shadow=25,
            portal={"card_style": "classic_panel", "theme_mode": "classic"},
            components={"boton_principal": {"fill": _solid("#8b1e2d"), "radius": 8, "text": {"color": "#ffffff", "weight": 700}, "hover": {"fill": _solid("#6f1824")}},
                        "tarjeta": {"border": {"width": 1, "color": "#e2d3bd"}, "radius": 8}})},
        {"key": "minimal", "label": "Minimal", "tokens": make_tokens(mini, font="Inter", radius=6, shadow=10,
            portal={"card_style": "flat_dashboard", "theme_mode": "light"},
            components={"boton_principal": {"fill": _solid("#111827"), "radius": 6, "text": {"color": "#ffffff", "weight": 600}},
                        "tarjeta": {"border": {"width": 1, "color": "#e5e7eb"}, "shadow": 5, "radius": 6}})},
        {"key": "oscuro", "label": "Oscuro", "tokens": make_tokens(osc, font="Manrope", radius=16, shadow=45, glow=35,
            base=_grad("#0b0507", "#1a070c", 180, kind="radial"), portal={"card_style": "dark_elevated", "theme_mode": "dark"},
            components={"boton_principal": {"fill": _grad("#e3122f", "#9d17ff", 135), "glow": 40, "radius": 16, "text": {"color": "#ffffff", "weight": 700}}})},
    ]


def _valid_hex(value: Any, fallback: str) -> str:
    """validHex() de client.js (acepta #rgb y #rrggbb) y luego al formato de los tokens."""
    text = str(value or "").strip()
    picked = text if re.match(r"^#[0-9a-fA-F]{3}$", text) or re.match(r"^#[0-9a-fA-F]{6}$", text) else fallback
    return color(picked, "color")


_PRESET_STYLE = {"clonexa_dark": "aurora_boreal", "field_ops_dark": "cyber_grid", "voltage_field": "cyber_grid", "retail_neon": "holografico",
                 "hospitality_gold": "neon_profundo", "production_neon": "cyber_grid", "boardroom_dark": "corporate_dark",
                 "executive_light": "corporate_light", "classic_office": "classic_dashboard", "neutral_slate": "neutral_slate",
                 "minimal_light": "corporate_light", "custom": "aurora_boreal"}


def normalize_branding(raw: dict) -> dict:
    """Port de normalizeBranding() de client.js: lo que el portal ve hoy."""
    raw = raw if isinstance(raw, dict) else {}
    preset = str(raw.get("visual_preset") or raw.get("preset_visual") or raw.get("preset") or "custom").strip()
    style = str(raw.get("background_style") or "").strip()
    font = str(raw.get("font_family") or "").strip()
    card = str(raw.get("card_style") or "").strip()
    mode = str(raw.get("theme_mode") or raw.get("mode") or "").strip()
    try:
        angle = float(raw.get("gradient_angle") or 135) or 135
    except (TypeError, ValueError):
        angle = 135
    return {
        "primary_color": _valid_hex(raw.get("primary_color") or raw.get("color_principal"), "#ff2bd6"),
        "secondary_color": _valid_hex(raw.get("secondary_color") or raw.get("color_secundario"), "#00ff88"),
        "background_color": _valid_hex(raw.get("background_color") or raw.get("color_fondo"), "#050509"),
        "text_color": _valid_hex(raw.get("text_color") or raw.get("color_texto"), "#f8fafc"),
        "background_style": style if style in portal_css.BACKGROUND_STYLES else _PRESET_STYLE.get(preset, "aurora_boreal"),
        "font_family": font if font in PORTAL_FONTS else "Inter",
        "card_style": card if card in portal_css.CARD_STYLES else "glass_premium",
        "theme_mode": mode if mode in portal_css.THEME_MODES else "dark",
        "gradient_from": _valid_hex(raw.get("gradient_from") or raw.get("primary_color"), "#ff2bd6"),
        "gradient_to": _valid_hex(raw.get("gradient_to") or raw.get("secondary_color"), "#00ff88"),
        "gradient_extra": _valid_hex(raw.get("gradient_extra") or raw.get("background_color"), "#050509"),
        "gradient_angle": max(0, min(360, int(round(angle)))),
    }


def from_branding(branding: dict, logo_id: Optional[str] = None, panels: bool = False) -> dict:
    """Borrador inicial que reproduce el aspecto actual: los mismos valores que
    normalizeBranding() de client.js (colores, estilo de fondo, tarjetas, modo
    y tipografia). El fondo general es el estilo de fondo del portal (preset);
    los paneles conservan su fondo propio y solo reciben la marca si hoy la
    reciben (panels: interruptores mini_panel_brand / brand_everywhere)."""
    b = normalize_branding(branding)
    colors = palette(b["primary_color"], b["secondary_color"], b["background_color"], b["text_color"])
    portal = {k: b[k] for k in PORTAL_DEFAULT}
    return make_tokens(colors, font=b["font_family"], base={"kind": "preset"}, logo=logo_id, panels=panels, portal=portal,
                       screens_own=True, font_size=None, heading_weight=None)


def portal_values(tokens: dict) -> dict:
    """Los valores normalizados (forma de normalizeBranding) que salen de los tokens."""
    c, p = tokens["theme"]["colors"], tokens["theme"]["portal"]
    family = tokens["theme"]["font"]["family"]
    return {"primary_color": c["primary"], "secondary_color": c["secondary"], "background_color": c["background"], "text_color": c["text"],
            "font_family": family if family in PORTAL_FONTS else "Inter", **p}


def branding_for_panels(tokens: dict, company_id: str) -> dict:
    """Lo que hsp_brand.js ya sabe aplicar (traduce la hoja oscura a la marca)."""
    c = tokens["theme"]["colors"]
    p = tokens["theme"]["portal"]
    family = tokens["theme"]["font"]["family"]
    out = {"primary_color": c["primary"], "secondary_color": c["secondary"], "background_color": c["background"],
           "text_color": c["text"], "theme_mode": "light" if luminance(c["background"]) > 0.4 else "dark",
           # hsp_brand.js arma el fondo claro con estos dos (los mismos de company_branding).
           "gradient_from": p["gradient_from"], "gradient_to": p["gradient_to"], "gradient_angle": p["gradient_angle"]}
    if family != "Sistema":
        out["font_family"] = family
    if tokens["theme"].get("logo"):
        out["logo_url"] = f"/brand-media/{company_id}/{tokens['theme']['logo']}.webp"
    return out


def branding_for_portal(tokens: dict, company_id: str) -> dict:
    """Lo que client.js usa de state.branding (logo y valores) con marca publicada."""
    out = dict(portal_values(tokens))
    out["mode"] = out["theme_mode"]
    out["logo_url"] = f"/brand-media/{company_id}/{tokens['theme']['logo']}.webp" if tokens["theme"].get("logo") else ""
    return out


# ------------------------------------------------- paleta desde el logo ---
def palette_from_image(raw: bytes) -> dict:
    """Propone la paleta completa desde los colores del logo."""
    from PIL import Image

    image = Image.open(io.BytesIO(raw)).convert("RGBA")
    image.thumbnail((160, 160))
    pixels = [(r, g, b) for r, g, b, a in image.getdata() if a > 128]
    if not pixels:
        return dict(CLONEXA_DEFAULT)
    small = Image.new("RGB", (len(pixels), 1))
    small.putdata(pixels)
    quant = small.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
    pal = quant.getpalette()[: 8 * 3]
    counts = sorted(quant.getcolors() or [], reverse=True)
    found = []
    for count, idx in counts:
        rgb = tuple(pal[idx * 3: idx * 3 + 3])
        h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
        found.append({"hex": _hex(rgb), "count": count, "h": h, "l": l, "s": s})
    vivid = [f for f in found if f["s"] > 0.25 and 0.15 < f["l"] < 0.85] or found
    primary = max(vivid, key=lambda f: f["count"] * (0.5 + f["s"]))
    others = [f for f in vivid if f is not primary and min(abs(f["h"] - primary["h"]), 1 - abs(f["h"] - primary["h"])) > 0.08]
    secondary = others[0]["hex"] if others else mix(primary["hex"], "#ffffff", 0.35)
    mean_l = sum(f["l"] * f["count"] for f in found) / max(1, sum(f["count"] for f in found))
    background = mix(primary["hex"], "#000000", 0.9) if mean_l < 0.7 else mix(primary["hex"], "#ffffff", 0.94)
    return palette(primary["hex"], secondary, background)


# --------------------------------------------------------------- generador ---
def _num(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:.2f}".rstrip("0").rstrip(".")


def _rgba(hex_color: str, alpha: float) -> str:
    r, g, b = _rgb(color(hex_color, "c"))
    return f"rgba({r},{g},{b},{_num(round(max(0.0, min(1.0, alpha)), 3))})"


def _gradient_css(g: dict) -> str:
    stops = ",".join(f"{color(s['color'], 'c')} {_num(s['at'])}%" for s in g["stops"])
    if g["type"] == "radial":
        return f"radial-gradient(circle at center,{stops})"
    return f"linear-gradient({_num(g['angle'])}deg,{stops})"


def _fill_css(f: dict, tokens: Optional[dict] = None) -> str:
    if f["kind"] == "preset":
        return " ".join(portal_css.branding_background(portal_values(tokens)).split())
    return color(f["color"], "c") if f["kind"] == "solid" else _gradient_css(f["gradient"])


def _media_url(company_id: str, image: str, lite: bool) -> str:
    return f'url("/brand-media/{image_id(company_id, "c")}/{image_id(image, "i")}{"-lite" if lite else ""}.webp")'


def _shadow_css(shadow: Optional[float], glow: Optional[float], glow_color: str) -> Optional[str]:
    parts = []
    if shadow:
        parts.append(f"0 {_num(round(shadow * 0.12, 1))}px {_num(round(shadow * 0.4, 1))}px {_rgba('#000000', 0.15 + shadow * 0.004)}")
    if glow:
        parts.append(f"0 0 {_num(round(glow * 0.3, 1))}px {_rgba(glow_color, 0.25 + glow * 0.006)}")
    if shadow == 0 and glow == 0:
        return "none"
    return ",".join(parts) if parts else None


def _props_css(p: dict, primary: str, lite: bool = False) -> str:
    out = []
    if "fill" in p:
        out.append(f"background:{_fill_css(p['fill'])}")
    if "border" in p:
        b = p["border"]
        out.append(f"border:{_num(b['width'])}px solid {color(b.get('color', primary), 'c')}" if b["width"] else "border:0")
    if "radius" in p:
        out.append(f"border-radius:{_num(p['radius'])}px")
    glow_color = (p.get("border") or {}).get("color") or primary
    shadow = _shadow_css(p.get("shadow"), None if lite else p.get("glow"), glow_color) if ("shadow" in p or "glow" in p) else None
    if shadow:
        out.append(f"box-shadow:{shadow}")
    if "text" in p:
        t = p["text"]
        if "color" in t:
            out.append(f"color:{color(t['color'], 'c')}")
        if "weight" in t:
            out.append(f"font-weight:{_num(t['weight'])}")
        if "size" in t:
            out.append(f"font-size:{_num(t['size'])}px")
    return ";".join(out)


def _family_of(selector: str) -> str:
    m = re.match(r"^\.([a-z0-9]+)-", selector)
    return m.group(1) if m else ""


def _root(scope: str, prefix: str = "html body") -> str:
    """Selector raiz de una pantalla; un scope que empieza en body cuelga de html."""
    if scope.startswith("body"):
        return f"{prefix.rsplit(' body', 1)[0]} {scope}"
    return f"{prefix} {scope}"


def _join(screen_specs: list[dict], selectors: list[str], suffix: str = "") -> str:
    out = []
    for spec in screen_specs:
        for scope in spec["scope"]:
            for sel in selectors:
                for part in sel.split(","):
                    part = part.strip()
                    fam = _family_of(part)
                    if fam and fam not in spec["prefixes"]:
                        continue
                    out.append(f"{_root(scope)} {part}{suffix}")
    return ",".join(dict.fromkeys(out))


def _background_css(scopes: list[str], bg: dict, company_id: str, tokens: dict, page_bg: bool = True) -> list[str]:
    rules = []
    sel = ",".join(_root(s) for s in scopes)
    rules.append(f"{sel}{{background:{_fill_css(bg['base'], tokens)};position:relative;isolation:isolate}}")
    page = ",".join(f"html body:has({s})" for s in scopes if not s.startswith("body"))
    if page and page_bg:
        rules.append(f"{page}{{background:{_fill_css(bg['base'], tokens)}}}")
    rules += _layers_css([_root(s) for s in scopes], [_root(s, "html.cx-lite body") for s in scopes], bg, company_id)
    return rules


def _layers_css(targets: list[str], lite_targets: list[str], bg: dict, company_id: str) -> list[str]:
    """Imagen (::before) y velo (::after) de un fondo, con su version liviana."""
    rules = []
    im = bg.get("image")
    if im:
        if im["mode"] == "cover":
            size, repeat = "cover", "no-repeat"
        elif im["mode"] == "watermark":
            size, repeat = f"{_num(im['size'])}% auto", "no-repeat"
        else:
            size, repeat = f"{_num(im['size'] * 4)}px auto", "repeat"
        layer = "pointer-events:none;content:\"\";position:fixed;inset:0;z-index:-1"
        for lite, group in ((False, targets), (True, lite_targets)):
            before = ",".join(f"{t}::before" for t in group)
            rules.append(f"{before}{{{layer};background:{_media_url(company_id, im['id'], lite)} {im['position']}/{size} {repeat};opacity:{_num(im['opacity'] / 100)}}}")
    v = bg.get("veil")
    if v:
        after = ",".join(f"{t}::after" for t in targets)
        filters = []
        if v["blur"]:
            filters.append(f"blur({_num(v['blur'])}px)")
        if v["darken"]:
            filters.append(f"brightness({_num(round(1 - v['darken'] / 100, 2))})")
        backdrop = f";backdrop-filter:{' '.join(filters)};-webkit-backdrop-filter:{' '.join(filters)}" if filters else ""
        rules.append(f"{after}{{pointer-events:none;content:\"\";position:fixed;inset:0;z-index:-1;background:{_gradient_css(v['gradient'])};opacity:{_num(v['opacity'] / 100)}{backdrop}}}")
        lite_after = ",".join(f"{t}::after" for t in lite_targets)
        rules.append(f"{lite_after}{{backdrop-filter:none;-webkit-backdrop-filter:none}}")
    return rules


_FORBIDDEN = re.compile(r"[<>\\]|javascript|expression\s*\(|@import|behavior\s*:|-moz-binding", re.IGNORECASE)
_URL = re.compile(r"url\(")
_ALLOWED_URL = re.compile(r'url\("/brand-media/[0-9a-f-]{36}/[0-9a-f-]{36}(-lite)?\.webp"\)')


def applies_to(tokens: dict, page: str) -> bool:
    """La marca publicada solo toca restaurante y mini paneles si theme.panels."""
    return page in ("portal", "login") or bool(tokens["theme"].get("panels"))


def css_for(tokens: dict, company_id: str, states: bool = False, page: Optional[str] = None) -> str:
    """CSS de la marca, armado solo con valores validados. Siempre revalida.
    page: "portal" | "login" | "panels" | "mini" (None = todas: vista previa).
    states=True (solo la vista previa): los estados cursor encima y presionado
    tambien se ven en elementos marcados con data-cx-state."""
    t = validate(tokens)
    if page is not None and page not in PAGES:
        raise BrandInvalid("page", "pagina desconocida")
    reg = registry()
    c = t["theme"]["colors"]
    primary = c["primary"]
    pages = [page] if page else list(PAGES)
    screens = {k: s for k, s in reg["screens"].items() if s["page"] in pages}
    rules = [":root{" + ";".join(f"--cxb-{k.replace('_', '-')}:{v}" for k, v in c.items())
             + f";--cxb-radius:{_num(t['theme']['radius'])}px}}"]
    general = t["backgrounds"]["general"]
    # Portal: la hoja base del portal (la misma de applyBranding) con estos valores.
    if "portal" in pages:
        body_bg = None if general["base"]["kind"] == "preset" else _fill_css(general["base"], t)
        rules.append(" ".join(portal_css.render(portal_values(t), body_bg).split()))
        rules += _layers_css(["html body"], ["html.cx-lite body"], general, company_id)
    family = t["theme"]["font"]["family"]
    font_stack = "system-ui,-apple-system,Segoe UI,Roboto,sans-serif" if family == "Sistema" else f"'{family}',system-ui,sans-serif"
    # El ingreso del portal con su aspecto de siempre tampoco cambia de letra.
    other = [s for k, s in screens.items() if s["page"] != "portal" and not (s["page"] == "login" and t["backgrounds"][k].get("own"))]
    if other:
        scope_sel = ",".join(_root(sc) for s in other for sc in s["scope"])
        size = t["theme"]["font"]["size"]
        rules.append(f"{scope_sel}{{font-family:{font_stack}" + (f";font-size:{_num(size)}px" if size else "") + "}")
    weight = t["theme"]["font"]["heading_weight"]
    if weight:
        heads = ",".join(f"{_root(sc)} {hd}" for s in screens.values() for sc in s["scope"] for hd in ("h1", "h2", "h3"))
        rules.append(f"{heads}{{font-weight:{_num(weight)}}}")
    # Fondos por pantalla: heredar (general), propio del panel (nada) o personalizado.
    for key, spec in screens.items():
        bg = t["backgrounds"][key]
        if bg.get("own"):
            continue
        if bg.get("inherit"):
            if spec["page"] == "portal":
                continue  # el portal ya lleva el fondo general en su hoja base
            bg = general
        rules += _background_css(spec["scope"], bg, company_id, t, page_bg=spec["page"] != "portal")
    # Componentes por tipo y luego piezas con nombre.
    specs = list(screens.values())
    for kind, spec in reg["types"].items():
        st = t["components"].get(kind)
        if not st:
            continue
        sel = _join(specs, spec["selectors"])
        _emit_style(rules, sel, lambda suffix, spec=spec: _join(specs, spec["selectors"], suffix), st, primary, states)
    for piece in reg["pieces"]:
        st = t["pieces"].get(piece["key"])
        if not st or piece["screen"] not in screens:
            continue
        scopes = reg["screens"][piece["screen"]]["scope"]
        # En el portal las piezas del panel principal estan en todas sus vistas.
        if reg["screens"][piece["screen"]]["page"] == "portal":
            scopes = [sc for s in screens.values() if s["page"] == "portal" for sc in s["scope"]]
        attr = f'[data-brand="{piece["key"]}"][data-brand="{piece["key"]}"]'
        sel = ",".join(f"{_root(s)} {attr}" for s in scopes)
        _emit_style(rules, sel, lambda suffix, scopes=scopes, attr=attr: ",".join(f"{_root(s)} {attr}{suffix}" for s in scopes), st, primary, states)
    css = "\n".join(r for r in rules if r)
    if _FORBIDDEN.search(css) or len(_URL.findall(css)) != len(_ALLOWED_URL.findall(css)):
        raise BrandInvalid("css", "salida no permitida")
    return css


def _emit_style(rules: list[str], sel: str, with_suffix, st: dict, primary: str, states: bool = False) -> None:
    if not sel:
        return
    body = _props_css(st, primary)
    if body:
        rules.append(f"{sel}{{{body}}}")
        if st.get("glow"):
            lite = ",".join(f"html.cx-lite{part[4:]}" for part in sel.split(",") if part.startswith("html "))
            if lite:
                rules.append(f"{lite}{{{_props_css({k: v for k, v in st.items() if k in ('shadow', 'glow')}, primary, lite=True) or 'box-shadow:none'}}}")
    for state, pseudo in (("hover", ":hover"), ("active", ":active")):
        if st.get(state):
            body = _props_css(st[state], primary)
            if body:
                target = with_suffix(pseudo) + ("," + with_suffix(f'[data-cx-state="{state}"]') if states else "")
                rules.append(f"{target}{{{body}}}")
