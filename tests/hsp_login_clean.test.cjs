// 049Y: la pantalla de ingreso de los mini paneles muestra solo logo, título y
// usuario/clave. Los controles de avisos ("Toca la pantalla para activar el
// sonido…" y el botón Sonido) aparecen solo ya con sesión.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { FakeStorage, boot, flush } = require('./_cashier_boot.cjs');

function routes(url) {
  if (url.includes('/mini-panel-login')) return [200, { access_token: 'jwt' }];
  if (url.includes('/orders?status=active')) return [200, { orders: [] }];
  if (url.includes('/waiter-ordering/menu')) return [200, { categories: [] }];
  if (url.includes('/waiter-ordering/caja/config')) return [200, { direct_sale: false, redesign: false }];
  if (url.includes('/caja-arqueo/')) return [403, { detail: 'cash_count_not_enabled' }];
  if (url.includes('/mini-panel-operational-session')) return [200, { operational_session: { status: 'active', active_seconds: 0, break_seconds: 0 } }];
  return [404, {}];
}

const controls = (b) => b.body.children.find((c) => c.id === 'cxAlertControls');

test('caja: sin sesión no hay controles de sonido; al entrar sí', async () => {
  const b = boot({ local: new FakeStorage(), routes });
  for (let i = 0; i < 4; i += 1) await flush();
  assert.match(b.root.innerHTML, /cshLoginForm/);
  assert.equal(controls(b), undefined, 'la pantalla de ingreso no muestra configuraciones');
  assert.doesNotMatch(b.root.innerHTML, /Sonido|Toca la pantalla/);

  (b.listeners.document.submit || []).forEach((cb) => cb({ preventDefault() {}, target: { closest: (sel) => (sel === '#cshLoginForm' ? {} : null) } }));
  for (let i = 0; i < 8; i += 1) await flush();
  assert.doesNotMatch(b.root.innerHTML, /cshLoginForm/);
  assert.ok(controls(b), 'ya con sesión aparecen los controles');
  assert.match(controls(b).innerHTML, /data-cx-alert-mute/);
});

test('caja: al volver al ingreso los controles se quitan', async () => {
  const local = new FakeStorage();
  local.setItem('clonexa_cashier_token_c1', 'jwt');
  const b = boot({ local, routes });
  for (let i = 0; i < 6; i += 1) await flush();
  assert.ok(controls(b));
  b.click('data-csh-logout');
  for (let i = 0; i < 4; i += 1) await flush();
  assert.match(b.root.innerHTML, /cshLoginForm/);
  assert.equal(controls(b), undefined);
});

test('mesero y cocina: la visibilidad de los controles sigue a la pantalla de ingreso', () => {
  for (const file of ['app/web/hsp_waiter.js', 'app/web/hsp_kitchen.js', 'app/web/hsp_cashier.js']) {
    const src = readFileSync(file, 'utf8');
    assert.match(src, /Alerts\.setVisible\(state\.screen !== "login"\)/, file);
  }
  const alerts = readFileSync('app/web/hsp_alerts.js', 'utf8');
  assert.match(alerts, /let visible = false;/, 'ocultos hasta que el panel diga que hay sesión');
});
