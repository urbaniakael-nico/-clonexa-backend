// Fase B · diccionario único del portal: español = texto base (sin cambios),
// si falta una traducción se ve el español (nunca una clave), y frases con
// números o partes separadas con "·" se traducen.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const WEB = path.join(__dirname, "..", "app", "web");

function load(language) {
  const window = { CxLocale: { loaded: true, language } };
  const document = { readyState: "complete", body: null, documentElement: null, addEventListener() {} };
  const ctx = vm.createContext({ window, document, setTimeout: () => 0, NodeFilter: {}, console });
  for (const f of ["client_i18n_dict.js", "client_i18n_core.js"]) vm.runInContext(fs.readFileSync(path.join(WEB, f), "utf8"), ctx);
  return window.CxI18n;
}

test("en español no traduce nada (regla de oro)", () => {
  const i18n = load("es");
  assert.equal(i18n.lang(), "es");
  assert.equal(i18n.lookup("Nómina"), null);
  assert.equal(i18n.t("Total a pagar"), "Total a pagar");
  assert.equal(i18n.locale(), "es-CO");
});

test("idioma desconocido o sin cargar: español", () => {
  assert.equal(load("pt").lang(), "es");
  assert.equal(load(undefined).lang(), "es");
});

test("inglés y francés traducen; si falta, el español (nunca la clave)", () => {
  const en = load("en");
  assert.equal(en.t("Total a pagar"), "Total to pay");
  assert.equal(en.t("Texto que nadie tradujo"), "Texto que nadie tradujo");
  assert.equal(en.locale(), "en-US");
  const fr = load("fr");
  assert.equal(fr.t("Nómina"), "Paie");
  assert.equal(fr.t("Hola {name}", { name: "Ana" }), "Hola Ana");
});

test("patrones con números y partes con ·", () => {
  const en = load("en");
  assert.equal(en.lookup("2 turnos"), "2 shifts");
  assert.equal(en.lookup("1 turno"), "1 shift");
  assert.equal(en.lookup("Periodo del 26 sep al 10 oct"), "Period from Sep 26 to Oct 10");
  assert.equal(en.lookup("Pantalón · Mujer · Talla 4 → 30"), "Pants · Women · Size 4 → 30");
  assert.equal(en.lookup("PANT SET · talla 10"), "PANT SET · size 10", "el nombre de la referencia no se toca");
  assert.equal(en.lookup("Velvet · Laura"), null, "solo datos: sin cambio");
  assert.equal(load("fr").lookup("⚠ 2 turnos por confirmar"), "⚠ 2 services à confirmer");
});

test("las páginas cargan el diccionario después de CxLocale", () => {
  for (const page of ["client.html", "mini_panel.html", "hsp_cashier.html", "hsp_waiter.html", "hsp_kitchen.html"]) {
    const html = fs.readFileSync(path.join(WEB, page), "utf8");
    const a = html.indexOf("client_locale.js"), b = html.indexOf("client_i18n_dict.js"), c = html.indexOf("client_i18n_core.js");
    assert.ok(a > 0 && a < b && b < c, page);
  }
});
