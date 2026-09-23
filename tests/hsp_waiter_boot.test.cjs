// Smoke test of the WHOLE hsp_waiter.js in a minimal fake browser: boots
// with a saved session, walks the flow with real click handlers, uses the
// phone back button (popstate), survives a WiFi drop, and never throws a
// ReferenceError from a wiring mistake the per-function tests can't see.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/hsp_waiter.js', 'utf8');
const { kitSource } = require('./_menu_kit.cjs');

class FakeStorage {
  constructor() { this.data = new Map(); }
  getItem(k) { return this.data.has(k) ? this.data.get(k) : null; }
  setItem(k, v) { this.data.set(k, String(v)); }
  removeItem(k) { this.data.delete(k); }
}

function element(tag = 'div') {
  return {
    tagName: tag, id: '', className: '', textContent: '', innerHTML: '', children: [], attrs: {},
    style: {}, classList: { toggle() {}, add() {}, remove() {} },
    setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; },
    appendChild(child) { this.children.push(child); child.parent = this; return child; },
    remove() { if (this.parent) this.parent.children = this.parent.children.filter((c) => c !== this); },
    // Sheets wire their own buttons: hand back an inert element.
    querySelector() { return { addEventListener() {}, textContent: '', value: '', classList: { toggle() {} } }; },
    querySelectorAll() { return []; }, addEventListener() {},
  };
}

function boot({ local = new FakeStorage(), session = new FakeStorage(), routes }) {
  const listeners = { document: {}, window: {} };
  const root = element('main');
  const body = element('body');
  const head = element('head');
  const history = {
    entries: [{ state: null }], index: 0, exited: false,
    get state() { return this.entries[this.index].state; },
    pushState(s) { this.entries = this.entries.slice(0, this.index + 1); this.entries.push({ state: s }); this.index += 1; },
    replaceState(s) { this.entries[this.index] = { state: s }; },
    go(n) {
      const t = this.index + n;
      if (t < 0) { this.exited = true; return; }
      if (t >= this.entries.length || n === 0) return;
      this.index = t;
      (listeners.window.popstate || []).forEach((cb) => cb({ state: this.state }));
    },
    back() { this.go(-1); },
  };
  const document = {
    head, body, visibilityState: 'visible',
    getElementById: (id) => (id === 'app' ? root : body.children.find((c) => c.id === id) || null),
    createElement: (tag) => element(tag),
    querySelectorAll: () => [],
    addEventListener: (type, cb) => { (listeners.document[type] = listeners.document[type] || []).push(cb); },
  };
  const errors = [];
  const window = {
    location: { search: '?company_id=c1' },
    localStorage: local, sessionStorage: session, history,
    confirm: () => true,
    setInterval: () => 0, clearInterval: () => {}, setTimeout: () => 0,
    crypto: { getRandomValues: (a) => a.fill(7) },
    addEventListener: (type, cb) => { (listeners.window[type] = listeners.window[type] || []).push(cb); },
  };
  const calls = [];
  const fetch = (url, options = {}) => {
    calls.push({ url, options });
    const handler = routes(url, options);
    if (handler instanceof Error) return Promise.reject(handler);
    const [status, body] = handler;
    return Promise.resolve({ ok: status < 300, status, json: () => Promise.resolve(body) });
  };
  const ctx = vm.createContext({
    window, document, fetch, navigator: {}, console: { error: (...a) => errors.push(a) },
    FormData: class { get(k) { return k === 'username' ? 'laura' : 'x'; } },
    URLSearchParams, Intl, JSON, Math, Date, Array, Number, String, Promise, Set, Map, Uint8Array, Error,
  });
  vm.runInContext(kitSource, ctx);   // hsp_waiter.html loads the kit first
  vm.runInContext(source, ctx);
  const click = (attr, value = '') => {
    const target = {
      closest: (sel) => (sel === `[${attr}]` ? { getAttribute: () => value, disabled: false } : null),
    };
    (listeners.document.click || []).forEach((cb) => cb({ target, stopPropagation() {} }));
  };
  return { ctx, root, body, history, calls, click, errors, listeners, local, session };
}

const flush = () => new Promise((r) => setImmediate(r));

function happyRoutes(url) {
  if (url.includes('/qr-tables')) return [200, { tables: [{ label: 'Mesa 1' }] }];
  if (url.includes('/waiter-ordering/menu')) return [200, { categories: [{ key: 'carnes', label: 'Carnes', products: [] }], quantity_buttons: [] }];
  if (url.includes('/mini-panel-operational-session')) return [200, { operational_session: { active_seconds: 60 } }];
  if (url.includes('/ventas-hoy')) return [200, { total_today: 0, daily_goal: 0 }];
  if (url.includes('/mis-mesas')) return [200, { tables: [] }];
  if (url.includes('/avisos')) return [200, { enabled: true, avisos: [] }];
  if (url.includes('/mini-panel-refresh')) return [200, { access_token: 'renewed-jwt' }];
  return [404, { detail: 'no' }];
}

function withSavedSession() {
  const local = new FakeStorage();
  local.setItem('clonexa_waiter_token_c1', 'jwt-1');
  local.setItem('clonexa_waiter_profile_c1', JSON.stringify({ companyName: 'Asadero', mesero: 'Laura', username: 'laura' }));
  return local;
}

test('boots straight into the home screen from a saved session and renews the token', async () => {
  const b = boot({ local: withSavedSession(), routes: happyRoutes });
  await flush(); await flush();
  assert.match(b.root.innerHTML, /Tomar pedido/);
  assert.match(b.root.innerHTML, /Laura/);
  assert.ok(b.calls.some((c) => c.url.includes('/mini-panel-refresh?panel_type=mesero') && c.options.method === 'POST'));
  assert.equal(b.local.getItem('clonexa_waiter_token_c1'), 'renewed-jwt');
  assert.deepEqual(b.errors, []);
});

test('clicks walk the flow and the phone back button walks it back', async () => {
  const b = boot({ local: withSavedSession(), routes: happyRoutes });
  await flush(); await flush();
  b.click('data-wtr-new-order');
  assert.match(b.root.innerHTML, /Elige la mesa/);
  b.click('data-wtr-table', 'Mesa 1');
  assert.match(b.root.innerHTML, /Carnes/);
  b.click('data-wtr-cat', 'carnes');
  assert.match(b.root.innerHTML, /Sin productos en esta categoría/);

  b.history.back();
  assert.match(b.root.innerHTML, /Carnes/);
  b.history.back();
  assert.match(b.root.innerHTML, /Elige la mesa/);
  b.history.back();
  assert.match(b.root.innerHTML, /Tomar pedido/);
  assert.equal(b.history.exited, false);
  assert.deepEqual(b.errors, []);
});

test('a WiFi drop shows the offline bar and keeps the mesero in the panel', async () => {
  let online = true;
  const b = boot({ local: withSavedSession(), routes: (url, o) => (online ? happyRoutes(url, o) : new TypeError('Failed to fetch')) });
  await flush(); await flush();
  online = false;
  (b.listeners.window.offline || []).forEach((cb) => cb());
  const bar = b.body.children.find((c) => c.id === 'wtrNet');
  assert.ok(bar);
  assert.match(bar.textContent, /Sin conexión/);
  assert.match(b.root.innerHTML, /Tomar pedido/);
  assert.equal(b.local.getItem('clonexa_waiter_token_c1'), 'renewed-jwt');   // still logged in

  online = true;
  (b.listeners.window.online || []).forEach((cb) => cb());
  await flush(); await flush();
  assert.equal(b.body.children.find((c) => c.id === 'wtrNet'), undefined);
});

test('the login form sends a stable device id', async () => {
  const b = boot({ routes: (url) => (url.includes('mini-panel-login') ? [401, { detail: 'Usuario o clave inválidos.' }] : happyRoutes(url)) });
  (b.listeners.document.submit || []).forEach((cb) => cb({
    target: { closest: () => ({}) }, preventDefault() {},
  }));
  await flush();
  const login = b.calls.find((c) => c.url.includes('mini-panel-login'));
  assert.ok(login, 'login request');
  const body = JSON.parse(login.options.body);
  assert.match(body.device_id, /^[A-Za-z0-9_-]{8,80}$/);
  assert.equal(b.local.getItem('clonexa_mini_panel_device_id'), body.device_id);
});

test('a token renewal answering after a 401 does not revive the closed session', async () => {
  const b = boot({
    local: withSavedSession(),
    routes: (url, o) => (url.includes('/waiter-ordering/menu') ? [401, { detail: 'Tu sesion se abrio en otro dispositivo.' }] : happyRoutes(url, o)),
  });
  await flush(); await flush(); await flush();
  assert.match(b.root.innerHTML, /otro dispositivo/);
  assert.equal(b.local.getItem('clonexa_waiter_token_c1'), null);
});

test('choosing "Mesa 11" titles the screen "Mesa 11" and each category shows its emoji', async () => {
  const b = boot({
    local: withSavedSession(),
    routes: (url, o) => {
      if (url.includes('/waiter-ordering/menu')) {
        return [200, {
          menu_emojis: true,
          quantity_buttons: [],
          categories: [
            { key: 'pollo', label: 'Pollo', has_image: false, products: [{ id: 'p1', name: 'POLLO Asado', price: 1 }] },
            { key: 'gaseosa', label: 'Gaseosa', has_image: false, products: [] },
            { key: 'combo', label: 'Combo', has_image: false, products: [] },
            { key: 'carne', label: 'Carne', has_image: true, products: [] },
          ],
        }];
      }
      return happyRoutes(url, o);
    },
  });
  await flush(); await flush();
  b.click('data-wtr-new-order');
  b.click('data-wtr-table', 'Mesa 11');
  const html = b.root.innerHTML;
  assert.match(html, /<h1>Mesa 11<\/h1>/);
  assert.doesNotMatch(html, /Mesa Mesa/);
  assert.match(html, /wtr-emoji">🍗</);
  assert.match(html, /wtr-emoji">🥤</);
  assert.match(html, /wtr-emoji">🍽️</);                        // no match -> default
  assert.match(html, /categories\/carne\/image/);               // photo replaces the emoji
  assert.doesNotMatch(html, /wtr-emoji">🥩</);
  b.click('data-wtr-cat', 'pollo');
  assert.match(b.root.innerHTML, /wtr-prod-emoji">🍗</);
});

function menuWithPortions() {
  return (url, o) => {
    if (url.includes('/waiter-ordering/menu')) {
      return [200, {
        quantity_buttons: ['1/4', '1/2', '3/4', '1', '2'],
        categories: [{ key: 'menu', label: 'Menu', has_image: false, products: [
          { id: 'pollo', name: 'POLLO Asado', price: 40000, allows_portions: true, quantity_ref_id: 'pollo',
            quantity_options: [{ label: '1/4', available: true, price: 10000 }, { label: '1', available: true, price: 40000 }] },
          { id: 'gaseosa', name: 'GASEOSA Coca Cola', price: 4500, allows_portions: false },
        ] }],
      }];
    }
    return happyRoutes(url, o);
  };
}

async function openProduct(productId) {
  const b = boot({ local: withSavedSession(), routes: menuWithPortions() });
  await flush(); await flush();
  b.click('data-wtr-new-order');
  b.click('data-wtr-table', 'Mesa 2');
  b.click('data-wtr-cat', 'menu');
  b.click('data-wtr-product', productId);
  const sheet = b.body.children.filter((c) => /wtr-sheet/.test(c.innerHTML)).pop();
  return sheet ? sheet.innerHTML : '';
}

test('a product that allows portions shows the fraction buttons', async () => {
  const html = await openProduct('pollo');
  assert.match(html, /data-qty-index="0"/);
  assert.match(html, /<span>1\/4<\/span>/);
  assert.doesNotMatch(html, /wtr-stepper/);
});

test('a product without portions shows only a whole-unit selector with its price', async () => {
  const html = await openProduct('gaseosa');
  assert.match(html, /wtr-stepper/);
  assert.match(html, /data-qty-step="1"/);
  assert.match(html, /id="wtrStepQty">1</);
  assert.match(html, /Vas a cobrar <strong id="wtrQtyPrice">\$\s?4\.500/);
  assert.doesNotMatch(html, /data-qty-index/);
  assert.doesNotMatch(html, /1\/4/);
});
