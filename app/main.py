from __future__ import annotations

import ipaddress
import logging
import os
from urllib.parse import urlparse
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
    client = getattr(request, "client", None)
    if client and getattr(client, "host", None):
        return client.host
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


# CLONEXA_SEC_2026_09_23_SWEEP_START
# 2026-09-23 security sweep: of ~443 endpoints, ~360 across whole modules
# (hospitality, employees, inventory, mini_panel_sales, marketplace,
# shoplink, company_experience, references_v1, bots, materials, assemblies)
# require no authentication, with no global filter covering them. We are
# NOT closing any of that yet -- PASO 1 only measures live traffic (who is
# actually calling these with no session, and from where) before deciding
# what's safe to lock down without breaking a live company. PASO 2 is the
# one narrow, safe cut agreed on: an archived company's data endpoints
# should not keep answering.
#
# Registration order matters here: the archived-company guard (PASO 2) is
# registered FIRST so the audit middleware (PASO 1), registered SECOND,
# ends up as the outermost middleware and observes every /api/v1/* request
# -- including ones PASO 2 goes on to block with a 403 -- before either one
# decides anything.

def _clonexa_company_id_from_request(request) -> str | None:
    from_path = _clonexa_company_id_from_path(request.url.path)
    if from_path:
        return from_path
    return request.query_params.get("company_id") or request.query_params.get("companyId")


# ---------------------------------------------------------------------------
# PASO 2 (registered first / innermost): archived companies stop answering
# on data endpoints. companies.py's own management endpoints stay reachable
# so Admin V2 can still see and un-archive the company. Inactive companies
# are NOT touched here.
# ---------------------------------------------------------------------------

_CLONEXA_COMPANY_MGMT_TAILS = {
    "",
    "status",
    "archive",
    "restore",
    "operational-reset",
    "client-settings",
    "access-policy",
    "session-policy",
    "access-sessions",
    "experience",
    "experience/branding",
    "branding",
}


def _clonexa_is_company_management_path(path: str) -> bool:
    clean = path.rstrip("/") or "/"
    if clean == "/api/v1/companies":
        return True
    prefix = "/api/v1/companies/"
    if not path.startswith(prefix):
        return False
    remainder = path[len(prefix):].strip("/")
    if not remainder:
        return True
    _company_id, _, tail = remainder.partition("/")
    if tail.startswith("access-sessions"):
        return True
    return tail in _CLONEXA_COMPANY_MGMT_TAILS


async def _clonexa_company_is_archived(company_id: str) -> bool:
    try:
        company_uuid = UUID(str(company_id))
    except (TypeError, ValueError):
        return False
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Company.status).where(Company.id == company_uuid))
            status_value = result.scalar_one_or_none()
    except Exception as exc:
        logging.getLogger("clonexa.archived_guard").warning("No se pudo verificar estado de empresa: %s", exc)
        return False
    return str(status_value or "").strip().lower() == "archived"


@app.middleware("http")
async def _clonexa_archived_company_guard(request, call_next):
    path = request.url.path
    if not path.startswith("/api/v1/") or _clonexa_is_company_management_path(path):
        return await call_next(request)

    company_id = _clonexa_company_id_from_request(request)
    if not company_id:
        return await call_next(request)

    if await _clonexa_company_is_archived(company_id):
        return JSONResponse({"detail": "Empresa archivada."}, status_code=403)

    return await call_next(request)


# ---------------------------------------------------------------------------
# PASO 1 (registered second / outermost): measure only, never block. Logs
# one grep-able line for any /api/v1/* request that arrives with no valid
# session, so we can see which of the ~360 unauthenticated endpoints real
# traffic (especially from the 3 live companies) actually depends on before
# locking any of them down.
# ---------------------------------------------------------------------------

_CLONEXA_LIVE_COMPANY_IDS = {
    "7625872c-f941-4479-a27b-f8443be953c5",  # ASADERO EL SOCIO
    "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4",  # The Time Machine
    "d63cf68c-be5b-4a30-aee4-341973018db1",  # Velvet
}


def _clonexa_live_company_ids() -> set[str]:
    """The 3 active companies whose traffic we actually care about right
    now; every other company_id in the audit log is demo/test noise that
    can be ignored while triaging. Fixed ids on purpose (not a name lookup)
    so this never depends on a company's name or a cached query."""
    return _CLONEXA_LIVE_COMPANY_IDS


def _clonexa_token_from_request(request) -> str | None:
    authorization = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    if not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    return token or None


def _clonexa_token_scope_hint(token: str | None) -> str | None:
    if not token:
        return None
    try:
        from app.services.auth_service import decode_access_token

        payload = decode_access_token(token)
        scope = payload.get("scope")
        return str(scope) if scope else None
    except Exception:
        return None


async def _clonexa_has_valid_session(request, db, token: str | None) -> bool:
    """Admin V2 cookie session, or a company/mini-panel JWT that actually
    validates (signature, expiry and -- if it carries one -- an active
    session row). Never raises: any failure just means "no valid session"."""
    try:
        from app.web.admin_v2_routes import _active_session as _clonexa_admin_v2_active

        if await _clonexa_admin_v2_active(request, db):
            return True
    except Exception:
        pass

    if not token:
        return False
    try:
        from app.services.auth_service import get_current_company_user

        await get_current_company_user(db, token)
        return True
    except Exception:
        return False


def _clonexa_audit_origin(request, token_scope: str | None) -> str:
    if token_scope in {"client", "mini_panel"}:
        return token_scope
    referer = request.headers.get("referer") or request.headers.get("Referer") or ""
    try:
        ref_path = urlparse(referer).path
    except Exception:
        ref_path = ""
    scope = _clonexa_access_scope(ref_path)
    if scope == "ordering_qr":
        return "qr_publico"
    if scope in {"client", "mini_panel"}:
        return scope
    return "desconocido"


# The audit lines are INFO, but nothing configures Python logging in this
# app (uvicorn only sets up its own loggers), so the root logger's default
# WARNING level silently dropped every AUTH_AUDIT line since it was added.
# Give this one logger its own stdout handler at INFO (Railway shows stdout
# as info). Propagation stays on: the root logger has no handler here, so
# nothing is printed twice, and pytest's caplog can still see the lines.
import sys as _clonexa_sys

class _ClonexaStdoutHandler(logging.StreamHandler):
    """Always writes to the current sys.stdout (not the one at import)."""

    @property
    def stream(self):
        return _clonexa_sys.stdout

    @stream.setter
    def stream(self, _value):
        pass


_clonexa_audit_logger = logging.getLogger("clonexa.auth_audit")
if not any(getattr(h, "_clonexa_audit", False) for h in _clonexa_audit_logger.handlers):
    _clonexa_audit_handler = _ClonexaStdoutHandler()
    _clonexa_audit_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    _clonexa_audit_handler._clonexa_audit = True
    _clonexa_audit_logger.addHandler(_clonexa_audit_handler)
_clonexa_audit_logger.setLevel(logging.INFO)


def _clonexa_auth_audit_enabled() -> bool:
    return os.getenv("CLONEXA_AUTH_AUDIT", "true").strip().lower() not in {"0", "false", "off", "no"}


@app.middleware("http")
async def _clonexa_auth_audit_middleware(request, call_next):
    path = request.url.path
    if not path.startswith("/api/v1/") or not _clonexa_auth_audit_enabled():
        return await call_next(request)

    try:
        token = _clonexa_token_from_request(request)
        async with AsyncSessionLocal() as db:
            has_session = await _clonexa_has_valid_session(request, db, token)
        if not has_session:
            company_id = _clonexa_company_id_from_request(request)
            live_ids = _clonexa_live_company_ids()
            empresa_viva = bool(company_id) and str(company_id) in live_ids
            origin = _clonexa_audit_origin(request, _clonexa_token_scope_hint(token))
            _clonexa_audit_logger.info(
                "AUTH_AUDIT path=%s method=%s company_id=%s empresa_viva=%s origen=%s ip=%s",
                path,
                request.method,
                company_id or "-",
                str(empresa_viva).lower(),
                origin,
                _clonexa_request_ip(request) or "-",
            )
    except Exception as exc:
        _clonexa_audit_logger.warning("Fallo no bloqueante en auditoria de auth: %s", exc)

    return await call_next(request)
# CLONEXA_SEC_2026_09_23_SWEEP_END


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, object]:
    return {"ok": True, "status": "ok", "service": "clonexa-backend"}



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

    try:
        # 049D: corte diario de sesiones y turnos abiertos (todas las empresas).
        from app.services.session_cutoff import start_cutoff_loop

        start_cutoff_loop()
    except Exception as exc:
        import logging

        logging.getLogger("clonexa.session_cutoff").warning("No se pudo iniciar el corte diario: %s", exc)

    try:
        from app.services.shoplink_whatsapp_web import start_whatsapp_bridge

        start_whatsapp_bridge()
    except Exception as exc:
        import logging

        logging.getLogger("clonexa.whatsapp_bridge").warning(
            "No se pudo iniciar puente WhatsApp Web: %s", exc
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
