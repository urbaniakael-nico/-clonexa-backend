// Loads app/web/hsp_menu_kit.js (the menu pieces shared by the mesero and
// caja panels) in a vm context. Not a test file: node --test only runs
// *.test.cjs.
const { readFileSync } = require('node:fs');
const vm = require('node:vm');

const kitSource = readFileSync('app/web/hsp_menu_kit.js', 'utf8');

function loadKit(extraGlobals = {}) {
  const ctx = vm.createContext({ window: {}, Intl, Math, Number, String, Array, JSON, Set, Object, ...extraGlobals });
  vm.runInContext(kitSource, ctx);
  return ctx.window.CxMenuKit;
}

module.exports = { kitSource, loadKit };
