// 049Y: imprimir la cuenta de un domicilio desde el panel de caja (interruptor
// delivery_print, hoy ASADERO): botón en el detalle, el documento con cliente,
// dirección, domicilio aparte y estado del pago, y reimpresión desde
// "Domicilios cobrados" del turno.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { FakeStorage, boot, flush, saleDocSource } = require('./_cashier_boot.cjs');
const vm = require('node:vm');

const DELIVERY = {
  id: 'd1', order_number: 'HSP-0042', table_number: 'Domicilio 4F2A', status: 'entregado', total: 45000,
  created_at: new Date().toISOString(),
  items: [
    { id: 'l1', name: 'Pollo asado', quantity: 2, unit_price: 20000, subtotal: 40000, station: 'parrilla' },
    { id: 'l2', name: 'Valor domicilio', quantity: 1, unit_price: 5000, subtotal: 5000, station: 'domicilio' },
  ],
  metadata: { delivery: { customer_name: 'Ana Perez', address: 'Calle 10 # 20-30', payment_method: 'qr', payment_status: 'por_verificar' } },
};

const DOCUMENT = {
  title: 'CUENTA DE COBRO', not_invoice_notice: 'NO ES FACTURA DE VENTA', number: 'CC-000010', issuer: { trade_name: 'Asadero El Socio', nit: '900123456-7' },
  lines: [{ qty: '2', name: 'Pollo asado', subtotal: 40000 }], products_total: 40000, delivery_fee: 5000, total: 45000,
  delivery: { customer_name: 'Ana Perez', customer_phone: '573001234567', address: 'Calle 10 # 20-30', address_notes: 'Torre 2',
    payment_method_label: 'Transferencia', payment_state: 'PAGO POR VERIFICAR · la caja aún no confirma el dinero. No entregar como pagado.',
    collect: false, pending_verification: true, change: '' },
};

function routes(flag, documentCalls) {
  return (url, options = {}) => {
    if (url.includes('/caja/documento')) {
      documentCalls.push(JSON.parse(options.body));
      return [200, { ok: true, document: DOCUMENT }];
    }
    if (url.includes('/orders?status=active')) return [200, { orders: [DELIVERY] }];
    if (url.includes('/waiter-ordering/menu')) return [200, { categories: [] }];
    if (url.includes('/waiter-ordering/caja/config')) return [200, { direct_sale: true, delivery: true, redesign: true, delivery_print: flag }];
    if (url.includes('/caja/resumen')) return [200, { sold: 0, charged: 0, pending: 0, orders: 0, accounts: 0, ticket: 0, deliveries: 1, tables: 0, methods: [], direct_sales: [],
      deliveries_paid: [{ id: 'd0', label: 'Domicilio 0041', customer: 'Luis', total: 38000, method: 'cash', method_label: 'Efectivo', closed_at: new Date().toISOString() }],
      charged_accounts: [{ key: 'd0', order_ids: ['d0'], label: 'Domicilio 0041', channel: 'domicilio', channel_label: 'Domicilio', numbers: ['0041'], document_number: '',
        customer: 'Luis', waiter: '', total: 38000, method: 'cash', method_label: 'Efectivo', closed_at: new Date().toISOString(), items: [] }] }];
    if (url.includes('/caja-arqueo/')) return [403, { detail: 'cash_count_not_enabled' }];
    if (url.includes('/domicilios/')) return [200, { drivers: [] }];
    if (url.includes('/mini-panel-operational-session')) return [200, { operational_session: { status: 'active', active_seconds: 0, break_seconds: 0 } }];
    return [404, {}];
  };
}

async function ready(flag) {
  const local = new FakeStorage();
  local.setItem('clonexa_cashier_token_c1', 'jwt');
  const documentCalls = [];
  const b = boot({ local, routes: routes(flag, documentCalls) });
  for (let i = 0; i < 8; i += 1) await flush();
  return { b, documentCalls };
}

async function openDelivery(b) {
  b.click('data-csh-open-delivery', 'd1');
  for (let i = 0; i < 4; i += 1) await flush();
}

test('el detalle del domicilio tiene "Imprimir cuenta" e imprime ese pedido', async () => {
  const { b, documentCalls } = await ready(true);
  await openDelivery(b);
  assert.match(b.root.innerHTML, /Domicilio/);
  assert.match(b.root.innerHTML, /data-csh-print-order="d1"[^>]*>🖨 Imprimir cuenta/);
  b.click('data-csh-print-order', 'd1');
  for (let i = 0; i < 4; i += 1) await flush();
  assert.deepEqual(documentCalls[0], { order_ids: ['d1'] });
  const frame = b.body.children.find((c) => c.tagName === 'iframe');
  assert.ok(frame, 'prepara el marco de impresión');
  assert.match(frame.written, /CUENTA DE COBRO/);
  assert.match(frame.written, /NO ES FACTURA DE VENTA/);
  assert.match(frame.written, /Ana Perez/);
  assert.match(frame.written, /Calle 10 # 20-30/);
  assert.match(frame.written, /<span>Domicilio<\/span><strong>\$5\.000<\/strong>/, 'el domicilio en su propia línea');
  assert.match(frame.written, /PAGO POR VERIFICAR/);
  assert.match(frame.written, /cxdoc-pay-state[^"]*is-pending/);
});

test('los domicilios cobrados se reimprimen desde «Cobrados» (049Z: ya no ocupan la pantalla)', async () => {
  const { b, documentCalls } = await ready(true);
  assert.doesNotMatch(b.root.innerHTML, /Domicilio 0041/);
  b.click('data-csh-charged-open');
  for (let i = 0; i < 4; i += 1) await flush();
  assert.match(b.root.innerHTML, /Domicilio 0041/);
  b.click('data-csh-print-ids', 'd0');
  for (let i = 0; i < 4; i += 1) await flush();
  assert.deepEqual(documentCalls[0], { order_ids: ['d0'] });
});

test('sin el interruptor, el detalle y el tablero quedan como antes', async () => {
  const { b } = await ready(false);
  await openDelivery(b);
  assert.doesNotMatch(b.root.innerHTML, /data-csh-print-order="d1"/);
});

test('el documento de una mesa no cambia (sin bloque de domicilio)', () => {
  const ctx = vm.createContext({ window: {}, document: {}, Number, String, Date, Math });
  vm.runInContext(saleDocSource, ctx);
  const html = ctx.window.CxSaleDocument.documentBody({ ...DOCUMENT, delivery: undefined, payment_label: 'Efectivo' });
  assert.doesNotMatch(html, /cxdoc-delivery|cxdoc-pay-state|<span>Domicilio<\/span>/);
  assert.match(html, /<span>Pago<\/span><strong>Efectivo<\/strong>/);
});
