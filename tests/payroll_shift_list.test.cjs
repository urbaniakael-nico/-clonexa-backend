// Nómina v2 · payroll_shift_list (056J): dentro de la tarjeta del colaborador, una
// TABLA compacta: encabezado con avatar, nombre, rol y documento (a la derecha valor
// total y número de turnos); columnas Fecha | Horario | Horas | Referencias | Valor;
// "+X h YY ext" solo si hay extra; pausas solo en el detalle al tocar la fila; última
// fila TOTAL. Sin el interruptor, el desglose de siempre. Solo presentación: los
// números vienen del cálculo y el TOTAL es la suma exacta de los turnos.
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
  { start: '2026-10-14T13:00:00Z', end: '2026-10-14T23:30:00Z', pause_minutes: 30, regular_minutes: 480, extra_minutes: 121, gross_amount: 95000 },
];
const CARD = { id: 'e1', name: 'Ana Ruiz', role: 'Operaria', document: '123', closed: 2, regular: 588, extra: 121, gross: 113000, discount: 0, net: 113000, shifts: SHIFTS, pending: [] };
const ACTIVITY = (on) => ({
  modules: { references: true, gps: false, panels: false },
  references: { e1: [{ reference: 'PANT SET', start: '2026-10-13T18:30:00Z', end: '2026-10-13T20:00:00Z' }, { reference: 'Mystic jacket', start: '2026-10-14T14:00:00Z', end: '2026-10-14T20:00:00Z' }] },
  reference_closures: { e1: [{ reference: 'PANT SET', size: 'M', quantity: 10, at: '2026-10-14T15:00:00Z' }] },
  ...(on ? { ui: { shift_list: true } } : {}),
});
const flat = (s) => s.replace(/\s+/g, ' ');

test('con el interruptor: tabla compacta con encabezado, columnas, extra solo si hay y TOTAL igual a la suma', () => {
  const P = load();
  P.model.activity = ACTIVITY(true);
  const html = flat(P.detail(CARD));
  assert.match(html, /class="pv-thead-card"/);
  assert.match(html, /Ana Ruiz<\/span><span class="pv-role">Operaria · 123<\/span>/, 'nombre, rol y documento');
  assert.match(html, /<span class="pv-net">\$\s?113\.000<\/span><span class="pv-time">2 turnos<\/span>/, 'valor total y número de turnos a la derecha');
  for (const col of ['Fecha', 'Horario', 'Horas', 'Referencias', 'Valor']) assert.ok(html.includes(`<th scope="col"`) && html.includes(`>${col}</th>`), col);
  assert.equal((html.match(/class="pv-trow /g) || []).length, 2, 'una fila por turno');
  assert.match(html, />Mar 13 oct<\/button>/, 'fecha corta en la zona de la empresa (Bogotá)');
  assert.match(html, /13:22 – 15:25/);
  assert.match(html, /<td data-label="Horas">1 h 48<\/td>/, 'sin extra: sin etiqueta');
  assert.match(html, /<td data-label="Horas">10 h 01<small class="pv-ext">\+2 h 01 ext<\/small><\/td>/, 'con extra: etiqueta pequeña');
  assert.equal((html.match(/pv-ext"/g) || []).length, 1, 'la etiqueta de extra solo donde hay extra');
  assert.doesNotMatch(html, /Pausas/, 'las pausas no se ven hasta abrir el detalle');
  assert.match(html, /class="pv-tref">PANT SET<\/td>/);
  assert.match(html, /class="pv-tref">Mystic jacket, PANT SET<\/td>/);
  const t = P.shiftTotals(CARD);
  assert.equal(t.regular, CARD.regular, 'coincide con lo que calculó la nómina');
  assert.equal(t.extra, CARD.extra);
  assert.match(html, /pv-ttotal[\s\S]*TOTAL · 2 turnos[\s\S]*11 h 49<small class="pv-ext-line">ext 2 h 01<\/small>[\s\S]*title="PANT SET, Mystic jacket">2<\/td>[\s\S]*\$\s?113\.000/);
});

test('al tocar una fila se despliega el detalle con pausas, ordinarias y extra', () => {
  const P = load();
  P.model.activity = ACTIVITY(true);
  P.model.openShift = `e1|${SHIFTS[1].start}`;
  const html = flat(P.detail(CARD));
  assert.match(html, /class="pv-tdetail"/);
  assert.match(html, /<dt>Pausas<\/dt><dd>0 h 30<\/dd>[\s\S]*<dt>Horas ordinarias<\/dt><dd>8 h 00<\/dd>[\s\S]*<dt>Horas extra<\/dt><dd>2 h 01<\/dd>/);
  assert.match(html, /aria-expanded="true"/);
  assert.match(SRC, /const srow = t\.closest\("\[data-pv-srow\]"\);/);
});

test('sin el interruptor: el desglose de siempre', () => {
  const P = load();
  P.model.activity = ACTIVITY(false);
  const html = P.detail(CARD);
  assert.doesNotMatch(html, /pv-table|pv-thead-card/);
  assert.match(html, /class="pv-shift-main"/);
  assert.match(html, /class="pv-detail-head"/);
});

test('estilos y textos: letra pequeña, filas compactas y filas apiladas en celular', () => {
  assert.match(CSS, /\.pv-table \{ width: 100%; border-collapse: collapse; font-size: 12\.5px/);
  assert.match(CSS, /\.pv-table th, \.pv-table td \{ padding: 5px 8px;/);
  assert.match(CSS, /@media \(max-width: 560px\) \{\s*\.pv-table thead \{ display: none; \}/);
  const w = {};
  vm.runInContext(DICT, vm.createContext({ window: w, Object }));
  for (const k of ['Pausas', 'Horas ordinarias', 'Referencias', 'Fecha', 'Horario', 'Valor', 'ext', 'turnos']) {
    assert.ok(k in w.CX_I18N_DICT.en && k in w.CX_I18N_DICT.fr, k);
  }
});
