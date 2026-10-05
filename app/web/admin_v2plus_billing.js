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
  const model = { data: null, error: "", filter: "todas", logos: {}, companyId: "", detail: null, edit: null, modal: null, busy: false, notice: "" };
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
      <div class="vp-head-actions"><button class="vp-btn" type="button" data-vpb-refresh>Refrescar</button></div></header>`;
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
        const actions = p.status === "por_validar"
          ? `<button class="vp-btn vp-btn-sm vp-btn-primary" type="button" data-vpb-validate="${h(p.id)}">Marcar como pago validado</button>`
          : p.receipt_id ? `<a class="vp-btn vp-btn-sm" href="${h(api.receiptUrl(id, p.receipt_id))}" target="_blank" rel="noopener">${h(code)}${p.receipt_status === "anulado" ? " (anulado)" : ""}</a>
            ${p.status === "validado" ? `<button class="vp-btn vp-btn-sm" type="button" data-vpb-link="${h(p.receipt_id)}">Copiar enlace para el cliente</button>
            <button class="vp-btn vp-btn-sm vp-btn-danger" type="button" data-vpb-void="${h(p.id)}" data-vpb-code="${h(code)}">Anular</button>` : ""}` : "";
        return `<tr><td>${h(period(p.period))}</td><td class="vp-mono">${h(money(p.amount, k.currency))}</td><td>${h(day(p.paid_on))}</td>
          <td>${h(methods[p.method] || p.method)}${p.reference ? ` · <span class="vp-mono">${h(p.reference)}</span>` : ""}</td>
          <td><span class="vp-bill-pill ${cls}">${h(label)}</span>${p.validated_by && p.status !== "por_validar" ? `<small> ${h(p.validated_by)} · ${h(day(p.validated_at))}</small>` : ""}${p.void_reason ? `<small> Motivo: ${h(p.void_reason)}</small>` : ""}</td>
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
      ${calendar(d)}${paymentsPanel(d)}`;
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
      body = `<form class="vp-form-grid" data-vpb-void-form><p class="vp-login-hint vp-bill-wide">El comprobante ${h(m.code)} queda marcado como ANULADO; no se borra y su número no se reutiliza.</p>
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

  // ------------------------------------------------------------ dibujo y carga
  function view() { return `${model.companyId ? detailView() : boardView()}${modal()}`; }

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

  function onSubmit(event) {
    if (!ctx || !ctx.active()) return;
    const form = event.target;
    if (!form || !form.matches) return;
    const id = model.companyId;
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
        document.addEventListener("keydown", onKey);
        bound = true;
      }
      const p = (context && context.params) || {};
      if (p.company) { openCompany(p.company, p.focus || ""); return; }
      model.companyId = "";
      draw();
      loadBoard();
    },
    refreshPulse() {},
  };
  window.CxConsoleBilling = { model, api, view, boardView, detailView, chartByMonth, chartByCompany, chartByType, money, stateOf, STATES };
})();
