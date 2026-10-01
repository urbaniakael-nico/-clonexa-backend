"""Consola v2+: entrar con huella (llave de acceso WebAuthn) O con clave.

Se usa un autenticador de software (llaves P-256 reales, mismo formato que un
lector de huella) para probar la verificacion de verdad, de punta a punta."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import bcrypt
import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.deps import get_db
from app.web import admin_v2_routes as v2
from app.web import admin_v2plus_routes as plus

ORIGIN, RP_ID = "http://testserver", "testserver"
PASSWORD = "clave-de-prueba-larga-2026"


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class SoftAuthenticator:
    """Un "lector de huella" de software: firma como lo haria el equipo."""

    def __init__(self):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self.counter = 0

    def _cose(self) -> bytes:
        numbers = self.key.public_key().public_numbers()
        return cbor2.dumps({1: 2, 3: -7, -1: 1, -2: numbers.x.to_bytes(32, "big"), -3: numbers.y.to_bytes(32, "big")})

    def create(self, options: dict, origin=ORIGIN) -> dict:
        client = json.dumps({"type": "webauthn.create", "challenge": options["challenge"], "origin": origin, "crossOrigin": False}).encode()
        auth = (hashlib.sha256(options["rp"]["id"].encode()).digest() + bytes([0x45]) + struct.pack(">I", 0)
                + bytes(16) + struct.pack(">H", len(self.credential_id)) + self.credential_id + self._cose())
        att = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth})
        return {"id": b64(self.credential_id), "rawId": b64(self.credential_id), "type": "public-key",
                "response": {"clientDataJSON": b64(client), "attestationObject": b64(att), "transports": ["internal"]},
                "clientExtensionResults": {}, "authenticatorAttachment": "platform"}

    def get(self, options: dict, origin=ORIGIN, rp_id=RP_ID, tamper=False) -> dict:
        self.counter += 1
        client = json.dumps({"type": "webauthn.get", "challenge": options["challenge"], "origin": origin, "crossOrigin": False}).encode()
        auth = hashlib.sha256(rp_id.encode()).digest() + bytes([0x05]) + struct.pack(">I", self.counter)
        signature = self.key.sign(auth + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
        if tamper:
            signature = signature[:-2] + bytes([signature[-2] ^ 1, signature[-1]])
        return {"id": b64(self.credential_id), "rawId": b64(self.credential_id), "type": "public-key",
                "response": {"clientDataJSON": b64(client), "authenticatorData": b64(auth), "signature": b64(signature), "userHandle": None},
                "clientExtensionResults": {}}


class PasskeyDb:
    def __init__(self, ready=True):
        self.ready = ready
        self.rows: dict[str, dict] = {}
        self.commit = AsyncMock()

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        p = params or {}
        rows: list = []
        count = 0
        if "to_regclass('public.admin_v2_passkeys')" in sql:
            rows = [{"ok": self.ready}]
        elif sql.startswith("SELECT id, credential_id, public_key"):
            rows = sorted(self.rows.values(), key=lambda r: r["created_at"])
        elif sql.startswith("SELECT * FROM admin_v2_passkeys WHERE credential_id"):
            rows = [r for r in self.rows.values() if r["credential_id"] == p["cid"]]
        elif sql.startswith("INSERT INTO admin_v2_passkeys"):
            if not any(r["credential_id"] == p["cid"] for r in self.rows.values()):
                rid = uuid.uuid4()
                self.rows[str(rid)] = {"id": rid, "credential_id": p["cid"], "public_key": p["pk"], "sign_count": p["sc"],
                                       "label": p["label"], "transports": json.loads(p["transports"]),
                                       "created_at": datetime.now(timezone.utc), "last_used_at": None}
        elif sql.startswith("UPDATE admin_v2_passkeys SET sign_count"):
            for r in self.rows.values():
                if r["credential_id"] == p["cid"]:
                    r.update(sign_count=p["sc"], last_used_at=datetime.now(timezone.utc))
        elif sql.startswith("DELETE FROM admin_v2_passkeys"):
            count = 1 if self.rows.pop(p["id"], None) else 0
        else:
            raise AssertionError(f"SQL no esperado: {sql[:100]}")
        return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows, first=lambda: rows[0] if rows else None),
                               rowcount=count)


@pytest.fixture
def world(monkeypatch):
    db = PasskeyDb()
    session = {"on": False}

    async def fake_db():
        yield db

    async def active(_request, _db):
        return session["on"]

    monkeypatch.setattr(plus, "_active_session", active)
    monkeypatch.setattr(v2, "register_access_session", AsyncMock(return_value="sess-9"))
    monkeypatch.setattr(v2, "list_access_sessions", AsyncMock(return_value=[]))
    monkeypatch.setattr(v2, "close_access_session", AsyncMock())
    monkeypatch.setenv(v2.PASSWORD_BCRYPT_ENV, bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(rounds=4)).decode())
    monkeypatch.delenv("CLONEXA_WEBAUTHN_RP_ID", raising=False)
    monkeypatch.delenv("CLONEXA_WEBAUTHN_ORIGIN", raising=False)
    v2._login_failures.clear()
    app_main.app.dependency_overrides[get_db] = fake_db
    yield SimpleNamespace(db=db, session=session, client=TestClient(app_main.app))
    app_main.app.dependency_overrides.pop(get_db, None)
    v2._login_failures.clear()


def register(world, device: SoftAuthenticator, label="Portátil oficina"):
    world.session["on"] = True
    start = world.client.post("/admin-v2plus/api/passkeys/register/options")
    assert start.status_code == 200, start.text
    options = start.json()["options"]
    assert options["authenticatorSelection"]["userVerification"] == "required", "exige la huella (o PIN), no solo tocar"
    done = world.client.post("/admin-v2plus/api/passkeys/register/verify", json={"label": label, "credential": device.create(options)})
    world.session["on"] = False
    world.client.cookies.clear()
    return done


def login_with(world, device: SoftAuthenticator, **kw):
    start = world.client.post("/admin-v2plus/api/passkey/login/options")
    if start.status_code != 200:
        return start
    return world.client.post("/admin-v2plus/api/passkey/login/verify", json={"credential": device.get(start.json()["options"], **kw)})


def test_admin_v2plus_redirects_to_its_own_login(world):
    response = world.client.get("/admin-v2plus", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/admin-v2plus/login"


def test_admin_v2plus_login_page_asks_fingerprint_first_only_with_registered_devices(world):
    page = world.client.get("/admin-v2plus/login")
    assert page.status_code == 200 and 'data-has-passkeys="false"' in page.text
    assert "Entrar con clave" in page.text and 'action="/admin-v2plus/login"' in page.text
    register(world, SoftAuthenticator())
    assert 'data-has-passkeys="true"' in world.client.get("/admin-v2plus/login").text


def test_admin_v2plus_passkey_management_requires_session(world):
    for method, path in [("GET", "/admin-v2plus/api/passkeys"), ("POST", "/admin-v2plus/api/passkeys/register/options"),
                         ("POST", "/admin-v2plus/api/passkeys/register/verify"), ("DELETE", f"/admin-v2plus/api/passkeys/{uuid.uuid4()}")]:
        assert world.client.request(method, path, json={}).status_code == 401, path


def test_admin_v2plus_register_then_enter_with_fingerprint(world):
    device = SoftAuthenticator()
    done = register(world, device)
    assert done.status_code == 200 and done.json()["passkeys"][0]["label"] == "Portátil oficina"
    stored = next(iter(world.db.rows.values()))
    assert stored["credential_id"] == b64(device.credential_id) and stored["public_key"], "solo la llave publica"
    entered = login_with(world, device)
    assert entered.status_code == 200 and entered.json() == {"ok": True, "redirect": "/admin-v2plus"}
    assert v2.ADMIN_V2_COOKIE in entered.headers.get("set-cookie", ""), "abre la misma sesion de Admin V2"
    assert v2.register_access_session.await_args.kwargs["metadata"]["method"] == "passkey"
    assert stored["sign_count"] == 1 and stored["last_used_at"] is not None


def test_admin_v2plus_fingerprint_rejects_forgery_other_device_and_other_site(world):
    device = SoftAuthenticator()
    register(world, device)
    assert login_with(world, device, tamper=True).status_code == 401, "firma alterada"
    assert login_with(world, SoftAuthenticator()).status_code == 401, "un equipo no registrado"
    assert login_with(world, device, origin="https://phishing.example").status_code == 401, "otro sitio"
    assert v2.ADMIN_V2_COOKIE not in world.client.cookies


def test_admin_v2plus_fingerprint_needs_a_fresh_challenge(world):
    device = SoftAuthenticator()
    register(world, device)
    start = world.client.post("/admin-v2plus/api/passkey/login/options").json()["options"]
    world.client.cookies.clear()                                     # sin el reto firmado
    replay = world.client.post("/admin-v2plus/api/passkey/login/verify", json={"credential": device.get(start)})
    assert replay.status_code == 401


def test_admin_v2plus_fingerprint_failures_share_the_five_attempt_limit(world):
    device = SoftAuthenticator()
    register(world, device)
    for _ in range(5):
        assert login_with(world, device, tamper=True).status_code == 401
    blocked = world.client.post("/admin-v2plus/api/passkey/login/options")
    assert blocked.status_code == 429 and "Demasiados intentos" in blocked.json()["detail"]
    pw = world.client.post("/admin-v2plus/login", data={"email": v2.ADMIN_V2_EMAIL, "password": PASSWORD}, follow_redirects=False)
    assert pw.status_code == 429, "el limite es el mismo para clave y huella"


def test_admin_v2plus_without_devices_fingerprint_says_use_the_password(world):
    response = world.client.post("/admin-v2plus/api/passkey/login/options")
    assert response.status_code == 404 and "Entra con tu clave" in response.json()["detail"]


def test_admin_v2plus_enter_with_password_goes_to_the_new_console(world):
    ok = world.client.post("/admin-v2plus/login", data={"email": v2.ADMIN_V2_EMAIL, "password": PASSWORD}, follow_redirects=False)
    assert ok.status_code == 303 and ok.headers["location"] == "/admin-v2plus"
    assert v2.ADMIN_V2_COOKIE in ok.headers.get("set-cookie", "")
    bad = world.client.post("/admin-v2plus/login", data={"email": v2.ADMIN_V2_EMAIL, "password": "mala"}, follow_redirects=False)
    assert bad.status_code == 401 and "Credenciales invalidas." in bad.text and "Consola v2+" in bad.text


def test_admin_v2plus_remove_a_device(world):
    register(world, SoftAuthenticator())
    world.session["on"] = True
    rid = next(iter(world.db.rows))
    assert world.client.delete(f"/admin-v2plus/api/passkeys/{rid}").json()["passkeys"] == []
    assert world.client.delete(f"/admin-v2plus/api/passkeys/{rid}").status_code == 404


def test_admin_v2plus_passkeys_migration():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "migrations/versions/022p_admin_passkeys.py"
    spec = importlib.util.spec_from_file_location("mig_022p", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(module.revision) <= 32 and module.down_revision == "022o_delivery_print"
    assert "public_key bytea" in path.read_text(encoding="utf-8")
