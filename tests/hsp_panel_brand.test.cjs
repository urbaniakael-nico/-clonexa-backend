// 049V: el tema de la empresa (Admin V2) en los mini paneles de caja, mesero
// y cocina (hsp_brand.js), solo con el interruptor mini_panel_brand.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');

const source = readFileSync('app/web/hsp_brand.js', 'utf8');
const waiterCss = readFileSync('app/web/hsp_waiter.js', 'utf8');

// La marca del ASADERO tal como la guarda Admin V2 (tema claro).
const ASADERO = {
  primary_color: '#51b6e1', secondary_color: '#f2791c', background_color: '#ffedbd', text_color: '#000000',
  font_family: 'Poppins', theme_mode: 'light', gradient_from: '#7ed4f1', gradient_to: '#ffcd94', logo_url: 'data:image/webp;base64,AAAA',
};

function styleNode(text, id = '') {
  return { tagName: 'STYLE', id, textContent: text, remove() { this.removed = true; } };
}

function load({ cached = null } = {}) {
  const store = new Map();
  if (cached) store.set('clonexa_panel_brand_c1', JSON.stringify(cached));
  const head = { children: [], appendChild(n) { this.children.push(n); n.parent = this; return n; } };
  const attrs = {};
  const document = {
    head, readyState: 'complete',
    documentElement: { setAttribute: (k, v) => { attrs[k] = v; }, removeAttribute: (k) => { delete attrs[k]; } },
    createElement: (tag) => (tag === 'style' ? styleNode('') : { tagName: tag.toUpperCase(), id: '' }),
    getElementById: (id) => head.children.find((n) => n.id === id) || null,
    addEventListener() {},
  };
  const timers = [];
  const window = {
    location: { search: '?company_id=c1' },
    localStorage: { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k) },
    setTimeout: (cb) => timers.push(cb),
  };
  const ctx = vm.createContext({ window, document, URLSearchParams, JSON, Math, Number, String, Array, Promise, WeakMap, Map, Set, parseInt, encodeURIComponent });
  vm.runInContext(source, ctx);
  return { Brand: window.CxPanelBrand, head, attrs, store, timers };
}

test('la paleta del ASADERO es clara, con su texto negro y sus colores', () => {
  const { Brand } = load();
  const p = Brand.palette(ASADERO);
  assert.equal(p.mode, 'light');
  assert.equal(p.ink, '#000000');
  assert.equal(p.primary, '#51b6e1');
  assert.equal(p.secondary, '#f2791c');
  assert.equal(p.font, 'Poppins');
  assert.equal(p.logo, ASADERO.logo_url);
  assert.ok(Brand.contrast(p.primaryInk, p.surface) >= 4.5, 'el azul se oscurece para leerse como texto');
  assert.ok(Brand.contrast(p.onPrimary, p.primary) >= 4.5 || Brand.contrast(p.onPrimary, p.primary) >= 3, 'texto legible sobre el primario');
});

test('traduce la hoja oscura del panel a la marca', () => {
  const { Brand } = load();
  const p = Brand.palette(ASADERO);
  const css = Brand.themeCss(`
    :root{color-scheme:dark}
    body{margin:0;background:#080712;color:#f5f3ff}
    .x-card{border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.05);color:#fff}
    .x-btn-primary{border:none;background:linear-gradient(135deg,#ff7a18,#ff2d95 55%,#a855f7)}
    .x-danger{background:#b91c1c;color:#fff}
    .x-sheet{background:#120e20;color:#f5f3ff}
    .x-total{color:#ffd166}
    .x-label{color:#c9c3e6}
    @media (max-width:860px){.x-grid{background:#0d1522}}
  `, p);
  assert.match(css, /color-scheme:light/);
  assert.match(css, /body\{margin:0;background:var\(--cxb-bg\);color:var\(--cxb-ink\)\}/);
  assert.match(css, /\.x-card\{border:1px solid rgba\(0,0,0,0\.12\);background:rgba\(255,255,255,0\.65\);color:var\(--cxb-ink\)\}/);
  assert.match(css, /\.x-btn-primary\{border:none;background:linear-gradient\(135deg,var\(--cxb-primary\),var\(--cxb-primary\) 55%,var\(--cxb-primary2\)\);color:var\(--cxb-on-primary\)\}/);
  assert.match(css, /\.x-danger\{background:#b91c1c;color:#fff\}/);          // un botón rojo sigue con texto blanco
  assert.match(css, /\.x-sheet\{background:var\(--cxb-surface\);color:var\(--cxb-ink\)\}/);   // casi negro no es "de color"
  assert.match(css, /\.x-total\{color:#b45309\}/);                           // el pastel se oscurece sobre fondo claro
  assert.match(css, /\.x-label\{color:var\(--cxb-muted\)\}/);
  assert.match(css, /@media \(max-width:860px\)\{\.x-grid\{background:var\(--cxb-bg2\)\}\}/);
});

test('un tema oscuro de marca conserva los pasteles y el texto claro', () => {
  const { Brand } = load();
  const p = Brand.palette({ primary_color: '#ef233c', secondary_color: '#ff2bd6', background_color: '#050505', text_color: '#f8fafc' });
  assert.equal(p.mode, 'dark');
  const css = Brand.themeCss('.a{color:#ffd166}.b{border:1px solid rgba(255,255,255,.12)}', p);
  assert.match(css, /\.a\{color:#ffd166\}/);
  assert.match(css, /\.b\{border:1px solid rgba\(248,250,252,0\.12\)\}/);
});

test('aplica sobre las hojas del panel, deja las variables y se puede quitar', () => {
  const { Brand, head, attrs } = load();
  const panel = styleNode('body{background:#080712;color:#f5f3ff}');
  head.appendChild(panel);
  Brand.apply(ASADERO);
  assert.equal(attrs['data-cx-brand'], 'light');
  assert.match(panel.textContent, /var\(--cxb-bg\)/);
  const vars = head.children.find((n) => n.id === 'cxPanelBrand049V');
  assert.match(vars.textContent, /--cxb-primary:#51b6e1/);
  assert.match(vars.textContent, /--cxb-font:"Poppins"/);
  assert.match(vars.textContent, /\.csh-brand,html\[data-cx-brand\] \.wtr-brand,html\[data-cx-brand\] \.ktc-brand\{font-size:0/);   // logo en el ingreso
  assert.ok(head.children.some((n) => n.tagName === 'LINK' && /fonts\.googleapis\.com\/css2\?family=Poppins/.test(n.href)));
  Brand.apply(ASADERO);                                           // aplicar dos veces no traduce lo ya traducido
  assert.equal(panel.textContent, Brand.themeCss('body{background:#080712;color:#f5f3ff}', Brand.palette(ASADERO)));
  Brand.clear();
  assert.equal(panel.textContent, 'body{background:#080712;color:#f5f3ff}');
  assert.equal(attrs['data-cx-brand'], undefined);
});

test('load: con el interruptor guarda y aplica; sin él lo quita y no toca nada', async () => {
  const { Brand, head, store } = load();
  const panel = styleNode('body{background:#080712}');
  head.appendChild(panel);
  const asked = [];
  await Brand.load(async (path) => { asked.push(path); return { enabled: true, branding: ASADERO }; });
  assert.deepEqual(asked, ['/panel-theme']);
  assert.ok(store.has('clonexa_panel_brand_c1'));
  assert.match(panel.textContent, /--cxb-bg/);
  await Brand.load(async () => ({ enabled: false, branding: null }));
  assert.equal(store.has('clonexa_panel_brand_c1'), false);
  assert.equal(panel.textContent, 'body{background:#080712}');
  await Brand.load(async () => { throw new Error('sin red'); });   // sin red: no revienta
  assert.equal(Brand.current(), null);
});

test('con el tema guardado, la pantalla de ingreso ya sale con la marca', () => {
  const { head, timers, attrs } = load({ cached: ASADERO });
  const panel = styleNode('.wtr-login-card{background:rgba(15,12,28,.85)}');
  head.appendChild(panel);
  timers.forEach((cb) => cb());
  assert.equal(attrs['data-cx-brand'], 'light');
  assert.match(panel.textContent, /background:var\(--cxb-surface\)/);
});

test('la hoja real del mesero queda sin blancos sobre fondo claro', () => {
  const { Brand } = load();
  const css = waiterCss.slice(waiterCss.indexOf('style.textContent = `') + 21, waiterCss.indexOf('`;', waiterCss.indexOf('style.textContent = `')));
  const out = Brand.themeCss(css, Brand.palette(ASADERO));
  assert.doesNotMatch(out, /background:#080712/);
  assert.doesNotMatch(out, /\.wtr-login-card input\{[^}]*color:#fff/);
  assert.match(out, /\.wtr-brand\{[^}]*color:var\(--cxb-primary-ink\)/);
});
