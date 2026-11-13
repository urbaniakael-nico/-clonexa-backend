"""NEXUS · Radar de innovacion de Clonexa (interno). Crea o actualiza, idempotente por nombre:

- "NEXUS - Radar"     lunes 8:00 (Bogota) y a pedido (webhook POST nexus-radar con X-Nexa-Token desde la consola, o
                      sub-flujo desde /radar): backend abre el informe y arma la peticion -> Claude Sonnet 5.5 con
                      busqueda web (max 8) -> backend valida (fuente real con fecha, sin repetir) y guarda -> NEXUS:
                      cabecera + un mensaje por idea con [⭐ Me interesa] [🗂 Al backlog] [✖ Descartar].
                      Ejecuciones exitosas sin guardar datos. Tope: 3 a pedido por dia (lo decide el backend).
- "NEXUS - Errores"   Error Workflow del Radar: cierra el informe como fallido y avisa por NEXUS en una linea.
- "NEXUS - Comandos"  Telegram Trigger (credencial "NEXUS Bot"): botones, /radar <tema>, /ideas, /backlog, /ayuda;
                      solo el chat del dueno (los demas se ignoran y se registra solo su huella). Webhook POST
                      nexus-editar (X-Nexa-Token): la consola cambio el estado -> se edita el mensaje en NEXUS.
Credenciales que ya existen en n8n: "NEXUS Bot" (telegramApi), "Anthropic Nexa", "Nexa backend (X-Nexa-Token)".
El token del bot nunca sale de n8n. El chat del dueno se guarda tambien como credencial "NEXUS_CHAT_ID".
Antes de cambiar un flujo guarda su JSON en respaldos-clonexa\\n8n\\<fecha>\\ y despues exporta el resultado.
Uso: py -3.11 ops/n8n/nexus_flows.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nexa_v2_flows as v2  # noqa: E402

BACKEND = v2.BACKEND + "/api/v1/radar"
C_NX = {"telegramApi": {"id": "SConJagqELMk7ruJ", "name": "NEXUS Bot"}}
CHAT = v2.CHAT                     # chat privado del dueno (el mismo id en @CloNEXA_bot y en NEXUS; verificado con el /start)
F_RADAR, F_ERR, F_CMD = "NEXUS - Radar", "NEXUS - Errores", "NEXUS - Comandos"
CHAT_CRED = "NEXUS_CHAT_ID"


def nid(flow: str, name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"nexus/{flow}/{name}"))


def fix(f: v2.Flow, flow: str, pos: dict) -> None:
    for n in f.nodes:
        n["id"] = nid(flow, n["name"])
        if n["name"] in pos:
            n["position"] = list(pos[n["name"]])


def be(f: v2.Flow, name: str, method: str, path: str, cred: dict, body: str | None = None, **kw) -> str:
    return f.http(name, method, "=" + BACKEND + path, cred, json_body=body, timeout=120000, **kw)


def nx(f: v2.Flow, name: str, text: str, buttons: list | None = None, html: bool = True, **extra) -> str:
    p: dict = {"chatId": CHAT, "text": text, "additionalFields": {"appendAttribution": False, "disable_web_page_preview": True}}
    if html:
        p["additionalFields"]["parse_mode"] = "HTML"
    if buttons:
        p["replyMarkup"] = "inlineKeyboard"
        p["inlineKeyboard"] = {"rows": [{"row": {"buttons": [{"text": t, "additionalFields": {"callback_data": d}} for t, d in row]}}
                                        for row in buttons]}
    return f.add(name, "n8n-nodes-base.telegram", p, 1.2, C_NX, **extra)


IDEA_BUTTONS = [[("⭐ Me interesa", "={{ $json.botones.interesa }}"), ("🗂 Al backlog", "={{ $json.botones.backlog }}"),
                 ("✖ Descartar", "={{ $json.botones.descartar }}")]]


# ------------------------------------------------------------------ NEXUS - Radar
def flow_radar(cred: dict) -> v2.Flow:
    f = v2.Flow()
    f.cron("Lunes 8:00", "0 8 * * 1")
    f.add("Desde la consola", "n8n-nodes-base.webhook", {"httpMethod": "POST", "path": "nexus-radar", "responseMode": "onReceived",
                                                         "authentication": "headerAuth", "options": {}}, 2, cred,
          webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, "hook/nexus-radar")))
    f.sub_trigger("Desde Comandos")
    f.code("Opciones", """
const j = $json || {};
let tipo = 'semanal', tema = '', origen = 'cron';
if (j.body && typeof j.body === 'object') { tipo = 'a_pedido'; tema = String(j.body.tema || ''); origen = j.body.origen === 'telegram' ? 'telegram' : 'consola'; }
else if (j.origen) { tipo = 'a_pedido'; tema = String(j.tema || ''); origen = 'telegram'; }
return [{ json: { tipo, tema: tema.slice(0, 300), origen } }];
""")
    be(f, "Abrir informe", "POST", "/n8n/start", cred, body="={{ JSON.stringify($json) }}")
    f.iff("¿Abierto?", "$json.ok === true")
    f.http("Claude", "POST", "https://api.anthropic.com/v1/messages", v2.C_ANTH, cred_type="anthropicApi",
           json_body="={{ JSON.stringify($json.request) }}", timeout=300000,
           headers={"anthropic-version": "2023-06-01", "anthropic-beta": "server-side-fallback-2026-07-01"})
    f.iff("¿Pausa?", "$json.stop_reason === 'pause_turn'")
    be(f, "Continuar", "POST", "/n8n/continue", cred,
       body="={{ JSON.stringify({ informe_id: $('Abrir informe').first().json.informe_id, request: $('Abrir informe').first().json.request, responses: [$json] }) }}")
    f.http("Claude (continuar)", "POST", "https://api.anthropic.com/v1/messages", v2.C_ANTH, cred_type="anthropicApi",
           json_body="={{ JSON.stringify($json.request) }}", timeout=300000,
           headers={"anthropic-version": "2023-06-01", "anthropic-beta": "server-side-fallback-2026-07-01"})
    f.code("Respuestas", """
const open = $('Abrir informe').first().json;
const r1 = $('Claude').first().json;
let r2 = null; try { r2 = $('Claude (continuar)').first().json; } catch (e) {}
return [{ json: { body: JSON.stringify({ informe_id: open.informe_id, responses: r2 ? [r1, r2] : [r1] }) } }];
""", executeOnce=True)
    be(f, "Guardar informe", "POST", "/n8n/finish", cred, body="={{ $json.body }}")
    f.iff("¿Listo?", "$json.ok === true")
    nx(f, "NEXUS: cabecera", "={{ $json.cabecera }}")
    f.code("Una por idea", "return ($('Guardar informe').first().json.ideas || []).map(i => ({ json: i }));")
    nx(f, "NEXUS: idea", "={{ $json.mensaje }}", IDEA_BUTTONS)
    be(f, "Guardar mensaje", "POST", "/n8n/ideas/{{ $('Una por idea').item.json.id }}/message", cred,
       body="={{ JSON.stringify({ message_id: ($json.result || {}).message_id || $json.message_id || 0 }) }}")
    nx(f, "NEXUS: aviso", "={{ $json.mensaje || '⚠️ NEXUS: no pude abrir el informe.' }}")
    for t in ("Lunes 8:00", "Desde la consola", "Desde Comandos"):
        f.link(t, "Opciones")
    f.chain("Opciones", "Abrir informe", "¿Abierto?", "Claude", "¿Pausa?", "Continuar", "Claude (continuar)", "Respuestas")
    f.link("¿Pausa?", "Respuestas", 1)
    f.chain("Respuestas", "Guardar informe", "¿Listo?", "NEXUS: cabecera", "Una por idea", "NEXUS: idea", "Guardar mensaje")
    f.link("¿Abierto?", "NEXUS: aviso", 1)
    f.link("¿Listo?", "NEXUS: aviso", 1)
    fix(f, F_RADAR, {"Lunes 8:00": (0, 0), "Desde la consola": (0, 180), "Desde Comandos": (0, 360), "Opciones": (240, 180),
                     "Abrir informe": (480, 180), "¿Abierto?": (720, 180), "Claude": (960, 120), "¿Pausa?": (1200, 120),
                     "Continuar": (1440, 0), "Claude (continuar)": (1680, 0), "Respuestas": (1920, 120), "Guardar informe": (2160, 120),
                     "¿Listo?": (2400, 120), "NEXUS: cabecera": (2640, 40), "Una por idea": (2880, 40), "NEXUS: idea": (3120, 40),
                     "Guardar mensaje": (3360, 40), "NEXUS: aviso": (2640, 300)})
    return f


# ------------------------------------------------------------------ NEXUS - Errores
def flow_errores(cred: dict) -> v2.Flow:
    f = v2.Flow()
    f.add("Si falla", "n8n-nodes-base.errorTrigger", {}, 1)
    be(f, "Cerrar informe", "POST", "/n8n/fail", cred,
       body="={{ JSON.stringify({ informe_id: 0, error: String((($json.execution || {}).error || {}).message || 'error en n8n').slice(0, 200) }) }}")
    nx(f, "NEXUS: falló", "={{ '⚠️ NEXUS: el radar falló (' + String(((($('Si falla').first().json.execution || {}).error || {}).message) || 'error').slice(0, 120) + ').' }}",
       html=False)
    f.chain("Si falla", "Cerrar informe", "NEXUS: falló")
    fix(f, F_ERR, {"Si falla": (0, 0), "Cerrar informe": (240, 0), "NEXUS: falló": (480, 0)})
    return f


# ------------------------------------------------------------------ despliegue
def export(flow: dict) -> Path:
    d = v2.BACKUPS / dt.date.today().isoformat()
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{flow['name'].replace(' ', '_')}_{flow['id']}_despues.json"
    p.write_text(json.dumps(flow, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def chat_credential() -> None:
    """El chat del dueno como credencial (la licencia de n8n no tiene variables). Los flujos usan la misma constante."""
    names = {c["name"] for c in v2.call("GET", "/credentials?limit=100").get("data", [])}
    if CHAT_CRED not in names:
        v2.call("POST", "/credentials", {"name": CHAT_CRED, "type": "httpHeaderAuth", "data": {"name": "X-Nexus-Chat", "value": CHAT}})
        print("credencial creada", CHAT_CRED)


def main() -> None:
    cred = v2.backend_credential()
    existing = {w["name"]: w for w in v2.all_workflows()}
    chat_credential()
    quiet = {"saveDataSuccessExecution": "none", "saveManualExecutions": False}
    ef = flow_errores(cred)
    eid = v2.upsert(F_ERR, ef.nodes, ef.conns, quiet, True, existing)
    rf = flow_radar(cred)
    rid = v2.upsert(F_RADAR, rf.nodes, rf.conns, {**quiet, "errorWorkflow": eid}, True, existing)
    ids = [eid, rid]
    if "flow_comandos" in globals():
        cf = globals()["flow_comandos"](cred, rid)
        ids.append(v2.upsert(F_CMD, cf.nodes, cf.conns, {**quiet, "errorWorkflow": eid}, True, existing))
    for wid in ids:
        print("exportado", export(v2.call("GET", f"/workflows/{wid}")).name)


if __name__ == "__main__":
    main()
