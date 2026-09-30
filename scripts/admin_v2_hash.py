"""Genera el hash bcrypt de la clave del acceso maestro (Admin V2).

Uso:
    python scripts/admin_v2_hash.py

Pide la clave dos veces por consola (no se ve al escribir) e imprime el hash
listo para pegar en Railway como CLONEXA_ADMIN_V2_PASSWORD_BCRYPT.
No guarda nada en disco ni en el historial de la terminal.
"""
from __future__ import annotations

import getpass
import sys

import bcrypt

MIN_LENGTH = 12


def make_hash(password: str) -> str:
    if len(password) < MIN_LENGTH:
        raise ValueError(f"La clave debe tener al menos {MIN_LENGTH} caracteres.")
    if len(password.encode("utf-8")) > 72:
        raise ValueError("La clave no puede pasar de 72 bytes (limite de bcrypt).")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def main() -> int:
    password = getpass.getpass("Nueva clave del acceso maestro: ")
    again = getpass.getpass("Repite la clave: ")
    if password != again:
        print("Las claves no coinciden. No se genero nada.", file=sys.stderr)
        return 1
    try:
        hashed = make_hash(password)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("\nPega este valor en Railway como CLONEXA_ADMIN_V2_PASSWORD_BCRYPT (tal cual, sin comillas):\n")
    print(hashed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
