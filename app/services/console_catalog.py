"""Datos de solo lectura para Catalogo y Salud de la Consola v2+.

- catalog_usage: cuantas empresas usan cada paquete y, por modulo, en que
  paquetes esta y en cuantas empresas esta encendido (pocas consultas
  agregadas, nunca una por empresa). Sirve tambien para los candidatos a
  limpieza: modulos sin ninguna empresa (en cualquier estado) ni paquete,
  la misma regla de Admin V2 (cxModuleCanDelete025T).
- security_status: que variables de seguridad estan definidas (SIN mostrar
  valores), el cierre automatico de sesiones y un ESTIMADO de endpoints de
  /api/v1 sin sesion, calculado leyendo las dependencias de las rutas en
  memoria (no hace ninguna peticion ni toca la base).
"""
from __future__ import annotations

import os
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _exists(db: AsyncSession, table: str) -> bool:
    return bool((await db.execute(text("SELECT to_regclass(:n) IS NOT NULL"), {"n": f"public.{table}"})).scalar())


async def catalog_usage(db: AsyncSession) -> dict:
    packages: dict[str, dict[str, Any]] = {}
    modules: dict[str, dict[str, Any]] = {}
    if await _exists(db, "company_package_assignments"):
        for r in (await db.execute(text("""
            SELECT a.package_id::text AS package_id,
                   COUNT(DISTINCT a.company_id) FILTER (WHERE LOWER(COALESCE(a.status, '')) = 'active'
                       AND LOWER(COALESCE(c.status, '')) NOT IN ('archived', 'deleted')) AS companies
            FROM company_package_assignments a JOIN companies c ON c.id = a.company_id
            GROUP BY a.package_id
        """))).mappings().all():
            packages[r["package_id"]] = {"companies": int(r["companies"] or 0)}
    if await _exists(db, "company_modules"):
        for r in (await db.execute(text("""
            SELECT m.code,
                   COUNT(DISTINCT cm.company_id) FILTER (WHERE cm.enabled IS TRUE
                       AND LOWER(COALESCE(c.status, '')) NOT IN ('archived', 'deleted')) AS companies_on,
                   COUNT(DISTINCT cm.company_id) AS companies_any
            FROM modules m
            LEFT JOIN company_modules cm ON cm.module_id = m.id
            LEFT JOIN companies c ON c.id = cm.company_id
            GROUP BY m.code
        """))).mappings().all():
            modules[str(r["code"])] = {"companies_on": int(r["companies_on"] or 0), "companies_any": int(r["companies_any"] or 0), "packages": []}
    if await _exists(db, "package_modules"):
        for r in (await db.execute(text("""
            SELECT m.code, p.code AS package_code, p.name AS package_name
            FROM package_modules pm JOIN modules m ON m.id = pm.module_id JOIN packages p ON p.id = pm.package_id
            ORDER BY p.name
        """))).mappings().all():
            entry = modules.setdefault(str(r["code"]), {"companies_on": 0, "companies_any": 0, "packages": []})
            entry["packages"].append({"code": r["package_code"], "name": r["package_name"]})
    for entry in modules.values():
        entry["cleanup_candidate"] = entry["companies_any"] == 0 and not entry["packages"]
    return {"ok": True, "packages": packages, "modules": modules}


# Variables de seguridad: solo si estan definidas, nunca el valor.
SECURITY_VARS = (
    ("CLONEXA_ADMIN_V2_PASSWORD_BCRYPT", "Clave del acceso maestro (bcrypt)"),
    ("CLONEXA_ADMIN_V2_SECRET", "Firma de la cookie de Admin V2 (si falta, usa JWT_SECRET_KEY)"),
    ("JWT_SECRET_KEY", "Firma de los tokens del portal y los mini paneles"),
    ("DATABASE_URL", "Conexion a la base de datos"),
    ("CLONEXA_SESSION_IDLE_HOURS", "Cierre automatico de sesiones sin actividad"),
)
_AUTH_HINT = re.compile(r"require|session|auth|current_user|current_company|admin|tenant|owner_only|token|guard", re.IGNORECASE)


def _route_has_auth(route: Any) -> bool:
    stack = list(getattr(getattr(route, "dependant", None), "dependencies", []) or [])
    while stack:
        dep = stack.pop()
        name = getattr(getattr(dep, "call", None), "__name__", "")
        if _AUTH_HINT.search(name):
            return True
        stack.extend(getattr(dep, "dependencies", []) or [])
    endpoint = getattr(route, "endpoint", None)
    try:
        import inspect

        source = inspect.getsource(endpoint)
    except (OSError, TypeError):
        return False
    body = source.split(":", 1)[-1]
    return bool(re.search(r"_valid_session\(|_active_session\(|_require_admin|require_company_user|_admin_required\(|"
                          r"require_admin_v2|validate_access_session|get_current_company_user|_require_[a-z_]*session", body))


def open_endpoints_estimate(app: Any) -> dict:
    """Estimado informativo: rutas /api/v1 sin una dependencia o chequeo de sesion visible."""
    open_routes: list[str] = []
    total = 0
    for route in getattr(app, "routes", []):
        path = str(getattr(route, "path", ""))
        if not path.startswith("/api/v1/") or not getattr(route, "methods", None):
            continue
        total += 1
        if not _route_has_auth(route):
            for method in sorted(route.methods):
                open_routes.append(f"{method} {path}")
    by_area: dict[str, int] = {}
    for item in open_routes:
        area = item.split(" ", 1)[1].split("/")[3] if item.count("/") >= 3 else "otros"
        by_area[area] = by_area.get(area, 0) + 1
    return {"estimate": True, "routes_checked": total, "open": len(open_routes),
            "by_area": dict(sorted(by_area.items(), key=lambda kv: -kv[1])[:15])}


async def security_status(db: AsyncSession, app: Any, *, master_access_mode: str) -> dict:
    from app.services import session_idle

    variables = [{"name": name, "label": label, "present": bool(os.getenv(name, "").strip())} for name, label in SECURITY_VARS]
    if not any(v["present"] for v in variables if v["name"] == "JWT_SECRET_KEY"):
        # El proyecto acepta SECRET_KEY o CLONEXA_JWT_SECRET como alternativas.
        alt = bool(os.getenv("SECRET_KEY", "").strip() or os.getenv("CLONEXA_JWT_SECRET", "").strip())
        for v in variables:
            if v["name"] == "JWT_SECRET_KEY":
                v["present"] = alt
                v["label"] += " (o SECRET_KEY)"
    idle: dict[str, Any] = {"hours": session_idle.idle_hours(), "raw_present": bool(os.getenv(session_idle.ENV, "").strip()),
                            "reason": session_idle.REASON, "last_run_at": None, "last_run_closed": 0, "closed_7d": 0}
    if await _exists(db, "clonexa_access_sessions"):
        last = (await db.execute(text("""
            SELECT closed_at, COUNT(*) AS n FROM clonexa_access_sessions
            WHERE closed_reason = :reason GROUP BY closed_at ORDER BY closed_at DESC LIMIT 1
        """), {"reason": session_idle.REASON})).mappings().first()
        if last:
            idle["last_run_at"] = last["closed_at"].isoformat() if last["closed_at"] else None
            idle["last_run_closed"] = int(last["n"] or 0)
        idle["closed_7d"] = int((await db.execute(text("""
            SELECT COUNT(*) FROM clonexa_access_sessions
            WHERE closed_reason = :reason AND closed_at >= NOW() - INTERVAL '7 days'
        """), {"reason": session_idle.REASON})).scalar() or 0)
    return {"ok": True, "master_access_mode": master_access_mode, "variables": variables, "session_idle": idle,
            "open_endpoints": open_endpoints_estimate(app)}
