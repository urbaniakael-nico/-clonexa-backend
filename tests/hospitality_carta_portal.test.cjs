// Módulo Carta (048T / 049J / 049K) en el portal: asistente por pasos con
// categoría y subcategoría, selector de insumos con casillas, tarjetas sin
// foto, mover varios platos, categorías con imagen completa, QR, insumos y
// aviso del Dashboard.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');

function portal(data, metrics = {}) {
  const calls = [];
  const dom = { typed: {}, values: {}, boxes: {} };
  const ctx = vm.createContext({
    h: (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
    state: { companyId: 'c1', dashboardMetrics: metrics }, API: '/api/v1', Math, Number, String, Array, Object, JSON, Map, Set, Date,
    URL: { createObjectURL: () => 'blob:x', revokeObjectURL: () => {} },
    FormData: class { constructor() { this.parts = []; } append(k, v) { this.parts.push([k, v]); } },
    api: async (full, options = {}) => {
      const path = full.replace('/carta/companies/c1', '');
      calls.push({ path, method: options.method || 'GET', body: options.body ? JSON.parse(options.body) : null });
      return ctx.respond(path, options);
    },
    apiForm: async (path, form) => { calls.push({ path, method: 'POST', form: form.parts }); return ctx.respond(path, {}); },
    document: {
      getElementById: () => null,
      // los campos que el paso actual pinta, con lo que "escribió" la persona
      querySelectorAll: (sel) => (sel === '[data-wz-field]' && ctx.cxCarWiz049J
        ? [...ctx.cxCarWizHtml049J().matchAll(/data-wz-field="(\w+)"/g)].filter((m) => m[1] in dom.typed)
          .map((m) => ({ getAttribute: () => m[1], value: dom.typed[m[1]] }))
        : []),
      querySelector: (sel) => {
        if (sel in dom.values) return { value: dom.values[sel] };
        if (sel === '[data-wz-results]' || sel === '[data-wz-lines]') return (dom.boxes[sel] = dom.boxes[sel] || { innerHTML: '' });
        return null;
      },
    },
  });
  const a = source.indexOf('  /* CX_CARTA_048T_START */');
  const b = source.indexOf('  /* CX_CARTA_048T_END */');
  vm.runInContext(source.slice(a, b), ctx);
  ctx.cxCar048T.data = data;
  ctx.respond = () => data;
  ctx.screen = () => (ctx.cxCar048T.tab === 'categorias' ? ctx.cxCarCategoriesHtml049K() : ctx.cxCarPlatosHtml049J());
  // clic "de verdad": el botón tiene que estar pintado en la pantalla actual
  ctx.click = async (attr, value, extra = {}) => {
    const needle = value === undefined ? attr : `${attr}="${value}"`;
    assert.ok(ctx.screen().includes(needle), `no hay botón ${needle} en pantalla`);
    const target = { closest: (sel) => (sel === `[${attr}]` ? { getAttribute: () => value ?? '', ...extra } : extra[sel] || null) };
    return ctx.cxCarHandleClick049J(target);
  };
  // casilla del selector / de mover platos
  ctx.check = (attr, value, checked = true) => {
    assert.ok(ctx.screen().includes(`${attr}="${value}"`), `no hay casilla ${value}`);
    return ctx.cxCarOnChange049J({ target: { closest: (sel) => (sel === `[${attr}]` ? { getAttribute: () => value, checked } : null) } });
  };
  ctx.qty = (index, value) => ctx.cxCarOnInput049J({ target: { closest: (sel) => (sel === '[data-wz-line-qty]' ? { getAttribute: () => String(index), value } : null) } });
  ctx.search = (value) => ctx.cxCarOnInput049J({ target: { closest: (sel) => (sel === '[data-wz-search]' ? { value } : null) } });
  ctx.calls = calls;
  ctx.dom = dom;
  return ctx;
}

const PLATOS = 'cat-platos';
const CARNES = 'sub-carnes';
const DATA = {
  item_types: { venta_directa: 'Venta directa', ingrediente: 'Ingrediente', consumible: 'Consumible' },
  purchase_units: ['unidad', 'libra', 'kilo', 'gramo', 'litro', 'ml'], consumption_units: ['g', 'ml', 'unidad'],
  stations: ['parrilla', 'bebidas'],
  categories: [
    { id: 'cat-bebidas', label: 'BEBIDAS', hint: 'gaseosas, jugos, energizantes, cerveza', station: 'bebidas', quick_notes: [], requires_term: false, has_image: true, image_version: '5', dish_count: 0, children: [] },
    { id: PLATOS, label: 'PLATOS A LA CARTA', hint: 'churrasco, carne asada, pechuga a la plancha, costillitas', station: 'parrilla', quick_notes: ['sin sal'], requires_term: true, has_image: false, dish_count: 0,
      children: [{ id: CARNES, parent_id: PLATOS, label: 'CARNES', station: '', quick_notes: [], requires_term: false, has_image: true, image_version: '9', dish_count: 1 }] },
    { id: 'cat-pollo', label: 'POLLO', hint: 'frito, broaster, asado', station: 'parrilla', quick_notes: [], requires_term: false, has_image: false, dish_count: 1, children: [] },
    { id: 'cat-rapidas', label: 'COMIDAS RÁPIDAS', hint: 'hamburguesas, perros calientes, salchipapas', station: '', quick_notes: [], requires_term: false, has_image: false, dish_count: 0, children: [] },
    { id: 'cat-porciones', label: 'PORCIONES', hint: 'papa francesa, papa salada, ensalada, presa de pollo', station: '', quick_notes: [], requires_term: false, has_image: false, dish_count: 0, children: [] },
  ],
  insumos: [
    { id: 'i1', name: 'Pollo crudo', item_type: 'ingrediente', consumption_unit: 'g', units_per_purchase: 1600, stock: -350, avg_cost: 12.5, sale_price: 0, purchase_unit: 'unidad' },
    { id: 'i2', name: 'Gas', item_type: 'consumible', consumption_unit: 'unidad', units_per_purchase: 1, stock: 3, avg_cost: 90000, sale_price: 0, purchase_unit: 'unidad' },
    { id: 'i3', name: 'Pan de hamburguesa', item_type: 'ingrediente', consumption_unit: 'unidad', units_per_purchase: 1, stock: 40, avg_cost: 800, sale_price: 0, purchase_unit: 'unidad' },
    { id: 'i4', name: 'Carne molida', item_type: 'ingrediente', consumption_unit: 'g', units_per_purchase: 1000, stock: 5000, avg_cost: 22, sale_price: 0, purchase_unit: 'kilo' },
    { id: 'i5', name: 'Salsa de tomate', item_type: 'ingrediente', consumption_unit: 'g', units_per_purchase: 1000, stock: 900, avg_cost: 9, sale_price: 0, purchase_unit: 'unidad' },
    { id: 'i6', name: 'Coca-Cola 400 ml', item_type: 'venta_directa', consumption_unit: 'unidad', units_per_purchase: 1, stock: 24, avg_cost: 2200, sale_price: 4000, purchase_unit: 'unidad' },
    ...Array.from({ length: 12 }, (_, n) => ({ id: `x${n}`, name: `Insumo extra ${n}`, item_type: 'ingrediente', consumption_unit: 'g', units_per_purchase: 1, stock: 1, avg_cost: 1, sale_price: 0, purchase_unit: 'unidad' })),
  ],
  items: [
    { id: 'd1', name: 'POLLO Asado', display_name: 'POLLO Asado 500 gr', presentation: '500 gr', category_id: 'cat-pollo', top_category_id: 'cat-pollo', category_label: 'POLLO', subcategory_label: '',
      effective_station: 'parrilla', station: '', kind: 'preparado', price: 40000, cost: 7390, margin: 32610, margin_pct: 81.5,
      below_cost: false, missing_cost: [], no_recipe: false, active: true, available: true,
      recipe: [{ inventory_item_id: 'i1', component_item_id: null, insumo: 'Pollo crudo', unit: 'g', quantity: 400, yield_pct: 80 }] },
    { id: 'd2', name: 'CARNE Churrasco', display_name: 'CARNE Churrasco', category_id: CARNES, top_category_id: PLATOS, category_label: 'PLATOS A LA CARTA', subcategory_label: 'CARNES',
      effective_station: 'parrilla', station: '', kind: 'preparado', price: 3000, cost: 7390, margin: -4390, margin_pct: -146.3,
      below_cost: true, missing_cost: [], no_recipe: false, active: true, available: true, recipe: [] },
    { id: 'd3', name: 'GASEOSA Manzana', display_name: 'GASEOSA Manzana', category_id: null, top_category_id: null, category_label: '', subcategory_label: '',
      effective_station: '', station: '', kind: 'directo', inventory_item_id: 'i6', direct_qty: 1, price: 4000, cost: 2200, margin: 1800, margin_pct: 45,
      below_cost: false, missing_cost: [], no_recipe: false, active: true, available: true, recipe: [] },
    { id: 'd4', name: 'PAPA SALADA', display_name: 'PAPA SALADA', category_id: null, top_category_id: null, category_label: '', subcategory_label: '',
      effective_station: '', station: '', kind: 'preparado', price: 5000, cost: null, margin: null, margin_pct: null,
      below_cost: false, missing_cost: [], no_recipe: true, active: true, available: true, recipe: [] },
  ],
};

test('platos: tarjetas sin foto, por categoría y subcategoría, con precio, margen, Editar y Eliminar; nada de tablas', () => {
  const html = portal(DATA).cxCarPlatosHtml049J();
  assert.doesNotMatch(html, /<table|<img/);
  assert.match(html, /<h3>PLATOS A LA CARTA <small>1<\/small>[\s\S]*› CARNES[\s\S]*data-car-card="d2"[\s\S]*CARNE Churrasco[\s\S]*\$3\.000[\s\S]*Precio por debajo del costo/);
  assert.match(html, /<h3>POLLO <small>1<\/small>[\s\S]*POLLO Asado 500 gr[\s\S]*\$40\.000[\s\S]*Margen \$32\.610 · 81\.5%/);
  assert.match(html, /data-car-edit="d1">Editar<\/button><button class="client-btn danger" type="button" data-car-del="d1">Eliminar/);
  assert.match(html, /<b class="bad">2 sin categoría<\/b>/);
  assert.ok(html.indexOf('PLATOS A LA CARTA <small>') < html.indexOf('POLLO <small>') && html.indexOf('POLLO <small>') < html.indexOf('SIN CATEGORÍA'),
    'en el orden de las categorías de la Carta');
});

test('asistente: categoría -> subcategoría, receta con casillas y precio; plato completo en 5 pasos con costo y margen', async () => {
  const ctx = portal(DATA);
  const created = { ...DATA.items[1], id: 'n1', name: 'Churrasco', display_name: 'Churrasco 275 gr', price: 32000, cost: 3437.5, margin: 28562.5, margin_pct: 89.3, below_cost: false,
    recipe: [{ inventory_item_id: 'i4', insumo: 'Carne molida', unit: 'g', quantity: 275 }] };
  ctx.respond = (path) => ({ ...DATA, items: [...DATA.items, created], ...(path === '/items' ? { created_id: 'n1' } : {}) });
  let screens = 1;
  await ctx.click('data-car-new');
  // Paso 1: las categorías de la Carta con sus ejemplos; una con subcategorías las muestra
  let html = ctx.cxCarWizHtml049J();
  for (const label of ['BEBIDAS', 'PLATOS A LA CARTA', 'POLLO', 'COMIDAS RÁPIDAS', 'PORCIONES']) assert.match(html, new RegExp(`<b>${label}</b>`));
  assert.match(html, /gaseosas, jugos, energizantes, cerveza/);
  assert.match(html, /data-wz-cat-add><b>\+ Agregar categoría/);
  await ctx.click('data-wz-cat', PLATOS);
  assert.equal(ctx.cxCarWiz049J.step, 1, 'espera la subcategoría');
  html = ctx.cxCarWizHtml049J();
  assert.match(html, /¿En qué subcategoría de PLATOS A LA CARTA\?[\s\S]*data-wz-sub="">[\s\S]*Directo en PLATOS A LA CARTA[\s\S]*data-wz-sub="sub-carnes"><b>CARNES/);
  await ctx.click('data-wz-sub', CARNES); screens += 1;
  // Paso 2: nombre y presentación
  ctx.dom.typed = { name: 'Churrasco', presentation: '' };
  await ctx.click('data-wz-pres', '275 gr');
  ctx.dom.typed = { name: 'Churrasco' };
  await ctx.click('data-wz-next'); screens += 1;
  // Paso 3: buscador arriba, lista con casillas (todas las coincidencias, con scroll) y cantidades
  await ctx.click('data-wz-mode', 'receta');
  html = ctx.cxCarWizHtml049J();
  assert.ok(html.indexOf('data-wz-search') < html.indexOf('data-wz-results'), 'buscador arriba');
  assert.equal((html.match(/type="checkbox" name="wz-pick"/g) || []).length, 17, 'todo el inventario menos el consumible, desplazable');
  assert.doesNotMatch(html, /data-wz-check="insumo:i2"/, 'nunca un consumible');
  ctx.search('carne mol');
  assert.match(ctx.dom.boxes['[data-wz-results]'].innerHTML, /data-wz-check="insumo:i4"/);
  assert.doesNotMatch(ctx.dom.boxes['[data-wz-results]'].innerHTML, /Pan de hamburguesa/);
  await ctx.check('data-wz-check', 'insumo:i4');
  ctx.search('pan');
  await ctx.check('data-wz-check', 'insumo:i3');
  ctx.search('');
  await ctx.check('data-wz-check', 'insumo:i5');
  await ctx.check('data-wz-check', 'insumo:i5', false); // desmarcar la quita
  assert.match(ctx.dom.boxes['[data-wz-lines]'].innerHTML, /Carne molida[\s\S]*data-wz-line-qty="0" value=""[\s\S]*Pan de hamburguesa[\s\S]*data-wz-line-qty="1" value="1"/);
  assert.doesNotMatch(ctx.dom.boxes['[data-wz-lines]'].innerHTML, /Salsa de tomate/);
  await ctx.click('data-wz-next');
  assert.match(ctx.cxCarWizHtml049J(), /Escribe la cantidad de Carne molida/);
  ctx.qty(0, '275');
  await ctx.click('data-wz-del', '1');
  await ctx.click('data-wz-next'); screens += 1;
  // Paso 4: precio
  ctx.dom.typed = { price: '' };
  await ctx.click('data-wz-next');
  assert.match(ctx.cxCarWizHtml049J(), /Escribe el precio de venta/);
  ctx.dom.typed = { price: '32000' };
  await ctx.click('data-wz-next'); screens += 1;
  // Paso 5: opciones, sin foto por plato; la estación sale de la categoría
  html = ctx.cxCarWizHtml049J();
  assert.doesNotMatch(html, /type="file"|Subir foto/);
  assert.match(html, /Se vende por porciones \(1\/4, 1\/2, 3\/4, entero\)[\s\S]*Pide término de cocción[\s\S]*Visible en la carta/);
  assert.match(html, /<option value="">La de la categoría \(parrilla\)<\/option>/);
  await ctx.click('data-wz-toggle', 'requires_term');
  ctx.dom.typed = {};
  await ctx.click('data-wz-save');
  assert.ok(screens < 6, `se crea en ${screens} pasos`);

  const [create, recipe] = ctx.calls.filter((c) => c.method !== 'GET');
  assert.equal(create.path, '/items');
  assert.deepEqual({ ...create.body }, { name: 'Churrasco', presentation: '275 gr', price: 32000, category_id: CARNES, station: '', kind: 'preparado',
    inventory_item_id: null, direct_qty: 1, requires_term: true, allows_portions: false, active: true });
  assert.equal(recipe.path, '/items/n1/recipe');
  assert.deepEqual(JSON.parse(JSON.stringify(recipe.body.lines)), [{ inventory_item_id: 'i4', quantity: 275, yield_pct: 100, unit: 'g' }]);
  assert.ok(!ctx.calls.some((c) => c.form), 'no sube foto de plato');
  const summary = ctx.cxCarPlatosHtml049J();
  assert.match(summary, /Plato guardado[\s\S]*Churrasco 275 gr[\s\S]*PLATOS A LA CARTA › CARNES[\s\S]*Estación parrilla[\s\S]*<dt>Precio<\/dt><dd>\$32\.000[\s\S]*<dt>Costo<\/dt><dd>\$3\.438[\s\S]*Margen/);
});

test('producto del inventario: un solo producto y el precio ya cargado en el insumo para confirmarlo', async () => {
  const ctx = portal(DATA);
  ctx.respond = (path) => ({ ...DATA, ...(path === '/items' ? { created_id: 'n2' } : {}) });
  await ctx.click('data-car-new');
  await ctx.click('data-wz-cat', 'cat-bebidas');
  ctx.dom.typed = { name: 'Coca-Cola', presentation: '400 ml' };
  await ctx.click('data-wz-next');
  await ctx.click('data-wz-mode', 'directo');
  assert.match(ctx.cxCarWizHtml049J(), /type="radio" name="wz-pick" data-wz-check="insumo:i6"/);
  await ctx.check('data-wz-check', 'insumo:i3');
  await ctx.check('data-wz-check', 'insumo:i6');
  assert.equal(ctx.cxCarWiz049J.direct.inventory_item_id, 'i6', 'uno solo: el último marcado');
  ctx.dom.typed = {};
  await ctx.click('data-wz-next');
  assert.equal(ctx.cxCarWiz049J.step, 4);
  const html = ctx.cxCarWizHtml049J();
  assert.match(html, /Precio cargado en el insumo Coca-Cola 400 ml: <b>\$4\.000<\/b>\. Confírmalo o ajústalo\./);
  assert.match(html, /data-wz-field="price"[^>]*value="4000"/);
  ctx.dom.typed = { price: '4500' }; // lo ajusta
  await ctx.click('data-wz-next');
  ctx.dom.typed = {};
  await ctx.click('data-wz-save');
  const create = ctx.calls.find((c) => c.path === '/items');
  assert.equal(create.body.kind, 'directo');
  assert.equal(create.body.inventory_item_id, 'i6');
  assert.equal(create.body.price, 4500);
  assert.ok(!ctx.calls.some((c) => c.path.endsWith('/recipe')), 'un directo no manda receta');
});

test('sin receta se salta los ingredientes; sin estación en la categoría avisa', async () => {
  const ctx = portal(DATA);
  ctx.respond = (path) => ({ ...DATA, ...(path === '/items' ? { created_id: 'n3' } : {}) });
  await ctx.click('data-car-new');
  await ctx.click('data-wz-cat', 'cat-porciones');
  ctx.dom.typed = { name: 'Papa salada' };
  await ctx.click('data-wz-next');
  await ctx.click('data-wz-mode', 'sin');
  ctx.dom.typed = {};
  await ctx.click('data-wz-next');
  ctx.dom.typed = { price: '5000' };
  await ctx.click('data-wz-next');
  assert.match(ctx.cxCarWizHtml049J(), /Su categoría no tiene estación/);
  ctx.dom.typed = {};
  await ctx.click('data-wz-save');
  assert.equal(ctx.calls.find((c) => c.path === '/items').body.kind, 'preparado');
  assert.deepEqual(JSON.parse(JSON.stringify(ctx.calls.find((c) => c.path === '/items/n3/recipe').body)), { lines: [] });
});

test('combo: se arma marcando platos de la carta o insumos y manda sus partes', async () => {
  const ctx = portal(DATA);
  ctx.respond = (path) => ({ ...DATA, ...(path === '/items' ? { created_id: 'n4' } : {}) });
  await ctx.click('data-car-new');
  await ctx.click('data-wz-cat', 'cat-pollo');
  ctx.dom.typed = { name: 'Combo Socio' };
  await ctx.click('data-wz-next');
  await ctx.click('data-wz-mode', 'combo');
  assert.match(ctx.cxCarWizHtml049J(), /data-wz-check="plato:d1"[\s\S]*🍽 POLLO Asado 500 gr/);
  await ctx.check('data-wz-check', 'plato:d1');
  await ctx.check('data-wz-check', 'insumo:i6');
  ctx.qty(1, '2');
  ctx.dom.typed = {};
  await ctx.click('data-wz-next');
  ctx.dom.typed = { price: '45000' };
  await ctx.click('data-wz-next');
  ctx.dom.typed = {};
  await ctx.click('data-wz-save');
  assert.equal(ctx.calls.find((c) => c.path === '/items').body.kind, 'combo');
  assert.deepEqual(JSON.parse(JSON.stringify(ctx.calls.find((c) => c.path === '/items/n4/recipe').body.lines)),
    [{ component_item_id: 'd1', quantity: 1 }, { inventory_item_id: 'i6', quantity: 2, yield_pct: 100, unit: 'unidad' }]);
});

test('mover varios platos a la vez a su categoría', async () => {
  const ctx = portal(DATA);
  await ctx.click('data-car-move');
  let html = ctx.cxCarPlatosHtml049J();
  assert.match(html, /data-car-select="d3"/);
  assert.doesNotMatch(html, /data-car-edit=/, 'en modo mover no se edita');
  await ctx.click('data-car-select-group', 'none'); // "Marcar todos" en SIN CATEGORÍA
  assert.deepEqual([...ctx.cxCarUi049J.selected], ['d3', 'd4']);
  await ctx.check('data-car-select', 'd4', false);
  await ctx.check('data-car-select', 'd1', true);
  html = ctx.cxCarPlatosHtml049J();
  assert.match(html, /Marcados: <b>2<\/b>[\s\S]*<option value="sub-carnes" >&nbsp;&nbsp;› CARNES/);
  ctx.dom.values['[data-car-move-target]'] = 'cat-bebidas';
  await ctx.click('data-car-move-go');
  const move = ctx.calls.find((c) => c.path === '/items-category');
  assert.deepEqual(JSON.parse(JSON.stringify(move.body)), { item_ids: ['d3', 'd1'], category_id: 'cat-bebidas' });
  assert.equal(ctx.cxCarUi049J.moving, false);
  assert.match(ctx.cxCar048T.message, /2 plato\(s\) movidos a BEBIDAS/);
});

test('categorías: imagen completa (sin recorte), estación, notas, subcategorías y subir imagen', async () => {
  const ctx = portal(DATA);
  ctx.cxCar048T.tab = 'categorias';
  const html = ctx.cxCarCategoriesHtml049K();
  assert.match(html, /data-car-cat-row="cat-bebidas"[\s\S]*class="cx-car-fit-049k" style="--img:url\('\/api\/v1\/companies\/c1\/waiter-ordering\/products\/cat-bebidas\/image\?v=5'\)"><img/);
  assert.match(source, /\.cx-car-fit-049k img \{[^}]*object-fit:contain/, 'se ve completa');
  assert.match(html, /data-car-cat-row="sub-carnes"[\s\S]*Subcategoría/);
  assert.match(html, /data-car-cat-row="cat-platos"[\s\S]*<option value="parrilla" selected>parrilla<\/option>[\s\S]*value="sin sal"[\s\S]*name="requires_term" checked/);
  assert.match(html, /data-car-sub-add="cat-pollo">\+ Subcategoría en POLLO/);
  // guardar una fila
  const row = { querySelector: (sel) => ({ '[name=label]': { value: 'Pollo ' }, '[name=station]': { value: 'parrilla' },
    '[name=quick_notes]': { value: 'bien asado, sin sal' }, '[name=requires_term]': { checked: true } })[sel] };
  await ctx.click('data-car-cat-save', 'cat-pollo', { '[data-car-cat-row]': row, closest: (sel) => (sel === '[data-car-cat-row]' ? row : null) });
  const put = ctx.calls.find((c) => c.path === '/categories/cat-pollo');
  assert.deepEqual(JSON.parse(JSON.stringify(put.body)), { label: 'Pollo', station: 'parrilla', quick_notes: ['bien asado', 'sin sal'], requires_term: true });
  // subcategoría nueva
  await ctx.click('data-car-sub-add', 'cat-pollo');
  ctx.dom.values['[data-car-new-sub]'] = 'Broaster';
  ctx.respond = () => ({ ...DATA, created_category_id: 'sub-new' });
  await ctx.click('data-car-sub-save', 'cat-pollo');
  assert.deepEqual(JSON.parse(JSON.stringify(ctx.calls.find((c) => c.path === '/categories').body)), { label: 'Broaster', parent_id: 'cat-pollo' });
  // imagen: se sube por la ruta de Carta
  await ctx.cxCarOnChange049J({ target: { closest: (sel) => (sel === '[data-car-cat-image]' ? { getAttribute: () => 'cat-pollo', files: [{ name: 'pollo.jpg' }] } : null) } });
  const upload = ctx.calls.find((c) => c.form);
  assert.equal(upload.path, '/carta/companies/c1/categories/cat-pollo/image');
  assert.equal(upload.form[0][0], 'image');
});

test('editar abre el asistente con lo que ya tiene; eliminar pide confirmación', async () => {
  const ctx = portal(DATA);
  await ctx.click('data-car-edit', 'd2');
  const wiz = ctx.cxCarWiz049J;
  assert.equal(wiz.id, 'd2');
  assert.equal(wiz.category_id, CARNES);
  assert.equal(wiz.pickedTop, PLATOS);
  await ctx.click('data-wz-cancel');
  await ctx.click('data-car-edit', 'd1');
  assert.equal(ctx.cxCarWiz049J.lines[0].yield_pct, 80, 'conserva el rendimiento de la receta');
  await ctx.click('data-wz-cancel');
  await ctx.click('data-car-del', 'd1');
  assert.match(ctx.cxCarPlatosHtml049J(), /¿Eliminar este plato\?[\s\S]*data-car-del-yes="d1">Sí, eliminar/);
  assert.equal(ctx.calls.length, 0, 'todavía no borra');
  await ctx.click('data-car-del-yes', 'd1');
  assert.deepEqual({ path: ctx.calls[0].path, method: ctx.calls[0].method }, { path: '/items/d1', method: 'DELETE' });
});

test('QR de la carta: opcional, imagen para descargar, link y cambio de código', () => {
  const ctx = portal(DATA);
  assert.match(source, /const tabs = \[\["platos", "Platos"\], \["categorias", "Categorías"\], \["qr", "QR de la carta"\]\];/);
  assert.match(ctx.cxCarQrHtml049J(), /Generando el QR/);
  ctx.cxCarUi049J.qr = { url: 'https://x.test/carta-qr?t=abc', image: 'blob:qr' };
  const html = ctx.cxCarQrHtml049J();
  assert.match(html, /Opcional[\s\S]*No reemplaza al mesero ni a la caja/);
  assert.match(html, /<img src="blob:qr" alt="QR de la carta">/);
  assert.match(html, /data-car-qr-download >Descargar imagen/);
  assert.match(html, /href="https:\/\/x\.test\/carta-qr\?t=abc" target="_blank"/);
  assert.match(source, /fetch\(`\$\{API\}\/carta\/companies\/\$\{encodeURIComponent\(state\.companyId\)\}\/qr\.png`, \{ headers: authHeaders\(\{\}\) \}\)/, 'la imagen se pide con sesión');
});

test('049R: sin pestaña Insumos en Carta ni "Insumos y compras" en Inventario: todo nace en Modificar material', () => {
  const ctx = portal(DATA);
  assert.equal(typeof ctx.cxCarInsumosHtml048T, 'undefined');
  assert.equal(typeof ctx.cxInvInsumosPanelHtml049Q, 'undefined', 'la pestaña Insumos y compras se quitó');
  assert.doesNotMatch(source, /\["insumos", "Insumos"\]|data-car-save-insumo|Insumos y compras|data-inventory-mode="insumos"|data-car-go-inventory/);
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

// ------------------------------------------------ paneles: tres niveles y atrás
const kit = readFileSync('app/web/hsp_menu_kit.js', 'utf8');
const qrPage = readFileSync('app/web/carta_qr.js', 'utf8');
const waiter = readFileSync('app/web/hsp_waiter.js', 'utf8');
const delivery = readFileSync('app/web/hsp_delivery.js', 'utf8');

function kitCtx() {
  const window = {};
  const ctx = vm.createContext({ window, document: {}, console, Math, Number, String, Array, Object, JSON, Intl, encodeURIComponent });
  vm.runInContext(kit, ctx);
  return window.CxMenuKit;
}

test('kit: la imagen de una categoría de Carta se ve completa; The Time Machine sigue igual', () => {
  const Kit = kitCtx();
  const carta = Kit.categoryGridHtml([{ key: 'c1', label: 'POLLO', has_image: true, image_item_id: 'c1', image_version: '7', image_fit: 'contain' }], { companyId: 'co' });
  assert.match(carta, /class="wtr-cat-img wtr-cat-fit" style="--wtr-img:url\('\/api\/v1\/companies\/co\/waiter-ordering\/products\/c1\/image\?v=7'\)"><img src="\/api\/v1\/companies\/co\/waiter-ordering\/products\/c1\/image\?v=7"/);
  assert.match(kit, /\.wtr-cat-fit img\{[^}]*object-fit:contain/);
  const ttm = Kit.categoryGridHtml([{ key: 'club', label: 'Cervezas', has_image: true }], { companyId: 'co' });
  assert.match(ttm, /<div class="wtr-cat-img" style="background-image:url\('\/api\/v1\/companies\/co\/waiter-ordering\/categories\/club\/image'\)"><\/div>/);
});

test('carta del QR: categoría -> subcategoría -> platos en texto, y atrás vuelve un nivel', () => {
  const listeners = {};
  const history = { entries: [{ state: null }], index: 0,
    get state() { return this.entries[this.index].state; },
    replaceState(s) { this.entries[this.index] = { state: s }; },
    pushState(s) { this.entries = this.entries.slice(0, this.index + 1); this.entries.push({ state: s }); this.index += 1; },
    back() { if (this.index === 0) { this.exited = true; return; } this.index -= 1; listeners.popstate({ state: this.state }); } };
  const root = { innerHTML: '' };
  const window = { history, location: { search: '?t=tok' }, scrollTo() {}, addEventListener: (n, f) => { listeners[n] = f; } };
  const doc = { getElementById: () => root, createElement: () => ({}), head: { appendChild() {} }, body: {},
    querySelector: () => null, querySelectorAll: () => [], addEventListener: (n, f) => { listeners[`doc_${n}`] = f; } };
  const data = { company_id: 'co', company_name: 'ASADERO', menu_emojis: false, categories: [
    { key: 'c1', label: 'PLATOS A LA CARTA', has_image: true, image_item_id: 'c1', image_fit: 'contain',
      subcategories: [{ key: 's1', label: 'CARNES', has_image: true, image_item_id: 's1', image_fit: 'contain', products: [{ id: 'p1', name: 'Churrasco 275 gr', price: 32000 }] }],
      products: [{ id: 'p1', name: 'Churrasco 275 gr', price: 32000, subcategory_key: 's1' }, { id: 'p2', name: 'Pechuga', price: 25000, subcategory_key: '' }] },
    { key: 'c2', label: 'BEBIDAS', has_image: false, subcategories: [], products: [{ id: 'p3', name: 'Coca-Cola 400 ml', price: 4000 }] }] };
  const ctx = vm.createContext({ window, document: doc, MutationObserver: class { observe() {} }, URLSearchParams, console, Math, Number, String, Array, Object, JSON, Intl, encodeURIComponent,
    fetch: async () => ({ ok: true, json: async () => data }) });
  vm.runInContext(kit, ctx);
  window.CxMenuKit.injectStyles = () => {};
  ctx.window = window; ctx.history = history;
  vm.runInContext(qrPage.replace('(function () {', '(function () { const window = globalThis.window;'), ctx);
  return new Promise((resolve) => setTimeout(resolve, 0)).then(() => {
    const click = (attr, value) => listeners.doc_click({ target: { closest: (sel) => (sel === `[${attr}]` ? { getAttribute: () => value } : null) } });
    assert.match(root.innerHTML, /data-cq-cat="c1"[\s\S]*wtr-cat-fit/);
    click('data-cq-cat', 'c1');
    assert.match(root.innerHTML, /data-cq-sub="s1"[\s\S]*Pechuga/);
    assert.doesNotMatch(root.innerHTML, /Churrasco/, 'los platos de la subcategoría van adentro');
    click('data-cq-sub', 's1');
    assert.match(root.innerHTML, /<h2 class="cq-cat-title">CARNES<\/h2>[\s\S]*<li><span>Churrasco 275 gr<\/span><b>\$\s?32\.000<\/b><\/li>/);
    assert.doesNotMatch(root.innerHTML, /<img/, 'el plato va sin imagen');
    history.back();
    assert.match(root.innerHTML, /data-cq-sub="s1"/);
    history.back();
    assert.match(root.innerHTML, /data-cq-cat="c1"/);
    assert.ok(!history.exited);
    history.back();
    assert.equal(history.exited, true, 'solo desde el inicio sale');
  });
});

test('mesero y domicilios: tres niveles con Carta', () => {
  assert.match(waiter, /goto\(picked && \(picked\.subcategories \|\| \[\]\)\.length \? "subcategories" : "products"\)/);
  assert.match(waiter, /Kit\.categoryGridHtml\(subs, kitOptions\("data-wtr-sub"\)\)/);
  assert.match(waiter, /state\.menuCarta = data\.carta === true/);
  assert.match(delivery, /Kit\.categoryGridHtml\(subs, kitOptions\("data-dom-sub"\)\)/);
  assert.match(delivery, /Kit\.backNav\(/);
});


// ------------------------------------------- 049N: unidades y costo en la receta
const TOMATE = { id: 't1', name: 'Tomate', item_type: 'ingrediente', purchase_unit: 'kilo', consumption_unit: 'g', units_per_purchase: 1000,
  stock: 5000, avg_cost: 4, sale_price: 0 }; // el kilo costó $4.000 -> $4 por gramo
const ACEITE = { id: 'a1', name: 'Aceite', item_type: 'ingrediente', purchase_unit: 'litro', consumption_unit: 'ml', units_per_purchase: 1000,
  stock: 3000, avg_cost: 12, sale_price: 0 };
const PAN = { id: 'p1', name: 'Pan', item_type: 'ingrediente', purchase_unit: 'unidad', consumption_unit: 'unidad', units_per_purchase: 1,
  stock: 40, avg_cost: 800, sale_price: 0 };
const POLLO = { id: 'po', name: 'Pollo', item_type: 'ingrediente', purchase_unit: 'unidad', consumption_unit: 'g', units_per_purchase: 1600,
  stock: 16000, avg_cost: 12.5, sale_price: 0 };
const UNITS_DATA = { ...DATA, insumos: [TOMATE, ACEITE, PAN, POLLO] };

test('unidades: conversión entre gr, kg, lb, ml, litros, unidad y par en ambos sentidos', () => {
  const ctx = portal(UNITS_DATA);
  assert.equal(ctx.cxCarFactor049N('g', TOMATE), 1);
  assert.equal(ctx.cxCarFactor049N('kg', TOMATE), 1000);
  assert.equal(ctx.cxCarFactor049N('lb', TOMATE), 453.59237);
  assert.equal(ctx.cxCarFactor049N('l', ACEITE), 1000);
  assert.equal(ctx.cxCarFactor049N('ml', ACEITE), 1);
  assert.equal(ctx.cxCarFactor049N('par', PAN), 2);
  assert.equal(ctx.cxCarFactor049N('unidad', POLLO), 1600, '1 unidad de pollo = lo que trae cada unidad de compra');
  assert.equal(ctx.cxCarFactor049N('ml', TOMATE), null, 'no convierte masa a volumen');
  assert.equal(ctx.cxCarFactor049N('g', PAN), null, 'el pan no tiene peso definido');
  // 049R: la misma lista para todos; solo se eligen las que convierten solas (sin preguntas)
  const opts = ctx.cxCarUnitOptions049N({ inventory_item_id: 't1', unit: 'g' });
  assert.match(opts, /<option value="g" selected>gr<\/option><option value="kg" >kg<\/option><option value="lb" >lb<\/option><option value="oz" >onza<\/option><option value="ml"  disabled>ml<\/option>/);
  const labels = (html) => [...html.matchAll(/>([^<]+)<\/option>/g)].map((m) => m[1]);
  for (const id of ['t1', 'p1', 'a1', 'po']) {
    assert.deepEqual(labels(ctx.cxCarUnitOptions049N({ inventory_item_id: id, unit: 'zz' })),
      ['gr', 'kg', 'lb', 'onza', 'ml', 'litros', 'unidad', 'par', 'docena', 'paquete', 'cucharada', 'pizca'], `${id}: la misma lista para todos`);
  }
  const enabled = (id) => [...ctx.cxCarUnitOptions049N({ inventory_item_id: id, unit: 'zz' }).matchAll(/<option value="(\w+)" >/g)].map((m) => m[1]);
  assert.deepEqual(enabled('t1'), ['g', 'kg', 'lb', 'oz'], 'tomate en gramos: gr, kg, lb, onza');
  assert.deepEqual(enabled('a1'), ['ml', 'l', 'cucharada'], 'aceite: ml, litros, cucharada');
  assert.deepEqual(enabled('p1'), ['unidad', 'par', 'docena'], 'pan: unidad, par, docena');
});

test('costo de la porción al escribir la cantidad: 3 gr de tomate de $4.000 el kilo = $12', async () => {
  const ctx = portal(UNITS_DATA);
  await ctx.click('data-car-new');
  await ctx.click('data-wz-cat', 'cat-pollo');
  ctx.dom.typed = { name: 'Hamburguesa' };
  await ctx.click('data-wz-next');
  await ctx.click('data-wz-mode', 'receta');
  await ctx.check('data-wz-check', 'insumo:t1');
  await ctx.check('data-wz-check', 'insumo:a1');
  const wiz = ctx.cxCarWiz049J;
  assert.equal(wiz.lines[0].unit, 'g', 'arranca en la unidad del inventario');
  ctx.qty(0, '3');
  assert.equal(ctx.cxCarPortionMoney049N(ctx.cxCarLineCost049N(wiz.lines[0]).cost), '$12');
  wiz.lines[1].quantity = '0.02';
  await ctx.cxCarOnChange049J({ target: { closest: (sel) => (sel === '[data-wz-line-unit]' ? { getAttribute: () => '1', value: 'l' } : null) } });
  assert.equal(wiz.lines[1].unit, 'l');
  assert.equal(ctx.cxCarLineCost049N(wiz.lines[1]).need, 20, '0,02 litros = 20 ml del inventario');
  assert.equal(ctx.cxCarLineCost049N(wiz.lines[1]).cost, 240);
  const costs = ctx.cxCarCostsHtml049N(wiz);
  assert.match(costs, /Costo de los ingredientes por plato<\/span><b>\$252<\/b>/, 'suma los ingredientes: 12 + 240');
  assert.ok(costs.indexOf('Aceite') < costs.indexOf('Tomate'), 'el que más pesa, primero');
  assert.match(costs, /Aceite<\/span><i style="--pct:95\.2%"><\/i><b>\$240<\/b><small>95%/);
  const html = ctx.cxCarWizHtml049J();
  assert.match(html, /data-wz-line-unit="0"[\s\S]*data-wz-line-cost="0"[^>]*>\$12<\/b>/);
  ctx.dom.typed = {};
  await ctx.click('data-wz-next');
  ctx.dom.typed = { price: '18000' };
  await ctx.click('data-wz-next');
  ctx.dom.typed = {};
  ctx.respond = (path) => ({ ...UNITS_DATA, ...(path === '/items' ? { created_id: 'h1' } : {}) });
  await ctx.click('data-wz-save');
  const recipe = ctx.calls.find((c) => c.path === '/items/h1/recipe');
  assert.deepEqual(JSON.parse(JSON.stringify(recipe.body.lines)),
    [{ inventory_item_id: 't1', quantity: 3, yield_pct: 100, unit: 'g' }, { inventory_item_id: 'a1', quantity: 0.02, yield_pct: 100, unit: 'l' }]);
});

test('resumen: costo total del plato y el aporte de cada ingrediente', () => {
  const ctx = portal(UNITS_DATA);
  const html = ctx.cxCarRecipeBreakdown049N({ kind: 'preparado', cost: 252, recipe: [
    { insumo: 'Tomate', quantity: 3, unit: 'g', unit_label: 'gr', cost: 12, share_pct: 4.8 },
    { insumo: 'Aceite', quantity: 0.02, unit: 'l', unit_label: 'litros', cost: 240, share_pct: 95.2 }] });
  assert.match(html, /Costo por ingrediente<\/span><b>\$252<\/b>[\s\S]*Aceite <small>0\.02 litros<\/small>[\s\S]*\$240[\s\S]*95\.2%[\s\S]*Tomate <small>3 gr<\/small>[\s\S]*\$12/);
});

test('contraste: encabezados de categoría con fondo propio, precios en el color del texto y avisos legibles', () => {
  const start = source.indexOf('  function cxCarStyles049N() {');
  const css = source.slice(start, source.indexOf('  /* CX_CARTA_048T_END */'));
  assert.match(css, /\.cx-car-group-049j > h3 \{[^}]*background:#1e293b; color:#ffffff;[^}]*font-size:20px/);
  assert.match(css, /\.cx-car-price-049j \{ color:inherit;/);
  assert.match(css, /\.cx-car-flags-049j em\.bad \{ background:#fef3c7; color:#78350f;/);
  assert.match(css, /\.cx-car-margin-049j\.ok \{ background:#dcfce7; color:#14532d; \}/);
  const carta = source.slice(source.indexOf('  /* CX_CARTA_048T_START */'), source.indexOf('  /* CX_CARTA_048T_END */'));
  assert.doesNotMatch(carta, /rgba\(255,255,255,/, 'nada de blanco translúcido fijo sobre fondos claros');
  assert.doesNotMatch(carta, /#ffd166/, 'sin el amarillo que no se lee');
  assert.match(source, /cxCarStyles049J\(\);\n    cxCarStyles049N\(\);/);
});


// ---------------------------------------- 049O: equivalencias y alerta de costo
const CARNE = { id: 'c1', name: 'Carne de res', item_type: 'ingrediente', purchase_unit: 'unidad', consumption_unit: 'unidad',
  units_per_purchase: 1, stock: 20, avg_cost: 14000, sale_price: 0, equivalences: {}, size_value: 1, size_unit: 'lb' };
const SAL = { id: 's1', name: 'Sal', item_type: 'ingrediente', purchase_unit: 'kilo', consumption_unit: 'g', units_per_purchase: 1000,
  stock: 900, avg_cost: 3, sale_price: 0, equivalences: {} };
const EQ_DATA = { ...DATA, insumos: [CARNE, SAL, TOMATE] };

test('049R: la carta calcula el costo de la porción al instante, sin equivalencias que llenar', async () => {
  const CARNE_SALDO = { id: 'k1', name: 'Carne asada', item_type: 'ingrediente', purchase_unit: 'kg', consumption_unit: 'g', units_per_purchase: 1000,
    stock: 12000, stock_value: 192000, avg_cost: 16, sale_price: 0, equivalences: {} };
  const ctx = portal({ ...DATA, insumos: [CARNE_SALDO] });
  await ctx.click('data-car-new');
  await ctx.click('data-wz-cat', 'cat-pollo');
  ctx.dom.typed = { name: 'CARNE Asada' };
  await ctx.click('data-wz-next');
  await ctx.click('data-wz-mode', 'receta');
  await ctx.check('data-wz-check', 'insumo:k1');
  const wiz = ctx.cxCarWiz049J;
  ctx.qty(0, '275');
  assert.equal(wiz.lines[0].unit || 'g', 'g');
  const html = ctx.cxCarWizHtml049J();
  assert.doesNotMatch(html, /data-wz-eq|Falta la equivalencia|data-car-go-inventory/, 'sin preguntas ni configuraciones');
  assert.match(html, /data-wz-line-cost="0"[^>]*>\$4\.400</, '275 gr de un saldo de 12.000 gr y $192.000 = $4.400');
  wiz.lines[0].unit = 'kg';
  wiz.lines[0].quantity = '0.275';
  assert.equal(ctx.cxCarPortionMoney049N(ctx.cxCarLineCost049N(wiz.lines[0]).cost), '$4.400', 'en kilos da lo mismo');
});

test('una línea vieja en una unidad que no convierte: se avisa qué unidades sirven (sin formulario)', () => {
  const SAL = { id: 's1', name: 'Sal', item_type: 'ingrediente', purchase_unit: 'kg', consumption_unit: 'g', units_per_purchase: 1000, stock: 900, avg_cost: 3, equivalences: {} };
  const ctx = portal({ ...DATA, insumos: [SAL] });
  const line = { inventory_item_id: 's1', insumo: 'Sal', unit: 'cucharada', quantity: 1 };
  assert.equal(ctx.cxCarFactor049N('cucharada', SAL), null);
  const note = ctx.cxCarEqForm049O(line, 0);
  assert.match(note, /cucharada no se convierte a lo que hay de Sal: elige gr, kg, lb, onza\./);
  assert.doesNotMatch(note, /<input|<button/);
  assert.equal(ctx.cxCarFactor049N('cucharada', { consumption_unit: 'ml' }), 15, '1 cucharada = 15 ml sin preguntar');
});

test('costo desproporcionado: avisa en vez de mostrar la cifra como correcta', () => {
  const ctx = portal(EQ_DATA);
  const wiz = { price: '32000', lines: [{ inventory_item_id: 'c1', insumo: 'Carne de res', unit: 'unidad', quantity: '275', yield_pct: 100 }] };
  assert.equal(ctx.cxCarLineCostText049O(wiz, wiz.lines[0]), '⚠ $3.850.000');
  assert.match(ctx.cxCarCostsHtml049N(wiz), /data-wz-suspect>⚠ Costo desproporcionado: Carne de res cuesta más de 3 veces el precio del plato/);
  const d = { kind: 'preparado', cost: null, price: 32000, cost_suspect: ['Carne de res'], missing_equivalence: [], active: true, available: true,
    missing_cost: [], recipe: [{ insumo: 'Carne de res', quantity: 275, unit: 'unidad', unit_label: 'unidad', cost: 3850000, share_pct: 100, cost_suspect: true }] };
  assert.match(ctx.cxCarMarginHtml049J(d), /Costo por revisar/);
  assert.match(ctx.cxCarFlagsHtml049J(d), /<em class="bad">Costo desproporcionado: Carne de res \(revisa la unidad\)<\/em>/);
  assert.match(ctx.cxCarRecipeBreakdown049N(d), /Costo por ingrediente<\/span><b>por revisar<\/b>[\s\S]*<b class="bad">⚠ \$3\.850\.000<\/b>[\s\S]*casi seguro la unidad está mal/);
  assert.match(ctx.cxCarFlagsHtml049J({ ...d, cost_suspect: [], missing_equivalence: ['Papa'] }), /Falta equivalencia: Papa/);
});

test('atajos de cantidad ampliados en el paso 2', () => {
  const ctx = portal(DATA);
  ctx.cxCarWiz049J = ctx.cxCarWizFrom049J(null);
  const html = ctx.cxCarWizNameHtml049J(ctx.cxCarWiz049J);
  for (const chip of ['100 gr', '150 gr', '200 gr', '250 gr', '300 gr', '400 gr', '1 kg', '150 ml', '200 ml', '300 ml', '400 ml', '1 L', '2 L',
    '1 unidad', '1/2 unidad', 'porción personal', 'porción familiar', '125 gr', '275 gr', '500 ml', '1.5 L']) {
    assert.ok(html.includes(`data-wz-pres="${chip}"`), chip);
  }
});

test('carne mal cargada: la carta dice que se corrige registrando la compra de nuevo', () => {
  const MAL = { id: 'm1', name: 'CARNE Asada', item_type: 'ingrediente', purchase_unit: 'unidad', consumption_unit: 'g', units_per_purchase: 1,
    stock: 16, avg_cost: null, purchase_weight_missing: true, equivalences: {} };
  const ctx = portal({ ...DATA, insumos: [MAL] });
  const line = { inventory_item_id: 'm1', insumo: 'CARNE Asada', unit: 'g', quantity: '275', yield_pct: 100 };
  assert.equal(ctx.cxCarFactor049N('g', MAL), null, 'no se calcula con un saldo imposible');
  assert.match(ctx.cxCarEqForm049O(line, 0), /CARNE Asada quedó mal cargado en Inventario: registra su compra con &quot;Corregir saldo&quot;/);
});

// ------------------- 049R: Inventario = cuenta con dos saldos (solo con Carta)
const CARNE_KG = { id: 'k1', name: 'Carne asada', item_type: 'ingrediente', purchase_unit: 'kg', consumption_unit: 'g', units_per_purchase: 1000,
  unit: 'kg', unit_label: 'kg', natural_factor: 1000, stock: 11725, stock_natural: 11.725, min_stock_natural: 2, avg_cost: 16, cost_per_unit: 16000,
  stock_value: 187600, balance_suspect: false, sale_price: 0, equivalences: {},
  last_purchase: { quantity: 3, unit: 'kg', unit_label: 'kg', total_paid: 42000, base_quantity: 3000, unit_cost: 14, created_at: '2026-09-28T15:00:00' } };

function inventoryCtx(insumos) {
  const ctx = portal({ ...DATA, insumos });
  ctx.cxInv049Q.data = { ...DATA, insumos };
  ctx.notices = [];
  ctx.showInventoryNotice = (text, kind) => ctx.notices.push([kind || 'ok', text]);
  ctx.renderInventoryModule = async () => {};
  ctx.setTimeout = (fn) => fn();
  return ctx;
}

test('dos saldos: comprar 12 kg por $192.000, consumir 275 gr y comprar 3 kg por $42.000', async () => {
  const empty = { ...CARNE_KG, stock: 0, stock_natural: 0, stock_value: null, avg_cost: null, cost_per_unit: null, last_purchase: null };
  const ctx = inventoryCtx([CARNE_KG]);
  const first = ctx.cxInvPurchasePreview049Q(empty, 12, 'kg', 192000);
  assert.equal(first.text, 'Saldo: 12.000 gr y $192.000 · $16,00 por gr');
  // tras consumir 275 gr: 11.725 gr y $187.600; entra la segunda compra
  const second = ctx.cxInvPurchasePreview049Q(CARNE_KG, 3, 'kg', 42000);
  assert.equal(second.stock, 14725);
  assert.equal(second.value, 229600);
  assert.equal(second.cost, 229600 / 14725, 'costo por gramo = dinero / cantidad');
  assert.equal(second.text, 'Saldo: 14.725 gr y $229.600 · $15,59 por gr');
  // la compra se escribe en la fila: cantidad total, unidad y total pagado; nunca un precio unitario
  const cell = ctx.cxInvBuyCellHtml049R(CARNE_KG);
  assert.match(cell, /data-inv-buy-qty="k1" placeholder="Cantidad total"[\s\S]*<select data-inv-buy-unit="k1"[\s\S]*<option value="kg" selected>kg[\s\S]*data-inv-buy-total="k1" placeholder="Total pagado"[\s\S]*data-inv-buy-save="k1">Registrar compra/);
  assert.doesNotMatch(cell, /precio unitario|Precio de entrada/i);
  Object.assign(ctx.dom.values, { '[data-inv-buy-qty="k1"]': '3', '[data-inv-buy-unit="k1"]': 'kg', '[data-inv-buy-total="k1"]': '42.000' });
  await ctx.cxInvHandleClick049Q({ closest: (sel) => (sel === '[data-inv-buy-save]' ? { getAttribute: () => 'k1' } : null) });
  const post = ctx.calls.find((c) => c.path === '/insumos/k1/purchases');
  assert.deepEqual(JSON.parse(JSON.stringify(post.body)), { quantity: 3, unit: 'kg', total_paid: 42000, replace: false });
  assert.match(ctx.notices[0][1], /Saldo: 14\.725 gr y \$229\.600/);
});

test('saldos a la vista, nota discreta de la última compra y carne dañada lista para corregir', () => {
  const ctx = inventoryCtx([CARNE_KG]);
  assert.equal(ctx.cxInvStockText049Q(CARNE_KG), '11,725 kg (11.725 gr)');
  assert.match(ctx.cxInvBalanceHtml049R(CARNE_KG), /<b>\$187\.600<\/b><small>\$16,00 por gr<\/small>/);
  assert.match(ctx.cxInvLastPurchaseHtml049R(CARNE_KG), /class="cx-inv-last-049r">Última compra: 3 kg · \$42\.000 · 28\/09\/2026</);
  const damaged = { ...CARNE_KG, id: 'd1', stock: 16, avg_cost: 56000, balance_suspect: true };
  assert.match(ctx.cxInvBalanceHtml049R(damaged), /Mal cargado: registra la compra con "Corregir saldo"/);
  assert.match(ctx.cxInvBuyCellHtml049R(damaged), /data-inv-buy-replace="d1" checked> Corregir saldo/, 'la corrección viene marcada');
  assert.doesNotMatch(ctx.cxInvBuyCellHtml049R(CARNE_KG), /data-inv-buy-replace="k1" checked/);
  const fixed = ctx.cxInvPurchasePreview049Q(damaged, 12, 'kg', 192000, true);
  assert.equal(fixed.text, 'Saldo: 12.000 gr y $192.000 · $16,00 por gr', 'corregir = los saldos quedan los de la compra');
});

test('crear con Carta: nombre, cantidad total comprada, unidad de compra, total pagado y mínimo. Nada más', async () => {
  const ctx = inventoryCtx([]);
  const html = ctx.cxInvCreatePanelHtml049R();
  const labels = [...html.matchAll(/<label>([^<]+)<\/label>/g)].map((m) => m[1]);
  assert.deepEqual(labels, ['Nombre / referencia', 'Cantidad total comprada', 'Unidad de medida de compra', 'Total pagado', 'Mínimo alerta']);
  assert.doesNotMatch(html, /Precio de salida|Color|Tamaño|Precio de entrada|Porciones|Adjuntar factura|type="file"/i);
  const units = [...html.split('inventoryCreateUnit049Q')[1].split('</select>')[0].matchAll(/>([^<]+)<\/option>/g)].map((m) => m[1]);
  assert.deepEqual(units, ['gr', 'kg', 'lb', 'onza', 'ml', 'litros', 'unidad', 'par', 'docena', 'paquete', 'cucharada', 'pizca'], 'misma lista que Carta');
  assert.equal(ctx.cxInvCreatePreview049Q('kg', 12, 192000).text, 'Saldo: 12.000 gr y $192.000 · $16,00 por gr');
  assert.match(source, /if \(cxInvCartaOn049Q\(\)\) return cxInvCreatePanelHtml049R\(\);/, 'solo con Carta; las demás empresas no cambian');
});
