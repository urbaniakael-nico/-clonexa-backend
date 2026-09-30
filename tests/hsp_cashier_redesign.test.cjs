// 049V: rediseño del panel de caja (interruptor cashier_redesign): franja de
// indicadores del turno, secciones Mesas / Domicilios / Ventas de caja, el Z
// del día y la nueva venta en una sola pantalla con el cobro al final.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { FakeStorage, boot, flush } = require('./_cashier_boot.cjs');

const T0 = Date.now();
const ago = (m) => new Date(T0 - m * 60000).toISOString();

const MENU = {
  quantity_buttons: [], menu_emojis: true, carta: true,
  categories: [
    { key: 'pollos', label: 'Pollos', station: '', has_image: true, image_item_id: 'pollos', image_version: '3', image_fit: 'contain', quick_notes: [], subcategories: [],
      products: [{ id: 'p1', name: 'Pollo asado', price: 42000, carta_kind: 'preparado', station: 'Parrilla', allows_portions: false }] },
    { key: 'bebidas', label: 'Bebidas', station: '', has_image: true, image_item_id: 'bebidas', image_fit: 'contain', quick_notes: [], subcategories: [],
      products: [{ id: 'b1', name: 'Coca-Cola', price: 4500, carta_kind: 'directo', station: '', allows_portions: false }] },
  ],
};

const ORDERS = [
  { id: 'm7', table_key: 'mesa 7', table_number: 'Mesa 7', status: 'entregado', total: 84000, created_at: ago(50), metadata: { waiter: { name: 'Laura' } }, items: [] },
  { id: 'm2', table_key: 'mesa 2', table_number: 'Mesa 2', status: 'alistando', total: 46000, created_at: ago(10), metadata: { waiter: { name: 'Pedro' } }, items: [] },
  // Venta de caja independiente esperando cocina: va a "Ventas de caja", no a Mesas.
  { id: 'v14', table_key: 'venta 014', table_number: 'Venta 014', status: 'alistando', total: 23000, created_at: ago(5), metadata: { cashier_sale: { kind: 'independiente' } }, items: [] },
];

const SUMMARY = {
  sold: 250000, charged: 180000, pending: 70000, orders: 9, accounts: 6, ticket: 41666.67, deliveries: 2, tables: 4,
  since: ago(120), shift_open: true,
  methods: [
    { method: 'cash', label: 'Efectivo', total: 100000, count: 3 },
    { method: 'transfer', label: 'Transferencia', total: 50000, count: 2 },
    { method: 'card', label: 'Tarjeta', total: 30000, count: 1 },
  ],
  direct_sales: [
    { id: 'v14', label: 'Venta 014', total: 23000, paid: false },
    { id: 'v13', label: 'Venta 013', total: 9000, paid: true, method: 'cash', method_label: 'Efectivo', closed_at: ago(20), products: 2 },
  ],
};

const Z = {
  business_day: '2026-09-29', now_local: '29/09/2026 10:42 p. m.', cashier_name: 'Caja Uno', company_name: 'ASADERO EL SOCIO',
  z: { sales: 6, orders: 7, products: 15, total: 180000, methods: SUMMARY.methods, channels: [], items: [{ name: 'Pollo asado', units: 3, total: 126000 }],
    open_count: 2, open_total: 70000, cancelled_count: 0, cancelled_total: 0 },
  history: [],
};

const SAVED_Z = { id: 'z1', number: 7, created_local: '29/09/2026 10:43 p. m.', cashier_name: 'Caja Uno', business_day: '2026-09-29', total: 180000,
  summary: { ...Z.z, company_name: 'ASADERO EL SOCIO' } };

function routes({ redesign = true, orders = ORDERS, summary = SUMMARY, delivery = true } = {}) {
  return (url, options = {}) => {
    if (url.includes('/orders?status=active')) return [200, { orders }];
    if (url.includes('/waiter-ordering/menu')) return [200, MENU];
    if (url.includes('/waiter-ordering/caja/config')) return [200, { direct_sale: true, delivery, redesign }];
    if (url.includes('/caja/resumen')) return [200, summary];
    if (url.includes('/caja/z') && options.method === 'POST') return [201, SAVED_Z];
    if (url.includes('/caja/z')) return [200, Z];
    if (url.includes('/caja/ventas')) return [201, { ok: true, charged: true, label: 'Venta 015', order: { id: 'v15' } }];
    if (url.includes('/qr-tables')) return [200, { tables: [{ label: 'Mesa 1' }] }];
    if (url.includes('/mini-panel-operational-session')) return [200, { operational_session: { status: 'active', active_seconds: 3600, break_seconds: 300 } }];
    if (url.includes('/mini-panel-refresh')) return [200, { access_token: 'renewed' }];
    return [404, {}];
  };
}

async function ready(opts) {
  const local = new FakeStorage();
  local.setItem('clonexa_cashier_token_c1', 'jwt-caja');
  const b = boot({ local, routes: routes(opts) });
  for (let i = 0; i < 6; i += 1) await flush();
  return b;
}

function section(html, key) {
  const start = html.indexOf(`cx5-sec-${key}`);
  assert.ok(start >= 0, `sección ${key}`);
  const next = html.indexOf('cx5-sec cx5-sec-', start + 10);
  return html.slice(start, next < 0 ? undefined : next);
}

test('las tres secciones muestran lo que corresponde, cada una con su contador', async () => {
  const b = await ready();
  const html = b.root.innerHTML;
  assert.equal(b.root.attrs['data-cx5'], '1');
  const mesas = section(html, 'mesas');
  assert.match(mesas, /data-cx5-count="mesas">2</);
  assert.match(mesas, /data-csh-open-table="mesa 7"/);
  assert.match(mesas, /data-csh-open-table="mesa 2"/);
  assert.doesNotMatch(mesas, /Venta 014/);                          // la venta de caja no es una mesa
  assert.match(mesas, /Laura/);
  const ventas = section(html, 'ventas');
  assert.match(ventas, /data-cx5-count="ventas">2</);              // abierta + cobrada del turno
  assert.match(ventas, /data-csh-open-table="venta 014"/);
  assert.match(ventas, /Venta 013/);
  assert.match(ventas, /data-csh-print-order="v13"/);
  const domicilios = section(html, 'domicilios');
  assert.match(domicilios, /data-cx5-count="domicilios">0</);
  assert.match(domicilios, /is-empty/);                             // vacía = una línea, sin cuadrícula
  assert.match(domicilios, /Sin domicilios abiertos/);
  assert.doesNotMatch(domicilios, /cx5-grid/);
});

test('los domicilios salen con su dirección y estado de pago', async () => {
  const delivery = { id: 'd1', order_number: 'QR-1-021', table_number: 'Domicilio A1', status: 'entregado', total: 61000, created_at: ago(30), items: [],
    metadata: { delivery: { customer_name: 'Marcela', address: 'Cra 45 # 12-30', payment_method: 'qr', payment_status: 'por_verificar' } } };
  const b = await ready({ orders: [...ORDERS, delivery] });
  const dl = section(b.root.innerHTML, 'domicilios');
  assert.match(dl, /data-cx5-count="domicilios">1</);
  assert.match(dl, /Cra 45 # 12-30/);
  assert.match(dl, /Pago QR por verificar/);
  assert.doesNotMatch(section(b.root.innerHTML, 'mesas'), /Domicilio/);
});

test('la franja de indicadores cuadra con el resumen del turno', async () => {
  const b = await ready();
  const html = b.root.innerHTML;
  assert.match(html, /data-cx5-kpi="sold">\$\s?250\.000</);
  assert.match(html, /Cobrado \$\s?180\.000 · Por cobrar \$\s?70\.000/);
  assert.match(html, /data-cx5-kpi="orders">9</);
  assert.match(html, /data-cx5-kpi="ticket">\$\s?41\.667</);
  assert.match(html, /data-cx5-kpi="deliveries">2</);
  assert.match(html, /data-cx5-kpi="tables">4</);
  assert.match(html, /data-cx5-method="cash"[\s\S]*?\$\s?100\.000/);
  assert.match(html, /data-cx5-method="transfer"[\s\S]*?\$\s?50\.000/);
  assert.match(html, /data-cx5-method="card"[\s\S]*?\$\s?30\.000/);
  assert.ok(b.calls.some((c) => c.url.includes('/waiter-ordering/caja/resumen')));
});

test('el turno es una línea compacta con Pausa y Cerrar jornada, sin desplegar', async () => {
  const b = await ready();
  const html = b.root.innerHTML;
  assert.match(html, /class="cx5-shift /);
  assert.match(html, /data-csh-active-clock>1:0\d:\d\d</);
  assert.match(html, /data-csh-break-clock>0:05:\d\d</);
  assert.match(html, /data-csh-shift-pause/);
  assert.match(html, /data-csh-shift-finish/);
  assert.doesNotMatch(html, /data-csh-shift-toggle/);
});

test('registrar la red y salir siguen disponibles en el menú ⋯', async () => {
  const b = await ready();
  assert.doesNotMatch(b.root.innerHTML, /data-csh-register-network/);
  b.click('data-csh-more');
  assert.match(b.root.innerHTML, /data-csh-register-network/);
  assert.match(b.root.innerHTML, /data-csh-logout/);
});

test('Sacar Z: muestra totales y métodos, lo registra en el servidor y lo imprime', async () => {
  const b = await ready();
  b.click('data-csh-z-open');
  await flush(); await flush();
  let html = b.root.innerHTML;
  assert.match(html, /data-cx5-z="total">\$\s?180\.000</);
  assert.match(html, /data-cx5-z="sales">6</);
  assert.match(html, /data-cx5-z="products">15</);
  assert.match(html, /Efectivo[\s\S]*?\$\s?100\.000/);
  assert.match(html, /Quedan 2 pedidos sin cobrar/);
  assert.equal(b.calls.some((c) => c.url.includes('/caja/z') && c.options.method === 'POST'), false);   // ver no registra

  b.click('data-csh-z-register');
  await flush(); await flush();
  const post = b.calls.find((c) => c.url.endsWith('/waiter-ordering/caja/z') && c.options.method === 'POST');
  assert.ok(post, 'POST del Z');
  assert.equal(post.options.body, undefined);                          // el cajero no envía cifras
  html = b.root.innerHTML;
  assert.match(html, /Z #0007 registrado · 29\/09\/2026 10:43 p\. m\. · Caja Uno/);
  const frame = b.body.children.find((c) => c.tagName === 'iframe');
  assert.ok(frame, 'se imprime');
  assert.match(frame.written, /CIERRE DE CAJA · Z #0007/);
  assert.match(frame.written, /Cajero<\/span><b>Caja Uno/);
  assert.match(frame.written, /TOTAL<\/span><span>\$\s?180\.000/);
  assert.match(frame.written, /Efectivo \(3\)<\/span><b>\$\s?100\.000/);
  assert.match(frame.written, /Transferencia \(2\)<\/span><b>\$\s?50\.000/);
  assert.match(frame.written, /Tarjeta \(1\)<\/span><b>\$\s?30\.000/);
});

function lastSheet(b) {
  return b.body.children.filter((c) => c.className === 'wtr-sheet-backdrop').pop();
}

function addProduct(b, id) {
  b.click('data-csh-product', id);
  lastSheet(b).querySelector('[data-sheet-add]').fire('click');
}

test('nueva venta: categorías con la imagen completa, sin recorte', async () => {
  const b = await ready();
  b.click('data-csh-new-sale');
  const html = b.root.innerHTML;
  assert.match(html, /class="cx5-cats "/);
  assert.match(html, /<span class="cx5-art" style="--img:url\('[^']*waiter-ordering\/products\/pollos\/image\?v=3'\)"><img src="[^"]*pollos\/image\?v=3"/);
  assert.doesNotMatch(html, /wtr-cat-img/);                         // no el fondo "cover" que recortaba
  const css = b.ctx.document.head.children.map((s) => s.textContent).join('\n');
  assert.match(css, /\.cx5-art img\{position:absolute;inset:0;display:block;width:100%;height:100%;object-fit:contain\}/);
  // Sin categoría elegida, toda la carta se ve en el centro (nunca una pantalla vacía).
  assert.match(html, /data-csh-product="p1"/);
  assert.match(html, /data-csh-product="b1"/);
});

test('una venta completa se arma y se cobra sin salir de la pantalla', async () => {
  const b = await ready();
  b.click('data-csh-new-sale');
  b.click('data-csh-cat', 'bebidas');
  assert.equal(b.ctx.window.history.state.cshDepth, 1);             // la categoría no abre otra página
  addProduct(b, 'b1');
  let html = b.root.innerHTML;
  assert.match(html, /aria-label="Resumen de la venta"/);
  assert.match(html, /1 x Coca-Cola/);
  // Una gaseosa no necesita cocina: se cobra ahí mismo.
  assert.match(html, /aria-checked="true" class="is-on" data-csh-sale-route="now"/);
  assert.match(html, /data-csh-sale-pay="transfer"/);
  b.click('data-csh-sale-step', '0:1');
  assert.match(b.root.innerHTML, /data-cx5-sale-total>\$\s?9\.000</);
  b.click('data-csh-sale-pay', 'transfer');
  await flush(); await flush(); await flush();
  const body = JSON.parse(b.calls.find((c) => c.url.includes('/caja/ventas')).options.body);
  assert.equal(body.payment_method, 'transfer');
  assert.equal(body.send_to_kitchen, false);
  assert.equal(body.items[0].quantity, 2);
  assert.match(b.root.innerHTML, /Venta 015 cobrada\./);
  assert.equal(b.ctx.window.history.state.cshDepth, 0);
});

test('enviar a cocina se sugiere solo cuando hay algo que preparar, y el cajero puede cambiarlo', async () => {
  const b = await ready();
  b.click('data-csh-new-sale');
  addProduct(b, 'p1');
  let html = b.root.innerHTML;
  assert.match(html, /aria-checked="true" class="is-on" data-csh-sale-route="kitchen"/);
  assert.match(html, /Sugerido: tiene platos que se preparan \(Pollo asado\)/);
  assert.match(html, /data-csh-sale-send/);
  assert.doesNotMatch(html, /data-csh-sale-pay=/);                  // se cobra cuando cocina lo marque listo
  b.click('data-csh-sale-route', 'now');                            // lo entrega ya: aparece el cobro
  html = b.root.innerHTML;
  assert.match(html, /data-csh-sale-pay="cash"/);
  addProduct(b, 'b1');                                              // la elección manual se respeta
  assert.match(b.root.innerHTML, /aria-checked="true" class="is-on" data-csh-sale-route="now"/);
});

test('el efectivo sigue pasando por la calculadora de cambio', async () => {
  const b = await ready();
  b.click('data-csh-new-sale');
  addProduct(b, 'b1');
  b.click('data-csh-sale-pay', 'cash');
  const cash = b.body.children.find((c) => /csh-cash-backdrop/.test(c.className));
  assert.ok(cash, 'calculadora de cambio');
  assert.equal(b.calls.some((c) => c.url.includes('/caja/ventas')), false);
});

test('sin el interruptor el panel es exactamente el de antes', async () => {
  const b = await ready({ redesign: false });
  const html = b.root.innerHTML;
  assert.equal(b.root.attrs['data-cx5'], undefined);
  assert.match(html, /<h1>Mesas abiertas<\/h1>/);
  assert.doesNotMatch(html, /cx5-/);
  assert.equal(b.calls.some((c) => c.url.includes('/caja/resumen')), false);
});

test('los tres mini paneles cargan el tema de la empresa antes que su propio código', () => {
  for (const page of ['hsp_cashier.html', 'hsp_waiter.html', 'hsp_kitchen.html']) {
    const html = readFileSync(`app/web/${page}`, 'utf8');
    const brand = html.indexOf('hsp_brand.js');
    assert.ok(brand > 0, page);
    const panel = html.indexOf(page.replace('.html', '.js'));
    assert.ok(brand < panel, `${page}: tema antes del panel`);
  }
  for (const file of ['hsp_waiter.js', 'hsp_kitchen.js', 'hsp_cashier.js']) {
    const src = readFileSync(`app/web/${file}`, 'utf8');
    assert.match(src, /CxPanelBrand\.load\(\(path\) => waiterApi\(path\)\)/, file);
  }
});
