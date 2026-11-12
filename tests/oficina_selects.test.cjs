// Oficina 3D · las listas del editor (Personaje, Género, Túnica, Cuerpo...) se leen: fondo oscuro, letra clara,
// color-scheme oscuro y contraste AA (>= 4.5:1). Cada opción tiene su nombre (ninguna vacía).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');

const css = readFileSync('app/web/oficina/oficina.css', 'utf8').replace(/\r\n/g, '\n');
const app = readFileSync('app/web/oficina/oficina_app.js', 'utf8').replace(/\r\n/g, '\n');

function rule(selector) {
  const re = new RegExp('(^|\\n|\\})\\s*' + selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s*\\{([^}]*)\\}');
  const m = css.match(re);
  assert.ok(m, `falta la regla ${selector}`);
  return Object.fromEntries(m[2].split(';').filter(Boolean).map(d => { const i = d.indexOf(':'); return [d.slice(0, i).trim(), d.slice(i + 1).trim()]; }));
}
function lum(hex) {
  const n = hex.replace('#', ''); const full = n.length === 3 ? n.split('').map(c => c + c).join('') : n;
  const [r, g, b] = [0, 2, 4].map(i => parseInt(full.slice(i, i + 2), 16) / 255).map(c => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
const contrast = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

test('desplegables con esquema oscuro y opciones de fondo oscuro con letra clara (AA)', () => {
  assert.equal(rule(':root')['color-scheme'], 'dark', 'el desplegable nativo se pinta oscuro');
  const sel = rule('select');
  assert.equal(sel['color-scheme'], 'dark');
  const opt = rule('select option,select optgroup');
  assert.ok(contrast(opt.color, opt['background-color']) >= 4.5, `opciones: ${contrast(opt.color, opt['background-color']).toFixed(1)}:1`);
  assert.ok(contrast(sel.color, sel['background-color']) >= 4.5);
  const chk = rule('select option:checked');
  assert.ok(contrast(chk.color, chk['background-color']) >= 4.5, 'la opción elegida también se lee');
  const dis = rule('select option:disabled');
  assert.ok(contrast(dis.color, opt['background-color']) >= 4.5);
  for (const s of ['#top select', '#info select', '#ed input,#ed select']) {
    const r = rule(s);
    assert.match(r.background, /^#[0-9a-f]{6}$/i, `${s}: fondo sólido (no blanco ni transparente sobre el sistema)`);
    assert.ok(contrast(r.color === '#fff' ? '#ffffff' : r.color, r.background) >= 4.5, `${s}: contraste`);
  }
});

test('cada opción del editor tiene su nombre (Personaje, Género, Túnica, Barba, Cuerpo, Peinado, Accesorio)', () => {
  const start = app.indexOf('// ===== reglas puras'), end = app.indexOf('// ===== fin reglas puras =====');
  const ctx = vm.createContext({ genderFromName: () => null });
  vm.runInContext(app.slice(start, end) + '\nthis.out = {MIXAMO, MIXAMO_LABEL, BODY_LABEL, HAIR_LABEL, ACC_LABEL};', ctx);
  const { MIXAMO, MIXAMO_LABEL, BODY_LABEL, HAIR_LABEL, ACC_LABEL } = ctx.out;
  for (const g of ['hombre', 'mujer']) for (const m of MIXAMO[g]) assert.ok(String(MIXAMO_LABEL[m] || '').trim(), `personaje ${m} sin nombre`);
  for (const L of [BODY_LABEL, HAIR_LABEL, ACC_LABEL]) for (const [k, v] of Object.entries(L)) assert.ok(String(v).trim(), `opción ${k} vacía`);
  // las opciones fijas del formulario Mixamo tienen texto
  assert.match(app, /opt\('', 'Automático', v\.model\)/);
  assert.match(app, /opt\('hombre', 'Hombre', gender\)\}\$\{opt\('mujer', 'Mujer', gender\)/);
  assert.doesNotMatch(app, /<option[^>]*>\s*<\/option>/, 'ninguna opción vacía');
});
