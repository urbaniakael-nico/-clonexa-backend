const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/hospitality_order.js', 'utf8');

function fn(name) {
  const start = source.search(new RegExp(`  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 2);
  const next = tail.search(/\n  (?:async )?function /);
  return next < 0 ? tail : tail.slice(0, next);
}

test('one phone keeps one account during the activation and a new activation gets another', () => {
  const storage = new Map();
  let sequence = 0;
  const localStorage = {
    getItem: key => storage.get(key) || null,
    setItem: (key, value) => storage.set(key, String(value)),
  };
  const context = vm.createContext({
    state: {
      companyId: 'tenant-1', table: 'Mesa 3',
      access: { code: 'ABCDE' }, accountId: '', accountScope: '',
    },
    window: { localStorage, sessionStorage: localStorage },
    crypto: { randomUUID: () => `00000000-0000-4000-8000-${String(++sequence).padStart(12, '0')}` },
  });
  vm.runInContext(
    fn('normalizeText') +
    fn('accessStorageKey') +
    fn('storedAccessCode') +
    fn('accountIdentityStorageKey') +
    fn('tableCustomerAccountId'),
    context,
  );

  const first = context.tableCustomerAccountId();
  assert.equal(context.tableCustomerAccountId(), first);
  context.state.access.code = 'FGHIJ';
  const second = context.tableCustomerAccountId();
  assert.notEqual(second, first);
  assert.match(first, /^qr_account_/);
  assert.equal(storage.size, 2);
});

test('mobile breakdown renders each person with only their products and marks this phone', () => {
  const context = vm.createContext({
    state: {
      tableAccount: {
        accounts: [
          { name: 'Persona 1', total: 15000, orders_count: 2, is_current: true,
            items: [{ name: 'Aguila', quantity: 3, unit_price: 5000, subtotal: 15000 }] },
          { name: 'Persona 2', total: 20000, orders_count: 1, is_current: false,
            items: [{ name: 'Stella', quantity: 2, unit_price: 10000, subtotal: 20000 }] },
        ],
      },
    },
    h: String,
    money: value => `$ ${Number(value)}`,
  });
  vm.runInContext(fn('tableAccountProductRows') + fn('tableAccountItemsHtml'), context);
  const html = context.tableAccountItemsHtml();

  assert.equal((html.match(/<section class="qr-person-account/g) || []).length, 2);
  assert.match(html, /Persona 1[\s\S]*Tu cuenta[\s\S]*Aguila/);
  assert.match(html, /Persona 2[\s\S]*Stella/);
  assert.doesNotMatch(html, /Persona 1[\s\S]*Stella[\s\S]*Persona 2/);
});
