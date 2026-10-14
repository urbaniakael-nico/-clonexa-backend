// Recordatorio de pago en el panel principal: textos (es/en/fr), estados
// (en ventana, vencido, saldo parcial), montos COP/USD, "Ya pagué" y que
// NUNCA habla de suspensión. Solo se carga en el panel principal.
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { readFileSync } = require('node:fs');

const SRC = readFileSync('app/web/billing_reminder.js', 'utf8');

function load() {
  const window = {};
  vm.runInContext(SRC, vm.createContext({ window, Intl, Date, Number, String, Object, Math, JSON, RegExp }));
  return window.CxBillingReminder;
}

const STATE = { company_name: 'Bar Demo', period: '2026-10-01', amount: 220000, balance: 220000, currency: 'COP', due_date: '2026-10-20', state: 'open', partial: false };

test('en ventana: saludo, mes, monto y fecha límite', () => {
  const R = load();
  const m = R.message(STATE, 'es');
  assert.equal(m.hello, 'Hola, Bar Demo 👋');
  assert.equal(m.body, 'Tu mensualidad de octubre de 2026 por $220.000 COP está disponible para pago. Fecha límite: 20 de octubre.');
});

test('vencido: cambia el texto, amable, desde el día siguiente a la fecha límite', () => {
  const R = load();
  const m = R.message({ ...STATE, state: 'overdue' }, 'es');
  assert.match(m.body, /^Tu pago de octubre de 2026 está vencido desde el 21 de octubre\./);
  const p = R.message({ ...STATE, state: 'overdue', partial: true, balance: 20000 }, 'es');
  assert.match(p.body, /Saldo pendiente: \$20\.000 COP/);
});

test('pago parcial muestra el saldo; USD con su formato', () => {
  const R = load();
  assert.match(R.message({ ...STATE, partial: true, balance: 150000 }, 'es').body, /saldo de \$150\.000 COP/);
  assert.equal(R.money(1250.5, 'USD'), 'US$1,250.50');
  assert.match(R.message({ ...STATE, currency: 'USD', amount: 1250.5, balance: 1250.5 }, 'en').body, /US\$1,250\.50/);
});

test('es, en y fr: todas las frases traducidas y ninguna habla de suspender o bloquear', () => {
  const R = load();
  const all = [...Object.keys(R.TEXTS.en), ...Object.values(R.TEXTS.en), ...Object.values(R.TEXTS.fr)];
  assert.deepEqual(Object.keys(R.TEXTS.en).sort(), Object.keys(R.TEXTS.fr).sort());
  for (const text of all) assert.doesNotMatch(text, /suspend|suspens|bloque|block|cort[ae]|coupé|désactiv/i, text);
  assert.doesNotMatch(SRC.replace(/\/\/.*$/gm, ''), /suspend|bloque/i, 'ni en el código que arma el emergente');
  for (const l of ['es', 'en', 'fr']) {
    for (const st of [STATE, { ...STATE, state: 'overdue' }, { ...STATE, partial: true }, { ...STATE, state: 'overdue', partial: true }]) {
      const m = R.message(st, l);
      assert.ok(m.body && !/\{\w+\}/.test(m.body), `${l}: ${m.body}`);
    }
  }
  assert.match(R.message({ ...STATE, state: 'overdue' }, 'fr').body, /en retard depuis le 21 octobre/);
});

test('tarjeta: logo de Clonexa, QR, "Ya pagué" y "Recordar luego"; el formulario acepta imagen o PDF', () => {
  const R = load();
  const main = R.cardHtml(STATE, 'main', 'es', 'blob:qr', '', false);
  assert.match(main, /clonexa-icono\.svg\?v=cx26a/);
  assert.match(main, /src="blob:qr"/);
  assert.match(main, /data-cxbr-paid>Ya pagué/);
  assert.match(main, /data-cxbr-close>Recordar luego/);
  const up = R.cardHtml(STATE, 'upload', 'es', '', '', false);
  assert.match(up, /accept="image\/png,image\/jpeg,image\/webp,application\/pdf"/);
  assert.match(up, /máx\. 5 MB/);
  assert.match(up, /Monto pagado \(opcional\)/);
  const done = R.cardHtml(STATE, 'done', 'en', '', '', false);
  assert.match(done, /Thank you!/);
  const esc = R.cardHtml({ ...STATE, company_name: '<b>x</b>' }, 'main', 'es', '', '', false);
  assert.doesNotMatch(esc, /<b>x<\/b>/, 'escapa el nombre');
});

test('solo se carga en el panel principal, nunca en mini paneles', () => {
  assert.match(readFileSync('app/web/client.html', 'utf8'), /billing_reminder\.js\?v=/);
  for (const page of ['mini_panel.html', 'hsp_cashier.html', 'hsp_kitchen.html', 'hsp_waiter.html', 'hospitality_order.html', 'login.html']) {
    assert.doesNotMatch(readFileSync(`app/web/${page}`, 'utf8'), /billing_reminder/, page);
  }
});
