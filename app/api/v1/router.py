from importlib import import_module

from fastapi import APIRouter

api_router = APIRouter()


def _include(module_name: str, prefix: str, tags: list[str]) -> None:
    try:
        module = import_module(f"app.api.v1.endpoints.{module_name}")
    except Exception:
        return
    router = getattr(module, "router", None)
    if router is None:
        return
    api_router.include_router(router, prefix=prefix, tags=tags)


for _module_name, _prefix, _tags in [
    ("companies", "/companies", ["companies"]),
    ("employees", "/employees", ["employees"]),
    ("events", "/events", ["events"]),
    ("shifts", "/shifts", ["shifts"]),
    ("crm", "/crm", ["crm"]),
    ("payroll", "/payroll", ["payroll"]),
    ("gps", "/gps", ["gps"]),
    ("inventory", "/inventory", ["inventory"]),
    ("materials", "/materials", ["materials"]),
    ("materials_webapp", "/materials-webapp", ["materials_webapp"]),
    ("kpis", "/kpis", ["kpis"]),
    ("reports", "/reports", ["reports"]),
    ("bots", "/bots", ["bots"]),
    ("modules", "/modules", ["modules"]),
    ("packages", "/packages", ["packages"]),
    ("company_modules", "/companies", ["company_modules"]),
    ("company_experience", "/companies", ["company_experience"]),
    ("auth", "/auth", ["auth"]),
    ("company_users", "/companies", ["company_users"]),
    ("mini_panel_notes", "/mini-panel-notes", ["mini_panel_notes"]),
    ("mini_panel_quotes", "/mini-panel-quotes", ["mini_panel_quotes"]),
    ("mini_panel_sales", "/mini-panel-sales", ["mini_panel_sales"]),
    ("mini_panel_requests", "/mini-panel-requests", ["mini_panel_requests"]),
    ("day_closing", "/day-closing", ["day_closing"]),
    ("hospitality", "/hospitality", ["hospitality"]),
    ("field", "/field", ["field"]),
    ("landing_analytics", "/landing-analytics", ["landing_analytics"]),
    ("assemblies", "/assemblies", ["assemblies"]),
    ("shoplink", "/shoplink", ["shoplink"]),
    ("transport_calls", "/transport-calls", ["transport_calls"]),
    ("transport_telephony", "/transport-telephony", ["transport_telephony"]),
    ("transport_contracts", "/transport-contracts", ["transport_contracts"]),
    ("transport_quotes_tickets", "/transport-quotes-tickets", ["transport_quotes_tickets"]),
    ("transport_payments", "/transport-payments", ["transport_payments"]),
]:
    _include(_module_name, _prefix, _tags)

# CLONEXA 020B core settings router
from app.api.v1.endpoints import core_settings as core_settings_router
api_router.include_router(core_settings_router.router, prefix="/companies", tags=["core_settings"])











# CLONEXA References V1 router
from app.api.v1.endpoints import references_v1 as references_v1_router
api_router.include_router(references_v1_router.router, prefix="/references-v1", tags=["references_v1"])


# CLONEXA Bot Flow V1 router
from app.api.v1.endpoints import bot_flow_v1 as bot_flow_v1_router
api_router.include_router(bot_flow_v1_router.router, prefix="/bot-flow-v1", tags=["bot_flow_v1"])


# CLONEXA Velvet Bot V1 router
from app.api.v1.endpoints import velvet_bot_v1 as velvet_bot_v1_router
api_router.include_router(velvet_bot_v1_router.router, prefix="/velvet-bot-v1", tags=["velvet_bot_v1"])


# CLONEXA Company Bots V1 router
from app.api.v1.endpoints import company_bots_v1 as company_bots_v1_router
api_router.include_router(company_bots_v1_router.router, prefix="/company-bots-v1", tags=["company_bots_v1"])


# CLONEXA Module Catalog V1 router
from app.api.v1.endpoints import module_catalog_v1 as module_catalog_v1_router
api_router.include_router(module_catalog_v1_router.router, prefix="/module-catalog-v1", tags=["module_catalog_v1"])


# CLONEXA Adaptive Reports V1 router
from app.api.v1.endpoints import adaptive_reports_v1 as adaptive_reports_v1_router
api_router.include_router(adaptive_reports_v1_router.router, prefix="/adaptive-reports-v1", tags=["adaptive_reports_v1"])


# CLONEXA Adaptive KPIs V1 router
from app.api.v1.endpoints import adaptive_kpis_v1 as adaptive_kpis_v1_router
api_router.include_router(adaptive_kpis_v1_router.router, prefix="/adaptive-kpis-v1", tags=["adaptive_kpis_v1"])


# CLONEXA Adaptive KPI Panel V1 router
from app.api.v1.endpoints import adaptive_kpis_panel_v1 as adaptive_kpis_panel_v1_router
api_router.include_router(adaptive_kpis_panel_v1_router.router, prefix="/adaptive-kpis-panel-v1", tags=["adaptive_kpis_panel_v1"])


# CLONEXA Adaptive Reports Detail V1 router
from app.api.v1.endpoints import adaptive_reports_detail_v1 as adaptive_reports_detail_v1_router
api_router.include_router(adaptive_reports_detail_v1_router.router, prefix="/adaptive-reports-detail-v1", tags=["adaptive_reports_detail_v1"])


# CLONEXA Production V1 router
from app.api.v1.endpoints import production_v1 as production_v1_router
api_router.include_router(production_v1_router.router, prefix="/production-v1", tags=["production_v1"])


# CLONEXA CRM Live V1 router
from app.api.v1.endpoints import crm_live_v1 as crm_live_v1_router
api_router.include_router(crm_live_v1_router.router, prefix="/crm-live-v1", tags=["crm_live_v1"])


# CLONEXA CRM Core V1 router
from app.api.v1.endpoints import crm_core_v1 as crm_core_v1_router
api_router.include_router(crm_core_v1_router.router, prefix="/crm-core-v1", tags=["crm_core_v1"])


# CLONEXA Company Settings V1 router
from app.api.v1.endpoints import company_settings_v1 as company_settings_v1_router
api_router.include_router(company_settings_v1_router.router, prefix="/company-settings-v1", tags=["company_settings_v1"])
