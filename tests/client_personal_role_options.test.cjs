const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/client.js', 'utf8');

function fn(name) {
  const start = source.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

function constBlock(name) {
  const start = source.search(new RegExp(`\\n  const ${name}( =|\\()`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

// personalRoleOptions (Workforce's role dropdown) must show a restaurant-only
// role list for a company with waiter_ordering active (today only Asadero El
// Socio) and the untouched generic list for every other company, per the
// per-company-switch rule -- with isClientModuleActive() driving which list
// applies and a legacy/unknown saved role never disappearing from the row.
function roleOptionsContext(activeModuleCodes = [], companyRoles = null) {
  const context = vm.createContext({ window: { location: {} }, document: undefined, String, Array, Boolean });
  vm.runInContext(
    `function activeClientModules() { return ${JSON.stringify(activeModuleCodes)}.map((code) => ({ code, enabled: true })); }\n`
      + `const state = { companyId: "c1" };\n`
      // Roles por empresa (051A): lo que devolvio /employee-roles; null = sin configuracion (como hoy).
      + `let cxEmployeeRoles051A = ${companyRoles ? JSON.stringify({ companyId: 'c1', configured: true, roles: companyRoles }) : 'null'};\n`
      + fn('cxEmployeeRolesConfigured051A')
      + fn('cxPersonalRoleList051A')
      + constBlock('h')
      + fn('cxNormalizeModuleToken017H')
      + constBlock('CX_HIDDEN_CLIENT_MODULE_CODES_017H')
      + fn('cxIsHiddenClientModule017H')
      + fn('isClientModuleActive')
      + constBlock('CX_PERSONAL_ROLES_DEFAULT_030S')
      + constBlock('CX_PERSONAL_ROLES_WAITER_ORDERING_030S')
      + fn('personalRoleFallbackLabel030S')
      + fn('personalRoleOptions'),
    context,
  );
  return context;
}

function optionValues(html) {
  return Array.from(html.matchAll(/<option value="([^"]*)"/g)).map((m) => m[1]);
}

test('a company without waiter_ordering keeps the full generic role list', () => {
  const ctx = roleOptionsContext([]);
  const values = optionValues(ctx.personalRoleOptions('vendedor'));
  assert.deepEqual(values, [
    'admin_empresa', 'supervisor', 'agente_call', 'agente_externo', 'tesoreria',
    'gerencia', 'tecnico', 'operario', 'vendedor', 'barman', 'mesero', 'cajero',
    'inventario', 'operator',
  ]);
});

test('a company with waiter_ordering active sees only the 6 restaurant roles', () => {
  const ctx = roleOptionsContext(['waiter_ordering']);
  const values = optionValues(ctx.personalRoleOptions('mesero'));
  assert.deepEqual(values, ['dueno', 'gerente', 'administrador', 'mesero', 'parrillero', 'cajero']);
});

test('an employee with a legacy role outside the restaurant list keeps it selected instead of losing it', () => {
  const ctx = roleOptionsContext(['waiter_ordering']);
  const html = ctx.personalRoleOptions('vendedor');
  assert.ok(html.includes('value="vendedor"'));
  const match = html.match(/<option value="vendedor"[^>]*>/);
  assert.ok(match[0].includes('selected'));
});

test('the restaurant list marks the actually-selected role, not the fallback', () => {
  const ctx = roleOptionsContext(['waiter_ordering']);
  const html = ctx.personalRoleOptions('administrador');
  const selected = html.match(/<option value="([^"]*)"[^>]*selected/);
  assert.equal(selected[1], 'administrador');
});

// Roles por empresa (Consola v2+ · Ficha · Roles): con configuracion el selector
// muestra SOLO los roles de la empresa con su nombre visible; sin ella, igual que hoy.
const URBANIA = [['gerencia', 'Director'], ['supervisor', 'Supervisor'], ['inventario', 'Logística'], ['operario', 'Operario'], ['otro', 'Otro']];

test('a company with its own roles sees only those, with its visible names, in its order', () => {
  const ctx = roleOptionsContext(['domicilios_whatsapp'], URBANIA);
  const html = ctx.personalRoleOptions('supervisor');
  assert.deepEqual(optionValues(html), ['gerencia', 'supervisor', 'inventario', 'operario', 'otro']);
  assert.match(html, /<option value="gerencia" >Director<\/option>/);
  assert.match(html, /<option value="inventario" >Logística<\/option>/);
  assert.ok(!html.includes('domiciliario'), 'la lista de la empresa manda, sin agregados');
});

test('a role the company turned off stays selected and is marked "rol no habilitado" (it never changes alone)', () => {
  const ctx = roleOptionsContext([], URBANIA);
  const html = ctx.personalRoleOptions('tecnico');
  assert.match(html, /<option value="tecnico" selected>Tecnico \(rol no habilitado\)<\/option>/);
});

test('without configuration nothing changes, even for a legacy role (no "rol no habilitado")', () => {
  const ctx = roleOptionsContext([], null);
  const html = ctx.personalRoleOptions('rol_viejo');
  assert.match(html, /<option value="rol_viejo" selected>Rol Viejo<\/option>/);
  assert.equal(optionValues(html).length, 15);
});
