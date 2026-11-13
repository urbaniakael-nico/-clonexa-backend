"""Nexa: prospeccion por ubicacion y correos de prospeccion (interno de Clonexa). Idempotente, por nombre.

Crea o actualiza:
- "Nexa - Prospección"          L-V 7:00 Bogota: plan del backend -> Google Places (credencial "Google Places")
                                 -> backend (sin cadenas, sin duplicados, correo solo de la web) -> resumen a
                                 Telegram por zona. Refresca cada 30 dias los datos de Google (place_id se guarda).
                                 Webhook de prueba GET nexa-prospeccion?k=..&zona=..&limite=..&max=..&tipos=..
- "Nexa - Correos prospección"  L-V 7:30: arma el lote del dia (max 25) y lo manda a Telegram con
                                 [✅ Enviar lote] [👀 Ver correo de ejemplo] [❌ Saltar hoy]. Cada 10 min entre 8:00 y
                                 16:50 envia por Gmail el siguiente correo APROBADO (el backend decide horario legal,
                                 espaciado, 1 por semana y seguimiento unico). Sub-flujo de los botones del lote.
                                 Webhook de prueba GET nexa-prospeccion-pruebas?k=..: los 3 correos de ejemplo SOLO
                                 al correo de Clonexa.
Y cambia (antes guarda su JSON en respaldos-clonexa\\n8n\\<fecha>\\):
- "Nexa - Bot de comandos": callback "px:enviar|saltar:<lote>" -> sub-flujo del lote; "pa:<accion>:<id>" y
                     "pv:visitado:<codigo>" -> sub-flujo de "Nexa - Cola asistida".
- "Nexa - Cola asistida" (025p, nuevo): L-V 8:30 hasta 15 negocios para Instagram/Facebook que el dueno envia A
                     MANO ([📋 Copiar texto] [📲 Abrir perfil] [✅ Enviado] [⏭ Saltar] [🚫 No contactar]); webhook de
                     prueba GET nexa-cola-asistida-prueba?k=.. (negocios de prueba); webhook POST nexa-ruta (X-Nexa-Token)
                     con la Ruta del dia de la consola y [✅ Visitado] por parada.
- "Nexa - Correos": cada correo nuevo pasa primero por el backend (/inbound-email): si es un prospecto lo
                     marca "respondio" (o baja si dice NO) y avisa a Telegram; si es baja no se redacta respuesta.
- "Nexa - WhatsApp ventas": si el backend manda "prospecto" (el negocio escribio con su codigo), Claude
                     responde con la demo de la carta video y ofrece agendar la demo.

Secretos (nunca en el repo, nunca se imprimen): referencias\\n8n-key.txt, nexa-ingest-token.txt y
nexa-prospeccion-webhook-secret.txt (se crea si no existe).
Uso: py -3.11 ops/n8n/nexa_prospeccion_flows.py
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import secrets
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nexa_v2_flows as v2  # noqa: E402  (API de n8n, respaldo, Flow, credenciales)

BACKEND = v2.BACKEND + "/api/v1/prospecting"
C_PLACES = {"httpHeaderAuth": {"id": "bNvf7VZcI63JeE3i", "name": "Google Places"}}
C_GMAIL = {"gmailOAuth2": {"id": "dCD1TC3AgRsLjPp6", "name": "Gmail account"}}
F_PROSP = "Nexa - Prospección"
F_MAIL = "Nexa - Correos prospección"
F_BOT = "Nexa - Bot de comandos"
F_CORREOS = "Nexa - Correos"
F_WA = "Nexa - WhatsApp ventas"
F_COLA = "Nexa - Cola asistida"
SECRET_FILE = v2.REFS / "nexa-prospeccion-webhook-secret.txt"
MARK = "/* prospeccion-025i */"


def hook_secret() -> str:
    if not SECRET_FILE.exists():
        SECRET_FILE.write_text(secrets.token_urlsafe(24) + "\n", encoding="utf-8")
    return v2._secret(SECRET_FILE.name)


def node_id(flow: str, name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"prospeccion/{flow}/{name}"))


def fix_ids(f: v2.Flow, flow: str) -> None:
    for n in f.nodes:
        n["id"] = node_id(flow, n["name"])


def be(f: v2.Flow, name: str, method: str, path_expr: str, cred: dict, body: str | None = None, **extra) -> str:
    return f.http(name, method, "=" + BACKEND + path_expr, cred, json_body=body, timeout=170000, **extra)


# ------------------------------------------------------------------ Nexa - Prospección
def flow_prospeccion(cred: dict, secret: str) -> v2.Flow:
    f = v2.Flow()
    f.cron("L-V 7:00", "0 7 * * 1-5")
    f.webhook("Prueba (webhook)", "nexa-prospeccion")
    f.code("Opciones", """
const q = ($json.query || null);
const desde = new Date().toISOString();
if (q) {
  if (q.k !== '__SECRET__') throw new Error('Acceso no autorizado');
  const n = (v, d, max) => { const x = parseInt(v, 10); return Number.isFinite(x) && x > 0 ? Math.min(x, max) : d; };
  return [{ json: { prueba: true, desde, zona: String(q.zona || '').slice(0, 60), tipos: String(q.tipos || '').slice(0, 200), nicho: String(q.nicho || '').slice(0, 20),
    max: n(q.max, 6, 40), limite: q.limite ? n(q.limite, 20, 60) : null } }];
}
return [{ json: { prueba: false, desde, zona: '', tipos: '', nicho: '', max: 34, limite: null } }];
""".replace("__SECRET__", secret))
    be(f, "Plan del backend", "GET", "/n8n/scan-plan?max={{ $json.max }}&zona={{ encodeURIComponent($json.zona) }}&tipos={{ encodeURIComponent($json.tipos) }}&nicho={{ encodeURIComponent($json.nicho || '') }}", cred)
    f.code("Búsquedas", """
const plan = ($json.plan || []);
if (!plan.length) return [{ json: { vacio: true } }];
return plan.map(p => ({ json: p }));
""")
    f.iff("¿Hay búsquedas?", "!$json.vacio")
    f.http("Google Places", "POST", "={{ $json.request.url }}", C_PLACES, json_body="={{ JSON.stringify($json.request.body) }}",
           headers={"X-Goog-FieldMask": "={{ $json.request.field_mask }}"}, timeout=60000)
    f.code("Para el backend", """
const opts = $('Opciones').first().json;
const out = [];
const searches = $('Búsquedas').all();
$input.all().forEach((it, i) => {
  const s = (searches[i] || {}).json || {};
  const r = it.json || {};
  out.push({ json: { body: JSON.stringify({ zone_id: s.zone_id, business_type: s.business_type, places: (r.places || []).slice(0, 60),
    next_page_token: r.nextPageToken || '', limit_new: opts.limite, scan_web: true }), error: r.error ? String(r.error.message || r.error.status || 'error').slice(0, 200) : '' } });
});
return out;
""")
    be(f, "Guardar en el backend", "POST", "/n8n/places", cred, body="={{ $json.body }}")
    be(f, "Resumen del backend", "GET", "/n8n/scan-report?desde={{ encodeURIComponent($('Opciones').first().json.desde) }}", cred, executeOnce=True)
    f.code("Mensaje", """
const r = $json || {};
const opts = $('Opciones').first().json;
let errs = [];
try { errs = $('Para el backend').all().map(x => x.json.error).filter(Boolean); } catch (e) {}
const msg = (opts.prueba ? '🧪 <b>Prueba</b> · ' : '') + (r.mensaje || '⚠️ No pude leer el resumen de la prospección.') +
  (errs.length ? '\\n⚠️ Google Places: ' + errs.slice(0, 2).join(' | ') : '');
return [{ json: { msg } }];
""")
    f.tg("Telegram: resumen", "={{ $json.msg }}")
    f.chain("L-V 7:00", "Opciones")
    f.link("Prueba (webhook)", "Opciones")
    f.chain("Opciones", "Plan del backend", "Búsquedas", "¿Hay búsquedas?", "Google Places", "Para el backend", "Guardar en el backend", "Resumen del backend",
            "Mensaje", "Telegram: resumen")
    f.link("¿Hay búsquedas?", "Resumen del backend", 1)
    # refresco de 30 dias (terminos de Google): solo en la corrida diaria
    f.iff("¿Corrida diaria?", "!$json.prueba")
    be(f, "Por refrescar", "GET", "/n8n/refresh-due?limit=40", cred)
    f.code("Uno por negocio", "const items = ($json.items || []); return items.map(i => ({ json: { ...i, field_mask: $json.field_mask } }));")
    f.http("Google: detalle", "GET", "=https://places.googleapis.com/v1/places/{{ $json.place_id }}?languageCode=es&regionCode=CO", C_PLACES,
           headers={"X-Goog-FieldMask": "={{ $json.field_mask }}"}, timeout=30000)
    f.code("Refresco", """
const due = $('Uno por negocio').all();
return $input.all().map((it, i) => { const r = it.json || {}; const nf = !!(r.error && (r.error.code === 404 || r.error.status === 'NOT_FOUND'));
  return { json: { body: JSON.stringify({ prospect_id: due[i].json.id, place: r.error ? null : r, not_found: nf }), skip: !!(r.error && !nf) } }; }).filter(x => !x.json.skip);
""")
    be(f, "Guardar refresco", "POST", "/n8n/refresh", cred, body="={{ $json.body }}")
    f.link("Opciones", "¿Corrida diaria?")
    f.chain("¿Corrida diaria?", "Por refrescar", "Uno por negocio", "Google: detalle", "Refresco", "Guardar refresco")
    # 025p ahorro: webs ya guardadas, una vez cada 30 dias (sin Google); reporte semanal de gasto (lunes 8:00)
    be(f, "Revisar webs (30 días)", "POST", "/n8n/web-rescan?limit=30", cred, body="{}")
    f.link("¿Corrida diaria?", "Revisar webs (30 días)")
    f.cron("Lunes 8:00", "0 8 * * 1")
    be(f, "Gasto de la semana", "GET", "/n8n/cost-report?dias=7", cred)
    f.tg("Telegram: gasto", "={{ $json.mensaje || '⚠️ No pude leer el gasto de la prospección.' }}")
    f.chain("Lunes 8:00", "Gasto de la semana", "Telegram: gasto")
    _layout(f, {
        "L-V 7:00": (0, 0), "Prueba (webhook)": (0, 200), "Opciones": (240, 100), "Plan del backend": (480, 100), "Búsquedas": (720, 100),
        "¿Hay búsquedas?": (960, 100), "Google Places": (1200, 0), "Para el backend": (1440, 0), "Guardar en el backend": (1680, 0),
        "Resumen del backend": (1920, 100), "Mensaje": (2160, 100), "Telegram: resumen": (2400, 100),
        "¿Corrida diaria?": (480, 420), "Por refrescar": (720, 420), "Uno por negocio": (960, 420), "Google: detalle": (1200, 420),
        "Refresco": (1440, 420), "Guardar refresco": (1680, 420), "Revisar webs (30 días)": (720, 600),
        "Lunes 8:00": (0, 800), "Gasto de la semana": (240, 800), "Telegram: gasto": (480, 800)})
    fix_ids(f, F_PROSP)
    return f


# ------------------------------------------------------------------ Nexa - Correos prospección
def gmail_send(f: v2.Flow, name: str, to: str, subject: str, html: str, sender: str) -> str:
    return f.add(name, "n8n-nodes-base.gmail", {"resource": "message", "operation": "send", "sendTo": to, "subject": subject,
                                               "emailType": "html", "message": html,
                                               "options": {"appendAttribution": False, "senderName": sender}},
                 2.1, C_GMAIL, onError="continueErrorOutput")


def flow_correos(cred: dict, secret: str) -> v2.Flow:
    f = v2.Flow()
    # 1) lote del dia
    f.cron("L-V 7:30", "30 7 * * 1-5")
    be(f, "Armar lote de hoy", "POST", "/n8n/batch/today", cred, body="{}")
    f.iff("¿Hay lote nuevo?", "$json.enviar_aviso === true")
    f.add("Telegram: lote", "n8n-nodes-base.telegram", {
        "chatId": v2.CHAT, "text": "={{ $json.mensaje }}", "replyMarkup": "inlineKeyboard",
        "inlineKeyboard": {"rows": [
            {"row": {"buttons": [{"text": "✅ Enviar lote", "additionalFields": {"callback_data": "=px:enviar:{{ $json.batch.id }}"}}]}},
            {"row": {"buttons": [{"text": "👀 Ver correo de ejemplo", "additionalFields": {"url": "={{ $json.preview_url }}"}}]}},
            {"row": {"buttons": [{"text": "❌ Saltar hoy", "additionalFields": {"callback_data": "=px:saltar:{{ $json.batch.id }}"}}]}}]},
        "additionalFields": {"appendAttribution": False, "disable_web_page_preview": True, "parse_mode": "HTML"}}, 1.2, v2.C_TG)
    f.chain("L-V 7:30", "Armar lote de hoy", "¿Hay lote nuevo?", "Telegram: lote")
    # 2) envio espaciado
    f.cron("Cada 10 min (8:00-16:50)", "*/10 8-16 * * 1-5")
    be(f, "Siguiente correo", "POST", "/n8n/outbox/claim", cred, body="{}")
    f.iff("¿Hay correo?", "!!$json.item")
    gmail_send(f, "Gmail: enviar", "={{ $json.item.to }}", "={{ $json.item.subject }}", "={{ $json.item.html }}", "={{ $json.item.sender_name }}")
    be(f, "Marcar enviado", "POST", "/n8n/outbox/{{ $('Siguiente correo').first().json.item.contact_id }}/sent", cred,
       body="={{ JSON.stringify({ message_id: $json.id || '', thread_id: $json.threadId || '' }) }}")
    be(f, "Marcar fallido", "POST", "/n8n/outbox/{{ $('Siguiente correo').first().json.item.contact_id }}/failed", cred,
       body="={{ JSON.stringify({ error: String(($json.error && ($json.error.message || $json.error)) || 'gmail').slice(0, 400) }) }}")
    f.tg("Telegram: fallo de envío", "={{ '⚠️ Gmail no envió el correo de prospección a ' + $('Siguiente correo').first().json.item.prospect + '. Queda marcado fallido (no se reintenta solo).' }}", html=False)
    f.chain("Cada 10 min (8:00-16:50)", "Siguiente correo", "¿Hay correo?", "Gmail: enviar", "Marcar enviado")
    f.link("Gmail: enviar", "Marcar fallido", 1)
    f.link("Marcar fallido", "Telegram: fallo de envío")
    # 3) botones del lote (lo llama el Bot de comandos)
    f.sub_trigger("Botón del lote")
    be(f, "Decidir lote", "POST", "/n8n/batch/{{ $json.batch_id }}/decide", cred, body="={{ JSON.stringify({ accion: $json.accion }) }}")
    f.add("Editar mensaje del lote", "n8n-nodes-base.telegram", {
        "operation": "editMessageText", "messageType": "message", "chatId": v2.CHAT,
        "messageId": "={{ $('Botón del lote').first().json.msg_id }}",
        "text": "={{ $('Botón del lote').first().json.msg_text + '\\n\\n' + ($json.mensaje || 'No pude cambiar el lote: ' + JSON.stringify($json).slice(0, 200)) }}",
        "additionalFields": {"disable_web_page_preview": True}}, 1.2, v2.C_TG)
    f.chain("Botón del lote", "Decidir lote", "Editar mensaje del lote")
    # 4) correos de ejemplo (solo al correo de Clonexa)
    f.webhook("Probar plantillas", "nexa-prospeccion-pruebas", respond="lastNode")
    f.code("¿Autorizado?", "if ((($json.query || {}).k) !== '__SECRET__') throw new Error('Acceso no autorizado'); return [{ json: {} }];".replace("__SECRET__", secret))
    be(f, "Correos de ejemplo", "POST", "/n8n/test-emails", cred, body="{}")
    f.code("Uno por plantilla", "return ($json.items || []).filter(i => !i.bloqueado).map(i => ({ json: i }));", alwaysOutputData=False)
    gmail_send(f, "Gmail: ejemplo", "={{ $json.to }}", "={{ $json.subject }}", "={{ $json.html }}", "={{ $json.sender_name }}")
    be(f, "Ejemplo enviado", "POST", "/n8n/outbox/{{ $('Uno por plantilla').item.json.contact_id }}/sent", cred,
       body="={{ JSON.stringify({ message_id: $json.id || '', thread_id: $json.threadId || '' }) }}")
    f.code("Respuesta", """
const all = $('Correos de ejemplo').first().json.items || [];
return [{ json: { enviados: all.filter(i => !i.bloqueado).map(i => ({ para: i.to, asunto: i.subject, demo: i.demo_url, whatsapp: i.wa_url, baja: i.unsub_url })),
  bloqueados: all.filter(i => i.bloqueado).map(i => i.to) } }];
""", executeOnce=True)
    f.chain("Probar plantillas", "¿Autorizado?", "Correos de ejemplo", "Uno por plantilla", "Gmail: ejemplo", "Ejemplo enviado", "Respuesta")
    _layout(f, {
        "L-V 7:30": (0, 0), "Armar lote de hoy": (240, 0), "¿Hay lote nuevo?": (480, 0), "Telegram: lote": (720, 0),
        "Cada 10 min (8:00-16:50)": (0, 240), "Siguiente correo": (240, 240), "¿Hay correo?": (480, 240), "Gmail: enviar": (720, 240),
        "Marcar enviado": (960, 180), "Marcar fallido": (960, 320), "Telegram: fallo de envío": (1200, 320),
        "Botón del lote": (0, 520), "Decidir lote": (240, 520), "Editar mensaje del lote": (480, 520),
        "Probar plantillas": (0, 760), "¿Autorizado?": (240, 760), "Correos de ejemplo": (480, 760), "Uno por plantilla": (720, 760),
        "Gmail: ejemplo": (960, 760), "Ejemplo enviado": (1200, 760), "Respuesta": (1440, 760)})
    fix_ids(f, F_MAIL)
    return f


# ------------------------------------------------------------------ Nexa - Cola asistida (025p)
def tg_buttons(f: v2.Flow, name: str, text: str, rows: list, chat: str = v2.CHAT, **extra) -> str:
    """Telegram con botones mixtos: ("texto", "cb", valor) o ("texto", "url", valor)."""
    def btn(t, kind, val):
        return {"text": t, "additionalFields": {"callback_data" if kind == "cb" else "url": val}}
    return f.add(name, "n8n-nodes-base.telegram", {
        "chatId": chat, "text": text, "replyMarkup": "inlineKeyboard",
        "inlineKeyboard": {"rows": [{"row": {"buttons": [btn(*b) for b in row]}} for row in rows]},
        "additionalFields": {"appendAttribution": False, "disable_web_page_preview": True, "parse_mode": "HTML"}}, 1.2, v2.C_TG, **extra)


def flow_cola(cred: dict, secret: str) -> v2.Flow:
    """Cola ASISTIDA de Instagram/Facebook: Nexa prepara el texto, el dueno lo envia a mano. Nunca se envia nada
    automatico a Instagram ni a Facebook (la API no lo permite y Meta bloquea bots)."""
    f = v2.Flow()
    # 1) cola del dia (L-V 8:30) o simulada (webhook de prueba con los negocios de prueba)
    f.cron("L-V 8:30", "30 8 * * 1-5")
    be(f, "Cola de hoy", "POST", "/n8n/assisted/today", cred, body="{}")
    f.webhook("Prueba (webhook)", "nexa-cola-asistida-prueba")
    f.code("¿Autorizado?", "if ((($json.query || {}).k) !== '__SECRET__') throw new Error('Acceso no autorizado'); return [{ json: {} }];"
           .replace("__SECRET__", secret))
    be(f, "Cola simulada", "POST", "/n8n/assisted/test", cred, body="{}")
    f.iff("¿Hay cola?", "$json.enviar === true")
    f.tg("Telegram: cabecera", "={{ $json.cabecera }}")
    f.code("Uno por negocio", "return ($('¿Hay cola?').first().json.items || []).map(i => ({ json: i }));")
    tg_buttons(f, "Telegram: negocio", "={{ $json.mensaje }}", [
        [("📋 Copiar texto", "cb", "={{ $json.botones.copiar }}"), ("📲 Abrir perfil", "url", "={{ $json.perfil }}")],
        [("✅ Enviado", "cb", "={{ $json.botones.enviado }}"), ("⏭ Saltar", "cb", "={{ $json.botones.saltar }}")],
        [("🚫 No contactar", "cb", "={{ $json.botones.bloquear }}")]])
    f.chain("L-V 8:30", "Cola de hoy", "¿Hay cola?", "Telegram: cabecera", "Uno por negocio", "Telegram: negocio")
    f.chain("Prueba (webhook)", "¿Autorizado?", "Cola simulada", "¿Hay cola?")
    # 2) botones (los llama el Bot de comandos): pa:copiar|enviado|saltar|bloquear:<id> y pv:visitado:<codigo>
    f.sub_trigger("Botón de la cola")
    f.iff("¿Visita?", "$json.ns === 'pv'")
    be(f, "Registrar visita", "POST", "/n8n/visited", cred, body="={{ JSON.stringify({ codigo: $json.param }) }}")
    be(f, "Acción de la cola", "POST", "/n8n/assisted/action", cred,
       body="={{ JSON.stringify({ accion: $json.accion, id: Number($json.param) || 0 }) }}")
    f.code("Resultado", """
const b = $('Botón de la cola').first().json;
const r = $json || {};
const visita = b.ns === 'pv';
return [{ json: { texto: r.texto || '', editar: visita ? !!r.ok : !!r.editar, mensaje: r.mensaje || ('No pude registrar: ' + JSON.stringify(r).slice(0, 150)),
  msg_id: b.msg_id, msg_text: b.msg_text || '' } }];
""")
    f.iff("¿Copiar?", "!!$json.texto")
    f.tg("Telegram: texto para copiar", "={{ $json.texto }}", html=False)
    f.iff("¿Editar?", "$json.editar === true")
    f.add("Editar mensaje", "n8n-nodes-base.telegram", {
        "operation": "editMessageText", "messageType": "message", "chatId": v2.CHAT, "messageId": "={{ $json.msg_id }}",
        "text": "={{ $json.msg_text + '\\n\\n' + $json.mensaje }}", "additionalFields": {"disable_web_page_preview": True}}, 1.2, v2.C_TG)
    f.tg("Telegram: aviso", "={{ $json.mensaje }}", html=False)
    f.link("Botón de la cola", "¿Visita?")
    f.link("¿Visita?", "Registrar visita", 0)
    f.link("¿Visita?", "Acción de la cola", 1)
    f.link("Registrar visita", "Resultado")
    f.link("Acción de la cola", "Resultado")
    f.chain("Resultado", "¿Copiar?", "Telegram: texto para copiar")
    f.link("¿Copiar?", "¿Editar?", 1)
    f.link("¿Editar?", "Editar mensaje", 0)
    f.link("¿Editar?", "Telegram: aviso", 1)
    # 3) ruta del dia desde la consola (el backend llama con X-Nexa-Token)
    f.add("Ruta (backend)", "n8n-nodes-base.webhook", {"httpMethod": "POST", "path": "nexa-ruta", "responseMode": "onReceived",
                                                       "authentication": "headerAuth", "options": {}}, 2, cred,
          webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, "hook/nexa-ruta")))
    tg_buttons(f, "Telegram: ruta", "={{ $json.body.cabecera }}", [[("🗺️ Abrir la ruta en Google Maps", "url", "={{ $json.body.ruta_url }}")]])
    f.code("Una por parada", "return (($('Ruta (backend)').first().json.body || {}).paradas || []).map(p => ({ json: p }));")
    tg_buttons(f, "Telegram: parada", "={{ $json.mensaje }}", [[("📍 Google Maps", "url", "={{ $json.maps_url }}"), ("✅ Visitado", "cb", "={{ $json.callback }}")]])
    f.chain("Ruta (backend)", "Telegram: ruta", "Una por parada", "Telegram: parada")
    _layout(f, {
        "L-V 8:30": (0, 0), "Cola de hoy": (240, 0), "Prueba (webhook)": (0, 200), "¿Autorizado?": (240, 200), "Cola simulada": (480, 200),
        "¿Hay cola?": (720, 80), "Telegram: cabecera": (960, 80), "Uno por negocio": (1200, 80), "Telegram: negocio": (1440, 80),
        "Botón de la cola": (0, 480), "¿Visita?": (240, 480), "Registrar visita": (480, 400), "Acción de la cola": (480, 560),
        "Resultado": (720, 480), "¿Copiar?": (960, 480), "Telegram: texto para copiar": (1200, 400), "¿Editar?": (1200, 580),
        "Editar mensaje": (1440, 520), "Telegram: aviso": (1440, 660),
        "Ruta (backend)": (0, 860), "Telegram: ruta": (240, 860), "Una por parada": (480, 860), "Telegram: parada": (720, 860)})
    fix_ids(f, F_COLA)
    return f


def _layout(f: v2.Flow, pos: dict) -> None:
    for n in f.nodes:
        if n["name"] in pos:
            n["position"] = list(pos[n["name"]])


# ------------------------------------------------------------------ cambios a flujos existentes
def _node(flow: dict, name: str) -> dict:
    return next(n for n in flow["nodes"] if n["name"] == name)


def _drop(flow: dict, names: set) -> None:
    flow["nodes"] = [n for n in flow["nodes"] if n["name"] not in names]
    for k in list(flow["connections"]):
        if k in names:
            flow["connections"].pop(k)
            continue
        for outs in flow["connections"][k].get("main", []):
            outs[:] = [c for c in outs if c["node"] not in names]


def patch_bot(bot: dict, sub_id: str, cola_id: str) -> dict:
    bot = copy.deepcopy(bot)
    added = {"¿Lote de prospección?", "Responder botón (lote)", "Datos del lote", "Lote de prospección",
             "¿Cola asistida?", "Responder botón (cola)", "Datos de la cola", "Cola asistida"}
    _drop(bot, added)
    leer = _node(bot, "Leer mensaje")
    js = leer["parameters"]["jsCode"]
    old = "tipo: ns === 'nx' ? 'boton' : 'otro'"
    if old in js:
        js = js.replace(old, "tipo: ns === 'nx' ? 'boton' : ns === 'px' ? 'prospeccion' : 'otro'")
    old2 = "ns === 'px' ? 'prospeccion' : 'otro'"
    if old2 in js:
        js = js.replace(old2, "ns === 'px' ? 'prospeccion' : (ns === 'pa' || ns === 'pv') ? 'asistida' : 'otro'")
    assert "ns === 'px'" in js and "'asistida'" in js, "Leer mensaje cambio: revisar el parche de prospeccion"
    if "ns: ns," not in js:
        js = js.replace("accion: accion || '', param: arg || '',", "ns: ns, accion: accion || '', param: arg || '',", 1)
    assert "ns: ns," in js, "Leer mensaje cambio: no encontre accion/param"
    leer["parameters"]["jsCode"] = js
    f = v2.Flow()
    f.iff("¿Lote de prospección?", "$('Leer mensaje').first().json.tipo === 'prospeccion'")
    f.add("Responder botón (lote)", "n8n-nodes-base.telegram", {"resource": "callback", "operation": "answerQuery",
          "queryId": "={{ $('Leer mensaje').first().json.cb_id }}", "additionalFields": {"text": "Listo"}}, 1.2, v2.C_TG)
    f.code("Datos del lote", """
const j = $('Leer mensaje').first().json;
return [{ json: { accion: j.accion === 'enviar' ? 'enviar' : 'saltar', batch_id: Number(j.param) || 0, msg_id: j.msg_id, msg_text: j.msg_text } }];
""")
    f.run("Lote de prospección", sub_id, wait=False)
    # cola asistida y ruta de visitas (025p)
    f.iff("¿Cola asistida?", "$('Leer mensaje').first().json.tipo === 'asistida'")
    f.add("Responder botón (cola)", "n8n-nodes-base.telegram", {"resource": "callback", "operation": "answerQuery",
          "queryId": "={{ $('Leer mensaje').first().json.cb_id }}",
          "additionalFields": {"text": "={{ $('Leer mensaje').first().json.accion === 'copiar' ? 'Te mando el texto abajo' : 'Listo' }}"}}, 1.2, v2.C_TG)
    f.code("Datos de la cola", """
const j = $('Leer mensaje').first().json;
return [{ json: { ns: j.ns === 'pv' ? 'pv' : 'pa', accion: String(j.accion || ''), param: String(j.param || ''), msg_id: j.msg_id, msg_text: j.msg_text } }];
""")
    f.run("Cola asistida", cola_id, wait=False)
    _layout(f, {"¿Cola asistida?": (560, -80), "Responder botón (cola)": (800, -160), "Datos de la cola": (1040, -160), "Cola asistida": (1280, -160),
                "¿Lote de prospección?": (560, 120), "Responder botón (lote)": (800, 40), "Datos del lote": (1040, 40), "Lote de prospección": (1280, 40)})
    fix_ids(f, F_BOT)
    bot["nodes"] += f.nodes
    eres = bot["connections"]["¿Eres tú?"]["main"]
    eres[0] = [{"node": "¿Cola asistida?", "type": "main", "index": 0}]
    bot["connections"].update(f.conns)
    bot["connections"]["¿Cola asistida?"] = {"main": [[{"node": "Responder botón (cola)", "type": "main", "index": 0}],
                                                      [{"node": "¿Lote de prospección?", "type": "main", "index": 0}]]}
    bot["connections"]["Responder botón (cola)"] = {"main": [[{"node": "Datos de la cola", "type": "main", "index": 0}]]}
    bot["connections"]["Datos de la cola"] = {"main": [[{"node": "Cola asistida", "type": "main", "index": 0}]]}
    bot["connections"]["¿Lote de prospección?"] = {"main": [[{"node": "Responder botón (lote)", "type": "main", "index": 0}],
                                                           [{"node": "¿Botón?", "type": "main", "index": 0}]]}
    bot["connections"]["Responder botón (lote)"] = {"main": [[{"node": "Datos del lote", "type": "main", "index": 0}]]}
    bot["connections"]["Datos del lote"] = {"main": [[{"node": "Lote de prospección", "type": "main", "index": 0}]]}
    return bot


def patch_correos(flow: dict, cred: dict) -> dict:
    flow = copy.deepcopy(flow)
    added = {"¿Es prospecto?", "Unir prospecto", "¿Respuesta de prospecto?", "Avisar: prospecto", "¿Sigue a Claude?"}
    _drop(flow, added)
    f = v2.Flow()
    be(f, "¿Es prospecto?", "POST", "/n8n/inbound-email", cred,
       body="={{ JSON.stringify({ de: $json.de, asunto: $json.asunto, cuerpo: $json.cuerpo, thread_id: $json.threadId || '' }) }}")
    f.add("Unir prospecto", "n8n-nodes-base.code", {"mode": "runOnceForEachItem", "jsCode": """
const orig = $('Filtrar automáticos').item.json;
const r = $json || {};
return { json: { ...orig, es_prospecto: !!r.es_prospecto, baja: !!r.baja, aviso: r.aviso || '' } };
"""}, 2)
    f.iff("¿Respuesta de prospecto?", "$json.es_prospecto === true")
    f.tg("Avisar: prospecto", "={{ $json.aviso }}")
    f.iff("¿Sigue a Claude?", "$json.baja !== true")
    _layout(f, {"¿Es prospecto?": (220, 160), "Unir prospecto": (440, 160), "¿Respuesta de prospecto?": (660, 300),
                "Avisar: prospecto": (880, 300), "¿Sigue a Claude?": (660, 160)})
    fix_ids(f, F_CORREOS)
    flow["nodes"] += f.nodes
    flow["connections"]["Filtrar automáticos"] = {"main": [[{"node": "¿Es prospecto?", "type": "main", "index": 0}]]}
    flow["connections"]["¿Es prospecto?"] = {"main": [[{"node": "Unir prospecto", "type": "main", "index": 0}]]}
    flow["connections"]["Unir prospecto"] = {"main": [[{"node": "¿Sigue a Claude?", "type": "main", "index": 0},
                                                       {"node": "¿Respuesta de prospecto?", "type": "main", "index": 0}]]}
    flow["connections"]["¿Respuesta de prospecto?"] = {"main": [[{"node": "Avisar: prospecto", "type": "main", "index": 0}]]}
    flow["connections"]["¿Sigue a Claude?"] = {"main": [[{"node": "Preparar a Claude", "type": "main", "index": 0}]]}
    return flow


WA_CONTEXT_OLD = "  primer_mensaje: src.primer,\n  ahora_colombia: isoBog(Date.now()),\n};"
WA_CONTEXT_NEW = "  primer_mensaje: src.primer,\n  ahora_colombia: isoBog(Date.now()),\n  prospecto: body.prospecto || null, " + MARK + "\n};"
WA_PROMPT_OLD = "{ type: 'text', text: 'CONTEXTO DE ESTA CONVERSACIÓN:\\n' + JSON.stringify(ctxInfo) }"
WA_PROMPT_NEW = ("{ type: 'text', text: 'CONTEXTO DE ESTA CONVERSACIÓN:\\n' + JSON.stringify(ctxInfo) + (body.prospecto && !body.prospecto.baja ? "
                 "'\\n\\nPROSPECTO ' + " + json.dumps(MARK) + " + ': este negocio (' + body.prospecto.negocio + ', ' + body.prospecto.tipo + ') nos escribió PRIMERO con el código ' + body.prospecto.codigo + ' del correo de Clonexa. "
                 "Agradece que escribió y llámalo por el nombre del negocio. ' + (['bar'].includes(body.prospecto.tipo) ? "
                 "'Habla de las 5 fugas de dinero de un bar (inventario, pedidos por QR, mesas abiertas, caja y turnos) en 2 líneas. ' : "
                 "['taller'].includes(body.prospecto.tipo) ? 'Habla de la nómina en 5 minutos y el costo real por prenda en 2 líneas. ' : "
                 "'Muéstrale la carta en video con QR en 2 líneas: sus clientes escanean el QR de la mesa y ven sus platos en video, de frente y de perfil, y piden desde el celular. "
                 "Comparte este enlace de la demo: https://www.clonexa.com.co/?utm_source=whatsapp&utm_medium=prospeccion&utm_content=' + body.prospecto.codigo + '#carta-video . ') + "
                 "'Luego ofrece agendar una demo de 20 minutos (sigue las reglas de AGENDAR). Sin precios.' : '') }")


def patch_wa(flow: dict) -> dict:
    flow = copy.deepcopy(flow)
    prep = _node(flow, "Preparar")
    js = prep["parameters"]["jsCode"]
    if MARK not in js:
        assert WA_CONTEXT_OLD in js and WA_PROMPT_OLD in js, "Preparar cambio: revisar el parche de prospeccion"
        js = js.replace(WA_CONTEXT_OLD, WA_CONTEXT_NEW).replace(WA_PROMPT_OLD, WA_PROMPT_NEW)
    prep["parameters"]["jsCode"] = js
    return flow


def save_export(flow: dict, label: str) -> Path:
    d = v2.BACKUPS / dt.date.today().isoformat()
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{flow['name'].replace(' ', '_')}_{flow['id']}_{label}.json"
    p.write_text(json.dumps(flow, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def put_existing(flow: dict, nodes_conns: dict) -> None:
    """PUT de un flujo existente (respaldo antes). Los de Telegram: desactivar -> PUT -> activar."""
    wid = flow["id"]
    v2.backup(flow)
    was_active = flow.get("active")
    if was_active:
        v2.call("POST", f"/workflows/{wid}/deactivate")
    v2.call("PUT", f"/workflows/{wid}", v2.body_of(flow["name"], nodes_conns["nodes"], nodes_conns["connections"], flow.get("settings") or {}))
    if was_active:
        v2.call("POST", f"/workflows/{wid}/activate")
    print("actualizado", flow["name"], wid)


def main() -> None:
    cred = v2.backend_credential()
    secret = hook_secret()
    existing = {w["name"]: w for w in v2.all_workflows()}
    err = (existing.get("Nexa - Errores") or {}).get("id")
    settings = {"errorWorkflow": err} if err else {}
    pf = flow_prospeccion(cred, secret)
    pid = v2.upsert(F_PROSP, pf.nodes, pf.conns, settings, True, existing)
    mf = flow_correos(cred, secret)
    mid = v2.upsert(F_MAIL, mf.nodes, mf.conns, settings, True, existing)
    cf = flow_cola(cred, secret)
    cid = v2.upsert(F_COLA, cf.nodes, cf.conns, settings, True, existing)
    bot = v2.call("GET", f"/workflows/{existing[F_BOT]['id']}")
    put_existing(bot, patch_bot(bot, mid, cid))
    cor = v2.call("GET", f"/workflows/{existing[F_CORREOS]['id']}")
    put_existing(cor, patch_correos(cor, cred))
    wa = v2.call("GET", f"/workflows/{existing[F_WA]['id']}")
    put_existing(wa, patch_wa(wa))
    for wid in (pid, mid, cid, existing[F_BOT]["id"], existing[F_CORREOS]["id"], existing[F_WA]["id"]):
        print("exportado", save_export(v2.call("GET", f"/workflows/{wid}"), "despues").name)


if __name__ == "__main__":
    main()
