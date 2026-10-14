// Turnos (módulo shifts; solo empresas con el módulo activo, hoy VOLTAGE).
// Tres pestañas: Malla | Cambios (n) | Configuración. La malla se arma sola
// (borrador determinista con reglas duras y blandas), se publica al bot y,
// ya publicada, solo cambia con "⇄ Cambio de turno" (lo crea el supervisor).
// Datos en /turnos/companies/{id}/...; el servidor valida sesión, módulo y rol.
// Textos por t() (diccionario único), fechas por CxLocale.
(() => {
  "use strict";

  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const num = (v) => Number(v || 0) || 0;
  const fill = (s, vars) => (vars ? String(s).replace(/\{(\w+)\}/g, (m, k) => (vars[k] !== undefined ? String(vars[k]) : m)) : String(s));
  const T = (s, vars) => (typeof window !== "undefined" && window.CxI18n && typeof window.CxI18n.t === "function" ? window.CxI18n.t(s, vars) : fill(s, vars));
  const L = () => (typeof window !== "undefined" ? window.CxLocale : null);

  const STATUS = { pending: "Creada", waiting: "Esperando respuesta", accepted: "Aceptado", rejected: "Rechazado", expired: "Vencido", cancelled: "Cancelado" };
  const REASON = {
    rest: "sin el descanso mínimo", cap: "pasa el tope semanal", days_off: "se queda sin día libre", consecutive_days: "demasiados días seguidos",
    consecutive_nights: "demasiadas noches seguidas", role: "otro rol", same_shift: "ya tiene ese turno",
  };
  const REST_OPTS = [8, 9, 10, 11, 12, 14, 16, 24];
  const OFF_OPTS = [0, 1, 2, 3];
  const DAYS_OPTS = [3, 4, 5, 6, 7];
  const NIGHT_OPTS = [1, 2, 3, 4, 5, 6, 7];
  const CAP_OPTS = [20, 24, 30, 36, 40, 42, 44, 46, 48, 50, 56, 60];
  const RESP_OPTS = [0.5, 1, 2, 4, 8, 12, 24];

  const model = { tab: "grid", week: "", ctx: null, data: null, changes: [], draft: null, error: "", info: "", busy: "", denied: "", modal: null, loading: false };
  let ctx = null;
  let bound = false;

  // ------------------------------------------------------------ formatos
  function hm(minutes) {
    const m = Math.max(0, Math.round(num(minutes)));
    return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`;
  }
  const lang = () => (window.CxI18n && window.CxI18n.locale ? window.CxI18n.locale() : "es-CO");
  function fmt(iso, opts) {
    if (!iso) return "—";
    const loc = L();
    const d = /^\d{4}-\d{2}-\d{2}$/.test(String(iso)) ? `${iso}T12:00:00Z` : iso;
    if (loc && typeof loc.dateTime === "function") return loc.dateTime(d, opts, lang()) || "—";
    try { return new Intl.DateTimeFormat(lang(), { ...opts, timeZone: "UTC" }).format(new Date(d)); } catch (_) { return String(iso).slice(0, 10); }
  }
  const dayShort = (iso) => fmt(iso, { weekday: "short", day: "numeric" });
  const dayLong = (iso) => fmt(iso, { weekday: "short", day: "2-digit", month: "short" });
  const stamp = (iso) => fmt(iso, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });
  function today() {
    const loc = L();
    return (loc && typeof loc.filterDay === "function" && loc.filterDay(new Date())) || new Date().toISOString().slice(0, 10);
  }
  function addDays(iso, n) { const d = new Date(`${iso}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); }
  function monday(iso) { const wd = (new Date(`${iso}T12:00:00Z`).getUTCDay() + 6) % 7; return addDays(iso, -wd); }

  const tpl = (id) => arr(model.ctx && model.ctx.templates).find((t) => t.id === id) || null;
  const emp = (id) => arr(model.ctx && model.ctx.employees).find((e) => e.id === id) || null;
  const roleLabel = (code) => { const r = arr(model.ctx && model.ctx.roles).find((x) => x.code === code); return r ? r.label : code; };
  const can = (k) => !!(model.ctx && model.ctx.can && model.ctx.can[k]);

  function gapText(g) {
    const vars = { n: num(g.missing), role: roleLabel(g.role).toLowerCase(), shift: g.template, day: dayShort(g.date) };
    return num(g.missing) === 1 ? T("Falta 1 {role} · {shift} · {day}", vars) : T("Faltan {n} {role} · {shift} · {day}", vars);
  }
  function reasonText(list) { return arr(list).map((r) => T(REASON[r] || r)).join(", "); }

  // ------------------------------------------------------------ datos
  const base = () => `${ctx.apiBase}/turnos/companies/${encodeURIComponent(ctx.companyId)}`;
  const headers = (json) => { const t = ctx.token(); return { ...(t ? { Authorization: `Bearer ${t}` } : {}), ...(json ? { "Content-Type": "application/json" } : {}) }; };

  async function call(path, method = "GET", body = undefined) {
    const res = await fetch(`${base()}${path}`, { method, headers: headers(body !== undefined), body: body !== undefined ? JSON.stringify(body) : undefined });
    if (res.status === 401 || res.status === 403 || res.status === 404) {
      let detail = "";
      try { const j = await res.json(); detail = typeof j.detail === "string" ? j.detail : ""; } catch (_) {}
      const err = new Error(detail ? T(detail) : T("No tienes acceso a Turnos."));
      err.status = res.status;
      throw err;
    }
    if (!res.ok) {
      let msg = T("No se pudo completar la acción.");
      try { const j = await res.json(); if (j && j.detail) msg = T(typeof j.detail === "string" ? j.detail : (j.detail.message || msg)); } catch (_) {}
      throw new Error(msg);
    }
    return res.json();
  }

  async function loadAll() {
    model.loading = true; model.error = ""; draw();
    try {
      model.ctx = await call("/context");
      model.draft = null;
      const [week, changes] = await Promise.all([call(`/week?start=${model.week}`), call("/changes")]);
      model.data = week; model.changes = arr(changes.items); model.denied = "";
    } catch (error) {
      if (error.status && error.status !== 404 && model.ctx === null) model.denied = error.message;
      else if (error.status === 403 || error.status === 401) model.denied = error.message;
      else model.error = error.message || T("No se pudo cargar Turnos.");
    } finally { model.loading = false; draw(); }
  }

  async function loadWeek() {
    try { model.data = await call(`/week?start=${model.week}`); } catch (error) { model.error = error.message; }
    draw();
  }

  async function act(kind, fn) {
    model.busy = kind; model.error = ""; model.info = ""; draw();
    try { await fn(); } catch (error) { model.error = error.message || T("No se pudo completar la acción."); }
    finally { model.busy = ""; draw(); }
  }

  // ------------------------------------------------------------ vistas
  function head() {
    const c = (ctx && ctx.company) || {};
    const logoUrl = model.ctx ? model.ctx.logo_url : "";
    const logo = logoUrl ? `<img class="sh-logo" src="${h(logoUrl)}" alt="">` : `<span class="sh-logo sh-logo-txt">${h(String(c.name || "?").slice(0, 1))}</span>`;
    return `<header class="client-hero sh-head"><button type="button" class="sh-btn sh-back" data-sh-back>← ${h(T("Módulos"))}</button>
      <div class="sh-brand">${logo}<div><p class="client-eyebrow">${h(c.name || "")}</p><h1 class="client-title">${h(T("Turnos"))}</h1></div></div></header>`;
  }

  function tabs() {
    const open = model.changes.filter((c) => c.status === "pending" || c.status === "waiting").length;
    const items = [["grid", T("Malla")], ["changes", `${T("Cambios")} (${open})`], ["config", T("Configuración")]];
    return `<nav class="sh-tabs" role="tablist" aria-label="${h(T("Turnos"))}">${items.map(([k, l]) => `<button type="button" role="tab" aria-selected="${model.tab === k}" class="${model.tab === k ? "client-btn is-on" : ""}" data-sh-tab="${k}">${h(l)}</button>`).join("")}</nav>`;
  }

  function weekTotals(rows) {
    const out = {};
    for (const a of rows) { const t = tpl(a.template_id); if (t) out[a.employee_id] = (out[a.employee_id] || 0) + num(t.minutes); }
    return out;
  }

  function grid() {
    const d = model.data;
    if (!d) return `<section class="client-panel"><p class="sh-muted">${h(model.loading ? T("Cargando…") : T("Sin datos."))}</p></section>`;
    const rows = arr(d.assignments);
    const byKey = {};
    rows.forEach((a) => { byKey[`${a.employee_id}|${a.work_date}`] = a; });
    const totals = weekTotals(rows);
    const published = d.status === "published";
    const label = `${fmt(d.days[0], { day: "numeric", month: "short" })} – ${fmt(d.days[6], { day: "numeric", month: "short" })}`;
    const chip = published ? T("Publicada") : d.status === "draft" ? T("Borrador") : T("Sin armar");
    const people = arr(model.ctx && model.ctx.employees);
    const supervisorCanChange = published && can("create_change");
    const bar = `<section class="client-panel sh-bar">
      <div class="sh-week"><button type="button" class="sh-btn is-icon" data-sh-week="-1" aria-label="${h(T("Semana anterior"))}">◀</button>
        <b class="sh-week-label">${h(label)}</b><button type="button" class="sh-btn is-icon" data-sh-week="1" aria-label="${h(T("Semana siguiente"))}">▶</button>
        <i class="sh-chip is-${h(d.status)}">${h(chip)}</i></div>
      <div class="sh-actions">
        <button type="button" class="sh-btn" data-sh-build ${published || model.busy ? "disabled" : ""} title="${published ? h(T("La semana publicada no se rearma")) : ""}">⚡ ${h(T("Armar malla"))}</button>
        <button type="button" class="client-btn sh-btn is-primary" data-sh-publish ${d.status !== "draft" || model.busy ? "disabled" : ""}>${h(T("Publicar al bot"))}</button>
        ${can("create_change") ? `<button type="button" class="sh-btn" data-sh-change ${!published || model.busy ? "disabled" : ""}>⇄ ${h(T("Cambio de turno"))}</button>` : ""}
      </div></section>`;
    const headRow = `<div class="sh-row is-head" role="row"><span class="sh-who" role="columnheader">${h(T("Persona"))}</span>${d.days.map((day) => `<span role="columnheader">${h(dayShort(day))}</span>`).join("")}<span class="sh-total" role="columnheader">${h(T("Total"))}</span></div>`;
    const body = people.map((e) => `<div class="sh-row" role="row"><span class="sh-who" role="rowheader"><b>${h(e.name)}</b><small>${h(e.role_label || e.role)}${e.telegram ? "" : ` · ${h(T("sin bot"))}`}</small></span>
      ${d.days.map((day) => {
        const a = byKey[`${e.id}|${day}`];
        const t = a ? tpl(a.template_id) : null;
        const label = t ? `${t.name} ${t.start}–${t.end}` : T("Libre");
        const inner = t ? `<b>${h(t.code)}</b>` : `<span>${h(T("Libre"))}</span>`;
        const style = t ? ` style="--sh-c:${h(t.color)}"` : "";
        return supervisorCanChange && a
          ? `<button type="button" class="sh-cell is-on" role="cell"${style} data-sh-cell="${h(a.id)}" aria-label="${h(`${dayLong(day)}: ${label}. ${T("Cambio de turno")}`)}">${inner}</button>`
          : `<span class="sh-cell${t ? " is-on" : ""}" role="cell"${style} aria-label="${h(`${dayLong(day)}: ${label}`)}">${inner}</span>`;
      }).join("")}<span class="sh-total" role="cell"><b>${h(hm(totals[e.id] || 0))}</b></span></div>`).join("");
    const legend = `<p class="sh-legend">${arr(model.ctx.templates).filter((t) => t.active).map((t) => `<span><i style="--sh-c:${h(t.color)}"></i>${h(`${t.code} · ${t.name} ${t.start}–${t.end}`)}</span>`).join("")}</p>`;
    return `${bar}<section class="client-panel"><div class="sh-grid" role="table" aria-label="${h(T("Malla"))}">${headRow}${body || `<p class="sh-muted">${h(T("Sin colaboradores activos."))}</p>`}</div>${legend}</section>${summary(d.analysis || {})}`;
  }

  function summary(an) {
    const gaps = arr(an.gaps), rest = arr(an.rest);
    const okLine = (ok, good, list) => ok ? `<li class="is-ok">✓ ${h(good)}</li>` : list;
    const fair = arr(an.fairness).filter((f) => f.minutes || f.nights || f.weekends);
    return `<section class="client-panel sh-summary"><h2 class="client-eyebrow sh-h">${h(T("Revisión de la semana"))}</h2><ul class="sh-checks">
      ${okLine(!gaps.length, T("Cobertura completa"), gaps.map((g) => `<li class="is-bad">⚠ ${h(gapText(g))}</li>`).join(""))}
      ${okLine(!rest.length, T("Descansos cumplidos"), rest.map((r) => `<li class="is-bad">⚠ ${h(`${r.name}: ${reasonText(r.reasons)}`)}</li>`).join(""))}
      </ul>${fair.length ? `<h3 class="sh-h3">${h(T("Reparto de noches y fines de semana"))}</h3><div class="sh-fair" role="table">
      <div class="sh-frow is-head" role="row"><span>${h(T("Persona"))}</span><span>${h(T("Noches"))}</span><span>${h(T("Fines de semana"))}</span><span>${h(T("Horas"))}</span></div>
      ${fair.map((f) => `<div class="sh-frow" role="row"><span>${h(f.name)}</span><span>${h(f.nights)}</span><span>${h(f.weekends)}</span><span>${h(hm(f.minutes))}</span></div>`).join("")}</div>` : ""}</section>`;
  }

  function changesView() {
    const list = model.changes;
    if (!list.length) return `<section class="client-panel"><p class="sh-muted">${h(T("Aún no hay cambios de turno."))}</p></section>`;
    return `<section class="sh-changes">${list.map((c) => {
      const t = tpl(c.template_id);
      const owner = emp(c.requester_employee_id);
      const cur = c.current_index !== null && c.current_index !== undefined ? arr(c.candidates)[c.current_index] : null;
      const status = c.uncovered ? T("Sin cubrir") : T(STATUS[c.status] || c.status);
      const steps = arr(c.log).map((ev) => {
        const who = ev.name || "";
        const txt = ev.kind === "created" ? T("Creada por {by} · {n} candidatos", { by: ev.by || "—", n: num(ev.candidates) })
          : ev.kind === "offered" ? (ev.bot ? T("Esperando a {who}", { who }) : T("Esperando a {who} (sin bot: registrar a mano)", { who }))
          : ev.kind === "accepted" ? T("{who} aceptó", { who }) + (ev.via === "manual" ? ` · ${T("registrado a mano por {by}", { by: ev.by || "—" })}` : "")
          : ev.kind === "rejected" ? T("{who} no puede", { who }) + (ev.via === "manual" ? ` · ${T("registrado a mano por {by}", { by: ev.by || "—" })}` : "")
          : ev.kind === "expired" ? T("{who} no respondió a tiempo", { who })
          : ev.kind === "invalid" ? T("{who} ya no cumple las reglas", { who })
          : ev.kind === "uncovered" ? T("Lista agotada: turno sin cubrir")
          : ev.kind === "cancelled" ? T("Cancelado por {by}", { by: ev.by || "—" }) : ev.kind;
        return `<li><time>${h(stamp(ev.at))}</time><span>${h(txt)}</span></li>`;
      }).join("");
      const sup = can("create_change");
      const actions = !sup ? "" : c.status === "pending"
        ? `<button type="button" class="client-btn sh-btn is-primary" data-sh-send="${h(c.id)}" ${model.busy ? "disabled" : ""}>${h(T("Enviar por bot"))}</button><button type="button" class="sh-btn" data-sh-cancel="${h(c.id)}">${h(T("Cancelar"))}</button>`
        : c.status === "waiting" && cur
          ? `<span class="sh-manual">${h(T("Registrar respuesta de {who}:", { who: cur.name }))}</span><button type="button" class="sh-btn" data-sh-reply="${h(c.id)}" data-sh-accept="1">✅ ${h(T("Acepta"))}</button><button type="button" class="sh-btn" data-sh-reply="${h(c.id)}" data-sh-accept="0">❌ ${h(T("No puede"))}</button><button type="button" class="sh-btn" data-sh-cancel="${h(c.id)}">${h(T("Cancelar"))}</button>`
          : "";
      return `<article class="client-panel sh-change${c.uncovered ? " is-alert" : ""}"><header class="sh-change-head"><div><b>${h(t ? `${t.name} ${t.start}–${t.end}` : "—")}</b>
        <small>${h(dayLong(c.work_date))} · ${h(T("cambio de {who}", { who: owner ? owner.name : "—" }))}</small></div><i class="sh-chip is-${h(c.uncovered ? "alert" : c.status)}">${h(status)}</i></header>
        ${cur && c.status === "waiting" ? `<p class="sh-wait">${h(T("Esperando a {who} hasta {at}", { who: cur.name, at: stamp(c.deadline_at) }))}</p>` : ""}
        <ol class="sh-steps">${steps}</ol>${actions ? `<div class="sh-actions">${actions}</div>` : ""}</article>`;
    }).join("")}</section>`;
  }

  function sel(name, value, opts, labelFn = (v) => v) {
    return `<select data-sh-rule="${name}">${opts.map((o) => `<option value="${h(o)}" ${String(o) === String(value) ? "selected" : ""}>${h(labelFn(o))}</option>`).join("")}</select>`;
  }

  function configView() {
    if (!model.ctx) return "";
    const d = model.draft || (model.draft = JSON.parse(JSON.stringify({ templates: model.ctx.templates, rules: model.ctx.rules, coverage: model.ctx.coverage })));
    const r = d.rules;
    const capDefault = num(r.default_weekly_hours_cap);
    const capOpts = ["", ...CAP_OPTS.filter((x) => x !== capDefault)];
    const rules = `<div class="sh-rules">
      <label class="sh-field">${h(T("Horas mínimas entre turnos"))}${sel("min_rest_hours", r.min_rest_hours, REST_OPTS, (v) => `${v} h`)}</label>
      <label class="sh-field">${h(T("Días libres por semana"))}${sel("days_off_per_week", r.days_off_per_week, OFF_OPTS)}</label>
      <label class="sh-field">${h(T("Máximo de días seguidos"))}${sel("max_consecutive_days", r.max_consecutive_days, DAYS_OPTS)}</label>
      <label class="sh-field">${h(T("Tope de horas por semana"))}${sel("weekly_hours_cap", r.weekly_hours_cap === null || r.weekly_hours_cap === undefined ? "" : r.weekly_hours_cap, capOpts, (v) => (v === "" ? T("{n} h (el de Personal)", { n: capDefault }) : `${v} h`))}</label>
      <label class="sh-field">${h(T("Máximo de noches seguidas"))}${sel("max_consecutive_nights", r.max_consecutive_nights, NIGHT_OPTS)}</label>
      <label class="sh-field">${h(T("Tiempo para responder un cambio"))}${sel("response_hours", r.response_hours, RESP_OPTS, (v) => (num(v) < 1 ? `${num(v) * 60} min` : `${v} h`))}</label></div>`;
    const tpls = `<div class="sh-tpls">${d.templates.map((t, i) => `<div class="sh-tpl" style="--sh-c:${h(t.color)}">
      <label class="sh-field is-name">${h(T("Nombre"))}<input data-sh-tpl="${i}" data-k="name" value="${h(t.name)}" maxlength="60"></label>
      <label class="sh-field is-code">${h(T("Código"))}<input data-sh-tpl="${i}" data-k="code" value="${h(t.code)}" maxlength="4"></label>
      <label class="sh-field">${h(T("Inicio"))}<input type="time" data-sh-tpl="${i}" data-k="start" value="${h(t.start)}"></label>
      <label class="sh-field">${h(T("Fin"))}<input type="time" data-sh-tpl="${i}" data-k="end" value="${h(t.end)}"></label>
      <label class="sh-field is-color">${h(T("Color"))}<input type="color" data-sh-tpl="${i}" data-k="color" value="${h(t.color)}"></label>
      <label class="sh-check"><input type="checkbox" data-sh-tpl="${i}" data-k="active" ${t.active !== false ? "checked" : ""}>${h(T("Activo"))}</label>
      <small class="sh-tpl-note">${h(String(t.end) <= String(t.start) ? T("Nocturno: cruza la medianoche y cuenta para el día en que empieza") : "")}</small></div>`).join("")}
      <button type="button" class="sh-btn" data-sh-add-tpl>+ ${h(T("Turno"))}</button></div>`;
    const active = d.templates.map((t, i) => ({ ...t, i })).filter((t) => t.active !== false);
    const roles = arr(model.ctx.roles);
    const minOf = (t, role) => { const c = d.coverage.find((x) => (x.template_id ? x.template_id === t.id : x.template_code === t.code) && x.role === role); return c ? num(c.min) : 0; };
    const cov = !roles.length ? `<p class="sh-muted">${h(T("Sin colaboradores activos."))}</p>` : `<div class="sh-cov" role="table" style="--sh-cols:${active.length}">
      <div class="sh-cov-row is-head" role="row"><span>${h(T("Rol"))}</span>${active.map((t) => `<span>${h(t.code)} · ${h(t.name)}</span>`).join("")}</div>
      ${roles.map((role) => `<div class="sh-cov-row" role="row"><span>${h(role.label)}</span>${active.map((t) => `<label><span class="sh-sr">${h(`${role.label} · ${t.name}`)}</span><select data-sh-cov="${h(role.code)}" data-t="${h(t.id || "")}" data-code="${h(t.code)}">${[0, 1, 2, 3, 4, 5, 6, 8, 10].map((n) => `<option value="${n}" ${minOf(t, role.code) === n ? "selected" : ""}>${n}</option>`).join("")}</select></label>`).join("")}</div>`).join("")}</div>`;
    return `<section class="client-panel"><h2 class="client-eyebrow sh-h">${h(T("Turnos de la empresa"))}</h2>${tpls}</section>
      <section class="client-panel"><h2 class="client-eyebrow sh-h">${h(T("Reglas de descanso"))}</h2>${rules}</section>
      <section class="client-panel"><h2 class="client-eyebrow sh-h">${h(T("Cobertura mínima por rol y turno"))}</h2>${cov}</section>
      <div class="sh-save"><button type="button" class="client-btn sh-btn is-primary" data-sh-save ${model.busy ? "disabled" : ""}>${h(T("Guardar configuración"))}</button></div>`;
  }

  function changeModal() {
    const m = model.modal;
    if (!m) return "";
    const rows = arr(model.data && model.data.assignments);
    const people = arr(model.ctx.employees).filter((e) => rows.some((a) => a.employee_id === e.id));
    const mine = rows.filter((a) => a.employee_id === m.employee_id);
    const p = m.proposal;
    const cands = p ? arr(p.candidates) : [];
    const list = !p ? "" : `${!p.enough ? `<p class="sh-notice" role="alert">${h(cands.length ? T("Solo hay 1 candidato válido: no alcanza para proponer el cambio con opciones.") : T("No hay candidatos válidos que cumplan todas las reglas."))}</p>` : ""}
      ${cands.length ? `<ol class="sh-cands">${cands.map((c) => `<li><div class="sh-cand-head"><b>${h(c.name)}</b><i class="sh-chip is-${h(c.kind)}">${h(c.kind === "swap" ? T("Intercambio directo") : T("Cubre"))}</i>${c.telegram ? "" : `<i class="sh-chip is-nobot">${h(T("sin bot"))}</i>`}</div>
        <small>${c.kind === "swap" && tpl(c.swap_template_id) ? h(T("Le pasa su turno {shift}", { shift: tpl(c.swap_template_id).name })) + " · " : ""}${h(T("{h} en la semana · {a} días con asistencia · {p} entradas a tiempo · {c} cambios recientes", { h: hm(c.week_minutes), a: c.attendance, p: c.punctuality, c: c.changes }))}</small></li>`).join("")}</ol>` : ""}
      ${arr(p.discarded).length ? `<details class="sh-disc"><summary>${h(T("Descartados ({n})", { n: arr(p.discarded).length }))}</summary><ul>${arr(p.discarded).map((x) => `<li>${h(x.name)}: ${h(reasonText(x.reasons))}</li>`).join("")}</ul></details>` : ""}`;
    return `<div class="sh-overlay" data-sh-overlay><div class="client-panel sh-modal" role="dialog" aria-modal="true" aria-labelledby="shModalTitle">
      <header class="sh-modal-head"><h2 id="shModalTitle">⇄ ${h(T("Cambio de turno"))}</h2><button type="button" class="sh-btn is-small" data-sh-close aria-label="${h(T("Cerrar"))}">✕</button></header>
      <div class="sh-pick"><label class="sh-field">${h(T("Persona"))}<select data-sh-pick-emp><option value="">—</option>${people.map((e) => `<option value="${h(e.id)}" ${m.employee_id === e.id ? "selected" : ""}>${h(e.name)}</option>`).join("")}</select></label>
      <label class="sh-field">${h(T("Turno"))}<select data-sh-pick-shift><option value="">—</option>${mine.map((a) => { const t = tpl(a.template_id); return `<option value="${h(a.id)}" ${m.assignment_id === a.id ? "selected" : ""}>${h(`${dayLong(a.work_date)} · ${t ? `${t.name} ${t.start}–${t.end}` : ""}`)}</option>`; }).join("")}</select></label></div>
      ${m.loading ? `<p class="sh-muted" role="status">${h(T("Buscando candidatos…"))}</p>` : list}
      <div class="sh-actions"><button type="button" class="client-btn sh-btn is-primary" data-sh-create ${!p || !p.enough || model.busy ? "disabled" : ""}>${h(T("Enviar por bot"))}</button></div></div></div>`;
  }

  function view() {
    if (model.denied) return `<div class="sh-root" data-sh-root>${head()}<section class="client-panel sh-denied"><p>${h(model.denied)}</p></section></div>`;
    const body = model.tab === "config" ? configView() : model.tab === "changes" ? changesView() : grid();
    return `<div class="sh-root" data-sh-root>${head()}${tabs()}
      ${model.error ? `<div class="sh-notice" role="alert">${h(model.error)}</div>` : ""}${model.info ? `<div class="sh-notice is-ok" role="status">${h(model.info)}</div>` : ""}
      ${body}${model.ctx ? changeModal() : ""}</div>`;
  }

  function draw() { if (!ctx) return; const host = ctx.host(); if (host) host.innerHTML = view(); }

  // ------------------------------------------------------------ acciones
  async function propose() {
    const m = model.modal;
    if (!m || !m.assignment_id) return;
    m.loading = true; m.proposal = null; draw();
    try { m.proposal = await call("/changes/proposal", "POST", { assignment_id: m.assignment_id }); }
    catch (error) { model.error = error.message; }
    finally { m.loading = false; draw(); }
  }

  function onClick(event) {
    const t = event.target;
    if (!ctx || !t || !t.closest || !t.closest("[data-sh-root]")) return;
    const attr = (a) => { const el = t.closest(`[${a}]`); return el ? el.getAttribute(a) : null; };
    let v;
    if (t.closest("[data-sh-back]")) { ctx.back(); return; }
    if ((v = attr("data-sh-tab"))) { model.tab = v; model.error = ""; model.info = ""; draw(); return; }
    if ((v = attr("data-sh-week"))) { model.week = addDays(model.week, 7 * Number(v)); loadWeek(); return; }
    if (t.closest("[data-sh-build]")) { act("build", async () => { model.data = await call(`/week/build?start=${model.week}`, "POST"); model.info = T("Borrador armado."); }); return; }
    if (t.closest("[data-sh-publish]")) {
      act("publish", async () => {
        const res = await call(`/week/publish?start=${model.week}`, "POST");
        model.data = res;
        const s = res.sent || {};
        model.info = T("Semana publicada: {n} personas la recibieron por bot.", { n: num(s.sent) }) + (arr(s.without_bot).length ? ` ${T("Sin bot: {names}", { names: arr(s.without_bot).join(", ") })}` : "");
      });
      return;
    }
    if (t.closest("[data-sh-change]")) { model.modal = { employee_id: "", assignment_id: "", proposal: null }; draw(); return; }
    if ((v = attr("data-sh-cell"))) {
      const a = arr(model.data && model.data.assignments).find((x) => x.id === v);
      if (a) { model.modal = { employee_id: a.employee_id, assignment_id: a.id, proposal: null }; propose(); }
      return;
    }
    if (t.closest("[data-sh-close]") || (t.matches && t.matches("[data-sh-overlay]"))) { model.modal = null; draw(); return; }
    if (t.closest("[data-sh-create]")) {
      const id = model.modal && model.modal.assignment_id;
      act("create", async () => {
        await call("/changes", "POST", { assignment_id: id, send: true });
        model.modal = null; model.tab = "changes";
        model.changes = arr((await call("/changes")).items);
        model.info = T("Cambio enviado por bot al primer candidato.");
      });
      return;
    }
    if ((v = attr("data-sh-send"))) { act("send", async () => { await call(`/changes/${v}/send`, "POST"); model.changes = arr((await call("/changes")).items); }); return; }
    if ((v = attr("data-sh-cancel"))) { act("cancel", async () => { await call(`/changes/${v}/cancel`, "POST"); model.changes = arr((await call("/changes")).items); }); return; }
    if ((v = attr("data-sh-reply"))) {
      const accept = attr("data-sh-accept") === "1";
      act("reply", async () => { await call(`/changes/${v}/reply`, "POST", { accept }); model.changes = arr((await call("/changes")).items); await loadWeek(); });
      return;
    }
    if (t.closest("[data-sh-add-tpl]")) { model.draft.templates.push({ id: null, name: "", code: "", start: "08:00", end: "16:00", color: "#0ea5e9", active: true }); draw(); return; }
    if (t.closest("[data-sh-save]")) {
      const d = model.draft;
      act("save", async () => {
        const body = { templates: d.templates, rules: d.rules, coverage: d.coverage.map((c) => ({ template_id: c.template_id || null, template_code: c.template_code || null, role: c.role, min: c.min })) };
        model.ctx = await call("/config", "PUT", body);
        model.draft = null;
        model.info = T("Configuración guardada.");
        await loadWeek();
      });
    }
  }

  function onChange(event) {
    const t = event.target;
    if (!ctx || !t || !t.closest || !t.closest("[data-sh-root]")) return;
    let v;
    if (t.hasAttribute("data-sh-pick-emp")) { model.modal = { employee_id: t.value, assignment_id: "", proposal: null }; draw(); return; }
    if (t.hasAttribute("data-sh-pick-shift")) { model.modal.assignment_id = t.value; propose(); return; }
    if ((v = t.getAttribute("data-sh-rule"))) {
      const raw = t.value;
      model.draft.rules[v] = raw === "" ? null : Number(raw);
      return;
    }
    if ((v = t.getAttribute("data-sh-tpl")) !== null) {
      const k = t.getAttribute("data-k");
      model.draft.templates[Number(v)][k] = k === "active" ? t.checked : t.value;
      if (k === "start" || k === "end" || k === "active" || k === "color") draw();
      return;
    }
    if ((v = t.getAttribute("data-sh-cov"))) {
      const tid = t.getAttribute("data-t") || null;
      const code = t.getAttribute("data-code");
      const list = model.draft.coverage.filter((c) => !((tid ? c.template_id === tid : c.template_code === code) && c.role === v));
      list.push({ template_id: tid, template_code: tid ? null : code, role: v, min: Number(t.value) });
      model.draft.coverage = list;
    }
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
    model.week = monday(today());
    model.modal = null; model.tab = "grid"; model.draft = null; model.ctx = null; model.denied = "";
    draw();
    await loadAll();
  }

  window.CxShiftsV1 = { mount, model, view, hm, gapText, monday, addDays };
})();
