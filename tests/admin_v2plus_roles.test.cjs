// Consola v2+ · Ficha · pestaña Roles: todos los roles del registro con
// interruptor "la empresa lo usa", nombre visible y qué permite; guardar pide
// confirmación (la auditoría la escribe el servidor); apagar un rol con
// empleados avisa cuántos y no les cambia el rol.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/admin_v2plus_company.js', 'utf8');
const companiesSource = readFileSync('app/web/admin_v2plus_companies.js', 'utf8');
const fichaSource = readFileSync('app/web/admin_v2plus_ficha.js', 'utf8');
const CATALOG = JSON.parse(readFileSync('app/services/role_catalog.json', 'utf8'));

function load() {
  const calls = [];
  const fetch = async (url, options = {}) => {
    calls.push({ url, method: options.method || 'GET', body: options.body ? JSON.parse(options.body) : undefined });
    return { status: 200, ok: true, json: async () => ({}) };
  };
  const window = { location: { href: '', origin: 'https://clonexa.app', hash: '' } };
  const ctx = vm.createContext({ window, document: {}, fetch, JSON, Object, Array, String, Math, Number, Promise, Error, Date, Boolean, encodeURIComponent, decodeURIComponent });
  vm.runInContext(companiesSource, ctx);
  vm.runInContext(fichaSource, ctx);
  vm.runInContext(source, ctx);
  return { ui: window.CxConsoleCompany, calls };
}

// Lo que devuelve GET /admin-v2/api/companies/{id}/employee-roles para Urbania ya configurada.
function urbaniaView() {
  const on = { gerencia: 'Director', supervisor: 'Supervisor', inventario: 'Logística', operario: 'Operario', otro: 'Otro' };
  return { configured: true, common: CATALOG.common, unknown_roles: {}, roles: CATALOG.roles.map((r) => ({ ...r, enabled: r.code in on,
    visible_label: on[r.code] || r.label, employees: { supervisor: 2, tecnico: 1 }[r.code] || 0 })) };
}

test('pestaña Roles en la ficha, con su lectura y escritura en /admin-v2/api (sesión de Admin V2)', async () => {
  const { ui, calls } = load();
  assert.match(source, /\["accesos", "Usuarios y accesos"\], \["roles", "Roles"\]/);
  await ui.reads.roles('76974191-1dc6-4eb4-9b19-7d1e9ad82946');
  await ui.writes.saveRoles('76974191-1dc6-4eb4-9b19-7d1e9ad82946', { roles: [] });
  assert.deepEqual(calls.map((c) => `${c.method} ${c.url}`), [
    'GET /admin-v2/api/companies/76974191-1dc6-4eb4-9b19-7d1e9ad82946/employee-roles',
    'PUT /admin-v2/api/companies/76974191-1dc6-4eb4-9b19-7d1e9ad82946/employee-roles']);
});

test('todos los roles del registro con interruptor, nombre visible, qué permite y empleados', () => {
  const { ui } = load();
  ui.model = { ...ui.model, roles: urbaniaView(), rolesDraft: null };
  const html = ui.tabRoles({ name: 'URBANIA' });
  for (const r of CATALOG.roles) {
    assert.match(html, new RegExp(`data-vpf-role-on="${r.code}"`), r.code);
    assert.match(html, new RegExp(`data-vpf-role-label="${r.code}"`), r.code);
    assert.ok(html.includes(r.permits[0].replace(/'/g, '&#039;')), `qué permite ${r.code}`);
  }
  assert.match(html, /data-vpf-role-on="gerencia" checked/); assert.match(html, /data-vpf-role-on="tecnico" >/);
  assert.match(html, /data-vpf-role-label="gerencia" value="Director"/);
  assert.match(html, /data-vpf-role-label="tecnico" value="Tecnico" maxlength="40" aria-label="Nombre visible de Tecnico" disabled/);
  assert.match(html, /<td class="vp-mono">1<br><small class="vp-role-warn">rol no habilitado<\/small><\/td>/, 'tecnico apagado con 1 empleado');
  assert.match(html, /Configurados para esta empresa/);
  assert.match(html, /<b>Otro<\/b> <span class="vp-state-pill">nuevo<\/span><br><small class="vp-mono-muted">otro<\/small>/);
  assert.match(html, /data-vpf-roles-save disabled/, 'sin cambios no se guarda');
});

test('plan: apagar un rol con empleados avisa cuántos y no les cambia el rol; al menos un rol', () => {
  const { ui } = load();
  const view = urbaniaView();
  const draft = ui.rolesDraftFrom(view);
  assert.equal(ui.rolesPlan(view, draft).changed, false);
  draft.supervisor.enabled = false;
  const plan = ui.rolesPlan(view, draft);
  assert.equal(plan.changed, true);
  assert.deepEqual(JSON.parse(JSON.stringify(plan.offWithEmployees)), [{ code: 'supervisor', label: 'Supervisor', employees: 2 }, { code: 'tecnico', label: 'Tecnico', employees: 1 }]);
  assert.deepEqual(JSON.parse(JSON.stringify(plan.on.map((r) => r.code))), ['gerencia', 'inventario', 'operario', 'otro']);
  assert.equal(plan.body.roles.length, CATALOG.roles.length, 'manda todos los roles con su estado');
  ui.model = { ...ui.model, roles: view, rolesDraft: draft };
  assert.match(ui.tabRoles({ name: 'URBANIA' }), /2 con Supervisor, 1 con Tecnico: al guardar quedan marcados “rol no habilitado” y su rol no cambia\./);
  Object.values(draft).forEach((d) => { d.enabled = false; });
  assert.equal(ui.rolesPlan(view, draft).error, 'La empresa debe usar al menos un rol.');
  const renamed = ui.rolesDraftFrom(view);
  renamed.gerencia.label = 'Dirección';
  assert.equal(ui.rolesPlan(view, renamed).changed, true, 'cambiar el nombre visible también es un cambio');
});

test('guardar y volver a todos los roles piden confirmación antes de escribir', () => {
  assert.match(source, /ask\("Guardar roles", `Guardar los roles de \$\{c\.name\}\? Personal ofrecerá: \$\{names\}\.\$\{warn\} Queda en la auditoría\.`/);
  assert.match(source, /ask\("Volver a todos los roles",[\s\S]*writes\.saveRoles\(id, \{ reset: true \}\)/);
  assert.doesNotMatch(source, /writes\.saveRoles\(id, plan\.body\)\);\n\s*return true;\n\s*\}\n\s*if \(t\.closest\("\[data-vpf-roles-reset/, 'nunca guarda sin pasar por ask');
});
