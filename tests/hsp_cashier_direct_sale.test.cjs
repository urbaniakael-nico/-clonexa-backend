// Caja (waiter_ordering): "Nueva venta" with the SAME visual flow as the
// mesero panel (categories with photo/emoji -> products -> product sheet
// from the shared kit -> cart), keeping the caja's destino, "Enviar a
// cocina" and cobro; table cards with timer and real state; a compact table
// detail; and "Imprimir cuenta" with the configured CUENTA DE COBRO.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { source, FakeStorage, boot, flush } = require('./_cashier_boot.cjs');

const MENU = {
  quantity_buttons: ['1/4', '1/2', '3/4', '1', '2'],
  menu_emojis: true,
  categories: [
    { key: 'pollo', label: 'Pollo', has_image: false, requires_term: false, quick_notes: ['Sin sal'], products: [
      { id: 'pollo', name: 'POLLO Asado', price: 40000, allows_portions: true, quantity_ref_id: 'pollo',
        quantity_options: [{ label: '1/4', available: true, price: 10000 }, { label: '1', available: true, price: 40000 }] },
    ] },
    { key: 'gaseosa', label: 'Gaseosa', has_image: true, products: [{ id: 'gaseosa', name: 'GASEOSA Coca Cola', price: 4500, allows_portions: false }] },
  ],
};

const T0 = Date.now();
const ago = (minutes) => new Date(T0 - minutes * 60000).toISOString();

const ORDERS = [
  // Mesa 7: opened 50 min ago, one comanda still in the kitchen.
  { id: 'o71', table_key: 'mesa 7', table_number: 'Mesa 7', status: 'entregado', total: 30000, created_at: ago(50),
    metadata: { waiter: { name: 'Laura' }, kitchen: { ready_at: ago(40), delivered_at: ago(35) } },
    items: [{ name: 'POLLO Asado', quantity: 0.75, quantity_label: '3/4', unit_price: 40000, subtotal: 30000, observations: 'bien asado' }] },
  { id: 'o72', table_key: 'mesa 7', table_number: 'Mesa 7', status: 'alistando', total: 9000, created_at: ago(5),
    metadata: { waiter: { name: 'Laura' } }, items: [{ name: 'GASEOSA Coca Cola', quantity: 2, unit_price: 4500, subtotal: 9000 }] },
  // Mesa 2: 12 min, out of the kitchen but not delivered to the table yet.
  { id: 'o21', table_key: 'mesa 2', table_number: 'Mesa 2', status: 'entregado', total: 40000, created_at: ago(12),
    metadata: { waiter: { name: 'Pedro' }, kitchen: { ready_at: ago(2) } }, items: [{ name: 'POLLO Asado', quantity: 1, unit_price: 40000, subtotal: 40000 }] },
  // Mesa 9: 80 min, everything at the table.
  { id: 'o91', table_key: 'mesa 9', table_number: 'Mesa 9', status: 'entregado', total: 4500, created_at: ago(80),
    metadata: { waiter: { name: 'Ana' }, kitchen: { ready_at: ago(70), delivered_at: ago(65) } }, items: [{ name: 'GASEOSA', quantity: 1, unit_price: 4500, subtotal: 4500 }] },
];

const DOCUMENT = {
  title: 'CUENTA DE COBRO', not_invoice_notice: 'NO ES FACTURA DE VENTA', dian_pending_notice: '',
  number: 'CC-000042', number_label: 'Consecutivo interno', issued_at: new Date(T0).toISOString(),
  issuer: { trade_name: 'El Socio', nit: '900123', regime: 'No responsable de IVA', logo_url: '', legal_name: '', address: 'Cra 1', phone: '300' },
  table: 'Mesa 7', waiter: 'Laura', lines: [{ qty: '3/4', name: 'POLLO Asado', subtotal: 30000, observations: 'bien asado' }],
  subtotal: 39000, iva: 0, total: 39000, iva_percent: 0, footer: 'Gracias por su visita', withholdings: '', resolution: '', payment_label: '',
};

function routesWith({ directSale = true, sale = [201, { ok: true, charged: true, label: 'Venta 007', order: { id: 'v7' } }], orders = ORDERS } = {}) {
  return (url) => {
    if (url.includes('/orders?status=active')) return [200, { orders }];
    if (url.includes('/waiter-ordering/menu')) return [200, MENU];
    if (url.includes('/caja/config')) return [200, { direct_sale: directSale }];
    if (url.includes('/qr-tables')) return [200, { tables: [{ label: 'Mesa 1' }, { label: 'Mesa 3' }] }];
    if (url.includes('/caja/ventas')) return sale;
    if (url.includes('/caja/documento')) return [200, { ok: true, document: DOCUMENT }];
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

function lastSheet(b) {
  return b.body.children.filter((c) => c.className === 'wtr-sheet-backdrop').pop();
}

async function ready(routes = routesWith()) {
  const b = boot({ local: saved(), routes });
  await flush(); await flush(); await flush();
  return b;
}

// ---------------------------------------------------------------------------
// Nueva venta = mesero flow (shared kit)
// ---------------------------------------------------------------------------

test('Nueva venta starts with the category grid of the mesero, emoji or photo', async () => {
  const b = await ready();
  b.click('data-csh-new-sale');
  const html = b.root.innerHTML;
  assert.match(html, /class="wtr-grid-cat"/);                       // the kit's grid
  assert.match(html, /data-csh-cat="pollo"/);
  assert.match(html, /wtr-emoji">🍗</);                               // emoji
  assert.match(html, /categories\/gaseosa\/image/);                   // photo replaces it
  assert.match(html, /Venta independiente/);
  assert.match(html, /Enviar a cocina/);
});

test('a product with portions opens the kit sheet with its fraction buttons', async () => {
  const b = await ready();
  b.click('data-csh-new-sale');
  b.click('data-csh-cat', 'pollo');
  assert.match(b.root.innerHTML, /class="wtr-grid-prod"/);
  b.click('data-csh-product', 'pollo');
  const sheet = lastSheet(b);
  assert.match(sheet.innerHTML, /data-qty-index="0"/);
  assert.match(sheet.innerHTML, /<span>1\/4<\/span>/);
  assert.match(sheet.innerHTML, /Observaciones/);
  assert.match(sheet.innerHTML, /Sin sal/);                            // quick notes of the category
  assert.match(sheet.innerHTML, /Agregar a la venta/);
});

test('a product without portions gets the whole-unit selector, and the sale is charged on the spot', async () => {
  const b = await ready();
  b.click('data-csh-new-sale');
  b.click('data-csh-cat', 'gaseosa');
  b.click('data-csh-product', 'gaseosa');
  const sheet = lastSheet(b);
  assert.match(sheet.innerHTML, /wtr-stepper/);
  assert.doesNotMatch(sheet.innerHTML, /data-qty-index/);
  sheet.querySelector('[data-sheet-add]').fire('click');
  assert.match(b.root.innerHTML, /1 x GASEOSA Coca Cola/);
  assert.match(b.root.innerHTML, /data-csh-sale-pay="cash"/);          // independent + no kitchen -> charge here

  b.click('data-csh-sale-pay', 'cash');                                 // Efectivo -> calculadora de cambio
  const cash = b.body.children.find((c) => /csh-cash-backdrop/.test(c.className));
  assert.ok(cash, 'cash calculator');
  assert.equal(b.calls.some((c) => c.url.includes('/caja/ventas')), false);   // nothing charged yet
  cash.querySelector('[data-cash-bill="10000"]').fire('click');
  cash.querySelector('[data-cash-send]').fire('click');
  await flush(); await flush();
  const body = JSON.parse(b.calls.find((c) => c.url.includes('/caja/ventas')).options.body);
  assert.deepEqual(body, {
    table: '', send_to_kitchen: false, payment_method: 'cash',
    items: [{ inventory_item_id: 'gaseosa', quantity: 1, observations: '', quick_notes: [], term: '' }],
  });
  assert.match(b.root.innerHTML, /Venta 007 cobrada\. Cambio: \$\s?5\.500\./);   // 10.000 - 4.500
  assert.match(b.root.innerHTML, /Última cobrada: <b>Venta 007<\/b>/);
});

test('a fraction line goes to the server as the fraction, never as a price (inventory deducted like the mesero)', async () => {
  const b = await ready(routesWith({ sale: [201, { ok: true, charged: false, label: 'Mesa 3', order: { id: 'x' } }] }));
  b.click('data-csh-new-sale');
  change(b, 'data-csh-sale-table', { value: 'Mesa 3' });
  change(b, 'data-csh-sale-kitchen', { checked: true });
  b.click('data-csh-cat', 'pollo');
  b.click('data-csh-product', 'pollo');
  lastSheet(b).querySelector('[data-sheet-add]').fire('click');     // default choice: "1"
  assert.match(b.root.innerHTML, /1 · POLLO Asado/);
  assert.match(b.root.innerHTML, /Enviar a cocina/);
  b.click('data-csh-sale-send');
  await flush(); await flush();
  const body = JSON.parse(b.calls.find((c) => c.url.includes('/caja/ventas')).options.body);
  assert.equal(body.table, 'Mesa 3');
  assert.equal(body.send_to_kitchen, true);
  assert.equal(body.payment_method, null);
  assert.deepEqual(body.items, [{ inventory_item_id: 'pollo', quantity: 1, observations: '', quick_notes: [], term: '', fraction: '1' }]);
  assert.equal(JSON.stringify(body).includes('40000'), false);
});

test('cart lines can be removed, and the phone back walks products -> categories -> tables', async () => {
  const b = await ready();
  b.click('data-csh-new-sale');
  b.click('data-csh-cat', 'gaseosa');
  b.click('data-csh-product', 'gaseosa');
  lastSheet(b).querySelector('[data-sheet-add]').fire('click');
  b.click('data-csh-sale-remove', '0');
  assert.match(b.root.innerHTML, /Elige una categoría y agrega productos/);
  b.history.back();
  assert.match(b.root.innerHTML, /class="wtr-grid-cat"/);
  b.history.back();
  assert.match(b.root.innerHTML, /Mesas abiertas/);
  assert.equal(b.history.exited, false);
});

test('the caja reuses the mesero components instead of copying them', () => {
  for (const name of ['menuEmoji', 'quantityChoices', 'openItemSheet', 'categoryGridHtml', 'stepQuantity']) {
    assert.doesNotMatch(source, new RegExp(`function ${name}\\(`), name);
  }
  assert.match(source, /Kit\.openItemSheet\(/);
  assert.match(source, /Kit\.categoryGridHtml\(/);
  assert.match(source, /Kit\.productGridHtml\(/);
});

// ---------------------------------------------------------------------------
// Mesas abiertas: cards
// ---------------------------------------------------------------------------

test('each card shows the big number, timer, mesero, total and real state, oldest first', async () => {
  const b = await ready();
  const html = b.root.innerHTML;
  const order = ['mesa 9', 'mesa 7', 'mesa 2'].map((key) => html.indexOf(`data-csh-open-table="${key}"`));
  assert.ok(order[0] < order[1] && order[1] < order[2], 'oldest table first');

  const card = (key) => html.slice(html.indexOf(`data-csh-open-table="${key}"`), html.indexOf('</button>', html.indexOf(`data-csh-open-table="${key}"`)));
  assert.match(card('mesa 7'), /<small>Mesa<\/small><b>7<\/b>/);
  assert.match(card('mesa 7'), /⏱ 50 min/);
  assert.match(card('mesa 7'), /Mesero: Laura/);
  assert.match(card('mesa 7'), /\$\s?39\.000/);
  assert.match(card('mesa 7'), /En preparación/);                       // one comanda still in the kitchen
  assert.match(card('mesa 2'), /Listo para cobrar/);                    // out of the kitchen, not at the table
  assert.match(card('mesa 9'), /Listo para cobrar/);                    // kitchen marked Entregado: still to charge
  assert.match(card('mesa 9'), /⏱ 1 h 20 min/);
  assert.doesNotMatch(html, /Entregado/i);                              // the caja never shows "Entregado"
});

// ---------------------------------------------------------------------------
// Table detail + print
// ---------------------------------------------------------------------------

test('the table detail lists quantity/portion, product and value, and the total', async () => {
  const b = await ready();
  b.click('data-csh-open-table', 'mesa 7');
  const html = b.root.innerHTML;
  assert.match(html, /<h1>Mesa 7<\/h1>/);
  assert.match(html, /<td>3\/4<\/td>\s*<td>POLLO Asado/);
  assert.match(html, /bien asado/);
  assert.match(html, /<td>2×<\/td>\s*<td>GASEOSA Coca Cola/);
  assert.match(html, /<tfoot><tr><td colspan="2">Total<\/td><td>\$\s?39\.000<\/td>/);
  assert.match(html, /Datos de cobro/);
  assert.match(html, /data-csh-print/);
});

test('Imprimir cuenta asks the server for the document and prints a CUENTA DE COBRO that is NOT a factura', async () => {
  const b = await ready();
  b.click('data-csh-open-table', 'mesa 7');
  b.click('data-csh-print');
  await flush(); await flush();
  const request = b.calls.find((c) => c.url.includes('/caja/documento'));
  assert.deepEqual(JSON.parse(request.options.body), { order_ids: ['o71', 'o72'] });
  const frame = b.body.children.find((c) => c.tagName === 'iframe');
  assert.ok(frame, 'print frame');
  assert.match(frame.written, /CUENTA DE COBRO/);
  assert.match(frame.written, /NO ES FACTURA DE VENTA/);
  assert.match(frame.written, /CC-000042/);
  assert.match(frame.written, /El Socio/);
  assert.match(frame.written, /Gracias por su visita/);
  assert.match(frame.written, /@page\{size:80mm auto/);
});

test('without the company switch the caja has no "Nueva venta"', async () => {
  const b = await ready(routesWith({ directSale: false }));
  assert.doesNotMatch(b.root.innerHTML, /Nueva venta/);
  assert.equal(b.calls.some((c) => c.url.includes('/qr-tables')), false);
});
