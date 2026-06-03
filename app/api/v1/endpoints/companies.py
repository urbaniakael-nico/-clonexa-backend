from __future__ import annotations

import ipaddress
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.core import Company


router = APIRouter()
ALLOWED_COMPANY_STATUSES = {"active", "inactive", "archived"}
ALLOWED_THEME_MODES = {"dark", "light", "corporate", "classic"}
ALLOWED_BRANDING_FONTS = {"Inter", "Manrope", "Sora", "Space Grotesk", "Rajdhani", "Orbitron", "Poppins", "Montserrat"}
ALLOWED_CARD_STYLES = {
    "glass_premium",
    "neon_border",
    "soft_solid",
    "dark_elevated",
    "classic_panel",
    "flat_dashboard",
    "executive_glass",
}
ALLOWED_BACKGROUND_MODES = {"solid", "gradient", "iridescent"}
ALLOWED_SURFACE_STYLES = {"glass", "soft", "neon", "solid"}
ACCESS_POLICY_SCOPES = {
    "client": "Panel cliente",
    "mini_panel": "Mini paneles",
    "ordering_qr": "QR / ordenar",
}


class CompanyCreateRequest(BaseModel):
    name: str
    slug: str
    timezone: Optional[str] = "America/Bogota"
    status: Optional[str] = "active"
    plan: Optional[str] = "standard"
    settings_json: Optional[Dict[str, Any]] = None


class CompanyStatusRequest(BaseModel):
    status: str


class CompanyOperationalResetRequest(BaseModel):
    dry_run: bool = True
    scopes: Optional[list[str]] = None
    confirm_slug: Optional[str] = None
    confirm_text: Optional[str] = None


class CompanyBrandingRequest(BaseModel):
    logo_url: Optional[str] = ""
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    background_color: Optional[str] = None
    text_color: Optional[str] = None
    visual_preset: Optional[str] = None
    background_style: Optional[str] = None
    background_mode: Optional[str] = None
    surface_style: Optional[str] = None
    font_family: Optional[str] = None
    card_style: Optional[str] = None
    font_family: str | None = None
    card_style: str | None = None
    gradient_from: Optional[str] = None
    gradient_to: Optional[str] = None
    gradient_extra: Optional[str] = None
    gradient_angle: Optional[float] = None
    mode: Optional[str] = None
    theme_mode: Optional[str] = None

    # Compatibility with older/frontend variants
    color_principal: Optional[str] = None
    color_secundario: Optional[str] = None
    color_fondo: Optional[str] = None
    color_texto: Optional[str] = None
    preset_visual: Optional[str] = None

    # Compatibility with existing experience schema variants
    card_color: Optional[str] = None
    button_color: Optional[str] = None
    success_color: Optional[str] = None
    custom_css_json: Optional[Dict[str, Any]] = None



class CompanyClientSettingsRequest(BaseModel):
    language: Optional[str] = None
    currency: Optional[str] = None
    timezone: Optional[str] = None
    inactivity_lock_minutes: Optional[int] = None
    payroll_regular_hours_limit: Optional[float] = None
    payroll: Optional[Dict[str, Any]] = None


class CompanyAccessPolicyRequest(BaseModel):
    enabled: Optional[bool] = False
    scopes: Optional[Dict[str, Dict[str, Any]]] = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _company_columns() -> set[str]:
    try:
        return set(Company.__table__.columns.keys())
    except Exception:
        return set()


def _has_column(name: str) -> bool:
    return name in _company_columns()


def _json_store_column() -> Optional[str]:
    """
    Prefer settings_json because the current CLONEXA core already uses it in the
    company payload. Keep fallbacks to avoid migrations if a previous install used
    a different JSON column name.
    """
    columns = _company_columns()
    for candidate in ("settings_json", "experience_json", "metadata_json", "branding_json"):
        if candidate in columns:
            return candidate
    return None


def _iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _company_payload(company: Company) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "id": str(getattr(company, "id", "")),
        "company_id": str(getattr(company, "id", "")),
        "name": getattr(company, "name", ""),
        "slug": getattr(company, "slug", ""),
        "status": getattr(company, "status", "active"),
        "timezone": getattr(company, "timezone", "America/Bogota"),
        "plan": getattr(company, "plan", None),
        "created_at": _iso(getattr(company, "created_at", None)),
        "updated_at": _iso(getattr(company, "updated_at", None)),
    }
    for optional_field in ("archived_at", "deleted_at", "settings_json", "experience_json", "metadata_json", "branding_json"):
        if hasattr(company, optional_field):
            payload[optional_field] = _iso(getattr(company, optional_field))
    return payload


async def _get_company_or_404(db: AsyncSession, company_id: UUID) -> Company:
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    return company


def _touch_company(company: Company, now: Optional[datetime] = None) -> None:
    now = now or _now()
    if hasattr(company, "updated_at"):
        company.updated_at = now


def _client_ip_from_request(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return ""


def _normalise_ip_entry(value: Any) -> Optional[str]:
    text_value = str(value or "").strip()
    if not text_value:
        return None

    try:
        if "/" in text_value:
            return str(ipaddress.ip_network(text_value, strict=False))
        return str(ipaddress.ip_address(text_value))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"IP o CIDR invalido: {text_value}")


def _normalise_ip_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items = value.replace(",", "\n").splitlines()
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []

    seen: set[str] = set()
    result: list[str] = []
    for item in raw_items:
        normalised = _normalise_ip_entry(item)
        if normalised and normalised not in seen:
            seen.add(normalised)
            result.append(normalised)
    return result


def _default_access_policy() -> Dict[str, Any]:
    return {
        "enabled": False,
        "scopes": {
            code: {
                "label": label,
                "enabled": False,
                "allowed_ips": [],
            }
            for code, label in ACCESS_POLICY_SCOPES.items()
        },
    }


def _normalise_access_policy(raw: Any) -> Dict[str, Any]:
    base = _default_access_policy()
    if not isinstance(raw, dict):
        return base

    base["enabled"] = bool(raw.get("enabled"))
    scopes = raw.get("scopes") if isinstance(raw.get("scopes"), dict) else {}

    for code, label in ACCESS_POLICY_SCOPES.items():
        scope = scopes.get(code) if isinstance(scopes.get(code), dict) else {}
        base["scopes"][code] = {
            "label": label,
            "enabled": bool(scope.get("enabled")),
            "allowed_ips": _normalise_ip_list(scope.get("allowed_ips") or scope.get("ips") or []),
        }

    if raw.get("updated_at"):
        base["updated_at"] = str(raw.get("updated_at"))
    return base


def _read_company_access_policy(company: Company) -> Dict[str, Any]:
    store = _read_json_store(company)
    security = store.get("security") if isinstance(store.get("security"), dict) else {}
    return _normalise_access_policy(security.get("ip_allowlist"))


def _write_company_access_policy(company: Company, payload: CompanyAccessPolicyRequest) -> Dict[str, Any]:
    column = _json_store_column()
    if not column:
        raise HTTPException(
            status_code=500,
            detail="No existe una columna JSON persistente en companies para guardar politica de accesos.",
        )

    store = _read_json_store(company)
    security = dict(store.get("security") or {})
    data = payload.model_dump(exclude_unset=True)
    policy = _normalise_access_policy(data)
    policy["updated_at"] = _now().isoformat()

    security["ip_allowlist"] = policy
    store["security"] = security
    setattr(company, column, store)
    _touch_company(company)
    return policy


def _apply_company_status(company: Company, status: str) -> None:
    normalized = str(status or "").strip().lower()
    if normalized == "deleted":
        normalized = "archived"
    if normalized not in ALLOWED_COMPANY_STATUSES:
        raise HTTPException(status_code=400, detail="Estado inválido. Usa active, inactive o archived.")

    now = _now()
    company.status = normalized
    _touch_company(company, now)

    if normalized == "archived":
        if hasattr(company, "archived_at"):
            company.archived_at = now
        if hasattr(company, "deleted_at"):
            company.deleted_at = now

    if normalized == "active":
        if hasattr(company, "archived_at"):
            company.archived_at = None
        if hasattr(company, "deleted_at"):
            company.deleted_at = None


OPERATIONAL_RESET_SCOPE_LABELS: Dict[str, str] = {
    "commercial": "Comercial",
    "references": "Referencias y produccion",
    "workforce": "Personal, marcaciones y bot",
    "payroll": "Nomina",
    "inventory": "Inventario y materiales",
}


OPERATIONAL_RESET_TABLES: list[dict[str, str]] = [
    {"scope": "commercial", "table": "mini_panel_sales_records", "label": "Ventas / facturas"},
    {"scope": "commercial", "table": "mini_panel_sales_cuts", "label": "Cortes comerciales"},
    {"scope": "commercial", "table": "mini_panel_quotes", "label": "Cotizaciones"},
    {"scope": "commercial", "table": "mini_panel_notes", "label": "Notas y agenda"},
    {"scope": "references", "table": "reference_production_closures", "label": "Cierres de produccion"},
    {"scope": "references", "table": "reference_work_sessions", "label": "Sesiones por referencia"},
    {"scope": "references", "table": "production_archive_snapshots", "label": "Snapshots de produccion"},
    {"scope": "references", "table": "product_references", "label": "Catalogo de referencias"},
    {"scope": "payroll", "table": "payroll_period_items", "label": "Items de nomina"},
    {"scope": "payroll", "table": "payroll_entries", "label": "Entradas de nomina legacy"},
    {"scope": "payroll", "table": "payroll_periods", "label": "Periodos de nomina"},
    {"scope": "inventory", "table": "field_material_movements", "label": "Movimientos de materiales campo"},
    {"scope": "inventory", "table": "field_material_request_items", "label": "Items solicitudes campo"},
    {"scope": "inventory", "table": "field_technician_material_stock", "label": "Stock por tecnico"},
    {"scope": "inventory", "table": "field_material_requests", "label": "Solicitudes campo"},
    {"scope": "inventory", "table": "field_materials", "label": "Materiales campo"},
    {"scope": "inventory", "table": "field_technicians", "label": "Tecnicos campo"},
    {"scope": "inventory", "table": "field_billing_projects", "label": "Proyectos campo"},
    {"scope": "inventory", "table": "material_order_units", "label": "Unidades de orden de materiales"},
    {"scope": "inventory", "table": "material_requests", "label": "Solicitudes de materiales"},
    {"scope": "inventory", "table": "inventory_movements", "label": "Movimientos de inventario"},
    {"scope": "inventory", "table": "inventory_items", "label": "Items de inventario"},
    {"scope": "inventory", "table": "inventory_locations", "label": "Ubicaciones de inventario"},
    {"scope": "workforce", "table": "mini_panel_work_sessions", "label": "Sesiones de trabajo mini panel"},
    {"scope": "workforce", "table": "company_telegram_pending_actions", "label": "Acciones pendientes Telegram"},
    {"scope": "workforce", "table": "company_telegram_user_preferences", "label": "Preferencias usuarios Telegram"},
    {"scope": "workforce", "table": "velvet_bot_v1_pending_actions", "label": "Acciones pendientes bot"},
    {"scope": "workforce", "table": "gps_tracking_sessions", "label": "Sesiones GPS"},
    {"scope": "workforce", "table": "workforce_attendance_events", "label": "Marcaciones"},
    {"scope": "workforce", "table": "workforce_attendance_status", "label": "Estado actual asistencia"},
    {"scope": "workforce", "table": "workforce_personnel_history", "label": "Historial de personal"},
    {"scope": "workforce", "table": "employee_current_status", "label": "Estado actual empleados"},
    {"scope": "workforce", "table": "work_sessions", "label": "Sesiones de trabajo"},
    {"scope": "workforce", "table": "work_events", "label": "Eventos de trabajo"},
    {"scope": "workforce", "table": "bot_users", "label": "Usuarios operativos de bot"},
    {"scope": "workforce", "table": "employee_roles", "label": "Roles asignados a empleados"},
    {"scope": "workforce", "table": "employees", "label": "Personal"},
]


OPERATIONAL_RESET_PRESERVED = [
    "companies",
    "company_modules",
    "company_package_assignments",
    "packages",
    "modules",
    "company_users",
    "company_branding",
    "company_localization",
    "company_crm_layout",
    "company_crm_launchpad_cards",
    "company_crm_widgets",
    "company_crm_sections",
    "company_crm_actions",
    "company_crm_field_configs",
    "company_alert_rules",
    "company_bot_instances",
    "company_settings",
    "company_kpi_panel_config",
]


def _normalise_reset_scopes(scopes: Optional[list[str]]) -> list[str]:
    valid = set(OPERATIONAL_RESET_SCOPE_LABELS.keys())
    requested = [str(item or "").strip().lower() for item in (scopes or [])]
    if not requested or "all" in requested:
        return list(OPERATIONAL_RESET_SCOPE_LABELS.keys())
    selected = [item for item in requested if item in valid]
    if not selected:
        raise HTTPException(status_code=400, detail="Selecciona al menos un alcance valido para el reset.")
    return selected


def _reset_plan(scopes: list[str]) -> list[dict[str, str]]:
    selected = set(scopes)
    seen: set[str] = set()
    plan: list[dict[str, str]] = []
    for item in OPERATIONAL_RESET_TABLES:
        table = item["table"]
        if item["scope"] in selected and table not in seen:
            plan.append(item)
            seen.add(table)
    return plan


async def _table_has_company_id(db: AsyncSession, table_name: str) -> bool:
    result = await db.execute(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
              AND column_name = 'company_id'
            LIMIT 1
            """
        ),
        {"table_name": table_name},
    )
    return result.scalar_one_or_none() is not None


async def _company_table_count(db: AsyncSession, table_name: str, company_id: UUID) -> int:
    if not await _table_has_company_id(db, table_name):
        return 0
    result = await db.execute(
        text(f"SELECT COUNT(*) FROM {table_name} WHERE company_id::text = :company_id"),
        {"company_id": str(company_id)},
    )
    return int(result.scalar_one() or 0)


async def _company_table_delete(db: AsyncSession, table_name: str, company_id: UUID) -> int:
    if not await _table_has_company_id(db, table_name):
        return 0
    result = await db.execute(
        text(f"DELETE FROM {table_name} WHERE company_id::text = :company_id"),
        {"company_id": str(company_id)},
    )
    return int(result.rowcount or 0)


async def _ensure_operational_reset_audit(db: AsyncSession) -> None:
    await db.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto";'))
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS clonexa_company_operational_reset_audit (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id text NOT NULL,
                company_slug text NOT NULL,
                executed boolean NOT NULL DEFAULT false,
                scopes_json jsonb NOT NULL DEFAULT '[]'::jsonb,
                counts_json jsonb NOT NULL DEFAULT '[]'::jsonb,
                total_rows integer NOT NULL DEFAULT 0,
                requested_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )


async def _write_operational_reset_audit(
    db: AsyncSession,
    *,
    company: Company,
    executed: bool,
    scopes: list[str],
    tables: list[dict[str, Any]],
    total_rows: int,
) -> None:
    await _ensure_operational_reset_audit(db)
    await db.execute(
        text(
            """
            INSERT INTO clonexa_company_operational_reset_audit (
                company_id,
                company_slug,
                executed,
                scopes_json,
                counts_json,
                total_rows
            )
            VALUES (
                :company_id,
                :company_slug,
                :executed,
                CAST(:scopes_json AS jsonb),
                CAST(:counts_json AS jsonb),
                :total_rows
            )
            """
        ),
        {
            "company_id": str(company.id),
            "company_slug": str(company.slug),
            "executed": executed,
            "scopes_json": json.dumps(scopes, ensure_ascii=False),
            "counts_json": json.dumps(tables, ensure_ascii=False),
            "total_rows": total_rows,
        },
    )


def _hex_or_default(value: Any, default: str) -> str:
    text = str(value or "").strip()
    if not text:
        return default
    if re_match_hex(text):
        return text.lower()
    raise HTTPException(status_code=400, detail=f"Color inválido: {text}. Usa #RGB o #RRGGBB.")


def re_match_hex(value: str) -> bool:
    import re
    return bool(re.fullmatch(r"#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?", value or ""))


def _default_branding(company: Optional[Company] = None) -> Dict[str, Any]:
    slug = str(getattr(company, "slug", "") or "").lower()
    name = str(getattr(company, "name", "") or "").lower()

    if "voltage" in slug or "voltage" in name:
        return {
            "logo_url": "",
            "primary_color": "#2563eb",
            "secondary_color": "#00ff88",
            "background_color": "#05070a",
            "text_color": "#f8fafc",
            "visual_preset": "field_ops_dark",
            "background_style": "aurora_boreal",
            "mode": "dark",
            "theme_mode": "dark",
        }

    if any(key in slug or key in name for key in ("radio", "despecho", "bar", "hospitality")):
        return {
            "logo_url": "",
            "primary_color": "#f59e0b",
            "secondary_color": "#ef4444",
            "background_color": "#11100c",
            "text_color": "#fff7ed",
            "visual_preset": "hospitality_gold",
            "background_style": "neon_profundo",
            "mode": "dark",
            "theme_mode": "dark",
        }

    if any(key in slug or key in name for key in ("mundo", "case", "retail")):
        return {
            "logo_url": "",
            "primary_color": "#f97316",
            "secondary_color": "#22c55e",
            "background_color": "#09090b",
            "text_color": "#ffffff",
            "visual_preset": "retail_neon",
            "background_style": "holografico",
            "mode": "dark",
            "theme_mode": "dark",
        }

    if "velvet" in slug or "velvet" in name or "production" in slug:
        return {
            "logo_url": "",
            "primary_color": "#ef233c",
            "secondary_color": "#f8fafc",
            "background_color": "#09090b",
            "text_color": "#f8fafc",
            "visual_preset": "production_neon",
            "background_style": "cyber_grid",
            "mode": "dark",
            "theme_mode": "dark",
        }

    return {
        "logo_url": "",
        "primary_color": "#ff2bd6",
        "secondary_color": "#00ff88",
        "background_color": "#050509",
        "text_color": "#f8fafc",
        "visual_preset": "clonexa_dark",
        "background_style": "cyber_grid",
        "mode": "dark",
        "theme_mode": "dark",
    }


def _normalise_branding(raw: Optional[Dict[str, Any]], company: Optional[Company] = None) -> Dict[str, Any]:
    raw = raw or {}
    if "branding" in raw and isinstance(raw.get("branding"), dict):
        raw = raw["branding"]

    custom_css = raw.get("custom_css_json") if isinstance(raw.get("custom_css_json"), dict) else {}
    defaults = _default_branding(company)

    mode = str(raw.get("mode") or raw.get("theme_mode") or defaults["mode"]).strip().lower()
    if mode not in ALLOWED_THEME_MODES:
        raise HTTPException(status_code=400, detail="theme_mode/mode invalido. Usa dark, light, corporate o classic.")

    background_style = (
        raw.get("background_style")
        or custom_css.get("background_style")
        or defaults.get("background_style")
        or "cyber_grid"
    )
    background_mode = str(
        raw.get("background_mode")
        or raw.get("backgroundMode")
        or custom_css.get("background_mode")
        or custom_css.get("backgroundMode")
        or defaults.get("background_mode")
        or "gradient"
    ).strip().lower()
    surface_style = str(
        raw.get("surface_style")
        or raw.get("surfaceStyle")
        or custom_css.get("surface_style")
        or custom_css.get("surfaceStyle")
        or defaults.get("surface_style")
        or "glass"
    ).strip().lower()

    font_family = (
        raw.get("font_family")
        or raw.get("fontFamily")
        or custom_css.get("font_family")
        or custom_css.get("fontFamily")
        or defaults.get("font_family")
        or "Inter"
    )

    card_style = (
        raw.get("card_style")
        or raw.get("cardStyle")
        or custom_css.get("card_style")
        or custom_css.get("cardStyle")
        or defaults.get("card_style")
        or "glass_premium"
    )

    if font_family not in ALLOWED_BRANDING_FONTS:
        font_family = "Inter"

    if card_style not in ALLOWED_CARD_STYLES:
        card_style = "glass_premium"

    if background_mode not in ALLOWED_BACKGROUND_MODES:
        background_mode = "gradient"

    if surface_style not in ALLOWED_SURFACE_STYLES:
        surface_style = "glass"

    try:
        gradient_angle = float(
            raw.get("gradient_angle")
            or raw.get("gradientAngle")
            or custom_css.get("gradient_angle")
            or custom_css.get("gradientAngle")
            or defaults.get("gradient_angle")
            or 135
        )
    except (TypeError, ValueError):
        gradient_angle = 135

    if gradient_angle < 0 or gradient_angle > 360:
        gradient_angle = 135

    primary_color = _hex_or_default(raw.get("primary_color") or raw.get("color_principal") or raw.get("button_color"), defaults["primary_color"])
    secondary_color = _hex_or_default(raw.get("secondary_color") or raw.get("color_secundario") or raw.get("success_color"), defaults["secondary_color"])
    background_color = _hex_or_default(raw.get("background_color") or raw.get("color_fondo"), defaults["background_color"])
    text_color = _hex_or_default(raw.get("text_color") or raw.get("color_texto"), defaults["text_color"])

    branding = {
        "logo_url": str(raw.get("logo_url") or defaults["logo_url"] or "").strip(),
        "primary_color": primary_color,
        "secondary_color": secondary_color,
        "background_color": background_color,
        "text_color": text_color,
        "visual_preset": str(raw.get("visual_preset") or raw.get("preset_visual") or defaults["visual_preset"] or "clonexa_dark").strip(),
        "background_style": str(background_style or "cyber_grid").strip(),
        "background_mode": background_mode,
        "surface_style": surface_style,
        "font_family": font_family,
        "card_style": card_style,
        "gradient_from": _hex_or_default(raw.get("gradient_from") or raw.get("gradientFrom"), primary_color),
        "gradient_to": _hex_or_default(raw.get("gradient_to") or raw.get("gradientTo"), secondary_color),
        "gradient_extra": _hex_or_default(raw.get("gradient_extra") or raw.get("gradientExtra"), background_color),
        "gradient_angle": gradient_angle,
        "mode": mode,
        "theme_mode": mode,
    }
    return branding


def _read_json_store(company: Company) -> Dict[str, Any]:
    column = _json_store_column()
    if not column:
        return {}
    value = getattr(company, column, None)
    if isinstance(value, dict):
        return dict(value)
    return {}


def _read_company_branding(company: Company) -> Dict[str, Any]:
    column = _json_store_column()
    if not column:
        return _default_branding(company)

    value = getattr(company, column, None)

    if column == "branding_json" and isinstance(value, dict):
        return _normalise_branding(value, company)

    store = dict(value) if isinstance(value, dict) else {}
    candidates = [
        store.get("branding"),
        store.get("company_branding"),
        (store.get("experience") or {}).get("branding") if isinstance(store.get("experience"), dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            return _normalise_branding(candidate, company)
    return _default_branding(company)


def _write_company_branding(company: Company, branding: Dict[str, Any]) -> None:
    column = _json_store_column()
    if not column:
        raise HTTPException(
            status_code=500,
            detail="No existe una columna JSON persistente en companies para guardar branding.",
        )

    normalized = _normalise_branding(branding, company)
    now_iso = _now().isoformat()

    if column == "branding_json":
        setattr(company, column, {**normalized, "updated_at": now_iso})
        _touch_company(company)
        return

    current = _read_json_store(company)
    current["branding"] = {**normalized, "updated_at": now_iso}
    current["company_branding"] = {**normalized, "updated_at": now_iso}
    experience = current.get("experience") if isinstance(current.get("experience"), dict) else {}
    experience["branding"] = {**normalized, "updated_at": now_iso}
    current["experience"] = experience

    setattr(company, column, current)
    _touch_company(company)


def _experience_payload(company: Company) -> Dict[str, Any]:
    branding = _read_company_branding(company)
    return {
        "company_id": str(getattr(company, "id", "")),
        "branding": branding,
        "company_branding": branding,
        "localization": _read_client_settings(company),
        "client_settings": _read_client_settings(company),
        "layout": {},
        "launchpad_cards": [],
        "widgets": [],
        "sections": [],
        "actions": [],
        "field_configs": [],
        "alert_rules": [],
    }




def _number_or_default(value: Any, default: float) -> float:
    try:
        number = float(value)
        if number > 0 and number <= 168:
            return number
    except Exception:
        pass
    return default


def _read_client_settings(company: Company) -> Dict[str, Any]:
    store = _read_json_store(company)
    client = store.get("client_settings") if isinstance(store.get("client_settings"), dict) else {}
    payroll = client.get("payroll") if isinstance(client.get("payroll"), dict) else {}

    ordinary_hours = _number_or_default(
        payroll.get("ordinary_hours_limit", client.get("payroll_regular_hours_limit", 48)),
        48,
    )

    return {
        "company_id": str(getattr(company, "id", "")),
        "language": str(client.get("language") or "es"),
        "currency": str(client.get("currency") or "COP"),
        "timezone": str(client.get("timezone") or getattr(company, "timezone", "America/Bogota") or "America/Bogota"),
        "inactivity_lock_minutes": int(client.get("inactivity_lock_minutes") or 30),
        "payroll_regular_hours_limit": ordinary_hours,
        "payroll": {
            "ordinary_hours_limit": ordinary_hours,
        },
    }


def _write_client_settings(company: Company, payload: CompanyClientSettingsRequest) -> Dict[str, Any]:
    column = _json_store_column()
    if not column:
        raise HTTPException(
            status_code=500,
            detail="No existe una columna JSON persistente en companies para guardar ajustes del cliente.",
        )

    store = _read_json_store(company)
    client = dict(store.get("client_settings") or {})
    payroll = dict(client.get("payroll") or {})

    data = payload.model_dump(exclude_unset=True)

    if "language" in data and data.get("language") is not None:
        language = str(data.get("language") or "es").strip().lower()
        client["language"] = language or "es"

    if "currency" in data and data.get("currency") is not None:
        currency = str(data.get("currency") or "COP").strip().upper()
        client["currency"] = currency or "COP"

    if "timezone" in data and data.get("timezone") is not None:
        timezone = str(data.get("timezone") or "America/Bogota").strip()
        client["timezone"] = timezone or "America/Bogota"
        if hasattr(company, "timezone"):
            company.timezone = client["timezone"]

    if "inactivity_lock_minutes" in data and data.get("inactivity_lock_minutes") is not None:
        try:
            minutes = int(data.get("inactivity_lock_minutes") or 30)
        except Exception:
            minutes = 30
        client["inactivity_lock_minutes"] = max(1, min(minutes, 1440))

    payroll_payload = data.get("payroll") if isinstance(data.get("payroll"), dict) else {}
    ordinary_value = data.get("payroll_regular_hours_limit", payroll_payload.get("ordinary_hours_limit"))
    if ordinary_value is not None:
        payroll["ordinary_hours_limit"] = _number_or_default(ordinary_value, 48)
        client["payroll_regular_hours_limit"] = payroll["ordinary_hours_limit"]

    client["payroll"] = payroll
    client["updated_at"] = _now().isoformat()

    store["client_settings"] = client
    setattr(company, column, store)
    _touch_company(company)

    return _read_client_settings(company)


def _normalize_branding_extra_fields(data: dict) -> dict:
    font_family = data.get("font_family") or data.get("fontFamily") or "Inter"
    card_style = data.get("card_style") or data.get("cardStyle") or "glass_premium"

    if font_family not in ALLOWED_BRANDING_FONTS:
        font_family = "Inter"

    if card_style not in ALLOWED_CARD_STYLES:
        card_style = "glass_premium"

    data["font_family"] = font_family
    data["card_style"] = card_style
    return data


@router.get("")
@router.get("/")
async def list_companies(db: AsyncSession = Depends(get_db)) -> list[Dict[str, Any]]:
    order_column = Company.created_at.desc() if _has_column("created_at") else Company.name.asc()
    result = await db.execute(select(Company).order_by(order_column))
    return [_company_payload(company) for company in result.scalars().all()]


@router.post("")
@router.post("/")
async def create_company(payload: CompanyCreateRequest, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    name = str(payload.name or "").strip()
    slug = str(payload.slug or "").strip().lower()
    if not name:
        raise HTTPException(status_code=400, detail="El nombre de la empresa es obligatorio.")
    if not slug:
        raise HTTPException(status_code=400, detail="El slug de la empresa es obligatorio.")

    existing_result = await db.execute(select(Company).where(Company.slug == slug))
    if existing_result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Ya existe una empresa con ese slug.")

    now = _now()
    columns = _company_columns()
    values: Dict[str, Any] = {}
    if "id" in columns:
        values["id"] = uuid4()
    if "name" in columns:
        values["name"] = name
    if "slug" in columns:
        values["slug"] = slug
    if "timezone" in columns:
        values["timezone"] = payload.timezone or "America/Bogota"
    if "status" in columns:
        status = str(payload.status or "active").strip().lower()
        values["status"] = status if status in ALLOWED_COMPANY_STATUSES else "active"
    if "plan" in columns:
        values["plan"] = payload.plan or "standard"
    if "settings_json" in columns:
        values["settings_json"] = payload.settings_json or {}
    if "created_at" in columns:
        values["created_at"] = now
    if "updated_at" in columns:
        values["updated_at"] = now

    company = Company(**values)
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return _company_payload(company)


@router.post("/{company_id}/operational-reset")
async def operational_reset_company(
    company_id: UUID,
    payload: CompanyOperationalResetRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    company = await _get_company_or_404(db, company_id)
    scopes = _normalise_reset_scopes(payload.scopes)
    plan = _reset_plan(scopes)

    tables: list[dict[str, Any]] = []
    for item in plan:
        table_name = item["table"]
        available = await _table_has_company_id(db, table_name)
        rows = await _company_table_count(db, table_name, company_id) if available else 0
        tables.append({
            "scope": item["scope"],
            "scope_label": OPERATIONAL_RESET_SCOPE_LABELS[item["scope"]],
            "table": table_name,
            "label": item["label"],
            "available": available,
            "rows": rows,
        })

    total_rows = sum(int(item["rows"] or 0) for item in tables)
    execute = not payload.dry_run
    expected_text = f"RESET {company.slug}"

    if not execute:
        return {
            "ok": True,
            "dry_run": True,
            "executed": False,
            "company_id": str(company.id),
            "company_slug": company.slug,
            "scopes": scopes,
            "scope_labels": [OPERATIONAL_RESET_SCOPE_LABELS[item] for item in scopes],
            "tables": tables,
            "total_rows": total_rows,
            "preserved": OPERATIONAL_RESET_PRESERVED,
            "confirmation_required": {
                "confirm_slug": company.slug,
                "confirm_text": expected_text,
            },
        }

    confirm_slug = str(payload.confirm_slug or "").strip()
    confirm_text = str(payload.confirm_text or "").strip()
    if confirm_slug != company.slug or confirm_text != expected_text:
        raise HTTPException(
            status_code=400,
            detail=f"Confirmacion invalida. Escribe el slug y la frase exacta: {expected_text}",
        )

    deleted_tables: list[dict[str, Any]] = []
    try:
        for item in plan:
            table_name = item["table"]
            available = await _table_has_company_id(db, table_name)
            deleted = await _company_table_delete(db, table_name, company_id) if available else 0
            deleted_tables.append({
                "scope": item["scope"],
                "scope_label": OPERATIONAL_RESET_SCOPE_LABELS[item["scope"]],
                "table": table_name,
                "label": item["label"],
                "available": available,
                "rows": deleted,
            })

        deleted_total = sum(int(item["rows"] or 0) for item in deleted_tables)
        await _write_operational_reset_audit(
            db,
            company=company,
            executed=True,
            scopes=scopes,
            tables=deleted_tables,
            total_rows=deleted_total,
        )
        _touch_company(company)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return {
        "ok": True,
        "dry_run": False,
        "executed": True,
        "company_id": str(company.id),
        "company_slug": company.slug,
        "scopes": scopes,
        "scope_labels": [OPERATIONAL_RESET_SCOPE_LABELS[item] for item in scopes],
        "tables": deleted_tables,
        "total_rows": sum(int(item["rows"] or 0) for item in deleted_tables),
        "preserved": OPERATIONAL_RESET_PRESERVED,
    }


@router.get("/{company_id}")
async def get_company(company_id: UUID, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    return _company_payload(await _get_company_or_404(db, company_id))


@router.patch("/{company_id}")
async def patch_company(company_id: UUID, payload: CompanyStatusRequest, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    company = await _get_company_or_404(db, company_id)
    _apply_company_status(company, payload.status)
    await db.commit()
    await db.refresh(company)
    return _company_payload(company)


@router.patch("/{company_id}/status")
async def update_company_status(company_id: UUID, payload: CompanyStatusRequest, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    company = await _get_company_or_404(db, company_id)
    _apply_company_status(company, payload.status)
    await db.commit()
    await db.refresh(company)
    return _company_payload(company)


@router.patch("/{company_id}/archive")
async def archive_company(company_id: UUID, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    company = await _get_company_or_404(db, company_id)
    _apply_company_status(company, "archived")
    await db.commit()
    await db.refresh(company)
    return _company_payload(company)


@router.patch("/{company_id}/restore")
async def restore_company(company_id: UUID, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    company = await _get_company_or_404(db, company_id)
    _apply_company_status(company, "active")
    await db.commit()
    await db.refresh(company)
    return _company_payload(company)


@router.delete("/{company_id}")
async def delete_company_as_archive(company_id: UUID, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    company = await _get_company_or_404(db, company_id)
    _apply_company_status(company, "archived")
    await db.commit()
    await db.refresh(company)
    return _company_payload(company)



@router.get("/{company_id}/client-settings")
async def get_company_client_settings(company_id: UUID, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    company = await _get_company_or_404(db, company_id)
    return _read_client_settings(company)


@router.put("/{company_id}/client-settings")
async def update_company_client_settings(
    company_id: UUID,
    payload: CompanyClientSettingsRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    company = await _get_company_or_404(db, company_id)
    result = _write_client_settings(company, payload)
    await db.commit()
    await db.refresh(company)
    return _read_client_settings(company)


@router.get("/{company_id}/access-policy")
async def get_company_access_policy(
    company_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    company = await _get_company_or_404(db, company_id)
    policy = _read_company_access_policy(company)
    return {
        "company_id": str(company.id),
        "current_ip": _client_ip_from_request(request),
        **policy,
    }


@router.put("/{company_id}/access-policy")
async def update_company_access_policy(
    company_id: UUID,
    payload: CompanyAccessPolicyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    company = await _get_company_or_404(db, company_id)
    policy = _write_company_access_policy(company, payload)
    await db.commit()
    await db.refresh(company)
    return {
        "company_id": str(company.id),
        "current_ip": _client_ip_from_request(request),
        **policy,
    }


@router.get("/{company_id}/experience")
async def get_company_experience(company_id: UUID, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    company = await _get_company_or_404(db, company_id)
    return _experience_payload(company)


@router.get("/{company_id}/branding")
async def get_company_branding(company_id: UUID, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    company = await _get_company_or_404(db, company_id)
    branding = _read_company_branding(company)
    return {"company_id": str(company.id), "branding": branding, **branding}


@router.put("/{company_id}/experience/branding")
async def update_company_experience_branding(
    company_id: UUID,
    payload: CompanyBrandingRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    company = await _get_company_or_404(db, company_id)
    _write_company_branding(company, payload.model_dump(exclude_none=True))
    await db.commit()
    await db.refresh(company)
    return _experience_payload(company)


@router.put("/{company_id}/branding")
async def update_company_branding(
    company_id: UUID,
    payload: CompanyBrandingRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    company = await _get_company_or_404(db, company_id)
    _write_company_branding(company, payload.model_dump(exclude_none=True))
    await db.commit()
    await db.refresh(company)
    branding = _read_company_branding(company)
    return {"company_id": str(company.id), "branding": branding, **branding}
