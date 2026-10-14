// Reportes v2 (interruptor reports_v2): pantalla, rangos, textos por t(),
// PDF con la sesión y el enganche de client.js (apagado = pantalla de siempre).
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { readFileSync } = require('node:fs');

const SRC = readFileSync('app/web/reports_v2.js', 'utf8');
const CLIENT = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');
const PAYLOAD = JSON.parse(readFileSync('tests/fixtures/reports_v2_payload.json', 'utf8'));

function load(extra = {}) {
  const window = { ...extra };
  vm.runInContext(SRC, vm.createContext({ window, document: {}, URLSearchParams, JSON, Object, Array, String, Number, Math, Date, Map, Set, Promise, Error, encodeURIComponent }));
  return window.CxReportsV2;
}

test('pantalla: seis cifras del payload, bloques, sin menú lateral, sin CSV ni KPIs', () => {
  const R = load();
  Object.assign(R.model, { data: PAYLOAD, denied: false, loading: false, modal: null });
  global.ctx = null;
  const html = R.view.call(null);
  assert.equal((html.match(/class="rr-fig"/g) || []).length, 6);
  assert.match(html, /<small>En turno ahora<\/small><b>2<\/b><span>de 3 activos<\/span>/);
  assert.match(html, /<small>Horas trabajadas<\/small><b>47 h 00 min<\/b><span>45 h 00 min ordinarias \+ 2 h 00 min extra<\/span>/);
  assert.match(html, /<small>Fuera de perímetro<\/small><b>2<\/b><span>marcaciones<\/span>/);
  assert.match(html, /<small>Material pendiente<\/small><b>2<\/b>/);
  assert.match(html, /<small>Stock bajo<\/small><b>2<\/b><span>1 en cero<\/span>/);
  for (const t of ['Horas por día', 'Alertas', 'Materiales', 'Inventario bajo mínimo', 'Personal', 'Toda la cuadrilla', 'Ver PDF', 'Imprimir', 'Descargar PDF', '← Módulos']) assert.ok(html.includes(t), t);
  assert.doesNotMatch(html, /client-sidebar|CLONEXA|CSV|KPI/i, 'sin menú lateral, sin CSV ni KPIs');
  assert.match(html, /Nicolás Gómez pasó las 40 h 00 min de la semana/, 'alerta con el límite semanal de la empresa (VOLTAGE = 40)');
  assert.match(html, /data-rr-box="requested"[^>]*><small>Solicitadas<\/small><b>3<\/b>/);
  assert.match(html, /<i class="rr-tag is-zero">Cero<\/i>/);
  assert.match(html, /data-rr-person-open="e1"/);
  R.model.modal = { type: 'box', key: 'delivered' };
  assert.match(R.view(), /role="dialog"[\s\S]*MAT-1[\s\S]*Entregada/);
  R.model.modal = { type: 'person', id: 'e1' };
  assert.match(R.view(), /role="dialog"[\s\S]*Nicolás Gómez[\s\S]*9 h 00 min/);
  R.model.denied = true;
  assert.match(R.view(), /Reportes es solo del dueño y del director/);
});

test('rangos en el día de la empresa: Hoy, Esta semana (lunes a hoy), Mes (día 1 a hoy)', () => {
  const R = load();
  assert.deepEqual({ ...R.range('today', '2026-10-15') }, { from: '2026-10-15', to: '2026-10-15' });
  assert.deepEqual({ ...R.range('week', '2026-10-15') }, { from: '2026-10-12', to: '2026-10-15' }, 'jueves 15 -> lunes 12');
  assert.deepEqual({ ...R.range('week', '2026-10-12') }, { from: '2026-10-12', to: '2026-10-12' });
  assert.deepEqual({ ...R.range('week', '2026-10-18') }, { from: '2026-10-12', to: '2026-10-18' }, 'domingo');
  assert.deepEqual({ ...R.range('month', '2026-10-15') }, { from: '2026-10-01', to: '2026-10-15' });
  assert.equal(R.hm(2820), '47 h 00 min'); assert.equal(R.hm(65), '1 h 05 min');
});

test('textos por t() y moneda por el formateador central', () => {
  const calls = [];
  const R = load({ CxI18n: { t: (s, v) => { calls.push(s); return s === 'Reportes' ? 'Reports' : s.replace(/\{(\w+)\}/g, (m, k) => (v && v[k] !== undefined ? v[k] : m)); }, locale: () => 'en-US' },
    CxLocale: { money: (n) => `$${Number(n).toFixed(2)}`, loaded: true } });
  Object.assign(R.model, { data: PAYLOAD, denied: false, modal: null });
  const html = R.view();
  assert.match(html, /<h1 class="client-title">Reports<\/h1>/);
  assert.ok(calls.includes('Toda la cuadrilla') && calls.includes('Horas por día'));
  assert.match(html, /\$812\.50/);
});

test('PDF: ver e imprimir inline, descargar attachment, con la sesión y los filtros', () => {
  assert.match(SRC, /pdfBlob\("inline"\)/); assert.match(SRC, /pdfBlob\("attachment"\)/);
  assert.match(SRC, /export\.pdf\?\$\{query\(\{ disposition \}\)\}`, \{ headers: headers\(\) \}/, 'con Authorization (la pestaña nueva no tendría la sesión)');
  assert.match(SRC, /frame\.contentWindow\.print\(\)/); assert.match(SRC, /catch \(_\) \{ window\.open\(url, "_blank"\); \}/, 'si el navegador bloquea imprimir, abre la pestaña');
  const R = load();
  Object.assign(R.model, { preset: 'today', employeeId: 'e1' });
  assert.match(R.query({ disposition: 'inline' }), /preset=custom&start_date=\d{4}-\d{2}-\d{2}&end_date=\d{4}-\d{2}-\d{2}&disposition=inline&employee_id=e1/);
});

test('client.js: solo el enganche; con el interruptor apagado se pinta la pantalla de siempre', () => {
  assert.match(CLIENT, /async function renderReports\(filters = null, activeTab = "employee_summary"\) \{\n    if \(!filters && await cxReportsV2Try053C\(\)\) return;\n    reportStyles\(\);/);
  assert.match(CLIENT, /row\.settings\.reports_v2 === true/);
  assert.match(CLIENT, /reports_v2\.js\?v=053C/); assert.match(CLIENT, /reports_v2\.css\?v=053C/);
  // La pantalla de siempre solo cambió el logo en texto por el logo nuevo de Clonexa (2026-10).
  assert.match(CLIENT, /<div class="client-logo"><img src="\/assets\/brand\/clonexa-logo-horizontal\.svg\?v=cx26a" alt="CLONEXA"/, 'la pantalla de siempre no cambia (salvo el logo nuevo)');
  const css = readFileSync('app/web/reports_v2.css', 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
  const SEMANTIC = /var\(--cx-(warning|danger),\s*#[0-9a-f]{3,8}\)/gi;
  const rest = css.replace(SEMANTIC, '');
  const bad = (rest.match(/#[0-9a-f]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)/gi) || []).filter((c) => !/^rgba?\(\s*0\s*,\s*0\s*,\s*0/.test(c));
  assert.deepEqual(bad, [], `colores fijos: ${bad.join(', ')}`);
  for (const v of ['--cx-primary', '--cx-secondary', '--cx-text', '--cx-bg']) assert.ok(css.includes(`var(${v})`), v);
});
