// Consola v2+ · Facturación: lo que cada empresa registrada le paga a Clonexa.
// Tablero (tarjetas, indicadores, gráficas SVG propias, filtros) y detalle por
// empresa (contrato y tramos, calendario de cuotas, pagos, comprobantes y
// contrato adjunto). Todo con la sesión de Admin V2 (/admin-v2/api/billing).
// Las demos no facturan. Sin estilos en línea (CSP de v2+): colores por clase.
(() => {
  "use strict";

  const API = "/admin-v2/api/billing";
  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const enc = encodeURIComponent;

  async function request(url, options = {}) {
    const response = await fetch(url, { credentials: "same-origin", ...options, headers: { Accept: "application/json", ...(options.body && typeof options.body === "string" ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) } });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401) { window.location.href = "/admin-v2plus/login"; throw new Error("Sesión vencida."); }
    if (!response.ok) {
      const d = data && data.detail;
      throw new Error((d && typeof d === "object" ? d.message : d) || `Respuesta ${response.status}`);
    }
    return data;
  }
  const api = {
    board: () => request(`${API}/board`),
    company: (id) => request(`${API}/companies/${enc(id)}`),
    saveContract: (id, body) => request(`${API}/companies/${enc(id)}/contract`, { method: "PUT", body: JSON.stringify(body) }),
    addType: (label) => request(`${API}/contract-types`, { method: "POST", body: JSON.stringify({ label }) }),
    pay: (id, body) => request(`${API}/companies/${enc(id)}/payments`, { method: "POST", body: JSON.stringify(body) }),
    validate: (id, pid) => request(`${API}/companies/${enc(id)}/payments/${enc(pid)}/validate`, { method: "POST", body: "{}" }),
    voidPay: (id, pid, reason) => request(`${API}/companies/${enc(id)}/payments/${enc(pid)}/void`, { method: "POST", body: JSON.stringify({ reason }) }),
    link: (id, rid) => request(`${API}/companies/${enc(id)}/receipts/${enc(rid)}/link`, { method: "POST", body: "{}" }),
    upload: (id, file) => request(`${API}/companies/${enc(id)}/contract-file`, { method: "POST", body: file, headers: { "Content-Type": "application/pdf", "X-File-Name": String(file.name || "contrato.pdf").replace(/[^\w .()-]/g, "_") } }),
    receiptUrl: (id, rid) => `${API}/companies/${enc(id)}/receipts/${enc(rid)}.pdf`,
    fileUrl: (id, fid) => `${API}/companies/${enc(id)}/contract-file/${enc(fid)}`,
    logo: (id) => request(`/admin-v2/api/brand/${enc(id)}/summary`).then((d) => (d && d.logo_url) || "").catch(() => ""),
    provider: () => request(`${API}/provider`),
    saveProvider: (body) => request(`${API}/provider`, { method: "PUT", body: JSON.stringify(body) }),
    uploadQr: (file) => request(`${API}/provider/qr`, { method: "POST", body: file, headers: { "Content-Type": file.type || "image/png" } }),
    providerQrUrl: () => `${API}/provider/qr`,
    draftCompanies: () => request(`${API}/drafts/companies`),
    draftPrefill: (id, fromManual) => request(`${API}/drafts/companies/${enc(id)}${fromManual ? "?desde=manual" : ""}`),
    draftPreview: (id, body) => request(`${API}/drafts/companies/${enc(id)}/preview`, { method: "POST", body: JSON.stringify(body) }),
    draftGenerate: (id, body) => request(`${API}/drafts/companies/${enc(id)}/generate`, { method: "POST", body: JSON.stringify(body) }),
    draftPdf: async (id, body) => {
      const r = await fetch(`${API}/drafts/companies/${enc(id)}/preview.pdf`, { method: "POST", credentials: "same-origin", body: JSON.stringify(body), headers: { "Content-Type": "application/json", Accept: "application/pdf" } });
      if (r.status === 401) { window.location.href = "/admin-v2plus/login"; throw new Error("Sesión vencida."); }
      if (!r.ok) { const d = await r.json().catch(() => ({})); const x = d && d.detail; throw new Error((x && typeof x === "object" ? x.message : x) || `Respuesta ${r.status}`); }
      return r.blob();
    },
    reminder: (id, enabled) => request(`${API}/companies/${enc(id)}/reminder`, { method: "PUT", body: JSON.stringify({ enabled }) }),
    proofUrl: (id, pid) => `${API}/companies/${enc(id)}/payments/${enc(pid)}/proof`,
  };

  const STATES = {
    al_dia: { label: "Al día", cls: "is-ok" },
    en_ventana: { label: "En ventana de pago", cls: "is-warn" },
    en_mora: { label: "En mora", cls: "is-bad" },
    sin_contrato: { label: "Sin contrato", cls: "is-muted" },
  };
  const INST = { pendiente: ["Pendiente", "is-muted"], en_ventana: ["En ventana", "is-warn"], pagada: ["Pagada", "is-ok"], en_mora: ["En mora", "is-bad"], anulada: ["Anulada", "is-muted"] };
  const PAY = { por_validar: ["Por validar", "is-warn"], validado: ["Validado", "is-ok"], anulado: ["Anulado", "is-bad"] };
  const FILTERS = [["todas", "Todas"], ["al_dia", "Al día"], ["en_ventana", "En ventana"], ["en_mora", "En mora"]];
  const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

  function money(value, currency = "COP") {
    const n = Number(value || 0);
    let txt;
    try { txt = n.toLocaleString("es-CO", { maximumFractionDigits: 2 }); } catch (_) { txt = String(n); }
    return `${currency === "COP" ? "$" : `${currency} `}${txt}`;
  }
  const day = (iso) => {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
    return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}` : "—";
  };
  const period = (iso) => {
    const m = /^(\d{4})-(\d{2})/.exec(String(iso || ""));
    return m ? `${MONTHS[Number(m[2]) - 1]} ${m[1]}` : "—";
  };
  const todayIso = () => {
    try { return new Date().toLocaleDateString("en-CA", { timeZone: "America/Bogota" }); } catch (_) { return new Date().toISOString().slice(0, 10); }
  };

  // ------------------------------------------------------------ estado
  const model = { data: null, error: "", filter: "todas", logos: {}, companyId: "", detail: null, edit: null, modal: null, busy: false, notice: "", draft: null, provider: null };
  let ctx = null;
  let bound = false;

  function stateOf(summary) {
    const s = STATES[(summary && summary.state) || "sin_contrato"] || STATES.sin_contrato;
    const late = summary && summary.state === "en_mora" && summary.days_late ? ` · ${summary.days_late} día${summary.days_late === 1 ? "" : "s"}` : "";
    return `<span class="vp-bill-pill ${s.cls}">${h(s.label)}${h(late)}</span>`;
  }

  function avatar(company) {
    const logo = model.logos[company.id];
    if (logo) return `<img class="vp-bill-logo" src="${h(logo)}" alt="">`;
    const initials = window.CxConsolePlus && window.CxConsolePlus.initials ? window.CxConsolePlus.initials(company.name) : String(company.name || "?").slice(0, 2).toUpperCase();
    return `<span class="vp-bill-logo vp-bill-initials" aria-hidden="true">${h(initials)}</span>`;
  }

  // ------------------------------------------------------------ gráficas
  const empty = (text) => `<div class="vp-empty vp-bill-chart-empty">${h(text)}</div>`;

  function chartByMonth(rows) {
    const list = arr(rows);
    const max = Math.max(0, ...list.map((r) => Math.max(Number(r.expected || 0), Number(r.collected || 0))));
    if (!list.length || max <= 0) return empty("Todavía no hay cuotas ni pagos para graficar.");
    const W = 1000, H = 220, pad = 24, slot = (W - pad) / list.length, bw = Math.max(4, slot / 2 - 3);
    const y = (v) => H - pad - ((H - pad * 2) * Number(v || 0)) / max;
    const bars = list.map((r, i) => {
      const x = pad + i * slot;
      const lab = String(r.month || "").slice(5, 7);
      return `<g><title>${h(r.label)}: recaudado ${h(money(r.collected))} de ${h(money(r.expected))}</title>
        <rect class="vp-bill-bar-exp" x="${x.toFixed(1)}" y="${y(r.expected).toFixed(1)}" width="${bw.toFixed(1)}" height="${(H - pad - y(r.expected)).toFixed(1)}" rx="2"></rect>
        <rect class="vp-bill-bar-col" x="${(x + bw + 2).toFixed(1)}" y="${y(r.collected).toFixed(1)}" width="${bw.toFixed(1)}" height="${(H - pad - y(r.collected)).toFixed(1)}" rx="2"></rect>
        <text class="vp-bill-axis" x="${(x + bw).toFixed(1)}" y="${H - 6}" text-anchor="middle">${h(MONTHS[Number(lab) - 1] || "")}</text></g>`;
    }).join("");
    return `<svg class="vp-bill-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Recaudo por mes: recaudado contra esperado">
      <line class="vp-bill-baseline" x1="${pad}" x2="${W}" y1="${H - pad}" y2="${H - pad}"></line>${bars}</svg>
      <p class="vp-bill-legend"><span class="vp-bill-key is-exp"></span>Esperado <span class="vp-bill-key is-col"></span>Recaudado</p>`;
  }

  function chartByCompany(rows) {
    const list = arr(rows).filter((r) => Number(r.collected) > 0);
    if (!list.length) return empty("Todavía no hay pagos validados.");
    const max = Math.max(...list.map((r) => Number(r.collected)));
    // Ancho cercano al real de la tarjeta: el texto queda legible (escala ~1).
    const W = 320, row = 40, H = list.length * row + 4;
    return `<svg class="vp-bill-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Recaudo por empresa, últimos 12 meses">${list.map((r, i) => {
      const w = Math.max(2, (220 * Number(r.collected)) / max);
      return `<g><title>${h(r.name)}: ${h(money(r.collected))}</title><text class="vp-bill-axis" x="0" y="${i * row + 13}">${h(String(r.name).slice(0, 28))}</text>
        <rect class="vp-bill-bar-col" x="0" y="${i * row + 19}" width="${w.toFixed(1)}" height="14" rx="3"></rect>
        <text class="vp-bill-axis" x="${(w + 6).toFixed(1)}" y="${i * row + 31}">${h(money(r.collected))}</text></g>`;
    }).join("")}</svg>`;
  }

  function chartByType(rows) {
    const list = arr(rows).filter((r) => Number(r.count) > 0);
    const total = list.reduce((a, r) => a + Number(r.count), 0);
    if (!total) return empty("Todavía no hay contratos.");
    const R = 15.915, C = 2 * Math.PI * R;
    let offset = 0;
    const rings = list.map((r, i) => {
      const len = (C * Number(r.count)) / total;
      const seg = `<circle class="vp-bill-ring is-s${i % 6}" cx="21" cy="21" r="${R}" fill="none" stroke-width="7" stroke-dasharray="${len.toFixed(2)} ${(C - len).toFixed(2)}" stroke-dashoffset="${(-offset).toFixed(2)}"><title>${h(r.label)}: ${h(r.count)}</title></circle>`;
      offset += len;
      return seg;
    }).join("");
    return `<div class="vp-bill-donut"><svg viewBox="0 0 42 42" role="img" aria-label="Distribución por tipo de contrato">${rings}
      <text class="vp-bill-donut-n" x="21" y="23.5" text-anchor="middle">${h(total)}</text></svg>
      <ul class="vp-bill-donut-keys">${list.map((r, i) => `<li><span class="vp-bill-key is-s${i % 6}"></span>${h(r.label)} · <b>${h(r.count)}</b></li>`).join("")}</ul></div>`;
  }

  // ------------------------------------------------------------ tablero
  function card(c) {
    const s = c.summary || {};
    const co = c.company;
    const k = c.contract;
    const month = s.month || null;
    const next = s.next || null;
    const progress = k && Number(k.min_months) ? `<span class="vp-mini-chip">mes ${h(Math.min(s.months_done || 0, k.min_months))} de ${h(k.min_months)}</span>` : "";
    return `<article class="vp-panel vp-bill-card" data-vpb-open="${h(co.id)}" tabindex="0" role="button" aria-label="Abrir la facturación de ${h(co.name)}">
      <header class="vp-bill-card-head">${avatar(co)}<div><b>${h(co.name)}</b><small>${k ? h(c.type_label) : "Sin contrato"}</small></div>${stateOf(s)}</header>
      ${k ? `<div class="vp-kv-grid vp-bill-card-kv">
        <div class="vp-kv"><span>Valor mensual</span><strong>${h(money(month ? month.amount : (next && next.amount) || 0, k.currency))}</strong></div>
        <div class="vp-kv"><span>Próximo pago</span><strong>${next ? `${h(day(next.due_from))} al ${h(day(next.due_date))}` : "—"}</strong></div></div>
        <div class="vp-chip-row">${progress}${arr(s.alerts).filter((a) => a.kind === "vence").map((a) => `<span class="vp-mini-chip is-warn">${h(a.text)}</span>`).join("")}
          <button class="vp-btn vp-btn-sm vp-btn-link" type="button" data-vpb-open="${h(co.id)}" data-vpb-focus="files">${c.has_file ? "Ver contrato" : "Adjuntar contrato"}</button></div>`
        : `<p class="vp-login-hint">Aún no tiene contrato. <button class="vp-btn vp-btn-sm vp-btn-link" type="button" data-vpb-open="${h(co.id)}">Crear contrato</button></p>`}
    </article>`;
  }

  function boardView() {
    const d = model.data;
    const head = `<header class="vp-head"><div><p class="vp-eyebrow">NÚCLEO CLONEXA · FACTURACIÓN</p><h1 class="vp-title">Facturación</h1></div>
      <div class="vp-head-actions"><button class="vp-btn vp-btn-primary" type="button" data-vpb-draft>Redactar contrato</button>
        <button class="vp-btn" type="button" data-vpb-provider>Datos del proveedor</button>
        <button class="vp-btn" type="button" data-vpb-refresh>Refrescar</button></div></header>`;
    if (model.error && !d) return `${head}<div class="vp-alert" role="alert"><span>${h(model.error)}</span></div>`;
    if (!d) return `${head}<p class="vp-loading">Cargando facturación…</p>`;
    const k = d.kpis || {};
    const cards = arr(d.cards);
    const count = (f) => (f === "todas" ? cards.length : cards.filter((c) => (c.summary || {}).state === f).length);
    const shown = model.filter === "todas" ? cards : cards.filter((c) => (c.summary || {}).state === model.filter);
    return `${head}
      <p class="vp-login-hint">Solo empresas registradas; las demos no facturan. Las alertas solo avisan: nada se suspende ni se bloquea solo.</p>
      <section class="vp-cards">${[["Recaudado este mes", k.collected_month], ["Por cobrar este mes", k.due_month], ["En mora", k.overdue], ["Ingreso mensual esperado", k.expected_monthly]]
        .map(([l, v], i) => `<div class="vp-panel vp-card ${i === 2 && Number(v) > 0 ? "vp-bill-kpi-bad" : ""}"><span>${h(l)}</span><strong>${h(money(v))}</strong></div>`).join("")}</section>
      <nav class="vp-chips" aria-label="Filtrar por estado">${FILTERS.map(([key, label]) => `<button class="vp-chip ${model.filter === key ? "is-active" : ""}" type="button" data-vpb-filter="${key}">${h(label)} · ${h(count(key))}</button>`).join("")}</nav>
      <section class="vp-bill-grid vp-zone-scroll" aria-label="Empresas">${shown.map(card).join("") || `<div class="vp-empty">Ninguna empresa en este estado.</div>`}</section>
      <div class="vp-sum-grid vp-bill-charts">
        <section class="vp-panel vp-section vp-bill-wide"><h2>Recaudo por mes</h2>${chartByMonth(d.charts && d.charts.by_month)}</section>
        <section class="vp-panel vp-section"><h2>Recaudo por empresa</h2>${chartByCompany(d.charts && d.charts.by_company)}</section>
        <section class="vp-panel vp-section"><h2>Tipos de contrato</h2>${chartByType(d.charts && d.charts.by_type)}</section>
      </div>`;
  }

  // ------------------------------------------------------------ detalle
  function contractPanel(d) {
    const k = d.contract;
    const types = arr(d.types);
    if (model.edit) return contractForm(d);
    if (!k) return `<section class="vp-panel vp-section"><h2>Contrato</h2><div class="vp-empty">Sin contrato todavía.</div>
      <div class="vp-actions"><button class="vp-btn vp-btn-primary" type="button" data-vpb-edit>Crear contrato</button></div></section>`;
    const label = (types.find((t) => t.code === k.contract_type) || {}).label || k.contract_type;
    const tiers = arr(k.tiers).map((t) => `<li class="vp-action vp-toggle-row"><b>${t.month_to ? `Meses ${h(t.month_from)} a ${h(t.month_to)}` : `Desde el mes ${h(t.month_from)}`}</b><span class="vp-mono">${h(money(t.amount, k.currency))}</span></li>`).join("");
    return `<section class="vp-panel vp-section"><div class="vp-row-between"><h2>Contrato</h2><button class="vp-btn vp-btn-sm" type="button" data-vpb-edit>Editar</button></div>
      <div class="vp-kv-grid">
        <div class="vp-kv"><span>Tipo</span><strong>${h(label)}</strong></div>
        <div class="vp-kv"><span>Inicio</span><strong>${h(day(k.start_date))}</strong></div>
        <div class="vp-kv"><span>Mínimo</span><strong>${Number(k.min_months) ? `${h(k.min_months)} meses` : "Sin mínimo"}</strong></div>
        <div class="vp-kv"><span>Ventana de pago</span><strong>del ${h(k.pay_day_from)} al ${h(k.pay_day_to)} de cada mes</strong></div>
        <div class="vp-kv"><span>Moneda</span><strong>${h(k.currency)}</strong></div>
        <div class="vp-kv"><span>Estado</span><strong>${h(String(k.status).replace(/^./, (c) => c.toUpperCase()))}</strong></div></div>
      <h3 class="vp-bill-sub">Tramos de precio</h3><ul class="vp-actions-list">${tiers}</ul>
      ${k.notes ? `<p class="vp-login-hint">${h(k.notes)}</p>` : ""}</section>`;
  }

  function contractForm(d) {
    const e = model.edit;
    const types = arr(d.types);
    return `<section class="vp-panel vp-section"><h2>${d.contract ? "Editar contrato" : "Crear contrato"}</h2>
      <form class="vp-form-grid" data-vpb-contract-form>
        <label class="vp-field">Tipo<select name="contract_type" required>${types.map((t) => `<option value="${h(t.code)}" ${e.contract_type === t.code ? "selected" : ""}>${h(t.label)}</option>`).join("")}</select></label>
        <label class="vp-field">Inicio<input name="start_date" type="date" required value="${h(e.start_date)}"></label>
        <label class="vp-field">Mínimo de meses<input name="min_months" type="number" min="0" max="120" value="${h(e.min_months)}"></label>
        <label class="vp-field">Moneda<input name="currency" maxlength="3" value="${h(e.currency)}" autocomplete="off"></label>
        <label class="vp-field">Paga desde el día<input name="pay_day_from" type="number" min="1" max="28" required value="${h(e.pay_day_from)}"></label>
        <label class="vp-field">hasta el día<input name="pay_day_to" type="number" min="1" max="28" required value="${h(e.pay_day_to)}"></label>
        <label class="vp-field">Estado<select name="status">${["vigente", "pausado", "terminado"].map((s) => `<option value="${s}" ${e.status === s ? "selected" : ""}>${s[0].toUpperCase() + s.slice(1)}</option>`).join("")}</select></label>
        <label class="vp-field vp-bill-wide">Notas<textarea name="notes" rows="2" maxlength="2000">${h(e.notes)}</textarea></label>
        <fieldset class="vp-bill-wide vp-bill-tiers"><legend>Tramos de precio (el último queda abierto: «en adelante»)</legend>
          ${e.tiers.map((t, i) => `<div class="vp-bill-tier" data-vpb-tier="${i}">
            <label class="vp-field">Desde el mes<input name="tier_from_${i}" type="number" min="1" value="${h(t.month_from)}" required></label>
            <label class="vp-field">Hasta el mes<input name="tier_to_${i}" type="number" min="1" value="${h(t.month_to ?? "")}" placeholder="en adelante"></label>
            <label class="vp-field">Valor mensual<input name="tier_amount_${i}" type="number" min="0" step="0.01" value="${h(t.amount)}" required></label>
            ${e.tiers.length > 1 ? `<button class="vp-btn vp-btn-sm" type="button" data-vpb-tier-del="${i}" aria-label="Quitar tramo">✕</button>` : ""}</div>`).join("")}
          <button class="vp-btn vp-btn-sm" type="button" data-vpb-tier-add>Agregar tramo</button></fieldset>
        <div class="vp-actions vp-bill-wide"><button class="vp-btn vp-btn-primary" type="submit">Guardar contrato</button><button class="vp-btn" type="button" data-vpb-edit-cancel>Cancelar</button>
          <button class="vp-btn vp-btn-sm vp-btn-link" type="button" data-vpb-type-add>Agregar un tipo de contrato</button></div>
      </form></section>`;
  }

  function filesPanel(d) {
    const files = arr(d.files);
    const id = d.company.id;
    return `<section class="vp-panel vp-section" id="vpb-files"><h2>Contrato adjunto</h2>
      ${files.length ? `<ul class="vp-actions-list vp-bill-scroll">${files.map((f) => `<li class="vp-action vp-toggle-row"><b>Versión ${h(f.version)}${f.is_current ? " · vigente" : ""}</b>
        <small>${h(f.original_name)} · ${h(Math.round(f.size_bytes / 1024))} KB · ${h(day(f.created_at))}</small>
        <a class="vp-btn vp-btn-sm" href="${h(api.fileUrl(id, f.id))}" target="_blank" rel="noopener">Ver</a></li>`).join("")}</ul>` : `<div class="vp-empty">Sin contrato adjunto.</div>`}
      <form class="vp-form-grid" data-vpb-upload-form><label class="vp-field">${files.length ? "Reemplazar (la versión anterior se conserva)" : "Adjuntar contrato"}<input name="file" type="file" accept="application/pdf,.pdf" required></label>
        <button class="vp-btn" type="submit">${files.length ? "Reemplazar" : "Adjuntar"}</button></form>
      <p class="vp-login-hint">Solo PDF, hasta 10 MB. Se guarda en la zona privada; solo se abre con sesión.</p></section>`;
  }

  function calendar(d) {
    const items = arr(d.installments);
    const cur = todayIso().slice(0, 7);
    const k = d.contract || {};
    if (!items.length) return `<section class="vp-panel vp-section"><h2>Calendario de cuotas</h2><div class="vp-empty">Sin cuotas: crea el contrato.</div></section>`;
    return `<section class="vp-panel vp-section"><h2>Calendario de cuotas</h2><div class="vp-table-wrap vp-bill-scroll"><table class="vp-table">
      <thead><tr><th>Cuota</th><th>Periodo</th><th>Valor</th><th>Ventana</th><th>Estado</th><th></th></tr></thead><tbody>
      ${items.map((i) => {
        const [label, cls] = INST[i.status] || [i.status, ""];
        const when = String(i.period).slice(0, 7);
        const tag = when === cur ? " · este mes" : when > cur ? " · próxima" : "";
        const extra = i.status === "en_mora" ? ` · ${i.days_late} d` : i.status === "en_ventana" && i.days_left !== null ? ` · vence en ${i.days_left} d` : "";
        const canPay = !["pagada", "anulada"].includes(i.status);
        return `<tr class="${when === cur ? "vp-bill-current" : ""}"><td>${h(i.seq)}</td><td>${h(period(i.period))}<small>${h(tag)}</small></td><td class="vp-mono">${h(money(i.amount, k.currency))}</td>
          <td>${h(day(i.due_from))} – ${h(day(i.due_date))}</td><td><span class="vp-bill-pill ${cls}">${h(label)}${h(extra)}</span></td>
          <td>${canPay ? `<button class="vp-btn vp-btn-sm" type="button" data-vpb-pay="${h(i.id)}">Registrar pago</button>` : ""}</td></tr>`;
      }).join("")}</tbody></table></div></section>`;
  }

  function paymentsPanel(d) {
    const list = arr(d.payments);
    const k = d.contract || {};
    const id = d.company.id;
    return `<section class="vp-panel vp-section"><h2>Pagos</h2>${list.length ? `<div class="vp-table-wrap vp-bill-scroll"><table class="vp-table">
      <thead><tr><th>Periodo</th><th>Valor</th><th>Fecha</th><th>Medio · referencia</th><th>Estado</th><th>Comprobante</th></tr></thead><tbody>
      ${list.map((p) => {
        const [label, cls] = PAY[p.status] || [p.status, ""];
        const methods = d.methods || {};
        const code = p.receipt_number ? `CX-${String(p.receipt_number).padStart(6, "0")}` : "";
        const proof = p.has_proof ? `<a class="vp-btn vp-btn-sm" href="${h(api.proofUrl(id, p.id))}" target="_blank" rel="noopener">Ver comprobante del cliente</a>` : "";
        const actions = p.status === "por_validar"
          ? `${proof}<button class="vp-btn vp-btn-sm vp-btn-primary" type="button" data-vpb-validate="${h(p.id)}">Marcar como pago validado</button>
            <button class="vp-btn vp-btn-sm vp-btn-danger" type="button" data-vpb-void="${h(p.id)}" data-vpb-code="">Anular</button>`
          : p.receipt_id ? `<a class="vp-btn vp-btn-sm" href="${h(api.receiptUrl(id, p.receipt_id))}" target="_blank" rel="noopener">${h(code)}${p.receipt_status === "anulado" ? " (anulado)" : ""}</a>
            ${p.status === "validado" ? `<button class="vp-btn vp-btn-sm" type="button" data-vpb-link="${h(p.receipt_id)}">Copiar enlace para el cliente</button>
            <button class="vp-btn vp-btn-sm vp-btn-danger" type="button" data-vpb-void="${h(p.id)}" data-vpb-code="${h(code)}">Anular</button>` : ""}` : "";
        return `<tr><td>${h(period(p.period))}</td><td class="vp-mono">${h(money(p.amount, k.currency))}</td><td>${h(day(p.paid_on))}</td>
          <td>${h(methods[p.method] || p.method)}${p.reference ? ` · <span class="vp-mono">${h(p.reference)}</span>` : ""}</td>
          <td><span class="vp-bill-pill ${cls}">${h(label)}</span>${p.source === "cliente" ? `<small> Reportado por el cliente</small>` : ""}${p.validated_by && p.status !== "por_validar" ? `<small> ${h(p.validated_by)} · ${h(day(p.validated_at))}</small>` : ""}${p.void_reason ? `<small> Motivo: ${h(p.void_reason)}</small>` : ""}</td>
          <td><div class="vp-chip-row">${actions}</div></td></tr>`;
      }).join("")}</tbody></table></div>` : `<div class="vp-empty">Sin pagos registrados.</div>`}</section>`;
  }

  function detailView() {
    const d = model.detail;
    const back = `<p><button class="vp-btn vp-btn-sm vp-btn-link" type="button" data-vpb-back>← Facturación</button></p>`;
    if (model.error && !d) return `${back}<div class="vp-alert" role="alert"><span>${h(model.error)}</span></div>`;
    if (!d) return `${back}<p class="vp-loading">Cargando la facturación de la empresa…</p>`;
    const s = d.summary || {};
    const k = d.contract;
    return `${back}<header class="vp-head"><div class="vp-bill-card-head">${avatar(d.company)}<div><p class="vp-eyebrow">FACTURACIÓN</p><h1 class="vp-title">${h(d.company.name)}</h1></div></div>
      <div class="vp-head-actions">${stateOf(s)}${k && Number(k.min_months) ? `<span class="vp-mini-chip">mes ${h(Math.min(s.months_done || 0, k.min_months))} de ${h(k.min_months)}</span>` : ""}
        <a class="vp-btn vp-btn-sm" href="#empresa/${enc(d.company.id)}">Ficha</a></div></header>
      ${model.error ? `<div class="vp-alert" role="alert"><span>${h(model.error)}</span></div>` : ""}
      ${model.notice ? `<p class="vp-ok-text" role="status">${h(model.notice)}</p>` : ""}
      ${arr(s.alerts).length ? `<div class="vp-alert ${s.state === "en_mora" ? "" : "vp-alert-soft"}" role="status">${arr(s.alerts).map((a) => `<span>${h(a.text)}</span>`).join("")}<small>Solo es un aviso: nada se suspende ni se bloquea.</small></div>` : ""}
      <div class="vp-sum-grid">${contractPanel(d)}${filesPanel(d)}</div>
      ${documentsPanel(d)}${calendar(d)}${paymentsPanel(d)}`;
  }

  // ------------------------------------------------------------ ventanas
  function modal() {
    const m = model.modal;
    if (!m) return "";
    const head = `<div class="vp-modal-head"><h2>${h(m.title)}</h2><button class="vp-btn vp-btn-sm" type="button" data-vpb-close aria-label="Cerrar">✕</button></div>`;
    const err = m.error ? `<div class="vp-alert" role="alert"><span>${h(m.error)}</span></div>` : "";
    let body = "";
    if (m.type === "pay") {
      const methods = (model.detail && model.detail.methods) || {};
      body = `<form class="vp-form-grid" data-vpb-pay-form>
        <label class="vp-field">Valor<input name="amount" type="number" min="0.01" step="0.01" required value="${h(m.amount)}"></label>
        <label class="vp-field">Fecha del pago<input name="paid_on" type="date" required value="${h(todayIso())}"></label>
        <label class="vp-field">Medio<select name="method" required>${Object.entries(methods).map(([k, v]) => `<option value="${h(k)}">${h(v)}</option>`).join("")}</select></label>
        <label class="vp-field">Referencia<input name="reference" maxlength="60" autocomplete="off" placeholder="código de la transacción"></label>
        <label class="vp-field vp-bill-wide">Nota<input name="note" maxlength="500" autocomplete="off"></label>
        <p class="vp-login-hint vp-bill-wide">Queda «por validar» hasta que lo marques como validado. No escribas números de tarjeta ni de cuentas bancarias.</p>
        ${err}<div class="vp-actions vp-bill-wide"><button class="vp-btn vp-btn-primary" type="submit" ${model.busy ? "disabled" : ""}>Registrar pago</button><button class="vp-btn" type="button" data-vpb-close>Cancelar</button></div></form>`;
    } else if (m.type === "void") {
      body = `<form class="vp-form-grid" data-vpb-void-form><p class="vp-login-hint vp-bill-wide">${m.code ? `El comprobante ${h(m.code)} queda marcado como ANULADO; no se borra y su número no se reutiliza.` : "El pago por validar queda ANULADO y la cuota vuelve a deberse (si lo reportó el cliente, el recordatorio vuelve a salir)."}</p>
        <label class="vp-field vp-bill-wide">Motivo<input name="reason" required minlength="5" maxlength="500" autocomplete="off"></label>
        ${err}<div class="vp-actions vp-bill-wide"><button class="vp-btn vp-btn-danger" type="submit" ${model.busy ? "disabled" : ""}>Anular pago</button><button class="vp-btn" type="button" data-vpb-close>Cancelar</button></div></form>`;
    } else if (m.type === "type") {
      body = `<form class="vp-form-grid" data-vpb-type-form><label class="vp-field vp-bill-wide">Nombre del tipo<input name="label" required minlength="2" maxlength="80" autocomplete="off"></label>
        ${err}<div class="vp-actions vp-bill-wide"><button class="vp-btn vp-btn-primary" type="submit">Agregar</button><button class="vp-btn" type="button" data-vpb-close>Cancelar</button></div></form>`;
    } else {
      body = `<p class="vp-login-hint">${h(m.message)}</p>${err}<div class="vp-actions"><button class="vp-btn vp-btn-primary" type="button" data-vpb-confirm ${model.busy ? "disabled" : ""}>${h(m.cta || "Confirmar")}</button><button class="vp-btn" type="button" data-vpb-close>Cancelar</button></div>`;
    }
    return `<div class="vp-modal" data-vpb-modal><div class="vp-panel vp-modal-card" role="dialog" aria-modal="true">${head}${body}</div></div>`;
  }

  // ------------------------------------------------------------ redactar contrato
  // Paso 1: empresa (registradas SIN contrato). Paso 2: formulario precargado
  // (módulos activos, fecha sugerida). Paso 3: vista previa y "Generar y guardar".
  const CLIENT_FIELDS = [["legal_name", "Razón social"], ["doc_id", "NIT o CC"], ["representative", "Representante"], ["address", "Dirección"],
    ["email", "Correo"], ["phone", "Teléfono"]];
  const PROVIDER_FIELDS = [["name", "Nombre"], ["trade_name", "Marca"], ["doc_id", "Documento o NIT"], ["email", "Correo"], ["phones", "Teléfonos"], ["city", "Ciudad"],
    ["zelle_name", "Nombre del titular en Zelle"], ["zelle_contact", "Zelle (correo o teléfono)"]];
  const LANGUAGES = [["es", "Español"], ["es_en", "Bilingüe ES-EN"]];
  const PAY_METHODS = [["qr", "QR"], ["zelle", "Zelle"]];

  function blankOr(value) { return value === null || value === undefined || value === "" ? `<mark class="vp-bill-blank">______________</mark>` : h(value); }
  function segments(list) {
    return arr(list).map((s) => (s[0] === "b" ? `<mark class="vp-bill-blank">______________</mark>` : s[0] === "s" ? `<mark class="vp-bill-blank">______</mark>` : h(s[1]))).join("");
  }

  function draftPick() {
    const d = model.draft;
    const list = arr(d.companies);
    return `<section class="vp-panel vp-section"><h2>1. Elige la empresa</h2>
      <p class="vp-login-hint">Solo empresas registradas (no demos) que todavía no tienen contrato.</p>
      ${list.length ? `<ul class="vp-actions-list">${list.map((c) => `<li class="vp-action vp-toggle-row"><b>${h(c.name)}</b>
        <button class="vp-btn vp-btn-sm vp-btn-primary" type="button" data-vpb-draft-pick="${h(c.id)}">Redactar</button></li>`).join("")}</ul>`
        : `<div class="vp-empty">Todas las empresas registradas ya tienen contrato.</div>`}</section>`;
  }

  function draftForm() {
    const d = model.draft;
    const f = d.form;
    const types = arr(d.types);
    const active = arr(d.prefill && d.prefill.modules);
    const chosen = new Set(arr(f.modules).map((m) => m.code));
    const byCode = Object.fromEntries(arr(f.modules).map((m) => [m.code, m]));
    const cl = f.client || {};
    const sur = f.surcharge || {};
    const lang = f.language === "es_en" ? "es_en" : "es";
    const pay = f.payment_method === "zelle" ? "zelle" : "qr";
    const prov = d.provider || {};
    const zelleMissing = [["zelle_name", "nombre del titular"], ["zelle_contact", "correo o teléfono"]].filter(([k]) => !prov[k]).map(([, l]) => l);
    return `<form class="vp-form-grid" data-vpb-draft-form>
      <section class="vp-panel vp-section vp-bill-wide"><h2>2. Datos del contrato · ${h(d.prefill && d.prefill.company && d.prefill.company.name)}</h2>
        ${d.prefill && d.prefill.current ? `<p class="vp-login-hint">Editas ${h(d.prefill.current.number)} versión ${h(d.prefill.current.version)}: al guardar se genera la versión ${h(Number(d.prefill.current.version) + 1)} y la anterior queda en el historial.</p>` : ""}
        ${f.from_manual ? `<p class="vp-login-hint">Redactas desde el contrato registrado a mano (precargado con su tipo, inicio, mínimo, ventana, moneda y tramos). Al generar, el contrato a mano queda guardado en el historial (no se borra), el redactado pasa a ser el vigente (versión 1) y las cuotas se recalculan sin duplicar.</p>` : ""}
        <div class="vp-form-grid">
        <label class="vp-field">Idioma del contrato<select name="language" data-vpb-draft-redraw>${LANGUAGES.map(([v, l]) => `<option value="${v}" ${lang === v ? "selected" : ""}>${h(l)}</option>`).join("")}</select></label>
        <label class="vp-field">Medio de pago<select name="payment_method" data-vpb-draft-redraw>${PAY_METHODS.map(([v, l]) => `<option value="${v}" ${pay === v ? "selected" : ""}>${h(l)}</option>`).join("")}</select></label>
        <label class="vp-field">Tipo de contrato<select name="contract_type" required>${types.map((t) => `<option value="${h(t.code)}" ${f.contract_type === t.code ? "selected" : ""}>${h(t.label)}</option>`).join("")}</select></label>
        <label class="vp-field">Fecha de inicio<input name="start_date" type="date" required value="${h(f.start_date)}"></label>
        <label class="vp-field">Días de prueba (0 = sin prueba)<input name="trial_days" type="number" min="0" max="90" value="${h(f.trial_days ?? 0)}"></label>
        <label class="vp-field">Permanencia mínima (meses)<input name="min_months" type="number" min="0" max="120" value="${h(f.min_months ?? 0)}"></label>
        <label class="vp-field">Moneda<select name="currency">${["COP", "USD"].map((c) => `<option ${f.currency === c ? "selected" : ""}>${c}</option>`).join("")}</select></label>
        <label class="vp-field">Paga desde el día<input name="pay_day_from" type="number" min="1" max="28" required value="${h(f.pay_day_from)}"></label>
        <label class="vp-field">hasta el día<input name="pay_day_to" type="number" min="1" max="28" required value="${h(f.pay_day_to)}"></label>
        ${lang === "es_en" ? `<input type="hidden" name="jurisdiction_city" value="${h(f.jurisdiction_city)}">` : `<label class="vp-field">Ciudad de jurisdicción<input name="jurisdiction_city" maxlength="80" value="${h(f.jurisdiction_city)}" placeholder="vacío = línea para llenar"></label>`}
        <label class="vp-field">Ciudad de firma<input name="sign_city" maxlength="80" value="${h(f.sign_city)}" placeholder="vacío = línea para llenar"></label>
        </div>
        <fieldset class="vp-bill-tiers"><legend>Tramos de precio (el último queda abierto: «en adelante»)</legend>
          ${arr(f.tiers).map((t, i) => `<div class="vp-bill-tier">
            <label class="vp-field">Desde el mes<input name="tier_from_${i}" type="number" min="1" value="${h(t.month_from)}" required></label>
            <label class="vp-field">Hasta el mes<input name="tier_to_${i}" type="number" min="1" value="${h(t.month_to ?? "")}" placeholder="en adelante"></label>
            <label class="vp-field">Valor mensual<input name="tier_amount_${i}" type="number" min="0" step="0.01" value="${h(t.amount)}" required></label>
            ${f.tiers.length > 1 ? `<button class="vp-btn vp-btn-sm" type="button" data-vpb-dtier-del="${i}" aria-label="Quitar tramo">✕</button>` : ""}</div>`).join("")}
          <button class="vp-btn vp-btn-sm" type="button" data-vpb-dtier-add>Agregar tramo</button></fieldset>
        <fieldset class="vp-bill-tiers"><legend>Recargo mensual por ajustes nuevos (opcional)</legend><div class="vp-bill-tier">
          <label class="vp-field">Monto<input name="surcharge_amount" type="number" min="0" step="0.01" value="${h(sur.amount ?? "")}"></label>
          <label class="vp-field">Desde el mes<input name="surcharge_from" type="number" min="1" max="120" value="${h(sur.from_month ?? "")}"></label></div></fieldset>
        ${lang === "es_en" ? `<p class="vp-login-hint">Bilingüe: español e inglés en dos columnas; en caso de diferencia prevalece el español. Ley de Colombia y jueces de Bogotá. Montos y fechas salen en los dos idiomas (USD con punto decimal en la columna en inglés).</p>` : ""}
        ${pay === "zelle" ? `<p class="vp-login-hint">Zelle: el Anexo 2 dice pagar por Zelle al titular y al correo o teléfono de «Datos del proveedor», con la referencia «empresa - mes año», y verificar siempre los datos por los canales oficiales. No lleva QR ni números de cuenta.${lang !== "es_en" || f.currency !== "USD" ? " Zelle va con el contrato Bilingüe ES-EN en USD." : ""}${zelleMissing.length ? ` Falta en «Datos del proveedor»: ${h(zelleMissing.join(" y "))} (sale como línea para llenar).` : ""}</p>` : ""}
      </section>
      <section class="vp-panel vp-section vp-bill-wide"><h2>Datos del cliente</h2>
        <p class="vp-login-hint">Todos son opcionales: si quedan vacíos, el PDF deja una línea para llenar a mano, resaltada en amarillo suave.</p>
        <div class="vp-form-grid">${CLIENT_FIELDS.map(([k, label]) => `<label class="vp-field">${h(label)}<input name="client_${k}" maxlength="200" value="${h(cl[k])}" autocomplete="off"></label>`).join("")}</div>
      </section>
      <section class="vp-panel vp-section vp-bill-wide"><h2>Alcance: módulos activos</h2>
        <p class="vp-login-hint">Salen del sistema con su nombre del catálogo. Puedes ajustar la línea que describe cada uno${lang === "es_en" ? " (y su nombre y línea en inglés para el anexo bilingüe)" : ""}.</p>
        ${active.length ? `<ul class="vp-actions-list">${active.map((m, i) => {
          const cur = byCode[m.code] || m;
          const en = lang === "es_en" ? `<input class="vp-bill-module-line" name="mod_name_en_${i}" maxlength="80" value="${h(cur.name_en || m.name_en || m.name)}" aria-label="Nombre en inglés de ${h(m.name)}" placeholder="Nombre en inglés">
            <input class="vp-bill-module-line" name="mod_line_en_${i}" maxlength="200" value="${h(cur.line_en || m.line_en || m.line)}" aria-label="Qué hace ${h(m.name)} (inglés)" placeholder="Línea en inglés">` : "";
          return `<li class="vp-action vp-bill-module"><label class="vp-check"><input type="checkbox" name="mod_on_${i}" ${chosen.has(m.code) ? "checked" : ""}> <b>${h(m.name)}</b></label>
            <input type="hidden" name="mod_code_${i}" value="${h(m.code)}"><input type="hidden" name="mod_name_${i}" value="${h(cur.name || m.name)}">
            <input class="vp-bill-module-line" name="mod_line_${i}" maxlength="200" value="${h(cur.line || m.line)}" aria-label="Qué hace ${h(m.name)}">${en}</li>`;
        }).join("")}</ul>` : `<div class="vp-empty">La empresa no tiene módulos activos.</div>`}
      </section>
      ${d.error ? `<div class="vp-alert vp-bill-wide" role="alert"><span>${h(d.error)}</span></div>` : ""}
      <div class="vp-actions vp-bill-wide"><button class="vp-btn vp-btn-primary" type="submit" ${model.busy ? "disabled" : ""}>Vista previa</button>
        <button class="vp-btn" type="button" data-vpb-draft-cancel>Cancelar</button></div></form>`;
  }

  function draftPreview() {
    const d = model.draft;
    const p = d.preview || {};
    const v = p.vigencia || {};
    const prov = p.provider || {};
    const cl = p.client || {};
    const cards = [["Proveedor", [[null, `${prov.name || ""} · ${prov.trade_name || "CLONEXA"}`], ["NIT/documento", prov.doc_id], ["Correo", prov.email], ["Teléfonos", prov.phones], ["Ciudad", prov.city]]],
      ["Cliente", [[null, p.company_name], ...CLIENT_FIELDS.map(([k, l]) => [l, cl[k]])]],
      ["Vigencia", [["Modalidad", v.type], ["Inicio del servicio", v.start], ["Prueba", v.trial], ["Primer período pagado", v.paid_start],
        ["Permanencia mínima", v.min_months ? `${v.min_months} meses (hasta el ${v.end})` : "Sin permanencia: mes a mes"]]],
      ["Pago", [["Moneda", p.currency], ["Ventana de pago", (p.pago || {}).window], ["Canal", (p.pago || {}).channel],
        ...(p.surcharge ? [["Recargo por ajustes nuevos", `${p.surcharge.amount_text} desde el período ${p.surcharge.from_month}`]] : [])]]];
    const blocks = {
      CUOTAS: () => `<div class="vp-table-wrap"><table class="vp-table"><thead><tr><th>No.</th><th>Período</th><th>Ventana de pago</th><th>Tarifa</th><th>Observación</th></tr></thead><tbody>
        ${arr(p.schedule).map((r) => `<tr><td>${h(r.seq)}</td><td>${h(r.period)}</td><td>${h(r.window)}</td><td class="vp-mono">${h(r.amount_text)}</td><td>${h(r.note)}</td></tr>`).join("")}</tbody></table></div>`,
      ACCESOS: () => `<dl class="vp-bill-doc-kv">${arr(p.access).map(([k, val]) => `<dt>${h(k)}</dt><dd>${blankOr(val)}</dd>`).join("")}</dl>`,
      QR: () => `<p class="vp-login-hint">${(model.draft.provider || {}).has_qr ? "Aquí va el QR de pago de «Datos del proveedor»." : "Sin QR cargado: el PDF deja la línea para llenarlo. Súbelo en «Datos del proveedor»."}</p>`,
      MODULOS: () => (p.bilingual ? `<div class="vp-bill-doc-bi">${["", "_en"].map((x) => `<ul class="vp-bill-doc-list">${arr(p.modules).map((m) => `<li><b>${h(m["name" + x] || m.name)}</b>: ${h(m["line" + x] || m.line)}</li>`).join("")}</ul>`).join("")}</div>`
        : `<ul class="vp-bill-doc-list">${arr(p.modules).map((m) => `<li><b>${h(m.name)}</b>: ${h(m.line)}</li>`).join("")}</ul>`),
      FIRMAS: () => `<p class="vp-login-hint">Firmas de EL PROVEEDOR y EL CLIENTE.</p>`,
    };
    return `<section class="vp-panel vp-section"><div class="vp-row-between"><h2>3. Vista previa</h2>
        <div class="vp-chip-row"><span class="vp-mini-chip">N.º ${h(p.number)}${d.prefill && d.prefill.current ? "" : " (se confirma al guardar)"}</span><span class="vp-mini-chip">Versión ${h(p.version)}</span><span class="vp-mini-chip">Verificación ${h(p.verification)}</span></div></div>
      <article class="vp-bill-doc">
        <header class="vp-bill-doc-band"><img src="/assets/brand/clonexa-logo-horizontal.svg?v=cx26a" alt="CLONEXA"><span>CONTRATO DE SERVICIO</span></header>
        <h3 class="vp-bill-doc-title">${h(p.title)}</h3><p class="vp-bill-doc-sub">${segments(p.subtitle)}</p>
        <div class="vp-bill-doc-cards">${cards.map(([title, rows]) => `<div class="vp-bill-doc-card"><b>${h(title.toUpperCase())}</b>${rows.map(([k, val]) => `<span>${k ? `${h(k)}: ` : ""}${blankOr(val)}</span>`).join("")}</div>`).join("")}</div>
        <div class="vp-bill-doc-strip">${arr(p.tiers).map((t) => `<div><small>${h(t.label)}</small><b>${h(t.amount_text)}</b></div>`).join("")}
          <div class="is-total"><small>Compromiso mínimo</small><b>${v.min_months ? h(p.commitment_text) : "Mes a mes"}</b></div></div>
        ${v.min_months ? `<p class="vp-login-hint">En letras: ${h(p.commitment_words)}.</p>` : ""}
        <div class="vp-chip-row">${arr(p.modules).map((m) => `<span class="vp-bill-tag">${h(m.name)}</span>`).join("")}</div>
        ${p.bilingual ? `<p class="vp-bill-doc-sub">${h(p.title_en)}<br>${segments(p.subtitle_en)}</p>` : ""}
        ${arr(p.sections).map((s) => (p.bilingual ? bilingualSection(s, blocks) : `<section class="vp-bill-doc-sec">${s.title !== "PARTES" ? `<h4>${h(s.title)}</h4>` : ""}${arr(s.blocks).map((b) => (b.type === "block" ? (blocks[b.name] || (() => ""))() : `<p>${segments(b.segments)}</p>`)).join("")}</section>`)).join("")}
      </article>
      ${d.error ? `<div class="vp-alert" role="alert"><span>${h(d.error)}</span></div>` : ""}
      <div class="vp-actions"><button class="vp-btn vp-btn-primary" type="button" data-vpb-draft-generate ${model.busy ? "disabled" : ""}>Generar y guardar</button>
        <button class="vp-btn" type="button" data-vpb-draft-pdf ${model.busy ? "disabled" : ""}>Ver el PDF</button>
        <button class="vp-btn" type="button" data-vpb-draft-edit>Volver a editar</button>
        ${d.pdfUrl ? `<a class="vp-btn vp-btn-link" href="${h(d.pdfUrl)}" target="_blank" rel="noopener">Abrir el PDF de muestra</a>` : ""}</div></section>`;
  }

  // contrato bilingue: cada seccion en dos columnas (español | inglés), párrafo con párrafo
  function bilingualSection(s, blocks) {
    const head = s.title !== "PARTES" ? `<div class="vp-bill-doc-bi"><h4>${h(s.title)}</h4><h4 class="is-en">${h(s.title_en || s.title)}</h4></div>` : "";
    return `<section class="vp-bill-doc-sec">${head}${arr(s.blocks).map((b) => (b.type === "block" ? (blocks[b.name] || (() => ""))()
      : `<div class="vp-bill-doc-bi"><p>${segments(b.segments)}</p><p class="is-en">${segments(b.segments_en)}</p></div>`)).join("")}</section>`;
  }

  function draftView() {
    const d = model.draft;
    const back = `<p><button class="vp-btn vp-btn-sm vp-btn-link" type="button" data-vpb-draft-cancel>← Facturación</button></p>`;
    const head = `<header class="vp-head"><div><p class="vp-eyebrow">FACTURACIÓN</p><h1 class="vp-title">Redactar contrato</h1></div></header>`;
    if (d.loading) return `${back}${head}<p class="vp-loading">Cargando…</p>`;
    if (d.step === "pick") return `${back}${head}${d.error ? `<div class="vp-alert" role="alert"><span>${h(d.error)}</span></div>` : ""}${draftPick()}`;
    if (d.step === "preview") return `${back}${head}${draftPreview()}`;
    return `${back}${head}${draftForm()}`;
  }

  function readDraftForm(form) {
    const f = Object.fromEntries(new FormData(form).entries());
    const tiers = arr(model.draft.form.tiers).map((_, i) => ({ month_from: Number(f[`tier_from_${i}`]), month_to: f[`tier_to_${i}`] === "" || f[`tier_to_${i}`] === undefined ? null : Number(f[`tier_to_${i}`]), amount: Number(f[`tier_amount_${i}`] || 0) }));
    const modules = arr(model.draft.prefill && model.draft.prefill.modules).map((m, i) => {
      if (!f[`mod_on_${i}`]) return null;
      const prev = arr(model.draft.form.modules).find((x) => x.code === f[`mod_code_${i}`]) || m;
      return { code: f[`mod_code_${i}`], name: f[`mod_name_${i}`], line: f[`mod_line_${i}`] || "",
        name_en: f[`mod_name_en_${i}`] !== undefined ? String(f[`mod_name_en_${i}`]) : (prev.name_en || m.name_en || ""),
        line_en: f[`mod_line_en_${i}`] !== undefined ? String(f[`mod_line_en_${i}`]) : (prev.line_en || m.line_en || "") };
    }).filter(Boolean);
    const client = Object.fromEntries(CLIENT_FIELDS.map(([k]) => [k, String(f[`client_${k}`] || "").trim()]));
    return { contract_type: f.contract_type, start_date: f.start_date, trial_days: Number(f.trial_days || 0), min_months: Number(f.min_months || 0), currency: f.currency || "COP",
      pay_day_from: Number(f.pay_day_from), pay_day_to: Number(f.pay_day_to), tiers, surcharge: { amount: f.surcharge_amount || "", from_month: f.surcharge_from || "" },
      jurisdiction_city: String(f.jurisdiction_city || "").trim(), sign_city: String(f.sign_city || "").trim(), client, modules,
      language: f.language === "es_en" ? "es_en" : "es", payment_method: f.payment_method === "zelle" ? "zelle" : "qr",
      ...(model.draft.form.from_manual ? { from_manual: true } : {}) };
  }

  async function openDraft(companyId, fromManual) {
    model.companyId = "";
    model.provider = null;
    model.draft = { step: companyId ? "form" : "pick", loading: true, companies: [], error: "" };
    draw();
    try {
      if (companyId) {
        const pre = await api.draftPrefill(companyId, !!fromManual);
        Object.assign(model.draft, { companyId, prefill: pre, types: pre.types, form: pre.form, provider: (await api.provider().catch(() => ({}))).provider || {} });
      } else {
        const r = await api.draftCompanies();
        Object.assign(model.draft, { companies: r.companies, types: r.types, provider: r.provider });
      }
    } catch (error) { model.draft.error = error.message; if (companyId) model.draft.step = "pick"; }
    model.draft.loading = false;
    draw();
  }

  // ------------------------------------------------------------ datos del proveedor
  function providerView() {
    const m = model.provider || {};
    const p = m.data || {};
    const back = `<p><button class="vp-btn vp-btn-sm vp-btn-link" type="button" data-vpb-provider-close>← Facturación</button></p>`;
    if (!m.data && !m.error) return `${back}<p class="vp-loading">Cargando…</p>`;
    return `${back}<header class="vp-head"><div><p class="vp-eyebrow">FACTURACIÓN</p><h1 class="vp-title">Datos del proveedor</h1></div></header>
      <p class="vp-login-hint">Los contratos nuevos toman estos datos. Cuando cambien (por ejemplo, al constituirse la sociedad), solo se editan aquí; los contratos ya generados no cambian.</p>
      ${m.error ? `<div class="vp-alert" role="alert"><span>${h(m.error)}</span></div>` : ""}${model.notice ? `<p class="vp-ok-text" role="status">${h(model.notice)}</p>` : ""}
      <div class="vp-sum-grid"><section class="vp-panel vp-section"><h2>Proveedor</h2><form class="vp-form-grid" data-vpb-provider-form>
        ${PROVIDER_FIELDS.map(([k, label]) => `<label class="vp-field ${k === "phones" ? "vp-bill-wide" : ""}">${h(label)}<input name="${k}" maxlength="300" value="${h(p[k])}" ${k === "name" ? "required" : ""} autocomplete="off"></label>`).join("")}
        <div class="vp-actions vp-bill-wide"><button class="vp-btn vp-btn-primary" type="submit" ${model.busy ? "disabled" : ""}>Guardar</button></div></form></section>
      <section class="vp-panel vp-section"><h2>QR de pago</h2>
        ${p.has_qr ? `<img class="vp-bill-qr" src="${h(api.providerQrUrl())}?t=${h(m.stamp || 0)}" alt="QR de pago">` : `<div class="vp-empty">Sin QR todavía.</div>`}
        <form class="vp-form-grid" data-vpb-qr-form><label class="vp-field">${p.has_qr ? "Reemplazar QR" : "Subir QR"}<input name="file" type="file" accept="image/png,image/jpeg,image/webp" required></label>
          <button class="vp-btn" type="submit" ${model.busy ? "disabled" : ""}>Subir</button></form>
        <p class="vp-login-hint">PNG, JPG o WebP hasta 5 MB. Se guarda tal cual en el almacenamiento privado (no en la base de datos).</p></section></div>`;
  }

  async function openProvider() {
    model.companyId = "";
    model.draft = null;
    model.notice = "";
    model.provider = { data: null, error: "", stamp: Date.now() };
    draw();
    try { model.provider.data = (await api.provider()).provider; } catch (error) { model.provider.error = error.message; }
    draw();
  }

  // ------------------------------------------------------------ contrato redactado (detalle)
  // "Ver PDF" lo abre en otra pestaña; "Descargar PDF" lo guarda con su número y versión.
  function pdfButtons(d, doc, files, main) {
    if (!doc.file_id || !files[doc.file_id]) return "";
    const url = h(api.fileUrl(d.company.id, doc.file_id));
    const name = h(`${doc.number}-v${doc.version}.pdf`);
    return `<span class="vp-chip-row"><a class="vp-btn vp-btn-sm ${main ? "vp-btn-primary" : ""}" href="${url}" target="_blank" rel="noopener">Ver PDF</a>
      <a class="vp-btn vp-btn-sm" href="${url}?descargar=1" download="${name}">Descargar PDF</a></span>`;
  }

  function documentsPanel(d) {
    const docs = arr(d.documents);
    const k = d.contract;
    if (!k) return "";
    const files = Object.fromEntries(arr(d.files).map((f) => [f.id, f]));
    const on = k.reminder_enabled !== false;
    return `<section class="vp-panel vp-section"><div class="vp-row-between"><h2>Contrato redactado y recordatorio</h2>
        <button class="vp-btn vp-btn-sm ${on ? "vp-btn-primary" : ""}" type="button" data-vpb-reminder="${on ? "off" : "on"}" aria-pressed="${on}">Recordatorio en el panel: ${on ? "encendido" : "apagado"}</button></div>
      <p class="vp-login-hint">El recordatorio sale en el panel principal (solo dueño o admin) desde el día de pago, si la cuota del mes no está cubierta. Nunca suspende ni bloquea nada.</p>
      ${docs.length && docs[0].is_current ? `<div class="vp-actions vp-bill-pdf-main"><b>Contrato vigente: ${h(docs[0].number)} · versión ${h(docs[0].version)}</b>${pdfButtons(d, docs[0], files, true)}</div>` : ""}
      ${docs.length ? `<ul class="vp-actions-list vp-bill-scroll">${docs.map((doc) => `<li class="vp-action vp-toggle-row"><b>${h(doc.number)} · versión ${h(doc.version)}${doc.is_current ? " · vigente" : ""}</b>
          <small>Verificación ${h(doc.verification)} · ${h(day(doc.created_at))}</small>
          ${pdfButtons(d, doc, files, false)}</li>`).join("")}</ul>
        <div class="vp-actions"><button class="vp-btn vp-btn-sm" type="button" data-vpb-draft-edit-company="${h(d.company.id)}">Editar contrato (genera la versión ${h(Number(docs[0].version) + 1)})</button></div>`
        : `<p class="vp-login-hint">Este contrato se registró a mano: no tiene documento redactado.</p>
          ${d.manual_redraft ? `<div class="vp-actions"><button class="vp-btn vp-btn-sm vp-btn-primary" type="button" data-vpb-draft-manual="${h(d.company.id)}">Redactar desde este contrato</button></div>
            <p class="vp-login-hint">Abre «Redactar contrato» precargado con este contrato. Al generar, el contrato a mano queda en el historial y el redactado pasa a ser el vigente (versión 1).</p>`
            : `<p class="vp-login-hint">Tiene pagos registrados: no se reemplaza desde Redactar contrato.</p>`}`}
      ${arr(d.history).length ? `<h3 class="vp-bill-sub">Historial</h3><ul class="vp-actions-list">${arr(d.history).map((x) => `<li class="vp-action vp-toggle-row"><b>Contrato registrado a mano · ${h((x.snapshot || {}).currency || "")} · inicio ${h(day((x.snapshot || {}).start_date))}</b>
          <small>Reemplazado por el contrato redactado el ${h(day(x.created_at))}</small></li>`).join("")}</ul>` : ""}</section>`;
  }

  // ------------------------------------------------------------ dibujo y carga
  function view() { return `${model.draft ? draftView() : model.provider ? providerView() : model.companyId ? detailView() : boardView()}${modal()}`; }

  function draw() {
    if (!ctx || !ctx.active()) return;
    const root = ctx.root();
    if (root) root.innerHTML = view();
  }

  async function loadLogos(ids) {
    const missing = ids.filter((id) => !(id in model.logos));
    missing.forEach((id) => { model.logos[id] = ""; });
    const got = await Promise.all(missing.map((id) => api.logo(id)));
    missing.forEach((id, i) => { model.logos[id] = got[i]; });
    if (got.some(Boolean)) draw();
  }

  async function loadBoard() {
    model.error = "";
    try { model.data = await api.board(); } catch (error) { model.error = error.message; }
    draw();
    if (model.data) loadLogos(arr(model.data.cards).map((c) => c.company.id));
  }

  async function openCompany(id, focus) {
    model.companyId = id;
    model.detail = null;
    model.edit = null;
    model.error = "";
    model.notice = "";
    draw();
    try { model.detail = await api.company(id); } catch (error) { model.error = error.message; }
    draw();
    loadLogos([id]);
    if (focus === "files" && ctx && ctx.root() && ctx.root().querySelector) {
      const el = ctx.root().querySelector("#vpb-files");
      if (el && el.scrollIntoView) el.scrollIntoView({ block: "start" });
    }
  }

  function startEdit() {
    const k = model.detail && model.detail.contract;
    model.edit = k ? { ...k, tiers: arr(k.tiers).map((t) => ({ ...t })) }
      : { contract_type: "mensual", start_date: todayIso().slice(0, 8) + "01", min_months: 0, currency: "COP", pay_day_from: 1, pay_day_to: 5, status: "vigente", notes: "", tiers: [{ month_from: 1, month_to: null, amount: 0 }] };
  }

  function readForm(form) {
    const f = Object.fromEntries(new FormData(form).entries());
    const tiers = model.edit.tiers.map((_, i) => ({ month_from: Number(f[`tier_from_${i}`]), month_to: f[`tier_to_${i}`] === "" ? null : Number(f[`tier_to_${i}`]), amount: Number(f[`tier_amount_${i}`]) }));
    return { contract_type: f.contract_type, start_date: f.start_date, min_months: Number(f.min_months || 0), currency: String(f.currency || "COP").toUpperCase(),
      pay_day_from: Number(f.pay_day_from), pay_day_to: Number(f.pay_day_to), status: f.status, notes: f.notes || "", tiers };
  }

  async function run(fn, notice) {
    model.busy = true;
    draw();
    try {
      const result = await fn();
      if (result && result.installments) model.detail = { ...model.detail, ...result };
      model.modal = null;
      model.notice = notice || "";
      model.error = "";
      return result;
    } catch (error) {
      if (model.modal) model.modal.error = error.message; else model.error = error.message;
      return null;
    } finally {
      model.busy = false;
      draw();
    }
  }

  async function copy(text) {
    try { await navigator.clipboard.writeText(text); return true; } catch (_) { return false; }
  }

  // ------------------------------------------------------------ eventos
  function onClick(event) {
    if (!ctx || !ctx.active()) return;
    const t = event.target;
    if (!t || !t.closest) return;
    const id = model.companyId;
    const open = t.closest("[data-vpb-open]");
    if (open) { event.preventDefault(); openCompany(open.getAttribute("data-vpb-open"), open.getAttribute("data-vpb-focus") || ""); return; }
    const filter = t.closest("[data-vpb-filter]");
    if (filter) { model.filter = filter.getAttribute("data-vpb-filter"); draw(); return; }
    if (t.closest("[data-vpb-refresh]")) { loadBoard(); return; }
    if (t.closest("[data-vpb-back]")) { model.companyId = ""; model.detail = null; model.error = ""; draw(); loadBoard(); return; }
    if (t.closest("[data-vpb-draft]")) { openDraft(""); return; }
    if (t.closest("[data-vpb-provider]")) { openProvider(); return; }
    if (t.closest("[data-vpb-provider-close]") || t.closest("[data-vpb-draft-cancel]")) { model.draft = null; model.provider = null; model.notice = ""; draw(); loadBoard(); return; }
    const pick = t.closest("[data-vpb-draft-pick]");
    if (pick) { openDraft(pick.getAttribute("data-vpb-draft-pick")); return; }
    const fromManual = t.closest("[data-vpb-draft-manual]");
    if (fromManual) { openDraft(fromManual.getAttribute("data-vpb-draft-manual"), true); return; }
    const editDoc = t.closest("[data-vpb-draft-edit-company]");
    if (editDoc) { openDraft(editDoc.getAttribute("data-vpb-draft-edit-company")); return; }
    if (model.draft && t.closest("[data-vpb-draft-edit]")) { model.draft.step = "form"; model.draft.error = ""; draw(); return; }
    if (model.draft && (t.closest("[data-vpb-dtier-add]") || t.closest("[data-vpb-dtier-del]"))) {
      const form = t.closest("form");
      if (form) model.draft.form = readDraftForm(form);
      const tiers = model.draft.form.tiers;
      const del = t.closest("[data-vpb-dtier-del]");
      if (del) tiers.splice(Number(del.getAttribute("data-vpb-dtier-del")), 1);
      else {
        const last = tiers[tiers.length - 1];
        if (last.month_to === null) last.month_to = last.month_from;
        tiers.push({ month_from: Number(last.month_to) + 1, month_to: null, amount: last.amount });
      }
      draw();
      return;
    }
    if (model.draft && t.closest("[data-vpb-draft-pdf]")) {
      const dr = model.draft;
      model.busy = true; draw();
      api.draftPdf(dr.companyId, dr.form).then((blob) => {
        if (dr.pdfUrl) URL.revokeObjectURL(dr.pdfUrl);
        dr.pdfUrl = URL.createObjectURL(blob);
        window.open(dr.pdfUrl, "_blank");
      }).catch((error) => { dr.error = error.message; }).finally(() => { model.busy = false; draw(); });
      return;
    }
    if (model.draft && t.closest("[data-vpb-draft-generate]")) {
      const dr = model.draft;
      model.modal = { type: "confirm", title: "Generar y guardar el contrato", cta: "Generar y guardar",
        message: "Se crea el contrato con sus cuotas y alertas, se genera el PDF con su número, versión y código de verificación, y se guarda en el almacenamiento privado.",
        run: async () => {
          model.busy = true; draw();
          try {
            const r = await api.draftGenerate(dr.companyId, dr.form);
            model.modal = null;
            model.draft = null;
            await openCompany(dr.companyId);
            model.notice = `Contrato ${r.document.number} versión ${r.document.version} generado y guardado. Verificación ${r.document.verification}.`;
          } catch (error) { if (model.modal) model.modal.error = error.message; }
          model.busy = false; draw();
        } };
      draw();
      return;
    }
    const rem = t.closest("[data-vpb-reminder]");
    if (rem && id) {
      const enabled = rem.getAttribute("data-vpb-reminder") === "on";
      run(async () => { const r = await api.reminder(id, enabled); model.detail = { ...model.detail, documents: r.documents }; return r; },
        enabled ? "Recordatorio en el panel encendido." : "Recordatorio en el panel apagado.");
      return;
    }
    if (t.closest("[data-vpb-close]") || (t.matches && t.matches("[data-vpb-modal]"))) { model.modal = null; draw(); return; }
    if (t.closest("[data-vpb-edit]")) { startEdit(); draw(); return; }
    if (t.closest("[data-vpb-edit-cancel]")) { model.edit = null; draw(); return; }
    if (t.closest("[data-vpb-type-add]")) { model.modal = { type: "type", title: "Nuevo tipo de contrato" }; draw(); return; }
    if (t.closest("[data-vpb-tier-add]")) {
      const form = t.closest("form");
      if (form) Object.assign(model.edit, { ...readForm(form), tiers: readForm(form).tiers });
      const last = model.edit.tiers[model.edit.tiers.length - 1];
      if (last.month_to === null) last.month_to = last.month_from;
      model.edit.tiers.push({ month_from: Number(last.month_to) + 1, month_to: null, amount: last.amount });
      draw();
      return;
    }
    const del = t.closest("[data-vpb-tier-del]");
    if (del) {
      const form = t.closest("form");
      if (form) Object.assign(model.edit, readForm(form));
      model.edit.tiers.splice(Number(del.getAttribute("data-vpb-tier-del")), 1);
      draw();
      return;
    }
    const pay = t.closest("[data-vpb-pay]");
    if (pay) {
      const inst = arr(model.detail && model.detail.installments).find((i) => i.id === pay.getAttribute("data-vpb-pay"));
      if (inst) { model.modal = { type: "pay", title: `Registrar pago · ${period(inst.period)}`, installment: inst.id, amount: Math.max(0, Number(inst.amount) - Number(inst.validated || 0)) || inst.amount }; draw(); }
      return;
    }
    const val = t.closest("[data-vpb-validate]");
    if (val) {
      const pid = val.getAttribute("data-vpb-validate");
      model.modal = { type: "confirm", title: "Marcar como pago validado", cta: "Validar y generar comprobante",
        message: "La cuota queda pagada y se genera el comprobante con el siguiente número consecutivo. ¿Confirmas que el dinero ya llegó?",
        run: () => run(async () => { const r = await api.validate(id, pid); return r; }, "Pago validado. Comprobante generado.") };
      draw();
      return;
    }
    const vd = t.closest("[data-vpb-void]");
    if (vd) { model.modal = { type: "void", title: "Anular pago validado", payment: vd.getAttribute("data-vpb-void"), code: vd.getAttribute("data-vpb-code") }; draw(); return; }
    const ln = t.closest("[data-vpb-link]");
    if (ln) {
      run(async () => {
        const r = await api.link(id, ln.getAttribute("data-vpb-link"));
        const url = `${window.location.origin}${r.url}`;
        const ok = await copy(url);
        if (!ok) throw new Error(`Copia este enlace (vence en 7 días): ${url}`);
        return r;
      }, "Enlace copiado. Vence en 7 días y solo abre este comprobante.");
      return;
    }
    if (t.closest("[data-vpb-confirm]") && model.modal && model.modal.run) { model.modal.run(); }
  }

  function onKey(event) {
    if (!ctx || !ctx.active() || (event.key !== "Enter" && event.key !== " ")) return;
    const card = event.target && event.target.matches && event.target.matches("article[data-vpb-open]") ? event.target : null;
    if (card) { event.preventDefault(); openCompany(card.getAttribute("data-vpb-open")); }
  }

  function onChange(event) {
    if (!ctx || !ctx.active() || !model.draft || model.draft.step !== "form") return;
    const t = event.target;
    if (!t || !t.matches || !t.matches("[data-vpb-draft-redraw]")) return;
    const form = t.closest("form");
    if (form) { model.draft.form = readDraftForm(form); draw(); }
  }

  function onSubmit(event) {
    if (!ctx || !ctx.active()) return;
    const form = event.target;
    if (!form || !form.matches) return;
    const id = model.companyId;
    if (form.matches("[data-vpb-draft-form]") && model.draft) {
      event.preventDefault();
      const dr = model.draft;
      dr.form = readDraftForm(form);
      if (!dr.form.modules.length) { dr.error = "Elige al menos un módulo del alcance."; draw(); return; }
      model.busy = true; dr.error = ""; draw();
      api.draftPreview(dr.companyId, dr.form).then((r) => { dr.preview = r.preview; dr.step = "preview"; })
        .catch((error) => { dr.error = error.message; }).finally(() => { model.busy = false; draw(); });
      return;
    }
    if (form.matches("[data-vpb-provider-form]") && model.provider) {
      event.preventDefault();
      const body = Object.fromEntries(new FormData(form).entries());
      model.busy = true; draw();
      api.saveProvider(body).then((r) => { model.provider.data = r.provider; model.provider.error = ""; model.notice = "Datos del proveedor guardados."; })
        .catch((error) => { model.provider.error = error.message; }).finally(() => { model.busy = false; draw(); });
      return;
    }
    if (form.matches("[data-vpb-qr-form]") && model.provider) {
      event.preventDefault();
      const file = form.querySelector("input[type=file]").files[0];
      if (!file) return;
      if (file.size > 5 * 1024 * 1024) { model.provider.error = "El QR pesa más de 5 MB."; draw(); return; }
      model.busy = true; draw();
      api.uploadQr(file).then((r) => { model.provider.data = r.provider; model.provider.stamp = Date.now(); model.provider.error = ""; model.notice = "QR de pago actualizado."; })
        .catch((error) => { model.provider.error = error.message; }).finally(() => { model.busy = false; draw(); });
      return;
    }
    if (form.matches("[data-vpb-contract-form]")) {
      event.preventDefault();
      const body = readForm(form);
      Object.assign(model.edit, body);
      model.modal = { type: "confirm", title: model.detail.contract ? "Guardar cambios del contrato" : "Crear contrato", cta: "Guardar",
        message: model.detail.contract ? "Las cuotas sin pagos validados se recalculan con los nuevos datos. Las ya pagadas no cambian." : "Se generan las cuotas mes a mes desde el inicio del contrato.",
        run: async () => { const r = await run(() => api.saveContract(id, body), "Contrato guardado."); if (r) model.edit = null; draw(); } };
      draw();
      return;
    }
    if (form.matches("[data-vpb-pay-form]")) {
      event.preventDefault();
      const f = Object.fromEntries(new FormData(form).entries());
      run(() => api.pay(id, { ...f, installment_id: model.modal.installment, amount: Number(f.amount) }), "Pago registrado: queda por validar.");
      return;
    }
    if (form.matches("[data-vpb-void-form]")) {
      event.preventDefault();
      const reason = String(new FormData(form).get("reason") || "");
      run(() => api.voidPay(id, model.modal.payment, reason), "Pago anulado. El comprobante quedó marcado como anulado.");
      return;
    }
    if (form.matches("[data-vpb-type-form]")) {
      event.preventDefault();
      const label = String(new FormData(form).get("label") || "");
      run(async () => {
        const r = await api.addType(label);
        model.detail = { ...model.detail, types: r.types };
        if (model.edit) model.edit.contract_type = r.type.code;
        return r;
      }, "Tipo de contrato agregado.");
      return;
    }
    if (form.matches("[data-vpb-upload-form]")) {
      event.preventDefault();
      const file = form.querySelector("input[type=file]").files[0];
      if (!file) return;
      if (file.size > 10 * 1024 * 1024) { model.error = "El contrato pesa más de 10 MB."; draw(); return; }
      run(async () => { const r = await api.upload(id, file); model.detail = { ...model.detail, files: r.files }; return r; }, "Contrato adjuntado.");
    }
  }

  window.CxConsoleSections = window.CxConsoleSections || {};
  window.CxConsoleSections.billing = {
    mount(context) {
      ctx = context;
      if (!bound && typeof document.addEventListener === "function") {
        document.addEventListener("click", onClick);
        document.addEventListener("submit", onSubmit);
        document.addEventListener("change", onChange);
        document.addEventListener("keydown", onKey);
        bound = true;
      }
      const p = (context && context.params) || {};
      model.draft = null;
      model.provider = null;
      if (p.company) { openCompany(p.company, p.focus || ""); return; }
      model.companyId = "";
      draw();
      loadBoard();
    },
    refreshPulse() {},
  };
  window.CxConsoleBilling = { model, api, view, boardView, detailView, chartByMonth, chartByCompany, chartByType, money, stateOf, STATES,
    draftView, providerView, documentsPanel, readDraftForm, segments, onChange };
})();
