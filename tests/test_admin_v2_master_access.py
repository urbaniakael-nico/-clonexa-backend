"""Acceso maestro de Admin V2: la clave nunca vive en el repo, bcrypt primero,
SHA-256 heredado con aviso, login cerrado sin variables y limite de intentos."""
from __future__ import annotations

import hashlib
import importlib.util
import logging
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock

import bcrypt
import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.deps import get_db
from app.web import admin_v2_routes as routes

ROOT = Path(__file__).resolve().parent.parent
EMAIL = routes.ADMIN_V2_EMAIL
PASSWORD = "clave-de-prueba-larga-2026"
client = TestClient(app_main.app)


@pytest.fixture
def env(monkeypatch):
    monkeypatch.delenv(routes.PASSWORD_BCRYPT_ENV, raising=False)
    monkeypatch.delenv(routes.PASSWORD_SHA256_ENV, raising=False)
    routes._login_failures.clear()
    monkeypatch.setattr(routes, "register_access_session", AsyncMock(return_value="sess-1"))
    monkeypatch.setattr(routes, "list_access_sessions", AsyncMock(return_value=[]))
    monkeypatch.setattr(routes, "close_access_session", AsyncMock())
    monkeypatch.setattr(routes, "_active_session", AsyncMock(return_value=False))

    async def fake_db():
        yield None

    app_main.app.dependency_overrides[get_db] = fake_db
    yield monkeypatch
    app_main.app.dependency_overrides.pop(get_db, None)
    routes._login_failures.clear()


def login(password=PASSWORD, email=EMAIL, ip="200.1.1.1"):
    return client.post("/admin-v2/login", data={"email": email, "password": password},
                       headers={"x-forwarded-for": ip}, follow_redirects=False)


def test_admin_v2_login_with_bcrypt(env):
    env.setenv(routes.PASSWORD_BCRYPT_ENV, bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(rounds=4)).decode())
    env.setenv(routes.PASSWORD_SHA256_ENV, hashlib.sha256(b"otra-clave").hexdigest())  # bcrypt manda
    assert routes.master_access_mode() == "bcrypt"
    ok = login()
    assert ok.status_code == 303 and ok.headers["location"] == "/admin-v2"
    assert routes.ADMIN_V2_COOKIE in ok.headers.get("set-cookie", "")
    assert login(password="otra-clave").status_code == 401, "con bcrypt, el SHA-256 ya no abre"
    assert login(password="mala").status_code == 401


def test_admin_v2_login_with_legacy_sha256_warns(env, caplog):
    env.setenv(routes.PASSWORD_SHA256_ENV, hashlib.sha256(PASSWORD.encode()).hexdigest())
    routes._legacy_warned = False
    assert routes.master_access_mode() == "sha256_legacy"
    with caplog.at_level(logging.WARNING, logger="clonexa.admin_v2"):
        assert login().status_code == 303
    assert any("migra a CLONEXA_ADMIN_V2_PASSWORD_BCRYPT" in r.getMessage() for r in caplog.records)


def test_admin_v2_login_closed_without_variables(env):
    assert routes.master_access_mode() == "unset"
    page = client.get("/admin-v2/login")
    assert page.status_code == 503
    assert "Acceso maestro sin configurar: define CLONEXA_ADMIN_V2_PASSWORD_BCRYPT en Railway" in page.text
    attempt = login()
    assert attempt.status_code == 503 and "sin configurar" in attempt.text
    assert routes.ADMIN_V2_COOKIE not in attempt.headers.get("set-cookie", "")
    routes.register_access_session.assert_not_awaited()


def test_admin_v2_blocks_after_five_failures_per_ip(env, caplog):
    env.setenv(routes.PASSWORD_BCRYPT_ENV, bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(rounds=4)).decode())
    with caplog.at_level(logging.WARNING, logger="clonexa.admin_v2"):
        for _ in range(5):
            assert login(password="mala").status_code == 401
    failures = [r.getMessage() for r in caplog.records if "intento fallido" in r.getMessage()]
    assert len(failures) == 5 and "200.1.1.1" in failures[0]
    assert all("mala" not in message for message in failures), "nunca se registra la clave"
    blocked = login()                                         # ni con la clave correcta
    assert blocked.status_code == 429 and "Demasiados intentos" in blocked.text
    assert int(blocked.headers["retry-after"]) > 0
    assert login(ip="200.9.9.9").status_code == 303, "otra IP no queda bloqueada"
    # A los 15 minutos se vuelve a poder.
    routes._login_failures["200.1.1.1"] = type(routes._login_failures["200.1.1.1"])(
        t - routes.LOGIN_WINDOW_SECONDS - 1 for t in routes._login_failures["200.1.1.1"])
    assert login().status_code == 303


def test_admin_v2_rate_limit_uses_the_proxy_ip_not_the_spoofable_one(env):
    env.setenv(routes.PASSWORD_BCRYPT_ENV, bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(rounds=4)).decode())
    for n in range(5):
        login(password="mala", ip=f"1.2.3.{n}, 200.1.1.1")   # el cliente cambia lo primero
    assert login(ip="9.9.9.9, 200.1.1.1").status_code == 429


def test_admin_v2_default_hash_is_gone_from_the_code():
    source = (ROOT / "app/web/admin_v2_routes.py").read_text(encoding="utf-8")
    assert "8a0b1744088773d637ad0b016cc2424fac07ae0a59a9dd946a8022958e55e10c" not in source
    tracked = subprocess.run(["git", "grep", "-l", "8a0b1744088773d637ad0b016cc2424fac07ae0a59a9dd946a8022958e55e10c", "--", "app", "scripts"],
                             cwd=ROOT, capture_output=True, text=True)
    assert tracked.stdout.strip() == "", "ningun archivo del codigo trae el hash viejo"
    assert 'os.getenv(\n    "CLONEXA_ADMIN_V2_PASSWORD_SHA256",' not in source


def test_admin_v2_hash_script_makes_a_bcrypt_hash_and_writes_nothing(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("admin_v2_hash", ROOT / "scripts/admin_v2_hash.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.chdir(tmp_path)
    answers = iter(["una-clave-muy-segura-2026", "una-clave-muy-segura-2026"])
    monkeypatch.setattr(module.getpass, "getpass", lambda _prompt: next(answers))
    assert module.main() == 0
    assert list(tmp_path.iterdir()) == [], "no guarda nada en disco"
    hashed = module.make_hash("una-clave-muy-segura-2026")
    assert hashed.startswith("$2b$12$") and bcrypt.checkpw(b"una-clave-muy-segura-2026", hashed.encode())
    with pytest.raises(ValueError):
        module.make_hash("corta")
