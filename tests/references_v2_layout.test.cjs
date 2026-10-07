// Referencias v2: ningún texto desborda su contenedor (scrollWidth > clientWidth)
// en las tres pestañas, a 1280, 1024 y 375 px, con el tema de Velvet y el de la
// demo. Usa el portal real (client.html + client.js) con datos de ejemplo en
// Chrome headless. Si no hay Chrome en la máquina, la prueba se salta.
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
const TABS = ['catalogo', 'cortes', 'estado'];
const WIDTHS = [1280, 1024, 375];
const IDS = { velvet: 'd63cf68c-be5b-4a30-aee4-341973018db1', demo: 'f8503267-0111-46b4-84c5-ee339cc6273e' };
const TYPES = { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml' };

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/client.html') {
      const html = fs.readFileSync(path.join(WEB, 'client.html'), 'utf8').replace('<link rel="stylesheet"', '<script src="/__preview.js"></script>\n  <link rel="stylesheet"');
      return send(html, 'text/html');
    }
    if (url.pathname === '/__preview.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'references_v2_preview.js')), TYPES['.js']);
    if (url.pathname === '/client-static/garment_catalog.json') return send(fs.readFileSync(path.join(ROOT, 'app', 'services', 'garment_catalog.json')), TYPES['.json']);
    if (url.pathname === '/__frames.html') {
      const q = url.searchParams;
      const frames = TABS.flatMap((tab) => WIDTHS.map((w) => `<iframe data-k="${tab}-${w}" style="width:${w}px;height:1400px;border:0;display:block" src="/client.html?company_id=${IDS[q.get('theme')]}&theme=${q.get('theme')}&tab=${tab}"></iframe>`));
      return send(`<!doctype html><html><body style="margin:0">${frames.join('')}<pre id="all"></pre><script>
        setTimeout(() => { const out = {}; document.querySelectorAll('iframe').forEach((f) => { const d = f.contentDocument && f.contentDocument.getElementById('layout'); out[f.dataset.k] = d ? JSON.parse(d.textContent) : null; });
          document.getElementById('all').textContent = JSON.stringify(out); }, 15000);</script></body></html>`, 'text/html');
    }
    const file = url.pathname.startsWith('/client-static/') ? path.join(WEB, url.pathname.slice('/client-static/'.length)) : null;
    if (file && file.startsWith(WEB) && fs.existsSync(file) && fs.statSync(file).isFile()) return send(fs.readFileSync(file), TYPES[path.extname(file)] || 'application/octet-stream');
    res.writeHead(404); res.end();
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

function dump(url, profile) {
  return new Promise((resolve, reject) => {
    execFile(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', `--user-data-dir=${profile}`, '--window-size=1400,1400', '--virtual-time-budget=22000', '--dump-dom', url],
      { timeout: 120000, maxBuffer: 64 * 1024 * 1024 }, (err, stdout) => (err ? reject(err) : resolve(stdout)));
  });
}

test('ningún texto desborda y las etiquetas van en fila en Catálogo, Cortes y Estado (1280, 1024 y 375 px; Velvet y demo)', { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 300000 }, async () => {
  const server = await serve();
  const port = server.address().port;
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-rv-layout-'));
  try {
    for (const theme of Object.keys(IDS)) {
      const html = await dump(`http://127.0.0.1:${port}/__frames.html?theme=${theme}`, profile);
      const m = html.match(/<pre id="all">([^<]*)<\/pre>/);
      assert.ok(m && m[1], `${theme}: sin resultado de la medición`);
      const results = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
      for (const tab of TABS) {
        for (const w of WIDTHS) {
          const r = results[`${tab}-${w}`];
          assert.ok(r, `${theme} ${tab} ${w}px: la pantalla no se dibujó`);
          assert.equal(r.page_overflow, false, `${theme} ${tab} ${w}px: la página se sale de ancho`);
          assert.deepEqual(r.bad, [], `${theme} ${tab} ${w}px: textos que desbordan: ${JSON.stringify(r.bad)}`);
          assert.deepEqual(r.stacked, [], `${theme} ${tab} ${w}px: etiquetas apiladas en: ${JSON.stringify(r.stacked)}`);
        }
      }
    }
  } finally {
    server.close();
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
  }
});
