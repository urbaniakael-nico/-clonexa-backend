// Módulo Carta (048T) en el portal: platos, receta, insumos y aviso del Dashboard.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');

function portal(data, metrics = {}) {
  const ctx = vm.createContext({
    h: (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
    state: { companyId: 'c1', dashboardMetrics: metrics }, Math, Number, String, Array, Object, JSON, Map,
  });
  const a = source.indexOf('  /* CX_CARTA_048T_START */');
  const b = source.indexOf('  /* CX_CARTA_048T_END */');
  vm.runInContext(source.slice(a, b), ctx);
  ctx.cxCar048T.data = data;
  return ctx;
}

const DATA = {
  item_types: { venta_directa: 'Venta directa', ingrediente: 'Ingrediente', consumible: 'Consumible' },
  purchase_units: ['unidad', 'libra', 'kilo', 'gramo', 'litro', 'ml'], consumption_units: ['g', 'ml', 'unidad'],
  insumos: [
    { id: 'i1', name: 'Pollo crudo', item_type: 'ingrediente', purchase_unit: 'unidad', consumption_unit: 'g', units_per_purchase: 1600, stock: -350, avg_cost: 12.5 },
    { id: 'i2', name: 'Gas', item_type: 'consumible', purchase_unit: 'unidad', consumption_unit: 'unidad', units_per_purchase: 1, stock: 3, avg_cost: 90000 },
  ],
  items: [
    { id: 'd1', name: 'POLLO Asado', kind: 'preparado', price: 40000, cost: 7390, margin: 32610, margin_pct: 81.5, below_cost: false, missing_cost: [], no_recipe: false, active: true, available: true,
      recipe: [{ inventory_item_id: 'i1', insumo: 'Pollo crudo', unit: 'g', quantity: 400, yield_pct: 80 }] },
    { id: 'd2', name: 'Combo barato', kind: 'preparado', price: 3000, cost: 7390, margin: -4390, margin_pct: -146.3, below_cost: true, missing_cost: [], no_recipe: false, active: true, available: true, recipe: [] },
  ],
};

test('platos: costo, margen y aviso cuando el precio queda por debajo del costo', () => {
  const html = portal(DATA).cxCarDishesHtml048T();
  assert.match(html, /<b class="bad">1 con precio por debajo del costo<\/b>/);
  assert.match(html, /data-car-dish="d1"[\s\S]*Con receta[\s\S]*\$40\.000[\s\S]*\$7\.390[\s\S]*\$32\.610 <small>81\.5%<\/small>/);
  assert.match(html, /<tr class="below" data-car-dish="d2">[\s\S]*El precio de venta quedó por debajo del costo/);
  assert.match(html, /data-car-recipe="d1">Receta/);
});

test('receta: cantidad en el plato, rendimiento y nunca un consumible en la lista', () => {
  const ctx = portal(DATA);
  ctx.cxCar048T.draftLines = DATA.items[0].recipe;
  const html = ctx.cxCarRecipeHtml048T(DATA.items[0]);
  assert.match(html, /el sistema descuenta cantidad ÷ rendimiento/);
  assert.match(html, /<option value="i1" selected>Pollo crudo \(g\)<\/option>/);
  assert.doesNotMatch(html, /Gas/, 'los consumibles no se ofrecen para recetas');
  assert.match(html, /name="yield_pct"[^>]*value="80"/);
});

test('insumos: tipo, unidades, conversión, existencia negativa marcada y costo por unidad de consumo', () => {
  const html = portal(DATA).cxCarInsumosHtml048T();
  assert.match(html, /<option value="consumible" selected>Consumible<\/option>/);
  assert.match(html, /name="units_per_purchase" type="number"[^>]*value="1600"/);
  assert.match(html, /-350 g <small class="bad">negativo: revisar<\/small>/);
  assert.match(html, /\$12,50<small> por g<\/small>/, 'costo por gramo con centavos');
  assert.match(html, /nunca aparecen en la carta/);
});

test('Dashboard: aviso de insumos en negativo y platos bajo costo; sin módulo, nada', () => {
  const banner = portal(DATA, { carta048T: { negative_stock: [{ name: 'Pollo crudo', stock: -350, unit: 'g' }], below_cost: [{ name: 'Combo barato' }], no_recipe: [] } }).cxCarDashboardBanner048T();
  assert.match(banner, /data-client-module="carta"[\s\S]*1 insumo\(s\) en negativo: Pollo crudo \(-350 g\)[\s\S]*1 plato\(s\) con precio por debajo del costo: Combo barato/);
  assert.equal(portal(DATA, {}).cxCarDashboardBanner048T(), '');
  assert.equal(portal(DATA, { carta048T: { negative_stock: [], below_cost: [] } }).cxCarDashboardBanner048T(), '');
  assert.match(source, /if \(codes\.has\("carta"\)\) \{\s*metrics\.carta048T = await api/);
  assert.match(source, /if \(code === "carta"\) \{\s*await renderCartaModule048T\(\);/);
  assert.match(source, /if \(!isClientModuleActive\("carta"\)\) \{\s*render\(\);\s*return;/);
});

test('Reportes: dice de dónde sale el margen (real de receta o estimado)', () => {
  assert.match(source, /data-own-real-cost>Margen con el costo real de las recetas/);
});
