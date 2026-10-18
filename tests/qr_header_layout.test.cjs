// QR de la mesa: encabezado nuevo y nombre fijo (qr_welcome_name, carta de bar), en Chrome sin ventana.
// Basado en qr_welcome_layout.test.cjs (mismo simulador). Antes:
// - Parte 2: en la lista de pronósticos de la polla el círculo de la mesa nunca tapa
//   el nombre (los largos se cortan con "…") y "Polla activa" pasa AA, en tema
//   oscuro y claro, a 375 px.
// - Parte 3: pantalla de bienvenida con nombre (qr_welcome_name) a 375 px y el chip
//   "Laura · Mesa 4"; sin el interruptor no aparece nada nuevo.
// Si no hay Chrome, se salta. CX_QRH_SHOTS=<carpeta> guarda capturas PNG.
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
const TYPES = { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html' };
const CASES = [
  ['con-nombre-375', '&qr=open&bar=1&named=Nicolas', 375], ['con-nombre-320', '&qr=open&bar=1&named=Nicolas', 320],
  ['sin-nombre-375', '&qr=open&bar=1&welcome=1&skip=1', 375], ['mesa-abierta-375', '&qr=open&bar=1&named=Nicolas&hint=1', 375],
  ['detalle-375', '&qr=open&bar=1&named=Nicolas&detail=1', 375], ['sin-interruptor-375', '&qr=open&bar=1', 375],
];

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/ordenar') {
      return send(fs.readFileSync(path.join(WEB, 'hospitality_order.html'), 'utf8').replace('<script', '<script src="/__qr.js"></script>\n  <script'), 'text/html');
    }
    if (url.pathname === '/__qr.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'loyalty_retos_qr_preview.js')), TYPES['.js']);
    if (url.pathname === '/__frames.html') {
      // Una empresa por caso: los marcos comparten localStorage (mismo origen).
      const frames = CASES.map(([k, q, w], i) => `<iframe data-k="${k}" style="width:${w}px;height:1400px;border:0;display:block" src="/ordenar?company_id=${CID.slice(0, -1)}${i}&mesa=Mesa%204&scroll=0${q}"></iframe>`);
      return send(`<!doctype html><html><body style="margin:0">${frames.join('')}<pre id="all"></pre><script>
        setTimeout(() => { const out = {}; document.querySelectorAll('iframe').forEach((f) => { const d = f.contentDocument && f.contentDocument.getElementById('layout'); out[f.dataset.k] = d ? JSON.parse(d.textContent) : null; });
          document.getElementById('all').textContent = JSON.stringify(out); }, 20000);</script></body></html>`, 'text/html');
    }
    if (url.pathname === '/__one.html') {
      return send(`<!doctype html><html><body style="margin:0;background:#fff"><iframe style="width:${Number(url.searchParams.get('w')) || 375}px;height:900px;border:0;display:block" src="/ordenar?company_id=${CID}${Date.now() % 9}&mesa=Mesa%204${url.searchParams.get('q') || ''}"></iframe></body></html>`, 'text/html');
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

test('QR: encabezado nuevo (logo, Mesa, nombre, Mesa abierta), cuenta y música lado a lado, nombre fijo; apagado = el de siempre',
  { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 400000 }, async () => {
    const server = await serve();
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-qrh-layout-'));
    const base = `http://127.0.0.1:${server.address().port}`;
    try {
      const html = await chrome([`--user-data-dir=${profile}`, '--window-size=500,1400', '--virtual-time-budget=30000', '--dump-dom', `${base}/__frames.html`]);
      const m = html.match(/<pre id="all">([^<]*)<\/pre>/);
      assert.ok(m && m[1], 'sin resultado de la medición');
      const r = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
      for (const [k] of CASES.filter(([k]) => k !== 'sin-interruptor-375')) {
        const x = r[k];
        assert.ok(x && x.mounted, `${k}: no se montó`);
        assert.equal(x.page_overflow, false, `${k}: la página se sale de ancho`);
        assert.deepEqual(x.head_bad, [], `${k}: el encabezado desborda ${JSON.stringify(x.head_bad)}`);
        assert.deepEqual(x.head_low, [], `${k}: contraste bajo ${JSON.stringify(x.head_low)}`);
        assert.equal(x.old_head, false, `${k}: el encabezado de antes no se ve`);
        assert.equal(x.change_name, false, `${k}: no se ve "Cambiar nombre"`);
        assert.equal(x.green_box, false, `${k}: no hay caja verde`);
        assert.match(x.cards_text[0], /🧾 Cuenta de la mesa[\s\S]*\$\s?86\.000[\s\S]*3 pedidos[\s\S]*Ver detalle ▾/);
        assert.match(x.cards_text[1], /🎵 Música[\s\S]*¿Qué deseas escuchar\?[\s\S]*Pedir canción ▾/);
      }
      assert.match(r['con-nombre-375'].head, /Mesa 4\s*👤 Nicolas\s*● Mesa abierta/);
      assert.equal(r['con-nombre-375'].side_by_side, true, '375 px: cuenta y música lado a lado');
      assert.equal(r['con-nombre-320'].side_by_side, false, '320 px: una debajo de la otra');
      assert.match(r['sin-nombre-375'].head, /Mesa 4\s*Agregar mi nombre\s*● Mesa abierta/);
      assert.match(r['mesa-abierta-375'].hint, /La mesa sigue abierta\. Puedes continuar ordenando; este acceso se cerrará cuando el bar cierre la mesa\./);
      assert.equal(r['con-nombre-375'].hint, '', 'el texto solo al tocar la etiqueta');
      assert.equal(r['detalle-375'].detail_open, true, 'Ver detalle abre el mismo detalle de cuentas');
      const off = r['sin-interruptor-375'];
      assert.ok(off && off.mounted);
      assert.equal(off.old_head, true, 'sin el interruptor, el encabezado de siempre');
      assert.equal(off.head, '');
      const shots = process.env.CX_QRH_SHOTS;
      if (shots) {
        fs.mkdirSync(shots, { recursive: true });
        for (const [k, q, w] of CASES) {
          await chrome([`--user-data-dir=${profile}`, `--window-size=${w},900`, '--hide-scrollbars', '--virtual-time-budget=8000', `--screenshot=${path.join(shots, `${k}.png`)}`,
            `${base}/__one.html?w=${w}&q=${encodeURIComponent(`${q}&scroll=0`)}`]);
        }
      }
    } finally {
      server.close();
      try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
    }
  });
