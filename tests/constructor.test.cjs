// Modo constructor (fase 1): reglas puras del editor (ajuste 10 cm, deshacer/rehacer, cruces, puertas tapadas,
// conexiones únicas, alinear, duplicar, catálogo), reglas puras del motor 3D (paredes con aberturas, asientos de mesas
// conectadas, pantallas), cada forma del catálogo tiene su objeto por código, y en Chrome de verdad: el MISMO plano de
// 150 objetos se dibuja en Humano y en Caricatura sin errores y sin mover nada (y el tiempo por cuadro). Sin capturas.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const http = require('node:http');
const path = require('node:path');
const vm = require('node:vm');
const { spawn } = require('node:child_process');
const { pathToFileURL } = require('node:url');

const ROOT = path.resolve(__dirname, '..');
const OF = path.join(ROOT, 'app', 'web', 'oficina');
const CAT = JSON.parse(fs.readFileSync(path.join(ROOT, 'app', 'services', 'constructor_catalogo.json'), 'utf8')).items;
const loadR = () => import(pathToFileURL(path.join(OF, 'constructor_reglas.js')).href);
const CHROME = [process.env.CHROME_PATH, 'C:/Program Files/Google/Chrome/Application/chrome.exe', '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser']
  .find((p) => p && fs.existsSync(p));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const plain = (x) => JSON.parse(JSON.stringify(x));   // valores del contexto vm (otro realm)

function pureOf(file, start, end, extra = {}) {
  const src = fs.readFileSync(path.join(OF, file), 'utf8');
  const body = src.slice(src.indexOf(start), src.indexOf(end)).replace(/^export /gm, '');
  const names = [...body.matchAll(/^(?:function|const)\s+([A-Za-z_]\w*)/gm)].map((m) => m[1]);
  const ctx = vm.createContext({ Math, Number, String, JSON, Array, Set, ...extra });
  vm.runInContext(body + `\n;globalThis.__out = {${names.join(',')}};`, ctx);
  return ctx.__out;
}
const objRules = () => pureOf('plano_objetos.js', '// ------------------------------------------------------------------ reglas puras', '// ------------------------------------------------------------------ materiales');
const engRules = (O) => pureOf('oficina_plano.js', '// ===== reglas puras', '// ===== fin reglas puras', { O });

function plan() {
  return { formato: 'clonexa.plano', version_esquema: 1, sala: { ancho: 10, fondo: 8, alto: 3 },
    paredes: [{ id: 'w1', x1: 0, z1: 8, x2: 10, z2: 8, grosor: 0.15, alto: 3, color: '#ffffff', material: 'pintura' }],
    aberturas: [{ id: 'a1', pared: 'w1', tipo: 'puerta', pos: 5, ancho: 1, alto: 2.1, base: 0 }], pisos: [], zonas: [],
    objetos: [{ id: 'o1', asset: 'mesa_redonda_4', x: 2, z: 2, rot: 0, escala: 1, color: null, capa: 'muebles', conexion: { tipo: 'mesa', id: 'Mesa 1' } },
      { id: 'o2', asset: 'mesa_redonda_4', x: 2.5, z: 2.2, rot: 0, escala: 1, color: null, capa: 'muebles', conexion: null },
      { id: 'o3', asset: 'sofa', x: 5, z: 7.6, rot: 0, escala: 1, color: null, capa: 'muebles', conexion: null }] };
}
const SIZES = { mesa_redonda_4: { w: 1.9, d: 1.9, conectable: 'mesa' }, sofa: { w: 2, d: 0.85 } };

test('ajuste a 10 cm (Alt libre), deshacer y rehacer', async () => {
  const R = await loadR();
  assert.equal(R.snap(1.234), 1.2); assert.equal(R.snap(1.26), 1.3); assert.equal(R.snap(1.234, true), 1.234);
  const h = new R.History(); const p = plan(); h.push(p); const p2 = R.clone(p); p2.objetos[0].x = 9;
  const back = h.undo(p2); assert.equal(back.objetos[0].x, 2); assert.ok(h.canRedo);
  assert.equal(h.redo(back).objetos[0].x, 9); assert.ok(!h.canRedo);
});

test('avisos iguales al servidor: cruces, puerta tapada, sin conectar y mesas reales sin objeto', async () => {
  const R = await loadR();
  const w = R.warnings(plan(), SIZES, { mesa: [{ id: 'Mesa 1', label: 'Mesa 1' }, { id: 'Mesa 2', label: 'Mesa 2' }] });
  assert.deepEqual(w.cruces, [['o1', 'o2']]);
  assert.deepEqual(w.puertas, [['o3', 'a1']]);
  assert.deepEqual(w.sin_conectar, ['o2']);
  assert.deepEqual(w.mesas_sin_objeto, ['Mesa 2']);
});

test('una entidad real se conecta a un solo objeto; duplicar no copia la conexión', async () => {
  const R = await loadR(); const p = plan();
  assert.equal(R.connect(p, 'o2', 'mesa', 'Mesa 1').ok, false, 'Mesa 1 ya está en o1');
  assert.deepEqual(R.freeEntities(p, { mesa: [{ id: 'Mesa 1' }, { id: 'Mesa 2' }] }, 'mesa', 'o2').map((e) => e.id), ['Mesa 2']);
  assert.ok(R.connect(p, 'o2', 'mesa', 'Mesa 2').ok);
  const [id] = R.duplicate(p, ['o1']); const c = p.objetos.find((o) => o.id === id);
  assert.equal(c.conexion, null); assert.equal(c.x, 2.5);
  assert.equal(R.badge({ tipo: 'mesa', id: 'Mesa 12' }), '12');
});

test('alinear, girar, mover, borrar y puertas pegadas a la pared', async () => {
  const R = await loadR(); const p = plan();
  R.align(p, ['o1', 'o2', 'o3'], 'top'); assert.deepEqual(p.objetos.map((o) => o.z), [2, 2, 2]);
  R.align(p, ['o1', 'o2', 'o3'], 'spreadx'); assert.deepEqual(p.objetos.map((o) => o.x), [2, 3.5, 5]);
  R.rotate(p, ['o1'], -45); assert.equal(p.objetos[0].rot, 315);
  const a = R.addOpening(p, 9.8, 7.7, 'ventana', [1.2, 1.2, 0.9]); assert.ok(a); assert.equal(a.pared, 'w1'); assert.ok(a.pos <= 10 - 0.6, 'la ventana queda dentro de su pared');
  assert.equal(R.addOpening(p, 5, 3, 'puerta', [0.9, 2.1, 0]), null, 'lejos de una pared no se pega');
  R.remove(p, ['w1']); assert.equal(p.aberturas.length, 0, 'sin pared no quedan sus aberturas');
});

test('catálogo: 120+ objetos, cada forma tiene su objeto por código, variantes de color y búsqueda sin tildes', async () => {
  const R = await loadR();
  assert.ok(CAT.length >= 120);
  const src = fs.readFileSync(path.join(OF, 'plano_objetos.js'), 'utf8');
  for (const it of CAT) {
    if (it.f === 'glb') { assert.ok(fs.existsSync(path.join(OF, 'recursos', it.a)), it.id); continue; }
    assert.match(src, new RegExp(`\\n\\s+${it.f}: \\(`), `forma ${it.f} (${it.id})`);
    assert.ok((it.v || []).length >= 1, `${it.id} con variantes`);
  }
  const items = CAT.map((x) => ({ id: x.id, nombre: x.n, categoria: x.c, zonas: x.z, variantes: x.v }));
  assert.ok(R.filterCatalog(items, { q: 'neon' }).some((x) => x.id === 'neon'), 'neón sin tilde');
  assert.ok(R.filterCatalog(items, { zone: 'cocina' }).every((x) => x.zonas.includes('cocina')));
  assert.deepEqual(R.swatches({ variantes: ['#111111'] }, { primary: '#F20B6D', secondary: 'x' }), ['#111111', '#f20b6d'], 'paleta del Estudio de marca');
});

test('motor del plano: paredes con aberturas, asientos y pantallas vivas', () => {
  const O = objRules();
  assert.equal(O.shade('#808080', 0.5), '#404040'); assert.equal(O.hexOf('nope', '#000000'), '#000000');
  assert.deepEqual(plain(O.toScene(1, 2, { ancho: 10, fondo: 8 })), [-4, -2]);
  assert.equal(O.instKey({ asset: 'silla', color: '#ABCDEF' }, {}), 'silla|#abcdef||', 'mismo modelo+color se dibuja junto (instancias)');
  const E = engRules(O);
  const pieces = E.wallPieces(10, 3, [{ pos: 5, ancho: 2, base: 0, alto: 2.2 }, { pos: 8, ancho: 1, base: 1, alto: 1 }]);
  assert.deepEqual(plain(pieces.map((p) => [p.a, p.b, p.y0, p.y1].map((v) => Math.round(v * 10) / 10))),
    [[0, 4, 0, 3], [4, 6, 2.2, 3], [6, 7.5, 0, 3], [7.5, 8.5, 0, 1], [7.5, 8.5, 2, 3], [8.5, 10, 0, 3]]);
  const seats = E.tableSeats({ x: 5, z: 4, rot: 0 }, { ancho: 10, fondo: 8 }, { forma: 'table_six' });
  assert.equal(seats.length, 6);
  assert.deepEqual(plain(E.outward({ x1: 0, z1: 0, x2: 10, z2: 0 }, { ancho: 10, fondo: 8 })), [0, -1], 'la pared de arriba mira hacia afuera');
  assert.equal(E.screenModel('canciones', { songs: [{ title: 'La Bicicleta' }] }).rows[0], 'La Bicicleta');
  assert.equal(E.screenModel('comandas', { kitchen: [] }).empty, 'Sin comandas');
  assert.ok(E.screenModel('logo', {}).logo);
  assert.deepEqual(E.staffPeople({ people: [{ key: 'a', status: 'paused' }] })[0].paused, true);
});

test('páginas del constructor: CSP con importmap, sin scripts en línea y solo rutas con sesión', () => {
  for (const f of ['constructor.html', 'constructor_vista.html', 'biblioteca.html']) {
    const html = fs.readFileSync(path.join(OF, f), 'utf8');
    const inline = [...html.matchAll(/<script(?![^>]*src=)[^>]*>/g)].map((m) => m[0]);
    assert.deepEqual(inline, ['<script type="importmap">'], f);
    for (const m of html.matchAll(/(?:src|href)="(\/admin-v2plus\/oficina\/[^"]+)"/g)) assert.ok(!m[1].includes('..'), m[1]);
  }
  const routes = fs.readFileSync(path.join(ROOT, 'app', 'web', 'oficina_routes.py'), 'utf8');
  for (const n of ['plano.js', 'plano_objetos.js', 'constructor.js', 'constructor_reglas.js', 'constructor_vista.js', 'biblioteca.js', 'constructor.css']) assert.ok(routes.includes(`"${n}"`), n);
});

// ------------------------------------------------------------------ Chrome de verdad: mismo plano, dos estilos
function payload(style) {
  const items = CAT.map((x) => ({ id: x.id, nombre: x.n, categoria: x.c, zonas: x.z, forma: x.f, medidas: { w: x.s[0], d: x.s[1], h: x.s[2] }, variantes: x.v || [], conectable: x.k || null,
    capa: x.l || 'muebles', url: x.f === 'glb' ? `/admin-v2plus/oficina/recursos/${x.a}` : undefined }));
  const pool = items.filter((x) => x.capa === 'muebles');
  const objetos = []; for (let i = 0; i < 150; i++) { const it = pool[(i * 7) % pool.length];
    objetos.push({ id: 'o' + i, asset: it.id, x: 1.5 + (i % 15) * 1.8, z: 1.5 + Math.floor(i / 15) * 1.6, rot: (i % 4) * 90, escala: 1, color: null, variante: null, capa: 'muebles',
      conexion: it.conectable === 'mesa' ? { tipo: 'mesa', id: 'Mesa ' + i } : null, texto: null }); }
  const sala = { ancho: 30, fondo: 18, alto: 3.2 };
  const paredes = [[0, 0, 30, 0], [30, 0, 30, 18], [30, 18, 0, 18], [0, 18, 0, 0]].map(([a, b, c, d], i) => ({ id: 'w' + i, x1: a, z1: b, x2: c, z2: d, grosor: 0.15, alto: 3.2, color: '#9a3b2e', material: i ? 'pintura' : 'ladrillo' }));
  return { ok: true, version: 1, estilo: style, name: 'Prueba', brand: { primary: '#f20b6d' }, catalogo: items.filter((x) => objetos.some((o) => o.asset === x.id)),
    plano: { formato: 'clonexa.plano', version_esquema: 1, sala, paredes, aberturas: [{ id: 'a1', pared: 'w2', tipo: 'puerta_doble', pos: 15, ancho: 1.6, alto: 2.2, base: 0 }],
      pisos: [{ id: 'p1', zona: null, puntos: [[0, 0], [30, 0], [30, 18], [0, 18]], material: 'ajedrez', color: '#f4efe6' }], zonas: [], objetos } };
}
const ASSET = { 'mixamo.js': 'oficina_mixamo.js', 'pisos_reglas.js': 'oficina_pisos_rules.js', 'bar_reglas.js': 'oficina_bar_rules.js', 'gestos.js': 'oficina_gestos.js',
  'arquitecto.js': 'oficina_arquitecto.js', 'plano.js': 'oficina_plano.js', 'plano_objetos.js': 'plano_objetos.js', 'constructor_vista.js': 'constructor_vista.js', 'app.css': 'oficina.css', 'constructor.css': 'constructor.css' };
function serve(style) {
  const server = http.createServer((req, res) => {
    const u = new URL(req.url, 'http://x'); const p = u.pathname; const send = (code, body, type) => { res.writeHead(code, { 'content-type': type }); res.end(body); };
    if (p === '/admin-v2plus/constructor/vista') return send(200, fs.readFileSync(path.join(OF, 'constructor_vista.html')), 'text/html');
    if (p.startsWith('/admin-v2plus/oficina/vendor/three/')) return send(200, fs.readFileSync(path.join(ROOT, 'app/web/vendor/three-0.160.0', p.split('/vendor/three/')[1])), 'application/javascript');
    if (p === '/admin-v2plus/oficina/recursos/manifest.json') return send(200, fs.readFileSync(path.join(OF, 'recursos', 'manifest.json')), 'application/json');
    if (p.startsWith('/admin-v2plus/oficina/recursos/')) return send(200, fs.readFileSync(path.join(OF, 'recursos', p.split('/recursos/')[1])), 'application/octet-stream');
    const name = p.split('/admin-v2plus/oficina/')[1];
    if (name && ASSET[name]) return send(200, fs.readFileSync(path.join(OF, ASSET[name])), name.endsWith('.css') ? 'text/css' : 'application/javascript');
    if (/\/plano$/.test(p)) return send(200, JSON.stringify(payload(style)), 'application/json');
    if (/\/vivo$/.test(p)) return send(200, JSON.stringify({ ok: true, rev: 'r', tables: [{ label: 'Mesa 0', open: true, guests: 2 }], staff: { people: [] } }), 'application/json');
    send(404, '{}', 'application/json');
  });
  return new Promise((r) => server.listen(0, '127.0.0.1', () => r(server)));
}
async function launch() {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-constructor-'));
  const proc = spawn(CHROME, ['--headless=new', '--enable-unsafe-swiftshader', '--no-first-run', '--remote-debugging-port=0', `--user-data-dir=${profile}`, '--window-size=1280,720', 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
  const wsUrl = await new Promise((resolve, reject) => { let b = ''; const t = setTimeout(() => reject(new Error('Chrome no abrió DevTools')), 30000);
    proc.stderr.on('data', (d) => { b += d; const m = b.match(/DevTools listening on (ws:\/\/\S+)/); if (m) { clearTimeout(t); resolve(m[1]); } }); });
  const list = await (await fetch(`http://127.0.0.1:${new URL(wsUrl).port}/json/list`)).json();
  const ws = new WebSocket(list.find((t) => t.type === 'page').webSocketDebuggerUrl); await new Promise((r) => { ws.onopen = r; });
  let id = 0; const pend = new Map(); const errors = [];
  ws.onmessage = (ev) => { const m = JSON.parse(ev.data); if (m.id && pend.has(m.id)) { const p = pend.get(m.id); pend.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); }
    if (m.method === 'Runtime.exceptionThrown') errors.push(JSON.stringify(m.params.exceptionDetails).slice(0, 300));
    if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') errors.push(m.params.args.map((a) => a.value || a.description).join(' ').slice(0, 300)); };
  const send = (method, params = {}) => new Promise((res, rej) => { id++; pend.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
  return { send, errors, close: () => { try { ws.close(); } catch (_) {} proc.kill(); try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {} } };
}

test('Chrome: el mismo plano de 150 objetos en Humano y en Caricatura, sin errores y sin mover nada',
  { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 240000 }, async () => {
    const out = {};
    for (const style of ['humano', 'caricatura']) {
      const server = await serve(style); const cdp = await launch();
      try {
        await cdp.send('Runtime.enable'); await cdp.send('Page.enable');
        await cdp.send('Page.navigate', { url: `http://127.0.0.1:${server.address().port}/admin-v2plus/constructor/vista?empresa=21a3065e-38ee-4fc3-96ed-ae1707a3b8e4` });
        let r = null;
        for (let i = 0; i < 90; i++) { await sleep(1000); r = (await cdp.send('Runtime.evaluate', { expression: 'window.__cxVista ? JSON.stringify({s: window.__cxVista.stats, b: window.__cxVista.bench(20), msg: document.getElementById("cxvMsg").textContent}) : null', returnByValue: true })).result.value; if (r) break; }
        assert.ok(r, 'la vista 3D abrió'); out[style] = JSON.parse(r);
        assert.deepEqual(cdp.errors.filter((e) => !/bar\/manifest|404/.test(e)), [], `${style} sin errores`);
        assert.equal(out[style].msg, '');
      } finally { cdp.close(); server.close(); }
    }
    assert.equal(out.humano.s.objects, 150); assert.equal(out.caricatura.s.objects, 150);
    assert.equal(out.humano.s.instanced, out.caricatura.s.instanced, 'mismas instancias en los dos estilos');
    assert.ok(out.caricatura.s.drawGroups > out.humano.s.drawGroups, 'caricatura agrega el contorno');
    console.log(`ms por cuadro (software, sin GPU): humano ${out.humano.b.ms}, caricatura ${out.caricatura.b.ms}`);
  });
