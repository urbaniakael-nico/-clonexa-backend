// CRM VELVET-LAB (056K) en Chrome headless con la página real (crm_lab.html + .css + .js)
// y datos de ejemplo, en celular horizontal (844 x 390 y 740 x 360), celular vertical
// (390 x 844) y tableta (1024 x 768 y 1280 x 800):
// - la página nunca hace scroll; la barra superior siempre visible; solo la cuadrícula
//   hace scroll por dentro; 4 columnas en horizontal y 2 en vertical;
// - tarjetas con su color por estado (TRABAJANDO aqua del tema, EN PAUSA ámbar, SIN
//   TURNO clara) en orden trabajando → en pausa → sin turno y alfabético, cronómetro h:mm:ss;
// - teclado del PIN completo (12 teclas de 48 px o más, el 0 visible), lista de
//   referencias y botón Iniciar visibles, panel con turno activo y Cerrar prendas;
// - colores del tema de Velvet; con otro tema el CRM cambia de color;
// - el botón de pantalla completa solo con soporte (sin la API, no aparece);
// - sin desborde, contraste AA, nada "por persona" y vuelta a la lista a los 20 s.
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
const SIZES = [[844, 390], [740, 360], [390, 844], [1024, 768], [1280, 800]];
const VIEWS = ['list', 'pin', 'nopin', 'startpin', 'start', 'startpick', 'person', 'refs', 'close', 'over'];
const AQUA = 'rgb(0, 255, 225)';

function frameSrc(v, theme = 'velvet', fsOk = true) {
  return `/mini-panel/crm-lab?company_id=${v === 'login' ? LOGIN_CID : CID}&view=${v}&theme=${theme}${fsOk ? '' : '&fs=0'}`;
}

function serve(cases) {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/mini-panel/crm-lab') {
      const html = fs.readFileSync(path.join(WEB, 'crm_lab.html'), 'utf8').replace('<script src="/client-static/crm_lab.js', '<script src="/__preview.js"></script>\n  <script src="/client-static/crm_lab.js');
      return send(html, 'text/html');
    }
    if (url.pathname === '/__preview.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'crm_lab_preview.js')), TYPES['.js']);
    if (url.pathname === '/__frames.html') {
      const list = cases[url.searchParams.get('g')];
      const frames = list.map((c) => `<iframe data-k="${c.k}" allow="fullscreen" style="width:${c.w}px;height:${c.h}px;border:0;display:block" src="${frameSrc(c.v, c.theme, c.fs !== false)}"></iframe>`);
      return send(`<!doctype html><html><body style="margin:0">${frames.join('')}<pre id="all"></pre><script>
        setTimeout(() => { const out = {}; document.querySelectorAll('iframe').forEach((f) => { const d = f.contentDocument && f.contentDocument.getElementById('layout'); out[f.dataset.k] = d ? JSON.parse(d.textContent) : null; });
          document.getElementById('all').textContent = JSON.stringify(out); }, 14000);</script></body></html>`, 'text/html');
    }
    if (url.pathname === '/__one.html') {
      const w = Number(url.searchParams.get('w')) || 1280;
      const h = Number(url.searchParams.get('h')) || 800;
      return send(`<!doctype html><html><body style="margin:0"><iframe allow="fullscreen" style="width:${w}px;height:${h}px;border:0;display:block" src="${frameSrc(url.searchParams.get('v'))}"></iframe></body></html>`, 'text/html');
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

// Un grupo por tamaño de pantalla (más los casos sueltos) para no cargar 50 iframes a la vez.
const CASES = {};
for (const [w, h] of SIZES) CASES[`${w}x${h}`] = VIEWS.map((v) => ({ k: `${v}-${w}x${h}`, v, w, h }));
CASES.extra = [
  { k: 'otro-844x390', v: 'list', w: 844, h: 390, theme: 'otro' },
  { k: 'nofs-844x390', v: 'list', w: 844, h: 390, fs: false },
  { k: 'login-390x844', v: 'login', w: 390, h: 844 },
  { k: 'idle-1280x800', v: 'idle', w: 1280, h: 800 },
];

test('CRM VELVET-LAB: cabe en celular horizontal y vertical y en tableta, con los colores del tema',
  { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 600000 }, async () => {
    const server = await serve(CASES);
    const base = `http://127.0.0.1:${server.address().port}`;
    const r = {};
    try {
      for (const g of Object.keys(CASES)) {
        const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-crm-layout-'));
        try {
          const html = await chrome([`--user-data-dir=${profile}`, '--window-size=1400,1400', '--virtual-time-budget=22000', '--dump-dom', `${base}/__frames.html?g=${g}`]);
          const m = html.match(/<pre id="all">([^<]*)<\/pre>/);
          assert.ok(m && m[1], `${g}: sin resultado de la medición`);
          Object.assign(r, JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')));
        } finally {
          try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
        }
      }
      if (process.env.CX_DEBUG) console.log(JSON.stringify(r, null, 1));
      const ORDER = ['Ana María Restrepo Villalobos', 'Carla Díaz', 'Bea Gómez', 'Daniela Ruiz (prueba)', 'Eva Ríos', 'Fabiola', 'Gina', 'Helena', 'Irene', 'Juana', 'Karen', 'Laura'];
      for (const [w, h] of SIZES) {
        const size = `${w}x${h}`;
        const landscape = w > h;
        for (const v of VIEWS) {
          const x = r[`${v}-${size}`];
          const k = `${v} ${size}`;
          assert.ok(x && x.mounted, `${k}: no se montó ${JSON.stringify(x)}`);
          assert.equal(x.page_scroll, false, `${k}: la página hace scroll`);
          assert.equal(x.page_overflow, false, `${k}: la página se sale de ancho`);
          assert.equal(x.top_visible, true, `${k}: la barra superior no se ve completa`);
          assert.deepEqual(x.bad, [], `${k}: textos que desbordan: ${JSON.stringify(x.bad)}`);
          assert.deepEqual(x.low_contrast, [], `${k}: contraste bajo: ${JSON.stringify(x.low_contrast)}`);
          assert.equal(x.per_person, false, `${k}: nada "por persona"`);
          assert.deepEqual(x.squashed, [], `${k}: textos aplastados o recortados: ${JSON.stringify(x.squashed)}`);
          assert.deepEqual(x.spill, [], `${k}: textos que se salen de su tarjeta: ${JSON.stringify(x.spill)}`);
          if (v !== 'list') assert.equal(x.win_visible, true, `${k}: la ventana se sale de la pantalla`);
        }
        const list = r[`list-${size}`];
        assert.deepEqual(list.tiles.map((t) => t.split('|')[1]), ORDER, `${size}: trabajando → en pausa → sin turno, alfabético`);
        assert.deepEqual(list.tiles.slice(0, 3).map((t) => t.split('|')[0]), ['is-working', 'is-working', 'is-on_break']);
        assert.equal(list.columns, landscape ? 4 : 2, `${size}: columnas de la cuadrícula`);
        assert.equal(list.colors.working, AQUA, `${size}: TRABAJANDO con el aqua del tema de Velvet`);
        assert.equal(new Set(Object.values(list.colors)).size, 4, `${size}: cada estado con su color ${JSON.stringify(list.colors)}`);
        assert.match(list.clock, /^\d+:\d{2}:\d{2}$/, 'cronómetro h:mm:ss');
        assert.deepEqual(list.chips, ['● 2 trabajando', '● 1 en pausa']);
        assert.equal(list.fs_button, true, 'pantalla completa con soporte');
        if (h <= 400) assert.equal(list.grid_scrolls, true, `${size}: con más colaboradores, solo la cuadrícula hace scroll`);
        for (const v of ['pin', 'startpin']) {
          assert.equal(r[`${v}-${size}`].keys, 12, `${size}: teclado 3 x 4`);
          assert.equal(r[`${v}-${size}`].keys_visible, 12, `${size} ${v}: las 12 teclas completas y de 48 px o más`);
          assert.equal(r[`${v}-${size}`].zero_visible, true, `${size}: el 0 visible`);
        }
        assert.equal(r[`nopin-${size}`].ask_admin, true, 'sin PIN: Pide tu PIN al administrador');
        for (const v of ['start', 'startpick']) {
          assert.equal(r[`${v}-${size}`].pin_steps, true, `${size}: 1 · PIN marcado en el PIN`);
          assert.ok(r[`${v}-${size}`].refs_visible >= 2, `${size} ${v}: lista de referencias visible`);
          assert.equal(r[`${v}-${size}`].startgo_visible, true, `${size} ${v}: botón Iniciar visible`);
        }
        assert.equal(r[`start-${size}`].start_disabled, true, `${size}: sin referencia el botón está deshabilitado`);
        assert.equal(r[`startpick-${size}`].start_label, '▶ Iniciar turno en Mystic jacket con capota larga');
        assert.deepEqual(r[`person-${size}`].actions, ['Pausa', 'Fin de turno', 'Cambiar referencia', 'Cerrar prendas']);
        assert.equal(r[`person-${size}`].acts_visible, 4, `${size}: acciones del turno visibles`);
        assert.equal(r[`refs-${size}`].refs, 5, 'buscar referencia activa');
        assert.ok(r[`refs-${size}`].refs_visible >= 2, `${size}: referencias visibles`);
        assert.deepEqual(r[`close-${size}`].sizes, ['SPendiente 12', 'MPendiente 6', 'LPendiente 0']);
        assert.equal(r[`close-${size}`].qty, '7', 'cantidad con el teclado numérico');
        assert.equal(r[`close-${size}`].keys_visible, r[`close-${size}`].keys, `${size}: teclado de cantidad completo`);
        assert.equal(r[`over-${size}`].over, true, 'supera el pendiente: pide confirmación');
        assert.ok(r[`over-${size}`].calls.some((c) => c.startsWith('POST /crm-lab/') && c.endsWith('/action')));
      }
      const otro = r['otro-844x390'];
      assert.ok(otro && otro.mounted);
      assert.deepEqual(otro.low_contrast, [], `otro tema: contraste ${JSON.stringify(otro.low_contrast)}`);
      for (const k of ['working', 'on_break', 'sin_turno', 'bar']) {
        assert.notEqual(otro.colors[k], r['list-844x390'].colors[k], `con otro tema cambia el color de ${k}`);
      }
      assert.equal(r['nofs-844x390'].fs_button, false, 'sin soporte de pantalla completa no hay botón');
      assert.equal(r['login-390x844'].login, true, 'ingreso del panel con usuario y clave');
      assert.equal(r['idle-1280x800'].before_idle, true);
      assert.equal(r['idle-1280x800'].back_to_list, true, 'a los 20 s sin uso vuelve a la lista');
      assert.equal(r['idle-1280x800'].employee_token_cleared, true, 'y olvida el token del colaborador');
      const shots = process.env.CX_CRM_SHOTS;
      if (shots) {
        fs.mkdirSync(shots, { recursive: true });
        const want = (process.env.CX_CRM_SHOTS_VIEWS || 'list,startpin,startpick,person,close').split(',');
        for (const [w, h] of SIZES) {
          for (const v of want) {
            const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-crm-shot-'));
            await chrome([`--user-data-dir=${profile}`, `--window-size=${w},${h}`, '--hide-scrollbars', '--virtual-time-budget=9000',
              `--screenshot=${path.join(shots, `crm-${v}-${w}x${h}.png`)}`, `${base}/__one.html?w=${w}&h=${h}&v=${v}`]);
            try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
          }
        }
      }
    } finally {
      server.close();
    }
  });
