// 071A: Horario de la semana (interruptor work_schedule). CRM Campo: "Horario de la semana" al
// frente de cada operación, chip Fuera de horario y Horario 2 por persona; editor con Horario 1/2,
// día puntual y copia de semana; portal: Cerrar turno de cualquier turno con motivo y doble
// confirmación; panel del líder: solo salida programada u hora actual; Board: chip rojo;
// Personal: selector Horario. Con el interruptor apagado, client.js no carga nada nuevo.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const WEB = 'app/web/';
const SRC = readFileSync(`${WEB}work_schedule.js`, 'utf8');
const CSS = readFileSync(`${WEB}work_schedule.css`, 'utf8');
const OPEN = readFileSync(`${WEB}open_shifts.js`, 'utf8');
const CRM = readFileSync(`${WEB}crm_places.js`, 'utf8').replace(/\r\n/g, '\n');
const BOARD = readFileSync(`${WEB}reports_board.js`, 'utf8');
const WF = readFileSync(`${WEB}workforce_v2.js`, 'utf8');
const PANEL = readFileSync(`${WEB}lider_operacion.js`, 'utf8');
const DICT = readFileSync(`${WEB}client_i18n_dict.js`, 'utf8');
const CORE = readFileSync(`${WEB}client_i18n_core.js`, 'utf8');
const CLIENT = readFileSync(`${WEB}client.js`, 'utf8').replace(/\r\n/g, '\n');
const LIDER_HTML = readFileSync(`${WEB}lider_operacion.html`, 'utf8');

function loadWs() {
  const window = {};
  const document = { addEventListener() {}, getElementById: () => null, body: null, querySelector: () => null, activeElement: null };
  vm.runInNewContext(SRC, { window, document, Intl, Date, console, JSON });
  return window.CxWorkSchedule;
}

const H1 = { slot: 1, name: 'Horario 1', days: [0, 1, 2, 3, 4], start: '07:00', end: '17:00', lunch_start: '12:00', lunch_end: '13:00', overrides: { '2026-11-13': { start: '07:00', end: '13:00' } } };
const H2 = { slot: 2, name: 'Horario 2', days: [1, 2, 3, 4, 5], start: '09:00', end: '19:00', overrides: { '2026-11-14': { off: true } } };

test('reglas puras: semana, días puntuales, cuerpo que se guarda y nota de copia', () => {
  const W = loadWs();
  assert.equal(W.addDays('2026-11-09', 6), '2026-11-15');
  assert.equal(W.clock('17:00'), '5:00 p. m.');
  assert.equal(W.clock('07:05'), '7:05 a. m.');
  assert.equal(W.weekLabel('2026-11-09'), 'Semana del 9 nov al 15 nov');
  assert.equal(W.dayMode(H1, '2026-11-13'), 'custom');
  assert.equal(W.dayMode(H2, '2026-11-14'), 'off');
  assert.equal(W.dayMode(H1, '2026-11-10'), 'normal');
  assert.deepEqual(JSON.parse(JSON.stringify(W.planOf(H1, '2026-11-13', 4))), { off: false, start: '07:00', end: '13:00', special: true });
  assert.equal(W.planOf(H1, '2026-11-15', 6).off, true);
  const body = W.bodyOf('2026-11-09', [H1, H2]);
  assert.equal(body.week_start, '2026-11-09');
  assert.deepEqual(body.slots.map((s) => s.slot), [1, 2]);
  assert.equal(body.slots[1].lunch_start, null);
  const added = W.newSlot([H1]);
  assert.equal(added.name, 'Horario 2');
  assert.equal(added.start, '07:00');
  assert.match(W.sourceNote({ configured: true, source: 'copied', copied_from: '2026-11-02' }), /Copiado de la semana del 2 nov/);
  assert.match(W.sourceNote({ configured: false }), /el bot no le pregunta a nadie/);
  assert.equal(W.zoneLabel('America/Chicago'), 'CT');
  assert.equal(W.zoneLabel('America/New_York'), 'ET');
});

test('CRM Campo: "Horario de la semana" al frente de cada operación; editar solo dueño/admin; chips por persona', () => {
  const W = loadWs();
  const group = { key: 'va', name: 'Virginia', schedule: { configured: true, slots: [{ slot: 1, name: 'Horario 1', today: '7:00 a. m. – 5:00 p. m.' }] } };
  W._ctx({ canEdit: () => true });
  let html = W.sectionExtra(group);
  assert.match(html, /Horario de la semana/);
  assert.match(html, /Hoy: 7:00 a\. m\. – 5:00 p\. m\./);
  assert.match(html, /data-cxws-open="va"[^>]*>Editar horario</);
  W._ctx({ canEdit: () => false });
  assert.match(W.sectionExtra(group), />Ver horario</);
  assert.match(W.sectionExtra({ ...group, schedule: { configured: false, slots: [] } }), /Sin horario configurado/);
  assert.equal(W.sectionExtra({ key: 'none', name: 'Sin asignar', schedule: null }), '', 'Sin asignar no lleva horario');
  const two = { ...group, schedule: { configured: true, slots: [{ name: 'Horario 1', today: 'A' }, { name: 'Horario 2', today: 'B' }] } };
  assert.match(W.sectionExtra(two), /Horario 1: A · Horario 2: B/);
  assert.match(W.rowExtra({ schedule: { out_of_schedule: true, slot_name: 'Horario 2' } }), /cxws-chip is-late">Fuera de horario<.*Horario 2/);
  assert.equal(W.rowExtra({ schedule: { out_of_schedule: false, slot_name: null } }), '');
  assert.equal(W.rowExtra({}), '', 'sin el interruptor el servidor no manda schedule');
});

test('editor: Horario 1 y 2, día puntual, "+ Agregar horario", selector por persona; solo lectura sin permiso', () => {
  const W = loadWs();
  const data = { week_start: '2026-11-09', configured: true, source: 'week', can_edit: true, location: { id: 'va', name: 'Virginia', timezone: 'America/New_York' },
    slots: [H1, H2], people: [{ id: 'p1', name: 'Ana <b>', slot: 1 }, { id: 'p2', name: 'Beto', slot: 2 }] };
  Object.assign(W.model, { open: true, loc: data.location, data, slots: [H1, H2] });
  let html = W.modalView();
  assert.match(html, /Horario de la semana · Virginia/);
  assert.match(html, /Semana del 9 nov al 15 nov/);
  assert.match(html, /\(ET\)/);
  assert.match(html, /<legend>Horario 1<\/legend>.*<legend>Horario 2<\/legend>/s);
  assert.match(html, /name="ostart-0-2026-11-13" value="07:00".*name="oend-0-2026-11-13" value="13:00"/s, 'viernes con otra hora');
  assert.match(html, /name="mode-1-2026-11-14"[^]*?<option value="off" selected>/, 'sábado libre en Horario 2');
  assert.match(html, /\+ Agregar horario/);
  assert.match(html, /Guardar esta semana/);
  assert.match(html, /solo de referencia: se descuenta únicamente la pausa que la persona marca/);
  assert.match(html, /Horario de cada persona/);
  assert.match(html, /data-cxws-person="p2"[^>]*>.*<option value="2" selected>Horario 2/s);
  assert.ok(html.includes('Ana &lt;b&gt;') && !html.includes('Ana <b>'));
  W.model.data = { ...data, can_edit: false };
  html = W.modalView();
  assert.ok(!html.includes('Guardar esta semana') && !html.includes('Agregar horario'), 'el líder / supervisor solo ve');
  assert.match(html, /Solo el dueño o el administrador cambia el horario/);
  assert.match(html, /name="start-0" value="07:00" disabled/);
  assert.match(html, /Viernes 13 nov<\/th><td>7:00 a\. m\. – 1:00 p\. m\. <small>\(día puntual\)/);
  W.model.data = { ...data, slots: [H1], people: data.people };
  assert.ok(!W.modalView().includes('Horario de cada persona'), 'con un solo horario no hay selector');
  assert.match(CSS, /\.cxws-chip\.is-late \{[^}]*var\(--cx-danger, #b91c1c\)/);
  assert.match(CSS, /\.cxos-root \{ --cxos-late: var\(--cx-danger/, 'el rojo de Turnos abiertos solo con el interruptor');
  assert.match(CSS, /minmax\(0, 1fr\)/, 'no se desborda en 375 px');
});

// ------------------------------------------------------------ portal: Cerrar turno
function loadOpen() {
  const window = {};
  vm.runInNewContext(OPEN, { window, document: { addEventListener() {} }, Intl, Date, setInterval: () => 1, clearInterval() {}, console });
  return window.CxOpenShifts;
}
const SCHED = { ok: true, schedule_mode: true, alert_hours: 15, can_close: true, reasons: [{ code: 'olvido', label: 'Olvidó finalizar' }, { code: 'salida_real', label: 'Salida real confirmada' }, { code: 'otro', label: 'Otro' }],
  shifts: [
    { employee_id: 'e1', employee_name: 'Oscar Diaz', status: 'working', shift_started_at: '2026-11-08T12:00:00Z', hours_open: 31, work_location_name: 'Virginia', timezone: 'America/New_York',
      scheduled_end_at: '2026-11-08T22:00:00Z', default_end_at: '2026-11-08T22:00:00Z', out_of_schedule: false, over_limit: true, slot_name: null },
    { employee_id: 'e2', employee_name: 'Corto', status: 'working', shift_started_at: '2026-11-09T12:00:00Z', hours_open: 2, work_location_name: 'Virginia', timezone: 'America/New_York',
      scheduled_end_at: '2026-11-09T22:00:00Z', default_end_at: '2026-11-09T14:00:00Z', out_of_schedule: false, over_limit: false },
    { employee_id: 'e3', employee_name: 'Hector', status: 'on_break', shift_started_at: '2026-11-07T13:00:00Z', hours_open: 53, work_location_name: 'Alabama', timezone: 'America/Chicago',
      scheduled_end_at: '2026-11-07T23:00:00Z', default_end_at: '2026-11-07T23:00:00Z', out_of_schedule: true, over_limit: true, slot_name: 'Horario 2', reason: 'inventario' },
  ] };

test('portal (modo horario): todos los turnos abiertos, Fuera de horario primero, con su salida programada', () => {
  const O = loadOpen();
  const html = O.view(SCHED);
  assert.match(html, /<h3>Turnos abiertos \(3\)<\/h3>/);
  assert.match(html, /Fuera de horario: 1/);
  assert.deepEqual(O.scheduleShifts(SCHED).map((s) => s.employee_id), ['e3', 'e1', 'e2']);
  assert.equal((html.match(/data-cxos-open=/g) || []).length, 3, 'Cerrar turno en CUALQUIER turno abierto, no solo > 15 h');
  assert.match(html, /cxos-chip is-late">Fuera de horario/);
  assert.match(html, /Más de 15 h/);
  assert.match(html, /Salida programada 0?8\/11,? 17:00/);
  assert.match(html, /Sigue trabajando: inventario/);
  assert.ok(!O.view({ ...SCHED, shifts: [] }), 'sin turnos abiertos no dibuja nada');
  O.model.open = 'e2';
  const form = O.view(SCHED);
  assert.match(form, /name="end_local" required value="2026-11-09T09:00"/, 'hora por defecto: la actual si la salida aún no llega');
  assert.match(form, /<option value="olvido">Olvidó finalizar<\/option><option value="salida_real">Salida real confirmada<\/option><option value="otro">Otro<\/option>/);
  O.model.open = 'e1';
  assert.match(O.view(SCHED), /value="2026-11-08T17:00"/, 'la salida programada si ya pasó');
  O.model.open = null;
});

test('portal: motivo obligatorio, "Otro" pide detalle, hora editada, y DOS pasos antes de llamar al servidor', async () => {
  const O = loadOpen();
  const shift = SCHED.shifts[0];
  const now = Date.parse('2026-11-09T15:00:00Z');
  assert.equal(O.validateSchedule({ end_local: '2026-11-08T18:30', reason_code: '' }, shift, now).field, 'reason_code');
  assert.equal(O.validateSchedule({ end_local: '2026-11-08T18:30', reason_code: 'otro', reason_detail: 'no' }, shift, now).field, 'reason_detail');
  assert.equal(O.validateSchedule({ end_local: '2026-11-08T06:00', reason_code: 'olvido' }, shift, now).field, 'end_at', 'antes de la entrada');
  assert.deepEqual(JSON.parse(JSON.stringify(O.validateSchedule({ end_local: '2026-11-08T18:30', reason_code: 'olvido', reason_detail: ' ' }, shift, now))),
    { ok: true, body: { end_at: '2026-11-08T23:30:00Z', reason_code: 'olvido', reason_detail: '', confirmed: true } });
  const calls = [];
  O._ctx({ companyId: 'c1', host: () => ({ innerHTML: '', contains: () => true }), api: async (path, opts) => { calls.push({ path, opts }); return opts ? { ok: true, notified: true } : SCHED; } });
  O.model.data = SCHED;
  O.model.open = 'e1';
  const form = { getAttribute: (k) => (k === 'data-cxos-form' ? 'e1' : null), elements: { end_local: { value: '2026-11-08T18:30' }, reason_code: { value: 'salida_real' }, reason_detail: { value: 'lo vio el supervisor' } } };
  O.onSubmit({ target: form, preventDefault() {} });
  assert.equal(calls.length, 0, 'el primer paso no guarda');
  assert.equal(O.model.confirm.id, 'e1');
  let html = O.view(SCHED);
  assert.match(html, /¿Cerrar el turno de Oscar Diaz\?/);
  assert.match(html, /Salida: <b>0?8\/11,? 18:30<\/b>/);
  assert.match(html, /data-cxos-yes disabled/);
  const el = (attr, extra = {}) => ({ closest: (sel) => (sel === `[${attr}]` ? {} : null), ...extra });
  await O.onClick({ target: el('data-cxos-yes') });
  assert.equal(calls.length, 0, 'sin marcar la confirmación no se envía');
  await O.onClick({ target: el('data-cxos-check', { checked: true }) });
  assert.match(O.view(SCHED), /data-cxos-yes >Sí, cerrar turno/);
  await O.onClick({ target: el('data-cxos-yes') });
  const post = calls.find((c) => c.opts);
  assert.equal(post.path, '/open-shifts/companies/c1/employees/e1/close');
  assert.deepEqual(JSON.parse(post.opts.body), { end_at: '2026-11-08T23:30:00Z', reason_code: 'salida_real', reason_detail: 'lo vio el supervisor', confirmed: true });
  assert.match(O.model.saved, /cerrado a las 0?8\/11,? 18:30\. Quedó en la auditoría y se le avisó por el bot/);
});

test('portal sin el interruptor: el aviso de siempre (solo > límite, nota libre)', () => {
  const O = loadOpen();
  const html = O.view({ ...SCHED, schedule_mode: undefined });
  assert.match(html, /Turnos de más de 15 h \(2\)/);
  assert.ok(!html.includes('Fuera de horario'));
});

// ------------------------------------------------------------ Board de Reportes
test('Board: chip rojo "Fuera de horario" con sus horas; sin la marca, el de siempre', () => {
  const window = { addEventListener() {} };
  vm.runInNewContext(BOARD, { window, document: { addEventListener() {}, createElement: () => ({ style: {} }), hidden: false }, console, Intl, Date, setTimeout, clearTimeout, setInterval: () => 1, clearInterval() {}, localStorage: { getItem: () => null, setItem() {} }, URLSearchParams, URL });
  const B = window.CxReportsBoard;
  assert.deepEqual(JSON.parse(JSON.stringify(B.chipOf({ state: 'working', minutes: 610, out_of_schedule: true }))), { cls: 'is-late', text: 'Fuera de horario 10 h 10 min'.replace('10 h 10 min', B.hm(610)) });
  assert.equal(B.chipOf({ state: 'to_confirm', out_of_schedule: true }).cls, 'is-late');
  assert.equal(B.chipOf({ state: 'working', minutes: 60 }).cls, 'is-working');
  assert.equal(B.chipOf({ state: 'done', out_of_schedule: true }).cls, 'is-done', 'ya terminó: no es Fuera de horario');
  assert.match(readFileSync(`${WEB}reports_board.css`, 'utf8'), /\.rb-now\.is-late \{[^}]*var\(--rb-danger\)/);
});

// ------------------------------------------------------------ Personal: selector Horario
test('Personal: selector "Horario" solo si su operación tiene más de un horario', () => {
  const window = {};
  vm.runInNewContext(WF, { window, document: { addEventListener() {}, activeElement: null, createElement: () => ({ style: {} }) }, Blob: function Blob() {}, URL: {}, console });
  const W = window.CxWorkforceV2;
  W.model.wl = { locations: [{ id: 'va', name: 'Virginia', is_active: true }], assignments: { e1: 'va', e2: 'al' } };
  W.model.ws = { slots: { e1: 2 }, locations: { va: [{ slot: 1, name: 'Horario 1' }, { slot: 2, name: 'Horario 2' }], al: [{ slot: 1, name: 'Horario 1' }] }, can_edit: true };
  const html = W.scheduleSelect({ id: 'e1', work_location_id: 'va' });
  assert.match(html, /<span>Horario<\/span><select name="schedule_slot" >/);
  assert.match(html, /<option value="2" selected>Horario 2/);
  assert.equal(W.scheduleSelect({ id: 'e2', work_location_id: 'al' }), '', 'un solo horario: no aparece');
  W.model.ws.can_edit = false;
  assert.match(W.scheduleSelect({ id: 'e1', work_location_id: 'va' }), /disabled/);
  W.model.ws = null;
  assert.equal(W.scheduleSelect({ id: 'e1' }), '', 'interruptor apagado: nada cambia');
});

// ------------------------------------------------------------ panel del líder
function loadLeader() {
  const window = { location: { search: '?company_id=c1&type=lider_operacion&lugar=virginia' },
    __CX_LIDER__: { ok: true, name: 'Virginia', slug: 'virginia', accent: 0, abbr: 'ET', timezone: 'America/New_York', brand: {} },
    localStorage: { getItem: () => 'es', setItem() {} }, sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} }, history: { state: null, replaceState() {}, pushState() {} }, addEventListener() {} };
  const document = { readyState: 'complete', hidden: false, addEventListener() {}, getElementById: () => null, querySelector: () => null, querySelectorAll: () => [],
    documentElement: { setAttribute() {}, style: { setProperty() {} } }, body: null };
  const context = vm.createContext({ window, document, navigator: { language: 'es-CO' }, console, Intl, Date, URLSearchParams, setTimeout: () => 1, clearTimeout() {}, setInterval: () => 1, clearInterval() {}, MutationObserver: undefined });
  vm.runInContext(DICT, context);
  vm.runInContext(CORE, context);
  vm.runInContext(BOARD, context);
  vm.runInContext(PANEL, context);
  return window.CxLiderOperacion;
}

test('líder: chip Fuera de horario, detalle con salida programada, Cerrar turno con SOLO dos horas y dos pasos', () => {
  const L = loadLeader();
  const p = { id: 'h', name: 'Hector Sandoval', role: 'Operario', state: 'to_confirm', minutes: 3180, can_finish: false, can_close: true, out_of_schedule: true,
    scheduled_end: '5:00 p. m.', slot_name: 'Horario 1', schedule_reason: null, origin: 'app', last_mark: null, shift: { in: { t: '07:00', d: '2026-11-07', a: 'ET' }, pauses: [] } };
  const chip = L.stateChip(p, 15);
  assert.equal(chip.text, 'Fuera de horario');
  assert.match(chip.cls, /is-late/);
  L.st.crm = { people: [p], counts: { total: 1 }, limit_hours: 15, work_schedule: true, operation: { local_time: '12:00' } };
  const detail = L.detailBody(p, 15);
  assert.match(detail, /Salida programada.*5:00 p\. m\./s);
  assert.match(detail, /data-lo-close="h">Cerrar turno/);
  assert.ok(!detail.includes('data-lo-finish='), 'en un turno Fuera de horario el cierre es con motivo');
  assert.match(L.crmList(), /data-lo-horario>Horario de la semana/);
  L.st.close = { id: 'h', name: 'Hector Sandoval', scheduled: '5:00 p. m.', step: 1, choice: 'scheduled', reason: '', detail: '', confirmed: false, busy: false, error: '' };
  let html = L.closeDialog();
  assert.equal((html.match(/type="radio"/g) || []).length, 2, 'solo dos opciones');
  assert.ok(!/type="(time|datetime-local|text)"/.test(html), 'no puede escribir otra hora');
  assert.match(html, /value="scheduled" checked/);
  assert.match(html, /Salida programada · 5:00 p\. m\./);
  assert.match(html, /Hora actual · <span data-lo-clock/);
  assert.equal(L.closeStep1({ choice: 'now', reason: '' }), 'Elige el motivo del cierre.');
  assert.equal(L.closeStep1({ choice: 'now', reason: 'otro', detail: 'no' }), 'Escribe el detalle del motivo (mínimo 5 caracteres).');
  assert.equal(L.closeStep1({ choice: 'scheduled', reason: 'olvido' }), '');
  L.st.close.step = 2;
  html = L.closeDialog();
  assert.match(html, /¿Cerrar el turno de Hector Sandoval\?/);
  assert.match(html, /data-lo-close-yes disabled/, 'sin la casilla no se envía');
  L.st.close = { ...L.st.close, scheduled: '' , step: 1, choice: 'now' };
  assert.match(L.closeDialog(), /value="scheduled"  disabled/, 'sin salida programada solo la hora actual');
  assert.equal(L.closeStep1({ choice: 'scheduled', reason: 'olvido' }), 'Elige la salida programada o la hora actual.');
  L.st.close = null;
  L.st.schedule = { data: { configured: true, week_start: '2026-11-09', week_end: '2026-11-15', slots: [{ name: 'Horario 1', lunch_start: '12:00', lunch_end: '13:00',
    days_view: [{ name: 'Lunes', date: '2026-11-09', off: false, label: '7:00 a. m. – 5:00 p. m.' }, { name: 'Sábado', date: '2026-11-14', off: true, label: 'Libre' }] }] } };
  html = L.scheduleView();
  assert.match(html, /Horario de la semana/);
  assert.match(html, /7:00 a\. m\. – 5:00 p\. m\./);
  assert.ok(!html.includes('<input') && !html.includes('<select'), 'el líder solo ve el horario');
  L.st.schedule = null;
  const plain = { ...p, out_of_schedule: false, can_close: false, can_finish: true, state: 'working', scheduled_end: null };
  assert.ok(!L.detailBody(plain, 15).includes('data-lo-close='), 'sin Fuera de horario: no hay Cerrar turno');
});

test('textos nuevos traducidos (en / fr) y el panel pide los archivos nuevos', () => {
  const context = vm.createContext({ window: {}, console });
  vm.runInContext(DICT, context);
  const src = DICT;
  for (const k of ['Fuera de horario', 'Horario de la semana', 'Salida programada', 'Hora actual', 'Sí, cerrar turno', 'Olvidó finalizar']) {
    assert.equal((src.match(new RegExp(`"${k}":`, 'g')) || []).length, 2, k);
  }
  assert.match(LIDER_HTML, /lider_operacion\.js\?v=071A/);
  assert.match(LIDER_HTML, /reports_board\.js\?v=071A/);
  assert.match(LIDER_HTML, /client_i18n_dict\.js\?v=071A/);
});

test('client.js: work_schedule.js solo con el interruptor; CRM Campo recibe los ganchos solo si cargó', () => {
  assert.match(CLIENT, /settings\.work_schedule === true/);
  assert.match(CLIENT, /\/client-static\/work_schedule\.js\?v=071A/);
  assert.match(CLIENT, /\/client-static\/work_schedule\.css\?v=071A/);
  assert.match(CLIENT, /if \(!cxWorkScheduleOn071A\(\)\) return false;/);
  assert.match(CLIENT, /\.\.\.\(schedule \? \{ sectionExtra: .*rowExtra: .*\} : \{\}\)/);
  assert.match(CLIENT, /workSchedule: cxWorkScheduleOn071A\(\)/);
  assert.match(CRM, /function extra\(name, item\) \{\n    return ctx && typeof ctx\[name\] === "function"/, 'sin ganchos, CRM Campo no cambia');
  assert.match(readFileSync(`${WEB}client.html`, 'utf8'), /client\.js\?v=[^"]*_071A_[^"]*"/, 'el navegador pide el client.js nuevo');
});
