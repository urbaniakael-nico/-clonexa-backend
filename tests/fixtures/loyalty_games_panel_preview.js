// Vista previa del panel de Juegos en vivo dentro del portal real (client.html +
// client.js), con datos de ejemplo y el tema de The Time Machine. Abre
// Fidelización, espera el botón "🎮 Juegos en vivo" (solo aparece si /context
// responde 200), lo abre y mide desbordes y contraste AA en <pre id="layout">.
// ?role=admin|barman, ?tab=live|config|questions|history, ?off=1 (interruptor apagado).
(() => {
  const P = new URLSearchParams(location.search);
  const CID = P.get("company_id");
  const ROLE = P.get("role") || "admin";
  const branding = { mode: "dark", theme_mode: "dark", font_family: "Poppins", primary_color: "#6b5d00", text_color: "#ffffff", secondary_color: "#aea924",
    background_color: "#14110a", gradient_from: "#14110a", gradient_to: "#2a2410", background_mode: "gradient", card_style: "neon_border", visual_preset: "classic_office" };
  const json = (b, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
  const real = window.fetch.bind(window);
  try { localStorage.setItem("clonexa_access_token", "preview"); } catch (_) {}
  const now = Date.now();
  const iso = (ms) => new Date(now + ms).toISOString();
  const names = ["Camila", "Ana María Restrepo V", "Beto", "Dani la del Rock", "Juan Pablo", "Sofi"];
  const live = {
    now: iso(0), active: false, focus: "round", game_day: "2026-10-16",
    roulette: { id: "d1", range_min: 1, range_max: 50, number: 37, prize: "Shot", spun_at: iso(-60000), drawn: [7, 21, 44, 37] },
    round: { id: "r1", kind: "trivia", status: "closed", prize: "Botella de aguardiente", count: 6, players: names.map((n, i) => ({ id: `p${i}`, name: n })),
      all_players: names.map((n, i) => ({ id: `p${i}`, name: n, hidden: i === 5, result: "ranked", place: i + 1, validated: i === 0 })),
      goal: 10, ranking: names.slice(0, 5).map((n, i) => ({ id: `p${i}`, name: n, rank: i + 1, score: 10 - i, done: i === 0, ms: 102000 + i * 9000 })),
      podium: [{ place: 1, id: "p0", name: "Camila", score: 10, ms: 102000 }, { place: 2, id: "p1", name: "Ana María Restrepo V", score: 9, ms: 111000 }, { place: 3, id: "p2", name: "Beto", score: 8, ms: 151000 }],
      started_at: iso(-300000), ends_at: iso(-120000), join_url: "https://x/juegos/jugar?r=abc", token: "abc" },
  };
  if (P.get("round") === "playing") {  // ronda en juego: Terminar ahora / Cancelar y reiniciar
    live.active = true;
    Object.assign(live.round, { status: "playing", podium: [], ends_at: iso(95000), closed_at: null });
  }
  const ctx = { role: ROLE, can: { configure: ROLE === "admin", launch: true, validate: true },
    brand: { name: "The Time Machine", logo_url: "", primary: "#6b5d00", secondary: "#aea924", language: "es", timezone: "America/Bogota" },
    settings: { memory_pairs: 5, memory_times: { 5: 120, 7: 150, 10: 210, 13: 270, 15: 300 }, trivia_seconds: 240, differences_seconds: 180, differences_penalty: 5,
      differences_scene: "pub", roulette_ranges: [{ min: 1, max: 50, prize: "Shot" }, { min: 1, max: 100, prize: "Cerveza" }],
      prizes: { memory: "Botella de aguardiente", trivia: "Ronda de la casa", roulette: "", differences: "Coctel" }, texts: { claim: "Reclama con tu documento", consent: "Autorizo el tratamiento de mis datos para este concurso" } },
    pair_options: [5, 7, 10, 13, 15], levels: P.get("low") === "1" ? { 1: 8, 2: 8, 3: 3, 4: 8, 5: 2 } : { 1: 8, 2: 8, 3: 8, 4: 8, 5: 8 },
    scenes: [{ id: "pub", name: "Bar" }, { id: "concert", name: "Concierto" }],
    live, ...(ROLE === "admin" ? { screen_url: "https://clonexa-backend-production.up.railway.app/juegos/pantalla?t=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX" } : {}) };
  const seed = [["¿Qué banda canta \"Bohemian Rhapsody\"?", "Queen", "The Beatles", "AC/DC", 1], ["¿Cuál es el nombre real de Raphael?", "Miguel Rafael Martos Sánchez", "José Rómulo Sosa", "Rafael Pérez Botija", 4],
    ["¿En qué banda tocaba Ringo Starr antes de The Beatles?", "Rory Storm and the Hurricanes", "The Quarrymen", "The Animals", 5]];
  const questions = seed.map(([q, a, b, c, l], i) => ({ id: `q${i}`, level: l, question: q, correct_answer: a, wrong_1: b, wrong_2: c, active: i !== 1 }));
  const history = { rounds: [{ id: "r1", kind: "trivia", status: "closed", prize: "Botella de aguardiente", game_day: "2026-10-16", created_at: iso(-400000), players: 6, validated: 1,
    goal: 10, results: [{ place: 1, name: "Camila", score: 10, ms: 102000 }, { place: 2, name: "Ana María Restrepo V", score: 9, ms: 111000 }, { place: 3, name: "Beto", score: 8, ms: 151000 }] }],
    draws: [{ id: "d1", game_day: "2026-10-16", range_min: 1, range_max: 50, number: 37, prize: "Shot", spun_by: "barman@ttm", spun_at: iso(-60000) }] };

  window.fetch = async (url, opts) => {
    const u = String(url);
    if (!u.startsWith("/api/v1")) return real(url, opts);
    const p = u.slice(7).split("?")[0];
    if (p.endsWith("/locale")) return json({ currency: "COP", timezone: "America/Bogota", language: "es", decimals: 0 });
    if (p === `/companies/${CID}`) return json({ id: CID, name: "The Time Machine", slug: "ttm", status: "active" });
    if (p === `/companies/${CID}/experience`) return json({ company_id: CID, branding });
    if (p === `/companies/${CID}/modules`) return json([{ id: "cm1", company_id: CID, module_id: "m1", enabled: true, settings: {}, module: { code: "loyalty", name: "Fidelización" } }]);
    if (p.startsWith(`/loyalty-retos/companies/${CID}/`)) return json({ detail: "Retos para las mesas no está activo para esta empresa." }, 404);  // sin loyalty_retos_v2
    if (p.startsWith(`/loyalty-games/companies/${CID}/`)) {
      if (P.get("off") === "1") return json({ detail: "Juegos en vivo no está activo para esta empresa." }, 404);
      if (p.endsWith("/context")) return json(ctx);
      if (p.endsWith("/live")) return json(live);
      if (p.endsWith("/questions")) return json({ items: questions });
      if (p.endsWith("/history")) return json(history);
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
    const root = document.querySelector(".lg-root");
    const out = document.createElement("pre");
    out.id = "layout";
    if (!root) { out.textContent = JSON.stringify({ mounted: false, ...extra }); document.body.appendChild(out); return; }
    const bad = [], low = [];
    root.querySelectorAll("*").forEach((el) => {
      if (/^(INPUT|SELECT|OPTION)$/.test(el.tagName) || el.offsetParent === null) return;
      if (el.scrollWidth > el.clientWidth + 1) bad.push({ tag: el.tagName, cls: String(el.className || ""), text: (el.textContent || "").trim().slice(0, 40), sw: el.scrollWidth, cw: el.clientWidth });
      const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
      if (own && !el.classList.contains("client-btn") && !el.closest(".client-btn")) { const r = ratio(el); if (r < 4.5) low.push({ tag: el.tagName, cls: String(el.className || ""), text: el.textContent.trim().slice(0, 30), ratio: r }); }
    });
    const text = root.textContent.replace(/\s+/g, " ");
    out.textContent = JSON.stringify({ mounted: true, page_overflow: document.documentElement.scrollWidth > window.innerWidth + 1, bad, low_contrast: low,
      tabs: [...root.querySelectorAll(".lg-tabs button")].map((b) => b.textContent.trim()), screen_link: !!root.querySelector("[data-lg-screen-url]"),
      validate: !!root.querySelector("[data-lg-validate]"), spin: !!root.querySelector("[data-lg-spin]"), pairs: root.querySelectorAll("[data-lg-pairs] option").length,
      opens: [...root.querySelectorAll("[data-lg-open]")].map((b) => b.getAttribute("data-lg-open")), scenes: root.querySelectorAll("[data-lg-defscene] option").length, scenepick: [...root.querySelectorAll("[data-lg-scenepick] option")].map((o) => o.textContent.trim()),
      memtimes: root.querySelectorAll("[data-lg-memtime]").length, warning: /Nivel 3: solo 3 preguntas activas/.test(root.textContent), text: text.slice(0, 4000), ...extra });
    document.body.appendChild(out);
  }

  const go = (n = 0) => {
    const card = document.querySelector('[data-client-module="loyalty"]');
    if (!card) return n > 80 ? measure({ reason: "sin tarjeta" }) : setTimeout(() => go(n + 1), 200);
    card.click();
    const waitBtn = (k = 0) => {
      const btn = document.querySelector("[data-loy-games-open-055b]");
      if (!btn) return k > 25 ? measure({ button: false }) : setTimeout(() => waitBtn(k + 1), 200);
      btn.click();
      const waitPanel = (j = 0) => {
        if (!document.querySelector(".lg-root .lg-tabs")) return j > 40 ? measure({ button: true }) : setTimeout(() => waitPanel(j + 1), 200);
        const tab = P.get("tab");
        if (tab && tab !== "live") { const b = document.querySelector(`[data-lg-tab="${tab}"]`); if (b) b.click(); }
        if (P.get("confirm")) setTimeout(() => { const b = document.querySelector(`[data-lg-ask="${P.get("confirm")}"]`); if (b) b.click(); }, 500);
        setTimeout(() => measure({ button: true }), 1000);
      };
      waitPanel();
    };
    setTimeout(waitBtn, 400);
  };
  window.addEventListener("load", () => setTimeout(go, 300));
})();
