// Board de gerencia de Reportes (interruptor reports_board; hoy solo VOLTAGE).
// Todo lo que registran los operarios, por operación y en orden A-Z. Una sola llamada
// (GET /reports-board/companies/{id}) trae todo: búsqueda, filtros y orden son aquí mismo,
// sin volver al servidor. Cada 60 s solo se pide el estado en vivo (?part=live).
// Mismas horas que Nómina; aquí no hay valores de pago. El servidor decide qué operación
// ve cada quien (un supervisor, solo la suya).
(() => {
  "use strict";

  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const num = (v) => Number(v || 0) || 0;
  const fill = (s, vars) => (vars ? String(s).replace(/\{(\w+)\}/g, (m, k) => (vars[k] !== undefined ? String(vars[k]) : m)) : String(s));
  const T = (s, vars) => (typeof window !== "undefined" && window.CxI18n && typeof window.CxI18n.t === "function" ? window.CxI18n.t(s, vars) : fill(s, vars));

  const PREFS = "cx_rb_064a";
  const LIVE_MS = 60000;
  const FULL_EVERY = 10; // cada 10 minutos se recarga todo, en silencio
  const ALERTS_SHOWN = 5;
  const NOTES_STEP = 5;
  const PRESETS = [["today", "Hoy"], ["week", "Semana"], ["month", "Mes"], ["custom", "Personalizado"]];
  const STATUS = [["working", "En turno"], ["on_break", "En pausa"], ["alerts", "Con alertas"]];
  const SORTS = [["az", "A-Z"], ["hours", "Horas en turno"], ["last", "Última marca"]];
  const DAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];
  const MARK = { in: "Entrada", pause: "Pausa", resume: "Retomar", out: "Salida" };
  const GEO = { inside: "En perímetro", outside: "Fuera de perímetro", unconfigured: "Sin perímetro", none: "Sin ubicación", adjusted: "Ajuste manual" };

  const model = {
    preset: "week", anchor: "", from: "", to: "", weekStart: "sunday", data: null, loading: false, error: "", denied: false, busy: "",
    query: "", op: "all", status: "", sort: "az", open: "", notesShown: {}, alertsAll: {},
  };
  let ctx = null;
  let bound = false;
  let timer = null;
  let ticks = 0;
  let seq = 0;

  // ------------------------------------------------------------ formatos
  function hm(minutes) {
    const m = Math.max(0, Math.round(num(minutes)));
    return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")}`;
  }
  function today() {
    const loc = typeof window !== "undefined" ? window.CxLocale : null;
    return (loc && typeof loc.filterDay === "function" && loc.filterDay(new Date())) || new Date().toISOString().slice(0, 10);
  }
  const toDate = (iso) => new Date(`${iso}T12:00:00Z`);
  const lang = () => (typeof window !== "undefined" && window.CxI18n && window.CxI18n.locale ? window.CxI18n.locale() : "es-CO");
  function addDays(iso, n) { const d = toDate(iso); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); }
  function dayLabel(iso, withWeekday = true) {
    if (!iso) return "—";
    try {
      return new Intl.DateTimeFormat(lang(), { timeZone: "UTC", day: "2-digit", month: "short", ...(withWeekday ? { weekday: "short" } : {}) }).format(toDate(iso));
    } catch (_) { return iso; }
  }

  function weekdayShort(iso) {
    try { return new Intl.DateTimeFormat(lang(), { timeZone: "UTC", weekday: "short" }).format(toDate(iso)).replace(".", ""); } catch (_) { return ""; }
  }

  // Periodo: la semana es la laboral de la empresa (la misma de Nómina).
  function rangeOf(preset, anchor, weekStart = "sunday", custom = {}) {
    const base = anchor;
    if (preset === "today") return { from: base, to: base };
    if (preset === "week") {
      const first = Math.max(0, DAYS.indexOf(weekStart));
      const back = (toDate(base).getUTCDay() - first + 7) % 7;
      const from = addDays(base, -back);
      return { from, to: addDays(from, 6) };
    }
    if (preset === "month") {
      const d = toDate(base);
      const last = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0, 12));
      return { from: `${base.slice(0, 8)}01`, to: last.toISOString().slice(0, 10) };
    }
    return { from: custom.from || base, to: custom.to || custom.from || base };
  }
  function range() { return rangeOf(model.preset, model.anchor, model.weekStart, { from: model.from, to: model.to }); }
  function shiftAnchor(dir) {
    const r = range();
    if (model.preset === "today") model.anchor = addDays(model.anchor, dir);
    else if (model.preset === "week") model.anchor = addDays(model.anchor, 7 * dir);
    else if (model.preset === "month") { const d = toDate(`${model.anchor.slice(0, 8)}15`); d.setUTCMonth(d.getUTCMonth() + dir); model.anchor = d.toISOString().slice(0, 10); }
    else {
      const len = Math.round((toDate(r.to) - toDate(r.from)) / 86400000) + 1;
      model.from = addDays(r.from, len * dir);
      model.to = addDays(r.to, len * dir);
    }
  }

  // ------------------------------------------------------------ búsqueda (sin mayúsculas ni tildes)
  const stripMarks = (s) => String(s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "");
  const norm = (s) => stripMarks(s).toLowerCase().replace(/\s+/g, " ").trim();
  function personNotes(p) { return arr(p.days).flatMap((d) => arr(d.shifts).flatMap((s) => arr(s.notes))); }
  function matchOf(p, q) {
    if (!q) return { hit: true };
    if (norm(p.name).includes(q) || norm(p.document).includes(q)) return { hit: true, by: "person" };
    const note = personNotes(p).find((n) => norm(n.text).includes(q));
    return note ? { hit: true, by: "note", note } : { hit: false };
  }
  // Resalta en el texto original lo que coincide con la búsqueda (ya sin tildes), escapando todo lo demás.
  function highlight(text, q) {
    const raw = String(text ?? "");
    if (!q) return h(raw);
    let flat = "";
    const map = [];
    Array.from(raw).forEach((ch, i) => { const n = stripMarks(ch).toLowerCase().replace(/\s/g, " "); for (const c of n) { flat += c; map.push(i); } });
    const at = flat.indexOf(q);
    if (at < 0) return h(raw);
    const chars = Array.from(raw);
    const a = map[at];
    const b = map[at + q.length - 1] + 1;
    return `${h(chars.slice(0, a).join(""))}<mark>${h(chars.slice(a, b).join(""))}</mark>${h(chars.slice(b).join(""))}`;
  }
  function snippet(text, q) {
    const raw = String(text ?? "");
    const i = stripMarks(raw).toLowerCase().indexOf(q);
    if (i < 0 || raw.length <= 90) return raw;
    return `${i > 30 ? "…" : ""}${raw.slice(Math.max(0, i - 30), i + q.length + 40)}${i + q.length + 40 < raw.length ? "…" : ""}`;
  }

  function passesStatus(p, status) {
    if (status === "alerts") return arr(p.alerts).length > 0;
    if (status) return p.now && p.now.state === status;
    return true;
  }
  function sortPeople(list, sort) {
    if (sort === "hours") return [...list].sort((a, b) => num(b.connected) - num(a.connected));
    if (sort === "last") return [...list].sort((a, b) => String((b.last_mark || {}).at || "").localeCompare(String((a.last_mark || {}).at || "")));
    return list; // el servidor ya las manda A-Z (sin tildes)
  }
  function visiblePeople(op, m = model) {
    const q = norm(m.query);
    return sortPeople(arr(op.people).filter((p) => matchOf(p, q).hit && passesStatus(p, m.status)), m.sort);
  }
  const visibleOps = (m = model) => arr(m.data && m.data.operations).filter((o) => m.op === "all" || o.key === m.op);
  const countOf = (m = model) => ({
    shown: visibleOps(m).reduce((n, o) => n + visiblePeople(o, m).length, 0),
    total: arr(m.data && m.data.operations).reduce((n, o) => n + arr(o.people).length, 0),
  });

  // ------------------------------------------------------------ preferencias
  function loadPrefs() {
    try {
      const raw = JSON.parse(localStorage.getItem(`${PREFS}:${ctx.companyId}`) || "{}") || {};
      if (SORTS.some(([k]) => k === raw.sort)) model.sort = raw.sort;
      if (raw.status === "" || STATUS.some(([k]) => k === raw.status)) model.status = raw.status;
      if (typeof raw.op === "string") model.op = raw.op;
    } catch (_) { /* sin localStorage: valores por defecto */ }
  }
  function savePrefs() {
    try { localStorage.setItem(`${PREFS}:${ctx.companyId}`, JSON.stringify({ op: model.op, status: model.status, sort: model.sort })); } catch (_) { /* sin localStorage */ }
  }

  // ------------------------------------------------------------ datos
  const base = () => `${ctx.apiBase}/reports-board/companies/${encodeURIComponent(ctx.companyId)}`;
  const headers = () => { const t = ctx.token(); return t ? { Authorization: `Bearer ${t}` } : {}; };
  const params = () => { const r = range(); return new URLSearchParams({ start: r.from, end: r.to }).toString(); };

  async function load(silent = false) {
    const mine = ++seq;
    if (!silent) { model.loading = true; model.error = ""; draw(); }
    try {
      const res = await fetch(`${base()}?${params()}`, { headers: headers() });
      if (mine !== seq) return;
      if (res.status === 401 || res.status === 403) { model.denied = true; model.data = null; return; }
      if (!res.ok) throw new Error(String(res.status));
      const data = await res.json();
      if (mine !== seq) return;
      model.denied = false;
      model.data = data;
      model.error = "";
      const start = data.rules && data.rules.week_start_day;
      if (start && start !== model.weekStart) {
        model.weekStart = start;
        if (model.preset === "week") { load(silent); return; }
      }
      if (model.op !== "all" && !arr(data.operations).some((o) => o.key === model.op)) model.op = "all";
      if (data.scope && data.scope.limited) model.op = "all";
    } catch (_) {
      if (mine === seq) model.error = T("No se pudo cargar el Board. Revisa la conexión e inténtalo de nuevo.");
    } finally {
      if (mine === seq) { model.loading = false; silent ? drawLive() : draw(); }
    }
  }

  // Estado en vivo: cambia los chips y las cifras "ahora" sin tocar nada más.
  function applyLive(live, data = model.data) {
    if (!live || !data) return;
    const people = live.people || {};
    const clocks = live.clocks || {};
    const recount = (list, held) => {
      const st = list.map((p) => p.now.state);
      const over = list.filter((p) => p.now.over_limit).length;
      return { working: st.filter((s) => s === "working").length, on_break: st.filter((s) => s === "on_break").length, no_shift: st.filter((s) => s === "no_shift").length,
        open_over: over, to_confirm: held + over };
    };
    arr(data.operations).forEach((o) => {
      arr(o.people).forEach((p) => { if (people[p.id]) p.now = people[p.id]; });
      if (clocks[o.key]) o.local_time = clocks[o.key].local_time;
      o.figures = { ...o.figures, ...recount(arr(o.people), num(o.figures && o.figures.held)) };
    });
    const everyone = arr(data.operations).flatMap((o) => arr(o.people));
    data.figures = { ...data.figures, ...recount(everyone, num(data.figures && data.figures.held)) };
  }
  async function tick() {
    if (!ctx || !ctx.host()) { stopTimer(); return; }
    if (typeof document !== "undefined" && document.hidden) return;
    if (!model.data || model.loading) return;
    ticks += 1;
    if (ticks % FULL_EVERY === 0) { await load(true); return; }
    try {
      const res = await fetch(`${base()}?part=live`, { headers: headers() });
      if (!res.ok) return;
      applyLive(await res.json());
      drawLive();
    } catch (_) { /* el siguiente minuto lo intenta otra vez */ }
  }
  function stopTimer() { if (timer) { clearInterval(timer); timer = null; } }

  async function download(kind) {
    const paths = { pdf: ["export.pdf", "pdf"], marks: ["marks.csv", "csv"], notes: ["notes.csv", "csv"] };
    const [path, ext] = paths[kind] || paths.pdf;
    model.busy = kind; model.error = ""; draw();
    try {
      const res = await fetch(`${base()}/${path}?${params()}`, { headers: headers() });
      if (!res.ok) throw new Error(String(res.status));
      const url = URL.createObjectURL(await res.blob());
      const r = range();
      const a = document.createElement("a");
      a.href = url;
      a.download = `${kind === "pdf" ? "board" : kind === "marks" ? "marcaciones" : "notas"}_${r.from}_${r.to}.${ext}`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (_) {
      model.error = T("No se pudo generar el archivo.");
    } finally { model.busy = ""; draw(); }
  }

  // ------------------------------------------------------------ contraste (desde el tema de la empresa)
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
  // Virginia verde agua, Alabama ámbar; pausas violeta (separación validada con daltonismo).
  const ACCENTS = [{ r: 45, g: 212, b: 191 }, { r: 251, g: 191, b: 36 }];
  const PAUSE = { r: 167, g: 139, b: 250 };
  function applyContrast(root) {
    if (!root || typeof getComputedStyle !== "function") return;
    const text = themeColor(root, "var(--cx-text)") || { r: 255, g: 255, b: 255 };
    const bg = themeColor(root, "var(--cx-bg)") || { r: 15, g: 23, b: 42 };
    const primary = themeColor(root, "var(--cx-primary)") || bg;
    const secondary = themeColor(root, "var(--cx-secondary, var(--cx-primary))") || primary;
    const surface = pair(bg, [text], 7);
    const head = pair(primary, [text, surface.bg]);
    const set = (k, v) => root.style.setProperty(k, v);
    set("--rb-surface", css(surface.bg));
    set("--rb-on", css(surface.fg));
    set("--rb-accent-bg", css(head.bg));
    set("--rb-accent-fg", css(head.fg));
    const plate = mix(surface.bg, surface.fg, 0.08); // alertas y pausas van sobre esta placa
    set("--rb-danger", css(inkOn(plate, { r: 252, g: 129, b: 129 }, 4.6)));
    set("--rb-warn", css(inkOn(plate, { r: 251, g: 191, b: 36 }, 4.6)));
    set("--rb-good", css(inkOn(plate, secondary, 4.6)));
    set("--rb-pause", css(inkOn(surface.bg, PAUSE, 3)));
    ACCENTS.forEach((c, i) => {
      const headI = pair(c, [{ r: 255, g: 255, b: 255 }, { r: 10, g: 12, b: 20 }]);
      set(`--rb-a${i}-ink`, css(inkOn(surface.bg, c)));
      set(`--rb-a${i}-bar`, css(inkOn(surface.bg, c, 3)));
      set(`--rb-a${i}-bg`, css(headI.bg));
      set(`--rb-a${i}-fg`, css(headI.fg));
    });
  }

  // ------------------------------------------------------------ vistas
  function chipOf(now) {
    const n = now || {};
    if (n.state === "working") return { cls: "is-working", text: `${T("Trabajando")} ${hm(n.minutes)}` };
    if (n.state === "on_break") return { cls: "is-break", text: `${T("En pausa")} ${hm(n.minutes)}` };
    if (n.state === "to_confirm") return { cls: "is-confirm", text: T("Por confirmar") };
    if (n.state === "done") return { cls: "is-done", text: n.end ? `${T("Terminó")} ${n.end.t} ${n.end.a}` : T("Terminó") };
    return { cls: "is-off", text: T("Sin turno hoy") };
  }

  function head() {
    const r = range();
    const company = (model.data && model.data.company) || {};
    const busy = model.busy ? "disabled" : "";
    return `<header class="rb-panel rb-head">
      <div class="rb-title"><button type="button" class="client-btn rb-back" data-rb-back>← ${h(T("Módulos"))}</button>
        <div><p class="client-eyebrow">${h(company.name || "")}</p><h1 class="client-title">${h(T("Board de gerencia"))}</h1></div></div>
      <div class="rb-controls">
        <div class="rb-seg" role="group" aria-label="${h(T("Periodo"))}">${PRESETS.map(([k, l]) => `<button type="button" class="client-btn ${model.preset === k ? "is-on" : ""}" data-rb-preset="${k}" aria-pressed="${model.preset === k}">${h(T(l))}</button>`).join("")}</div>
        <div class="rb-nav"><button type="button" class="client-btn rb-arrow" data-rb-move="-1" aria-label="${h(T("Periodo anterior"))}">‹</button>
          <span class="rb-range" role="status">${h(r.from === r.to ? dayLabel(r.from) : `${dayLabel(r.from)} – ${dayLabel(r.to)}`)}</span>
          <button type="button" class="client-btn rb-arrow" data-rb-move="1" aria-label="${h(T("Periodo siguiente"))}">›</button></div>
        ${model.preset === "custom" ? `<label class="rb-date">${h(T("Desde"))}<input type="date" data-rb-from value="${h(r.from)}"></label><label class="rb-date">${h(T("Hasta"))}<input type="date" data-rb-to value="${h(r.to)}"></label>` : ""}
        <div class="rb-exports"><button type="button" class="client-btn" data-rb-export="marks" ${busy}>${h(T("CSV marcaciones"))}</button>
          <button type="button" class="client-btn" data-rb-export="notes" ${busy}>${h(T("CSV notas"))}</button>
          <button type="button" class="rb-primary" data-rb-export="pdf" ${busy}>${h(T("Descargar PDF"))}</button></div>
      </div></header>`;
  }

  function figures(f = {}) {
    const tiles = [["En turno ahora", num(f.working)], ["En pausa ahora", num(f.on_break)], ["Sin turno hoy", num(f.no_shift)], ["Horas en turno", hm(f.connected)],
      ["Pausas", hm(f.pause)], ["Fuera de perímetro", num(f.outside), num(f.outside) > 0 ? "is-danger" : ""], ["Por confirmar", num(f.to_confirm), num(f.to_confirm) > 0 ? "is-warn" : ""], ["Notas del periodo", num(f.notes)]];
    return `<div class="rb-figs">${tiles.map(([l, v, c]) => `<div class="rb-fig ${c || ""}"><span>${h(T(l))}</span><strong>${h(v)}</strong></div>`).join("")}</div>`;
  }

  function filters() {
    const data = model.data || {};
    const ops = arr(data.operations);
    const limited = data.scope && data.scope.limited;
    const c = countOf();
    const opChips = limited || ops.length < 2 ? "" : [["all", ops.length > 2 ? T("Todas") : T("Ambas")], ...ops.map((o) => [o.key, o.name])]
      .map(([k, l]) => `<button type="button" class="rb-chip ${model.op === k ? "is-on" : ""}" data-rb-op="${h(k)}" aria-pressed="${model.op === k}">${h(l)}</button>`).join("");
    return `<section class="rb-panel rb-filters" aria-label="${h(T("Filtros"))}">
      <div class="rb-searchrow"><div class="rb-search"><input type="search" data-rb-search value="${h(model.query)}" placeholder="${h(T("Buscar por nombre, documento o texto de una nota"))}" aria-label="${h(T("Buscar por nombre, documento o texto de una nota"))}" autocomplete="off">
        <button type="button" class="rb-clear" data-rb-clear aria-label="${h(T("Limpiar búsqueda"))}" ${model.query ? "" : "hidden"}>✕</button></div>
        <span class="rb-count" data-rb-count role="status">${h(T("{n} de {m} personas", { n: c.shown, m: c.total }))}</span></div>
      <div class="rb-chiprow">${opChips}${opChips ? `<span class="rb-sep" aria-hidden="true"></span>` : ""}${STATUS.map(([k, l]) => `<button type="button" class="rb-chip ${model.status === k ? "is-on" : ""}" data-rb-status="${k}" aria-pressed="${model.status === k}">${h(T(l))}</button>`).join("")}
        <label class="rb-sort">${h(T("Orden"))}<select data-rb-sort>${SORTS.map(([k, l]) => `<option value="${k}" ${model.sort === k ? "selected" : ""}>${h(T(l))}</option>`).join("")}</select></label></div></section>`;
  }

  // Barras por día: pagable (color de la operación) y pausas encima; 2 px de separación.
  function chart(op) {
    const days = arr(op.hours_by_day);
    if (!days.some((d) => num(d.payable) + num(d.pause))) return `<p class="rb-empty">${h(T("Sin horas en el periodo."))}</p>`;
    const max = Math.max(1, ...days.map((d) => num(d.payable) + num(d.pause)));
    const every = days.length <= 8 ? 1 : days.length <= 16 ? 2 : 5;
    const compact = days.length > 8;
    return `<div class="rb-legend"><i class="rb-sw is-pay"></i>${h(T("Pagable"))}<i class="rb-sw is-pause"></i>${h(T("Pausas"))}<span class="rb-legend-max">${h(T("Máximo {h}", { h: hm(max) }))}</span></div>
      <ul class="rb-chart" role="list" style="--n:${days.length}">${days.map((d, i) => {
        const label = `${dayLabel(d.date)}: ${T("Pagable")} ${hm(d.payable)} · ${T("Pausas")} ${hm(d.pause)}`;
        const show = i % every === 0;
        return `<li class="rb-col" tabindex="0" aria-label="${h(label)}"><span class="rb-tip ${i >= days.length / 2 ? "is-end" : ""}">${h(label)}</span>
          <span class="rb-bars"><i class="is-pause" style="height:${(num(d.pause) / max) * 100}%"></i><i class="is-pay" style="height:${(num(d.payable) / max) * 100}%"></i></span>
          <small>${show ? (compact ? h(d.date.slice(8)) : `${h(weekdayShort(d.date))}<br>${h(d.date.slice(8))}`) : ""}</small></li>`;
      }).join("")}</ul>`;
  }

  function alertText(a) {
    const when = `${dayLabel(a.d, false)} ${a.t} ${a.a}`;
    if (a.kind === "outside") return { tag: T("Fuera de perímetro"), detail: `${T(a.mark || "")} · ${when}`, cls: "is-danger" };
    if (a.kind === "no_location") return { tag: T("Sin ubicación"), detail: `${T(a.mark || "")} · ${when}`, cls: "is-warn" };
    if (a.kind === "to_confirm") return { tag: a.open ? T("Turno abierto de {h}", { h: hm(a.minutes) }) : T("Por confirmar"), detail: `${T("Entrada")} · ${when}`, cls: "is-danger" };
    return { tag: T("Cerca de overtime: {h}", { h: hm(a.minutes) }), detail: `${T("Última salida")} · ${when}`, cls: "is-warn" };
  }

  function alertsOf(op) {
    const q = norm(model.query);
    const list = arr(op.alerts).filter((a) => { const p = arr(op.people).find((x) => x.id === a.employee_id); return p ? matchOf(p, q).hit && passesStatus(p, model.status) : true; });
    if (!list.length) return `<p class="rb-empty">${h(T("Sin alertas."))}</p>`;
    const shown = model.alertsAll[op.key] ? list : list.slice(0, ALERTS_SHOWN);
    return `<ul class="rb-alerts">${shown.map((a) => { const t = alertText(a); return `<li class="${t.cls}"><button type="button" class="rb-link" data-rb-open="${h(a.employee_id)}">${h(a.employee)}</button> <b>${h(t.tag)}</b> <span>${h(t.detail)}</span></li>`; }).join("")}</ul>
      ${list.length > ALERTS_SHOWN ? `<button type="button" class="client-btn rb-more" data-rb-alerts="${h(op.key)}">${h(model.alertsAll[op.key] ? T("Ver menos") : T("Ver todas ({n})", { n: list.length }))}</button>` : ""}`;
  }

  function block(op) {
    const f = op.figures || {};
    const count = arr(op.people).length;
    const stats = [["En turno", num(f.working)], ["En pausa", num(f.on_break)], ["Horas en turno", hm(f.connected)], ["Pausas", hm(f.pause)], ["Notas", num(f.notes)]];
    return `<section class="rb-panel rb-block rb-op-${h(op.color)}" aria-label="${h(op.name)}">
      <header class="rb-block-head"><h2>${h(op.name)}${op.code ? ` <small>${h(op.code)}</small>` : ""}</h2><span class="rb-clock">${h(op.local_time)} ${h(op.abbr)}</span>
        <p>${h(arr(op.supervisors).length ? `${T("Supervisor")}: ${op.supervisors.join(", ")}` : T("Sin supervisor"))} · ${h(count === 1 ? T("1 persona") : T("{n} personas", { n: count }))}</p>
        ${op.perimeter_missing ? `<p class="rb-nogeo">${h(T("Perímetro sin configurar"))}</p>` : ""}</header>
      <div class="rb-stats">${stats.map(([l, v]) => `<div><span>${h(T(l))}</span><strong>${h(v)}</strong></div>`).join("")}</div>
      <h3>${h(T("Horas por día"))}</h3>${chart(op)}
      <h3>${h(T("Alertas"))} <small>${arr(op.alerts).length}</small></h3>${alertsOf(op)}</section>`;
  }

  const mapLink = (m) => (m && m.lat !== undefined && m.lng !== undefined
    ? `<a class="rb-map" href="https://www.google.com/maps?q=${encodeURIComponent(`${m.lat},${m.lng}`)}" target="_blank" rel="noopener noreferrer">${h(T("mapa"))}</a>` : "");
  const geoChip = (m) => (m && m.s ? `<span class="rb-geo is-${h(m.s)}">${h(T(GEO[m.s] || ""))}${m.n ? ` · ${h(m.n)}` : ""}</span>` : "");
  function markLine(m, dayIso) {
    if (!m) return "";
    return `<span class="rb-mk"><b>${h(T(MARK[m.k]))}</b> <time>${h(m.t)} ${h(m.a)}</time>${m.d !== dayIso ? ` <small>(${h(dayLabel(m.d, false))})</small>` : ""} ${geoChip(m)} ${mapLink(m)}</span>`;
  }

  function shiftView(s, d, q) {
    const notes = arr(s.notes);
    const hideMaterialNotes = arr(d.materials).length > 0;
    const main = notes.filter((n) => n.kind === "summary");
    const others = notes.filter((n) => n.kind !== "summary" && n.kind !== "manual_close" && !(hideMaterialNotes && n.kind === "material"));
    const manualNote = notes.find((n) => n.kind === "manual_close");
    return `<div class="rb-shift ${s.state === "ok" ? "" : `is-${h(s.state)}`}">
      ${s.state === "held" ? `<span class="rb-flag is-confirm">${h(T("Por confirmar: no suma horas todavía"))}</span>` : ""}
      ${s.state === "running" ? `<span class="rb-flag is-running">${h(T("Turno en curso: no suma horas todavía"))}</span>` : ""}
      ${s.adjusted ? `<span class="rb-flag is-adjusted">${h(T("Ajustado"))}</span>` : ""}
      <ul class="rb-marks">
        <li>${markLine(s.in, d.date)}</li>
        ${arr(s.pauses).map((p) => `<li class="is-pause">${markLine(p.start, d.date)}${p.end ? ` <span class="rb-to" aria-hidden="true">→</span> ${markLine(p.end, d.date)}` : ""} <span class="rb-dur">${h(p.minutes)} min${p.auto && s.state === "running" ? ` · ${h(T("en pausa ahora"))}` : ""}</span></li>`).join("")}
        ${s.out ? `<li>${markLine(s.out, d.date)}</li>` : ""}
      </ul>
      ${s.manual ? `<div class="rb-closed"><b>${h(T("Cerrado por {who}", { who: s.manual.by || T("supervisor") }))}</b> ${s.out ? `<span>${h(T("Hora puesta"))}: ${h(s.out.t)} ${h(s.out.a)}</span>` : ""}${manualNote ? `<p>${highlight(manualNote.text, q)}</p>` : ""}</div>` : ""}
      ${main.map((n) => `<div class="rb-summary"><b>${h(T("Resumen de la jornada"))}</b><p>${highlight(n.text, q)}</p></div>`).join("")}
      ${others.map((n) => `<p class="rb-note"><b>${h(T(n.label || "Nota"))}</b> ${n.t ? `<time>${h(n.t)} ${h(n.a)}</time> ` : ""}${highlight(n.text, q)}</p>`).join("")}
    </div>`;
  }

  function timeline(p) {
    const q = norm(model.query);
    const days = arr(p.days);
    if (!days.length) return `<p class="rb-empty">${h(T("Sin marcas en el periodo."))}</p>`;
    return `<div class="rb-days">${days.map((d) => `<article class="rb-day"><h4>${h(dayLabel(d.date))}</h4>
      ${arr(d.shifts).map((s) => shiftView(s, d, q)).join("")}
      ${arr(d.materials).length ? `<div class="rb-mats"><b>${h(T("Pedidos de material"))}</b><ul>${d.materials.map((m) => `<li>${h(m.what)}${num(m.qty) ? ` × ${h(m.qty)}${m.unit ? ` ${h(m.unit)}` : ""}` : ""} <time>${h(m.t)} ${h(m.a)}</time></li>`).join("")}</ul></div>` : ""}
      <p class="rb-daytotal"><span>${h(T("En turno"))} <b>${h(hm(d.connected))}</b></span> · <span>${h(T("Pausas"))} <b>${h(hm(d.pause))}</b></span> · <span>${h(T("Pagable"))} <b>${h(hm(d.payable))}</b></span></p></article>`).join("")}</div>`;
  }

  function tableOf(op) {
    const q = norm(model.query);
    const list = visiblePeople(op);
    if (!list.length && (q || model.status)) return "";
    const cols = ["Empleado", "Rol", "Ahora", "Días", "En turno", "Pausas", "Pagables", "Overtime", "Fuera de perímetro", "Notas", "Materiales", "Última marca"].map((c) => T(c));
    return `<div class="rb-table-wrap rb-op-${h(op.color)}"><table class="rb-table" aria-label="${h(T("Tabla {name}", { name: op.name }))}">
      <caption>${h(op.name)} <small>${h(op.abbr)}</small></caption>
      <thead><tr>${cols.map((c, i) => `<th scope="col" class="${i >= 3 && i <= 10 ? "rb-n" : ""}">${h(c)}</th>`).join("")}</tr></thead>
      <tbody>${list.length ? list.map((p) => {
        const chip = chipOf(p.now);
        const match = matchOf(p, q);
        const open = model.open === p.id;
        const last = p.last_mark;
        const cell = (i, v, cls = "") => `<td class="rb-n ${cls}" data-l="${h(cols[i])}">${v}</td>`;
        return `<tr class="rb-row ${open ? "is-open" : ""}"><th scope="row" data-l="${h(cols[0])}"><button type="button" class="rb-who" data-rb-open="${h(p.id)}" aria-expanded="${open}"><span class="rb-caret" aria-hidden="true">${open ? "▾" : "▸"}</span><span><span class="rb-name">${highlight(p.name, q)}</span>${p.document ? `<small class="rb-doc">${highlight(p.document, q)}</small>` : ""}${match.by === "note" ? `<small class="rb-hit">${h(T("Nota"))}: ${highlight(snippet(match.note.text, q), q)}</small>` : ""}</span></button></th>
          <td data-l="${h(cols[1])}">${h(p.role || "—")}</td>
          <td data-l="${h(cols[2])}"><span class="rb-now ${chip.cls}" data-rb-now="${h(p.now && p.now.state)}">${h(chip.text)}</span></td>
          ${cell(3, h(p.days_worked))}${cell(4, h(hm(p.connected)))}${cell(5, h(hm(p.pause)))}${cell(6, `<b>${h(hm(p.payable))}</b>`)}${cell(7, h(hm(p.overtime)), num(p.overtime) ? "is-warn" : "")}
          ${cell(8, h(p.outside), num(p.outside) > 0 ? "is-danger" : "")}${cell(9, h(p.notes))}${cell(10, h(p.materials))}
          <td data-l="${h(cols[11])}" class="rb-last">${last ? `${h(dayLabel(last.d, false))} ${h(last.t)} ${h(last.a)}` : "—"}</td></tr>
          ${open ? `<tr class="rb-detail"><td colspan="12">${timeline(p)}</td></tr>` : ""}`;
      }).join("") : `<tr><td colspan="12" class="rb-empty">${h(T("Sin personas."))}</td></tr>`}</tbody></table></div>`;
  }

  function notesOf(op) {
    const q = norm(model.query);
    const peopleHit = (n) => { const p = arr(op.people).find((x) => x.id === n.employee_id); return p && (norm(p.name).includes(q) || norm(p.document).includes(q)); };
    const list = arr(op.notes).filter((n) => !q || norm(n.text).includes(q) || peopleHit(n));
    const shown = list.slice(0, model.notesShown[op.key] || NOTES_STEP);
    return `<section class="rb-panel rb-notes rb-op-${h(op.color)}" aria-label="${h(T("Notas de cierre {name}", { name: op.name }))}"><h2>${h(T("Notas de cierre"))}: ${h(op.name)} <small>${list.length}</small></h2>
      ${shown.length ? `<ul>${shown.map((n) => `<li><header><button type="button" class="rb-link" data-rb-open="${h(n.employee_id)}">${highlight(n.employee, q)}</button> <time>${h(dayLabel(n.d, false))} ${h(n.t)} ${h(n.a)}</time>${n.kind === "manual_close" ? ` <small>${h(T("Cierre del supervisor"))}</small>` : ""}</header><p>${highlight(n.text, q)}</p></li>`).join("")}</ul>` : `<p class="rb-empty">${h(T("Sin notas en el periodo."))}</p>`}
      ${list.length > shown.length ? `<button type="button" class="client-btn rb-more" data-rb-notes="${h(op.key)}">${h(T("Ver más"))}</button>` : ""}</section>`;
  }

  function results() {
    if (!model.data) return "";
    const ops = visibleOps();
    return `<div class="rb-blocks">${ops.map(block).join("")}</div>
      ${ops.map(tableOf).join("")}
      ${countOf().shown === 0 ? `<p class="rb-panel rb-empty">${h(T("Ninguna persona coincide con la búsqueda o los filtros."))}</p>` : ""}
      <div class="rb-notes-grid">${ops.map(notesOf).join("")}</div>`;
  }

  function view() {
    if (model.denied) return `<div class="rb-root" data-rb-root>${head()}<section class="rb-panel"><p>${h(T("Tu rol no tiene acceso al Board de gerencia."))}</p></section></div>`;
    const data = model.data;
    const body = data ? `<div data-rb-figs>${figures(data.figures)}</div>
      ${data.scope && data.scope.supervisor_no_place ? `<p class="rb-panel rb-notice" role="status">${h(T("Tu usuario de supervisor no tiene lugar de trabajo: ves todas las operaciones."))}</p>` : ""}
      ${filters()}<div data-rb-results>${results()}</div>`
      : `<section class="rb-panel"><p class="rb-empty">${h(model.loading ? T("Cargando…") : T("Sin datos."))}</p></section>`;
    return `<div class="rb-root" data-rb-root>${head()}
      ${model.error ? `<div class="rb-panel rb-notice" role="alert">${h(model.error)}</div>` : ""}${model.loading && data ? `<p class="rb-loading" role="status">${h(T("Cargando…"))}</p>` : ""}
      ${body}</div>`;
  }

  function draw() {
    if (!ctx) return;
    const host = ctx.host();
    if (!host) return;
    host.innerHTML = view();
    applyContrast(host.querySelector && host.querySelector(".rb-root"));
  }
  // Sin tocar la barra de filtros: la búsqueda no pierde el foco ni el cursor.
  function drawResults() {
    const host = ctx && ctx.host();
    const box = host && host.querySelector && host.querySelector("[data-rb-results]");
    if (!box) { draw(); return; }
    box.innerHTML = results();
    const count = host.querySelector("[data-rb-count]");
    if (count) { const c = countOf(); count.textContent = T("{n} de {m} personas", { n: c.shown, m: c.total }); }
    const clear = host.querySelector("[data-rb-clear]");
    if (clear) clear.hidden = !model.query;
  }
  function drawLive() {
    const host = ctx && ctx.host();
    const figs = host && host.querySelector && host.querySelector("[data-rb-figs]");
    if (!figs || !model.data) { draw(); return; }
    figs.innerHTML = figures(model.data.figures);
    drawResults();
  }

  // ------------------------------------------------------------ eventos
  function setQuery(value) { model.query = value; drawResults(); }

  function onClick(event) {
    const t = event.target;
    if (!ctx || !t || !t.closest || !t.closest("[data-rb-root]")) return;
    const attr = (a) => { const el = t.closest(`[${a}]`); return el ? el.getAttribute(a) : null; };
    let v;
    if (t.closest("[data-rb-back]")) { stopTimer(); ctx.back(); return; }
    if ((v = attr("data-rb-preset"))) {
      if (v === "custom") { const r = range(); model.from = r.from; model.to = r.to; }
      model.preset = v;
      model.anchor = today();
      load();
      return;
    }
    if ((v = attr("data-rb-move"))) { shiftAnchor(Number(v)); load(); return; }
    if ((v = attr("data-rb-export"))) { download(v); return; }
    if ((v = attr("data-rb-op"))) { model.op = v; savePrefs(); draw(); return; }
    if ((v = attr("data-rb-status"))) { model.status = model.status === v ? "" : v; savePrefs(); draw(); return; }
    if (t.closest("[data-rb-clear]")) {
      setQuery("");
      const input = ctx.host().querySelector("[data-rb-search]");
      if (input) { input.value = ""; input.focus(); }
      return;
    }
    if ((v = attr("data-rb-alerts"))) { model.alertsAll[v] = !model.alertsAll[v]; drawResults(); return; }
    if ((v = attr("data-rb-notes"))) { model.notesShown[v] = (model.notesShown[v] || NOTES_STEP) + NOTES_STEP * 2; drawResults(); return; }
    if ((v = attr("data-rb-open"))) {
      const fromTable = Boolean(t.closest(".rb-who"));
      model.open = model.open === v && fromTable ? "" : v;
      drawResults();
      if (!fromTable && model.open && typeof document.querySelector === "function") {
        const row = ctx.host().querySelector(`.rb-who[data-rb-open="${String(v).replace(/"/g, "")}"]`);
        if (row && row.scrollIntoView) row.scrollIntoView({ block: "center" });
      }
    }
  }
  function onInput(event) {
    const t = event.target;
    if (ctx && t && t.matches && t.closest("[data-rb-root]") && t.matches("[data-rb-search]")) setQuery(t.value);
  }
  function onChange(event) {
    const t = event.target;
    if (!ctx || !t || !t.closest || !t.closest("[data-rb-root]")) return;
    if (t.hasAttribute("data-rb-sort")) { model.sort = t.value; savePrefs(); drawResults(); return; }
    if (t.hasAttribute("data-rb-from") && t.value) { model.from = t.value; if (model.to < t.value) model.to = t.value; load(); return; }
    if (t.hasAttribute("data-rb-to") && t.value) { model.to = t.value; if (model.from > t.value) model.from = t.value; load(); }
  }
  function onKey(event) {
    if (!ctx || event.key !== "Escape" || !model.query) return;
    const host = ctx.host();
    if (!host) return;
    setQuery("");
    const input = host.querySelector("[data-rb-search]");
    if (input) input.value = "";
  }

  async function mount(context) {
    ctx = context;
    if (!bound && typeof document.addEventListener === "function") {
      document.addEventListener("click", onClick);
      document.addEventListener("input", onInput);
      document.addEventListener("change", onChange);
      document.addEventListener("keydown", onKey);
      bound = true;
    }
    Object.assign(model, { preset: "week", anchor: today(), data: null, error: "", denied: false, query: "", open: "", notesShown: {}, alertsAll: {} });
    loadPrefs();
    stopTimer();
    ticks = 0;
    if (typeof setInterval === "function") timer = setInterval(tick, LIVE_MS);
    await load();
  }

  window.CxReportsBoard = { mount, model, view, results, rangeOf, norm, matchOf, highlight, visiblePeople, countOf, chipOf, applyLive, hm, alertText, contrast, _ctx: (c) => { ctx = c; } };
})();
