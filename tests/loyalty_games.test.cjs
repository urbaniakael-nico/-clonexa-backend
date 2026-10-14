// Juegos en vivo (interruptor loyalty_games): ruleta que cae en el número
// guardado, flechas del ranking, panel (barman vs dueño), página del jugador,
// textos por t() en es/en/fr y el enganche de client.js.
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { readFileSync } = require('node:fs');

const PANEL = readFileSync('app/web/loyalty_games.js', 'utf8');
const SCREEN = readFileSync('app/web/loyalty_games_screen.js', 'utf8');
const PLAY = readFileSync('app/web/loyalty_games_play.js', 'utf8');
const CLIENT = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');
const DICT = readFileSync('app/web/client_i18n_dict.js', 'utf8');

function run(src, extra = {}) {
  const window = { ...extra };
  vm.runInContext(src, vm.createContext({ window, document: {}, location: { search: '?r=abc.def' }, URLSearchParams, JSON, Object, Array, String, Number, Math, Date, Map, Set, Promise, Error, Intl, encodeURIComponent }));
  return window;
}

test('ruleta: la animación siempre cae en el número que guardó el servidor', () => {
  const S = run(SCREEN).CxLoyaltyGamesScreen;
  for (const [min, max] of [[1, 50], [1, 100], [0, 9], [100, 999]]) {
    for (let target = min; target <= max; target += Math.max(1, Math.floor((max - min) / 17))) {
      const end = S.rouletteFrame(1, min, max, target);
      assert.equal(end.number, target);
      assert.equal(S.numberAt(end.angle, min, max), target, `${min}-${max}: el número bajo la flecha es ${target}`);
      assert.ok(end.angle >= 360 * 6, 'da varias vueltas');
    }
  }
  const mid = S.rouletteFrame(0.5, 1, 50, 37);
  assert.ok(mid.number >= 1 && mid.number <= 50);
  assert.ok(S.ease(0) === 0 && S.ease(1) === 1 && S.ease(0.5) > 0.5, 'frena al final');
});

test('ranking: ▲ al subir, ▼ al bajar; escenas por ronda y estado', () => {
  const S = run(SCREEN).CxLoyaltyGamesScreen;
  const marks = S.arrows({ a: 1, b: 2, c: 3 }, [{ id: 'b', rank: 1 }, { id: 'a', rank: 2 }, { id: 'c', rank: 3 }, { id: 'd', rank: 4 }]);
  assert.deepEqual({ ...marks }, { b: 'up', a: 'down', c: '', d: '' });
  assert.equal(S.sceneKey({ focus: 'roulette', roulette: { id: 'x' } }), 'roulette:x');
  assert.equal(S.sceneKey({ focus: 'round', round: { id: 'r', status: 'playing' } }), 'round:r:playing');
  assert.equal(S.sceneKey({ focus: 'idle' }), 'idle');
});

const CTX = (role) => ({
  role, can: { configure: role === 'admin', launch: true, validate: true }, brand: { name: 'TTM', logo_url: '/brand-media/a/b.webp', timezone: 'America/Bogota' },
  settings: { memory_seconds: 120, trivia_seconds: 180, roulette_ranges: [{ min: 1, max: 50, prize: 'Shot' }], prizes: { memory: 'Botella', trivia: '', roulette: '' }, texts: { claim: 'Reclama con tu documento', consent: 'Autorizo' } },
  screen_url: role === 'admin' ? 'https://x/juegos/pantalla?t=SECRET' : undefined,
});
const LIVE = {
  now: '2026-10-17T03:00:00Z', active: false, roulette: { range_min: 1, range_max: 50, drawn: [7, 21] },
  round: { id: 'r1', kind: 'memory', status: 'closed', prize: 'Botella', ranking: [{ id: 'p1', name: 'Camila', rank: 1, score: 5 }], podium: [{ place: 1, id: 'p1', name: 'Camila' }],
    all_players: [{ id: 'p1', name: 'Camila', hidden: false, validated: true }, { id: 'p2', name: 'Grosería', hidden: true }] },
};

function panel(role) {
  const G = run(PANEL).CxLoyaltyGames;
  Object.assign(G.model, { ctx: CTX(role), live: LIVE, tab: 'live', denied: '' });
  return G;
}

test('panel: el barman lanza y valida, pero no ve Configuración, Preguntas ni el enlace de la pantalla', () => {
  const html = panel('barman').view();
  for (const t of ['Ruleta de la rifa', 'Girar', 'Abrir registro', 'Validar ganador', 'Quitar de la pantalla', 'Sacados esta noche (1–50): 7, 21', '1.er puesto: <b>Camila</b>']) assert.ok(html.includes(t), t);
  assert.doesNotMatch(html, /data-lg-tab="(config|questions|history)"/);
  assert.doesNotMatch(html, /SECRET/);
  const admin = panel('admin').view();
  assert.match(admin, /data-lg-tab="config"[\s\S]*data-lg-tab="questions"[\s\S]*data-lg-tab="history"/);
  assert.match(admin, /value="https:\/\/x\/juegos\/pantalla\?t=SECRET"/);
  assert.match(admin, /data-lg-regenerate/);
});

test('validación: muestra "✓ Coincide: Camila · 1.er puesto" o "✗ No coincide", nunca el documento', () => {
  const G = panel('barman');
  G.model.validation = { match: true, name: 'Camila', place: 1 };
  assert.match(G.view(), /✓ Coincide: Camila · 1\.er puesto/);
  G.model.validation = { match: false, name: null, place: 2 };
  assert.match(G.view(), /✗ No coincide/);
  G.model.form.doc = '';
  assert.match(G.view(), /data-lg-doc inputmode="numeric" autocomplete="off" maxlength="20" value=""/, 'el documento no se queda en pantalla');
});

test('jugador: inscripción con casilla obligatoria (Ley 1581) y resultados', () => {
  const W = run(PLAY);
  const P = W.CxLoyaltyGamesPlay;
  P.st.info = { kind: 'trivia', status: 'registration', prize: 'Ronda', texts: { consent: 'Autorizo el tratamiento de mis datos para este concurso' }, brand: {} };
  let html = P.body();
  assert.match(html, /name="name" maxlength="20"/);
  assert.match(html, /type="checkbox" name="consent"\s+required/);
  assert.match(html, /Autorizo el tratamiento de mis datos para este concurso \(Ley 1581\)/);
  P.st.me = { status: 'closed', name: 'Ana', result: { result: 'lost', place: null } };
  assert.match(P.body(), /Se acabó el tiempo, perdiste/);
  P.st.me.result = { result: 'ranked', place: 1 };
  P.st.info.texts.claim = 'Reclama con tu documento';
  assert.match(P.body(), /¡Quedaste en el puesto 1![\s\S]*Reclama con tu documento/);
  P.st.info.kind = 'memory';
  P.st.me = { status: 'playing', name: 'Ana', ends_at: '2026-10-17T03:02:00Z', memory: { size: 10, faces: { 3: '🎸' }, matched: [], open: 3, pairs: 0, total_pairs: 5 } };
  html = P.body();
  assert.equal((html.match(/data-lgx-flip=/g) || []).length, 10);
  assert.equal((html.match(/is-up/g) || []).length, 1, 'solo la carta volteada muestra su cara');
  assert.ok(P.ERRORS.documento_ya_juega);
});

test('textos por t(): todo tiene inglés y francés en el diccionario único', () => {
  const w = {};
  vm.runInContext(DICT, vm.createContext({ window: w, Object }));
  const D = w.CX_I18N_DICT;
  const keys = new Set();
  for (const src of [PANEL, SCREEN, PLAY]) {
    for (const m of src.matchAll(/T\("([^"]*)"/g)) keys.add(m[1]);
    for (const b of src.matchAll(/const (?:KIND|STATUS|ERRORS) = \{([\s\S]*?)\};/g)) for (const m of b[1].matchAll(/:\s*"([^"]+)"/g)) keys.add(m[1]);
  }
  ['1.er puesto', '2.º puesto', '3.er puesto', 'Reclama con tu documento', 'Autorizo el tratamiento de mis datos para este concurso'].forEach((k) => keys.add(k));
  assert.deepEqual([...keys].filter((k) => !(k in D.en) || !(k in D.fr)), []);
  assert.equal(D.en['Se acabó el tiempo, perdiste'], "Time's up, you lost");
});

test('client.js: el botón solo aparece si el servidor dice que el interruptor está encendido', () => {
  assert.match(CLIENT, /`;\n    cxLoyGamesDecorate055B\("orders"\);\n\n    cxHspRenderOrdersBoard024R\(summary\);/);
  assert.match(CLIENT, /`;\n    cxLoyGamesDecorate055B\("loyalty"\);\n    cxHspLoyaltyPaint024Z\(\);/);
  assert.match(CLIENT, /fetch\(`\$\{API\}\/loyalty-games\/companies\/\$\{encodeURIComponent\(companyId\)\}\/context`, \{ headers: authHeaders\(\) \}\)\n\s+\.then\(\(res\) => res\.ok\)/);
  assert.match(CLIENT, /\/client-static\/loyalty_games\.js\?v=055B/);
  assert.match(PANEL, /Authorization: `Bearer \$\{t\}`/, 'el panel siempre con la sesión');
  assert.match(SCREEN, /prefers-reduced-motion: reduce/);
});

test('v2 celular: cuadrícula por cantidad de cartas, trivia de 10 con reemplazo y 7 diferencias sin zonas ocultas', () => {
  const P = run(PLAY).CxLoyaltyGamesPlay;
  const g = (n) => ({ ...P.gridOf(n) });
  assert.deepEqual([g(10), g(14), g(20), g(26), g(30)], [{ cols: 4, rows: 3 }, { cols: 4, rows: 4 }, { cols: 4, rows: 5 }, { cols: 5, rows: 6 }, { cols: 5, rows: 6 }]);
  P.st.info = { kind: 'memory', status: 'playing', texts: {}, brand: {} };
  P.st.me = { status: 'playing', kind: 'memory', ends_at: '2026-10-17T03:05:00Z', memory: { size: 30, faces: { 4: '🎻' }, matched: [], open: 4, pairs: 0, total_pairs: 15 } };
  let html = P.body();
  assert.equal((html.match(/data-lgx-flip=/g) || []).length, 30);
  assert.match(html, /--cols:5;--rows:6/);
  P.st.info.kind = 'trivia';
  P.st.me = { status: 'playing', kind: 'trivia', rules: 2 };
  P.st.question = { done: false, v: 2, replaced: true, lap: 2, correct: 6, goal: 10, question: { id: 'q', text: '¿?', options: ['a', 'b', 'c'], remaining_ms: 9000 } };
  assert.match(P.body(), /Correctas 6 de 10 · vuelta 2[\s\S]*Pregunta nueva: reemplaza una que fallaste/);
  P.st.me = { status: 'closed', kind: 'trivia', rules: 2, result: { result: 'ranked', place: 2, score: 8, finished: false } };
  assert.match(P.body(), /Se acabó el tiempo[\s\S]*Lograste 8 de 10 correctas[\s\S]*¡Quedaste en el puesto 2!/);
  P.st.info.kind = 'differences';
  P.st.me = { status: 'playing', kind: 'differences', differences: { total: 7, found: 2, penalty_ms: 10000, zones: [{ id: 'z', x: 0.5, y: 0.5, r: 0.05 }] } };
  html = P.body();
  assert.match(html, /\/image\/a\.png[\s\S]*\/image\/b\.png/);
  assert.match(html, /2\/7[\s\S]*\+10 s/);
  assert.doesNotMatch(PLAY, /zones\s*=\s*\[\s*\{[^}]*cx/, 'el celular nunca tiene la lista de zonas ocultas');
  assert.match(PLAY, /call\("\/tap", "POST", \{ x, y \}\)/, 'solo manda la coordenada normalizada');
});

test('v2 pantalla: miniaturas en juego y revelado de las 7 después del podio', () => {
  const S = run(SCREEN).CxLoyaltyGamesScreen;
  assert.ok(S);
  assert.match(SCREEN, /REVEAL_AFTER_MS = 8000/);
  assert.match(SCREEN, /r\.kind === "differences" \? `\/ \$\{r\.goal \|\| 7\}`/, 'ranking x/7');
  assert.match(SCREEN, /class="lgx-thumbs"/);
});
