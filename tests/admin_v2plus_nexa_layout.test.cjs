// Conversaciones Nexa en Chrome headless con la consola v2+ real: a 1280 px la
// lista y el chat lado a lado; a 390 px la lista sola o el chat solo con
// "← Conversaciones". Ningún texto desborda y la página no se sale de ancho.
// Si no hay Chrome, la prueba se salta.
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
const CASES = [['open-1280', 1280, '?open=1'], ['list-1280', 1280, ''], ['open-390', 390, '?open=1'], ['list-390', 390, '']];

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/admin-v2plus') {
      const html = fs.readFileSync(path.join(WEB, 'admin_v2plus.html'), 'utf8').replace('<link rel="stylesheet" href="/admin-v2plus.css"', '<script src="/__preview.js"></script>\n  <link rel="stylesheet" href="/admin-v2plus.css"');
      return send(html, 'text/html');
    }
    if (url.pathname === '/__preview.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'nexa_wa_preview.js')), 'application/javascript');
    if (url.pathname === '/__frames.html') {
      const frames = CASES.map(([k, w, q]) => `<iframe data-k="${k}" style="width:${w}px;height:1100px;border:0;display:block" src="/admin-v2plus${q}"></iframe>`);
      return send(`<!doctype html><html><body style="margin:0">${frames.join('')}<pre id="all"></pre><script>
        setTimeout(() => { const out = {}; document.querySelectorAll('iframe').forEach((f) => { const d = f.contentDocument && f.contentDocument.getElementById('layout'); out[f.dataset.k] = d ? JSON.parse(d.textContent) : null; });
          document.getElementById('all').textContent = JSON.stringify(out); }, 9000);</script></body></html>`, 'text/html');
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
    execFile(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', `--user-data-dir=${profile}`, '--window-size=1400,1400', '--virtual-time-budget=15000', '--dump-dom', url],
      { timeout: 120000, maxBuffer: 64 * 1024 * 1024 }, (err, stdout) => (err ? reject(err) : resolve(stdout)));
  });
}

test('Conversaciones Nexa: sin desborde a 1280 y 390 px; lado a lado en escritorio, una cosa a la vez en el celular',
  { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 200000 }, async () => {
    const server = await serve();
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-nx-layout-'));
    try {
      const html = await dump(`http://127.0.0.1:${server.address().port}/__frames.html`, profile);
      const m = html.match(/<pre id="all">([^<]*)<\/pre>/);
      assert.ok(m && m[1], 'sin resultado de la medición');
      const r = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
      for (const [k] of CASES) {
        const x = r[k];
        assert.ok(x && x.mounted, `${k}: no se montó`);
        assert.equal(x.page_overflow, false, `${k}: la página se sale de ancho: ${JSON.stringify(x.wide)}`);
        assert.deepEqual(x.bad, [], `${k}: textos que desbordan: ${JSON.stringify(x.bad)}`);
      }
      const desk = r['open-1280'];
      assert.ok(desk.list && desk.detail, '1280: lista y chat visibles');
      assert.equal(desk.back, false, '1280: sin botón de volver');
      assert.ok(desk.list_box.right <= desk.detail_box.left, '1280: lado a lado');
      assert.equal(desk.rows, 5);
      assert.equal(desk.bubbles, 7);
      assert.ok(r['list-1280'].list && !r['list-1280'].detail, '1280 sin abrir: la lista y "Elige una conversación"');
      assert.ok(r['open-390'].detail && !r['open-390'].list && r['open-390'].back, '390 abierta: solo el chat, con volver');
      assert.ok(r['list-390'].list && !r['list-390'].detail, '390: solo la lista');
    } finally {
      server.close();
      try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
    }
  });
