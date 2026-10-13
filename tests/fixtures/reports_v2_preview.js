// Vista previa de Reportes v2 (interruptor reports_v2) con datos de ejemplo
// (sin servidor ni personas reales), con el tema de VOLTAGE (marca publicada).
// El payload sale de tests/fixtures/reports_v2_payload.json (generado con la
// misma build_insights del servidor). ?lang=en simula la empresa en inglés.
// Al final mide desbordes y contraste AA y deja el resultado en <pre id="layout">.
(() => {
  const P = new URLSearchParams(location.search);
  const CID = P.get("company_id");
  const LANG = P.get("lang") || "es";
  const branding = { mode: "dark", theme_mode: "dark", font_family: "Poppins", primary_color: "#ffffff", text_color: "#ffffff", secondary_color: "#00ff9d",
    background_color: "#002e8a", gradient_from: "#f3f4f6", gradient_to: "#e5e7eb", background_mode: "gradient", card_style: "neon_border", visual_preset: "classic_office" };
  // Sin marca publicada: el portal aplica la marca de la empresa (variables --cx-* en :root).
  const json = (b, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
  const real = window.fetch.bind(window);
  window.__rrCalls = [];
  try { localStorage.setItem("clonexa_access_token", "preview"); } catch (_) {}
  let payload = null;
  window.fetch = async (url, opts) => {
    const u = String(url);
    if (!u.startsWith("/api/v1")) return real(url, opts);
    window.__rrCalls.push(u);
    const p = u.slice(7).split("?")[0];
    if (p.endsWith("/locale")) return json({ currency: "USD", timezone: "America/Chicago", language: LANG, decimals: 2 });
    if (p === `/companies/${CID}`) return json({ id: CID, name: "VOLTAGE", slug: "urban__demo", status: "active" });
    if (p === `/companies/${CID}/experience`) return json({ company_id: CID, branding });
    if (p === `/companies/${CID}/modules`) return json([{ id: "cm1", company_id: CID, module_id: "m1", enabled: true, settings: { reports_v2: P.get("v2") !== "0" }, module: { code: "reports", name: "Reportes" } }]);
    if (p.includes("/reports/companies/") && p.endsWith("/general")) {
      if (P.get("denied") === "1") return json({ detail: "Reportes es solo del dueño y del director" }, 403);
      payload = payload || await real("/__payload.json").then((r) => r.json());
      return json(payload);
    }
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
    const root = document.querySelector(".rr-root");
    const out = document.createElement("pre");
    out.id = "layout";
    if (!root) { out.textContent = JSON.stringify({ mounted: false, sidebar: !!document.querySelector(".client-sidebar"), calls: window.__rrCalls }); document.body.appendChild(out); return; }
    const bad = [];
    root.querySelectorAll("*").forEach((el) => {
      if (/^(INPUT|SELECT|OPTION)$/.test(el.tagName) || el.closest(".rr-hours, .rr-alerts")) return;
      if (el.offsetParent === null && getComputedStyle(el).position !== "fixed") return;
      if (el.scrollWidth > el.clientWidth + 1) bad.push({ tag: el.tagName, cls: String(el.className || ""), text: (el.textContent || "").trim().slice(0, 40), sw: el.scrollWidth, cw: el.clientWidth });
    });
    const low = [];
    [".rr-fig small", ".rr-fig b", ".rr-fig span", ".rr-hours li > *", ".rr-alerts li", ".rr-box small", ".rr-box b", ".rr-row > *", ".rr-person-card b", ".rr-person-card small",
      ".rr-pc-nums span", ".rr-tag", ".rr-h", ".rr-btn", ".rr-seg button", ".rr-field", ".rr-denied p", ".rr-modal-head h2"].forEach((sel) => root.querySelectorAll(sel).forEach((el) => {
      if (el.offsetParent === null && !el.closest(".rr-modal")) return;
      if (el.classList.contains("client-btn")) return;
      if (!(el.textContent || "").trim()) return;
      const r = ratio(el);
      if (r < 4.5) low.push({ sel, text: (el.textContent || "").trim().slice(0, 30), ratio: r });
    }));
    const text = root.textContent || "";
    out.textContent = JSON.stringify({ mounted: true, width: window.innerWidth, page_overflow: document.documentElement.scrollWidth > window.innerWidth + 1, bad, low_contrast: low,
      sidebar: !!document.querySelector(".client-sidebar"), csv: /csv/i.test(text), kpis: /\bKPIs?\b/.test(text), figs: root.querySelectorAll(".rr-fig").length,
      denied: !!root.querySelector(".rr-denied"), english: /Hours per day/.test(text), calls: window.__rrCalls });
    document.body.appendChild(out);
  }

  const go = () => {
    const btn = document.querySelector('[data-client-module="reports"]') || [...document.querySelectorAll(".client-nav button")].find((b) => /report/i.test(b.textContent));
    if (!btn) return setTimeout(go, 200);
    btn.click();
    const wait = (n = 0) => {
      const ready = document.querySelector(".rr-root .rr-fig, .rr-root .rr-denied") || (n > 40 && document.querySelector(".client-hero"));
      if (!ready) return setTimeout(() => wait(n + 1), 200);
      if (P.get("modal") === "box") { const b = document.querySelector('[data-rr-box="requested"]'); if (b) b.click(); }
      if (P.get("modal") === "person") { const b = document.querySelector("[data-rr-person-open]"); if (b) b.click(); }
      setTimeout(measure, 900);
    };
    setTimeout(wait, 300);
  };
  window.addEventListener("load", () => setTimeout(go, 300));
})();
