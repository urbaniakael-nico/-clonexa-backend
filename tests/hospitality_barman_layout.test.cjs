// Panel Barman con la música a la derecha (barman_music_layout, solo The Time
// Machine), en el portal real con Chrome sin ventana: 1280 y 1600 px, tablet
// horizontal (1024) y vertical (768). No guarda capturas: todo son medidas.
// Si no hay Chrome, se salta.
const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFile } = require('node:child_process');

const ROOT = path.resolve(__dirname, '..');
const WEB = path.join(ROOT, 'app', 'web');
const CHROME = [process.env.CHROME_PATH, 'C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'].find((p) => p && fs.existsSync(p));
const CID = '21a3065e-0000-4000-8000-00000000c0de';
const TYPES = { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html' };
const CASES = [
  ['on-1280', 1280, '&on=1&songs=40&archived=1'], ['on-1600', 1600, '&on=1&songs=40&archived=1'],
  ['on-1024', 1024, '&on=1&songs=40'], ['on-768', 768, '&on=1&songs=40'],
  ['pocas-1280', 1280, '&on=1&songs=2'], ['sin-qrbar-1280', 1280, '&on=1&songs=3'],
  ['falla-copia-1280', 1280, '&on=1&songs=3&clip=fail'], ['tres-cierres-1280', 1280, '&on=1&songs=2&closed=3'],
  ['sin-cierres-1280', 1280, '&on=1&songs=2&closed=0&tables=3'], ['kanban-1280', 1280, '&on=1&board=kanban'],
  ['cierre-1280', 1280, '&on=1&gen=1'], ['total-servidor-1280', 1280, '&on=1&songs=2&sum=big'], ['total-falla-1280', 1280, '&on=1&songs=2&sum=fail'], ['off-1280', 1280, '&songs=3&closed=8'],
];

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/client.html') {
      return send(fs.readFileSync(path.join(WEB, 'client.html'), 'utf8').replace('<link rel="stylesheet"', '<script src="/__preview.js"></script>\n  <link rel="stylesheet"'), 'text/html');
    }
    if (url.pathname === '/__preview.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'barman_layout_preview.js')), TYPES['.js']);
    if (url.pathname === '/__frames.html') {
      const frames = CASES.map(([k, w, q]) => `<iframe data-k="${k}" style="width:${w}px;height:1800px;border:0;display:block" src="/client.html?company_id=${CID}${q}"></iframe>`);
      return send(`<!doctype html><html><body style="margin:0">${frames.join('')}<pre id="all"></pre><script>
        const read = () => { const out = {}; document.querySelectorAll('iframe').forEach((f) => { const d = f.contentDocument && f.contentDocument.getElementById('layout'); out[f.dataset.k] = d ? JSON.parse(d.textContent) : null; }); return out; };
        setTimeout(() => { document.getElementById('all').textContent = JSON.stringify(read()); }, 40000);</script></body></html>`, 'text/html');
    }
    const file = url.pathname.startsWith('/client-static/') ? path.join(WEB, url.pathname.slice('/client-static/'.length)) : null;
    if (file && file.startsWith(WEB) && fs.existsSync(file) && fs.statSync(file).isFile()) return send(fs.readFileSync(file), TYPES[path.extname(file)] || 'application/octet-stream');
    res.writeHead(404); res.end();
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

function chrome(args) {
  return new Promise((resolve, reject) => {
    execFile(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', ...args], { timeout: 200000, maxBuffer: 64 * 1024 * 1024 }, (err, stdout) => (err ? reject(err) : resolve(stdout)));
  });
}

test('Panel Barman: música a la derecha, Copiar y cierres plegables; apagado = el de siempre',
  { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 400000 }, async () => {
    const server = await serve();
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-barman-layout-'));
    const base = `http://127.0.0.1:${server.address().port}`;
    try {
      const html = await chrome([`--user-data-dir=${profile}`, '--window-size=1700,1400', '--virtual-time-budget=60000', '--dump-dom', `${base}/__frames.html`]);
      const m = html.match(/<pre id="all">([^<]*)<\/pre>/);
      assert.ok(m && m[1], 'sin resultado de la medición');
      const r = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&nbsp;/g, ' '));
      if (process.env.CX_BARMAN_DUMP) fs.writeFileSync(process.env.CX_BARMAN_DUMP, JSON.stringify(r, null, 1));

      // Desde la v2 (070A) el diseño de tarjetas y la música fija se miden en
      // hospitality_barman_v2.test.cjs; aquí queda lo que sigue igual.
      for (const k of ['on-1280', 'on-1600', 'on-1024', 'on-768']) {
        const x = r[k];
        assert.ok(x && x.mounted, `${k}: no se montó ${x && x.error}`);
        assert.equal(x.switch_class, true, k);
        assert.equal(x.page_overflow, false, `${k}: la página se sale de ancho`);
        assert.deepEqual(x.clipped, [], `${k}: contenido por fuera de su caja`);
        assert.deepEqual(x.song_buttons, ['Copiar'], `${k}: solo Copiar`);
        assert.deepEqual(x.song_controls, { search: false, bulk: false }, k);
      }

      for (const k of ['on-1280', 'on-1600']) {
        const x = r[k];
        assert.ok(x.queue.left > x.fold.right, `${k}: música a la derecha`);
        assert.equal(x.list_scrolls, true, `${k}: la lista se desplaza dentro del panel`);
        assert.ok(['auto', 'scroll'].includes(x.list_overflow_y), k);
        assert.ok(x.list.bottom <= x.queue.bottom, `${k}: la lista no se sale del panel`);
        assert.match(x.title, /^Mesas cerradas hoy \(8\) · Total \$\s?360\.000$/, `${k}: la archivada no cuenta`);
      }

      // Plegable: 5 a la vista, de la más reciente a la más antigua, y Ver todas.
      const x = r['on-1280'];
      assert.equal(x.open_default, true);
      assert.deepEqual(x.chips_default, ['Mesa 20', 'Mesa 21', 'Mesa 22', 'Mesa 23', 'Mesa 24']);
      assert.equal(x.more_label, 'Ver todas (8)');
      assert.equal(x.chips_all, 8);
      assert.equal(x.chips_after_poll, 8, 'Ver todas sobrevive al refresco automático');
      assert.equal(x.chips_back, 5);
      assert.equal(x.closed_after_click, true);
      assert.equal(x.still_closed, true, 'plegada sigue plegada tras el refresco automático');
      assert.ok(x.collapsed_h < 110, `plegada ocupa poco (${x.collapsed_h})`);

      const few = r['tres-cierres-1280'];
      assert.equal(few.more_label, '', 'con 5 o menos no hay Ver todas');
      assert.equal(few.chips_default.length, 3);
      assert.match(few.title, /^Mesas cerradas hoy \(3\) · Total \$\s?60\.000$/);
      const none = r['sin-cierres-1280'];
      assert.match(none.title, /^Mesas cerradas hoy \(0\) · Total \$\s?0$/);
      assert.deepEqual(none.clipped, []);

      // Copiar: portapapeles + archivar, y no vuelve con el refresco.
      for (const k of ['on-1280', 'sin-qrbar-1280']) {
        const c = r[k];
        assert.equal(c.copied.length, 1, k);
        assert.match(c.copied[0], /^Canción de ejemplo \d+ - Artista$/, k);
        assert.deepEqual(c.archived, [c.copy_id], k);
        assert.equal(c.copy_gone, true, k);
        assert.equal(c.copy_still_gone, true, `${k}: no reaparece`);
        assert.equal(Number(c.song_count_after), Number(c.song_count) - 1, k);
      }
      const fail = r['falla-copia-1280'];
      assert.deepEqual(fail.archived, [], 'si no copia, no archiva');
      assert.equal(fail.copy_gone, false, 'si no copia, la canción sigue');
      assert.match(fail.toast, /No se pudo copiar/);

      // El total es del servidor: nunca la suma de los pedidos cargados.
      const big = r['total-servidor-1280'];
      assert.match(big.title, /^Mesas cerradas hoy \(300\) · Total \$\s?5\.000\.000$/);
      assert.equal(big.more_label, 'Ver todas (8)', 'Ver todas dice cuántas puede mostrar');
      assert.match(big.closed_note, /muestra 8 de 300 mesas/);
      assert.deepEqual(big.clipped, []);
      assert.equal(r['on-1280'].closed_note, '', 'si están todas, no hay nota');
      const down = r['total-falla-1280'];
      assert.equal(down.title, 'Mesas cerradas hoy · Total no disponible', 'sin servidor no inventa un total parcial');
      assert.deepEqual(down.chips_default.length, 5, 'la lista sigue funcionando');

      // "Generar cierre" los pasa al historial como hoy: la sección queda en cero.
      const gen = r['cierre-1280'];
      assert.equal(gen.posted, true, 'usa el mismo POST /day-closures');
      assert.match(gen.before, /\(8\)/);
      assert.match(gen.after, /^Mesas cerradas hoy \(0\) · Total \$\s?0$/);
      assert.equal(gen.chips, 0);
      assert.equal(gen.more, false);

      // Con el kanban y sin el interruptor, el panel de siempre.
      for (const k of ['kanban-1280', 'off-1280']) {
        const o = r[k];
        assert.ok(o && o.mounted, k);
        assert.equal(o.switch_class, false, k);
        assert.equal(o.fold, null, k);
        assert.equal(o.song_controls.search, true, `${k}: sigue el buscador`);
        assert.deepEqual(o.song_buttons, ['Archivar'], k);
        assert.equal(o.summary_calls, 0, `${k}: sin el interruptor no consulta el total`);
      }
      assert.ok(r['off-1280'].tables.top >= r['off-1280'].grid.bottom, 'apagado: Mesas debajo, a todo el ancho');
    } finally {
      server.close();
      try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
    }
  });
