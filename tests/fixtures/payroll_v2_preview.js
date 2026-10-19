// Vista previa del portal para Nómina v2 (payroll_v2): datos de ejemplo (sin
// servidor ni personas reales) con el tema de VOLTAGE (marca publicada:
// primario y texto blancos), Velvet o ASADERO (marca publicada clara).
// ?theme=voltage|velvet|asadero · ?open=<id> despliega un registro ·
// ?modal=1 abre "confirmar salida". Al final mide textos que desbordan,
// contraste AA y el aislamiento por empresa, y deja todo en <pre id="layout">.
(() => {
  const P = new URLSearchParams(location.search);
  const THEMES = {
    voltage: { id: "76974191-1dc6-4eb4-9b19-7d1e9ad82946", name: "VOLTAGE", slug: "urban__demo",
      branding: { mode: "dark", theme_mode: "dark", font_family: "Poppins", primary_color: "#ffffff", text_color: "#ffffff", secondary_color: "#00ff9d",
        background_color: "#002e8a", gradient_from: "#f3f4f6", gradient_to: "#e5e7eb", background_mode: "gradient", card_style: "neon_border", visual_preset: "classic_office" }, published: true },
    velvet: { id: "d63cf68c-be5b-4a30-aee4-341973018db1", name: "Velvet", slug: "velvet",
      branding: { primary_color: "#a600ff", secondary_color: "#8cff00", background_color: "#00ffe1", text_color: "#000000", visual_preset: "custom", background_style: "holografico",
        background_mode: "gradient", surface_style: "glass", font_family: "Sora", card_style: "glass_premium", gradient_from: "#a600ff", gradient_to: "#8cff00", gradient_extra: "#00ffe1", gradient_angle: 135, mode: "dark", theme_mode: "dark" } },
    asadero: { id: "7625872c-f941-4479-a27b-f8443be953c5", name: "ASADERO EL SOCIO", slug: "asadero",
      branding: { mode: "light", theme_mode: "light", font_family: "Poppins", primary_color: "#8b1e2d", text_color: "#2b1d16", secondary_color: "#c9a227", background_color: "#f7f1e8",
        gradient_from: "#7ed4f1", gradient_to: "#ffcd94", background_mode: "gradient", card_style: "neon_border", visual_preset: "classic_office" }, published: true },
  };
  const KEY = P.get("theme") || "voltage";
  const T = THEMES[KEY];
  const CID = T.id;
  if (T.published && P.get("brand") !== "0") window.__CX_PORTAL_BRAND__ = { branding: T.branding, pieces: {} };

  const at = (d, hm) => new Date(`2026-10-${d}T${hm}:00-05:00`).toISOString();
  const shift = (d, a, b, reg, ext, gross, extra = {}) => ({ start: at(d, a), end: at(d, b), regular_minutes: reg, extra_minutes: ext, gross_amount: String(gross), pause_minutes: 30, ...extra });
  const person = (id, name, role, rate, shifts, extra = {}) => {
    const reg = shifts.reduce((s, x) => s + x.regular_minutes, 0);
    const ext = shifts.reduce((s, x) => s + x.extra_minutes, 0);
    const gross = shifts.reduce((s, x) => s + Number(x.gross_amount), 0);
    const discount = extra.discount || 0;
    return { employee_id: id, employee_name: name, employee_role: role, closed_shifts: shifts.length, regular_minutes: reg, extra_minutes: ext,
      hourly_rate_regular: rate, hourly_rate_extra: rate * 1.25, gross_amount: gross, discount_amount: discount, net_amount: gross - discount, shifts };
  };

  // Personas de ejemplo por empresa (inventadas).
  const DATA = {
    voltage: {
      rows: [
        person("v1", "Nicolás Gómez Restrepo", "Supervisor", 9000, [shift("05", "07:00", "16:30", 480, 60, 86250), shift("06", "07:10", "15:40", 480, 0, 72000)], { discount: 10000 }),
        person("v2", "Diana Directora (prueba)", "Director", 15000, [shift("05", "08:00", "17:00", 480, 30, 129375)]),
        person("v3", "Luis Logística (prueba)", "Logística", 8000, [shift("06", "06:00", "14:30", 480, 0, 64000)]),
        person("v4", "Olga Operaria (prueba)", "Operario", 7000, [shift("07", "07:00", "15:30", 480, 0, 56000)]),
        person("v5", "Óscar Otro (prueba)", "Otro", 6500, [shift("07", "09:00", "13:30", 240, 0, 26000)]),
      ],
      pending: { employee_id: "v4", employee_name: "Olga Operaria (prueba)", source: "attendance", session_ref: "ci-1", closure_id: "cl-1", start: at("08", "07:00"), end: at("09", "00:00"), minutes: 990, reason: "corte_diario", status: "pending" },
      activity: { modules: { gps: true, references: false, panels: false, orders: false }, documents: { v1: "1020304050", v2: "52123456" },
        gps: { v1: [{ at: at("05", "07:02"), lat: 4.6274, lng: -74.1317, perimeter: "EDIFICIO 1", status: "Dentro" }, { at: at("05", "12:00"), lat: 4.6275, lng: -74.1318, perimeter: "EDIFICIO 1", status: "Dentro" }],
          v3: [{ at: at("06", "06:05"), lat: 4.61, lng: -74.12, perimeter: "", status: "Fuera de los perímetros" }] },
        references: {}, reference_closures: {}, panels: {} },
    },
    velvet: {
      rows: [
        person("w1", "Camila Restrepo Vélez", "Operaria", 7500, [shift("05", "07:00", "16:00", 480, 30, 64688), shift("06", "07:00", "15:30", 480, 0, 60000)]),
        person("w2", "Laura Ospina", "Supervisora", 9000, [shift("05", "08:00", "17:00", 480, 0, 72000)]),
        person("w3", "Mateo Cárdenas", "Operario", 7500, [shift("06", "06:30", "15:00", 480, 0, 60000)]),
      ],
      pending: { employee_id: "w3", employee_name: "Mateo Cárdenas", source: "attendance", session_ref: "ci-2", closure_id: "cl-2", start: at("07", "06:30"), end: at("08", "00:00"), minutes: 1020, reason: "corte_diario", status: "pending" },
      activity: { modules: { gps: false, references: true, panels: false, orders: false }, documents: { w1: "1144556677" },
        gps: {}, references: { w1: [{ reference: "PANT SET Marfil", start: at("05", "07:15"), end: at("05", "11:40"), minutes: 265 }, { reference: "Mystic jacket", start: at("05", "12:30"), end: at("05", "15:50"), minutes: 200 }],
          w2: [{ reference: "Aurora Azul", start: at("05", "08:10"), end: at("05", "16:30"), minutes: 500 }] },
        reference_closures: { w1: [{ reference: "PANT SET Marfil", size: "10", quantity: 30, at: at("05", "11:40") }] }, panels: {} },
      cfg: { enabled: true, cutoff_days: [10, 25], auto_close: true, period: { period_start: "2026-09-26", period_end: "2026-10-10", headline: "Periodo del 26 sep al 10 oct", closed: false, auto_close_label: "corte automático el 11 oct a las 00:01" } },
    },
    asadero: {
      rows: [
        person("a1", "Jhon Mesero Ejemplo", "Mesero", 6500, [shift("05", "11:00", "20:00", 480, 30, 56063, { mini_panel_session_id: "s1", panel_type: "mesero" })]),
        person("a2", "Rosa Cocina Ejemplo", "Parrillero", 7000, [shift("05", "10:30", "19:30", 480, 30, 60375, { mini_panel_session_id: "s2", panel_type: "cocina" })]),
        person("a3", "Pedro Caja Ejemplo", "Cajero", 6800, [shift("05", "11:00", "21:00", 480, 90, 67150, { mini_panel_session_id: "s3", panel_type: "caja" })]),
        person("a4", "Ana Mesera Ejemplo", "Mesera", 6500, [shift("06", "12:00", "18:00", 330, 0, 35750, { mini_panel_session_id: "s4", panel_type: "mesero" })]),
      ],
      pending: { employee_id: "a4", employee_name: "Ana Mesera Ejemplo", source: "mini_panel", session_ref: "s5", closure_id: "cl-3", panel_type: "mesero", start: at("07", "12:00"), end: at("08", "00:00"), minutes: 720, reason: "corte_diario", status: "pending" },
      activity: { modules: { gps: false, references: false, panels: true, orders: true }, documents: {},
        gps: {}, references: {}, reference_closures: {},
        panels: { s1: { panel_type: "mesero", start: at("05", "11:00"), end: at("05", "20:00"), orders_taken: 23, orders_taken_total: 1186000, orders_ready: 0, charges: 0, charges_total: 0 },
          s2: { panel_type: "cocina", start: at("05", "10:30"), end: at("05", "19:30"), orders_taken: 0, orders_taken_total: 0, orders_ready: 41, charges: 0, charges_total: 0 },
          s3: { panel_type: "caja", start: at("05", "11:00"), end: at("05", "21:00"), orders_taken: 0, orders_taken_total: 0, orders_ready: 0, charges: 37, charges_total: 2104500 },
          s4: { panel_type: "mesero", start: at("06", "12:00"), end: at("06", "18:00"), orders_taken: 9, orders_taken_total: 402000, orders_ready: 0, charges: 0, charges_total: 0 } } },
    },
  };
  const D = DATA[KEY];
  if (P.get("list") === "1") D.activity.ui = { shift_list: true };  // payroll_shift_list
  const totals = D.rows.reduce((t, r) => ({ people: t.people + 1, regular_minutes: t.regular_minutes + r.regular_minutes, extra_minutes: t.extra_minutes + r.extra_minutes,
    gross_amount: t.gross_amount + r.gross_amount, discount_amount: t.discount_amount + r.discount_amount, net_amount: t.net_amount + r.net_amount }),
  { people: 0, regular_minutes: 0, extra_minutes: 0, gross_amount: 0, discount_amount: 0, net_amount: 0 });
  const period = D.cfg ? { from: D.cfg.period.period_start, to: D.cfg.period.period_end } : { from: "2026-10-01", to: "2026-10-15" };

  const json = (b, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
  const real = window.fetch.bind(window);
  window.__pvCalls = [];
  try { localStorage.setItem("clonexa_access_token", "preview"); } catch (_) {}
  window.fetch = async (url, opts) => {
    const u = String(url);
    if (!u.startsWith("/api/v1")) return real(url, opts);
    window.__pvCalls.push(u);
    const p = u.slice(7).split("?")[0];
    // Fase B: ?lang=en|fr simula una empresa en ese idioma (dólares y Chicago); sin lang, español, pesos y Bogotá.
    if (p.endsWith("/locale")) {
      const lang = new URLSearchParams(location.search).get("lang") || "es";
      return json(lang === "es" ? { currency: "COP", timezone: "America/Bogota", language: "es", decimals: 0 } : { currency: "USD", timezone: "America/Chicago", language: lang, decimals: 2 });
    }
    if (p === `/companies/${CID}`) return json({ id: CID, name: T.name, slug: T.slug, status: "active" });
    if (p === `/companies/${CID}/experience`) return json({ company_id: CID, branding: T.branding });
    if (p === `/companies/${CID}/modules`) return json([{ id: "cm1", company_id: CID, module_id: "m1", enabled: true, settings: P.get("v2") === "0" ? {} : { payroll_v2: true }, module: { code: "payroll", name: "Nómina" } }]);
    if (p.endsWith("/period-config")) return json(D.cfg || { enabled: false });
    if (p.endsWith("/periods/calculate")) return json({ period: { period_start: period.from, period_end: period.to, status: "open" }, rows: D.rows, totals, unverified_shifts: [D.pending], source: "calculated" });
    if (p.endsWith("/period-activity")) return json(D.activity);
    if (p.endsWith("/closures/preview")) {
      const row = D.rows.find((r) => r.employee_id === D.pending.employee_id);
      return json({ employee_id: row.employee_id, before: { regular_minutes: row.regular_minutes, extra_minutes: row.extra_minutes, net_amount: row.net_amount },
        after: { regular_minutes: row.regular_minutes + 480, extra_minutes: row.extra_minutes + 30, net_amount: row.net_amount + 60000 } });
    }
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
    const root = document.querySelector(".pv-root");
    const bad = [];
    root.querySelectorAll("*").forEach((el) => {
      if (el.tagName === "INPUT" && el.placeholder && !el.value && el.offsetParent !== null) {
        const ph = getComputedStyle(el, "::placeholder"); const cs = getComputedStyle(el);
        const c2 = (measure.c = measure.c || document.createElement("canvas")).getContext("2d");
        c2.font = `${ph.fontWeight || cs.fontWeight} ${ph.fontSize || cs.fontSize} ${cs.fontFamily}`;
        const need = c2.measureText(el.placeholder).width + parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
        if (need > el.clientWidth + 1) bad.push({ tag: "PLACEHOLDER", text: el.placeholder, sw: Math.ceil(need), cw: el.clientWidth });
      }
      if (/^(INPUT|SELECT|TEXTAREA|OPTION)$/.test(el.tagName) || el.closest("svg")) return;
      if (el.offsetParent === null && getComputedStyle(el).position !== "fixed") return;
      if (el.scrollWidth > el.clientWidth + 1) bad.push({ tag: el.tagName, cls: String(el.className || ""), text: (el.textContent || "").trim().slice(0, 40), sw: el.scrollWidth, cw: el.clientWidth });
    });
    const selectors = [".pv-status", ".pv-stat span", ".pv-stat strong", ".pv-filter", ".pv-name", ".pv-role", ".pv-time", ".pv-net", ".pv-flag", ".pv-avatar",
      ".pv-detail-head span", ".pv-shift-main span", ".pv-act span", ".pv-alert", ".pv-kv dt", ".pv-kv dd", ".pv-preview-table td", ".pv-modal-head h2"];
    const low = [];
    selectors.forEach((sel) => root.querySelectorAll(sel).forEach((el) => {
      if (el.offsetParent === null && !el.closest(".pv-modal")) return;
      const r = ratio(el);
      if (r < 4.5) low.push({ sel, text: (el.textContent || "").trim().slice(0, 30), ratio: r });
    }));
    const text = root.textContent || "";
    // Aislamiento: el detalle solo muestra lo de SU empresa.
    const shows = { gps: /Ubicación:|Ver en el mapa/.test(text), references: /Referencias:/.test(text), panels: /conexión \d|pedidos tomados|pedidos listos|cobros/.test(text) };
    const out = document.createElement("pre");
    out.id = "layout";
    out.textContent = JSON.stringify({ width: window.innerWidth, theme: KEY, mounted: true, page_overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
      bad, low_contrast: low, shows, cards: root.querySelectorAll(".pv-card").length, csv: /csv/i.test(text), calls: window.__pvCalls });
    document.body.appendChild(out);
  }

  const go = () => {
    const btn = [...document.querySelectorAll(".client-nav button")].find((b) => /n[oó]mina|payroll/i.test(b.textContent));
    if (!btn) return setTimeout(go, 200);
    btn.click();
    const wait = () => {
      if (!document.querySelector(".pv-root .pv-card")) return setTimeout(wait, 200);
      const open = P.get("open");
      if (open) { const card = document.querySelector(`[data-pv-card="${open}"]`); if (card) card.click(); }
      if (P.get("modal") === "1") {
        setTimeout(() => {
          const pend = document.querySelector(`[data-pv-card="${D.pending.employee_id}"]`);
          if (pend && pend.getAttribute("aria-expanded") !== "true") pend.click();
          setTimeout(() => {
            const b = document.querySelector("[data-pv-confirm]");
            if (b) b.click();
            setTimeout(() => {
              const input = document.querySelector("[data-pv-real-end]");
              if (input) { input.value = new Date(new Date(D.pending.start).getTime() + 9 * 3600000 - 5 * 3600000).toISOString().slice(0, 16); input.dispatchEvent(new Event("input", { bubbles: true })); }
              setTimeout(measure, 1200);
            }, 300);
          }, 300);
        }, 300);
        return;
      }
      setTimeout(measure, 1200);
    };
    setTimeout(wait, 400);
  };
  window.addEventListener("load", () => setTimeout(go, 300));
})();
