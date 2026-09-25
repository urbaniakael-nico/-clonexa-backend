// Corte diario de sesiones (048Q) en el portal, Nómina, Admin V2 y mini paneles.
// Ejecuta las funciones reales de client.js y session_closure_banner.js.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');
const admin = readFileSync('app/web/admin_v2.js', 'utf8').replace(/\r\n/g, '\n');
const bannerSource = readFileSync('app/web/session_closure_banner.js', 'utf8');

function fn(name) {
  const start = source.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  var |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

function portal(metrics = {}) {
  const ctx = vm.createContext({
    h: (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
    state: { companyId: 'c1', company: { timezone: 'America/Bogota' }, dashboardMetrics: metrics },
    Intl, Date, Math, Number, String, Array, Object, JSON,
  });
  vm.runInContext('var cxSess048Q = { message: "", error: "" };\n'
    + ['cxSessLocalInput048Q', 'cxSessWhen048Q', 'cxSessClosureRowHtml048Q', 'cxSessDashboardBanner048Q',
      'cxPayCoHours048O', 'cxPayUnverifiedHtml048Q'].map(fn).join('\n'), ctx);
  return ctx;
}

const CLOSURE = {
  id: 'k1', employee_id: 'e1', employee_name: 'Ana Workforce', panel_type: 'mesero', status: 'pending', reason: 'corte_diario',
  started_at: '2026-09-24T13:00:00Z', system_end_at: '2026-09-25T05:00:00Z', declared_end_at: null,
  message: 'Ana Workforce fue desconectado por el sistema a las 00:00',
};

test('Dashboard: un aviso por persona con el nombre de Workforce y el recuadro de hora real', () => {
  const ctx = portal({ sessions048Q: { people: [{ employee_id: 'e1', employee_name: 'Ana Workforce', message: CLOSURE.message, closures: [CLOSURE, { ...CLOSURE, id: 'k2', panel_type: 'caja' }] }], live_alerts: [] } });
  const html = ctx.cxSessDashboardBanner048Q();
  assert.equal((html.match(/data-sess-person=/g) || []).length, 1);
  assert.match(html, /<strong>Ana Workforce fue desconectado por el sistema a las 00:00<\/strong>/);
  assert.match(html, /data-sess-closure="k1"[\s\S]*mesero · entrada 2026-09-24 08:00/);
  assert.match(html, /type="datetime-local" data-sess-end-048q value="" min="2026-09-24T08:00" max="2026-09-25T00:00"/);
  assert.match(html, /data-sess-confirm-048q="k2">Guardar hora real/);
  assert.match(html, /queda fija y no se puede volver a modificar\. Mientras tanto estas horas no se liquidan\./);
});

test('Dashboard: la hora declarada por el empleado se ve como sin confirmar', () => {
  const ctx = portal({ sessions048Q: { people: [{ employee_id: 'e1', message: CLOSURE.message, closures: [{ ...CLOSURE, status: 'declared', declared_end_at: '2026-09-24T22:00:00Z' }] }], live_alerts: [] } });
  const html = ctx.cxSessDashboardBanner048Q();
  assert.match(html, /Hora declarada por el empleado: 2026-09-24 17:00 \(sin confirmar\)/);
  assert.match(html, /value="2026-09-24T17:00"/);
  assert.match(html, />Confirmar hora</);
});

test('Dashboard: alerta en vivo de sesión abierta de más; sin datos no se muestra nada', () => {
  const ctx = portal({ sessions048Q: { people: [], live_alerts: [{ employee_id: 'e2', employee_name: 'Beto', panel_type: 'caja', started_at: '2026-09-25T11:00:00Z', hours_open: 13.5 }] } });
  assert.match(ctx.cxSessDashboardBanner048Q(), /data-sess-live="e2"[\s\S]*Beto lleva 13\.5 h con la sesión abierta[\s\S]*desde 2026-09-25 06:00/);
  assert.equal(portal({ sessions048Q: { people: [], live_alerts: [] } }).cxSessDashboardBanner048Q(), '');
  assert.equal(portal({}).cxSessDashboardBanner048Q(), '', 'sin permiso (403) no se ve nada');
  assert.match(source, /\$\{cxSanDashboardBanner048K\(\)\}\s*\$\{cxSessDashboardBanner048Q\(\)\}/);
  assert.match(source, /metrics\.sessions048Q = await cxSessLoad048Q\(companyId\)\.catch\(\(\) => null\);/);
});

test('Nómina: turnos sin hora real aparte, con su motivo y el ajuste', () => {
  const ctx = portal();
  const html = ctx.cxPayUnverifiedHtml048Q([
    { source: 'mini_panel', session_ref: 's1', closure_id: 'k1', status: 'pending', reason: 'corte_diario', employee_name: 'Ana Workforce', panel_type: 'mesero', start: '2026-09-24T13:00:00Z', end: '2026-09-25T05:00:00Z', minutes: 960 },
    { source: 'mini_panel', session_ref: 's2', closure_id: null, status: 'pending', reason: 'historico_largo', employee_name: 'Carla', panel_type: 'sales', start: '2026-09-01T13:00:00Z', end: '2026-09-03T13:00:00Z', minutes: 2880 },
  ]);
  assert.match(html, /Turnos sin hora real de salida: 64 h fuera de la liquidación/);
  assert.match(html, /Ana Workforce · mesero · corte diario del sistema · entrada 2026-09-24 08:00 · cierre 2026-09-25 00:00 · 16 h/);
  assert.match(html, /data-sess-closure="" data-sess-source="mini_panel" data-sess-ref="s2"[\s\S]*turno larguísimo \(histórico\)/);
  assert.equal(ctx.cxPayUnverifiedHtml048Q([]), '');
  assert.match(source, /unverified: payload\.unverified_shifts \|\| \[\],/);
  assert.doesNotMatch(source, /auto_closed_shifts/);
});

test('Admin V2: hora del corte y alerta por empresa', () => {
  assert.match(admin, /\$\{cxSessPolicyPanel048Q\(company\)\}/);
  assert.match(admin, /cxJsonRequest\(`\/workforce-sessions\/companies\/\$\{encodeURIComponent\(id\)\}\/policy`, \{\s*method: "PUT"/);
  assert.match(admin, /<input type="time" name="cutoff_time" value="\$\{escapeHtml\(data\.cutoff_time \|\| "00:00"\)\}">/);
});

function runBanner({ search, token, closures, keys }) {
  const appended = [];
  const listeners = {};
  const requests = [];
  const storage = { getItem: (key) => (key === token.key ? token.value : null) };
  const document = {
    currentScript: { getAttribute: () => keys },
    readyState: 'complete',
    body: { appendChild: (el) => appended.push(el) },
    createElement: () => ({ innerHTML: '', remove() {}, contains: () => true }),
    addEventListener: (type, cb) => { listeners[type] = cb; },
  };
  const window = {
    location: { search },
    localStorage: storage,
    sessionStorage: { getItem: () => null },
    setInterval: () => 0,
  };
  const ctx = vm.createContext({
    window, document, URLSearchParams, Intl, Date, JSON, String, Number, Array, encodeURIComponent,
    fetch: async (url, options) => {
      requests.push({ url, options });
      return { ok: true, json: async () => ({ closures }) };
    },
  });
  vm.runInContext(bannerSource, ctx);
  return { appended, requests, listeners };
}

test('mini panel: el empleado ve su cierre y solo puede proponer la hora', async () => {
  const run = runBanner({
    search: '?company_id=c1&type=sales', keys: 'clonexa_mini_panel_token_{cid}_{type}',
    token: { key: 'clonexa_mini_panel_token_c1_sales', value: 'tok' }, closures: [CLOSURE],
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(run.requests[0].url, '/api/v1/workforce-sessions/companies/c1/closures/mine');
  assert.equal(run.requests[0].options.headers.Authorization, 'Bearer tok');
  const html = run.appended[0].innerHTML;
  assert.match(html, /Ana Workforce fue desconectado por el sistema a las 00:00/);
  assert.match(html, /El administrador debe confirmarla antes de que cuente para tu pago/);
  assert.match(html, /data-cx-sess-declare="k1"[^>]*>Enviar mi hora de salida/);
  assert.match(html, /min="2026-09-24T08:00" max="2026-09-25T00:00"/);
  assert.doesNotMatch(bannerSource, /closures\/confirm/, 'el empleado nunca confirma');
  for (const page of ['hsp_waiter', 'hsp_cashier', 'mini_panel']) {
    assert.match(readFileSync(`app/web/${page}.html`, 'utf8'), /session_closure_banner\.js\?v=048Q" data-token-keys="clonexa_/);
  }
});

function fnFrom(file, name) {
  const src = readFileSync(file, 'utf8').replace(/\r\n/g, '\n');
  const start = src.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, `${file}:${name}`);
  const tail = src.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  var |\n  \/\/ /);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

const CUT_401 = { status: 401, ok: false, json: async () => ({ detail: 'Corte diario del sistema: vuelve a entrar con tu usuario y clave.' }) };

test('reingreso: la cocina vuelve al login con cualquier 401 de sesión, no solo "otro dispositivo"', async () => {
  const calls = [];
  const ctx = vm.createContext({
    state: { screen: 'board', error: '' },
    token: () => 'tok', setToken: (v) => calls.push(['setToken', v]), stopPolling: () => calls.push(['stop']),
    render: () => calls.push(['render']), fetch: async () => CUT_401, String, Object,
  });
  vm.runInContext(fnFrom('app/web/hsp_kitchen.js', 'api'), ctx);
  await assert.rejects(ctx.api('/x'));
  assert.equal(ctx.state.screen, 'login');
  assert.match(ctx.state.error, /corte diario\. Vuelve a entrar con tu usuario y clave/);
  assert.deepEqual(calls.map((c) => c[0]), ['stop', 'setToken', 'render']);
  // Sin sesion (p. ej. clave errada en el login) no se hace nada raro.
  const ctx2 = vm.createContext({ state: { screen: 'login', error: '' }, token: () => '', setToken() {}, stopPolling() {}, render() {}, fetch: async () => CUT_401, String, Object });
  vm.runInContext(fnFrom('app/web/hsp_kitchen.js', 'api'), ctx2);
  await assert.rejects(ctx2.api('/login'));
  assert.equal(ctx2.state.error, '');
});

test('reingreso: el mini panel (CRM) lleva al login de siempre con el motivo', async () => {
  const cleared = [];
  const ctx = vm.createContext({
    isLogin: false, window: { location: { href: '' } }, clearMiniPanelToken024B: () => cleared.push(1),
    loginUrl: () => '/mini-panel/login?company_id=c1&type=sales', fetch: async () => CUT_401, encodeURIComponent, Boolean,
  });
  vm.runInContext('let sessionLost048Q = false;\n' + fnFrom('app/web/mini_panel.js', 'hasAuthHeader048Q') + fnFrom('app/web/mini_panel.js', 'api'), ctx);
  await assert.rejects(ctx.api('/x', { headers: { Authorization: 'Bearer tok' } }));
  assert.equal(ctx.window.location.href, '/mini-panel/login?company_id=c1&type=sales&motivo=Corte%20diario%20del%20sistema%3A%20vuelve%20a%20entrar%20con%20tu%20usuario%20y%20clave.');
  assert.equal(cleared.length, 1);
  await assert.rejects(ctx.api('/y', { headers: { Authorization: 'Bearer tok' } }));
  assert.equal(cleared.length, 1, 'redirige una sola vez');
  const mini = readFileSync('app/web/mini_panel.js', 'utf8');
  assert.match(mini, /if \(isLogin\) \{\s*renderLogin\(params\.get\("motivo"\) \|\| ""\);/);
});

test('reingreso: mesero y caja vuelven al login con mensaje del corte', () => {
  for (const file of ['app/web/hsp_waiter.js', 'app/web/hsp_cashier.js']) {
    const ctx = vm.createContext({ String });
    vm.runInContext(fnFrom(file, 'sessionLostMessage'), ctx);
    assert.equal(ctx.sessionLostMessage('Corte diario del sistema: vuelve a entrar con tu usuario y clave.'),
      'El sistema cerró tu turno en el corte diario. Vuelve a entrar con tu usuario y clave.');
    assert.match(readFileSync(file, 'utf8'), /if \(response\.status === 401 && tok && !options\.isLogin\) \{\s*handleSessionLost\(message\);/);
  }
});
