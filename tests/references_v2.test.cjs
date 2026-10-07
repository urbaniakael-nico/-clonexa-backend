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
  assert.deepEqual(plain(R.sizesFor(CATALOG, 'mujer', 'blusa')), ['XS', 'S', 'M', 'L', 'XL', 'XXL']);
  assert.deepEqual(plain(R.sizesFor(CATALOG, 'mujer', 'ropa_interior')), ['XS', 'S', 'M', 'L', 'XL', 'XXL']);
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

test('estado: tres columnas (activas, visibles para bot, no visibles), buscador y género', () => {
  const R = load();
  let c = R.columns(ROWS, EXTRAS, { gender: 'mujer' }, CATALOG);
  assert.deepEqual(plain(c.activas.map((r) => r.id)), ['p10', 'p12', 'mj', 'mp', 'aa'], 'lo no clasificado se ve en Mujer');
  assert.deepEqual(plain(c.visibles.map((r) => r.id)), ['p10', 'mj', 'mp']);
  assert.deepEqual(plain(c.noVisibles.map((r) => r.id)), ['p12', 'aa']);
  c = R.columns(ROWS, EXTRAS, { gender: 'hombre' }, CATALOG);
  assert.equal(c.activas.length, 0, 'hombre funciona y hoy no tiene referencias');
  c = R.columns(ROWS, EXTRAS, { gender: 'mujer', search: 'pantalon' }, CATALOG);
  assert.deepEqual(plain(c.activas.map((r) => r.id)), ['p10', 'p12'], 'busca también por la prenda');
  c = R.columns(ROWS, EXTRAS, { gender: 'mujer', search: 'azul' }, CATALOG);
  assert.deepEqual(plain(c.activas.map((r) => r.id)), ['aa']);
});

test('tarjetas: tallas combinadas tal cual, por clasificar con sugerencia, nota de despliegue y acciones', () => {
  const R = load();
  const m = R.model;
  Object.assign(m, { catalog: CATALOG, rows: ROWS, extras: EXTRAS, tab: 'estado', filterGender: 'mujer', search: '' });
  let html = R.view();
  assert.match(html, /<b>Mystic pant<\/b><small>Sin categoría · 4, 6, 8, 10, 12 <i class="rv-chip is-amber">Tallas combinadas<\/i><\/small>/, 'la fila combinada no se parte; la etiqueta va junto a sus tallas');
  assert.match(html, /Tallas combinadas/);
  assert.match(html, /<b>PANT SET · talla 10<\/b><small>Pantalón · Mujer · Marfil<\/small>/);
  assert.match(html, /Por clasificar/);
  assert.match(html, /<p class="rv-sug"><span><i class="rv-chip is-cyan">Por clasificar<\/i> Sugerencia: <b>Chaqueta · Mujer<\/b><\/span><button[^>]*data-rv-confirm="mj"/, 'misma línea; se confirma con un clic; nunca sola');
  assert.match(html, /Enviada 1 a despliegue el 06\/10\/2026 \(fotos\)/);
  assert.match(html, /Meta <b>126<\/b>.*Producido <b>126<\/b>.*Pendiente <b>0<\/b>/s);
  m.open = 'No visibles:p12';
  html = R.view();
  assert.match(html, /Hacer visible para bot/);
  for (const b of ['Editar', 'Reiniciar ciclo', 'Archivar']) assert.match(html, new RegExp(`>${b}</button>`));
  assert.match(SRC, /confirm\(`Reiniciar ciclo de esta referencia con meta \$\{total\}\? El historial anterior queda guardado y el conteo activo empieza en cero\.`\)/, 'misma confirmación de hoy');
  assert.match(SRC, /confirm\("¿Archivar esta referencia\? No se borrará físicamente\."\)/);
  assert.equal(R.nextChannel(ROWS[1], true), 'both', 'sistema + bot');
  assert.equal(R.nextChannel(ROWS[0], false), 'system');
  assert.deepEqual(plain(R.rowPayload(ROWS[0], { channel: 'system' })), { category: 'Pantalón', name: 'PANT SET', size: '10', color: 'Marfil', sku: '', unit_price: 0, initial_quantity: 30, channel: 'system' });
});

test('cortes: tallas de la referencia (una combinada se elige por talla sin partir la fila) y movimientos del registro', () => {
  const R = load();
  const g = R.groups(ROWS);
  const pant = g.find((x) => x.name === 'PANT SET');
  assert.deepEqual(plain(R.groupSizes(pant)), [{ size: '10', id: 'p10' }, { size: '12', id: 'p12' }]);
  const mystic = g.find((x) => x.name === 'Mystic pant');
  assert.deepEqual(plain(R.groupSizes(mystic).map((s) => s.size)), ['4', '6', '8', '10', '12']);
  assert.ok(R.groupSizes(mystic).every((s) => s.id === 'mp'));
  const m = R.model;
  m.rows = ROWS;
  m.cut = { refId: 'p10', date: '2026-10-06', received: { 10: '30', 12: '20' }, novelties: { corte: { note: 'Pieza mal cortada en talla 12', quantity: '1' }, bordado: { note: 'Falta el logo', quantity: '2' } },
    deploy: { quantity: '1', size: '10', date: '2026-10-06' } };
  const items = plain(R.cutItems());
  assert.deepEqual(items.map((i) => [i.kind, i.section || '', i.size || '', i.quantity, i.reference_id]), [
    ['ingreso', '', '10', 30, 'p10'], ['ingreso', '', '12', 20, 'p12'], ['novedad', 'corte', '', 1, 'p10'], ['novedad', 'bordado', '', 2, 'p10'], ['despliegue', '', '10', 1, 'p10']]);
  m.tab = 'cortes'; m.catalog = CATALOG;
  m.balance = { received: 50, novelty: 3, deployed: 1, available: 46, log: [] };
  const html = R.view();
  assert.match(html, /<div class="is-k-recv"><b>50<\/b>/); assert.match(html, /<div class="is-k-av"><b>46<\/b>/);
  assert.match(html, /<b class="rv-nowrap">92&nbsp;%<\/b>/, '92 % sin partirse');
  assert.match(html, /<h2 class="client-eyebrow rv-step is-violet"><i>3<\/i>Enviado a despliegue<\/h2><p class="client-muted rv-step-sub">Prenda terminada para fotos<\/p>/);
  for (const s of ['Corte', 'Bordado', 'Taller', 'Lavado', 'Otro']) assert.match(html, new RegExp(`<i></i>${s}</span>`));
  assert.doesNotMatch(html, /pieza<\/label>/i, 'sin campo pieza');
  assert.match(html, /El número <b>producido<\/b> no se toca/);
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
  assert.match(readFileSync('app/web/client.js', 'utf8'), /references_v2\.js\?v=050D/);
});
