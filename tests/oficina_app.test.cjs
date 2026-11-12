// Oficina 3D (Consola v2+): reglas puras del navegador, botón del menú y página sin código en línea.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/oficina/oficina_app.js', 'utf8').replace(/\r\n/g, '\n');

function pure() {
  const start = source.indexOf('// ===== reglas puras');
  const end = source.indexOf('// ===== fin reglas puras =====');
  assert.ok(start > 0 && end > start, 'bloque de reglas puras');
  const ctx = vm.createContext({});
  vm.runInContext(source.slice(start, end) + '\nthis.out = {decideLite, fromServer, toServer, mergeCfg, staffDiff, floorYs, assignSeats, reorder, agentVisualState, isRealFloor, esc, POLL_MS, ST};', ctx);
  // valores de otro "realm" (vm): se comparan como JSON
  const plain = fn => (...args) => { const r = fn(...args); return r && typeof r === 'object' ? JSON.parse(JSON.stringify(r)) : r; };
  return Object.fromEntries(Object.entries(ctx.out).map(([k, v]) => [k, typeof v === 'function' ? plain(v) : v]));
}

test('modo liviano: lo elegido manda; si no, solo en celulares o equipos lentos', () => {
  const { decideLite } = pure();
  const desk = { coarse: false, width: 1440, cores: 8, memory: 8 };
  assert.equal(decideLite(null, desk), false);
  assert.equal(decideLite(null, { ...desk, coarse: true }), true, 'celular (pantalla táctil)');
  assert.equal(decideLite(null, { ...desk, width: 390 }), true, 'pantalla angosta');
  assert.equal(decideLite(null, { ...desk, cores: 2 }), true, 'pocos núcleos');
  assert.equal(decideLite(null, { ...desk, memory: 2 }), true, 'poca memoria');
  assert.equal(decideLite('0', { ...desk, coarse: true }), false, 'el interruptor apagado manda');
  assert.equal(decideLite('1', desk), true, 'el interruptor encendido manda');
});

test('quién entra al piso al iniciar turno y quién sale al cerrarlo', () => {
  const { staffDiff } = pure();
  const d = staffDiff(['a', 'b', 'c'], [{ key: 'b' }, { key: 'c' }, { key: 'd' }]);
  assert.deepEqual(d.add.map(p => p.key), ['d']);
  assert.deepEqual(d.remove, ['a']);
  assert.deepEqual(staffDiff([], []), { add: [], remove: [] });
});

test('CLONEXA arriba, los pisos en el orden del ascensor y la recepción abajo', () => {
  const { floorYs, reorder } = pure();
  const ys = floorYs(4);
  assert.deepEqual(ys.floors.map(y => +y.toFixed(2)), [22.85, 17.25, 11.65, 6.05], 'mismas alturas que la maqueta');
  assert.equal(+ys.clonexa.toFixed(2), 28.45);
  assert.ok(ys.clonexa > Math.max(...ys.floors));
  assert.equal(+floorYs(0).clonexa.toFixed(2), 6.05, 'sin empresas: CLONEXA sobre la recepción');
  assert.deepEqual(reorder(['a', 'b', 'c', 'd'], 3, 0), ['d', 'a', 'b', 'c'], 'arrastrar en el ascensor');
});

test('lo guardado en el editor se traduce a los campos del personaje y de vuelta', () => {
  const { fromServer, toServer, mergeCfg } = pure();
  const item = { clave: 'agente:ventas', nombre: 'Nexa Pro', estilo: 'lego', color_ropa: '#112233', color_pelo: '', accesorio: 'casco', cuerpo: 'alto', peinado: 'rizado', cara_url: '/x?e=1&s=2' };
  assert.deepEqual(JSON.parse(JSON.stringify(fromServer(item))), { name: 'Nexa Pro', style: 'lego', color: '#112233', acc: 'casco', body: 'alto', hairStyle: 'rizado' }, 'la imagen ya no se usa');
  assert.deepEqual(JSON.parse(JSON.stringify(fromServer({ estilo: 'modelo', accesorio: 'capa' }))), {}, 'estilos y accesorios retirados no se aplican');
  assert.deepEqual(JSON.parse(JSON.stringify(toServer({ style: 'anime', color: '#000000', name: 'X', body: 'robusto', hairStyle: 'calvo', img: 'no' }))),
    { estilo: 'anime', color_ropa: '#000000', nombre: 'X', cuerpo: 'robusto', peinado: 'calvo' }, 'nada de enlaces');
  const cfg = mergeCfg({ style: 'anime', color: '#f20b6d', hair: '#111' }, [{ estilo: 'real' }, null, { color_ropa: '#abcdef' }].filter(Boolean));
  assert.equal(cfg.style, 'real'); assert.equal(cfg.color, '#abcdef'); assert.equal(cfg.hair, '#111', 'plantilla → empresa → persona');
});

test('puestos: primero los de su uniforme, luego cualquiera libre', () => {
  const { assignSeats } = pure();
  const out = assignSeats([{ uniform: 'cocina' }, { uniform: 'cocina' }, { uniform: 'dj' }, { uniform: 'mesero' }], { cocina: [[1, 1, 0]], any: [[2, 2, 0], [3, 3, 0]] });
  assert.deepEqual(out.map(x => x.seat), [[1, 1, 0], [2, 2, 0], [3, 3, 0]], 'sin puesto libre no aparece (queda en "+N")');
});

test('estados con color: sin datos en gris; uno desconocido también', () => {
  const { agentVisualState, ST } = pure();
  assert.equal(agentVisualState('err'), 'err');
  assert.equal(agentVisualState('raro'), 'nodata');
  assert.equal(ST.nodata.c, '#6b7280');
  assert.equal(ST.err.c, '#ef4444');
});

test('consulta cada 30 s y se pausa si la pestaña no se ve', () => {
  const { POLL_MS } = pure();
  assert.equal(POLL_MS, 30000);
  assert.match(source, /document\.addEventListener\('visibilitychange', \(\) => \{ if \(document\.hidden\) clearTimeout\(timer\); else \{ poll\(\); schedule\(\); \} \}\);/);
  assert.match(source, /if \(document\.hidden\) return;/);
  assert.match(source, /r\.status === 401\) \{ location\.href = '\/admin-v2plus\/login'/);
});

test('three solo desde el propio backend (sin CDN) y sin estilos ni manejadores en línea', () => {
  const imports = [...source.matchAll(/^import .* from '([^']+)';$/gm)].map(m => m[1]);
  assert.deepEqual(imports, ['three', 'three/addons/environments/RoomEnvironment.js', 'three/addons/geometries/RoundedBoxGeometry.js', '/admin-v2plus/oficina/pisos_reglas.js'],
    'three del propio backend y la regla de género de los pisos (misma para editor y pisos)');
  assert.doesNotMatch(source, /https?:\/\/(cdn|unpkg|jsdelivr)/i);
  assert.doesNotMatch(source, /\sstyle="/);
  assert.doesNotMatch(source, /<[a-z][^>]*\son(click|error|load|submit|input|change)=/i);
  const html = readFileSync('app/web/oficina/oficina.html', 'utf8').replace(/\r\n/g, '\n');
  assert.match(html, /<script type="importmap">\{"imports":\{"three":"\/admin-v2plus\/oficina\/vendor\/three\/build\/three\.module\.js"/);
  assert.match(html, /<a class="back" href="\/admin-v2plus" id="btnBack">← Volver a la consola<\/a>/);
});

test('el editor: sin imagen ni modelo; cuerpo, peinado, pelo, piel, ropa con la marca y accesorios', () => {
  assert.match(source, /Usa solo personajes propios o con permiso\. Los personajes de películas o cómics \(Batman, etc\.\) tienen dueño y no se pueden usar\./);
  assert.doesNotMatch(source, /Imagen como cara|Imagen completa|Modelo 3D|type="file"|personajes\/archivo|GLTFLoader/);
  for (const label of ['Cuerpo', 'Peinado', 'Color de pelo', 'Tono de piel', 'Ropa', 'Accesorio', 'Ropa con la marca']) assert.ok(source.includes(label), label);
  assert.match(source, /const ACC_LABEL = \{none: 'Ninguno', delantal: 'Delantal', gorra: 'Gorra', casco: 'Casco', audifonos: 'Audífonos', gafas: 'Gafas', chaleco: 'Chaleco', corbata: 'Corbata'\};/);
});

test('solo los pisos con el interruptor "realista" abren el motor nuevo (y se carga al entrar)', () => {
  const { isRealFloor } = pure();
  assert.equal(isRealFloor({ style: 'realista' }), true);
  assert.equal(isRealFloor({ style: 'clasico' }), false);
  assert.equal(isRealFloor({}), false);
  assert.equal(isRealFloor(null), false);
  assert.equal(isRealFloor({ style: 'bar' }), true, 'el bar aprobado (The Time Machine)');
  assert.match(source, /isBar \? await import\('\/admin-v2plus\/oficina\/bar\.js'\) : await import\('\/admin-v2plus\/oficina\/real\.js'\);/, 'cada motor se carga solo al entrar a su piso');
  assert.match(source, /isCx \? await import\('\/admin-v2plus\/oficina\/clonexa\.js'\) : approved \? await import\(approved\)/, 'pisos aprobados: un motor por plantilla');
  assert.match(source, /if \(REAL\) REAL\.tick\(\); else \{ R\.render\(S, C\); updTags\(\); \}/);
});

test('el textos que llegan del servidor se escapan', () => {
  const { esc } = pure();
  assert.equal(esc('<img src=x onerror=1>"'), '&lt;img src=x onerror=1&gt;&quot;');
  assert.match(source, /\$\{esc\(d\.name\)\}/);
});

test('Consola v2+: "🏢 Ir a la oficina" justo debajo de "Conversaciones Nexa"', () => {
  const html = readFileSync('app/web/admin_v2plus.html', 'utf8').replace(/\r\n/g, '\n');
  assert.match(html, /data-vp-view="nexa">Conversaciones Nexa<\/button>\n\s*<a class="vp-nav-item vp-nav-link" href="\/admin-v2plus\/oficina" data-vp-oficina>🏢 Ir a la oficina<\/a>\n\s*<\/nav>/);
});
