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
function roleOptionsContext(activeModuleCodes = []) {
  const context = vm.createContext({ window: { location: {} }, document: undefined, String, Array });
  vm.runInContext(
    `function activeClientModules() { return ${JSON.stringify(activeModuleCodes)}.map((code) => ({ code, enabled: true })); }\n`
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
