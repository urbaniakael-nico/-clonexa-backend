// Auditoría XSS (2026-10): el soporte/guía de una venta de mini panel se abre
// en una ventana nueva (mismo origen) con document.write. file_data llega del
// servidor tal cual lo subió otro usuario; antes se interpolaba sin escapar y
// una carga como `x" onerror="…` cerraba el atributo src.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/mini_panel.js', 'utf8').replace(/\r\n/g, '\n');

function fn(name) {
  const start = source.search(new RegExp(`\\n  function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function /);
  return tail.slice(0, next) + '\n';
}

function load() {
  const written = [];
  const ctx = vm.createContext({
    String,
    window: { open: () => ({ document: { write: (html) => written.push(html) } }) },
  });
  vm.runInContext(`${fn('h')}${fn('salesOpenFile022G')}${fn('salesPrintFile022G')}`, ctx);
  return { ctx, written };
}

const PAYLOADS = [
  'x" onerror="alert(document.cookie)',
  '"><img src=x onerror=alert(1)>',
  'data:image/png;base64,AAAA"><img src=x onerror=alert(1)>',
];

for (const type of ['image/png', 'application/pdf']) {
  for (const payload of PAYLOADS) {
    test(`abrir e imprimir soporte (${type}) no ejecuta ${payload}`, () => {
      const { ctx, written } = load();
      ctx.salesOpenFile022G({ file_data: payload, file_type: type });
      ctx.salesPrintFile022G({ file_data: payload, file_type: type });
      assert.equal(written.length, 2);
      for (const html of written) {
        assert.doesNotMatch(html, /<img src=x/);
        assert.doesNotMatch(html, /src="[^"]*"\s*onerror=/);
        assert.doesNotMatch(html, /src="x" onerror/);
        // Un solo atributo src, cerrado donde lo cierra la plantilla.
        assert.equal((html.match(/ src="/g) || []).length, 1);
        assert.match(html, /&quot;|&lt;/);
      }
    });
  }
}

test('un soporte normal se ve igual que antes', () => {
  const { ctx, written } = load();
  const png = 'data:image/png;base64,iVBORw0KGgo+/=';
  ctx.salesOpenFile022G({ file_data: png, file_type: 'image/png' });
  ctx.salesOpenFile022G({ file_data: 'data:application/pdf;base64,JVBERi0=', file_type: 'application/pdf' });
  assert.equal(written[0], `<img src="${png}" style="max-width:100%;height:auto;display:block;margin:auto" />`);
  assert.equal(written[1], '<iframe src="data:application/pdf;base64,JVBERi0=" style="width:100%;height:100vh;border:0"></iframe>');
});
