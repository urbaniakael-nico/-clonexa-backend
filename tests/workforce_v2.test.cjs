// Personal v2 (interruptor workforce_v2): ninguna función de Personal se
// pierde, con el interruptor apagado se sirve la pantalla de siempre, colores
// solo del tema y pares AA calculados desde el tema.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const SRC = readFileSync('app/web/workforce_v2.js', 'utf8');
const CSS = readFileSync('app/web/workforce_v2.css', 'utf8');
const CLIENT = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');

function load() {
  const window = {};
  const listeners = {};
  const document = { addEventListener: (t, f) => { listeners[t] = f; }, activeElement: null, createElement: () => ({ style: {}, remove() {} }) };
  vm.runInNewContext(SRC, { window, document, Blob: function Blob() {}, URL: {}, getComputedStyle: undefined, console });
  return { W: window.CxWorkforceV2, listeners, document };
}

// Monta la pantalla con un "host" sin DOM real y los datos de ejemplo.
async function mounted(W) {
  const host = { innerHTML: '', querySelector: () => null, contains: () => true };
  await W.mount({ companyId: 'c1', host: () => host, roles: () => URBANIA, configured: () => true, personalApi: async () => EMPLOYEES });
  return W.model;
}

const URBANIA = [['gerencia', 'Director'], ['supervisor', 'Supervisor'], ['inventario', 'Logística'], ['operario', 'Operario'], ['otro', 'Otro']];
const EMPLOYEES = [
  { id: 'e1', full_name: 'Nicolás Gómez', role: 'supervisor', status: 'active', phone: '300', email: 'n@u.co', telegram_user_id: '5', hire_date: '2026-01-15',
    hourly_rate_regular: 18, hourly_rate_extra: 24, deduction_1: 10, deduction_2: 0 },
  { id: 'e2', full_name: 'Ana', role: 'gerencia', status: 'inactive' },
  { id: 'e3', full_name: 'Zoe', role: 'tecnico', status: 'archived' },
  { id: 'e4', full_name: 'Beto', role: 'otro', status: 'activo' },
];

test('reglas: cifras, filtros (activos, inactivos, archivados), búsqueda por nombre, rol visible, teléfono, correo y Telegram', () => {
  const { W } = load();
  assert.deepEqual(JSON.parse(JSON.stringify(W.stats(EMPLOYEES))), { total: 4, active: 2, inactive: 1, archived: 1 });
  const names = (f, q = '') => W.visible(EMPLOYEES, f, q, URBANIA).map((e) => e.full_name);
  assert.deepEqual(names('all'), ['Ana', 'Beto', 'Nicolás Gómez', 'Zoe'], 'orden por nombre');
  assert.deepEqual(names('active'), ['Beto', 'Nicolás Gómez']);
  assert.deepEqual(names('inactive'), ['Ana']);
  assert.deepEqual(names('archived'), ['Zoe']);
  assert.deepEqual(names('all', 'director'), ['Ana'], 'busca por el nombre visible del rol');
  assert.deepEqual(names('all', 'nicolas'), ['Nicolás Gómez'], 'sin tildes');
  for (const q of ['300', 'n@u.co', '5']) assert.deepEqual(names('all', q), ['Nicolás Gómez'], q);
});

test('CSV: las mismas columnas de la pantalla de siempre (con Documento), con el nombre visible del rol y el estado', () => {
  const { W } = load();
  const csv = W.csvText([{ ...EMPLOYEES[0], document_id: '1020304050' }], URBANIA).split('\n');
  assert.equal(csv[0], '"Nombre","Documento","Rol","Telefono","Correo","Telegram ID","Fecha ingreso","Hora ordinaria","Hora extra","Descuento 1","Descuento 2","Estado"');
  assert.equal(csv[1], '"Nicolás Gómez","1020304050","Supervisor","300","n@u.co","5","2026-01-15","18","24","10","0","Activo"');
});

test('guardar: mismo cuerpo que la pantalla de siempre, con todos los campos', () => {
  const { W } = load();
  assert.deepEqual([...W.FIELDS], ['full_name', 'document_id', 'role', 'phone', 'email', 'telegram_user_id', 'hire_date', 'hourly_rate_regular', 'hourly_rate_extra', 'deduction_1', 'deduction_2', 'status']);
  const body = W.payloadOf('c1', { full_name: 'Ana', document_id: '', role: 'otro', phone: '', email: 'a@b.co', telegram_user_id: '9', hire_date: '2026-02-01',
    hourly_rate_regular: '20', hourly_rate_extra: '', deduction_1: '1.5', deduction_2: '0', status: 'active' });
  assert.deepEqual(JSON.parse(JSON.stringify(body)), { company_id: 'c1', full_name: 'Ana', document_id: null, role: 'otro', phone: null, email: 'a@b.co', telegram_user_id: '9',
    hire_date: '2026-02-01', hourly_rate_regular: 20, hourly_rate_extra: 0, deduction_1: 1.5, deduction_2: 0, status: 'active', employee_type: 'otro' });
});

test('pantalla: cabecera con agregar, historial, asistencia y volver; cifras; búsqueda, filtros y CSV en una línea; tabla agrupada; menú por fila', async () => {
  const { W } = load();
  const m = await mounted(W);
  assert.equal(m.employees.length, 4);
  m.menu = 'e2';
  const html = W.view();
  for (const attr of ['data-wf2-add', 'data-personal-history', 'data-personal-asistencia', 'data-client-back-dashboard', 'data-wf2-search', 'data-wf2-csv']) assert.ok(html.includes(attr), attr);
  for (const [k, l] of [['all', 'Todos'], ['active', 'Activos'], ['inactive', 'Inactivos'], ['archived', 'Archivados']]) {
    assert.match(html, new RegExp(`data-wf2-filter="${k}">${l}</button>`), `el filtro ${l} tiene nombre`);
  }
  assert.match(html, /<div class="wf-tools">[\s\S]*data-wf2-search[\s\S]*wf-filters[\s\S]*data-wf2-csv[\s\S]*<\/div>/, 'una sola línea');
  assert.match(html, /<th class="wf-group" colspan="3" scope="colgroup">Persona<\/th><th class="wf-group" colspan="3" scope="colgroup">Contrato<\/th>/);
  for (const t of ['Nombre', 'Rol', 'Documento · teléfono · correo · Telegram ID', 'Ingreso', 'Hora ordinaria · extra', 'Descuentos', 'Estado', 'Acciones']) assert.ok(html.includes(`>${t}</th>`), t);
  // Cada fila muestra todos los campos: teléfono, correo, Telegram, ingreso, horas y descuentos.
  assert.match(html, /<span class="wf-sub">Doc\.<\/span> <span class="wf-sub">—<\/span><\/span><span class="wf-kv"><span class="wf-sub">Tel\.<\/span> 300<\/span><span class="wf-kv"><span class="wf-sub">Correo<\/span> <span class="wf-wrap">n@u\.co<\/span><\/span><span class="wf-kv"><span class="wf-sub">Telegram<\/span> 5<\/span>/);
  assert.match(html, /<span class="wf-sub">Ord\.<\/span> 18<\/span><span class="wf-kv"><span class="wf-sub">Extra<\/span> 24<\/span>/);
  assert.match(html, /<span class="wf-sub">1:<\/span> 10<\/span><span class="wf-kv"><span class="wf-sub">2:<\/span> 0<\/span>/);
  assert.match(html, /<span class="wf-role-text">Director<\/span>/, 'rol visible completo');
  assert.match(html, /Tecnico<\/span> <span class="wf-pill wf-pill-warn"[^>]*>rol no habilitado<\/span>/, 'rol apagado: marcado, sin cambiarlo');
  assert.match(html, /data-wf2-menu="e2"[^>]*>Acciones/, 'menú por fila con nombre');
  assert.match(html, /data-wf2-edit="e2">Editar[\s\S]*data-wf2-act="activate" data-id="e2">Activar[\s\S]*class="wf-menu-item wf-menu-danger" data-wf2-delete="e2">Eliminar/);
  assert.match(html, /class="wf-cards"/, 'tarjetas para celular');
  m.menu = '';
});

test('editar: todos los campos; el rol ofrece solo los de la empresa; Eliminar pide confirmación y archiva', async () => {
  const { W } = load();
  const m = await mounted(W);
  m.modal = { type: 'edit', employee: { ...EMPLOYEES[0] } };
  let html = W.view();
  for (const f of ['full_name', 'document_id', 'phone', 'email', 'telegram_user_id', 'hire_date', 'hourly_rate_regular', 'hourly_rate_extra', 'deduction_1', 'deduction_2']) assert.match(html, new RegExp(`<input name="${f}"`), f);
  assert.match(html, /<select name="role" class="wf-role-select">/); assert.match(html, /<select name="status">/);
  const options = [...html.matchAll(/<option value="([^"]+)"[^>]*>([^<]+)<\/option>/g)].map((x) => x[2]);
  assert.deepEqual(options.slice(0, 5), ['Director', 'Supervisor', 'Logística', 'Operario', 'Otro']);
  assert.match(html, /<button class="wf-btn-primary" type="submit" >Guardar<\/button>/, 'Guardar con nombre y par AA');
  m.modal = { type: 'delete', id: 'e1', name: 'Nicolás Gómez' };
  html = W.view();
  assert.match(html, /Eliminar a Nicolás Gómez[\s\S]*Se archiva para auditoría[\s\S]*class="wf-btn-danger" type="button" data-wf2-delete-go="e1"/);
  assert.match(SRC, /act\(go\.getAttribute\("data-wf2-delete-go"\), "archive"/, 'eliminar usa el mismo endpoint archive');
  assert.match(SRC, /\/employees\/\$\{encodeURIComponent\(id\)\}\/\$\{action\}/, 'activar/inactivar/archivar: endpoints de siempre');
  assert.doesNotMatch(SRC, /\bconfirm\(/, 'sin diálogos del navegador');
  m.modal = null;
});

test('contraste: el par se calcula desde el color del tema hasta pasar AA (primario y texto blancos = caso Urbania)', () => {
  const { W } = load();
  const white = { r: 255, g: 255, b: 255 };
  const p = W.pair(white, [white]);
  assert.ok(W.contrast(p.bg, p.fg) >= 4.5, 'blanco sobre blanco se corrige');
  const dark = { r: 11, g: 18, b: 32 };
  assert.deepEqual(JSON.parse(JSON.stringify(W.pair(dark, [white]))), { bg: dark, fg: white }, 'si el tema ya pasa, no se toca');
});

test('client.js: solo el enganche; con el interruptor apagado se sirve la pantalla de siempre', () => {
  const start = CLIENT.indexOf('function cxWorkforceV2On051B');
  const fn = CLIENT.slice(start, CLIENT.indexOf('\n  }\n', start) + 4);
  const on = (settings) => vm.runInNewContext(`${fn}; cxWorkforceV2On051B()`, { activeClientModules: () => [{ code: 'workforce', raw: { settings } }] });
  assert.equal(on({}), false, 'apagado por defecto');
  assert.equal(on({ workforce_v2: 'true' }), false, 'solo true de verdad');
  assert.equal(on({ workforce_v2: true }), true);
  assert.match(CLIENT, /async function renderPersonalModule\(\) \{\n    await cxLoadEmployeeRoles051A\(\);\n    if \(cxWorkforceV2On051B\(\) && await cxWorkforceV2Mount051B\(\)\) return;\n    ensurePersonalGridStyles\(\);/);
  assert.match(CLIENT, /try \{ await cxWorkforceV2Load051B\(\); \} catch \(_\) \{ return false; \}/, 'si el archivo no carga, la de siempre');
  assert.doesNotMatch(readFileSync('app/web/client.html', 'utf8'), /workforce_v2/, 'client.html no cambia');
  const sw = JSON.parse(readFileSync('app/services/switch_registry.json', 'utf8')).switches.find((s) => s.key === 'workforce_v2');
  assert.equal(sw.module, 'workforce');
  // La pantalla nueva no usa las clases/atributos que los parches viejos de Personal vigilan.
  assert.doesNotMatch(SRC, /personal-grid|data-personal-row|data-personal-search|personal-toolbar/);
});

test('tema: workforce_v2.css sin colores fijos (solo los respaldos semánticos) ni recuadro propio', () => {
  const css = CSS.replace(/\/\*[\s\S]*?\*\//g, '');
  const SEMANTIC = /var\(--cx-(success|warning|danger),\s*#[0-9a-f]{3,8}\)/gi;
  const rest = css.replace(SEMANTIC, '');
  const found = rest.match(/#[0-9a-f]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)|\b(white|black)\b(?!-)/gi) || [];
  assert.deepEqual(found, [], `colores fijos: ${found.join(', ')}`);
  for (const v of ['--cx-primary', '--cx-text', '--cx-bg']) assert.ok(css.includes(`var(${v}`), v);
  assert.doesNotMatch(css, /\.wf-root \{[^}]*(background|border-radius|padding)\s*:/, 'sin recuadro propio');
  assert.match(SRC, /class="client-hero wf-head"/); assert.match(SRC, /class="client-panel wf-panel"/); assert.match(SRC, /class="client-btn/);
  assert.match(css, /@media \(max-width: 760px\)[\s\S]*\.wf-table-wrap \{ display: none; \}[\s\S]*\.wf-cards \{ display: grid; \}/, 'celular: tarjetas');
  assert.match(css, /min-height: 44px/);
});
