// Carta de DOMICILIOS POR WHATSAPP (/domicilio?c=<empresa>&s=<codigo>).
// The link the customer line sent: personal, single use, 30 minutes. Same
// menu and product sheet as the mesero/caja panels (hsp_menu_kit.js):
// categories with photo or emoji, products with photo, quantity/portions,
// observations, cart. Only products with stock (the server's menu). At the
// end: name, address, location, payment (contra entrega, or QR + receipt
// sent to the WhatsApp chat) and subtotal + domicilio = total. Prices are
// recomputed by the server; what this page shows is only a preview.
(() => {
  "use strict";

  const Kit = window.CxMenuKit;
  const { h, money } = Kit;
  const root = document.getElementById("app");
  const params = new URLSearchParams(window.location.search);
  const companyId = params.get("c") || "";
  const code = params.get("s") || "";
  const API = `/api/v1/domicilios/public/${encodeURIComponent(companyId)}`;

  const state = {
    screen: "loading",
    error: "",
    notice: "",
    data: null,
    category: "",
    cart: [],
    form: { customer_name: "", address: "", address_notes: "", notes: "", payment_method: "cash", pays_with: "" },
    location: null,
    locating: false,
    busy: false,
    done: null,
  };

  async function request(path, options = {}) {
    const response = await fetch(path, { ...options, headers: { "Content-Type": "application/json", ...(options.headers || {}) } });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = typeof body.detail === "string" ? body.detail : "No se pudo completar. Intenta de nuevo.";
      const error = new Error(detail);
      error.status = response.status;
      throw error;
    }
    return body;
  }

  async function load() {
    if (!companyId || !code) {
      state.screen = "error";
      state.error = "Este enlace no es valido. Escribenos por WhatsApp para recibir uno nuevo.";
      render();
      return;
    }
    try {
      state.data = await request(`${API}?s=${encodeURIComponent(code)}`);
      state.screen = "categories";
    } catch (error) {
      state.screen = "error";
      state.error = error.message;
    }
    render();
  }

  // ------------------------------------------------------------- menu ---
  function menu() {
    return (state.data && state.data.categories) || [];
  }

  function kitOptions(attr) {
    return { companyId, emojis: Boolean(state.data && state.data.menu_emojis), attr, bar: false };
  }

  function currentCategory() {
    return menu().find((cat) => cat.key === state.category) || null;
  }

  function subtotal() {
    return Kit.cartTotal(state.cart);
  }

  function fee() {
    return Number((state.data && state.data.delivery_fee) || 0);
  }

  function total() {
    return subtotal() + fee();
  }

  function openItemSheet(product, category, portionLabel, prefill, editIndex) {
    Kit.openItemSheet({
      product,
      category,
      portionLabel,
      prefill,
      quantityButtons: (state.data && state.data.quantity_buttons) || [],
      addLabel: "Agregar al pedido",
      menuProductId: Kit.findMenuProduct(menu(), product.id) ? product.id : undefined,
      onAdd: (line) => {
        if (editIndex === null || editIndex === undefined) state.cart.push(line);
        else state.cart[editIndex] = line;
        state.notice = `${line.name} agregado.`;
        render();
      },
    });
  }

  function openProduct(productId) {
    const category = currentCategory();
    const product = (category ? category.products || [] : []).find((item) => item.id === productId);
    if (!product) return;
    if (Kit.productOpenMode(product, (state.data && state.data.quantity_buttons) || []) === "portions") {
      Kit.openPortionSheet(product, (portionProduct, label) => openItemSheet(portionProduct, category, label));
    } else {
      openItemSheet(product, category, null);
    }
  }

  function editLine(index) {
    const line = state.cart[index];
    if (!line) return;
    const found = line.menu_product_id ? Kit.findMenuProduct(menu(), line.menu_product_id) : null;
    if (found) openItemSheet(found.product, found.category, null, line, index);
    else openItemSheet({ id: line.inventory_item_id, name: line.name, price: line.unit_price }, null, line.portion_label || null, line, index);
  }

  // --------------------------------------------------------- checkout ---
  function paysWith() {
    const value = Number(String(state.form.pays_with || "").replace(/[^\d]/g, ""));
    return Number.isFinite(value) && value > 0 ? value : 0;
  }

  function checkoutProblem() {
    if (!state.cart.length) return "Agrega al menos un producto.";
    if (String(state.form.customer_name).trim().length < 2) return "Escribe tu nombre.";
    if (String(state.form.address).trim().length < 5) return "Escribe la direccion de entrega.";
    if (state.form.payment_method === "cash" && paysWith() && paysWith() < total()) return `El valor con el que pagas es menor al total (${money(total())}).`;
    return "";
  }

  function orderPayload() {
    return {
      s: code,
      customer_name: String(state.form.customer_name).trim(),
      address: String(state.form.address).trim(),
      address_notes: String(state.form.address_notes).trim(),
      notes: String(state.form.notes).trim(),
      latitude: state.location ? state.location.latitude : null,
      longitude: state.location ? state.location.longitude : null,
      payment_method: state.form.payment_method,
      pays_with: state.form.payment_method === "cash" && paysWith() ? paysWith() : null,
      items: state.cart.map(Kit.orderItemPayload),
    };
  }

  async function submit() {
    const problem = checkoutProblem();
    if (problem) {
      state.error = problem;
      render();
      return;
    }
    state.busy = true;
    state.error = "";
    render();
    try {
      state.done = await request(`${API}/orders`, { method: "POST", body: JSON.stringify(orderPayload()) });
      state.cart = [];
      state.screen = "done";
    } catch (error) {
      state.error = error.message;
      if (error.status === 410) state.screen = "error";
    } finally {
      state.busy = false;
      render();
    }
  }

  function useMyLocation() {
    if (!navigator.geolocation) {
      state.error = "Tu celular no permite compartir la ubicacion desde aqui. Compartela por WhatsApp.";
      render();
      return;
    }
    state.locating = true;
    render();
    navigator.geolocation.getCurrentPosition(
      (position) => {
        state.location = { latitude: position.coords.latitude, longitude: position.coords.longitude };
        state.locating = false;
        state.notice = "Ubicacion agregada.";
        render();
      },
      () => {
        state.locating = false;
        state.error = "No pudimos leer tu ubicacion. Compartela por WhatsApp o escribe bien la direccion.";
        render();
      },
      { enableHighAccuracy: true, timeout: 15000 },
    );
  }

  function whatsappLocationUrl() {
    const phone = String((state.data && state.data.whatsapp_number) || "").replace(/\D/g, "");
    if (!phone) return "";
    return `https://wa.me/${phone}?text=${encodeURIComponent("Te comparto mi ubicacion para el domicilio")}`;
  }

  // ---------------------------------------------------------- screens ---
  function header(back) {
    const count = state.cart.length;
    return `
      <header class="dom-header">
        ${back ? `<button class="dom-back" type="button" data-dom-back aria-label="Volver">‹</button>` : ""}
        <div class="dom-title">
          <small>Pedido a domicilio</small>
          <strong>${h((state.data && state.data.company_name) || "")}</strong>
        </div>
        <button class="dom-cart-btn" type="button" data-dom-checkout ${count ? "" : "disabled"}>🛒 ${count} · ${h(money(subtotal()))}</button>
      </header>
      ${state.notice ? `<div class="dom-notice">${h(state.notice)}</div>` : ""}`;
  }

  function screenCategories() {
    return `${header(false)}${Kit.categoryGridHtml(menu(), kitOptions("data-dom-cat"))}`;
  }

  function screenProducts() {
    const category = currentCategory();
    return `
      ${header(true)}
      <h2 class="dom-section">${h(category ? category.label : "")}</h2>
      ${Kit.productGridHtml(category ? category.products : [], kitOptions("data-dom-product"))}`;
  }

  function paymentBlock() {
    const method = state.form.payment_method;
    const qr = state.data && state.data.has_payment_qr;
    const option = (value, label) => `
      <label class="dom-pay ${method === value ? "is-active" : ""}">
        <input type="radio" name="payment" value="${value}" data-dom-payment ${method === value ? "checked" : ""}> ${label}
      </label>`;
    return `
      <div class="dom-block">
        <h3>Pago</h3>
        ${option("cash", "Efectivo contra entrega")}
        ${option("card", "Datafono contra entrega")}
        ${qr ? option("qr", "Pago por QR") : ""}
        ${method === "cash" ? `
          <label>Pagas con (para llevarte el cambio)
            <input inputmode="numeric" data-dom-field="pays_with" value="${h(state.form.pays_with)}" placeholder="Ej: 100000">
          </label>
          ${paysWith() >= total() ? `<div class="dom-hint">Cambio: <b>${h(money(paysWith() - total()))}</b></div>` : ""}` : ""}
        ${method === "qr" ? `
          <div class="dom-qr">
            <img src="${h(`${API}/payment-qr?s=${encodeURIComponent(code)}`)}" alt="QR de pago">
            <p>Paga <b>${h(money(total()))}</b> con este QR y <b>envia la foto del comprobante a nuestro chat de WhatsApp</b>. La caja confirma el pago antes de despachar tu pedido.</p>
          </div>` : ""}
      </div>`;
  }

  function screenCheckout() {
    const waUrl = whatsappLocationUrl();
    return `
      ${header(true)}
      <div class="dom-checkout">
        <div class="dom-block">
          <h3>Tu pedido</h3>
          ${state.cart.map((line, index) => `
            <div class="dom-line">
              <button type="button" class="dom-line-main" data-dom-edit="${index}">
                <span>${Kit.cartLineLabel(line)}</span>
                ${line.observations ? `<small>${h(line.observations)}</small>` : ""}
              </button>
              <strong>${h(money(Number(line.unit_price || 0) * Number(line.quantity || 0)))}</strong>
              <button type="button" class="dom-remove" data-dom-remove="${index}" aria-label="Quitar">✕</button>
            </div>`).join("") || `<div class="wtr-empty">Tu carrito esta vacio.</div>`}
          <button type="button" class="wtr-btn" data-dom-more>+ Agregar mas productos</button>
        </div>
        <div class="dom-block">
          <h3>Entrega</h3>
          <label>Nombre<input data-dom-field="customer_name" value="${h(state.form.customer_name)}" autocomplete="name"></label>
          <label>Direccion<input data-dom-field="address" value="${h(state.form.address)}" placeholder="Calle, numero, barrio" autocomplete="street-address"></label>
          <label>Indicaciones (opcional)<input data-dom-field="address_notes" value="${h(state.form.address_notes)}" placeholder="Apto, torre, casa azul..."></label>
          <div class="dom-location">
            <button type="button" class="wtr-btn" data-dom-locate ${state.locating ? "disabled" : ""}>${state.location ? "📍 Ubicacion agregada" : state.locating ? "Buscando..." : "📍 Usar mi ubicacion actual"}</button>
            ${waUrl ? `<a class="wtr-btn dom-wa" href="${h(waUrl)}" target="_blank" rel="noopener">Compartir ubicacion por WhatsApp</a>
              <small>En el chat toca 📎 › Ubicacion › Enviar tu ubicacion actual.</small>` : ""}
            ${state.data && state.data.whatsapp_location ? `<div class="dom-hint">✓ Ya recibimos tu ubicacion por WhatsApp.</div>` : ""}
          </div>
          <label>Nota para el pedido (opcional)<input data-dom-field="notes" value="${h(state.form.notes)}"></label>
        </div>
        ${paymentBlock()}
        <div class="dom-block dom-totals">
          <div><span>Subtotal</span><b>${h(money(subtotal()))}</b></div>
          <div><span>Domicilio</span><b>${h(money(fee()))}</b></div>
          <div class="dom-total"><span>Total</span><b>${h(money(total()))}</b></div>
        </div>
        ${state.error ? `<div class="dom-error">${h(state.error)}</div>` : ""}
        <button type="button" class="wtr-btn wtr-btn-primary" data-dom-submit ${state.busy || !state.cart.length ? "disabled" : ""}>${state.busy ? "Enviando..." : `Confirmar pedido · ${h(money(total()))}`}</button>
      </div>`;
  }

  function screenDone() {
    const done = state.done || {};
    return `
      <section class="dom-center">
        <div class="dom-done">
          <div class="dom-big">✅</div>
          <h2>Pedido recibido</h2>
          <p>Pedido <b>#${h(String(done.order_number || "").split("-").pop())}</b> por <b>${h(money(done.total))}</b>.</p>
          <p>Tiempo estimado de entrega: <b>${h(done.eta_minutes)} minutos</b>.</p>
          ${done.payment_status === "por_verificar"
            ? `<p class="dom-warn">Recuerda enviar la foto del comprobante a nuestro chat de WhatsApp. Confirmamos el pago antes de despachar.</p>`
            : ""}
          <p>Te avisaremos por WhatsApp cuando tu pedido salga.</p>
        </div>
      </section>`;
  }

  function screenError() {
    return `
      <section class="dom-center">
        <div class="dom-done">
          <div class="dom-big">⏱</div>
          <h2>Enlace no disponible</h2>
          <p>${h(state.error)}</p>
        </div>
      </section>`;
  }

  function render() {
    let html = "";
    if (state.screen === "loading") html = `<section class="dom-center"><p>Cargando la carta...</p></section>`;
    else if (state.screen === "categories") html = screenCategories();
    else if (state.screen === "products") html = screenProducts();
    else if (state.screen === "checkout") html = screenCheckout();
    else if (state.screen === "done") html = screenDone();
    else html = screenError();
    root.innerHTML = `<div class="dom-shell">${html}</div>`;
    state.notice = "";
  }

  // ---------------------------------------------------------- events ---
  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!target || !target.closest) return;
    const cat = target.closest("[data-dom-cat]");
    if (cat) {
      state.category = cat.getAttribute("data-dom-cat") || "";
      state.screen = "products";
      render();
      return;
    }
    const product = target.closest("[data-dom-product]");
    if (product) {
      openProduct(product.getAttribute("data-dom-product") || "");
      return;
    }
    if (target.closest("[data-dom-back]")) {
      state.error = "";
      state.screen = state.screen === "checkout" && state.category ? "products" : "categories";
      if (state.screen === "products" && !currentCategory()) state.screen = "categories";
      render();
      return;
    }
    if (target.closest("[data-dom-more]")) {
      state.screen = "categories";
      render();
      return;
    }
    const checkout = target.closest("[data-dom-checkout]");
    if (checkout && !checkout.disabled) {
      state.screen = "checkout";
      render();
      return;
    }
    const remove = target.closest("[data-dom-remove]");
    if (remove) {
      state.cart.splice(Number(remove.getAttribute("data-dom-remove")), 1);
      render();
      return;
    }
    const edit = target.closest("[data-dom-edit]");
    if (edit) {
      editLine(Number(edit.getAttribute("data-dom-edit")));
      return;
    }
    if (target.closest("[data-dom-locate]")) {
      useMyLocation();
      return;
    }
    const submitBtn = target.closest("[data-dom-submit]");
    if (submitBtn && !submitBtn.disabled) submit();
  });

  document.addEventListener("input", (event) => {
    const field = event.target && event.target.closest ? event.target.closest("[data-dom-field]") : null;
    if (!field) return;
    // Typing never re-renders (the keyboard would close); only the
    // cambio preview depends on it, refreshed on change.
    state.form[field.getAttribute("data-dom-field")] = String(field.value || "");
  });

  document.addEventListener("change", (event) => {
    const target = event.target;
    if (!target || !target.closest) return;
    if (target.closest("[data-dom-payment]")) {
      state.form.payment_method = String(target.value || "cash");
      render();
    } else if (target.closest("[data-dom-field]")) {
      render();
    }
  });

  const STYLES = `
    body{margin:0;background:#080712;color:#f5f3ff;font-family:system-ui,-apple-system,Segoe UI,sans-serif}
    .dom-shell{max-width:760px;margin:0 auto;min-height:100vh;padding-bottom:32px}
    .dom-header{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:10px;padding:14px 16px;background:rgba(8,7,18,.94);border-bottom:1px solid rgba(255,255,255,.08)}
    .dom-title{display:grid;flex:1;min-width:0}.dom-title small{color:#8f8aa8;font-weight:800}.dom-title strong{font-size:18px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .dom-back{width:44px;height:44px;border-radius:14px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#fff;font-size:26px}
    .dom-cart-btn{min-height:44px;padding:0 14px;border-radius:14px;border:none;background:linear-gradient(135deg,#ff7a18,#ff2d95);color:#fff;font-weight:900}
    .dom-cart-btn:disabled{opacity:.45}
    .dom-notice{margin:10px 16px 0;padding:10px 12px;border-radius:12px;background:rgba(34,197,94,.16);color:#bbf7d0;font-weight:800}
    .dom-section{margin:16px 16px 0}
    .dom-checkout{display:grid;gap:14px;padding:16px}
    .dom-block{display:grid;gap:10px;padding:14px;border-radius:18px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.1)}
    .dom-block h3{margin:0}
    .dom-block label{display:grid;gap:6px;font-size:13px;font-weight:800;color:#c9c3e6}
    .dom-block input{padding:12px;border-radius:12px;border:1px solid rgba(255,255,255,.16);background:rgba(3,7,18,.6);color:#fff;font:inherit;font-size:16px}
    .dom-line{display:flex;align-items:center;gap:10px}
    .dom-line-main{flex:1;display:grid;text-align:left;background:none;border:none;color:#fff;font:inherit;padding:0}
    .dom-line-main small{color:#8f8aa8}
    .dom-remove{width:36px;height:36px;border-radius:10px;border:1px solid rgba(255,255,255,.14);background:none;color:#fecaca}
    .dom-location{display:grid;gap:8px}.dom-location small{color:#8f8aa8}
    .dom-wa{display:grid;place-items:center;text-decoration:none;background:#16a34a;border:none}
    .dom-pay{display:flex!important;align-items:center;gap:10px;padding:12px;border-radius:14px;border:1px solid rgba(255,255,255,.14);color:#fff!important;font-size:15px!important}
    .dom-pay.is-active{border-color:#ff7a18;background:rgba(255,122,24,.12)}
    .dom-qr{display:grid;gap:10px;justify-items:center;text-align:center}
    .dom-qr img{width:240px;max-width:100%;background:#fff;border-radius:16px;padding:10px}
    .dom-hint{color:#bbf7d0;font-weight:800}
    .dom-totals div{display:flex;justify-content:space-between}
    .dom-total{font-size:20px;color:#ffd166}
    .dom-error{padding:12px;border-radius:12px;background:rgba(239,68,68,.16);color:#fecaca;font-weight:800}
    .dom-center{min-height:100vh;display:grid;place-items:center;padding:24px;text-align:center}
    .dom-done{max-width:420px;display:grid;gap:6px}.dom-big{font-size:56px}
    .dom-warn{color:#fde68a;font-weight:800}
  `;

  function injectStyles() {
    if (document.getElementById("cxDeliveryStyles")) return;
    const style = document.createElement("style");
    style.id = "cxDeliveryStyles";
    style.textContent = STYLES;
    document.head.appendChild(style);
  }

  // Exposed for tests only.
  window.CxDeliveryPage = { state, render, checkoutProblem, orderPayload, total, subtotal, whatsappLocationUrl };

  Kit.injectStyles();
  injectStyles();
  load();
})();
