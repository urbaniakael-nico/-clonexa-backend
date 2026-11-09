/* CLONEXA 072A: Avisos por WhatsApp (interruptor whatsapp_group_reports, solo dueño / admin).
   Configuración editable (destinatarios, horas, modo prueba), "Enviar prueba ahora" por tipo e
   Historial de avisos. Todo se valida en el servidor; esta pantalla solo arma el formulario. */
(function () {
  "use strict";
  const DAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
  const STATUS = { pending: "En cola", sending: "Enviando", sent: "Enviado", failed: "Fallido", skipped: "Sin destino", received: "Recibido" };
  const model = { data: null, items: [], error: "", notice: "", busy: false, denied: false };
  let ctx = null;
  let bound = false;

  function h(v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function headers(json) {
    const t = ctx && ctx.token ? ctx.token() : "";
    const out = t ? { Authorization: `Bearer ${t}` } : {};
    if (json) out["Content-Type"] = "application/json";
    return out;
  }
  function url(path) {
    return `${ctx.apiBase}/group-reports/companies/${encodeURIComponent(ctx.companyId)}${path}`;
  }
  async function call(method, path, body) {
    const res = await fetch(url(path), { method, headers: headers(body !== undefined), body: body !== undefined ? JSON.stringify(body) : undefined, credentials: "same-origin" });
    let data = {};
    try { data = await res.json(); } catch (_) { data = {}; }
    if (!res.ok) {
      const err = new Error((data && data.detail && (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail))) || `Error ${res.status}`);
      err.status = res.status;
      throw err;
    }
    return data;
  }

  function when(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "—";
    return d.toLocaleString("es-CO", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  }
  function locName(id) {
    const loc = ((model.data && model.data.locations) || []).find((l) => l.id === id);
    return loc ? loc.name : "";
  }
  function locSelect(field, value, empty) {
    const locs = (model.data && model.data.locations) || [];
    return `<select data-gr-field="${field}">${empty ? `<option value="">${h(empty)}</option>` : ""}${locs.map((l) => `<option value="${h(l.id)}" ${l.id === value ? "selected" : ""}>${h(l.name)}</option>`).join("")}</select>`;
  }
  function daySelect(field, value) {
    return `<select data-gr-field="${field}">${DAYS.map((d, i) => `<option value="${i}" ${Number(value) === i ? "selected" : ""}>${d}</option>`).join("")}</select>`;
  }

  function view() {
    if (model.denied) return `<section class="gr-root" data-gr-root><p class="gr-error">${h(model.error)}</p></section>`;
    if (!model.data) return `<section class="gr-root" data-gr-root><p>${h(model.error || "Cargando…")}</p></section>`;
    const c = model.data.config;
    const ops = c.operations || [];
    const opOf = (id) => ops.find((o) => o.location_id === id);
    const sup = c.supervisor || {};
    const owners = (c.owners || []).length ? c.owners : [{ name: "", phone: "", email: "" }];
    return `<section class="gr-root" data-gr-root>
      <header class="gr-head"><button type="button" class="client-btn" data-gr-back>← Volver</button>
        <div><p class="client-eyebrow">Configuración</p><h1 class="client-title">Avisos por WhatsApp</h1></div></header>
      ${model.notice ? `<p class="gr-notice" role="status">${h(model.notice)}</p>` : ""}
      ${model.error ? `<p class="gr-error" role="alert">${h(model.error)}</p>` : ""}
      ${model.data.n8n_ready ? "" : `<p class="gr-error">Falta conectar el envío (variables de n8n en Railway). Los avisos quedan en el historial como fallidos.</p>`}
      <div class="gr-card ${c.test_mode ? "is-test" : "is-live"}">
        <label class="gr-switch"><input type="checkbox" data-gr-field="test_mode" ${c.test_mode ? "checked" : ""}>
          <span><strong>Modo prueba</strong> — todo WhatsApp va solo a mi número y todo correo al de Clonexa, con el prefijo [PRUEBA].</span></label>
        <p class="gr-hint">${c.test_mode ? "Encendido: nada sale a grupos, supervisor ni dueños." : "Apagado: los avisos salen a los destinatarios reales."}</p>
      </div>
      <div class="gr-card"><h2>Número y correo de envío</h2>
        <div class="gr-grid"><label>Mi número (WhatsApp de envío)<input data-gr-field="own_number" inputmode="tel" value="${h(c.own_number)}" placeholder="13468244098"></label>
        <label>Correo de Clonexa<input data-gr-field="clonexa_email" type="email" value="${h(c.clonexa_email)}"></label></div></div>
      <div class="gr-card"><h2>Grupos por operación</h2>
        ${((model.data.locations) || []).map((l) => {
          const o = opOf(l.id);
          return `<div class="gr-row" data-gr-op="${h(l.id)}"><label class="gr-check"><input type="checkbox" data-gr-op-on ${o ? "checked" : ""}> ${h(l.name)}</label>
            <label>ID del grupo<input data-gr-op-jid value="${h(o ? o.group_jid : "")}" placeholder="1203…@g.us"></label>
            <label>Nombre del grupo<input data-gr-op-name value="${h(o ? o.group_name : "")}"></label></div>`;
        }).join("")}</div>
      <div class="gr-card"><h2>Supervisor (recordatorio diario del timesheet)</h2>
        <div class="gr-grid"><label>Nombre<input data-gr-field="supervisor.name" value="${h(sup.name)}"></label>
        <label>WhatsApp<input data-gr-field="supervisor.phone" inputmode="tel" value="${h(sup.phone)}"></label>
        <label>Correo (opcional)<input data-gr-field="supervisor.email" type="email" value="${h(sup.email)}"></label>
        <label>Operación${locSelect("supervisor.location_id", sup.location_id, "—")}</label></div></div>
      <div class="gr-card"><h2>Dueños (resumen diario y totales de la semana)</h2>
        ${owners.map((o, i) => `<div class="gr-grid" data-gr-owner="${i}"><label>Nombre<input data-gr-owner-name value="${h(o.name)}"></label>
          <label>WhatsApp<input data-gr-owner-phone inputmode="tel" value="${h(o.phone)}"></label>
          <label>Correo<input data-gr-owner-email type="email" value="${h(o.email)}"></label></div>`).join("")}
        <button type="button" class="client-btn" data-gr-add-owner>+ Agregar dueño</button></div>
      <div class="gr-card"><h2>Horas</h2>
        <div class="gr-grid">
          <label>Corte de entrada (min después)<input type="number" min="0" max="240" data-gr-field="checkin_after_min" value="${h(c.checkin_after_min)}"></label>
          <label>Corte de salida (min después)<input type="number" min="0" max="240" data-gr-field="checkout_after_min" value="${h(c.checkout_after_min)}"></label>
          <label>Resumen a dueños (min después de la última salida)<input type="number" min="0" max="240" data-gr-field="summary_after_min" value="${h(c.summary_after_min)}"></label>
          <label>Recordatorio extra del timesheet (día siguiente)<input type="time" data-gr-field="followup_time" value="${h(c.followup_time)}"></label>
          <label>Timesheet semanal al grupo de${locSelect("weekly_location_id", c.weekly_location_id, "—")}</label>
          <label>Día del timesheet semanal${daySelect("weekly_weekday", c.weekly_weekday)}</label>
          <label>Totales de la semana: día${daySelect("totals_weekday", c.totals_weekday)}</label>
          <label>Totales de la semana: hora<input type="time" data-gr-field="totals_time" value="${h(c.totals_time)}"></label>
          <label>Zona de los totales<select data-gr-field="totals_tz">${(model.data.timezones || []).map((z) => `<option ${z === c.totals_tz ? "selected" : ""}>${h(z)}</option>`).join("")}</select></label>
        </div></div>
      <div class="gr-card"><h2>Tipos de aviso</h2>
        <ul class="gr-kinds">${(model.data.kinds || []).map((k) => `<li><label class="gr-check"><input type="checkbox" data-gr-kind="${h(k.key)}" ${c.kinds && c.kinds[k.key] !== false ? "checked" : ""}> ${h(k.label)}</label>
          <button type="button" class="client-btn" data-gr-test="${h(k.key)}" ${model.busy ? "disabled" : ""}>Enviar prueba ahora</button></li>`).join("")}</ul>
        <p class="gr-hint">"Enviar prueba ahora" siempre va a mi número y al correo de Clonexa, aunque el modo prueba esté apagado.</p></div>
      <div class="gr-actions"><button type="button" class="rb-primary client-btn" data-gr-save ${model.busy ? "disabled" : ""}>Guardar configuración</button></div>
      <div class="gr-card"><h2>Historial de avisos</h2>
        <div class="gr-table-wrap"><table class="gr-table" aria-label="Historial de avisos"><thead><tr><th>Fecha</th><th>Tipo</th><th>Destino</th><th>Estado</th></tr></thead>
        <tbody>${model.items.length ? model.items.map((r) => `<tr class="is-${h(r.status)}"><td>${h(when(r.created_at))}</td><td>${h(r.kind_label)}${r.test ? ' <small class="gr-tag">prueba</small>' : ""}</td>
          <td>${h(r.destination)}</td><td>${h(STATUS[r.status] || r.status)}${r.error ? `<small class="gr-err">${h(r.error)}</small>` : ""}</td></tr>`).join("") : `<tr><td colspan="4">Todavía no hay avisos.</td></tr>`}</tbody></table></div></div>
    </section>`;
  }

  function draw() {
    const host = ctx && ctx.host();
    if (host) host.innerHTML = view();
  }

  function read() {
    const host = ctx.host();
    const c = JSON.parse(JSON.stringify(model.data.config));
    host.querySelectorAll("[data-gr-field]").forEach((el) => {
      const path = el.getAttribute("data-gr-field").split(".");
      const value = el.type === "checkbox" ? el.checked : el.value;
      if (path.length === 2) { c[path[0]] = c[path[0]] || {}; c[path[0]][path[1]] = value; } else c[path[0]] = value;
    });
    c.operations = [];
    host.querySelectorAll("[data-gr-op]").forEach((row) => {
      if (!row.querySelector("[data-gr-op-on]").checked) return;
      c.operations.push({ location_id: row.getAttribute("data-gr-op"), group_jid: row.querySelector("[data-gr-op-jid]").value.trim(), group_name: row.querySelector("[data-gr-op-name]").value.trim() });
    });
    c.owners = [];
    host.querySelectorAll("[data-gr-owner]").forEach((row) => {
      c.owners.push({ name: row.querySelector("[data-gr-owner-name]").value, phone: row.querySelector("[data-gr-owner-phone]").value, email: row.querySelector("[data-gr-owner-email]").value });
    });
    c.kinds = {};
    host.querySelectorAll("[data-gr-kind]").forEach((el) => { c.kinds[el.getAttribute("data-gr-kind")] = el.checked; });
    return c;
  }

  async function load() {
    try {
      const [data, hist] = await Promise.all([call("GET", "/config"), call("GET", "/history?limit=100")]);
      model.data = data;
      model.items = hist.items || [];
      model.error = "";
    } catch (e) {
      model.error = e.message;
      model.denied = e.status === 401 || e.status === 403 || e.status === 404;
    }
    draw();
  }

  async function save() {
    model.busy = true; model.notice = ""; model.error = "";
    try {
      model.data = await call("PUT", "/config", read());
      model.notice = model.data.config.test_mode ? "Guardado. Modo prueba encendido." : "Guardado. Modo prueba APAGADO: los avisos salen a los destinatarios reales.";
    } catch (e) { model.error = e.message; }
    model.busy = false;
    draw();
  }

  async function test(kind) {
    model.busy = true; model.notice = ""; model.error = "";
    draw();
    try {
      const out = await call("POST", `/test/${encodeURIComponent(kind)}`, {});
      model.notice = `Prueba en cola (${out.deliveries} envío${out.deliveries === 1 ? "" : "s"}). Sale en menos de un minuto; mira el historial.`;
      const hist = await call("GET", "/history?limit=100");
      model.items = hist.items || [];
    } catch (e) { model.error = e.message; }
    model.busy = false;
    draw();
  }

  function onClick(event) {
    const t = event.target;
    if (!ctx || !t || !t.closest || !t.closest("[data-gr-root]")) return;
    if (t.closest("[data-gr-back]")) { ctx.back(); return; }
    if (t.closest("[data-gr-save]")) { save(); return; }
    if (t.closest("[data-gr-add-owner]")) { model.data.config = read(); model.data.config.owners.push({ name: "", phone: "", email: "" }); draw(); return; }
    const k = t.closest("[data-gr-test]");
    if (k) test(k.getAttribute("data-gr-test"));
  }

  async function mount(context) {
    ctx = context;
    Object.assign(model, { data: null, items: [], error: "", notice: "", busy: false, denied: false });
    if (!bound && typeof document.addEventListener === "function") {
      document.addEventListener("click", onClick);
      bound = true;
    }
    draw();
    await load();
  }

  async function available(context) {
    try {
      const res = await fetch(`${context.apiBase}/group-reports/companies/${encodeURIComponent(context.companyId)}/config`,
        { headers: context.token && context.token() ? { Authorization: `Bearer ${context.token()}` } : {}, credentials: "same-origin" });
      return res.ok;
    } catch (_) { return false; }
  }

  window.CxGroupReports = { mount, available, view, read, model, locName, _ctx: (c) => { ctx = c; } };
})();
