// Caja: facturacion directa. The whole hsp_cashier.js booted in a fake
// browser: the active catalog shows up (portion groups as one product per
// portion), an independent sale is charged on the spot with the chosen
// method, "Enviar a cocina" / "a una mesa" send one button instead, and
// the panel is unchanged for a company without the switch.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { source, FakeStorage, boot, flush } = require('./_cashier_boot.cjs');

function fn(name) {
  const start = source.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

const MENU = {
  categories: [
    { key: 'carnes', label: 'Carnes', products: [
      { id: 'carne', name: 'CARNE Asada', price: 25000 },
      { id: 'pollo', name: 'Pollo', is_portioned: true, portions: [
        { inventory_item_id: 'pollo-1', label: 'Entero', price: 40000 },
        { inventory_item_id: 'pollo-12', label: '1/2', price: 19000 },
      ] },
    ] },
    { key: 'bebidas', label: 'Bebidas', products: [{ id: 'gaseosa', name: 'GASEOSA Postobon', price: 4000 }] },
  ],
};

function routesWith({ directSale = true, sale = [201, { ok: true, charged: true, label: 'Venta 007' }] } = {}) {
  return (url) => {
    if (url.includes('/orders?status=active')) return [200, { orders: [{ id: 'o1', table_key: 'mesa 3', table_number: 'Mesa 3', status: 'entregado', total: 1, items: [] }] }];
    if (url.includes('/waiter-ordering/menu')) return [200, MENU];
    if (url.includes('/caja/config')) return [200, { direct_sale: directSale }];
    if (url.includes('/qr-tables')) return [200, { tables: [{ label: 'Mesa 1' }, { label: 'Mesa 3' }] }];
    if (url.includes('/caja/ventas')) return sale;
    if (url.includes('/mini-panel-refresh')) return [200, { access_token: 'renewed' }];
    return [404, {}];
  };
}

function saved() {
  const local = new FakeStorage();
  local.setItem('clonexa_cashier_token_c1', 'jwt-caja');
  return local;
}

function change(b, attr, props) {
  const target = { closest: (sel) => (sel === `[${attr}]` ? {} : null), ...props };
  (b.listeners.document.change || []).forEach((cb) => cb({ target }));
}

async function openNewSale(routes) {
  const b = boot({ local: saved(), routes });
  await flush(); await flush(); await flush();
  b.click('data-csh-new-sale');
  return b;
}

test('the whole active catalog appears, each portion as its own product', () => {
  const ctx = vm.createContext({ String, Number, Array });
  vm.runInContext(fn('saleProducts') + fn('filterSaleProducts'), ctx);
  const products = ctx.saleProducts(MENU.categories);
  assert.deepEqual(JSON.parse(JSON.stringify(products.map((p) => [p.id, p.name, p.price]))), [
    ['carne', 'CARNE Asada', 25000],
    ['pollo-1', 'Pollo Entero', 40000],
    ['pollo-12', 'Pollo 1/2', 19000],
    ['gaseosa', 'GASEOSA Postobon', 4000],
  ]);
  assert.equal(JSON.stringify(ctx.filterSaleProducts(products, 'bebidas', '').map((p) => p.id)), '["gaseosa"]');
  assert.equal(JSON.stringify(ctx.filterSaleProducts(products, '', 'pollo').map((p) => p.id)), '["pollo-1","pollo-12"]');
});

test('"Nueva venta" lists the products and charges an independent sale on the spot', async () => {
  const b = await openNewSale(routesWith());
  assert.match(b.root.innerHTML, /Nueva venta/);
  assert.match(b.root.innerHTML, /Pollo 1\/2/);
  assert.match(b.root.innerHTML, /GASEOSA Postobon/);

  b.click('data-csh-sale-add', 'gaseosa');
  b.click('data-csh-sale-add', 'gaseosa');
  b.click('data-csh-sale-add', 'pollo-12');
  assert.match(b.root.innerHTML, /data-csh-sale-pay="cash"/);   // charge right here
  assert.match(b.root.innerHTML, /\$\s?27\.000/);                // 2x4000 + 19000

  b.click('data-csh-sale-pay', 'cash');
  await flush(); await flush();
  const call = b.calls.find((c) => c.url.includes('/caja/ventas'));
  assert.deepEqual(JSON.parse(call.options.body), {
    table: '', send_to_kitchen: false, payment_method: 'cash',
    items: [{ inventory_item_id: 'gaseosa', quantity: 2 }, { inventory_item_id: 'pollo-12', quantity: 1 }],
  });
  assert.match(b.root.innerHTML, /Venta 007 cobrada/);
  assert.match(b.root.innerHTML, /Mesas abiertas/);
});

test('the request never carries a price', async () => {
  const b = await openNewSale(routesWith());
  b.click('data-csh-sale-add', 'carne');
  b.click('data-csh-sale-pay', 'card');
  await flush();
  const body = JSON.parse(b.calls.find((c) => c.url.includes('/caja/ventas')).options.body);
  assert.equal(JSON.stringify(body).includes('25000'), false);
});

test('"Enviar a cocina" replaces the payment buttons with a single send', async () => {
  const b = await openNewSale(routesWith({ sale: [201, { ok: true, charged: false, label: 'Venta 008' }] }));
  b.click('data-csh-sale-add', 'carne');
  change(b, 'data-csh-sale-kitchen', { checked: true });
  assert.doesNotMatch(b.root.innerHTML, /data-csh-sale-pay=/);
  assert.match(b.root.innerHTML, /Se cobra cuando cocina la marque lista/);
  b.click('data-csh-sale-send');
  await flush(); await flush();
  const body = JSON.parse(b.calls.find((c) => c.url.includes('/caja/ventas')).options.body);
  assert.equal(body.send_to_kitchen, true);
  assert.equal(body.payment_method, null);
  assert.match(b.root.innerHTML, /Venta 008 enviado a cocina/);
});

test('adding to a table from the table screen targets that table', async () => {
  const b = boot({ local: saved(), routes: routesWith({ sale: [201, { ok: true, charged: false, label: 'Mesa 3' }] }) });
  await flush(); await flush(); await flush();
  b.click('data-csh-open-table', 'mesa 3');
  b.click('data-csh-add-product');
  assert.match(b.root.innerHTML, /<option value="Mesa 3" selected>/);
  b.click('data-csh-sale-add', 'gaseosa');
  assert.match(b.root.innerHTML, /Agregar a Mesa 3/);
  b.click('data-csh-sale-send');
  await flush(); await flush();
  const body = JSON.parse(b.calls.find((c) => c.url.includes('/caja/ventas')).options.body);
  assert.equal(body.table, 'Mesa 3');
  assert.equal(body.send_to_kitchen, false);
});

test('the quantity buttons add and remove, and the phone back leaves the sale', async () => {
  const b = await openNewSale(routesWith());
  b.click('data-csh-sale-add', 'gaseosa');
  b.click('data-csh-sale-inc', 'gaseosa');
  assert.match(b.root.innerHTML, /<b>2<\/b>/);
  b.click('data-csh-sale-dec', 'gaseosa');
  b.click('data-csh-sale-dec', 'gaseosa');
  assert.match(b.root.innerHTML, /Toca un producto para agregarlo/);
  b.history.back();
  assert.match(b.root.innerHTML, /Mesas abiertas/);
  assert.equal(b.history.exited, false);
});

test('a failed sale stays on screen to retry', async () => {
  const b = await openNewSale(routesWith({ sale: [422, { detail: 'Selecciona un metodo de pago valido.' }] }));
  b.click('data-csh-sale-add', 'gaseosa');
  b.click('data-csh-sale-pay', 'cash');
  await flush(); await flush();
  assert.match(b.root.innerHTML, /Nueva venta/);
  assert.match(b.root.innerHTML, /GASEOSA Postobon/);
});

test('without the company switch the panel has no "Nueva venta"', async () => {
  const b = boot({ local: saved(), routes: routesWith({ directSale: false }) });
  await flush(); await flush(); await flush();
  assert.doesNotMatch(b.root.innerHTML, /Nueva venta/);
  assert.equal(b.calls.some((c) => c.url.includes('/qr-tables')), false);
});
