import base64
import binascii
import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services.access_sessions import close_access_session, list_access_sessions, register_access_session, validate_access_session

router = APIRouter()

WEB_DIR = Path(__file__).resolve().parent
ASSETS_DIR = WEB_DIR / "assets"
ADMIN_V2_EMAIL = os.getenv("CLONEXA_ADMIN_V2_EMAIL", "clonexasaas@gmail.com").strip().lower()
ADMIN_V2_PASSWORD_HASH = os.getenv(
    "CLONEXA_ADMIN_V2_PASSWORD_SHA256",
    "8a0b1744088773d637ad0b016cc2424fac07ae0a59a9dd946a8022958e55e10c",
).strip().lower()
ADMIN_V2_COOKIE = "clonexa_admin_v2_session"
ADMIN_V2_SESSION_SECONDS = 8 * 60 * 60
_FALLBACK_SESSION_SECRET = secrets.token_urlsafe(48)


def _session_seconds() -> int:
    try:
        return int(os.getenv("CLONEXA_ADMIN_V2_SESSION_SECONDS", str(ADMIN_V2_SESSION_SECONDS)))
    except (TypeError, ValueError):
        return ADMIN_V2_SESSION_SECONDS


def _session_secret() -> bytes:
    configured = os.getenv("CLONEXA_ADMIN_V2_SECRET") or os.getenv("JWT_SECRET_KEY") or os.getenv("SECRET_KEY")
    return (configured or _FALLBACK_SESSION_SECRET).encode("utf-8")


def _is_secure_request(request: Request) -> bool:
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return forwarded_proto == "https" or request.url.scheme == "https"


def _password_hash(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _create_session_token(email: str, session_key: str) -> str:
    expires_at = int(time.time()) + _session_seconds()
    payload = base64.urlsafe_b64encode(f"{email}|{expires_at}|{session_key}".encode("utf-8")).decode("ascii")
    signature = hmac.new(_session_secret(), payload.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def _session_payload(request: Request) -> dict[str, str | int]:
    token = request.cookies.get(ADMIN_V2_COOKIE, "")
    if "." not in token:
        return {}

    payload, signature = token.rsplit(".", 1)
    expected = hmac.new(_session_secret(), payload.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return {}

    try:
        decoded = base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8")
        parts = decoded.split("|")
        if len(parts) != 3:
            return {}
        email, expires_at_raw, session_key = parts
        expires_at = int(expires_at_raw)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return {}

    if email.lower() != ADMIN_V2_EMAIL or expires_at < int(time.time()) or not session_key:
        return {}
    return {"email": email.lower(), "expires_at": expires_at, "session_key": session_key}


def _valid_session(request: Request) -> bool:
    return bool(_session_payload(request))


def _session_key_from_request(request: Request) -> str:
    payload = _session_payload(request)
    return str(payload.get("session_key") or "")


async def _active_session(request: Request, db: AsyncSession) -> bool:
    if not _valid_session(request):
        return False
    try:
        await validate_access_session(db, _session_key_from_request(request), expected_scope="admin_v2")
        return True
    except HTTPException:
        return False


async def _require_admin_v2_session(request: Request, db: AsyncSession) -> None:
    if not await _active_session(request, db):
        raise HTTPException(status_code=303, headers={"Location": "/admin-v2/login"})


def _no_store(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


async def _read_login_payload(request: Request) -> dict[str, str]:
    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        try:
            data = await request.json()
        except Exception:
            data = {}
        return {
            "email": str(data.get("email", "")),
            "password": str(data.get("password", "")),
        }

    body = (await request.body()).decode("utf-8", errors="ignore")
    parsed = parse_qs(body)
    return {
        "email": parsed.get("email", [""])[0],
        "password": parsed.get("password", [""])[0],
    }


def _login_html(error: str = "") -> str:
    error_markup = f'<div class="error">{error}</div>' if error else ""
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CLONEXA Admin V2</title>
  <style>
    :root {{
      --bg: #090713;
      --panel: rgba(24, 28, 44, 0.88);
      --line: rgba(255, 255, 255, 0.14);
      --text: #f7efff;
      --muted: rgba(247, 239, 255, 0.68);
      --accent: #f72585;
      --accent-2: #b517ff;
      --ok: #b8ffd2;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 28px;
      color: var(--text);
      background:
        radial-gradient(circle at 12% 15%, rgba(247, 37, 133, 0.22), transparent 32%),
        radial-gradient(circle at 84% 20%, rgba(24, 242, 255, 0.14), transparent 28%),
        linear-gradient(135deg, #180020, #041018 62%, #0b0614);
      font-family: Inter, Segoe UI, system-ui, sans-serif;
    }}
    .card {{
      width: min(100%, 520px);
      padding: 34px;
      border: 1px solid var(--line);
      border-radius: 26px;
      background: linear-gradient(145deg, rgba(255,255,255,0.09), rgba(255,255,255,0.035)), var(--panel);
      box-shadow: 0 28px 90px rgba(0,0,0,0.42);
    }}
    .eyebrow {{
      margin: 0 0 10px;
      color: var(--accent);
      font-size: 12px;
      font-weight: 900;
      letter-spacing: 0.18em;
      text-transform: uppercase;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: clamp(34px, 8vw, 58px);
      line-height: 0.95;
      letter-spacing: 0;
    }}
    p {{
      margin: 0 0 28px;
      color: var(--muted);
      font-size: 16px;
      font-weight: 700;
      line-height: 1.45;
    }}
    label {{
      display: block;
      margin: 18px 0 8px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 900;
      letter-spacing: 0.14em;
      text-transform: uppercase;
    }}
    input {{
      width: 100%;
      height: 58px;
      padding: 0 18px;
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 14px;
      outline: none;
      color: var(--text);
      background: rgba(2, 5, 16, 0.86);
      font-size: 16px;
      font-weight: 800;
    }}
    input:focus {{
      border-color: rgba(184,255,210,0.75);
      box-shadow: 0 0 0 4px rgba(184,255,210,0.10);
    }}
    button {{
      width: 100%;
      height: 60px;
      margin-top: 22px;
      border: 0;
      border-radius: 16px;
      color: #080916;
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
      font-size: 16px;
      font-weight: 950;
      cursor: pointer;
    }}
    .error {{
      margin: 0 0 18px;
      padding: 14px 16px;
      border: 1px solid rgba(255, 92, 122, 0.42);
      border-radius: 14px;
      color: #ffd5dd;
      background: rgba(255, 92, 122, 0.12);
      font-weight: 850;
    }}
    .hint {{
      margin-top: 18px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 750;
    }}
  </style>
</head>
<body>
  <main class="card">
    <p class="eyebrow">Acceso maestro</p>
    <h1>CLONEXA V2</h1>
    <p>Ingresa tus credenciales SaaS para abrir la consola.</p>
    {error_markup}
    <form method="post" action="/admin-v2/login" autocomplete="on">
      <label for="email">Correo</label>
      <input id="email" name="email" type="email" inputmode="email" autocomplete="username" required autofocus />
      <label for="password">Contraseña</label>
      <input id="password" name="password" type="password" autocomplete="current-password" required />
      <button type="submit">Entrar a consola</button>
    </form>
    <div class="hint">Sesion protegida por cookie segura de la consola V2.</div>
  </main>
</body>
</html>"""


@router.get("/admin-v2/login", response_class=HTMLResponse, include_in_schema=False)
async def admin_v2_login_page(request: Request, db: AsyncSession = Depends(get_db)):
    if await _active_session(request, db):
        return RedirectResponse(url="/admin-v2", status_code=303)
    return _no_store(HTMLResponse(_login_html()))


@router.post("/admin-v2/login", include_in_schema=False)
async def admin_v2_login(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await _read_login_payload(request)
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "")

    valid_email = hmac.compare_digest(email, ADMIN_V2_EMAIL)
    valid_password = hmac.compare_digest(_password_hash(password), ADMIN_V2_PASSWORD_HASH)
    if not (valid_email and valid_password):
        return _no_store(HTMLResponse(_login_html("Credenciales invalidas."), status_code=401))

    session_key = await register_access_session(
        db,
        company_id=None,
        scope="admin_v2",
        subject_id=None,
        subject_label=email,
        request=request,
        enforce_policy=False,
        metadata={"surface": "admin_v2"},
    )
    response = RedirectResponse(url="/admin-v2", status_code=303)
    response.set_cookie(
        ADMIN_V2_COOKIE,
        _create_session_token(email, session_key),
        max_age=_session_seconds(),
        httponly=True,
        secure=_is_secure_request(request),
        samesite="lax",
        path="/",
    )
    return response


@router.post("/admin-v2/logout", include_in_schema=False)
async def admin_v2_logout(request: Request, db: AsyncSession = Depends(get_db)):
    session_key = _session_key_from_request(request)
    if session_key:
        await close_access_session(db, session_key, "logout")
    response = RedirectResponse(url="/admin-v2/login", status_code=303)
    response.delete_cookie(ADMIN_V2_COOKIE, path="/")
    return response


@router.get("/admin-v2/api/sessions", include_in_schema=False)
async def admin_v2_sessions(request: Request, db: AsyncSession = Depends(get_db)):
    await _require_admin_v2_session(request, db)
    current = _session_key_from_request(request)
    sessions = await list_access_sessions(db, company_id=None, scope="admin_v2", include_closed=True, limit=40)
    return {
        "ok": True,
        "current_session": current,
        "active": len([item for item in sessions if str(item.get("status") or "").lower() == "active"]),
        "sessions": sessions,
    }


@router.post("/admin-v2/api/sessions/{session_key}/close", include_in_schema=False)
async def admin_v2_close_session(session_key: str, request: Request, db: AsyncSession = Depends(get_db)):
    await _require_admin_v2_session(request, db)
    closed = await close_access_session(db, session_key, "closed_from_admin_v2")
    return {"ok": True, "closed": bool(closed), "closed_session": session_key}


@router.get("/admin-v2", response_class=HTMLResponse, include_in_schema=False)
@router.get("/admin-v2/", response_class=HTMLResponse, include_in_schema=False)
async def admin_v2_page(request: Request, db: AsyncSession = Depends(get_db)):
    await _require_admin_v2_session(request, db)
    html_path = WEB_DIR / "admin_v2.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Admin Console V2 no encontrada")
    return _no_store(FileResponse(html_path))


@router.get("/admin-v2.css", include_in_schema=False)
async def admin_v2_css():
    css_path = WEB_DIR / "admin_v2.css"
    if not css_path.exists():
        raise HTTPException(status_code=404, detail="CSS Admin V2 no encontrado")
    return _no_store(FileResponse(css_path, media_type="text/css"))


@router.get("/admin-v2.js", include_in_schema=False)
async def admin_v2_js():
    js_path = WEB_DIR / "admin_v2.js"
    if not js_path.exists():
        raise HTTPException(status_code=404, detail="JS Admin V2 no encontrado")
    return _no_store(FileResponse(js_path, media_type="application/javascript"))


@router.get("/admin-v2-assets/{asset_path:path}", include_in_schema=False)
async def admin_v2_assets(asset_path: str):
    safe_path = (ASSETS_DIR / asset_path).resolve()
    assets_root = ASSETS_DIR.resolve()

    if assets_root not in safe_path.parents and safe_path != assets_root:
        raise HTTPException(status_code=404, detail="Asset inválido")

    if not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(status_code=404, detail="Asset no encontrado")

    return _no_store(FileResponse(safe_path))


@router.get("/admin-v2/ping", include_in_schema=False)
async def admin_v2_ping(request: Request, db: AsyncSession = Depends(get_db)):
    await _require_admin_v2_session(request, db)
    return _no_store(Response("OK", media_type="text/plain"))
