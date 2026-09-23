// Portal "Pedidos por mesero" -> "Documento de venta" configuration, and the
// shared printable document (sale_document.js) used by the caja and the
// portal preview. Only for companies with waiter_ordering.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const client = readFileSync('app/web/client.js', 'utf8');
const saleDocSource = readFileSync('app/web/sale_document.js', 'utf8');

function fn(name) {
  const start = client.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = client.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

function constBlock(name) {
  const start = client.indexOf(`\n  const ${name} = `);
  assert.ok(start >= 0, name);
  const end = client.indexOf('];\n', start);
  return client.slice(start, end + 3).replace(`const ${name}`, `var ${name}`);
}

function saleDoc() {
  const ctx = vm.createContext({ window: {}, String, Number, Math, Date, Array, JSON });
  vm.runInContext(saleDocSource, ctx);
  return ctx.window.CxSaleDocument;
}

function portal({ waiterOrdering = true } = {}) {
  const ctx = vm.createContext({ String, Number, Math, Array, JSON, window: { CxSaleDocument: saleDoc() } });
  vm.runInContext(
    'function h(v){return String(v ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}\n'
      + `function isClientModuleActive(code){return ${waiterOrdering} && code === "waiter_ordering";}\n`
      + 'class FormData { constructor(form){ this.values = form.values; } get(k){ return this.values[k] ?? null; } }\n'
      + constBlock('SALE_DOC_REGIMES_046A')
      + ['cxIsSaleDocumentCode046A', 'cxSaleDocFormPayload046A', 'cxSaleDocPreviewHtml046A', 'cxSaleDocFormHtml046A'].map(fn).join(''),
    ctx,
  );
  return ctx;
}

const DOC = {
  title: 'CUENTA DE COBRO', not_invoice_notice: 'NO ES FACTURA DE VENTA', dian_pending_notice: '',
  number: 'CC-000001', number_label: 'Consecutivo interno', issued_at: '2026-09-23T23:00:00+00:00',
  issuer: { trade_name: 'El Socio <b>', nit: '900', regime: 'No responsable de IVA', logo_url: 'https://cdn.x/logo.png', legal_name: 'Socio SAS', address: 'Cra 1', phone: '300' },
  table: 'Mesa 5', waiter: 'Laura', lines: [{ qty: '3/4', name: 'POLLO Asado', subtotal: 30000 }, { qty: '2', name: 'GASEOSA', subtotal: 9000, observations: 'fria' }],
  subtotal: 36111, iva: 2889, iva_percent: 8, prices_include_iva: true, total: 39000,
  withholdings: 'No somos autorretenedores', resolution: '', footer: 'Gracias por su visita', payment_label: 'Efectivo',
};

// ---------------------------------------------------------------------------
// The printed document
// ---------------------------------------------------------------------------

test('the printed document is a CUENTA DE COBRO that says NO ES FACTURA DE VENTA', () => {
  const html = saleDoc().documentHtml(DOC);
  assert.match(html, /<h1 class="cxdoc-title">CUENTA DE COBRO<\/h1>/);
  assert.equal((html.match(/NO ES FACTURA DE VENTA/g) || []).length, 2);   // top and bottom
  assert.doesNotMatch(html.replace(/NO ES FACTURA DE VENTA/g, ''), /FACTURA/);
  assert.match(html, /Consecutivo interno<\/span><strong>CC-000001/);
});

test('it uses the configured data and the consumed products', () => {
  const html = saleDoc().documentHtml(DOC);
  for (const text of ['El Socio &lt;b&gt;', 'NIT 900', 'Socio SAS', 'No responsable de IVA', 'Cra 1', 'Tel. 300', 'Mesa 5', 'Laura',
    '3/4', 'POLLO Asado', 'fria', 'IVA 8% (incluido)', 'TOTAL', 'Efectivo', 'No somos autorretenedores', 'Gracias por su visita']) {
    assert.ok(html.includes(text), text);
  }
  assert.match(html, /\$30\.000/);
  assert.match(html, /\$39\.000/);
  assert.match(html, /<img class="cxdoc-logo" src="https:\/\/cdn\.x\/logo\.png"/);
  assert.match(html, /@page\{size:80mm auto/);
});

test('an unsafe logo address is never rendered', () => {
  const html = saleDoc().documentHtml({ ...DOC, issuer: { ...DOC.issuer, logo_url: 'javascript:alert(1)' } });
  assert.doesNotMatch(html, /<img/);
});

test('with the DIAN switch the pending-provider notice is printed and it is still not a factura', () => {
  const html = saleDoc().documentHtml({ ...DOC, dian_pending_notice: 'Falta integrar el proveedor tecnológico autorizado por la DIAN.' });
  assert.match(html, /Falta integrar el proveedor/);
  assert.match(html, /CUENTA DE COBRO/);
  assert.match(html, /NO ES FACTURA DE VENTA/);
});

// ---------------------------------------------------------------------------
// Portal module
// ---------------------------------------------------------------------------

test('the module only exists for companies with waiter_ordering', () => {
  assert.equal(portal().cxIsSaleDocumentCode046A('waiter_ordering'), true);
  assert.equal(portal({ waiterOrdering: false }).cxIsSaleDocumentCode046A('waiter_ordering'), false);
  assert.equal(portal().cxIsSaleDocumentCode046A('stock'), false);
  // routed before the generic "se construira" placeholder
  const start = client.indexOf('  async function renderClientModulePlaceholder(code) {');
  assert.match(client.slice(start, start + 300), /cxIsSaleDocumentCode046A\(code\)[\s\S]*renderSaleDocumentModule046A\(\)/);
  assert.match(client, /waiter_ordering: \["Documento de venta", "cuenta de cobro de la caja", "DOC"\]/);
});

test('the form has every requested field, with the DIAN switch off by default', () => {
  const html = portal().cxSaleDocFormHtml046A({ config: {}, next_number: '000001', company_name: 'Asadero', branding_logo_url: 'https://b/logo.png' });
  for (const name of ['logo_url', 'trade_name', 'legal_name', 'nit', 'address', 'phone', 'regime', 'iva_percent', 'prices_include_iva',
    'withholdings', 'prefix', 'numbering_start', 'resolution', 'footer', 'dian_electronic_enabled',
    'dian_resolution_number', 'dian_resolution_date', 'dian_range_from', 'dian_range_to', 'dian_valid_until']) {
    assert.ok(html.includes(`name="${name}"`), name);
  }
  assert.match(html, /<input type="checkbox" name="dian_electronic_enabled" >/);
  assert.match(html, /Habilitado como facturador electrónico ante la DIAN/);
  assert.match(html, /CUENTA DE COBRO<\/b> con la leyenda <b>NO ES FACTURA DE VENTA/);
  assert.match(html, /Próximo número: <b>000001<\/b>/);
  assert.match(html, /placeholder="https:\/\/b\/logo\.png"/);           // branding logo as default
});

test('switching DIAN on shows that the authorized provider is still missing', () => {
  const html = portal().cxSaleDocFormHtml046A({ config: { dian_electronic_enabled: true }, dian_pending_notice: 'Falta integrar el proveedor tecnológico autorizado por la DIAN.' });
  assert.match(html, /name="dian_electronic_enabled" checked/);
  assert.match(html, /cx-saledoc-alert-046a">Falta integrar el proveedor/);
});

test('the form is read into the payload the server validates', () => {
  const values = {
    logo_url: ' https://x/l.png ', trade_name: 'El Socio', legal_name: 'Socio SAS', nit: '900', address: 'Cra 1', phone: '300',
    regime: 'regimen_simple', iva_percent: '8,5', prices_include_iva: 'on', withholdings: '', prefix: 'cc', numbering_start: '100',
    resolution: '', footer: 'Gracias', dian_electronic_enabled: null,
  };
  const payload = portal().cxSaleDocFormPayload046A({ values });
  assert.equal(payload.logo_url, 'https://x/l.png');
  assert.equal(payload.iva_percent, 8.5);
  assert.equal(payload.prices_include_iva, true);
  assert.equal(payload.prefix, 'CC');
  assert.equal(payload.numbering_start, 100);
  assert.equal(payload.dian_electronic_enabled, false);
});

test('the preview renders the server-built document in an isolated frame', () => {
  const html = portal().cxSaleDocPreviewHtml046A(DOC);
  assert.match(html, /<iframe class="cx-saledoc-preview-046a"/);
  assert.match(html, /CUENTA DE COBRO/);
  assert.match(html, /NO ES FACTURA DE VENTA/);
  assert.match(portal().cxSaleDocPreviewHtml046A(null), /Guarda la configuración/);
});
