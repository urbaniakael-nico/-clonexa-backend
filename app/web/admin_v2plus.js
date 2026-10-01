// Consola v2+ · Centro de mando. Consume SOLO /admin-v2/api/overview (misma
// sesión de Admin V2), se refresca cada 60 s y con "Refrescar". Las funciones
// de dibujo son puras (reciben el overview y devuelven HTML) para probarlas.
(() => {
  "use strict";

  const OVERVIEW_URL = "/admin-v2/api/overview";
  const REFRESH_MS = 60000;
  const STATES = {
    operando: { label: "Operando", chip: "Operando" },
    // Activa que no operó hoy pero sí en los últimos 7 días (no es "inactiva").
    sin_operacion_hoy: { label: "Sin operación hoy", chip: "Sin operación hoy" },
    dormida: { label: "Dormida", chip: "Dormidas" },
    riesgo: { label: "En riesgo", chip: "En riesgo" },
    inactiva: { label: "Inactiva", chip: "Inactivas" },
  };
  const FILTERS = ["todas", "operando", "sin_operacion_hoy", "dormida", "riesgo", "inactiva"];
  const VIEWS = {
    command: "Centro de mando", companies: "Empresas", switches: "Interruptores", access: "Accesos y sesiones",
    catalog: "Catálogo", billing: "Facturación", health: "Salud y seguridad", audit: "Auditoría", landing: "Landing",
  };

  const state = { overview: null, filter: "todas", view: "command", error: "", loading: false, updatedAt: null };

  // ------------------------------------------------------------ utilidades
  function h(value) {
    return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  }

  function money(value) {
    const n = Math.round(Number(value || 0));
    try { return `$${n.toLocaleString("es-CO")}`; } catch (_) { return `$${n}`; }
  }

  function initials(name) {
    const words = String(name || "").trim().split(/\s+/).filter(Boolean);
    return ((words[0] || "?")[0] + (words[1] ? words[1][0] : "")).toUpperCase();
  }

  function since(iso, now = Date.now()) {
    const t = Date.parse(iso || "");
    if (!Number.isFinite(t)) return "Sin señales";
    const minutes = Math.max(0, Math.round((now - t) / 60000));
    if (minutes < 1) return "Ahora";
    if (minutes < 60) return `Hace ${minutes} min`;
    const hours = Math.round(minutes / 60);
    if (hours < 24) return `Hace ${hours} h`;
    return `Hace ${Math.round(hours / 24)} d`;
  }

  function companies(overview) {
    return overview && Array.isArray(overview.companies) ? overview.companies : [];
  }

  function counts(overview) {
    const list = companies(overview);
    const out = { todas: list.length, operando: 0, sin_operacion_hoy: 0, dormida: 0, riesgo: 0, inactiva: 0 };
    list.forEach((c) => { if (out[c.state] !== undefined) out[c.state] += 1; });
    return out;
  }

  function filtered(overview, filter) {
    const list = companies(overview);
    return filter && filter !== "todas" ? list.filter((c) => c.state === filter) : list;
  }

  // ------------------------------------------------------------ dibujo
  function alertBand(overview) {
    const mode = overview && overview.master_access_mode;
    if (!mode || mode === "bcrypt") return "";
    const detail = mode === "sha256_legacy"
      ? "El acceso maestro usa SHA-256 sin sal. Genera el hash con scripts/admin_v2_hash.py y define CLONEXA_ADMIN_V2_PASSWORD_BCRYPT en Railway."
      : "El acceso maestro no tiene clave configurada. Define CLONEXA_ADMIN_V2_PASSWORD_BCRYPT en Railway.";
    return `<div class="vp-alert" role="alert" data-vp-alert><strong>⚠ ACCESO MAESTRO SIN BCRYPT</strong><span>${h(detail)}</span></div>`;
  }

  function cards(overview) {
    const t = (overview && overview.totals) || {};
    const card = (cls, label, value, note) => `
      <div class="vp-panel vp-card ${cls}"><span>${h(label)}</span><strong>${h(value)}</strong>${note ? `<small>${h(note)}</small>` : ""}</div>`;
    return `<section class="vp-cards" aria-label="Resumen de hoy">
      ${card("vp-card-sales", "Ventas hoy", money(t.sales_today_total), "Todo Clonexa")}
      ${card("vp-card-ok", "Operando hoy", t.operating_today || 0, "Con venta u operación real")}
      ${card("vp-card-dormant", "Dormidas", t.dormant || 0, "Más de 7 días sin señal")}
      ${card("vp-card-risk", "En riesgo", t.at_risk || 0, "Requieren atención")}
      ${card("", "Sesiones abiertas", t.open_sessions || 0, "En todas las empresas")}
    </section>`;
  }

  function chips(overview, filter) {
    const n = counts(overview);
    return `<div class="vp-chips" role="group" aria-label="Filtrar empresas">
      ${FILTERS.map((key) => `<button class="vp-chip ${filter === key ? "is-active" : ""}" type="button" data-vp-filter="${key}" aria-pressed="${filter === key}">${h(key === "todas" ? "Todas" : STATES[key].chip)}<b>${h(n[key])}</b></button>`).join("")}
    </div>`;
  }

  function companyRow(c, now) {
    const st = STATES[c.state] || STATES.inactiva;
    return `<tr data-vp-company="${h(c.id)}">
      <td><div class="vp-company"><span class="vp-initials" aria-hidden="true">${h(initials(c.name))}</span><span><b>${h(c.name)}</b><small>${h(c.slug)}</small></span></div></td>
      <td><span class="vp-state"><span class="vp-dot vp-dot-${h(c.state)}" aria-hidden="true"></span><span><b>${h(st.label)}</b><br><small class="vp-mono-muted">${h(c.state_reason || "")}</small></span></span></td>
      <td>${h(c.plan || "—")}</td>
      <td class="vp-mono">${h(c.modules_enabled || 0)}</td>
      <td class="vp-mono">${h(money(c.sales_today_total))}</td>
      <td class="vp-mono" title="${h(c.last_real_signal_at || "")}">${h(since(c.last_real_signal_at, now))}</td>
      <td><div class="vp-actions">
        <a class="vp-btn vp-btn-sm" href="/admin-v2?company_id=${encodeURIComponent(c.id)}">Ficha</a>
        <a class="vp-btn vp-btn-sm" href="/client?company_id=${encodeURIComponent(c.id)}" target="_blank" rel="noopener">Entrar como empresa</a>
      </div></td>
    </tr>`;
  }

  function table(overview, filter, now = Date.now()) {
    const all = companies(overview);
    const rows = filtered(overview, filter);
    if (!all.length) return `<div class="vp-empty" data-vp-empty>Aún no hay empresas activas en Clonexa.</div>`;
    if (!rows.length) return `<div class="vp-empty" data-vp-empty>Ninguna empresa en este estado.</div>`;
    return `<div class="vp-table-wrap"><table class="vp-table">
      <thead><tr><th>Empresa</th><th>Estado</th><th>Plan</th><th>Módulos</th><th>Ventas hoy</th><th>Última señal real</th><th><span class="sr-only">Acciones</span></th></tr></thead>
      <tbody>${rows.map((c) => companyRow(c, now)).join("")}</tbody>
    </table></div>`;
  }

  function actions(overview) {
    const items = [];
    const mode = overview && overview.master_access_mode;
    if (mode && mode !== "bcrypt") items.push({ kind: "critical", title: "Acceso maestro sin bcrypt", detail: "Define CLONEXA_ADMIN_V2_PASSWORD_BCRYPT en Railway." });
    companies(overview).filter((c) => c.state === "riesgo").forEach((c) => items.push({ kind: "risk", title: c.name, detail: c.state_reason }));
    companies(overview).filter((c) => c.state === "dormida").forEach((c) => items.push({ kind: "dormant", title: c.name, detail: `Dormida · ${c.state_reason}` }));
    const list = items.length
      ? `<ul class="vp-actions-list">${items.map((i) => `<li class="vp-action vp-action-${i.kind}"><b>${h(i.title)}</b><small>${h(i.detail || "")}</small></li>`).join("")}</ul>`
      : `<div class="vp-empty">Nada pendiente. Todo en orden.</div>`;
    return `<aside class="vp-panel vp-section" data-vp-actions><h2>Requiere acción</h2>${list}</aside>`;
  }

  function commandCenter(overview, filter = "todas", options = {}) {
    const now = options.now || Date.now();
    const updated = options.updatedAt ? `Actualizado ${new Date(options.updatedAt).toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" })}` : "";
    return `
      <header class="vp-head">
        <div><p class="vp-eyebrow">SISTEMA OPERATIVO EMPRESARIAL · NÚCLEO CLONEXA</p><h1 class="vp-title">Centro de mando</h1></div>
        <div class="vp-head-actions">
          <button class="vp-btn vp-btn-search" type="button" data-vp-search><span>Buscar u ordenar…</span><span class="vp-kbd">Ctrl K</span></button>
          <button class="vp-btn" type="button" data-vp-refresh>Refrescar</button>
          <a class="vp-btn vp-btn-primary" href="/admin-v2">+ Nueva empresa</a>
          ${updated ? `<span class="vp-updated">${h(updated)}</span>` : ""}
        </div>
      </header>
      ${options.error ? `<div class="vp-alert" role="alert"><strong>No se pudo actualizar</strong><span>${h(options.error)}</span></div>` : ""}
      ${alertBand(overview)}
      ${cards(overview)}
      <div class="vp-grid">
        <section class="vp-panel vp-section" aria-label="Pulso de empresas">
          <h2>Pulso de empresas</h2>
          ${chips(overview, filter)}
          <div data-vp-table>${table(overview, filter, now)}</div>
        </section>
        ${actions(overview)}
      </div>`;
  }

  function soon(view) {
    return `<section class="vp-panel vp-soon"><h2>${h(VIEWS[view] || "Sección")}</h2><p>Próximamente. Mientras tanto, esta función sigue en Admin V2.</p>
      <a class="vp-btn" href="/admin-v2">Abrir Admin V2</a></section>`;
  }

  // ------------------------------------------------------------ app
  function main() { return document.getElementById("vpMain"); }

  function render() {
    const root = main();
    if (!root) return;
    if (state.view !== "command") { root.innerHTML = soon(state.view); return; }
    if (!state.overview) {
      root.innerHTML = state.error ? `<div class="vp-alert" role="alert"><strong>No se pudo cargar</strong><span>${h(state.error)}</span></div>` : `<p class="vp-loading">Cargando el Centro de mando…</p>`;
      return;
    }
    root.innerHTML = commandCenter(state.overview, state.filter, { updatedAt: state.updatedAt, error: state.error });
  }

  function toast(message) {
    const old = document.querySelector(".vp-toast");
    if (old) old.remove();
    const el = document.createElement("div");
    el.className = "vp-toast";
    el.setAttribute("role", "status");
    el.textContent = message;
    document.body.appendChild(el);
    window.setTimeout(() => el.remove(), 3500);
  }

  async function load() {
    if (state.loading) return;
    state.loading = true;
    try {
      const response = await fetch(OVERVIEW_URL, { credentials: "same-origin", headers: { Accept: "application/json" } });
      const type = response.headers.get("content-type") || "";
      if (response.status === 401 || response.redirected || !type.includes("application/json")) {
        window.location.href = "/admin-v2/login";
        return;
      }
      if (!response.ok) throw new Error(`Respuesta ${response.status}`);
      state.overview = await response.json();
      state.updatedAt = Date.now();
      state.error = "";
    } catch (error) {
      state.error = (error && error.message) || "Sin conexión.";
    } finally {
      state.loading = false;
      render();
    }
  }

  function onClick(event) {
    const target = event.target;
    if (!target || !target.closest) return;
    const nav = target.closest("[data-vp-view]");
    if (nav) {
      state.view = nav.getAttribute("data-vp-view") || "command";
      document.querySelectorAll("[data-vp-view]").forEach((b) => b.classList.toggle("is-active", b === nav));
      render();
      return;
    }
    const chip = target.closest("[data-vp-filter]");
    if (chip) { state.filter = chip.getAttribute("data-vp-filter") || "todas"; render(); return; }
    if (target.closest("[data-vp-refresh]")) { load(); return; }
    if (target.closest("[data-vp-search]")) toast("El panel de órdenes (Ctrl K) llega en la fase 2.");
  }

  function start() {
    document.addEventListener("click", onClick);
    document.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && String(event.key).toLowerCase() === "k") {
        event.preventDefault();
        toast("El panel de órdenes (Ctrl K) llega en la fase 2.");
      }
    });
    load();
    window.setInterval(load, REFRESH_MS);
  }

  window.CxConsolePlus = { commandCenter, table, chips, cards, alertBand, actions, filtered, counts, initials, since, money, soon, state };
  if (document.getElementById && document.getElementById("vpMain")) start();
})();
