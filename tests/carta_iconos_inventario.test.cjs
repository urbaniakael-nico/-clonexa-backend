// Inventario del portal (client.js, bloque 079A): "Agregar artículo" con vista
// previa del ícono mientras escriben el nombre, "Cambiar ícono" (galería con
// buscador por nombre y sinónimos), "Subir foto" y "Volver al automático"; lo
// mismo al editar un artículo existente. Interruptor apagado: no se agrega nada.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const CLIENT = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');
const BLOCK = CLIENT.slice(CLIENT.indexOf('/* CLONEXA_079A_ICONOS_CARTA_START'), CLIENT.indexOf('/* CLONEXA_079A_ICONOS_CARTA_END */'));
const url = (k) => `/assets/iconos-carta/${k === 'bebida' ? 'bebida-generica' : k}.svg?v=ic1`;
const GALLERY = [['agua', 'Agua', ['agua', 'cristal', 'brisa', 'manantial']], ['aguardiente', 'Aguardiente', ['aguardiente', 'guaro', 'antioqueno', 'nectar', 'blanco', 'amarillo']],
  ['paquete', 'Paquete', ['paquete', 'snack', 'papa', 'papita']], ['tiket', 'Tiket', ['tiket', 'ticket', 'boleta', 'entrada', 'cover']], ['ron', 'Ron', ['ron']],
  ['bebida', 'Bebida', []]].map(([key, label, words]) => ({ key, label, words, url: url(key), generic: key === 'bebida' }));

function el(tag = 'div', attrs = {}) {
  return {
    tag, attrs, value: attrs.value || '', id: attrs.id || '', innerHTML: '', outerHTML: '', files: attrs.files || null, removed: false,
    matches(sel) { const m = /^\[([\w-]+)\]$/.exec(sel); return sel === `#${this.id}` || Boolean(m && m[1] in this.attrs); },
    closest(sel) { return this.matches(sel) ? this : (this.parent ? this.parent.closest(sel) : (sel === '.cx-inv-field' && this.id === 'inventoryCreateName' ? fieldEl : null)); },
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    insertAdjacentHTML(_where, html) { inserted.push(html); },
    remove() { this.removed = true; }, focus() {},
  };
}
let inserted = [];
let fieldEl = null;

function load({ on = true, items = [], name = '' } = {}) {
  inserted = [];
  const calls = [];
  const listeners = {};
  const nameInput = el('input', { id: 'inventoryCreateName', value: name });
  fieldEl = el('div');
  let cardHost = null;
  const notices = [];
  const document = {
    head: { appendChild() {} }, body: el('body'),
    getElementById(id) { return id === 'inventoryCreateName' ? nameInput : null; },
    createElement() { return { textContent: '', id: '' }; },
    querySelector(sel) {
      if (sel === '[data-ico-card-079a=""]') return cardHost;
      if (sel === '.client-main') return el('main');
      return null;
    },
    addEventListener(type, fn) { listeners[type] = fn; },
  };
  const api = async (path, options = {}) => {
    calls.push(`${options.method || 'GET'} ${path}${options.body ? ` ${options.body}` : ''}`);
    if (path.endsWith('/carta-iconos')) return on ? { on: true, gallery: GALLERY, items } : { on: false };
    if (options.method === 'PUT') { const body = JSON.parse(options.body); return { ok: true, icon: { source: body.icono_key ? 'manual' : 'auto', key: body.icono_key || 'ron', url: url(body.icono_key || 'ron') } }; }
    return {};
  };
  const apiForm = async (path) => { calls.push(`FORM ${path}`); return {}; };
  const h = (v) => String(v ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  const ctx = vm.createContext({ document, state: { companyId: 'c1' }, api, apiForm, h, showInventoryNotice: (m) => notices.push(m), FormData: class { append() {} },
    URL: { createObjectURL: () => 'blob:foto' }, setTimeout: (f) => f(), console });
  vm.runInContext(`${BLOCK}\n;globalThis.__T = { cxIcons079A, cxIconsMount079A, cxIconCardHtml079A, cxIconRecognize079A, cxIconsAfterCreate079A, cxIconGalleryHtml079A, cxIconPanelHtml079A };`, ctx);
  return { T: ctx.__T, calls, listeners, nameInput, notices, setCard(v) { cardHost = v; } };
}

test('apagado: el Inventario queda igual (no se inserta tarjeta, panel ni galería)', async () => {
  const { T, calls } = load({ on: false });
  await T.cxIconsMount079A('create');
  await T.cxIconsMount079A('modify');
  assert.deepEqual(inserted, []);
  assert.equal(T.cxIcons079A.on, false);
  assert.deepEqual(calls, ['GET /hospitality/companies/c1/carta-iconos', 'GET /hospitality/companies/c1/carta-iconos']);
});

test('agregar artículo: vista previa al escribir y "✓ Reconocido: <palabra>" o "Sin reconocer"', async () => {
  const { T } = load({ name: 'Aguardiente Antioqueño 375' });
  await T.cxIconsMount079A('create');
  assert.equal(inserted.length, 1);
  const card = inserted[0];
  assert.match(card, /<img src="\/assets\/iconos-carta\/aguardiente\.svg\?v=ic1" alt="Aguardiente Antioqueño 375"/);
  assert.match(card, /✓ Reconocido: aguardiente/);
  assert.match(card, /Así se verá en la pantalla de la mesa \(QR\)\./);
  assert.match(card, /🎨 Cambiar ícono/);
  assert.match(card, /📷 Subir foto<input type="file"/);
  assert.doesNotMatch(card, /Volver al automático/, 'solo aparece si se eligió algo a mano');
  for (const [name, key, word] of [['AGUARDIENTES', 'aguardiente', 'aguardientes'], ['Papitas', 'paquete', 'papitas'], ['Boleta VIP', 'tiket', 'boleta']]) {
    assert.deepEqual({ ...T.cxIconRecognize079A(name) }, { key, word });
  }
  const unknown = T.cxIconCardHtml079A('Hookah menta', { pending: {} });
  assert.match(unknown, /Sin reconocer: saldrá el ícono genérico/);
  assert.match(unknown, /bebida-generica\.svg/);
  assert.doesNotMatch(unknown, /🍽/);
});

test('Cambiar ícono: galería con buscador por nombre y sinónimos; la elección se guarda al crear', async () => {
  const { T, calls } = load({ name: 'Hookah' });
  await T.cxIconsMount079A('create');
  T.cxIcons079A.editing = '';
  T.cxIcons079A.query = 'guaro';
  let g = T.cxIconGalleryHtml079A();
  assert.match(g, /Galería de íconos/);
  assert.match(g, /placeholder="🔎 Buscar: guaro, papas, entrada\.\.\."/);
  assert.match(g, /data-ico-pick-079a="aguardiente"/);
  assert.doesNotMatch(g, /data-ico-pick-079a="ron"/);
  T.cxIcons079A.query = 'entra';
  assert.match(T.cxIconGalleryHtml079A(), /data-ico-pick-079a="tiket"/);
  T.cxIcons079A.query = '';
  assert.equal((T.cxIconGalleryHtml079A().match(/data-ico-pick-079a=/g) || []).length, GALLERY.length);
  // elegir a mano
  T.cxIcons079A.pending = { key: 'tiket', file: null };
  const card = T.cxIconCardHtml079A('Hookah', { pending: T.cxIcons079A.pending });
  assert.match(card, /🎨 Elegido a mano: Tiket/);
  assert.match(card, /tiket\.svg/);
  assert.match(card, /↺ Volver al automático/);
  g = T.cxIconGalleryHtml079A();
  assert.match(g, /class="is-current" data-ico-pick-079a="tiket"/);
  await T.cxIconsAfterCreate079A('new-id');
  assert.ok(calls.includes('PUT /hospitality/companies/c1/carta-iconos/items/new-id {"icono_key":"tiket"}'));
  assert.equal(T.cxIcons079A.pending.key, null, 'el siguiente artículo arranca en automático');
});

test('Subir foto al crear: la foto manda en la vista previa y se sube con el flujo de siempre', async () => {
  const { T, calls } = load({ name: 'Ron' });
  await T.cxIconsMount079A('create');
  T.cxIcons079A.pending = { key: null, file: { name: 'f.jpg' }, preview: 'blob:foto' };
  assert.match(T.cxIconCardHtml079A('Ron', { pending: T.cxIcons079A.pending }), /📷 Foto propia[\s\S]*Volver al automático/);
  await T.cxIconsAfterCreate079A('id9');
  assert.ok(calls.includes('FORM /companies/c1/waiter-ordering/products/id9/image'));
});

test('editar artículos existentes: lista con su ícono, Cambiar ícono y Volver al automático', async () => {
  const items = [
    { id: 'a', name: 'Aguardiente <x>', icon: { source: 'auto', key: 'aguardiente', url: url('aguardiente'), word: 'aguardiente' } },
    { id: 'b', name: 'Hookah', icon: { source: 'manual', key: 'tiket', url: url('tiket'), word: 'hookah' } },
    { id: 'c', name: 'Paquete', icon: { source: 'photo', key: '', url: '/api/v1/companies/21a3065e-38ee-4fc3-96ed-ae1707a3b8e4/waiter-ordering/products/0f0f0f0f-0000-4000-8000-000000000001/image', word: 'paquete' } },
    { id: 'd', name: 'Cachimba', icon: { source: 'generic', key: 'bebida', url: url('bebida'), word: 'cachimba' } }];
  const { T, calls, listeners, notices } = load({ items });
  await T.cxIconsMount079A('modify');
  const panel = inserted[0];
  assert.match(panel, /Íconos de la carta/);
  assert.match(panel, /Aguardiente &lt;x&gt;/);
  assert.match(panel, /✓ Reconocido: aguardiente/);
  assert.match(panel, /🎨 Elegido a mano: Tiket[\s\S]*data-ico-auto-079a="b"/);
  assert.match(panel, /📷 Foto propia/);
  assert.match(panel, /Sin reconocer: ícono genérico/);
  assert.equal((panel.match(/data-ico-auto-079a=/g) || []).length, 1, 'Volver al automático solo en el elegido a mano');
  // Volver al automático en el existente
  const target = { closest: (s) => (s === '[data-ico-auto-079a]' ? { getAttribute: () => 'b' } : null), matches: () => false };
  await listeners.click({ target });
  assert.ok(calls.includes('PUT /hospitality/companies/c1/carta-iconos/items/b {"icono_key":null}'));
  assert.deepEqual(notices, ['Volvió al ícono automático.']);
});

test('enganches: render del Inventario y crear artículo llaman al bloque 079A', () => {
  assert.match(CLIENT, /if \(mode === "compras" && carta049Q\) cxInvRestockLoad049T\(\);\n    cxIconsMount079A\(mode\);/);
  assert.match(CLIENT, /const createdItemId = createdItem\?\.id \|\| created\?\.id \|\| created\?\.item_id;\n      await cxIconsAfterCreate079A\(createdItemId\);/);
  assert.doesNotMatch(BLOCK, /\son[a-z]+=|style="/, 'sin manejadores ni estilos en línea');
});
