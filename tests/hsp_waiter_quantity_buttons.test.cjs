const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/hsp_waiter.js', 'utf8');
const { loadKit } = require('./_menu_kit.cjs');

function fn(name) {
  const start = source.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

// Quantity buttons, cart-line math and the order payload live in
// hsp_menu_kit.js (shared with the caja). The "lista para llevar" notice is
// covered in hsp_panel_alerts.test.cjs.
function context(extraState = {}) {
  const Kit = loadKit();
  const state = { cart: [], menu: [], quantityButtons: [], ...extraState };
  return {
    ...Kit,
    state,
    cartTotal: () => Kit.cartTotal(state.cart),
    findMenuProduct: (id) => Kit.findMenuProduct(state.menu, id),
  };
}

// Menu product exactly as waiter_ordering_menu returns it with the switch on.
const CARNE = {
  id: 'carne', name: 'CARNE Asada', price: 25000, quantity_ref_id: 'carne',
  quantity_options: [
    { label: '1/4', available: true, price: 6250 },
    { label: '1/2', available: true, price: 12500 },
    { label: '3/4', available: true, price: 18750 },
    { label: '1', available: true, price: 25000 },
    { label: '2', available: true, price: 50000 },
  ],
};
const POLLO = {
  id: 'pollo', name: 'Pollo', is_portioned: true, quantity_ref_id: 'pollo-1',
  portions: [
    { inventory_item_id: 'pollo-1', label: 'Entero', price: 40000 },
    { inventory_item_id: 'pollo-12', label: '1/2', price: 19000 },
    { inventory_item_id: 'pollo-fam', label: 'Familiar', price: 90000 },
  ],
  quantity_options: [
    { label: '1/4', available: true, price: 10000 },
    { label: '1/2', available: true, price: 19000 },
    { label: '1', available: true, price: 40000 },
    { label: '3/4', available: false, price: null },
  ],
};

test('portionFraction reads fractions, whole numbers and words, and nothing else', () => {
  const ctx = context();
  assert.equal(ctx.portionFraction('1/4'), 0.25);
  assert.equal(ctx.portionFraction('3/4 de pollo'), 0.75);
  assert.equal(ctx.portionFraction('2'), 2);
  assert.equal(ctx.portionFraction('Medio'), 0.5);
  assert.equal(ctx.portionFraction('Entero'), 1);
  assert.equal(ctx.portionFraction('Familiar'), null);
  assert.equal(ctx.portionFraction('1/0'), null);
});

test('each button shows the price the server calculated, before adding', () => {
  const ctx = context({ quantityButtons: ['1/4', '1/2', '3/4', '1', '2'] });
  const choices = ctx.quantityChoices(CARNE);
  assert.deepEqual(choices.map((c) => [c.label, c.price]), [
    ['1/4', 6250], ['1/2', 12500], ['3/4', 18750], ['1', 25000], ['2', 50000],
  ]);
  assert.ok(choices.every((c) => c.inventory_item_id === 'carne' && c.fraction === c.label));
});

test('a portion group keeps non-fraction portions reachable and marks unpriced ones', () => {
  const ctx = context();
  const choices = ctx.quantityChoices(POLLO);
  const byLabel = Object.fromEntries(choices.map((c) => [c.label, c]));
  assert.equal(byLabel['1/2'].price, 19000);          // configured portion price
  assert.equal(byLabel['3/4'].available, false);
  assert.equal(byLabel.Familiar.price, 90000);         // extra, sent as its own item
  assert.equal(byLabel.Familiar.fraction, '');
  assert.equal(byLabel.Familiar.inventory_item_id, 'pollo-fam');
  assert.equal(byLabel.Entero, undefined);             // same as the "1" button
});

test('the sheet preselects the whole unit, or the line being edited', () => {
  const ctx = context();
  const choices = ctx.quantityChoices(CARNE);
  assert.equal(choices[ctx.defaultChoiceIndex(choices, null)].label, '1');
  assert.equal(choices[ctx.defaultChoiceIndex(choices, { fraction: '3/4' })].label, '3/4');
});

test('a button choice becomes one cart line priced at the shown amount', () => {
  const ctx = context();
  const choice = ctx.quantityChoices(CARNE).find((c) => c.label === '3/4');
  const line = ctx.choiceCartLine(CARNE, choice, { term: '', observations: 'sin sal', quick_notes: [] });
  assert.equal(line.quantity, 1);
  assert.equal(line.unit_price, 18750);
  assert.equal(line.fraction, '3/4');
  assert.equal(line.menu_product_id, 'carne');
  assert.equal(line.observations, 'sin sal');

  ctx.state.cart = [line, { unit_price: 5000, quantity: 2 }];
  assert.equal(ctx.cartTotal(), 28750);
  assert.equal(ctx.cartLineLabel(line), '3/4 · CARNE Asada');
});

test('the order request sends the fraction and never a price', () => {
  const ctx = context();
  const choice = ctx.quantityChoices(CARNE).find((c) => c.label === '1/2');
  const payload = ctx.orderItemPayload(ctx.choiceCartLine(CARNE, choice, { term: '', observations: '', quick_notes: [] }));
  assert.equal(payload.fraction, '1/2');
  assert.equal(payload.inventory_item_id, 'carne');
  assert.equal(payload.unit_price, undefined);
  assert.equal(payload.line_total, undefined);
});

test('a classic line (switch off) is sent exactly as before, with no fraction key', () => {
  const ctx = context();
  const payload = ctx.orderItemPayload({ inventory_item_id: 'x', quantity: 2, observations: '', quick_notes: [], term: '' });
  assert.deepEqual(Object.keys(payload).sort(), ['inventory_item_id', 'observations', 'quantity', 'quick_notes', 'term']);
});

test('editing a cart line finds its menu product again', () => {
  const ctx = context({ menu: [{ key: 'carne', products: [CARNE] }, { key: 'pollo', products: [POLLO] }] });
  assert.equal(ctx.findMenuProduct('pollo').category.key, 'pollo');
  assert.equal(ctx.findMenuProduct('nope'), null);
});

test('the whole-unit selector never goes below 1, above 99, or to a fraction', () => {
  const ctx = loadKit();
  assert.equal(ctx.stepQuantity(1, -1), 1);
  assert.equal(ctx.stepQuantity(2, 1), 3);
  assert.equal(ctx.stepQuantity(99, 1), 99);
  assert.equal(ctx.stepQuantity(1.5, 0), 2);
  assert.equal(ctx.stepQuantity('abc', 0), 1);
});
