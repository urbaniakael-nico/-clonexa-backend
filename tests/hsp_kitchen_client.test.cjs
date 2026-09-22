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

function context(thresholds = { green_max_minutes: 10, yellow_max_minutes: 20 }) {
  const ctx = vm.createContext({ Date, Math, Number });
  vm.runInContext(
    `var state = { thresholds: ${JSON.stringify(thresholds)} };\n` + fn('minutesOpen') + '\n' + fn('timerClass'),
    ctx,
  );
  return ctx;
}

test('an order just created is under the green threshold', () => {
  const ctx = context();
  const createdAt = new Date(Date.now() - 2 * 60000).toISOString();
  assert.equal(ctx.timerClass(ctx.minutesOpen(createdAt)), 'ktc-timer-green');
});

test('an order between the green and yellow thresholds is yellow', () => {
  const ctx = context();
  const createdAt = new Date(Date.now() - 15 * 60000).toISOString();
  assert.equal(ctx.timerClass(ctx.minutesOpen(createdAt)), 'ktc-timer-yellow');
});

test('an order past the yellow threshold is red', () => {
  const ctx = context();
  const createdAt = new Date(Date.now() - 25 * 60000).toISOString();
  assert.equal(ctx.timerClass(ctx.minutesOpen(createdAt)), 'ktc-timer-red');
});

test('the thresholds are configurable per company', () => {
  const ctx = context({ green_max_minutes: 2, yellow_max_minutes: 5 });
  const createdAt = new Date(Date.now() - 3 * 60000).toISOString();
  assert.equal(ctx.timerClass(ctx.minutesOpen(createdAt)), 'ktc-timer-yellow');
});

test('minutesOpen tolerates a missing/invalid created_at instead of throwing', () => {
  const ctx = context();
  assert.equal(ctx.minutesOpen(''), 0);
  assert.equal(ctx.minutesOpen(undefined), 0);
});
