// Mesero panel on a phone: the session survives a background-unloaded tab
// and a reload, the phone's back button walks the flow instead of leaving,
// leaving with an unsent cart asks first, and a network drop never logs the
// mesero out nor loses the cart. Runs the panel's real functions against a
// fake browser (history entries, localStorage/sessionStorage, fetch).
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/hsp_waiter.js', 'utf8');

function fn(name) {
  const start = source.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

class FakeStorage {
  constructor() { this.data = new Map(); }
  getItem(k) { return this.data.has(k) ? this.data.get(k) : null; }
  setItem(k, v) { this.data.set(k, String(v)); }
  removeItem(k) { this.data.delete(k); }
  clear() { this.data.clear(); }
}

class FakeHistory {
  constructor() { this.entries = [{ state: null }]; this.index = 0; this.exited = false; this.onPop = null; }
  get state() { return this.entries[this.index].state; }
  pushState(state) { this.entries = this.entries.slice(0, this.index + 1); this.entries.push({ state }); this.index += 1; }
  replaceState(state) { this.entries[this.index] = { state }; }
  go(n) {
    const target = this.index + n;
    if (target < 0) { this.exited = true; return; }   // the browser leaves the app
    if (target >= this.entries.length || n === 0) return;
    this.index = target;
    this.onPop({ state: this.state });
  }
  back() { this.go(-1); }
}

const PANEL_FUNCTIONS = [
  'storeGet', 'storeSet', 'storeJson', 'token', 'setToken', 'persistCart', 'restoreCart', 'clearPersistedCart',
  'persistNav', 'restoreNav', 'historyPush', 'installHistory', 'goto', 'back', 'resetToHome', 'closeOpenSheets',
  'confirmLeave', 'popAction', 'onPopState', 'markOffline', 'markOnline', 'sessionLostMessage', 'handleSessionLost',
  'api', 'addOrUpdateCartLine',
];

function browser({ local = new FakeStorage(), session = new FakeStorage(), history = new FakeHistory(), confirmAnswer = true } = {}) {
  const sheets = [];
  const confirms = [];
  const window = {
    localStorage: local,
    sessionStorage: session,
    history,
    confirm: (msg) => { confirms.push(msg); return confirmAnswer; },
    setInterval: () => 1,
    clearInterval: () => {},
  };
  const document = {
    querySelectorAll: () => {
      const list = sheets.slice();
      list.forEach = Array.prototype.forEach;
      return list;
    },
  };
  const ctx = vm.createContext({ window, document, JSON, Math, Array, String, Number, Error, Promise, fetch: null });
  vm.runInContext(
    'var storageKey = "clonexa_waiter_token_c1", cartKey = "clonexa_waiter_cart_c1", navKey = "clonexa_waiter_nav_c1", RECONNECT_MS = 5000;\n'
      + 'var historyReady = false, ignorePops = 0, reconnectHandle = null;\n'
      + 'var state = { screen: "home", stack: ["home"], cart: [], table: "", category: null, menu: [1], username: "laura", offline: false, offlineReason: "", error: "" };\n'
      + PANEL_FUNCTIONS.map(fn).join('\n')
      + '\nvar renders = 0;\n'
      + 'function render() { renders += 1; }\nfunction safeRender() { renders += 1; }\n'
      + 'function renderConnection() {}\nfunction stopSessionKeeper() {}\n'
      + 'function loadMenu() { return Promise.resolve(); }\nfunction refreshHomeWidgets() {}\n'
      + 'function tryReconnect() {}\n',
    ctx,
  );
  history.onPop = (event) => ctx.onPopState(event);
  return { ctx, window, history, local, session, sheets, confirms };
}

function walkToProducts(b) {
  b.ctx.installHistory();
  b.ctx.goto('table');
  b.ctx.state.table = 'Mesa 4';
  b.ctx.goto('categories');
  b.ctx.state.category = 'carnes';
  b.ctx.goto('products');
}

// ---------------------------------------------------------------------------
// Session survives
// ---------------------------------------------------------------------------

test('the token survives the browser unloading the tab (sessionStorage wiped)', () => {
  const b = browser();
  b.ctx.setToken('jwt-1');
  b.session.clear();                        // tab discarded / reopened from the link
  const again = browser({ local: b.local, session: new FakeStorage() });
  assert.equal(again.ctx.token(), 'jwt-1');
});

test('the token survives a reload', () => {
  const b = browser();
  b.ctx.setToken('jwt-1');
  const reloaded = browser({ local: b.local, session: b.session, history: b.history });
  assert.equal(reloaded.ctx.token(), 'jwt-1');
});

test('a token saved by the old version (sessionStorage) is moved to localStorage', () => {
  const b = browser();
  b.session.setItem('clonexa_waiter_token_c1', 'old-jwt');
  assert.equal(b.ctx.token(), 'old-jwt');
  assert.equal(b.local.getItem('clonexa_waiter_token_c1'), 'old-jwt');
  assert.equal(b.session.getItem('clonexa_waiter_token_c1'), null);
});

test('storage that throws (private mode) never crashes the panel', () => {
  const broken = { getItem() { throw new Error('SecurityError'); }, setItem() { throw new Error('QuotaExceeded'); }, removeItem() { throw new Error('x'); } };
  const b = browser({ local: broken, session: broken });
  assert.doesNotThrow(() => b.ctx.setToken('jwt'));
  assert.equal(b.ctx.token(), '');
  assert.doesNotThrow(() => b.ctx.persistCart());
});

test('the cart survives the tab being unloaded, but not into another mesero\'s login', () => {
  const b = browser();
  b.ctx.addOrUpdateCartLine({ inventory_item_id: 'carne', quantity: 1, unit_price: 25000 });
  const same = browser({ local: b.local, session: new FakeStorage() });
  same.ctx.restoreCart('laura');
  assert.equal(same.ctx.state.cart.length, 1);

  const other = browser({ local: b.local, session: new FakeStorage() });
  other.ctx.restoreCart('pedro');
  assert.equal(other.ctx.state.cart.length, 0);
});

// ---------------------------------------------------------------------------
// Back button
// ---------------------------------------------------------------------------

test('back walks producto -> categoria -> mesa -> inicio without leaving the app', () => {
  const b = browser();
  walkToProducts(b);
  assert.equal(b.ctx.state.screen, 'products');

  b.history.back();
  assert.equal(b.ctx.state.screen, 'categories');
  b.history.back();
  assert.equal(b.ctx.state.screen, 'table');
  b.history.back();
  assert.equal(b.ctx.state.screen, 'home');
  assert.equal(b.history.exited, false);
});

test('the in-app back arrow uses the same history', () => {
  const b = browser();
  walkToProducts(b);
  b.ctx.back();
  assert.equal(b.ctx.state.screen, 'categories');
  assert.equal(JSON.stringify(b.ctx.state.stack), JSON.stringify(['home', 'table', 'categories']));
});

test('from the home screen with an empty cart, back leaves without asking', () => {
  const b = browser();
  b.ctx.installHistory();
  b.history.back();
  assert.equal(b.confirms.length, 0);
  assert.equal(b.history.exited, true);
});

test('from the home screen with an unsent cart, back asks and staying keeps everything', () => {
  const b = browser({ confirmAnswer: false });
  b.ctx.installHistory();
  b.ctx.addOrUpdateCartLine({ inventory_item_id: 'carne', quantity: 1, unit_price: 25000 });
  b.history.back();

  assert.equal(b.confirms.length, 1);
  assert.match(b.confirms[0], /pedido sin enviar/);
  assert.equal(b.history.exited, false);
  assert.equal(b.ctx.state.screen, 'home');
  assert.equal(b.ctx.state.cart.length, 1);
  // and the next back asks again instead of silently leaving
  b.history.back();
  assert.equal(b.confirms.length, 2);
  assert.equal(b.history.exited, false);
});

test('confirming the exit with an unsent cart leaves (the cart stays saved)', () => {
  const b = browser({ confirmAnswer: true });
  b.ctx.installHistory();
  b.ctx.addOrUpdateCartLine({ inventory_item_id: 'carne', quantity: 1, unit_price: 25000 });
  b.history.back();
  assert.equal(b.history.exited, true);
  assert.ok(b.local.getItem('clonexa_waiter_cart_c1'));
});

test('if "salir" had no page to go back to, the flow still returns to inicio', () => {
  const b = browser();
  b.ctx.installHistory();
  b.history.back();                          // leave -> browser has nowhere to go
  assert.equal(b.history.index, 0);          // still on the base entry
  b.history.exited = false;

  b.ctx.goto('table');
  b.history.back();
  assert.equal(b.ctx.state.screen, 'home');
  assert.equal(b.history.exited, false);
});

test('back with a product sheet open only closes the sheet', () => {
  const b = browser();
  walkToProducts(b);
  const sheet = { removed: false, remove() { this.removed = true; b.sheets.splice(b.sheets.indexOf(this), 1); } };
  b.sheets.push(sheet);

  b.history.back();

  assert.equal(sheet.removed, true);
  assert.equal(b.ctx.state.screen, 'products');
  b.history.back();                          // now it navigates
  assert.equal(b.ctx.state.screen, 'categories');
});

test('after sending an order the history returns to the home entry', () => {
  const b = browser();
  walkToProducts(b);
  b.ctx.goto('cart');
  b.ctx.resetToHome();
  assert.equal(b.ctx.state.screen, 'home');
  assert.equal(b.history.state.wtrDepth, 0);
  b.history.back();                          // next back is the "leave" step
  assert.equal(b.history.exited, true);
});

test('a reload in the middle of the flow comes back to the same screen', () => {
  const b = browser();
  walkToProducts(b);

  const reloaded = browser({ local: b.local, session: b.session, history: b.history });
  reloaded.ctx.installHistory();

  assert.equal(reloaded.ctx.state.screen, 'products');
  assert.equal(reloaded.ctx.state.category, 'carnes');
  assert.equal(reloaded.ctx.state.table, 'Mesa 4');
  reloaded.history.back();
  assert.equal(reloaded.ctx.state.screen, 'categories');
});

test('popAction is ignored on the login screen', () => {
  const b = browser();
  assert.equal(b.ctx.popAction({ wtrDepth: 0 }, 1, 'login', false).type, 'ignore');
});

// ---------------------------------------------------------------------------
// Network drop
// ---------------------------------------------------------------------------

function response(status, body) {
  return { ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) };
}

test('a network drop marks offline but never logs out nor clears the cart', async () => {
  const b = browser();
  b.ctx.setToken('jwt-1');
  b.ctx.addOrUpdateCartLine({ inventory_item_id: 'carne', quantity: 1, unit_price: 25000 });
  b.ctx.fetch = () => Promise.reject(new TypeError('Failed to fetch'));

  await assert.rejects(b.ctx.api('/api/v1/x'), /Sin conexión/);

  assert.equal(b.ctx.state.offline, true);
  assert.equal(b.ctx.state.screen, 'home');
  assert.equal(b.ctx.token(), 'jwt-1');
  assert.equal(b.ctx.state.cart.length, 1);
  assert.ok(b.local.getItem('clonexa_waiter_cart_c1'));

  b.ctx.fetch = () => Promise.resolve(response(200, { ok: true }));
  await b.ctx.api('/api/v1/x');
  assert.equal(b.ctx.state.offline, false);
});

test('leaving the restaurant WiFi (403) is shown as no connection, not a logout', async () => {
  const b = browser();
  b.ctx.setToken('jwt-1');
  b.ctx.fetch = () => Promise.resolve(response(403, { detail: 'Conectate al WiFi del restaurante.' }));
  await assert.rejects(b.ctx.api('/api/v1/x'));
  assert.equal(b.ctx.state.offline, true);
  assert.equal(b.ctx.state.offlineReason, 'wifi');
  assert.equal(b.ctx.token(), 'jwt-1');
});

test('a real session loss (401) goes to login but keeps the cart', async () => {
  const b = browser();
  b.ctx.setToken('jwt-1');
  b.ctx.addOrUpdateCartLine({ inventory_item_id: 'carne', quantity: 1, unit_price: 25000 });
  b.ctx.fetch = () => Promise.resolve(response(401, { detail: 'Tu sesion se abrio en otro dispositivo.' }));

  await assert.rejects(b.ctx.api('/api/v1/x'));

  assert.equal(b.ctx.state.screen, 'login');
  assert.equal(b.ctx.state.error, 'Tu sesión se abrió en otro dispositivo.');
  assert.equal(b.ctx.token(), '');
  assert.ok(b.local.getItem('clonexa_waiter_cart_c1'));
});

test('a wrong password on the login form is not treated as a lost session', async () => {
  const b = browser();
  b.ctx.state.screen = 'login';
  b.ctx.fetch = () => Promise.resolve(response(401, { detail: 'Usuario o clave inválidos.' }));
  await assert.rejects(b.ctx.api('/login', { isLogin: true }), /inválidos/);
  assert.equal(b.ctx.state.error, '');
});

test('the panel escapes text without String.replaceAll (older Android WebViews)', () => {
  const { kitSource, loadKit } = require('./_menu_kit.cjs');
  assert.doesNotMatch(kitSource, /\.replaceAll\(/);
  assert.doesNotMatch(source, /\.replaceAll\(/);
  assert.equal(loadKit().h('<b>"Mesa" & \'1\'</b>'), '&lt;b&gt;&quot;Mesa&quot; &amp; &#039;1&#039;&lt;/b&gt;');
});
