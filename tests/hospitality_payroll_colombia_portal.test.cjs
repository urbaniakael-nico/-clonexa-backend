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
      'cxPayCoEmployeeHtml048O', 'cxPayCoRowsHtml048O', 'cxPayCoConfigHtml048O', 'cxPayCoCsvRows048O',
      'cxPayMissingRateHtml048P'].map(fn).join('\n'), ctx);
  return ctx;
}

const ROW = {
  employeeId: 'e1', name: 'Ana Mesera', role: 'mesero', net: 90000, discount: 4000,
  colombia: {
    monthly_salary: 1750905, salary_missing: false, worked_days: 1,
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

test('sin aviso con el interruptor apagado; nota del contador con el encendido', () => {
  const ctx = portal();
  assert.equal(ctx.cxPayCoNotice048O({ state: 'manual', notice: 'x' }), '');
  assert.doesNotMatch(source, /Modo manual activo|obligatorios para trabajadores con contrato laboral/);
  const law = ctx.cxPayCoNotice048O({ state: 'colombia', notice: 'Es una ayuda y no reemplaza la revisión de un contador.', arl_level: 2, reference: { date: '2026-09-25', smmlv: 1750905, transport_allowance: 249095, weekly_hours: 42, night_start: '19:00', sunday_holiday_pct: 90 } });
  assert.match(law, /no reemplaza la revisión de un contador/);
  assert.match(law, /jornada 42 h semanales · nocturno desde 19:00 · dominical\/festivo 90% · ARL nivel 2/);
  assert.equal(ctx.cxPayCoNotice048O(null), '', 'empresa sin el módulo: nada nuevo');
});

test('desglose por empleado: horas por tipo, valor, total y alerta en rojo', () => {
  const html = portal().cxPayCoEmployeeHtml048O(ROW);
  assert.match(html, /Ana Mesera[\s\S]*salario base \$1\.750\.905,00/);
  assert.doesNotMatch(html, /data-payco-alert="salary_missing"/);
  assert.match(html, /class="cx-payco-alert" data-payco-alert="extra_daily">Incumplimiento: 2026-09-22: 3 h extra/);
  assert.match(html, /Ordinaria nocturna[\s\S]*nocturno 35%[\s\S]*1 h[\s\S]*\$11\.255,82/);
  assert.match(html, /<tr class="cx-payco-extra">[\s\S]*Extra diurna[\s\S]*3 h/);
  assert.match(html, /Auxilio de transporte \(1 días\)[\s\S]*\$8\.303,17/);
  assert.match(html, /Descuentos del empleado \(el auxilio no entra en la base\)[\s\S]*Salud empleado 4% sobre \$78\.000,00/);
  assert.match(html, /Prima de servicios 8\.33% sobre \$86\.303,17/);
  assert.match(html, /Neto a pagar<\/span><strong>\$90\.000,00/);
});

test('empleado sin salario: marcado en su tarjeta y en la lista, sin asumir nada', () => {
  const ctx = portal();
  const card = ctx.cxPayCoEmployeeHtml048O({ ...ROW, net: 0, colombia: { ...ROW.colombia, salary_missing: true, monthly_salary: 0, alerts: [] } });
  assert.match(card, /data-payco-alert="salary_missing">Sin salario configurado: sus horas se muestran pero no se liquidan/);
  assert.doesNotMatch(card, /salario base/);
  const list = ctx.cxPayMissingRateHtml048P([{ employee_name: 'Ana Mesera', employee_role: 'mesero', minutes: 480 }]);
  assert.match(list, /Empleados sin salario configurado \(1\): no se les liquidó ningún valor[\s\S]*<li>Ana Mesera · mesero · 8 h trabajadas<\/li>/);
  assert.equal(ctx.cxPayMissingRateHtml048P([]), '');
  const simple = ctx.cxPayMissingRateHtml048P([{ employee_name: 'Beto', employee_role: 'caja', minutes: 300, missing: ['valor hora'] }]);
  assert.match(simple, /Empleados sin valor hora configurado \(1\): esas horas quedaron en \$0\.[\s\S]*<li>Beto · caja · 5 h trabajadas · falta valor hora<\/li>/);
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

test('Admin V2: acceso directo al interruptor de normativa colombiana en el Resumen de la empresa', () => {
  assert.match(admin, /\$\{cxPayCoSwitchPanel048R\(company\)\}/);
  const start = admin.indexOf('  function cxPayCoSwitchPanel048R(');
  const end = admin.indexOf('  /* CX_PAYROLL_COLOMBIA_SWITCH_048R_END */');
  const run = (rows) => {
    const ctx = vm.createContext({
      escapeHtml: (v) => String(v ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])),
      cxCompanyModuleRowMap: () => new Map(rows), String,
    });
    vm.runInContext(admin.slice(start, end), ctx);
    return ctx.cxPayCoSwitchPanel048R({ id: 'asadero' });
  };
  const off = run([]);
  assert.match(off, /Nómina: aplicar normativa laboral colombiana[\s\S]*Apagado: cálculo simple/);
  assert.match(off, /data-cx-company-module-toggle\s+data-company-id="asadero"\s+data-module-code="nomina_colombia"\s+data-action="activate">Encender normativa colombiana/);
  assert.match(off, /data-view="modules">Parámetros de ley por año/);
  const on = run([['nomina_colombia', { code: 'nomina_colombia', enabled: true }]]);
  assert.match(on, /cx-badge-live">Encendido[\s\S]*data-action="deactivate">Apagar normativa colombiana/);
  assert.match(admin, /if \(openCompany && String\(state\.selectedCompanyId\) === String\(companyId\)\) renderCompanyDetailTab\(openCompany\);/);
});
