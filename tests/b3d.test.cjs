// BIBLIOTECA 3D (prototipo aprobado integrado): catálogo igual en el servidor y en el navegador, reglas puras del motor en
// vivo, pantallas seguras para la CSP de la consola, Mixamo nunca en el repo, Humano sin accesorios sueltos, y en Chrome de
// verdad (API simulada, sin capturas): constructor, personajes, inicio y el visor del cliente con un plano de 150 objetos.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const H = require('./_b3d_harness.cjs');

const ROOT = path.resolve(__dirname, '..');
const OF = path.join(ROOT, 'app', 'web', 'oficina');
const B3D = path.join(OF, 'b3d');
const read = (f) => fs.readFileSync(f, 'utf8');
const plain = (x) => JSON.parse(JSON.stringify(x));

test('el catálogo del servidor (constructor_v2.ITEMS) y el del navegador (catalog.js) dicen lo mismo', () => {
  const js = read(path.join(B3D, 'catalog.js'));
  const out = {};
  for (const m of js.matchAll(/^add\('([a-z_0-9]+)', '[^']*', '([a-z]+)', ([\d.]+), ([\d.]+), \[[^\]]*\]/gm)) {
    const next = js.indexOf('\nadd(', m.index + 1); const seg = js.slice(m.index, next < 0 ? js.length : next);
    out[m[1]] = [m[2], +m[3], +m[4], (seg.match(/conn: '([a-z]+)'/) || [])[1] || '', /wall: true/.test(seg) ? 1 : 0, ((seg.match(/props: \[([^\]]*)\]/) || [])[1] || '').replace(/'/g, '')];
  }
  const py = read(path.join(ROOT, 'app', 'services', 'constructor_v2.py'));
  const block = py.slice(py.indexOf('ITEMS: dict[str, tuple]'), py.indexOf(']}', py.indexOf('ITEMS: dict[str, tuple]')));
  const server = {};
  for (const m of block.matchAll(/\["([a-z_0-9]+)", "([a-z]+)", ([\d.]+), ([\d.]+), "([a-z]*)", (\d), "([a-z]*)"\]/g)) server[m[1]] = [m[2], +m[3], +m[4], m[5], +m[6], m[7]];
  assert.equal(Object.keys(out).length, 65, '65 objetos en el prototipo');
  assert.deepEqual(server, out);
  assert.equal(new Set(Object.values(out).map((x) => x[0])).size, 13, '13 carpetas');
});

function engineRules() {
  const src = read(path.join(OF, 'oficina_plano.js'));
  const body = src.slice(src.indexOf('// ===== reglas puras'), src.indexOf('// ===== fin reglas puras')).replace(/^export /gm, '');
  const names = [...body.matchAll(/^(?:function|const)\s+([A-Za-z_]\w*)/gm)].map((m) => m[1]);
  const ctx = vm.createContext({ Math, Number, String, JSON, Array, Set, parseInt, defaultToon: (i) => ({ seed: i, hair: 'corto' }), defaultHuman: (i) => ({ base: 'Remy', seed: i }) });
  vm.runInContext(body + `\n;globalThis.__out = {${names.join(',')}};`, ctx);
  return ctx.__out;
}

test('motor en vivo: cámara del editor, conexiones, asientos, animación desde el dato real, pantallas, nevera y personaje', () => {
  const E = engineRules();
  assert.deepEqual(plain(E.cameraFor({ w: 14, d: 10 })), { pos: [14 * .15, 14 * .82, 12], look: [0, 0, -.3], fov: 45 }, 'misma vista inicial que el editor');
  assert.equal(E.connKind('mesa:Mesa 3'), 'mesa'); assert.equal(E.connId('mesa:Mesa 3'), 'Mesa 3'); assert.equal(E.connKind(undefined), '');
  const s = E.seatOf({ x: 1, z: 2, rot: 0 }, { d: .7 }, 'escritorio');
  assert.deepEqual(plain(s).map((v) => +v.toFixed(3)), [1, 2.65, +Math.PI.toFixed(3)], 'la persona frente al escritorio, mirándolo');
  assert.equal(E.tableSeats({ item: 'mesa_redonda', x: 0, z: 0, rot: 0 }, { w: 2, d: 2 }).length, 4);
  assert.equal(E.tableSeats({ item: 'mesa_larga', x: 0, z: 0, rot: 0 }, { w: 2.4, d: 1.9 }).length, 6);
  assert.equal(E.tableSeats({ item: 'mesa_2', x: 0, z: 0, rot: 90 }, { w: .8, d: 1.6 }).length, 2);
  assert.equal(E.liveClip('dance', true, true), 'sit', 'en pausa -> sentada');
  assert.equal(E.liveClip('idle', false, true), 'work', 'en su puesto -> trabajando');
  assert.equal(E.liveClip('dance', false, false), 'dance'); assert.equal(E.liveClip(undefined, false, false), 'idle');
  assert.equal(E.screenKind({ item: 'tv_pared', screen: 'Partido / TV' }), null, 'Partido / TV es imagen fija');
  assert.equal(E.screenKind({ item: 'tv_pared', screen: 'Domicilios' }), 'domicilios');
  assert.equal(E.screenKind({ item: 'tv_pared', screen: 'Partido / TV', conn: 'pantalla:comandas' }), 'comandas', 'conectada: su dato real');
  assert.deepEqual(plain(E.screenModel('canciones', { songs: [{ title: 'Tusa' }] }).rows), ['Tusa']);
  assert.equal(E.screenModel('turno', { staff: { people: [{ label: 'Ana P.' }] } }).title, 'Personal en turno · 1');
  assert.equal(E.inventoryLevel({ inventory: { Cervezas: { items: 4, low: 1 } } }, 'inv:Cervezas'), .75);
  assert.equal(E.inventoryLevel({}, 'inv:Nada'), 1, 'sin datos: nevera llena');
  const look = plain(E.lookFor('abc', { abc: { human: { base: 'Ch22_nonPBR' } } }));
  assert.equal(look.human.base, 'Ch22_nonPBR', 'el personaje guardado manda'); assert.equal(look.toon.hair, 'corto', 'sobre el de por defecto');
  assert.deepEqual(plain(E.lookFor('xyz', {})), plain(E.lookFor('xyz', {})), 'el mismo personaje cada vez (por su huella)');
});

test('pantallas seguras para la CSP: sin scripts ni onclick en línea, importmap de three r160 y rutas con sesión', () => {
  for (const page of ['index.html', 'constructor.html', 'personajes.html']) {
    const html = read(path.join(B3D, page));
    assert.ok(!/\son[a-z]+=/i.test(html), page + ': sin onclick');
    const scripts = [...html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)];
    for (const [, attrs, code] of scripts) assert.ok(/type="importmap"/.test(attrs) || (/src="\/admin-v2plus\/oficina\/b3d\/[a-z]+\.js"/.test(attrs) && !code.trim()), page + ': ' + attrs);
    assert.ok(html.includes('"three":"/admin-v2plus/oficina/vendor/three/build/three.module.js"'), page);
    assert.ok(!/(src|href)="(js|css|assets|lib)\//.test(html), page + ': sin rutas del prototipo');
  }
  const routes = read(path.join(ROOT, 'app', 'web', 'constructor_routes.py'));
  for (const f of fs.readdirSync(B3D).filter((f) => /\.(js|css)$/.test(f))) assert.ok(routes.includes(`"${f}"`), f + ' en la lista blanca');
  assert.ok(read(path.join(ROOT, 'app', 'web', 'oficina_routes.py')).includes('"examples/jsm/controls/OrbitControls.js"'));
});

test('el motor en vivo no carga el guardado de la consola y Mixamo sale del bucket privado (nunca del repo)', () => {
  for (const f of ['core.js', 'catalog.js', 'room.js', 'char.js']) assert.ok(!read(path.join(B3D, f)).includes("from './store.js'"), f);
  assert.ok(!read(path.join(OF, 'oficina_plano.js')).includes('store.js'));
  const ch = read(path.join(B3D, 'char.js'));
  assert.ok(ch.includes("export let ASSET_BASE = '/admin-v2plus/oficina/bar';") && ch.includes('`${ASSET_BASE}/personajes/${n}.glb`'));
  assert.ok(read(path.join(OF, 'oficina_plano.js')).includes("setAssetBase(ROOT + 'bar')"), 'visor: ruta firmada');
  const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)]);
  const mixamo = walk(path.join(ROOT, 'app')).filter((f) => /(Ch\d\d_nonPBR|Remy|Rumba_Dancing|Typing|Sitting)\.glb$/i.test(f));
  assert.deepEqual(mixamo, [], 'Mixamo no se redistribuye');
});

test('Humano sin accesorios sueltos (decisión del dueño); Caricatura con sus 9 accesorios', () => {
  const ch = read(path.join(B3D, 'char.js')), pe = read(path.join(B3D, 'people.js'));
  assert.ok(ch.includes('export const HUMAN_ACC = [];'));
  const hum = pe.slice(pe.indexOf('const TABS_HUM'), pe.indexOf('\n', pe.indexOf('const TABS_HUM')));
  const toon = pe.slice(pe.indexOf('const TABS_TOON'), pe.indexOf('\n', pe.indexOf('const TABS_TOON')));
  assert.ok(!hum.includes("'acc'") && toon.includes("'acc'"));
  assert.equal((ch.match(/acc: \[(.*?)\],\n/s) || [''])[0].split("['").length - 1, 9);
});

// ------------------------------------------------------------------ Chrome de verdad (API simulada, sin capturas)
const CH = { skip: !H.CHROME && 'Chrome no está instalado en esta máquina', timeout: 300000 };

test('Chrome: constructor guarda por empresa, conecta con datos reales y publica (Humano y Caricatura)', CH, async () => {
  for (const style of ['human', 'toon']) {
    const srv = await H.serve(); const cid = H.COMPANIES[0].id; srv.states.get(cid).style = style;
    const b = await H.launch({ width: 1440, height: 900 });
    try {
      await b.go(`${srv.url}/admin-v2plus/biblioteca3d/constructor?empresa=${cid}`);
      await b.waitFor("document.querySelectorAll('#tpls .tc').length >= 6", 120);
      assert.equal(await b.evaluate("document.querySelector('.cxEmp').textContent"), 'Night Bar (demo)');
      await b.evaluate("document.querySelector('#tpls .tc').click(); true");
      await b.waitFor('!!(window.__cx && __cx.plan && __cx.plan.objects.length > 10)');
      const conns = await b.evaluate('JSON.stringify(__cx.plan.objects.filter(o => o.conn).map(o => o.conn))');
      assert.ok(JSON.parse(conns).includes('mesa:Mesa 1') && JSON.parse(conns).includes('caja:caja-1'), 'la plantilla queda conectada a las entidades reales: ' + conns);
      const n = await b.evaluate("(() => { __cx.placeItem('sofa', 0, 0, 0); return __cx.plan.objects.length; })()");
      await b.waitFor(`(${JSON.stringify(srv.log.length)} >= 0) && true`);
      await H.sleep(1500);
      const put = srv.log.filter((l) => l.method === 'PUT' && /\/disenos\//.test(l.path)).pop();
      assert.ok(put && put.json.plan.objects.length === n, 'autoguardado con el plano del prototipo');
      await b.evaluate("document.querySelector('#pubBtn').click(); true"); await H.sleep(1200);
      assert.ok(srv.log.some((l) => l.method === 'POST' && /\/publicar$/.test(l.path)), 'Publicar en vivo');
      await b.evaluate("document.querySelector('#menuBtn').click(); document.querySelector('#mVersions').click(); true"); await H.sleep(800);
      assert.ok((await b.evaluate("document.querySelector('#verList').textContent")).includes('Versión 1'));
      assert.deepEqual(b.errors, [], style + ' sin errores');
      assert.ok((await b.evaluate('JSON.stringify(__cx.bench(5))')).includes('"objects"'));
    } finally { b.close(); srv.server.close(); }
  }
});

test('Chrome: personajes (equipo real, editor, guardar y uniforme) e inicio (empresa, estilo y marca)', CH, async () => {
  const srv = await H.serve(); const cid = H.COMPANIES[0].id;
  const b = await H.launch({ width: 1440, height: 900 });
  try {
    await b.go(`${srv.url}/admin-v2plus/biblioteca3d/personajes?empresa=${cid}`);
    await b.waitFor("document.querySelectorAll('#grid .sc').length >= 6", 120);
    await b.evaluate("document.querySelector('#grid .sc').click(); true");
    await b.waitFor("!document.querySelector('#edit').classList.contains('hide')");
    assert.deepEqual(JSON.parse(await b.evaluate("JSON.stringify([...document.querySelectorAll('#ic small')].map(x => x.textContent))")), ['Persona', 'Piel', 'Pelo', 'Barba', 'Arriba', 'Abajo', 'Zapatos', 'Uniforme'], 'Humano: sin Accesorios');
    await b.evaluate("document.querySelector('#ic [data-t=arriba]').click(); document.querySelector('#pan .cw button').click(); document.querySelector('#save').click(); true");
    await H.sleep(1200);
    assert.ok(srv.log.some((l) => l.method === 'PUT' && /\/equipo\/[0-9a-f]{12}$/.test(l.path) && l.json.custom === true), 'guardar el personaje');
    await b.evaluate("document.querySelector('#back').click(); true"); await H.sleep(500);
    await b.evaluate("document.querySelector('[data-ap]').click(); true"); await H.sleep(1200);
    assert.ok(srv.log.some((l) => l.method === 'PUT' && /\/equipo\//.test(l.path) && l.json.uniform === 'u-barra'), 'Aplicar uniforme a su área');
    await b.evaluate("document.querySelector('#stySel').value = 'toon'; document.querySelector('#stySel').dispatchEvent(new Event('change')); true"); await H.sleep(600);
    assert.ok(srv.log.some((l) => l.path.endsWith('/estilo') && l.json.style === 'toon'));
    await b.evaluate("document.querySelector('#grid .sc').click(); true"); await H.sleep(800);
    assert.ok((await b.evaluate("[...document.querySelectorAll('#ic small')].map(x => x.textContent).join()")).includes('Accesorios'), 'Caricatura: con Accesorios');
    await b.go(`${srv.url}/admin-v2plus/biblioteca3d/?empresa=${cid}`);
    await b.waitFor("document.querySelectorAll('.ec button').length === 2", 60);
    assert.equal(await b.evaluate("document.querySelectorAll('#br input[disabled]').length"), 4, 'Estudio de marca de solo lectura');
    assert.ok((await b.evaluate("document.querySelector('a[data-to=personajes]').getAttribute('href')")).includes('empresa=' + cid), 'la empresa viaja');
    await b.evaluate("document.querySelector('#apply').click(); true"); await H.sleep(1200);
    assert.ok(srv.log.some((l) => l.method === 'POST' && l.path.endsWith('/aplicar-marca')));
    await b.evaluate("document.querySelectorAll('.ec button')[1].click(); true"); await H.sleep(1200);
    assert.ok((await b.evaluate('location.search')).includes(H.COMPANIES[1].id));
    assert.deepEqual(b.errors, []);
  } finally { b.close(); srv.server.close(); }
});

test('Chrome: visor del cliente dibuja el plano publicado de 150 objetos con room.js + char.js en los dos estilos', CH, async () => {
  const out = {};
  for (const style of ['humano', 'caricatura']) {
    const v = await H.serveViewer({ style }); const b = await H.launch({ width: 1280, height: 720 });
    try {
      await b.go(v.url); await b.waitFor('!!(window.__cxVivo && window.__cxVivo.floor)', 120); await H.sleep(6000);
      out[style] = JSON.parse(await b.evaluate(`(() => { const {floor, R} = window.__cxVivo; const gl = R.getContext(); const t0 = performance.now(); for (let i = 0; i < 5; i++) floor.tick(); gl.finish();
        let objs = 0, people = 0; floor.scene.traverse(x => { if (x.isGroup && x.userData.objId) objs++; }); floor.scene.children.forEach(g => { let p = false; g.traverse(x => { if (x.userData.person) p = true; }); if (p) people++; });
        return JSON.stringify({ms: (performance.now() - t0) / 5, objs, people, chip: document.querySelector('[data-biz]').textContent, tags: [...document.querySelectorAll('#barTags .tg')].map(t => t.textContent).join('|')}); })()`));
      assert.deepEqual(b.errors, [], style + ' sin errores');
    } finally { b.close(); v.server.close(); }
  }
  for (const s of ['humano', 'caricatura']) {
    assert.equal(out[s].objs, 151, s + ': todos los objetos del plano');
    assert.ok(out[s].people >= 5, s + ': 2 personas en turno + clientes en la mesa con QR activo');
    assert.equal(out[s].chip, '1 mesas con QR activo');
    assert.ok(out[s].tags.includes('Laura M. · Cajera') && out[s].tags.includes('Andrés P. · Barman'), 'las personas aparecen cuando abren turno');
  }
  console.log(`ms por cuadro (software, sin GPU): humano ${out.humano.ms.toFixed(1)}, caricatura ${out.caricatura.ms.toFixed(1)}`);
});
