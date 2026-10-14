// Recordatorio de pago de Clonexa en el panel principal (solo dueño o admin:
// el servidor responde 403 a los demás roles y a los tokens de mini panel).
// Sale UNA vez al cargar el panel (no al navegar entre módulos): "Recordar
// luego" lo cierra hasta la próxima vez que abran el panel. "Ya pagué" sube el
// comprobante (imagen o PDF, máx. 5 MB) y crea un pago POR VALIDAR; desde ahí
// el servidor deja de mostrarlo para esa cuota. Nunca bloquea ni suspende nada
// y ningún texto habla de suspensión. Textos por t() (es, en, fr).
(() => {
  "use strict";

  const API = "/api/v1/billing-reminder";
  const MAX_BYTES = 5 * 1024 * 1024;
  const LOGO = "/assets/brand/clonexa-icono.svg?v=cx26a";
  const LOCALES = { es: "es-CO", en: "en-US", fr: "fr-FR" };

  // Traducciones (la clave ES el texto en español, como el resto del portal).
  const TEXTS = {
    en: {
      "Hola, {company} 👋": "Hi, {company} 👋",
      "Tu mensualidad de {month} por {amount} está disponible para pago. Fecha límite: {due}.": "Your {month} subscription for {amount} is ready to be paid. Due date: {due}.",
      "Te queda un saldo de {balance} de tu mensualidad de {month}. Fecha límite: {due}.": "You have a remaining balance of {balance} on your {month} subscription. Due date: {due}.",
      "Tu pago de {month} está vencido desde el {since}. Cuando puedas, págalo con el QR; si ya lo hiciste, cuéntanos con «Ya pagué».": "Your {month} payment has been past due since {since}. Whenever you can, pay it with the QR code; if you already did, let us know with “I already paid”.",
      "Tu pago de {month} está vencido desde el {since}. Saldo pendiente: {balance}. Si ya lo pagaste, cuéntanos con «Ya pagué».": "Your {month} payment has been past due since {since}. Remaining balance: {balance}. If you already paid, let us know with “I already paid”.",
      "Escanea el QR para pagar": "Scan the QR code to pay",
      "Ya pagué": "I already paid",
      "Recordar luego": "Remind me later",
      "Sube la foto o el PDF del comprobante (máx. 5 MB).": "Upload a photo or PDF of the receipt (max. 5 MB).",
      "Comprobante": "Receipt",
      "Monto pagado (opcional)": "Amount paid (optional)",
      "Enviar comprobante": "Send receipt",
      "Volver": "Back",
      "Enviando…": "Sending…",
      "¡Gracias! Recibimos tu comprobante. Lo revisamos y te confirmamos.": "Thank you! We received your receipt. We will review it and confirm.",
      "Cerrar": "Close",
      "Adjunta el comprobante.": "Attach the receipt.",
      "El archivo pesa más de 5 MB.": "The file is larger than 5 MB.",
      "Solo se acepta una imagen o un PDF.": "Only an image or a PDF is accepted.",
      "No se pudo enviar. Intenta de nuevo.": "It could not be sent. Please try again.",
      "Recordatorio de pago": "Payment reminder",
    },
    fr: {
      "Hola, {company} 👋": "Bonjour, {company} 👋",
      "Tu mensualidad de {month} por {amount} está disponible para pago. Fecha límite: {due}.": "Votre mensualité pour {month} ({amount}) est disponible au paiement. Date limite : {due}.",
      "Te queda un saldo de {balance} de tu mensualidad de {month}. Fecha límite: {due}.": "Il vous reste un solde de {balance} pour la mensualité {month}. Date limite : {due}.",
      "Tu pago de {month} está vencido desde el {since}. Cuando puedas, págalo con el QR; si ya lo hiciste, cuéntanos con «Ya pagué».": "Votre paiement pour {month} est en retard depuis le {since}. Quand vous le pouvez, réglez-le avec le QR ; si c’est déjà fait, dites-le-nous avec « J’ai déjà payé ».",
      "Tu pago de {month} está vencido desde el {since}. Saldo pendiente: {balance}. Si ya lo pagaste, cuéntanos con «Ya pagué».": "Votre paiement pour {month} est en retard depuis le {since}. Solde restant : {balance}. Si c’est déjà fait, dites-le-nous avec « J’ai déjà payé ».",
      "Escanea el QR para pagar": "Scannez le QR pour payer",
      "Ya pagué": "J’ai déjà payé",
      "Recordar luego": "Me le rappeler plus tard",
      "Sube la foto o el PDF del comprobante (máx. 5 MB).": "Envoyez la photo ou le PDF du justificatif (5 Mo max.).",
      "Comprobante": "Justificatif",
      "Monto pagado (opcional)": "Montant payé (facultatif)",
      "Enviar comprobante": "Envoyer le justificatif",
      "Volver": "Retour",
      "Enviando…": "Envoi…",
      "¡Gracias! Recibimos tu comprobante. Lo revisamos y te confirmamos.": "Merci ! Nous avons reçu votre justificatif. Nous le vérifions et vous confirmons.",
      "Cerrar": "Fermer",
      "Adjunta el comprobante.": "Joignez le justificatif.",
      "El archivo pesa más de 5 MB.": "Le fichier dépasse 5 Mo.",
      "Solo se acepta una imagen o un PDF.": "Seule une image ou un PDF est accepté.",
      "No se pudo enviar. Intenta de nuevo.": "L’envoi a échoué. Réessayez.",
      "Recordatorio de pago": "Rappel de paiement",
    },
  };

  function register() {
    const dict = window.CX_I18N_DICT;
    if (!dict) return;
    for (const lang of ["en", "fr"]) {
      dict[lang] = dict[lang] || {};
      Object.entries(TEXTS[lang]).forEach(([es, tr]) => { if (!(es in dict[lang])) dict[lang][es] = tr; });
    }
  }

  function fill(text, vars) {
    return vars ? String(text).replace(/\{(\w+)\}/g, (m, k) => (vars[k] !== undefined ? String(vars[k]) : m)) : String(text);
  }

  function lang(state) {
    const l = (window.CxLocale && window.CxLocale.loaded && window.CxLocale.language) || (state && state.language) || "es";
    return l === "en" || l === "fr" ? l : "es";
  }

  // t() del portal (CxI18n, con estas frases ya registradas en su diccionario);
  // sin él (pruebas o portal a medio cargar), la misma tabla aquí.
  function t(es, vars, l) {
    if (window.CxI18n && typeof window.CxI18n.t === "function" && window.CxLocale && window.CxLocale.loaded) {
      return window.CxI18n.t(es, vars);
    }
    const table = TEXTS[l] || {};
    return fill(Object.prototype.hasOwnProperty.call(table, es) ? table[es] : es, vars);
  }

  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");

  function group(value, decimals, thousands, point) {
    const n = Number(value);
    const fixed = (Number.isFinite(n) ? Math.abs(n) : 0).toFixed(decimals);
    const [whole, frac] = fixed.split(".");
    return `${n < 0 ? "-" : ""}${whole.replace(/\B(?=(\d{3})+(?!\d))/g, thousands)}${decimals ? point + frac : ""}`;
  }

  // Moneda del contrato (COP o USD) con el formato de la empresa.
  function money(value, currency) {
    if (currency === "USD") return `US$${group(value, 2, ",", ".")}`;
    return `$${group(value, 0, ".", ",")} COP`;
  }

  // Fechas de calendario (AAAA-MM-DD) en el idioma de la empresa; sin corrimiento de zona.
  function day(iso, l) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
    if (!m) return "";
    const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), 12));
    try { return new Intl.DateTimeFormat(LOCALES[l] || "es-CO", { day: "numeric", month: "long", timeZone: "UTC" }).format(d); } catch (_) { return iso; }
  }

  function monthName(iso, l) {
    const m = /^(\d{4})-(\d{2})/.exec(String(iso || ""));
    if (!m) return "";
    const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, 15, 12));
    try { return new Intl.DateTimeFormat(LOCALES[l] || "es-CO", { month: "long", year: "numeric", timeZone: "UTC" }).format(d); } catch (_) { return iso; }
  }

  function nextDay(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
    if (!m) return iso;
    const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]) + 1, 12));
    return d.toISOString().slice(0, 10);
  }

  // El mensaje según el estado (en ventana / vencido; total / saldo). Nunca menciona suspensión.
  function message(state, l, tr = t) {
    const vars = { company: state.company_name || "", month: monthName(state.period, l), amount: money(state.amount, state.currency),
      balance: money(state.balance, state.currency), due: day(state.due_date, l), since: day(nextDay(state.due_date), l) };
    const hello = tr("Hola, {company} 👋", vars, l);
    let body;
    if (state.state === "overdue") {
      body = state.partial
        ? tr("Tu pago de {month} está vencido desde el {since}. Saldo pendiente: {balance}. Si ya lo pagaste, cuéntanos con «Ya pagué».", vars, l)
        : tr("Tu pago de {month} está vencido desde el {since}. Cuando puedas, págalo con el QR; si ya lo hiciste, cuéntanos con «Ya pagué».", vars, l);
    } else {
      body = state.partial
        ? tr("Te queda un saldo de {balance} de tu mensualidad de {month}. Fecha límite: {due}.", vars, l)
        : tr("Tu mensualidad de {month} por {amount} está disponible para pago. Fecha límite: {due}.", vars, l);
    }
    return { hello, body };
  }

  function css(theme) {
    const th = theme || {};
    return `.cxbr-veil{position:fixed;inset:0;z-index:2147483000;display:grid;place-items:center;padding:16px;background:rgba(5,5,9,.62);backdrop-filter:blur(4px)}
.cxbr-card{width:min(440px,100%);max-height:calc(100vh - 32px);overflow:auto;border-radius:22px;padding:22px 22px 18px;background:${th.background || "#050509"};color:${th.text || "#f8fafc"};border:1px solid ${th.primary || "#ff2bd6"}55;box-shadow:0 24px 70px rgba(0,0,0,.45),0 0 40px ${th.primary || "#ff2bd6"}30;font:15px/1.45 inherit}
.cxbr-head{display:flex;align-items:center;gap:12px;margin-bottom:10px}.cxbr-head img{width:40px;height:40px;flex:0 0 auto}
.cxbr-head b{font-size:18px}.cxbr-body{margin:0 0 14px;opacity:.92}
.cxbr-qr{display:grid;justify-items:center;gap:6px;margin:6px 0 14px}.cxbr-qr img{width:min(220px,70vw);height:auto;border-radius:12px;background:#fff;padding:8px}
.cxbr-qr small{opacity:.75}.cxbr-actions{display:flex;flex-wrap:wrap;gap:10px;justify-content:flex-end}
.cxbr-btn{min-height:42px;border-radius:12px;padding:10px 16px;font-weight:800;cursor:pointer;border:1px solid ${th.primary || "#ff2bd6"}66;background:transparent;color:inherit}
.cxbr-btn.is-main{border:0;color:#fff;background:linear-gradient(135deg,${th.primary || "#ff2bd6"},${th.secondary || "#00ff88"})}
.cxbr-btn[disabled]{opacity:.6;cursor:wait}.cxbr-field{display:grid;gap:6px;margin:0 0 12px}.cxbr-field input{min-height:40px;border-radius:10px;padding:8px 10px;border:1px solid ${th.primary || "#ff2bd6"}55;background:rgba(255,255,255,.06);color:inherit}
.cxbr-error{color:#ff8a8a;margin:0 0 10px}.cxbr-hint{opacity:.8;margin:0 0 12px}`;
  }

  function cardHtml(state, view, l, qrUrl, error, busy) {
    const msg = message(state, l);
    const head = `<div class="cxbr-head"><img src="${LOGO}" alt="CLONEXA"><b>${h(msg.hello)}</b></div>`;
    if (view === "done") {
      return `${head}<p class="cxbr-body">${h(t("¡Gracias! Recibimos tu comprobante. Lo revisamos y te confirmamos.", null, l))}</p>
        <div class="cxbr-actions"><button class="cxbr-btn is-main" type="button" data-cxbr-close>${h(t("Cerrar", null, l))}</button></div>`;
    }
    if (view === "upload") {
      return `${head}<form data-cxbr-form><p class="cxbr-hint">${h(t("Sube la foto o el PDF del comprobante (máx. 5 MB).", null, l))}</p>
        <label class="cxbr-field">${h(t("Comprobante", null, l))}<input name="file" type="file" accept="image/png,image/jpeg,image/webp,application/pdf" required></label>
        <label class="cxbr-field">${h(t("Monto pagado (opcional)", null, l))}<input name="amount" type="number" min="0" step="0.01" inputmode="decimal" placeholder="${h(money(state.balance, state.currency))}"></label>
        ${error ? `<p class="cxbr-error" role="alert">${h(error)}</p>` : ""}
        <div class="cxbr-actions"><button class="cxbr-btn" type="button" data-cxbr-back>${h(t("Volver", null, l))}</button>
        <button class="cxbr-btn is-main" type="submit" ${busy ? "disabled" : ""}>${h(busy ? t("Enviando…", null, l) : t("Enviar comprobante", null, l))}</button></div></form>`;
    }
    return `${head}<p class="cxbr-body">${h(msg.body)}</p>
      ${qrUrl ? `<div class="cxbr-qr"><img src="${h(qrUrl)}" alt="QR"><small>${h(t("Escanea el QR para pagar", null, l))}</small></div>` : ""}
      <div class="cxbr-actions"><button class="cxbr-btn" type="button" data-cxbr-close>${h(t("Recordar luego", null, l))}</button>
      <button class="cxbr-btn is-main" type="button" data-cxbr-paid>${h(t("Ya pagué", null, l))}</button></div>`;
  }

  // ------------------------------------------------------------ navegador
  function authToken() {
    const keys = ["clonexa_access_token", "clonexa_token", "clonexa_client_token", "access_token", "token", "auth_token", "jwt"];
    for (const store of [window.localStorage, window.sessionStorage].filter(Boolean)) {
      for (const key of keys) {
        let value = "";
        try { value = store.getItem(key) || ""; } catch (_) { value = ""; }
        if (!value) continue;
        if (value.trim().startsWith("{")) {
          try { const d = JSON.parse(value); const nested = d.access_token || d.token || d.jwt; if (nested) return nested; } catch (_) {}
        } else return value;
      }
    }
    return "";
  }

  function isPdfOrImage(file) {
    return /^(image\/(png|jpeg|webp)|application\/pdf)$/.test(String(file && file.type || "")) || /\.(png|jpe?g|webp|pdf)$/i.test(String(file && file.name || ""));
  }

  async function open(state, token) {
    const l = lang(state);
    let qrUrl = "";
    if (state.has_qr) {
      try {
        const r = await fetch(`${API}/qr`, { headers: { Authorization: `Bearer ${token}` }, credentials: "same-origin" });
        if (r.ok) qrUrl = URL.createObjectURL(await r.blob());
      } catch (_) {}
    }
    const style = document.createElement("style");
    style.textContent = css(state.theme);
    document.head.appendChild(style);
    const veil = document.createElement("div");
    veil.className = "cxbr-veil";
    veil.setAttribute("data-no-i18n", "");
    veil.innerHTML = `<section class="cxbr-card" role="dialog" aria-modal="true" aria-label="${h(t("Recordatorio de pago", null, l))}"></section>`;
    document.body.appendChild(veil);
    const card = veil.querySelector(".cxbr-card");
    const ui = { view: "main", error: "", busy: false };
    const draw = () => { card.innerHTML = cardHtml(state, ui.view, l, qrUrl, ui.error, ui.busy); };
    const close = () => { veil.remove(); style.remove(); if (qrUrl) URL.revokeObjectURL(qrUrl); };
    veil.addEventListener("click", (e) => {
      const el = e.target;
      if (el.closest("[data-cxbr-close]")) { close(); return; }
      if (el.closest("[data-cxbr-paid]")) { ui.view = "upload"; ui.error = ""; draw(); return; }
      if (el.closest("[data-cxbr-back]")) { ui.view = "main"; ui.error = ""; draw(); }
    });
    veil.addEventListener("submit", async (e) => {
      e.preventDefault();
      const form = e.target;
      const file = form.querySelector("input[type=file]").files[0];
      const amount = String(form.querySelector("input[name=amount]").value || "").trim();
      if (!file) { ui.error = t("Adjunta el comprobante.", null, l); draw(); return; }
      if (file.size > MAX_BYTES) { ui.error = t("El archivo pesa más de 5 MB.", null, l); draw(); return; }
      if (!isPdfOrImage(file)) { ui.error = t("Solo se acepta una imagen o un PDF.", null, l); draw(); return; }
      ui.busy = true; ui.error = ""; draw();
      try {
        const r = await fetch(`${API}/paid${amount ? `?amount=${encodeURIComponent(amount)}` : ""}`, {
          method: "POST", body: file, credentials: "same-origin",
          headers: { Authorization: `Bearer ${token}`, "Content-Type": file.type || "application/octet-stream" } });
        if (!r.ok) throw new Error(String(r.status));
        ui.view = "done";
      } catch (_) {
        ui.error = t("No se pudo enviar. Intenta de nuevo.", null, l);
      } finally {
        ui.busy = false;
        draw();
      }
    });
    draw();
  }

  async function check() {
    const token = authToken();
    if (!token) return;
    let state = null;
    try {
      const r = await fetch(API, { headers: { Authorization: `Bearer ${token}`, Accept: "application/json" }, credentials: "same-origin" });
      if (!r.ok) return; // 401/403 (otros roles, mini paneles): nada
      state = await r.json();
    } catch (_) { return; }
    if (state && state.show) open(state, token);
  }

  // Una sola vez por carga del panel: espera a que el panel termine de entrar.
  function start() {
    register();
    let tries = 0;
    const timer = setInterval(() => {
      tries += 1;
      const loading = document.querySelector(".loading-panel");
      if ((!loading && authToken()) || tries > 40) {
        clearInterval(timer);
        if (authToken()) check();
      }
    }, 500);
  }

  window.CxBillingReminder = { TEXTS, message, money, day, monthName, nextDay, cardHtml, t, fill, register };
  if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
    else start();
  }
})();
