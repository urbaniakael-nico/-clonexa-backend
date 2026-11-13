// Consola v2+ · Ventas · Nexa → Cola de hoy (solo Admin V2). Pensada para el CELULAR: el dueño copia el texto,
// abre el perfil en la app de Instagram o Facebook, adjunta el bumerán y lo envía A MANO. Nada se envía solo.
// Una sola fuente: el backend (/api/v1/prospecting/admin/cola). Enviado / Saltar / No contactar son las mismas
// reglas que los botones de Telegram (Ley 2300: L-V 8:00-17:00, 1 contacto por semana, seguimiento único a los
// 7 días, baja en todos los canales). Sin estilos en línea (CSP de v2+): todo por clase. Todo escapado.
(() => {
  "use strict";

  const API = "/api/v1/prospecting/admin/cola";
  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const TABS = [["pendientes", "Pendientes"], ["seguimientos", "Seguimientos"], ["archivados", "Archivados"]];
  const NET = { instagram: ["IG", "Instagram"], facebook: ["f", "Facebook"] };

  async function request(url, options = {}) {
    const response = await fetch(url, { credentials: "same-origin", ...options,
      headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) } });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401) { window.location.href = "/admin-v2plus/login"; throw new Error("Sesión vencida."); }
    if (!response.ok) throw new Error((data && typeof data.detail === "string" && data.detail) || `Respuesta ${response.status}`);
    return data;
  }
  const api = {
    cola: () => request(API),
    pendientes: () => request(`${API}/pendientes`),
    accion: (id, accion) => request(`${API}/${encodeURIComponent(id)}/accion`, { method: "POST", body: JSON.stringify({ accion }) }),
  };

  const model = { tab: "pendientes", data: null, error: "", notice: "", menu: "", confirm: "", leaving: "", busy: "" };
  let ctx = null;
  let bound = false;

  const safeWeb = (u) => (/^https:\/\/(www\.|m\.)?(instagram|facebook)\.com\/[^\s"'<>]*$/i.test(String(u || "")) ? String(u) : "");
  const safeApp = (u) => (/^(instagram:\/\/user\?username=[A-Za-z0-9_.]{1,30}|fb:\/\/facewebmodal\/f\?href=[A-Za-z0-9%._~-]+)$/.test(String(u || "")) ? String(u) : "");
  const safeVideo = (u) => (/^\/admin-v2plus\/bumeranes\/[a-z]+\.mp4$/.test(String(u || "")) ? String(u) : "");
  const hora = (iso) => { if (!iso) return ""; try { return new Date(iso).toLocaleTimeString("es-CO", { timeZone: "America/Bogota", hour: "numeric", minute: "2-digit" }); } catch (_) { return ""; } };
  const items = (tab) => arr(model.data && model.data[tab]);

  // ------------------------------------------------------------ menú: contador de pendientes
  function setBadge(n) {
    if (typeof document === "undefined" || !document.querySelectorAll) return;
    document.querySelectorAll("[data-cola-badge]").forEach((b) => { b.textContent = n > 0 ? String(n) : ""; b.hidden = !(n > 0); });
  }
  async function refreshBadge() {
    try { setBadge(Number((await api.pendientes()).pendientes || 0)); } catch (_) { /* sin sesión: el menú no muestra nada */ }
  }

  // ------------------------------------------------------------ vistas
  function header() {
    const d = model.data || {};
    const limit = Number(d.limite || 15);
    const sent = Number(d.enviados || 0);
    return `<header class="vp-head vp-cola-head"><div><p class="vp-eyebrow">VENTAS · NEXA</p><h1 class="vp-title">Cola de hoy</h1></div></header>
      <section class="vp-panel vp-section vp-cola-progress" aria-label="Avance de hoy">
        <div class="vp-row-between"><b>${h(d.fecha_label || "Hoy")}</b><b data-cola-count>${h(sent)} de ${h(limit)} enviados</b></div>
        <progress class="vp-cola-bar" max="${h(limit)}" value="${h(Math.min(sent, limit))}" aria-label="${h(sent)} de ${h(limit)} enviados"></progress>
        ${d.horario === false ? `<p class="vp-login-hint">⏰ Fuera del horario legal (lunes a viernes, 8:00 a 17:00, sin festivos): no envíes ahora.</p>` : ""}
      </section>
      <nav class="vp-cola-tabs" role="tablist" aria-label="Cola de hoy">${TABS.map(([k, l]) => `<button class="vp-chip vp-cola-tab ${model.tab === k ? "is-active" : ""}" type="button" role="tab"
        aria-selected="${model.tab === k}" data-cola-tab="${k}">${h(l)} <span>${h(items(k).length)}</span></button>`).join("")}</nav>`;
  }

  function netIcon(network) {
    const [short, label] = NET[network] || ["?", network];
    return `<span class="vp-cola-net is-${h(network)}" role="img" aria-label="${h(label)}">${h(short)}</span>`;
  }

  function card(i) {
    const web = safeWeb(i.profile_url);
    const app = safeApp(i.app_url);
    const video = safeVideo(i.video);
    const menuOpen = model.menu === String(i.id);
    const confirm = model.confirm === String(i.id);
    return `<article class="vp-panel vp-cola-card ${model.leaving === String(i.id) ? "is-leaving" : ""}" data-cola-card="${h(i.id)}">
      <header class="vp-cola-card-head">${netIcon(i.network)}<div><h2>${h(i.name)}</h2>
        <p>${h(i.nicho)}${i.zona ? ` · ${h(i.zona)}` : ""}${i.kind === "seguimiento" ? ` · <b class="vp-cola-follow">Seguimiento</b>` : ""}</p></div></header>
      <pre class="vp-cola-text" data-cola-text="${h(i.id)}">${h(i.text)}</pre>
      <div class="vp-cola-actions">
        ${web ? `<a class="vp-btn vp-cola-btn ${i.liked ? "is-done" : ""}" href="${h(web)}" target="_blank" rel="noopener noreferrer" data-cola-like="${h(i.id)}">👍 ${i.liked ? "Seguido" : "Seguir y dar like"}</a>` : ""}
        ${video ? `<a class="vp-btn vp-cola-btn" href="${h(video)}" download data-cola-video="${h(video)}" data-cola-name="${h(i.name)}">📥 Guardar video</a>` : ""}
        <button class="vp-btn vp-cola-btn" type="button" data-cola-copy="${h(i.id)}">📋 Copiar</button>
        ${web ? `<a class="vp-btn vp-cola-btn" href="${h(web)}" target="_blank" rel="noopener noreferrer" data-cola-open="${h(app)}">📲 Abrir perfil</a>` : ""}
        <button class="vp-btn vp-cola-btn vp-cola-sent" type="button" data-cola-act="enviado" data-cola-id="${h(i.id)}" ${model.busy === String(i.id) ? "disabled" : ""}>✅ Enviado</button>
        <button class="vp-btn vp-cola-btn vp-cola-more" type="button" data-cola-menu="${h(i.id)}" aria-expanded="${menuOpen}" aria-label="Más opciones">⋯</button>
      </div>
      ${menuOpen ? `<div class="vp-cola-menu" role="menu">
        <button class="vp-btn" type="button" role="menuitem" data-cola-act="saltar" data-cola-id="${h(i.id)}">⏭ Saltar (vuelve mañana)</button>
        <button class="vp-btn ${confirm ? "vp-btn-danger" : ""}" type="button" role="menuitem" data-cola-act="bloquear" data-cola-id="${h(i.id)}">${confirm ? "🚫 Confirmar: no contactar nunca (todos los canales)" : "🚫 No contactar"}</button>
      </div>` : ""}
    </article>`;
  }

  function archived(i) {
    const label = i.no_contactar ? "no contactar" : i.status === "enviado" ? `enviado ${h(hora(i.sent_at))}` : i.status === "saltado" ? "saltado · vuelve mañana" : h(i.status);
    return `<article class="vp-cola-archived ${i.status === "enviado" ? "is-sent" : ""}" data-cola-card="${h(i.id)}">
      <span>${i.status === "enviado" ? "✓" : "·"} <b>${h(i.name)}</b> · ${label}</span>
      ${i.status === "enviado" ? (i.replied ? `<span class="vp-cola-replied">💬 Respondió</span>`
        : `<button class="vp-btn vp-btn-sm" type="button" data-cola-act="respondio" data-cola-id="${h(i.id)}">💬 Respondió</button>`) : `<span>archivado</span>`}
    </article>`;
  }

  function list() {
    const rows = items(model.tab);
    if (!rows.length) {
      const empty = model.tab === "archivados" ? "Todavía no hay nada archivado hoy." : model.tab === "seguimientos" ? "Hoy no hay seguimientos."
        : (model.data && model.data.motivo === "fin_de_semana") ? "Fin de semana: la cola vuelve el lunes." : (model.data && model.data.motivo === "festivo") ? "Festivo: hoy no se escribe."
        : "Nada pendiente. ¡Cola al día! 🎉";
      return `<div class="vp-empty">${h(empty)}</div>`;
    }
    return model.tab === "archivados" ? `<div class="vp-cola-list">${rows.map(archived).join("")}</div>` : `<div class="vp-cola-grid">${rows.map(card).join("")}</div>`;
  }

  function view() {
    if (model.error && !model.data) return `${header()}<div class="vp-alert" role="alert"><span>${h(model.error)}</span></div>`;
    if (!model.data) return `${header()}<p class="vp-loading">Armando la cola de hoy…</p>`;
    return `<div class="vp-cola">${header()}
      ${model.notice ? `<p class="vp-ok-text" role="status">${h(model.notice)}</p>` : ""}${model.error ? `<div class="vp-alert" role="alert"><span>${h(model.error)}</span></div>` : ""}
      ${list()}</div>`;
  }

  function root() { return (ctx && ctx.root && ctx.root()) || null; }
  const active = () => ctx && (!ctx.active || ctx.active());
  function draw() { const r = root(); if (r && active()) r.innerHTML = view(); }

  async function load() {
    try { model.data = await api.cola(); model.error = ""; } catch (e) { model.error = e.message; }
    setBadge(Number((model.data && model.data.por_enviar) || 0));
    draw();
  }

  // ------------------------------------------------------------ acciones
  async function copy(text) {
    try { await navigator.clipboard.writeText(text); return true; } catch (_) {
      try {
        const ta = document.createElement("textarea"); ta.value = text; ta.setAttribute("readonly", ""); ta.className = "vp-cola-copybuf";
        document.body.appendChild(ta); ta.select(); const ok = document.execCommand("copy"); ta.remove(); return ok;
      } catch (__) { return false; }
    }
  }
  const isPhone = () => /Android|iPhone|iPad|iPod/i.test((typeof navigator !== "undefined" && navigator.userAgent) || "");

  async function saveVideo(url, name) {
    // En el celular, compartir el archivo deja "Guardar video" (queda en la galería para adjuntarlo); si no se puede, descarga.
    try {
      if (isPhone() && navigator.canShare) {
        const blob = await (await fetch(url, { credentials: "same-origin" })).blob();
        const file = new File([blob], url.split("/").pop(), { type: "video/mp4" });
        if (navigator.canShare({ files: [file] })) { await navigator.share({ files: [file], title: name }); return true; }
      }
    } catch (_) { /* cae a la descarga */ }
    return false;
  }

  async function act(id, accion) {
    model.busy = String(id); model.menu = ""; model.confirm = ""; draw();
    try {
      const r = await api.accion(id, accion);
      model.notice = r.mensaje || ""; model.error = r.ok ? "" : (r.mensaje || "No se pudo.");
      if (r.ok && accion !== "respondio") {
        model.leaving = String(id); model.busy = ""; draw();   // animación corta: la tarjeta se va a Archivados
        await new Promise((res) => setTimeout(res, 320));
        model.leaving = "";
      }
    } catch (e) { model.error = e.message; }
    model.busy = "";
    await load();
  }

  async function onClick(event) {
    if (!active()) return;
    const t = event.target;
    if (!t || !t.closest) return;
    const tab = t.closest("[data-cola-tab]");
    if (tab) { model.tab = tab.getAttribute("data-cola-tab"); model.menu = ""; draw(); return; }
    const copyBtn = t.closest("[data-cola-copy]");
    if (copyBtn) {
      const it = [...items("pendientes"), ...items("seguimientos")].find((x) => String(x.id) === copyBtn.getAttribute("data-cola-copy"));
      model.notice = it && (await copy(it.text)) ? "📋 Texto copiado: pégalo en el chat." : "No pude copiar: mantén presionado el texto para copiarlo.";
      draw(); return;
    }
    const open = t.closest("[data-cola-open]");
    if (open) {
      const app = safeApp(open.getAttribute("data-cola-open"));
      if (app && isPhone()) {   // abre la app; si no está instalada, sigue la URL web del enlace
        event.preventDefault();
        const web = open.getAttribute("href");
        const started = Date.now();
        window.location.href = app;
        setTimeout(() => { if (document.visibilityState !== "hidden" && Date.now() - started < 2500) window.open(web, "_blank", "noopener"); }, 1200);
      }
      return;
    }
    const like = t.closest("[data-cola-like]");
    if (like) { api.accion(like.getAttribute("data-cola-like"), "like").then(load).catch(() => {}); return; }   // el enlace abre el perfil
    const vid = t.closest("[data-cola-video]");
    if (vid) { if (await saveVideo(vid.getAttribute("data-cola-video"), vid.getAttribute("data-cola-name"))) event.preventDefault(); return; }
    const menu = t.closest("[data-cola-menu]");
    if (menu) { const id = menu.getAttribute("data-cola-menu"); model.menu = model.menu === id ? "" : id; model.confirm = ""; draw(); return; }
    const a = t.closest("[data-cola-act]");
    if (a) {
      const id = a.getAttribute("data-cola-id");
      const accion = a.getAttribute("data-cola-act");
      if (accion === "bloquear" && model.confirm !== id) { model.confirm = id; draw(); return; }
      await act(id, accion);
    }
  }

  window.CxConsoleSections = window.CxConsoleSections || {};
  window.CxConsoleSections.cola = {
    mount(context) {
      ctx = context;
      if (!bound && typeof document.addEventListener === "function") { document.addEventListener("click", onClick); bound = true; }
      model.notice = ""; draw(); load();
      // en el celular el menú va arriba: la vista baja directo a la cola (p. ej. desde "Abrir la cola" de Telegram)
      const r = root();
      if (r && r.scrollIntoView && window.innerWidth && window.innerWidth < 860) { try { r.scrollIntoView({ block: "start" }); } catch (_) {} }
    },
  };
  // el contador del menú se llena al abrir la consola (y cada 5 minutos)
  if (typeof window !== "undefined" && typeof document !== "undefined" && document.querySelectorAll) {
    refreshBadge();
    if (window.setInterval) window.setInterval(refreshBadge, 300000);
  }
  window.CxConsoleCola = { model, api, view, card, archived, list, header, setBadge, refreshBadge, load, act, onClick, TABS };
})();
