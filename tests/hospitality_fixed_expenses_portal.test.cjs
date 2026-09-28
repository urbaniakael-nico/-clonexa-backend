// 049M en el portal: Gastos fijos en Inventario (tabla mes a mes con suma
// por concepto y total, recibo), estado de resultados en Reportes y el arqueo
// en el panel de caja (Costos ya no existe).
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');
const cashier = readFileSync('app/web/hsp_cashier.js', 'utf8');

function portal() {
  const calls = [];
  const fields = {};
  const root = { querySelector: (sel) => (sel in fields ? fields[sel] : null), innerHTML: '', dataset: {}, addEventListener() {} };
  const ctx = vm.createContext({
    h: (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
    state: { companyId: 'c1' }, Math, Number, String, Array, Object, JSON, Date,
    FormData: class { constructor() { this.parts = []; } append(k, v) { this.parts.push([k, v]); } },
    api: async (path, options = {}) => { calls.push({ path, method: options.method || 'GET', body: options.body ? JSON.parse(options.body) : null }); return ctx.respond(path); },
    apiForm: async (path, form) => { calls.push({ path, method: 'POST', form: form.parts }); return {}; },
    document: { getElementById: () => root, addEventListener() {}, createElement: () => ({}), head: { appendChild() {} } },
  });
  const a = source.indexOf('  /* CX_INVENTORY_049M_START */');
  const b = source.indexOf('  /* CX_INVENTORY_049M_END */');
  vm.runInContext(source.slice(a, b), ctx);
  ctx.respond = () => DATA;
  ctx.calls = calls;
  ctx.fields = fields;
  return ctx;
}

const DATA = {
  groups: { servicios: 'Servicios públicos', arriendo: 'Arriendo', otros: 'Otros gastos' },
  concepts: [
    { key: 'agua', label: 'Agua', group: 'servicios' }, { key: 'luz', label: 'Luz', group: 'servicios' },
    { key: 'gas', label: 'Gas', group: 'servicios' }, { key: 'internet', label: 'Internet', group: 'servicios' },
    { key: 'arriendo', label: 'Arriendo', group: 'arriendo' }, { key: 'aseo', label: 'Aseo', group: 'otros' },
    { key: 'mantenimiento', label: 'Mantenimiento', group: 'otros' }, { key: 'fumigacion', label: 'Fumigación', group: 'otros' },
    { key: 'vigilancia', label: 'Vigilancia', group: 'otros' },
  ],
  records: [{ id: 'r1', concept_label: 'Luz', month: '2026-09', amount: 216000, observation: '', has_receipt: true }],
  table: {
    months: ['2026-08', '2026-09'],
    rows: [
      { concept_key: 'luz', label: 'Luz', group: 'servicios', by_month: { '2026-08': 180000, '2026-09': 216000 }, total: 396000, change_pct: 20 },
      { concept_key: 'arriendo', label: 'Arriendo', group: 'arriendo', by_month: { '2026-08': 2500000, '2026-09': 2500000 }, total: 5000000, change_pct: 0 },
    ],
    totals_by_month: { '2026-08': 2680000, '2026-09': 2716000 }, total: 5396000,
  },
};

test('Gastos fijos: conceptos por grupo, tabla mes a mes con total por concepto y por mes', () => {
  const ctx = portal();
  ctx.cxFix049M.data = DATA;
  const html = ctx.cxFixPanelHtml049M();
  assert.match(html, /<optgroup label="Servicios públicos"><option value="agua">Agua<\/option><option value="luz">Luz<\/option><option value="gas">Gas<\/option><option value="internet">Internet<\/option><\/optgroup><optgroup label="Arriendo"><option value="arriendo">Arriendo<\/option><\/optgroup><optgroup label="Otros gastos"><option value="aseo">Aseo<\/option><option value="mantenimiento">Mantenimiento<\/option><option value="fumigacion">Fumigación<\/option><option value="vigilancia">Vigilancia<\/option>/);
  assert.match(html, /data-fix-concept-open>\+ Concepto propio/);
  assert.match(html, /type="month" data-fix-month/);
  assert.match(html, /accept="image\/jpeg,image\/png,image\/webp" data-fix-receipt/);
  assert.match(html, /<th class="num">ago 2026<\/th><th class="num">sep 2026<\/th><th class="num">Total<\/th>/);
  assert.match(html, /data-fix-row="luz"><td><b>Luz<\/b> <small class="up">▲ 20\.0%<\/small><\/td><td class="num">\$180\.000<\/td><td class="num">\$216\.000<\/td><td class="num"><b>\$396\.000<\/b>/);
  assert.match(html, /Total del mes<\/b><\/td><td class="num"><b>\$2\.680\.000<\/b><\/td><td class="num"><b>\$2\.716\.000<\/b><\/td><td class="num"><b>\$5\.396\.000/);
  assert.match(html, /data-fix-view="r1">Ver recibo/);
});

test('Gastos fijos: guardar con recibo y validaciones', async () => {
  const ctx = portal();
  ctx.cxFix049M.data = DATA;
  ctx.respond = (path) => (path.endsWith('/records') ? { ...DATA, created_id: 'n1' } : DATA);
  Object.assign(ctx.fields, {
    '[data-fix-concept]': { value: 'luz' }, '[data-fix-month]': { value: '2026-09' }, '[data-fix-amount]': { value: '' },
    '[data-fix-observation]': { value: '' }, '[data-fix-receipt]': { files: [{ name: 'recibo.jpg' }] },
  });
  const click = (attr) => ctx.cxFixHandleClick049M({ closest: (sel) => (sel === `[${attr}]` ? { getAttribute: () => '' } : null) });
  await click('data-fix-save');
  assert.match(ctx.cxFix049M.error, /Escribe el valor/);
  ctx.fields['[data-fix-amount]'] = { value: '216000' };
  await click('data-fix-save');
  const create = ctx.calls.find((c) => c.path === '/fixed-expenses/companies/c1/records');
  assert.deepEqual(JSON.parse(JSON.stringify(create.body)), { concept_key: 'luz', month: '2026-09', amount: 216000, observation: '' });
  const upload = ctx.calls.find((c) => c.form);
  assert.equal(upload.path, '/fixed-expenses/companies/c1/records/n1/receipt');
  assert.match(ctx.cxFix049M.message, /con su recibo/);
});

test('Reportes: estado de resultados que descuenta los gastos fijos', () => {
  const start = source.indexOf('  function cxOwnIncome049M(st) {');
  const end = source.indexOf('  function cxOwnSection048S(title, body, loading) {');
  const ctx = vm.createContext({ h: (v) => String(v ?? ''), Number, cxOwnMoney048S: (v) => `$${Math.round(Number(v) || 0).toLocaleString('es-CO')}` });
  vm.runInContext(source.slice(start, end), ctx);
  const html = ctx.cxOwnIncome049M({ sales: 1000000, cost_of_goods: 400000, gross_margin: 600000, fixed_expenses: 400000, has_fixed_expenses: true,
    fixed_by_concept: [{ label: 'Arriendo', amount: 300000 }, { label: 'Luz', amount: 100000 }], operating_profit: 200000 });
  assert.match(html, /Utilidad real: ya descuenta arriendo y servicios/);
  assert.match(html, /Ventas<\/span><b>\$1\.000\.000[\s\S]*− Costo de mercancía<\/span><b>\$400\.000[\s\S]*= Margen bruto<\/span><b>\$600\.000[\s\S]*− Gastos fijos<\/span><b>\$400\.000[\s\S]*Arriendo<\/span><b>\$300\.000[\s\S]*= Utilidad después de gastos fijos<\/span><b>\$200\.000/);
  const bare = ctx.cxOwnIncome049M({ sales: 1, cost_of_goods: 0, gross_margin: 1, fixed_expenses: 0, operating_profit: 1, has_fixed_expenses: false,
    warning: 'Sin gastos fijos cargados, esta cifra es margen bruto, no utilidad real.' });
  assert.match(bare, /data-own-no-fixed><strong>Sin gastos fijos cargados, esta cifra es margen bruto, no utilidad real\.<\/strong>/);
  assert.match(bare, /= Margen bruto \(faltan los gastos fijos\)/);
  assert.doesNotMatch(bare, /Utilidad después de gastos fijos/, 'nunca la llama utilidad sin los gastos');
  assert.match(source, /const note = card\.note \? `<small class="bad" data-own-kpi-note>\$\{h\(card\.note\)\}<\/small>` : "";/);
  assert.match(source, /\$\{cxOwnKpis048S\(s\)\}\n      \$\{cxOwnIncome049M\(s\?\.income_statement\)\}/);
});

test('Costos ya no está en el portal y el arqueo vive en el panel de caja', () => {
  assert.doesNotMatch(source, /renderCostosModule048V|CX_COSTOS_048V|\/costos\/companies/);
  assert.doesNotMatch(source, /costos: \["Costos"/);
  assert.match(cashier, /\/api\/v1\/caja-arqueo\/companies\/\$\{encodeURIComponent\(companyId\)\}\$\{path\}/);
  assert.doesNotMatch(cashier, /\/api\/v1\/costos\//);
  assert.doesNotMatch(cashier, /data-csh-gasto-open|Registrar gasto del cajón/);
  assert.match(cashier, /data-csh-arq-submit/);
});
