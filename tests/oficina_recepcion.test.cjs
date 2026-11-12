// Oficina 3D · RECEPCIÓN con Nexa: reglas puras con datos simulados (cada estado -> posición, animación y color),
// +N con más de 8, sin datos, enlace al tocar, Nexa Talking/Idle, el flujo n8n "Oficina - Estado" sin datos
// personales y el código de producción sin datos de ejemplo de la referencia (Kennedy, Techo, Castilla, Timiza...).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { pathToFileURL } = require('node:url');

const load = () => import(pathToFileURL(path.resolve('app/web/oficina/oficina_pisos_rules.js')).href);
const src = f => readFileSync(f, 'utf8').replace(/\r\n/g, '\n');
const v = (id, state, extra = {}) => ({ id, state, tag: { head: 'Restaurante · Suba', small: 'Precio · WhatsApp' }, ...extra });

test('cada estado va a su lugar con su animación y su color', async () => {
  const P = await load(); const R = P.RECEPCION;
  const plan = P.receptionPlan([v('t', 'talking'), v('n', 'new'), v('w', 'waiting'), v('d', 'demo'), v('i', 'idle')]);
  const by = Object.fromEntries(plan.map(p => [p.id, p]));
  assert.deepEqual([by.t.clip, by.t.arrive, by.t.cls], ['Talking', false, 'lead']); assert.ok(R.COUNTER.includes(by.t.spot), 'hablando: en el mostrador');
  assert.deepEqual([by.n.clip, by.n.arrive], ['Talking', true], 'recién llegado: entra caminando y va al mostrador'); assert.ok(R.COUNTER.includes(by.n.spot));
  assert.deepEqual([by.w.clip, by.w.seated, by.w.color], ['Sitting', true, '#f59e0b'], 'en espera: sentado, naranja'); assert.ok(R.SEATS.includes(by.w.spot));
  assert.deepEqual([by.d.clip, by.d.color, by.d.cls], ['Sitting', '#a855f7', 'demo'], 'demo: morado');
  assert.deepEqual([by.i.clip, by.i.color, by.i.cls], ['Idle', '#94a3b8', 'gris'], 'sin respuesta: gris, de pie'); assert.ok(R.ENTRANCE.includes(by.i.spot), 'cerca de la entrada');
  // la sala de espera tiene 4 puestos: el resto de pie al lado
  const many = P.receptionPlan(['a', 'b', 'c', 'd', 'e', 'f'].map(id => v(id, 'waiting')));
  assert.equal(many.filter(p => p.seated).length, 4); assert.equal(many.filter(p => !p.seated).length, 2);
  // las puertas, el mostrador y los asientos están dentro del salón
  for (const [x, z] of [...R.COUNTER, ...R.SEATS, ...R.STAND, ...R.ENTRANCE, R.NEXA, R.DOOR]) assert.ok(Math.abs(x) < R.ROOM.W / 2 && Math.abs(z) < R.ROOM.D / 2 + 1, `${x},${z}`);
});

test('máximo 8 visibles; la pantalla muestra filas y "+N"; sin datos "Sin visitas hoy"', async () => {
  const P = await load();
  const ten = Array.from({ length: 10 }, (_, i) => v('v' + i, 'idle'));
  assert.equal(P.receptionPlan(ten).length, 8);
  const scr = P.receptionScreen({ screen: ten.slice(0, 8).map(() => ({ a: 'Bar', b: 'Precio · Correo', state: 'En espera', color: '#f59e0b' })), interesados: 10 });
  assert.equal(scr.rows.length, 6); assert.equal(scr.more, 4, '10 interesados, 6 filas en pantalla -> +4'); assert.equal(scr.empty, false);
  const none = P.receptionScreen({ screen: [], interesados: 0, empty: true });
  assert.deepEqual([none.rows.length, none.more, none.empty, none.title], [0, 0, true, 'Recepción · interesados de hoy']);
  assert.deepEqual(P.nexaTag({ nexa: { state: 'idle', text: 'Esperando visitas' } }), { clip: 'Idle', cls: 'nodata', text: 'Nexa · Recepción', small: 'Esperando visitas' });
  assert.deepEqual(P.nexaTag({ nexa: { state: 'talking', text: 'Atendiendo: carta video' } }).clip, 'Talking');
  assert.deepEqual(P.receptionDiff(new Set(['a', 'b']), [v('b', 'idle'), v('c', 'new')]), { enter: ['c'], leave: ['a'] });
});

test('tocar un visitante: su conversación en Conversaciones Nexa o el prospecto en el Mapa comercial', async () => {
  const P = await load(); const id = '0f8fad5b-d9cb-469f-a165-70867728950e';
  assert.equal(P.visitorLink({ link: { type: 'nexa', id } }), `/admin-v2plus#nexa/${id}`);
  assert.equal(P.visitorLink({ link: { type: 'mapa', id } }), `/admin-v2plus#mapa/${id}`);
  assert.equal(P.visitorLink({ link: null }), null, 'Leads DEMO / correos: sin enlace');
  assert.equal(P.visitorLink({ link: { type: 'nexa', id: 'javascript:alert(1)' } }), null);
  const console = src('app/web/admin_v2plus.js');
  assert.match(console, /#mapa\\\/\(\[0-9a-fA-F-\]\{36\}\)/, 'la consola abre #mapa/{prospecto}');
  assert.match(src('app/web/admin_v2plus_mapa.js'), /if \(model\.openId\) \{ const id = model\.openId; model\.openId = ""; openDetail\(id\); \}/);
  const app = src('app/web/oficina/oficina_app.js');
  assert.match(app, /kind === 'visitante' \? showVisitor\(info\)/);
  assert.match(app, /window\.open\(link, '_blank', 'noopener'\)/);
  assert.match(app, /p === lobby && rcApproved\(\)/, 'la planta baja abre la recepción solo con el interruptor');
  assert.match(app, /import\('\/admin-v2plus\/oficina\/recepcion\.js'\)/);
});

test('Nexa recepcionista: mujer, túnica negra con líneas rosadas, Talking/Idle; visitantes sin datos personales', async () => {
  const P = await load();
  const rec = src('app/web/oficina/oficina_recepcion.js');
  assert.match(rec, /model: 'Ch07_nonPBR', gender: 'mujer', tunic: true, lines: 0xf20b6d/);
  assert.match(rec, /liveUrl: `\$\{API\}\/recepcion\/vivo`/);
  assert.match(rec, /'Sin visitas hoy'/);
  assert.doesNotMatch(rec, /Math\.random/, 'nada al azar');
  assert.doesNotMatch(rec, /style="/, 'sin estilos en línea (CSP)');
  assert.ok(!P.CHARACTERS.filter(m => m !== 'Ch17_nonPBR').includes(undefined));
  const ids = ['a1', 'b2', 'c3', 'd4', 'e5'];
  assert.deepEqual(ids.map(P.visitorModel), ids.map(P.visitorModel), 'personaje estable por visitante');
  assert.ok(ids.every(id => P.visitorModel(id) !== 'Ch17_nonPBR'));
  for (const f of ['app/web/oficina/oficina_recepcion.js', 'app/web/oficina/oficina_pisos_rules.js', 'app/services/oficina_recepcion.py']) {
    const s = src(f);
    for (const sample of ['Kennedy', 'Quiero la carta video', 'Techo', 'Castilla', 'Timiza']) assert.ok(!s.includes(sample), `${f}: dato de ejemplo "${sample}"`);
  }
  const css = src('app/web/oficina/oficina.css');
  for (const c of ['i.lead{background:#f20b6d}', 'i.espera{background:#f59e0b}', 'i.demo{background:#a855f7}', 'i.gris{background:#94a3b8}']) assert.ok(css.includes(c), c);
});

test('flujo n8n "Oficina - Estado": Leads DEMO y Correos de hoy sin usuario, nombre, correo ni texto', () => {
  const py = src('ops/n8n/oficina_estado_flow.py');
  const armar = py.slice(py.indexOf('ARMAR = r"""') + 'ARMAR = r"""'.length, py.indexOf('"""', py.indexOf('ARMAR = r"""') + 12));
  const now = Date.now(), iso = m => new Date(now - m * 60000).toISOString();
  const data = {
    'Flujos': { data: [
      { name: 'Nexa - Leads DEMO', staticData: { global: { leads: [
        { fecha: iso(5), red: 'instagram', usuario: '@maria_lopez', texto: 'Precio y demo? mi cel 3001234567', post: 'https://x', estado: 'nuevo' },
        { fecha: iso(60 * 30), red: 'facebook', usuario: 'Pedro Pérez', texto: 'info', estado: 'nuevo' }] } } },
      { name: 'Nexa - Correos', staticData: JSON.stringify({ global: { borradores: {
        m1: { de: 'ana@empresa.co', nombre: 'Ana Ruiz', asunto: 'Carta en video', resumen: 'Quiere la carta digital', cuerpo: 'Hola soy Ana', tipo: 'cliente potencial', estado: 'pendiente', fecha: iso(30) },
        m2: { de: 'socio@aliado.co', nombre: 'Socio', asunto: 'Alianza', resumen: 'aliado', tipo: 'aliado', estado: 'pendiente', fecha: iso(20) } } } }) }] },
    'Lista de flujos': [], 'Ejecuciones': [], 'Corriendo': { data: [] }, 'Calendario': {}, 'Ideas': {}, 'Reporte semanal': {},
  };
  const $ = name => ({ first: () => ({ json: data[name] || {} }), all: () => (Array.isArray(data[name]) ? data[name] : []).map(json => ({ json })) });
  const ctx = vm.createContext({ $, Date, JSON, Object, Array, String, Set, Math });
  const out = vm.runInContext(`(function(){${armar}})()`, ctx)[0].json.reception;
  const r = JSON.parse(JSON.stringify(out));
  assert.equal(r.ok, true);
  assert.deepEqual(JSON.stringify(r.leads.map(l => [l.channel, l.state, l.topics])), JSON.stringify([['instagram', 'nuevo', ['precio', 'demo']]]), 'solo las últimas 24 h');
  assert.deepEqual(r.mail.map(m => [m.channel, m.state, m.topics]), [['correo', 'pendiente', ['carta_video']]], 'solo clientes potenciales');
  const blob = JSON.stringify(r);
  for (const bad of ['maria', '3001234567', 'Pedro', 'ana@', 'Ana Ruiz', 'Hola soy', 'Quiere la carta', 'socio@', 'https://x']) assert.ok(!blob.includes(bad), bad);
});

test('etiquetas sin taparse: la que choca sube; las zonas no se mueven', async () => {
  const P = await load();
  const placed = [];
  assert.equal(P.declutter(placed, 500, 300, 200, 24, false), 300, 'zona fija');
  const y2 = P.declutter(placed, 520, 300, 200, 24);
  assert.ok(y2 <= 300 - 24 - 2, `sube por encima de la otra (${y2})`);
  assert.equal(P.declutter(placed, 1200, 300, 200, 24), 300, 'lejos: no se mueve');
  assert.equal(placed.length, 3);
  assert.match(src('app/web/oficina/oficina_mixamo.js'), /P\.declutter\(placed, x,/);
});
