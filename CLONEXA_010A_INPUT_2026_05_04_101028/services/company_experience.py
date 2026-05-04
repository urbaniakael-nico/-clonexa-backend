import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


ENGINE_BY_SLUG = {
    "voltage": "field",
    "radio-despecho": "hospitality",
    "radio_despecho": "hospitality",
    "radio despecho": "hospitality",
    "mundo-case": "retail",
    "mundo_case": "retail",
    "mundo case": "retail",
    "velvet": "production",
}

BRANDING_BY_ENGINE = {
    "field": ("field", "field_ops_dark", "#1d4ed8", "#00ff88"),
    "hospitality": ("hospitality", "hospitality_night_ops", "#ef233c", "#ff2bd6"),
    "retail": ("retail", "retail_pastel_performance", "#ff1744", "#38bdf8"),
    "production": ("production", "production_neon", "#ef233c", "#a1a1aa"),
    "default": ("default", "clonexa_default", "#ef233c", "#ff2bd6"),
}

DEFAULTS = {
    "field": {
        "module": "field",
        "launchpad": [
            ("field_dashboard", "CRM Field", "/client/field/dashboard"),
            ("field_kpis", "KPIs Field", "/client/field/kpis"),
            ("technicians", "Técnicos", "/client/field/technicians"),
            ("gps", "GPS", "/client/field/gps"),
            ("tasks", "Tareas / Solicitudes", "/client/field/tasks"),
            ("inventory_materials", "Inventario / Materiales", "/client/field/inventory"),
            ("payroll_current_period", "Nómina Quincenal", "/client/field/payroll"),
            ("billing", "Billing", "/client/field/billing"),
            ("reports", "Reportes", "/client/field/reports"),
            ("settings", "Configuración", "/client/field/settings"),
        ],
        "widgets": [
            ("active_technicians", "Técnicos activos"),
            ("lunch_technicians", "Técnicos en almuerzo"),
            ("requests_today", "Solicitudes hoy"),
            ("critical_stock", "Stock crítico"),
            ("gross_period", "Bruto corte"),
            ("net_period", "Neto corte"),
            ("latest_labor", "Última labor"),
            ("hours_by_billing", "Horas por billing"),
            ("payroll_estimate", "Nómina proyectada"),
        ],
        "sections": [
            ("technicians", "Técnicos"),
            ("gps_tracking", "GPS / ubicación"),
            ("tasks", "Tareas"),
            ("materials_inventory", "Inventario materiales"),
            ("payroll", "Nómina"),
            ("billing", "Billing"),
            ("reports", "Reportes"),
            ("settings", "Configuración"),
        ],
        "actions": [
            ("add_technician", "Agregar técnico"),
            ("upload_inventory", "Cargar inventario"),
            ("create_task", "Crear tarea"),
            ("view_current_payroll", "Ver nómina actual"),
            ("export_report", "Exportar reporte"),
        ],
        "field_configs": [
            ("technician", "name", "Nombre", "text", True),
            ("technician", "phone", "Teléfono", "phone", False),
            ("technician", "role", "Rol", "select", True),
            ("technician", "hourly_rate_regular", "Valor hora ordinaria", "money", True),
            ("technician", "hourly_rate_extra", "Valor hora extra", "money", True),
            ("technician", "discount_1", "Descuento 1", "money", False),
            ("technician", "discount_2", "Descuento 2", "money", False),
            ("technician", "billing", "Billing asignado", "text", False),
            ("technician", "active", "Activo", "boolean", False),
        ],
        "alerts": [
            ("gps_missing", "field.gps_missing", "warning", "banner"),
            ("technician_out_of_zone", "field.technician_out_of_zone", "danger", "card_alert"),
            ("task_overdue", "field.task_overdue", "warning", "toast"),
        ],
    },
    "hospitality": {
        "module": "hospitality",
        "launchpad": [
            ("barman_panel", "Panel Barman", "/client/hospitality/barman"),
            ("hospitality_kpis", "KPIs Bar", "/client/hospitality/kpis"),
            ("tables", "Mesas", "/client/hospitality/tables"),
            ("orders", "Pedidos", "/client/hospitality/orders"),
            ("inventory", "Inventario", "/client/hospitality/inventory"),
            ("customers_loyalty", "Clientes / Puntos", "/client/hospitality/loyalty"),
            ("qr_whatsapp", "QR / WhatsApp", "/client/hospitality/qr"),
            ("day_closing", "Cierre de día", "/client/hospitality/day-closing"),
            ("settings", "Configuración", "/client/hospitality/settings"),
        ],
        "widgets": [
            ("pending_orders", "Pedidos pendientes"),
            ("preparing_orders", "Pedidos alistando"),
            ("served_orders", "Pedidos entregados"),
            ("closed_tables", "Mesas cerradas"),
            ("open_total", "Total abierto"),
            ("daily_sales", "Ventas del día"),
            ("low_stock", "Stock bajo"),
            ("top_product", "Producto más vendido"),
        ],
        "sections": [
            ("barman_panel", "Panel Barman"),
            ("orders_by_status", "Pedidos por estado"),
            ("tables", "Mesas"),
            ("bar_direct_sale", "Venta directa barra"),
            ("inventory", "Inventario"),
            ("day_closing", "Cierre de día"),
            ("kpis", "Dashboard KPIs"),
            ("qr_tables", "QR mesas"),
            ("whatsapp", "WhatsApp"),
            ("loyalty", "Fidelización"),
        ],
        "actions": [
            ("create_bar_sale", "Crear venta barra"),
            ("open_inventory", "Abrir inventario"),
            ("sync_events", "Sincronizar eventos"),
            ("close_day", "Cerrar día"),
            ("generate_qr", "Generar QR"),
        ],
        "field_configs": [
            ("product", "name", "Producto", "text", True),
            ("product", "price", "Precio", "money", True),
            ("product", "stock", "Stock", "number", False),
            ("table", "table_number", "Mesa", "text", True),
            ("customer", "phone", "Teléfono cliente", "phone", False),
            ("customer", "points", "Puntos", "number", False),
        ],
        "alerts": [
            ("new_order", "hospitality.new_order", "success", "toast"),
            ("low_stock", "hospitality.low_stock", "warning", "card_alert"),
            ("table_not_closed", "hospitality.table_not_closed", "warning", "badge"),
            ("day_closing_pending", "hospitality.day_closing_pending", "danger", "banner"),
        ],
    },
    "retail": {
        "module": "retail",
        "launchpad": [
            ("retail_dashboard", "CRM Retail", "/client/retail/dashboard"),
            ("retail_kpis", "KPIs Retail", "/client/retail/kpis"),
            ("stores", "Tiendas", "/client/retail/stores"),
            ("staff", "Personal", "/client/retail/staff"),
            ("sales", "Ventas", "/client/retail/sales"),
            ("requests", "Solicitudes", "/client/retail/requests"),
            ("warehouse", "Bodega", "/client/retail/warehouse"),
            ("payroll", "Nómina", "/client/retail/payroll"),
            ("commercial_closing", "Cierres", "/client/retail/closing"),
            ("settings", "Configuración", "/client/retail/settings"),
        ],
        "widgets": [
            ("working_staff", "Personal laborando"),
            ("paused_staff", "Personal pausado"),
            ("requests_today", "Solicitudes hoy"),
            ("net_hours_today", "Horas netas hoy"),
            ("monthly_sales", "Total ventas mes"),
            ("best_store", "Mejor tienda"),
            ("best_seller", "Mejor vendedor"),
            ("open_stores", "Tiendas abiertas"),
        ],
        "sections": [
            ("operative_status", "Estado operativo"),
            ("active_staff", "Activos"),
            ("paused_staff", "En pausa"),
            ("areas", "Áreas"),
            ("warehouse", "Bodega"),
            ("sales_design", "Ventas / Diseño"),
            ("stores", "Tiendas"),
            ("recent_requests", "Solicitudes recientes"),
            ("active_store_openings", "Aperturas activas"),
            ("ranking_stores", "Ranking tiendas"),
            ("ranking_sellers", "Ranking vendedores"),
            ("commercial_closing", "Cierre comercial"),
        ],
        "actions": [
            ("open_store", "Abrir tienda"),
            ("create_request", "Crear solicitud"),
            ("register_sale", "Registrar venta"),
            ("close_commercial_day", "Cerrar día comercial"),
            ("export_monthly_report", "Exportar reporte mensual"),
        ],
        "field_configs": [
            ("staff", "name", "Nombre", "text", True),
            ("staff", "phone", "Teléfono", "phone", False),
            ("staff", "role", "Rol", "select", True),
            ("staff", "store", "Tienda", "text", False),
            ("sale", "amount", "Valor venta", "money", True),
            ("request", "detail", "Detalle solicitud", "textarea", True),
        ],
        "alerts": [
            ("store_not_opened", "retail.store_not_opened", "warning", "banner"),
            ("request_pending", "retail.request_pending", "info", "badge"),
            ("commercial_closing_pending", "retail.commercial_closing_pending", "danger", "card_alert"),
        ],
    },
    "production": {
        "module": "production",
        "launchpad": [
            ("production_dashboard", "CRM Producción", "/client/production/dashboard"),
            ("production_kpis", "KPIs Producción", "/client/production/kpis"),
            ("operators", "Operarios", "/client/production/operators"),
            ("references", "Referencias", "/client/production/references"),
            ("production", "Producción", "/client/production"),
            ("payroll_current_period", "Nómina Quincenal", "/client/production/payroll"),
            ("reports", "Reportes", "/client/production/reports"),
            ("settings", "Configuración", "/client/production/settings"),
        ],
        "widgets": [
            ("connected_operators", "Operarios conectados"),
            ("paused_operators", "Operarios en pausa"),
            ("active_production", "Producción activa"),
            ("finished_production", "Producción terminada"),
            ("total_operators", "Total operarios"),
            ("fortnight_hours", "Horas quincenales"),
            ("active_references", "Referencias activas"),
            ("productivity", "Productividad"),
            ("payroll_estimate", "Nómina estimada"),
        ],
        "sections": [
            ("active_operators", "Operarios activos"),
            ("paused_operators", "Operarios en pausa"),
            ("production_by_reference", "Producción por referencia"),
            ("fortnight_by_operator", "Corte por operario"),
            ("fortnight_by_reference", "Corte por referencia"),
            ("payroll_table", "Tabla nómina"),
            ("reports", "Reportes"),
        ],
        "actions": [
            ("add_operator", "Agregar operario"),
            ("create_reference", "Crear referencia"),
            ("register_production", "Registrar producción"),
            ("view_current_payroll", "Ver nómina actual"),
            ("export_production_report", "Exportar reporte producción"),
        ],
        "field_configs": [
            ("operator", "name", "Nombre", "text", True),
            ("operator", "role", "Rol", "select", True),
            ("operator", "active", "Activo", "boolean", False),
            ("reference", "code", "Código referencia", "text", True),
            ("reference", "name", "Nombre referencia", "text", True),
            ("production", "quantity", "Cantidad", "number", True),
        ],
        "alerts": [
            ("production_below_target", "production.production_below_target", "warning", "card_alert"),
            ("shift_not_closed", "production.shift_not_closed", "danger", "banner"),
            ("reference_delayed", "production.reference_delayed", "warning", "toast"),
        ],
    },
}


def _company_id(value: UUID | str) -> str:
    return str(value)


def _normalize_slug(value: str | None) -> str:
    return (value or "").strip().lower().replace("_", "-")


async def _execute(db: AsyncSession, sql: str, params: dict[str, Any] | None = None):
    return await db.execute(text(sql), params or {})


async def _rows(db: AsyncSession, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    result = await _execute(db, sql, params)
    return [dict(row) for row in result.mappings().all()]


async def _one(db: AsyncSession, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    result = await _execute(db, sql, params)
    row = result.mappings().first()
    return dict(row) if row else None


async def _scalar(db: AsyncSession, sql: str, params: dict[str, Any] | None = None):
    result = await _execute(db, sql, params)
    return result.scalar()


async def _table_exists(db: AsyncSession, table_name: str) -> bool:
    exists = await _scalar(db, "SELECT to_regclass(:table_name)", {"table_name": f"public.{table_name}"})
    return bool(exists)


async def _safe_rows(db: AsyncSession, table_name: str, order_by: str, company_id: str) -> list[dict[str, Any]]:
    if not await _table_exists(db, table_name):
        return []
    return await _rows(
        db,
        f"""
        SELECT *
        FROM {table_name}
        WHERE company_id = CAST(:company_id AS uuid)
        ORDER BY {order_by}
        """,
        {"company_id": company_id},
    )


async def _safe_one(db: AsyncSession, table_name: str, company_id: str) -> dict[str, Any]:
    if not await _table_exists(db, table_name):
        return {}
    row = await _one(
        db,
        f"""
        SELECT *
        FROM {table_name}
        WHERE company_id = CAST(:company_id AS uuid)
        LIMIT 1
        """,
        {"company_id": company_id},
    )
    return row or {}


async def _company(db: AsyncSession, company_id: str) -> dict[str, Any] | None:
    return await _one(
        db,
        """
        SELECT id::text AS id, name, slug
        FROM companies
        WHERE id = CAST(:company_id AS uuid)
        """,
        {"company_id": company_id},
    )


async def _detect_engine(db: AsyncSession, company_id: str) -> str:
    if await _table_exists(db, "company_modules"):
        rows = await _rows(
            db,
            """
            SELECT m.code
            FROM company_modules cm
            JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id = CAST(:company_id AS uuid)
              AND cm.enabled = true
            """,
            {"company_id": company_id},
        )
        module_codes = {str(row["code"]).lower() for row in rows}
        for engine in ("field", "hospitality", "retail", "production"):
            if engine in module_codes:
                return engine

    company = await _company(db, company_id)
    if not company:
        return "default"
    slug = _normalize_slug(company.get("slug"))
    name = _normalize_slug(company.get("name"))
    return ENGINE_BY_SLUG.get(slug) or ENGINE_BY_SLUG.get(name) or "default"


async def _insert_branding(db: AsyncSession, company_id: str, engine: str):
    theme, preset, primary, secondary = BRANDING_BY_ENGINE.get(engine, BRANDING_BY_ENGINE["default"])
    await _execute(
        db,
        """
        INSERT INTO company_branding (
            id, company_id, logo_palette_json, primary_color, secondary_color,
            background_color, card_color, text_color, success_color, button_color,
            status_color, theme_mode, industry_theme, visual_preset, custom_css_json,
            created_at, updated_at
        )
        VALUES (
            gen_random_uuid(), CAST(:company_id AS uuid), '{}'::jsonb, :primary_color, :secondary_color,
            '#050505', '#18181b', '#f8fafc', '#00ff88', :primary_color,
            '#00ff88', 'dark', :industry_theme, :visual_preset, '{}'::jsonb,
            now(), now()
        )
        ON CONFLICT (company_id) DO UPDATE SET
            visual_preset = CASE
                WHEN company_branding.visual_preset IS NULL OR company_branding.visual_preset = '' OR company_branding.visual_preset = 'clonexa_default'
                THEN EXCLUDED.visual_preset ELSE company_branding.visual_preset END,
            industry_theme = CASE
                WHEN company_branding.industry_theme IS NULL OR company_branding.industry_theme = '' OR company_branding.industry_theme = 'default'
                THEN EXCLUDED.industry_theme ELSE company_branding.industry_theme END,
            logo_palette_json = COALESCE(company_branding.logo_palette_json, '{}'::jsonb),
            custom_css_json = COALESCE(company_branding.custom_css_json, '{}'::jsonb),
            updated_at = now()
        """,
        {
            "company_id": company_id,
            "industry_theme": theme,
            "visual_preset": preset,
            "primary_color": primary,
            "secondary_color": secondary,
        },
    )


async def _insert_localization(db: AsyncSession, company_id: str):
    await _execute(
        db,
        """
        INSERT INTO company_localization (
            id, company_id, default_language, enabled_languages, labels_json, created_at, updated_at
        )
        VALUES (
            gen_random_uuid(), CAST(:company_id AS uuid), 'es', '["es","en","fr"]'::jsonb, '{}'::jsonb, now(), now()
        )
        ON CONFLICT (company_id) DO NOTHING
        """,
        {"company_id": company_id},
    )


async def _insert_layout(db: AsyncSession, company_id: str):
    await _execute(
        db,
        """
        INSERT INTO company_crm_layout (
            id, company_id, layout_name, sidebar_enabled, topbar_enabled, density,
            home_view, settings_json, created_at, updated_at
        )
        VALUES (
            gen_random_uuid(), CAST(:company_id AS uuid), 'default', true, true,
            'comfortable', 'launchpad', '{}'::jsonb, now(), now()
        )
        ON CONFLICT (company_id) DO NOTHING
        """,
        {"company_id": company_id},
    )


async def _insert_defaults(db: AsyncSession, company_id: str, engine: str):
    data = DEFAULTS.get(engine)
    if not data:
        return
    module = data["module"]

    for position, (code, title, route) in enumerate(data["launchpad"], start=1):
        await _execute(
            db,
            """
            INSERT INTO company_crm_launchpad_cards (
                id, company_id, module_code, card_code, title_key, route_path,
                enabled, position, size, action_type, settings_json, created_at, updated_at
            )
            VALUES (
                gen_random_uuid(), CAST(:company_id AS uuid), :module_code, :card_code, :title_key,
                :route_path, true, :position, 'medium', 'navigate', '{}'::jsonb, now(), now()
            )
            ON CONFLICT (company_id, module_code, card_code) DO NOTHING
            """,
            {
                "company_id": company_id,
                "module_code": module,
                "card_code": code,
                "title_key": title,
                "route_path": route,
                "position": position,
            },
        )

    for position, (code, title) in enumerate(data["widgets"], start=1):
        await _execute(
            db,
            """
            INSERT INTO company_crm_widgets (
                id, company_id, module_code, widget_code, title_key, metric_source,
                enabled, position, size, settings_json, created_at, updated_at
            )
            VALUES (
                gen_random_uuid(), CAST(:company_id AS uuid), :module_code, :widget_code,
                :title_key, :widget_code, true, :position, 'medium', '{}'::jsonb, now(), now()
            )
            ON CONFLICT (company_id, module_code, widget_code) DO NOTHING
            """,
            {
                "company_id": company_id,
                "module_code": module,
                "widget_code": code,
                "title_key": title,
                "position": position,
            },
        )

    for position, (code, title) in enumerate(data["sections"], start=1):
        await _execute(
            db,
            """
            INSERT INTO company_crm_sections (
                id, company_id, module_code, section_code, title_key, section_type,
                enabled, position, settings_json, created_at, updated_at
            )
            VALUES (
                gen_random_uuid(), CAST(:company_id AS uuid), :module_code, :section_code,
                :title_key, 'page', true, :position, '{}'::jsonb, now(), now()
            )
            ON CONFLICT (company_id, module_code, section_code) DO NOTHING
            """,
            {
                "company_id": company_id,
                "module_code": module,
                "section_code": code,
                "title_key": title,
                "position": position,
            },
        )

    for position, (code, title) in enumerate(data["actions"], start=1):
        await _execute(
            db,
            """
            INSERT INTO company_crm_actions (
                id, company_id, module_code, action_code, title_key, action_type,
                enabled, position, settings_json, created_at, updated_at
            )
            VALUES (
                gen_random_uuid(), CAST(:company_id AS uuid), :module_code, :action_code,
                :title_key, 'navigate', true, :position, '{}'::jsonb, now(), now()
            )
            ON CONFLICT (company_id, module_code, action_code) DO NOTHING
            """,
            {
                "company_id": company_id,
                "module_code": module,
                "action_code": code,
                "title_key": title,
                "position": position,
            },
        )

    for position, (entity, code, label, field_type, required) in enumerate(data["field_configs"], start=1):
        await _execute(
            db,
            """
            INSERT INTO company_crm_field_configs (
                id, company_id, module_code, entity_code, field_code, label_key,
                field_type, required, enabled, position, options_json, validation_json,
                settings_json, created_at, updated_at
            )
            VALUES (
                gen_random_uuid(), CAST(:company_id AS uuid), :module_code, :entity_code,
                :field_code, :label_key, :field_type, :required, true, :position,
                '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, now(), now()
            )
            ON CONFLICT (company_id, module_code, entity_code, field_code) DO NOTHING
            """,
            {
                "company_id": company_id,
                "module_code": module,
                "entity_code": entity,
                "field_code": code,
                "label_key": label,
                "field_type": field_type,
                "required": bool(required),
                "position": position,
            },
        )

    for position, (code, message, severity, display_type) in enumerate(data["alerts"], start=1):
        await _execute(
            db,
            """
            INSERT INTO company_alert_rules (
                id, company_id, module_code, rule_code, condition_json, display_type,
                severity, enabled, message_key, settings_json, created_at, updated_at
            )
            VALUES (
                gen_random_uuid(), CAST(:company_id AS uuid), :module_code, :rule_code,
                '{}'::jsonb, :display_type, :severity, true, :message_key,
                '{}'::jsonb, now(), now()
            )
            ON CONFLICT (company_id, module_code, rule_code) DO NOTHING
            """,
            {
                "company_id": company_id,
                "module_code": module,
                "rule_code": code,
                "message_key": message,
                "display_type": display_type,
                "severity": severity,
                "position": position,
            },
        )


async def ensure_company_experience_defaults(db: AsyncSession, company_id: UUID | str) -> dict[str, int | str]:
    company_id_s = _company_id(company_id)
    engine = await _detect_engine(db, company_id_s)

    required_tables = [
        "company_branding",
        "company_localization",
        "company_crm_layout",
        "company_crm_launchpad_cards",
        "company_crm_widgets",
        "company_crm_sections",
        "company_crm_actions",
        "company_crm_field_configs",
        "company_alert_rules",
    ]
    for table_name in required_tables:
        if not await _table_exists(db, table_name):
            return {"engine": engine, "error": f"missing_table:{table_name}"}

    await _insert_branding(db, company_id_s, engine)
    await _insert_localization(db, company_id_s)
    await _insert_layout(db, company_id_s)
    await _insert_defaults(db, company_id_s, engine)
    await db.commit()

    counts = await _counts(db, company_id_s)
    counts["engine"] = engine
    return counts


async def _counts(db: AsyncSession, company_id: str) -> dict[str, int]:
    table_map = {
        "branding": "company_branding",
        "localization": "company_localization",
        "layout": "company_crm_layout",
        "launchpad_cards": "company_crm_launchpad_cards",
        "widgets": "company_crm_widgets",
        "sections": "company_crm_sections",
        "actions": "company_crm_actions",
        "field_configs": "company_crm_field_configs",
        "alert_rules": "company_alert_rules",
    }
    out: dict[str, int] = {}
    for key, table_name in table_map.items():
        if not await _table_exists(db, table_name):
            out[key] = 0
            continue
        out[key] = int(await _scalar(db, f"SELECT COUNT(*) FROM {table_name} WHERE company_id = CAST(:company_id AS uuid)", {"company_id": company_id}) or 0)
    return out


async def get_company_experience(db: AsyncSession, company_id: UUID | str) -> dict[str, Any]:
    company_id_s = _company_id(company_id)
    try:
        await ensure_company_experience_defaults(db, company_id_s)
    except Exception:
        await db.rollback()

    return {
        "branding": await _safe_one(db, "company_branding", company_id_s),
        "localization": await _safe_one(db, "company_localization", company_id_s),
        "layout": await _safe_one(db, "company_crm_layout", company_id_s),
        "launchpad_cards": await _safe_rows(db, "company_crm_launchpad_cards", "position, card_code", company_id_s),
        "widgets": await _safe_rows(db, "company_crm_widgets", "position, widget_code", company_id_s),
        "sections": await _safe_rows(db, "company_crm_sections", "position, section_code", company_id_s),
        "actions": await _safe_rows(db, "company_crm_actions", "position, action_code", company_id_s),
        "field_configs": await _safe_rows(db, "company_crm_field_configs", "position, entity_code, field_code", company_id_s),
        "alert_rules": await _safe_rows(db, "company_alert_rules", "rule_code", company_id_s),
    }


async def update_branding(db: AsyncSession, company_id: UUID | str, payload: dict[str, Any]) -> dict[str, Any]:
    company_id_s = _company_id(company_id)
    allowed = [
        "logo_url", "primary_color", "secondary_color", "background_color", "card_color",
        "text_color", "success_color", "button_color", "status_color", "theme_mode",
        "industry_theme", "visual_preset", "font_family",
    ]
    await ensure_company_experience_defaults(db, company_id_s)
    values = {k: v for k, v in payload.items() if k in allowed}
    if values:
        assignments = ", ".join([f"{key} = :{key}" for key in values])
        values["company_id"] = company_id_s
        await _execute(db, f"UPDATE company_branding SET {assignments}, updated_at = now() WHERE company_id = CAST(:company_id AS uuid)", values)
        await db.commit()
    return await _safe_one(db, "company_branding", company_id_s)


async def update_localization(db: AsyncSession, company_id: UUID | str, payload: dict[str, Any]) -> dict[str, Any]:
    company_id_s = _company_id(company_id)
    await ensure_company_experience_defaults(db, company_id_s)
    values = {
        "company_id": company_id_s,
        "default_language": payload.get("default_language", "es"),
        "enabled_languages": json.dumps(payload.get("enabled_languages", ["es", "en", "fr"])),
    }
    await _execute(
        db,
        """
        UPDATE company_localization
        SET default_language = :default_language,
            enabled_languages = CAST(:enabled_languages AS jsonb),
            updated_at = now()
        WHERE company_id = CAST(:company_id AS uuid)
        """,
        values,
    )
    await db.commit()
    return await _safe_one(db, "company_localization", company_id_s)


COLLECTIONS = {
    "launchpad_cards": {
        "table": "company_crm_launchpad_cards",
        "code": "card_code",
        "fields": ["module_code", "card_code", "title_key", "subtitle_key", "icon", "route_path", "enabled", "position", "size", "action_type"],
        "order": "position, card_code",
    },
    "widgets": {
        "table": "company_crm_widgets",
        "code": "widget_code",
        "fields": ["module_code", "widget_code", "title_key", "metric_source", "enabled", "position", "size", "icon"],
        "order": "position, widget_code",
    },
    "sections": {
        "table": "company_crm_sections",
        "code": "section_code",
        "fields": ["module_code", "section_code", "title_key", "route_path", "section_type", "enabled", "position", "icon"],
        "order": "position, section_code",
    },
    "actions": {
        "table": "company_crm_actions",
        "code": "action_code",
        "fields": ["module_code", "action_code", "title_key", "target", "action_type", "enabled", "position", "icon"],
        "order": "position, action_code",
    },
    "field_configs": {
        "table": "company_crm_field_configs",
        "code": "field_code",
        "fields": ["module_code", "entity_code", "field_code", "label_key", "field_type", "required", "enabled", "position"],
        "order": "position, entity_code, field_code",
    },
    "alert_rules": {
        "table": "company_alert_rules",
        "code": "rule_code",
        "fields": ["module_code", "rule_code", "event_type", "display_type", "severity", "enabled", "message_key"],
        "order": "rule_code",
    },
}


async def list_collection(db: AsyncSession, company_id: UUID | str, collection: str) -> list[dict[str, Any]]:
    cfg = COLLECTIONS[collection]
    return await _safe_rows(db, cfg["table"], cfg["order"], _company_id(company_id))


async def create_collection_item(db: AsyncSession, company_id: UUID | str, collection: str, payload: dict[str, Any]) -> dict[str, Any]:
    cfg = COLLECTIONS[collection]
    company_id_s = _company_id(company_id)
    await ensure_company_experience_defaults(db, company_id_s)
    values = {field: payload.get(field) for field in cfg["fields"]}
    values["company_id"] = company_id_s
    for boolean_field in ("enabled", "required"):
        if boolean_field in values and values[boolean_field] is None:
            values[boolean_field] = True if boolean_field == "enabled" else False
    if values.get("position") is None:
        values["position"] = 0
    columns = ["id", "company_id", *values.keys()]
    insert_columns = ["id", *[c for c in columns if c != "id"]]
    placeholders = ["gen_random_uuid()", *[f":{c}" for c in insert_columns if c != "id"]]
    sql = f"""
        INSERT INTO {cfg['table']} ({', '.join(insert_columns)}, settings_json, created_at, updated_at)
        VALUES ({', '.join(placeholders)}, '{{}}'::jsonb, now(), now())
        RETURNING *
    """
    result = await _execute(db, sql, values)
    await db.commit()
    return dict(result.mappings().first())


async def update_collection_item(db: AsyncSession, company_id: UUID | str, collection: str, item_id: UUID | str, payload: dict[str, Any]) -> dict[str, Any] | None:
    cfg = COLLECTIONS[collection]
    values = {field: payload.get(field) for field in cfg["fields"] if field in payload}
    if not values:
        return await _one(db, f"SELECT * FROM {cfg['table']} WHERE id = CAST(:item_id AS uuid) AND company_id = CAST(:company_id AS uuid)", {"item_id": str(item_id), "company_id": _company_id(company_id)})
    values["item_id"] = str(item_id)
    values["company_id"] = _company_id(company_id)
    assignments = ", ".join([f"{key} = :{key}" for key in values if key not in {"item_id", "company_id"}])
    result = await _execute(
        db,
        f"""
        UPDATE {cfg['table']}
        SET {assignments}, updated_at = now()
        WHERE id = CAST(:item_id AS uuid)
          AND company_id = CAST(:company_id AS uuid)
        RETURNING *
        """,
        values,
    )
    await db.commit()
    row = result.mappings().first()
    return dict(row) if row else None


async def delete_collection_item(db: AsyncSession, company_id: UUID | str, collection: str, item_id: UUID | str) -> dict[str, Any]:
    cfg = COLLECTIONS[collection]
    await _execute(
        db,
        f"DELETE FROM {cfg['table']} WHERE id = CAST(:item_id AS uuid) AND company_id = CAST(:company_id AS uuid)",
        {"item_id": str(item_id), "company_id": _company_id(company_id)},
    )
    await db.commit()
    return {"ok": True, "deleted": str(item_id)}
