"""Roles de empleado por empresa (capa B: Employee.role).

- El registro unico vive en role_catalog.json: codigo interno, nombre por
  defecto y que permite cada rol. Los permisos salen SIEMPRE del codigo.
- Cada empresa puede elegir que roles usa y un nombre visible propio:
  company_modules.settings del modulo workforce, clave employee_roles =
  {"roles": [{"code": "gerencia", "label": "Director"}, ...]}.
- Empresa sin esa clave (todas hoy salvo Urbania) = None: el selector, el bot
  y los reportes siguen exactamente como antes.
- Apagar un rol nunca cambia el rol de los empleados que ya lo tienen: quedan
  marcados "rol no habilitado" en la pantalla.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

PATH = Path(__file__).with_name("role_catalog.json")
MODULE = "workforce"
KEY = "employee_roles"
LABEL_MAX = 40
ROLE_KEYS = ("role", "employee_role")


class Invalid(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


@lru_cache(maxsize=1)
def catalog() -> dict:
    data = json.loads(PATH.read_text(encoding="utf-8"))
    codes = [r["code"] for r in data["roles"]]
    if len(codes) != len(set(codes)):
        raise ValueError("codigo de rol repetido")
    for role in data["roles"]:
        if not re.fullmatch(r"[a-z_]{2,40}", role["code"]) or not str(role.get("label") or "").strip():
            raise ValueError(f"rol mal definido: {role.get('code')}")
        if not role.get("permits"):
            raise ValueError(f"{role['code']}: falta permits")
    return data


def codes() -> list[str]:
    return [r["code"] for r in catalog()["roles"]]


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _settings(raw: Any) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except ValueError:
            raw = {}
    return raw if isinstance(raw, dict) else {}


def parse_config(settings: Any) -> dict | None:
    """La configuracion guardada, limpia y en el orden del registro; None si no hay."""
    raw = _settings(settings).get(KEY)
    if not isinstance(raw, dict) or not isinstance(raw.get("roles"), list):
        return None
    known = {r["code"]: r for r in catalog()["roles"]}
    picked: dict[str, str] = {}
    for item in raw["roles"]:
        if not isinstance(item, dict):
            continue
        code = norm(item.get("code"))
        if code in known and code not in picked:
            picked[code] = str(item.get("label") or "").strip()[:LABEL_MAX] or known[code]["label"]
    if not picked:
        return None
    return {"roles": [{"code": c, "label": picked[c]} for c in codes() if c in picked],
            "updated_at": raw.get("updated_at")}


def validate_body(body: Any) -> dict:
    """Cuerpo de la consola -> configuracion a guardar. Al menos un rol."""
    if not isinstance(body, dict) or not isinstance(body.get("roles"), list):
        raise Invalid("roles", "Envía la lista de roles.")
    known = {r["code"]: r for r in catalog()["roles"]}
    out: dict[str, str] = {}
    for item in body["roles"]:
        if not isinstance(item, dict):
            raise Invalid("roles", "Rol inválido.")
        code = str(item.get("code") or "").strip()
        if code not in known:
            raise Invalid("roles", f"El rol {code or '(vacío)'} no está en el registro.")
        if item.get("enabled") is False:
            continue
        label = re.sub(r"\s+", " ", str(item.get("label") or "")).strip()
        if len(label) > LABEL_MAX:
            raise Invalid(f"label:{code}", f"El nombre visible de {known[code]['label']} es muy largo (máximo {LABEL_MAX}).")
        out[code] = label or known[code]["label"]
    if not out:
        raise Invalid("roles", "La empresa debe usar al menos un rol.")
    labels = [v.lower() for v in out.values()]
    if len(labels) != len(set(labels)):
        raise Invalid("roles", "Dos roles no pueden tener el mismo nombre visible.")
    return {"roles": [{"code": c, "label": out[c]} for c in codes() if c in out],
            "updated_at": datetime.now(timezone.utc).isoformat()}


def labels(config: dict | None) -> dict[str, str]:
    return {r["code"]: r["label"] for r in (config or {}).get("roles") or []}


def display(config: dict | None, raw_role: Any) -> str:
    """Nombre visible de un rol; sin configuracion (o rol fuera de ella) el texto de siempre."""
    raw = "" if raw_role is None else str(raw_role)
    if not config:
        return raw
    return labels(config).get(norm(raw), raw)


def relabel(payload: Any, config: dict | None) -> Any:
    """Cambia, en una respuesta ya armada, los valores de role/employee_role por
    el nombre visible. Sin configuracion devuelve el mismo objeto intacto."""
    if not config:
        return payload
    names = labels(config)

    def walk(value: Any) -> Any:
        if isinstance(value, dict):
            out = {}
            for key, item in value.items():
                if key in ROLE_KEYS and isinstance(item, str):
                    out[key] = names.get(norm(item), item)
                else:
                    out[key] = walk(item)
            return out
        if isinstance(value, list):
            return [walk(item) for item in value]
        return value

    return walk(payload)


# ----------------------------------------------------------------- base ---
async def load_config(db: AsyncSession, company_id: Any) -> dict | None:
    """Configuracion de UNA empresa; None si no tiene (o si algo falla: nunca rompe la pantalla)."""
    try:
        row = (await db.execute(text("""
            SELECT cm.settings
            FROM company_modules cm JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id = CAST(:company_id AS uuid) AND m.code = :module
            LIMIT 1
        """), {"company_id": str(company_id), "module": MODULE})).mappings().first()
        return parse_config(row["settings"]) if row else None
    except Exception:
        return None


async def role_counts(db: AsyncSession, company_id: Any) -> dict[str, int]:
    """Empleados no archivados por codigo de rol (normalizado)."""
    result = await db.execute(text("""
        SELECT COALESCE(NULLIF(role, ''), employee_type, '') AS role, COUNT(*)::int AS total
        FROM employees
        WHERE company_id = CAST(:company_id AS uuid)
          AND LOWER(COALESCE(status, 'active')) NOT IN ('archived', 'archivado')
        GROUP BY 1
    """), {"company_id": str(company_id)})
    out: dict[str, int] = {}
    for row in result.mappings().all():
        key = norm(row["role"])
        out[key] = out.get(key, 0) + int(row["total"] or 0)
    return out


async def save_config(db: AsyncSession, company_id: Any, config: dict) -> bool:
    """Mezcla la clave en settings del modulo workforce de ESA empresa (no toca las demas claves).
    False si la empresa no tiene el modulo workforce."""
    result = await db.execute(text("""
        UPDATE company_modules cm
           SET settings = COALESCE(cm.settings, '{}'::jsonb) || jsonb_build_object(CAST(:key AS text), CAST(:value AS jsonb)),
               updated_at = now()
          FROM modules m
         WHERE m.id = cm.module_id AND m.code = :module AND cm.company_id = CAST(:company_id AS uuid)
    """), {"company_id": str(company_id), "module": MODULE, "key": KEY, "value": json.dumps(config, ensure_ascii=False)})
    await db.commit()
    return bool(getattr(result, "rowcount", 0))


def view(config: dict | None, counts: dict[str, int]) -> dict:
    """Lo que ve la consola: todos los roles del registro con su estado en la empresa."""
    names = labels(config)
    roles = []
    for role in catalog()["roles"]:
        code = role["code"]
        roles.append({**role, "enabled": (code in names) if config else True,
                      "visible_label": names.get(code, role["label"]), "employees": counts.get(code, 0)})
    known = set(codes())
    outside = {code: n for code, n in counts.items() if code and code not in known}
    return {"configured": bool(config), "roles": roles, "common": catalog().get("common") or [],
            "unknown_roles": outside, "updated_at": (config or {}).get("updated_at")}


def client_view(config: dict | None) -> dict:
    """Lo que necesita el portal: None = como siempre; si no, la lista corta en orden."""
    if not config:
        return {"configured": False, "roles": []}
    return {"configured": True, "roles": [{"code": r["code"], "label": r["label"]} for r in config["roles"]]}


def allowed_change(config: dict | None, new_role: Any, old_role: Any = None) -> bool:
    """Guardar un empleado: con configuracion solo se acepta un rol habilitado,
    o el mismo rol que ya tenia (un rol apagado no se cambia solo)."""
    if not config:
        return True
    new = norm(new_role)
    if new in labels(config):
        return True
    return old_role is not None and new == norm(old_role)
