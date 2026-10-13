// Reportes v2 (interruptor reports_v2 del módulo reports; hoy solo VOLTAGE).
// Una sola pantalla a pantalla completa: seis cifras, horas por día, alertas,
// materiales, inventario bajo mínimo y personal, con PDF para ver, imprimir y
// descargar. Los datos salen de /reports/.../general (insights_v2, el mismo
// cálculo del PDF). Textos por t() (diccionario único), dinero, fechas y zona
// por CxLocale. Solo el dueño y el director entran (el servidor responde 403).
(() => {
  "use strict";

  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const num = (v) => Number(v || 0) || 0;
  const fill = (s, vars) => (vars ? String(s).replace(/\{(\w+)\}/g, (m, k) => (vars[k] !== undefined ? String(vars[k]) : m)) : String(s));
  const T = (s, vars) => (typeof window !== "undefined" && window.CxI18n && typeof window.CxI18n.t === "function" ? window.CxI18n.t(s, vars) : fill(s, vars));
  const L = () => (typeof window !== "undefined" ? window.CxLocale : null);

  const PRESETS = [["today", "Hoy"], ["week", "Esta semana"], ["month", "Mes"], ["custom", "Personalizado"]];
  const BOXES = [["requested", "Solicitadas"], ["delivered", "Entregadas"], ["consigned", "Consignadas/instaladas"], ["returned", "Devueltas"]];
  const STATUS = {
    pending: "Pendiente", pendiente: "Pendiente", approved: "Aprobada", aprobado: "Aprobada", requested: "Solicitada", delivered: "Entregada",
    entregado: "Entregada", consigned: "Consignada", consigned_partial: "Consignada parcial", returned: "Devuelta", returned_partial: "Devuelta parcial",
    rejected: "Rechazada", cancelled: "Cancelada",
  };
  const STATE = { working: "En turno", break: "En pausa", off: "Fuera de turno" };

  const model = { preset: "week", from: "", to: "", employeeId: "", data: null, loading: false, error: "", denied: false, modal: null, busy: "" };
  let ctx = null;
  let bound = false;

  // ------------------------------------------------------------ formatos
  function hm(minutes) {
    const m = Math.max(0, Math.round(num(minutes)));
    return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`;
  }
  function money(v) {
    const legacy = (x) => `$ ${Math.round(num(x)).toLocaleString("es-CO")}`;
    const loc = L();
    return loc && typeof loc.money === "function" ? loc.money(num(v), legacy) : legacy(v);
  }
  const lang = () => (window.CxI18n && window.CxI18n.locale ? window.CxI18n.locale() : "es-CO");
  function when(value, withTime = true) {
    if (!value) return "—";
    const loc = L();
    const opts = withTime ? { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false } : { weekday: "short", day: "2-digit", month: "short" };
    if (loc && typeof loc.dateTime === "function") {
      const d = /^\d{4}-\d{2}-\d{2}$/.test(String(value)) ? `${value}T12:00:00Z` : value;
      return loc.dateTime(d, opts, lang()) || "—";
    }
    return String(value).slice(0, 16).replace("T", " ");
  }
  function today() {
    const loc = L();
    return (loc && typeof loc.filterDay === "function" && loc.filterDay(new Date())) || new Date().toISOString().slice(0, 10);
  }
  function addDays(iso, n) { const d = new Date(`${iso}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); }

  // Rango del filtro en el día de la empresa: Hoy, Esta semana (lunes a hoy), Mes (día 1 a hoy) o Personalizado.
  function range(preset = model.preset, base = today()) {
    if (preset === "today") return { from: base, to: base };
    if (preset === "week") { const wd = (new Date(`${base}T12:00:00Z`).getUTCDay() + 6) % 7; return { from: addDays(base, -wd), to: base }; }
    if (preset === "month") return { from: `${base.slice(0, 8)}01`, to: base };
    return { from: model.from || base, to: model.to || base };
  }

  function query(extra = {}) {
    const r = range();
    const p = new URLSearchParams({ preset: "custom", start_date: r.from, end_date: r.to, ...extra });
    if (model.employeeId) p.set("employee_id", model.employeeId);
    return p.toString();
  }

  // ------------------------------------------------------------ datos
  const base = () => `${ctx.apiBase}/reports/companies/${encodeURIComponent(ctx.companyId)}`;
  const headers = () => { const t = ctx.token(); return t ? { Authorization: `Bearer ${t}` } : {}; };

  async function load() {
    model.loading = true; model.error = ""; draw();
    try {
      const res = await fetch(`${base()}/general?${query()}`, { headers: headers() });
      if (res.status === 403 || res.status === 401) { model.denied = true; model.data = null; return; }
      if (!res.ok) throw new Error(`${res.status}`);
      model.denied = false;
      model.data = await res.json();
    } catch (error) {
      model.error = T("No se pudo cargar Reportes.");
    } finally { model.loading = false; draw(); }
  }

  async function pdfBlob(disposition) {
    const res = await fetch(`${base()}/export.pdf?${query({ disposition })}`, { headers: headers() });
    if (res.status === 403 || res.status === 401) throw new Error(T("Reportes es solo del dueño y del director"));
    if (!res.ok) throw new Error(T("No se pudo generar el PDF."));
    return URL.createObjectURL(await res.blob());
  }

  async function pdfAction(kind) {
    model.busy = kind; model.error = ""; draw();
    const tab = kind === "view" ? window.open("", "_blank") : null; // se abre ya (si no, el navegador lo bloquea)
    try {
      if (kind === "view") {
        const url = await pdfBlob("inline");
        if (tab) tab.location.href = url; else window.open(url, "_blank");
      } else if (kind === "print") {
        const url = await pdfBlob("inline");
        const frame = document.createElement("iframe");
        frame.className = "rr-print-frame";
        frame.setAttribute("aria-hidden", "true");
        frame.src = url;
        frame.onload = () => {
          try { frame.contentWindow.focus(); frame.contentWindow.print(); } catch (_) { window.open(url, "_blank"); }
        };
        document.body.appendChild(frame);
        setTimeout(() => frame.remove(), 120000);
      } else {
        const url = await pdfBlob("attachment");
        const a = document.createElement("a");
        a.href = url;
        a.download = `reporte_${(ctx.company && ctx.company.slug) || "empresa"}_${range().from}_${range().to}.pdf`;
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 60000);
      }
    } catch (error) {
      if (tab) tab.close();
      model.error = error.message || T("No se pudo generar el PDF.");
    } finally { model.busy = ""; draw(); }
  }

  // ------------------------------------------------------------ vistas
  function head() {
    const company = (model.data && model.data.company) || ctx.company || {};
    const logo = company.logo_url ? `<img class="rr-logo" src="${h(company.logo_url)}" alt="">` : `<span class="rr-logo rr-logo-txt">${h(String(company.name || "?").slice(0, 1))}</span>`;
    return `<header class="client-hero rr-head"><button type="button" class="rr-btn rr-back" data-rr-back>← ${h(T("Módulos"))}</button>
      <div class="rr-brand">${logo}<div><p class="client-eyebrow">${h(company.name || "")}</p><h1 class="client-title">${h(T("Reportes"))}</h1></div></div></header>`;
  }

  function bar() {
    const people = arr(model.data && model.data.details && model.data.details.employees).filter((e) => e.status !== "archived");
    const r = range();
    return `<section class="client-panel rr-bar">
      <div class="rr-seg" role="group" aria-label="${h(T("Periodo"))}">${PRESETS.map(([k, l]) => `<button type="button" class="${model.preset === k ? "client-btn is-on" : ""}" data-rr-preset="${k}" aria-pressed="${model.preset === k}">${h(T(l))}</button>`).join("")}</div>
      ${model.preset === "custom" ? `<label class="rr-field">${h(T("Desde"))}<input type="date" data-rr-from value="${h(r.from)}"></label><label class="rr-field">${h(T("Hasta"))}<input type="date" data-rr-to value="${h(r.to)}"></label>` : ""}
      <label class="rr-field rr-person">${h(T("Persona"))}<select data-rr-person><option value="">${h(T("Toda la cuadrilla"))}</option>${people.map((e) => `<option value="${h(e.id)}" ${model.employeeId === String(e.id) ? "selected" : ""}>${h(e.full_name)}</option>`).join("")}</select></label>
      <div class="rr-actions"><button type="button" class="rr-btn" data-rr-pdf="view" ${model.busy ? "disabled" : ""}>${h(T("Ver PDF"))}</button>
        <button type="button" class="rr-btn" data-rr-pdf="print" ${model.busy ? "disabled" : ""}>${h(T("Imprimir"))}</button>
        <button type="button" class="client-btn rr-btn is-primary" data-rr-pdf="download" ${model.busy ? "disabled" : ""}>${h(T("Descargar PDF"))}</button></div></section>`;
  }

  function figures(f) {
    const tiles = [
      ["En turno ahora", `${num(f.in_shift)}`, T("de {n} activos", { n: num(f.active) })],
      ["Horas trabajadas", hm(num(f.regular_minutes) + num(f.extra_minutes)), T("{ord} ordinarias + {ext} extra", { ord: hm(f.regular_minutes), ext: hm(f.extra_minutes) })],
      ["Nómina del periodo", money(f.net), T("neto")],
      ["Fuera de perímetro", `${num(f.gps_outside)}`, T("marcaciones")],
      ["Material pendiente", `${num(f.materials_pending)}`, T("órdenes sin entregar o sin devolver")],
      ["Stock bajo", `${num(f.low_stock)}`, T("{n} en cero", { n: num(f.zero_stock) })],
    ];
    return `<div class="rr-figs">${tiles.map(([l, v, s]) => `<div class="rr-fig"><small>${h(T(l))}</small><b>${h(v)}</b><span>${h(s)}</span></div>`).join("")}</div>`;
  }

  function hoursChart(days) {
    const list = arr(days);
    const max = Math.max(1, ...list.map((d) => num(d.regular) + num(d.extra)));
    if (!list.some((d) => num(d.regular) || num(d.extra))) return `<p class="client-muted rr-muted">${h(T("Sin horas en el periodo."))}</p>`;
    return `<div class="rr-legend"><i class="is-reg"></i>${h(T("Ordinarias"))}<i class="is-ext"></i>${h(T("Extra"))}</div><ul class="rr-hours">${list.map((d) => {
      const total = num(d.regular) + num(d.extra);
      return `<li><span class="rr-hday">${h(when(d.date, false))}</span><span class="rr-hbar" role="img" aria-label="${h(`${hm(d.regular)} · ${hm(d.extra)}`)}"><i class="is-reg" style="--w:${(num(d.regular) / max) * 100}%"></i><i class="is-ext" style="--w:${(num(d.extra) / max) * 100}%"></i></span><b>${h(total ? hm(total) : "—")}</b></li>`;
    }).join("")}</ul>`;
  }

  function alertText(a) {
    if (a.kind === "gps_outside") return T("Marcación fuera de perímetro: {employee} · {at}", { employee: a.employee || "—", at: when(a.at) });
    if (a.kind === "weekly_hours") return T("{employee} pasó las {limit} de la semana del {week}: {hours}", { employee: a.employee || "—", limit: hm(a.limit), week: when(a.week, false), hours: hm(a.minutes) });
    if (a.kind === "stale_delivery") return T("Orden {order} ({material}) entregada hace más de 2 días sin devolución ni consigna · {employee}", { order: a.order || "", material: a.material || "", employee: a.employee || "—" });
    return T("Material en cero: {material}", { material: a.material || "" });
  }

  function alerts(list) {
    if (!arr(list).length) return `<p class="client-muted rr-muted">${h(T("Sin alertas."))}</p>`;
    return `<ul class="rr-alerts">${arr(list).map((a) => `<li class="is-${h(a.level || "warning")}">${h(alertText(a))}</li>`).join("")}</ul>`;
  }

  function materials(boxes) {
    return `<div class="rr-boxes">${BOXES.map(([k, l], i) => `<button type="button" class="rr-box" data-rr-box="${k}" aria-haspopup="dialog"><small>${h(T(l))}</small><b>${arr(boxes && boxes[k]).length}</b></button>${i < BOXES.length - 1 ? `<span class="rr-arrow" aria-hidden="true">→</span>` : ""}`).join("")}</div>`;
  }

  function inventory(list) {
    if (!arr(list).length) return `<p class="client-muted rr-muted">${h(T("Sin materiales bajo el mínimo."))}</p>`;
    return `<div class="rr-table" role="table"><div class="rr-row is-head" role="row"><span>${h(T("Material"))}</span><span>${h(T("Stock"))}</span><span>${h(T("Mínimo"))}</span><span></span></div>
      ${arr(list).map((i) => `<div class="rr-row" role="row"><span>${h(i.material)}</span><span>${h(i.stock)}</span><span>${h(i.min)}</span><span><i class="rr-tag ${i.label === "zero" ? "is-zero" : "is-low"}">${h(T(i.label === "zero" ? "Cero" : "Bajo"))}</i></span></div>`).join("")}</div>`;
  }

  function people(list) {
    if (!arr(list).length) return `<p class="client-muted rr-muted">${h(T("Sin colaboradores."))}</p>`;
    return `<div class="rr-people">${arr(list).map((p) => `<button type="button" class="rr-person-card" data-rr-person-open="${h(p.employee_id)}" aria-haspopup="dialog">
      <span class="rr-pc-head"><b>${h(p.name)}</b><i class="rr-tag is-${h(p.state)}">${h(T(STATE[p.state] || p.state))}</i></span><small>${h(p.role || "")}</small>
      <span class="rr-pc-nums"><span>${h(T("Horas"))} <b>${h(hm(num(p.regular) + num(p.extra)))}</b></span><span>${h(T("Extra"))} <b>${h(hm(p.extra))}</b></span>
        <span>${h(T("Fuera de perímetro"))} <b>${h(p.gps_outside)}</b></span>${p.orders_requested !== null && p.orders_requested !== undefined ? `<span>${h(T("Órdenes pedidas"))} <b>${h(p.orders_requested)}</b></span>` : ""}
        ${p.deliveries !== null && p.deliveries !== undefined ? `<span>${h(T("Entregas"))} <b>${h(p.deliveries)}</b></span>` : ""}<span>${h(T("Neto"))} <b>${h(money(p.net))}</b></span></span></button>`).join("")}</div>`;
  }

  function modalView(ins) {
    if (!model.modal) return "";
    let title = "", body = "";
    if (model.modal.type === "box") {
      const box = BOXES.find(([k]) => k === model.modal.key) || ["", ""];
      const list = arr(ins.materials && ins.materials[model.modal.key]);
      title = T(box[1]);
      body = list.length ? `<div class="rr-table rr-orders" role="table"><div class="rr-row is-head" role="row"><span>${h(T("Orden"))}</span><span>${h(T("Material"))}</span><span>${h(T("Cantidad"))}</span><span>${h(T("Colaborador"))}</span><span>${h(T("Estado"))}</span></div>
        ${list.map((o) => `<div class="rr-row" role="row"><span>${h(o.order)}</span><span>${h(o.material)}</span><span>${h(`${o.quantity} ${o.unit || ""}`.trim())}</span><span>${h(o.employee)}</span><span>${h(T(STATUS[o.status] || o.status))}</span></div>`).join("")}</div>`
        : `<p class="client-muted rr-muted">${h(T("Sin órdenes."))}</p>`;
    } else {
      const p = arr(ins.people).find((x) => x.employee_id === model.modal.id);
      if (!p) return "";
      title = p.name;
      body = p.shifts.length ? `<div class="rr-table rr-shifts" role="table"><div class="rr-row is-head" role="row"><span>${h(T("Entrada"))}</span><span>${h(T("Salida"))}</span><span>${h(T("Ordinarias"))}</span><span>${h(T("Extra"))}</span><span>${h(T("Bruto"))}</span></div>
        ${p.shifts.map((s) => `<div class="rr-row" role="row"><span>${h(when(s.start))}</span><span>${h(when(s.end))}</span><span>${h(hm(s.regular))}</span><span>${h(hm(s.extra))}</span><span>${h(money(s.gross))}</span></div>`).join("")}</div>`
        : `<p class="client-muted rr-muted">${h(T("Sin turnos en el periodo."))}</p>`;
    }
    return `<div class="rr-overlay" data-rr-overlay><div class="client-panel rr-modal" role="dialog" aria-modal="true" aria-labelledby="rrModalTitle">
      <header class="rr-modal-head"><h2 id="rrModalTitle">${h(title)}</h2><button type="button" class="rr-btn is-small" data-rr-close aria-label="${h(T("Cerrar"))}">✕</button></header>${body}</div></div>`;
  }

  function view() {
    if (model.denied) return `<div class="rr-root" data-rr-root>${head()}<section class="client-panel rr-denied"><p>${h(T("Reportes es solo del dueño y del director"))}</p></section></div>`;
    const ins = (model.data && model.data.insights_v2) || null;
    const body = !ins ? `<section class="client-panel"><p class="client-muted rr-muted">${h(model.loading ? T("Cargando…") : T("Sin datos."))}</p></section>` : `
      ${figures(ins.figures || {})}
      <div class="rr-grid">
        <section class="client-panel"><h2 class="client-eyebrow rr-h">${h(T("Horas por día"))}</h2>${hoursChart(ins.hours_by_day)}</section>
        <section class="client-panel"><h2 class="client-eyebrow rr-h">${h(T("Alertas"))}<b>${arr(ins.alerts).length}</b></h2>${alerts(ins.alerts)}</section>
      </div>
      <div class="rr-grid">
        <section class="client-panel"><h2 class="client-eyebrow rr-h">${h(T("Materiales"))}</h2>${materials(ins.materials)}</section>
        <section class="client-panel"><h2 class="client-eyebrow rr-h">${h(T("Inventario bajo mínimo"))}</h2>${inventory(ins.inventory_low)}</section>
      </div>
      <section class="client-panel"><h2 class="client-eyebrow rr-h">${h(T("Personal"))}</h2>${people(ins.people)}</section>`;
    return `<div class="rr-root" data-rr-root>${head()}${bar()}
      ${model.error ? `<div class="rr-notice" role="alert">${h(model.error)}</div>` : ""}${model.loading && ins ? `<p class="client-muted rr-muted" role="status">${h(T("Cargando…"))}</p>` : ""}
      ${body}${ins ? modalView(ins) : ""}</div>`;
  }

  function draw() { if (!ctx) return; const host = ctx.host(); if (host) host.innerHTML = view(); }

  // ------------------------------------------------------------ eventos
  function onClick(event) {
    const t = event.target;
    if (!ctx || !t || !t.closest || !t.closest("[data-rr-root]")) return;
    const attr = (a) => { const el = t.closest(`[${a}]`); return el ? el.getAttribute(a) : null; };
    let v;
    if (t.closest("[data-rr-back]")) { ctx.back(); return; }
    if ((v = attr("data-rr-preset"))) { model.preset = v; if (v === "custom") { const r = range("week"); model.from = model.from || r.from; model.to = model.to || r.to; } load(); return; }
    if ((v = attr("data-rr-pdf"))) { pdfAction(v); return; }
    if ((v = attr("data-rr-box"))) { model.modal = { type: "box", key: v }; draw(); return; }
    if ((v = attr("data-rr-person-open"))) { model.modal = { type: "person", id: v }; draw(); return; }
    if (t.closest("[data-rr-close]") || (t.matches && t.matches("[data-rr-overlay]"))) { model.modal = null; draw(); }
  }

  function onChange(event) {
    const t = event.target;
    if (!ctx || !t || !t.closest || !t.closest("[data-rr-root]")) return;
    if (t.hasAttribute("data-rr-person")) { model.employeeId = t.value; load(); return; }
    if (t.hasAttribute("data-rr-from")) { model.from = t.value; load(); return; }
    if (t.hasAttribute("data-rr-to")) { model.to = t.value; load(); }
  }

  function onKey(event) { if (ctx && event.key === "Escape" && model.modal) { model.modal = null; draw(); } }

  async function mount(context) {
    ctx = context;
    if (!bound && typeof document.addEventListener === "function") {
      document.addEventListener("click", onClick);
      document.addEventListener("change", onChange);
      document.addEventListener("keydown", onKey);
      bound = true;
    }
    model.modal = null;
    draw();
    await load();
  }

  window.CxReportsV2 = { mount, model, view, range, hm, money, alertText, query };
})();
