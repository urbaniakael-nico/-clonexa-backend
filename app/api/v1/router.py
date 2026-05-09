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
    ("field", "/field", ["field"]),
]:
    _include(_module_name, _prefix, _tags)

# CLONEXA company users router
from app.api.v1.endpoints import company_users as company_users_router
api_router.include_router(company_users_router.router, prefix="/companies", tags=["company_users"])

# CLONEXA auth router
from app.api.v1.endpoints import auth as auth_router
api_router.include_router(auth_router.router, prefix="/auth", tags=["auth"])

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
