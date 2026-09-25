// Nómina con normativa colombiana en el portal y Admin V2 (048O). Ejecuta las
// funciones reales de client.js.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');
const admin = readFileSync('app/web/admin_v2.js', 'utf8').replace(/\r\n/g, '\n');

function fn(name) {
  const start = source.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  var |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

function portal() {
  const ctx = vm.createContext({
    h: (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
    Intl, Date, Math, Number, String, Array, Object, JSON,
  });
  vm.runInContext('var cxPayCo048O = { open: false, config: null, message: "", error: "" };\n'
    + ['payrollNumber', 'payrollMoney', 'cxPayCoHours048O', 'cxPayCoNotice048O', 'cxPayCoPartsHtml048O',
      'cxPayCoEmployeeHtml048O', 'cxPayCoRowsHtml048O', 'cxPayCoConfigHtml048O', 'cxPayCoCsvRows048O'].map(fn).join('\n'), ctx);
  return ctx;
}

const ROW = {
  employeeId: 'e1', name: 'Ana Mesera', role: 'mesero', net: 90000, discount: 4000,
  colombia: {
    monthly_salary: 1750905, salary_is_minimum_default: true, worked_days: 1,
    earned_amount: 78000, transport_allowance: 8303.17,
    lines: [
      { type: 'ord_night', label: 'Ordinaria nocturna', surcharge: 'nocturno 35%', minutes: 60, hour_value: 11255.82, base_hour_value: 8337.64, amount: 11255.82, from: '2026-09-22', to: '2026-09-22' },
      { type: 'ext_day', label: 'Extra diurna', surcharge: 'extra diurna 25%', minutes: 180, hour_value: 10422.05, base_hour_value: 8337.64, amount: 31266.15, from: '2026-09-22', to: '2026-09-22' },
    ],
    alerts: [{ kind: 'extra_daily', message: '2026-09-22: 3 h extra en el dia (maximo legal 2 h).' }],
    employee_deductions: [{ label: 'Salud empleado', pct: 4, base: 78000, amount: 3120, note: '' }],
    employee_deductions_total: 3120, other_deductions: 0,
    employer_contributions: [{ label: 'Pension empleador', pct: 12, base: 78000, amount: 9360, note: '' }],
    employer_contributions_total: 9360,
    provisions: [{ label: 'Prima de servicios', pct: 8.33, base: 86303.17, amount: 7189.05, note: 'Base incluye auxilio de transporte' }],
    provisions_total: 7189.05,
  },
};

test('aviso obligatorio con el interruptor apagado y nota con el encendido', () => {
  const ctx = portal();
  const manual = ctx.cxPayCoNotice048O({ state: 'manual', notice: 'Modo manual: los recargos ... son obligatorios para trabajadores con contrato laboral. Usa este modo solo si la nómina se liquida en otro sistema.' });
  assert.match(manual, /data-payco-notice="manual"[\s\S]*Modo manual activo[\s\S]*obligatorios para trabajadores con contrato laboral[\s\S]*otro sistema/);
  const law = ctx.cxPayCoNotice048O({ state: 'colombia', notice: 'Es una ayuda y no reemplaza la revisión de un contador.', arl_level: 2, reference: { date: '2026-09-25', smmlv: 1750905, transport_allowance: 249095, weekly_hours: 42, night_start: '19:00', sunday_holiday_pct: 90 } });
  assert.match(law, /no reemplaza la revisión de un contador/);
  assert.match(law, /jornada 42 h semanales · nocturno desde 19:00 · dominical\/festivo 90% · ARL nivel 2/);
  assert.equal(ctx.cxPayCoNotice048O(null), '', 'empresa sin el módulo: nada nuevo');
});

test('desglose por empleado: horas por tipo, valor, total y alerta en rojo', () => {
  const html = portal().cxPayCoEmployeeHtml048O(ROW);
  assert.match(html, /Ana Mesera[\s\S]*sin salario configurado: se usa el mínimo/);
  assert.match(html, /class="cx-payco-alert" data-payco-alert="extra_daily">Incumplimiento: 2026-09-22: 3 h extra/);
  assert.match(html, /Ordinaria nocturna[\s\S]*nocturno 35%[\s\S]*1 h[\s\S]*\$11\.255,82/);
  assert.match(html, /<tr class="cx-payco-extra">[\s\S]*Extra diurna[\s\S]*3 h/);
  assert.match(html, /Auxilio de transporte \(1 días\)[\s\S]*\$8\.303,17/);
  assert.match(html, /Descuentos del empleado \(el auxilio no entra en la base\)[\s\S]*Salud empleado 4% sobre \$78\.000,00/);
  assert.match(html, /Prima de servicios 8\.33% sobre \$86\.303,17/);
  assert.match(html, /Neto a pagar<\/span><strong>\$90\.000,00/);
});

test('configuración de salarios y ARL y CSV con el desglose', () => {
  const ctx = portal();
  assert.match(ctx.cxPayCoConfigHtml048O(), /data-payco-config-open>Salarios y ARL/);
  ctx.cxPayCo048O.open = true;
  ctx.cxPayCo048O.config = { arl_level: 2, exonerated: true, employees: [{ id: 'e1', name: 'Ana', role: 'mesero', monthly_salary: 2000000, arl_level: null }] };
  const form = ctx.cxPayCoConfigHtml048O();
  assert.match(form, /<option value="2" selected>Nivel 2<\/option>/);
  assert.match(form, /name="exonerated" checked/);
  assert.match(form, /data-payco-config-employee="e1"[\s\S]*name="salary" value="2000000"/);
  const csv = ctx.cxPayCoCsvRows048O([ROW]);
  assert.ok(csv.some((line) => line[0] === 'Ordinaria nocturna' && line[1] === 'nocturno 35%'));
  assert.ok(csv.some((line) => line[0] === 'ALERTA'));
  assert.equal(ctx.cxPayCoCsvRows048O([{ name: 'x', net: 1 }]).length, 0, 'modo manual: CSV igual que hoy');
});

test('Nómina usa el desglose solo en modo colombiano y no cae a un cálculo local', () => {
  assert.match(source, /\$\{coLaw \? cxPayCoRowsHtml048O\(rows\) : payrollRowsTable\(rows\)\}/);
  assert.match(source, /legalMode: payload\.legal_mode \|\| null,/);
  assert.match(source, /if \(isClientModuleActive\("nomina_colombia"\)\) throw error;/);
  assert.match(source, /modules = modules\.filter\(\(module\) => module\.code !== "nomina_colombia"\);/);
  assert.match(source, /if \(code === "nomina_colombia"\) \{\s*await renderPayrollModule\(\);/);
});

test('Admin V2: interruptor en el catálogo y editor de parámetros por año', () => {
  assert.match(admin, /nomina_colombia: \["APLICAR NORMATIVA LABORAL COLOMBIANA"/);
  assert.match(admin, /\$\{cxPayCoAdminSection048O\(\)\}/);
  assert.match(admin, /cxJsonRequest\("\/payroll-co\/params"\)/);
  assert.match(admin, /cxJsonRequest\(`\/payroll-co\/params\/\$\{year\}\/template`\)/);
  const start = admin.indexOf('  function cxPayCoAdminSection048O(');
  const end = admin.indexOf('\n  function cxPayCoAdminReadForm048O(');
  const formStart = admin.indexOf('  function cxPayCoAdminValue048O(');
  const ctx = vm.createContext({
    escapeHtml: (v) => String(v ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])),
    JSON, Math, Date, Number, String,
  });
  vm.runInContext('var cxPayCoAdmin048O = { loaded: true, fields: [{ key: "smmlv", label: "Salario minimo mensual (SMMLV)", kind: "money" }, { key: "fsp_brackets", label: "Tabla FSP", kind: "json" }], years: [{ year: 2026 }], year: 2026, draft: { year: 2026, params: { smmlv: 1750905, fsp_brackets: [[4, 1]] }, changes: [{ from: "2026-07-15", weekly_hours: 42 }] }, message: "", error: "" };\n'
    + admin.slice(formStart, start) + admin.slice(start, end), ctx);
  const html = ctx.cxPayCoAdminSection048O();
  assert.match(html, /Parámetros de ley por año/);
  assert.match(html, /data-payco-admin-year="2026"/);
  assert.match(html, /data-payco-admin-new="2027">Preparar 2027/);
  assert.match(html, /name="smmlv" data-kind="money" value="1750905"/);
  assert.match(html, /name="fsp_brackets" data-kind="json" rows="2">\[\[4,1\]\]/);
  assert.match(html, /&quot;from&quot;: &quot;2026-07-15&quot;/);
});
