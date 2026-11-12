// Consola v2+ · Empresas -> detalle -> "Módulos y mini paneles": tarjeta NEGOCIO EN VIVO 3D (módulo live3d), debajo de
// Mini paneles. Interruptor con auditoría, vista previa del piso, plantilla, privacidad, quién lo ve, modo TV, modo
// liviano, consumo medido y botones (abrir como el cliente, editar distribución, personajes, apagar).
// La configuración es la MISMA fila de la Oficina 3D (una sola fuente): lo que se cambia aquí se ve en la oficina.
(() => {
  "use strict";

  const API = (cid) => `/admin-v2/api/companies/${encodeURIComponent(cid)}/live3d`;
  const state = new Map();   // company_id -> {data, busy, msg, preview}

  function h(v) { return String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;"); }
  async function req(url, opts = {}) {
    const r = await fetch(url, { credentials: "same-origin", ...opts, headers: { "Content-Type": "application/json", Accept: "application/json", ...(opts.headers || {}) } });
    const data = await r.json().catch(() => ({}));
    if (r.status === 401) { window.location.href = "/admin-v2plus/login"; throw new Error("Sesión vencida."); }
    if (!r.ok) throw new Error((data && typeof data.detail === "string" && data.detail) || `Respuesta ${r.status}`);
    return data;
  }
  // ===== reglas puras (tests/admin_v2plus_live3d.test.cjs) =====
  function usageText(u) {
    if (!u) return "—";
    const gb = Number(u.month_bytes || 0) / 1024 ** 3;
    const vol = gb >= 0.1 ? `${gb.toFixed(1).replace(".", ",")} GB` : `${(Number(u.month_bytes || 0) / 1024 ** 2).toFixed(1).replace(".", ",")} MB`;
    const n = Number(u.screens || 0);
    return `${n} ${n === 1 ? "pantalla abierta" : "pantallas abiertas"} · ${vol} este mes`;
  }
  function select(name, options, value) {
    return `<select data-cx3d-field="${h(name)}" aria-label="${h(name)}">${(options || []).map((o) => `<option value="${h(o.key)}" ${o.key === value ? "selected" : ""}>${h(o.label)}</option>`).join("")}</select>`;
  }
  function cardHtml(d, ui = {}) {
    if (!d) return `<div class="vp-empty">Cargando Negocio en vivo 3D…</div>`;
    const on = !!d.enabled;
    const preview = ui.preview
      ? `<img src="${h(ui.preview)}" alt="Vista previa del piso de ${h(d.name)}">`
      : `<div class="cx3d-noprev"><b>${d.has_engine ? "🏢" : "🧱"}</b><span>${d.has_engine ? "La vista previa se toma sola la primera vez que se abre el piso." : "Esta plantilla aún no tiene piso 3D."}</span></div>`;
    const roles = d.audience === "roles"
      ? `<input class="vp-search vp-input-sm" data-cx3d-field="roles" value="${h((d.roles || []).join(", "))}" placeholder="mesero, cajero, barman" aria-label="Roles que lo ven">` : "";
    return `<header class="cx3d-head"><h2>NEGOCIO EN VIVO 3D</h2><span class="cx3d-pill ${on ? "is-on" : ""}">${on ? "Encendido" : "Apagado"}</span>
        <button class="vp-switch-btn ${on ? "is-on" : ""}" type="button" role="switch" aria-checked="${on}" aria-label="${on ? "Apagar" : "Encender"} Negocio en vivo 3D" data-cx3d-toggle><span></span></button></header>
      <p class="cx3d-sub">Complemento de la mensualidad · el cliente ve su negocio en 3D con sus datos reales. Solo ve su propio piso.</p>
      <div class="cx3d-body">
        <div class="cx3d-prev">${preview}</div>
        <div class="cx3d-grid">
          <label class="cx3d-f"><span>Plantilla</span>${select("plantilla", d.options.templates, d.template)}</label>
          <label class="cx3d-f"><span>Privacidad del personal</span>${select("privacidad", d.options.privacy, d.privacy)}</label>
          <label class="cx3d-f"><span>Quién lo ve</span>${select("audience", d.options.audience, d.audience)}${roles}</label>
          <div class="cx3d-f"><span>Modo TV / pantalla completa</span><div class="cx3d-row"><b>${d.tv ? "Permitido" : "No permitido"}</b>
            <button class="vp-switch-btn ${d.tv ? "is-on" : ""}" type="button" role="switch" aria-checked="${!!d.tv}" aria-label="Modo TV" data-cx3d-tv><span></span></button></div></div>
          <label class="cx3d-f"><span>Modo liviano en celulares</span>${select("lite", d.options.lite, d.lite)}</label>
          <div class="cx3d-f"><span>Consumo</span><b data-cx3d-usage>${h(usageText(d.usage))}</b></div>
        </div>
      </div>
      ${ui.msg ? `<p class="cx3d-msg" role="status">${h(ui.msg)}</p>` : ""}
      <div class="vp-actions cx3d-actions">
        <button class="vp-btn vp-btn-primary" type="button" data-cx3d-open ${d.has_engine ? "" : "disabled"}>Abrir como el cliente</button>
        <a class="vp-btn" href="/admin-v2plus/oficina?piso=${encodeURIComponent(d.company_id)}&arquitecto=1" target="_blank" rel="noopener" data-cx3d-arch>Editar distribución (arquitecto)</a>
        <a class="vp-btn" href="/admin-v2plus/oficina?piso=${encodeURIComponent(d.company_id)}&personajes=1" target="_blank" rel="noopener" data-cx3d-chars>Personajes del negocio</a>
        <button class="vp-btn" type="button" data-cx3d-toggle>${on ? "Apagar" : "Encender"}</button>
      </div>`;
  }
  function bodyFor(field, value, d) {
    if (field === "roles") return { roles: String(value || "").split(/[,\n]/).map((x) => x.trim()).filter(Boolean) };
    if (field === "tv") return { tv: !d.tv };
    if (field === "toggle") return { enabled: !d.enabled };
    return { [field]: value };
  }
  // ===== fin reglas puras =====

  function paint(el) {
    const cid = el.getAttribute("data-cx3d");
    const st = state.get(cid) || {};
    el.innerHTML = cardHtml(st.data, st);
  }
  async function load(el) {
    const cid = el.getAttribute("data-cx3d");
    el.setAttribute("data-cx3d-loaded", "1");
    const st = state.get(cid) || {};
    state.set(cid, st);
    try { st.data = await req(API(cid)); } catch (e) { el.innerHTML = `<div class="vp-empty">No se pudo cargar Negocio en vivo 3D: ${h(e.message)}</div>`; return; }
    paint(el);
    loadPreview(el, cid);
  }
  async function loadPreview(el, cid) {
    // la CSP de la consola no admite blob: la imagen se pide por su ruta (misma sesión, caché de 5 min)
    const st = state.get(cid);
    const url = `${API(cid)}/vista.jpg?t=${Math.floor(Date.now() / 300000)}`;
    try {
      const r = await fetch(url, { credentials: "same-origin" });
      if (!r.ok) return;
      st.preview = url;
      paint(el);
    } catch (_) { /* sin imagen */ }
  }
  async function save(el, body, note) {
    const cid = el.getAttribute("data-cx3d");
    const st = state.get(cid) || {};
    try {
      st.data = await req(API(cid), { method: "PUT", body: JSON.stringify(body), headers: note ? { "X-Cx-Audit-Note": note } : {} });
      st.msg = "Guardado ✓";
    } catch (e) { st.msg = e.message || "No se pudo guardar."; }
    paint(el);
  }

  document.addEventListener("change", (e) => {
    const f = e.target.closest("[data-cx3d] [data-cx3d-field]");
    if (!f) return;
    const el = f.closest("[data-cx3d]");
    const d = (state.get(el.getAttribute("data-cx3d")) || {}).data;
    if (d) save(el, bodyFor(f.getAttribute("data-cx3d-field"), f.value, d));
  });
  document.addEventListener("click", async (e) => {
    const el = e.target.closest("[data-cx3d]");
    if (!el) return;
    const d = (state.get(el.getAttribute("data-cx3d")) || {}).data;
    if (!d) return;
    if (e.target.closest("[data-cx3d-toggle]")) { save(el, bodyFor("toggle", null, d), `${d.enabled ? "Apaga" : "Enciende"} Negocio en vivo 3D`); return; }
    if (e.target.closest("[data-cx3d-tv]")) { save(el, bodyFor("tv", null, d)); return; }
    if (e.target.closest("[data-cx3d-open]")) {
      const win = window.open("about:blank", "_blank");
      try { const r = await req(`${API(d.company_id)}/abrir`, { method: "POST", body: "{}" }); if (win) { win.opener = null; win.location.href = r.url; } else window.location.href = r.url; }
      catch (err) { if (win) win.close(); const st = state.get(d.company_id); st.msg = err.message; paint(el); }
    }
  });
  // la ficha de empresa se vuelve a dibujar a menudo: cada tarjeta nueva se llena sola (y se refresca el consumo)
  const fill = () => document.querySelectorAll("[data-cx3d]").forEach((el) => {
    if (!el.hasAttribute("data-cx3d-loaded")) load(el);
    else if (!el.firstElementChild) paint(el);
  });
  new MutationObserver(fill).observe(document.documentElement, { childList: true, subtree: true });
  setInterval(() => document.querySelectorAll("[data-cx3d][data-cx3d-loaded]").forEach(async (el) => {
    const cid = el.getAttribute("data-cx3d"); const st = state.get(cid);
    if (!st || !st.data || document.hidden) return;
    try { const fresh = await req(API(cid)); st.data.usage = fresh.usage; const u = el.querySelector("[data-cx3d-usage]"); if (u) u.textContent = usageText(fresh.usage); } catch (_) {}
  }), 30000);

  window.CxLive3dCard = {
    html: (cid) => `<section class="vp-panel vp-section cx3d-card" aria-label="Negocio en vivo 3D" data-cx3d="${h(cid)}"${(state.get(cid) || {}).data ? ' data-cx3d-loaded="1"' : ""}>${cardHtml((state.get(cid) || {}).data, state.get(cid) || {})}</section>`,
    _pure: { usageText, cardHtml, bodyFor },
  };
})();
