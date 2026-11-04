// 064C: flecha atrás/adelante del panel Líder de operación en Chrome real a 390 y 1280 px: cada
// pantalla es una entrada, no recarga ni pierde la sesión, Inicio pregunta antes de salir y atrás
// nunca vuelve al formulario. Sin Chrome, la prueba se salta.
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
const TYPES = { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json' };

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/panel.html') return send(fs.readFileSync(path.join(WEB, 'lider_operacion.html'), 'utf8').replace('<!--CX_LIDER_BOOT-->', '<script src="/__flow.js"></script>'), 'text/html');
    if (url.pathname === '/__flow.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'lider_operacion_history.js')), TYPES['.js']);
    if (url.pathname === '/__fix.json') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'reports_board_caso.json')), TYPES['.json']);
    const file = url.pathname.startsWith('/client-static/') ? path.join(WEB, url.pathname.slice('/client-static/'.length)) : null;
    if (file && file.startsWith(WEB) && fs.existsSync(file) && fs.statSync(file).isFile()) return send(fs.readFileSync(file), TYPES[path.extname(file)] || 'application/octet-stream');
    res.writeHead(404); res.end();
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

function dump(url, profile, width) {
  return new Promise((resolve, reject) => {
    execFile(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', `--user-data-dir=${profile}`, `--window-size=${width},900`, '--virtual-time-budget=40000', '--dump-dom', url],
      { timeout: 150000, maxBuffer: 64 * 1024 * 1024 }, (err, stdout) => (err ? reject(err) : resolve(stdout)));
  });
}

// Paso esperado: pantalla, persona abierta, pregunta abierta.
const EXPECTED = [
  ['login', 'login', false, false],
  ['entro', 'inicio', false, false],
  ['atras en inicio tras entrar', 'inicio', false, true],
  ['no', 'inicio', false, false],
  ['atras otra vez', 'inicio', false, true],
  ['atras con la pregunta abierta', 'inicio', false, true],
  ['no otra vez', 'inicio', false, false],
  ['crm', 'crm', false, false],
  ['reportes mes', 'reportes', false, false],
  ['persona', 'reportes', true, false],
  ['atras cierra persona', 'reportes', false, false],
  ['adelante abre persona', 'reportes', true, false],
  ['atras cierra persona 2', 'reportes', false, false],
  ['atras a crm', 'crm', false, false],
  ['adelante a reportes', 'reportes', false, false],
  ['reportes conserva mes', 'reportes', false, false],
  ['atras a crm 2', 'crm', false, false],
  ['atras a inicio', 'inicio', false, false],
  ['atras pregunta', 'inicio', false, true],
  ['adelante en inicio no rompe', 'inicio', false, false],
  ['barra a inicio', 'inicio', false, false],
  ['atras tras barra a inicio', 'inicio', false, true],
  ['si salir', 'login', false, false],
  ['atras tras salir', 'login', false, false],
];

for (const width of [390, 1280]) {
  test(`064C atrás y adelante a ${width} px`, { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 200000 }, async () => {
    const server = await serve();
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-lo-hist-'));
    try {
      const html = await dump(`http://127.0.0.1:${server.address().port}/panel.html?company_id=c1&type=lider_operacion&lugar=alabama`, profile, width);
      const m = html.match(/<pre id="steps">([^<]*)<\/pre>/);
      assert.ok(m && m[1], 'el recorrido no terminó');
      const steps = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
      assert.ok(!steps.some((s) => s.error), JSON.stringify(steps.at(-1)));
      assert.deepEqual(steps.map((s) => [s.name, s.screen, s.person_open, s.confirm]), EXPECTED);
      for (const s of steps) {
        assert.equal(s.same_page, true, `${s.name}: la página se recargó`);
        assert.equal(s.overflow, false, `${s.name}: se sale de ancho`);
      }
      const named = Object.fromEntries(steps.map((s) => [s.name, s]));
      for (const n of ['entro', 'atras en inicio tras entrar', 'crm', 'atras a crm', 'adelante a reportes', 'atras tras barra a inicio']) assert.equal(named[n].token, 'tok', `${n}: perdió la sesión`);
      assert.equal(named['reportes conserva mes'].preset, 'month', 'volver a Reportes conserva el periodo');
      assert.equal(named['atras tras barra a inicio'].logouts, 0, 'preguntar no cierra la sesión');
      assert.equal(named['si salir'].logouts, 1, 'Sí cierra la sesión en el servidor');
      assert.equal(named['si salir'].token, '');
      assert.equal(named['atras tras salir'].token, '', 'atrás después de salir no devuelve el panel');
    } finally {
      await new Promise((resolve) => server.close(resolve));
      fs.rmSync(profile, { recursive: true, force: true });
    }
  });
}
