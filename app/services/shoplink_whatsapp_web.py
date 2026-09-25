from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings

_PROCESS: subprocess.Popen | None = None


def _bridge_port() -> int:
    return int(os.getenv("WHATSAPP_BRIDGE_PORT", "3219"))


def _bridge_url() -> str:
    return os.getenv("WHATSAPP_BRIDGE_URL", f"http://127.0.0.1:{_bridge_port()}").rstrip("/")


def start_whatsapp_bridge() -> bool:
    global _PROCESS
    if str(os.getenv("WHATSAPP_WEB_ENABLED", "true")).lower() in {"0", "false", "no"}:
        return False
    if _PROCESS and _PROCESS.poll() is None:
        return True

    root = Path(__file__).resolve().parents[2]
    script = root / "app" / "services" / "whatsapp_bridge" / "bridge.mjs"
    if not script.exists():
        return False

    env = os.environ.copy()
    env.setdefault("WHATSAPP_BRIDGE_PORT", str(_bridge_port()))
    env.setdefault("WHATSAPP_AUTH_DIR", "/tmp/clonexa-whatsapp-auth")
    env.setdefault(
        "WHATSAPP_INBOUND_URL",
        os.getenv("WHATSAPP_INBOUND_URL", f"http://127.0.0.1:{os.getenv('PORT', '8000')}/api/v1/bots/whatsapp-web/inbound"),
    )
    env.setdefault("WHATSAPP_INBOUND_SECRET", os.getenv("WHATSAPP_INBOUND_SECRET", get_settings().JWT_SECRET_KEY))
    _PROCESS = subprocess.Popen(["node", str(script)], cwd=str(root), env=env)
    return True


async def _request(method: str, path: str, payload: dict[str, Any] | None = None, timeout: float = 22) -> dict[str, Any]:
    start_whatsapp_bridge()
    url = f"{_bridge_url()}{path}"
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(method, url, json=payload)
            data = response.json()
            if response.status_code >= 400 and isinstance(data, dict):
                return data
            return data if isinstance(data, dict) else {"ok": False, "detail": str(data)}
        except (httpx.ConnectError, httpx.ReadError) as exc:
            last_error = exc
            await asyncio.sleep(0.35 + attempt * 0.25)
    return {"ok": False, "status": "bridge_unavailable", "detail": str(last_error or "WhatsApp bridge no disponible.")}


# Each company can link two numbers, one per line, and a number only ever
# serves one line (the bridge refuses the same phone on both):
#   - "interno": the internal agent (nomina, CRM, produccion) for the owner
#     and the Workforce phones allowed to query it. Also sends the ShopLink /
#     transport alerts, as it always did.
#   - "clientes": the public number customers write to; it never reaches the
#     internal agent (see app/services/whatsapp_customer_line.py).
# WARNING: automating WhatsApp Web is against WhatsApp's terms and the number
# can be banned -- use a dedicated number for the customer line.
WHATSAPP_LINES = ("interno", "clientes")


def whatsapp_line(value: Any) -> str:
    line = str(value or "").strip().lower()
    return line if line in WHATSAPP_LINES else "interno"


def _session_key(company_id: str, line: str = "interno") -> str:
    # "interno" keeps the bare company id so already-linked sessions survive.
    return str(company_id) if whatsapp_line(line) == "interno" else f"{company_id}--clientes"


async def whatsapp_status(company_id: str, line: str = "interno") -> dict[str, Any]:
    return await _request("GET", f"/sessions/{_session_key(company_id, line)}")


async def whatsapp_start(company_id: str, line: str = "interno") -> dict[str, Any]:
    return await _request("POST", f"/sessions/{_session_key(company_id, line)}/start")


async def whatsapp_logout(company_id: str, line: str = "interno") -> dict[str, Any]:
    return await _request("POST", f"/sessions/{_session_key(company_id, line)}/logout")


async def whatsapp_send(company_id: str, to: str, message: str, line: str = "interno") -> dict[str, Any]:
    return await _request("POST", f"/sessions/{_session_key(company_id, line)}/send", {"to": to, "message": message})
