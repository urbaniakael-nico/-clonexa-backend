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
