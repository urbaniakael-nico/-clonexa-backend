// Consola v2+ · Ficha de empresa. Pruebas de CONTRATO de cada escritura:
// mismo endpoint, método y cuerpo que Admin V2 (y la prueba lee admin_v2.js
// para avisar si v2 cambia). Además: mini paneles solo encender/apagar,
// links iguales a v2, reset con las mismas reglas, sin configuración operativa.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/admin_v2plus_company.js', 'utf8');
const companiesSource = readFileSync('app/web/admin_v2plus_companies.js', 'utf8');
const fichaSource = readFileSync('app/web/admin_v2plus_ficha.js', 'utf8');
const v2 = readFileSync('app/web/admin_v2.js', 'utf8').replace(/\r\n/g, '\n');

function load(responder = () => ({ status: 200, body: {} })) {
  const calls = [];
  const fetch = async (url, options = {}) => {
    const call = { url, method: options.method || 'GET', body: options.body ? JSON.parse(options.body) : undefined };
    calls.push(call);
    const { status, body } = responder(call);
    return { status, ok: status >= 200 && status < 300, json: async () => body };
  };
  const window = { location: { href: '', origin: 'https://clonexa.app', hash: '' } };
  const ctx = vm.createContext({ window, document: {}, fetch, JSON, Object, Array, String, Math, Number, Promise, Error, Date, encodeURIComponent, decodeURIComponent });
  vm.runInContext(companiesSource, ctx);
  vm.runInContext(fichaSource, ctx);
  vm.runInContext(source, ctx);
  return { ui: window.CxConsoleCompany, calls };
}
const strip = (calls) => calls.map((c) => `${c.method} ${c.url} ${c.body === undefined ? '' : JSON.stringify(c.body)}`.trim());
const ID = '7625872c-f941-4479-a27b-f8443be953c5';

test('cada escritura usa el endpoint, método y cuerpo de Admin V2', async () => {
  const { ui, calls } = load();
  const w = ui.writes;
  await w.activatePackage(ID, 'restaurante');
  await w.toggleModule(ID, 'carta', 'activate');
  await w.toggleModule(ID, 'carta', 'deactivate');
  await w.createUser(ID, 'Ana', 'ana@bar.co', 'Clave-1!');
  await w.resetPassword(ID, 'u1', '');
  await w.resetPassword(ID, 'u1', 'Nueva-123');
  await w.unlockUser(ID, 'u1');
  await w.setUserStatus(ID, 'u1', 'inactive');
  await w.saveAccessPolicy(ID, { enabled: true, scopes: {} });
  await w.saveSessionPolicy(ID, { enabled: false, mode: 'replace_oldest', scopes: {} });
  await w.closeSession(ID, 'sk1');
  await w.closeAllSessions(ID);
  await w.saveTelegram(ID, { name: '  Bot  ', token: ' 123:ABC ', flow_code: 'base' });
  await w.testTelegram(ID);
  await w.activateWebhook(ID, 'velvet_references');
  await w.deactivateTelegram(ID);
  await w.operationalReset(ID, false, ['commercial'], 'asadero', '');
  await w.operationalReset(ID, true, ['commercial', 'payroll'], 'asadero', 'RESET asadero');
  assert.deepEqual(strip(calls), [
    `POST /api/v1/companies/${ID}/activate-package {"package_code":"restaurante","settings":{}}`,
    `POST /api/v1/companies/${ID}/modules/carta/activate {"settings":{}}`,
    `POST /api/v1/companies/${ID}/modules/carta/deactivate {"settings":{}}`,
    `POST /api/v1/companies/${ID}/users {"name":"Ana","full_name":"Ana","email":"ana@bar.co","password":"Clave-1!","temporary_password":"Clave-1!","role":"company_admin","status":"active","must_change_password":true}`,
    `POST /api/v1/companies/${ID}/users/u1/reset-password {}`,
    `POST /api/v1/companies/${ID}/users/u1/reset-password {"password":"Nueva-123"}`,
    `POST /api/v1/companies/${ID}/users/u1/unlock {}`,
    `PUT /api/v1/companies/${ID}/users/u1 {"status":"inactive"}`,
    `PUT /api/v1/companies/${ID}/access-policy {"enabled":true,"scopes":{}}`,
    `PUT /api/v1/companies/${ID}/session-policy {"enabled":false,"mode":"replace_oldest","scopes":{}}`,
    `POST /api/v1/companies/${ID}/access-sessions/sk1/close {}`,
    `POST /api/v1/companies/${ID}/access-sessions/close {}`,
    `PUT /api/v1/bots/companies/${ID}/telegram {"name":"Bot","token":"123:ABC"}`,
    `POST /api/v1/bots/companies/${ID}/telegram/test {}`,
    `POST /api/v1/company-bots-v1/companies/${ID}/telegram/activate-webhook {"flow_code":"velvet_references"}`,
    `POST /api/v1/bots/companies/${ID}/telegram/deactivate {}`,
    `POST /api/v1/companies/${ID}/operational-reset {"dry_run":true,"scopes":["commercial"],"confirm_slug":"asadero","confirm_text":""}`,
    `POST /api/v1/companies/${ID}/operational-reset {"dry_run":false,"scopes":["commercial","payroll"],"confirm_slug":"asadero","confirm_text":"RESET asadero"}`,
  ]);
});

test('Admin V2 sigue usando esos mismos endpoints y cuerpos', () => {
  const has = (re, label) => assert.match(v2, re, label);
  has(/apiPost\(`\$\{API\}\/companies\/\$\{companyId\}\/activate-package`, \{ package_code: packageCode, settings: \{\} \}\)/, 'F04');
  has(/cxJsonRequest\(`\/companies\/\$\{companyId\}\/modules\/\$\{moduleCode\}\/\$\{action\}`, \{\s*method: "POST",\s*body: JSON\.stringify\(\{ settings: \{\} \}\),/, 'M04');
  has(/const body = \{\s*name: fullName,\s*full_name: fullName,\s*email: email,\s*password: password,\s*temporary_password: password,\s*role: "company_admin",\s*status: "active",\s*must_change_password: true\s*\};/, 'U02');
  has(/const body = typedPassword \? \{ password: typedPassword \} : \{\};\s*const response = await apiPost\(`\$\{API\}\/companies\/\$\{companyId\}\/users\/\$\{userId\}\/reset-password`, body\)/, 'U03');
  has(/apiPost\(`\$\{API\}\/companies\/\$\{companyId\}\/users\/\$\{userId\}\/unlock`, \{\}\)/, 'U04');
  has(/apiPut\(`\$\{API\}\/companies\/\$\{companyId\}\/users\/\$\{userId\}`, \{ status \}\)/, 'U05');
  has(/apiPut\(`\$\{API\}\/companies\/\$\{companyId\}\/access-policy`, \{\s*enabled: data\.get\("enabled"\) === "on",\s*scopes,\s*\}\)/, 'A02');
  has(/apiPut\(`\$\{API\}\/companies\/\$\{companyId\}\/session-policy`, \{\s*enabled: data\.get\("enabled"\) === "on",\s*mode: String\(data\.get\("mode"\) \|\| "replace_oldest"\),\s*scopes,\s*\}\)/, 'A04');
  has(/apiPost\(`\$\{API\}\/companies\/\$\{companyId\}\/access-sessions\/\$\{sessionKey\}\/close`, \{\}\)/, 'A06');
  has(/apiPost\(`\$\{API\}\/companies\/\$\{companyId\}\/access-sessions\/close`, \{\}\)/, 'A07');
  has(/body\.token = String\(body\.token \|\| ""\)\.trim\(\);\s*body\.name = String\(body\.name \|\| ""\)\.trim\(\);\s*delete body\.flow_code;\s*[\s\S]{0,40}apiPut\(`\$\{API\}\/bots\/companies\/\$\{companyId\}\/telegram`, body\)/, 'T03');
  has(/apiPost\(`\$\{API\}\/bots\/companies\/\$\{companyId\}\/telegram\/test`, \{\}\)/, 'T04');
  has(/apiPost\(`\$\{API\}\/company-bots-v1\/companies\/\$\{companyId\}\/telegram\/activate-webhook`, \{\s*flow_code: flowCode,\s*\}\)/, 'T05');
  has(/apiPost\(`\$\{API\}\/bots\/companies\/\$\{companyId\}\/telegram\/deactivate`, \{\}\)/, 'T06');
  has(/apiPost\(`\$\{API\}\/companies\/\$\{encodeURIComponent\(companyId\)\}\/operational-reset`, \{\s*dry_run: !execute,\s*scopes,\s*confirm_slug: confirmSlug,\s*confirm_text: confirmText,\s*\}\)/, 'R01');
  has(/fetch\(`\$\{API\}\/companies\/\$\{encodeURIComponent\(companyId\)\}\/modules\/mini_panel\/activate`, \{\s*method: "POST",[\s\S]{0,120}settings: \{\s*mini_panel_modules: \{\s*enabled: config\.enabled === true,\s*selected_panel: config\.selected_panel \|\| "",\s*panels: config\.panels \|\| \{\},\s*module_names: config\.module_names \|\| \{\},\s*updated_at: new Date\(\)\.toISOString\(\)/, 'X02');
});

test('políticas: los formularios arman el mismo cuerpo que Admin V2', () => {
  const { ui } = load();
  const form = { enabled: 'on', client_enabled: 'on', client_ips: '190.1.1.1, 10.0.0.0/8\n\n 8.8.8.8 ', mini_panel_ips: '', ordering_qr_enabled: 'on', ordering_qr_ips: '1.2.3.4' };
  assert.deepEqual(JSON.parse(JSON.stringify(ui.accessPolicyBody((k) => form[k] ?? null))), {
    enabled: true,
    scopes: { client: { enabled: true, allowed_ips: ['190.1.1.1', '10.0.0.0/8', '8.8.8.8'] },
      mini_panel: { enabled: false, allowed_ips: [] }, ordering_qr: { enabled: true, allowed_ips: ['1.2.3.4'] } },
  });
  const sform = { mode: 'block_new', mini_panel_enabled: 'on', mini_panel_max: '7', client_max: '' };
  assert.deepEqual(JSON.parse(JSON.stringify(ui.sessionPolicyBody((k) => sform[k] ?? null))), {
    enabled: false, mode: 'block_new', scopes: { client: { enabled: false, max_sessions: 1 }, mini_panel: { enabled: true, max_sessions: 7 } },
  });
  assert.match(v2, /const ACCESS_POLICY_SCOPES_026G = \[\s*\["client"[^\]]*\],\s*\["mini_panel"[^\]]*\],\s*\["ordering_qr"/);
  assert.match(v2, /max_sessions: Number\(data\.get\(`\$\{code\}_max`\) \|\| 1\)/);
});

const MODULES = [
  { enabled: true, settings: {}, module: { code: 'carta', name: 'Carta' } },
  { enabled: false, settings: {}, module: { code: 'gps', name: 'GPS' } },
  { enabled: true, settings: { qr_config: { mode: 'hospitality', include_bar: false, base_url: 'https://pedidos.bar.co/ordenar/' } }, module: { code: 'hospitality_qr', name: 'QR' } },
  { enabled: true, settings: { mini_panel_modules: { enabled: true, selected_panel: 'sales', module_names: { notas: 'Notas' },
    panels: { sales: { enabled: true, link: 'https://x/mini-panel/login?company_id=a&type=sales', modules: ['notas'], max_users: 12 }, inventory: { enabled: false } } } },
    module: { code: 'mini_panel', name: 'Creacion mini panel' } },
];

test('mini paneles: solo encender/apagar, sin tocar módulos, links ni máximos', async () => {
  const { ui, calls } = load();
  const { config, present } = ui.miniPanelConfig(MODULES);
  assert.equal(present, true);
  const on = ui.toggledPanels(config, ID, 'inventory', true);
  assert.deepEqual(JSON.parse(JSON.stringify(on.panels.sales)), config.panels.sales, 'el panel de ventas queda igual');
  assert.equal(on.panels.inventory.enabled, true);
  assert.equal(on.panels.inventory.max_users, 5, 'mismo máximo por defecto que v2 (Inventario = 5)');
  assert.equal(on.panels.inventory.link, `https://clonexa.app/mini-panel/login?company_id=${ID}&type=inventory`);
  const off = ui.toggledPanels(config, ID, 'sales', false);
  assert.equal(off.panels.sales.enabled, false);
  assert.equal(off.selected_panel, 'sales', 'sin otro panel encendido, queda el mismo (regla de v2)');
  const all = ui.toggledPanels(config, ID, '*', false);
  assert.equal(all.enabled, false);
  assert.deepEqual(JSON.parse(JSON.stringify(all.panels)), config.panels);
  await ui.writes.saveMiniPanels(ID, on);
  const body = calls[0].body.settings.mini_panel_modules;
  assert.equal(calls[0].url, `/api/v1/companies/${ID}/modules/mini_panel/activate`);
  assert.deepEqual(Object.keys(body), ['enabled', 'selected_panel', 'panels', 'module_names', 'updated_at']);
  assert.deepEqual(body.module_names, { notas: 'Notas' });
});

test('mini paneles: si el servidor rechaza, la Ficha lo muestra (v2 no revisa la respuesta)', async () => {
  const { ui } = load(() => ({ status: 500, body: { detail: 'boom' } }));
  await assert.rejects(ui.writes.saveMiniPanels(ID, { panels: {} }), /boom/);
});

test('Copiar links: los mismos que arma Admin V2', () => {
  const { ui } = load();
  const links = ui.accessLinks({ id: ID }, MODULES);
  assert.deepEqual(JSON.parse(JSON.stringify(links.map((l) => `${l.title} | ${l.href}`))), [
    `Panel cliente | https://clonexa.app/client?company_id=${ID}`,
    'Login empresa | https://clonexa.app/login',
    'Mini panel Ventas | https://x/mini-panel/login?company_id=a&type=sales',
    `QR publico | https://pedidos.bar.co/ordenar?company_id=${ID}&mesa=Mesa%201`,
  ]);
  assert.match(v2, /\{ title: "Panel cliente", href: `\/client\?company_id=\$\{encodedId\}`/);
  assert.match(v2, /\{ title: "Login empresa", href: "\/login"/);
  assert.match(v2, /if \(settings\.mode === "voting"\) return "Participante 1";\s*if \(settings\.mode === "generic"\) return "QR 1";\s*return settings\.include_bar \? "Barra" : "Mesa 1";/);
});

test('reset operativo: mismas reglas que Admin V2 (alcance, slug, frase, confirmación final)', () => {
  const { ui } = load();
  const c = { slug: 'asadero', name: 'Asadero' };
  assert.equal(ui.resetPlan(c, [], '', '', false).error, 'Selecciona al menos un alcance para el reset.');
  assert.equal(ui.resetPlan(c, ['commercial'], '', '', false).error, undefined, 'la simulación no pide slug');
  assert.equal(ui.resetPlan(c, ['commercial'], 'asadero', 'RESET Asadero', true).error, 'Confirmacion invalida. Escribe RESET asadero.');
  assert.equal(ui.resetPlan(c, ['commercial'], 'asadero', 'RESET asadero', true).confirm,
    'Vas a borrar datos operativos de Asadero. La empresa, modulos, accesos y branding se conservan. Continuar?');
  assert.match(v2, /window\.confirm\(`Vas a borrar datos operativos de \$\{company\.name\}\. La empresa, modulos, accesos y branding se conservan\. Continuar\?`\)/);
  for (const scope of ['commercial', 'references', 'workforce', 'payroll', 'inventory']) assert.match(source, new RegExp(`code: "${scope}"`));
});

test('flujos del bot: las mismas opciones que botFlowOptions de Admin V2', () => {
  const { ui } = load();
  ui.model = { ...ui.model, modules: [{ enabled: true, module: { code: 'references' } }, { enabled: true, module: { code: 'workforce' } }, { enabled: true, module: { code: 'gps' } }] };
  const html = ui.botFlowOptions('velvet_references');
  assert.match(html, /value="base"/);
  assert.match(html, /value="velvet_references" selected/);
  assert.match(html, /value="field_operations"/);
  assert.doesNotMatch(html, /retail_sales|hospitality_orders/);
});

test('la Ficha no trae configuración operativa (pedidos por mesero, cocina, categorías, porciones, metas)', () => {
  for (const src of [source, fichaSource]) {
    // Ningún endpoint operativo: categorías, porciones, metas, estaciones de cocina ni imágenes.
    assert.doesNotMatch(src, /waiter-ordering|daily-goal|cocina-users|portions|\/image`|stations|quick_notes|daily_goal/);
  }
  // waiter_ordering solo aparece para encender/apagar mesero, cocina y caja (segments).
  const uses = source.match(/modules\/waiter_ordering\/[a-z]+/g) || [];
  assert.deepEqual([...new Set(uses)], ['modules/waiter_ordering/activate']);
  assert.match(source, /Configuración avanzada en Admin V2/);
  assert.match(source, /Abrir en Estudio de marca \(próximamente\)/);
});

test('la ficha dibuja encabezado, pestañas y escapa los datos', () => {
  const { ui } = load();
  ui.model = { ...ui.model, id: ID, tab: 'resumen', company: { id: ID, name: 'Bar <img src=x onerror=alert(1)>', slug: 'bar', status: 'active', settings_json: { kind: 'registrada' } },
    modules: MODULES, users: [{ id: 'u1', status: 'active' }] };
  const html = ui.view();
  assert.doesNotMatch(html, /<img src=x/);
  assert.match(html, /Bar &lt;img src=x onerror=alert\(1\)&gt;/);
  assert.match(html, /<b>Registrada<\/b> · Activa/);
  assert.match(html, /ID 7625872c ⧉/);
  for (const label of ['Entrar como empresa', 'Copiar links', 'Cerrar sesiones', 'Clonar como demo']) assert.match(html, new RegExp(label));
  for (const tab of ['Resumen', 'Paquete', 'Módulos y mini paneles', 'Usuarios y accesos', 'Bots', 'Datos', 'Marca']) assert.match(html, new RegExp(`>${tab}</button>`));
  assert.match(html, /href="\/client\?company_id=7625872c-f941-4479-a27b-f8443be953c5" target="_blank"/);
  ui.model = { ...ui.model, tab: 'marca', experience: { branding: { logo_url: 'javascript:alert(1)', primary_color: '#ff0000' } } };
  const marca = ui.view();
  assert.doesNotMatch(marca, /src="javascript:/, 'un logo que no es https ni ruta propia no se pinta');
  assert.match(marca, /data-vpf-swatch="#ff0000"/);
  assert.doesNotMatch(marca, /style=/);
});

test('ruta /admin-v2plus#empresa/{id}', () => {
  const plus = readFileSync('app/web/admin_v2plus.js', 'utf8');
  const ctx = vm.createContext({ window: {}, document: {}, Date, Math, Number, String, Array, encodeURIComponent, decodeURIComponent });
  vm.runInContext(plus, ctx);
  const route = ctx.window.CxConsolePlus.companyFromHash;
  assert.equal(route(`#empresa/${ID}`), ID);
  assert.equal(route('#empresa/x<script>'), '');
  assert.equal(route('#otra'), '');
  assert.match(plus, /href="#empresa\/\$\{encodeURIComponent\(c\.id\)\}">Ficha</);
  assert.doesNotMatch(plus, /href="\/admin-v2\?company_id=\$\{encodeURIComponent\(c\.id\)\}">Ficha/);
});

test('cada pestaña de la Ficha se dibuja sin errores, con y sin datos', () => {
  const { ui } = load();
  const company = { id: ID, name: 'Asadero', slug: 'asadero', status: 'active', settings_json: { kind: 'registrada' } };
  const full = {
    modules: MODULES, packages: [{ code: 'restaurante', name: 'Restaurante Pro' }],
    users: [{ id: 'u1', full_name: 'Ana', email: 'ana@bar.co', role: 'company_admin', status: 'active', locked_until: null, last_login_at: null }],
    accessPolicy: { enabled: true, current_ip: '1.2.3.4', scopes: { client: { enabled: true, allowed_ips: ['1.2.3.4'] } } },
    sessionPolicy: { enabled: true, mode: 'block_new', scopes: { mini_panel: { enabled: true, max_sessions: 3 } } },
    sessions: { sessions: [{ session_key: 'k1', scope: 'client', status: 'active', subject_label: 'ana@bar.co', last_seen_at: null, ip_address: '1.2.3.4' }] },
    experience: { branding: { logo_url: '/admin-v2-assets/clonexa-logo.png', primary_color: '#ff0000', font_family: 'Sora' } },
    telegram: { configured: true, webhook_mode: 'dedicated', flow_code: 'base' },
    reset: { executed: false, total_rows: 3, tables: [{ table: 'mini_panel_quotes', label: 'Cotizaciones', scope_label: 'Comercial', rows: 3 }] },
  };
  for (const [tab, needle] of [['resumen', 'Actividad · últimos 14 días'], ['paquete', 'Restaurante Pro'], ['modulos', 'Módulos de la empresa'],
    ['accesos', 'Guardar politica IP'], ['bots', 'Reinstalar webhook dedicado'], ['datos', 'Simulación lista'], ['marca', 'clonexa-logo.png']]) {
    ui.model = { ...ui.model, id: ID, company, tab, ...full };
    assert.match(ui.view(), new RegExp(needle), tab);
    ui.model = { ...ui.model, id: ID, company, tab, modules: null, packages: null, users: null, accessPolicy: null, sessionPolicy: null,
      sessions: null, experience: null, telegram: null, reset: null };
    assert.ok(ui.view().length > 100, `${tab} sin datos`);
  }
  ui.model = { ...ui.model, modal: { type: 'password', password: 'Clonexa-x-1!' } };
  assert.match(ui.view(), /value="Clonexa-x-1!" data-vpf-copy-value><button class="vp-btn vp-btn-sm" type="button" data-vpf-copy-password>Copiar/);
  ui.model = { ...ui.model, modal: { type: 'purge', company, plan: { total_rows: 1, tables: [{ table: 't', rows: 1 }] } } };
  assert.match(ui.view(), /data-vpf-c-purge-go/);
  ui.model = { ...ui.model, modal: { type: 'clone', company, password: 'x' } };
  assert.match(ui.view(), /data-vpf-c-clone-form/);
});
