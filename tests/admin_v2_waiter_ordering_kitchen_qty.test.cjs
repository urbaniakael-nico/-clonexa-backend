const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/admin_v2.js', 'utf8');

function fn(name) {
  const start = source.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

function constLine(name) {
  const match = source.match(new RegExp(`\\n  const ${name} = [^\\n]+`));
  assert.ok(match, name);
  return match[0].replace('const ', 'var ');
}

function context() {
  const ctx = vm.createContext({ Array, String });
  vm.runInContext(
    constLine('CX_WO_DEFAULT_QTY_BUTTONS_042K') + '\n'
      + fn('cxWaiterOrderingKitchenQtySettings042K') + '\n' + fn('cxReadQuantityButtons042K'),
    ctx,
  );
  return ctx;
}

test('both switches are off unless explicitly true', () => {
  const ctx = context();
  const settings = ctx.cxWaiterOrderingKitchenQtySettings042K({});
  assert.equal(settings.kitchen_board_columns, false);
  assert.equal(settings.quantity_buttons_enabled, false);
  assert.deepEqual(Array.from(settings.quantity_buttons), ['1/4', '1/2', '3/4', '1', '2']);
  assert.equal(ctx.cxWaiterOrderingKitchenQtySettings042K({ kitchen_board_columns: 'yes' }).kitchen_board_columns, false);
});

test('stored buttons round-trip', () => {
  const ctx = context();
  const settings = ctx.cxWaiterOrderingKitchenQtySettings042K({ kitchen_board_columns: true, quantity_buttons_enabled: true, quantity_buttons: ['1/2', '1'] });
  assert.equal(settings.kitchen_board_columns, true);
  assert.deepEqual(Array.from(settings.quantity_buttons), ['1/2', '1']);
});

test('the buttons field keeps only valid, unique fractions', () => {
  const ctx = context();
  assert.deepEqual(Array.from(ctx.cxReadQuantityButtons042K('1/2, 1, abc, 1/0, 1, 1.5')), ['1/2', '1', '1.5']);
  assert.deepEqual(Array.from(ctx.cxReadQuantityButtons042K('')), ['1/4', '1/2', '3/4', '1', '2']);
});

test('caja direct sale is off unless explicitly true', () => {
  const ctx = context();
  assert.equal(ctx.cxWaiterOrderingKitchenQtySettings042K({}).cashier_direct_sale, false);
  assert.equal(ctx.cxWaiterOrderingKitchenQtySettings042K({ cashier_direct_sale: 'yes' }).cashier_direct_sale, false);
  assert.equal(ctx.cxWaiterOrderingKitchenQtySettings042K({ cashier_direct_sale: true }).cashier_direct_sale, true);
});

test('kitchen roster is off unless explicitly true', () => {
  const ctx = context();
  assert.equal(ctx.cxWaiterOrderingKitchenQtySettings042K({}).kitchen_roster, false);
  assert.equal(ctx.cxWaiterOrderingKitchenQtySettings042K({ kitchen_roster: 1 }).kitchen_roster, false);
  assert.equal(ctx.cxWaiterOrderingKitchenQtySettings042K({ kitchen_roster: true }).kitchen_roster, true);
});

test('menu emojis are off unless explicitly true', () => {
  const ctx = context();
  assert.equal(ctx.cxWaiterOrderingKitchenQtySettings042K({}).menu_emojis, false);
  assert.equal(ctx.cxWaiterOrderingKitchenQtySettings042K({ menu_emojis: true }).menu_emojis, true);
});
