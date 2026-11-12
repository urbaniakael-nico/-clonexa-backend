// Vista previa del portal para Lugares de trabajo (work_locations): datos de
// ejemplo (sin servidor ni personas reales). ?screen=personal|crm, ?wl=1
// enciende el interruptor, ?theme=voltage|demo|velvet. 70 personas (Virginia,
// Alabama y algunas sin lugar). Al final mide desbordes, contraste AA y el
// acomodo de las secciones, y deja el resultado en <pre id="layout">.
(() => {
  const P = new URLSearchParams(location.search);
  const THEMES = {
    // Marca de VOLTAGE: texto blanco sobre fondo celeste (el par difícil para AA).
    voltage: { name: "VOLTAGE", branding: { primary_color: "#6395f2", secondary_color: "#f9a124", background_color: "#a8c5ff", text_color: "#ffffff", font_family: "Poppins",
      mode: "dark", theme_mode: "dark", card_style: "neon_border", background_mode: "gradient", gradient_from: "#f3f4f6", gradient_to: "#e5e7eb", gradient_extra: "#d6d3d1", gradient_angle: 135, background_style: "neutral_slate", surface_style: "neon", visual_preset: "custom" } },
    demo: { name: "Radio Despecho", branding: { primary_color: "#38bdf8", secondary_color: "#f8fafc", background_color: "#0b1220", text_color: "#f8fafc", visual_preset: "boardroom_dark", background_style: "corporate_dark", background_mode: "gradient", surface_style: "neon", font_family: "Manrope", card_style: "neon_border", gradient_from: "#0f172a", gradient_to: "#164e63", gradient_extra: "#111827", gradient_angle: 140, mode: "corporate", theme_mode: "corporate" } },
    velvet: { name: "Velvet", branding: { primary_color: "#a600ff", secondary_color: "#8cff00", background_color: "#00ffe1", text_color: "#000000", visual_preset: "custom", background_style: "holografico", background_mode: "gradient", surface_style: "glass", font_family: "Sora", card_style: "glass_premium", gradient_from: "#a600ff", gradient_to: "#8cff00", gradient_extra: "#00ffe1", gradient_angle: 135, mode: "dark", theme_mode: "dark" } },
  };
  const T = THEMES[P.get("theme") || "voltage"];
  if (P.get("theme") === "voltage") window.__CX_PORTAL_BRAND__ = { branding: T.branding, pieces: {} };
  const CID = P.get("company_id") || "f1e8f774-f052-49ca-880a-268805f07db0";
  const WL = P.get("wl") === "1";
  const SCREEN = P.get("screen") || "personal";
  const FIRST = ["Andrea", "Bruno", "Camila", "Diego", "Elena", "Felipe", "Gabriela", "Hugo", "Isabel", "Julián", "Karen", "Luis", "María José", "Nicolás", "Olga"];
  const LAST = ["Ramírez", "Gómez", "Restrepo", "Hernández", "Washington", "Montgomery", "Rodríguez Villalobos"];
  const places = [
    { id: "va", name: "Virginia", code: "VA", timezone: "America/New_York", is_active: true, sort_order: 1 },
    { id: "al", name: "Alabama", code: "AL", timezone: "America/Chicago", is_active: true, sort_order: 2 },
  ];
  const employees = [];
  const assignments = {};
  for (let i = 0; i < 70; i += 1) {
    const id = `e${i}`;
    const role = i % 17 === 0 ? "supervisor" : i === 1 ? "gerencia" : "operario";
    employees.push({ id, company_id: CID, full_name: `${FIRST[i % FIRST.length]} ${LAST[i % LAST.length]} ${i}`, role, employee_type: role, status: i % 23 === 5 ? "inactive" : "active",
      phone: `30012345${String(i).padStart(2, "0")}`, email: `persona${i}@voltage-demo.us`, telegram_user_id: `7000${i}`, hire_date: "2026-01-15",
      hourly_rate_regular: 18, hourly_rate_extra: 24, deduction_1: i % 4 ? 0 : 10, deduction_2: 0 });
    assignments[id] = i % 10 === 9 ? null : i % 2 ? "al" : "va";
  }
  const statuses = ["working", "working", "on_break", "sin_turno", "working", "checked_out"];
  const gpsPlaces = ["inside", "outside", "none", "inside", "unconfigured"];
  const rowOf = (e, i) => ({ employee_id: e.id, employee_name: e.full_name, employee_role: e.role === "supervisor" ? "Supervisor" : e.role === "gerencia" ? "Director" : "Operario",
    work_location_id: assignments[e.id], is_supervisor: e.role === "supervisor", gps_place: gpsPlaces[i % gpsPlaces.length],
    gps: gpsPlaces[i % gpsPlaces.length] === "none" ? null : { gps_status: gpsPlaces[i % gpsPlaces.length], zone_name: "Planta", coordinates: "37.5, -77.4" },
    core: { status: statuses[i % statuses.length], status_label: "", shift_effective_seconds: 3600 + i * 97, current_pause_seconds: 300, pause_accumulated_seconds: 300 },
    adapters: [{ code: "gps", title: "GPS", enabled: true, items: [] }] });
  function board() {
    const rows = employees.filter((e) => e.status === "active").map(rowOf);
    const order = { working: 0, on_break: 1 };
    const sort = (list) => list.slice().sort((a, b) => ((order[a.core.status] ?? 2) - (order[b.core.status] ?? 2)) || a.employee_name.localeCompare(b.employee_name, "es"));
    const counts = (list) => ({ total: list.length, working: list.filter((r) => r.core.status === "working").length, on_break: list.filter((r) => r.core.status === "on_break").length,
      no_shift: list.filter((r) => !["working", "on_break"].includes(r.core.status)).length, in_perimeter: list.filter((r) => r.gps_place === "inside").length });
    const group = (key, name, code, tz, list) => ({ key, name, code, timezone: tz, is_active: true, supervisors: list.filter((r) => r.is_supervisor).map((r) => r.employee_name), counts: counts(list), people: sort(list) });
    const all = counts(rows);
    return { ok: true, active_modules: ["crm", "gps", "materials", "workforce"], locations: places,
      summary: { employees_total: all.total, active_now: all.working, on_break: all.on_break, out: all.no_shift, gps_adapter: true, gps_inside: all.in_perimeter, materials_adapter: true },
      groups: [group("va", "Virginia", "VA", "America/New_York", rows.filter((r) => r.work_location_id === "va")),
        group("al", "Alabama", "AL", "America/Chicago", rows.filter((r) => r.work_location_id === "al")),
        group("none", "Sin asignar", null, null, rows.filter((r) => !r.work_location_id))] };
  }
  const json = (b, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
  const real = window.fetch.bind(window);
  try { localStorage.setItem("clonexa_access_token", "preview"); localStorage.removeItem(`cx_crm_place_${CID}`); } catch (_) {}
  const mod = (code, name, settings = {}) => ({ id: `cm-${code}`, company_id: CID, module_id: `m-${code}`, enabled: true, settings, module: { code, name } });
  window.fetch = async (url, opts) => {
    const u = String(url);
    if (!u.startsWith("/api/v1")) return real(url, opts);
    const p = u.slice(7).split("?")[0];
    if (p.endsWith("/locale")) return json({ currency: "USD", timezone: "America/New_York", language: "es", decimals: 2 });
    if (p === `/companies/${CID}`) return json({ id: CID, name: T.name, slug: "voltage_operation", status: "active" });
    if (p === `/companies/${CID}/experience`) return json({ company_id: CID, branding: T.branding });
    if (p === `/companies/${CID}/modules`) return json([mod("workforce", "Personal", { workforce_v2: true, ...(WL ? { work_locations: true } : {}) }), mod("crm", "CRM Campo"), mod("gps", "GPS"), mod("materials", "Materiales")]);
    if (p === `/employee-roles/companies/${CID}`) return json({ configured: false, roles: [] });
    if (p === "/employees") return json(employees);
    if (p === `/work-locations/companies/${CID}`) return WL ? json({ ok: true, locations: places, assignments, can_manage: true, can_assign: true }) : json({ detail: "off" }, 404);
    if (p === `/work-locations/companies/${CID}/board`) return WL ? json(board()) : json({ detail: "off" }, 404);
    if (p.startsWith("/crm-core-v1/companies/") && p.endsWith("/snapshot")) {
      const b = board();
      return json({ ok: true, active_modules: b.active_modules, summary: b.summary, employees: b.groups.flatMap((g) => g.people).slice(0, 8) });
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
  function ratio(el) {
    const fg = rgb(getComputedStyle(el).color);
    const bg = backgroundOf(el);
    const a = lum(fg) + 0.05;
    const b = lum(bg) + 0.05;
    return Math.round((Math.max(a, b) / Math.min(a, b)) * 100) / 100;
  }

  const SELECTORS = {
    personal: [".wf-th", ".wf-group", ".wf-stat span", ".wf-stat strong", ".wf-filter", ".wf-name", ".wf-sub", ".wf-pill", ".wf-card-label", ".wf-role-text", ".wf-place", ".wf-selbar strong"],
    crm: [".cxp-tab", ".cxp-name", ".cxp-role", ".cxp-chip", ".cxp-time", ".cxp-gps", ".cxp-kpi span", ".cxp-kpi strong", ".cxp-sec-head h3", ".cxp-clock span", ".cxp-clock strong", ".cxp-sup"],
  };

  function measure() {
    const root = document.querySelector(".wf-root") || document.querySelector(".cxp-root") || document.querySelector(".client-main");
    const bad = [];
    root.querySelectorAll("*").forEach((el) => {
      if (/^(INPUT|SELECT|TEXTAREA|OPTION)$/.test(el.tagName) || el.closest("svg")) return;
      if (el.offsetParent === null && getComputedStyle(el).position !== "fixed") return;
      if (el.scrollWidth > el.clientWidth + 1 && !el.classList.contains("wf-scroll")) bad.push({ tag: el.tagName, cls: String(el.className || ""), text: (el.textContent || "").trim().slice(0, 40), sw: el.scrollWidth, cw: el.clientWidth });
    });
    const low = [];
    SELECTORS[SCREEN].forEach((sel) => root.querySelectorAll(sel).forEach((el) => {
      if (el.offsetParent === null) return;
      const r = ratio(el);
      if (r < 4.5) low.push({ sel, text: (el.textContent || "").trim().slice(0, 30), ratio: r });
    }));
    const wrap = root.querySelector(".wf-table-wrap");
    const tableScroll = Boolean(wrap && wrap.offsetParent !== null && wrap.scrollWidth > wrap.clientWidth + 1) && `${wrap.scrollWidth}>${wrap.clientWidth}: ${[...wrap.querySelectorAll("tbody tr:first-child td")].map((t) => Math.round(t.getBoundingClientRect().width)).join("+")}`;
    const secs = [...document.querySelectorAll(".cxp-sec")].map((s) => { const r = s.getBoundingClientRect(); return { top: Math.round(r.top), left: Math.round(r.left) }; });
    const out = document.createElement("pre");
    out.id = "layout";
    out.textContent = JSON.stringify({ width: window.innerWidth, wl: WL, screen: SCREEN,
      mounted: Boolean(SCREEN === "personal" ? document.querySelector(".wf-root") : (WL ? document.querySelector(".cxp-root .cxp-sec") : document.querySelector(".cx-crm-people-grid"))),
      places_ui: Boolean(document.querySelector(".wf-place, .cxp-root")), legacy_crm: Boolean(document.querySelector(".cx-crm-people-grid")),
      rows: document.querySelectorAll(".cxp-row").length, sections: secs, tabs: [...document.querySelectorAll(".cxp-tab")].map((b) => b.textContent.trim()),
      page_overflow: document.documentElement.scrollWidth > window.innerWidth + 1, table_scroll: tableScroll, bad, low_contrast: low });
    document.body.appendChild(out);
  }

  const go = () => {
    const btn = [...document.querySelectorAll(".client-nav button, .cxop-card-078a[data-client-module]")].map((b) => b.querySelector("strong") || b).find((b) => (SCREEN === "crm" ? /crm/i : /personal|workforce/i).test(b.textContent));
    if (!btn) return setTimeout(go, 200);
    btn.click();
    const ready = SCREEN === "personal" ? ".wf-root .wf-table, .wf-root .wf-cards" : (WL ? ".cxp-root .cxp-sec" : ".cx-crm-people-grid, .personal-empty");
    const wait = () => (document.querySelector(ready) ? setTimeout(() => {
      // Personal: marcar dos personas para medir también la barra de selección.
      if (SCREEN === "personal" && WL) { [...document.querySelectorAll("[data-wf2-pick]")].slice(0, 2).forEach((b) => b.click()); }
      setTimeout(measure, 900);
    }, 900) : setTimeout(wait, 200));
    setTimeout(wait, 400);
  };
  window.addEventListener("load", () => setTimeout(go, 300));
})();
