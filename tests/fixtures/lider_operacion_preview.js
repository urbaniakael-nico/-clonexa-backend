// 064B: vista previa del panel Líder de operación con el tema de VOLTAGE y datos inventados (la
// salida real del Board en reports_board_caso.json, solo Alabama). ?tab=login|inicio|crm|reportes,
// ?lang=es|en, ?op=0|1. Mide textos que desbordan, contraste AA y deja todo en <pre id="layout">.
(() => {
  const P = new URLSearchParams(location.search);
  const tab = P.get("tab") || "inicio";
  const accent = Number(P.get("op") || 1);
  const name = accent === 0 ? "Virginia" : "Alabama";
  window.__CX_LIDER__ = { ok: true, name, slug: name.toLowerCase(), accent, abbr: accent === 0 ? "ET" : "CT", timezone: accent === 0 ? "America/New_York" : "America/Chicago",
    brand: { font_family: "Poppins", primary_color: "#ffffff", text_color: "#ffffff", secondary_color: "#00ff9d", background_color: "#002e8a" } };
  Object.defineProperty(navigator, "geolocation", { value: { getCurrentPosition: (ok) => ok({ coords: { latitude: 32.3, longitude: -86.3, accuracy: 9 } }) } });
  const getItem = Storage.prototype.getItem;
  Storage.prototype.getItem = function (k) {
    if (k === "cx_lider_lang") return P.get("lang") || "es";
    if (String(k).startsWith("clonexa_mini_panel_token_")) return tab === "login" ? "" : "preview";
    return getItem.call(this, k);
  };
  Storage.prototype.setItem = function () {};
  const OP = { id: "op", name, code: name.slice(0, 2).toUpperCase(), timezone: window.__CX_LIDER__.timezone, abbr: window.__CX_LIDER__.abbr, accent, slug: name.toLowerCase(), local_time: "12:00", local_date: "2026-11-05" };
  const LONG = "Maximiliano Alejandro de la Santísima Trinidad Fernández-Montenegro";
  const STATES = [["working", 280], ["on_break", 20], ["no_shift"], ["to_confirm", 900], ["working", 45]];
  const PEOPLE = Array.from({ length: 25 }, (_, i) => {
    const [state, minutes] = STATES[i % STATES.length];
    return { id: `p${i}`, name: i === 3 ? LONG : `Persona de prueba ${String(i + 1).padStart(2, "0")}`, role: i % 7 === 0 ? "Supervisor" : "Operario", state, ...(minutes ? { minutes } : {}), can_finish: state === "working" || state === "on_break", origin: i % 2 ? "pin" : "app",
      ...(i % 10 === 2 ? { end: { t: "17:05", a: OP.abbr } } : {}),
      last_mark: i % 5 === 2 && i % 10 !== 2 ? null : { k: "in", label: "Entrada", t: "07:00", d: "2026-11-05", a: OP.abbr, place: i % 2 ? "Sin perímetro" : "Patio de almacenamiento principal número 3", s: i % 2 ? "unconfigured" : "inside" } };
  });
  const json = (b) => new Response(JSON.stringify(b), { status: 200, headers: { "content-type": "application/json" } });
  const real = window.fetch.bind(window);
  window.fetch = async (url, opts) => {
    const u = String(url);
    if (u.includes("/lider-operacion/") && u.includes("/inicio")) return json({ ok: true, company: "VOLTAGE", me: { name: "Alma Ruiz de la Torre Montenegro", role: "Supervisor" }, operation: OP,
      crm: { total: 25, working: 10, on_break: 5, no_shift: 5, to_confirm: 5 }, reports: { hours_minutes: 61250, alerts: 14, notes_today: 3, notes: 37, week: { start: "2026-11-01", end: "2026-11-07" } } });
    if (u.includes("/lider-operacion/") && u.includes("/crm")) return json({ ok: true, operation: OP, counts: { total: 25, working: 10, on_break: 5, no_shift: 5, to_confirm: 5 }, limit_hours: 15, people: PEOPLE });
    if (u.includes("/pin/verificar")) return json({ ok: true, employee: { name: LONG, role: "Operario", state: "on_break", actions: ["resume", "end"] } });
    if (u.includes("/lider-operacion/") && u.includes("/reportes")) {
      const fix = await (await real("/__fix.json")).json();
      fix.operations = fix.operations.filter((o) => o.name === name).map((o) => ({ ...o, color: accent, people: o.people.map(({ document, ...rest }) => rest) }));
      fix.scope = { limited: true, supervisor_no_place: false };
      fix.can_manage = false;
      fix.people_total = fix.operations[0].people.length;
      return json(fix);
    }
    return real(url, opts);
  };

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
    for (let i = layers.length - 1; i >= 0; i -= 1) { const l = layers[i]; base = { r: l.r * l.a + base.r * (1 - l.a), g: l.g * l.a + base.g * (1 - l.a), b: l.b * l.a + base.b * (1 - l.a) }; }
    return base;
  }
  function ratio(el) { const fg = rgb(getComputedStyle(el).color); const bg = backgroundOf(el); const a = lum(fg) + 0.05; const b = lum(bg) + 0.05; return Math.round((Math.max(a, b) / Math.min(a, b)) * 100) / 100; }

  function measure() {
    const root = document.querySelector(".lo-app");
    const out = document.createElement("pre");
    out.id = "layout";
    const bad = [];
    root.querySelectorAll("*").forEach((el) => {
      if (/^(INPUT|SELECT|TEXTAREA|OPTION)$/.test(el.tagName) || el.closest(".rb-tip") || el.offsetParent === null) return;
      if (el.closest(".rb-table-wrap") && el !== el.closest(".rb-table-wrap")) return;
      if (el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).display !== "inline") bad.push({ tag: el.tagName, cls: String(el.className || "").slice(0, 40), text: (el.textContent || "").trim().slice(0, 40) });
    });
    const low = [];
    root.querySelectorAll(".lo-head h1, .lo-kicker, .lo-lang button, .lo-card label, .lo-primary, .lo-bigclock strong, .lo-bigclock span, .lo-who, .lo-counter strong, .lo-counter span, .lo-module h3, .lo-module p, .lo-crm-top h2, .lo-chip, .lo-person b, .lo-person small, .lo-time, .lo-finish, .lo-pdf, .lo-state, .lo-pin-hint, .lo-key, .lo-note p, .lo-action, .lo-link, .lo-person-card h2, .lo-avatar, .lo-nav button, .client-title, .client-eyebrow, .rb-root .client-btn, .rb-fig span, .rb-fig strong, .rb-chip, .rb-table thead th, .rb-now").forEach((el) => {
      if (el.offsetParent === null || !(el.textContent || "").trim()) return;
      const r = ratio(el);
      if (r < 4.5) low.push({ cls: String(el.className || el.tagName), text: (el.textContent || "").trim().slice(0, 30), ratio: r });
    });
    const small = [...root.querySelectorAll(".lo-nav button, .lo-chip, .lo-lang button, .lo-primary, .lo-key, .lo-action, .lo-finish, .lo-pdf, .lo-link, .lo-counter")].filter((b) => b.offsetParent !== null && b.getBoundingClientRect().height < 44).map((b) => (b.textContent || "").trim());
    const nav = document.querySelector(".lo-nav");
    const cards = [...root.querySelectorAll(".lo-module")];
    const dotColor = (cls) => { const el = root.querySelector(`.lo-person.${cls} .lo-dot, .lo-counter.${cls} strong`); return el ? getComputedStyle(el)[el.tagName === "STRONG" ? "color" : "backgroundColor"] : ""; };
    out.textContent = JSON.stringify({ width: window.innerWidth, ready: true, tab, page_overflow: document.documentElement.scrollWidth > window.innerWidth + 1, bad, low_contrast: low, small,
      text: root.textContent.replace(/\s+/g, " ").slice(0, 5000), nav: nav ? [...nav.querySelectorAll("button")].map((b) => b.textContent.trim()) : [], modules: cards.length,
      side_by_side: cards.length === 3 && Math.abs(cards[0].getBoundingClientRect().top - cards[1].getBoundingClientRect().top) < 2,
      keys: root.querySelectorAll(".lo-key").length, actions: [...root.querySelectorAll(".lo-action")].map((b) => b.getAttribute("data-lo-punch")), finish_buttons: root.querySelectorAll(".lo-finish").length,
      semaforo: { working: dotColor("is-working"), on_break: dotColor("is-on_break"), to_confirm: dotColor("is-to_confirm"), no_shift: dotColor("is-no_shift") },
      body_bg: getComputedStyle(root).backgroundColor,
      people: root.querySelectorAll(".lo-person").length, board_rows: root.querySelectorAll(".rb-row").length, exports: root.querySelectorAll("[data-rb-export]").length,
      money: /\$|Bruto|Neto|Tarifa/.test(root.textContent), head_bg: nav ? getComputedStyle(document.querySelector(".lo-head")).backgroundColor : getComputedStyle(document.querySelector(".lo-head") || root).backgroundColor });
    document.body.appendChild(out);
  }

  const go = () => {
    if (tab === "login") return setTimeout(measure, 300);
    const wanted = tab === "pinp" ? "pin" : tab;
    const target = [...document.querySelectorAll(".lo-nav [data-lo-tab]")].find((b) => b.getAttribute("data-lo-tab") === wanted);
    if (!target) return setTimeout(go, 150);
    target.click();
    const wait = () => {
      if (tab === "reportes" && !document.querySelector(".rb-root .rb-row")) return setTimeout(wait, 150);
      if (tab === "crm" && !document.querySelector(".lo-person")) return setTimeout(wait, 150);
      if (tab === "inicio" && !document.querySelector(".lo-module")) return setTimeout(wait, 150);
      if ((tab === "pin" || tab === "pinp") && !document.querySelector(".lo-key")) return setTimeout(wait, 150);
      if (tab === "pinp" && !window.__pinTyped) {
        window.__pinTyped = true;
        for (const k of ["4", "8", "2", "7", "ok"]) document.querySelector(`[data-lo-key="${k}"]`).click();
        return setTimeout(measure, 700);
      }
      setTimeout(measure, 500);
    };
    setTimeout(wait, 200);
  };
  window.addEventListener("load", () => setTimeout(go, 200));
})();
