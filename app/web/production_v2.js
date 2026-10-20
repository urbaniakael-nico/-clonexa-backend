// Producción v2 (interruptor production_v2 del módulo production; hoy solo Velvet).
// Tablero por LOTE: seis cifras del equipo, lotes en proceso (con su detalle por
// talla), en vivo, cerradas vs enviadas a Bombón por semana o mes, tiempo del
// equipo por referencia (participación, no productividad) y alertas, con PDF.
// Los datos salen de /production-v2/.../insights (el mismo cálculo del PDF).
// Cuando no hay datos suficientes una cifra dice "Sin datos aún" y por qué.
// Nunca cifras por persona. Textos por t(), dinero, fechas y zona por CxLocale.
(() => {
  "use strict";

  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const num = (v) => Number(v || 0) || 0;
  const fill = (s, vars) => (vars ? String(s).replace(/\{(\w+)\}/g, (m, k) => (vars[k] !== undefined ? String(vars[k]) : m)) : String(s));
  const T = (s, vars) => (typeof window !== "undefined" && window.CxI18n && typeof window.CxI18n.t === "function" ? window.CxI18n.t(s, vars) : fill(s, vars));
  const L = () => (typeof window !== "undefined" ? window.CxLocale : null);

  const PRESETS = [["week", "Semana"], ["month", "Mes"], ["quarter", "Trimestre"], ["custom", "Personalizado"]];
  const STATUS = { working: "Trabajando", on_break: "En pausa" };

  const model = { preset: "week", from: "", to: "", data: null, loading: false, error: "", denied: false, open: "", busy: "" };
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
  function day(value) {
    if (!value) return "—";
    const loc = L();
    if (loc && typeof loc.dateTime === "function") return loc.dateTime(`${String(value).slice(0, 10)}T12:00:00Z`, { day: "2-digit", month: "short" }, lang()) || "—";
    return String(value).slice(0, 10);
  }
  function today() {
    const loc = L();
    return (loc && typeof loc.filterDay === "function" && loc.filterDay(new Date())) || new Date().toISOString().slice(0, 10);
  }

  function query(extra = {}) {
    const p = new URLSearchParams({ preset: model.preset, ...extra });
    if (model.preset === "custom") { p.set("date_from", model.from || today()); p.set("date_to", model.to || today()); }
    return p.toString();
  }

  // ------------------------------------------------------------ datos
  const base = () => `${ctx.apiBase}/production-v2/companies/${encodeURIComponent(ctx.companyId)}`;
  const headers = () => { const t = ctx.token(); return t ? { Authorization: `Bearer ${t}` } : {}; };

  async function load() {
    model.loading = true; model.error = ""; draw();
    try {
      const res = await fetch(`${base()}/insights?${query()}`, { headers: headers(), credentials: "same-origin" });
      if (res.status === 401) { model.error = T("No pudimos cargar Producción: sesión vencida, vuelve a entrar."); return; }
      if (res.status === 403) { model.denied = true; model.data = null; return; }
      if (!res.ok) throw new Error(`${res.status}`);
      model.denied = false;
      model.data = await res.json();
    } catch (_) {
      model.error = T("No pudimos cargar Producción. Revisa la conexión e intenta de nuevo.");
    } finally { model.loading = false; draw(); }
  }

  async function pdf(kind) {
    model.busy = kind; model.error = ""; draw();
    const tab = kind === "view" ? window.open("", "_blank") : null;
    try {
      const res = await fetch(`${base()}/export.pdf?${query({ disposition: kind === "view" ? "inline" : "attachment" })}`, { headers: headers(), credentials: "same-origin" });
      if (!res.ok) throw new Error(T("No se pudo generar el PDF."));
      const url = URL.createObjectURL(await res.blob());
      if (kind === "view") { if (tab) tab.location.href = url; else window.open(url, "_blank"); }
      else {
        const a = document.createElement("a");
        const p = (model.data && model.data.period) || {};
        a.href = url; a.download = `produccion_${p.from || ""}_${p.to || ""}.pdf`;
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
    const c = (model.data && model.data.company) || {};
    const logo = c.logo_url ? `<img class="pp-logo" src="${h(c.logo_url)}" alt="">` : `<span class="pp-logo pp-logo-txt">${h(String(c.name || "?").slice(0, 1))}</span>`;
    return `<header class="client-hero pp-head"><div class="pp-brand">${logo}<div><p class="client-eyebrow">${h(c.name || "")}</p><h1 class="client-title">${h(T("Producción"))}</h1>
      <p class="pp-sub">${h(T("El taller por lote: cifras del equipo, nunca por persona."))}</p></div></div></header>`;
  }

  function bar() {
    return `<section class="client-panel pp-toolbar">
      <div class="pp-seg" role="group" aria-label="${h(T("Periodo"))}">${PRESETS.map(([k, l]) => `<button type="button" class="${model.preset === k ? "client-btn is-on" : ""}" data-pp-preset="${k}" aria-pressed="${model.preset === k}">${h(T(l))}</button>`).join("")}</div>
      ${model.preset === "custom" ? `<div class="pp-dates"><label class="pp-field">${h(T("Desde"))}<input type="date" data-pp-from value="${h(model.from || today())}"></label><label class="pp-field">${h(T("Hasta"))}<input type="date" data-pp-to value="${h(model.to || today())}"></label></div>` : ""}
      <div class="pp-actions"><button type="button" class="pp-btn" data-pp-pdf="view" ${model.busy ? "disabled" : ""}>${h(T("Ver PDF"))}</button>
        <button type="button" class="client-btn pp-btn is-primary" data-pp-pdf="download" ${model.busy ? "disabled" : ""}>${h(T("Descargar PDF"))}</button></div></section>`;
  }

  // Una cifra: valor o "Sin datos aún" con el motivo.
  function tile(label, item, value, sub) {
    const ok = item && item.status === "ok";
    return `<div class="pp-kpi ${ok ? "" : "is-empty"}"><small>${h(T(label))}</small><b>${h(ok ? value : T("Sin datos aún"))}</b><span>${h(ok ? sub : T((item && item.reason) || ""))}</span></div>`;
  }

  function kpis(k) {
    const w = k.workshop_now || {};
    return `<div class="pp-kpis">
      ${tile("En el taller ahora", w, String(num(w.value)), T("{w} trabajando · {p} en pausa · {l} lotes", { w: num(w.working), p: num(w.paused), l: num(w.lots) }))}
      ${tile("Prendas cerradas", k.closed, String(num((k.closed || {}).value)), T("{n} lotes", { n: num((k.closed || {}).lots) }))}
      ${tile("Enviadas a Bombón", k.sent, String(num((k.sent || {}).value)), T("{n} cerradas por enviar", { n: num((k.sent || {}).to_send) }))}
      ${tile("Días por lote", k.days_per_lot, String((k.days_per_lot || {}).value ?? ""), T("{n} lotes completos", { n: num((k.days_per_lot || {}).lots) }))}
      ${tile("Horas-equipo por prenda", k.team_hours_per_garment, hm((k.team_hours_per_garment || {}).value), T("tiempo del equipo ÷ prendas cerradas"))}
      ${tile("Mano de obra por prenda", k.labor_per_garment, money((k.labor_per_garment || {}).value), T("Nómina del equipo: {m}", { m: money((k.labor_per_garment || {}).labor) }))}
    </div>`;
  }

  const SECTION = { corte: "Corte", bordado: "Bordado", taller: "Taller", lavado: "Lavado", otro: "Otro" };

  function lotBody(lot) {
    const sizes = `<div class="pp-table" role="table"><div class="pp-row pp-row-5 is-head" role="row"><span>${h(T("Talla"))}</span><span>${h(T("Meta"))}</span><span>${h(T("Recibido"))}</span><span>${h(T("Cerradas"))}</span><span>${h(T("Pendiente"))}</span></div>
      ${arr(lot.sizes).map((s) => `<div class="pp-row pp-row-5" role="row"><span>${h(s.size || "—")}</span><span>${h(num(s.meta))}</span><span>${h(num(s.received))}</span><span>${h(num(s.closed))}</span><span>${h(num(s.pending))}</span></div>`).join("")}</div>`;
    const cuts = arr(lot.cuts).length
      ? `<ul class="pp-mini">${arr(lot.cuts).map((c) => `<li><span>${h(day(c.date))}</span><span>${h(arr(c.sizes).map((z) => `${z.size || "—"} ${z.quantity}`).join(" · "))}</span><b>${h(num(c.quantity))}</b></li>`).join("")}</ul>`
      : `<p class="pp-muted">${h(T("Sin cortes registrados."))}</p>`;
    const news = arr(lot.news).length
      ? `<ul class="pp-mini">${arr(lot.news).map((n) => `<li><span>${h(T(SECTION[n.section] || n.section))}</span><span></span><b>${h(num(n.quantity))}</b></li>`).join("")}</ul>`
      : `<p class="pp-muted">${h(T("Sin novedades."))}</p>`;
    const people = arr(lot.people).length
      ? `<ul class="pp-mini">${arr(lot.people).map((p) => `<li><span>${h(p.name)}</span><span></span><b>${h(hm(num(p.seconds) / 60))}</b></li>`).join("")}</ul>`
      : `<p class="pp-muted">${h(T("Sin tiempo del equipo en el periodo."))}</p>`;
    return `<div class="pp-lot-body"><p class="pp-muted">${h(T("Inicio {d} · última actividad {l} · tiempo del equipo en el periodo {t}", { d: day(lot.started), l: day(lot.last_activity), t: hm(num(lot.team_seconds) / 60) }))}</p>
      <h3 class="pp-h3">${h(T("Tallas"))}</h3>${sizes}
      <div class="pp-detail-grid"><div><h3 class="pp-h3">${h(T("Cortes por fecha"))}</h3>${cuts}</div>
        <div><h3 class="pp-h3">${h(T("Novedades por sección"))}</h3>${news}</div>
        <div><h3 class="pp-h3">${h(T("Horas del equipo en el lote"))}</h3>${people}</div></div></div>`;
  }

  function lots(list) {
    if (!arr(list).length) return `<p class="pp-muted">${h(T("Sin lotes en proceso."))}</p>`;
    return `<ul class="pp-lots">${arr(list).map((lot) => {
      const pct = lot.meta ? Math.min(100, Math.round((num(lot.closed) * 100) / num(lot.meta))) : 0;
      const open = model.open === lot.key;
      const team = arr(lot.team).length ? `<small class="pp-team">${h(T("Equipo"))}: ${h(arr(lot.team).join(", "))}</small>` : "";
      return `<li class="pp-lot ${lot.late ? "is-late" : ""}"><button type="button" class="pp-lot-head" data-pp-lot="${h(lot.key)}" aria-expanded="${open}">
        <span class="pp-lot-name"><b>${h(lot.name)}</b>${lot.working_now ? `<i class="pp-live-dot" aria-hidden="true"></i><small>${h(T("{n} trabajando ahora", { n: lot.working_now }))}</small>` : ""}${lot.late ? `<small class="pp-late">${h(T("Más días que el promedio"))}</small>` : ""}</span>
        <span class="pp-meter" role="img" aria-label="${h(T("{c} de {m} cerradas", { c: num(lot.closed), m: num(lot.meta) }))}"><i style="--w:${pct}%"></i></span>
        <span class="pp-lot-nums"><span><b>${h(num(lot.closed))} / ${h(num(lot.meta))}</b></span><span>${h(T("Pendiente"))} <b>${h(lot.pending)}</b></span>
          <span>${h(T("Enviadas"))} <b>${h(lot.sent)}</b></span><span>${h(T("Días"))} <b>${h(lot.days_open ?? "—")}</b></span></span>${team}</button>
        ${open ? lotBody(lot) : ""}</li>`;
    }).join("")}</ul>`;
  }

  function live(list) {
    if (!arr(list).length) return `<p class="pp-muted">${h(T("Nadie trabajando ahora."))}</p>`;
    return `<ul class="pp-live">${arr(list).map((p) => `<li class="is-${h(p.status)}"><i aria-hidden="true"></i><b>${h(p.name)}</b><span>${h(p.reference || T("Sin referencia"))}</span>
      <small>${h(T(STATUS[p.status] || p.status))} · ${h(hm(p.elapsed_minutes))}</small></li>`).join("")}</ul>`;
  }

  function series(data) {
    const list = arr(data.series);
    if (!list.some((s) => num(s.closed) || num(s.sent))) return `<p class="pp-muted">${h(T("Sin cierres ni envíos en el periodo."))}</p>`;
    const max = Math.max(1, ...list.map((s) => Math.max(num(s.closed), num(s.sent))));
    const unit = (data.period || {}).by === "month" ? "Mes" : "Semana";
    return `<div class="pp-legend"><i class="is-closed"></i>${h(T("Cerradas"))}<i class="is-sent"></i>${h(T("Enviadas"))}</div>
      <ul class="pp-bars">${list.map((s) => `<li><span class="pp-bday">${h(T(unit))} ${h(day(s.bucket))}</span>
        <span class="pp-pair"><span class="pp-bar" role="img" aria-label="${h(T("{n} cerradas", { n: num(s.closed) }))}"><i class="is-closed" style="--w:${(num(s.closed) / max) * 100}%"></i></span>
        <span class="pp-bar" role="img" aria-label="${h(T("{n} enviadas", { n: num(s.sent) }))}"><i class="is-sent" style="--w:${(num(s.sent) / max) * 100}%"></i></span></span>
        <b>${h(num(s.closed))} / ${h(num(s.sent))}</b></li>`).join("")}</ul>`;
  }

  // Barra apilada por referencia: horas efectivas de cada persona (participación, no productividad).
  function share(tt) {
    const list = arr(tt && tt.by_reference);
    if (!list.length) return `<p class="pp-muted">${h(T("Sin tiempo del equipo en el periodo."))}</p>`;
    const names = [];
    list.forEach((r) => arr(r.people).forEach((p) => { if (!names.includes(p.name)) names.push(p.name); }));
    const tone = (name) => names.indexOf(name) % 6;
    const max = Math.max(1, ...list.map((r) => num(r.seconds)));
    return `<p class="pp-note">${h(T("Participación, no productividad: horas efectivas de cada persona en cada referencia."))}</p>
      <div class="pp-legend pp-legend-people">${names.map((n) => `<span><i class="pp-tone-${tone(n)}"></i>${h(n)}</span>`).join("")}</div>
      <ul class="pp-share">${list.map((r) => {
        const people = arr(r.people);
        const segs = people.map((p) => `<i class="pp-tone-${tone(p.name)}" style="--w:${(num(p.seconds) / max) * 100}%" title="${h(`${p.name} · ${hm(num(p.seconds) / 60)}`)}"></i>`).join("");
        const label = people.map((p) => `${p.name} ${hm(num(p.seconds) / 60)}`).join(", ");
        return `<li><span class="pp-share-name">${h(r.name)}</span><span class="pp-stack" role="img" aria-label="${h(label || r.name)}">${segs || `<i class="pp-tone-0" style="--w:${(num(r.seconds) / max) * 100}%"></i>`}</span>
          <b>${h(num(r.percent))}%</b><small>${h(hm(num(r.seconds) / 60))}</small></li>`;
      }).join("")}</ul>`;
  }

  function alertText(a) {
    const ref = a.reference || "";
    if (a.kind === "long_session") return T("{ref}: hay una sesión abierta hace más de 12 h (¿se olvidó cerrar?)", { ref });
    if (a.kind === "slow_lot") return T("{ref}: {d} días abierto (promedio {a}) y {p}% cerrado", { ref, d: a.days, a: a.avg, p: a.percent });
    if (a.kind === "open_news") return T("Novedades en {s}: {n} prendas ({ref})", { s: T(SECTION[a.section] || a.section), n: num(a.quantity), ref });
    if (a.kind === "no_recent_time") return a.days == null ? T("{ref}: referencia activa sin tiempo registrado", { ref }) : T("{ref}: referencia activa sin tiempo registrado hace {d} días", { ref, d: a.days });
    return T("{ref}: {n} prendas cerradas sin enviar a Bombón", { ref, n: num(a.quantity) });
  }

  function alerts(list) {
    if (!arr(list).length) return `<p class="pp-muted">${h(T("Sin alertas."))}</p>`;
    return `<ul class="pp-alerts">${arr(list).map((a) => `<li class="is-${h(a.level || "warning")}">${h(alertText(a))}</li>`).join("")}</ul>`;
  }

  function view() {
    if (model.denied) return `<div class="pp-root" data-pp-root>${head()}<section class="client-panel"><p class="pp-muted">${h(T("Producción es solo del dueño o administrador."))}</p></section></div>`;
    const d = model.data;
    const body = !d ? `<section class="client-panel"><p class="pp-muted">${h(model.loading ? T("Cargando…") : T("Sin datos."))}</p></section>` : `
      ${kpis(d.kpis || {})}
      <section class="client-panel"><h2 class="client-eyebrow pp-h">${h(T("Lotes en proceso"))}<b>${arr(d.lots_in_process).length}</b></h2>${lots(d.lots_in_process)}</section>
      <div class="pp-grid">
        <section class="client-panel"><h2 class="client-eyebrow pp-h">${h(T("En vivo"))}<b>${arr(d.live).length}</b></h2>${live(d.live)}</section>
        <section class="client-panel"><h2 class="client-eyebrow pp-h">${h(T("Alertas"))}<b>${arr(d.alerts).length}</b></h2>${alerts(d.alerts)}</section>
      </div>
      <div class="pp-grid">
        <section class="client-panel"><h2 class="client-eyebrow pp-h">${h(T("Cerradas vs enviadas a Bombón"))}</h2>${series(d)}</section>
        <section class="client-panel"><h2 class="client-eyebrow pp-h">${h(T("Tiempo del equipo por referencia"))}</h2>${share(d.team_time)}</section>
      </div>`;
    const notice = model.error ? `<div class="pp-notice" role="alert">${h(model.error)} <button type="button" class="pp-btn" data-pp-retry>${h(T("Reintentar"))}</button></div>` : "";
    return `<div class="pp-root" data-pp-root>${head()}${bar()}${notice}${body}</div>`;
  }

  function draw() { if (!ctx) return; const host = ctx.host(); if (host) host.innerHTML = view(); }

  // ------------------------------------------------------------ eventos
  function onClick(event) {
    const t = event.target;
    if (!ctx || !t || !t.closest || !t.closest("[data-pp-root]")) return;
    const attr = (a) => { const el = t.closest(`[${a}]`); return el ? el.getAttribute(a) : null; };
    let v;
    if (attr("data-pp-retry") !== null) { load(); return; }
    if ((v = attr("data-pp-preset"))) { model.preset = v; load(); return; }
    if ((v = attr("data-pp-pdf"))) { pdf(v); return; }
    if ((v = attr("data-pp-lot"))) { model.open = model.open === v ? "" : v; draw(); }
  }

  function onChange(event) {
    const t = event.target;
    if (!ctx || !t || !t.closest || !t.closest("[data-pp-root]")) return;
    if (t.hasAttribute("data-pp-from")) { model.from = t.value; load(); return; }
    if (t.hasAttribute("data-pp-to")) { model.to = t.value; load(); }
  }

  async function mount(context) {
    ctx = context;
    if (!bound && typeof document.addEventListener === "function") {
      document.addEventListener("click", onClick);
      document.addEventListener("change", onChange);
      bound = true;
    }
    model.open = "";
    draw();
    await load();
  }

  window.CxProductionV2 = { mount, model, view, hm, money, alertText, query, PRESETS };
})();
