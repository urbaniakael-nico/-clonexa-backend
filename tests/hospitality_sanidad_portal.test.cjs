// Módulo SANIDAD en el portal (048K): planilla, historial, ítems y aviso del
// Dashboard. Ejecuta las funciones reales de client.js.
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

function portal({ role = 'company_admin', dashboard = {} } = {}) {
  const ctx = vm.createContext({
    h: (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
    currentClientRole: () => role,
    state: { company: { timezone: 'America/Bogota' }, dashboardMetrics: dashboard },
    Intl, Date, Math, Number, String, Array, Set, Object, JSON,
  });
  vm.runInContext(`var cxSan048K = { tab: "sheet", date: "", sheet: null, staff: [], today: "2026-09-24", items: [], history: [], message: "", error: "", busy: false };\n`
    + ['cxSanDashboardBanner048K', 'cxSanIsAdmin048K', 'cxSanDateLabel048K', 'cxSanTime048K', 'cxSanCompliance048K',
      'cxSanGroups048K', 'cxSanSheetHtml048K', 'cxSanHistoryHtml048K', 'cxSanItemsHtml048K'].map(fn).join('\n'), ctx);
  return ctx;
}

const ENTRIES = [
  { item_id: 'i1', section: 'Cocina', label: 'Mesones limpios', checked: true, observation: '', requires_value: false, value: null },
  { item_id: 'i2', section: 'Neveras y temperaturas', label: 'Temperatura de la nevera', checked: false, observation: 'revisar', requires_value: true, value_label: '°C', value: 3.5 },
];

test('el módulo tiene nombre en el menú y su propia ruta', () => {
  assert.match(source, /sanidad: \["Sanidad", "planilla diaria de limpieza", "SAN"\],/);
  assert.match(source, /if \(code === "sanidad"\) \{\s*await renderSanitationModule048K\(\);/);
  assert.match(source, /if \(!isClientModuleActive\("sanidad"\)\) \{\s*render\(\);\s*return;/, 'sin el módulo no se ve nada');
});

test('aviso en el Dashboard solo cuando falta la planilla', () => {
  const alert = portal({ dashboard: { sanitation048K: { alert: true, message: 'Falta diligenciar la planilla de Sanidad del 23/09.' } } });
  assert.match(alert.cxSanDashboardBanner048K(), /data-client-module="sanidad"[\s\S]*Planilla de Sanidad pendiente[\s\S]*Falta diligenciar la planilla de Sanidad del 23\/09\./);
  assert.equal(portal({ dashboard: { sanitation048K: { alert: false } } }).cxSanDashboardBanner048K(), '');
  assert.equal(portal({ dashboard: {} }).cxSanDashboardBanner048K(), '', 'empresa sin el módulo: nada');
  assert.match(source, /if \(codes\.has\("sanidad"\)\) \{\s*metrics\.sanitation048K = await api/);
});

test('planilla abierta: fecha, responsable, secciones, check, valor numérico y observación', () => {
  const ctx = portal();
  ctx.cxSan048K.staff = [{ id: 'e1', name: 'Ana Cocina', role: 'cocina' }];
  ctx.cxSan048K.sheet = { date: '2026-09-24', status: 'open', responsible_employee_id: 'e1', entries: ENTRIES, notes: [] };
  const html = ctx.cxSanSheetHtml048K();
  assert.match(html, /type="date" value="2026-09-24" max="2026-09-24"/);
  assert.match(html, /<option value="e1" selected>Ana Cocina · cocina<\/option>/);
  assert.match(html, /<h3>Cocina<\/h3>[\s\S]*Mesones limpios[\s\S]*<h3>Neveras y temperaturas<\/h3>/);
  assert.match(html, /type="number"[^>]*data-san-value-048k value="3.5"[\s\S]*<small>°C<\/small>/);
  assert.match(html, /data-san-obs-048k value="revisar"/);
  assert.match(html, /<b data-san-pct-048k>50%<\/b>/);
  assert.match(html, /Cerrar y firmar planilla/);
  assert.doesNotMatch(html, / disabled/);
});

test('planilla cerrada: solo lectura, firmada, y con notas posteriores', () => {
  const ctx = portal();
  ctx.cxSan048K.sheet = {
    date: '2026-09-23', status: 'closed', responsible_employee_id: 'e1', responsible_name: 'Ana Cocina', compliance: 50,
    closed_at: '2026-09-24T03:10:00Z', closed_by: 'Pedro', entries: ENTRIES,
    notes: [{ note: 'Se revisó de nuevo.', author: 'Dueño', created_at: '2026-09-24T12:00:00Z' }],
  };
  const html = ctx.cxSanSheetHtml048K();
  assert.match(html, /🔒 Planilla cerrada el [\s\S]* por Pedro · responsable Ana Cocina\. Ya no se puede editar\./);
  assert.equal((html.match(/data-san-check-048k[^>]*disabled/g) || []).length, 2);
  assert.doesNotMatch(html, /Guardar borrador|Cerrar y firmar planilla/);
  assert.match(html, /Notas posteriores al cierre[\s\S]*Dueño[\s\S]*Se revisó de nuevo\.[\s\S]*data-san-add-note-048k/);
});

test('historial: fecha, responsable, cumplimiento y Ver / Descargar / Imprimir', () => {
  const ctx = portal();
  ctx.cxSan048K.history = [{ date: '2026-09-23', responsible_name: 'Ana Cocina', compliance: 95, closed_at: '2026-09-24T03:10:00Z', closed_by: 'Pedro' }];
  const html = ctx.cxSanHistoryHtml048K();
  assert.match(html, /<b>23\/09\/2026<\/b>[\s\S]*Ana Cocina[\s\S]*cx-san-pct-tag-048k ok">95%/);
  assert.match(html, /data-san-view-048k="2026-09-23">Ver<[\s\S]*data-san-download-048k="2026-09-23">Descargar<[\s\S]*data-san-print-048k="2026-09-23">Imprimir</);
  assert.match(source, /\/sanitation\/companies\/\$\{encodeURIComponent\(state\.companyId\)\}\/sheets\/\$\{encodeURIComponent\(day\)\}\/pdf`, \{\s*headers: authHeaders\(\{\}\),/, 'el PDF se pide con la sesión');
});

test('configurar ítems: agregar, editar, reordenar y desactivar; solo administradores', () => {
  const ctx = portal();
  ctx.cxSan048K.items = [
    { id: 'i1', section: 'Cocina', label: 'Mesones limpios', requires_value: false, value_label: '', active: true },
    { id: 'i2', section: 'Neveras', label: 'Temperatura', requires_value: true, value_label: '°C', active: false },
  ];
  const html = ctx.cxSanItemsHtml048K();
  assert.match(html, /data-san-add-form-048k/);
  assert.match(html, /data-san-item-048k="i2"[\s\S]*data-san-item-value-048k checked[\s\S]*value="°C"/);
  assert.match(html, /cx-san-item-048k is-off" data-san-item-048k="i2"/);
  assert.match(html, /data-san-item-up-048k[\s\S]*data-san-item-down-048k[\s\S]*data-san-item-save-048k/);
  assert.match(portal({ role: 'operador' }).cxSanItemsHtml048K(), /Solo un administrador de la empresa puede configurar los ítems\./);
});
