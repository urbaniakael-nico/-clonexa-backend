const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/admin_v2.js', 'utf8');

function fn(name) {
  const start = source.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

function constBlock(name) {
  const start = source.search(new RegExp(`\\n  const ${name} = `));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

// Mesero/cocina/caja as Admin V2 mini panel segments: off by default (a
// missing key is disabled, never assumed enabled), round-trips through the
// form reader the same shape cxWaiterOrderingSettings026K normalizes.
function segmentsContext() {
  const context = vm.createContext({ Array, String, Boolean });
  vm.runInContext(
    constBlock('CX_WO_SEGMENT_TYPES_031T')
      + fn('cxWaiterOrderingSegments031T')
      + fn('cxReadWaiterOrderingSegmentsFromForm031T'),
    context,
  );
  return context;
}

test('a brand new company (no segments key at all) has every segment disabled', () => {
  const ctx = segmentsContext();
  const segments = ctx.cxWaiterOrderingSegments031T(undefined);
  assert.deepEqual(JSON.parse(JSON.stringify(segments)), {
    mesero: { enabled: false, modules: [] },
    cocina: { enabled: false, modules: [] },
    caja: { enabled: false, modules: [] },
  });
});

test('an explicitly disabled segment stays disabled and keeps its modules list', () => {
  const ctx = segmentsContext();
  const segments = ctx.cxWaiterOrderingSegments031T({
    mesero: { enabled: true, modules: ["a", "b"] },
    cocina: { enabled: false },
  });
  assert.equal(segments.mesero.enabled, true);
  assert.deepEqual(Array.from(segments.mesero.modules), ["a", "b"]);
  assert.equal(segments.cocina.enabled, false);
  assert.equal(segments.caja.enabled, false);
});

test('reading the form only enables a segment whose checkbox was actually checked', () => {
  const ctx = segmentsContext();
  const segments = ctx.cxReadWaiterOrderingSegmentsFromForm031T({
    segment_mesero_enabled: "on",
    segment_mesero_modules: "inventario, kpis",
    // cocina/caja checkboxes absent -> unchecked, exactly what FormData gives for an unchecked box.
  });
  assert.equal(segments.mesero.enabled, true);
  assert.deepEqual(Array.from(segments.mesero.modules), ["inventario", "kpis"]);
  assert.equal(segments.cocina.enabled, false);
  assert.equal(segments.caja.enabled, false);
});
