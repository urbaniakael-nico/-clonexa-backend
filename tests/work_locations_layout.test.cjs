// Lugares de trabajo: Personal (con lugar, filtro y selección) y CRM Campo por
// lugar sin textos cortados, sin desborde de página y con contraste AA (4.5:1)
// a 1280 y 390 px, con la marca de VOLTAGE (texto blanco sobre celeste), la
// demo y Velvet. En escritorio las secciones del CRM van en 2 columnas y en
// celular una debajo de otra. Con el interruptor apagado, CRM Campo es el de
// siempre. Usa el portal real (client.html + client.js) en Chrome headless.
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
const THEMES = (process.env.WL_THEMES || 'voltage,demo,velvet').split(',');
const WIDTHS = [1280, 390];
const TYPES = { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html' };
const CID = 'f1e8f774-f052-49ca-880a-268805f07db0';

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/client.html') {
      const html = fs.readFileSync(path.join(WEB, 'client.html'), 'utf8').replace('<link rel="stylesheet"', '<script src="/__preview.js"></script>\n  <link rel="stylesheet"');
      return send(html, 'text/html');
    }
    if (url.pathname === '/__preview.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'work_locations_preview.js')), TYPES['.js']);
    if (url.pathname === '/__frames.html') {
      const q = url.searchParams;
      const frames = WIDTHS.map((w) => `<iframe data-k="${w}" style="width:${w}px;height:1600px;border:0;display:block" src="/client.html?company_id=${CID}&theme=${q.get('theme')}&screen=${q.get('screen')}&wl=${q.get('wl')}"></iframe>`);
      return send(`<!doctype html><html><body style="margin:0">${frames.join('')}<pre id="all"></pre><script>
        setTimeout(() => { const out = {}; document.querySelectorAll('iframe').forEach((f) => { const d = f.contentDocument && f.contentDocument.getElementById('layout'); out[f.dataset.k] = d ? JSON.parse(d.textContent) : null; });
          document.getElementById('all').textContent = JSON.stringify(out); }, 13000);</script></body></html>`, 'text/html');
    }
    const file = url.pathname.startsWith('/client-static/') ? path.join(WEB, url.pathname.slice('/client-static/'.length)) : null;
    if (file && file.startsWith(WEB) && fs.existsSync(file) && fs.statSync(file).isFile()) return send(fs.readFileSync(file), TYPES[path.extname(file)] || 'application/octet-stream');
    res.writeHead(404); res.end();
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

function dump(url, profile) {
  return new Promise((resolve, reject) => {
    execFile(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', `--user-data-dir=${profile}`, '--window-size=1400,1600', '--virtual-time-budget=20000', '--dump-dom', url],
      { timeout: 120000, maxBuffer: 64 * 1024 * 1024 }, (err, stdout) => (err ? reject(err) : resolve(stdout)));
  });
}

async function measure(port, profile, theme, screen, wl) {
  const html = await dump(`http://127.0.0.1:${port}/__frames.html?theme=${theme}&screen=${screen}&wl=${wl}`, profile);
  const m = html.match(/<pre id="all">([^<]*)<\/pre>/);
  assert.ok(m && m[1], `${theme} ${screen}: sin resultado de la medición`);
  return JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
}

test('Lugares de trabajo: Personal y CRM Campo a 1280 y 390 px sin desbordes y con contraste AA; apagado = CRM de siempre', { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 600000 }, async () => {
  const server = await serve();
  const port = server.address().port;
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-wl-layout-'));
  try {
    for (const theme of THEMES) {
      for (const screen of ['personal', 'crm']) {
        const results = await measure(port, profile, theme, screen, 1);
        for (const w of WIDTHS) {
          const r = results[w];
          const tag = `${theme} ${screen} ${w}px`;
          assert.ok(r && r.mounted, `${tag}: la pantalla no se dibujó (${JSON.stringify(r)})`);
          assert.ok(r.places_ui, `${tag}: no se ve nada de lugares`);
          assert.equal(r.page_overflow, false, `${tag}: la página se sale de ancho`);
          assert.deepEqual(r.bad, [], `${tag}: textos que desbordan: ${JSON.stringify(r.bad)}`);
          assert.deepEqual(r.low_contrast, [], `${tag}: contraste bajo AA: ${JSON.stringify(r.low_contrast)}`);
          if (screen === 'personal') assert.equal(r.table_scroll, false, `${tag}: la tabla necesita desplazamiento lateral (${r.table_scroll})`);
          if (screen === 'crm') {
            assert.deepEqual(r.tabs.map((t) => t.replace(/\s*\(\d+\)$/, '')), ['Todas', 'Virginia', 'Alabama', 'Sin asignar'], tag);
            assert.equal(r.rows, 67, `${tag}: las 67 personas activas en la lista (${r.rows})`);
            assert.equal(r.legacy_crm, false, `${tag}: no se dibuja el CRM de siempre`);
            const [va, al] = r.sections;
            if (w === 1280) assert.ok(va.top === al.top && al.left > va.left, `${tag}: 2 columnas (${JSON.stringify(r.sections)})`);
            else assert.ok(al.top > va.top && al.left === va.left, `${tag}: una debajo de otra (${JSON.stringify(r.sections)})`);
          }
        }
      }
    }
    const off = await measure(port, profile, 'voltage', 'crm', 0);
    for (const w of WIDTHS) {
      assert.ok(off[w] && off[w].legacy_crm, `apagado ${w}px: CRM Campo de siempre`);
      assert.equal(off[w].places_ui, false, `apagado ${w}px: nada de lugares`);
    }
  } finally {
    server.close();
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
  }
});
