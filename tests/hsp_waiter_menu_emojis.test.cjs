// Mesero panel: a representative emoji per category / product (switch
// menu_emojis), a photo from Admin V2 always replaces it, and the table title
// never repeats "Mesa".
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/hsp_waiter.js', 'utf8');

function fn(name) {
  const start = source.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

function constBlock(name) {
  const start = source.indexOf(`\n  const ${name} = `);
  assert.ok(start >= 0, name);
  const end = source.indexOf(';\n', start);
  return source.slice(start, end + 2).replace(`const ${name}`, `var ${name}`);
}

function context(menuEmojis = true) {
  const ctx = vm.createContext({ String, Array });
  vm.runInContext(
    `var companyId = "c1"; var state = { menuEmojis: ${menuEmojis} };\n`
      + constBlock('MENU_EMOJIS') + constBlock('DEFAULT_MENU_EMOJI')
      + fn('menuEmoji') + fn('tileArt') + fn('tableTitle'),
    ctx,
  );
  return ctx;
}

test('each kind of food gets its own emoji', () => {
  const ctx = context();
  const expected = {
    'Pollo Asado': '🍗', 'CARNE Churrasco': '🥩', 'Hamburguesa doble': '🍔', 'GASEOSA Coca Cola': '🥤',
    'Bebidas': '🥤', 'Cerveza Aguila': '🍺', 'Papas francesas': '🍟', 'Ensalada de la casa': '🥗',
    'Postre del día': '🍰', 'Sopa de verduras': '🍲', 'Arroz con pollo': '🍚', 'Pescado frito': '🐟',
    'Perro caliente': '🌭', 'Arepa con queso': '🫓',
  };
  for (const [name, emoji] of Object.entries(expected)) assert.equal(ctx.menuEmoji(name), emoji, name);
});

test('matching ignores accents, case and plurals', () => {
  const ctx = context();
  assert.equal(ctx.menuEmoji('PÓLLOS'), '🍗');
  assert.equal(ctx.menuEmoji('Hamburguesas'), '🍔');
  assert.equal(ctx.menuEmoji('Cervezas nacionales'), '🍺');
  assert.equal(ctx.menuEmoji('  jugos naturales'), '🥤');
});

test('a product with no match uses the default icon', () => {
  const ctx = context();
  assert.equal(ctx.menuEmoji('Combo familiar'), '🍽️');
  assert.equal(ctx.menuEmoji(''), '🍽️');
  assert.equal(ctx.menuEmoji(undefined), '🍽️');
});

test('the table is easy to extend: every row is [words, emoji] and words are unique', () => {
  const ctx = context();
  const seen = new Set();
  for (const [words, emoji] of ctx.MENU_EMOJIS) {
    assert.ok(Array.isArray(words) && words.length && typeof emoji === 'string');
    for (const word of words) {
      assert.equal(seen.has(word), false, `duplicated word: ${word}`);
      assert.match(word, /^[a-zñ0-9]+$/, `write words without accents/uppercase: ${word}`);
      seen.add(word);
    }
  }
});

test('an uploaded photo replaces the emoji, for categories and products', () => {
  const ctx = context();
  const category = ctx.tileArt('category', { key: 'pollo', label: 'Pollo', has_image: true });
  assert.equal(category.type, 'image');
  assert.equal(category.url, '/api/v1/companies/c1/waiter-ordering/categories/pollo/image');
  const product = ctx.tileArt('product', { id: 'inv-9', name: 'Pollo asado', has_image: true });
  assert.equal(product.url, '/api/v1/companies/c1/waiter-ordering/products/inv-9/image');
  const group = ctx.tileArt('product', { id: 'pollo', name: 'Pollo', has_image: true, image_item_id: 'pollo-12' });
  assert.equal(group.url, '/api/v1/companies/c1/waiter-ordering/products/pollo-12/image');
  assert.equal(ctx.tileArt('category', { key: 'pollo', label: 'Pollo', has_image: false }).emoji, '🍗');
  assert.equal(ctx.tileArt('product', { id: 'x', name: 'Cerveza', has_image: false }).emoji, '🍺');
});

test('with the switch off the panel looks exactly like before', () => {
  const ctx = context(false);
  assert.equal(ctx.tileArt('category', { key: 'pollo', label: 'Pollo' }).emoji, '🍽️');
  assert.equal(ctx.tileArt('product', { id: 'x', name: 'Pollo' }).type, 'none');
  assert.equal(ctx.tileArt('product', { id: 'x', name: 'Pollo', has_image: true }).type, 'image');
});

test('the table title never repeats "Mesa"', () => {
  const ctx = context();
  assert.equal(ctx.tableTitle('Mesa 11'), 'Mesa 11');
  assert.equal(ctx.tableTitle('mesa 3'), 'mesa 3');
  assert.equal(ctx.tableTitle('11'), 'Mesa 11');
  assert.equal(ctx.tableTitle(' 7 '), 'Mesa 7');
  assert.equal(ctx.tableTitle('Mesada VIP'), 'Mesa Mesada VIP');
});

test('no screen builds "Mesa ${...}" by hand anymore', () => {
  assert.doesNotMatch(source, /`Mesa \$\{h?\(?(state\.table|t\.table_number)/);
});
