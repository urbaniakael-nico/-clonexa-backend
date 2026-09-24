// "Pedido musical por mesa" (048B, lista agrupada 048D) en el panel: solo con el
// interruptor qr_bar_menu (The Time Machine). Ejecuta las funciones reales
// de client.js en un contexto aislado.
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

const NAMES = [
  'cxIsHospitalityQrCode024S', 'cxHspActiveSongRequests031T', 'cxHspSongRequestCard031C',
  'cxHspSongByTableOn048B', 'cxHspSongTableKey048B', 'cxHspSongGroups048B', 'cxHspSongGroupedHtml048D',
  'cxHspCopyText048B', 'cxHspCopyFallback048B', 'cxHspSongToast048B',
  'cxHspCopyAndArchiveSong048B', 'cxHspRenderSongRequests031C', 'cxHspPaintSongQueue031K',
];

const song = (id, table, name, minute) => ({
  id, table_number: table, song: name, status: 'pendiente', created_at: `2026-09-23T22:${String(minute).padStart(2, '0')}:00Z`,
});

function panel({ barMenu = true, songs = [], archiveFails = false } = {}) {
  const list = { innerHTML: '', dataset: {}, scrollTop: 0, scrollHeight: 0, clientHeight: 0, querySelectorAll: () => [] };
  const count = { textContent: '' };
  const toast = { id: '', textContent: '', classList: { add() {}, remove() {}, toggle() {} }, setAttribute() {} };
  const copied = [];
  const archived = [];
  const qrModule = { code: 'qr', raw: { settings: barMenu ? { qr_bar_menu: true, qr_config: { orders_board: 'mesas' } } : { qr_config: {} } } };
  const context = vm.createContext({
    h: (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
    activeClientModules: () => [{ code: 'hospitality', raw: {} }, qrModule],
    document: {
      getElementById: (id) => ({ hspSongRequests031C: list, hspSongCount031C: count, hspSongToast048B: toast }[id] || null),
      createElement: () => toast,
      body: { appendChild() {} },
    },
    navigator: { clipboard: { writeText: async (text) => { copied.push(text); } } },
    window: { requestAnimationFrame: (f) => f(), setTimeout: () => 0, clearTimeout() {} },
    cxHspApi024R: async (path, options) => {
      archived.push(path);
      if (archiveFails) throw new Error('sin red');
      return { ok: true };
    },
    Date, JSON, String, Number, Map, Set, Array, Promise, Infinity,
  });
  vm.runInContext(
    `var cxHspSongRequests031C = ${JSON.stringify(songs)}; var cxHspSongSearch031H = "";\n`
      + NAMES.map(fn).join('\n'),
    context,
  );
  const paint = () => { context.cxHspPaintSongQueue031K(context.cxHspSongRequests031C, { force: true }); return list.innerHTML; };
  return { context, list, count, copied, archived, toast, paint };
}

const TWO_TABLES = [
  song('s1', 'Mesa 8', 'Simplemente amigos', 5),
  song('s2', 'Mesa 3', 'Música de plancha', 7),
  song('s3', 'Mesa 8', 'Juan Gabriel - Querida', 9),
  song('s4', 'Mesa 3', 'Vicente Fernández', 2),
];

const groupOf = (html, key) => {
  const match = new RegExp(`data-hsp-song-group="${key}"[\\s\\S]*?</section>`).exec(html);
  return match ? match[0] : '';
};
const songsOf = (html, key) => [...groupOf(html, key).matchAll(/<span class="hsp-song-name-048b">♫ ([^<]+)<\/span>/g)].map((m) => m[1]);

test('lista agrupada por mesa, todo a la vista y sin carpetas desplegables', () => {
  const p = panel({ songs: TWO_TABLES });
  const html = p.paint();
  const heads = [...html.matchAll(/<header class="hsp-song-group-head-048d">\s*<span>([^<]+)<\/span>/g)].map((m) => m[1]);
  assert.deepEqual(heads, ['Mesa 3', 'Mesa 8'], 'un encabezado por mesa, de menor a mayor');
  assert.doesNotMatch(html, /<details|<summary|hsp-song-table-/, 'nada que desplegar');
  assert.doesNotMatch(html, /data-hsp-song-archive=|Buscar canción/);
  assert.equal(p.count.textContent, '4', 'contador total arriba a la derecha');
});

test('debajo de cada mesa sus canciones, una por línea y en orden de llegada, con Copiar', () => {
  const p = panel({ songs: TWO_TABLES });
  const html = p.paint();
  assert.deepEqual(songsOf(html, 'n3'), ['Vicente Fernández', 'Música de plancha']);
  assert.deepEqual(songsOf(html, 'n8'), ['Simplemente amigos', 'Juan Gabriel - Querida']);
  assert.equal((groupOf(html, 'n8').match(/data-hsp-song-copy=/g) || []).length, 2);
  assert.match(groupOf(html, 'n8'), /data-hsp-song-copy="s1">Copiar<\/button>/);
  assert.match(groupOf(html, 'n3'), /<small>2 canciones<\/small>/);
});

test('el bloque tiene su propio desplazamiento', () => {
  const css = source.split('\n').find((line) => line.includes('.hsp-song-list-031c{'));
  assert.match(css, /max-height:310px;overflow-y:auto/);
  assert.match(source, /<div id="hspSongRequests031C" class="hsp-song-list-031c hsp-song-bytable-048b"><\/div>/);
});

test('Copiar copia el nombre, archiva la canción y la quita de la lista', async () => {
  const p = panel({ songs: TWO_TABLES });
  p.paint();
  await p.context.cxHspCopyAndArchiveSong048B('s1');
  assert.deepEqual(p.copied, ['Simplemente amigos']);
  assert.deepEqual(p.archived, ['/song-requests/s1/archive']);
  assert.doesNotMatch(p.list.innerHTML, /Simplemente amigos/);
  assert.match(p.list.innerHTML, /Juan Gabriel - Querida/);
  assert.equal(p.count.textContent, '3', 'el contador se actualiza');
  assert.match(p.toast.textContent, /✓ Copiada: Simplemente amigos/);
});

test('al archivar la última canción de una mesa, su encabezado desaparece; sin nada queda el mensaje', async () => {
  const p = panel({ songs: [song('a', 'Mesa 3', 'Una', 1), song('b', 'Mesa 8', 'Dos', 2)] });
  p.paint();
  await p.context.cxHspCopyAndArchiveSong048B('a');
  assert.doesNotMatch(p.list.innerHTML, /data-hsp-song-group="n3"|>Mesa 3</);
  assert.match(p.list.innerHTML, /data-hsp-song-group="n8"/);
  assert.equal(p.count.textContent, '1');
  await p.context.cxHspCopyAndArchiveSong048B('b');
  assert.match(p.list.innerHTML, /Sin solicitudes musicales pendientes/);
  assert.equal(p.count.textContent, '0');
});

test('si archivar falla, la canción vuelve a la lista', async () => {
  const p = panel({ songs: [song('a', 'Mesa 3', 'Una', 1)], archiveFails: true });
  p.paint();
  await p.context.cxHspCopyAndArchiveSong048B('a');
  assert.match(p.list.innerHTML, /data-hsp-song-copy="a"/);
  assert.equal(p.count.textContent, '1');
});

test('otras empresas (sin qr_bar_menu): la lista de siempre con Archivar', () => {
  const p = panel({ barMenu: false, songs: TWO_TABLES });
  const html = p.paint();
  assert.match(html, /<span>Canción<\/span><span>Mesa<\/span><span>Acción<\/span>/);
  assert.equal((html.match(/data-hsp-song-archive=/g) || []).length, 4);
  assert.doesNotMatch(html, /hsp-song-table-048b|data-hsp-song-copy/);
});

test('el bloque sin buscador ni "Archivar más antiguas" solo con el interruptor', () => {
  const start = source.indexOf('${cxHspSongByTableOn048B() ? `');
  assert.ok(start > 0);
  const [onBranch, offBranch] = source.slice(start, source.indexOf('<div id="hspSongRequests031C" class="hsp-song-list-031c"></div>`}', start)).split('` : `');
  assert.match(onBranch, /PEDIDO MUSICAL POR MESA/);
  assert.doesNotMatch(onBranch, /data-hsp-song-search|Archivar más antiguas/);
  assert.match(offBranch, /Buscar canción o mesa/);
  assert.match(offBranch, /Archivar más antiguas/);
  assert.match(source, /<span class="hsp-pill-024r music" id="hspSongCount031C">0<\/span>/, 'se mantiene el contador');
});
