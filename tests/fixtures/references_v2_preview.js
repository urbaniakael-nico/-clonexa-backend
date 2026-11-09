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
  const balance = { reference: { id: "p10", name: "PANT SET", color: "Marfil" }, classified: true, catalog_sizes: ["4", "6", "8", "10", "12", "14", "16"], existing_sizes: ["10", "12"],
    received: 1250, novelty: 333, deployed: 1000, available: -83, received_by_date: [{ date: "2026-09-16", quantity: 1221 }, { date: "2026-10-06", quantity: 29 }], log: [
    { id: "m5", kind: "despliegue", size: "10", quantity: 1, event_date: "2026-10-06", created_by: "Ana" },
    { id: "m4", kind: "novedad", section: "corte", quantity: 1, note: "pieza mal cortada en talla 12 con una observación larga para ver que no se sale", event_date: "2026-10-06", created_by: "Ana" },
    { id: "m1", kind: "ingreso", size: "10", quantity: 30, event_date: "2026-10-06", created_by: "Ana" },
    { id: "m2", kind: "ingreso", size: "8", quantity: 6, event_date: "2026-10-06", created_by: "Ana", size_without_reference: true },
    { id: "m6", kind: "ingreso", size: "4", quantity: 1221, event_date: "2026-09-16", created_by: "Ana", size_without_reference: true },
    { id: "m7", kind: "ingreso", size: "6", quantity: 9, event_date: "2026-09-16", created_by: "Ana", size_without_reference: true, voided_at: "2026-09-17", void_reason: "doble" }] };
  if (P.get("small") === "1") Object.assign(balance, { received: 50, novelty: 3, deployed: 1, available: 46 });
  // Tarjeta única (una referencia = nombre + color) y orden operacional, como /v2/groups y /v2/op-order.
  const line = (size, id, o = {}) => ({ size, color: "", reference_id: id, solo_corte: !id, anchor_id: id ? null : "aa", meta: 0, produced: 0, pending: 0, bot_active: false, received: 0, combined: false, ...o });
  const cuts = (list) => list.map(([date, sizes, at]) => ({ date, sizes: sizes.map(([size, quantity]) => ({ size, quantity })), total: sizes.reduce((a, x) => a + x[1], 0), last_at: at || null }));
  const groups = [
    { key: "auroraazul💙|azul", name: "Aurora Azul 💙", color: "Azul", received: 36, produced: 9, meta: 0, percent: 25, solo_corte: ["S", "M"],
      colors: ["Azul"], pending: 0, cuts_by_date: cuts([["2026-10-06", [["S", 26], ["M", 10]], "2026-10-06T19:42:00Z"]]),
      lines: [line("S", null, { received: 26 }), line("SM", "aa", { produced: 9, bot_active: false, color: "Azul" }), line("M", null, { received: 10 })] },
    { key: "leggingsdeportivolargoedicionespecial|negrocarbon", name: "Leggings Deportivo Largo Edición Especial", color: "Negro carbón", received: 1250, produced: 1180, meta: 1250, percent: 94.4, solo_corte: [],
      lines: [line("12", "lg", { meta: 1250, produced: 1180, bot_active: true, received: 1250 })] },
    { key: "mysticjacket|marfil", name: "Mystic jacket", color: "Marfil", received: 0, produced: 126, meta: 126, percent: null, solo_corte: [],
      lines: [line("SM, MI", "mj", { meta: 126, produced: 126, bot_active: true, combined: true })] },
    { key: "mysticpant|", name: "Mystic pant", color: "", received: 0, produced: 114, meta: 114, percent: null, solo_corte: [],
      lines: [line("4, 6, 8, 10, 12", "mp", { meta: 114, produced: 114, bot_active: true, combined: true })] },
    { key: "pantset|marfil", name: "PANT SET", color: "Marfil", received: 1250, produced: 0, meta: 50, percent: 0, solo_corte: ["4", "6", "8"],
      colors: ["Marfil"], pending: 50, cuts_by_date: cuts([["2026-10-06", [["8", 6], ["10", 30]], "2026-10-06T21:10:00Z"], ["2026-09-16", [["4", 1221], ["6", 9]]]]),
      lines: [line("4", null, { received: 1221, anchor_id: "p10" }), line("6", null, { received: 9, anchor_id: "p10" }), line("8", null, { received: 6, anchor_id: "p10" }),
        line("10", "p10", { meta: 30, pending: 30, bot_active: true, received: 30, color: "Marfil" }), line("12", "p12", { meta: 20, pending: 20, received: 0 })] }];
  const opItems = [{ id: "i1", name: "Corte y trazo de piezas", minutes: 25, size: "", position: 0 }, { id: "i2", name: "Costura", minutes: 60, size: "", position: 1 },
    { id: "i3", name: "Botones y ojales", minutes: 27, size: "", position: 2 }, { id: "i4", name: "Bolsillo extra talla M", minutes: 5, size: "M", position: 3 }];
  const opData = { group: groups[0], settings: { value_per_garment: 24000 }, calc: { items: opItems }, sizes: ["S", "SM", "M"] };
  // reference_lifecycle: nombres anteriores, corrección, talla cerrada, solicitud del bot y cuenta por talla.
  const LIFE = P.get("life") === "1";
  const E2E = P.get("e2e") === "1";
  const LIFE_KEY = "pantset|marfil";
  const lifeAt = "2026-11-05T12:00:00Z";
  const lifeState = LIFE ? Object.fromEntries(groups.map((g) => [g.key, { former_names: [], renames: [], corrections: [], closes: [], reopened: [], requests: [], status: "open" }])) : null;
  let lifeAccount = null;
  if (LIFE && E2E) {
    // Clics reales: la talla 10 con producido 28 y ninguna talla cerrada.
    Object.assign(groups.find((g) => g.key === LIFE_KEY).lines.find((l) => l.size === "10"), { produced: 28, pending: 2 });
    lifeAccount = { total_sizes: 5, closed_sizes: 0, time: { total_seconds: 2033100, people: [{ name: "KRIS", total_seconds: 2033100 }], unclosed: [] }, totals: { closed_qty: 0, minutes_per_garment: null, labor_per_garment: null }, sizes: [] };
  } else if (LIFE) {
    lifeState[LIFE_KEY] = { former_names: ["Pantalón de la colección anterior con un nombre muy largo", "PANT"], renames: [{ old_name: "PANT", new_name: "PANT SET", actor: "Dueña de la empresa", at: lifeAt }],
      corrections: [{ size: "10", before: 28, after: 0, actor: "Dueña de la empresa", reason: "Se metió por error desde el bot con un motivo largo para ver que no se sale", at: lifeAt }],
      closes: [{ size: "12", closed_qty: 18, reason_code: "cierre_ciclo", reason_label: "Cierre de ciclo", actor: "Dueña de la empresa", at: lifeAt }], reopened: [{ size: "12", reason: "Faltó contar", actor: "Dueña", at: lifeAt }],
      requests: [{ id: "q1", size: "10", quantity: 12, received: 30, produced: 28, employee: "KRIS", at: lifeAt }], status: P.get("flow") === "closed" ? "closed" : "open" };
    lifeAccount = { total_sizes: 5, closed_sizes: 1, time: { total_seconds: 776340, people: [{ name: "KRIS", total_seconds: 776340 }], unclosed: [{ name: "TATA", started: lifeAt, reason: "abierta" }] },
      totals: { closed_qty: 18, minutes_per_garment: 245.5, labor_per_garment: 40900 },
      sizes: [{ size: "12", closed: true, closed_qty: 18, meta: 20, diff_meta: -2, received: 0, diff_received: 18, days: 12, seconds: 300000, minutes_per_garment: 245.5, labor_per_garment: 40900, reason_label: "Cierre de ciclo", reason_note: "Detalle largo del motivo del cierre de ciclo" }] };
  }
  // Cortes con clics reales (?cuts=1): una referencia recién creada (rojita medium S/M) y un
  // servidor de mentira que guarda los movimientos y devuelve balance y tarjeta con lo guardado.
  const CUTS = P.get("cuts") === "1";
  window.__cutPosts = [];
  const cutMoves = [];
  if (CUTS) {
    rows.push({ id: "rs", name: "rojita medium", category: "Chaqueta", size: "S", color: "rojo", bot_active: true, channel: "bot", initial_quantity: 46 },
      { id: "rm", name: "rojita medium", category: "Chaqueta", size: "M", color: "rojo", bot_active: true, channel: "bot", initial_quantity: 25 });
    extras.rs = { gender: "mujer", body_part: "superior", garment_type: "chaqueta", classified: true };
    extras.rm = { gender: "mujer", body_part: "superior", garment_type: "chaqueta", classified: true };
    // Al crearla (077A): la cantidad de cada talla es la recepción inicial, con la fecha de creación.
    const day = new Date().toLocaleDateString("en-CA", { timeZone: "America/Bogota" });
    cutMoves.push({ reference_id: "rs", kind: "ingreso", size: "S", quantity: 46, event_date: day, created_by: "Velvet Admin", origin: "recepcion_inicial" },
      { reference_id: "rm", kind: "ingreso", size: "M", quantity: 25, event_date: day, created_by: "Velvet Admin", origin: "recepcion_inicial" });
  }
  const rojita = () => {
    const live = cutMoves.filter((m) => !m.voided_at);
    const sum = (k, z) => live.filter((m) => m.kind === k && (!z || m.size === z)).reduce((a, m) => a + m.quantity, 0);
    const days = {};
    live.filter((m) => m.kind === "ingreso").forEach((m) => { const d = days[m.event_date] = days[m.event_date] || { date: m.event_date, sizes: {}, total: 0, last_at: null }; d.sizes[m.size] = (d.sizes[m.size] || 0) + m.quantity; d.total += m.quantity; });
    const ln = (size, id, meta) => line(size, id, { meta, pending: meta, bot_active: true, color: "rojo", received: sum("ingreso", size) });
    return { key: "rojitamedium", name: "rojita medium", color: "rojo", colors: ["rojo"], received: sum("ingreso"), produced: 0, meta: 71, pending: 71, percent: 0, solo_corte: [],
      cuts_by_date: Object.values(days).map((d) => ({ ...d, sizes: Object.entries(d.sizes).map(([size, quantity]) => ({ size, quantity })) })), lines: [ln("S", "rs", 46), ln("M", "rm", 25)],
      balance: { reference: { id: "rs", name: "rojita medium", color: "rojo" }, classified: true, catalog_sizes: ["S", "M", "L"], existing_sizes: ["M", "S"],
        received: sum("ingreso"), novelty: sum("novedad"), deployed: sum("despliegue"), available: sum("ingreso") - sum("novedad") - sum("despliegue"),
        received_by_date: Object.values(days).map((d) => ({ date: d.date, quantity: d.total })), log: cutMoves.map((m, i) => ({ id: `cm${i}`, ...m })), events: [{ kind: "creada", actor: "Velvet Admin", at: new Date().toISOString(), detail: {} }] } };
  };
  window.__lifePosts = [];
  let catalog = null;
  const json = (b) => new Response(JSON.stringify(b), { status: 200, headers: { "content-type": "application/json" } });
  const real = window.fetch.bind(window);
  try { localStorage.setItem("clonexa_access_token", "preview"); } catch (_) {}
  window.fetch = async (url, opts) => {
    const u = String(url);
    if (!u.startsWith("/api/v1")) return real(url, opts);
    const p = u.slice(7).split("?")[0];
    // Fase B: ?lang=en|fr simula una empresa en ese idioma (dólares y Chicago); sin lang, español, pesos y Bogotá.
    if (p.endsWith("/locale")) {
      const lang = new URLSearchParams(location.search).get("lang") || "es";
      return json(lang === "es" ? { currency: "COP", timezone: "America/Bogota", language: "es", decimals: 0 } : { currency: "USD", timezone: "America/Chicago", language: lang, decimals: 2 });
    }
    if (p === `/companies/${CID}`) return json({ id: CID, name: T.name, slug: T.name.toLowerCase().replace(/ /g, "-"), status: "active" });
    if (p === `/companies/${CID}/experience`) return json({ company_id: CID, branding: T.branding });
    if (p === `/companies/${CID}/modules`) return json([{ id: "cm1", company_id: CID, module_id: "m1", enabled: true, settings: { references_v2: true, reference_lifecycle: LIFE }, module: { code: "references", name: "Referencias" } }]);
    if (LIFE && p.includes("/reference-lifecycle/")) {
      if (p.endsWith("/state")) return json({ references: lifeState });
      if (p.endsWith("/account")) return json(lifeAccount);
      const body = JSON.parse((opts && opts.body) || "{}");
      window.__lifePosts.push({ path: p.split("/").pop(), body });
      if (p.endsWith("/produced-correction")) {
        const l = groups.find((g) => g.key === LIFE_KEY).lines.find((x) => x.reference_id === body.reference_id);
        lifeState[LIFE_KEY].corrections.unshift({ size: l.size, before: l.produced, after: body.new_value, actor: "Dueña", reason: body.reason, at: lifeAt });
        Object.assign(l, { produced: body.new_value, pending: Math.max(l.meta - body.new_value, 0) });
      }
      return json({ ok: true });
    }
    if (p.endsWith("/v2/catalog")) { catalog = catalog || await real("/client-static/garment_catalog.json").then((r) => r.json()); return json({ catalog, counts: { mujer: { parts: { inferior: 3, superior: 2 }, garments: { pantalon: 3 } } } }); }
    if (p.endsWith("/summary")) return json(summary);
    if (p.endsWith("/v2/board")) return json({ extras });
    if (CUTS && p.endsWith("/v2/movements")) {
      const body = JSON.parse((opts && opts.body) || "{}");
      window.__cutPosts.push(body);
      body.items.forEach((m) => cutMoves.push({ ...m, size: m.size || "", created_by: "Dueña" }));
      return json({ ok: true, count: body.items.length });
    }
    if (CUTS && p.endsWith("/v2/groups")) return json({ groups: [...groups, rojita()] });
    if (CUTS && /\/v2\/references\/r[sm]\/balance$/.test(p)) return json(rojita().balance);
    if (p.endsWith("/v2/groups")) return json({ groups });
    if (p.endsWith("/v2/op-order")) return json(opData);
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
    if (m.tab === "cortes" && !CUTS) { m.cut.refId = "p10"; m.cut.received = { 10: "30", 12: "20", 8: "6" }; m.logOpen = { "2026-09-16": true }; m.cut.novelties = { corte: { note: "Pieza mal cortada en talla 12", quantity: "1" } }; m.cut.deploy = { quantity: "1", size: "10", date: "2026-10-06" }; m.balance = balance; }
    if (m.tab === "estado" && P.get("modal") !== "0") R.openGroupModal(P.get("modal") || "pantset|marfil");
    if (m.tab === "orden") { m.op.key = groups[0].key; m.op.view = P.get("view") || ""; R.setOp(opData); }
    if (LIFE) {
      m.life = lifeState;
      m.lifeAccount[LIFE_KEY] = lifeAccount;
      const flow = { correct: { kind: "correct", step: 1, size: "10" }, correcterr: { kind: "correct", step: 1, size: "10", errors: { value: "Valor inválido", reason: "Escribe el motivo" } }, correct2: { kind: "correct", step: 2, size: "10" }, close: { kind: "close", step: 1, size: "10" },
        close2: { kind: "close", step: 2, size: "10" }, finish: { kind: "finish", step: 2, size: "10" }, rename: { kind: "rename", step: 1, size: "" }, rename2: { kind: "rename", step: 2, size: "" }, reopen: { kind: "reopen", step: 1, size: "12" } }[P.get("flow")];
      if (P.get("flow") === "edit") m.lifeEdit = LIFE_KEY;
      if (flow) m.lifeFlow = { key: LIFE_KEY, reason: "Se metió por error", code: "", note: "", checked: false, errors: {}, value: flow.kind === "rename" ? "PANT SET edición nueva" : "40", ...flow };
    }
    host.innerHTML = R.view();
    return true;
  }

  // ---------------------------------------------------------------- contraste AA (elementos de la tarjeta única y la orden operacional)
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
  const CONTRAST = [".rv-tl-nums span", ".rv-tl-cell", ".rv-life-err", ".rv-life-ok", ".rv-gline > *", ".rv-gfoot span", ".rv-gfoot b", ".rv-gcard .rv-card-head b", ".rv-gcard .rv-card-head small", ".rv-gmline .rv-gsize", ".rv-gmnums span",
    ".rv-gcolor", ".rv-gmcolor", ".rv-gcuts li > *", ".rv-op-row > span", ".rv-op-kpis b", ".rv-op-kpis small", ".rv-op-sz b", ".rv-op-szn", ".rv-op-sizes .rv-chip", ".rv-gbot .rv-chip"];

  function measure() {
    const root = document.querySelector(".rv-root");
    const bad = [];
    root.querySelectorAll("*").forEach((el) => {
      // Campos de texto libre se desplazan por dentro; los de cantidad (fichas de talla) deben mostrar su numero completo.
      if ((/^(INPUT|SELECT|TEXTAREA|OPTION)$/.test(el.tagName) && !el.classList.contains("rv-qty")) || el.closest("svg")) return;
      if (el.offsetParent === null && getComputedStyle(el).position !== "fixed") return; // oculto
      // Texto de ayuda ("cantidad") entero dentro de su campo vacio.
      if (el.tagName === "INPUT" && el.placeholder && !el.value) {
        const ph = getComputedStyle(el, "::placeholder");
        const cs = getComputedStyle(el);
        const ctx2 = (measure.c = measure.c || document.createElement("canvas")).getContext("2d");
        ctx2.font = `${ph.fontWeight || cs.fontWeight} ${ph.fontSize || cs.fontSize} ${cs.fontFamily}`;
        const need = ctx2.measureText(el.placeholder).width + parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
        if (need > el.clientWidth + 1) bad.push({ tag: "PLACEHOLDER", cls: String(el.className || ""), text: el.placeholder, sw: Math.ceil(need), cw: el.clientWidth });
      }
      if (el.scrollWidth > el.clientWidth + 1) bad.push({ tag: el.tagName, cls: String(el.className || ""), text: (el.textContent || "").trim().slice(0, 40), sw: el.scrollWidth, cw: el.clientWidth });
    });
    const page = document.documentElement.scrollWidth > window.innerWidth + 1;
    // Las etiquetas de cada tarjeta van en fila (una al lado de otra).
    const stacked = [...root.querySelectorAll(".rv-chips")].filter((g) => g.offsetParent !== null && new Set([...g.children].map((c) => c.offsetTop)).size > 1)
      .map((g) => { const owner = g.closest(".rv-card, .rv-part") || g; const name = owner.querySelector("b"); return `${name ? name.textContent : "?"} (${g.clientWidth}px: ${[...g.children].map((c) => c.offsetWidth).join("+")})`; });
    const out = document.createElement("pre");
    out.id = "layout";
    const low = [];
    CONTRAST.forEach((sel) => root.querySelectorAll(sel).forEach((el) => {
      if (el.offsetParent === null && !el.closest(".rv-modal")) return;
      if (!(el.textContent || "").trim()) return;
      const r = ratio(el);
      if (r < 4.5) low.push({ sel, text: (el.textContent || "").trim().slice(0, 30), ratio: r });
    }));
    out.textContent = JSON.stringify({ width: window.innerWidth, tab: P.get("tab"), page_overflow: page, bad, stacked, low_contrast: low });
    document.body.appendChild(out);
  }

  const go = () => {
    const btn = [...document.querySelectorAll(".client-nav button")].find((b) => /referenc|référence/i.test(b.textContent));
    if (!btn) return setTimeout(go, 200);
    btn.click();
    const wait = () => (setup() ? setTimeout(measure, 1200) : setTimeout(wait, 200));
    setTimeout(wait, 400);
  };
  window.addEventListener("load", () => setTimeout(go, 300));
})();
