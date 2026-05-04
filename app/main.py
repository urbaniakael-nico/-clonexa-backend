from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

try:
    from app.api.v1.router import api_router
except Exception:
    api_router = None

try:
    from app.web.admin_routes import register_admin_console
except Exception:
    register_admin_console = None

try:
    from app.web.client_routes import register_client_portal
except Exception:
    register_client_portal = None


app = FastAPI(title="Clonexa Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "clonexa-backend"}


if api_router is not None:
    app.include_router(api_router, prefix="/api/v1")

if register_admin_console is not None:
    register_admin_console(app)

if register_client_portal is not None:
    register_client_portal(app)

# CLONEXA web assets
app.mount("/assets", StaticFiles(directory="app/web/assets"), name="assets")

# CLONEXA_ADMIN_V2_ROUTE
try:
    from app.web.admin_v2_routes import router as admin_v2_router
    app.include_router(admin_v2_router)
except Exception as exc:
    import logging
    logging.getLogger("clonexa.admin_v2").warning("Admin Console V2 no pudo registrarse: %s", exc)
# END_CLONEXA_ADMIN_V2_ROUTE
