// Nómina v2 (interruptor payroll_v2): mini tarjetas, buscador, filtros y
// orden; detalle por turno con solo los datos de su empresa; confirmar salida
// con el flujo de siempre; enganche (apagado = pantalla de siempre); sin CSV;
// colores solo del tema.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const SRC = readFileSync('app/web/payroll_v2.js', 'utf8');
const CSS = readFileSync('app/web/payroll_v2.css', 'utf8');
const CLIENT = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');
const plain = (v) => JSON.parse(JSON.stringify(v));

function load() {
  const window = { addEventListener() {} };
  const document = { addEventListener() {}, activeElement: null, createElement: () => ({ style: {}, remove() {} }) };
  vm.runInNewContext(SRC, { window, document, console, Intl, Date, setTimeout, clearTimeout });
  return window.CxPayrollV2;
}

const at = (d, hm) => new Date(`2026-10-${d}T${hm}:00-05:00`).toISOString();
const SNAP = {
  period: { period_start: '2026-10-01', period_end: '2026-10-15' },
  rows: [
    { employee_id: 'a', employee_name: 'Zoe Ruiz', employee_role: 'Director', regular_minutes: 480, extra_minutes: 0, gross_amount: 100, discount_amount: 0, net_amount: 100, closed_shifts: 1,
      shifts: [{ start: at('05', '07:00'), end: at('05', '15:00'), regular_minutes: 480, extra_minutes: 0, gross_amount: '100', pause_minutes: 30 }] },
    { employee_id: 'b', employee_name: 'Ana Pérez', employee_role: 'Supervisor', regular_minutes: 960, extra_minutes: 60, gross_amount: 300, discount_amount: 10, net_amount: 290, closed_shifts: 2,
      shifts: [{ start: at('06', '07:00'), end: at('06', '16:00'), regular_minutes: 480, extra_minutes: 60, gross_amount: '200', mini_panel_session_id: 's1', pause_minutes: 0 }] },
  ],
  totals: { people: 2, regular_minutes: 1440, extra_minutes: 60, gross_amount: 400, discount_amount: 10, net_amount: 390 },
  unverified_shifts: [{ employee_id: 'c', employee_name: 'Beto Sin Turnos', source: 'attendance', session_ref: 'ci', closure_id: 'cl', start: at('07', '07:00'), end: at('08', '00:00'), minutes: 900 }],
};

test('mini tarjetas: una por colaborador, también quien solo tiene turnos por confirmar', () => {
  const P = load();
  const cards = P.buildCards(SNAP, { documents: { b: '1020' } });
  assert.deepEqual(plain(cards.map((c) => [c.id, c.name, c.net, c.pending.length, c.document])), [
    ['a', 'Zoe Ruiz', 100, 0, ''], ['b', 'Ana Pérez', 290, 0, '1020'], ['c', 'Beto Sin Turnos', 0, 1, '']]);
  assert.equal(P.initials('Óscar Otro (prueba)'), 'ÓO', 'iniciales sin paréntesis');
});

test('buscador por nombre o documento, filtros Todos / Por confirmar y orden por total, tiempo o nombre', () => {
  const P = load();
  const cards = P.buildCards(SNAP, { documents: { b: '1020' } });
  const ids = (f, q, s) => plain(P.visibleCards(cards, f, q, s).map((c) => c.id));
  assert.deepEqual(ids('all', '', 'total'), ['b', 'a', 'c']);
  assert.deepEqual(ids('all', '', 'time'), ['b', 'a', 'c']);
  assert.deepEqual(ids('all', '', 'name'), ['a', 'c', 'b'].sort((x, y) => ({ a: 'Zoe', b: 'Ana', c: 'Beto' })[x].localeCompare(({ a: 'Zoe', b: 'Ana', c: 'Beto' })[y])));
  assert.deepEqual(ids('pending', '', 'total'), ['c']);
  assert.deepEqual(ids('all', 'perez', 'total'), ['b'], 'sin tildes');
  assert.deepEqual(ids('all', '1020', 'total'), ['b'], 'por documento');
});

test('detalle por turno: solo lo de la empresa (sección y pedidos, ubicación o referencias) y solo en el rango del turno', () => {
  const P = load();
  const shift = SNAP.rows[1].shifts[0];
  const panels = { modules: { panels: true, orders: true }, panels: { s1: { panel_type: 'mesero', start: shift.start, end: shift.end, orders_taken: 7, orders_taken_total: 350000 } } };
  const acts = plain(P.activityFor(panels, 'b', shift));
  assert.equal(acts.length, 1);
  assert.match(acts[0].text, /^Mesero · conexión \d\d:\d\d · salida \d\d:\d\d$/);
  assert.equal(acts[0].extra, '7 pedidos tomados ($350.000)');
  const noOrders = plain(P.activityFor({ modules: { panels: true, orders: false }, panels: panels.panels }, 'b', shift));
  assert.equal(noOrders[0].extra, '', 'sin datos por persona: solo la sección');
  const gps = { modules: { gps: true }, gps: { b: [{ at: at('06', '08:00'), lat: 4.6, lng: -74.1, perimeter: 'EDIFICIO 1' }, { at: at('09', '08:00'), lat: 1, lng: 1, perimeter: 'OTRO DIA' }],
    z: [{ at: at('06', '08:00'), lat: 1, lng: 1, perimeter: 'DE OTRA PERSONA' }] } };
  const g = plain(P.activityFor(gps, 'b', shift));
  assert.equal(g[0].text, 'Ubicación: EDIFICIO 1', 'ni otro día ni otra persona');
  assert.equal(g[0].map, 'https://www.google.com/maps?q=4.6%2C-74.1');
  const refs = { modules: { references: true }, references: { b: [{ reference: 'PANT SET', start: at('06', '08:00'), end: at('06', '10:00') }] },
    reference_closures: { b: [{ reference: 'PANT SET', size: '10', quantity: 30, at: at('06', '10:00') }] } };
  const r = plain(P.activityFor(refs, 'b', shift));
  assert.equal(r[0].text, 'Referencias: PANT SET'); assert.match(r[0].extra, /^30 unidades terminadas \(PANT SET talla 10 × 30\)$/);
  assert.deepEqual(plain(P.activityFor({ modules: {} }, 'b', shift)), [], 'sin módulos: solo entrada, salida, pausas y horas');
});

test('pantalla: barra en una fila, franja con total a pagar resaltado, sin nada de CSV, tarjeta marcada "Confirmar salida"', () => {
  const P = load();
  P.model.snapshot = SNAP; P.model.activity = { documents: {} }; P.model.period = { from: '2026-10-01', to: '2026-10-15' }; P.model.cols = 4; P.model.open = 'c';
  const html = P.view();
  assert.match(html, /<header class="client-hero pv-bar">[\s\S]*data-pv-status[\s\S]*data-pv-from[\s\S]*data-pv-to[\s\S]*data-pv-calc>Calcular periodo[\s\S]*data-pv-refresh>Actualizar[\s\S]*data-client-back-dashboard>Volver/);
  for (const l of ['Colaboradores', 'Horas ordinarias', 'Horas extra', 'Bruto', 'Descuentos']) assert.ok(html.includes(`<span>${l}</span>`), l);
  assert.match(html, /<div class="pv-stat is-total"><span>Total a pagar<\/span><strong>\$390<\/strong>/);
  assert.doesNotMatch(html, /csv|Exportaci/i, 'sin CSV en la pantalla');
  assert.doesNotMatch(SRC, /export\.csv|exportPayrollCsv|data-payroll-export/i);
  assert.match(html, /data-pv-filter="all">Todos <b>3<\/b>[\s\S]*data-pv-filter="pending">Por confirmar <b>1<\/b>/);
  assert.match(html, /class="pv-card is-pending is-open" data-pv-card="c" aria-expanded="true"[\s\S]*⚠ Confirmar salida/);
  assert.match(html, /<section class="pv-detail" id="pv-detail-c"[\s\S]*Sin documento[\s\S]*data-pv-confirm="0"/, 'registro desplegado con el turno por confirmar');
  P.model.open = '';
});

test('confirmar salida: ventana con entrada, cierre del sistema, hora real, nota y vista previa; mismo endpoint y regla de siempre', () => {
  const P = load();
  P.model.snapshot = SNAP; P.model.period = { from: '2026-10-01', to: '2026-10-15' };
  P.model.modal = { item: SNAP.unverified_shifts[0], realEnd: '2026-10-07T16:00', note: '', busy: false,
    preview: { before: { regular_minutes: 0, extra_minutes: 0, net_amount: 0 }, after: { regular_minutes: 480, extra_minutes: 30, net_amount: 85000 } } };
  const html = P.view();
  assert.match(html, /role="dialog" aria-modal="true"[\s\S]*<dt>Entrada<\/dt>[\s\S]*<dt>La cerró el sistema<\/dt>/);
  assert.match(html, /data-pv-real-end value="2026-10-07T16:00" min="2026-10-07T07:00" max="2026-10-08T00:00"/);
  assert.match(html, /<textarea data-pv-note/);
  assert.match(html, /Al confirmar[\s\S]*8 h 00 min[\s\S]*\$85\.000/);
  assert.match(html, /data-pv-close aria-label="Cerrar">✕/);
  assert.match(SRC, /\/workforce-sessions\/companies\/\$\{encodeURIComponent\(ctx\.companyId\)\}\/closures\/confirm/, 'mismo endpoint de confirmar');
  assert.match(SRC, /if \(u\.closure_id\) body\.closure_id = u\.closure_id; else Object\.assign\(body, \{ source: u\.source, session_ref: u\.session_ref \}\);/);
  assert.match(SRC, /await load\(model\.period\); \/\/ la tarjeta y los totales se recalculan/);
  assert.match(SRC, /event\.key === "Escape" && model\.modal/, 'se cierra con Esc');
  assert.match(SRC, /t\.matches\("\[data-pv-modal\]"\)/, 'y tocando fuera');
  assert.match(CSS, /@media \(max-width: 760px\)[\s\S]*\.pv-modal-card \{ width: 100%; max-height: 100vh; height: 100%;/, 'en celular ocupa toda la pantalla');
  P.model.modal = null;
});

test('client.js: solo el enganche; apagado (o colombiana) = pantalla de siempre; la de siempre no cambia', () => {
  const start = CLIENT.indexOf('function cxPayrollV2On052B');
  const fn = CLIENT.slice(start, CLIENT.indexOf('\n  }\n', start) + 4);
  const on = (settings) => vm.runInNewContext(`${fn}; cxPayrollV2On052B()`, { activeClientModules: () => [{ code: 'payroll', raw: { settings } }] });
  assert.equal(on({}), false); assert.equal(on({ payroll_v2: 'true' }), false); assert.equal(on({ payroll_v2: true }), true);
  assert.match(CLIENT, /async function renderPayrollModule\(period, options = \{\}\) \{\n    if \(!isClientModuleActive\("payroll"\)\) \{\n      render\(\);\n      return;\n    \}\n    if \(cxPayrollV2On052B\(\) && await cxPayrollV2Mount052B\(period\)\) return;/);
  assert.match(SRC, /legal_mode\.state === "colombia"\) return false;/, 'con normativa colombiana: la de siempre');
  assert.match(CLIENT, /<h2>Exportación<\/h2>/, 'la pantalla de siempre conserva lo suyo');
  assert.doesNotMatch(readFileSync('app/web/client.html', 'utf8'), /payroll_v2/);
  const sw = JSON.parse(readFileSync('app/services/switch_registry.json', 'utf8')).switches.find((s) => s.key === 'payroll_v2');
  assert.equal(sw.module, 'payroll');
});

test('tema: payroll_v2.css sin colores fijos (solo el respaldo de alerta) ni recuadro propio; contraste calculado', () => {
  const css = CSS.replace(/\/\*[\s\S]*?\*\//g, '');
  const rest = css.replace(/var\(--cx-(success|warning|danger),\s*#[0-9a-f]{3,8}\)/gi, '');
  const found = rest.match(/#[0-9a-f]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)|\b(white|black)\b(?!-)/gi) || [];
  assert.deepEqual(found, [], `colores fijos: ${found.join(', ')}`);
  for (const v of ['--cx-primary', '--cx-text', '--cx-bg']) assert.ok(css.includes(`var(${v}`), v);
  assert.doesNotMatch(css, /\.pv-root \{[^}]*(background|border-radius|padding)\s*:/, 'sin recuadro propio');
  assert.match(SRC, /class="client-hero pv-bar"/); assert.match(SRC, /class="client-panel pv-panel"/); assert.match(SRC, /class="client-btn"/);
  const P = load();
  const white = { r: 255, g: 255, b: 255 };
  const p = P.pair(white, [white]);
  assert.ok(P.contrast(p.bg, p.fg) >= 4.5, 'primario y texto blancos (VOLTAGE) se corrigen');
});
