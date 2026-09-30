// 049Y: cerrar la jornada de caja nunca deja al cajero atrapado. En
// producción el arqueo respondía "Este turno ya tiene su arqueo registrado" y
// no había forma de cerrar. Ahora: si el turno ya tiene arqueo se muestra y se
// sigue; el Z se saca cuantas veces se quiera; y si algo falla se dice, se
// anota para el dueño y se puede cerrar igual.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { FakeStorage, boot, flush } = require('./_cashier_boot.cjs');

const MENU = { quantity_buttons: [], menu_emojis: false, categories: [] };
const REGISTERED = { id: 'a1', counted: 185000, expected: 185000, difference: 0, base: 0, cash_sales: 185000,
  needs_observation: false, created_at: '2026-09-30T02:40:00Z' };
const Z_PREVIEW = { since_local: '30/09/2026 08:00 a. m.', now_local: '30/09/2026 10:00 p. m.', cashier_name: 'Carla',
  z: { total: 185000, sales: 3, products: 5, orders: 3, methods: [{ method: 'cash', label: 'Efectivo', count: 3, total: 185000 }] },
  history: [] };

function routes(opts = {}) {
  let zNumber = 0;
  const seen = { arqueoPosts: 0, zPosts: 0, finish: 0, incidents: [] };
  const fn = (url, options = {}) => {
    const post = options.method === 'POST';
    if (url.includes('/caja-arqueo/') && url.endsWith('/caja/config')) return [200, { enabled: true, denominations: [50000] }];
    if (url.includes('/caja-arqueo/') && url.endsWith('/caja/cierre/incidencia')) {
      seen.incidents.push(JSON.parse(options.body));
      return [200, { ok: true, recorded: true }];
    }
    if (url.includes('/caja-arqueo/') && url.endsWith('/caja/arqueo') && post) {
      seen.arqueoPosts += 1;
      return opts.arqueoFails ? [500, { detail: 'No se pudo registrar el arqueo.' }] : [200, { ...REGISTERED, already_registered: false }];
    }
    if (url.includes('/caja-arqueo/') && url.endsWith('/caja/arqueo')) return [200, { count: opts.registered ? REGISTERED : null }];
    if (url.includes('/waiter-ordering/caja/z') && post) {
      seen.zPosts += 1;
      if (opts.zFails) return [409, { detail: 'No se pudo registrar el Z.' }];
      zNumber += 1;
      return [201, { id: `z${zNumber}`, number: zNumber, cashier_name: 'Carla', created_local: '30/09/2026', total: 185000, summary: Z_PREVIEW.z }];
    }
    if (url.includes('/waiter-ordering/caja/z')) return opts.zFails ? [409, { detail: 'Z caído' }] : [200, JSON.parse(JSON.stringify(Z_PREVIEW))];
    if (url.includes('/mini-panel-operational-session/finish')) {
      seen.finish += 1;
      if (opts.finishFails) return [409, { detail: 'No se pudo cerrar.' }];
      return [200, { operational_session: null }];
    }
    if (url.includes('/orders?status=active')) return [200, { orders: [] }];
    if (url.includes('/waiter-ordering/menu')) return [200, MENU];
    if (url.includes('/waiter-ordering/caja/config')) return [200, { direct_sale: false, redesign: opts.redesign !== false }];
    if (url.includes('/caja/resumen')) return [200, { sold: 0, charged: 0, pending: 0, orders: 0, accounts: 0, ticket: 0, deliveries: 0, tables: 0, methods: [], direct_sales: [] }];
    if (url.includes('/mini-panel-operational-session')) return [200, { operational_session: { status: 'active', active_seconds: 100, break_seconds: 0 } }];
    return [404, {}];
  };
  return { fn, seen };
}

async function ready(opts) {
  const local = new FakeStorage();
  local.setItem('clonexa_cashier_token_c1', 'jwt');
  const r = routes(opts);
  const b = boot({ local, routes: r.fn });
  for (let i = 0; i < 6; i += 1) await flush();
  return { b, seen: r.seen };
}

async function settle() { for (let i = 0; i < 6; i += 1) await flush(); }

function key(b, attr, value) {
  const target = { value, getAttribute: () => '', closest: (sel) => (sel === `[${attr}]` ? {} : null) };
  (b.listeners.document.input || []).forEach((cb) => cb({ target }));
}

test('turno con arqueo ya registrado: no pide contar otra vez y deja cerrar', async () => {
  const { b, seen } = await ready({ registered: true });
  b.click('data-csh-shift-finish');
  await settle();
  const html = b.root.innerHTML;
  assert.match(html, /Arqueo ya registrado/);
  assert.doesNotMatch(html, /data-csh-arq-total/, 'no vuelve a mostrar el formulario de conteo');
  assert.match(html, /data-csh-arq-finish/);
  b.click('data-csh-arq-finish');
  await settle();
  assert.match(b.root.innerHTML, /Cierre de caja · Z/);
  b.click('data-csh-close-finish');
  await settle();
  assert.equal(seen.arqueoPosts, 0, 'nunca reenvía el conteo');
  assert.equal(seen.finish, 1);
  assert.match(b.root.innerHTML, /Jornada cerrada/);
  assert.equal(b.local.getItem('clonexa_cashier_token_c1'), null, 'se cierra la sesión');
});

test('el Z se saca varias veces y siempre deja cerrar la jornada', async () => {
  const { b, seen } = await ready({});
  b.click('data-csh-shift-finish');
  await settle();
  key(b, 'data-csh-arq-total', '185000');
  b.click('data-csh-arq-submit');
  await settle();
  b.click('data-csh-arq-finish');
  await settle();
  b.click('data-csh-close-z');
  await settle();
  assert.match(b.root.innerHTML, /Z #0001 registrado/);
  b.click('data-csh-close-z');
  await settle();
  b.click('data-csh-close-z');
  await settle();
  assert.equal(seen.zPosts, 3);
  assert.match(b.root.innerHTML, /Z #0003 registrado/);
  assert.match(b.root.innerHTML, /#0001/, 'el historial muestra los Z anteriores');
  b.click('data-csh-close-finish');
  await settle();
  assert.equal(seen.finish, 1);
  assert.match(b.root.innerHTML, /Jornada cerrada/);
});

test('si el arqueo falla, lo dice, lo anota y deja continuar al cierre', async () => {
  const { b, seen } = await ready({ arqueoFails: true });
  b.click('data-csh-shift-finish');
  await settle();
  key(b, 'data-csh-arq-total', '90000');
  b.click('data-csh-arq-submit');
  await settle();
  assert.match(b.root.innerHTML, /No se pudo registrar el arqueo/);
  assert.match(b.root.innerHTML, /data-csh-arq-skip/);
  b.click('data-csh-arq-skip');
  await settle();
  assert.equal(seen.incidents[0].step, 'arqueo');
  assert.equal(seen.incidents[0].counted, 90000, 'queda lo que alcanzó a contar');
  b.click('data-csh-close-finish');
  await settle();
  assert.equal(seen.finish, 1);
  assert.match(b.root.innerHTML, /Jornada cerrada/);
});

test('si el Z falla, se puede cerrar igual', async () => {
  const { b, seen } = await ready({ registered: true, zFails: true });
  b.click('data-csh-shift-finish');
  await settle();
  b.click('data-csh-arq-finish');
  await settle();
  assert.match(b.root.innerHTML, /Puedes cerrar la jornada igual/);
  b.click('data-csh-close-finish');
  await settle();
  assert.equal(seen.finish, 1);
  assert.ok(seen.incidents.some((i) => i.step === 'z'));
});

test('si el servidor no cierra el turno, se puede reintentar o salir igual', async () => {
  const { b, seen } = await ready({ registered: true, finishFails: true });
  b.click('data-csh-shift-finish');
  await settle();
  b.click('data-csh-arq-finish');
  await settle();
  b.click('data-csh-close-finish');
  await settle();
  assert.match(b.root.innerHTML, /data-csh-close-leave/);
  assert.ok(seen.incidents.some((i) => i.step === 'cierre'));
  b.click('data-csh-close-leave');
  await settle();
  assert.equal(b.local.getItem('clonexa_cashier_token_c1'), null);
  assert.match(b.root.innerHTML, /avísale al administrador/);
});

test('sin el rediseño (sin Z) el cierre va directo tras el arqueo', async () => {
  const { b, seen } = await ready({ registered: true, redesign: false });
  b.click('data-csh-shift-finish');
  await settle();
  b.click('data-csh-arq-finish');
  await settle();
  assert.equal(seen.finish, 1);
  assert.equal(seen.zPosts, 0);
});
