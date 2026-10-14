// Juegos en vivo · panel dentro del portal real (client.html + client.js): el
// botón aparece en Fidelización solo con el interruptor; En vivo, Configuración,
// Preguntas e Historial a 1280 y 375 px sin desborde y con AA; el barman no ve
// la configuración ni el enlace de la pantalla. Si no hay Chrome, se salta.
// CX_GAMES_SHOTS=<carpeta> guarda capturas PNG.
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
  ['live-admin-1280', 1280, ''], ['live-admin-375', 375, ''], ['live-barman-375', 375, '&role=barman'], ['config-1280', 1280, '&tab=config'], ['config-375', 375, '&tab=config'],
  ['questions-1280', 1280, '&tab=questions'], ['questions-375', 375, '&tab=questions'], ['history-1280', 1280, '&tab=history'], ['history-375', 375, '&tab=history'], ['off-1280', 1280, '&off=1'],
  ['config-low-375', 375, '&tab=config&low=1'],
];

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/client.html') {
      const html = fs.readFileSync(path.join(WEB, 'client.html'), 'utf8').replace('<link rel="stylesheet"', '<script src="/__preview.js"></script>\n  <link rel="stylesheet"');
      return send(html, 'text/html');
    }
    if (url.pathname === '/__preview.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'loyalty_games_panel_preview.js')), TYPES['.js']);
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

test('Juegos en vivo · panel: botón solo con el interruptor; sin desborde y con AA a 1280 y 375 px; barman sin configuración',
  { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 400000 }, async () => {
    const server = await serve();
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-lgp-layout-'));
    const base = `http://127.0.0.1:${server.address().port}`;
    try {
      const html = await chrome([`--user-data-dir=${profile}`, '--window-size=1400,1400', '--virtual-time-budget=30000', '--dump-dom', `${base}/__frames.html`]);
      const m = html.match(/<pre id="all">([^<]*)<\/pre>/);
      assert.ok(m && m[1], 'sin resultado de la medición');
      const r = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
      for (const [k] of CASES.filter(([k]) => k !== 'off-1280')) {
        const x = r[k];
        assert.ok(x && x.mounted, `${k}: no se montó ${JSON.stringify(x)}`);
        assert.equal(x.page_overflow, false, `${k}: la página se sale de ancho`);
        assert.deepEqual(x.bad, [], `${k}: textos que desbordan: ${JSON.stringify(x.bad)}`);
        assert.deepEqual(x.low_contrast, [], `${k}: contraste bajo: ${JSON.stringify(x.low_contrast)}`);
      }
      assert.deepEqual(r['live-admin-1280'].tabs, ['En vivo', 'Configuración', 'Preguntas', 'Historial']);
      assert.equal(r['live-admin-1280'].screen_link, true);
      assert.equal(r['live-admin-1280'].validate, true);
      assert.deepEqual(r['live-barman-375'].tabs, ['En vivo'], 'el barman no ve Configuración ni Preguntas');
      assert.equal(r['live-barman-375'].screen_link, false);
      assert.equal(r['live-barman-375'].spin, true);
      assert.equal(r['live-admin-1280'].pairs, 5, 'el barman elige 5, 7, 10, 13 o 15 parejas al abrir');
      assert.deepEqual(r['live-barman-375'].opens, ['memory', 'trivia', 'differences']);
      assert.equal(r['config-1280'].scenes, 4, 'escenas activas');
      assert.equal(r['config-1280'].memtimes, 5, 'tiempo editable por cada cantidad de parejas');
      assert.equal(r['config-low-375'].warning, true, 'avisa si un nivel tiene menos de 4 preguntas activas');
      assert.equal(r['config-1280'].warning, false);
      assert.equal(r['off-1280'].mounted, false, 'interruptor apagado: no aparece');
      assert.equal(r['off-1280'].button, false, 'interruptor apagado: sin botón en Fidelización');
      const shots = process.env.CX_GAMES_SHOTS;
      if (shots) {
        fs.mkdirSync(shots, { recursive: true });
        for (const [k, w, q] of CASES) {
          await chrome([`--user-data-dir=${profile}-${k}`, `--window-size=${w},1500`, '--hide-scrollbars', '--virtual-time-budget=14000',
            `--screenshot=${path.join(shots, `panel-${k}.png`)}`, `${base}/__one.html?w=${w}&q=${encodeURIComponent(q)}`]);
        }
      }
    } finally {
      server.close();
      try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
    }
  });
