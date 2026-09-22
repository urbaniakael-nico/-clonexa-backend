const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/client.js', 'utf8');

function fn(name) {
  const start = source.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

const NAMES = [
  'cxIsHospitalityQrCode024S', 'cxHspQrClamp025N', 'cxHspQrCleanBase025N',
  'cxHspQrConfigFromModules025N', 'cxHspOrdersBoardMode034D',
  'cxHspTablesBoardSection034D', 'cxHspKanbanBoardSection034D', 'cxHspOrdersBoardSection034D',
];

// Only the switch/board-selection functions above are exercised here; they are
// pure functions of `modules`, so a stub activeClientModules() is enough — no
// need to drag in the whole company-modules state machine.
function board(modules) {
  const context = vm.createContext({
    window: { location: { origin: 'https://panel.clonexa.test' } },
    Intl, Date, Math, Number, String, Array, Map, Set, JSON,
  });
  vm.runInContext(
    `function activeClientModules() { return ${JSON.stringify(modules)}; }\n`
      + NAMES.map(fn).join('\n'),
    context,
  );
  return context;
}

function qrModule(settings) {
  return { code: 'qr', enabled: true, settings };
}

test('a company with no orders_board setting keeps the kanban board (off by default)', () => {
  const ctx = board([qrModule({ qr_config: { mode: 'hospitality', max_capacity: 12 } })]);
  const config = ctx.cxHspQrConfigFromModules025N();
  assert.equal(config.ordersBoard, 'kanban');
  assert.equal(ctx.cxHspOrdersBoardMode034D(), 'kanban');
});

test('a company with no qr module at all also defaults to kanban', () => {
  const ctx = board([]);
  assert.equal(ctx.cxHspOrdersBoardMode034D(), 'kanban');
});

test('orders_board: "mesas" switches only that company to the table board', () => {
  const ctx = board([qrModule({ qr_config: { mode: 'hospitality', orders_board: 'mesas' } })]);
  const config = ctx.cxHspQrConfigFromModules025N();
  assert.equal(config.ordersBoard, 'mesas');
  assert.equal(ctx.cxHspOrdersBoardMode034D(), 'mesas');
});

test('an unrecognized orders_board value falls back to kanban instead of breaking the board', () => {
  const ctx = board([qrModule({ qr_config: { orders_board: 'algo-raro' } })]);
  assert.equal(ctx.cxHspOrdersBoardMode034D(), 'kanban');
});

test('the rendered section markup matches the resolved mode', () => {
  const kanban = board([qrModule({ qr_config: {} })]);
  const kanbanHtml = kanban.cxHspOrdersBoardSection034D();
  assert.match(kanbanHtml, /class="hsp-kanban-024r"/);
  assert.match(kanbanHtml, /id="hspPending024R"/);
  assert.doesNotMatch(kanbanHtml, /hspTablesGrid034B/);

  const mesas = board([qrModule({ qr_config: { orders_board: 'mesas' } })]);
  const mesasHtml = mesas.cxHspOrdersBoardSection034D();
  assert.match(mesasHtml, /hsp-tables-board-034b/);
  assert.match(mesasHtml, /id="hspTablesGrid034B"/);
  assert.doesNotMatch(mesasHtml, /id="hspPending024R"/);
});
