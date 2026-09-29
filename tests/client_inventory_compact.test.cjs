// Portal > Inventario: compact AND complete. Every column is as wide as its
// longest value (never "27!" for "275gr" or "290" for "29.000"), prices show
// thousands separators and are parsed back on save, rows are one input tall,
// "Permite porciones" shows only for restaurants with waiter_ordering, and
// "Eliminar" asks for confirmation.
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

function context({ restaurant = false, carta = false } = {}) {
  const ctx = vm.createContext({ String, Number, Array, JSON, Math, Intl });
  vm.runInContext(
    'function h(v){return String(v ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}\n'
      + 'function getInventoryPendingInvoice(){return null;}\n'
      + 'function inventoryQtyLabel(v){return String(v);}\n'
      + 'function inventoryStatusLabel(s){return s === "inactive" ? "Inactivo" : "Activo";}\n'
      + 'function renderInventoryHistoryPanel(){return "";}\n'
      + `function cxInvCartaOn049Q(){return ${carta};}\n`
      // 049R: con Carta la fila lee el insumo (saldos, última compra y compra en línea)
      + 'function cxInvInsumo049Q(id){return { id, natural_factor: 1000, min_stock_natural: 2 };}\n'
      + 'function cxInvStockText049Q(){return "12 kg (12.000 gr)";}\n'
      + 'function cxInvLastPurchaseHtml049R(){return "<small>Última compra: 3 kg · $42.000 · 28/09/2026</small>";}\n'
      + 'function cxInvBalanceHtml049R(){return "<b>$192.000</b>";}\n'
      + 'function cxInvBuyCellHtml049R(i){return `<div data-inv-buy-row="${i.id}"></div>`;}\n'
      + 'var CX_CAR_RECIPE_UNITS_049N = [["g", "gr"], ["kg", "kg"]];\n'
      + `function isClientModuleActive(code){return ${restaurant} && code === "waiter_ordering";}\n`
      + 'var window = { __cxInventorySearchQuery: "" };\n'
      + ['inventoryMoneyLabel045B', 'inventoryMoneyValue045B', 'inventoryShowsPortions045B', 'inventoryTextWidth045B',
        'inventoryColumnPlan045B', 'renderInventoryRow', 'renderInventoryModifyPanel', 'inventoryDeleteMessage045B',
        'cxInvSizeHtml049M', 'cxInvReadSize049M', 'cxInvSizeProblem049M'].map(fn).join('')
      + source.match(/\r?\n  const CX_INV_UNITS_049M = \[[\s\S]*?\];\r?\n/)[0].replace('const', 'var'),
    ctx,
  );
  return ctx;
}

const ROW = {
  id: 'inv-1', name_reference: 'CARNE Churrasco', size: '275gr', color: '', current_stock: 3,
  min_stock: 5, entry_price: 12000, sale_price: 29000, status: 'inactive', alert_low: true, allows_portions: false,
};

test('prices show thousands separators and are parsed back exactly', () => {
  const ctx = context();
  const html = ctx.renderInventoryRow(ROW, 0);
  assert.match(html, /data-inventory-field="sale_price" data-inventory-money type="text" inputmode="decimal" value="29\.000"/);
  assert.match(html, /data-inventory-field="entry_price"[^>]*value="12\.000"/);
  assert.equal(ctx.inventoryMoneyLabel045B(1250000), '1.250.000');
  for (const [input, value] of [['29.000', 29000], ['29000', 29000], ['1.250.000', 1250000], ['1.234,5', 1234.5], ['$ 4.500', 4500], ['12.5', 12.5], ['', 0], ['abc', 0]]) {
    assert.equal(ctx.inventoryMoneyValue045B(input), value, input);
  }
});

test('saving reads prices with the separator-aware parser', () => {
  const payload = fn('inventoryRowPayload');
  assert.match(payload, /entry_price: inventoryMoneyValue045B\(/);
  assert.match(payload, /sale_price: inventoryMoneyValue045B\(/);
});

test('every column is at least as wide as its longest value', () => {
  const ctx = context();
  const rows = [ROW, { ...ROW, id: 'inv-2', name_reference: 'HAMBURGUESA DOBLE CON QUESO Y TOCINETA', size: '500 ml', sale_price: 1250000 }];
  const plan = Object.fromEntries(ctx.inventoryColumnPlan045B(rows, false).map((c) => [c.key, c.px]));
  const chrome = 34;   // cell + input padding and borders
  assert.ok(plan.name - chrome >= ctx.inventoryTextWidth045B('HAMBURGUESA DOBLE CON QUESO Y TOCINETA', 14));
  assert.ok(plan.size - chrome >= ctx.inventoryTextWidth045B('500 ml', 13));
  assert.ok(plan.sale_price - chrome >= ctx.inventoryTextWidth045B('1.250.000', 13));
  assert.ok(plan.status - 50 >= ctx.inventoryTextWidth045B('Inactivo', 13));
  // generous estimate: a bold "M" is ~0.9em, never estimated narrower
  assert.ok(ctx.inventoryTextWidth045B('MMMM', 10) >= 36);
});

test('the table is as wide as all columns together, and the name takes the rest', () => {
  const ctx = context();
  const html = ctx.renderInventoryModifyPanel([ROW], []);
  const plan = ctx.inventoryColumnPlan045B([ROW], false);
  const total = plan.reduce((sum, c) => sum + c.px, 0);
  assert.match(html, new RegExp(`<table class="cx-inv-table" style="min-width:${total}px">`));
  assert.match(html, /<col class="cx-inv-w-name">/);            // no fixed width: gets the leftover
  assert.match(html, /<col class="cx-inv-w-size" style="width:\d+px">/);
  assert.doesNotMatch(source, /text-overflow: ellipsis; \}/);
});

test('header, colgroup, row cells and empty row agree (with and without Porciones)', () => {
  for (const restaurant of [false, true]) {
    const ctx = context({ restaurant });
    const cols = restaurant ? 11 : 10;
    const html = ctx.renderInventoryModifyPanel([], []);
    assert.equal((html.match(/<th[ >]/g) || []).length, cols);
    assert.equal((html.match(/<col /g) || []).length, cols);
    assert.match(html, new RegExp(`colspan="${cols}"`));
    assert.equal((ctx.renderInventoryRow(ROW, 0).match(/<td[ >]/g) || []).length, cols);
  }
});

test('"Permite porciones" only shows for companies with waiter_ordering, reflecting the product', () => {
  assert.doesNotMatch(context().renderInventoryRow(ROW, 0), /allows_portions/);
  const html = context({ restaurant: true }).renderInventoryRow({ ...ROW, allows_portions: true }, 0);
  assert.match(html, /<input type="checkbox" data-inventory-field="allows_portions" checked>/);
  assert.match(fn('inventoryRowPayload'), /allows_portions: !!row\.querySelector/);
});

test('every existing hook is still there, plus Eliminar in the compact menu', () => {
  const html = context().renderInventoryRow(ROW, 0);
  for (const hook of [
    'data-inventory-field="name_reference"', 'data-inv-size-value', 'data-inventory-field="color"',
    'data-inventory-field="min_stock"', 'data-inventory-field="entry_price"', 'data-inventory-field="sale_price"',
    'data-inventory-field="status"', 'data-inventory-entry-qty="inv-1"', 'data-inventory-entry-invoice="inv-1"',
    'data-inventory-update="inv-1"', 'data-inventory-entry="inv-1"', 'data-inventory-disable="inv-1"',
    'data-inventory-search-text=',
  ]) assert.ok(html.includes(hook), hook);
  assert.match(html, /<details class="cx-inv-more-045a">[\s\S]*data-inventory-disable="inv-1">Deshabilitar<[\s\S]*data-inventory-delete="inv-1" data-inventory-delete-name="CARNE Churrasco">Eliminar</);
});

test('Eliminar asks exactly the confirmation the owner asked for', () => {
  const body = fn('deleteInventoryItem045B');
  assert.match(body, /window\.confirm\(`¿Eliminar \$\{name\}\? Esta acción no se puede deshacer\.`\)/);
  assert.match(body, /method: "DELETE"/);
  assert.match(body, /\/inventory\/companies\/\$\{encodeURIComponent\(companyId\)\}\/items\/\$\{encodeURIComponent\(itemId\)\}/);
});

test('the result message tells which path was applied', () => {
  const ctx = context();
  assert.equal(ctx.inventoryDeleteMessage045B({ mode: 'deleted' }, 'GASEOSA Coca'), 'GASEOSA Coca eliminado.');
  assert.equal(
    ctx.inventoryDeleteMessage045B({ mode: 'hidden', history: ['movimientos de inventario'] }, 'CARNE Churrasco'),
    'CARNE Churrasco eliminado de las listas. Se conserva en la base porque tiene movimientos de inventario.',
  );
});

test('low stock is still flagged on the stock pill', () => {
  assert.match(context().renderInventoryRow(ROW, 0), /cx-inv-stock low" title="Stock bajo">3 <span aria-label="Stock bajo">⚠<\/span>/);
});


test('tamaño: número + unidad (se despliega al escribir), y lo que no se entendió queda marcado', () => {
  const ctx = context();
  const done = ctx.renderInventoryRow({ ...ROW, size: '275 gr', size_value: 275, size_unit: 'gr' }, 0);
  assert.match(done, /data-inv-size-value value="275"/);
  assert.match(done, /<select data-inv-size-unit ><option value="">Unidad<\/option><optgroup label="Peso"><option value="gr" selected>gr<\/option><option value="lb" >lb<\/option><option value="kg" >kg<\/option><\/optgroup><optgroup label="Volumen"><option value="ml" >ml<\/option><option value="litros" >litros<\/option><\/optgroup><optgroup label="Unidad"><option value="unidad" >unidad<\/option><option value="paquete" >paquete<\/option><option value="caja" >caja<\/option><option value="docena" >docena<\/option>/);
  const empty = ctx.cxInvSizeHtml049M({});
  assert.match(empty, /<select data-inv-size-unit hidden>/, 'la unidad aparece al escribir el número');
  const review = ctx.renderInventoryRow({ ...ROW, size: 'M', size_review: true }, 0);
  assert.match(review, /data-inv-size-legacy="M"[\s\S]*Revisar: "M"/);
  const scope = (value, unit, legacy) => ({ querySelector: () => ({
    getAttribute: () => legacy || null,
    querySelector: (sel) => (sel === '[data-inv-size-value]' ? { value } : { value: unit }),
  }) });
  assert.deepEqual({ ...ctx.cxInvReadSize049M(scope('1.5', 'litros')) }, { size_value: '1.5', size_unit: 'litros' });
  assert.deepEqual({ ...ctx.cxInvReadSize049M(scope('', '', 'M')) }, {}, 'sin tocar: el valor anterior no se pierde');
  assert.deepEqual({ ...ctx.cxInvReadSize049M(scope('', '')) }, { size: '' });
  assert.match(ctx.cxInvSizeProblem049M({ size_value: '275', size_unit: '' }), /Elige la unidad/);
});

test('botón Gastos fijos junto a Crear, Modificar y CSV', () => {
  assert.match(source, /data-inventory-mode="modify">Modificar material<\/button>\s*(?:\$\{carta049Q \? `<button[^`]*data-inventory-mode="insumos">Insumos y compras<\/button>` : ""\}\s*)?<button type="button" data-inventory-export>CSV \+ archivar<\/button>\s*<button class="\$\{mode === "fixed" \? "active" : ""\}" type="button" data-inventory-mode="fixed">Gastos fijos<\/button>/);
  assert.match(source, /window\.__cxInventoryMode = \["create", "modify", "fixed", "compras"\]\.includes\(mode\)/);
  // 049T: "Próximas compras" solo con Carta
  assert.match(source, /\$\{carta049Q \? `<button class="\$\{mode === "compras" \? "active" : ""\}" type="button" data-inventory-mode="compras">Próximas compras<\/button>` : ""\}/);
});

test('049S: con Carta, Modificar material usa su propia tabla; sin Carta nada cambia', () => {
  const ctx = context({ restaurant: true, carta: true });
  vm.runInContext('function cxInvCartaRowHtml049S(row){return "<tr carta=" + row.id + ">";}\nfunction cxInvCartaPanelHtml049S(){return "<section carta>";}', ctx);
  assert.equal(ctx.renderInventoryRow({ ...ROW }, 0), '<tr carta=inv-1>');
  assert.equal(ctx.renderInventoryModifyPanel([], []), '<section carta>');
  // sin Carta la tabla de siempre, con todas sus columnas
  assert.match(context({ restaurant: true }).renderInventoryRow(ROW, 0), /data-inventory-field="color"[\s\S]*data-inventory-field="sale_price"[\s\S]*allows_portions/);
});
