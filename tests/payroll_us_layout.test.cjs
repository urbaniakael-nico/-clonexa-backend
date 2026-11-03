// 063A: Nómina EE. UU. por operación (us_payroll) con el tema de VOLTAGE a 1280 y 390 px:
// con dos personas desplegadas, con búsqueda, con el filtro Por confirmar y con la ventana de
// confirmar salida abierta: ningún texto desborda, la página no se sale de ancho, todo pasa
// AA y no aparece nada de ubicación, mapa ni notas. Portal real con datos de ejemplo
// (tests/fixtures/payroll_us_preview.js) en Chrome headless; sin Chrome la prueba se salta.
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
const CID = 'f1e8f774-f052-49ca-880a-268805f07db0';
const WIDTHS = [1280, 390];
const STATES = { open: '&open=1', search: '&q=hernandez', pending: '&filter=pending', modal: '&modal=1' };
const TYPES = { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json' };

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/client.html') {
      const html = fs.readFileSync(path.join(WEB, 'client.html'), 'utf8').replace('<link rel="stylesheet"', '<script src="/__preview.js"></script>\n  <link rel="stylesheet"');
      return send(html, 'text/html');
    }
    if (url.pathname === '/__preview.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'payroll_us_preview.js')), TYPES['.js']);
    if (url.pathname === '/__fix.json') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'us_payroll_caso.json')), TYPES['.json']);
    if (url.pathname === '/__frames.html') {
      const frames = WIDTHS.flatMap((w) => Object.entries(STATES).map(([k, q]) => `<iframe data-k="${w}-${k}" style="width:${w}px;height:1800px;border:0;display:block" src="/client.html?company_id=${CID}${q}"></iframe>`));
      return send(`<!doctype html><html><body style="margin:0">${frames.join('')}<pre id="all"></pre><script>
        setTimeout(() => { const out = {}; document.querySelectorAll('iframe').forEach((f) => { const d = f.contentDocument && f.contentDocument.getElementById('layout'); out[f.dataset.k] = d ? JSON.parse(d.textContent) : null; });
          document.getElementById('all').textContent = JSON.stringify(out); }, 16000);</script></body></html>`, 'text/html');
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
      { timeout: 150000, maxBuffer: 64 * 1024 * 1024 }, (err, stdout) => (err ? reject(err) : resolve(stdout)));
  });
}

test('063A Nómina por operación (VOLTAGE): sin textos cortados, AA y sin ubicación/mapa/notas a 1280 y 390 px', { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 300000 }, async () => {
  const server = await serve();
  const port = server.address().port;
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-pvu-layout-'));
  try {
    const html = await dump(`http://127.0.0.1:${port}/__frames.html`, profile);
    const m = html.match(/<pre id="all">([^<]*)<\/pre>/);
    assert.ok(m && m[1], 'sin resultado de la medición');
    const results = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
    for (const w of WIDTHS) {
      for (const k of Object.keys(STATES)) {
        const r = results[`${w}-${k}`];
        assert.ok(r && r.mounted, `${w}px ${k}: la pantalla nueva no se dibujó`);
        assert.equal(r.page_overflow, false, `${w}px ${k}: la página se sale de ancho: ${JSON.stringify(r.wide)}`);
        assert.deepEqual(r.bad, [], `${w}px ${k}: textos que desbordan: ${JSON.stringify(r.bad)}`);
        assert.deepEqual(r.low_contrast, [], `${w}px ${k}: contraste bajo AA: ${JSON.stringify(r.low_contrast)}`);
        assert.equal(r.banned, false, `${w}px ${k}: no debe mostrar ubicación, mapa ni notas`);
        assert.ok(r.calls.every((u) => !/export/i.test(u)), `${w}px ${k}: no descarga nada solo`);
      }
      assert.equal(results[`${w}-open`].tables, 2, `${w}px: una tabla por operación`);
      assert.equal(results[`${w}-open`].rows, 5, `${w}px: 5 personas (1 Virginia + 4 Alabama)`);
      assert.equal(results[`${w}-open`].days, 1, `${w}px: una persona abierta a la vez, con su semana día por día`);
      assert.equal(results[`${w}-search`].count, '1 de 5 personas', `${w}px: la búsqueda filtra sin tildes`);
      assert.equal(results[`${w}-pending`].rows, 2, `${w}px: Por confirmar = 2 personas`);
      assert.equal(results[`${w}-modal`].modal, true, `${w}px: ventana de confirmar salida`);
    }
  } finally {
    server.close();
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
  }
});
