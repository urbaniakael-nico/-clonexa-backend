// Consola v2+ · Catálogo → "Palabras sin ícono" (galería de íconos de carta):
// por empresa, palabra y número de artículos, para decidir qué ícono agregar.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

function load(responder) {
  const calls = [];
  const fetch = async (url, options = {}) => {
    calls.push(url);
    const { status, body } = responder(url);
    return { status, ok: status >= 200 && status < 300, json: async () => body };
  };
  const window = { location: { href: '', origin: 'https://x' } };
  const ctx = vm.createContext({ window, document: {}, fetch, JSON, Object, Array, String, Number, Math, Promise, Error, Date, Map, Set, encodeURIComponent });
  vm.runInContext(readFileSync('app/web/admin_v2plus_catalog.js', 'utf8'), ctx);
  return { C: window.CxConsoleCatalog, calls, window };
}

test('pestaña "Palabras sin ícono": lista por empresa con palabra y artículos, texto escapado', async () => {
  const { C, calls } = load(() => ({ status: 200, body: { companies: [
    { company_id: 't', company_name: 'THE TIME MACHINE', words: [{ word: 'hookah', items: 3, last_seen: '2026-11-13T15:00:00' }, { word: 'cover<x>', items: 1, last_seen: null }] },
    { company_id: 'o', company_name: 'Otra', words: [{ word: 'cachimba', items: 1 }] }] } }));
  C.model.tab = 'iconos';
  await C.loadMisses079A();
  assert.equal(calls[0], '/api/v1/hospitality/admin/carta-iconos/palabras');
  const html = C.view();
  assert.match(html, /data-vpk-tab="iconos">Palabras sin ícono</);
  assert.match(html, /<h3>THE TIME MACHINE<\/h3>[\s\S]*<b>hookah<\/b><\/td><td>3 artículos<\/td><td>2026-11-13/);
  assert.match(html, /cover&lt;x&gt;[\s\S]*1 artículo</);
  assert.match(html, /<h3>Otra<\/h3>[\s\S]*cachimba/);
  assert.doesNotMatch(html, /cover<x>/);
});

test('sin palabras: aviso de que todos tienen su ícono; sin sesión Admin V2 lleva al ingreso', async () => {
  const empty = load(() => ({ status: 200, body: { companies: [] } }));
  empty.C.model.tab = 'iconos';
  await empty.C.loadMisses079A();
  assert.match(empty.C.view(), /Ninguna: todos los artículos tienen su ícono/);
  const out = load(() => ({ status: 401, body: { detail: 'admin_v2_session_required' } }));
  out.C.model.tab = 'iconos';
  await out.C.loadMisses079A();
  assert.match(out.C.view(), /admin_v2_session_required/);
});
