"""NEGOCIO EN VIVO 3D (modulo vendible "live3d", categoria Complementos).

El cliente ve SU piso de la Oficina 3D (su local, su personal, su representante, sus pantallas) con sus datos reales:
nunca el edificio, ni otras empresas, ni el piso de Clonexa. Una sola fuente de configuracion: la fila de la empresa
en oficina_pisos (la misma que usa la Oficina 3D de la consola) + el modulo live3d en company_modules.

- Interruptor: company_modules (modulo live3d). Apagado para todas; la migracion 025o lo enciende solo en The Time
  Machine (piloto).
- Quien lo ve: 'dueno' (solo el dueno), 'dueno_admin' (dueno y administradores) o 'roles' (el dueno + roles elegidos).
- Acceso del cliente: el panel pide un TICKET firmado (5 min) con su sesion normal (Bearer); el visor lo cambia por
  una cookie HttpOnly firmada (12 h, Path del piso de esa empresa) y TODO lo del visor (motor, three, recursos CC0,
  personajes de Mixamo del bucket privado, copia viva) exige esa cookie + el enlace firmado de la empresa. Cada
  peticion vuelve a comprobar (cache 10 s) que el usuario siga activo, el modulo encendido y su rol en "Quien lo ve".
- Copia viva COMPARTIDA: una sola consulta a la base por empresa cada 7 s (cache en memoria con TTL y una sola
  consulta a la vez por empresa), servida a todas sus pantallas.
- Consumo medido: pantallas abiertas (latido de la copia viva, ventana de 25 s) y bytes servidos por empresa
  (se guardan por mes en live3d_consumo, sin datos pesados).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

MODULE_CODE = "live3d"
MODULE_NAME = "Negocio en vivo 3D"
CATEGORY = "Complementos"
TTM = "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4"

AUDIENCES = ("dueno", "dueno_admin", "roles")
AUDIENCE_LABEL = {"dueno": "Solo el dueño", "dueno_admin": "Dueño y administradores", "roles": "Roles elegidos"}
LITE_MODES = ("auto", "siempre", "nunca")
LITE_LABEL = {"auto": "Automático", "siempre": "Siempre", "nunca": "Nunca"}
PRIVACY_LABEL = {"nombre": "Nombre + inicial y cargo", "cargo": "Solo cargo"}
# Plantilla -> estilo del piso con motor aprobado (el mismo interruptor oficina_pisos.estilo de la oficina).
STYLE_FOR = {"bar": "bar", "taller": "aprobado", "restaurante": "aprobado", "campo": "aprobado"}
WITH_ENGINE = tuple(STYLE_FOR)
NOUN = {"bar": "bar", "restaurante": "restaurante", "taller": "taller", "campo": "operación", "general": "negocio"}

OWNER_ROLES = {"company_admin", "admin_empresa", "dueno", "dueño", "owner", "propietario"}
ADMIN_ROLES = {"administrador", "admin", "gerente", "gerencia", "manager"}
ROLE_RE = re.compile(r"^[a-z0-9_ñáéíóú]{2,40}$")

TICKET_TTL = 5 * 60
COOKIE_TTL = 12 * 60 * 60
RECHECK_TTL = 10.0
SCREEN_WINDOW = 25.0
LIVE_TTL = 7.0
FLUSH_EVERY = 60.0
PREVIEW_MAX = 160 * 1024
PREVIEW_EVERY = 10 * 60.0


def norm_role(role: Any) -> str:
    return str(role or "").strip().lower().replace(" ", "_")


def role_allowed(role: Any, audience: str, roles: list[str]) -> bool:
    """El dueno siempre ve su negocio; administradores con 'dueno_admin'; con 'roles', el dueno + los elegidos."""
    r = norm_role(role)
    if r in OWNER_ROLES:
        return True
    if audience == "dueno_admin":
        return r in ADMIN_ROLES
    if audience == "roles":
        return r in {norm_role(x) for x in roles or []}
    return False


def clean_roles(raw: Any) -> list[str]:
    if not isinstance(raw, list) or len(raw) > 20:
        raise ValueError("Roles no válidos.")
    out = []
    for item in raw:
        r = norm_role(item)
        if not ROLE_RE.match(r):
            raise ValueError("Roles no válidos.")
        if r not in out:
            out.append(r)
    return out


def lite_for(mode: str) -> Optional[str]:
    """Lo que recibe el visor: '1' siempre liviano, '0' nunca, None automatico (celulares y equipos lentos)."""
    return {"siempre": "1", "nunca": "0"}.get(mode)


# ------------------------------------------------------------------ firma (ticket, cookie, enlace)
def _key(secret: bytes, purpose: str) -> bytes:
    return hmac.new(secret, f"clonexa-live3d:{purpose}".encode(), hashlib.sha256).digest()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text_: str) -> bytes:
    return base64.urlsafe_b64decode(text_ + "=" * (-len(text_) % 4))


def sign(secret: bytes, purpose: str, payload: dict) -> str:
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    mac = _b64(hmac.new(_key(secret, purpose), body.encode(), hashlib.sha256).digest()[:24])
    return f"{body}.{mac}"


def verify(secret: bytes, purpose: str, token: str, now: Optional[float] = None) -> Optional[dict]:
    try:
        body, mac = str(token or "").split(".", 1)
        want = _b64(hmac.new(_key(secret, purpose), body.encode(), hashlib.sha256).digest()[:24])
        if not hmac.compare_digest(mac, want):
            return None
        data = json.loads(_unb64(body))
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict) or float(data.get("e") or 0) < (now if now is not None else time.time()):
        return None
    try:
        data["c"] = str(uuid.UUID(str(data.get("c"))))
    except ValueError:
        return None
    if data.get("k") not in ("c", "a"):
        return None
    return data


def link_sig(secret: bytes, company_id: str) -> str:
    """Parte firmada (estable) de las rutas del visor de una empresa: los archivos tienen el mismo enlace en cada
    visita (cache del navegador) pero solo sirven con la cookie de sesion del visor de ESA empresa."""
    return _b64(hmac.new(_key(secret, "link"), str(company_id).encode(), hashlib.sha256).digest()[:12])


def cookie_name(company_id: str) -> str:
    return "cx3d_" + str(company_id).replace("-", "")[:12]


# ------------------------------------------------------------------ configuracion (una sola fuente)
async def _one(db: AsyncSession, sql: str, params: dict) -> Optional[dict]:
    row = (await db.execute(text(sql), params)).mappings().first()
    return dict(row) if row else None


async def module_enabled(db: AsyncSession, company_id: str) -> bool:
    row = await _one(db, """
        SELECT cm.enabled FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id = CAST(:c AS uuid) AND lower(m.code) = :code ORDER BY cm.enabled DESC LIMIT 1
    """, {"c": company_id, "code": MODULE_CODE})
    return bool(row and row.get("enabled"))


def _roles_value(raw: Any) -> list[str]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = []
    return [norm_role(x) for x in raw] if isinstance(raw, list) else []


def settings_of(row: dict) -> dict:
    """Ajustes del modulo guardados en la fila del piso (valores por defecto si no hay fila)."""
    audience = row.get("quien_ve") if row.get("quien_ve") in AUDIENCES else "dueno_admin"
    lite = row.get("liviano") if row.get("liviano") in LITE_MODES else "auto"
    return {"audience": audience, "roles": _roles_value(row.get("roles_ve")), "tv": row.get("modo_tv") is not False, "lite": lite}


async def save_settings(db: AsyncSession, company_id: str, actor: str, **fields: Any) -> None:
    cols = {"audience": "quien_ve", "roles": "roles_ve", "tv": "modo_tv", "lite": "liviano"}
    values = {cols[k]: (json.dumps(v) if k == "roles" else v) for k, v in fields.items() if k in cols}
    if not values:
        return
    names = list(values)
    rendered = [f"CAST(:{n} AS jsonb)" if n == "roles_ve" else f":{n}" for n in names]
    await db.execute(text(f"""
        INSERT INTO oficina_pisos (company_id, updated_by, {', '.join(names)}) VALUES (CAST(:c AS uuid), :a, {', '.join(rendered)})
        ON CONFLICT (company_id) DO UPDATE SET {', '.join(f'{n} = EXCLUDED.{n}' for n in names)}, updated_by = EXCLUDED.updated_by, updated_at = now()
    """), {"c": company_id, "a": actor[:120], **values})
    await db.commit()


async def set_module(db: AsyncSession, company_id: str, enabled: bool) -> None:
    """Enciende o apaga el modulo de la empresa (crea el modulo en el catalogo si faltara)."""
    mid = (await db.execute(text("SELECT id FROM modules WHERE lower(code) = :code LIMIT 1"), {"code": MODULE_CODE})).scalar()
    if mid is None:
        mid = (await db.execute(text("""
            INSERT INTO modules (id, code, name, description, category, is_active, created_at, updated_at)
            VALUES (gen_random_uuid(), :code, :name, :d, :cat, TRUE, now(), now()) RETURNING id
        """), {"code": MODULE_CODE, "name": MODULE_NAME, "cat": CATEGORY,
               "d": "El cliente ve su negocio en 3D con sus datos reales. Solo su propio piso."})).scalar()
    found = (await db.execute(text("SELECT id FROM company_modules WHERE company_id = CAST(:c AS uuid) AND module_id = :m LIMIT 1"),
                              {"c": company_id, "m": mid})).scalar()
    if found is None:
        await db.execute(text("""
            INSERT INTO company_modules (id, company_id, module_id, enabled, settings, activated_at, created_at, updated_at)
            VALUES (gen_random_uuid(), CAST(:c AS uuid), :m, :e, '{}'::jsonb, now(), now(), now())
        """), {"c": company_id, "m": mid, "e": enabled})
    else:
        await db.execute(text("UPDATE company_modules SET enabled = :e, updated_at = now() WHERE id = :id"), {"e": enabled, "id": found})
    await db.commit()
    forget(company_id)


# ------------------------------------------------------------------ acceso (ticket -> cookie) con re-chequeo
_CHECK: dict[str, tuple[float, bool]] = {}


def forget(company_id: Optional[str] = None) -> None:
    """Vuelve a comprobar el acceso de inmediato (al apagar el modulo o cambiar "Quien lo ve")."""
    if company_id is None:
        _CHECK.clear()
        return
    for k in [k for k in _CHECK if k.startswith(str(company_id))]:
        _CHECK.pop(k, None)


async def recheck(key: str, fn: Callable[[], Awaitable[bool]]) -> bool:
    hit = _CHECK.get(key)
    if hit and time.monotonic() - hit[0] < RECHECK_TTL:
        return hit[1]
    ok = await fn()
    _CHECK[key] = (time.monotonic(), ok)
    return ok


# ------------------------------------------------------------------ copia viva compartida (1 consulta / empresa / 7 s)
_LIVE: dict[str, tuple[float, dict]] = {}
_LOCKS: dict[str, asyncio.Lock] = {}
STATS: dict[str, dict] = {}


def reset() -> None:
    _LIVE.clear()
    _LOCKS.clear()
    STATS.clear()
    _CHECK.clear()
    _SCREENS.clear()
    _BYTES.clear()
    _FLUSHED.clear()
    _PREVIEW_AT.clear()


def drop_live(company_id: str) -> None:
    _LIVE.pop(str(company_id), None)


async def shared_live(company_id: str, build: Callable[[], Awaitable[dict]], ttl: float = LIVE_TTL) -> dict:
    """La copia viva de una empresa: una sola construccion (consultas a la base) por TTL, aunque haya N pantallas
    pidiendo a la vez (las demas esperan la misma)."""
    cid = str(company_id)
    hit = _LIVE.get(cid)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    lock = _LOCKS.setdefault(cid, asyncio.Lock())
    async with lock:
        hit = _LIVE.get(cid)
        if hit and time.monotonic() - hit[0] < ttl:
            return hit[1]
        snap = await build()
        _LIVE[cid] = (time.monotonic(), snap)
        s = STATS.setdefault(cid, {"builds": 0, "first": time.monotonic()})
        s["builds"] += 1
        return snap


# ------------------------------------------------------------------ consumo (pantallas y bytes)
_SCREENS: dict[str, dict[str, float]] = {}
_BYTES: dict[str, int] = {}
_FLUSHED: dict[str, float] = {}
SCREEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,40}$")


def heartbeat(company_id: str, screen: str) -> None:
    if not SCREEN_RE.match(screen or ""):
        return
    now = time.monotonic()
    seen = _SCREENS.setdefault(str(company_id), {})
    seen[screen] = now
    for k in [k for k, t in seen.items() if now - t > SCREEN_WINDOW * 4]:
        seen.pop(k, None)


def screens_now(company_id: str) -> int:
    now = time.monotonic()
    return sum(1 for t in (_SCREENS.get(str(company_id)) or {}).values() if now - t <= SCREEN_WINDOW)


def count_bytes(company_id: str, n: int) -> None:
    if n > 0:
        _BYTES[str(company_id)] = _BYTES.get(str(company_id), 0) + int(n)


def pending_bytes(company_id: str) -> int:
    return _BYTES.get(str(company_id), 0)


def _month(now: Optional[datetime] = None):
    return (now or datetime.now(timezone.utc)).date().replace(day=1)


async def flush(db: AsyncSession, company_id: str, force: bool = False) -> None:
    """Pasa los bytes medidos a live3d_consumo (una fila por empresa y mes). Nunca rompe la respuesta."""
    cid = str(company_id)
    if not force and time.monotonic() - _FLUSHED.get(cid, 0.0) < FLUSH_EVERY:
        return
    delta, peak = _BYTES.pop(cid, 0), screens_now(cid)
    _FLUSHED[cid] = time.monotonic()
    if not delta and not peak:
        return
    try:
        await db.execute(text("""
            INSERT INTO live3d_consumo (company_id, mes, bytes, pantallas_max, updated_at) VALUES (CAST(:c AS uuid), :m, :b, :p, now())
            ON CONFLICT (company_id, mes) DO UPDATE SET bytes = live3d_consumo.bytes + EXCLUDED.bytes,
              pantallas_max = GREATEST(live3d_consumo.pantallas_max, EXCLUDED.pantallas_max), updated_at = now()
        """), {"c": cid, "m": _month(), "b": delta, "p": peak})
        await db.commit()
    except Exception as error:
        import logging

        logging.getLogger("clonexa.live3d").warning("consumo sin guardar (%s: %s)", type(error).__name__, str(error)[:200])
        await db.rollback()
        _BYTES[cid] = _BYTES.get(cid, 0) + delta   # se reintenta en el siguiente


async def usage(db: AsyncSession, company_id: str) -> dict:
    cid = str(company_id)
    row = None
    try:
        row = await _one(db, "SELECT bytes, pantallas_max FROM live3d_consumo WHERE company_id = CAST(:c AS uuid) AND mes = :m",
                         {"c": cid, "m": _month()})
    except Exception:
        await db.rollback()
    month = int((row or {}).get("bytes") or 0) + pending_bytes(cid)
    s = STATS.get(cid)
    per_min = None
    if s and s["builds"] and time.monotonic() - s["first"] >= 60:
        per_min = round(s["builds"] / ((time.monotonic() - s["first"]) / 60.0), 1)
    return {"screens": screens_now(cid), "month_bytes": month, "month_gb": round(month / 1024 ** 3, 3),
            "month_mb": round(month / 1024 ** 2, 1), "peak_screens": int((row or {}).get("pantallas_max") or 0),
            "builds": (s or {}).get("builds", 0), "queries_per_min": per_min}


# ------------------------------------------------------------------ modo arquitecto de los pisos aprobados
# Objetos que se pueden mover en cada plantilla (ademas de las mesas reales de la empresa): la barra del bar queda
# pegada a su pared (la escena aprobada la dibuja con la contrabarra, los taburetes y el paso del personal).
ARCH_FIXED = {"bar": ("dj", "pista", "planta:0", "planta:1", "planta:2"), "restaurante": (), "taller": (), "campo": ()}
ARCH_MACHINES = {"taller": 24}
ARCH_LIMIT = 14.0


def clean_arch(body: Any, template: str, tables: list[str]) -> dict:
    """[x, z, giro] por objeto (mesa:<etiqueta>, maquina:<n> o los fijos de la plantilla), dentro del salon."""
    import math

    if template not in ARCH_FIXED:
        raise ValueError("Este piso no tiene objetos movibles.")
    if not isinstance(body, dict) or not isinstance(body.get("items"), dict):
        raise ValueError("Envía la distribución.")
    if len(body["items"]) > 120:
        raise ValueError("Demasiados objetos.")
    allowed = set(ARCH_FIXED[template]) | {f"maquina:{i}" for i in range(ARCH_MACHINES.get(template, 0))}
    if template in ("bar", "restaurante"):
        allowed |= {f"mesa:{t}" for t in tables}
    out: dict[str, list[float]] = {}
    for key, value in body["items"].items():
        if key not in allowed:
            raise ValueError("La distribución tiene objetos que no son de este piso.")
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            raise ValueError("Posición no válida.")
        try:
            x, z, r = (float(v) for v in value)
        except (TypeError, ValueError):
            raise ValueError("Posición no válida.") from None
        if not all(math.isfinite(v) for v in (x, z, r)):
            raise ValueError("Posición no válida.")
        out[key] = [round(max(-ARCH_LIMIT, min(ARCH_LIMIT, x)), 2), round(max(-ARCH_LIMIT, min(ARCH_LIMIT, z)), 2), round(math.remainder(r, 2 * math.pi), 3)]
    return out


# ------------------------------------------------------------------ vista previa (imagen chica del piso, en el bucket)
_PREVIEW_AT: dict[str, float] = {}


def preview_key(company_id: str) -> str:
    return f"oficina/vivo3d/{uuid.UUID(str(company_id))}/vista.jpg"


def preview_ok(raw: bytes) -> bool:
    return bool(raw) and len(raw) <= PREVIEW_MAX and raw[:3] == b"\xff\xd8\xff"


def preview_due(company_id: str) -> bool:
    return time.monotonic() - _PREVIEW_AT.get(str(company_id), -PREVIEW_EVERY) >= PREVIEW_EVERY


def preview_saved(company_id: str) -> None:
    _PREVIEW_AT[str(company_id)] = time.monotonic()


__all__ = ["role_allowed", "sign", "verify", "link_sig", "shared_live", "heartbeat", "screens_now", "count_bytes", "usage",
           "settings_of", "save_settings", "set_module", "module_enabled"]
