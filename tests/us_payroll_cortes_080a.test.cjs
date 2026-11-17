// 080A: Nómina por corte de pago (us_payroll_rules.pay_period; hoy solo VOLTAGE). "Quincena" pasa
// a "Corte (2 semanas)", muestra el corte actual, flechas y selector de cortes (ancla 02/11/2026),
// "Semana" lunes a domingo, y en el detalle Semana 1 / Semana 2 con su overtime. Sin el ajuste,
// todo igual que antes (Quincena = 2 semanas laborales).
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const PAYROLL = readFileSync('app/web/payroll_v2.js', 'utf8');
const RULES = { week_start_day: 'monday', week_start_time: '00:00', overtime_after_minutes: 2400, overtime_factor: 1.5, pay_period: { type: 'biweekly', anchor: '2026-11-02' } };

function payroll() {
  const window = { addEventListener() {} };
  const document = { addEventListener() {}, activeElement: null, createElement: () => ({ style: {}, remove() {} }) };
  vm.runInNewContext(PAYROLL, { window, document, console, Intl, Date, setTimeout, clearTimeout, localStorage: { getItem: () => null, setItem() {} } });
  return window.CxPayrollV2;
}
const plain = (v) => JSON.parse(JSON.stringify(v));

function row() {
  const table = { '02': [570, 60], '03': [690, 60], '04': [570, 60], '05': [570, 60], '06': [690, 60], '09': [630, 60], '10': [630, 60], '11': [630, 60], '12': [570, 60], '13': [570, 60], '14': [570, 60] };
  const days = Object.entries(table).map(([d, [p, z]]) => ({ date: `2026-11-${d}`, payable: p, pause: z, regular: p, overtime: 0 }));
  const w1 = days.filter((d) => d.date <= '2026-11-08');
  const w2 = days.filter((d) => d.date > '2026-11-08');
  return {
    employee_id: 'emp-ana', employee_name: 'Ana Alabama', employee_role: 'operario', closed_shifts: 11, regular_minutes: 4800, extra_minutes: 1890, rate_pending: true,
    shifts: days.map((d) => ({ start: `${d.date}T12:00:00Z`, end: `${d.date}T22:30:00Z`, regular_minutes: d.regular, extra_minutes: 0, pause_minutes: 60, connected_minutes: d.payable + 60,
      worked_minutes: d.payable, gross_amount: '0', us: { adjusted: d.date === '2026-11-02' } })),
    us: { place: 'Alabama', tz: 'America/Chicago', abbr: 'CT', days_worked: 11, connected_minutes: 7350, pause_minutes: 660, payable_minutes: 6690, regular_minutes: 4800, overtime_minutes: 1890,
      rate_pending: true, weeks: [
        { week_start: '2026-11-02', week_end: '2026-11-08', payable: 3090, pause: 300, regular: 2400, overtime: 690, days: w1 },
        { week_start: '2026-11-09', week_end: '2026-11-15', payable: 3600, pause: 360, regular: 2400, overtime: 1200, days: w2 }] },
  };
}

function screen(extra = {}, rules = RULES) {
  const P = payroll();
  const snapshot = { period: { period_start: '2026-11-02', period_end: '2026-11-15' }, rows: [row()], totals: { payable_minutes: 6690, extra_minutes: 1890 },
    us_payroll: { rules, operations: [{ name: 'Alabama', abbr: 'CT', tz: 'America/Chicago' }], cut: { start: '2026-11-02', end: '2026-11-15', label: 'Corte 02/11 - 15/11' } } };
  Object.assign(P.model, { snapshot, activity: { documents: {} }, period: { from: '2026-11-02', to: '2026-11-15' }, cfg: null, open: '', query: '', opFilter: 'all',
    usSort: 'payable', usMode: 'fortnight', modal: null, loading: false, notice: '', error: '' }, extra);
  return P;
}

test('080A: cortes cada 2 semanas desde el ancla 02/11/2026 (incluye 30/11) y semana lunes a domingo', () => {
  const P = payroll();
  const pp = plain(P.payPeriodOf(RULES));
  assert.deepEqual(pp, { type: 'biweekly', days: 14, anchor: '2026-11-02' });
  const cut = (ref) => plain(P.usPeriodFor('fortnight', ref, 'monday', pp));
  assert.deepEqual(cut('2026-11-02'), { from: '2026-11-02', to: '2026-11-15' });
  assert.deepEqual(cut('2026-11-15'), { from: '2026-11-02', to: '2026-11-15' });
  assert.deepEqual(cut('2026-11-17'), { from: '2026-11-16', to: '2026-11-29' });
  assert.deepEqual(cut('2026-11-30'), { from: '2026-11-30', to: '2026-12-13' });
  assert.deepEqual(cut('2026-12-20'), { from: '2026-12-14', to: '2026-12-27' });
  assert.deepEqual(cut('2026-11-01'), { from: '2026-10-19', to: '2026-11-01' });
  assert.deepEqual(plain(P.usPeriodFor('week', '2026-11-15', 'monday', pp)), { from: '2026-11-09', to: '2026-11-15' }, 'Semana = lunes a domingo');
  assert.deepEqual(plain(P.usPeriodFor('fortnight', '2026-11-03', 'sunday')), { from: '2026-10-25', to: '2026-11-07' }, 'sin cortes: quincena de siempre');
  assert.equal(P.payPeriodOf({}), null);
  assert.equal(P.payPeriodOf({ pay_period: { type: 'monthly', anchor: '2026-11-02' } }), null);
});

test('080A: botón "Corte (2 semanas)", fechas del corte, flechas y selector de cortes', () => {
  const html = screen().view();
  assert.match(html, /data-pvu-mode="week">Semana<[\s\S]*data-pvu-mode="fortnight">Corte \(2 semanas\)<[\s\S]*data-pvu-mode="custom">Personalizado</);
  assert.match(html, /<h1 class="client-title">Nómina por corte<\/h1>/);
  assert.match(html, /Corte 02\/11 – 15\/11 · <b>Lun 02\/11 – Dom 15\/11<\/b>/);
  assert.match(html, /data-pvu-step="-1" aria-label="corte anterior"[\s\S]*<select data-pvu-cut[\s\S]*data-pvu-step="1" aria-label="corte siguiente"/);
  assert.match(html, /<option value="2026-11-02" selected>Corte 02\/11 – 15\/11/);
  assert.match(html, /<option value="2026-11-16"[^>]*>Corte 16\/11 – 29\/11/);
  const week = screen({ usMode: 'week', period: { from: '2026-11-09', to: '2026-11-15' } }).view();
  assert.doesNotMatch(week, /data-pvu-cut/);
  assert.match(week, /Semana laboral <b>Lun 09\/11 – Dom 15\/11<\/b>/);
  const before = screen({}, { week_start_day: 'sunday' }).view();
  assert.match(before, /data-pvu-mode="fortnight">Quincena</, 'otra empresa: Quincena');
  assert.doesNotMatch(before, /Corte \(2 semanas\)|data-pvu-cut/);
});

test('080A: detalle de la persona con Semana 1 y Semana 2 (overtime por semana) y el chip de ajuste masivo', () => {
  const d = screen({ open: 'emp-ana' }).view();
  assert.match(d, /Semana 1: <b>51 h 30<\/b> pagables · 40 h 00 regulares · <b class="pvu-ot">11 h 30 overtime<\/b>/);
  assert.match(d, /Semana 2: <b>60 h 00<\/b> pagables · 40 h 00 regulares · <b class="pvu-ot">20 h 00 overtime<\/b>/);
  assert.match(d, /<caption>Semana 1 · Lun 02\/11 – Dom 08\/11 · hora CT[\s\S]*<caption>Semana 2 · Lun 09\/11 – Dom 15\/11/);
  assert.match(d, /Lun 02\/11 <span class="pvu-adj"[^>]*>Ajuste masivo<\/span>/);
  assert.doesNotMatch(d, /Mar 03\/11 <span class="pvu-adj"/);
});
