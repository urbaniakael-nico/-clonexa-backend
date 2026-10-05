"""Fase 4 · Parte 2: tokens de marca, generador, versiones y API.

- La validacion rechaza colores no hex, angulos fuera de rango, fuentes fuera
  de la lista, claves desconocidas e intentos de inyectar </style>,
  url(javascript:...) o expression(.
- El generador solo emite valores validados; cada plantilla sale limpia.
- Un borrador no cambia lo publicado; publicar si; volver de version restaura.
- Una empresa nunca recibe tokens ni imagenes de otra.
- Todos los endpoints exigen sesion de Admin V2; publicar pide el nombre.
"""
from __future__ import annotations

import copy
import json
import re
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.deps import get_db
from app.services import brand_media as media
from app.services import brand_store as store
from app.services import brand_theme as bt
from app.web import admin_v2plus_companies as ep

A, B = str(uuid.uuid4()), str(uuid.uuid4())


def base_tokens() -> dict:
    return copy.deepcopy(bt.templates()[0]["tokens"])


# ------------------------------------------------------------ validacion
@pytest.mark.parametrize("mutate,field", [
    (lambda t: t["theme"]["colors"].__setitem__("primary", "red"), "theme.colors.primary"),
    (lambda t: t["theme"]["colors"].__setitem__("text", "#12345g"), "theme.colors.text"),
    (lambda t: t["theme"]["colors"].__setitem__("primary", "#fff</style><script>alert(1)</script>"), "theme.colors.primary"),
    (lambda t: t["theme"]["font"].__setitem__("family", "Comic Sans"), "theme.font.family"),
    (lambda t: t["theme"]["font"].__setitem__("family", "Inter;}</style>"), "theme.font.family"),
    (lambda t: t["theme"]["font"].__setitem__("size", 99), "theme.font.size"),
    (lambda t: t["theme"].__setitem__("radius", True), "theme.radius"),
    (lambda t: t["backgrounds"]["general"].__setitem__("base", {"kind": "gradient", "gradient": {"type": "linear", "angle": 400, "stops": [{"color": "#000000", "at": 0}, {"color": "#ffffff", "at": 100}]}}), "backgrounds.general.base.gradient.angle"),
    (lambda t: t["backgrounds"]["general"].__setitem__("base", {"kind": "gradient", "gradient": {"type": "conic", "stops": [{"color": "#000000", "at": 0}, {"color": "#ffffff", "at": 100}]}}), "backgrounds.general.base.gradient.type"),
    (lambda t: t["backgrounds"]["general"].__setitem__("base", {"kind": "gradient", "gradient": {"type": "linear", "stops": [{"color": "#000000", "at": 0}]}}), "backgrounds.general.base.gradient.stops"),
    (lambda t: t["backgrounds"]["general"].__setitem__("image", {"id": "url(javascript:alert(1))", "mode": "cover"}), "backgrounds.general.image.id"),
    (lambda t: t["backgrounds"]["general"].__setitem__("image", {"id": str(uuid.uuid4()), "mode": "expression(alert(1))"}), "backgrounds.general.image.mode"),
    (lambda t: t["backgrounds"]["general"].__setitem__("image", {"id": str(uuid.uuid4()), "mode": "cover", "position": "center;background:url(javascript:x)"}), "backgrounds.general.image.position"),
    (lambda t: t["backgrounds"]["general"].__setitem__("inherit", True), "backgrounds.general.inherit"),
    (lambda t: t.__setitem__("css", "body{}"), "tokens.css"),
    (lambda t: t["components"].__setitem__("boton_principal", {"style": "color:red"}), "components.boton_principal.style"),
    (lambda t: t["components"].__setitem__("mi_tipo", {}), "components.mi_tipo"),
    (lambda t: t["pieces"].__setitem__("caja.borrar_todo", {}), "pieces.caja.borrar_todo"),
    (lambda t: t["pieces"].__setitem__("caja.cobrar", {"text": {"color": "expression(alert(1))"}}), "pieces.caja.cobrar.text.color"),
    (lambda t: t["pieces"].__setitem__("caja.cobrar", {"hover": {"radius": 3}}), "pieces.caja.cobrar.hover.radius"),
])
def test_validation_rejects_bad_values_and_injections(mutate, field):
    tokens = base_tokens()
    mutate(tokens)
    with pytest.raises(bt.BrandInvalid) as info:
        bt.validate(tokens)
    assert info.value.path == field


def test_validation_normalizes():
    t = base_tokens()
    t["theme"]["colors"]["primary"] = "#ABC"
    t["theme"]["font"]["heading_weight"] = 750
    out = bt.validate(t)
    assert out["theme"]["colors"]["primary"] == "#aabbcc"
    assert out["theme"]["font"]["heading_weight"] == 700
    assert out["backgrounds"]["caja"] == {"inherit": True}


def test_generator_only_emits_safe_css_for_every_template():
    img = str(uuid.uuid4())
    for tpl in bt.templates():
        t = copy.deepcopy(tpl["tokens"])
        t["backgrounds"]["mesero"] = {"base": {"kind": "solid", "color": "#101010"},
                                     "image": {"id": img, "mode": "pattern", "size": 20, "position": "top left", "opacity": 30},
                                     "veil": {"gradient": {"type": "radial", "angle": 0, "stops": [{"color": "#000000", "at": 0}, {"color": "#222222", "at": 100}]}, "darken": 40, "blur": 8, "opacity": 70}}
        t["pieces"]["mesero.enviar_pedido"] = {"fill": {"kind": "solid", "color": "#00ff00"}, "glow": 40, "hover": {"glow": 80}, "active": {"shadow": 10}}
        css = bt.css_for(t, A)
        assert "<" not in css and ">" not in css and "javascript" not in css.lower() and "expression" not in css.lower() and "@import" not in css
        urls = re.findall(r'url\("([^"]+)"\)', css)
        assert urls and all(u.startswith(f"/brand-media/{A}/") for u in urls), "solo imagenes de ESTA empresa y del mismo origen"
        assert f"/brand-media/{A}/{img}-lite.webp" in css, "version liviana para equipos lentos"
        assert "html.cx-lite body .wtr-shell::after{backdrop-filter:none" in css, "modo liviano apaga el desenfoque"
        assert '[data-brand="mesero.enviar_pedido"]' in css and ":hover" in css and ":active" in css


def test_generator_revalidates_even_if_tokens_were_tampered():
    t = base_tokens()
    t["theme"]["colors"]["primary"] = "#000;}</style>"
    with pytest.raises(bt.BrandInvalid):
        bt.css_for(t, A)


def test_without_images_drops_all_images():
    t = base_tokens()
    img = str(uuid.uuid4())
    t["theme"]["logo"] = img
    t["backgrounds"]["general"]["image"] = {"id": img, "mode": "cover"}
    clean = bt.without_images(bt.validate(t))
    assert bt.image_ids(clean) == set()


def test_registry_pieces_are_tagged_in_the_panels():
    """Restaurante: data-brand en el HTML que arman sus JS. Portal: selector para
    el marcado al vuelo de client.js. Mini paneles: data-brand en mini_panel.js."""
    src = "".join(open(f"app/web/{f}.js", encoding="utf-8").read() for f in ("hsp_cashier", "hsp_waiter", "hsp_kitchen", "mini_panel"))
    reg = bt.registry()
    for piece in reg["pieces"]:
        family = reg["screens"][piece["screen"]]["family"]
        if family == "portal":
            assert piece.get("selector"), piece["key"]
        else:
            assert f'data-brand="{piece["key"]}"' in src, piece["key"]


def test_initial_tokens_from_company_branding():
    out = bt.from_branding({"primary_color": "#123456", "background_color": "#ffffff", "font_family": "Sora",
                            "gradient_from": "#111111", "gradient_to": "#222222", "gradient_angle": 90, "logo_url": "javascript:x"}, None)
    assert out["theme"]["colors"]["primary"] == "#123456" and out["theme"]["font"]["family"] == "Sora"
    assert out["theme"]["portal"]["gradient_angle"] == 90 and out["theme"]["portal"]["gradient_from"] == "#111111"
    assert out["backgrounds"]["general"]["base"] == {"kind": "preset"}
    assert out["theme"]["logo"] is None
    junk = bt.from_branding({"primary_color": "red", "font_family": "Comic Sans"})
    assert junk["theme"]["colors"]["primary"] == "#ff2bd6" and junk["theme"]["font"]["family"] == "Inter"


def test_palette_from_logo_proposes_full_palette():
    import io

    from PIL import Image

    img = Image.new("RGB", (100, 100), "#ffffff")
    for x in range(100):
        for y in range(60):
            img.putpixel((x, y), (220, 30, 60))
        for y in range(60, 100):
            img.putpixel((x, y), (20, 90, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    pal = bt.palette_from_image(buf.getvalue())
    assert set(pal) == set(bt.COLOR_KEYS)
    r, g, b = int(pal["primary"][1:3], 16), int(pal["primary"][3:5], 16), int(pal["primary"][5:7], 16)
    assert r > 150 and g < 90, "el rojo dominante es el primario"
    assert bt.contrast(pal["text"], pal["background"]) >= 4.5


# ------------------------------------------------------------ versiones
class ThemesDb:
    """Interpreta las consultas de brand_store sobre listas en memoria."""

    def __init__(self):
        self.themes: list[dict] = []
        self.images: list[dict] = []

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        p = params or {}
        mine = [t for t in self.themes if t["company_id"] == p.get("c")]
        now = datetime.now(timezone.utc)
        if sql.startswith("SELECT version, status, tokens, created_at, published_at"):
            return R(sorted(mine, key=lambda t: -t["version"]))
        if sql.startswith("SELECT COALESCE(MAX(version), 0) + 1"):
            return R(scalar=max([t["version"] for t in mine], default=0) + 1)
        if sql.startswith("INSERT INTO company_brand_themes"):
            self.themes.append({"company_id": p["c"], "version": p["v"], "status": p["s"], "tokens": json.loads(p["t"]), "created_at": now,
                                "published_at": now if p["s"] == "published" else None})
            return R()
        if sql.startswith("UPDATE company_brand_themes SET tokens"):
            hit = [t for t in mine if t["status"] == "draft"]
            for t in hit:
                t["tokens"] = json.loads(p["t"])
            return R(rowcount=len(hit))
        if sql.startswith("UPDATE company_brand_themes SET status = 'archived'"):
            for t in mine:
                if t["status"] == "published":
                    t["status"] = "archived"
            return R()
        if sql.startswith("UPDATE company_brand_themes SET status = 'published'"):
            for t in mine:
                if t["version"] == p["v"]:
                    t["status"], t["published_at"] = "published", now
            return R()
        if sql.startswith("DELETE FROM company_brand_themes"):
            keep = {t["version"] for t in sorted(mine, key=lambda t: -t["version"])[: p["keep"]]}
            self.themes = [t for t in self.themes if not (t["company_id"] == p["c"] and t["status"] == "archived" and t["version"] not in keep)]
            return R()
        if sql.startswith("SELECT version, tokens FROM company_brand_themes"):
            return R([t for t in mine if t["status"] == "draft"])
        if sql.startswith("SELECT version, status, tokens FROM company_brand_themes"):
            return R([t for t in mine if t["version"] == p["v"]])
        if sql.startswith("SELECT tokens FROM company_brand_themes WHERE company_id = CAST(:c AS uuid) AND status = 'published'"):
            return R([t for t in mine if t["status"] == "published"])
        if sql.startswith("SELECT tokens FROM company_brand_themes WHERE company_id = CAST(:c AS uuid) AND status IN"):
            return R(sorted([t for t in mine if t["status"] in ("published", "draft")], key=lambda t: t["status"] != "published"))
        if sql.startswith("SELECT id::text FROM company_brand_images"):
            return R([(i["id"],) for i in self.images if i["company_id"] == p["c"] and i["id"] in p["ids"]])
        raise AssertionError(sql)

    async def commit(self):
        pass

    async def rollback(self):
        pass


class R:
    def __init__(self, rows=None, scalar=None, rowcount=0):
        self.rows, self._scalar, self.rowcount = rows or [], scalar, rowcount

    def mappings(self):
        return SimpleNamespace(all=lambda: self.rows, first=lambda: self.rows[0] if self.rows else None)

    def all(self):
        return self.rows

    def scalar(self):
        return self._scalar


@pytest.mark.asyncio
async def test_draft_does_not_change_published_publish_does_and_rollback_restores():
    db = ThemesDb()
    first = await store.state(db, A, {"primary_color": "#111111"})
    assert first["published"] is None and first["draft"]["tokens"]["theme"]["colors"]["primary"] == "#111111"
    assert await store.published_tokens(db, A) is None, "sin publicar: se ve igual que hoy"

    t1 = base_tokens()
    await store.save_draft(db, A, t1)
    assert await store.published_tokens(db, A) is None, "guardar el borrador no publica"
    v1 = await store.publish(db, A)
    assert (await store.published_tokens(db, A))["theme"]["colors"]["primary"] == t1["theme"]["colors"]["primary"]

    s = await store.state(db, A, {})
    t2 = copy.deepcopy(s["draft"]["tokens"])
    t2["theme"]["colors"]["primary"] = "#00ff00"
    await store.save_draft(db, A, t2)
    assert (await store.published_tokens(db, A))["theme"]["colors"]["primary"] != "#00ff00", "editar no toca a los operarios"
    await store.publish(db, A)
    assert (await store.published_tokens(db, A))["theme"]["colors"]["primary"] == "#00ff00"

    await store.rollback(db, A, v1)
    assert (await store.published_tokens(db, A))["theme"]["colors"]["primary"] == t1["theme"]["colors"]["primary"], "volver restaura"
    with pytest.raises(store.BrandConflict):
        await store.rollback(db, A, 999)
    await store.unpublish(db, A)
    assert await store.published_tokens(db, A) is None


@pytest.mark.asyncio
async def test_max_ten_versions_per_company():
    db = ThemesDb()
    for i in range(14):
        t = base_tokens()
        t["theme"]["radius"] = i
        await store.save_draft(db, A, t)
        await store.publish(db, A)
        await store.state(db, A, {})
    assert len([t for t in db.themes if t["company_id"] == A]) <= 10


@pytest.mark.asyncio
async def test_companies_never_receive_each_others_tokens_or_images():
    db = ThemesDb()
    img_b = str(uuid.uuid4())
    db.images.append({"id": img_b, "company_id": B})
    tb = base_tokens()
    tb["theme"]["colors"]["primary"] = "#bbbbbb"
    tb["backgrounds"]["general"]["image"] = {"id": img_b, "mode": "cover"}
    await store.save_draft(db, B, tb)
    await store.publish(db, B)
    assert await store.published_tokens(db, A) is None, "A no recibe la marca de B"
    ta = base_tokens()
    ta["theme"]["logo"] = img_b
    with pytest.raises(bt.BrandInvalid, match="no es de esta empresa"):
        await store.save_draft(db, A, ta)
    copied = await store.tokens_for_copy(db, B)
    assert copied["theme"]["colors"]["primary"] == "#bbbbbb" and bt.image_ids(copied) == set(), "copiar no lleva sus imagenes"
    css = bt.css_for(await store.published_tokens(db, B), B)
    assert f"/brand-media/{B}/{img_b}" in css and A not in css


@pytest.mark.asyncio
async def test_initial_draft_moves_the_logo_to_the_bucket():
    class Mem:
        objects = {}

        def put(self, k, d):
            self.objects[k] = d

        def get(self, k):
            return self.objects[k]

        def delete(self, ks):
            pass

        def list(self, p):
            return []

    import base64
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (20, 20), "#ff0000").save(buf, format="PNG")
    logo = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    db = ThemesDb()
    saved = {}

    async def fake_upload(_db, cid, raw):
        saved["cid"], saved["raw"] = cid, raw
        return {"id": "11111111-2222-3333-4444-555555555555"}

    media.set_backend(Mem())
    try:
        orig = media.upload
        media.upload = fake_upload
        first = await store.state(db, A, {"logo_url": logo, "primary_color": "#ff0000"})
    finally:
        media.upload = orig
        media.set_backend(None)
    assert saved["cid"] == A and saved["raw"] == buf.getvalue()
    assert first["draft"]["tokens"]["theme"]["logo"] == "11111111-2222-3333-4444-555555555555"


def test_sql_params_used_twice_are_cast():
    """asyncpg no deduce el tipo si un parametro se usa en dos lugares sin CAST
    (fallo real en produccion: AmbiguousParameterError en el INSERT de versiones)."""
    import re as _re
    from pathlib import Path as _P

    for f in ("app/services/brand_store.py", "app/services/brand_media.py", "app/services/brand_share.py", "app/web/brand_routes.py"):
        src = _P(f).read_text(encoding="utf-8")
        for sql in _re.findall(r'text\(\s*f?"""(.*?)"""', src, _re.S):
            names = _re.findall(r"(?<!:):([a-z_]+)\b", sql)
            for name in {n for n in names if names.count(n) > 1}:
                bare = _re.findall(rf"(?<!CAST\():{name}\b(?! AS)", sql)
                assert not bare, f"{f}: :{name} se usa varias veces sin CAST en: {sql.strip()[:80]}"


# ------------------------------------------------------------ endpoints
@pytest.fixture
def client(monkeypatch):
    db = ThemesDb()

    async def fake_db():
        yield db

    app_main.app.dependency_overrides[get_db] = fake_db
    yield SimpleNamespace(c=TestClient(app_main.app), mp=monkeypatch, db=db)
    app_main.app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("method,path", [
    ("get", "/admin-v2/api/brand/templates"), ("get", f"/admin-v2/api/brand/{A}"), ("put", f"/admin-v2/api/brand/{A}/draft"),
    ("post", f"/admin-v2/api/brand/{A}/publish"), ("post", f"/admin-v2/api/brand/{A}/rollback/1"),
    ("post", f"/admin-v2/api/brand/{A}/unpublish"), ("post", f"/admin-v2/api/brand/{A}/palette-from-logo"),
    ("post", f"/admin-v2/api/brand/{A}/copy-from/{B}"),
])
def test_brand_endpoints_require_admin_v2_session(client, method, path):
    client.mp.setattr(ep.v2, "_active_session", AsyncMock(return_value=False))
    res = getattr(client.c, method)(path, **({"json": {}} if method in ("put", "post") else {}))
    assert res.status_code == 401
    assert client.db.themes == []


def test_publish_requires_the_company_name_and_is_audited(client):
    client.mp.setattr(ep.v2, "_active_session", AsyncMock(return_value=True))
    client.mp.setattr("app.web.brand_routes.load_company", AsyncMock(return_value={"id": A, "name": "ASADERO EL SOCIO", "kind": "registrada"}))
    noted = []
    client.mp.setattr("app.web.brand_routes._audit", AsyncMock(side_effect=lambda req, **d: noted.append(d)))
    assert client.c.put(f"/admin-v2/api/brand/{A}/draft", json={"tokens": base_tokens()}).status_code == 200
    bad = base_tokens()
    bad["theme"]["colors"]["primary"] = "rojo"
    res = client.c.put(f"/admin-v2/api/brand/{A}/draft", json={"tokens": bad})
    assert res.status_code == 422 and res.json()["detail"]["field"] == "theme.colors.primary"
    assert client.c.post(f"/admin-v2/api/brand/{A}/publish", json={"confirm_name": "otra"}).status_code == 400
    res = client.c.post(f"/admin-v2/api/brand/{A}/publish", json={"confirm_name": "asadero el socio"})
    assert res.status_code == 200 and noted[-1]["marca"] == "publicada"
