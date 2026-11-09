"""Flujos de n8n de VOLTAGE (whatsapp_group_reports, 072A). Idempotente: crea o actualiza.

1) "VOLTAGE envios": webhook POST /webhook/voltage-envios con cabecera X-Clonexa-Secret ->
   descarga adjuntos (enlace firmado + cabecera) -> Evolution (texto o documento) o Gmail de
   Clonexa (con o sin adjuntos) -> responde {ok, error} a Clonexa. Si falla el ultimo intento,
   avisa por correo a Clonexa.
2) "VOLTAGE timesheets": Evolution (messages.upsert, ruta secreta) y Gmail de Clonexa (correos con
   adjuntos) -> Clonexa decide (classify) -> Drive VOLTAGE/Timesheets/<operacion>/<aaaa-mm-dd> ->
   Clonexa anota la foto (received) -> "Recibida ✅" por WhatsApp. Otros mensajes privados:
   respuesta automatica una vez al dia (lo decide Clonexa). Nunca responde en los grupos salvo la
   confirmacion de la foto del grupo semanal.

Credenciales que crea si no existen (valores leidos de C:\\Users\\valef\\Desktop\\referencias, nunca
impresos): "Evolution VOLTAGE" (apikey) y "Clonexa VOLTAGE secreto" (X-Clonexa-Secret). Usa
"Gmail account" y, si existe, la credencial de Google Drive (tipo googleDriveOAuth2Api); sin ella
el flujo de timesheets queda creado pero INACTIVO.
Uso: py -3.11 ops/n8n/voltage_group_reports_flow.py [--export carpeta]
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
EVOLUTION = "https://evolution-api-production-10ae.up.railway.app"
INSTANCE = "voltage"
CLONEXA = "https://clonexa-backend-production.up.railway.app/api/v1/group-reports"
COMPANY = "f1e8f774-f052-49ca-880a-268805f07db0"
ALERT_TO = "clonexasaas@gmail.com"
GMAIL = {"id": "dCD1TC3AgRsLjPp6", "name": "Gmail account"}
SEND_NAME, TS_NAME = "VOLTAGE envios", "VOLTAGE timesheets"
EVO_CRED, SECRET_CRED = "Evolution VOLTAGE", "Clonexa VOLTAGE secreto"


def _read(name: str) -> str:
    value = (REFS / name).read_text("utf-8").strip()
    if len(value) < 20:
        sys.exit(f"{name} no tiene el valor esperado (no se muestra).")
    return value


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


def credential(name: str, header: str, value: str) -> dict:
    for c in call("GET", "/credentials?limit=100").get("data", []):
        if c["name"] == name:
            return {"id": c["id"], "name": name}
    made = call("POST", "/credentials", {"name": name, "type": "httpHeaderAuth", "data": {"name": header, "value": value}})
    return {"id": made["id"], "name": name}


def drive_credential() -> dict | None:
    for c in call("GET", "/credentials?limit=100").get("data", []):
        if c["type"] == "googleDriveOAuth2Api":
            return {"id": c["id"], "name": c["name"]}
    return None


# ------------------------------------------------------------------ piezas
def node(name, type_, version, pos, params, creds=None, **extra):
    n = {"parameters": params, "name": name, "type": f"n8n-nodes-base.{type_}", "typeVersion": version, "position": pos}
    if creds:
        n["credentials"] = creds
    n.update(extra)
    return n


def http_json(name, pos, url, body_expr, cred_key, cred, method="POST", on_error=True):
    params = {"method": method, "url": url, "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
              "sendBody": True, "specifyBody": "json", "jsonBody": body_expr, "options": {"timeout": 60000}}
    extra = {"onError": "continueRegularOutput"} if on_error else {}
    return node(name, "httpRequest", 4.2, pos, params, {cred_key: cred}, **extra)


def cond_true(expr):
    return {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                           "conditions": [{"id": "c1", "leftValue": expr, "rightValue": True,
                                           "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                           "combinator": "and"}, "options": {}}


def switch(values):
    rules = []
    for v in values:
        rules.append({"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                                     "conditions": [{"leftValue": "={{ $json.route }}", "rightValue": v,
                                                     "operator": {"type": "string", "operation": "equals"}}], "combinator": "and"},
                      "renameOutput": True, "outputKey": v})
    return {"rules": {"values": rules}, "options": {}}


def links(pairs):
    out: dict = {}
    for src, dst, *rest in pairs:
        idx = rest[0] if rest else 0
        main = out.setdefault(src, {"main": []})["main"]
        while len(main) <= idx:
            main.append([])
        main[idx].append({"node": dst, "type": "main", "index": 0})
    return out


SETTINGS = {"executionOrder": "v1", "timezone": "America/New_York", "saveDataSuccessExecution": "none", "saveDataErrorExecution": "all"}


# ------------------------------------------------------------------ 1) envios
JUNTAR = r"""
const b = $('Desde Clonexa').first().json.body || {};
const items = $input.all();
const binary = {}; const props = []; let media = null;
for (let i = 0; i < items.length; i++) {
  const it = items[i];
  if (!it.binary || !it.binary.data) continue;
  const meta = (b.attachments || [])[i] || {};
  const key = 'att' + i;
  binary[key] = { ...it.binary.data, fileName: meta.file_name || it.binary.data.fileName, mimeType: meta.mimetype || it.binary.data.mimeType };
  props.push(key);
  if (!media) {
    const buf = await this.helpers.getBinaryDataBuffer(i, 'data');
    const mt = meta.mimetype || it.binary.data.mimeType || 'application/octet-stream';
    media = { b64: buf.toString('base64'), file_name: meta.file_name || 'archivo', mimetype: mt, mediatype: String(mt).startsWith('image/') ? 'image' : 'document' };
  }
}
const isMail = b.channel === 'email';
const route = isMail ? (props.length ? 'mail_att' : 'mail') : (media ? 'wa_doc' : 'wa_text');
return [{ json: { ...b, route, to_text: Array.isArray(b.to) ? b.to.join(',') : String(b.to || ''), att_props: props.join(','), media }, binary }];
"""
ADJUNTOS = r"""
const b = $input.first().json.body || {};
const atts = Array.isArray(b.attachments) ? b.attachments : [];
if (!atts.length) return [{ json: { none: true } }];
return atts.map((a, i) => ({ json: { url: a.url, file_name: a.file_name, mimetype: a.mimetype, idx: i, none: false } }));
"""
RESULTADO = r"""
const it = $input.first().json || {};
const b = $('Desde Clonexa').first().json.body || {};
let err = null;
if (it.error) err = typeof it.error === 'string' ? it.error : (it.error.message || JSON.stringify(it.error));
if (!err && it.status && String(it.status).toUpperCase() === 'ERROR') err = JSON.stringify(it.response || it).slice(0, 280);
return [{ json: { ok: !err, error: err ? String(err).slice(0, 280) : null, delivery_id: b.delivery_id,
  last: !!err && Number(b.attempt || 0) >= Number(b.max_attempts || 3), kind_label: b.kind_label || b.kind, destination: b.destination } }];
"""


def send_flow(secret_cred, evo_cred) -> dict:
    evo = f"{EVOLUTION}/message"
    nodes = [
        node("Desde Clonexa", "webhook", 2, [0, 300], {"httpMethod": "POST", "path": "voltage-envios", "authentication": "headerAuth",
                                                      "responseMode": "responseNode", "options": {}}, {"httpHeaderAuth": secret_cred},
             webhookId="voltage-envios"),
        node("Adjuntos", "code", 2, [220, 300], {"jsCode": ADJUNTOS}),
        node("Hay adjuntos", "if", 2, [440, 300], cond_true("={{ $json.none === true }}")),
        node("Descargar", "httpRequest", 4.2, [660, 400], {"url": "={{ $json.url }}", "authentication": "genericCredentialType",
                                                          "genericAuthType": "httpHeaderAuth",
                                                          "options": {"response": {"response": {"responseFormat": "file", "outputPropertyName": "data"}}}},
             {"httpHeaderAuth": secret_cred}, onError="continueRegularOutput"),
        node("Juntar", "code", 2, [880, 300], {"jsCode": JUNTAR}),
        node("Canal", "switch", 3, [1100, 300], switch(["wa_text", "wa_doc", "mail_att", "mail"])),
        http_json("WhatsApp texto", [1340, 100], f"{evo}/sendText/{INSTANCE}",
                  "={{ JSON.stringify({ number: $json.to_text, text: $json.text }) }}", "httpHeaderAuth", evo_cred),
        http_json("WhatsApp imagen o documento", [1340, 250], f"{evo}/sendMedia/{INSTANCE}",
                  "={{ JSON.stringify({ number: $json.to_text, mediatype: $json.media.mediatype, mimetype: $json.media.mimetype, fileName: $json.media.file_name, caption: $json.text, media: $json.media.b64 }) }}",
                  "httpHeaderAuth", evo_cred),
        node("Fallo la imagen", "if", 2, [1560, 200], cond_true("={{ !!$json.error }}")),
        http_json("WhatsApp texto (respaldo)", [1780, 120], f"{evo}/sendText/{INSTANCE}",
                  "={{ JSON.stringify({ number: $('Juntar').item.json.to_text, text: $('Juntar').item.json.text }) }}", "httpHeaderAuth", evo_cred),
        node("Correo con adjuntos", "gmail", 2.1, [1340, 400], {"sendTo": "={{ $json.to_text }}", "subject": "={{ $json.subject }}", "emailType": "={{ $json.html ? 'html' : 'text' }}",
                                                               "message": "={{ $json.text }}",
                                                               "options": {"appendAttribution": False,
                                                                           "attachmentsUi": {"attachmentsBinary": [{"property": "={{ $json.att_props }}"}]}}},
             {"gmailOAuth2": GMAIL}, onError="continueRegularOutput"),
        node("Correo", "gmail", 2.1, [1340, 550], {"sendTo": "={{ $json.to_text }}", "subject": "={{ $json.subject }}", "emailType": "={{ $json.html ? 'html' : 'text' }}",
                                                  "message": "={{ $json.text }}", "options": {"appendAttribution": False}},
             {"gmailOAuth2": GMAIL}, onError="continueRegularOutput"),
        node("Resultado", "code", 2, [2000, 300], {"jsCode": RESULTADO}),
        node("Responder", "respondToWebhook", 1.1, [1800, 300], {"respondWith": "json",
                                                                "responseBody": "={{ JSON.stringify({ ok: $json.ok, error: $json.error }) }}", "options": {}}),
        node("Ultimo intento fallo", "if", 2, [2020, 300], cond_true("={{ $json.last === true }}")),
        node("Avisar falla", "gmail", 2.1, [2240, 300], {"sendTo": ALERT_TO, "subject": "=[VOLTAGE] Falló un aviso: {{ $json.kind_label }}",
                                                        "emailType": "text",
                                                        "message": "=No se pudo entregar después de 3 intentos.\nTipo: {{ $json.kind_label }}\nDestino: {{ $json.destination }}\nError: {{ $json.error }}\nMira el Historial de avisos en el portal.",
                                                        "options": {"appendAttribution": False}}, {"gmailOAuth2": GMAIL}),
    ]
    conns = links([("Desde Clonexa", "Adjuntos"), ("Adjuntos", "Hay adjuntos"), ("Hay adjuntos", "Juntar", 0), ("Hay adjuntos", "Descargar", 1),
                   ("Descargar", "Juntar"), ("Canal", "WhatsApp texto", 0), ("Canal", "WhatsApp imagen o documento", 1), ("Canal", "Correo con adjuntos", 2),
                   ("Canal", "Correo", 3), ("Juntar", "Canal"), ("WhatsApp texto", "Resultado"), ("WhatsApp imagen o documento", "Fallo la imagen"), ("Fallo la imagen", "WhatsApp texto (respaldo)", 0),
                   ("Fallo la imagen", "Resultado", 1), ("WhatsApp texto (respaldo)", "Resultado"),
                   ("Correo con adjuntos", "Resultado"), ("Correo", "Resultado"), ("Resultado", "Responder"), ("Responder", "Ultimo intento fallo"),
                   ("Ultimo intento fallo", "Avisar falla", 0)])
    return {"name": SEND_NAME, "nodes": nodes, "connections": conns, "settings": SETTINGS}


# ------------------------------------------------------------------ 2) timesheets
LEER_WA = r"""
const b = $input.first().json.body || {};
const ev = String(b.event || '').toLowerCase().replace('_', '.');
if (ev !== 'messages.upsert' || (b.instance && b.instance !== 'voltage')) return [];
const d = b.data || {}; const key = d.key || {};
if (key.fromMe) return [];
const jid = String(key.remoteJid || '');
const isGroup = jid.endsWith('@g.us');
const m = d.message || {};
const doc = m.documentMessage || (m.documentWithCaptionMessage && m.documentWithCaptionMessage.message && m.documentWithCaptionMessage.message.documentMessage);
const media = m.imageMessage || doc;
const mt = media ? String(media.mimetype || (m.imageMessage ? 'image/jpeg' : '')).split(';')[0] : '';
const okType = !!media && (mt.startsWith('image/') || mt === 'application/pdf');
if (isGroup && !okType) return [];
if (d.messageType === 'protocolMessage' || m.protocolMessage || m.reactionMessage) return [];
const b64 = m.base64 || d.base64 || '';
const ext = mt === 'application/pdf' ? 'pdf' : ((mt.split('/')[1] || 'jpg'));
const sender = isGroup ? jid : String(key.senderPn || key.remoteJidAlt || jid);
const stamp = new Date().toISOString().replace(/[:.]/g, '-');
return [{ json: { channel: 'whatsapp', jid: sender, is_group: isGroup, has_media: okType && !!b64, from_me: false, b64, mimetype: mt,
  file_name: (doc && doc.fileName) || `timesheet_${stamp}.${ext}` } }];
"""
LEER_MAIL = r"""
const it = $input.first();
const j = it.json || {};
const from = (j.from && j.from.value && j.from.value[0] && j.from.value[0].address) || j.from?.text || '';
const keys = Object.keys(it.binary || {}).filter((k) => { const t = String(it.binary[k].mimeType || ''); return t.startsWith('image/') || t === 'application/pdf'; });
return [{ json: { channel: 'email', from_email: from, subject: j.subject || '', has_media: keys.length > 0, keys }, binary: it.binary || {} }];
"""
CARPETA = r"""
const c = $input.first().json || {};
const prev = $('__CLASIFICAR__').first().json || {};
const files = (c.files || []);
return [{ json: { ...prev, folder_id: files.length ? files[0].id : '', create: !files.length } }];
"""
ARCHIVO_WA = r"""
const c = $input.first().json || {};
const prev = $('Carpeta del dia WA').first().json;
const src = $('Leer WhatsApp').first().json;
const bin = await this.helpers.prepareBinaryData(Buffer.from(src.b64, 'base64'), src.file_name, src.mimetype);
return [{ json: { ...prev, folder_id: c.id || prev.folder_id, file_name: src.file_name, sender: src.jid }, binary: { data: bin } }];
"""
ARCHIVOS_MAIL = r"""
const c = $input.first().json || {};
const prev = $('Carpeta del dia correo').first().json;
const src = $('Leer correo').first();
return (src.json.keys || []).map((k) => ({ json: { ...prev, folder_id: c.id || prev.folder_id, file_name: src.binary[k].fileName || k, sender: src.json.from_email },
  binary: { data: src.binary[k] } }));
"""


def drive_nodes(suffix, x, y, classify_name, drive_cred, archive_code):
    q = ("={{ \"name='\" + $json.date + \"' and '\" + $json.drive_parent_id + \"' in parents and "
         "mimeType='application/vnd.google-apps.folder' and trashed=false\" }}")
    dcred = {"googleDriveOAuth2Api": drive_cred} if drive_cred else None
    return [
        node(f"Buscar dia {suffix}", "httpRequest", 4.2, [x, y], {"url": "https://www.googleapis.com/drive/v3/files", "authentication": "predefinedCredentialType",
                                                                 "nodeCredentialType": "googleDriveOAuth2Api", "sendQuery": True,
                                                                 "queryParameters": {"parameters": [{"name": "q", "value": q}, {"name": "fields", "value": "files(id,name)"}]},
                                                                 "options": {}}, dcred),
        node(f"Carpeta del dia {suffix}", "code", 2, [x + 220, y], {"jsCode": CARPETA.replace("__CLASIFICAR__", classify_name)}),
        node(f"Crear dia {suffix}", "if", 2, [x + 440, y], cond_true("={{ $json.create === true }}")),
        node(f"Nueva carpeta {suffix}", "httpRequest", 4.2, [x + 660, y - 100], {"method": "POST", "url": "https://www.googleapis.com/drive/v3/files",
                                                                                "authentication": "predefinedCredentialType", "nodeCredentialType": "googleDriveOAuth2Api",
                                                                                "sendBody": True, "specifyBody": "json",
                                                                                "jsonBody": "={{ JSON.stringify({ name: $json.date, mimeType: 'application/vnd.google-apps.folder', parents: [$json.drive_parent_id] }) }}",
                                                                                "options": {}}, dcred),
        node(f"Archivo {suffix}", "code", 2, [x + 880, y], {"jsCode": archive_code}),
        node(f"Subir {suffix}", "googleDrive", 3, [x + 1100, y], {"name": "={{ $json.file_name }}",
                                                                  "driveId": {"__rl": True, "value": "My Drive", "mode": "list", "cachedResultName": "My Drive"},
                                                                  "folderId": {"__rl": True, "value": "={{ $json.folder_id }}", "mode": "id"},
                                                                  "options": {}}, dcred),
        http_json(f"Avisar a Clonexa {suffix}", [x + 1320, y], f"{CLONEXA}/inbound/{COMPANY}/received",
                  "={{ JSON.stringify({ location_id: $('Archivo " + suffix + "').item.json.location_id, source: '" + ("whatsapp" if suffix == "WA" else "email") +
                  "', sender: $('Archivo " + suffix + "').item.json.sender, file_name: $('Archivo " + suffix + "').item.json.file_name, drive_url: 'https://drive.google.com/file/d/' + $json.id }) }}",
                  "httpHeaderAuth", None, on_error=False),
    ]


def ts_flow(secret_cred, evo_cred, drive_cred, path_secret) -> dict:
    nodes = [
        node("Evolution", "webhook", 2, [0, 200], {"httpMethod": "POST", "path": f"voltage-ts-{path_secret}", "responseMode": "onReceived", "options": {}},
             webhookId="voltage-ts"),
        node("Leer WhatsApp", "code", 2, [220, 200], {"jsCode": LEER_WA}),
        http_json("Clasificar WA", [440, 200], f"{CLONEXA}/inbound/{COMPANY}/classify",
                  "={{ JSON.stringify({ channel: 'whatsapp', jid: $json.jid, is_group: $json.is_group, has_media: $json.has_media, from_me: false }) }}",
                  "httpHeaderAuth", secret_cred, on_error=False),
        node("Accion WA", "switch", 3, [660, 200], {**switch(["save", "autoreply"]),
                                                    "rules": {"values": [{**r, "conditions": {**r["conditions"], "conditions": [{**r["conditions"]["conditions"][0], "leftValue": "={{ $json.action }}"}]}}
                                                                         for r in switch(["save", "autoreply"])["rules"]["values"]]}}),
        *drive_nodes("WA", 880, 120, "Clasificar WA", drive_cred, ARCHIVO_WA),
        node("Hay respuesta", "if", 2, [2420, 120], cond_true("={{ !!$('Archivo WA').item.json.reply }}")),
        http_json("Recibida", [2640, 120], f"{EVOLUTION}/message/sendText/{INSTANCE}",
                  "={{ JSON.stringify({ number: $('Archivo WA').item.json.reply.to, text: $('Archivo WA').item.json.reply.text }) }}", "httpHeaderAuth", evo_cred),
        http_json("Respuesta automatica", [880, 360], f"{EVOLUTION}/message/sendText/{INSTANCE}",
                  "={{ JSON.stringify({ number: $json.reply.to, text: $json.reply.text }) }}", "httpHeaderAuth", evo_cred),
        node("Correo Clonexa", "gmailTrigger", 1.2, [0, 600], {"pollTimes": {"item": [{"mode": "everyMinute"}]}, "simple": False,
                                                              "filters": {"q": "has:attachment -from:me newer_than:2d"},
                                                              "options": {"downloadAttachments": True}}, {"gmailOAuth2": GMAIL}),
        node("Leer correo", "code", 2, [220, 600], {"jsCode": LEER_MAIL}),
        http_json("Clasificar correo", [440, 600], f"{CLONEXA}/inbound/{COMPANY}/classify",
                  "={{ JSON.stringify({ channel: 'email', from_email: $json.from_email, subject: $json.subject, has_media: $json.has_media }) }}",
                  "httpHeaderAuth", secret_cred, on_error=False),
        node("Guardar correo", "if", 2, [660, 600], cond_true("={{ $json.action === 'save' }}")),
        *drive_nodes("correo", 880, 600, "Clasificar correo", drive_cred, ARCHIVOS_MAIL),
    ]
    for n in nodes:
        if n["name"].startswith("Avisar a Clonexa"):
            n["credentials"] = {"httpHeaderAuth": secret_cred}
    pairs = [("Evolution", "Leer WhatsApp"), ("Leer WhatsApp", "Clasificar WA"), ("Clasificar WA", "Accion WA"),
             ("Accion WA", "Buscar dia WA", 0), ("Accion WA", "Respuesta automatica", 1),
             ("Correo Clonexa", "Leer correo"), ("Leer correo", "Clasificar correo"), ("Clasificar correo", "Guardar correo"),
             ("Guardar correo", "Buscar dia correo", 0)]
    for s in ("WA", "correo"):
        pairs += [(f"Buscar dia {s}", f"Carpeta del dia {s}"), (f"Carpeta del dia {s}", f"Crear dia {s}"),
                  (f"Crear dia {s}", f"Nueva carpeta {s}", 0), (f"Crear dia {s}", f"Archivo {s}", 1),
                  (f"Nueva carpeta {s}", f"Archivo {s}"), (f"Archivo {s}", f"Subir {s}"), (f"Subir {s}", f"Avisar a Clonexa {s}")]
    pairs += [("Avisar a Clonexa WA", "Hay respuesta"), ("Hay respuesta", "Recibida", 0)]
    return {"name": TS_NAME, "nodes": nodes, "connections": links(pairs), "settings": SETTINGS}


# ------------------------------------------------------------------ despliegue
def upsert(flow: dict, activate: bool) -> str:
    found = next((w for w in call("GET", "/workflows?limit=200").get("data", []) if w["name"] == flow["name"]), None)
    if found:
        call("PUT", f"/workflows/{found['id']}", flow)
        wid = found["id"]
    else:
        wid = call("POST", "/workflows", flow)["id"]
    if activate:
        call("POST", f"/workflows/{wid}/activate")
    else:
        try:
            call("POST", f"/workflows/{wid}/deactivate")
        except SystemExit:
            pass
    return wid


def scrub(flow: dict, secrets: list[str]) -> dict:
    text = json.dumps(flow, ensure_ascii=False, indent=1)
    for s in secrets:
        text = text.replace(s, "<SECRETO_EN_REFERENCIAS>")
    return json.loads(text)


def main() -> None:
    secret = _read("voltage-reports-n8n-secret.txt")
    path_secret = _read("evolution-webhook-path.txt")
    secret_cred = credential(SECRET_CRED, "X-Clonexa-Secret", secret)
    evo_cred = credential(EVO_CRED, "apikey", _read("evolution-api-key.txt"))
    drive = drive_credential()
    send = send_flow(secret_cred, evo_cred)
    ts = ts_flow(secret_cred, evo_cred, drive, path_secret)
    if "--export" in sys.argv:
        folder = Path(sys.argv[sys.argv.index("--export") + 1])
        for f in (send, ts):
            (folder / (f["name"].lower().replace(" ", "_") + ".json")).write_text(
                json.dumps(scrub(copy.deepcopy(f), [path_secret]), ensure_ascii=False, indent=1), "utf-8")
        print("exportados (sin secretos)")
        return
    sid = upsert(send, activate=True)
    tid = upsert(ts, activate=drive is not None)
    print(f"{SEND_NAME}: {sid} activo")
    print(f"{TS_NAME}: {tid} {'activo' if drive else 'INACTIVO: falta conectar Google Drive en n8n'}")


if __name__ == "__main__":
    main()
