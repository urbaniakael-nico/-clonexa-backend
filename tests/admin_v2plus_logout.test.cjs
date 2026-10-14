// Consola v2+ · botón "Cerrar sesión" del menú lateral (2026-10-14): abre el
// diálogo de la v2+, cierra la sesión EN EL SERVIDOR (consoleApi.logout =
// POST /admin-v2/logout) y va a /admin-v2plus/login con replace (Atrás no
// vuelve). Si el servidor no responde, avisa y no sale.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const plus = readFileSync('app/web/admin_v2plus.js', 'utf8');
const admin = readFileSync('app/web/admin_v2plus_admin.js', 'utf8');
const html = readFileSync('app/web/admin_v2plus.html', 'utf8').replace(/\r\n/g, '\n');
const css = readFileSync('app/web/admin_v2plus.css', 'utf8').replace(/\r\n/g, '\n');

function boot(logoutResponse = { status: 303, ok: false, type: 'opaqueredirect' }) {
  const calls = [];
  const replaced = [];
  const handlers = {};
  const nodes = {};
  const main = { innerHTML: '' };
  const document = {
    readyState: 'complete',
    body: { appendChild: (node) => { nodes[node.id] = node; } },
    getElementById: (id) => (id === 'vpMain' ? main : nodes[id] || null),
    createElement: () => ({ id: '', innerHTML: '' }),
    querySelectorAll: () => [],
    querySelector: () => null,
    addEventListener: (type, fn) => { (handlers[type] = handlers[type] || []).push(fn); },
  };
  const fetch = async (url, options = {}) => {
    calls.push({ url, method: options.method || 'GET', credentials: options.credentials, redirect: options.redirect });
    if (url === '/admin-v2/logout') {
      if (logoutResponse instanceof Error) throw logoutResponse;
      return logoutResponse;
    }
    return { status: 200, ok: true, json: async () => ({ ok: true, companies: [], totals: {} }) };
  };
  const window = {
    location: { href: '', hash: '', origin: 'https://clonexa.app', replace: (u) => replaced.push(u), reload: () => replaced.push('reload') },
    addEventListener: (type, fn) => { (handlers[`window:${type}`] = handlers[`window:${type}`] || []).push(fn); },
    setInterval: () => 0,
  };
  const ctx = vm.createContext({ window, document, fetch, JSON, Object, Array, String, Math, Number, Promise, Error, Date, Map, Set,
    URLSearchParams, encodeURIComponent, decodeURIComponent, setTimeout, clearTimeout });
  vm.runInContext(plus, ctx);
  vm.runInContext(admin, ctx);
  const click = async (attr) => {
    const target = { closest: (sel) => (sel === `[${attr}]` ? target : null), getAttribute: () => '' };
    for (const fn of handlers.click || []) await fn({ target, preventDefault() {} });
    await new Promise((r) => setTimeout(r, 0));
  };
  return { window, calls, replaced, handlers, click, dialog: () => (nodes.vpLogout ? nodes.vpLogout.innerHTML : '') };
}

test('menú: "Cerrar sesión" con ícono, abajo junto a "Huella de este equipo" y sin "Volver a Admin V2"', () => {
  assert.match(html, /data-vp-passkeys-open>☝ Huella de este equipo<\/button>\s*<button class="vp-nav-item vp-logout-btn" type="button" data-vp-logout-open>/);
  assert.match(html, /<svg class="vp-logout-icon"[^>]*aria-hidden="true"/);
  assert.doesNotMatch(html, /Volver a Admin V2/);
  // En móvil el menú lateral pasa arriba (estático) y nada oculta el botón.
  assert.ok(css.includes('.vp-sidebar { position: static; height: auto; }'));
  assert.doesNotMatch(css, /\.vp-logout-btn[^{]*\{[^}]*display:\s*none/);
});

test('clic → diálogo de la v2+ → POST /admin-v2/logout en el servidor → replace a /admin-v2plus/login', async () => {
  const b = boot();
  await b.click('data-vp-logout-open');
  assert.match(b.dialog(), /class="vp-modal" data-vp-logout-modal[\s\S]*class="vp-panel vp-modal-card" role="dialog" aria-modal="true"/);
  assert.match(b.dialog(), /¿Cerrar tu sesión de la consola en este equipo\?/);
  assert.match(b.dialog(), /class="vp-btn vp-btn-danger" type="button" data-vp-logout-go >Cerrar sesión<\/button><button class="vp-btn" type="button" data-vp-logout-close>Cancelar/);
  assert.equal(b.calls.filter((c) => c.url === '/admin-v2/logout').length, 0, 'abrir el diálogo no cierra nada');
  await b.click('data-vp-logout-go');
  const post = b.calls.find((c) => c.url === '/admin-v2/logout');
  assert.deepEqual({ ...post }, { url: '/admin-v2/logout', method: 'POST', credentials: 'same-origin', redirect: 'manual' });
  assert.deepEqual(b.replaced, ['/admin-v2plus/login']);
  assert.equal(b.window.location.href, '', 'replace, no href: el botón Atrás no vuelve a la consola');
});

test('cancelar no cierra la sesión', async () => {
  const b = boot();
  await b.click('data-vp-logout-open');
  await b.click('data-vp-logout-close');
  assert.equal(b.dialog(), '');
  assert.equal(b.calls.filter((c) => c.url === '/admin-v2/logout').length, 0);
  assert.deepEqual(b.replaced, []);
});

test('si el servidor falla o no responde, avisa y no sale', async () => {
  for (const response of [{ status: 500, ok: false, type: 'basic' }, new Error('Failed to fetch')]) {
    const b = boot(response);
    await b.click('data-vp-logout-open');
    await b.click('data-vp-logout-go');
    assert.deepEqual(b.replaced, []);
    assert.match(b.dialog(), /class="vp-alert" role="alert"/);
    assert.match(b.dialog(), /No se pudo cerrar la sesión en el servidor|Failed to fetch/);
    assert.doesNotMatch(b.dialog(), /disabled/, 'se puede reintentar');
  }
});

test('Atrás desde la memoria del navegador (bfcache) recarga y el servidor manda al ingreso', () => {
  const b = boot();
  const [onShow] = b.handlers['window:pageshow'];
  onShow({ persisted: false });
  assert.deepEqual(b.replaced, []);
  onShow({ persisted: true });
  assert.deepEqual(b.replaced, ['reload']);
});

test('"Cerrar mi sesión" de Accesos usa el mismo consoleApi.logout y muestra el error si falla', () => {
  assert.match(admin, /ask\("Cerrar mi sesión", "¿Cerrar tu sesión de la consola en este equipo\?", \(\) => act\(\(\) => consoleApi\.logout\(\), ""\)/);
  assert.match(plus, /const admin = window\.CxConsoleAdmin && window\.CxConsoleAdmin\.consoleApi;[\s\S]*await admin\.logout\(\);/);
});
