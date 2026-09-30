// 049Y: en Mini Paneles se muestra y se copia el link corto /c/CODIGO cuando
// el servidor lo habilita (interruptor short_links); si no, o si falla, queda
// el link largo de siempre.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/client.js', 'utf8');

function fn(name) {
  const start = source.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 3);
  const next = tail.search(/\n  \/\/ |\n  (?:async )?function |\n  let |\n  const |\n  document\.|\n  \/\* /);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

const LONG = 'https://clonexa.app/mini-panel/caja?company_id=co-1';

function card() {
  const box = { textContent: LONG, attrs: {}, setAttribute(k, v) { this.attrs[k] = v; } };
  const button = {
    isConnected: true, attrs: { 'data-minipanel-copy-link': LONG },
    getAttribute(k) { return this.attrs[k]; }, setAttribute(k, v) { this.attrs[k] = v; },
    closest: (sel) => (sel === '.cx-mini-link-card' ? { querySelector: (q) => (q === '.cx-mini-link-box' ? box : null) } : null),
  };
  return { box, button };
}

function ctx(apiImpl) {
  const { box, button } = card();
  const calls = [];
  const context = vm.createContext({
    Array, Set, String, JSON, encodeURIComponent, URL,
    state: { companyId: 'co-1' },
    window: { location: { origin: 'https://clonexa.app' } },
    document: { querySelectorAll: () => [button] },
    api: async (path, options) => { calls.push({ path, body: JSON.parse(options.body) }); return apiImpl(); },
  });
  vm.runInContext(fn('cxMiniPanelAbsoluteUrl019B') + fn('cxMiniPanelShortLinks049Y'), context);
  return { context, box, button, calls };
}

test('con el interruptor, la tarjeta muestra y copia el link corto', async () => {
  const t = ctx(() => ({ enabled: true, links: { [LONG]: '/c/K7PM2Q' } }));
  await t.context.cxMiniPanelShortLinks049Y();
  assert.equal(t.calls[0].path, '/short-links/companies/co-1/mini-panels');
  assert.deepEqual(t.calls[0].body, { links: [LONG] });
  assert.equal(t.box.textContent, 'https://clonexa.app/c/K7PM2Q');
  assert.equal(t.button.getAttribute('data-minipanel-copy-link'), 'https://clonexa.app/c/K7PM2Q');
  assert.equal(t.box.attrs.title, LONG, 'el largo queda como referencia');
});

test('sin el interruptor, queda el link largo', async () => {
  const t = ctx(() => ({ enabled: false, links: {} }));
  await t.context.cxMiniPanelShortLinks049Y();
  assert.equal(t.box.textContent, LONG);
  assert.equal(t.button.getAttribute('data-minipanel-copy-link'), LONG);
});

test('si el servidor falla, queda el link largo', async () => {
  const t = ctx(() => { throw new Error('500'); });
  await t.context.cxMiniPanelShortLinks049Y();
  assert.equal(t.button.getAttribute('data-minipanel-copy-link'), LONG);
});

test('Mini Paneles pide los cortos cada vez que se dibuja', () => {
  const render = source.slice(source.indexOf('async function renderMiniPanelLinksModule019B'), source.indexOf('/* CLONEXA_019B_CLIENT_MINI_PANEL_LINKS_END */'));
  assert.match(render, /cxMiniPanelShortLinks049Y\(\);/);
});
