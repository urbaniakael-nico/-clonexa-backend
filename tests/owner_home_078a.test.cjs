// 078A · panel del dueño SIN barra lateral (panel-tm-propuesta.png), para todas las empresas. SOLO DISEÑO:
// - las tarjetas abren la pantalla de siempre (data-client-module), las cifras salen de renderClientHeroKpis;
// - con "Negocio en vivo 3D" la tarjeta grande va primero (2x2 en escritorio); sin el módulo no aparece;
// - colores de la marca con contraste AA en 3 paletas distintas;
// - en Chrome headless: 390 px una columna (3D primero), 768 px dos columnas, 1440 px cuatro; nada desborda,
//   con 3 y con 12 módulos. Si no hay Chrome, la parte de navegador se salta.
const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const { execFile } = require('node:child_process');

const SRC = fs.readFileSync(path.join(__dirname, '..', 'app', 'web', 'client.js'), 'utf8').replace(/\r\n/g, '\n');
const CHROME = [process.env.CHROME_PATH, 'C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser'].find((p) => p && fs.existsSync(p));
const PALETTES = {
  ttm: { primary_color: '#d4b02a', secondary_color: '#3b2f0b', background_color: '#121110', text_color: '#f5f1e6' },
  clara: { primary_color: '#2563eb', secondary_color: '#93c5fd', background_color: '#f8fafc', text_color: '#0f172a' },
  neon: { primary_color: '#f20b6d', secondary_color: '#7c3aed', background_color: '#0b0614', text_color: '#ffffff' },
};
const MODS = ['orders', 'qr', 'stock', 'inventory', 'loyalty', 'hospitality', 'workforce', 'sales', 'bots', 'carta', 'domicilios_whatsapp', 'assistant_ai'];
const TITLES = { orders: ['Pedidos', 'creacion, seguimiento y estados', 'ORD'], qr: ['QR de mesas', 'accesos por mesa', 'QR'], stock: ['Stock', 'existencias y alertas', 'STO'],
  assistant_ai: ['Asistente CLONEXA', 'chat operativo y automatizaciones', 'AI'] };

function load() {
  const start = SRC.indexOf('  /* CLONEXA_078A_OWNER_HOME_START'), end = SRC.indexOf('  /* CLONEXA_078A_OWNER_HOME_END */');
  assert.ok(start > 0 && end > start, 'bloque 078A');
  const css = [];
  const h = (v) => String(v ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  const ctx = vm.createContext({
    state: { companyId: 'c1' }, h, API: '/api/v1',
    document: { addEventListener() {}, getElementById: () => null, createElement: () => ({ set textContent(v) { css.push(v); } }), head: { appendChild() {} } },
    logo: (c) => `<span>${h((c.name || 'C').slice(0, 1))}</span>`,
    renderClientHeroKpis: () => [['Mesas activas', '0', 'abre a las 18:00'], ['Sin stock', '7', '0 con stock bajo · ver cuáles'], ['Pedidos pendientes', '0', 'sin mesas pendientes'], ['Total abierto', '$ 0', 'cuentas abiertas']]
      .map(([l, v, d], i) => `<div class="client-kpi${i === 1 ? ' danger' : ''}" data-client-kpi-label="${l}"><span>${l}</span><strong>${v}</strong><small>${d}</small></div>`).join(''),
    renderClientHeroActions: () => '', cxHspDashboardPendingBanner030D: () => '', cxSanDashboardBanner048K: () => '', cxSessDashboardBanner048Q: () => '', cxCarDashboardBanner048T: () => '',
  });
  vm.runInContext(SRC.slice(start, end) + `\nthis.out = {cxOpHomeHtml078A, cxOpPalette078A, cxOpContrast078A, cxOpChip078A, cxOpStyles078A, cxOpInfo078A};`, ctx);
  ctx.out.cxOpStyles078A();
  return { ...ctx.out, css: css.join('\n'), ctx };
}
function modules(n) {
  return MODS.slice(0, n).map((code) => { const t = TITLES[code] || [code.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase()), 'servicio activo con una descripción corta', code.slice(0, 3).toUpperCase()];
    return { code, title: t[0], subtitle: t[1], badge: t[2] }; });
}
function page(L, { pal, n, live }) {
  L.ctx.state.companyId = 'c1';
  L.cxOpInfo078A.c1 = live ? { classic: false, live3d: { noun: 'bar', template: 'bar' } } : { classic: false, live3d: null };
  const html = L.cxOpHomeHtml078A({ company: { name: '"The Time Machine"' }, b: PALETTES[pal], modules: modules(n), hasHospitalityDashboard: true,
    hospitalityMetrics: { pendingOrders: 0, qrTables: 10, outOfStock: 7 } });
  return html;
}

test('las tarjetas abren la pantalla de siempre y las cifras son las mismas del panel', () => {
  const L = load();
  const html = page(L, { pal: 'ttm', n: 12, live: true });
  for (const code of MODS) assert.ok(html.includes(`data-client-module="${code}"`), code);
  assert.ok(html.includes('id="clientDashboardRoot030D"') && html.includes('class="client-hero'), 'los monitores de siempre siguen encontrando el panel');
  assert.ok(html.includes('data-hsp-toggle-visual-alerts') && html.includes('data-hsp-toggle-sound-alerts'), 'Alertas con los interruptores de siempre');
  assert.ok(html.includes('Sistema operativo empresarial') && html.includes('● LIVE') && html.includes('data-cxop-account-078a'));
  assert.ok(!html.includes('client-sidebar') && !html.includes('Tenant activo') && !/<aside/.test(html), 'sin barra lateral ni UUID');
  assert.ok(html.includes('Ver mi bar en vivo') && html.includes('● EN VIVO') && html.includes('Abrir'));
  assert.ok(html.includes('10 mesas') && html.includes('0 abiertos') && /is-bad[^>]*>7 sin stock/.test(html), 'datos vivos en la esquina');
  assert.ok(html.indexOf('cxop-live-078a') < html.indexOf('data-client-module='), '3D primero');
  assert.ok(html.lastIndexOf('data-client-module="assistant_ai"') > html.lastIndexOf('data-client-module="domicilios_whatsapp"'), 'el Asistente al final y a lo ancho');
  const without = page(L, { pal: 'ttm', n: 3, live: false });
  assert.ok(!without.includes('cxop-live-078a') && !without.includes('Ver mi'), 'sin el módulo no aparece');
});

test('marca: colores de cada paleta con contraste AA (texto, atenuado, acento, alerta e IA)', () => {
  const L = load();
  for (const [name, b] of Object.entries(PALETTES)) {
    const p = L.cxOpPalette078A(b);
    const c = L.cxOpContrast078A;
    assert.ok(c(p.text, p.card) >= 4.5, `${name}: texto`);
    assert.ok(c(p.muted, p.card) >= 4.5, `${name}: texto atenuado`);
    assert.ok(c(p.onAccent, p.accent) >= 4.5, `${name}: texto sobre el acento`);
    assert.ok(c(p.accentText, p.card) >= 4.5, `${name}: acento como texto`);
    assert.ok(c(p.dangerText, p.danger) >= 4.5, `${name}: alerta en rojo`);
    assert.ok(c(p.aiText, p.ai) >= 4.5, `${name}: Asistente`);
    assert.equal(p.accent, b.primary_color, `${name}: usa el color de la marca`);
  }
  const malo = L.cxOpPalette078A({ primary_color: '#777777', background_color: '#808080', text_color: '#888888' });
  assert.ok(L.cxOpContrast078A(malo.text, malo.card) >= 4.5, 'marca con poco contraste: se corrige el texto');
});

function serve(L) {
  const cases = [];
  for (const pal of Object.keys(PALETTES)) for (const n of [3, 12]) for (const live of [true, false]) cases.push({ pal, n, live });
  const doc = (c) => `<!doctype html><html><head><meta charset="utf-8"><style>body{margin:0;font-family:Arial,sans-serif}${L.css}</style></head><body>${page(L, c)}
    <pre id="layout"></pre><script>
      const grid = document.querySelector('[data-cxop-grid-078a]'); const cards = [...grid.children];
      const lefts = new Set(cards.filter(x => !x.classList.contains('cxop-live-078a') && !x.classList.contains('cxop-ai-078a')).map(x => Math.round(x.getBoundingClientRect().left)));
      const live = document.querySelector('.cxop-live-078a'); const r = live && live.getBoundingClientRect();
      const first = cards.map(x => x.getBoundingClientRect()).sort((a, b) => a.top - b.top || a.left - b.left)[0];
      const over = [...document.querySelectorAll('.cxop-card-078a strong, .cxop-card-078a small, .client-kpi strong, .client-kpi small, .cxop-name-078a')].filter(e => e.scrollWidth > e.clientWidth + 1).length;
      const mod = cards.find(x => x.matches('[data-client-module]:not(.cxop-ai-078a)'));
      document.getElementById('layout').textContent = JSON.stringify({cols: lefts.size, pageOver: document.documentElement.scrollWidth > innerWidth + 1, over,
        liveFirst: live ? (Math.round(r.top) === Math.round(first.top) && Math.round(r.left) === Math.round(first.left)) : null,
        liveRatio: live ? +(r.width / mod.getBoundingClientRect().width).toFixed(2) : null, liveTall: live ? +(r.height / mod.getBoundingClientRect().height).toFixed(2) : null});
    </script></body></html>`;
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const m = /^\/case\/(\d+)$/.exec(url.pathname);
    if (m) { res.writeHead(200, { 'content-type': 'text/html' }); return res.end(doc(cases[Number(m[1])])); }
    if (url.pathname === '/frames.html') {
      const frames = []; cases.forEach((c, i) => [390, 768, 1440].forEach((w) => frames.push(`<iframe data-k="${i}|${w}" style="width:${w}px;height:1300px;border:0;display:block" src="/case/${i}"></iframe>`)));
      res.writeHead(200, { 'content-type': 'text/html' });
      return res.end(`<!doctype html><html><body style="margin:0">${frames.join('')}<pre id="all"></pre><script>setTimeout(() => { const out = {};
        document.querySelectorAll('iframe').forEach(f => { const d = f.contentDocument && f.contentDocument.getElementById('layout'); out[f.dataset.k] = d && d.textContent ? JSON.parse(d.textContent) : null; });
        document.getElementById('all').textContent = JSON.stringify(out); }, 4000);</script></body></html>`);
    }
    res.writeHead(404); res.end();
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve({ server, cases })));
}

test('responsive con 3 paletas, con y sin 3D, con 3 y 12 módulos, en 390, 768 y 1440 px', { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 200000 }, async () => {
  const L = load();
  const { server, cases } = await serve(L);
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-op078a-'));
  try {
    const html = await new Promise((resolve, reject) => execFile(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', `--user-data-dir=${profile}`, '--window-size=1500,1400',
      '--virtual-time-budget=10000', '--dump-dom', `http://127.0.0.1:${server.address().port}/frames.html`], { timeout: 150000, maxBuffer: 64 * 1024 * 1024 }, (e, out) => (e ? reject(e) : resolve(out))));
    const m = html.match(/<pre id="all">([^<]*)<\/pre>/);
    assert.ok(m && m[1], 'sin medición');
    const all = JSON.parse(m[1].replace(/&quot;/g, '"'));
    cases.forEach((c, i) => {
      for (const w of [390, 768, 1440]) {
        const r = all[`${i}|${w}`]; const k = `${c.pal} ${c.n} módulos ${c.live ? 'con' : 'sin'} 3D a ${w}px`;
        assert.ok(r, `${k}: sin medición`);
        assert.equal(r.pageOver, false, `${k}: la página no se sale de ancho`);
        assert.equal(r.over, 0, `${k}: ningún texto desborda`);
        if (w !== 1440 || c.n === 12) assert.equal(r.cols, w === 390 ? 1 : w === 768 ? 2 : 4, `${k}: columnas`);
        if (c.live) {
          assert.equal(r.liveFirst, true, `${k}: "Ver mi negocio en vivo" primero`);
          if (w === 1440) assert.ok(r.liveRatio > 1.9 && r.liveTall > 1.9, `${k}: grande 2x2 (${r.liveRatio} x ${r.liveTall})`);
        }
      }
    });
  } finally {
    server.close();
    fs.rmSync(profile, { recursive: true, force: true });
  }
});
