// Turnos abiertos y "Cerrar turno" (interruptor open_shift_alert).
// - Apagado (otra empresa): client.js no carga el archivo ni cambia CRM Campo / Personal.
// - Encendido (VOLTAGE): lista de turnos abiertos con horas, "más de 12 h", y Cerrar
//   turno con la hora real de salida EN LA HORA DEL LUGAR y nota obligatoria.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const SRC = readFileSync('app/web/open_shifts.js', 'utf8');
const CSS = readFileSync('app/web/open_shifts.css', 'utf8');
const CLIENT = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');

function load() {
  const window = {};
  const listeners = {};
  const document = { addEventListener: (t, f) => { listeners[t] = f; } };
  vm.runInNewContext(SRC, { window, document, Intl, Date, setInterval: () => 1, clearInterval: () => {}, console });
  return { O: window.CxOpenShifts, listeners };
}

const DATA = {
  ok: true, alert_hours: 12, can_close: true, long_open: 1,
  shifts: [
    { employee_id: 'e1', employee_name: 'Ana <b>', status: 'working', shift_started_at: '2026-11-01T11:00:00Z', hours_open: 13.5,
      work_location_id: 'va', work_location_name: 'Virginia', timezone: 'America/New_York' },
    { employee_id: 'e2', employee_name: 'Dan', status: 'on_break', shift_started_at: '2026-11-02T19:00:00Z', hours_open: 5,
      work_location_id: null, work_location_name: null, timezone: 'America/Chicago' },
  ],
};

test('hora del lugar <-> UTC, también con cambio de horario', () => {
  const { O } = load();
  assert.equal(O.zonedToUtcIso('2026-11-02T18:30', 'America/New_York'), '2026-11-02T23:30:00Z', 'EST = UTC-5');
  assert.equal(O.zonedToUtcIso('2026-07-02T18:30', 'America/New_York'), '2026-07-02T22:30:00Z', 'EDT = UTC-4');
  assert.equal(O.zonedToUtcIso('2026-11-02T18:30', 'America/Chicago'), '2026-11-03T00:30:00Z');
  assert.equal(O.utcToZonedInput('2026-11-02T23:30:00Z', 'America/New_York'), '2026-11-02T18:30');
  assert.equal(O.zonedToUtcIso('mañana', 'America/New_York'), '');
  assert.equal(O.hoursLabel(13.5), '13 h 30 min');
});

test('validación igual que el servidor: salida después del inicio, no futura, nota obligatoria', () => {
  const { O } = load();
  const shift = DATA.shifts[0];
  const now = Date.parse('2026-11-02T02:00:00Z');
  assert.equal(O.validate({ end_local: '', note: 'olvidó finalizar' }, shift, now).field, 'end_at');
  assert.equal(O.validate({ end_local: '2026-11-01T05:00', note: 'olvidó finalizar' }, shift, now).field, 'end_at', 'antes del inicio');
  assert.equal(O.validate({ end_local: '2026-11-02T08:00', note: 'olvidó finalizar' }, shift, now).field, 'end_at', 'futuro');
  assert.equal(O.validate({ end_local: '2026-11-01T18:30', note: ' ok ' }, shift, now).field, 'note');
  assert.equal(JSON.stringify(O.validate({ end_local: '2026-11-01T18:30', note: '  salió  6:30 pm ' }, shift, now)),
    JSON.stringify({ ok: true, body: { end_at: '2026-11-01T23:30:00Z', note: 'salió 6:30 pm' } }));
});

test('vista: solo turnos de más de 12 h, con su botón; escapa nombres; N = 0 no dibuja nada', () => {
  const { O } = load();
  const html = O.view(DATA);
  assert.match(html, /<h3>Turnos de más de 12 h \(1\)<\/h3>/);
  assert.ok(!html.includes('Turnos abiertos'), 'el título viejo ya no sale');
  assert.match(html, /Ana &lt;b&gt;/);
  assert.ok(!html.includes('Ana <b>'));
  assert.match(html, /Virginia · Trabajando/);
  assert.ok(!html.includes('Dan'), 'el turno de 5 h no aparece aquí (solo en la vista por lugar)');
  assert.equal((html.match(/data-cxos-open=/g) || []).length, 1, 'un solo botón Cerrar turno: el de 13 h');
  assert.ok(!O.view({ ...DATA, can_close: false }).includes('data-cxos-open'), 'sin permiso: solo lectura');
  assert.equal(O.view({ ...DATA, shifts: [] }), '');
  assert.equal(O.view({ ...DATA, shifts: [DATA.shifts[1]] }), '', 'solo turnos normales: la sección no se muestra');
  const seven = { ...DATA.shifts[1], employee_id: 'e7', employee_name: 'Eva', hours_open: 7 };
  assert.equal(O.view({ ...DATA, shifts: [seven] }), '', 'turno de 7 h: no aparece');
  assert.match(O.view({ ...DATA, alert_hours: 6, shifts: [seven] }), /Turnos de más de 6 h \(1\)/, 'límite de la empresa');
  const thirteen = { ...seven, hours_open: 13 };
  const sixteen = { ...seven, hours_open: 16 };
  assert.equal(O.view({ ...DATA, alert_hours: 15, shifts: [thirteen] }), '', 'con 15 h, el turno de 13 h no aparece');
  const fifteen = O.view({ ...DATA, alert_hours: 15, shifts: [sixteen] });
  assert.match(fifteen, /Turnos de más de 15 h \(1\)/);
  assert.ok(!fifteen.includes('12 h'), 'el título dice el valor de la empresa');
  assert.equal(O.view({ ...DATA, alert_hours: undefined, shifts: [sixteen] }), '', 'sin valor del servidor no inventa un límite');
});

test('turno de 7 h no se puede cerrar desde la pantalla (no hay botón ni envío)', async () => {
  const { O } = load();
  const host = { innerHTML: '', contains: () => true };
  let posts = 0;
  const seven = { ...DATA.shifts[1], employee_id: 'e7', employee_name: 'Eva', hours_open: 7 };
  const api = async (path, opts) => { if (opts && opts.method === 'POST') posts += 1; return { ...DATA, shifts: [seven] }; };
  await O.mount({ companyId: 'c1', api, host: () => host });
  assert.equal(host.innerHTML, '');
  O.model.open = 'e7';
  await O.submit('e7', { end_local: '2026-11-01T18:30', note: 'Olvidó finalizar' });
  assert.equal(posts, 0);
});

test('el 400 del servidor (aún no supera 12 horas) se muestra tal cual', async () => {
  const { O } = load();
  const host = { innerHTML: '', contains: () => true };
  const api = async (path, opts) => {
    if (opts && opts.method === 'POST') throw new Error('400 Bad Request {"detail":"Este turno aún no supera 12 horas"}');
    return DATA;
  };
  await O.mount({ companyId: 'c1', api, host: () => host });
  O.model.open = 'e1';
  await O.submit('e1', { end_local: '2026-11-01T18:30', note: 'Olvidó finalizar' });
  assert.match(host.innerHTML, /Este turno aún no supera 12 horas/);
});

test('cerrar turno: envía hora del lugar en UTC y nota, recarga y confirma', async () => {
  const { O } = load();
  const calls = [];
  const host = { innerHTML: '', contains: () => true };
  let data = JSON.parse(JSON.stringify(DATA));
  const api = async (path, opts) => {
    calls.push([path, opts]);
    if (opts && opts.method === 'POST') { data = { ...data, shifts: data.shifts.slice(1), long_open: 0 }; return { ok: true }; }
    return data;
  };
  await O.mount({ companyId: 'c1', api, host: () => host });
  assert.equal(calls[0][0], '/open-shifts/companies/c1');
  O.model.open = 'e1';
  await O.submit('e1', { end_local: '2026-11-01T18:30', note: 'Olvidó finalizar' });
  const post = calls.find((c) => c[1] && c[1].method === 'POST');
  assert.equal(post[0], '/open-shifts/companies/c1/employees/e1/close');
  assert.deepEqual(JSON.parse(post[1].body), { end_at: '2026-11-01T23:30:00Z', note: 'Olvidó finalizar' });
  assert.match(host.innerHTML, /cerrado\. Quedó en la auditoría/);
  assert.ok(!host.innerHTML.includes('Turnos de más de'), 'quedó en 0: solo el aviso de cerrado');
});

test('error del servidor se muestra y no se envía con nota vacía', async () => {
  const { O } = load();
  const host = { innerHTML: '', contains: () => true };
  let posts = 0;
  const api = async (path, opts) => {
    if (opts && opts.method === 'POST') { posts += 1; throw new Error('422 Unprocessable {"detail":"Esa persona no tiene un turno abierto."}'); }
    return DATA;
  };
  await O.mount({ companyId: 'c1', api, host: () => host });
  O.model.open = 'e1';
  await O.submit('e1', { end_local: '2026-11-01T18:30', note: '' });
  assert.equal(posts, 0);
  assert.match(host.innerHTML, /La nota es obligatoria/);
  await O.submit('e1', { end_local: '2026-11-01T18:30', note: 'Olvidó finalizar' });
  assert.equal(posts, 1);
  assert.match(host.innerHTML, /Esa persona no tiene un turno abierto\./);
});

test('client.js: solo con el interruptor, arriba de CRM Campo por lugar y de Personal v2', () => {
  assert.match(CLIENT, /return settings\.open_shift_alert === true;/);
  assert.match(CLIENT, /async function cxOpenShiftsAttach060C\(anchorId\) \{\n    if \(!cxOpenShiftsOn060C\(\)\) return false;/);
  assert.match(CLIENT, /if \(mounted\) cxOpenShiftsAttach060C\("cxCrmPlacesHost059A"\);/);
  assert.match(CLIENT, /authApi: api,\n    \}\);\n    cxOpenShiftsAttach060C\("cxWorkforceV2Host051B"\);/);
  assert.match(CLIENT, /\/client-static\/open_shifts\.js\?v=071A/);
  assert.match(CLIENT, /\/client-static\/open_shifts\.css\?v=071A/);
  assert.match(readFileSync('app/web/client.html', 'utf8'), /client\.js\?v=[^"]*_060C_060D[^"]*"/, 'el navegador pide el client.js nuevo');
});

test('CSS sin colores propios (solo el tema)', () => {
  assert.ok(!/#[0-9a-f]{3,8}\b/i.test(CSS), 'sin hex');
  assert.ok(!/rgb\(|hsl\(/i.test(CSS));
});
