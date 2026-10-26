"""Crea (o actualiza) en n8n los flujos "Clonexa - Leer carta" y "Clonexa - Aviso cupo".

- Llave de n8n: C:\\Users\\valef\\Desktop\\referencias\\n8n-key.txt (cabecera X-N8N-API-KEY).
- Token del regreso: C:\\Users\\valef\\Desktop\\referencias\\carta-import-token.txt; se guarda
  en n8n como credencial Header Auth "Clonexa carta token" (X-Carta-Token).
- Claude: la MISMA credencial y forma del nodo que llama a api.anthropic.com en
  "Nexa - Publicar en todas" (Z3M4w25F42Snki5j). No crea llaves nuevas.
- Telegram: el mismo nodo/credencial de "Nexa - Bot de comandos" (chat 5126243056).
- Gmail: la primera credencial Gmail que use algún flujo.
Nunca imprime llaves ni tokens.
Uso: py -3.11 ops/n8n/deploy_carta_flows.py
"""
from __future__ import annotations

import copy
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://main-production-54df.up.railway.app/api/v1"
REFS = Path(r"C:\Users\valef\Desktop\referencias")
HERE = Path(__file__).resolve().parent
NEXA_PUBLISH = "Z3M4w25F42Snki5j"
CHAT_ID = "5126243056"
CRED_NAME = "Clonexa carta token"


def read_secret(name: str, pattern: str) -> str:
    raw = (REFS / name).read_bytes().decode("utf-8", "replace")
    for line in raw.splitlines():
        if re.fullmatch(pattern, line.strip()):
            return line.strip()
    sys.exit(f"{name} no tiene el valor esperado (no se muestra el contenido).")


KEY = read_secret("n8n-key.txt", r"eyJ[\w-]+\.[\w-]+\.[\w-]+|n8n_api_[\w-]{20,}")
TOKEN = read_secret("carta-import-token.txt", r"[\w-]{40,}")


def call(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        sys.exit(f"n8n {method} {path} -> {e.code}: {e.read().decode()[:300]}")


def workflows() -> list[dict]:
    return call("GET", "/workflows?limit=250").get("data", [])


def find_node(flow: dict, test) -> dict | None:
    return next((n for n in flow.get("nodes", []) if test(n)), None)


def main() -> None:
    flows = workflows()
    by_name = {w["name"]: w for w in flows}
    nexa = call("GET", f"/workflows/{NEXA_PUBLISH}")
    claude = find_node(nexa, lambda n: "api.anthropic.com" in json.dumps(n.get("parameters", {})))
    if not claude or not claude.get("credentials"):
        sys.exit("No encontré el nodo de Claude con credencial en 'Nexa - Publicar en todas'.")
    bot = by_name.get("Nexa - Bot de comandos")
    bot = call("GET", f"/workflows/{bot['id']}") if bot else None
    telegram = bot and find_node(bot, lambda n: n.get("type") == "n8n-nodes-base.telegram")
    if not telegram:
        sys.exit("No encontré el nodo de Telegram en 'Nexa - Bot de comandos'.")
    gmail = None
    for w in flows:
        full = call("GET", f"/workflows/{w['id']}")
        gmail = find_node(full, lambda n: n.get("type") == "n8n-nodes-base.gmail" and n.get("credentials"))
        if gmail:
            break

    # credencial del token (se crea una vez; n8n no deja leer su valor)
    cred = call("POST", "/credentials", {"name": CRED_NAME, "type": "httpHeaderAuth", "data": {"name": "X-Carta-Token", "value": TOKEN}})
    token_cred = {"id": cred["id"], "name": cred["name"]}

    def fill(template: dict) -> dict:
        flow = copy.deepcopy(template)
        flow.pop("_doc", None)
        for node in flow["nodes"]:
            if node.get("credentials") == {"httpHeaderAuth": "__CARTA_TOKEN_CRED__"}:
                node["credentials"] = {"httpHeaderAuth": token_cred}
            if node.get("credentials") == "__ANTHROPIC_CRED__":
                node["credentials"] = claude["credentials"]
                p = claude.get("parameters", {})
                node["parameters"]["authentication"] = p.get("authentication", "genericCredentialType")
                for k in ("genericAuthType", "nodeCredentialType"):
                    if k in p:
                        node["parameters"][k] = p[k]
            if node.get("type") == "__TELEGRAM_NODE__":
                node["type"] = telegram["type"]
                node["typeVersion"] = telegram.get("typeVersion", 1.2)
                params = copy.deepcopy(telegram.get("parameters", {}))
                params.update({"chatId": CHAT_ID, "text": "={{ $json.texto }}"})
                node["parameters"] = params
                node["credentials"] = telegram["credentials"]
            if node.get("credentials") == "__GMAIL_CRED__":
                if gmail:
                    node["credentials"] = gmail["credentials"]
                else:
                    node["credentials"] = {}
                    node["disabled"] = True
        return flow

    for file, name in (("clonexa-leer-carta.json", "Clonexa - Leer carta"), ("clonexa-aviso-cupo.json", "Clonexa - Aviso cupo")):
        flow = fill(json.loads((HERE / file).read_text(encoding="utf-8")))
        body = {k: flow[k] for k in ("name", "nodes", "connections", "settings")}
        existing = by_name.get(name)
        saved = call("PUT", f"/workflows/{existing['id']}", body) if existing else call("POST", "/workflows", body)
        call("POST", f"/workflows/{saved['id']}/activate", {})
        print(f"{name}: id {saved['id']} activo{' (Gmail sin credencial: nodo apagado)' if name.endswith('cupo') and not gmail else ''}")


if __name__ == "__main__":
    main()
