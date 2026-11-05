// reference_lifecycle: nada se sale de ancho en el editor de la referencia (cada paso de corregir,
// cerrar, renombrar y reabrir) ni en el tablero de Producción con las dos cifras y Cerradas, a 1280,
// 1024 y 375 px con el tema de Velvet. Portal real en Chrome headless; sin Chrome se salta.
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
const FLOWS = ['none', 'correct', 'correcterr', 'correct2', 'close', 'close2', 'rename', 'rename2', 'reopen', 'closed'];
const WIDTHS = [1280, 390, 375];
const TYPES = { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml', '.webp': 'image/webp' };

const INSIGHTS = { company: { name: 'Velvet', logo_url: '' }, period: { from: '2026-10-15', to: '2026-10-30', by: 'week' }, lifecycle: true,
  kpis: { workshop_now: { status: 'ok', value: 4, working: 3, paused: 1, lots: 1 }, closed: { status: 'ok', value: 58, lots: 1 }, sent: { status: 'sin_datos', reason: 'Aún no hay envíos a Bombón registrados en Referencias.' },
    days_per_lot: { status: 'ok', value: 15, lots: 1 }, team_hours_per_garment: { status: 'ok', value: 223, team_minutes: 12886 }, labor_per_garment: { status: 'pendiente', reason: 'Falta valor hora: KRIS, TATA' } },
  lots_in_process: [{ key: 'choco', name: 'Choco-fresa con un nombre bastante largo de referencia', former_names: ['Nombre anterior muy largo de la misma referencia', 'Otro'], meta: 58, closed: 10, pending: 48, received: 58, sent: 0, days_open: 22, started: '2026-10-14', last_activity: '2026-10-30', team: ['GELO', 'KATHE', 'TATA', 'KRIS'], working_now: 2,
    sizes: [{ size: 'S', meta: 44, received: 44, closed: 10, pending: 34 }, { size: 'M', meta: 14, received: 14, closed: 0, pending: 14 }], cuts: [], news: [], total_seconds: 776340, period_seconds: 773160,
    people: [{ name: 'GELO', total_seconds: 250260, period_seconds: 250260 }, { name: 'KRIS', total_seconds: 148800, period_seconds: 145620 }], unclosed: [{ name: 'TATA', started: '2026-11-05T12:00:00+00:00', reason: 'turno_sin_confirmar' }],
    corrections: [{ size: 'S', before: 28, after: 0, actor: 'Dueña de la empresa', reason: 'Se metió por error desde el bot', at: '2026-11-05T12:00:00Z' }],
    account: { allocation: 'repartido por cantidad', sizes: [{ size: 'S', closed: true, closed_qty: 40, meta: 44, received: 44, diff_received: -4, days: 16, seconds: 500000, minutes_per_garment: 208.3, labor_per_garment: 34722 }, { size: 'M', closed: false, meta: 14, received: 14, seconds: 276340, minutes_per_garment: null, labor_per_garment: null }],
      totals: { closed_qty: 40, meta: 58, received: 58, seconds: 776340, days: 16, minutes_per_garment: 323.5, labor_per_garment: null }, labor_missing: ['KRIS', 'TATA'] } }],
  lots_closed: [{ key: 'lote', name: 'Dreamy Jacket', former_names: [], total_seconds: 36000, period_seconds: 0, people: [], unclosed: [],
    account: { sizes: [{ size: 'S', closed: true, closed_qty: 40, meta: 44, received: 44, diff_received: -4, days: 6, seconds: 26667, minutes_per_garment: 11.1, labor_per_garment: 1852 }], totals: { closed_qty: 40, meta: 44, received: 44, seconds: 36000, days: 6, minutes_per_garment: 15, labor_per_garment: 2500 }, labor_missing: [] } }],
  live: [], series: [], team_time: { by_reference: [] }, alerts: [] };

function productionPage(open) {
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <link rel="stylesheet" href="/client-static/client.css"><link rel="stylesheet" href="/client-static/production_v2.css">
  <style>:root{--cx-primary:#a600ff;--cx-secondary:#8cff00;--cx-bg:#00ffe1;--cx-text:#000000}body{margin:0;background:var(--cx-bg);color:var(--cx-text);font-family:system-ui}</style></head>
  <body><section class="client-main" style="padding:16px"><div id="host"></div></section><pre id="layout"></pre>
  <script>window.fetch=async()=>({ok:true,status:200,json:async()=>(${JSON.stringify(INSIGHTS)})});</script>
  <script src="/client-static/production_v2.js"></script>
  <script>(async()=>{const P=window.CxProductionV2;await P.mount({companyId:'c',apiBase:'',token:()=>'',host:()=>document.getElementById('host')});P.model.open=${JSON.stringify(open)};
    document.getElementById('host').innerHTML=P.view();
    const bad=[...document.querySelectorAll('.pp-root *')].filter((el)=>el.scrollWidth>el.clientWidth+1&&el.clientWidth>0&&getComputedStyle(el).display!=='inline').map((el)=>({c:String(el.className),t:(el.textContent||'').trim().slice(0,40),sw:el.scrollWidth,cw:el.clientWidth}));
    document.getElementById('layout').textContent=JSON.stringify({page:document.documentElement.scrollWidth>innerWidth+1,bad});})();</script></body></html>`;
}

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/client.html') {
      return send(fs.readFileSync(path.join(WEB, 'client.html'), 'utf8').replace('<link rel="stylesheet"', '<script src="/__preview.js"></script>\n  <link rel="stylesheet"'), 'text/html');
    }
    if (url.pathname === '/__preview.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'references_v2_preview.js')), TYPES['.js']);
    if (url.pathname === '/client-static/garment_catalog.json') return send(fs.readFileSync(path.join(ROOT, 'app', 'services', 'garment_catalog.json')), TYPES['.json']);
    if (url.pathname === '/__p.html') return send(productionPage(url.searchParams.get('open')), 'text/html; charset=utf-8');
    if (url.pathname === '/__frames.html') {
      const q = url.searchParams.get('which');
      const frames = q === 'refs'
        ? FLOWS.flatMap((flow) => WIDTHS.map((w) => `<iframe data-k="${flow}-${w}" style="width:${w}px;height:1400px;border:0;display:block" src="/client.html?company_id=${VELVET}&theme=velvet&tab=estado&life=1&flow=${flow}"></iframe>`))
        : ['choco', 'lote'].flatMap((open) => WIDTHS.map((w) => `<iframe data-k="${open}-${w}" style="width:${w}px;height:1200px;border:0;display:block" src="/__p.html?open=${open}"></iframe>`));
      const wait = q === 'refs' ? 25000 : 5000;
      return send(`<!doctype html><html><body style="margin:0">${frames.join('')}<pre id="all"></pre><script>
        setTimeout(() => { const out = {}; document.querySelectorAll('iframe').forEach((f) => { const d = f.contentDocument && f.contentDocument.getElementById('layout'); out[f.dataset.k] = d && d.textContent ? JSON.parse(d.textContent) : null; });
          document.getElementById('all').textContent = JSON.stringify(out); }, ${wait});</script></body></html>`, 'text/html');
    }
    const file = url.pathname.startsWith('/client-static/') ? path.join(WEB, url.pathname.slice('/client-static/'.length)) : null;
    if (file && file.startsWith(WEB) && fs.existsSync(file) && fs.statSync(file).isFile()) return send(fs.readFileSync(file), TYPES[path.extname(file)] || 'application/octet-stream');
    res.writeHead(404); res.end();
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

async function measure(which, budget) {
  const server = await serve();
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-life-layout-'));
  try {
    const out = await new Promise((resolve, reject) => execFile(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', `--user-data-dir=${profile}`, `--virtual-time-budget=${budget}`,
      '--window-size=1400,1400', '--dump-dom', `http://127.0.0.1:${server.address().port}/__frames.html?which=${which}`], { timeout: 280000, maxBuffer: 128 * 1024 * 1024 }, (e, so) => (e ? reject(e) : resolve(so))));
    const m = /<pre id="all">([^<]*)<\/pre>/.exec(out);
    assert.ok(m && m[1], 'sin resultado de la medición');
    return JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
  } finally {
    server.close();
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
  }
}

test('editor de la referencia: ningún paso se sale de ancho (1280, 1024 y 375 px)', { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 300000 }, async () => {
  const all = await measure('refs', 32000);
  for (const flow of FLOWS) {
    for (const w of WIDTHS) {
      const r = all[`${flow}-${w}`];
      assert.ok(r, `${flow} ${w}px: no se dibujó`);
      assert.equal(r.page_overflow, false, `${flow} ${w}px: la página se sale de ancho`);
      assert.deepEqual(r.bad, [], `${flow} ${w}px: desborda ${JSON.stringify(r.bad)}`);
      assert.deepEqual(r.low_contrast, [], `${flow} ${w}px: contraste bajo ${JSON.stringify(r.low_contrast)}`);
    }
  }
});

test('Producción: dos cifras, cuenta por talla y Cerradas sin salirse de ancho', { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 200000 }, async () => {
  const all = await measure('prod', 8000);
  for (const open of ['choco', 'lote']) {
    for (const w of WIDTHS) {
      const r = all[`${open}-${w}`];
      assert.ok(r, `${open} ${w}px: sin medida`);
      assert.equal(r.page, false, `${open} ${w}px: scroll horizontal`);
      assert.deepEqual(r.bad, [], `${open} ${w}px: desborda ${JSON.stringify(r.bad)}`);
    }
  }
});
