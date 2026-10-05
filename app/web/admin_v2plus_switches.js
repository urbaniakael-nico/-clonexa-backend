// Consola v2+ · Interruptores (Fase 3, parte 3). Matriz interruptores × empresas
// a partir del registro único (app/services/switch_registry.json, servido por
// GET /admin-v2/api/switches). Guardar usa el MISMO endpoint que Admin V2
// (POST /api/v1/companies/{id}/modules/{code}/activate) enviando SOLO la clave
// cambiada; el servidor mezcla settings sin tocar las demás. El motivo va a la
// auditoría en la cabecera X-Cx-Audit-Note. También: configuración QR (M05) y
// corte diario de sesiones (S01, S02) con los cuerpos de Admin V2.
// Sin estilos ni scripts en línea.
(() => {
  "use strict";

  const API = "/api/v1";
  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const fold = (v) => String(v ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const matches = (q, ...f) => { const w = fold(q).split(" ").filter(Boolean); const hay = fold(f.join(" ")); return w.every((x) => hay.includes(x) || hay.replace(/ /g, "").includes(x)); };
  const V2_WARNING = "También se cambia desde Admin V2; cámbialo solo desde aquí";

  async function request(url, options = {}) {
    const response = await fetch(url, { credentials: "same-origin", ...options, headers: { "Content-Type": "application/json", Accept: "application/json", ...(options.headers || {}) } });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401 && String(url).startsWith("/admin-v2")) { window.location.href = "/admin-v2plus/login"; throw new Error("Sesión vencida."); }
    if (!response.ok) throw new Error((data && (typeof data.detail === "string" ? data.detail : data.message)) || `Respuesta ${response.status}`);
    return data;
  }
  const auditNote = (note) => ({ "X-Cx-Audit-Note": encodeURIComponent(JSON.stringify(note)) });

  // ------------------------------------------------------------ registro
  let cache = null;
  let pending = null;
  const Registry = {
    load(force = false) {
      if (cache && !force) return Promise.resolve(cache);
      if (pending && !force) return pending;
      pending = request("/admin-v2/api/switches").then((data) => { cache = data; return data; }).finally(() => { pending = null; });
      return pending;
    },
    data: () => cache,
    list: () => (cache ? arr(cache.registry && cache.registry.switches) : []),
    get: (key) => Registry.list().find((s) => s.key === key) || null,
    // Interruptores encendidos con los módulos de UNA empresa (filas de F01).
    onFor(modules) {
      const rows = arr(modules).map((row) => { const m = row && row.module && typeof row.module === "object" ? row.module : row || {}; return { code: String(m.code || row.module_code || row.code || ""), enabled: row.enabled !== false, settings: row.settings || {} }; });
      const by = new Map(rows.map((r) => [r.code, r]));
      return Registry.list().filter((s) => { const m = by.get(s.module); return m && m.enabled && m.settings && m.settings[s.key] === true; });
    },
  };

  // ------------------------------------------------------------ reglas
  // Lo que pasa al cambiar `key` en una empresa: bloqueos, avisos y exigencias.
  function plan(sw, company, nextOn) {
    const state = (company.switches || {})[sw.key] || {};
    const out = { blocked: "", warnings: [], needsAck: false, needsName: false };
    if (nextOn && state.locked) {
      out.blocked = `No se puede encender: ${company.name} no tiene encendido ${arr(state.missing_modules).join(", ")}.`;
      return out;
    }
    if (sw.v2_form) out.warnings.push({ kind: "v2", text: V2_WARNING });
    if (!nextOn) {
      const dependents = Registry.list().filter((o) => arr(o.depends_on).some((d) => d.key === sw.key) && ((company.switches || {})[o.key] || {}).on);
      dependents.forEach((o) => { const why = arr(o.depends_on).find((d) => d.key === sw.key).why; out.warnings.push({ kind: "dep", text: `«${o.label}» está encendido y depende de este: ${why}` }); });
      out.needsAck = dependents.length > 0;
    } else {
      arr(sw.depends_on).filter((d) => !((company.switches || {})[d.key] || {}).on).forEach((d) => {
        const other = Registry.get(d.key);
        out.warnings.push({ kind: "dep", text: `Depende de «${other ? other.label : d.key}», que está apagado: ${d.why}` });
      });
    }
    if (sw.note) out.warnings.push({ kind: "note", text: sw.note });
    out.needsName = Boolean(sw.delicate) && company.kind !== "demo";
    return out;
  }

  // Guarda SOLO la clave cambiada; rechaza sin llamar al servidor si está bloqueado.
  async function saveSwitch(sw, company, nextOn, reason) {
    const p = plan(sw, company, nextOn);
    if (p.blocked) throw new Error(p.blocked);
    const why = String(reason || "").trim();
    if (why.length < 3) throw new Error("Escribe un motivo corto.");
    return request(`${API}/companies/${encodeURIComponent(company.id)}/modules/${encodeURIComponent(sw.module)}/activate`, {
      method: "POST",
      headers: auditNote({ interruptor: sw.key, valor: nextOn, motivo: why.slice(0, 200) }),
      body: JSON.stringify({ settings: { [sw.key]: nextOn } }),
    });
  }

  // ------------------------------------------------- M05 · configuración QR
  const QR_COUNT_OPTIONS = [10, 15, 20, 30, 40, 50, 70, 100, 120, 150, 200, 300, 500];
  const QR_MODES = [
    { code: "hospitality", label: "Mesas / bar", includeBar: true },
    { code: "voting", label: "Votacion / participantes", includeBar: false },
    { code: "generic", label: "Generico", includeBar: false },
  ];
  const qrNorm = (v) => String(v || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  const isQrModule = (code) => ["qr", "mesa_qr", "mesas_qr", "qr_mesas", "hospitality_qr", "voting_qr"].includes(qrNorm(code));
  const origin = () => (window.location && window.location.origin) || "";
  function qrBaseUrl(value) {
    let text = String(value || "").trim();
    if (!text) return origin();
    text = text.replace(/\/+$/, "").replace(/\/ordenar$/i, "");
    return text || origin();
  }
  function qrClamp(value, fallback = 10) {
    const n = Math.round(Number(value || fallback));
    if (!Number.isFinite(n)) return fallback;
    return Math.min(500, Math.max(1, n));
  }
  function qrNormalize(row = {}) {
    const source = row && row.settings && typeof row.settings === "object" ? row.settings : {};
    const raw = source.qr_config && typeof source.qr_config === "object" ? source.qr_config : (source.hospitality_qr && typeof source.hospitality_qr === "object" ? source.hospitality_qr : source);
    const mode = QR_MODES.some((m) => m.code === raw.mode) ? raw.mode : "hospitality";
    const modeDef = QR_MODES.find((m) => m.code === mode) || QR_MODES[0];
    const maxCapacity = qrClamp(raw.max_capacity || raw.capacity || raw.limit || raw.table_count || raw.count || 12, 12);
    const count = Math.min(maxCapacity, qrClamp(raw.table_count || raw.count || raw.visible_count || maxCapacity, maxCapacity));
    return {
      mode, max_capacity: maxCapacity, table_count: count,
      include_bar: typeof raw.include_bar === "boolean" ? raw.include_bar : modeDef.includeBar,
      orders_board: String(raw.orders_board || "kanban").toLowerCase() === "mesas" ? "mesas" : "kanban",
      base_url: qrBaseUrl(raw.base_url || raw.public_base_url || origin()), updated_at: raw.updated_at || "",
    };
  }
  // Mismo cuerpo que cxSaveCompanyQrConfig025N.
  function qrPayload(raw) {
    const modeDef = QR_MODES.find((m) => m.code === raw.mode) || QR_MODES[0];
    const maxCapacity = qrClamp(raw.max_capacity, 10);
    return {
      mode: modeDef.code, max_capacity: maxCapacity, table_count: Math.min(maxCapacity, qrClamp(raw.table_count, maxCapacity)),
      include_bar: raw.include_bar === "on", orders_board: raw.orders_board === "mesas" ? "mesas" : "kanban",
      base_url: qrBaseUrl(raw.base_url || origin()), updated_at: new Date().toISOString(),
    };
  }
  const config = {
    modules: (cid) => request(`${API}/companies/${encodeURIComponent(cid)}/modules?enabled_only=false`),
    saveQr: (cid, moduleCode, payload, reason) => request(`${API}/companies/${encodeURIComponent(cid)}/modules/${encodeURIComponent(moduleCode)}/activate`,
      { method: "POST", headers: auditNote({ ajuste: "qr_config", motivo: reason }), body: JSON.stringify({ settings: { qr_config: payload } }) }),
    policy: (cid) => request(`${API}/workforce-sessions/companies/${encodeURIComponent(cid)}/policy`),                       // S01
    savePolicy: (cid, body, reason) => request(`${API}/workforce-sessions/companies/${encodeURIComponent(cid)}/policy`,   // S02
      { method: "PUT", headers: auditNote({ ajuste: "corte_diario", motivo: reason }), body: JSON.stringify(body) }),
    // Mismo cuerpo que cxSessPolicyPanel048Q.
    policyBody: (raw) => ({ cutoff_time: raw.cutoff_time, alert_after_hours: Number(raw.alert_after_hours) }),
  };

  // ------------------------------------------------------------ estado
  const model = { data: null, error: "", notice: "", query: "", kind: "registrada", modal: null, focusKey: "", cfg: { companyId: "", qrRow: null, modules: null, policy: null, error: "" } };
  let ctx = null;
  let bound = false;

  const companies = () => arr(model.data && model.data.companies);
  const companyById = (id) => companies().find((c) => c.id === id) || null;

  function visible() {
    const all = companies().filter((c) => model.kind === "todas" || c.kind === model.kind);
    const sws = Registry.list();
    const q = model.query;
    if (!fold(q)) return { cols: all, rows: sws };
    const rows = sws.filter((s) => matches(q, s.label, s.key, s.description, s.group, s.module));
    const cols = all.filter((c) => matches(q, c.name, c.slug));
    if (rows.length && !cols.length) return { cols: all, rows };
    if (cols.length && !rows.length) return { cols, rows: sws };
    return { cols, rows };
  }

  // ------------------------------------------------------------ vistas
  function cell(sw, c) {
    const st = (c.switches || {})[sw.key] || {};
    if (st.locked && !st.on) {
      return `<td><span class="vp-sw-cell is-locked" role="img" title="Bloqueado: falta ${h(arr(st.missing_modules).join(", "))}" aria-label="${h(sw.label)} en ${h(c.name)}: bloqueado, falta ${h(arr(st.missing_modules).join(", "))}">🔒</span></td>`;
    }
    return `<td><button class="vp-switch-btn ${st.on ? "is-on" : ""}" type="button" role="switch" aria-checked="${st.on ? "true" : "false"}"
      aria-label="${h(sw.label)} en ${h(c.name)}: ${st.on ? "encendido" : "apagado"}" data-vpw-cell="${h(sw.key)}|${h(c.id)}"><span></span></button></td>`;
  }

  function badges(sw) {
    return `${sw.delicate ? `<span class="vp-state-pill vp-pill-warn" title="${h(sw.delicate_reason)}">Delicado</span>` : ""}${sw.v2_form ? `<span class="vp-state-pill" title="${h(V2_WARNING)}">También en Admin V2</span>` : ""}${arr(sw.depends_on).length ? `<span class="vp-state-pill" title="${h(arr(sw.depends_on).map((d) => d.why).join(" "))}">Depende de ${h(arr(sw.depends_on).map((d) => (Registry.get(d.key) || {}).label || d.key).join(", "))}</span>` : ""}`;
  }

  function matrixView() {
    if (model.error && !model.data) return `<div class="vp-alert" role="alert"><span>${h(model.error)}</span></div>`;
    if (!model.data) return `<p class="vp-loading">Cargando interruptores…</p>`;
    const { cols, rows } = visible();
    const groups = arr(model.data.registry.groups).map((g) => [g, rows.filter((s) => s.group === g)]).filter(([, items]) => items.length);
    const toolbar = `<div class="vp-toolbar"><input class="vp-search" type="search" placeholder="Buscar interruptor o empresa" value="${h(model.query)}" data-vpw-search aria-label="Buscar interruptor o empresa">
      <div class="vp-chips">${[["registrada", "Registradas"], ["demo", "Demos"], ["todas", "Todas"]].map(([k, l]) => `<button class="vp-chip ${model.kind === k ? "is-active" : ""}" type="button" data-vpw-kind="${k}">${l}</button>`).join("")}</div></div>
      <p class="vp-login-hint"><span class="vp-switch-btn is-on vp-legend" aria-hidden="true"><span></span></span> encendido · <span class="vp-switch-btn vp-legend" aria-hidden="true"><span></span></span> apagado · 🔒 bloqueado (la empresa no tiene el módulo). Cada cambio afecta solo a esa empresa.</p>`;
    if (!cols.length || !groups.length) return `${toolbar}<div class="vp-empty">Nada coincide con la búsqueda.</div>`;
    return `${toolbar}<div class="vp-table-wrap vp-zone-scroll vp-sw-wrap"><table class="vp-table vp-table-compact vp-sw-matrix">
      <thead><tr><th scope="col">Interruptor</th>${cols.map((c) => `<th scope="col" class="${model.cfg.companyId === c.id ? "is-focus" : ""}"><a href="#empresa/${encodeURIComponent(c.id)}">${h(c.name)}</a><small>${h(c.kind === "demo" ? "demo" : "registrada")}</small></th>`).join("")}</tr></thead>
      <tbody>${groups.map(([g, items]) => `<tr class="vp-sw-group"><th scope="rowgroup" colspan="${cols.length + 1}">${h(g)}</th></tr>${items.map((sw) => `
        <tr class="${model.focusKey === sw.key ? "is-focus" : ""}" id="vpw-row-${h(sw.key)}"><th scope="row"><b>${h(sw.label)}</b><small class="vp-mono-muted">${h(sw.module)} · ${h(sw.key)}</small><small>${h(sw.description)}</small><span class="vp-chip-row">${badges(sw)}</span></th>
        ${cols.map((c) => cell(sw, c)).join("")}</tr>`).join("")}`).join("")}</tbody></table></div>`;
  }

  function configView() {
    const cfg = model.cfg;
    const list = companies().filter((c) => model.kind === "todas" || c.kind === model.kind);
    const pick = `<label class="vp-field">Empresa<select data-vpw-cfg-company><option value="">Elige una empresa…</option>${list.map((c) => `<option value="${h(c.id)}" ${cfg.companyId === c.id ? "selected" : ""}>${h(c.name)}</option>`).join("")}</select></label>`;
    if (!cfg.companyId) return `<section class="vp-panel vp-section"><h2>Configuración QR y corte diario</h2>${pick}</section>`;
    const err = cfg.error ? `<div class="vp-alert" role="alert"><span>${h(cfg.error)}</span></div>` : "";
    let qr = `<p class="vp-loading">Cargando…</p>`;
    if (cfg.modules) {
      const row = cfg.qrRow;
      if (!row) qr = `<div class="vp-empty">Esta configuración solo se desbloquea cuando la empresa tiene el módulo QR activo.</div>`;
      else {
        const s = qrNormalize(row);
        const opts = (value) => Array.from(new Set([...QR_COUNT_OPTIONS, Number(value)])).filter((n) => n > 0 && n <= 500).sort((a, b) => a - b).map((n) => `<option value="${n}" ${n === Number(value) ? "selected" : ""}>${n}</option>`).join("");
        qr = `<form class="vp-form-grid" data-vpw-qr-form data-module="${h(row.code)}">
          <label class="vp-field">Uso del QR<select name="mode">${QR_MODES.map((m) => `<option value="${m.code}" ${s.mode === m.code ? "selected" : ""}>${h(m.label)}</option>`).join("")}</select></label>
          <label class="vp-field">Capacidad máxima<select name="max_capacity">${opts(s.max_capacity)}</select></label>
          <label class="vp-field">QR / mesas a generar<select name="table_count">${opts(s.table_count)}</select></label>
          <label class="vp-field">URL pública base<input name="base_url" type="url" value="${h(s.base_url)}"></label>
          <label class="vp-field">Tablero de pedidos<select name="orders_board"><option value="kanban" ${s.orders_board === "kanban" ? "selected" : ""}>Columnas</option><option value="mesas" ${s.orders_board === "mesas" ? "selected" : ""}>Mesas</option></select></label>
          <label class="vp-check"><input name="include_bar" type="checkbox" ${s.include_bar ? "checked" : ""}> Incluir QR adicional de Barra</label>
          <p class="vp-login-hint">Se verán en el cliente <b>${h(s.table_count + (s.include_bar ? 1 : 0))} QR</b> · lectura pública ${h(s.base_url)}/ordenar</p>
          <button class="vp-btn vp-btn-primary" type="submit">Guardar configuración QR</button></form>`;
      }
    }
    const pol = cfg.policy;
    const policy = !pol ? `<p class="vp-loading">Cargando…</p>` : pol.error ? `<div class="vp-alert" role="alert"><span>${h(pol.error)}</span></div>` : `<form class="vp-form-grid" data-vpw-policy-form>
      <p class="vp-login-hint">A esta hora el sistema cierra los turnos y logins de mini panel que sigan abiertos. Las horas cortadas no se pagan hasta que el administrador registre la hora real.</p>
      <label class="vp-field">Hora del corte<input type="time" name="cutoff_time" value="${h(pol.cutoff_time || "00:00")}"></label>
      <label class="vp-field">Alerta si una sesión pasa de (horas)<input type="number" min="1" max="24" step="0.5" name="alert_after_hours" value="${h(pol.alert_after_hours || 12)}"></label>
      <button class="vp-btn vp-btn-primary" type="submit">Guardar corte</button></form>`;
    return `<section class="vp-panel vp-section"><h2>Configuración QR y corte diario</h2>${pick}${err}
      <div class="vp-card-grid"><article class="vp-panel-card"><header><b>Configuración QR</b></header>${qr}</article>
      <article class="vp-panel-card"><header><b>Corte diario de sesiones</b><span class="vp-state-pill">${h((pol && pol.cutoff_time) || "00:00")}</span></header>${policy}</article></div></section>`;
  }

  function modalView() {
    const md = model.modal;
    if (!md) return "";
    const err = md.error ? `<div class="vp-alert" role="alert"><span>${h(md.error)}</span></div>` : "";
    const head = `<div class="vp-modal-head"><h2>${h(md.title)}</h2><button class="vp-btn vp-btn-sm" type="button" data-vpw-close aria-label="Cerrar">✕</button></div>`;
    let body = "";
    if (md.type === "switch") {
      const { sw, company, nextOn, plan: p } = md;
      body = `<p class="vp-login-hint">${nextOn ? "Encender" : "Apagar"} <b>${h(sw.label)}</b> en <b>${h(company.name)}</b>.</p>
        <p class="vp-sw-only"><b>Solo esta empresa.</b> Las demás empresas y los demás ajustes no cambian.</p>
        <p class="vp-login-hint">${h(sw.description)}</p>
        ${p.warnings.map((w) => `<div class="vp-alert vp-alert-${w.kind === "note" ? "info" : "warn"}" role="note"><span>${h(w.text)}</span></div>`).join("")}
        ${sw.delicate ? `<div class="vp-alert" role="note"><span><b>Delicado:</b> ${h(sw.delicate_reason)}</span></div>` : ""}
        <label class="vp-field">Motivo (queda en la auditoría)<input data-vpw-reason maxlength="200" value="${h(md.reason || "")}" placeholder="Ej.: lo pidió el dueño por WhatsApp"></label>
        ${p.needsName ? `<label class="vp-field">Escribe el nombre de la empresa para confirmar: <b>${h(company.name)}</b><input data-vpw-name autocomplete="off" value="${h(md.name || "")}"></label>` : ""}
        ${p.needsAck ? `<label class="vp-check"><input type="checkbox" data-vpw-ack ${md.ack ? "checked" : ""}> Entiendo lo que deja de funcionar</label>` : ""}
        ${err}<div class="vp-actions"><button class="vp-btn ${nextOn ? "vp-btn-primary" : "vp-btn-danger"}" type="button" data-vpw-go ${md.busy ? "disabled" : ""}>${nextOn ? "Encender" : "Apagar"} solo en ${h(company.name)}</button><button class="vp-btn" type="button" data-vpw-close>Cancelar</button></div>`;
    } else {
      body = `<p class="vp-login-hint">${h(md.message)}</p><p class="vp-sw-only"><b>Solo esta empresa:</b> ${h(md.companyName)}.</p>
        <label class="vp-field">Motivo (queda en la auditoría)<input data-vpw-reason maxlength="200" value="${h(md.reason || "")}"></label>
        ${err}<div class="vp-actions"><button class="vp-btn vp-btn-primary" type="button" data-vpw-go ${md.busy ? "disabled" : ""}>Guardar</button><button class="vp-btn" type="button" data-vpw-close>Cancelar</button></div>`;
    }
    return `<div class="vp-modal" data-vpw-modal><div class="vp-panel vp-modal-card" role="dialog" aria-modal="true">${head}${body}</div></div>`;
  }

  function view() {
    return `<header class="vp-head"><div><p class="vp-eyebrow">NÚCLEO CLONEXA · INTERRUPTORES</p><h1 class="vp-title">Interruptores</h1></div>
      <div class="vp-head-actions"><button class="vp-btn" type="button" data-vpw-refresh>Refrescar</button></div></header>
      ${model.notice ? `<p class="vp-ok-text" role="status">${h(model.notice)}</p>` : ""}${model.error && model.data ? `<div class="vp-alert" role="alert"><span>${h(model.error)}</span></div>` : ""}
      <section class="vp-panel vp-section">${matrixView()}</section>${model.data ? configView() : ""}${modalView()}`;
  }

  const FOCUS = ["[data-vpw-search]", "[data-vpw-reason]", "[data-vpw-name]"];
  function draw() {
    if (!ctx || !ctx.active() || !ctx.root()) return;
    const active = typeof document.activeElement !== "undefined" ? document.activeElement : null;
    const keep = active && active.matches && FOCUS.find((s) => active.matches(s));
    const caret = keep ? active.selectionStart : null;
    ctx.root().innerHTML = view();
    if (keep) { const el = ctx.root().querySelector(keep); if (el) { el.focus(); try { el.setSelectionRange(caret, caret); } catch (_) {} } }
  }

  // ------------------------------------------------------------ carga
  async function load(force = false) {
    try { model.data = await Registry.load(force); model.error = ""; }
    catch (error) { model.error = error.message || "No se pudieron leer los interruptores."; }
    draw();
    if (model.focusKey && ctx && ctx.root() && ctx.root().querySelector) {
      const row = ctx.root().querySelector(`#vpw-row-${model.focusKey}`);
      if (row && row.scrollIntoView) row.scrollIntoView({ block: "center" });
    }
  }

  async function loadConfig(cid) {
    const cfg = model.cfg;
    Object.assign(cfg, { companyId: cid, modules: null, qrRow: null, policy: null, error: "" });
    draw();
    if (!cid) return;
    const [mods, pol] = await Promise.all([
      config.modules(cid).catch((e) => { cfg.error = e.message; return []; }),
      config.policy(cid).catch((e) => ({ error: e.message })),
    ]);
    if (cfg.companyId !== cid) return;
    cfg.modules = arr(mods);
    const rows = cfg.modules.map((row) => { const m = row.module && typeof row.module === "object" ? row.module : row; return { code: String(m.code || row.module_code || row.code || ""), enabled: row.enabled !== false, settings: row.settings || {} }; });
    cfg.qrRow = rows.find((r) => isQrModule(r.code) && r.enabled) || null;
    cfg.policy = pol;
    draw();
  }

  // ------------------------------------------------------------ eventos
  function openSwitch(key, cid) {
    const sw = Registry.get(key);
    const company = companyById(cid);
    if (!sw || !company) return;
    const nextOn = !((company.switches || {})[key] || {}).on;
    const p = plan(sw, company, nextOn);
    if (p.blocked) { model.notice = ""; model.error = p.blocked; draw(); return; }
    model.error = "";
    model.modal = { type: "switch", title: `${nextOn ? "Encender" : "Apagar"} interruptor`, sw, company, nextOn, plan: p, reason: "", name: "", ack: false };
    draw();
  }

  async function confirm() {
    const md = model.modal;
    if (!md || md.busy) return;
    const reason = String(md.reason || "").trim();
    if (reason.length < 3) { md.error = "Escribe un motivo corto (queda en la auditoría)."; draw(); return; }
    if (md.type === "switch") {
      if (md.plan.needsName && fold(md.name) !== fold(md.company.name)) { md.error = "El nombre no coincide con el de la empresa."; draw(); return; }
      if (md.plan.needsAck && !md.ack) { md.error = "Confirma que entiendes lo que deja de funcionar."; draw(); return; }
    }
    md.busy = true;
    md.error = "";
    draw();
    try {
      if (md.type === "switch") {
        await saveSwitch(md.sw, md.company, md.nextOn, reason);
        model.notice = `«${md.sw.label}» ${md.nextOn ? "encendido" : "apagado"} solo en ${md.company.name}.`;
        model.modal = null;
        await load(true);
      } else {
        await md.run(reason);
        model.notice = md.done;
        model.modal = null;
        await loadConfig(model.cfg.companyId);
      }
    } catch (error) {
      if (model.modal) { model.modal.busy = false; model.modal.error = error.message || "No se pudo guardar."; }
    } finally { draw(); }
  }

  function onClick(event) {
    if (!ctx || !ctx.active()) return;
    const t = event.target;
    if (!t || !t.closest) return;
    const c = t.closest("[data-vpw-cell]");
    if (c) { const [key, cid] = c.getAttribute("data-vpw-cell").split("|"); openSwitch(key, cid); return; }
    const k = t.closest("[data-vpw-kind]");
    if (k) { model.kind = k.getAttribute("data-vpw-kind"); draw(); return; }
    if (t.closest("[data-vpw-refresh]")) { model.notice = ""; load(true); return; }
    if (t.closest("[data-vpw-close]") || (t.matches && t.matches("[data-vpw-modal]"))) { model.modal = null; draw(); return; }
    if (t.closest("[data-vpw-go]")) { confirm(); }
  }
  function onInput(event) {
    if (!ctx || !ctx.active()) return;
    const t = event.target;
    if (!t || !t.matches) return;
    if (t.matches("[data-vpw-search]")) { model.query = t.value; model.focusKey = ""; draw(); return; }
    if (model.modal && t.matches("[data-vpw-reason]")) { model.modal.reason = t.value; return; }
    if (model.modal && t.matches("[data-vpw-name]")) { model.modal.name = t.value; return; }
  }
  function onChange(event) {
    if (!ctx || !ctx.active()) return;
    const t = event.target;
    if (!t || !t.matches) return;
    if (t.matches("[data-vpw-cfg-company]")) { loadConfig(t.value); return; }
    if (model.modal && t.matches("[data-vpw-ack]")) model.modal.ack = t.checked;
  }
  function onSubmit(event) {
    if (!ctx || !ctx.active()) return;
    const form = event.target;
    if (!form || !form.matches) return;
    const cid = model.cfg.companyId;
    const company = companyById(cid) || { name: "la empresa" };
    if (form.matches("[data-vpw-qr-form]")) {
      event.preventDefault();
      const raw = Object.fromEntries(new FormData(form).entries());
      const payload = qrPayload(raw);
      const moduleCode = form.getAttribute("data-module") || "qr";
      model.modal = { type: "config", title: "Guardar configuración QR", companyName: company.name, reason: "",
        message: `${payload.table_count}${payload.include_bar ? " + barra" : ""} QR, capacidad ${payload.max_capacity}, tablero ${payload.orders_board === "mesas" ? "Mesas" : "Columnas"}.`,
        run: (reason) => config.saveQr(cid, moduleCode, payload, reason), done: `Configuración QR guardada solo en ${company.name}.` };
      draw();
    } else if (form.matches("[data-vpw-policy-form]")) {
      event.preventDefault();
      const body = config.policyBody(Object.fromEntries(new FormData(form).entries()));
      model.modal = { type: "config", title: "Guardar corte diario", companyName: company.name, reason: "",
        message: `Corte a las ${body.cutoff_time}; alerta si una sesión pasa de ${body.alert_after_hours} h.`,
        run: (reason) => config.savePolicy(cid, body, reason), done: `Corte diario guardado solo en ${company.name}.` };
      draw();
    }
  }

  window.CxConsoleSections = window.CxConsoleSections || {};
  window.CxConsoleSections.switches = {
    mount(context) {
      ctx = context;
      model.notice = "";
      const params = (context && context.params) || {};
      model.focusKey = params.key || "";
      if (params.key) { const sw = Registry.get(params.key); model.query = sw ? sw.label : params.key; }
      if (params.companyId) { model.kind = "todas"; loadConfig(params.companyId); }
      if (!bound && typeof document.addEventListener === "function") {
        document.addEventListener("click", onClick);
        document.addEventListener("input", onInput);
        document.addEventListener("change", onChange);
        document.addEventListener("submit", onSubmit);
        bound = true;
      }
      draw();
      load(true).then(() => { const sw = params.key && Registry.get(params.key); if (sw && model.query === params.key) { model.query = sw.label; draw(); } });
    },
  };
  window.CxSwitchRegistry = Registry;
  window.CxConsoleSwitches = { model, view, plan, saveSwitch, config, qrNormalize, qrPayload, openSwitch, confirm, V2_WARNING, _setCache: (d) => { cache = d; model.data = d; } };
})();
