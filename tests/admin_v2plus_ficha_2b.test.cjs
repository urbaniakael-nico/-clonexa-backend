// Consola v2+ · Ficha 2b: Resumen visual, tablero de Módulos y mini paneles,
// y Usuarios y accesos sin el chorro de sesiones.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const fichaSource = readFileSync('app/web/admin_v2plus_ficha.js', 'utf8');
const companySource = readFileSync('app/web/admin_v2plus_company.js', 'utf8');
const companiesSource = readFileSync('app/web/admin_v2plus_companies.js', 'utf8');
const ID = 'f8503267-0111-46b4-84c5-ee339cc6273e';
const plain = (value) => JSON.parse(JSON.stringify(value));

function load() {
  const calls = [];
  const fetch = async (url, options = {}) => {
    calls.push({ url, method: options.method || 'GET', body: options.body ? JSON.parse(options.body) : undefined });
    return { status: 200, ok: true, json: async () => ({}) };
  };
  const window = { location: { href: '', origin: 'https://clonexa.app', hash: '' } };
  const ctx = vm.createContext({ window, document: {}, fetch, JSON, Object, Array, String, Math, Number, Promise, Error, Date, Map, Set, encodeURIComponent, decodeURIComponent });
  vm.runInContext(companiesSource, ctx);
  vm.runInContext(fichaSource, ctx);
  vm.runInContext(companySource, ctx);
  return { f: window.CxFicha, company: window.CxConsoleCompany, calls };
}

const MODULES = [
  { enabled: true, settings: {}, module: { code: 'inventory', name: 'Inventario', category: 'inventory' } },
  { enabled: true, settings: {}, module: { code: 'cotizaciones', name: 'Cotizaciones', category: 'sales' } },
  { enabled: false, settings: {}, module: { code: 'gps', name: 'GPS Campo', category: 'operations' } },
  { enabled: true, settings: {}, module: { code: 'core', name: 'Núcleo', category: 'core' } },
  { enabled: true, settings: {}, module: { code: 'hospitality', name: 'Gestión de Mesas', category: 'hospitality' } },
  { enabled: true, module: { code: 'waiter_ordering', name: 'Pedidos por mesero', category: 'hospitality' },
    settings: { stations: ['parrilla'], waiter_user_limit: 8, segments: { mesero: { enabled: true, modules: ['notas'], extra: 1 }, caja: { enabled: false } } } },
  { enabled: true, settings: {}, module: { code: 'domicilios_whatsapp', name: 'Domicilios por WhatsApp', category: 'hospitality' } },
  { enabled: true, module: { code: 'mini_panel', name: 'Creacion mini panel', category: 'core' },
    settings: { mini_panel_modules: { enabled: true, selected_panel: 'sales', module_names: { notas: 'Notas' }, clave_futura: { x: 1 },
      panels: { sales: { enabled: true, link: 'https://x/mp?type=sales', modules: ['notas'], max_users: 12, custom: 'se conserva' } } } } },
];

// ------------------------------------------------------------ buscador
test('buscador: tildes, mayúsculas, coincidencia parcial y sin resultados', () => {
  const { f } = load();
  const codes = (q, filter = 'todos') => plain(f.filterModules(MODULES, q, filter).map((m) => m.code));
  assert.deepEqual(codes('inven'), ['inventory'], 'parcial');
  assert.deepEqual(codes('INVENTARIO'), ['inventory'], 'mayúsculas');
  assert.deepEqual(codes('gestion mesas'), ['hospitality'], 'sin tilde contra "Gestión"');
  assert.deepEqual(codes('núcleo'), ['core', 'mini_panel'], 'con tilde contra la categoría "Núcleo"');
  assert.deepEqual(codes('waiter'), ['waiter_ordering'], 'por código');
  assert.deepEqual(codes('restaurante').sort(), ['domicilios_whatsapp', 'hospitality', 'waiter_ordering'], 'por categoría');
  assert.deepEqual(codes('zzz'), []);
  assert.deepEqual(codes('', 'apagados'), ['gps']);
  assert.equal(codes('', 'encendidos').length, 7);
  const html = f.modulesZone(MODULES, { query: 'zzz', filter: 'todos', collapsed: {} });
  assert.match(html, /Ningún módulo coincide con «zzz»/);
  const zone = f.modulesZone(MODULES, { query: '', filter: 'todos', collapsed: { Restaurante: true } });
  assert.match(zone, /data-vpf-mod-filter="encendidos"[^>]*>Encendidos<b>7<\/b>/);
  assert.match(zone, /aria-expanded="false">▸ Restaurante/, 'grupo plegado');
  assert.doesNotMatch(zone, /Gestión de Mesas/, 'el grupo plegado no muestra sus tarjetas');
});

test('cada tarjeta muestra nombre, código e interruptor inconfundible', () => {
  const { f } = load();
  const html = f.modulesZone(MODULES, { query: '', filter: 'todos', collapsed: {} });
  assert.match(html, /<b>Inventario<\/b><small class="vp-mono">inventory<\/small>/);
  assert.match(html, /class="vp-switch-btn is-on" type="button" role="switch" aria-checked="true" aria-label="Apagar Inventario"\s+data-vpf-module="inventory" data-action="deactivate"/);
  assert.match(html, /class="vp-switch-btn " type="button" role="switch" aria-checked="false" aria-label="Encender GPS Campo"\s+data-vpf-module="gps" data-action="activate"/);
  assert.match(html, /draggable="true" data-vpf-drag="inventory"/);
  assert.doesNotMatch(html, /data-vpf-drag="gps"/, 'un módulo apagado no se arrastra');
  assert.doesNotMatch(html, /data-vpf-drag="core"/, 'un módulo base no se arrastra');
});

// ------------------------------------------------------------ asignar
test('asignar y quitar produce el mismo cuerpo que la Ficha para el mismo resultado y conserva claves desconocidas', async () => {
  const { f, company, calls } = load();
  const start = company.miniPanelConfig(MODULES).config;
  // Resultado final: Inventario y Cotizaciones en Ventas, luego se quita Notas.
  let draft = f.assignModule(start, 'sales', f.moduleList(MODULES).find((m) => m.code === 'inventory')).config;
  draft = f.assignModule(draft, 'sales', f.moduleList(MODULES).find((m) => m.code === 'cotizaciones')).config;
  draft = f.unassignModule(draft, 'sales', 'notas');
  assert.deepEqual(plain(draft.panels.sales.modules), ['inventory', 'cotizacion'], 'código canónico igual que v2 (cotizaciones → cotizacion)');
  assert.equal(draft.panels.sales.link, 'https://x/mp?type=sales');
  assert.equal(draft.panels.sales.max_users, 12);
  assert.equal(draft.panels.sales.custom, 'se conserva');
  assert.deepEqual(plain(draft.module_names), { notas: 'Notas', inventory: 'Inventario', cotizacion: 'Cotizaciones' });
  assert.deepEqual(plain(start.panels.sales.modules), ['notas'], 'el borrador nunca toca el original');

  await company.writes.saveMiniPanels(ID, draft);
  const [call] = calls;
  assert.equal(call.method, 'POST');
  assert.equal(call.url, `/api/v1/companies/${ID}/modules/mini_panel/activate`, 'mismo endpoint de siempre');
  const body = call.body.settings.mini_panel_modules;
  const expected = plain(f.miniPanelsBody(draft, body.updated_at)).settings.mini_panel_modules;
  assert.deepEqual(body, expected);
  for (const key of ['enabled', 'selected_panel', 'panels', 'module_names', 'updated_at']) assert.ok(key in body, key);
  assert.deepEqual(body.clave_futura, { x: 1 }, 'una clave que la consola no conoce se conserva');
  assert.deepEqual(Object.keys(call.body), ['settings']);
});

test('un módulo apagado (o base) no se puede asignar', () => {
  const { f, company } = load();
  const start = company.miniPanelConfig(MODULES).config;
  const off = f.assignModule(start, 'sales', f.moduleList(MODULES).find((m) => m.code === 'gps'));
  assert.match(off.error, /Solo se asignan módulos encendidos/);
  assert.equal(off.config, start, 'no cambia nada');
  const base = f.assignModule(start, 'sales', f.moduleList(MODULES).find((m) => m.code === 'core'));
  assert.match(base.error, /base/);
  const pick = f.picker(MODULES, { pick: 'sales', pickQuery: '' });
  assert.match(pick, /GPS Campo<\/b><small class="vp-mono">gps · Apagado en la empresa<\/small>\s*<button class="vp-btn vp-btn-sm" type="button" data-vpf-assign="gps" disabled>/);
  assert.match(pick, /data-vpf-assign="inventory" >Añadir/);
  assert.match(f.picker(MODULES, { pick: 'sales', pickQuery: 'zzz' }), /Ningún módulo coincide/);
});

test('asignar a un panel que no existía lo crea con el link y el máximo por defecto de v2', () => {
  const { f, company } = load();
  const start = company.miniPanelConfig(MODULES).config;
  const { config } = f.assignModule(start, 'inventory', f.moduleList(MODULES).find((m) => m.code === 'inventory'), { companyId: ID, origin: 'https://clonexa.app' });
  assert.deepEqual(plain(config.panels.inventory), { enabled: false, link: `https://clonexa.app/mini-panel/login?company_id=${ID}&type=inventory`, modules: ['inventory'], max_users: 5 });
  const on = f.setPanelEnabled(config, 'inventory', true, { companyId: ID, origin: 'https://clonexa.app' });
  assert.equal(on.panels.inventory.enabled, true);
  assert.deepEqual(plain(on.panels.inventory.modules), ['inventory']);
});

test('mapa de paneles: restaurante y generales, chips con ×, guardar solo con cambios', () => {
  const { f, company } = load();
  const config = company.miniPanelConfig(MODULES).config;
  const data = { config, present: true, counts: { mesero: { users: 3 }, caja: { users: 1 }, sales: { users: 2 } },
    rest: f.restaurantState(MODULES), companyId: ID, origin: 'https://clonexa.app', ui: { dirty: false } };
  const html = f.panelsZone(data);
  assert.match(html, /<h3 class="vp-subtitle">Restaurante<\/h3>/);
  for (const label of ['Mesero', 'Cocina', 'Caja', 'Domicilios', 'Ventas', 'Tiendas', 'Inventario', 'Logística', 'Call center', 'Externo', 'Otro']) {
    assert.match(html, new RegExp(`<b>${label}</b>`), label);
  }
  const card = (type) => html.slice(html.indexOf(`="${type}"`), html.indexOf('</article>', html.indexOf(`="${type}"`)));
  assert.match(card('mesero'), /Encendido[\s\S]*3 usuarios[\s\S]*Notas|notas/);
  assert.match(card('mesero'), new RegExp(`data-vpf-copy="https://clonexa.app/mini-panel/mesero/login\\?company_id=${ID}"`));
  assert.match(card('mesero'), /data-vpf-segment="mesero" data-on="0">Apagar/);
  assert.match(card('caja'), /Apagado[\s\S]*data-vpf-segment="caja" data-on="1">Encender/);
  assert.match(card('domicilios'), /Lo atiende la Caja/);
  assert.match(card('domicilios'), /1 usuario\(s\) de caja/);
  assert.match(card('sales'), /data-vpf-unassign="sales" data-code="notas"/);
  assert.match(card('sales'), /data-vpf-pick="sales">\+ Añadir módulo/);
  assert.match(html, /data-vpf-drop="sales"/);
  assert.doesNotMatch(html, /Guardar cambios/, 'sin cambios no hay botón de guardar');
  assert.match(f.panelsZone({ ...data, ui: { dirty: true } }), /Cambios sin guardar[\s\S]*data-vpf-save-panels>Guardar cambios/);
  const noMini = f.panelsZone({ ...data, present: false });
  assert.match(noMini, /no tiene encendido el módulo de mini paneles/);
  const noWo = f.panelsZone({ ...data, rest: { ...data.rest, waiterOrdering: false } });
  assert.match(noWo, /Requiere el módulo Pedidos por mesero/);
  assert.doesNotMatch(noWo, /data-vpf-segment=/, 'sin el módulo no se ofrece el interruptor');
});

test('encender un panel de restaurante: mismo endpoint que Admin V2, solo "segments" y sin tocar lo demás', async () => {
  const { f, company, calls } = load();
  const rest = f.restaurantState(MODULES);
  await company.writes.setSegment(ID, rest.segments, 'caja', true);
  const [call] = calls;
  assert.equal(call.url, `/api/v1/companies/${ID}/modules/waiter_ordering/activate`);
  assert.deepEqual(call.body, { settings: { segments: {
    mesero: { enabled: true, modules: ['notas'], extra: 1 }, cocina: { enabled: false, modules: [] }, caja: { enabled: true, modules: [] } } } });
  // El servidor mezcla settings por clave (activate_company_module): estaciones, límites, etc. quedan iguales.
  const stored = MODULES.find((m) => m.module.code === 'waiter_ordering').settings;
  const merged = { ...stored, ...call.body.settings };
  assert.deepEqual(merged.stations, ['parrilla']);
  assert.equal(merged.waiter_user_limit, 8);
  const v2 = readFileSync('app/web/admin_v2.js', 'utf8');
  assert.match(v2, /cxJsonRequest\(`\/companies\/\$\{encodeURIComponent\(companyId\)\}\/modules\/waiter_ordering\/activate`/);
  assert.match(v2, /segments\[type\] = \{\s*enabled: data\[`segment_\$\{type\}_enabled`\] === "on",/);
});

// ------------------------------------------------------------ resumen
const SINCE = (iso) => (iso ? 'Hace 5 min' : '—');
test('el resumen se dibuja con datos completos', () => {
  const { f } = load();
  const days = Array.from({ length: 14 }, (_, i) => ({ date: `2026-09-${String(17 + i).padStart(2, '0')}`, logins: i % 3 }));
  const html = f.summary({
    company: { id: ID, name: 'Radio <b>Despecho</b>', status: 'inactive', plan: 'starter' }, kind: 'demo', since: SINCE,
    pulse: { state: 'riesgo', state_reason: 'Inactiva con 6 módulos', plan: 'Bar Pro', last_real_signal_at: '2026-10-01T00:00:00Z' },
    modules: MODULES, users: [{ status: 'active', role: 'company_admin' }, { status: 'inactive', role: 'mesero' }],
    experience: { branding: { logo_url: 'data:image/webp;base64,UklGRg==', primary_color: '#ff0000', secondary_color: '#00ff00', background_color: '#000000' } },
    activity: { days, sessions: { stale: 4 } }, audit: [{ method: 'POST', path: `/api/v1/companies/${ID}/modules/kpis/activate`, status_code: 200, at: 'x', actor: 'a@b.co' }],
    links: [{ title: 'Panel cliente', href: 'https://clonexa.app/client?company_id=x' }],
    panels: [{ on: true, label: 'Mesero', users: 3, link: 'https://clonexa.app/mini-panel/mesero/login' }],
  });
  assert.doesNotMatch(html, /<b>Despecho<\/b>/);
  assert.match(html, /Radio &lt;b&gt;Despecho&lt;\/b&gt;/);
  assert.match(html, /<img class="vp-sum-logo" src="data:image\/webp;base64,UklGRg=="/);
  assert.match(html, /<b>Demo<\/b> · Inactiva · Plan Bar Pro/);
  assert.equal((html.match(/class="vp-color-dot" data-vpf-swatch="#/g) || []).length, 3);
  assert.match(html, /vp-sum-light vp-light-riesgo[\s\S]*En riesgo/);
  assert.match(html, /<svg class="vp-chart"/);
  assert.equal((html.match(/<rect class="vp-bar[ "]/g) || []).length, 14);
  assert.match(html, /<b>7<\/b> de 8 encendidos/);
  assert.match(html, /data-vpf-goto="modulos"/);
  assert.match(html, /<b>Mesero<\/b><small>3 usuarios<\/small>/);
  assert.match(html, /<b>1<\/b> ingresos|ingresos ·/);
  assert.match(html, /Usuarios activos<\/span><strong>1 de 2/);
  assert.match(html, /Dueño con acceso<\/span><strong class="vp-yes">Sí/);
  assert.match(html, /POST \/modules\/kpis\/activate/);
  assert.match(html, /Inactiva con 7 módulos encendidos/);
  assert.match(html, /4 sesiones viejas sin cerrar/);
  assert.match(html, /Entrar como empresa/);
  assert.doesNotMatch(html, /\sstyle=/);
});

test('el resumen se dibuja con datos vacíos', () => {
  const { f } = load();
  const html = f.summary({ company: { id: ID, name: 'Nueva', status: 'active' }, kind: 'registrada', pulse: null, modules: [], users: [],
    experience: {}, activity: { days: Array.from({ length: 14 }, (_, i) => ({ date: `2026-09-${17 + i}`, logins: 0 })), sessions: {} }, audit: [], links: [], panels: [], since: SINCE });
  assert.match(html, /Sin ingresos en los últimos 14 días/);
  assert.match(html, /<b>0<\/b> de 0 encendidos/);
  assert.match(html, /Ningún módulo encendido/);
  assert.match(html, /Ningún mini panel encendido/);
  assert.match(html, /Sin cambios registrados/);
  assert.match(html, /Dueño con acceso<\/span><strong class="vp-no">No/);
  assert.match(html, /Sin dueño con acceso/);
  assert.match(html, /<span class="vp-sum-logo vp-initials">NU<\/span>/);
  const loading = f.summary({ company: { id: ID, name: 'X', status: 'active' }, modules: null, users: null, activity: null, audit: null, links: [], panels: [] });
  assert.match(loading, /Cargando/);
  const ok = f.summary({ company: { id: ID, name: 'X', status: 'active' }, modules: [], users: [{ status: 'active', role: 'owner' }], activity: { days: [], sessions: {} }, audit: [], links: [], panels: [] });
  assert.match(ok, /Todo en orden/);
});

// ------------------------------------------------------------ sesiones
test('sesiones: una tarjeta de resumen y el detalle paginado con buscador', () => {
  const { f } = load();
  const card = f.sessionsCard({ open_recent: 2, connected_now: 1, stale: 40, last_seen_at: 'x', recent_hours: 24 }, SINCE);
  assert.match(card, /<b>2<\/b> abiertas · <b>1<\/b> conectadas ahora · última Hace 5 min/);
  assert.match(card, /40 sin actividad \(más de 24 h\)/);
  assert.match(card, /data-vpf-close-all>Cerrar todas/);
  assert.match(card, /data-vpf-sessions-toggle>Ver detalle/);
  const sessions = Array.from({ length: 23 }, (_, i) => ({ session_key: `k${i}`, scope: i % 2 ? 'client' : 'mini_panel', status: i < 20 ? 'active' : 'closed',
    subject_label: i === 7 ? 'Ana Pérez' : `user${i}@bar.co`, last_seen_at: 'x', ip_address: '1.1.1.1' }));
  const page1 = f.sessionsTable(sessions, { query: '', page: 1 }, SINCE);
  assert.equal((page1.match(/<tr><td>/g) || []).length, 10);
  assert.match(page1, /Página 1 de 3 · 23 sesiones/);
  assert.match(page1, /data-vpf-sess-page="0" disabled/);
  const page3 = f.sessionsTable(sessions, { query: '', page: 3 }, SINCE);
  assert.equal((page3.match(/<tr><td>/g) || []).length, 3);
  assert.match(f.sessionsTable(sessions, { query: 'ana perez', page: 1 }, SINCE), /Ana Pérez[\s\S]*Página 1 de 1 · 1 sesiones/);
  assert.match(f.sessionsTable(sessions, { query: 'zzz', page: 1 }, SINCE), /Sin sesiones que coincidan/);
  assert.match(page1, /data-vpf-close-session="k0">Cerrar/);
});

test('Usuarios y accesos: sin el chorro de sesiones, políticas plegadas', () => {
  const { company } = load();
  const users = Array.from({ length: 9 }, (_, i) => ({ id: `u${i}`, full_name: i === 3 ? 'José Ñúñez' : `Usuario ${i}`, email: `u${i}@x.co`, role: 'mesero', status: 'active' }));
  company.model = { ...company.model, id: ID, tab: 'accesos', company: { id: ID, name: 'X', slug: 'x', status: 'active' }, users,
    activity: { sessions: { open_recent: 1, connected_now: 0, stale: 41 } }, accessPolicy: { enabled: false, scopes: {} }, sessionPolicy: { enabled: false, scopes: {} },
    sessions: { sessions: Array.from({ length: 42 }, (_, i) => ({ session_key: `k${i}`, status: 'active', scope: 'client' })) } };
  let html = company.view();
  assert.match(html, /<b>1<\/b> abiertas/);
  assert.doesNotMatch(html, /data-vpf-close-session=/, 'el detalle no se despliega solo');
  assert.match(html, /data-vpf-user-search/, 'más de 8 usuarios: buscador');
  assert.match(html, /<details class="vp-panel vp-section vp-fold"><summary>Política de acceso por IP/);
  assert.doesNotMatch(html, /<details[^>]* open/, 'plegadas por defecto');
  company.model = { ...company.model, userQuery: 'jose nunez', sess: { open: true, query: '', page: 1 } };
  html = company.view();
  assert.match(html, /José Ñúñez/);
  assert.doesNotMatch(html, /Usuario 4/);
  assert.equal((html.match(/data-vpf-close-session=/g) || []).length, 10, '10 por página');
});

test('Centro de mando: "Sesiones abiertas" son las de 24 h y las viejas van aparte', () => {
  const plus = readFileSync('app/web/admin_v2plus.js', 'utf8');
  const ctx = vm.createContext({ window: {}, document: {}, Date, Math, Number, String, Array, encodeURIComponent, decodeURIComponent });
  vm.runInContext(plus, ctx);
  const html = ctx.window.CxConsolePlus.table({ companies: [{ id: 'a', kind: 'registrada', name: 'TTM', slug: 'ttm', state: 'activa_hoy', open_sessions: 2, stale_sessions: 40 }] }, 'todas', Date.now());
  assert.match(html, /title="Con actividad en las últimas 24 h">2<br><small class="vp-mono-muted">\+40 sin actividad<\/small>/);
});

test('la ruta inicial #empresa/{id} espera a que carguen todos los scripts', () => {
  const plus = readFileSync('app/web/admin_v2plus.js', 'utf8');
  assert.match(plus, /if \(document\.readyState === "loading"\) document\.addEventListener\("DOMContentLoaded", firstRoute\);/);
  const html = readFileSync('app/web/admin_v2plus.html', 'utf8');
  assert.ok(html.indexOf('admin-v2plus-ficha.js') < html.indexOf('admin-v2plus-company.js'), 'las vistas cargan antes que la Ficha');
});
