// 064A: Board de gerencia (reports_board): la fixture es la salida REAL del servidor
// (tests/fixtures/make_reports_board_fixture.py). Búsqueda, filtros, chips en vivo, línea de
// tiempo, exportes y el modal de perímetros de Administrar lugares.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const SRC = readFileSync('app/web/reports_board.js', 'utf8');
const CSS = readFileSync('app/web/reports_board.css', 'utf8');
const WF = readFileSync('app/web/workforce_v2.js', 'utf8');
const CLIENT = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');
const FIX = JSON.parse(readFileSync('tests/fixtures/reports_board_caso.json', 'utf8'));
const clone = (v) => JSON.parse(JSON.stringify(v));

function load(store = {}, fetchImpl) {
  const localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
  const listeners = {};
  const window = { addEventListener() {} };
  const document = { addEventListener: (t, f) => { listeners[t] = f; }, createElement: () => ({ style: {}, remove() {} }), hidden: false };
  vm.runInNewContext(SRC, { window, document, console, Intl, Date, setTimeout, clearTimeout, setInterval: () => 1, clearInterval() {}, localStorage, URLSearchParams, fetch: fetchImpl, URL });
  return { B: window.CxReportsBoard, listeners };
}

function screen(extra = {}) {
  const { B } = load();
  Object.assign(B.model, { data: clone(FIX), preset: 'week', anchor: '2026-11-05', query: '', op: 'all', status: '', sort: 'az', open: '', loading: false, error: '', denied: false, notesShown: {}, alertsAll: {} }, extra);
  B._ctx({ companyId: 'c1', apiBase: '/api/v1', token: () => 't', host: () => null, back() {} });
  return B;
}
const names = (B, op) => B.visiblePeople(B.model.data.operations.find((o) => o.name === op), B.model).map((p) => p.name);

test('dos bloques y tablas A-Z por operación; Sin lugar asignado solo si hay', () => {
  const B = screen();
  const html = B.view();
  for (const s of ['Board de gerencia', 'En turno ahora', 'En pausa ahora', 'Sin turno hoy', 'Horas en turno', 'Fuera de perímetro', 'Por confirmar', 'Notas del periodo', 'Descargar PDF', 'CSV marcaciones', 'CSV notas',
    'aria-label="Tabla Virginia"', 'aria-label="Tabla Alabama"', 'aria-label="Tabla Sin lugar asignado"', 'Horas por día', 'Notas de cierre', 'Perímetro sin configurar', 'Supervisor: Sofía Mora', 'Sin supervisor']) assert.ok(html.includes(s), s);
  assert.deepEqual(names(B, 'Virginia'), ['Ángela Núñez', 'Bruno Díaz', 'Carla Peña', 'Diego Ruiz', 'Sofía Mora']);
  assert.doesNotMatch(html, /\$|Bruto|Neto|Tarifa|Semana laboral por persona/);
  const noPlace = clone(FIX);
  noPlace.operations = noPlace.operations.filter((o) => o.key !== 'none');
  assert.doesNotMatch(screen({ data: noPlace }).view(), /Sin lugar asignado/);
});

test('chip en vivo: trabajando, en pausa, sin turno, por confirmar y terminó', () => {
  const B = screen();
  const person = (name) => B.model.data.operations.flatMap((o) => o.people).find((p) => p.name === name);
  assert.equal(B.chipOf(person('Bruno Díaz').now).text, 'Trabajando 4 h 40');
  assert.equal(B.chipOf(person('Carla Peña').now).text, 'En pausa 0 h 20');
  assert.equal(B.chipOf(person('Sofía Mora').now).text, 'Sin turno hoy');
  assert.equal(B.chipOf(person('Gabriel Luna').now).text, 'Por confirmar');
  assert.equal(B.chipOf({ state: 'done', end: { t: '16:25', a: 'ET' } }).text, 'Terminó 16:25 ET');
});

test('el estado en vivo cambia chips y cifras sin tocar las horas', () => {
  const B = screen();
  const before = B.model.data.figures;
  B.applyLive({ people: { 'id-diego': { state: 'working', minutes: 12 }, 'id-bruno': { state: 'no_shift' } }, clocks: { 'id-va': { local_time: '09:09' } } });
  const op = B.model.data.operations.find((o) => o.name === 'Virginia');
  assert.equal(op.local_time, '09:09');
  assert.equal(op.people.find((p) => p.id === 'id-diego').now.minutes, 12);
  assert.equal(B.model.data.figures.working, before.working, 'uno entra y otro sale');
  assert.equal(B.model.data.figures.connected, before.connected);
  assert.equal(B.model.data.figures.to_confirm, before.to_confirm);
});

test('búsqueda con y sin tilde, por documento y por texto de nota; N de M', () => {
  for (const q of ['angela', 'ÁNGELA', 'núñez', 'nunez']) assert.deepEqual(names(screen({ query: q }), 'Virginia'), ['Ángela Núñez'], q);
  assert.deepEqual(names(screen({ query: 'al-200' }), 'Alabama'), ['Felipe Soto']);
  const B = screen({ query: 'RACK 9' });
  assert.deepEqual(names(B, 'Virginia'), ['Ángela Núñez']);
  assert.deepEqual(names(B, 'Alabama'), []);
  assert.deepEqual(JSON.parse(JSON.stringify(B.countOf())), { shown: 1, total: 11 });
  const results = B.results();
  assert.ok(results.includes('<mark>rack 9</mark>'), 'resalta en la nota');
  assert.match(results, /rb-hit/);
  assert.equal(B.highlight('<b>Peñá</b>', 'pena'), '&lt;b&gt;<mark>Peñá</mark>&lt;/b&gt;', 'escapa y resalta sin tildes');
});

test('filtros: operación, en turno, en pausa, con alertas; orden y preferencias', async () => {
  let B = screen({ op: 'none' });
  assert.equal(B.countOf().shown, 1);
  B = screen({ status: 'working' });
  assert.equal(B.countOf().shown, 1);
  B = screen({ status: 'on_break' });
  assert.equal(B.countOf().shown, 1);
  B = screen({ status: 'alerts' });
  assert.ok(names(B, 'Alabama').includes('Elena Gómez') && !names(B, 'Virginia').includes('Sofía Mora'));
  B = screen({ sort: 'hours' });
  assert.equal(names(B, 'Alabama')[0], 'Felipe Soto');
  B = screen({ sort: 'last' });
  assert.equal(names(B, 'Virginia')[0], 'Carla Peña');
  // Recuerda la última elección; localStorage dañado no rompe.
  const store = { 'cx_rb_064a:c1': JSON.stringify({ op: 'id-al', status: 'alerts', sort: 'hours' }) };
  const data = clone(FIX);
  const { B: B2 } = load(store, async () => ({ ok: true, status: 200, json: async () => data }));
  await B2.mount({ companyId: 'c1', apiBase: '/api/v1', token: () => '', host: () => null, back() {} });
  assert.equal(B2.model.op, 'id-al');
  assert.equal(B2.model.sort, 'hours');
  const { B: B3 } = load({ 'cx_rb_064a:c1': '{no' }, async () => ({ ok: true, status: 200, json: async () => data }));
  await B3.mount({ companyId: 'c1', apiBase: '/api/v1', token: () => '', host: () => null, back() {} });
  assert.equal(B3.model.sort, 'az');
});

test('periodo: semana laboral (domingo), mes, hoy y personalizado', () => {
  const { B } = load();
  assert.deepEqual({ ...B.rangeOf('week', '2026-11-05', 'sunday') }, { from: '2026-11-01', to: '2026-11-07' });
  assert.deepEqual({ ...B.rangeOf('week', '2026-11-05', 'monday') }, { from: '2026-11-02', to: '2026-11-08' });
  assert.deepEqual({ ...B.rangeOf('month', '2026-02-05') }, { from: '2026-02-01', to: '2026-02-28' });
  assert.deepEqual({ ...B.rangeOf('today', '2026-11-05') }, { from: '2026-11-05', to: '2026-11-05' });
  assert.deepEqual({ ...B.rangeOf('custom', '2026-11-05', 'sunday', { from: '2026-10-01', to: '2026-10-09' }) }, { from: '2026-10-01', to: '2026-10-09' });
});

test('línea de tiempo: pausas, chips, mapa, materiales, nota, cierre por supervisor y totales', () => {
  let html = screen({ open: 'id-angela' }).results();
  for (const s of ['Entrada', '06:45 ET', 'Pausa', 'Retomar', '54 min', 'Salida', '16:25 ET', 'En perímetro · Bodega', 'google.com/maps?q=', 'Pedidos de material', 'Cable 6 AWG', '11:40 ET', 'Resumen de la jornada', 'Etiquetado del rack 9', '9 h 40', '0 h 54', '8 h 46']) assert.ok(html.includes(s), s);
  html = screen({ open: 'id-ivan' }).results();
  for (const s of ['Cerrado por Sofía Mora', 'Hora puesta', '17:00 CT', 'Olvidó marcar la salida', 'Sin ubicación']) assert.ok(html.includes(s), s);
  html = screen({ open: 'id-diego' }).results();
  assert.ok(html.includes('Fuera de perímetro'), 'marca fuera');
  html = screen({ open: 'id-bruno' }).results();
  assert.ok(html.includes('Turno en curso'), 'turno abierto');
  html = screen({ open: 'id-helena' }).results();
  assert.ok(html.includes('Por confirmar: no suma horas'), 'por confirmar');
});

test('alertas: nombre y hora; fuera de perímetro en rojo en la tabla; Ver más en notas', () => {
  const B = screen();
  const html = B.results();
  assert.ok(html.includes('Cerca de overtime') && html.includes('Sin ubicación') && html.includes('Turno abierto de 15 h 00'));
  assert.match(html, /is-danger" data-l="Fuera de perímetro">1</);
  const data = clone(FIX);
  const va = data.operations[0];
  va.notes = Array.from({ length: 12 }, (_, i) => ({ ...va.notes[0], text: `Nota ${i}` }));
  const many = screen({ data }).results();
  assert.ok(many.includes('Nota 4') && !many.includes('Nota 5') && many.includes('Ver más'));
  assert.ok(screen({ data, notesShown: { [va.key]: 15 } }).results().includes('Nota 11'));
});

test('supervisor sin lugar: aviso; limitado: sin chips de operación', () => {
  const data = clone(FIX);
  data.scope = { limited: false, supervisor_no_place: true };
  assert.match(screen({ data }).view(), /no tiene lugar de trabajo/);
  const one = clone(FIX);
  one.scope = { limited: true, supervisor_no_place: false };
  one.operations = one.operations.slice(0, 1);
  assert.doesNotMatch(screen({ data: one }).view(), /data-rb-op=/);
  assert.match(screen().view(), /data-rb-op="all"[^>]*>Ambas|Todas/);
});

test('CSS sin colores fijos; client.js solo entra con el interruptor y Reportes sigue igual sin él', () => {
  assert.doesNotMatch(CSS.replace(/\/\*[\s\S]*?\*\//g, ''), /#[0-9a-fA-F]{3,8}\b|rgb\(/);
  assert.match(CLIENT, /settings\.reports_board === true/);
  assert.match(CLIENT, /async function cxReportsV2Try053C\(\) \{\n    if \(await cxReportsBoardTry064A\(\)\) return true;/);
  assert.match(CLIENT, /reports_board\.js\?v=067A/);
});

// ---------------------------------------------------------------- Administrar lugares
const tick = () => new Promise((r) => setTimeout(r, 0));
async function settle() { for (let i = 0; i < 10; i += 1) await tick(); }
function wf({ on = true } = {}) {
  const window = {};
  const listeners = {};
  const document = { addEventListener: (t, f) => { listeners[t] = f; }, activeElement: null, createElement: () => ({ style: {}, remove() {} }) };
  vm.runInNewContext(WF, { window, document, Blob: function Blob() {}, URL: {}, getComputedStyle: undefined, console });
  const host = { innerHTML: '', querySelector: () => null, contains: () => true };
  const calls = [];
  const places = { places: [{ id: 'va', name: 'Virginia', perimeters: [], supervisors: [] }], employees: [{ id: 'e1', name: 'Sofía', role: 'supervisor' }], default_radius_m: 300, near_ot_hours: 36 };
  const authApi = async (path, opts = {}) => {
    calls.push({ path, ...opts });
    if (path.endsWith('/places')) return places;
    if (path.endsWith('/suggest')) return { days: 7, saved: false, suggestion: { latitude: 38.9, longitude: -77, marks: 5, p90_m: 120 } };
    if (path.endsWith('/recalculate')) return { updated: 4, inside: 3, outside: 1, no_location: 2 };
    if (opts.method === 'PUT' && path.includes('/places/')) { const b = JSON.parse(opts.body); return { perimeters: b.perimeters, supervisors: b.supervisors.map((id) => ({ employee_id: id })) }; }
    if (opts.method === 'PUT') return {};
    return { locations: [{ id: 'va', name: 'Virginia', code: 'VA', timezone: 'America/New_York', is_active: true }], assignments: {}, can_manage: true, can_assign: true, perimeters_on: on };
  };
  return { W: window.CxWorkforceV2, listeners, host, calls, authApi };
}
function target(attrs, extra = {}) {
  const el = { getAttribute: (a) => (a in attrs ? attrs[a] : null), matches: (sel) => { const m = String(sel).match(/^\[([\w-]+)\]$/); return !!(m && m[1] in attrs); }, closest: (sel) => { const m = String(sel).match(/^\[([\w-]+)\]$/); return m && m[1] in attrs ? el : null; }, ...extra };
  return el;
}

test('perímetros: sugerir no guarda; usar solo llena el formulario; Guardar y Recalcular', async () => {
  const { W, listeners, host, calls, authApi } = wf();
  await W.mount({ companyId: 'c1', host: () => host, roles: () => [], configured: () => true, workLocations: true, personalApi: async () => [], authApi });
  await settle();
  listeners.click({ target: target({ 'data-wf2-places': '' }) });
  assert.match(host.innerHTML, /data-wf2-geo="va"/);
  listeners.click({ target: target({ 'data-wf2-geo': 'va' }) });
  await settle();
  assert.match(host.innerHTML, /Virginia: perímetros y supervisores/);
  assert.match(host.innerHTML, /Este lugar aún no tiene perímetro/);
  assert.match(host.innerHTML, /data-wf2-geo-recalc disabled/, 'sin perímetro guardado no hay recálculo');

  listeners.click({ target: target({ 'data-wf2-geo-suggest': '' }) });
  await settle();
  assert.match(host.innerHTML, /Sugerencia \(sin guardar\)/);
  assert.equal(calls.filter((c) => c.method === 'PUT').length, 0, 'la sugerencia no guarda nada');
  listeners.click({ target: target({ 'data-wf2-geo-use': '' }) });
  await settle();
  assert.equal(W.model.modal.rows[0].latitude, 38.9);
  assert.equal(W.model.modal.rows[0].radius_m, 300, 'radio por defecto');
  assert.equal(calls.filter((c) => c.method === 'PUT').length, 0, 'usarla tampoco: falta confirmar');

  W.model.modal.supervisors.push('e1');
  listeners.submit({ preventDefault() {}, target: target({ 'data-wf2-geoform': '' }) });
  await settle();
  const put = calls.find((c) => c.method === 'PUT' && c.path.includes('/places/va'));
  assert.deepEqual(JSON.parse(put.body).supervisors, ['e1']);
  assert.equal(JSON.parse(put.body).perimeters[0].longitude, -77);
  assert.ok(calls.some((c) => c.path.endsWith('/settings')), 'guarda la alerta de overtime');
  assert.match(host.innerHTML, /Guardado/);

  listeners.click({ target: target({ 'data-wf2-geo-recalc': '' }) });
  await settle();
  assert.ok(calls.some((c) => c.path.endsWith('/recalculate') && c.method === 'POST'));
  assert.match(host.innerHTML, /3 en perímetro, 1 fuera, 2 sin ubicación\. Las horas no cambian/);
});

test('Administrar lugares sin reports_board: sin perímetros', async () => {
  const { W, listeners, host, calls, authApi } = wf({ on: false });
  await W.mount({ companyId: 'c1', host: () => host, roles: () => [], configured: () => true, workLocations: true, personalApi: async () => [], authApi });
  await settle();
  listeners.click({ target: target({ 'data-wf2-places': '' }) });
  assert.doesNotMatch(host.innerHTML, /data-wf2-geo=|Perímetros y supervisores/);
  assert.ok(calls.every((c) => !c.path.includes('reports-board')));
});

test('066A: turno del ajuste masivo: chip Ajustado y "Ajuste manual" en vez del perímetro', () => {
  assert.match(SRC, /adjusted: "Ajuste manual"/);
  assert.match(SRC, /s\.adjusted \? `<span class="rb-flag is-adjusted">\$\{h\(T\("Ajustado"\)\)\}<\/span>` : ""/);
});
