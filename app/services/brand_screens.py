"""Que pantallas del Estudio de marca tiene una empresa (etapa 2).

- Panel principal (/client): siempre (dashboard, vista de modulo e ingreso).
- Restaurante: solo con waiter_ordering encendido; cada panel solo si su
  segmento (mesero, cocina, caja) esta encendido; su ingreso si hay alguno.
- Mini paneles generales: solo si el modulo mini_panel esta encendido y tiene
  al menos un tipo (ventas, tiendas...) encendido.
Una sola consulta, filtrada por company_id.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import brand_theme as bt

PANEL_FLAGS = ("mini_panel_brand", "brand_everywhere")


def _settings(raw: Any) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except ValueError:
            raw = {}
    return raw if isinstance(raw, dict) else {}


def _mini_types(settings: dict) -> list[str]:
    config = settings.get("mini_panel_modules") if isinstance(settings.get("mini_panel_modules"), dict) else (
        settings if isinstance(settings.get("panels"), dict) else {})
    panels = config.get("panels") if isinstance(config.get("panels"), dict) else {}
    known = bt.registry()["mini_types"]
    return [t for t in known if isinstance(panels.get(t), dict) and panels[t].get("enabled") is True]


def compute(modules: dict[str, dict]) -> dict:
    """modules: {code: {"enabled": bool, "settings": dict}} de UNA empresa."""
    wo = modules.get("waiter_ordering") or {}
    wo_on = wo.get("enabled") is True
    wo_settings = _settings(wo.get("settings"))
    segments = wo_settings.get("segments") if isinstance(wo_settings.get("segments"), dict) else {}
    segment_on = {s: wo_on and isinstance(segments.get(s), dict) and segments[s].get("enabled") is True for s in ("mesero", "cocina", "caja")}
    mini = modules.get("mini_panel") or {}
    mini_types = _mini_types(_settings(mini.get("settings"))) if mini.get("enabled") is True else []
    screens = []
    for key, spec in bt.registry()["screens"].items():
        req = spec.get("requires") or {}
        if req.get("module") == "waiter_ordering":
            seg = req.get("segment")
            ok = any(segment_on.values()) if seg == "any" else segment_on.get(seg, False)
        elif req.get("mini_panel"):
            ok = bool(mini_types)
        else:
            ok = True
        if ok:
            screens.append(key)
    return {"screens": screens, "mini_types": mini_types, "segments": segment_on,
            "panels_branded_today": wo_on and any(wo_settings.get(f) is True for f in PANEL_FLAGS)}


async def for_company(db: AsyncSession, company_id: str) -> dict:
    rows = (await db.execute(text("""
        SELECT LOWER(m.code) AS code, cm.enabled, cm.settings
        FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id = CAST(:c AS uuid) AND LOWER(m.code) IN ('waiter_ordering', 'mini_panel')
    """), {"c": company_id})).mappings().all()
    return compute({str(r["code"]): {"enabled": r["enabled"] is True, "settings": r["settings"]} for r in rows})


async def enabled_modules(db: AsyncSession, company_id: str) -> list[dict]:
    """Modulos encendidos (codigo y nombre) para que la vista previa del portal
    muestre el mismo menu y las mismas tarjetas que ve la empresa. Solo la
    configuracion: nunca datos de operacion."""
    rows = (await db.execute(text("""
        SELECT m.code, m.name, m.category FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id = CAST(:c AS uuid) AND cm.enabled IS TRUE ORDER BY m.name
    """), {"c": company_id})).mappings().all()
    return [{"code": str(r["code"]), "name": str(r["name"] or r["code"]), "category": str(r["category"] or "")} for r in rows]
