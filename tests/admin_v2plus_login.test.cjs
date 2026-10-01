// Consola v2+: la entrada pide la huella apenas abre (si hay equipos
// registrados y el navegador lo permite) y deja "Entrar con clave" como
// alternativa; el panel "Huella de este equipo" y la conversión WebAuthn.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const loginSource = readFileSync('app/web/admin_v2plus_login.js', 'utf8');
const webauthnSource = readFileSync('app/web/webauthn_browser.js', 'utf8');
const consoleSource = readFileSync('app/web/admin_v2plus.js', 'utf8');

function el(attrs = {}) {
  return { hidden: false, textContent: '', attrs, getAttribute(k) { return this.attrs[k]; }, focus() { this.focused = true; } };
}

function bootLogin({ hasPasskeys, supported = true, error = '' }) {
  const nodes = {
    '[data-vp-passkey-box]': el(), '[data-vp-password-form]': el(), '[data-vp-passkey-status]': el(),
    '[data-vp-login-error]': Object.assign(el(), { hidden: !error, textContent: error }), '[data-vp-use-passkey]': el(), '[data-vp-no-passkey]': el(),
  };
  const email = el();
  const calls = [];
  const listeners = {};
  const document = {
    body: el({ 'data-has-passkeys': hasPasskeys ? 'true' : 'false' }),
    querySelector: (sel) => nodes[sel] || null,
    getElementById: (id) => (id === 'email' ? email : null),
    addEventListener: (type, cb) => { listeners[type] = cb; },
  };
  const window = { location: { href: '' }, PublicKeyCredential: supported ? function PKC() {} : undefined };
  const navigator = { credentials: { get: async () => { calls.push('get'); throw Object.assign(new Error('x'), { name: 'NotAllowedError' }); } } };
  const fetch = async (url) => { calls.push(url); return { ok: true, json: async () => ({ ok: true, options: { challenge: 'AQID', allowCredentials: [{ id: 'BAUG', type: 'public-key' }] } }) }; };
  const ctx = vm.createContext({ window, document, navigator, fetch, atob, btoa, Uint8Array, String, JSON, Object, Array, Error });
  vm.runInContext(webauthnSource, ctx);
  vm.runInContext(loginSource, ctx);
  return { nodes, email, calls, window };
}

const flush = () => new Promise((r) => setImmediate(r));

test('con huellas registradas, apenas abre pide la huella; la clave queda como alternativa', async () => {
  const t = bootLogin({ hasPasskeys: true });
  await flush(); await flush();
  assert.equal(t.nodes['[data-vp-passkey-box]'].hidden, false);
  assert.equal(t.nodes['[data-vp-password-form]'].hidden, true);
  assert.deepEqual(t.calls.slice(0, 2), ['/admin-v2plus/api/passkey/login/options', 'get'], 'pide la huella sin que toquen nada');
  assert.match(t.nodes['[data-vp-login-error]'].textContent, /Se canceló|entra con tu clave/);
});

test('sin huellas registradas, o sin soporte del navegador, va directo a la clave', async () => {
  for (const opts of [{ hasPasskeys: false }, { hasPasskeys: true, supported: false }]) {
    const t = bootLogin(opts);
    await flush();
    assert.equal(t.nodes['[data-vp-password-form]'].hidden, false);
    assert.equal(t.nodes['[data-vp-passkey-box]'].hidden, true);
    assert.equal(t.calls.length, 0, 'no intenta la huella');
    assert.equal(t.email.focused, true);
  }
});

test('después de una clave equivocada se queda en el formulario de clave', async () => {
  const t = bootLogin({ hasPasskeys: true, error: 'Credenciales invalidas.' });
  await flush();
  assert.equal(t.nodes['[data-vp-password-form]'].hidden, false);
  assert.equal(t.calls.length, 0);
  assert.equal(t.nodes['[data-vp-use-passkey]'].hidden, false, 'puede volver a la huella');
});

test('conversión WebAuthn: base64url de ida y vuelta y opciones con buffers', () => {
  const ctx = vm.createContext({ window: {}, atob, btoa, Uint8Array, String, Object, Array });
  vm.runInContext(webauthnSource, ctx);
  const W = ctx.window.CxWebAuthn;
  const bytes = new Uint8Array([0, 255, 62, 63, 1]);
  assert.equal(W.toBase64url(bytes.buffer), 'AP8-PwE');
  assert.deepEqual(Array.from(new Uint8Array(W.toBuffer('AP8-PwE'))), [0, 255, 62, 63, 1]);
  const created = W.creationOptions({ challenge: 'AQID', user: { id: 'BAU', name: 'x' }, excludeCredentials: [{ id: 'Bg', type: 'public-key' }] });
  assert.equal(new Uint8Array(created.challenge).length, 3);
  assert.equal(new Uint8Array(created.user.id).length, 2);
  assert.match(W.friendlyError({ name: 'NotAllowedError' }), /Se canceló/);
});

test('panel "Huella de este equipo" en la consola', () => {
  const ctx = vm.createContext({ window: {}, document: {}, Date, Math, Number, String, Array, encodeURIComponent });
  vm.runInContext(consoleSource, ctx);
  const ui = ctx.window.CxConsolePlus;
  assert.equal(ui.passkeysPanel({ open: false }), '');
  const empty = ui.passkeysPanel({ open: true, list: [], ready: true });
  assert.match(empty, /Registrar la huella de este equipo/);
  assert.match(empty, /Aún no hay equipos registrados/);
  assert.match(empty, /la clave sigue funcionando como alternativa/);
  const one = ui.passkeysPanel({ open: true, ready: true, list: [{ id: 'k1', label: 'Portátil <b>', created_at: '2026-10-01T10:00:00Z', last_used_at: null }] });
  assert.match(one, /Equipos registrados \(1\)/);
  assert.match(one, /data-vp-passkey-delete="k1"/);
  assert.match(one, /Portátil &lt;b&gt;/);
  assert.match(ui.passkeysPanel({ open: true, list: [], ready: false }), /Falta la migración 022p_admin_passkeys/);
  assert.match(ui.passkeysPanel({ open: true, list: [] }, false), /no permite llaves de acceso/);
});
