// Domicilios por WhatsApp (048N): public carta (hsp_delivery.js), caja
// section (hsp_cashier.js), kitchen comanda (hsp_kitchen.js) and portal
// (client.js). Runs the real files.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { FakeStorage, boot, flush } = require('./_cashier_boot.cjs');

const kitSource = readFileSync('app/web/hsp_menu_kit.js', 'utf8');
const deliverySource = readFileSync('app/web/hsp_delivery.js', 'utf8');
const kitchenSource = readFileSync('app/web/hsp_kitchen.js', 'utf8').replace(/\r\n/g, '\n');
const clientSource = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');

// ------------------------------------------------------------ carta ---
const CARTA = {
  ok: true,
  company_name: 'Asadero El Socio',
  categories: [
    { key: 'pollo', label: 'Pollo', has_image: true, products: [{ id: 'p1', name: 'Pollo asado', price: 20000, has_image: true }] },
    { key: 'gaseosa', label: 'Gaseosa', has_image: false, products: [{ id: 'g1', name: 'Gaseosa', price: 4000 }] },
  ],
  quantity_buttons: [],
  menu_emojis: true,
  delivery_fee: 5000,
  eta_minutes: 40,
  has_payment_qr: true,
  phone_hint: '***4567',
  whatsapp_location: false,
  whatsapp_number: '573110000000',
};

function carta({ search = '?c=c1&s=codigo123456', routes } = {}) {
  const listeners = {};
  const app = { innerHTML: '' };
  const calls = [];
  const element = () => ({ id: '', textContent: '', appendChild() {} });
  const document = {
    getElementById: (id) => (id === 'app' ? app : null),
    createElement: element,
    head: { appendChild() {} },
    body: { appendChild() {} },
    addEventListener: (type, cb) => { (listeners[type] = listeners[type] || []).push(cb); },
  };
  const fetch = (url, options = {}) => {
    calls.push({ url, options });
    const [status, body] = routes(url, options);
    return Promise.resolve({ ok: status < 300, status, json: () => Promise.resolve(body) });
  };
  const ctx = vm.createContext({
    window: { location: { search } }, document, fetch, navigator: {}, URLSearchParams, Intl, JSON, Math, Number, String, Array, Promise, Error, encodeURIComponent,
  });
  ctx.window.document = document;
  vm.runInContext(kitSource, ctx);
  vm.runInContext(deliverySource, ctx);
  const click = (attr, value = '') => {
    const target = { closest: (sel) => (sel === `[${attr}]` ? { getAttribute: () => value, disabled: false } : null) };
    (listeners.click || []).forEach((cb) => cb({ target }));
  };
  return { ctx, app, calls, click, page: ctx.window.CxDeliveryPage };
}

const cartaRoutes = (url) => {
  if (url.includes('/orders')) return [201, { ok: true, order_number: 'HSP-0042', total: 45000, eta_minutes: 40, payment_status: 'por_verificar' }];
  return [200, CARTA];
};

test('carta: same visual menu (categories with photo/emoji) from the link', async () => {
  const c = carta({ routes: cartaRoutes });
  await flush(); await flush();
  assert.equal(c.calls[0].url, '/api/v1/domicilios/public/c1?s=codigo123456');
  assert.match(c.app.innerHTML, /Pedido a domicilio[\s\S]*Asadero El Socio/);
  assert.match(c.app.innerHTML, /data-dom-cat="pollo"[\s\S]*background-image:url\('\/api\/v1\/companies\/c1\/waiter-ordering\/categories\/pollo\/image'\)/);
  assert.match(c.app.innerHTML, /data-dom-cat="gaseosa"[\s\S]*wtr-emoji/);
  c.click('data-dom-cat', 'pollo');
  assert.match(c.app.innerHTML, /data-dom-product="p1"[\s\S]*Pollo asado[\s\S]*\$\s?20\.000/);
});

test('carta: checkout shows subtotal + domicilio = total, name, address, location and payments', async () => {
  const c = carta({ routes: cartaRoutes });
  await flush(); await flush();
  c.page.state.cart.push({ inventory_item_id: 'p1', menu_product_id: 'p1', name: 'Pollo asado', unit_price: 20000, quantity: 2, observations: 'sin sal', quick_notes: [], term: '' });
  c.click('data-dom-checkout');
  const html = c.app.innerHTML;
  assert.match(html, /Subtotal<\/span><b>\$\s?40\.000[\s\S]*Domicilio<\/span><b>\$\s?5\.000[\s\S]*Total<\/span><b>\$\s?45\.000/);
  assert.match(html, /data-dom-field="customer_name"[\s\S]*data-dom-field="address"/);
  assert.match(html, /Usar mi ubicacion actual/);
  assert.match(html, /href="https:\/\/wa\.me\/573110000000\?text=[^"]+"[^>]*>Compartir ubicacion por WhatsApp/);
  assert.match(html, /Efectivo contra entrega[\s\S]*Datafono contra entrega[\s\S]*Pago por QR/);
  assert.match(html, /Pagas con/);

  c.page.state.form.payment_method = 'qr';
  c.page.render();
  assert.match(c.app.innerHTML, /src="\/api\/v1\/domicilios\/public\/c1\/payment-qr\?s=codigo123456"/);
  assert.match(c.app.innerHTML, /envia la foto del comprobante a nuestro chat de WhatsApp/);
});

test('carta: without a payment QR there is no QR option', async () => {
  const c = carta({ routes: (url) => [200, { ...CARTA, has_payment_qr: false }] });
  await flush(); await flush();
  c.page.state.cart.push({ inventory_item_id: 'g1', name: 'Gaseosa', unit_price: 4000, quantity: 1 });
  c.click('data-dom-checkout');
  assert.doesNotMatch(c.app.innerHTML, /Pago por QR/);
});

test('carta: validation, cambio and a payload without prices', async () => {
  const c = carta({ routes: cartaRoutes });
  await flush(); await flush();
  assert.equal(c.page.checkoutProblem(), 'Agrega al menos un producto.');
  c.page.state.cart.push({ inventory_item_id: 'p1', name: 'Pollo asado', unit_price: 20000, quantity: 2, observations: 'sin sal', quick_notes: ['Sin sal'], term: '' });
  assert.equal(c.page.checkoutProblem(), 'Escribe tu nombre.');
  Object.assign(c.page.state.form, { customer_name: 'Ana', address: 'Calle 10 # 20-30', pays_with: '30.000' });
  assert.match(c.page.checkoutProblem(), /menor al total/);
  c.page.state.form.pays_with = '100000';
  assert.equal(c.page.checkoutProblem(), '');
  c.page.state.location = { latitude: 4.6, longitude: -74.08 };
  const payload = c.page.orderPayload();
  assert.equal(payload.s, 'codigo123456');
  assert.equal(payload.pays_with, 100000);
  assert.equal(payload.latitude, 4.6);
  assert.deepEqual(JSON.parse(JSON.stringify(payload.items)), [{ inventory_item_id: 'p1', quantity: 2, observations: 'sin sal', quick_notes: ['Sin sal'], term: '' }]);
  assert.equal('unit_price' in payload.items[0], false, 'el precio lo pone el servidor');
});

test('carta: order confirmed screen, and a used/expired link shows how to get a new one', async () => {
  const c = carta({ routes: cartaRoutes });
  await flush(); await flush();
  c.page.state.cart.push({ inventory_item_id: 'p1', name: 'Pollo asado', unit_price: 20000, quantity: 1 });
  Object.assign(c.page.state.form, { customer_name: 'Ana', address: 'Calle 10 # 20-30', payment_method: 'qr' });
  c.page.state.screen = 'checkout';
  c.click('data-dom-submit');
  await flush(); await flush();
  assert.match(c.app.innerHTML, /Pedido recibido[\s\S]*#0042[\s\S]*40 minutos[\s\S]*foto del comprobante/);

  const gone = carta({ routes: () => [410, { detail: 'Este enlace ya vencio o ya se uso. Escribenos de nuevo por WhatsApp para recibir uno nuevo.' }] });
  await flush(); await flush();
  assert.match(gone.app.innerHTML, /Enlace no disponible[\s\S]*Escribenos de nuevo por WhatsApp/);
});

// ------------------------------------------------------------- caja ---
const T0 = Date.now();
const ago = (m) => new Date(T0 - m * 60000).toISOString();
const DELIVERY_QR = {
  id: 'd1', order_number: 'HSP-0042', table_key: 'domicilio 4f2a', table_number: 'Domicilio 4F2A', status: 'entregado', total: 45000, created_at: ago(20),
  items: [{ name: 'Pollo asado', quantity: 2, unit_price: 20000, subtotal: 40000 }, { name: 'Valor domicilio', quantity: 1, unit_price: 5000, subtotal: 5000, station: 'domicilio' }],
  metadata: { delivery: { customer_name: 'Ana Perez', customer_phone: '573001234567', address: 'Calle 10 # 20-30', location_url: 'https://maps.google.com/?q=4.6,-74.08', payment_method: 'qr', payment_status: 'por_verificar', total: 45000, fee: 5000, driver: null, notified: {} } },
};
const TABLE = { id: 'o1', table_key: 'mesa 3', table_number: 'Mesa 3', status: 'alistando', total: 9000, created_at: ago(5), metadata: {}, items: [] };

function cajaRoutes(orders, extra = () => null) {
  return (url, options) => {
    const custom = extra(url, options);
    if (custom) return custom;
    if (url.includes('/orders?status=active')) return [200, { orders }];
    if (url.includes('/caja/config')) return [200, { direct_sale: false, delivery: true }];
    if (url.includes('/waiter-ordering/menu')) return [200, { categories: [] }];
    if (url.includes('/mini-panel-refresh')) return [200, { access_token: 'renewed' }];
    return [404, {}];
  };
}

async function caja(routes) {
  const local = new FakeStorage();
  local.setItem('clonexa_cashier_token_c1', 'jwt-caja');
  const b = boot({ local, routes });
  b.ctx.window.confirm = () => true;
  await flush(); await flush(); await flush();
  return b;
}

test('caja: domicilios in their own section, never mixed with the tables', async () => {
  const b = await caja(cajaRoutes([TABLE, DELIVERY_QR]));
  const html = b.root.innerHTML;
  const [tablesPart, deliveryPart] = html.split('🛵 Domicilios');
  assert.ok(deliveryPart, 'sección Domicilios');
  assert.match(tablesPart, /data-csh-open-table="mesa 3"/);
  assert.doesNotMatch(tablesPart, /Domicilio 4F2A|domicilio 4f2a/);
  assert.match(deliveryPart, /data-csh-open-delivery="d1"[\s\S]*#0042[\s\S]*Ana Perez · Calle 10 # 20-30[\s\S]*⚠ Pago QR por verificar[\s\S]*\$\s?45\.000/);
});

test('caja: a QR payment shows the warning and cannot be dispatched or closed before verifying', async () => {
  const b = await caja(cajaRoutes([DELIVERY_QR]));
  b.click('data-csh-open-delivery', 'd1');
  const html = b.root.innerHTML;
  assert.match(html, /PAGO POR QR SIN VERIFICAR[\s\S]*Un comprobante se puede falsificar[\s\S]*data-csh-verify-payment/);
  assert.match(html, /Abrir en el mapa/);
  assert.match(html, /data-csh-dispatched disabled/);
  assert.doesNotMatch(html, /data-csh-delivery-pay=/);
  assert.match(html, /Verifica el pago antes de cerrar/);

  b.click('data-csh-verify-payment');
  await flush(); await flush();
  const call = b.calls.find((c) => c.url.endsWith('/api/v1/domicilios/companies/c1/orders/d1/verify-payment'));
  assert.ok(call, 'verifica en el servidor');
  assert.equal(call.options.method, 'POST');
});

test('caja: send to a domiciliario from the Workforce list', async () => {
  const verified = JSON.parse(JSON.stringify(DELIVERY_QR));
  verified.metadata.delivery.payment_status = 'verificado';
  const b = await caja(cajaRoutes([verified], (url) => {
    if (url.endsWith('/drivers')) return [200, { drivers: [{ employee_id: 'e7', name: 'Pedro Moto', phone: '573112223344' }] }];
    if (url.includes('/assign') || url.includes('/dispatched')) return [200, { ok: true }];
    return null;
  }));
  b.click('data-csh-open-delivery', 'd1');
  assert.match(b.root.innerHTML, /QR verificado ✓/);
  assert.match(b.root.innerHTML, /data-csh-delivery-pay="transfer"[^>]*>Cerrar \(pagado por QR\)/);
  b.click('data-csh-drivers-toggle');
  await flush(); await flush();
  assert.match(b.root.innerHTML, /data-csh-assign-driver="e7"[^>]*>Pedro Moto · 573112223344/);
  b.click('data-csh-assign-driver', 'e7');
  await flush(); await flush();
  const assign = b.calls.find((c) => c.url.endsWith('/orders/d1/assign'));
  assert.deepEqual(JSON.parse(assign.options.body), { employee_id: 'e7' });
});

test('caja: a company without the module shows no Domicilios section', async () => {
  const b = await caja((url) => {
    if (url.includes('/caja/config')) return [200, { direct_sale: false, delivery: false }];
    if (url.includes('/orders?status=active')) return [200, { orders: [TABLE] }];
    if (url.includes('/mini-panel-refresh')) return [200, { access_token: 'x' }];
    return [200, { categories: [] }];
  });
  assert.doesNotMatch(b.root.innerHTML, /Domicilios/);
});

// ---------------------------------------------------------- kitchen ---
function kitchenFn(name) {
  const start = kitchenSource.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = kitchenSource.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

test('cocina: a domicilio comanda says so and shows the address', () => {
  const ctx = vm.createContext({ String });
  vm.runInContext(['h', 'deliveryTag'].map(kitchenFn).join('\n'), ctx);
  assert.match(ctx.deliveryTag({ delivery: { customer_name: 'Ana', address: 'Calle 10 # 20-30' } }), /🛵 DOMICILIO · Ana<small>Calle 10 # 20-30<\/small>/);
  assert.equal(ctx.deliveryTag({ delivery: null }), '');
});

// ----------------------------------------------------------- portal ---
function clientFn(name) {
  const start = clientSource.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = clientSource.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

function portal(active = true) {
  const ctx = vm.createContext({
    h: (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
    isClientModuleActive: (code) => active && code === 'domicilios_whatsapp',
    botWhatsAppStatusLabel027F: (s) => s,
    botWhatsAppQr027F: () => '',
    String, Array, Number, JSON,
  });
  const constant = (name) => {
    const start = clientSource.indexOf(`\n  const ${name} = `);
    const end = clientSource.indexOf(';\n', start) + 2;
    return clientSource.slice(start, end).replace(`const ${name}`, `var ${name}`);
  };
  vm.runInContext(
    [constant('CX_DOM_DAYS_048N'), constant('CX_DOM_WARNING_048N'), 'var cxDom048N = { settings: null, hasQr: false, qrUrl: "", message: "", error: "", busy: false, forbidden: false };',
      ...['cxDomScheduleHtml048N', 'cxDomFormHtml048N', 'cxDomReadForm048N', 'cxBotWaClientesCard048N'].map(clientFn)].join('\n'),
    ctx,
  );
  return ctx;
}

test('portal: configuration form with schedule, values, messages, QR and the WhatsApp warning', () => {
  const ctx = portal();
  ctx.cxDom048N.settings = {
    schedule: { mon: [{ from: '11:00', to: '15:00' }, { from: '18:00', to: '22:00' }], tue: [] },
    delivery_fee: 5000, eta_minutes: 40, driver_role: 'domiciliario', greeting_message: 'Hola {link}', closed_message: 'Cerrado {horario}',
  };
  const html = ctx.cxDomFormHtml048N();
  assert.match(html, /Automatizar WhatsApp Web no está permitido por WhatsApp[\s\S]*Usa un número dedicado/);
  assert.match(html, /data-dom-slot-048n="mon:0:from" value="11:00"[\s\S]*data-dom-slot-048n="mon:1:to" value="22:00"/);
  assert.match(html, /data-dom-field-048n="delivery_fee" value="5000"[\s\S]*data-dom-field-048n="eta_minutes" value="40"/);
  assert.match(html, /data-dom-field-048n="greeting_message">Hola \{link\}<\/textarea>[\s\S]*Cerrado \{horario\}/);
  assert.match(html, /Los comprobantes no se guardan en el sistema[\s\S]*data-dom-qr-file-048n/);

  const values = { 'mon:0:from': '11:00', 'mon:0:to': '15:00', 'sat:0:from': '18:00', 'sat:0:to': '02:00', 'sun:0:from': '10:00', 'sun:0:to': '' };
  const fields = { delivery_fee: '6000', eta_minutes: '50', driver_role: 'Domiciliario', greeting_message: 'Hola', closed_message: 'Cerrado' };
  const fakeRoot = {
    querySelector(sel) {
      const slot = /data-dom-slot-048n="([^"]+)"/.exec(sel);
      if (slot) return { value: values[slot[1]] || '' };
      const field = /data-dom-field-048n="([^"]+)"/.exec(sel);
      return field ? { value: fields[field[1]] } : null;
    },
  };
  const read = JSON.parse(JSON.stringify(ctx.cxDomReadForm048N(fakeRoot)));
  assert.deepEqual(read.schedule.mon, [{ from: '11:00', to: '15:00' }]);
  assert.deepEqual(read.schedule.sat, [{ from: '18:00', to: '02:00' }]);
  assert.deepEqual(read.schedule.sun, [], 'franja incompleta no se guarda');
  assert.equal(read.delivery_fee, 6000);
  assert.equal(read.driver_role, 'domiciliario');
});

test('portal: non-admins are told only an admin can configure', () => {
  const ctx = portal();
  ctx.cxDom048N.forbidden = true;
  assert.match(ctx.cxDomFormHtml048N(), /Solo un administrador/);
});

test('portal: the customer WhatsApp number card only with the module, with its warning', () => {
  const ctx = portal();
  assert.equal(ctx.cxBotWaClientesCard048N(null), '');
  const html = ctx.cxBotWaClientesCard048N({ status: 'connected', connected_phone: '573110000000' });
  assert.match(html, /Número de clientes[\s\S]*Nunca entrega datos internos[\s\S]*número dedicado/);
  assert.match(html, /data-bot-wa-cli-048n="start"[\s\S]*data-bot-wa-cli-048n="logout" >/);
  assert.match(clientSource, /if \(!isClientModuleActive\("domicilios_whatsapp"\)\) return null;\n    try \{\n      return await api\(`\/bots\/companies\/\$\{encodeURIComponent\(state\.companyId\)\}\/whatsapp-web\?line=clientes`\);/);
});

test('portal: module route, menu label and Workforce role Domiciliario only with the module', () => {
  assert.match(clientSource, /domicilios_whatsapp: \["Domicilios", "pedidos por WhatsApp", "DOM"\],/);
  assert.match(clientSource, /if \(code === "domicilios_whatsapp"\) \{\s*await renderDeliveryModule048N\(\);/);
  assert.match(clientSource, /if \(!isClientModuleActive\("domicilios_whatsapp"\)\) \{\s*render\(\);\s*return;/);
  assert.match(clientSource, /const roles = isClientModuleActive\("domicilios_whatsapp"\)\n      \? \[\.\.\.baseRoles, \["domiciliario", "Domiciliario"\]\]\n      : baseRoles;/);
});
