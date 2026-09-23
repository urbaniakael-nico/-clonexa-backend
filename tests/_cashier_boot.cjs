// Shared fake browser for booting the WHOLE hsp_cashier.js (not a test file:
// node --test only runs *.test.cjs).
const { readFileSync } = require('node:fs');
const vm = require('node:vm');

const source = readFileSync('app/web/hsp_cashier.js', 'utf8');
const { kitSource } = require('./_menu_kit.cjs');
const saleDocSource = readFileSync('app/web/sale_document.js', 'utf8');

class FakeStorage {
  constructor() { this.data = new Map(); }
  getItem(k) { return this.data.has(k) ? this.data.get(k) : null; }
  setItem(k, v) { this.data.set(k, String(v)); }
  removeItem(k) { this.data.delete(k); }
  clear() { this.data.clear(); }
}

// A node a sheet wires listeners on (e.g. its "Agregar" button): tests can
// fire them with node.fire('click').
function stubNode() {
  return {
    listeners: {}, textContent: '', value: '', disabled: false,
    classList: { toggle() {}, add() {}, remove() {} },
    addEventListener(type, cb) { (this.listeners[type] = this.listeners[type] || []).push(cb); },
    fire(type) { (this.listeners[type] || []).forEach((cb) => cb({ target: this })); },
  };
}

function element(tag = 'div') {
  const node = {
    tagName: tag, id: '', className: '', textContent: '', innerHTML: '', children: [], attrs: {}, style: {}, _q: {},
    setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; },
    appendChild(child) { this.children.push(child); child.parent = this; return child; },
    remove() { if (this.parent) this.parent.children = this.parent.children.filter((c) => c !== this); },
    querySelector(sel) { if (!this._q[sel]) this._q[sel] = stubNode(); return this._q[sel]; },
    querySelectorAll() { return []; }, addEventListener() {},
  };
  if (tag === 'iframe') {
    // Print frame: keep what sale_document.js writes so tests can read it.
    node.written = '';
    node.contentWindow = {
      focus() {}, print() { node.printed = true; },
      document: { readyState: 'complete', open() {}, close() {}, write(html) { node.written += html; } },
    };
  }
  return node;
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
  // hsp_cashier.html loads the shared menu kit and the document renderer first.
  vm.runInContext(kitSource, ctx);
  vm.runInContext(saleDocSource, ctx);
  vm.runInContext(source, ctx);
  const click = (attr, value = '') => {
    const target = { closest: (sel) => (sel === `[${attr}]` ? { getAttribute: () => value, disabled: false } : null) };
    (listeners.document.click || []).forEach((cb) => cb({ target }));
  };
  return { ctx, root, body, history: hist, calls, click, errors, listeners, local, session };
}

const flush = () => new Promise((r) => setImmediate(r));

module.exports = { source, saleDocSource, FakeStorage, boot, flush };
