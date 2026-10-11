// Vista previa del portal para Personal (workforce_v2): datos de ejemplo (sin
// servidor ni usuarios reales) con el tema de Urbania o de la demo.
// ?v2=1 enciende el interruptor; ?roles=1 trae la configuracion de roles de
// Urbania. Al final mide textos que desbordan, contraste AA de titulos y
// celdas, y deja el resultado en <pre id="layout">.
(() => {
  const P = new URLSearchParams(location.search);
  const THEMES = {
    urbania: { name: "URBANIA", branding: { mode: "dark", card_style: "neon_border", text_color: "#ffffff", theme_mode: "dark", font_family: "Space Grotesk", gradient_to: "#e5e7eb", gradient_from: "#f3f4f6", primary_color: "#584b4b", surface_style: "neon", visual_preset: "classic_office", gradient_angle: 135, gradient_extra: "#d6d3d1", background_mode: "gradient", secondary_color: "#b45309", background_color: "#0055ff", background_style: "neutral_slate" } },
    demo: { name: "Radio Despecho", branding: { primary_color: "#38bdf8", secondary_color: "#f8fafc", background_color: "#0b1220", text_color: "#f8fafc", visual_preset: "boardroom_dark", background_style: "corporate_dark", background_mode: "gradient", surface_style: "neon", font_family: "Manrope", card_style: "neon_border", gradient_from: "#0f172a", gradient_to: "#164e63", gradient_extra: "#111827", gradient_angle: 140, mode: "corporate", theme_mode: "corporate" } },
    velvet: { name: "Velvet", branding: { primary_color: "#a600ff", secondary_color: "#8cff00", background_color: "#00ffe1", text_color: "#000000", visual_preset: "custom", background_style: "holografico", background_mode: "gradient", surface_style: "glass", font_family: "Sora", card_style: "glass_premium", gradient_from: "#a600ff", gradient_to: "#8cff00", gradient_extra: "#00ffe1", gradient_angle: 135, mode: "dark", theme_mode: "dark" } },
  };
  // Marca publicada de Urbania (Estudio de marca): primario y texto BLANCOS sobre fondo claro,
  // el caso que hoy deja los titulos de columna blanco sobre blanco.
  THEMES.urbania_marca = { name: "URBANIA", branding: { ...THEMES.urbania.branding, primary_color: "#ffffff", text_color: "#ffffff", secondary_color: "#00ff9d", background_color: "#88affb", font_family: "Poppins" } };
  const T = THEMES[P.get("theme") || "urbania"];
  if (P.get("theme") === "urbania_marca") window.__CX_PORTAL_BRAND__ = { branding: T.branding, pieces: {} };
  const CID = P.get("company_id") || "76974191-1dc6-4eb4-9b19-7d1e9ad82946";
  const V2 = P.get("v2") === "1";
  const ROLES = P.get("roles") === "1";
  const emp = (id, full_name, role, extra = {}) => ({ id, company_id: CID, full_name, role, employee_type: role, status: "active", phone: "", email: "",
    telegram_user_id: "", hire_date: "2026-01-15", hourly_rate_regular: 18, hourly_rate_extra: 24, deduction_1: 0, deduction_2: 0, ...extra });
  const employees = [
    emp("e1", "Nicolás Gómez Restrepo", "supervisor", { phone: "3001234567", email: "nicolas.gomez@urbania-demo.co", telegram_user_id: "700000001", deduction_1: 10 }),
    emp("e2", "Diana Director Ejemplo", "gerencia", { phone: "3002223344", email: "direccion@urbania-demo.co", hourly_rate_regular: 35, hourly_rate_extra: 45 }),
    emp("e3", "Luis Logística Prueba", "inventario", { phone: "3003334455", telegram_user_id: "700000003" }),
    emp("e4", "Olga Operaria Prueba", "operario", { phone: "3004445566", status: "inactive" }),
    emp("e5", "Óscar Otro Prueba", "otro", { email: "otro@urbania-demo.co" }),
    emp("e6", "Tatiana Técnico Antigua", "tecnico", { status: "archived" }),
  ];
  const roleConfig = { configured: true, roles: [{ code: "gerencia", label: "Director" }, { code: "supervisor", label: "Supervisor" },
    { code: "inventario", label: "Logística" }, { code: "operario", label: "Operario" }, { code: "otro", label: "Otro" }] };
  const json = (b) => new Response(JSON.stringify(b), { status: 200, headers: { "content-type": "application/json" } });
  const real = window.fetch.bind(window);
  try { localStorage.setItem("clonexa_access_token", "preview"); } catch (_) {}
  window.fetch = async (url, opts) => {
    const u = String(url);
    if (!u.startsWith("/api/v1")) return real(url, opts);
    const p = u.slice(7).split("?")[0];
    if (p === `/companies/${CID}`) return json({ id: CID, name: T.name, slug: "urban__demo", status: "active" });
    if (p === `/companies/${CID}/experience`) return json({ company_id: CID, branding: T.branding });
    if (p === `/companies/${CID}/modules`) return json([{ id: "cm1", company_id: CID, module_id: "m1", enabled: true, settings: V2 ? { workforce_v2: true } : {}, module: { code: "workforce", name: "Personal" } }]);
    if (p === `/employee-roles/companies/${CID}`) return json(ROLES ? roleConfig : { configured: false, roles: [] });
    if (p === "/employees") return json(employees);
    return json({});
  };

  // ---------------------------------------------------------------- medida
  function rgb(value) {
    const srgb = String(value || "").match(/color\(srgb ([^)]+)\)/);
    if (srgb) {
      const [r, g, b, a = 1] = srgb[1].split(/[ /]+/).filter(Boolean).map(Number);
      return { r: r * 255, g: g * 255, b: b * 255, a };
    }
    const m = String(value || "").match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const [r, g, b, a = 1] = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
    return { r, g, b, a };
  }
  function lum({ r, g, b }) {
    const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  }
  // Fondo efectivo: compone los fondos solidos de los ancestros sobre el fondo de la pagina.
  function backgroundOf(el) {
    const layers = [];
    for (let node = el; node; node = node.parentElement) {
      const c = rgb(getComputedStyle(node).backgroundColor);
      if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; }
    }
    let base = { r: 255, g: 255, b: 255 };
    const bodyImg = getComputedStyle(document.body).backgroundImage;
    const stops = String(bodyImg).match(/rgba?\([^)]+\)/g);
    if (stops && stops.length) base = rgb(stops[0]); // primer color del degradado de la pagina
    for (let i = layers.length - 1; i >= 0; i -= 1) {
      const l = layers[i];
      base = { r: l.r * l.a + base.r * (1 - l.a), g: l.g * l.a + base.g * (1 - l.a), b: l.b * l.a + base.b * (1 - l.a) };
    }
    return base;
  }
  function ratio(el) {
    const fg = rgb(getComputedStyle(el).color);
    const bg = backgroundOf(el);
    const a = lum(fg) + 0.05;
    const b = lum(bg) + 0.05;
    return Math.round((Math.max(a, b) / Math.min(a, b)) * 100) / 100;
  }

  function measure() {
    const root = document.querySelector(".wf-root") || document.querySelector(".client-main");
    const bad = [];
    root.querySelectorAll("*").forEach((el) => {
      // Texto de ayuda entero dentro de su campo vacio.
      if (el.tagName === "INPUT" && el.placeholder && !el.value && el.offsetParent !== null) {
        const ph = getComputedStyle(el, "::placeholder");
        const cs = getComputedStyle(el);
        const c2 = (measure.c = measure.c || document.createElement("canvas")).getContext("2d");
        c2.font = `${ph.fontWeight || cs.fontWeight} ${ph.fontSize || cs.fontSize} ${cs.fontFamily}`;
        const need = c2.measureText(el.placeholder).width + parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
        if (need > el.clientWidth + 1) bad.push({ tag: "PLACEHOLDER", text: el.placeholder, sw: Math.ceil(need), cw: el.clientWidth });
      }
      if (/^(INPUT|SELECT|TEXTAREA|OPTION)$/.test(el.tagName) || el.closest("svg")) return;
      if (el.offsetParent === null && getComputedStyle(el).position !== "fixed") return;
      if (el.scrollWidth > el.clientWidth + 1 && !el.classList.contains("wf-scroll")) {
        bad.push({ tag: el.tagName, cls: String(el.className || ""), text: (el.textContent || "").trim().slice(0, 40), sw: el.scrollWidth, cw: el.clientWidth });
      }
    });
    // Contraste AA de titulos de columna, cifras, filtros y textos de la tabla (o tarjetas).
    const selectors = [".wf-th", ".wf-group", ".wf-stat span", ".wf-stat strong", ".wf-filter", ".wf-name", ".wf-sub", ".wf-pill", ".wf-card-label", ".wf-role-text"];
    const low = [];
    selectors.forEach((sel) => root.querySelectorAll(sel).forEach((el) => {
      if (el.offsetParent === null) return;
      const r = ratio(el);
      if (r < 4.5) low.push({ sel, text: (el.textContent || "").trim().slice(0, 30), ratio: r });
    }));
    // La tabla cabe sin desplazamiento lateral (la clase wf-scroll es solo una red de seguridad).
    const wrap = root.querySelector(".wf-table-wrap");
    const tableScroll = Boolean(wrap && wrap.offsetParent !== null && wrap.scrollWidth > wrap.clientWidth + 1) && `${wrap.scrollWidth}>${wrap.clientWidth}: ${[...wrap.querySelectorAll("tbody tr:first-child td")].map((t) => Math.round(t.getBoundingClientRect().width)).join("+")}`;
    const roles = [...root.querySelectorAll(".wf-role-select")].slice(0, 1).map((s) => [...s.options].map((o) => o.textContent.trim()));
    const out = document.createElement("pre");
    out.id = "layout";
    out.textContent = JSON.stringify({ width: window.innerWidth, v2: V2, mounted: Boolean(document.querySelector(".wf-root")),
      page_overflow: document.documentElement.scrollWidth > window.innerWidth + 1, table_scroll: tableScroll, bad, low_contrast: low, role_options: roles[0] || [] });
    document.body.appendChild(out);
  }

  const go = () => {
    const btn = [...document.querySelectorAll(".client-nav button")].find((b) => /personal|workforce/i.test(b.textContent));
    if (!btn) return setTimeout(go, 200);
    btn.click();
    const wait = () => (document.querySelector(V2 ? ".wf-root .wf-table, .wf-root .wf-cards" : ".personal-grid") ? setTimeout(measure, 1500) : setTimeout(wait, 200));
    setTimeout(wait, 400);
  };
  window.addEventListener("load", () => setTimeout(go, 300));
})();
