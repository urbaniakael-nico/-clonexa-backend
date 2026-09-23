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

// Fase 2, general capability: mesero/cocina/caja mini panel segments are
// read from the per-company waiter_ordering module settings (Admin V2's
// segment checkboxes), off by default, only ever appearing for a company
// that has both the module enabled and that specific segment turned on.
function segmentsContext(moduleRows) {
  const context = vm.createContext({ Array, Object, String, Number, Boolean });
  vm.runInContext(
    `function activeClientModules() { return ${JSON.stringify(moduleRows)}; }\n`
      + `function cxMiniPanelTypeLabel019B(code) { return code; }\n`
      + fn('cxWaiterOrderingMiniPanelSegments030S')
      + fn('cxMergeWaiterOrderingSegments030S'),
    context,
  );
  return context;
}

function waiterOrderingModule(settings) {
  return [{ code: "waiter_ordering", enabled: true, raw: { settings } }];
}

test('a company with no waiter_ordering module at all gets zero segments', () => {
  const ctx = segmentsContext([]);
  const segments = ctx.cxWaiterOrderingMiniPanelSegments030S();
  assert.deepEqual(Object.keys(segments), []);
});

test('waiter_ordering enabled but every segment off (brand new company) still yields nothing', () => {
  const ctx = segmentsContext(waiterOrderingModule({}));
  const segments = ctx.cxWaiterOrderingMiniPanelSegments030S();
  assert.deepEqual(Object.keys(segments), []);
});

test('only the explicitly-enabled segments show up, with the real limits and dedicated link', () => {
  const ctx = segmentsContext(waiterOrderingModule({
    segments: { mesero: { enabled: true }, cocina: { enabled: false }, caja: { enabled: true } },
    waiter_user_limit: 5,
    cashier_user_limit: 1,
  }));
  const segments = ctx.cxWaiterOrderingMiniPanelSegments030S();

  assert.deepEqual(Object.keys(segments).sort(), ["caja", "mesero"]);
  assert.equal(segments.mesero.max_users, 5);
  assert.equal(segments.mesero.login_template, "/mini-panel/mesero?company_id={company_id}");
  assert.equal(segments.caja.max_users, 1);
  assert.equal(segments.caja.login_template, "/mini-panel/caja?company_id={company_id}");
});

test('a missing limit falls back to the Fase 1 defaults (10/2/1)', () => {
  const ctx = segmentsContext(waiterOrderingModule({
    segments: { mesero: { enabled: true }, cocina: { enabled: true }, caja: { enabled: true } },
  }));
  const segments = ctx.cxWaiterOrderingMiniPanelSegments030S();
  assert.equal(segments.mesero.max_users, 10);
  assert.equal(segments.cocina.max_users, 2);
  assert.equal(segments.caja.max_users, 1);
});

test('merge is additive: an existing generic segment list keeps its own entries', () => {
  const ctx = segmentsContext([]);
  const base = { enabled: true, panels: { sales: { code: "sales", enabled: true } } };
  const merged = ctx.cxMergeWaiterOrderingSegments030S(base, { mesero: { code: "mesero", enabled: true } });
  assert.deepEqual(Object.keys(merged.panels).sort(), ["mesero", "sales"]);
});

test('merge with no base object still produces a usable enabled settings object', () => {
  const ctx = segmentsContext([]);
  const merged = ctx.cxMergeWaiterOrderingSegments030S(null, { mesero: { code: "mesero", enabled: true } });
  assert.equal(merged.enabled, true);
  assert.deepEqual(Object.keys(merged.panels), ["mesero"]);
});

test('merge with no waiter segments returns the base untouched', () => {
  const ctx = segmentsContext([]);
  const base = { enabled: true, panels: { sales: {} } };
  const merged = ctx.cxMergeWaiterOrderingSegments030S(base, {});
  assert.equal(merged, base);
});

// --- cxMiniPanelType026J: restaurant aliases must mirror the backend's
// _cx_panel_type_019d exactly (parrillero/cajero/etc resolve to the right
// panel code, not pass through as an unregistered literal string).
function typeContext() {
  const context = vm.createContext({ String });
  vm.runInContext(fn('cxMiniPanelType026J'), context);
  return context;
}

test('parrillero and parrillera alias to the cocina panel code', () => {
  const ctx = typeContext();
  assert.equal(ctx.cxMiniPanelType026J('parrillero'), 'cocina');
  assert.equal(ctx.cxMiniPanelType026J('parrillera'), 'cocina');
});

test('cajero/cajera/cashier alias to the caja panel code', () => {
  const ctx = typeContext();
  assert.equal(ctx.cxMiniPanelType026J('cajero'), 'caja');
  assert.equal(ctx.cxMiniPanelType026J('cajera'), 'caja');
  assert.equal(ctx.cxMiniPanelType026J('cashier'), 'caja');
});

test('mesero/cocina/caja pass through as themselves', () => {
  const ctx = typeContext();
  assert.equal(ctx.cxMiniPanelType026J('mesero'), 'mesero');
  assert.equal(ctx.cxMiniPanelType026J('cocina'), 'cocina');
  assert.equal(ctx.cxMiniPanelType026J('caja'), 'caja');
});

// --- cxMiniPanelMaxUsers026J fallback defaults for the 3 new segments.
function maxUsersContext() {
  const context = vm.createContext({ Number, Math });
  vm.runInContext(fn('cxMiniPanelMaxUsers026J'), context);
  return context;
}

test('cxMiniPanelMaxUsers026J falls back to 10/2/1 for mesero/cocina/caja when unset', () => {
  const ctx = maxUsersContext();
  assert.equal(ctx.cxMiniPanelMaxUsers026J({}, 'mesero'), 10);
  assert.equal(ctx.cxMiniPanelMaxUsers026J({}, 'cocina'), 2);
  assert.equal(ctx.cxMiniPanelMaxUsers026J({}, 'caja'), 1);
});

// --- Workforce role -> segment candidate matching ("Generar usuario"): rol
// Mesero shows up for Meseros, Parrillero/Cocina for Cocina, Cajero for Caja.
function constBlock(name) {
  const start = source.search(new RegExp(`\\n  const ${name}( =|\\()`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

function roleMatchContext() {
  const context = vm.createContext({ String });
  vm.runInContext(
    constBlock('CX_MINI_PANEL_ROLE_TOKENS_026J')
      + fn('cxNormalizeRole019C')
      + fn('cxMiniPanelEmployeeRoleTokens026J')
      + fn('cxMiniPanelType026J')
      + fn('cxMiniPanelEmployeeMatchesType026J'),
    context,
  );
  return context;
}

test('an employee with role mesero is a candidate for the Meseros segment only', () => {
  const ctx = roleMatchContext();
  const employee = { role: 'mesero' };
  assert.equal(ctx.cxMiniPanelEmployeeMatchesType026J(employee, 'mesero'), true);
  assert.equal(ctx.cxMiniPanelEmployeeMatchesType026J(employee, 'cocina'), false);
  assert.equal(ctx.cxMiniPanelEmployeeMatchesType026J(employee, 'caja'), false);
});

test('an employee with role parrillero is a candidate for the Cocina segment', () => {
  const ctx = roleMatchContext();
  const employee = { role: 'parrillero' };
  assert.equal(ctx.cxMiniPanelEmployeeMatchesType026J(employee, 'cocina'), true);
  assert.equal(ctx.cxMiniPanelEmployeeMatchesType026J(employee, 'mesero'), false);
});

test('an employee with role cajero is a candidate for the Caja segment', () => {
  const ctx = roleMatchContext();
  const employee = { role: 'cajero' };
  assert.equal(ctx.cxMiniPanelEmployeeMatchesType026J(employee, 'caja'), true);
});
