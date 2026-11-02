"""Agrega al flujo EXISTENTE "Nexa - WhatsApp ventas" (eH34gfwulD898szi) los avisos
de error del webhook de WhatsApp. No crea flujos nuevos.

El backend (app/services/nexa_whatsapp.py, alert()) llama POST
/webhook/nexa-wa-avisos con X-Nexa-Forward cuando el webhook falla al guardar,
reenviar a n8n o responder; como maximo una vez cada 15 minutos.

Cambio exacto (idempotente): 2 nodos nuevos y su conexion; nada mas se toca.
- "Aviso del backend": webhook POST nexa-wa-avisos, credencial Header Auth
  "Nexa WA reenvio" (la misma del nodo "Del backend").
- "Aviso de error": Telegram con la credencial del nodo "Avisar a Telegram",
  chat 5126243056, texto plano = body.texto.
Antes de guardar escribe un respaldo del JSON actual (argumento 1 o la carpeta
actual). Revertir: PUT del respaldo. Nunca imprime secretos.
Uso: py -3.11 ops/n8n/nexa_wa_alerts_flow.py [carpeta_respaldo]
"""
from __future__ import annotations

import copy
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://main-production-54df.up.railway.app/api/v1"
REFS = Path(r"C:\Users\valef\Desktop\referencias")
FLOW = "eH34gfwulD898szi"
PATH = "nexa-wa-avisos"
CHAT_ID = "5126243056"
HOOK_NAME = "Aviso del backend"
TG_NAME = "Aviso de error"
SETTINGS_KEYS = ("executionOrder", "saveDataErrorExecution", "saveDataSuccessExecution", "saveManualExecutions",
                 "saveExecutionProgress", "timezone", "errorWorkflow", "callerPolicy", "executionTimeout")


def read_key() -> str:
    raw = (REFS / "n8n-key.txt").read_bytes().decode("utf-8", "replace")
    for line in raw.splitlines():
        if re.fullmatch(r"eyJ[\w-]+\.[\w-]+\.[\w-]+|n8n_api_[\w-]{20,}", line.strip()):
            return line.strip()
    sys.exit("n8n-key.txt no tiene el valor esperado (no se muestra el contenido).")


KEY = read_key()


def call(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        sys.exit(f"n8n {method} {path} -> {e.code}: {e.read().decode()[:300]}")


def patch(flow: dict) -> dict:
    """Devuelve el cuerpo del PUT con los 2 nodos agregados (o reemplazados)."""
    nodes = [n for n in flow["nodes"] if n["name"] not in (HOOK_NAME, TG_NAME)]
    hook = next(n for n in nodes if n["type"] == "n8n-nodes-base.webhook" and n["parameters"].get("path") == "nexa-wa-ventas")
    tg = next(n for n in nodes if n["name"] == "Avisar a Telegram")
    x, y = hook.get("position", [0, 0])
    # Solo texto plano: el nodo original trae un teclado con botones que aqui no aplica
    # y el detalle del error puede traer _ o * (parse_mode lo romperia).
    params = {"resource": "message", "operation": "sendMessage", "chatId": CHAT_ID,
              "text": "={{ String(($json.body && $json.body.texto) || 'Aviso de Nexa WhatsApp').slice(0, 1000) }}",
              "additionalFields": {"appendAttribution": False, "disable_web_page_preview": True}}
    nodes += [
        {"id": "9b6f3c1e-5a7d-4e2b-8c90-1a2b3c4d5e01", "name": HOOK_NAME, "type": hook["type"], "typeVersion": hook.get("typeVersion", 2),
         "position": [x, y + 900], "webhookId": "5f0d7a52-9c1e-4c55-9b7e-6e6578612d77",
         "parameters": {"httpMethod": "POST", "path": PATH, "authentication": "headerAuth", "responseMode": "onReceived", "options": {}},
         "credentials": copy.deepcopy(hook["credentials"])},
        {"id": "9b6f3c1e-5a7d-4e2b-8c90-1a2b3c4d5e02", "name": TG_NAME, "type": tg["type"], "typeVersion": tg.get("typeVersion", 1.2),
         "position": [x + 260, y + 900], "parameters": params, "credentials": copy.deepcopy(tg["credentials"])},
    ]
    connections = {k: v for k, v in flow["connections"].items() if k not in (HOOK_NAME, TG_NAME)}
    connections[HOOK_NAME] = {"main": [[{"node": TG_NAME, "type": "main", "index": 0}]]}
    settings = {k: v for k, v in (flow.get("settings") or {}).items() if k in SETTINGS_KEYS}
    return {"name": flow["name"], "nodes": nodes, "connections": connections, "settings": settings}


def main() -> None:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    flow = call("GET", f"/workflows/{FLOW}")
    backup = folder / f"n8n_{FLOW}_respaldo_{time.strftime('%Y%m%d_%H%M%S')}.json"
    backup.write_text(json.dumps(flow, ensure_ascii=False, indent=1), encoding="utf-8")
    before = {n["name"] for n in flow["nodes"]}
    body = patch(flow)
    saved = call("PUT", f"/workflows/{FLOW}", body)
    if not saved.get("active"):
        call("POST", f"/workflows/{FLOW}/activate", {})
    after = call("GET", f"/workflows/{FLOW}")
    names = {n["name"] for n in after["nodes"]}
    print(f"respaldo: {backup}")
    print(f"nodos antes {len(before)} -> despues {len(names)}; nuevos: {sorted(names - before)}; quitados: {sorted(before - names)}")
    print(f"activo: {after.get('active')}")


if __name__ == "__main__":
    main()
