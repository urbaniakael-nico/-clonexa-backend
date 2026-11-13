// Consola v2+ · Ventas · Nexa → Cola de hoy: tarjetas con el texto armado, botones grandes (Seguir y dar like,
// Guardar video, Copiar, Abrir perfil, Enviado, ⋯ Saltar / No contactar), pestañas, contador del menú, 401.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const SRC = readFileSync('app/web/admin_v2plus_cola.js', 'utf8');
const HTML = readFileSync('app/web/admin_v2plus.html', 'utf8');
const SHELL = readFileSync('app/web/admin_v2plus.js', 'utf8');
const ROUTES = readFileSync('app/web/admin_v2plus_routes.py', 'utf8');
const CSS = readFileSync('app/web/admin_v2plus.css', 'utf8');

const ITEM = (id, over = {}) => ({ id, kind: 'inicial', status: 'pendiente', network: 'instagram', name: `Always <Pub> ${id}`, nicho: 'Bares', niche: 'bar', zona: 'Techo',
  text: '¡Qué más, Always Pub! 🍻\nSomos CLONEXA 🚀\n\n👉 clonexa.com.co/b/SXFB3W\nSi no quieren más mensajes, respondan NO.',
  profile_url: 'https://www.instagram.com/alwayspub/', app_url: 'instagram://user?username=alwayspub', liked: false, video: '/admin-v2plus/bumeranes/bar.mp4',
  sent_at: null, replied: false, no_contactar: false, ...over });
const DATA = () => ({ ok: true, fecha: '2026-11-13', fecha_label: 'Jueves 13 nov', limite: 15, total: 6, enviados: 3, por_enviar: 3, motivo: '', horario: true,
  pendientes: [ITEM(1), ITEM(2, { network: 'facebook', profile_url: 'https://www.facebook.com/excalibur', app_url: 'fb://facewebmodal/f?href=https%3A%2F%2Fwww.facebook.com%2Fexcalibur', niche: 'tienda', video: '' })],
  seguimientos: [ITEM(3, { kind: 'seguimiento', text: '¡Hola de nuevo, Rubí! 👋', nicho: 'Talleres y fábricas' })],
  archivados: [ITEM(4, { status: 'enviado', sent_at: '2026-11-13T14:12:00Z' }), ITEM(5, { status: 'saltado' }), ITEM(6, { status: 'cancelado', no_contactar: true }),
    ITEM(7, { status: 'enviado', sent_at: '2026-11-13T15:00:00Z', replied: true })] });

function load(responder) {
  const calls = [];
  const badges = [{ textContent: '', hidden: true }];
  const root = { innerHTML: '' };
  const listeners = {};
  const fetch = async (url, options = {}) => {
    calls.push(`${options.method || 'GET'} ${url}${options.body ? ` ${options.body}` : ''}`);
    const { status, body } = responder(url, options);
    return { status, ok: status >= 200 && status < 300, json: async () => body };
  };
  const window = { location: { href: '' }, setInterval() {}, open() {} };
  const document = { querySelectorAll: (s) => (s === '[data-cola-badge]' ? badges : []), addEventListener: (t, f) => { listeners[t] = f; }, visibilityState: 'visible' };
  const ctx = vm.createContext({ window, document, fetch, JSON, Object, Array, String, Number, Math, Promise, Error, Date, URLSearchParams, encodeURIComponent,
    setTimeout: (f) => f(), navigator: { userAgent: 'Desktop', clipboard: { writeText: async () => {} } } });
  vm.runInContext(SRC, ctx);
  const C = window.CxConsoleCola;
  window.CxConsoleSections.cola.mount({ root: () => root, active: () => true });
  return { C, calls, badges, root, listeners, window };
}
const flush = () => new Promise((r) => setImmediate(r));

test('menú: "Cola de hoy" con contador, debajo de Conversaciones Nexa (no dentro de Radar); #cola abre la vista', () => {
  assert.match(HTML, /data-vp-view="nexa">Conversaciones Nexa<\/button>\r?\n\s*<button class="vp-nav-item vp-nav-cola" type="button" data-vp-view="cola">📋 Cola de hoy <span class="vp-nav-badge" data-cola-badge hidden><\/span><\/button>\r?\n\s*<button class="vp-nav-item" type="button" data-vp-view="radar">/);
  assert.match(HTML, /<script src="\/admin-v2plus-cola\.js"><\/script>/);
  assert.match(SHELL, /cola: "Cola de hoy"/);
  assert.match(SHELL, /"#cola"\) \{ setView\("cola"\)/);
  assert.match(ROUTES, /admin-v2plus-cola\.js[\s\S]{0,400}_require_session_json/);
});

test('contador del menú: pendientes del día (se oculta en 0)', async () => {
  const { C, badges } = load((url) => (url.endsWith('/pendientes') ? { status: 200, body: { pendientes: 12 } } : { status: 200, body: DATA() }));
  await flush(); await flush();
  await C.refreshBadge();
  assert.equal(badges[0].textContent, '12');
  assert.equal(badges[0].hidden, false);
  C.setBadge(0);
  assert.equal(badges[0].hidden, true);
});

test('encabezado, pestañas y tarjeta con el texto armado y los 6 botones; todo escapado', async () => {
  const { C, root } = load(() => ({ status: 200, body: DATA() }));
  await flush(); await flush();
  const html = root.innerHTML;
  assert.match(html, /VENTAS · NEXA[\s\S]*Cola de hoy/);
  assert.match(html, /<b>Jueves 13 nov<\/b><b data-cola-count>3 de 15 enviados<\/b>/);
  assert.match(html, /<progress class="vp-cola-bar" max="15" value="3"/);
  assert.match(html, /data-cola-tab="pendientes">Pendientes <span>2<\/span>/);
  assert.match(html, /data-cola-tab="seguimientos">Seguimientos <span>1<\/span>/);
  assert.match(html, /data-cola-tab="archivados">Archivados <span>4<\/span>/);
  assert.match(html, /aria-label="Instagram">IG</);
  assert.match(html, /aria-label="Facebook">f</);
  assert.match(html, /<h2>Always &lt;Pub&gt; 1<\/h2>/);
  assert.doesNotMatch(html, /<Pub>/);
  assert.match(html, /Bares · Techo/);
  assert.match(html, /<pre class="vp-cola-text"[^>]*>¡Qué más, Always Pub! 🍻\nSomos CLONEXA/);
  for (const t of ['👍 Seguir y dar like', '📥 Guardar video', '📋 Copiar', '📲 Abrir perfil', '✅ Enviado', 'aria-label="Más opciones">⋯']) assert.ok(html.includes(t), t);
  assert.match(html, /href="\/admin-v2plus\/bumeranes\/bar\.mp4" download/);
  assert.match(html, /data-cola-open="instagram:\/\/user\?username=alwayspub"/);
  assert.match(html, /data-cola-open="fb:\/\/facewebmodal\/f\?href=https%3A%2F%2Fwww\.facebook\.com%2Fexcalibur"/);
  // tienda sin bumerán: sin "Guardar video" en esa tarjeta
  const card2 = html.split('data-cola-card="2"')[1].split('</article>')[0];
  assert.doesNotMatch(card2, /Guardar video/);
  assert.doesNotMatch(html, /\sstyle=|\son[a-z]+=/, 'sin estilos ni manejadores en línea (CSP)');
  C.model.tab = 'seguimientos';
  C.load && null;
});

test('seguimientos y archivados: texto de seguimiento, "Respondió" solo en enviados', async () => {
  const { C, root, listeners } = load(() => ({ status: 200, body: DATA() }));
  await flush(); await flush();
  await listeners.click({ target: { closest: (s) => (s === '[data-cola-tab]' ? { getAttribute: () => 'seguimientos' } : null) } });
  assert.match(root.innerHTML, /Talleres y fábricas · Techo · <b class="vp-cola-follow">Seguimiento<\/b>/);
  assert.match(root.innerHTML, /¡Hola de nuevo, Rubí! 👋/);
  await listeners.click({ target: { closest: (s) => (s === '[data-cola-tab]' ? { getAttribute: () => 'archivados' } : null) } });
  const html = root.innerHTML;
  assert.match(html, /✓ <b>Always &lt;Pub&gt; 4<\/b> · enviado [^<]+<\/span>\s*<button class="vp-btn vp-btn-sm" type="button" data-cola-act="respondio" data-cola-id="4">💬 Respondió<\/button>/);
  assert.match(html, /Always &lt;Pub&gt; 5<\/b> · saltado · vuelve mañana/);
  assert.match(html, /Always &lt;Pub&gt; 6<\/b> · no contactar/);
  assert.match(html, /data-cola-card="7"[\s\S]*?<span class="vp-cola-replied">💬 Respondió<\/span>/);
});

test('✅ Enviado: registra en el servidor, animación corta y la lista se recarga limpia', async () => {
  let state = DATA();
  const { root, calls, listeners, C } = load((url, opts) => {
    if (opts.method === 'POST') { state = { ...state, enviados: 4, pendientes: [state.pendientes[1]], archivados: [ITEM(1, { status: 'enviado' }), ...state.archivados] }; return { status: 200, body: { ok: true, mensaje: '✅ Enviado: quedó registrado' } }; }
    return { status: 200, body: state };
  });
  await flush(); await flush();
  const seen = [];
  const origDraw = root;
  await listeners.click({ target: { closest: (s) => (s === '[data-cola-act]' ? { getAttribute: (k) => (k === 'data-cola-id' ? '1' : 'enviado') } : null) } });
  assert.ok(calls.includes('POST /api/v1/prospecting/admin/cola/1/accion {"accion":"enviado"}'));
  assert.match(root.innerHTML, /4 de 15 enviados/);
  assert.doesNotMatch(root.innerHTML, /data-cola-card="1"/, 'ya no está en Pendientes');
  assert.match(root.innerHTML, /✅ Enviado: quedó registrado/);
  assert.match(CSS, /\.vp-cola-card\.is-leaving \{ opacity: 0; transform: translateX\(40px\) scale\(\.97\); \}/);
  assert.equal(C.model.leaving, '');
  void seen; void origDraw;
});

test('⋯: Saltar y No contactar (pide confirmación antes de excluir en todos los canales)', async () => {
  const { root, calls, listeners } = load((url, opts) => (opts.method === 'POST' ? { status: 200, body: { ok: true, mensaje: 'ok' } } : { status: 200, body: DATA() }));
  await flush(); await flush();
  await listeners.click({ target: { closest: (s) => (s === '[data-cola-menu]' ? { getAttribute: () => '2' } : null) } });
  assert.match(root.innerHTML, /⏭ Saltar \(vuelve mañana\)/);
  assert.match(root.innerHTML, />🚫 No contactar</);
  const block = { target: { closest: (s) => (s === '[data-cola-act]' ? { getAttribute: (k) => (k === 'data-cola-id' ? '2' : 'bloquear') } : null) } };
  await listeners.click(block);
  assert.ok(!calls.some((c) => c.startsWith('POST')), 'primer toque solo pide confirmar');
  assert.match(root.innerHTML, /🚫 Confirmar: no contactar nunca \(todos los canales\)/);
  await listeners.click(block);
  assert.ok(calls.includes('POST /api/v1/prospecting/admin/cola/2/accion {"accion":"bloquear"}'));
  await listeners.click({ target: { closest: (s) => (s === '[data-cola-act]' ? { getAttribute: (k) => (k === 'data-cola-id' ? '3' : 'saltar') } : null) } });
  assert.ok(calls.includes('POST /api/v1/prospecting/admin/cola/3/accion {"accion":"saltar"}'));
});

test('sin sesión: 401 lleva al ingreso de v2+', async () => {
  const { window, C } = load(() => ({ status: 401, body: {} }));
  await flush(); await flush();
  await assert.rejects(C.api.cola());
  assert.equal(window.location.href, '/admin-v2plus/login');
});

test('celular primero: 1 columna; en PC 2 columnas; botones de 52 px', () => {
  assert.match(CSS, /\.vp-cola-grid \{ display: grid; grid-template-columns: minmax\(0, 1fr\);/);
  assert.match(CSS, /@media \(min-width: 1024px\) \{ \.vp-cola-grid \{ grid-template-columns: repeat\(2, minmax\(0, 1fr\)\);/);
  assert.match(CSS, /\.vp-cola-btn \{ min-height: 52px;/);
});
