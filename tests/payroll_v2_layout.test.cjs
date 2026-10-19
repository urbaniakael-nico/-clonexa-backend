// Nómina v2: con el tema de VOLTAGE (marca: primario y texto blancos), Velvet
// y ASADERO (marca clara), a 1280 y 375 px, con un registro desplegado y con
// la ventana de confirmar salida abierta: ningún texto desborda, la página no
// se sale de ancho, todo pasa AA, no hay CSV y el detalle muestra SOLO lo de
// esa empresa (ubicación, referencias o sección). Portal real con datos de
// ejemplo en Chrome headless; sin Chrome la prueba se salta.
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
const COMPANIES = {
  voltage: { id: '76974191-1dc6-4eb4-9b19-7d1e9ad82946', open: 'v1', shows: { gps: true, references: false, panels: false } },
  velvet: { id: 'd63cf68c-be5b-4a30-aee4-341973018db1', open: 'w1', shows: { gps: false, references: true, panels: false } },
  asadero: { id: '7625872c-f941-4479-a27b-f8443be953c5', open: 'a1', shows: { gps: false, references: false, panels: true } },
};
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
    if (url.pathname === '/__preview.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'payroll_v2_preview.js')), TYPES['.js']);
    if (url.pathname === '/__frames.html') {
      const key = url.searchParams.get('theme');
      const c = COMPANIES[key];
      const frames = WIDTHS.flatMap((w) => [['open', `&open=${c.open}`], ['modal', '&modal=1'], ['list', `&open=${c.open}&list=1`]].map(([k, q]) => `<iframe data-k="${w}-${k}" style="width:${w}px;height:1600px;border:0;display:block" src="/client.html?company_id=${c.id}&theme=${key}${q}"></iframe>`));
      return send(`<!doctype html><html><body style="margin:0">${frames.join('')}<pre id="all"></pre><script>
        setTimeout(() => { const out = {}; document.querySelectorAll('iframe').forEach((f) => { const d = f.contentDocument && f.contentDocument.getElementById('layout'); out[f.dataset.k] = d ? JSON.parse(d.textContent) : null; });
          document.getElementById('all').textContent = JSON.stringify(out); }, 14000);</script></body></html>`, 'text/html');
    }
    const file = url.pathname.startsWith('/client-static/') ? path.join(WEB, url.pathname.slice('/client-static/'.length)) : null;
    if (file && file.startsWith(WEB) && fs.existsSync(file) && fs.statSync(file).isFile()) return send(fs.readFileSync(file), TYPES[path.extname(file)] || 'application/octet-stream');
    res.writeHead(404); res.end();
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

function dump(url, profile) {
  return new Promise((resolve, reject) => {
    execFile(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', `--user-data-dir=${profile}`, '--window-size=1400,1400', '--virtual-time-budget=20000', '--dump-dom', url],
      { timeout: 150000, maxBuffer: 64 * 1024 * 1024 }, (err, stdout) => (err ? reject(err) : resolve(stdout)));
  });
}

test('Nómina v2: sin textos cortados, AA, sin CSV y solo los datos de cada empresa (VOLTAGE, Velvet, ASADERO; 1280 y 375 px)', { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 600000 }, async () => {
  const server = await serve();
  const port = server.address().port;
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-pv-layout-'));
  try {
    for (const [key, c] of Object.entries(COMPANIES)) {
      const html = await dump(`http://127.0.0.1:${port}/__frames.html?theme=${key}`, profile);
      const m = html.match(/<pre id="all">([^<]*)<\/pre>/);
      assert.ok(m && m[1], `${key}: sin resultado de la medición`);
      const results = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
      for (const w of WIDTHS) {
        for (const k of ['open', 'modal', 'list']) {
          const r = results[`${w}-${k}`];
          assert.ok(r && r.mounted, `${key} ${w}px ${k}: la pantalla nueva no se dibujó`);
          assert.equal(r.cards >= 3, true, `${key} ${w}px ${k}: faltan mini tarjetas`);
          assert.equal(r.page_overflow, false, `${key} ${w}px ${k}: la página se sale de ancho`);
          assert.deepEqual(r.bad, [], `${key} ${w}px ${k}: textos que desbordan: ${JSON.stringify(r.bad)}`);
          assert.deepEqual(r.low_contrast, [], `${key} ${w}px ${k}: contraste bajo AA: ${JSON.stringify(r.low_contrast)}`);
          assert.equal(r.csv, false, `${key} ${w}px ${k}: no debe haber nada de CSV`);
          assert.ok(r.calls.every((u) => !/export/i.test(u)), `${key}: no llama a ninguna exportación`);
          if (k === 'open') assert.deepEqual(r.shows, c.shows, `${key} ${w}px: el detalle muestra solo lo de su empresa`);
        }
      }
    }
  } finally {
    server.close();
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
  }
});
