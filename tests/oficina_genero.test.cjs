// Oficina 3D · el género (y el personaje) del editor cambia el modelo en TODOS los pisos y persiste al recargar.
// Cadena: editor -> guardado (oficina_personajes, devuelve TODAS las columnas con "" las no tocadas) -> capas
// (plantilla global -> plantilla de la empresa -> persona) -> motor del piso (personCfg / agentCfg / repCfg / bar).
// Antes: un "" de la fila de la persona tapaba el "Mujer" de su plantilla, la cola de guardado era una sola (cambiar
// de persona antes de 600 ms perdía el cambio), el representante ignoraba el editor y el bar no se rehacía en vivo.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { pathToFileURL } = require('node:url');

const load = () => import(pathToFileURL(path.resolve('app/web/oficina/oficina_pisos_rules.js')).href);
const loadBar = () => import(pathToFileURL(path.resolve('app/web/oficina/oficina_bar_rules.js')).href);
const src = f => readFileSync(path.join('app/web/oficina', f), 'utf8').replace(/\r\n/g, '\n');

// Lo que devuelve el servidor para una fila del editor: todas las columnas, "" las que no se tocaron.
const COLS = ['nombre', 'rol', 'tarea', 'estilo', 'color_ropa', 'color_pantalon', 'color_pelo', 'color_piel', 'accesorio', 'color_accesorio', 'cuerpo', 'peinado',
  'genero', 'personaje', 'tunica', 'barba', 'color_barba'];
const row = (clave, fields) => Object.assign({ company_id: 'velvet', clave }, Object.fromEntries(COLS.map(c => [c, ''])), fields);

function appPure() {
  const s = src('oficina_app.js');
  const start = s.indexOf('// ===== reglas puras'), end = s.indexOf('// ===== fin reglas puras =====');
  const ctx = vm.createContext({ genderFromName: () => null });
  vm.runInContext(s.slice(start, end) + '\nthis.out = {mergeRaw, queueSave, changesLook};', ctx);
  return ctx.out;
}

test('capas: un "" de la persona no tapa el género de su plantilla (la causa de "sigue saliendo un hombre")', async () => {
  const P = await load();
  const { mergeRaw } = appPure();
  const plantilla = row('plantilla:costura', { genero: 'mujer' });
  const persona = row('persona:abc', { tunica: 'si' });   // la persona ya tenía una fila (otro cambio): genero ""
  for (const merged of [P.mergeSaved(undefined, plantilla, persona), JSON.parse(JSON.stringify(mergeRaw([undefined, plantilla, persona])))]) {
    assert.equal(merged.genero, 'mujer');
    assert.equal(merged.tunica, 'si');
    const cfg = P.personCfg('abc', 'Gelo', merged);
    assert.equal(cfg.gender, 'mujer');
    assert.ok(P.WOMEN.includes(cfg.model), `sale ${cfg.model}`);
  }
  // la persona sí manda sobre su plantilla cuando eligió algo
  const m2 = P.mergeSaved(plantilla, row('persona:abc', { genero: 'hombre' }));
  assert.equal(P.personCfg('abc', 'Gelo', m2).gender, 'hombre');
});

test('Velvet, Asadero y VOLTAGE: Hombre <-> Mujer y Personaje cambian el modelo; Automático es estable por persona', async () => {
  const P = await load();
  const floors = [['Velvet', {}], ['Asadero', {}], ['Asadero domiciliario', { models: ['Ch17_nonPBR'] }], ['VOLTAGE', { models: ['Ch17_nonPBR'] }]];
  for (const [name, defaults] of floors) {
    const key = 'k-' + name;
    const auto = P.personCfg(key, 'Gelo', {}, defaults);
    assert.equal(auto.gender, defaults.models ? 'hombre' : 'hombre', `${name}: Gelo sin editar`);
    const w = P.personCfg(key, 'Gelo', P.mergeSaved(row('persona:' + key, { genero: 'mujer', personaje: '' })), defaults);
    assert.equal(w.gender, 'mujer', `${name}: Mujer`);
    assert.ok(P.WOMEN.includes(w.model), `${name}: Mujer -> ${w.model}`);
    assert.equal(P.personCfg(key, 'Gelo', P.mergeSaved(row('persona:' + key, { genero: 'mujer' })), defaults).model, w.model, `${name}: Automático estable`);
    const chosen = P.personCfg(key, 'Gelo', P.mergeSaved(row('persona:' + key, { genero: 'mujer', personaje: 'Ch22_nonPBR' })), defaults);
    assert.equal(chosen.model, 'Ch22_nonPBR', `${name}: personaje elegido`);
    const back = P.personCfg(key, 'Gelo', P.mergeSaved(row('persona:' + key, { genero: 'hombre', personaje: '' })), defaults);
    assert.ok(P.MEN.includes(back.model) && back.gender === 'hombre', `${name}: Mujer -> Hombre`);
    // un personaje del otro género guardado (fila vieja) no gana: Automático del género elegido
    assert.ok(P.WOMEN.includes(P.personCfg(key, 'Gelo', { genero: 'mujer', personaje: 'Remy' }, defaults).model));
  }
  // Automático: distintas personas no son todas el mismo personaje
  const models = new Set(Array.from({ length: 12 }, (_, i) => P.personCfg('p' + i, '', { genero: 'mujer' }).model));
  assert.ok(models.size >= 2, 'Automático reparte personajes del género');
});

test('Clonexa (agentes), representantes y The Time Machine (bar) también siguen al editor', async () => {
  const P = await load();
  const B = await loadBar();
  assert.equal(P.agentCfg('creativo', {}).gender, 'hombre');
  const a = P.agentCfg('creativo', P.mergeSaved(row('agente:creativo', { genero: 'mujer' })));
  assert.ok(P.WOMEN.includes(a.model) && a.gender === 'mujer');
  assert.equal(P.agentCfg('creativo', { genero: 'mujer', personaje: 'Ch21_nonPBR' }).model, 'Ch21_nonPBR');
  // representante (Velvet, Asadero, VOLTAGE): Ch07 por defecto; el editor lo cambia
  assert.equal(P.repCfg({}).model, 'Ch07_nonPBR');
  const rep = P.repCfg(P.mergeSaved(row('rep', { genero: 'hombre' })));
  assert.ok(P.MEN.includes(rep.model) && rep.model !== 'Ch17_nonPBR' && rep.gender === 'hombre');
  assert.equal(P.repCfg({ genero: 'hombre', personaje: 'Ch42_nonPBR' }).model, 'Ch42_nonPBR');
  // bar de The Time Machine: personal y representante
  const merged = P.mergeSaved(row('plantilla:barman', { genero: 'mujer' }), row('persona:x', { tunica: 'no' }));
  assert.ok(B.WOMEN.test(B.staffModel('Ch01_nonPBR', merged, 'x')), 'barman -> mujer');
  assert.equal(B.staffModel('Ch01_nonPBR', { genero: 'mujer', personaje: 'Ch22_nonPBR' }, 'x'), 'Ch22_nonPBR');
  assert.ok(!B.WOMEN.test(B.staffModel(B.REP_MODEL, { genero: 'hombre' }, 'rep')), 'representante del bar -> hombre');
});

test('cola de guardado por personaje: cambiar de persona antes de guardar ya no pierde el cambio', () => {
  const { queueSave, changesLook } = appPure();
  const q = new Map();
  queueSave(q, 'v|persona:gelo', { clave: 'persona:gelo', company_id: 'v' }, { genero: 'mujer', personaje: '' });
  queueSave(q, 'v|persona:otra', { clave: 'persona:otra', company_id: 'v' }, { tunica: 'si' });
  queueSave(q, 'v|persona:gelo', { clave: 'persona:gelo', company_id: 'v' }, { personaje: 'Ch21_nonPBR' });
  assert.deepEqual(JSON.parse(JSON.stringify(q.get('v|persona:gelo'))), { clave: 'persona:gelo', company_id: 'v', genero: 'mujer', personaje: 'Ch21_nonPBR' });
  assert.deepEqual(JSON.parse(JSON.stringify(q.get('v|persona:otra'))), { clave: 'persona:otra', company_id: 'v', tunica: 'si' });
  assert.equal(changesLook({ genero: 'mujer' }), true);
  assert.equal(changesLook({ cuerpo: 'alto' }), false);
});

test('el código usa la cadena completa en todos los pisos (en vivo, sin reabrir la página)', () => {
  const app = src('oficina_app.js');
  assert.match(app, /rawCfg: \(kind, k, uniform\) => mergeRaw\(layers\(kind, k, uniform\)\)/, 'los pisos reciben las capas sin que "" tape');
  assert.match(app, /import \{genderFromName\} from '\/admin-v2plus\/oficina\/pisos_reglas\.js'/, 'el editor usa la misma regla de género que los pisos');
  assert.match(app, /REAL\.rebuild\(\)/, 'el piso abierto se rehace al cambiar');
  assert.doesNotMatch(app, /let saveTimer = null, pending = \{\}/, 'ya no hay una sola cola de guardado');
  assert.match(src('oficina_mixamo.js'), /rebuild\(\) \{/);
  assert.match(src('oficina_bar.js'), /rebuild\(\) \{/, 'The Time Machine también cambia en vivo');
  assert.match(src('oficina_bar.js'), /staffModel\(RULES\.REP_MODEL, \(o\.rawCfg && o\.rawCfg\('rep', 'rep'\)\)/);
  for (const f of ['oficina_taller.js', 'oficina_restaurante.js', 'oficina_campo.js']) {
    assert.match(src(f), /P\.repCfg\(savedFor\(o, 'rep', 'rep'\)\)/, `${f}: el representante sigue al editor`);
    assert.doesNotMatch(src(f), /makePerson\(\{model: 'Ch07_nonPBR', kind: 'rep'/, `${f}: representante fijo`);
  }
  assert.match(src('oficina_taller.js'), /savedFor\(o, 'staff', p\.key, p\.uniform \|\| 'costura'\)/, 'Velvet usa la plantilla real de la persona');
});
