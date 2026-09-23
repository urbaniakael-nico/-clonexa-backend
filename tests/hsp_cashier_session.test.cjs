// Caja panel gets the same session fix as the mesero panel: the WHOLE
// hsp_cashier.js booted in a minimal fake browser. The session survives a
// discarded tab and a reload, the phone back button returns mesa -> mesas
// instead of leaving, a WiFi drop never logs out, a real 401 does.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/hsp_cashier.js', 'utf8');

class FakeStorage {
  constructor() { this.data = new Map(); }
  getItem(k) { return this.data.has(k) ? this.data.get(k) : null; }
  setItem(k, v) { this.data.set(k, String(v)); }
  removeItem(k) { this.data.delete(k); }
  clear() { this.data.clear(); }
}

function element(tag = 'div') {
  return {
    tagName: tag, id: '', className: '', textContent: '', innerHTML: '', children: [], attrs: {}, style: {},
    setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; },
    appendChild(child) { this.children.push(child); child.parent = this; return child; },
    remove() { if (this.parent) this.parent.children = this.parent.children.filter((c) => c !== this); },
    querySelector() { return { addEventListener() {} }; }, querySelectorAll() { return []; }, addEventListener() {},
  };
}

function fakeHistory(listeners) {
  return {
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
}

function boot({ local = new FakeStorage(), session = new FakeStorage(), history = null, routes }) {
  const listeners = { document: {}, window: {} };
  const root = element('main');
  const body = element('body');
  const hist = history || fakeHistory(listeners);
  if (history) history.listeners = listeners;
  const document = {
    head: element('head'), body, visibilityState: 'visible',
    getElementById: (id) => (id === 'app' ? root : body.children.find((c) => c.id === id) || null),
    createElement: (tag) => element(tag),
    querySelectorAll: () => [],
    addEventListener: (type, cb) => { (listeners.document[type] = listeners.document[type] || []).push(cb); },
  };
  const errors = [];
  const window = {
    location: { search: '?company_id=c1' }, localStorage: local, sessionStorage: session, history: hist,
    setInterval: () => 0, clearInterval: () => {}, setTimeout: () => 0,
    crypto: { getRandomValues: (a) => a.fill(9) },
    addEventListener: (type, cb) => { (listeners.window[type] = listeners.window[type] || []).push(cb); },
  };
  const calls = [];
  const fetch = (url, options = {}) => {
    calls.push({ url, options });
    const r = routes(url, options);
    if (r instanceof Error) return Promise.reject(r);
    return Promise.resolve({ ok: r[0] < 300, status: r[0], json: () => Promise.resolve(r[1]) });
  };
  const ctx = vm.createContext({
    window, document, fetch, console: { error: (...a) => errors.push(a) },
    FormData: class { get(k) { return k === 'username' ? 'caja1' : 'x'; } },
    URLSearchParams, Intl, JSON, Math, Date, Array, Number, String, Promise, Map, Set, Uint8Array, Error,
  });
  vm.runInContext(source, ctx);
  const click = (attr, value = '') => {
    const target = { closest: (sel) => (sel === `[${attr}]` ? { getAttribute: () => value, disabled: false } : null) };
    (listeners.document.click || []).forEach((cb) => cb({ target }));
  };
  return { ctx, root, body, history: hist, calls, click, errors, listeners, local, session };
}

const flush = () => new Promise((r) => setImmediate(r));

function routes(url) {
  if (url.includes('/orders?status=active')) {
    return [200, { orders: [{ id: 'o1', table_key: 'mesa 3', table_number: 'Mesa 3', status: 'entregado', total: 20000, items: [{ name: 'Carne', quantity: 1, unit_price: 20000 }] }] }];
  }
  if (url.includes('/waiter-ordering/menu')) return [200, { categories: [] }];
  if (url.includes('/mini-panel-refresh')) return [200, { access_token: 'renewed' }];
  return [404, {}];
}

function saved() {
  const local = new FakeStorage();
  local.setItem('clonexa_cashier_token_c1', 'jwt-caja');
  return local;
}

test('boots into the open tables from a saved session and renews the token', async () => {
  const b = boot({ local: saved(), routes });
  await flush(); await flush();
  assert.match(b.root.innerHTML, /Mesa 3/);
  assert.equal(b.local.getItem('clonexa_cashier_token_c1'), 'renewed');
  assert.deepEqual(b.errors, []);
});

test('the session survives the tab being unloaded (sessionStorage gone)', async () => {
  const first = boot({ local: saved(), routes });
  await flush();
  const again = boot({ local: first.local, session: new FakeStorage(), routes });
  await flush(); await flush();
  assert.match(again.root.innerHTML, /Mesas abiertas/);
});

test('a token left by the old version in sessionStorage is kept', async () => {
  const session = new FakeStorage();
  session.setItem('clonexa_cashier_token_c1', 'old');
  const b = boot({ session, routes: (u) => (u.includes('refresh') ? [409, {}] : routes(u)) });
  await flush();
  assert.equal(b.local.getItem('clonexa_cashier_token_c1'), 'old');
  assert.match(b.root.innerHTML, /Mesas abiertas/);
});

test('back from a table returns to the tables list instead of leaving', async () => {
  const b = boot({ local: saved(), routes });
  await flush(); await flush();
  b.click('data-csh-open-table', 'mesa 3');
  assert.match(b.root.innerHTML, /CUENTA - NO ES FACTURA/);
  b.history.back();
  assert.match(b.root.innerHTML, /Mesas abiertas/);
  assert.equal(b.history.exited, false);
  b.click('data-csh-open-table', 'mesa 3');
  b.click('data-csh-back');                   // on-screen arrow uses the same history
  assert.match(b.root.innerHTML, /Mesas abiertas/);
});

test('a reload while viewing a table comes back to that table', async () => {
  const b = boot({ local: saved(), routes });
  await flush(); await flush();
  b.click('data-csh-open-table', 'mesa 3');
  const reloaded = boot({ local: b.local, session: b.session, history: b.history, routes });
  await flush(); await flush();
  assert.match(reloaded.root.innerHTML, /CUENTA - NO ES FACTURA/);
});

test('a WiFi drop shows the offline bar and does not log out', async () => {
  let online = true;
  const b = boot({ local: saved(), routes: (u) => (online ? routes(u) : new TypeError('Failed to fetch')) });
  await flush(); await flush();
  online = false;
  (b.listeners.window.offline || []).forEach((cb) => cb());
  assert.ok(b.body.children.find((c) => c.id === 'cshNet'));
  assert.match(b.root.innerHTML, /Mesas abiertas/);
  assert.ok(b.local.getItem('clonexa_cashier_token_c1'));
  online = true;
  (b.listeners.window.online || []).forEach((cb) => cb());
  await flush(); await flush();
  assert.equal(b.body.children.find((c) => c.id === 'cshNet'), undefined);
});

test('a real session loss (401) goes back to login', async () => {
  const b = boot({ local: saved(), routes: (u) => (u.includes('/orders?status=active') ? [401, { detail: 'Tu sesion se abrio en otro dispositivo.' }] : routes(u)) });
  await flush(); await flush();
  assert.match(b.root.innerHTML, /Panel Caja/);
  assert.match(b.root.innerHTML, /otro dispositivo/);
  assert.equal(b.local.getItem('clonexa_cashier_token_c1'), null);
});

test('login sends a stable device id and a wrong password is not a lost session', async () => {
  const b = boot({ routes: (u) => (u.includes('mini-panel-login') ? [401, { detail: 'Usuario o clave inválidos.' }] : routes(u)) });
  (b.listeners.document.submit || []).forEach((cb) => cb({ target: { closest: () => ({}) }, preventDefault() {} }));
  await flush(); await flush();
  const login = b.calls.find((c) => c.url.includes('mini-panel-login'));
  assert.match(JSON.parse(login.options.body).device_id, /^[A-Za-z0-9_-]{8,80}$/);
  assert.match(b.root.innerHTML, /Usuario o clave inválidos/);
});

test('h() no longer uses String.replaceAll', () => {
  const start = source.indexOf('\n  function h(');
  const body = source.slice(start, source.indexOf('\n  }\n', start));
  assert.doesNotMatch(body, /replaceAll/);
});
