"""Nexa v2: contenido desde el calendario (Google Sheet), vista previa y aprobacion por Telegram,
plan B con carrusel, /tema y alertas de error. Crea o actualiza (idempotente, por nombre):

- "Nexa - Archivo temporal"  webhook GET nexa-archivo: entrega un archivo de Drive con firma HMAC que
                              vence en 1 hora (x=jpg lo convierte a JPEG en el backend). No hace
                              publico nada en Drive.
- "Nexa - Errores"            Error Workflow de todos los flujos Nexa: flujo, paso, error corto y hora.
- "Nexa - Mostrar pieza"      sub-flujo: video o album + texto IG/FB + [Aprobar] [Cambiar texto] [Descartar].
- "Nexa - Plan B"             sub-flujo: carrusel con Claude + backend (Pillow) -> Drive -> fila -> vista previa;
                              formato Avatar: HeyGen v3 si hay saldo, si no aviso con 3 botones.
- "Nexa - Vista previa"       todos los dias 18:00 Bogota (manana "Listo para aprobar"; L/M/V sin pieza -> plan B).
- "Nexa - Publicar del dia"   L/M/V 12:00 Bogota: publica lo "Aprobado" de hoy (IG, FB, YouTube, LinkedIn);
                              webhook con simular=1 arma todo sin enviar.
Y cambia los existentes:
- "Nexa - Bot de comandos": botones (callback_query), respuesta con texto nuevo, /tema, /temas, /planb,
                            ayuda nueva y /saldo con HeyGen v3.
- "Nexa - Publicar en todas": disparador de los lunes 7:00 apagado (webhooks intactos), HeyGen v3
                            (users/me, POST /v3/videos, GET /v3/videos/{id}) con el mismo avatar y voz,
                            error de saldo/clave de Claude con motivo claro, aviso de saldo con botones.
- errorWorkflow = "Nexa - Errores" en todos los flujos "Nexa - *".

Secretos (nunca en el repo, nunca se imprimen): C:\\Users\\valef\\Desktop\\referencias\\
  n8n-key.txt, nexa-ingest-token.txt (= NEXA_INGEST_TOKEN del backend), nexa-archivo-secret.txt
  (firma de enlaces temporales), nexa-v2-webhook-secret.txt (webhooks de prueba). La clave de los
  enlaces viejos (?k=) se lee del flujo "Nexa - Publicar en todas".
Antes de cambiar un flujo existente guarda su JSON en respaldos-clonexa\\n8n\\<fecha>\\.
Uso: py -3.11 ops/n8n/nexa_v2_flows.py
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import re
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.services import nexa_ad  # noqa: E402  catalogo de escenas demo y emoji permitidos

BASE = "https://main-production-54df.up.railway.app"
API = BASE + "/api/v1"
BACKEND = "https://clonexa-backend-production.up.railway.app"
LANDING = "https://clonexa-landing-production.up.railway.app/"
REFS = Path(r"C:\Users\valef\Desktop\referencias")
BACKUPS = Path(r"C:\Users\valef\Desktop\respaldos-clonexa\n8n")
CHAT = "5126243056"
SHEET = "1A0qx99Pw4vk3EwC_qdi4XkLBWxmBysSKxJIggGKSpwg"
ROOT = "10cWifMMbdgD_7Cq-Cr4Cyao93ymxV5je"
IG_ID = "17841457985115880"
PAGE_ID = "1397005896827159"
AVATAR_ID = "e2e5dbd302844e8892f9ca447042640d"  # "Nexa" (talking photo de v2 = avatar_id de foto en v3)
VOICE_ID = "145ee9caa9a344d9bf61ddd3d95de7b1"
OLD_FLOW = "Z3M4w25F42Snki5j"
BOT_FLOW = "adr1SajrF8PMvXp5"

C_DRIVE = {"googleDriveOAuth2Api": {"id": "dj7S7oBBJNi7vjxr", "name": "Google Drive account"}}
C_TG = {"telegramApi": {"id": "Somdc8F0zAOWWHcY", "name": "Telegram Nexa"}}
C_META = {"facebookGraphApi": {"id": "JRMZkw2y1ZaqunGk", "name": "Meta Clonexa"}}
C_YT = {"youTubeOAuth2Api": {"id": "64cmCUx8wJLJIkdN", "name": "YouTube account"}}
C_LI = {"linkedInOAuth2Api": {"id": "cgHcbQnrBq8Y3hGD", "name": "LinkedIn account"}}
C_ANTH = {"anthropicApi": {"id": "X6Q45d5OD6gz0wiS", "name": "Anthropic Nexa"}}
C_HEYGEN = {"httpHeaderAuth": {"id": "XAKoudIwrZhCuy6g", "name": "HeyGen Nexa"}}
BACKEND_CRED_NAME = "Nexa backend (X-Nexa-Token)"
SETTINGS_KEYS = ("executionOrder", "saveDataErrorExecution", "saveDataSuccessExecution", "saveManualExecutions",
                 "saveExecutionProgress", "timezone", "errorWorkflow", "callerPolicy", "executionTimeout")


# ------------------------------------------------------------------ API n8n
def _secret(name: str, pattern: str = r"[\w-]{20,}") -> str:
    raw = (REFS / name).read_text(encoding="utf-8", errors="replace")
    for line in raw.splitlines():
        if re.fullmatch(pattern, line.strip()):
            return line.strip()
    sys.exit(f"{name} no tiene el valor esperado (no se muestra el contenido).")


KEY = _secret("n8n-key.txt", r"eyJ[\w-]+\.[\w-]+\.[\w-]+|n8n_api_[\w-]{20,}")


def call(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method,
                                 headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"n8n {method} {path} -> {e.code}: {e.read().decode()[:400]}")


def all_workflows() -> list[dict]:
    out, cur = [], None
    while True:
        r = call("GET", "/workflows?limit=100" + (f"&cursor={cur}" if cur else ""))
        out += r["data"]
        cur = r.get("nextCursor")
        if not cur:
            return out


def backup(flow: dict) -> None:
    d = BACKUPS / dt.date.today().isoformat()
    d.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%H%M%S")
    name = flow["name"].replace(" ", "_").replace("/", "-")
    (d / f"{name}_{flow['id']}_{stamp}.json").write_text(json.dumps(flow, ensure_ascii=False, indent=1), encoding="utf-8")


def body_of(name: str, nodes: list, connections: dict, settings: dict) -> dict:
    return {"name": name, "nodes": nodes, "connections": connections,
            "settings": {k: v for k, v in settings.items() if k in SETTINGS_KEYS}}


def upsert(name: str, nodes: list, connections: dict, settings: dict, activate: bool, existing: dict) -> str:
    settings = {"executionOrder": "v1", "timezone": "America/Bogota", "saveManualExecutions": True, **settings}
    was = name in existing
    if was:
        wid = existing[name]["id"]
        cur = call("GET", f"/workflows/{wid}")
        backup(cur)
        if cur.get("active"):
            call("POST", f"/workflows/{wid}/deactivate")
        call("PUT", f"/workflows/{wid}", body_of(name, nodes, connections, settings))
    else:
        wid = call("POST", "/workflows", body_of(name, nodes, connections, settings))["id"]
        existing[name] = {"id": wid}
    if activate:
        call("POST", f"/workflows/{wid}/activate")
    print(("actualizado" if was else "creado"), name, wid, "(activo)" if activate else "")
    return wid


def backend_credential() -> dict:
    token = _secret("nexa-ingest-token.txt")
    for c in call("GET", "/credentials?limit=100").get("data", []):
        if c["name"] == BACKEND_CRED_NAME:
            return {"httpHeaderAuth": {"id": c["id"], "name": c["name"]}}
    c = call("POST", "/credentials", {"name": BACKEND_CRED_NAME, "type": "httpHeaderAuth", "data": {"name": "X-Nexa-Token", "value": token}})
    return {"httpHeaderAuth": {"id": c["id"], "name": BACKEND_CRED_NAME}}


# ------------------------------------------------------------------ constructores de nodos
class Flow:
    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.conns: dict = {}
        self._x = 0

    def add(self, name: str, type_: str, params: dict, tv: float = 1, creds: dict | None = None, pos=None, **extra) -> str:
        if pos is None:
            pos = [self._x, 0]
            self._x += 240
        n = {"id": str(uuid.uuid5(uuid.NAMESPACE_URL, "nexa-v2/" + name)), "name": name, "type": type_, "typeVersion": tv,
             "position": pos, "parameters": params}
        if creds:
            n["credentials"] = copy.deepcopy(creds)
        n.update(extra)
        self.nodes.append(n)
        return name

    def link(self, a: str, b: str, out: int = 0) -> None:
        main = self.conns.setdefault(a, {"main": []})["main"]
        while len(main) <= out:
            main.append([])
        main[out].append({"node": b, "type": "main", "index": 0})

    def chain(self, *names: str) -> None:
        for a, b in zip(names, names[1:]):
            self.link(a, b)

    # tipos
    def code(self, name: str, js: str, **extra) -> str:
        return self.add(name, "n8n-nodes-base.code", {"jsCode": js}, 2, **extra)

    def iff(self, name: str, expr: str) -> str:
        return self.add(name, "n8n-nodes-base.if", {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                        "conditions": [{"id": str(uuid.uuid5(uuid.NAMESPACE_URL, "cond/" + name)), "leftValue": "={{ " + expr + " }}", "rightValue": "",
                                        "operator": {"type": "boolean", "operation": "true", "singleValue": True}}], "combinator": "and"}, "options": {}}, 2)

    def http(self, name: str, method: str, url: str, creds: dict | None = None, *, cred_type: str | None = None, json_body: str | None = None,
             query: dict | None = None, headers: dict | None = None, fmt: str | None = None, full: bool = False, binary_in: str | None = None,
             timeout: int = 120000, **extra) -> str:
        p: dict = {"method": method, "url": url, "options": {"response": {"response": {"neverError": True}}, "timeout": timeout}}
        if fmt:
            p["options"]["response"]["response"]["responseFormat"] = fmt
            if fmt == "file":
                p["options"]["response"]["response"]["outputPropertyName"] = "data"
        if full:
            p["options"]["response"]["response"]["fullResponse"] = True
        if creds:
            t = next(iter(creds))
            if t == "httpHeaderAuth":
                p.update({"authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth"})
            else:
                p.update({"authentication": "predefinedCredentialType", "nodeCredentialType": cred_type or t})
        if query:
            p.update({"sendQuery": True, "queryParameters": {"parameters": [{"name": k, "value": v} for k, v in query.items()]}})
        if headers:
            p.update({"sendHeaders": True, "headerParameters": {"parameters": [{"name": k, "value": v} for k, v in headers.items()]}})
        if json_body is not None:
            p.update({"sendBody": True, "specifyBody": "json", "jsonBody": json_body})
        if binary_in:
            p.update({"sendBody": True, "contentType": "binaryData", "inputDataFieldName": binary_in})
        return self.add(name, "n8n-nodes-base.httpRequest", p, 4.2, creds, onError="continueRegularOutput", **extra)

    def tg(self, name: str, text: str, buttons: list[list[tuple[str, str]]] | None = None, html: bool = True, chat: str = CHAT, **extra) -> str:
        p: dict = {"chatId": chat, "text": text, "additionalFields": {"appendAttribution": False, "disable_web_page_preview": True}}
        if html:
            p["additionalFields"]["parse_mode"] = "HTML"
        if buttons:
            p["replyMarkup"] = "inlineKeyboard"
            p["inlineKeyboard"] = {"rows": [{"row": {"buttons": [{"text": t, "additionalFields": {"callback_data": d}} for t, d in row]}} for row in buttons]}
        return self.add(name, "n8n-nodes-base.telegram", p, 1.2, C_TG, **extra)

    def wait(self, name: str, seconds: int) -> str:
        return self.add(name, "n8n-nodes-base.wait", {"amount": seconds, "unit": "seconds"}, 1.1, webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, "wait/" + name)))

    def run(self, name: str, workflow_id: str, wait: bool) -> str:
        return self.add(name, "n8n-nodes-base.executeWorkflow", {"source": "database", "workflowId": {"__rl": True, "value": workflow_id, "mode": "id"},
                        "mode": "each", "options": {"waitForSubWorkflow": wait}}, 1.1)

    def sub_trigger(self, name: str = "Al llamarlo") -> str:
        return self.add(name, "n8n-nodes-base.executeWorkflowTrigger", {}, 1)

    def webhook(self, name: str, path: str, method: str = "GET", respond: str = "onReceived") -> str:
        return self.add(name, "n8n-nodes-base.webhook", {"httpMethod": method, "path": path, "responseMode": respond, "options": {}}, 2,
                        webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, "hook/" + path)))

    def cron(self, name: str, expr: str) -> str:
        return self.add(name, "n8n-nodes-base.scheduleTrigger", {"rule": {"interval": [{"field": "cronExpression", "expression": expr}]}}, 1.2)

    def crypto(self, name: str, value_expr: str, secret: str, out: str = "firma") -> str:
        return self.add(name, "n8n-nodes-base.crypto", {"action": "hmac", "type": "SHA256", "value": value_expr, "dataPropertyName": out,
                                                        "secret": secret, "encoding": "hex"}, 1)


# ------------------------------------------------------------------ JS compartido
JS_COMMON = r"""
const SHEET = '__SHEET__', ROOT = '__ROOT__', HOST = '__HOST__', CHAT = '__CHAT__';
const COLS = ['fecha','dia','formato','modulo','tema','gancho','ig','li','tt','hashtags','archivo','estado','enlaces'];
const norm = s => String(s == null ? '' : s).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
const esc = s => String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const toIso = s => { s = String(s || '').trim(); let m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/); if (m) return m[3] + '-' + m[2].padStart(2,'0') + '-' + m[1].padStart(2,'0'); m = s.match(/^(\d{4})-(\d{2})-(\d{2})/); return m ? m[0] : ''; };
const isoBog = (off = 0) => new Date(Date.now() - 5 * 3600e3 + off * 86400e3).toISOString().slice(0, 10);
const dow = iso => new Date(iso + 'T12:00:00Z').getUTCDay();
const DIAS = ['Domingo','Lunes','Martes','Miércoles','Jueves','Viernes','Sábado'];
const ddmm = iso => iso.slice(8, 10) + '/' + iso.slice(5, 7);
const ddmmyyyy = iso => iso.slice(8, 10) + '/' + iso.slice(5, 7) + '/' + iso.slice(0, 4);
const filas = values => (values || []).map((r, i) => { const o = { fila: i + 1 }; COLS.forEach((c, j) => o[c] = String((r || [])[j] == null ? '' : r[j]).trim()); o.iso = toIso(o.fecha); o.est = norm(o.estado); return o; }).filter(o => o.fila > 1 && o.iso);
const kindOf = f => !f ? 'nada' : (String(f.mimeType || '').includes('folder') ? 'carpeta' : (String(f.mimeType || '').startsWith('video/') || /\.mp4$/i.test(f.name) ? 'video' : (String(f.mimeType || '').startsWith('image/') || /\.(png|jpe?g)$/i.test(f.name) ? 'imagen' : 'otro')));
const elegir = (files, p) => { const base = String(p.archivo || '').split('/').pop().trim(); files = (files || []).filter(f => !f.trashed);
  return (base && files.find(f => f.name === base)) || (base && files.find(f => f.name.startsWith(p.iso) && f.name.includes(base))) || files.find(f => f.name.startsWith(p.iso)) || null; };
const parseJson = v => { if (v && typeof v === 'object') return v; try { return JSON.parse(v); } catch (e) { return {}; } };
""".replace("__SHEET__", SHEET).replace("__ROOT__", ROOT).replace("__HOST__", BASE).replace("__CHAT__", CHAT)

SHEETS = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET}/values"
DRIVE_FILES = "https://www.googleapis.com/drive/v3/files"
CAL_RANGE = "Calendario!A1:M800"
LIST_ROOT_Q = {"q": f"'{ROOT}' in parents and trashed=false", "fields": "files(id,name,mimeType,createdTime,size)", "pageSize": "1000", "orderBy": "createdTime desc"}


def read_calendar(f: Flow, name: str = "Leer calendario") -> str:
    return f.http(name, "GET", f"{SHEETS}/{CAL_RANGE}", C_DRIVE)


def list_root(f: Flow, name: str = "Archivos en Drive") -> str:
    return f.http(name, "GET", DRIVE_FILES, C_DRIVE, query=LIST_ROOT_Q)


def sheet_put(f: Flow, name: str, range_expr: str, values_expr: str, **extra) -> str:
    """range_expr y values_expr son JS (sin {{ }})."""
    return f.http(name, "PUT", "={{ '" + SHEETS + "/' + encodeURIComponent(" + range_expr + ") + '?valueInputOption=USER_ENTERED' }}", C_DRIVE,
                  json_body="={{ JSON.stringify({ values: " + values_expr + " }) }}", **extra)


def sheet_append(f: Flow, name: str, range_: str, values_expr: str, **extra) -> str:
    return f.http(name, "POST", f"{SHEETS}/{range_}:append?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS", C_DRIVE,
                  json_body="={{ JSON.stringify({ values: " + values_expr + " }) }}", **extra)


def album_nodes(f: Flow, src: str, then: str, x: int, y: int) -> None:
    """Telegram no acepta un album de tamano variable por expresion: una variante por cantidad (2..10)."""
    prev = src
    for n in range(2, 11):
        cond = f.iff(f"¿{n} láminas?", f"$json.urls.length === {n}")
        f.nodes[-1]["position"] = [x, y + (n - 2) * 140]
        media = [{"type": "photo", "media": "={{ $json.urls[" + str(i) + "] }}", "additionalFields": ({"caption": "={{ $json.caption }}"} if i == 0 else {})} for i in range(n)]
        alb = f.add(f"Álbum de {n}", "n8n-nodes-base.telegram", {"operation": "sendMediaGroup", "chatId": CHAT, "media": {"media": media}, "additionalFields": {}},
                    1.2, C_TG, pos=[x + 240, y + (n - 2) * 140], onError="continueRegularOutput")
        f.link(prev, cond, 0 if prev == src else 1)
        f.link(cond, alb, 0)
        f.link(alb, then)
        prev = cond
    one = f.add("Primera lámina", "n8n-nodes-base.telegram", {"operation": "sendPhoto", "chatId": CHAT, "file": "={{ $json.urls[0] }}",
                                                               "additionalFields": {"caption": "={{ $json.caption }}"}}, 1.2, C_TG,
                pos=[x + 240, y + 9 * 140], onError="continueRegularOutput")
    f.link(prev, one, 1)
    f.link(one, then)


def _if_params(expr: str, name: str) -> dict:
    return {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                           "conditions": [{"id": str(uuid.uuid5(uuid.NAMESPACE_URL, "cond/" + name)), "leftValue": "={{ " + expr + " }}", "rightValue": "",
                                           "operator": {"type": "boolean", "operation": "true", "singleValue": True}}], "combinator": "and"}, "options": {}}


def sign_nodes(f: Flow, name_prefix: str, secret: str) -> tuple[str, str]:
    """Items {id, x} -> Crypto -> items con url firmada (1 hora)."""
    a = f.code(name_prefix + ": preparar firma", r"""
const exp = Math.floor(Date.now() / 1000) + 3600;
return $input.all().map(i => ({ json: { ...i.json, exp, msg: i.json.id + '.' + exp + '.' + (i.json.x || 'raw') } }));
""")
    b = f.crypto(name_prefix + ": firmar", "={{ $json.msg }}", secret)
    c = f.code(name_prefix + ": url", r"""
return $input.all().map(i => ({ json: { ...i.json, url: '__HOST__/webhook/nexa-archivo?f=' + i.json.id + '&e=' + i.json.exp + '&x=' + (i.json.x || 'raw') + '&s=' + i.json.firma } }));
""".replace("__HOST__", BASE))
    f.chain(a, b, c)
    return a, c


# ------------------------------------------------------------------ flujos
def flow_archivo(secret: str, backend_cred: dict) -> Flow:
    f = Flow()
    f.webhook("Pedir archivo", "nexa-archivo", "GET", "responseNode")
    f.code("Leer firma", r"""
const q = $json.query || {};
const id = String(q.f || ''), exp = String(q.e || ''), x = String(q.x || 'raw');
return [{ json: { id, exp, x, s: String(q.s || ''), msg: id + '.' + exp + '.' + x } }];
""")
    f.crypto("Calcular firma", "={{ $json.msg }}", secret, "calc")
    f.code("Validar", r"""
const j = $json, now = Date.now() / 1000, e = Number(j.exp);
const ok = /^[\w-]{10,100}$/.test(j.id) && ['raw','jpg'].includes(j.x) && j.s.length === 64 && j.s === j.calc && e > now && e - now <= 7200;
return [{ json: { ok, id: j.id, x: j.x } }];
""")
    f.iff("¿Firma válida?", "$json.ok")
    f.http("Bajar de Drive", "GET", "={{ 'https://www.googleapis.com/drive/v3/files/' + $json.id + '?alt=media' }}", C_DRIVE, fmt="file", timeout=300000)
    f.iff("¿A JPEG?", "$('Validar').first().json.x === 'jpg'")
    f.http("Convertir a JPEG", "POST", BACKEND + "/api/v1/nexa-content/jpeg", backend_cred, fmt="file", binary_in="data",
           headers={"Content-Type": "={{ $binary.data.mimeType || 'image/png' }}"})
    resp = {"respondWith": "binary", "inputDataFieldName": "data",
            "options": {"responseHeaders": {"entries": [{"name": "Content-Type", "value": "={{ $binary.data.mimeType || 'application/octet-stream' }}"},
                                                         {"name": "Cache-Control", "value": "private, max-age=600"}]}}}
    f.add("Entregar JPEG", "n8n-nodes-base.respondToWebhook", copy.deepcopy(resp), 1.1)
    f.add("Entregar archivo", "n8n-nodes-base.respondToWebhook", copy.deepcopy(resp), 1.1)
    f.add("Negar", "n8n-nodes-base.respondToWebhook", {"respondWith": "text", "responseBody": "enlace vencido o no valido",
                                                        "options": {"responseCode": 403}}, 1.1)
    f.chain("Pedir archivo", "Leer firma", "Calcular firma", "Validar", "¿Firma válida?")
    f.link("¿Firma válida?", "Bajar de Drive", 0)
    f.link("¿Firma válida?", "Negar", 1)
    f.link("Bajar de Drive", "¿A JPEG?")
    f.link("¿A JPEG?", "Convertir a JPEG", 0)
    f.link("¿A JPEG?", "Entregar archivo", 1)
    f.link("Convertir a JPEG", "Entregar JPEG")
    return f


def flow_errores() -> Flow:
    f = Flow()
    f.add("Si falla un flujo", "n8n-nodes-base.errorTrigger", {}, 1)
    f.code("Armar alerta", r"""
const e = $json.execution || {}, w = $json.workflow || {}, t = $json.trigger || {};
const err = e.error || t.error || {};
let msg = String(err.message || err.description || 'sin detalle').replace(/\s+/g, ' ').trim();
const low = msg.toLowerCase();
let motivo = '';
if (/credit balance|billing|insufficient.*(credit|fund|quota)|saldo/.test(low)) motivo = 'Sin saldo en la API (recarga antes de reintentar).';
else if (/authentication_error|invalid x-api-key|api key|unauthorized|401|clave/.test(low)) motivo = 'Clave o permiso inválido.';
const hora = new Date(Date.now() - 5 * 3600e3).toISOString().slice(0, 16).replace('T', ' ');
const texto = '🚨 Falló un flujo de Nexa\n' +
  'Flujo: ' + (w.name || '?') + '\n' +
  'Paso: ' + (e.lastNodeExecuted || (t.node && t.node.name) || '?') + '\n' +
  'Error: ' + msg.slice(0, 300) + '\n' +
  (motivo ? 'Motivo: ' + motivo + '\n' : '') +
  'Hora: ' + hora + ' (Bogotá)' + (e.url ? '\nVer: ' + e.url : '');
return [{ json: { texto } }];
""")
    f.tg("Avisar por Telegram", "={{ $json.texto }}", html=False)
    f.chain("Si falla un flujo", "Armar alerta", "Avisar por Telegram")
    return f


def flow_mostrar(secret: str) -> Flow:
    f = Flow()
    f.sub_trigger()
    f.code("Entrada", "return [{ json: { fila: Number($json.fila) || 0, nota: String($json.nota || '') } }];")
    f.http("Leer fila", "GET", "={{ '" + SHEETS + "/' + encodeURIComponent('Calendario!A' + $json.fila + ':M' + $json.fila) }}", C_DRIVE)
    list_root(f)
    f.code("Pieza", JS_COMMON + r"""
const e = $('Entrada').first().json;
const row = (($('Leer fila').first().json.values) || [[]])[0] || [];
const p = { fila: e.fila }; COLS.forEach((c, j) => p[c] = String(row[j] == null ? '' : row[j]).trim()); p.iso = toIso(p.fecha);
const file = elegir($('Archivos en Drive').first().json.files, p);
const kind = kindOf(file);
const dia = p.iso ? DIAS[dow(p.iso)] + ' ' + ddmm(p.iso) : p.fecha;
const ig = (p.ig || '(sin texto de Instagram/Facebook)').slice(0, 2800);
const aviso = kind === 'nada' ? '\n⚠️ No encontré el archivo en Drive (Nexa / Contenido): ' + esc(p.archivo || 'sin nombre') + '\n' : '';
const msg = '👀 <b>Vista previa · ' + esc(dia) + '</b>' + (e.nota ? ' · ' + esc(e.nota) : '') + '\n<b>' + esc(p.tema) + '</b> · ' + esc(p.formato) + '\n' + aviso + '\n' +
  esc(ig) + (p.hashtags ? '\n\n' + esc(p.hashtags) : '') + '\n\n<i>Estado: ' + esc(p.estado || '—') + '. Si la apruebas se publica el ' + esc(dia) + ' a las 12:00.</i>';
return [{ json: { ...p, kind, file_id: file ? file.id : '', file_name: file ? file.name : '', msg, caption: (kind === 'video' ? '🎬 ' : '🖼 ') + dia + ' · ' + p.tema } }];
""")
    f.iff("¿Video?", "$json.kind === 'video'")
    f.iff("¿Carpeta?", "['carpeta', 'imagen'].includes($json.kind)")
    f.http("Bajar video", "GET", "={{ 'https://www.googleapis.com/drive/v3/files/' + $json.file_id + '?alt=media' }}", C_DRIVE, fmt="file", timeout=300000)
    f.add("Enviar video", "n8n-nodes-base.telegram", {"operation": "sendVideo", "chatId": CHAT, "binaryData": True, "binaryPropertyName": "data",
                                                      "additionalFields": {"caption": "={{ $('Pieza').first().json.caption }}", "supports_streaming": True}},
          1.2, C_TG, onError="continueRegularOutput")
    f.http("Láminas", "GET", DRIVE_FILES, C_DRIVE, query={"q": "={{ \"'\" + $json.file_id + \"' in parents and trashed=false and mimeType contains 'image/'\" }}",
                                                       "fields": "files(id,name,mimeType)", "orderBy": "name", "pageSize": "50"})
    f.code("Láminas en orden", r"""
const p = $('Pieza').first().json;
if (p.kind === 'imagen') return [{ json: { id: p.file_id, x: 'jpg', name: p.file_name } }];
const fs = ($json.files || []).slice().sort((a, b) => a.name.localeCompare(b.name, 'es', { numeric: true }));
return fs.slice(0, 10).map(x => ({ json: { id: x.id, x: 'jpg', name: x.name } }));
""")
    a, c = sign_nodes(f, "Álbum", secret)
    f.code("Armar álbum", "return [{ json: { urls: $input.all().map(i => i.json.url), caption: $('Pieza').first().json.caption } }];")
    f.tg("Texto y botones", "={{ $('Pieza').first().json.msg }}",
         [[("✅ Aprobar", "={{ 'nx:a:' + $('Pieza').first().json.fila }}"), ("✏️ Cambiar texto", "={{ 'nx:c:' + $('Pieza').first().json.fila }}"),
           ("❌ Descartar", "={{ 'nx:d:' + $('Pieza').first().json.fila }}")]], executeOnce=True)
    f.chain("Al llamarlo", "Entrada", "Leer fila", "Archivos en Drive", "Pieza", "¿Video?")
    f.link("¿Video?", "Bajar video", 0)
    f.link("¿Video?", "¿Carpeta?", 1)
    f.chain("Bajar video", "Enviar video", "Texto y botones")
    f.link("¿Carpeta?", "Láminas", 0)
    f.link("¿Carpeta?", "Texto y botones", 1)
    f.chain("Láminas", "Láminas en orden", a)
    f.link(c, "Armar álbum")
    album_nodes(f, "Armar álbum", "Texto y botones", 3600, 300)
    return f


CLAUDE_SYSTEM = ("Eres Nexa, la presentadora creada con IA de Clonexa. Clonexa es un sistema operativo en la nube para pequeños negocios en Latinoamérica "
                 "(restaurantes, asaderos, bares, talleres de confección, personal en campo). Une pedidos (mesero, QR en la mesa, cocina, caja, domicilios), "
                 "inventario, turnos, nómina, clientes, fidelización y reportes en un solo lugar, desde el celular o el computador. Tarifa plana con usuarios "
                 "ilimitados y se adapta a cada negocio. GUÍA DE ESTILO: español latino neutro; cercana, profesional y con energía; frases cortas; tutea al dueño "
                 "del negocio. Reglas: no inventes estadísticas ni datos de clientes; no nombres clientes reales; no prometas resultados garantizados; la "
                 "factura electrónica DIAN es 'próximamente'; no menciones precios. Responde SOLO con un objeto JSON válido, sin texto antes ni después.")

MODULOS = ["Fugas de inventario en bares: cómo detectar licor que se pierde", "Pedidos por QR desde la mesa: menos errores y más ventas",
           "Turnos del personal sin enredos ni chats eternos", "Nómina en minutos: pagar por horas o por producción sin calculadora",
           "Del mesero a la cocina y a la caja: cero pedidos perdidos", "Domicilios que llegan directo a cocina", "Fidelizar clientes en un bar con juegos en vivo",
           "Reportes simples: saber qué se vende y qué no", "Talleres de confección: controlar la producción por lote", "Cierre de caja sin descuadres",
           "Del cuaderno a la nube: primeros pasos para digitalizar tu negocio", "Atender clientes por WhatsApp sin perder mensajes"]


def flow_planb(backend_cred: dict, mostrar_id: str, gen_key: str) -> Flow:
    f = Flow()
    f.sub_trigger()
    f.code("Entrada", "return [{ json: { fecha: String($json.fecha || '0'), modo: String($json.modo || 'auto'), tema: String($json.tema || ''), avatar: !!$json.avatar } }];")
    read_calendar(f)
    f.http("Leer ideas", "GET", f"{SHEETS}/Ideas!A1:C500", C_DRIVE)
    f.code("Elegir tema", JS_COMMON + r"""
const e = $('Entrada').first().json;
const cal = filas($('Leer calendario').first().json.values);
const ideas = (($('Leer ideas').first().json.values) || []).map((r, i) => ({ fila: i + 1, fecha: r[0] || '', tema: String(r[1] || '').trim(), estado: norm(r[2]) })).filter(x => x.fila > 1 && x.tema && x.estado === 'pendiente');
let fecha = /^\d{8}$/.test(e.fecha) ? e.fecha.slice(0, 4) + '-' + e.fecha.slice(4, 6) + '-' + e.fecha.slice(6, 8) : (toIso(e.fecha) || '');
if (!fecha) {  // el siguiente lunes, miercoles o viernes despues de la ultima fecha del calendario (y desde manana)
  const ultima = cal.reduce((m, r) => r.iso > m ? r.iso : m, isoBog(0));
  for (let k = 1; k < 400; k++) { const d = isoBog(k); if (d > ultima && [1, 3, 5].includes(dow(d)) && !cal.some(r => r.iso === d)) { fecha = d; break; } }
}
const row = cal.find(r => r.iso === fecha && !['publicado', 'descartado'].includes(r.est)) || null;
const idea = e.tema ? null : (ideas[0] || null);
const semana = Math.floor(Date.now() / (7 * 86400e3));
const tema = e.tema || (idea && idea.tema) || (row && (row.tema || row.gancho)) || __MODULOS__[semana % __MODULOS__.length];
const avatar = e.modo === 'auto' && (e.avatar || (row && norm(row.formato).includes('avatar')));
const modo = avatar ? 'avatar' : (e.modo === 'video_anterior' ? 'video_anterior' : 'carrusel');
return [{ json: { fecha, compacta: fecha.replace(/-/g, ''), dia: DIAS[dow(fecha)], fila: row ? row.fila : 0, tema, gancho: row ? row.gancho : '', modulo: row ? row.modulo : '',
  idea_fila: idea ? idea.fila : 0, modo, cal_count: cal.length } }];
""".replace("__MODULOS__", json.dumps(MODULOS, ensure_ascii=False)))
    f.iff("¿Avatar?", "$json.modo === 'avatar'")
    f.iff("¿Video anterior?", "$json.modo === 'video_anterior'")
    # --- avatar
    f.http("HeyGen: saldo", "GET", "https://api.heygen.com/v3/users/me", C_HEYGEN)
    f.code("¿Alcanza?", r"""
const w = (($json.data || {}).wallet) || {}, u = (($json.data || {}).usage_based) || {};
const saldo = Number(w.remaining_balance != null ? w.remaining_balance : (u.remaining_credits || 0)) || 0;
const necesita = 2.6;  // ~ un video de 70 s con Avatar IV (antes ~155 unidades; 60 unidades = 1 USD)
return [{ json: { ...$('Elegir tema').first().json, saldo, necesita, ok: saldo >= necesita, moneda: w.currency || 'usd' } }];
""")
    f.iff("¿Hay saldo?", "$json.ok")
    f.http("Generar video", "GET", BASE + "/webhook/nexa-generar", query={"k": gen_key, "tema": "={{ $json.tema }}"})
    f.tg("Avisar: generando", "={{ (() => { const t = $('¿Alcanza?').first().json; return '🎬 Generando el video con avatar sobre <b>' + t.tema.replace(/[<>&]/g, '') + '</b> (' + t.dia + ' ' + t.fecha.slice(8,10) + '/' + t.fecha.slice(5,7) + '). Te llega para revisar en unos minutos (aprobación en su página de revisión).'; })() }}")
    f.tg("Avisar: sin saldo", "={{ '⚠️ Saldo de HeyGen insuficiente para el video con avatar del ' + $json.dia + ' ' + $json.fecha.slice(8,10) + '/' + $json.fecha.slice(5,7) + '.\\nHay USD ' + $json.saldo.toFixed(2) + ' y se necesitan unos USD ' + $json.necesita.toFixed(2) + '.\\n¿Qué hago?' }}",
         [[("🔄 Recargué, intentar de nuevo", "={{ 'nx:hr:' + $json.compacta }}")], [("🖼 Hacer anuncio", "={{ 'nx:hk:' + $json.compacta }}")],
          [("🎞 Usar un video anterior", "={{ 'nx:hv:' + $json.compacta }}")]])
    # --- video anterior
    list_root(f, "Videos en Drive")
    f.code("Elegir video", JS_COMMON + r"""
const t = $('Elegir tema').first().json;
const cal = filas($('Leer calendario').first().json.values);
const v = ($json.files || []).filter(x => kindOf(x) === 'video' && !x.name.startsWith(t.fecha)).sort((a, b) => String(b.createdTime).localeCompare(String(a.createdTime)))[0];
if (!v) return [{ json: { ok: false, msg: '🎞 No hay videos anteriores en Drive (Nexa / Contenido).' } }];
const src = cal.find(r => r.archivo && v.name.includes(String(r.archivo).split('/').pop())) || cal.find(r => v.name.startsWith(r.iso) && r.ig) || {};
const vals = ['Reel (video anterior)', src.modulo || t.modulo || '', src.tema || t.tema, src.gancho || t.gancho || '', src.ig || '', src.li || '', src.tt || '', src.hashtags || '', v.name, 'Listo para aprobar'];
return [{ json: { ok: true, fila: t.fila, fecha: t.fecha, dia: t.dia, vals } }];
""")
    f.iff("¿Hay video anterior?", "$json.ok")
    f.tg("Avisar: sin videos", "={{ $json.msg }}", html=False)
    # --- carrusel
    f.code("Pedido a Claude", r"""
const t = $json;
const formato = `{"tema": "tema en pocas palabras", "escena": "uno de los ids de ESCENAS", "tag": "rubro en mayúsculas, máx 24 caracteres",
 "titulo": "inicio del titular", "resaltado": "parte del titular que va en color", "remate": "opcional: cierre corto en blanco, o vacío",
 "subtitulo": "máx 85 caracteres", "funciones": [{"emoji": "uno de EMOJI", "texto": "máx 22 caracteres"}],
 "gancho": "primera frase del post", "ig_fb": "texto de Instagram/Facebook", "linkedin": "texto de LinkedIn", "tiktok": "máx 120 caracteres", "hashtags": "5 hashtags, el último #clonexa"}`;
const pedido = `Arma un ANUNCIO VISUAL de una sola imagen para Instagram sobre: ${t.tema}.` + (t.gancho ? ` Gancho sugerido: ${t.gancho}.` : '') + (t.modulo ? ` Módulos de Clonexa: ${t.modulo}.` : '') +
 `\nESCENAS (pantallas reales de empresas demo; elige la que mejor muestre el tema): ${JSON.stringify(__ESCENAS__)}` +
 `\nEMOJI permitidos: ${__EMOJI__.join(' ')}` +
 `\nReglas: el titular completo (titulo + resaltado + remate) tiene MÁXIMO 8 PALABRAS, directo y concreto (ej: titulo "Del QR de la mesa", resaltado "a la cocina."). ` +
 `4 o 5 funciones cortas de Clonexa relacionadas con el tema, cada una con un emoji de la lista; no inventes cifras. ` +
 `Textos de redes: empiezan con el gancho, sin hashtags (van aparte), sin enlaces; ig_fb breve con 3 a 5 viñetas y cierra con "👉 Comenta DEMO y te escribo por privado.\nSígueme para más tips."; linkedin más profesional con una pregunta al final; nombra a Clonexa. Formato JSON:\n${formato}`;
return [{ json: { ...t, claude_body: JSON.stringify({ model: 'claude-sonnet-5-5', max_tokens: 16000, output_config: { effort: 'low' }, system: __SYSTEM__, messages: [{ role: 'user', content: pedido }] }) } }];
""".replace("__SYSTEM__", json.dumps(CLAUDE_SYSTEM, ensure_ascii=False))
       .replace("__ESCENAS__", json.dumps({k: v["rubro"] for k, v in nexa_ad.SCENES.items()}, ensure_ascii=False))
       .replace("__EMOJI__", json.dumps(list(nexa_ad.EMOJI), ensure_ascii=False)))
    f.http("Claude: anuncio", "POST", "https://api.anthropic.com/v1/messages", C_ANTH, json_body="={{ $json.claude_body }}",
           headers={"anthropic-version": "2023-06-01"}, timeout=180000)
    f.code("Leer Claude", r"""
const r = $json;
if (r.error || r.type === 'error') {
  const er = r.error || {}; const m = String(er.message || JSON.stringify(r)).slice(0, 200);
  if (/credit balance|billing/i.test(m) || er.type === 'billing_error') throw new Error('Claude sin saldo: la cuenta de Anthropic se quedó sin créditos. Recarga en console.anthropic.com → Billing. (' + m + ')');
  if (er.type === 'authentication_error' || er.type === 'permission_error') throw new Error('Clave de Claude inválida o sin permiso (credencial "Anthropic Nexa"). (' + m + ')');
  throw new Error('Claude respondió error: ' + m);
}
const t = ((r.content || []).find(c => c.type === 'text') || {}).text || '';
if (!t) throw new Error('Claude no devolvió texto (stop_reason: ' + (r.stop_reason || '?') + ')');
let d; try { d = JSON.parse(t.slice(t.indexOf('{'), t.lastIndexOf('}') + 1)); } catch (e) { throw new Error('No pude leer el JSON de Claude: ' + t.slice(0, 200)); }
const cut = (s, n) => String(s || '').replace(/\s+/g, ' ').trim().slice(0, n);
const ESC = __ESC_IDS__;
const escena = ESC.includes(d.escena) ? d.escena : ESC[0];
// titular: maximo 8 palabras (se recorta primero el remate, luego el resaltado y al final el titulo)
let ti = cut(d.titulo, 80).split(' ').filter(Boolean), re = cut(d.resaltado, 60).split(' ').filter(Boolean), rm = cut(d.remate, 40).split(' ').filter(Boolean);
while (ti.length + re.length + rm.length > 8) { if (rm.length) rm.pop(); else if (re.length > 1) re.pop(); else ti.pop(); }
const funciones = (d.funciones || []).slice(0, 5).map(x => ({ emoji: String(x.emoji || '✅').slice(0, 16), texto: cut(x.texto, 28) })).filter(x => x.texto);
if (funciones.length < 4) throw new Error('Claude devolvió ' + funciones.length + ' funciones (se necesitan 4 o 5)');
const spec = { escena, tag: cut(d.tag, 28).toUpperCase(), titulo: ti.join(' ') || cut(d.tema, 80), resaltado: re.join(' '), remate: rm.join(' '), subtitulo: cut(d.subtitulo, 110), funciones };
const t0 = $('Elegir tema').first().json;
const slug = String(d.tema || t0.tema).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40);
return [{ json: { ...t0, spec, archivo: t0.fecha + ' anuncio-' + slug + '.png', tema_final: cut(d.tema, 90) || t0.tema, gancho_final: String(d.gancho || spec.titulo).trim(),
  ig: String(d.ig_fb || '').trim(), li: String(d.linkedin || '').trim(), tt: String(d.tiktok || '').trim(), hashtags: String(d.hashtags || '#clonexa').trim() } }];
""".replace("__ESC_IDS__", json.dumps(list(nexa_ad.SCENES))))
    f.http("Dibujar anuncio", "POST", BACKEND + "/api/v1/nexa-content/ad", backend_cred, json_body="={{ JSON.stringify($json.spec) }}", timeout=180000)
    f.code("Anuncio a archivo", r"""
if (!$json.png_b64) throw new Error('El backend no dibujó el anuncio: ' + JSON.stringify($json).slice(0, 250));
const name = $('Leer Claude').first().json.archivo;
const bin = await this.helpers.prepareBinaryData(Buffer.from($json.png_b64, 'base64'), name, 'image/png');
return [{ json: { name, folder: '__ROOT__' }, binary: { data: bin } }];
""".replace("__ROOT__", ROOT))
    f.http("Sesión de subida", "POST", "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&fields=id,name", C_DRIVE,
           json_body="={{ JSON.stringify({ name: $json.name, parents: [$json.folder], mimeType: 'image/png' }) }}", full=True)
    f.code("Unir sesión y archivo", r"""
const src = $('Anuncio a archivo').all();
return $input.all().map((i, k) => { const loc = ((i.json.headers || {}).location) || ''; if (!loc) throw new Error('Drive no abrió la subida de ' + src[k].json.name); return { json: { loc, name: src[k].json.name }, binary: src[k].binary }; });
""")
    f.http("Subir lámina", "PUT", "={{ $json.loc }}", C_DRIVE, binary_in="data", headers={"Content-Type": "image/png"})
    f.code("Fila del plan B", JS_COMMON + r"""
const d = $('Leer Claude').first().json;
if (!$input.all().some(i => i.json.id)) throw new Error('Drive no guardó el anuncio: ' + JSON.stringify($input.first().json).slice(0, 200));
const vals = ['Anuncio (plan B)', d.modulo || 'Plan B', d.tema_final, d.gancho_final, d.ig, d.li, d.tt, d.hashtags, d.archivo, 'Listo para aprobar'];
return [{ json: { fila: d.fila, fecha: d.fecha, dia: d.dia, vals, idea_fila: d.idea_fila } }];
""")
    # escribir la fila (se usa en los dos caminos: plan B y video anterior)
    f.iff("¿Ya hay fila?", "$json.fila > 0")
    sheet_put(f, "Actualizar fila", "'Calendario!C' + $json.fila + ':L' + $json.fila", "[$json.vals]")
    sheet_append(f, "Agregar fila", "Calendario!A:L", "[[ $json.fecha.slice(8,10) + '/' + $json.fecha.slice(5,7) + '/' + $json.fecha.slice(0,4), $json.dia ].concat($json.vals)]")
    f.code("Fila final", r"""
let fila = 0, idea = 0, nota = 'Plan B';
try { const a = $('Agregar fila').first().json; const m = String(((a.updates || {}).updatedRange) || '').match(/!A(\d+)/); if (m) fila = Number(m[1]); } catch (e) {}
try { const p = $('Fila del plan B').first().json; if (!fila) fila = p.fila; idea = p.idea_fila || 0; } catch (e) {}
try { const v = $('Elegir video').first().json; if (v && v.ok) { if (!fila) fila = v.fila; nota = 'video anterior'; } } catch (e) {}
if (!fila) throw new Error('No pude ubicar la fila del calendario');
return [{ json: { fila, idea_fila: idea, nota } }];
""")
    f.iff("¿Vino de una idea?", "$json.idea_fila > 0")
    sheet_put(f, "Marcar idea usada", "'Ideas!C' + $json.idea_fila", "[['Usada']]")
    f.code("Para la vista previa", "const j = $('Fila final').first().json; return [{ json: { fila: j.fila, nota: j.nota } }];")
    f.run("Mostrar pieza", mostrar_id, True)
    # conexiones
    f.chain("Al llamarlo", "Entrada", "Leer calendario", "Leer ideas", "Elegir tema", "¿Avatar?")
    f.link("¿Avatar?", "HeyGen: saldo", 0)
    f.link("¿Avatar?", "¿Video anterior?", 1)
    f.chain("HeyGen: saldo", "¿Alcanza?", "¿Hay saldo?")
    f.link("¿Hay saldo?", "Generar video", 0)
    f.link("¿Hay saldo?", "Avisar: sin saldo", 1)
    f.link("Generar video", "Avisar: generando")
    f.link("¿Video anterior?", "Videos en Drive", 0)
    f.link("¿Video anterior?", "Pedido a Claude", 1)
    f.chain("Videos en Drive", "Elegir video", "¿Hay video anterior?")
    f.link("¿Hay video anterior?", "¿Ya hay fila?", 0)
    f.link("¿Hay video anterior?", "Avisar: sin videos", 1)
    f.chain("Pedido a Claude", "Claude: anuncio", "Leer Claude", "Dibujar anuncio", "Anuncio a archivo",
            "Sesión de subida", "Unir sesión y archivo", "Subir lámina", "Fila del plan B", "¿Ya hay fila?")
    f.link("¿Ya hay fila?", "Actualizar fila", 0)
    f.link("¿Ya hay fila?", "Agregar fila", 1)
    f.link("Actualizar fila", "Fila final")
    f.link("Agregar fila", "Fila final")
    f.chain("Fila final", "¿Vino de una idea?")
    f.link("¿Vino de una idea?", "Marcar idea usada", 0)
    f.link("¿Vino de una idea?", "Para la vista previa", 1)
    f.link("Marcar idea usada", "Para la vista previa")
    f.link("Para la vista previa", "Mostrar pieza")
    return f


def flow_vista_previa(mostrar_id: str, planb_id: str, hook_secret: str) -> Flow:
    f = Flow()
    f.cron("Todos los días 18:00", "0 18 * * *")
    f.webhook("Probar (enlace)", "nexa-vista-previa", "GET")
    f.code("Fecha de mañana", JS_COMMON + r"""
let fecha = isoBog(1), planb = true;
try { const q = $('Probar (enlace)').first().json.query || {}; if (q.k !== '__SECRET__') throw new Error('Acceso no autorizado'); fecha = toIso(q.fecha) || fecha; planb = q.planb !== '0'; } catch (e) { if (String(e.message).includes('autorizado')) throw e; }
return [{ json: { fecha, planb } }];
""".replace("__SECRET__", hook_secret))
    read_calendar(f)
    f.code("Revisar mañana", JS_COMMON + r"""
const { fecha, planb } = $('Fecha de mañana').first().json;
const cal = filas($json.values);
const listos = cal.filter(r => r.iso === fecha && r.est === 'listo para aprobar').map(r => r.fila);
const hay = cal.some(r => r.iso === fecha && ['listo para aprobar', 'aprobado', 'publicado'].includes(r.est));
const necesita = planb && !hay && [1, 3, 5].includes(dow(fecha));
return [{ json: { fecha, listos, planb: necesita } }];
""")
    f.iff("¿Hay piezas listas?", "$json.listos.length > 0")
    f.code("Una por pieza", "return $json.listos.map(fila => ({ json: { fila, nota: 'para mañana' } }));")
    f.run("Mostrar pieza", mostrar_id, True)
    f.iff("¿Plan B?", "$('Revisar mañana').first().json.planb")
    f.code("Pedir plan B", "const j = $('Revisar mañana').first().json; return [{ json: { fecha: j.fecha, modo: 'auto' } }];")
    f.tg("Avisar: plan B", "={{ (() => { const f = $('Revisar mañana').first().json.fecha; return '📭 Mañana (' + f.slice(8,10) + '/' + f.slice(5,7) + ') no hay pieza lista: activo el plan B.'; })() }}")
    f.run("Plan B", planb_id, True)
    f.link("Todos los días 18:00", "Fecha de mañana")
    f.link("Probar (enlace)", "Fecha de mañana")
    f.chain("Fecha de mañana", "Leer calendario", "Revisar mañana", "¿Hay piezas listas?")
    f.link("¿Hay piezas listas?", "Una por pieza", 0)
    f.link("¿Hay piezas listas?", "¿Plan B?", 1)
    f.chain("Una por pieza", "Mostrar pieza")
    f.link("¿Plan B?", "Avisar: plan B", 0)
    f.chain("Avisar: plan B", "Pedir plan B", "Plan B")
    return f


def flow_publicar(secret_archivo: str, hook_secret: str) -> Flow:
    f = Flow()
    f.cron("L, M y V 12:00", "0 12 * * 1,3,5")
    f.webhook("Simular o probar (enlace)", "nexa-publicar-dia", "GET")
    f.code("Entrada", JS_COMMON + r"""
let fecha = isoBog(0), simular = false, todas = false;
try { const q = $('Simular o probar (enlace)').first().json.query || {}; if (q.k !== '__SECRET__') throw new Error('Acceso no autorizado'); fecha = toIso(q.fecha) || fecha; simular = q.simular !== '0'; todas = simular && q.todas === '1'; } catch (e) { if (String(e.message).includes('autorizado')) throw e; }
return [{ json: { fecha, simular, todas, vuelta: $runIndex } }];
""".replace("__SECRET__", hook_secret))
    read_calendar(f)
    list_root(f)
    f.code("Elegir pieza", JS_COMMON + r"""
const { fecha, simular, todas } = $('Entrada').last().json;
const cal = filas($('Leer calendario').last().json.values);
const hechas = (() => { try { return $('Fila publicada').all().map(i => i.json.fila); } catch (e) { return []; } })();
const aprobadas = cal.filter(r => r.iso === fecha && (r.est === 'aprobado' || (todas && r.est === 'listo para aprobar')) && !hechas.includes(r.fila));  // todas: solo en simulacion
if (!aprobadas.length) return [{ json: { nada: true, fecha, simular, primera: hechas.length === 0 } }];
const p = aprobadas[0];
const file = elegir($('Archivos en Drive').last().json.files, p);
return [{ json: { nada: false, fecha, simular, ...p, kind: kindOf(file), file_id: file ? file.id : '', file_name: file ? file.name : '', otras: aprobadas.length - 1 } }];
""")
    f.iff("¿Nada aprobado?", "$json.nada")
    f.iff("¿Primera vuelta?", "$json.primera")
    f.tg("Avisar: nada que publicar", "={{ '📭 Hoy (' + $json.fecha.slice(8,10) + '/' + $json.fecha.slice(5,7) + ') no hay ninguna pieza en estado Aprobado: no publiqué nada.' + ($json.simular ? ' (simulación)' : '') }}", html=False)
    f.iff("¿Hay archivo?", "['video','carpeta','imagen'].includes($json.kind)")
    f.tg("Avisar: falta archivo", "={{ '⚠️ La pieza aprobada de hoy («' + $json.tema + '», fila ' + $json.fila + ') no tiene archivo en Drive (Nexa / Contenido): ' + ($json.archivo || 'sin nombre') + '. No publiqué nada.' }}", html=False)
    f.iff("¿Es carrusel?", "$json.kind === 'carpeta'")
    f.http("Láminas", "GET", DRIVE_FILES, C_DRIVE, query={"q": "={{ \"'\" + $json.file_id + \"' in parents and trashed=false and mimeType contains 'image/'\" }}",
                                                       "fields": "files(id,name,mimeType)", "orderBy": "name", "pageSize": "50"})
    f.code("Archivos a firmar", r"""
const p = $('Elegir pieza').last().json;
if (p.kind === 'video') return [{ json: { id: p.file_id, x: 'raw', name: p.file_name } }];
if (p.kind === 'imagen') return [{ json: { id: p.file_id, x: 'jpg', name: p.file_name } }];
const fs = ($('Láminas').last().json.files || []).slice().sort((a, b) => a.name.localeCompare(b.name, 'es', { numeric: true })).slice(0, 10);
return fs.map(x => ({ json: { id: x.id, x: 'jpg', name: x.name } }));
""")
    a, c = sign_nodes(f, "Envío", secret_archivo)
    f.code("Plan de envío", JS_COMMON + r"""
const p = $('Elegir pieza').last().json;
const files = $input.all().map(i => i.json);
const camp = 'nexa-' + p.iso;
const link = red => '__LANDING__?utm_source=' + red + '&utm_medium=social&utm_campaign=' + camp;
const tags = p.hashtags || '#clonexa';
const ig = (p.ig || p.gancho || p.tema).trim();
const li = (p.li || ig).trim();
const t = {
  instagram: (ig + '\n\n' + tags).slice(0, 2200),
  facebook: ig + '\n\n👉 Agenda tu demo gratis: ' + link('facebook') + '\n\n' + tags,
  linkedin: li + '\n\n👉 Agenda una demo gratis: ' + link('linkedin') + '\n\n' + tags,
  youtube_titulo: String(p.gancho || p.tema).replace(/[<>]/g, '').slice(0, 95),
  youtube_descripcion: ig + '\n\n👉 Agenda tu demo gratis: ' + link('youtube') + '\n\n' + tags + ' #Shorts',
  tiktok: (p.tt || '') + ' ' + tags,
};
const video = p.kind === 'video';
const redes = video ? {
  instagram: { endpoint: 'POST graph.facebook.com/__IG__/media (REELS) + media_publish', video_url: files[0].url },
  facebook: { endpoint: 'POST graph-video.facebook.com/__PAGE__/videos', file_url: files[0].url },
  youtube: { endpoint: 'POST googleapis.com/upload/youtube/v3/videos (Short, público)', archivo: files[0].name },
  linkedin: { endpoint: 'POST api.linkedin.com/rest/videos + rest/posts (perfil personal)', archivo: files[0].name },
} : files.length === 1 ? {
  instagram: { endpoint: 'POST graph.facebook.com/__IG__/media (imagen) + media_publish', image_urls: files.map(x => x.url) },
  facebook: { endpoint: 'POST graph.facebook.com/__PAGE__/photos (published=false) + /feed con attached_media', urls: files.map(x => x.url) },
  linkedin: { endpoint: 'POST api.linkedin.com/rest/images + rest/posts con una imagen (perfil personal)', laminas: files.map(x => x.name) },
} : {
  instagram: { endpoint: 'POST graph.facebook.com/__IG__/media x' + files.length + ' (is_carousel_item) + CAROUSEL + media_publish', image_urls: files.map(x => x.url) },
  facebook: { endpoint: 'POST graph.facebook.com/__PAGE__/photos (published=false) x' + files.length + ' + /feed con attached_media', urls: files.map(x => x.url) },
  linkedin: { endpoint: 'POST api.linkedin.com/rest/images x' + files.length + ' + rest/posts multiImage (perfil personal)', laminas: files.map(x => x.name) },
};
const omitidas = { tiktok: 'solo hay claves de sandbox de TikTok (falta la app aprobada para producción)' };
if (!video) omitidas.youtube = 'YouTube Shorts necesita video; las imágenes no van a YouTube';
return [{ json: { fila: p.fila, fecha: p.iso, tema: p.tema, formato: p.formato, kind: p.kind, video, files, textos: t, redes, omitidas, simular: p.simular, otras: p.otras } }];
""".replace("__LANDING__", LANDING).replace("__IG__", IG_ID).replace("__PAGE__", PAGE_ID))
    f.iff("¿Simulación?", "$json.simular")
    f.code("Resumen de simulación", JS_COMMON + r"""
const j = $json;
const l = ['🧪 <b>Publicación simulada</b> (no se envió nada)', esc(j.tema) + ' · ' + esc(j.formato) + ' · fila ' + j.fila, ''];
for (const [red, r] of Object.entries(j.redes)) {
  l.push('• <b>' + red + '</b>: ' + esc(r.endpoint));
  const urls = r.image_urls || r.urls || (r.video_url ? [r.video_url] : r.file_url ? [r.file_url] : null);
  if (urls) l.push('  ' + urls.length + ' archivo(s) con enlace temporal (vence en 1 h). Orden: ' + j.files.map(f => f.name).join(', '));
  else if (r.laminas || r.archivo) l.push('  sube los bytes desde Drive: ' + esc((r.laminas || [r.archivo]).join(', ')));
}
for (const [red, why] of Object.entries(j.omitidas)) l.push('⏭ ' + red + ': ' + esc(why));
l.push('', '<b>Instagram:</b> ' + esc(j.textos.instagram.slice(0, 250)) + '…');
l.push('<b>LinkedIn:</b> ' + esc(j.textos.linkedin.slice(0, 180)) + '…');
if (j.video) l.push('<b>YouTube:</b> ' + esc(j.textos.youtube_titulo));
l.push('', 'Primer enlace temporal: ' + esc(j.files[0].url));
return [{ json: { ...j, msg: l.join('\n') } }];
""")
    f.tg("Enviar simulación", "={{ $json.msg }}")
    # ---------------- publicacion real
    f.iff("IG: ¿video?", "$('Plan de envío').last().json.video")
    f.http("IG: crear Reel", "POST", f"https://graph.facebook.com/{IG_ID}/media", C_META,
           json_body="={{ JSON.stringify({ media_type: 'REELS', video_url: $('Plan de envío').last().json.files[0].url, caption: $('Plan de envío').last().json.textos.instagram, share_to_feed: true }) }}")
    f.iff("IG: ¿una imagen?", "$('Plan de envío').last().json.files.length === 1")
    f.http("IG: crear imagen", "POST", f"https://graph.facebook.com/{IG_ID}/media", C_META,
           json_body="={{ JSON.stringify({ image_url: $('Plan de envío').last().json.files[0].url, caption: $('Plan de envío').last().json.textos.instagram }) }}")
    f.code("IG: hijos", "return $('Plan de envío').last().json.files.map(x => ({ json: { image_url: x.url } }));")
    f.http("IG: crear lámina", "POST", f"https://graph.facebook.com/{IG_ID}/media", C_META,
           json_body="={{ JSON.stringify({ image_url: $json.image_url, is_carousel_item: true }) }}")
    f.code("IG: armar carrusel", r"""
const ids = $input.all().map(i => i.json.id);
if (ids.some(x => !x)) return [{ json: { error: 'Instagram no aceptó una lámina: ' + JSON.stringify(($input.all().find(i => !i.json.id) || {}).json || {}).slice(0, 250) } }];
return [{ json: { body: JSON.stringify({ media_type: 'CAROUSEL', children: ids.join(','), caption: $('Plan de envío').last().json.textos.instagram }) } }];
""")
    f.iff("IG: ¿láminas ok?", "!$json.error")
    f.http("IG: crear carrusel", "POST", f"https://graph.facebook.com/{IG_ID}/media", C_META, json_body="={{ $json.body }}")
    f.code("IG: contenedor", "return [{ json: { container: $json.id || '', error: $json.id ? '' : ($json.error && typeof $json.error === 'string' ? $json.error : JSON.stringify($json.error || $json).slice(0, 250)) } }];")
    f.iff("IG: ¿contenedor?", "!!$json.container")
    f.wait("IG: esperar 20 s", 20)
    f.http("IG: estado", "GET", "={{ 'https://graph.facebook.com/' + $json.container + '?fields=status_code,status' }}", C_META)
    f.code("IG: evaluar", r"""
const c = $('IG: esperar 20 s').last().json.container; const s = $json.status_code || '';
return [{ json: { container: c, listo: s === 'FINISHED', fallo: ['ERROR', 'EXPIRED'].includes(s) || $runIndex > 25, error: s ? ('Instagram: ' + s + ' ' + ($json.status || '')) : JSON.stringify($json.error || $json).slice(0, 250) } }];
""")
    f.iff("IG: ¿listo?", "$json.listo")
    f.iff("IG: ¿falló?", "$json.fallo")
    f.http("IG: publicar", "POST", f"https://graph.facebook.com/{IG_ID}/media_publish", C_META, json_body="={{ JSON.stringify({ creation_id: $json.container }) }}")
    f.http("IG: enlace", "GET", "={{ 'https://graph.facebook.com/' + ($json.id || 'x') + '?fields=permalink' }}", C_META)
    f.code("IG: resultado", r"""
const get = n => { try { return $(n).last().json; } catch (e) { return null; } };
const pub = get('IG: publicar'), en = get('IG: enlace');
if (pub && pub.id) return [{ json: { red: 'Instagram', ok: true, link: (en && en.permalink) || 'instagram.com/clonexaapp' } }];
const ev = get('IG: evaluar'), ct = get('IG: contenedor');
return [{ json: { red: 'Instagram', ok: false, info: (pub && JSON.stringify(pub.error || pub).slice(0, 250)) || (ev && ev.error) || (ct && ct.error) || 'error desconocido' } }];
""", executeOnce=True)
    # facebook
    f.iff("FB: ¿video?", "$('Plan de envío').last().json.video")
    f.http("FB: video", "POST", f"https://graph-video.facebook.com/{PAGE_ID}/videos", C_META, timeout=300000,
           json_body="={{ JSON.stringify({ file_url: $('Plan de envío').last().json.files[0].url, description: $('Plan de envío').last().json.textos.facebook, title: $('Plan de envío').last().json.tema }) }}")
    f.code("FB: fotos", "return $('Plan de envío').last().json.files.map(x => ({ json: { url: x.url } }));")
    f.http("FB: subir foto", "POST", f"https://graph.facebook.com/{PAGE_ID}/photos", C_META, json_body="={{ JSON.stringify({ url: $json.url, published: false }) }}")
    f.code("FB: armar", r"""
const ids = $input.all().map(i => i.json.id);
if (ids.some(x => !x)) return [{ json: { error: 'Facebook no aceptó una foto: ' + JSON.stringify(($input.all().find(i => !i.json.id) || {}).json || {}).slice(0, 250) } }];
return [{ json: { body: JSON.stringify({ message: $('Plan de envío').last().json.textos.facebook, attached_media: ids.map(id => ({ media_fbid: id })) }) } }];
""")
    f.iff("FB: ¿fotos ok?", "!$json.error")
    f.http("FB: publicar", "POST", f"https://graph.facebook.com/{PAGE_ID}/feed", C_META, json_body="={{ $json.body }}")
    f.code("FB: resultado", r"""
const get = n => { try { return $(n).last().json; } catch (e) { return null; } };
const v = get('FB: video'), p = get('FB: publicar'), a = get('FB: armar');
const r = v || p;
if (r && r.id) return [{ json: { red: 'Facebook', ok: true, link: v ? 'https://www.facebook.com/watch/?v=' + r.id : 'https://www.facebook.com/' + r.id } }];
return [{ json: { red: 'Facebook', ok: false, info: (a && a.error) || JSON.stringify((r && (r.error || r)) || 'sin respuesta').slice(0, 250) } }];
""", executeOnce=True)
    # youtube (solo video)
    f.iff("YT: ¿video?", "$('Plan de envío').last().json.video")
    f.http("Bajar video", "GET", "={{ 'https://www.googleapis.com/drive/v3/files/' + $('Plan de envío').last().json.files[0].id + '?alt=media' }}", C_DRIVE, fmt="file", timeout=300000)
    f.code("Medir video", "const b = await this.helpers.getBinaryDataBuffer(0, 'data'); return [{ json: { size: b.length }, binary: $input.first().binary }];")
    f.http("YT: iniciar subida", "POST", "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status", C_YT, full=True,
           headers={"X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": "={{ $('Medir video').last().json.size }}"},
           json_body="={{ JSON.stringify({ snippet: { title: $('Plan de envío').last().json.textos.youtube_titulo, description: $('Plan de envío').last().json.textos.youtube_descripcion, categoryId: '22', defaultLanguage: 'es', defaultAudioLanguage: 'es', tags: ['Clonexa', 'negocios', 'restaurantes', 'pymes'] }, status: { privacyStatus: 'public', selfDeclaredMadeForKids: false } }) }}")
    f.code("YT: preparar archivo", "const loc = ($json.headers || {}).location || ''; return [{ json: { location: loc, error: loc ? '' : JSON.stringify($json.body || $json).slice(0, 250) }, binary: $('Medir video').last().binary }];")
    f.http("YT: subir video", "PUT", "={{ $json.location || 'https://www.googleapis.com/upload/youtube/v3/videos' }}", C_YT, binary_in="data",
           headers={"Content-Type": "video/mp4"}, timeout=600000)
    f.code("YT: resultado", r"""
let prep = null; try { prep = $('YT: preparar archivo').last().json; } catch (e) {}
if (prep && prep.error) return [{ json: { red: 'YouTube', ok: false, info: prep.error } }];
return [{ json: $json.id ? { red: 'YouTube', ok: true, link: 'https://youtu.be/' + $json.id } : { red: 'YouTube', ok: false, info: JSON.stringify($json.error || $json).slice(0, 250) } }];
""", executeOnce=True)
    # linkedin
    li_h = {"LinkedIn-Version": "202608", "X-Restli-Protocol-Version": "2.0.0", "Content-Type": "application/json"}
    f.http("LI: quién soy", "GET", "https://api.linkedin.com/v2/userinfo", C_LI, executeOnce=True)
    f.iff("LI: ¿video?", "$('Plan de envío').last().json.video")
    f.http("LI: iniciar video", "POST", "https://api.linkedin.com/rest/videos?action=initializeUpload", C_LI, headers=li_h,
           json_body="={{ JSON.stringify({ initializeUploadRequest: { owner: 'urn:li:person:' + $('LI: quién soy').last().json.sub, fileSizeBytes: $('Medir video').last().json.size, uploadCaptions: false, uploadThumbnail: false } }) }}")
    f.code("LI: partes del video", r"""
const v = $json.value || {};
if (!v.uploadInstructions) return [{ json: { error: 'LinkedIn no inició la subida: ' + JSON.stringify($json).slice(0, 250) } }];
return [{ json: { instr: v.uploadInstructions, video: v.video, token: v.uploadToken || '' }, binary: $('Medir video').last().binary }];
""")
    f.code("LI: dividir", r"""
const j = $input.first().json;
if (j.error) return [{ json: { error: j.error } }];
const buf = await this.helpers.getBinaryDataBuffer(0, 'data');
const out = [];
for (const p of j.instr) { const bin = await this.helpers.prepareBinaryData(buf.subarray(p.firstByte, p.lastByte + 1), 'parte.mp4', 'application/octet-stream'); out.push({ json: { uploadUrl: p.uploadUrl }, binary: { data: bin } }); }
return out;
""")
    f.http("LI: subir parte", "PUT", "={{ $json.uploadUrl }}", C_LI, binary_in="data", headers={"Content-Type": "application/octet-stream"}, full=True, timeout=300000)
    f.code("LI: cerrar video", r"""
const items = $input.all(); const p = $('LI: partes del video').last().json;
const bad = items.find(i => !(i.json.statusCode < 300));
if (bad) return [{ json: { error: 'LinkedIn rechazó una parte: ' + (bad.json.statusCode || JSON.stringify(bad.json).slice(0, 200)) } }];
return [{ json: { body: JSON.stringify({ finalizeUploadRequest: { video: p.video, uploadToken: p.token, uploadedPartIds: items.map(i => (i.json.headers || {}).etag) } }) } }];
""")
    f.http("LI: finalizar video", "POST", "https://api.linkedin.com/rest/videos?action=finalizeUpload", C_LI, headers=li_h, json_body="={{ $json.body }}", full=True)
    f.wait("LI: esperar 30 s", 30)
    f.code("LI: imágenes", "return $('Plan de envío').last().json.files.map(x => ({ json: { id: x.id, name: x.name } }));")
    f.http("LI: bajar lámina", "GET", "={{ 'https://www.googleapis.com/drive/v3/files/' + $json.id + '?alt=media' }}", C_DRIVE, fmt="file")
    f.http("LI: iniciar imagen", "POST", "https://api.linkedin.com/rest/images?action=initializeUpload", C_LI, headers=li_h,
           json_body="={{ JSON.stringify({ initializeUploadRequest: { owner: 'urn:li:person:' + $('LI: quién soy').last().json.sub } }) }}")
    f.code("LI: pareja", r"""
const bins = $('LI: bajar lámina').all();
return $input.all().map((i, k) => ({ json: { uploadUrl: ((i.json.value || {}).uploadUrl) || '', image: ((i.json.value || {}).image) || '', err: i.json.value ? '' : JSON.stringify(i.json).slice(0, 200) }, binary: bins[k].binary }));
""")
    f.http("LI: subir imagen", "PUT", "={{ $json.uploadUrl }}", C_LI, binary_in="data", headers={"Content-Type": "application/octet-stream"}, full=True)
    f.code("LI: armar publicación", r"""
const v = $('Plan de envío').last().json, sub = $('LI: quién soy').last().json.sub;
const tags = []; let s = v.textos.linkedin || '';
s = s.replace(/#([\p{L}\p{N}_]+)/gu, (m, t) => { tags.push(t); return '\u0000' + (tags.length - 1) + '\u0000'; });
s = s.replace(/[\\|{}@\[\]()<>*_~#]/g, '\\$&').replace(/\u0000(\d+)\u0000/g, (m, i) => '{hashtag|\\#|' + tags[+i] + '}');
let content;
if (v.video) {
  let p = null; try { p = $('LI: partes del video').last().json; } catch (e) {}
  let c = null; try { c = $('LI: cerrar video').last().json; } catch (e) {}
  if (!p || p.error || (c && c.error)) return [{ json: { error: (p && p.error) || (c && c.error) || 'no se subió el video' } }];
  content = { media: { id: p.video, title: v.tema } };
} else {
  const pares = $('LI: pareja').all().map(i => i.json); const subidas = $('LI: subir imagen').all().map(i => i.json);
  const mal = pares.find(x => !x.image) || subidas.find(x => !(x.statusCode < 300));
  if (mal) return [{ json: { error: 'LinkedIn no aceptó una lámina: ' + JSON.stringify(mal).slice(0, 200) } }];
  content = pares.length === 1 ? { media: { id: pares[0].image, altText: v.tema } }
    : { multiImage: { images: pares.map((x, k) => ({ id: x.image, altText: v.tema + ' (' + (k + 1) + '/' + pares.length + ')' })) } };
}
return [{ json: { body: JSON.stringify({ author: 'urn:li:person:' + sub, commentary: s, visibility: 'PUBLIC', distribution: { feedDistribution: 'MAIN_FEED', targetEntities: [], thirdPartyDistributionChannels: [] }, content, lifecycleState: 'PUBLISHED', isReshareDisabledByAuthor: false }) } }];
""", executeOnce=True)
    f.iff("LI: ¿lista?", "!$json.error")
    f.http("LI: publicar", "POST", "https://api.linkedin.com/rest/posts", C_LI, headers=li_h, json_body="={{ $json.body }}", full=True)
    f.code("LI: resultado", r"""
let a = null; try { a = $('LI: armar publicación').last().json; } catch (e) {}
if (a && a.error) return [{ json: { red: 'LinkedIn', ok: false, info: a.error } }];
const id = ($json.headers || {})['x-restli-id'];
return [{ json: ($json.statusCode < 300 && id) ? { red: 'LinkedIn', ok: true, link: 'https://www.linkedin.com/feed/update/' + id } : { red: 'LinkedIn', ok: false, info: ($json.statusCode || '') + ' ' + JSON.stringify($json.body || $json).slice(0, 250) } }];
""", executeOnce=True)
    f.code("Resumen", JS_COMMON + r"""
const v = $('Plan de envío').last().json;
const get = n => { try { return $(n).last().json; } catch (e) { return null; } };
const rs = ['IG: resultado', 'FB: resultado', 'YT: resultado', 'LI: resultado'].map(get).filter(Boolean);
const lineas = rs.map(r => (r.ok ? '✅ ' : '❌ ') + r.red + ': ' + esc(r.ok ? r.link : r.info));
for (const [red, why] of Object.entries(v.omitidas)) lineas.push('⏭ ' + red + ': ' + esc(why));
const enlaces = rs.filter(r => r.ok).map(r => r.red + ': ' + r.link).join('\n');
const fallos = rs.filter(r => !r.ok).map(r => r.red).join(', ');
const estado = rs.some(r => r.ok) ? 'Publicado' : 'Aprobado';
return [{ json: { fila: v.fila, estado, enlaces: enlaces + (fallos ? (enlaces ? '\n' : '') + 'Falló: ' + fallos : ''),
  msg: '📣 <b>Publicación de Nexa</b> · ' + esc(v.tema) + '\n\n' + lineas.join('\n') + (estado === 'Aprobado' ? '\n\nNinguna red publicó: la fila sigue en Aprobado.' : '') } }];
""", executeOnce=True)
    sheet_put(f, "Marcar publicado", "'Calendario!L' + $json.fila + ':M' + $json.fila", "[[ $json.estado, $json.enlaces ]]")
    f.tg("Avisar resultado", "={{ $('Resumen').last().json.msg }}")
    f.code("Fila publicada", "return [{ json: { fila: $('Resumen').last().json.fila } }];")
    f.iff("¿Otra aprobada hoy?", "$('Plan de envío').last().json.otras > 0 && $runIndex < 4")
    # conexiones
    f.link("L, M y V 12:00", "Entrada")
    f.link("Simular o probar (enlace)", "Entrada")
    f.chain("Entrada", "Leer calendario", "Archivos en Drive", "Elegir pieza", "¿Nada aprobado?")
    f.link("¿Nada aprobado?", "¿Primera vuelta?", 0)
    f.link("¿Primera vuelta?", "Avisar: nada que publicar", 0)
    f.link("¿Nada aprobado?", "¿Hay archivo?", 1)
    f.link("¿Hay archivo?", "¿Es carrusel?", 0)
    f.link("¿Hay archivo?", "Avisar: falta archivo", 1)
    f.link("¿Es carrusel?", "Láminas", 0)
    f.link("¿Es carrusel?", "Archivos a firmar", 1)
    f.link("Láminas", "Archivos a firmar")
    f.link("Archivos a firmar", a)
    f.link(c, "Plan de envío")
    f.chain("Plan de envío", "¿Simulación?")
    f.link("¿Simulación?", "Resumen de simulación", 0)
    f.link("Resumen de simulación", "Enviar simulación")
    f.link("¿Simulación?", "IG: ¿video?", 1)
    f.link("IG: ¿video?", "IG: crear Reel", 0)
    f.link("IG: ¿video?", "IG: ¿una imagen?", 1)
    f.link("IG: ¿una imagen?", "IG: crear imagen", 0)
    f.link("IG: ¿una imagen?", "IG: hijos", 1)
    f.link("IG: crear imagen", "IG: contenedor")
    f.link("IG: crear Reel", "IG: contenedor")
    f.chain("IG: hijos", "IG: crear lámina", "IG: armar carrusel", "IG: ¿láminas ok?")
    f.link("IG: ¿láminas ok?", "IG: crear carrusel", 0)
    f.link("IG: ¿láminas ok?", "IG: contenedor", 1)
    f.link("IG: crear carrusel", "IG: contenedor")
    f.link("IG: contenedor", "IG: ¿contenedor?")
    f.link("IG: ¿contenedor?", "IG: esperar 20 s", 0)
    f.link("IG: ¿contenedor?", "IG: resultado", 1)
    f.chain("IG: esperar 20 s", "IG: estado", "IG: evaluar", "IG: ¿listo?")
    f.link("IG: ¿listo?", "IG: publicar", 0)
    f.link("IG: ¿listo?", "IG: ¿falló?", 1)
    f.link("IG: ¿falló?", "IG: resultado", 0)
    f.link("IG: ¿falló?", "IG: esperar 20 s", 1)
    f.chain("IG: publicar", "IG: enlace", "IG: resultado", "FB: ¿video?")
    f.link("FB: ¿video?", "FB: video", 0)
    f.link("FB: ¿video?", "FB: fotos", 1)
    f.link("FB: video", "FB: resultado")
    f.chain("FB: fotos", "FB: subir foto", "FB: armar", "FB: ¿fotos ok?")
    f.link("FB: ¿fotos ok?", "FB: publicar", 0)
    f.link("FB: ¿fotos ok?", "FB: resultado", 1)
    f.link("FB: publicar", "FB: resultado")
    f.link("FB: resultado", "YT: ¿video?")
    f.link("YT: ¿video?", "Bajar video", 0)
    f.link("YT: ¿video?", "LI: quién soy", 1)
    f.chain("Bajar video", "Medir video", "YT: iniciar subida", "YT: preparar archivo", "YT: subir video", "YT: resultado", "LI: quién soy", "LI: ¿video?")
    f.link("LI: ¿video?", "LI: iniciar video", 0)
    f.link("LI: ¿video?", "LI: imágenes", 1)
    f.chain("LI: iniciar video", "LI: partes del video", "LI: dividir", "LI: subir parte", "LI: cerrar video", "LI: finalizar video", "LI: esperar 30 s", "LI: armar publicación")
    f.chain("LI: imágenes", "LI: bajar lámina", "LI: iniciar imagen", "LI: pareja", "LI: subir imagen", "LI: armar publicación")
    f.link("LI: armar publicación", "LI: ¿lista?")
    f.link("LI: ¿lista?", "LI: publicar", 0)
    f.link("LI: ¿lista?", "LI: resultado", 1)
    f.chain("LI: publicar", "LI: resultado", "Resumen", "Marcar publicado", "Avisar resultado", "Fila publicada", "¿Otra aprobada hoy?")
    f.link("¿Otra aprobada hoy?", "Entrada", 0)
    return f


# ------------------------------------------------------------------ cambios en flujos existentes
BOT_READ = r"""
const u = $json;
if (u.callback_query) {
  const q = u.callback_query; const m = q.message || {};
  const chat = String(((m.chat || {}).id) || ((q.from || {}).id) || '');
  const [ns, accion, arg] = String(q.data || '').split(':');
  return [{ json: { tipo: ns === 'nx' ? 'boton' : 'otro', chat, autorizado: chat === '__CHAT__' && String((q.from || {}).id) === '__CHAT__', cmd: '', arg: '', texto: '',
    accion: accion || '', param: arg || '', fila: Number(arg) || 0, cb_id: q.id, msg_id: m.message_id, msg_text: String(m.text || m.caption || '').slice(0, 3500) } }];
}
const m = u.message || {};
const chat = String((m.chat || {}).id || '');
const texto = (m.text || '').trim();
const rep = m.reply_to_message || {};
const ref = String(rep.text || '').match(/#F(\d+)/);
if (ref && rep.from && rep.from.is_bot && texto && !texto.startsWith('/')) {
  return [{ json: { tipo: 'texto_nuevo', chat, autorizado: chat === '__CHAT__', cmd: '', arg: '', texto, fila: Number(ref[1]) } }];
}
const limpio = texto.replace(/^\/\s+/, '/').replace(/^\/plan\s+b/i, '/planb');
const [primera, ...resto] = limpio.split(/\s+/);
const cmd = (primera || '').toLowerCase().replace(/@.*$/, '');
const tipo = cmd === '/tema' ? 'tema' : cmd === '/temas' ? 'temas' : cmd === '/planb' ? 'planb' : 'comando';
return [{ json: { tipo, chat, autorizado: chat === '__CHAT__', cmd, arg: resto.join(' '), texto } }];
""".replace("__CHAT__", CHAT)

BOT_HELP = ("🤖 <b>Bot de Nexa</b> · comandos:\n\n"
            "/tema <i>idea</i> → anota un tema para próximos contenidos (ej: /tema cierre de caja en bares)\n"
            "/temas → ideas pendientes\n"
            "/planb → arma ya un anuncio visual con la siguiente idea (queda para aprobar)\n"
            "/reporte → cifras de las redes\n"
            "/saldo → saldo de HeyGen\n"
            "/pendiente → video con avatar esperando aprobación\n"
            "/generar <i>tema</i> → video con avatar (cuesta saldo de HeyGen)\n\n"
            "📅 Cada día a las 6 p. m. te llega la vista previa de lo de mañana con [Aprobar] [Cambiar texto] [Descartar]. "
            "Lunes, miércoles y viernes a las 12:00 se publica lo aprobado del día.")


def patch_bot(bot: dict, mostrar_id: str, planb_id: str) -> dict:
    f = Flow()
    f.nodes = [n for n in bot["nodes"]]
    f.conns = copy.deepcopy(bot["connections"])
    by = {n["name"]: n for n in f.nodes}
    by["Mensaje al bot"]["parameters"]["updates"] = ["message", "callback_query"]
    by["Leer mensaje"]["parameters"]["jsCode"] = BOT_READ
    by["Responder: ayuda"]["parameters"]["text"] = BOT_HELP
    by["HeyGen: saldo"]["parameters"]["url"] = "https://api.heygen.com/v3/users/me"
    by["Responder: saldo"]["parameters"]["text"] = ("={{ (() => { const w = (($json.data || {}).wallet) || {}; const s = Number(w.remaining_balance || 0); "
                                                   "return '💳 <b>Saldo de HeyGen</b>: USD ' + s.toFixed(2) + (w.auto_reload && w.auto_reload.enabled ? ' (recarga automática activa)' : '') + "
                                                   "'\\nUn video de ~70 s con Avatar IV cuesta unos USD 2.6: alcanza para ' + Math.floor(s / 2.6) + '.' + (s < 2.6 ? '\\n⚠️ Recarga en HeyGen → API.' : '') + "
                                                   "'\\n\\nEl saldo de Claude se revisa en console.anthropic.com → Billing.'; })() }}")
    keep = {n["name"] for n in bot["nodes"]} - {"x"}
    new = {"¿Qué llegó?", "¿Botón?", "Responder botón", "¿Aprobar?", "Hoja: aprobar", "Marcar aprobado", "¿Descartar?", "Hoja: descartar", "Marcar descartado",
           "¿Cambiar texto?", "Pedir texto nuevo", "¿Plan B con fecha?", "Armar plan B", "Avisar: armando", "Plan B", "¿Texto nuevo?", "Hoja: texto nuevo",
           "Avisar: texto guardado", "Volver a mostrar", "Mostrar pieza", "¿/tema?", "¿Tema vacío?", "Responder: cómo usar /tema", "Hoja: anotar idea",
           "Responder: anotado", "¿/temas?", "Hoja: leer ideas", "Listar ideas", "Responder: ideas", "¿/planb?", "Armar /planb", "Avisar: /planb"}
    f.nodes = [n for n in f.nodes if n["name"] not in new]
    for k in list(f.conns):
        if k in new:
            f.conns.pop(k)
    f._x = 0
    Y = 900

    def at(name, x, y):
        next(n for n in f.nodes if n["name"] == name)["position"] = [x, y]

    f.iff("¿Botón?", "$('Leer mensaje').first().json.tipo === 'boton'"); at("¿Botón?", 700, Y)
    f.add("Responder botón", "n8n-nodes-base.telegram", {"resource": "callback", "operation": "answerQuery", "queryId": "={{ $('Leer mensaje').first().json.cb_id }}",
                                                         "additionalFields": {}}, 1.2, C_TG, pos=[950, Y], onError="continueRegularOutput")
    f.iff("¿Aprobar?", "$('Leer mensaje').first().json.accion === 'a'"); at("¿Aprobar?", 1200, Y)
    sheet_put(f, "Hoja: aprobar", "'Calendario!L' + $('Leer mensaje').first().json.fila", "[['Aprobado']]"); at("Hoja: aprobar", 1450, Y)
    edit = lambda label: {"operation": "editMessageText", "messageType": "message", "chatId": CHAT, "messageId": "={{ $('Leer mensaje').first().json.msg_id }}",
                          "text": "={{ $('Leer mensaje').first().json.msg_text + '\\n\\n" + label + "' }}", "additionalFields": {"disable_web_page_preview": True}}
    f.add("Marcar aprobado", "n8n-nodes-base.telegram", edit("✅ APROBADO: se publica ese día a las 12:00."), 1.2, C_TG, pos=[1700, Y], onError="continueRegularOutput")
    f.iff("¿Descartar?", "$('Leer mensaje').first().json.accion === 'd'"); at("¿Descartar?", 1450, Y + 160)
    sheet_put(f, "Hoja: descartar", "'Calendario!L' + $('Leer mensaje').first().json.fila", "[['Descartado']]"); at("Hoja: descartar", 1700, Y + 160)
    f.add("Marcar descartado", "n8n-nodes-base.telegram", edit("❌ DESCARTADO."), 1.2, C_TG, pos=[1950, Y + 160], onError="continueRegularOutput")
    f.iff("¿Cambiar texto?", "$('Leer mensaje').first().json.accion === 'c'"); at("¿Cambiar texto?", 1700, Y + 320)
    f.add("Pedir texto nuevo", "n8n-nodes-base.telegram", {"chatId": CHAT, "replyMarkup": "forceReply", "forceReply": {"force_reply": True},
          "text": "={{ '✏️ Escribe el texto nuevo de Instagram/Facebook y envíalo como RESPUESTA a este mensaje (los hashtags van aparte, no hace falta ponerlos).\\nRef: #F' + $('Leer mensaje').first().json.fila }}",
          "additionalFields": {"appendAttribution": False}}, 1.2, C_TG, pos=[1950, Y + 320])
    f.iff("¿Plan B con fecha?", "['hr','hk','hv'].includes($('Leer mensaje').first().json.accion)"); at("¿Plan B con fecha?", 1950, Y + 480)
    f.code("Armar plan B", "const j = $('Leer mensaje').first().json; return [{ json: { fecha: j.param, modo: j.accion === 'hv' ? 'video_anterior' : j.accion === 'hk' ? 'carrusel' : 'auto', avatar: j.accion === 'hr' } }];")
    at("Armar plan B", 2200, Y + 480)
    f.tg("Avisar: armando", "={{ (() => { const a = $('Leer mensaje').first().json.accion; return a === 'hk' ? '🖼 Armo el anuncio (tarda 1 a 2 minutos)…' : a === 'hv' ? '🎞 Busco el video anterior…' : '🔄 Reviso el saldo de HeyGen otra vez…'; })() }}", html=False)
    at("Avisar: armando", 2450, Y + 480)
    f.run("Plan B", planb_id, False); at("Plan B", 2700, Y + 480)
    f.iff("¿Texto nuevo?", "$('Leer mensaje').first().json.tipo === 'texto_nuevo'"); at("¿Texto nuevo?", 950, Y + 700)
    sheet_put(f, "Hoja: texto nuevo", "'Calendario!G' + $('Leer mensaje').first().json.fila", "[[ $('Leer mensaje').first().json.texto ]]"); at("Hoja: texto nuevo", 1200, Y + 700)
    f.tg("Avisar: texto guardado", "💾 Texto guardado en el calendario. Así queda:", html=False); at("Avisar: texto guardado", 1450, Y + 700)
    f.code("Volver a mostrar", "return [{ json: { fila: $('Leer mensaje').first().json.fila, nota: 'texto actualizado' } }];"); at("Volver a mostrar", 1700, Y + 700)
    f.run("Mostrar pieza", mostrar_id, False); at("Mostrar pieza", 1950, Y + 700)
    f.iff("¿/tema?", "$('Leer mensaje').first().json.tipo === 'tema'"); at("¿/tema?", 1200, Y + 900)
    f.iff("¿Tema vacío?", "!$('Leer mensaje').first().json.arg"); at("¿Tema vacío?", 1450, Y + 900)
    f.tg("Responder: cómo usar /tema", "Escribe el tema después del comando, por ejemplo:\n/tema cierre de caja en bares", html=False); at("Responder: cómo usar /tema", 1700, Y + 860)
    sheet_append(f, "Hoja: anotar idea", "Ideas!A:C", "[[ new Date(Date.now() - 5 * 3600e3).toISOString().slice(0, 10), $('Leer mensaje').first().json.arg.slice(0, 300), 'Pendiente' ]]")
    at("Hoja: anotar idea", 1700, Y + 980)
    f.tg("Responder: anotado", "={{ $json.updates ? 'Anotado ✅' : '⚠️ No pude anotarlo en la pestaña Ideas: ' + JSON.stringify($json.error || $json).slice(0, 200) }}", html=False)
    at("Responder: anotado", 1950, Y + 980)
    f.iff("¿/temas?", "$('Leer mensaje').first().json.tipo === 'temas'"); at("¿/temas?", 1450, Y + 1160)
    f.http("Hoja: leer ideas", "GET", f"{SHEETS}/Ideas!A1:C500", C_DRIVE); at("Hoja: leer ideas", 1700, Y + 1160)
    f.code("Listar ideas", r"""
const esc = s => String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const p = (($json.values) || []).slice(1).filter(r => String(r[2] || '').trim().toLowerCase() === 'pendiente' && r[1]);
return [{ json: { msg: p.length ? '💡 <b>Ideas pendientes</b> (' + p.length + ')\n' + p.slice(0, 30).map((r, i) => (i + 1) + '. ' + esc(r[1]) + ' <i>(' + esc(r[0]) + ')</i>').join('\n') + '\n\nEl plan B usa la primera.' : '💡 No hay ideas pendientes. Agrega una con /tema …' } }];
"""); at("Listar ideas", 1950, Y + 1160)
    f.tg("Responder: ideas", "={{ $json.msg }}"); at("Responder: ideas", 2200, Y + 1160)
    f.iff("¿/planb?", "$('Leer mensaje').first().json.tipo === 'planb'"); at("¿/planb?", 1700, Y + 1320)
    f.code("Armar /planb", "return [{ json: { fecha: '0', modo: 'carrusel', tema: $('Leer mensaje').first().json.arg || '' } }];"); at("Armar /planb", 1950, Y + 1320)
    f.tg("Avisar: /planb", "🖼 Armo un anuncio visual con la siguiente idea pendiente para el próximo lunes, miércoles o viernes libre (1 a 2 minutos)…", html=False)
    at("Avisar: /planb", 2200, Y + 1320)
    f.nodes[-1]["executeOnce"] = True
    # el plan B de /planb reutiliza el mismo nodo "Plan B"
    f.link("Avisar: /planb", "Armar /planb")
    f.link("Armar /planb", "Plan B")
    # enrutar: ¿Eres tu? (si) -> ¿Boton? -> ... -> ¿/reporte? (lo de antes)
    f.conns["¿Eres tú?"]["main"][0] = [{"node": "¿Botón?", "type": "main", "index": 0}]
    f.link("¿Botón?", "Responder botón", 0)
    f.link("¿Botón?", "¿Texto nuevo?", 1)
    f.link("Responder botón", "¿Aprobar?")
    f.link("¿Aprobar?", "Hoja: aprobar", 0)
    f.link("Hoja: aprobar", "Marcar aprobado")
    f.link("¿Aprobar?", "¿Descartar?", 1)
    f.link("¿Descartar?", "Hoja: descartar", 0)
    f.link("Hoja: descartar", "Marcar descartado")
    f.link("¿Descartar?", "¿Cambiar texto?", 1)
    f.link("¿Cambiar texto?", "Pedir texto nuevo", 0)
    f.link("¿Cambiar texto?", "¿Plan B con fecha?", 1)
    f.link("¿Plan B con fecha?", "Avisar: armando", 0)
    f.chain("Avisar: armando", "Armar plan B", "Plan B")
    f.link("¿Texto nuevo?", "Hoja: texto nuevo", 0)
    f.chain("Hoja: texto nuevo", "Avisar: texto guardado", "Volver a mostrar", "Mostrar pieza")
    f.link("¿Texto nuevo?", "¿/tema?", 1)
    f.link("¿/tema?", "¿Tema vacío?", 0)
    f.link("¿Tema vacío?", "Responder: cómo usar /tema", 0)
    f.link("¿Tema vacío?", "Hoja: anotar idea", 1)
    f.link("Hoja: anotar idea", "Responder: anotado")
    f.link("¿/tema?", "¿/temas?", 1)
    f.link("¿/temas?", "Hoja: leer ideas", 0)
    f.chain("Hoja: leer ideas", "Listar ideas", "Responder: ideas")
    f.link("¿/temas?", "¿/planb?", 1)
    f.link("¿/planb?", "Avisar: /planb", 0)
    f.link("¿/planb?", "¿/reporte?", 1)
    # "Avisar: armando" usa $json.modo; desde /planb el aviso es otro nodo
    for n in f.nodes:
        if n["name"] in ("Avisar: texto guardado",):
            n["parameters"]["chatId"] = CHAT
    return {"nodes": f.nodes, "connections": f.conns}


def patch_old(old: dict) -> dict:
    nodes = copy.deepcopy(old["nodes"])
    by = {n["name"]: n for n in nodes}
    by["Cada lunes 7 am"]["disabled"] = True
    lr = by["Leer respuesta de Claude"]["parameters"]
    js = lr["jsCode"]
    guard = r"""
const r = $json;
if (r.error || r.type === 'error') {
  const er = r.error || {}; const m = String(er.message || JSON.stringify(r)).slice(0, 200);
  if (/credit balance|billing/i.test(m) || er.type === 'billing_error') throw new Error('Claude sin saldo: la cuenta de Anthropic se quedó sin créditos. Recarga en console.anthropic.com → Billing. (' + m + ')');
  if (er.type === 'authentication_error' || er.type === 'permission_error') throw new Error('Clave de Claude inválida o sin permiso (credencial "Anthropic Nexa"). (' + m + ')');
  throw new Error('Claude respondió error: ' + m);
}
"""
    if "Claude sin saldo" not in js:
        js = js.replace("const r = $json;", guard, 1)
    new_body = ("const heygen = { type: 'avatar', avatar_id: '" + AVATAR_ID + "', voice_id: '" + VOICE_ID + "', script: d.guion, aspect_ratio: '9:16', "
                "resolution: '720p', background: { type: 'color', value: '#0b0710' }, engine: { type: 'avatar_iv' }, title: 'Nexa · ' + (d.tema || prev.tema || '') };")
    js = re.sub(r"const heygen = \{.*?\};", lambda m: new_body, js, count=1, flags=re.S)
    dup = " necesita_usd: Math.round(((Math.ceil(segundos * 2) + 10) / 60) * 100) / 100,"
    js = js.replace(dup, "")  # idempotente: se quita y se pone una sola vez
    js = js.replace("unidades: Math.ceil(segundos * 2) + 10,", "unidades: Math.ceil(segundos * 2) + 10," + dup, 1)
    lr["jsCode"] = js
    pp = by["Preparar pedido a Claude"]["parameters"]
    pp["jsCode"] = pp["jsCode"].replace("model: 'claude-sonnet-5-5', max_tokens: 6000, system:", "model: 'claude-sonnet-5-5', max_tokens: 16000, output_config: { effort: 'low' }, system:")
    if "Claude no devolvió texto (stop_reason" not in lr["jsCode"]:
        lr["jsCode"] = lr["jsCode"].replace("if (!t) throw new Error('Claude no devolvió texto: '", "if (!t) throw new Error('Claude no devolvió texto (stop_reason: ' + (r.stop_reason || '?') + '): '")
    by["HeyGen: saldo"]["parameters"]["url"] = "https://api.heygen.com/v3/users/me"
    by["¿Alcanza el saldo?"]["parameters"]["jsCode"] = r"""
const w = (($json.data || {}).wallet) || {}, u = (($json.data || {}).usage_based) || {};
const saldo = Number(w.remaining_balance != null ? w.remaining_balance : (u.remaining_credits || 0)) || 0;
const d = $('Leer respuesta de Claude').first().json;
const necesita = d.necesita_usd || Math.round((d.unidades / 60) * 100) / 100;
return [{ json: { ok: saldo >= necesita, saldo, necesita, heygen_body: d.heygen_body } }];
"""
    by["HeyGen: crear video"]["parameters"]["url"] = "https://api.heygen.com/v3/videos"
    by["ID del video"]["parameters"]["jsCode"] = r"""
const id = ($json.data || {}).video_id;
if (!id) throw new Error('HeyGen no creó el video: ' + JSON.stringify($json.error || $json).slice(0, 300));
return [{ json: { video_id: id } }];
"""
    by["HeyGen: estado"]["parameters"]["url"] = "={{ 'https://api.heygen.com/v3/videos/' + $json.video_id }}"
    by["Revisar estado"]["parameters"]["jsCode"] = r"""
const d = $json.data || {};
const id = d.id || d.video_id || $('Esperar 60 s').first().json.video_id;
return [{ json: { video_id: id, status: d.status || 'desconocido', video_url: d.video_url || '', duration: d.duration || 0, fallo: d.status === 'failed' || $runIndex > 25, error: d.failure_message ? (d.failure_code ? d.failure_code + ': ' : '') + String(d.failure_message).slice(0, 300) : '' } }];
"""
    sb = by["Avisar: saldo bajo"]["parameters"]
    sb["text"] = "={{ '⚠️ Saldo de HeyGen insuficiente para el video con avatar.\\nHay USD ' + Number($json.saldo).toFixed(2) + ' y se necesitan unos USD ' + Number($json.necesita).toFixed(2) + '.\\n¿Qué hago?' }}"
    sb["replyMarkup"] = "inlineKeyboard"
    sb["inlineKeyboard"] = {"rows": [{"row": {"buttons": [{"text": "🔄 Recargué, intentar de nuevo", "additionalFields": {"callback_data": "nx:hr:0"}}]}},
                                     {"row": {"buttons": [{"text": "🖼 Hacer anuncio", "additionalFields": {"callback_data": "nx:hk:0"}}]}},
                                     {"row": {"buttons": [{"text": "🎞 Usar un video anterior", "additionalFields": {"callback_data": "nx:hv:0"}}]}}]}
    return {"nodes": nodes, "connections": old["connections"]}


# ------------------------------------------------------------------ principal
def main() -> None:
    secret_archivo = _secret("nexa-archivo-secret.txt")
    hook_secret = _secret("nexa-v2-webhook-secret.txt")
    existing = {w["name"]: w for w in all_workflows()}
    old = call("GET", f"/workflows/{OLD_FLOW}")
    m = re.search(r"q\.k !== '([\w-]+)'", json.dumps([n["parameters"].get("jsCode", "") for n in old["nodes"]]))
    if not m:
        sys.exit("No encontre la clave de los enlaces en el flujo viejo")
    gen_key = m.group(1)
    backend_cred = backend_credential()

    errores_id = upsert("Nexa - Errores", *_nc(flow_errores()), {}, True, existing)
    common = {"errorWorkflow": errores_id}
    upsert("Nexa - Archivo temporal", *_nc(flow_archivo(secret_archivo, backend_cred)), common, True, existing)
    mostrar_id = upsert("Nexa - Mostrar pieza", *_nc(flow_mostrar(secret_archivo)), common, True, existing)
    planb_id = upsert("Nexa - Plan B", *_nc(flow_planb(backend_cred, mostrar_id, gen_key)), common, True, existing)
    upsert("Nexa - Vista previa", *_nc(flow_vista_previa(mostrar_id, planb_id, hook_secret)), common, True, existing)
    upsert("Nexa - Publicar del día", *_nc(flow_publicar(secret_archivo, hook_secret)), common, True, existing)

    # existentes
    bot = call("GET", f"/workflows/{BOT_FLOW}")
    backup(bot)
    pb = patch_bot(bot, mostrar_id, planb_id)
    if bot.get("active"):  # sin esto n8n no vuelve a registrar el webhook de Telegram
        call("POST", f"/workflows/{BOT_FLOW}/deactivate")
    call("PUT", f"/workflows/{BOT_FLOW}", body_of(bot["name"], pb["nodes"], pb["connections"], {**bot.get("settings", {}), **common}))
    call("POST", f"/workflows/{BOT_FLOW}/activate")
    print("actualizado", bot["name"])
    backup(old)
    po = patch_old(old)
    if old.get("active"):
        call("POST", f"/workflows/{OLD_FLOW}/deactivate")
    call("PUT", f"/workflows/{OLD_FLOW}", body_of(old["name"], po["nodes"], po["connections"], {**old.get("settings", {}), **common}))
    call("POST", f"/workflows/{OLD_FLOW}/activate")
    print("actualizado", old["name"], "(lunes 7:00 apagado)")

    # errorWorkflow en el resto de flujos Nexa
    for w in all_workflows():
        if not w["name"].startswith("Nexa - ") or w["id"] in (errores_id, BOT_FLOW, OLD_FLOW) or "(temporal)" in w["name"]:
            continue
        full = call("GET", f"/workflows/{w['id']}")
        if (full.get("settings") or {}).get("errorWorkflow") == errores_id:
            continue
        backup(full)
        was_active = full.get("active")
        if was_active:
            call("POST", f"/workflows/{w['id']}/deactivate")
        call("PUT", f"/workflows/{w['id']}", body_of(full["name"], full["nodes"], full["connections"], {**(full.get("settings") or {}), **common}))
        if was_active:
            call("POST", f"/workflows/{w['id']}/activate")
        print("errorWorkflow ->", w["name"])


def _nc(f: Flow) -> tuple[list, dict]:
    return f.nodes, f.conns


if __name__ == "__main__":
    main()
