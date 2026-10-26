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

test('sin turno: 1 · PIN → 2 · Referencia → 3 · Iniciar; sin referencia no se puede iniciar', () => {
  const C = crm();
  const refs = [{ id: 'r1', name: 'PANT SET', pending: 12 }, { id: 'r2', name: 'Choco-fresa', pending: 0 }];
  Object.assign(C.st, { token: 't', view: 'list', pinFor: 'e1', pin: '', board: { people: [{ employee_id: 'e1', name: 'Ana', status: 'sin_turno', has_pin: true }] } });
  let html = C.view();
  assert.match(html, /<ol class="crm-steps"[\s\S]*class="is-on" aria-current="step">\s*1 · PIN/, 'paso 1 en el PIN');
  Object.assign(C.st, { pinFor: null, view: 'person', refs, startRef: '', person: { employee_id: 'e1', name: 'Ana', status: 'sin_turno', reference: null, sizes: [] } });
  html = C.view();
  assert.match(html, /class="is-on" aria-current="step">\s*2 · Referencia/);
  assert.match(html, /<p class="crm-say">¿En qué vas a trabajar\?<\/p>/);
  assert.match(html, /<b>PANT SET<\/b><small>Pendiente 12<\/small>/, 'cada referencia con su pendiente');
  assert.match(html, /data-crm-startgo disabled>\s*Elige una referencia para iniciar<\/button>/, 'deshabilitado hasta elegir');
  assert.match(html, /<div class="crm-foot"><button type="button" class="crm-btn is-primary crm-startgo"/, 'el botón Iniciar abajo a la izquierda');
  C.st.startRef = 'r1';
  html = C.view();
  assert.match(html, /class="is-on" aria-current="step">\s*3 · Iniciar/);
  assert.match(html, /data-crm-startgo >\s*▶ Iniciar turno en PANT SET<\/button>/);
  assert.match(html, /aria-checked="true"\s*class="crm-refopt is-on" data-crm-startref="r1"/);
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

test('056K: CRM en vivo ordenado por estado y alfabético, tarjetas con su etiqueta y cronómetro h:mm:ss', () => {
  const C = crm();
  const people = [
    { employee_id: 's2', name: 'zoe', status: 'sin_turno' }, { employee_id: 'p1', name: 'Bea', status: 'on_break', reference_name: 'PANT', since: '2026-10-19T10:00:00Z', paused_since: '2026-10-19T11:00:00Z' },
    { employee_id: 'w2', name: 'Carla', status: 'working', reference_name: 'Body', since: '2026-10-19T09:00:00Z' }, { employee_id: 's1', name: 'Álvaro', status: 'sin_turno' },
    { employee_id: 'w1', name: 'ana', status: 'working', reference_name: 'PANT', since: '2026-10-19T08:00:00Z' },
  ];
  assert.deepEqual(Array.from(C.ordered(people), (p) => p.employee_id), ['w1', 'w2', 'p1', 's1', 's2']);
  Object.assign(C.st, { token: 't', view: 'list', pinFor: null, person: null, query: '', board: { working: 2, paused: 1, people } });
  const html = C.view();
  assert.match(html, /class="crm-tile is-working" data-crm-pick="w1">\s*<span class="crm-tag">TRABAJANDO<\/span><span class="crm-name">ana<\/span><span class="crm-ref">PANT<\/span><span class="crm-clock" data-crm-clock="2026-10-19T08:00:00Z">/);
  assert.match(html, /class="crm-tile is-on_break" data-crm-pick="p1">[\s\S]*?EN PAUSA[\s\S]*?data-crm-clock="2026-10-19T11:00:00Z"/, 'en pausa: el tiempo en pausa');
  assert.match(html, /class="crm-tile is-sin_turno" data-crm-pick="s1">[\s\S]*?SIN TURNO[\s\S]*?Toca para iniciar/);
  assert.match(html, /●<\/i> 2 trabajando[\s\S]*●<\/i> 1 en pausa/);
  C.st.offset = 0;
  assert.match(C.hms(new Date(Date.now() - (3600 + 125) * 1000).toISOString()), /^1:02:0[56]$/);
  assert.equal(C.hms(''), '');
  assert.match(CRM, /querySelectorAll\("\[data-crm-clock\]"\)\.forEach\(\(el\) => \{\s*const text = hms\(el\.getAttribute\("data-crm-clock"\)\);/, 'corre cada segundo en el navegador');
});

test('056K: colores del tema de la empresa (Velvet: TRABAJANDO aqua, acento morado) y AA; otro tema cambia los colores', () => {
  const C = crm();
  const velvet = C.palette({ primary: '#7c3aed', theme: { background: 'linear-gradient(135deg, #00ffe1, #a600ff)', primary: '#a600ff', secondary: '#8cff00', bg: '#00ffe1', warning: '' } });
  assert.equal(velvet.page, 'linear-gradient(135deg, #00ffe1, #a600ff)', 'el mismo fondo del portal');
  assert.equal(velvet.work, 'rgb(0,255,225)');
  assert.equal(velvet.accent, 'rgb(166,0,255)');
  assert.equal(velvet.pause, undefined, 'sin color de aviso en el tema: el ámbar de respaldo');
  const other = C.palette({ theme: { background: 'linear-gradient(135deg, #050509, #1d4ed8)', primary: '#1d4ed8', secondary: '#f97316', bg: '#050509', warning: '#eab308' } });
  for (const k of ['page', 'work', 'accent', 'bar', 'idle', 'surface']) assert.notEqual(other[k], velvet[k], k);
  assert.equal(other.work, 'rgb(249,115,22)', 'fondo oscuro: TRABAJANDO con el secundario');
  const n = (c) => c.match(/\d+/g).map(Number);
  for (const p of [velvet, other]) {
    for (const k of ['accent', 'bar', 'work', 'work-line', 'idle', 'idle-line', 'surface', 'key']) {
      const on = p[`on-${k}`] === '#ffffff' ? [255, 255, 255] : [17, 17, 17];
      assert.ok(C.contrast(on, n(p[k])) >= 4.5, `${k}: texto AA`);
    }
  }
  assert.doesNotMatch(readFileSync('app/web/crm_lab.js', 'utf8').match(/function palette[\s\S]*?\r?\n  \}\r?\n/)[0], /#[0-9a-f]{6}/i, 'sin colores fijos en la paleta');
});

test('056K: pantalla completa solo con soporte; manifest para abrir sin barra', () => {
  const C = crm();
  assert.equal(C.fsOk(), false, 'sin document: sin botón');
  Object.assign(C.st, { token: 't', view: 'list', pinFor: null, board: { people: [] } });
  assert.doesNotMatch(C.view(), /data-crm-fs/);
  assert.match(CRM, /document\.fullscreenEnabled \|\| document\.webkitFullscreenEnabled/);
  assert.match(CRM, /el\.requestFullscreen \|\| el\.webkitRequestFullscreen/);
  assert.match(CRM, /"Salir de pantalla completa"/);
  const html = readFileSync('app/web/crm_lab.html', 'utf8');
  assert.match(html, /<link rel="manifest" href="\/client-static\/crm_lab\.webmanifest\?v=056K">/);
  assert.match(html, /name="apple-mobile-web-app-capable" content="yes"/);
  assert.match(html, /viewport-fit=cover/);
  const m = JSON.parse(readFileSync('app/web/crm_lab.webmanifest', 'utf8'));
  assert.equal(m.display, 'fullscreen');
  assert.equal(m.orientation, 'any');
  assert.ok(m.start_url.startsWith('/mini-panel/crm-lab') && m.scope === '/mini-panel/crm-lab');
  assert.ok(m.icons.some((i) => i.sizes === '512x512'));
  assert.match(CRM, /COMPANY_KEY = "clonexa_crm_lab_company"/, 'desde la pantalla de inicio recuerda la empresa');
  assert.match(readFileSync('app/web/client_routes.py', 'utf8'), /allowed_names=frozenset\(\{"crm_lab\.webmanifest"\}\)/);
  const CSS = readFileSync('app/web/crm_lab.css', 'utf8');
  assert.match(CSS, /height: 100dvh/);
  assert.match(CSS, /env\(safe-area-inset-top\)/);
  assert.match(CSS, /@media \(orientation: portrait\) \{\s*\.crm-grid \{ grid-template-columns: repeat\(2, minmax\(0, 1fr\)\); \}/);
});

test('056L: cronómetro grande = TRABAJADO del turno (no se reinicia al cambiar de referencia); pausas y referencias en letra pequeña', () => {
  const C = crm();
  const now = '2026-10-27T01:00:00.000Z';
  const people = [
    { employee_id: 'w1', name: 'Ana', status: 'working', reference_name: '1300', since: '2026-10-26T23:50:00Z',
      connected_seconds: 14400, pause_seconds: 2100, worked_seconds: 12300, current_pause_seconds: null,
      reference_started_at: '2026-10-26T23:50:00Z', reference_worked_seconds: 4200, previous_reference: { name: '1234', worked_seconds: 3600 } },
    { employee_id: 'p1', name: 'Bea', status: 'on_break', reference_name: '1200', since: '2026-10-27T00:00:00Z', paused_since: '2026-10-27T00:40:00Z',
      connected_seconds: 3600, pause_seconds: 1200, worked_seconds: 2400, current_pause_seconds: 1200,
      reference_started_at: '2026-10-27T00:00:00Z', reference_worked_seconds: 2400, previous_reference: null },
  ];
  Object.assign(C.st, { token: 't', view: 'list', pinFor: null, person: null, query: '', offset: 0, board: { now, working: 1, paused: 1, people } });
  const html = C.view().replace(/\s+/g, ' ');
  const ana = html.match(/data-crm-pick="w1">.*?<\/button>/)[0];
  assert.match(ana, /<span class="crm-meta">Pausa <span class="crm-meta-t">0:35<\/span><\/span>/, 'total de pausas, discreto y quieto mientras trabaja');
  assert.match(ana, /<span class="crm-meta-n">Ref\. 1300<\/span>&nbsp;·&nbsp;<span class="crm-meta-t" data-crm-clock="2026-10-26T23:50:00.000Z" data-crm-fmt="hm">1:10<\/span>/, 'la referencia actual corre (sin pausas)');
  assert.match(ana, /<span class="crm-meta-n">Anterior: Ref\. 1234<\/span>&nbsp;·&nbsp;<span class="crm-meta-t">1:00<\/span>/, 'duración de la referencia anterior');
  assert.match(ana, /<span class="crm-clock" data-crm-clock="2026-10-26T21:35:00.000Z">3:25:00<\/span>/, 'trabajado = conectado - pausas y corre');
  const bea = html.match(/data-crm-pick="p1">.*?<\/button>/)[0];
  assert.match(bea, /class="crm-meta is-pausing">En pausa <span class="crm-meta-t" data-crm-clock="2026-10-27T00:40:00.000Z" data-crm-fmt="hm">0:20<\/span> · total pausas <span class="crm-meta-t" data-crm-clock="2026-10-27T00:40:00.000Z" data-crm-fmt="hm">0:20<\/span>/, 'en pausa: la línea de pausa corre');
  assert.match(bea, /Ref\. 1200<\/span>&nbsp;·&nbsp;<span class="crm-meta-t">0:40<\/span>/, 'la referencia queda congelada en pausa');
  assert.match(bea, /<span class="crm-clock">0:40:00<\/span>/, 'el cronómetro grande queda congelado en el trabajado');
  assert.doesNotMatch(bea, /Anterior/);
  // Sin los campos nuevos (servidor viejo): la tarjeta de siempre.
  C.st.board = { now, working: 1, paused: 0, people: [{ employee_id: 'x', name: 'Old', status: 'working', reference_name: 'PANT', since: '2026-10-27T00:00:00Z' }] };
  assert.match(C.view(), /<span class="crm-ref">PANT<\/span><span class="crm-clock" data-crm-clock="2026-10-27T00:00:00Z">/);
});
