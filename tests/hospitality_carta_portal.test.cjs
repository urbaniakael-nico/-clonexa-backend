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
  assert.deepEqual(JSON.parse(JSON.stringify(recipe.body.lines)), [{ inventory_item_id: 'i4', quantity: 275, yield_pct: 100 }]);
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
    [{ component_item_id: 'd1', quantity: 1 }, { inventory_item_id: 'i6', quantity: 2, yield_pct: 100 }]);
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
  assert.match(source, /\["categorias", "Categorías"\], \["insumos", "Insumos"\], \["qr", "QR de la carta"\]/);
  assert.match(ctx.cxCarQrHtml049J(), /Generando el QR/);
  ctx.cxCarUi049J.qr = { url: 'https://x.test/carta-qr?t=abc', image: 'blob:qr' };
  const html = ctx.cxCarQrHtml049J();
  assert.match(html, /Opcional[\s\S]*No reemplaza al mesero ni a la caja/);
  assert.match(html, /<img src="blob:qr" alt="QR de la carta">/);
  assert.match(html, /data-car-qr-download >Descargar imagen/);
  assert.match(html, /href="https:\/\/x\.test\/carta-qr\?t=abc" target="_blank"/);
  assert.match(source, /fetch\(`\$\{API\}\/carta\/companies\/\$\{encodeURIComponent\(state\.companyId\)\}\/qr\.png`, \{ headers: authHeaders\(\{\}\) \}\)/, 'la imagen se pide con sesión');
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
