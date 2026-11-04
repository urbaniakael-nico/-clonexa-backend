// 064B + 067A: mini panel Líder de operación. Pantalla (semáforo, ES/EN, filtros de CRM), Marcar con
// PIN, finalizar turnos, el Board en modo solo lectura sin tocar el del portal y la tarjeta de la consola v2+.
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
  crm: { total: 25, working: 12, on_break: 3, no_shift: 8, to_confirm: 2 }, reports: { hours_minutes: 6125, alerts: 4, notes_today: 2, notes: 7 } };
const PEOPLE = [
  { id: 'a', name: 'Ángela Núñez', role: 'Operario', state: 'working', minutes: 280, can_finish: true, origin: 'app', last_mark: { k: 'in', label: 'Entrada', t: '07:00', d: '2026-11-05', a: 'CT', place: 'Patio' } },
  { id: 'b', name: 'Bruno Díaz', role: 'Operario', state: 'on_break', minutes: 20, can_finish: true, origin: 'pin', last_mark: { k: 'pause', label: 'Pausa', t: '11:40', d: '2026-11-05', a: 'CT', place: '' } },
  { id: 'c', name: 'Carla Peña', role: 'Supervisor', state: 'no_shift', can_finish: false, origin: '', last_mark: null },
  { id: 'd', name: 'Diego Ruiz', role: 'Operario', state: 'no_shift', can_finish: false, origin: 'lider', end: { t: '17:05', a: 'CT' }, last_mark: { k: 'out', label: 'Salida', t: '17:05', d: '2026-11-04', a: 'CT', place: 'Sin perímetro' } },
  { id: 'e', name: 'Elena Gómez', role: 'Operario', state: 'to_confirm', minutes: 900, can_finish: false, origin: 'app', last_mark: { k: 'in', label: 'Entrada', t: '21:00', d: '2026-11-04', a: 'CT', place: '' } },
];

test('Inicio: reloj, 4 contadores en semáforo y 3 accesos; sin dinero', () => {
  const { L } = load({ token: 't' });
  const html = L.homeView(HOME);
  for (const s of ['Supervisor', '25 personas', 'CT', 'data-lo-clock="America/Chicago"', 'Trabajando', 'En pausa', 'Por confirmar', 'Sin turno', 'CRM Campo', 'Reportes', 'Marcar con PIN',
    '102 h 05 esta semana', '7 notas', '4 alertas']) assert.ok(html.includes(s), s);
  assert.equal((html.match(/class="lo-module/g) || []).length, 3, '3 accesos');
  assert.deepEqual([...html.matchAll(/data-lo-counter="(\w+)"><strong>(\d+)/g)].map((m) => [m[1], m[2]]), [['working', '12'], ['on_break', '3'], ['to_confirm', '2'], ['no_shift', '8']]);
  assert.doesNotMatch(html, /\$|Bruto|Neto/);
});

test('Barra inferior: Inicio · CRM · PIN · Reportes · Salir', () => {
  const { L } = load({ token: 't' });
  const html = L.nav();
  assert.deepEqual([...html.matchAll(/<button[^>]*>([^<]+)</g)].map((m) => m[1]), ['Inicio', 'CRM', 'PIN', 'Reportes', 'Salir']);
});

test('CRM: buscador sin tildes, chips en semáforo, A-Z, origen y tiempo; finalizar solo si se puede', () => {
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
  L.st.crm = { counts: { total: 5, working: 1, on_break: 1, no_shift: 2, to_confirm: 1 }, people: PEOPLE, operation: HOME.operation, limit_hours: 15 };
  const html = L.crmList();
  for (const s of ['5 personas · A-Z', 'PDF lista', 'Ángela Núñez', 'Entrada 07:00 · App', 'Pausa 11:40 · PIN', '4 h 40', '0 h 20', '+15 h', 'Terminó 17:05 CT', 'Sin marcas recientes', 'Salida ayer 17:05 · Líder'])
    assert.ok(html.includes(s), s);
  assert.deepEqual([...html.matchAll(/data-lo-chip="(\w+)"/g)].map((m) => m[1]), ['working', 'on_break', 'to_confirm', 'no_shift']);
  for (const [cls, name] of [['is-working', 'Ángela'], ['is-on_break', 'Bruno'], ['is-to_confirm', 'Elena'], ['is-no_shift', 'Carla']]) assert.match(html, new RegExp(`lo-person ${cls}"[^]*?${name}`));
  // Solo trabajando o en pausa (menos del límite): "Por confirmar" no tiene botón y nunca hay campo de hora.
  assert.deepEqual([...html.matchAll(/data-lo-finish="(\w+)"/g)].map((m) => m[1]), ['a', 'b']);
  assert.doesNotMatch(html, /type="(time|datetime-local)"|name="end_at"|Cerrar turno/i);
});

test('Finalizar: confirmación con nombre y hora local, sin campo para escribir horas', () => {
  const { L, window } = load({ token: 't' });
  L.st.home = HOME;
  L.st.finish = { id: 'a', name: 'Ángela <Núñez>', busy: false };
  const html = L.finishDialog();
  assert.match(html, /¿Finalizar el turno de Ángela &lt;Núñez&gt; ahora \(<span data-lo-clock="America\/Chicago">[\d:]*<\/span> CT\)\?/);
  assert.doesNotMatch(html, /<input|<select|<textarea/);
  for (const s of ['data-lo-finish-yes', 'data-lo-finish-no', 'role="alertdialog"', 'hora actual del servidor']) assert.ok(html.includes(s), s);
  window.CxI18n.setLanguage('en');
  assert.match(L.finishDialog(), /End Ángela &lt;Núñez&gt;&#039;s shift now|End Ángela &lt;Núñez&gt;'s shift now/);
});

function fakeTimers() {
  const pending = new Map();
  let next = 1;
  const set = (fn, ms) => { pending.set(next, { fn, ms }); return next++; };
  const clear = (id) => pending.delete(id);
  return { set, clear, pending, due: () => [...pending.values()].map((t) => t.ms).filter((ms) => ms === 20000), fire(ms) { for (const [id, t] of [...pending]) if (t.ms === ms) { pending.delete(id); t.fn(); } } };
}

function pinPanel(responses = {}, geo = { coords: { latitude: 32.3, longitude: -86.3, accuracy: 9 } }) {
  const timers = fakeTimers();
  const calls = [];
  const fetchStub = async (url, opts = {}) => {
    calls.push({ url: String(url), body: opts.body ? JSON.parse(opts.body) : null });
    const key = Object.keys(responses).find((k) => String(url).includes(k));
    const answer = key ? responses[key] : { status: 200, body: {} };
    return { ok: answer.status < 400, status: answer.status, json: async () => answer.body };
  };
  const session = {};
  const window = { location: { search: '?company_id=c1&type=lider_operacion&lugar=alabama' }, history: { state: { lo: 1, screen: 'pin', depth: 2 }, replaceState() {}, pushState() {}, go() {} }, addEventListener() {},
    __CX_LIDER__: { ok: true, name: 'Alabama', slug: 'alabama', accent: 1, abbr: 'CT', timezone: 'America/Chicago', brand: {} }, scrollTo() {},
    localStorage: { getItem: () => 'es', setItem() {} }, sessionStorage: { getItem: (k) => (k.includes('token') ? 't' : null), setItem: (k, v) => { session[k] = v; }, removeItem() {} } };
  const document = { readyState: 'complete', hidden: false, addEventListener() {}, getElementById: () => null, querySelector: () => null, querySelectorAll: () => [], documentElement: { setAttribute() {}, style: { setProperty() {} } }, body: null };
  const navigator = { language: 'es-CO', geolocation: geo ? { getCurrentPosition: (ok) => ok(geo) } : { getCurrentPosition: (_ok, fail) => fail(new Error('denied')) } };
  const context = vm.createContext({ window, document, navigator, console, Intl, Date, URLSearchParams, setTimeout: timers.set, clearTimeout: timers.clear, setInterval: () => 1, clearInterval() {}, MutationObserver: undefined, fetch: fetchStub, Promise, JSON });
  vm.runInContext(DICT, context);
  vm.runInContext(CORE, context);
  vm.runInContext(BOARD, context);
  vm.runInContext(PANEL, context);
  const L = window.CxLiderOperacion;
  L.st.tab = 'pin';
  return { L, timers, calls, window };
}
const settle = async () => { for (let i = 0; i < 8; i += 1) await new Promise((r) => setImmediate(r)); };
const OK_PIN = { 'pin/verificar': { status: 200, body: { ok: true, employee: { name: 'Hector Sandoval', role: 'Operario', state: 'working', actions: ['pause', 'end'] } } }, 'pin/marcar': { status: 200, body: { ok: true, name: 'Hector Sandoval', at: '09:31 CT' } } };

test('PIN: teclado de 4 dígitos con ubicación e intentos; no pasa de 4', () => {
  const { L } = pinPanel();
  let html = L.pinView();
  for (const k of ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'del', 'ok']) assert.ok(html.includes(`data-lo-key="${k}"`), k);
  for (const s of ['Cada persona marca con su propio PIN', '5 intentos fallidos = bloqueo de 15 min', 'Borrar']) assert.ok(html.includes(s), s);
  for (const k of ['1', '2', '3', '4', '5']) L.pressKey(k);
  assert.equal(L.pinState().digits, '1234');
  html = L.pinView();
  assert.equal((html.match(/<i class="is-on"/g) || []).length, 4);
  assert.ok(!html.includes('1234'), 'el PIN no se escribe en la página');
  L.pressKey('del');
  assert.equal(L.pinState().digits, '123');
});

test('PIN correcto: nombre, semáforo y solo las acciones posibles; Finalizar pide el resumen', async () => {
  const { L, calls } = pinPanel(OK_PIN);
  for (const k of ['4', '8', '2', '7']) L.pressKey(k);
  L.pressKey('ok');
  await settle();
  assert.deepEqual(calls[0].body, { pin: '4827' });
  let html = L.pinView();
  for (const s of ['Hector Sandoval', 'HS', 'is-working', 'Trabajando', 'data-lo-punch="pause"', 'data-lo-punch="end"', 'Vuelve solo al teclado en 20 s', 'Panel PIN']) assert.ok(html.includes(s), s);
  assert.ok(!html.includes('data-lo-punch="start"') && !html.includes('data-lo-punch="resume"'), 'solo lo posible');
  assert.ok(!html.includes('4827'));

  await L.punch('end');
  assert.equal(calls.length, 1, 'tocar Finalizar aún no marca');
  html = L.pinView();
  assert.ok(html.includes('data-lo-summary') && html.includes('Resumen de la jornada'));
  await L.punch('end');
  assert.equal(calls.length, 1, 'sin resumen no marca');
  assert.ok(L.pinView().includes('Escribe el resumen de la jornada.'));
  L.pinState().summary = 'Rack 4 listo';
  await L.punch('end');
  await settle();
  assert.equal(calls.length, 2);
  const sent = calls[1].body;
  assert.equal(sent.pin, '4827');
  assert.equal(sent.action, 'end');
  assert.equal(sent.summary, 'Rack 4 listo');
  assert.equal(sent.latitude, 32.3);
  assert.equal(sent.longitude, -86.3);
  assert.ok(!('at' in sent) && !('occurred_at' in sent) && !('time' in sent), 'la hora la pone el servidor');
  assert.equal(L.pinState().digits, '', 'el PIN sale de la memoria');
  assert.ok(L.pinView().includes('Turno finalizado · Hector Sandoval · 09:31 CT'));
});

test('PIN: a los 20 s sin tocar vuelve al teclado y olvida a la persona', async () => {
  const { L, timers } = pinPanel(OK_PIN);
  for (const k of ['4', '8', '2', '7']) L.pressKey(k);
  assert.deepEqual(timers.due(), [20000], 'ya corre desde el primer dígito');
  L.pressKey('ok');
  await settle();
  assert.ok(L.pinState().person);
  assert.deepEqual(timers.due(), [20000], 'un solo reloj');
  L.touchPin();
  assert.deepEqual(timers.due(), [20000], 'tocar lo reinicia, no suma');
  timers.fire(20000);
  assert.equal(L.pinState().person, null);
  assert.equal(L.pinState().digits, '');
  assert.ok(L.pinView().includes('data-lo-key="1"'));
  assert.equal(L.IDLE_MS, 20000);
});

test('PIN: sin ubicación no marca y lo dice; errores del servidor se muestran sin perder la sesión', async () => {
  const noGeo = pinPanel(OK_PIN, null);
  for (const k of ['4', '8', '2', '7']) noGeo.L.pressKey(k);
  noGeo.L.pressKey('ok');
  await settle();
  await noGeo.L.punch('pause');
  assert.equal(noGeo.calls.filter((c) => c.url.includes('pin/marcar')).length, 0, 'no llama al servidor');
  assert.ok(noGeo.L.pinView().includes('Activa la ubicación de este equipo'));

  const other = pinPanel({ 'pin/verificar': { status: 422, body: { detail: 'Este PIN no es de Alabama' } } });
  for (const k of ['1', '3', '5', '7']) other.L.pressKey(k);
  other.L.pressKey('ok');
  await settle();
  assert.ok(other.L.pinView().includes('Este PIN no es de Alabama'));
  assert.equal(other.L.pinState().digits, '', 'limpia el teclado');
  assert.equal(other.L.st.tab, 'pin', 'sigue en su sesión');

  const locked = pinPanel({ 'pin/verificar': { status: 423, body: { detail: 'Demasiados intentos. Este equipo queda bloqueado 15 min.' } } });
  for (const k of ['1', '3', '5', '7']) locked.L.pressKey(k);
  locked.L.pressKey('ok');
  await settle();
  assert.ok(locked.L.pinView().includes('Este equipo queda bloqueado 15 min.'));

  const short = pinPanel();
  short.L.pressKey('1');
  short.L.pressKey('ok');
  await settle();
  assert.equal(short.calls.length, 0, 'con menos de 4 dígitos no llama');
});

test('Finalizar: pide la ubicación del equipo y solo manda eso al servidor', async () => {
  const { L, calls } = pinPanel({ '/finalizar': { status: 200, body: { ok: true, name: 'Ana', at: '09:40 CT' } }, '/crm': { status: 200, body: { ok: true, operation: HOME.operation, counts: {}, people: [] } } });
  L.st.tab = 'crm';
  L.st.finish = { id: 'e1', name: 'Ana', busy: false };
  await L.finishNow();
  await settle();
  const call = calls.find((c) => c.url.includes('/finalizar'));
  assert.deepEqual(Object.keys(call.body).sort(), ['accuracy', 'latitude', 'longitude']);
  assert.match(call.url, /\/crm\/e1\/finalizar$/);
  assert.equal(L.st.crmNote.text, 'Turno de Ana finalizado a las 09:40 CT.');

  const none = pinPanel({}, null);
  none.L.st.tab = 'crm';
  none.L.st.finish = { id: 'e1', name: 'Ana', busy: false };
  await none.L.finishNow();
  assert.equal(none.calls.filter((c) => c.url.includes('/finalizar')).length, 0);
  assert.equal(none.L.st.crmNote.text, 'Activa la ubicación de este equipo');
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
  for (const s of ['25 people', 'Field CRM', 'Working', 'On break', 'To confirm', 'No shift', 'Reports', 'Clock in with PIN', '102 h 05 this week', '7 notes', '4 alerts']) assert.ok(html.includes(s), s);
  assert.deepEqual([...L.nav().matchAll(/<button[^>]*>([^<]+)</g)].map((m) => m[1]), ['Home', 'CRM', 'PIN', 'Reports', 'Sign out']);
  for (const [es, en] of [['Este PIN no es de Alabama', 'This PIN is not from Alabama'], ['PIN incorrecto. Intentos restantes: 3.', 'Wrong PIN. Attempts left: 3.'], ['Demasiados intentos. Este equipo queda bloqueado 15 min.', 'Too many attempts. This device is locked for 15 min.'],
    ['Activa la ubicación de este equipo', 'Turn on location on this device'], ['Esa persona no es de Alabama.', 'That person is not from Alabama.']]) assert.equal(L.serverText(es), en);
  L.st.tab = 'pin';
  for (const s of ['Each person clocks in with their own PIN', '5 failed attempts = locked for 15 min', 'Delete']) assert.ok(L.pinView().includes(s), s);
  assert.equal(L.serverText('Este panel es solo para el líder de Alabama'), 'This panel is only for the Alabama lead');
  assert.equal(L.serverText('Usuario o clave inválidos.'), 'Invalid username or password.');
  L.st.crm = { counts: {}, people: PEOPLE, operation: HOME.operation, limit_hours: 15 };
  for (const s of ['Check-in 07:00 · App', 'Working', 'On break', 'Finished 17:05 CT', 'To confirm', 'No recent marks', 'End shift now', 'PDF list', 'Check-out yesterday 17:05 · Lead', '+15 h']) assert.ok(L.crmList().includes(s), s);
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
  B._ctx({ companyId: 'c1', apiBase: '/api/v1', token: () => 't', host: () => null, back() {}, ...(readonly ? { readonly: true, baseUrl: '/api/v1/lider-operacion/companies/c1/reportes', pdf: readonly === 'pdf' } : {}) });
  return B;
}

test('Board del líder: Hoy, Semana y Mes, cifras con overtime, sin CSV ni Pagable; PDF solo si el panel lo pide', () => {
  const B = board(true);
  const html = B.view();
  for (const s of ['data-rb-preset="today"', 'data-rb-preset="week"', 'data-rb-preset="month"', 'Horas en turno', 'Pausas', 'Overtime', 'Horas por día', 'Alertas', 'Notas de cierre']) assert.ok(html.includes(s), s);
  for (const s of ['data-rb-export', 'Descargar PDF', 'CSV', 'data-rb-preset="custom"', 'data-rb-back', 'Pagable', 'documento', 'Board de gerencia']) assert.ok(!html.includes(s), s);
  const withPdf = board('pdf').view();
  assert.deepEqual([...withPdf.matchAll(/data-rb-export="(\w+)"/g)].map((m) => m[1]), ['pdf'], 'solo el PDF, sin CSV');
  assert.ok(withPdf.includes('Descargar PDF'));
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

test('Consola: muestra y copia el enlace corto en lugar del largo; sin corto, el largo', () => {
  const F = ficha();
  const withShort = { places: CONSOLE.places.map((p, i) => ({ ...p, short_link: i ? '/c/2M496FCU' : '/c/8AWXZJSY' })) };
  const html = F.leaderZone(withShort, {}, 'https://clonexa.app');
  for (const s of ['data-vpf-copy="https://clonexa.app/c/8AWXZJSY"', 'data-vpf-copy="https://clonexa.app/c/2M496FCU"', 'Copiar enlace', '<small class="vp-mono" data-vpl-link>https://clonexa.app/c/8AWXZJSY</small>']) assert.ok(html.includes(s), s);
  assert.ok(!html.includes('company_id='), 'sin company_id visible');
  assert.ok(F.leaderZone(CONSOLE, {}, 'https://clonexa.app').includes('lugar=virginia'), 'si no se pudo crear, el largo sigue');
});

test('Pregunta de salida en español e inglés, con Sí y No', () => {
  const { L, window } = load({ token: 't' });
  for (const s of ['¿Salir del panel?', 'data-lo-exit-yes', 'data-lo-exit-no', 'role="alertdialog"', '>Sí<', '>No<']) assert.ok(L.exitDialog().includes(s), s);
  window.CxI18n.setLanguage('en');
  for (const s of ['Leave the panel?', '>Yes<', '>No<']) assert.ok(L.exitDialog().includes(s), s);
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

test('El panel solo llama a sus rutas, al ingreso y a su salida; sus únicas escrituras son PIN y finalizar', () => {
  const calls = [...new Set([...PANEL.matchAll(/fetch\((.+?), \{/g)].map((m) => m[1].trim()))];
  assert.deepEqual(calls.sort(), ['`${API}/auth/logout`', '`${API}/companies/${encodeURIComponent(CID)}/mini-panel-login`', 'panelUrl(path)'].sort());
  assert.deepEqual([...PANEL.matchAll(/read\("(\w+)"\)/g)].map((m) => m[1]).sort(), ['crm', 'inicio']);
  assert.deepEqual([...PANEL.matchAll(/send\(["`]([^"`]+)["`]/g)].map((m) => m[1]).sort(), ['crm/${encodeURIComponent(f.id)}/finalizar', 'pin/marcar', 'pin/verificar']);
  assert.doesNotMatch(PANEL, /localStorage\.setItem\([^)]*pin|sessionStorage\.setItem\([^)]*pin/i, 'el PIN no se guarda en el navegador');
});

test('Workforce: PIN en la ficha, se ve una sola vez; sin ruta no se muestra', () => {
  const WF = readFileSync(`${WEB}workforce_v2.js`, 'utf8');
  for (const s of ['PIN de marcación (4 dígitos)', 'Generar PIN', 'Quitar', 'no vinculado', 'vinculado', 'no se volverá a mostrar', '/lider-operacion/workforce/companies/', 'data-wf2-punch-new', 'data-wf2-punch-del']) assert.ok(WF.includes(s), s);
  assert.match(WF, /e\.id && model\.punch \? /, 'solo en una ficha existente y con el servidor encendido');
  assert.match(WF, /catch \(_\) \{\n\s+model\.punch = null;/, 'apagado: 404 y no se muestra nada');
  assert.doesNotMatch(WF.slice(WF.indexOf('function punchAction')), /punchShown = data\.pin;[^]*localStorage/);
});

test('Nómina y Board del portal muestran el origen de la marca', () => {
  const USP = readFileSync(`${WEB}us_payroll.js`, 'utf8');
  assert.ok(USP.includes('m.origin === "pin"') && USP.includes('Panel PIN'));
  assert.ok(BOARD.includes('const ORIGIN = { pin: "PIN", lider: "Líder" }') && BOARD.includes('rb-origin'));
});
