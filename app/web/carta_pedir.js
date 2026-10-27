/* CLONEXA 058A · QR y piezas: la carta (la de video o la de fotos, CxCartaApp)
 * para pedir a Domicilio o Para llevar (/pedir?k=...), y la carta del mesero
 * (/carta-mesero?company_id=...&k=...), que SOLO abre con su sesión de mesero.
 *
 * Domicilio: carta -> pedido -> datos (nombre, celular, dirección, barrio,
 * referencia, pago contra entrega, nota y autorización de datos) ->
 * confirmación con el resumen y el estado. Para llevar: nombre, celular y hora
 * aproximada de recogida. Sin pasarela de pagos. Un campo oculto que una
 * persona nunca llena frena a los robots.
 */
(function () {
  "use strict";
  const API = "/api/v1";
  const params = new URLSearchParams(window.location.search);
  const token = params.get("k") || "";
  const companyId = params.get("company_id") || "";
  const isMesero = /\/carta-mesero\/?$/.test(window.location.pathname);
  const S = { data: null, kind: "", app: null, lines: [], screen: "carta", busy: false, error: "", done: null, form: {}, tables: [], table: "" };
  let overlay = null;
  let pollTimer = null;

  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const money = (v) => (window.CxCartaApp ? window.CxCartaApp.money(v, S.data && S.data.carta && S.data.carta.locale) : `$${Math.round(Number(v) || 0).toLocaleString("es-CO")}`);
  const total = () => S.lines.reduce((n, l) => n + l.price * l.quantity, 0);

  function waiterToken() {
    try { return window.localStorage.getItem(`clonexa_waiter_token_${companyId}`) || window.sessionStorage.getItem(`clonexa_waiter_token_${companyId}`) || ""; } catch (_) { return ""; }
  }

  async function api(path, options = {}) {
    const headers = { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) };
    const response = await fetch(`${API}${path}`, { ...options, headers, cache: "no-store" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = data && data.detail;
      const message = Array.isArray(detail) ? (detail[0] && String(detail[0].msg || "").replace(/^Value error, /, "")) : detail;
      const error = new Error(message || "No se pudo completar. Intenta de nuevo.");
      error.status = response.status;
      throw error;
    }
    return data;
  }

  // ------------------------------------------------------------ pantallas
  function ensureOverlay() {
    if (overlay) return overlay;
    overlay = document.createElement("div");
    overlay.className = "cxp";
    overlay.hidden = true;
    document.body.appendChild(overlay);
    overlay.addEventListener("click", onClick);
    overlay.addEventListener("submit", onSubmit);
    overlay.addEventListener("input", onInput);
    return overlay;
  }

  function styles(pal) {
    if (document.getElementById("cxpStyles")) return;
    const p = pal || { base: "#0c0a14", text: "#ffffff", muted: "#c9c3e6", cardSolid: "#1b1726", line: "rgba(255,255,255,.16)", primary: "#7c3aed", onPrimary: "#ffffff" };
    const style = document.createElement("style");
    style.id = "cxpStyles";
    style.textContent = `
      .cxp{position:fixed;inset:0;z-index:90;overflow:auto;background:${p.base};color:${p.text};font-family:${p.font || "system-ui,sans-serif"};padding:16px 16px calc(24px + env(safe-area-inset-bottom))}
      .cxp *{box-sizing:border-box}
      .cxp-wrap{max-width:520px;margin:0 auto;display:grid;gap:14px}
      .cxp-top{display:flex;align-items:center;gap:10px}
      .cxp-top h1{flex:1;margin:0;font-size:22px;line-height:1.2}
      .cxp-ic{min-width:44px;min-height:44px;border-radius:14px;border:1px solid ${p.line};background:transparent;color:inherit;font-size:18px;cursor:pointer}
      .cxp-card{display:grid;gap:10px;padding:14px;border-radius:18px;background:${p.cardSolid};border:1px solid ${p.line}}
      .cxp label{display:grid;gap:6px;font-size:14px;font-weight:700}
      .cxp input,.cxp select,.cxp textarea{width:100%;min-height:48px;padding:12px;border-radius:12px;border:1px solid ${p.line};background:rgba(127,127,127,.08);color:inherit;font:inherit;font-size:16px}
      .cxp textarea{min-height:76px;resize:vertical}
      .cxp .cxp-check{display:flex;align-items:flex-start;gap:10px;font-weight:600}
      .cxp .cxp-check input{width:24px;min-height:24px;height:24px;flex:none;margin:2px 0 0}
      .cxp a{color:inherit;text-decoration:underline}
      .cxp-pay{display:grid;grid-template-columns:1fr 1fr;gap:8px}
      .cxp-pay label{display:flex;align-items:center;gap:8px;min-height:48px;padding:0 12px;border-radius:12px;border:1px solid ${p.line};font-weight:700}
      .cxp-pay input{width:20px;min-height:20px;height:20px;margin:0}
      .cxp-line{display:flex;justify-content:space-between;gap:10px;font-size:14px}
      .cxp-line small{display:block;color:${p.muted}}
      .cxp-total{display:flex;justify-content:space-between;font-size:18px;font-weight:900;border-top:1px solid ${p.line};padding-top:10px}
      .cxp-muted{color:${p.muted};font-size:13px;margin:0}
      .cxp-btn{min-height:52px;border-radius:16px;border:0;padding:0 18px;font:inherit;font-weight:900;font-size:16px;cursor:pointer;background:${p.primary};color:${p.onPrimary}}
      .cxp-btn.ghost{background:transparent;color:inherit;border:1px solid ${p.line}}
      .cxp-btn[disabled]{opacity:.6}
      .cxp-err{margin:0;padding:10px 12px;border-radius:12px;background:rgba(239,68,68,.16);color:inherit;font-weight:700}
      .cxp-ok{font-size:44px;margin:0;text-align:center}
      .cxp-num{font-size:26px;font-weight:900;text-align:center;margin:0}
      .cxp-status{text-align:center;font-weight:900;padding:10px;border-radius:12px;border:1px solid ${p.line}}
      .cxp-hp{position:absolute!important;left:-9999px!important;width:1px!important;height:1px!important;overflow:hidden!important}
      .cxp-tables{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px}
      .cxp-tables button{min-height:56px;border-radius:14px;border:1px solid ${p.line};background:transparent;color:inherit;font:inherit;font-weight:800;cursor:pointer}
      .cxp-tables button.on{background:${p.primary};color:${p.onPrimary};border-color:transparent}
      .cxp-center{min-height:100vh;display:grid;place-items:center;text-align:center;padding:24px;background:#0c0a14;color:#fff;font-family:system-ui,sans-serif}
      .cxp-center .cxp-card{max-width:380px;background:#1b1726;border-color:rgba(255,255,255,.16)}
      .cxp-center a.cxp-btn{display:grid;place-items:center;text-decoration:none}`;
    document.head.appendChild(style);
  }

  function linesHtml() {
    return `${S.lines.map((l) => `<div class="cxp-line"><span>${h(l.quantity)} × ${h(l.name)}${[l.term, ...(l.quick_notes || []), l.note].filter(Boolean).length ? `<small>${h([l.term, ...(l.quick_notes || []), l.note].filter(Boolean).join(" · "))}</small>` : ""}</span><b>${h(money(l.price * l.quantity))}</b></div>`).join("")}`;
  }

  function slots() {
    const out = [];
    const now = new Date(Date.now() + 20 * 60000);
    now.setMinutes(Math.ceil(now.getMinutes() / 15) * 15, 0, 0);
    for (let i = 0; i < 13; i += 1) {
      const t = new Date(now.getTime() + i * 15 * 60000);
      out.push(t.toLocaleTimeString("es-CO", { hour: "numeric", minute: "2-digit" }));
    }
    return out;
  }

  function formHtml() {
    const f = S.form;
    const dom = S.kind === "domicilio";
    const d = (S.data && S.data.delivery) || {};
    const fee = dom ? Number(d.fee || 0) : 0;
    return `<form class="cxp-wrap" data-cxp-form novalidate>
      <div class="cxp-top"><button type="button" class="cxp-ic" data-cxp-back aria-label="Volver a la carta">←</button><h1>${dom ? "Datos de la entrega" : "Datos para recoger"}</h1></div>
      <div class="cxp-card">
        <label>Nombre<input name="name" autocomplete="name" required maxlength="120" value="${h(f.name || "")}"></label>
        <label>Celular<input name="phone" type="tel" inputmode="tel" autocomplete="tel" required maxlength="24" value="${h(f.phone || "")}"></label>
        ${dom ? `<label>Dirección<input name="address" autocomplete="street-address" required maxlength="240" value="${h(f.address || "")}" placeholder="Calle 10 # 5-20, apto 301"></label>
        <label>Barrio<input name="barrio" maxlength="120" value="${h(f.barrio || "")}"></label>
        <label>Referencia (opcional)<input name="reference" maxlength="240" value="${h(f.reference || "")}" placeholder="Portería, casa esquinera, color…"></label>
        <fieldset class="cxp-card" style="padding:0;border:0;background:none"><legend style="font-weight:700;font-size:14px;margin-bottom:6px">Forma de pago (contra entrega)</legend>
          <div class="cxp-pay"><label><input type="radio" name="payment" value="efectivo" ${f.payment !== "transferencia" ? "checked" : ""}> Efectivo</label>
          <label><input type="radio" name="payment" value="transferencia" ${f.payment === "transferencia" ? "checked" : ""}> Transferencia</label></div></fieldset>`
        : `<label>Hora aproximada de recogida<select name="pickup" required>${slots().map((t) => `<option ${f.pickup === t ? "selected" : ""}>${h(t)}</option>`).join("")}</select></label>`}
        <label>Nota (opcional)<textarea name="note" maxlength="500">${h(f.note || "")}</textarea></label>
        <label class="cxp-hp" aria-hidden="true">No llenar<input name="website" tabindex="-1" autocomplete="off"></label>
        ${dom ? `<label class="cxp-check"><input type="checkbox" name="consent" required ${f.consent ? "checked" : ""}><span>Autorizo el tratamiento de mis datos para gestionar mi pedido. <a href="${h(S.data.policy_url)}" target="_blank" rel="noopener">Política de datos</a></span></label>` : ""}
      </div>
      <div class="cxp-card"><b>Tu pedido</b>${linesHtml()}
        ${dom && fee > 0 ? `<div class="cxp-line"><span>Domicilio</span><b>${h(money(fee))}</b></div>` : ""}
        <div class="cxp-total"><span>Total</span><span>${h(money(total() + fee))}</span></div>
        ${dom && fee <= 0 ? `<p class="cxp-muted">${h(d.fee_text || "El restaurante te confirma el valor del domicilio.")}</p>` : ""}
        ${dom ? `<p class="cxp-muted">Pagas al recibir. No pedimos datos de tarjeta.</p>` : `<p class="cxp-muted">Pagas al recoger en el restaurante.</p>`}
      </div>
      ${S.error ? `<p class="cxp-err" role="alert">${h(S.error)}</p>` : ""}
      <button class="cxp-btn" type="submit" ${S.busy ? "disabled" : ""}>${S.busy ? "Enviando…" : "Enviar pedido"}</button>
    </form>`;
  }

  function doneHtml() {
    const o = S.done;
    const dom = S.kind === "domicilio";
    return `<div class="cxp-wrap">
      <p class="cxp-ok" aria-hidden="true">✓</p>
      <h1 style="text-align:center;margin:0">¡Pedido recibido!</h1>
      <p class="cxp-num">${h(o.order_number || "")}</p>
      <div class="cxp-status" role="status" aria-live="polite">Estado: ${h(o.status_text || "Recibido")}</div>
      <div class="cxp-card"><b>Resumen</b>${linesHtml()}
        <div class="cxp-total"><span>Total</span><span>${h(money(o.total))}</span></div>
        ${o.fee_text ? `<p class="cxp-muted">${h(o.fee_text)}</p>` : ""}
        <p class="cxp-muted">${dom ? `Entrega en: ${h(S.form.address || "")}${S.form.barrio ? `, ${h(S.form.barrio)}` : ""}. Pago contra entrega (${h(S.form.payment === "transferencia" ? "transferencia" : "efectivo")}).` : `Recoges hacia las ${h(S.form.pickup || "")}. Pagas al recoger.`}</p>
      </div>
      <button class="cxp-btn ghost" type="button" data-cxp-again>Hacer otro pedido</button>
    </div>`;
  }

  function tablesHtml() {
    return `<div class="cxp-wrap">
      <div class="cxp-top"><button type="button" class="cxp-ic" data-cxp-back aria-label="Volver a la carta">←</button><h1>¿A qué mesa?</h1></div>
      <div class="cxp-card"><b>Pedido</b>${linesHtml()}<div class="cxp-total"><span>Total</span><span>${h(money(total()))}</span></div></div>
      ${S.tables.length ? `<div class="cxp-tables" role="group" aria-label="Tus mesas abiertas">${S.tables.map((t) => `<button type="button" data-cxp-table="${h(t.table_number)}" class="${S.table === t.table_number ? "on" : ""}" aria-pressed="${S.table === t.table_number}">${h(t.table_number)}<br><small>${h(money(t.total))}</small></button>`).join("")}</div>`
        : `<p class="cxp-err" role="alert">No tienes mesas abiertas. Abre la mesa en tu panel de mesero y vuelve aquí.</p>`}
      ${S.error ? `<p class="cxp-err" role="alert">${h(S.error)}</p>` : ""}
      <button class="cxp-btn" type="button" data-cxp-send-table ${S.busy || !S.table ? "disabled" : ""}>${S.busy ? "Enviando…" : "Agregar a la cuenta de la mesa"}</button>
    </div>`;
  }

  function paint() {
    const el = ensureOverlay();
    if (S.screen === "carta") { el.hidden = true; if (S.app) S.app.show(); return; }
    if (S.app) S.app.hide();
    el.hidden = false;
    el.innerHTML = S.screen === "form" ? formHtml() : S.screen === "done" ? doneHtml() : tablesHtml();
    el.scrollTop = 0;
  }

  function stop(message, link) {
    styles(null);
    document.getElementById("app").innerHTML = `<section class="cxp-center"><div class="cxp-card"><strong>${h(message)}</strong>${link ? `<a class="cxp-btn" href="${h(link.href)}">${h(link.label)}</a>` : ""}</div></section>`;
  }

  // ------------------------------------------------------------ eventos
  function readForm(form) {
    const data = new FormData(form);
    ["name", "phone", "address", "barrio", "reference", "note", "pickup", "website"].forEach((k) => { S.form[k] = String(data.get(k) || ""); });
    S.form.payment = String(data.get("payment") || "efectivo");
    S.form.consent = data.get("consent") === "on";
  }

  function onInput(event) {
    const form = event.target && event.target.closest && event.target.closest("[data-cxp-form]");
    if (form) readForm(form);
  }

  async function onSubmit(event) {
    const form = event.target;
    if (!form.matches("[data-cxp-form]")) return;
    event.preventDefault();
    readForm(form);
    const dom = S.kind === "domicilio";
    if (S.form.name.trim().length < 2) { S.error = "Escribe tu nombre."; paint(); return; }
    if ((S.form.phone.match(/\d/g) || []).length < 7) { S.error = "Escribe un celular válido."; paint(); return; }
    if (dom && S.form.address.trim().length < 5) { S.error = "Escribe la dirección de entrega."; paint(); return; }
    if (dom && !S.form.consent) { S.error = "Marca la casilla de autorización de datos para enviar el pedido."; paint(); return; }
    S.busy = true;
    S.error = "";
    paint();
    try {
      const out = await api(`/carta-links/public/${encodeURIComponent(token)}/orders`, { method: "POST", body: JSON.stringify({
        ...S.form, items: S.lines.map((l) => ({ inventory_item_id: l.id, quantity: l.quantity, observations: l.note || "", quick_notes: l.quick_notes || [], term: l.term || "" })),
      }) });
      S.done = out;
      S.screen = "done";
      if (S.app) S.app.clearCart();
      poll();
    } catch (error) {
      S.error = error.message;
    }
    S.busy = false;
    paint();
  }

  function poll() {
    clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
      if (!S.done || S.screen !== "done") { clearInterval(pollTimer); return; }
      try {
        const st = await api(`/carta-links/public/${encodeURIComponent(token)}/orders/${encodeURIComponent(S.done.order_id)}?s=${encodeURIComponent(S.done.key)}`);
        if (st.status_text !== S.done.status_text) { S.done.status_text = st.status_text; paint(); }
      } catch (_) {}
    }, 20000);
  }

  async function onClick(event) {
    const t = event.target;
    if (!t || !t.closest) return;
    if (t.closest("[data-cxp-back]")) { S.screen = "carta"; S.error = ""; paint(); return; }
    if (t.closest("[data-cxp-again]")) { S.done = null; S.lines = []; S.screen = "carta"; clearInterval(pollTimer); paint(); return; }
    const table = t.closest("[data-cxp-table]");
    if (table) { S.table = table.getAttribute("data-cxp-table"); S.error = ""; paint(); return; }
    if (t.closest("[data-cxp-send-table]") && S.table && !S.busy) {
      S.busy = true;
      S.error = "";
      paint();
      try {
        const response = await fetch(`${API}/companies/${encodeURIComponent(companyId)}/waiter-ordering/orders`, {
          method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${waiterToken()}` }, cache: "no-store",
          body: JSON.stringify({ table: S.table, items: S.lines.map((l) => ({ inventory_item_id: l.id, quantity: l.quantity, observations: l.note || "", quick_notes: l.quick_notes || [], term: l.term || "" })) }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || "No se pudo agregar a la mesa.");
        if (S.app) S.app.clearCart();
        const where = S.table;
        S.lines = [];
        S.table = "";
        S.screen = "carta";
        paint();
        await reloadTables();
        if (S.app) { S.app.state.msg = `Agregado a la cuenta de ${where}.`; S.app.openCart(); }
      } catch (error) {
        S.error = error.message;
        paint();
      }
      S.busy = false;
    }
  }

  // ------------------------------------------------------------ carga
  function mount(carta, where, submitLabel) {
    S.app = window.CxCartaApp.mount({ data: carta, adapter: {
      canOrder: true, where, submitLabel,
      submit: async (lines) => {
        S.lines = lines;
        S.error = "";
        S.screen = isMesero ? "tables" : "form";
        paint();
        return { keepCart: true };
      },
    } });
    styles(S.app.palette);
    ensureOverlay();
  }

  async function reloadTables() {
    try {
      const data = await api(`/carta-links/companies/${encodeURIComponent(companyId)}/mesero?k=${encodeURIComponent(token)}`, { headers: { Authorization: `Bearer ${waiterToken()}` } });
      S.tables = data.tables || [];
    } catch (_) {}
  }

  async function load() {
    if (!window.CxCartaApp) { stop("No se pudo cargar la carta. Recarga la página."); return; }
    if (isMesero) {
      const login = { href: `/mini-panel/mesero?company_id=${encodeURIComponent(companyId)}`, label: "Entrar al panel de mesero" };
      if (!companyId || !token) { stop("Este QR de mesero no es válido."); return; }
      if (!waiterToken()) { stop("Inicia sesión en tu panel de mesero para abrir la carta.", login); return; }
      try {
        const data = await api(`/carta-links/companies/${encodeURIComponent(companyId)}/mesero?k=${encodeURIComponent(token)}`, { headers: { Authorization: `Bearer ${waiterToken()}` } });
        S.data = data;
        S.tables = data.tables || [];
        mount(data.carta, `Mesero · ${data.mesero || ""}`.trim(), "Elegir la mesa");
        document.getElementById("app").innerHTML = "";
      } catch (error) {
        if (error.status === 401 || error.status === 403 && !/apagado/i.test(error.message)) stop("Inicia sesión en tu panel de mesero para abrir la carta.", login);
        else stop(error.message);
      }
      return;
    }
    if (!token) { stop("Este enlace no es válido. Pide el QR nuevo al restaurante."); return; }
    try {
      const data = await api(`/carta-links/public/${encodeURIComponent(token)}`);
      S.data = data;
      S.kind = data.kind;
      document.title = `${data.label} · ${(data.carta.company && data.carta.company.name) || "Carta"}`;
      mount(data.carta, data.label, "Continuar");
      document.getElementById("app").innerHTML = "";
    } catch (error) {
      stop(error.message);
    }
  }

  window.CxCartaPedir = { state: S, paint, formHtml, doneHtml, tablesHtml };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", load);
  else load();
})();
