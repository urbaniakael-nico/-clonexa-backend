// 063A: vista previa del portal para la Nómina EE. UU. por operación (us_payroll) con el
// tema de VOLTAGE (marca publicada: primario y texto blancos). Datos: la fixture real del
// servidor (Virginia, /__fix.json) + Alabama inventada. Sin servidor ni personas reales.
// ?open=1 abre una persona y luego otra (queda abierta la última) · ?modal=1 abre "confirmar salida" · ?q=texto busca ·
// ?filter=pending filtra. Mide textos que desbordan, contraste AA y que no aparezca nada
// de ubicación, mapa o notas; deja todo en <pre id="layout">.
(() => {
  const P = new URLSearchParams(location.search);
  const CID = "f1e8f774-f052-49ca-880a-268805f07db0";
  const BRANDING = { mode: "dark", theme_mode: "dark", font_family: "Poppins", primary_color: "#ffffff", text_color: "#ffffff", secondary_color: "#00ff9d",
    background_color: "#002e8a", gradient_from: "#f3f4f6", gradient_to: "#e5e7eb", background_mode: "gradient", card_style: "neon_border", visual_preset: "classic_office" };
  window.__CX_PORTAL_BRAND__ = { branding: BRANDING, pieces: {} };
  // Cada marco con su propia elección: no se guarda nada entre marcos.
  try {
    const set = Storage.prototype.setItem;
    Storage.prototype.setItem = function (k, v) { if (String(k).startsWith("cx_pv_us_063a")) return; return set.call(this, k, v); };
    localStorage.setItem("clonexa_access_token", "preview");
  } catch (_) {}

  const real = window.fetch.bind(window);
  const fixture = real("/__fix.json").then((r) => r.json());
  function alabama(id, name, doc, hours, rate) {
    const days = [2, 3, 4, 5, 6].map((d, i) => {
      const before = i * hours * 60;
      const reg = Math.max(0, Math.min(hours * 60, 2400 - before));
      return { date: `2026-11-0${d}`, payable: hours * 60, pause: 30, regular: reg, overtime: hours * 60 - reg };
    });
    const sum = (k) => days.reduce((s, d) => s + d[k], 0);
    const reg = sum("regular"); const ot = sum("overtime");
    const gross = rate ? Math.round((reg / 60 * rate + ot / 60 * rate * 1.5) * 100) / 100 : null;
    return { doc, row: { employee_id: id, employee_name: name, employee_role: "operario", closed_shifts: 5, regular_minutes: reg, extra_minutes: ot,
      gross_amount: gross || 0, discount_amount: 0, net_amount: gross || 0, rate_pending: !rate,
      shifts: days.map((d) => ({ start: `${d.date}T12:30:00Z`, end: `${new Date(Date.parse(`${d.date}T12:30:00Z`) + (d.payable + 30) * 60000).toISOString()}`, regular_minutes: d.regular,
        extra_minutes: d.overtime, pause_minutes: 30, connected_minutes: d.payable + 30, worked_minutes: d.payable, gross_amount: "0" })),
      us: { place: "Alabama", place_missing: false, tz: "America/Chicago", abbr: "CT", days_worked: 5, connected_minutes: sum("payable") + 150, pause_minutes: 150,
        payable_minutes: sum("payable"), regular_minutes: reg, overtime_minutes: ot, rate: rate || null, overtime_rate: rate ? rate * 1.5 : null, gross, deductions: 0, net: gross, rate_pending: !rate,
        weeks: [{ week_start: "2026-11-01", week_end: "2026-11-07", payable: sum("payable"), pause: 150, regular: reg, overtime: ot, days }] } } };
  }
  async function snapshot() {
    const s = JSON.parse(JSON.stringify((await fixture).snapshot));
    const extra = [alabama("al1", "Eduardo Pablo Lores Londres", "AL-4455", 9, 20), alabama("al2", "María José Hernández Castañeda de la Torre", "AL-7788", 8, 0),
      alabama("al3", "Luis Pérez", "", 7, 18.5)];
    extra.forEach((x) => s.rows.push(x.row));
    s.us_payroll.operations = [{ name: "Virginia", abbr: "ET", tz: "America/New_York" }, { name: "Alabama", abbr: "CT", tz: "America/Chicago" }];
    s.unverified_shifts = [{ employee_id: "al4", employee_name: "Óscar Peña", employee_role: "operario", place: "Alabama", abbr: "CT", source: "attendance", session_ref: "ci-9",
      closure_id: "cl-9", start: "2026-11-04T12:00:00Z", end: "2026-11-05T05:00:00Z", minutes: 900, status: "pending" },
    { employee_id: "emp-caso", employee_name: "Colaboradora Caso 2 Nov", employee_role: "operario", place: "Virginia", abbr: "ET", source: "attendance", session_ref: "ci-8",
      closure_id: "cl-8", start: "2026-11-03T11:00:00Z", end: "2026-11-04T04:00:00Z", minutes: 960, status: "pending" }];
    const t = s.totals;
    s.rows.slice(1).forEach((r) => { t.people += 1; t.regular_minutes += r.regular_minutes; t.extra_minutes += r.extra_minutes; t.payable_minutes += r.us.payable_minutes;
      t.pause_minutes += r.us.pause_minutes; t.connected_minutes += r.us.connected_minutes; t.gross_amount += r.gross_amount; t.net_amount += r.net_amount; });
    return { s, docs: { "emp-caso": "VA-1122", al1: "AL-4455", al2: "AL-7788" } };
  }

  const json = (b, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
  window.__pvCalls = [];
  window.fetch = async (url, opts) => {
    const u = String(url);
    if (!u.startsWith("/api/v1")) return real(url, opts);
    window.__pvCalls.push(u);
    const p = u.slice(7).split("?")[0];
    if (p.endsWith("/locale")) return json({ currency: "USD", timezone: "America/Chicago", language: "es", decimals: 2 });
    if (p === `/companies/${CID}`) return json({ id: CID, name: "VOLTAGE", slug: "voltage", status: "active" });
    if (p === `/companies/${CID}/experience`) return json({ company_id: CID, branding: BRANDING });
    if (p === `/companies/${CID}/modules`) return json([{ id: "cm1", company_id: CID, module_id: "m1", enabled: true,
      settings: { payroll_v2: true, us_payroll: true, us_payroll_rules: { week_start_day: "sunday", week_start_time: "00:00", overtime_after_minutes: 2400, overtime_factor: 1.5 } },
      module: { code: "payroll", name: "Nómina" } }]);
    if (p.endsWith("/period-config")) return json({ enabled: false });
    if (p.endsWith("/periods/calculate")) { const { s } = await snapshot(); return json(s); }
    if (p.endsWith("/period-activity")) { const { docs } = await snapshot(); return json({ modules: { gps: true, references: false, panels: false, orders: false }, documents: docs,
      gps: { "emp-caso": [{ at: "2026-11-02T11:46:00Z", lat: 38.9, lng: -77, perimeter: "", status: "Sin perímetro" }] }, references: {}, reference_closures: {}, panels: {} }); }
    if (p.endsWith("/closures/preview")) return json({ before: { regular_minutes: 2400, extra_minutes: 0, net_amount: 0 }, after: { regular_minutes: 2400, extra_minutes: 420, net_amount: 0 } });
    return json({});
  };

  // ---------------------------------------------------------------- medida
  function rgb(value) {
    const srgb = String(value || "").match(/color\(srgb ([^)]+)\)/);
    if (srgb) { const [r, g, b, a = 1] = srgb[1].split(/[ /]+/).filter(Boolean).map(Number); return { r: r * 255, g: g * 255, b: b * 255, a }; }
    const m = String(value || "").match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const [r, g, b, a = 1] = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
    return { r, g, b, a };
  }
  function lum({ r, g, b }) { const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); }
  function backgroundOf(el) {
    const layers = [];
    for (let node = el; node; node = node.parentElement) { const c = rgb(getComputedStyle(node).backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } }
    let base = { r: 255, g: 255, b: 255 };
    const stops = String(getComputedStyle(document.body).backgroundImage).match(/rgba?\([^)]+\)/g);
    if (stops && stops.length) base = rgb(stops[0]);
    for (let i = layers.length - 1; i >= 0; i -= 1) { const l = layers[i]; base = { r: l.r * l.a + base.r * (1 - l.a), g: l.g * l.a + base.g * (1 - l.a), b: l.b * l.a + base.b * (1 - l.a) }; }
    return base;
  }
  function ratio(el) { const fg = rgb(getComputedStyle(el).color); const bg = backgroundOf(el); const a = lum(fg) + 0.05; const b = lum(bg) + 0.05; return Math.round((Math.max(a, b) / Math.min(a, b)) * 100) / 100; }

  function measure() {
    const root = document.querySelector(".pvu-root");
    if (!root) { const out = document.createElement("pre"); out.id = "layout"; out.textContent = JSON.stringify({ mounted: false }); document.body.appendChild(out); return; }
    const bad = [];
    root.querySelectorAll("*").forEach((el) => {
      if (/^(INPUT|SELECT|TEXTAREA|OPTION)$/.test(el.tagName) || el.closest("svg")) return;
      if (el.offsetParent === null && getComputedStyle(el).position !== "fixed") return;
      if (el.closest(".pvu-table-wrap") && el !== el.closest(".pvu-table-wrap")) return; // la tabla se mide aparte (puede desplazarse a lo ancho en pantallas medianas)
      if (el.scrollWidth > el.clientWidth + 1) bad.push({ tag: el.tagName, cls: String(el.className || ""), text: (el.textContent || "").trim().slice(0, 40), sw: el.scrollWidth, cw: el.clientWidth });
    });
    // La tabla de cada operación cabe completa (sin barra de desplazamiento) a 1280 y a 390 px.
    root.querySelectorAll(".pvu-table-wrap").forEach((w) => { if (w.scrollWidth > w.clientWidth + 1) bad.push({ tag: "TABLE", cls: w.className, sw: w.scrollWidth, cw: w.clientWidth }); });
    const selectors = [".pvu-week", ".pvu-rule", ".pvu-count", ".pv-filter", ".pvu-sum-head h2", ".pvu-sum-head span", ".pvu-stat span", ".pvu-stat strong", ".pvu-table caption",
      ".pvu-table thead th", ".pvu-table td", ".pv-name", ".pvu-doc", ".pvu-pend", ".pvu-ot", ".pvu-chip", ".pvu-confirm", ".pvu-days caption", ".pvu-days th", ".pvu-days td",
      ".pvu-link", ".pvu-foot span", ".pvu-foot strong", ".pv-alert strong", ".pv-alert span", ".pv-kv dt", ".pv-kv dd", ".pv-preview-table td", ".pv-modal-head h2", ".pv-empty"];
    const low = [];
    selectors.forEach((sel) => root.querySelectorAll(sel).forEach((el) => {
      if (el.offsetParent === null && !el.closest(".pv-modal")) return;
      if (!(el.textContent || "").trim()) return;
      const r = ratio(el);
      if (r < 4.5) low.push({ sel, text: (el.textContent || "").trim().slice(0, 30), ratio: r });
    }));
    // Si la pagina se sale de ancho: los elementos mas profundos que pasan el borde (diagnostico).
    const wide = [];
    document.querySelectorAll("body *").forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.width && r.right > window.innerWidth + 1 && ![...el.children].some((c) => c.getBoundingClientRect().right > window.innerWidth + 1)) {
        wide.push({ tag: el.tagName, cls: String(el.className || "").slice(0, 40), text: (el.textContent || "").trim().slice(0, 40), right: Math.round(r.right), w: Math.round(r.width) });
      }
    });
    const text = root.textContent || "";
    const out = document.createElement("pre");
    out.id = "layout";
    out.textContent = JSON.stringify({ width: window.innerWidth, mounted: true, page_overflow: document.documentElement.scrollWidth > window.innerWidth + 1, wide: wide.slice(0, 8), bad, low_contrast: low,
      tables: root.querySelectorAll(".pvu-table").length, rows: root.querySelectorAll(".pvu-row").length, days: root.querySelectorAll(".pvu-days").length,
      banned: /Sin perímetro|Ver en el mapa|Resumen de la jornada|Etiquetado rack|Ubicación:/.test(text.replace("Ver ubicación y notas en Reportes", "")) || !!root.querySelector("a[href*='maps']"),
      count: (root.querySelector(".pvu-count") || {}).textContent || "", modal: !!root.querySelector(".pv-modal"), calls: window.__pvCalls });
    document.body.appendChild(out);
  }

  const go = () => {
    const btn = [...document.querySelectorAll(".client-nav button")].find((b) => /n[oó]mina|payroll/i.test(b.textContent));
    if (!btn) return setTimeout(go, 200);
    btn.click();
    const wait = () => {
      if (!document.querySelector(".pvu-root .pvu-row")) return setTimeout(wait, 200);
      const steps = [];
      if (P.get("open") === "1") steps.push(() => document.querySelector('[data-pvu-open="al2"]').click(), () => document.querySelector('[data-pvu-open="emp-caso"]').click());
      if (P.get("filter")) steps.push(() => document.querySelector(`[data-pvu-filter="${P.get("filter")}"]`).click());
      if (P.get("q")) steps.push(() => { const s = document.querySelector("[data-pv-search]"); s.value = P.get("q"); s.dispatchEvent(new Event("input", { bubbles: true })); });
      if (P.get("modal") === "1") steps.push(() => document.querySelector("[data-pv-confirm]").click(), () => {
        const input = document.querySelector("[data-pv-real-end]"); if (input) { input.value = "2026-11-04T15:00"; input.dispatchEvent(new Event("input", { bubbles: true })); }
        const note = document.querySelector("[data-pv-note]"); if (note) { note.value = "Olvidó marcar la salida"; note.dispatchEvent(new Event("input", { bubbles: true })); }
      });
      const run = (i) => { if (i >= steps.length) return setTimeout(measure, 1200); steps[i](); setTimeout(() => run(i + 1), 400); };
      run(0);
    };
    setTimeout(wait, 400);
  };
  window.addEventListener("load", () => setTimeout(go, 300));
})();
