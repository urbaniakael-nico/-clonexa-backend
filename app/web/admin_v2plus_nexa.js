// Consola v2+ · Conversaciones Nexa (solo Admin V2): el WhatsApp de ventas de
// Clonexa (+57 314 479 8220). Lista con filtros por etapa y fecha, buscador y
// contador de nuevas; detalle estilo chat (solo lectura) con los datos que
// Nexa detectó y el estado de cada entrega; Pausar / Reanudar Nexa, Marcar no
// interesado y Exportar CSV. Se actualiza solo cada 15 s.
// Sin estilos en línea (CSP de v2+): todo por clase. Todo escapado.
(() => {
  "use strict";

  const API = "/admin-v2/api/nexa-wa";
  const REFRESH_MS = 15000;
  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const enc = encodeURIComponent;
  const STAGES = { nuevo: "Nuevo", calificado: "Calificado", demo_agendada: "Demo agendada", pidio_persona: "Pidió persona", no_interesado: "No interesado", baja: "Baja" };
  const STATUS = { sent: ["✓", "Enviado"], delivered: ["✓✓", "Entregado"], read: ["✓✓", "Leído"], failed: ["⚠", "Fallido"] };
  const DOW = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
  const MON = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

  async function request(url, options = {}) {
    const response = await fetch(url, { credentials: "same-origin", ...options,
      headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) } });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401) { window.location.href = "/admin-v2plus/login"; throw new Error("Sesión vencida."); }
    if (!response.ok) throw new Error((data && typeof data.detail === "string" && data.detail) || `Respuesta ${response.status}`);
    return data;
  }

  function listUrl(f = {}) {
    const p = new URLSearchParams();
    if (f.stage) p.set("stage", f.stage);
    if (f.q) p.set("q", f.q);
    if (f.desde) p.set("desde", f.desde);
    if (f.hasta) p.set("hasta", f.hasta);
    const qs = p.toString();
    return `${API}/conversations${qs ? `?${qs}` : ""}`;
  }
  const api = {
    list: (f) => request(listUrl(f)),
    detail: (id) => request(`${API}/conversations/${enc(id)}`),
    pause: (id, paused) => request(`${API}/conversations/${enc(id)}/pause`, { method: "POST", body: JSON.stringify({ paused }) }),
    notInterested: (id) => request(`${API}/conversations/${enc(id)}/not-interested`, { method: "POST", body: "{}" }),
    csvUrl: (id) => `${API}/conversations/${enc(id)}/export.csv`,
  };

  // ------------------------------------------------------------ estado
  const model = { filters: { stage: "", q: "", desde: "", hasta: "" }, list: null, selected: "", detail: null, busy: "", error: "", updatedAt: null };
  let ctx = null;
  let bound = false;
  let timer = null;
  let typing = null;

  // ------------------------------------------------------------ utilidades
  // Hora de Colombia (UTC-5, sin horario de verano), sin depender del equipo.
  function bogota(iso) {
    const t = Date.parse(iso || "");
    if (!Number.isFinite(t)) return null;
    const d = new Date(t - 5 * 3600000);
    return { y: d.getUTCFullYear(), mo: d.getUTCMonth(), d: d.getUTCDate(), dow: d.getUTCDay(), h: d.getUTCHours(), mi: d.getUTCMinutes() };
  }
  function clock(b) {
    const h12 = b.h % 12 || 12;
    return `${h12}:${String(b.mi).padStart(2, "0")} ${b.h < 12 ? "a. m." : "p. m."}`;
  }
  function when(iso, now = Date.now()) {
    const b = bogota(iso);
    if (!b) return "";
    const today = bogota(new Date(now).toISOString());
    if (b.y === today.y && b.mo === today.mo && b.d === today.d) return clock(b);
    const yesterday = bogota(new Date(now - 86400000).toISOString());
    if (b.y === yesterday.y && b.mo === yesterday.mo && b.d === yesterday.d) return `Ayer ${clock(b)}`;
    return `${DOW[b.dow]} ${b.d} ${MON[b.mo]}${b.y !== today.y ? ` ${b.y}` : ""} · ${clock(b)}`;
  }
  function phone(wa) {
    const d = String(wa || "").replace(/\D/g, "");
    if (d.length === 12 && d.startsWith("57")) return `+57 ${d.slice(2, 5)} ${d.slice(5, 8)} ${d.slice(8)}`;
    return d ? `+${d}` : "";
  }
  function waLink(wa) {
    const d = String(wa || "").replace(/\D/g, "");
    return d ? `<a class="vp-nx-wa" href="https://wa.me/${d}" target="_blank" rel="noopener noreferrer">${h(phone(d))}</a>` : "";
  }
  function safeUrl(url) {
    return /^https:\/\/[^\s"'<>]+$/i.test(String(url || "")) ? String(url) : "";
  }
  function stageChip(stage) {
    const key = STAGES[stage] ? stage : "nuevo";
    return `<span class="vp-nx-stage is-${key}">${h(STAGES[key])}</span>`;
  }
  function name(c) { return (c && (c.nombre || phone(c.wa_id))) || "Sin nombre"; }

  // ------------------------------------------------------------ dibujo
  function chipsHtml(list, stage) {
    const counts = (list && list.counts) || {};
    const total = (list && list.total) || 0;
    const chip = (key, label, n) => `<button class="vp-chip ${stage === key ? "is-active" : ""}" type="button" data-nx-stage="${key}" aria-pressed="${stage === key}">${h(label)}<b>${h(n)}</b></button>`;
    return chip("", "Todas", total) + Object.keys(STAGES).map((k) => chip(k, STAGES[k], counts[k] || 0)).join("");
  }

  function rowHtml(c, selected, now) {
    return `<li class="vp-nx-row ${c.id === selected ? "is-selected" : ""} ${c.nueva ? "is-new" : ""}">
      <button class="vp-nx-open" type="button" data-nx-open="${h(c.id)}" aria-label="Abrir conversación con ${h(name(c))}">
        <span class="vp-nx-row-top"><b class="vp-nx-name">${c.nueva ? '<span class="vp-nx-dot" aria-hidden="true"></span><span class="sr-only">Nueva: </span>' : ""}${h(name(c))}</b><time class="vp-nx-time">${h(when(c.ultimo_at, now))}</time></span>
        <span class="vp-nx-biz">${h([c.tipo_negocio, c.ciudad].filter(Boolean).join(" · ") || "Sin datos aún")}</span>
        <span class="vp-nx-last">${h(c.ultimo || "")}</span>
      </button>
      <span class="vp-nx-row-meta">${stageChip(c.etapa)}${c.nexa_pausada ? '<span class="vp-nx-paused">Nexa pausada</span>' : ""}${waLink(c.wa_id)}</span>
    </li>`;
  }

  function listHtml(list, selected = "", now = Date.now()) {
    if (!list) return `<p class="vp-loading">Cargando conversaciones…</p>`;
    const items = arr(list.items);
    if (!items.length) return `<div class="vp-empty">${list.total ? "Ninguna conversación con estos filtros." : "Aún no hay conversaciones. Cuando alguien le escriba a Nexa al +57 314 479 8220, aparece aquí."}</div>`;
    return `<ul class="vp-nx-list">${items.map((c) => rowHtml(c, selected, now)).join("")}</ul>`;
  }

  function bubbleHtml(m, now) {
    const st = STATUS[m.estado];
    const opts = arr(m.opciones).length ? `<span class="vp-nx-opts">${arr(m.opciones).map((o) => `<span class="vp-nx-opt">${h(o)}</span>`).join("")}</span>` : "";
    const kind = m.tipo && !["text", "buttons", "list", "interactive", "button"].includes(m.tipo) ? `<span class="vp-nx-kind">[${h(m.tipo)}]</span> ` : "";
    const status = m.direccion === "out" && st
      ? `<span class="vp-nx-status is-${h(m.estado)}" title="${h(st[1])}${m.error ? `: ${h(m.error)}` : ""}">${h(st[0])} ${h(st[1])}</span>` : "";
    return `<li class="vp-nx-msg is-${m.direccion === "out" ? "out" : "in"}">
      <div class="vp-nx-bubble"><p>${kind}${h(m.texto || "")}</p>${opts}</div>
      <span class="vp-nx-msg-meta"><time>${h(when(m.creado, now))}</time>${status}</span>
    </li>`;
  }

  function detailHtml(d, now = Date.now(), busy = "") {
    if (!d) return `<div class="vp-empty vp-nx-pick">Elige una conversación para verla.</div>`;
    const c = d.contacto || {};
    const e = d.entregas || {};
    const demo = safeUrl(c.demo_link);
    const kv = (label, value) => `<div class="vp-kv"><span>${h(label)}</span><b>${value}</b></div>`;
    const plain = (v) => (v ? h(v) : "—");
    const paused = Boolean(c.nexa_pausada);
    const closed = c.etapa === "no_interesado" || c.etapa === "baja";
    return `<article class="vp-nx-detail-inner">
      <header class="vp-nx-dhead">
        <button class="vp-btn vp-btn-sm vp-nx-back" type="button" data-nx-back>← Conversaciones</button>
        <div class="vp-nx-who"><h3>${h(name(c))}</h3><p>${waLink(c.wa_id)} ${stageChip(c.etapa)}${paused ? '<span class="vp-nx-paused">Nexa pausada</span>' : ""}</p></div>
        <div class="vp-nx-actions">
          <button class="vp-btn vp-btn-sm ${paused ? "vp-btn-primary" : ""}" type="button" data-nx-pause="${paused ? "0" : "1"}" ${busy ? "disabled" : ""}>${paused ? "Reanudar Nexa" : "Pausar Nexa"}</button>
          <button class="vp-btn vp-btn-sm vp-btn-danger" type="button" data-nx-noint ${busy || closed ? "disabled" : ""}>Marcar no interesado</button>
          <a class="vp-btn vp-btn-sm" href="${h(api.csvUrl(c.id))}" download>Exportar CSV</a>
        </div>
      </header>
      <section class="vp-kv-grid vp-nx-data" aria-label="Datos detectados">
        ${kv("Negocio", plain(c.tipo_negocio))}${kv("Ciudad", plain(c.ciudad))}${kv("Tamaño", plain(c.tamano))}${kv("Qué les cuesta", plain(c.dolor))}
        ${kv("Correo", plain(c.correo))}${kv("Idioma", plain(c.idioma === "en" ? "Inglés" : c.idioma === "es" ? "Español" : c.idioma))}
        ${kv("Demo", c.demo_at ? `${h(when(c.demo_at, now))}${demo ? ` · <a href="${h(demo)}" target="_blank" rel="noopener noreferrer">Meet</a>` : ""}` : "—")}
        ${kv("Entregas", `<span class="vp-mono">${h(e.sent || 0)} enviados · ${h(e.delivered || 0)} entregados · ${h(e.read || 0)} leídos${e.failed ? ` · <span class="vp-nx-bad">${h(e.failed)} fallidos</span>` : ""}</span>`)}
      </section>
      <ol class="vp-nx-chat" data-nx-chat aria-label="Conversación">${arr(d.mensajes).map((m) => bubbleHtml(m, now)).join("") || '<li class="vp-empty">Sin mensajes.</li>'}</ol>
      <p class="vp-nx-note">Solo lectura: Nexa responde sola. Para escribir tú, pausa Nexa y abre el chat en WhatsApp.</p>
    </article>`;
  }

  function view(now = Date.now()) {
    const f = model.filters;
    const nuevas = (model.list && model.list.nuevas) || 0;
    return `<section class="vp-nx ${model.selected ? "has-detail" : ""}" data-nx-root>
      <header class="vp-head">
        <div><p class="vp-eyebrow">VENTAS · WHATSAPP</p><h2 class="vp-title">Conversaciones Nexa</h2>
          <p class="vp-ficha-meta"><span class="vp-nx-new-count ${nuevas ? "is-on" : ""}" data-nx-nuevas>${h(nuevas)} ${nuevas === 1 ? "nueva" : "nuevas"}</span> · <span data-nx-updated>${model.updatedAt ? `Actualizado ${h(when(new Date(model.updatedAt).toISOString(), now))}` : "Se actualiza cada 15 s"}</span></p></div>
      </header>
      <div class="vp-panel vp-nx-filters">
        <div class="vp-toolbar">
          <label class="sr-only" for="vpNxQ">Buscar</label>
          <input id="vpNxQ" class="vp-search" type="search" placeholder="Buscar nombre, número, negocio o ciudad" value="${h(f.q)}" data-nx-q autocomplete="off">
          <div class="vp-nx-dates">
            <label class="vp-field">Desde<input type="date" value="${h(f.desde)}" data-nx-date="desde"></label>
            <label class="vp-field">Hasta<input type="date" value="${h(f.hasta)}" data-nx-date="hasta"></label>
          </div>
        </div>
        <div class="vp-chips" role="group" aria-label="Filtrar por etapa" data-nx-chips>${chipsHtml(model.list, f.stage)}</div>
      </div>
      ${model.error ? `<div class="vp-alert" role="alert"><strong>No se pudo cargar</strong><span>${h(model.error)}</span></div>` : ""}
      <div class="vp-nx-layout">
        <div class="vp-panel vp-nx-side" data-nx-list>${listHtml(model.list, model.selected, now)}</div>
        <div class="vp-panel vp-nx-detail" data-nx-detail>${detailHtml(model.detail, now, model.busy)}</div>
      </div>
    </section>`;
  }

  // ------------------------------------------------------------ montaje y datos
  function root() { return (ctx && ctx.root && ctx.root()) || null; }
  function q(sel) { const r = root(); return r && r.querySelector ? r.querySelector(sel) : null; }

  function draw() {
    const r = root();
    if (!r) return;
    r.innerHTML = view();
    scrollChat(true);
  }

  // El refresco solo cambia lista, contadores y chat: el buscador conserva lo escrito y el foco.
  function drawParts(stickBottom) {
    const now = Date.now();
    const box = q("[data-nx-root]");
    if (!box) { draw(); return; }
    box.classList.toggle("has-detail", Boolean(model.selected));
    const set = (sel, html) => { const el = q(sel); if (el) el.innerHTML = html; };
    set("[data-nx-chips]", chipsHtml(model.list, model.filters.stage));
    set("[data-nx-list]", listHtml(model.list, model.selected, now));
    const n = (model.list && model.list.nuevas) || 0;
    const badge = q("[data-nx-nuevas]");
    if (badge) { badge.textContent = `${n} ${n === 1 ? "nueva" : "nuevas"}`; badge.classList.toggle("is-on", n > 0); }
    const upd = q("[data-nx-updated]");
    if (upd && model.updatedAt) upd.textContent = `Actualizado ${when(new Date(model.updatedAt).toISOString(), now)}`;
    set("[data-nx-detail]", detailHtml(model.detail, now, model.busy));
    scrollChat(stickBottom);
  }

  function scrollChat(force) {
    const chat = q("[data-nx-chat]");
    if (chat && force) chat.scrollTop = chat.scrollHeight;
  }

  function nearBottom() {
    const chat = q("[data-nx-chat]");
    return !chat || chat.scrollHeight - chat.scrollTop - chat.clientHeight < 80;
  }

  async function loadList() {
    try {
      model.list = await api.list(model.filters);
      model.error = "";
      model.updatedAt = Date.now();
    } catch (err) { model.error = (err && err.message) || "Sin conexión."; }
  }

  async function loadDetail() {
    if (!model.selected) { model.detail = null; return; }
    try { model.detail = await api.detail(model.selected); } catch (err) { model.error = (err && err.message) || "Sin conexión."; }
  }

  async function refresh() {
    if (!ctx || (ctx.active && !ctx.active())) { stop(); return; }
    const stick = nearBottom();
    await Promise.all([loadList(), loadDetail()]);
    if (ctx.active && !ctx.active()) return;
    drawParts(stick);
  }

  function stop() { if (timer) { window.clearInterval(timer); timer = null; } }
  function schedule() { stop(); timer = window.setInterval(refresh, REFRESH_MS); }

  async function open(id) {
    model.selected = id;
    model.detail = null;
    drawParts(true);
    await loadDetail();
    await loadList(); // abrirla la marca como vista: baja el contador de nuevas
    drawParts(true);
  }

  async function act(fn, done) {
    if (model.busy || !model.selected) return;
    model.busy = "1";
    drawParts(false);
    try {
      model.detail = await fn();
      if (ctx && ctx.toast) ctx.toast(done);
      await loadList();
    } catch (err) { model.error = (err && err.message) || "No se pudo."; }
    model.busy = "";
    drawParts(false);
  }

  function onClick(event) {
    if (!ctx || (ctx.active && !ctx.active())) return;
    const t = event.target;
    if (!t || !t.closest) return;
    const openBtn = t.closest("[data-nx-open]");
    if (openBtn) { open(openBtn.getAttribute("data-nx-open") || ""); return; }
    const stage = t.closest("[data-nx-stage]");
    if (stage) { model.filters.stage = stage.getAttribute("data-nx-stage") || ""; loadList().then(() => drawParts(false)); return; }
    if (t.closest("[data-nx-back]")) { model.selected = ""; model.detail = null; drawParts(false); return; }
    const pause = t.closest("[data-nx-pause]");
    if (pause) { const p = pause.getAttribute("data-nx-pause") === "1"; act(() => api.pause(model.selected, p), p ? "Nexa pausada para este número." : "Nexa reanudada."); return; }
    if (t.closest("[data-nx-noint]")) act(() => api.notInterested(model.selected), "Marcado como no interesado.");
  }

  function onInput(event) {
    if (!ctx || (ctx.active && !ctx.active())) return;
    const t = event.target;
    if (!t || !t.matches) return;
    if (t.matches("[data-nx-q]")) {
      model.filters.q = String(t.value || "").slice(0, 80);
      if (typing) window.clearTimeout(typing);
      typing = window.setTimeout(() => loadList().then(() => drawParts(false)), 300);
    }
  }

  function onChange(event) {
    if (!ctx || (ctx.active && !ctx.active())) return;
    const t = event.target;
    if (t && t.matches && t.matches("[data-nx-date]")) {
      model.filters[t.getAttribute("data-nx-date")] = /^\d{4}-\d{2}-\d{2}$/.test(t.value || "") ? t.value : "";
      loadList().then(() => drawParts(false));
    }
  }

  window.CxConsoleSections = window.CxConsoleSections || {};
  window.CxConsoleSections.nexa = {
    mount(context) {
      ctx = context;
      if (!bound && typeof document.addEventListener === "function") {
        document.addEventListener("click", onClick);
        document.addEventListener("input", onInput);
        document.addEventListener("change", onChange);
        bound = true;
      }
      const p = (context && context.params) || {};
      if (p.contact) { model.selected = p.contact; model.detail = null; }
      draw();
      Promise.all([loadList(), loadDetail()]).then(() => drawParts(true));
      schedule();
    },
    refreshPulse() {},
  };
  window.CxConsoleNexa = { model, api, view, listHtml, detailHtml, chipsHtml, bubbleHtml, stageChip, when, phone, waLink, listUrl, refresh, open, STAGES, REFRESH_MS };
})();
