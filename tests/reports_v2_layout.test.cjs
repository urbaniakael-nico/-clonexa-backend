// Reportes v2 en Chrome headless con el portal real (client.html + client.js):
// a 1280 y 375 px, ningún texto desborda, contraste AA, sin menú lateral, sin
// CSV ni KPIs, seis cifras, el emergente, inglés y el "solo del dueño y del
// director". Con el interruptor apagado, la pantalla de siempre. Si no hay
// Chrome, la prueba se salta.
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
const CID = '76974191-1dc6-4eb4-9b19-7d1e9ad82946';
const TYPES = { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json' };
const CASES = [
  ['main-1280', 1280, ''], ['main-375', 375, ''], ['box-1280', 1280, '&modal=box'], ['person-375', 375, '&modal=person'],
  ['en-1280', 1280, '&lang=en'], ['denied-375', 375, '&denied=1'], ['off-1280', 1280, '&v2=0'],
];

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/client.html') {
      const html = fs.readFileSync(path.join(WEB, 'client.html'), 'utf8').replace('<link rel="stylesheet"', '<script src="/__preview.js"></script>\n  <link rel="stylesheet"');
      return send(html, 'text/html');
    }
    if (url.pathname === '/__preview.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'reports_v2_preview.js')), TYPES['.js']);
    if (url.pathname === '/__payload.json') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'reports_v2_payload.json')), TYPES['.json']);
    if (url.pathname === '/__frames.html') {
      const frames = CASES.map(([k, w, q]) => `<iframe data-k="${k}" style="width:${w}px;height:1600px;border:0;display:block" src="/client.html?company_id=${CID}${q}"></iframe>`);
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
    execFile(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', `--user-data-dir=${profile}`, '--window-size=1400,1400', '--virtual-time-budget=24000', '--dump-dom', url],
      { timeout: 150000, maxBuffer: 64 * 1024 * 1024 }, (err, stdout) => (err ? reject(err) : resolve(stdout)));
  });
}

test('Reportes v2: sin desborde, AA, sin menú lateral ni CSV ni KPIs (1280 y 375 px); inglés; solo dueño y director; apagado = la de siempre',
  { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 300000 }, async () => {
    const server = await serve();
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-rr-layout-'));
    try {
      const html = await dump(`http://127.0.0.1:${server.address().port}/__frames.html`, profile);
      const m = html.match(/<pre id="all">([^<]*)<\/pre>/);
      assert.ok(m && m[1], 'sin resultado de la medición');
      const r = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
      for (const [k] of CASES.filter(([k]) => k !== 'off-1280')) {
        const x = r[k];
        assert.ok(x && x.mounted, `${k}: no se montó`);
        assert.equal(x.page_overflow, false, `${k}: la página se sale de ancho`);
        assert.deepEqual(x.bad, [], `${k}: textos que desbordan: ${JSON.stringify(x.bad)}`);
        assert.deepEqual(x.low_contrast, [], `${k}: contraste bajo: ${JSON.stringify(x.low_contrast)}`);
        assert.equal(x.sidebar, false, `${k}: sin menú lateral`);
        assert.equal(x.csv, false, `${k}: sin CSV`);
        assert.equal(x.kpis, false, `${k}: sin KPIs`);
      }
      assert.equal(r['main-1280'].figs, 6, 'seis cifras');
      assert.equal(r['en-1280'].english, true, 'en inglés con el idioma de la empresa');
      assert.equal(r['denied-375'].denied, true, '403: "solo del dueño y del director"');
      assert.equal(r['off-1280'].mounted, false, 'apagado: no se monta');
      assert.equal(r['off-1280'].sidebar, true, 'apagado: la pantalla de siempre (con su menú)');
    } finally {
      server.close();
      try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
    }
  });
