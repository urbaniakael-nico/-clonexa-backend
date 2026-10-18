// Nombre fijo del invitado (qr_welcome_name): el QR ya no cambia el nombre (solo
// "Agregar mi nombre" una vez), el panel del bar lo corrige con diálogo solo si el
// servidor responde 200, y sin el interruptor la carta de bar usa el encabezado de siempre.
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { readFileSync } = require('node:fs');

const QR = readFileSync('app/web/hospitality_order.js', 'utf8').replace(/\r\n/g, '\n');
const CLIENT = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');

test('QR: el nombre del servidor manda y se manda una sola vez', () => {
  assert.match(QR, /customer: welcomeOn056B\(\) \? \(state\.namePending056C \|\| ""\) : \(state\.customerName \|\| ""\)/);
  assert.match(QR, /rememberCustomerName\(state\.guest056C\.named \? state\.guest056C\.name : ""\);/);
  assert.match(QR, /if \(welcomeNamed056C\(\)\) return;  \/\/ nombre fijo: no se vuelve a pedir ni se cambia/);
  assert.match(QR, /includes\("nombre_fijo"\)\) state\.error = wt056B\("Tu nombre ya quedó guardado en esta mesa\./);
  assert.doesNotMatch(QR.slice(QR.indexOf('CLONEXA_056B_QR_WELCOME_START'), QR.indexOf('CLONEXA_056B_QR_WELCOME_END')), /"Cambiar nombre"/);
});

test('QR: encabezado nuevo solo con la bienvenida; "Mesa abierta" en la etiqueta, sin caja verde', () => {
  assert.match(QR, /\$\{welcomeOn056B\(\) \? welcomeBarTop056C\(companyName, tableAccount, songDraft\) : `\$\{barHeaderHtml\(companyName\)\}/, 'sin el interruptor: el encabezado de siempre');
  assert.match(QR, /if \(welcomeOn056B\(\) && barMenuOn\(\)\) \{\n      state\.openHint056C = true;\n    \} else \{\n      state\.message = "La mesa sigue abierta\./);
  assert.match(QR, /data-open-hint aria-expanded="\$\{open\}" aria-controls="qrwHint056C"/);
  assert.match(QR, /<strong id="qrTableAccountTotal030B">[\s\S]*<small id="qrTableAccountMeta030B">[\s\S]*<div id="qrTableAccountBreakdown033C"/, 'la cuenta se pinta con los mismos ids de siempre');
  assert.match(QR, /@media\(max-width:339px\)\{\.qrw-cards\{grid-template-columns:minmax\(0,1fr\)\}/);
});

test('panel del bar: "Corregir nombre" solo con el interruptor y con cuenta del QR', () => {
  const start = CLIENT.indexOf('  function cxQrGuestFixBtn056C');
  const end = CLIENT.indexOf('  function cxQrGuestFixStyles056C');
  const out = {};
  vm.runInContext(`const h = (v) => String(v ?? "").replace(/</g, "&lt;"); let cxQrGuestFixEnabled056C = false; ${CLIENT.slice(start, end)}
    out.btn = cxQrGuestFixBtn056C; out.on = () => { cxQrGuestFixEnabled056C = true; };`, vm.createContext({ out, String }));
  assert.equal(out.btn('Mesa 4', { account_id: 'qr_a', name: 'Nico' }), '', 'apagado: nada');
  out.on();
  assert.match(out.btn('Mesa 4', { account_id: 'qr_a', name: 'Nico' }), /data-guest-fix-table="Mesa 4" data-guest-fix-account="qr_a" data-guest-fix-name="Nico">✏️ Corregir nombre/);
  assert.equal(out.btn('Mesa 4', { name: 'Cliente' }), '', 'sin cuenta del QR (mesero o barra): nada');
  assert.match(CLIENT, /fetch\(`\$\{API\}\/hospitality\/companies\/\$\{encodeURIComponent\(companyId\)\}\/qr-guests\/config`, \{ headers: authHeaders\(\) \}\)/);
  assert.match(CLIENT, /role="dialog" aria-modal="true"[\s\S]*Sí, corregir/);
  assert.doesNotMatch(CLIENT.slice(CLIENT.indexOf('CLONEXA_056C_GUEST_NAME_FIX_START'), CLIENT.indexOf('CLONEXA_056C_GUEST_NAME_FIX_END')), /\bconfirm\(|\balert\(|\bprompt\(/);
});
