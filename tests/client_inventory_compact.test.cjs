// Portal > Inventario: compact table. The name column is wide (and pinned),
// numbers are narrow, the stock entry (qty + invoice + Ingresar) and the row
// actions (Guardar, Deshabilitar) each sit on one line -- with every data-*
// hook the existing handlers use still in place.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/client.js', 'utf8');

function fn(name) {
  const start = source.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

function context() {
  const ctx = vm.createContext({ String, Number, Array, JSON, Math });
  vm.runInContext(
    'function h(v){return String(v ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}\n'
      + 'function getInventoryPendingInvoice(){return null;}\n'
      + 'function inventoryQtyLabel(v){return String(v);}\n'
      + 'function inventoryStatusLabel(s){return s === "inactive" ? "Inactivo" : "Activo";}\n'
      + 'function renderInventoryHistoryPanel(){return "";}\n'
      + 'var window = { __cxInventorySearchQuery: "" };\n'
      + fn('renderInventoryRow') + fn('renderInventoryModifyPanel'),
    ctx,
  );
  return ctx;
}

const ROW = {
  id: 'inv-1', name_reference: 'CARNE Churrasco 300 gramos', size: '300g', color: '', current_stock: 3,
  min_stock: 5, entry_price: 12000, sale_price: 28000, status: 'active', alert_low: true,
};

test('the full product name is in a wide, titled name cell', () => {
  const html = context().renderInventoryRow(ROW, 0);
  assert.match(html, /<td class="cx-inv-col-name"><input data-inventory-field="name_reference" value="CARNE Churrasco 300 gramos" title="CARNE Churrasco 300 gramos">/);
  assert.match(source, /col\.cx-inv-w-name \{ width: auto; \}/);   // takes all the remaining width
  assert.match(source, /\.cx-inv-table \{ table-layout: fixed; min-width: 1130px;/);
  assert.match(source, /th\.cx-inv-col-name, \.cx-inv-table td\.cx-inv-col-name \{\s*position: sticky; left: 0;/);
  assert.doesNotMatch(source, /min-width: 1480px/);
});

test('every existing hook is still there, so all functions keep working', () => {
  const html = context().renderInventoryRow(ROW, 0);
  for (const hook of [
    'data-inventory-field="name_reference"', 'data-inventory-field="size"', 'data-inventory-field="color"',
    'data-inventory-field="min_stock"', 'data-inventory-field="entry_price"', 'data-inventory-field="sale_price"',
    'data-inventory-field="status"', 'data-inventory-entry-qty="inv-1"', 'data-inventory-entry-invoice="inv-1"',
    'data-inventory-update="inv-1"', 'data-inventory-entry="inv-1"', 'data-inventory-disable="inv-1"',
    'data-inventory-search-text=',
  ]) assert.ok(html.includes(hook), hook);
});

test('stock entry and actions are each on one line', () => {
  const html = context().renderInventoryRow(ROW, 0);
  const entry = html.slice(html.indexOf('<div class="cx-inv-entry-line">'), html.indexOf('</div>', html.indexOf('cx-inv-entry-line')));
  assert.match(entry, /data-inventory-entry-qty/);
  assert.match(entry, /cx-inv-invoice-compact/);
  assert.match(entry, />Ingresar</);
  const actions = html.slice(html.indexOf('<div class="cx-inv-actions">'));
  assert.match(actions, />Guardar</);
  assert.match(actions, /<details class="cx-inv-more-045a">[\s\S]*data-inventory-disable="inv-1">Deshabilitar</);   // compact "⋯" menu
  assert.match(source, /\.cx-inv-entry-line, \.cx-inv-table \.cx-inv-actions \{ display: flex; flex-wrap: nowrap;/);
});

test('the invoice picker keeps the text the invoice-state code updates', () => {
  const html = context().renderInventoryRow(ROW, 0);
  assert.match(html, /aria-label="Adjuntar factura">\s*<input data-inventory-entry-invoice="inv-1"[^>]*>\s*<span>Adjuntar factura<\/span>/);
});

test('low stock is still flagged on the stock pill', () => {
  const html = context().renderInventoryRow(ROW, 0);
  assert.match(html, /cx-inv-stock low" title="Stock bajo">3 <span aria-label="Stock bajo">⚠<\/span>/);
});

test('header, colgroup and empty row agree on 10 columns', () => {
  const ctx = context();
  const html = ctx.renderInventoryModifyPanel([], []);
  assert.equal((html.match(/<th[ >]/g) || []).length, 10);
  assert.equal((html.match(/<col /g) || []).length, 10);
  assert.match(html, /colspan="10"/);
  const row = ctx.renderInventoryRow(ROW, 0);
  assert.equal((row.match(/<td[ >]/g) || []).length, 10);
});
