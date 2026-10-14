// Juegos en vivo en Chrome headless: pantalla del bar a 1920×1080 y 1280×720
// (espera, ruleta, registro, en juego, podio) y celular a 375 px (inscripción,
// espera, memoria, trivia, perdiste, ganaste): sin desborde, contraste AA, letras
// grandes en la pantalla, nombres de 20 caracteres sin cortar e inglés.
// Si no hay Chrome, se salta. CX_GAMES_SHOTS=<carpeta> guarda capturas PNG.
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
const TYPES = { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html' };
const SCREENS = ['idle', 'roulette', 'registration', 'playing', 'podium'];
const PHONES = ['join', 'wait', 'memory', 'trivia', 'lost', 'win'];
const CASES = [
  ...SCREENS.flatMap((s) => [[`screen-${s}-1080`, 1920, 1080, `/juegos/screen.html?t=tok&scene=${s}`], [`screen-${s}-720`, 1280, 720, `/juegos/screen.html?t=tok&scene=${s}`]]),
  ['screen-en-720', 1280, 720, '/juegos/screen.html?t=tok&scene=registration&lang=en'], ['screen-denied-720', 1280, 720, '/juegos/screen.html?t=bad&denied=1'],
  ...PHONES.map((v) => [`phone-${v}`, 375, 812, `/juegos/play.html?r=round-${v}.sig&view=${v}`]), ['phone-en', 375, 812, '/juegos/play.html?r=round-en.sig&view=trivia&lang=en'],
];

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    const page = { '/juegos/screen.html': 'loyalty_games_screen.html', '/juegos/play.html': 'loyalty_games_play.html' }[url.pathname];
    if (page) return send(fs.readFileSync(path.join(WEB, page), 'utf8').replace('<link rel="stylesheet"', '<script src="/__preview.js"></script>\n  <link rel="stylesheet"'), 'text/html');
    if (/^\/api\/v1\/loyalty-games\/screen\/[^/]+\/qr\.svg$/.test(url.pathname)) {  // un QR de ejemplo (el real lo hace segno en el servidor)
      let cells = '';
      for (let y = 0; y < 25; y += 1) for (let x = 0; x < 25; x += 1) if (((x * 7 + y * 13) % 5) < 2 || (x < 7 && y < 7) || (x > 17 && y < 7) || (x < 7 && y > 17)) cells += `<rect x="${x}" y="${y}" width="1" height="1"/>`;
      return send(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 25 25"><rect width="25" height="25" fill="#fff"/><g fill="#0b0a14">${cells}</g></svg>`, 'image/svg+xml');
    }
    if (url.pathname === '/__preview.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'loyalty_games_preview.js')), TYPES['.js']);
    if (url.pathname === '/__frames.html') {
      const frames = CASES.map(([k, w, hh, src]) => `<iframe data-k="${k}" style="width:${w}px;height:${hh}px;border:0;display:block" src="${src}"></iframe>`);
      return send(`<!doctype html><html><body style="margin:0">${frames.join('')}<pre id="all"></pre><script>
        setTimeout(() => { const out = {}; document.querySelectorAll('iframe').forEach((f) => { const d = f.contentDocument && f.contentDocument.getElementById('layout'); out[f.dataset.k] = d ? JSON.parse(d.textContent) : null; });
          document.getElementById('all').textContent = JSON.stringify(out); }, 9000);</script></body></html>`, 'text/html');
    }
    if (url.pathname === '/__one.html') {
      const w = Number(url.searchParams.get('w')), hh = Number(url.searchParams.get('h'));
      return send(`<!doctype html><html><body style="margin:0;background:#000"><iframe style="width:${w}px;height:${hh}px;border:0;display:block" src="${url.searchParams.get('src')}"></iframe></body></html>`, 'text/html');
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

test('Juegos en vivo: pantalla del bar 16:9 y celular 375 px sin desborde, AA y letras grandes; inglés; token inválido',
  { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 400000 }, async () => {
    const server = await serve();
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-lg-layout-'));
    const base = `http://127.0.0.1:${server.address().port}`;
    try {
      const html = await chrome([`--user-data-dir=${profile}`, '--window-size=2000,1400', '--virtual-time-budget=16000', '--dump-dom', `${base}/__frames.html`]);
      const m = html.match(/<pre id="all">([^<]*)<\/pre>/);
      assert.ok(m && m[1], 'sin resultado de la medición');
      const r = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
      for (const [k] of CASES) {
        const x = r[k];
        assert.ok(x && x.mounted, `${k}: no se montó ${JSON.stringify(x)}`);
        assert.equal(x.page_overflow, false, `${k}: la página se sale de ancho`);
        assert.equal(x.vert, false, `${k}: la pantalla se sale de alto`);
        assert.deepEqual(x.bad, [], `${k}: textos que desbordan: ${JSON.stringify(x.bad)}`);
        assert.deepEqual(x.low_contrast, [], `${k}: contraste bajo: ${JSON.stringify(x.low_contrast)}`);
        assert.deepEqual(x.small, [], `${k}: letra pequeña para ver a distancia: ${JSON.stringify(x.small)}`);
      }
      for (const res of ['1080', '720']) {
        assert.equal(r[`screen-registration-${res}`].names, 14, 'los nombres inscritos');
        assert.match(r[`screen-registration-${res}`].text, /Escanea y juega[\s\S]*14 inscritos/);
        assert.equal(r[`screen-playing-${res}`].rank, 10, 'ranking en vivo');
        assert.equal(r[`screen-podium-${res}`].steps, 3, 'podio');
        assert.match(r[`screen-podium-${res}`].text, /Reclama con tu documento/);
        assert.match(r[`screen-roulette-${res}`].text, /37[\s\S]*Shot de tequila[\s\S]*Sacados esta noche/);
      }
      assert.match(r['screen-en-720'].text, /Scan and play/);
      assert.match(r['screen-denied-720'].text, /Esta pantalla no está autorizada/);
      assert.match(r['phone-join'].text, /Autorizo el tratamiento de mis datos para este concurso \(Ley 1581\)/);
      assert.match(r['phone-wait'].text, /¡Listo, Camila!/);
      assert.equal(r['phone-memory'].cards, 10);
      assert.equal(r['phone-memory'].faces, 3, 'solo las caras que el servidor reveló');
      assert.equal(r['phone-trivia'].opts, 3);
      assert.match(r['phone-lost'].text, /Se acabó el tiempo, perdiste/);
      assert.match(r['phone-win'].text, /¡Quedaste en el puesto 1![\s\S]*Reclama con tu documento/);
      assert.match(r['phone-en'].text, /Question 3 of 5/);
      const shots = process.env.CX_GAMES_SHOTS;
      if (shots) {
        fs.mkdirSync(shots, { recursive: true });
        for (const [k, w, hh, src] of CASES) {
          await chrome([`--user-data-dir=${profile}-${k}`, `--window-size=${w},${hh}`, '--hide-scrollbars', '--virtual-time-budget=6000',
            `--screenshot=${path.join(shots, `juegos-${k}.png`)}`, `${base}/__one.html?w=${w}&h=${hh}&src=${encodeURIComponent(src)}`]);
        }
      }
    } finally {
      server.close();
      try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
    }
  });
