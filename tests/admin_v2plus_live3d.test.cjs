// Consola v2+ · tarjeta NEGOCIO EN VIVO 3D (modulo-3d-consola.png): campos, consumo, botones y lugar en la ficha.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

function load() {
  const listeners = [];
  const ctx = vm.createContext({ window: {}, document: { addEventListener: (t) => listeners.push(t), querySelectorAll: () => [], documentElement: {} },
    MutationObserver: class { observe() {} }, setInterval: () => 0, fetch: async () => ({}) });
  vm.runInContext(readFileSync('app/web/oficina/admin_v2plus_live3d.js', 'utf8'), ctx);
  return ctx.window.CxLive3dCard;
}
const DATA = {
  company_id: '21a3065e-38ee-4fc3-96ed-ae1707a3b8e4', name: 'The Time Machine', enabled: true, template: 'bar', has_engine: true, privacy: 'nombre',
  audience: 'dueno_admin', roles: [], tv: true, lite: 'auto', usage: { screens: 2, month_bytes: 0.3 * 1024 ** 3 },
  options: { templates: [{ key: 'bar', label: 'Bar' }, { key: 'general', label: 'Oficina general (sin piso 3D aún)' }], privacy: [{ key: 'nombre', label: 'Nombre + inicial y cargo' }, { key: 'cargo', label: 'Solo cargo' }],
    audience: [{ key: 'dueno', label: 'Solo el dueño' }, { key: 'dueno_admin', label: 'Dueño y administradores' }, { key: 'roles', label: 'Roles elegidos' }],
    lite: [{ key: 'auto', label: 'Automático' }, { key: 'siempre', label: 'Siempre' }, { key: 'nunca', label: 'Nunca' }] },
};

test('consumo medido: pantallas abiertas y GB/MB del mes', () => {
  const { usageText } = load()._pure;
  assert.equal(usageText({ screens: 2, month_bytes: 0.3 * 1024 ** 3 }), '2 pantallas abiertas · 0,3 GB este mes');
  assert.equal(usageText({ screens: 1, month_bytes: 5 * 1024 ** 2 }), '1 pantalla abierta · 5,0 MB este mes');
  assert.equal(usageText(null), '—');
});

test('tarjeta como la imagen aprobada: estado, campos, consumo y los cuatro botones', () => {
  const html = load()._pure.cardHtml(DATA, {});
  for (const t of ['NEGOCIO EN VIVO 3D', 'Encendido', 'Plantilla', 'Privacidad del personal', 'Quién lo ve', 'Modo TV / pantalla completa', 'Permitido',
    'Modo liviano en celulares', 'Consumo', '2 pantallas abiertas · 0,3 GB este mes', 'Abrir como el cliente', 'Editar distribución (arquitecto)', 'Personajes del negocio', 'Apagar']) {
    assert.ok(html.includes(t), t);
  }
  assert.ok(html.includes(`/admin-v2plus/oficina?piso=${DATA.company_id}&amp;arquitecto=1`) || html.includes(`/admin-v2plus/oficina?piso=${DATA.company_id}&arquitecto=1`));
  assert.ok(html.includes('&personajes=1') || html.includes('&amp;personajes=1'));
  assert.ok(!/\son[a-z]+=/i.test(html) && !html.includes(' style="'), 'sin código ni estilos en línea (CSP de la consola)');
  const off = load()._pure.cardHtml({ ...DATA, enabled: false, has_engine: false, audience: 'roles', roles: ['mesero'] }, {});
  assert.ok(off.includes('Apagado') && off.includes('Encender') && off.includes('data-cx3d-open disabled') && off.includes('value="mesero"'));
});

test('lo que se guarda al cambiar cada control', () => {
  const { bodyFor } = load()._pure;
  assert.deepEqual(JSON.parse(JSON.stringify(bodyFor('roles', 'mesero, cajero\nbarman', DATA))), { roles: ['mesero', 'cajero', 'barman'] });
  assert.deepEqual(JSON.parse(JSON.stringify(bodyFor('toggle', null, DATA))), { enabled: false });
  assert.deepEqual(JSON.parse(JSON.stringify(bodyFor('tv', null, DATA))), { tv: false });
  assert.deepEqual(JSON.parse(JSON.stringify(bodyFor('plantilla', 'taller', DATA))), { plantilla: 'taller' });
});

test('va DEBAJO de Mini paneles en "Módulos y mini paneles" y el script se carga en la consola', () => {
  const company = readFileSync('app/web/admin_v2plus_company.js', 'utf8');
  const panels = company.indexOf('F().panelsZone({'), card = company.indexOf('window.CxLive3dCard.html(c.id)'), crm = company.indexOf('${crmCard(c)}');
  assert.ok(panels > 0 && card > panels && card < crm, 'debajo de Mini paneles');
  const html = readFileSync('app/web/admin_v2plus.html', 'utf8');
  assert.ok(html.indexOf('/admin-v2plus-live3d.js') > html.indexOf('/admin-v2plus-company.js'));
});
