// Carta en video del QR de la mesa (hospitality_order.html real + menu_video_feed.js)
// en Chrome sin ventana a 390 x 844: el plato ocupa la pantalla, nombre, precio y
// "Agregar" siempre visibles (sin chocar con "Tu pedido"), contraste AA, solo el
// video visible y el siguiente cargados, en silencio y en bucle; plato sin video =
// foto con movimiento; sin foto = tarjeta. "Agregar" suma al pedido. Con el
// interruptor apagado no aparece. Si no hay Chrome, se salta.
// CX_MV_SHOTS=<carpeta> guarda capturas PNG.
const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFile } = require('node:child_process');

const ROOT = path.resolve(__dirname, '..');
const WEB = path.join(ROOT, 'app', 'web');
const MEDIA = path.join(__dirname, 'fixtures', 'menu_video');
const CHROME = [process.env.CHROME_PATH, 'C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'].find((p) => p && fs.existsSync(p));
const CID = '57b00000-0000-4000-8000-00000000c0d';
const TYPES = { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html', '.webp': 'image/webp', '.mp4': 'video/mp4' };
const CASES = [['video-390', ''], ['agregar-390', '&add=1'], ['apagado-390', '&video=0']];

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/ordenar') {
      return send(fs.readFileSync(path.join(WEB, 'hospitality_order.html'), 'utf8').replace('<script', '<script src="/__mv.js"></script>\n  <script'), 'text/html');
    }
    if (url.pathname === '/__mv.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'menu_video_qr_preview.js')), TYPES['.js']);
    if (url.pathname.startsWith('/__mv/')) {
      const file = path.join(MEDIA, path.basename(url.pathname));
      if (fs.existsSync(file)) return send(fs.readFileSync(file), TYPES[path.extname(file)]);
    }
    if (url.pathname === '/__frames.html') {
      const frames = CASES.map(([k, q], i) => `<iframe data-k="${k}" style="width:390px;height:844px;border:0;display:block" src="/ordenar?company_id=${CID}${i}&mesa=Mesa%204${q}"></iframe>`);
      return send(`<!doctype html><html><body style="margin:0">${frames.join('')}<pre id="all"></pre><script>
        setTimeout(() => { const out = {}; document.querySelectorAll('iframe').forEach((f) => { const d = f.contentDocument && f.contentDocument.getElementById('layout'); out[f.dataset.k] = d ? JSON.parse(d.textContent) : null; });
          document.getElementById('all').textContent = JSON.stringify(out); }, 12000);</script></body></html>`, 'text/html');
    }
    if (url.pathname === '/__one.html') {
      return send(`<!doctype html><html><body style="margin:0;background:#fff"><iframe style="width:390px;height:844px;border:0;display:block" src="/ordenar?company_id=${CID}9&mesa=Mesa%204${url.searchParams.get('q') || ''}"></iframe></body></html>`, 'text/html');
    }
    const file = url.pathname.startsWith('/client-static/') ? path.join(WEB, url.pathname.slice('/client-static/'.length)) : null;
    if (file && file.startsWith(WEB) && fs.existsSync(file) && fs.statSync(file).isFile()) return send(fs.readFileSync(file), TYPES[path.extname(file)] || 'application/octet-stream');
    res.writeHead(404); res.end();
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

function chrome(args) {
  return new Promise((resolve, reject) => {
    execFile(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', '--autoplay-policy=no-user-gesture-required', ...args],
      { timeout: 200000, maxBuffer: 64 * 1024 * 1024 }, (err, stdout) => (err ? reject(err) : resolve(stdout)));
  });
}

test('QR carta en video a 390 px: pantalla completa, Agregar visible, AA y solo 2 videos cargados',
  { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 300000 }, async () => {
    const server = await serve();
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-mv-layout-'));
    const base = `http://127.0.0.1:${server.address().port}`;
    try {
      const html = await chrome([`--user-data-dir=${profile}`, '--window-size=500,2600', '--virtual-time-budget=20000', '--dump-dom', `${base}/__frames.html`]);
      const m = html.match(/<pre id="all">([^<]*)<\/pre>/);
      assert.ok(m && m[1], 'sin resultado de la medición');
      const r = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
      const v = r['video-390'];
      assert.ok(v && v.mounted, 'la carta en video no se montó');
      assert.equal(v.page_overflow, false);
      assert.deepEqual(v.slide, { w: 390, h: 844 }, 'cada plato ocupa la pantalla');
      assert.deepEqual(v.visible, { name: true, price: true, add: true, dock: true, cats: true });
      assert.equal(v.text.name, 'Lomo al trapo');
      assert.match(v.text.price, /42\.000/);
      assert.equal(v.text.add, 'Agregar +');
      assert.equal(v.add_over_dock, false, '"Agregar" no choca con "Tu pedido"');
      assert.ok(v.add_size.h >= 44 && v.add_size.w >= 44, 'botón táctil de 44 px o más');
      assert.ok(v.add_ratio >= 4.5, `contraste de Agregar ${v.add_ratio}`);
      assert.ok(v.info_ratio >= 4.5, `contraste del nombre ${v.info_ratio}`);
      assert.equal(v.slides, 4);
      assert.deepEqual(v.videos, [true, true], 'solo el visible y el siguiente tienen video');
      assert.equal(v.muted, true, 'sin sonido, en bucle y en línea');
      assert.equal(v.kenburns, true, 'plato sin video: su foto con movimiento');
      assert.equal(v.card, true, 'plato sin foto: tarjeta (nunca un hueco)');
      assert.deepEqual(v.cats, ['FUERTES', 'SOPAS', 'BEBIDAS', 'POSTRES']);
      const a = r['agregar-390'];
      assert.match(a.text.dock, /Tu pedido · 1 producto/);
      assert.match(a.text.add, /Agregar \+1/);
      const off = r['apagado-390'];
      assert.equal(off.mounted, false, 'con el interruptor apagado no hay carta en video');
      assert.equal(off.list_photo, true, 'la carta en lista muestra la foto del plato si la tiene');
      const shots = process.env.CX_MV_SHOTS;
      if (shots) {
        fs.mkdirSync(shots, { recursive: true });
        for (const [k, q] of [['qr-carta-video-390', ''], ['qr-carta-video-agregar-390', '&add=1'], ['qr-lista-con-foto-390', '&video=0']]) {
          await chrome([`--user-data-dir=${profile}-${k}`, '--window-size=390,844', '--virtual-time-budget=9000', '--hide-scrollbars',
            `--screenshot=${path.join(shots, `${k}.png`)}`, `${base}/__one.html?q=${encodeURIComponent(q)}`]);
        }
      }
    } finally {
      server.close();
    }
  });
