"""Flujo de n8n "Nexa - WhatsApp ventas": arma el JSON (sin secretos) y lo despliega.

Meta -> backend (/api/v1/nexa-wa/webhook) -> este flujo (webhook "nexa-wa-ventas",
cabecera X-Nexa-Forward) -> Claude decide la respuesta -> Cloud API de WhatsApp
-> registro en /api/v1/nexa-wa/outbound -> aviso a Telegram solo en demo
agendada, pidio persona y errores; resumen diario a las 6 p. m.

Credenciales (n8n):
- "WhatsApp Nexa" (Header Auth: Authorization: Bearer <token>) <- referencias\\whatsapp-token.txt
- "Nexa WA reenvio" (Header Auth: X-Nexa-Forward) <- referencias\\nexa-wa-forward-secret.txt
- Claude "Anthropic Nexa", Google Calendar y "Telegram Nexa": las que ya existen.
Nunca imprime llaves ni tokens.

Uso:
  py -3.11 ops/n8n/nexa_whatsapp_flow.py --write     # solo escribe ops/n8n/nexa-whatsapp-ventas.json
  py -3.11 ops/n8n/nexa_whatsapp_flow.py --deploy    # credenciales + crear/actualizar + activar
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "nexa-whatsapp-ventas.json"
REFS = Path(r"C:\Users\valef\Desktop\referencias")
N8N = "https://main-production-54df.up.railway.app/api/v1"
NAME = "Nexa - WhatsApp ventas"
BACKEND = "https://clonexa-backend-production.up.railway.app"
GRAPH = "https://graph.facebook.com/v26.0/1331771733361816/messages"
CHAT_ID = "5126243056"
MODEL = "claude-sonnet-5-5"
CREDS = {
    "anthropic": {"anthropicApi": {"id": "X6Q45d5OD6gz0wiS", "name": "Anthropic Nexa"}},
    "calendar": {"googleCalendarOAuth2Api": {"id": "pYEUvBLK0TOMnW7T", "name": "Google Calendar account"}},
    "telegram": {"telegramApi": {"id": "Somdc8F0zAOWWHcY", "name": "Telegram Nexa"}},
}
WA_CRED = "WhatsApp Nexa"
FWD_CRED = "Nexa WA reenvio"

# ---------------------------------------------------------------- el papel de Nexa
SYSTEM = """Eres Nexa, la asistente virtual con IA de Clonexa, y atiendes el WhatsApp de ventas de Clonexa (+57 314 479 8220). Te escriben dueños y encargados de negocios que llegaron por su cuenta.

QUÉ ES CLONEXA (en una frase): software en la nube que conecta la operación del negocio en un solo sistema (pedidos, cocina, caja, inventario, turnos, nómina, clientes y reportes) y se adapta a cada negocio. Funciona en los celulares, tabletas y computadores que ya tienen, sin equipos especiales. Tarifa plana con usuarios ilimitados (no se cobra por usuario). Lo configuramos con su marca y acompañamos a su equipo; el soporte sigue por WhatsApp. La factura electrónica DIAN está en desarrollo y llega próximamente: nunca digas que ya existe.

ESTILO
- Cálida y profesional, como una buena asesora. Cada mensaje corto: máximo 3 o 4 líneas. Normalmente 1 o 2 mensajes por turno, nunca más de 3.
- Sin emojis en exceso (como mucho uno, y no en todos los mensajes).
- Responde en el idioma del cliente (español o inglés). Si escribe en inglés, todo en inglés, opciones incluidas.
- Una pregunta a la vez. No repitas preguntas por datos que ya están en el contacto.
- No inventes nada. Si algo no está en esta guía, pasa a una persona.

PRIMER MENSAJE (cuando primer_mensaje es true)
- Saluda, di que eres Nexa, la asistente virtual con IA de Clonexa, y di qué es Clonexa en una frase.
- Incluye siempre: "Al continuar aceptas el tratamiento de tus datos para atenderte: https://www.clonexa.com.co/privacidad" (en inglés: "By continuing you accept the processing of your data to assist you: https://www.clonexa.com.co/privacidad").
- Si el cliente hizo una pregunta concreta, respóndela breve.
- Si aún no dijo su tipo de negocio, termina con un mensaje tipo "list" que pregunte el tipo de negocio con estas opciones exactas: Restaurante, Bar, Taller o fábrica, Tienda o cadena, Distribuidora, Call center, Personal en campo, Otro (en inglés: Restaurant, Bar, Workshop or factory, Store or chain, Distributor, Call center, Field staff, Other). Si ya lo dijo, sigue calificando.

CALIFICAR: 2 o 3 preguntas cortas, una por turno, solo lo que falte: 1) ciudad; 2) tamaño (cuántas personas, sedes o mesas); 3) qué les cuesta hoy (pedidos, inventario, turnos, nómina, cierres de caja, control del personal...). Con el tipo de negocio y al menos otro dato, la etapa es "calificado".

MOSTRAR VALOR (un mensaje, cuando ya sabes qué les cuesta): conecta su dolor con 2 o 3 funciones reales de su sector y comparte el enlace de su página. Usa solo estas funciones y estas páginas:
- Restaurante -> https://www.clonexa.com.co/restaurantes?utm_source=whatsapp&utm_medium=nexa : menú QR por mesa (piden desde el celular, sin descargar app); panel del mesero en el celular directo a cocina; pantalla de cocina por columnas con el tiempo de cada comanda; domicilios en la misma pantalla; la caja cobra la cuenta exacta (efectivo, transferencia o tarjeta); cierre del día por método de pago; inventario; reportes; turnos y nómina.
- Bar -> https://www.clonexa.com.co/bares?utm_source=whatsapp&utm_medium=nexa : carta QR por mesa con la cuenta de la mesa y pedir canción; pantalla de barra con el estado de cada pedido; juegos en vivo desde el celular con la tabla en el TV y el premio de la ronda; fidelización; cierre por día de negocio (lo vendido en la madrugada queda en la misma noche); inventario de licores; reportes.
- Taller o fábrica -> https://www.clonexa.com.co/talleres-y-fabricas?utm_source=whatsapp&utm_medium=nexa : tablero del taller en una tableta con PIN para cada persona; tiempo por referencia; producción por lote (prendas cerradas, avance, días por lote, mano de obra por prenda); nómina desde las horas reales (ordinarias y extra); cotizaciones y cuentas de cobro en PDF.
- Call center -> https://www.clonexa.com.co/call-centers?utm_source=whatsapp&utm_medium=nexa : supervisión de asesores en vivo (en llamada, disponible, en pausa); registro de llamadas con resultado y duración; cotizaciones y tickets imprimibles; contratos y avales; tesorería y cartera por cobrar; se implementa por etapas. NO hay grabación de llamadas ni IVR: no los menciones ni los prometas.
- Personal en campo -> https://www.clonexa.com.co/personal-en-campo?utm_source=whatsapp&utm_medium=nexa : inicio y cierre de turno desde el celular o el bot de Telegram; si está dentro de su zona de trabajo (GPS por zonas); pausas y tiempo de cada persona en vivo; órdenes de material con número (aprobar, entregar, devolver) que descuentan inventario; horas listas para la nómina. NO hay mapas de ruta ni seguimiento de rutas: no los menciones.
- Tienda o cadena, Distribuidora u Otro -> https://www.clonexa.com.co/que-es-clonexa?utm_source=whatsapp&utm_medium=nexa : apertura de cada tienda cuando su equipo inicia turno; solicitudes a bodega con su estado (enviada, alistando, lista, recibida); inventario; turnos, nómina y reportes; se construye a la medida sobre la base de Clonexa.

PRECIOS Y FECHAS
- NUNCA des precios, rangos, descuentos ni promociones, aunque insistan. Di: "Armamos una cotización a la medida en la demo" y ofrece agendarla.
- NUNCA prometas fechas (de implementación, de entrega ni de funciones nuevas).

AGENDAR LA DEMO
- Después de mostrar valor, o antes si el cliente la pide, ofrece una demo de 30 minutos por Google Meet con el equipo de Clonexa.
- Si acepta o pide horarios: accion "ofrecer_horarios". Tu mensaje solo introduce los horarios (por ejemplo "Te propongo estos horarios:"). NO escribas horarios ni botones de horarios: el sistema agrega los horarios libres reales como botones.
- Si el cliente propone un día u hora: ponlo en preferencia_horario (desde = fecha y hora ISO con -05:00, franja = "manana" o "tarde") y usa accion "ofrecer_horarios".
- Pide su correo para enviarle la invitación (es opcional). Si lo da, ponlo en datos_detectados.correo.
- Las demos son de lunes a viernes, de 9:00 a. m. a 5:00 p. m., hora de Colombia.
- Si el contacto ya tiene demo agendada (demo_at), no ofrezcas otra salvo que quiera cambiarla.

PASAR A UNA PERSONA: si pide hablar con una persona, si pregunta algo que no está en esta guía (integraciones puntuales, temas legales, soporte de una cuenta que ya existe, precios después de ofrecer la demo) o si hay una queja: responde que Nicolás, del equipo de Clonexa, le escribe pronto por este mismo chat; etapa "pidio_persona"; accion "pasar_a_persona"; en resumen, una línea con lo que necesita. No inventes la respuesta.

OTRAS ETAPAS: "no_interesado" si dice claramente que no le interesa (despídete amable, sin insistir). "baja" solo si pide no recibir más mensajes. Si nada cambia, repite la etapa actual del contacto.

DATOS DETECTADOS: llena solo lo que el cliente dijo (nombre, idioma "es" o "en", tipo_negocio, ciudad, tamano, dolor, correo); deja "" lo que no sepas.

SALIDA: solo el JSON del esquema. Tipos de mensaje: "text" (opciones vacía), "buttons" (de 1 a 3 opciones de máximo 20 caracteres) o "list" (de 1 a 10 opciones de máximo 24 caracteres)."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["mensajes", "datos_detectados", "etapa", "accion", "preferencia_horario", "resumen"],
    "properties": {
        "mensajes": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["tipo", "texto", "opciones"],
            "properties": {"tipo": {"type": "string", "enum": ["text", "buttons", "list"]}, "texto": {"type": "string"},
                           "opciones": {"type": "array", "items": {"type": "string"}}}}},
        "datos_detectados": {"type": "object", "additionalProperties": False,
                             "required": ["nombre", "idioma", "tipo_negocio", "ciudad", "tamano", "dolor", "correo"],
                             "properties": {k: {"type": "string"} for k in ["nombre", "idioma", "tipo_negocio", "ciudad", "tamano", "dolor", "correo"]}},
        "etapa": {"type": "string", "enum": ["nuevo", "calificado", "demo_agendada", "pidio_persona", "no_interesado", "baja"]},
        "accion": {"type": "string", "enum": ["ninguna", "ofrecer_horarios", "crear_cita", "pasar_a_persona"]},
        "preferencia_horario": {"type": "object", "additionalProperties": False, "required": ["desde", "franja"],
                                "properties": {"desde": {"type": "string"}, "franja": {"type": "string", "enum": ["", "manana", "tarde"]}}},
        "resumen": {"type": "string"},
    },
}

# ---------------------------------------------------------------- código de los nodos (JavaScript de n8n)
# Común a varios nodos: hora de Colombia (UTC-5 fijo), festivos, horarios libres y textos.
COMMON = r"""
const TZ_MS = 5 * 3600000;
const FESTIVOS = new Set(['2026-01-01','2026-01-12','2026-03-23','2026-04-02','2026-04-03','2026-05-01','2026-05-18','2026-06-08','2026-06-15','2026-06-29',
  '2026-07-20','2026-08-07','2026-08-17','2026-10-12','2026-11-02','2026-11-16','2026-12-08','2026-12-25','2027-01-01','2027-01-11','2027-03-22','2027-03-25',
  '2027-03-26','2027-05-01','2027-05-10','2027-05-31','2027-06-07','2027-07-05','2027-07-20','2027-08-07','2027-08-16','2027-10-18','2027-11-01','2027-11-15',
  '2027-12-08','2027-12-25']);
const pad = (n) => String(n).padStart(2, '0');
const bog = (ms) => { const d = new Date(ms - TZ_MS); return { y: d.getUTCFullYear(), mo: d.getUTCMonth(), d: d.getUTCDate(), dow: d.getUTCDay(), h: d.getUTCHours(), mi: d.getUTCMinutes() }; };
const dayKey = (b) => `${b.y}-${pad(b.mo + 1)}-${pad(b.d)}`;
const isoBog = (ms) => { const b = bog(ms); return `${dayKey(b)}T${pad(b.h)}:${pad(b.mi)}:00-05:00`; };
const isEn = (c) => String((c && c.idioma) || '').toLowerCase().startsWith('en');
const DOW = { es: ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'], en: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] };
const DOWL = { es: ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'], en: ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'] };
const MON = { es: ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'], en: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'] };
const MONL = { es: ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'],
  en: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'] };
const h12 = (b, long) => `${b.h % 12 || 12}:${pad(b.mi)} ${long ? (b.h < 12 ? 'a. m.' : 'p. m.') : (b.h < 12 ? 'am' : 'pm')}`;
// Botón: "Jue 29 oct 10:00 am" (máx. 20 caracteres) / "Thu Oct 29 10:00 am"
const slotTitle = (ms, en) => { const b = bog(ms); return en ? `${DOW.en[b.dow]} ${MON.en[b.mo]} ${b.d} ${h12(b)}` : `${DOW.es[b.dow]} ${b.d} ${MON.es[b.mo]} ${h12(b)}`; };
const slotLong = (ms, en) => { const b = bog(ms); return en ? `${DOWL.en[b.dow]}, ${MONL.en[b.mo]} ${b.d} at ${h12(b, false)} (Colombia time)`
  : `el ${DOWL.es[b.dow]} ${b.d} de ${MONL.es[b.mo]} a las ${h12(b, true)} (hora de Colombia)`; };
const workable = (ms) => { const b = bog(ms); const m = b.h * 60 + b.mi; return b.dow >= 1 && b.dow <= 5 && !FESTIVOS.has(dayKey(b)) && m >= 540 && m + 30 <= 1020; };
const overlaps = (ms, busy) => busy.some((x) => { const s = Date.parse(x.start), e = Date.parse(x.end); return s < ms + 1800000 && e > ms; });
// Tres horarios libres: lunes a viernes 9:00-17:00 de Colombia, 30 min, con 3 h de anticipación, separados al menos 3 h.
function pickSlots(busy, nowMs, pref) {
  pref = pref || {};
  const minMs = nowMs + 3 * 3600000;
  const step = 1800000;
  let start = Math.ceil(minMs / step) * step;
  const wanted = Date.parse(pref.desde || '');
  const out = [];
  if (Number.isFinite(wanted) && wanted >= minMs && wanted % step === 0 && workable(wanted) && !overlaps(wanted, busy)) out.push(wanted);
  if (Number.isFinite(wanted) && wanted > start) start = Math.ceil(wanted / step) * step;
  const end = start + 14 * 86400000;
  for (let t = start; t < end && out.length < 3; t += step) {
    if (!workable(t) || overlaps(t, busy)) continue;
    const h = bog(t).h;
    if (pref.franja === 'manana' && h >= 12) continue;
    if (pref.franja === 'tarde' && h < 12) continue;
    if (out.every((c) => Math.abs(c - t) >= 3 * 3600000)) out.push(t);
  }
  return out.sort((a, b) => a - b);
}
const freeBusyBody = (fromMs, toMs) => ({ timeMin: new Date(fromMs).toISOString(), timeMax: new Date(toMs).toISOString(), timeZone: 'America/Bogota', items: [{ id: 'primary' }] });
const busyOf = (j) => ((j && j.calendars && j.calendars.primary && j.calendars.primary.busy) || []);
const calOk = (j) => !!(j && j.calendars && j.calendars.primary && !j.calendars.primary.errors && !j.error);
const T = {
  es: { solo_texto: 'Por ahora solo leo mensajes de texto. Escríbeme tu pregunta o, si prefieres, agendamos una demo con el equipo.',
    intro: 'Hola, soy Nexa, la asistente virtual con IA de Clonexa.',
    consent: 'Al continuar aceptas el tratamiento de tus datos para atenderte: https://www.clonexa.com.co/privacidad',
    elegir: 'Elige un horario para la demo (30 min por Google Meet, hora de Colombia).', correo: ' Si me dejas tu correo, te llega la invitación.',
    ocupado: 'Ese horario se acaba de ocupar. Te propongo estos:', sin_horarios: 'Estos días la agenda está llena. Nicolás, del equipo de Clonexa, te escribe para cuadrar la demo.',
    listo: (when, link, mail) => `¡Listo! Tu demo quedó agendada ${when}.${link ? `\nEnlace de Google Meet: ${link}` : ''}${mail ? `\nTe llega la invitación a ${mail}.` : ''}`,
    no_cita: 'No pude agendarla en este momento. Nicolás, del equipo de Clonexa, te confirma el horario en breve.',
    espera: 'Ya te respondemos en un momento.', lista: 'Elegir' },
  en: { solo_texto: 'For now I can only read text messages. Write me your question or, if you prefer, we can book a demo with the team.',
    intro: "Hi, I'm Nexa, Clonexa's AI virtual assistant.",
    consent: 'By continuing you accept the processing of your data to assist you: https://www.clonexa.com.co/privacidad',
    elegir: 'Pick a time for the demo (30 min on Google Meet, Colombia time).', correo: " If you share your email, you'll get the invite.",
    ocupado: 'That time was just taken. Here are other options:', sin_horarios: 'The calendar is full these days. Nicolás from Clonexa will message you to set up the demo.',
    listo: (when, link, mail) => `Done! Your demo is booked for ${when}.${link ? `\nGoogle Meet link: ${link}` : ''}${mail ? `\nThe invite is on its way to ${mail}.` : ''}`,
    no_cita: "I couldn't book it right now. Nicolás from Clonexa will confirm the time shortly.",
    espera: "We'll get back to you in a moment.", lista: 'Choose' },
};
const tx = (c) => T[isEn(c) ? 'en' : 'es'];
// Respuesta base: lo que viaja hasta "Armar envío".
const base = (src, extra) => ({ wa_id: src.wa_id, contacto: src.contacto, primer: src.primer,
  respuesta: { mensajes: [], etapa: src.contacto.etapa, datos_detectados: {}, accion: 'ninguna', consentimiento_visto: !!src.primer, demo: null, resumen: '' },
  aviso: '', error_text: '', ...(extra || {}) });
"""

PREPARAR = COMMON + r"""
const body = $input.first().json.body || {};
const msg = body.mensaje || {};
const c = body.contacto || {};
const src = { wa_id: c.wa_id, contacto: c, primer: !!body.primer_mensaje };
if (!c.wa_id) return [];
if (msg.tipo === 'reaction' || msg.tipo === 'unsupported' || msg.tipo === 'system') return [];
const t = tx(c);
if (!msg.respondible) {
  const out = base(src, { ruta: 'fijo' });
  out.respuesta.mensajes = [{ tipo: 'text', texto: src.primer ? `${t.intro} ${t.solo_texto}\n\n${t.consent}` : t.solo_texto, opciones: [] }];
  return [{ json: out }];
}
const reply = String(msg.reply_id || '');
if (reply.startsWith('cita|')) {
  const ms = Date.parse(reply.slice(5));
  if (Number.isFinite(ms)) return [{ json: base(src, { ruta: 'cita', slot: ms, fb_body: freeBusyBody(ms, ms + 1800000) }) }];
}
const hist = Array.isArray(body.historial) ? body.historial : [];
const messages = [];
for (const h of hist) {
  const role = h.direccion === 'out' ? 'assistant' : 'user';
  let text = String(h.texto || '').trim();
  if (!text) text = h.tipo && h.tipo !== 'text' ? `[${h.tipo}]` : '';
  if (!text) continue;
  if (!messages.length && role === 'assistant') continue;
  const last = messages[messages.length - 1];
  if (last && last.role === role) last.content += `\n${text}`;
  else messages.push({ role, content: text });
}
if (!messages.length || messages[messages.length - 1].role !== 'user') messages.push({ role: 'user', content: String(msg.texto || '').trim() || '[mensaje]' });
const ctxInfo = {
  contacto: { nombre: c.nombre || '', idioma: c.idioma || '', tipo_negocio: c.tipo_negocio || '', ciudad: c.ciudad || '', tamano: c.tamano || '', dolor: c.dolor || '',
    correo: c.correo || '', etapa: c.etapa || 'nuevo', demo_at: c.demo_at || '' },
  primer_mensaje: src.primer,
  ahora_colombia: isoBog(Date.now()),
};
const claude_body = {
  model: __MODEL__,
  max_tokens: 1500,
  thinking: { type: 'between_tools' },
  output_config: { effort: 'low', format: { type: 'json_schema', schema: __SCHEMA__ } },
  system: [{ type: 'text', text: __SYSTEM__, cache_control: { type: 'ephemeral' } }, { type: 'text', text: 'CONTEXTO DE ESTA CONVERSACIÓN:\n' + JSON.stringify(ctxInfo) }],
  messages,
};
return [{ json: { ...base(src, { ruta: 'claude' }), claude_body } }];
"""

LEER_CLAUDE = COMMON + r"""
const src = $('Preparar').first().json;
const r = $input.first().json || {};
const out = base(src);
const t = tx(src.contacto);
const block = (Array.isArray(r.content) ? r.content : []).find((b) => b && b.type === 'text');
let d = null;
try { d = block ? JSON.parse(block.text) : null; } catch (e) { d = null; }
const msgs = d && Array.isArray(d.mensajes) ? d.mensajes.filter((m) => m && String(m.texto || '').trim()).slice(0, 3) : [];
if (!d || !msgs.length) {
  const why = r.error ? (r.error.message || JSON.stringify(r.error)).slice(0, 300) : (r.stop_reason ? `stop_reason ${r.stop_reason}` : 'respuesta sin JSON');
  out.respuesta.mensajes = [{ tipo: 'text', texto: t.espera, opciones: [] }];
  out.respuesta.consentimiento_visto = false;
  out.aviso = 'error';
  out.error_text = `Claude no respondió (${why}).`;
  return [{ json: { ...out, ofrecer: false } }];
}
let accion = d.accion || 'ninguna';
const pref = d.preferencia_horario || {};
if (accion === 'crear_cita') accion = 'ofrecer_horarios'; // la cita se confirma tocando un botón con un horario libre real
out.respuesta = { mensajes: msgs.map((m) => ({ tipo: m.tipo, texto: String(m.texto).trim(), opciones: Array.isArray(m.opciones) ? m.opciones.map(String) : [] })),
  etapa: d.etapa || src.contacto.etapa, datos_detectados: d.datos_detectados || {}, accion, consentimiento_visto: true, demo: null, resumen: d.resumen || '' };
if (accion === 'pasar_a_persona') { out.respuesta.etapa = 'pidio_persona'; out.aviso = 'persona'; }
const now = Date.now();
return [{ json: { ...out, ofrecer: accion === 'ofrecer_horarios', pref, fb_body: freeBusyBody(now, now + 15 * 86400000) } }];
"""

# Después de "Calendar: horarios" (desde Claude) o "Calendar: otros horarios" (si el elegido se ocupó).
PROPONER = COMMON + r"""
const prev = $('__PREV__').first().json;
const cal = $input.first().json || {};
const out = { ...prev, respuesta: { ...prev.respuesta, mensajes: (prev.respuesta.mensajes || []).filter((m) => m.tipo !== 'buttons') } };
const c = prev.contacto || {};
const t = tx(c);
if (!calOk(cal)) {
  out.respuesta.mensajes.push({ tipo: 'text', texto: t.sin_horarios, opciones: [] });
  out.aviso = 'error';
  out.error_text = `Google Calendar no respondió (${String((cal.error && (cal.error.message || cal.error)) || 'sin datos').slice(0, 200)}).`;
  return [{ json: out }];
}
const slots = pickSlots(busyOf(cal), Date.now(), prev.pref || {});
if (!slots.length) {
  out.respuesta.mensajes.push({ tipo: 'text', texto: t.sin_horarios, opciones: [] });
  out.respuesta.etapa = 'pidio_persona';
  out.aviso = out.aviso || 'persona';
  out.respuesta.resumen = 'No hay horarios libres en los próximos días para la demo.';
  return [{ json: out }];
}
const en = isEn(c);
out.respuesta.mensajes = out.respuesta.mensajes.slice(0, 2);
out.respuesta.mensajes.push({ tipo: 'buttons', texto: t.elegir + (c.correo ? '' : t.correo), opciones: slots.map((s) => slotTitle(s, en)), ids: slots.map((s) => `cita|${isoBog(s)}`) });
return [{ json: out }];
"""

REVISAR = COMMON + r"""
const src = $('Preparar').first().json;
const cal = $input.first().json || {};
const c = src.contacto || {};
const ms = src.slot;
const ok = calOk(cal) && workable(ms) && ms >= Date.now() + 3600000 && !overlaps(ms, busyOf(cal));
if (!ok) {
  const out = base(src, { libre: false, pref: { desde: '', franja: '' }, fb_body: freeBusyBody(Date.now(), Date.now() + 15 * 86400000) });
  out.respuesta.mensajes = [{ tipo: 'text', texto: tx(c).ocupado, opciones: [] }];
  return [{ json: out }];
}
const who = [c.nombre, c.tipo_negocio, c.ciudad].filter(Boolean).join(' · ');
const ev_body = {
  summary: `Demo Clonexa · ${c.nombre || c.wa_id}${c.tipo_negocio ? ` (${c.tipo_negocio})` : ''}`,
  description: `Demo agendada por Nexa (WhatsApp).\n${who}\nWhatsApp: +${c.wa_id}\nTamaño: ${c.tamano || '—'}\nQué les cuesta: ${c.dolor || '—'}\nConversación: ${c.console_url || ''}`,
  start: { dateTime: isoBog(ms), timeZone: 'America/Bogota' },
  end: { dateTime: isoBog(ms + 1800000), timeZone: 'America/Bogota' },
  attendees: c.correo ? [{ email: c.correo }] : [],
  conferenceData: { createRequest: { requestId: `nexa-${c.wa_id}-${ms}`, conferenceSolutionKey: { type: 'hangoutsMeet' } } },
  reminders: { useDefault: true },
};
return [{ json: { ...base(src), libre: true, ev_body } }];
"""

CONFIRMAR = COMMON + r"""
const ev = $input.first().json || {};
const src = $('Preparar').first().json;
const c = src.contacto || {};
const t = tx(c);
const out = base(src);
if (!ev.id) {
  out.respuesta.mensajes = [{ tipo: 'text', texto: t.no_cita, opciones: [] }];
  out.respuesta.etapa = 'pidio_persona';
  out.respuesta.resumen = 'Eligió un horario de demo pero Google Calendar no creó el evento.';
  out.aviso = 'error';
  out.error_text = `No se pudo crear la cita (${String((ev.error && (ev.error.message || ev.error)) || 'sin id').slice(0, 200)}).`;
  return [{ json: out }];
}
const link = ev.hangoutLink || ((ev.conferenceData && (ev.conferenceData.entryPoints || []).find((p) => p.entryPointType === 'video')) || {}).uri || '';
out.respuesta.mensajes = [{ tipo: 'text', texto: t.listo(slotLong(src.slot, isEn(c)), link, c.correo), opciones: [] }];
out.respuesta.etapa = 'demo_agendada';
out.respuesta.accion = 'crear_cita';
out.respuesta.demo = { inicio: isoBog(src.slot), enlace: link || ev.htmlLink || '' };
out.aviso = 'demo';
return [{ json: out }];
"""

# Una pieza por mensaje para la Cloud API (texto, botones hasta 3, lista hasta 10). Solo respuestas: nunca plantillas.
ARMAR = r"""
const j = $input.first().json;
const en = String((j.contacto && j.contacto.idioma) || '').startsWith('en');
const cut = (s, n) => { s = String(s || '').trim(); return s.length > n ? s.slice(0, n - 1).trimEnd() + '…' : s; };
const items = [];
for (const [i, m0] of (j.respuesta.mensajes || []).slice(0, 3).entries()) {
  const m = { ...m0, opciones: (m0.opciones || []).map(String).filter((o) => o.trim()) };
  let tipo = m.tipo;
  if (tipo === 'buttons' && m.opciones.length > 3) tipo = 'list';
  if ((tipo === 'buttons' || tipo === 'list') && !m.opciones.length) tipo = 'text';
  const id = (k) => (m.ids && m.ids[k]) || `op|${k + 1}`;
  let graph;
  if (tipo === 'buttons') {
    graph = { type: 'interactive', interactive: { type: 'button', body: { text: cut(m.texto, 1024) },
      action: { buttons: m.opciones.slice(0, 3).map((o, k) => ({ type: 'reply', reply: { id: id(k), title: cut(o, 20) } })) } } };
  } else if (tipo === 'list') {
    graph = { type: 'interactive', interactive: { type: 'list', body: { text: cut(m.texto, 1024) },
      action: { button: en ? 'Choose' : 'Elegir', sections: [{ title: en ? 'Options' : 'Opciones', rows: m.opciones.slice(0, 10).map((o, k) => ({ id: id(k), title: cut(o, 24) })) }] } } };
  } else {
    graph = { type: 'text', text: { body: cut(m.texto, 4096), preview_url: /https?:\/\//.test(m.texto) } };
  }
  graph = { messaging_product: 'whatsapp', recipient_type: 'individual', to: j.wa_id, ...graph };
  const shown = tipo === 'buttons' ? m.opciones.slice(0, 3).map((o) => cut(o, 20)) : tipo === 'list' ? m.opciones.slice(0, 10).map((o) => cut(o, 24)) : [];
  items.push({ json: { i, tipo, texto: m.texto, opciones: shown, graph, src: i === 0 ? j : null } });
}
return items;
"""

JUNTAR = r"""
const ctx = $('Armar envío').all().map((x) => x.json);
const res = $input.all().map((x) => x.json || {});
const src = (ctx[0] && ctx[0].src) || {};
const mensajes = ctx.map((m, k) => {
  const r = res[k] || {};
  const id = r.messages && r.messages[0] && r.messages[0].id;
  const err = r.error ? String(r.error.message || (r.error.error && r.error.error.message) || JSON.stringify(r.error)).slice(0, 300) : '';
  return { meta_id: id || null, tipo: m.tipo, texto: m.texto, opciones: m.opciones, estado: id ? 'sent' : 'failed', error: id ? null : (err || 'sin id de Meta') };
});
const failed = mensajes.filter((m) => m.estado === 'failed');
const r = src.respuesta || {};
const sentAny = mensajes.some((m) => m.estado === 'sent');
let aviso = src.aviso || '';
let error_text = src.error_text || '';
if (failed.length) { aviso = 'error'; error_text = `${error_text ? error_text + ' ' : ''}Meta no envió ${failed.length} de ${mensajes.length} mensajes: ${failed[0].error}`; }
const outbound = { wa_id: src.wa_id, mensajes, datos_detectados: r.datos_detectados || {}, etapa: r.etapa || null,
  consentimiento_visto: !!(r.consentimiento_visto && sentAny), accion: r.accion || 'ninguna', demo: r.demo || null, nota: r.resumen ? `Nexa: ${r.resumen}` : null };
return [{ json: { outbound, aviso, error_text, contacto: src.contacto || {}, respuesta: r } }];
"""

TELEGRAM_MSG = r"""
const j = $('Juntar envío').first().json;
const back = $input.first().json || {};
const c = { ...(j.contacto || {}), ...((back && back.contacto) || {}) };
const d = (j.respuesta && j.respuesta.datos_detectados) || {};
const esc = (s) => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const LABEL = { nuevo: 'Nuevo', calificado: 'Calificado', demo_agendada: 'Demo agendada', pidio_persona: 'Pidió persona', no_interesado: 'No interesado', baja: 'Baja' };
const num = String(c.wa_id || '');
const phone = num.length === 12 && num.startsWith('57') ? `+57 ${num.slice(2, 5)} ${num.slice(5, 8)} ${num.slice(8)}` : `+${num}`;
const etapa = (j.outbound && j.outbound.etapa) || c.etapa;
const head = { demo: '📅 <b>Demo agendada</b>', persona: '🙋 <b>Pidió una persona</b>', error: '⚠️ <b>Nexa WhatsApp: error</b>' }[j.aviso] || '<b>Nexa WhatsApp</b>';
const lines = [head, `<b>${esc(c.nombre || d.nombre || 'Sin nombre')}</b> · ${esc(phone)}`,
  `${esc(c.tipo_negocio || d.tipo_negocio || 'Negocio sin dato')} · ${esc(c.ciudad || d.ciudad || 'Ciudad sin dato')}`, `Etapa: ${esc(back.etapa_label || LABEL[etapa] || etapa || '—')}`];
if (j.aviso === 'demo' && j.outbound.demo) lines.push(`Cita: ${esc(j.outbound.demo.inicio)}${j.outbound.demo.enlace ? `\nMeet: ${esc(j.outbound.demo.enlace)}` : ''}`);
if (j.aviso === 'persona') lines.push(`Necesita: ${esc((j.respuesta && j.respuesta.resumen) || 'hablar con una persona')}\nSi le vas a escribir tú, pausa Nexa en la consola.`);
if (j.aviso === 'error') lines.push(esc(j.error_text || 'Error sin detalle'));
return [{ json: { msg: lines.join('\n'), url: c.console_url || 'https://clonexa-backend-production.up.railway.app/admin-v2plus' } }];
"""

RESUMEN_MSG = r"""
const d = $input.first().json || {};
const esc = (s) => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const LABEL = { nuevo: 'Nuevo', calificado: 'Calificado', demo_agendada: 'Demo agendada', pidio_persona: 'Pidió persona', no_interesado: 'No interesado', baja: 'Baja' };
if (!d.ok) return [{ json: { msg: `⚠️ <b>Nexa WhatsApp</b>: no pude leer el resumen del día (${esc((d.error && d.error.message) || 'sin respuesta')}).`,
  url: 'https://clonexa-backend-production.up.railway.app/admin-v2plus' } }];
const lines = [`📊 <b>Nexa WhatsApp · resumen de hoy</b> (${esc(d.fecha)})`, `Conversaciones nuevas: <b>${d.nuevas}</b>`, `Calificadas: <b>${d.calificadas}</b>`,
  `Demos agendadas: <b>${d.demos}</b>`, `Pidieron persona: <b>${d.personas}</b>`];
const list = (d.contactos || []).slice(0, 8).map((c) => `• ${esc(c.nombre || 'Sin nombre')} · +${esc(c.wa_id)} · ${esc(c.tipo_negocio || '—')} · ${esc(c.ciudad || '—')} · ${esc(LABEL[c.etapa] || c.etapa)}`);
if (list.length) lines.push('', ...list);
else lines.push('', 'Hoy nadie escribió.');
return [{ json: { msg: lines.join('\n'), url: 'https://clonexa-backend-production.up.railway.app/admin-v2plus#nexa' } }];
"""


# ---------------------------------------------------------------- nodos
def _id(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"nexa-wa-ventas/{name}"))


def code(name: str, js: str, pos) -> dict:
    return {"id": _id(name), "name": name, "type": "n8n-nodes-base.code", "typeVersion": 2, "position": pos,
            "parameters": {"mode": "runOnceForAllItems", "jsCode": js.strip() + "\n"}}


def iff(name: str, expr: str, pos) -> dict:
    return {"id": _id(name), "name": name, "type": "n8n-nodes-base.if", "typeVersion": 2, "position": pos,
            "parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                                          "conditions": [{"id": _id(name + "/c"), "leftValue": "={{ " + expr + " }}", "rightValue": "",
                                                          "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                                          "combinator": "and"}, "options": {}}}


def http(name: str, pos, *, method: str, url: str, body: str | None, cred: str, timeout: int = 20000, headers=None) -> dict:
    p: dict = {"method": method, "url": url, "options": {"timeout": timeout}}
    if cred == "anthropic":
        p.update({"authentication": "predefinedCredentialType", "nodeCredentialType": "anthropicApi"})
        creds = CREDS["anthropic"]
    elif cred == "calendar":
        p.update({"authentication": "predefinedCredentialType", "nodeCredentialType": "googleCalendarOAuth2Api"})
        creds = CREDS["calendar"]
    else:  # "wa" o "fwd": Header Auth propia de este flujo
        p.update({"authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth"})
        creds = {"httpHeaderAuth": f"__{cred.upper()}_CRED__"}
    if headers:
        p.update({"sendHeaders": True, "headerParameters": {"parameters": [{"name": k, "value": v} for k, v in headers.items()]}})
    if body is not None:
        p.update({"sendBody": True, "specifyBody": "json", "jsonBody": body})
    return {"id": _id(name), "name": name, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": pos, "parameters": p,
            "credentials": creds, "retryOnFail": True, "maxTries": 2, "waitBetweenTries": 1000, "onError": "continueRegularOutput"}


def telegram(name: str, pos) -> dict:
    return {"id": _id(name), "name": name, "type": "n8n-nodes-base.telegram", "typeVersion": 1.2, "position": pos, "webhookId": _id(name + "/wh"),
            "credentials": CREDS["telegram"], "onError": "continueRegularOutput",
            "parameters": {"chatId": CHAT_ID, "text": "={{ $json.msg }}", "replyMarkup": "inlineKeyboard",
                           "inlineKeyboard": {"rows": [{"row": {"buttons": [{"text": "Abrir en la consola", "additionalFields": {"url": "={{ $json.url }}"}}]}}]},
                           "additionalFields": {"appendAttribution": False, "parse_mode": "HTML"}}}


def build() -> dict:
    preparar = (PREPARAR.replace("__MODEL__", json.dumps(MODEL)).replace("__SCHEMA__", json.dumps(SCHEMA, ensure_ascii=False))
                .replace("__SYSTEM__", json.dumps(SYSTEM, ensure_ascii=False)))
    nodes = [
        {"id": _id("Del backend"), "name": "Del backend", "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [0, 300],
         "webhookId": "6f0c8a52-7d1e-4f0b-9a57-6e1f2d0c9a11", "credentials": {"httpHeaderAuth": "__FWD_CRED__"},
         "parameters": {"httpMethod": "POST", "path": "nexa-wa-ventas", "authentication": "headerAuth", "responseMode": "onReceived", "options": {}}},
        code("Preparar", preparar, [220, 300]),
        iff("¿Eligió horario?", "$json.ruta === 'cita'", [440, 300]),
        http("Calendar: ¿sigue libre?", [660, 100], method="POST", url="https://www.googleapis.com/calendar/v3/freeBusy", body="={{ $json.fb_body }}", cred="calendar"),
        code("Revisar horario", REVISAR, [880, 100]),
        iff("¿Libre?", "$json.libre === true", [1100, 100]),
        http("Calendar: crear cita", [1320, 0], method="POST",
             url="https://www.googleapis.com/calendar/v3/calendars/primary/events?conferenceDataVersion=1&sendUpdates=all", body="={{ $json.ev_body }}", cred="calendar"),
        code("Confirmar cita", CONFIRMAR, [1540, 0]),
        http("Calendar: otros horarios", [1320, 200], method="POST", url="https://www.googleapis.com/calendar/v3/freeBusy", body="={{ $json.fb_body }}", cred="calendar"),
        code("Proponer otros horarios", PROPONER.replace("__PREV__", "Revisar horario"), [1540, 200]),
        iff("¿Usa Claude?", "$json.ruta === 'claude'", [660, 420]),
        http("Claude", [880, 360], method="POST", url="https://api.anthropic.com/v1/messages", body="={{ $json.claude_body }}", cred="anthropic", timeout=45000,
             headers={"anthropic-version": "2023-06-01"}),
        code("Leer Claude", LEER_CLAUDE, [1100, 360]),
        iff("¿Ofrecer horarios?", "$json.ofrecer === true", [1320, 360]),
        http("Calendar: horarios", [1540, 300], method="POST", url="https://www.googleapis.com/calendar/v3/freeBusy", body="={{ $json.fb_body }}", cred="calendar"),
        code("Proponer horarios", PROPONER.replace("__PREV__", "Leer Claude"), [1760, 300]),
        code("Armar envío", ARMAR, [1980, 300]),
        http("Enviar a WhatsApp", [2200, 300], method="POST", url=GRAPH, body="={{ $json.graph }}", cred="wa", timeout=15000),
        code("Juntar envío", JUNTAR, [2420, 300]),
        http("Registrar en backend", [2640, 300], method="POST", url=f"{BACKEND}/api/v1/nexa-wa/outbound", body="={{ $json.outbound }}", cred="fwd", timeout=15000),
        iff("¿Avisar?", "!!$('Juntar envío').first().json.aviso", [2860, 300]),
        code("Mensaje Telegram", TELEGRAM_MSG, [3080, 240]),
        telegram("Avisar a Telegram", [3300, 240]),
        {"id": _id("Cada día 6 p. m."), "name": "Cada día 6 p. m.", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [0, 700],
         "parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "0 18 * * *"}]}}},
        http("Resumen del backend", [220, 700], method="GET", url=f"{BACKEND}/api/v1/nexa-wa/daily-summary", body=None, cred="fwd"),
        code("Mensaje resumen", RESUMEN_MSG, [440, 700]),
        telegram("Resumen a Telegram", [660, 700]),
    ]
    # Respuesta fija (audio, foto...) va directo a "Armar envío".
    link = lambda *targets: {"main": [[{"node": t, "type": "main", "index": 0} for t in group] for group in targets]}  # noqa: E731
    connections = {
        "Del backend": link(["Preparar"]),
        "Preparar": link(["¿Eligió horario?"]),
        "¿Eligió horario?": link(["Calendar: ¿sigue libre?"], ["¿Usa Claude?"]),
        "Calendar: ¿sigue libre?": link(["Revisar horario"]),
        "Revisar horario": link(["¿Libre?"]),
        "¿Libre?": link(["Calendar: crear cita"], ["Calendar: otros horarios"]),
        "Calendar: crear cita": link(["Confirmar cita"]),
        "Confirmar cita": link(["Armar envío"]),
        "Calendar: otros horarios": link(["Proponer otros horarios"]),
        "Proponer otros horarios": link(["Armar envío"]),
        "¿Usa Claude?": link(["Claude"], ["Armar envío"]),
        "Claude": link(["Leer Claude"]),
        "Leer Claude": link(["¿Ofrecer horarios?"]),
        "¿Ofrecer horarios?": link(["Calendar: horarios"], ["Armar envío"]),
        "Calendar: horarios": link(["Proponer horarios"]),
        "Proponer horarios": link(["Armar envío"]),
        "Armar envío": link(["Enviar a WhatsApp"]),
        "Enviar a WhatsApp": link(["Juntar envío"]),
        "Juntar envío": link(["Registrar en backend"]),
        "Registrar en backend": link(["¿Avisar?"]),
        "¿Avisar?": link(["Mensaje Telegram"], []),
        "Mensaje Telegram": link(["Avisar a Telegram"]),
        "Cada día 6 p. m.": link(["Resumen del backend"]),
        "Resumen del backend": link(["Mensaje resumen"]),
        "Mensaje resumen": link(["Resumen a Telegram"]),
    }
    return {"name": NAME, "nodes": nodes, "connections": connections,
            "settings": {"timezone": "America/Bogota", "executionOrder": "v1"}}


# ---------------------------------------------------------------- despliegue
def secret(name: str, pattern: str) -> str:
    value = (REFS / name).read_text(encoding="utf-8-sig").strip()
    if not re.fullmatch(pattern, value):
        sys.exit(f"{name} no tiene el valor esperado (no se muestra el contenido).")
    return value


def call(key: str, method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(N8N + path, data=data, method=method,
                                 headers={"X-N8N-API-KEY": key, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        sys.exit(f"n8n {method} {path} -> {e.code}: {e.read().decode()[:400]}")


def credential(key: str, name: str, header: str, value: str) -> dict:
    """Crea la credencial Header Auth si no existe; si ya existe la reutiliza (la API no deja leer su valor)."""
    existing = [c for c in call(key, "GET", "/credentials?limit=250").get("data", []) if c["name"] == name]
    if existing:
        return {"id": existing[0]["id"], "name": name}
    saved = call(key, "POST", "/credentials", {"name": name, "type": "httpHeaderAuth", "data": {"name": header, "value": value}})
    return {"id": saved["id"], "name": name}


def deploy() -> None:
    key = secret("n8n-key.txt", r"[\w.\-]{40,}")
    wa_token = secret("whatsapp-token.txt", r"[A-Za-z0-9]{100,}")
    fwd = secret("nexa-wa-forward-secret.txt", r"[\w\-]{32,}")
    wa = credential(key, WA_CRED, "Authorization", f"Bearer {wa_token}")
    fw = credential(key, FWD_CRED, "X-Nexa-Forward", fwd)
    flow = json.loads(json.dumps(build()).replace('"__WA_CRED__"', json.dumps(wa)).replace('"__FWD_CRED__"', json.dumps(fw)))
    body = {k: flow[k] for k in ("name", "nodes", "connections", "settings")}
    current = [w for w in call(key, "GET", "/workflows?limit=250").get("data", []) if w["name"] == NAME]
    if current:
        wid = current[0]["id"]
        if current[0].get("active"):
            call(key, "POST", f"/workflows/{wid}/deactivate", {})
        call(key, "PUT", f"/workflows/{wid}", body)
    else:
        wid = call(key, "POST", "/workflows", body)["id"]
    call(key, "POST", f"/workflows/{wid}/activate", {})
    print(f"{NAME}: {wid} activo")


if __name__ == "__main__":
    flow = build()
    OUT.write_text(json.dumps(flow, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"escrito {OUT.name} ({len(flow['nodes'])} nodos)")
    if "--deploy" in sys.argv:
        deploy()
