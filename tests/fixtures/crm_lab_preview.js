// Vista previa del CRM VELVET-LAB con datos de ejemplo (sin servidor ni personas
// reales). ?view=list|pin|nopin|person|refs|close|over|login|idle|start|startpick|startpin
// y ?theme=velvet|otro. Al final mide desbordes, contraste AA, scroll de la página,
// lo que queda dentro de la pantalla y los colores, y lo deja en <pre id="layout">.
(() => {
  const P = new URLSearchParams(location.search);
  const VIEW = P.get("view") || "list";
  const THEME = P.get("theme") || "velvet";
  if (P.get("fs") === "0") {  // navegador sin Fullscreen API (ni la variante webkit)
    for (const k of ["fullscreenEnabled", "webkitFullscreenEnabled"]) Object.defineProperty(Document.prototype, k, { configurable: true, get: () => false });
  }
  const CID = P.get("company_id") || "";
  const json = (b, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
  const real = window.fetch.bind(window);
  window.__crmCalls = [];
  const ago = (min) => new Date(Date.now() - min * 60000).toISOString();
  try {
    if (VIEW === "login") localStorage.removeItem(`clonexa_crm_lab_token_${CID}`);
    else localStorage.setItem(`clonexa_crm_lab_token_${CID}`, "preview");
  } catch (_) {}

  // Tema como lo arma el servidor (crm_lab.theme): Velvet (marca guardada: holografico,
  // fondo aqua, principal morado) y otro tema oscuro para ver que el CRM cambia de color.
  const THEMES = {
    velvet: { background: "radial-gradient(circle at 0% 0%, #a600ff88, transparent 32%), radial-gradient(circle at 100% 0%, #8cff0066, transparent 34%), radial-gradient(circle at 50% 100%, #00ffe188, transparent 40%), linear-gradient(135deg, #00ffe1, #a600ff)",
      primary: "#a600ff", secondary: "#8cff00", bg: "#00ffe1", text: "#000000", warning: "", font: "Sora, Arial Black, system-ui, sans-serif" },
    otro: { background: "linear-gradient(135deg, #050509, #1d4ed8)", primary: "#1d4ed8", secondary: "#f97316", bg: "#050509", text: "#f8fafc", warning: "#eab308", font: "Inter, system-ui, sans-serif" },
  };
  const people = [
    { employee_id: "e1", name: "Ana María Restrepo Villalobos", status: "working", has_pin: true, reference_name: "PANT SET", since: ago(83),
      // 056L: tiempos del servidor (trabajado = conectado - pausas; referencia actual y anterior)
      connected_seconds: 14400, pause_seconds: 2100, worked_seconds: 12300, current_pause_seconds: null, reference_started_at: ago(70),
      reference_worked_seconds: 4200, previous_reference: { name: "Mystic jacket con capota larga", worked_seconds: 4800 } },
    { employee_id: "e2", name: "Bea Gómez", status: "on_break", has_pin: true, reference_name: "Mystic jacket con capota larga", since: ago(52), paused_since: ago(12),
      connected_seconds: 3120, pause_seconds: 3120 - 2400, worked_seconds: 2400, current_pause_seconds: 720, reference_started_at: ago(52),
      reference_worked_seconds: 2400, previous_reference: null },
    { employee_id: "e3", name: "Carla Díaz", status: "working", has_pin: true, reference_name: "Body básico", since: ago(140) },
    { employee_id: "e4", name: "Daniela Ruiz (prueba)", status: "sin_turno", has_pin: false, reference_name: null, since: null },
    { employee_id: "e5", name: "Eva Ríos", status: "sin_turno", has_pin: true, reference_name: null, since: null },
    ...["Fabiola", "Gina", "Helena", "Irene", "Juana", "Karen", "Laura"].map((name, i) => ({ employee_id: `x${i}`, name, status: "sin_turno", has_pin: true, reference_name: null, since: null })),
  ].reverse();  // el servidor ordena por nombre; la pantalla ordena por estado
  const board = { now: new Date().toISOString(), working: 2, paused: 1, people, live: people.filter((p) => p.status !== "sin_turno"),
    brand: { name: "VELVET", logo_url: "", primary: "#b0126f", secondary: "#f5c2e7", language: "es", timezone: "America/Bogota", theme: THEMES[THEME] } };
  const sizes = [
    { reference_id: "r-s", name: "PANT SET", size: "S", pending: 12, meta: 30 },
    { reference_id: "r-m", name: "PANT SET", size: "M", pending: 6, meta: 30 },
    { reference_id: "r-l", name: "PANT SET", size: "L", pending: 0, meta: 20 },
  ];
  const person = { employee_id: "e1", name: "Ana María Restrepo Villalobos", status: "working", reference: { id: "r-s", name: "PANT SET", started_at: ago(83) }, sizes };
  const refs = ["Body básico", "Mystic jacket con capota larga", "PANT SET", "Short denim", "Top encaje"].map((name, i) => ({ id: `ref-${i}`, name, sizes_count: 3, pending: [12, 0, 48, 7, 130][i] }));
  // 056J: ?view=start|startpick · persona SIN turno: primero la referencia.
  const fresh = { employee_id: "e5", name: "Eva Ríos", status: "sin_turno", reference: null, sizes: [] };

  window.fetch = async (url, opts = {}) => {
    const u = String(url);
    if (!u.includes("/api/v1/")) return real(url, opts);
    window.__crmCalls.push(`${opts.method || "GET"} ${u.replace(/.*\/api\/v1/, "")}`);
    if (u.includes("/board")) return json(board);
    if (u.includes("/references")) return json({ items: refs });
    if (u.includes("/unlock")) return json({ employee_token: "emp", person: VIEW.startsWith("start") ? fresh : person });
    if (u.includes("/action")) {
      const body = JSON.parse(opts.body || "{}");
      if (VIEW === "over" && body.action === "close" && !body.confirm) return json({ detail: { code: "supera_el_pendiente", pending: 6 } }, 409);
      return json(person);
    }
    if (u.includes("/mini-panel-login")) return json({ access_token: "x", user: {} });
    return json({ detail: "no" }, 404);
  };

  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const click = (sel) => { const el = document.querySelector(sel); if (el) el.click(); return !!el; };
  const until = async (sel, ms = 4000) => { const end = Date.now() + ms; while (!document.querySelector(sel) && Date.now() < end) await wait(25); return !!document.querySelector(sel); };

  function rgb(v) { const m = String(v || "").match(/rgba?\(([^)]+)\)/); if (!m) return null; const [r, g, b, a = 1] = m[1].split(",").map((x) => parseFloat(x)); return { r, g, b, a }; }
  function lum({ r, g, b }) { const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); }
  function backgroundOf(el) {
    const layers = [];
    for (let node = el; node; node = node.parentElement) { const c = rgb(getComputedStyle(node).backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } }
    let base = { r: 15, g: 17, b: 23 };
    for (let i = layers.length - 1; i >= 0; i -= 1) { const l = layers[i]; base = { r: l.r * l.a + base.r * (1 - l.a), g: l.g * l.a + base.g * (1 - l.a), b: l.b * l.a + base.b * (1 - l.a) }; }
    return base;
  }
  function ratio(el) { const fg = rgb(getComputedStyle(el).color); const bg = backgroundOf(el); const a = lum(fg) + 0.05; const b = lum(bg) + 0.05; return Math.round((Math.max(a, b) / Math.min(a, b)) * 100) / 100; }

  function measure(extra) {
    const root = document.getElementById("crmApp");
    const bad = [];
    root.querySelectorAll("*").forEach((el) => {
      if (/^(INPUT|SELECT|OPTION)$/.test(el.tagName)) return;
      if (el.offsetParent === null && getComputedStyle(el).position !== "fixed") return;
      if (getComputedStyle(el).textOverflow === "ellipsis" || getComputedStyle(el).webkitLineClamp !== "none" && getComputedStyle(el).webkitLineClamp) return;  // recortes a propósito con …
      if (el.scrollWidth > el.clientWidth + 1) bad.push({ tag: el.tagName, cls: String(el.className || ""), text: (el.textContent || "").trim().slice(0, 40), sw: el.scrollWidth, cw: el.clientWidth });
    });
    const low = [];
    root.querySelectorAll("h1, h2, h3, p, b, span, small, button, label, li").forEach((el) => {
      if (el.offsetParent === null && !el.closest(".crm-modal")) return;
      if (![...el.childNodes].some((n) => n.nodeType === 3 && n.nodeValue.trim())) return;
      if (el.closest(".crm-modal") && !el.closest(".crm-win")) return;
      const r = ratio(el);
      const big = parseFloat(getComputedStyle(el).fontSize) >= 24 || (parseFloat(getComputedStyle(el).fontSize) >= 18.66 && Number(getComputedStyle(el).fontWeight) >= 700);
      if (r < (big ? 3 : 4.5)) low.push({ tag: el.tagName, cls: String(el.className || ""), text: (el.textContent || "").trim().slice(0, 30), ratio: r });
    });
    const text = root.textContent || "";
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const inside = (el) => { if (!el) return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.top >= -1 && r.left >= -1 && r.bottom <= vh + 1 && r.right <= vw + 1; };
    const keys = [...document.querySelectorAll("[data-crm-key], [data-crm-qkey], [data-crm-closego].crm-key")];
    const tiles = [...root.querySelectorAll(".crm-tile")];
    const bgOf = (sel) => { const el = root.querySelector(sel); return el ? getComputedStyle(el).backgroundColor : ""; };
    const grid = root.querySelector(".crm-grid");
    const firstTop = tiles.length ? tiles[0].getBoundingClientRect().top : 0;
    const top = root.querySelector(".crm-top");
    const out = document.createElement("pre");
    out.id = "layout";
    out.textContent = JSON.stringify({ mounted: true, view: VIEW, width: window.innerWidth, page_overflow: document.documentElement.scrollWidth > window.innerWidth + 1, bad, low_contrast: low,
      people: root.querySelectorAll("[data-crm-pick]").length, ribbon: root.querySelectorAll(".crm-ribbon li").length,
      counts: (root.querySelector(".crm-counts") || {}).textContent || "", pin_keys: root.querySelectorAll("[data-crm-key]").length,
      ask_admin: /Pide tu PIN al administrador/.test(text), actions: [...root.querySelectorAll("[data-crm-act]")].map((b) => b.textContent.trim()),
      sizes: [...root.querySelectorAll("[data-crm-size]")].map((b) => b.textContent.replace(/\s+/g, " ").trim()), refs: root.querySelectorAll("[data-crm-ref]").length,
      over: /Supera el pendiente de esa talla \(6\)/.test(text), login: !!root.querySelector("[data-crm-login]"), hm: (text.match(/\d+ h \d{2} min/) || [""])[0],
      per_person: /por persona/i.test(text), calls: window.__crmCalls,
      page_scroll: document.documentElement.scrollHeight > vh + 1 || document.documentElement.scrollWidth > vw + 1 || document.scrollingElement.scrollTop > 0,
      top_visible: inside(top), fs_button: !!root.querySelector("[data-crm-fs]"),
      keys: keys.length, keys_visible: keys.filter((k) => inside(k) && k.getBoundingClientRect().height >= 47.5).length,
      zero_visible: inside(document.querySelector('[data-crm-key="0"], [data-crm-qkey="0"]')),
      tiles: tiles.map((t) => `${t.className.replace("crm-tile ", "")}|${t.querySelector(".crm-name").textContent}`),
      columns: new Set(tiles.filter((t) => Math.abs(t.getBoundingClientRect().top - firstTop) < 2).map((t) => Math.round(t.getBoundingClientRect().left))).size,
      grid_scrolls: !!grid && grid.scrollHeight > grid.clientHeight + 1 && getComputedStyle(grid).overflowY === "auto",
      colors: { working: bgOf(".crm-tile.is-working"), on_break: bgOf(".crm-tile.is-on_break"), sin_turno: bgOf(".crm-tile.is-sin_turno"), bar: bgOf(".crm-top") },
      squashed: [...root.querySelectorAll(".crm-tile > *, .crm-win h2, .crm-refopt > *")].filter((el) => el.getBoundingClientRect().height < parseFloat(getComputedStyle(el).fontSize) * 1.05)
        .map((el) => `${el.className || el.tagName}:${el.textContent.trim().slice(0, 20)}:${Math.round(el.getBoundingClientRect().height)}`),
      spill: [...root.querySelectorAll(".crm-tile > *, .crm-refopt > *")].filter((el) => { const b = el.parentElement.getBoundingClientRect(); const r = el.getBoundingClientRect(); return r.bottom > b.bottom + 0.5 || r.right > b.right + 0.5; })
        .map((el) => `${el.className}:${el.textContent.trim().slice(0, 20)}`),
      clock: ((root.querySelector(".crm-tile.is-working .crm-clock") || {}).textContent || ""),
      chips: [...root.querySelectorAll(".crm-chip")].map((c) => c.textContent.replace(/\s+/g, " ").trim()),
      refs_visible: [...document.querySelectorAll("[data-crm-startref], [data-crm-ref]")].filter(inside).length,
      startgo_visible: inside(document.querySelector("[data-crm-startgo]")),
      acts_visible: [...document.querySelectorAll("[data-crm-act]")].filter(inside).length,
      win_visible: inside(document.querySelector(".crm-win")), ...extra });
    document.body.appendChild(out);
  }

  window.addEventListener("load", async () => {
    await until("[data-crm-pick], [data-crm-login]");
    let extra = {};
    if (VIEW === "pin") { click('[data-crm-pick="e1"]'); await wait(50); click('[data-crm-key="1"]'); click('[data-crm-key="2"]'); }
    if (VIEW === "nopin") click('[data-crm-pick="e4"]');
    if (VIEW === "startpin") { click('[data-crm-pick="e5"]'); await wait(50); click('[data-crm-key="1"]'); }
    if (["person", "refs", "close", "over", "idle"].includes(VIEW)) {
      click('[data-crm-pick="e1"]');
      for (const k of ["1", "2", "3", "4"]) { await until(`[data-crm-key="${k}"]:not([disabled])`); click(`[data-crm-key="${k}"]`); }
      await until(".crm-personal");
      await until('[data-crm-act]:not([disabled])');
    }
    if (VIEW === "refs") { click('[data-crm-act="pick_switch"]'); await until("[data-crm-ref]"); }
    if (VIEW === "start" || VIEW === "startpick") {
      click('[data-crm-pick="e5"]');
      await until(".crm-steps");
      extra.pin_steps = !!document.querySelector('.crm-steps li.is-on[aria-current="step"]');
      for (const k of ["1", "2", "3", "4"]) { await until(`[data-crm-key="${k}"]:not([disabled])`); click(`[data-crm-key="${k}"]`); }
      await until("[data-crm-startref]");
      extra.start_disabled = !!document.querySelector("[data-crm-startgo][disabled]");
      if (VIEW === "startpick") { click('[data-crm-startref="ref-1"]'); await until("[data-crm-startgo]:not([disabled])"); extra.start_label = document.querySelector("[data-crm-startgo]").textContent.trim(); }
    }
    if (VIEW === "close" || VIEW === "over") {
      click('[data-crm-act="pick_close"]');
      await until('[data-crm-size="r-m"]');
      click('[data-crm-size="r-m"]');
      await until('[data-crm-size="r-m"].is-on');
      click('[data-crm-qkey="7"]');
      await until('[data-crm-qtyshow]');
      extra.qty = document.querySelector("[data-crm-qtyshow]").textContent;
      if (VIEW === "over") { await until("[data-crm-closego]:not([disabled])"); click("[data-crm-closego]"); await until(".crm-warn"); }
    }
    if (VIEW === "idle") {
      extra.before_idle = !!document.querySelector(".crm-personal");
      window.CxCrmLab.st.lastTouch = Date.now() - 21000;  // 21 s sin tocar
      await wait(1300);
      extra.back_to_list = !!document.querySelector("[data-crm-pick]") && !document.querySelector(".crm-personal");
      extra.employee_token_cleared = window.CxCrmLab.st.empToken === "";
    }
    await wait(300);
    measure(extra);
  });
})();
