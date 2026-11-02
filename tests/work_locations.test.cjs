// Lugares de trabajo (interruptor work_locations): Personal v2 y CRM Campo.
// - Apagado (otra empresa con Workforce y CRM Campo): el formulario conserva
//   Descuento 2, no hay columna, filtro ni casillas, y CRM Campo es el de siempre.
// - Encendido (VOLTAGE): Lugar de trabajo en vez de Descuento 2 sin cambiar el
//   dato guardado, filtro y CSV con lugar, asignación múltiple, Administrar
//   lugares; CRM por lugar con conteos, hora local, Sin asignar, orden y buscador.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const WF = readFileSync('app/web/workforce_v2.js', 'utf8');
const CRM = readFileSync('app/web/crm_places.js', 'utf8');
const CRM_CSS = readFileSync('app/web/crm_places.css', 'utf8');
const WF_CSS = readFileSync('app/web/workforce_v2.css', 'utf8');
const CLIENT = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');

const tick = () => new Promise((r) => setTimeout(r, 0));
async function settle() { for (let i = 0; i < 8; i += 1) await tick(); }

function loadWf() {
  const window = {};
  const listeners = {};
  const document = { addEventListener: (t, f) => { listeners[t] = f; }, activeElement: null, createElement: () => ({ style: {}, remove() {} }) };
  vm.runInNewContext(WF, { window, document, Blob: function Blob() {}, URL: {}, getComputedStyle: undefined, console });
  return { W: window.CxWorkforceV2, listeners };
}

const ROLES = [['gerencia', 'Director'], ['supervisor', 'Supervisor'], ['operario', 'Operario']];
const EMPLOYEES = [
  { id: 'e1', full_name: 'Nicolás Gómez', role: 'supervisor', status: 'active', deduction_1: 10, deduction_2: 37.5, hourly_rate_regular: 18 },
  { id: 'e2', full_name: 'Ana', role: 'operario', status: 'active', deduction_2: 0 },
  { id: 'e3', full_name: 'Beto', role: 'operario', status: 'inactive', deduction_2: 0 },
];
const PLACES = { locations: [
  { id: 'va', name: 'Virginia', code: 'VA', timezone: 'America/New_York', is_active: true },
  { id: 'al', name: 'Alabama', code: 'AL', timezone: 'America/Chicago', is_active: true },
  { id: 'tx', name: 'Texas', code: 'TX', timezone: 'America/Chicago', is_active: false },
], assignments: { e1: 'va', e2: null, e3: 'al' }, can_manage: true, can_assign: true };

async function mountWf({ on, places = PLACES } = {}) {
  const { W, listeners } = loadWf();
  const host = { innerHTML: '', querySelector: () => null, contains: () => true };
  const calls = [];
  const personal = [];
  await W.mount({
    companyId: 'c1', host: () => host, roles: () => ROLES, configured: () => true, workLocations: on,
    personalApi: async (path, opts = {}) => { personal.push({ path, ...opts }); return opts.method === 'POST' ? { id: 'nuevo' } : EMPLOYEES; },
    authApi: async (path, opts = {}) => { calls.push({ path, ...opts }); if (!opts.method) return places; return { ok: true, changed: 1 }; },
  });
  return { W, host, calls, personal, listeners };
}

function form(attr, id, values) {
  const elements = {};
  Object.entries(values).forEach(([k, v]) => { elements[k] = typeof v === 'object' ? v : { value: v }; });
  return { elements, getAttribute: (a) => (a === attr ? id : null), matches: (sel) => sel === `[${attr}]` };
}

test('apagado: formulario con Descuento 2, sin Lugar, sin columnas ni casillas, y no llama al servidor de lugares', async () => {
  const { W, host, calls } = await mountWf({ on: false });
  assert.equal(W.model.wl, null);
  assert.equal(calls.length, 0, 'sin interruptor no se pide nada de lugares');
  assert.doesNotMatch(host.innerHTML, /Lugar|data-wf2-pick|Administrar lugares|wf-place/);
  W.model.modal = { type: 'edit', employee: { ...EMPLOYEES[0] } };
  const html = W.view();
  assert.match(html, /name="deduction_2"/);
  assert.match(html, />Descuento 2</);
  assert.doesNotMatch(html, /work_location_id/);
  const csv = W.csvText(EMPLOYEES, ROLES, W.model.wl).split('\n')[0];
  assert.equal(csv, '"Nombre","Documento","Rol","Telefono","Correo","Telegram ID","Fecha ingreso","Hora ordinaria","Hora extra","Descuento 1","Descuento 2","Estado"', 'CSV igual que siempre');
});

test('apagado: guardar envía Descuento 2 del formulario como siempre', async () => {
  const { W, listeners, personal, calls } = await mountWf({ on: false });
  W.model.modal = { type: 'edit', employee: { ...EMPLOYEES[0] } };
  const f = form('data-wf2-form', 'e1', { full_name: 'Nicolás Gómez', role: 'supervisor', deduction_2: '12', status: 'active' });
  listeners.submit({ target: f, preventDefault() {} });
  await settle();
  const patch = personal.find((c) => c.method === 'PATCH');
  assert.equal(JSON.parse(patch.body).deduction_2, 12);
  assert.equal(calls.length, 0);
});

test('encendido: Lugar de trabajo reemplaza Descuento 2; columna, chip, filtro, casillas y Administrar lugares', async () => {
  const { W, host } = await mountWf({ on: true });
  assert.ok(W.model.wl, 'lugares cargados');
  assert.match(host.innerHTML, /<th class="wf-th" scope="col">Lugar<\/th>/);
  assert.match(host.innerHTML, /wf-place ">Virginia</);
  assert.match(host.innerHTML, /wf-place is-none">Sin asignar</);
  assert.match(host.innerHTML, /data-wf2-place-filter="all"[^>]*>Todos</);
  assert.match(host.innerHTML, /data-wf2-place-filter="va"[^>]*>Virginia</);
  assert.match(host.innerHTML, /data-wf2-place-filter="al"[^>]*>Alabama</);
  assert.match(host.innerHTML, /data-wf2-place-filter="none"[^>]*>Sin asignar</);
  assert.doesNotMatch(host.innerHTML, /data-wf2-place-filter="tx"/, 'desactivado no se ofrece como filtro');
  assert.match(host.innerHTML, /data-wf2-places>Administrar lugares/);
  assert.match(host.innerHTML, /data-wf2-pick-all/);
  W.model.modal = { type: 'edit', employee: { ...EMPLOYEES[0] } };
  const html = W.view();
  assert.doesNotMatch(html, /name="deduction_2"/, 'Descuento 2 no está en el formulario');
  assert.match(html, /<span>Lugar de trabajo<\/span><select name="work_location_id" >/);
  assert.match(html, /<option value="va" selected>Virginia<\/option>/);
  assert.doesNotMatch(html, /value="tx"/, 'lugar desactivado no se ofrece');
  assert.match(html, /<legend>Contrato<\/legend>/);
});

test('encendido: editar conserva el descuento 2 guardado y traslada con historial (assign)', async () => {
  const { W, listeners, personal, calls } = await mountWf({ on: true });
  W.model.modal = { type: 'edit', employee: { ...EMPLOYEES[0] } };
  const f = form('data-wf2-form', 'e1', { full_name: 'Nicolás Gómez', role: 'supervisor', status: 'active', deduction_1: '10', work_location_id: { value: 'al', disabled: false } });
  listeners.submit({ target: f, preventDefault() {} });
  await settle();
  const body = JSON.parse(personal.find((c) => c.method === 'PATCH').body);
  assert.equal(body.deduction_2, 37.5, 'el descuento 2 guardado no cambia');
  assert.equal(body.deduction_1, 10);
  const assign = calls.find((c) => c.method === 'POST');
  assert.equal(assign.path, '/work-locations/companies/c1/assign');
  assert.deepEqual(JSON.parse(assign.body), { employee_ids: ['e1'], work_location_id: 'al', source: 'personal_form' });
});

test('encendido: crear empleado con lugar (descuento 2 en 0) y sin cambio de lugar no hay traslado', async () => {
  const { W, listeners, personal, calls } = await mountWf({ on: true });
  W.model.modal = { type: 'edit', employee: { status: 'active', role: 'operario' } };
  listeners.submit({ target: form('data-wf2-form', '', { full_name: 'Nueva Persona', role: 'operario', status: 'active', work_location_id: { value: 'va', disabled: false } }), preventDefault() {} });
  await settle();
  assert.equal(JSON.parse(personal.find((c) => c.method === 'POST').body).deduction_2, 0);
  assert.deepEqual(JSON.parse(calls.find((c) => c.method === 'POST').body).employee_ids, ['nuevo']);

  const second = await mountWf({ on: true });
  second.W.model.modal = { type: 'edit', employee: { ...EMPLOYEES[0] } };
  second.listeners.submit({ target: form('data-wf2-form', 'e1', { full_name: 'Nicolás Gómez', role: 'supervisor', status: 'active', work_location_id: { value: 'va', disabled: false } }), preventDefault() {} });
  await settle();
  assert.equal(second.calls.filter((c) => c.method === 'POST').length, 0, 'mismo lugar: no se registra traslado');
});

test('encendido: filtro por lugar, búsqueda por lugar y CSV con la columna Lugar', () => {
  const { W } = loadWf();
  const names = (f, q = '') => W.visible(EMPLOYEES, 'all', q, ROLES, PLACES, f).map((e) => e.full_name);
  assert.deepEqual(names('all'), ['Ana', 'Beto', 'Nicolás Gómez']);
  assert.deepEqual(names('va'), ['Nicolás Gómez']);
  assert.deepEqual(names('al'), ['Beto']);
  assert.deepEqual(names('none'), ['Ana']);
  assert.deepEqual(names('all', 'alabama'), ['Beto']);
  assert.deepEqual(W.visible(EMPLOYEES, 'active', '', ROLES, PLACES, 'va').map((e) => e.full_name), ['Nicolás Gómez'], 'se combina con Activos');
  const csv = W.csvText(EMPLOYEES.slice(0, 2), ROLES, PLACES).split('\n');
  assert.match(csv[0], /"Estado","Lugar"$/);
  assert.match(csv[1], /"Activo","Virginia"$/);
  assert.match(csv[2], /"Activo","Sin asignar"$/);
  assert.equal(W.assignLabel(12, 'Virginia'), 'Asignar 12 empleados a Virginia');
  assert.equal(W.assignLabel(1, 'Alabama'), 'Asignar 1 empleado a Alabama');
  assert.equal(W.assignLabel(3, 'Sin asignar'), 'Quitar el lugar a 3 empleados');
  assert.deepEqual({ ...W.keepDeduction2({ deduction_2: '' }, { deduction_2: 50 }) }, { deduction_2: '50' });
  assert.deepEqual({ ...W.keepDeduction2({ deduction_2: '' }, null) }, { deduction_2: '0' });
});

test('encendido: selección múltiple -> Asignar lugar -> confirmar "Asignar 2 empleados a Virginia"', async () => {
  const { W, listeners, calls, host } = await mountWf({ on: true });
  const box = (id, checked) => ({ matches: (s) => s === '[data-wf2-pick]', getAttribute: () => id, checked });
  listeners.change({ target: box('e2', true) });
  listeners.change({ target: box('e3', true) });
  assert.match(host.innerHTML, /2 seleccionados/);
  const click = (attr) => ({ closest: (s) => (s === `[${attr}]` ? {} : null), matches: () => false });
  listeners.click({ target: click('data-wf2-assign') });
  assert.equal(W.model.modal.type, 'assign');
  assert.match(host.innerHTML, /Asignar 2 empleados a Virginia/);
  listeners.change({ target: { matches: (s) => s === '[data-wf2-assign-target]', value: 'al' } });
  assert.match(host.innerHTML, /Asignar 2 empleados a Alabama/);
  listeners.submit({ target: form('data-wf2-assignform', '', { work_location_id: 'al' }), preventDefault() {} });
  await settle();
  const post = calls.find((c) => c.method === 'POST');
  assert.deepEqual(JSON.parse(post.body), { employee_ids: ['e2', 'e3'], work_location_id: 'al', source: 'personal_multiple' });
  assert.equal(W.model.selected.size, 0, 'la selección se limpia');
});

test('Administrar lugares: solo con can_manage; ordenar, agregar y guardar envía la lista', async () => {
  const noManage = await mountWf({ on: true, places: { ...PLACES, can_manage: false, can_assign: false } });
  assert.doesNotMatch(noManage.host.innerHTML, /Administrar lugares|data-wf2-pick/);
  noManage.W.model.modal = { type: 'edit', employee: { ...EMPLOYEES[0] } };
  assert.match(noManage.W.view(), /<select name="work_location_id" disabled>/, 'sin permiso el lugar se ve pero no se cambia');

  const { W, listeners, calls } = await mountWf({ on: true });
  const click = (attr, value) => ({ closest: (s) => (s === `[${attr}]` ? { getAttribute: () => value } : null), matches: () => false });
  listeners.click({ target: click('data-wf2-places') });
  assert.equal(W.model.modal.type, 'places');
  listeners.click({ target: click('data-wf2-place-down', '0') });
  assert.deepEqual(W.model.modal.rows.map((r) => r.id), ['al', 'va', 'tx']);
  listeners.click({ target: click('data-wf2-place-add') });
  listeners.input({ target: { matches: (s) => s === '[data-wf2-place-field]', getAttribute: (a) => (a === 'data-i' ? '3' : 'name'), value: 'Georgia' } });
  listeners.submit({ target: form('data-wf2-placesform', '', {}), preventDefault() {} });
  await settle();
  const put = calls.find((c) => c.method === 'PUT');
  assert.equal(put.path, '/work-locations/companies/c1/locations');
  assert.deepEqual(JSON.parse(put.body).locations.map((r) => r.name), ['Alabama', 'Virginia', 'Texas', 'Georgia']);
});

test('servidor de lugares caído o 404: Personal sigue como siempre (con Descuento 2)', async () => {
  const { W } = loadWf();
  const host = { innerHTML: '', querySelector: () => null, contains: () => true };
  await W.mount({ companyId: 'c1', host: () => host, roles: () => ROLES, configured: () => true, workLocations: true,
    personalApi: async () => EMPLOYEES, authApi: async () => { throw new Error('404 Not Found'); } });
  assert.equal(W.model.wl, null);
  W.model.modal = { type: 'edit', employee: { ...EMPLOYEES[0] } };
  assert.match(W.view(), /name="deduction_2"/);
});

// ------------------------------------------------------------ CRM Campo
function loadCrm(storage) {
  const window = { localStorage: storage };
  const document = { addEventListener() {}, activeElement: null, createElement: () => ({ style: {}, remove() {} }) };
  vm.runInNewContext(CRM, { window, document, Intl, Date, console, setInterval: () => 0, clearInterval() {}, getComputedStyle: undefined, CSS: {} });
  return window.CxCrmPlaces;
}

const row = (id, name, status, place = 'inside', role = 'Operario') => ({ employee_id: id, employee_name: name, employee_role: role, gps_place: place,
  core: { status, shift_effective_seconds: status === 'sin_turno' ? 0 : 3723 } });
const BOARD = {
  ok: true, active_modules: ['crm', 'gps', 'materials', 'workforce'],
  summary: { employees_total: 6, active_now: 3, on_break: 1, gps_adapter: true, gps_inside: 2 },
  groups: [
    { key: 'va', name: 'Virginia', code: 'VA', timezone: 'America/New_York', supervisors: ['Zoe Sup'], counts: { total: 4, working: 2, on_break: 1, no_shift: 1, in_perimeter: 2 },
      people: [row('a', 'Andrés', 'working'), row('z', 'Zoe Sup', 'working', 'outside', 'Supervisor'), row('b', 'Bea', 'on_break', 'none'), row('c', 'Carlos', 'sin_turno', 'none')] },
    { key: 'al', name: 'Alabama', code: 'AL', timezone: 'America/Chicago', supervisors: [], counts: { total: 1, working: 1, on_break: 0, no_shift: 0, in_perimeter: 0 },
      people: [row('d', 'Dani', 'working', 'unconfigured')] },
    { key: 'none', name: 'Sin asignar', code: null, timezone: null, supervisors: [], counts: { total: 1, working: 0, on_break: 0, no_shift: 1, in_perimeter: 0 },
      people: [row('e', 'Eva', 'sin_turno', 'none')] },
  ],
};

test('CRM: botones Todas · Virginia (4) · Alabama (1) · Sin asignar (1); Sin asignar solo si hay gente', () => {
  const P = loadCrm({ getItem: () => null, setItem() {} });
  assert.deepEqual(JSON.parse(JSON.stringify(P.buttons(BOARD.groups))), [
    { key: 'all', label: 'Todas', count: 6 }, { key: 'va', label: 'Virginia', count: 4 }, { key: 'al', label: 'Alabama', count: 1 }, { key: 'none', label: 'Sin asignar', count: 1 }]);
  const noneEmpty = BOARD.groups.slice(0, 2);
  assert.deepEqual([...P.buttons([...noneEmpty, { key: 'none', name: 'Sin asignar', people: [] }]).map((b) => b.key)], ['all', 'va', 'al']);
  assert.equal(P.validFilter(BOARD.groups, 'al'), 'al');
  assert.equal(P.validFilter(BOARD.groups, 'borrado'), 'all', 'si el lugar guardado ya no está vuelve a Todas');
});

test('CRM: orden trabajando, en pausa, sin turno; alfabético; buscador por nombre sin tildes', () => {
  const P = loadCrm({ getItem: () => null, setItem() {} });
  const mixed = [row('c', 'carlos', 'sin_turno'), row('b', 'Bea', 'on_break'), row('z', 'Zoe', 'working'), row('a', 'Ándres', 'working'), row('x', 'Xime', 'checked_out')];
  assert.deepEqual(P.sortPeople(mixed).map((r) => r.employee_name), ['Ándres', 'Zoe', 'Bea', 'carlos', 'Xime']);
  assert.deepEqual(P.searchPeople(mixed, 'andres').map((r) => r.employee_name), ['Ándres']);
  assert.equal(P.searchPeople(mixed, '').length, 5);
  assert.deepEqual(JSON.parse(JSON.stringify(P.countsOf(BOARD.groups[0].people))), { total: 4, working: 2, on_break: 1, no_shift: 1, in_perimeter: 1 });
});

test('CRM: hora local por zona; Virginia va una hora por delante de Alabama (verano e invierno)', () => {
  const P = loadCrm({ getItem: () => null, setItem() {} });
  for (const iso of ['2026-07-15T15:00:00Z', '2026-12-15T15:00:00Z', '2026-11-01T05:30:00Z']) {
    const d = new Date(iso);
    assert.equal(P.tzOffsetMinutes('America/New_York', d) - P.tzOffsetMinutes('America/Chicago', d), 60, iso);
  }
  const d = new Date('2026-12-15T15:00:00Z');
  assert.match(P.localTime('America/New_York', d), /^10:00/);
  assert.match(P.localTime('America/Chicago', d), /^9:00/);
  assert.equal(P.localTime(null, d), '');
  assert.equal(P.hm(3723), '1:02');
});

test('CRM: Todas = una sección por lugar en 2 columnas + tarjetas de arriba; un lugar = solo su sección', () => {
  const P = loadCrm({ getItem: () => null, setItem() {} });
  P.model.data = BOARD;
  P.model.filter = 'all';
  let html = P.view();
  assert.match(html, /cxp-sections is-all/);
  assert.equal((html.match(/data-cxp-sec=/g) || []).length, 3);
  assert.match(html, /Supervisor: Zoe Sup/);
  assert.match(html, /data-cxp-clock="America\/New_York"/);
  assert.match(html, /data-cxp-clock="America\/Chicago"/);
  assert.match(html, /<span>Activos<\/span><strong>2<\/strong>/);
  assert.match(html, /<span>En perímetro<\/span><strong>2<\/strong>/);
  assert.match(html, /<span>Sin turno<\/span><strong>1<\/strong>/);
  assert.match(html, />Trabajando</);
  assert.match(html, />En pausa</);
  assert.match(html, />Sin turno</);
  assert.match(html, />En perímetro</);
  assert.match(html, />Fuera</);
  assert.match(html, />Sin ubicación</);
  assert.match(html, /data-cxp-open="a"/);
  P.model.filter = 'al';
  html = P.view();
  assert.equal((html.match(/data-cxp-sec=/g) || []).length, 1);
  assert.match(html, /data-cxp-sec="al"/);
  assert.doesNotMatch(html, /cxp-sections is-all/);
  P.model.filter = 'va';
  P.model.query = 'bea';
  html = P.view();
  assert.match(html, /data-cxp-open="b"/);
  assert.doesNotMatch(html, /data-cxp-open="a"/);
  P.model.query = 'nadie';
  assert.match(P.view(), /Nadie coincide con la búsqueda/);
});

test('CRM: recuerda la última elección (localStorage) y no se rompe si el almacenamiento falla', () => {
  const store = {};
  const P = loadCrm({ getItem: (k) => store[k] || null, setItem: (k, v) => { store[k] = v; } });
  P.saveChoice('c1', 'al');
  assert.equal(P.readChoice('c1'), 'al');
  assert.equal(P.readChoice('c2'), 'all', 'por empresa');
  const broken = loadCrm({ getItem: () => { throw new Error('bloqueado'); }, setItem: () => { throw new Error('bloqueado'); } });
  assert.doesNotThrow(() => broken.saveChoice('c1', 'va'));
  assert.equal(broken.readChoice('c1'), 'all');
});

test('CRM: una sola llamada al tablero; si falla, mount devuelve false (CRM de siempre)', async () => {
  const P = loadCrm({ getItem: () => null, setItem() {} });
  const host = { innerHTML: '', querySelector: () => null, querySelectorAll: () => [], contains: () => true };
  const paths = [];
  assert.equal(await P.mount({ companyId: 'c1', host: () => host, api: async (p) => { paths.push(p); return BOARD; }, top: () => '<div class="client-kpi-grid">TOP</div>' }), true);
  assert.deepEqual(paths, ['/work-locations/companies/c1/board']);
  assert.match(host.innerHTML, /TOP/);
  const Q = loadCrm({ getItem: () => null, setItem() {} });
  assert.equal(await Q.mount({ companyId: 'c1', host: () => host, api: async () => { throw new Error('404'); } }), false);
});

test('client.js: CRM y Personal solo cambian con work_locations; los ganchos 059A no tocan el resto', () => {
  assert.match(CLIENT, /function cxWorkLocationsOn059A\(\) \{[\s\S]{0,300}settings\.work_locations === true;/);
  assert.match(CLIENT, /if \(cxWorkLocationsOn059A\(\)\) \{ \/\/ 059A: CRM por lugar\n\s+if \(await cxCrmPlacesMount059A\(\)\) return;/);
  assert.match(CLIENT, /workLocations: cxWorkLocationsOn059A\(\)/);
  assert.match(CLIENT, /authApi: api,/);
  const crm = CLIENT.slice(CLIENT.indexOf('async function renderCrmModule()'));
  assert.match(crm.slice(0, 600), /isClientModuleActive\("crm"\)[\s\S]*cxWorkLocationsOn059A/, 'el gancho va después del chequeo del módulo');
  assert.match(crm, /renderCrmCollaboratorCards\(crm\.people/, 'el CRM de siempre sigue intacto como respaldo');
  assert.doesNotMatch(readFileSync('app/web/client.html', 'utf8'), /crm_places|work_locations/, 'client.html no cambia');
});

test('tema: CSS nuevos sin colores fijos salvo los respaldos semánticos', () => {
  const strip = (css) => css.replace(/var\(--cx-(success|warning|danger), #[0-9a-f]{6}\)/gi, '');
  for (const [name, css] of [['crm_places.css', CRM_CSS], ['workforce_v2.css 059A', WF_CSS.slice(WF_CSS.indexOf('059A'))]]) {
    assert.doesNotMatch(strip(css), /#[0-9a-f]{3,8}\b|rgba?\(/i, name);
  }
  assert.match(CRM_CSS, /@media \(max-width: 900px\)[\s\S]*cxp-sections\.is-all \{ grid-template-columns: minmax\(0, 1fr\)/, 'una debajo de otra en celular');
});

test('059B: el navegador pide client.js y crm_places nuevos (versión en la URL) y la caída al CRM de siempre avisa', () => {
  const html = readFileSync('app/web/client.html', 'utf8');
  assert.match(html, /\/client-static\/client\.js\?v=[^"]*_059B[^"]*"/, 'client.js con la versión 059B (o posterior)');
  assert.match(CLIENT, /crm_places\.js\?v=059B/);
  assert.match(CLIENT, /crm_places\.css\?v=059B/);
  const i = CLIENT.indexOf('async function renderCrmModule()');
  const body = CLIENT.slice(i, i + 900);
  assert.match(body, /if \(cxWorkLocationsOn059A\(\)\) \{[\s\S]*if \(await cxCrmPlacesMount059A\(\)\) return;[\s\S]*console\.warn\("CRM por lugar no cargo/);
});
