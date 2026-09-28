// Nómina por días de corte (049L) en el portal: el periodo viene
// preseleccionado, se ve cuál es y cuándo cierra, se navega a periodos
// viejos y se editan los días de corte. Sin configuración, nada cambia.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');

function portal(responses) {
  const calls = [];
  const rendered = [];
  const ctx = vm.createContext({
    h: (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
    state: { companyId: 'velvet' }, Math, Number, String, Array, Object, JSON, Date, Boolean,
    api: async (path, options = {}) => { calls.push({ path, method: options.method || 'GET', body: options.body ? JSON.parse(options.body) : null }); return responses(path, options); },
    document: { querySelector: (sel) => ({ '[data-payroll-cutoffs]': { value: '10, 25' }, '[data-payroll-autoclose]': { checked: true } })[sel] || null },
    payrollReadPeriod: () => ({ from: '2026-09-26', to: '2026-10-10' }),
    renderPayrollModule: async (period) => { rendered.push(period); },
  });
  const a = source.indexOf('  /* CX_PAYROLL_CUTOFFS_049L_START */');
  const b = source.indexOf('  /* CX_PAYROLL_CUTOFFS_049L_END */');
  vm.runInContext(source.slice(a, b), ctx);
  ctx.calls = calls;
  ctx.rendered = rendered;
  return ctx;
}

function periodResponse(start, end, headline, extra = {}) {
  return { enabled: true, cutoff_days: [10, 25], auto_close: true,
    period: { period_start: start, period_end: end, headline, closed: false, auto_close_label: 'el corte se procesa solo el 11 de octubre a las 00:01', ...extra } };
}

const SEPT = periodResponse('2026-09-26', '2026-10-10', 'Periodo del 26 sep al 10 oct · cierra el 10 de octubre');

test('se ve qué periodo es y cuándo cierra, con el corte automático', () => {
  const ctx = portal(() => SEPT);
  const html = ctx.cxPayPeriodHtml049L(SEPT, { from: '2026-09-26', to: '2026-10-10' });
  assert.match(html, /data-payroll-period-headline>Periodo del 26 sep al 10 oct · cierra el 10 de octubre</);
  assert.match(html, /Periodo abierto · el corte se procesa solo el 11 de octubre a las 00:01/);
  assert.match(html, /data-payroll-period-shift="prev">‹ Periodo anterior[\s\S]*data-payroll-period-shift="next">Periodo siguiente ›/);
  assert.match(html, /data-payroll-cutoffs value="10, 25"/);
  const manual = ctx.cxPayPeriodHtml049L(SEPT, { from: '2026-09-01', to: '2026-09-15' });
  assert.match(manual, /Periodo del 2026-09-01 al 2026-09-15[\s\S]*Fechas elegidas a mano/);
  assert.match(ctx.cxPayPeriodHtml049L({ ...SEPT, period: { ...SEPT.period, closed: true } }, { from: '2026-09-26', to: '2026-10-10' }), /Periodo cerrado/);
});

test('sin días de corte (otra empresa) no se ve nada nuevo y no se vuelve a preguntar', async () => {
  const ctx = portal(() => ({ enabled: false }));
  assert.equal(ctx.cxPayPeriodHtml049L({ enabled: false }, { from: '2026-09-16', to: '2026-09-28' }), '');
  await ctx.cxPayLoadCfg049L();
  await ctx.cxPayLoadCfg049L('2026-09-01');
  assert.equal(ctx.calls.length, 1, 'una sola consulta por empresa');
});

test('periodo anterior y siguiente: se consulta un periodo viejo a mano, cruzando el año', async () => {
  const ctx = portal((path) => {
    if (path.includes('date_ref=2026-09-25')) return periodResponse('2026-09-11', '2026-09-25', 'Periodo del 11 sep al 25 sep · cerró el 25 de septiembre');
    if (path.includes('date_ref=2026-10-11')) return periodResponse('2026-10-11', '2026-10-25', 'x');
    return SEPT;
  });
  await ctx.cxPayHandleClick049L({ closest: (sel) => (sel === '[data-payroll-period-shift]' ? { getAttribute: () => 'prev' } : null) });
  await ctx.cxPayHandleClick049L({ closest: (sel) => (sel === '[data-payroll-period-shift]' ? { getAttribute: () => 'next' } : null) });
  assert.deepEqual(JSON.parse(JSON.stringify(ctx.rendered)), [{ from: '2026-09-11', to: '2026-09-25' }, { from: '2026-10-11', to: '2026-10-25' }]);
  assert.equal(ctx.cxPayShiftDate049L('2026-12-26', -1), '2026-12-25');
  assert.equal(ctx.cxPayShiftDate049L('2027-01-10', 1), '2027-01-11');
  assert.equal(ctx.cxPayShiftDate049L('2026-12-31', 1), '2027-01-01');
});

test('guardar días de corte', async () => {
  const ctx = portal(() => SEPT);
  await ctx.cxPayHandleClick049L({ closest: (sel) => (sel === '[data-payroll-cutoffs-save]' ? {} : null) });
  const put = ctx.calls.find((c) => c.method === 'PUT');
  assert.equal(put.path, '/payroll/companies/velvet/period-config');
  assert.deepEqual(JSON.parse(JSON.stringify(put.body)), { cutoff_days: [10, 25], auto_close: true });
  assert.match(ctx.cxPayCfg049L.message, /guardados/);
});

test('al abrir Nómina el periodo viene de los días de corte', () => {
  assert.match(source, /async function renderPayrollModule\(period, options = \{\}\) \{/);
  assert.match(source, /period = periodCfg049L\.enabled\s*\? \{ from: periodCfg049L\.period\.period_start, to: periodCfg049L\.period\.period_end \}\s*: payrollDefaultPeriod\(\);/);
  assert.match(source, /\$\{cxPayPeriodHtml049L\(periodCfg049L, period\)\}/);
});
