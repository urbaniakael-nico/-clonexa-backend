// Carta en modo video en un CELULAR de verdad (emulación móvil por CDP, no un iframe):
// /ordenar (mesa) y /carta-qr, a 390x844 (iPhone) y 412x915 (Android), con video y con foto.
// - La página no se ensancha (antes las fotos del producto quedaban a su ancho natural detrás
//   de la carta, el celular alejaba la página y cada plato medía ~1.875 px de alto).
// - Cada plato mide exactamente la pantalla.
// - Al deslizar pasa de a un plato (adelante, atrás y casi una pantalla), con snap obligatorio y
//   scroll-snap-stop: always.
// Usa el Chrome sin ventana de CI (CHROME_PATH) por el protocolo DevTools; si no hay, se salta.
const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');

const WEB = path.join(__dirname, '..', 'app', 'web');
const MEDIA = path.join(__dirname, 'fixtures', 'menu_video');
const CHROME = [process.env.CHROME_PATH, 'C:/Program Files/Google/Chrome/Application/chrome.exe', '/usr/bin/google-chrome', '/usr/bin/chromium']
  .find((p) => p && fs.existsSync(p));
const CID = '57c00000-0000-4000-8000-0000000b4a5a';
const TYPES = { '.js': 'application/javascript', '.html': 'text/html', '.webp': 'image/webp', '.mp4': 'video/mp4', '.css': 'text/css' };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function media(name) {
  const real = path.join(MEDIA, name);
  if (fs.existsSync(real)) return real;
  if (name.endsWith('.mp4')) return path.join(MEDIA, 'd1.mp4');
  if (name.endsWith('-poster.webp')) return path.join(MEDIA, 'd1-poster.webp');
  return path.join(MEDIA, 'd3.webp'); // 540 px de ancho: más ancha que el celular, como las fotos reales
}

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type, status = 200) => { res.writeHead(status, { 'content-type': type }); res.end(body); };
    const inject = (file) => fs.readFileSync(path.join(WEB, file), 'utf8').replace('<script', '<script src="/__fx.js"></script>\n  <script');
    if (url.pathname === '/carta-qr') return send(inject('carta_qr.html'), 'text/html');
    if (url.pathname === '/ordenar') return send(inject('hospitality_order.html'), 'text/html');
    if (url.pathname === '/__fx.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'carta_app_preview.js')), TYPES['.js']);
    if (url.pathname.startsWith('/__mv/')) { const f = media(path.basename(url.pathname)); return send(fs.readFileSync(f), TYPES[path.extname(f)]); }
    const file = url.pathname.startsWith('/client-static/') ? path.join(WEB, url.pathname.slice(15)) : null;
    if (file && file.startsWith(WEB) && fs.existsSync(file)) return send(fs.readFileSync(file), TYPES[path.extname(file)] || 'application/octet-stream');
    res.writeHead(404); res.end();
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

// ---------------------------------------------------------------- CDP mínimo (WebSocket de Node 24)
async function launch() {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-carta-movil-'));
  const proc = spawn(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--autoplay-policy=no-user-gesture-required',
    '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
  const wsUrl = await new Promise((resolve, reject) => {
    let buf = '';
    const t = setTimeout(() => reject(new Error('Chrome no abrió DevTools')), 30000);
    proc.stderr.on('data', (d) => { buf += d; const m = buf.match(/DevTools listening on (ws:\/\/\S+)/); if (m) { clearTimeout(t); resolve(m[1]); } });
  });
  const port = new URL(wsUrl).port;
  const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const pageWs = list.find((t) => t.type === 'page').webSocketDebuggerUrl;
  const ws = new WebSocket(pageWs);
  await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
  let id = 0;
  const pending = new Map();
  ws.onmessage = (ev) => { const msg = JSON.parse(ev.data); if (msg.id && pending.has(msg.id)) { const { resolve, reject } = pending.get(msg.id); pending.delete(msg.id); msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result); } };
  const send = (method, params = {}) => new Promise((resolve, reject) => { id += 1; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
  const close = () => { try { ws.close(); } catch (_) {} proc.kill(); };
  return { send, close };
}

async function evaluate(cdp, expr) {
  const r = await cdp.send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
  return r.result.value;
}

// Deslizar: desplazamiento suave del carrusel con el recorrido del dedo (de y0 a y1). Respeta el
// snap obligatorio igual que un dedo y termina en el plato siguiente o anterior. (El toque por
// CDP en chrome-headless-shell mueve el carrusel pero no termina el gesto; con Chromium completo
// el dedo real se verifico aparte: 0 -> 844 -> 1688.)
async function drag(cdp, x, y0, y1) {
  await evaluate(cdp, `document.querySelector('.cxa-vscroll').scrollBy({ top: ${y0 - y1}, behavior: 'smooth' })`);
  await sleep(1500);
}

const MEASURE = `(() => { const v = document.querySelector('.cxa-vscroll'); const c = document.querySelector('.cxa');
  if (!v || !c) return null;
  return { innerW: innerWidth, innerH: innerHeight, docW: document.documentElement.scrollWidth, cxa: Math.round(c.getBoundingClientRect().height),
    box: v.clientHeight, slides: [...v.children].slice(0, 4).map((s) => Math.round(s.getBoundingClientRect().height)),
    first: v.children[0] && v.children[0].querySelector('video') ? 'video' : 'foto', top: v.scrollTop,
    snap: getComputedStyle(v).scrollSnapType, stop: getComputedStyle(v.children[0]).scrollSnapStop }; })()`;

const SIZES = [[390, 844, 'iPhone'], [412, 915, 'Android']];
const PAGES = [['ordenar', `/ordenar?company_id=${CID}&mesa=Mesa%204&brand=brasa&view=video`], ['carta-qr', `/carta-qr?t=token-de-prueba-123456789&company_id=${CID}&brand=brasa&view=video`]];

test('carta en video en celular: cada plato = la pantalla y se desliza de a uno (/ordenar y /carta-qr, iPhone y Android, video y foto)',
  { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 300000 }, async () => {
    const server = await serve();
    const base = `http://127.0.0.1:${server.address().port}`;
    const cdp = await launch();
    try {
      await cdp.send('Page.enable');
      await cdp.send('Runtime.enable');
      for (const [w, hgt, label] of SIZES) {
        await cdp.send('Emulation.setDeviceMetricsOverride', { width: w, height: hgt, deviceScaleFactor: 2, mobile: true });
        await cdp.send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 });
        for (const [name, url] of PAGES) {
          for (const video of [true, false]) {
            const tag = `${label} ${w}x${hgt} ${name} ${video ? 'video' : 'foto'}`;
            await cdp.send('Page.navigate', { url: base + url + (video ? '' : '&video=0') });
            let m = null;
            for (let i = 0; i < 60 && !(m && m.slides.length >= 3); i += 1) { await sleep(250); m = await evaluate(cdp, MEASURE); }
            assert.ok(m, `${tag}: la carta en video no se abrió`);
            assert.equal(m.first, video ? 'video' : 'foto', `${tag}: medio del primer plato`);
            assert.equal(m.innerW, w, `${tag}: el celular alejó la página (ancho visible ${m.innerW})`);
            assert.ok(m.docW <= w, `${tag}: la página se sale de ancho (${m.docW} px)`);
            assert.equal(m.innerH, hgt, `${tag}: alto visible ${m.innerH}`);
            assert.equal(m.cxa, hgt, `${tag}: la carta mide ${m.cxa} px de alto`);
            assert.equal(m.box, hgt, `${tag}: el carrusel mide ${m.box} px`);
            m.slides.forEach((s, i) => assert.equal(s, hgt, `${tag}: el plato ${i + 1} mide ${s} px y no la pantalla`));
            assert.match(m.snap, /y mandatory/);
            assert.equal(m.stop, 'always');
            const x = Math.round(w / 2);
            await drag(cdp, x, Math.round(hgt * 0.7), Math.round(hgt * 0.3));
            assert.equal((await evaluate(cdp, MEASURE)).top, hgt, `${tag}: el primer deslizamiento no quedó en el plato 2`);
            await drag(cdp, x, Math.round(hgt * 0.7), Math.round(hgt * 0.3));
            assert.equal((await evaluate(cdp, MEASURE)).top, 2 * hgt, `${tag}: el segundo deslizamiento no quedó en el plato 3`);
            await drag(cdp, x, Math.round(hgt * 0.95), Math.round(hgt * 0.02)); // casi una pantalla: igual de a uno
            assert.equal((await evaluate(cdp, MEASURE)).top, 3 * hgt, `${tag}: un deslizamiento largo saltó platos`);
            await drag(cdp, x, Math.round(hgt * 0.3), Math.round(hgt * 0.7));
            assert.equal((await evaluate(cdp, MEASURE)).top, 2 * hgt, `${tag}: hacia atrás también de a uno`);
          }
        }
      }
    } finally {
      cdp.close();
      server.close();
    }
  });
