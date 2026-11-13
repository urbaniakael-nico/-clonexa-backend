// Cola de hoy en Chrome headless con la consola v2+ real, a 390 px (celular, 1 columna) y 1440 px (PC, 2
// columnas): ningún texto desborda, la página no se sale de ancho, botones grandes para el dedo (≥ 48 px) y
// contraste AA en el texto y los botones. Si no hay Chrome, la prueba se salta.
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
const CASES = [['cola-390', 390], ['cola-1440', 1440]];

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/admin-v2plus') {
      const html = fs.readFileSync(path.join(WEB, 'admin_v2plus.html'), 'utf8').replace('<link rel="stylesheet" href="/admin-v2plus.css"', '<script src="/__preview.js"></script>\n  <link rel="stylesheet" href="/admin-v2plus.css"');
      return send(html, 'text/html');
    }
    if (url.pathname === '/__preview.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'cola_preview.js')), 'application/javascript');
    if (url.pathname === '/__frames.html') {
      const frames = CASES.map(([k, w]) => `<iframe data-k="${k}" style="width:${w}px;height:1400px;border:0;display:block" src="/admin-v2plus"></iframe>`);
      return send(`<!doctype html><html><body style="margin:0">${frames.join('')}<pre id="all"></pre><script>
        setTimeout(() => { const out = {}; document.querySelectorAll('iframe').forEach((f) => { const d = f.contentDocument && f.contentDocument.getElementById('layout'); out[f.dataset.k] = d ? JSON.parse(d.textContent) : null; });
          document.getElementById('all').textContent = JSON.stringify(out); }, 12000);</script></body></html>`, 'text/html');
    }
    if (url.pathname === '/admin-v2plus.css') return send(fs.readFileSync(path.join(WEB, 'admin_v2plus.css')), 'text/css');
    const js = /^\/admin-v2plus(-[a-z-]+)?\.js$/.exec(url.pathname);
    if (js) {
      const name = js[1] === '-webauthn' ? 'webauthn_browser.js' : `admin_v2plus${(js[1] || '').replace(/-/g, '_')}.js`;
      const file = path.join(WEB, name);
      if (fs.existsSync(file)) return send(fs.readFileSync(file), 'application/javascript');
    }
    res.writeHead(404); res.end();
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

function dump(url, profile) {
  return new Promise((resolve, reject) => {
    execFile(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', `--user-data-dir=${profile}`, '--window-size=1500,1500', '--virtual-time-budget=20000', '--dump-dom', url],
      { timeout: 150000, maxBuffer: 64 * 1024 * 1024 }, (err, stdout) => (err ? reject(err) : resolve(stdout)));
  });
}

test('Cola de hoy: 390 px una columna, 1440 px dos; sin desbordes, botones grandes y contraste AA',
  { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 200000 }, async () => {
    const server = await serve();
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-cola-layout-'));
    try {
      const html = await dump(`http://127.0.0.1:${server.address().port}/__frames.html`, profile);
      const m = html.match(/<pre id="all">([^<]*)<\/pre>/);
      assert.ok(m && m[1], 'sin resultado de la medición');
      const r = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
      for (const [k] of CASES) {
        const x = r[k];
        assert.ok(x && x.mounted, `${k}: no se montó ${JSON.stringify(x)}`);
        assert.equal(x.page_overflow, false, `${k}: la página se sale de ancho`);
        assert.deepEqual(x.bad, [], `${k}: textos que desbordan`);
        assert.equal(x.cards, 4, `${k}: las 4 tarjetas pendientes`);
        assert.ok(x.min_btn_h >= 48, `${k}: botones de ${x.min_btn_h} px de alto`);
        assert.ok(x.min_btn_w >= 44, `${k}: botones de ${x.min_btn_w} px de ancho`);
        assert.deepEqual(x.low, [], `${k}: contraste bajo ${JSON.stringify(x.low)}`);
        assert.equal(x.badge, '12', `${k}: contador del menú`);
        assert.match(x.nav_active, /Cola de hoy/);
      }
      assert.equal(r['cola-390'].columns, 1, '390 px: una columna');
      assert.equal(r['cola-1440'].columns, 2, '1440 px: dos columnas');
    } finally {
      server.close();
      try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
    }
  });
