// Turnos (modulo shifts): pantalla, permisos visibles, textos por t() en es/en/fr
// y el enganche de client.js (solo desde la tarjeta del modulo activo).
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { readFileSync } = require('node:fs');

const SRC = readFileSync('app/web/shifts_v1.js', 'utf8');
const CLIENT = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');
const DICT_SRC = readFileSync('app/web/client_i18n_dict.js', 'utf8');

function load(extra = {}) {
  const window = { ...extra };
  vm.runInContext(SRC, vm.createContext({ window, document: {}, URLSearchParams, JSON, Object, Array, String, Number, Math, Date, Map, Set, Promise, Error, Intl, encodeURIComponent }));
  return window.CxShiftsV1;
}

function dict() {
  const window = {};
  vm.runInContext(DICT_SRC, vm.createContext({ window, Object }));
  return window.CX_I18N_DICT;
}

const T = [{ id: 'tm', code: 'M', name: 'Mañana', start: '06:00', end: '14:00', color: '#f59e0b', active: true, minutes: 480 },
  { id: 'tn', code: 'N', name: 'Noche', start: '22:00', end: '06:00', color: '#7c3aed', active: true, minutes: 480 }];
const CTX = (role) => ({ role, can: { create_change: role === 'supervisor' }, logo_url: '/brand-media/x/y.webp', templates: T,
  rules: { min_rest_hours: 12, days_off_per_week: 1, max_consecutive_days: 6, weekly_hours_cap: null, max_consecutive_nights: 3, response_hours: 2, default_weekly_hours_cap: 40 },
  coverage: [], roles: [{ code: 'operario', label: 'Operario' }],
  employees: [{ id: 'e1', name: 'Olga', role: 'operario', role_label: 'Operario', telegram: false }, { id: 'e2', name: 'Ana', role: 'operario', role_label: 'Operario', telegram: true }] });
const DAYS = ['2026-10-12', '2026-10-13', '2026-10-14', '2026-10-15', '2026-10-16', '2026-10-17', '2026-10-18'];
const WEEK = (status) => ({ week_start: DAYS[0], status, days: DAYS, assignments: [
  { id: 'a1', employee_id: 'e1', work_date: DAYS[0], template_id: 'tm', status }, { id: 'a2', employee_id: 'e1', work_date: DAYS[1], template_id: 'tn', status },
  { id: 'a3', employee_id: 'e2', work_date: DAYS[0], template_id: 'tn', status }],
  analysis: { gaps: status === 'draft' ? [{ date: '2026-10-15', template_id: 'tn', template: 'Noche', role: 'operario', missing: 1 }] : [], rest: [], fairness: [] } });

function mounted(role, status) {
  const S = load();
  Object.assign(S.model, { ctx: CTX(role), data: WEEK(status), changes: [], tab: 'grid', denied: '', modal: null });
  return S;
}

test('malla: una fila por persona, celda por dia (codigo o Libre), total X h YY min y el logo del panel', () => {
  const S = mounted('supervisor', 'published');
  const html = S.view.call(null);
  assert.equal((html.match(/class="sh-row" role="row"/g) || []).length, 2);
  assert.equal((html.match(/class="sh-cell/g) || []).length, 14);
  assert.match(html, /<b>16 h 00 min<\/b>/, 'Olga: mañana + noche');
  assert.match(html, /Olga<\/b><small>Operario · sin bot<\/small>/);
  assert.match(html, /<img class="sh-logo" src="\/brand-media\/x\/y\.webp"/);
  for (const t of ['Malla', 'Cambios (0)', 'Configuración', '← Módulos', 'Armar malla', 'Publicar al bot', 'Cambio de turno', '✓ Cobertura completa', '✓ Descansos cumplidos']) assert.ok(html.includes(t), t);
  assert.match(html, /data-sh-build disabled/, 'la semana publicada no se rearma');
  assert.match(html, /data-sh-cell="a1"/, 'el supervisor abre el cambio desde la celda');
  assert.doesNotMatch(html, /contenteditable|<input/, 'sin edición manual de celdas');
});

test('el dueño y el director no crean cambios; borrador con hueco dicho en palabras', () => {
  const S = mounted('director', 'draft');
  const html = S.view();
  assert.doesNotMatch(html, /data-sh-change|data-sh-cell=/);
  assert.match(html, /data-sh-publish >|data-sh-publish>/);
  assert.match(html, /⚠ Falta 1 operario · Noche · /);
  assert.equal(S.gapText({ missing: 2, role: 'operario', template: 'Noche', date: '2026-10-15' }).startsWith('Faltan 2 operario · Noche · '), true);
});

test('cambio de turno: candidatos con razones, descartados y "no hay suficientes" sin inventar', () => {
  const S = mounted('supervisor', 'published');
  S.model.modal = { employee_id: 'e1', assignment_id: 'a1', proposal: { enough: false, candidates: [{ employee_id: 'e2', name: 'Ana', kind: 'swap', swap_template_id: 'tn', week_minutes: 480, attendance: 3, punctuality: 2, changes: 0, telegram: true }],
    discarded: [{ employee_id: 'e9', name: 'Beto', reasons: ['rest', 'cap'] }] } };
  const html = S.view();
  assert.match(html, /role="dialog"/);
  assert.match(html, /Intercambio directo/);
  assert.match(html, /Le pasa su turno Noche · 8 h 00 min en la semana · 3 días con asistencia · 2 entradas a tiempo · 0 cambios recientes/);
  assert.match(html, /Beto: sin el descanso mínimo, pasa el tope semanal/);
  assert.match(html, /Solo hay 1 candidato válido/);
  assert.match(html, /data-sh-create disabled/, 'con menos de 2 no se envía');
});

test('cambios: seguimiento creada -> esperando a X -> resultado, sin cubrir en alerta y respuesta a mano', () => {
  const S = mounted('supervisor', 'published');
  S.model.tab = 'changes';
  S.model.changes = [{ id: 'c1', requester_employee_id: 'e1', template_id: 'tm', work_date: DAYS[0], status: 'waiting', uncovered: false, current_index: 0, deadline_at: '2026-10-12T17:00:00Z',
    candidates: [{ employee_id: 'e2', name: 'Ana' }], log: [{ at: '2026-10-12T15:00:00Z', kind: 'created', by: 'sup', candidates: 1 }, { at: '2026-10-12T15:00:00Z', kind: 'offered', name: 'Ana', bot: true }] },
  { id: 'c2', requester_employee_id: 'e2', template_id: 'tn', work_date: DAYS[1], status: 'expired', uncovered: true, current_index: null, candidates: [], log: [{ at: '2026-10-12T15:00:00Z', kind: 'uncovered' }] }];
  const html = S.view();
  assert.match(html, /Cambios \(1\)/);
  assert.match(html, /Creada por sup · 1 candidatos[\s\S]*Esperando a Ana/);
  assert.match(html, /Registrar respuesta de Ana:[\s\S]*data-sh-reply="c1" data-sh-accept="1"/);
  assert.match(html, /sh-change is-alert[\s\S]*Sin cubrir[\s\S]*Lista agotada: turno sin cubrir/);
  S.model.ctx = CTX('director');
  assert.doesNotMatch(S.view(), /data-sh-reply|data-sh-send|data-sh-cancel/, 'solo el supervisor actúa sobre los cambios');
});

test('configuración: plantillas, reglas con selectores (tope = el de Personal) y cobertura por rol', () => {
  const S = mounted('director', 'draft');
  S.model.tab = 'config';
  const html = S.view();
  for (const k of ['min_rest_hours', 'days_off_per_week', 'max_consecutive_days', 'weekly_hours_cap', 'max_consecutive_nights', 'response_hours']) assert.match(html, new RegExp(`<select data-sh-rule="${k}">`), k);
  assert.match(html, /<option value="" selected>40 h \(el de Personal\)<\/option>/);
  assert.match(html, /Nocturno: cruza la medianoche/);
  assert.match(html, /data-sh-cov="operario" data-t="tm"/);
});

test('textos por t(): todos tienen inglés y francés en el diccionario único', () => {
  const D = dict();
  const keys = new Set([...SRC.matchAll(/T\("([^"]*)"/g)].map((m) => m[1]));
  for (const k of ['Creada', 'Esperando respuesta', 'Aceptado', 'Rechazado', 'Vencido', 'Cancelado', 'sin el descanso mínimo', 'pasa el tope semanal', 'otro rol']) keys.add(k);
  const missing = [...keys].filter((k) => !(k in D.en) || !(k in D.fr));
  assert.deepEqual(missing, []);
  const calls = [];
  const S = load({ CxI18n: { t: (s, v) => { calls.push(s); return (D.en[s] || s).replace(/\{(\w+)\}/g, (m, k) => (v && v[k] !== undefined ? v[k] : m)); }, locale: () => 'en-US' } });
  Object.assign(S.model, { ctx: CTX('supervisor'), data: WEEK('published'), changes: [], tab: 'grid' });
  const html = S.view();
  assert.match(html, /<h1 class="client-title">Shifts<\/h1>/);
  assert.match(html, /Build schedule/);
  assert.ok(calls.includes('Libre'));
});

test('client.js: Turnos solo se abre desde su tarjeta y carga su archivo aparte', () => {
  assert.match(CLIENT, /if \(code === "shifts" && await cxShiftsOpen055A\(\)\) \{\n\s+return;\n\s+\}\n\n\s+if \(code === "workforce"\)/);
  assert.match(CLIENT, /\/client-static\/shifts_v1\.js\?v=055A/);
  assert.match(CLIENT, /\/client-static\/shifts_v1\.css\?v=055A/);
  assert.match(CLIENT, /token: authToken/);
  assert.match(SRC, /\/turnos\/companies\/\$\{encodeURIComponent\(ctx\.companyId\)\}/);
  assert.match(SRC, /Authorization: `Bearer \$\{t\}`/, 'siempre con la sesión');
  const S = load();
  assert.equal(S.monday('2026-10-18'), '2026-10-12');
  assert.equal(S.hm(2400), '40 h 00 min');
});
