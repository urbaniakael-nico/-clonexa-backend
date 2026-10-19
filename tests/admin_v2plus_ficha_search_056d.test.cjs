// Consola v2+ · Ficha: el buscador de módulos encuentra los mini paneles con
// "mini_panels", "minipanel", "mini panel" y "paneles" (sin plurales, guiones,
// guion bajo ni tildes), y el aviso sin mini paneles trae "Encender módulo".
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { readFileSync } = require('node:fs');

const fichaSource = readFileSync('app/web/admin_v2plus_ficha.js', 'utf8');

function load() {
  const window = { location: { href: '', origin: 'https://clonexa.app', hash: '' } };
  vm.runInContext(fichaSource, vm.createContext({ window, document: {}, JSON, Object, Array, String, Math, Number, Promise, Error, Date, Map, Set, encodeURIComponent }));
  return window.CxFicha;
}

const MODULES = [
  { enabled: false, settings: {}, module: { code: 'mini_panel', name: 'Mini panel', category: 'core' } },
  { enabled: true, settings: {}, module: { code: 'inventory', name: 'Inventario', category: 'inventory' } },
  { enabled: true, settings: {}, module: { code: 'cotizaciones', name: 'Cotizaciones', category: 'sales' } },
];

test('buscador: mini_panels, minipanel, mini panel, paneles, mini-panel y Mini Panéles', () => {
  const f = load();
  for (const q of ['mini_panels', 'minipanel', 'mini panel', 'paneles', 'mini-panel', 'Mini Panéles', 'MINIPANELS']) {
    const codes = f.filterModules(MODULES, q).map((m) => m.code);
    assert.deepEqual([...codes], ['mini_panel'], q);
  }
  assert.deepEqual([...f.filterModules(MODULES, 'inventarios').map((m) => m.code)], ['inventory'], 'plural de otros módulos');
  assert.deepEqual([...f.filterModules(MODULES, 'cotizacion').map((m) => m.code)], ['cotizaciones']);
  assert.equal(f.filterModules(MODULES, 'nomina').length, 0);
});

test('aviso sin mini paneles: botón "Encender módulo" directo', () => {
  assert.match(fichaSource, /Esta empresa no tiene encendido el módulo de mini paneles \(mini_panel\)\. <button class="vp-btn vp-btn-sm" type="button" data-vpf-module="mini_panel" data-action="activate">Encender módulo<\/button>/);
});
