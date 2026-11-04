// 064B: mini panel Líder de operación. Pantalla (solo lectura, ES/EN, filtros de CRM), el Board en
// modo solo lectura sin tocar el del portal, y la tarjeta de la consola v2+.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const WEB = 'app/web/';
const PANEL = readFileSync(`${WEB}lider_operacion.js`, 'utf8');
const BOARD = readFileSync(`${WEB}reports_board.js`, 'utf8');
const DICT = readFileSync(`${WEB}client_i18n_dict.js`, 'utf8');
const CORE = readFileSync(`${WEB}client_i18n_core.js`, 'utf8');
const FICHA = readFileSync(`${WEB}admin_v2plus_ficha.js`, 'utf8');
const COMPANY = readFileSync(`${WEB}admin_v2plus_company.js`, 'utf8');
const FIX = JSON.parse(readFileSync('tests/fixtures/reports_board_caso.json', 'utf8'));

function load({ token = '', saved = '', browser = 'es-CO' } = {}) {
  const local = saved ? { cx_lider_lang: saved } : {};
  const session = {};
  const window = { location: { search: '?company_id=c1&type=lider_operacion&lugar=alabama' },
    __CX_LIDER__: { ok: true, name: 'Alabama', slug: 'alabama', accent: 1, abbr: 'CT', timezone: 'America/Chicago', brand: {} },
    localStorage: { getItem: (k) => (k in local ? local[k] : null), setItem: (k, v) => { local[k] = v; } },
    sessionStorage: { getItem: (k) => (k in session ? session[k] : (k.includes('token') ? token : null)), setItem: (k, v) => { session[k] = v; }, removeItem: (k) => { delete session[k]; session[k] = ''; } } };
  const document = { readyState: 'complete', hidden: false, addEventListener() {}, getElementById: () => null, querySelector: () => null, querySelectorAll: () => [],
    documentElement: { setAttribute() {}, style: { setProperty() {} } }, body: null };
  const context = vm.createContext({ window, document, navigator: { language: browser }, console, Intl, Date, URLSearchParams, setTimeout: () => 1, clearTimeout() {}, setInterval: () => 1, clearInterval() {}, MutationObserver: undefined });
  vm.runInContext(DICT, context);
  vm.runInContext(CORE, context);
  vm.runInContext(BOARD, context);
  vm.runInContext(PANEL, context);
  return { L: window.CxLiderOperacion, window };
}

const HOME = { company: 'VOLTAGE', me: { name: 'Alma Ruiz', role: 'Supervisor' },
  operation: { id: 'al', name: 'Alabama', timezone: 'America/Chicago', abbr: 'CT', accent: 1, slug: 'alabama', local_time: '12:00', local_date: '2026-11-05' },
  crm: { total: 25, working: 12, on_break: 3, no_shift: 8, to_confirm: 2 }, reports: { hours_minutes: 6125, alerts: 4, notes_today: 2 } };
const PEOPLE = [
  { id: 'a', name: 'Ángela Núñez', role: 'Operario', state: 'working', minutes: 280, last_mark: { k: 'in', label: 'Entrada', t: '07:00', a: 'CT', place: 'Patio' } },
  { id: 'b', name: 'Bruno Díaz', role: 'Operario', state: 'on_break', minutes: 20, last_mark: { k: 'pause', label: 'Pausa', t: '11:40', a: 'CT', place: '' } },
  { id: 'c', name: 'Carla Peña', role: 'Supervisor', state: 'no_shift', last_mark: null },
  { id: 'd', name: 'Diego Ruiz', role: 'Operario', state: 'no_shift', end: { t: '17:05', a: 'CT' }, last_mark: { k: 'out', label: 'Salida', t: '17:05', a: 'CT', place: 'Sin perímetro' } },
  { id: 'e', name: 'Elena Gómez', role: 'Operario', state: 'to_confirm', minutes: 900, last_mark: { k: 'in', label: 'Entrada', t: '21:00', a: 'CT', place: '' } },
];

test('Inicio: saludo, rol, hora y personas; dos tarjetas; el aviso de lo que no está; sin dinero', () => {
  const { L } = load({ token: 't' });
  const html = L.homeView(HOME);
  for (const s of ['Hola, Alma Ruiz', 'Supervisor', '25 personas', 'CT', 'CRM Campo', 'Trabajando', 'En pausa', 'Sin turno', 'Reportes', 'Horas de la semana', '102 h 05', 'Alertas', 'Notas de hoy',
    'Este panel solo muestra Alabama. Nómina, tarifas y la otra operación no están disponibles aquí.']) assert.ok(html.includes(s), s);
  assert.equal((html.match(/class="lo-module"/g) || []).length, 2, 'solo 2 módulos');
  assert.doesNotMatch(html, /\$|Bruto|Neto/);
});

test('Barra inferior: Inicio · CRM · Reportes · Salir', () => {
  const { L } = load({ token: 't' });
  const html = L.nav();
  assert.deepEqual([...html.matchAll(/<button[^>]*>([^<]+)</g)].map((m) => m[1]), ['Inicio', 'CRM', 'Reportes', 'Salir']);
});

test('CRM: buscador sin tildes, chips por estado y sin botones de escritura', () => {
  const { L } = load({ token: 't' });
  const names = (q, chip) => [...L.filterPeople(PEOPLE, q, chip)].map((p) => p.id).join('');
  assert.equal(names('', 'all'), 'abcde');
  assert.equal(names('', 'working'), 'a');
  assert.equal(names('', 'on_break'), 'b');
  assert.equal(names('', 'no_shift'), 'cd', 'quien terminó hoy también es Sin turno');
  assert.equal(names('', 'to_confirm'), 'e');
  assert.equal(names('angela', 'all'), 'a');
  assert.equal(names('NUÑEZ', 'working'), 'a');
  assert.equal(names('angela', 'no_shift'), '');
  L.st.crm = { counts: { total: 5, working: 1, on_break: 1, no_shift: 2, to_confirm: 1 }, people: PEOPLE, operation: HOME.operation };
  const html = L.crmList();
  for (const s of ['Todos', 'Trabajando', 'En pausa', 'Sin turno', 'Por confirmar', 'Ángela Núñez', 'Última marca: Entrada 07:00 CT · Patio', 'Trabajando 4 h 40', 'En pausa 0 h 20', 'Terminó 17:05 CT', 'Por confirmar 15 h 00', 'Sin marcas recientes'])
    assert.ok(html.includes(s), s);
  assert.doesNotMatch(html, /Cerrar turno|Confirmar salida|Close shift/i);
  assert.equal((html.match(/<button/g) || []).length, 5, 'solo los 5 chips');
});

test('Idioma: recuerda la elección; sin elección usa el idioma del navegador', () => {
  assert.equal(load({ saved: 'en' }).L.savedLang(), 'en');
  assert.equal(load({ saved: 'es', browser: 'en-US' }).L.savedLang(), 'es');
  assert.equal(load({ browser: 'en-US' }).L.savedLang(), 'en');
  assert.equal(load({ browser: 'es-CO' }).L.savedLang(), 'es');
});

test('EN: pantalla y mensajes del servidor traducidos', () => {
  const { L, window } = load({ token: 't' });
  window.CxI18n.setLanguage('en');
  const html = L.homeView(HOME);
  for (const s of ['Hello, Alma Ruiz', '25 people', 'Field CRM', 'Working', 'On break', 'No shift', 'Reports', 'Hours this week', 'Alerts', 'Notes today',
    'This panel only shows Alabama. Payroll, rates and the other operation are not available here.']) assert.ok(html.includes(s), s);
  assert.deepEqual([...L.nav().matchAll(/<button[^>]*>([^<]+)</g)].map((m) => m[1]), ['Home', 'CRM', 'Reports', 'Sign out']);
  assert.equal(L.serverText('Este panel es solo para el líder de Alabama'), 'This panel is only for the Alabama lead');
  assert.equal(L.serverText('Usuario o clave inválidos.'), 'Invalid username or password.');
  L.st.crm = { counts: {}, people: PEOPLE, operation: HOME.operation };
  for (const s of ['Last mark: Check-in 07:00 CT', 'Working 4 h 40', 'On break 0 h 20', 'Finished 17:05 CT', 'To confirm 15 h 00', 'No recent marks']) assert.ok(L.crmList().includes(s), s);
});

test('Ingreso: usuario y clave con el nombre de la operación; enlace malo avisa', () => {
  const { L, window } = load();
  const html = L.loginView();
  for (const s of ['Alabama', 'Líder de operación', 'name="username"', 'name="password"', 'type="password"', 'Entrar', 'Español', 'English']) assert.ok(html.includes(s), s);
  const bad = load();
  bad.L.st.notice = 'Este panel es solo para el líder de Alabama';
  assert.ok(bad.L.loginView().includes('Este panel es solo para el líder de Alabama'));
  assert.ok(window);
});

function board(readonly) {
  const window = { addEventListener() {} };
  const document = { addEventListener() {}, createElement: () => ({ style: {}, remove() {} }), hidden: false };
  vm.runInNewContext(BOARD, { window, document, console, Intl, Date, setTimeout, clearTimeout, setInterval: () => 1, clearInterval() {}, localStorage: { getItem: () => null, setItem() {} }, URLSearchParams });
  const B = window.CxReportsBoard;
  Object.assign(B.model, { data: JSON.parse(JSON.stringify(FIX)), preset: 'week', anchor: '2026-11-05', query: '', op: 'all', status: '', sort: 'az', open: '', loading: false, error: '', denied: false, busy: '', notesShown: {}, alertsAll: {} });
  B._ctx({ companyId: 'c1', apiBase: '/api/v1', token: () => 't', host: () => null, back() {}, ...(readonly ? { readonly: true, baseUrl: '/api/v1/lider-operacion/companies/c1/reportes' } : {}) });
  return B;
}

test('Board del líder: Hoy, Semana y Mes, cifras con overtime, sin exportes ni Pagable', () => {
  const B = board(true);
  const html = B.view();
  for (const s of ['data-rb-preset="today"', 'data-rb-preset="week"', 'data-rb-preset="month"', 'Horas en turno', 'Pausas', 'Overtime', 'Horas por día', 'Alertas', 'Notas de cierre']) assert.ok(html.includes(s), s);
  for (const s of ['data-rb-export', 'Descargar PDF', 'CSV', 'data-rb-preset="custom"', 'data-rb-back', 'Pagable', 'documento', 'Board de gerencia']) assert.ok(!html.includes(s), s);
});

test('Board del portal: sin cambios', () => {
  const B = board(false);
  const html = B.view();
  for (const s of ['data-rb-export="pdf"', 'data-rb-export="marks"', 'data-rb-preset="custom"', 'data-rb-back', 'Pagable', 'Buscar por nombre, documento o texto de una nota', 'Board de gerencia']) assert.ok(html.includes(s), s);
});

function ficha() {
  const window = { location: { href: '', origin: 'https://x', hash: '' } };
  const ctx = vm.createContext({ window, document: {}, fetch: async () => ({}), JSON, Object, Array, String, Math, Number, Promise, Error, Date, Map, Set, RegExp, console, setTimeout, clearTimeout, Intl, encodeURIComponent, URLSearchParams });
  vm.runInContext(FICHA, ctx);
  return window.CxFicha;
}
const CONSOLE = { label: 'Líder de operación', places: [
  { id: 'va', name: 'Virginia', abbr: 'ET', accent: 0, link: '/mini-panel/login?company_id=c1&type=lider_operacion&lugar=virginia', supervisors: [{ id: 's1', name: 'Sofía Mora', role: 'supervisor' }], leaders: [] },
  { id: 'al', name: 'Alabama', abbr: 'CT', accent: 1, link: '/mini-panel/login?company_id=c1&type=lider_operacion&lugar=alabama', supervisors: [{ id: 's2', name: 'Alma Ruiz', role: 'supervisor' }],
    leaders: [{ user_id: 'u1', username: 'alma.lider', full_name: 'Alma Ruiz', status: 'active', valid: true }] },
] };

test('Consola: los dos enlaces para copiar y el formulario solo con los supervisores de la operación', () => {
  const F = ficha();
  const html = F.leaderZone(CONSOLE, {}, 'https://clonexa.app');
  for (const s of ['Líder de operación', 'Virginia', 'Alabama', 'Crear líder', 'alma.lider', 'nunca va por correo',
    'data-vpf-copy="https://clonexa.app/mini-panel/login?company_id=c1&amp;type=lider_operacion&amp;lugar=virginia"',
    'data-vpf-copy="https://clonexa.app/mini-panel/login?company_id=c1&amp;type=lider_operacion&amp;lugar=alabama"']) assert.ok(html.includes(s), s);
  const options = (h) => [...h.matchAll(/<select [^>]*name="employee_id".*?<\/select>/gs)][0][0];
  assert.ok(options(html).includes('Sofía Mora') && !options(html).includes('Alma Ruiz'), 'Virginia primero');
  const al = F.leaderZone(CONSOLE, { place: 'al' }, 'https://clonexa.app');
  assert.ok(options(al).includes('Alma Ruiz') && !options(al).includes('Sofía Mora'));
  assert.ok(al.includes('value="al" selected'));
});

test('Consola: sin supervisores no deja crear; apagado no se muestra; sin estilos en línea (CSP)', () => {
  const F = ficha();
  const empty = F.leaderZone({ places: [{ ...CONSOLE.places[0], supervisors: [] }] }, {}, '');
  assert.ok(empty.includes('Sin supervisores en Virginia') && empty.includes('Personal') && /type="submit" disabled/.test(empty));
  assert.equal(F.leaderZone({ off: true }), '');
  assert.equal(F.leaderZone(null), '');
  assert.doesNotMatch(F.leaderZone(CONSOLE, {}, ''), /style=|<script/);
});

test('Consola: la pestaña carga el líder y escribe con el contrato del servidor; nada de correo', () => {
  assert.ok(COMPANY.includes('modulos: ["modules", "activity", "crmLab", "lider"]'));
  assert.ok(COMPANY.includes('`${API}/lider-operacion/consola/companies/${encodeURIComponent(id)}/lideres`'));
  assert.ok(COMPANY.includes('form.matches("[data-vpl-form]")'));
  assert.doesNotMatch(FICHA.slice(FICHA.indexOf('function leaderZone'), FICHA.indexOf('function picker')), /mailto|send_email|sendEmail/);
});

test('El panel solo llama a sus rutas de lectura, al ingreso y a su salida', () => {
  const calls = [...PANEL.matchAll(/fetch\((.+?), \{/g)].map((m) => m[1].trim());
  assert.deepEqual(calls.sort(), ['`${API}/auth/logout`', '`${API}/companies/${encodeURIComponent(CID)}/mini-panel-login`', 'panelUrl(path)'].sort());
  assert.deepEqual([...PANEL.matchAll(/read\("(\w+)"\)/g)].map((m) => m[1]).sort(), ['crm', 'inicio']);
});
