// Juegos en vivo (interruptor loyalty_games del módulo loyalty).
// Panel dentro del portal: lo abre Fidelización o el Panel Barman.
// - En vivo (dueño/admin y barman): girar la ruleta, abrir registro de Memoria
//   o Trivia, iniciar, cerrar, quitar un nombre de la pantalla y validar al
//   ganador por documento (el servidor compara el HMAC; nunca se ve el número).
// - Configuración, Preguntas e Historial: solo dueño/admin (el servidor responde 403).
// Datos en /loyalty-games/companies/{id}/...; textos por t(); horas en la zona de la empresa.
(() => {
  "use strict";

  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const num = (v) => Number(v || 0) || 0;
  const fill = (s, vars) => (vars ? String(s).replace(/\{(\w+)\}/g, (m, k) => (vars[k] !== undefined ? String(vars[k]) : m)) : String(s));
  const T = (s, vars) => (typeof window !== "undefined" && window.CxI18n && typeof window.CxI18n.t === "function" ? window.CxI18n.t(s, vars) : fill(s, vars));

  const KIND = { memory: "Memoria relámpago", trivia: "Trivia Máquina del tiempo", roulette: "Ruleta de la rifa", differences: "7 diferencias" };
  const ICON = { memory: "🃏", trivia: "⏳", differences: "🔍" };
  const STATUS = { registration: "Registro abierto", playing: "En juego", closed: "Cerrada", cancelled: "Cancelada" };
  const ERRORS = {
    numeros_agotados: "Ya salieron todos los números de ese rango esta noche.",
    parejas_invalidas: "Las parejas deben ser 5, 7, 10, 13 o 15.",
    escena_invalida: "Escoge Bar o Concierto.",
    ya_hay_una_ronda_activa: "Ya hay una ronda abierta: ciérrala antes de abrir otra.",
    la_ronda_no_esta_en_registro: "La ronda ya no está en registro.",
    la_ronda_no_esta_cerrada: "Primero cierra la ronda.",
    puesto_sin_ganador: "Ese puesto no tiene ganador.",
    datos_purgados: "Los datos de esta ronda ya se purgaron (30 días).",
    documento_invalido: "Documento inválido.",
    rango_invalido: "Rango inválido.",
    opciones_repetidas: "Las tres opciones deben ser distintas.",
  };
  const LEVEL_OPTS = [1, 2, 3, 4, 5];
  const MEM_OPTS = [60, 90, 120, 150, 180, 210, 240, 270, 300, 360, 420];
  const TRIVIA_OPTS = [120, 150, 180, 210, 240, 300, 360, 420, 600];
  const DIFF_OPTS = [90, 120, 150, 180, 240, 300, 420];
  const PENALTY_OPTS = [0, 2, 3, 5, 8, 10, 15];

  const model = { tab: "live", ctx: null, live: null, questions: [], history: null, draft: null, qEdit: null, error: "", info: "", busy: "",
    denied: "", lastSpin: null, validation: null, loading: false, form: { range: 0, spinPrize: "", prize: {}, place: 1, doc: "", pairs: null, scene: null } };
  let ctx = null;
  let bound = false;
  let timer = null;

  // ------------------------------------------------------------ formatos
  const zone = () => (model.ctx && model.ctx.brand && model.ctx.brand.timezone) || undefined;
  const locale = () => (window.CxI18n && window.CxI18n.locale ? window.CxI18n.locale() : "es-CO");
  function clock(iso) {
    if (!iso) return "—";
    try { return new Intl.DateTimeFormat(locale(), { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: zone() }).format(new Date(iso)); } catch (_) { return String(iso).slice(11, 16); }
  }
  function day(iso) {
    if (!iso) return "—";
    try { return new Intl.DateTimeFormat(locale(), { weekday: "short", day: "2-digit", month: "short", timeZone: "UTC" }).format(new Date(`${String(iso).slice(0, 10)}T12:00:00Z`)); } catch (_) { return String(iso).slice(0, 10); }
  }
  // Resultado y tiempo (castigos incluidos): "5/7 · 01:42", "8/10 · 02:31", "7 parejas · 01:12".
  function fmtTime(ms) {
    if (ms === null || ms === undefined || ms === "") return "";
    const s2 = Math.max(0, Math.round(Number(ms) / 1000));
    return `${String(Math.floor(s2 / 60)).padStart(2, "0")}:${String(s2 % 60).padStart(2, "0")}`;
  }
  function resultLabel(kind, score, goal, ms) {
    const n = Number(score) || 0;
    const main = kind === "memory" ? T(n === 1 ? "{n} pareja" : "{n} parejas", { n }) : `${n}/${goal || "?"}`;
    const t = fmtTime(ms);
    return t ? `${main} · ${t}` : main;
  }
  function placeLabel(n) { return T(["", "1.er puesto", "2.º puesto", "3.er puesto"][n] || "{n}.º puesto", { n }); }
  function errText(e) { return T(ERRORS[e] || e || "No se pudo completar la acción."); }
  const can = (k) => !!(model.ctx && model.ctx.can && model.ctx.can[k]);
  const isAdmin = () => !!(model.ctx && model.ctx.role === "admin");

  // ------------------------------------------------------------ datos
  const base = () => `${ctx.apiBase}/loyalty-games/companies/${encodeURIComponent(ctx.companyId)}`;
  const headers = (json) => { const t = ctx.token(); return { ...(t ? { Authorization: `Bearer ${t}` } : {}), ...(json ? { "Content-Type": "application/json" } : {}) }; };

  async function call(path, method = "GET", body = undefined) {
    const res = await fetch(`${base()}${path}`, { method, headers: headers(body !== undefined), body: body !== undefined ? JSON.stringify(body) : undefined });
    let data = null;
    try { data = await res.json(); } catch (_) {}
    if (!res.ok) {
      const err = new Error(errText(data && typeof data.detail === "string" ? data.detail : ""));
      err.status = res.status;
      throw err;
    }
    return data;
  }

  async function loadAll() {
    model.loading = true; draw();
    try {
      model.ctx = await call("/context");
      model.live = model.ctx.live;
      model.denied = "";
    } catch (error) {
      model.denied = error.status === 401 || error.status === 403 || error.status === 404 ? T("Juegos en vivo no está disponible para tu usuario.") : "";
      model.error = model.denied ? "" : error.message;
    } finally { model.loading = false; draw(); schedule(); }
  }

  async function loadLive() {
    try { model.live = await call("/live"); } catch (error) { model.error = error.message; }
    if (!liveInputsBusy()) draw();
  }

  function schedule() {
    if (timer) clearTimeout(timer);
    if (!ctx || !model.ctx) return;
    const active = model.live && model.live.active;
    timer = setTimeout(async () => {
      if (!ctx || !document.querySelector("[data-lg-root]")) { timer = null; return; }
      if (model.tab === "live" && !model.busy) await loadLive();
      schedule();
    }, active ? 1000 : 5000);
  }

  async function act(kind, fn) {
    model.busy = kind; model.error = ""; model.info = ""; draw();
    try { await fn(); } catch (error) { model.error = error.message || T("No se pudo completar la acción."); }
    finally { model.busy = ""; draw(); }
  }

  // ------------------------------------------------------------ vistas
  function head() {
    const c = (ctx && ctx.company) || {};
    const logoUrl = model.ctx && model.ctx.brand ? model.ctx.brand.logo_url : "";
    const logo = logoUrl ? `<img class="lg-logo" src="${h(logoUrl)}" alt="">` : `<span class="lg-logo lg-logo-txt">${h(String(c.name || "?").slice(0, 1))}</span>`;
    return `<header class="client-hero lg-head"><button type="button" class="lg-btn lg-back" data-lg-back>← ${h(T("Volver"))}</button>
      <div class="lg-brand">${logo}<div><p class="client-eyebrow">${h(c.name || "")}</p><h1 class="client-title">🎮 ${h(T("Juegos en vivo"))}</h1></div></div></header>`;
  }

  function tabs() {
    const items = [["live", T("En vivo")]];
    if (isAdmin()) items.push(["config", T("Configuración")], ["questions", T("Preguntas")], ["history", T("Historial")]);
    return `<nav class="lg-tabs" role="tablist" aria-label="${h(T("Juegos en vivo"))}">${items.map(([k, l]) => `<button type="button" role="tab" aria-selected="${model.tab === k}" class="${model.tab === k ? "client-btn is-on" : ""}" data-lg-tab="${k}">${h(l)}</button>`).join("")}</nav>`;
  }

  function screenCard() {
    if (!isAdmin() || !model.ctx.screen_url) return "";
    return `<section class="client-panel lg-card"><h2 class="lg-h">📺 ${h(T("Pantalla del bar"))}</h2>
      <p class="lg-muted">${h(T("Ábrela en el televisor o proyector. Es de solo lectura y no pide clave."))}</p>
      <div class="lg-link"><input readonly value="${h(model.ctx.screen_url)}" aria-label="${h(T("Enlace de la pantalla"))}" data-lg-screen-url>
        <a class="lg-btn" href="${h(model.ctx.screen_url)}" target="_blank" rel="noopener">${h(T("Abrir"))}</a>
        <button type="button" class="lg-btn" data-lg-copy>${h(T("Copiar"))}</button>
        <button type="button" class="lg-btn" data-lg-regenerate>${h(T("Regenerar enlace"))}</button></div></section>`;
  }

  function rouletteCard() {
    const ranges = arr(model.ctx.settings && model.ctx.settings.roulette_ranges);
    const r = model.live && model.live.roulette;
    const spin = model.lastSpin;
    return `<section class="client-panel lg-card"><h2 class="lg-h">🎡 ${h(T("Ruleta de la rifa"))}</h2>
      <div class="lg-row"><label class="lg-field">${h(T("Rango"))}<select data-lg-range>${ranges.map((x, i) => `<option value="${i}" ${Number(model.form.range) === i ? "selected" : ""}>${h(`${x.min}–${x.max}${x.prize ? ` · ${x.prize}` : ""}`)}</option>`).join("")}</select></label>
        <label class="lg-field lg-grow">${h(T("Premio"))}<input data-lg-spin-prize maxlength="160" value="${h(model.form.spinPrize)}" placeholder="${h(T("Premio del giro"))}"></label>
        <button type="button" class="client-btn lg-btn is-primary" data-lg-spin ${model.busy ? "disabled" : ""}>🎡 ${h(T("Girar"))}</button></div>
      ${spin ? `<p class="lg-spin" role="status"><b>${h(spin.number)}</b><span>${h(spin.prize || "")}</span></p>` : ""}
      ${r ? `<p class="lg-muted">${h(T("Sacados esta noche ({min}–{max}): {list}", { min: r.range_min, max: r.range_max, list: arr(r.drawn).join(", ") }))}</p>` : ""}
    </section>`;
  }

  function launchCard() {
    const busy = model.live && model.live.active;
    const prizes = (model.ctx.settings && model.ctx.settings.prizes) || {};
    return `<section class="client-panel lg-card"><h2 class="lg-h">🕹️ ${h(T("Abrir un juego"))}</h2>
      ${["memory", "trivia", "differences"].map((k) => `<div class="lg-row"><b class="lg-game">${ICON[k]} ${h(T(KIND[k]))}</b>
        ${k === "differences" ? `<label class="lg-field">${h(T("Escena"))}<select data-lg-scenepick>${arr(model.ctx.scenes).map((sc) => `<option value="${h(sc.id)}" ${(model.form.scene || model.ctx.settings.differences_scene) === sc.id ? "selected" : ""}>${h(T(sc.name))}</option>`).join("")}</select></label>` : ""}
        ${k === "memory" ? `<label class="lg-field">${h(T("Parejas"))}<select data-lg-pairs>${arr(model.ctx.pair_options).map((n) => `<option value="${n}" ${Number(model.form.pairs || model.ctx.settings.memory_pairs) === n ? "selected" : ""}>${n} · ${h(mmss(model.ctx.settings.memory_times[String(n)]))}</option>`).join("")}</select></label>` : ""}
        <label class="lg-field lg-grow">${h(T("Premio"))}<input data-lg-prize="${k}" maxlength="160" value="${h(model.form.prize[k] !== undefined ? model.form.prize[k] : (prizes[k] || ""))}"></label>
        <button type="button" class="lg-btn" data-lg-open="${k}" ${busy || model.busy ? "disabled" : ""}>${h(T("Abrir registro"))}</button></div>`).join("")}
      ${busy ? `<p class="lg-muted">${h(T("Hay una ronda abierta: ciérrala para abrir otra."))}</p>` : ""}</section>`;
  }

  function mmss(sec) { const s2 = Math.max(0, Math.round(Number(sec) || 0)); return `${Math.floor(s2 / 60)}:${String(s2 % 60).padStart(2, "0")}`; }

  function lowLevels() {
    const lv = (model.ctx && model.ctx.levels) || {};
    return Object.keys(lv).filter((k) => Number(lv[k]) < 4).map((k) => ({ level: k, n: Number(lv[k]) }));
  }

  function levelWarning() {
    const low = lowLevels();
    if (!low.length) return "";
    return `<div class="lg-notice" role="status">${low.map((x) => h(T("Nivel {n}: solo {m} preguntas activas. Se recomiendan 4 o más para cambiar las falladas.", { n: x.level, m: x.n }))).join("<br>")}</div>`;
  }

  function remaining(r) {
    if (!r || !r.ends_at || !model.live) return "";
    const ms = new Date(r.ends_at).getTime() - new Date(model.live.now).getTime();
    const s = Math.max(0, Math.round(ms / 1000));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }

  function roundCard() {
    const r = model.live && model.live.round;
    if (!r) return `<section class="client-panel lg-card"><h2 class="lg-h">${h(T("Ronda actual"))}</h2><p class="lg-muted">${h(T("No hay ronda esta noche."))}</p></section>`;
    const all = arr(r.all_players).length ? r.all_players : arr(r.players);
    const actions = r.status === "registration"
      ? `<button type="button" class="client-btn lg-btn is-primary" data-lg-start="${h(r.id)}" ${model.busy ? "disabled" : ""}>▶ ${h(T("Iniciar"))}</button><button type="button" class="lg-btn" data-lg-close="${h(r.id)}">${h(T("Cancelar registro"))}</button>`
      : r.status === "playing" ? `<button type="button" class="lg-btn" data-lg-close="${h(r.id)}" ${model.busy ? "disabled" : ""}>■ ${h(T("Cerrar ronda"))}</button>` : "";
    const podium = arr(r.podium);
    return `<section class="client-panel lg-card"><header class="lg-round-head"><div><h2 class="lg-h">${h(T(KIND[r.kind]))}</h2>
        <p class="lg-muted">${h(r.prize ? T("Premio: {p}", { p: r.prize }) : T("Sin premio definido"))}</p></div>
        <i class="lg-chip is-${h(r.status)}">${h(T(STATUS[r.status] || r.status))}${r.status === "playing" ? ` · ${h(remaining(r))}` : ""}</i></header>
      ${r.status === "registration" && r.join_url ? `<p class="lg-muted">${h(T("Los jugadores entran con el QR de la pantalla del bar."))}</p>` : ""}
      <div class="lg-actions">${actions}</div>
      ${r.status === "playing" || r.status === "closed" ? `<ol class="lg-rank">${arr(r.ranking).slice(0, 10).map((p) => `<li><b>${h(p.rank)}.</b><span>${h(p.name)}</span><em>${h(resultLabel(r.kind, p.score, r.goal, p.ms))}</em></li>`).join("")}</ol>` : ""}
      ${podium.length ? `<p class="lg-podium">${podium.map((p) => `<span>${h(placeLabel(p.place))}: <b>${h(p.name)}</b>${p.score !== undefined ? ` · ${h(resultLabel(r.kind, p.score, r.goal, p.ms))}` : ""}</span>`).join("")}</p>` : ""}
      <h3 class="lg-h3">${h(T("Inscritos ({n})", { n: all.filter((p) => !p.hidden).length }))}</h3>
      <ul class="lg-players">${all.map((p) => `<li class="${p.hidden ? "is-hidden" : ""}"><span>${h(p.name)}${p.validated ? " ✓" : ""}</span>${p.hidden ? `<small>${h(T("Oculto"))}</small>` : `<button type="button" class="lg-btn is-small" data-lg-hide="${h(p.id)}" data-lg-round="${h(r.id)}">${h(T("Quitar de la pantalla"))}</button>`}</li>`).join("") || `<li class="lg-muted">${h(T("Aún no hay inscritos."))}</li>`}</ul>
      ${r.status === "closed" && podium.length ? validateBox(r) : ""}</section>`;
  }

  function validateBox(r) {
    const v = model.validation;
    return `<div class="lg-validate"><h3 class="lg-h3">${h(T("Validar ganador"))}</h3>
      <div class="lg-row"><label class="lg-field">${h(T("Puesto"))}<select data-lg-place>${arr(r.podium).map((p) => `<option value="${p.place}" ${Number(model.form.place) === p.place ? "selected" : ""}>${h(placeLabel(p.place))}</option>`).join("")}</select></label>
        <label class="lg-field lg-grow">${h(T("Documento"))}<input data-lg-doc inputmode="numeric" autocomplete="off" maxlength="20" value="${h(model.form.doc)}"></label>
        <button type="button" class="client-btn lg-btn is-primary" data-lg-validate="${h(r.id)}" ${model.busy ? "disabled" : ""}>${h(T("Validar"))}</button></div>
      ${v ? `<p class="lg-result ${v.match ? "is-ok" : "is-bad"}" role="status">${v.match ? h(T("✓ Coincide: {name} · {place}", { name: v.name, place: placeLabel(v.place) })) : h(T("✗ No coincide"))}</p>` : ""}</div>`;
  }

  function liveView() {
    if (!model.ctx) return "";
    return `${screenCard()}<div class="lg-grid">${rouletteCard()}${launchCard()}</div>${roundCard()}`;
  }

  function sel(attr, value, opts, label = (v) => v) {
    return `<select ${attr}>${opts.map((o) => `<option value="${h(o)}" ${String(o) === String(value) ? "selected" : ""}>${h(label(o))}</option>`).join("")}</select>`;
  }

  function configView() {
    const d = model.draft || (model.draft = JSON.parse(JSON.stringify(model.ctx.settings)));
    const scenes = arr(model.ctx.scenes);
    return `${levelWarning()}<section class="client-panel lg-card"><h2 class="lg-h">🃏 ${h(T("Memoria relámpago"))}</h2>
        <div class="lg-row"><label class="lg-field">${h(T("Parejas por defecto"))}${sel('data-lg-set="memory_pairs"', d.memory_pairs, arr(model.ctx.pair_options), (n) => T("{n} parejas", { n }))}</label></div>
        <p class="lg-muted">${h(T("Tiempo según las parejas (el barman puede cambiar las parejas al abrir la ronda):"))}</p>
        <div class="lg-row">${arr(model.ctx.pair_options).map((n) => `<label class="lg-field">${h(T("{n} parejas", { n }))}${sel(`data-lg-memtime="${n}"`, d.memory_times[String(n)], MEM_OPTS, mmss)}</label>`).join("")}</div></section>
      <section class="client-panel lg-card"><h2 class="lg-h">⏳ ${h(T("Trivia"))}</h2><div class="lg-row">
        <label class="lg-field">${h(T("Tiempo total"))}${sel('data-lg-set="trivia_seconds"', d.trivia_seconds, TRIVIA_OPTS, mmss)}</label></div>
        <p class="lg-muted">${h(T("10 preguntas (2 por nivel), 10 s cada una. Las falladas se cambian por otras nuevas del mismo nivel."))}</p></section>
      <section class="client-panel lg-card"><h2 class="lg-h">🔍 ${h(T("7 diferencias"))}</h2><div class="lg-row">
        <label class="lg-field">${h(T("Tiempo total"))}${sel('data-lg-set="differences_seconds"', d.differences_seconds, DIFF_OPTS, mmss)}</label>
        <label class="lg-field">${h(T("Castigo por toque en falso"))}${sel('data-lg-set="differences_penalty"', d.differences_penalty, PENALTY_OPTS, (n) => `+${n} s`)}</label></div>
        <div class="lg-row"><label class="lg-field">${h(T("Escena por defecto"))}<select data-lg-defscene>${scenes.map((sc) => `<option value="${h(sc.id)}" ${d.differences_scene === sc.id ? "selected" : ""}>${h(T(sc.name))}</option>`).join("")}</select></label></div></section>
      <section class="client-panel lg-card"><h2 class="lg-h">${h(T("Rangos y premios de la ruleta"))}</h2>
        ${arr(d.roulette_ranges).map((r, i) => `<div class="lg-row"><label class="lg-field">${h(T("Desde"))}<input type="number" min="0" max="9999" data-lg-rng="${i}" data-k="min" value="${h(r.min)}"></label>
          <label class="lg-field">${h(T("Hasta"))}<input type="number" min="1" max="9999" data-lg-rng="${i}" data-k="max" value="${h(r.max)}"></label>
          <label class="lg-field lg-grow">${h(T("Premio"))}<input data-lg-rng="${i}" data-k="prize" maxlength="160" value="${h(r.prize || "")}"></label>
          <button type="button" class="lg-btn is-small" data-lg-rng-del="${i}" aria-label="${h(T("Quitar rango"))}">✕</button></div>`).join("")}
        <button type="button" class="lg-btn" data-lg-rng-add>+ ${h(T("Rango"))}</button></section>
      <section class="client-panel lg-card"><h2 class="lg-h">${h(T("Premios por defecto"))}</h2><div class="lg-row">
        ${["memory", "trivia", "differences", "roulette"].map((k) => `<label class="lg-field lg-grow">${h(T(KIND[k]))}<input data-lg-defprize="${k}" maxlength="160" value="${h((d.prizes || {})[k] || "")}"></label>`).join("")}</div></section>
      <section class="client-panel lg-card"><h2 class="lg-h">${h(T("Textos"))}</h2>
        <label class="lg-field">${h(T("Texto del podio"))}<input data-lg-text="claim" maxlength="160" value="${h((d.texts || {}).claim || "")}"></label>
        <label class="lg-field">${h(T("Autorización de datos (Ley 1581)"))}<input data-lg-text="consent" maxlength="160" value="${h((d.texts || {}).consent || "")}"></label></section>
      <div class="lg-save"><button type="button" class="client-btn lg-btn is-primary" data-lg-save ${model.busy ? "disabled" : ""}>${h(T("Guardar configuración"))}</button></div>`;
  }

  function qForm(q) {
    return `<div class="lg-qform" data-lg-qform>
      <label class="lg-field">${h(T("Nivel"))}${sel("data-lg-q=\"level\"", q.level || 1, LEVEL_OPTS)}</label>
      <label class="lg-field lg-wide">${h(T("Pregunta"))}<input data-lg-q="question" maxlength="240" value="${h(q.question || "")}"></label>
      <label class="lg-field">${h(T("Correcta"))}<input data-lg-q="correct_answer" maxlength="120" value="${h(q.correct_answer || "")}"></label>
      <label class="lg-field">${h(T("Falsa 1"))}<input data-lg-q="wrong_1" maxlength="120" value="${h(q.wrong_1 || "")}"></label>
      <label class="lg-field">${h(T("Falsa 2"))}<input data-lg-q="wrong_2" maxlength="120" value="${h(q.wrong_2 || "")}"></label>
      <label class="lg-check"><input type="checkbox" data-lg-q="active" ${q.active !== false ? "checked" : ""}>${h(T("Activa"))}</label>
      <div class="lg-actions"><button type="button" class="client-btn lg-btn is-primary" data-lg-qsave>${h(T("Guardar pregunta"))}</button><button type="button" class="lg-btn" data-lg-qcancel>${h(T("Cancelar"))}</button></div></div>`;
  }

  function questionsView() {
    const list = model.questions;
    const editing = model.qEdit;
    return `<section class="client-panel lg-card"><header class="lg-round-head"><h2 class="lg-h">${h(T("Banco de preguntas"))}</h2>
        <button type="button" class="lg-btn" data-lg-qnew>+ ${h(T("Pregunta"))}</button></header>
      <p class="lg-muted">${h(T("La trivia toma 2 preguntas activas de cada nivel (1 a 5) y cambia las falladas por otras nuevas del mismo nivel."))}</p>${levelWarning()}
      ${editing && !editing.id ? qForm(editing) : ""}
      ${LEVEL_OPTS.map((lv) => {
        const rows = list.filter((q) => Number(q.level) === lv);
        return `<h3 class="lg-h3">${h(T("Nivel {n}", { n: lv }))} · ${h(T("{n} activas", { n: rows.filter((q) => q.active).length }))}</h3><ul class="lg-qlist">${rows.map((q) => editing && editing.id === q.id ? `<li>${qForm(editing)}</li>` : `<li class="${q.active ? "" : "is-off"}"><div><b>${h(q.question)}</b><small>✓ ${h(q.correct_answer)} · ✗ ${h(q.wrong_1)} · ✗ ${h(q.wrong_2)}${q.active ? "" : ` · ${h(T("Desactivada"))}`}</small></div><button type="button" class="lg-btn is-small" data-lg-qedit="${h(q.id)}">${h(T("Editar"))}</button></li>`).join("")}</ul>`;
      }).join("")}</section>`;
  }

  function historyView() {
    const hst = model.history;
    if (!hst) return `<section class="client-panel lg-card"><p class="lg-muted">${h(T("Cargando…"))}</p></section>`;
    return `<section class="client-panel lg-card"><h2 class="lg-h">${h(T("Rondas"))}</h2><div class="lg-table" role="table">
        <div class="lg-tr is-head" role="row"><span>${h(T("Noche"))}</span><span>${h(T("Juego"))}</span><span>${h(T("Premio"))}</span><span>${h(T("Jugadores"))}</span><span>${h(T("Podio"))}</span></div>
        ${arr(hst.rounds).map((r) => `<div class="lg-tr" role="row"><span>${h(day(r.game_day))} ${h(clock(r.created_at))}</span><span>${h(T(KIND[r.kind] || r.kind))} · ${h(T(STATUS[r.status] || r.status))}</span><span>${h(r.prize || "—")}</span><span>${h(r.players)}</span><span>${arr(r.results).map((p) => h(`${p.place}. ${p.name}${p.score !== undefined ? ` (${resultLabel(r.kind, p.score, r.goal, p.ms)})` : ""}`)).join(" · ") || "—"}${r.validated ? ` · ${h(T("{n} validados", { n: r.validated }))}` : ""}</span></div>`).join("") || `<p class="lg-muted">${h(T("Sin rondas todavía."))}</p>`}</div></section>
      <section class="client-panel lg-card"><h2 class="lg-h">${h(T("Giros de la ruleta"))}</h2><div class="lg-table is-draws" role="table">
        <div class="lg-tr is-head" role="row"><span>${h(T("Hora"))}</span><span>${h(T("Número"))}</span><span>${h(T("Rango"))}</span><span>${h(T("Premio"))}</span><span>${h(T("Giró"))}</span></div>
        ${arr(hst.draws).map((d) => `<div class="lg-tr" role="row"><span>${h(day(d.game_day))} ${h(clock(d.spun_at))}</span><span><b>${h(d.number)}</b></span><span>${h(`${d.range_min}–${d.range_max}`)}</span><span>${h(d.prize || "—")}</span><span>${h(d.spun_by)}</span></div>`).join("") || `<p class="lg-muted">${h(T("Sin giros todavía."))}</p>`}</div></section>`;
  }

  function view() {
    if (model.denied) return `<div class="lg-root" data-lg-root>${head()}<section class="client-panel lg-card"><p class="lg-denied">${h(model.denied)}</p></section></div>`;
    const body = !model.ctx ? `<section class="client-panel lg-card"><p class="lg-muted">${h(T("Cargando…"))}</p></section>`
      : model.tab === "config" ? configView() : model.tab === "questions" ? questionsView() : model.tab === "history" ? historyView() : liveView();
    return `<div class="lg-root" data-lg-root>${head()}${model.ctx ? tabs() : ""}
      ${model.error ? `<div class="lg-notice" role="alert">${h(model.error)}</div>` : ""}${model.info ? `<div class="lg-notice is-ok" role="status">${h(model.info)}</div>` : ""}${body}</div>`;
  }

  function draw() {
    if (!ctx) return;
    const host = ctx.host();
    if (host) host.innerHTML = view();
  }

  // El sondeo no repinta mientras alguien escribe (premio, documento): lo escrito vive en model.form.
  function liveInputsBusy() {
    const el = typeof document !== "undefined" ? document.activeElement : null;
    return !!(el && el.closest && el.closest("[data-lg-root]") && /^(INPUT|SELECT)$/.test(el.tagName));
  }

  // ------------------------------------------------------------ eventos
  function onClick(event) {
    const t = event.target;
    if (!ctx || !t || !t.closest || !t.closest("[data-lg-root]")) return;
    const attr = (a) => { const el = t.closest(`[${a}]`); return el ? el.getAttribute(a) : null; };
    let v;
    if (t.closest("[data-lg-back]")) { if (timer) clearTimeout(timer); timer = null; const b = ctx.back; ctx = null; b(); return; }
    if ((v = attr("data-lg-tab"))) {
      model.tab = v; model.error = ""; model.info = "";
      if (v === "questions") act("q", async () => { model.questions = arr((await call("/questions")).items); });
      else if (v === "history") act("h", async () => { model.history = await call("/history"); });
      else draw();
      return;
    }
    if (t.closest("[data-lg-copy]")) { try { navigator.clipboard.writeText(model.ctx.screen_url); model.info = T("Enlace copiado."); } catch (_) {} draw(); return; }
    if (t.closest("[data-lg-regenerate]")) { act("regen", async () => { const r = await call("/screen/regenerate", "POST"); model.ctx.screen_url = r.screen_url; model.info = T("Enlace nuevo: el anterior ya no abre la pantalla."); }); return; }
    if (t.closest("[data-lg-spin]")) {
      const body = { range_index: Number(model.form.range) || 0 };
      const prize = String(model.form.spinPrize || "").trim();
      if (prize) body.prize = prize;
      act("spin", async () => { model.lastSpin = await call("/roulette/spin", "POST", body); await loadLive(); });
      return;
    }
    if ((v = attr("data-lg-open"))) { const prize = model.form.prize[v] !== undefined ? model.form.prize[v] : ((model.ctx.settings.prizes || {})[v] || ""); const body = { kind: v, prize };
      if (v === "memory") body.pairs = Number(model.form.pairs || model.ctx.settings.memory_pairs);
      if (v === "differences") body.scene = model.form.scene || model.ctx.settings.differences_scene;
      act("open", async () => { model.live = await call("/rounds", "POST", body); model.validation = null; schedule(); }); return; }
    if ((v = attr("data-lg-start"))) { act("start", async () => { model.live = await call(`/rounds/${v}/start`, "POST"); schedule(); }); return; }
    if ((v = attr("data-lg-close"))) { act("close", async () => { model.live = await call(`/rounds/${v}/close`, "POST"); }); return; }
    if ((v = attr("data-lg-hide"))) { const rid = attr("data-lg-round"); act("hide", async () => { model.live = await call(`/rounds/${rid}/players/${v}/hide`, "POST"); }); return; }
    if ((v = attr("data-lg-validate"))) {
      const body = { place: Number(model.form.place) || 1, document: model.form.doc };
      model.form.doc = "";
      act("validate", async () => { model.validation = await call(`/rounds/${v}/validate`, "POST", body); await loadLive(); });
      return;
    }
    if (t.closest("[data-lg-rng-add]")) { model.draft.roulette_ranges.push({ min: 1, max: 100, prize: "" }); draw(); return; }
    if ((v = attr("data-lg-rng-del")) !== null) { model.draft.roulette_ranges.splice(Number(v), 1); draw(); return; }
    if (t.closest("[data-lg-save]")) {
      act("save", async () => {
        model.ctx.settings = await call("/settings", "PUT", model.draft);
        model.draft = null;
        model.info = T("Configuración guardada.");
      });
      return;
    }
    if (t.closest("[data-lg-qnew]")) { model.qEdit = { level: 1, active: true }; draw(); return; }
    if ((v = attr("data-lg-qedit"))) { model.qEdit = { ...model.questions.find((q) => q.id === v) }; draw(); return; }
    if (t.closest("[data-lg-qcancel]")) { model.qEdit = null; draw(); return; }
    if (t.closest("[data-lg-qsave]")) {
      const q = model.qEdit;
      act("qsave", async () => {
        await call(q.id ? `/questions/${q.id}` : "/questions", q.id ? "PUT" : "POST", q);
        model.questions = arr((await call("/questions")).items); model.qEdit = null; model.info = T("Pregunta guardada.");
        const lv = {};
        model.questions.filter((x) => x.active).forEach((x) => { lv[String(x.level)] = (lv[String(x.level)] || 0) + 1; });
        model.ctx.levels = Object.fromEntries([1, 2, 3, 4, 5].map((n) => [String(n), lv[String(n)] || 0]));
      });
    }
  }

  function onInput(event) {
    const t = event.target;
    if (!ctx || !t || !t.closest || !t.closest("[data-lg-root]")) return;
    let v;
    if (t.hasAttribute("data-lg-range")) model.form.range = Number(t.value);
    else if (t.hasAttribute("data-lg-spin-prize")) model.form.spinPrize = t.value;
    else if ((v = t.getAttribute("data-lg-prize"))) model.form.prize[v] = t.value;
    else if (t.hasAttribute("data-lg-place")) model.form.place = Number(t.value);
    else if (t.hasAttribute("data-lg-doc")) model.form.doc = t.value;
    else if (t.hasAttribute("data-lg-pairs")) model.form.pairs = Number(t.value);
    else if (t.hasAttribute("data-lg-scenepick")) model.form.scene = t.value;
  }

  function onChange(event) {
    onInput(event);
    const t = event.target;
    if (!ctx || !t || !t.closest || !t.closest("[data-lg-root]")) return;
    let v;
    if ((v = t.getAttribute("data-lg-set"))) { model.draft[v] = Number(t.value); return; }
    if ((v = t.getAttribute("data-lg-memtime"))) { model.draft.memory_times[v] = Number(t.value); return; }
    if (t.hasAttribute("data-lg-defscene")) { model.draft.differences_scene = t.value; return; }
    if ((v = t.getAttribute("data-lg-rng")) !== null) { const k = t.getAttribute("data-k"); model.draft.roulette_ranges[Number(v)][k] = k === "prize" ? t.value : Number(t.value); return; }
    if ((v = t.getAttribute("data-lg-defprize"))) { model.draft.prizes[v] = t.value; return; }
    if ((v = t.getAttribute("data-lg-text"))) { model.draft.texts[v] = t.value; return; }
    if ((v = t.getAttribute("data-lg-q")) && model.qEdit) { model.qEdit[v] = v === "active" ? t.checked : v === "level" ? Number(t.value) : t.value; }
  }

  async function mount(context) {
    ctx = context;
    if (!bound && typeof document.addEventListener === "function") {
      document.addEventListener("click", onClick);
      document.addEventListener("change", onChange);
      document.addEventListener("input", onInput);
      bound = true;
    }
    Object.assign(model, { tab: "live", ctx: null, live: null, draft: null, qEdit: null, error: "", info: "", denied: "", lastSpin: null, validation: null,
      form: { range: 0, spinPrize: "", prize: {}, place: 1, doc: "", pairs: null, scene: null } });
    draw();
    await loadAll();
  }

  window.CxLoyaltyGames = { mount, model, view, placeLabel, errText, liveInputsBusy, resultLabel, fmtTime };
})();
