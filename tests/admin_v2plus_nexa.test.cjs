// Consola v2+ · Conversaciones Nexa: lista (etapas con color, wa.me, nuevas,
// buscador y fechas en la URL), detalle estilo chat de solo lectura (opciones,
// estados de entrega), Pausar / Reanudar, Marcar no interesado, Exportar CSV,
// refresco cada 15 s y la ruta #nexa/{id}. Sin estilos en línea y todo escapado.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/admin_v2plus_nexa.js', 'utf8');
const shell = readFileSync('app/web/admin_v2plus.js', 'utf8');
const html = readFileSync('app/web/admin_v2plus.html', 'utf8');

const NOW = Date.parse('2026-10-28T20:00:00Z'); // 3:00 p. m. en Bogotá
const ID = '7d3b8a6e-1111-4c22-9333-444455556666';

function load(responder = () => ({ status: 200, body: {} })) {
  const calls = [];
  const timers = [];
  const handlers = {};
  const fetch = async (url, options = {}) => {
    calls.push({ url, method: options.method || 'GET', body: options.body });
    const { status, body } = responder(url, options);
    return { status, ok: status >= 200 && status < 300, json: async () => body };
  };
  const ctx = vm.createContext({
    document: { addEventListener: (type, fn) => { handlers[type] = fn; } }, fetch, console, JSON, Math, Number, String, Array, Object, Promise, Date,
    URLSearchParams, encodeURIComponent,
  });
  ctx.window = ctx;
  ctx.window.location = { href: '' };
  ctx.window.setInterval = (fn, ms) => { timers.push({ fn, ms }); return timers.length; };
  ctx.window.clearInterval = () => {};
  ctx.window.setTimeout = (fn) => { fn(); return 1; };
  ctx.window.clearTimeout = () => {};
  vm.runInContext(source, ctx);
  return { N: ctx.window.CxConsoleNexa, section: ctx.window.CxConsoleSections.nexa, calls, timers, handlers };
}

function list() {
  return {
    ok: true, total: 3, nuevas: 1,
    counts: { nuevo: 1, calificado: 1, demo_agendada: 1, pidio_persona: 0, no_interesado: 0, baja: 0 },
    items: [
      { id: ID, wa_id: '573001112233', nombre: 'Ana <b>Gómez</b>', tipo_negocio: 'Bar', ciudad: 'Medellín', etapa: 'calificado', nexa_pausada: false,
        ultimo: '¿Tienen juegos en vivo?', ultimo_at: '2026-10-28T19:40:00Z', nueva: true },
      { id: 'b2', wa_id: '573005556677', nombre: null, tipo_negocio: null, ciudad: null, etapa: 'demo_agendada', nexa_pausada: true,
        ultimo: 'Listo, nos vemos', ultimo_at: '2026-10-27T15:00:00Z', nueva: false },
      { id: 'c3', wa_id: '13468244098', nombre: 'Joe', etapa: 'inventada', ultimo: 'hi', ultimo_at: '2026-09-01T15:00:00Z', nueva: false },
    ],
  };
}

function detail(extra = {}) {
  return {
    ok: true,
    contacto: { id: ID, wa_id: '573001112233', nombre: 'Ana <b>Gómez</b>', idioma: 'es', tipo_negocio: 'Bar', ciudad: 'Medellín', tamano: '12 mesas',
      dolor: 'pedidos <script>', correo: 'ana@bar.co', etapa: 'calificado', nexa_pausada: false, demo_at: '2026-10-29T15:00:00Z',
      demo_link: 'https://meet.google.com/abc-defg-hij', ...extra },
    entregas: { sent: 1, delivered: 1, read: 1, failed: 1 },
    mensajes: [
      { id: 'm1', direccion: 'in', tipo: 'text', texto: 'Hola <img src=x>', opciones: [], estado: null, creado: '2026-10-28T19:30:00Z' },
      { id: 'm2', direccion: 'out', tipo: 'list', texto: '¿Qué tipo de negocio tienes?', opciones: ['Restaurante', 'Bar'], estado: 'read', creado: '2026-10-28T19:30:05Z' },
      { id: 'm3', direccion: 'in', tipo: 'audio', texto: null, opciones: [], estado: null, creado: '2026-10-28T19:31:00Z' },
      { id: 'm4', direccion: 'out', tipo: 'text', texto: 'Por ahora leo texto', opciones: [], estado: 'failed', error: '131047 Re-engagement', creado: '2026-10-28T19:31:02Z' },
    ],
  };
}

test('URL de la lista: etapa, buscador y fechas', () => {
  const { N } = load();
  assert.equal(N.listUrl({}), '/admin-v2/api/nexa-wa/conversations');
  assert.equal(N.listUrl({ stage: 'calificado', q: 'bar & co', desde: '2026-10-01', hasta: '2026-10-28' }),
    '/admin-v2/api/nexa-wa/conversations?stage=calificado&q=bar+%26+co&desde=2026-10-01&hasta=2026-10-28');
  assert.equal(N.api.csvUrl(ID), `/admin-v2/api/nexa-wa/conversations/${ID}/export.csv`);
});

test('hora de Colombia y número legible', () => {
  const { N } = load();
  assert.equal(N.when('2026-10-28T19:40:00Z', NOW), '2:40 p. m.');
  assert.equal(N.when('2026-10-27T15:00:00Z', NOW), 'Ayer 10:00 a. m.');
  assert.equal(N.when('2026-09-01T15:00:00Z', NOW), 'mar 1 sep · 10:00 a. m.');
  assert.equal(N.when('2025-12-31T17:05:00Z', NOW), 'mié 31 dic 2025 · 12:05 p. m.');
  assert.equal(N.when('', NOW), '');
  assert.equal(N.phone('573144798220'), '+57 314 479 8220');
  assert.equal(N.phone('13468244098'), '+13468244098');
});

test('lista: nombre, número con wa.me, negocio, ciudad, etapa con color, último mensaje, hora y nuevas', () => {
  const { N } = load();
  const out = N.listHtml(list(), ID, NOW);
  assert.match(out, /vp-nx-row is-selected is-new[\s\S]*?data-nx-open="7d3b8a6e[^"]*"[\s\S]*?vp-nx-dot[\s\S]*?Ana &lt;b&gt;Gómez&lt;\/b&gt;[\s\S]*?<time class="vp-nx-time">2:40 p\. m\.<\/time>/);
  assert.match(out, /Bar · Medellín/);
  assert.match(out, /<span class="vp-nx-stage is-calificado">Calificado<\/span>/);
  assert.match(out, /href="https:\/\/wa\.me\/573001112233" target="_blank" rel="noopener noreferrer">\+57 300 111 2233</);
  assert.match(out, /¿Tienen juegos en vivo\?/);
  assert.match(out, /\+57 300 555 6677<\/b>[\s\S]*?Sin datos aún[\s\S]*?is-demo_agendada">Demo agendada[\s\S]*?Nexa pausada/, 'sin nombre: el número');
  assert.match(out, /is-nuevo">Nuevo</, 'etapa desconocida cae en Nuevo');
  assert.doesNotMatch(out, /<b>Gómez<\/b>/);
  assert.match(N.listHtml({ total: 0, items: [] }), /Aún no hay conversaciones[\s\S]*\+57 314 479 8220/);
  assert.match(N.listHtml({ total: 4, items: [] }), /Ninguna conversación con estos filtros/);
});

test('chips por etapa con su contador', () => {
  const { N } = load();
  const out = N.chipsHtml(list(), 'calificado');
  assert.deepEqual([...out.matchAll(/data-nx-stage="([a-z_]*)"[^>]*>([^<]+)<b>(\d+)<\/b>/g)].map((m) => [m[1], m[2], m[3]]), [
    ['', 'Todas', '3'], ['nuevo', 'Nuevo', '1'], ['calificado', 'Calificado', '1'], ['demo_agendada', 'Demo agendada', '1'],
    ['pidio_persona', 'Pidió persona', '0'], ['no_interesado', 'No interesado', '0'], ['baja', 'Baja', '0']]);
  assert.match(out, /class="vp-chip is-active" type="button" data-nx-stage="calificado" aria-pressed="true"/);
});

test('detalle: chat de solo lectura, datos detectados, entregas, opciones y botones', () => {
  const { N } = load();
  const out = N.detailHtml(detail(), NOW);
  assert.match(out, /<h3>Ana &lt;b&gt;Gómez&lt;\/b&gt;<\/h3>/);
  assert.match(out, /vp-nx-msg is-in[\s\S]*?Hola &lt;img src=x&gt;/);
  assert.match(out, /vp-nx-msg is-out[\s\S]*?¿Qué tipo de negocio tienes\?[\s\S]*?<span class="vp-nx-opt">Restaurante<\/span><span class="vp-nx-opt">Bar<\/span>[\s\S]*?vp-nx-status is-read" title="Leído">✓✓ Leído/);
  assert.match(out, /<span class="vp-nx-kind">\[audio\]<\/span>/);
  assert.match(out, /vp-nx-status is-failed" title="Fallido: 131047 Re-engagement">⚠ Fallido/);
  assert.match(out, /<span>Qué les cuesta<\/span><b>pedidos &lt;script&gt;<\/b>/);
  assert.match(out, /<span>Idioma<\/span><b>Español<\/b>/);
  assert.match(out, /<span>Demo<\/span><b>jue 29 oct · 10:00 a\. m\. · <a href="https:\/\/meet\.google\.com\/abc-defg-hij"/);
  assert.match(out, /1 enviados · 1 entregados · 1 leídos · <span class="vp-nx-bad">1 fallidos/);
  assert.match(out, /data-nx-pause="1"[^>]*>Pausar Nexa</);
  assert.match(out, /data-nx-noint >Marcar no interesado</);
  assert.match(out, /href="\/admin-v2\/api\/nexa-wa\/conversations\/7d3b8a6e[^"]*\/export\.csv" download>Exportar CSV</);
  assert.doesNotMatch(out, /<textarea|<input/, 'solo lectura: no hay caja para escribir');
  assert.doesNotMatch(out, /style="/);
});

test('detalle: pausada muestra Reanudar; baja o no interesado desactivan el botón; enlaces raros no salen', () => {
  const { N } = load();
  const paused = N.detailHtml(detail({ nexa_pausada: true, etapa: 'baja', demo_link: 'javascript:alert(1)' }), NOW);
  assert.match(paused, /data-nx-pause="0"[^>]*>Reanudar Nexa</);
  assert.match(paused, /data-nx-noint disabled>Marcar no interesado</);
  assert.match(paused, /is-baja">Baja</);
  assert.doesNotMatch(paused, /javascript:/);
  assert.match(N.detailHtml(null), /Elige una conversación/);
});

test('vista completa: nuevas, buscador, fechas y sin estilos en línea', () => {
  const { N } = load();
  N.model.list = list();
  N.model.selected = ID;
  N.model.detail = detail();
  const out = N.view(NOW);
  assert.match(out, /class="vp-nx has-detail" data-nx-root/);
  assert.match(out, /<h2 class="vp-title">Conversaciones Nexa<\/h2>/);
  assert.match(out, /vp-nx-new-count is-on" data-nx-nuevas>1 nueva</);
  assert.match(out, /type="search"[^>]*data-nx-q/);
  assert.match(out, /type="date" value="" data-nx-date="desde"[\s\S]*type="date" value="" data-nx-date="hasta"/);
  assert.doesNotMatch(out, /style="/);
  assert.doesNotMatch(source, /\sstyle="/, 'CSP de v2+');
});

test('montar: carga lista y detalle, se actualiza cada 15 s y Pausar / No interesado llaman al servidor', async () => {
  const { section, calls, timers, handlers, N } = load((url, options) => {
    if (url.includes('/pause')) return { status: 200, body: detail({ nexa_pausada: JSON.parse(options.body).paused }) };
    if (url.includes('/not-interested')) return { status: 200, body: detail({ etapa: 'no_interesado' }) };
    if (url.includes(`/conversations/${ID}`)) return { status: 200, body: detail() };
    return { status: 200, body: list() };
  });
  const root = { innerHTML: '', querySelector: () => null };
  section.mount({ root: () => root, active: () => true, params: { contact: ID }, toast() {} });
  await new Promise((r) => setTimeout(r, 0));
  assert.deepEqual(calls.map((c) => `${c.method} ${c.url}`), ['GET /admin-v2/api/nexa-wa/conversations', `GET /admin-v2/api/nexa-wa/conversations/${ID}`]);
  assert.equal(timers.length, 1);
  assert.equal(timers[0].ms, 15000, 'cada 15 s');
  await timers[0].fn();
  assert.equal(calls.length, 4, 'el refresco pide lista y detalle otra vez');

  const el = (attr, value) => ({ closest: (sel) => (sel === `[${attr}]` ? { getAttribute: () => value } : null) });
  handlers.click({ target: el('data-nx-pause', '1') });
  await new Promise((r) => setTimeout(r, 0));
  const pause = calls.find((c) => c.url.endsWith('/pause'));
  assert.equal(pause.method, 'POST');
  assert.deepEqual(JSON.parse(pause.body), { paused: true });
  assert.equal(N.model.detail.contacto.nexa_pausada, true);
  await new Promise((r) => setTimeout(r, 0));
  handlers.click({ target: el('data-nx-noint', '') });
  await new Promise((r) => setTimeout(r, 0));
  assert.ok(calls.some((c) => c.method === 'POST' && c.url.endsWith('/not-interested')));
});

test('fuera de la vista no se refresca ni atiende clics', async () => {
  const { section, calls, timers, handlers } = load(() => ({ status: 200, body: list() }));
  let active = true;
  section.mount({ root: () => ({ innerHTML: '', querySelector: () => null }), active: () => active, params: {} });
  await new Promise((r) => setTimeout(r, 0));
  const before = calls.length;
  active = false;
  await timers[0].fn();
  handlers.click({ target: { closest: () => ({ getAttribute: () => 'x' }) } });
  assert.equal(calls.length, before);
});

test('consola: menú, script y ruta #nexa/{id} de los avisos de Telegram', () => {
  assert.match(html, /data-vp-view="landing">Landing<\/button>\s*<button class="vp-nav-item" type="button" data-vp-view="nexa">Conversaciones Nexa<\/button>/);
  assert.match(html, /<script src="\/admin-v2plus-nexa\.js"><\/script>/);
  const ctx = vm.createContext({ window: {}, document: {}, Date, Math, Number, String, Array, encodeURIComponent });
  vm.runInContext(shell, ctx);
  const plus = ctx.window.CxConsolePlus;
  assert.equal(plus.VIEWS.nexa, 'Conversaciones Nexa');
  assert.equal(plus.nexaFromHash(`#nexa/${ID}`), ID);
  assert.equal(plus.nexaFromHash('#nexa/../../x'), '');
  assert.equal(plus.nexaFromHash(`#empresa/${ID}`), '');
});
