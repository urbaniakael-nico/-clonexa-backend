// Fase A · formateador único del portal (client_locale.js).
// Regla de oro: con COP cada lugar sigue con su formato de siempre; solo con
// otra moneda cambia. Lector de cifras igual al del servidor. Días en la zona
// de la empresa, con horario de verano.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const SRC = readFileSync('app/web/client_locale.js', 'utf8');
const CLIENT = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');

function load(data) {
  const window = {};
  vm.runInNewContext(SRC, { window, Intl, Date, Number, String, Math, Promise });
  if (data) window.CxLocale.apply(data);
  return window.CxLocale;
}

test('dinero: COP con el formato de siempre (legacy); USD "$1,234.50"; sin cargar = COP', () => {
  const cop = load();
  assert.equal(cop.currency, 'COP');
  assert.equal(cop.foreign(), false);
  assert.equal(cop.money(1234.5, (v) => `LEGACY ${v}`), 'LEGACY 1234.5', 'con COP manda el de siempre');
  assert.equal(cop.money(1234.5), '$ 1.235');
  const usd = load({ currency: 'USD', timezone: 'America/Chicago', language: 'es' });
  assert.equal(usd.foreign(), true);
  assert.equal(usd.money(1234.5, () => 'no'), '$1,234.50');
  assert.equal(usd.money(-5), '-$5.00');
  assert.equal(usd.money(0), '$0.00');
  assert.equal(load({ currency: 'EUR' }).money(1234.5), '1.234,50 €');
  assert.equal(load({ currency: 'XXX' }).currency, 'COP', 'moneda desconocida = COP');
});

// Los lectores de siempre (client.js antes de la Fase A), copiados tal cual.
function oldInventory(value) {
  const raw = String(value ?? '').replace(/[\s$]/g, '');
  if (!raw) return 0;
  let normalized = raw;
  if (raw.includes(',')) normalized = raw.replace(/\./g, '').replace(',', '.');
  else if (/^\d{1,3}(\.\d{3})+$/.test(raw)) normalized = raw.replace(/\./g, '');
  const n = Number(normalized);
  return Number.isFinite(n) ? n : 0;
}

test('lector: "1.234,50" (COP) y "1,234.50" (USD) -> 1234.5; en COP da lo mismo que el lector de siempre', () => {
  const cop = load();
  const usd = load({ currency: 'USD' });
  assert.equal(cop.parse('1.234,50'), 1234.5);
  assert.equal(usd.parse('1,234.50'), 1234.5);
  assert.equal(cop.parse('1,234.50'), 1234.5, 'antes inventario lo guardaba como 1,2345');
  assert.equal(usd.parse('1,234'), 1234);
  assert.equal(usd.parse('1.5'), 1.5);
  assert.equal(cop.parse(1234.567), 1234.567, 'los números del servidor pasan tal cual');
  for (const raw of ['29.000', '1.234,5', '29000', '12.5', '1.120.000', '14,5', '$ 1.234', '0', '', '7,25', '100', '2.5']) {
    assert.equal(cop.parse(raw), oldInventory(raw), `"${raw}" en COP igual que antes`);
  }
});

test('días: corte en la zona de la empresa, con el fin del horario de verano (Chicago, 1 nov 2026)', () => {
  const chi = load({ currency: 'USD', timezone: 'America/Chicago' });
  assert.equal(chi.dayBoundUtc('2026-10-31'), '2026-10-31T05:00:00.000Z', 'CDT = UTC-5');
  assert.equal(chi.dayBoundUtc('2026-11-02'), '2026-11-02T06:00:00.000Z', 'CST = UTC-6');
  assert.equal(chi.dayBoundUtc('2026-11-01', true), '2026-11-02T05:59:59.999Z');
  assert.equal(chi.dayKey(new Date('2026-11-09T05:30:00Z')), '2026-11-08', 'para Chicago aún es el día 8');
  const bog = load();
  assert.equal(bog.dayKey(new Date('2026-11-09T05:30:00Z')), '2026-11-09');
  assert.equal(bog.dayBoundUtc('2026-10-11'), '2026-10-11T05:00:00.000Z');
});

test('portal: cada formateador de dinero gana la guarda (COP igual) y Reportes deja de ser siempre USD', () => {
  const GUARD = 'if (typeof window !== "undefined" && window.CxLocale && window.CxLocale.foreign() && value !== null && value !== undefined) return window.CxLocale.money(value);';
  for (const name of ['mundoCaseCompactMoney024L', 'cxFixMoney049M', 'cxStockMoney024T', 'payrollMoney', 'kpiMoney', 'cxSalesMoney023P', 'cxUniversalMoney021D',
    'cxReferencesMoney022M', 'cxClosingMoney023K', 'cxHspMoney024R', 'cxOwnMoney048S', 'cxTransportContractsMoney028M', 'cxSalesMoney022F',
    'cxCarMoney048T', 'cxCarUnitMoney048T', 'cxCarPortionMoney049N']) {
    assert.ok(CLIENT.includes(`function ${name}(value) {\n    ${GUARD}`), name);
  }
  assert.match(CLIENT, /function fmtMoney\(value\) \{\n    const n = Number\(value \|\| 0\);\n[^\n]*\n    if \(typeof window !== "undefined" && window\.CxLocale\) return window\.CxLocale\.money\(n\);/);
  for (const name of ['inventoryMoneyValue045B', 'cxInvMoneyValue049Q', 'payrollNumber']) {
    assert.ok(CLIENT.includes(`function ${name}(value) {\n    if (typeof window !== "undefined" && window.CxLocale) return window.CxLocale.parse(value);`), name);
  }
  assert.match(CLIENT, /await window\.CxLocale\.load\(state\.companyId, \(path\) => api\(path\)\);/, 'se carga una vez al entrar');
  assert.match(readFileSync('app/web/client.html', 'utf8').replace(/\r\n/g, '\n'), /client_locale\.js\?v=052C"><\/script>\n  <script src="\/client-static\/client_i18n_dict\.js\?v=052D"><\/script>\n  <script src="\/client-static\/client_i18n_core\.js\?v=052D"><\/script>\n  <script src="\/client-static\/client\.js/);
  assert.doesNotMatch(CLIENT, /NÃ³mina|rÃ©f/, 'sin letras dañadas');
});

test('una guarda de verdad: con COP un formateador escribe lo mismo; con USD usa la moneda de la empresa', () => {
  const start = CLIENT.indexOf('  function cxFixMoney049M(value) {');
  const fn = CLIENT.slice(start, CLIENT.indexOf('\n  }\n', start) + 4);
  const run = (data, v) => {
    const window = {};
    vm.runInNewContext(SRC, { window, Intl, Date, Number, String, Math, Promise });
    if (data) window.CxLocale.apply(data);
    return vm.runInNewContext(`${fn}; cxFixMoney049M(${v})`, { window, Number, Math });
  };
  assert.equal(run(null, 1234567), `$${Math.round(1234567).toLocaleString('es-CO')}`);
  assert.equal(run({ currency: 'COP' }, 1234567), `$${Math.round(1234567).toLocaleString('es-CO')}`);
  assert.equal(run({ currency: 'USD' }, 1234.5), '$1,234.50');
});

test('filtros de días (Fase B): todas las empresas cortan a la medianoche de su zona, también Bogotá', () => {
  const bog = load();
  assert.equal(bog.filterDay(new Date('2026-11-09T03:00:00Z')), '2026-11-08', 'Bogotá: las 10 pm del 8 son el día 8 (antes, el 9 por UTC)');
  assert.equal(bog.filterBound('2026-10-11'), '2026-10-11T05:00:00.000Z');
  const chi = load({ currency: 'USD', timezone: 'America/Chicago' });
  assert.equal(chi.filterDay(new Date('2026-11-09T05:30:00Z')), '2026-11-08');
  assert.equal(chi.filterBound('2026-11-02'), '2026-11-02T06:00:00.000Z');
  assert.match(CLIENT, /\(\(typeof window !== "undefined" && window\.CxLocale && window\.CxLocale\.filterDay\(now\)\) \|\| now\.toISOString\(\)\.slice\(0, 10\)\)/);
});

test('filtros de días con jornada nocturna (The Time Machine 18:00-04:00): el día termina al cierre', () => {
  const ttm = load({ currency: 'COP', timezone: 'America/Bogota', business_day: { open: '18:00', close: '04:00', overnight: true } });
  assert.equal(ttm.filterDay(new Date('2026-10-12T07:00:00Z')), '2026-10-11', 'las 02:00 del 12 son de la noche del 11');
  assert.equal(ttm.filterDay(new Date('2026-10-12T08:59:00Z')), '2026-10-11', '03:59');
  assert.equal(ttm.filterDay(new Date('2026-10-12T09:00:00Z')), '2026-10-12', '04:00');
  assert.equal(ttm.filterBound('2026-10-11'), '2026-10-11T09:00:00.000Z');
  assert.equal(ttm.filterBound('2026-10-11', true), '2026-10-12T08:59:59.999Z');
  assert.equal(ttm.filterDay(new Date('2026-11-01T06:00:00Z')), '2026-10-31', 'cambio de mes');
  const day = load({ timezone: 'America/Bogota', business_day: { open: '08:00', close: '22:00', overnight: false } });
  assert.equal(day.filterBound('2026-10-11'), '2026-10-11T05:00:00.000Z', 'jornada de un solo día: medianoche');
  const asadero = load({ timezone: 'America/Bogota', business_day: null });
  assert.equal(asadero.filterDay(new Date('2026-10-12T07:00:00Z')), '2026-10-12', 'sin jornada: medianoche');
});
