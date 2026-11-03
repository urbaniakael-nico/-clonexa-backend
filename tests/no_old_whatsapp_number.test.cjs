// El WhatsApp de Clonexa ahora es +57 314 479 8220; el numero viejo de EE. UU. no debe volver.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const OLD = /13468244098|346[ .-]?824[ .-]?4098/;

function walk(dir, out) {
  for (const d of fs.readdirSync(dir, { withFileTypes: true })) {
    if (['node_modules', '.git', '__pycache__'].includes(d.name)) continue;
    const p = path.join(dir, d.name);
    if (d.isDirectory()) walk(p, out);
    else if (/\.(py|js|cjs|html|json|md|txt|css)$/.test(d.name)) out.push(p);
  }
  return out;
}

test('el numero viejo de WhatsApp (+1 346 824 4098) no aparece en app, migraciones, ops ni pruebas', () => {
  const files = ['app', 'migrations', 'ops', 'tests'].flatMap((d) => walk(path.join(ROOT, d), []));
  const bad = files.filter((f) => f !== __filename && OLD.test(fs.readFileSync(f, 'utf8'))).map((f) => path.relative(ROOT, f));
  assert.deepStrictEqual(bad, []);
});
