// Carta de bar en la pantalla QR del cliente (qr_bar_menu, hoy solo The Time
// Machine). Arranca la página real con un navegador falso (_qr_order_boot).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { boot, flush } = require('./_qr_order_boot.cjs');

const INVENTORY = [
  { id: 'p1', name: 'Cerveza Aguila', price: 6000 },
  { id: 'p2', name: 'Cerveza Club Colombia', price: 7000 },
  { id: 'p3', name: 'Aguardiente Antioqueño media', price: 60000 },
  { id: 'p4', name: 'Cigarrillos Marlboro', price: 1500 },
  { id: 'p5', name: 'Agua Cristal', price: 3000 },
];

function routesFor({ barMenu = true, logo = 'https://cdn.test/ttm-logo.png', companyName = 'The Time Machine' } = {}) {
  return (url, options = {}) => {
    const method = options.method || 'GET';
    if (/\/companies\/c1$/.test(url)) return [401, { detail: 'Token requerido.' }];
    if (url.includes('/companies/c1/branding')) return [200, { branding: { logo_url: logo } }];
    if (url.includes('/qr-tables/access/verify')) return [200, { access: { active: true } }];
    if (url.includes('/qr-tables/access?')) {
      return [200, { access: { active: false }, company_name: companyName, ui: { bar_menu: barMenu } }];
    }
    if (url.includes('/qr-tables/account')) return [200, { account: { total: 13000, orders_count: 1, accounts_count: 1, items: [], accounts: [] } }];
    if (url.includes('/assemblies/')) return [200, {}];
    if (url.includes('/inventory-lite')) return [200, { inventory: INVENTORY }];
    if (url.includes('/loyalty-campaigns/active')) return [200, {}];
    if (url.includes('/song-requests') && method === 'POST') return [200, { ok: true }];
    if (url.endsWith('/orders') && method === 'POST') return [200, { order: { order_number: 'QR-7' } }];
    return [404, { detail: 'not found' }];
  };
}

async function settle() {
  for (let i = 0; i < 6; i += 1) await flush();
}

async function unlocked(opts = {}) {
  const page = boot({ routes: routesFor(opts), withKit: opts.withKit !== false });
  await settle();
  page.input('qrAccessCode025B', 'ABCDE');
  page.click('data-access-verify');
  await settle();
  return page;
}

test('sin activar: va directo a la clave, sin error técnico (401 Token requerido)', async () => {
  const page = boot({ routes: routesFor() });
  await settle();
  const html = page.html();
  assert.match(html, /Ingresa la clave de activación/);
  assert.doesNotMatch(html, /401|Token requerido|Unauthorized|detail/);
  assert.doesNotMatch(html, /acceso protegido para ordenar desde esta mesa/);
  assert.match(html, /<h1>Mesa 5<\/h1>/);
});

test('el arreglo del 401 aplica también a la pantalla clásica (sin interruptor)', async () => {
  const page = boot({ routes: routesFor({ barMenu: false }) });
  await settle();
  const html = page.html();
  assert.doesNotMatch(html, /Token requerido|401/);
  assert.match(html, /Ingresa clave de activacion/);
  // el nombre llega por el endpoint público de acceso
  assert.match(html, /The Time Machine - acceso protegido para ordenar desde esta mesa/);
});

test('un error técnico de la clave se muestra como mensaje amable', async () => {
  const page = boot({
    routes: (url, options) => (url.includes('/access/verify') ? [500, { detail: 'boom' }] : routesFor()(url, options)),
  });
  await settle();
  page.input('qrAccessCode025B', 'ABCDE');
  page.click('data-access-verify');
  await settle();
  assert.match(page.html(), /No pudimos conectar con el bar/);
  assert.doesNotMatch(page.html(), /500|boom/);
});

test('header: solo "Mesa X" y el logo del bar (inicial si no hay logo)', async () => {
  const page = await unlocked();
  const html = page.html();
  assert.match(html, /<header class="qrb-head">\s*<h1>Mesa 5<\/h1>\s*<div class="qr-logo qrb-logo"><img src="https:\/\/cdn.test\/ttm-logo.png"/);
  assert.doesNotMatch(html, /acceso protegido|CLONEXA|arma tu pedido y queda/);

  const noLogo = await unlocked({ logo: '' });
  assert.match(noLogo.html(), /<div class="qr-logo qrb-logo">T<\/div>/);
});

test('cuenta y canción son líneas compactas y colapsables', async () => {
  const page = await unlocked();
  const html = page.html();
  assert.match(html, /<details class="qrb-line" data-bar-line="account" >\s*<summary><span>🧾 Cuenta total de la mesa<\/span><strong id="qrTableAccountTotal030B">/);
  assert.match(html, /<details class="qrb-line" data-bar-line="song" >\s*<summary><span>🎵 ¿Qué deseas escuchar\?<\/span>/);
});

test('menú agrupado por categoría con su icono; tocar una abre sus productos', async () => {
  const page = await unlocked();
  let html = page.html();
  const tile = (cat, icon) => new RegExp(`data-bar-cat="${cat}">\\s*<span class="qrb-cat-icon" aria-hidden="true">${icon}</span>\\s*<strong>${cat}</strong>`);
  assert.match(html, tile('Cerveza', '🍺'));
  assert.match(html, tile('Aguardiente', '🍶'));
  assert.match(html, tile('Cigarrillos', '🚬'));
  assert.match(html, tile('Agua', '💧'));
  assert.match(html, /data-bar-cat="Cerveza">[\s\S]*?<small>2 productos<\/small>/);
  assert.match(html, /id="qrSearch024X"/, 'se mantiene el buscador');
  assert.doesNotMatch(html, /data-add=/, 'la carta arranca en categorías');

  page.click('data-bar-cat', 'Cerveza');
  html = page.html();
  assert.match(html, /Cerveza Aguila/);
  assert.match(html, /Cerveza Club Colombia/);
  assert.doesNotMatch(html, /Marlboro/);
  assert.match(html, /data-bar-cat-back/);

  page.click('data-bar-cat-back');
  assert.match(page.html(), /data-bar-cat="Cigarrillos"/);

  page.type('qrSearch024X', 'marlboro');
  html = page.html();
  assert.match(html, /Cigarrillos Marlboro/);
  assert.doesNotMatch(html, /Cerveza Aguila/);
});

test('CONFIRMA TU PEDIDO + aviso permanente de productos sin enviar', async () => {
  const page = await unlocked();
  assert.match(page.html(), /<span>CONFIRMA TU PEDIDO<\/span>/);
  assert.doesNotMatch(page.html(), /qrb-pending/);
  assert.doesNotMatch(page.html(), /Ver pedido|Abrir carrito/);

  page.click('data-bar-cat', 'Cerveza');
  page.click('data-add', 'p1');
  page.click('data-inc', 'p1');
  const html = page.html();
  assert.match(html, /class="qrb-pending"[\s\S]*Tienes 2 productos sin enviar/);
  assert.match(html, /qrb-dock-btn has-items/);
  assert.match(html, /2 productos · \$\s?12\.000/);
});

test('confirmar envía el pedido y muestra "¡Pedido enviado a la barra!" con los productos', async () => {
  const page = await unlocked();
  page.click('data-bar-cat', 'Cerveza');
  page.click('data-add', 'p1');
  page.click('data-add', 'p2');
  page.click('data-cart-open');
  page.click('data-submit-order');
  await settle();

  const order = page.calls.find((c) => c.url.endsWith('/orders') && c.options.method === 'POST');
  assert.ok(order, 'se envió el pedido');
  const body = JSON.parse(order.options.body);
  assert.deepEqual(body.items.map((i) => [i.name, i.quantity]), [['Cerveza Aguila', 1], ['Cerveza Club Colombia', 1]]);
  assert.equal(body.source, 'qr');

  let html = page.html();
  assert.match(html, /¡Pedido enviado a la barra!/);
  assert.match(html, /Pedido QR-7/);
  assert.match(html, /<li><strong>1 ×<\/strong> Cerveza Aguila<\/li>/);
  assert.match(html, /<li><strong>1 ×<\/strong> Cerveza Club Colombia<\/li>/);
  assert.doesNotMatch(html, /qrb-pending/, 'ya no quedan productos sin enviar');

  // el cliente debe cerrarla
  page.runTimers();
  assert.match(page.html(), /¡Pedido enviado a la barra!/);
  page.click('data-bar-sent-close');
  html = page.html();
  assert.doesNotMatch(html, /¡Pedido enviado a la barra!/);
});

test('la canción muestra "Tu canción fue enviada" y limpia el campo', async () => {
  const page = await unlocked();
  const input = page.input('qrSongRequest031C', 'Simplemente amigos');
  page.click('data-submit-song');
  await settle();

  const call = page.calls.find((c) => c.url.includes('/song-requests'));
  assert.ok(call);
  assert.equal(JSON.parse(call.options.body).song, 'Simplemente amigos');
  const html = page.html();
  assert.match(html, /Tu canción fue enviada: <strong>Simplemente amigos<\/strong>/);
  assert.match(html, /data-bar-line="song" open/, 'la línea queda abierta para ver el aviso');
  assert.equal(input.value, '');
  assert.match(html, /id="qrSongRequest031C"[^>]*value=""/);
});

test('Asadero/Velvet (sin interruptor): pantalla de siempre', async () => {
  const page = await unlocked({ barMenu: false, companyName: 'ASADERO EL SOCIO' });
  const html = page.html();
  assert.match(html, /Explora el menu/);
  assert.match(html, /arma tu pedido y queda en pendiente para el barman/);
  assert.match(html, /data-category="Todos"/);
  assert.match(html, /Agregar \+/);
  assert.match(html, /Ver pedido|Agrega tu primera bebida/);
  assert.doesNotMatch(html, /qrb-|CONFIRMA TU PEDIDO|data-bar-cat/);

  page.click('data-add', 'p1');
  page.click('data-submit-order');
  await settle();
  assert.match(page.html(), /Tu pedido fue recibido/);
  assert.doesNotMatch(page.html(), /Pedido enviado a la barra/);
});

test('sin el kit de menú cargado, la empresa con interruptor cae a la pantalla clásica', async () => {
  const page = await unlocked({ withKit: false });
  assert.match(page.html(), /Explora el menu/);
  assert.doesNotMatch(page.html(), /qrb-/);
});
