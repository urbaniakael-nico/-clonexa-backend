// Flujo de n8n "Nexa - WhatsApp ventas" (ops/n8n/nexa-whatsapp-ventas.json):
// se ejecuta el JavaScript de cada nodo de código con entradas de ejemplo.
// Sin secretos en el JSON, Claude con salida JSON por esquema, horarios libres
// reales (lunes a viernes 9-17 de Colombia, 3 h de anticipación, sin festivos),
// botones y listas dentro de los límites de Meta, cita con Google Meet, respuesta
// fija para audio/foto, "Ya te respondemos en un momento" si Claude falla y
// avisos a Telegram solo en demo, persona y errores.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');

const raw = readFileSync('ops/n8n/nexa-whatsapp-ventas.json', 'utf8');
const flow = JSON.parse(raw);
const node = (name) => flow.nodes.find((n) => n.name === name);

// Corre un nodo de código: $input = items de entrada; $('Nombre') = salida de otro nodo.
function run(name, input, outputs = {}, now) {
  const items = (Array.isArray(input) ? input : [input]).map((json) => ({ json }));
  const $input = { first: () => items[0], all: () => items };
  const $ = (n) => {
    if (!(n in outputs)) throw new Error(`nodo ${n} no ejecutado`);
    const list = (Array.isArray(outputs[n]) ? outputs[n] : [outputs[n]]).map((json) => ({ json }));
    return { first: () => list[0], all: () => list };
  };
  const RealDate = Date;
  if (now) {
    global.Date = class extends RealDate { constructor(...a) { super(...(a.length ? a : [now])); } static now() { return now; } };
  }
  try {
    return new Function('$input', '$', node(name).parameters.jsCode)($input, $);
  } finally { global.Date = RealDate; }
}

const NOW = Date.parse('2026-10-28T14:00:00Z'); // miércoles 9:00 a. m. en Bogotá
const contacto = { id: 'c1', wa_id: '573001112233', nombre: 'Ana', idioma: 'es', tipo_negocio: 'Bar', ciudad: 'Medellín', etapa: 'calificado', correo: '',
  console_url: 'https://clonexa-backend-production.up.railway.app/admin-v2plus#nexa/c1' };
const hook = (mensaje, extra = {}) => ({ body: { mensaje: { respondible: true, tipo: 'text', texto: 'Hola', reply_id: null, ...mensaje }, contacto: { ...contacto, ...(extra.contacto || {}) },
  historial: extra.historial || [{ direccion: 'in', tipo: 'text', texto: mensaje.texto || 'Hola' }], primer_mensaje: !!extra.primer } });

test('el JSON del flujo no lleva secretos: solo marcadores de credenciales', () => {
  assert.doesNotMatch(raw, /EAA[A-Za-z0-9]{20,}|Bearer [A-Za-z0-9]{20,}|sk-ant-|n8n_api_/);
  assert.equal(node('Enviar a WhatsApp').credentials.httpHeaderAuth, '__WA_CRED__');
  assert.equal(node('Del backend').credentials.httpHeaderAuth, '__FWD_CRED__');
  assert.equal(node('Del backend').parameters.authentication, 'headerAuth', 'n8n valida X-Nexa-Forward');
  assert.equal(node('Registrar en backend').credentials.httpHeaderAuth, '__FWD_CRED__');
  assert.deepEqual(node('Claude').credentials, { anthropicApi: { id: 'X6Q45d5OD6gz0wiS', name: 'Anthropic Nexa' } });
  assert.equal(node('Avisar a Telegram').parameters.chatId, '5126243056');
  assert.equal(node('Enviar a WhatsApp').parameters.url, 'https://graph.facebook.com/v26.0/1331771733361816/messages');
  assert.doesNotMatch(raw, /"type": ?"template"/, 'nunca plantillas');
});

test('reintento 1 vez en Claude, Meta, Calendar y backend; resumen diario a las 6 p. m. hora de Colombia', () => {
  for (const n of ['Claude', 'Enviar a WhatsApp', 'Calendar: horarios', 'Calendar: crear cita', 'Registrar en backend']) {
    assert.equal(node(n).retryOnFail, true, n);
    assert.equal(node(n).maxTries, 2, n);
    assert.equal(node(n).onError, 'continueRegularOutput', n);
  }
  assert.equal(flow.settings.timezone, 'America/Bogota');
  assert.equal(node('Cada día 6 p. m.').parameters.rule.interval[0].expression, '0 18 * * *');
});

test('Preparar: texto -> Claude (sonnet 5.5, JSON por esquema, historial user/assistant, contexto)', () => {
  const [out] = run('Preparar', hook({ texto: 'Tengo un bar' }, { primer: true, historial: [
    { direccion: 'out', tipo: 'text', texto: 'mensaje viejo de Nexa' }, { direccion: 'in', tipo: 'text', texto: 'Hola' },
    { direccion: 'in', tipo: 'text', texto: 'Tengo un bar' }, { direccion: 'out', tipo: 'list', texto: '¿Qué negocio?' }, { direccion: 'in', tipo: 'audio', texto: '' }] }), {}, NOW);
  const b = out.json.claude_body;
  assert.equal(out.json.ruta, 'claude');
  assert.equal(b.model, 'claude-sonnet-5-5');
  assert.ok(b.max_tokens >= 1500);
  assert.equal(b.temperature, undefined, 'Sonnet 5.5 rechaza temperature');
  assert.equal(b.output_config.format.type, 'json_schema');
  assert.deepEqual(b.output_config.format.schema.required, ['mensajes', 'datos_detectados', 'etapa', 'accion', 'preferencia_horario', 'resumen']);
  assert.deepEqual(b.messages, [{ role: 'user', content: 'Hola\nTengo un bar' }, { role: 'assistant', content: '¿Qué negocio?' }, { role: 'user', content: '[audio]' }]);
  assert.match(b.system[0].text, /asistente virtual con IA de Clonexa/);
  assert.match(b.system[0].text, /https:\/\/www\.clonexa\.com\.co\/privacidad/);
  assert.match(b.system[0].text, /NUNCA des precios/);
  assert.match(b.system[0].text, /Armamos una cotización a la medida en la demo/);
  assert.match(b.system[0].text, /NO hay grabación de llamadas ni IVR/);
  assert.match(b.system[0].text, /NO hay mapas de ruta/);
  assert.match(b.system[0].text, /DIAN[^.]*próximamente/);
  assert.match(b.system[0].text, /Nicolás/);
  for (const p of ['restaurantes', 'bares', 'talleres-y-fabricas', 'call-centers', 'personal-en-campo', 'que-es-clonexa']) {
    assert.match(b.system[0].text, new RegExp(`clonexa\\.com\\.co/${p}\\?utm_source=whatsapp&utm_medium=nexa`), p);
  }
  for (const o of ['Restaurante', 'Bar', 'Taller o fábrica', 'Tienda o cadena', 'Distribuidora', 'Call center', 'Personal en campo', 'Otro']) assert.ok(b.system[0].text.includes(o), o);
  const ctx = JSON.parse(b.system[1].text.split('\n')[1]);
  assert.equal(ctx.primer_mensaje, true);
  assert.equal(ctx.ahora_colombia, '2026-10-28T09:00:00-05:00');
});

test('Preparar: audio o foto -> respuesta fija (con presentación y datos si es el primero); reacción -> nada', () => {
  const [first] = run('Preparar', hook({ tipo: 'audio', respondible: false, texto: '' }, { primer: true }));
  assert.equal(first.json.ruta, 'fijo');
  assert.match(first.json.respuesta.mensajes[0].texto, /^Hola, soy Nexa, la asistente virtual con IA de Clonexa\. Por ahora solo leo mensajes de texto[\s\S]*privacidad$/);
  assert.equal(first.json.respuesta.consentimiento_visto, true);
  const [later] = run('Preparar', hook({ tipo: 'image', respondible: false, texto: '' }, { contacto: { idioma: 'en' } }));
  assert.match(later.json.respuesta.mensajes[0].texto, /^For now I can only read text messages/);
  assert.deepEqual(run('Preparar', hook({ tipo: 'reaction', respondible: false })), []);
});

test('Preparar: botón de horario -> ruta cita con la consulta a Calendar de esos 30 min', () => {
  const [out] = run('Preparar', hook({ tipo: 'interactive', texto: 'Jue 29 oct 10:00 am', reply_id: 'cita|2026-10-29T10:00:00-05:00' }));
  assert.equal(out.json.ruta, 'cita');
  assert.equal(out.json.slot, Date.parse('2026-10-29T15:00:00Z'));
  assert.deepEqual(out.json.fb_body, { timeMin: '2026-10-29T15:00:00.000Z', timeMax: '2026-10-29T15:30:00.000Z', timeZone: 'America/Bogota', items: [{ id: 'primary' }] });
});

const claude = (d) => ({ content: [{ type: 'text', text: JSON.stringify(d) }], stop_reason: 'end_turn' });
const answer = (extra = {}) => ({ mensajes: [{ tipo: 'text', texto: 'Hola, soy Nexa', opciones: [] }], datos_detectados: { nombre: '', idioma: 'es', tipo_negocio: 'Bar', ciudad: '', tamano: '', dolor: '', correo: '' },
  etapa: 'calificado', accion: 'ninguna', preferencia_horario: { desde: '', franja: '' }, resumen: '', ...extra });

test('Leer Claude: toma el bloque text, pasar a persona avisa; si Claude falla -> "Ya te respondemos en un momento" + aviso', () => {
  const prep = run('Preparar', hook({ texto: 'Hola' }))[0].json;
  const [ok] = run('Leer Claude', claude(answer()), { Preparar: prep });
  assert.deepEqual(ok.json.respuesta.mensajes, [{ tipo: 'text', texto: 'Hola, soy Nexa', opciones: [] }]);
  assert.equal(ok.json.respuesta.etapa, 'calificado');
  assert.equal(ok.json.aviso, '');
  assert.equal(ok.json.ofrecer, false);
  const [p] = run('Leer Claude', claude(answer({ accion: 'pasar_a_persona', etapa: 'calificado', resumen: 'Pregunta por integración con Siigo' })), { Preparar: prep });
  assert.equal(p.json.respuesta.etapa, 'pidio_persona');
  assert.equal(p.json.aviso, 'persona');
  for (const bad of [{ error: { message: 'overloaded' } }, { content: [{ type: 'text', text: 'no es json' }] }, { content: [], stop_reason: 'refusal' }]) {
    const [f] = run('Leer Claude', bad, { Preparar: prep });
    assert.deepEqual(f.json.respuesta.mensajes, [{ tipo: 'text', texto: 'Ya te respondemos en un momento.', opciones: [] }]);
    assert.equal(f.json.aviso, 'error');
    assert.match(f.json.error_text, /Claude no respondió/);
  }
  const [hours] = run('Leer Claude', claude(answer({ accion: 'crear_cita', preferencia_horario: { desde: '2026-10-29T15:00:00-05:00', franja: '' } })), { Preparar: prep });
  assert.equal(hours.json.ofrecer, true, 'una hora escrita se confirma con un botón de horario libre');
});

test('Proponer horarios: 3 libres, lunes a viernes 9-17 de Colombia, 3 h de anticipación, sin festivos ni ocupados, botones de 20 caracteres', () => {
  const prep = run('Preparar', hook({ texto: 'sí, quiero la demo' }))[0].json;
  const leer = run('Leer Claude', claude(answer({ accion: 'ofrecer_horarios', mensajes: [{ tipo: 'text', texto: 'Te propongo estos horarios:', opciones: [] }, { tipo: 'buttons', texto: 'x', opciones: ['inventado'] }] })),
    { Preparar: prep }, NOW)[0].json;
  const busy = { calendars: { primary: { busy: [{ start: '2026-10-28T17:00:00Z', end: '2026-10-28T19:00:00Z' }] } } }; // 12:00-14:00 ocupado
  const [out] = run('Proponer horarios', busy, { 'Leer Claude': leer }, NOW);
  const msgs = out.json.respuesta.mensajes;
  assert.deepEqual(msgs.map((m) => m.tipo), ['text', 'buttons'], 'los botones inventados por Claude se quitan');
  const b = msgs[1];
  assert.deepEqual(b.opciones, ['Mié 28 oct 2:00 pm', 'Jue 29 oct 9:00 am', 'Jue 29 oct 12:00 pm']);
  assert.deepEqual(b.ids, ['cita|2026-10-28T14:00:00-05:00', 'cita|2026-10-29T09:00:00-05:00', 'cita|2026-10-29T12:00:00-05:00']);
  assert.ok(b.opciones.every((o) => o.length <= 20));
  assert.match(b.texto, /30 min por Google Meet, hora de Colombia\)\. Si me dejas tu correo/);

  // Festivo (lunes 2 nov 2026) y fin de semana se saltan; franja de la tarde
  const viernes = Date.parse('2026-10-30T21:00:00Z'); // vie 4:00 p. m.
  const leer2 = { ...leer, pref: { desde: '', franja: 'tarde' } };
  const [late] = run('Proponer horarios', { calendars: { primary: { busy: [] } } }, { 'Leer Claude': leer2 }, viernes);
  assert.deepEqual(late.json.respuesta.mensajes[1].opciones, ['Mar 3 nov 12:00 pm', 'Mar 3 nov 3:00 pm', 'Mié 4 nov 12:00 pm']);

  // Hora pedida por el cliente, libre -> primera opción
  const leer3 = { ...leer, pref: { desde: '2026-10-29T15:30:00-05:00', franja: '' }, contacto: { ...contacto, correo: 'ana@bar.co' } };
  const [asked] = run('Proponer horarios', { calendars: { primary: { busy: [] } } }, { 'Leer Claude': leer3 }, NOW);
  assert.equal(asked.json.respuesta.mensajes[1].ids[0], 'cita|2026-10-29T15:30:00-05:00');
  assert.doesNotMatch(asked.json.respuesta.mensajes[1].texto, /correo/, 'si ya dio el correo no se pide');

  // Calendar caído -> aviso de error y Nicolás cuadra
  const [down] = run('Proponer horarios', { error: { message: 'invalid_grant' } }, { 'Leer Claude': leer }, NOW);
  assert.equal(down.json.aviso, 'error');
  assert.match(down.json.respuesta.mensajes.at(-1).texto, /Nicolás/);
});

test('Cita: libre -> evento con Meet e invitado; ocupado -> otros horarios; confirmación con fecha, hora y enlace', () => {
  const prep = run('Preparar', hook({ tipo: 'interactive', texto: 'Jue 29 oct 10:00 am', reply_id: 'cita|2026-10-29T10:00:00-05:00' }, { contacto: { correo: 'ana@bar.co' } }))[0].json;
  const [free] = run('Revisar horario', { calendars: { primary: { busy: [] } } }, { Preparar: prep }, NOW);
  assert.equal(free.json.libre, true);
  const ev = free.json.ev_body;
  assert.deepEqual(ev.start, { dateTime: '2026-10-29T10:00:00-05:00', timeZone: 'America/Bogota' });
  assert.deepEqual(ev.end, { dateTime: '2026-10-29T10:30:00-05:00', timeZone: 'America/Bogota' });
  assert.deepEqual(ev.attendees, [{ email: 'ana@bar.co' }]);
  assert.equal(ev.conferenceData.createRequest.conferenceSolutionKey.type, 'hangoutsMeet');
  assert.match(ev.description, /admin-v2plus#nexa\/c1/);
  assert.match(node('Calendar: crear cita').parameters.url, /conferenceDataVersion=1&sendUpdates=all/);

  const [taken] = run('Revisar horario', { calendars: { primary: { busy: [{ start: '2026-10-29T15:00:00Z', end: '2026-10-29T16:00:00Z' }] } } }, { Preparar: prep }, NOW);
  assert.equal(taken.json.libre, false);
  assert.match(taken.json.respuesta.mensajes[0].texto, /se acaba de ocupar/);

  const [done] = run('Confirmar cita', { id: 'ev1', hangoutLink: 'https://meet.google.com/abc-defg-hij', htmlLink: 'https://calendar.google.com/x' },
    { Preparar: prep, 'Revisar horario': free.json }, NOW);
  assert.equal(done.json.respuesta.mensajes[0].texto,
    '¡Listo! Tu demo quedó agendada el jueves 29 de octubre a las 10:00 a. m. (hora de Colombia).\nEnlace de Google Meet: https://meet.google.com/abc-defg-hij\nTe llega la invitación a ana@bar.co.');
  assert.equal(done.json.respuesta.etapa, 'demo_agendada');
  assert.deepEqual(done.json.respuesta.demo, { inicio: '2026-10-29T10:00:00-05:00', enlace: 'https://meet.google.com/abc-defg-hij' });
  assert.equal(done.json.aviso, 'demo');
  const [fail] = run('Confirmar cita', { error: { message: 'forbidden' } }, { Preparar: prep, 'Revisar horario': free.json }, NOW);
  assert.equal(fail.json.aviso, 'error');
  assert.equal(fail.json.respuesta.etapa, 'pidio_persona');
});

test('Armar envío: texto, botones (máx. 3, 20 caracteres) y lista (máx. 10, 24 caracteres) para la Cloud API', () => {
  const j = { wa_id: '573001112233', contacto, respuesta: { mensajes: [
    { tipo: 'text', texto: 'Mira https://www.clonexa.com.co/bares', opciones: [] },
    { tipo: 'list', texto: '¿Qué tipo de negocio tienes?', opciones: ['Restaurante', 'Bar', 'Taller o fábrica', 'Tienda o cadena', 'Distribuidora', 'Call center', 'Personal en campo', 'Otro', 'Uno más', 'Dos más', 'Once'] },
    { tipo: 'buttons', texto: 'Elige', opciones: ['Jue 29 oct 10:00 am', 'Una opción demasiado larga para un botón'], ids: ['cita|2026-10-29T10:00:00-05:00'] },
    { tipo: 'text', texto: 'cuarto mensaje: no se manda', opciones: [] }] } };
  const out = run('Armar envío', j).map((x) => x.json);
  assert.equal(out.length, 3, 'máximo 3 mensajes por turno');
  assert.deepEqual(out[0].graph, { messaging_product: 'whatsapp', recipient_type: 'individual', to: '573001112233', type: 'text', text: { body: 'Mira https://www.clonexa.com.co/bares', preview_url: true } });
  const list = out[1].graph.interactive;
  assert.equal(list.type, 'list');
  assert.equal(list.action.button, 'Elegir');
  assert.equal(list.action.sections[0].rows.length, 10);
  assert.deepEqual(list.action.sections[0].rows[2], { id: 'op|3', title: 'Taller o fábrica' });
  const btn = out[2].graph.interactive;
  assert.equal(btn.type, 'button');
  assert.deepEqual(btn.action.buttons.map((b) => b.reply), [{ id: 'cita|2026-10-29T10:00:00-05:00', title: 'Jue 29 oct 10:00 am' }, { id: 'op|2', title: 'Una opción demasiad…' }]);
  assert.ok(btn.action.buttons.every((b) => b.reply.title.length <= 20));
  assert.ok(out[0].src && out[1].src === null, 'el contexto viaja en el primer mensaje');
  const four = run('Armar envío', { ...j, respuesta: { mensajes: [{ tipo: 'buttons', texto: 'x', opciones: ['a', 'b', 'c', 'd'] }, { tipo: 'buttons', texto: 'y', opciones: [] }] } }).map((x) => x.json);
  assert.equal(four[0].graph.interactive.type, 'list', 'más de 3 opciones -> lista');
  assert.equal(four[1].graph.type, 'text', 'sin opciones -> texto');
});

test('Juntar envío: ids de Meta, fallidos y el registro para el backend', () => {
  const src = { wa_id: '573001112233', contacto, aviso: '', error_text: '', respuesta: { etapa: 'calificado', datos_detectados: { ciudad: 'Medellín' }, accion: 'ninguna', consentimiento_visto: true, demo: null, resumen: '' } };
  const armar = [{ i: 0, tipo: 'text', texto: 'Hola', opciones: [], src }, { i: 1, tipo: 'buttons', texto: 'Elige', opciones: ['A'], src: null }];
  const [ok] = run('Juntar envío', [{ messages: [{ id: 'wamid.1' }] }, { messages: [{ id: 'wamid.2' }] }], { 'Armar envío': armar });
  assert.deepEqual(ok.json.outbound.mensajes.map((m) => [m.meta_id, m.estado]), [['wamid.1', 'sent'], ['wamid.2', 'sent']]);
  assert.equal(ok.json.outbound.etapa, 'calificado');
  assert.equal(ok.json.outbound.consentimiento_visto, true);
  assert.equal(ok.json.aviso, '');
  const [bad] = run('Juntar envío', [{ messages: [{ id: 'wamid.1' }] }, { error: { message: '(#131047) Re-engagement message' } }], { 'Armar envío': armar });
  assert.deepEqual(bad.json.outbound.mensajes.map((m) => m.estado), ['sent', 'failed']);
  assert.equal(bad.json.aviso, 'error');
  assert.match(bad.json.error_text, /Meta no envió 1 de 2 mensajes: \(#131047\)/);
  const [none] = run('Juntar envío', [{ error: { message: 'down' } }, { error: { message: 'down' } }], { 'Armar envío': armar });
  assert.equal(none.json.outbound.consentimiento_visto, false, 'si no llegó nada, el aviso de datos no cuenta como visto');
});

test('Telegram: formato corto con nombre, número, negocio, ciudad, etapa y enlace a la consola; resumen diario', () => {
  const juntar = { aviso: 'demo', error_text: '', contacto, respuesta: { datos_detectados: {} }, outbound: { etapa: 'demo_agendada', demo: { inicio: '2026-10-29T10:00:00-05:00', enlace: 'https://meet.google.com/x' } } };
  const [m] = run('Mensaje Telegram', { ok: true, etapa_label: 'Demo agendada', contacto: { ...contacto, nombre: 'Ana <script>' } }, { 'Juntar envío': juntar });
  assert.equal(m.json.msg, '📅 <b>Demo agendada</b>\n<b>Ana &lt;script&gt;</b> · +57 300 111 2233\nBar · Medellín\nEtapa: Demo agendada\nCita: 2026-10-29T10:00:00-05:00\nMeet: https://meet.google.com/x');
  assert.equal(m.json.url, contacto.console_url);
  const [p] = run('Mensaje Telegram', { error: { message: 'backend caído' } }, { 'Juntar envío': { ...juntar, aviso: 'persona', respuesta: { resumen: 'Quiere precios ya' }, outbound: { etapa: 'pidio_persona' } } });
  assert.match(p.json.msg, /^🙋 <b>Pidió una persona<\/b>[\s\S]*Etapa: Pidió persona\nNecesita: Quiere precios ya/);
  assert.equal(node('¿Avisar?').parameters.conditions.conditions[0].leftValue, "={{ !!$('Juntar envío').first().json.aviso }}", 'solo con aviso');
  const [r] = run('Mensaje resumen', { ok: true, fecha: '2026-10-28', nuevas: 3, calificadas: 2, demos: 1, personas: 0, activas: 4,
    contactos: [{ nombre: 'Ana', wa_id: '573001112233', tipo_negocio: 'Bar', ciudad: 'Medellín', etapa: 'demo_agendada' }] });
  assert.equal(r.json.msg, '📊 <b>Nexa WhatsApp · resumen de hoy</b> (2026-10-28)\nConversaciones nuevas: <b>3</b>\nCalificadas: <b>2</b>\nDemos agendadas: <b>1</b>\nPidieron persona: <b>0</b>\n\n• Ana · +573001112233 · Bar · Medellín · Demo agendada');
});

test('conexiones: cada camino termina en Armar envío -> WhatsApp -> backend -> ¿Avisar?', () => {
  const next = (n, i = 0) => ((flow.connections[n] || {}).main || [])[i]?.map((x) => x.node) || [];
  assert.deepEqual(next('¿Eligió horario?', 0), ['Calendar: ¿sigue libre?']);
  assert.deepEqual(next('¿Eligió horario?', 1), ['¿Usa Claude?']);
  assert.deepEqual(next('¿Usa Claude?', 1), ['Armar envío'], 'respuesta fija');
  for (const n of ['Confirmar cita', 'Proponer otros horarios', 'Proponer horarios']) assert.deepEqual(next(n), ['Armar envío'], n);
  assert.deepEqual(next('¿Ofrecer horarios?', 1), ['Armar envío']);
  assert.deepEqual(next('Armar envío'), ['Enviar a WhatsApp']);
  assert.deepEqual(next('Juntar envío'), ['Registrar en backend']);
  assert.deepEqual(next('¿Avisar?', 0), ['Mensaje Telegram']);
});
