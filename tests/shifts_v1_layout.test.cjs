// Turnos (modulo shifts) en Chrome headless con el portal real (client.html +
// client.js): Malla, Cambios, Configuracion y Cambio de turno a 1280 y 375 px,
// sin desborde, contraste AA, ingles y el 403. Si no hay Chrome, se salta.
// CX_SHIFTS_SHOTS=<carpeta> guarda ademas capturas PNG de cada caso.
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
  ['grid-1280', 1280, ''], ['grid-375', 375, ''], ['draft-1280', 1280, '&status=draft&role=owner'], ['draft-375', 375, '&status=draft&role=owner'],
  ['changes-1280', 1280, '&tab=changes'], ['changes-375', 375, '&tab=changes'], ['config-1280', 1280, '&tab=config'], ['config-375', 375, '&tab=config'],
  ['modal-1280', 1280, '&modal=1'], ['modal-375', 375, '&modal=1'], ['en-1280', 1280, '&lang=en'], ['denied-375', 375, '&denied=1'],
];

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/client.html') {
      const html = fs.readFileSync(path.join(WEB, 'client.html'), 'utf8').replace('<link rel="stylesheet"', '<script src="/__preview.js"></script>\n  <link rel="stylesheet"');
      return send(html, 'text/html');
    }
    if (url.pathname === '/__preview.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'shifts_v1_preview.js')), TYPES['.js']);
    if (url.pathname === '/__frames.html') {
      const frames = CASES.map(([k, w, q]) => `<iframe data-k="${k}" style="width:${w}px;height:1800px;border:0;display:block" src="/client.html?company_id=${CID}${q}"></iframe>`);
      return send(`<!doctype html><html><body style="margin:0">${frames.join('')}<pre id="all"></pre><script>
        setTimeout(() => { const out = {}; document.querySelectorAll('iframe').forEach((f) => { const d = f.contentDocument && f.contentDocument.getElementById('layout'); out[f.dataset.k] = d ? JSON.parse(d.textContent) : null; });
          document.getElementById('all').textContent = JSON.stringify(out); }, 20000);</script></body></html>`, 'text/html');
    }
    if (url.pathname === '/__one.html') {  // captura: un solo caso en un iframe del ancho exacto
      const w = Number(url.searchParams.get('w')) || 1280;
      return send(`<!doctype html><html><body style="margin:0;background:#fff"><iframe style="width:${w}px;height:1500px;border:0;display:block" src="/client.html?company_id=${CID}${url.searchParams.get('q') || ''}"></iframe></body></html>`, 'text/html');
    }
    const file = url.pathname.startsWith('/client-static/') ? path.join(WEB, url.pathname.slice('/client-static/'.length)) : null;
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

test('Turnos: Malla, Cambios, Configuracion y Cambio de turno sin desborde y con AA (1280 y 375 px); ingles; 403',
  { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 400000 }, async () => {
    const server = await serve();
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-sh-layout-'));
    const base = `http://127.0.0.1:${server.address().port}`;
    try {
      const html = await chrome([`--user-data-dir=${profile}`, '--window-size=1400,1400', '--virtual-time-budget=30000', '--dump-dom', `${base}/__frames.html`]);
      const m = html.match(/<pre id="all">([^<]*)<\/pre>/);
      assert.ok(m && m[1], 'sin resultado de la medición');
      const r = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
      for (const [k] of CASES) {
        const x = r[k];
        assert.ok(x && x.mounted, `${k}: no se montó ${JSON.stringify(x)}`);
        assert.equal(x.page_overflow, false, `${k}: la página se sale de ancho`);
        assert.deepEqual(x.bad, [], `${k}: textos que desbordan: ${JSON.stringify(x.bad)}`);
        assert.deepEqual(x.low_contrast, [], `${k}: contraste bajo: ${JSON.stringify(x.low_contrast)}`);
      }
      for (const k of ['grid-1280', 'grid-375']) {
        assert.equal(r[k].rows, 6, 'una fila por persona');
        assert.equal(r[k].cells, 42, 'una celda por día');
        assert.match(r[k].total, /^\d+ h \d{2} min$/);
        assert.equal(r[k].ok, true, '✓ Cobertura completa');
        assert.equal(r[k].change_btn, true, 'el supervisor ve ⇄ Cambio de turno');
      }
      assert.deepEqual(r['grid-1280'].tabs, ['Malla', 'Cambios (1)', 'Configuración']);
      assert.equal(r['draft-1280'].gap, true, 'el hueco se dice: "Falta 1 operario · Noche · jue 15"');
      assert.equal(r['draft-1280'].change_btn, false, 'el dueño no crea cambios');
      assert.equal(r['modal-375'].modal, true, 'emergente de Cambio de turno');
      assert.equal(r['en-1280'].english, true);
      assert.equal(r['denied-375'].denied, true);
      const shots = process.env.CX_SHIFTS_SHOTS;
      if (shots) {
        fs.mkdirSync(shots, { recursive: true });
        for (const [k, w, q] of CASES) {
          await chrome([`--user-data-dir=${profile}-${k}`, `--window-size=${w},1500`, '--hide-scrollbars', '--virtual-time-budget=12000',
            `--screenshot=${path.join(shots, `turnos-${k}.png`)}`, `${base}/__one.html?w=${w}&q=${encodeURIComponent(q)}`]);
        }
      }
    } finally {
      server.close();
      try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
    }
  });
