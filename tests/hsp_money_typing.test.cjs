// 049X: los campos de dinero se escriben con naturalidad. El "Total contado"
// del arqueo se borraba mientras el cajero escribía: el sondeo de mesas (cada
// 4 s) redibujaba el panel con el arqueo abierto y el campo volvía vacío. Se
// simula escribir dígito por dígito, con sondeos entre tecla y tecla, y el
// valor final debe ser exactamente el que se escribió.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const { FakeStorage, boot, flush } = require('./_cashier_boot.cjs');

const MENU = { quantity_buttons: [], quantity_picker: true, menu_emojis: false, categories: [
  { key: 'bebidas', label: 'Bebidas', has_image: false, quick_notes: [], products: [
    { id: 'gaseosa', name: 'GASEOSA', price: 4500, allows_portions: false },
    { id: 'pollo', name: 'POLLO', price: 28000, allows_portions: true },
  ] },
] };

function routes(calls = []) {
  return (url, options = {}) => {
    if (url.includes('/caja-arqueo/') && url.endsWith('/caja/config')) return [200, { enabled: true, denominations: [50000, 20000, 10000] }];
    if (url.includes('/caja-arqueo/') && url.endsWith('/caja/arqueo') && options.method === 'POST') {
      calls.push(JSON.parse(options.body));
      return [200, { id: 'a1', counted: 185000, expected: 185000, difference: 0, base: 0, cash_sales: 185000, needs_observation: false }];
    }
    if (url.includes('/caja-arqueo/') && url.endsWith('/caja/arqueo')) return [200, { count: null }];
    if (url.includes('/orders?status=active')) return [200, { orders: [] }];
    if (url.includes('/waiter-ordering/menu')) return [200, MENU];
    if (url.includes('/waiter-ordering/caja/config')) return [200, { direct_sale: true, redesign: true }];
    if (url.includes('/caja/resumen')) return [200, { sold: 0, charged: 0, pending: 0, orders: 0, accounts: 0, ticket: 0, deliveries: 0, tables: 0, methods: [], direct_sales: [] }];
    if (url.includes('/caja/ventas')) return [201, { ok: true, charged: true, label: 'Venta 030', order: { id: 'v30' } }];
    if (url.includes('/mini-panel-operational-session')) return [200, { operational_session: { status: 'active', active_seconds: 100, break_seconds: 0 } }];
    if (url.includes('/qr-tables')) return [200, { tables: [] }];
    return [404, {}];
  };
}

async function ready(calls) {
  const local = new FakeStorage();
  local.setItem('clonexa_cashier_token_c1', 'jwt');
  const b = boot({ local, routes: routes(calls) });
  for (let i = 0; i < 6; i += 1) await flush();
  return b;
}

// Una tecla: el navegador cambia el valor del campo y avisa "input".
function key(b, attr, value, attrValue = '') {
  const target = { value, getAttribute: () => attrValue, closest: (sel) => (sel === `[${attr}]` ? {} : null) };
  (b.listeners.document.input || []).forEach((cb) => cb({ target }));
  return target;
}

// Un sondeo de fondo (el mismo camino que el intervalo de 4 s).
async function poll(b) {
  (b.listeners.document.visibilitychange || []).forEach((cb) => cb());
  await flush(); await flush();
}

async function openArqueo(b) {
  b.click('data-csh-shift-finish');
  await flush(); await flush();
  assert.match(b.root.innerHTML, /Arqueo de caja/);
}

test('arqueo: "Total contado" dígito por dígito, con sondeos en medio, queda 185000', async () => {
  const calls = [];
  const b = await ready(calls);
  await openArqueo(b);
  let typed = '';
  for (const digit of '185000') {
    typed += digit;
    const field = key(b, 'data-csh-arq-total', typed);
    assert.equal(field.value, typed, 'la tecla no se reescribe');
    await poll(b);                                                  // antes: aquí se borraba
    assert.match(b.root.innerHTML, /Arqueo de caja/);
  }
  b.click('data-csh-arq-submit');
  await flush(); await flush();
  assert.deepEqual(calls, [{ counted: 185000 }]);
});

test('arqueo: aunque algo redibuje, lo escrito sigue en el campo y la lectura en pesos va aparte', async () => {
  const b = await ready([]);
  await openArqueo(b);
  key(b, 'data-csh-arq-total', '1');
  key(b, 'data-csh-arq-total', '18');
  key(b, 'data-csh-arq-total', '185.000');                           // con el punto de miles
  b.click('data-csh-arq-cancel');                                     // cierra...
  await openArqueo(b);                                                // ...un arqueo nuevo empieza vacío
  assert.match(b.root.innerHTML, /data-csh-arq-total placeholder="\$ contado" value=""/);
  key(b, 'data-csh-arq-total', '2');
  key(b, 'data-csh-arq-total', '25');
  key(b, 'data-csh-arq-total', '250000');
  b.click('data-csh-arq-submit');                                     // un redibujo cualquiera (botón ocupado)
  assert.match(b.root.innerHTML, /data-csh-arq-total placeholder="\$ contado" value="250000"/);
  assert.match(b.root.innerHTML.replace(/ /g, ' '), /Son \$250\.000/);
});

test('arqueo: el punto de miles no se pierde ni corta la cifra', async () => {
  const calls = [];
  const b = await ready(calls);
  await openArqueo(b);
  for (const v of ['1', '18', '185', '185.', '185.0', '185.00', '185.000']) key(b, 'data-csh-arq-total', v);
  b.click('data-csh-arq-submit');
  await flush(); await flush();
  assert.deepEqual(calls, [{ counted: 185000 }]);                    // no 185
});

test('arqueo: billetes y monedas dígito por dígito', async () => {
  const calls = [];
  const b = await ready(calls);
  await openArqueo(b);
  for (const v of ['1', '12']) { key(b, 'data-csh-den', v, '10000'); await poll(b); }
  for (const v of ['3']) { key(b, 'data-csh-den', v, '50000'); await poll(b); }
  b.click('data-csh-arq-submit');
  await flush(); await flush();
  assert.deepEqual(calls, [{ denominations: { 10000: 12, 50000: 3 } }]);
});

function lastSheet(b, cls) {
  return b.body.children.filter((c) => cls.test(c.className)).pop();
}

test('cobro en efectivo: "Monto recibido" dígito por dígito; nunca se reescribe y el cambio sale bien', async () => {
  const b = await ready([]);
  b.click('data-csh-new-sale');
  b.click('data-csh-product', 'gaseosa');
  lastSheet(b, /wtr-sheet-backdrop/).querySelector('[data-sheet-add]').fire('click');
  b.click('data-csh-sale-pay', 'cash');
  const cash = lastSheet(b, /csh-cash-backdrop/);
  const input = cash.querySelector('#cshCashReceived');
  let typed = '';
  for (const digit of '50000') {
    typed += digit;
    input.value = typed;
    input.fire('input');
    assert.equal(input.value, typed);
    await poll(b);
  }
  assert.equal(cash.querySelector('[data-cash-send]').disabled, false);
  cash.querySelector('[data-cash-send]').fire('click');
  await flush(); await flush();
  assert.match(b.root.innerHTML.replace(/ /g, ' '), /Cambio: \$ ?45\.500/);
});

test('cantidad: el entero dígito por dígito (12) sin saltos', async () => {
  const b = await ready([]);
  b.click('data-csh-new-sale');
  b.click('data-csh-product', 'pollo');
  const sheet = lastSheet(b, /wtr-sheet-backdrop/);
  const input = sheet.querySelector('[data-cxq-whole]');
  for (const v of ['1', '12']) {
    input.value = v;
    input.fire('input');
    assert.equal(input.value, v);
  }
  sheet.querySelector('[data-sheet-add]').fire('click');
  assert.match(b.root.innerHTML, /12 x POLLO/);
});

// ------------------------------------------------ portal: Inventario (Carta)
const client = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');

function fn(name) {
  const start = client.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = client.slice(start + 1);
  return `${tail.slice(0, tail.indexOf('\n  }\n') + 4)}\n`;
}

test('Registrar compra / crear insumo: "Total pagado" dígito por dígito da la cifra escrita y el campo no se toca', () => {
  const ctx = vm.createContext({ String, Number });
  vm.runInContext(`${fn('cxInvMoneyValue049Q')}${fn('inventoryMoneyValue045B')}
    var refreshed = []; function cxInvRefreshPreview049Q(id){ refreshed.push(id); } function cxInvRefreshCreatePreview049Q(){ refreshed.push('create'); }
    ${fn('cxInvOnInput049Q')}`, ctx);
  let typed = '';
  for (const ch of '192.000') {
    typed += ch;
    let writes = 0;
    const field = {
      get value() { return typed; }, set value(_v) { writes += 1; },
      getAttribute: (a) => (a === 'data-inv-buy-total' ? 'i1' : null),
    };
    ctx.cxInvOnInput049Q({ target: { closest: (sel) => (sel.includes('data-inv-buy-total') ? field : null) } });
    assert.equal(writes, 0, 'el manejador nunca reescribe el campo');
  }
  assert.equal(ctx.cxInvMoneyValue049Q(typed), 192000);
  assert.equal(ctx.inventoryMoneyValue045B(typed), 192000);
  assert.equal(ctx.cxInvMoneyValue049Q('192000'), 192000);
  assert.equal(ctx.cxInvMoneyValue049Q('$ 1.120.000'), 1120000);
  assert.equal(ctx.refreshed.length, 7);
});

test('no queda ningún campo de dinero del arqueo como número del navegador (185.000 no se vuelve 185)', () => {
  const cashier = readFileSync('app/web/hsp_cashier.js', 'utf8');
  assert.match(cashier, /<input type="text" inputmode="numeric" autocomplete="off" data-csh-arq-total/);
  assert.doesNotMatch(cashier, /type="number"[^>]*data-csh-(arq-total|den)/);
});
