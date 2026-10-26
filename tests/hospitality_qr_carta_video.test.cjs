// Carta en video en el QR de la mesa (interruptor carta_video, 057B). Arranca la
// página real (_qr_order_boot) con una carta en video falsa que registra lo que
// recibe: "Agregar" es el MISMO addItem de la lista y el pedido que llega a
// cocina/caja es idéntico. Sin el interruptor nada cambia.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { boot, flush, FakeStorage } = require('./_qr_order_boot.cjs');

const INVENTORY = [
  { id: 'd1', name: 'Lomo al trapo', price: 42000, category_label: 'FUERTES', description: 'Con papa criolla',
    photo_url: '/menu-media/c1/f.webp', video_url: '/menu-media/c1/v.mp4', poster_url: '/menu-media/c1/p.webp' },
  { id: 'd2', name: 'Limonada de coco', price: 12000, category_label: 'BEBIDAS', photo_url: '/menu-media/c1/l.webp', video_url: '', poster_url: '' },
  { id: 'd3', name: 'Pan de bono', price: 4000, category_label: 'BEBIDAS' },
];

function routesFor({ video = true, inventory = INVENTORY } = {}) {
  return (url, options = {}) => {
    const method = options.method || 'GET';
    if (/\/companies\/c1$/.test(url)) return [401, { detail: 'Token requerido.' }];
    if (url.includes('/companies/c1/branding')) return [200, { branding: { primary_color: '#ff8a1c' } }];
    if (url.includes('/qr-tables/access/verify')) return [200, { access: { active: true } }];
    if (url.includes('/qr-tables/access?')) return [200, { access: { active: false }, company_name: 'Demo', ui: { bar_menu: false } }];
    if (url.includes('/qr-tables/account')) return [200, { account: { total: 0, orders_count: 0, accounts_count: 0, items: [], accounts: [] } }];
    if (url.includes('/assemblies/')) return [200, {}];
    if (url.includes('/inventory-lite')) return [200, { inventory, ...(video === null ? {} : { carta_video: video }) }];
    if (url.includes('/loyalty-campaigns/active')) return [200, {}];
    if (url.endsWith('/orders') && method === 'POST') return [200, { order: { order_number: 'QR-9' } }];
    return [404, { detail: 'not found' }];
  };
}

function fakeFeed() {
  const log = { mounts: [], updates: [], shown: 0, hidden: 0 };
  const api = {
    mount(opts) {
      log.mounts.push(opts);
      const ctl = { active: 0, show() { log.shown += 1; }, hide() { log.hidden += 1; }, update(s) { log.updates.push(s); }, destroy() {}, activate() {} };
      log.controller = ctl;
      return ctl;
    },
    switchButton() { log.switch = log.switch || { hidden: false }; return log.switch; },
  };
  return { api, log };
}

async function settle(page) {
  for (let i = 0; i < 6; i += 1) { await flush(); page.runTimers(); }
}

async function unlocked(opts = {}) {
  const feed = fakeFeed();
  const page = boot({ routes: routesFor(opts), local: opts.local || new FakeStorage() });
  if (opts.feed !== false) page.window.CxMenuVideoFeed = feed.api;
  await settle(page);
  page.input('qrAccessCode025B', 'ABCDE');
  page.click('data-access-verify');
  await settle(page);
  return { page, feed: feed.log };
}

function orderBody(page) {
  const call = page.calls.find((c) => c.url.endsWith('/orders') && (c.options.method || 'GET') === 'POST');
  return call ? JSON.parse(call.options.body) : null;
}

test('con carta_video: se monta la carta en video con video, foto o tarjeta por plato', async () => {
  const { feed } = await unlocked();
  assert.equal(feed.mounts.length, 1);
  const opts = feed.mounts[0];
  assert.deepEqual(opts.items.map((i) => [i.id, i.category, Boolean(i.video_url), Boolean(i.photo_url)]),
    [['d1', 'FUERTES', true, true], ['d2', 'BEBIDAS', false, true], ['d3', 'BEBIDAS', false, false]]);
  assert.equal(opts.items[0].description, 'Con papa criolla');
  assert.equal(opts.accentText, '#111111', 'texto del botón con contraste sobre el color de la marca');
  assert.ok(feed.shown >= 1);
  assert.equal(feed.switch.hidden, true, 'el botón "Carta en video" solo aparece en la lista');
});

test('Agregar en la carta en video usa el mismo carrito y el pedido llega a cocina igual que desde la lista', async () => {
  const fromVideo = await unlocked();
  fromVideo.feed.mounts[0].onAdd('d1');
  fromVideo.feed.mounts[0].onAdd('d1');
  fromVideo.feed.mounts[0].onAdd('d2');
  await settle(fromVideo.page);
  const last = fromVideo.feed.updates[fromVideo.feed.updates.length - 1];
  assert.equal(last.count, 3);
  assert.equal(last.total, 96000);
  assert.equal(fromVideo.feed.mounts[0].qty('d1'), 2);
  fromVideo.feed.mounts[0].onCart();
  await settle(fromVideo.page);
  assert.ok(fromVideo.feed.hidden >= 1, 'el pedido se revisa en el mismo panel de siempre');
  assert.match(fromVideo.page.html(), /Tu pedido[\s\S]*Lomo al trapo[\s\S]*Limonada de coco/);
  fromVideo.page.click('data-submit-order');
  await settle(fromVideo.page);

  const fromList = await unlocked({ video: false });
  fromList.page.click('data-add', 'd1');
  fromList.page.click('data-add', 'd1');
  fromList.page.click('data-add', 'd2');
  fromList.page.click('data-submit-order');
  await settle(fromList.page);
  const a = orderBody(fromVideo.page);
  const b = orderBody(fromList.page);
  assert.ok(a && b, 'los dos envían el pedido');
  const strip = (body) => ({ ...body, account_id: 'x', client_order_id: 'x', idempotency_key: 'x' });
  assert.deepEqual(strip(a), strip(b), 'mismo cuerpo hacia cocina/caja');
});

test('botón Lista: cambia a la carta en lista y lo recuerda en este celular', async () => {
  const local = new FakeStorage();
  const { page, feed } = await unlocked({ local });
  feed.mounts[0].onList();
  await settle(page);
  assert.ok(feed.hidden >= 1);
  assert.equal(feed.switch.hidden, false, 'aparece "Carta en video" para volver');
  assert.match(page.html(), /Explora el menu/);
  assert.equal(local.getItem('clonexa_qr_view_c1'), 'lista');
  const again = await unlocked({ local });
  assert.equal(again.feed.mounts.length, 0, 'abre en lista porque así lo dejó');
});

test('sin carta_video: el QR se ve igual que antes (otra empresa no cambia); la foto solo si el plato la tiene', async () => {
  const plain = INVENTORY.map(({ id, name, price }) => ({ id, name, price }));
  const before = await unlocked({ video: null, inventory: plain, feed: false });
  const off = await unlocked({ video: false, inventory: plain });
  assert.equal(off.feed.mounts.length, 0);
  assert.equal(off.page.html(), before.page.html(), 'misma pantalla que sin esta función');
  assert.doesNotMatch(off.page.html(), /qr-product-photo-057b/);
  const withPhoto = await unlocked({ video: false });
  assert.match(withPhoto.page.html(), /<img class="qr-product-photo-057b" src="\/menu-media\/c1\/f\.webp"/);
  assert.equal(withPhoto.feed.mounts.length, 0);
});
