// Personal v2: ningún texto desborda, la página no se sale de ancho y los
// títulos de columna, cifras, filtros y textos pasan contraste AA (4.5:1) a
// 1280 y 375 px, con el tema de Urbania (y su marca publicada: primario y
// texto blancos), el de la demo y el de Velvet. Usa el portal real
// (client.html + client.js) con datos de ejemplo en Chrome headless.
// Si no hay Chrome en la máquina, la prueba se salta.
const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFile } = require('node:child_process');

const ROOT = path.resolve(__dirname, '..');
const WEB = path.join(ROOT, 'app', 'web');
const CHROME = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
].find((p) => p && fs.existsSync(p));
const THEMES = ['urbania', 'urbania_marca', 'demo', 'velvet'];
const WIDTHS = [1280, 375];
const TYPES = { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json' };

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/client.html') {
      const html = fs.readFileSync(path.join(WEB, 'client.html'), 'utf8').replace('<link rel="stylesheet"', '<script src="/__preview.js"></script>\n  <link rel="stylesheet"');
      return send(html, 'text/html');
    }
    if (url.pathname === '/__preview.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'workforce_v2_preview.js')), TYPES['.js']);
    if (url.pathname === '/__frames.html') {
      const theme = url.searchParams.get('theme');
      const frames = WIDTHS.map((w) => `<iframe data-k="${w}" style="width:${w}px;height:1400px;border:0;display:block" src="/client.html?company_id=76974191-1dc6-4eb4-9b19-7d1e9ad82946&theme=${theme}&v2=1&roles=1"></iframe>`);
      return send(`<!doctype html><html><body style="margin:0">${frames.join('')}<pre id="all"></pre><script>
        setTimeout(() => { const out = {}; document.querySelectorAll('iframe').forEach((f) => { const d = f.contentDocument && f.contentDocument.getElementById('layout'); out[f.dataset.k] = d ? JSON.parse(d.textContent) : null; });
          document.getElementById('all').textContent = JSON.stringify(out); }, 12000);</script></body></html>`, 'text/html');
    }
    const file = url.pathname.startsWith('/client-static/') ? path.join(WEB, url.pathname.slice('/client-static/'.length)) : null;
    if (file && file.startsWith(WEB) && fs.existsSync(file) && fs.statSync(file).isFile()) return send(fs.readFileSync(file), TYPES[path.extname(file)] || 'application/octet-stream');
    res.writeHead(404); res.end();
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

function dump(url, profile) {
  return new Promise((resolve, reject) => {
    execFile(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', `--user-data-dir=${profile}`, '--window-size=1400,1400', '--virtual-time-budget=18000', '--dump-dom', url],
      { timeout: 120000, maxBuffer: 64 * 1024 * 1024 }, (err, stdout) => (err ? reject(err) : resolve(stdout)));
  });
}

test('Personal v2: sin textos cortados, sin desborde de página y contraste AA (1280 y 375 px; Urbania, su marca, demo y Velvet)', { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 400000 }, async () => {
  const server = await serve();
  const port = server.address().port;
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-wf-layout-'));
  try {
    for (const theme of THEMES) {
      const html = await dump(`http://127.0.0.1:${port}/__frames.html?theme=${theme}`, profile);
      const m = html.match(/<pre id="all">([^<]*)<\/pre>/);
      assert.ok(m && m[1], `${theme}: sin resultado de la medición`);
      const results = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
      for (const w of WIDTHS) {
        const r = results[w];
        assert.ok(r && r.mounted, `${theme} ${w}px: la pantalla nueva no se dibujó`);
        assert.equal(r.page_overflow, false, `${theme} ${w}px: la página se sale de ancho`);
        assert.deepEqual(r.bad, [], `${theme} ${w}px: textos que desbordan: ${JSON.stringify(r.bad)}`);
        assert.equal(r.table_scroll, false, `${theme} ${w}px: la tabla necesita desplazamiento lateral (${r.table_scroll})`);
        assert.deepEqual(r.low_contrast, [], `${theme} ${w}px: contraste bajo AA: ${JSON.stringify(r.low_contrast)}`);
      }
    }
  } finally {
    server.close();
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
  }
});
