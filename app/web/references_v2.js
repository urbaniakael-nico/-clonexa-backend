// Referencias v2 (interruptor references_v2): Catálogo comercial, Información
// de cortes y Estado de referencias. client.js solo la monta cuando el
// interruptor está encendido; la pantalla de siempre queda como respaldo.
// Datos: los endpoints de siempre (listado, resumen, PATCH, reset, archivar,
// export) y los nuevos /v2 (catálogo, clasificar, movimientos, balance).
(() => {
  "use strict";

  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const num = (v) => Number(v || 0) || 0;
  const fold = (v) => String(v ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const TABS = [["catalogo", "1 · Catálogo comercial"], ["cortes", "2 · Información de cortes"], ["estado", "3 · Estado de referencias"]];
  const SECTIONS = [["corte", "Corte"], ["bordado", "Bordado"], ["taller", "Taller"], ["lavado", "Lavado"], ["otro", "Otro"]];
  const TITLES = {
    catalogo: ["Catálogo comercial", "Crea referencias paso a paso: parte, prenda, talla y cantidad."],
    cortes: ["Información de cortes", "Recibe cortes, registra novedades por sección y envíos a despliegue."],
    estado: ["Estado de referencias", "Tus referencias actuales, agrupadas. Nada se borra ni se cambia."],
  };

  // ------------------------------------------------------------ ilustraciones
  const SVG = {
    chaqueta: '<path d="M22 10l-10 5-8 20 9 4 4-9v28h30V30l4 9 9-4-8-20-10-5-8 9z"/><path d="M32 19v38M26 35h6M26 41h6"/>',
    camiseta: '<path d="M22 10l-10 5-8 14 9 5 4-6v30h30V28l4 6 9-5-8-14-10-5c-2 5-6 8-10 8s-8-3-10-8z"/>',
    blusa: '<path d="M24 10l-10 6-8 16 8 4 5-8v30h26V28l5 8 8-4-8-16-10-6-8 10z"/><circle cx="32" cy="28" r="1.5"/><circle cx="32" cy="36" r="1.5"/>',
    buzo: '<path d="M22 12l-10 4-8 26 8 2 5-14v28h30V30l5 14 8-2-8-26-10-4c0 6-4 10-10 10s-10-4-10-10z"/><path d="M24 50h16"/>',
    top: '<path d="M22 12v10l-6 10v18h32V32l-6-10V12M22 22h20"/>',
    pantalon: '<path d="M18 8h28l4 50H36l-4-32-4 32H14z"/><path d="M18 16h28"/>',
    falda: '<path d="M20 10h24v8H20zM20 18L10 56h44L44 18M28 18l-4 38M36 18l4 38"/>',
    short: '<path d="M14 14h36l4 26H38l-6-12-6 12H10z"/><path d="M14 20h36"/>',
    leggings: '<path d="M22 6h20l2 54h-8l-4-40-4 40h-8z"/><path d="M22 12h20"/>',
    medias: '<path d="M26 6h12v28l12 10c3 3 1 10-4 10H30c-3 0-4-2-4-5z"/><path d="M26 12h12"/>',
    ropa_interior: '<path d="M8 16h48l-4 10c-6 4-12 10-14 22h-12c-2-12-8-18-14-22z"/><path d="M8 22h48"/>',
  };
  const icon = (code, cls = "") => `<svg class="rv-icon ${cls}" viewBox="0 0 64 64" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="3" stroke-linejoin="round" stroke-linecap="round">${SVG[code] || SVG.top}</svg>`;

  // ------------------------------------------------------------ estado
  const blankForm = () => ({ part: "", garment: "", sizes: {}, name: "", color: "" });
  const blankCut = () => ({ refId: "", date: today(), received: {}, novelties: {}, deploy: { quantity: "", size: "", date: today() } });
  const model = {
    tab: "catalogo", gender: "mujer", botVisible: true, form: blankForm(), cut: blankCut(),
    catalog: null, counts: {}, rows: [], extras: {}, balance: null, search: "", filterGender: "mujer", open: "", editing: "",
    notice: "", error: "", busy: false, voiding: "",
  };
  let ctx = null;
  let bound = false;

  function today() {
    try { return new Date().toLocaleDateString("en-CA", { timeZone: "America/Bogota" }); } catch (_) { return new Date().toISOString().slice(0, 10); }
  }

  // ------------------------------------------------------------ reglas puras
  function garmentsOf(catalog, part) { return arr(catalog && catalog.garments).filter((g) => g.body_part === part); }
  function garmentOf(catalog, code) { return arr(catalog && catalog.garments).find((g) => g.code === code) || null; }
  function sizesFor(catalog, gender, garmentCode) {
    const g = garmentOf(catalog, garmentCode);
    return g && catalog.sizes && catalog.sizes[gender] ? arr(catalog.sizes[gender][g.size_set]) : [];
  }

  function chosenSizes(form, catalog, gender) {
    const order = sizesFor(catalog, gender, form.garment);
    return order.filter((s) => Object.prototype.hasOwnProperty.call(form.sizes, s)).map((s) => ({ size: s, quantity: num(form.sizes[s]) }));
  }

  function summaryText(form, catalog, gender) {
    const g = garmentOf(catalog, form.garment);
    const lines = chosenSizes(form, catalog, gender);
    if (!g || !lines.length) return "";
    const label = gender === "hombre" ? "Hombre" : "Mujer";
    const total = lines.reduce((a, l) => a + l.quantity, 0);
    return `${g.label} · ${label} · ${lines.map((l) => `Talla ${l.size} → ${l.quantity}`).join(" · ")} · Total ${total}`;
  }

  function combined(size) { return String(size || "").includes(","); }

  function groups(rows) {
    const map = new Map();
    arr(rows).forEach((r) => {
      const key = [fold(r.name), fold(r.category), fold(r.color)].join("|");
      if (!map.has(key)) map.set(key, { key, name: r.name, color: r.color, category: r.category, rows: [] });
      map.get(key).rows.push(r);
    });
    return [...map.values()].sort((a, b) => fold(a.name).localeCompare(fold(b.name)));
  }

  function sizeKey(v) {
    const order = { xs: 0, s: 1, m: 2, l: 3, xl: 4, xxl: 5, unica: 6, "única": 6 };
    const s = String(v || "").trim().toLowerCase();
    if (/^\d+$/.test(s)) return [0, Number(s)];
    if (s in order) return [1, order[s]];
    return [2, 0, s];
  }
  const bySize = (a, b) => { const x = sizeKey(a), y = sizeKey(b); return x[0] - y[0] || x[1] - y[1] || String(x[2] || "").localeCompare(String(y[2] || "")); };

  // Tallas de una referencia para registrar cortes: una combinada se puede elegir por talla, pero la fila no se parte.
  function groupSizes(group) {
    const out = new Map();
    arr(group && group.rows).forEach((r) => String(r.size || "").split(",").map((s) => s.trim()).filter(Boolean).forEach((s) => { if (!out.has(s)) out.set(s, r.id); }));
    return [...out.keys()].sort(bySize).map((s) => ({ size: s, id: out.get(s) }));
  }

  function matchesGender(row, extra, filter) {
    if (filter === "todas") return true;
    const g = extra && extra.gender;
    if (filter === "hombre") return g === "hombre";
    return !g || g === "mujer"; // hoy todo es de mujer: lo no clasificado se ve en Mujer
  }

  function columns(rows, extras, { search = "", gender = "mujer" } = {}, catalog = null) {
    const q = fold(search).trim();
    const list = arr(rows).filter((r) => {
      const ex = (extras || {})[r.id] || {};
      if (!matchesGender(r, ex, gender)) return false;
      if (!q) return true;
      const g = garmentOf(catalog, ex.garment_type);
      return fold([r.name, r.category, r.size, r.color, r.sku, g && g.label].join(" ")).includes(q);
    });
    return { activas: list, visibles: list.filter((r) => r.bot_active === true), noVisibles: list.filter((r) => r.bot_active !== true) };
  }

  function nextChannel(row, visible) {
    const ch = String(row.channel || (row.bot_active ? "bot" : "system")).toLowerCase();
    if (visible) return ch === "system" ? "both" : ch === "both" ? "both" : "bot";
    return "system";
  }

  function rowPayload(row, patch = {}) {
    return { category: row.category || "", name: row.name || "", size: row.size || "", color: row.color || "", sku: row.sku || "",
      unit_price: num(row.unit_price), initial_quantity: num(row.initial_quantity), channel: row.channel || (row.bot_active ? "bot" : "system"), ...patch };
  }

  // ------------------------------------------------------------ api
  const base = () => `/references-v1/companies/${encodeURIComponent(ctx.companyId)}`;
  const call = (path, options = {}) => ctx.api(`${base()}${path}`, options);
  const post = (path, body) => call(path, { method: "POST", body: JSON.stringify(body || {}) });

  async function loadAll() {
    const [cat, list, summary, board] = await Promise.all([
      call("/v2/catalog"), call(""), call("/summary").catch(() => ({ by_reference_size: [] })), call("/v2/board").catch(() => ({ extras: {} })),
    ]);
    model.catalog = cat.catalog;
    model.counts = cat.counts || {};
    const byId = new Map(arr(summary.by_reference_size).map((r) => [String(r.id), r]));
    model.rows = arr(list.items).map((r) => ({ ...r, ...(byId.get(String(r.id)) || {}), channel: r.channel || (r.bot_active ? "bot" : "system") }));
    model.extras = board.extras || {};
  }

  function errorText(error) {
    const raw = String((error && error.message) || error || "");
    const m = raw.match(/"message"\s*:\s*"([^"]+)"/) || raw.match(/"detail"\s*:\s*"([^"]+)"/);
    return m ? m[1] : raw.replace(/^\d{3}\s+\S*\s*/, "") || "No se pudo completar.";
  }

  // ------------------------------------------------------------ vistas
  function head() {
    const [title, sub] = TITLES[model.tab];
    const company = (ctx && ctx.company && ctx.company.name) || "Empresa";
    return `<header class="client-hero rv-head"><div><p class="client-eyebrow">${h(company)} · Referencias</p><h1 class="client-title">${h(title)}</h1><p class="client-muted">${h(sub)}</p></div>
      <nav class="rv-tabs" role="tablist">${TABS.map(([k, l]) => `<button type="button" role="tab" class="rv-tab ${model.tab === k ? "client-btn is-on" : ""}" aria-selected="${model.tab === k}" data-rv-tab="${k}">${h(l)}</button>`).join("")}</nav></header>
      ${model.notice ? `<div class="rv-notice" role="status">${h(model.notice)}</div>` : ""}${model.error ? `<div class="rv-notice is-error" role="alert">${h(model.error)}</div>` : ""}`;
  }

  function genderSwitch(attr, value, withAll = false) {
    const opts = [["mujer", "Mujer"], ["hombre", "Hombre"]].concat(withAll ? [["todas", "Todas"]] : []);
    return `<div class="rv-seg" role="group">${opts.map(([k, l]) => `<button type="button" class="${value === k ? "client-btn is-on" : ""}" ${attr}="${k}">${h(l)}</button>`).join("")}</div>`;
  }

  function catalogView() {
    const c = model.catalog;
    if (!c) return `<p class="client-muted rv-muted">Cargando catálogo…</p>`;
    const f = model.form;
    const counts = (model.counts[model.gender] || { parts: {}, garments: {} });
    const g = garmentOf(c, f.garment);
    const part = arr(c.body_parts).find((p) => p.code === f.part);
    const route = [part && part.short, g && g.label, model.gender === "hombre" ? "Hombre" : "Mujer"].filter(Boolean).join(" › ");
    const partCard = (p) => {
      const n = counts.parts[p.code] || 0;
      return `<button type="button" class="rv-part ${f.part === p.code ? "is-on" : ""}" data-rv-part="${p.code}">${icon(p.code === "superior" ? "chaqueta" : "falda", p.code === "superior" ? "is-cyan" : "is-lime")}
        <span><b>${h(p.label)}</b><small>${h(p.hint)}</small><span class="rv-chips">${f.part === p.code ? `<i class="rv-chip is-lime">Seleccionada</i>` : ""}<i class="rv-chip">${n} referencia${n === 1 ? "" : "s"}</i></span></span></button>`;
    };
    const sizes = sizesFor(c, model.gender, f.garment);
    const text = summaryText(f, c, model.gender);
    return `<section class="client-panel rv-panel rv-bar"><div class="rv-bar-item"><span class="client-label rv-label">Género</span>${genderSwitch("data-rv-gender", model.gender)}</div>
        <label class="rv-bar-item rv-toggle"><span>Visible para bot</span><input type="checkbox" data-rv-bot ${model.botVisible ? "checked" : ""}><i aria-hidden="true"></i></label>
        <div class="rv-bar-item rv-route">Ruta: <b>${h(route || "—")}</b></div></section>
      <section class="client-panel rv-panel"><h2 class="client-eyebrow rv-step"><i>1</i>Elige la parte</h2><div class="rv-parts">${arr(c.body_parts).map(partCard).join("")}</div></section>
      ${f.part ? `<section class="client-panel rv-panel"><h2 class="client-eyebrow rv-step"><i>2</i>Elige la prenda<span class="rv-step-detail">&nbsp;· ${h(part.short)}</span></h2><div class="rv-garments rv-scroll">${garmentsOf(c, f.part).map((x) => `
        <button type="button" class="rv-garment ${f.garment === x.code ? "is-on" : ""}" data-rv-garment="${x.code}">${icon(x.code)}<b>${h(x.label)}</b><small>${counts.garments[x.code] || 0}${counts.garments[x.code] === 1 ? " referencia" : counts.garments[x.code] ? " referencias" : ""}</small></button>`).join("")}</div></section>` : ""}
      ${g ? `<section class="client-panel rv-panel"><h2 class="client-eyebrow rv-step"><i>3</i>Tallas y cantidades<span class="rv-step-detail">&nbsp;· ${h(g.label)} ${model.gender === "hombre" ? "Hombre" : "Mujer"}</span></h2>
        <div class="rv-sizes-grid"><div class="rv-sizes">${sizes.map((s) => {
          const on = Object.prototype.hasOwnProperty.call(f.sizes, s);
          return `<div class="rv-size"><button type="button" class="rv-size-btn ${on ? "is-on" : ""}" data-rv-size="${h(s)}" aria-pressed="${on}">${h(s)}</button>
            <input class="rv-qty" type="number" min="0" inputmode="numeric" placeholder="cantidad" data-rv-qty="${h(s)}" value="${on ? h(f.sizes[s]) : ""}" ${on ? "" : "disabled"} aria-label="Cantidad talla ${h(s)}"></div>`;
        }).join("")}</div>
        <div class="rv-fields"><label class="rv-field">Nombre de la referencia<input data-rv-name value="${h(f.name)}" maxlength="120" placeholder="Ej: PANT SET"></label>
          <label class="rv-field">Color<input data-rv-color value="${h(f.color)}" maxlength="60" placeholder="Ej: Marfil"></label></div></div>
        <div class="rv-summary"><p data-rv-summary>${text ? h(text) : "Marca al menos una talla con su cantidad."}</p>
          <div class="rv-actions"><button type="button" class="rv-btn" data-rv-clear>Limpiar</button><button type="button" class="client-btn rv-btn is-primary" data-rv-save ${model.busy ? "disabled" : ""}>Guardar referencia</button></div></div></section>` : ""}`;
  }

  function cutsView() {
    const gs = groups(model.rows);
    const group = gs.find((x) => x.rows.some((r) => r.id === model.cut.refId)) || null;
    const sizes = groupSizes(group);
    const cut = model.cut;
    const b = model.balance;
    const pct = b && b.received ? Math.max(0, Math.round((b.available / b.received) * 100)) : 0;
    return `<div class="rv-cuts"><div class="rv-cuts-main">
      <section class="client-panel rv-panel"><h2 class="client-eyebrow rv-step is-cyan"><i>1</i>Recepción del corte</h2>
        <div class="rv-fields rv-two"><label class="rv-field">Fecha de ingreso<input type="date" data-rv-cut="date" value="${h(cut.date)}"></label>
          <label class="rv-field">Referencia<select data-rv-cut-ref><option value="">Elige la referencia</option>${gs.map((x) => `<option value="${h(x.rows[0].id)}" ${group && group.key === x.key ? "selected" : ""}>${h(x.name)}${x.color ? ` · ${h(x.color)}` : ""}</option>`).join("")}</select></label></div>
        ${group ? `<span class="client-label rv-label">Talla y cantidad recibida</span><div class="rv-sizes">${sizes.map((s) => {
          const on = Object.prototype.hasOwnProperty.call(cut.received, s.size);
          return `<div class="rv-size"><button type="button" class="rv-size-btn ${on ? "is-on" : ""}" data-rv-recv="${h(s.size)}" aria-pressed="${on}">${h(s.size)}</button>
            <input class="rv-qty" type="number" min="0" inputmode="numeric" placeholder="cantidad" data-rv-recv-qty="${h(s.size)}" value="${on ? h(cut.received[s.size]) : ""}" ${on ? "" : "disabled"}></div>`;
        }).join("")}</div>` : `<p class="client-muted rv-muted">Elige una referencia para ver sus tallas.</p>`}</section>
      <section class="client-panel rv-panel"><h2 class="client-eyebrow rv-step is-red"><i>2</i>Novedades por sección</h2>
        <div class="rv-nov"><span class="client-label rv-label">Sección</span><span class="client-label rv-label">Observación</span><span class="client-label rv-label">Cantidad</span>
        ${SECTIONS.map(([k, l]) => { const n = cut.novelties[k] || {}; return `<span class="rv-sec is-${k}"><i></i>${h(l)}</span>
          <input data-rv-nov-note="${k}" value="${h(n.note || "")}" maxlength="500" placeholder="Escribe la observación…">
          <input type="number" min="0" inputmode="numeric" data-rv-nov-qty="${k}" value="${h(n.quantity || "")}" placeholder="0">`; }).join("")}</div></section>
      <section class="client-panel rv-panel"><h2 class="client-eyebrow rv-step is-violet"><i>3</i>Enviado a despliegue</h2><p class="client-muted rv-step-sub">Prenda terminada para fotos</p>
        <div class="rv-deploy"><label class="rv-field">Cantidad<input type="number" min="0" inputmode="numeric" data-rv-dep="quantity" value="${h(cut.deploy.quantity)}" placeholder="0"></label>
          <label class="rv-field">Talla<select data-rv-dep="size"><option value="">—</option>${sizes.map((s) => `<option ${cut.deploy.size === s.size ? "selected" : ""}>${h(s.size)}</option>`).join("")}</select></label>
          <label class="rv-field">Fecha de envío<input type="date" data-rv-dep="date" value="${h(cut.deploy.date)}"></label>
          <button type="button" class="client-btn rv-btn is-primary" data-rv-cut-save ${model.busy || !group ? "disabled" : ""}>Guardar registro</button></div></section></div>
      <aside class="rv-cuts-side">
        <section class="client-panel rv-panel"><h2 class="client-eyebrow rv-step is-cyan">Balance</h2>${group ? `<p class="client-muted rv-step-sub is-flat">${h(group.name)}${group.color ? ` · ${h(group.color)}` : ""}</p>` : ""}${b ? `
          <div class="rv-kpis"><div class="is-k-recv"><b>${h(b.received)}</b><small>Recibido</small></div><div class="is-k-nov"><b>${h(b.novelty)}</b><small>Con novedad</small></div>
            <div class="is-k-dep"><b>${h(b.deployed)}</b><small>A despliegue</small></div><div class="is-k-av"><b>${h(b.available)}</b><small>Disponible</small></div></div>
          <div class="rv-progress"><span style="--p:${Math.min(100, pct)}%"></span></div><p class="rv-muted rv-row"><span>Disponible = recibido − novedades − despliegue</span> <b class="rv-nowrap">${h(pct)}&nbsp;%</b></p>
          <p class="rv-note">El número <b>producido</b> no se toca. Cada novedad o envío queda como movimiento con fecha.</p>` : `<p class="client-muted rv-muted">Elige una referencia para ver su balance.</p>`}</section>
        <section class="client-panel rv-panel"><h2 class="client-eyebrow rv-step is-cyan">Bitácora de la referencia</h2>${b && arr(b.log).length ? `<ol class="rv-log rv-scroll">${arr(b.log).map(logItem).join("")}</ol>` : `<p class="client-muted rv-muted">Sin movimientos todavía.</p>`}</section>
      </aside></div>`;
  }

  function logItem(m) {
    const sec = (SECTIONS.find(([k]) => k === m.section) || [])[1];
    const what = m.kind === "ingreso" ? `Ingreso de corte · talla ${m.size} → ${m.quantity}`
      : m.kind === "despliegue" ? `Enviada${m.quantity === 1 ? "" : "s"} ${m.quantity} prenda${m.quantity === 1 ? "" : "s"}${m.size ? ` talla ${m.size}` : ""} a despliegue (fotos)`
        : `${sec} · ${m.quantity}${m.note ? ` · ${m.note}` : ""}`;
    const when = `${String(m.event_date || "").split("-").reverse().join("/")}${m.created_by ? ` · ${m.created_by}` : ""}`;
    const voided = !!m.voided_at;
    return `<li class="rv-log-item is-${m.kind === "novedad" ? "red" : m.kind === "despliegue" ? "violet" : "cyan"} ${voided ? "is-void" : ""}"><span>${h(what)}</span>
      <small>${h(when)}${voided ? ` · Anulado: ${h(m.void_reason || "")}` : ""}</small>
      ${voided ? "" : model.voiding === m.id ? `<span class="rv-void"><input data-rv-void-reason maxlength="300" placeholder="Motivo"><button type="button" class="rv-btn is-small" data-rv-void-go="${h(m.id)}">Anular</button><button type="button" class="rv-btn is-small" data-rv-void-cancel>Cancelar</button></span>`
        : `<button type="button" class="rv-link" data-rv-void="${h(m.id)}">Anular</button>`}</li>`;
  }

  function stateView() {
    const cols = columns(model.rows, model.extras, { search: model.search, gender: model.filterGender }, model.catalog);
    const col = (title, cls, list) => `<section class="client-panel rv-panel rv-col"><h2 class="client-eyebrow rv-col-head ${cls}">${h(title)}<b>${list.length}</b></h2>
      <div class="rv-col-list rv-scroll" data-rv-fit>${list.map((r) => card(r, title)).join("") || `<p class="client-muted rv-muted">Nada aquí.</p>`}</div>
      <p class="client-muted rv-more" data-rv-more hidden></p></section>`;
    return `<section class="client-panel rv-panel rv-bar"><input class="rv-search" type="search" data-rv-search value="${h(model.search)}" placeholder="Buscar por nombre, prenda, talla, color o SKU…" aria-label="Buscar">
        ${genderSwitch("data-rv-fgender", model.filterGender, true)}<button type="button" class="rv-btn" data-rv-export>Exportar CSV</button></section>
      <div class="rv-cols">${col("Activas", "is-lime", cols.activas)}${col("Visibles para bot", "is-cyan", cols.visibles)}${col("No visibles", "is-violet", cols.noVisibles)}</div>`;
  }

  function siblings(r) {
    const key = [fold(r.name), fold(r.category), fold(r.color)].join("|");
    return model.rows.filter((x) => [fold(x.name), fold(x.category), fold(x.color)].join("|") === key).length;
  }

  function card(r, column) {
    const ex = model.extras[r.id] || {};
    const g = garmentOf(model.catalog, ex.garment_type);
    const isCombined = ex.combined_sizes || combined(r.size);
    // "· talla X" solo si la referencia tiene una fila por talla; si no, la talla va abajo.
    const split = !isCombined && siblings(r) > 1;
    const title = split ? `${r.name} · talla ${r.size}` : r.name;
    const sub = [g ? g.label : r.category || "Sin categoría", ex.gender ? (ex.gender === "hombre" ? "Hombre" : "Mujer") : "", r.color, split ? "" : r.size].filter(Boolean).join(" · ");
    const meta = num(r.initial_quantity), done = num(r.finished_quantity), pending = r.pending_quantity != null ? num(r.pending_quantity) : Math.max(meta - done, 0);
    const pct = meta > 0 ? Math.min(100, Math.round((done / meta) * 100)) : 0;
    const key = `${column}:${r.id}`;
    const open = model.open === key;
    const sug = ex.suggestion;
    const sugG = sug && garmentOf(model.catalog, sug.garment_type);
    return `<article class="rv-card ${open ? "is-open" : ""}"><button type="button" class="rv-card-head" data-rv-open="${h(key)}" aria-expanded="${open}"><span><b>${h(title)}</b><small>${h(sub)}${isCombined ? ` <i class="rv-chip is-amber">Tallas combinadas</i>` : ""}</small></span><i aria-hidden="true">${open ? "▴" : "▾"}</i></button>
      <div class="rv-chips">${!ex.classified && !sugG ? `<i class="rv-chip is-cyan">Por clasificar</i>` : ""}
        <i class="rv-chip ${r.bot_active ? "is-lime" : "is-violet"}">${r.bot_active ? "Visible para bot" : "No visible"}</i></div>
      ${!ex.classified && sugG ? `<p class="rv-sug"><span><i class="rv-chip is-cyan">Por clasificar</i> Sugerencia: <b>${h(sugG.label)} · ${sug.gender === "hombre" ? "Hombre" : "Mujer"}</b></span><button type="button" class="rv-btn is-small" data-rv-confirm="${h(r.id)}">Confirmar</button></p>` : ""}
      <div class="rv-progress"><span style="--p:${pct}%"></span></div>
      <p class="rv-row"><span>Meta <b>${h(meta)}</b></span><span>Producido <b>${h(done)}</b></span><span>Pendiente <b>${h(pending)}</b></span></p>
      ${ex.deployed ? `<p class="rv-deploy-note">Enviada${ex.deployed.quantity === 1 ? "" : "s"} ${h(ex.deployed.quantity)} a despliegue el ${h(String(ex.deployed.last_date || "").split("-").reverse().join("/"))} (fotos)</p>` : ""}
      ${open ? cardBody(r, ex) : ""}</article>`;
  }

  function cardBody(r, ex) {
    if (model.editing === r.id) {
      const f = (name, label, type = "text") => `<label class="rv-field">${label}<input data-rv-edit="${name}" type="${type}" value="${h(r[name] ?? "")}"></label>`;
      return `<div class="rv-card-body"><div class="rv-fields rv-two">${f("name", "Nombre")}${f("category", "Categoría")}${f("size", "Talla / modelo")}${f("color", "Color")}${f("sku", "SKU")}${f("unit_price", "Precio unidad", "number")}${f("initial_quantity", "Meta operativa", "number")}</div>
        <div class="rv-actions"><button type="button" class="client-btn rv-btn is-primary" data-rv-edit-save="${h(r.id)}">Guardar</button><button type="button" class="rv-btn" data-rv-edit-cancel>Cancelar</button></div></div>`;
    }
    const c = model.catalog;
    const sug = ex.suggestion || {};
    const classify = ex.classified ? "" : `<div class="rv-classify"><span class="client-label rv-label">Clasificar</span>
      <select data-rv-cls-gender="${h(r.id)}">${[["mujer", "Mujer"], ["hombre", "Hombre"]].map(([k, l]) => `<option value="${k}" ${(sug.gender || "mujer") === k ? "selected" : ""}>${l}</option>`).join("")}</select>
      <select data-rv-cls-garment="${h(r.id)}"><option value="">Prenda…</option>${arr(c && c.garments).map((g) => `<option value="${g.code}" ${sug.garment_type === g.code ? "selected" : ""}>${h(g.label)}</option>`).join("")}</select>
      <button type="button" class="rv-btn is-small" data-rv-cls-go="${h(r.id)}">Confirmar clasificación</button></div>`;
    return `<div class="rv-card-body"><label class="rv-toggle rv-panel-inline"><span>Hacer visible para bot</span><input type="checkbox" data-rv-visible="${h(r.id)}" ${r.bot_active ? "checked" : ""}><i aria-hidden="true"></i></label>
      ${classify}<div class="rv-actions"><button type="button" class="rv-btn" data-rv-edit-open="${h(r.id)}">Editar</button><button type="button" class="rv-btn" data-rv-reset="${h(r.id)}">Reiniciar ciclo</button><button type="button" class="rv-btn" data-rv-archive="${h(r.id)}">Archivar</button></div></div>`;
  }

  function view() {
    const body = model.tab === "catalogo" ? catalogView() : model.tab === "cortes" ? cutsView() : stateView();
    return `<div class="rv-root" data-rv-root>${head()}${body}</div>`;
  }

  // Cada columna muestra solo tarjetas completas: su alto se recorta al borde de
  // la ultima que cabe y el pie dice cuantas quedan (se ven desplazando la lista).
  function fitLists(host) {
    if (!host || !host.querySelectorAll || typeof getComputedStyle !== "function") return;
    host.querySelectorAll("[data-rv-fit]").forEach((list) => {
      list.style.height = "";
      const cards = [...list.children].filter((c) => c.classList && c.classList.contains("rv-card"));
      const more = list.parentElement && list.parentElement.querySelector("[data-rv-more]");
      const limit = list.clientHeight;
      if (!cards.length || list.scrollHeight <= limit + 1) { if (more) more.hidden = true; return; }
      const top = list.getBoundingClientRect().top - list.scrollTop;
      let fit = 0, bottom = 0;
      cards.forEach((c) => { const b = c.getBoundingClientRect().bottom - top; if (b <= limit + 1) { fit += 1; bottom = b; } });
      if (fit && bottom > 0) list.style.height = `${Math.ceil(bottom + 2)}px`;
      if (more) { more.hidden = false; more.textContent = `+ ${cards.length - fit} más · desliza la lista para verlas`; }
    });
  }

  function draw() {
    if (!ctx) return;
    const host = ctx.host();
    if (!host) return;
    const active = document.activeElement;
    const keep = active && active.getAttribute ? ["data-rv-search", "data-rv-name", "data-rv-color"].find((a) => active.hasAttribute(a)) : null;
    const caret = keep ? active.selectionStart : null;
    host.innerHTML = view();
    fitLists(host);
    if (keep) { const again = host.querySelector(`[${keep}]`); if (again) { again.focus(); try { again.setSelectionRange(caret, caret); } catch (_) {} } }
  }

  // ------------------------------------------------------------ acciones
  async function run(fn, notice) {
    model.busy = true; model.error = ""; draw();
    try { await fn(); model.notice = notice || ""; } catch (error) { model.error = errorText(error); model.notice = ""; }
    finally { model.busy = false; draw(); }
  }

  async function reload() { await loadAll(); }

  async function loadBalance() {
    model.balance = model.cut.refId ? await call(`/v2/references/${encodeURIComponent(model.cut.refId)}/balance`) : null;
  }

  function cutItems() {
    const gs = groups(model.rows);
    const group = gs.find((x) => x.rows.some((r) => r.id === model.cut.refId));
    if (!group) return [];
    const ids = new Map(groupSizes(group).map((s) => [s.size, s.id]));
    const items = [];
    Object.entries(model.cut.received).forEach(([size, q]) => { if (num(q) > 0) items.push({ reference_id: ids.get(size) || group.rows[0].id, kind: "ingreso", size, quantity: num(q), event_date: model.cut.date }); });
    SECTIONS.forEach(([k]) => { const n = model.cut.novelties[k] || {}; if (num(n.quantity) > 0) items.push({ reference_id: group.rows[0].id, kind: "novedad", section: k, quantity: num(n.quantity), note: n.note || "", event_date: model.cut.date }); });
    const d = model.cut.deploy;
    if (num(d.quantity) > 0) items.push({ reference_id: ids.get(d.size) || group.rows[0].id, kind: "despliegue", size: d.size, quantity: num(d.quantity), event_date: d.date });
    return items;
  }

  function onClick(event) {
    const t = event.target;
    if (!ctx || !t || !t.closest || !t.closest("[data-rv-root]")) return;
    const f = model.form;
    const attr = (sel, a) => { const el = t.closest(`[${sel}]`); return el ? el.getAttribute(a || sel) : null; };
    let v;
    if ((v = attr("data-rv-tab"))) { model.tab = v; model.notice = ""; model.error = ""; draw(); return; }
    if ((v = attr("data-rv-gender"))) { model.gender = v; f.sizes = {}; draw(); return; }
    if ((v = attr("data-rv-part"))) { f.part = v; f.garment = ""; f.sizes = {}; draw(); return; }
    if ((v = attr("data-rv-garment"))) { f.garment = v; f.sizes = {}; draw(); return; }
    if ((v = attr("data-rv-size"))) { if (Object.prototype.hasOwnProperty.call(f.sizes, v)) delete f.sizes[v]; else f.sizes[v] = ""; draw(); return; }
    if (t.closest("[data-rv-clear]")) { model.form = blankForm(); model.notice = ""; draw(); return; }
    if (t.closest("[data-rv-save]")) {
      const lines = chosenSizes(f, model.catalog, model.gender);
      if (!f.name.trim()) { model.error = "Escribe el nombre de la referencia."; draw(); return; }
      if (!lines.length) { model.error = "Marca al menos una talla."; draw(); return; }
      const g = garmentOf(model.catalog, f.garment);
      run(async () => {
        await post("/v2/catalog-create", { name: f.name, color: f.color, gender: model.gender, body_part: g.body_part, garment_type: g.code, bot_visible: model.botVisible, sizes: lines });
        const text = summaryText(f, model.catalog, model.gender);
        model.form = blankForm();
        await reload();
        model.notice = `Referencia guardada: ${text}.`;
      });
      return;
    }
    if ((v = attr("data-rv-recv"))) { const r = model.cut.received; if (Object.prototype.hasOwnProperty.call(r, v)) delete r[v]; else r[v] = ""; draw(); return; }
    if (t.closest("[data-rv-cut-save]")) {
      const items = cutItems();
      if (!items.length) { model.error = "No hay cantidades para guardar."; draw(); return; }
      run(async () => { await post("/v2/movements", { items }); const id = model.cut.refId; model.cut = blankCut(); model.cut.refId = id; await loadBalance(); await reload(); }, "Registro guardado.");
      return;
    }
    if ((v = attr("data-rv-void"))) { model.voiding = v; draw(); return; }
    if (t.closest("[data-rv-void-cancel]")) { model.voiding = ""; draw(); return; }
    if ((v = attr("data-rv-void-go"))) {
      const reason = String((ctx.host().querySelector("[data-rv-void-reason]") || {}).value || "").trim();
      if (reason.length < 3) { model.error = "Escribe el motivo para anular."; draw(); return; }
      run(async () => { await post(`/v2/movements/${encodeURIComponent(v)}/void`, { reason }); model.voiding = ""; await loadBalance(); await reload(); }, "Movimiento anulado. Queda en la bitácora.");
      return;
    }
    if ((v = attr("data-rv-fgender"))) { model.filterGender = v; draw(); return; }
    if (t.closest("[data-rv-export]")) {
      const q = model.search ? `?q=${encodeURIComponent(model.search)}` : "";
      const a = document.createElement("a");
      a.href = `${ctx.apiBase}${base()}/export.csv${q}`;
      a.download = `clonexa_referencias_${ctx.companyId}_${today()}.csv`;
      document.body.appendChild(a); a.click(); a.remove();
      return;
    }
    if ((v = attr("data-rv-open"))) { model.open = model.open === v ? "" : v; model.editing = ""; draw(); return; }
    const row = (id) => model.rows.find((r) => r.id === id);
    if ((v = attr("data-rv-confirm"))) {
      const sug = (model.extras[v] || {}).suggestion || {};
      const g = garmentOf(model.catalog, sug.garment_type);
      if (!g) return;
      run(async () => { await post(`/v2/references/${encodeURIComponent(v)}/classify`, { gender: sug.gender || "mujer", body_part: g.body_part, garment_type: g.code }); await reload(); }, "Clasificación confirmada.");
      return;
    }
    if ((v = attr("data-rv-cls-go"))) {
      const host = ctx.host();
      const gender = (host.querySelector(`[data-rv-cls-gender="${v}"]`) || {}).value || "mujer";
      const g = garmentOf(model.catalog, (host.querySelector(`[data-rv-cls-garment="${v}"]`) || {}).value);
      if (!g) { model.error = "Elige la prenda."; draw(); return; }
      run(async () => { await post(`/v2/references/${encodeURIComponent(v)}/classify`, { gender, body_part: g.body_part, garment_type: g.code }); await reload(); }, "Clasificación confirmada.");
      return;
    }
    if ((v = attr("data-rv-edit-open"))) { model.editing = v; draw(); return; }
    if (t.closest("[data-rv-edit-cancel]")) { model.editing = ""; draw(); return; }
    if ((v = attr("data-rv-edit-save"))) {
      const r = row(v); if (!r) return;
      const host = ctx.host();
      const read = (n) => (host.querySelector(`[data-rv-edit="${n}"]`) || {}).value;
      const patch = { name: String(read("name") || "").trim(), category: String(read("category") || "").trim(), size: String(read("size") || "").trim(),
        color: String(read("color") || "").trim(), sku: String(read("sku") || "").trim(), unit_price: num(read("unit_price")), initial_quantity: num(read("initial_quantity")) };
      if (!patch.name || !patch.size) { model.error = "Nombre y talla/modelo son obligatorios."; draw(); return; }
      run(async () => { await call(`/${encodeURIComponent(v)}`, { method: "PATCH", body: JSON.stringify(rowPayload(r, patch)) }); model.editing = ""; await reload(); }, "Referencia actualizada.");
      return;
    }
    if ((v = attr("data-rv-reset"))) {
      const r = row(v); if (!r) return;
      const total = num(r.initial_quantity);
      if (!confirm(`Reiniciar ciclo de esta referencia con meta ${total}? El historial anterior queda guardado y el conteo activo empieza en cero.`)) return;
      run(async () => { await post(`/${encodeURIComponent(v)}/reset`, { initial_quantity: total, source: "client_panel" }); await reload(); }, "Referencia reiniciada. El historial anterior se conserva.");
      return;
    }
    if ((v = attr("data-rv-archive"))) {
      if (!confirm("¿Archivar esta referencia? No se borrará físicamente.")) return;
      run(async () => { await call(`/${encodeURIComponent(v)}`, { method: "DELETE" }); model.open = ""; await reload(); }, "Referencia archivada.");
    }
  }

  function onChange(event) {
    const t = event.target;
    if (!ctx || !t || !t.closest || !t.closest("[data-rv-root]")) return;
    if (t.hasAttribute("data-rv-bot")) { model.botVisible = !!t.checked; return; }
    if (t.hasAttribute("data-rv-cut-ref")) {
      model.cut = { ...blankCut(), refId: t.value, date: model.cut.date };
      run(loadBalance);
      return;
    }
    const vis = t.getAttribute("data-rv-visible");
    if (vis) {
      const r = model.rows.find((x) => x.id === vis);
      if (!r) return;
      run(async () => { await call(`/${encodeURIComponent(vis)}`, { method: "PATCH", body: JSON.stringify(rowPayload(r, { channel: nextChannel(r, t.checked) })) }); await reload(); },
        t.checked ? "Ahora es visible para el bot." : "Ya no es visible para el bot.");
      return;
    }
    if (t.getAttribute("data-rv-dep") === "size") { model.cut.deploy.size = t.value; }
  }

  function onInput(event) {
    const t = event.target;
    if (!ctx || !t || !t.closest || !t.closest("[data-rv-root]")) return;
    let v;
    if ((v = t.getAttribute("data-rv-qty")) !== null) { model.form.sizes[v] = t.value; const p = ctx.host().querySelector("[data-rv-summary]"); if (p) p.textContent = summaryText(model.form, model.catalog, model.gender) || "Marca al menos una talla con su cantidad."; return; }
    if (t.hasAttribute("data-rv-name")) { model.form.name = t.value; return; }
    if (t.hasAttribute("data-rv-color")) { model.form.color = t.value; return; }
    if ((v = t.getAttribute("data-rv-recv-qty")) !== null) { model.cut.received[v] = t.value; return; }
    if (t.getAttribute("data-rv-cut") === "date") { model.cut.date = t.value; return; }
    if ((v = t.getAttribute("data-rv-nov-note"))) { model.cut.novelties[v] = { ...(model.cut.novelties[v] || {}), note: t.value }; return; }
    if ((v = t.getAttribute("data-rv-nov-qty"))) { model.cut.novelties[v] = { ...(model.cut.novelties[v] || {}), quantity: t.value }; return; }
    if ((v = t.getAttribute("data-rv-dep"))) { model.cut.deploy[v] = t.value; return; }
    if (t.hasAttribute("data-rv-search")) { model.search = t.value; draw(); }
  }

  async function mount(context) {
    ctx = context;
    if (!bound && typeof document.addEventListener === "function") {
      document.addEventListener("click", onClick);
      document.addEventListener("change", onChange);
      document.addEventListener("input", onInput);
      if (typeof window.addEventListener === "function") window.addEventListener("resize", () => { if (ctx) fitLists(ctx.host()); });
      bound = true;
    }
    model.notice = ""; model.error = "";
    draw();
    try { await loadAll(); } catch (error) { model.error = errorText(error); }
    draw();
  }

  window.CxReferencesV2 = { mount, model, view, summaryText, sizesFor, garmentsOf, chosenSizes, columns, groups, groupSizes, nextChannel, rowPayload, cutItems, combined };
})();
