// Oficina 3D · gestos en Chrome de verdad (CDP, emulación táctil). Antes: deslizar con el dedo o con dos dedos en el
// touchpad hacía "atrás" en Chrome y sacaba de la oficina. Ahora: deslizar horizontal GIRA y la página sigue en la
// oficina; pellizco acerca; rueda horizontal gira; html/body sin overscroll y el lienzo con touch-action: none.
// Cámara: límites por piso (nunca detrás de una pared ni bajo el piso) y paredes entre la cámara y el centro ocultas.
// No guarda capturas. Sin Chrome, la parte del navegador se salta.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { pathToFileURL } = require('node:url');

const ROOT = path.resolve(__dirname, '..');
const OF = path.join(ROOT, 'app', 'web', 'oficina');
const CHROME = [process.env.CHROME_PATH, 'C:/Program Files/Google/Chrome/Application/chrome.exe', '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser']
  .find((p) => p && fs.existsSync(p));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const loadRules = () => import(pathToFileURL(path.join(OF, 'oficina_pisos_rules.js')).href);

const PAGE = `<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/app.css"></head><body><canvas id="c"></canvas><pre id="out"></pre>
<script type="module">
import {attachGestures} from '/gestos.js';
const g = window.__g = {rotate: 0, rotY: 0, zoom: 1, pan: 0, taps: 0};
attachGestures(document.getElementById('c'), {rotate: (dx, dy) => { g.rotate += dx; g.rotY += dy; }, zoom: f => { g.zoom *= f; }, pan: (dx, dy) => { g.pan += Math.abs(dx) + Math.abs(dy); }, tap: () => { g.taps++; }});
window.__ready = true;
</script></body></html>`;

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/inicio.html') return send('<!doctype html><title>inicio</title><p>página anterior</p>', 'text/html');
    if (url.pathname === '/oficina.html') return send(PAGE, 'text/html');
    if (url.pathname === '/gestos.js') return send(fs.readFileSync(path.join(OF, 'oficina_gestos.js')), 'application/javascript');
    if (url.pathname === '/app.css') return send(fs.readFileSync(path.join(OF, 'oficina.css')), 'text/css');
    res.writeHead(404); res.end();
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

async function launch() {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-oficina-gestos-'));
  const proc = spawn(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'],
    { stdio: ['ignore', 'ignore', 'pipe'] });
  const wsUrl = await new Promise((resolve, reject) => {
    let buf = ''; const t = setTimeout(() => reject(new Error('Chrome no abrió DevTools')), 30000);
    proc.stderr.on('data', (d) => { buf += d; const m = buf.match(/DevTools listening on (ws:\/\/\S+)/); if (m) { clearTimeout(t); resolve(m[1]); } });
  });
  const list = await (await fetch(`http://127.0.0.1:${new URL(wsUrl).port}/json/list`)).json();
  const ws = new WebSocket(list.find((t) => t.type === 'page').webSocketDebuggerUrl);
  await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
  let id = 0; const pending = new Map();
  ws.onmessage = (ev) => { const msg = JSON.parse(ev.data); if (msg.id && pending.has(msg.id)) { const { resolve, reject } = pending.get(msg.id); pending.delete(msg.id); msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result); } };
  const send = (method, params = {}) => new Promise((resolve, reject) => { id += 1; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
  return { send, close: () => { try { ws.close(); } catch (_) {} proc.kill(); try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {} } };
}
const evaluate = async (cdp, expr) => (await cdp.send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })).result.value;

async function swipe(cdp, from, to, steps = 8) {
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: from[0], y: from[1], id: 1 }] });
  for (let i = 1; i <= steps; i++) {
    const x = from[0] + (to[0] - from[0]) * i / steps, y = from[1] + (to[1] - from[1]) * i / steps;
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x, y, id: 1 }] }); await sleep(16);
  }
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
}

test('en Chrome táctil: deslizar horizontal gira y NO navega atrás; pellizco acerca; rueda horizontal gira',
  { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 120000 }, async () => {
    const server = await serve(); const base = `http://127.0.0.1:${server.address().port}`;
    const cdp = await launch();
    try {
      await cdp.send('Page.enable'); await cdp.send('Runtime.enable');
      await cdp.send('Emulation.setDeviceMetricsOverride', { width: 412, height: 860, deviceScaleFactor: 2, mobile: true });
      await cdp.send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 });
      await cdp.send('Page.navigate', { url: base + '/inicio.html' }); await sleep(600);
      await cdp.send('Page.navigate', { url: base + '/oficina.html' });
      for (let i = 0; i < 40 && !(await evaluate(cdp, 'window.__ready === true')); i++) await sleep(150);
      assert.equal(await evaluate(cdp, 'history.length >= 2'), true, 'hay una página anterior a la que podría volver');
      const css = await evaluate(cdp, `({html: getComputedStyle(document.documentElement).overscrollBehaviorX, body: getComputedStyle(document.body).overscrollBehaviorX,
        bodyY: getComputedStyle(document.body).overscrollBehaviorY, canvas: getComputedStyle(document.getElementById('c')).touchAction})`);
      assert.deepEqual(css, { html: 'none', body: 'none', bodyY: 'none', canvas: 'none' });

      // deslizar a la derecha desde el borde izquierdo (el gesto de "atrás") y a la izquierda: gira, no navega
      await swipe(cdp, [8, 430], [380, 430]);
      await swipe(cdp, [380, 430], [20, 430]);
      await sleep(500);
      const after = await evaluate(cdp, '({path: location.pathname, g: window.__g})');
      assert.equal(after.path, '/oficina.html', 'el gesto no sacó de la oficina');
      assert.ok(after.g.rotate !== 0, `deslizar gira (${after.g.rotate})`);
      assert.equal(after.g.taps, 0, 'un deslizamiento no es un toque');

      // pellizco: dos dedos que se separan -> acercar (factor < 1 = menos distancia)
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: 180, y: 430, id: 1 }, { x: 230, y: 430, id: 2 }] });
      for (let i = 1; i <= 6; i++) { await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: 180 - i * 20, y: 430, id: 1 }, { x: 230 + i * 20, y: 430, id: 2 }] }); await sleep(16); }
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] }); await sleep(200);
      const z = await evaluate(cdp, 'window.__g.zoom');
      assert.ok(z < 0.6, `pellizco acerca (factor ${z})`);

      // rueda horizontal (dos dedos de lado en el touchpad): gira y no navega
      const r0 = await evaluate(cdp, 'window.__g.rotate');
      await cdp.send('Emulation.setTouchEmulationEnabled', { enabled: false });
      await cdp.send('Input.dispatchMouseEvent', { type: 'mouseWheel', x: 200, y: 430, deltaX: -400, deltaY: 0 }); await sleep(400);
      const w = await evaluate(cdp, '({path: location.pathname, r: window.__g.rotate})');
      assert.equal(w.path, '/oficina.html');
      assert.ok(w.r !== r0, 'la rueda horizontal gira');
      // Ctrl + rueda (pellizco del touchpad) acerca sin hacer zoom de la página
      const z0 = await evaluate(cdp, 'window.__g.zoom');
      await cdp.send('Input.dispatchMouseEvent', { type: 'mouseWheel', x: 200, y: 430, deltaX: 0, deltaY: -50, modifiers: 2 }); await sleep(200);
      assert.ok((await evaluate(cdp, 'window.__g.zoom')) < z0, 'Ctrl + rueda acerca la cámara');
      assert.equal(await evaluate(cdp, 'visualViewport.scale'), 1, 'la página no se amplió');
    } finally { cdp.close(); server.close(); }
  });

test('cámara por piso: nunca bajo el piso ni más lejos/cerca del límite; paredes entre la cámara y el centro se ocultan', async () => {
  const P = await loadRules();
  for (const [name, F] of [['Clonexa', P.CLONEXA], ['Velvet', P.TALLER], ['Asadero', P.RESTAURANTE], ['VOLTAGE', P.CAMPO]]) {
    const L = P.camLimits(F.ROOM, F.CAMERA);
    const T = F.CAMERA.look, d = F.CAMERA.pos.map((v, i) => v - T[i]); const len = Math.hypot(...d);
    const home = { dist: len, pol: Math.acos(d[1] / len), az: Math.atan2(d[0], d[2]), tx: T[0], tz: T[2] };
    assert.deepEqual(P.clampCam({ ...home }, L), home, `${name}: la cámara aprobada queda tal cual`);
    // gestos extremos: girar por debajo, alejar al infinito, acercar a cero, centro fuera del salón
    for (const g of [{ ...home, pol: 3 }, { ...home, pol: -2 }, { ...home, dist: 999 }, { ...home, dist: 0.1, pol: 1.5 }, { ...home, tx: 99, tz: -99, az: 9 }]) {
      const c = P.clampCam(g, L); const pos = P.camPos(c, L.lookY);
      assert.ok(pos[1] >= L.minY - 1e-9, `${name}: cámara bajo el piso (${pos[1].toFixed(2)})`);
      assert.ok(c.dist >= L.distMin && c.dist <= L.distMax, `${name}: distancia ${c.dist}`);
      assert.ok(Math.abs(c.az) <= 1.1 + 1e-9 && Math.abs(c.tx) <= F.ROOM.W / 2 && Math.abs(c.tz) <= F.ROOM.D / 2, `${name}: giro/centro`);
    }
    // girado al máximo a la izquierda y lejos: la cámara queda fuera de la pared izquierda -> se oculta
    const side = P.clampCam({ ...home, az: -1.1, dist: L.distMax }, L);
    assert.equal(P.wallsToHide(P.camPos(side, L.lookY), F.ROOM).left, true, `${name}: pared izquierda entre la cámara y el centro`);
    assert.deepEqual(P.wallsToHide(P.camPos(home, L.lookY), F.ROOM), { back: false, front: true, left: false, right: false }, `${name}: vista inicial`);
  }
  const R = P.TALLER.ROOM;
  assert.equal(P.wallSide({ min: [-9.2, 0, -6.2], max: [-9, 3.4, 6] }, R), 'left', 'pared izquierda');
  assert.equal(P.wallSide({ min: [-9, 0, -6.2], max: [9, 3.4, -6] }, R), 'back', 'pared del fondo');
  assert.equal(P.wallSide({ min: [-2, 1.8, -5.99], max: [2, 2.9, -5.97] }, R), 'back', 'el logo/pantalla pegado al fondo va con su pared');
  assert.equal(P.wallSide({ min: [-1, 0, -1], max: [1, 1, 1] }, R), null, 'una mesa no es pared');
  assert.equal(P.wallSide({ min: [-9, -0.3, -6], max: [9, 0, 6] }, R), null, 'el piso no es pared');
});

test('los motores usan los gestos y los límites (pisos aprobados, bar y edificio)', () => {
  const src = (f) => fs.readFileSync(path.join(OF, f), 'utf8');
  for (const f of ['oficina_mixamo.js', 'oficina_bar.js', 'oficina_app.js']) {
    assert.match(src(f), /attachGestures\(/, `${f}: gestos`);
    assert.doesNotMatch(src(f), /addEventListener\('pointerdown'/, `${f}: sin manejadores sueltos que dejen pasar el "atrás"`);
  }
  for (const f of ['oficina_mixamo.js', 'oficina_bar.js']) {
    assert.match(src(f), /camLimits\(/); assert.match(src(f), /cutaway\(\)/, `${f}: oculta paredes`);
  }
  const routes = fs.readFileSync(path.join(ROOT, 'app', 'web', 'oficina_routes.py'), 'utf8');
  assert.match(routes, /"gestos\.js": \("oficina\/oficina_gestos\.js"/);
});
