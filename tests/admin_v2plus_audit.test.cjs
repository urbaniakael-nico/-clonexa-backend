// Consola v2+ · Auditoría: menú y pestaña de la Ficha sobre GET /admin-v2/api/audit.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/admin_v2plus_audit.js', 'utf8');

function load() {
  const calls = [];
  const fetch = async (url) => { calls.push(url); return { status: 200, ok: true, json: async () => ({ entries: [] }) }; };
  const ctx = vm.createContext({ window: { location: {} }, document: {}, fetch, Date, JSON, Object, Array, String, Number, encodeURIComponent });
  vm.runInContext(source, ctx);
  return { ui: ctx.window.CxConsoleAudit, calls };
}

test('arma la consulta con los filtros de empresa, fecha y acción', async () => {
  const { ui, calls } = load();
  assert.equal(ui.query({}), '/admin-v2/api/audit');
  assert.equal(ui.query({ company_id: 'c 1', date_from: '2026-10-01', date_to: '', action: 'purge&x' }),
    '/admin-v2/api/audit?company_id=c%201&date_from=2026-10-01&action=purge%26x');
  await ui.load({ action: 'POST' });
  assert.deepEqual(calls, ['/admin-v2/api/audit?action=POST']);
});

test('la tabla escapa todo y marca los fallos', () => {
  const { ui } = load();
  const html = ui.table([
    { at: '2026-10-04T15:00:00Z', method: 'POST', path: '/admin-v2/api/companies/c1/purge', company_id: 'c1', status_code: 200,
      actor: 'clonexasaas@gmail.com', ip: '181.1.1.1', surface: 'v2plus', detail: { company_name: 'Bar <img src=x onerror=alert(1)>', deleted_rows: 42 } },
    { at: '2026-10-04T15:01:00Z', method: 'PATCH', path: '/api/v1/companies/c2/status', company_id: 'c2', status_code: 400, actor: 'x', ip: '', surface: 'v2' },
  ], { c1: 'Demo Bar' });
  assert.doesNotMatch(html, /<img src=x/);
  assert.match(html, /company_name: Bar &lt;img src=x onerror=alert\(1\)&gt; · deleted_rows: 42/);
  assert.match(html, /<a href="#empresa\/c1">Demo Bar<\/a>/);
  assert.match(html, /vp-audit-fail">400/);
  assert.match(html, /Consola v2\+/);
  assert.match(html, /Admin V2/);
  assert.match(ui.table([]), /Sin escrituras registradas/);
  const noCompany = ui.table([{ at: '', method: 'POST', path: '/x', company_id: 'c1', status_code: 200 }], {}, false);
  assert.doesNotMatch(noCompany, /<th>Empresa<\/th>/, 'en la Ficha la empresa ya está fija');
});

test('en la Ficha el filtro de empresa queda fijo', () => {
  const { ui } = load();
  const fixed = ui.panel({ fixed: { company_id: 'c1' }, filters: {}, entries: [], error: '', loading: false }, {});
  assert.doesNotMatch(fixed, /name="company_id"/);
  const free = ui.panel({ fixed: {}, filters: { action: 'kind' }, entries: [], error: '', loading: false }, {});
  assert.match(free, /name="company_id"/);
  assert.match(free, /name="action" value="kind"/);
  assert.match(free, /180 días/);
});

test('Auditoría sale del menú: vive en Salud y seguridad; la pestaña de la Ficha se conserva', () => {
  const html = readFileSync('app/web/admin_v2plus.html', 'utf8');
  assert.doesNotMatch(html, /data-vp-view="audit"/, 'sin entrada propia en el menú');
  const admin = readFileSync('app/web/admin_v2plus_admin.js', 'utf8');
  assert.match(admin, /\$\{auditBlock\(\)\}/, 'bloque en Salud y seguridad');
  assert.match(admin, /CxConsoleAudit\.load\(\{ limit: 5 \}\)/, 'los últimos 5');
  assert.match(admin, /data-vpx-audit-all>Ver todo</);
  assert.match(admin, /vp-audit-window" data-vpa-host/, 'el listado completo en una ventana');
  const palette = readFileSync('app/web/admin_v2plus_palette.js', 'utf8');
  assert.match(palette, /push\("section", "Auditoría"[\s\S]*view: "health", focus: "audit"/, 'Ctrl+K lleva al bloque');
  assert.match(html, /<script src="\/admin-v2plus-audit\.js"><\/script>/);
  const ficha = readFileSync('app/web/admin_v2plus_company.js', 'utf8');
  assert.match(ficha, /\["auditoria", "Auditoría"\]/);
  assert.match(ficha, /CxConsoleAudit\.mountInto\(audit, \{ company_id: model\.id \}\)/);
  const plus = readFileSync('app/web/admin_v2plus.js', 'utf8');
  assert.match(plus, /state\.view === "audit" && window\.CxConsoleAudit/);
});

test('la auditoría se lee en lenguaje claro, no como ruta técnica', () => {
  const vm = require('node:vm');
  const window = { CxSwitchRegistry: { get: (k) => (k === 'cashier_redesign' ? { label: 'Caja rediseñada' } : null) } };
  const ctx = vm.createContext({ window, document: {}, fetch: async () => ({}), JSON, Object, Array, String, Number, Date, Map, Math, encodeURIComponent });
  vm.runInContext(readFileSync('app/web/admin_v2plus_audit.js', 'utf8'), ctx);
  const A = window.CxConsoleAudit;
  const V = 'd63cf68c-be5b-4a30-aee4-341973018db1';
  const S = '7625872c-f941-4479-a27b-f8443be953c5';
  const names = { [V]: 'Velvet', [S]: 'ASADERO' };
  const d = (method, path, detail, extra = {}) => A.describe({ method, path, company_id: path.includes(V) ? V : path.includes(S) ? S : null, status_code: 200, detail, ...extra }, names);
  assert.equal(d('POST', `/admin-v2/api/brand/${V}/publish`, { marca: 'publicada', version: 2 }), 'Publicó la marca de Velvet (versión 2)');
  assert.equal(d('POST', `/api/v1/companies/${S}/modules/waiter_ordering/activate`, { interruptor: 'cashier_redesign', valor: true }), 'Encendió Caja rediseñada en ASADERO');
  assert.equal(d('POST', `/api/v1/companies/${S}/modules/waiter_ordering/activate`, { interruptor: 'cashier_redesign', valor: false }), 'Apagó Caja rediseñada en ASADERO');
  assert.equal(d('POST', `/admin-v2/api/brand/${V}/rollback/1`, {}), 'Volvió la marca de Velvet a la versión 1');
  assert.equal(d('POST', `/admin-v2/api/brand/${V}/share`, {}), 'Compartió la vista previa de la marca de Velvet');
  assert.equal(d('POST', `/admin-v2/api/billing/companies/${V}/payments/x/validate`, { comprobante: 'CX-000007' }), 'Validó un pago de Velvet (comprobante CX-000007)');
  assert.equal(d('POST', `/admin-v2/api/brand/${V}/publish`, {}, { status_code: 409 }), 'Publicó la marca de Velvet (no se completó)');
  assert.match(d('DELETE', `/api/v1/companies/${S}/algo/raro`, {}), /^Borró algo raro en ASADERO$/);
});

test('el bloque de Auditoría en Salud y seguridad muestra 5 registros', () => {
  const vm = require('node:vm');
  const window = { location: { href: '' } };
  const ctx = vm.createContext({ window, document: {}, fetch: async () => ({ ok: true, status: 200, json: async () => ({}) }), JSON, Object, Array, String, Number, Date, Map, Set, Math, Promise, Error, URLSearchParams, encodeURIComponent });
  for (const f of ['admin_v2plus_audit.js', 'admin_v2plus_admin.js']) vm.runInContext(readFileSync(`app/web/${f}`, 'utf8'), ctx);
  const adm = window.CxConsoleAdmin;
  adm.model.health.status = { ok: true };
  adm.model.health.audit = Array.from({ length: 8 }, (_, i) => ({ method: 'POST', path: `/admin-v2/api/brand/c${i}/publish`, company_id: null, status_code: 200, at: '2026-10-05T12:00:00Z', actor: 'admin', detail: { company_name: `Empresa ${i}` } }));
  const root = { innerHTML: '', querySelector: () => null, querySelectorAll: () => [] };
  window.CxConsoleSections.health.mount({ root: () => root, active: () => true, overview: () => ({ health: {}, companies: [] }), toast: () => {}, params: {} });
  const block = root.innerHTML.split('data-vpx-audit-block')[1].split('</section>')[0];
  assert.equal((block.match(/<li class="vp-action">/g) || []).length, 5);
  assert.match(block, /Publicó la marca de Empresa 0/);
  assert.doesNotMatch(block, /\/admin-v2\/api\/brand/, 'sin rutas técnicas');
  assert.match(block, /data-vpx-audit-all>Ver todo/);
});
