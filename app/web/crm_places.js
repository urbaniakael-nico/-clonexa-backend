// CRM Campo dividido por lugar de trabajo (interruptor work_locations del
// modulo workforce). client.js solo lo monta con el interruptor encendido; sin
// el interruptor, o si este archivo no carga, CRM Campo sigue igual que siempre.
// Datos: UNA llamada (GET /work-locations/companies/{id}/board) que ya viene
// agrupada por lugar; se refresca cada 60 s y los tiempos corren cada segundo.
// Colores: solo los del tema; los pares de texto se calculan para pasar AA.
(() => {
  "use strict";

  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const fold = (v) => String(v ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const ALL = "all";
  const NONE = "none";
  const REFRESH_MS = 60000;
  const STATUS = { working: "Trabajando", on_break: "En pausa" };
  const GPS = { inside: "En perímetro", outside: "Fuera", unconfigured: "Sin perímetro", none: "Sin ubicación" };

  const model = { data: null, filter: ALL, query: "", error: "", loading: false, detail: null };
  let ctx = null;
  let bound = false;
  let tick = null;
  let refresh = null;

  // ------------------------------------------------------------ reglas puras
  const statusOf = (row) => { const s = row && row.core && row.core.status; return s === "working" || s === "on_break" ? s : "no_shift"; };
  const statusLabel = (row) => STATUS[statusOf(row)] || "Sin turno";
  const ORDER = { working: 0, on_break: 1, no_shift: 2 };

  function sortPeople(list) {
    return arr(list).slice().sort((a, b) => (ORDER[statusOf(a)] - ORDER[statusOf(b)])
      || String(a.employee_name || "").localeCompare(String(b.employee_name || ""), "es", { sensitivity: "base" }));
  }

  function searchPeople(list, query) {
    const q = fold(query).trim();
    if (!q) return arr(list);
    const words = q.split(/\s+/).filter(Boolean);
    return arr(list).filter((row) => { const name = fold(row.employee_name); return words.every((w) => name.includes(w)); });
  }

  function countsOf(list) {
    const out = { total: 0, working: 0, on_break: 0, no_shift: 0, in_perimeter: 0 };
    arr(list).forEach((row) => { out.total += 1; out[statusOf(row)] += 1; if (row.gps_place === "inside") out.in_perimeter += 1; });
    return out;
  }

  // Botones de arriba: Todas, cada lugar con su número y "Sin asignar" solo si hay gente.
  function buttons(groups) {
    const total = arr(groups).reduce((n, g) => n + arr(g.people).length, 0);
    return [{ key: ALL, label: "Todas", count: total }].concat(arr(groups)
      .filter((g) => g.key !== NONE || arr(g.people).length > 0)
      .map((g) => ({ key: g.key, label: g.name, count: arr(g.people).length })));
  }

  function shownGroups(groups, filter) {
    if (filter === ALL) return arr(groups);
    return arr(groups).filter((g) => g.key === filter);
  }

  function validFilter(groups, key) {
    return key === ALL || buttons(groups).some((b) => b.key === key) ? key : ALL;
  }

  // Hora local de un lugar. La diferencia entre lugares sale de la zona IANA
  // (Virginia America/New_York va una hora por delante de Alabama America/Chicago).
  function localTime(tz, date = new Date()) {
    if (!tz) return "";
    try { return new Intl.DateTimeFormat("es-US", { timeZone: tz, hour: "numeric", minute: "2-digit" }).format(date); } catch (_) { return ""; }
  }
  function tzOffsetMinutes(tz, date = new Date()) {
    const parts = new Intl.DateTimeFormat("en-US", { timeZone: tz, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })
      .formatToParts(date).reduce((o, p) => { o[p.type] = p.value; return o; }, {});
    const asUtc = Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day), Number(parts.hour) % 24, Number(parts.minute));
    return Math.round((asUtc - Math.floor(date.getTime() / 60000) * 60000) / 60000);
  }

  function hm(seconds) {
    const s = Math.max(0, Math.floor(Number(seconds) || 0));
    const hh = Math.floor(s / 3600);
    const mm = Math.floor((s % 3600) / 60);
    return `${hh}:${String(mm).padStart(2, "0")}`;
  }

  function storageKey(companyId) { return `cx_crm_place_${companyId || ""}`; }
  function readChoice(companyId) { try { return window.localStorage.getItem(storageKey(companyId)) || ALL; } catch (_) { return ALL; } }
  function saveChoice(companyId, key) { try { window.localStorage.setItem(storageKey(companyId), key); } catch (_) { /* sin almacenamiento */ } }

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
  function mix(c, to, t) { return { r: Math.round(c.r + (to.r - c.r) * t), g: Math.round(c.g + (to.g - c.g) * t), b: Math.round(c.b + (to.b - c.b) * t) }; }
  function pair(bg, candidates, goal = 4.5) {
    const fgs = candidates.filter(Boolean);
    let best = fgs[0];
    fgs.forEach((c) => { if (contrast(bg, c) > contrast(bg, best)) best = c; });
    if (contrast(bg, best) >= goal) return { bg, fg: best };
    const to = lum(best) > 0.4 ? { r: 0, g: 0, b: 0 } : { r: 255, g: 255, b: 255 };
    for (let t = 0.05; t <= 1.0001; t += 0.05) { const next = mix(bg, to, t); if (contrast(next, best) >= goal) return { bg: next, fg: best }; }
    return { bg: to, fg: best };
  }
  const css = (c) => `rgb(${c.r}, ${c.g}, ${c.b})`;
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
    const surface = pair(bg, [text], 7);
    const head = pair(primary, [text, surface.bg]);
    root.style.setProperty("--cxp-surface", css(surface.bg));
    root.style.setProperty("--cxp-on", css(surface.fg));
    root.style.setProperty("--cxp-accent", css(head.bg));
    root.style.setProperty("--cxp-on-accent", css(head.fg));
  }

  // ------------------------------------------------------------ dibujo
  function timerAttrs(row) {
    const s = statusOf(row);
    const base = Number(row.core && row.core.shift_effective_seconds) || 0;
    return `data-cxp-timer data-base="${base}" data-running="${s === "working" ? 1 : 0}" data-at="${Date.now()}"`;
  }

  function rowView(row) {
    const s = statusOf(row);
    const gps = model.data && model.data.summary && model.data.summary.gps_adapter ? GPS[row.gps_place] || GPS.none : "";
    return `<li><button type="button" class="cxp-row" data-cxp-open="${h(row.employee_id)}" aria-label="${h(row.employee_name)}: ${h(statusLabel(row))}. Ver detalle">
      <span class="cxp-dot s-${s}" aria-hidden="true"></span>
      <span class="cxp-who"><span class="cxp-name">${h(row.employee_name || "Empleado")}</span><span class="cxp-role">${h(row.employee_role || "")}</span></span>
      <span class="cxp-chip s-${s}">${h(statusLabel(row))}</span>${extra("rowExtra", row)}
      <span class="cxp-time" ${s === "no_shift" ? "" : timerAttrs(row)}>${s === "no_shift" ? "—" : hm(row.core.shift_effective_seconds)}</span>
      ${gps ? `<small class="cxp-gps g-${h(row.gps_place || "none")}">${h(gps)}</small>` : ""}
    </button></li>`;
  }

  // 071A: ganchos opcionales (horario de la semana). Sin ellos, nada cambia.
  function extra(name, item) {
    return ctx && typeof ctx[name] === "function" ? String(ctx[name](item, model.data) || "") : "";
  }

  function sectionView(group) {
    const c = group.counts || countsOf(group.people);
    const gpsOn = Boolean(model.data && model.data.summary && model.data.summary.gps_adapter);
    const people = sortPeople(searchPeople(group.people, model.query));
    const sup = arr(group.supervisors);
    const kpi = (label, value) => `<div class="cxp-kpi"><span>${h(label)}</span><strong>${h(value)}</strong></div>`;
    return `<section class="cxp-sec" data-cxp-sec="${h(group.key)}" aria-labelledby="cxpSec-${h(group.key)}">
      <header class="cxp-sec-head">
        <h3 id="cxpSec-${h(group.key)}">${h(group.name)}${group.code ? ` <span class="cxp-code">${h(group.code)}</span>` : ""}${group.is_active === false ? ' <span class="cxp-code">desactivado</span>' : ""}</h3>
        ${group.timezone ? `<div class="cxp-clock"><span>Hora local</span> <strong data-cxp-clock="${h(group.timezone)}">${h(localTime(group.timezone))}</strong></div>` : ""}
      </header>${extra("sectionExtra", group)}
      <p class="cxp-sup">${sup.length ? `${sup.length === 1 ? "Supervisor" : "Supervisores"}: ${h(sup.join(", "))}` : group.key === NONE ? "Personas sin lugar de trabajo: asígnalas en Personal." : "Sin supervisor asignado"}</p>
      <div class="cxp-kpis">${kpi("Activos", c.working)}${kpi("En pausa", c.on_break)}${gpsOn ? kpi("En perímetro", c.in_perimeter) : ""}${kpi("Sin turno", c.no_shift)}</div>
      ${people.length ? `<ul class="cxp-list">${people.map(rowView).join("")}</ul>`
        : `<p class="cxp-empty">${arr(group.people).length ? "Nadie coincide con la búsqueda." : "Nadie en este lugar todavía."}</p>`}
    </section>`;
  }

  function view() {
    const d = model.data;
    if (!d) return `<div class="cxp-root"><p class="cxp-empty">${model.error ? h(model.error) : "Cargando CRM Campo…"}</p></div>`;
    const groups = arr(d.groups);
    const shown = shownGroups(groups, model.filter);
    const btns = buttons(groups);
    return `<div class="cxp-root">
      ${model.error ? `<div class="cxp-alert" role="alert">${h(model.error)}</div>` : ""}
      <div class="cxp-bar">
        <div class="cxp-tabs" role="group" aria-label="Lugar de trabajo">${btns.map((b) => `<button type="button" class="cxp-tab ${model.filter === b.key ? "is-active" : ""}" aria-pressed="${model.filter === b.key}" data-cxp-filter="${h(b.key)}">${h(b.label)}${b.key === ALL ? "" : ` (${b.count})`}</button>`).join("")}</div>
        <input class="cxp-search" type="search" data-cxp-search value="${h(model.query)}" placeholder="Buscar por nombre" aria-label="Buscar por nombre">
      </div>
      ${model.filter === ALL && ctx && typeof ctx.top === "function" ? `<div class="cxp-top">${ctx.top(d)}</div>` : ""}
      <div class="cxp-sections ${model.filter === ALL && shown.length > 1 ? "is-all" : ""}">${shown.map(sectionView).join("") || '<p class="cxp-empty">No hay colaboradores operativos para mostrar.</p>'}</div>
      ${model.detail ? detailView() : ""}
    </div>`;
  }

  function findRow(id) {
    for (const g of arr(model.data && model.data.groups)) {
      const row = arr(g.people).find((r) => String(r.employee_id) === String(id));
      if (row) return row;
    }
    return null;
  }

  function detailView() {
    const row = findRow(model.detail);
    if (!row) return "";
    const body = ctx && typeof ctx.detail === "function" ? ctx.detail(row, model.data) : "";
    return `<div class="cxp-modal" data-cxp-modal><div class="cxp-modal-card" role="dialog" aria-modal="true" aria-labelledby="cxpDetailTitle">
      <div class="cxp-modal-head"><h3 id="cxpDetailTitle">${h(row.employee_name)}</h3><button type="button" class="client-btn" data-cxp-close>Cerrar</button></div>
      ${body}
    </div></div>`;
  }

  function host() { return ctx && typeof ctx.host === "function" ? ctx.host() : null; }

  function draw() {
    const el = host();
    if (!el) return;
    const active = document.activeElement;
    const keep = active && active.matches && active.matches("[data-cxp-search]");
    const caret = keep ? active.selectionStart : null;
    el.innerHTML = view();
    applyContrast(el.querySelector(".cxp-root"));
    if (keep) { const again = el.querySelector("[data-cxp-search]"); if (again) { again.focus(); try { again.setSelectionRange(caret, caret); } catch (_) {} } }
    if (model.detail) {
      if (ctx && typeof ctx.afterDetail === "function") ctx.afterDetail();
      const close = el.querySelector("[data-cxp-close]");
      if (close && !(active && active.closest && active.closest("[data-cxp-modal]"))) close.focus();
    }
    ticker();
  }

  function ticker() {
    const el = host();
    if (!el) return;
    const now = Date.now();
    el.querySelectorAll("[data-cxp-timer]").forEach((t) => {
      const extra = t.getAttribute("data-running") === "1" ? Math.max(0, Math.floor((now - Number(t.getAttribute("data-at") || now)) / 1000)) : 0;
      t.textContent = hm(Number(t.getAttribute("data-base") || 0) + extra);
    });
    el.querySelectorAll("[data-cxp-clock]").forEach((c) => { c.textContent = localTime(c.getAttribute("data-cxp-clock")); });
  }

  function stop() {
    if (tick) clearInterval(tick);
    if (refresh) clearInterval(refresh);
    tick = null;
    refresh = null;
  }

  function errorText(error) {
    const raw = String((error && error.message) || error || "");
    const i = raw.indexOf("{");
    try { const d = JSON.parse(i >= 0 ? raw.slice(i) : raw); return typeof d.detail === "string" ? d.detail : raw; } catch (_) { return raw || "No se pudo cargar CRM Campo."; }
  }

  async function load() {
    if (model.loading) return false;
    model.loading = true;
    try {
      const data = await ctx.api(`/work-locations/companies/${encodeURIComponent(ctx.companyId)}/board`);
      if (!data || !Array.isArray(data.groups)) throw new Error("Respuesta sin lugares.");
      model.data = data;
      model.error = "";
      model.filter = validFilter(data.groups, model.filter);
      return true;
    } catch (error) {
      model.error = model.data ? `No se pudo actualizar: ${errorText(error)}` : errorText(error);
      return false;
    } finally {
      model.loading = false;
    }
  }

  // ------------------------------------------------------------ eventos
  function inside(t) { const el = host(); return el && el.contains(t); }

  function onClick(event) {
    const t = event.target;
    if (!t || !t.closest || !inside(t)) return;
    const f = t.closest("[data-cxp-filter]");
    if (f) { model.filter = f.getAttribute("data-cxp-filter"); saveChoice(ctx.companyId, model.filter); draw(); return; }
    const open = t.closest("[data-cxp-open]");
    if (open) { model.detail = open.getAttribute("data-cxp-open"); draw(); return; }
    if (t.closest("[data-cxp-close]") || (t.matches && t.matches("[data-cxp-modal]"))) { const id = model.detail; model.detail = null; draw(); focusRow(id); }
  }
  function focusRow(id) {
    const el = host();
    const row = el && id ? el.querySelector(`[data-cxp-open="${CSS.escape ? CSS.escape(id) : id}"]`) : null;
    if (row) row.focus();
  }
  function onInput(event) {
    const t = event.target;
    if (!t || !t.matches || !inside(t) || !t.matches("[data-cxp-search]")) return;
    model.query = t.value;
    draw();
  }
  function onKey(event) {
    if (event.key !== "Escape" || !model.detail || !host()) return;
    const id = model.detail;
    model.detail = null;
    draw();
    focusRow(id);
  }

  async function mount(context) {
    stop();
    ctx = context;
    model.data = null;
    model.error = "";
    model.query = "";
    model.detail = null;
    model.filter = readChoice(ctx.companyId);
    if (!bound && typeof document.addEventListener === "function") {
      document.addEventListener("click", onClick);
      document.addEventListener("input", onInput);
      document.addEventListener("keydown", onKey);
      bound = true;
    }
    draw();
    const ok = await load();
    if (!ok && !model.data) return false;
    draw();
    tick = setInterval(() => { if (!host()) { stop(); return; } ticker(); }, 1000);
    refresh = setInterval(async () => { if (!host()) { stop(); return; } if (model.detail) return; await load(); draw(); }, REFRESH_MS);
    return true;
  }

  async function reload() { if (!ctx || !host()) return false; const ok = await load(); draw(); return ok; }

  window.CxCrmPlaces = { mount, view, model, reload, sortPeople, searchPeople, countsOf, buttons, shownGroups, validFilter, localTime, tzOffsetMinutes, hm,
    statusOf, statusLabel, readChoice, saveChoice, storageKey, pair, contrast, GPS, ALL, NONE };
})();
