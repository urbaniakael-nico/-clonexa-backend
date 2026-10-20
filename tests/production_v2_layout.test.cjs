// Producción v2 (056J): la barra de filtros y PDF se ve COMPLETA. Antes usaba la clase
// .pp-bar, que en la misma hoja es la barra de los gráficos (10 px y overflow oculto) y
// la recortaba a una franja. Chrome headless con client.css + production_v2.css reales,
// a 1280, 1024 y 375 px (y con Personalizado abierto): sin recorte, filtros a la
// izquierda y PDF a la derecha en escritorio, dos filas en celular, sin scroll
// horizontal y texto de los botones con contraste AA. Sin Chrome la prueba se salta.
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
const CASES = [[1280, 'week'], [1024, 'week'], [375, 'week'], [1280, 'custom'], [375, 'custom']];

const INSIGHTS = { company: { name: 'Velvet', logo_url: '' }, period: { from: '2026-10-13', to: '2026-10-19', by: 'week' },
  kpis: { workshop_now: { status: 'ok', value: 1, working: 1, paused: 0, lots: 1 } }, lots_in_process: [], live: [], series: [], team_time: { by_reference: [] }, alerts: [] };

function page(preset) {
  // Tema de Velvet (marca del panel inicial: primario morado, texto negro sobre fondo turquesa).
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <link rel="stylesheet" href="/client-static/client.css"><link rel="stylesheet" href="/client-static/production_v2.css">
  <style>:root{--cx-primary:#a600ff;--cx-secondary:#8cff00;--cx-bg:#00ffe1;--cx-text:#000000}body{margin:0;background:var(--cx-bg);color:var(--cx-text);font-family:system-ui}</style></head>
  <body><section class="client-main" style="padding:16px"><div id="host"></div></section><pre id="layout"></pre>
  <script>window.fetch=async()=>({ok:true,status:200,json:async()=>(${JSON.stringify(INSIGHTS)})});</script>
  <script src="/client-static/production_v2.js"></script>
  <script>(async()=>{const P=window.CxProductionV2;P.model.preset=${JSON.stringify(preset)};
    await P.mount({companyId:'c',apiBase:'',token:()=>'',host:()=>document.getElementById('host')});
    const bar=document.querySelector('.pp-toolbar');const r=bar.getBoundingClientRect();
    const seg=document.querySelector('.pp-seg').getBoundingClientRect();const act=document.querySelector('.pp-actions').getBoundingClientRect();
    const cut=[...bar.querySelectorAll('button,input')].filter((b)=>{const x=b.getBoundingClientRect();return x.height<30||x.top<r.top-1||x.bottom>r.bottom+1||x.left<r.left-1||x.right>r.right+1;}).map((b)=>b.textContent.trim()||b.tagName);
    const lum=(c)=>{const m=c.match(/[\\d.]+/g).map(Number);const f=(v)=>{v/=255;return v<=0.03928?v/12.92:((v+0.055)/1.055)**2.4};return 0.2126*f(m[0])+0.7152*f(m[1])+0.0722*f(m[2]);};
    const bg=(el)=>{for(let n=el;n;n=n.parentElement){const c=getComputedStyle(n).backgroundColor;const a=(c.match(/[\\d.]+/g)||[]).map(Number);if(a.length>=3&&(a.length===3||a[3]>=0.99))return c;}return 'rgb(0,255,225)';};
    const low=[...bar.querySelectorAll('button')].map((b)=>{const a=lum(getComputedStyle(b).color)+0.05;const c=lum(bg(b))+0.05;return {t:b.textContent.trim(),r:Math.max(a,c)/Math.min(a,c)};}).filter((x)=>x.r<4.5);
    document.getElementById('layout').textContent=JSON.stringify({w:innerWidth,h:Math.round(r.height),overflowY:bar.scrollHeight>bar.clientHeight+1,overflowX:bar.scrollWidth>bar.clientWidth+1,
      page:document.documentElement.scrollWidth>innerWidth+1,cut,low,overflowCss:getComputedStyle(bar).overflow,
      sameRow:Math.abs(seg.top-act.top)<6,actionsRight:act.right>=r.right-40,twoRows:act.top>=seg.bottom-1});})();</script></body></html>`;
}

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/__p.html') return send(page(url.searchParams.get('preset')), 'text/html; charset=utf-8');
    if (url.pathname === '/__frames.html') {
      const frames = CASES.map(([w, p]) => `<iframe data-k="${w}-${p}" style="width:${w}px;height:700px;border:0;display:block" src="/__p.html?preset=${p}"></iframe>`);
      return send(`<!doctype html><html><body style="margin:0">${frames.join('')}<pre id="all"></pre><script>
        setTimeout(() => { const out = {}; document.querySelectorAll('iframe').forEach((f) => { const d = f.contentDocument && f.contentDocument.getElementById('layout'); out[f.dataset.k] = d && d.textContent ? JSON.parse(d.textContent) : null; });
          document.getElementById('all').textContent = JSON.stringify(out); }, 5000);</script></body></html>`, 'text/html');
    }
    const file = url.pathname.startsWith('/client-static/') ? path.join(WEB, url.pathname.slice('/client-static/'.length)) : null;
    if (file && file.startsWith(WEB) && fs.existsSync(file)) return send(fs.readFileSync(file), file.endsWith('.css') ? 'text/css' : 'application/javascript');
    res.writeHead(404); res.end();
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

test('Producción v2: barra de filtros y PDF completa a 1280, 1024 y 375 px', { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 200000 }, async () => {
  const server = await serve();
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-pp-layout-'));
  try {
    const out = await new Promise((resolve, reject) => execFile(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', `--user-data-dir=${profile}`,
      '--virtual-time-budget=8000', '--window-size=1400,900', '--dump-dom', `http://127.0.0.1:${server.address().port}/__frames.html`],
      { timeout: 150000, maxBuffer: 32 * 1024 * 1024 }, (e, so) => (e ? reject(e) : resolve(so))));
    const m = /<pre id="all">([\s\S]*?)<\/pre>/.exec(out);
    assert.ok(m && m[1], 'el arnés no terminó');
    const all = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&'));
    if (process.env.CX_DEBUG) console.log(JSON.stringify(all, null, 1));
    for (const [w, p] of CASES) {
      const r = all[`${w}-${p}`];
      assert.ok(r, `${w} ${p}: sin medida`);
      assert.ok(r.h >= 48, `${w} ${p}: la barra mide ${r.h}px (recortada)`);
      assert.equal(r.overflowCss, 'visible', `${w} ${p}: overflow`);
      assert.deepEqual(r.cut, [], `${w} ${p}: controles cortados ${JSON.stringify(r.cut)}`);
      assert.equal(r.overflowX || r.page, false, `${w} ${p}: scroll horizontal`);
      assert.deepEqual(r.low, [], `${w} ${p}: contraste bajo ${JSON.stringify(r.low)}`);
      if (w >= 1024 && p === 'week') assert.ok(r.sameRow && r.actionsRight, `${w}: filtros a la izquierda y PDF a la derecha en la misma fila`);
      if (w === 375) assert.ok(r.twoRows, '375: filtros y PDF en dos filas');
    }
  } finally {
    server.close();
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
  }
});
