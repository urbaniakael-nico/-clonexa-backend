// Referencias v2: selección de parte, prenda y tallas, resumen, filtros de las
// tres columnas, cortes y el enganche de client.js (interruptor apagado = pantalla de siempre).
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { readFileSync } = require('node:fs');

const SRC = readFileSync('app/web/references_v2.js', 'utf8');
const CATALOG = JSON.parse(readFileSync('app/services/garment_catalog.json', 'utf8'));
const plain = (v) => JSON.parse(JSON.stringify(v));

function load() {
  const window = {};
  const ctx = vm.createContext({ window, document: {}, JSON, Object, Array, String, Number, Math, Date, Map, Set, Promise, Error, encodeURIComponent });
  vm.runInContext(SRC, ctx);
  return window.CxReferencesV2;
}

const ROWS = [
  { id: 'p10', name: 'PANT SET', category: 'Pantalón', size: '10', color: 'Marfil', bot_active: true, channel: 'bot', initial_quantity: 30, finished_quantity: 0, pending_quantity: 30 },
  { id: 'p12', name: 'PANT SET', category: 'Pantalón', size: '12', color: 'Marfil', bot_active: false, channel: 'system', initial_quantity: 20, finished_quantity: 0, pending_quantity: 20 },
  { id: 'mj', name: 'Mystic jacket', category: 'Superior', size: 'SM, MI', color: 'Marfil', bot_active: true, channel: 'bot', initial_quantity: 126, finished_quantity: 126, pending_quantity: 0 },
  { id: 'mp', name: 'Mystic pant', category: '', size: '4, 6, 8, 10, 12', color: '', bot_active: true, channel: 'bot', initial_quantity: 114, finished_quantity: 114, pending_quantity: 0 },
  { id: 'aa', name: 'Aurora Azul', category: 'Chaqueta', size: 'Sm-MI', color: 'Azul', bot_active: false, channel: 'system', initial_quantity: 0, finished_quantity: 0 },
];
const EXTRAS = {
  p10: { gender: 'mujer', body_part: 'inferior', garment_type: 'pantalon', classified: true, combined_sizes: false, deployed: { quantity: 1, last_date: '2026-10-06' } },
  p12: { gender: 'mujer', body_part: 'inferior', garment_type: 'pantalon', classified: true, combined_sizes: false },
  mj: { classified: false, combined_sizes: true, suggestion: { gender: 'mujer', body_part: 'superior', garment_type: 'chaqueta' } },
  mp: { classified: false, combined_sizes: true, suggestion: { gender: 'mujer', body_part: 'inferior', garment_type: 'pantalon' } },
  aa: { classified: false, combined_sizes: false, suggestion: { gender: 'mujer', body_part: 'superior', garment_type: 'chaqueta' } },
};

test('catálogo: tallas por género y prenda, siempre de menor a mayor', () => {
  const R = load();
  assert.deepEqual(plain(R.sizesFor(CATALOG, 'mujer', 'pantalon')), ['4', '6', '8', '10', '12', '14', '16']);
  assert.deepEqual(plain(R.sizesFor(CATALOG, 'mujer', 'blusa')), ['S', 'M', 'L'], 'prendas superiores de mujer: solo S, M, L');
  assert.deepEqual(plain(R.sizesFor(CATALOG, 'mujer', 'chaqueta')), ['S', 'M', 'L']);
  assert.deepEqual(plain(R.sizesFor(CATALOG, 'mujer', 'ropa_interior')), ['S', 'M', 'L']);
  assert.deepEqual(plain(R.sizesFor(CATALOG, 'mujer', 'medias')), ['Única']);
  assert.deepEqual(plain(R.sizesFor(CATALOG, 'hombre', 'pantalon')), ['28', '30', '32', '34', '36', '38', '40']);
  assert.deepEqual(plain(R.sizesFor(CATALOG, 'hombre', 'camiseta')), ['S', 'M', 'L', 'XL', 'XXL']);
  assert.deepEqual(plain(R.garmentsOf(CATALOG, 'superior').map((g) => g.code)), ['chaqueta', 'camiseta', 'blusa', 'buzo', 'top']);
  assert.deepEqual(plain(R.garmentsOf(CATALOG, 'inferior').map((g) => g.code)), ['pantalon', 'falda', 'short', 'leggings', 'medias', 'ropa_interior']);
});

test('selección de parte, prenda y tallas; el campo de cantidad se habilita al marcar; resumen', () => {
  const R = load();
  const m = R.model;
  m.catalog = CATALOG; m.counts = { mujer: { parts: { inferior: 3, superior: 2 }, garments: { pantalon: 3 } } };
  global.ctx = null;
  let html = R.view();
  assert.match(html, /Prendas parte superior/); assert.match(html, /Prendas parte inferior/);
  assert.match(html, /2 referencias/); assert.match(html, /3 referencias/);
  assert.doesNotMatch(html, /Elige la prenda/, 'la prenda aparece al elegir la parte');
  m.form.part = 'inferior';
  html = R.view();
  assert.match(html, /Elige la prenda<span class="rv-step-detail">&nbsp;· Parte inferior<\/span>/);
  for (const g of ['Pantalón', 'Falda', 'Short', 'Leggings', 'Medias', 'Ropa interior']) assert.match(html, new RegExp(`<b>${g}</b>`));
  assert.match(html, /<svg class="rv-icon/, 'ilustraciones SVG en el código');
  m.form.garment = 'pantalon';
  m.form.sizes = { 6: '20', 4: '30' };
  html = R.view();
  assert.match(html, /Tallas y cantidades<span class="rv-step-detail">&nbsp;· Pantalón Mujer<\/span>/);
  assert.match(html, /data-rv-qty="4" value="30" (?!disabled)/);
  assert.match(html, /data-rv-qty="8" value="" disabled/, 'sin marcar, la cantidad está deshabilitada');
  assert.match(html, /Ruta: <b>Parte inferior › Pantalón › Mujer<\/b>/);
  assert.equal(R.summaryText(m.form, CATALOG, 'mujer'), 'Pantalón · Mujer · Talla 4 → 30 · Talla 6 → 20 · Total 50');
  assert.deepEqual(plain(R.chosenSizes(m.form, CATALOG, 'mujer')), [{ size: '4', quantity: 30 }, { size: '6', quantity: 20 }]);
  assert.match(html, /Limpiar/); assert.match(html, /Guardar referencia/);
});

test('estado: tres columnas (activas, visibles para bot, no visibles), buscador y género; por nombre y talla de menor a mayor', () => {
  const R = load();
  let c = R.columns(ROWS, EXTRAS, { gender: 'mujer' }, CATALOG);
  assert.deepEqual(plain(c.activas.map((r) => r.id)), ['aa', 'mj', 'mp', 'p10', 'p12'], 'lo no clasificado se ve en Mujer; por nombre y talla');
  assert.deepEqual(plain(c.visibles.map((r) => r.id)), ['mj', 'mp', 'p10']);
  assert.deepEqual(plain(c.noVisibles.map((r) => r.id)), ['aa', 'p12']);
  const tallas = [12, 10, 8, 6].map((n) => ({ id: `t${n}`, name: 'PANT SET', category: 'Pantalón', size: String(n), color: 'Marfil', bot_active: true }));
  assert.deepEqual(plain(R.columns(tallas, {}, { gender: 'mujer' }, CATALOG).activas.map((r) => r.size)), ['6', '8', '10', '12'], 'hoy salían 12, 10, 8, 6');
  c = R.columns(ROWS, EXTRAS, { gender: 'hombre' }, CATALOG);
  assert.equal(c.activas.length, 0, 'hombre funciona y hoy no tiene referencias');
  c = R.columns(ROWS, EXTRAS, { gender: 'mujer', search: 'pantalon' }, CATALOG);
  assert.deepEqual(plain(c.activas.map((r) => r.id)), ['p10', 'p12'], 'busca también por la prenda');
  c = R.columns(ROWS, EXTRAS, { gender: 'mujer', search: 'azul' }, CATALOG);
  assert.deepEqual(plain(c.activas.map((r) => r.id)), ['aa']);
});

test('orden de tallas: numéricas ascendentes y letras XS, S, M, L, XL, XXL (SM antes que ML), igual que el servidor', () => {
  const R = load();
  const sizes = ['12', '10', '8', '6', '4', 'XL', 'S', 'M', 'XS', 'XXL', 'L', 'ML', 'SM', '4, 6, 8, 10, 12'];
  assert.deepEqual(plain(sizes.slice().sort(R.bySize)), ['4', '4, 6, 8, 10, 12', '6', '8', '10', '12', 'XS', 'S', 'SM', 'M', 'ML', 'L', 'XL', 'XXL']);
  const g = R.groups([{ id: 'b', name: 'B', size: '12' }, { id: 'a12', name: 'A', size: '12' }, { id: 'a4', name: 'A', size: '4' }]);
  assert.deepEqual(plain(g.map((x) => x.name)), ['A', 'B'], 'selector de referencia por nombre');
  assert.deepEqual(plain(g[0].rows.map((r) => r.size)), ['4', '12'], 'y sus tallas de menor a mayor');
});

// Grupos como los devuelve /v2/groups (references_v2.build_groups): una
// referencia = nombre + color, una línea por talla, "solo corte" incluidas.
const GROUPS = [
  { key: 'auroraazul|azul', name: 'Aurora Azul', color: 'Azul', colors: ['Azul'], received: 36, produced: 9, meta: 0, pending: 0, percent: 25, solo_corte: ['S', 'M'], unsized_received: 0,
    cuts_by_date: [{ date: '2026-10-06', sizes: [{ size: 'S', quantity: 26 }, { size: 'M', quantity: 10 }], total: 36, last_at: null }],
    lines: [{ size: 'S', color: '', reference_id: null, solo_corte: true, anchor_id: 'aa', meta: 0, produced: 0, pending: 0, bot_active: false, received: 26, combined: false },
      { size: 'SM', color: 'Azul', reference_id: 'aa', solo_corte: false, anchor_id: null, meta: 0, produced: 9, pending: 0, bot_active: true, received: 0, combined: false },
      { size: 'M', color: '', reference_id: null, solo_corte: true, anchor_id: 'aa', meta: 0, produced: 0, pending: 0, bot_active: false, received: 10, combined: false }] },
  { key: 'mysticpant|', name: 'Mystic pant', color: '', colors: [], received: 0, produced: 114, meta: 114, pending: 0, percent: null, solo_corte: [], unsized_received: 0, cuts_by_date: [],
    lines: [{ size: '4, 6, 8, 10, 12', color: '', reference_id: 'mp', solo_corte: false, anchor_id: null, meta: 114, produced: 114, pending: 0, bot_active: true, received: 0, combined: true }] },
  { key: 'pantset|marfil', name: 'PANT SET', color: 'Marfil', colors: ['Marfil'], received: 50, produced: 0, meta: 50, pending: 50, percent: 0, solo_corte: [], unsized_received: 0,
    cuts_by_date: [{ date: '2026-10-06', sizes: [{ size: '10', quantity: 30 }], total: 30, last_at: '2026-10-06T15:00:00Z' }, { date: '2026-09-16', sizes: [{ size: '12', quantity: 20 }], total: 20, last_at: null }],
    lines: [{ size: '10', color: 'Marfil', reference_id: 'p10', solo_corte: false, anchor_id: null, meta: 30, produced: 0, pending: 30, bot_active: true, received: 30, combined: false },
      { size: '12', color: '', reference_id: 'p12', solo_corte: false, anchor_id: null, meta: 20, produced: 0, pending: 20, bot_active: false, received: 20, combined: false }] },
];
const ROWS_G = ROWS.map((r) => (r.id === 'aa' ? { ...r, size: 'SM', bot_active: true, channel: 'bot' } : r));

test('estado: una tarjeta por referencia (nombre + color) con una línea por talla; columnas filtran tallas', () => {
  const R = load();
  Object.assign(R.model, { extras: EXTRAS, groups: GROUPS });
  const c = R.groupColumns(GROUPS, { gender: 'mujer' }, CATALOG);
  assert.deepEqual(plain(c.activas.map((g) => g.name)), ['Aurora Azul', 'Mystic pant', 'PANT SET']);
  assert.deepEqual(plain(c.visibles.map((g) => [g.name, g.lines.map((l) => l.size)])), [['Aurora Azul', ['SM']], ['Mystic pant', ['4, 6, 8, 10, 12']], ['PANT SET', ['10']]]);
  assert.deepEqual(plain(c.noVisibles.map((g) => [g.name, g.lines.map((l) => l.size)])), [['PANT SET', ['12']]], '"solo corte" no es referencia todavía: solo en Activas');
  assert.deepEqual(plain(R.groupColumns(GROUPS, { gender: 'mujer', search: 'pantalon' }, CATALOG).activas.map((g) => g.name)), ['PANT SET'], 'busca por la prenda');
  assert.deepEqual(plain(R.groupColumns(GROUPS, { gender: 'mujer', search: ' sm' }, CATALOG).activas.map((g) => g.name)), ['Aurora Azul'], 'y por talla');
  assert.equal(R.groupColumns(GROUPS, { gender: 'hombre' }, CATALOG).activas.length, 0);
});

test('Aurora Azul: tarjeta con S, SM y M, recibido 36 y % = producido ÷ 36; "solo corte" con botón para crearla', () => {
  const R = load();
  const m = R.model;
  Object.assign(m, { catalog: CATALOG, rows: ROWS_G, extras: EXTRAS, groups: GROUPS, tab: 'estado', filterGender: 'mujer', search: '', modal: '', lastOpen: '' });
  const html = R.view();
  const aurora = html.slice(html.indexOf('data-rv-gopen="auroraazul|azul"'), html.indexOf('data-rv-gopen="mysticpant|"'));
  assert.deepEqual([...aurora.matchAll(/<b class="rv-gsize" role="cell">([^<]+)(?:<small[^>]*>[^<]*<\/small>)?<\/b>/g)].map((x) => x[1]), ['S', 'SM', 'M'], 'orden del catálogo');
  assert.match(aurora, /<small>Mujer · Azul · 3 tallas<\/small>/);
  assert.match(aurora, /Meta <b>0<\/b> · Recibido <b>36<\/b> · Producido <b>9<\/b> · Pendiente <b>0<\/b> · <b>25&nbsp;%<\/b>/, 'totales de la referencia');
  assert.match(aurora, /<b class="rv-gsize" role="cell">SM<small class="rv-gcolor">Azul<\/small><\/b>/, 'el color va en cada talla');
  assert.match(aurora, /--p:25%/);
  assert.match(aurora, /<b class="rv-gsize" role="cell">S<\/b><span role="cell" data-k="Meta">—<\/span><span role="cell" data-k="Recibido">26<\/span>/);
  assert.deepEqual([...html.matchAll(/data-rv-gopen="([^"]+)"/g)].map((x) => x[1]).filter((k, i, a) => a.indexOf(k) === i), ['auroraazul|azul', 'mysticpant|', 'pantset|marfil']);
  assert.equal((aurora.match(/<span class="rv-gbot" role="cell"><i class="rv-chip is-amber">solo corte<\/i><\/span>/g) || []).length, 2, '"solo corte" en la columna Bot, sin interruptor');
  assert.match(aurora, /data-rv-visible="aa" checked aria-label="Visible para bot talla SM"/, 'la talla con fila lleva interruptor del bot');
  assert.match(aurora, /data-rv-gcreate="auroraazul\|azul"[^>]*>Crear S y M<\/button>/, 'crear de una vez las tallas solo corte');
  assert.match(html, /data-rv-gbot="pantset\|marfil" data-rv-on="1">Todas visibles/, 'con alguna oculta: Todas visibles');
  assert.match(html, /data-rv-gbot="mysticpant\|" data-rv-on="0">Todas ocultas/, 'todas visibles: Todas ocultas');
  assert.match(aurora, /data-rv-gconfirm="auroraazul\|azul">Confirmar/, 'sugerencia de clasificación con un clic');
  assert.match(html, /<b>Mystic pant<\/b>.*<b class="rv-gsize" role="cell">4, 6, 8, 10, 12<\/b>/s, 'la fila combinada no se parte');
  assert.match(html, /Recibido <b>0<\/b> · Producido <b>114<\/b> · Pendiente <b>0<\/b> · <b>—<\/b>/, 'sin cortes: "—"');
  assert.match(html, /Enviada 1 a Bombón el 06\/10\/2026 \(fotos\)/, 'nota de Bombón de todas sus tallas');
  assert.doesNotMatch(html, /despliegue/i);
  assert.match(SRC, /Se crean con meta 0 y NO visibles para el bot/, 'crear de una vez: misma regla de "Crear referencia en talla N"');
  assert.match(SRC, /post\(`\/v2\/references\/\$\{encodeURIComponent\(l\.anchor_id\)\}\/add-size`, \{ size: l\.size \}\)/, 'usa el endpoint que ya existe');
  assert.match(SRC, /confirm\(`¿\$\{on \? "Hacer visibles" : "Ocultar"\} para el bot/, 'visibles/ocultas con confirmación');
  assert.equal(R.nextChannel(ROWS[1], true), 'both', 'sistema + bot');
  assert.equal(R.nextChannel(ROWS[0], false), 'system');
  assert.deepEqual(plain(R.rowPayload(ROWS[0], { channel: 'system' })), { category: 'Pantalón', name: 'PANT SET', size: '10', color: 'Marfil', sku: '', unit_price: 0, initial_quantity: 30, channel: 'system' });
});

test('emergente: todas las tallas (meta y bot por talla, reiniciar y archivar por talla), avisa cambios y cierra marcando la tarjeta', () => {
  const R = load();
  const m = R.model;
  Object.assign(m, { catalog: CATALOG, rows: ROWS_G, extras: EXTRAS, groups: GROUPS, tab: 'estado', filterGender: 'mujer', search: '', modal: '', gdraft: null, lastOpen: '' });
  assert.equal(R.openGroupModal('pantset|marfil'), true);
  let html = R.view();
  assert.match(html, /role="dialog" aria-modal="true"/);
  assert.match(html, /data-rv-gm-meta="p10" value="30"/); assert.match(html, /data-rv-gm-meta="p12" value="20"/);
  assert.match(html, /<span class="rv-gmcolor">Color <b>Marfil<\/b><\/span>/, 'talla con color: se muestra');
  assert.match(html, /data-rv-gm-color="p12" value="" maxlength="60" placeholder="Escribe el color"/, 'talla sin color: se puede escribir');
  assert.match(html, /<span>Pendiente <b>30<\/b><\/span>/);
  assert.match(html, /data-rv-gmeta="pantset\|marfil">Igualar meta a lo recibido/);
  assert.match(html, /Cortes por fecha.*06\/10\/2026.*10 <b>30<\/b>.*16\/09\/2026.*12 <b>20<\/b>.*Total recibido<\/span><span><\/span><b>50<\/b>/s, 'del más reciente al más viejo y total general');
  assert.match(html, /data-rv-gm-bot="p10" checked/); assert.match(html, /data-rv-gm-bot="p12"\s+aria-label/);
  assert.match(html, /data-rv-reset="p10">Reiniciar ciclo<\/button><button type="button" class="rv-btn is-small" data-rv-archive="p10">Archivar/);
  assert.match(html, /data-rv-reset="p12">Reiniciar ciclo/);
  assert.match(html, /<option value="pantalon" selected>Pantalón<\/option>/, 'prenda actual');
  assert.match(html, /data-rv-modal-close aria-label="Cerrar">✕/);
  R.openGroupModal('auroraazul|azul');
  assert.match(R.view(), /data-rv-gaddsize="S" data-rv-anchor="aa" data-rv-gname="Aurora Azul">Crear referencia en talla S/, 'las "solo corte" también se crean desde aquí');
  R.openGroupModal('pantset|marfil');
  assert.equal(R.groupDirty(), false);
  m.gdraft.p12.color = 'Marfil';
  assert.equal(R.groupDirty(), true, 'escribir el color cuenta como cambio');
  m.gdraft.p12.color = '';
  m.gdraft.p12.meta = '25';
  assert.equal(R.groupDirty(), true);
  let asked = '';
  assert.equal(R.closeModal((msg) => { asked = msg; return false; }), false, 'con cambios, avisa y no cierra si dicen que no');
  assert.match(asked, /cambios sin guardar/);
  assert.equal(R.closeModal(() => true), true);
  assert.equal(m.modal, ''); assert.equal(m.lastOpen, 'g:pantset|marfil');
  assert.match(R.view(), /class="rv-card rv-gcard  is-last">\s*<button type="button" class="rv-card-head" data-rv-gopen="pantset\|marfil"/, 'la tarjeta abierta queda marcada');
  assert.match(SRC, /confirm\(`Reiniciar ciclo de esta referencia con meta \$\{total\}\? El historial anterior queda guardado y el conteo activo empieza en cero\.`\)/, 'misma confirmación de hoy');
  assert.match(SRC, /confirm\("¿Archivar esta referencia\? No se borrará físicamente\."\)/);
  assert.match(SRC, /method: "PATCH", body: JSON\.stringify\(rowPayload\(r, \{ initial_quantity: num\(d\.meta\), channel: nextChannel\(r, d\.visible\) \}\)\)/, 'guarda con el endpoint de siempre');
  assert.match(SRC, /rowPayload\(model\.rows\.find\(\(x\) => x\.id === r\.id\) \|\| r, \{ color: String\(d\.color\)\.trim\(\) \}\)/, 'el color: PATCH de siempre, solo ese campo');
  assert.match(SRC, /post\("\/v2\/groups\/meta-sync", \{ key, apply: false \}\)/, 'igualar meta: primero el antes/después');
  assert.match(SRC, /Igualar la meta a lo recibido en cortes:/, 'y pide confirmación');
  assert.match(SRC, /event\.key !== "Escape"/, 'se cierra con Esc');
  assert.match(SRC, /t\.matches\("\[data-rv-overlay\]"\)/, 'y tocando fuera');
});

// Mismo caso que tests/test_references_op_order_pg.py (servidor): misma fórmula, mismas cifras.
const ITEMS = [{ id: 'a', name: 'Corte', minutes: 25, size: '' }, { id: 'b', name: 'Costura', minutes: 60, size: '' },
  { id: 'c', name: 'Botones', minutes: 27, size: '' }, { id: 'd', name: 'Bolsillo', minutes: 5, size: 'M' }];
const LINES = [{ size: 'S', received: 26, produced: 0 }, { size: 'SM', received: 0, produced: 9 }, { size: 'M', received: 10, produced: 0 }];

test('orden operacional: 112 min, $24.000, 25 min = 22,3 % = $5.357; "solo M" suma a M (117); la suma da exacta; orden 68h 02m', () => {
  const R = load();
  const c = R.opCalc(ITEMS, 24000, LINES);
  assert.equal(c.minutes, 112);
  assert.deepEqual(plain(c.items.map((i) => [i.percent, i.value])), [[22.3, 5357], [53.6, 12857], [24.1, 5786], [null, null]]);
  assert.equal(c.items.reduce((a, i) => a + (i.value || 0), 0), 24000, 'el último ítem absorbe el redondeo');
  assert.equal(c.order_minutes, 26 * 112 + 10 * 117); assert.equal(c.order_label, '68h 02m');
  assert.deepEqual(plain(c.per_size.map((s) => [s.size, s.minutes])), [['S', 112], ['SM', 112], ['M', 117]]);
  assert.deepEqual(plain(c.extra_sizes), ['M']);
  assert.equal(c.received, 36); assert.equal(c.percent, 25);
  const mView = R.opCalc(ITEMS, 24000, LINES, 'M');
  assert.equal(mView.minutes, 117);
  assert.equal(mView.items.reduce((a, i) => a + (i.value || 0), 0), 24000);
  assert.equal(R.hm(4082), '68h 02m');
  assert.equal(R.money(5357), '$ 5.357', 'COP sin centavos (formato de siempre)');
  assert.equal(R.opCalc([], 24000, LINES).value_per_minute, null, 'sin ítems no divide por cero');
});

test('orden operacional: pantalla entre Cortes y Estado, indicadores, tallas, ítems y "+ Agregar ítem"', () => {
  const R = load();
  const m = R.model;
  Object.assign(m, { catalog: CATALOG, rows: ROWS_G, extras: EXTRAS, groups: GROUPS, tab: 'orden', modal: '' });
  m.op.key = 'auroraazul|azul'; m.op.view = '';
  R.setOp({ group: GROUPS[0], settings: { value_per_garment: 24000 }, calc: { items: ITEMS } });
  let html = R.view();
  assert.deepEqual([...html.matchAll(/data-rv-tab="(\w+)"/g)].map((x) => x[1]), ['catalogo', 'cortes', 'orden', 'estado'], 'Catálogo → Cortes → Orden operacional → Estado');
  // Diseño aprobado: seis indicadores con etiqueta, cifra y detalle.
  assert.match(html, /<small>Tiempo por prenda<\/small><b>1h 52m<\/b><small class="is-detail">Talla M: 1h 57m<\/small>/, 'y por talla cuando tiene ítems extra');
  assert.match(html, /<small>Valor por prenda<\/small><b>\$ 24\.000<\/b><small class="is-detail">igual para todas las tallas<\/small>/);
  assert.match(html, /<small>Valor por minuto<\/small><b>\$ 214<\/b><small class="is-detail">sobre 112 min<\/small>/);
  assert.match(html, /<small>Cortes recibidos<\/small><b>36<\/b><small class="is-detail">S 26 · M 10<\/small>/);
  assert.match(html, /<small>Producido<\/small><b>9 · 25&nbsp;%<\/b><small class="is-detail">producido ÷ recibido<\/small>/);
  assert.match(html, /<small>Tiempo de la orden<\/small><b>68h 02m<\/b><small class="is-detail">36 prendas<\/small>/);
  assert.match(html, /<div class="rv-op-tile is-cut"><b>S<\/b><strong>26<\/strong><small>solo corte<\/small><\/div><div class="rv-op-tile "><b>SM<\/b><strong>0<\/strong><small>referencia<\/small>/);
  assert.match(html, /Avance · 9 de 36/);
  assert.match(html, /<span class="rv-op-name">Corte<\/span><span>0h 25m<\/span><span><i class="rv-pill ">Todas<\/i><\/span>\s*<span class="rv-op-pct"><i class="rv-op-bar-mini" style="--p:22\.3%"><\/i>22,3&nbsp;%<\/span><span class="rv-op-val">\$ 5\.357<\/span>/);
  assert.match(html, /<div class="rv-op-row is-off" role="row"><span class="rv-op-name">Bolsillo<\/span><span>0h 05m<\/span><span><i class="rv-pill is-size">Solo M<\/i><\/span>\s*<span class="rv-op-pct">—<\/span>/, 'el ítem de otra talla no suma a "Todas"');
  assert.match(html, /data-rv-op-editbtn="a" aria-label="Editar Corte"[^>]*>✎/);
  assert.match(html, /Total por prenda \(todas las tallas\)<\/span><b>1h 52m · \$ 24\.000 · 100&nbsp;%<\/b>/);
  assert.match(html, /Nuevo ítem<input data-rv-op-new="name"/);
  assert.match(html, /data-rv-op-add[^>]*>\+ Agregar ítem/);
  assert.match(html, /<select data-rv-op-view><option value="">Todas<\/option><option value="S" >S<\/option><option value="SM" >SM<\/option><option value="M" >M<\/option>/);
  assert.match(html, /data-rv-op-value value="\$ 24\.000"/, 'el valor se ve con el formato de la moneda');
  m.op.editing = 'a'; m.op.edit = { name: 'Corte', hours: '0', minutes: '25', size: '' };
  html = R.view();
  assert.match(html, /data-rv-op-move="a" data-rv-dir="-1" disabled/); assert.match(html, /data-rv-op-del="a">Eliminar/);
  m.op.editing = ''; m.op.edit = null;
  m.op.view = 'M';
  html = R.view();
  assert.match(html, /<small>Tiempo por prenda<\/small><b>1h 57m<\/b><small class="is-detail">talla M<\/small>/);
  assert.match(html, /Total por prenda \(talla M\)<\/span><b>1h 57m · \$ 24\.000 · 100&nbsp;%<\/b>/);
  assert.match(SRC, /confirm\(`¿Eliminar el ítem "\$\{i\.name\}"/, 'eliminar pide confirmación');
});

test('agrupación: la misma clave que el servidor (mayúsculas, tildes y espacios no cuentan)', () => {
  const R = load();
  assert.equal(R.groupKey('  Aurora  Azul '), 'auroraazul');
  assert.equal(R.groupKey('Lucky Coat'), R.groupKey('lucky  coat'), 'Lucky Coat con dos colores es una sola referencia');
  assert.equal(R.groupKey('Aurora Café'), R.groupKey('aurora cafe'));
  const g = R.groups([{ id: '1', name: 'Aurora Cafe', category: 'Superior', size: 'SM', color: 'Café' }, { id: '2', name: 'aurora  cafe', category: 'Chaqueta', size: 'ML', color: 'cafe' }]);
  assert.equal(g.length, 1, 'Cortes agrupa igual que Estado y Orden operacional (la categoría no separa)');
  const lucky = R.groups([{ id: 'l1', name: 'Lucky Coat', size: 'ML', color: '' }, { id: 'l2', name: 'lucky coat', size: 'SM', color: 'verde oliva' }]);
  assert.equal(lucky.length, 1, 'un grupo aunque tenga dos colores');
  assert.match(readFileSync('app/services/references_v2.py', 'utf8'), /return re\.sub\(r"\\s\+", "", _fold\(name\)\)/);
});

test('cortes: todas las tallas de la prenda; las que no existen como referencia se marcan y su corte va a la referencia', () => {
  const R = load();
  const rows = [{ id: 'p4', name: 'PANT SET', category: 'Pantalón', size: '4', color: 'Marfil' }, { id: 'p6', name: 'PANT SET', category: 'Pantalón', size: '6', color: 'Marfil' }];
  const pant = R.groups(rows)[0];
  const bal = { reference: { id: 'p4', name: 'PANT SET', color: 'Marfil' }, classified: true, catalog_sizes: ['4', '6', '8', '10', '12', '14', '16'], existing_sizes: ['4', '6'] };
  const sizes = plain(R.groupSizes(pant, bal));
  assert.deepEqual(sizes.map((s) => [s.size, s.exists, s.id]), [['4', true, 'p4'], ['6', true, 'p6'], ['8', false, 'p4'], ['10', false, 'p4'], ['12', false, 'p4'], ['14', false, 'p4'], ['16', false, 'p4']]);
  assert.deepEqual(plain(R.groupSizes(pant, { ...bal, classified: false, catalog_sizes: [] }).map((s) => s.size)), ['4', '6'], 'sin clasificar: sus tallas actuales');
  const mystic = R.groups(ROWS).find((x) => x.name === 'Mystic pant');
  assert.deepEqual(plain(R.groupSizes(mystic).map((s) => s.size)), ['4', '6', '8', '10', '12'], 'una combinada se elige por talla sin partir la fila');
  const m = R.model;
  Object.assign(m, { rows, catalog: CATALOG, tab: 'cortes', balance: { ...bal, received: 9, novelty: 0, deployed: 0, available: 9, received_by_date: [{ date: '2026-10-06', quantity: 9 }],
    log: [{ id: 'x8', kind: 'ingreso', size: '8', quantity: 6, event_date: '2026-10-06', size_without_reference: true }, { id: 'x12', kind: 'ingreso', size: '12', quantity: 3, event_date: '2026-10-06', size_without_reference: true }] } });
  m.cut = { refId: 'p4', date: '2026-10-06', received: { 8: '6', 12: '3', 4: '2' }, novelties: {}, deploy: { quantity: '', size: '', date: '2026-10-06' } };
  assert.deepEqual(plain(R.cutItems()).map((i) => [i.size, i.reference_id]), [['4', 'p4'], ['8', 'p4'], ['12', 'p4']], 'la talla 8 y 12 se guardan con la referencia (sin crearla)');
  const html = R.view();
  assert.match(html, /class="rv-size-btn is-on is-new" data-rv-recv="8"/, 'talla sin referencia: borde punteado');
  assert.match(html, /class="rv-size-btn is-on " data-rv-recv="4"/);
  assert.match(html, /data-rv-addsize="8">Crear referencia en talla 8<\/button><button type="button" class="rv-btn is-small" data-rv-addsize="12">Crear referencia en talla 12/);
  assert.match(SRC, /meta 0 y NO visible para el bot/);
  const unclassified = R.view.call(null);
  assert.ok(unclassified);
  m.balance = { ...m.balance, classified: false, catalog_sizes: [] };
  assert.match(R.view(), /Esta referencia no está clasificada/);
});

test('cortes: Bombón, recuadro de cortes recibidos y bitácora agrupada por fecha', () => {
  const R = load();
  const rows = [{ id: 'p10', name: 'PANT SET', category: 'Pantalón', size: '10', color: 'Marfil' }, { id: 'p12', name: 'PANT SET', category: 'Pantalón', size: '12', color: 'Marfil' }];
  const log = [
    { id: 'a', kind: 'ingreso', size: '12', quantity: 3, event_date: '2026-10-06' }, { id: 'b', kind: 'ingreso', size: '4', quantity: 8, event_date: '2026-10-06' },
    { id: 'c', kind: 'ingreso', size: '10', quantity: 4, event_date: '2026-10-06' }, { id: 'd', kind: 'novedad', section: 'corte', quantity: 1, note: 'pieza mal cortada', event_date: '2026-10-06' },
    { id: 'e', kind: 'despliegue', size: '10', quantity: 1, event_date: '2026-10-06' }, { id: 'f', kind: 'ingreso', size: '6', quantity: 42, event_date: '2026-09-16' },
    { id: 'g', kind: 'ingreso', size: '8', quantity: 9, event_date: '2026-09-16', voided_at: '2026-09-17', void_reason: 'doble' }];
  const days = plain(R.groupLog(log));
  assert.deepEqual(days.map((d) => [d.date, d.totalIngreso]), [['2026-10-06', 15], ['2026-09-16', 42]], 'la más reciente arriba; los anulados no suman');
  assert.deepEqual(days[0].ingresos.map((m) => m.size), ['4', '10', '12'], 'tallas juntas y ordenadas');
  const box = plain(R.receivedBox({ received_by_date: [{ date: '2026-09-16', quantity: 42 }, { date: '2026-10-06', quantity: 29 }], available: 60 }));
  assert.equal(box.total, 71); assert.equal(box.lines.reduce((a, l) => a + l.quantity, 0), box.total, 'suma por fecha = total recibido');
  const m = R.model;
  Object.assign(m, { rows, catalog: CATALOG, tab: 'cortes', logOpen: {} });
  m.cut = { refId: 'p10', date: '2026-10-06', received: {}, novelties: {}, deploy: { quantity: '', size: '', date: '2026-10-06' } };
  m.balance = { reference: { id: 'p10' }, classified: true, catalog_sizes: ['4', '6', '8', '10', '12', '14', '16'], received: 71, novelty: 3, deployed: 1, available: 67,
    received_by_date: [{ date: '2026-09-16', quantity: 42 }, { date: '2026-10-06', quantity: 29 }], log };
  let html = R.view();
  assert.match(html, /<i>3<\/i>Enviado a Bombón<\/h2><p class="client-muted rv-step-sub">Prenda terminada para fotos<\/p>/);
  assert.match(html, /<small>A Bombón<\/small>/); assert.match(html, /Disponible = recibido − novedades − Bombón/);
  assert.doesNotMatch(html, /despliegue/i, 'el texto visible ya no dice despliegue');
  assert.match(html, /<li><span>16\/09\/2026<\/span><b>42<\/b><\/li><li><span>06\/10\/2026<\/span><b>29<\/b><\/li>\s*<li class="is-total"><span>Total recibido · disponible 67<\/span><b>71<\/b>/, 'el disponible solo en el total');
  assert.match(html, /data-rv-logday="2026-10-06" aria-expanded="true"><span><b>06\/10\/2026<\/b> · Ingreso de corte · total 15<\/span><i aria-hidden="true">▾/, 'la más reciente desplegada');
  assert.match(html, /data-rv-logday="2026-09-16" aria-expanded="false"><span><b>16\/09\/2026<\/b> · Ingreso de corte · total 42<\/span><i aria-hidden="true">▸/, 'las demás plegadas');
  assert.match(html, /<b>Tallas<\/b> 4→8 · 10→4 · 12→3/);
  assert.match(html, /<b>Corte<\/b> · 1 · pieza mal cortada/); assert.match(html, /<b>Enviado a Bombón<\/b> · talla 10 · 1/);
  m.logOpen = { '2026-10-06': false, '2026-09-16': true };
  html = R.view();
  assert.match(html, /data-rv-logday="2026-10-06" aria-expanded="false"/); assert.match(html, /data-rv-logday="2026-09-16" aria-expanded="true"/);
  assert.match(html, /Ingreso talla 8 → 9<\/span><small>Anulado: doble/, 'el anulado se conserva en el historial');
  m.logOpen = {}; m.voiding = 'in:2026-10-06';
  assert.match(R.view(), /data-rv-ids="b,c,a" data-rv-label="los ingresos de las tallas 4, 10, 12 del 06\/10\/2026"/, 'anular un grupo dice qué tallas afecta');
  assert.match(SRC, /if \(ids\.length > 1 && !confirm\(`Se anulan \$\{el\.getAttribute\("data-rv-label"\)\}/, 'y pide confirmación');
  m.voiding = '';
});

test('client.js: solo el enganche; con el interruptor apagado se sirve la pantalla de siempre', () => {
  const src = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');
  const start = src.indexOf('function cxReferencesV2On050B');
  const fn = src.slice(start, src.indexOf('\n  }\n', start) + 4);
  const on = (settings) => vm.runInNewContext(`${fn}; cxReferencesV2On050B("references")`, {
    activeClientModules: () => [{ code: 'references', raw: { settings } }],
  });
  assert.equal(on({}), false, 'apagado por defecto');
  assert.equal(on({ references_v2: false }), false);
  assert.equal(on({ references_v2: 'true' }), false, 'solo true de verdad');
  assert.equal(on({ references_v2: true }), true);
  assert.match(src, /if \(cxReferencesV2On050B\(activeReferencesNavCode022E\) && await cxReferencesV2Mount050B\(activeReferencesNavCode022E\)\) return;/);
  assert.match(src, /try \{ await cxReferencesV2Load050B\(\); \} catch \(_\) \{ return false; \}/, 'si el archivo no carga, la de siempre');
  const html = readFileSync('app/web/client.html', 'utf8');
  assert.doesNotMatch(html, /references_v2/, 'client.html no cambia: el archivo se carga solo con el interruptor');
  const registry = JSON.parse(readFileSync('app/services/switch_registry.json', 'utf8'));
  const sw = registry.switches.find((s) => s.key === 'references_v2');
  assert.equal(sw.module, 'references');
});

test('diseño: botones de 44 px, listas con desplazamiento interno y celular', () => {
  const css = readFileSync('app/web/references_v2.css', 'utf8');
  assert.match(css, /\.rv-scroll \{ max-height: min\(70vh, 760px\); overflow-y: auto;/);
  assert.match(css, /\.rv-btn \{ min-height: 44px; min-width: 44px;/);
  assert.match(css, /\.rv-size-btn \{ height: 40px;/, 'tallas: fichas de 40 px');
  assert.match(css, /\.rv-kpis \{ display: grid; grid-template-columns: repeat\(auto-fit, minmax\(124px, 1fr\)\)/, 'balance: 2 x 2 si no cabe');
  assert.match(css, /\.rv-tab \{ min-height: 44px;/);
  assert.match(css, /@media \(max-width: 720px\)/);
  assert.doesNotMatch(SRC, /<img|data:image|\.png|\.jpg/, 'sin imágenes: SVG en el código');
});

test('tema: references_v2.css no tiene colores fijos; todo sale de las variables del portal', () => {
  const css = readFileSync('app/web/references_v2.css', 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
  // Única excepción: los respaldos semánticos de éxito, alerta y peligro cuando la marca no los trae.
  const SEMANTIC = /var\(--cx-(success|warning|danger),\s*#[0-9a-f]{3,8}\)/gi;
  assert.equal((css.match(SEMANTIC) || []).length, 3, 'solo los tres respaldos semánticos');
  const rest = css.replace(SEMANTIC, '');
  const NEUTRAL = /^(#fff|#ffffff|#000|#000000|rgba?\(\s*(0\s*,\s*0\s*,\s*0|255\s*,\s*255\s*,\s*255)\s*(,\s*[\d.]+\s*)?\))$/i;
  const found = rest.match(/#[0-9a-f]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)/gi) || [];
  // Colores relativos al tema (rgb(from var(--cx-…))) no son fijos.
  const bad = found.filter((c) => !NEUTRAL.test(c.trim()) && !c.trim().toLowerCase().startsWith('rgb(from var(--cx-'));
  assert.deepEqual(bad, [], `colores fijos: ${bad.join(', ')}`);
  for (const v of ['--cx-primary', '--cx-secondary', '--cx-text', '--cx-bg']) assert.ok(css.includes(`var(${v})`), v);
  assert.doesNotMatch(css, /\.rv-root \{[^}]*(background|border-radius|padding)\s*:/, 'sin recuadro propio');
  assert.doesNotMatch(css, /[{;]\s*max-width:\s*\d/, 'sin ancho máximo propio (los @media no cuentan)');
  assert.match(css, /scrollbar-width: thin/);
  const js = readFileSync('app/web/references_v2.js', 'utf8');
  assert.match(js, /class="client-hero rv-head"/); assert.match(js, /class="client-panel rv-panel/);
  assert.match(js, /client-btn rv-btn is-primary/); assert.match(js, /"client-btn is-on"/);
  assert.doesNotMatch(js, /setProperty\("--rv-/, 'sin pintura de marca propia');
  assert.match(readFileSync('app/web/client.js', 'utf8'), /references_v2\.js\?v=053A/);
});
