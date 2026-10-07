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

test('tarjetas: tallas combinadas tal cual, por clasificar con sugerencia, nota de Bombón; al tocar abre el emergente', () => {
  const R = load();
  const m = R.model;
  Object.assign(m, { catalog: CATALOG, rows: ROWS, extras: EXTRAS, tab: 'estado', filterGender: 'mujer', search: '' });
  let html = R.view();
  assert.match(html, /<b>Mystic pant<\/b><small>Sin categoría · 4, 6, 8, 10, 12 <i class="rv-chip is-amber">Tallas combinadas<\/i><\/small>/, 'la fila combinada no se parte; la etiqueta va junto a sus tallas');
  assert.match(html, /<b>PANT SET · talla 10<\/b><small>Pantalón · Mujer · Marfil<\/small>/);
  assert.match(html, /<p class="rv-sug"><span><i class="rv-chip is-cyan">Por clasificar<\/i> Sugerencia: <b>Chaqueta · Mujer<\/b><\/span><button[^>]*data-rv-confirm="mj"/, 'misma línea; se confirma con un clic; nunca sola');
  assert.match(html, /Enviada 1 a Bombón el 06\/10\/2026 \(fotos\)/);
  assert.doesNotMatch(html, /despliegue/i, 'solo cambia el texto visible: "Bombón"');
  assert.match(html, /Meta <b>126<\/b>.*Producido <b>126<\/b>.*Pendiente <b>0<\/b>/s);
  assert.match(html, /data-rv-open="p12" aria-haspopup="dialog"/);
  assert.match(SRC, /confirm\(`Reiniciar ciclo de esta referencia con meta \$\{total\}\? El historial anterior queda guardado y el conteo activo empieza en cero\.`\)/, 'misma confirmación de hoy');
  assert.match(SRC, /confirm\("¿Archivar esta referencia\? No se borrará físicamente\."\)/);
  assert.equal(R.nextChannel(ROWS[1], true), 'both', 'sistema + bot');
  assert.equal(R.nextChannel(ROWS[0], false), 'system');
  assert.deepEqual(plain(R.rowPayload(ROWS[0], { channel: 'system' })), { category: 'Pantalón', name: 'PANT SET', size: '10', color: 'Marfil', sku: '', unit_price: 0, initial_quantity: 30, channel: 'system' });
});

test('emergente: abre con los datos actuales, avisa cambios sin guardar, cierra y deja la tarjeta marcada', () => {
  const R = load();
  const m = R.model;
  Object.assign(m, { catalog: CATALOG, rows: ROWS, extras: EXTRAS, tab: 'estado', filterGender: 'mujer', search: '', modal: '', draft: null, lastOpen: '' });
  assert.equal(R.openModal('p12'), true);
  m.modalBalance = { log: [{ kind: 'ingreso', size: '12', quantity: 20, event_date: '2026-10-06' }, { kind: 'ingreso', size: '10', quantity: 30, event_date: '2026-10-06' },
    { kind: 'ingreso', size: '12', quantity: 5, event_date: '2026-09-16', voided_at: '2026-09-17' }] };
  let html = R.view();
  assert.match(html, /role="dialog" aria-modal="true"/);
  assert.match(html, /data-rv-m="name" value="PANT SET"/); assert.match(html, /data-rv-m="color" value="Marfil"/);
  assert.match(html, /data-rv-m="size" value="12"/); assert.match(html, /data-rv-m="initial_quantity" type="number" min="0" inputmode="numeric" value="20"/);
  assert.match(html, /<option value="pantalon" selected>Pantalón<\/option>/, 'prenda actual');
  assert.match(html, /data-rv-m="visible" >/, 'no visible para bot');
  assert.match(html, /<li><span>06\/10\/2026<\/span><b>20<\/b><\/li><li class="is-total"><span>Total recibido<\/span><b>20<\/b>/, 'solo los cortes de su talla, sin anulados');
  for (const b of ['Guardar', 'Reiniciar ciclo', 'Archivar']) assert.match(html, new RegExp(`>${b}</button>`));
  assert.match(html, /data-rv-modal-close aria-label="Cerrar">✕/);
  assert.equal(R.isDirty(), false);
  m.draft.initial_quantity = '25';
  assert.equal(R.isDirty(), true);
  let asked = '';
  assert.equal(R.closeModal((msg) => { asked = msg; return false; }), false, 'con cambios, avisa y no cierra si dicen que no');
  assert.match(asked, /cambios sin guardar/);
  assert.equal(m.modal, 'p12');
  assert.equal(R.closeModal(() => true), true);
  assert.equal(m.modal, ''); assert.equal(m.lastOpen, 'p12');
  assert.match(R.view(), /class="rv-card  is-last"><button type="button" class="rv-card-head" data-rv-open="p12"/, 'la tarjeta abierta queda marcada');
  assert.match(SRC, /event\.key !== "Escape"/, 'se cierra con Esc');
  assert.match(SRC, /t\.matches\("\[data-rv-overlay\]"\)/, 'y tocando fuera');
  assert.match(SRC, /method: "PATCH", body: JSON\.stringify\(rowPayload\(r, \{ name: d\.name\.trim\(\)/, 'guarda con el endpoint de siempre');
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
  assert.match(readFileSync('app/web/client.js', 'utf8'), /references_v2\.js\?v=050E/);
});
