// Cotizaciones y cuentas de cobro v2 (interruptor quotes_v2):
// - Tres pasos; las tres tarjetas de origen y el cliente obligatorio para seguir.
// - Desde producción: líneas con los cierres (cantidad fija), aviso de ya cobradas.
// - Desde referencias: tallas y cantidad; valor por prenda o "Escríbelo".
// - Resumen: descuento resta, la retención NO resta del total (regla actual).
// - Historial: Activas / Cobradas / Archivadas y acciones por documento;
//   archivar pide confirmación en la página (sin diálogos del navegador).
// - client.js solo monta la pantalla nueva con quotes_v2 encendido.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const SRC = readFileSync('app/web/quotes_v2.js', 'utf8');
const CLIENT = readFileSync('app/web/client.js', 'utf8');

function load() {
  const window = {};
  vm.runInNewContext(SRC, { window, document: {}, URLSearchParams, console, setTimeout, clearTimeout });
  return window.CxQuotesV2;
}

const PROD = {
  lines: [{ key: 'pantset', name: 'PANT SET', description: 'PANT SET · S 4 / M 6', quantity: 10, sizes: [{ size: 'S', quantity: 4 }, { size: 'M', quantity: 6 }],
    closure_ids: ['c1', 'c2'], unit_price: 12000, price_source: 'op_order' }],
  already_charged: [{ document: 'CB-2026-0003', quantity: 7 }], already_charged_total: 7,
};

test('paso 1: tres orígenes, aviso de ya cobradas y cliente obligatorio', () => {
  const Q = load();
  Q.model.defaults = { clients: [{ client_name: 'Bombón SAS', client_document: '900123' }], company: { name: 'VELVET' } };
  Q.model.prod = PROD;
  const html = Q.view();
  for (const s of ['Desde producción', 'Desde referencias', 'Manual', 'Origen y cliente', 'Revisar líneas', 'Generar PDF']) assert.ok(html.includes(s), s);
  assert.match(html, /7 prendas ya cobradas en CB-2026-0003/);
  assert.match(html, /<option value="Bombón SAS · 900123">/);
  assert.equal(Q.canNext(), false);
  Q.model.client.name = 'Bombón SAS';
  assert.equal(Q.canNext(), true);
});

test('paso 2 desde producción: líneas ligadas a los cierres y resumen con retención que no resta', () => {
  const Q = load();
  Q.model.prod = PROD;
  Q.model.origin = 'production';
  Q.model.client.name = 'Bombón SAS';
  Q.buildLines();
  assert.equal(Q.model.lines.length, 1);
  assert.deepEqual([...Q.model.lines[0].closure_ids], ['c1', 'c2']);
  Q.model.step = 2;
  Q.model.discount = '10000';
  Q.model.retention = '4';
  const s = Q.summary();
  assert.deepEqual({ ...s }, { subtotal: 120000, discount: 10000, retention: 4800, total: 110000 });
  const html = Q.view();
  assert.match(html, /data-qv-k="quantity" value="10" readonly/);
  assert.match(html, /Orden operacional/);
  assert.match(html, /Retención \(no resta del total\)/);
  const p = Q.payload();
  assert.deepEqual([...p.lines[0].closure_ids], ['c1', 'c2']);
  assert.deepEqual([...p.discounts.map((d) => d.kind)], ['discount', 'retention']);
  assert.equal(p.origin, 'production');
});

test('desde referencias: tallas con cantidad y valor faltante bloquea el paso', () => {
  const Q = load();
  Q.model.origin = 'references';
  Q.model.refs = [{ key: 'aurora', name: 'Aurora', sizes: [{ size: 'S' }, { size: 'M' }], unit_price: null, price_source: 'manual' }];
  Q.model.picks = { aurora: { S: '2', M: '3' } };
  Q.model.client.name = 'X';
  Q.buildLines();
  assert.equal(Q.model.lines[0].description, 'Aurora · S 2 / M 3');
  assert.equal(Q.model.lines[0].quantity, 5);
  Q.model.step = 2;
  assert.equal(Q.canNext(), false, 'sin valor por prenda no sigue');
  assert.match(Q.view(), /Escríbelo/);
  Q.model.lines[0].unit_price = '9000';
  assert.equal(Q.canNext(), true);
});

test('historial: filtros, acciones y confirmación de archivar en la página', () => {
  const Q = load();
  Q.model.hist.data = {
    totals: { active: { count: 1, amount: 50 }, paid: { count: 0, amount: 0 }, archived: { count: 0, amount: 0 } },
    documents: [{ id: 'd1', status: 'converted', document_number: 'CB-2026-0001', document_label: 'Cuenta de cobro', client_name: 'A', total: 50, items: [], charged_closures: 2 },
      { id: 'd2', status: 'issued', document_number: 'CT-2026-0002', document_label: 'Cotización', client_name: 'B', total: 10, items: [] }],
  };
  Q.model.report = { collected: 100, pending: 50 };
  let html = Q.view();
  for (const s of ['Activas', 'Cobradas', 'Archivadas', 'Cobrado este mes', 'Por cobrar', 'Detalle', 'Marcar pagada', 'Convertir a cuenta de cobro', 'Archivar']) assert.ok(html.includes(s), s);
  Q.model.hist.confirm = 'd1';
  html = Q.view();
  assert.match(html, /Sí, archivar/);
  assert.match(html, /Se liberan 2 cierres para cobrarlos de nuevo\./);
  assert.doesNotMatch(SRC, /window\.confirm|\bconfirm\(|alert\(/);
});

test('client.js monta la pantalla nueva solo con quotes_v2 encendido', () => {
  assert.match(CLIENT, /settings\.quotes_v2 === true/);
  assert.match(CLIENT, /if \(cxQuotesV2On056H\(\) && await cxQuotesV2Mount056H\(activeCode\)\) return;/);
});
