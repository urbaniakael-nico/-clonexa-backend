// Consola v2+ · Facturación: tablero, gráficas con estado vacío, filtros,
// detalle y pestaña de la Ficha. Sin estilos en línea (CSP de v2+).
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { readFileSync } = require('node:fs');

const SRC = readFileSync('app/web/admin_v2plus_billing.js', 'utf8');

function load() {
  const calls = [];
  const window = { location: { href: '', origin: 'https://clonexa.test' }, CxConsolePlus: { initials: (n) => String(n).slice(0, 2).toUpperCase() } };
  const fetch = async (url, opts = {}) => { calls.push({ url, method: opts.method || 'GET' }); return { ok: true, status: 200, json: async () => ({}) }; };
  const ctx = vm.createContext({ window, document: {}, fetch, navigator: {}, JSON, Object, Array, String, Number, Math, Date, Promise, Error, encodeURIComponent, FormData: class {} });
  vm.runInContext(SRC, ctx);
  return { B: window.CxConsoleBilling, window, calls };
}

const card = (id, name, state, extra = {}) => ({
  company: { id, name },
  contract: { contract_type: 'minimo', status: 'vigente', currency: 'COP', min_months: 6, pay_day_from: 15, pay_day_to: 20, start_date: '2026-09-01' },
  type_label: 'Mínimo de meses', has_file: false,
  summary: { state, days_late: state === 'en_mora' ? 4 : 0, months_done: 2, min_months: 6, alerts: [],
    month: { amount: 250, due_from: '2026-10-15', due_date: '2026-10-20' }, next: { amount: 250, due_from: '2026-10-15', due_date: '2026-10-20' } },
  ...extra,
});

const BOARD = {
  kpis: { collected_month: 250, due_month: 450, overdue: 200, expected_monthly: 700 },
  cards: [card('a', 'The Time Machine', 'en_ventana'), card('b', 'Velvet', 'en_mora'), card('c', 'ASADERO', 'al_dia'),
    { company: { id: 'd', name: 'Sin contrato' }, contract: null, type_label: '', has_file: false, summary: { state: 'sin_contrato', alerts: [] } }],
  charts: { by_month: Array.from({ length: 12 }, (_, i) => ({ month: `2026-${String(i + 1).padStart(2, '0')}-01`, label: 'x', expected: 0, collected: 0 })), by_company: [], by_type: [] },
};

test('tablero: indicadores, tarjetas con estado y color, "mes 2 de 6" y filtros', () => {
  const { B } = load();
  B.model.data = BOARD;
  let html = B.boardView();
  for (const kpi of ['Recaudado este mes', 'Por cobrar este mes', 'En mora', 'Ingreso mensual esperado']) assert.match(html, new RegExp(kpi));
  assert.match(html, /vp-bill-kpi-bad/, 'la mora con valor se resalta');
  assert.match(html, /vp-bill-pill is-warn">En ventana de pago/);
  assert.match(html, /vp-bill-pill is-bad">En mora · 4 días/);
  assert.match(html, /vp-bill-pill is-ok">Al día/);
  assert.match(html, /mes 2 de 6/);
  assert.match(html, /15 oct 2026 al 20 oct 2026/);
  assert.match(html, /Adjuntar contrato/);
  assert.match(html, /Crear contrato/, 'la que no tiene contrato invita a crearlo');
  assert.match(html, /Todas · 4/); assert.match(html, /En mora · 1/);
  assert.match(html, /vp-bill-grid vp-zone-scroll/, 'la lista no estira la página');
  B.model.filter = 'en_mora';
  html = B.boardView();
  assert.match(html, /Velvet/); assert.doesNotMatch(html, /The Time Machine/);
});

test('gráficas SVG propias con estado vacío', () => {
  const { B } = load();
  assert.match(B.chartByMonth(BOARD.charts.by_month), /vp-empty/);
  assert.match(B.chartByCompany([]), /vp-empty/);
  assert.match(B.chartByType([]), /vp-empty/);
  const month = B.chartByMonth([{ month: '2026-09-01', label: 'Sep', expected: 250, collected: 250 }, { month: '2026-10-01', label: 'Oct', expected: 250, collected: 0 }]);
  assert.match(month, /^<svg class="vp-bill-chart"/); assert.match(month, /vp-bill-bar-exp/); assert.match(month, /vp-bill-bar-col/);
  assert.match(B.chartByCompany([{ name: 'TTM', collected: 450 }]), /<svg/);
  const donut = B.chartByType([{ label: 'Mínimo de meses', count: 2 }, { label: 'Mensual', count: 1 }]);
  assert.match(donut, /stroke-dasharray/); assert.match(donut, /Mínimo de meses · <b>2/);
  assert.doesNotMatch(SRC, /style="/, 'sin estilos en línea');
  assert.doesNotMatch(SRC, /<script|chart\.js|d3/i, 'sin librerías de gráficas');
});

test('detalle: contrato y tramos, calendario, pagos y comprobantes', () => {
  const { B } = load();
  B.model.companyId = 'a';
  B.model.detail = {
    company: { id: 'a', name: 'The Time Machine' }, types: [{ code: 'minimo', label: 'Mínimo de meses' }], methods: { transferencia: 'Transferencia' },
    contract: { contract_type: 'minimo', start_date: '2026-09-01', min_months: 6, currency: 'COP', pay_day_from: 15, pay_day_to: 20, status: 'vigente', notes: '',
      tiers: [{ month_from: 1, month_to: 2, amount: 250 }, { month_from: 3, month_to: null, amount: 200 }] },
    summary: { state: 'en_mora', days_late: 2, months_done: 2, alerts: [{ kind: 'mora', text: 'Cuota de Octubre 2026 en mora: 2 día(s) de atraso' }] },
    installments: [
      { id: 'i1', seq: 1, period: '2026-09-01', amount: 250, due_from: '2026-09-15', due_date: '2026-09-20', status: 'pagada', validated: 250 },
      { id: 'i2', seq: 2, period: '2026-10-01', amount: 250, due_from: '2026-10-15', due_date: '2026-10-20', status: 'en_mora', days_late: 2, validated: 0 },
      { id: 'i3', seq: 3, period: '2026-11-01', amount: 200, due_from: '2026-11-15', due_date: '2026-11-20', status: 'pendiente', validated: 0 }],
    payments: [
      { id: 'p1', status: 'validado', amount: 250, paid_on: '2026-09-18', method: 'transferencia', reference: 'TRX-1', receipt_id: 'r1', receipt_number: 1, receipt_status: 'vigente', period: '2026-09-01', validated_by: 'admin', validated_at: '2026-09-18T15:00:00Z' },
      { id: 'p2', status: 'por_validar', amount: 250, paid_on: '2026-10-22', method: 'transferencia', reference: '', period: '2026-10-01' },
      { id: 'p3', status: 'anulado', amount: 250, paid_on: '2026-09-02', method: 'transferencia', receipt_id: 'r0', receipt_number: 3, receipt_status: 'anulado', period: '2026-09-01', void_reason: 'Devuelto' }],
    files: [],
  };
  const html = B.detailView();
  assert.match(html, /Meses 1 a 2/); assert.match(html, /Desde el mes 3/);
  assert.match(html, /del 15 al 20 de cada mes/);
  assert.match(html, /Solo es un aviso: nada se suspende ni se bloquea/);
  assert.equal((html.match(/data-vpb-pay="/g) || []).length, 2, 'registrar pago solo en cuotas no pagadas');
  assert.match(html, /data-vpb-validate="p2">Marcar como pago validado/);
  assert.match(html, /CX-000001/); assert.match(html, /Copiar enlace para el cliente/);
  assert.match(html, /data-vpb-void="p1"/);
  assert.match(html, /CX-000003 \(anulado\)/, 'el comprobante anulado sigue visible');
  assert.doesNotMatch(html, /data-vpb-void="p3"/);
  assert.match(html, /\/admin-v2\/api\/billing\/companies\/a\/receipts\/r1\.pdf/);
  assert.match(html, /vp-bill-scroll/, 'calendario y pagos con scroll interno');
  assert.match(html, /Solo PDF, hasta 10 MB/);
});

test('todas las llamadas van a /admin-v2/api con la sesión (same-origin)', () => {
  const urls = [...SRC.matchAll(/request\(`([^`]+)`/g)].map((m) => m[1]);
  assert.ok(urls.length >= 9);
  for (const u of urls) assert.match(u, /^(\$\{API\}|\/admin-v2\/api\/)/, u);
  assert.match(SRC, /const API = "\/admin-v2\/api\/billing"/);
  assert.match(SRC, /credentials: "same-origin"/);
});

test('Ficha: pestaña Facturación y aviso de mora; Centro de mando con alertas', () => {
  const ficha = readFileSync('app/web/admin_v2plus_company.js', 'utf8');
  assert.match(ficha, /\["facturacion", "Facturación"\]/);
  assert.match(ficha, /facturacion: \["billing"\]/);
  assert.match(ficha, /Las demos no facturan/);
  assert.match(ficha, /\$\{billingAlert\(\)\}/);
  const plus = readFileSync('app/web/admin_v2plus.js', 'utf8');
  assert.match(plus, /\/admin-v2\/api\/billing\/alerts/);
  assert.match(plus, /title: `Facturación · \$\{a\.company_name\}`/);
  assert.match(plus, /billing: "Facturación"/);
});
