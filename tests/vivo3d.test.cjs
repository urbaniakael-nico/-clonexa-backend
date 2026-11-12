// Negocio en vivo 3D: reglas puras del visor del cliente (vivo3d.js), del modo arquitecto (oficina_arquitecto.js),
// de los enlaces de la consola a la oficina (oficina_app.js) y de la página del visor (sin código en línea).
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const read = (f) => readFileSync(f, 'utf8').replace(/\r\n/g, '\n');
function block(src, names, extra = {}) {
  const start = src.indexOf('// ===== reglas puras'), end = src.indexOf('// ===== fin reglas puras =====');
  assert.ok(start >= 0 && end > start, 'bloque de reglas puras');
  const ctx = vm.createContext({ URLSearchParams, ...extra });
  vm.runInContext(src.slice(start, end) + `\nthis.out = {${names.join(',')}};`, ctx);
  const plain = (fn) => (...a) => { const r = fn(...a); return r && typeof r === 'object' ? JSON.parse(JSON.stringify(r)) : r; };
  return Object.fromEntries(Object.entries(ctx.out).map(([k, v]) => [k, typeof v === 'function' ? plain(v) : v]));
}
async function arq() { return import('../app/web/oficina/oficina_arquitecto.js'); }

test('visor: abre el MISMO motor que la oficina y nada más; sin motor -> aviso', () => {
  const { engineFor } = block(read('app/web/oficina/vivo3d.js'), ['engineFor']);
  assert.deepEqual(engineFor({ style: 'bar', template: 'bar' }), { file: 'bar.js', fn: 'openBar' });
  assert.deepEqual(engineFor({ style: 'aprobado', template: 'taller' }), { file: 'taller.js', fn: 'open' });
  assert.deepEqual(engineFor({ style: 'aprobado', template: 'campo' }), { file: 'campo.js', fn: 'open' });
  assert.equal(engineFor({ style: 'clasico', template: 'bar' }), null);
  assert.equal(engineFor({ style: 'aprobado', template: 'general' }), null, 'oficina general: aún sin piso 3D');
  assert.equal(engineFor({ style: 'aprobado', template: 'clonexa' }), null, 'nunca el piso de Clonexa');
});

test('visor: modo liviano de la tarjeta (siempre / nunca / automático en celulares)', () => {
  const { decideLite } = block(read('app/web/oficina/vivo3d.js'), ['decideLite']);
  const desk = { coarse: false, width: 1440, cores: 8, memory: 8 };
  assert.equal(decideLite('1', desk), true);
  assert.equal(decideLite('0', { ...desk, coarse: true, width: 390 }), false);
  assert.equal(decideLite(null, desk), false);
  assert.equal(decideLite(null, { ...desk, coarse: true }), true);
  assert.equal(decideLite(null, { ...desk, width: 390 }), true);
});

test('visor: cada pantalla manda su latido solo en la copia viva', () => {
  const { screenId, withScreen, mergeRaw } = block(read('app/web/oficina/vivo3d.js'), ['screenId', 'withScreen', 'mergeRaw']);
  const store = new Map(); const s = { getItem: (k) => store.get(k) || null, setItem: (k, v) => store.set(k, v) };
  const id = screenId(s, () => 0.5);
  assert.match(id, /^[A-Za-z0-9_-]{16}$/);
  assert.equal(screenId(s, () => 0.1), id, 'estable en la pestaña');
  assert.equal(withScreen('/r/x/y/api/pisos/c/vivo', id), `/r/x/y/api/pisos/c/vivo?s=${id}`);
  assert.equal(withScreen('/r/x/y/api/pisos/c/vivo?rev=a', id), `/r/x/y/api/pisos/c/vivo?rev=a&s=${id}`);
  assert.equal(withScreen('/r/x/y/api/piso', id), '/r/x/y/api/piso');
  assert.deepEqual(mergeRaw([{ genero: 'mujer', personaje: '' }, { personaje: 'Ch21_nonPBR' }, null]), { genero: 'mujer', personaje: 'Ch21_nonPBR' });
});

test('visor: solo lectura (sin editor ni arquitecto), modo TV y página sin código en línea', () => {
  const js = read('app/web/oficina/vivo3d.js');
  assert.ok(js.includes('readonly: true, architect: false'));
  assert.ok(!js.includes('/personajes\', {method: \'PUT\'') && !js.includes('distribucion'), 'el cliente no guarda nada');
  assert.ok(js.includes('requestFullscreen') && js.includes("classList.toggle('tv'"), 'modo TV');
  assert.ok(js.includes('document.hidden'), 'pausa si la pestaña no se ve');
  const html = read('app/web/oficina/vivo3d.html');
  assert.equal((html.match(/<script/g) || []).length, 2, 'solo el importmap y el módulo');
  assert.ok(!/\son[a-z]+=/i.test(html) && !html.includes(' style="'), 'sin manejadores ni estilos en línea');
  assert.ok(html.includes('"/admin-v2plus/oficina/":"__ROOT__"'), 'los motores salen por la ruta firmada');
  const css = read('app/web/oficina/vivo3d.css');
  assert.ok(css.includes('body.vivo3d.tv #v3top') && css.includes('[data-arch-toggle]{display:none}'), 'TV sin controles; nunca el arquitecto');
});

test('modo arquitecto: límites del salón, giro de 90°, cuerpo que guarda y puntos que siguen al objeto', async () => {
  const A = await arq();
  const lim = A.limits({ W: 16, D: 11 });
  assert.deepEqual(A.clampXZ(50, -50, lim), [7.4, -4.9]);
  assert.ok(Math.abs(A.turn90(0) - Math.PI / 2) < 1e-9 && Math.abs(Math.abs(A.turn90(Math.PI / 2)) - Math.PI) < 1e-9);
  const items = [{ key: 'mesa:Mesa 1', get: () => [1.234, -2.345, 0] }, { key: 'dj', get: () => [5, -4, 1.5708] }];
  assert.deepEqual(A.layoutBody(items), { items: { 'mesa:Mesa 1': [1.23, -2.35, 0], dj: [5, -4, 1.571] } });
  assert.deepEqual(A.savedPos({ dj: [1, 2, 3] }, 'dj', [0, 0]), [1, 2, 3]);
  assert.deepEqual(A.savedPos({ dj: ['x', 2, 3] }, 'dj', [6.9, -4.6]), [6.9, -4.6, 0], 'dato malo: la posición aprobada');
  const moved = A.follow([6.9, -5.2], [6.9, -4.6, 0], [0, 0, 0]);
  assert.ok(Math.abs(moved[0]) < 1e-9 && Math.abs(moved[1] + 0.6) < 1e-9, 'el DJ sigue detrás de su cabina');
  const turned = A.follow([1, 0], [0, 0, 0], [0, 0, Math.PI / 2]);
  assert.ok(Math.abs(turned[0]) < 1e-9 && Math.abs(turned[1] + 1) < 1e-9, 'giro como three (rotation.y)');
  const off = A.attachArchitect({ architect: false }, { items: [{}] });
  assert.equal(off.on, false, 'sin permiso de arquitecto (cliente): no hace nada');
});

test('motores: posiciones guardadas y modo arquitecto en bar, taller y restaurante; nunca en el visor', () => {
  const bar = read('app/web/oficina/oficina_bar.js');
  for (const k of ["'mesa:' + label", "'dj'", "'pista'", "'planta:' + i"]) assert.ok(bar.includes(`savedPos(ARCH, ${k}`), k);
  assert.ok(bar.includes('attachArchitect(o,'), 'bar');
  assert.ok(read('app/web/oficina/oficina_taller.js').includes("A.archPos('maquina:' + k"), 'máquinas del taller');
  assert.ok(read('app/web/oficina/oficina_restaurante.js').includes("A.archPos('mesa:' + label"), 'mesas del restaurante');
  assert.ok(read('app/web/oficina/oficina_mixamo.js').includes('attachArchitect(o,'), 'motor común');
  const a = read('app/web/oficina/oficina_arquitecto.js');
  assert.ok(a.includes('if (!o.architect || !items.length)'), 'solo con o.architect (consola)');
});

test('consola -> oficina: ?piso=&arquitecto=1 abre su piso; ?personajes=1 filtra el editor a esa empresa', () => {
  const { scopeFromQuery, scopedEntries } = block(read('app/web/oficina/oficina_app.js'), ['scopeFromQuery', 'scopedEntries'],
    { genderFromName: () => null, attachGestures: () => null });
  const cid = '21a3065e-38ee-4fc3-96ed-ae1707a3b8e4';
  assert.deepEqual(scopeFromQuery(`?piso=${cid}&arquitecto=1`), { cid, arch: true, chars: false });
  assert.deepEqual(scopeFromQuery(`?piso=${cid}&personajes=1`), { cid, arch: false, chars: true });
  assert.deepEqual(scopeFromQuery('?piso=../../x&arquitecto=1'), { cid: null, arch: false, chars: false });
  const groups = [['CLONEXA', [{ cid: null, clave: 'agente:director' }]], ['REPRESENTANTES', [{ cid, clave: 'rep' }, { cid: 'otra', clave: 'rep' }]],
    ['PLANTILLAS DE PERSONAL', [{ cid: null, clave: 'plantilla:barman', sub: 'Todas las empresas' }]], ['PERSONAS EN TURNO AHORA', [{ cid, clave: 'persona:a' }, { cid: 'otra', clave: 'persona:b' }]]];
  const out = scopedEntries(groups, cid, 'The Time Machine');
  assert.deepEqual(out.map(([t]) => t), ['REPRESENTANTES', 'PLANTILLAS DE PERSONAL', 'PERSONAS EN TURNO AHORA'], 'sin los agentes de Clonexa');
  assert.deepEqual(out[0][1].map((e) => e.cid), [cid]);
  assert.deepEqual(out[1][1], [{ cid, clave: 'plantilla:barman', sub: 'The Time Machine' }], 'plantillas propias de la empresa');
  assert.deepEqual(out[2][1].map((e) => e.clave), ['persona:a']);
  assert.deepEqual(scopedEntries(groups, null), groups, 'sin filtro: el editor de siempre');
});
