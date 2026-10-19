// Nómina v2 (interruptor payroll_v2 del módulo payroll). client.js solo la
// monta cuando el interruptor está encendido; apagado, si el archivo no carga
// o con la normativa colombiana encendida, se sirve la pantalla de siempre.
// El cálculo NO cambia: usa el mismo endpoint de cálculo y el mismo flujo de
// "confirmar salida" (workforce-sessions/closures/confirm, una sola vez).
// Datos nuevos solo de lectura: /payroll/.../period-activity (qué hizo cada
// persona en cada turno según los módulos de la empresa) y
// /payroll/.../closures/preview (cómo quedaría antes de confirmar).
// Colores: solo los del tema; los pares que deben pasar AA se calculan aquí.
(() => {
  "use strict";

  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const num = (v) => { const n = Number(v); return Number.isFinite(n) ? n : 0; };
  const fold = (v) => String(v ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  // Fase A: la zona de la empresa (CxLocale); sin ella, Bogotá como siempre.
  const tzOf = () => (typeof window !== "undefined" && window.CxLocale && window.CxLocale.timezone) || "America/Bogota";
  const PANELS = { mesero: "Mesero", cocina: "Cocina", caja: "Caja", sales: "Ventas", store: "Tienda", inventory: "Inventario",
    logistics: "Logística", call_center: "Call Center", external: "Externo", other: "Otro" };
  const SORTS = [["total", "Total a pagar"], ["time", "Tiempo trabajado"], ["name", "Nombre"]];

  const model = { period: null, cfg: null, snapshot: null, activity: null, query: "", filter: "all", sort: "total", open: "",
    modal: null, notice: "", error: "", loading: false, cols: 4 };
  let ctx = null;
  let bound = false;
  let previewTimer = null;

  // ------------------------------------------------------------ formato
  function money(v) {
    if (typeof window !== "undefined" && window.CxLocale && window.CxLocale.foreign()) return window.CxLocale.money(num(v)); // Fase A: moneda de la empresa
    return `$${Math.round(num(v)).toLocaleString("es-CO")}`;
  }
  function hours(minutes) {
    const m = Math.max(0, Math.round(num(minutes)));
    return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`;
  }
  function parts(iso) {
    const d = new Date(iso || "");
    if (Number.isNaN(d.getTime())) return null;
    const f = new Intl.DateTimeFormat("sv-SE", { timeZone: tzOf(), year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(d);
    const [date, time] = f.split(" ");
    return { date, time, local: `${date}T${time}` };
  }
  function day(iso) {
    const d = new Date(iso || "");
    if (Number.isNaN(d.getTime())) return "—";
    // Fase B: días y meses en el idioma de la empresa (en español, es-CO como siempre).
    const loc = (typeof window !== "undefined" && window.CxI18n && window.CxI18n.locale()) || "es-CO";
    return new Intl.DateTimeFormat(loc, { timeZone: tzOf(), weekday: "short", day: "2-digit", month: "short" }).format(d);
  }
  const clock = (iso) => (parts(iso) || {}).time || "—";
  function initials(name) {
    const words = String(name || "?").trim().split(/\s+/).filter((w) => /^\p{L}/u.test(w));
    if (!words.length) return "?";
    return ((words[0] || "?")[0] + (words.length > 1 ? words[words.length - 1][0] : "")).toUpperCase();
  }

  // ------------------------------------------------------------ reglas puras
  // Una tarjeta por colaborador con tiempo en el periodo o con turnos por confirmar.
  function buildCards(snapshot, activity) {
    const docs = (activity && activity.documents) || {};
    const byId = new Map();
    arr(snapshot && snapshot.rows).forEach((r) => {
      const id = String(r.employee_id || "");
      byId.set(id, { id, name: r.employee_name || "Colaborador", role: r.employee_role || "", document: docs[id] || "",
        regular: num(r.regular_minutes), extra: num(r.extra_minutes), gross: num(r.gross_amount), discount: num(r.discount_amount),
        net: num(r.net_amount), shifts: arr(r.shifts), closed: num(r.closed_shifts), pending: [] });
    });
    arr(snapshot && snapshot.unverified_shifts).forEach((u) => {
      const id = String(u.employee_id || `sin-id:${u.employee_name || ""}`);
      if (!byId.has(id)) {
        byId.set(id, { id, name: u.employee_name || "Colaborador", role: "", document: docs[id] || "", regular: 0, extra: 0, gross: 0,
          discount: 0, net: 0, shifts: [], closed: 0, pending: [] });
      }
      byId.get(id).pending.push(u);
    });
    return [...byId.values()];
  }

  function visibleCards(cards, filter, query, sort) {
    const q = fold(query).trim();
    const list = arr(cards)
      .filter((c) => filter !== "pending" || c.pending.length)
      .filter((c) => !q || fold(`${c.name} ${c.document}`).includes(q));
    const by = {
      total: (a, b) => b.net - a.net || a.name.localeCompare(b.name, "es"),
      time: (a, b) => (b.regular + b.extra) - (a.regular + a.extra) || a.name.localeCompare(b.name, "es"),
      name: (a, b) => a.name.localeCompare(b.name, "es", { sensitivity: "base" }),
    };
    return list.sort(by[sort] || by.total);
  }

  function totalsOf(snapshot) {
    const t = (snapshot && snapshot.totals) || {};
    return { people: num(t.people), regular: num(t.regular_minutes), extra: num(t.extra_minutes), gross: num(t.gross_amount),
      discount: num(t.discount_amount), net: num(t.net_amount) };
  }

  const within = (iso, start, end) => { const t = Date.parse(iso || ""); return Number.isFinite(t) && t >= Date.parse(start) && t <= Date.parse(end); };
  const overlaps = (s, e, start, end) => Date.parse(s || "") <= Date.parse(end) && Date.parse(e || new Date().toISOString()) >= Date.parse(start);

  // Lo que hizo la persona en ESE turno, solo con datos de su empresa (vienen ya filtrados por company_id).
  function activityFor(activity, employeeId, shift) {
    const a = activity || {};
    const m = a.modules || {};
    const out = [];
    if (!shift || !shift.start || !shift.end) return out;
    if (m.panels && shift.mini_panel_session_id && a.panels && a.panels[shift.mini_panel_session_id]) {
      const p = a.panels[shift.mini_panel_session_id];
      const label = PANELS[p.panel_type] || p.panel_type || "Mini panel";
      const extra = [];
      if (m.orders && p.panel_type === "mesero") extra.push(`${num(p.orders_taken)} pedidos tomados (${money(p.orders_taken_total)})`);
      if (m.orders && p.panel_type === "cocina") extra.push(`${num(p.orders_ready)} pedidos listos`);
      if (m.orders && p.panel_type === "caja") extra.push(`${num(p.charges)} cobros (${money(p.charges_total)})`);
      out.push({ kind: "panel", text: `${label} · conexión ${clock(p.start)} · salida ${p.end ? clock(p.end) : "abierta"}`, extra: extra.join(" · ") });
    }
    if (m.gps) {
      const points = arr((a.gps || {})[employeeId]).filter((g) => within(g.at, shift.start, shift.end));
      if (points.length) {
        const first = points[0];
        const names = [...new Set(points.map((g) => g.perimeter).filter(Boolean))];
        out.push({ kind: "gps", text: `Ubicación: ${names.length ? names.join(", ") : (first.status || "fuera de los perímetros")}`,
          extra: `${points.length} ${points.length === 1 ? "registro" : "registros"} GPS`,
          map: `https://www.google.com/maps?q=${encodeURIComponent(`${first.lat},${first.lng}`)}` });
      }
    }
    if (m.references) {
      const sessions = arr((a.references || {})[employeeId]).filter((r) => overlaps(r.start, r.end, shift.start, shift.end));
      const closures = arr((a.reference_closures || {})[employeeId]).filter((c) => within(c.at, shift.start, shift.end));
      if (sessions.length || closures.length) {
        const refs = [...new Set(sessions.map((r) => r.reference).filter(Boolean))];
        const qty = closures.reduce((s, c) => s + num(c.quantity), 0);
        out.push({ kind: "references", text: `Referencias: ${refs.length ? refs.join(", ") : closures.map((c) => c.reference).join(", ")}`,
          extra: closures.length ? `${qty} unidades terminadas (${closures.map((c) => `${c.reference}${c.size ? ` talla ${c.size}` : ""} × ${num(c.quantity)}`).join(" · ")})` : "" });
      }
    }
    return out;
  }

  // ------------------------------------------------------------ contraste
  function parse(value) {
    const srgb = String(value || "").match(/color\(srgb ([^)]+)\)/);
    if (srgb) { const p = srgb[1].split(/[ /]+/).filter(Boolean).map(Number); return { r: Math.round(p[0] * 255), g: Math.round(p[1] * 255), b: Math.round(p[2] * 255) }; }
    const m = String(value || "").match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
    return { r: p[0], g: p[1], b: p[2] };
  }
  function lum(c) { const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); }
  function contrast(a, b) { const x = lum(a) + 0.05; const y = lum(b) + 0.05; return Math.max(x, y) / Math.min(x, y); }
  function mix(c, t, k) { return { r: Math.round(c.r + (t.r - c.r) * k), g: Math.round(c.g + (t.g - c.g) * k), b: Math.round(c.b + (t.b - c.b) * k) }; }
  const css = (c) => `rgb(${c.r}, ${c.g}, ${c.b})`;
  function pair(bg, candidates, goal = 4.5) {
    const fgs = candidates.filter(Boolean);
    let best = fgs[0];
    fgs.forEach((c) => { if (contrast(bg, c) > contrast(bg, best)) best = c; });
    if (contrast(bg, best) >= goal) return { bg, fg: best };
    const toward = lum(best) > 0.4 ? { r: 0, g: 0, b: 0 } : { r: 255, g: 255, b: 255 };
    for (let k = 0.05; k <= 1.0001; k += 0.05) { const next = mix(bg, toward, k); if (contrast(next, best) >= goal) return { bg: next, fg: best }; }
    return { bg: toward, fg: best };
  }
  // Un color del tema usado como texto sobre la superficie: se ajusta hasta pasar AA.
  function inkOn(surface, color, goal = 4.5) {
    if (contrast(surface, color) >= goal) return color;
    const toward = lum(surface) > 0.4 ? { r: 0, g: 0, b: 0 } : { r: 255, g: 255, b: 255 };
    for (let k = 0.05; k <= 1.0001; k += 0.05) { const next = mix(color, toward, k); if (contrast(surface, next) >= goal) return next; }
    return toward;
  }
  function themeColor(root, expr) {
    const probe = document.createElement("span");
    probe.style.color = expr;
    probe.style.display = "none";
    root.appendChild(probe);
    const value = parse(getComputedStyle(probe).color);
    probe.remove();
    return value;
  }
  function applyContrast(root) {
    if (!root || typeof getComputedStyle !== "function") return;
    const text = themeColor(root, "var(--cx-text)") || { r: 255, g: 255, b: 255 };
    const bg = themeColor(root, "var(--cx-bg)") || { r: 15, g: 23, b: 42 };
    const primary = themeColor(root, "var(--cx-primary)") || bg;
    const warning = themeColor(root, "var(--cx-warning, #b45309)") || primary;
    const surface = pair(bg, [text], 7);
    const head = pair(primary, [text, surface.bg]);
    const set = (k, v) => root.style.setProperty(k, v);
    set("--pv-surface", css(surface.bg));
    set("--pv-on-surface", css(surface.fg));
    set("--pv-accent-bg", css(head.bg));
    set("--pv-accent-fg", css(head.fg));
    set("--pv-warn-ink", css(inkOn(surface.bg, warning)));
  }

  // ------------------------------------------------------------ dibujo
  function statusText() {
    const cfg = model.cfg;
    const p = model.period || {};
    if (cfg && cfg.enabled && cfg.period) {
      const exact = cfg.period.period_start === p.from && cfg.period.period_end === p.to;
      if (!exact) return "Fechas elegidas a mano";
      return cfg.period.closed ? "Periodo cerrado" : "Periodo abierto";
    }
    return "Periodo abierto";
  }

  function topBar() {
    const p = model.period || {};
    const cfg = model.cfg;
    return `<header class="client-hero pv-bar">
      <div class="pv-title"><div class="client-eyebrow">Nómina</div><h1 class="client-title">Nómina</h1></div>
      <span class="pv-status" data-pv-status>${h(statusText())}</span>
      <label class="pv-date"><span>Desde</span><input type="date" data-pv-from value="${h(p.from || "")}"></label>
      <label class="pv-date"><span>Hasta</span><input type="date" data-pv-to value="${h(p.to || "")}"></label>
      <div class="pv-bar-actions">
        <button class="pv-btn-primary" type="button" data-pv-calc>Calcular periodo</button>
        <button class="client-btn" type="button" data-pv-refresh>Actualizar</button>
        <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
      </div>
      ${cfg && cfg.enabled ? `<div class="pv-cutnav" aria-label="Periodos de corte">
        <button class="client-btn" type="button" data-pv-shift="prev">‹ Periodo anterior</button>
        <button class="client-btn" type="button" data-pv-shift="current">Periodo actual</button>
        <button class="client-btn" type="button" data-pv-shift="next">Periodo siguiente ›</button>
        <span class="pv-sub">${h((cfg.period && cfg.period.headline) || "")}</span></div>` : ""}
    </header>`;
  }

  function strip() {
    const t = totalsOf(model.snapshot);
    const cell = (label, value, hl) => `<div class="pv-stat${hl ? " is-total" : ""}"><span>${h(label)}</span><strong>${h(value)}</strong></div>`;
    return `<section class="pv-strip" aria-label="Resumen del periodo">
      ${cell("Colaboradores", String(t.people))}${cell("Horas ordinarias", hours(t.regular))}${cell("Horas extra", hours(t.extra))}
      ${cell("Bruto", money(t.gross))}${cell("Descuentos", money(t.discount))}${cell("Total a pagar", money(t.net), true)}
    </section>`;
  }

  function alerts() {
    const s = model.snapshot || {};
    const out = [];
    const missing = arr(s.missing_rate_employees);
    if (missing.length) out.push(`<div class="pv-alert" role="status"><strong>Sin valor hora (${missing.length})</strong>: ${missing.map((m) => h(m.employee_name)).join(", ")}. Esas horas quedaron en $0.</div>`);
    const pending = arr(s.unverified_shifts);
    if (pending.length) {
      const mins = pending.reduce((a, u) => a + num(u.minutes), 0);
      out.push(`<div class="pv-alert" role="status"><strong>⚠ ${pending.length} ${pending.length === 1 ? "turno" : "turnos"} por confirmar</strong>: ${h(hours(mins))} fuera de la liquidación hasta registrar la hora real de salida (una sola vez).</div>`);
    }
    return out.join("");
  }

  function toolbar(cards) {
    const pending = cards.filter((c) => c.pending.length).length;
    return `<div class="pv-tools">
      <input class="pv-search" type="search" data-pv-search value="${h(model.query)}" placeholder="Nombre o documento" aria-label="Buscar colaborador por nombre o documento">
      <div class="pv-filters" role="group" aria-label="Filtrar colaboradores">
        <button type="button" class="pv-filter ${model.filter === "all" ? "is-active" : ""}" aria-pressed="${model.filter === "all"}" data-pv-filter="all">Todos <b>${cards.length}</b></button>
        <button type="button" class="pv-filter ${model.filter === "pending" ? "is-active" : ""}" aria-pressed="${model.filter === "pending"}" data-pv-filter="pending">Por confirmar <b>${pending}</b></button>
      </div>
      <label class="pv-sort"><span>Ordenar por</span><select data-pv-sort>${SORTS.map(([k, l]) => `<option value="${k}" ${model.sort === k ? "selected" : ""}>${l}</option>`).join("")}</select></label>
    </div>`;
  }

  function card(c) {
    const open = model.open === c.id;
    return `<button type="button" class="pv-card ${c.pending.length ? "is-pending" : ""} ${open ? "is-open" : ""}" data-pv-card="${h(c.id)}" aria-expanded="${open}" aria-controls="pv-detail-${h(c.id)}">
      <span class="pv-avatar" aria-hidden="true">${h(initials(c.name))}</span>
      <span class="pv-card-main"><span class="pv-name">${h(c.name)}</span><span class="pv-role">${h(c.role || "Sin rol")}</span>
        ${c.pending.length ? `<span class="pv-flag">⚠ Confirmar salida</span>` : ""}</span>
      <span class="pv-card-nums"><span class="pv-time">${h(hours(c.regular + c.extra))}</span><span class="pv-net">${h(money(c.net))}</span></span>
      <span class="pv-arrow" aria-hidden="true">${open ? "▴" : "▾"}</span>
    </button>`;
  }

  function shiftRow(c, s) {
    const acts = activityFor(model.activity, c.id, s);
    return `<li class="pv-shift">
      <div class="pv-shift-main">
        <span class="pv-shift-day">${h(day(s.start))}</span>
        <span>${h(clock(s.start))} → ${h(clock(s.end))}</span>
        <span class="pv-sub">Pausas ${h(hours(s.pause_minutes))}</span>
        <span>Ord. ${h(hours(s.regular_minutes))}</span>
        <span>Extra ${h(hours(s.extra_minutes))}</span>
        <strong class="pv-shift-value">${h(money(s.gross_amount))}</strong>
      </div>
      ${acts.map((a) => `<div class="pv-act pv-act-${a.kind}"><span>${h(a.text)}</span>${a.extra ? `<span class="pv-sub">${h(a.extra)}</span>` : ""}${a.map ? `<a class="pv-map" href="${h(a.map)}" target="_blank" rel="noopener noreferrer">Ver en el mapa</a>` : ""}</div>`).join("")}
    </li>`;
  }

  // ------------------------------------------------------------ 056E: desglose en lista (payroll_shift_list)
  // Solo presentacion: cada turno es una tarjeta (fecha y rango arriba; Pausas, Horas
  // ordinarias, Horas extra y Referencias en filas) y al final una tarjeta de TOTAL.
  const listOn = () => !!(model.activity && model.activity.ui && model.activity.ui.shift_list === true);
  const T = (text) => (typeof window !== "undefined" && window.CxI18n && typeof window.CxI18n.t === "function" ? window.CxI18n.t(text) : text);

  function dayLong(iso) {
    const d = new Date(iso || "");
    if (Number.isNaN(d.getTime())) return "—";
    const loc = (typeof window !== "undefined" && window.CxI18n && window.CxI18n.locale()) || "es-CO";
    const text = new Intl.DateTimeFormat(loc, { timeZone: tzOf(), weekday: "short", day: "numeric", month: "short" }).format(d).replace(/\./g, "");
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  function shiftRefs(c, s) {
    const a = model.activity || {};
    if (!(a.modules || {}).references) return [];
    const names = arr((a.references || {})[c.id]).filter((r) => overlaps(r.start, r.end, s.start, s.end)).map((r) => r.reference);
    arr((a.reference_closures || {})[c.id]).filter((x) => within(x.at, s.start, s.end)).forEach((x) => names.push(x.reference));
    return [...new Set(names.filter(Boolean))];
  }

  function shiftCard(c, s) {
    const refs = shiftRefs(c, s);
    const acts = activityFor(model.activity, c.id, s).filter((a) => a.kind !== "references");
    return `<li class="pv-shift pv-scard">
      <div class="pv-scard-top"><span class="pv-scard-when"><b>${h(dayLong(s.start))}</b> · ${h(clock(s.start))} → ${h(clock(s.end))}</span>
        <strong class="pv-shift-value">${h(money(s.gross_amount))}</strong></div>
      <dl class="pv-scard-rows">
        <div><dt>${h(T("Pausas"))}</dt><dd>${h(hours(s.pause_minutes))}</dd></div>
        <div><dt>${h(T("Horas ordinarias"))}</dt><dd>${h(hours(s.regular_minutes))}</dd></div>
        <div><dt>${h(T("Horas extra"))}</dt><dd>${h(hours(s.extra_minutes))}</dd></div>
        <div><dt>${h(T("Referencias"))}</dt><dd>${refs.length ? h(refs.join(", ")) : "—"}</dd></div>
      </dl>
      ${acts.map((a) => `<div class="pv-act pv-act-${a.kind}"><span>${h(a.text)}</span>${a.extra ? `<span class="pv-sub">${h(a.extra)}</span>` : ""}${a.map ? `<a class="pv-map" href="${h(a.map)}" target="_blank" rel="noopener noreferrer">Ver en el mapa</a>` : ""}</div>`).join("")}
    </li>`;
  }

  // TOTAL = suma de los turnos que se ven arriba (mismos numeros de la nomina).
  function shiftTotals(c) {
    const refs = new Set();
    let regular = 0;
    let extra = 0;
    c.shifts.forEach((s) => { regular += num(s.regular_minutes); extra += num(s.extra_minutes); shiftRefs(c, s).forEach((r) => refs.add(r)); });
    return { shifts: c.shifts.length, regular, extra, refs: [...refs] };
  }

  function totalCard(c) {
    const t = shiftTotals(c);
    return `<li class="pv-shift pv-scard pv-scard-total" aria-label="${h(T("Total"))}">
      <div class="pv-scard-top"><span class="pv-scard-when"><b>${h(T("TOTAL"))}</b></span></div>
      <dl class="pv-scard-rows">
        <div><dt>${h(T("Turnos"))}</dt><dd>${h(t.shifts)}</dd></div>
        <div><dt>${h(T("Horas ordinarias"))}</dt><dd>${h(hours(t.regular))}</dd></div>
        <div><dt>${h(T("Horas extra"))}</dt><dd>${h(hours(t.extra))}</dd></div>
        <div><dt>${h(T("Referencias trabajadas"))}</dt><dd>${t.refs.length ? `${h(t.refs.length)} · ${h(t.refs.join(", "))}` : "0"}</dd></div>
      </dl>
    </li>`;
  }

  function pendingRow(u, index) {
    return `<li class="pv-shift is-pending">
      <button type="button" class="pv-pending-btn" data-pv-confirm="${h(index)}">
        <span class="pv-shift-day">${h(day(u.start))}</span>
        <span>${h(clock(u.start))} → ${h(clock(u.end))} <span class="pv-sub">(lo cerró el sistema)</span></span>
        <span>${h(hours(u.minutes))} sin liquidar</span>
        <span class="pv-flag">⚠ Confirmar salida</span>
      </button>
    </li>`;
  }

  function detail(c) {
    const pendingIndex = (u) => arr(model.snapshot && model.snapshot.unverified_shifts).indexOf(u);
    return `<section class="pv-detail" id="pv-detail-${h(c.id)}" aria-label="Registro de ${h(c.name)}">
      <div class="pv-detail-head"><span>${c.document ? `Documento ${h(c.document)}` : "Sin documento"}</span>
        <span>${h(c.closed)} ${c.closed === 1 ? "turno" : "turnos"}</span><span>Extras ${h(hours(c.extra))}</span>
        <span>Bruto ${h(money(c.gross))} · descuentos ${h(money(c.discount))}</span></div>
      <ul class="pv-shifts">
        ${c.pending.map((u) => pendingRow(u, pendingIndex(u))).join("")}
        ${c.shifts.slice().sort((a, b) => Date.parse(a.start) - Date.parse(b.start)).map((s) => (listOn() ? shiftCard(c, s) : shiftRow(c, s))).join("")}
        ${!c.shifts.length && !c.pending.length ? `<li class="pv-sub">Sin turnos en el periodo.</li>` : ""}
        ${listOn() && c.shifts.length ? totalCard(c) : ""}
      </ul>
    </section>`;
  }

  // La tarjeta abierta se despliega debajo de SU fila, a todo el ancho.
  function grid(list) {
    const cols = Math.max(1, model.cols);
    const out = [];
    list.forEach((c, i) => {
      out.push(card(c));
      const rowEnd = (i % cols === cols - 1) || i === list.length - 1;
      if (rowEnd) {
        const rowStart = i - (i % cols);
        const openCard = list.slice(rowStart, i + 1).find((x) => x.id === model.open);
        if (openCard) out.push(detail(openCard));
      }
    });
    return `<div class="pv-grid" data-pv-grid>${out.join("")}</div>`;
  }

  function modalView() {
    const md = model.modal;
    if (!md) return "";
    const u = md.item;
    const p = md.preview;
    const minLocal = (parts(u.start) || {}).local || "";
    const maxLocal = (parts(u.end) || {}).local || "";
    const row = (label, before, after) => `<tr><th scope="row">${h(label)}</th><td>${h(before)}</td><td>${h(after)}</td></tr>`;
    return `<div class="pv-modal" data-pv-modal>
      <div class="pv-modal-card" role="dialog" aria-modal="true" aria-labelledby="pvModalTitle">
        <div class="pv-modal-head"><h2 id="pvModalTitle">Confirmar salida · ${h(u.employee_name || "Colaborador")}</h2>
          <button type="button" class="pv-x" data-pv-close aria-label="Cerrar">✕</button></div>
        <dl class="pv-kv"><div><dt>Entrada</dt><dd>${h(day(u.start))} ${h(clock(u.start))}</dd></div>
          <div><dt>La cerró el sistema</dt><dd>${h(day(u.end))} ${h(clock(u.end))}</dd></div>
          ${u.declared_end_at ? `<div><dt>Hora que propuso el empleado</dt><dd>${h(day(u.declared_end_at))} ${h(clock(u.declared_end_at))}</dd></div>` : ""}</dl>
        <label class="pv-field"><span>Hora real de salida</span><input type="datetime-local" data-pv-real-end value="${h(md.realEnd || "")}" min="${h(minLocal)}" max="${h(maxLocal)}"></label>
        <label class="pv-field"><span>Nota (opcional)</span><textarea data-pv-note rows="2" maxlength="300" placeholder="Por qué esta hora">${h(md.note || "")}</textarea></label>
        <div class="pv-preview" aria-live="polite">${p ? `<table class="pv-preview-table"><thead><tr><th scope="col"></th><th scope="col">Hoy</th><th scope="col">Al confirmar</th></tr></thead><tbody>
          ${row("Horas ordinarias", hours(p.before.regular_minutes), hours(p.after.regular_minutes))}
          ${row("Horas extra", hours(p.before.extra_minutes), hours(p.after.extra_minutes))}
          ${row("Total a pagar", money(p.before.net_amount), money(p.after.net_amount))}</tbody></table>`
          : `<span class="pv-sub">${md.realEnd ? "Calculando cómo quedaría…" : "Elige la hora real para ver cómo quedaría."}</span>`}</div>
        ${md.error ? `<div class="pv-alert" role="alert">${h(md.error)}</div>` : ""}
        <p class="pv-sub">Se registra una sola vez y no se puede volver a modificar.</p>
        <div class="pv-modal-actions"><button class="pv-btn-primary" type="button" data-pv-confirm-go ${md.busy || !md.realEnd ? "disabled" : ""}>Confirmar salida</button>
          <button class="client-btn" type="button" data-pv-close>Cancelar</button></div>
      </div></div>`;
  }

  function view() {
    const cards = buildCards(model.snapshot, model.activity);
    const list = visibleCards(cards, model.filter, model.query, model.sort);
    return `<div class="pv-root">
      ${topBar()}
      ${model.notice ? `<div class="pv-notice" role="status">${h(model.notice)}</div>` : ""}
      ${model.error ? `<div class="pv-alert" role="alert">${h(model.error)}</div>` : ""}
      ${strip()}
      ${alerts()}
      <section class="client-panel pv-panel">
        ${toolbar(cards)}
        ${model.loading ? `<p class="pv-sub">Calculando el periodo…</p>` : list.length ? grid(list)
          : `<div class="pv-empty">${cards.length ? "Nadie coincide con la búsqueda o el filtro." : "No hay tiempos de nómina en el periodo."}</div>`}
      </section>
      ${modalView()}
    </div>`;
  }

  function measureCols(host) {
    const w = (host && host.clientWidth) || 1200;
    return w >= 860 ? 4 : w >= 520 ? 2 : 1;
  }

  function draw() {
    const host = ctx && ctx.host();
    if (!host) return;
    model.cols = measureCols(host);
    const active = document.activeElement;
    const keep = active && active.matches && (active.matches("[data-pv-search]") ? "[data-pv-search]" : active.matches("[data-pv-note]") ? "[data-pv-note]" : "");
    const caret = keep ? active.selectionStart : null;
    host.innerHTML = view();
    applyContrast(host.querySelector(".pv-root"));
    const gridEl = host.querySelector("[data-pv-grid]");
    if (gridEl) gridEl.style.setProperty("--pv-cols", String(model.cols));
    if (keep) { const again = host.querySelector(keep); if (again) { again.focus(); try { again.setSelectionRange(caret, caret); } catch (_) {} } }
    if (model.modal && !(active && active.closest && active.closest("[data-pv-modal]"))) {
      const first = host.querySelector("[data-pv-real-end]");
      if (first) first.focus();
    }
  }

  // ------------------------------------------------------------ datos
  async function calculate(period) {
    const cid = encodeURIComponent(ctx.companyId);
    const snapshot = await ctx.api(`/payroll/companies/${cid}/periods/calculate`, { method: "POST", body: JSON.stringify({ period_start: period.from, period_end: period.to }) });
    let activity = null;
    try {
      activity = await ctx.api(`/payroll/companies/${cid}/period-activity?period_start=${encodeURIComponent(period.from)}&period_end=${encodeURIComponent(period.to)}`);
    } catch (_) { activity = null; } // sin el detalle, las tarjetas siguen (solo horas)
    return { snapshot, activity };
  }

  async function load(period) {
    model.loading = true;
    model.error = "";
    draw();
    try {
      const { snapshot, activity } = await calculate(period);
      model.snapshot = snapshot || {};
      model.activity = activity;
      model.period = { from: (snapshot.period && snapshot.period.period_start) || period.from, to: (snapshot.period && snapshot.period.period_end) || period.to };
      if (model.cfg && model.cfg.enabled && model.cfg.period && model.cfg.period.period_start !== model.period.from && ctx.loadCfg) model.cfg = await ctx.loadCfg(model.period.from);
    } catch (error) {
      model.error = error.message || "No se pudo calcular la nómina.";
    }
    model.loading = false;
    draw();
  }

  function readPeriod() {
    const host = ctx.host();
    const from = (host.querySelector("[data-pv-from]") || {}).value || (model.period || {}).from;
    const to = (host.querySelector("[data-pv-to]") || {}).value || (model.period || {}).to;
    return { from, to };
  }

  function errorText(error) {
    const raw = String((error && error.message) || error || "");
    const i = raw.indexOf("{");
    if (i >= 0) { try { const d = JSON.parse(raw.slice(i)); if (typeof d.detail === "string") return d.detail; } catch (_) {} }
    return raw || "No se pudo completar.";
  }

  async function preview() {
    const md = model.modal;
    if (!md || !md.realEnd) return;
    const u = md.item;
    try {
      md.preview = await ctx.api(`/payroll/companies/${encodeURIComponent(ctx.companyId)}/closures/preview`, { method: "POST",
        body: JSON.stringify({ period_start: model.period.from, period_end: model.period.to, source: u.source, session_ref: u.session_ref, real_end_at: md.realEnd }) });
      md.error = "";
    } catch (error) {
      md.preview = null;
      md.error = errorText(error);
    }
    if (model.modal === md) draw();
  }

  async function confirmGo() {
    const md = model.modal;
    if (!md || md.busy || !md.realEnd) return;
    const u = md.item;
    md.busy = true;
    draw();
    const body = { real_end_at: md.realEnd };
    if (md.note) body.note = md.note;
    if (u.closure_id) body.closure_id = u.closure_id; else Object.assign(body, { source: u.source, session_ref: u.session_ref });
    try {
      await ctx.api(`/workforce-sessions/companies/${encodeURIComponent(ctx.companyId)}/closures/confirm`, { method: "POST", body: JSON.stringify(body) });
      model.modal = null;
      model.notice = `Salida confirmada para ${u.employee_name || "el colaborador"}. La nómina se recalculó.`;
      await load(model.period); // la tarjeta y los totales se recalculan
    } catch (error) {
      md.busy = false;
      md.error = errorText(error);
      draw();
    }
  }

  // ------------------------------------------------------------ eventos
  function inside(t) { return ctx && ctx.host() && ctx.host().contains(t); }

  async function onClick(event) {
    const t = event.target;
    if (!t || !t.closest || !inside(t)) return;
    if (t.closest("[data-pv-close]") || (t.matches && t.matches("[data-pv-modal]"))) { model.modal = null; draw(); return; }
    if (t.closest("[data-pv-confirm-go]")) { confirmGo(); return; }
    const pend = t.closest("[data-pv-confirm]");
    if (pend) {
      const item = arr(model.snapshot && model.snapshot.unverified_shifts)[Number(pend.getAttribute("data-pv-confirm"))];
      if (item) {
        const proposed = item.declared_end_at ? (parts(item.declared_end_at) || {}).local : "";
        model.modal = { item, realEnd: proposed || "", note: "", preview: null, error: "", busy: false };
        draw();
        if (proposed) preview();
      }
      return;
    }
    const cardBtn = t.closest("[data-pv-card]");
    if (cardBtn) { const id = cardBtn.getAttribute("data-pv-card"); model.open = model.open === id ? "" : id; draw(); return; }
    const filter = t.closest("[data-pv-filter]");
    if (filter) { model.filter = filter.getAttribute("data-pv-filter"); draw(); return; }
    if (t.closest("[data-pv-calc]") || t.closest("[data-pv-refresh]")) { model.notice = ""; load(readPeriod()); return; }
    const shift = t.closest("[data-pv-shift]");
    if (shift && ctx.loadCfg && model.cfg && model.cfg.enabled) {
      const way = shift.getAttribute("data-pv-shift");
      const p = model.period;
      const ref = way === "prev" ? ctx.shiftDate(p.from, -1) : way === "next" ? ctx.shiftDate(p.to, 1) : "";
      model.cfg = await ctx.loadCfg(ref);
      if (model.cfg.enabled) load({ from: model.cfg.period.period_start, to: model.cfg.period.period_end });
    }
  }

  function onInput(event) {
    const t = event.target;
    if (!t || !t.matches || !inside(t)) return;
    if (t.matches("[data-pv-search]")) { model.query = t.value; draw(); return; }
    if (t.matches("[data-pv-note]") && model.modal) { model.modal.note = t.value; return; }
    if (t.matches("[data-pv-real-end]") && model.modal) {
      model.modal.realEnd = t.value;
      model.modal.preview = null;
      clearTimeout(previewTimer);
      previewTimer = setTimeout(preview, 350);
      const go = ctx.host().querySelector("[data-pv-confirm-go]");
      if (go) go.disabled = !t.value;
    }
  }

  function onChange(event) {
    const t = event.target;
    if (!t || !t.matches || !inside(t)) return;
    if (t.matches("[data-pv-sort]")) { model.sort = t.value; draw(); }
  }

  function onKey(event) {
    if (event.key === "Escape" && model.modal && ctx && ctx.host()) { model.modal = null; draw(); }
  }

  function onResize() {
    if (!ctx || !ctx.host()) return;
    const cols = measureCols(ctx.host());
    if (cols !== model.cols) draw();
  }

  async function mount(context) {
    ctx = context;
    Object.assign(model, { snapshot: null, activity: null, open: "", modal: null, notice: "", error: "", query: "", filter: "all", sort: "total" });
    model.cfg = ctx.cfg || null;
    model.period = ctx.period;
    // Con la normativa colombiana el detalle es otro: se queda la pantalla de siempre.
    let first;
    try {
      first = await calculate(ctx.period);
    } catch (error) {
      first = null;
      model.error = error.message || "No se pudo calcular la nómina.";
    }
    if (first && first.snapshot && first.snapshot.legal_mode && first.snapshot.legal_mode.state === "colombia") return false;
    ctx.renderShell();
    if (!bound && typeof document.addEventListener === "function") {
      document.addEventListener("click", onClick);
      document.addEventListener("input", onInput);
      document.addEventListener("change", onChange);
      document.addEventListener("keydown", onKey);
      if (typeof window.addEventListener === "function") window.addEventListener("resize", onResize);
      bound = true;
    }
    if (first) {
      model.snapshot = first.snapshot || {};
      model.activity = first.activity;
      model.period = { from: (model.snapshot.period && model.snapshot.period.period_start) || ctx.period.from, to: (model.snapshot.period && model.snapshot.period.period_end) || ctx.period.to };
    }
    draw();
    return true;
  }

  window.CxPayrollV2 = { mount, view, model, buildCards, visibleCards, totalsOf, activityFor, hours, money, pair, contrast, initials, detail, shiftTotals, dayLong };
})();
