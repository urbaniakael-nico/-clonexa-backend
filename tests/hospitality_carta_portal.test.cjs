// Módulo Carta (048T / 049J) en el portal: asistente por pasos, tarjetas con
// foto, combo, QR, insumos y aviso del Dashboard.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');

function portal(data, metrics = {}) {
  const calls = [];
  const dom = { typed: {}, qty: '' };
  const ctx = vm.createContext({
    h: (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
    state: { companyId: 'c1', dashboardMetrics: metrics }, API: '/api/v1', Math, Number, String, Array, Object, JSON, Map, Date,
    URL: { createObjectURL: () => 'blob:foto', revokeObjectURL: () => {} },
    FormData: class { constructor() { this.parts = []; } append(k, v) { this.parts.push([k, v]); } },
    api: async (full, options = {}) => { const path = full.replace('/carta/companies/c1', ''); calls.push({ path, method: options.method || 'GET', body: options.body ? JSON.parse(options.body) : null }); return ctx.respond(path, options); },
    apiForm: async (path, form) => { calls.push({ path, method: 'POST', form: form.parts }); return ctx.respond(path, {}); },
    document: {
      getElementById: () => null,
      // los campos que el paso actual pinta, con lo que "escribió" la persona
      querySelectorAll: (sel) => (sel === '[data-wz-field]'
        ? [...ctx.cxCarWizHtml049J().matchAll(/data-wz-field="(\w+)"/g)].filter((m) => m[1] in dom.typed)
          .map((m) => ({ getAttribute: () => m[1], value: dom.typed[m[1]] }))
        : []),
      querySelector: (sel) => (sel === '[data-wz-qty]' && ctx.cxCarWiz049J?.pick ? { value: dom.qty } : null),
    },
  });
  const a = source.indexOf('  /* CX_CARTA_048T_START */');
  const b = source.indexOf('  /* CX_CARTA_048T_END */');
  vm.runInContext(source.slice(a, b), ctx);
  ctx.cxCar048T.data = data;
  ctx.respond = () => data;
  // clic "de verdad": el botón tiene que estar pintado en la pantalla actual
  ctx.click = async (attr, value) => {
    const html = ctx.cxCarWiz049J ? ctx.cxCarWizHtml049J() : ctx.cxCarPlatosHtml049J();
    const needle = value === undefined ? attr : `${attr}="${value}"`;
    assert.ok(html.includes(needle), `no hay botón ${needle} en pantalla`);
    const target = { closest: (sel) => (sel === `[${attr}]` ? { getAttribute: () => value ?? '', textContent: '' } : null) };
    return ctx.cxCarHandleClick049J(target);
  };
  ctx.calls = calls;
  ctx.dom = dom;
  return ctx;
}

const DATA = {
  item_types: { venta_directa: 'Venta directa', ingrediente: 'Ingrediente', consumible: 'Consumible' },
  purchase_units: ['unidad', 'libra', 'kilo', 'gramo', 'litro', 'ml'], consumption_units: ['g', 'ml', 'unidad'],
  categories: [
    { label: 'BEBIDAS', hint: 'gaseosas, jugos, energizantes, cerveza', preset: true },
    { label: 'PLATOS A LA CARTA', hint: 'churrasco, carne asada, pechuga a la plancha, costillitas', preset: true },
    { label: 'POLLO', hint: 'frito, broaster, asado', preset: true },
    { label: 'COMIDAS RÁPIDAS', hint: 'hamburguesas, perros calientes, salchipapas', preset: true },
    { label: 'PORCIONES', hint: 'papa francesa, papa salada, ensalada, presa de pollo', preset: true },
  ],
  insumos: [
    { id: 'i1', name: 'Pollo crudo', item_type: 'ingrediente', purchase_unit: 'unidad', consumption_unit: 'g', units_per_purchase: 1600, stock: -350, avg_cost: 12.5 },
    { id: 'i2', name: 'Gas', item_type: 'consumible', purchase_unit: 'unidad', consumption_unit: 'unidad', units_per_purchase: 1, stock: 3, avg_cost: 90000 },
    { id: 'i3', name: 'Pan de hamburguesa', item_type: 'ingrediente', purchase_unit: 'unidad', consumption_unit: 'unidad', units_per_purchase: 1, stock: 40, avg_cost: 800 },
    { id: 'i4', name: 'Carne molida', item_type: 'ingrediente', purchase_unit: 'kilo', consumption_unit: 'g', units_per_purchase: 1000, stock: 5000, avg_cost: 22 },
    { id: 'i5', name: 'Salsa de tomate', item_type: 'ingrediente', purchase_unit: 'unidad', consumption_unit: 'g', units_per_purchase: 1000, stock: 900, avg_cost: 9 },
    { id: 'i6', name: 'Coca-Cola 400 ml', item_type: 'venta_directa', purchase_unit: 'unidad', consumption_unit: 'unidad', units_per_purchase: 1, stock: 24, avg_cost: 2200 },
  ],
  items: [
    { id: 'd1', name: 'POLLO Asado', display_name: 'POLLO Asado 500 gr', presentation: '500 gr', category_key: 'POLLO', kind: 'preparado', price: 40000, cost: 7390, margin: 32610, margin_pct: 81.5,
      below_cost: false, missing_cost: [], no_recipe: false, active: true, available: true, has_image: true, station: 'parrilla',
      recipe: [{ inventory_item_id: 'i1', component_item_id: null, insumo: 'Pollo crudo', unit: 'g', quantity: 400, yield_pct: 80 }] },
    { id: 'd2', name: 'Combo barato', display_name: 'Combo barato', category_key: '', kind: 'combo', price: 3000, cost: 7390, margin: -4390, margin_pct: -146.3,
      below_cost: true, missing_cost: [], no_recipe: false, active: true, available: true, has_image: false,
      recipe: [{ inventory_item_id: null, component_item_id: 'd1', insumo: 'POLLO Asado 500 gr', unit: 'plato', quantity: 1, yield_pct: 100 }] },
  ],
};

test('platos: tarjetas con foto, nombre, precio y margen, agrupadas por categoría; nada de tablas', () => {
  const html = portal(DATA).cxCarPlatosHtml049J();
  assert.doesNotMatch(html, /<table/);
  assert.match(html, /<h3>POLLO <small>1<\/small><\/h3>[\s\S]*data-car-card="d1"[\s\S]*src="\/api\/v1\/companies\/c1\/waiter-ordering\/products\/d1\/image\?v=0"[\s\S]*POLLO Asado 500 gr[\s\S]*\$40\.000[\s\S]*Margen \$32\.610 · 81\.5%/);
  assert.match(html, /data-car-edit="d1">Editar<\/button><button class="client-btn danger" type="button" data-car-del="d1">Eliminar/);
  assert.match(html, /<h3>SIN CATEGORÍA[\s\S]*cx-car-card-049j below" data-car-card="d2"[\s\S]*<em>Combo<\/em>[\s\S]*Precio por debajo del costo/);
  assert.ok(html.indexOf('POLLO <small>') < html.indexOf('SIN CATEGORÍA'), 'en el orden de las categorías');
});

test('asistente: un plato completo con receta y foto en 5 pasos, con resumen de costo y margen', async () => {
  const ctx = portal(DATA);
  const created = { id: 'n1', name: 'Hamburguesa', display_name: 'Hamburguesa 125 gr', category_key: 'COMIDAS RÁPIDAS', kind: 'preparado', price: 18000,
    cost: 3657, margin: 14343, margin_pct: 79.7, below_cost: false, missing_cost: [], no_recipe: false, active: true, available: true, has_image: true,
    recipe: [{ inventory_item_id: 'i3', insumo: 'Pan de hamburguesa', unit: 'unidad', quantity: 1 }, { inventory_item_id: 'i4', insumo: 'Carne molida', unit: 'g', quantity: 125 }] };
  ctx.respond = (path) => ({ ...DATA, items: [...DATA.items, created], ...(path === '/items' ? { created_id: 'n1' } : {}) });
  let screens = 1;
  await ctx.click('data-car-new');
  // Paso 1: categorías con botones grandes ya creados + agregar
  let html = ctx.cxCarWizHtml049J();
  for (const label of ['BEBIDAS', 'PLATOS A LA CARTA', 'POLLO', 'COMIDAS RÁPIDAS', 'PORCIONES']) assert.match(html, new RegExp(`data-wz-cat="${label}"`));
  assert.match(html, /gaseosas, jugos, energizantes, cerveza/);
  assert.match(html, /data-wz-cat-add><b>\+ Agregar categoría/);
  await ctx.click('data-wz-cat', 'COMIDAS RÁPIDAS'); screens += 1;
  // Paso 2: nombre y presentación
  assert.equal(ctx.cxCarWiz049J.step, 2);
  ctx.dom.typed = { name: 'Hamburguesa', presentation: '' };
  await ctx.click('data-wz-pres', '125 gr');
  ctx.dom.typed = { name: 'Hamburguesa' };
  await ctx.click('data-wz-next'); screens += 1;
  // Paso 3: precio (sin precio no avanza)
  ctx.dom.typed = { price: '' };
  await ctx.click('data-wz-next');
  assert.equal(ctx.cxCarWiz049J.step, 3);
  assert.match(ctx.cxCarWizHtml049J(), /Escribe el precio de venta/);
  ctx.dom.typed = { price: '18000' };
  await ctx.click('data-wz-next'); screens += 1;
  // Paso 4: ingredientes con el buscador y el botón +
  await ctx.click('data-wz-mode', 'receta');
  ctx.cxCarWiz049J.search = 'PAN hambur';
  html = ctx.cxCarWizHtml049J();
  assert.match(html, /data-wz-pick="insumo:i3">Pan de hamburguesa/);
  assert.doesNotMatch(html, /Carne molida|data-wz-pick="insumo:i2"/, 'filtra y nunca ofrece consumibles');
  await ctx.click('data-wz-pick', 'insumo:i3');
  ctx.dom.qty = '1';
  await ctx.click('data-wz-add');
  ctx.cxCarWiz049J.search = 'carne';
  await ctx.click('data-wz-pick', 'insumo:i4');
  ctx.dom.qty = '';
  await ctx.click('data-wz-add');
  assert.match(ctx.cxCarWizHtml049J(), /Escribe la cantidad de Carne molida/);
  ctx.dom.qty = '125';
  await ctx.click('data-wz-add');
  ctx.cxCarWiz049J.search = 'salsa';
  await ctx.click('data-wz-pick', 'insumo:i5');
  ctx.dom.qty = '2';
  await ctx.click('data-wz-add');
  await ctx.click('data-wz-del', '2'); // se puede quitar
  html = ctx.cxCarWizHtml049J();
  assert.match(html, /Pan de hamburguesa<\/span><b>1 unidad[\s\S]*Carne molida<\/span><b>125 g/);
  assert.doesNotMatch(html, /Salsa de tomate<\/span>/);
  await ctx.click('data-wz-next'); screens += 1;
  // Paso 5: foto (ajustada al marco 4:3) y opciones
  ctx.cxCarOnChange049J({ target: { closest: () => ({ files: [{ name: 'foto.jpg' }] }) } });
  html = ctx.cxCarWizHtml049J();
  assert.match(html, /<span class="frame"><img src="blob:foto"/);
  assert.match(html, /Se vende por porciones \(1\/4, 1\/2, 3\/4, entero\)[\s\S]*Pide término de cocción[\s\S]*Visible en la carta/);
  await ctx.click('data-wz-toggle', 'requires_term');
  await ctx.click('data-wz-save');
  assert.ok(screens < 6, `se crea en ${screens} pasos`);

  const [create, recipe, photo] = ctx.calls;
  assert.equal(create.path, '/items');
  assert.deepEqual({ ...create.body }, { name: 'Hamburguesa', presentation: '125 gr', price: 18000, category_key: 'COMIDAS RÁPIDAS', station: '', kind: 'preparado',
    inventory_item_id: null, direct_qty: 1, requires_term: true, allows_portions: false, active: true });
  assert.equal(recipe.path, '/items/n1/recipe');
  assert.deepEqual(JSON.parse(JSON.stringify(recipe.body.lines)), [{ inventory_item_id: 'i3', quantity: 1, yield_pct: 100 }, { inventory_item_id: 'i4', quantity: 125, yield_pct: 100 }]);
  assert.equal(photo.path, '/carta/companies/c1/items/n1/photo');
  assert.equal(photo.form[0][0], 'image');
  assert.equal(ctx.cxCarWiz049J, null);
  const summary = ctx.cxCarPlatosHtml049J();
  assert.match(summary, /Plato guardado[\s\S]*Hamburguesa 125 gr[\s\S]*<dt>Precio<\/dt><dd>\$18\.000[\s\S]*<dt>Costo<\/dt><dd>\$3\.657[\s\S]*Margen \$14\.343 · 79\.7%/);
});

test('asistente: un producto sin receta se salta los ingredientes; un directo descuenta su producto', async () => {
  const ctx = portal(DATA);
  ctx.respond = (path) => ({ ...DATA, ...(path === '/items' ? { created_id: 'n2' } : {}) });
  await ctx.click('data-car-new');
  await ctx.click('data-wz-cat', 'BEBIDAS');
  ctx.dom.typed = { name: 'Coca-Cola', presentation: '400 ml' };
  await ctx.click('data-wz-next');
  ctx.dom.typed = { price: '4000' };
  await ctx.click('data-wz-next');
  await ctx.click('data-wz-next');
  assert.match(ctx.cxCarWizHtml049J(), /Elige cómo se arma el plato/);
  await ctx.click('data-wz-mode', 'directo');
  ctx.cxCarWiz049J.search = 'coca';
  await ctx.click('data-wz-pick', 'insumo:i6');
  assert.equal(ctx.cxCarWiz049J.pick.quantity, 1, 'por unidad arranca en 1');
  ctx.dom.qty = '1';
  await ctx.click('data-wz-add');
  await ctx.click('data-wz-next');
  await ctx.click('data-wz-save');
  assert.equal(ctx.calls.length, 1, 'un directo no manda receta');
  assert.equal(ctx.calls[0].body.kind, 'directo');
  assert.equal(ctx.calls[0].body.inventory_item_id, 'i6');

  const skip = portal(DATA);
  skip.respond = (path) => ({ ...DATA, ...(path === '/items' ? { created_id: 'n3' } : {}) });
  await skip.click('data-car-new');
  await skip.click('data-wz-cat', 'PORCIONES');
  skip.dom.typed = { name: 'Papa salada' };
  await skip.click('data-wz-next');
  skip.dom.typed = { price: '5000' };
  await skip.click('data-wz-next');
  await skip.click('data-wz-mode', 'sin');
  await skip.click('data-wz-next');
  await skip.click('data-wz-save');
  assert.equal(skip.calls[0].body.kind, 'preparado');
  assert.deepEqual(JSON.parse(JSON.stringify(skip.calls[1].body)), { lines: [] });
});

test('combo: se arma con platos de la carta o insumos y manda sus partes, no una existencia', async () => {
  const ctx = portal(DATA);
  ctx.respond = (path) => ({ ...DATA, ...(path === '/items' ? { created_id: 'n4' } : {}) });
  await ctx.click('data-car-new');
  await ctx.click('data-wz-cat', 'POLLO');
  ctx.dom.typed = { name: 'Combo Socio' };
  await ctx.click('data-wz-next');
  ctx.dom.typed = { price: '45000' };
  await ctx.click('data-wz-next');
  await ctx.click('data-wz-mode', 'combo');
  const html = ctx.cxCarWizHtml049J();
  assert.match(html, /data-wz-pick="plato:d1">🍽 POLLO Asado 500 gr/);
  assert.doesNotMatch(html, /data-wz-pick="plato:d2"/, 'un combo no lleva otro combo');
  await ctx.click('data-wz-pick', 'plato:d1');
  ctx.dom.qty = '1';
  await ctx.click('data-wz-add');
  ctx.cxCarWiz049J.search = 'coca';
  await ctx.click('data-wz-pick', 'insumo:i6');
  ctx.dom.qty = '2';
  await ctx.click('data-wz-add');
  await ctx.click('data-wz-next');
  await ctx.click('data-wz-save');
  assert.equal(ctx.calls[0].body.kind, 'combo');
  assert.equal(ctx.calls[0].body.inventory_item_id, null);
  assert.deepEqual(JSON.parse(JSON.stringify(ctx.calls[1].body.lines)), [{ component_item_id: 'd1', quantity: 1 }, { inventory_item_id: 'i6', quantity: 2, yield_pct: 100 }]);
});

test('editar abre el asistente con lo que ya tiene; eliminar pide confirmación', async () => {
  const ctx = portal(DATA);
  await ctx.click('data-car-edit', 'd1');
  const wiz = ctx.cxCarWiz049J;
  assert.equal(wiz.id, 'd1');
  assert.equal(wiz.mode, 'receta');
  assert.equal(wiz.category, 'POLLO');
  assert.equal(wiz.presentation, '500 gr');
  assert.equal(wiz.lines[0].yield_pct, 80, 'conserva el rendimiento de la receta');
  await ctx.click('data-wz-cancel');
  await ctx.click('data-car-del', 'd1');
  assert.match(ctx.cxCarPlatosHtml049J(), /¿Eliminar este plato\?[\s\S]*data-car-del-yes="d1">Sí, eliminar/);
  assert.equal(ctx.calls.length, 0, 'todavía no borra');
  await ctx.click('data-car-del-yes', 'd1');
  assert.deepEqual({ path: ctx.calls[0].path, method: ctx.calls[0].method }, { path: '/items/d1', method: 'DELETE' });
});

test('QR de la carta: pestaña propia, imagen para descargar, link y cambio de código', () => {
  const ctx = portal(DATA);
  assert.match(source, /\["qr", "QR de la carta"\]/);
  assert.match(ctx.cxCarQrHtml049J(), /Generando el QR/);
  ctx.cxCarUi049J.qr = { url: 'https://x.test/carta-qr?t=abc', image: 'blob:qr' };
  const html = ctx.cxCarQrHtml049J();
  assert.match(html, /<img src="blob:qr" alt="QR de la carta">/);
  assert.match(html, /data-car-qr-download >Descargar imagen/);
  assert.match(html, /href="https:\/\/x\.test\/carta-qr\?t=abc" target="_blank"/);
  assert.match(html, /data-car-qr-regen>Cambiar código/);
  assert.match(source, /fetch\(`\$\{API\}\/carta\/companies\/\$\{encodeURIComponent\(state\.companyId\)\}\/qr\.png`, \{ headers: authHeaders\(\{\}\) \}\)/, 'la imagen se pide con sesión');
});

test('carta del QR: misma vista del kit y solo el código del QR como credencial', () => {
  const page = readFileSync('app/web/carta_qr.js', 'utf8');
  assert.match(page, /fetch\(`\/api\/v1\/carta\/public\/\$\{encodeURIComponent\(token\)\}`\)/);
  assert.match(page, /Kit\.categoryGridHtml/);
  assert.match(page, /Kit\.productGridHtml/);
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
