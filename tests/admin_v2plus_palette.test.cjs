// Consola v2+ · Buscador Ctrl+K: tildes, parciales, acciones rápidas y teclado.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/admin_v2plus_palette.js', 'utf8');

function load(extra = {}) {
  const listeners = {};
  const opened = [];
  const window = { location: { hash: '' }, open: (...a) => opened.push(a), ...extra };
  const document = { addEventListener: (t, f) => { listeners[t] = f; } };
  const ctx = vm.createContext({ window, document, navigator: {}, fetch: async () => ({ ok: true, json: async () => [] }), JSON, Object, Array, String, Number, Math, Promise, RegExp, encodeURIComponent });
  vm.runInContext(source, ctx);
  return { P: window.CxConsolePalette, window, listeners, opened };
}

const DATA = {
  views: { command: 'Centro de mando', companies: 'Empresas', catalog: 'Catálogo', switches: 'Interruptores', health: 'Salud y seguridad' },
  companies: [{ id: 'a1', name: 'ASADERO EL SOCIO', slug: 'asadero', kind: 'registrada', status: 'active' },
    { id: 't1', name: 'The Time Machine', slug: 'ttm', kind: 'registrada', status: 'active' },
    { id: 'v1', name: 'Vieja Guardia', slug: 'vieja', status: 'archived' }],
  modules: [{ code: 'waiter_ordering', name: 'Pedidos por mesero', category: 'hospitality' }, { code: 'nomina_colombia', name: 'Nómina Colombia', category: 'finance' }],
  packages: [{ id: 'p1', code: 'restaurante_pro', name: 'Restaurante Pro' }],
  switches: [{ key: 'cashier_redesign', label: 'Caja rediseñada', group: 'Caja', module: 'waiter_ordering' }],
};

test('busca empresas, secciones, módulos, paquetes e interruptores, sin tildes y con parciales', () => {
  const { P } = load();
  const index = P.buildIndex(DATA);
  const titles = (q) => P.search(index, q).map((r) => `${r.kind}:${r.title}`);
  assert.equal(titles('asad')[0], 'company:ASADERO EL SOCIO', 'parcial');
  assert.equal(titles('nomina')[0], 'module:Nómina Colombia', 'sin tilde contra "Nómina"');
  assert.equal(titles('CATALOGO')[0], 'section:Catálogo', 'mayúsculas y tildes');
  assert.equal(titles('tm')[0], 'company:The Time Machine', 'iniciales / subsecuencia');
  assert.ok(titles('restaurante').includes('package:Restaurante Pro'));
  assert.equal(titles('caja redis')[0], 'switch:Caja rediseñada');
  assert.ok(titles('waiter').includes('module:Pedidos por mesero'), 'por código');
  assert.equal(titles('zzzzqqq').length, 0);
  assert.ok(!titles('ra').some((t) => t.startsWith('section:')), 'dos letras sueltas no traen secciones al azar');
  assert.ok(titles('').length > 5, 'sin texto lista todo');
  assert.ok(titles('vieja')[0].startsWith('company:'), 'también las archivadas');
});

test('acciones rápidas de una empresa: Ficha, entrar como empresa, copiar links', () => {
  const { P } = load();
  const [asadero] = P.search(P.buildIndex(DATA), 'asadero');
  assert.deepEqual(JSON.parse(JSON.stringify(asadero.actions.map((a) => a.label))), ['Abrir Ficha', 'Entrar como empresa', 'Copiar links']);
  const html = (P.model.results = [asadero], P.model.open = true, P.panel());
  assert.match(html, /role="combobox"[\s\S]*role="listbox"[\s\S]*role="option" aria-selected="true"/);
  assert.match(html, /data-vpp-act="0:0">Abrir Ficha[\s\S]*data-vpp-act="0:1">Entrar como empresa[\s\S]*data-vpp-act="0:2">Copiar links/);
  assert.doesNotMatch(html, /\sstyle=/);
});

test('ejecuta cada acción sin guardar nada', () => {
  const calls = [];
  const plus = { setView: (v, p) => calls.push(['view', v, p && JSON.parse(JSON.stringify(p))]), toast: () => {}, VIEWS: DATA.views, state: {} };
  const catalog = { model: { tab: 'paquetes', builder: { x: 1 }, modQuery: '' } };
  const { P, window, opened } = load({ CxConsolePlus: plus, CxConsoleCatalog: catalog });
  P.run({ id: 'ficha', companyId: 'a1' });
  assert.equal(window.location.hash, '#empresa/a1');
  P.run({ id: 'enter', companyId: 'a 1' });
  assert.deepEqual(JSON.parse(JSON.stringify(opened[0])), ['/client?company_id=a%201', '_blank', 'noopener']);
  P.run({ id: 'go', view: 'health' });
  P.run({ id: 'module', code: 'nomina_colombia', name: 'Nómina Colombia' });
  P.run({ id: 'package', packageId: 'p1' });
  P.run({ id: 'switch', key: 'cashier_redesign' });
  assert.deepEqual(calls, [['view', 'health', undefined], ['view', 'catalog', { tab: 'modulos' }], ['view', 'catalog', { tab: 'paquetes', editPackage: 'p1' }], ['view', 'switches', { key: 'cashier_redesign' }]]);
  assert.equal(catalog.model.modQuery, 'Nómina Colombia');
  assert.equal(catalog.model.builder, null);
  assert.doesNotMatch(source, /method:\s*"(POST|PUT|PATCH|DELETE)"/, 'el buscador solo lee');
});

test('teclado: Ctrl+K abre y cierra, flechas mueven, Enter ejecuta, Esc cierra; también desde cualquier sección', () => {
  const { P, listeners } = load();
  const ev = (key, extra = {}) => ({ key, preventDefault() { this.prevented = true; }, ...extra });
  const k = ev('k', { ctrlKey: true });
  listeners.keydown(k);
  assert.equal(P.model.open, true);
  assert.equal(k.prevented, true);
  P.model.results = P.search(P.buildIndex(DATA), '');
  P.model.active = 0;
  listeners.keydown(ev('ArrowDown'));
  assert.equal(P.model.active, 1);
  listeners.keydown(ev('ArrowUp'));
  listeners.keydown(ev('ArrowUp'));
  assert.equal(P.model.active, P.model.results.length - 1, 'da la vuelta');
  listeners.keydown(ev('Escape'));
  assert.equal(P.model.open, false);
  listeners.keydown(ev('k', { metaKey: true }));
  assert.equal(P.model.open, true, 'Cmd+K en Mac');
  listeners.keydown(ev('k', { ctrlKey: true }));
  assert.equal(P.model.open, false);
  const html = readFileSync('app/web/admin_v2plus.html', 'utf8');
  assert.match(html, /class="vp-nav-item vp-search-nav" type="button" data-vp-search>/, 'botón en el menú lateral de todas las secciones');
  assert.match(html, /<script src="\/admin-v2plus-palette\.js"><\/script>/);
  const plus = readFileSync('app/web/admin_v2plus.js', 'utf8');
  assert.doesNotMatch(plus, /llega en la fase 2/);
});
