const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/hsp_waiter.js', 'utf8');

function fn(name) {
  const start = source.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

function context(cart = []) {
  const ctx = vm.createContext({ Intl, Math, Number, String, JSON });
  vm.runInContext(
    `var state = { cart: ${JSON.stringify(cart)} };\n` + fn('money') + '\n' + fn('cartTotal'),
    ctx,
  );
  return ctx;
}

test('money formats whole COP amounts without decimals', () => {
  const ctx = context();
  assert.match(ctx.money(16000), /16[.,]000/);
});

test('cartTotal sums quantity x unit_price across the cart', () => {
  const ctx = context([
    { unit_price: 4000, quantity: 2 },
    { unit_price: 5000, quantity: 1 },
  ]);
  assert.equal(ctx.cartTotal(), 13000);
});

test('cartTotal is zero for an empty cart', () => {
  const ctx = context([]);
  assert.equal(ctx.cartTotal(), 0);
});

function formatHMSContext() {
  const ctx = vm.createContext({ Math, Number, String });
  vm.runInContext(fn('formatHMS'), ctx);
  return ctx;
}

test('formatHMS shows only minutes under an hour', () => {
  const ctx = formatHMSContext();
  assert.equal(ctx.formatHMS(65), '1m');
  assert.equal(ctx.formatHMS(0), '0m');
});

test('formatHMS shows hours and padded minutes past an hour', () => {
  const ctx = formatHMSContext();
  assert.equal(ctx.formatHMS(3661), '1h 01m');
  assert.equal(ctx.formatHMS(7200), '2h 00m');
});

test('addOrUpdateCartLine pushes a new line when no editIndex, replaces in place otherwise', () => {
  const ctx = vm.createContext({ JSON });
  vm.runInContext(
    'var state = { cart: [{ name: "Carne" }] };\n' +
      'function persistCart(){ state._persisted = JSON.stringify(state.cart); }\n' +
      fn('addOrUpdateCartLine'),
    ctx,
  );
  ctx.addOrUpdateCartLine({ name: 'Papas' });
  assert.equal(ctx.state.cart.length, 2);
  assert.equal(ctx.state.cart[1].name, 'Papas');

  ctx.addOrUpdateCartLine({ name: 'Carne editada' }, 0);
  assert.equal(ctx.state.cart.length, 2);
  assert.equal(ctx.state.cart[0].name, 'Carne editada');
});

test('removeCartLine removes exactly the requested index', () => {
  const ctx = vm.createContext({ JSON });
  vm.runInContext(
    'var state = { cart: [{ name: "A" }, { name: "B" }, { name: "C" }] };\n' +
      'function persistCart(){}\n' +
      fn('removeCartLine'),
    ctx,
  );
  ctx.removeCartLine(1);
  assert.deepEqual(Array.from(ctx.state.cart, (c) => c.name), ['A', 'C']);
});
