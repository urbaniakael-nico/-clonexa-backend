// 072A: Avisos por WhatsApp (whatsapp_group_reports): pantalla de configuración, historial y
// el botón del Board de gerencia (solo cuando el servidor dice group_reports: true).
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const SRC = readFileSync('app/web/group_reports.js', 'utf8');
const CSS = readFileSync('app/web/group_reports.css', 'utf8');
const BOARD = readFileSync('app/web/reports_board.js', 'utf8');
const FIX = JSON.parse(readFileSync('tests/fixtures/reports_board_caso.json', 'utf8'));

function load(src, fetchImpl) {
  const window = { addEventListener() {} };
  const document = { addEventListener() {}, createElement: () => ({ style: {}, remove() {} }), head: { appendChild() {} }, hidden: false };
  const localStorage = { getItem: () => null, setItem() {} };
  vm.runInNewContext(src, { window, document, console, Intl, Date, setTimeout, clearTimeout, setInterval: () => 1, clearInterval() {}, localStorage, URLSearchParams, URL, fetch: fetchImpl });
  return window;
}

const DATA = {
  ok: true,
  n8n_ready: true,
  timezones: ['America/New_York', 'America/Chicago'],
  kinds: [{ key: 'checkin', label: 'Corte de entrada' }, { key: 'checkout', label: 'Corte de salida' }, { key: 'owners_daily', label: 'Resumen del día a dueños' }],
  locations: [{ id: 'va', name: 'Virginia', timezone: 'America/New_York' }, { id: 'al', name: 'Alabama', timezone: 'America/Chicago' }],
  config: {
    test_mode: true, own_number: '13468244098', clonexa_email: 'clonexa@example.test',
    operations: [{ location_id: 'al', group_jid: '120363000000000002@g.us', group_name: 'VOLTAGE Alabama' }],
    supervisor: { name: 'Noel Dubon', phone: '17030000001', email: '', location_id: 'al' },
    owners: [{ name: 'Adriana', phone: '17030000002', email: 'a@example.test' }],
    weekly_location_id: 'va', weekly_weekday: 4, followup_time: '09:00', checkin_after_min: 30, checkout_after_min: 30, summary_after_min: 30,
    totals_weekday: 0, totals_time: '08:00', totals_tz: 'America/New_York', kinds: { checkin: true, checkout: false, owners_daily: true },
  },
};

function screen(extra = {}) {
  const w = load(SRC);
  const G = w.CxGroupReports;
  Object.assign(G.model, { data: JSON.parse(JSON.stringify(DATA)), items: [], error: '', notice: '', busy: false, denied: false }, extra);
  G._ctx({ companyId: 'c1', apiBase: '/api/v1', token: () => 't', host: () => null, back() {} });
  return G;
}

test('configuración: modo prueba, destinatarios, horas y tipos con "Enviar prueba ahora"', () => {
  const G = screen();
  const html = G.view();
  for (const s of ['Avisos por WhatsApp', 'Modo prueba', 'nada sale a grupos, supervisor ni dueños', 'Grupos por operación', 'Virginia', 'Alabama',
    '120363000000000002@g.us', 'Noel Dubon', 'Dueños (resumen diario y totales de la semana)', 'Adriana', 'Corte de entrada (min después)',
    'Recordatorio extra del timesheet (día siguiente)', 'Totales de la semana: hora', 'Enviar prueba ahora', 'Guardar configuración', 'Historial de avisos',
    'Todavía no hay avisos.']) assert.ok(html.includes(s), s);
  assert.equal((html.match(/data-gr-test="/g) || []).length, 3, 'un botón de prueba por tipo');
  assert.match(html, /data-gr-kind="checkout" >/, 'tipo apagado sin checked');
  assert.match(html, /data-gr-op="va"><label class="gr-check"><input type="checkbox" data-gr-op-on >/, 'Virginia sin grupo configurado aún');
  assert.ok(html.includes('is-test'));
});

test('modo prueba apagado y aviso cuando falta n8n', () => {
  const G = screen();
  G.model.data.config.test_mode = false;
  G.model.data.n8n_ready = false;
  const html = G.view();
  assert.ok(html.includes('Apagado: los avisos salen a los destinatarios reales.') && html.includes('is-live'));
  assert.ok(html.includes('Falta conectar el envío'));
});

test('historial: fecha, tipo, destino y estado; fallido con su error', () => {
  const G = screen({ items: [
    { id: 2, kind: 'checkin', kind_label: 'Corte de entrada', destination: 'Grupo Alabama → prueba', status: 'failed', error: 'n8n respondió 500', test: true, created_at: '2026-11-09T12:30:00Z' },
    { id: 1, kind: 'received', kind_label: 'Timesheet recibido', destination: 'Drive Alabama (WhatsApp 1703…)', status: 'received', error: null, test: false, created_at: '2026-11-09T23:45:00Z' },
  ] });
  const html = G.view();
  for (const s of ['Corte de entrada', 'Grupo Alabama → prueba', 'Fallido', 'n8n respondió 500', 'prueba', 'Timesheet recibido', 'Recibido']) assert.ok(html.includes(s), s);
  assert.ok(html.includes('class="is-failed"'));
});

test('se escapa todo lo que viene del servidor', () => {
  const G = screen();
  G.model.data.config.owners = [{ name: '<img src=x onerror=alert(1)>', phone: '', email: '' }];
  assert.ok(!G.view().includes('<img src=x'));
});

test('sin permiso: solo el mensaje del servidor', () => {
  const G = screen({ data: null, denied: true, error: 'Solo el dueño o el administrador de la empresa ve y cambia los avisos por WhatsApp.' });
  const html = G.view();
  assert.ok(html.includes('Solo el dueño') && !html.includes('Guardar configuración'));
});

test('CSS sin desbordes en móvil', () => {
  assert.match(CSS, /minmax\(min\(100%, 220px\), 1fr\)/);
  assert.match(CSS, /@media \(max-width: 640px\)/);
});

test('Board de gerencia: botón "Avisos WhatsApp" solo con group_reports del servidor', () => {
  const w = load(BOARD);
  const B = w.CxReportsBoard;
  B._ctx({ companyId: 'c1', apiBase: '/api/v1', token: () => 't', host: () => null, back() {} });
  Object.assign(B.model, { data: JSON.parse(JSON.stringify(FIX)), preset: 'week', anchor: '2026-11-05', query: '', op: 'all', status: '', sort: 'az', open: '', loading: false, error: '', denied: false, notesShown: {}, alertsAll: {} });
  assert.ok(!B.view().includes('data-rb-avisos'), 'sin el interruptor no aparece');
  B.model.data.group_reports = true;
  assert.ok(B.view().includes('data-rb-avisos') && B.view().includes('Avisos WhatsApp'));
  assert.ok(BOARD.includes('/client-static/group_reports.js?v=072A'), 'el archivo se carga solo al tocar el botón');
});
