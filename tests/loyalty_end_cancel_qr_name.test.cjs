// Terminar ahora / Cancelar y reiniciar en el panel de Juegos en vivo (diálogo en la
// página, jugador ve "Este juego fue cancelado") y nombre al entrar a la mesa por QR
// (qr_welcome_name): frase con [bar], nombre limpio de 30, chip "Laura · Mesa 4",
// el pedido ya no pide el nombre, cocina "Laura · Mesa 4", Reportes con invitados y
// búsqueda por nombre, Ajustes con la frase solo si el servidor responde 200, y con
// el interruptor apagado todo queda como hoy.
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { readFileSync } = require('node:fs');

const GAMES = readFileSync('app/web/loyalty_games.js', 'utf8');
const PLAY = readFileSync('app/web/loyalty_games_play.js', 'utf8');
const QR = readFileSync('app/web/hospitality_order.js', 'utf8').replace(/\r\n/g, '\n');
const KITCHEN = readFileSync('app/web/hsp_kitchen.js', 'utf8').replace(/\r\n/g, '\n');
const CLIENT = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');
const SETTINGS = readFileSync('app/web/client_core_settings.js', 'utf8').replace(/\r\n/g, '\n');
const DICT = readFileSync('app/web/client_i18n_dict.js', 'utf8');

function run(src, extra = {}) {
  const window = { ...extra };
  vm.runInContext(src, vm.createContext({ window, document: {}, location: { search: '?r=abc.def' }, URLSearchParams, JSON, Object, Array, String, Number, Math, Date, Map, Set, Promise, Error, Intl, encodeURIComponent }));
  return window;
}

// ---------------------------------------------------------------- Parte 1: Juegos en vivo
function gamesPanel(status) {
  const G = run(GAMES).CxLoyaltyGames;
  Object.assign(G.model, {
    ctx: { role: 'barman', can: {}, brand: {}, settings: { roulette_ranges: [{ min: 1, max: 50 }], prizes: {}, memory_pairs: 5, memory_times: { 5: 120 } }, pair_options: [5], scenes: [] },
    live: { now: '2026-10-17T03:00:00Z', active: true, round: { id: 'r1', kind: 'memory', status, prize: 'Botella', players: [], all_players: [], ranking: [], podium: [] } },
    tab: 'live', denied: '',
  });
  return G;
}

test('Juegos en vivo: "Terminar ahora" y "Cancelar y reiniciar" con diálogo en la página', () => {
  let G = gamesPanel('playing');
  let html = G.view();
  assert.match(html, /data-lg-ask="close" data-lg-round="r1"[^>]*>■ Terminar ahora/);
  assert.match(html, /data-lg-ask="cancel" data-lg-round="r1"[^>]*>↺ Cancelar y reiniciar/);
  G = gamesPanel('registration');
  html = G.view();
  assert.match(html, /data-lg-start="r1"[\s\S]*data-lg-ask="cancel"/, 'en registro: iniciar o cancelar');
  assert.doesNotMatch(html, /Cancelar registro|Cerrar ronda/);
  G.model.confirm = { action: 'cancel', id: 'r1' };
  html = G.view();
  assert.match(html, /role="dialog" aria-modal="true"[\s\S]*Cancelar y reiniciar[\s\S]*Se anula sin ganador[\s\S]*data-lg-confirm[\s\S]*Sí, cancelar[\s\S]*data-lg-unconfirm/);
  G.model.confirm = { action: 'close', id: 'r1' };
  assert.match(G.view(), /Se cierra con el ranking actual y la pantalla del bar muestra el podio\.[\s\S]*Sí, terminar/);
  assert.match(GAMES, /call\(`\/rounds\/\$\{c\.id\}\/\$\{c\.action === "cancel" \? "cancel" : "close"\}`, "POST"\)/);
  assert.doesNotMatch(GAMES, /\bconfirm\(|\balert\(|\bprompt\(/, 'sin ventanas del navegador');
  G = gamesPanel('closed');
  assert.doesNotMatch(G.view(), /data-lg-ask=/, 'una ronda cerrada ya no se termina ni se cancela');
});

test('jugador: "Este juego fue cancelado" (inscrito o no)', () => {
  const P = run(PLAY).CxLoyaltyGamesPlay;
  P.st.info = { kind: 'memory', status: 'cancelled', texts: {}, brand: {} };
  P.st.me = null;
  assert.match(P.body(), /Este juego fue cancelado/);
  P.st.me = { status: 'cancelled', kind: 'memory' };
  assert.match(P.body(), /Este juego fue cancelado/);
});

// ---------------------------------------------------------------- Parte 3: bienvenida en el QR
function welcome(ui, extra = {}) {
  const start = QR.indexOf('  /* CLONEXA_056B_QR_WELCOME_START');
  const end = QR.indexOf('  /* CLONEXA_056B_QR_WELCOME_END */');
  const src = `const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    const isAssemblyMode = () => false;
    const barMyName = () => ${JSON.stringify(extra.myName || '')};
    const barTableTitle = () => "Mesa 4";
    const customerStorageKey = () => "k";
    const brand = () => ({ logo: "" });
    const state = { ui: ${JSON.stringify(ui)}, customerName: ${JSON.stringify(extra.name || '')}, access: { unlocked: true }, company: { name: "The Time Machine" } };
    const document = { addEventListener() {}, getElementById() { return null; } };
    const window = { localStorage: { getItem: (k) => ${JSON.stringify(extra.skip ? '1' : null)}, setItem() {} } };
    ${QR.slice(start, end)}
    out.api = { welcomeOn056B, welcomePhrase056B, welcomeCleanName056B, welcomeLabel056B, welcomeChip056B, welcomeNameKnown056B, welcomeAsYouHtml056B, welcomeNamed056C, welcomeBarTop056C, state };`;
  const out = {};
  vm.runInContext(src, vm.createContext({ out, String, Number, JSON, Element: function () {} }));
  return out.api;
}

const UI = { bar_menu: true, welcome_name: true, welcome_text: '¡Bienvenido a [bar]! 🎶 Qué bueno tenerte esta noche. ¿Cómo te llamas?', welcome_custom: false, language: 'es', name_max: 30 };

test('bienvenida: frase con [bar], nombre opcional sin HTML y de 30, "Laura · Mesa 4"', () => {
  const W = welcome(UI);
  assert.equal(W.welcomeOn056B(), true);
  assert.equal(W.welcomePhrase056B(), '¡Bienvenido a The Time Machine! 🎶 Qué bueno tenerte esta noche. ¿Cómo te llamas?');
  assert.equal(W.welcomeCleanName056B('  <b>Laura</b>   <script>x</script>María de los Ángeles Restrepo Vélez '), 'Laura x María de los Ángeles R');
  assert.equal(W.welcomeCleanName056B('<<>>'), '');
  assert.equal(W.welcomeNameKnown056B(), false, 'sin nombre: se pide al activar');
  assert.match(W.welcomeChip056B(), /👤 Invitado · Mesa 4[\s\S]*Agregar mi nombre/);
  const named = welcome(UI, { name: 'Laura' });
  assert.equal(named.welcomeLabel056B(), 'Laura · Mesa 4');
  assert.equal(named.welcomeNameKnown056B(), true, 'con nombre ya no se pide al pedir');
  assert.match(named.welcomeAsYouHtml056B(), /Pides como[\s\S]*Laura · Mesa 4/);
  assert.doesNotMatch(named.welcomeAsYouHtml056B() + named.welcomeChip056B(), /Cambiar nombre|data-welcome-open/, 'nombre fijo: no se cambia desde el QR');
  const skipped = welcome(UI, { skip: true, myName: 'Persona 2' });
  assert.equal(skipped.welcomeNameKnown056B(), true, '"Ahora no": tampoco se vuelve a pedir');
  assert.equal(skipped.welcomeLabel056B(), 'Persona 2 · Mesa 4', 'queda con el nombre por defecto');
  const custom = welcome({ ...UI, welcome_text: 'Hola [bar], ¿quién eres?', welcome_custom: true });
  assert.equal(custom.welcomePhrase056B(), 'Hola The Time Machine, ¿quién eres?');
  const off = welcome({ bar_menu: true });
  assert.equal(off.welcomeOn056B(), false);
  assert.equal(off.welcomeChip056B(), '', 'sin el interruptor no aparece nada');
  assert.equal(off.welcomeNameKnown056B(), false, 'sin el interruptor el pedido pide el nombre como siempre');
});

test('QR: la bienvenida se engancha solo con ui.welcome_name y el pedido deja de pedir el nombre', () => {
  assert.match(QR, /state\.ui = \{ bar_menu: access\.ui\?\.bar_menu === true \};\n      if \(access\.ui\?\.welcome_name === true\) \{/);
  assert.match(QR, /if \(welcomeOn056B\(\)\) setTimeout\(\(\) => \{ showWelcome056B\(\)\.catch\(\(\) => \{\}\); \}, 0\);/, 'apenas se activa la mesa');
  assert.equal((QR.match(/\$\{welcomeNameKnown056B\(\) \? welcomeAsYouHtml056B\(\) : `<label class="qr-field">/g) || []).length, 2, 'carta de bar y QR clásico');
  assert.match(QR, /state\.namePending056C = name;  \/\/ se manda UNA vez; despues el nombre queda fijo\n    try \{\n      await refreshTableAccount\(\);/, 'el nombre va a la sesión del invitado una sola vez');
  assert.match(QR, /value="\$\{h\(document\.getElementById\("qrTeam024Z"\)\?\.value \|\| \(welcomeOn056B\(\) \? state\.customerName : ""\) \|\| ""\)\}"/, 'retos con el nombre ya escrito');
  assert.match(welcome(UI, { name: '<img src=x>' }).welcomeChip056B(), /&lt;img src=x&gt; · Mesa 4/, 'el nombre siempre escapado');
});

test('Parte 2: lista de pronósticos sin encimarse ("…") y "Polla activa" con el color de marca legible', () => {
  assert.match(QR, /\.qr-rank-row\{display:grid;grid-template-columns:auto minmax\(0,1fr\)/);
  assert.match(QR, /\.qr-rank-row > span\{[^}]*text-overflow:ellipsis/);
  assert.match(QR, /\.qr-rank-row strong\{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis\}/);
  assert.match(QR, /\.qr-eyebrow\{margin:0 0 6px;color:var\(--qr-eyebrow\)/);
  const start = QR.indexOf('  function qrHexRgb');
  const end = QR.indexOf('  function injectStyles');
  const out = {};
  vm.runInContext(`${QR.slice(start, end)}; out.f = qrReadableAccent; out.lum = qrLum; out.rgb = qrHexRgb;`, vm.createContext({ out, Math, String, parseInt }));
  for (const [primary, bg] of [['#6b5d00', '#14110a'], ['#ff8a1c', '#ffffff'], ['#000000', '#000000'], ['#ffffff', '#ffffff'], ['bad', '']]) {
    const color = out.f(primary, bg);
    const m = color.match(/\d+/g).map(Number);
    const rgb = color === '#ffffff' ? [255, 255, 255] : m;
    const b = out.rgb(bg) || [18, 0, 34];
    const card = b.map((c, i) => 0.88 * (0.72 * [15, 23, 42][i] + 0.28 * c) + 0.12 * 255);
    const a = out.lum(rgb) + 0.05; const c2 = out.lum(card) + 0.05;
    assert.ok(Math.max(a, c2) / Math.min(a, c2) >= 4.5, `${primary} sobre ${bg}: ${color}`);
  }
  assert.equal(out.f('#ffd166', '#120022'), 'rgb(255,209,102)', 'si la marca ya se lee, queda tal cual');
});

test('cocina "Laura · Mesa 4", Reportes con invitados y búsqueda, Ajustes solo con 200', () => {
  assert.match(KITCHEN, /return comanda\.guest_name \? `\$\{comanda\.guest_name\} · \$\{table\}` : table;/);
  assert.equal((KITCHEN.match(/\$\{h\(tableLabel\(comanda\)\)\}/g) || []).length, 3);
  assert.match(CLIENT, /cxHspDashGuestSearch056B = data\.event_search\.guest_search === true;/);
  assert.match(CLIENT, /\$\{cxHspDashGuestSearch056B \? `<label>Nombre del invitado<input type="search"/);
  assert.match(CLIENT, /\(cxHspDashGuestSearch056B \? cxHspDashEventListHtml056B\(\) : cxHspDashEvents033B\.map\(cxHspDashEventCard033B\)\.join\(""\)\)/, 'sin el interruptor, la lista de siempre');
  const start = CLIENT.indexOf('  function cxHspGuestNorm056B');
  const end = CLIENT.indexOf('  function cxHspDashEventListHtml056B');
  const out = {};
  vm.runInContext(`let cxHspDashEvents033B = ${JSON.stringify([{ id: 'a', location: 'Mesa 4', guest_names: ['Laura', 'Persona 2'] }, { id: 'b', location: 'Mesa 7', guest_names: ['Andrés'] }, { id: 'c', type: 'bar', customer_name: 'Juan' }])};
    let cxHspDashGuestSearch056B = true; let cxHspDashGuestFilter056B = "";
    ${CLIENT.slice(start, end)}
    out.labels = cxHspGuestLabels056B; out.find = (q) => { cxHspDashGuestFilter056B = q; return cxHspDashVisibleEvents056B().map((e) => e.id); };`, vm.createContext({ out, String, Array }));
  assert.deepEqual([...out.labels({ location: 'Mesa 4', guest_names: ['Laura'] })], ['Laura · Mesa 4']);
  assert.deepEqual([...out.find('laura')], ['a']);
  assert.deepEqual([...out.find('andres')], ['b'], 'sin tildes');
  assert.deepEqual([...out.find('JUAN')], ['c']);
  assert.deepEqual([...out.find('')], ['a', 'b', 'c']);
  assert.match(SETTINGS, /data = await api\(`\/hospitality\/companies\/\$\{encodeURIComponent\(id\)\}\/qr-welcome`\);\n    \} catch \(_\) \{\n      return;\n    \}/, 'sin el interruptor (404) no aparece');
  assert.match(SETTINGS, /maxlength="\$\{Number\(data\.max \|\| 160\)\}"/);
});

test('textos por t(): inglés y francés', () => {
  const w = {};
  vm.runInContext(DICT, vm.createContext({ window: w, Object }));
  const D = w.CX_I18N_DICT;
  const keys = new Set();
  const block = QR.slice(QR.indexOf('CLONEXA_056B_QR_WELCOME_START'), QR.indexOf('CLONEXA_056B_QR_WELCOME_END'));
  for (const m of block.matchAll(/wt056B\("([^"]+)"/g)) keys.add(m[1]);
  for (const m of SETTINGS.matchAll(/wt056B\("([^"]+)"/g)) keys.add(m[1]);
  for (const m of GAMES.matchAll(/^\s+(?:close|cancel): \[("[^\]]+)\],?$/gm)) for (const s of m[1].matchAll(/"([^"]+)"/g)) keys.add(s[1]);
  ['La mesa sigue abierta. Puedes continuar ordenando; este acceso se cerrará cuando el bar cierre la mesa.', '¡Bienvenido a [bar]! 🎶 Qué bueno tenerte esta noche. ¿Cómo te llamas?', 'Este juego fue cancelado', 'Juego cancelado: la pantalla del bar quedó en espera.',
    'Juego terminado: la pantalla muestra el podio.', 'La ronda ya terminó.'].forEach((k) => keys.add(k));
  assert.ok(keys.size > 20);
  assert.deepEqual([...keys].filter((k) => !(k in D.en) || !(k in D.fr)), []);
  assert.equal(D.en['Ahora no'], 'Not now');
});
