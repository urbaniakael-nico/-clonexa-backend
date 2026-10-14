// Vista previa de Juegos en vivo con datos de ejemplo (sin servidor ni personas
// reales) y los colores de The Time Machine. Pantalla del bar: ?scene=idle|
// roulette|registration|playing|podium. Celular: ?view=join|wait|memory|trivia|
// lost|win. ?lang=en. Al final mide desbordes, contraste AA y tamaño de letra y
// deja el resultado en <pre id="layout">.
(() => {
  const P = new URLSearchParams(location.search);
  const LANG = P.get("lang") || "es";
  const SCREEN = location.pathname.includes("screen");
  const now = Date.now();
  const iso = (ms) => new Date(now + ms).toISOString();
  const brand = { name: "The Time Machine", logo_url: "", primary: "#6b5d00", secondary: "#aea924", language: LANG, timezone: "America/Bogota" };
  const NAMES = ["Camila", "Ana María Restrepo V", "Beto", "Dani la del Rock", "Juan Pablo", "Sofi", "El Mono", "Laura G", "Andrés F", "Pipe", "Valentina Ospina", "Tato", "Nico", "Mafe"];
  const players = NAMES.map((name, i) => ({ id: `p${i}`, name }));
  const ranking = NAMES.slice(0, 10).map((name, i) => ({ id: `p${(i * 3) % 10}`, name, rank: i + 1, score: Math.max(0, 5 - Math.floor(i / 2)), done: i < 2, ms: 30000 + i * 1000 }));
  const scene = P.get("scene") || "idle";
  const round = (status, kind = "memory") => ({ id: "r1", kind, status, prize: "Botella de aguardiente", players, count: players.length, ranking: status === "registration" ? [] : ranking,
    podium: status === "closed" ? [{ place: 1, id: "p0", name: "Camila" }, { place: 2, id: "p1", name: "Ana María Restrepo V" }, { place: 3, id: "p2", name: "Beto" }] : [],
    started_at: iso(-45000), ends_at: iso(75000), duration_seconds: 120 });
  const state = () => ({
    now: new Date().toISOString(), game_day: "2026-10-16", brand, texts: { claim: "Reclama con tu documento", consent: "Autorizo el tratamiento de mis datos para este concurso" },
    focus: scene === "roulette" ? "roulette" : scene === "idle" ? "idle" : "round", active: scene === "registration" || scene === "playing",
    roulette: scene === "roulette" ? { id: "d1", range_min: 1, range_max: 50, number: 37, prize: "Shot de tequila", spun_at: iso(-30000), drawn: [7, 21, 44, 3, 18, 29, 37] } : null,
    round: scene === "registration" ? round("registration") : scene === "playing" ? round("playing") : scene === "podium" ? round("closed", "trivia") : null,
  });

  const view = P.get("view") || "join";
  const kind = view === "trivia" || view === "lost" ? "trivia" : "memory";
  const status = view === "join" ? "registration" : view === "wait" ? "registration" : view === "memory" || view === "trivia" ? "playing" : "closed";
  if (!SCREEN && view !== "join") { try { localStorage.setItem(`cxlg:${(P.get("r") || "").slice(0, 48)}`, "player.token"); } catch (_) {} }
  const me = () => ({ name: "Camila", status, kind, now: new Date().toISOString(), ends_at: iso(80000), hidden: false,
    memory: kind === "memory" ? { size: 10, faces: { 0: "🎸", 5: "🎸", 2: "🍸" }, matched: [0, 5], open: 2, pairs: 1, total_pairs: 5 } : undefined,
    result: view === "lost" ? { result: "lost", place: null, score: 3 } : view === "win" ? { result: "ranked", place: 1, score: 5 } : undefined });
  const question = { done: false, answered: 2, total: 5, lap: 1, correct: 2,
    question: { id: "q3", text: "¿Qué guitarrista construyó con su padre la guitarra \"Red Special\"?", level: 5, options: ["Jimmy Page", "Brian May", "Keith Richards"], remaining_ms: 7000, limit_ms: 10000 } };

  const json = (b, s = 200) => new Response(JSON.stringify(b), { status: s, headers: { "content-type": "application/json" } });
  const real = window.fetch.bind(window);
  window.fetch = async (url, opts) => {
    const u = String(url);
    if (!u.startsWith("/api/v1/loyalty-games")) return real(url, opts);
    if (u.includes("/qr.svg")) {
      let cells = "";
      for (let y = 0; y < 25; y += 1) for (let x = 0; x < 25; x += 1) if (((x * 7 + y * 13) % 5) < 2 || (x < 7 && y < 7) || (x > 17 && y < 7) || (x < 7 && y > 17)) cells += `<rect x="${x}" y="${y}" width="1" height="1"/>`;
      return new Response(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 25 25"><rect width="25" height="25" fill="#fff"/><g fill="#0b0a14">${cells}</g></svg>`, { headers: { "content-type": "image/svg+xml" } });
    }
    if (u.includes("/screen/")) return P.get("denied") === "1" ? json({ detail: "pantalla_no_autorizada" }, 403) : json(state());
    const path = u.split("?")[0];
    if (path.endsWith("/me")) return json(me());
    if (path.endsWith("/question")) return json(question);
    return json({ kind, status: view === "join" ? "registration" : status, prize: "Botella de aguardiente", duration_seconds: 120, ends_at: iso(80000), now: new Date().toISOString(),
      brand, texts: { claim: "Reclama con tu documento", consent: "Autorizo el tratamiento de mis datos para este concurso" } });
  };

  function rgb(value) {
    const m = String(value || "").match(/rgba?\(([^)]+)\)/);
    const srgb = String(value || "").match(/color\(srgb ([^)]+)\)/);
    if (srgb) { const [r, g, b, a = 1] = srgb[1].split(/[ /]+/).filter(Boolean).map(Number); return { r: r * 255, g: g * 255, b: b * 255, a }; }
    if (!m) return null;
    const [r, g, b, a = 1] = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
    return { r, g, b, a };
  }
  function firstStop(img) {
    const s = String(img || "");
    if (!s.includes("gradient")) return null;
    const m = s.match(/(rgba?\([^)]+\)|color\(srgb [^)]+\))/);
    return m ? { ...rgb(m[1]), a: 1 } : null;
  }
  function lum({ r, g, b }) { const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); }
  function bgOf(el) {
    const layers = [];
    for (let n = el; n && n !== document.documentElement; n = n.parentElement) {
      const cs = getComputedStyle(n);
      const stop = n === document.body ? null : firstStop(cs.backgroundImage);
      if (stop) { layers.push(stop); break; }
      const c = rgb(cs.backgroundColor);
      if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; }
    }
    let base = { r: 11, g: 10, b: 20 };
    for (let i = layers.length - 1; i >= 0; i -= 1) { const l = layers[i]; base = { r: l.r * l.a + base.r * (1 - l.a), g: l.g * l.a + base.g * (1 - l.a), b: l.b * l.a + base.b * (1 - l.a) }; }
    return base;
  }
  function ratio(el) { const fg = rgb(getComputedStyle(el).color); const bg = bgOf(el); const a = lum(fg) + 0.05; const b = lum(bg) + 0.05; return Math.round((Math.max(a, b) / Math.min(a, b)) * 100) / 100; }

  function measure() {
    const root = document.getElementById(SCREEN ? "lgxScreen" : "lgxPlay");
    const out = document.createElement("pre");
    out.id = "layout";
    out.style.display = "none";
    const bad = [], low = [], small = [];
    const leaves = [...root.querySelectorAll("*")].filter((el) => el.offsetParent !== null && !el.closest("svg") && !/^(INPUT|IMG|I)$/.test(el.tagName)
      && [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()));
    for (const el of leaves) {
      if (el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).overflow !== "visible") bad.push({ cls: String(el.className), text: el.textContent.trim().slice(0, 30), sw: el.scrollWidth, cw: el.clientWidth });
      const r = ratio(el);
      if (r < 4.5) low.push({ cls: String(el.className), tag: el.tagName, text: el.textContent.trim().slice(0, 30), ratio: r });
      const fs = parseFloat(getComputedStyle(el).fontSize);
      if (SCREEN && fs < window.innerHeight * 0.021) small.push({ cls: String(el.className), text: el.textContent.trim().slice(0, 30), fs });
    }
    // Nombres cortados con "…" (no deberia pasar con 20 caracteres).
    root.querySelectorAll(".lgx-who, .lgx-pname").forEach((el) => { if (el.scrollWidth > el.clientWidth + 1) bad.push({ cls: String(el.className), text: el.textContent, cut: true }); });
    const vert = SCREEN ? root.scrollHeight > root.clientHeight + 1 : false;
    out.textContent = JSON.stringify({ mounted: root.children.length > 0, w: window.innerWidth, hgt: window.innerHeight, page_overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
      vert, bad, low_contrast: low, small, text: root.textContent.replace(/\s+/g, " ").trim().slice(0, 400),
      names: root.querySelectorAll(".lgx-names li").length, rank: root.querySelectorAll(".lgx-rank li").length, steps: root.querySelectorAll(".lgx-step").length,
      cards: root.querySelectorAll("[data-lgx-flip]").length, faces: root.querySelectorAll(".lgx-card3d.is-up").length, opts: root.querySelectorAll(".lgx-opt").length });
    document.body.appendChild(out);
  }
  window.addEventListener("load", () => setTimeout(measure, 2600));
})();
