// 049U: Reportes del dueño con el nuevo orden (Asadero): HOY en vivo, ALERTAS,
// EL PERIODO y LA CARTA; gráfica que elige su tipo, venta y margen separados,
// análisis de carta sin nombres encimados y 403 para quien no es el dueño.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');

function portal({ phone = false, v2 = true } = {}) {
  const intervals = [];
  const dom = { live: { innerHTML: '' }, alerts: { innerHTML: '' }, root: { innerHTML: '', querySelector: () => null } };
  const ctx = vm.createContext({
    h: (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
    state: { companyId: 'c1' }, URLSearchParams, Math, Number, String, Array, Object, JSON, Map, Set, Infinity, Date, Promise,
    cxInvCartaOn049Q: () => v2,
    window: { matchMedia: () => ({ matches: phone, addEventListener: () => {} }) },
    setInterval: (fn, ms) => { intervals.push(ms); return intervals.length; }, clearInterval: () => {},
    document: {
      hidden: false,
      getElementById: (id) => (id === 'hspDashRoot024W' ? dom.root : null),
      querySelector: (sel) => (sel === '[data-own-live]' ? dom.live : sel === '[data-own-alerts]' ? dom.alerts : null),
      createElement: () => ({}), head: { appendChild: () => {} },
    },
    cxHspDashRenderEventSearch033B: () => '<events>',
  });
  const a = source.indexOf('  /* CX_OWNER_REPORT_048S_START */');
  const b = source.indexOf('  /* CX_OWNER_REPORT_048S_END */');
  vm.runInContext(source.slice(a, b), ctx);
  ctx.intervals = intervals;
  ctx.dom = dom;
  return ctx;
}

const LIVE = {
  date: '2026-09-28', weekday: 'Lunes', has_sales: true, sales: 1155250, margin: 615283, margin_pct: 53.3, margin_complete: false,
  orders: 38, accounts: 21, ticket: 55012, open_tables: 3, open_total: 184000, deliveries_in_progress: 2, long_open_tables: [],
  compare: { date: '2026-09-21', weekday: 'Lunes', sales_same_time: 1031000, margin_same_time: 500000, sales_full_day: 1500000,
    sales_change_pct: 12.0, margin_change_pct: -4.5, orders_same_time: 30 },
  generated_at: '2026-09-28T20:00:05-05:00', last_close: null,
};

test('HOY: lo vendido y el margen en grande, contra el mismo día de la semana pasada a esta hora', () => {
  const ctx = portal();
  ctx.cxOwn048S.live = LIVE;
  const html = ctx.cxOwnLiveHtml049U();
  assert.match(html, /Hoy · Lunes 28\/09[\s\S]*En vivo · actualizado/);
  assert.match(html, /data-own-today-sales><span>Vendido hoy<\/span><b>\$1\.155\.250<\/b>\s*<small class="good">▲ 12% vs el lunes pasado a esta hora<\/small>/);
  assert.match(html, /Lunes 21\/09: \$1\.031\.000 a esta hora · \$1\.500\.000 el día completo/);
  assert.match(html, /data-own-today-margin><span>Le queda \(margen\)<\/span><b>\$615\.283<\/b>\s*<small class="cx-own-pct-049u">53% de lo vendido<\/small>/);
  assert.match(html, /class="bad">▼ 4,5% vs el lunes pasado a esta hora/);
  assert.match(html, /Margen parcial: hay productos sin precio de entrada/);
  assert.match(html, /Pedidos<\/span><b>38<\/b>[\s\S]*Ticket promedio<\/span><b>\$55\.012<\/b>[\s\S]*Mesas abiertas<\/span><b>3<\/b><small>\$184\.000 en curso<\/small>[\s\S]*Domicilios en curso<\/span><b>2<\/b>/);
  assert.doesNotMatch(html, /vs ayer|vs el domingo/, 'un lunes no se compara con un domingo');
});

test('HOY sin operación: muestra el cierre del último día con su fecha', () => {
  const ctx = portal();
  ctx.cxOwn048S.live = { ...LIVE, has_sales: false, sales: 0, orders: 0, open_tables: 0, deliveries_in_progress: 0,
    last_close: { date: '2026-09-26', weekday: 'Sábado', sales: 980000, margin: 510000, margin_pct: 52, orders: 30, accounts: 18, ticket: 54444, margin_complete: true } };
  const html = ctx.cxOwnLiveHtml049U();
  assert.match(html, /Hoy todavía no hay ventas[\s\S]*data-own-last-close[\s\S]*Último cierre · Sábado 26\/09<\/span><b>\$980\.000<\/b>[\s\S]*Le quedó \(margen\)<\/span><b>\$510\.000<\/b>[\s\S]*52% de lo vendido/);
});

test('HOY se actualiza solo cada 5 s (y las alertas cada minuto) mientras la pantalla está abierta', async () => {
  const ctx = portal();
  let calls = 0;
  ctx.cxHspDashApi024W = async (path) => { calls += 1; return path === '/owner-report/live' ? LIVE : { alerts: [] }; };
  ctx.cxOwn048S.tab = 'owner';
  ctx.cxOwnStartLive049U();
  assert.deepEqual(ctx.intervals, [5000, 60000]);
  await new Promise((r) => setTimeout(r, 0));
  assert.ok(calls >= 2 && ctx.dom.live.innerHTML.includes('$1.155.250'), 'pinta solo el bloque de HOY, sin recargar la página');
  ctx.cxOwnStartLive049U();
  assert.equal(ctx.intervals.length, 2, 'no duplica los relojes');
});

test('403: quien no es el dueño ve el aviso y no se pide nada más', async () => {
  const ctx = portal();
  ctx.cxHspDashApi024W = async () => { throw new Error('403 Forbidden {"detail":"role_not_allowed"}'); };
  await ctx.cxOwnLiveLoad049U();
  assert.equal(ctx.cxOwn048S.forbidden, true);
  assert.match(ctx.cxOwnView049U(), /data-own-forbidden><b>Reportes es solo del dueño del negocio\.<\/b>/);
  assert.doesNotMatch(ctx.cxOwnView049U(), /data-own-period-block|data-own-alerts/);
});

test('ALERTAS justo después de HOY, cada una con el enlace a donde se resuelve', () => {
  const ctx = portal();
  ctx.cxOwn048S.alerts = { alerts: [
    { kind: 'uncosted', severity: 'bad', title: '4 producto(s) sin precio de entrada: el margen está incompleto', detail: '$60.000 vendidos...', items: ['Limonada', 'Jugo', 'Té', 'Agua', 'Café', 'Pan'], link: { module: 'carta', label: 'Completar en Carta' } },
    { kind: 'restock', severity: 'warn', title: '2 insumo(s) agotado(s) o por agotarse', detail: '', items: ['PAPA'], link: { module: 'inventory', mode: 'compras', label: 'Ver Próximas compras' } },
  ] };
  const html = ctx.cxOwnAlertsHtml049U();
  assert.match(html, /data-own-alert="uncosted"[\s\S]*4 producto\(s\) sin precio de entrada[\s\S]*Limonada · Jugo · Té · Agua · Café y 1 más[\s\S]*data-own-go="carta"  data-client-module="carta">Completar en Carta →/);
  assert.match(html, /data-own-go="inventory" data-own-go-mode="compras" data-client-module="inventory">Ver Próximas compras →/);
  ctx.cxOwn048S.live = LIVE;
  ctx.cxOwn048S.summary = { period: { label: 'Últimos 7 días', start: 'a', end: 'b', prev_start: 'c', prev_end: 'd' }, readings: [], kpis: { cards: [], losses: {}, costing: {} } };
  const view = ctx.cxOwnView049U();
  const order = ['data-own-live', 'data-own-alerts', 'data-own-period-block', 'data-own-carta-block'].map((k) => view.indexOf(k));
  assert.deepEqual([...order].sort((x, y) => x - y), order, 'HOY, alertas, periodo, carta');
  assert.ok(order.every((i) => i >= 0));
  assert.match(ctx.cxOwnAlertsHtml049U.call(null) , /Alertas/);
  ctx.cxOwn048S.alerts = { alerts: [] };
  assert.match(ctx.cxOwnAlertsHtml049U(), /Nada pendiente/);
});

test('la gráfica elige su tipo según los datos y explica en una frase qué muestra', () => {
  const ctx = portal();
  const hours = ctx.cxOwnSmartChart049U({ chart: { kind: 'hours', explain: 'Solo hubo ventas el lunes 28/09 (28 días sin operación): una barra por día no diría nada, así que se muestra la venta por hora.' },
    hours: [{ hour: 12, sales: 200000, orders: 5 }, { hour: 13, sales: 400000, orders: 9 }, { hour: 1, sales: 50000, orders: 1 }], days: [] });
  assert.match(hours, /data-own-chart-explain="hours">Solo hubo ventas el lunes 28\/09[\s\S]*se muestra la venta por hora/);
  assert.match(hours, /data-own-chart="hours"[\s\S]*12 p\.m\.[\s\S]*1 p\.m\.[\s\S]*1 a\.m\./);
  const days = ['2026-09-21', '2026-09-22', '2026-09-23'].map((date, i) => ({ date, weekday: 'Lunes', sales: 1155250 - i * 100000, margin: 615283, margin_pct: 53.3 - i }));
  const bars = ctx.cxOwnSmartChart049U({ chart: { kind: 'bars', explain: 'Venta de cada uno de los 3 días...' }, days });
  assert.match(bars, /data-own-chart="bars"/);
  assert.match(bars, /class="pct-axis">100%<\/text>/, 'el margen en su propio eje, en %');
  assert.match(bars, /class="pct-label">53%<\/text>/);
  assert.match(bars, /Venta \(\$, eje izquierdo\)[\s\S]*Margen % \(eje derecho\)/);
  const trend = ctx.cxOwnSmartChart049U({ chart: { kind: 'trend', explain: 'Con 21 días...' }, days: Array.from({ length: 21 }, (_, i) => ({ date: `2026-09-${String(i + 1).padStart(2, '0')}`, weekday: 'Lunes', sales: 1000 * i, margin_pct: 50 })) });
  assert.match(trend, /data-own-chart="trend"[\s\S]*class="sales-line"/);
});

test('análisis de carta: puntos numerados que no se enciman, color por cuadrante y leyenda', () => {
  const ctx = portal();
  const products = Array.from({ length: 8 }, (_, i) => ({ key: `p${i}`, name: `Plato con nombre largo ${i}`, share_pct: 20 + (i % 2) * 0.1, margin_unit: 5000 + (i % 3),
    sales: 100000 - i, quadrant: ['estrella', 'vaca', 'enigma', 'perro'][i % 4] }));
  const svg = ctx.cxOwnScatter049U({ products, thresholds: { popularity_share_pct: 15, avg_margin_unit: 4000 } });
  const dots = [...svg.matchAll(/<circle cx="([\d.]+)" cy="([\d.]+)" r="11"/g)].map((m) => [Number(m[1]), Number(m[2])]);
  assert.equal(dots.length, 8);
  for (let i = 0; i < dots.length; i += 1) for (let j = i + 1; j < dots.length; j += 1) {
    assert.ok(Math.hypot(dots[i][0] - dots[j][0], dots[i][1] - dots[j][1]) >= 22, `los puntos ${i + 1} y ${j + 1} no se enciman`);
  }
  assert.doesNotMatch(svg, /class="dot-label"/, 'sin nombres dentro de la gráfica');
  assert.match(svg, /class="zone"/, 'cada cuadrante con su color de fondo');
  assert.match(svg, /data-own-legend[\s\S]*Estrellas \(2\)[\s\S]*<span class="n">1<\/span>Plato con nombre largo 0[\s\S]*Vacas \(2\)[\s\S]*Enigmas \(2\)[\s\S]*Perros \(2\)/);
  const menu = ctx.cxOwnMenu048S({ products, thresholds: { popularity_share_pct: 15, avg_margin_unit: 4000 } }, ctx.cxOwnScatter049U);
  assert.match(menu, /data-own-legend[\s\S]*data-own-menu-table/, 'la tabla de productos sigue debajo');
});

test('celular: una columna y lo pesado plegado; computador: todo desplegado', () => {
  const phone = portal({ phone: true });
  assert.match(phone.cxOwnFold049U('¿Cuándo se llena?', 'x', { heavy: true, key: 'heatmap' }), /data-own-fold="heatmap" >/);
  assert.match(phone.cxOwnFold049U('Operación', 'x', { key: 'ops' }), /data-own-fold="ops" open>/, 'lo liviano abierto también en el celular');
  const desk = portal({ phone: false });
  assert.match(desk.cxOwnFold049U('¿Cuándo se llena?', 'x', { heavy: true, key: 'heatmap' }), /data-own-fold="heatmap" open>/);
  assert.match(source, /@media \(max-width: 760px\) \{\s*\.cx-own-hero-049u, \.cx-own-alerts-049u \{ grid-template-columns:1fr; \}/);
  assert.match(source, /\.cx-own-cols-049u \{ display:grid; grid-template-columns:repeat\(2, minmax\(0, 1fr\)\)/);
});

test('solo con el interruptor (Asadero): The Time Machine sigue viendo su Reportes de siempre', () => {
  const ttm = portal({ v2: false });
  ttm.cxOwn048S.tab = 'owner';
  ttm.cxOwnPaint048S(true);
  assert.match(ttm.dom.root.innerHTML, /class="cx-own-048s" data-own-048s-root>/);
  assert.doesNotMatch(ttm.dom.root.innerHTML, /cx-own-v2-049u|data-own-live/);
  assert.equal(ttm.intervals.length, 0, 'sin reloj en vivo');
});
