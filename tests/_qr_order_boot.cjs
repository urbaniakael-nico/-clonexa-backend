// Boots app/web/hospitality_order.js (the public QR table page) inside a vm
// with a tiny fake browser: #app keeps the rendered HTML as a string, clicks
// are dispatched to the document listeners with a target whose closest()
// understands the [data-attr] selectors the page uses, and fetch answers
// from a routes function. Optionally loads hsp_menu_kit.js first.
const { readFileSync } = require('node:fs');
const vm = require('node:vm');

const pageSource = readFileSync('app/web/hospitality_order.js', 'utf8');
const kitSource = readFileSync('app/web/hsp_menu_kit.js', 'utf8');

class Element {}
class HTMLInputElement extends Element {}
class HTMLDetailsElement extends Element {}

class FakeStorage {
  constructor() { this.map = new Map(); }
  getItem(key) { return this.map.has(key) ? this.map.get(key) : null; }
  setItem(key, value) { this.map.set(key, String(value)); }
  removeItem(key) { this.map.delete(key); }
}

function fakeTarget(attrs = {}) {
  const el = new Element();
  el.attrs = { ...attrs };
  el.getAttribute = (name) => (name in el.attrs ? el.attrs[name] : null);
  el.closest = (selector) => {
    const match = /^\[([\w-]+)\]$/.exec(selector);
    return match && match[1] in el.attrs ? el : null;
  };
  return el;
}

function flush() {
  return new Promise((resolve) => setImmediate(resolve));
}

function boot({ search = '?company_id=c1&mesa=Mesa%205', routes, withKit = true, local = new FakeStorage() } = {}) {
  const listeners = {};
  const app = { innerHTML: '' };
  const inputs = new Map();
  const head = { children: [], appendChild(node) { this.children.push(node); return node; } };
  const calls = [];
  const document = {
    head,
    body: { appendChild() {} },
    visibilityState: 'visible',
    activeElement: null,
    getElementById(id) {
      if (id === 'app') return app;
      if (inputs.has(id)) return inputs.get(id);
      return head.children.find((node) => node.id === id) || null;
    },
    createElement(tag) {
      return { tagName: tag, id: '', textContent: '', remove() {} };
    },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
  };
  const window = {
    location: { search, href: `https://x.test/mesa${search}` },
    localStorage: local,
    sessionStorage: new FakeStorage(),
    history: { pushState() {}, back() {} },
    addEventListener() {},
    setTimeout: (fn) => { window.timers.push(fn); return window.timers.length; },
    scrollTo() {},
    timers: [],
  };
  const fetch = async (url, options = {}) => {
    calls.push({ url, options });
    const [status, body] = routes(url, options) || [404, { detail: 'not found' }];
    return {
      ok: status >= 200 && status < 300,
      status,
      statusText: status === 401 ? 'Unauthorized' : '',
      json: async () => body,
      text: async () => JSON.stringify(body),
    };
  };
  const ctx = vm.createContext({
    window,
    document,
    fetch,
    URLSearchParams,
    Intl,
    Element,
    HTMLInputElement,
    HTMLDetailsElement,
    setTimeout: window.setTimeout,
    setInterval: () => 0,
    console,
  });
  ctx.globalThis = ctx;
  window.window = window;
  if (withKit) vm.runInContext(kitSource, ctx); // sets window.CxMenuKit
  vm.runInContext(pageSource, ctx);

  function dispatch(type, target) {
    (listeners[type] || []).forEach((fn) => fn({ target, key: '', preventDefault() {} }));
  }

  function input(id, value) {
    const el = new HTMLInputElement();
    el.id = id;
    el.value = value;
    el.focus = () => {};
    el.setSelectionRange = () => {};
    inputs.set(id, el);
    return el;
  }

  return {
    ctx,
    app,
    calls,
    local,
    window,
    html: () => app.innerHTML,
    click: (attr, value = '') => dispatch('click', fakeTarget({ [attr]: value })),
    type: (id, value) => dispatch('input', input(id, value)),
    input,
    runTimers: () => { const pending = window.timers.splice(0); pending.forEach((fn) => fn()); },
  };
}

module.exports = { boot, flush, FakeStorage };
