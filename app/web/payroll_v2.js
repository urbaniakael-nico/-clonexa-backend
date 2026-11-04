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

  const model = { period: null, cfg: null, snapshot: null, activity: null, query: "", filter: "all", sort: "total", open: "", openShift: "",
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

  // ------------------------------------------------------------ 061A: reglas EE. UU. (us_payroll)
  // Solo si el calculo trae snapshot.us_payroll (interruptor us_payroll; hoy VOLTAGE):
  // horas pagables / regulares / overtime por semana laboral, pausas sin pago, desglose,
  // linea de tiempo de cada turno, PDF y CSV. Sin tarifa el dinero dice "Pendiente".
  const usOn = () => !!(model.snapshot && model.snapshot.us_payroll);
  let usLoading = false;
  function usLib() {
    if (typeof window !== "undefined" && window.CxUsPayroll) return window.CxUsPayroll;
    if (!usLoading && typeof document !== "undefined" && document.createElement && document.head) {
      usLoading = true;
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = "/client-static/us_payroll.css?v=061A";
      document.head.appendChild(link);
      const script = document.createElement("script");
      script.src = "/client-static/us_payroll.js?v=067A";
      script.onload = () => draw();
      script.onerror = () => { usLoading = false; };
      document.head.appendChild(script);
    }
    return null;
  }
  const PENDING = "Pendiente";
  const cash = (v, pending) => (pending ? PENDING : money(v));

  async function usExport(kind) {
    const p = model.period || {};
    if (!ctx.apiBase || typeof ctx.token !== "function") { model.error = "No se pudo descargar el archivo."; draw(); return; }
    const q = new URLSearchParams({ period_start: p.from || "", period_end: p.to || "" });
    try {
      const token = ctx.token();
      const res = await fetch(`${ctx.apiBase}/us-payroll/companies/${encodeURIComponent(ctx.companyId)}/export.${kind}?${q}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!res.ok) throw new Error(res.status === 403 ? "La nómina es solo del dueño y del director." : "No se pudo descargar el archivo.");
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `nomina_${p.from}_${p.to}.${kind}`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (error) {
      model.error = error.message || "No se pudo descargar el archivo.";
      draw();
    }
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
        net: num(r.net_amount), shifts: arr(r.shifts), closed: num(r.closed_shifts), pending: [],
        ...(r.us ? { us: r.us, ratePending: !!r.rate_pending, payable: num(r.us.payable_minutes), row: r } : {}) });
    });
    arr(snapshot && snapshot.unverified_shifts).forEach((u) => {
      const id = String(u.employee_id || `sin-id:${u.employee_name || ""}`);
      if (!byId.has(id)) {
        byId.set(id, { id, name: u.employee_name || "Colaborador", role: u.employee_role || "", document: docs[id] || "", regular: 0, extra: 0, gross: 0,
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
    // 063A: acento de cada operación: texto sobre la superficie y encabezado de tabla, ambos AA.
    OP_ACCENTS.forEach((c, i) => {
      const headI = pair(c, [{ r: 255, g: 255, b: 255 }, { r: 10, g: 12, b: 20 }]);
      set(`--pvu-a${i}-ink`, css(inkOn(surface.bg, c)));
      set(`--pvu-a${i}-bg`, css(headI.bg));
      set(`--pvu-a${i}-fg`, css(headI.fg));
    });
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
        ${usOn() ? `<button class="client-btn" type="button" data-pv-us-export="pdf">PDF</button><button class="client-btn" type="button" data-pv-us-export="csv">CSV</button>` : ""}
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
    if (usOn()) {
      const raw = (model.snapshot && model.snapshot.totals) || {};
      const missing = arr(model.snapshot.us_payroll.missing_rate).length;
      const allPending = raw.rate_pending && !t.net;
      return `<section class="pv-strip" aria-label="Resumen del periodo">
        ${cell("Colaboradores", String(t.people))}${cell("Horas pagables", hours(raw.payable_minutes))}${cell("Regulares", hours(t.regular))}
        ${cell("Overtime", hours(t.extra))}${cell("Pausas (sin pago)", hours(raw.pause_minutes))}
        ${cell("Total a pagar", allPending ? PENDING : `${money(t.net)}${missing ? ` · ${missing} sin tarifa` : ""}`, true)}
      </section>`;
    }
    return `<section class="pv-strip" aria-label="Resumen del periodo">
      ${cell("Colaboradores", String(t.people))}${cell("Horas ordinarias", hours(t.regular))}${cell("Horas extra", hours(t.extra))}
      ${cell("Bruto", money(t.gross))}${cell("Descuentos", money(t.discount))}${cell("Total a pagar", money(t.net), true)}
    </section>`;
  }

  function alerts() {
    const s = model.snapshot || {};
    const out = [];
    const missing = arr(s.missing_rate_employees);
    if (usOn()) {
      const U = usLib();
      out.push(`<p class="usp-rules">${h(U ? U.rulesLine(s.us_payroll.rules) : "")}</p>`);
      if (missing.length) out.push(U ? U.missingRate(missing) : `<div class="pv-alert" role="status"><strong>${missing.length} empleados sin tarifa</strong>: ${missing.map((m) => h(m.employee_name)).join(", ")}.</div>`);
      const noPlace = arr(s.us_payroll.missing_place);
      if (noPlace.length) out.push(`<div class="pv-alert" role="status"><strong>Sin lugar asignado (${noPlace.length})</strong>: ${noPlace.map((m) => h(m.employee_name)).join(", ")}. Sus horas van en la hora de la empresa.</div>`);
    } else if (missing.length) out.push(`<div class="pv-alert" role="status"><strong>Sin valor hora (${missing.length})</strong>: ${missing.map((m) => h(m.employee_name)).join(", ")}. Esas horas quedaron en $0.</div>`);
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
      <span class="pv-card-nums"><span class="pv-time">${h(hours(c.us ? c.payable : c.regular + c.extra))}</span><span class="pv-net">${h(c.us ? cash(c.net, c.ratePending) : money(c.net))}</span></span>
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

  // TOTAL = suma de los turnos que se ven arriba (mismos numeros de la nomina).
  function shiftTotals(c) {
    const refs = new Set();
    let regular = 0;
    let extra = 0;
    let connected = 0;
    let pauses = 0;
    let worked = 0;
    c.shifts.forEach((s) => {
      regular += num(s.regular_minutes); extra += num(s.extra_minutes); shiftRefs(c, s).forEach((r) => refs.add(r));
      const t = shiftTimes(s);
      connected += t.connected; pauses += t.pauses; worked += t.worked;
    });
    return { shifts: c.shifts.length, regular, extra, refs: [...refs], connected, pauses, worked };
  }

  // 056J: tabla compacta. Horas "X h YY" (ordinarias + extra); extra solo como
  // etiqueta si es mayor a 0; pausas solo en el detalle (ya estan descontadas).
  function hhmm(minutes) {
    const m = Math.max(0, Math.round(num(minutes)));
    return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")}`;
  }

  function dayShort(iso) {
    return dayLong(iso).replace(/,/g, "").replace(/\s+de\s+/g, " ");
  }

  const shiftKey = (c, s) => `${c.id}|${s.start}`;

  // 056L: Conectado | Pausas | Trabajado del servidor (app/services/shift_times.py:
  // trabajado = conectado - pausas). Solo presentacion: el pago no cambia.
  function shiftTimes(s) {
    const worked = s.worked_minutes != null ? num(s.worked_minutes) : num(s.regular_minutes) + num(s.extra_minutes);
    const pauses = num(s.pause_minutes);
    return { connected: s.connected_minutes != null ? num(s.connected_minutes) : worked + pauses, pauses, worked };
  }

  function shiftRowsTable(c, s) {
    const key = shiftKey(c, s);
    const open = model.openShift === key;
    const refs = shiftRefs(c, s);
    const acts = activityFor(model.activity, c.id, s).filter((a) => a.kind !== "references");
    const ext = num(s.extra_minutes) > 0 ? `<small class="pv-ext">+${h(hhmm(s.extra_minutes))} ${h(T("ext"))}</small>` : "";
    const times = shiftTimes(s);
    return `<tr class="pv-trow ${open ? "is-open" : ""}" data-pv-srow="${h(key)}">
        <td data-label="${h(T("Fecha"))}"><button type="button" class="pv-tbtn" data-pv-srow="${h(key)}" aria-expanded="${open}">${h(dayShort(s.start))}</button></td>
        <td data-label="${h(T("Horario"))}">${h(clock(s.start))} – ${h(clock(s.end))}</td>
        <td data-label="${h(T("Conectado"))}">${h(hhmm(times.connected))}</td>
        <td data-label="${h(T("Pausas"))}">${h(hhmm(times.pauses))}</td>
        <td data-label="${h(T("Trabajado"))}" class="pv-tworked"><b>${h(hhmm(times.worked))}</b>${ext}</td>
        <td data-label="${h(T("Referencias"))}" class="pv-tref">${refs.length ? h(refs.join(", ")) : "—"}</td>
        <td data-label="${h(T("Valor"))}" class="pv-tnum">${h(money(s.gross_amount))}</td>
      </tr>
      ${open ? `<tr class="pv-tdetail"><td colspan="7"><dl class="pv-tkv">
        <div><dt>${h(T("Horas ordinarias"))}</dt><dd>${h(hhmm(s.regular_minutes))}</dd></div>
        <div><dt>${h(T("Horas extra"))}</dt><dd>${h(hhmm(s.extra_minutes))}</dd></div></dl>
        ${acts.map((a) => `<div class="pv-act pv-act-${a.kind}"><span>${h(a.text)}</span>${a.extra ? `<span class="pv-sub">${h(a.extra)}</span>` : ""}${a.map ? `<a class="pv-map" href="${h(a.map)}" target="_blank" rel="noopener noreferrer">Ver en el mapa</a>` : ""}</div>`).join("")}
      </td></tr>` : ""}`;
  }

  function shiftTable(c) {
    const shifts = c.shifts.slice().sort((a, b) => Date.parse(a.start) - Date.parse(b.start));
    const t = shiftTotals(c);
    const value = shifts.reduce((sum, x) => sum + num(x.gross_amount), 0);
    return `<div class="pv-thead-card"><span class="pv-avatar" aria-hidden="true">${h(initials(c.name))}</span>
        <span class="pv-card-main"><span class="pv-name">${h(c.name)}</span><span class="pv-role">${h(c.role || "Sin rol")}${c.document ? ` · ${h(c.document)}` : ""}</span></span>
        <span class="pv-card-nums"><span class="pv-net">${h(money(value))}</span><span class="pv-time">${h(t.shifts)} ${h(t.shifts === 1 ? T("turno") : T("turnos"))}</span></span></div>
      ${shifts.length ? `<table class="pv-table"><thead><tr><th scope="col">${h(T("Fecha"))}</th><th scope="col">${h(T("Horario"))}</th><th scope="col">${h(T("Conectado"))}</th><th scope="col">${h(T("Pausas"))}</th><th scope="col">${h(T("Trabajado"))}</th>
        <th scope="col">${h(T("Referencias"))}</th><th scope="col" class="pv-tnum">${h(T("Valor"))}</th></tr></thead>
        <tbody>${shifts.map((s) => shiftRowsTable(c, s)).join("")}</tbody>
        <tfoot><tr class="pv-ttotal"><th scope="row" data-label="${h(T("TOTAL"))}">${h(T("TOTAL"))} · ${h(t.shifts)} ${h(t.shifts === 1 ? T("turno") : T("turnos"))}</th><td></td>
          <td data-label="${h(T("Conectado"))}">${h(hhmm(t.connected))}</td>
          <td data-label="${h(T("Pausas"))}">${h(hhmm(t.pauses))}</td>
          <td data-label="${h(T("Trabajado"))}" class="pv-tworked"><b>${h(hhmm(t.worked))}</b>${t.extra > 0 ? `<small class="pv-ext-line">${h(T("ext"))} ${h(hhmm(t.extra))}</small>` : ""}</td>
          <td data-label="${h(T("Referencias"))}" title="${h(t.refs.join(", "))}">${h(t.refs.length)}</td>
          <td data-label="${h(T("Valor"))}" class="pv-tnum">${h(money(value))}</td></tr></tfoot></table>` : ""}`;
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

  // 061A: desglose de nomina, semana laboral y linea de tiempo de cada turno.
  function detailUs(c, pendingIndex) {
    const U = usLib();
    const shifts = c.shifts.slice().sort((a, b) => Date.parse(a.start) - Date.parse(b.start));
    return `<section class="pv-detail" id="pv-detail-${h(c.id)}" aria-label="Registro de ${h(c.name)}">
      ${c.pending.length ? `<ul class="pv-shifts">${c.pending.map((u) => pendingRow(u, pendingIndex(u))).join("")}</ul>` : ""}
      ${!U ? `<p class="pv-sub">Cargando el detalle…</p>` : `${U.breakdown(c.row, money)}${U.weekTable(c.us.weeks)}
        <div class="usp-shifts">${shifts.map((s) => U.timeline(s.us)).join("")}</div>`}
      ${!c.shifts.length && !c.pending.length ? `<p class="pv-sub">Sin turnos en el periodo.</p>` : ""}
    </section>`;
  }

  function detail(c) {
    const pendingIndex = (u) => arr(model.snapshot && model.snapshot.unverified_shifts).indexOf(u);
    if (c.us) return detailUs(c, pendingIndex);
    return `<section class="pv-detail" id="pv-detail-${h(c.id)}" aria-label="Registro de ${h(c.name)}">
      ${listOn() ? "" : `<div class="pv-detail-head"><span>${c.document ? `Documento ${h(c.document)}` : "Sin documento"}</span>
        <span>${h(c.closed)} ${c.closed === 1 ? "turno" : "turnos"}</span><span>Extras ${h(hours(c.extra))}</span>
        <span>Bruto ${h(money(c.gross))} · descuentos ${h(money(c.discount))}</span></div>`}
      <ul class="pv-shifts">
        ${c.pending.map((u) => pendingRow(u, pendingIndex(u))).join("")}
        ${listOn() ? "" : c.shifts.slice().sort((a, b) => Date.parse(a.start) - Date.parse(b.start)).map((s) => shiftRow(c, s)).join("")}
        ${!c.shifts.length && !c.pending.length ? `<li class="pv-sub">Sin turnos en el periodo.</li>` : ""}
      </ul>
      ${listOn() ? shiftTable(c) : ""}
    </section>`;
  }

  // ------------------------------------------------------------ 063A: Nómina EE. UU. por operación
  // Solo con us_payroll (hoy VOLTAGE). Nómina = solo horas y valores, una tabla por operación
  // (lugar de trabajo: Virginia ET, Alabama CT...), búsqueda rápida y detalle día por día.
  // Ubicación, mapa, notas y bitácora del turno se quedan en Reportes. Mismas cifras del
  // servidor (app/services/us_time.py): aquí no se calcula nada del pago.
  const US_PREFS = "cx_pv_us_063a";
  const US_SORTS = [["payable", "Horas pagables"], ["name", "Nombre"], ["overtime", "Overtime"], ["status", "Estado"]];
  const US_MODES = [["week", "Semana"], ["fortnight", "Quincena"], ["custom", "Personalizado"]];
  const WEEK_IDX = { sunday: 0, monday: 1, tuesday: 2, wednesday: 3, thursday: 4, friday: 5, saturday: 6 };
  const WD = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"];
  // Acentos de cada operación (verde agua, ámbar, azul); payroll_v2.js los ajusta para AA.
  const OP_ACCENTS = [{ r: 20, g: 184, b: 166 }, { r: 245, g: 158, b: 11 }, { r: 96, g: 165, b: 250 }];
  Object.assign(model, { usMode: "week", opFilter: "all", usSort: "payable" });

  function usPrefsLoad(companyId) {
    try {
      const raw = JSON.parse(localStorage.getItem(`${US_PREFS}:${companyId}`) || "{}") || {};
      if (US_MODES.some(([k]) => k === raw.mode)) model.usMode = raw.mode;
      if (US_SORTS.some(([k]) => k === raw.sort)) model.usSort = raw.sort;
      if (typeof raw.filter === "string" && raw.filter) model.opFilter = raw.filter;
    } catch (_) { /* sin localStorage: valores por defecto */ }
  }
  function usPrefsSave() {
    try { localStorage.setItem(`${US_PREFS}:${ctx.companyId}`, JSON.stringify({ mode: model.usMode, sort: model.usSort, filter: model.opFilter })); } catch (_) { /* sin localStorage */ }
  }

  // Fechas como texto AAAA-MM-DD (sin horas, sin zonas).
  function addDays(iso, n) {
    const [y, m, d] = String(iso).split("-").map(Number);
    const t = new Date(Date.UTC(y, m - 1, d + n, 12));
    return t.toISOString().slice(0, 10);
  }
  const weekdayOf = (iso) => { const [y, m, d] = String(iso).split("-").map(Number); return new Date(Date.UTC(y, m - 1, d, 12)).getUTCDay(); };
  function todayIn(tz) {
    try { return new Intl.DateTimeFormat("sv-SE", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date()); } catch (_) { return new Date().toISOString().slice(0, 10); }
  }
  function weekStartOf(iso, startDay) {
    const want = WEEK_IDX[startDay] !== undefined ? WEEK_IDX[startDay] : 0;
    return addDays(iso, -((weekdayOf(iso) - want + 7) % 7));
  }
  // Semana = la semana laboral (dom-sáb); quincena = esa semana y la anterior.
  function usPeriodFor(mode, refIso, startDay) {
    const ws = weekStartOf(refIso, startDay);
    if (mode === "fortnight") return { from: addDays(ws, -7), to: addDays(ws, 6) };
    return { from: ws, to: addDays(ws, 6) };
  }
  const dm = (iso) => { const p = String(iso || "").split("-"); return p.length === 3 ? `${p[2]}/${p[1]}` : "—"; };
  const wdLabel = (iso) => `${WD[weekdayOf(iso)]} ${dm(iso)}`;
  function clockIn(iso, tz) {
    const d = new Date(iso || "");
    if (Number.isNaN(d.getTime())) return { date: "", time: "—" };
    try {
      const f = new Intl.DateTimeFormat("sv-SE", { timeZone: tz || tzOf(), year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(d);
      const [date, time] = f.split(" ");
      return { date, time };
    } catch (_) { return { date: "", time: "—" }; }
  }

  const usRules = () => ((model.snapshot && model.snapshot.us_payroll && model.snapshot.us_payroll.rules) || (ctx && ctx.usRules) || {});

  // Personas agrupadas por operación; los totales son de TODA la operación (la búsqueda no los cambia).
  function usOperations(snapshot, cards) {
    const us = (snapshot && snapshot.us_payroll) || {};
    const order = arr(us.operations).map((o) => ({ name: o.name, abbr: o.abbr || "", tz: o.tz || "" }));
    const known = new Map(order.map((o) => [o.name, o]));
    const placeOf = (c) => (c.us ? c.us.place : (c.pending[0] && c.pending[0].place)) || "";
    cards.forEach((c) => {
      const p = placeOf(c);
      if (p && !known.has(p)) { const o = { name: p, abbr: (c.us && c.us.abbr) || (c.pending[0] && c.pending[0].abbr) || "", tz: (c.us && c.us.tz) || "" }; order.push(o); known.set(p, o); }
    });
    const ops = order.map((o, i) => ({ ...o, key: o.name, accent: i % OP_ACCENTS.length, label: o.abbr ? `${o.name} (${o.abbr})` : o.name, people: [] }));
    const none = { name: "Sin lugar asignado", key: "__none__", abbr: us.company_abbr || "", tz: us.company_tz || "", accent: -1, label: "Sin lugar asignado", people: [] };
    const byKey = new Map(ops.map((o) => [o.key, o]));
    cards.forEach((c) => { (byKey.get(placeOf(c)) || none).people.push(c); });
    const out = ops.filter((o) => o.people.length);
    if (none.people.length) out.push(none);
    out.forEach((o) => {
      const t = { payable: 0, regular: 0, overtime: 0, pause: 0, connected: 0, gross: 0, net: 0, ratePending: false, missing: 0, pendingCount: 0, pendingMinutes: 0 };
      o.people.forEach((c) => {
        const u = c.us || {};
        t.payable += num(u.payable_minutes); t.regular += num(u.regular_minutes); t.overtime += num(u.overtime_minutes);
        t.pause += num(u.pause_minutes); t.connected += num(u.connected_minutes);
        t.gross += num(u.gross); t.net += num(u.net);
        if (c.us && c.ratePending) { t.ratePending = true; t.missing += 1; }
        t.pendingCount += c.pending.length; t.pendingMinutes += c.pending.reduce((s, x) => s + num(x.minutes), 0);
      });
      o.totals = t;
    });
    return out;
  }

  function usVisible(people, query, filter, sort) {
    const q = fold(query).trim();
    const list = people.filter((c) => (filter !== "pending" || c.pending.length) && (!q || fold(`${c.name} ${c.document}`).includes(q)));
    const pay = (c) => num(c.us && c.us.payable_minutes);
    const ot = (c) => num(c.us && c.us.overtime_minutes);
    const byName = (a, b) => a.name.localeCompare(b.name, "es", { sensitivity: "base" });
    const by = {
      payable: (a, b) => pay(b) - pay(a) || byName(a, b),
      name: byName,
      overtime: (a, b) => ot(b) - ot(a) || pay(b) - pay(a) || byName(a, b),
      status: (a, b) => b.pending.length - a.pending.length || byName(a, b),
    };
    return list.sort(by[sort] || by.payable);
  }

  const usMoney = (value, pending) => (pending ? PENDING : money(value));
  function usBruto(t) {
    if (t.ratePending && !t.gross) return "Tarifa pendiente";
    return `${money(t.gross)}${t.missing ? ` · ${t.missing} sin tarifa` : ""}`;
  }
  const statusChip = (n) => (n ? `<span class="pvu-chip is-warn">${h(n)} ${n === 1 ? "salida" : "salidas"} por confirmar</span>` : `<span class="pvu-chip is-ok">OK</span>`);
  const opClass = (o) => (o.accent >= 0 ? `pvu-op-${o.accent}` : "pvu-op-x");

  function usHeader() {
    const p = model.period || {};
    const custom = model.usMode === "custom";
    const title = model.usMode === "fortnight" ? "Nómina quincenal" : custom ? "Nómina" : "Nómina semanal";
    const range = `${wdLabel(p.from)} – ${wdLabel(p.to)}`;
    const step = model.usMode === "fortnight" ? "2 semanas" : "semana";
    return `<header class="client-hero pv-bar pvu-bar">
      <div class="pv-title"><div class="client-eyebrow">Nómina</div><h1 class="client-title">${h(title)}</h1>
        <p class="pvu-week">${custom ? "Periodo" : "Semana laboral"} <b>${h(range)}</b></p>
        <p class="pvu-rule">Overtime por encima de 40 h · Pausas sin pago</p></div>
      <div class="pvu-controls">
        <div class="pvu-seg" role="group" aria-label="Periodo">${US_MODES.map(([k, l]) => `<button type="button" class="pv-filter ${model.usMode === k ? "is-active" : ""}" aria-pressed="${model.usMode === k}" data-pvu-mode="${k}">${l}</button>`).join("")}</div>
        ${custom ? `<label class="pv-date"><span>Desde</span><input type="date" data-pv-from value="${h(p.from || "")}"></label>
          <label class="pv-date"><span>Hasta</span><input type="date" data-pv-to value="${h(p.to || "")}"></label>
          <button class="pv-btn-primary" type="button" data-pv-calc>Calcular</button>`
          : `<div class="pvu-nav"><button class="client-btn pvu-arrow" type="button" data-pvu-step="-1" aria-label="${h(step)} anterior">‹</button>
          <button class="client-btn pvu-arrow" type="button" data-pvu-step="1" aria-label="${h(step)} siguiente">›</button></div>`}
        <button class="client-btn" type="button" data-pv-us-export="csv">CSV</button>
        <button class="pv-btn-primary" type="button" data-pv-us-export="pdf">Descargar PDF</button>
        <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
      </div>
    </header>`;
  }

  function usAlert(cards) {
    const n = cards.reduce((s, c) => s + c.pending.length, 0);
    if (!n) return "";
    const mins = cards.reduce((s, c) => s + c.pending.reduce((a, x) => a + num(x.minutes), 0), 0);
    return `<div class="pv-alert pvu-alert" role="status"><span><strong>⚠ ${h(n)} ${n === 1 ? "turno" : "turnos"} por confirmar</strong> · ${h(hhmm(mins))} no entran a la nómina hasta registrar la salida real</span>
      <button class="client-btn" type="button" data-pvu-review>Revisar</button></div>`;
  }

  function usFilters(ops, cards, shown) {
    const pendingN = cards.reduce((s, c) => s + c.pending.length, 0);
    const chips = [["all", "Ambas operaciones"], ...ops.map((o) => [o.key, o.label]), ["pending", `Por confirmar (${pendingN})`]];
    if (ops.length > 2) chips[0][1] = "Todas las operaciones";
    return `<div class="pvu-tools" data-pvu-tools>
      <div class="pvu-search"><input class="pv-search" type="search" data-pv-search value="${h(model.query)}" placeholder="Buscar por nombre o documento" aria-label="Buscar por nombre o documento">
        ${model.query ? `<button type="button" class="pvu-clear" data-pvu-clear aria-label="Limpiar búsqueda">✕</button>` : ""}</div>
      <span class="pvu-count" aria-live="polite">${h(shown)} de ${h(cards.length)} personas</span>
      <div class="pv-filters pvu-chips" role="group" aria-label="Operación">${chips.map(([k, l]) => `<button type="button" class="pv-filter ${model.opFilter === k ? "is-active" : ""}" aria-pressed="${model.opFilter === k}" data-pvu-filter="${h(k)}">${h(l)}</button>`).join("")}</div>
      <label class="pv-sort"><span>Ordenar por</span><select data-pvu-sort>${US_SORTS.map(([k, l]) => `<option value="${k}" ${model.usSort === k ? "selected" : ""}>${l}</option>`).join("")}</select></label>
    </div>`;
  }

  function usSummary(o) {
    const t = o.totals;
    const now = o.tz ? clockIn(new Date().toISOString(), o.tz).time : "";
    const stat = (label, value, cls = "") => `<div class="pvu-stat ${cls}"><span>${h(label)}</span><strong>${h(value)}</strong></div>`;
    return `<section class="pvu-sum ${opClass(o)}" aria-label="Resumen ${h(o.name)}">
      <div class="pvu-sum-head"><h2>${h(o.name)}</h2><span>${o.abbr ? `${h(now ? `${now} ` : "")}${h(o.abbr)} · ` : ""}${h(o.people.length)} ${o.people.length === 1 ? "persona" : "personas"}</span></div>
      <div class="pvu-stats">${stat("Horas pagables", hhmm(t.payable), "is-main")}${stat("Regulares", hhmm(t.regular))}${stat("Overtime", hhmm(t.overtime), t.overtime > 0 ? "is-ot" : "")}
        ${stat("Pausas", hhmm(t.pause))}${stat("Bruto", usBruto(t))}${stat("Por confirmar", t.pendingCount ? `${t.pendingCount} · ${hhmm(t.pendingMinutes)}` : "0", t.pendingCount ? "is-warn" : "")}</div>
    </section>`;
  }

  const US_COLS = ["Empleado", "Rol", "Días", "En turno", "Pausas", "Pagables", "Regulares", "Overtime", "Tarifa", "Bruto", "Neto", "Estado"];

  function usRow(c, pendingIndex) {
    const u = c.us || {};
    const open = model.open === c.id;
    const pend = !c.us || c.ratePending;
    const ot = num(u.overtime_minutes);
    const cell = (i, value, cls = "") => `<td data-label="${h(US_COLS[i])}" class="${cls}">${value}</td>`;
    return `<tr class="pvu-row ${open ? "is-open" : ""} ${c.pending.length ? "is-pending" : ""}">
      <th scope="row" data-label="Empleado"><button type="button" class="pvu-open" data-pvu-open="${h(c.id)}" aria-expanded="${open}" aria-controls="pvu-d-${h(c.id)}">
        <span class="pvu-caret" aria-hidden="true">${open ? "▾" : "▸"}</span><span class="pvu-who"><span class="pv-name">${h(c.name)}</span>${c.document ? `<span class="pvu-doc">${h(c.document)}</span>` : ""}</span></button></th>
      ${cell(1, h(c.role || "—"), "pvu-role")}${cell(2, h(num(u.days_worked)), "pvu-n")}${cell(3, h(hhmm(u.connected_minutes)), "pvu-n")}${cell(4, h(hhmm(u.pause_minutes)), "pvu-n")}
      ${cell(5, `<b>${h(hhmm(u.payable_minutes))}</b>`, "pvu-n pvu-pay")}${cell(6, h(hhmm(u.regular_minutes)), "pvu-n")}
      ${cell(7, ot > 0 ? `<b class="pvu-ot">${h(hhmm(ot))}</b>` : h(hhmm(0)), "pvu-n")}
      ${cell(8, pend ? `<span class="pvu-pend">Pendiente</span>` : h(`${money(u.rate)}/h`), "pvu-n")}
      ${cell(9, pend ? `<span class="pvu-pend">Pendiente</span>` : h(money(u.gross)), "pvu-n")}
      ${cell(10, pend ? `<span class="pvu-pend">Pendiente</span>` : `<b>${h(money(u.net))}</b>`, "pvu-n")}
      ${cell(11, `${statusChip(c.pending.length)}${c.pending.length ? ` <button type="button" class="pvu-confirm" data-pv-confirm="${h(pendingIndex(c.pending[0]))}">Confirmar salida</button>` : ""}`, "pvu-state")}
    </tr>
    ${open ? `<tr class="pvu-detail-row" id="pvu-d-${h(c.id)}"><td colspan="12">${usDetail(c, pendingIndex)}</td></tr>` : ""}`;
  }

  // Día por día del periodo (semana laboral dom-sáb; en quincena, dos semanas): entrada,
  // salida, en turno, pausas y pagables. Horas en la zona de SU lugar. Nada más.
  function usDays(c) {
    const u = c.us || {};
    const tz = u.tz || "";
    const map = new Map();
    const get = (d) => { if (!map.has(d)) map.set(d, { in: null, out: null, outDate: "", payable: 0, pause: 0 }); return map.get(d); };
    arr(u.weeks).forEach((w) => arr(w.days).forEach((d) => { const x = get(d.date); x.payable += num(d.payable); x.pause += num(d.pause); }));
    arr(c.shifts).forEach((s) => {
      const a = clockIn(s.start, tz);
      if (!a.date) return;
      const x = get(a.date);
      if (!x.in || Date.parse(s.start) < x.inAt) { x.in = a.time; x.inAt = Date.parse(s.start); }
      const b = clockIn(s.end, tz);
      if (b.date && (!x.out || Date.parse(s.end) > x.outAt)) { x.out = b.time; x.outAt = Date.parse(s.end); x.outDate = b.date !== a.date ? b.date : ""; }
    });
    return map;
  }

  function usDetail(c, pendingIndex) {
    const p = model.period || {};
    const u = c.us || {};
    const days = usDays(c);
    const abbr = u.abbr || (c.pending[0] && c.pending[0].abbr) || "";
    const weeks = [];
    for (let ws = weekStartOf(p.from, usRules().week_start_day); ws <= p.to; ws = addDays(ws, 7)) weeks.push(ws);
    const grid = weeks.map((ws) => {
      const list = [0, 1, 2, 3, 4, 5, 6].map((i) => addDays(ws, i));
      let pay = 0; let pause = 0;
      const rows = list.map((d) => {
        const x = days.get(d);
        const out = d < p.from || d > p.to;
        if (x && !out) { pay += x.payable; pause += x.pause; }
        return `<tr class="${out ? "is-out" : ""} ${x ? "" : "is-empty"}"><th scope="row">${h(wdLabel(d))}</th>
          <td data-label="Entrada">${h(x && x.in ? x.in : "—")}</td><td data-label="Salida">${h(x && x.out ? `${x.out}${x.outDate ? ` (${dm(x.outDate)})` : ""}` : "—")}</td>
          <td data-label="En turno" class="pvu-n">${x ? h(hhmm(x.payable + x.pause)) : "—"}</td><td data-label="Pausas" class="pvu-n">${x ? h(hhmm(x.pause)) : "—"}</td>
          <td data-label="Pagables" class="pvu-n">${x ? `<b>${h(hhmm(x.payable))}</b>` : "—"}</td></tr>`;
      }).join("");
      return `<table class="pvu-days"><caption>Semana ${h(wdLabel(ws))} – ${h(wdLabel(addDays(ws, 6)))}${abbr ? ` · hora ${h(abbr)}` : ""}</caption>
        <thead><tr><th scope="col">Día</th><th scope="col">Entrada</th><th scope="col">Salida</th><th scope="col" class="pvu-n">En turno</th><th scope="col" class="pvu-n">Pausas</th><th scope="col" class="pvu-n">Pagables</th></tr></thead>
        <tbody>${rows}</tbody>
        <tfoot><tr><th scope="row">Total</th><td></td><td></td><td class="pvu-n">${h(hhmm(pay + pause))}</td><td class="pvu-n">${h(hhmm(pause))}</td><td class="pvu-n"><b>${h(hhmm(pay))}</b></td></tr></tfoot></table>`;
    }).join("");
    const held = c.pending.map((x) => `<li><span>${h(wdLabel(clockIn(x.start, u.tz).date))} · entrada ${h(clockIn(x.start, u.tz).time)}${abbr ? ` ${h(abbr)}` : ""} · ${h(hhmm(x.minutes))} sin liquidar</span>
      <button type="button" class="pvu-confirm" data-pv-confirm="${h(pendingIndex(x))}">Confirmar salida</button></li>`).join("");
    return `<div class="pvu-detail" aria-label="Detalle de ${h(c.name)}">
      <div class="pvu-days-wrap">${grid}</div>
      ${held ? `<ul class="pvu-held">${held}</ul>` : ""}
      <button type="button" class="pvu-link" data-reports-open>Ver ubicación y notas en Reportes</button>
    </div>`;
  }

  function usTable(o, list, pendingIndex) {
    const t = o.totals;
    const allP = t.ratePending && !t.gross;
    return `<section class="pvu-table-wrap ${opClass(o)}" aria-label="Tabla ${h(o.name)}">
      <table class="pvu-table"><caption>${h(o.label)}</caption>
        <thead><tr>${US_COLS.map((k, i) => `<th scope="col" class="${i >= 2 && i <= 10 ? "pvu-n" : ""}">${h(k)}</th>`).join("")}</tr></thead>
        <tbody>${list.map((c) => usRow(c, pendingIndex)).join("")}</tbody>
        <tfoot><tr class="pvu-total"><th scope="row" data-label="Total">Total ${h(o.name)}</th><td data-label="Rol"></td><td data-label="Días"></td>
          <td data-label="En turno" class="pvu-n">${h(hhmm(t.connected))}</td><td data-label="Pausas" class="pvu-n">${h(hhmm(t.pause))}</td>
          <td data-label="Pagables" class="pvu-n"><b>${h(hhmm(t.payable))}</b></td><td data-label="Regulares" class="pvu-n">${h(hhmm(t.regular))}</td>
          <td data-label="Overtime" class="pvu-n">${t.overtime > 0 ? `<b class="pvu-ot">${h(hhmm(t.overtime))}</b>` : h(hhmm(0))}</td><td data-label="Tarifa"></td>
          <td data-label="Bruto" class="pvu-n">${allP ? `<span class="pvu-pend">Pendiente</span>` : h(money(t.gross))}</td>
          <td data-label="Neto" class="pvu-n">${allP ? `<span class="pvu-pend">Pendiente</span>` : `<b>${h(money(t.net))}</b>`}</td>
          <td data-label="Estado">${statusChip(t.pendingCount)}</td></tr></tfoot>
      </table></section>`;
  }

  function viewUs() {
    const cards = buildCards(model.snapshot, model.activity);
    const ops = usOperations(model.snapshot, cards);
    const pendingIndex = (u) => arr(model.snapshot && model.snapshot.unverified_shifts).indexOf(u);
    const f = model.opFilter;
    const shownOps = ops.filter((o) => f === "all" || f === "pending" || f === o.key);
    if (!shownOps.length && ops.length) model.opFilter = "all";
    const useOps = shownOps.length ? shownOps : ops;
    const lists = useOps.map((o) => ({ o, list: usVisible(o.people, model.query, f === "pending" ? "pending" : "all", model.usSort) }));
    const shown = lists.reduce((s, x) => s + x.list.length, 0);
    const tables = lists.filter((x) => x.list.length).map((x) => usTable(x.o, x.list, pendingIndex)).join("");
    const empty = model.query.trim() ? `Nadie coincide con '${model.query.trim()}'` : f === "pending" ? "No hay turnos por confirmar." : "No hay horas de nómina en el periodo.";
    const total = totalsOf(model.snapshot);
    const raw = (model.snapshot && model.snapshot.totals) || {};
    const pendingN = cards.reduce((s, c) => s + c.pending.length, 0);
    return `<div class="pv-root pvu-root">
      ${usHeader()}
      ${model.notice ? `<div class="pv-notice" role="status">${h(model.notice)}</div>` : ""}
      ${model.error ? `<div class="pv-alert" role="alert">${h(model.error)}</div>` : ""}
      ${usAlert(cards)}
      <section class="client-panel pv-panel pvu-panel">
        ${usFilters(ops, cards, shown)}
        ${model.loading ? `<p class="pv-sub">Calculando el periodo…</p>` : `
          <div class="pvu-sums">${useOps.map(usSummary).join("")}</div>
          ${tables || `<div class="pv-empty">${h(empty)}</div>`}`}
      </section>
      <footer class="pvu-foot"><span>Solo horas y valores. Ubicación, notas y bitácora están en Reportes.</span>
        <strong>Total ${h((ctx && ctx.companyName) || "empresa")}: ${h(hhmm(raw.payable_minutes))} pagables · ${h(hhmm(total.extra))} overtime · ${h(pendingN)} por confirmar</strong></footer>
      ${modalView()}
    </div>`;
  }

  async function usStep(dir) {
    const p = model.period || {};
    const days = model.usMode === "fortnight" ? 14 : 7;
    const next = usPeriodFor(model.usMode, addDays(p.to, dir * days), usRules().week_start_day);
    await load(next);
  }

  async function usSetMode(mode) {
    model.usMode = mode;
    usPrefsSave();
    if (mode === "custom") { draw(); return; }
    const p = model.period || {};
    await load(usPeriodFor(mode, p.to || todayIn(tzOf()), usRules().week_start_day));
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

  // 063A: con us_payroll la nota es obligatoria (el servidor también lo exige).
  const confirmReady = (md) => !!(md && md.realEnd && (!usOn() || String(md.note || "").trim()));

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
        <label class="pv-field"><span>${usOn() ? "Nota (obligatoria)" : "Nota (opcional)"}</span><textarea data-pv-note rows="2" maxlength="300" placeholder="Por qué esta hora" ${usOn() ? "required aria-required=\"true\"" : ""}>${h(md.note || "")}</textarea></label>
        <div class="pv-preview" aria-live="polite">${p ? `<table class="pv-preview-table"><thead><tr><th scope="col"></th><th scope="col">Hoy</th><th scope="col">Al confirmar</th></tr></thead><tbody>
          ${row(usOn() ? "Regulares" : "Horas ordinarias", hours(p.before.regular_minutes), hours(p.after.regular_minutes))}
          ${row(usOn() ? "Overtime" : "Horas extra", hours(p.before.extra_minutes), hours(p.after.extra_minutes))}
          ${row(usOn() ? "Neto" : "Total a pagar", usOn() && md.ratePending ? PENDING : money(p.before.net_amount), usOn() && md.ratePending ? PENDING : money(p.after.net_amount))}</tbody></table>`
          : `<span class="pv-sub">${md.realEnd ? "Calculando cómo quedaría…" : "Elige la hora real para ver cómo quedaría."}</span>`}</div>
        ${md.error ? `<div class="pv-alert" role="alert">${h(md.error)}</div>` : ""}
        <p class="pv-sub">Se registra una sola vez y no se puede volver a modificar.${usOn() ? " Queda en la auditoría: quién confirmó, cuándo y la nota." : ""}</p>
        <div class="pv-modal-actions"><button class="pv-btn-primary" type="button" data-pv-confirm-go ${md.busy || !confirmReady(md) ? "disabled" : ""}>Confirmar salida</button>
          <button class="client-btn" type="button" data-pv-close>Cancelar</button></div>
      </div></div>`;
  }

  function view() {
    if (usOn()) return viewUs(); // 063A: Nómina EE. UU. por operación
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
    if (!md || md.busy || !confirmReady(md)) {
      if (md && md.realEnd && usOn() && !String(md.note || "").trim()) { md.error = "Escribe una nota: por qué esta es la hora real de salida."; draw(); }
      return;
    }
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
    const usx = t.closest("[data-pv-us-export]");
    if (usx) { usExport(usx.getAttribute("data-pv-us-export") === "csv" ? "csv" : "pdf"); return; }
    const pend = t.closest("[data-pv-confirm]");
    if (pend) {
      const item = arr(model.snapshot && model.snapshot.unverified_shifts)[Number(pend.getAttribute("data-pv-confirm"))];
      if (item) {
        const proposed = item.declared_end_at ? (parts(item.declared_end_at) || {}).local : "";
        const owner = arr(model.snapshot && model.snapshot.rows).find((r) => String(r.employee_id) === String(item.employee_id));
        model.modal = { item, realEnd: proposed || "", note: "", preview: null, error: "", busy: false, ratePending: !owner || !!owner.rate_pending };
        draw();
        if (proposed) preview();
      }
      return;
    }
    if (usOn()) {
      const op = t.closest("[data-pvu-open]");
      if (op) { const id = op.getAttribute("data-pvu-open"); model.open = model.open === id ? "" : id; draw(); return; }
      const fl = t.closest("[data-pvu-filter]");
      if (fl) { model.opFilter = fl.getAttribute("data-pvu-filter"); usPrefsSave(); draw(); return; }
      if (t.closest("[data-pvu-review]")) {
        model.opFilter = "pending"; usPrefsSave(); draw();
        const tools = ctx.host().querySelector("[data-pvu-tools]");
        if (tools && tools.scrollIntoView) tools.scrollIntoView({ block: "start", behavior: "smooth" });
        return;
      }
      if (t.closest("[data-pvu-clear]")) { model.query = ""; draw(); const s = ctx.host().querySelector("[data-pv-search]"); if (s) s.focus(); return; }
      const md = t.closest("[data-pvu-mode]");
      if (md) { usSetMode(md.getAttribute("data-pvu-mode")); return; }
      const st = t.closest("[data-pvu-step]");
      if (st) { model.notice = ""; usStep(Number(st.getAttribute("data-pvu-step")) || 1); return; }
    }
    const srow = t.closest("[data-pv-srow]");
    if (srow && !(t.closest("a"))) { const k = srow.getAttribute("data-pv-srow"); model.openShift = model.openShift === k ? "" : k; draw(); return; }
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
    if (t.matches("[data-pv-note]") && model.modal) {
      model.modal.note = t.value;
      const go = ctx.host().querySelector("[data-pv-confirm-go]");
      if (go) go.disabled = !confirmReady(model.modal);
      return;
    }
    if (t.matches("[data-pv-real-end]") && model.modal) {
      model.modal.realEnd = t.value;
      model.modal.preview = null;
      clearTimeout(previewTimer);
      previewTimer = setTimeout(preview, 350);
      const go = ctx.host().querySelector("[data-pv-confirm-go]");
      if (go) go.disabled = !confirmReady(model.modal);
    }
  }

  function onChange(event) {
    const t = event.target;
    if (!t || !t.matches || !inside(t)) return;
    if (t.matches("[data-pv-sort]")) { model.sort = t.value; draw(); }
    if (t.matches("[data-pvu-sort]")) { model.usSort = t.value; usPrefsSave(); draw(); }
  }

  function onKey(event) {
    if (event.key === "Escape" && model.modal && ctx && ctx.host()) { model.modal = null; draw(); return; }
    // 063A: Esc en la búsqueda la limpia.
    const t = event.target;
    if (event.key === "Escape" && t && t.matches && t.matches("[data-pv-search]") && inside(t) && model.query) { model.query = ""; draw(); }
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
    // 063A: con us_payroll el periodo es la semana laboral (o la quincena) que eligió la última vez.
    if (ctx.usPayroll) {
      Object.assign(model, { usMode: "week", opFilter: "all", usSort: "payable" });
      usPrefsLoad(ctx.companyId);
      if (model.usMode !== "custom") ctx.period = model.period = usPeriodFor(model.usMode, todayIn(tzOf()), (ctx.usRules || {}).week_start_day);
    }
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

  window.CxPayrollV2 = { mount, view, model, buildCards, visibleCards, totalsOf, activityFor, hours, money, pair, contrast, initials, detail, shiftTotals, dayLong, hhmm, dayShort, usOn, cash,
    usOperations, usVisible, usPeriodFor, weekStartOf, usDays, confirmReady };
})();
