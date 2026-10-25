"""Rotacion de la clave de los tokens de bots: la clave vieja sigue descifrando
hasta que se quita, y lo nuevo se cifra con CLONEXA_BOT_TOKEN_KEY."""
import pytest
from cryptography.fernet import InvalidToken

from app.api.v1.endpoints import bots

TOKEN = "123456:ABC-def_ghi"


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.delenv(bots.BOT_TOKEN_KEY_ENV, raising=False)
    monkeypatch.delenv(bots.BOT_TOKEN_KEY_PREVIOUS_ENV, raising=False)
    monkeypatch.setattr(bots.get_settings(), "JWT_SECRET_KEY", "jwt-viejo")

    def use(primary=None, previous=None, jwt=None):
        if primary is not None:
            monkeypatch.setenv(bots.BOT_TOKEN_KEY_ENV, primary)
        if previous is not None:
            monkeypatch.setenv(bots.BOT_TOKEN_KEY_PREVIOUS_ENV, previous)
        if jwt is not None:
            monkeypatch.setattr(bots.get_settings(), "JWT_SECRET_KEY", jwt)

    return use


def test_sin_variables_nuevas_usa_jwt_como_antes(keys):
    stored = bots.encrypt_token(TOKEN)
    assert stored.startswith("fernet:")
    expected = bots._fernet_for("jwt-viejo").decrypt(stored.removeprefix("fernet:").encode()).decode()
    assert expected == TOKEN
    assert bots.decrypt_token(stored) == TOKEN
    assert bots.token_uses_primary_key(stored)


def test_clave_nueva_cifra_y_la_anterior_descifra(keys):
    old_stored = bots.encrypt_token(TOKEN)
    keys(primary="clave-nueva", previous="jwt-viejo", jwt="jwt-rotado")
    assert bots.decrypt_token(old_stored) == TOKEN
    assert not bots.token_uses_primary_key(old_stored)

    new_stored = bots.reencrypt_token(old_stored)
    assert bots.token_uses_primary_key(new_stored)
    assert bots._fernet_for("clave-nueva").decrypt(new_stored.removeprefix("fernet:").encode()).decode() == TOKEN
    assert bots.decrypt_token(bots.encrypt_token(TOKEN)) == TOKEN


def test_sin_la_anterior_lo_viejo_ya_no_descifra(keys):
    old_stored = bots.encrypt_token(TOKEN)
    keys(primary="clave-nueva", jwt="jwt-rotado")
    with pytest.raises(InvalidToken):
        bots.decrypt_token(old_stored)


def test_rotar_jwt_no_toca_los_bots_si_hay_clave_propia(keys):
    keys(primary="clave-nueva")
    stored = bots.encrypt_token(TOKEN)
    keys(jwt="otro-jwt-mas")
    assert bots.decrypt_token(stored) == TOKEN


def test_varias_anteriores_y_espacios(keys):
    keys(primary="a")
    stored_a = bots.encrypt_token(TOKEN)
    keys(primary="c", previous=" b , a ,")
    assert bots.decrypt_token(stored_a) == TOKEN
    assert bots._bot_token_secrets() == ["c", "b", "a"]


def test_reencrypt_ignora_lo_que_no_es_fernet(keys):
    assert bots.reencrypt_token(None) is None
    assert bots.reencrypt_token("b64:eHg=") is None
    assert not bots.token_uses_primary_key("b64:eHg=")
