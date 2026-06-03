from __future__ import annotations

import ipaddress
import logging
from uuid import UUID

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.core import Company

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


def _clonexa_request_ip(request) -> str:
    forwarded = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return ""


def _clonexa_access_scope(path: str) -> str | None:
    clean_path = (path or "").rstrip("/") or "/"
    if clean_path == "/client":
        return "client"
    if clean_path == "/mini-panel" or clean_path.startswith("/mini-panel/"):
        return "mini_panel"
    if clean_path == "/ordenar":
        return "ordering_qr"
    if clean_path.startswith("/api/v1/mini-panel-"):
        return "mini_panel"
    return None


def _clonexa_company_id_from_path(path: str) -> str | None:
    parts = [part for part in (path or "").split("/") if part]
    for index, part in enumerate(parts):
        if part == "companies" and index + 1 < len(parts):
            return parts[index + 1]
    return None


def _clonexa_ip_allowed(ip_value: str, allowed_items: list[str]) -> bool:
    try:
        ip_address = ipaddress.ip_address(ip_value)
    except ValueError:
        return False

    for item in allowed_items:
        text = str(item or "").strip()
        if not text:
            continue
        try:
            if "/" in text:
                if ip_address in ipaddress.ip_network(text, strict=False):
                    return True
            elif ip_address == ipaddress.ip_address(text):
                return True
        except ValueError:
            continue
    return False


async def _clonexa_access_policy_for_company(company_id: str) -> dict | None:
    try:
        company_uuid = UUID(str(company_id))
    except (TypeError, ValueError):
        return None

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Company.settings_json).where(Company.id == company_uuid))
            settings = result.scalar_one_or_none()
    except Exception as exc:
        logging.getLogger("clonexa.ip_access").warning("No se pudo validar politica IP: %s", exc)
        return None

    if not isinstance(settings, dict):
        return None

    security = settings.get("security") if isinstance(settings.get("security"), dict) else {}
    policy = security.get("ip_allowlist") if isinstance(security.get("ip_allowlist"), dict) else {}
    return policy


def _clonexa_blocked_response(request, scope: str, ip_value: str):
    detail = {
        "detail": "Acceso restringido por politica IP.",
        "scope": scope,
        "ip": ip_value,
    }
    accept = (request.headers.get("accept") or "").lower()
    if "text/html" not in accept:
        return JSONResponse(detail, status_code=403)

    return HTMLResponse(
        f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Acceso restringido - CLONEXA</title>
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 28px;
      color: #f8f4ff;
      background: radial-gradient(circle at 15% 20%, rgba(247, 37, 133, .28), transparent 32%),
        linear-gradient(135deg, #090713, #06151b 70%, #120016);
      font-family: Inter, Segoe UI, system-ui, sans-serif;
    }}
    main {{
      width: min(620px, 100%);
      padding: 34px;
      border: 1px solid rgba(255,255,255,.16);
      border-radius: 24px;
      background: rgba(20, 24, 38, .86);
      box-shadow: 0 30px 90px rgba(0,0,0,.42);
    }}
    .kicker {{
      color: #ff2bd6;
      font-size: 12px;
      font-weight: 900;
      letter-spacing: .18em;
      text-transform: uppercase;
    }}
    h1 {{ margin: 12px 0; font-size: clamp(34px, 8vw, 58px); line-height: .95; }}
    p {{ color: rgba(248,244,255,.74); font-size: 18px; line-height: 1.5; }}
    code {{
      display: inline-block;
      margin-top: 8px;
      padding: 10px 12px;
      border-radius: 12px;
      background: rgba(255,255,255,.08);
      color: #b8ffd2;
      font-size: 15px;
    }}
  </style>
</head>
<body>
  <main>
    <div class="kicker">CLONEXA Seguridad</div>
    <h1>Acceso restringido</h1>
    <p>Esta empresa solo permite abrir este panel desde IPs autorizadas en Admin V2.</p>
    <p>IP detectada:<br><code>{ip_value}</code></p>
  </main>
</body>
</html>""",
        status_code=403,
    )


@app.middleware("http")
async def _clonexa_company_ip_access_guard(request, call_next):
    scope = _clonexa_access_scope(request.url.path)
    if not scope:
        return await call_next(request)

    company_id = (
        request.query_params.get("company_id")
        or request.headers.get("x-company-id")
        or _clonexa_company_id_from_path(request.url.path)
    )
    if not company_id:
        return await call_next(request)

    policy = await _clonexa_access_policy_for_company(company_id)
    if not policy or not policy.get("enabled"):
        return await call_next(request)

    scopes = policy.get("scopes") if isinstance(policy.get("scopes"), dict) else {}
    scoped = scopes.get(scope) if isinstance(scopes.get(scope), dict) else {}
    allowed_ips = scoped.get("allowed_ips") if isinstance(scoped.get("allowed_ips"), list) else []
    if not scoped.get("enabled") or not allowed_ips:
        return await call_next(request)

    ip_value = _clonexa_request_ip(request)
    if _clonexa_ip_allowed(ip_value, allowed_ips):
        return await call_next(request)

    return _clonexa_blocked_response(request, scope, ip_value)

@app.middleware("http")
async def _clonexa_legacy_admin_redirect(request, call_next):
    """
    CLONEXA 019D:
    /admin legacy queda depurado como redirect permanente a /admin-v2.
    No se elimina para no romper accesos guardados.
    """
    if request.url.path.rstrip("/") == "/admin":
        return RedirectResponse(url="/admin-v2", status_code=308)
    return await call_next(request)


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



@app.on_event("startup")
async def _clonexa_startup_bootstrap_bots() -> None:
    """
    CLONEXA 011A3-R2:
    Al reiniciar la API, vuelve a levantar los listeners Telegram activos.
    Evita depender de volver a presionar "Iniciar escucha" por empresa.
    """
    try:
        from app.api.v1.endpoints.bots import bootstrap_telegram_listeners

        await bootstrap_telegram_listeners()
    except Exception as exc:
        import logging

        logging.getLogger("clonexa.telegram_listener").warning(
            "No se pudieron restaurar listeners Telegram activos: %s", exc
        )


if api_router is not None:
    app.include_router(api_router, prefix="/api/v1")

if register_admin_console is not None:
    register_admin_console(app)

if register_client_portal is not None:
    register_client_portal(app)


# CLONEXA_MATERIALS_WEBAPP_ROUTE
try:
    from app.web.materials_webapp_routes import router as materials_webapp_router
    app.include_router(materials_webapp_router)
except Exception as exc:
    import logging
    logging.getLogger("clonexa.materials_webapp").warning("Materials Web App no pudo registrarse: %s", exc)
# END_CLONEXA_MATERIALS_WEBAPP_ROUTE

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
