// Información de cortes con clics reales en el portal (390 y 1280 px): en una referencia recién creada,
// lo que se recibe por talla, la novedad por sección y el envío a Bombón se guardan y se ven al instante en
// Balance, Bitácora, la tarjeta de Estado (Recibido por talla) y los cortes por fecha del editor. Una talla
// que la referencia no tiene pide confirmar antes de guardar. Chrome headless, sin capturas; sin Chrome se salta.
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
const VELVET = 'd63cf68c-be5b-4a30-aee4-341973018db1';
const WIDTHS = [390, 1280];
const TYPES = { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml', '.webp': 'image/webp' };

// Corre dentro del portal, cuando la pantalla ya se dibujó.
function runner() {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const $ = (s) => document.querySelector(s);
  const txt = (el) => (el ? el.textContent.replace(/\s+/g, ' ').trim() : null);
  // Como una persona: escribe (input) y sale de la casilla (change).
  const type = (el, v) => { el.focus(); el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); };
  const pick = (el, v) => { el.value = v; el.dispatchEvent(new Event('change', { bubbles: true })); };
  const go = async () => {
    while (!$('#layout')) await sleep(200);
    const out = {};
    pick($('[data-rv-cut-ref]'), 'rs');
    await sleep(800);
    out.sizes = [...document.querySelectorAll('[data-rv-recv]')].map((b) => b.getAttribute('data-rv-recv'));
    out.balance0 = txt($('.rv-kpis'));
    out.log0 = txt($('.rv-days'));
    $('[data-rv-recv="S"]').click(); type($('[data-rv-recv-qty="S"]'), '40');
    $('[data-rv-recv="M"]').click(); type($('[data-rv-recv-qty="M"]'), '22');
    type($('[data-rv-nov-qty="corte"]'), '2'); type($('[data-rv-nov-note="corte"]'), 'Piezas manchadas');
    type($('[data-rv-dep="quantity"]'), '1'); pick($('[data-rv-dep="size"]'), 'S');
    out.kept = { s: ($('[data-rv-recv-qty="S"]') || {}).value, m: ($('[data-rv-recv-qty="M"]') || {}).value, nov: ($('[data-rv-nov-qty="corte"]') || {}).value };
    out.save_disabled = $('[data-rv-cut-save]').disabled;
    $('[data-rv-cut-save]').click();
    await sleep(1500);
    out.posts = window.__cutPosts.slice();
    out.error = txt($('.rv-notice.is-error'));
    out.balance = txt($('.rv-kpis'));
    out.log = txt($('.rv-days'));
    // Misma talla, fecha y cantidad que la recepción inicial: pregunta; "es el mismo" no suma.
    window.__asked = [];
    window.confirm = (q) => { window.__asked.push(q); return false; };
    $('[data-rv-recv="S"]').click(); type($('[data-rv-recv-qty="S"]'), '46');
    $('[data-rv-cut-save]').click();
    await sleep(600);
    out.posts_after_dup = window.__cutPosts.length;
    out.dup_notice = txt($('.rv-notice'));
    // Talla que la referencia no tiene: pide confirmar y, sin confirmar, no guarda.
    $('[data-rv-recv="L"]').click(); type($('[data-rv-recv-qty="L"]'), '5');
    $('[data-rv-cut-save]').click();
    await sleep(600);
    out.asked = window.__asked.slice();
    out.posts_after_l = window.__cutPosts.length;
    // Salir con datos sin guardar avisa; aceptando, se va a Estado de referencias (tarjeta y editor).
    window.confirm = (q) => { window.__asked.push(q); return true; };
    $('[data-rv-tab="estado"]').click();
    out.asked_leave = window.__asked.slice(2);
    await sleep(600);
    const card = [...document.querySelectorAll('.rv-gcard')].find((c) => /rojita medium/.test(c.textContent));
    out.card = card ? [...card.querySelectorAll('.rv-gline:not(.is-head)')].map((l) => [...l.children].slice(0, 4).map((c) => txt(c))) : null;
    out.card_foot = card ? txt(card.querySelector('.rv-gfoot p')) : null;
    if (card) card.querySelector('[data-rv-gopen]').click();
    await sleep(800);
    out.editor_cuts = txt($('.rv-gcuts'));
    const p = document.createElement('pre'); p.id = 'e2e'; p.textContent = JSON.stringify(out); document.body.appendChild(p);
  };
  go().catch((e) => { const p = document.createElement('pre'); p.id = 'e2e'; p.textContent = JSON.stringify({ crash: String((e && e.stack) || e) }); document.body.appendChild(p); });
}

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/client.html') {
      return send(fs.readFileSync(path.join(WEB, 'client.html'), 'utf8').replace('<link rel="stylesheet"', '<script src="/__preview.js"></script><script src="/__runner.js"></script>\n  <link rel="stylesheet"'), 'text/html');
    }
    if (url.pathname === '/__preview.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'references_v2_preview.js')), TYPES['.js']);
    if (url.pathname === '/__runner.js') return send(`(${runner.toString()})();`, TYPES['.js']);
    if (url.pathname === '/client-static/garment_catalog.json') return send(fs.readFileSync(path.join(ROOT, 'app', 'services', 'garment_catalog.json')), TYPES['.json']);
    if (url.pathname === '/__frames.html') {
      const frames = WIDTHS.map((w) => `<iframe data-k="${w}" style="width:${w}px;height:900px;border:0;display:block" src="/client.html?company_id=${VELVET}&theme=velvet&tab=cortes&life=1&cuts=1"></iframe>`);
      return send(`<!doctype html><html><body style="margin:0">${frames.join('')}<pre id="all"></pre><script>
        setTimeout(() => { const out = {}; document.querySelectorAll('iframe').forEach((f) => { const d = f.contentDocument && f.contentDocument.getElementById('e2e'); out[f.dataset.k] = d && d.textContent ? JSON.parse(d.textContent) : null; });
          document.getElementById('all').textContent = JSON.stringify(out); }, 16000);</script></body></html>`, 'text/html');
    }
    const file = url.pathname.startsWith('/client-static/') ? path.join(WEB, url.pathname.slice('/client-static/'.length)) : null;
    if (file && file.startsWith(WEB) && fs.existsSync(file) && fs.statSync(file).isFile()) return send(fs.readFileSync(file), TYPES[path.extname(file)] || 'application/octet-stream');
    res.writeHead(404); res.end();
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

test('un corte nuevo en una referencia recién creada se guarda y se ve en Balance, Bitácora, tarjeta y editor', { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 200000 }, async () => {
  const server = await serve();
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-cuts-'));
  let all;
  try {
    const dom = await new Promise((resolve, reject) => execFile(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', `--user-data-dir=${profile}`, '--virtual-time-budget=24000',
      '--window-size=1400,1900', '--dump-dom', `http://127.0.0.1:${server.address().port}/__frames.html`], { timeout: 150000, maxBuffer: 64 * 1024 * 1024 }, (e, so) => (e ? reject(e) : resolve(so))));
    const m = /<pre id="all">([^<]*)<\/pre>/.exec(dom);
    assert.ok(m && m[1], 'sin resultado');
    all = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
  } finally {
    server.close();
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
  }
  if (process.env.CX_DEBUG) console.log(JSON.stringify(all, null, 1));
  for (const w of WIDTHS) {
    const r = all[w];
    assert.ok(r, `${w}: sin resultado`);
    assert.equal(r.crash, undefined, `${w}: ${r.crash}`);
    assert.deepEqual(r.sizes, ['S', 'M', 'L'], `${w}: tallas de la prenda`);
    assert.equal(r.save_disabled, false, `${w}: Guardar registro habilitado`);
    assert.equal(r.error, null, `${w}: sin error`);
    assert.match(r.balance0, /^71\s*Recibido\s*0\s*Con novedad\s*0\s*A Bombón\s*71\s*Disponible$/, `${w}: recepción inicial al instante`);
    assert.match(r.log0, /Recepción inicial · total 71/, `${w}`);
    assert.match(r.log0, /Referencia creada · .+ · Velvet Admin/, `${w}`);
    assert.match(r.log0, /Recepción inicial · S 46 · M 25 · \d\d\/\d\d\/\d{4} · Velvet Admin/, `${w}`);
    assert.equal(r.posts.length, 1, `${w}: se envió el registro`);
    const items = r.posts[0].items.map((i) => [i.kind, i.reference_id, i.size || '', i.quantity, i.section || '']);
    assert.deepEqual(items, [['ingreso', 'rs', 'S', 40, ''], ['ingreso', 'rm', 'M', 22, ''], ['novedad', 'rs', '', 2, 'corte'], ['despliegue', 'rs', 'S', 1, '']], `${w}: cada talla con su fila`);
    assert.match(r.balance, /^133\s*Recibido\s*2\s*Con novedad\s*1\s*A Bombón\s*130\s*Disponible$/, `${w}: Balance suma`);
    assert.match(r.log, /Ingreso de corte · total 133/, `${w}: Bitácora`);
    assert.match(r.log, /Recepción inicial · S 46 · M 25/, `${w}: la inicial sigue`);
    assert.match(r.log, /S→40 · M→22/, `${w}: Bitácora por talla`);
    assert.match(r.log, /Corte · 2 · Piezas manchadas/, `${w}: novedad`);
    assert.match(r.log, /Enviado a Bombón · talla S · 1/, `${w}: envío a Bombón`);
    assert.equal(r.asked.length, 2, `${w}: duplicado y talla que no existe piden confirmar`);
    assert.match(r.asked[0], /S ya tiene recepción inicial de 46 hoy\. ¿Es un corte nuevo\?/, `${w}: aviso de duplicado`);
    assert.equal(r.posts_after_dup, 1, `${w}: "es el mismo" no suma`);
    assert.match(r.dup_notice, /No se sumó/, `${w}`);
    assert.match(r.asked[1], /rojita medium no tiene talla L/, `${w}: aviso claro`);
    assert.equal(r.posts_after_l, 1, `${w}: sin confirmar no se guarda`);
    assert.equal(r.asked_leave.length, 1, `${w}: salir sin guardar avisa`);
    assert.match(r.asked_leave[0], /datos sin guardar en Información de cortes \(L 5\)/, `${w}`);
    assert.deepEqual(r.card.map((c) => c.map((x) => x.replace(/\s+/g, ''))), [['Srojo', '46', '86', '0'], ['Mrojo', '25', '47', '0']], `${w}: tarjeta con Recibido por talla`);
    assert.match(r.card_foot, /Recibido 133/, `${w}`);
    assert.match(r.editor_cuts.replace(/\s+/g, ''), /S86·M47133/, `${w}: cortes por fecha del editor`);
  }
});
