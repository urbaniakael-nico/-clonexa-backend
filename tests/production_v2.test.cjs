// Producción v2 (interruptor production_v2):
// - "Sin datos aún" con su motivo cuando una cifra no tiene datos.
// - Lote atrasado en rojo, equipo del lote y detalle (tallas, cortes, novedades, horas).
// - Tiempo del equipo apilado por persona con el título "participación, no productividad".
// - Nunca cifras de prendas por persona; horas "X h YY min".
// - client.js solo monta el tablero nuevo con el interruptor encendido.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const SRC = readFileSync('app/web/production_v2.js', 'utf8');
const CLIENT = readFileSync('app/web/client.js', 'utf8');

function load() {
  const window = {};
  vm.runInNewContext(SRC, { window, document: {}, URLSearchParams, console });
  return window.CxProductionV2;
}

const SIN = (reason) => ({ status: 'sin_datos', value: null, reason });
const DATA = {
  company: { name: 'VELVET' },
  period: { from: '2026-10-13', to: '2026-10-19', by: 'week' },
  kpis: {
    workshop_now: { status: 'ok', value: 2, working: 1, paused: 1, lots: 1 },
    closed: SIN('Aún no hay cierres registrados.'),
    sent: SIN('Aún no hay envíos a Bombón registrados en Referencias.'),
    days_per_lot: SIN('Ningún lote se completó en el periodo.'),
    team_hours_per_garment: SIN('Sin prendas cerradas en el periodo.'),
    labor_per_garment: SIN('Sin prendas cerradas en el periodo.'),
  },
  lots_in_process: [{
    key: 'choco', name: 'Choco-fresa', meta: 58, closed: 10, pending: 48, sent: 0, days_open: 30, late: true, working_now: 1,
    team: ['Ana', 'Bea'], people: [{ name: 'Ana', seconds: 14400 }, { name: 'Bea', seconds: 3600 }],
    sizes: [{ size: 'M', meta: 58, received: 58, closed: 10, pending: 48 }],
    cuts: [{ date: '2026-10-14', sizes: [{ size: 'M', quantity: 58 }], quantity: 58 }],
    news: [{ section: 'bordado', quantity: 2 }], team_seconds: 18000,
  }],
  live: [{ name: 'Ana', status: 'working', reference: 'Choco-fresa', elapsed_minutes: 75 }],
  series: [{ bucket: '2026-10-12', closed: 0, sent: 0 }],
  team_time: { total_seconds: 18000, by_reference: [{ key: 'choco', name: 'Choco-fresa', seconds: 18000, percent: 100,
    people: [{ name: 'Ana', seconds: 14400 }, { name: 'Bea', seconds: 3600 }] }] },
  alerts: [{ kind: 'open_news', level: 'warning', reference: 'Choco-fresa', section: 'bordado', quantity: 2 },
    { kind: 'slow_lot', level: 'danger', reference: 'Choco-fresa', days: 30, avg: 12, percent: 17 }],
};

test('Sin datos aún con su motivo y horas X h YY min', () => {
  const P = load();
  P.model.data = DATA;
  const html = P.view();
  assert.equal((html.match(/Sin datos aún/g) || []).length, 5);
  assert.match(html, /Aún no hay cierres registrados\./);
  assert.match(html, /1 h 15 min/);
  assert.equal(P.hm(75), '1 h 15 min');
});

test('lote atrasado en rojo, equipo y detalle con tallas, cortes, novedades y horas', () => {
  const P = load();
  P.model.data = DATA;
  P.model.open = 'choco';
  const html = P.view();
  assert.match(html, /pp-lot is-late/);
  assert.match(html, /Equipo: Ana, Bea/);
  assert.match(html, /10 \/ 58/);
  for (const s of ['Recibido', 'Cortes por fecha', 'Novedades por sección', 'Bordado', 'Horas del equipo en el lote', '4 h 00 min']) assert.ok(html.includes(s), s);
});

test('tiempo apilado por persona: participación, no productividad; nada de prendas por persona', () => {
  const P = load();
  P.model.data = DATA;
  const html = P.view();
  assert.match(html, /Participación, no productividad/);
  assert.equal((html.match(/class="pp-tone-\d" style="--w:/g) || []).length, 2);
  for (const bad of [/prendas por persona/i, /por día por persona/i, /minutos por prenda por persona/i]) assert.doesNotMatch(html, bad);
  assert.equal(P.alertText(DATA.alerts[0]), 'Novedades en Bordado: 2 prendas (Choco-fresa)');
  assert.equal(P.alertText({ kind: 'not_sent', reference: 'X', quantity: 3 }), 'X: 3 prendas cerradas sin enviar a Bombón');
});

test('client.js monta el tablero solo con production_v2 encendido', () => {
  assert.match(CLIENT, /settings\.production_v2 === true/);
  assert.match(CLIENT, /if \(cxProductionV2On056G\(\) && await cxProductionV2Mount056G\(\)\) return;/);
});
