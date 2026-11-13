// Oficina 3D · piso de Clonexa · área Innovación (NEXUS): estado real del Radar, sin datos de ejemplo, piso ampliado.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');

const SCENE = readFileSync('app/web/oficina/oficina_clonexa.js', 'utf8');
const APP = readFileSync('app/web/oficina/oficina_app.js', 'utf8');
const ENGINE = readFileSync('app/web/oficina/oficina_mixamo.js', 'utf8');
const load = () => import('../app/web/oficina/oficina_pisos_rules.js');

test('NEXUS: Typing cuando el Radar corre, Sitting cuando espera, rojo si falló', async () => {
  const P = await load();
  assert.deepEqual(P.nexusState({ state: 'work' }), { clip: 'Typing', ring: null, cls: 'work', text: 'Investigando…' });
  assert.equal(P.nexusState({ state: 'wait', nuevas: 4 }).text, '4 ideas nuevas');
  assert.equal(P.nexusState({ state: 'wait', nuevas: 1 }).text, '1 idea nueva');
  assert.equal(P.nexusState({ state: 'wait', nuevas: 0 }).text, 'Sin ideas aún');
  const err = P.nexusState({ state: 'err' });
  assert.equal(err.ring, 'red'); assert.equal(err.clip, 'Sitting');
  assert.equal(P.nexusState(null).text, 'Sin datos');
  assert.equal(P.radarTag({ next_label: 'lunes 16/11 8:00' }), 'próximo informe: lunes 16/11 8:00');
  assert.equal(P.radarTag(null), 'próximo informe: —');
});

test('NEXUS: hombre, túnica negra con líneas cian', async () => {
  const P = await load();
  const cfg = P.agentCfg('nexus', {});
  assert.equal(cfg.gender, 'hombre'); assert.equal(cfg.tunic, true); assert.equal(cfg.lines, 0x22d3ee); assert.equal(cfg.name, 'NEXUS');
  assert.equal(P.agentCfg('director', {}).lines, 0xa855f7, 'el CEO sigue con líneas moradas');
});

test('piso ampliado a la derecha: Innovación no tapa ninguna área existente', async () => {
  const P = await load();
  const { ROOM, ZONES } = P.CLONEXA;
  assert.equal(ROOM.X0 - ROOM.W / 2, -15, 'el borde izquierdo no se movió');
  const box = ([x, z, w, d]) => [x - w / 2, z - d / 2, x + w / 2, z + d / 2];
  const inn = box(ZONES.innovacion);
  assert.ok(inn[2] <= ROOM.X0 + ROOM.W / 2, 'cabe en el piso');
  for (const [k, z] of Object.entries(ZONES)) {
    if (k === 'innovacion') continue;
    const b = box(z);
    assert.ok(inn[0] >= b[2] || inn[2] <= b[0] || inn[1] >= b[3] || inn[3] <= b[1], `no se cruza con ${k}`);
  }
  assert.equal(ZONES.innovacion[4], 0x22d3ee, 'línea cian');
  const lim = P.camLimits(ROOM, P.CLONEXA.CAMERA);
  assert.deepEqual(lim.tx, [-14, 25]);
  assert.deepEqual(P.wallsToHide([-16, 5, 0], ROOM).left, true);
  assert.deepEqual(P.wallsToHide([20, 5, 0], ROOM).right, false, 'dentro del piso ampliado');
  assert.equal(P.wallSide({ min: [-15.2, 0, -3], max: [-14.9, 3, 3] }, ROOM), 'left');
});

test('pantallas con datos REALES: nada de los textos de ejemplo de la referencia', () => {
  for (const sample of ['catálogo de productos en la API', 'Cierra en 12 días', 'Competidor POS lanzó', "'5'", 'lunes 8:00\'']) assert.ok(!SCENE.includes(sample), sample);
  assert.match(SCENE, /Sin ideas aún/);
  assert.match(SCENE, /snap\.radar/);
  assert.match(SCENE, /NEXUS · Radar de innovación/);
  assert.match(SCENE, /'Backlog'/);
});

test('tocar NEXUS o la pantalla abre Radar · Innovación (solo esa ruta)', () => {
  assert.match(SCENE, /hit\.userData\.link = P\.RADAR_LINK/);
  assert.match(ENGINE, /else if \(ud\.link && o\.onLink\) o\.onLink\(ud\.link\)/);
  assert.match(APP, /kind === 'nexus' \? openConsole\(info && info\.link\)/);
  assert.match(APP, /function openConsole\(link\) \{ if \(link === '\/admin-v2plus#radar'\) window\.open\(link, '_blank', 'noopener'\); \}/);
});
