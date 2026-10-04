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

test('menú "Auditoría", pestaña en la Ficha y script cargado', () => {
  const html = readFileSync('app/web/admin_v2plus.html', 'utf8');
  assert.match(html, /data-vp-view="audit">Auditoría<\/button>/);
  assert.match(html, /<script src="\/admin-v2plus-audit\.js"><\/script>/);
  const ficha = readFileSync('app/web/admin_v2plus_company.js', 'utf8');
  assert.match(ficha, /\["auditoria", "Auditoría"\]/);
  assert.match(ficha, /CxConsoleAudit\.mountInto\(audit, \{ company_id: model\.id \}\)/);
  const plus = readFileSync('app/web/admin_v2plus.js', 'utf8');
  assert.match(plus, /state\.view === "audit" && window\.CxConsoleAudit/);
});
