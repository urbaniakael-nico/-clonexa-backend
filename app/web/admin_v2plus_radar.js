// Consola v2+ · Radar · Innovación (NEXUS), solo Admin V2. Una sola fuente: el backend (/api/v1/radar/admin).
// Tablero por estado (Nuevas / Me interesa / Backlog / En curso / Hechas), lista con filtros por estado y categoría,
// notas, abrir la fuente, historial de informes con su costo, temas que vigila (agregar, editar, apagar) y
// "Generar informe ahora" (mismo tope diario que Telegram). Lo que cambia aquí edita el mensaje en NEXUS.
// Sin estilos en línea (CSP de v2+): todo por clase. Todo escapado.
(() => {
  "use strict";

  const API = "/api/v1/radar/admin";
  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const STATES = { nueva: "Nueva", me_interesa: "⭐ Me interesa", backlog: "🗂 Backlog", en_curso: "En curso", hecha: "Hecha", descartada: "✖ Descartada" };
  const BOARD = [["nueva", "Nuevas"], ["me_interesa", "Me interesa"], ["backlog", "Backlog"], ["en_curso", "En curso"], ["hecha", "Hechas"]];
  const CATS = { herramientas: "Herramientas y APIs", competencia: "Competencia", fondos: "Fondos y convocatorias", normas: "Leyes y normas", nichos: "Ideas por nicho", otra: "Otra" };
  const LV = { alto: "alto", medio: "medio", bajo: "bajo" };
  const TABS = [["tablero", "Tablero"], ["lista", "Lista"], ["informes", "Informes"], ["temas", "Temas que vigila"]];

  async function request(url, options = {}) {
    const response = await fetch(url, { credentials: "same-origin", ...options,
      headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) } });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401) { window.location.href = "/admin-v2plus/login"; throw new Error("Sesión vencida."); }
    if (!response.ok) throw new Error((data && typeof data.detail === "string" && data.detail) || `Respuesta ${response.status}`);
    return data;
  }
  const ideasUrl = (f = {}) => { const p = new URLSearchParams(); if (f.estado) p.set("estado", f.estado); if (f.categoria) p.set("categoria", f.categoria); const qs = p.toString(); return `${API}/ideas${qs ? `?${qs}` : ""}`; };
  const api = {
    ideas: (f) => request(ideasUrl(f)),
    patch: (id, body) => request(`${API}/ideas/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(body) }),
    informes: () => request(`${API}/informes`),
    temas: () => request(`${API}/temas`),
    tema: (t) => request(t.id ? `${API}/temas/${encodeURIComponent(t.id)}` : `${API}/temas`, { method: t.id ? "PUT" : "POST", body: JSON.stringify({ nombre: t.nombre, descripcion: t.descripcion, activo: t.activo !== false }) }),
    generar: (tema) => request(`${API}/generar`, { method: "POST", body: JSON.stringify({ tema: tema || "" }) }),
  };

  const model = { tab: "tablero", filters: { estado: "", categoria: "" }, ideas: null, counts: {}, informes: null, temas: null,
    notesOpen: "", notice: "", error: "", busy: false, tema: "" };
  let ctx = null;
  let bound = false;

  const safeUrl = (u) => (/^https?:\/\/[^\s"'<>]+$/i.test(String(u || "")) ? String(u) : "");
  const money = (v) => `US$${Number(v || 0).toFixed(2)}`;
  const fecha = (iso) => { if (!iso) return "—"; try { return new Date(iso).toLocaleString("es-CO", { timeZone: "America/Bogota", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }); } catch (_) { return String(iso).slice(0, 16); } };

  // ------------------------------------------------------------ vistas
  function sourceLink(i) {
    const f = arr(i.fuentes)[0] || {};
    const u = safeUrl(f.url);
    return u ? `<a class="vp-rx-src" href="${h(u)}" target="_blank" rel="noopener noreferrer">📎 ${h(f.titulo || f.url)}</a><small>${h(f.fecha || "")}</small>` : `<small>Sin fuente</small>`;
  }
  function stateSelect(i) {
    return `<select class="vp-rx-state" data-rx-state="${h(i.id)}" aria-label="Estado de la idea">${Object.entries(STATES).map(([k, l]) => `<option value="${k}" ${i.estado === k ? "selected" : ""}>${h(l)}</option>`).join("")}</select>`;
  }
  function notes(i) {
    if (model.notesOpen !== String(i.id)) return i.notas ? `<p class="vp-rx-notes">📝 ${h(i.notas)}</p>` : "";
    return `<form class="vp-rx-noteform" data-rx-notes="${h(i.id)}"><textarea name="notas" maxlength="2000" rows="3" aria-label="Notas">${h(i.notas || "")}</textarea>
      <div class="vp-actions"><button class="vp-btn vp-btn-sm vp-btn-primary" type="submit">Guardar notas</button><button class="vp-btn vp-btn-sm" type="button" data-rx-notes-cancel>Cancelar</button></div></form>`;
  }
  function card(i) {
    return `<article class="vp-rx-card is-${h(i.estado)}">
      <div class="vp-row-between"><b class="vp-rx-title">${h(i.titulo)}</b><span class="vp-rx-score" title="Puntaje">${h(i.puntaje)}</span></div>
      <p class="vp-rx-sum">${h(i.resumen || "")}</p>
      ${i.por_que ? `<p class="vp-rx-why"><b>Por qué nos sirve:</b> ${h(i.por_que)}</p>` : ""}
      <p class="vp-rx-meta">${h(CATS[i.categoria] || i.categoria || "")} · Impacto ${h(LV[i.impacto] || i.impacto)} · Esfuerzo ${h(LV[i.esfuerzo] || i.esfuerzo)} · Costo ${h(LV[i.costo] || i.costo)}${i.costo_estimado ? ` (${h(i.costo_estimado)})` : ""}${i.fecha_limite ? ` · ⏳ cierra ${h(i.fecha_limite)}` : ""}</p>
      <div class="vp-rx-src-row">${sourceLink(i)}</div>
      ${notes(i)}
      <div class="vp-actions">${stateSelect(i)}<button class="vp-btn vp-btn-sm" type="button" data-rx-notes-open="${h(i.id)}">📝 Notas</button></div>
    </article>`;
  }
  function board() {
    const items = arr(model.ideas);
    return `<div class="vp-rx-board">${BOARD.map(([k, l]) => { const col = items.filter((i) => i.estado === k);
      return `<section class="vp-panel vp-rx-col" aria-label="${h(l)}"><h3>${h(l)} <b>${h(model.counts[k] || 0)}</b></h3>${col.length ? col.map(card).join("") : `<p class="vp-empty">Sin ideas aún</p>`}</section>`; }).join("")}</div>`;
  }
  function list() {
    const f = model.filters;
    const opt = (v, l, cur) => `<option value="${h(v)}" ${String(cur) === String(v) ? "selected" : ""}>${h(l)}</option>`;
    const items = arr(model.ideas);
    return `<form class="vp-panel vp-section vp-form-grid vp-rx-filters" data-rx-filters>
        <label class="vp-field">Estado<select name="estado">${opt("", "Todos", f.estado)}${Object.entries(STATES).map(([k, l]) => opt(k, l, f.estado)).join("")}</select></label>
        <label class="vp-field">Categoría<select name="categoria">${opt("", "Todas", f.categoria)}${Object.entries(CATS).map(([k, l]) => opt(k, l, f.categoria)).join("")}</select></label>
        <div class="vp-actions"><button class="vp-btn vp-btn-primary" type="submit">Filtrar</button></div></form>
      <div class="vp-rx-list">${items.length ? items.map(card).join("") : `<div class="vp-empty">Sin ideas aún</div>`}</div>`;
  }
  function informes() {
    const d = model.informes;
    if (!d) return `<p class="vp-loading">Cargando informes…</p>`;
    const rows = arr(d.informes);
    return `<section class="vp-panel vp-section"><h3>Historial de informes</h3>
      <p class="vp-login-hint">A pedido hoy: ${h(d.a_pedido_hoy)} de ${h(d.tope_diario)} · costo total de la lista: ${h(money(d.costo_total_usd))}</p>
      ${rows.length ? `<div class="vpm-table-wrap"><table class="vpm-table"><thead><tr><th>#</th><th>Fecha</th><th>Tipo</th><th>Tema</th><th>Estado</th><th>Ideas</th><th>Descartadas</th><th>Búsquedas</th><th>Tokens</th><th>Costo</th></tr></thead>
      <tbody>${rows.map((r) => `<tr><td>${h(r.id)}</td><td>${h(fecha(r.created_at))}</td><td>${r.tipo === "semanal" ? "Semanal" : "A pedido"}</td><td>${h(r.tema || "—")}</td>
        <td class="vp-rx-st is-${h(r.estado)}">${h(r.estado)}${r.error ? ` · ${h(r.error)}` : ""}</td><td>${h(r.n_ideas)}</td><td>${h(r.descartadas)}</td><td>${h(r.busquedas)}</td>
        <td>${h(Number(r.tokens_in || 0) + Number(r.tokens_out || 0))}</td><td class="vp-mono">${h(money(r.costo_usd))}</td></tr>`).join("")}</tbody></table></div>` : `<div class="vp-empty">Aún no hay informes.</div>`}</section>`;
  }
  function temas() {
    const ts = model.temas;
    if (!ts) return `<p class="vp-loading">Cargando temas…</p>`;
    return `<section class="vp-panel vp-section"><h3>Temas que vigila NEXUS</h3>
      <div class="vp-rx-temas">${ts.map((t) => `<form class="vp-rx-tema ${t.activo ? "" : "is-off"}" data-rx-tema="${h(t.id)}">
        <label class="vp-field">Tema<input name="nombre" required minlength="3" maxlength="120" value="${h(t.nombre)}"></label>
        <label class="vp-field">Qué vigila<textarea name="descripcion" maxlength="600" rows="2">${h(t.descripcion)}</textarea></label>
        <label class="vp-rx-check"><input type="checkbox" name="activo" ${t.activo ? "checked" : ""}> Encendido</label>
        <button class="vp-btn vp-btn-sm" type="submit">Guardar</button></form>`).join("")}</div>
      <form class="vp-rx-tema is-new" data-rx-tema="">
        <label class="vp-field">Tema nuevo<input name="nombre" required minlength="3" maxlength="120" placeholder="Ej: Pagos con QR en Colombia"></label>
        <label class="vp-field">Qué vigila<textarea name="descripcion" maxlength="600" rows="2"></textarea></label>
        <input type="hidden" name="activo" value="on"><button class="vp-btn vp-btn-sm vp-btn-primary" type="submit">Agregar tema</button></form></section>`;
  }
  function view() {
    const c = model.counts || {};
    const nuevas = c.nueva || 0;
    const body = model.tab === "lista" ? list() : model.tab === "informes" ? informes() : model.tab === "temas" ? temas() : board();
    return `<section class="vp-rx" data-rx-root>
      <header class="vp-head"><div><p class="vp-eyebrow">INNOVACIÓN · NEXUS</p><h2 class="vp-title">Radar · Innovación</h2>
        <p class="vp-ficha-meta">${h(nuevas)} ${nuevas === 1 ? "idea nueva" : "ideas nuevas"} · informe semanal los lunes 8:00 a. m. · máximo 3 a pedido por día</p></div>
        <form class="vp-rx-generate" data-rx-generate><input name="tema" maxlength="300" placeholder="Tema (opcional)" value="${h(model.tema)}" aria-label="Tema del informe">
          <button class="vp-btn vp-btn-primary" type="submit" ${model.busy ? "disabled" : ""}>🛰️ Generar informe ahora</button></form></header>
      ${model.notice ? `<div class="vp-alert is-ok" role="status"><span>${h(model.notice)}</span></div>` : ""}
      ${model.error ? `<div class="vp-alert" role="alert"><span>${h(model.error)}</span></div>` : ""}
      <nav class="vp-rx-tabs" aria-label="Vistas del radar">${TABS.map(([k, l]) => `<button class="vp-chip ${model.tab === k ? "is-active" : ""}" type="button" data-rx-tab="${k}" aria-pressed="${model.tab === k}">${h(l)}</button>`).join("")}</nav>
      <div data-rx-body>${model.ideas === null && (model.tab === "tablero" || model.tab === "lista") ? `<p class="vp-loading">Cargando ideas…</p>` : body}</div>
    </section>`;
  }

  // ------------------------------------------------------------ datos y eventos
  function root() { return (ctx && ctx.root && ctx.root()) || null; }
  function draw() { const r = root(); if (r) r.innerHTML = view(); }
  async function loadIdeas() {
    try { const f = model.tab === "lista" ? model.filters : {}; const d = await api.ideas(f); model.ideas = arr(d.ideas); model.counts = d.counts || {}; model.error = ""; }
    catch (e) { model.error = e.message; model.ideas = model.ideas || []; }
  }
  async function loadTab() {
    if (model.tab === "informes") { try { model.informes = await api.informes(); } catch (e) { model.error = e.message; } }
    else if (model.tab === "temas") { try { model.temas = arr((await api.temas()).temas); } catch (e) { model.error = e.message; } }
    else await loadIdeas();
    draw();
  }
  const active = () => ctx && (!ctx.active || ctx.active());

  async function onClick(event) {
    if (!active()) return;
    const t = event.target;
    if (!t || !t.closest || !t.closest("[data-rx-root]")) return;
    const tab = t.closest("[data-rx-tab]");
    if (tab) { model.tab = tab.getAttribute("data-rx-tab"); model.notice = ""; loadTab(); return; }
    const no = t.closest("[data-rx-notes-open]");
    if (no) { model.notesOpen = no.getAttribute("data-rx-notes-open"); draw(); return; }
    if (t.closest("[data-rx-notes-cancel]")) { model.notesOpen = ""; draw(); }
  }
  async function onChange(event) {
    if (!active()) return;
    const t = event.target;
    if (!t || !t.matches || !t.matches("[data-rx-state]")) return;
    try { await api.patch(t.getAttribute("data-rx-state"), { estado: t.value }); model.notice = `Estado: ${STATES[t.value] || t.value} (también en NEXUS).`; }
    catch (e) { model.error = e.message; }
    await loadIdeas(); draw();
  }
  async function onSubmit(event) {
    if (!active()) return;
    const form = event.target;
    if (!form || !form.matches) return;
    const d = new FormData(form);
    if (form.matches("[data-rx-filters]")) { event.preventDefault(); model.filters = { estado: String(d.get("estado") || ""), categoria: String(d.get("categoria") || "") }; await loadIdeas(); draw(); return; }
    if (form.matches("[data-rx-notes]")) { event.preventDefault(); try { await api.patch(form.getAttribute("data-rx-notes"), { notas: String(d.get("notas") || "") }); model.notesOpen = ""; model.notice = "Notas guardadas."; } catch (e) { model.error = e.message; } await loadIdeas(); draw(); return; }
    if (form.matches("[data-rx-tema]")) {
      event.preventDefault();
      const id = form.getAttribute("data-rx-tema");
      try { await api.tema({ id: id ? Number(id) : 0, nombre: String(d.get("nombre") || "").trim(), descripcion: String(d.get("descripcion") || "").trim(), activo: Boolean(d.get("activo")) }); model.notice = id ? "Tema guardado." : "Tema agregado: NEXUS lo vigila desde el próximo informe."; }
      catch (e) { model.error = e.message === "tema_repetido" ? "Ya existe ese tema." : e.message; }
      model.temas = arr((await api.temas()).temas); draw(); return;
    }
    if (form.matches("[data-rx-generate]")) {
      event.preventDefault();
      model.tema = String(d.get("tema") || "").trim();
      model.busy = true; draw();
      try { const r = await api.generar(model.tema); model.notice = `NEXUS está investigando (${r.usados} de ${r.tope} a pedido hoy). Llega a Telegram y aparece aquí en unos minutos.`; model.error = ""; }
      catch (e) { model.error = e.message === "tope_diario" ? "Ya van 3 informes a pedido hoy: el próximo, mañana." : e.message === "n8n_no_disponible" ? "n8n no respondió: intenta de nuevo." : e.message; }
      model.busy = false; draw();
    }
  }

  window.CxConsoleSections = window.CxConsoleSections || {};
  window.CxConsoleSections.radar = {
    mount(context) {
      ctx = context;
      if (!bound && typeof document.addEventListener === "function") {
        document.addEventListener("click", onClick); document.addEventListener("change", onChange); document.addEventListener("submit", onSubmit); bound = true;
      }
      draw(); loadTab();
    },
    refreshPulse() {},
  };
  window.CxConsoleRadar = { model, api, view, board, list, informes, temas, card, ideasUrl, STATES, BOARD };
})();
