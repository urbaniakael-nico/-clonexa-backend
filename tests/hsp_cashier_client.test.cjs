const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/hsp_cashier.js', 'utf8');

function fn(name) {
  const start = source.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

const { loadKit } = require('./_menu_kit.cjs');

// money() comes from the shared menu kit (hsp_menu_kit.js) since the caja
// reuses the mesero's components.
function context() {
  const ctx = vm.createContext({ Intl, Math, Number, String });
  vm.runInContext(fn('normKey'), ctx);
  ctx.money = loadKit().money;
  return ctx;
}

test('money formats whole COP amounts without decimals', () => {
  const ctx = context();
  assert.match(ctx.money(9000), /9[.,]000/);
});

test('normKey lowercases and trims so table grouping is stable', () => {
  const ctx = context();
  assert.equal(ctx.normKey('  Mesa 4 '), 'mesa 4');
  assert.equal(ctx.normKey('MESA 4'), 'mesa 4');
});

test('normKey tolerates missing values instead of throwing', () => {
  const ctx = context();
  assert.equal(ctx.normKey(undefined), '');
  assert.equal(ctx.normKey(null), '');
});
