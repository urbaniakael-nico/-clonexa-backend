// Galería de íconos de Clonexa en la pantalla QR del bar (iconos_carta_clonexa,
// piloto The Time Machine) y en el kit de mesero/caja/domicilios.
// Encendido: <img src=SVG alt=nombre> en categorías y productos. Apagado: el
// HTML es idéntico al de hoy (emojis como antes).
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { boot, flush } = require('./_qr_order_boot.cjs');

const V = 'ic1';
const url = (k) => `/assets/iconos-carta/${k === 'bebida' ? 'bebida-generica' : k}.svg?v=${V}`;
const icon = (key, source = 'auto', word = key) => ({ source, key, url: url(key), word, auto: { key, url: url(key), word, recognized: source !== 'generic' } });
const CATS = [['Agua Cristal', 'agua'], ['Aguardiente Antioqueño', 'aguardiente'], ['Cerveza Aguila', 'cerveza'], ['Chiclets Trident', 'chiclets'],
  ['Cigarrillo Marlboro', 'cigarrillo'], ['Gaseosa Coca Cola', 'gaseosa'], ['Hidratante Gatorade', 'hidratante'], ['Paquete papas', 'paquete'],
  ['Ron Medellín', 'ron'], ['Shot de tequila', 'shot'], ['Tequila José Cuervo', 'tequila'], ['Tiket cover', 'tiket'], ['Vodka Absolut', 'vodka'],
  ['Whiskey Old Parr', 'whiskey']];
const BASE = [...CATS.map(([name], i) => ({ id: `p${i}`, name, price: 5000 })), { id: 'h1', name: 'Hookah menta', price: 30000 }];
const WITH_ICONS = BASE.map((item, i) => ({ ...item, icon: i < CATS.length ? icon(CATS[i][1]) : icon('bebida', 'generic', 'hookah') }));

function routesFor({ inventory, iconos }) {
  return (url2, options = {}) => {
    if (/\/companies\/c1$/.test(url2)) return [200, { name: 'The Time Machine' }];
    if (url2.includes('/companies/c1/branding')) return [200, { branding: {} }];
    if (url2.includes('/qr-tables/access/verify')) return [200, { access: { active: true } }];
    if (url2.includes('/qr-tables/access?')) return [200, { access: { active: false }, company_name: 'The Time Machine', ui: { bar_menu: true } }];
    if (url2.includes('/qr-tables/account')) return [200, { account: { total: 0, orders_count: 0, accounts_count: 0, items: [], accounts: [] } }];
    if (url2.includes('/inventory-lite')) return [200, { inventory, ...(iconos ? { iconos_carta: true } : {}) }];
    if (url2.includes('/loyalty-campaigns/active')) return [200, {}];
    return [404, { detail: 'not found' }];
  };
}
async function settle() { for (let i = 0; i < 6; i += 1) await flush(); }
async function page(opts) {
  const p = boot({ routes: routesFor(opts) });
  await settle();
  p.input('qrAccessCode025B', 'ABCDE');
  p.click('data-access-verify');
  await settle();
  return p;
}

test('encendido: cada categoría del bar con su SVG de Clonexa (img con alt), Hookah con el genérico, nunca el plato', async () => {
  const p = await page({ inventory: WITH_ICONS, iconos: true });
  const html = p.html();
  for (const [name, key] of CATS) {
    const cat = name.split(' ')[0];
    const re = new RegExp(`data-bar-cat="${cat}">\\s*<span class="qrb-cat-icon" aria-hidden="true"><img class="cx-carta-icon" src="${url(key).replace(/[?.]/g, '\\$&')}" alt="${cat}" width="64" height="64"`);
    assert.match(html, re, cat);
  }
  assert.match(html, /data-bar-cat="Hookah">\s*<span class="qrb-cat-icon" aria-hidden="true"><img class="cx-carta-icon" src="\/assets\/iconos-carta\/bebida-generica\.svg\?v=ic1" alt="Hookah"/);
  assert.doesNotMatch(html, /🍽|🍾|🥃|🍸|<svg class="cx-bar-icon"/, 'sin emojis del celular');
  // productos: también con su ícono y el nombre como alt
  p.click('data-bar-cat', 'Aguardiente');
  assert.match(p.html(), /<span class="qrb-product-icon" aria-hidden="true"><img class="cx-carta-icon" src="\/assets\/iconos-carta\/aguardiente\.svg\?v=ic1" alt="Aguardiente Antioqueño"/);
});

test('encendido: la categoría toma el ícono elegido a mano que más se repite; la foto manda en el producto', async () => {
  const inv = [{ id: 'a', name: 'Paquete uno', price: 1, icon: icon('chiclets', 'manual', 'paquete') },
    { id: 'b', name: 'Paquete dos', price: 1, icon: { ...icon('paquete'), source: 'auto' } },
    { id: 'c', name: 'Paquete tres', price: 1, icon: { source: 'photo', key: '', url: '/api/v1/companies/21a3065e-38ee-4fc3-96ed-ae1707a3b8e4/waiter-ordering/products/0f0f0f0f-0000-4000-8000-000000000001/image', word: 'paquete', auto: icon('paquete').auto } }];
  const p = await page({ inventory: inv, iconos: true });
  assert.match(p.html(), /data-bar-cat="Paquete">\s*<span class="qrb-cat-icon" aria-hidden="true"><img class="cx-carta-icon" src="\/assets\/iconos-carta\/chiclets\.svg/);
  p.click('data-bar-cat', 'Paquete');
  assert.match(p.html(), /<img class="cx-carta-icon is-photo" src="\/api\/v1\/companies\/21a3065e-38ee-4fc3-96ed-ae1707a3b8e4\/waiter-ordering\/products\/0f0f0f0f-0000-4000-8000-000000000001\/image" alt="Paquete tres"/);
});

test('apagado (cualquier otra empresa): HTML idéntico al de hoy, con los emojis de siempre', async () => {
  const before = await page({ inventory: BASE, iconos: false });
  const off = await page({ inventory: WITH_ICONS, iconos: false });
  assert.equal(off.html(), before.html(), 'aunque llegaran datos de ícono, sin el interruptor no se pintan');
  assert.match(before.html(), /data-bar-cat="Aguardiente">\s*<span class="qrb-cat-icon" aria-hidden="true">🍾<\/span>/);
  assert.doesNotMatch(before.html(), /cx-carta-icon|iconos-carta/);
});

test('una URL rara nunca se pinta (solo SVG de la galería o la foto del producto)', () => {
  const ctx = vm.createContext({ window: {}, document: {}, Intl, Number, Math, String, Array, Object, JSON });
  vm.runInContext(readFileSync('app/web/hsp_menu_kit.js', 'utf8'), ctx);
  const kit = ctx.window.CxMenuKit;
  for (const bad of ['javascript:alert(1)', 'https://evil.test/x.svg', '/assets/iconos-carta/../x.svg', '/assets/iconos-carta/a.svg" onerror="x', '']) {
    assert.equal(kit.cartaIconHtml079A({ url: bad }, 'x'), '', bad);
  }
  assert.match(kit.cartaIconHtml079A({ url: url('ron'), source: 'auto' }, 'Ron <b>'), /alt="Ron &lt;b&gt;"/);
});

test('kit (mesero, caja, domicilios): con icon usa el SVG en la ranura del emoji; sin icon todo igual que hoy', () => {
  const ctx = vm.createContext({ window: {}, document: {}, Intl, Number, Math, String, Array, Object, JSON });
  vm.runInContext(readFileSync('app/web/hsp_menu_kit.js', 'utf8'), ctx);
  const kit = ctx.window.CxMenuKit;
  const menuOff = [{ key: 'ron', label: 'Ron', has_image: false, products: [] }];
  const menuOn = [{ ...menuOff[0], icon: { source: 'auto', key: 'ron', url: url('ron') } }];
  const off = kit.categoryGridHtml(menuOff, { companyId: 'c1', emojis: true });
  assert.match(off, /wtr-emoji">🥃</);
  assert.equal(kit.categoryGridHtml(menuOff, { companyId: 'c1', emojis: false }), kit.categoryGridHtml(JSON.parse(JSON.stringify(menuOff)), { companyId: 'c1', emojis: false }));
  assert.match(kit.categoryGridHtml(menuOn, { companyId: 'c1', emojis: false }), /wtr-emoji"><img class="cx-carta-icon" src="\/assets\/iconos-carta\/ron\.svg\?v=ic1" alt="Ron"/);
  const prodOn = kit.productGridHtml([{ id: 'p', name: 'Ron viejo', price: 1, icon: icon('ron') }], { companyId: 'c1' });
  assert.match(prodOn, /wtr-prod-emoji"><img class="cx-carta-icon"[^>]*alt="Ron viejo"/);
  // la foto subida sigue mandando aunque haya ícono
  const photo = kit.tileArt('product', { id: 'p', name: 'Ron', has_image: true, icon: icon('ron') }, { companyId: 'c1' });
  assert.equal(photo.type, 'image');
  // mesero/caja/domicilios pasan por el mismo tileArt (sin cambios en sus archivos)
  for (const f of ['hsp_waiter.js', 'hsp_cashier.js', 'hsp_delivery.js']) assert.match(readFileSync(`app/web/${f}`, 'utf8'), /Kit\.(tileArt|categoryGridHtml)/, f);
});
