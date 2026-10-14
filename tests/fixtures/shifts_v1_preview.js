// Vista previa de Turnos (modulo shifts) con datos de ejemplo (sin servidor ni
// personas reales) y el tema de VOLTAGE. ?tab=grid|changes|config, ?modal=1
// (Cambio de turno), ?role=owner|supervisor, ?status=draft (con un hueco),
// ?lang=en, ?denied=1 (403). Al final mide desbordes y contraste AA y deja el
// resultado en <pre id="layout">.
(() => {
  const P = new URLSearchParams(location.search);
  const CID = P.get("company_id");
  const LANG = P.get("lang") || "es";
  const ROLE = P.get("role") || "supervisor";
  const DRAFT = P.get("status") === "draft";
  const branding = { mode: "dark", theme_mode: "dark", font_family: "Poppins", primary_color: "#ffffff", text_color: "#ffffff", secondary_color: "#00ff9d",
    background_color: "#002e8a", gradient_from: "#f3f4f6", gradient_to: "#e5e7eb", background_mode: "gradient", card_style: "neon_border", visual_preset: "classic_office" };
  const json = (b, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
  const real = window.fetch.bind(window);
  window.__shCalls = [];
  try { localStorage.setItem("clonexa_access_token", "preview"); } catch (_) {}

  const T = [
    { id: "tm", code: "M", name: "Mañana", start: "06:00", end: "14:00", color: "#f59e0b", active: true, night: false, minutes: 480 },
    { id: "tt", code: "T", name: "Tarde", start: "14:00", end: "22:00", color: "#3b82f6", active: true, night: false, minutes: 480 },
    { id: "tn", code: "N", name: "Noche", start: "22:00", end: "06:00", color: "#7c3aed", active: true, night: true, minutes: 480 },
  ];
  const E = [
    ["e1", "Olga Operaria (prueba)", "operario", "Operario", false], ["e2", "Ana María Restrepo Villalobos", "operario", "Operario", true],
    ["e3", "Carlos Pérez", "operario", "Operario", true], ["e4", "Beto Díaz", "operario", "Operario", false], ["e5", "Sara Gómez", "operario", "Operario", true],
    ["e6", "NICOLAS GOMEZ", "supervisor", "Supervisor", true],
  ].map(([id, name, role, role_label, telegram]) => ({ id, name, role, role_label, telegram }));
  const days = ["2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16", "2026-10-17", "2026-10-18"];
  const assignments = [];
  const ops = E.filter((e) => e.role === "operario");
  days.forEach((d, i) => {
    T.forEach((t, k) => {
      const e = ops[(i + k * 2) % ops.length];
      if (DRAFT && d === "2026-10-15" && t.id === "tn") return;
      assignments.push({ id: `a-${i}-${k}`, employee_id: e.id, work_date: d, week_start: days[0], template_id: t.id, status: DRAFT ? "draft" : "published" });
    });
  });
  const fairness = E.map((e) => {
    const mine = assignments.filter((a) => a.employee_id === e.id);
    return { employee_id: e.id, name: e.name, role: e.role, nights: mine.filter((a) => a.template_id === "tn").length,
      weekends: mine.filter((a) => a.work_date >= "2026-10-17").length, minutes: mine.length * 480 };
  });
  const week = { week_start: days[0], status: DRAFT ? "draft" : "published", days, assignments,
    analysis: { gaps: DRAFT ? [{ date: "2026-10-15", template_id: "tn", template: "Noche", role: "operario", missing: 1 }] : [], rest: [], fairness,
      coverage_ok: !DRAFT, rest_ok: true } };
  const context = {
    role: ROLE, can: { configure: true, build: true, publish: true, create_change: ROLE === "supervisor" }, logo_url: "",
    templates: T, rules: { min_rest_hours: 12, days_off_per_week: 1, max_consecutive_days: 6, weekly_hours_cap: null, max_consecutive_nights: 3, response_hours: 2, default_weekly_hours_cap: 40 },
    coverage: T.map((t) => ({ template_id: t.id, role: "operario", min: 1 })), roles: [{ code: "operario", label: "Operario" }, { code: "supervisor", label: "Supervisor" }], employees: E,
  };
  const log = (kind, extra) => ({ at: "2026-10-14T15:00:00+00:00", kind, ...extra });
  const changes = [
    { id: "c1", assignment_id: "a-2-0", requester_employee_id: "e1", work_date: "2026-10-14", template_id: "tm", status: "waiting", uncovered: false, current_index: 1,
      deadline_at: "2026-10-14T17:00:00+00:00", candidates: [{ employee_id: "e3", name: "Carlos Pérez" }, { employee_id: "e4", name: "Beto Díaz", telegram: false }],
      log: [log("created", { by: "nicolas@urbania", candidates: 2 }), log("offered", { name: "Carlos Pérez", bot: true }), log("rejected", { name: "Carlos Pérez", via: "bot" }), log("offered", { name: "Beto Díaz", bot: false })] },
    { id: "c2", assignment_id: "a-4-2", requester_employee_id: "e2", work_date: "2026-10-16", template_id: "tn", status: "expired", uncovered: true, current_index: null,
      candidates: [{ employee_id: "e5", name: "Sara Gómez" }, { employee_id: "e3", name: "Carlos Pérez" }],
      log: [log("created", { by: "nicolas@urbania", candidates: 2 }), log("offered", { name: "Sara Gómez", bot: true }), log("expired", { name: "Sara Gómez" }),
        log("offered", { name: "Carlos Pérez", bot: true }), log("expired", { name: "Carlos Pérez" }), log("uncovered", {})] },
    { id: "c3", assignment_id: "a-1-1", requester_employee_id: "e5", work_date: "2026-10-13", template_id: "tt", status: "accepted", uncovered: false, current_index: 0,
      candidates: [{ employee_id: "e1", name: "Olga Operaria (prueba)" }],
      log: [log("created", { by: "nicolas@urbania", candidates: 3 }), log("offered", { name: "Olga Operaria (prueba)", bot: false }), log("accepted", { name: "Olga Operaria (prueba)", via: "manual", by: "nicolas@urbania" })] },
  ];
  const proposal = { assignment: assignments[6], enough: true, candidates: [
    { employee_id: "e4", name: "Beto Díaz", role: "operario", kind: "cover", week_minutes: 1920, attendance: 18, punctuality: 15, changes: 0, telegram: false },
    { employee_id: "e3", name: "Carlos Pérez", role: "operario", kind: "swap", swap_template_id: "tt", week_minutes: 2400, attendance: 20, punctuality: 19, changes: 1, telegram: true },
  ], discarded: [{ employee_id: "e5", name: "Sara Gómez", reasons: ["rest"] }, { employee_id: "e2", name: "Ana María Restrepo Villalobos", reasons: ["cap", "consecutive_days"] }, { employee_id: "e6", name: "NICOLAS GOMEZ", reasons: ["role"] }] };

  window.fetch = async (url, opts) => {
    const u = String(url);
    if (!u.startsWith("/api/v1")) return real(url, opts);
    window.__shCalls.push(u);
    const p = u.slice(7).split("?")[0];
    if (p.endsWith("/locale")) return json({ currency: "USD", timezone: "America/Chicago", language: LANG, decimals: 2 });
    if (p === `/companies/${CID}`) return json({ id: CID, name: "VOLTAGE", slug: "urban__demo", status: "active" });
    if (p === `/companies/${CID}/experience`) return json({ company_id: CID, branding });
    if (p === `/companies/${CID}/modules`) return json([{ id: "cm1", company_id: CID, module_id: "m1", enabled: true, settings: {}, module: { code: "shifts", name: "Turnos" } }]);
    if (p.startsWith(`/turnos/companies/${CID}/`)) {
      if (P.get("denied") === "1") return json({ detail: "Turnos: tu rol no tiene acceso a este panel." }, 403);
      if (p.endsWith("/context")) return json(context);
      if (p.endsWith("/week")) return json(week);
      if (p.endsWith("/changes")) return json({ items: changes });
      if (p.endsWith("/changes/proposal")) return json(proposal);
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
    const root = document.querySelector(".sh-root");
    const out = document.createElement("pre");
    out.id = "layout";
    if (!root) { out.textContent = JSON.stringify({ mounted: false, calls: window.__shCalls }); document.body.appendChild(out); return; }
    const bad = [];
    root.querySelectorAll("*").forEach((el) => {
      if (/^(INPUT|SELECT|OPTION)$/.test(el.tagName) || el.classList.contains("sh-sr")) return;
      if (el.offsetParent === null && getComputedStyle(el).position !== "fixed") return;
      if (el.scrollWidth > el.clientWidth + 1) bad.push({ tag: el.tagName, cls: String(el.className || ""), text: (el.textContent || "").trim().slice(0, 40), sw: el.scrollWidth, cw: el.clientWidth });
    });
    const low = [];
    [".sh-who b", ".sh-who small", ".sh-cell", ".sh-total", ".sh-row.is-head > *", ".sh-checks li", ".sh-frow > *", ".sh-chip", ".sh-h", ".sh-h3", ".sh-btn", ".sh-tabs button",
      ".sh-field", ".sh-check", ".sh-steps time", ".sh-steps span", ".sh-change-head b", ".sh-change-head small", ".sh-wait", ".sh-manual", ".sh-cands b", ".sh-cands small",
      ".sh-disc summary", ".sh-legend span", ".sh-denied p", ".sh-modal-head h2", ".sh-week-label", ".sh-cov-row > span", ".sh-tpl-note", ".sh-notice"].forEach((sel) => root.querySelectorAll(sel).forEach((el) => {
      if (el.offsetParent === null && !el.closest(".sh-modal")) return;
      if (el.classList.contains("client-btn")) return;
      if (!(el.textContent || "").trim()) return;
      const r = ratio(el);
      if (r < 4.5) low.push({ sel, text: (el.textContent || "").trim().slice(0, 30), ratio: r });
    }));
    const text = root.textContent || "";
    out.textContent = JSON.stringify({ mounted: true, width: window.innerWidth, page_overflow: document.documentElement.scrollWidth > window.innerWidth + 1, bad, low_contrast: low,
      rows: root.querySelectorAll(".sh-grid .sh-row:not(.is-head)").length, cells: root.querySelectorAll(".sh-grid .sh-cell").length,
      total: (root.querySelector(".sh-total b") || {}).textContent || "", gap: /Falta 1 operario · Noche · jue 15/.test(text), ok: /Cobertura completa/.test(text),
      tabs: [...root.querySelectorAll(".sh-tabs button")].map((b) => b.textContent.trim()), modal: !!root.querySelector(".sh-modal"),
      change_btn: !!root.querySelector("[data-sh-change]"), denied: !!root.querySelector(".sh-denied"), english: /Build schedule|Schedule/.test(text), calls: window.__shCalls });
    document.body.appendChild(out);
  }

  const go = () => {
    const btn = document.querySelector('[data-client-module="shifts"]');
    if (!btn) return setTimeout(go, 200);
    btn.click();
    const wait = (n = 0) => {
      const ready = document.querySelector(".sh-root .sh-grid, .sh-root .sh-denied") || n > 60;
      if (!ready) return setTimeout(() => wait(n + 1), 200);
      const tab = P.get("tab");
      if (tab) { const b = document.querySelector(`[data-sh-tab="${tab}"]`); if (b) b.click(); }
      if (P.get("modal") === "1") { const c = document.querySelector("[data-sh-cell]"); if (c) c.click(); }
      setTimeout(measure, 1200);
    };
    setTimeout(wait, 300);
  };
  window.addEventListener("load", () => setTimeout(go, 300));
})();
