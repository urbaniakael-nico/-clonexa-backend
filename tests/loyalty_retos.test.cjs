// Retos para las mesas (interruptor loyalty_retos_v2): tarjetas de tipo con cómo se
// gana y "ya hay uno en curso", asistente Qué → Cuándo → Revisar (atajos en la zona y
// la jornada del bar, orden de las fechas, maqueta del QR sin la respuesta secreta),
// "En curso" con el botón de lo que falta, historial con premio, textos por t() en
// es/en/fr, el enganche de client.js (solo con el interruptor) y el QR de la mesa
// (polla abierta, cerrada, empate y ganador) más el desempate en Juegos en vivo.
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { readFileSync } = require('node:fs');

const SRC = readFileSync('app/web/loyalty_retos.js', 'utf8');
const CSS = readFileSync('app/web/loyalty_retos.css', 'utf8');
const CLIENT = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');
const QR = readFileSync('app/web/hospitality_order.js', 'utf8').replace(/\r\n/g, '\n');
const PLAY = readFileSync('app/web/loyalty_games_play.js', 'utf8');
const SCREEN = readFileSync('app/web/loyalty_games_screen.js', 'utf8');
const DICT = readFileSync('app/web/client_i18n_dict.js', 'utf8');

const seen = new Set();
const fill = (s, vars) => (vars ? String(s).replace(/\{(\w+)\}/g, (m, k) => (vars[k] !== undefined ? String(vars[k]) : m)) : String(s));

function load() {
  const window = { CxI18n: { t: (s, vars) => { seen.add(s); return fill(s, vars); }, locale: () => 'es-CO' } };
  vm.runInContext(SRC, vm.createContext({ window, document: {}, JSON, Object, Array, String, Number, Math, Date, Map, Set, Promise, Error, Intl, encodeURIComponent, setTimeout, clearTimeout, setInterval, clearInterval }));
  return window.CxLoyaltyRetos;
}

// 2026-10-18 21:00 en Bogotá (UTC-5) = 2026-10-19T02:00Z
const NOW = '2026-10-19T02:00:00Z';
const ST = (extra = {}) => ({
  now: NOW, role: 'admin', timezone: 'America/Bogota', business_day: { open: '18:00', close: '04:00', overnight: true }, games_on: true, currency: 'COP',
  active: { consumption: null, score_pool: null, vote_poll: null }, history: [], ...extra,
});
function retos(st) {
  const R = load();
  Object.assign(R.model, { st, offset: new Date(NOW).getTime() - Date.now(), tab: 'main', wizard: null, denied: '' });
  return R;
}

const POOL = {
  id: 'p1', campaign_type: 'score_pool', title: 'Final', prize: 'Botella', team_a: 'Colombia', team_b: 'Argentina', status: 'active', rules_version: 2,
  stage: 'registration', deadline: '2026-10-19T03:00:00Z', deadline_label: 'Pronósticos cierran en', actions: [], participants: 3,
  predictions: [{ table_number: 'Mesa 1', score_a: 2, score_b: 1 }, { table_number: 'Mesa 2', score_a: 2, score_b: 1 }, { table_number: 'Mesa 3', score_a: 0, score_b: 0 }],
  result: {}, result_status: '', winner: null, tiebreak: null,
};

test('paso 1: tres tarjetas con cómo se gana; si hay una polla en curso lo dice y lleva a ella', () => {
  const R = retos(ST({ active: { consumption: null, score_pool: POOL, vote_poll: null } }));
  const html = R.view();
  assert.match(html, /Retos para las mesas/);
  assert.match(html, /data-client-back-dashboard[\s\S]*data-rt-games[\s\S]*Historial/, 'encabezado con Juegos en vivo e Historial');
  for (const t of ['Gana la mesa con más consumo registrado en el torneo. Automático.', 'Gana quien acierte el marcador exacto.',
    'Gana según el tipo: más votos, respuesta correcta o el que elija el bar.']) assert.ok(html.includes(t), t);
  assert.match(html, /Ya hay una polla en curso: <b>Final<\/b>[\s\S]*data-rt-goto="p1"/);
  assert.match(html, /data-rt-new="consumption"/);
  assert.match(html, /data-rt-new="vote_poll"/);
  assert.doesNotMatch(html, /data-rt-new="score_pool"/, 'uno activo por tipo');
  const off = retos(ST({ games_on: false })).view();
  assert.doesNotMatch(off, /data-rt-games/, 'sin loyalty_games no hay botón de Juegos en vivo');
});

test('hora de la empresa: atajos en la zona y la jornada del bar', () => {
  const R = load();
  const tz = 'America/Bogota';
  assert.equal(new Date(R.zonedToUtc(2026, 10, 18, 20, 0, tz)).toISOString(), '2026-10-19T01:00:00.000Z');
  assert.equal(R.toInput(Date.parse('2026-10-19T01:00:00Z'), tz), '2026-10-18T20:00');
  assert.equal(R.fromInput('2026-10-18T20:00', tz), Date.parse('2026-10-19T01:00:00Z'));
  const bd = { open: '18:00', close: '04:00', overnight: true };
  // A la 1:00 a. m. del 19 la jornada sigue siendo la del 18: "Hoy 8:00 p. m." es el 18 (ya pasó).
  const late = Date.parse('2026-10-19T06:00:00Z');
  assert.deepEqual({ ...R.businessDate(late, tz, bd) }, { y: 2026, m: 10, d: 18 });
  assert.equal(R.presetTime('tonight', late, tz, bd), Date.parse('2026-10-19T01:00:00Z'));
  assert.equal(R.presetTime('tomorrow', late, tz, bd), Date.parse('2026-10-20T01:00:00Z'));
  assert.equal(R.presetTime('1h', Date.parse('2026-10-19T02:03:00Z'), tz, bd), Date.parse('2026-10-19T03:05:00Z'), 'en 1 hora, redondeado a 5 min');
  assert.equal(R.insideJornada(Date.parse('2026-10-19T08:00:00Z'), tz, bd), true, '3:00 a. m. dentro de la jornada');
  assert.equal(R.insideJornada(Date.parse('2026-10-19T15:00:00Z'), tz, bd), false, '10:00 a. m. fuera');
  const w = R.whenFromMain('consumption', Date.parse('2026-10-19T01:00:00Z'), tz);
  assert.deepEqual({ ...w }, { registration_ends_at: '2026-10-18T20:00', starts_at: '2026-10-18T20:00', ends_at: '2026-10-18T23:00' });
});

test('cuándo: validación clara del orden de las fechas y aviso fuera de la jornada', () => {
  const R = load();
  const tz = 'America/Bogota';
  const bd = { open: '18:00', close: '04:00', overnight: true };
  const now = Date.parse(NOW);
  const bad = R.checkWhen('consumption', { registration_ends_at: '2026-10-18T22:00', starts_at: '2026-10-18T21:30', ends_at: '2026-10-18T21:00' }, now, tz, bd);
  assert.deepEqual([...bad.errors], ['El torneo debe empezar cuando cierra la inscripción o después.', 'El torneo debe cerrar después de empezar.']);
  assert.deepEqual([...R.checkWhen('score_pool', { predictions_close_at: '2026-10-18T20:00' }, now, tz, bd).errors], ['La hora de pronósticos ya pasó.']);
  const ok = R.checkWhen('vote_poll', { ends_at: '2026-10-19T10:00' }, now, tz, bd);
  assert.deepEqual([...ok.errors], []);
  assert.deepEqual([...ok.warnings], ['Fuera de la jornada del bar: Cierre.']);
  assert.deepEqual([...R.checkWhen('vote_poll', { ends_at: '' }, now, tz, bd).errors], ['Falta: Cierre']);
});

test('asistente de 3 pasos por tipo: Qué → Cuándo → Revisar con maqueta del QR', () => {
  for (const type of ['consumption', 'score_pool', 'vote_poll']) {
    const R = retos(ST());
    const w = R.newWizard(type);
    R.model.wizard = w;
    let html = R.view();
    assert.match(html, /aria-current="step"><b>1<\/b><span>Qué/);
    assert.match(html, /data-rt-next/);
    assert.doesNotMatch(html, /data-rt-back/, 'el primer paso no tiene Atrás');
    assert.match(html, /data-rt-prize="1\/4 de ron"/, 'premio con ejemplos');
    if (type === 'score_pool') assert.match(html, /data-rt-w="team_a"[\s\S]*VS[\s\S]*data-rt-w="team_b"/);
    assert.equal(R.validateWhat(w)[0], 'Escribe el premio.');
    w.step = 2;
    html = R.view();
    assert.match(html, /En 1 hora[\s\S]*Hoy 8:00 p\. m\.[\s\S]*Mañana[\s\S]*Personalizado/);
    assert.match(html, /Horas de America\/Bogota · Jornada del bar:/);
    assert.match(html, /data-rt-back/);
    w.preset = 'custom';
    assert.match(R.view(), /type="datetime-local"/);
    w.step = 3;
    w.data.prize = 'Botella';
    html = R.view();
    assert.match(html, /class="rt-phone"[\s\S]*Así se verá en el QR de la mesa/);
    assert.match(html, /data-rt-publish/);
  }
});

test('concurso: tipos, hasta 5 opciones y respuesta correcta guardada en secreto', () => {
  const R = retos(ST());
  const w = R.newWizard('vote_poll');
  R.model.wizard = w;
  for (const mode of ['registration', 'yes_no', 'true_false', 'participants']) {
    w.data.vote_mode = mode;
    const html = R.view();
    assert.match(html, new RegExp(`value="${mode}" data-rt-mode checked`));
    assert.equal(/Respuesta correcta \(secreta/.test(html), mode === 'yes_no' || mode === 'true_false', mode);
    assert.equal(/data-rt-opt="0"/.test(html), mode === 'participants', mode);
  }
  w.data = { ...w.data, vote_mode: 'yes_no', prize: 'Shot', description: '¿Gana Colombia?', secret_answer: '' };
  assert.deepEqual([...R.validateWhat(w)], ['Marca la respuesta correcta.']);
  w.data.secret_answer = 'no';
  w.when = { ends_at: '2026-10-18T23:00' };
  const body = R.payloadOf(w);
  assert.equal(body.secret_answer, 'no');
  assert.equal(body.ends_at, '2026-10-19T04:00:00.000Z', 'la hora viaja en UTC desde la zona del bar');
  w.step = 3;
  const phone = R.view().split('class="rt-phone"')[1];
  assert.doesNotMatch(phone, /🔒/, 'la maqueta del QR no muestra la respuesta correcta');
  w.data = { ...w.data, vote_mode: 'participants', options: ['Ana', 'ana', ''] };
  assert.deepEqual([...R.validateWhat(w)], ['Las opciones no se pueden repetir.']);
  w.data.options = ['Ana', 'Beto', 'Caro', 'Dani', 'Eva'];
  w.step = 1;
  assert.doesNotMatch(R.view(), /data-rt-opt-add/, 'máximo 5');
});

test('en curso: etapa, cuenta regresiva, participantes, conteo y el botón de lo que falta', () => {
  const tie = { ...POOL, stage: 'result', deadline: null, actions: ['tiebreak', 'pick_winner'], result_status: 'tie', final_score: { score_a: 2, score_b: 1 },
    result: { matches: [{ table_key: 'mesa 1', table_number: 'Mesa 1', team_name: 'Los 1' }, { table_key: 'mesa 2', table_number: 'Mesa 2', team_name: 'Los 2' }] } };
  const cons = { id: 'c1', campaign_type: 'consumption', title: 'Reto', prize: 'Ron', status: 'active', stage: 'playing', deadline: '2026-10-19T05:00:00Z',
    deadline_label: 'El torneo cierra en', actions: ['close_now'], participants: 2, leaderboard: [{ rank: 1, team_name: 'Los 2', table_number: 'Mesa 2', orders_count: 2, total: 90000 }] };
  const vote = { id: 'v1', campaign_type: 'vote_poll', vote_mode: 'participants', title: 'Karaoke', prize: 'Shots', status: 'active', stage: 'registration', description: '¿Quién cantó mejor?',
    deadline: '2026-10-19T02:30:00Z', deadline_label: 'Votación cierra en', actions: ['close_now'], participants: 4, results: [{ key: 'option_1', label: 'Ana', count: 3, percent: 75 }] };
  const R = retos(ST({ active: { consumption: cons, score_pool: tie, vote_poll: vote } }));
  let html = R.view();
  assert.match(html, /<li class="is-done" >Inscripción<\/li><li class="is-done" >En juego<\/li><li class="is-on" aria-current="step">Resultado<\/li>/);
  assert.match(html, /data-rt-count="2026-10-19T05:00:00Z">3:00:00</, 'cuenta regresiva');
  assert.match(html, /Participantes<\/span><b>4</);
  assert.match(html, /Marcador final: <b>Colombia 2 - 1 Argentina<\/b>[\s\S]*Empate: 2 mesas acertaron el marcador exacto\./);
  assert.match(html, /Desempatar con Juego en vivo/);
  assert.match(html, /O elige el ganador/);
  assert.match(html, /Cerrar votación/);
  assert.match(html, /\$\s?90\.000/);
  R.model.confirm = 'p1:tiebreak';
  html = R.view();
  assert.match(html, /¿Seguro\?[\s\S]*data-rt-do="tiebreak" data-rt-id="p1"/, 'confirmación en la tarjeta, sin ventanas del navegador');
  assert.doesNotMatch(SRC, /\bconfirm\(|\balert\(|\bprompt\(/);
  // Desempate abierto: lleva a Juegos en vivo y no deja elegir a mano.
  R.model.st.active.score_pool = { ...tie, tiebreak: { round_id: 'g1', kind: 'trivia', status: 'registration', players: 1 } };
  html = R.view();
  assert.match(html, /Desempate en Juegos en vivo: Trivia Máquina del tiempo · Registro abierto · 1 inscrito\(s\)[\s\S]*Abrir Juegos en vivo/);
  assert.doesNotMatch(html, /O elige el ganador/);
  // Sin Juegos en vivo, el bar elige.
  R.model.st = ST({ games_on: false, active: { consumption: null, score_pool: tie, vote_poll: null } });
  html = R.view();
  assert.doesNotMatch(html, /Desempatar con Juego en vivo/);
  assert.match(html, /<legend>Elegir ganador<\/legend>[\s\S]*Los 1 \(Mesa 1\)[\s\S]*Los 2 \(Mesa 2\)/);
  // Polla con pronósticos cerrados: poner marcador final.
  R.model.st.active.score_pool = { ...POOL, stage: 'playing', deadline: null, actions: ['set_score'] };
  assert.match(R.view(), /data-rt-f="score_a"[\s\S]*data-rt-f="score_b"[\s\S]*Poner marcador final/);
  // Sí/No de antes (sin respuesta guardada): el bar la indica al cerrar.
  R.model.st.active.vote_poll = { ...vote, vote_mode: 'yes_no', secret_answer_key: '', results: [] };
  assert.match(R.view(), /¿Cuál era la respuesta correcta\?[\s\S]*Cerrar ahora/);
});

test('historial y premios: ganador, premio, fecha y validación (pendiente → entregado)', () => {
  const hist = [
    { id: 'h1', type: 'score_pool', title: 'Final', prize: 'Botella', team_a: 'A', team_b: 'B', result_status: 'winner', source: 'tiebreak', final_score: { score_a: 2, score_b: 1 },
      winner: { kind: 'table', table_number: 'Mesa 3', team_name: 'Los 3', player_name: 'Beto', source: 'tiebreak' }, prize_status: 'pending', closed_at: NOW },
    { id: 'h2', type: 'consumption', title: 'Reto', prize: 'Ron', result_status: 'winner', source: 'consumption', winner: { kind: 'table', table_number: 'Mesa 2', team_name: 'Los 2' },
      prize_status: 'delivered', prize_delivered_at: NOW, prize_delivered_by: 'barman@bar', closed_at: NOW },
    { id: 'h3', type: 'vote_poll', title: 'Viejo', prize: 'x', result_status: '', winner: null, prize_status: '', closed_at: NOW },
  ];
  const R = retos(ST({ history: hist }));
  let html = R.view();
  assert.match(html, /Premios por entregar[\s\S]*Beto · Los 3 \(Mesa 3\)[\s\S]*Documento del ganador[\s\S]*Validar y entregar/, 'el desempate valida con documento');
  R.model.tab = 'history';
  html = R.view();
  assert.match(html, /Desempate con Juego en vivo/);
  assert.match(html, /✓ Entregado[\s\S]*barman@bar/);
  assert.match(html, /Sin resultado registrado/, 'los retos de antes aparecen en el historial');
  assert.match(html, /aria-pressed="true"/);
});

test('textos por t(): todo tiene inglés y francés en el diccionario único', () => {
  const w = {};
  vm.runInContext(DICT, vm.createContext({ window: w, Object }));
  const D = w.CX_I18N_DICT;
  for (const b of SRC.matchAll(/const (?:TYPES|HOW|BUSY|MODES|MODE_HOW|ANSWERS|STAGES|GAMES|ROUND|SOURCES|OUTCOMES|ERRORS) = \{([\s\S]*?)\};/g)) {
    for (const m of b[1].matchAll(/:\s*"([^"]+)"/g)) seen.add(m[1]);
  }
  for (const src of [SRC, PLAY, SCREEN]) for (const m of src.matchAll(/T\("([^"]*)"/g)) seen.add(m[1]);
  // Etiquetas de la cuenta regresiva que manda el servidor (stage_of) y textos de los botones.
  const SERVICE = readFileSync('app/services/loyalty_retos.py', 'utf8');
  for (const m of SERVICE.matchAll(/"([^"]+ en)"/g)) seen.add(m[1]);
  for (const m of SRC.matchAll(/(?:confirmBtn\(r, "\w+", |field\()"([^"]+)"/g)) seen.add(m[1]);
  ['Elige tu mesa.', 'Esa mesa no está en el desempate.', 'Ya hay una persona de esa mesa en el desempate.'].forEach((k) => seen.add(k));
  const missing = [...seen].filter((k) => k && (!(k in D.en) || !(k in D.fr)));
  assert.deepEqual(missing, []);
  assert.equal(D.en['Retos para las mesas'], 'Table challenges');
});

test('estilos: tema del panel, sin desborde (minmax 0 y 375 px) y AA en los botones', () => {
  assert.match(CSS, /var\(--cx-text\)/);
  assert.match(CSS, /@media \(max-width: 720px\)/);
  assert.match(CSS, /\.rt-layout \{ display: grid; grid-template-columns: minmax\(0, 1\.05fr\) minmax\(0, \.95fr\)/);
  assert.match(CSS, /min-height: 44px/);
  assert.doesNotMatch(CSS, /white-space: nowrap/, 'ningún texto se corta');
});

test('client.js: la pantalla nueva solo con el interruptor; si no, Fidelización de siempre', () => {
  assert.match(CLIENT, /async function renderHospitalityLoyaltyModule024Z\(\) \{\n    if \(await cxLoyRetosOpen056A\(\)\) return;\n    cxHspLoyaltyStyles024Z\(\);/);
  assert.match(CLIENT, /fetch\(`\$\{API\}\/loyalty-retos\/companies\/\$\{encodeURIComponent\(companyId\)\}\/state`, \{ headers: authHeaders\(\) \}\)\n\s+\.then\(\(res\) => res\.ok \|\| res\.status === 403\)/);
  assert.match(CLIENT, /\/client-static\/loyalty_retos\.js\?v=056A/);
  assert.match(CLIENT, /\/client-static\/loyalty_retos\.css\?v=056A/);
  assert.match(CLIENT, /openGames: \(\) => cxLoyGamesOpen055B\("loyalty"\)/);
  assert.match(CLIENT, /<h1 class="client-title">Sorteos de consumo<\/h1>/, 'la pantalla vieja sigue igual');
  assert.match(SRC, /Authorization: `Bearer \$\{t\}`/, 'siempre con la sesión');
});

// ---------------------------------------------------------------- QR de la mesa
function qr(scoreCampaign, scorePrediction = null, table = 'Mesa 1') {
  const start = QR.indexOf('  /* CLONEXA_056A_RETOS_QR_START');
  const end = QR.indexOf('  /* CLONEXA_056A_RETOS_QR_END */');
  const src = `const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;");
    const voteModeLabel025O = (m) => m;
    const state = { table: ${JSON.stringify(table)} };
    ${QR.slice(start, end)}
    out.score = cxRetoScoreHtml056A(campaign, prediction);`;
  const out = {};
  vm.runInContext(src, vm.createContext({ out, campaign: scoreCampaign, prediction: scorePrediction, String, Number }));
  return out.score;
}

test('QR de la mesa: polla abierta, cerrada, empate y ganador', () => {
  const base = { id: 'p', title: 'Final', prize: 'Botella', team_a: 'Colombia', team_b: 'Argentina', rules_version: 2 };
  assert.equal(qr({ ...base, predictions_open: true, result_status: '' }), null, 'abierta: el formulario de siempre');
  assert.match(QR, /Pronósticos cierran en/);
  const mine = { id: 'x', table_key: 'mesa 1', score_a: 2, score_b: 1 };
  assert.match(qr({ ...base, predictions_open: false, result_status: '' }, mine), /Pronósticos cerrados[\s\S]*Tu pronóstico: 2 - 1/);
  const fin = { score_a: 2, score_b: 1 };
  assert.match(qr({ ...base, result_status: 'tie', final_score: fin, tied_tables: [{ table_key: 'mesa 1' }, { table_key: 'mesa 4' }] }, mine), /Empate: prepárate para el desempate/);
  assert.match(qr({ ...base, result_status: 'tie', final_score: fin, tied_tables: [{ table_key: 'mesa 2' }, { table_key: 'mesa 4' }] }, mine), /Marcador final: Colombia <b>2 - 1<\/b> Argentina[\s\S]*Hubo empate entre 2 mesas/);
  assert.match(qr({ ...base, result_status: 'winner', final_score: fin, winner: { table_key: 'mesa 1', table_number: 'Mesa 1' } }, mine), /¡Ganaste!/);
  assert.match(qr({ ...base, result_status: 'winner', final_score: fin, winner: { table_key: 'mesa 3', table_number: 'Mesa 3', team_name: 'Los 3', player_name: 'Beto' } }, mine), /Marcador final[\s\S]*Ganó Los 3 \(Beto\)/);
  assert.match(qr({ ...base, result_status: 'no_winner', final_score: fin }, null, 'Mesa_7'), /Nadie acertó el marcador exacto/);
  assert.equal(qr({ id: 'old', title: 'Polla vieja', team_a: 'A', team_b: 'B' }), null, 'las pollas de antes se ven igual');
  assert.doesNotMatch(QR, /secret_answer/, 'la respuesta correcta nunca llega al QR');
});

test('desempate en Juegos en vivo: el jugador elige su mesa (solo las empatadas) y la pantalla lo anuncia', () => {
  const window = {};
  vm.runInContext(PLAY, vm.createContext({ window, document: {}, location: { search: '?r=abc.def' }, URLSearchParams, JSON, Object, Array, String, Number, Math, Date, Map, Set, Promise, Error, Intl, encodeURIComponent }));
  const P = window.CxLoyaltyGamesPlay;
  P.st.info = { kind: 'memory', status: 'registration', texts: {}, brand: {}, tiebreak: { title: 'Desempate · Final', teams: 'Colombia vs Argentina', tables: [{ key: 'mesa 1', label: 'Mesa 1' }, { key: 'mesa 3', label: 'Mesa 3' }] } };
  P.st.me = null;
  const html = P.body();
  assert.match(html, /<select name="table" required><option value="">Elige tu mesa<\/option><option value="mesa 1" >Mesa 1<\/option><option value="mesa 3" >Mesa 3<\/option><\/select>/);
  assert.match(PLAY, /if \(st\.form\.table\) body\.table = st\.form\.table;/);
  P.st.info.tiebreak = null;
  assert.doesNotMatch(P.body(), /name="table"/, 'las rondas de siempre no piden mesa');
  assert.match(SCREEN, /Desempate de la polla \{teams\}/);
});
