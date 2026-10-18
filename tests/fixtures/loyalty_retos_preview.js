// Vista previa de Retos para las mesas dentro del portal real (client.html +
// client.js) con datos de ejemplo y el tema de The Time Machine. Abre
// Fidelización (la pantalla nueva solo aparece si /loyalty-retos/.../state
// responde 200), recorre el caso pedido y mide desbordes y contraste AA en
// <pre id="layout">. ?view=main|history, ?wiz=consumption|score_pool|vote_poll&step=1..3,
// ?mode=yes_no (concurso), ?off=1 (interruptor apagado: la pantalla de siempre).
(() => {
  const P = new URLSearchParams(location.search);
  const CID = P.get("company_id");
  const branding = { mode: "dark", theme_mode: "dark", font_family: "Poppins", primary_color: "#6b5d00", text_color: "#ffffff", secondary_color: "#aea924",
    background_color: "#14110a", gradient_from: "#14110a", gradient_to: "#2a2410", background_mode: "gradient", card_style: "neon_border", visual_preset: "classic_office" };
  const json = (b, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
  const real = window.fetch.bind(window);
  try { localStorage.setItem("clonexa_access_token", "preview"); } catch (_) {}
  const now = Date.now();
  const iso = (ms) => new Date(now + ms).toISOString();
  const consumption = {
    id: "c1", campaign_type: "consumption", title: "Reto de consumo · Viernes de rock", prize: "1/4 de ron Viejo de Caldas", status: "active", rules_version: 2,
    stage: "playing", deadline: iso(2 * 3600000 + 754000), deadline_label: "El torneo cierra en", actions: ["close_now", "cancel"], participants: 6,
    leaderboard: [
      { rank: 1, team_name: "Los del fondo con nombre largo de verdad", table_number: "Mesa 12", orders_count: 7, total: 412000 },
      { rank: 2, team_name: "Rockeros", table_number: "Mesa 3", orders_count: 4, total: 268500 },
      { rank: 3, team_name: "Mesa 7", table_number: "Mesa 7", orders_count: 2, total: 98000 },
      { rank: 4, team_name: "Las chicas", table_number: "Mesa 1", orders_count: 1, total: 32000 }],
  };
  const pool = {
    id: "p1", campaign_type: "score_pool", title: "Polla · Colombia vs Argentina", prize: "Botella de aguardiente", team_a: "Colombia", team_b: "Argentina", status: "active", rules_version: 2,
    stage: "result", deadline: null, actions: ["tiebreak", "pick_winner", "cancel"], participants: 9, result_status: "tie", final_score: { score_a: 2, score_b: 1 },
    result: { matches: [{ table_key: "mesa 4", table_number: "Mesa 4", team_name: "Los parceros" }, { table_key: "mesa 9", table_number: "Mesa 9", team_name: "Mesa 9" }] },
    predictions: [[2, 1], [2, 1], [1, 1], [0, 0], [3, 1], [1, 0], [2, 0], [1, 1], [0, 1]].map(([a, b], i) => ({ table_number: `Mesa ${i + 1}`, score_a: a, score_b: b })),
    tiebreak: null,
  };
  const vote = {
    id: "v1", campaign_type: "vote_poll", vote_mode: "participants", title: "Karaoke de las 10", prize: "Ronda de shots", status: "active", rules_version: 2,
    description: "¿Quién cantó mejor esta noche?", stage: "registration", deadline: iso(1520000), deadline_label: "Votación cierra en", actions: ["close_now", "cancel"], participants: 14,
    results: [{ key: "option_1", label: "Ana — Bohemian Rhapsody", count: 6, percent: 42.9 }, { key: "option_2", label: "Beto", count: 5, percent: 35.7 }, { key: "option_3", label: "Caro", count: 3, percent: 21.4 }],
  };
  const history = [
    { id: "h1", type: "score_pool", title: "Polla · Final de la Libertadores", prize: "Botella de ron", team_a: "Nacional", team_b: "River", result_status: "winner", source: "tiebreak",
      final_score: { score_a: 1, score_b: 1 }, winner: { kind: "table", table_number: "Mesa 5", team_name: "Los de la esquina", player_name: "Camila", source: "tiebreak" }, prize_status: "pending", closed_at: iso(-86400000) },
    { id: "h2", type: "consumption", title: "Reto de consumo", prize: "1/4 de ron", result_status: "winner", source: "consumption", winner: { kind: "table", table_number: "Mesa 2", team_name: "Rockeros" },
      prize_status: "delivered", prize_delivered_at: iso(-170000000), prize_delivered_by: "barman@ttm", closed_at: iso(-172800000) },
    { id: "h3", type: "vote_poll", title: "¿Sí o no?", prize: "Shot", result_status: "no_winner", source: "", winner: null, prize_status: "", closed_at: iso(-260000000) },
    { id: "h4", type: "score_pool", title: "Polla vieja", prize: "x", result_status: "", winner: null, prize_status: "", closed_at: iso(-400000000) },
  ];
  const state = { now: iso(0), role: "admin", timezone: "America/Bogota", language: "es", currency: "COP", games_on: true,
    business_day: { open: "18:00", close: "04:00", overnight: true }, active: { consumption, score_pool: pool, vote_poll: vote }, history };
  if (P.get("wiz")) state.active[P.get("wiz")] = null;  // el tipo que se va a lanzar arranca libre

  window.fetch = async (url, opts) => {
    const u = String(url);
    if (!u.startsWith("/api/v1")) return real(url, opts);
    const p = u.slice(7).split("?")[0];
    if (p.endsWith("/locale")) return json({ currency: "COP", timezone: "America/Bogota", language: "es", decimals: 0 });
    if (p === `/companies/${CID}`) return json({ id: CID, name: "The Time Machine", slug: "ttm", status: "active" });
    if (p === `/companies/${CID}/experience`) return json({ company_id: CID, branding });
    if (p === `/companies/${CID}/modules`) return json([{ id: "cm1", company_id: CID, module_id: "m1", enabled: true, settings: {}, module: { code: "loyalty", name: "Fidelización" } }]);
    if (p.startsWith(`/loyalty-retos/companies/${CID}/`)) {
      if (P.get("off") === "1") return json({ detail: "Retos para las mesas no está activo para esta empresa." }, 404);
      if (p.endsWith("/state")) return json(state);
    }
    if (p.startsWith(`/loyalty-games/companies/${CID}/`)) return json({ role: "admin", can: {}, brand: {}, settings: {}, live: {} });
    if (p.includes("/loyalty-campaigns/summary")) return json({ ok: true, campaign: null, score_campaign: null, vote_campaign: null });
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
  function bgOf(el) {
    const layers = [];
    for (let n = el; n; n = n.parentElement) { const c = rgb(getComputedStyle(n).backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } }
    let base = { r: 255, g: 255, b: 255 };
    const stops = String(getComputedStyle(document.body).backgroundImage).match(/rgba?\([^)]+\)/g);
    if (stops && stops.length) base = rgb(stops[0]);
    for (let i = layers.length - 1; i >= 0; i -= 1) { const l = layers[i]; base = { r: l.r * l.a + base.r * (1 - l.a), g: l.g * l.a + base.g * (1 - l.a), b: l.b * l.a + base.b * (1 - l.a) }; }
    return base;
  }
  function ratio(el) { const fg = rgb(getComputedStyle(el).color); const bg = bgOf(el); const a = lum(fg) + 0.05; const b = lum(bg) + 0.05; return Math.round((Math.max(a, b) / Math.min(a, b)) * 100) / 100; }

  function measure(extra = {}) {
    const root = document.querySelector(".rt-root");
    const out = document.createElement("pre");
    out.id = "layout";
    out.style.display = "none";
    if (!root) {
      const old = document.querySelector(".client-title");
      out.textContent = JSON.stringify({ mounted: false, title: old ? old.textContent.trim() : "", ...extra });
      document.body.appendChild(out);
      return;
    }
    const bad = [], low = [];
    root.querySelectorAll("*").forEach((el) => {
      if (/^(INPUT|SELECT|OPTION|TEXTAREA)$/.test(el.tagName) || el.offsetParent === null) return;
      if (el.closest(".rt-phone-screen")) return;  // maqueta del QR: colores fijos del celular (se miden aparte)
      if (el.scrollWidth > el.clientWidth + 1) bad.push({ tag: el.tagName, cls: String(el.className || ""), text: (el.textContent || "").trim().slice(0, 40), sw: el.scrollWidth, cw: el.clientWidth });
      const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
      if (own && !el.classList.contains("client-btn") && !el.closest(".client-btn")) { const r = ratio(el); if (r < 4.5) low.push({ tag: el.tagName, cls: String(el.className || ""), text: el.textContent.trim().slice(0, 30), ratio: r }); }
    });
    const phoneLow = [...root.querySelectorAll(".rt-phone-screen *")].filter((el) => [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()))
      .map((el) => ({ text: el.textContent.trim().slice(0, 20), ratio: ratio(el) })).filter((x) => x.ratio < 4.5);
    out.textContent = JSON.stringify({ mounted: true, page_overflow: document.documentElement.scrollWidth > window.innerWidth + 1, bad, low_contrast: low, phone_low: phoneLow,
      types: root.querySelectorAll(".rt-type").length, live: root.querySelectorAll(".rt-live").length, step: (root.querySelector('.rt-steps [aria-current="step"]') || {}).textContent || "",
      phone: !!root.querySelector(".rt-phone"), text: root.textContent.replace(/\s+/g, " ").slice(0, 3000), ...extra });
    document.body.appendChild(out);
  }

  const fire = (el, value) => { el.value = value; el.dispatchEvent(new Event("input", { bubbles: true })); el.dispatchEvent(new Event("change", { bubbles: true })); };
  const click = (sel) => { const el = document.querySelector(sel); if (el) el.click(); return !!el; };

  function wizard() {
    const type = P.get("wiz");
    const step = Number(P.get("step") || 1);
    if (!click(`[data-rt-new="${type}"]`)) return false;
    const set = (k, v) => { const el = document.querySelector(`[data-rt-w="${k}"]`); if (el) fire(el, v); };
    set("prize", type === "consumption" ? "1/4 de ron Viejo de Caldas" : type === "score_pool" ? "Botella de aguardiente" : "Ronda de shots");
    if (type === "score_pool") { set("team_a", "Colombia"); set("team_b", "Argentina"); set("title", "Polla · Colombia vs Argentina"); }
    if (type === "vote_poll") {
      const mode = P.get("mode") || "participants";
      const radio = document.querySelector(`[data-rt-mode][value="${mode}"]`);
      if (radio) { radio.checked = true; radio.dispatchEvent(new Event("change", { bubbles: true })); }
      set("title", mode === "participants" ? "Karaoke de las 10" : "Pregunta del partido");
      set("description", mode === "participants" ? "¿Quién cantó mejor esta noche?" : "¿Colombia gana el partido?");
      if (mode === "participants") ["Ana — Bohemian Rhapsody", "Beto", "Caro"].forEach((v, i) => { const el = document.querySelector(`[data-rt-opt="${i}"]`); if (el) fire(el, v); });
      else { const s = document.querySelector("[data-rt-secret]"); if (s) { s.checked = true; s.dispatchEvent(new Event("change", { bubbles: true })); } }
    }
    for (let i = 1; i < step; i += 1) click("[data-rt-next]");
    if (P.get("custom") === "1") click('[data-rt-preset="custom"]');
    return true;
  }

  const go = (n = 0) => {
    const card = document.querySelector('[data-client-module="loyalty"]');
    if (!card) return n > 80 ? measure({ reason: "sin tarjeta" }) : setTimeout(() => go(n + 1), 200);
    card.click();
    const waitRoot = (j = 0) => {
      if (P.get("off") === "1") return setTimeout(() => measure({ off: true }), 2500);
      if (!document.querySelector(".rt-root .rt-layout, .rt-root .rt-card")) return j > 50 ? measure({ waited: true }) : setTimeout(() => waitRoot(j + 1), 200);
      if (P.get("view") === "history") click('[data-rt-tab="history"]');
      if (P.get("wiz") && !wizard()) return measure({ wizard: false });
      if (P.get("confirm")) click(`[data-rt-ask="${P.get("confirm")}"]`);
      return setTimeout(() => measure(), 900);
    };
    setTimeout(waitRoot, 400);
  };
  window.addEventListener("load", () => setTimeout(go, 300));
})();
