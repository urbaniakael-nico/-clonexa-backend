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

// ---- contrato bilingüe (español | inglés), Zelle y "Redactar desde este contrato"
function loadWithForm() {
  const window = { location: { href: '', origin: 'https://clonexa.test' }, CxConsolePlus: { initials: (n) => String(n).slice(0, 2).toUpperCase() } };
  class FormData { constructor(f) { this.f = f; } entries() { return Object.entries(this.f.__values || {}); } }
  const ctx = vm.createContext({ window, document: {}, fetch: async () => ({ ok: true, status: 200, json: async () => ({}) }), navigator: {}, JSON, Object, Array, String, Number, Math, Date, Promise, Error, encodeURIComponent, FormData });
  vm.runInContext(SRC, ctx);
  return window.CxConsoleBilling;
}

function draftModel(form) {
  return { step: 'form', error: '', types: [{ code: 'mensual', label: 'Mensual' }], provider: { has_qr: true, zelle_name: '', zelle_contact: '' },
    prefill: { company: { name: 'Empresa USD' }, modules: [{ code: 'payroll', name: 'Nómina', line: 'Horas.', name_en: 'Payroll', line_en: 'Hours.' }] },
    form: { contract_type: 'mensual', start_date: '2026-11-01', trial_days: 0, min_months: 3, currency: 'USD', pay_day_from: 1, pay_day_to: 5,
      tiers: [{ month_from: 1, month_to: null, amount: 1500 }], surcharge: { amount: '', from_month: '' }, client: {},
      modules: [{ code: 'payroll', name: 'Nómina', line: 'Horas.', name_en: 'Payroll', line_en: 'Hours.' }], ...form } };
}

test('formulario: "Idioma del contrato" (Español por defecto | Bilingüe ES-EN) y "Medio de pago" (QR por defecto | Zelle)', () => {
  const B = load();
  B.model.draft = draftModel({});
  let html = B.draftView();
  assert.match(html, /Idioma del contrato<select name="language" data-vpb-draft-redraw><option value="es" selected>Español<\/option><option value="es_en" >Bilingüe ES-EN<\/option>/);
  assert.match(html, /Medio de pago<select name="payment_method" data-vpb-draft-redraw><option value="qr" selected>QR<\/option><option value="zelle" >Zelle<\/option>/);
  assert.doesNotMatch(html, /name="mod_name_en_0"/, 'en español no hay campos en inglés');
  assert.match(html, /name="jurisdiction_city" maxlength/, 'en español la ciudad de jurisdicción sigue igual');
  B.model.draft = draftModel({ language: 'es_en', payment_method: 'zelle' });
  html = B.draftView();
  assert.match(html, /<option value="es_en" selected>Bilingüe ES-EN/);
  assert.match(html, /name="mod_name_en_0" maxlength="80" value="Payroll"/);
  assert.match(html, /name="mod_line_en_0" maxlength="200" value="Hours\."/);
  assert.match(html, /prevalece el español\. Ley de Colombia y jueces de Bogotá/);
  assert.match(html, /No lleva QR ni números de cuenta\. Falta en «Datos del proveedor»: nombre del titular y correo o teléfono/);
  assert.doesNotMatch(html, /style="/, 'sin estilos en línea (CSP de v2+)');
});

test('leer el formulario: idioma, medio de pago, módulos en inglés y "desde el contrato manual"', () => {
  const B = loadWithForm();
  B.model.draft = draftModel({ language: 'es_en', from_manual: true });
  const form = { __values: { contract_type: 'mensual', start_date: '2026-11-01', trial_days: '0', min_months: '3', currency: 'USD', pay_day_from: '1', pay_day_to: '5',
    tier_from_0: '1', tier_to_0: '', tier_amount_0: '1500', language: 'es_en', payment_method: 'zelle', mod_on_0: 'on', mod_code_0: 'payroll',
    mod_name_0: 'Nómina', mod_line_0: 'Horas.', mod_name_en_0: 'Payroll', mod_line_en_0: 'Hours and pay.' } };
  const f = B.readDraftForm(form);
  assert.equal(f.language, 'es_en');
  assert.equal(f.payment_method, 'zelle');
  assert.equal(f.from_manual, true);
  assert.deepEqual(JSON.parse(JSON.stringify(f.modules)), [{ code: 'payroll', name: 'Nómina', line: 'Horas.', name_en: 'Payroll', line_en: 'Hours and pay.' }]);
  B.model.draft = draftModel({});
  const es = B.readDraftForm({ __values: { ...form.__values, language: 'es', payment_method: 'qr' } });
  assert.equal(es.language, 'es');
  assert.equal(es.from_manual, undefined, 'sin "desde el contrato manual" no se manda');
});

test('vista previa bilingüe: cada sección en dos columnas (español | inglés)', () => {
  const B = load();
  B.model.draft = { step: 'preview', error: '', provider: {}, prefill: {}, preview: {
    bilingual: true, number: 'CX-2026-004', version: 1, verification: 'AAAAA-BBBBB', title: 'CONTRATO', title_en: 'AGREEMENT', subtitle: [['t', 'para X']],
    subtitle_en: [['t', 'for X']], currency: 'USD', company_name: 'Empresa USD', provider: {}, client: {}, vigencia: { min_months: 3 }, pago: {}, tiers: [],
    modules: [{ name: 'Nómina', line: 'Horas.', name_en: 'Payroll', line_en: 'Hours.' }], schedule: [], access: [],
    sections: [{ title: 'VIGÉSIMA. IDIOMA', title_en: 'TWENTIETH. LANGUAGE', blocks: [{ type: 'p', segments: [['t', 'Prevalece el español.']], segments_en: [['t', 'The Spanish version shall prevail.']] }] },
      { title: 'SEGUNDA', title_en: 'SECOND', blocks: [{ type: 'block', name: 'MODULOS' }] }] } };
  const html = B.draftView();
  assert.match(html, /<div class="vp-bill-doc-bi"><h4>VIGÉSIMA\. IDIOMA<\/h4><h4 class="is-en">TWENTIETH\. LANGUAGE<\/h4><\/div>/);
  assert.match(html, /<div class="vp-bill-doc-bi"><p>Prevalece el español\.<\/p><p class="is-en">The Spanish version shall prevail\.<\/p><\/div>/);
  assert.match(html, /<b>Nómina<\/b>: Horas\.[\s\S]*<b>Payroll<\/b>: Hours\./);
  assert.match(html, /AGREEMENT<br>for X/);
  assert.doesNotMatch(html, /style="/);
});

test('ficha: "Redactar desde este contrato" solo si el contrato manual NO tiene pagos; el manual queda en el historial', () => {
  const B = load();
  const d = { company: { id: 'v1', name: 'Empresa USD' }, contract: { reminder_enabled: false }, files: [], documents: [], manual_redraft: true, history: [] };
  let html = B.documentsPanel(d);
  assert.match(html, /data-vpb-draft-manual="v1">Redactar desde este contrato/);
  assert.match(html, /el contrato a mano queda en el historial y el redactado pasa a ser el vigente \(versión 1\)/);
  html = B.documentsPanel({ ...d, manual_redraft: false });
  assert.doesNotMatch(html, /data-vpb-draft-manual/, 'con pagos: el bloqueo de siempre');
  assert.match(html, /Tiene pagos registrados: no se reemplaza desde Redactar contrato\./);
  html = B.documentsPanel({ ...d, manual_redraft: false, documents: [{ id: 'd1', number: 'CX-2026-004', version: 1, verification: 'X', is_current: true }],
    history: [{ id: 'h1', source: 'manual', snapshot: { currency: 'USD', start_date: '2026-11-01' }, created_at: '2026-10-27T15:00:00Z' }] });
  assert.match(html, /CX-2026-004 · versión 1 · vigente/);
  assert.match(html, /Historial[\s\S]*Contrato registrado a mano · USD · inicio/);
});

test('ficha con contrato redactado: botones claros "Ver PDF" y "Descargar PDF"', () => {
  const B = load();
  const d = { company: { id: 'c1', name: 'Bar' }, contract: { reminder_enabled: true }, files: [{ id: 'f2' }, { id: 'f1' }],
    documents: [{ id: 'd2', number: 'CX-2026-001', version: 2, verification: 'A', is_current: true, file_id: 'f2' },
      { id: 'd1', number: 'CX-2026-001', version: 1, verification: 'B', is_current: false, file_id: 'f1' }] };
  const html = B.documentsPanel(d);
  assert.match(html, /<div class="vp-actions vp-bill-pdf-main"><b>Contrato vigente: CX-2026-001 · versión 2<\/b>[\s\S]*?class="vp-btn vp-btn-sm vp-btn-primary" href="[^"]*contract-file\/f2" target="_blank" rel="noopener">Ver PDF<\/a>[\s\S]*?href="[^"]*contract-file\/f2\?descargar=1" download="CX-2026-001-v2\.pdf">Descargar PDF<\/a>/);
  assert.match(html, /contract-file\/f1\?descargar=1" download="CX-2026-001-v1\.pdf">Descargar PDF/, 'cada versión del historial también');
  assert.equal((html.match(/>Ver PDF</g) || []).length, 3, 'vigente arriba + una por versión');
  assert.doesNotMatch(html, /style="/);
  assert.doesNotMatch(B.documentsPanel({ ...d, documents: [] }), /Ver PDF|Descargar PDF/, 'sin contrato redactado no salen');
});

test('datos del proveedor: "Nombre del titular en Zelle" y "Zelle (correo o teléfono)"', () => {
  const B = load();
  B.model.provider = { data: { name: 'Prov', zelle_name: 'Titular', zelle_contact: 'z@demo.test', has_qr: false }, error: '', stamp: 1 };
  const html = B.providerView();
  assert.match(html, /Nombre del titular en Zelle<input name="zelle_name" maxlength="300" value="Titular"/);
  assert.match(html, /Zelle \(correo o teléfono\)<input name="zelle_contact" maxlength="300" value="z@demo\.test"/);
});
