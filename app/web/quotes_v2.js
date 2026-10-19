// Cotizaciones y cuentas de cobro v2 (interruptor quotes_v2; hoy solo Velvet).
// Tres pasos: 1 Origen y cliente → 2 Revisar líneas → 3 Generar PDF, con el
// historial a un lado (buscador, Activas / Cobradas / Archivadas, totales y por
// documento: Detalle, PDF, Convertir a cuenta de cobro, Marcar pagada y Archivar).
// Origen: Desde producción (prendas cerradas del periodo, cada cierre se cobra una
// sola vez), Desde referencias (tallas y cantidad) o Manual; siempre se puede
// agregar una línea manual. Los cálculos finales los hace el servidor (/quotes-v2),
// con la misma regla de siempre: la retención no resta del total.
// Textos por t(), dinero y fechas por CxLocale; sin colores propios.
(() => {
  "use strict";

  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const num = (v) => { const n = Number(String(v ?? "").replace(",", ".")); return Number.isFinite(n) ? n : 0; };
  const fill = (s, vars) => (vars ? String(s).replace(/\{(\w+)\}/g, (m, k) => (vars[k] !== undefined ? String(vars[k]) : m)) : String(s));
  const T = (s, vars) => (typeof window !== "undefined" && window.CxI18n && typeof window.CxI18n.t === "function" ? window.CxI18n.t(s, vars) : fill(s, vars));
  const L = () => (typeof window !== "undefined" ? window.CxLocale : null);

  const ORIGINS = [
    ["production", "Desde producción", "Cuenta de cobro con las prendas cerradas del periodo."],
    ["references", "Desde referencias", "Cotización: elige referencias, tallas y cantidad."],
    ["manual", "Manual", "Conceptos libres, como siempre."],
  ];
  const FILTERS = [["active", "Activas"], ["paid", "Cobradas"], ["archived", "Archivadas"]];
  const METHODS = [["transferencia", "Transferencia"], ["efectivo", "Efectivo"], ["cheque", "Cheque"], ["otro", "Otro"]];
  const SOURCE = { op_order: "Orden operacional", reference: "Precio de la referencia", manual: "Escríbelo" };

  const blankClient = () => ({ name: "", document: "", phone: "", address: "", email: "" });
  const model = {
    step: 1, origin: "production", from: "", to: "", client: blankClient(), lines: [], prod: null, refs: null, refQuery: "",
    picks: {}, discount: "", retention: "", payment: { method: "transferencia", name: "", data: "" }, notes: "",
    useSignature: true, defaults: null, busy: "", error: "", done: null, denied: false,
    hist: { q: "", status: "active", data: null, open: "", confirm: "" }, report: null,
  };
  let ctx = null;
  let bound = false;

  // ------------------------------------------------------------ formatos
  function money(v) {
    const legacy = (x) => `$ ${Math.round(num(x)).toLocaleString("es-CO")}`;
    const loc = L();
    return loc && typeof loc.money === "function" ? loc.money(num(v), legacy) : legacy(v);
  }
  const lang = () => (window.CxI18n && window.CxI18n.locale ? window.CxI18n.locale() : "es-CO");
  function day(value) {
    if (!value) return "—";
    const loc = L();
    if (loc && typeof loc.dateTime === "function") return loc.dateTime(String(value), { day: "2-digit", month: "short", year: "numeric" }, lang()) || "—";
    return String(value).slice(0, 10);
  }
  function today() {
    const loc = L();
    return (loc && typeof loc.filterDay === "function" && loc.filterDay(new Date())) || new Date().toISOString().slice(0, 10);
  }
  const monthStart = () => `${today().slice(0, 8)}01`;

  // Mismo cálculo que el servidor (para el resumen mientras se escribe).
  function summary() {
    const subtotal = model.lines.reduce((s, l) => s + Math.max(0, num(l.quantity)) * Math.max(0, num(l.unit_price)), 0);
    const discount = Math.min(Math.max(0, num(model.discount)), subtotal);
    const retention = Math.round(subtotal * Math.min(100, Math.max(0, num(model.retention)))) / 100;
    return { subtotal, discount, retention, total: Math.max(0, subtotal - discount) };
  }

  // ------------------------------------------------------------ datos
  const base = () => `${ctx.apiBase}/quotes-v2/companies/${encodeURIComponent(ctx.companyId)}`;
  async function api(path, opts = {}) {
    const t = ctx.token();
    const res = await fetch(`${base()}${path}`, { method: opts.method || "GET", body: opts.body ? JSON.stringify(opts.body) : undefined,
      credentials: "same-origin", headers: { ...(opts.body ? { "Content-Type": "application/json" } : {}), ...(t ? { Authorization: `Bearer ${t}` } : {}) } });
    if (res.status === 401) throw new Error(T("No pudimos cargar Cotizaciones: sesión vencida, vuelve a entrar."));
    if (res.status === 403) { model.denied = true; throw new Error(T("Cotizaciones es solo del dueño o administrador.")); }
    if (!res.ok) {
      let detail = "";
      try { detail = (await res.json()).detail; } catch (_) {}
      throw new Error(typeof detail === "string" && detail ? T(detail) : T("No se pudo completar. Intenta de nuevo."));
    }
    return opts.raw ? res : res.json();
  }

  async function run(label, fn) {
    model.busy = label; model.error = ""; draw();
    try { await fn(); } catch (e) { model.error = e.message || T("No se pudo completar. Intenta de nuevo."); } finally { model.busy = ""; draw(); }
  }

  async function loadDefaults() {
    const d = await api("/defaults");
    model.defaults = d;
    if (d.payment) model.payment = { method: d.payment.method || "transferencia", name: d.payment.name || "", data: d.payment.data || "" };
    model.useSignature = Boolean(d.signature);
  }

  async function loadProduction() {
    model.prod = await api(`/from-production?date_from=${encodeURIComponent(model.from)}&date_to=${encodeURIComponent(model.to)}`);
  }
  async function loadRefs() { model.refs = (await api("/references")).references || []; }

  async function loadHistory() {
    const p = new URLSearchParams({ q: model.hist.q, status: model.hist.status });
    model.hist.data = await api(`/documents?${p}`);
    model.report = await api(`/report?date_from=${monthStart()}&date_to=${today()}`);
  }

  // Líneas del paso 2 según el origen (las manuales que ya existan se conservan).
  function buildLines() {
    const manual = model.lines.filter((l) => l.manual);
    let lines = [];
    if (model.origin === "production" && model.prod) {
      lines = arr(model.prod.lines).map((l) => ({ description: l.description, quantity: l.quantity, unit_price: l.unit_price ?? "", key: l.key,
        sizes: l.sizes, closure_ids: l.closure_ids, source: l.price_source, locked: true }));
    } else if (model.origin === "references" && model.refs) {
      for (const r of model.refs) {
        const pick = model.picks[r.key];
        if (!pick) continue;
        const sizes = arr(r.sizes).map((s) => ({ size: s.size, quantity: Math.max(0, Math.round(num(pick[s.size]))) })).filter((s) => s.quantity > 0);
        if (!sizes.length) continue;
        lines.push({ description: `${r.name} · ${sizes.map((s) => `${s.size} ${s.quantity}`).join(" / ")}`, quantity: sizes.reduce((a, s) => a + s.quantity, 0),
          unit_price: r.unit_price ?? "", key: r.key, sizes, source: r.price_source, locked: true });
      }
    }
    model.lines = lines.concat(manual.length || model.origin !== "manual" ? manual : [{ description: "", quantity: 1, unit_price: "", manual: true }]);
  }

  function payload() {
    const discounts = [];
    if (num(model.discount) > 0) discounts.push({ name: T("Descuento"), value: num(model.discount), kind: "discount" });
    if (num(model.retention) > 0) discounts.push({ name: T("Retención"), percent: num(model.retention), kind: "retention" });
    return {
      origin: model.origin, client: model.client, notes: model.notes, payment: model.payment, discounts,
      period: model.origin === "production" ? { from: model.from, to: model.to } : null,
      signature_id: model.useSignature && model.defaults && model.defaults.signature ? model.defaults.signature.id : null,
      lines: model.lines.filter((l) => String(l.description || "").trim()).map((l) => ({
        description: l.description, quantity: num(l.quantity), unit_price: l.unit_price === "" ? null : num(l.unit_price),
        key: l.key, sizes: l.sizes, closure_ids: l.closure_ids })),
    };
  }

  function canNext() {
    if (model.step === 1) return Boolean(String(model.client.name || "").trim());
    if (model.step === 2) {
      const lines = model.lines.filter((l) => String(l.description || "").trim());
      return lines.length > 0 && lines.every((l) => l.unit_price !== "" && num(l.quantity) > 0);
    }
    return true;
  }

  async function pdf(id, kind, docType) {
    const tab = kind === "view" ? window.open("", "_blank") : null;
    await run("pdf", async () => {
      try {
        const q = new URLSearchParams({ disposition: kind === "view" ? "inline" : "attachment", ...(docType ? { document_type: docType } : {}) });
        const res = await api(`/documents/${encodeURIComponent(id)}/pdf?${q}`, { raw: true });
        const url = URL.createObjectURL(await res.blob());
        if (kind === "view") { if (tab) tab.location.href = url; else window.open(url, "_blank"); return; }
        const a = document.createElement("a");
        const name = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") || "");
        a.href = url; a.download = name ? name[1] : "documento.pdf";
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 60000);
      } catch (e) { if (tab) tab.close(); throw e; }
    });
  }

  // ------------------------------------------------------------ vistas
  function head() {
    const c = (model.defaults && model.defaults.company) || {};
    const logo = c.logo_url ? `<img class="qv-logo" src="${h(c.logo_url)}" alt="">` : `<span class="qv-logo qv-logo-txt">${h(String(c.name || "?").slice(0, 1))}</span>`;
    return `<header class="client-hero qv-head"><div class="qv-brand">${logo}<div><p class="client-eyebrow">${h(c.name || "")}</p>
      <h1 class="client-title">${h(T("Cotizaciones y cuentas de cobro"))}</h1></div></div></header>`;
  }

  function steps() {
    const names = ["Origen y cliente", "Revisar líneas", "Generar PDF"];
    return `<ol class="qv-steps">${names.map((n, i) => `<li class="${model.step === i + 1 ? "is-on" : model.step > i + 1 ? "is-done" : ""}" ${model.step === i + 1 ? 'aria-current="step"' : ""}>
      <b>${i + 1}</b><span>${h(T(n))}</span></li>`).join("")}</ol>`;
  }

  function clientBox() {
    const list = arr(model.defaults && model.defaults.clients);
    const c = model.client;
    const field = (k, label, type = "text") => `<label class="qv-field">${h(T(label))}<input type="${type}" data-qv-client="${k}" value="${h(c[k])}" maxlength="220"></label>`;
    return `<section class="qv-box"><h3 class="qv-h3">${h(T("Cliente"))}</h3>
      <div class="qv-row"><label class="qv-field qv-grow">${h(T("Buscar cliente anterior"))}<input type="search" list="qvClients" data-qv-pick-client placeholder="${h(T("Nombre o NIT"))}"></label>
        <button type="button" class="qv-btn" data-qv-new-client>${h(T("Nuevo cliente"))}</button></div>
      <datalist id="qvClients">${list.map((x) => `<option value="${h(x.client_name)}${x.client_document ? ` · ${h(x.client_document)}` : ""}"></option>`).join("")}</datalist>
      <div class="qv-grid2">${field("name", "Nombre o razón social")}${field("document", "NIT o documento")}${field("phone", "Teléfono", "tel")}${field("email", "Correo", "email")}</div>
      ${field("address", "Dirección")}</section>`;
  }

  function prodBox() {
    const p = model.prod;
    const notice = p && num(p.already_charged_total) > 0
      ? `<p class="qv-warn" role="status">${h(arr(p.already_charged).map((x) => T("{n} prendas ya cobradas en {doc}", { n: x.quantity, doc: x.document })).join(" · "))}</p>` : "";
    const body = !p ? "" : arr(p.lines).length ? `<ul class="qv-mini">${arr(p.lines).map((l) => `<li><span>${h(l.name)}</span><span>${h(arr(l.sizes).map((s) => `${s.size} ${s.quantity}`).join(" · "))}</span><b>${h(l.quantity)}</b></li>`).join("")}</ul>`
      : `<p class="qv-muted">${h(T("No hay prendas cerradas sin cobrar en el periodo."))}</p>`;
    return `<section class="qv-box"><h3 class="qv-h3">${h(T("Periodo"))}</h3><div class="qv-row">
      <label class="qv-field">${h(T("Desde"))}<input type="date" data-qv-from value="${h(model.from)}"></label>
      <label class="qv-field">${h(T("Hasta"))}<input type="date" data-qv-to value="${h(model.to)}"></label></div>${notice}${body}</section>`;
  }

  function refsBox() {
    if (!model.refs) return `<section class="qv-box"><p class="qv-muted">${h(T("Cargando…"))}</p></section>`;
    const needle = model.refQuery.trim().toLowerCase();
    const list = model.refs.filter((r) => !needle || r.name.toLowerCase().includes(needle));
    return `<section class="qv-box"><h3 class="qv-h3">${h(T("Referencias"))}</h3>
      <label class="qv-field">${h(T("Buscar referencia"))}<input type="search" data-qv-ref-q value="${h(model.refQuery)}"></label>
      <ul class="qv-refs">${list.map((r) => `<li><div class="qv-ref-name"><b>${h(r.name)}</b><small>${r.unit_price != null ? h(money(r.unit_price)) : h(T("Sin valor"))}</small></div>
        <div class="qv-sizes">${arr(r.sizes).map((s) => `<label class="qv-size">${h(s.size)}<input type="number" min="0" step="1" inputmode="numeric" data-qv-ref="${h(r.key)}" data-qv-size="${h(s.size)}" value="${h((model.picks[r.key] || {})[s.size] || "")}" aria-label="${h(`${r.name} ${s.size}`)}"></label>`).join("")}</div></li>`).join("")
        || `<li class="qv-muted">${h(T("Sin referencias."))}</li>`}</ul></section>`;
  }

  function step1() {
    return `<div class="qv-origins" role="radiogroup" aria-label="${h(T("Origen"))}">${ORIGINS.map(([k, label, sub]) => `<button type="button" role="radio" aria-checked="${model.origin === k}" class="qv-origin ${model.origin === k ? "is-on" : ""}" data-qv-origin="${k}">
      <b>${h(T(label))}</b><span>${h(T(sub))}</span></button>`).join("")}</div>
      ${model.origin === "production" ? prodBox() : model.origin === "references" ? refsBox() : ""}${clientBox()}`;
  }

  function step2() {
    const s = summary();
    const rows = model.lines.map((l, i) => `<div class="qv-line" role="row">
      <label class="qv-field qv-desc">${h(T("Concepto"))}<input data-qv-line="${i}" data-qv-k="description" value="${h(l.description)}" ${l.locked ? "readonly" : ""} maxlength="600"></label>
      <label class="qv-field">${h(T("Cantidad"))}<input type="number" min="0" step="1" data-qv-line="${i}" data-qv-k="quantity" value="${h(l.quantity)}" ${l.closure_ids ? "readonly" : ""}></label>
      <label class="qv-field">${h(T("Valor por prenda"))}<input type="number" min="0" step="1" data-qv-line="${i}" data-qv-k="unit_price" value="${h(l.unit_price)}" ${l.unit_price === "" ? 'aria-invalid="true"' : ""}>
        ${l.source ? `<small class="qv-src">${h(T(SOURCE[l.source] || l.source))}</small>` : ""}</label>
      <span class="qv-line-total"><small>${h(T("Total"))}</small><b data-qv-line-total="${i}">${h(money(num(l.quantity) * num(l.unit_price)))}</b></span>
      ${l.locked ? "" : `<button type="button" class="qv-btn qv-x" data-qv-del="${i}" aria-label="${h(T("Quitar línea"))}">×</button>`}</div>`).join("");
    const sig = model.defaults && model.defaults.signature;
    return `<section class="qv-box"><h3 class="qv-h3">${h(T("Líneas"))}</h3><div class="qv-lines" role="table">${rows || `<p class="qv-muted">${h(T("Sin líneas."))}</p>`}</div>
      <button type="button" class="qv-btn" data-qv-add>${h(T("+ Línea manual"))}</button></section>
      <div class="qv-grid2"><section class="qv-box"><h3 class="qv-h3">${h(T("Descuento y retención"))}</h3>
        <label class="qv-field">${h(T("Descuento"))}<input type="number" min="0" step="1" data-qv-discount value="${h(model.discount)}"></label>
        <label class="qv-field">${h(T("Retención (%)"))}<input type="number" min="0" max="100" step="0.1" data-qv-retention value="${h(model.retention)}"></label></section>
        <section class="qv-box qv-sum" data-qv-sum>${sumHtml(s)}</section></div>
      <section class="qv-box"><h3 class="qv-h3">${h(T("Pago"))}</h3><div class="qv-grid2">
        <label class="qv-field">${h(T("Método"))}<select data-qv-pay="method">${METHODS.map(([k, l]) => `<option value="${k}" ${model.payment.method === k ? "selected" : ""}>${h(T(l))}</option>`).join("")}</select></label>
        <label class="qv-field">${h(T("Banco o titular"))}<input data-qv-pay="name" value="${h(model.payment.name)}" maxlength="120"></label></div>
        <label class="qv-field">${h(T("Datos de pago"))}<input data-qv-pay="data" value="${h(model.payment.data)}" maxlength="1200"></label>
        <label class="qv-field">${h(T("Notas"))}<input data-qv-notes value="${h(model.notes)}" maxlength="2500"></label></section>
      <section class="qv-box"><h3 class="qv-h3">${h(T("Firma"))}</h3>
        ${sig ? `<label class="qv-check"><input type="checkbox" data-qv-use-sig ${model.useSignature ? "checked" : ""}> ${h(T("Usar la firma guardada"))}</label>` : `<p class="qv-muted">${h(T("Sin firma guardada."))}</p>`}
        <label class="qv-field">${h(T("Subir una firma nueva (PNG o JPG)"))}<input type="file" accept="image/png,image/jpeg,image/webp" data-qv-sig-file></label></section>`;
  }

  function sumHtml(s) {
    return `<h3 class="qv-h3">${h(T("Resumen"))}</h3><dl class="qv-dl"><dt>${h(T("Subtotal"))}</dt><dd>${h(money(s.subtotal))}</dd>
      <dt>${h(T("Descuento"))}</dt><dd>− ${h(money(s.discount))}</dd><dt>${h(T("Retención (no resta del total)"))}</dt><dd>${h(money(s.retention))}</dd>
      <dt class="qv-total">${h(T("Total"))}</dt><dd class="qv-total">${h(money(s.total))}</dd></dl>`;
  }

  function step3() {
    if (model.done) {
      const d = model.done;
      return `<section class="qv-box qv-done"><p class="client-eyebrow">${h(T(d.document_label))}</p><h2 class="qv-number">${h(d.document_number)}</h2>
        <p>${h(d.client_name)} · <b>${h(money(d.total))}</b></p>
        <div class="qv-row"><button type="button" class="qv-btn" data-qv-pdf="${h(d.id)}" data-qv-kind="view">${h(T("Ver PDF"))}</button>
          <button type="button" class="client-btn qv-btn is-primary" data-qv-pdf="${h(d.id)}" data-qv-kind="download">${h(T("Descargar PDF"))}</button>
          <button type="button" class="qv-btn" data-qv-reset>${h(T("Nuevo documento"))}</button></div></section>`;
    }
    const s = summary();
    const kind = model.origin === "production" ? "Cuenta de cobro" : "Cotización";
    return `<section class="qv-box"><h3 class="qv-h3">${h(T("Confirmar"))}</h3><dl class="qv-dl"><dt>${h(T("Documento"))}</dt><dd>${h(T(kind))}</dd>
      <dt>${h(T("Cliente"))}</dt><dd>${h(model.client.name)}</dd><dt>${h(T("Líneas"))}</dt><dd>${h(model.lines.filter((l) => String(l.description || "").trim()).length)}</dd>
      <dt class="qv-total">${h(T("Total"))}</dt><dd class="qv-total">${h(money(s.total))}</dd></dl>
      <button type="button" class="client-btn qv-btn is-primary" data-qv-emit ${model.busy ? "disabled" : ""}>${h(T("Emitir y generar PDF"))}</button></section>`;
  }

  function nav() {
    if (model.done) return "";
    return `<div class="qv-nav">${model.step > 1 ? `<button type="button" class="qv-btn" data-qv-back>${h(T("Atrás"))}</button>` : "<span></span>"}
      ${model.step < 3 ? `<button type="button" class="client-btn qv-btn is-primary" data-qv-next ${canNext() && !model.busy ? "" : "disabled"}>${h(T("Siguiente"))}</button>` : ""}</div>`;
  }

  function docActions(d) {
    const c = model.hist.confirm === d.id;
    const items = model.hist.open === d.id ? `<ul class="qv-mini">${arr(d.items).map((i) => `<li><span>${h(i.description)}</span><span>${h(i.quantity)} × ${h(money(i.unit_price))}</span><b>${h(money(i.total))}</b></li>`).join("")}</ul>` : "";
    return `<div class="qv-acts">
      <button type="button" class="qv-btn" data-qv-detail="${h(d.id)}" aria-expanded="${model.hist.open === d.id}">${h(T("Detalle"))}</button>
      <button type="button" class="qv-btn" data-qv-pdf="${h(d.id)}" data-qv-kind="download">${h(T("PDF"))}</button>
      ${d.status === "issued" ? `<button type="button" class="qv-btn" data-qv-convert="${h(d.id)}">${h(T("Convertir a cuenta de cobro"))}</button>` : ""}
      ${d.status === "converted" && !d.paid_at ? `<button type="button" class="qv-btn" data-qv-paid="${h(d.id)}">${h(T("Marcar pagada"))}</button>` : ""}
      ${d.status !== "archived" ? (c ? `<button type="button" class="qv-btn is-danger" data-qv-archive="${h(d.id)}">${h(T("Sí, archivar"))}</button><button type="button" class="qv-btn" data-qv-cancel>${h(T("No"))}</button>`
        : `<button type="button" class="qv-btn" data-qv-ask="${h(d.id)}">${h(T("Archivar"))}</button>`) : ""}</div>${items}
      ${c && d.charged_closures ? `<p class="qv-muted">${h(T("Se liberan {n} cierres para cobrarlos de nuevo.", { n: d.charged_closures }))}</p>` : ""}`;
  }

  function history() {
    const data = model.hist.data;
    const tot = (data && data.totals) || {};
    const r = model.report;
    return `<aside class="client-panel qv-hist"><h2 class="client-eyebrow qv-h">${h(T("Historial"))}</h2>
      ${r ? `<div class="qv-kpis"><div><small>${h(T("Cobrado este mes"))}</small><b>${h(money(r.collected))}</b></div><div><small>${h(T("Por cobrar"))}</small><b>${h(money(r.pending))}</b></div></div>` : ""}
      <label class="qv-field">${h(T("Buscar"))}<input type="search" data-qv-hq value="${h(model.hist.q)}" placeholder="${h(T("Cliente, NIT o número"))}"></label>
      <div class="qv-seg" role="group">${FILTERS.map(([k, l]) => `<button type="button" class="${model.hist.status === k ? "client-btn is-on" : ""}" aria-pressed="${model.hist.status === k}" data-qv-hstatus="${k}">
        ${h(T(l))} <small>${h(num((tot[k] || {}).count))}</small></button>`).join("")}</div>
      <p class="qv-muted">${h(T("Total {m}", { m: money((tot[model.hist.status] || {}).amount) }))}</p>
      <ul class="qv-docs">${data ? arr(data.documents).map((d) => `<li class="qv-doc is-${h(d.status)}"><div class="qv-doc-top"><b>${h(d.document_number)}</b><span>${h(money(d.total))}</span></div>
        <div class="qv-doc-sub"><span>${h(d.client_name)}</span><span>${h(day(d.created_at))}</span></div>
        <div class="qv-doc-sub"><span>${h(T(d.document_label))}${d.paid_at ? ` · ${h(T("Pagada"))}` : ""}</span>${d.charged_closures ? `<span>${h(T("{n} cierres", { n: d.charged_closures }))}</span>` : ""}</div>
        ${docActions(d)}</li>`).join("") || `<li class="qv-muted">${h(T("Sin documentos."))}</li>` : `<li class="qv-muted">${h(T("Cargando…"))}</li>`}</ul></aside>`;
  }

  function view() {
    if (model.denied) return `<div class="qv-root" data-qv-root>${head()}<section class="client-panel"><p class="qv-muted">${h(T("Cotizaciones es solo del dueño o administrador."))}</p></section></div>`;
    const body = model.step === 1 ? step1() : model.step === 2 ? step2() : step3();
    return `<div class="qv-root" data-qv-root>${head()}<div class="qv-layout"><section class="client-panel qv-main">${steps()}
      ${model.error ? `<div class="qv-notice" role="alert">${h(model.error)} <button type="button" class="qv-btn" data-qv-retry>${h(T("Reintentar"))}</button></div>` : ""}${body}${nav()}</section>${history()}</div></div>`;
  }

  function draw() { if (!ctx) return; const host = ctx.host(); if (host) host.innerHTML = view(); }
  function drawSum() {
    const host = ctx && ctx.host();
    if (!host || !host.querySelector) return;
    const box = host.querySelector("[data-qv-sum]");
    if (box) box.innerHTML = sumHtml(summary());
    model.lines.forEach((l, i) => { const el = host.querySelector(`[data-qv-line-total="${i}"]`); if (el) el.textContent = money(num(l.quantity) * num(l.unit_price)); });
    const next = host.querySelector("[data-qv-next]");
    if (next) next.disabled = !canNext();
  }

  // ------------------------------------------------------------ eventos
  function reset() {
    Object.assign(model, { step: 1, client: blankClient(), lines: [], prod: null, picks: {}, discount: "", retention: "", notes: "", done: null, error: "" });
    if (model.origin === "production") run("prod", loadProduction);
  }

  function onClick(event) {
    const t = event.target;
    if (!ctx || !t || !t.closest || !t.closest("[data-qv-root]")) return;
    const attr = (a) => { const el = t.closest(`[${a}]`); return el ? el.getAttribute(a) : null; };
    let v;
    if ((v = attr("data-qv-origin"))) {
      model.origin = v; model.lines = [];
      if (v === "production" && !model.prod) run("prod", loadProduction);
      else if (v === "references" && !model.refs) run("refs", loadRefs);
      else draw();
      return;
    }
    if (attr("data-qv-retry") !== null) { run("init", init); return; }
    if (attr("data-qv-new-client") !== null) { model.client = blankClient(); draw(); return; }
    if (attr("data-qv-next") !== null) { if (!canNext()) return; if (model.step === 1) buildLines(); model.step += 1; draw(); return; }
    if (attr("data-qv-back") !== null) { model.step -= 1; draw(); return; }
    if (attr("data-qv-add") !== null) { model.lines.push({ description: "", quantity: 1, unit_price: "", manual: true }); draw(); return; }
    if ((v = attr("data-qv-del")) !== null) { model.lines.splice(Number(v), 1); draw(); return; }
    if (attr("data-qv-emit") !== null) {
      run("emit", async () => {
        const res = await api("/documents", { method: "POST", body: payload() });
        model.done = res.document;
        if (model.origin === "production") model.prod = null;
        await loadHistory();
      });
      return;
    }
    if (attr("data-qv-reset") !== null) { reset(); draw(); return; }
    if ((v = attr("data-qv-pdf"))) { pdf(v, attr("data-qv-kind") || "download"); return; }
    if ((v = attr("data-qv-hstatus"))) { model.hist.status = v; run("hist", loadHistory); return; }
    if ((v = attr("data-qv-detail"))) { model.hist.open = model.hist.open === v ? "" : v; draw(); return; }
    if ((v = attr("data-qv-ask"))) { model.hist.confirm = v; draw(); return; }
    if (attr("data-qv-cancel") !== null) { model.hist.confirm = ""; draw(); return; }
    if ((v = attr("data-qv-archive"))) { model.hist.confirm = ""; run("arch", async () => { await api(`/documents/${encodeURIComponent(v)}/archive`, { method: "POST", body: {} }); model.prod = null; await loadHistory(); }); return; }
    if ((v = attr("data-qv-convert"))) { run("conv", async () => { await api(`/documents/${encodeURIComponent(v)}/convert`, { method: "POST", body: {} }); await loadHistory(); }); return; }
    if ((v = attr("data-qv-paid"))) { run("paid", async () => { await api(`/documents/${encodeURIComponent(v)}/paid`, { method: "POST", body: { paid: true } }); await loadHistory(); }); }
  }

  let hqTimer = null;
  function onInput(event) {
    const t = event.target;
    if (!ctx || !t || !t.closest || !t.closest("[data-qv-root]")) return;
    const a = (k) => t.getAttribute(k);
    if (t.hasAttribute("data-qv-client")) { model.client[a("data-qv-client")] = t.value; drawSum(); return; }
    if (t.hasAttribute("data-qv-line")) { model.lines[Number(a("data-qv-line"))][a("data-qv-k")] = t.value; drawSum(); return; }
    if (t.hasAttribute("data-qv-discount")) { model.discount = t.value; drawSum(); return; }
    if (t.hasAttribute("data-qv-retention")) { model.retention = t.value; drawSum(); return; }
    if (t.hasAttribute("data-qv-pay")) { model.payment[a("data-qv-pay")] = t.value; return; }
    if (t.hasAttribute("data-qv-notes")) { model.notes = t.value; return; }
    if (t.hasAttribute("data-qv-ref")) { const k = a("data-qv-ref"); model.picks[k] = { ...(model.picks[k] || {}), [a("data-qv-size")]: t.value }; return; }
    if (t.hasAttribute("data-qv-hq")) { model.hist.q = t.value; clearTimeout(hqTimer); hqTimer = setTimeout(() => run("hist", loadHistory), 350); }
  }

  function onChange(event) {
    const t = event.target;
    if (!ctx || !t || !t.closest || !t.closest("[data-qv-root]")) return;
    if (t.hasAttribute("data-qv-pick-client")) {
      const value = String(t.value || "").trim().toLowerCase();
      const hit = arr(model.defaults && model.defaults.clients).find((x) => `${x.client_name}${x.client_document ? ` · ${x.client_document}` : ""}`.toLowerCase() === value
        || x.client_name.toLowerCase() === value || (x.client_document && x.client_document.toLowerCase() === value));
      if (hit) { model.client = { name: hit.client_name, document: hit.client_document, phone: hit.client_phone, address: hit.client_address, email: hit.client_email }; draw(); }
      return;
    }
    if (t.hasAttribute("data-qv-from") || t.hasAttribute("data-qv-to")) {
      if (t.hasAttribute("data-qv-from")) model.from = t.value; else model.to = t.value;
      run("prod", loadProduction); return;
    }
    if (t.hasAttribute("data-qv-ref-q")) { model.refQuery = t.value; draw(); return; }
    if (t.hasAttribute("data-qv-use-sig")) { model.useSignature = t.checked; return; }
    if (t.hasAttribute("data-qv-sig-file") && t.files && t.files[0]) {
      const file = t.files[0];
      const reader = new FileReader();
      reader.onload = () => run("sig", async () => {
        const res = await api("/signatures", { method: "POST", body: { data_url: reader.result } });
        model.defaults = { ...(model.defaults || {}), signature: res.signature };
        model.useSignature = true;
      });
      reader.readAsDataURL(file);
    }
  }

  async function mount(context) {
    ctx = context;
    if (!bound && typeof document.addEventListener === "function") {
      document.addEventListener("click", onClick);
      document.addEventListener("input", onInput);
      document.addEventListener("change", onChange);
      bound = true;
    }
    model.from = model.from || monthStart();
    model.to = model.to || today();
    draw();
    await run("init", init);
  }

  async function init() {
    await loadDefaults();
    await Promise.all([loadHistory(), model.origin === "production" ? loadProduction() : Promise.resolve()]);
  }

  window.CxQuotesV2 = { mount, model, view, summary, payload, buildLines, canNext, money };
})();
