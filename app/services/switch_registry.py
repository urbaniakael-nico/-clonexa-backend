"""Registro unico de interruptores por empresa y su matriz (Consola v2+).

El registro vive en switch_registry.json: solo lo registrado aparece en la
consola. La matriz lee, con una sola consulta, los modulos de cada empresa no
archivada que algun interruptor necesita, y devuelve por empresa el estado de
cada interruptor (encendido / apagado / bloqueado con el motivo). Nunca devuelve
otras claves de settings: solo las registradas.

Guardar NO pasa por aqui: la consola usa el mismo endpoint de Admin V2
(POST /api/v1/companies/{id}/modules/{code}/activate) con solo la clave
cambiada; el servidor mezcla settings sin tocar las demas claves.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.company_kind import resolve_kind

PATH = Path(__file__).with_name("switch_registry.json")


@lru_cache(maxsize=1)
def registry() -> dict:
    data = json.loads(PATH.read_text(encoding="utf-8"))
    validate(data)
    return data


def validate(data: dict) -> None:
    groups = set(data.get("groups") or [])
    keys = [s["key"] for s in data["switches"]]
    if len(keys) != len(set(keys)):
        raise ValueError("clave de interruptor repetida")
    for s in data["switches"]:
        for field in ("key", "label", "module", "group", "description"):
            if not str(s.get(field) or "").strip():
                raise ValueError(f"{s.get('key')}: falta {field}")
        if s["group"] not in groups:
            raise ValueError(f"{s['key']}: grupo desconocido {s['group']}")
        if s.get("delicate") and not s.get("delicate_reason"):
            raise ValueError(f"{s['key']}: delicado sin motivo")
        for dep in s.get("depends_on") or []:
            if dep.get("key") not in keys or dep.get("key") == s["key"]:
                raise ValueError(f"{s['key']}: depende de un interruptor no registrado")


def required_modules() -> list[str]:
    out: set[str] = set()
    for s in registry()["switches"]:
        out.add(s["module"])
        out.update(s.get("requires_modules") or [])
    return sorted(out)


def _settings(raw: Any) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except ValueError:
            raw = {}
    return raw if isinstance(raw, dict) else {}


def company_state(modules: dict[str, dict]) -> dict[str, dict]:
    """modules: {code: {"enabled": bool, "settings": dict}} de UNA empresa."""
    out: dict[str, dict] = {}
    for s in registry()["switches"]:
        mod = modules.get(s["module"]) or {}
        on = mod.get("enabled") is True and _settings(mod.get("settings")).get(s["key"]) is True
        missing = [code for code in [s["module"], *(s.get("requires_modules") or [])] if (modules.get(code) or {}).get("enabled") is not True]
        out[s["key"]] = {"on": on, "locked": bool(missing), "missing_modules": missing}
    return out


async def matrix(db: AsyncSession) -> dict:
    codes = required_modules()
    rows = (await db.execute(text("""
        SELECT c.id::text AS company_id, c.name, c.slug, c.status, c.settings_json, x.code, x.enabled, x.settings
        FROM companies c
        LEFT JOIN (
            SELECT cm.company_id, m.code, cm.enabled, cm.settings
            FROM company_modules cm JOIN modules m ON m.id = cm.module_id
            WHERE m.code = ANY(:codes)
        ) x ON x.company_id = c.id
        WHERE LOWER(COALESCE(c.status, '')) NOT IN ('archived', 'deleted')
        ORDER BY c.name
    """), {"codes": codes})).mappings().all()
    companies: dict[str, dict] = {}
    for r in rows:
        entry = companies.setdefault(r["company_id"], {
            "id": r["company_id"], "name": r["name"], "slug": r["slug"], "status": r["status"],
            "kind": resolve_kind(r["company_id"], _settings(r["settings_json"])), "modules": {}})
        if r["code"]:
            entry["modules"][r["code"]] = {"enabled": r["enabled"] is True, "settings": _settings(r["settings"])}
    out = []
    for c in companies.values():
        out.append({k: c[k] for k in ("id", "name", "slug", "status", "kind")} | {"switches": company_state(c["modules"])})
    return {"ok": True, "registry": registry(), "companies": out}
