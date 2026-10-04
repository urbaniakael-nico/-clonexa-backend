// Consola v2+ con CSP estricta: el logo ya no usa onerror en línea; si no
// carga, logoFallback() muestra "CX" igual que antes.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

function fn(source, name) {
  const start = source.search(new RegExp(`\\n  function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 3);
  return tail.slice(0, tail.search(/\n  (?:async )?function |\n  \/\/ -{3,}/)) + '\n';
}

function fakeLogo({ complete, naturalWidth }) {
  const fallback = { style: {} };
  const img = {
    complete, naturalWidth, style: {}, listeners: {},
    parentElement: { querySelector: (sel) => (sel === '.cx-logo-fallback' ? fallback : null) },
    addEventListener(type, cb) { this.listeners[type] = cb; },
  };
  return { img, fallback };
}

for (const file of ['app/web/admin_v2plus.js', 'app/web/admin_v2plus_login.js']) {
  const source = readFileSync(file, 'utf8').replace(/\r\n/g, '\n');

  test(`${file}: logo roto → se ve "CX" (ya roto al cargar o después)`, () => {
    const broken = fakeLogo({ complete: true, naturalWidth: 0 });
    const later = fakeLogo({ complete: false, naturalWidth: 0 });
    const ok = fakeLogo({ complete: true, naturalWidth: 120 });
    const ctx = vm.createContext({ document: { querySelectorAll: () => [broken.img, later.img, ok.img] } });
    vm.runInContext(fn(source, 'logoFallback'), ctx);
    ctx.logoFallback();
    assert.equal(broken.img.style.display, 'none');
    assert.equal(broken.fallback.style.display, 'grid');
    assert.equal(later.fallback.style.display, undefined);
    later.img.listeners.error();
    assert.equal(later.img.style.display, 'none');
    assert.equal(later.fallback.style.display, 'grid');
    assert.equal(ok.img.style.display, undefined);
    assert.equal(ok.fallback.style.display, undefined);
  });
}

test('las páginas de v2+ no traen código en línea', () => {
  for (const file of ['app/web/admin_v2plus.html', 'app/web/admin_v2plus_login.html']) {
    const html = readFileSync(file, 'utf8');
    assert.doesNotMatch(html, /\son[a-z]+\s*=/, file);
    assert.doesNotMatch(html, /<script(?![^>]*\bsrc=)[^>]*>/, file);
    assert.doesNotMatch(html, /\sstyle=/, file);
  }
});

test('el HTML que generan los JS de v2+ tampoco trae estilos ni manejadores en línea', () => {
  const { readdirSync } = require('node:fs');
  const files = readdirSync('app/web').filter((f) => /^admin_v2plus.*\.js$/.test(f));
  assert.ok(files.includes('admin_v2plus_companies.js'));
  for (const f of files) {
    const js = readFileSync(`app/web/${f}`, 'utf8');
    assert.doesNotMatch(js, /\sstyle="/, f);
    assert.doesNotMatch(js, /<[a-z][^>]*\son(click|error|load|submit|input|change)=/i, f);
  }
  const html = readFileSync('app/web/admin_v2plus.html', 'utf8');
  assert.match(html, /<script src="\/admin-v2plus\.js"><\/script>\s*<script src="\/admin-v2plus-companies\.js"><\/script>/);
});
