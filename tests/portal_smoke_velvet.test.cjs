// Prueba de humo del portal (056I) con client.html y client.js REALES en Chrome
// headless, módulos e interruptores de Velvet y fetch simulado:
// - con token del portal y sin token (vista previa por cookie), cada módulo del
//   menú dibuja contenido y no hay errores de JavaScript (056G/056H quedaban en
//   blanco por un ReferenceError al montar Producción v2 y Cotizaciones v2);
// - las llamadas de Producción v2 y Cotizaciones v2 llevan la sesión: el token si
//   existe y siempre credentials "same-origin" (cookie de Admin V2 o vista previa);
// - si esas APIs fallan (401 o 500) se ve el aviso con "Reintentar", nunca en blanco.
// Sin Chrome la prueba se salta.
const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFile } = require('node:child_process');

const WEB = path.resolve(__dirname, '..', 'app', 'web');
const CHROME = [process.env.CHROME_PATH, 'C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'].find((p) => p && fs.existsSync(p));
const CID = 'd63cf68c-be5b-4a30-aee4-341973018db1';
const TYPES = { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html' };
const CASES = [['token', ''], ['cookie', ''], ['token', '401'], ['cookie', '500']];

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/client.html') {
      const html = fs.readFileSync(path.join(WEB, 'client.html'), 'utf8').replace('<link rel="stylesheet"', '<script src="/__preview.js"></script>\n  <link rel="stylesheet"');
      return send(html, 'text/html');
    }
    if (url.pathname === '/__preview.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'portal_smoke_preview.js')), TYPES['.js']);
    const file = url.pathname.startsWith('/client-static/') ? path.join(WEB, url.pathname.slice('/client-static/'.length)) : null;
    if (file && file.startsWith(WEB) && fs.existsSync(file) && fs.statSync(file).isFile()) return send(fs.readFileSync(file), TYPES[path.extname(file)] || 'application/octet-stream');
    res.writeHead(404); res.end();
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

test('Portal de Velvet: ningún módulo queda en blanco, con token o con cookie, y los errores muestran Reintentar',
  { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 300000 }, async () => {
    const server = await serve();
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-portal-smoke-'));
    try {
      const all = {};
      for (const [a, f] of CASES) {  // un Chrome por caso: los iframes del mismo origen comparten localStorage
        const url = `http://127.0.0.1:${server.address().port}/client.html?company_id=${CID}&auth=${a}&fail=${f}`;
        const out = await new Promise((resolve, reject) => execFile(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', `--user-data-dir=${profile}-${a}-${f}`,
          '--virtual-time-budget=40000', '--window-size=1280,900', '--dump-dom', url], { timeout: 120000, maxBuffer: 64 * 1024 * 1024 }, (e, so) => (e ? reject(e) : resolve(so))));
        const m = /<pre id="layout">([\s\S]*?)<\/pre>/.exec(out);
        assert.ok(m && m[1], `${a}-${f}: el arnés no terminó`);
        all[`${a}-${f || 'ok'}`] = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
      }
      if (process.env.CX_DEBUG) console.log(JSON.stringify(all, null, 1));
      for (const [a, f] of CASES) {
        const k = `${a}-${f || 'ok'}`;
        const r = all[k];
        assert.ok(r, `${k}: sin resultado`);
        for (const [code, v] of Object.entries(r.results)) {
          assert.ok(!v.missing, `${k} ${code}: no está en el menú`);
          assert.ok(v.chars > 40, `${k} ${code}: el área principal quedó en blanco (${v.chars}): ${v.sample}`);
          const own = (v.errors || []).filter((e) => /production_v2|quotes_v2|cxV2|056I|056G|056H|ReferenceError/.test(e));
          assert.deepEqual(own, [], `${k} ${code}: errores de JavaScript ${JSON.stringify(own)}`);
        }
        assert.equal(r.results.production.v2, true, `${k}: Producción v2`);
        assert.equal(r.results.cotizacion.v2, true, `${k}: Cotizaciones v2`);
        if (f) {
          assert.ok(r.results.production.retry && r.results.cotizacion.retry, `${k}: falta el aviso con Reintentar`);
        }
        const v2calls = r.calls.filter((c) => /production-v2|quotes-v2/.test(c.p));
        assert.ok(v2calls.length >= 2, `${k}: Producción v2 y Cotizaciones v2 no pidieron datos`);
        for (const c of v2calls) {
          assert.equal(c.credentials, 'same-origin', `${k} ${c.p}: sin cookie`);
          assert.equal(c.auth, a === 'token', `${k} ${c.p}: token ${c.auth}`);
        }
      }
    } finally {
      server.close();
      for (const [a, f] of CASES) { try { fs.rmSync(`${profile}-${a}-${f}`, { recursive: true, force: true }); } catch (_) {} }
      try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
    }
  });
