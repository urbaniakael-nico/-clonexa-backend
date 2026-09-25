// Reportes para el dueño (048S) en el portal: solo restaurantes con
// waiter_ordering. Ejecuta las funciones reales de client.js.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');

function fn(name) {
  const start = source.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  var |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

function block(startMarker, endMarker) {
  const a = source.indexOf(startMarker);
  const b = source.indexOf(endMarker);
  assert.ok(a >= 0 && b > a, startMarker);
  return source.slice(a, b);
}

function portal() {
  const ctx = vm.createContext({
    h: (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
    state: { companyId: 'c1' }, URLSearchParams, Math, Number, String, Array, Object, JSON, Map, Set, Infinity,
  });
  vm.runInContext(block('  /* CX_OWNER_REPORT_048S_START */', '  async function cxOwnLoad048S(') , ctx);
  vm.runInContext(['cxOwnPeriodBar048S', 'cxOwnReadings048S', 'cxOwnCard048S', 'cxOwnKpis048S', 'cxOwnSalesChart048S',
    'cxOwnDays048S', 'cxOwnHeatmap048S', 'cxOwnScatter048S', 'cxOwnMenu048S', 'cxOwnTeam048S', 'cxOwnBars048S',
    'cxOwnOps048S', 'cxOwnInventory048S', 'cxOwnCsv048S'].map(fn).join('\n'), ctx);
  return ctx;
}

const SUMMARY = {
  period: { label: 'Últimos 7 días', start: '2026-09-19', end: '2026-09-25', prev_start: '2026-09-12', prev_end: '2026-09-18' },
  readings: ['El sábado vendes 3 veces lo del martes.', 'Se cancelaron $15.000 en 3 pedidos, casi todo entre las 8 p.m. y las 9 p.m.'],
  kpis: {
    cards: [
      { key: 'sales', label: 'Ventas', value: 1200000, kind: 'money', change_pct: 20, better: 'up' },
      { key: 'cost_pct', label: 'Costo de mercancía / venta', value: 42.5, kind: 'pct', change_pct: 5, better: 'down' },
      { key: 'losses', label: 'Mermas y cancelaciones', value: 15000, kind: 'money', change_pct: -30, better: 'down' },
      { key: 'accounts', label: 'Cuentas', value: 40, kind: 'count', change_pct: null, better: 'up' },
    ],
    losses: { merma_total: 40000, merma_count: 1, merma_cost: 20000, cancelled_total: 5000, cancelled_count: 1 },
    costing: { complete: false, uncosted_count: 2, uncosted_sales: 60000, uncosted: [{ name: 'Limonada' }, { name: 'Jugo' }], derived: ['Pollo broster'] },
  },
  busiest_weekday: { enough: false, message: 'Datos insuficientes, se necesitan al menos 3 semanas' },
};

test('indicadores: variación en verde o rojo según qué es mejor, y aviso de lo que falta costear', () => {
  const html = portal().cxOwnKpis048S(SUMMARY);
  assert.match(html, /data-own-kpi="sales"[\s\S]*\$1\.200\.000[\s\S]*class="good">▲ 20\.0% vs periodo anterior/);
  assert.match(html, /data-own-kpi="cost_pct"[\s\S]*42\.5%[\s\S]*class="bad">▲ 5\.0%/, 'subir el costo es malo');
  assert.match(html, /data-own-kpi="losses"[\s\S]*class="good">▼ 30\.0%/, 'bajar las mermas es bueno');
  assert.match(html, /data-own-kpi="accounts"[\s\S]*Sin periodo anterior para comparar/);
  assert.match(html, /data-own-uncosted[\s\S]*Margen incompleto: 2 producto\(s\) sin precio de entrada[\s\S]*\$60\.000 de venta no tienen costo[\s\S]*Limonada, Jugo/);
  assert.match(html, /Costo por porción derivado del entero[\s\S]*Pollo broster/);
  assert.match(html, /Mermas: \$40\.000 en 1 pedido\(s\) \(costo perdido \$20\.000\)/);
  assert.match(portal().cxOwnKpis048S(null), /Calculando/, 'mientras llega: esqueleto, no pantalla en blanco');
});

test('lecturas automáticas arriba; sin lecturas no se muestra el bloque', () => {
  const ctx = portal();
  assert.match(ctx.cxOwnReadings048S(SUMMARY.readings), /data-own-readings[\s\S]*El sábado vendes 3 veces lo del martes\./);
  assert.equal(ctx.cxOwnReadings048S([]), '');
});

test('corrección a y c: día más movido exige 3 repeticiones; solo días con movimiento', () => {
  const ctx = portal();
  const daily = { idle_days: 13, table: [{ date: '2026-09-16', weekday: 'Miércoles', orders: 12, sales: 693000, margin: 300000 }] };
  const html = ctx.cxOwnDays048S(daily, SUMMARY.busiest_weekday);
  assert.match(html, /data-own-idle>13 días sin operación en el periodo\./);
  assert.match(html, /Día más movido de la semana<\/span><b>—<\/b><small>Datos insuficientes, se necesitan al menos 3 semanas/);
  assert.equal((html.match(/<tr><td>/g) || []).length, 1, 'una sola fila: el único día con ventas');
  const ok = ctx.cxOwnDays048S(daily, { enough: true, weekday: 'Sábado', average: 900000, days: 4, plural: 'sábados' });
  assert.match(ok, /<b>Sábado<\/b><small>\$900\.000 promedio en 4 sábados/);
});

const MENU = {
  thresholds: { popularity_share_pct: 17.5, avg_margin_unit: 9000 },
  products: [
    { key: 'a', name: 'POLLO Asado', units: 1.75, units_text: '1 y 3/4', portions_text: '2 de 1/4, 1 de 1/2, 1 entero', sales: 90000, cost: 35000, margin_unit: 31428, margin_total: 55000, costed: true, quadrant: 'estrella', share_pct: 40 },
    { key: 'b', name: 'Gaseosa', units: 12, units_text: '12', portions_text: '', sales: 36000, cost: 30000, margin_unit: 500, margin_total: 6000, costed: true, quadrant: 'vaca', share_pct: 45 },
    { key: 'c', name: 'Limonada', units: 3, units_text: '3', portions_text: '', sales: 18000, cost: null, margin_unit: null, margin_total: null, costed: false },
  ],
};

test('corrección b y análisis de carta: unidades enteras con desglose, cuadrantes y tabla ordenable', () => {
  const ctx = portal();
  const html = ctx.cxOwnMenu048S(MENU);
  assert.match(html, /<td>POLLO Asado<small>2 de 1\/4, 1 de 1\/2, 1 entero<\/small><\/td><td>1 y 3\/4<\/td>/);
  assert.doesNotMatch(html, /1\.75 mov/);
  assert.match(html, /data-own-dot="estrella"[\s\S]*data-own-dot="vaca"/);
  assert.match(html, /Estrellas \(1\)[\s\S]*Protégelos[\s\S]*Vacas \(1\)[\s\S]*Sube el precio o baja el costo[\s\S]*Enigmas \(0\)[\s\S]*Promociónalos[\s\S]*Perros \(0\)[\s\S]*Sácalos de la carta/);
  assert.match(html, /<td>Limonada<\/td><td>3<\/td><td>\$18\.000<\/td><td><em class="bad">Sin costo<\/em>/);
  assert.match(html, /data-own-sort="sales">Venta ▼/);
  ctx.cxOwn048S.sort = { key: 'margin_total', dir: 'desc' };
  const sorted = ctx.cxOwnMenu048S(MENU);
  assert.ok(sorted.indexOf('POLLO Asado</td>') < sorted.indexOf('Gaseosa</td>') || sorted.indexOf('>POLLO Asado<') < sorted.indexOf('>Gaseosa<'));
  assert.match(ctx.cxOwnMenu048S({ products: [], thresholds: null, note: 'Se necesitan al menos 3 productos con costo para clasificar la carta.' }), /al menos 3 productos con costo/);
});

test('corrección d y operación: mesas y domicilios en listas separadas', () => {
  const html = portal().cxOwnOps048S({
    channels: [{ channel: 'mesa', label: 'Mesa', sales: 800000, accounts: 30, ticket: 26666 }, { channel: 'domicilio', label: 'Domicilio', sales: 200000, accounts: 5, ticket: 40000 }],
    payments: [{ label: 'Efectivo', sales: 600000 }, { label: 'Transferencia', sales: 400000 }],
    avg_table_minutes: 55, rotation_per_jornada: 2.5,
    top_tables: [{ name: 'Mesa 3', sales: 120000 }], top_deliveries: [{ name: 'Juan · Calle 5', sales: 60000 }],
  });
  const tables = html.slice(html.indexOf('data-own-top-tables'), html.indexOf('data-own-top-deliveries'));
  const deliveries = html.slice(html.indexOf('data-own-top-deliveries'));
  assert.match(tables, /Mesa 3/);
  assert.doesNotMatch(tables, /Juan/);
  assert.match(deliveries, /Domicilios con más consumo[\s\S]*Juan · Calle 5/);
  assert.match(html, /data-own-channel="domicilio"[\s\S]*5 cuenta\(s\) · ticket \$40\.000/);
  assert.match(html, /55 min[\s\S]*Rotación: 2\.5 veces por mesa en cada jornada/);
});

test('mapa de calor: cada venta en su día de jornada y su hora', () => {
  const html = portal().cxOwnHeatmap048S({ weekdays: ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'], hours: [18, 1], max: 7000,
    cells: [{ weekday: 4, hour: 1, sales: 5000 }, { weekday: 4, hour: 18, sales: 7000 }] });
  assert.match(html, /<span class="hour">6 p\.m\.<\/span><span class="hour">1 a\.m\.<\/span>/);
  assert.match(html, /data-own-cell="4-18" style="background:rgba\(34,197,94,1\.00\)"/);
  assert.match(html, /data-own-cell="4-1" style="background:rgba\(34,197,94,0\.76\)"/);
  assert.match(html, /data-own-cell="5-1" style="background:rgba\(34,197,94,0\.00\)"/);
});

test('equipo: venta por hora trabajada y cocina; inventario: qué comprar hoy', () => {
  const ctx = portal();
  const team = ctx.cxOwnTeam048S({ waiters: [{ name: 'Ana', sales: 40000, tables: 1, ticket: 40000, hours: 2, sales_per_hour: 20000 }, { name: 'Beto', sales: 80000, tables: 2, ticket: 40000, hours: 0, sales_per_hour: null }], excluded_hours: 12 },
    { comandas: 2, slow_pct: 50, slow_minutes: 20, stations: [{ name: 'parrilla', avg_minutes: 20, max_minutes: 25 }], products: [{ name: 'POLLO Asado', avg_minutes: 20, max_minutes: 25 }] });
  assert.match(team, /<td>Ana<\/td>[\s\S]*<b>\$20\.000<\/b>/);
  assert.match(team, /<td>Beto<\/td>[\s\S]*<b>Sin turno<\/b>/);
  assert.match(team, /12 h de turnos cerrados por el sistema sin hora real no cuentan/);
  assert.match(team, /Comandas de más de 20 min<\/span><b class="bad">50%/);
  const inv = ctx.cxOwnInventory048S({ value: 374000, uncosted_items: 2, buy_today: [{ name: 'Papa salada', stock: 2, daily: 1, days: 2 }], coverage: [], idle: [{ name: 'Limonada', stock: 9, value: null }] });
  assert.match(inv, /data-own-buy[\s\S]*Papa salada[\s\S]*alcanza para 2 día\(s\)/);
  assert.match(inv, /Sin rotación en el periodo \(1\)/);
});

test('periodo y exportación: selector, PDF y CSV', () => {
  const ctx = portal();
  ctx.cxOwn048S.summary = SUMMARY;
  const bar = ctx.cxOwnPeriodBar048S();
  for (const label of ['Hoy', 'Ayer', 'Últimos 7 días', 'Este mes', 'Personalizado']) assert.match(bar, new RegExp(`>${label}<`));
  assert.match(bar, /class="active" type="button" data-own-048s data-own-period="7d"/);
  assert.match(bar, /data-own-pdf>PDF para el contador/);
  ctx.cxOwn048S.details = { menu: MENU, daily: { table: [] }, team: { waiters: [] }, operations: { channels: [], payments: [] }, inventory: { buy_today: [] } };
  const csv = ctx.cxOwnCsv048S();
  assert.match(csv, /"POLLO Asado","1 y 3\/4","2 de 1\/4, 1 de 1\/2, 1 entero"/);
  assert.match(csv, /"Limonada","3","","18000","Sin costo"/);
});

test('solo los restaurantes con waiter_ordering ven la pantalla nueva; las demás empresas no cambian', () => {
  assert.match(source, /function cxHspDashPaint024W\(\) \{\s*const root = document\.getElementById\("hspDashRoot024W"\);\s*if \(!root\) return;\s*\/\/ 048S[^\n]*\n\s*if \(cxHspDashRestaurant048H\(\)\) \{/);
  assert.match(source, /function cxHspDashRestaurant048H\(\) \{\s*return isClientModuleActive\("waiter_ordering"\);/);
  assert.match(source, /if \(cxHspDashRestaurant048H\(\) && \(cxOwn048S\.companyId !== state\.companyId \|\| !cxOwn048S\.summary\)\) cxOwnLoad048S\(\);/);
  // El reporte de siempre sigue intacto para las demás.
  assert.match(source, /\$\{cxHspDashRankCard024W\("Mesas con mas consumo", cxHspDashTop024W\(totals\.tables, "total", 6\), "total", cxHspMoney024R\)\}/);
  assert.match(source, /data-own-tab="events">Consumos y reimpresión/);
  assert.match(source, /cxOwn048S\.tab === "events" \? cxHspDashRenderEventSearch033B\(\)/);
});
