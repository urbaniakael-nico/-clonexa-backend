// 049Z: el tema que el servidor incrusta (window.__CX_BRAND__) se aplica desde
// el primer pintado, también en páginas sin company_id (QR de la carta), y
// los colores del QR de mesa y del panel genérico pasan a la marca.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/hsp_brand.js', 'utf8');
const BRAND = { primary_color: '#b91c1c', secondary_color: '#f59e0b', background_color: '#fff7ed', text_color: '#1c1917' };

function load({ search = '', embedded = null } = {}) {
  const head = { children: [], appendChild(el) { this.children.push(el); }, querySelectorAll: () => [] };
  const store = new Map();
  const attrs = {};
  const timers = [];
  const ctx = vm.createContext({
    window: {
      location: { search }, __CX_BRAND__: embedded, setTimeout: (fn) => timers.push(fn),
      localStorage: { getItem: (k) => store.get(k) || null, setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k) },
    },
    document: {
      readyState: 'complete', head,
      getElementById: (id) => head.children.find((c) => c.id === id) || null,
      createElement: (tag) => ({ tagName: tag, id: '', textContent: '', rel: '', href: '', remove() {} }),
      documentElement: { setAttribute: (k, v) => { attrs[k] = v; }, removeAttribute: (k) => { delete attrs[k]; } },
    },
    URLSearchParams, JSON, Math, Number, String, Array, WeakMap, Promise, parseInt,
  });
  vm.runInContext(source, ctx);
  timers.forEach((fn) => fn());
  return { brand: ctx.window.CxPanelBrand, head, attrs, store };
}

test('el tema incrustado se aplica aunque la página no traiga company_id (QR de la carta)', () => {
  const t = load({ search: '?t=token-de-la-carta', embedded: BRAND });
  assert.equal(t.attrs['data-cx-brand'], 'light');
  const vars = t.head.children.find((c) => c.id === 'cxPanelBrand049V');
  assert.match(vars.textContent, /--cxb-primary:#b91c1c/);
});

test('en el link de domicilios (?c=) se aplica y se recuerda para la próxima vez', () => {
  const t = load({ search: '?c=co-1&s=K7PM2QX9HD', embedded: BRAND });
  assert.equal(t.attrs['data-cx-brand'], 'light');
  assert.ok(t.store.get('clonexa_panel_brand_co-1'));
});

test('sin tema incrustado ni guardado, nada cambia', () => {
  const t = load({ search: '?company_id=co-1' });
  assert.equal(t.attrs['data-cx-brand'], undefined);
});

test('fondos del QR de mesa y variables del panel genérico pasan a la marca', () => {
  const { brand } = load();
  const p = brand.palette(BRAND);
  const css = brand.themeCss(':root{--bg:#080813;--text:#ffffff;--pink:#ff22b8}.qr-card{background:rgba(2,6,23,.58)}body{background:linear-gradient(135deg,#050510,#19102f 50%)}', p);
  assert.match(css, /--bg:var\(--cxb-bg\)/);
  assert.match(css, /--text:var\(--cxb-ink\)/);
  assert.match(css, /--pink:var\(--cxb-primary\)/);
  assert.match(css, /\.qr-card\{background:var\(--cxb-surface\)\}/);
  assert.doesNotMatch(css, /#050510|#19102f/);
});
