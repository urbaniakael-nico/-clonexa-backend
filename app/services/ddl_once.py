"""DDL "por si acaso" sin bloquear tablas en cada mensaje (060A, todas las empresas).

Causa del DBAPIError del bot (2 nov 2026, logs de Postgres): "deadlock detected".
Cada update de Telegram llamaba a ensure_bot_storage() / ensure_company_bot_storage() /
_ensure_gps_perimeter_storage() / _ensure_material_requests_storage() DENTRO de su
transaccion. Aunque la tabla ya exista:
- ``CREATE INDEX IF NOT EXISTS ... ON gps_tracking_sessions`` toma un ShareLock de
  la TABLA antes de ver que el indice ya existe, y lo guarda hasta el commit;
- ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS`` toma un AccessExclusiveLock.
Dos updates a la vez (ubicacion en vivo + Pausa) tenian cada uno su ShareLock y luego
pedian RowExclusiveLock para el ``UPDATE gps_tracking_sessions``: cada uno esperaba al
otro -> Postgres mataba uno (deadlock) y ese update fallaba sin respuesta.

Con ``@ddl_once("clave")`` la funcion solo corre su DDL si falta algo. Para saberlo,
se "graba" su SQL una vez (sin tocar la base), se sacan los nombres (extension, tabla,
indice, columna, indice que debe NO existir) y se verifican con ``to_regclass`` /
``pg_attribute`` / ``pg_extension``, que no toman bloqueos de tabla. Si todo existe,
queda marcado para el resto del proceso y no vuelve a consultar. Si falta algo (base
nueva, pruebas) o la verificacion no se puede hacer, corre el DDL de siempre.
"""
from __future__ import annotations

import functools
import logging
import re
from typing import Any, Awaitable, Callable

from sqlalchemy import text

log = logging.getLogger("clonexa.ddl_once")

_READY: set[str] = set()
_CHECKS: dict[str, list[tuple] | None] = {}

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("ext", re.compile(r'^CREATE EXTENSION IF NOT EXISTS "?([\w-]+)"?;?$', re.I)),
    ("rel", re.compile(r"^CREATE TABLE IF NOT EXISTS (\w+)\b", re.I)),
    ("rel", re.compile(r"^CREATE (?:UNIQUE )?INDEX IF NOT EXISTS (\w+)\b", re.I)),
    ("col", re.compile(r"^ALTER TABLE (\w+) ADD COLUMN IF NOT EXISTS (\w+)\b", re.I)),
    ("absent", re.compile(r"^DROP INDEX IF EXISTS (\w+);?$", re.I)),
]


class _Result:
    def scalar(self) -> None:
        return None

    def first(self) -> None:
        return None

    def mappings(self) -> "_Result":
        return self

    def all(self) -> list:
        return []


class _Recorder:
    """Sesion falsa: guarda el SQL que la funcion ejecutaria, sin tocar la base."""

    def __init__(self) -> None:
        self.sql: list[str] = []

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> _Result:
        self.sql.append(str(statement))
        return _Result()

    async def commit(self) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


def checks_from_sql(statements: list[str]) -> list[tuple] | None:
    """Objetos que el DDL garantiza. None si hay una sentencia que no se sabe verificar."""
    out: list[tuple] = []
    for raw in statements:
        stmt = re.sub(r"\s+", " ", raw).strip()
        if not stmt:
            continue
        for kind, pattern in _PATTERNS:
            match = pattern.match(stmt)
            if match:
                out.append((kind, *[g.lower() for g in match.groups()]))
                break
        else:
            return None
    return out


async def _record(fn: Callable[..., Awaitable[Any]]) -> list[tuple] | None:
    recorder = _Recorder()
    try:
        await fn(recorder)
    except Exception:
        return None
    return checks_from_sql(recorder.sql)


VERIFY_SQL = """
    SELECT
      (SELECT count(*) FROM pg_extension WHERE extname = ANY(CAST(:exts AS text[]))) = :n_ext
      AND (SELECT count(*) FROM unnest(CAST(:rels AS text[])) AS r(name) WHERE to_regclass(r.name) IS NOT NULL) = :n_rel
      AND (SELECT count(*) FROM unnest(CAST(:absent AS text[])) AS r(name) WHERE to_regclass(r.name) IS NOT NULL) = 0
      AND (SELECT count(*) FROM unnest(CAST(:ct AS text[]), CAST(:cc AS text[])) AS x(t, c)
             JOIN pg_attribute a ON a.attrelid = to_regclass(x.t) AND a.attname = x.c AND NOT a.attisdropped) = :n_col
"""


def verify_params(checks: list[tuple]) -> dict[str, Any]:
    exts = sorted({c[1] for c in checks if c[0] == "ext"})
    rels = sorted({c[1] for c in checks if c[0] == "rel"} | {c[1] for c in checks if c[0] == "col"})
    absent = sorted({c[1] for c in checks if c[0] == "absent"})
    cols = sorted({(c[1], c[2]) for c in checks if c[0] == "col"})
    return {"exts": exts, "n_ext": len(exts), "rels": rels, "n_rel": len(rels), "absent": absent,
            "ct": [t for t, _ in cols], "cc": [c for _, c in cols], "n_col": len(cols)}


async def already_there(db: Any, key: str, fn: Callable[..., Awaitable[Any]]) -> bool:
    if key not in _CHECKS:
        _CHECKS[key] = await _record(fn)
    checks = _CHECKS[key]
    if not checks:
        return False
    try:
        result = await db.execute(text(VERIFY_SQL), verify_params(checks))
        return result.scalar() is True
    except Exception as exc:  # sesion falsa o base rara: el DDL de siempre
        log.debug("ddl_once %s: no se pudo verificar (%s)", key, type(exc).__name__)
        return False


def ddl_once(key: str) -> Callable:
    def deco(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @functools.wraps(fn)
        async def wrapper(db: Any, *args: Any, **kwargs: Any) -> Any:
            if key in _READY:
                return None
            if await already_there(db, key, fn):
                _READY.add(key)
                return None
            return await fn(db, *args, **kwargs)

        wrapper.ddl_key = key  # type: ignore[attr-defined]
        wrapper.ddl_fn = fn  # type: ignore[attr-defined]
        return wrapper

    return deco


def reset() -> None:
    """Solo pruebas."""
    _READY.clear()
    _CHECKS.clear()
