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

const NAMES = [
  'cxHspMoney024R', 'cxHspPaymentLabel024V', 'cxHspPaymentMethod024V', 'cxHspNormKey024Y',
  'cxHspTableKey024Y', 'cxHspItemKey024Y', 'cxHspItemSubtotal024Y', 'cxHspIsBarAccount031D',
  'cxHspIsBarOnlyOrder031D', 'cxHspGroupAccounts024Y', 'cxHspMergedTableCards024Y',
  'cxHspClosedReference031R', 'cxHspClosedTableGroups031R', 'cxHspCloseControls030A',
  'cxHspTableSlots034B', 'cxHspTableStart034B', 'cxHspOrderTime034B', 'cxHspOrderCustomers034B',
  'cxHspNewOrderBlock034B', 'cxHspTableQuickAdd034B', 'cxHspTableCard034B', 'cxHspClosedStrip034B',
];

function board(orders, qrTables) {
  const context = vm.createContext({
    document: { getElementById: () => null },
    h: (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
    Intl, Date, Math, Number, String, Array, Map, Set, JSON,
  });
  vm.runInContext(
    `var cxHspOrders024R = ${JSON.stringify(orders)}; var cxHspQrTables034B = ${JSON.stringify(qrTables)};\n`
      + NAMES.map(fn).join('\n'),
    context,
  );
  return context;
}

const QR = Array.from({ length: 12 }, (_, i) => ({ label: `Mesa ${i + 1}`, table_key: `mesa ${i + 1}`, access_active: false }));
const item = (name, qty, price) => ({ inventory_item_id: name, name, quantity: qty, unit_price: price, subtotal: qty * price });
const order = (id, table, status, items, extra = {}) => ({
  id, table_number: table, table_key: table.toLowerCase(), status, items,
  total: items.reduce((s, i) => s + i.subtotal, 0), created_at: '2026-09-21T22:00:00Z',
  people: [{ name: extra.customer || 'nicolas', total: items.reduce((s, i) => s + i.subtotal, 0), items }],
  source: extra.source || 'qr_table', ...extra,
});

test('always shows one card per configured table, free ones included', () => {
  const ctx = board([], QR);
  const slots = ctx.cxHspTableSlots034B();
  assert.equal(slots.length, 12);
  const html = ctx.cxHspTableCard034B(slots[0]);
  assert.match(html, /is-free/);
  assert.match(html, /Libre/);
  assert.doesNotMatch(html, /data-hsp-timer-start/);
  assert.match(html, /data-hsp-quick-add-table="Mesa 1"/, 'a free table can be opened from the bar');
});

test('a new QR order lights the card, highlights products and blocks closing', () => {
  const orders = [
    order('a', 'Mesa 1', 'entregado', [item('AGUA Cristal', 1, 4000)]),
    order('b', 'Mesa 1', 'pendiente', [item('CERVEZA Poker', 3, 4000)], { customer: 'laura', created_at: '2026-09-21T22:10:00Z' }),
  ];
  const ctx = board(orders, QR);
  const html = ctx.cxHspTableCard034B(ctx.cxHspTableSlots034B()[0]);
  assert.match(html, /is-new/);
  assert.match(html, /Nuevo pedido · laura/);
  assert.match(html, /3 x<\/b> CERVEZA Poker/);
  assert.match(html, /data-hsp-deliver="b" data-hsp-deliver-status="pendiente"/);
  assert.match(html, /data-hsp-reject="b"/);
  assert.match(html, /Entrega el pedido nuevo para poder cerrar/);
  assert.doesNotMatch(html, /Cerrar mesa/);
  assert.match(html, /\$\s?16\.000/, 'total mesa sums delivered + new');
  assert.match(html, /data-hsp-quick-add="a"/, 'barman adds into the delivered order, not the glowing one');
});

test('fully delivered table shows timer, products, people and the payment close controls', () => {
  const ctx = board([order('a', 'Mesa 3', 'entregado', [item('AGUA Cristal', 1, 4000)])], QR);
  const html = ctx.cxHspTableCard034B(ctx.cxHspTableSlots034B()[2]);
  assert.match(html, /is-active/);
  assert.match(html, /data-hsp-timer-start="2026-09-21T22:00:00/);
  assert.match(html, /1 x AGUA Cristal/);
  assert.match(html, /<span>nicolas<\/span>/);
  assert.match(html, /Modo de pago obligatorio/);
  assert.match(html, /data-hsp-close-ids="a"/);
});

test('timer prefers the QR activation time when the table is active', () => {
  const qr = QR.map((t, i) => (i === 4 ? { ...t, access_active: true, access_activated_at: '2026-09-21T21:30:00Z' } : t));
  const ctx = board([], qr);
  const html = ctx.cxHspTableCard034B(ctx.cxHspTableSlots034B()[4]);
  assert.match(html, /is-active/);
  assert.match(html, /data-hsp-timer-start="2026-09-21T21:30:00Z"/);
});

test('orders on tables outside the configured list are never hidden; bar accounts stay out', () => {
  const orders = [
    order('x', 'Terraza VIP', 'entregado', [item('AGUA Cristal', 1, 4000)]),
    order('y', 'Barra', 'entregado', [item('AGUA Cristal', 1, 4000)], { source: 'bar_account' }),
  ];
  const ctx = board(orders, QR);
  const labels = ctx.cxHspTableSlots034B().map((slot) => slot.label);
  assert.equal(labels.length, 13);
  assert.ok(labels.includes('Terraza VIP'));
  assert.ok(!labels.includes('Barra'));
});

test('closed tables go to the bottom strip, archived ones do not', () => {
  const orders = [
    order('c1', 'Mesa 2', 'cerrado', [item('AGUA Cristal', 2, 4000)], { payment_method: 'cash' }),
    order('c2', 'Mesa 6', 'cerrado', [item('AGUA Cristal', 1, 4000)], { archived_at: '2026-09-20T08:16:31Z' }),
  ];
  const ctx = board(orders, QR);
  const strip = ctx.cxHspClosedStrip034B();
  assert.match(strip, /Mesa 2/);
  assert.match(strip, /\$\s?8\.000/);
  assert.doesNotMatch(strip, /Mesa 6/);
  assert.equal(ctx.cxHspTableSlots034B().filter((s) => s.orders.length).length, 0, 'closed tables free their card');
});
