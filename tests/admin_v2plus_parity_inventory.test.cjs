// Consola v2+ · inventario de paridad con Admin V2.
// Extrae de admin_v2.js TODAS las llamadas al servidor (apiGet/apiPost/apiPut/
// apiPatch/apiDelete, cxJsonRequest y fetch) y falla si alguna ruta no aparece
// en docs/consola_v2plus_paridad.md. Así ninguna función de v2 se pierde.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');

const V2 = readFileSync('app/web/admin_v2.js', 'utf8').replace(/\r\n/g, '\n');
const DOC = readFileSync('docs/consola_v2plus_paridad.md', 'utf8').replace(/\r\n/g, '\n');

const CALL = /\b(apiGet|apiPost|apiPut|apiPatch|apiDelete|cxJsonRequest|fetch)\(/g;
const METHOD_OF = { apiGet: 'GET', apiPost: 'POST', apiPut: 'PUT', apiPatch: 'PATCH', apiDelete: 'DELETE' };
// Envoltorios internos: reciben la ruta ya armada por quien los llama.
const WRAPPERS = new Set(['fetch(path)', 'fetch(`/api/v1{}`)']);

// Lee un literal (`…`, "…" o '…') que empieza en `i`; cambia cada ${…} por {}.
function readLiteral(src, i) {
  const quote = src[i];
  let out = '';
  let j = i + 1;
  while (j < src.length && src[j] !== quote) {
    if (quote === '`' && src[j] === '$' && src[j + 1] === '{') {
      let depth = 1;
      let k = j + 2;
      const start = k;
      while (k < src.length && depth) {
        if (src[k] === '{') depth += 1;
        else if (src[k] === '}') depth -= 1;
        k += 1;
      }
      const expr = src.slice(start, k - 1).trim();
      out += expr === 'API' ? '/api/v1' : '{}';
      j = k;
      continue;
    }
    if (src[j] === '\\') { out += src[j + 1]; j += 2; continue; }
    out += src[j];
    j += 1;
  }
  return { value: out, end: j + 1 };
}

function normalise(path) {
  return path.split('?')[0].replace(/\/+$/, '') || '/';
}

function extractCalls(src) {
  const calls = [];
  const skipped = [];
  let match;
  while ((match = CALL.exec(src))) {
    const fn = match[1];
    const before = src.slice(Math.max(0, match.index - 9), match.index);
    if (/function\s*$/.test(before)) continue; // definición, no llamada
    let i = CALL.lastIndex;
    while (/\s/.test(src[i])) i += 1;
    if (!['`', '"', "'"].includes(src[i])) {
      skipped.push(`${fn}(${src.slice(i).match(/^[\w.]+/)[0]})`);
      continue;
    }
    const literal = readLiteral(src, i);
    let path = literal.value;
    if (fn === 'cxJsonRequest') path = `/api/v1${path}`;
    if (!path.startsWith('/') || path === '/api/v1{}') { skipped.push(`${fn}(\`${path}\`)`); continue; }
    let method = METHOD_OF[fn];
    if (!method) {
      // fetch / cxJsonRequest: el método va en las opciones de esa misma llamada.
      const tail = src.slice(literal.end, literal.end + 400);
      const nextCall = tail.search(/\b(apiGet|apiPost|apiPut|apiPatch|cxJsonRequest|fetch)\(/);
      const options = nextCall >= 0 ? tail.slice(0, nextCall) : tail;
      const m = options.match(/method:\s*["'](GET|POST|PUT|PATCH|DELETE)["']/);
      method = m ? m[1] : 'GET';
    }
    calls.push({ fn, method, path: normalise(path), line: src.slice(0, match.index).split('\n').length });
  }
  return { calls, skipped };
}

// Solo la tabla de acciones de Admin V2 (las nuevas de v2+ van en otra sección).
function inventoryRows(doc) {
  const rows = [];
  const start = doc.indexOf('## Acciones con petición al servidor');
  const section = doc.slice(start, doc.indexOf('\n## ', start + 5));
  for (const line of section.split('\n')) {
    const cells = line.split('|').map((c) => c.trim());
    if (cells.length < 4 || !/^[A-Z]\d{2}$/.test(cells[1] || '')) continue;
    const request = (line.match(/`(GET|POST|PUT|PATCH|DELETE) (\/[^`\s]*)`/) || []);
    rows.push({ id: cells[1], method: request[1], path: request[2] ? normalise(request[2]) : null, status: cells[cells.length - 2] });
  }
  return rows;
}

test('el extractor encuentra las llamadas de Admin V2 y solo salta los envoltorios conocidos', () => {
  const { calls, skipped } = extractCalls(V2);
  assert.ok(calls.length >= 65, `solo ${calls.length} llamadas: el extractor dejó de ver admin_v2.js`);
  assert.deepEqual([...new Set(skipped)].sort(), [...WRAPPERS].sort(),
    'apareció una llamada con ruta dinámica: agrégala al inventario y a WRAPPERS solo si es un envoltorio');
  const sample = calls.map((c) => `${c.method} ${c.path}`);
  for (const expected of [
    'GET /api/v1/companies',
    'POST /api/v1/companies/{}/operational-reset',
    'PUT /api/v1/companies/{}/waiter-ordering/mesero-users/{}/daily-goal',
    'POST /api/v1/companies/{}/waiter-ordering/products/{}/image',
    'DELETE /api/v1/modules/{}',
    'POST /admin-v2/logout',
  ]) assert.ok(sample.includes(expected), `falta ${expected}`);
});

test('cada ruta de Admin V2 está en el inventario con el mismo método', () => {
  const { calls } = extractCalls(V2);
  const rows = inventoryRows(DOC);
  const known = new Set(rows.filter((r) => r.path).map((r) => `${r.method} ${r.path}`));
  const missing = calls.filter((c) => !known.has(`${c.method} ${c.path}`))
    .map((c) => `${c.method} ${c.path} (admin_v2.js:${c.line}, ${c.fn})`);
  assert.deepEqual([...new Set(missing)], [], 'rutas de Admin V2 sin fila en docs/consola_v2plus_paridad.md');
});

test('cada fila del inventario tiene un estado válido y nada sobra', () => {
  const rows = inventoryRows(DOC);
  const ids = rows.map((r) => r.id);
  assert.equal(new Set(ids).size, ids.length, 'IDs repetidos');
  const VALID = /^(migrado|pendiente · Fase \d|no aplica|no se migra a v2\+ · decisión del dueño)/;
  for (const r of rows) assert.match(r.status, VALID, `${r.id}: estado «${r.status}»`);
  const { calls } = extractCalls(V2);
  const used = new Set(calls.map((c) => `${c.method} ${c.path}`));
  const orphan = rows.filter((r) => r.path && !used.has(`${r.method} ${r.path}`)).map((r) => r.id);
  assert.deepEqual(orphan, [], 'filas del inventario que ya no existen en admin_v2.js');
});

test('pedidos por mesero (W01–W12) y N-14 no se migran: decisión del dueño', () => {
  const rows = inventoryRows(DOC);
  const w = rows.filter((r) => /^W\d{2}$/.test(r.id));
  assert.equal(w.length, 12);
  for (const r of w) assert.match(r.status, /^no se migra a v2\+ · decisión del dueño/, r.id);
  const n14 = DOC.split('\n').find((l) => l.startsWith('| N-14 |'));
  assert.match(n14, /no se migra a v2\+ · decisión del dueño/);
  const section = DOC.slice(DOC.indexOf('## Configuración que hoy solo existe en Admin V2'));
  assert.ok(DOC.includes('## Configuración que hoy solo existe en Admin V2'));
  for (const item of ['estación por categoría y por cocinero', 'meta diaria del mesero', 'grupos de porciones', 'cocina y cantidades']) {
    assert.ok(section.includes(item), `falta «${item}»`);
  }
});

module.exports = { extractCalls, inventoryRows };
