// Arnés de la Biblioteca 3D: sirve las pantallas reales (app/web/oficina/b3d) con la API /admin-v2/api/b3d SIMULADA en
// memoria (sin base de datos ni sesión) y abre Chrome headless por DevTools. Lo usan tests/b3d.test.cjs y las mediciones
// locales. Mixamo: solo si MIXAMO_DIR apunta a una copia local (nunca está en el repo); si no, Humano cae a Caricatura.
const fs = require('node:fs');
const os = require('node:os');
const http = require('node:http');
const path = require('node:path');
const { spawn } = require('node:child_process');

const ROOT = path.resolve(__dirname, '..');
const OF = path.join(ROOT, 'app', 'web', 'oficina');
const B3D = path.join(OF, 'b3d');
const CHROME = [process.env.CHROME_PATH, 'C:/Program Files/Google/Chrome/Application/chrome.exe', '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser']
  .find((p) => p && fs.existsSync(p));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const hex = (n) => n.toString(16).padStart(12, '0');

function freshState() {
  const team = [['Laura M.', 'Cajera', 'Caja'], ['Andrés P.', 'Barman', 'Barra'], ['Sofía R.', 'Anfitriona', 'Salón'], ['Julián C.', 'Chef', 'Cocina'],
    ['Mateo G.', 'Mantenimiento', 'Bodega'], ['Valentina T.', 'Mesera', 'Salón']].map(([name, role, area], i) => ({ id: hex(0xa1 + i), name, role, area, shift: 'Sin turno abierto', custom: false, toon: {}, human: {}, uniform: null, real: true }));
  const ent = {
    mesa: Array.from({ length: 12 }, (_, i) => ({ id: `mesa:Mesa ${i + 1}`, label: `Mesa ${i + 1}` })),
    puesto: Array.from({ length: 15 }, (_, i) => ({ id: `puesto:${i + 1}`, label: `Puesto ${i + 1}` })),
    escritorio: team.map((p) => ({ id: 'emp:' + p.id, label: p.name })),
    caja: [{ id: 'caja:caja-1', label: 'Caja principal' }, { id: 'caja:caja-2', label: 'Caja 2' }],
    pantalla: ['canciones', 'comandas', 'domicilios', 'produccion', 'turno', 'logo'].map((k) => ({ id: 'pantalla:' + k, label: 'Pantalla · ' + k })),
    inventario: [{ id: 'inv:Cervezas', label: 'Inventario · Cervezas' }], sonido: [{ id: 'sonido:canciones', label: 'Canciones pedidas' }],
  };
  const uniforms = [
    { id: 'u-barra', name: 'Barra', desc: 'Camisa negra + delantal', toon: { top: 'camiseta', topColor: '#18181b', bottom: 'pantalon', bottomColor: '#4b5563', complete: 'ninguno', acc: { delantal: true }, accColor: '#f20b6d' }, human: { topColor: '#111111', topStyle: 'liso', bottomColor: '#1f1f24' } },
    { id: 'u-caja', name: 'Caja', desc: 'Chaqueta + jean', toon: { top: 'chaqueta', topColor: '#d59f2a', innerColor: '#ffffff', bottom: 'jean', bottomColor: '#2c4a7c', complete: 'ninguno' }, human: { topColor: '#d59f2a', topStyle: 'liso', bottomColor: '#2c4a7c' } },
    { id: 'u-cocina', name: 'Cocina', desc: 'Chaqueta de chef + gorro', toon: { top: 'chef', bottom: 'pantalon', bottomColor: '#1f2937', complete: 'ninguno', acc: { gorro_chef: true } }, human: { topColor: '#ffffff', topStyle: 'liso', bottomColor: '#1f2937' } },
    { id: 'u-salon', name: 'Salón', desc: 'Buzo de la marca', toon: { top: 'buzo', topColor: '#7c3aed', bottom: 'pantalon', bottomColor: '#111827', complete: 'ninguno' }, human: { topColor: '#7c3aed', topStyle: 'liso', bottomColor: '#111827' } },
  ];
  return { style: 'human', designs: [], versions: {}, team, uniforms, entities: ent, areas: ['Barra', 'Salón', 'Cocina', 'Caja', 'Bodega', 'Oficina'], catalog: [], review: [] };
}
const COMPANIES = [{ id: '11111111-1111-4111-8111-111111111111', name: 'Night Bar (demo)', kind: 'bar', brand: ['#f20b6d', '#7c3aed', '#111111', '#ffffff'], neon: 'Night Bar' },
  { id: '22222222-2222-4222-8222-222222222222', name: 'Call center demo', kind: 'callcenter', brand: ['#0ea5e9', '#22c55e', '#0b1220', '#f0f9ff'], neon: 'Contacto' }];

function serve(opts = {}) {
  const states = new Map(COMPANIES.map((c) => [c.id, freshState()]));
  const log = [];
  const server = http.createServer(async (req, res) => {
    const u = new URL(req.url, 'http://x'); const p = decodeURIComponent(u.pathname);
    const send = (code, body, type = 'application/json') => { res.writeHead(code, { 'content-type': type, 'cache-control': 'no-store' }); res.end(typeof body === 'string' || Buffer.isBuffer(body) ? body : JSON.stringify(body)); };
    const body = await new Promise((r) => { let b = []; req.on('data', (d) => b.push(d)); req.on('end', () => r(Buffer.concat(b).toString('utf8'))); });
    const file = (f, type) => fs.existsSync(f) ? send(200, fs.readFileSync(f), type) : send(404, '{}');
    if (p === '/admin-v2plus/biblioteca3d') { res.writeHead(303, { location: '/admin-v2plus/biblioteca3d/' + u.search }); return res.end(); }
    if (p === '/admin-v2plus/biblioteca3d/') return file(path.join(B3D, 'index.html'), 'text/html');
    if (p === '/admin-v2plus/biblioteca3d/constructor') return file(path.join(B3D, 'constructor.html'), 'text/html');
    if (p === '/admin-v2plus/biblioteca3d/personajes') return file(path.join(B3D, 'personajes.html'), 'text/html');
    if (p.startsWith('/admin-v2plus/oficina/b3d/')) { const n = p.split('/b3d/')[1]; return file(path.join(B3D, path.basename(n)), n.endsWith('.css') ? 'text/css' : 'application/javascript'); }
    if (p === '/admin-v2plus/oficina/logo-nombre.png') return file(path.join(OF, 'logo-nombre.png'), 'image/png');
    if (p.startsWith('/admin-v2plus/oficina/vendor/three/')) return file(path.join(ROOT, 'app/web/vendor/three-0.160.0', p.split('/vendor/three/')[1]), 'application/javascript');
    if (p.startsWith('/admin-v2plus/oficina/bar/')) return opts.mixamo ? file(path.join(opts.mixamo, p.split('/bar/')[1]), 'model/gltf-binary') : send(404, '{}');
    if (!p.startsWith('/admin-v2/api/b3d/')) return send(404, '{}');
    const rest = p.slice('/admin-v2/api/b3d'.length); const json = body ? (() => { try { return JSON.parse(body); } catch (e) { return null; } })() : null;
    log.push({ method: req.method, path: rest, json });
    if (rest === '/empresas') return send(200, { ok: true, items: COMPANIES });
    const m = rest.match(/^\/empresas\/([^/]+)(.*)$/); const st = m && states.get(m[1]);
    if (!st) return send(404, { detail: 'Empresa no encontrada' });
    const r = m[2];
    if (r === '' && req.method === 'GET') return send(200, { ok: true, company: COMPANIES.find((c) => c.id === m[1]), ...JSON.parse(JSON.stringify({ ...st, versions: undefined })) });
    if (r === '/estilo') { st.style = json.style; return send(200, { ok: true, style: st.style }); }
    let d = r.match(/^\/disenos\/([^/]+)(.*)$/);
    if (d) {
      const [, id, sub] = d; let des = st.designs.find((x) => x.id === id);
      if (sub === '' && req.method === 'PUT') { if (!des) { des = { id, version: 0, live: false }; st.designs.push(des); } Object.assign(des, { name: json.name, plan: json.plan, updated: Date.now() }); return send(200, { ok: true, id, thumb: json.thumb ? '' : undefined }); }
      if (sub === '' && req.method === 'DELETE') { st.designs = st.designs.filter((x) => x.id !== id); return send(des ? 200 : 404, { ok: !!des }); }
      if (!des) return send(404, { detail: 'Diseño no encontrado.' });
      if (sub === '/publicar') { des.version++; st.designs.forEach((x) => { x.live = x === des; }); (st.versions[id] = st.versions[id] || []).unshift({ n: des.version, date: Date.now(), plan: JSON.parse(JSON.stringify(des.plan)) }); return send(200, { ok: true, version: des.version }); }
      if (sub === '/versiones') return send(200, { ok: true, items: (st.versions[id] || []).map(({ n, date }) => ({ n, date })) });
      const v = sub.match(/^\/versiones\/(\d+)$/); if (v) { const x = (st.versions[id] || []).find((y) => y.n === +v[1]); return x ? send(200, { ok: true, plan: x.plan }) : send(404, {}); }
    }
    if (r === '/importar') { const plan = json; if (!plan || !plan.room) return send(422, { detail: 'Ese archivo no es un plano válido de Clonexa' }); plan.people = []; (plan.objects || []).forEach((o) => delete o.conn); return send(200, { ok: true, plan }); }
    d = r.match(/^\/equipo\/([0-9a-f]{12})$/); if (d) { const i = st.team.findIndex((x) => x.id === d[1]); const prev = st.team[i] || { id: d[1], real: false }; st.team[i < 0 ? st.team.length : i] = { ...prev, ...json }; return send(200, { ok: true }); }
    if (r === '/uniformes') { st.uniforms = json.items; return send(200, { ok: true, items: st.uniforms }); }
    if (r === '/aplicar-marca') return send(200, { ok: true, objects: 3, uniforms: st.uniforms.length });
    return send(404, {});
  });
  return new Promise((r) => server.listen(opts.port || 0, '127.0.0.1', () => r({ server, url: `http://127.0.0.1:${server.address().port}`, log, states, companies: COMPANIES })));
}

async function launch({ width = 1440, height = 900, gpu = false } = {}) {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-b3d-'));
  const flags = ['--headless=new', '--no-first-run', '--remote-debugging-port=0', `--user-data-dir=${profile}`, `--window-size=${width},${height}`, '--hide-scrollbars'];
  if (!gpu) flags.push('--enable-unsafe-swiftshader'); else flags.push('--use-angle=d3d11', '--enable-gpu', '--ignore-gpu-blocklist');
  const proc = spawn(CHROME, [...flags, 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
  const wsUrl = await new Promise((resolve, reject) => { let b = ''; const t = setTimeout(() => reject(new Error('Chrome no abrió DevTools')), 30000);
    proc.stderr.on('data', (d) => { b += d; const m = b.match(/DevTools listening on (ws:\/\/\S+)/); if (m) { clearTimeout(t); resolve(m[1]); } }); });
  const list = await (await fetch(`http://127.0.0.1:${new URL(wsUrl).port}/json/list`)).json();
  const ws = new WebSocket(list.find((t) => t.type === 'page').webSocketDebuggerUrl); await new Promise((r) => { ws.onopen = r; });
  let id = 0; const pend = new Map(); const errors = [];
  ws.onmessage = (ev) => { const m = JSON.parse(ev.data); if (m.id && pend.has(m.id)) { const p = pend.get(m.id); pend.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); }
    if (m.method === 'Runtime.exceptionThrown') errors.push(JSON.stringify(m.params.exceptionDetails).slice(0, 400));
    if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') errors.push(m.params.args.map((a) => a.value || a.description).join(' ').slice(0, 400)); };
  const send = (method, params = {}) => new Promise((res, rej) => { id++; pend.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
  await send('Runtime.enable'); await send('Page.enable');
  const evaluate = async (expression) => { const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 400)); return r.result.value; };
  const waitFor = async (expression, secs = 60) => { for (let i = 0; i < secs * 4; i++) { const v = await evaluate(expression).catch(() => null); if (v) return v; await sleep(250); } throw new Error('esperando: ' + expression); };
  const go = async (url) => { await send('Page.navigate', { url }); await sleep(300); };
  const shot = async (file) => { const r = await send('Page.captureScreenshot', { format: 'png' }); fs.writeFileSync(file, Buffer.from(r.data, 'base64')); };
  const close = () => { try { ws.close(); } catch (_) {} proc.kill(); setTimeout(() => { try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {} }, 500); };
  return { send, evaluate, waitFor, go, shot, errors, close };
}

// ------------------------------------------------------------------ visor del cliente (Negocio en vivo 3D) con un plano publicado
const VROOT = '/panel/negocio-en-vivo/r/11111111-1111-4111-8111-111111111111/firma/';
const VFILES = { 'app.css': 'oficina.css', 'vivo3d.css': 'vivo3d.css', 'vivo3d.js': 'vivo3d.js', 'plano.js': 'oficina_plano.js', 'mixamo.js': 'oficina_mixamo.js',
  'pisos_reglas.js': 'oficina_pisos_rules.js', 'bar_reglas.js': 'oficina_bar_rules.js', 'gestos.js': 'oficina_gestos.js', 'arquitecto.js': 'oficina_arquitecto.js' };
const ENGINE = ['core.js', 'catalog.js', 'room.js', 'char.js'];
// plano de n objetos con TODO el catálogo del prototipo (mesas conectadas a QR, personas del plano)
function bigPlan(n = 150) {
  const src = fs.readFileSync(path.join(B3D, 'catalog.js'), 'utf8');
  const ids = [...src.matchAll(/^add\('([a-z_0-9]+)'/gm)].map((m) => m[1]);
  const objects = []; const W = 30, D = 20;
  for (let i = 0; i < n; i++) {
    const item = ids[i % ids.length]; const o = { id: 'o' + i, item, x: -W / 2 + 1.5 + (i % 15) * 1.9, z: -D / 2 + 1.5 + Math.floor(i / 15) * 1.8, rot: (i % 4) * 90 };
    if (/^mesa_(redonda|cuadrada|2|larga|alta)$|^butaca$/.test(item)) o.conn = 'mesa:Mesa ' + (i + 1);
    if (/^(tv_pared|tv_pedestal|tablero)$/.test(item)) { o.screen = 'Canciones pedidas'; }
    if (item === 'neon') o.text = 'Night Bar';
    objects.push(o);
  }
  objects.push({ id: 'desk', item: 'escritorio', x: 13, z: 9, rot: 0, conn: 'emp:' + hex(0xa1) });
  const people = [{ id: 'p1', pid: hex(0xa2), x: 0, z: 9, rot: 180, clip: 'work' }];
  const inner = [{ id: 'm1', x1: -15, z1: 5, x2: -5, z2: 5, kind: 'alto', mat: 'azulejo', color: '#ffffff', door: { pos: .5, width: .9, type: 'puerta' } },
    { id: 'm2', x1: 5, z1: -10, x2: 5, z2: -4, kind: 'vidrio', color: '#bfe6ff', door: null }, { id: 'm3', x1: 8, z1: 6, x2: 12, z2: 6, kind: 'media', h: 1.1, door: { pos: .2, width: 1, type: 'hueco' } }];
  return { name: 'Prueba', room: { w: W, d: D, h: 3.4 }, floor: { mat: 'madera_oscura', color: '#5b3a26' }, walls: { n: { mat: 'ladrillo', color: '#8a4130' }, s: { mat: 'ladrillo', color: '#8a4130' }, e: { mat: 'pintura', color: '#e7e2f0' }, w: { mat: 'ladrillo', color: '#8a4130' } },
    openings: [{ id: 'a1', wall: 's', pos: .5, type: 'puerta_doble' }, { id: 'a2', wall: 'n', pos: .3, type: 'ventanal' }], inner, objects, people };
}
function serveViewer(opts = {}) {
  const style = opts.style || 'humano'; const plan = opts.plan || bigPlan(opts.n || 150);
  const snap = { ok: true, rev: 'r1', tables: [{ label: 'Mesa 11', open: true, guests: 3 }], songs: [{ title: 'Tusa' }],
    staff: { people: [{ key: hex(0xa1), label: 'Laura M. · Cajera', role: 'Cajera', uniform: 'caja', paused: false }, { key: hex(0xa2), label: 'Andrés P. · Barman', role: 'Barman', uniform: 'barman', paused: true }] } };
  const server = http.createServer((req, res) => {
    const u = new URL(req.url, 'http://x'); const p = decodeURIComponent(u.pathname);
    const send = (code, body, type = 'application/json') => { res.writeHead(code, { 'content-type': type }); res.end(typeof body === 'string' || Buffer.isBuffer(body) ? body : JSON.stringify(body)); };
    const file = (f, type) => fs.existsSync(f) ? send(200, fs.readFileSync(f), type) : send(404, '{}');
    if (!p.startsWith(VROOT)) return send(404, '{}');
    const r = p.slice(VROOT.length);
    if (r === '') return send(200, fs.readFileSync(path.join(OF, 'vivo3d.html'), 'utf8').replace(/__ROOT__/g, VROOT), 'text/html');
    if (VFILES[r]) return file(path.join(OF, VFILES[r]), r.endsWith('.css') ? 'text/css' : 'application/javascript');
    if (r.startsWith('b3d/')) return ENGINE.includes(r.slice(4)) ? file(path.join(B3D, r.slice(4)), 'application/javascript') : send(404, '{}');
    if (r.startsWith('vendor/three/')) return file(path.join(ROOT, 'app/web/vendor/three-0.160.0', r.slice(13)), 'application/javascript');
    if (r.startsWith('recursos/')) return file(path.join(OF, 'recursos', r.slice(9)), r.endsWith('.json') ? 'application/json' : 'application/octet-stream');
    if (r.startsWith('bar/')) return opts.mixamo ? file(path.join(opts.mixamo, r.slice(4)), 'model/gltf-binary') : send(404, '{}');
    if (r === 'api/piso') return send(200, { ok: true, floor: { company_id: COMPANIES[0].id, name: 'Night Bar', template: 'bar', plano: 1, estilo_escena: style, brand: { colors: { primary: '#f20b6d' } } }, tv: true, lite: false, noun: 'bar', admin: false, back: '/client' });
    if (r === 'api/personajes') return send(200, { ok: true, items: [] });
    if (/^api\/pisos\/[^/]+\/plano$/.test(r)) return send(200, { ok: true, version: 1, plano: plan, estilo: style, catalogo: [], looks: { [hex(0xa2)]: { toon: { hair: 'afro' }, human: { base: 'Remy', topColor: '#f20b6d' } } } });
    if (/^api\/pisos\/[^/]+\/vivo$/.test(r)) return send(200, u.searchParams.get('rev') === 'r1' ? { ok: true, same: true, rev: 'r1' } : snap);
    if (r === 'api/vista') return send(200, { ok: true });
    return send(404, '{}');
  });
  return new Promise((rs) => server.listen(0, '127.0.0.1', () => rs({ server, url: `http://127.0.0.1:${server.address().port}${VROOT}`, plan })));
}

module.exports = { serve, serveViewer, bigPlan, launch, CHROME, sleep, COMPANIES };
