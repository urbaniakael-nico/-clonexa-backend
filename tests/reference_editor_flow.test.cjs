// Editor de la referencia (reference_lifecycle) con clics reales en el portal, a 390 y 1280 px, en español:
// casillas separadas, errores en rojo y a la vista, 0 es válido, confirmar con casilla, aplicar y refrescar cifras,
// y cada talla en el mismo orden. Chrome headless, sin capturas; sin Chrome se salta.
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

// Corre dentro del portal, cuando la pantalla ya se midió.
const RUNNER = `(() => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const $ = (s) => document.querySelector(s);
  const LINE = '[data-rv-tl="10"]';
  const rect = (el) => { const r = el.getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom }; };
  const onTop = (el) => { el.scrollIntoView({ block: 'center' }); const r = el.getBoundingClientRect(); const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return hit === el; };
  const type = (el, v) => { el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); };
  const visible = (el) => { const r = el.getBoundingClientRect(); const box = $('.rv-modal').getBoundingClientRect(); return r.top >= box.top - 1 && r.bottom <= box.bottom + 1 && r.top >= 0 && r.bottom <= innerHeight; };
  const red = (el) => { const m = getComputedStyle(el).color.match(/[\\d.]+/g).map(Number); return m[0] > m[1] + 60 && m[0] > m[2] + 60; };
  const go = async () => {
    while (!$('#layout')) await sleep(200);
    const out = { lines: [] };
    // Fila 1, 2 y 3 de cada talla con reference_id: mismo lugar en todas.
    document.querySelectorAll('.rv-gmline.is-life').forEach((l) => {
      const a = rect(l), n = [...l.querySelectorAll('.rv-tl-nums > span')].map((s) => Math.round(rect(s).l - a.l));
      const c = [...l.querySelector('.rv-tl-row1').children].map((s) => Math.round(rect(s).l - a.l));
      out.lines.push({ size: l.getAttribute('data-rv-tl'), nums: n, first: c[0], meta: c[1], color: c[2],
        labels: [...l.querySelectorAll('.rv-tl-nums small')].map((s) => s.textContent),
        order: rect(l.querySelector('.rv-tl-row1')).b <= rect(l.querySelector('.rv-tl-nums')).t + 1 && rect(l.querySelector('.rv-tl-nums')).b <= rect(l.querySelector('.rv-tl-acts')).t + 1,
        buttons: [...l.querySelectorAll('.rv-tl-acts > button, .rv-tl-acts summary')].map((b) => b.textContent.trim()),
        inputs: l.querySelectorAll('.rv-tl-acts input[type="number"]').length, cut: l.classList.contains('is-cut') });
    });
    out.totals = $('.rv-life-totals').textContent.replace(/\\s+/g, ' ');
    $('[data-rv-lf-edit]').click();
    out.edit = [...document.querySelectorAll('.rv-edit-panel button')].map((b) => b.textContent.trim());

    $('.rv-edit-panel [data-rv-lf-start="correct"][data-rv-lf-size="10"]').click();
    let value = $('[data-rv-lf="value"]'), why = $('[data-rv-lf="reason"]');
    const a = rect(value), b = rect(why);
    out.fields = { separate: a.b <= b.t || b.b <= a.t || a.r <= b.l || b.r <= a.l, stacked: a.b <= b.t, side: a.r <= b.l,
      value_on_top: onTop(value), reason_on_top: onTop(why), labels: [value.closest('label').firstChild.textContent.trim(), why.closest('label').firstChild.textContent.trim()] };

    $('[data-rv-lf-next="correct2"]').click();
    const e1 = $('[data-rv-lf-err="value"]'), e2 = $('[data-rv-lf-err="reason"]');
    out.errors = { value: e1 && e1.textContent, reason: e2 && e2.textContent, red: !!e1 && red(e1) && red(e2), in_view: !!e1 && visible(e1) && visible(e2),
      below_field: !!e1 && rect(e1).t >= rect($('[data-rv-lf="value"]')).b - 1, step: window.CxReferencesV2.model.lifeFlow.step };

    type($('[data-rv-lf="value"]'), '0');
    $('[data-rv-lf-next="correct2"]').click();
    const e3 = $('[data-rv-lf-err="value"]'), e4 = $('[data-rv-lf-err="reason"]');
    out.zero = { value_error: e3 && e3.textContent, reason_error: e4 && e4.textContent, kept: $('[data-rv-lf="value"]').value };

    type($('[data-rv-lf="reason"]'), 'Registrado por error');
    $('[data-rv-lf-next="correct2"]').click();
    const flow = $('.rv-life-flow');
    out.confirm = { text: flow.textContent.replace(/\\s+/g, ' '), disabled_before: $('[data-rv-lf-next="correctgo"]').disabled, in_view: visible(flow) };
    $('[data-rv-lf="checked"]').click();
    out.confirm.disabled_after = $('[data-rv-lf-next="correctgo"]').disabled;
    $('[data-rv-lf-next="correctgo"]').click();
    await sleep(1500);
    const line = $(LINE);
    out.applied = { post: window.__lifePosts[0], figures: [...line.querySelectorAll('.rv-tl-nums span')].map((s) => s.textContent.replace(/\\s+/g, ' ').trim()), flow_closed: !$('.rv-life-flow'),
      history: (line.querySelector('.rv-life-history') || {}).textContent, notice: ($('.rv-life-ok') || {}).textContent, modal_open: !!$('.rv-modal') };
    const p = document.createElement('pre'); p.id = 'e2e'; p.textContent = JSON.stringify(out); document.body.appendChild(p);
  };
  go().catch((e) => { const p = document.createElement('pre'); p.id = 'e2e'; p.textContent = JSON.stringify({ crash: String(e && e.stack || e) }); document.body.appendChild(p); });
})();`;

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/client.html') {
      return send(fs.readFileSync(path.join(WEB, 'client.html'), 'utf8').replace('<link rel="stylesheet"', '<script src="/__preview.js"></script><script src="/__runner.js"></script>\n  <link rel="stylesheet"'), 'text/html');
    }
    if (url.pathname === '/__preview.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'references_v2_preview.js')), TYPES['.js']);
    if (url.pathname === '/__runner.js') return send(RUNNER, TYPES['.js']);
    if (url.pathname === '/client-static/garment_catalog.json') return send(fs.readFileSync(path.join(ROOT, 'app', 'services', 'garment_catalog.json')), TYPES['.json']);
    if (url.pathname === '/__frames.html') {
      const frames = WIDTHS.map((w) => `<iframe data-k="${w}" style="width:${w}px;height:900px;border:0;display:block" src="/client.html?company_id=${VELVET}&theme=velvet&tab=estado&life=1&e2e=1"></iframe>`);
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

test('corregir producido con clics reales a 390 y 1280 px', { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 200000 }, async () => {
  const server = await serve();
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-editor-'));
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

    // Cada talla en el mismo orden y lugar.
    const full = r.lines.filter((l) => !l.cut);
    assert.ok(full.length >= 2, `${w}: tallas`);
    for (const l of r.lines) {
      assert.equal(l.order, true, `${w} ${l.size}: filas en orden`);
      assert.deepEqual(l.labels, ['Recibido', 'Producido', 'Pendiente'], `${w} ${l.size}`);
      assert.deepEqual(l.nums, r.lines[0].nums, `${w} ${l.size}: cifras en el mismo lugar`);
      assert.equal(l.meta, r.lines[0].meta, `${w} ${l.size}: Meta en el mismo lugar`);
      assert.equal(l.color, r.lines[0].color, `${w} ${l.size}: Color en el mismo lugar`);
    }
    for (const l of full.filter((x) => x.size === '10')) {
      assert.deepEqual(l.buttons, ['Terminar ciclo'], `${w}: fila 3`);
      assert.equal(l.inputs, 1, `${w}: una casilla`);
    }
    for (const b of ['Cambiar nombre', 'Corregir producción terminada', 'Reiniciar ciclo', 'Archivar']) assert.ok(r.edit.includes(b), `${w}: Editar tiene ${b}: ${r.edit}`);

    // El total usa Producido.
    assert.match(r.totals, /Producido \d+/, `${w}`);
    assert.match(r.totals, /Horas por prenda/, `${w}`);

    // Dos casillas separadas con su etiqueta; una debajo de otra en celular.
    assert.equal(r.fields.separate, true, `${w}: casillas encimadas`);
    assert.equal(r.fields.value_on_top && r.fields.reason_on_top, true, `${w}: las dos se pueden tocar`);
    assert.deepEqual(r.fields.labels, ['Nuevo valor', 'Motivo (obligatorio)']);
    if (w === 390) assert.equal(r.fields.stacked, true, '390: una debajo de otra');
    if (w === 1280) assert.equal(r.fields.side, true, '1280: lado a lado');

    // Errores en rojo, bajo cada casilla y a la vista.
    assert.equal(r.errors.value, 'Valor inválido', `${w}`);
    assert.equal(r.errors.reason, 'Escribe el motivo', `${w}`);
    assert.equal(r.errors.red, true, `${w}: en rojo`);
    assert.equal(r.errors.in_view, true, `${w}: a la vista`);
    assert.equal(r.errors.below_field, true, `${w}: bajo su casilla`);
    assert.equal(r.errors.step, 1);

    // 0 es válido y no se pierde al redibujar.
    assert.equal(r.zero.value_error, null, `${w}: 0 es válido`);
    assert.equal(r.zero.reason_error, 'Escribe el motivo', `${w}`);
    assert.equal(r.zero.kept, '0', `${w}`);

    // Confirmación con casilla.
    assert.match(r.confirm.text, /¿Cambiar producido de 10 de 28 a 0\?/, `${w}`);
    assert.match(r.confirm.text, /Registrado por error/, `${w}`);
    assert.equal(r.confirm.disabled_before, true, `${w}: sin casilla no aplica`);
    assert.equal(r.confirm.disabled_after, false, `${w}: con casilla sí`);
    assert.equal(r.confirm.in_view, true, `${w}`);

    // Aplicar y refrescar cifras.
    assert.equal(r.applied.post.path, 'produced-correction');
    assert.equal(r.applied.post.body.new_value, 0, `${w}: manda 0`);
    assert.equal(r.applied.post.body.reason, 'Registrado por error');
    assert.equal(r.applied.post.body.expected_before, 28);
    assert.equal(r.applied.post.body.confirm && r.applied.post.body.confirm_final, true);
    assert.deepEqual(r.applied.figures, ['Recibido30', 'Producido0', 'Pendiente30'], `${w}: cifras nuevas`);
    assert.equal(r.applied.flow_closed && r.applied.modal_open, true, `${w}`);
    assert.match(r.applied.history, /Corregido 28 → 0 por Dueña · Registrado por error/, `${w}`);
    assert.equal(r.applied.notice, 'Corrección guardada.', `${w}`);
  }
});
