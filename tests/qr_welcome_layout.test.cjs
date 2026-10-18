// QR de la mesa (hospitality_order.html real) en Chrome sin ventana:
// - Parte 2: en la lista de pronósticos de la polla el círculo de la mesa nunca tapa
//   el nombre (los largos se cortan con "…") y "Polla activa" pasa AA, en tema
//   oscuro y claro, a 375 px.
// - Parte 3: pantalla de bienvenida con nombre (qr_welcome_name) a 375 px y el chip
//   "Laura · Mesa 4"; sin el interruptor no aparece nada nuevo.
// Si no hay Chrome, se salta. CX_QR_SHOTS=<carpeta> guarda capturas PNG.
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
  ['polla-oscuro-375', '&qr=open&long=1'], ['polla-claro-375', '&qr=open&long=1&theme=light'],
  ['bienvenida-375', '&qr=open&welcome=1'], ['con-nombre-375', '&qr=open&named=Laura'], ['sin-interruptor-375', '&qr=open'],
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
      const frames = CASES.map(([k, q], i) => `<iframe data-k="${k}" style="width:375px;height:1400px;border:0;display:block" src="/ordenar?company_id=${CID.slice(0, -1)}${i}&mesa=Mesa%204&scroll=0${q}"></iframe>`);
      return send(`<!doctype html><html><body style="margin:0">${frames.join('')}<pre id="all"></pre><script>
        setTimeout(() => { const out = {}; document.querySelectorAll('iframe').forEach((f) => { const d = f.contentDocument && f.contentDocument.getElementById('layout'); out[f.dataset.k] = d ? JSON.parse(d.textContent) : null; });
          document.getElementById('all').textContent = JSON.stringify(out); }, 20000);</script></body></html>`, 'text/html');
    }
    if (url.pathname === '/__one.html') {
      return send(`<!doctype html><html><body style="margin:0;background:#fff"><iframe style="width:375px;height:900px;border:0;display:block" src="/ordenar?company_id=${CID}&mesa=Mesa%204${url.searchParams.get('q') || ''}"></iframe></body></html>`, 'text/html');
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

test('QR: lista de la polla sin encimarse y "Polla activa" AA (claro y oscuro); bienvenida con nombre a 375 px',
  { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 400000 }, async () => {
    const server = await serve();
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-qrw-layout-'));
    const base = `http://127.0.0.1:${server.address().port}`;
    try {
      const html = await chrome([`--user-data-dir=${profile}`, '--window-size=500,1400', '--virtual-time-budget=30000', '--dump-dom', `${base}/__frames.html`]);
      const m = html.match(/<pre id="all">([^<]*)<\/pre>/);
      assert.ok(m && m[1], 'sin resultado de la medición');
      const r = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
      for (const k of ['polla-oscuro-375', 'polla-claro-375']) {
        const x = r[k];
        assert.ok(x && x.mounted, `${k}: no se montó`);
        assert.equal(x.page_overflow, false, `${k}: la página se sale de ancho`);
        assert.equal(x.overlaps, 0, `${k}: el círculo de la mesa tapa el nombre`);
        assert.deepEqual(x.bad, [], `${k}: desbordes ${JSON.stringify(x.bad)}`);
        assert.equal(x.eyebrow.text, 'Polla activa');
        assert.ok(x.eyebrow.ratio >= 4.5, `${k}: "Polla activa" con contraste ${x.eyebrow.ratio}`);
        assert.match(x.text, /Mesa 12|Terraza VIP 3/);
      }
      const w = r['bienvenida-375'];
      assert.equal(w.welcome, true, 'la bienvenida aparece apenas se activa la mesa');
      assert.match(w.welcome_text, /¡Bienvenido a The Time Machine! 🎶 Qué bueno tenerte esta noche\. ¿Cómo te llamas\?[\s\S]*Continuar[\s\S]*Ahora no/);
      assert.deepEqual(w.welcome_low, [], 'bienvenida con contraste AA');
      assert.equal(w.page_overflow, false);
      assert.equal(r['con-nombre-375'].welcome, false, 'con nombre ya no se vuelve a pedir');
      assert.match(r['con-nombre-375'].chip, /Laura · Mesa 4/);
      assert.doesNotMatch(r['con-nombre-375'].chip, /Cambiar nombre|Agregar mi nombre/, 'nombre fijo');
      assert.equal(r['sin-interruptor-375'].welcome, false);
      assert.equal(r['sin-interruptor-375'].chip, '', 'sin el interruptor, el QR de siempre');

      const shots = process.env.CX_QR_SHOTS;
      if (shots) {
        fs.mkdirSync(shots, { recursive: true });
        for (const [k, q] of CASES) {
          await chrome([`--user-data-dir=${profile}`, '--window-size=375,900', '--hide-scrollbars', '--virtual-time-budget=8000', `--screenshot=${path.join(shots, `${k}.png`)}`,
            `${base}/__one.html?q=${encodeURIComponent(`${q}${k.startsWith('polla') ? '' : '&scroll=0'}`)}`]);
        }
      }
    } finally {
      server.close();
      try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
    }
  });
