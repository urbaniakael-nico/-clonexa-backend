// Nómina y tiempos EE. UU. (interruptor us_payroll; hoy solo VOLTAGE). Las pantallas usan
// la salida REAL del servidor para Caso (tests/fixtures/us_payroll_caso.json,
// generada por tests/fixtures/make_us_payroll_fixture.py y verificada en
// tests/test_us_payroll_pg.py): mismas cifras en Reportes, Nómina, PDF, CSV y el bot.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const US = readFileSync('app/web/us_payroll.js', 'utf8');
const CSS = readFileSync('app/web/us_payroll.css', 'utf8');
const REPORTS = readFileSync('app/web/reports_v2.js', 'utf8');
const PAYROLL = readFileSync('app/web/payroll_v2.js', 'utf8');
const CLIENT = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');
const FIX = JSON.parse(readFileSync('tests/fixtures/us_payroll_caso.json', 'utf8'));
const clone = (v) => JSON.parse(JSON.stringify(v));

function usLib() {
  const window = {};
  vm.runInNewContext(US, { window });
  return window.CxUsPayroll;
}

function reports(withUs = true) {
  const window = withUs ? { CxUsPayroll: usLib() } : {};
  vm.runInContext(REPORTS, vm.createContext({ window, document: {}, URLSearchParams, JSON, Object, Array, String, Number, Math, Date, Map, Set, Promise, Error, encodeURIComponent }));
  return window.CxReportsV2;
}

function payroll(withUs = true) {
  const window = { addEventListener() {}, ...(withUs ? { CxUsPayroll: usLib() } : {}) };
  const document = { addEventListener() {}, activeElement: null, createElement: () => ({ style: {}, remove() {} }) };
  vm.runInNewContext(PAYROLL, { window, document, console, Intl, Date, setTimeout, clearTimeout });
  return window.CxPayrollV2;
}

const ROW = FIX.snapshot.rows[0];
const SHIFT = ROW.shifts[0].us;

test('línea de tiempo del turno de Caso: hora de Virginia (ET), pausa sin pago, ubicación, notas y totales', () => {
  const U = usLib();
  const html = U.timeline(SHIFT);
  assert.match(html, /Entrada<\/b> <span class="usp-time">06:45 ET<\/span>/, '06:45 ET, no 05:45 (Chicago)');
  assert.match(html, /Pausa<\/b> <span class="usp-time">10:34 ET – 11:29 ET<\/span>\s*<span class="usp-dur">0 h 55 min sin pago<\/span>/);
  assert.match(html, /Salida<\/b> <span class="usp-time">16:25 ET<\/span>/, '16:25 ET = 4:25 PM que vio en su celular');
  assert.match(html, /Sin perímetro/);
  assert.match(html, /href="https:\/\/www\.google\.com\/maps\?q=38\.900000,-77\.000000"/);
  assert.match(html, /En turno<\/dt><dd>9 h 40 min[\s\S]*Pausas \(sin pago\)<\/dt><dd>0 h 55 min[\s\S]*Tiempo pagable<\/dt><dd>8 h 45 min/);
  assert.doesNotMatch(html, /Overtime/, 'sin overtime: la semana no pasa de 40 h');
  assert.match(html, /Resumen de la jornada[\s\S]*Etiquetado rack A/);
  assert.match(html, /Virginia · hora ET/);
});

test('cierre por supervisor: quién, hora puesta y su nota; sin lugar: aviso', () => {
  const U = usLib();
  const t = { ...clone(SHIFT), manual_close: { by: 'Sofía (supervisor)', note: 'Olvidó finalizar', closed_at: '2026-11-04T02:00:00Z' }, notes: [], place: null, place_missing: true };
  const html = U.timeline(t);
  assert.match(html, /Lo cerró Sofía \(supervisor\) · hora puesta 16:25 ET · “Olvidó finalizar”/);
  assert.match(html, /Sin lugar asignado: hora de la empresa/);
  assert.match(U.timeline({ ...t, notes: [{ kind: 'x', label: '<b>', text: '<script>' }] }), /&lt;script&gt;/, 'escapa las notas');
});

test('sin tarifa el dinero dice Pendiente, nunca $0.00; con tarifa, el valor', () => {
  const U = usLib();
  assert.equal(U.money(0, true), 'Pendiente');
  assert.equal(U.money(null, false), 'Pendiente');
  assert.equal(U.money(950, false), '$950.00');
  const html = U.breakdown(ROW, (v) => `$${v.toFixed(2)}`);
  assert.match(html, /Lugar<\/dt><dd>Virginia/);
  assert.match(html, /Días trabajados<\/dt><dd>1/);
  assert.match(html, /Horas en turno<\/dt><dd>9 h 40 min[\s\S]*Pausas \(sin pago\)<\/dt><dd>0 h 55 min[\s\S]*Horas pagables<\/dt><dd>8 h 45 min[\s\S]*Regulares<\/dt><dd>8 h 45 min[\s\S]*Overtime<\/dt><dd>0 h 00 min/);
  assert.match(html, /Tarifa<\/dt><dd>Tarifa pendiente[\s\S]*Bruto regular<\/dt><dd>Pendiente[\s\S]*Bruto overtime \(1\.5x\)<\/dt><dd>Pendiente[\s\S]*Deducciones<\/dt><dd>Pendiente[\s\S]*Neto<\/dt><dd>Pendiente/);
  assert.doesNotMatch(html, /\$0/);
  assert.match(U.missingRate(FIX.snapshot.us_payroll.missing_rate), /1 empleados sin tarifa<\/b>: Colaboradora Caso 2 Nov/);
  assert.match(U.weekTable(ROW.us.weeks), /dom 01\/11 – sáb 07\/11[\s\S]*lun 02\/11 <b>8 h 45 min<\/b>[\s\S]*<b>8 h 45 min<\/b><\/td><td>8 h 45 min<\/td><td>0 h 00 min/);
  assert.match(U.rulesLine(FIX.snapshot.us_payroll.rules), /Semana laboral: domingo 00:00 \(hora del lugar\) · Overtime: más de 40 h por semana a 1\.5x · Pausas sin pago/);
});

test('Reportes v2: indicadores, tarjeta, horas por día y ventana del turno con las mismas cifras', () => {
  const R = reports();
  Object.assign(R.model, { data: { company: { name: 'VOLTAGE' }, insights_v2: clone(FIX.insights_v2), details: { employees: [] } }, denied: false, loading: false, modal: null });
  const html = R.view();
  assert.match(html, /<small>Horas pagables<\/small><b>8 h 45 min<\/b><span>8 h 45 min regulares \+ 0 h 00 min overtime<\/span>/);
  assert.match(html, /<small>Nómina del periodo<\/small><b>Pendiente<\/b><span>neto · pausas sin pago 0 h 55 min<\/span>/);
  assert.match(html, /1 empleados sin tarifa<\/b>: Colaboradora Caso 2 Nov/);
  assert.match(html, /Pagable<i class="is-ext"><\/i>Pausas \(sin pago\)/, 'la barra: pagable y pausas en otro color');
  assert.match(html, /Horas pagables <b>8 h 45 min<\/b><\/span><span>Overtime <b>0 h 00 min<\/b>[\s\S]*Pausas \(sin pago\) <b>0 h 55 min<\/b>[\s\S]*Neto <b>Pendiente<\/b>/);
  assert.match(html, /Semana laboral por persona[\s\S]*Colaboradora Caso 2 Nov[\s\S]*lun 02\/11 <b>8 h 45 min<\/b>/);
  assert.doesNotMatch(html, /\$ ?0(\.00)?\b/, 'nunca $0.00');
  R.model.modal = { type: 'person', id: 'emp-caso' };
  const modal = R.view();
  assert.match(modal, /role="dialog"[\s\S]*06:45 ET[\s\S]*10:34 ET – 11:29 ET[\s\S]*16:25 ET[\s\S]*Tiempo pagable<\/dt><dd>8 h 45 min/);
  assert.doesNotMatch(modal, /0 h 45 min/, 'la ventana ya no muestra "Extra 0h45"');
});

test('Reportes v2 sin us_payroll: la pantalla de siempre (otra empresa)', () => {
  const R = reports(false);
  const PAYLOAD = JSON.parse(readFileSync('tests/fixtures/reports_v2_payload.json', 'utf8'));
  Object.assign(R.model, { data: PAYLOAD, denied: false, loading: false, modal: null });
  const html = R.view();
  assert.match(html, /<small>Horas trabajadas<\/small>/);
  assert.doesNotMatch(html, /Horas pagables|Semana laboral por persona|Pendiente/);
});

test('Nómina v2 con us_payroll (063A): solo horas y valores por operación; sin línea de tiempo, ubicación ni notas', () => {
  const P = payroll();
  Object.assign(P.model, { snapshot: clone(FIX.snapshot), activity: null, period: { from: '2026-11-01', to: '2026-11-07' }, cfg: null, open: 'emp-caso', cols: 4 });
  const html = P.view();
  assert.match(html, /Resumen Virginia[\s\S]*Horas pagables<\/span><strong>8 h 45[\s\S]*Regulares<\/span><strong>8 h 45[\s\S]*Overtime<\/span><strong>0 h 00[\s\S]*Pausas<\/span><strong>0 h 55[\s\S]*Bruto<\/span><strong>Tarifa pendiente/);
  assert.match(html, /Tabla Virginia[\s\S]*Colaboradora Caso 2 Nov[\s\S]*<b>8 h 45<\/b>[\s\S]*Pendiente/);
  assert.match(html, /Lun 02\/11<\/th>\s*<td data-label="Entrada">06:45<\/td><td data-label="Salida">16:25/);
  assert.match(html, /data-pv-us-export="csv">CSV<\/button>[\s\S]*data-pv-us-export="pdf">Descargar PDF/);
  assert.doesNotMatch(html, /Sin perímetro|Ver en el mapa|Resumen de la jornada|Etiquetado rack|usp-shift|\$0\.00/);
});

test('Nómina v2 sin us_payroll: la pantalla de siempre, sin PDF/CSV nuevos', () => {
  const P = payroll(false);
  const snap = { period: { period_start: '2026-10-01', period_end: '2026-10-15' }, rows: [{ employee_id: 'a', employee_name: 'Zoe', regular_minutes: 480, extra_minutes: 0, net_amount: 100, gross_amount: 100, shifts: [] }],
    totals: { people: 1, regular_minutes: 480, extra_minutes: 0, gross_amount: 100, discount_amount: 0, net_amount: 100 } };
  Object.assign(P.model, { snapshot: snap, activity: null, period: { from: '2026-10-01', to: '2026-10-15' }, cfg: null, open: '' });
  const html = P.view();
  assert.match(html, /Horas ordinarias<\/span><strong>8 h 00 min/);
  assert.doesNotMatch(html, /Horas pagables|data-pv-us-export|Pendiente/);
});

test('client.js pide las versiones nuevas y pasa la sesión para la descarga; CSS solo del tema', () => {
  assert.match(CLIENT, /payroll_v2\.js\?v=063A/);
  assert.match(CLIENT, /payroll_v2\.css\?v=063A/);
  assert.match(CLIENT, /apiBase: API, token: \(\) => \(typeof cxReportsToken053C === "function" \? cxReportsToken053C\(\) : ""\)/);
  assert.match(REPORTS, /\/client-static\/us_payroll\.js\?v=061A/);
  assert.match(PAYROLL, /\/client-static\/us_payroll\.js\?v=061A/);
  assert.match(readFileSync('app/web/client.html', 'utf8'), /client\.js\?v=[^"]*_061A_063A"/);
  assert.ok(!/#[0-9a-f]{3,8}\b/i.test(CSS) && !/rgb\(|hsl\(/i.test(CSS), 'sin colores propios');
});
