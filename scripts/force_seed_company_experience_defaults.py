import asyncio
import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

try:
    from app.core import database as database_module
except Exception as exc:
    print(f"[ERROR] No se pudo importar app.core.database: {exc}")
    raise


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
    "field": {
        "industry_theme": "field",
        "visual_preset": "field_ops_dark",
        "primary_color": "#1d4ed8",
        "secondary_color": "#00ff88",
        "button_color": "#1d4ed8",
        "status_color": "#00ff88",
    },
    "hospitality": {
        "industry_theme": "hospitality",
        "visual_preset": "hospitality_night_ops",
        "primary_color": "#ef233c",
        "secondary_color": "#ff2bd6",
        "button_color": "#ef233c",
        "status_color": "#ffd166",
    },
    "retail": {
        "industry_theme": "retail",
        "visual_preset": "retail_pastel_performance",
        "primary_color": "#ff1744",
        "secondary_color": "#38bdf8",
        "button_color": "#ff1744",
        "status_color": "#00ff88",
    },
    "production": {
        "industry_theme": "production",
        "visual_preset": "production_neon",
        "primary_color": "#ef233c",
        "secondary_color": "#a1a1aa",
        "button_color": "#ef233c",
        "status_color": "#00ff88",
    },
    "default": {
        "industry_theme": "default",
        "visual_preset": "clonexa_default",
        "primary_color": "#ef233c",
        "secondary_color": "#ff2bd6",
        "button_color": "#ef233c",
        "status_color": "#00ff88",
    },
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


def _database_url() -> str:
    for attr in ("DATABASE_URL", "SQLALCHEMY_DATABASE_URI", "POSTGRES_DSN"):
        value = getattr(database_module, attr, None)
        if value:
            return str(value)
    try:
        from app.core.config import settings
        for attr in ("DATABASE_URL", "SQLALCHEMY_DATABASE_URI", "POSTGRES_DSN"):
            value = getattr(settings, attr, None)
            if value:
                return str(value)
    except Exception:
        pass
    raise RuntimeError("No se encontró DATABASE_URL en app.core.database ni app.core.config.settings")


def _sessionmaker():
    for attr in ("async_session_maker", "AsyncSessionLocal", "SessionLocal", "async_session"):
        factory = getattr(database_module, attr, None)
        if factory is not None:
            return factory
    engine = getattr(database_module, "engine", None) or getattr(database_module, "async_engine", None)
    if engine is None:
        engine = create_async_engine(_database_url(), future=True)
    return async_sessionmaker(engine, expire_on_commit=False)


def _normalize_slug(value: str | None) -> str:
    return (value or "").strip().lower().replace("_", "-")


def detect_engine(company: dict[str, Any]) -> str:
    slug = _normalize_slug(company.get("slug"))
    name = _normalize_slug(company.get("name"))
    return ENGINE_BY_SLUG.get(slug) or ENGINE_BY_SLUG.get(name) or "default"


async def execute(session, sql: str, params: dict[str, Any] | None = None):
    return await session.execute(text(sql), params or {})


async def fetch_companies(session):
    result = await execute(
        session,
        """
        SELECT id::text AS id, name, slug
        FROM companies
        WHERE lower(coalesce(slug, '')) IN ('voltage','radio-despecho','mundo-case','velvet')
           OR lower(coalesce(name, '')) IN ('voltage','radio despecho','mundo case','velvet')
        ORDER BY name
        """
    )
    return [dict(row) for row in result.mappings().all()]


async def seed_branding(session, company_id: str, engine: str):
    branding = BRANDING_BY_ENGINE.get(engine, BRANDING_BY_ENGINE["default"])
    await execute(
        session,
        """
        INSERT INTO company_branding (
            id, company_id, logo_palette_json, primary_color, secondary_color,
            background_color, card_color, text_color, success_color,
            button_color, status_color, theme_mode, industry_theme,
            visual_preset, custom_css_json, created_at, updated_at
        )
        VALUES (
            gen_random_uuid(), CAST(:company_id AS uuid), '{}'::jsonb,
            :primary_color, :secondary_color, '#050505', '#18181b', '#f8fafc',
            '#00ff88', :button_color, :status_color, 'dark',
            :industry_theme, :visual_preset, '{}'::jsonb, now(), now()
        )
        ON CONFLICT (company_id) DO UPDATE SET
            visual_preset = CASE
                WHEN company_branding.visual_preset IS NULL OR company_branding.visual_preset = '' OR company_branding.visual_preset = 'clonexa_default'
                THEN EXCLUDED.visual_preset ELSE company_branding.visual_preset END,
            industry_theme = CASE
                WHEN company_branding.industry_theme IS NULL OR company_branding.industry_theme = '' OR company_branding.industry_theme = 'default'
                THEN EXCLUDED.industry_theme ELSE company_branding.industry_theme END,
            button_color = COALESCE(company_branding.button_color, EXCLUDED.button_color),
            status_color = COALESCE(company_branding.status_color, EXCLUDED.status_color),
            logo_palette_json = COALESCE(company_branding.logo_palette_json, '{}'::jsonb),
            custom_css_json = COALESCE(company_branding.custom_css_json, '{}'::jsonb),
            updated_at = now()
        """,
        {"company_id": company_id, **branding},
    )


async def seed_localization(session, company_id: str):
    await execute(
        session,
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


async def seed_layout(session, company_id: str):
    await execute(
        session,
        """
        INSERT INTO company_crm_layout (
            id, company_id, layout_name, sidebar_enabled, topbar_enabled,
            density, home_view, settings_json, created_at, updated_at
        )
        VALUES (
            gen_random_uuid(), CAST(:company_id AS uuid), 'default', true, true,
            'comfortable', 'launchpad', '{}'::jsonb, now(), now()
        )
        ON CONFLICT (company_id) DO NOTHING
        """,
        {"company_id": company_id},
    )


async def seed_launchpad(session, company_id: str, engine: str):
    data = DEFAULTS.get(engine, DEFAULTS["field"])
    module = data["module"]
    for position, (code, title, route) in enumerate(data["launchpad"], start=1):
        await execute(
            session,
            """
            INSERT INTO company_crm_launchpad_cards (
                id, company_id, module_code, card_code, title_key, subtitle_key,
                icon, route_path, enabled, position, size, action_type,
                settings_json, created_at, updated_at
            )
            VALUES (
                gen_random_uuid(), CAST(:company_id AS uuid), :module_code, :card_code, :title_key,
                NULL, NULL, :route_path, true, :position, 'medium', 'navigate',
                '{}'::jsonb, now(), now()
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


async def seed_widgets(session, company_id: str, engine: str):
    data = DEFAULTS.get(engine, DEFAULTS["field"])
    module = data["module"]
    for position, (code, title) in enumerate(data["widgets"], start=1):
        await execute(
            session,
            """
            INSERT INTO company_crm_widgets (
                id, company_id, module_code, widget_code, title_key, metric_source,
                enabled, position, size, icon, settings_json, created_at, updated_at
            )
            VALUES (
                gen_random_uuid(), CAST(:company_id AS uuid), :module_code, :widget_code, :title_key,
                :metric_source, true, :position, 'medium', NULL, '{}'::jsonb, now(), now()
            )
            ON CONFLICT (company_id, module_code, widget_code) DO NOTHING
            """,
            {
                "company_id": company_id,
                "module_code": module,
                "widget_code": code,
                "title_key": title,
                "metric_source": code,
                "position": position,
            },
        )


async def seed_sections(session, company_id: str, engine: str):
    data = DEFAULTS.get(engine, DEFAULTS["field"])
    module = data["module"]
    for position, (code, title) in enumerate(data["sections"], start=1):
        await execute(
            session,
            """
            INSERT INTO company_crm_sections (
                id, company_id, module_code, section_code, title_key, route_path,
                section_type, enabled, position, icon, settings_json, created_at, updated_at
            )
            VALUES (
                gen_random_uuid(), CAST(:company_id AS uuid), :module_code, :section_code, :title_key,
                NULL, 'page', true, :position, NULL, '{}'::jsonb, now(), now()
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


async def seed_actions(session, company_id: str, engine: str):
    data = DEFAULTS.get(engine, DEFAULTS["field"])
    module = data["module"]
    for position, (code, title) in enumerate(data["actions"], start=1):
        await execute(
            session,
            """
            INSERT INTO company_crm_actions (
                id, company_id, module_code, action_code, title_key, target,
                action_type, enabled, position, icon, settings_json, created_at, updated_at
            )
            VALUES (
                gen_random_uuid(), CAST(:company_id AS uuid), :module_code, :action_code, :title_key,
                NULL, 'navigate', true, :position, NULL, '{}'::jsonb, now(), now()
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


async def seed_field_configs(session, company_id: str, engine: str):
    data = DEFAULTS.get(engine, DEFAULTS["field"])
    module = data["module"]
    for position, (entity, code, label, field_type, required) in enumerate(data["field_configs"], start=1):
        await execute(
            session,
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
                "required": required,
                "position": position,
            },
        )


async def seed_alerts(session, company_id: str, engine: str):
    data = DEFAULTS.get(engine, DEFAULTS["field"])
    module = data["module"]
    for position, (code, message, severity, display_type) in enumerate(data["alerts"], start=1):
        await execute(
            session,
            """
            INSERT INTO company_alert_rules (
                id, company_id, module_code, rule_code, event_type, condition_json,
                display_type, severity, enabled, message_key, settings_json,
                created_at, updated_at
            )
            VALUES (
                gen_random_uuid(), CAST(:company_id AS uuid), :module_code, :rule_code,
                NULL, '{}'::jsonb, :display_type, :severity, true, :message_key,
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


async def seed_company(session, company: dict[str, Any]):
    engine = detect_engine(company)
    if engine == "default":
        print(f"[SKIP] {company.get('name')} no tiene engine reconocido")
        return
    company_id = company["id"]
    await seed_branding(session, company_id, engine)
    await seed_localization(session, company_id)
    await seed_layout(session, company_id)
    await seed_launchpad(session, company_id, engine)
    await seed_widgets(session, company_id, engine)
    await seed_sections(session, company_id, engine)
    await seed_actions(session, company_id, engine)
    await seed_field_configs(session, company_id, engine)
    await seed_alerts(session, company_id, engine)
    print(f"[OK] {company.get('name')} | slug={company.get('slug')} | engine={engine}")


async def main():
    Session = _sessionmaker()
    print("\nCLONEXA CRM BUILDER FORCE SEED DEFAULTS 002-D")
    print("=" * 72)
    async with Session() as session:
        companies = await fetch_companies(session)
        if not companies:
            print("[WARN] No se encontraron empresas objetivo")
            return
        for company in companies:
            await seed_company(session, company)
        await session.commit()
    print("\n[OK] Defaults reales sembrados sin duplicar")


if __name__ == "__main__":
    asyncio.run(main())
