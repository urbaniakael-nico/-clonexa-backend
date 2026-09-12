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

test('zero and small sales values stay inside the yellow fill', () => {
  const context = vm.createContext({ h: String, cxHspMoney024R: n => `$ ${n}`, cxHspDashShiftRange033F: () => 'Jornada' });
  vm.runInContext(fn('cxHspDashNum024W') + fn('cxHspDashRenderChart024W'), context);
  const html = context.cxHspDashRenderChart024W([
    { key: '2026-09-07', label: '07 sept', subtitle: '2026', total: 0, orders: 0 },
    { key: '2026-09-08', label: '08 sept', subtitle: '2026', total: 15000, orders: 1 },
    { key: '2026-09-09', label: '09 sept', subtitle: '2026', total: 3557000, orders: 10 },
  ]);
  for (const total of [0, 15000, 3557000]) {
    assert.match(html, new RegExp(`<div class="hspdash-bar-024w" style="height:[^\"]+"><strong class="hspdash-barvalue-033e">\\$ ${total}</strong></div>`));
  }
  assert.match(source, /\.hspdash-bar-024w\{[^}]*min-height:32px/);
  assert.doesNotMatch(html, /aria-hidden="true"/);
});

test('shift caption displays both dates in company timezone and ongoing status', () => {
  const context = vm.createContext({cxHspDashEventTimezone033B: 'America/Bogota'});
  vm.runInContext(fn('cxHspDashDate024W') + fn('cxHspDashShiftRange033F'), context);
  const shifts = [{opened_at:'2026-09-07T23:00:00Z', closed_at:'2026-09-08T09:00:00Z'}];
  assert.match(context.cxHspDashShiftRange033F({shifts}), /0?7\/0?9.*18:00.*0?8\/0?9.*04:00/);
  shifts[0].is_open = true;
  assert.match(context.cxHspDashShiftRange033F({shifts}), /0?7\/0?9.*18:00.*En curso/);
  assert.equal(context.cxHspDashShiftRange033F({}), 'Sin jornada registrada');
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
  vm.runInContext(`let cxHspDashPending033G=null, cxHspDashEvents033B=[], cxHspDashEventSummary033B={}, cxHspDashEventError033B="", cxHspDashLoading033E=false, cxHspDashAnalytics033E=null, cxHspDashEventDate033B='', cxHspDashEventTimezone033B='', cxHspDashPainted033E='', cxHspDashMonitor033E=null, cxHspDashResume033E=null;` +
    fn('cxHspDashLoad024W') + fn('cxHspDashStopMonitor033E') + fn('cxHspDashStartMonitor033E'), context);
  context.cxHspDashStartMonitor033E();
  assert.equal(interval, 10000);
  const first = tick();
  await tick();
  assert.equal(calls, 1);
  pending.resolve({ today: '2026-09-10', analytics: { days: {}, weeks: {}, months: {} }, event_search: {date:'2026-09-10', events:[], summary:{reconciled:true}} });
  await first;
  assert.equal(paints, 1);
  const failed = tick(); pending.reject(new Error('offline')); await failed;
  assert.equal(errorText, 'offline');
  assert.equal(vm.runInContext('cxHspDashAnalytics033E.today', context), '2026-09-10');
  hidden = true; await tick(); assert.equal(calls, 2);
  hidden = false;
  const resumed = events.get('visibilitychange')();
  pending.resolve({ today: '2026-09-11', analytics: { days: {}, weeks: {}, months: {} }, event_search: {date:'2026-09-10', events:[], summary:{reconciled:true}} }); await resumed;
  assert.equal(calls, 3);
  root = null; await tick();
  assert.equal(events.size, 0);
  assert.equal(vm.runInContext('cxHspDashMonitor033E', context), null);
});

test('changing the search date discards the old response and replaces every panel together', async () => {
  const requests = [];
  const context = vm.createContext({
    state: {companyId:'tenant'},
    cxHspDashApi024W: url => new Promise(resolve => requests.push({url, resolve})),
  });
  vm.runInContext(`let cxHspDashPending033G=null, cxHspDashLoading033E=false, cxHspDashAnalytics033E=null,
    cxHspDashEventDate033B='2026-09-09', cxHspDashEvents033B=[], cxHspDashEventSummary033B={},
    cxHspDashEventTimezone033B='', cxHspDashEventLoading033B=false, cxHspDashEventError033B='';` +
    fn('cxHspDashLoad024W') + fn('cxHspDashLoadEvents033B'), context);
  const snapshot = (date, total) => ({today:'2026-09-11', analytics:{days:{total}, weeks:{}, months:{}},
    event_search:{date, events:[{total}], summary:{total, reconciled:true}}});
  const old = context.cxHspDashLoad024W();
  const search = context.cxHspDashLoadEvents033B('2026-09-10');
  assert.equal(requests.length, 1);
  requests[0].resolve(snapshot('2026-09-09', 100));
  await old;
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(requests.length, 2);
  assert.match(requests[1].url, /event_date=2026-09-10/);
  assert.equal(vm.runInContext('cxHspDashAnalytics033E', context), null);
  requests[1].resolve(snapshot('2026-09-10', 251000));
  await search;
  assert.equal(vm.runInContext('cxHspDashAnalytics033E.analytics.days.total', context), 251000);
  assert.equal(vm.runInContext('cxHspDashEventSummary033B.total', context), 251000);
  assert.equal(vm.runInContext('cxHspDashEvents033B[0].total', context), 251000);
});

test('shared QR table keeps same-name device accounts and their products separate', () => {
  const context = vm.createContext({});
  vm.runInContext(
    fn('cxHspPaymentLabel024V') +
    fn('cxHspPaymentMethod024V') +
    fn('cxHspNormKey024Y') +
    fn('cxHspTableKey024Y') +
    fn('cxHspItemKey024Y') +
    fn('cxHspItemSubtotal024Y') +
    fn('cxHspGroupAccounts024Y') +
    fn('cxHspMergedTableCards024Y'),
    context,
  );
  const orders = [
    {
      id: 'o1', table_number: 'Mesa 3', status: 'entregado', total: 5000, order_number: 'QR-1',
      people: [{ account_id: 'phone-a', customer_key: 'alex', name: 'Alex', total: 5000,
        items: [{ product_id: 'aguila', name: 'Aguila', quantity: 1, unit_price: 5000, subtotal: 5000 }] }],
      items: [{ product_id: 'aguila', name: 'Aguila', quantity: 1, unit_price: 5000, subtotal: 5000 }],
    },
    {
      id: 'o2', table_number: 'Mesa 3', status: 'entregado', total: 10000, order_number: 'QR-2',
      people: [{ account_id: 'phone-a', customer_key: 'alex', name: 'Alex', total: 10000,
        items: [{ product_id: 'aguila', name: 'Aguila', quantity: 2, unit_price: 5000, subtotal: 10000 }] }],
      items: [{ product_id: 'aguila', name: 'Aguila', quantity: 2, unit_price: 5000, subtotal: 10000 }],
    },
    {
      id: 'o3', table_number: 'Mesa 3', status: 'entregado', total: 20000, order_number: 'QR-3',
      people: [{ account_id: 'phone-b', customer_key: 'alex', name: 'Alex', total: 20000,
        items: [{ product_id: 'stella', name: 'Stella', quantity: 2, unit_price: 10000, subtotal: 20000 }] }],
      items: [{ product_id: 'stella', name: 'Stella', quantity: 2, unit_price: 10000, subtotal: 20000 }],
    },
  ];
  const merged = context.cxHspMergedTableCards024Y(orders)[0];
  assert.equal(merged.total, 35000);
  assert.equal(merged.people_summary.length, 2);
  const phoneA = merged.people_summary.find(person => person.account_id === 'phone-a');
  const phoneB = merged.people_summary.find(person => person.account_id === 'phone-b');
  assert.equal(phoneA.total, 15000);
  assert.equal(phoneA.orders, 2);
  assert.equal(phoneA.items.length, 1);
  assert.equal(phoneA.items[0].name, 'Aguila');
  assert.equal(phoneA.items[0].quantity, 3);
  assert.equal(phoneB.total, 20000);
  assert.equal(phoneB.items[0].name, 'Stella');
});
