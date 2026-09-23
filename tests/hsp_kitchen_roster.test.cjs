// Cocina "Registro entrada": one row per person assigned to the kitchen with
// Iniciar / Pausar / Salir turno, live worked time, escaped names.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/hsp_kitchen.js', 'utf8');

function fn(name) {
  const start = source.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

function context(roster = []) {
  const ctx = vm.createContext({ Date, Math, Number, String, Array });
  vm.runInContext(
    `var state = { roster: ${JSON.stringify(roster)} };\n`
      + ['h', 'rosterButtons', 'workedSeconds', 'formatWorked', 'screenRoster'].map(fn).join('\n'),
    ctx,
  );
  return ctx;
}

test('the buttons follow the person\'s state', () => {
  const ctx = context();
  assert.equal(JSON.stringify(ctx.rosterButtons({ state: 'off' })), '["iniciar"]');
  assert.equal(JSON.stringify(ctx.rosterButtons({ state: 'working' })), '["pausar","salir"]');
  assert.equal(JSON.stringify(ctx.rosterButtons({ state: 'on_break' })), '["iniciar","salir"]');
});

test('worked time keeps running while working and freezes on a pause', () => {
  const ctx = context();
  const serverTime = new Date('2026-09-23T12:00:00Z');
  const later = serverTime.getTime() + 10 * 60000;
  const session = { active_seconds: 3600, server_time: serverTime.toISOString() };
  assert.equal(ctx.formatWorked(ctx.workedSeconds({ state: 'working', session }, later)), '1h 10m');
  assert.equal(ctx.formatWorked(ctx.workedSeconds({ state: 'on_break', session }, later)), '1h 00m');
  assert.equal(ctx.workedSeconds({ state: 'off', session: null }, later), 0);
});

test('each person gets a row with their own buttons', () => {
  const ctx = context([
    { employee_id: 'e1', full_name: 'Ana Cocina', role: 'cocinera', state: 'working', session: { active_seconds: 60, server_time: new Date().toISOString() } },
    { employee_id: 'e2', full_name: 'Pedro <b>', role: 'parrillero', state: 'off', session: null },
  ]);
  const html = ctx.screenRoster();
  assert.match(html, /Ana Cocina/);
  assert.match(html, /data-ktc-roster="e1" data-ktc-roster-action="pausar"/);
  assert.match(html, /data-ktc-roster="e1" data-ktc-roster-action="salir"/);
  assert.match(html, /SALIR TURNO/);
  assert.match(html, /data-ktc-roster="e2" data-ktc-roster-action="iniciar"/);
  assert.doesNotMatch(html, /data-ktc-roster="e2" data-ktc-roster-action="pausar"/);
  assert.match(html, /Pedro &lt;b&gt;/);
  assert.match(html, /Trabajando/);
  assert.match(html, /Fuera de turno/);
});

test('an empty kitchen explains where people come from', () => {
  assert.match(context([]).screenRoster(), /No hay personas asignadas a cocina en Workforce/);
});
