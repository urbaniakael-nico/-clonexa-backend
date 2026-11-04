// 063A: Nómina EE. UU. por operación (interruptor us_payroll; hoy solo VOLTAGE). Solo horas
// y valores: un resumen y una tabla por operación (Virginia ET, Alabama CT), búsqueda rápida,
// filtro Por confirmar, detalle día por día SIN ubicación, mapa ni notas (eso queda en
// Reportes). Virginia sale de la fixture real del servidor (tests/fixtures/us_payroll_caso.json);
// Alabama son datos inventados con la misma forma (45 h -> 40 + 5 overtime a $20/h).
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const PAYROLL = readFileSync('app/web/payroll_v2.js', 'utf8');
const CSS = readFileSync('app/web/payroll_v2.css', 'utf8');
const CLIENT = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');
const FIX = JSON.parse(readFileSync('tests/fixtures/us_payroll_caso.json', 'utf8'));
const clone = (v) => JSON.parse(JSON.stringify(v));

function payroll(store = {}) {
  const localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
  const window = { addEventListener() {} };
  const document = { addEventListener() {}, activeElement: null, createElement: () => ({ style: {}, remove() {} }) };
  vm.runInNewContext(PAYROLL, { window, document, console, Intl, Date, setTimeout, clearTimeout, localStorage });
  return window.CxPayrollV2;
}

// Alabama: 5 días de 9 h (lun-vie), tarifa $20 -> 40 h regulares + 5 h overtime = $950.
function alabamaRow() {
  const days = [2, 3, 4, 5, 6].map((d) => ({ date: `2026-11-0${d}`, payable: 540, pause: 0, regular: d < 6 ? 540 : 240, overtime: d < 6 ? 0 : 300 }));
  return {
    employee_id: 'emp-jose', employee_name: 'José Núñez Prueba', employee_role: 'operario', closed_shifts: 5, regular_minutes: 2400, extra_minutes: 300,
    gross_amount: 950, discount_amount: 0, net_amount: 950, rate_pending: false,
    shifts: days.map((d) => ({ start: `${d.date}T13:00:00Z`, end: `${d.date}T22:00:00Z`, regular_minutes: d.regular, extra_minutes: d.overtime, pause_minutes: 0,
      connected_minutes: 540, worked_minutes: 540, gross_amount: '0' })),
    us: { place: 'Alabama', place_missing: false, tz: 'America/Chicago', abbr: 'CT', days_worked: 5, connected_minutes: 2700, pause_minutes: 0, payable_minutes: 2700,
      regular_minutes: 2400, overtime_minutes: 300, rate: 20, overtime_rate: 30, regular_amount: 800, overtime_amount: 150, gross: 950, deductions: 0, net: 950, rate_pending: false,
      weeks: [{ week_start: '2026-11-01', week_end: '2026-11-07', payable: 2700, pause: 0, regular: 2400, overtime: 300, days }] },
  };
}

function snapshot() {
  const s = clone(FIX.snapshot);
  s.rows.push(alabamaRow());
  s.us_payroll.operations = [{ name: 'Virginia', abbr: 'ET', tz: 'America/New_York' }, { name: 'Alabama', abbr: 'CT', tz: 'America/Chicago' }];
  s.unverified_shifts = [{ employee_id: 'emp-oscar', employee_name: 'Óscar Peña Prueba', employee_role: 'operario', place: 'Alabama', abbr: 'CT', source: 'attendance',
    session_ref: 'ci-9', closure_id: 'cl-9', start: '2026-11-04T12:00:00Z', end: '2026-11-05T05:00:00Z', minutes: 900, status: 'pending' }];
  s.totals = { ...s.totals, people: 2, regular_minutes: 525 + 2400, extra_minutes: 300, payable_minutes: 525 + 2700, pause_minutes: 55, connected_minutes: 580 + 2700,
    gross_amount: 950, net_amount: 950, rate_pending: true };
  return s;
}

function screen(extra = {}, store) {
  const P = payroll(store);
  Object.assign(P.model, { snapshot: snapshot(), activity: { documents: { 'emp-caso': 'DOC-1122', 'emp-jose': 'AL-5566' } }, period: { from: '2026-11-01', to: '2026-11-07' },
    cfg: null, open: '', query: '', opFilter: 'all', usSort: 'payable', usMode: 'week', modal: null, loading: false, notice: '', error: '' }, extra);
  return P;
}

const section = (html, name) => {
  const i = html.indexOf(`aria-label="Tabla ${name}"`);
  if (i < 0) return '';
  const j = html.indexOf('</section>', i);
  return html.slice(i, j);
};
const summary = (html, name) => {
  const i = html.indexOf(`aria-label="Resumen ${name}"`);
  return i < 0 ? '' : html.slice(i, html.indexOf('</section>', i));
};

test('063A: dos operaciones, cada una con su resumen y su tabla (Virginia ET, Alabama CT) y su total', () => {
  const html = screen().view();
  assert.match(html, /<h1 class="client-title">Nómina semanal<\/h1>[\s\S]*Semana laboral <b>Dom 01\/11 – Sáb 07\/11<\/b>[\s\S]*Overtime por encima de 40 h · Pausas sin pago/);
  assert.match(html, /data-pvu-mode="week">Semana[\s\S]*data-pvu-mode="fortnight">Quincena[\s\S]*data-pvu-mode="custom">Personalizado/);
  assert.match(html, /data-pv-us-export="csv">CSV[\s\S]*data-pv-us-export="pdf">Descargar PDF/);
  assert.match(html, /data-pvu-filter="all">Ambas operaciones[\s\S]*data-pvu-filter="Virginia">Virginia \(ET\)[\s\S]*data-pvu-filter="Alabama">Alabama \(CT\)[\s\S]*data-pvu-filter="pending">Por confirmar \(1\)/);
  assert.ok(html.indexOf('Resumen Virginia') < html.indexOf('Resumen Alabama'), 'Virginia primero (de este a oeste)');
  assert.match(html, /class="pvu-sum pvu-op-0" aria-label="Resumen Virginia"/, 'Virginia: acento verde agua');
  assert.match(html, /class="pvu-sum pvu-op-1" aria-label="Resumen Alabama"/, 'Alabama: acento ámbar');
  assert.match(summary(html, 'Virginia'), /<h2>Virginia<\/h2><span>\d\d:\d\d ET · 1 persona/);
  assert.match(summary(html, 'Alabama'), /<h2>Alabama<\/h2><span>\d\d:\d\d CT · 2 personas/);
  const al = section(html, 'Alabama');
  assert.match(al, /<thead><tr><th scope="col" class="">Empleado<\/th><th scope="col" class="">Rol<\/th><th scope="col" class="pvu-n">Días[\s\S]*En turno[\s\S]*Pausas[\s\S]*Pagables[\s\S]*Regulares[\s\S]*Overtime[\s\S]*Tarifa[\s\S]*Bruto[\s\S]*Neto[\s\S]*Estado/);
  assert.match(al, /José Núñez Prueba[\s\S]*data-label="Días" class="pvu-n">5<[\s\S]*data-label="Pagables" class="pvu-n pvu-pay"><b>45 h 00<\/b>[\s\S]*data-label="Regulares" class="pvu-n">40 h 00[\s\S]*<b class="pvu-ot">5 h 00<\/b>[\s\S]*\$20\/h[\s\S]*\$950[\s\S]*pvu-chip is-ok">OK/);
  assert.match(al, /Total Alabama[\s\S]*<b>45 h 00<\/b>[\s\S]*<b class="pvu-ot">5 h 00<\/b>[\s\S]*1 salida por confirmar/);
  const va = section(html, 'Virginia');
  assert.match(va, /Colaboradora Caso 2 Nov[\s\S]*<b>8 h 45<\/b>[\s\S]*data-label="Overtime" class="pvu-n">0 h 00<[\s\S]*<span class="pvu-pend">Pendiente<\/span>/);
  assert.doesNotMatch(va, /pvu-ot/, 'sin overtime no se resalta');
  assert.doesNotMatch(html, /\$0(\.00)?\b/, 'sin tarifa nunca $0.00');
  assert.match(summary(html, 'Virginia'), /Bruto<\/span><strong>Tarifa pendiente/);
  assert.match(html, /Solo horas y valores\. Ubicación, notas y bitácora están en Reportes\.[\s\S]*53 h 45 pagables · 5 h 00 overtime · 1 por confirmar/);
});

test('063A: los totales de cada resumen cuadran con la suma de las filas de su tabla', () => {
  const P = screen();
  const cards = P.buildCards(P.model.snapshot, P.model.activity);
  const ops = P.usOperations(P.model.snapshot, cards);
  assert.deepEqual(ops.map((o) => [o.name, o.people.length]), [['Virginia', 1], ['Alabama', 2]]);
  ops.forEach((o) => {
    const sum = (k) => o.people.reduce((s, c) => s + Number((c.us || {})[k] || 0), 0);
    assert.equal(o.totals.payable, sum('payable_minutes'));
    assert.equal(o.totals.regular, sum('regular_minutes'));
    assert.equal(o.totals.overtime, sum('overtime_minutes'));
    assert.equal(o.totals.pause, sum('pause_minutes'));
  });
  assert.equal(ops[1].totals.overtime, 300, 'overtime solo por encima de 40 h');
  assert.equal(ops[1].totals.pendingCount, 1);
  const html = P.view();
  assert.match(summary(html, 'Alabama'), /Horas pagables<\/span><strong>45 h 00[\s\S]*Regulares<\/span><strong>40 h 00[\s\S]*Overtime<\/span><strong>5 h 00[\s\S]*Bruto<\/span><strong>\$950[\s\S]*Por confirmar<\/span><strong>1 · 15 h 00/);
});

test('063A: búsqueda rápida por nombre con y sin tilde, por documento, en las dos operaciones; "N de M"; los resúmenes no cambian', () => {
  const base = screen().view();
  const sums = (html) => [summary(html, 'Virginia'), summary(html, 'Alabama')];
  for (const q of ['nunez', 'NÚÑEZ', 'José', 'AL-5566']) {
    const html = screen({ query: q }).view();
    assert.match(html, /1 de 3 personas/, q);
    assert.match(section(html, 'Alabama'), /José Núñez Prueba/, q);
    assert.equal(section(html, 'Virginia'), '', `${q}: Virginia sin coincidencias no muestra tabla`);
    assert.deepEqual(sums(html), sums(base), `${q}: los resúmenes son de toda la operación`);
  }
  const both = screen({ query: 'prueba' }).view();
  assert.match(both, /2 de 3 personas/);
  const doc = screen({ query: 'doc-1122' }).view();
  assert.match(section(doc, 'Virginia'), /Colaboradora Caso 2 Nov/);
  const none = screen({ query: 'zzz' }).view();
  assert.match(none, /0 de 3 personas/);
  assert.match(none, /Nadie coincide con &#039;zzz&#039;/);
  assert.match(none, /data-pvu-clear aria-label="Limpiar búsqueda"/, 'la X para limpiar');
  assert.deepEqual(sums(none), sums(base));
  assert.match(PAYROLL, /event\.key === "Escape" && t && t\.matches && t\.matches\("\[data-pv-search\]"\)[^\n]*model\.query = ""/, 'Esc limpia la búsqueda');
  assert.match(screen({ query: '<b>' }).view(), /Nadie coincide con &#039;&lt;b&gt;&#039;/, 'escapa la búsqueda');
});

test('063A: chips de operación y filtro Por confirmar con botón Confirmar salida; el aviso único y Revisar', () => {
  const al = screen({ opFilter: 'Alabama' }).view();
  assert.doesNotMatch(al, /Resumen Virginia|Tabla Virginia/);
  assert.match(al, /Tabla Alabama/);
  const pend = screen({ opFilter: 'pending' }).view();
  assert.match(pend, /1 de 3 personas/);
  const t = section(pend, 'Alabama');
  assert.match(t, /Óscar Peña Prueba[\s\S]*pvu-chip is-warn">1 salida por confirmar<\/span> <button type="button" class="pvu-confirm" data-pv-confirm="0">Confirmar salida/);
  assert.doesNotMatch(t, /José Núñez/);
  assert.match(t, /Óscar Peña Prueba[\s\S]*data-label="Rol" class="pvu-role">operario</, 'trae su rol (antes "Sin rol")');
  const html = screen().view();
  assert.equal((html.match(/role="status"/g) || []).length, 1, 'un solo aviso');
  assert.match(html, /⚠ 1 turno por confirmar<\/strong> · 15 h 00 no entran a la nómina hasta registrar la salida real[\s\S]*data-pvu-review>Revisar/);
  assert.doesNotMatch(html, /empleados sin tarifa|Sin valor hora/, 'sin avisos extra: el bruto dice Tarifa pendiente');
});

test('063A: diálogo Confirmar salida: hora real + nota obligatoria (auditoría); otra empresa, nota opcional', () => {
  const P = screen();
  const item = P.model.snapshot.unverified_shifts[0];
  P.model.modal = { item, realEnd: '2026-11-04T16:00', note: '', preview: null, error: '', busy: false, ratePending: true };
  let html = P.view();
  assert.match(html, /Nota \(obligatoria\)<\/span><textarea data-pv-note[^>]*required aria-required="true"/);
  assert.match(html, /data-pv-confirm-go disabled>Confirmar salida/);
  assert.match(html, /Queda en la auditoría: quién confirmó, cuándo y la nota\./);
  assert.equal(P.confirmReady(P.model.modal), false);
  P.model.modal.note = '   ';
  assert.equal(P.confirmReady(P.model.modal), false, 'solo espacios no cuenta');
  P.model.modal.note = 'Olvidó marcar la salida';
  assert.equal(P.confirmReady(P.model.modal), true);
  P.model.modal.preview = { before: { regular_minutes: 0, extra_minutes: 0, net_amount: 0 }, after: { regular_minutes: 240, extra_minutes: 0, net_amount: 0 } };
  html = P.view();
  assert.match(html, /Regulares<\/th><td>0 h 00 min<\/td><td>4 h 00 min[\s\S]*Neto<\/th><td>Pendiente<\/td><td>Pendiente/);
  // Otra empresa (sin us_payroll): todo como antes.
  const O = payroll();
  Object.assign(O.model, { snapshot: { rows: [], totals: {}, unverified_shifts: [item] }, period: { from: '2026-10-01', to: '2026-10-15' }, cfg: null,
    modal: { item, realEnd: '2026-11-04T16:00', note: '', preview: null, error: '', busy: false } });
  assert.match(O.view(), /Nota \(opcional\)/);
  assert.equal(O.confirmReady(O.model.modal), true);
});

test('063A: detalle de la persona: solo su semana día por día (hora del lugar), sin ubicación, mapa ni notas', () => {
  const html = screen({ open: 'emp-caso' }).view();
  const d = html.slice(html.indexOf('pvu-detail-row'), html.indexOf('</div></td></tr>', html.indexOf('pvu-detail-row')));
  assert.match(d, /Semana Dom 01\/11 – Sáb 07\/11 · hora ET/);
  assert.match(d, /Lun 02\/11<\/th>\s*<td data-label="Entrada">06:45<\/td><td data-label="Salida">16:25<\/td>\s*<td data-label="En turno" class="pvu-n">9 h 40<\/td><td data-label="Pausas" class="pvu-n">0 h 55<\/td>\s*<td data-label="Pagables" class="pvu-n"><b>8 h 45<\/b>/);
  assert.match(d, /Dom 01\/11[\s\S]*Sáb 07\/11/);
  assert.match(d, /Total<\/th><td><\/td><td><\/td><td class="pvu-n">9 h 40<\/td><td class="pvu-n">0 h 55<\/td><td class="pvu-n"><b>8 h 45<\/b>/);
  assert.match(d, /data-reports-open>Ver ubicación y notas en Reportes/);
  for (const banned of [/Sin perímetro/, /Ver en el mapa/, /google\.com\/maps/, /Resumen de la jornada/, /Etiquetado rack/, /Notas/, /usp-/]) assert.doesNotMatch(html, banned);
  const al = screen({ open: 'emp-jose' }).view();
  assert.match(al, /hora CT[\s\S]*Lun 02\/11<\/th>\s*<td data-label="Entrada">07:00<\/td><td data-label="Salida">16:00</, 'Alabama en hora de Chicago');
  const q = screen({ open: 'emp-jose', period: { from: '2026-10-25', to: '2026-11-07' }, usMode: 'fortnight' }).view();
  assert.match(q, /Nómina quincenal[\s\S]*Semana Dom 25\/10 – Sáb 31\/10[\s\S]*Semana Dom 01\/11 – Sáb 07\/11/, 'quincena: dos semanas');
  const p = screen({ open: 'emp-oscar' }).view();
  assert.match(p, /Mié 04\/11 · entrada 07:00 CT · 15 h 00 sin liquidar[\s\S]*data-pv-confirm="0">Confirmar salida/);
});

test('063A: semana laboral dom-sáb y quincena; orden y elección recordada (localStorage)', () => {
  const P0 = payroll();
  const P = { usPeriodFor: (...a) => JSON.parse(JSON.stringify(P0.usPeriodFor(...a))) };
  assert.deepEqual(P.usPeriodFor('week', '2026-11-03', 'sunday'), { from: '2026-11-01', to: '2026-11-07' });
  assert.deepEqual(P.usPeriodFor('week', '2026-11-01', 'sunday'), { from: '2026-11-01', to: '2026-11-07' });
  assert.deepEqual(P.usPeriodFor('week', '2026-11-07', 'sunday'), { from: '2026-11-01', to: '2026-11-07' });
  assert.deepEqual(P.usPeriodFor('fortnight', '2026-11-03', 'sunday'), { from: '2026-10-25', to: '2026-11-07' });
  assert.deepEqual(P.usPeriodFor('week', '2026-11-03', 'monday'), { from: '2026-11-02', to: '2026-11-08' });
  const S = screen();
  const people = S.buildCards(S.model.snapshot, S.model.activity);
  const names = (sort) => JSON.parse(JSON.stringify(S.usVisible(people, '', 'all', sort).map((c) => c.name)));
  assert.deepEqual(names('payable'), ['José Núñez Prueba', 'Colaboradora Caso 2 Nov', 'Óscar Peña Prueba']);
  assert.deepEqual(names('name'), ['Colaboradora Caso 2 Nov', 'José Núñez Prueba', 'Óscar Peña Prueba']);
  assert.deepEqual(names('overtime')[0], 'José Núñez Prueba');
  assert.deepEqual(names('status')[0], 'Óscar Peña Prueba');
  assert.match(PAYROLL, /const US_PREFS = "cx_pv_us_063a";/);
  assert.match(PAYROLL, /try \{ localStorage\.setItem\(`\$\{US_PREFS\}:\$\{ctx\.companyId\}`/);
  assert.match(PAYROLL, /JSON\.parse\(localStorage\.getItem\(`\$\{US_PREFS\}:\$\{companyId\}`\) \|\| "\{\}"\)[\s\S]{0,700}catch \(_\)/, 'lee con try/catch');
});

test('063A: client.js pasa el interruptor y la semana laboral al montar; versiones nuevas; CSS sin colores propios', () => {
  assert.match(CLIENT, /function cxPayrollUsCtx063A\(\) \{[\s\S]*settings\.us_payroll === true[\s\S]*us_payroll_rules/);
  assert.match(CLIENT, /\.\.\.cxPayrollUsCtx063A\(\), \/\/ 063A/);
  assert.match(CLIENT, /payroll_v2\.js\?v=067A/);
  assert.match(CLIENT, /payroll_v2\.css\?v=063A/);
  assert.match(readFileSync('app/web/client.html', 'utf8'), /client\.js\?v=[^"]*_063A"/);
  const block = CSS.slice(CSS.indexOf('063A'));
  assert.ok(block.length > 1000);
  assert.ok(!/#[0-9a-f]{3,8}\b/i.test(block) && !/rgb\(|hsl\(/i.test(block), 'solo variables del tema y acentos calculados para AA');
  assert.match(block, /@media \(max-width: 700px\)[\s\S]*\.pvu-table thead \{ display: none; \}/, 'en celular cada fila es una tarjeta');
});
