// Oficina 3D · pisos aprobados (Clonexa, Velvet, Asadero El Socio, VOLTAGE): reglas puras con datos simulados.
// Turno abierto/cerrado -> aparece/desaparece; pausa -> café (Velvet); mesa QR activa/libre y pedido -> mesero
// (Asadero); +N y fuera de perímetro (VOLTAGE); agente trabajando/espera/lounge/error (Clonexa); género del editor
// (Kriss hombre); y que el código de producción no traiga números de ejemplo de las vistas previas.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync, readdirSync } = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { pathToFileURL } = require('node:url');

const load = () => import(pathToFileURL(path.resolve('app/web/oficina/oficina_pisos_rules.js')).href);
const loadBar = () => import(pathToFileURL(path.resolve('app/web/oficina/oficina_bar_rules.js')).href);

test('medidas y cámaras iguales a las escenas aprobadas', async () => {
  const P = await load();
  // piso de Clonexa ampliado 11 m a la derecha para el área Innovación (NEXUS): el borde izquierdo y las áreas no se movieron
  assert.deepEqual(P.CLONEXA.ROOM, { W: 41, D: 20, WALL: 4.2, X0: 5.5 });
  assert.deepEqual(P.CLONEXA.CAMERA, { pos: [10.2, 19.5, 29.5], look: [5.5, 0, -1.4], fov: 32 }, 'encuadre del piso ampliado');
  assert.deepEqual(P.TALLER.ROOM, { W: 18, D: 12, WALL: 3.4 }); assert.deepEqual(P.TALLER.CAMERA.pos, [1.6, 8.6, 11.4], 'encuadre de velvet.png');
  assert.deepEqual(P.RESTAURANTE.CAMERA, { pos: [3, 11, 17], look: [0.5, 0.3, -0.8], fov: 32 });
  assert.deepEqual(P.CAMPO.ROOM, { W: 20, D: 13, WALL: 3.6 });
  assert.equal(P.CAMPO.VISIBLE, 5);
  assert.deepEqual(Object.keys(P.CLONEXA.ZONES), ['direccion', 'juntas', 'marketing', 'ventas', 'bots', 'tesoreria', 'lounge', 'innovacion']);
  assert.ok(P.LIVE_MS >= 5000 && P.LIVE_MS <= 10000, 'refresco cada 5-10 s');
});

test('género: por el nombre (Kriss es hombre), lo del editor manda y cada género tiene su lista de personajes', async () => {
  const P = await load();
  assert.deepEqual(P.MEN, ['Remy', 'Ch01_nonPBR', 'Ch06_nonPBR', 'Ch42_nonPBR', 'Ch17_nonPBR']);
  assert.deepEqual(P.WOMEN, ['Ch07_nonPBR', 'Ch21_nonPBR', 'Ch22_nonPBR']);
  assert.equal(P.genderFromName('KRISS'), 'hombre');
  assert.equal(P.genderFromName('Kriss M.'), 'hombre');
  assert.equal(P.genderFromName('María'), 'mujer');
  assert.equal(P.genderFromName('Carlos'), 'hombre');
  assert.equal(P.genderFromName('Isabel'), 'mujer');
  assert.equal(P.genderFromName(''), null);
  const kriss = P.personCfg('abc123abc123', 'Kriss', {});
  assert.equal(kriss.gender, 'hombre'); assert.ok(P.MEN.includes(kriss.model), 'Kriss usa un personaje masculino');
  const ana = P.personCfg('k1', 'Ana', {});
  assert.equal(ana.gender, 'mujer'); assert.ok(P.WOMEN.includes(ana.model));
  const forced = P.personCfg('k1', 'Ana', { genero: 'hombre', personaje: 'Ch42_nonPBR', barba: 'si', tunica: 'si', color_barba: '#aa3300' });
  assert.equal(forced.gender, 'hombre'); assert.equal(forced.model, 'Ch42_nonPBR'); assert.equal(forced.beard, true); assert.equal(forced.tunic, true); assert.equal(forced.beardColor, '#aa3300');
  const bad = P.personCfg('k1', 'Ana', { genero: 'mujer', personaje: 'Remy', barba: 'si' });
  assert.ok(P.WOMEN.includes(bad.model), 'un personaje de otro género no se usa'); assert.equal(bad.beard, false, 'barba solo hombres');
  assert.equal(P.personCfg('k1', 'Ana', {}).model, P.personCfg('k1', 'Ana', {}).model, 'estable');
  const voltage = P.personCfg('k9', 'Noel', {}, { models: ['Ch17_nonPBR'] });
  assert.equal(voltage.model, 'Ch17_nonPBR', 'técnicos de VOLTAGE con casco y chaleco');
});

test('CEO: túnica con líneas moradas, barba larga y pelo largo; el editor quita la barba o cambia su color', async () => {
  const P = await load();
  const ceo = P.agentCfg('director', {});
  assert.equal(ceo.tunic, true); assert.equal(ceo.lines, 0xa855f7); assert.equal(ceo.beard, true); assert.equal(ceo.longHair, true); assert.equal(ceo.gender, 'hombre');
  assert.equal(ceo.name, 'Tú · CEO');
  const noBeard = P.agentCfg('director', { barba: 'no', color_pelo: '#c0c0c0' });
  assert.equal(noBeard.beard, false); assert.equal(noBeard.hair, '#c0c0c0'); assert.equal(noBeard.longHair, true);
  const agent = P.agentCfg('contenido', {});
  assert.equal(agent.tunic, true, 'todos los agentes con túnica negra'); assert.equal(agent.lines, null); assert.equal(agent.beard, false);
});

test('Clonexa: trabajando escribe en su escritorio, esperando va al Lounge, error rojo, entrenamiento azul; flujo nuevo aparece solo', async () => {
  const P = await load();
  const workers = [
    { id: 'contenido', area: 'marketing', state: 'work', today: ['Nexa - Vista previa: 2 ejecuciones hoy'] },
    { id: 'planb', area: 'marketing', state: 'wait', today: [] },
    { id: 'tiktok', area: 'marketing', state: 'train', today: [] },
    { id: 'correos', area: 'ventas', state: 'err', today: [] },
    { id: 'lector', area: 'bots', state: 'nodata', today: [] },
    { id: 'guardian', area: 'bots', state: 'work', today: [] },
    { id: 'bot:f1e8f774', area: 'bots', state: 'work', today: ['3 turnos abiertos'], bot: true },
    { id: 'flujo:abc', area: 'ventas', state: 'work', today: [], extra: true },
    { id: 'director', area: 'direccion', state: 'work' }, { id: 'asistente', area: 'juntas', state: 'work' },
  ];
  const plan = P.clonexaPlan(workers); const by = Object.fromEntries(plan.map(p => [p.id, p]));
  assert.ok(!by.director && !by.asistente, 'CEO y Nexa Asistente tienen su puesto propio');
  assert.equal(by.contenido.clip, 'Typing'); assert.ok(by.contenido.desk && !by.contenido.lounge);
  assert.equal(by.planb.lounge[3], 'Sitting_Drinking', 'sin trabajo: al Lounge'); assert.equal(by.planb.tag.cls, 'wait');
  assert.equal(by.tiktok.ring, 'blue'); assert.equal(by.tiktok.clip, 'Sitting');
  assert.equal(by.correos.ring, 'red'); assert.match(by.correos.tag.text, /Error/);
  assert.equal(by.lector.tag.text, 'Sin datos');
  assert.deepEqual(by.guardian.stand, P.CLONEXA.GUARD);
  assert.equal(by['bot:f1e8f774'].area, 'bots'); assert.equal(by['bot:f1e8f774'].tag.text, '3 turnos abiertos');
  assert.equal(by['flujo:abc'].area, 'ventas', 'un flujo nuevo cae en su área');
  // al volver a trabajar, sale del Lounge a su escritorio
  const back = P.clonexaPlan(workers.map(w => (w.id === 'planb' ? { ...w, state: 'work' } : w))).find(p => p.id === 'planb');
  assert.equal(back.lounge, null); assert.equal(back.clip, 'Typing');
  // más trabajadores que escritorios: se agregan en fila
  const many = Array.from({ length: 9 }, (_, i) => ({ id: 'b' + i, area: 'bots', state: 'work' }));
  assert.equal(P.clonexaPlan(many).length, 9); assert.equal(P.desksFor('bots', 9).length, 9);
  assert.equal(P.ceoTag({ approvals: { pieces: 2, batch: true, leads: 1 } }), 'Aprobaciones pendientes: 2 piezas · 1 lote de correos · 1 leads');
  assert.equal(P.ceoTag({ approvals: { pieces: null, batch: null, leads: null } }), 'Aprobaciones pendientes: piezas — · lote — · leads —');
  assert.equal(P.treasuryTag({ treasury: [{ state: 'al_dia' }, { state: 'vencido' }] }), '1 de 2 al día');
  assert.equal(P.treasuryTag({ treasury: null }), 'Facturación: sin datos');
  assert.equal(P.treasuryWorker({ treasury: null }).state, 'nodata');
});

test('Velvet: turno abierto -> cose en su máquina; pausa -> café con minutos; cierra turno -> se va; máquina libre', async () => {
  const P = await load();
  assert.equal(P.machinePositions(6).length, 6); assert.equal(P.machinePositions(12).length, 12);
  assert.deepEqual(P.machinePositions(10)[0], [-7.4, -3.6], 'como velvet.html');
  const a = { key: 'a', label: 'Kriss · Operario', status: 'working', reference: 'REF 210' };
  const b = { key: 'b', label: 'Laura M. · Operaria', status: 'working', reference: null };
  const plan1 = P.assignMachines(new Map(), [a, b], 8);
  assert.equal(plan1.seat.get('a'), 0); assert.equal(plan1.seat.get('b'), 1); assert.deepEqual(plan1.free, [2, 3, 4, 5, 6, 7]);
  const plan2 = P.assignMachines(plan1.seat, [{ ...a, status: 'paused', paused_min: 12 }, b], 8);
  assert.ok(!plan2.seat.has('a') && plan2.cafe.includes('a'), 'pausa -> café'); assert.equal(plan2.seat.get('b'), 1, 'conserva su máquina');
  assert.deepEqual(P.sewerTag({ ...a, status: 'paused', paused_min: 12 }), { cls: 'pausa', text: 'Kriss · Operario', small: 'En pausa · 12 min' });
  assert.equal(P.sewerTag(a).small, 'Cosiendo · REF 210'); assert.equal(P.sewerTag(b).small, 'Cosiendo · —', 'sin referencia: —');
  const d = P.diffPeople(new Set(['a', 'b']), [b]); assert.deepEqual(d.leave, ['a'], 'cierra turno -> se va');
  assert.deepEqual(P.diffPeople(new Set(['b']), [a, b]).enter, ['a'], 'abre turno -> aparece');
  const m = P.boardModel({ lot: null, made: null, meta: null, percent: null, day: null, on_shift: 0, paused: 0, hours: null, week: null, week_sum: null, sent: null, to_send: null, next_send: null });
  assert.equal(m.lot, '—'); assert.equal(m.day, 'día —'); assert.equal(m.next, 'Próximo envío a Bombón: —'); assert.equal(m.kpis[2][0], '—');
  const m2 = P.boardModel({ lot: 'REF 210', made: 45, meta: 71, percent: 63, day: 9, on_shift: 5, paused: 1, hours: '4:35 h', week_sum: 20, sent: 3, to_send: 8 });
  assert.equal(m2.progress, '45 de 71 prendas'); assert.equal(m2.rack, '8 listas para Bombón');
});

test('Asadero: mesa con QR activa/libre, pedido entregado -> mesero, domicilio en camino -> moto', async () => {
  const P = await load();
  assert.deepEqual(P.tableTag({ label: 'Mesa 4', open: true }), { cls: 'mesa on', text: 'Mesa 4 · QR activo', dot: true });
  assert.deepEqual(P.tableTag({ label: 'Mesa 4', open: false }), { cls: 'mesa off', text: 'Mesa 4 · libre', dot: false });
  const lay = P.layoutTables(Array.from({ length: 16 }, (_, i) => `Mesa ${i + 1}`));
  assert.equal(lay.tables.length, P.RESTAURANTE.TABLES.length); assert.equal(lay.overflow, 16 - P.RESTAURANTE.TABLES.length);
  const s0 = { ok: true, tables: [{ label: 'Mesa 1', open: false }], orders: [], deliveries: [] };
  const s1 = { ok: true, tables: [{ label: 'Mesa 1', open: true }], orders: [{ id: 'o1', table: 'Mesa 1', state: 'preparando' }], deliveries: [{ id: 'd1', state: 'cocina', label: 'Domicilio 3F2A' }] };
  const s2 = { ok: true, tables: [{ label: 'Mesa 1', open: true }], orders: [{ id: 'o1', table: 'Mesa 1', state: 'entregado' }], deliveries: [{ id: 'd1', state: 'camino', label: 'Domicilio 3F2A', barrio: 'Kennedy' }] };
  assert.deepEqual(P.diffRestaurante(s0, s1).map(e => e.type), ['mesa_abierta']);
  assert.deepEqual(P.diffRestaurante(s1, s2).map(e => e.type), ['pedido_entregado', 'domicilio_sale']);
  assert.deepEqual(P.diffRestaurante(s2, s0).map(e => e.type), ['mesa_cerrada']);
  assert.deepEqual(P.diffRestaurante(null, s2).map(e => e.type), ['mesa_abierta'], 'la primera copia no anima pedidos');
  assert.equal(P.restStaffTask({ uniform: 'mesero', paused: false }, s1), 'Atendiendo 1 mesa');
  assert.equal(P.restStaffTask({ uniform: 'domiciliario' }, { on_the_way: [{ label: 'Domicilio 3F2A', barrio: 'Kennedy' }] }), 'En camino · Domicilio 3F2A Kennedy');
  assert.equal(P.restStaffTask({ uniform: 'cocina' }, { kitchen: [] }), 'Sin comandas');
  assert.equal(P.repRestaurante({ kpis: [['Pedidos del día', '—']] }), '— pedidos · — en cocina · — domicilios · — en turno');
  const r = P.route([3.2, -2.9], [-3.2, 2.9]); assert.deepEqual(r[r.length - 1], [-3.2, 2.9]);
  assert.equal(P.guestsFor({ label: 'Mesa 1', guests: 6 }), 4);
});

test('VOLTAGE: máximo 5 por operación, +N, supervisor y almacén por cargo, fuera de perímetro con aro rojo', async () => {
  const P = await load();
  const op = { name: 'Alabama', on: 7, scheduled: null, missing: null, outside: 1, extra: 2, cut: { kind: 'entrada', at: '06:30', status: 'enviado' },
    people: [{ key: 'o', label: 'Técnico', role: 'tecnico', outside: true }, { key: 's', label: 'Noel R. · Supervisor', role: 'supervisor' },
      { key: 'w', label: 'Almacén', role: 'almacen' }, { key: 't1', label: 'Técnico', role: 'tecnico' }, { key: 't2', label: 'Técnico', role: 'tecnico', paused: true }] };
  const spots = P.campoSpots(op, 1); const by = Object.fromEntries(spots.map(s => [s.key, s]));
  assert.equal(spots.length, 5);
  assert.equal(by.o.outside, true); assert.equal(by.o.tag.cls, 'red'); assert.equal(by.o.tag.small, '⚠ Fuera de perímetro');
  assert.deepEqual(by.s.pos, [P.CAMPO.SUPERVISOR[0], P.CAMPO.SUPERVISOR[1]]); assert.equal(by.s.clip, 'Talking');
  assert.equal(by.w.clip, 'Idle'); assert.equal(by.t1.clip, 'Bartending'); assert.equal(by.t2.tag.cls, 'pausa');
  assert.ok(P.campoSpots(op, -1).every(s => s.pos[0] < 0 || s.outside === false || s.pos[0] < 0), 'la otra operación al otro lado');
  const b = P.opBoard(op);
  assert.equal(b.on, '7 / —', 'sin horario guardado: —'); assert.equal(b.missing, '—'); assert.equal(b.cut, 'Corte de entrada 06:30 · enviado al grupo ✓');
  assert.equal(P.opBoard({ ...op, cut: null }).cut, 'Último corte: —');
  assert.equal(P.repCampo({ on_shift: 8, ops: [op] }), '8 en turno · 1 fuera de perímetro');
});

test('The Time Machine: el personal usa el selector de género del editor (sin nada guardado, igual que hoy)', async () => {
  const B = await loadBar();
  assert.equal(B.staffModel('Ch01_nonPBR', {}, 'k'), 'Ch01_nonPBR', 'sin cambios');
  assert.ok(B.WOMEN.test(B.staffModel('Ch01_nonPBR', { genero: 'mujer' }, 'k')));
  assert.equal(B.staffModel('Ch22_nonPBR', { genero: 'hombre', personaje: 'Ch42_nonPBR' }, 'k'), 'Ch42_nonPBR');
  assert.equal(B.staffModel('Ch01_nonPBR', { personaje: 'Ch17_nonPBR' }, 'k'), 'Ch01_nonPBR', 'Ch17 no está en el bar');
});

test('editor: género Hombre/Mujer, personaje, túnica y barba se guardan con los nombres del servidor', async () => {
  const src = readFileSync('app/web/oficina/oficina_app.js', 'utf8').replace(/\r\n/g, '\n');
  const start = src.indexOf('// ===== reglas puras'), end = src.indexOf('// ===== fin reglas puras =====');
  const P = await load();
  const ctx = vm.createContext({ genderFromName: P.genderFromName });   // el editor importa la regla de los pisos
  vm.runInContext(src.slice(start, end) + '\nthis.out = {fromServer, toServer, guessGender, isRealFloor, MIXAMO};', ctx);
  const { fromServer, toServer, guessGender, isRealFloor, MIXAMO } = ctx.out;
  assert.deepEqual(JSON.parse(JSON.stringify(toServer({ gender: 'hombre', model: 'Ch42_nonPBR', tunic: 'si', beard: 'no', beardColor: '#111111' }))),
    { genero: 'hombre', personaje: 'Ch42_nonPBR', tunica: 'si', barba: 'no', color_barba: '#111111' });
  assert.deepEqual(JSON.parse(JSON.stringify(fromServer({ genero: 'mujer', personaje: 'Ch21_nonPBR' }))), { gender: 'mujer', model: 'Ch21_nonPBR' });
  assert.equal(guessGender('Kriss'), 'hombre'); assert.equal(guessGender('Lucía P. · Operaria'), 'mujer');
  for (const n of ['Isabel', 'Gelo', 'Raquel', 'Andrea', 'Nicole', 'Luz', 'Carlos']) assert.equal(guessGender(n), P.genderFromName(n), `editor y piso dicen lo mismo: ${n}`);
  assert.equal(MIXAMO.hombre.length, 5); assert.equal(MIXAMO.mujer.length, 3);
  assert.equal(isRealFloor({ style: 'aprobado', template: 'taller' }), true);
  assert.equal(isRealFloor({ style: 'aprobado', template: 'general' }), false, 'solo plantillas con motor aprobado');
  assert.equal(isRealFloor({ style: 'clasico', template: 'taller' }), false);
});

test('código de producción sin números de ejemplo de las vistas previas, sin CDN ni estilos en línea', () => {
  const dir = 'app/web/oficina';
  const files = ['oficina_mixamo.js', 'oficina_pisos_rules.js', 'oficina_clonexa.js', 'oficina_taller.js', 'oficina_restaurante.js', 'oficina_campo.js'];
  const SAMPLES = ['rojita', '48 pedidos', '22 / 25', '8 / 10', '45 de 71', '12 domicilios', '30 en turno', '5 en turno', 'Lote 64%', '9 mesas', '37 pedidos',
    'Vence el 15', '3 de 4 al día', '4:35 h', "'142'", 'día 9 de 20', 'Kennedy Central', 'Castilla', 'Timiza', 'Domicilio #18', '2 bandejas', '1 ajiaco', 'churrasco',
    '2 picadas', 'Corte 6:30 enviado', '6 comandos hoy', '12 platos listos', '20 negocios', '2 conversaciones', 'Lote de 1 negocio', 'Reel 23/11', 'Rack A3', 'Rack C4',
    'Cobrando Mesa 2', '+17', '+3', 'Lun 16', 'Mié 18', 'Math.random', '0 errores hoy', 'reporte el lunes', 'Kennedy · Techo', 'Noel'];
  for (const f of files) {
    const body = readFileSync(path.join(dir, f), 'utf8');
    for (const s of SAMPLES) assert.ok(!body.includes(s), `${f} trae el valor de ejemplo "${s}"`);
    assert.ok(!/https?:\/\//.test(body), `${f}: sin CDN ni URL externas`);
    assert.ok(!body.includes(' style="') && !/<[a-z][^>]*\son[a-z]+=/i.test(body), `${f}: sin estilos ni manejadores en línea`);
  }
  const eng = readFileSync(path.join(dir, 'oficina_mixamo.js'), 'utf8');
  assert.ok(eng.includes("const MIX = ROOT + 'bar/';") && eng.includes("new URL('./', import.meta.url)"), 'Mixamo solo por la ruta con sesión (consola o visor firmado)');
  assert.ok(eng.includes('crossFadeTo') && eng.includes('document.hidden') && eng.includes('rev='), 'transiciones, pausa si no se ve y cambios incrementales');
  assert.ok(eng.includes('AMBIENTE') || readFileSync(path.join(dir, 'oficina_restaurante.js'), 'utf8').includes('AMBIENTE'), 'lo decorativo está marcado');
  assert.ok(!readdirSync(dir).some(f => /\.(fbx|glb)$/i.test(f)), 'ningún archivo de Mixamo junto al código');
});
