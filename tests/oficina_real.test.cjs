// Oficina 3D fase 1.5 · reglas puras del piso realista: evento -> animación con datos simulados, cámara casa de
// muñecas, clientes por mesa, animaciones de Quaternius por nombre y el resumen del representante (sin dinero).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const load = () => import(pathToFileURL(path.resolve('app/web/oficina/oficina_real_rules.js')).href);

const base = () => ({
  ok: true, rev: 'a',
  tables: [{ label: 'Mesa 1', open: false, guests: null }, { label: 'Mesa 7', open: false, guests: null }],
  orders: [], songs: [], game: null,
  staff: { count: 2, people: [{ key: 'b1', uniform: 'barman', paused: false, task: 'Atendiendo la barra' }, { key: 'm1', uniform: 'mesero', paused: false }] },
  kpis: [['Mesas abiertas', '0'], ['Pedidos a barra', '0'], ['Canciones pedidas', '0'], ['Personal en turno', '2']],
  business: { open: true },
});
const types = ev => ev.map(e => e.type);

test('refresco entre 5 y 10 s, 12 animaciones mínimas y transición suave', async () => {
  const R = await load();
  assert.ok(R.LIVE_MS >= 5000 && R.LIVE_MS <= 10000);
  assert.deepEqual(R.ANIMS, ['quieto', 'caminar', 'sentarse', 'sentado_hablando', 'teclear', 'servir', 'preparar_trago', 'mezclar', 'brindar', 'bailar', 'cafe', 'telefono']);
  assert.ok(R.FADE > 0 && R.FADE < 1);
});

test('mesa abierta -> llegan y se sientan; mesa cerrada -> se despiden y salen', async () => {
  const R = await load();
  const a = base(); const b = base();
  b.tables[1] = { label: 'Mesa 7', open: true, guests: 3 };
  const ev = R.diffLive(a, b);
  assert.deepEqual(ev.filter(e => e.type === 'mesa_abierta'), [{ type: 'mesa_abierta', table: 'Mesa 7', guests: 3, instant: false }]);
  assert.deepEqual(R.animationFor(ev.find(e => e.type === 'mesa_abierta')).anims, ['caminar', 'sentarse', 'sentado_hablando']);
  const c = base();
  const out = R.diffLive(b, c);
  assert.ok(types(out).includes('mesa_cerrada'));
  const anim = R.animationFor(out.find(e => e.type === 'mesa_cerrada'));
  assert.equal(anim.path, 'mesa→entrada'); assert.equal(anim.bubble, '👋');
});

test('sin número de personas en Clonexa llegan 2 a 4 (siempre los mismos por mesa)', async () => {
  const R = await load();
  for (let i = 1; i <= 30; i++) { const n = R.guestsFor({ label: `Mesa ${i}` }); assert.ok(n >= 2 && n <= 4); assert.equal(n, R.guestsFor({ label: `Mesa ${i}` })); }
  assert.equal(R.guestsFor({ label: 'Mesa 1', guests: 5 }), 5);
  assert.equal(R.guestsFor({ label: 'Mesa 1', guests: 40 }), 6, 'tope razonable');
});

test('pedido nuevo -> globo con la cantidad y el barman prepara; entregado -> el mesero lo lleva', async () => {
  const R = await load();
  const a = base(); const b = base();
  b.orders = [{ id: 'o1', table: 'Mesa 7', state: 'nuevo', items: 3 }];
  const nuevo = R.diffLive(a, b).find(e => e.type === 'pedido_nuevo');
  assert.deepEqual(nuevo, { type: 'pedido_nuevo', order: 'o1', table: 'Mesa 7', items: 3, instant: false });
  assert.deepEqual(R.animationFor(nuevo), { who: 'barman', anims: ['preparar_trago'], bubble: '🧾 3 productos', at: 'mesa' });
  const c = base(); c.orders = [{ id: 'o1', table: 'Mesa 7', state: 'entregado', items: 3 }];
  const ent = R.diffLive(b, c).find(e => e.type === 'pedido_entregado');
  assert.equal(ent.table, 'Mesa 7');
  const anim = R.animationFor(ent);
  assert.equal(anim.who, 'mesero'); assert.deepEqual(anim.anims, ['servir', 'caminar', 'quieto']); assert.equal(anim.then.anims[0], 'brindar');
  assert.equal(R.animationFor({ type: 'pedido_nuevo', items: 1 }).bubble, '🧾 1 producto');
});

test('canción pedida -> nota sobre el DJ con el título; juego activo -> pantalla grande', async () => {
  const R = await load();
  const a = base(); const b = base();
  b.songs = [{ id: 's1', title: 'La Bicicleta' }];
  b.game = { kind: 'trivia', label: 'Trivia', state: 'playing' };
  const ev = R.diffLive(a, b);
  const song = ev.find(e => e.type === 'cancion');
  assert.equal(song.title, 'La Bicicleta');
  assert.deepEqual(R.animationFor(song), { who: 'dj', anims: ['mezclar'], bubble: '♪ La Bicicleta' });
  assert.deepEqual(R.animationFor(ev.find(e => e.type === 'juego')), { who: 'pantalla', screen: 'trivia' });
  const c = JSON.parse(JSON.stringify(b)); c.game = null;
  assert.deepEqual(R.animationFor(R.diffLive(b, c).find(e => e.type === 'juego_fin')), { who: 'pantalla', screen: 'marca' });
  assert.deepEqual(R.screenLines(b), ['Trivia', 'jugando ahora']);
  assert.ok(!types(R.diffLive(b, JSON.parse(JSON.stringify(b)))).includes('cancion'), 'la misma canción no se repite');
});

test('turno: entra a su puesto; pausa -> zona de personal con café; cierra turno -> se va', async () => {
  const R = await load();
  const a = base(); const b = base();
  b.staff.people.push({ key: 'd1', uniform: 'dj', paused: false });
  const ini = R.diffLive(a, b).find(e => e.type === 'turno_inicio');
  assert.equal(ini.key, 'd1'); assert.equal(R.animationFor(ini).path, 'entrada→puesto');
  const c = JSON.parse(JSON.stringify(b)); c.staff.people[1].paused = true;
  const pausa = R.diffLive(b, c).find(e => e.type === 'pausa');
  assert.deepEqual(R.animationFor(pausa), { who: 'personal', path: 'puesto→personal', anims: ['caminar', 'cafe'] });
  assert.equal(R.workAnim('mesero', true), 'cafe');
  const d = JSON.parse(JSON.stringify(c)); d.staff.people[1].paused = false;
  assert.ok(types(R.diffLive(c, d)).includes('retoma'));
  const e = JSON.parse(JSON.stringify(d)); e.staff.people = e.staff.people.filter(p => p.key !== 'd1');
  const fin = R.diffLive(d, e).find(x => x.type === 'turno_fin');
  assert.equal(fin.key, 'd1'); assert.equal(R.animationFor(fin).path, 'puesto→entrada');
  assert.equal(R.workAnim('barman', false), 'preparar_trago'); assert.equal(R.workAnim('dj', false), 'mezclar'); assert.equal(R.workAnim('caja', false), 'teclear');
});

test('la primera copia solo acomoda (sin animar llegadas)', async () => {
  const R = await load();
  const b = base(); b.tables[0].open = true; b.orders = [{ id: 'o1', table: 'Mesa 1', state: 'nuevo', items: 1 }];
  const ev = R.diffLive(null, b);
  assert.ok(ev.filter(e => ['mesa_abierta', 'pedido_nuevo', 'turno_inicio'].includes(e.type)).every(e => e.instant === true));
  assert.deepEqual(R.diffLive(b, { ok: false }), []);
});

test('cámara casa de muñecas: la pared del frente siempre oculta, las laterales según el giro y sin atravesar paredes', async () => {
  const R = await load();
  assert.deepEqual(R.hiddenWalls(0), ['frente']);
  assert.deepEqual(R.hiddenWalls(0.9), ['frente', 'derecha']);
  assert.deepEqual(R.hiddenWalls(-0.9), ['frente', 'izquierda']);
  const room = { W: 26, D: 18 };
  const c = R.clampCamera({ az: 3, pol: 0.1, dist: 1, tx: 99, tz: -99 }, room);
  assert.ok(c.az <= 1.15 && c.pol >= 0.42 && c.dist >= 6 && c.tx <= 12 && c.tz >= -8);
  assert.ok(R.clampCamera({ az: 0, pol: 2, dist: 999 }, room).pol <= 1.22, 'nunca por debajo del piso');
  const wide = R.fitDistance(room, 40, 16 / 9), tall = R.fitDistance(room, 40, 9 / 16);
  assert.ok(tall > wide && wide > 10, 'en celular se aleja para que el piso llene la pantalla');
});

test('animaciones de Quaternius por nombre; si falta una, se usa la propia', async () => {
  const R = await load();
  const names = ['Idle_Loop', 'Walk_Loop', 'Sitting_Enter', 'Sitting_Talking_Loop', 'Dance_Loop', 'Drink'];
  assert.equal(R.pickClip(names, 'quieto'), 'Idle_Loop');
  assert.equal(R.pickClip(names, 'caminar'), 'Walk_Loop');
  assert.equal(R.pickClip(names, 'sentarse'), 'Sitting_Enter');
  assert.equal(R.pickClip(names, 'sentado_hablando'), 'Sitting_Talking_Loop');
  assert.equal(R.pickClip(names, 'bailar'), 'Dance_Loop');
  assert.equal(R.pickClip(names, 'teclear'), null);
  for (const a of R.ANIMS) assert.ok(R.UAL_CLIPS[a], a);
  // nombres reales de Universal Animation Library [Standard] (UAL1_Standard.glb)
  const ual = ['Idle_Loop', 'Idle_Talking_Loop', 'Walk_Loop', 'Walk_Formal_Loop', 'Sitting_Enter', 'Sitting_Exit', 'Sitting_Idle_Loop', 'Sitting_Talking_Loop', 'Dance_Loop', 'Interact', 'PickUp_Table'];
  const got = Object.fromEntries(R.ANIMS.map(a => [a, R.pickClip(ual, a)]));
  assert.deepEqual(got, { quieto: 'Idle_Loop', caminar: 'Walk_Loop', sentarse: 'Sitting_Enter', sentado_hablando: 'Sitting_Talking_Loop', teclear: 'Interact',
    servir: 'Walk_Formal_Loop', preparar_trago: 'Interact', mezclar: 'Interact', brindar: 'Sitting_Talking_Loop', bailar: 'Dance_Loop', cafe: 'Idle_Talking_Loop', telefono: 'Idle_Talking_Loop' },
    'todas las animaciones tienen clip; brindar (sentado) nunca cae a una de pie');
});

test('el representante resume solo actividad (nada de dinero)', async () => {
  const R = await load();
  const s = base(); s.tables[1].open = true; s.kpis = [['Mesas abiertas', '1'], ['Pedidos a barra', '12'], ['Canciones pedidas', '4'], ['Personal en turno', '3']];
  s.game = { kind: 'roulette', label: 'Ruleta', state: 'registration' };
  const text = R.repSummary(s);
  assert.equal(text, 'Hoy va así: 1 mesa abierta · 12 pedidos a barra · 4 canciones · 3 en turno · 🎮 Ruleta en pantalla');
  assert.doesNotMatch(text, /\$|cop|total|venta|precio/i);
  assert.match(R.repSummary({ ...s, business: { open: false } }), /^Cerrado por ahora\./);
  assert.match(R.repSummary({ ...s, business: { open: false, activity_off_hours: true } }), /^Fuera de horario pero con movimiento/);
});

test('modo arquitecto: solo posiciones redondeadas; pasillos para caminar', async () => {
  const R = await load();
  assert.deepEqual(R.layoutBody({ 'mesa:Mesa 1': [1.23456, -2.5, 0.785398] }), { items: { 'mesa:Mesa 1': [1.23, -2.5, 0.785] } });
  assert.deepEqual(R.aislePath([0, 5], [3, -2], 1), [[0, 1], [3, 1], [3, -2]]);
});

test('el motor usa la copia viva, pausa sin pestaña y nunca pide dinero', () => {
  const src = readFileSync('app/web/oficina/oficina_real.js', 'utf8');
  assert.match(src, /document\.addEventListener\('visibilitychange', onVis\)/);
  assert.match(src, /if \(closed \|\| document\.hidden\) return;/);
  assert.match(src, /\/vivo\?rev=/);
  assert.doesNotMatch(src, /total|precio|price|subtotal/i);
});
