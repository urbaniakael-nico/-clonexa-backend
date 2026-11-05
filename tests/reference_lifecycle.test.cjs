// reference_lifecycle (interruptor): pantallas de Referencias v2 y Producción v2.
// - Doble confirmación antes de corregir; historial visible; cerrar talla con motivo obligatorio (Entrega o Cierre de ciclo).
// - Buscar por nombre viejo y nuevo trae la misma referencia una sola vez.
// - Referencia cerrada: sale de Activas y va a Cerradas.
// - Sin el interruptor no aparece nada nuevo.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const REFS = readFileSync('app/web/references_v2.js', 'utf8');
const PROD = readFileSync('app/web/production_v2.js', 'utf8');
const CLIENT = readFileSync('app/web/client.js', 'utf8');

function loadRefs() {
  const window = {};
  vm.runInNewContext(REFS, { window, document: {}, URLSearchParams, console, confirm: () => true, setTimeout });
  return window.CxReferencesV2;
}
function loadProd() {
  const window = {};
  vm.runInNewContext(PROD, { window, document: {}, URLSearchParams, console });
  return window.CxProductionV2;
}

const LINE = (size, id, o = {}) => ({ size, color: '', reference_id: id, solo_corte: false, meta: 44, received: 44, produced: 28, pending: 16, bot_active: true, ...o });
const GROUP = { key: 'choconuevo', name: 'Choco nuevo', color: '', colors: [], received: 58, produced: 28, meta: 58, pending: 30, percent: 48, solo_corte: [], cuts_by_date: [],
  lines: [LINE('S', 's1'), LINE('M', 'm1', { meta: 14, received: 14, produced: 0, pending: 14 })] };
const STATE = (o = {}) => ({ former_names: ['Choco-fresa'], renames: [{ old_name: 'Choco-fresa', new_name: 'Choco nuevo', actor: 'Dueña', at: '2026-11-05T12:00:00Z' }],
  corrections: [], closes: [], reopened: [], requests: [], status: 'open', ...o });
const click = (attrs) => ({ closest: (sel) => { const name = sel.slice(1, -1); return name in attrs ? { getAttribute: (a) => (a in attrs ? attrs[a] : null) } : null; } });

function setup(state = STATE()) {
  const R = loadRefs();
  R.model.groups = [GROUP];
  R.model.gdraft = { s1: { meta: '44', visible: true, color: '' }, m1: { meta: '14', visible: true, color: '' } };
  R.model.modal = `g:${GROUP.key}`;
  R.model.life = { [GROUP.key]: state };
  R.model.tab = 'estado';
  return R;
}

test('sin el interruptor no aparece nada nuevo', () => {
  const R = setup();
  R.model.life = null;
  const html = R.groupModalView();
  assert.doesNotMatch(html, /Corregir producido|Cerrar talla|Cambiar nombre|antes:/);
  assert.doesNotMatch(R.groupCard(GROUP, 'Activas'), /antes:/);
  assert.deepEqual(R.groupColumns([GROUP], { gender: 'todas' }).cerradas.length, 0);
});

test('buscar por el nombre viejo y el nuevo trae la misma referencia una sola vez', () => {
  const R = setup();
  for (const search of ['choco-fresa', 'choco nuevo']) {
    const cols = R.groupColumns([GROUP], { search, gender: 'todas' });
    assert.equal(cols.activas.length, 1, search);
    assert.equal(cols.activas[0].name, 'Choco nuevo');
  }
  assert.equal(R.groupColumns([GROUP], { search: 'otra cosa', gender: 'todas' }).activas.length, 0);
  assert.match(R.groupCard(GROUP, 'Activas'), /antes: Choco-fresa/);
});

test('corregir producido: 0 es válido, errores por casilla y confirmación con casilla', () => {
  const R = setup();
  const m = R.model;
  assert.match(R.groupModalView(), /Corregir producido/);
  const start = { 'data-rv-lf-start': 'correct', 'data-rv-lf-key': GROUP.key, 'data-rv-lf-size': 'S' };
  R.lifeClick(click(start));
  assert.equal(m.lifeFlow.kind, 'correct');
  R.lifeClick(click({ 'data-rv-lf-next': 'correct2' }));
  assert.equal(m.lifeFlow.errors.value, 'Valor inválido', 'vacío no es 0');
  assert.equal(m.lifeFlow.errors.reason, 'Escribe el motivo');
  const shown = R.groupModalView();
  assert.match(shown, /data-rv-lf-err="value"[^>]*>Valor inválido/);
  assert.match(shown, /data-rv-lf-err="reason"[^>]*>Escribe el motivo/);
  m.lifeFlow.value = '0';
  R.lifeClick(click({ 'data-rv-lf-next': 'correct2' }));
  assert.equal(m.lifeFlow.errors.value, undefined, '0 es un valor válido');
  assert.equal(m.lifeFlow.step, 1, 'sin motivo no avanza');
  m.lifeFlow.reason = 'se metió por error';
  R.lifeClick(click({ 'data-rv-lf-next': 'correct2' }));
  assert.equal(m.lifeFlow.step, 2);
  const last = R.groupModalView();
  assert.match(last, /¿Cambiar producido de S de 28 a 0\?/);
  assert.match(last, /Confirmo la corrección/);
  assert.match(last, /data-rv-lf-next="correctgo" disabled/, 'sin la casilla no se puede aplicar');
  m.lifeFlow.checked = true;
  assert.doesNotMatch(R.groupModalView(), /data-rv-lf-next="correctgo" disabled/);
});

test('valor inválido: texto y negativos no pasan; 0 sí', () => {
  const R = setup();
  for (const bad of ['', ' ', '-1', '1.5', 'abc']) assert.equal(R.wholeNumber(bad), false, bad);
  for (const ok of ['0', ' 0 ', '28']) assert.equal(R.wholeNumber(ok), true, ok);
});

test('cada talla: tres filas en el mismo orden y Reiniciar y Archivar dentro de Más', () => {
  const R = setup();
  const html = R.groupModalView();
  const order = (s) => ['rv-tl-row1', 'rv-tl-nums', 'rv-tl-acts'].map((c) => s.indexOf(c));
  for (const piece of html.split('data-rv-tl="').slice(1)) {
    const at = order(piece);
    assert.ok(at[0] > -1 && at[0] < at[1] && at[1] < at[2], 'fila 1, fila 2, fila 3');
    assert.match(piece, /<summary[^>]*>Más<\/summary>[\s\S]*Reiniciar ciclo[\s\S]*Archivar/);
    assert.match(piece, /Corregir producido[\s\S]*Cerrar talla[\s\S]*Más/);
  }
});

test('sin prendas cerradas, por prenda y mano de obra dicen —', () => {
  const R = setup();
  R.model.lifeAccount[GROUP.key] = { totals: { closed_qty: 0, minutes_per_garment: null, labor_per_garment: null }, closed_sizes: 0, total_sizes: 2, time: { total_seconds: 72600, people: [], unclosed: [] }, sizes: [] };
  const html = R.groupModalView();
  assert.match(html, /Por prenda <b>—<\/b>/);
  assert.match(html, /Mano de obra por prenda <b>—<\/b>/);
});

test('corregir a más de lo recibido avisa antes de aplicar', () => {
  const R = setup();
  R.model.lifeFlow = { kind: 'correct', key: GROUP.key, size: 'S', step: 2, value: '50', reason: 'recuento' };
  assert.match(R.groupModalView(), /50 supera lo recibido \(44\)/);
});

test('el historial de correcciones se ve en la talla', () => {
  const R = setup(STATE({ corrections: [{ size: 'S', before: 28, after: 0, actor: 'Dueña', reason: 'se metió por error', at: '2026-11-05T12:00:00Z' }] }));
  assert.match(R.groupModalView(), /Corregido 28 → 0 por Dueña · se metió por error/);
});

test('cerrar talla: cantidad final y motivo obligatorios, solo Entrega o Cierre de ciclo, detalle opcional y confirmación', () => {
  const R = setup();
  const m = R.model;
  assert.match(R.groupModalView(), /Cerrar talla/);
  R.lifeClick(click({ 'data-rv-lf-start': 'close', 'data-rv-lf-key': GROUP.key, 'data-rv-lf-size': 'S' }));
  assert.equal(m.lifeFlow.value, '28', 'propone lo producido');
  const form = R.groupModalView();
  assert.match(form, /Cantidad final</);
  assert.match(form, /Motivo<select/);
  assert.match(form, /Detalle \(opcional\)/);
  assert.deepEqual([...form.matchAll(/<option value="([^"]+)"[^>]*>([^<]+)</g)].map((x) => [x[1], x[2]]), [['entrega', 'Entrega'], ['cierre_ciclo', 'Cierre de ciclo']]);
  assert.doesNotMatch(form, /Merma|Defecto|Devolución|Otro/);
  assert.doesNotMatch(form, /Bombón/);

  m.lifeFlow.value = '';
  R.lifeClick(click({ 'data-rv-lf-next': 'close2' }));
  assert.match(m.lifeFlow.errors.value, /cantidad final/);
  assert.match(m.lifeFlow.errors.code, /motivo/);
  assert.equal(m.lifeFlow.step, 1);

  m.lifeFlow.value = '40';
  m.lifeFlow.code = 'merma';
  R.lifeClick(click({ 'data-rv-lf-next': 'close2' }));
  assert.match(m.lifeFlow.errors.code, /motivo/, 'un motivo retirado no pasa');

  m.lifeFlow.code = 'entrega';
  R.lifeClick(click({ 'data-rv-lf-next': 'close2' }));
  assert.equal(m.lifeFlow.step, 2, 'el detalle es opcional');
  const confirm = R.groupModalView();
  assert.match(confirm, /¿Cerrar la talla S con 40 prendas\?/);
  assert.match(confirm, /Motivo: Entrega/);
});

test('cerrar talla: 0 es una cantidad final válida', () => {
  const R = setup();
  const m = R.model;
  R.lifeClick(click({ 'data-rv-lf-start': 'close', 'data-rv-lf-key': GROUP.key, 'data-rv-lf-size': 'S' }));
  m.lifeFlow.value = '0';
  m.lifeFlow.code = 'cierre_ciclo';
  m.lifeFlow.note = 'fin de temporada';
  R.lifeClick(click({ 'data-rv-lf-next': 'close2' }));
  assert.equal(m.lifeFlow.step, 2);
  const confirm = R.groupModalView();
  assert.match(confirm, /¿Cerrar la talla S con 0 prendas\?/);
  assert.match(confirm, /Motivo: Cierre de ciclo · fin de temporada/);
});

test('tarjeta: dice Cerrada · Entrega o Cerrada · Cierre de ciclo; un cierre sin motivo dice solo Cerrada', () => {
  const closes = (o) => STATE({ closes: [{ size: 'S', closed_qty: 40, actor: 'Dueña', at: '2026-11-05T12:00:00Z', ...o }] });
  const chip = (html) => html.match(/rv-chip is-lime is-closed-why">([^<]+)</)[1];
  for (const [state, text] of [
    [closes({ reason_code: 'entrega', reason_label: 'Entrega' }), 'Cerrada · Entrega'],
    [closes({ reason_code: 'cierre_ciclo', reason_label: 'Cierre de ciclo' }), 'Cerrada · Cierre de ciclo'],
    [closes({}), 'Cerrada'],
  ]) {
    const R = setup(state);
    assert.equal(chip(R.groupCard(GROUP, 'Activas')), text, 'en la tarjeta');
    assert.equal(chip(R.groupModalView()), text, 'en el editor');
  }
});

test('talla cerrada: muestra su cuenta, no el interruptor del bot, y reabrir pide doble confirmación', () => {
  const R = setup(STATE({ closes: [{ size: 'S', closed_qty: 40, actor: 'Dueña', at: '2026-11-05T12:00:00Z', reason_code: 'entrega', reason_label: 'Entrega' }] }));
  const m = R.model;
  m.lifeAccount[GROUP.key] = { totals: { closed_qty: 40 }, closed_sizes: 1, total_sizes: 2, time: { total_seconds: 7200, people: [{ name: 'KRIS', total_seconds: 7200 }], unclosed: [] },
    sizes: [{ size: 'S', closed: true, closed_qty: 40, meta: 44, diff_meta: -4, received: 44, diff_received: -4, days: 6, seconds: 7200, minutes_per_garment: 3, labor_per_garment: null, reason_label: 'Entrega' }] };
  const html = R.groupModalView();
  assert.match(html, /Talla cerrada/);
  assert.match(html, /Horas repartidas por cantidad/);
  assert.match(html, /Mano de obra por prenda <b>Pendiente/);
  assert.match(html, /Motivo <b>Entrega/);
  assert.doesNotMatch(html, /data-rv-gm-bot="s1"/);
  assert.match(html, /data-rv-gm-bot="m1"/);
  R.lifeClick(click({ 'data-rv-lf-start': 'reopen', 'data-rv-lf-key': GROUP.key, 'data-rv-lf-size': 'S' }));
  R.lifeClick(click({ 'data-rv-lf-next': 'reopen2' }));
  assert.match(m.lifeFlow.errors.reason, /motivo/);
  m.lifeFlow.reason = 'faltó contar';
  R.lifeClick(click({ 'data-rv-lf-next': 'reopen2' }));
  assert.match(R.groupModalView(), /data-rv-lf-next="reopengo" disabled/);
});

test('referencia cerrada: sale de Activas y va a Cerradas', () => {
  const R = setup(STATE({ status: 'closed', closes: [{ size: 'S', closed_qty: 40, actor: 'D', at: 'x' }, { size: 'M', closed_qty: 14, actor: 'D', at: 'x' }] }));
  const cols = R.groupColumns([GROUP], { gender: 'todas' });
  assert.equal(cols.activas.length, 0);
  assert.equal(cols.visibles.length, 0);
  assert.equal(cols.cerradas.length, 1);
  assert.match(R.groupModalView(), /Referencia cerrada/);
  assert.match(R.groupCard(GROUP, 'Cerradas'), /Cerrada/);
});

test('cambiar nombre: confirma con los dos nombres y dice que conserva todo', () => {
  const R = setup();
  const m = R.model;
  R.lifeClick(click({ 'data-rv-lf-start': 'rename', 'data-rv-lf-key': GROUP.key, 'data-rv-lf-size': '' }));
  assert.equal(m.lifeFlow.value, 'Choco nuevo');
  R.lifeClick(click({ 'data-rv-lf-next': 'rename2' }));
  assert.match(m.lifeFlow.errors.value, /ya es el nombre/);
  m.lifeFlow.value = 'Choco tres';
  R.lifeClick(click({ 'data-rv-lf-next': 'rename2' }));
  const html = R.groupModalView();
  assert.match(html, /¿Cambiar el nombre de Choco nuevo a Choco tres\?/);
  assert.match(html, /Se conserva todo/);
});

test('lo que el bot no registró aparece para aprobar', () => {
  const R = setup(STATE({ requests: [{ id: 'q1', size: 'S', quantity: 5, received: 44, produced: 42, employee: 'KRIS' }] }));
  const html = R.groupModalView();
  assert.match(html, /KRIS reportó 5 en talla S \(recibido 44, producido 42\)/);
  assert.match(html, /data-rv-lf-dec="approve"/);
  assert.match(html, /data-rv-lf-dec="reject"/);
  assert.match(R.groupCard(GROUP, 'Activas'), /Por aprobar: 1/);
});

// ---------------------------------------------------------------- Producción
const KPI = { status: 'ok', value: 1, working: 0, paused: 0, lots: 0, to_send: 0, labor: 0 };
const PROD_DATA = (o = {}) => ({
  company: { name: 'VELVET' }, period: { from: '2026-10-15', to: '2026-10-30', by: 'week' }, lifecycle: true,
  kpis: { workshop_now: KPI, closed: KPI, sent: KPI, days_per_lot: KPI, team_hours_per_garment: KPI, labor_per_garment: { status: 'pendiente', reason: 'Falta valor hora: KRIS' } },
  lots_in_process: [{ key: 'choco', name: 'Choco nuevo', former_names: ['Choco-fresa'], meta: 58, closed: 10, pending: 48, sent: 0, days_open: 22, sizes: [], cuts: [], news: [], team: ['Ana'],
    total_seconds: 776340, period_seconds: 773160, people: [{ name: 'Ana', total_seconds: 776340, period_seconds: 773160 }], unclosed: [{ name: 'Bea', started: '2026-11-05T12:00:00+00:00', reason: 'abierta' }],
    account: { sizes: [], totals: { closed_qty: 0, meta: 58, received: 58, seconds: 776340 }, labor_missing: [] }, corrections: [] }],
  lots_closed: [{ key: 'lote', name: 'Lote cerrado', former_names: [], total_seconds: 36000, period_seconds: 0, people: [], unclosed: [],
    account: { sizes: [{ size: 'S', closed: true, closed_qty: 40, meta: 44, received: 44, diff_received: -4, days: 6, seconds: 26667, minutes_per_garment: 11.1, labor_per_garment: 1852 }],
      totals: { closed_qty: 40, meta: 44, received: 44, seconds: 36000, minutes_per_garment: 11.1, labor_per_garment: 1852 }, labor_missing: [] } }],
  live: [], series: [], team_time: { by_reference: [] }, alerts: [], ...o });

test('Producción: las dos cifras en la tarjeta, sin cerrar aparte y cerradas con su cuenta', () => {
  const P = loadProd();
  P.model.data = PROD_DATA();
  P.model.open = 'choco';
  const html = P.view();
  assert.match(html, /Total de la referencia/);
  assert.match(html, /215 h 39 min/);
  assert.match(html, /214 h 46 min/);
  assert.match(html, /Sin cerrar/);
  assert.match(html, /Sesión abierta/);
  assert.match(html, /antes: Choco-fresa/);
  assert.match(html, /Lote cerrado/);
  assert.match(html, /Pendiente/);
  P.model.open = 'lote';
  assert.match(P.view(), /repartidas por cantidad/);
});

test('Producción: buscar por nombre viejo o nuevo; sin el interruptor no hay buscador ni Cerradas', () => {
  const P = loadProd();
  P.model.data = PROD_DATA();
  P.model.search = 'choco-fresa';
  assert.match(P.view(), /Choco nuevo/);
  assert.doesNotMatch(P.view(), /Lote cerrado/);
  P.model.search = '';
  P.model.data = PROD_DATA({ lifecycle: false, lots_closed: undefined });
  assert.doesNotMatch(P.view(), /data-pp-search/);
  assert.doesNotMatch(P.view(), /<h2[^>]*>Cerradas</);
});

test('client.js pasa el interruptor y pide los archivos nuevos', () => {
  assert.match(CLIENT, /function cxRefLifecycleOn068A/);
  assert.match(CLIENT, /settings\.reference_lifecycle === true/);
  assert.match(CLIENT, /lifecycle: cxRefLifecycleOn068A\(code\)/);
  assert.match(CLIENT, /name === "production_v2" \? "068D" : "056J"/);
});
