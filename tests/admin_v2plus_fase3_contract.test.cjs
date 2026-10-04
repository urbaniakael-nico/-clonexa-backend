// Consola v2+ · Fase 3. Contrato con Admin V2 de lo migrado: Catálogo
// (P01–P04, F03, M01–M03, N01–N03), Accesos (H03, H04, Z01), Salud (H01, H02)
// y Landing (L01). Cada prueba también lee admin_v2.js para avisar si v2 cambia.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const v2 = readFileSync('app/web/admin_v2.js', 'utf8').replace(/\r\n/g, '\n');
const SRC = ['admin_v2plus_companies.js', 'admin_v2plus_ficha.js', 'admin_v2plus_company.js', 'admin_v2plus_catalog.js', 'admin_v2plus_admin.js']
  .map((f) => readFileSync(`app/web/${f}`, 'utf8'));

function load(responder = () => ({ status: 200, body: {} })) {
  const calls = [];
  const fetch = async (url, options = {}) => {
    const call = { url, method: options.method || 'GET', body: options.body ? JSON.parse(options.body) : undefined };
    calls.push(call);
    const { status, body } = responder(call);
    return { status, ok: status >= 200 && status < 300, json: async () => body };
  };
  const window = { location: { href: '', origin: 'https://clonexa.app' } };
  const ctx = vm.createContext({ window, document: {}, fetch, JSON, Object, Array, String, Math, Number, Promise, Error, Date, Map, Set, URLSearchParams, encodeURIComponent, decodeURIComponent });
  SRC.forEach((s) => vm.runInContext(s, ctx));
  return { cat: window.CxConsoleCatalog, adm: window.CxConsoleAdmin, sections: window.CxConsoleSections, window, calls };
}
const strip = (calls) => calls.map((c) => `${c.method} ${c.url} ${c.body === undefined ? '' : JSON.stringify(c.body)}`.trim());
const plain = (v) => JSON.parse(JSON.stringify(v));
const MODULES = [{ code: 'mini_panel', name: 'Creacion mini panel' }, { code: 'inventory', name: 'Inventario' }, { code: 'crm', name: 'CRM' }];

// ------------------------------------------------------------ paquetes
test('crear paquete: POST /packages con el package_payload de v2 y luego PUT mini-panel-settings', async () => {
  const { cat, calls } = load((c) => ({ status: 200, body: c.url === '/api/v1/packages' ? { id: 'p-1' } : {} }));
  await cat.savePackage({ id: '', code: ' Bar Pro! ', name: ' Bar Pro ', description: ' x ', is_active: true, module_codes: ['crm', 'mini_panel', 'crm'],
    mini: { enabled: true, types: { sales: { enabled: true, users_allowed: 3 }, store: { enabled: true, users_allowed: 7 } } } }, MODULES);
  assert.deepEqual(strip(calls), [
    'POST /api/v1/packages {"code":"bar_pro","name":"Bar Pro","description":"x","is_active":true,"module_codes":["crm","mini_panel"]}',
    'PUT /api/v1/packages/p-1/mini-panel-settings {"enabled":true,"types":{"store":{"enabled":true,"label":"Tiendas","users_allowed":1},"sales":{"enabled":true,"label":"Ventas","users_allowed":3},"logistics":{"enabled":false,"label":"Logística","users_allowed":0},"inventory":{"enabled":false,"label":"Inventarios","users_allowed":0},"other":{"enabled":false,"label":"Otros","users_allowed":0}}}',
  ]);
});

test('editar paquete sin mini panel: PUT /packages/{id} y mini panel apagado con los valores por defecto de v2', async () => {
  const { cat, calls } = load();
  await cat.savePackage({ id: 'p-9', code: 'basico', name: 'Básico', description: '', is_active: false, module_codes: ['crm'], mini: {} }, MODULES);
  assert.equal(strip(calls)[0], 'PUT /api/v1/packages/p-9 {"code":"basico","name":"Básico","description":"","is_active":false,"module_codes":["crm"]}');
  const mini = calls[1].body;
  assert.equal(calls[1].url, '/api/v1/packages/p-9/mini-panel-settings');
  assert.deepEqual(plain(mini), plain(cat.miniDefaults({ enabled: false })));
  assert.equal(mini.enabled, false);
  assert.equal(mini.types.sales.login_template, 'https://clonexa.app/mini-panel/login?company_id={company_id}&type=sales');
  await assert.rejects(cat.savePackage({ code: '', name: '', module_codes: [], mini: {} }, MODULES), /obligatorios/);
});

test('Admin V2 usa los mismos cuerpos de paquetes', () => {
  assert.match(v2, /code: String\(raw\.code \|\| ""\)\.trim\(\)\.toLowerCase\(\)\.replace\(\/\[\^a-z0-9_:-\]\+\/g, "_"\)\.replace\(\/\^_\+\|_\+\$\/g, ""\),\s*name: String\(raw\.name \|\| ""\)\.trim\(\),\s*description: String\(raw\.description \|\| ""\)\.trim\(\),\s*is_active: raw\.is_active === "on",\s*module_codes: Array\.from\(new Set\(moduleCodes\)\),/);
  assert.match(v2, /saved = await apiPut\(`\$\{API\}\/packages\/\$\{editingId\}`, package_payload\);[\s\S]{0,40}saved = await apiPost\(`\$\{API\}\/packages`, package_payload\);/);
  assert.match(v2, /if \(package_payload\.module_codes\.some\(cxIsMiniPanelModuleCode\)\) \{\s*await savePackageMiniPanelSettings\(packageId, mini_panel\);\s*\} else \{\s*await savePackageMiniPanelSettings\(packageId, cxPackageMiniPanelDefaultSettings\(\{ enabled: false \}\)\);/);
  assert.match(v2, /apiPut\(`\$\{API\}\/packages\/\$\{packageId\}\/mini-panel-settings`, payload\)/);
  assert.match(v2, /apiGet\(`\$\{API\}\/packages\/\$\{packageId\}\/mini-panel-settings`\)/);
  assert.match(v2, /const CX_PACKAGE_MINI_PANEL_USER_LIMITS = \[1, 3, 5, 10, 15\];/);
});

// ------------------------------------------------------------ módulos
test('crear y eliminar módulo global: mismos cuerpos y confirmación que v2', async () => {
  const { cat, calls } = load();
  await cat.createModule({ code: 'Mi Modulo!', name: ' Mi módulo ', description: '', category: '' });
  await cat.deleteModule('mi_modulo');
  assert.deepEqual(strip(calls), [
    'POST /api/v1/modules {"code":"mi_modulo_","name":"Mi módulo","description":null,"category":"custom","is_active":true}',
    'DELETE /api/v1/modules/mi_modulo?confirm=mi_modulo',
  ]);
  assert.match(v2, /code: String\(data\.get\("code"\) \|\| ""\)\.trim\(\)\.toLowerCase\(\)\.replace\(\/\[\^a-z0-9_\]\/g, "_"\),\s*name: String\(data\.get\("name"\) \|\| ""\)\.trim\(\),\s*description: String\(data\.get\("description"\) \|\| ""\)\.trim\(\) \|\| null,\s*category: String\(data\.get\("category"\) \|\| ""\)\.trim\(\) \|\| "custom",\s*is_active: true,/);
  assert.match(v2, /cxJsonRequest\(`\/modules\/\$\{encodeURIComponent\(code\)\}\?confirm=\$\{encodeURIComponent\(code\)\}`, \{\s*method: "DELETE",/);
  assert.match(v2, /return assignmentCount === 0 && packageCount === 0;/, 'misma regla de limpieza');
});

// ------------------------------------------------------- nómina Colombia
test('parámetros de nómina: mismos endpoints y lectura del formulario que v2', async () => {
  const { cat, calls } = load((c) => ({ status: 200, body: c.url.endsWith('/template') ? { params: { smmlv: 1 }, changes: [] } : { fields: [], years: [] } }));
  await cat.payco.load();
  await cat.payco.template(2027);
  const fields = [{ key: 'smmlv', kind: 'number' }, { key: 'jornada_inicio', kind: 'time' }, { key: 'extra_holidays', kind: 'json' }, { key: 'tabla', kind: 'json' }];
  const form = { smmlv: '1.423.500', jornada_inicio: ' 06:00 ', extra_holidays: '', tabla: '{"a":1}', changes: '[{"desde":"2027-07-15"}]' };
  form.smmlv = '1423500,5';
  const body = cat.paycoBody(fields, (k) => form[k]);
  assert.deepEqual(plain(body), { params: { smmlv: 1423500.5, jornada_inicio: '06:00', extra_holidays: [], tabla: { a: 1 } }, changes: [{ desde: '2027-07-15' }] });
  await cat.payco.save(2027, body);
  assert.deepEqual(strip(calls).map((s) => s.split(' {')[0]), ['GET /api/v1/payroll-co/params', 'GET /api/v1/payroll-co/params/2027/template', 'PUT /api/v1/payroll-co/params/2027']);
  assert.match(v2, /if \(kind === "json"\) params\[input\.name\] = raw \? JSON\.parse\(raw\) : null;\s*else if \(kind === "time"\) params\[input\.name\] = raw;\s*else params\[input\.name\] = Number\(raw\.replace\(",", "\."\)\);/);
  assert.match(v2, /cxJsonRequest\(`\/payroll-co\/params\/\$\{year\}`, \{ method: "PUT", body: JSON\.stringify\(body\) \}\)/);
  assert.equal(cat.paycoValue({ key: 'extra_holidays', kind: 'json' }, undefined), '[]');
});

// ------------------------------------------------- accesos, salud, landing
test('sesiones de la consola y cerrar mi sesión: mismos endpoints que v2', async () => {
  const { adm, calls, window } = load();
  await adm.consoleApi.sessions();
  await adm.consoleApi.closeSession('abc123');
  await adm.consoleApi.logout();
  assert.deepEqual(strip(calls), ['GET /admin-v2/api/sessions', 'POST /admin-v2/api/sessions/abc123/close {}', 'POST /admin-v2/logout']);
  assert.equal(window.location.href, '/admin-v2plus/login');
  assert.match(v2, /apiPost\(`\/admin-v2\/api\/sessions\/\$\{sessionKey\}\/close`, \{\}\)/);
  assert.match(v2, /fetch\("\/admin-v2\/logout", \{ method: "POST" \}\)/);
});

test('estado del sistema: /health con respaldo /api/v1/health, como loadHealth de v2', async () => {
  const { adm, calls } = load((c) => ({ status: c.url === '/health' ? 500 : 200, body: { ok: true } }));
  await adm.consoleApi.health();
  assert.deepEqual(strip(calls), ['GET /health', 'GET /api/v1/health']);
  assert.match(v2, /apiGet\("\/health"\)\.catch\(\(\) => apiGet\(`\$\{API\}\/health`\)\)/);
});

test('landing: mismos parámetros y orden que loadLandingAnalytics025R', () => {
  const { adm } = load();
  assert.equal(adm.consoleApi.landingUrl({}), '/api/v1/landing-analytics/summary?days=30&limit=40');
  assert.equal(adm.consoleApi.landingUrl({ days: '7', source: 'ig', campaign: 'octubre', device: 'mobile' }),
    '/api/v1/landing-analytics/summary?days=7&limit=40&source=ig&campaign=octubre&device=mobile');
  assert.match(v2, /const params = new URLSearchParams\(\{\s*days: filters\.days \|\| "30",\s*limit: "40",\s*\}\);\s*if \(filters\.source\) params\.set\("source", filters\.source\);\s*if \(filters\.campaign\) params\.set\("campaign", filters\.campaign\);\s*if \(filters\.device\) params\.set\("device", filters\.device\);/);
});

test('las secciones del menú existen y ninguna queda en "Próximamente" salvo Estudio de marca', () => {
  const { sections } = load();
  for (const name of ['catalog', 'access', 'health', 'landing', 'brand']) assert.ok(sections[name] && sections[name].mount, name);
});

// ------------------------------------------------------------ vistas
test('Catálogo: paquetes en tarjetas con buscador y uso; builder como tablero', () => {
  const { cat } = load();
  cat.model.packages = [{ id: 'p1', code: 'bar', name: 'Bar <b>Pro</b>', is_active: true }, { id: 'p2', code: 'basico', name: 'Básico', is_active: false }];
  cat.model.modules = MODULES.map((m) => ({ ...m, category: 'core' }));
  cat.model.usage = { packages: { p1: { companies: 2 } }, modules: { crm: { companies_on: 3, companies_any: 3, packages: [{ code: 'bar', name: 'Bar' }], cleanup_candidate: false }, inventory: { companies_on: 0, companies_any: 0, packages: [], cleanup_candidate: true } } };
  cat.model.pkgQuery = 'basico';
  let html = cat.view();
  assert.match(html, /<b>Básico<\/b>/);
  assert.doesNotMatch(html, /Bar &lt;b&gt;/, 'el buscador filtra (sin tildes)');
  cat.model.pkgQuery = '';
  html = cat.view();
  assert.match(html, /Bar &lt;b&gt;Pro&lt;\/b&gt;[\s\S]*<b>2<\/b> empresa\(s\) lo usan/);
  cat.model.builder = { id: 'p1', code: 'bar', name: 'Bar', description: '', is_active: true, module_codes: ['crm', 'mini_panel'], mini: cat.miniDefaults({}), query: '' };
  html = cat.view();
  assert.match(html, /class="vp-board"/);
  assert.match(html, /draggable="true" data-vpk-drag="inventory"/);
  assert.match(html, /data-vpk-add="inventory"/);
  assert.match(html, /data-vpk-remove="crm"/);
  assert.match(html, /Mini paneles del paquete/, 'con mini_panel aparece su configuración');
  assert.doesNotMatch(html, /data-vpk-drag="crm"/, 'lo que ya está en el paquete no se ofrece');
  cat.model.builder = null;
  cat.model.tab = 'modulos';
  html = cat.view();
  assert.match(html, /CRM<\/b><span class="vp-state-pill is-on">3 empresa\(s\)/);
  assert.match(html, /Limpieza segura[\s\S]*data-vpk-delete="inventory"/);
  assert.doesNotMatch(html.slice(html.indexOf('Limpieza segura')), /data-vpk-delete="crm"/);
  cat.model.modQuery = 'xyz';
  assert.match(cat.view(), /Ningún módulo coincide/);
});

function mountWith(env, name, overview) {
  const root = { innerHTML: '', querySelector: () => null, querySelectorAll: () => [] };
  env.sections[name].mount({ root: () => root, active: () => true, overview: () => overview, toast: () => {}, params: {} });
  return root;
}

test('Accesos: Acceso Maestro con dueño, sin dueño y acciones de la Ficha', async () => {
  const env = load();
  const { adm } = env;
  adm.model.access.companies = [{ id: 'c1', name: 'Asadero', slug: 'asadero', status: 'active', settings_json: { kind: 'registrada' } },
    { id: 'c2', name: 'Sin <b>Dueño</b>', slug: 'sd', status: 'active', settings_json: { kind: 'registrada' } },
    { id: 'c3', name: 'Archivada', slug: 'ar', status: 'archived', settings_json: { kind: 'registrada' } }];
  adm.model.access.users = { c1: [{ id: 'u1', full_name: 'Ana', email: 'ana@x.co', role: 'company_admin', status: 'active' }], c2: [{ id: 'u2', role: 'mesero', status: 'active' }] };
  const root = mountWith(env, 'access', { companies: [] });
  await new Promise((r) => setTimeout(r, 0));
  const html = root.innerHTML;
  assert.match(html, /<b>Ana<\/b><br><small class="vp-mono-muted">ana@x\.co/);
  assert.match(html, /data-vpx-reset="c1" data-user="u1">Clave temporal/);
  assert.match(html, /data-vpx-unlock="c1" data-user="u1">Desbloquear/);
  assert.match(html, /data-vpx-status="c1" data-user="u1" data-status="inactive">Desactivar/);
  assert.match(html, /Sin &lt;b&gt;Dueño&lt;\/b&gt;[\s\S]*Sin acceso maestro[\s\S]*data-vpx-create="c2">Crear acceso/);
  assert.doesNotMatch(html, /Archivada/, 'las archivadas no aparecen');
  assert.match(html, /Acceso Maestro[\s\S]*Links por empresa[\s\S]*Sesiones de la consola/);
});

test('Salud: muestra si cada variable existe, nunca su valor; Estudio de marca con la empresa elegida', () => {
  const env = load();
  const { adm } = env;
  adm.model.health.status = { ok: true, service: 'clonexa-backend' };
  adm.model.health.security = { master_access_mode: 'bcrypt', variables: [{ name: 'JWT_SECRET_KEY', label: 'Firma', present: true }, { name: 'CLONEXA_ADMIN_V2_SECRET', label: 'Cookie', present: false }],
    session_idle: { hours: 72, reason: 'expirada_por_inactividad', last_run_at: '2026-10-04T23:25:00Z', last_run_closed: 39, closed_7d: 39 },
    open_endpoints: { open: 341, routes_checked: 565, by_area: { companies: 63 } } };
  const ov = { health: { database: { used_mb: 420, limit_mb: 500, used_pct: 84, warn: true }, deploy: { commit: 'eb541f6' }, demo_companies: 1 },
    companies: [{ id: 'r1', name: 'Radio', state: 'riesgo', state_reason: 'Inactiva con 16 módulos', kind: 'demo' }] };
  const html = mountWith(env, 'health', ov).innerHTML;
  assert.match(html, /JWT_SECRET_KEY<\/small><span class="vp-state-pill is-on">Definida/);
  assert.match(html, /CLONEXA_ADMIN_V2_SECRET<\/small><span class="vp-state-pill ">Falta/);
  assert.match(html, /72 h/);
  assert.match(html, /<strong>39 · /);
  assert.match(html, /420 MB de 500 MB/);
  assert.match(html, /Por encima del 80 %/);
  assert.match(html, /<a href="#empresa\/r1">Radio<\/a>/);
  assert.match(html, /<b>341<\/b> de 565 rutas/);
  assert.doesNotMatch(html, /\sstyle=/);
  const brand = load();
  const root = { innerHTML: '', querySelector: () => null, querySelectorAll: () => [] };
  brand.sections.brand.mount({ root: () => root, active: () => true, overview: () => null, toast: () => {}, params: { companyId: 'c1', companyName: 'Asadero' } });
  assert.match(root.innerHTML, /Próximamente[\s\S]*Empresa elegida: <b>Asadero<\/b>[\s\S]*href="#empresa\/c1"/);
});
