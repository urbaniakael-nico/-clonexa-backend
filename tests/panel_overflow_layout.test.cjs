// Desbordes en 5 paneles del portal con datos de ejemplo (tests/fixtures/panel_overflow_preview.js):
// barra en modo kanban (Pendiente/Alistando/Entregado/Cerrado), Materiales, Ventas,
// Cotizaciones/Tickets y Tesorería, a 390 (celular), 768, 1440 y 1600 px.
// Ningún botón ni campo sale de su tarjeta ni del área principal, ningún rótulo queda encima de
// otro y la página no se ensancha. Antes: el portal crecía al ancho de sus tablas (grilla 1fr),
// la fila "Agregar a esta mesa" montaba los rótulos y el cierre de mesa salía hasta 137 px.
// Usa el Chrome sin ventana de CI (CHROME_PATH) por el protocolo DevTools; si no hay, se salta.
const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');

const WEB = path.join(__dirname, '..', 'app', 'web');
const CHROME = [process.env.CHROME_PATH, 'C:/Program Files/Google/Chrome/Application/chrome.exe', '/usr/bin/google-chrome', '/usr/bin/chromium']
  .find((p) => p && fs.existsSync(p));
const CID = '0f0f0f0f-1111-4222-8333-444444444444';
const TYPES = { '.js': 'application/javascript', '.html': 'text/html', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.webp': 'image/webp', '.ico': 'image/x-icon' };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type, status = 200) => { res.writeHead(status, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/client.html') {
      return send(fs.readFileSync(path.join(WEB, 'client.html'), 'utf8').replace('<link rel="stylesheet"', '<script src="/__preview.js"></script>\n  <link rel="stylesheet"'), 'text/html');
    }
    if (url.pathname === '/__preview.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'panel_overflow_preview.js')), TYPES['.js']);
    let file = null;
    if (url.pathname.startsWith('/client-static/')) file = path.join(WEB, url.pathname.slice('/client-static/'.length));
    else if (url.pathname.startsWith('/assets/')) file = path.join(WEB, 'assets', url.pathname.slice('/assets/'.length));
    if (file && file.startsWith(WEB) && fs.existsSync(file) && fs.statSync(file).isFile()) return send(fs.readFileSync(file), TYPES[path.extname(file)] || 'application/octet-stream');
    send('', 'text/plain', 404);
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

async function launch() {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-paneles-'));
  const proc = spawn(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'],
    { stdio: ['ignore', 'ignore', 'pipe'] });
  const wsUrl = await new Promise((resolve, reject) => {
    let buf = '';
    const t = setTimeout(() => reject(new Error('Chrome no abrió DevTools')), 30000);
    proc.stderr.on('data', (d) => { buf += d; const m = buf.match(/DevTools listening on (ws:\/\/\S+)/); if (m) { clearTimeout(t); resolve(m[1]); } });
  });
  const list = await (await fetch(`http://127.0.0.1:${new URL(wsUrl).port}/json/list`)).json();
  const ws = new WebSocket(list.find((t) => t.type === 'page').webSocketDebuggerUrl);
  await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
  let id = 0;
  const pending = new Map();
  ws.onmessage = (ev) => { const msg = JSON.parse(ev.data); if (msg.id && pending.has(msg.id)) { const { resolve, reject } = pending.get(msg.id); pending.delete(msg.id); msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result); } };
  const send = (method, params = {}) => new Promise((resolve, reject) => { id += 1; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
  return { send, close: () => { try { ws.close(); } catch (_) {} proc.kill(); } };
}

const evaluate = async (cdp, expr) => (await cdp.send('Runtime.evaluate', { expression: expr, returnByValue: true })).result.value;

const PANELS = [['orders', 'barra (kanban)'], ['materials', 'Materiales'], ['sales', 'Ventas'], ['tqt', 'Cotizaciones/Tickets'], ['tp', 'Tesorería']];
const WIDTHS = [390, 768, 1440, 1600];

test('paneles del portal: nada sale de su tarjeta ni hay rótulos encimados (barra kanban, materiales, ventas, cotizaciones/tickets, tesorería; 390/768/1440/1600)',
  { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 600000 }, async () => {
    const server = await serve();
    const base = `http://127.0.0.1:${server.address().port}`;
    const cdp = await launch();
    const problems = [];
    try {
      await cdp.send('Page.enable');
      await cdp.send('Runtime.enable');
      for (const w of WIDTHS) {
        await cdp.send('Emulation.setDeviceMetricsOverride', { width: w, height: 1000, deviceScaleFactor: 1, mobile: w < 500 });
        for (const [panel, label] of PANELS) {
          await cdp.send('Page.navigate', { url: `${base}/client.html?company_id=${CID}&panel=${panel}` });
          let r = null;
          for (let i = 0; i < 150 && !r; i += 1) {
            await sleep(200);
            const raw = await evaluate(cdp, "(document.getElementById('layout') || {}).textContent || ''");
            if (raw) r = JSON.parse(raw);
          }
          assert.ok(r && r.mounted, `${label} ${w}px: el panel no se abrió ${r && r.error ? r.error : ''}`);
          if (panel === 'orders') assert.ok(await evaluate(cdp, "document.querySelectorAll('[data-hsp-close-received]').length > 0"), 'la barra debe tener mesas con cierre');
          if (r.page_overflow > 1) problems.push(`${label} ${w}px: la página se ensancha ${r.page_overflow}px`);
          for (const o of r.out) problems.push(`${label} ${w}px: ${o.el} sale ${o.px}px de ${o.card}`);
          for (const o of r.overlap) problems.push(`${label} ${w}px: rótulos encimados ${o}`);
        }
      }
    } finally {
      cdp.close();
      server.close();
    }
    assert.deepEqual(problems, [], problems.slice(0, 20).join('\n'));
  });
