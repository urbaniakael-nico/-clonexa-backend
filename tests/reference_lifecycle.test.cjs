// reference_lifecycle (interruptor): pantallas de Referencias v2 y Producción v2.
// - Doble confirmación antes de corregir; historial visible.
// - Terminar ciclo (076A): una casilla y su botón por talla; nada se cierra ni se oculta; Editar por tarjeta.
// - Buscar por nombre viejo y nuevo trae la misma referencia una sola vez.
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
  assert.doesNotMatch(html, /Corregir producción|Terminar ciclo|Cerrar talla|Cambiar nombre|Editar|antes:/);
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
  R.lifeClick(click({ 'data-rv-lf-edit': GROUP.key }));
  assert.match(R.groupModalView(), /Corregir producción terminada/, 'dentro de Editar');
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

test('cada talla: tres filas en el mismo orden y, al frente, UNA casilla con Terminar ciclo', () => {
  const R = setup();
  const html = R.groupModalView();
  const order = (s) => ['rv-tl-row1', 'rv-tl-nums', 'rv-tl-acts'].map((c) => s.indexOf(c));
  for (const piece of html.split('data-rv-tl="').slice(1)) {
    const at = order(piece);
    assert.ok(at[0] > -1 && at[0] < at[1] && at[1] < at[2], 'fila 1, fila 2, fila 3');
    assert.match(piece, /Recibido[\s\S]*Producido[\s\S]*Pendiente/);
    assert.equal((piece.match(/data-rv-fc=/g) || []).length, 1, 'una casilla numérica');
    assert.match(piece, />Terminar ciclo</);
    assert.doesNotMatch(piece, /Cerrar talla|Reabrir|Talla cerrada|Más</);
  }
  assert.doesNotMatch(html, /Cerrar talla|Reabrir|Talla cerrada|Cerrada ·|Tallas cerradas|Referencia cerrada/);
});

test('terminar ciclo: valida la cantidad, confirma con talla y prendas y suma a Producido', () => {
  const R = setup();
  const m = R.model;
  const go = { 'data-rv-lf-finish': `${GROUP.key}|s`, 'data-rv-lf-key': GROUP.key, 'data-rv-lf-size': 'S' };
  for (const bad of ['', '0', '-2', '1.5', 'abc']) {
    m.finishDraft[`${GROUP.key}|s`] = bad;
    R.lifeClick(click(go));
    assert.equal(m.lifeFlow.kind, 'finishinput', bad);
    assert.match(R.groupModalView(), /data-rv-lf-err="finish"[^>]*>Escribe cuántas prendas/);
  }
  m.finishDraft[`${GROUP.key}|s`] = '52';
  R.lifeClick(click(go));
  assert.equal(m.lifeFlow.kind, 'finish');
  const html = R.groupModalView();
  assert.match(html, /¿Terminar ciclo de S con 52 prendas\?/);
  assert.match(html, /Producido 28 → 80 · Pendiente 16 → 0\. La talla sigue activa\./);
  assert.match(html, /supera la meta \(44\)/);
  assert.match(html, /data-rv-lf-next="finishgo"[^>]*>Sí, terminar ciclo/);
});

test('historial de la talla: "Ciclo terminado · 52 prendas · quién · fecha" junto a las correcciones', () => {
  const R = setup(STATE({ cycles: [{ size: 'S', quantity: 52, actor: 'Admin V2', reason_label: 'Entrega', at: '2026-11-09T14:33:29Z' }],
    corrections: [{ size: 'S', before: 28, after: 0, actor: 'Admin V2', reason: 'error de registro', at: '2026-11-05T18:29:30Z' }] }));
  const html = R.groupModalView();
  assert.match(html, /Ciclo terminado · 52 prendas · Admin V2 · /);
  assert.match(html, /Corregido 28 → 0 por Admin V2 · error de registro/);
  assert.ok(html.indexOf('Ciclo terminado') < html.indexOf('Corregido 28'), 'lo más reciente arriba');
});

test('Editar (uno por tarjeta): cambiar nombre, corregir, reiniciar ciclo y archivar por talla', () => {
  const R = setup();
  let html = R.groupModalView();
  assert.equal((html.match(/data-rv-lf-edit=/g) || []).length, 1, 'un solo botón Editar');
  assert.doesNotMatch(html, /Reiniciar ciclo|Archivar|Cambiar nombre/, 'cerrado hasta tocar Editar');
  R.lifeClick(click({ 'data-rv-lf-edit': GROUP.key }));
  html = R.groupModalView();
  assert.match(html, /Cambiar nombre/);
  for (const [size, id] of [['S', 's1'], ['M', 'm1']]) {
    assert.match(html, new RegExp(`data-rv-lf-start="correct"[^>]*data-rv-lf-size="${size}"[^>]*>Corregir producción terminada`));
    assert.match(html, new RegExp(`data-rv-reset="${id}">Reiniciar ciclo`));
    assert.match(html, new RegExp(`data-rv-archive="${id}" data-rv-archive-label="Choco nuevo talla ${size}">Archivar`));
  }
  R.lifeClick(click({ 'data-rv-lf-edit': GROUP.key }));
  assert.doesNotMatch(R.groupModalView(), /Reiniciar ciclo/, 'Editar se cierra');
});

test('total de la referencia: Meta, Recibido, Producido, Pendiente, tiempo y por prenda con Producido; sin producido "—"', () => {
  const R = setup();
  R.model.lifeAccount[GROUP.key] = { totals: { produced: 28, minutes_per_garment: 43.2, labor_per_garment: null }, total_sizes: 2, time: { total_seconds: 72600, people: [], unclosed: [] }, sizes: [] };
  let html = R.groupModalView();
  assert.match(html, /Meta <b>58<\/b><\/li><li>Recibido <b>58<\/b><\/li><li>Producido <b>28<\/b><\/li><li>Pendiente <b>30<\/b>/);
  assert.match(html, /Tiempo del equipo <b>20 h 10 min/);
  assert.match(html, /Horas por prenda <b>0 h 43 min/);
  assert.match(html, /Mano de obra por prenda <b>Pendiente/);
  assert.doesNotMatch(html, /Prendas cerradas|Tallas cerradas/);
  R.model.lifeAccount[GROUP.key] = { totals: { produced: 0, minutes_per_garment: null, labor_per_garment: null }, total_sizes: 2, time: { total_seconds: 72600, people: [], unclosed: [] }, sizes: [] };
  html = R.groupModalView();
  assert.match(html, /Horas por prenda <b>—<\/b>/);
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

test('nada se cierra: un cierre viejo no oculta la talla, no quita el bot ni crea "Cerradas"', () => {
  const R = setup(STATE({ status: 'closed', closes: [{ size: 'S', closed_qty: 40, actor: 'D', at: 'x', reason_label: 'Entrega' }, { size: 'M', closed_qty: 14, actor: 'D', at: 'x' }] }));
  const cols = R.groupColumns([GROUP], { gender: 'todas' });
  assert.equal(cols.activas.length, 1);
  assert.equal(cols.visibles.length, 1);
  assert.equal(cols.cerradas.length, 0);
  const html = R.groupModalView();
  assert.match(html, /data-rv-gm-bot="s1"/, 'el interruptor Bot sigue');
  assert.doesNotMatch(html + R.groupCard(GROUP, 'Activas'), /Cerrada|Referencia cerrada|Reabrir/);
  R.model.groups = [GROUP];
  assert.doesNotMatch(R.view(), /<h2[^>]*>Cerradas/);
});

test('cortes: una talla que la referencia no tiene se detecta antes de guardar y el resumen dice lo que se guarda', () => {
  const R = setup();
  R.model.rows = [{ id: 's1', name: 'Choco nuevo', size: 'S', color: '' }, { id: 'm1', name: 'Choco nuevo', size: 'M', color: '' }];
  R.model.cut.refId = 's1';
  const items = [{ kind: 'ingreso', size: 'S', quantity: 3 }, { kind: 'ingreso', size: 'L', quantity: 5 }, { kind: 'novedad', section: 'corte', quantity: 1 }, { kind: 'despliegue', size: 'XL', quantity: 1 }];
  assert.deepEqual(JSON.parse(JSON.stringify(R.cutMissingSizes(items))), ['L', 'XL']);
  assert.equal(R.cutSummary(items), 'S 3 · L 5 · Corte 1 · Bombón 1');
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

// ---------------------------------------------------------------- recepción inicial (077A)
const INIT_BAL = () => ({ reference: { id: 's1', name: 'rojita medium' }, received: 71, novelty: 0, deployed: 0, available: 71, received_by_date: [{ date: '2026-11-09', quantity: 71 }],
  log: [{ id: 'i1', kind: 'ingreso', size: 'S', quantity: 46, event_date: '2026-11-09', created_by: 'Velvet Admin', origin: 'recepcion_inicial' },
    { id: 'i2', kind: 'ingreso', size: 'M', quantity: 25, event_date: '2026-11-09', created_by: 'Velvet Admin', origin: 'recepcion_inicial' }],
  events: [{ kind: 'creada', actor: 'Velvet Admin', at: '2026-11-09T14:16:56Z', detail: {} }] });

test('bitácora: "Referencia creada" y "Recepción inicial · S 46 · M 25" con fecha y quién', () => {
  const R = setup();
  const html = R.logView(INIT_BAL());
  assert.match(html, /09\/11\/2026<\/b> · Recepción inicial · total 71/);
  assert.match(html, /<b>Referencia creada<\/b> · [^<]+ · Velvet Admin/);
  assert.match(html, /<b>Recepción inicial<\/b> · S 46 · M 25 · 09\/11\/2026 · Velvet Admin/);
  assert.ok(html.indexOf('Referencia creada') < html.indexOf('<b>Recepción inicial'), 'primero la creación');
  assert.match(html, /data-rv-rf-start="i1">Corregir S/);
  R.model.life = null;
  assert.doesNotMatch(R.logView(INIT_BAL()), /data-rv-rf-start/, 'sin el interruptor no hay corregir');
});

test('corte con la misma talla, fecha y cantidad que la recepción inicial se detecta; otro no', () => {
  const R = setup();
  R.model.balance = INIT_BAL();
  const items = [{ kind: 'ingreso', size: 'S', quantity: 46, event_date: '2026-11-09' }, { kind: 'ingreso', size: 'M', quantity: 10, event_date: '2026-11-09' },
    { kind: 'ingreso', size: 'S', quantity: 46, event_date: '2026-11-10' }];
  assert.deepEqual(JSON.parse(JSON.stringify(R.cutDuplicates(items))).map((x) => [x.size, x.quantity, x.event_date]), [['S', 46, '2026-11-09']]);
});

test('corregir la recepción inicial: nuevo valor y motivo, luego confirmar con casilla', () => {
  const R = setup();
  const m = R.model;
  m.balance = INIT_BAL();
  m.recFix = { id: 'i1', step: 1, value: '', reason: '', checked: false, errors: {} };
  let html = R.recFixView(m.balance.log[0]);
  assert.match(html, /Corregir recepción inicial · talla S/);
  assert.match(html, /Nuevo valor/); assert.match(html, /Motivo \(obligatorio\)/);
  Object.assign(m.recFix, { step: 2, value: '40', reason: 'se contó mal' });
  html = R.recFixView(m.balance.log[0]);
  assert.match(html, /¿Cambiar la recepción inicial de S de 46 a 40\?/);
  assert.match(html, /data-rv-rf-next="go" disabled/, 'sin la casilla no aplica');
  m.recFix.checked = true;
  assert.doesNotMatch(R.recFixView(m.balance.log[0]), /data-rv-rf-next="go" disabled/);
});
