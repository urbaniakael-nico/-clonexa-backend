// Cuentas por persona con la carta de bar (qr_bar_menu), de punta a punta:
// dos teléfonos escanean el mismo QR de la mesa, cada uno queda con su
// cuenta, la pantalla del cliente muestra el desglose por persona y el
// tablero real del barman (client.js) suma ambas y cierra la mesa completa.
//
// El servidor falso guarda cada pedido con la misma forma que
// create_hospitality_order (people[0].account_id) y agrupa la cuenta por
// account_id; la agrupación real del servidor la prueba
// test_hospitality_qr_bar_accounts.py con estos mismos pedidos.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { boot, flush, FakeStorage } = require('./_qr_order_boot.cjs');

const INVENTORY = [
  { id: 'aguila', name: 'Cerveza Aguila', price: 6000 },
  { id: 'guaro', name: 'Aguardiente Antioqueño media', price: 60000 },
  { id: 'marlboro', name: 'Cigarrillos Marlboro', price: 1500 },
];

function fakeBarServer() {
  const orders = [];
  const accountFor = (accountId) => {
    const accounts = new Map();
    orders.forEach((order) => order.people.forEach((person) => {
      const row = accounts.get(person.account_id) || {
        account_id: person.account_id, name: person.name, total: 0, orders_count: 0, items: [],
        is_current: person.account_id === accountId,
      };
      row.total += person.total;
      row.orders_count += 1;
      row.items.push(...person.items);
      accounts.set(person.account_id, row);
    }));
    const list = [...accounts.values()].sort((a, b) => Number(b.is_current) - Number(a.is_current) || b.total - a.total);
    const current = list.find((row) => row.is_current) || null;
    return {
      total: orders.reduce((sum, order) => sum + order.total, 0),
      orders_count: orders.length,
      accounts_count: list.length,
      items: orders.flatMap((order) => order.items),
      accounts: list,
      current_account: current,
      current_total: current ? current.total : 0,
    };
  };
  const routes = (url, options = {}) => {
    const method = options.method || 'GET';
    const body = options.body ? JSON.parse(options.body) : {};
    if (/\/companies\/c1$/.test(url)) return [401, { detail: 'Token requerido.' }];
    if (url.includes('/branding')) return [200, { branding: {} }];
    if (url.includes('/qr-tables/access/verify')) return [200, { access: { active: true } }];
    if (url.includes('/qr-tables/access?')) return [200, { access: { active: true }, company_name: 'The Time Machine', ui: { bar_menu: true } }];
    if (url.includes('/qr-tables/account')) return [200, { account: accountFor(body.account_id) }];
    if (url.includes('/inventory-lite')) return [200, { inventory: INVENTORY }];
    if (url.endsWith('/orders') && method === 'POST') {
      const items = body.items.map((item) => ({
        inventory_item_id: item.inventory_item_id, name: item.name, quantity: item.quantity,
        unit_price: item.unit_price, subtotal: item.quantity * item.unit_price,
      }));
      const total = items.reduce((sum, item) => sum + item.subtotal, 0);
      const order = {
        id: `o${orders.length + 1}`, order_number: `QR-${orders.length + 1}`,
        table_number: body.table, table_key: body.table.toLowerCase(), source: 'qr', status: 'pendiente',
        customer_name: body.customer, items, total, created_at: `2026-09-23T22:0${orders.length}:00Z`,
        people: [{ id: body.account_id, account_id: body.account_id, name: body.customer, total, items }],
        metadata: { account_id: body.account_id },
      };
      orders.push(order);
      return [200, { order }];
    }
    return [200, {}];
  };
  return { orders, routes };
}

async function settle() {
  for (let i = 0; i < 8; i += 1) await flush();
}

async function phone(server) {
  // cada teléfono tiene su propio almacenamiento (su propio navegador)
  const page = boot({ routes: server.routes, local: new FakeStorage() });
  await settle();
  page.input('qrAccessCode025B', 'MESA5');
  page.click('data-access-verify');
  await settle();
  return page;
}

async function order(page, name, picks) {
  page.type('qrCustomer024S', name);
  for (const [id, qty] of picks) {
    page.click('data-add', id);
    for (let i = 1; i < qty; i += 1) page.click('data-inc', id);
  }
  page.click('data-cart-open');
  page.click('data-submit-order');
  await settle();
  page.click('data-bar-sent-close');
}

const orderPosts = (page) => page.calls
  .filter((c) => c.url.endsWith('/orders') && c.options.method === 'POST')
  .map((c) => JSON.parse(c.options.body));

function barmanBoard(orders) {
  const source = readFileSync('app/web/client.js', 'utf8');
  const fn = (name) => {
    const start = source.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
    assert.ok(start >= 0, name);
    const tail = source.slice(start + 3);
    const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
    return (next < 0 ? tail : tail.slice(0, next)) + '\n';
  };
  const names = [
    'cxHspMoney024R', 'cxHspPaymentLabel024V', 'cxHspPaymentMethod024V', 'cxHspNormKey024Y',
    'cxHspTableKey024Y', 'cxHspItemKey024Y', 'cxHspItemSubtotal024Y', 'cxHspIsBarAccount031D',
    'cxHspIsBarOnlyOrder031D', 'cxHspGroupAccounts024Y', 'cxHspMergedTableCards024Y',
    'cxHspCloseControls030A', 'cxHspTableSlots034B', 'cxHspTableStart034B', 'cxHspOrderTime034B',
    'cxHspOrderCustomers034B', 'cxHspNewOrderBlock034B', 'cxHspTableQuickAdd034B', 'cxHspTableCard034B',
  ];
  const context = vm.createContext({
    document: { getElementById: () => null },
    h: (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
    Intl, Date, Math, Number, String, Array, Map, Set, JSON,
  });
  const qrTables = [{ label: 'Mesa 5', table_key: 'mesa 5', access_active: true }];
  vm.runInContext(
    `var cxHspOrders024R = ${JSON.stringify(orders)}; var cxHspQrTables034B = ${JSON.stringify(qrTables)};\n`
      + names.map(fn).join('\n'),
    context,
  );
  const slots = context.cxHspTableSlots034B();
  assert.equal(slots.length, 1, 'una sola tarjeta para la mesa');
  const slot = slots[0];
  return context.cxHspTableCard034B(slot);
}

const money = (n) => `\\$\\s?${n.toLocaleString('de-DE')}`;

test('dos personas en la misma mesa: cuentas separadas y el total de la mesa suma ambas', async () => {
  const server = fakeBarServer();
  const laura = await phone(server);
  const nico = await phone(server);

  await order(laura, 'Laura', [['aguila', 2]]);           // 12.000
  await order(nico, 'Nico', [['guaro', 1]]);              // 60.000
  await order(laura, 'Laura', [['marlboro', 1]]);         // 1.500 -> Laura 13.500

  // 1. cada teléfono queda identificado aparte, y siempre con el mismo id
  const [l1, l2] = orderPosts(laura);
  const [n1] = orderPosts(nico);
  assert.match(l1.account_id, /^qr_account_/);
  assert.match(n1.account_id, /^qr_account_/);
  assert.notEqual(l1.account_id, n1.account_id, 'dos teléfonos = dos cuentas');
  assert.equal(l2.account_id, l1.account_id, 'el mismo teléfono sigue en su cuenta');
  assert.deepEqual([l1.customer, n1.customer], ['Laura', 'Nico']);
  assert.ok([l1, l2, n1].every((p) => p.source === 'qr' && p.access_code === 'MESA5' && p.table === 'Mesa 5'));

  // 2. el pedido de cada uno se suma a su propia cuenta (vista de cada cliente)
  laura.runIntervals();                                    // refresco periódico de la cuenta
  nico.runIntervals();
  await settle();
  laura.click('data-cart-close');                          // re-render
  nico.click('data-cart-close');
  const lauraHtml = laura.html();
  const nicoHtml = nico.html();

  assert.match(lauraHtml, new RegExp(`id="qrTableAccountTotal030B">${money(73500)}<`), 'total de la mesa = 13.500 + 60.000');
  assert.match(nicoHtml, new RegExp(`id="qrTableAccountTotal030B">${money(73500)}<`));
  assert.match(lauraHtml, /2 cuentas · 3 pedidos/);

  // 3. desglose por persona en la pantalla del cliente (carta de bar)
  const person = (name, orders, mine, total) => new RegExp(
    `<section class="qr-person-account${mine ? ' current' : ''}">[\\s\\S]*?<strong>${name}</strong>\\s*`
      + `<small>${orders} pedido\\(s\\)${mine ? ' · Tu cuenta' : ''}</small>[\\s\\S]*?<b>${money(total)}</b>`,
  );
  assert.match(lauraHtml, person('Laura', 2, true, 13500));
  assert.match(lauraHtml, person('Nico', 1, false, 60000));
  assert.match(nicoHtml, person('Nico', 1, true, 60000));
  assert.match(nicoHtml, person('Laura', 2, false, 13500));
  assert.equal((lauraHtml.match(/ · Tu cuenta/g) || []).length, 1, 'solo una cuenta marcada como propia');
  assert.match(lauraHtml, /data-bar-line="account"/, 'el desglose vive en la línea colapsable nueva');

  // 4. panel del barman: una tarjeta de mesa con cada persona y el total
  server.orders.forEach((o) => { o.status = 'entregado'; });
  const card = barmanBoard(server.orders);
  assert.match(card, new RegExp(`Total mesa</span><strong>${money(73500)}</strong>`));
  assert.match(card, new RegExp(`<summary><span>Nico</span><strong>${money(60000)}</strong></summary>`));
  assert.match(card, new RegExp(`<summary><span>Laura</span><strong>${money(13500)}</strong></summary>`));
  assert.match(card, /2 x Cerveza Aguila/);
  assert.match(card, /1 x Cigarrillos Marlboro/);

  // 5. el cierre de mesa cobra el total: cierra los 3 pedidos de ambas cuentas
  assert.match(card, /data-hsp-close-total="73500"/);
  const ids = /data-hsp-close-ids="([^"]+)"/.exec(card)[1].split('|').sort();
  assert.deepEqual(ids, ['o1', 'o2', 'o3']);
});

test('dos personas sin escribir nombre siguen separadas por teléfono', async () => {
  const server = fakeBarServer();
  const a = await phone(server);
  const b = await phone(server);
  await order(a, '', [['aguila', 1]]);
  await order(b, '', [['aguila', 1]]);
  const [pa] = orderPosts(a);
  const [pb] = orderPosts(b);
  assert.notEqual(pa.account_id, pb.account_id);
  a.runIntervals();
  await settle();
  a.click('data-cart-close');
  assert.match(a.html(), /2 cuentas · 2 pedidos/);
  assert.equal((a.html().match(/ · Tu cuenta/g) || []).length, 1);
});

test('el desglose por persona se ve dentro de la línea de cuenta (no como flotante oculto)', async () => {
  const server = fakeBarServer();
  const page = await phone(server);
  const barCss = page.ctx.document.getElementById('hspQrBarStyles047A');
  assert.ok(barCss, 'estilos de la carta de bar cargados');
  // .qr-table-breakdown-panel es un desplegable absoluto en la pantalla clásica;
  // dentro de la línea colapsable de la carta de bar debe fluir en su sitio.
  assert.match(barCss.textContent, /\.qrb-line \.qr-table-breakdown-panel\{position:static;/);
  assert.match(page.html(), /<div class="qrb-line-body">[\s\S]*?id="qrTableAccountBreakdown033C" class="qr-table-breakdown-panel"/);
});
