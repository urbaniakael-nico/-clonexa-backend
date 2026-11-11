// Oficina 3D · bar aprobado (The Time Machine): reglas puras del motor oficina_bar.js con datos simulados.
// Retargeting (mixamorig: y mixamorig12:), escala de cadera, en el sitio, mesa activa vs libre, abrir/cerrar,
// pedido -> mesero, pantalla de canciones con y sin datos, bar cerrado, ambiente marcado, clic que no cambia de piso.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { pathToFileURL } = require('node:url');

const load = () => import(pathToFileURL(path.resolve('app/web/oficina/oficina_bar_rules.js')).href);
const near = (a, b) => assert.ok(Math.abs(a - b) < 1e-6, `${a} ≈ ${b}`);

const snap = (open = [], extra = {}) => Object.assign({
  ok: true, tables: Array.from({ length: 10 }, (_, i) => ({ label: `Mesa ${i + 1}`, open: open.includes(i + 1), guests: null })),
  orders: [], songs: [], song_screen: { now: null, queue: [] }, staff: { count: 2, people: [] },
  kpis: [['Pedidos a barra', '37'], ['Canciones pedidas', '4'], ['Personal en turno', '4']], business: { open: true, hours: '18:00–04:00' },
}, extra);

test('medidas y cámara iguales a la escena aprobada (bar.html)', async () => {
  const R = await load();
  assert.deepEqual(R.ROOM, { W: 16, D: 11, WALL: 3.4 });
  assert.deepEqual(R.CAMERA, { pos: [3, 9.5, 15.5], look: [1, 0.6, -0.5], fov: 32 });
  assert.equal(R.BAR.z1 - R.BAR.z0, 7); assert.equal(R.BAR.h, 1.08); assert.equal(R.BAR.stools, 9);
  assert.deepEqual(R.TABLE_POS.slice(0, 10), [[-2.6, -3.0], [0, -3.0], [-2.6, -0.4], [0, -0.4], [2.6, -0.4], [-2.6, 2.2], [0, 2.2], [2.6, 2.2], [5.2, 2.2], [5.2, 4.4]]);
  near(R.stoolZ(0), -3.9); near(R.stoolZ(8), 2.3);
  assert.equal(R.CLIPS.length, 13);
});

test('retargeting: el prefijo de huesos cambia por personaje (mixamorig: y mixamorig12:)', async () => {
  const R = await load();
  const anim = ['mixamorigHips.position', 'mixamorigHips.quaternion', 'mixamorigLeftArm.quaternion', 'mixamorig:Spine.quaternion'];
  const a = R.retargetPlan(anim, 'mixamorigHips', 0.95, 0.96, 'Idle');
  assert.equal(a.prefix, 'mixamorig');
  assert.deepEqual(a.tracks.map(t => t.to), ['mixamorigHips.position', 'mixamorigHips.quaternion', 'mixamorigLeftArm.quaternion', 'mixamorigSpine.quaternion']);
  const b = R.retargetPlan(anim, 'mixamorig12Hips', 0.99, 0.96, 'Idle');
  assert.equal(b.prefix, 'mixamorig12');
  assert.deepEqual(b.tracks.map(t => t.to), ['mixamorig12Hips.position', 'mixamorig12Hips.quaternion', 'mixamorig12LeftArm.quaternion', 'mixamorig12Spine.quaternion']);
  assert.deepEqual(b.tracks.map(t => t.hips), [true, false, false, false], 'solo Hips.position se escala');
  assert.equal(R.retargetName('mixamorig9Head.quaternion', 'mixamorig2'), 'mixamorig2Head.quaternion');
});

test('escala de la cadera = cadera del personaje / cadera de la animación; caminar y bailar en el sitio', async () => {
  const R = await load();
  near(R.hipScale(2.09, 0.96), 2.09 / 0.96);   // Remy viene en otra escala
  assert.equal(R.hipScale(0, 0.96), 1);
  const k = R.hipScale(0.99, 0.96);
  const walk = [0, 0.95, 0.01, 0.02, 0.93, 0.8, -0.01, 0.95, 1.64];
  const inPlace = R.scaleHips(walk, k, true);
  for (let i = 0; i < inPlace.length; i += 3) { near(inPlace[i], 0); near(inPlace[i + 2], 0.01 * k); }
  near(inPlace[4], 0.93 * k);
  const free = R.scaleHips(walk, k, false);
  near(free[8], 1.64 * k);
  assert.ok(R.IN_PLACE.has('Walking') && R.IN_PLACE.has('Rumba_Dancing') && R.IN_PLACE.has('Silly_Dancing') && !R.IN_PLACE.has('Bartending'));
});

test('animaciones sentadas que empiezan de pie: solo la parte sentada y la cadera sobre la silla', async () => {
  const R = await load();
  const times = [0, 1, 2, 3, 4, 5];
  const v = [0, .95, 0, 0, .91, .6, -.2, .91, 1.7, -.3, .62, 2.6, -.31, .49, 2.66, -.31, .49, 2.64];
  assert.equal(R.seatedStart(times, v), 4);
  assert.equal(R.seatedStart([0, 1], [0, .58, 0, 0, .58, 0]), 0, 'ya sentada desde el inicio');
  const anchored = R.scaleHips([-.31, .49, 2.66, -.3, .49, 2.64], 1, false, true);
  near(anchored[0], 0); near(anchored[2], 0); near(anchored[5], -0.02);
  assert.equal(R.retargetPlan([], 'mixamorigHips', 1, 1, 'Sitting_Drinking', true).anchor, true);
});

test('altura real: hombres 1,78 m y mujeres 1,66 m (Ch07, Ch21, Ch22)', async () => {
  const R = await load();
  for (const n of ['Ch07_nonPBR', 'Ch21_nonPBR', 'Ch22_nonPBR']) assert.equal(R.heightFor(n), 1.66);
  for (const n of ['Remy', 'Ch01_nonPBR', 'Ch06_nonPBR', 'Ch42_nonPBR']) assert.equal(R.heightFor(n), 1.78);
  assert.deepEqual(R.STAFF_MODEL.dj, ['Ch06_nonPBR']); assert.equal(R.REP_MODEL, 'Ch07_nonPBR');
});

test('mesas reales a los puestos del plano y puestos de barra a los 9 taburetes', async () => {
  const R = await load();
  const l = R.layoutTables(['Mesa 1', 'Mesa 2', 'Barra 3', 'Barra 1', 'Mesa 3']);
  assert.deepEqual(l.tables.map(t => [t.label, t.pos]), [['Mesa 1', [-2.6, -3.0]], ['Mesa 2', [0, -3.0]], ['Mesa 3', [-2.6, -0.4]]]);
  assert.deepEqual(l.stools, { 'Barra 3': 2, 'Barra 1': 0 });
  const many = R.layoutTables(Array.from({ length: 16 }, (_, i) => `Mesa ${i + 1}`));
  assert.equal(many.tables.length, 14); assert.equal(many.overflow, 2);
});

test('mesa activa vs libre: etiqueta, y clientes que llegan', async () => {
  const R = await load();
  assert.deepEqual(R.tableTag('Mesa 4', true), { cls: 'mesa on', text: 'Mesa 4 · QR activo', dot: true });
  assert.deepEqual(R.tableTag('Mesa 2', false), { cls: 'mesa off', text: 'Mesa 2 · libre', dot: false });
  for (let i = 1; i <= 20; i++) { const n = R.guestsFor({ label: `Mesa ${i}` }); assert.ok(n === 2 || n === 3); }
  assert.equal(R.guestsFor({ label: 'Mesa 1', guests: 9 }), 4, 'las 4 sillas');
  const cast = R.guestCast('Mesa 7', 3);
  assert.equal(new Set(cast.map(c => c.side)).size, 3);
  assert.ok(cast.every(c => R.SIT_CLIPS.includes(c.clip) && R.HAPPY.includes(c.tint) && R.CLIENTS.includes(c.model)));
  assert.deepEqual(cast, R.guestCast('Mesa 7', 3), 'siempre los mismos por mesa');
});

test('abrir y cerrar mesa; pedido entregado -> el mesero lo lleva (la primera copia no anima)', async () => {
  const R = await load();
  const a = snap([]); const b = snap([7]);
  assert.deepEqual(R.diffBar(null, b), [{ type: 'mesa_abierta', table: 'Mesa 7', guests: R.guestsFor({ label: 'Mesa 7' }), instant: true }]);
  assert.deepEqual(R.diffBar(a, b).map(e => [e.type, e.instant]), [['mesa_abierta', false]]);
  assert.deepEqual(R.diffBar(b, a).map(e => e.type), ['mesa_cerrada']);
  const c = snap([7], { orders: [{ id: 'o1', table: 'Mesa 7', state: 'nuevo', items: 3 }] });
  const d = snap([7], { orders: [{ id: 'o1', table: 'Mesa 7', state: 'entregado', items: 3 }] });
  assert.deepEqual(R.diffBar(c, d), [{ type: 'pedido_entregado', table: 'Mesa 7', items: 3 }]);
  assert.deepEqual(R.diffBar(null, d), [{ type: 'mesa_abierta', table: 'Mesa 7', guests: R.guestsFor({ label: 'Mesa 7' }), instant: true }]);
  assert.equal(R.barmanClip('Preparando 3 productos · Mesa 7'), 'Bartending');
  assert.equal(R.barmanClip('Atendiendo la barra'), 'Idle');
});

test('personal: en su puesto, en pausa se aparta con Idle; el mesero llega detrás de la barra sin atravesarla', async () => {
  const R = await load();
  assert.equal(R.staffSpot('barman', 0, false).clip, 'Bartending');
  assert.deepEqual(R.staffSpot('barman', 0, false).pos.slice(0, 2), [R.BAR.x - 0.75, -2.6]);
  assert.equal(R.staffSpot('dj', 0, false).clip, 'Silly_Dancing');
  assert.equal(R.staffSpot('barman', 0, true).clip, 'Idle');
  const path = R.route(R.ENTRANCE, [R.BAR.x - 0.75, -2.6]);
  const gate = path.findIndex(p => p[0] < R.BAR.x);
  assert.ok(path[gate][1] > R.BAR.z1, 'entra por el extremo de la barra');
  assert.deepEqual(path[path.length - 1], [R.BAR.x - 0.75, -2.6]);
});

test('pista y ambiente: solo con el bar abierto y mesas activas (1 bailarín por cada 2, máximo 4)', async () => {
  const R = await load();
  assert.equal(R.dancersFor(snap([])), 0);
  assert.equal(R.dancersFor(snap([1, 4, 5, 7, 8])), 2);
  assert.equal(R.dancersFor(snap([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])), 4);
  assert.equal(R.dancersFor(snap([1, 2, 3, 4], { business: { open: false } })), 0);
  assert.deepEqual(R.ambientFor(snap([])), { stools: 0, standers: 0 });
  assert.deepEqual(R.ambientFor(snap([1, 4, 5])), { stools: 2, standers: 2 });
  const src = readFileSync('app/web/oficina/oficina_bar_rules.js', 'utf8');
  assert.match(src, /AMBIENTE \(no son datos\)/, 'el ambiente está marcado en el código');
});

test('pantalla "Canciones pedidas" con datos, sin datos y con el bar cerrado', async () => {
  const R = await load();
  const t0 = Date.parse('2026-11-11T23:00:00Z');
  const s = snap([4], { song_screen: { now: { title: 'Noche de salsa', table: 'Mesa 4', since: '2026-11-11T23:00:00Z' },
    queue: [{ title: 'Luces de neón', table: 'Mesa 7' }, { title: 'Volver a bailar', table: 'Barra · silla 3' }, { title: 'Ritmo de medianoche', table: 'Mesa 2' }] } });
  const m = R.screenModel(s, t0 + 105000);
  assert.equal(m.mode, 'lista'); assert.equal(m.now.title, 'Noche de salsa'); assert.equal(m.now.from, 'Pedida desde la Mesa 4');
  near(m.now.progress, 0.5);
  assert.deepEqual(m.queue, [{ n: '2', title: 'Luces de neón', from: 'Mesa 7' }, { n: '3', title: 'Volver a bailar', from: 'Barra · silla 3' }, { n: '4', title: 'Ritmo de medianoche', from: 'Mesa 2' }]);
  assert.equal(R.screenModel(s, t0 + 3600e3).now.progress, 0.95, 'nunca llega al final sin dato real');
  assert.deepEqual(R.screenModel(snap([]), t0), { mode: 'vacio', text: 'Pide tu canción desde el QR de tu mesa' });
  assert.deepEqual(R.screenModel(snap([], { business: { open: false, sign: 'Cerrado · abre 18:00' } }), t0), { mode: 'cerrado', sign: 'Cerrado · abre 18:00' });
  assert.equal(R.screenModel(snap([], { business: { open: false, activity_off_hours: true } }), t0).mode, 'vacio', 'con actividad fuera de horario se muestra igual');
  assert.equal(R.nowPlaying(s), 'Noche de salsa');
});

test('representante: cifras de actividad sin dinero', async () => {
  const R = await load();
  const txt = R.repBubble(snap([1, 4, 5, 7, 8]));
  assert.equal(txt, '5 mesas abiertas · 37 pedidos · 4 canciones · 4 en turno');
  assert.doesNotMatch(txt, /\$|COP|total|venta|precio/i);
});

test('clic dentro del piso: persona -> ficha, mesa -> estado, nunca cambia de piso', async () => {
  const R = await load();
  assert.deepEqual(R.clickTarget({ person: {} }), { type: 'persona' });
  assert.deepEqual(R.clickTarget({ table: 'Mesa 3' }), { type: 'mesa', label: 'Mesa 3' });
  assert.deepEqual(R.clickTarget({ floor: {} }), { type: 'nada' });
  assert.deepEqual(R.clickTarget(undefined), { type: 'nada' });
  const info = R.tableInfo(snap([3], { orders: [{ id: 'a', table: 'Mesa 3', state: 'nuevo', items: 2 }, { id: 'b', table: 'Mesa 3', state: 'entregado', items: 5 }] }), 'Mesa 3');
  assert.deepEqual(info, { label: 'Mesa 3', open: true, since: null, guests: null, pending: 2, songs: 0 });
  // el edificio ignora clic, arrastre y rueda mientras un piso está abierto
  const app = readFileSync('app/web/oficina/oficina_app.js', 'utf8').replace(/\r\n/g, '\n');
  const block = app.slice(app.indexOf('// ===== reglas puras'), app.indexOf('// ===== fin reglas puras ====='));
  const ctx = vm.createContext({}); vm.runInContext(block + '\nthis.f = buildingInputAllowed; this.r = isRealFloor;', ctx);
  assert.equal(ctx.f(null), true); assert.equal(ctx.f({}), false);
  assert.equal(ctx.r({ style: 'bar' }), true); assert.equal(ctx.r({ style: 'clasico' }), false);
  assert.match(app, /e\.target === canvas && buildingInputAllowed\(REAL \|\| realFor\)\) click\(e\)/);
  assert.match(app, /drag = buildingInputAllowed\(REAL \|\| realFor\) \?/);
  const bar = readFileSync('app/web/oficina/oficina_bar.js', 'utf8');
  assert.doesNotMatch(bar, /setFocus|onFloor/, 'el motor del bar no puede cambiar de piso');
});
