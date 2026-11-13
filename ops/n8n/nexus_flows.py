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


# codigo de los nodos (constantes: tests/nexus_flows_js.test.cjs las ejecuta sin la clave de n8n)
OPCIONES_JS = """
const j = $json || {};
let tipo = 'semanal', tema = '', origen = 'cron';
if (j.body && typeof j.body === 'object') { tipo = 'a_pedido'; tema = String(j.body.tema || ''); origen = j.body.origen === 'telegram' ? 'telegram' : 'consola'; }
else if (j.origen) { tipo = 'a_pedido'; tema = String(j.tema || ''); origen = 'telegram'; }
return [{ json: { tipo, tema: tema.slice(0, 300), origen } }];
"""
LEER_JS = """
const u = $json || {}; const DUENO = '__CHAT__';
if (u.callback_query) {
  const q = u.callback_query, m = q.message || {}; const chat = String(((m.chat || {}).id) || ((q.from || {}).id) || '');
  const [ns, estado, id] = String(q.data || '').split(':');
  return [{ json: { tipo: ns === 'rx' ? 'boton' : 'ayuda', ok: chat === DUENO && String((q.from || {}).id) === DUENO, chat, cb_id: q.id,
    estado: String(estado || ''), id: Number(id) || 0, msg_id: m.message_id } }];
}
const m = u.message || {}; const chat = String((m.chat || {}).id || ''); const t = String(m.text || '').trim();
const [first, ...rest] = t.split(/\\s+/); const cmd = (first || '').toLowerCase().replace(/@.*$/, '');
const tipo = cmd === '/radar' ? 'radar' : cmd === '/ideas' ? 'ideas' : cmd === '/backlog' ? 'backlog' : 'ayuda';
return [{ json: { tipo, ok: chat === DUENO && (m.chat || {}).type === 'private', chat, tema: rest.join(' ').slice(0, 300) } }];
"""

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
    f.code("Opciones", OPCIONES_JS)
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


# ------------------------------------------------------------------ NEXUS - Comandos
def nx_edit(f: v2.Flow, name: str, msg_id: str, text: str, with_buttons: bool = True) -> str:
    p: dict = {"operation": "editMessageText", "messageType": "message", "chatId": CHAT, "messageId": msg_id, "text": text,
               "additionalFields": {"parse_mode": "HTML", "disable_web_page_preview": True}}
    if with_buttons:
        p["replyMarkup"] = "inlineKeyboard"
        p["inlineKeyboard"] = {"rows": [{"row": {"buttons": [{"text": t, "additionalFields": {"callback_data": d}} for t, d in row]}}
                                        for row in IDEA_BUTTONS]}
    return f.add(name, "n8n-nodes-base.telegram", p, 1.2, C_NX)


def flow_comandos(cred: dict, radar_id: str) -> v2.Flow:
    f = v2.Flow()
    f.add("NEXUS (Telegram)", "n8n-nodes-base.telegramTrigger", {"updates": ["message", "callback_query"], "additionalFields": {}}, 1.1, C_NX,
          webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, "nexus/comandos/telegram")))
    f.code("Leer", LEER_JS.replace("__CHAT__", CHAT))
    f.iff("¿Es el dueño?", "$json.ok === true")
    # otros chats: se ignoran (sin respuesta) y se registra solo la huella
    f.add("Huella del chat", "n8n-nodes-base.crypto", {"action": "hash", "type": "SHA256", "value": "={{ $json.chat }}",
                                                       "dataPropertyName": "huella", "encoding": "hex"}, 1)
    be(f, "Registrar ignorado", "POST", "/n8n/ignored", cred, body="={{ JSON.stringify({ chat_hash: $json.huella, tipo: $json.tipo }) }}")
    # botones de una idea
    f.iff("¿Botón?", "$json.tipo === 'boton'")
    f.add("Responder botón", "n8n-nodes-base.telegram", {"resource": "callback", "operation": "answerQuery",
                                                         "queryId": "={{ $('Leer').first().json.cb_id }}", "additionalFields": {"text": "Listo"}}, 1.2, C_NX)
    be(f, "Cambiar estado", "POST", "/n8n/ideas/{{ $('Leer').first().json.id }}/state", cred,
       body="={{ JSON.stringify({ estado: $('Leer').first().json.estado }) }}")
    nx_edit(f, "Editar idea", "={{ $('Leer').first().json.msg_id }}", "={{ $json.mensaje || 'No pude cambiar la idea.' }}")
    # /radar <tema>
    f.iff("¿/radar?", "$json.tipo === 'radar'")
    f.iff("¿Con tema?", "!!$json.tema")
    f.code("Para el Radar", "return [{ json: { tema: $('Leer').first().json.tema, origen: 'telegram' } }];")
    f.run("Informe a pedido", radar_id, wait=False)
    nx(f, "NEXUS: investigando", "={{ '🔎 Investigando «' + $('Leer').first().json.tema + '»… te aviso cuando esté (máximo 3 informes a pedido al día).' }}",
       html=False)
    nx(f, "NEXUS: uso de /radar", "Escribe el tema así: /radar fondos para startups de software en Colombia", html=False)
    # /ideas, /backlog, /ayuda
    f.iff("¿Lista?", "$json.tipo === 'ideas' || $json.tipo === 'backlog'")
    be(f, "Leer lista", "GET", "/n8n/list?que={{ $('Leer').first().json.tipo }}", cred)
    be(f, "Leer ayuda", "GET", "/n8n/help", cred)
    nx(f, "NEXUS: respuesta", "={{ $json.mensaje || 'Sin datos.' }}")
    f.chain("NEXUS (Telegram)", "Leer", "¿Es el dueño?", "¿Botón?", "Responder botón", "Cambiar estado", "Editar idea")
    f.link("¿Es el dueño?", "Huella del chat", 1)
    f.link("Huella del chat", "Registrar ignorado")
    f.link("¿Botón?", "¿/radar?", 1)
    f.chain("¿/radar?", "¿Con tema?", "Para el Radar", "Informe a pedido")
    f.link("Para el Radar", "NEXUS: investigando")
    f.link("¿Con tema?", "NEXUS: uso de /radar", 1)
    f.link("¿/radar?", "¿Lista?", 1)
    f.chain("¿Lista?", "Leer lista", "NEXUS: respuesta")
    f.link("¿Lista?", "Leer ayuda", 1)
    f.link("Leer ayuda", "NEXUS: respuesta")
    # la consola cambio el estado: se edita el mensaje en NEXUS (el backend llama con X-Nexa-Token)
    f.add("Desde la consola", "n8n-nodes-base.webhook", {"httpMethod": "POST", "path": "nexus-editar", "responseMode": "onReceived",
                                                         "authentication": "headerAuth", "options": {}}, 2, cred,
          webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, "hook/nexus-editar")))
    f.iff("¿Tiene mensaje?", "!!($json.body || {}).message_id")
    f.code("Datos del mensaje", "const b = $json.body || {}; return [{ json: { message_id: b.message_id, mensaje: b.mensaje, botones: b.botones } }];")
    nx_edit(f, "Editar desde la consola", "={{ $json.message_id }}", "={{ $json.mensaje }}")
    f.chain("Desde la consola", "¿Tiene mensaje?", "Datos del mensaje", "Editar desde la consola")
    fix(f, F_CMD, {"NEXUS (Telegram)": (0, 200), "Leer": (240, 200), "¿Es el dueño?": (480, 200), "Huella del chat": (720, 480),
                   "Registrar ignorado": (960, 480), "¿Botón?": (720, 120), "Responder botón": (960, 0), "Cambiar estado": (1200, 0),
                   "Editar idea": (1440, 0), "¿/radar?": (960, 200), "¿Con tema?": (1200, 160), "Para el Radar": (1440, 120),
                   "Informe a pedido": (1680, 60), "NEXUS: investigando": (1680, 180), "NEXUS: uso de /radar": (1440, 280),
                   "¿Lista?": (1200, 360), "Leer lista": (1440, 340), "Leer ayuda": (1440, 440), "NEXUS: respuesta": (1680, 380),
                   "Desde la consola": (0, 720), "¿Tiene mensaje?": (240, 720), "Datos del mensaje": (480, 720), "Editar desde la consola": (720, 720)})
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
