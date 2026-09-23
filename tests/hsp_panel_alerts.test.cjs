// Alerts (sound + vibration + card until closed) in the three waiter_ordering
// panels, the caja's "Listo para cobrar" state and the cash calculator.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { FakeStorage, boot, flush, source: cashierSource } = require('./_cashier_boot.cjs');

const alertsSource = readFileSync('app/web/hsp_alerts.js', 'utf8');
const kitchenSource = readFileSync('app/web/hsp_kitchen.js', 'utf8');

// ---------------------------------------------------------------------------
// A small fake browser for the alerts module itself
// ---------------------------------------------------------------------------

function node(tag = 'div') {
  const n = {
    tagName: tag, id: '', className: '', innerHTML: '', textContent: '', children: [], attrs: {}, _q: {},
    setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; },
    appendChild(c) { this.children.push(c); c.parent = this; return c; },
    remove() { if (this.parent) this.parent.children = this.parent.children.filter((c) => c !== this); },
    querySelector(sel) {
      if (!this._q[sel]) this._q[sel] = { listeners: {}, addEventListener(t, cb) { (this.listeners[t] = this.listeners[t] || []).push(cb); }, fire(t) { (this.listeners[t] || []).forEach((cb) => cb({})); } };
      return this._q[sel];
    },
  };
  return n;
}

function alertsEnv() {
  const body = node('body');
  const head = node('head');
  const docListeners = {};
  const played = [];
  const vibrations = [];
  const storage = new FakeStorage();
  class FakeAudioContext {
    constructor() { this.state = 'suspended'; this.currentTime = 0; this.destination = {}; }
    resume() { this.state = 'running'; return Promise.resolve(); }
    createOscillator() {
      const osc = { frequency: {}, connect() {}, start() { played.push(osc.frequency.value); }, stop() {} };
      return osc;
    }
    createGain() { return { gain: { setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() {} }; }
  }
  const document = {
    body, head,
    getElementById: (id) => [...body.children, ...head.children].find((c) => c.id === id) || null,
    createElement: (tag) => node(tag),
    addEventListener: (type, cb) => { (docListeners[type] = docListeners[type] || []).push(cb); },
    removeEventListener: (type, cb) => { docListeners[type] = (docListeners[type] || []).filter((f) => f !== cb); },
  };
  const window = { AudioContext: FakeAudioContext, localStorage: storage };
  const navigator = { vibrate: (pattern) => { vibrations.push(pattern); return true; } };
  const ctx = vm.createContext({ window, document, navigator, String, Number, Array, Set, Promise, JSON, Math });
  vm.runInContext(alertsSource, ctx);
  const tap = () => (docListeners.pointerdown || []).slice().forEach((cb) => cb({}));
  const click = (target) => (docListeners.click || []).forEach((cb) => cb({ target }));
  return { CxAlerts: window.CxAlerts, body, played, vibrations, storage, tap, click, document };
}

test('each kind of alert has its own sound', () => {
  const { CxAlerts } = alertsEnv();
  const melodies = Object.values(CxAlerts.SOUNDS).map((notes) => JSON.stringify(notes));
  assert.equal(new Set(melodies).size, 4);
  assert.deepEqual(Object.keys(CxAlerts.SOUNDS).sort(), ['new_order', 'new_sale', 'ready', 'to_charge']);
});

test('audio is unlocked on the first tap; before that a banner asks for it', () => {
  const env = alertsEnv();
  const alerts = env.CxAlerts.create('cocina');
  alerts.install();
  const controls = env.body.children.find((c) => c.id === 'cxAlertControls');
  assert.match(controls.innerHTML, /Toca la pantalla para activar el sonido/);
  alerts.notify({ kind: 'new_order', title: 'Pedido nuevo · Mesa 4' });
  assert.equal(env.played.length, 0);                                // still locked
  env.tap();
  assert.equal(alerts.isUnlocked(), true);
  assert.doesNotMatch(controls.innerHTML, /Toca la pantalla/);
  alerts.notify({ kind: 'new_order', title: 'Pedido nuevo · Mesa 5' });
  assert.equal(JSON.stringify(env.played), JSON.stringify(env.CxAlerts.SOUNDS.new_order.map(([f]) => f)));
});

test('an alert vibrates and stays on screen until closed', () => {
  const env = alertsEnv();
  const alerts = env.CxAlerts.create('mesero');
  alerts.install();
  let closed = 0;
  alerts.notify({ kind: 'ready', title: 'Mesa 7 lista para llevar', message: 'Recógela', onClose: () => { closed += 1; } });
  assert.deepEqual(env.vibrations, [env.CxAlerts.VIBRATION.ready]);
  const stack = env.body.children.find((c) => c.id === 'cxAlertStack');
  assert.equal(stack.children.length, 1);
  assert.match(stack.children[0].innerHTML, /Mesa 7 lista para llevar/);
  assert.match(stack.children[0].className, /cx-alert-ready/);
  stack.children[0].querySelector('[data-cx-alert-close]').fire('click');
  assert.equal(stack.children.length, 0);
  assert.equal(closed, 1);
});

test('each panel has its own mute button, remembered per panel', () => {
  const env = alertsEnv();
  const caja = env.CxAlerts.create('caja');
  caja.install();
  env.tap();
  env.click({ closest: (sel) => (sel === '[data-cx-alert-mute]' ? {} : null) });
  assert.equal(caja.isMuted(), true);
  assert.equal(env.storage.getItem('clonexa_alerts_muted_caja'), '1');
  assert.equal(env.CxAlerts.create('cocina').isMuted(), false);       // other panels unaffected
  caja.notify({ kind: 'new_sale', title: 'Venta nueva' });
  assert.equal(env.played.length, 0);
  assert.equal(env.vibrations.length, 0);
  const stack = env.body.children.find((c) => c.id === 'cxAlertStack');
  assert.equal(stack.children.length, 1);                              // muted still shows the card
});

test('nothing is announced on the first load', () => {
  const { CxAlerts } = alertsEnv();
  assert.deepEqual(Array.from(CxAlerts.newIds(null, ['a', 'b'])), []);
  assert.deepEqual(Array.from(CxAlerts.newIds(new Set(['a']), ['a', 'b'])), ['b']);
});

// ---------------------------------------------------------------------------
// Cocina: pedido nuevo
// ---------------------------------------------------------------------------

function kitchenFn(name) {
  const start = kitchenSource.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = kitchenSource.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

test('cocina announces each new comanda once, never what was already there', () => {
  const env = alertsEnv();
  const ctx = vm.createContext({ window: { CxAlerts: env.CxAlerts }, Set, Array, String });
  vm.runInContext('var seenComandas = null;\n' + kitchenFn('comandaSummary') + kitchenFn('newComandaAlerts'), ctx);
  const a = { order_id: 'a', table_number: 'Mesa 1', items: [{ quantity: 1, name: 'CARNE' }] };
  const b = { order_id: 'b', table_number: 'Mesa 4', items: [{ quantity_label: '1/2', quantity: 0.5, name: 'POLLO' }, { quantity: 2, name: 'GASEOSA' }] };
  assert.equal(ctx.newComandaAlerts([a]).length, 0);                 // first load
  const alerts = ctx.newComandaAlerts([a, b]);
  assert.equal(alerts.length, 1);
  assert.equal(alerts[0].kind, 'new_order');
  assert.equal(alerts[0].title, 'Pedido nuevo · Mesa 4');
  assert.equal(alerts[0].message, '1/2 POLLO · 2× GASEOSA');
  assert.equal(ctx.newComandaAlerts([a, b]).length, 0);              // announced once
  assert.match(kitchenSource, /if \(Alerts\) alerts\.forEach\(\(alert\) => Alerts\.notify\(alert\)\);/);
});

// ---------------------------------------------------------------------------
// Caja: venta nueva / lista para cobrar + estados + calculadora
// ---------------------------------------------------------------------------

function cajaRoutes(state) {
  return (url, options) => {
    if (url.includes('/orders?status=active')) return [200, { orders: state.orders }];
    if (url.includes('/waiter-ordering/menu')) return [200, { categories: [] }];
    if (url.includes('/caja/config')) return [200, { direct_sale: true }];
    if (url.includes('/qr-tables')) return [200, { tables: [] }];
    if (url.includes('/close-table')) { state.closed.push({ url, body: JSON.parse(options.body) }); return [200, { ok: true }]; }
    if (url.includes('/mini-panel-refresh')) return [200, { access_token: 'x' }];
    return [404, {}];
  };
}

function saved() {
  const local = new FakeStorage();
  local.setItem('clonexa_cashier_token_c1', 'jwt');
  return local;
}

const poll = async (b) => { (b.listeners.window.online || []).forEach((cb) => cb()); await flush(); await flush(); };
const alertCards = (b) => {
  const stack = b.body.children.find((c) => c.id === 'cxAlertStack');
  return stack ? stack.children.map((c) => c.innerHTML) : [];
};

test('caja: a new sale and a table turning ready to charge are announced, its own sales are not', async () => {
  const now = new Date().toISOString();
  const state = { closed: [], orders: [
    { id: 'o1', table_key: 'mesa 7', table_number: 'Mesa 7', status: 'alistando', total: 39000, created_at: now, metadata: { waiter: { name: 'Laura' } }, items: [] },
  ] };
  const b = boot({ local: saved(), routes: cajaRoutes(state) });
  await flush(); await flush(); await flush();
  assert.deepEqual(alertCards(b), []);                                 // first load: nothing

  state.orders = [
    { ...state.orders[0], status: 'entregado' },
    { id: 'o2', table_key: 'mesa 2', table_number: 'Mesa 2', status: 'pendiente', total: 12000, created_at: now, metadata: { waiter: { name: 'Pedro' } }, items: [] },
    { id: 'v1', table_key: 'venta 005', table_number: 'Venta 005', status: 'pendiente', total: 4500, created_at: now, metadata: { cashier_sale: { kind: 'independiente' } }, items: [] },
  ];
  await poll(b);
  const cards = alertCards(b);
  assert.equal(cards.length, 2);
  assert.ok(cards.some((c) => /Mesa 7 lista para cobrar/.test(c)));
  assert.ok(cards.some((c) => /Venta nueva · Mesa 2/.test(c) && /Pedro/.test(c)));
  assert.ok(!cards.some((c) => /Venta 005/.test(c)));

  await poll(b);
  assert.equal(alertCards(b).length, 2);                               // no repeats
});

test('caja keeps "Listo para cobrar" after the kitchen delivers, until it is charged', async () => {
  const now = new Date().toISOString();
  const state = { closed: [], orders: [
    { id: 'o1', table_key: 'mesa 7', table_number: 'Mesa 7', status: 'entregado', total: 39000, created_at: now,
      metadata: { waiter: { name: 'Laura' }, kitchen: { ready_at: now, delivered_at: now } }, items: [] },
  ] };
  const b = boot({ local: saved(), routes: cajaRoutes(state) });
  await flush(); await flush(); await flush();
  assert.match(b.root.innerHTML, /Listo para cobrar/);
  assert.doesNotMatch(b.root.innerHTML, /Entregado/i);
  state.orders = [];                                                   // charged -> leaves the board
  await poll(b);
  assert.doesNotMatch(b.root.innerHTML, /Mesa 7|<b>7<\/b>/);
});

function cashierFn(name) {
  const start = cashierSource.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = cashierSource.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

test('the change is computed exactly, and a short amount says how much is missing', () => {
  const ctx = vm.createContext({ Math, Number, String });
  vm.runInContext(cashierFn('parseCash') + cashierFn('cashChange'), ctx);
  assert.equal(ctx.parseCash('50.000'), 50000);
  assert.equal(ctx.parseCash('$ 1.250.000'), 1250000);
  assert.equal(ctx.parseCash(''), 0);
  assert.deepEqual({ ...ctx.cashChange(39000, 50000) }, { ok: true, change: 11000, missing: 0 });
  assert.deepEqual({ ...ctx.cashChange(39000, 39000) }, { ok: true, change: 0, missing: 0 });
  assert.deepEqual({ ...ctx.cashChange(39000, 20000) }, { ok: false, change: 0, missing: 19000 });
  assert.match(cashierSource, /const CASH_BILLS = \[10000, 20000, 50000, 100000\];/);
});

async function openTable() {
  const now = new Date().toISOString();
  const state = { closed: [], orders: [
    { id: 'o1', table_key: 'mesa 7', table_number: 'Mesa 7', status: 'entregado', total: 39000, created_at: now, metadata: { waiter: { name: 'Laura' } }, items: [{ name: 'POLLO', quantity: 1, subtotal: 39000 }] },
  ] };
  const b = boot({ local: saved(), routes: cajaRoutes(state) });
  await flush(); await flush(); await flush();
  b.click('data-csh-open-table', 'mesa 7');
  return { b, state };
}

test('Efectivo opens the calculator: bills, live change, Enviar locked while short', async () => {
  const { b, state } = await openTable();
  b.click('data-csh-pay', 'cash');
  const sheet = b.body.children.find((c) => /csh-cash-backdrop/.test(c.className));
  assert.ok(sheet);
  assert.match(sheet.innerHTML, /data-cash-bill="10000"[\s\S]*data-cash-bill="20000"[\s\S]*data-cash-bill="50000"[\s\S]*data-cash-bill="100000"/);
  assert.match(sheet.innerHTML, /Monto exacto/);
  const send = sheet.querySelector('[data-cash-send]');
  const status = sheet.querySelector('#cshCashChange');
  assert.equal(send.disabled, true);
  assert.match(send.textContent, /Faltan \$\s?39\.000/);

  sheet.querySelector('[data-cash-bill="20000"]').fire('click');
  assert.equal(send.disabled, true);
  assert.match(status.innerHTML, /Faltan<\/span><strong class="csh-cash-missing">\$\s?19\.000/);
  send.fire('click');
  assert.equal(state.closed.length, 0);                                // blocked

  const input = sheet.querySelector('#cshCashReceived');
  input.value = '100.000';
  input.fire('input');                                                 // typed: live change
  assert.equal(send.disabled, false);
  assert.match(status.innerHTML, /Cambio<\/span><strong>\$\s?61\.000/);

  sheet.querySelector('[data-cash-exact]').fire('click');
  assert.match(status.innerHTML, /Cambio<\/span><strong>\$\s?0</);
  sheet.querySelector('[data-cash-bill="50000"]').fire('click');        // 39.000 + 50.000
  assert.match(status.innerHTML, /\$\s?50\.000/);

  send.fire('click');
  await flush(); await flush();
  assert.equal(state.closed.length, 1);
  assert.deepEqual(state.closed[0].body, { payment_method: 'cash' });
  assert.match(b.root.innerHTML, /Mesa 7 cobrada\. Cambio: \$\s?50\.000\./);
});

test('Transferencia and Tarjeta charge directly, without the calculator', async () => {
  for (const method of ['transfer', 'card']) {
    const { b, state } = await openTable();
    b.click('data-csh-pay', method);
    await flush(); await flush();
    assert.equal(b.body.children.some((c) => /csh-cash-backdrop/.test(c.className)), false);
    assert.deepEqual(state.closed.map((c) => c.body), [{ payment_method: method }]);
  }
});

test('the three panels load the alerts module (only waiter_ordering pages)', () => {
  for (const page of ['hsp_kitchen.html', 'hsp_cashier.html', 'hsp_waiter.html']) {
    assert.match(readFileSync(`app/web/${page}`, 'utf8'), /hsp_alerts\.js/, page);
  }
  assert.doesNotMatch(readFileSync('app/web/client.html', 'utf8'), /hsp_alerts\.js/);
});
