// "Pedido musical por mesa" (048B) en el panel de empresa: solo con el
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
  'cxHspSongByTableOn048B', 'cxHspSongTableKey048B', 'cxHspSongGroups048B', 'cxHspSongByTableHtml048B',
  'cxHspBindSongTables048B', 'cxHspCopyText048B', 'cxHspCopyFallback048B', 'cxHspSongToast048B',
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
    `var cxHspSongRequests031C = ${JSON.stringify(songs)}; var cxHspSongSearch031H = ""; var cxHspSongOpenTables048B = new Set();\n`
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

test('dos mesas con canciones muestran sus dos números, de menor a mayor', () => {
  const p = panel({ songs: TWO_TABLES });
  const html = p.paint();
  const numbers = [...html.matchAll(/<span class="hsp-song-table-num-048b">([^<]+)<\/span>/g)].map((m) => m[1]);
  assert.deepEqual(numbers, ['3', '8']);
  assert.match(html, /data-hsp-song-table="n3"[\s\S]*2 canciones/);
  assert.match(html, /hsp-song-table-arrow-048b/, 'cada número tiene su flecha');
  assert.doesNotMatch(html, /data-hsp-song-archive=|Buscar canción/);
  assert.equal(p.count.textContent, '4', 'contador total arriba a la derecha');
});

test('desplegar una mesa muestra solo sus canciones, en orden de llegada', () => {
  const p = panel({ songs: TWO_TABLES });
  const html = p.paint();
  const block = (key) => new RegExp(`data-hsp-song-table="${key}"[\\s\\S]*?</details>`).exec(html)[0];
  const songsOf = (key) => [...block(key).matchAll(/<span class="hsp-song-name-048b">♫ ([^<]+)<\/span>/g)].map((m) => m[1]);
  assert.deepEqual(songsOf('n3'), ['Vicente Fernández', 'Música de plancha']);
  assert.deepEqual(songsOf('n8'), ['Simplemente amigos', 'Juan Gabriel - Querida']);
  assert.match(block('n8'), /data-hsp-song-copy="s1">Copiar<\/button>/);

  // la mesa abierta sigue abierta en el siguiente repintado
  p.context.cxHspSongOpenTables048B.add('n8');
  const again = p.paint();
  assert.match(again, /data-hsp-song-table="n8" open/);
  assert.match(again, /data-hsp-song-table="n3" >/);
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

test('al archivar la última canción de una mesa, su número desaparece; sin nada queda el mensaje', async () => {
  const p = panel({ songs: [song('a', 'Mesa 3', 'Una', 1), song('b', 'Mesa 8', 'Dos', 2)] });
  p.paint();
  await p.context.cxHspCopyAndArchiveSong048B('a');
  assert.doesNotMatch(p.list.innerHTML, /data-hsp-song-table="n3"/);
  assert.match(p.list.innerHTML, /data-hsp-song-table="n8"/);
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
