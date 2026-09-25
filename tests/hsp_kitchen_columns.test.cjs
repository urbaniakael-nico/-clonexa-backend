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

function context(columns = {}) {
  const ctx = vm.createContext({ Date, Math, Number, String, Array });
  const constStart = source.indexOf('\n  const COLUMNS = ');
  const constEnd = source.indexOf('];', constStart) + 2;
  vm.runInContext(
    `var state = { thresholds: { green_max_minutes: 10, yellow_max_minutes: 20 }, columns: ${JSON.stringify(columns)} };\n`
      + source.slice(constStart, constEnd).replace('const COLUMNS', 'var COLUMNS') + '\n'
      + ['h', 'minutesOpen', 'timerClass', 'itemLine', 'itemQuantity', 'deliveryTag', 'boardColumns', 'columnAction', 'columnCard', 'screenColumns'].map(fn).join('\n'),
    ctx,
  );
  return ctx;
}

const ago = (minutes) => new Date(Date.now() - minutes * 60000).toISOString();

test('each column lists the oldest comanda first', () => {
  const ctx = context();
  const cols = ctx.boardColumns({
    columns: {
      nuevo: [{ order_id: 'b', created_at: ago(2) }, { order_id: 'a', created_at: ago(9) }],
      preparando: [{ order_id: 'd', created_at: ago(1) }, { order_id: 'c', created_at: ago(20) }],
      listo: [{ order_id: 'f', created_at: ago(30), ready_at: ago(1) }, { order_id: 'e', created_at: ago(5), ready_at: ago(4) }],
    },
  });
  assert.deepEqual(cols.nuevo.map((c) => c.order_id), ['a', 'b']);
  assert.deepEqual(cols.preparando.map((c) => c.order_id), ['c', 'd']);
  assert.deepEqual(cols.listo.map((c) => c.order_id), ['e', 'f']);   // by when it became ready
});

test('boardColumns tolerates a board without columns (switch off)', () => {
  const ctx = context();
  const cols = ctx.boardColumns({ comandas: [] });
  assert.deepEqual([cols.nuevo.length, cols.preparando.length, cols.listo.length], [0, 0, 0]);
});

test('each column moves the comanda one step forward with its own button', () => {
  const ctx = context();
  assert.deepEqual([ctx.columnAction('nuevo').label, ctx.columnAction('nuevo').path], ['EMPEZAR', 'start']);
  assert.deepEqual([ctx.columnAction('preparando').label, ctx.columnAction('preparando').path], ['COMANDA LISTA', 'ready']);
  assert.deepEqual([ctx.columnAction('listo').label, ctx.columnAction('listo').path], ['ENTREGADO', 'delivered']);
});

test('the three columns render with their titles and counters', () => {
  const ctx = context({
    nuevo: [{ order_id: 'a', table_number: 'Mesa 1', created_at: ago(1), items: [] }],
    preparando: [],
    listo: [{ order_id: 'b', table_number: 'Mesa 2', created_at: ago(8), ready_at: ago(1), items: [] }, { order_id: 'c', table_number: 'Mesa 3', created_at: ago(8), ready_at: ago(1), items: [] }],
  });
  const html = ctx.screenColumns();
  assert.match(html, /Pedido nuevo <span class="ktc-count">1<\/span>/);
  assert.match(html, /Preparando <span class="ktc-count">0<\/span>/);
  assert.match(html, /Listo <span class="ktc-count">2<\/span>/);
  assert.match(html, /data-ktc-path="start"/);
  assert.match(html, /data-ktc-path="delivered"/);
});

test('COMANDA LISTA is always pressable in Preparando (no per-item gate)', () => {
  const ctx = context();
  const html = ctx.columnCard({ order_id: 'x', created_at: ago(3), items: [{ id: 'l1', name: 'Carne', quantity: 1, ready: false }] }, 'preparando');
  assert.match(html, /data-ktc-path="ready"/);
  assert.doesNotMatch(html, /data-ktc-advance="x" data-ktc-path="ready" disabled/);
});

test('a fraction line shows its label instead of a decimal quantity', () => {
  const ctx = context();
  assert.equal(ctx.itemQuantity({ quantity: 0.75, quantity_label: '3/4' }), '3/4');
  assert.equal(ctx.itemQuantity({ quantity: 2 }), '2×');
});
