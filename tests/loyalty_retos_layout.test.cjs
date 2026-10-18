// Retos para las mesas · dentro del portal real (client.html + client.js) y el QR
// de la mesa (hospitality_order.html): tarjetas de tipo, En curso, asistente en sus
// 3 pasos, historial y la polla en el QR (abierta, cerrada, empate y ganador) a
// 1280 y 375 px, sin desborde y con contraste AA. Con el interruptor apagado queda
// la pantalla de siempre. Si no hay Chrome, se salta. CX_RETOS_SHOTS=<carpeta> guarda PNG.
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
const CID = '21a3065e-0000-4000-8000-00000000c0de';
const TYPES = { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png' };
const PANEL = [
  ['main-1280', 1280, ''], ['main-375', 375, ''],
  ['wiz1-polla-1280', 1280, '&wiz=score_pool&step=1'], ['wiz1-polla-375', 375, '&wiz=score_pool&step=1'],
  ['wiz2-consumo-1280', 1280, '&wiz=consumption&step=2'], ['wiz2-consumo-375', 375, '&wiz=consumption&step=2&custom=1'],
  ['wiz1-concurso-375', 375, '&wiz=vote_poll&step=1&mode=participants'],
  ['wiz3-concurso-1280', 1280, '&wiz=vote_poll&step=3&mode=yes_no'], ['wiz3-polla-375', 375, '&wiz=score_pool&step=3'],
  ['history-1280', 1280, '&view=history'], ['history-375', 375, '&view=history'], ['off-1280', 1280, '&off=1'],
];
const QR = [['qr-open-375', 375, '&qr=open'], ['qr-closed-375', 375, '&qr=closed'], ['qr-tie-375', 375, '&qr=tie'], ['qr-win-375', 375, '&qr=win']];

function page(file, fixture) {
  return fs.readFileSync(path.join(WEB, file), 'utf8').replace(/<script|<link rel="stylesheet"/, (m) => `<script src="/__${fixture}.js"></script>\n  ${m}`);
}

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/client.html') return send(page('client.html', 'panel'), 'text/html');
    if (url.pathname === '/ordenar') return send(page('hospitality_order.html', 'qr'), 'text/html');
    if (url.pathname === '/__panel.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'loyalty_retos_preview.js')), TYPES['.js']);
    if (url.pathname === '/__qr.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'loyalty_retos_qr_preview.js')), TYPES['.js']);
    if (url.pathname === '/__frames.html') {
      const src = ([k, w, q]) => `<iframe data-k="${k}" style="width:${w}px;height:2200px;border:0;display:block" src="${k.startsWith('qr-') ? `/ordenar?company_id=${CID}&mesa=Mesa%204&scroll=0` : `/client.html?company_id=${CID}`}${q}"></iframe>`;
      return send(`<!doctype html><html><body style="margin:0">${[...PANEL, ...QR].map(src).join('')}<pre id="all"></pre><script>
        setTimeout(() => { const out = {}; document.querySelectorAll('iframe').forEach((f) => { const d = f.contentDocument && f.contentDocument.getElementById('layout'); out[f.dataset.k] = d ? JSON.parse(d.textContent) : null; });
          document.getElementById('all').textContent = JSON.stringify(out); }, 24000);</script></body></html>`, 'text/html');
    }
    if (url.pathname === '/__one.html') {
      const w = Number(url.searchParams.get('w')) || 1280;
      const hgt = Number(url.searchParams.get('h')) || 1500;
      const target = url.searchParams.get('qr') ? `/ordenar?company_id=${CID}&mesa=Mesa%204${url.searchParams.get('q') || ''}` : `/client.html?company_id=${CID}${url.searchParams.get('q') || ''}`;
      return send(`<!doctype html><html><body style="margin:0;background:#fff"><iframe style="width:${w}px;height:${hgt}px;border:0;display:block" src="${target}"></iframe></body></html>`, 'text/html');
    }
    const file = url.pathname.startsWith('/client-static/') ? path.join(WEB, url.pathname.slice('/client-static/'.length)) : null;
    if (file && file.startsWith(WEB) && fs.existsSync(file) && fs.statSync(file).isFile()) return send(fs.readFileSync(file), TYPES[path.extname(file)] || 'application/octet-stream');
    res.writeHead(404); res.end();
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

function chrome(args) {
  return new Promise((resolve, reject) => {
    execFile(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', ...args], { timeout: 240000, maxBuffer: 64 * 1024 * 1024 }, (err, stdout) => (err ? reject(err) : resolve(stdout)));
  });
}

test('Retos para las mesas: pantalla nueva y QR de la mesa sin desborde y con AA a 1280 y 375 px; apagado = pantalla de siempre',
  { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 500000 }, async () => {
    const server = await serve();
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-rt-layout-'));
    const base = `http://127.0.0.1:${server.address().port}`;
    try {
      const html = await chrome([`--user-data-dir=${profile}`, '--window-size=1400,1400', '--virtual-time-budget=34000', '--dump-dom', `${base}/__frames.html`]);
      const m = html.match(/<pre id="all">([^<]*)<\/pre>/);
      assert.ok(m && m[1], 'sin resultado de la medición');
      const r = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
      for (const [k] of [...PANEL, ...QR].filter(([k]) => k !== 'off-1280')) {
        const x = r[k];
        assert.ok(x && x.mounted, `${k}: no se montó ${JSON.stringify(x)}`);
        assert.equal(x.page_overflow, false, `${k}: la página se sale de ancho`);
        assert.deepEqual(x.bad, [], `${k}: textos que desbordan: ${JSON.stringify(x.bad)}`);
        assert.deepEqual(x.low_contrast, [], `${k}: contraste bajo: ${JSON.stringify(x.low_contrast)}`);
        if (x.phone_low) assert.deepEqual(x.phone_low, [], `${k}: contraste bajo en la maqueta del QR`);
      }
      assert.equal(r['main-1280'].types, 3);
      assert.equal(r['main-1280'].live, 3, 'tres retos en curso');
      assert.match(r['main-375'].text, /Ya hay una polla en curso[\s\S]*Desempatar con Juego en vivo[\s\S]*Cerrar votación/);
      assert.match(r['wiz1-polla-1280'].step, /Qué/);
      assert.match(r['wiz2-consumo-1280'].step, /Cuándo/);
      assert.match(r['wiz2-consumo-1280'].text, /Jornada del bar/);
      assert.match(r['wiz3-concurso-1280'].step, /Revisar/);
      assert.equal(r['wiz3-concurso-1280'].phone, true, 'maqueta del celular');
      assert.match(r['history-1280'].text, /Premios por entregar|Historial/);
      assert.equal(r['off-1280'].mounted, false);
      assert.equal(r['off-1280'].title, 'Sorteos de consumo', 'interruptor apagado: la pantalla de siempre');
      assert.match(r['qr-open-375'].text, /Pronósticos cierran en/);
      assert.match(r['qr-closed-375'].text, /Pronósticos cerrados/);
      assert.match(r['qr-tie-375'].text, /Empate: prepárate para el desempate/);
      assert.match(r['qr-win-375'].text, /¡Ganaste!/);

      const shots = process.env.CX_RETOS_SHOTS;
      if (shots) {
        fs.mkdirSync(shots, { recursive: true });
        const list = [...PANEL.filter(([k]) => k !== 'off-1280').map(([k, w, q]) => [k, w, q, '', 1600]), ...QR.map(([k, w, q]) => [k, w, q, '1', 900])];
        for (const [k, w, q, qr, hgt] of list) {
          await chrome([`--user-data-dir=${profile}`, `--window-size=${w},${hgt}`, '--hide-scrollbars', '--virtual-time-budget=9000', `--screenshot=${path.join(shots, `${k}.png`)}`,
            `${base}/__one.html?w=${w}&h=${hgt}&q=${encodeURIComponent(q)}${qr ? '&qr=1' : ''}`]);
        }
      }
    } finally {
      server.close();
      try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
    }
  });
