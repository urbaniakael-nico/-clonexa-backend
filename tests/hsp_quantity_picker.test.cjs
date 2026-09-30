// 049W: selector de cantidad libre (entero + fracción), el MISMO componente
// (hsp_qty.js) en el mesero, la caja, el link de domicilios y el QR de mesa.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const { FakeStorage, boot, flush } = require('./_cashier_boot.cjs');

const qtySource = readFileSync('app/web/hsp_qty.js', 'utf8');

function picker() {
  const window = {};
  vm.runInContext(qtySource, vm.createContext({ window, document: {}, Number, String, Math, Array }));
  return window.CxQtyPicker;
}

// Un nodo falso con listeners, como los que arma el navegador.
function node(extra = {}) {
  return {
    value: '', textContent: '', listeners: {}, attrs: {}, classList: { on: false, toggle(_c, v) { this.on = v; } },
    setAttribute(k, v) { this.attrs[k] = v; },
    addEventListener(t, cb) { (this.listeners[t] = this.listeners[t] || []).push(cb); },
    fire(t) { (this.listeners[t] || []).forEach((cb) => cb({ target: this })); },
    ...extra,
  };
}

function box() {
  const nodes = {};
  return { nodes, querySelector: (sel) => { if (sel === '[data-cxq]') return null; nodes[sel] = nodes[sel] || node(); return nodes[sel]; } };
}

const money = (s) => s.replace(/ /g, ' ');

test('6 y 1/2: el entero más la fracción, en vivo, a 6,5 veces el precio', () => {
  const P = picker();
  assert.deepEqual({ ...P.split(6.5) }, { whole: 6, fraction: '1/2' });
  assert.equal(P.label(6.5), '6 1/2');
  assert.equal(P.label(0.25), '1/4');
  assert.equal(P.label(3), '3');
  assert.equal(P.quantityOf(6, '1/2'), 6.5);
  assert.equal(P.quantityOf(2, '1/8'), 2.125);
  assert.equal(money(P.totalText(28000, 6.5, 'Vas a cobrar')), 'Vas a cobrar $182.000 · 6 1/2');

  const b = box();
  const control = P.mount(b, { price: 28000, portions: true, quantity: 1, verb: 'Vas a cobrar' });
  const input = b.nodes['[data-cxq-whole]'];
  input.value = '6';
  input.fire('input');
  b.nodes['[data-cxq-frac="1/2"]'].fire('click');
  assert.equal(control.quantity(), 6.5);
  assert.equal(money(b.nodes['[data-cxq-total]'].textContent), 'Vas a cobrar $182.000 · 6 1/2');
  assert.equal(b.nodes['[data-cxq-frac="1/2"]'].attrs['aria-pressed'], 'true');
  b.nodes['[data-cxq-step="1"]'].fire('click');                 // + sube el entero, la fracción se queda
  assert.equal(control.quantity(), 7.5);
  b.nodes['[data-cxq-frac="1/2"]'].fire('click');               // tocarla otra vez la quita
  assert.equal(control.quantity(), 7);
});

test('solo media: el entero puede quedar en 0 si hay fracción; sin fracción nunca baja de 1', () => {
  const P = picker();
  const b = box();
  const control = P.mount(b, { price: 28000, portions: true, quantity: 1 });
  b.nodes['[data-cxq-frac="1/2"]'].fire('click');
  b.nodes['[data-cxq-step="-1"]'].fire('click');
  assert.equal(control.quantity(), 0.5);
  b.nodes['[data-cxq-frac="1/2"]'].fire('click');               // sin fracción vuelve a 1
  assert.equal(control.quantity(), 1);
  b.nodes['[data-cxq-step="-1"]'].fire('click');
  assert.equal(control.quantity(), 1);
});

test('los productos sin porciones no muestran fracciones', () => {
  const P = picker();
  const withPortions = P.html({ price: 28000, portions: true });
  for (const f of ['1/8', '1/4', '1/2', '3/4']) assert.match(withPortions, new RegExp(`data-cxq-frac="${f.replace('/', '\\/')}"`));
  const whole = P.html({ price: 4500, portions: false, quantity: 2 });
  assert.doesNotMatch(whole, /data-cxq-frac/);
  assert.match(whole, /data-cxq-step="1"/);
  assert.match(whole, /data-cxq-whole[^>]*value="2"/);
  const b = box();
  const control = P.mount(b, { price: 4500, portions: false, quantity: 1 });
  b.nodes['[data-cxq-whole]'].value = '6';
  b.nodes['[data-cxq-whole]'].fire('input');
  assert.equal(control.quantity(), 6);
});

// ------------------------------------------------------- caja, de punta a punta
const MENU = {
  quantity_buttons: ['1/4', '1/2', '3/4', '1', '2'], quantity_picker: true, menu_emojis: false,
  categories: [{ key: 'pollos', label: 'Pollos', station: 'Parrilla', has_image: false, quick_notes: [], products: [
    { id: 'pollo', name: 'POLLO Asado', price: 28000, allows_portions: true, carta_kind: 'preparado',
      quantity_ref_id: 'pollo', quantity_options: [{ label: '1/2', price: 14000, available: true }] },
    { id: 'gaseosa', name: 'GASEOSA', price: 4500, allows_portions: false, carta_kind: 'directo' },
  ] }],
};

function routes() {
  return (url) => {
    if (url.includes('/orders?status=active')) return [200, { orders: [] }];
    if (url.includes('/waiter-ordering/menu')) return [200, MENU];
    if (url.includes('/waiter-ordering/caja/config')) return [200, { direct_sale: true, redesign: true }];
    if (url.includes('/caja/resumen')) return [200, { sold: 0, charged: 0, pending: 0, orders: 0, accounts: 0, ticket: 0, deliveries: 0, tables: 0, methods: [], direct_sales: [] }];
    if (url.includes('/caja/ventas')) return [201, { ok: true, charged: true, label: 'Venta 020', order: { id: 'v20' } }];
    if (url.includes('/qr-tables')) return [200, { tables: [] }];
    return [404, {}];
  };
}

async function ready() {
  const local = new FakeStorage();
  local.setItem('clonexa_cashier_token_c1', 'jwt');
  const b = boot({ local, routes: routes() });
  for (let i = 0; i < 6; i += 1) await flush();
  return b;
}

const lastSheet = (b) => b.body.children.filter((c) => c.className === 'wtr-sheet-backdrop').pop();

test('caja: pedir 6 y 1/2 de pollo manda 6,5 (sin precio del cliente) y la gaseosa solo enteros', async () => {
  const b = await ready();
  b.click('data-csh-new-sale');
  b.click('data-csh-product', 'pollo');
  let sheet = lastSheet(b);
  assert.match(sheet.innerHTML, /data-cxq/);
  assert.doesNotMatch(sheet.innerHTML, /wtr-qty-grid/);                // ya no los botones fijos
  assert.match(sheet.innerHTML, /data-cxq-frac="1\/8"/);
  sheet.querySelector('[data-cxq-whole]').value = '6';
  sheet.querySelector('[data-cxq-whole]').fire('input');
  sheet.querySelector('[data-cxq-frac="1/2"]').fire('click');
  assert.match(money(sheet.querySelector('[data-cxq-total]').textContent), /Vas a cobrar \$182\.000 · 6 1\/2/);
  sheet.querySelector('[data-sheet-add]').fire('click');
  assert.match(b.root.innerHTML, /6 1\/2 · POLLO Asado/);
  assert.match(money(b.root.innerHTML), /data-cx5-sale-total>\$\s?182\.000</);

  b.click('data-csh-product', 'gaseosa');
  sheet = lastSheet(b);
  assert.doesNotMatch(sheet.innerHTML, /data-cxq-frac/);                // sin porciones: solo el entero
  sheet.querySelector('[data-sheet-add]').fire('click');

  b.click('data-csh-sale-route', 'now');
  b.click('data-csh-sale-pay', 'transfer');
  await flush(); await flush();
  const body = JSON.parse(b.calls.find((c) => c.url.includes('/caja/ventas')).options.body);
  assert.deepEqual(body.items.map((i) => [i.inventory_item_id, i.quantity, i.fraction]), [['pollo', 6.5, undefined], ['gaseosa', 1, undefined]]);
  assert.ok(body.items.every((i) => !('unit_price' in i)));
});

// ------------------------------------------------------- el mismo en los cuatro
test('el mismo componente en mesero, caja, domicilios y QR de mesa', () => {
  const pages = { 'hsp_waiter.html': 'hsp_waiter.js', 'hsp_cashier.html': 'hsp_cashier.js', 'domicilio.html': 'hsp_delivery.js', 'hospitality_order.html': 'hospitality_order.js' };
  for (const [page, app] of Object.entries(pages)) {
    const html = readFileSync(`app/web/${page}`, 'utf8');
    const qty = html.indexOf('/client-static/hsp_qty.js');
    assert.ok(qty > 0, `${page} carga hsp_qty.js`);
    assert.ok(qty < html.indexOf('hsp_menu_kit.js') && qty < html.indexOf(app), `${page}: antes del kit y de la app`);
  }
  const kit = readFileSync('app/web/hsp_menu_kit.js', 'utf8');
  assert.match(kit, /Picker\.html\(/);
  assert.match(kit, /Picker\.mount\(/);
  for (const file of ['hsp_waiter.js', 'hsp_cashier.js', 'hsp_delivery.js']) {
    assert.match(readFileSync(`app/web/${file}`, 'utf8'), /quantityPicker:/, file);
  }
  const qr = readFileSync('app/web/hospitality_order.js', 'utf8');
  assert.match(qr, /Picker\.html\(\{ price, portions/);
  assert.match(qr, /Picker\.mount\(sheet/);
  assert.match(qr, /state\.quantityPicker = first\.quantity_picker === true/);
  // Nadie más dibuja sus propios botones de fracción.
  for (const file of ['hsp_menu_kit.js', 'hsp_waiter.js', 'hsp_cashier.js', 'hsp_delivery.js', 'hospitality_order.js']) {
    assert.doesNotMatch(readFileSync(`app/web/${file}`, 'utf8'), /data-cxq-frac|"1\/8"/, file);
  }
});

// ------------------------------------------------------- Inventario: Editar
const clientSource = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');

function fn(name) {
  const start = clientSource.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = clientSource.slice(start + 1);
  return `${tail.slice(0, tail.indexOf('\n  }\n') + 4)}\n`;
}

function inventoryCtx() {
  const ctx = vm.createContext({ String, Number, Array, JSON, Math, Object });
  vm.runInContext(
    'function h(v){return String(v ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}\n'
      + 'function cxInvUnitOptions049Q(sel){return ["kg","gr","lb","unidad"].map((u)=>`<option value="${u}" ${u===sel?"selected":""}>${u}</option>`).join("");}\n'
      + 'function cxCarUnitLabel049O(u){return String(u||"unidad");}\n'
      + 'function cxCarFactor049N(unit, i){const w={kg:1000,gr:1,lb:453.6}; if (i.consumption_unit==="unidad") return unit==="unidad"?1:null; return w[unit] ?? null;}\n'
      + ['cxInvEditNeedsConvert049W', 'cxInvEditDialogHtml049W', 'cxInvEditPayloads049W'].map(fn).join(''),
    ctx,
  );
  return ctx;
}

const POLLO = { id: 'i1', name: 'POLLO Asado', unit: 'unidad', consumption_unit: 'unidad', stock: 35.25, min_stock_natural: 5 };
const ROW = { id: 'i1', name_reference: 'POLLO Asado', status: 'active', color: 'blanco', current_stock: 35.25 };

test('editar un insumo: nombre, unidad, mínimo y estado se editan; la existencia no', () => {
  const ctx = inventoryCtx();
  const html = ctx.cxInvEditDialogHtml049W(POLLO, ROW, '35,25 unidad');
  for (const field of ['data-inv-edit-name', 'data-inv-edit-unit', 'data-inv-edit-min', 'data-inv-edit-status']) {
    const tag = html.match(new RegExp(`<(input|select)[^>]*${field}="i1"[^>]*>`));
    assert.ok(tag, field);
    assert.doesNotMatch(tag[0], /disabled|readonly/i, `${field} editable`);
  }
  assert.match(html, /data-inv-edit-name="i1" value="POLLO Asado"/);
  assert.match(html, /<option value="unidad" selected>/);
  assert.match(html, /data-inv-edit-min="i1" value="5"/);
  // La existencia se ve, bloqueada, y se corrige solo con "Corregir saldo".
  const stock = html.slice(html.indexOf('data-inv-edit-stock'), html.indexOf('</div>', html.indexOf('data-inv-edit-stock')));
  assert.match(stock, /🔒 Existencia<\/span><b>35,25 unidad<\/b>/);
  assert.doesNotMatch(stock, /<input/);
  assert.match(stock, /data-inv-edit-fix="i1">Corregir saldo/);
});

test('guardar la edición manda nombre/estado a Inventario y unidad/mínimo a Carta, nunca la existencia', () => {
  const ctx = inventoryCtx();
  const out = ctx.cxInvEditPayloads049W(POLLO, ROW, { name: ' POLLO Asado entero ', unit: 'unidad', min: '8', status: 'inactive' });
  assert.deepEqual(JSON.parse(JSON.stringify(out)), {
    carta: { unit: 'unidad', min_stock: 8 },
    item: { name_reference: 'POLLO Asado entero', status: 'inactive', color: 'blanco' },
  });
  assert.ok(!JSON.stringify(out).includes('stock"') || !('current_stock' in out.item));
  assert.equal(ctx.cxInvEditPayloads049W(POLLO, ROW, { name: '  ', unit: 'unidad', min: 1 }).error, 'Escribe el nombre del insumo.');
  assert.match(ctx.cxInvEditPayloads049W(POLLO, ROW, { name: 'x', unit: 'unidad', min: -1 }).error, /negativo/);
  // Pasar de unidad a kg con existencia: se pide la equivalencia (la cantidad física no se pierde).
  assert.match(ctx.cxInvEditPayloads049W(POLLO, ROW, { name: 'x', unit: 'kg', min: 1 }).error, /cuántos kg hay en 1 unidad/);
  const converted = ctx.cxInvEditPayloads049W(POLLO, ROW, { name: 'x', unit: 'kg', min: 1, convert: '1.2' });
  assert.deepEqual(JSON.parse(JSON.stringify(converted.carta)), { unit: 'kg', min_stock: 1, convert_amount: 1.2 });
  // Entre unidades del mismo tipo no se pregunta nada.
  const carne = { id: 'c1', name: 'CARNE', unit: 'kg', consumption_unit: 'g', stock: 11450, min_stock_natural: 2 };
  assert.equal(ctx.cxInvEditNeedsConvert049W(carne, 'lb'), false);
});

test('la fila de Modificar material trae "Editar"', () => {
  assert.match(clientSource, /data-inv-edit-open="\$\{id\}">Editar<\/button>/);
  assert.match(clientSource, /cxInvOpenDialog049S\(editOpen\.getAttribute\("data-inv-edit-open"\), "edit"\)/);
});
