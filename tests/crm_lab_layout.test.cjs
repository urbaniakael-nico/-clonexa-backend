// CRM VELVET-LAB en Chrome headless con la pagina real (crm_lab.html + crm_lab.js):
// lista con en vivo, PIN, sin PIN, panel de la persona, referencias, Cerrar prendas
// y el aviso de pendiente, en tableta horizontal (1280 x 800) y celular (375 px):
// sin desborde, AA, nada "por persona" y vuelta a la lista a los 20 s.
// Si no hay Chrome, se salta. CX_CRM_SHOTS=<carpeta> guarda capturas PNG.
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
const CID = 'd63cf68c-be5b-4a30-aee4-341973018db1';
const LOGIN_CID = '00000000-0000-4000-8000-000000000001';  // otra clave en localStorage: los iframes comparten origen
const TYPES = { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json' };
const VIEWS = ['list', 'pin', 'nopin', 'person', 'refs', 'close', 'over'];
const CASES = [...VIEWS.flatMap((v) => [[`${v}-1280`, 1280, v], [`${v}-375`, 375, v]]), ['login-375', 375, 'login'], ['idle-1280', 1280, 'idle']];

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/mini-panel/crm-lab') {
      const html = fs.readFileSync(path.join(WEB, 'crm_lab.html'), 'utf8').replace('<script src="/client-static/crm_lab.js', '<script src="/__preview.js"></script>\n  <script src="/client-static/crm_lab.js');
      return send(html, 'text/html');
    }
    if (url.pathname === '/__preview.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'crm_lab_preview.js')), TYPES['.js']);
    if (url.pathname === '/__frames.html') {
      const frames = CASES.map(([k, w, v]) => `<iframe data-k="${k}" style="width:${w}px;height:800px;border:0;display:block" src="/mini-panel/crm-lab?company_id=${v === 'login' ? LOGIN_CID : CID}&view=${v}"></iframe>`);
      return send(`<!doctype html><html><body style="margin:0">${frames.join('')}<pre id="all"></pre><script>
        setTimeout(() => { const out = {}; document.querySelectorAll('iframe').forEach((f) => { const d = f.contentDocument && f.contentDocument.getElementById('layout'); out[f.dataset.k] = d ? JSON.parse(d.textContent) : null; });
          document.getElementById('all').textContent = JSON.stringify(out); }, 12000);</script></body></html>`, 'text/html');
    }
    if (url.pathname === '/__one.html') {
      const w = Number(url.searchParams.get('w')) || 1280;
      const h = Number(url.searchParams.get('h')) || 800;
      return send(`<!doctype html><html><body style="margin:0"><iframe style="width:${w}px;height:${h}px;border:0;display:block" src="/mini-panel/crm-lab?company_id=${url.searchParams.get('v') === 'login' ? LOGIN_CID : CID}&view=${url.searchParams.get('v')}"></iframe></body></html>`, 'text/html');
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

test('CRM VELVET-LAB: tableta (1280) y celular (375) sin desborde y con AA; PIN, persona, tallas y 20 s',
  { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 400000 }, async () => {
    const server = await serve();
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-crm-layout-'));
    const base = `http://127.0.0.1:${server.address().port}`;
    try {
      const html = await chrome([`--user-data-dir=${profile}`, '--window-size=1400,1400', '--virtual-time-budget=20000', '--dump-dom', `${base}/__frames.html`]);
      const m = html.match(/<pre id="all">([^<]*)<\/pre>/);
      assert.ok(m && m[1], 'sin resultado de la medición');
      const r = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
      for (const [k] of CASES) {
        const x = r[k];
        assert.ok(x && x.mounted, `${k}: no se montó ${JSON.stringify(x)}`);
        assert.equal(x.page_overflow, false, `${k}: la página se sale de ancho`);
        assert.deepEqual(x.bad, [], `${k}: textos que desbordan: ${JSON.stringify(x.bad)}`);
        assert.deepEqual(x.low_contrast, [], `${k}: contraste bajo: ${JSON.stringify(x.low_contrast)}`);
        assert.equal(x.per_person, false, `${k}: nada "por persona"`);
      }
      for (const k of ['list-1280', 'list-375']) {
        assert.equal(r[k].people, 5, 'todos los colaboradores activos');
        assert.equal(r[k].ribbon, 3, 'en vivo: trabajando y en pausa');
        assert.match(r[k].counts, /2 trabajando · 1 en pausa/);
        assert.match(r[k].hm, /^\d+ h \d{2} min$/, 'tiempo en formato X h YY min');
      }
      assert.equal(r['pin-375'].pin_keys, 12, 'teclado del PIN');
      assert.equal(r['nopin-1280'].ask_admin, true, 'sin PIN: Pide tu PIN al administrador');
      assert.deepEqual(r['person-1280'].actions, ['Pausa', 'Fin de turno', 'Cambiar referencia', 'Cerrar prendas']);
      assert.equal(r['refs-375'].refs, 5, 'buscar referencia activa');
      assert.deepEqual(r['close-1280'].sizes, ['SPendiente 12', 'MPendiente 6', 'LPendiente 0']);
      assert.equal(r['over-375'].over, true, 'supera el pendiente: pide confirmación');
      assert.ok(r['over-375'].calls.some((c) => c.startsWith('POST /crm-lab/') && c.endsWith('/action')));
      assert.equal(r['login-375'].login, true, 'ingreso del panel con usuario y clave');
      assert.equal(r['idle-1280'].before_idle, true);
      assert.equal(r['idle-1280'].back_to_list, true, 'a los 20 s sin uso vuelve a la lista');
      assert.equal(r['idle-1280'].employee_token_cleared, true, 'y olvida el token del colaborador');
      const shots = process.env.CX_CRM_SHOTS;
      if (shots) {
        fs.mkdirSync(shots, { recursive: true });
        for (const [k, w, v] of CASES) {
          await chrome([`--user-data-dir=${profile}-${k}`, `--window-size=${w},800`, '--hide-scrollbars', '--virtual-time-budget=8000',
            `--screenshot=${path.join(shots, `crm-${k}.png`)}`, `${base}/__one.html?w=${w}&h=800&v=${v}`]);
        }
      }
    } finally {
      server.close();
      try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
    }
  });
