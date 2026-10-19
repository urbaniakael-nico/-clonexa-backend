// Prueba de humo del portal (056I): Velvet con sus módulos e interruptores reales
// (production_v2, quotes_v2, references_v2, crm_velvet_lab, payroll_v2, workforce_v2),
// datos de ejemplo y fetch simulado. Recorre cada botón del menú y mide si el área
// principal tiene contenido, si hubo errores de JavaScript y qué sesión llevó cada
// llamada. ?auth=token (usuario del portal, token en localStorage) | cookie (vista
// previa "Entrar como empresa": sin token, solo cookie) · ?fail=401|500 hace fallar
// las APIs de Producción v2 y Cotizaciones v2. Resultado en <pre id="layout">.
(() => {
  const P = new URLSearchParams(location.search);
  const CID = "d63cf68c-be5b-4a30-aee4-341973018db1";
  const AUTH = P.get("auth") || "token";
  const FAIL = P.get("fail") || "";
  const errors = [];
  window.addEventListener("error", (e) => errors.push(String((e.error && e.error.stack) || e.message).slice(0, 300)));
  window.addEventListener("unhandledrejection", (e) => errors.push(String((e.reason && e.reason.stack) || e.reason).slice(0, 300)));
  try {
    localStorage.clear();
    if (AUTH === "token") localStorage.setItem("clonexa_access_token", "portal-token");
  } catch (_) {}

  const mod = (code, name, settings = {}) => ({ id: `cm-${code}`, company_id: CID, module_id: `m-${code}`, enabled: true, settings, module: { code, name } });
  const MODULES = [
    mod("workforce", "Workforce", { workforce_v2: true }), mod("production", "Producción", { production_v2: true }),
    mod("payroll", "Nómina", { payroll_v2: true, payroll_shift_list: true }), mod("references", "Referencias", { references_v2: true, crm_velvet_lab: true }),
    mod("bots", "Bots"), mod("cotizacion", "Cotizaciones", { quotes_v2: true }), mod("mini_panel", "Mini Paneles"), mod("assistant_ai", "Asistente"),
  ];
  const SIN = (reason) => ({ status: "sin_datos", value: null, reason });
  const INSIGHTS = { company: { name: "Velvet", logo_url: "" }, period: { from: "2026-10-19", to: "2026-10-19", by: "week" },
    kpis: { workshop_now: { status: "ok", value: 1, working: 1, paused: 0, lots: 1 }, closed: SIN("Aún no hay cierres registrados."), sent: SIN("x"),
      days_per_lot: SIN("x"), team_hours_per_garment: SIN("x"), labor_per_garment: SIN("x") },
    lots_in_process: [], live: [{ name: "Ana", status: "working", reference: "PANT SET", elapsed_minutes: 30 }], series: [], team_time: { total_seconds: 0, by_reference: [] }, alerts: [] };
  const QV = { "/defaults": { company: { name: "Velvet" }, payment: null, signature: null, clients: [] }, "/from-production": { lines: [], already_charged: [], already_charged_total: 0 },
    "/documents": { totals: {}, documents: [] }, "/report": { collected: 0, pending: 0 } };

  const calls = [];
  const json = (b, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
  const real = window.fetch.bind(window);
  window.fetch = async (url, opts = {}) => {
    const u = String(url);
    if (!u.startsWith("/api/v1")) return real(url, opts);
    const headers = opts.headers || {};
    const auth = headers.Authorization || headers.authorization || (typeof headers.get === "function" ? headers.get("Authorization") : "") || "";
    const p = u.slice(7).split("?")[0];
    calls.push({ p, auth: Boolean(auth), credentials: opts.credentials || "" });
    if (p.endsWith("/locale")) return json({ currency: "COP", timezone: "America/Bogota", language: "es", decimals: 0 });
    if (p === `/companies/${CID}`) return json({ id: CID, name: "Velvet", slug: "velvet", status: "active" });
    if (p === `/companies/${CID}/experience`) return json({ company_id: CID, branding: {} });
    if (p === `/companies/${CID}/modules`) return json(MODULES);
    if (p.startsWith("/production-v2/") || p.startsWith("/quotes-v2/")) {
      if (FAIL === "401") return json({ detail: "no_session" }, 401);
      if (FAIL === "500") return json({ detail: "boom" }, 500);
      if (p.startsWith("/production-v2/")) return json(INSIGHTS);
      const key = Object.keys(QV).find((k) => p.endsWith(k));
      return json(key ? QV[key] : {});
    }
    if (/\/employees$|employee-roles|\/bots\/|crm-lab\/.*pins/.test(p)) return json(p.includes("pins") ? { pins: [] } : []);
    return json({});
  };

  const results = {};
  const textOf = () => {
    const main = document.querySelector(".client-main");
    return main ? (main.innerText || main.textContent || "").replace(/\s+/g, " ").trim() : "";
  };
  const finish = () => {
    const out = document.createElement("pre");
    out.id = "layout";
    out.textContent = JSON.stringify({ auth: AUTH, fail: FAIL, results, errors, calls: calls.filter((c) => /production-v2|quotes-v2|mini-panel-quotes/.test(c.p)) });
    document.body.appendChild(out);
  };
  const visit = (codes, i) => {
    if (i >= codes.length) return finish();
    const code = codes[i];
    const btn = document.querySelector(`.client-nav [data-client-module="${code}"]`) || (code === "dashboard" ? document.querySelector(".client-nav [data-client-back-dashboard]") : null);
    if (!btn) { results[code] = { missing: true }; return visit(codes, i + 1); }
    const before = errors.length;
    btn.click();
    setTimeout(() => {
      const text = textOf();
      results[code] = { chars: text.length, sample: text.slice(0, 80), errors: errors.slice(before), retry: Boolean(document.querySelector("[data-pp-retry],[data-qv-retry],[data-cx-v2-retry]")),
        v2: Boolean(document.querySelector(".pp-root,.qv-root")) };
      visit(codes, i + 1);
    }, 2500);
  };
  const go = () => {
    if (!document.querySelector(".client-nav")) return setTimeout(go, 200);
    visit(["dashboard", ...MODULES.map((m) => m.module.code)], 0);
  };
  window.addEventListener("load", () => setTimeout(go, 500));
})();
