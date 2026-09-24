// Tablero de reportes con jornada por horario (048C): sin "Horas operadas",
// comparativo contra la misma jornada de la semana anterior e indicadores de
// bar. Las demás empresas (sin business_day) se ven igual que antes.
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

const NAMES = [
  'cxHspDashNum024W', 'cxHspDashDate024W', 'cxHspDashEmptyBucket024W', 'cxHspDashAggregate024W', 'cxHspDashTop024W',
  'cxHspDashHours024W', 'cxHspDashShiftRange033F', 'cxHspDashRenderChart024W', 'cxHspDashRenderTable024W',
  'cxHspDashRankCard024W', 'cxHspDashEventTime033B', 'cxHspDashEventItems033B', 'cxHspDashEventCard033B',
  'cxHspDashRenderEventSearch033B', 'cxHspDashDefaultEventDate033B', 'cxHspDashBusinessDay048C', 'cxHspDashMinutes048C',
  'cxHspDashDelta048C', 'cxHspDashHourLabel048C', 'cxHspDashIndicators048C', 'cxHspDashStyles048C',
  'cxHspDashKpiRows048D', 'cxHspDashKpiSelector048D', 'cxHspDashRestaurant048H', 'cxHspDashBusiestKpi048H',
  'cxHspWeekdayPlural048H', 'cxHspDashEventActions048H', 'cxHspDashStyles048H', 'cxHspDashFindEvent048H',
  'cxHspDashViewEvent048H', 'cxHspDashPrintEvent048H', 'cxHspStockStyles048E', 'cxHspDashPaint024W',
];

const bucket = (extra) => ({
  key: '', label: '', subtitle: '', closures: 0, orders: 0, total: 0, cash: 0, transfer: 0, card: 0, other: 0,
  products: {}, tables: {}, songs: {}, shifts: [], ...extra,
});

function businessPayload() {
  const day23 = bucket({
    key: '2026-09-23', label: '23 sep', subtitle: '2026', closures: 1, orders: 2, total: 50000, cash: 20000, transfer: 30000,
    tables: { 'Mesa 2': { name: 'Mesa 2', total: 30000, orders: 1 } }, prev_week_date: '2026-09-16', prev_week_total: 40000,
    shifts: [{ opened_at: '2026-09-23T23:00:00Z', closed_at: '2026-09-24T09:00:00Z', is_open: false }],
  });
  const totals = bucket({
    key: 'total', closures: 3, orders: 4, total: 65000, cash: 30000, transfer: 30000, card: 5000,
    tables: { 'Mesa 2': { name: 'Mesa 2', total: 30000, orders: 1 } },
    hours: [{ hour: 18, total: 20000, orders: 1 }, { hour: 2, total: 30000, orders: 1 }],
    top_products_quantity: [{ name: 'Cerveza Aguila', quantity: 4, total: 20000 }],
    top_products_total: [{ name: 'Aguardiente media', quantity: 1, total: 30000 }],
    no_rotation: [{ id: 'inv-agua', name: 'Agua Cristal', stock: 12 }],
    table_sessions: { sessions: 1, avg_consumption: 20000, avg_minutes: 120 },
    cancelled_count: 1, cancelled_total: 8000,
    cancelled: [{ order_number: 'QR-o5', table: 'Mesa 2', total: 8000, reason: 'Vaso roto' }],
  });
  // 30 jornadas de historial (09/09 .. 08/10 ficticias), la más reciente al final
  const history = Array.from({ length: 30 }, (_, i) => bucket({
    key: `h${String(i + 1).padStart(2, '0')}`, label: `J${String(i + 1).padStart(2, '0')}`, subtitle: '2026',
    total: (i + 1) * 1000, orders: 1, cash: (i + 1) * 1000,
  }));
  const snapshot = { periods: [day23], totals, history };
  return {
    company_id: 'c1', timezone: 'America/Bogota', today: '2026-09-24', generated_at: '2026-09-24T15:00:00Z',
    business_day: { enabled: true, open: '18:00', close: '04:00' },
    analytics: { days: snapshot, weeks: snapshot, months: snapshot },
    week_compare: { date: '2026-09-23', total: 50000, orders: 2, previous_date: '2026-09-16', previous_total: 40000, previous_orders: 1 },
    event_search: { date: '2026-09-22', events: [], summary: { events: 0, total: 0, orders: 0, message: 'No hubo ventas en la jornada del 22/09/2026 (22/09 18:00 a 23/09 04:00).' } },
  };
}

function legacyPayload() {
  const payload = businessPayload();
  delete payload.business_day;
  delete payload.week_compare;
  const legacy = { periods: [bucket({ key: '2026-09-23', label: '23 sep', worked_minutes: 600 })], totals: bucket({ key: 'total', worked_minutes: 9833 }) };
  payload.analytics = { days: legacy, weeks: legacy, months: legacy };
  payload.event_search.summary = { events: 0 };
  return payload;
}

const apiCalls = [];
const printed = [];

function dashboard(payload, mode = 'days', kpiDays = 10, restaurant = false) {
  const root = { innerHTML: '', querySelector: () => null };
  const head = { children: [], appendChild(node) { this.children.push(node); } };
  const ctx = vm.createContext({
    h: (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
    cxHspMoney024R: (value) => `$ ${Math.round(Number(value || 0)).toLocaleString('de-DE')}`,
    cxHspDashStatus033E: () => {},
    isClientModuleActive: (code) => restaurant && code === 'waiter_ordering',
    cxHspDashPeriodDefs024W: () => [],
    document: {
      head,
      getElementById: (id) => (id === 'hspDashRoot024W' ? root : head.children.find((node) => node.id === id) || null),
      createElement: () => {
        const node = { id: '', textContent: '', innerHTML: '', attrs: {} };
        node.setAttribute = (k, v) => { node.attrs[k] = v; };
        node.addEventListener = () => {};
        node.remove = () => {};
        return node;
      },
      body: { children: [], appendChild(node) { this.children.push(node); } },
    },
    api: async (path, options) => { apiCalls.push({ path, options }); return { document: { number: 'CC-000007', lines: [] } }; },
    state: { companyId: 'c1' },
    window: { CxSaleDocument: { printDocument: (doc) => printed.push(doc) }, alert: () => {} },
    Intl, Date, Math, Number, String, Array, Object, JSON,
  });
  vm.runInContext(
    `var cxHspDashAnalytics033E = ${JSON.stringify(payload)}; var cxHspDashMode024W = ${JSON.stringify(mode)};
     var cxHspDashEventTimezone033B = "America/Bogota"; var cxHspDashEventDate033B = "2026-09-22";
     var cxHspDashEventSummary033B = cxHspDashAnalytics033E.event_search.summary; var cxHspDashEvents033B = cxHspDashAnalytics033E.event_search.events || [];
     var cxHspDashEventLoading033B = false; var cxHspDashEventError033B = ""; var cxHspDashPainted033E = "";
     var cxHspDashKpiDays048D = ${kpiDays};\n`
      + NAMES.map(fn).join('\n'),
    ctx,
  );
  ctx.cxHspDashPaint024W();
  return { html: root.innerHTML, head, ctx };
}

test('jornada por horario: sin "Horas operadas" en KPI ni en la tabla', () => {
  const { html } = dashboard(businessPayload());
  assert.doesNotMatch(html, /Horas operadas/);
  assert.doesNotMatch(html, /<th>Horas<\/th>/);
  assert.match(html, /<span>Consumo por mesa<\/span><b>\$ 20\.000<\/b><small>Duración prom\. 2 h 00 min<\/small>/);
  assert.match(html, /3 jornada\(s\)/);
});

const kpiRows = (html) => {
  const table = /<table class="hspdash-table-024w">[\s\S]*?<\/table>/.exec(html)[0];
  return [...table.matchAll(/<tr>\s*<td>([^<]+?) 2026/g)].map((m) => m[1].trim());
};

test('KPI vs KPI muestra las últimas 10 jornadas, la más reciente arriba', () => {
  const { html } = dashboard(businessPayload());
  assert.deepEqual(kpiRows(html), ['J30', 'J29', 'J28', 'J27', 'J26', 'J25', 'J24', 'J23', 'J22', 'J21']);
  assert.match(html, /data-hsp-dash-kpi-days="10">10 días/);
  assert.match(html, /hspdash-tab-024w active" type="button" data-hsp-dash-kpi-days="10"/);
});

test('el selector amplía a 20 o 30 jornadas', () => {
  assert.equal(kpiRows(dashboard(businessPayload(), 'days', 20).html).length, 20);
  const rows30 = kpiRows(dashboard(businessPayload(), 'days', 30).html);
  assert.equal(rows30.length, 30);
  assert.equal(rows30[0], 'J30');
  assert.equal(rows30[29], 'J01');
});

test('la gráfica y las vistas semanal/mensual no cambian con el selector', () => {
  const days = dashboard(businessPayload()).html;
  assert.match(days, /data-hsp-sales-period="2026-09-23"/, 'la gráfica sigue con sus periodos');
  const weeks = dashboard(businessPayload(), 'weeks').html;
  assert.doesNotMatch(weeks, /data-hsp-dash-kpi-days/);
  assert.deepEqual(kpiRows(weeks), ['23 sep']);
});

test('la tabla KPI diaria compara contra la misma jornada de la semana anterior', () => {
  const payload = businessPayload();
  payload.analytics.days.history = [payload.analytics.days.periods[0]];
  const { html } = dashboard(payload);
  assert.match(html, /<th>vs sem\. ant\.<\/th>/);
  assert.match(html, /hspdash-delta-cell-048c up" title="2026-09-16: \$ 40\.000">\+25%<\/td>/);
  const weeks = dashboard(businessPayload(), 'weeks').html;
  assert.doesNotMatch(weeks, /vs sem\. ant\./, 'solo aplica en la vista diaria');
});

test('los KPI cuadran entre sí: total, ticket, mesa líder y métodos de pago', () => {
  const { html } = dashboard(businessPayload());
  assert.match(html, /<span>Total vendido<\/span><b>\$ 65\.000<\/b>/);
  assert.match(html, /<span>Ticket promedio<\/span><b>\$ 16\.250<\/b><small>4 pedido\(s\)<\/small>/);
  assert.match(html, /<span>Mesa lider<\/span><b>Mesa 2<\/b>/);
  assert.match(html, /<span>Efectivo<\/span><b>\$ 30\.000<\/b>[\s\S]*<span>Transferencia<\/span><b>\$ 30\.000<\/b>[\s\S]*<span>Tarjeta<\/span><b>\$ 5\.000<\/b>/);
});

test('indicadores de bar: hora pico, top 10, sin rotación, mesas, mermas y semana anterior', () => {
  const { html, head } = dashboard(businessPayload());
  assert.match(html, /Ventas por hora de la jornada · hora pico 02:00/);
  assert.match(html, /hspdash-hour-048c "[\s\S]*<b>18:00<\/b>[\s\S]*hspdash-hour-048c peak[\s\S]*<b>02:00<\/b>/);
  assert.match(html, /Top 10 en unidades[\s\S]*1\. Cerveza Aguila<\/span><b>4 u<\/b>/);
  assert.match(html, /Top 10 en plata[\s\S]*1\. Aguardiente media<\/span><b>\$ 30\.000<\/b>/);
  assert.match(html, /Sin rotación \(1\)[\s\S]*Agua Cristal<\/span><b>12 en stock<\/b>/);
  assert.match(html, /Consumo promedio<\/span><b>\$ 20\.000<\/b>[\s\S]*Duración promedio<\/span><b>2 h 00 min<\/b>/);
  assert.match(html, /1 pedido\(s\)<\/span><b>\$ 8\.000<\/b>[\s\S]*Vaso roto/);
  assert.match(html, /Misma jornada, semana anterior[\s\S]*\$ 50\.000[\s\S]*\$ 40\.000[\s\S]*\+25%/);
  assert.ok(head.children.some((node) => node.id === 'cxHspDashStyles048C'));
});

test('búsqueda de eventos sin datos lo dice con claridad', () => {
  const { html } = dashboard(businessPayload());
  assert.match(html, /No hubo ventas en la jornada del 22\/09\/2026 \(22\/09 18:00 a 23\/09 04:00\)\./);
  assert.match(html, /Jornada por horario \(18:00 a 04:00 del día siguiente\)/);
});

test('las demás empresas (sin jornada por horario) conservan el tablero actual', () => {
  const { html, head } = dashboard(legacyPayload());
  assert.match(html, /<span>Horas operadas<\/span><b>163h 53m<\/b>/);
  assert.match(html, /<th>Horas<\/th>/);
  assert.doesNotMatch(html, /Indicadores del bar|vs sem\. ant\.|Consumo por mesa/);
  assert.match(html, /cierre\(s\)/);
  assert.match(html, /No hay consumos capturados para este día\./);
  assert.ok(!head.children.some((node) => node.id === 'cxHspDashStyles048C'));
  assert.doesNotMatch(html, /data-hsp-dash-kpi-days/, 'sin selector de jornadas');
});

// ------------------------------------------------ ASADERO (waiter_ordering) --
function asaderoPayload() {
  const payload = legacyPayload();
  const totals = payload.analytics.days.totals;
  totals.total = 3200000;
  totals.busiest_weekday = { weekday: 5, label: 'Sábado', total: 1850000, days: 4 };
  totals.songs = { Querida: { name: 'Querida', count: 3 } };
  payload.event_search = {
    date: '2026-09-20',
    events: [{
      id: 'shift1:acc1', type: 'qr', location: 'Mesa 4', label: 'Mesa 4', activation_number: 1,
      started_at: '2026-09-20T18:00:00Z', ended_at: '2026-09-20T20:10:00Z', orders_count: 2,
      order_ids: ['o-1', 'o-2'], order_numbers: ['P-11', 'P-12'], payment_label: 'Efectivo', total: 88000,
      items: [{ name: 'POLLO Asado', quantity: 1, unit_price: 40000, subtotal: 40000 }, { name: 'Gaseosa', quantity: 2, unit_price: 24000, subtotal: 48000 }],
    }],
    summary: { events: 1, qr_events: 1, total: 88000, orders: 2 },
  };
  return payload;
}

test('Asadero: "Día más movido de la semana" en lugar de "Horas operadas"', () => {
  const { html } = dashboard(asaderoPayload(), 'days', 10, true);
  assert.doesNotMatch(html, /Horas operadas|<th>Horas<\/th>/);
  assert.match(html, /<span>Día más movido de la semana<\/span><b>Sábado<\/b><small>\$ 1\.850\.000 en 4 sábados<\/small>/);
});

test('Asadero: sin panel de canciones; The Time Machine lo conserva', () => {
  assert.doesNotMatch(dashboard(asaderoPayload(), 'days', 10, true).html, /Canciones mas pedidas/);
  assert.match(dashboard(businessPayload()).html, /Canciones mas pedidas/);
  assert.match(dashboard(legacyPayload()).html, /Canciones mas pedidas/, 'otras empresas sin cambios');
});

test('Asadero: la búsqueda de eventos permite ver y reimprimir un consumo viejo', async () => {
  const { html, ctx } = dashboard(asaderoPayload(), 'days', 10, true);
  assert.match(html, /data-hsp-event-view="shift1:acc1">Ver<\/button>\s*<button class="client-btn" type="button" data-hsp-event-print="shift1:acc1" >Imprimir/);

  ctx.cxHspDashViewEvent048H('shift1:acc1');
  const sheet = ctx.document.body.children.find((node) => node.id === 'hspEventView048H');
  assert.match(sheet.innerHTML, /<h2>Mesa 4<\/h2>/);
  assert.match(sheet.innerHTML, /POLLO Asado[\s\S]*Gaseosa/);
  assert.match(sheet.innerHTML, /\$ 88\.000/);

  apiCalls.length = 0; printed.length = 0;
  await ctx.cxHspDashPrintEvent048H('shift1:acc1');
  assert.equal(apiCalls.length, 1);
  assert.equal(apiCalls[0].path, '/companies/c1/waiter-ordering/sale-document/reprint');
  assert.deepEqual(JSON.parse(apiCalls[0].options.body), { order_ids: ['o-1', 'o-2'] });
  assert.equal(printed[0].number, 'CC-000007', 'imprime con el formato del documento de venta');
});

test('otras empresas no ven Ver/Imprimir ni pierden sus accesos del encabezado', () => {
  const payload = asaderoPayload();
  assert.doesNotMatch(dashboard(payload, 'days', 10, false).html, /data-hsp-event-view|data-hsp-event-print/);
  const source = readFileSync('app/web/client.js', 'utf8');
  assert.match(source, /\$\{cxHspDashRestaurant048H\(\) \? "" : `<button class="client-btn" type="button" data-client-module="orders">Pedidos<\/button>\s*<button class="client-btn" type="button" data-client-module="qr">Mesa QR<\/button>`\}/);
});
