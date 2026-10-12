// Moneda, zona horaria e idioma de la empresa en el portal: UN solo
// formateador (Fase A). Se carga una vez al entrar (GET /companies/{id}/locale,
// con sesión). Regla de oro: con COP (todas las empresas vivas salvo VOLTAGE)
// cada lugar sigue usando su formato de siempre; solo con otra moneda se usa
// el formato de esa moneda. Fechas y horas: siempre en la zona de la empresa.
(() => {
  "use strict";

  const DECIMALS = { COP: 0, CLP: 0, USD: 2, EUR: 2, MXN: 2, PEN: 2 };
  const state = { currency: "COP", timezone: "America/Bogota", language: "es", decimals: 0, loaded: false, companyId: "" };
  let loading = null;

  function apply(data) {
    const cur = String((data && data.currency) || "COP").toUpperCase();
    state.currency = cur in DECIMALS ? cur : "COP";
    state.decimals = DECIMALS[state.currency];
    state.timezone = String((data && data.timezone) || "America/Bogota");
    state.language = String((data && data.language) || "es");
    state.loaded = true;
  }

  // Carga una vez por empresa. Si falla, todo queda como siempre (COP y Bogotá).
  function load(companyId, getJson) {
    if (!companyId) return Promise.resolve(state);
    if (state.companyId === companyId && (state.loaded || loading)) return loading || Promise.resolve(state);
    state.companyId = companyId;
    loading = Promise.resolve()
      .then(() => getJson(`/companies/${encodeURIComponent(companyId)}/locale`))
      .then((data) => { apply(data); return state; })
      .catch(() => { apply({}); return state; })
      .finally(() => { loading = null; });
    return loading;
  }

  // ¿La empresa usa otra moneda que no es COP? Solo entonces cambian los formatos.
  const foreign = () => state.currency !== "COP";

  function group(value, decimals, thousands, point) {
    const n = Number(value);
    const fixed = (Number.isFinite(n) ? Math.abs(n) : 0).toFixed(decimals);
    const [whole, frac] = fixed.split(".");
    const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, thousands);
    return `${Number.isFinite(n) && n < 0 ? "-" : ""}${grouped}${decimals ? point + frac : ""}`;
  }

  // Dinero: con COP y un formato de siempre (legacy), exactamente ese texto.
  function money(value, legacy) {
    const cur = state.currency;
    if (cur === "COP" && typeof legacy === "function") return legacy(value);
    const d = DECIMALS[cur] ?? 2;
    if (cur === "USD" || cur === "MXN") { const t = group(value, d, ",", "."); return t.startsWith("-") ? `-$${t.slice(1)}` : `$${t}`; }
    if (cur === "EUR") return `${group(value, d, ".", ",")} €`;
    if (cur === "PEN") return `S/ ${group(value, d, ",", ".")}`;
    return `$ ${group(value, d, ".", ",")}`; // COP, CLP: "$ 1.234"
  }

  function number(value, decimals = 0) {
    const usd = state.currency === "USD" || state.currency === "MXN" || state.currency === "PEN";
    return group(value, decimals, usd ? "," : ".", usd ? "." : ",");
  }

  // Cifra escrita por una persona -> número. Misma regla que el servidor
  // (company_locale.parse_amount): "1.234,50" (COP) y "1,234.50" (USD) -> 1234.5.
  function parse(raw, currency = state.currency) {
    if (typeof raw === "number") return Number.isFinite(raw) ? raw : 0;
    let text = String(raw ?? "").replace(/[^\d,.-]/g, "");
    if (!text) return 0;
    const neg = text.startsWith("-");
    text = text.replace(/-/g, "");
    const lastDot = text.lastIndexOf(".");
    const lastComma = text.lastIndexOf(",");
    let dec = null;
    if (lastDot >= 0 && lastComma >= 0) dec = lastDot > lastComma ? "." : ",";
    else if (lastDot >= 0 || lastComma >= 0) {
      const sep = lastDot >= 0 ? "." : ",";
      const groupSep = ["USD", "MXN", "PEN"].includes(String(currency).toUpperCase()) ? "," : ".";
      const tail = text.slice(text.lastIndexOf(sep) + 1);
      const repeated = text.indexOf(sep) !== text.lastIndexOf(sep);
      dec = repeated || (tail.length === 3 && sep === groupSep) ? null : sep;
    }
    let n;
    if (dec) {
      const i = text.lastIndexOf(dec);
      n = Number(`${text.slice(0, i).replace(/[.,]/g, "") || "0"}.${text.slice(i + 1) || "0"}`);
    } else n = Number(text.replace(/[.,]/g, ""));
    if (!Number.isFinite(n)) return 0;
    return neg ? -n : n;
  }

  // Partes de fecha/hora en la zona de la empresa.
  function parts(value) {
    const d = value instanceof Date ? value : new Date(value || "");
    if (Number.isNaN(d.getTime())) return null;
    const f = new Intl.DateTimeFormat("sv-SE", { timeZone: state.timezone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(d);
    const [date, time] = f.split(" ");
    return { date, time, local: `${date}T${time}` };
  }
  const dayKey = (value = new Date()) => (parts(value) || {}).date || "";
  function dateTime(value, options = {}, locale = "es-CO") {
    const d = value instanceof Date ? value : new Date(value || "");
    if (Number.isNaN(d.getTime())) return "";
    return new Intl.DateTimeFormat(locale, { ...options, timeZone: state.timezone }).format(d);
  }

  // Minutos de diferencia de la zona de la empresa con UTC en ese instante (cambia con el horario de verano).
  function offsetMinutes(at) {
    const p = parts(at);
    if (!p) return 0;
    const [y, mo, d] = p.date.split("-").map(Number);
    const [hh, mm] = p.time.split(":").map(Number);
    return Math.round((Date.UTC(y, mo - 1, d, hh, mm) - Math.floor(at.getTime() / 60000) * 60000) / 60000);
  }
  // Instante UTC en que empieza (o termina) un día "AAAA-MM-DD" en la zona de la empresa.
  function dayBoundUtc(day, end = false) {
    const [y, mo, d] = String(day || "").split("-").map(Number);
    if (!y || !mo || !d) return null;
    const wall = end ? Date.UTC(y, mo - 1, d, 23, 59, 59, 999) : Date.UTC(y, mo - 1, d, 0, 0, 0, 0);
    let guess = new Date(wall);
    for (let i = 0; i < 3; i += 1) guess = new Date(wall - offsetMinutes(guess) * 60000);
    return guess.toISOString();
  }

  // Filtros de días del portal: el día y sus límites en la zona de la empresa.
  // Fase B: todas las empresas cortan a medianoche de su zona (en la Fase A
  // Bogotá seguía en UTC por la regla de oro; el cambio de cifras es a propósito).
  const localDays = () => true;
  const filterDay = (value) => (localDays() ? dayKey(value) : "");
  const filterBound = (day, end = false) => (localDays() ? dayBoundUtc(day, end) : null);

  window.CxLocale = {
    load, apply, money, number, parse, parts, dayKey, dateTime, foreign, offsetMinutes, dayBoundUtc, filterDay, filterBound, localDays,
    get currency() { return state.currency; }, get timezone() { return state.timezone; },
    get language() { return state.language; }, get decimals() { return state.decimals; }, get loaded() { return state.loaded; },
  };
})();
