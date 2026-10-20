// Vista previa del CRM VELVET-LAB con datos de ejemplo (sin servidor ni personas
// reales). ?view=list|pin|nopin|person|refs|close|over|login|idle. Al final mide
// desbordes y contraste AA y deja el resultado en <pre id="layout">.
(() => {
  const P = new URLSearchParams(location.search);
  const VIEW = P.get("view") || "list";
  const CID = P.get("company_id") || "";
  const json = (b, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
  const real = window.fetch.bind(window);
  window.__crmCalls = [];
  const ago = (min) => new Date(Date.now() - min * 60000).toISOString();
  try {
    if (VIEW === "login") localStorage.removeItem(`clonexa_crm_lab_token_${CID}`);
    else localStorage.setItem(`clonexa_crm_lab_token_${CID}`, "preview");
  } catch (_) {}

  const people = [
    { employee_id: "e1", name: "Ana María Restrepo Villalobos", status: "working", has_pin: true, reference_name: "PANT SET", since: ago(83) },
    { employee_id: "e2", name: "Bea Gómez", status: "on_break", has_pin: true, reference_name: "Mystic jacket con capota larga", since: ago(12) },
    { employee_id: "e3", name: "Carla Díaz", status: "working", has_pin: true, reference_name: "Body básico", since: ago(140) },
    { employee_id: "e4", name: "Daniela Ruiz (prueba)", status: "sin_turno", has_pin: false, reference_name: null, since: null },
    { employee_id: "e5", name: "Eva Ríos", status: "sin_turno", has_pin: true, reference_name: null, since: null },
  ];
  const board = { now: new Date().toISOString(), working: 2, paused: 1, people, live: people.filter((p) => p.status !== "sin_turno"),
    brand: { name: "VELVET", logo_url: "", primary: "#b0126f", secondary: "#f5c2e7", language: "es", timezone: "America/Bogota" } };
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
      if (el.closest(".crm-ribbon") && (el.classList.contains("crm-ribbon") || getComputedStyle(el).textOverflow === "ellipsis")) return;  // la cinta se desliza; nombres largos con …
      if (el.scrollWidth > el.clientWidth + 1) bad.push({ tag: el.tagName, cls: String(el.className || ""), text: (el.textContent || "").trim().slice(0, 40), sw: el.scrollWidth, cw: el.clientWidth });
    });
    const low = [];
    root.querySelectorAll("h1, h2, h3, p, b, span, small, button, label, li").forEach((el) => {
      if (el.offsetParent === null && !el.closest(".crm-modal")) return;
      if (![...el.childNodes].some((n) => n.nodeType === 3 && n.nodeValue.trim())) return;
      if (el.closest(".crm-modal") && !el.closest(".crm-card")) return;
      const r = ratio(el);
      const big = parseFloat(getComputedStyle(el).fontSize) >= 24 || (parseFloat(getComputedStyle(el).fontSize) >= 18.66 && Number(getComputedStyle(el).fontWeight) >= 700);
      if (r < (big ? 3 : 4.5)) low.push({ tag: el.tagName, cls: String(el.className || ""), text: (el.textContent || "").trim().slice(0, 30), ratio: r });
    });
    const text = root.textContent || "";
    const out = document.createElement("pre");
    out.id = "layout";
    out.textContent = JSON.stringify({ mounted: true, view: VIEW, width: window.innerWidth, page_overflow: document.documentElement.scrollWidth > window.innerWidth + 1, bad, low_contrast: low,
      people: root.querySelectorAll("[data-crm-pick]").length, ribbon: root.querySelectorAll(".crm-ribbon li").length,
      counts: (root.querySelector(".crm-counts") || {}).textContent || "", pin_keys: root.querySelectorAll("[data-crm-key]").length,
      ask_admin: /Pide tu PIN al administrador/.test(text), actions: [...root.querySelectorAll("[data-crm-act]")].map((b) => b.textContent.trim()),
      sizes: [...root.querySelectorAll("[data-crm-size]")].map((b) => b.textContent.replace(/\s+/g, " ").trim()), refs: root.querySelectorAll("[data-crm-ref]").length,
      over: /Supera el pendiente de esa talla \(6\)/.test(text), login: !!root.querySelector("[data-crm-login]"), hm: (text.match(/\d+ h \d{2} min/) || [""])[0],
      per_person: /por persona/i.test(text), calls: window.__crmCalls, ...extra });
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
      const q = document.querySelector("[data-crm-qty]");
      if (q) { q.value = "7"; q.dispatchEvent(new Event("input", { bubbles: true })); }
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
