// 049Z: el panel de caja muestra solo lo que requiere acción. Lo cobrado sale
// de la lista y queda en «Cobrados» (plegado, con buscador por número, monto,
// cliente o método, detalle y reimpresión). Sin nada pendiente: «Todo al día»
// y nada más. Los indicadores del turno no cambian.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { FakeStorage, boot, flush } = require('./_cashier_boot.cjs');

const now = () => new Date().toISOString();
const OPEN_SALE = { id: 'v14', table_key: 'venta 014', table_number: 'Venta 014', status: 'listo', total: 23000, created_at: now(),
  metadata: { cashier_sale: { kind: 'independiente' } }, items: [{ name: 'Pollo asado', quantity: 1, subtotal: 23000, ready: true }] };
const CHARGED = [
  { key: 'v14', order_ids: ['v14'], label: 'Venta 014', channel: 'venta_directa', channel_label: 'Venta directa en caja', numbers: ['00014'],
    document_number: 'CC-000031', customer: '', waiter: '', total: 23000, method: 'cash', method_label: 'Efectivo', closed_at: now(),
    items: [{ qty: '1', name: 'Pollo asado', subtotal: 23000 }] },
  { key: 'd1', order_ids: ['d1'], label: 'Domicilio 0042', channel: 'domicilio', channel_label: 'Domicilio', numbers: ['0042'],
    document_number: '', customer: 'Ana Pérez', waiter: '', total: 45000, method: 'transfer', method_label: 'Transferencia', closed_at: now(),
    items: [{ qty: '2', name: 'Pollo asado', subtotal: 40000 }, { qty: '1', name: 'Valor domicilio', subtotal: 5000 }] },
  { key: 'm1|m2', order_ids: ['m1', 'm2'], label: 'Mesa 7', channel: 'mesa', channel_label: 'Mesa', numbers: ['0101', '0102'],
    document_number: '', customer: '', waiter: 'Laura', total: 84000, method: 'card', method_label: 'Tarjeta', closed_at: now(),
    items: [{ qty: '2', name: 'Cerveza', subtotal: 14000 }, { qty: '1', name: 'Parrillada', subtotal: 70000 }] },
];

function summary(charged) {
  const total = charged.reduce((s, r) => s + r.total, 0);
  return { sold: total + 23000, charged: total, pending: 23000, orders: 5, accounts: 4, ticket: 40000, deliveries: 1, tables: 1,
    methods: [{ method: 'cash', label: 'Efectivo', total: 23000, count: 1 }], direct_sales: [], deliveries_paid: [], charged_accounts: charged };
}

function setup({ orders, charged }) {
  const world = { orders, summary: summary(charged), documents: [] };
  const routes = (url, options = {}) => {
    if (url.includes('/caja/documento')) {
      world.documents.push(JSON.parse(options.body));
      return [200, { ok: true, document: { title: 'CUENTA DE COBRO', lines: [], total: 0 } }];
    }
    if (url.includes('/orders?status=active')) return [200, { orders: world.orders }];
    if (url.includes('/waiter-ordering/menu')) return [200, { categories: [] }];
    if (url.includes('/waiter-ordering/caja/config')) return [200, { direct_sale: true, delivery: true, redesign: true, delivery_print: true }];
    if (url.includes('/caja/resumen')) return [200, world.summary];
    if (url.includes('/close-table')) return [200, { ok: true }];
    if (url.includes('/caja-arqueo/')) return [403, { detail: 'off' }];
    if (url.includes('/mini-panel-operational-session')) return [200, { operational_session: { status: 'active', active_seconds: 0, break_seconds: 0 } }];
    return [404, {}];
  };
  return { world, routes };
}

async function ready(opts) {
  const local = new FakeStorage();
  local.setItem('clonexa_cashier_token_c1', 'jwt');
  const { world, routes } = setup(opts);
  const b = boot({ local, routes });
  for (let i = 0; i < 8; i += 1) await flush();
  return { b, world };
}

async function settle() { for (let i = 0; i < 6; i += 1) await flush(); }

function typeSearch(b, value) {
  const target = { value, closest: (sel) => (sel === '[data-csh-charged-q]' ? {} : null) };
  (b.listeners.document.input || []).forEach((cb) => cb({ target }));
}

const sections = (html) => (html.match(/class="cx5-sec cx5-sec-/g) || []).length;

test('una venta cobrada desaparece de la lista principal', async () => {
  const { b, world } = await ready({ orders: [OPEN_SALE], charged: CHARGED.slice(1) });
  assert.match(b.root.innerHTML, /data-csh-open-table="venta 014"/);
  assert.match(b.root.innerHTML, /Ventas por cobrar/);
  // Se cobra: ya no está entre los pedidos abiertos y pasa a los cobrados.
  world.orders = [];
  world.summary = summary(CHARGED);
  (b.listeners.document.visibilitychange || []).forEach((cb) => cb());
  await settle();
  assert.doesNotMatch(b.root.innerHTML, /Venta 014/);
  assert.doesNotMatch(b.root.innerHTML, /Domicilio 0042|Mesa 7/, 'lo cobrado nunca aparece en la pantalla principal');
});

test('se encuentra en «Cobrados» por número, monto, cliente o método, se ve el detalle y se reimprime', async () => {
  const { b, world } = await ready({ orders: [], charged: CHARGED });
  assert.match(b.root.innerHTML, /data-csh-charged-open[^>]*>✓ Cobrados <span class="cx5-count-soft">3</);
  b.click('data-csh-charged-open');
  await settle();
  const list = () => b.root.innerHTML.slice(b.root.innerHTML.indexOf('id="cx5ChargedList"'));
  assert.match(list(), /Venta 014/); assert.match(list(), /Domicilio 0042/); assert.match(list(), /Mesa 7/);

  const only = (query, label) => {
    typeSearch(b, query);
    const html = list();
    for (const other of ['Venta 014', 'Domicilio 0042', 'Mesa 7']) {
      if (other === label) assert.match(html, new RegExp(other), `${query} → ${label}`);
      else assert.doesNotMatch(html, new RegExp(other), `${query} no debe traer ${other}`);
    }
  };
  only('0042', 'Domicilio 0042');          // número de venta
  only('$45.000', 'Domicilio 0042');       // monto con formato
  only('84000', 'Mesa 7');                 // monto
  only('ana', 'Domicilio 0042');           // cliente, sin tilde
  only('efectivo', 'Venta 014');           // método de pago
  only('CC-000031', 'Venta 014');          // consecutivo del documento
  typeSearch(b, 'nada que ver');
  assert.match(list(), /Nada coincide/);

  typeSearch(b, 'mesa 7');
  b.click('data-csh-charged-view', 'm1|m2');
  await settle();
  assert.match(list(), /Parrillada/);
  assert.match(list(), /Atendió: Laura/);
  b.click('data-csh-print-ids', 'm1,m2');
  await settle();
  assert.deepEqual(world.documents[0], { order_ids: ['m1', 'm2'] }, 'la mesa se reimprime con todos sus pedidos');
});

test('con todo cobrado la pantalla muestra «Todo al día» y nada más', async () => {
  const { b } = await ready({ orders: [], charged: CHARGED });
  const html = b.root.innerHTML;
  assert.match(html, /data-cx5-idle/);
  assert.match(html, /Todo al día/);
  assert.equal(sections(html), 0, 'ninguna lista: ni vacías ni de cobrados');
  assert.doesNotMatch(html, /Venta 014|Domicilio 0042|Mesa 7/);
  assert.doesNotMatch(html, /id="cx5ChargedList"/, '«Cobrados» está plegado');
});

test('los indicadores siguen mostrando el total del turno', async () => {
  const { b } = await ready({ orders: [OPEN_SALE], charged: CHARGED.slice(1) });
  const html = b.root.innerHTML;
  assert.match(html, /data-cx5-kpi="sold">\$\s?152\.000</);
  assert.match(html, /Cobrado \$\s?129\.000 · Por cobrar \$\s?23\.000/);
});
