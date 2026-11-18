// 081A: Nómina con semana y corte POR OPERACIÓN (us_payroll_rules.places). Virginia domingo a sábado,
// ancla 01/11; Alabama lunes a domingo, ancla 02/11. Con "Todas" cada operación muestra sus fechas;
// filtrando una, el selector muestra los cortes de esa operación. El detalle de la persona usa la
// semana de su operación. El cálculo pide us_span al servidor (cada persona con su corte).
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const PAYROLL = readFileSync('app/web/payroll_v2.js', 'utf8');
const VA_ID = 'place-va';
const RULES = { week_start_day: 'monday', week_start_time: '00:00', overtime_after_minutes: 2400, overtime_factor: 1.5, pay_period: { type: 'biweekly', anchor: '2026-11-02' },
  places: { [VA_ID]: { week_start_day: 'sunday', pay_period: { type: 'biweekly', anchor: '2026-11-01' } } } };

function payroll(calls = []) {
  const window = { addEventListener() {} };
  const document = { addEventListener() {}, activeElement: null, createElement: () => ({ style: {}, remove() {} }) };
  vm.runInNewContext(PAYROLL, { window, document, console, Intl, Date, setTimeout, clearTimeout, localStorage: { getItem: () => null, setItem() {} } });
  return window.CxPayrollV2;
}

function vaRow() {
  const days = [2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13].map((d) => ({ date: `2026-11-${String(d).padStart(2, '0')}`, payable: 720, pause: 30, regular: 0, overtime: 0 }));
  return { employee_id: 'emp-kewin', employee_name: 'Kewin Mauricio Rios Lindo', employee_role: 'operario', closed_shifts: 11, regular_minutes: 4800, extra_minutes: 3120, rate_pending: true,
    shifts: days.map((d) => ({ start: `${d.date}T12:00:00Z`, end: `${d.date}T00:30:00Z`, us: {} })),
    us: { place: 'Virginia', tz: 'America/New_York', abbr: 'ET', days_worked: 11, payable_minutes: 7920, regular_minutes: 4800, overtime_minutes: 3120, pause_minutes: 330, connected_minutes: 8250,
      rate_pending: true, period_start: '2026-11-01', period_end: '2026-11-14', cut_label: 'Corte 01/11 - 14/11',
      weeks: [{ week_start: '2026-11-01', week_end: '2026-11-07', payable: 4320, pause: 180, regular: 2400, overtime: 1920, days: days.slice(0, 6) },
        { week_start: '2026-11-08', week_end: '2026-11-14', payable: 3600, pause: 150, regular: 2400, overtime: 1200, days: days.slice(6) }] } };
}

function screen(extra = {}) {
  const P = payroll();
  const ops = [
    { name: 'Virginia', abbr: 'ET', tz: 'America/New_York', id: VA_ID, rules: { week_start_day: 'sunday', pay_period: { type: 'biweekly', anchor: '2026-11-01' } },
      period_start: '2026-11-01', period_end: '2026-11-14', cut: { start: '2026-11-01', end: '2026-11-14', label: 'Corte 01/11 - 14/11' } },
    { name: 'Alabama', abbr: 'CT', tz: 'America/Chicago', id: 'place-al', rules: { week_start_day: 'monday', pay_period: { type: 'biweekly', anchor: '2026-11-02' } },
      period_start: '2026-11-02', period_end: '2026-11-15', cut: { start: '2026-11-02', end: '2026-11-15', label: 'Corte 02/11 - 15/11' } }];
  const snapshot = { period: { period_start: '2026-11-01', period_end: '2026-11-15' }, rows: [vaRow()], totals: { payable_minutes: 7920, extra_minutes: 3120 },
    us_payroll: { rules: RULES, operations: ops, span: { kind: 'cut', ref: '2026-11-14' } } };
  Object.assign(P.model, { snapshot, activity: { documents: {} }, period: { from: '2026-11-01', to: '2026-11-15' }, span: { kind: 'cut', ref: '2026-11-14' }, cfg: null, open: '',
    query: '', opFilter: 'all', usSort: 'payable', usMode: 'fortnight', modal: null, loading: false, notice: '', error: '' }, extra);
  return P;
}

test('081A: con "Todas" cada operación muestra su propio corte y el selector junta los dos', () => {
  const html = screen().view();
  assert.match(html, /Virginia: <b>Corte 01\/11 – 14\/11<\/b>[\s\S]*Alabama: <b>Corte 02\/11 – 15\/11<\/b>/);
  assert.match(html, /<option value="2026-11-02" selected>Virginia 01\/11–14\/11 · Alabama 02\/11–15\/11/);
  assert.match(html, /<option value="2026-11-16"[^>]*>Virginia 15\/11–28\/11 · Alabama 16\/11–29\/11/);
});

test('081A: filtrando Virginia, el selector muestra los cortes de Virginia (01-14, 15-28, 29/11-12/12)', () => {
  const html = screen({ opFilter: 'Virginia' }).view();
  assert.match(html, /Corte 01\/11 – 14\/11 · <b>Dom 01\/11 – Sáb 14\/11<\/b>/);
  assert.match(html, /<option value="2026-11-01" selected>Corte 01\/11 – 14\/11/);
  assert.match(html, /<option value="2026-11-15"[^>]*>Corte 15\/11 – 28\/11/);
  assert.match(html, /<option value="2026-11-29"[^>]*>Corte 29\/11 – 12\/12/);
  const al = screen({ opFilter: 'Alabama' }).opCutOptions().map((o) => `${o.ref}|${o.label}|${o.selected}`);
  assert.equal(al[0], '2026-11-02|Corte 02/11 – 15/11|true');
  assert.ok(al.some((x) => x.startsWith('2026-11-16|Corte 16/11 – 29/11')));
});

test('081A: detalle de una persona de Virginia con semanas domingo a sábado y su overtime', () => {
  const d = screen({ open: 'emp-kewin' }).view();
  assert.match(d, /Semana 1: <b>72 h 00<\/b> pagables · 40 h 00 regulares · <b class="pvu-ot">32 h 00 overtime<\/b>/);
  assert.match(d, /<caption>Semana 1 · Dom 01\/11 – Sáb 07\/11 · hora ET[\s\S]*<caption>Semana 2 · Dom 08\/11 – Sáb 14\/11/);
});

test('081A: el cálculo pide al servidor el corte de cada operación (us_span) y el PDF/CSV también', () => {
  assert.match(PAYROLL, /us_span: model\.span/);
  assert.match(PAYROLL, /q\.set\("span_kind", model\.span\.kind\); q\.set\("span_ref", model\.span\.ref\)/);
  assert.match(PAYROLL, /\(ctx\.usRules \|\| \{\}\)\.places\) \{ \/\/ 081A/);
});
