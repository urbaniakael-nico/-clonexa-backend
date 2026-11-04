// 064B: panel Líder de operación con el tema de VOLTAGE a 390, 768 y 1280 px en español e inglés
// (Chrome headless): sin textos cortados, página sin desborde, AA, botones de 44 px, sin dinero.
// Sin Chrome, la prueba se salta.
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
const WIDTHS = [390, 768, 1280];
const TABS = ['login', 'inicio', 'crm', 'crmd', 'crmc1', 'crmc2', 'pin', 'pinp', 'reportes'];
const LIGHT_TABS = ['login', 'inicio', 'crm', 'crmd', 'crmc2', 'pinp', 'reportes'];
const LANGS = ['es', 'en'];
const TYPES = { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json' };

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/panel.html') {
      return send(fs.readFileSync(path.join(WEB, 'lider_operacion.html'), 'utf8').replace('<!--CX_LIDER_BOOT-->', '<script src="/__preview.js"></script>'), 'text/html');
    }
    if (url.pathname === '/__preview.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'lider_operacion_preview.js')), TYPES['.js']);
    if (url.pathname === '/__fix.json') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'reports_board_caso.json')), TYPES['.json']);
    if (url.pathname === '/__frames.html') {
      const w = Number(url.searchParams.get('w'));
      const light = url.searchParams.get('theme') === 'light';
      const frames = (light ? ['es'] : LANGS).flatMap((l) => (light ? LIGHT_TABS : TABS).map((t) => `<iframe data-k="${l}-${t}" style="width:${w}px;height:1500px;border:0;display:block" src="/panel.html?company_id=c1&type=lider_operacion&tab=${t}&lang=${l}&op=${t === 'crm' ? 0 : 1}&theme=${light ? 'light' : 'dark'}"></iframe>`));
      return send(`<!doctype html><html><body style="margin:0">${frames.join('')}<pre id="all"></pre><script>
        setTimeout(() => { const out = {}; document.querySelectorAll('iframe').forEach((f) => { const d = f.contentDocument && f.contentDocument.getElementById('layout'); out[f.dataset.k] = d ? JSON.parse(d.textContent) : null; });
          document.getElementById('all').textContent = JSON.stringify(out); }, 26000);</script></body></html>`, 'text/html');
    }
    const file = url.pathname.startsWith('/client-static/') ? path.join(WEB, url.pathname.slice('/client-static/'.length)) : null;
    if (file && file.startsWith(WEB) && fs.existsSync(file) && fs.statSync(file).isFile()) return send(fs.readFileSync(file), TYPES[path.extname(file)] || 'application/octet-stream');
    res.writeHead(404); res.end();
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

function dump(url, profile) {
  return new Promise((resolve, reject) => {
    execFile(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', `--user-data-dir=${profile}`, '--window-size=1400,1400', '--virtual-time-budget=34000', '--dump-dom', url],
      { timeout: 150000, maxBuffer: 64 * 1024 * 1024 }, (err, stdout) => (err ? reject(err) : resolve(stdout)));
  });
}

for (const w of WIDTHS) {
  test(`064B panel del líder a ${w} px: ES/EN, sin desborde, AA y 44 px`, { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 200000 }, async () => {
    const server = await serve();
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-lo-layout-'));
    try {
      const html = await dump(`http://127.0.0.1:${server.address().port}/__frames.html?w=${w}`, profile);
      const m = html.match(/<pre id="all">([^<]*)<\/pre>/);
      assert.ok(m && m[1], 'sin resultado de la medición');
      const results = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
      for (const l of LANGS) {
        for (const t of TABS) {
          const r = results[`${l}-${t}`];
          const at = `${w}px ${l} ${t}`;
          assert.ok(r && r.ready, `${at}: no se dibujó`);
          assert.equal(r.page_overflow, false, `${at}: la página se sale de ancho`);
          assert.deepEqual(r.bad, [], `${at}: textos que desbordan`);
          assert.deepEqual(r.low_contrast, [], `${at}: contraste bajo AA`);
          assert.deepEqual(r.small, [], `${at}: botones de menos de 44 px`);
          assert.equal(r.money, false, `${at}: sin valores de pago`);
        }
        assert.equal(results[`${l}-crm`].people, 25, `${w}px ${l}: lista de CRM`);
        assert.ok(results[`${l}-reportes`].board_rows > 0, `${w}px ${l}: tabla del Board`);
        assert.equal(results[`${l}-reportes`].exports, 1, `${w}px ${l}: solo el PDF`);
        assert.equal(results[`${l}-inicio`].modules, 3, `${w}px ${l}: 3 accesos`);
        assert.equal(results[`${l}-pin`].keys, 12, `${w}px ${l}: teclado`);
        assert.deepEqual(results[`${l}-pinp`].actions, ['resume', 'end'], `${w}px ${l}: solo acciones posibles`);
        assert.equal(results[`${l}-crm`].card_finish, 0, `${w}px ${l}: la tarjeta no tiene finalizar`);
        const d = results[`${l}-crmd`];
        assert.ok(d.sheet && d.sheet_link === 1, `${w}px ${l}: el detalle trae el enlace`);
        assert.equal(d.link_style.bg, 'rgba(0, 0, 0, 0)', `${w}px ${l}: sin relleno`);
        assert.equal(d.link_style.color, 'rgb(255, 116, 130)', `${w}px ${l}: texto rojo`);
        assert.equal(d.link_style.border, '0px', `${w}px ${l}: sin borde`);
        const one = results[`${l}-crmc1`];
        assert.deepEqual({ next: one.next, checkbox: one.checkbox, focus: one.focus_cancel, visible: one.cancel_visible }, { next: true, checkbox: false, focus: true, visible: true }, `${w}px ${l}: paso 1`);
        const two = results[`${l}-crmc2`];
        assert.deepEqual({ checkbox: two.checkbox, disabled: two.yes_disabled, focus: two.focus_cancel, visible: two.cancel_visible }, { checkbox: true, disabled: true, focus: true, visible: true }, `${w}px ${l}: paso 2`);
      }
      assert.deepEqual(results['es-inicio'].nav, ['Inicio', 'CRM', 'PIN', 'Reportes', 'Salir']);
      assert.deepEqual(results['en-inicio'].nav, ['Home', 'CRM', 'PIN', 'Reports', 'Sign out']);
      assert.ok(results['en-inicio'].text.includes('Clock in with PIN') && results['en-inicio'].text.includes('this week'));
      assert.ok(results['es-inicio'].text.includes('Marcar con PIN') && results['es-inicio'].text.includes('esta semana'));
      const light = (rgb) => { const [r, g, b] = rgb.match(/[\d.]+/g).map(Number); return (r + g + b) / 3; };
      assert.ok(light(results['es-inicio'].body_bg) < 40, 'fondo oscuro');
      for (const shot of [results['es-inicio'], results['es-crm']]) assert.deepEqual(shot.semaforo, { working: 'rgb(47, 240, 143)', on_break: 'rgb(255, 171, 61)', to_confirm: 'rgb(255, 116, 130)', no_shift: 'rgb(174, 186, 208)' }, 'el mismo semáforo');
      assert.notEqual(results['es-crm'].head_bg, results['es-inicio'].head_bg, 'cada operación con su acento');
      assert.equal(results['es-inicio'].side_by_side, w >= 768, w >= 768 ? 'tablet y escritorio: lado a lado' : 'celular: uno debajo del otro');
    } finally {
      await new Promise((resolve) => server.close(resolve));
      fs.rmSync(profile, { recursive: true, force: true });
    }
  });
}

for (const w of WIDTHS) {
  test(`068A modo claro a ${w} px: fondo claro, sin desborde, AA y 44 px`, { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 200000 }, async () => {
    const server = await serve();
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-lo-light-'));
    try {
      const html = await dump(`http://127.0.0.1:${server.address().port}/__frames.html?w=${w}&theme=light`, profile);
      const m = html.match(/<pre id="all">([^<]*)<\/pre>/);
      assert.ok(m && m[1], 'sin resultado de la medición');
      const results = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
      for (const t of LIGHT_TABS) {
        const r = results[`es-${t}`];
        const at = `${w}px ${t}`;
        assert.ok(r && r.ready, `${at}: no se dibujó`);
        assert.equal(r.page_overflow, false, `${at}: la página se sale de ancho`);
        assert.deepEqual(r.bad, [], `${at}: textos que desbordan`);
        assert.deepEqual(r.low_contrast, [], `${at}: contraste bajo AA`);
        assert.deepEqual(r.small, [], `${at}: botones de menos de 44 px`);
        assert.equal(r.body_bg, 'rgb(238, 243, 250)', `${at}: fondo claro`);
      }
      for (const shot of [results['es-inicio'], results['es-crm']]) assert.deepEqual(shot.semaforo, { working: 'rgb(10, 122, 67)', on_break: 'rgb(168, 77, 6)', to_confirm: 'rgb(192, 24, 58)', no_shift: 'rgb(86, 98, 121)' }, 'semáforo para fondo claro');
      assert.equal(results['es-crmd'].link_style.color, 'rgb(192, 24, 58)', 'finalizar en rojo');
      assert.equal(results['es-crmc2'].yes_disabled, true);
      assert.equal(results['es-crmc2'].focus_cancel, true, 'Cancelar por defecto');
    } finally {
      await new Promise((resolve) => server.close(resolve));
      fs.rmSync(profile, { recursive: true, force: true });
    }
  });
}
