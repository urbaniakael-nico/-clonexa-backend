// Vista previa del portal para la prueba de desborde de Referencias v2: datos
// de ejemplo (sin servidor ni usuarios reales) con el tema de Velvet o de la
// demo. Al final mide cada elemento y deja el resultado en <pre id="layout">.
(() => {
  const P = new URLSearchParams(location.search);
  const THEMES = {
    velvet: { name: "Velvet", branding: { primary_color: "#a600ff", secondary_color: "#8cff00", background_color: "#00ffe1", text_color: "#000000", visual_preset: "custom", background_style: "holografico", background_mode: "gradient", surface_style: "glass", font_family: "Sora", card_style: "glass_premium", gradient_from: "#a600ff", gradient_to: "#8cff00", gradient_extra: "#00ffe1", gradient_angle: 135, mode: "dark", theme_mode: "dark" } },
    demo: { name: "Radio Despecho", branding: { primary_color: "#38bdf8", secondary_color: "#f8fafc", background_color: "#0b1220", text_color: "#f8fafc", visual_preset: "boardroom_dark", background_style: "corporate_dark", background_mode: "gradient", surface_style: "neon", font_family: "Manrope", card_style: "neon_border", gradient_from: "#0f172a", gradient_to: "#164e63", gradient_extra: "#111827", gradient_angle: 140, mode: "corporate", theme_mode: "corporate" } },
  };
  const T = THEMES[P.get("theme") || "velvet"];
  const CID = P.get("company_id");
  const rows = [
    { id: "p10", name: "PANT SET", category: "Pantalón", size: "10", color: "Marfil", bot_active: true, channel: "bot", initial_quantity: 30 },
    { id: "p12", name: "PANT SET", category: "Pantalón", size: "12", color: "Marfil", bot_active: false, channel: "system", initial_quantity: 20 },
    { id: "mj", name: "Mystic jacket", category: "Superior", size: "SM, MI", color: "Marfil", bot_active: true, channel: "bot", initial_quantity: 126 },
    { id: "mp", name: "Mystic pant", category: "", size: "4, 6, 8, 10, 12", color: "", bot_active: true, channel: "bot", initial_quantity: 114 },
    { id: "aa", name: "Aurora Azul 💙", category: "Chaqueta", size: "Sm-MI", color: "Azul", bot_active: false, channel: "system", initial_quantity: 0 },
    { id: "lg", name: "Leggings Deportivo Largo Edición Especial", category: "Leggings", size: "12", color: "Negro carbón", bot_active: true, channel: "bot", initial_quantity: 1250 }];
  const summary = { by_reference_size: [{ id: "mj", finished_quantity: 126, pending_quantity: 0 }, { id: "mp", finished_quantity: 114, pending_quantity: 0 }, { id: "p10", finished_quantity: 0, pending_quantity: 30 }, { id: "p12", finished_quantity: 0, pending_quantity: 20 }, { id: "aa", finished_quantity: 0, pending_quantity: 0 }, { id: "lg", finished_quantity: 1180, pending_quantity: 70 }] };
  const extras = { p10: { gender: "mujer", body_part: "inferior", garment_type: "pantalon", classified: true, deployed: { quantity: 1, last_date: "2026-10-06" } },
    p12: { gender: "mujer", body_part: "inferior", garment_type: "pantalon", classified: true },
    mj: { classified: false, combined_sizes: true, suggestion: { gender: "mujer", body_part: "superior", garment_type: "chaqueta" } },
    mp: { classified: false, combined_sizes: true, suggestion: { gender: "mujer", body_part: "inferior", garment_type: "pantalon" } },
    aa: { classified: false, suggestion: { gender: "mujer", body_part: "superior", garment_type: "chaqueta" } },
    lg: { classified: false, suggestion: { gender: "mujer", body_part: "inferior", garment_type: "leggings" } } };
  const balance = { received: 1250, novelty: 333, deployed: 1000, available: -83, log: [
    { id: "m5", kind: "despliegue", size: "10", quantity: 1, event_date: "2026-10-06", created_by: "Ana" },
    { id: "m4", kind: "novedad", section: "corte", quantity: 1, note: "pieza mal cortada en talla 12", event_date: "2026-10-06", created_by: "Ana" },
    { id: "m1", kind: "ingreso", size: "10", quantity: 30, event_date: "2026-10-06", created_by: "Ana" }] };
  if (P.get("small") === "1") Object.assign(balance, { received: 50, novelty: 3, deployed: 1, available: 46 });
  let catalog = null;
  const json = (b) => new Response(JSON.stringify(b), { status: 200, headers: { "content-type": "application/json" } });
  const real = window.fetch.bind(window);
  try { localStorage.setItem("clonexa_access_token", "preview"); } catch (_) {}
  window.fetch = async (url, opts) => {
    const u = String(url);
    if (!u.startsWith("/api/v1")) return real(url, opts);
    const p = u.slice(7).split("?")[0];
    if (p === `/companies/${CID}`) return json({ id: CID, name: T.name, slug: T.name.toLowerCase().replace(/ /g, "-"), status: "active" });
    if (p === `/companies/${CID}/experience`) return json({ company_id: CID, branding: T.branding });
    if (p === `/companies/${CID}/modules`) return json([{ id: "cm1", company_id: CID, module_id: "m1", enabled: true, settings: { references_v2: true }, module: { code: "references", name: "Referencias" } }]);
    if (p.endsWith("/v2/catalog")) { catalog = catalog || await real("/client-static/garment_catalog.json").then((r) => r.json()); return json({ catalog, counts: { mujer: { parts: { inferior: 3, superior: 2 }, garments: { pantalon: 3 } } } }); }
    if (p.endsWith("/summary")) return json(summary);
    if (p.endsWith("/v2/board")) return json({ extras });
    if (p.endsWith("/balance")) return json(balance);
    if (p === `/references-v1/companies/${CID}`) return json({ items: rows });
    return json({});
  };

  function setup() {
    const R = window.CxReferencesV2;
    const host = document.getElementById("cxReferencesV2Host050B");
    if (!R || !host || !R.model.catalog) return false;
    const m = R.model;
    m.tab = P.get("tab") || "catalogo";
    if (m.tab === "catalogo") { m.form.part = "inferior"; m.form.garment = "pantalon"; m.form.sizes = { 4: "30", 6: "20", 16: "1200" }; m.form.name = "PANT SET"; m.form.color = "Marfil"; }
    if (m.tab === "cortes") { m.cut.refId = "p10"; m.cut.received = { 10: "30", 12: "20" }; m.cut.novelties = { corte: { note: "Pieza mal cortada en talla 12", quantity: "1" } }; m.cut.deploy = { quantity: "1", size: "10", date: "2026-10-06" }; m.balance = balance; }
    if (m.tab === "estado") m.open = "No visibles:p12";
    host.innerHTML = R.view();
    return true;
  }

  function measure() {
    const root = document.querySelector(".rv-root");
    const bad = [];
    root.querySelectorAll("*").forEach((el) => {
      // Campos de texto libre se desplazan por dentro; los de cantidad (fichas de talla) deben mostrar su numero completo.
      if ((/^(INPUT|SELECT|TEXTAREA|OPTION)$/.test(el.tagName) && !el.classList.contains("rv-qty")) || el.closest("svg")) return;
      if (el.offsetParent === null && getComputedStyle(el).position !== "fixed") return; // oculto
      if (el.scrollWidth > el.clientWidth + 1) bad.push({ tag: el.tagName, cls: String(el.className || ""), text: (el.textContent || "").trim().slice(0, 40), sw: el.scrollWidth, cw: el.clientWidth });
    });
    const page = document.documentElement.scrollWidth > window.innerWidth + 1;
    // Las etiquetas de cada tarjeta van en fila (una al lado de otra).
    const stacked = [...root.querySelectorAll(".rv-chips")].filter((g) => g.offsetParent !== null && new Set([...g.children].map((c) => c.offsetTop)).size > 1)
      .map((g) => { const owner = g.closest(".rv-card, .rv-part") || g; const name = owner.querySelector("b"); return `${name ? name.textContent : "?"} (${g.clientWidth}px: ${[...g.children].map((c) => c.offsetWidth).join("+")})`; });
    const out = document.createElement("pre");
    out.id = "layout";
    out.textContent = JSON.stringify({ width: window.innerWidth, tab: P.get("tab"), page_overflow: page, bad, stacked });
    document.body.appendChild(out);
  }

  const go = () => {
    const btn = [...document.querySelectorAll(".client-nav button")].find((b) => /referencia/i.test(b.textContent));
    if (!btn) return setTimeout(go, 200);
    btn.click();
    const wait = () => (setup() ? setTimeout(measure, 1200) : setTimeout(wait, 200));
    setTimeout(wait, 400);
  };
  window.addEventListener("load", () => setTimeout(go, 300));
})();
