// 049Z: link de domicilios con el interruptor checkout_v2 (hoy ASADERO):
// pago por transferencia con el QR del local (el pedido queda por verificar)
// y sin botones de ubicación: un texto pide compartirla por WhatsApp después
// de confirmar. Sin el interruptor, el formulario de siempre.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { flush } = require('./_cashier_boot.cjs');

const kitSource = readFileSync('app/web/hsp_menu_kit.js', 'utf8');
const deliverySource = readFileSync('app/web/hsp_delivery.js', 'utf8');

function cartaData(extra) {
  return {
    ok: true, company_name: 'Asadero El Socio', quantity_buttons: [], menu_emojis: false, delivery_fee: 5000, eta_minutes: 40,
    categories: [{ key: 'pollo', label: 'Pollo', products: [{ id: 'p1', name: 'Pollo asado', price: 20000 }] }],
    has_payment_qr: true, whatsapp_location: false, whatsapp_number: '573110000000', ...extra,
  };
}

function page(data) {
  const listeners = {};
  const app = { innerHTML: '' };
  const calls = [];
  const document = {
    getElementById: (id) => (id === 'app' ? app : null),
    createElement: () => ({ id: '', textContent: '', appendChild() {} }),
    head: { appendChild() {} }, body: { appendChild() {} },
    addEventListener: (type, cb) => { (listeners[type] = listeners[type] || []).push(cb); },
  };
  const fetch = (url, options = {}) => {
    calls.push({ url, options });
    const body = url.includes('/orders')
      ? { ok: true, order_number: 'HSP-0042', total: 25000, eta_minutes: 40, payment_status: 'por_verificar' }
      : data;
    return Promise.resolve({ ok: true, status: url.includes('/orders') ? 201 : 200, json: () => Promise.resolve(body) });
  };
  const ctx = vm.createContext({
    window: { location: { search: '?c=c1&s=K7PM2QX9HD' }, scrollTo() {} }, document, fetch, navigator: {},
    URLSearchParams, Intl, JSON, Math, Number, String, Array, Promise, Error, encodeURIComponent,
  });
  ctx.window.document = document;
  vm.runInContext(kitSource, ctx);
  vm.runInContext(deliverySource, ctx);
  const p = ctx.window.CxDeliveryPage;
  const toCheckout = () => {
    p.state.cart = [{ inventory_item_id: 'p1', name: 'Pollo asado', unit_price: 20000, quantity: 1 }];
    p.state.form.customer_name = 'Ana';
    p.state.form.address = 'Calle 10 # 20-30';
    p.state.screen = 'checkout';
    p.render();
  };
  const choose = (value) => (listeners.change || []).forEach((cb) => cb({ target: { value, closest: (s) => (s === '[data-dom-payment]' ? {} : null) } }));
  const click = (attr) => (listeners.click || []).forEach((cb) => cb({ target: { closest: (s) => (s === `[${attr}]` ? { getAttribute: () => '', disabled: false } : null) } }));
  return { app, calls, p, toCheckout, choose, click };
}

test('con checkout_v2 el formulario ya no tiene botones de ubicación: un texto pide compartirla por WhatsApp', async () => {
  const t = page(cartaData({ checkout_v2: true }));
  await flush(); await flush();
  t.toCheckout();
  assert.doesNotMatch(t.app.innerHTML, /data-dom-locate/);
  assert.doesNotMatch(t.app.innerHTML, /Usar mi ubicacion actual/);
  assert.doesNotMatch(t.app.innerHTML, /Compartir ubicacion por WhatsApp/);
  assert.match(t.app.innerHTML, /data-dom-location-info/);
  assert.match(t.app.innerHTML, /Después de confirmar el pedido, <b>compártenos tu ubicación por WhatsApp<\/b>/);
});

test('transferencia muestra el QR del local y el pedido queda por verificar', async () => {
  const t = page(cartaData({ checkout_v2: true }));
  await flush(); await flush();
  t.toCheckout();
  assert.match(t.app.innerHTML, /value="transfer"[^>]*> Transferencia/);
  t.choose('transfer');
  assert.match(t.app.innerHTML, /data-dom-transfer/);
  assert.match(t.app.innerHTML, /\/payment-qr\?s=K7PM2QX9HD/);
  assert.match(t.app.innerHTML, /por verificar/);
  t.click('data-dom-submit');
  await flush(); await flush();
  const sent = JSON.parse(t.calls.find((c) => c.url.includes('/orders')).options.body);
  assert.equal(sent.payment_method, 'transfer');
  assert.equal(sent.latitude, null);
  assert.match(t.app.innerHTML, /Recuerda enviar la foto del comprobante/);
  assert.match(t.app.innerHTML, /Compártenos tu ubicación por WhatsApp/);
});

test('sin el QR cargado, transferencia sigue disponible y avisa que los datos llegan por WhatsApp', async () => {
  const t = page(cartaData({ checkout_v2: true, has_payment_qr: false }));
  await flush(); await flush();
  t.toCheckout();
  t.choose('transfer');
  assert.doesNotMatch(t.app.innerHTML, /payment-qr/);
  assert.match(t.app.innerHTML, /te compartimos los datos de pago por WhatsApp/);
});

test('sin el interruptor, el formulario de siempre', async () => {
  const t = page(cartaData({}));
  await flush(); await flush();
  t.toCheckout();
  assert.match(t.app.innerHTML, /data-dom-locate/);
  assert.doesNotMatch(t.app.innerHTML, /value="transfer"/);
  assert.match(t.app.innerHTML, /Pago por QR/);
});
