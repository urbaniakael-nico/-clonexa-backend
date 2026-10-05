// Consola v2+ · Interruptores: registro, matriz, confirmación, guardado con
// SOLO la clave cambiada, bloqueos, delicados, dependencias, aviso de Admin V2,
// y la configuración QR (M05) y el corte diario (S01, S02) con los cuerpos de v2.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const v2 = readFileSync('app/web/admin_v2.js', 'utf8').replace(/\r\n/g, '\n');
const source = readFileSync('app/web/admin_v2plus_switches.js', 'utf8');
const REGISTRY = JSON.parse(readFileSync('app/services/switch_registry.json', 'utf8'));
const plain = (v) => JSON.parse(JSON.stringify(v));

function load(responder = () => ({ status: 200, body: {} })) {
  const calls = [];
  const fetch = async (url, options = {}) => {
    const call = { url, method: options.method || 'GET', headers: options.headers || {}, body: options.body ? JSON.parse(options.body) : undefined };
    calls.push(call);
    const { status, body } = responder(call);
    return { status, ok: status >= 200 && status < 300, json: async () => body };
  };
  const window = { location: { href: '', origin: 'https://clonexa.app' } };
  const ctx = vm.createContext({ window, document: {}, fetch, JSON, Object, Array, String, Number, Math, Promise, Error, Date, Map, Set, encodeURIComponent, decodeURIComponent, URLSearchParams });
  vm.runInContext(source, ctx);
  return { S: window.CxConsoleSwitches, R: window.CxSwitchRegistry, sections: window.CxConsoleSections, calls };
}

const st = (on, locked = false, missing = []) => ({ on, locked, missing_modules: missing });
function company(id, name, kind, overrides = {}) {
  const switches = Object.fromEntries(REGISTRY.switches.map((s) => [s.key, st(false)]));
  return { id, name, kind, switches: { ...switches, ...overrides } };
}
const ASADERO = company('a1', 'ASADERO EL SOCIO', 'registrada', { cash_count: st(true), cashier_redesign: st(true), sales_ledger: st(true) });
const DEMO = company('d1', 'Radio Despecho', 'demo', { delivery_print: st(false, true, ['domicilios_whatsapp']), qr_bar_menu: st(false, true, ['qr']) });
const DATA = { ok: true, registry: REGISTRY, companies: [ASADERO, DEMO] };

// ------------------------------------------------------------ registro
test('registro: los 15 interruptores del inventario, con grupos, delicados, dependencias y aviso de v2', () => {
  const keys = REGISTRY.switches.map((s) => s.key);
  assert.deepEqual(keys.slice().sort(), ['brand_everywhere', 'cash_count', 'cashier_direct_sale', 'cashier_redesign', 'checkout_v2', 'delivery_print', 'kitchen_board_columns',
    'kitchen_roster', 'menu_emojis', 'mini_panel_brand', 'qr_bar_menu', 'quantity_buttons_enabled', 'quantity_picker', 'sales_ledger', 'short_links']);
  const by = Object.fromEntries(REGISTRY.switches.map((s) => [s.key, s]));
  for (const k of ['sales_ledger', 'cashier_redesign', 'checkout_v2']) assert.equal(by[k].delicate, true, `${k} es delicado`);
  assert.deepEqual(REGISTRY.switches.filter((s) => s.v2_form).map((s) => s.key).sort(),
    ['cashier_direct_sale', 'kitchen_board_columns', 'kitchen_roster', 'menu_emojis', 'quantity_buttons_enabled']);
  assert.deepEqual(plain(by.cashier_redesign.depends_on.map((d) => d.key)), ['cash_count']);
  assert.deepEqual(by.delivery_print.requires_modules, ['domicilios_whatsapp']);
  assert.equal(by.checkout_v2.module, 'domicilios_whatsapp');
  assert.equal(by.qr_bar_menu.module, 'qr');
  for (const s of REGISTRY.switches) assert.ok(REGISTRY.groups.includes(s.group), s.key);
});

test('las 5 claves con aviso son exactamente las que guarda el formulario de Admin V2', () => {
  for (const key of ['kitchen_board_columns', 'kitchen_roster', 'cashier_direct_sale', 'menu_emojis', 'quantity_buttons_enabled']) {
    assert.match(v2, new RegExp(`\\b${key}\\b`), `${key} aparece en admin_v2.js`);
  }
  for (const key of ['cashier_redesign', 'sales_ledger', 'checkout_v2', 'cash_count', 'short_links', 'brand_everywhere']) {
    assert.doesNotMatch(v2, new RegExp(`\\b${key}\\b`), `${key} no lo guarda Admin V2`);
  }
});

// ------------------------------------------------------------ guardado
test('un cambio envía SOLO su clave, a esa empresa y ese módulo, con el mismo endpoint de v2 y el motivo para la auditoría', async () => {
  const { S, R, calls } = load();
  S._setCache(DATA);
  await S.saveSwitch(R.get('menu_emojis'), ASADERO, true, 'Lo pidió el dueño');
  assert.equal(calls.length, 1);
  const [c] = calls;
  assert.equal(`${c.method} ${c.url}`, 'POST /api/v1/companies/a1/modules/waiter_ordering/activate');
  assert.deepEqual(plain(c.body), { settings: { menu_emojis: true } }, 'ni otras claves ni otra empresa');
  assert.deepEqual(JSON.parse(decodeURIComponent(c.headers['X-Cx-Audit-Note'])), { interruptor: 'menu_emojis', valor: true, motivo: 'Lo pidió el dueño' });
  await S.saveSwitch(R.get('checkout_v2'), ASADERO, false, 'pausa');
  assert.equal(calls[1].url, '/api/v1/companies/a1/modules/domicilios_whatsapp/activate');
  assert.deepEqual(plain(calls[1].body), { settings: { checkout_v2: false } }, 'apagar manda false, no apaga el módulo');
  assert.match(v2, /\/modules\/\$\{encodeURIComponent\(moduleCode\)\}\/activate`, \{\s*method: "POST",\s*body: JSON\.stringify\(\{ settings: \{ qr_config: payload \} \}\),/, 'v2 usa el mismo endpoint con settings parciales');
});

test('un interruptor bloqueado no se puede encender y no llama al servidor', async () => {
  const { S, R, calls } = load();
  S._setCache(DATA);
  const p = S.plan(R.get('delivery_print'), DEMO, true);
  assert.match(p.blocked, /no tiene encendido domicilios_whatsapp/);
  await assert.rejects(S.saveSwitch(R.get('delivery_print'), DEMO, true, 'prueba'), /No se puede encender/);
  await assert.rejects(S.saveSwitch(R.get('menu_emojis'), DEMO, true, ''), /motivo/);
  assert.equal(calls.length, 0);
});

test('delicados en registradas exigen el nombre; en demos no. Dependencias y aviso de Admin V2', () => {
  const { S, R } = load();
  S._setCache(DATA);
  assert.equal(S.plan(R.get('sales_ledger'), ASADERO, false).needsName, true);
  assert.equal(S.plan(R.get('sales_ledger'), DEMO, true).needsName, false, 'demo: sin escribir el nombre');
  assert.equal(S.plan(R.get('menu_emojis'), ASADERO, true).needsName, false, 'no delicado');
  const off = S.plan(R.get('cash_count'), ASADERO, false);
  assert.equal(off.needsAck, true, 'apagar el arqueo con la caja rediseñada encendida pide confirmar');
  assert.match(off.warnings.map((w) => w.text).join(' '), /«Caja rediseñada» está encendido y depende de este/);
  const on = S.plan(R.get('cashier_redesign'), DEMO, true);
  assert.match(on.warnings.map((w) => w.text).join(' '), /Depende de «Arqueo de caja», que está apagado/);
  assert.equal(on.needsAck, false);
  const v2w = S.plan(R.get('kitchen_roster'), ASADERO, true).warnings.map((w) => w.text);
  assert.ok(v2w.includes('También se cambia desde Admin V2; cámbialo solo desde aquí'));
  assert.ok(!S.plan(R.get('short_links'), ASADERO, true).warnings.some((w) => w.kind === 'v2'));
});

// ------------------------------------------------------------ vista
test('matriz: agrupada, rojo encendido, gris apagado, candado con el motivo; filtro Registradas/Demos y buscador', () => {
  const { S } = load();
  S._setCache(DATA);
  S.model.kind = 'todas';
  let html = S.view();
  assert.match(html, /<th scope="rowgroup" colspan="3">Caja<\/th>/);
  assert.match(html, /class="vp-switch-btn is-on" type="button" role="switch" aria-checked="true"[\s\S]{0,80}aria-label="Arqueo de caja en ASADERO EL SOCIO: encendido" data-vpw-cell="cash_count\|a1"/);
  assert.match(html, /aria-label="Arqueo de caja en Radio Despecho: apagado" data-vpw-cell="cash_count\|d1"/);
  assert.match(html, /is-locked" role="img" title="Bloqueado: falta domicilios_whatsapp"/);
  assert.doesNotMatch(html, /data-vpw-cell="delivery_print\|d1"/, 'bloqueado no es botón');
  assert.match(html, /Delicado<\/span>/);
  assert.match(html, /También en Admin V2<\/span>/);
  assert.doesNotMatch(html, /\sstyle=/);
  S.model.kind = 'demo';
  html = S.view();
  assert.doesNotMatch(html, /ASADERO/);
  S.model.kind = 'todas';
  S.model.query = 'arqueo';
  html = S.view();
  assert.match(html, /Arqueo de caja/);
  assert.doesNotMatch(html, /Links cortos/);
  S.model.query = 'radio';
  html = S.view();
  assert.doesNotMatch(html, /<a href="#empresa\/a1">/, 'buscar una empresa deja solo su columna');
  S.model.query = '';
});

test('panel de confirmación: nombra función y empresa, pide motivo, avisa "solo esta empresa" y exige el nombre si es delicado', async () => {
  const { S, calls } = load();
  S._setCache(DATA);
  S.openSwitch('sales_ledger', 'a1');
  let html = S.view();
  assert.match(html, /Apagar <b>Ventas por día de cobro<\/b> en <b>ASADERO EL SOCIO<\/b>/);
  assert.match(html, /<b>Solo esta empresa\.<\/b>/);
  assert.match(html, /Motivo \(queda en la auditoría\)/);
  assert.match(html, /Escribe el nombre de la empresa para confirmar/);
  S.model.modal.reason = 'cierre de mes';
  S.model.modal.name = 'asadero';
  await S.confirm();
  assert.match(S.model.modal.error, /no coincide/);
  assert.equal(calls.length, 0);
  S.model.modal.name = 'Asadero el socio';
  await S.confirm();
  assert.equal(calls[0].url, '/api/v1/companies/a1/modules/waiter_ordering/activate');
  assert.deepEqual(plain(calls[0].body), { settings: { sales_ledger: false } });
});

// --------------------------------------------- M05 y S01/S02 (cuerpos de v2)
test('configuración QR: mismo cuerpo que cxSaveCompanyQrConfig025N', async () => {
  const { S, calls } = load();
  const payload = S.qrPayload({ mode: 'hospitality', max_capacity: '20', table_count: '50', include_bar: 'on', orders_board: 'mesas', base_url: 'https://x.co/ordenar/' });
  assert.deepEqual({ ...plain(payload), updated_at: 'x' }, { mode: 'hospitality', max_capacity: 20, table_count: 20, include_bar: true, orders_board: 'mesas', base_url: 'https://x.co', updated_at: 'x' });
  await S.config.saveQr('t1', 'qr', payload, 'más mesas');
  assert.equal(`${calls[0].method} ${calls[0].url}`, 'POST /api/v1/companies/t1/modules/qr/activate');
  assert.deepEqual(Object.keys(calls[0].body.settings), ['qr_config']);
  assert.match(v2, /const ordersBoard = raw\.orders_board === "mesas" \? "mesas" : "kanban";/);
  assert.match(v2, /const tableCount = Math\.min\(maxCapacity, cxClampQrOption025N\(raw\.table_count, maxCapacity\)\);/);
  assert.match(v2, /return Math\.min\(500, Math\.max\(1, number\)\);/);
  assert.equal(S.qrNormalize({ settings: { qr_config: { orders_board: 'mesas', table_count: 7, max_capacity: 10 } } }).orders_board, 'mesas');
});

test('corte diario: GET y PUT de la política con el cuerpo de cxSessPolicyPanel048Q', async () => {
  const { S, calls } = load();
  await S.config.policy('a1');
  await S.config.savePolicy('a1', S.config.policyBody({ cutoff_time: '03:00', alert_after_hours: '12.5' }), 'cierra tarde');
  assert.deepEqual(calls.map((c) => `${c.method} ${c.url}`), ['GET /api/v1/workforce-sessions/companies/a1/policy', 'PUT /api/v1/workforce-sessions/companies/a1/policy']);
  assert.deepEqual(plain(calls[1].body), { cutoff_time: '03:00', alert_after_hours: 12.5 });
  assert.match(v2, /body: JSON\.stringify\(\{ cutoff_time: data\.cutoff_time, alert_after_hours: Number\(data\.alert_after_hours\) \}\),/);
});

// ------------------------------------------------------------ Ficha
test('la Ficha muestra los interruptores encendidos de la empresa con enlace a Interruptores', () => {
  const { S, R } = load();
  S._setCache(DATA);
  const on = R.onFor([{ module: { code: 'waiter_ordering' }, enabled: true, settings: { cash_count: true, menu_emojis: false, otra: true } },
    { module: { code: 'qr' }, enabled: false, settings: { qr_bar_menu: true } }]);
  assert.deepEqual(plain(on.map((s) => s.key)), ['cash_count'], 'módulo apagado: su interruptor no cuenta');
  const ficha = readFileSync('app/web/admin_v2plus_ficha.js', 'utf8');
  assert.match(ficha, /card\("Interruptores encendidos"/);
  assert.match(ficha, /data-vpf-switches>Ver en Interruptores/);
  const company = readFileSync('app/web/admin_v2plus_company.js', 'utf8');
  assert.match(company, /setView\("switches", \{ companyId: model\.id \}\)/);
});
