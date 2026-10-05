"""Fase 4 · Partes 3 y 4: vista previa, enlace para el cliente e imagenes.

- Imagenes: las de la marca publicada son publicas; las del borrador solo con
  la consola o con un enlace vigente de ESA empresa; nunca las de otra.
- Enlace de vista previa: firmado, vence, se revoca, sin datos reales y no
  sirve para nada mas (ni otra empresa ni /api/v1).
- La vista previa del estudio y el render en vivo exigen sesion de Admin V2.
"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.deps import get_db
from app.services import brand_share as share
from app.services import brand_theme as bt
from app.web import admin_v2plus_companies as ep
from app.web import brand_routes

A, B = str(uuid.uuid4()), str(uuid.uuid4())
IMG_A, IMG_B = str(uuid.uuid4()), str(uuid.uuid4())


def tokens_with_image(img: str) -> dict:
    t = copy.deepcopy(bt.templates()[3]["tokens"])
    t["backgrounds"]["caja"] = {"base": {"kind": "solid", "color": "#111111"}, "image": {"id": img, "mode": "cover"}, "veil": None}
    return bt.validate(t)


class Db:
    """Interpreta las consultas de marca, enlaces e imagenes en memoria."""

    def __init__(self):
        self.themes, self.images, self.links = [], [], []

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        p = params or {}
        if "FROM company_brand_themes WHERE company_id = CAST(:c AS uuid) AND status = 'published'" in sql:
            return R([t for t in self.themes if t["company_id"] == p["c"] and t["status"] == "published"])
        if "FROM company_brand_themes WHERE company_id = CAST(:c AS uuid) AND status = 'draft'" in sql:
            return R([t for t in self.themes if t["company_id"] == p["c"] and t["status"] == "draft"])
        if sql.startswith("SELECT 1 FROM company_brand_images"):
            return R([1] if any(i["id"] == p["i"] and i["company_id"] == p["c"] for i in self.images) else [])
        if sql.startswith("INSERT INTO company_brand_share_links"):
            self.links.append({"id": p["i"], "company_id": p["c"], "secret_hash": p["h"], "expires_at": p["e"], "revoked_at": None, "created_at": datetime.now(timezone.utc)})
            return R()
        if sql.startswith("SELECT company_id::text AS company_id, secret_hash"):
            return R([link for link in self.links if link["id"] == p["i"]])
        if sql.startswith("UPDATE company_brand_share_links SET revoked_at"):
            hit = [link for link in self.links if link["id"] == p["i"] and link["company_id"] == p["c"] and link["revoked_at"] is None]
            for link in hit:
                link["revoked_at"] = datetime.now(timezone.utc)
            return R(rowcount=len(hit))
        if sql.startswith("SELECT id::text AS id, created_at, expires_at, revoked_at"):
            return R([link for link in self.links if link["company_id"] == p["c"]])
        raise AssertionError(sql)

    async def commit(self):
        pass

    async def rollback(self):
        pass


class R:
    def __init__(self, rows=None, rowcount=0):
        self.rows, self.rowcount = rows or [], rowcount

    def mappings(self):
        return SimpleNamespace(all=lambda: self.rows, first=lambda: self.rows[0] if self.rows else None)

    def first(self):
        return self.rows[0] if self.rows else None


# ------------------------------------------------------------ enlace
@pytest.mark.asyncio
async def test_share_token_is_signed_expires_and_can_be_revoked():
    db = Db()
    link = await share.create(db, A)
    assert link["url"] == f"/vista-marca/{link['token']}" and len(link["token"]) > 80
    assert db.links[0]["secret_hash"] not in link["token"], "en la base solo el hash"
    assert (await share.resolve(db, link["token"]))["company_id"] == A
    link_id, secret, sig = link["token"].split(".")
    assert await share.resolve(db, f"{link_id}.{secret}.{'0' * 32}") is None, "firma alterada"
    assert await share.resolve(db, f"{link_id}.{secret[:-1]}x.{sig}") is None, "secreto alterado"
    assert await share.resolve(db, "basura") is None
    db.links[0]["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert await share.resolve(db, link["token"]) is None, "vencido"
    db.links[0]["expires_at"] = datetime.now(timezone.utc) + timedelta(days=1)
    assert await share.revoke(db, B, link_id) is False, "otra empresa no lo revoca"
    assert await share.revoke(db, A, link_id) is True
    assert await share.resolve(db, link["token"]) is None, "revocado"
    assert share.TTL == timedelta(days=7)


@pytest.fixture
def client(monkeypatch):
    db = Db()

    async def fake_db():
        yield db

    app_main.app.dependency_overrides[get_db] = fake_db
    monkeypatch.setattr(brand_routes.v2, "_active_session", AsyncMock(return_value=False))
    yield SimpleNamespace(c=TestClient(app_main.app, base_url="https://testserver"), mp=monkeypatch, db=db)
    app_main.app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_share_page_shows_sample_data_only_and_sets_scoped_cookie(client):
    db = client.db
    db.themes.append({"company_id": A, "status": "draft", "tokens": tokens_with_image(IMG_A)})
    link = await share.create(db, A)
    res = client.c.get(link["url"] + "?screen=caja")
    assert res.status_code == 200
    body = res.text
    assert "Vista previa · aún no publicada" in body
    assert "muestra" in body and "Mesero de muestra" in body
    assert "hsp_cashier.js" not in body and "api/v1" not in body, "no carga el panel ni llama a la API"
    assert "frame-ancestors 'self'" in res.headers["content-security-policy"]
    cookie = res.headers["set-cookie"]
    assert f"Path=/brand-media/{A}/" in cookie and "HttpOnly" in cookie and "samesite=strict" in cookie.lower()
    db.links[0]["revoked_at"] = datetime.now(timezone.utc)
    gone = client.c.get(link["url"])
    assert gone.status_code == 404 and "ya no sirve" in gone.text


@pytest.mark.asyncio
async def test_share_token_does_not_open_api_or_other_company(client):
    db = client.db
    db.themes.append({"company_id": A, "status": "draft", "tokens": tokens_with_image(IMG_A)})
    link = await share.create(db, A)
    res = client.c.get(f"/api/v1/companies/{A}/users", headers={"Authorization": f"Bearer {link['token']}"})
    assert res.status_code in (401, 403), "el token no es una sesion"
    client.mp.setattr(ep.v2, "_active_session", AsyncMock(return_value=False))
    assert client.c.get(f"/admin-v2/api/brand/{A}", headers={"Authorization": f"Bearer {link['token']}"},
                        cookies={share.COOKIE: link["token"]}).status_code == 401


# ------------------------------------------------------------ imagenes
@pytest.mark.asyncio
async def test_image_access_rules(client):
    db = client.db
    req = SimpleNamespace(cookies={})
    db.themes += [{"company_id": A, "status": "published", "tokens": tokens_with_image(IMG_A)},
                  {"company_id": B, "status": "draft", "tokens": tokens_with_image(IMG_B)}]
    assert await brand_routes.can_view(req, db, A, IMG_A) == (True, True), "publicada: publica"
    assert await brand_routes.can_view(req, db, B, IMG_A) == (False, False), "la de A no se ve como de B"
    assert await brand_routes.can_view(req, db, B, IMG_B) == (False, False), "borrador sin permiso: no"
    link_b = await share.create(db, B)
    assert await brand_routes.can_view(SimpleNamespace(cookies={share.COOKIE: link_b["token"]}), db, B, IMG_B) == (True, False)
    link_a = await share.create(db, A)
    assert await brand_routes.can_view(SimpleNamespace(cookies={share.COOKIE: link_a["token"]}), db, B, IMG_B) == (False, False), "el enlace de A no abre imagenes de B"
    client.mp.setattr(brand_routes.v2, "_active_session", AsyncMock(return_value=True))
    assert await brand_routes.can_view(req, db, B, IMG_B) == (True, False), "la consola si"


# ------------------------------------------------------------ consola
def test_studio_preview_and_render_require_session(client):
    client.mp.setattr(ep.v2, "_active_session", AsyncMock(return_value=False))
    assert client.c.get(f"/admin-v2/brand-preview/{A}").status_code == 401
    assert client.c.post(f"/admin-v2/api/brand/{A}/render", json={"tokens": {}}).status_code == 401
    assert client.c.get(f"/admin-v2/api/brand/{A}/share").status_code == 401
    assert client.c.post(f"/admin-v2/api/brand/{A}/share", json={}).status_code == 401
    assert client.c.delete(f"/admin-v2/api/brand/{A}/share/{B}").status_code == 401


def test_preview_page_only_has_sample_screens():
    from app.web import brand_preview

    for screen in ("ingreso", "mesero", "cocina", "caja"):
        html = brand_preview.page(screen=screen, company_id=A, css="", branding={}, mode="studio")
        assert "<script src=\"/client-static/hsp_" not in html.replace("hsp_brand.js", ""), "ningun script de los paneles"
        assert "data-brand=" in html
        assert '<style id="cxBrandTheme">' in html
        assert "brand_preview.js" in html


# ------------------------------------------------------------ auditoria
def test_brand_writes_are_audited_with_their_company_and_render_is_not():
    from app.services import admin_audit

    assert admin_audit.company_id_from_path(f"/admin-v2/api/brand/{A}/publish") == A
    assert admin_audit.company_id_from_path(f"/admin-v2/api/brand/{A}/rollback/2") == A
    assert admin_audit.company_id_from_path(f"/api/v1/companies/{B}/modules/qr/activate") == B
    assert admin_audit.audited("POST", f"/admin-v2/api/brand/{A}/publish") is True
    assert admin_audit.audited("PUT", f"/admin-v2/api/brand/{A}/draft") is True
    assert admin_audit.audited("POST", f"/admin-v2/api/brand/{A}/render") is False, "el render en vivo no llena la auditoria"
    assert admin_audit.audited("GET", f"/admin-v2/api/brand/{A}") is False
