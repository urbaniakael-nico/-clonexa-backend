// Costos (048V) en el portal y arqueo a ciegas (048U) en el panel de caja.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const client = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');
const cashier = readFileSync('app/web/hsp_cashier.js', 'utf8').replace(/\r\n/g, '\n');
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function cashierFns(state) {
  const pick = (name) => {
    const start = cashier.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
    assert.ok(start >= 0, name);
    const tail = cashier.slice(start + 3);
    const next = tail.search(/\n  (?:async )?function /);
    return tail.slice(0, next) + '\n';
  };
  const ctx = vm.createContext({ h: esc, state, Math, Number, Object, JSON, String });
  vm.runInContext(['money048U', 'costosOverlay048U'].map(pick).join('\n'), ctx);
  return ctx;
}

test('caja: el conteo es a ciegas, sin lo esperado en pantalla', () => {
  const ctx = cashierFns({ arqueo: { step: 'count', busy: false, result: null, message: '' }, denominations: [50000, 20000], costosCats: {} });
  const html = ctx.costosOverlay048U();
  assert.match(html, /No vas a ver cuánto debería haber<\/b> hasta registrar tu conteo/);
  assert.match(html, /data-csh-arq-total/);
  assert.match(html, /data-csh-den="50000"/);
  assert.doesNotMatch(html, /Debía haber|expected/i, 'no revela lo esperado antes de contar');
});

test('caja: después del conteo revela lo esperado, la diferencia y exige observación', () => {
  const result = { id: 'k1', counted: 690000, expected: 700000, difference: -10000, base: 200000, cash_sales: 500000, drawer_expenses: 0, withdrawals: 0, needs_observation: true };
  const html = cashierFns({ arqueo: { step: 'result', busy: false, result, message: '' }, denominations: [], costosCats: {} }).costosOverlay048U();
  assert.match(html, /Contaste<\/span><b>\$690\.000[\s\S]*Debía haber<\/span><b>\$700\.000/);
  assert.match(html, /class="bad"><span>Faltante<\/span><b>\$10\.000/);
  assert.match(html, /Explica la diferencia \(obligatorio\)[\s\S]*data-csh-arq-save-obs/);
  const ok = cashierFns({ arqueo: { step: 'result', busy: false, result: { ...result, counted: 700000, difference: 0, needs_observation: false }, message: '' }, denominations: [], costosCats: {} }).costosOverlay048U();
  assert.match(ok, /<span>Cuadra<\/span>[\s\S]*data-csh-arq-finish\s*>Cerrar jornada/);
});

test('caja: "Cerrar jornada" pasa por el arqueo solo con Costos; gasto del cajón', () => {
  assert.match(cashier, /if \(target\.closest\("\[data-csh-shift-finish\]"\)\) \{\s*\/\/ 048U[^\n]*\n\s*if \(state\.costos\) \{\s*openArqueo048U\(\);\s*return;\s*\}\s*if \(window\.confirm/);
  assert.match(cashier, /\$\{state\.costos \? `<button class="csh-btn" type="button" data-csh-gasto-open>Registrar gasto del cajón<\/button>` : ""\}/);
  const gasto = cashierFns({ gasto: { busy: false, message: '' }, costosCats: { aseo: 'Aseo', otros: 'Otros' }, denominations: [] }).costosOverlay048U();
  assert.match(gasto, /Queda pendiente de aprobación y se descuenta de lo que debe haber en tu arqueo/);
  assert.match(gasto, /<option value="aseo">Aseo<\/option>/);
});

function costosPortal(data, meta) {
  const a = client.indexOf('  /* CX_COSTOS_048V_START */');
  const b = client.indexOf('  document.addEventListener("change", (event) => {\n    if (event.target && event.target.closest && event.target.closest("#cxCosRoot048V"))');
  const ctx = vm.createContext({ h: esc, state: { companyId: 'c1' }, Math, Number, String, Array, Object, JSON, Map, Date });
  vm.runInContext(client.slice(a, b), ctx);
  ctx.cxCos048V.meta = meta;
  ctx.cxCos048V.data = data;
  return ctx;
}

const META = { categories: { compras: 'Compra de insumos', aseo: 'Aseo' }, payment_methods: { efectivo: 'Efectivo', credito: 'Crédito (por pagar)' },
  paid_from: { cajon: 'Efectivo del cajón de ventas', banco: 'Banco' }, settings: { approval_threshold: 500000, drawer_base: 200000, iva_is_cost: true }, cost_centers: [{ name: 'Principal', is_default: true }] };

test('portal: egresos con aprobación, soporte y exportación para el contador', () => {
  const ctx = costosPortal({ expenses: { start: '2026-09-01', end: '2026-09-27', total: 30000, expenses: [
    { id: 'e1', expense_date: '2026-09-26', category_label: 'Otros', description: 'Hielo', created_by_name: 'Carla', created_by_kind: 'cashier', supplier_name: '', total: 30000, iva: 0, retention: 0, status: 'pendiente', has_attachment: false },
  ] } }, META);
  const html = ctx.cxCosExpensesHtml048V();
  assert.match(html, /data-cos-export>Exportar para el contador \(CSV\)/);
  assert.match(html, /Carla · desde la caja[\s\S]*<b>Pendiente<\/b>[\s\S]*data-cos-approve="e1">Aprobar[\s\S]*data-cos-reject="e1">Rechazar/);
  assert.match(html, /Subir foto<input type="file" accept="image\/\*" data-cos-att="e1">/);
});

test('portal: arqueos pendientes muestran lo esperado al dueño y el histórico por cajero', () => {
  const ctx = costosPortal({ pending: { pending: [{ session_id: 's1', cashier_name: 'Carla', shift_start: '2026-09-26T13:00:00', closed_reason: 'corte_diario', expected: 500000, base: 200000, cash_sales: 300000, drawer_expenses: 0, withdrawals: 0 }] },
    counts: { counts: [{ created_at: '2026-09-25T23:00:00', cashier_name: 'Carla', expected: 700000, counted: 690000, difference: -10000, result: 'faltante', observation: 'Vueltas', blind: true }],
      by_cashier: [{ cashier_name: 'Carla', counts: 1, shortage: 10000, surplus: 0 }] } }, META);
  const html = ctx.cxCosCountsHtml048V();
  assert.match(html, /Carla · turno 2026-09-26 13:00 \(cerrado por el corte diario\)[\s\S]*Esperado en el cajón: <b>\$500\.000<\/b>/);
  assert.match(html, /Observación \(obligatoria si hay diferencia\)/);
  assert.match(html, /data-cos-by-cashier[\s\S]*<td>Carla<\/td><td>1<\/td><td class="bad">\$10\.000/);
});

test('portal: presupuesto marca lo que se pasó y el Dashboard avisa', () => {
  const ctx = costosPortal({ budget: { month: '2026-09', categories: { aseo: 'Aseo' }, rows: [{ category: 'aseo', budget: 100000, real: 130000, pct: 130, over: true }] } }, META);
  assert.match(ctx.cxCosBudgetHtml048V(), /<tr class="rechazado"><td>Aseo<\/td>[\s\S]*130%[\s\S]*Se pasó/);
  ctx.state.dashboardMetrics = { costos048V: { pending_approvals: 2, pending_total: 45000, due_this_week: [{}], due_this_week_total: 93200, over_budget: [{ label: 'Aseo' }], pending_counts: 1 } };
  assert.match(ctx.cxCosDashboardBanner048V(), /2 egreso\(s\) por aprobar \(\$45\.000\) · cuentas por pagar que vencen esta semana: \$93\.200 · presupuesto superado en Aseo · 1 turno\(s\) de caja sin arqueo/);
  ctx.state.dashboardMetrics = {};
  assert.equal(ctx.cxCosDashboardBanner048V(), '');
  assert.match(client, /if \(code === "costos"\) \{\s*await renderCostosModule048V\(\);/);
  assert.match(client, /\$\{cxOwnSection048S\("Equipo", cxOwnTeam048S\(d\?\.team, d\?\.kitchen\) \+ cxOwnCashCounts048U\(d\?\.cash_counts \|\| \[\]\), !d\)\}/);
});
