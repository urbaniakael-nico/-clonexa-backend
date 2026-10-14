// Consola v2+ · Facturación: Redactar contrato (empresa, formulario precargado,
// vista previa con líneas para llenar), Datos del proveedor, interruptor del
// recordatorio, historial de versiones y pagos reportados por el cliente.
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { readFileSync } = require('node:fs');

const SRC = readFileSync('app/web/admin_v2plus_billing.js', 'utf8');

function load() {
  const window = { location: { href: '', origin: 'https://clonexa.test' }, CxConsolePlus: { initials: (n) => String(n).slice(0, 2).toUpperCase() } };
  const ctx = vm.createContext({ window, document: {}, fetch: async () => ({ ok: true, status: 200, json: async () => ({}) }), navigator: {}, JSON, Object, Array, String, Number, Math, Date, Promise, Error, encodeURIComponent, FormData: class {} });
  vm.runInContext(SRC, ctx);
  return window.CxConsoleBilling;
}

test('el tablero tiene "Redactar contrato" y "Datos del proveedor"', () => {
  const B = load();
  B.model.data = { kpis: {}, cards: [], charts: { by_month: [], by_company: [], by_type: [] } };
  const html = B.boardView();
  assert.match(html, /data-vpb-draft>Redactar contrato/);
  assert.match(html, /data-vpb-provider>Datos del proveedor/);
});

test('paso 1 lista solo lo que manda el servidor (registradas sin contrato)', () => {
  const B = load();
  B.model.draft = { step: 'pick', companies: [{ id: 'n1', name: 'Bar Nuevo' }], error: '' };
  const html = B.draftView();
  assert.match(html, /Bar Nuevo/);
  assert.match(html, /data-vpb-draft-pick="n1"/);
  B.model.draft.companies = [];
  assert.match(B.draftView(), /ya tienen contrato/);
});

test('paso 2: módulos activos precargados, datos del cliente opcionales, USD disponible', () => {
  const B = load();
  B.model.draft = { step: 'form', error: '', types: [{ code: 'minimo', label: 'Mínimo de meses' }],
    prefill: { company: { name: 'Bar Nuevo' }, modules: [{ code: 'hospitality', name: 'Hospitality', line: 'Mesas.' }, { code: 'inventory', name: 'Inventario', line: 'Stock.' }] },
    form: { contract_type: 'minimo', start_date: '2026-11-01', trial_days: 15, min_months: 6, currency: 'COP', pay_day_from: 15, pay_day_to: 20,
      tiers: [{ month_from: 1, month_to: 2, amount: 180000 }, { month_from: 3, month_to: null, amount: 220000 }], surcharge: { amount: '', from_month: '' },
      client: {}, modules: [{ code: 'hospitality', name: 'Hospitality', line: 'Mesas.' }] } };
  const html = B.draftView();
  assert.match(html, /name="mod_on_0" checked/);
  assert.doesNotMatch(html, /name="mod_on_1" checked/, 'solo los elegidos');
  assert.match(html, /<option >USD<\/option>|<option>USD<\/option>|<option >USD/);
  for (const f of ['client_legal_name', 'client_doc_id', 'client_representative', 'client_address', 'client_email', 'client_phone']) assert.match(html, new RegExp(`name="${f}"`));
  assert.match(html, /línea para llenar a mano, resaltada en amarillo suave/);
  assert.match(html, /name="trial_days"/);
  assert.match(html, /name="surcharge_amount"/);
  assert.doesNotMatch(html, /style="/, 'sin estilos en línea (CSP de v2+)');
});

test('paso 3: vista previa con número, versión, verificación y líneas resaltadas', () => {
  const B = load();
  B.model.draft = { step: 'preview', error: '', provider: { has_qr: false }, prefill: {}, preview: {
    number: 'CX-2026-003', version: 1, verification: 'ABCDE-12345', title: 'CONTRATO', subtitle: [['t', 'para Bar']], currency: 'COP',
    company_name: 'Bar Nuevo', provider: { name: 'Prov', trade_name: 'CLONEXA' }, client: { legal_name: '' }, vigencia: { min_months: 6, end: '30 de abril de 2027' },
    pago: { window: 'Del 15 al 20' }, tiers: [{ label: 'Meses 1 a 2', amount_text: '$180.000 COP' }], commitment_text: '$1.240.000 COP', commitment_words: 'un millón',
    modules: [{ name: 'Hospitality', line: 'Mesas.' }], schedule: [{ seq: 1, period: 'Noviembre 2026', window: '15–20 nov. 2026', amount_text: '$180.000 COP', note: 'x' }],
    access: [['Usuario entregado', null]],
    sections: [{ title: 'PARTES', blocks: [{ type: 'p', segments: [['t', 'identificado con '], ['b', '']] }] }, { title: 'QUINTA. PRECIO', blocks: [{ type: 'block', name: 'CUOTAS' }] }] } };
  const html = B.draftView();
  for (const s of ['CX-2026-003', 'Versión 1', 'ABCDE-12345', '\\$1\\.240\\.000 COP', 'Noviembre 2026', 'clonexa-logo-horizontal\\.svg']) assert.match(html, new RegExp(s));
  assert.match(html, /<mark class="vp-bill-blank">/);
  assert.match(html, /data-vpb-draft-generate *>Generar y guardar/);
  assert.doesNotMatch(html, /style="/);
});

test('detalle: interruptor del recordatorio, historial de versiones y pago reportado por el cliente', () => {
  const B = load();
  const d = { company: { id: 'c1', name: 'Bar' }, contract: { reminder_enabled: true, contract_type: 'minimo', tiers: [] },
    files: [{ id: 'f2' }, { id: 'f1' }], documents: [{ id: 'd2', number: 'CX-2026-001', version: 2, verification: 'AAAAA-BBBBB', is_current: true, file_id: 'f2' },
      { id: 'd1', number: 'CX-2026-001', version: 1, verification: 'CCCCC-DDDDD', is_current: false, file_id: 'f1' }] };
  let html = B.documentsPanel(d);
  assert.match(html, /Recordatorio en el panel: encendido/);
  assert.match(html, /data-vpb-reminder="off"/);
  assert.match(html, /versión 2 · vigente/);
  assert.match(html, /versión 1/);
  assert.match(html, /genera la versión 3/);
  html = B.documentsPanel({ ...d, contract: { ...d.contract, reminder_enabled: false } });
  assert.match(html, /apagado/);
  B.model.companyId = 'c1';
  B.model.detail = { ...d, summary: {}, installments: [], methods: {}, types: [],
    payments: [{ id: 'p1', status: 'por_validar', amount: 150000, paid_on: '2026-11-16', method: 'transferencia', period: '2026-11-01', source: 'cliente', has_proof: true }] };
  html = B.detailView();
  assert.match(html, /Reportado por el cliente/);
  assert.match(html, /payments\/p1\/proof/);
  assert.match(html, /data-vpb-void="p1"/, 'un pago por validar también se puede anular');
});

test('datos del proveedor: formulario y QR', () => {
  const B = load();
  B.model.provider = { data: { name: 'Prov', trade_name: 'CLONEXA', doc_id: '1', email: 'a@b.co', phones: '+57', city: '', has_qr: true }, error: '', stamp: 1 };
  const html = B.providerView();
  assert.match(html, /name="name"/);
  assert.match(html, /provider\/qr\?t=1/);
  assert.match(html, /no en la base de datos/);
});
