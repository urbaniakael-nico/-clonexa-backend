// Tarjeta "SIN STOCK" del Dashboard (048E), solo con qr_bar_menu (The Time
// Machine). Las demás empresas conservan "Stock bajo".
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');

function fn(name) {
  const start = source.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

const INVENTORY = [
  { id: 'i1', name_reference: 'Cerveza Aguila', current_stock: 0, min_stock: 12, status: 'inactive' }, // desactivado solo al llegar al mínimo
  { id: 'i2', name_reference: 'Aguardiente media', current_stock: 0, min_stock: 2, status: 'active' },
  { id: 'i3', name_reference: 'Club Colombia', current_stock: 3, min_stock: 6, status: 'inactive' },   // por acabarse
  { id: 'i4', name_reference: 'Agua Cristal', current_stock: 4, min_stock: 4, status: 'active' },       // por acabarse
  { id: 'i5', name_reference: 'Ron viejo', current_stock: 0, min_stock: 1, status: 'deleted' },         // eliminado: no cuenta
  { id: 'i6', name_reference: 'Coca Cola', current_stock: 40, min_stock: 10, status: 'active' },
];

function client({ barMenu = true, metrics = {} } = {}) {
  const body = { children: [], appendChild(node) { this.children.push(node); } };
  const head = { children: [], appendChild(node) { this.children.push(node); } };
  const kpis = [];
  const ctx = vm.createContext({
    h: (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
    cxHspMoney024R: (value) => `$ ${Number(value || 0)}`,
    cxHspSongByTableOn048B: () => barMenu,
    crmUseMundoCaseAreaMode024C: () => false,
    visibleClientModules: (modules) => modules,
    clientModuleCodes: () => new Set(['hospitality']),
    clientHasHospitalityDashboard025I: () => true,
    state: { dashboardMetrics: { hospitalityDashboard025I: metrics } },
    document: {
      body, head,
      getElementById: (id) => [...body.children, ...head.children].find((node) => node.id === id) || null,
      createElement: () => {
        const node = { id: '', className: '', innerHTML: '', textContent: '', attrs: {}, listeners: {} };
        node.setAttribute = (k, v) => { node.attrs[k] = v; };
        node.addEventListener = (type, cb) => { node.listeners[type] = cb; };
        node.remove = () => { body.children = body.children.filter((child) => child !== node); };
        return node;
      },
      querySelectorAll: () => kpis,
      querySelector: () => null,
    },
    Number, String, Array, Map, Set, Object, JSON, Math,
  });
  vm.runInContext(
    ['cxHspOutOfStockOn048E', 'cxHspStockAlerts048E', 'cxHspStockCardView048E', 'cxHspOpenOutOfStock048E',
      'cxHspStockStyles048E', 'buildClientHeroKpis', 'renderClientHeroKpis', 'cxHspDashboardPendingBanner030D',
      'cxHspPaintDashboardMetrics030D'].map(fn).join('\n'),
    ctx,
  );
  return { ctx, body, head, kpis };
}

test('cuenta los artículos en cero (también los desactivados solos) y aparte los de stock bajo', () => {
  const { ctx } = client();
  const result = JSON.parse(JSON.stringify(ctx.cxHspStockAlerts048E(INVENTORY)));
  assert.equal(result.outOfStock, 2);
  assert.deepEqual(result.outOfStockItems.map((row) => [row.name, row.status]), [
    ['Aguardiente media', 'active'], ['Cerveza Aguila', 'inactive'],
  ]);
  assert.equal(result.lowStockSoon, 2, 'Club Colombia y Agua Cristal están por acabarse');
});

test('con artículos agotados la tarjeta SIN STOCK es roja, con el número y la línea de stock bajo', () => {
  const metrics = client().ctx.cxHspStockAlerts048E(INVENTORY);
  const { ctx, head } = client({ metrics });
  const html = ctx.renderClientHeroKpis([{ code: 'hospitality' }]);
  assert.match(html, /<button class="client-kpi hsp-kpi-stock-048e danger" type="button" data-client-kpi-label="SIN STOCK" data-hsp-out-of-stock-048e>\s*<span>SIN STOCK<\/span>\s*<strong>2<\/strong>\s*<small>además, 2 con stock bajo<\/small>/);
  assert.doesNotMatch(html, /Stock bajo<\/span>/);
  assert.ok(head.children.some((node) => node.id === 'cxHspStockStyles048E'));
});

test('sin agotados la tarjeta es verde con "Todo con stock" y conserva la línea de stock bajo', () => {
  const metrics = client().ctx.cxHspStockAlerts048E(INVENTORY.filter((row) => Number(row.current_stock) > 0));
  const html = client({ metrics }).ctx.renderClientHeroKpis([{ code: 'hospitality' }]);
  assert.match(html, /hsp-kpi-stock-048e ok[\s\S]*<strong>Todo con stock<\/strong>\s*<small>además, 2 con stock bajo<\/small>/);
});

test('al tocarla abre la lista de los artículos agotados', () => {
  const metrics = client().ctx.cxHspStockAlerts048E(INVENTORY);
  const { ctx, body } = client({ metrics });
  ctx.cxHspOpenOutOfStock048E();
  const sheet = body.children.find((node) => node.id === 'hspOutOfStock048E');
  assert.ok(sheet, 'se abre la lista');
  assert.match(sheet.innerHTML, /Sin stock \(2\)/);
  assert.match(sheet.innerHTML, /Aguardiente media<\/span>\s*<b>Agotado<\/b>/);
  assert.match(sheet.innerHTML, /Cerveza Aguila<\/span>\s*<b>Agotado · inactivo<\/b>/);
  assert.doesNotMatch(sheet.innerHTML, /Club Colombia|Ron viejo|Coca Cola/);
  assert.match(source, /if \(target\.closest\("\[data-hsp-out-of-stock-048e\]"\)\) \{\s*cxHspOpenOutOfStock048E\(\);/);
});

test('el refresco automático actualiza número, línea y color', () => {
  const metrics = client().ctx.cxHspStockAlerts048E(INVENTORY);
  const { ctx, kpis } = client({ metrics });
  const classes = new Set(['client-kpi', 'hsp-kpi-stock-048e', 'ok']);
  const strong = { textContent: 'Todo con stock' };
  const small = { textContent: '' };
  kpis.push({
    getAttribute: () => 'SIN STOCK',
    hasAttribute: (name) => name === 'data-hsp-out-of-stock-048e',
    querySelector: (sel) => (sel === 'strong' ? strong : small),
    classList: { toggle: (name, on) => (on ? classes.add(name) : classes.delete(name)) },
  });
  ctx.cxHspPaintDashboardMetrics030D(metrics);
  assert.equal(strong.textContent, '2');
  assert.equal(small.textContent, 'además, 2 con stock bajo');
  assert.ok(classes.has('danger') && !classes.has('ok'));
});

test('las demás empresas conservan la tarjeta "Stock bajo"', () => {
  const { ctx } = client({ barMenu: false, metrics: { lowStock: 3 } });
  const html = ctx.renderClientHeroKpis([{ code: 'hospitality' }]);
  assert.match(html, /<div class="client-kpi" data-client-kpi-label="Stock bajo" >\s*<span>Stock bajo<\/span>\s*<strong>3<\/strong>/);
  assert.doesNotMatch(html, /SIN STOCK|hsp-kpi-stock-048e/);
  assert.match(source, /items\?include_inactive=\$\{outOfStockCard \? "true" : "false"\}/, 'solo con el interruptor pide inactivos');
});
