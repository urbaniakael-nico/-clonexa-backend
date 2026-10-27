// Consola v2+ · Menú video: los 5 pasos, la tabla editable, emparejar fotos,
// antes/después con estilos y Rehacer, celular de muestra y el resumen de
// publicar ("N platos nuevos, N actualizados, 0 borrados"). Sin estilos en
// línea (CSP de v2+) y todo escapado.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/admin_v2plus_menu_video.js', 'utf8');

function load() {
  const ctx = vm.createContext({ window: {}, document: { addEventListener() {} }, fetch: async () => ({ ok: true, status: 200, json: async () => ({}) }),
    console, setTimeout: () => 0, clearTimeout() {}, FormData: class {}, JSON, Math, Number, String, Array, Object, Set, Promise });
  ctx.window = ctx;
  vm.runInContext(source, ctx);
  return ctx.window.CxConsoleMenuVideo;
}

const REF1 = '11111111-1111-4111-8111-111111111111';
const REF2 = '22222222-2222-4222-8222-222222222222';
function data(overrides = {}) {
  return {
    company: { id: 'c1', name: 'Brasa & Maíz', kind: 'demo' }, carta_video: true, dishes: 0,
    quota: { month: '2026-10', new: { used: 0, limit: 3, left: 3 }, changes: { used: 1, limit: 3, left: 2 } },
    import: { id: 'i1', status: 'lista', table_data: { categorias: [], platos: [
      { ref: REF1, categoria: 'FUERTES', subcategoria: '', nombre: 'Lomo <al> trapo', descripcion: 'Con papa', precio: 42000, opciones: '' },
      { ref: REF2, categoria: 'BEBIDAS', subcategoria: '', nombre: 'Limonada', descripcion: '', precio: 12000, opciones: '' }] } },
    media: { [REF1]: { has_photo: true, photo_url: '/menu-media/c1/r.webp?e=1&s=x', front_original_url: '/menu-media/c1/o.webp?e=1&s=x',
      front_remaster_url: '/menu-media/c1/r.webp?e=1&s=x', video_url: '/menu-media/c1/v.mp4?e=1&s=x', poster_url: '/menu-media/c1/p.webp?e=1&s=x',
      use_remaster: true, clip_style: 'front_side', status: 'listo' } },
    jobs: { [REF1]: { status: 'listo', style: 'front_side' } },
    photos: [{ id: 'a1', dish_ref: REF1, role: 'front', source_name: 'lomo.jpg', url: '/x.webp' }, { id: 'a2', dish_ref: null, role: 'front', source_name: 'IMG_1.jpg', url: '/y.webp' }],
    ...overrides,
  };
}

function setup(step, extra = {}) {
  const M = load();
  Object.assign(M.model, { companyId: 'c1', data: data(extra), step });
  M.model.table = JSON.parse(JSON.stringify(M.model.data.import.table_data));
  return M;
}

test('los 5 pasos y el encabezado con el cupo del cliente', () => {
  const M = setup(2);
  const html = M.view();
  assert.deepEqual([...html.matchAll(/data-mv-step="(\d)"[^>]*>(\d\. [^<]+)</g)].map((m) => m[2]),
    ['1. Empresa', '2. Importar', '3. Fotos por plato', '4. Remasterizar y clips', '5. Publicar']);
  assert.match(html, /Brasa &amp; Maíz<\/b> · carta en video encendida · cupo del cliente 3\/3 nuevos y 2\/3 cambios este mes/);
  assert.doesNotMatch(html, /style="/, 'sin estilos en línea (CSP)');
});

test('paso 1: solo empresas con Carta, con su interruptor y cupo', () => {
  const M = load();
  M.model.companies = [{ id: 'c1', name: 'Brasa & Maíz', kind: 'demo', carta_video: true, dishes: 12, quota_new: 3, quota_changes: 3 }];
  M.model.health = { ffmpeg: '5.1.6', pillow: '11.0.0', bucket: true, token: true, queue: { jobs: 12, avg_total_ms: 2400, avg_clip_bytes: 180000 } };
  const html = M.companyStep();
  assert.match(html, /ffmpeg <b>5\.1\.6<\/b>/);
  assert.match(html, /12 clips en 30 días, promedio 2\.4 s y 176 KB/);
  assert.match(html, /data-mv-company="c1"[\s\S]*12 platos · Demo[\s\S]*Carta en video encendida[\s\S]*3 nuevos · 3 cambios/);
});

test('paso 2: leyendo, error con "Llenar a mano" y tabla editable escapada', () => {
  let M = setup(2, { import: { id: 'i1', status: 'leyendo', table_data: { platos: [] } } });
  M.model.table = { platos: [] };
  assert.match(M.importStep(), /Leyendo la carta…/);
  M = setup(2, { import: { id: 'i1', status: 'error', error: 'n8n respondió 500.', table_data: { platos: [] } } });
  M.model.table = { platos: [] };
  assert.match(M.importStep(), /No se pudo leer[\s\S]*n8n respondió 500\.[\s\S]*data-mv-manual/);
  M = setup(2);
  const html = M.importStep();
  assert.match(html, /Revisa y corrige antes de seguir · 2 platos/);
  for (const col of ['Categoría', 'Subcategoría', 'Plato', 'Descripción', 'Precio', 'Opciones']) assert.match(html, new RegExp(`<th scope="col">${col}</th>`));
  assert.match(html, /data-mv-cell="0:nombre" value="Lomo &lt;al&gt; trapo"/);
  assert.doesNotMatch(html, /<al>/);
});

test('paso 3: guía de los 3 ángulos, espacios Desde arriba / Frente / Perfil con Cambiar y Quitar; sueltas para asignar', () => {
  const M = setup(3);
  const html = M.photosStep();
  assert.match(html, /<svg[^>]*aria-label="Los tres ángulos[\s\S]*Desde arriba[\s\S]*Frente 45°[\s\S]*Perfil/);
  assert.match(html, /Plato completo y con espacio alrededor\.<\/b> Frente: a 45°\. Perfil: a la altura del plato\. Desde arriba: si el plato es grande/);
  assert.match(html, /Sin plato \(1\)[\s\S]*IMG_1\.jpg[\s\S]*data-mv-assign-ref="a2"[\s\S]*<option value="top">Desde arriba<\/option>/);
  assert.match(html, new RegExp(`Lomo &lt;al&gt; trapo[\s\S]*Desde arriba[\s\S]*>Subir<input[^>]*data-mv-change="${REF1}\|top"[\s\S]*Frente[\s\S]*src="/menu-media/c1/o\.webp\?e=1&amp;s=x"[\s\S]*>Cambiar<input[^>]*data-mv-change="${REF1}\|front"[\s\S]*data-mv-remove="${REF1}\|front">Quitar`));
  assert.doesNotMatch(html, /window\.confirm|style="/, 'sin ventanas del navegador ni estilos en línea');
});

test('Quitar: confirmación en la misma pantalla y Deshacer durante 10 s', () => {
  const M = setup(3);
  M.model.confirm = { key: `${REF1}|front` };
  let html = M.photosStep();
  assert.match(html, /¿Quitar la foto de frente\?[\s\S]*data-mv-remove-yes>Quitar<\/button>[\s\S]*data-mv-remove-no>Cancelar/);
  M.model.confirm = null;
  M.model.undo = { key: `${REF1}|front`, ref: REF1, role: 'front', original: 'o1', until: Date.now() + 10000 };
  assert.match(M.photosStep(), /data-mv-undo>Deshacer/);
  M.model.undo.until = Date.now() - 1;
  assert.doesNotMatch(M.photosStep(), /data-mv-undo/, 'pasados 10 s ya no se ofrece');
});

test('paso 4: antes/después, Rehacer, Quitar video, Rehacer todos y vista en el celular de muestra', () => {
  const M = setup(4);
  let html = M.clipsStep();
  assert.match(html, /Crear todos \(1\)[\s\S]*data-mv-regenerate>Rehacer todos los clips de la empresa/);
  assert.match(html, /720×1280/);
  assert.match(html, /Antes<\/figcaption>[\s\S]*Después<\/figcaption>/);
  assert.match(html, /data-mv-use-remaster="[^"]+" checked/);
  assert.match(html, />Rehacer<[\s\S]*data-mv-video-remove="[^"]+">Quitar video/);
  assert.doesNotMatch(html, /Frente a perfil|Paneo|data-mv-style/, 'un solo movimiento suave');
  assert.match(html, /<video class="vp-mv-phone-media" src="\/menu-media\/c1\/v\.mp4[^"]*" poster="[^"]+" autoplay muted loop playsinline>/);
  assert.match(html, /vp-mv-phone-info"><strong>Lomo &lt;al&gt; trapo<\/strong><span>\$42\.000<\/span><b>Agregar \+<\/b>/);
  M.model.confirm = { key: `${REF1}|video` };
  assert.match(M.clipsStep(), /¿Quitar el video\? Queda solo la foto\.[\s\S]*data-mv-remove-yes/);
});

test('paso 2: quitar una categoría (o una fila) de la importación antes de publicar', () => {
  const M = setup(2);
  let html = M.importStep();
  assert.match(html, /FUERTES <button[^>]*data-mv-cat-del="FUERTES"[^>]*aria-label="Quitar la categoría FUERTES"/);
  assert.match(html, /data-mv-row-del="0"/);
  M.model.confirm = { key: 'cat|BEBIDAS' };
  assert.match(M.importStep(), /¿Quitar BEBIDAS y sus 1 platos de la importación\?/);
});

test('paso 5: combinar, nunca borrar', () => {
  const M = setup(5);
  M.model.plan = { counts: { new: 1, updated: 1, unchanged: 0, deleted: 0 }, new_categories: ['BEBIDAS'],
    new: [{ nombre: 'Limonada', categoria: 'BEBIDAS', precio: 12000, media: false }],
    updated: [{ nombre: 'Lomo <al> trapo', categoria: 'FUERTES', precio: 42000, changes: ['precio', 'foto/video'] }], unchanged: [] };
  const html = M.publishStep();
  assert.match(html, /1 platos nuevos, 1 actualizados, 0 borrados\. Categorías nuevas: BEBIDAS\./);
  assert.match(html, /Limonada<\/td><td>BEBIDAS<\/td><td>\$12\.000<\/td><td>Nuevo · receta pendiente/);
  assert.match(html, /Actualiza precio, foto\/video/);
  assert.match(html, /data-mv-publish[^>]*>Publicar en Brasa &amp; Maíz/);
});

test('057C paso 5: se puede volver a publicar; sin cambios "No hay cambios para publicar"; aviso de la última publicación', () => {
  const published = { new: 12, updated: 0, deleted: 0, published_at: '2026-10-26T20:42:00Z', history: [] };
  const M = setup(5, { import: { id: 'i1', status: 'publicada', summary: { ...published, new: 0, updated: 1, published_at: '2026-10-26T20:42:00Z',
    history: [{ new: 12, updated: 0, published_at: '2026-10-26T19:00:00Z' }] }, table_data: { platos: [] } } });
  M.model.plan = { counts: { new: 0, updated: 1, unchanged: 11, deleted: 0 }, new_categories: [], new: [],
    updated: [{ nombre: 'Empanadas de la casa', categoria: 'ENTRADAS', precio: 9000, changes: ['foto/video'] }], unchanged: [] };
  let html = M.publishStep();
  assert.match(html, /<button type="button" class="vp-btn vp-btn-primary" data-mv-publish >Publicar en Brasa &amp; Maíz/, 'con 1 actualizado el botón está activo');
  assert.match(html, /Publicado (hoy )?[^:]*3:42[^:]*p\.\s?m\.:<\/strong> 0 nuevos, 1 actualizado, 0 borrados\./);
  assert.match(html, /Empanadas de la casa[\s\S]*Actualiza foto\/video/);
  M.model.plan = { counts: { new: 0, updated: 0, unchanged: 12, deleted: 0 }, new_categories: [], new: [], updated: [], unchanged: [] };
  html = M.publishStep();
  assert.match(html, /<button type="button" class="vp-btn" disabled>No hay cambios para publicar<\/button>/);
  assert.doesNotMatch(html, /data-mv-publish/);
  assert.equal(M.whenText('2026-10-26T20:42:00Z', new Date('2026-10-26T22:00:00Z')).startsWith('hoy '), true);
  assert.match(M.whenText('2026-10-20T20:42:00Z', new Date('2026-10-26T22:00:00Z')), /^20 (de )?oct/);
});
