// Consola v2+ · Radar · Innovación (NEXUS): tablero, lista, informes con costo, temas, generar y escape.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const SRC = readFileSync('app/web/admin_v2plus_radar.js', 'utf8');
const HTML = readFileSync('app/web/admin_v2plus.html', 'utf8');
const SHELL = readFileSync('app/web/admin_v2plus.js', 'utf8');

function load(responder) {
  const calls = [];
  const fetch = async (url, o = {}) => { calls.push(`${o.method || 'GET'} ${url}${o.body ? ' ' + o.body : ''}`); const { status = 200, body = {} } = responder(url, o) || {};
    return { status, ok: status < 300, json: async () => body }; };
  const window = { location: { href: '' } };
  const document = { addEventListener() {} };
  const ctx = vm.createContext({ window, document, fetch, JSON, Object, Array, String, Number, Promise, Error, Date, URLSearchParams, FormData: class {}, encodeURIComponent });
  vm.runInContext(SRC, ctx);
  return { R: window.CxConsoleRadar, S: window.CxConsoleSections.radar, calls, window };
}
const IDEAS = { counts: { nueva: 1, me_interesa: 1, backlog: 0, en_curso: 0, hecha: 0, descartada: 0 }, ideas: [
  { id: 1, titulo: 'Convocatoria <b>MinTIC</b>', resumen: 'r', por_que: 'p', categoria: 'fondos', impacto: 'alto', esfuerzo: 'medio', costo: 'bajo', puntaje: 80, estado: 'nueva',
    fecha_limite: '2026-12-01', fuentes: [{ url: 'https://www.mintic.gov.co/x', titulo: 'MinTIC', fecha: '2026-11-10' }] },
  { id: 2, titulo: 'Malo', estado: 'me_interesa', puntaje: 40, fuentes: [{ url: 'javascript:alert(1)', titulo: 'x' }] }] };

test('tablero por estado con datos reales, escapado y fuente solo http(s)', async () => {
  const { R, S } = load(() => ({ body: IDEAS }));
  const root = { innerHTML: '' };
  S.mount({ root: () => root, active: () => true });
  await new Promise((r) => setTimeout(r, 0));
  const html = root.innerHTML;
  for (const t of ['Radar · Innovación', 'Nuevas', 'Me interesa', 'Backlog', 'En curso', 'Hechas', 'Generar informe ahora', '80', 'cierra 2026-12-01'])
    assert.ok(html.includes(t), t);
  assert.match(html, /Convocatoria &lt;b&gt;MinTIC&lt;\/b&gt;/);
  assert.match(html, /href="https:\/\/www\.mintic\.gov\.co\/x" target="_blank" rel="noopener noreferrer"/);
  assert.doesNotMatch(html, /javascript:/);
  assert.doesNotMatch(html, /\sstyle=/);
  assert.match(html, /Sin ideas aún/, 'columnas vacías');
  assert.match(html, /data-rx-state="1"/);
});

test('sin ideas: "Sin ideas aún" (nada de datos de ejemplo)', () => {
  const { R } = load(() => ({ body: {} }));
  R.model.ideas = []; R.model.counts = {};
  const html = R.board();
  assert.equal((html.match(/Sin ideas aún/g) || []).length, 5);
  for (const sample of ['catálogo de productos en la API', 'Cierra en 12 días', 'Competidor POS lanzó']) assert.ok(!SRC.includes(sample), sample);
});

test('informes con costo y temas editables', () => {
  const { R } = load(() => ({}));
  R.model.informes = { a_pedido_hoy: 1, tope_diario: 3, costo_total_usd: 0.42, informes: [{ id: 3, tipo: 'a_pedido', tema: 'fondos <x>', estado: 'listo', n_ideas: 3, descartadas: 1, busquedas: 7, tokens_in: 30000, tokens_out: 4000, costo_usd: 0.21, created_at: '2026-11-13T14:00:00Z' }] };
  const ih = R.informes();
  assert.match(ih, /US\$0\.21/); assert.match(ih, /1 de 3/); assert.match(ih, /fondos &lt;x&gt;/); assert.match(ih, /US\$0\.42/);
  R.model.temas = [{ id: 1, nombre: 'Fondos', descripcion: 'd', activo: false }];
  const th = R.temas();
  assert.match(th, /is-off/); assert.match(th, /Agregar tema/); assert.match(th, /data-rx-tema="1"/);
  assert.equal(R.ideasUrl({ estado: 'backlog', categoria: 'fondos' }), '/api/v1/radar/admin/ideas?estado=backlog&categoria=fondos');
});

test('la consola tiene Radar · Innovación debajo de Conversaciones Nexa y #radar abre la vista', () => {
  assert.match(HTML, /data-vp-view="nexa">Conversaciones Nexa<\/button>\r?\n\s*<button class="vp-nav-item" type="button" data-vp-view="radar">Radar · Innovación<\/button>/);
  assert.match(HTML, /<script src="\/admin-v2plus-radar\.js"><\/script>/);
  assert.match(SHELL, /radar: "Radar · Innovación"/);
  assert.match(SHELL, /"#radar"\) \{ setView\("radar"\)/);
});
