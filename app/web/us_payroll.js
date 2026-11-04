// Nómina y tiempos EE. UU. (interruptor us_payroll del módulo payroll; hoy solo VOLTAGE).
// Piezas de pantalla compartidas por Reportes v2 y Nómina v2: la línea de tiempo de cada
// turno (entrada, pausas, salida, cierre por supervisor, notas y totales), la semana
// laboral por persona y el desglose de nómina. Solo presentación: las cifras llegan del
// servidor (app/services/us_time.py, una sola regla para bot, Reportes, Nómina, PDF y
// CSV). Sin tarifa el dinero dice "Pendiente", nunca $0.00. Solo colores del tema.
(() => {
  "use strict";

  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const num = (v) => { const n = Number(v); return Number.isFinite(n) ? n : 0; };
  const T = (s, vars) => {
    const fill = (x) => (vars ? String(x).replace(/\{(\w+)\}/g, (m, k) => (vars[k] !== undefined ? String(vars[k]) : m)) : String(x));
    return typeof window !== "undefined" && window.CxI18n && typeof window.CxI18n.t === "function" ? window.CxI18n.t(s, vars) : fill(s);
  };
  const WEEKDAY = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
  const PENDING = "Pendiente";

  function hm(minutes) {
    const m = Math.max(0, Math.round(num(minutes)));
    return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`;
  }

  // Dinero: sin tarifa (o sin valor) siempre "Pendiente".
  function money(value, pending, fmt) {
    if (pending || value === null || value === undefined) return T(PENDING);
    return typeof fmt === "function" ? fmt(num(value)) : `$${num(value).toFixed(2)}`;
  }

  function dayLabel(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
    if (!m) return "—";
    const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), 12));
    return `${T(WEEKDAY[d.getUTCDay()])} ${m[3]}/${m[2]}`;
  }

  const punch = (p) => (p ? `${p.local} ${p.abbr}` : "—");

  function place(loc) {
    if (!loc) return "";
    const label = `${T(loc.label || "Sin ubicación")}${loc.perimeter ? ` · ${loc.perimeter}` : ""}`;
    const cls = loc.status === "inside" ? "is-in" : loc.status === "outside" ? "is-out" : "is-none";
    return `<span class="usp-loc ${cls}">${h(label)}</span>${loc.map ? ` <a class="usp-map" href="${h(loc.map)}" target="_blank" rel="noopener noreferrer">${h(T("Ver en el mapa"))}</a>` : ""}`;
  }

  // Línea de tiempo de UN turno (t = shift.us del servidor).
  function timeline(t) {
    if (!t) return "";
    const items = [];
    // 067A: la marca del panel del líder se distingue; la del bot sigue sin etiqueta.
    const origin = (m) => (m && m.origin === "pin" ? ` <small class="usp-origin">${h(T("Panel PIN"))}</small>` : "");
    items.push(`<li class="usp-step is-in"><b>${h(T("Entrada"))}</b> <span class="usp-time">${h(punch(t.check_in))}</span>${origin(t.check_in)} ${place(t.check_in && t.check_in.location)}</li>`);
    arr(t.pauses).forEach((p) => {
      items.push(`<li class="usp-step is-pause"><b>${h(T("Pausa"))}</b> <span class="usp-time">${h(punch(p.start))} – ${h(p.end ? punch(p.end) : "—")}</span>
        <span class="usp-dur">${h(hm(p.minutes))} ${h(T("sin pago"))}</span>${p.start ? ` ${place(p.start.location)}` : ""}${p.closed_by_checkout ? ` <small>${h(T("(terminó al finalizar el turno)"))}</small>` : ""}</li>`);
    });
    const m = t.manual_close;
    const closed = m ? `<div class="usp-manual">${h(T("Lo cerró {by}", { by: m.by || T("un supervisor") }))} · ${h(T("hora puesta"))} ${h(punch(t.check_out))}${m.note ? ` · “${h(m.note)}”` : ""}</div>`
      : t.confirmed ? `<div class="usp-manual">${h(T("Salida confirmada en Nómina"))}</div>` : t.system_cutoff ? `<div class="usp-manual">${h(T("Cerrado por el sistema"))}</div>` : "";
    items.push(`<li class="usp-step is-out"><b>${h(T("Salida"))}</b> <span class="usp-time">${h(punch(t.check_out))}</span>${origin(t.check_out)} ${place(t.check_out && t.check_out.location)}${closed}</li>`);
    const totals = `<dl class="usp-totals">
      <div><dt>${h(T("En turno"))}</dt><dd>${h(hm(t.connected_minutes))}</dd></div>
      <div><dt>${h(T("Pausas (sin pago)"))}</dt><dd>${h(hm(t.pause_minutes))}</dd></div>
      <div class="is-main"><dt>${h(T("Tiempo pagable"))}</dt><dd>${h(hm(t.payable_minutes))}</dd></div>
      ${num(t.overtime_minutes) ? `<div><dt>${h(T("Overtime"))}</dt><dd>${h(hm(t.overtime_minutes))}</dd></div>` : ""}</dl>`;
    const notes = arr(t.notes).filter((n) => n.text);
    const noteList = notes.length ? `<div class="usp-notes"><b>${h(T("Notas"))}</b><ul>${notes.map((n) => `<li><span class="usp-time">${h(n.local || "")}</span> <i>${h(T(n.label || n.kind))}</i><p>${h(n.text)}</p></li>`).join("")}</ul></div>` : "";
    const head = `<div class="usp-head"><b>${h(dayLabel(t.check_in && t.check_in.date))}</b> · ${h(t.place || T("Sin lugar asignado"))} · ${h(T("hora {abbr}", { abbr: t.abbr || "" }))}${t.place_missing ? ` <small class="usp-warn">${h(T("Sin lugar asignado: hora de la empresa"))}</small>` : ""}</div>`;
    return `<article class="usp-shift">${head}<ol class="usp-line">${items.join("")}</ol>${totals}${noteList}</article>`;
  }

  // Semana laboral por persona: horas pagables de cada día, total, regulares y overtime.
  function weekTable(weeks) {
    const list = arr(weeks);
    if (!list.length) return "";
    return `<table class="usp-week"><thead><tr><th scope="col">${h(T("Semana"))}</th><th scope="col">${h(T("Días"))}</th><th scope="col">${h(T("Total"))}</th>
      <th scope="col">${h(T("Regulares"))}</th><th scope="col">${h(T("Overtime"))}</th></tr></thead><tbody>
      ${list.map((w) => `<tr><th scope="row">${h(dayLabel(w.week_start))} – ${h(dayLabel(w.week_end))}</th>
        <td>${arr(w.days).map((d) => `<span class="usp-day">${h(dayLabel(d.date))} <b>${h(hm(d.payable))}</b></span>`).join(" ")}</td>
        <td><b>${h(hm(w.payable))}</b></td><td>${h(hm(w.regular))}</td><td>${num(w.overtime) ? `<b class="usp-ot">${h(hm(w.overtime))}</b>` : h(hm(0))}</td></tr>`).join("")}
      </tbody></table>`;
  }

  // Desglose de nómina de una persona (row.us del snapshot).
  function breakdown(row, fmt) {
    const u = (row && row.us) || {};
    const pending = !!row.rate_pending;
    const cell = (label, value, cls = "") => `<div class="${cls}"><dt>${h(T(label))}</dt><dd>${h(value)}</dd></div>`;
    return `<dl class="usp-break">
      ${cell("Lugar", u.place || T("Sin lugar asignado"))}${cell("Días trabajados", String(num(u.days_worked)))}
      ${cell("Horas en turno", hm(u.connected_minutes))}${cell("Pausas (sin pago)", hm(u.pause_minutes))}
      ${cell("Horas pagables", hm(u.payable_minutes), "is-main")}${cell("Regulares", hm(u.regular_minutes))}${cell("Overtime", hm(u.overtime_minutes))}
      ${cell("Tarifa", pending ? T("Tarifa pendiente") : money(u.rate, false, fmt))}
      ${cell("Bruto regular", money(u.regular_amount, pending, fmt))}${cell("Bruto overtime (1.5x)", money(u.overtime_amount, pending, fmt))}
      ${cell("Deducciones", money(u.deductions, pending, fmt))}${cell("Neto", money(u.net, pending, fmt), "is-main")}
    </dl>`;
  }

  function missingRate(list) {
    const items = arr(list);
    if (!items.length) return "";
    return `<div class="usp-alert" role="status"><b>${h(T("{n} empleados sin tarifa", { n: items.length }))}</b>: ${items.map((m) => h(m.employee_name || m)).join(", ")}. ${h(T("Su dinero queda Pendiente hasta cargar la tarifa."))}</div>`;
  }

  function rulesLine(rules) {
    const r = rules || {};
    const days = { sunday: "domingo", monday: "lunes", tuesday: "martes", wednesday: "miércoles", thursday: "jueves", friday: "viernes", saturday: "sábado" };
    return T("Semana laboral: {day} {time} (hora del lugar) · Overtime: más de {limit} por semana a {factor}x · Pausas sin pago",
      { day: T(days[r.week_start_day] || r.week_start_day || "domingo"), time: r.week_start_time || "00:00", limit: hm(r.overtime_after_minutes || 2400).replace(" 00 min", ""), factor: r.overtime_factor || 1.5 });
  }

  window.CxUsPayroll = { hm, money, dayLabel, punch, timeline, weekTable, breakdown, missingRate, rulesLine };
})();
