// Nómina v2 · payroll_shift_list: cada turno es una tarjeta (fecha y rango arriba;
// Pausas, Horas ordinarias, Horas extra y Referencias en filas) y al final una
// tarjeta de TOTAL que es la suma exacta de los turnos. Sin el interruptor, el
// desglose de siempre. Solo presentación: los números vienen del cálculo.
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { readFileSync } = require('node:fs');

const SRC = readFileSync('app/web/payroll_v2.js', 'utf8');
const CSS = readFileSync('app/web/payroll_v2.css', 'utf8');
const DICT = readFileSync('app/web/client_i18n_dict.js', 'utf8');

function load() {
  const window = {};
  vm.runInContext(SRC, vm.createContext({ window, document: {}, JSON, Object, Array, String, Number, Math, Date, Map, Set, Promise, Intl, encodeURIComponent }));
  return window.CxPayrollV2;
}

const SHIFTS = [
  { start: '2026-10-13T18:22:00Z', end: '2026-10-13T20:25:00Z', pause_minutes: 15, regular_minutes: 108, extra_minutes: 0, gross_amount: 18000 },
  { start: '2026-10-14T13:00:00Z', end: '2026-10-14T23:30:00Z', pause_minutes: 30, regular_minutes: 480, extra_minutes: 120, gross_amount: 95000 },
];
const CARD = { id: 'e1', name: 'Ana Ruiz', document: '123', closed: 2, regular: 588, extra: 120, gross: 113000, discount: 0, net: 113000, shifts: SHIFTS, pending: [] };
const ACTIVITY = (on) => ({
  modules: { references: true, gps: false, panels: false },
  references: { e1: [{ reference: 'PANT SET', start: '2026-10-13T18:30:00Z', end: '2026-10-13T20:00:00Z' }, { reference: 'Mystic jacket', start: '2026-10-14T14:00:00Z', end: '2026-10-14T20:00:00Z' }] },
  reference_closures: { e1: [{ reference: 'PANT SET', size: 'M', quantity: 10, at: '2026-10-14T15:00:00Z' }] },
  ...(on ? { ui: { shift_list: true } } : {}),
});

test('con el interruptor: tarjetas por turno con sus filas y TOTAL igual a la suma', () => {
  const P = load();
  P.model.activity = ACTIVITY(true);
  const html = P.detail(CARD);
  assert.equal((html.match(/class="pv-shift pv-scard"/g) || []).length, 2, 'una tarjeta por turno');
  assert.match(html, /<b>Mar, 13 oct<\/b> · 13:22 → 15:25|<b>Mar, 13 de oct<\/b> · 13:22 → 15:25/, 'fecha y rango en la zona de la empresa (Bogotá)');
  for (const label of ['Pausas', 'Horas ordinarias', 'Horas extra', 'Referencias']) assert.ok(html.includes(`<dt>${label}</dt>`), label);
  assert.match(html, /<dt>Horas ordinarias<\/dt><dd>1 h 48 min<\/dd>/);
  assert.match(html, /<dt>Referencias<\/dt><dd>PANT SET<\/dd>/);
  assert.match(html, /<dt>Referencias<\/dt><dd>Mystic jacket, PANT SET<\/dd>/);
  const t = P.shiftTotals(CARD);
  assert.equal(t.shifts, 2);
  assert.equal(t.regular, SHIFTS.reduce((s, x) => s + x.regular_minutes, 0));
  assert.equal(t.extra, SHIFTS.reduce((s, x) => s + x.extra_minutes, 0));
  assert.equal(t.regular, CARD.regular, 'coincide con lo que calculó la nómina');
  assert.equal(t.extra, CARD.extra);
  assert.match(html, /pv-scard-total[\s\S]*<dt>Turnos<\/dt><dd>2<\/dd>[\s\S]*<dt>Horas ordinarias<\/dt><dd>9 h 48 min<\/dd>[\s\S]*<dt>Horas extra<\/dt><dd>2 h 00 min<\/dd>[\s\S]*<dt>Referencias trabajadas<\/dt><dd>2 · PANT SET, Mystic jacket<\/dd>/);
});

test('sin el interruptor: el desglose de siempre', () => {
  const P = load();
  P.model.activity = ACTIVITY(false);
  const html = P.detail(CARD);
  assert.doesNotMatch(html, /pv-scard/);
  assert.match(html, /class="pv-shift-main"/);
});

test('estilos y textos', () => {
  assert.match(CSS, /\.pv-scard-rows > div \{ display: grid; grid-template-columns: minmax\(120px, 40%\) minmax\(0, 1fr\)/);
  assert.match(CSS, /@media \(max-width: 480px\)/);
  const w = {};
  vm.runInContext(DICT, vm.createContext({ window: w, Object }));
  for (const k of ['Pausas', 'Horas ordinarias', 'Horas extra', 'Referencias', 'TOTAL', 'Turnos', 'Referencias trabajadas']) {
    assert.ok(k in w.CX_I18N_DICT.en && k in w.CX_I18N_DICT.fr, k);
  }
});
