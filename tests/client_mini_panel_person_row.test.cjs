const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/client.js', 'utf8');

function fn(name) {
  const start = source.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

function block(name) {
  // Grabs "const NAME = new Map();" style declarations that sit right above
  // a function of the same section (cxMiniPanelRowCredentials026J). Rewritten
  // to "var" so vm exposes it as a property on the context (a lexical const
  // declaration is not attached to the vm's global object).
  const start = source.search(new RegExp(`\\n  const ${name} = `));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
  const snippet = (next < 0 ? tail : tail.slice(0, next)) + '\n';
  return snippet.replace(/^const /, 'var ');
}

// cxMiniPanelPersonRow026J: the "Generar usuario y clave" button, the
// "Limite del plan alcanzado" disabled state, and the per-row credential
// block that shows the freshly created username/temp password once (never
// persisted -- the Map lives only in this module's memory).
function rowContext() {
  const context = vm.createContext({ Map, String, Boolean });
  vm.runInContext(
    `function h(v){ return String(v ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;"); }\n`
      + `function cxMiniPanelType026J(v){ return String(v||""); }\n`
      + `function cxMiniPanelEmployeeKey026J(e){ return String((e && (e.id || e.employee_id)) || "").trim(); }\n`
      + `function cxMiniPanelLink019B(){ return "/mini-panel/mesero?company_id=test-co"; }\n`
      + block('cxMiniPanelRowCredentials026J')
      + fn('cxMiniPanelPersonRow026J'),
    context,
  );
  return context;
}

const ITEM = { code: 'mesero', link: '/mini-panel/mesero?company_id=test-co' };

test('a candidate with no mini panel user yet gets the create button', () => {
  const ctx = rowContext();
  const html = ctx.cxMiniPanelPersonRow026J({ id: 'emp-1', full_name: 'Samuel', role: 'mesero' }, null, ITEM, false);
  assert.match(html, /data-minipanel-user-create="emp-1"/);
  assert.match(html, /data-minipanel-user-type="mesero"/);
  assert.match(html, /Generar usuario y clave/);
  assert.doesNotMatch(html, /Limite del plan alcanzado/);
});

test('once the segment limit is reached the button is disabled with the exact message', () => {
  const ctx = rowContext();
  const html = ctx.cxMiniPanelPersonRow026J({ id: 'emp-1', full_name: 'Samuel' }, null, ITEM, true);
  assert.match(html, /disabled>Limite del plan alcanzado<\/button>/);
  assert.doesNotMatch(html, /data-minipanel-user-create/);
});

test('an already-assigned person gets Regenerar clave instead of Generar usuario', () => {
  const ctx = rowContext();
  const html = ctx.cxMiniPanelPersonRow026J(
    { id: 'emp-1', full_name: 'Samuel' },
    { id: 'user-1', username: 'samuel.mesero', status: 'active' },
    ITEM, false,
  );
  assert.match(html, /data-minipanel-user-reset="user-1"/);
  assert.match(html, /Regenerar clave/);
  assert.doesNotMatch(html, /Generar usuario y clave/);
});

test('a just-created credential shows inline with a copy button and the "shown once" note', () => {
  const ctx = rowContext();
  ctx.cxMiniPanelRowCredentials026J.set('mesero:emp-1', { username: 'samuel.mesero', temporary_password: 'Ab12Cd34' });

  const html = ctx.cxMiniPanelPersonRow026J({ id: 'emp-1', full_name: 'Samuel' }, null, ITEM, false);

  assert.match(html, /samuel\.mesero/);
  assert.match(html, /Ab12Cd34/);
  assert.match(html, /data-minipanel-copy-credential="samuel\.mesero \/ Ab12Cd34"/);
  assert.match(html, /se muestra una sola vez/i);
  assert.match(html, /\/mini-panel\/mesero\?company_id=test-co/);
});

test('the credential is scoped to its own segment:employee key, not shared across cards', () => {
  const ctx = rowContext();
  ctx.cxMiniPanelRowCredentials026J.set('cocina:emp-1', { username: 'samuel.cocina', temporary_password: 'Xy98Zz11' });

  // Same employee, Meseros card this time -- must NOT show the cocina credential.
  const html = ctx.cxMiniPanelPersonRow026J({ id: 'emp-1', full_name: 'Samuel' }, null, ITEM, false);

  assert.doesNotMatch(html, /samuel\.cocina/);
  assert.doesNotMatch(html, /Xy98Zz11/);
});
