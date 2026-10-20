// CRM VELVET-LAB (interruptor crm_velvet_lab):
// - Personal v2: Asignar / Reiniciar / Quitar PIN CRM solo cuando el servidor
//   responde (interruptor encendido); apagado (404) Personal queda igual.
// - Tableta: horas "X h YY min", texto legible sobre el color de marca (AA),
//   20 s de espera, vuelta a la lista olvida al colaborador y textos por t().
// - Rutas: /mini-panel/crm-lab y el mini panel general redirige el tipo crm_lab.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const WF = readFileSync('app/web/workforce_v2.js', 'utf8');
const CRM = readFileSync('app/web/crm_lab.js', 'utf8');
const MINI = readFileSync('app/web/mini_panel.js', 'utf8');
const ROUTES = readFileSync('app/web/client_routes.py', 'utf8');

const EMPLOYEES = [
  { id: 'e1', full_name: 'Ana', role: 'operario', status: 'active' },
  { id: 'e2', full_name: 'Bea', role: 'operario', status: 'active' },
  { id: 'e3', full_name: 'Zoe', role: 'operario', status: 'archived' },
];

async function personal(pins) {
  const window = {};
  const listeners = {};
  const document = { addEventListener: (t, f) => { listeners[t] = f; }, activeElement: null, createElement: () => ({ style: {}, remove() {} }) };
  vm.runInNewContext(WF, { window, document, Blob: function Blob() {}, URL: {}, getComputedStyle: undefined, console });
  const W = window.CxWorkforceV2;
  const host = { innerHTML: '', querySelector: () => null, contains: () => true };
  const calls = [];
  const api = async (path, opts = {}) => {
    calls.push(`${opts.method || 'GET'} ${path}`);
    if (path.startsWith('/crm-lab/')) {
      if (pins === null) throw new Error('{"detail":"CRM VELVET-LAB no está activo para esta empresa."}');
      return opts.method ? { ok: true } : { pins };
    }
    return EMPLOYEES;
  };
  await W.mount({ companyId: 'c1', host: () => host, roles: () => [['operario', 'Operario']], configured: () => true, personalApi: api });
  await new Promise((r) => setTimeout(r, 0));
  return { W, host, listeners, calls };
}

test('Personal con el interruptor: insignia y menú Asignar / Reiniciar / Quitar PIN CRM', async () => {
  const { W, calls } = await personal({ e1: { has_pin: true } });
  assert.ok(calls.includes('GET /crm-lab/companies/c1/pins'));
  const html = W.view();
  assert.match(html, /PIN CRM ✓/);
  assert.match(html, /Sin PIN CRM/);
  W.model.menu = 'e1';
  assert.match(W.view(), /Reiniciar PIN CRM/);
  assert.match(W.view(), /Quitar PIN CRM/);
  W.model.menu = 'e2';
  assert.match(W.view(), /Asignar PIN CRM/);
  assert.doesNotMatch(W.view(), /Quitar PIN CRM/);
  W.model.menu = 'e3';
  assert.doesNotMatch(W.view(), /PIN CRM<\/button>/, 'archivados sin PIN');
  W.model.modal = { type: 'pin', id: 'e2', name: 'Bea' };
  const modal = W.view();
  assert.match(modal, /PIN CRM de Bea/);
  assert.match(modal, /inputmode="numeric" pattern="\[0-9\]\{4\}" maxlength="4"/);
  assert.match(modal, /Se guarda cifrado/);
});

test('Personal sin el interruptor (404): nada de PIN, igual que siempre', async () => {
  const { W } = await personal(null);
  assert.equal(W.model.pins, null);
  W.model.menu = 'e1';
  const html = W.view();
  assert.doesNotMatch(html, /PIN CRM/);
});

function crm() {
  const window = {};
  vm.runInNewContext(CRM, { window, URLSearchParams, location: { search: '?company_id=c1' }, console, Date, Math, setInterval, setTimeout });
  return window.CxCrmLab;
}

test('tableta: horas X h YY min, texto AA sobre la marca y 20 s', () => {
  const C = crm();
  assert.equal(C.hm(0), '0 h 00 min');
  assert.equal(C.hm(83), '1 h 23 min');
  assert.equal(C.hm(600.4), '10 h 00 min');
  assert.equal(C.IDLE_MS, 20000);
  for (const color of [[176, 18, 111], [245, 194, 231], [255, 255, 255], [0, 0, 0], [124, 58, 237], [250, 204, 21]]) {
    const on = C.readableOn(color) === '#ffffff' ? [255, 255, 255] : [17, 17, 17];
    assert.ok(C.contrast(on, color) >= 4.5, `texto legible sobre ${color}`);
  }
});

test('tableta: volver a la lista olvida al colaborador; sin PIN pide al administrador', () => {
  const C = crm();
  Object.assign(C.st, { token: 't', view: 'person', person: { employee_id: 'e1', name: 'Ana', status: 'working', sizes: [] }, empToken: 'emp', pinFor: null,
    board: { people: [{ employee_id: 'e4', name: 'Dani', status: 'sin_turno', has_pin: false }], live: [] } });
  assert.match(C.view(), /Listo · siguiente colaborador/);
  C.backToList();
  assert.equal(C.st.empToken, '');
  assert.equal(C.st.person, null);
  C.st.pinFor = 'e4';
  assert.match(C.view(), /Pide tu PIN al administrador/);
  assert.doesNotMatch(C.view(), /data-crm-key/, 'sin PIN no se muestra el teclado');
});

test('tableta: acciones según el estado y nada por persona', () => {
  const C = crm();
  const view = (status, reference) => {
    Object.assign(C.st, { token: 't', view: 'person', person: { employee_id: 'e1', name: 'Ana', status, reference, sizes: [] }, board: { people: [] } });
    return [...C.view().matchAll(/data-crm-act="([a-z_]+)"/g)].map((m) => m[1]);
  };
  assert.deepEqual(view('sin_turno', null), [], 'sin turno: primero la referencia (no hay Iniciar turno suelto)');
  assert.deepEqual(view('working', null), ['pause', 'end_shift', 'pick_start']);
  assert.deepEqual(view('working', { id: 'r', name: 'PANT SET' }), ['pause', 'end_shift', 'pick_switch', 'pick_close']);
  assert.deepEqual(view('on_break', { id: 'r', name: 'PANT SET' }), ['resume', 'end_shift', 'pick_switch', 'pick_close']);
  assert.doesNotMatch(CRM, /por persona|per_person|productividad/i);
  for (const text of ['Pausa', 'Reanudar', 'Fin de turno', 'Iniciar referencia', 'Cambiar referencia', 'Cerrar prendas']) {
    assert.ok(CRM.includes(`"${text}"`), `${text} pasa por t()`);
  }
});

test('sin turno: 1 · PIN → 2 · ¿En qué vas a trabajar? → 3 · Iniciar; sin referencia no se puede iniciar', () => {
  const C = crm();
  const refs = [{ id: 'r1', name: 'PANT SET', pending: 12 }, { id: 'r2', name: 'Choco-fresa', pending: 0 }];
  Object.assign(C.st, { token: 't', view: 'list', pinFor: 'e1', pin: '', board: { people: [{ employee_id: 'e1', name: 'Ana', status: 'sin_turno', has_pin: true }] } });
  let html = C.view();
  assert.match(html, /<ol class="crm-steps"[\s\S]*class="is-on" aria-current="step">\s*1 · PIN/, 'paso 1 en el PIN');
  Object.assign(C.st, { pinFor: null, view: 'person', refs, startRef: '', person: { employee_id: 'e1', name: 'Ana', status: 'sin_turno', reference: null, sizes: [] } });
  html = C.view();
  assert.match(html, /class="is-on" aria-current="step">\s*2 · ¿En qué vas a trabajar\?/);
  assert.match(html, /<b>PANT SET<\/b><small>Pendiente 12<\/small>/, 'cada referencia con su pendiente');
  assert.match(html, /data-crm-startgo disabled>\s*Elige una referencia para iniciar<\/button>/, 'deshabilitado hasta elegir');
  C.st.startRef = 'r1';
  html = C.view();
  assert.match(html, /class="is-on" aria-current="step">\s*3 · Iniciar/);
  assert.match(html, /data-crm-startgo >\s*▶ Iniciar turno en PANT SET<\/button>/);
  assert.match(html, /aria-checked="true"\s*class="crm-btn crm-refopt is-on" data-crm-startref="r1"/);
  // Con turno activo: el panel de siempre.
  Object.assign(C.st, { person: { employee_id: 'e1', name: 'Ana', status: 'working', reference: { id: 'r', name: 'PANT SET' }, sizes: [] } });
  html = C.view();
  assert.doesNotMatch(html, /crm-steps|data-crm-startgo/);
  assert.match(CRM, /if \(t\.closest\("\[data-crm-startgo\]"\)\) \{ if \(st\.startRef\) act\("start_shift", \{ reference_id: st\.startRef \}\); return; \}/);
  assert.equal(C.ERRORS.elige_una_referencia, 'Elige una referencia para iniciar.');
  C.backToList();
  assert.equal(C.st.startRef, '', 'volver a la lista olvida la referencia elegida');
});

test('rutas: página propia y el mini panel general redirige crm_lab', () => {
  assert.match(ROUTES, /"\/mini-panel\/crm-lab": "crm_lab\.html"/);
  assert.match(MINI, /\["crm_lab", "crmlab", "crm-lab"\]\.includes\(panelType\)/);
  assert.match(MINI, /window\.location\.replace\(`\/mini-panel\/crm-lab\?company_id=/);
});

test('consola v2+: tarjeta CRM VELVET-LAB solo con el interruptor (404 = no se muestra) y crea el usuario único', () => {
  const SRC = readFileSync('app/web/admin_v2plus_company.js', 'utf8');
  assert.match(SRC, /crmLab: \(id\) => apiGet\(`\$\{API\}\/crm-lab\/companies\/\$\{encodeURIComponent\(id\)\}\/panel-user`\)\.catch\(\(\) => \(\{ off: true \}\)\)/);
  assert.match(SRC, /if \(!crm \|\| crm\.off\) return "";/);
  assert.match(SRC, /createCrmUser: \(id\) => apiPost\(`\$\{API\}\/crm-lab\/companies\/\$\{encodeURIComponent\(id\)\}\/panel-user`, \{\}\)/);
  assert.match(SRC, /modulos: \["modules", "activity", "crmLab"\]/);
  assert.match(SRC, /data-vpf-reset="\$\{h\(crm\.user_id\)\}">Regenerar clave/);
});
