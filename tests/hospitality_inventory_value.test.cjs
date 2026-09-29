// 049T: Stock y Reportes con las mismas cifras de inventario (Asadero, módulo
// Carta). Cantidad, precio y total en la misma unidad: 12 kg a $16.000 el kilo
// = $192.000 (no 12.000 g x $16.000 = $192.000.000), y Reportes con el valor,
// el consumo, la cobertura y la rotación que salen del mismo cálculo.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');

function fn(name) {
  const start = source.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 1);
  const end = tail.indexOf('\n  }\n');
  return `${tail.slice(0, end + 4)}\n`;
}

function context() {
  const ctx = vm.createContext({ String, Number, Array, JSON, Math, Intl, Object });
  vm.runInContext(
    'function h(v){return String(v ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}\n'
      + 'function inventoryNumber(v){const n = Number(v); return Number.isFinite(n) ? n : 0;}\n'
      + 'function inventoryQtyLabel(v){return String(v);}\n'
      + 'function inventoryStatusLabel(s){return s === "inactive" ? "Inactivo" : "Activo";}\n'
      + 'function isClientModuleActive(){return true;}\n'
      + 'function cxStockAlertLabel024T(){return "OK";}\n'
      + 'function cxStockAlertClass024T(){return "ok";}\n'
      + 'function cxStockMoney024T(v){return "$" + Math.round(Number(v) || 0).toLocaleString("es-CO");}\n'
      + 'function cxOwnMoney048S(v){return "$" + Math.round(Number(v) || 0).toLocaleString("es-CO");}\n'
      + ['cxStockRow024T', 'cxStockQty049T', 'cxStockCartaRowHtml049T', 'cxStockSummary024T', 'cxOwnInventory048S', 'cxOwnInventory049T'].map(fn).join(''),
    ctx,
  );
  return ctx;
}

// como llega del servidor para el Asadero (inventory.list_inventory_items + enrich_stock_rows)
const CARNE = { id: 'c1', name_reference: 'CARNE Asada', status: 'active', current_stock: 12000, min_stock: 2000, entry_price: 16000, sale_price: 0,
  entry_stock_value: 192000, sale_stock_value: 0, unit: 'kg', unit_label: 'kg', base_label: 'gr', natural_factor: 1000, stock_natural: 12, min_stock_natural: 2 };
const GASEOSA = { id: 'g1', name_reference: 'GASEOSA Colombiana', status: 'active', current_stock: 69, min_stock: 12, entry_price: 4600, sale_price: 5000,
  entry_stock_value: 317400, sale_stock_value: 345000, unit: 'unidad', unit_label: 'unidad', base_label: 'unidad', natural_factor: 1, stock_natural: 69, min_stock_natural: 12 };

const cells = (html) => [...html.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map((m) => m[1].replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim());

test('Stock: 12 kg de carne con saldo de $192.000 muestra $192.000 de total, no millones', () => {
  const ctx = context();
  const c = cells(ctx.cxStockRow024T(CARNE));
  assert.equal(c[1], '12 kg 12.000 gr', 'cantidad en su unidad natural con el equivalente');
  assert.equal(c[2], '2 kg');
  assert.equal(c[3], '$16.000 / kg', 'el precio dice de qué unidad es');
  assert.equal(c[4], '—', 'el precio de venta de un insumo por peso vive en Carta');
  assert.equal(c[5], '$192.000');
  assert.doesNotMatch(ctx.cxStockRow024T(CARNE), /192\.000\.000/);
  const g = cells(ctx.cxStockRow024T(GASEOSA));
  assert.deepEqual([g[1], g[3], g[4], g[5]], ['69 unidad', '$4.600 / unidad', '$5.000', '$317.400']);
});

test('Stock: el resumen "Valor entrada" es la suma de los saldos', () => {
  const ctx = context();
  assert.equal(ctx.cxStockSummary024T([CARNE, GASEOSA]).entryValue, 192000 + 317400);
});

test('Stock sin Carta (The Time Machine y las demás): la fila de siempre', () => {
  const ctx = context();
  const plain = { id: 'x', name_reference: 'Club Colombia', status: 'active', current_stock: 48, min_stock: 6, entry_price: 3000, sale_price: 8000,
    entry_stock_value: 144000, sale_stock_value: 384000 };
  const c = cells(ctx.cxStockRow024T(plain));
  assert.deepEqual([c[1], c[3], c[4], c[5], c[6]], ['48', '$3.000', '$8.000', '$144.000', '$384.000']);
});

test('Reportes con Carta: valor, consumo diario, rotación y cobertura del mismo cálculo', () => {
  const ctx = context();
  const inv = { source: 'movimientos', value: 207000, uncosted_items: 0, daily_consumption_cost: 80000, inventory_days: 2.6, turns_per_month: 11.5, window_days: 28,
    buy_today: [{ name: 'CARNE Asada', stock: '12 kg', daily: '5 kg', days: 2.4 }],
    coverage: [{ name: 'CARNE Asada', stock: '12 kg', daily: '5 kg', days: 2.4 }],
    idle: [{ name: 'PAPA', stock: '5 kg', value: 15000 }], without_history: ['Tocineta'] };
  const html = ctx.cxOwnInventory048S(inv);
  assert.match(html, /Valor del inventario actual<\/span><b>\$207\.000<\/b><small class="neutral">suma de los saldos en dinero/);
  assert.match(html, /Consumo diario<\/span><b>\$80\.000<\/b><small class="neutral">promedio de los últimos 28 días/);
  assert.match(html, /Rotación<\/span><b>2,6 días<\/b><small class="neutral">el inventario se renueva 11,5 veces al mes/);
  assert.match(html, /<b>CARNE Asada<\/b><span>quedan 12 kg · se consumen 5 kg por día · alcanza para 2,4 día\(s\)/);
  assert.match(html, /Sin historial suficiente para proyectar: Tocineta\./);
  assert.match(html, /Sin consumo en los últimos 28 días \(1\)[\s\S]*PAPA · 5 kg en existencia · \$15\.000 quietos/);
  // sin Carta, la sección de siempre
  assert.match(ctx.cxOwnInventory048S({ value: 5000, buy_today: [], coverage: [], idle: [] }), /a precio de entrada/);
});
