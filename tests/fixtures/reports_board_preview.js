// 064A: vista previa del portal para el Board de gerencia con el tema de VOLTAGE (marca publicada).
// Datos: la salida real del servidor (/__fix.json, reports_board_caso.json, personas inventadas).
// ?open=1 abre una persona · ?q=texto busca · ?status=alerts filtra · ?off=1 interruptor apagado.
// Mide textos que desbordan, contraste AA y deja todo en <pre id="layout">.
(() => {
  const P = new URLSearchParams(location.search);
  const CID = "f1e8f774-f052-49ca-880a-268805f07db0";
  const BRANDING = { mode: "dark", theme_mode: "dark", font_family: "Poppins", primary_color: "#ffffff", text_color: "#ffffff", secondary_color: "#00ff9d",
    background_color: "#002e8a", gradient_from: "#f3f4f6", gradient_to: "#e5e7eb", background_mode: "gradient", card_style: "neon_border", visual_preset: "classic_office" };
  window.__CX_PORTAL_BRAND__ = { branding: BRANDING, pieces: {} };
  try {
    const set = Storage.prototype.setItem;
    Storage.prototype.setItem = function (k, v) { if (String(k).startsWith("cx_rb_064a")) return; return set.call(this, k, v); };
    localStorage.setItem("clonexa_access_token", "preview");
  } catch (_) {}
  const real = window.fetch.bind(window);
  const json = (b, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
  window.__rbCalls = [];
  window.fetch = async (url, opts) => {
    const u = String(url);
    if (!u.startsWith("/api/v1")) return real(url, opts);
    window.__rbCalls.push(u);
    const p = u.slice(7).split("?")[0];
    if (p.endsWith("/locale")) return json({ currency: "USD", timezone: "America/Chicago", language: "es", decimals: 2 });
    if (p === `/companies/${CID}`) return json({ id: CID, name: "VOLTAGE", slug: "voltage", status: "active" });
    if (p === `/companies/${CID}/experience`) return json({ company_id: CID, branding: BRANDING });
    if (p === `/companies/${CID}/modules`) return json([{ id: "cm1", company_id: CID, module_id: "m1", enabled: true, settings: { reports_v2: false, reports_board: P.get("off") !== "1" }, module: { code: "reports", name: "Reportes" } }]);
    if (p.startsWith("/reports-board/")) return json(await (await real("/__fix.json")).json());
    return json({});
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
    const stops = String(getComputedStyle(document.body).backgroundImage).match(/rgba?\([^)]+\)/g);
    if (stops && stops.length) base = rgb(stops[0]);
    for (let i = layers.length - 1; i >= 0; i -= 1) { const l = layers[i]; base = { r: l.r * l.a + base.r * (1 - l.a), g: l.g * l.a + base.g * (1 - l.a), b: l.b * l.a + base.b * (1 - l.a) }; }
    return base;
  }
  function ratio(el) { const fg = rgb(getComputedStyle(el).color); const bg = backgroundOf(el); const a = lum(fg) + 0.05; const b = lum(bg) + 0.05; return Math.round((Math.max(a, b) / Math.min(a, b)) * 100) / 100; }

  function measure() {
    const root = document.querySelector(".rb-root");
    const out = document.createElement("pre");
    out.id = "layout";
    if (!root) { out.textContent = JSON.stringify({ mounted: false, old: !!document.querySelector(".client-layout") }); document.body.appendChild(out); return; }
    const bad = [];
    root.querySelectorAll("*").forEach((el) => {
      if (/^(INPUT|SELECT|TEXTAREA|OPTION)$/.test(el.tagName) || el.closest(".rb-tip")) return;
      if (el.offsetParent === null) return;
      if (el.closest(".rb-table-wrap") && el !== el.closest(".rb-table-wrap")) return;
      if (el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).display !== "inline") bad.push({ tag: el.tagName, cls: String(el.className || ""), text: (el.textContent || "").trim().slice(0, 40), sw: el.scrollWidth, cw: el.clientWidth });
    });
    const selectors = [".client-title", ".client-eyebrow", ".rb-range", ".rb-root .client-btn", ".rb-primary", ".rb-fig span", ".rb-fig strong", ".rb-count", ".rb-chip", ".rb-sort", ".rb-block-head h2", ".rb-block-head p", ".rb-clock",
      ".rb-stats span", ".rb-stats strong", ".rb-block h3", ".rb-legend", ".rb-col small", ".rb-alerts b", ".rb-alerts span", ".rb-link", ".rb-table caption", ".rb-table thead th", ".rb-table td", ".rb-name", ".rb-doc", ".rb-hit",
      ".rb-now", ".rb-day h4", ".rb-mk", ".rb-geo", ".rb-map", ".rb-dur", ".rb-flag", ".rb-summary", ".rb-closed", ".rb-mats", ".rb-daytotal", ".rb-notes h2", ".rb-notes li", ".rb-root mark", ".rb-nogeo", ".rb-empty"];
    const low = [];
    selectors.forEach((sel) => root.querySelectorAll(sel).forEach((el) => {
      if (el.offsetParent === null || !(el.textContent || "").trim()) return;
      const r = ratio(el);
      if (r < 4.5) low.push({ sel, text: (el.textContent || "").trim().slice(0, 30), ratio: r });
    }));
    const wide = [];
    document.querySelectorAll("body *").forEach((el) => {
      const r = el.getBoundingClientRect();
      const reach = Math.max(r.right, r.left + el.scrollWidth);
      if (r.width && reach > document.documentElement.clientWidth + 1 && ![...el.children].some((c) => { const q = c.getBoundingClientRect(); return Math.max(q.right, q.left + c.scrollWidth) > document.documentElement.clientWidth + 1; })) {
        wide.push({ tag: el.tagName, cls: String(el.className || "").slice(0, 40), text: (el.textContent || "").trim().slice(0, 40), right: Math.round(r.right), reach: Math.round(reach) });
      }
    });
    const blocks = [...root.querySelectorAll(".rb-block")];
    const sideBySide = blocks.length >= 2 && Math.abs(blocks[0].getBoundingClientRect().top - blocks[1].getBoundingClientRect().top) < 2;
    const days = [...root.querySelectorAll(".rb-day")];
    const twoDays = days.length >= 2 && Math.abs(days[0].getBoundingClientRect().top - days[1].getBoundingClientRect().top) < 2;
    const wraps = [...root.querySelectorAll(".rb-table-wrap")].map((w) => ({ sw: w.scrollWidth, cw: w.clientWidth }));
    out.textContent = JSON.stringify({ width: window.innerWidth, mounted: true, page_overflow: document.documentElement.scrollWidth > window.innerWidth + 1, wide: wide.slice(0, 8), bad, low_contrast: low, wraps,
      blocks: blocks.length, side_by_side: sideBySide, two_days: twoDays, tables: root.querySelectorAll(".rb-table").length, rows: root.querySelectorAll(".rb-row").length, days: days.length,
      count: (root.querySelector("[data-rb-count]") || {}).textContent || "", text_money: /\$|Bruto|Neto|Tarifa/.test(root.textContent), old_list: /Semana laboral por persona/.test(root.textContent), calls: window.__rbCalls });
    document.body.appendChild(out);
  }

  const go = () => {
    const btn = [...document.querySelectorAll(".client-nav button, [data-client-module]")].find((b) => /reportes|reports/i.test(b.textContent || b.getAttribute("data-client-module") || ""));
    if (!btn) return setTimeout(go, 200);
    btn.click();
    if (P.get("off") === "1") return setTimeout(measure, 3000);
    const wait = () => {
      if (!document.querySelector(".rb-root .rb-row")) return setTimeout(wait, 200);
      const steps = [];
      if (P.get("open") === "1") steps.push(() => document.querySelector('.rb-who[data-rb-open="id-angela"]').click(), () => document.querySelector('.rb-who[data-rb-open="id-elena"]').click());
      if (P.get("status")) steps.push(() => document.querySelector(`[data-rb-status="${P.get("status")}"]`).click());
      if (P.get("q")) steps.push(() => { const s = document.querySelector("[data-rb-search]"); s.value = P.get("q"); s.dispatchEvent(new Event("input", { bubbles: true })); });
      const run = (i) => { if (i >= steps.length) return setTimeout(measure, 1000); steps[i](); setTimeout(() => run(i + 1), 300); };
      run(0);
    };
    setTimeout(wait, 400);
  };
  window.addEventListener("load", () => setTimeout(go, 300));
})();
