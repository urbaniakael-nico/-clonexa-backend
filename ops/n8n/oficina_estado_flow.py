"""n8n: flujo "Oficina - Estado" para la Oficina 3D de la Consola v2+ (interno de Clonexa). Idempotente.

GET <n8n>/webhook/oficina-estado con la cabecera X-Oficina-Secret. Sin ella (o con otra) responde 401 y no
consulta nada; el flujo solo guarda la huella SHA-256 del secreto, nunca el secreto. Responde en UNA sola respuesta:
- workflows: cada flujo "Nexa - *", "VOLTAGE *" y "Clonexa - *": activo o no, si esta corriendo ahora,
  ultima ejecucion (hora y estado), ultima buena, ultima con error y ejecuciones de hoy (Bogota).
- recent: ultimas ejecuciones terminadas de esos flujos (para "Actividad en vivo").
- calendar: hoja "Nexa - Calendario de contenido": piezas en "Listo para aprobar", "Aprobado", piezas de
  esta semana y la proxima publicacion.
- ideas: pestaña "Ideas": temas pendientes.
- report: pestaña "Reporte semanal": fecha del ultimo reporte (ok false si la pestaña no existe).
No guarda ejecuciones buenas (la respuesta trae la lista de flujos y pesaria en la base de n8n).

Secretos (nunca en el repo, nunca se imprimen): referencias\\n8n-key.txt (API de n8n) y
referencias\\oficina-estado-secret.txt (se crea si no existe). El backend lo lee de las variables de
Railway OFICINA_N8N_URL y OFICINA_N8N_SECRET (las pone --railway).
Uso: py -3.11 ops/n8n/oficina_estado_flow.py [--railway]
"""
from __future__ import annotations

import hashlib
import secrets
import shutil
import subprocess
import urllib.parse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nexa_v2_flows as v2  # noqa: E402  (API de n8n, respaldo, Flow, credenciales)

NAME = "Oficina - Estado"
PATH = "oficina-estado"
HEADER = "X-Oficina-Secret"
SECRET_FILE = v2.REFS / "oficina-estado-secret.txt"
CRED_HOOK = "Oficina - secreto del webhook"
CRED_API = "n8n API (Oficina)"
BACKEND_SERVICE = "-clonexa-backend"
URL = f"{v2.BASE}/webhook/{PATH}"


def hook_secret() -> str:
    if not SECRET_FILE.exists():
        SECRET_FILE.write_text(secrets.token_urlsafe(32) + "\n", encoding="utf-8")
    return v2._secret(SECRET_FILE.name)


def header_credential(name: str, header: str, value: str) -> dict:
    """Crea (o actualiza el valor de) una credencial de cabecera. Devuelve la referencia del nodo."""
    for c in v2.call("GET", "/credentials?limit=100").get("data", []):
        if c["name"] == name:
            try:
                v2.call("PATCH", f"/credentials/{c['id']}", {"name": name, "type": "httpHeaderAuth", "data": {"name": header, "value": value}})
            except RuntimeError:
                pass  # versiones de n8n sin PATCH: se reusa la credencial tal como esta
            return {"httpHeaderAuth": {"id": c["id"], "name": name}}
    c = v2.call("POST", "/credentials", {"name": name, "type": "httpHeaderAuth", "data": {"name": header, "value": value}})
    return {"httpHeaderAuth": {"id": c["id"], "name": name}}


ARMAR = r"""
const norm = s => String(s == null ? '' : s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
const toIso = s => { s = String(s || '').trim(); let m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/); if (m) return m[3] + '-' + m[2].padStart(2,'0') + '-' + m[1].padStart(2,'0'); m = s.match(/^(\d{4})-(\d{2})-(\d{2})/); return m ? m[0] : ''; };
const bogota = new Date(Date.now() - 5 * 3600e3); const today = bogota.toISOString().slice(0, 10);
const startToday = new Date(today + 'T05:00:00Z').getTime();
const dow = (bogota.getUTCDay() + 6) % 7; const monday = new Date(Date.parse(today + 'T12:00:00Z') - dow * 86400e3).toISOString().slice(0, 10);
const sunday = new Date(Date.parse(monday + 'T12:00:00Z') + 6 * 86400e3).toISOString().slice(0, 10);
const flows = $('Lista de flujos').all().map(i => i.json).filter(f => f.id);
const execs = $('Ejecuciones').all().map(i => i.json);
const runningRaw = ($('Corriendo').first() || {json: {}}).json;
const running = new Set(((runningRaw && runningRaw.data) || []).map(e => String(e.workflowId)));
const recent = [];
const workflows = flows.map((f, idx) => {
  const list = ((execs[idx] && execs[idx].data) || []).filter(e => String(e.workflowId) === String(f.id));
  const done = list.filter(e => e.stoppedAt && e.status !== 'running' && e.status !== 'waiting');
  const last = done[0] || null; const ok = done.find(e => e.status === 'success'); const bad = done.find(e => ['error', 'crashed'].includes(e.status));
  const todays = list.filter(e => Date.parse(e.startedAt) >= startToday);
  done.slice(0, 3).forEach(e => recent.push({workflow: f.name, status: e.status, started_at: e.startedAt, stopped_at: e.stoppedAt}));
  return {id: f.id, name: f.name, active: !!f.active, running: running.has(String(f.id)) || list.some(e => e.status === 'running'),
    last: last ? {status: last.status, started_at: last.startedAt, stopped_at: last.stoppedAt} : null,
    last_ok_at: ok ? ok.stoppedAt : null, last_error_at: bad ? bad.stoppedAt : null,
    today_runs: todays.length, today_errors: todays.filter(e => ['error', 'crashed'].includes(e.status)).length, today_runs_capped: list.length >= 100 && todays.length === list.length};
});
recent.sort((a, b) => String(b.stopped_at).localeCompare(String(a.stopped_at)));
const vals = name => { const j = ($(name).first() || {json: {}}).json || {}; return Array.isArray(j.values) ? j.values : null; };
// Calendario: A fecha, C formato, E tema, L estado
const calRows = vals('Calendario');
let calendar = {ok: false};
if (calRows) {
  const rows = calRows.slice(1).map(r => ({iso: toIso(r[0]), fecha: String(r[0] || '').trim(), formato: String(r[2] || '').trim(), tema: String(r[4] || '').trim(), est: norm(r[11])})).filter(r => r.iso);
  const ready = rows.filter(r => r.est === 'listo para aprobar'); const approved = rows.filter(r => r.est === 'aprobado');
  const upcoming = rows.filter(r => r.iso >= today && r.est !== 'publicado' && r.est !== 'descartado').sort((a, b) => a.iso.localeCompare(b.iso));
  const nxt = upcoming.find(r => r.est === 'aprobado') || upcoming[0] || null;
  calendar = {ok: true, ready: ready.length, approved: approved.length, week_pieces: rows.filter(r => r.iso >= monday && r.iso <= sunday).length,
    next: nxt ? {fecha: nxt.fecha, formato: nxt.formato, tema: nxt.tema.slice(0, 80), estado: nxt.est} : null,
    ready_items: ready.sort((a, b) => a.iso.localeCompare(b.iso)).slice(0, 8).map(r => ({fecha: r.fecha, formato: r.formato, tema: r.tema.slice(0, 80)}))};
}
const ideaRows = vals('Ideas');
let ideas = {ok: false};
if (ideaRows) {
  const pend = ideaRows.slice(1).filter(r => String(r[1] || '').trim() && (norm(r[2]) === 'pendiente' || !norm(r[2])));
  ideas = {ok: true, pending: pend.length, items: pend.slice(0, 5).map(r => String(r[1]).trim().slice(0, 80))};
}
const repRows = vals('Reporte semanal');
let report = {ok: false};
if (repRows) {
  const dates = repRows.slice(1).map(r => toIso(r[0])).filter(Boolean).sort();
  report = {ok: true, rows: Math.max(0, repRows.length - 1), last_date: dates.length ? dates[dates.length - 1] : null};
}
return [{json: {ok: true, generated_at: new Date().toISOString(), workflows, recent: recent.slice(0, 15), calendar, ideas, report}}];
"""

LISTA = r"""
const j = $input.first().json || {};
const keep = n => /^(Nexa - |VOLTAGE|Clonexa - )/i.test(String(n || ''));
const out = (j.data || []).filter(w => keep(w.name)).map(w => ({json: {id: w.id, name: w.name, active: !!w.active}}));
return out.length ? out : [{json: {}}];
"""


def build(api_cred: dict, secret_hash: str) -> v2.Flow:
    """La cabecera se compara por su huella SHA-256: el secreto nunca queda guardado en el flujo."""
    f = v2.Flow()
    f.add("Oficina (webhook)", "n8n-nodes-base.webhook", {"httpMethod": "GET", "path": PATH, "responseMode": "responseNode", "options": {}}, 2,
          webhookId="5f0f8e3c-8d5b-4f0e-9a6c-0f1c1a7e0b11")
    f.add("Huella de la cabecera", "n8n-nodes-base.crypto", {"action": "hash", "type": "SHA256", "encoding": "hex", "dataPropertyName": "huella",
                                                              "value": "={{ $json.headers['x-oficina-secret'] || '-' }}"}, 1)
    f.iff("¿Cabecera válida?", f"$json.huella === '{secret_hash}'")
    f.add("Sin autorización (401)", "n8n-nodes-base.respondToWebhook", {"respondWith": "json", "responseBody": '={"ok": false, "detail": "No autorizado"}',
                                                                       "options": {"responseCode": 401}}, 1.1)
    f.http("Flujos", "GET", v2.API + "/workflows?limit=250", api_cred, timeout=20000)
    f.code("Lista de flujos", LISTA, alwaysOutputData=True)
    f.http("Ejecuciones", "GET", "=" + v2.API + "/executions?workflowId={{ $json.id }}&limit=100", api_cred, timeout=20000, alwaysOutputData=True)
    f.http("Corriendo", "GET", v2.API + "/executions?status=running&limit=100", api_cred, timeout=20000, executeOnce=True)
    f.http("Calendario", "GET", f"{v2.SHEETS}/{v2.CAL_RANGE}", v2.C_DRIVE, executeOnce=True, timeout=20000)
    f.http("Ideas", "GET", f"{v2.SHEETS}/{urllib.parse.quote('Ideas!A1:C500')}", v2.C_DRIVE, executeOnce=True, timeout=20000)
    f.http("Reporte semanal", "GET", f"{v2.SHEETS}/{urllib.parse.quote(chr(39) + 'Reporte semanal' + chr(39) + '!A1:Z300')}", v2.C_DRIVE,
           executeOnce=True, timeout=20000)
    f.code("Armar respuesta", ARMAR)
    f.add("Responder", "n8n-nodes-base.respondToWebhook", {"respondWith": "json", "responseBody": "={{ JSON.stringify($json) }}", "options": {}}, 1.1)
    f.chain("Oficina (webhook)", "Huella de la cabecera", "¿Cabecera válida?")
    f.link("¿Cabecera válida?", "Flujos", 0)
    f.link("¿Cabecera válida?", "Sin autorización (401)", 1)
    f.chain("Flujos", "Lista de flujos", "Ejecuciones", "Corriendo", "Calendario", "Ideas", "Reporte semanal", "Armar respuesta", "Responder")
    for n in f.nodes:
        n["id"] = str(v2.uuid.uuid5(v2.uuid.NAMESPACE_URL, "oficina-estado/" + n["name"]))
    return f


def drop_credential(name: str) -> None:
    for c in v2.call("GET", "/credentials?limit=100").get("data", []):
        if c["name"] == name:
            v2.call("DELETE", f"/credentials/{c['id']}")
            print("credencial quitada:", name)


def set_railway(secret: str) -> None:
    """Variables del backend en Railway sin imprimir el secreto (no redespliega: lo hace el push)."""
    for key, value in (("OFICINA_N8N_URL", URL), ("OFICINA_N8N_SECRET", secret)):
        exe = shutil.which("railway") or shutil.which("railway.cmd") or "railway"  # Windows: railway.cmd
        r = subprocess.run([exe, "variable", "set", key, "--stdin", "--service", BACKEND_SERVICE, "--skip-deploys"], input=value,
                           capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[2]))
        print(f"Railway {key}:", "ok" if r.returncode == 0 else f"falló ({r.returncode})")
        if r.returncode != 0:
            sys.exit(1)


def main() -> None:
    secret = hook_secret()
    api_cred = header_credential(CRED_API, "X-N8N-API-KEY", v2.KEY)
    existing = {w["name"]: w for w in v2.all_workflows()}
    f = build(api_cred, hashlib.sha256(secret.encode("utf-8")).hexdigest())
    wid = v2.upsert(NAME, f.nodes, f.conns, {"saveDataSuccessExecution": "none", "saveDataErrorExecution": "all", "saveManualExecutions": False,
                                            "executionTimeout": 60}, True, existing)
    v2.backup(v2.call("GET", f"/workflows/{wid}"))
    drop_credential(CRED_HOOK)  # version anterior (cabecera de n8n respondia 403, no 401)
    print("webhook:", URL)
    if "--railway" in sys.argv:
        set_railway(secret)


if __name__ == "__main__":
    main()
