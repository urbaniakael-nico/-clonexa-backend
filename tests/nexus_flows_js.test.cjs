// NEXUS: el código de los nodos de n8n (ops/n8n/nexus_flows.py) se ejecuta aquí sin la clave de n8n.
// - "Leer" (NEXUS - Comandos): solo el chat del dueño; botones rx:<estado>:<id>; /radar <tema>, /ideas, /backlog, /ayuda.
// - "Opciones" (NEXUS - Radar): lunes = semanal; consola y /radar = a pedido.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');

const SRC = readFileSync('ops/n8n/nexus_flows.py', 'utf8');
const pyString = (name) => {
  const m = new RegExp(`${name} = """([\\s\\S]*?)"""`).exec(SRC);
  assert.ok(m, name);
  return m[1].replace(/\\\\/g, '\\');
};
const DUENO = '5126243056';
const LEER = pyString('LEER_JS').replace('__CHAT__', DUENO);
const OPC = pyString('OPCIONES_JS');
const run = (code, json) => new Function('$json', code)(json)[0].json;

test('Leer: solo el chat del dueño; cualquier otro queda ignorado', () => {
  const mine = run(LEER, { message: { chat: { id: Number(DUENO), type: 'private' }, text: '/ideas' } });
  assert.equal(mine.ok, true); assert.equal(mine.tipo, 'ideas');
  const other = run(LEER, { message: { chat: { id: 999, type: 'private' }, text: '/ideas' } });
  assert.equal(other.ok, false);
  const group = run(LEER, { message: { chat: { id: Number(DUENO), type: 'group' }, text: '/ideas' } });
  assert.equal(group.ok, false, 'un grupo con el mismo id no cuenta');
  const fake = run(LEER, { callback_query: { id: 'q', data: 'rx:backlog:7', from: { id: 1 }, message: { message_id: 3, chat: { id: Number(DUENO) } } } });
  assert.equal(fake.ok, false, 'botón tocado por otra persona');
});

test('Leer: comandos y botones', () => {
  const r = run(LEER, { message: { chat: { id: Number(DUENO), type: 'private' }, text: '/radar fondos para startups de software en Colombia' } });
  assert.equal(r.tipo, 'radar'); assert.equal(r.tema, 'fondos para startups de software en Colombia');
  assert.equal(run(LEER, { message: { chat: { id: Number(DUENO), type: 'private' }, text: '/backlog@NexusBot' } }).tipo, 'backlog');
  assert.equal(run(LEER, { message: { chat: { id: Number(DUENO), type: 'private' }, text: '/ayuda' } }).tipo, 'ayuda');
  assert.equal(run(LEER, { message: { chat: { id: Number(DUENO), type: 'private' }, text: 'hola' } }).tipo, 'ayuda');
  const b = run(LEER, { callback_query: { id: 'q1', data: 'rx:me_interesa:42', from: { id: Number(DUENO) }, message: { message_id: 9, chat: { id: Number(DUENO) } } } });
  assert.deepEqual([b.tipo, b.ok, b.estado, b.id, b.msg_id, b.cb_id], ['boton', true, 'me_interesa', 42, 9, 'q1']);
});

test('Opciones: semanal el lunes; a pedido desde la consola y desde /radar', () => {
  assert.deepEqual(run(OPC, { timestamp: 'x' }), { tipo: 'semanal', tema: '', origen: 'cron' });
  assert.deepEqual(run(OPC, { body: { tema: 'pagos', origen: 'consola' } }), { tipo: 'a_pedido', tema: 'pagos', origen: 'consola' });
  assert.deepEqual(run(OPC, { tema: 'fondos', origen: 'telegram' }), { tipo: 'a_pedido', tema: 'fondos', origen: 'telegram' });
});

test('el flujo del Radar no guarda ejecuciones exitosas y usa la búsqueda web vía backend', () => {
  assert.match(SRC, /saveDataSuccessExecution": "none"/);
  assert.match(SRC, /anthropic-beta": "server-side-fallback-2026-07-01"/);
  assert.doesNotMatch(SRC, /\d{8,}:[A-Za-z0-9_-]{30,}/, 'ningún token de bot en el repo');
});
