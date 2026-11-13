// Pantalla QR del bar con la galería de íconos de Clonexa (iconos_carta_clonexa)
// en Chrome sin ventana, a 390 px (celular) y 1440 px (PC): los SVG cargan, todos
// del mismo tamaño, dentro de su tarjeta, sin descuadrar la grilla ni desbordar.
// Mismo simulador que qr_header_layout.test.cjs. Si no hay Chrome, se salta.
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
const CID = '21a3065e-0000-4000-8000-0000000ic0de';
const TYPES = { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html', '.svg': 'image/svg+xml' };
const CASES = [['cats-390', '', 390], ['cats-1440', '', 1440], ['prod-390', '&prod=Aguardiente', 390], ['prod-1440', '&prod=Cerveza', 1440], ['off-390', '&off=1', 390]];

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/ordenar') {
      return send(fs.readFileSync(path.join(WEB, 'hospitality_order.html'), 'utf8').replace('<script', '<script src="/__qr.js"></script>\n  <script'), 'text/html');
    }
    if (url.pathname === '/__qr.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'iconos_carta_qr_preview.js')), TYPES['.js']);
    if (url.pathname === '/__frames.html') {
      const frames = CASES.map(([k, q, w], i) => `<iframe data-k="${k}" style="width:${w}px;height:1600px;border:0;display:block" src="/ordenar?company_id=${CID.slice(0, -1)}${i}&mesa=Mesa%204${q}"></iframe>`);
      return send(`<!doctype html><html><body style="margin:0">${frames.join('')}<pre id="all"></pre><script>
        setTimeout(() => { const out = {}; document.querySelectorAll('iframe').forEach((f) => { const d = f.contentDocument && f.contentDocument.getElementById('layout'); out[f.dataset.k] = d ? JSON.parse(d.textContent) : null; });
          document.getElementById('all').textContent = JSON.stringify(out); }, 20000);</script></body></html>`, 'text/html');
    }
    let file = null;
    if (url.pathname.startsWith('/client-static/')) file = path.join(WEB, url.pathname.slice('/client-static/'.length));
    if (url.pathname.startsWith('/assets/iconos-carta/')) file = path.join(WEB, 'assets', 'iconos-carta', path.basename(url.pathname));
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

test('QR del bar con íconos de Clonexa a 390 y 1440 px: cargan, mismo tamaño, sin descuadres; apagado = emojis',
  { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 400000 }, async () => {
    const server = await serve();
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-iconos-layout-'));
    const base = `http://127.0.0.1:${server.address().port}`;
    try {
      const html = await chrome([`--user-data-dir=${profile}`, '--window-size=1500,1600', '--virtual-time-budget=30000', '--dump-dom', `${base}/__frames.html`]);
      const m = html.match(/<pre id="all">([^<]*)<\/pre>/);
      assert.ok(m && m[1], 'sin resultado de la medición');
      const r = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
      for (const k of ['cats-390', 'cats-1440', 'prod-390', 'prod-1440']) {
        const x = r[k];
        assert.ok(x && x.mounted, `${k}: no se montó ${JSON.stringify(x)}`);
        assert.equal(x.imgs, x.tiles, `${k}: cada tarjeta con su ícono`);
        assert.equal(x.loaded, x.imgs, `${k}: algún SVG no cargó`);
        assert.equal(x.img_sizes.length, 1, `${k}: íconos de tamaños distintos ${x.img_sizes}`);
        assert.equal(x.icon_heights.length, 1, `${k}: la ranura del ícono cambia de alto ${x.icon_heights}`);
        assert.equal(x.uneven_rows, 0, `${k}: filas descuadradas`);
        assert.deepEqual(x.overflow, [], `${k}: texto que se sale`);
        assert.equal(x.outside, 0, `${k}: ícono fuera de su tarjeta`);
        assert.equal(x.page_overflow, false, `${k}: la página se sale de ancho`);
      }
      assert.equal(r['cats-390'].tiles, 14);
      assert.deepEqual(r['cats-390'].alts, ['Agua', 'Aguardiente', 'Cerveza']);
      const [w, h] = r['cats-390'].img_sizes[0].split('x').map(Number);
      assert.ok(w >= 55 && w <= 64 && w === h, `tamaño del ícono de categoría ${w}x${h} (el emoji de hoy es de 52 px)`);
      assert.ok(Math.max(...r['cats-1440'].per_row) > Math.max(...r['cats-390'].per_row), 'en PC caben más tarjetas por fila');
      const off = r['off-390'];
      assert.ok(off && off.mounted && off.imgs === 0, 'sin el interruptor: emojis, ningún <img>');
    } finally {
      server.close();
      try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
    }
  });
