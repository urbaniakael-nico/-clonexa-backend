const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const source = readFileSync('app/web/client.js', 'utf8');

function fn(name) {
  const start = source.search(new RegExp(`  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 2);
  const next = tail.search(/\n  (?:async )?function /);
  return next < 0 ? tail : tail.slice(0, next);
}

test('zero and small sales values are outside the variable-height fill', () => {
  const context = vm.createContext({ h: String, cxHspMoney024R: n => `$ ${n}` });
  vm.runInContext(fn('cxHspDashNum024W') + fn('cxHspDashRenderChart024W'), context);
  const html = context.cxHspDashRenderChart024W([
    { key: '2026-09-07', label: '07 sept', subtitle: '2026', total: 0, orders: 0 },
    { key: '2026-09-08', label: '08 sept', subtitle: '2026', total: 15000, orders: 1 },
    { key: '2026-09-09', label: '09 sept', subtitle: '2026', total: 3557000, orders: 10 },
  ]);
  for (const total of [0, 15000, 3557000]) {
    assert.ok(html.includes(`<strong class="hspdash-barvalue-033e">$ ${total}</strong>`));
  }
  assert.match(html, /height:0%" aria-hidden="true"><\/div>/);
  assert.doesNotMatch(html, /hspdash-bar-024w[^>]*>\$/);
});

test('monitor refreshes without overlap, resumes, preserves data on errors and stops after navigation', async () => {
  let tick, interval, pending, calls = 0, paints = 0, errorText = '', root = {}, hidden = false;
  const events = new Map();
  root.contains = () => false;
  const context = vm.createContext({
    state: { companyId: 'tenant' },
    document: {
      get hidden() { return hidden; }, activeElement: null,
      getElementById: () => root,
      addEventListener: (name, cb) => events.set(name, cb),
      removeEventListener: name => events.delete(name),
    },
    window: {
      setInterval: (cb, ms) => { tick = cb; interval = ms; return 1; }, clearInterval: () => {},
      addEventListener: (name, cb) => events.set(name, cb), removeEventListener: name => events.delete(name),
    },
    cxHspDashApi024W: async () => { calls++; return await new Promise((resolve, reject) => { pending = { resolve, reject }; }); },
    cxHspDashPaint024W: () => { paints++; }, cxHspDashStatus033E: value => { errorText = value || ''; },
  });
  vm.runInContext(`let cxHspDashLoading033E=false, cxHspDashAnalytics033E=null, cxHspDashEventDate033B='', cxHspDashEventTimezone033B='', cxHspDashPainted033E='', cxHspDashMonitor033E=null, cxHspDashResume033E=null;` +
    fn('cxHspDashLoad024W') + fn('cxHspDashStopMonitor033E') + fn('cxHspDashStartMonitor033E'), context);
  context.cxHspDashStartMonitor033E();
  assert.equal(interval, 10000);
  const first = tick();
  await tick();
  assert.equal(calls, 1);
  pending.resolve({ today: '2026-09-10', analytics: { days: {}, weeks: {}, months: {} } });
  await first;
  assert.equal(paints, 1);
  const failed = tick(); pending.reject(new Error('offline')); await failed;
  assert.equal(errorText, 'offline');
  assert.equal(vm.runInContext('cxHspDashAnalytics033E.today', context), '2026-09-10');
  hidden = true; await tick(); assert.equal(calls, 2);
  hidden = false;
  const resumed = events.get('visibilitychange')();
  pending.resolve({ today: '2026-09-11', analytics: { days: {}, weeks: {}, months: {} } }); await resumed;
  assert.equal(calls, 3);
  root = null; await tick();
  assert.equal(events.size, 0);
  assert.equal(vm.runInContext('cxHspDashMonitor033E', context), null);
});
