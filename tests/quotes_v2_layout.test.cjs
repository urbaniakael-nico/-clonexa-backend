// Cotizaciones v2 en Chrome headless con quotes_v2.js/.css reales y datos de prueba:
// pasos 1 (producción y referencias), 2 y 3 e historial, a 1280 y 375 px, sin
// desborde horizontal. Si no hay Chrome, se salta. No guarda capturas.
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
const VIEWS = ['prod', 'refs', 'lines', 'done'];
const CASES = VIEWS.flatMap((v) => [[`${v}-1280`, 1280, v], [`${v}-375`, 375, v]]);

const FIXTURES = {
  '/defaults': { company: { name: 'VELVET LAB DE CONFECCIÓN', logo_url: '' }, signature: { id: 's1' }, payment: { method: 'transferencia', name: 'Bancolombia', data: 'Ahorros 123-456789-00' },
    clients: [{ client_name: 'Bombón Moda Infantil SAS con un nombre largo', client_document: '900123456-7', client_phone: '3001234567', client_address: 'Cra 10 # 20-30', client_email: 'compras@bombon.co' }] },
  '/from-production': { lines: [{ key: 'pantset', name: 'PANT SET', description: 'PANT SET · S 40 / M 60 / L 26', quantity: 126, sizes: [{ size: 'S', quantity: 40 }, { size: 'M', quantity: 60 }, { size: 'L', quantity: 26 }],
    closure_ids: ['c1'], unit_price: 12000, price_source: 'op_order' }, { key: 'mystic', name: 'Mystic jacket con nombre muy largo de referencia', description: 'Mystic jacket · M 114', quantity: 114,
    sizes: [{ size: 'M', quantity: 114 }], closure_ids: ['c2'], unit_price: null, price_source: 'manual' }], already_charged: [{ document: 'CB-2026-0012', quantity: 7 }], already_charged_total: 7 },
  '/references': { references: [{ key: 'aurora', name: 'Aurora Azul 💙', active: true, sizes: [{ size: 'S' }, { size: 'M' }, { size: 'L' }], unit_price: 15000, price_source: 'op_order' },
    { key: 'choco', name: 'Choco-fresa', active: true, sizes: [{ size: 'S' }, { size: 'M' }, { size: 'L' }], unit_price: null, price_source: 'manual' }] },
  '/documents': { totals: { active: { count: 2, amount: 1512000 }, paid: { count: 1, amount: 3456000 }, archived: { count: 1, amount: 818000 } },
    documents: [{ id: 'd1', status: 'converted', document_number: 'CB-2026-0013', document_label: 'Cuenta de cobro', client_name: 'Bombón Moda Infantil SAS con un nombre largo', total: 1512000,
      created_at: '2026-10-19T15:00:00Z', items: [], charged_closures: 2 }, { id: 'd2', status: 'issued', document_number: 'CT-2026-0014', document_label: 'Cotización', client_name: 'Cliente B', total: 90000, created_at: '2026-10-18T15:00:00Z', items: [] }] },
  '/report': { collected: 3456000, pending: 1512000 },
};

function page(view) {
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <style>:root{--cx-primary:#7c3aed;--cx-secondary:#f59e0b;--cx-bg:#0f172a;--cx-text:#f8fafc}body{margin:0;background:var(--cx-bg);color:var(--cx-text);font-family:system-ui}
  .client-main{padding:16px}.client-btn{background:var(--cx-primary);color:#fff;border:0}</style>
  <link rel="stylesheet" href="/client-static/quotes_v2.css"></head><body><section class="client-main"><div id="host"></div></section><pre id="layout"></pre>
  <script>const FX=${JSON.stringify(FIXTURES)};window.fetch=async(u)=>{const p=new URL(u,location.href).pathname.replace(/^.*\\/companies\\/[^/]+/,'');
    return {ok:true,status:200,json:async()=>FX[p]||{},headers:{get:()=>''}};};</script>
  <script src="/client-static/quotes_v2.js"></script>
  <script>(async()=>{const Q=window.CxQuotesV2;await Q.mount({companyId:'c1',apiBase:'',token:()=>'t',host:()=>document.getElementById('host')});
    const v=${JSON.stringify(view)};const M=Q.model;
    if(v==='refs'){M.origin='references';M.refs=FX['/references'].references;M.picks={aurora:{S:'2',M:'3'}};}
    if(v==='lines'||v==='done'){M.client={name:'Bombón Moda Infantil SAS con un nombre largo',document:'900123456-7',phone:'',address:'',email:''};Q.buildLines();M.lines.push({description:'Transporte',quantity:1,unit_price:'20000',manual:true});M.step=2;M.discount='10000';M.retention='4';}
    if(v==='done'){M.step=3;M.done={id:'d1',document_label:'Cuenta de cobro',document_number:'CB-2026-0013',client_name:M.client.name,total:1512000};}
    document.getElementById('host').innerHTML=Q.view();
    const W=document.documentElement.clientWidth;const bad=[];
    document.querySelectorAll('#host *').forEach((el)=>{const r=el.getBoundingClientRect();if(r.width&&r.right>W+1&&!el.closest('.qv-refs,.qv-hist[style*=overflow]'))bad.push(el.className||el.tagName);});
    document.getElementById('layout').textContent=JSON.stringify({scroll:document.documentElement.scrollWidth,width:W,bad:bad.slice(0,5)});})();</script></body></html>`;
}

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/__q.html') return send(page(url.searchParams.get('v')), 'text/html; charset=utf-8');
    if (url.pathname === '/__frames.html') {
      const frames = CASES.map(([k, w, v]) => `<iframe data-k="${k}" style="width:${w}px;height:900px;border:0;display:block" src="/__q.html?v=${v}"></iframe>`);
      return send(`<!doctype html><html><body style="margin:0">${frames.join('')}<pre id="all"></pre><script>
        setTimeout(() => { const out = {}; document.querySelectorAll('iframe').forEach((f) => { const d = f.contentDocument && f.contentDocument.getElementById('layout'); out[f.dataset.k] = d && d.textContent ? JSON.parse(d.textContent) : null; });
          document.getElementById('all').textContent = JSON.stringify(out); }, 6000);</script></body></html>`, 'text/html');
    }
    const file = url.pathname.startsWith('/client-static/') ? path.join(WEB, url.pathname.slice('/client-static/'.length)) : null;
    if (file && file.startsWith(WEB) && fs.existsSync(file)) return send(fs.readFileSync(file), file.endsWith('.css') ? 'text/css' : 'application/javascript');
    res.writeHead(404); res.end();
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

test('Cotizaciones v2: pasos e historial a 1280 y 375 px sin desborde', { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 200000 }, async () => {
  const server = await serve();
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-quotes-layout-'));
  try {
    const url = `http://127.0.0.1:${server.address().port}/__frames.html`;
    const out = await new Promise((resolve, reject) => execFile(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', `--user-data-dir=${profile}`,
      '--virtual-time-budget=9000', '--window-size=1400,900', '--dump-dom', url], { timeout: 150000, maxBuffer: 32 * 1024 * 1024 }, (e, so) => (e ? reject(e) : resolve(so))));
    const m = /<pre id="all">([\s\S]*?)<\/pre>/.exec(out);
    assert.ok(m && m[1], 'el arnés no terminó');
    const all = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&'));
    if (process.env.CX_DEBUG) console.log(JSON.stringify(all));
    for (const [k] of CASES) {
      assert.ok(all[k], `${k}: sin medida`);
      assert.ok(all[k].scroll <= all[k].width, `${k}: desborde ${all[k].scroll} > ${all[k].width} ${JSON.stringify(all[k].bad)}`);
      assert.deepEqual(all[k].bad, [], `${k}: elementos fuera ${JSON.stringify(all[k].bad)}`);
    }
  } finally {
    server.close();
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
  }
});
