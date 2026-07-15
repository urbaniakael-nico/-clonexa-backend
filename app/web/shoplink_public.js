(() => {
  "use strict";

  const API = "/api/v1";
  const state = {
    data: null,
    category: "Todos",
    query: "",
    cart: [],
    customer: {},
    placing: false,
    order: null,
    checkoutError: "",
    couponDraft: "",
    coupon: { status: "idle", code: "", discountAmount: 0, message: "" },
    paymentMethod: "",
    cartOpen: false,
    appliedCampaign: null,
  };

  const h = (value) =>
    String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");

  const app = () => document.getElementById("shoplinkApp");
  const settings = () => state.data?.settings || {};
  const products = () => state.data?.products || [];
  const campaign = () => state.appliedCampaign || state.data?.campaign || null;

  function money(value, currency = "COP") {
    const number = Number(value || 0);
    if (!number) return "Por confirmar";
    try {
      return new Intl.NumberFormat("es-CO", {
        style: "currency",
        currency: currency || "COP",
        maximumFractionDigits: 0,
      }).format(number);
    } catch (error) {
      return `$ ${Math.round(number).toLocaleString("es-CO")}`;
    }
  }

  function companyIdFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return params.get("company_id") || params.get("companyId") || params.get("tenant") || "";
  }

  function campaignSlugFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return params.get("campaign") || params.get("campana") || "";
  }

  async function api(path, options = {}) {
    const res = await fetch(`${API}${path}`, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!res.ok) {
      const raw = await res.text().catch(() => "");
      let detail = raw;
      try { detail = JSON.parse(raw)?.detail || raw; } catch (error) { /* respuesta no JSON */ }
      throw new Error(detail || `${res.status} ${res.statusText}`);
    }
    return res.json();
  }

  function applyStoreTheme() {
    const s = settings();
    const accent = /^#[0-9a-fA-F]{6}$/.test(String(s.accent_color || "")) ? s.accent_color : "#ff7a00";
    document.documentElement.style.setProperty("--sl-accent", accent);
    document.body.dataset.theme = s.theme || "marketplace_pop";
    document.body.dataset.layout = s.layout_mode || "marketplace";
  }

  function visibleProducts() {
    const q = state.query.trim().toLowerCase();
    return products().filter((product) => {
      const categoryOk = state.category === "Todos" || String(product.category || "General") === state.category;
      const text = `${product.name || ""} ${product.category || ""} ${product.size || ""} ${product.color || ""} ${product.sku || ""}`.toLowerCase();
      return categoryOk && (!q || text.includes(q));
    });
  }

  function featuredProducts() {
    const featured = state.data?.featured || [];
    return (featured.length ? featured : products()).slice(0, 8);
  }

  function addToCart(productId) {
    const product = products().find((item) => String(item.id) === String(productId));
    if (!product || Number(product.stock || 0) <= 0) return;
    const existing = state.cart.find((item) => item.id === product.id);
    if (existing) existing.qty += 1;
    else state.cart.push({ ...product, qty: 1 });
    resetCouponAfterCartChange();
    state.order = null;
    state.checkoutError = "";
    render();
  }

  function setQty(productId, delta) {
    const item = state.cart.find((row) => String(row.id) === String(productId));
    if (!item) return;
    item.qty = Math.max(1, Number(item.qty || 1) + delta);
    resetCouponAfterCartChange();
    render();
  }

  function removeFromCart(productId) {
    state.cart = state.cart.filter((item) => String(item.id) !== String(productId));
    resetCouponAfterCartChange();
    render();
  }

  function resetCouponAfterCartChange() {
    if (state.coupon.status !== "idle" || state.coupon.code) {
      state.coupon = { status: "idle", code: "", discountAmount: 0, message: "Vuelve a aplicar el cupon para actualizar el descuento." };
      state.appliedCampaign = null;
    }
  }

  function cartTotal() {
    return state.cart.reduce((total, item) => total + Number(item.price || 0) * Number(item.qty || 1), 0);
  }

  function campaignDiscount() {
    const c = campaign();
    if (!c || !state.cart.length) return 0;
    if (c.coupon_required) {
      return state.coupon.status === "valid" ? Number(state.coupon.discountAmount || 0) : 0;
    }
    const type = String(c.discount_type || "none");
    const value = Number(c.discount_value || 0);
    if (!value || type === "none") return 0;
    const subtotal = cartTotal();
    if (subtotal < Number(c.min_order || 0)) return 0;
    const selected = new Set((c.product_ids || []).map(String));
    const base = selected.size
      ? state.cart.reduce((sum, item) => (
          selected.has(String(item.id)) || selected.has(String(item.raw_id)) || selected.has(String(item.id).replace("shoplink:", ""))
            ? sum + Number(item.price || 0) * Number(item.qty || 1)
            : sum
        ), 0)
      : subtotal;
    if (!base) return 0;
    return type === "percent" ? Math.min(base, Math.round(base * Math.min(value, 90) / 100)) : Math.min(base, value);
  }

  function cartPayableTotal() {
    return Math.max(0, cartTotal() - campaignDiscount());
  }

  function cartItemsCount() {
    return state.cart.reduce((total, item) => total + Number(item.qty || 1), 0);
  }

  function paymentMethods() {
    const values = settings().payment_methods || ["Efectivo", "Transferencia", "Tarjeta"];
    return values.filter((value) => String(value || "").trim());
  }

  function paymentIcon(method = "") {
    const value = String(method).toLowerCase();
    if (value.includes("efect")) return "$";
    if (value.includes("transfer")) return "↗";
    if (value.includes("tarjet")) return "▣";
    return "•";
  }

  function normalizeWhatsappPhone(value = "") {
    let phone = String(value || "").replace(/\D/g, "");
    if (phone.startsWith("00")) phone = phone.slice(2);
    if (phone.length === 10 && phone.startsWith("3")) phone = `57${phone}`;
    return phone;
  }

  function supportUrl() {
    const s = settings();
    const phone = normalizeWhatsappPhone(s.whatsapp_number || "");
    const store = s.store_name || state.data?.company?.name || "Tienda";
    const text = encodeURIComponent(`${s.cta_message || "Hola, necesito ayuda con mi pedido:"}\nTienda: ${store}`);
    return phone ? `https://wa.me/${phone}?text=${text}` : `https://wa.me/?text=${text}`;
  }

  function orderOwnerAlertUrl(order = {}) {
    if (order.owner_alert_url) return order.owner_alert_url;
    const s = settings();
    const phone = normalizeWhatsappPhone(order.owner_alert_phone || s.payment_proof_whatsapp || s.whatsapp_number || "");
    if (!phone) return "";
    const message = order.owner_alert_message || [
      "Nuevo pedido ShopLink",
      `Pedido: ${order.order_code || ""}`,
      `Cliente: ${state.customer.customer_name || order.customer_name || "Cliente"}`,
      `Telefono: ${state.customer.customer_phone || order.customer_phone || ""}`,
      `Total: ${money(order.total_amount, order.currency || s.currency)}`,
    ].filter(Boolean).join("\n");
    return `https://wa.me/${phone}?text=${encodeURIComponent(message)}`;
  }

  function openOwnerAlert(order = {}) {
    const url = orderOwnerAlertUrl(order);
    if (!url) return false;
    window.open(url, "_blank", "noopener");
    return true;
  }

  function productImages(product) {
    const urls = Array.isArray(product.image_urls) && product.image_urls.length
      ? product.image_urls
      : [product.image_url].filter(Boolean);
    return urls.filter(Boolean).slice(0, 3);
  }

  function productVisual(product) {
    const images = productImages(product);
    if (images.length) {
      return `
        <div class="sl-gallery ${images.length > 1 ? "multi" : "single"}">
          ${images.map((url, index) => `
            <button class="sl-image-thumb" type="button" data-shoplink-zoom="${h(url)}" data-shoplink-zoom-title="${h(product.name || "Producto")}">
              <img src="${h(url)}" alt="${h(product.name || "Producto")} ${index + 1}" loading="lazy">
            </button>
          `).join("")}
        </div>
      `;
    }
    const initials = String(product.name || "P").trim().slice(0, 2).toUpperCase();
    return `<div class="sl-product-fallback"><b>${h(initials)}</b><span>${h(product.category || "Nuevo")}</span></div>`;
  }

  function openImageZoom(url = "", title = "") {
    if (!url) return;
    document.querySelector("[data-shoplink-zoom-modal]")?.remove();
    document.body.insertAdjacentHTML("beforeend", `
      <div class="sl-zoom" data-shoplink-zoom-modal>
        <button class="sl-zoom-close" type="button" data-shoplink-zoom-close>Cerrar</button>
        <figure>
          <img src="${h(url)}" alt="${h(title || "Imagen de producto")}">
          ${title ? `<figcaption>${h(title)}</figcaption>` : ""}
        </figure>
      </div>
    `);
  }

  function closeImageZoom() {
    document.querySelector("[data-shoplink-zoom-modal]")?.remove();
  }

  function productCard(product, compact = false) {
    const s = settings();
    const hasStock = Number(product.stock || 0) > 0;
    return `
      <article class="sl-card ${compact ? "compact" : ""}">
        <div class="sl-media">${productVisual(product)}</div>
        <div class="sl-card-body">
          <small>${h(product.category || "General")}${product.size ? ` / ${h(product.size)}` : ""}${product.color ? ` / ${h(product.color)}` : ""}</small>
          <h3>${h(product.name || "Producto")}</h3>
          <div class="sl-card-row">
            <div>
              <div class="sl-price">${s.show_prices === false ? "Consultar" : h(money(product.price, s.currency))}</div>
              <span>${s.show_stock === false ? h(product.status || "Disponible") : `${h(product.stock ?? 0)} disponibles`}</span>
            </div>
            <button class="sl-icon-btn" type="button" data-shoplink-add="${h(product.id)}" ${hasStock ? "" : "disabled"}>${hasStock ? "+" : "0"}</button>
          </div>
        </div>
      </article>
    `;
  }

  function renderTopbar() {
    const data = state.data || {};
    const s = settings();
    const logo = s.logo_url || "";
    const support = s.support_whatsapp_enabled && s.whatsapp_number;
    return `
      <header class="sl-topbar">
        <div class="sl-brand">
          <div class="sl-logo">${logo ? `<img src="${h(logo)}" alt="">` : h((s.store_name || data.company?.name || "S").slice(0, 1).toUpperCase())}</div>
          <div>
            <strong>${h(s.store_name || data.company?.name || "Tienda")}</strong>
            <small>ShopLink by CLONEXA</small>
          </div>
        </div>
        <label class="sl-global-search">
          <span>Buscar</span>
          <input data-shoplink-search placeholder="Productos, categorias, colores..." value="${h(state.query)}">
        </label>
        ${support ? `<button class="sl-support" type="button" data-shoplink-support>Soporte</button>` : ""}
      </header>
    `;
  }

  function renderHero() {
    const data = state.data || {};
    const s = settings();
    const c = campaign();
    const heroImage = c?.banner_url || s.hero_image_url || "";
    const heroStyle = heroImage ? ` style="background-image:linear-gradient(90deg,rgba(10,12,18,.72),rgba(10,12,18,.18)),url('${h(heroImage)}')"` : "";
    return `
      <section class="sl-hero"${heroStyle}>
        <div>
          ${(c?.discount_label || s.announcement) ? `<div class="sl-announcement">${h(c?.discount_label || s.announcement)}</div>` : ""}
          <div class="sl-eyebrow">${c ? "Campana especial" : "Tienda online"}</div>
          <h1>${h(c?.headline || c?.title || s.headline || s.store_name || data.company?.name || "Compra en linea")}</h1>
          <p>${h(c?.description || s.description || "Explora productos, arma tu carrito y haz tu pedido en la web.")}</p>
          <div class="sl-meta">
            <span>${h(products().length)} productos</span>
            <span>${h((data.categories || []).length)} categorias</span>
            <span>${s.checkout_enabled === false ? "Solo vitrina" : "Checkout web"}</span>
            ${c?.coupon_required ? `<span>Cupon disponible</span>` : ""}
          </div>
        </div>
      </section>
    `;
  }

  function renderFeatured() {
    const rows = featuredProducts();
    if (!rows.length) return "";
    return `
      <section class="sl-strip">
        <div class="sl-section-head">
          <div>
            <div class="sl-eyebrow">Destacados</div>
            <h2>${campaign() ? "Seleccion de la promo" : "Vitrina principal"}</h2>
          </div>
        </div>
        <div class="sl-featured-row">
          ${rows.map((product) => productCard(product, true)).join("")}
        </div>
      </section>
    `;
  }

  function renderProducts() {
    const data = state.data || {};
    const categories = ["Todos", ...(data.categories || [])];
    const rows = visibleProducts();
    return `
      <section class="sl-panel">
        <div class="sl-section-head">
          <div>
            <div class="sl-eyebrow">Catalogo</div>
            <h2>Explora la tienda</h2>
            <p data-shoplink-visible-count>${h(rows.length)} de ${h(products().length)} productos visibles</p>
          </div>
        </div>
        <div class="sl-tabs">
          ${categories.map((category) => `
            <button class="sl-tab ${category === state.category ? "active" : ""}" type="button" data-shoplink-category="${h(category)}">
              ${h(category)}
            </button>
          `).join("")}
        </div>
        <div class="sl-products" data-shoplink-products-grid>
          ${renderProductGrid()}
        </div>
      </section>
    `;
  }

  function renderProductGrid() {
    const rows = visibleProducts();
    return rows.length
      ? rows.map((product) => productCard(product)).join("")
      : `<div class="sl-empty">No hay productos visibles para este filtro.</div>`;
  }

  function refreshProductResults() {
    const rows = visibleProducts();
    const count = document.querySelector("[data-shoplink-visible-count]");
    if (count) count.textContent = `${rows.length} de ${products().length} productos visibles`;
    const grid = document.querySelector("[data-shoplink-products-grid]");
    if (grid) grid.innerHTML = renderProductGrid();
  }

  function renderOrderSuccess() {
    const s = settings();
    const invoiceUrl = state.order.invoice_url
      ? (/^https?:\/\//i.test(state.order.invoice_url) ? state.order.invoice_url : `${window.location.origin}${state.order.invoice_url}`)
      : "";
    const ownerAlertUrl = orderOwnerAlertUrl(state.order);
    const alertSent = !!state.order.owner_alert_delivery?.ok;
    return `
      <div class="sl-success">
        <strong>Pedido recibido</strong>
        <p>Codigo ${h(state.order.order_code)}. Factura ${h(state.order.invoice_code || "generada")}.</p>
        <small>Total: ${h(money(state.order.total_amount, s.currency))}</small>
        ${alertSent ? `<small>La tienda ya recibio la alerta por WhatsApp.</small>` : ""}
        ${ownerAlertUrl && !alertSent ? `<button class="sl-btn" type="button" data-shoplink-owner-alert>Enviar alerta a la tienda por WhatsApp</button>` : ""}
        ${invoiceUrl ? `<button class="sl-btn secondary" type="button" data-shoplink-open-invoice="${h(invoiceUrl)}">Abrir factura</button>` : ""}
        ${ownerAlertUrl && !alertSent ? `<small>La tienda aun no tiene WhatsApp Web vinculado; toca el boton para abrir el aviso manual.</small>` : ""}
      </div>
    `;
  }

  function renderCouponBox() {
    const status = state.coupon.status;
    const message = state.coupon.message;
    return `
      <section class="sl-checkout-section sl-coupon-box ${h(status)}">
        <div class="sl-section-title">
          <span class="sl-section-icon">%</span>
          <div><strong>Cupon de descuento</strong><small>Escribe el codigo creado en la campaña</small></div>
        </div>
        <div class="sl-coupon-row">
          <input data-shoplink-coupon value="${h(state.couponDraft)}" placeholder="EJ: MARATON" autocomplete="off" ${status === "checking" ? "disabled" : ""}>
          <button type="button" data-shoplink-apply-coupon ${state.cart.length && state.couponDraft.trim() && status !== "checking" ? "" : "disabled"}>
            ${status === "checking" ? "Validando..." : "Aplicar"}
          </button>
        </div>
        ${message ? `<div class="sl-coupon-status"><span>${status === "valid" ? "✓" : status === "invalid" ? "!" : "i"}</span>${h(message)}${status === "valid" ? `<button type="button" data-shoplink-remove-coupon>Quitar</button>` : ""}</div>` : ""}
      </section>
    `;
  }

  function renderCheckoutForm() {
    const s = settings();
    const c = campaign();
    if (s.checkout_enabled === false) {
      return `<div class="sl-empty">La tienda esta en modo vitrina. Los pedidos web estan desactivados.</div>`;
    }
    const methods = paymentMethods();
    return `
      <div class="sl-checkout-flow">
        <div class="sl-checkout-steps" aria-label="Progreso de compra">
          <span class="done"><b>1</b>Carrito</span><i></i><span class="active"><b>2</b>Datos</span><i></i><span><b>3</b>Confirmar</span>
        </div>
        ${c ? `<div class="sl-promo-chip"><span>OFERTA</span><div><strong>${h(c.title || "Campaña activa")}</strong><small>${h(c.discount_label || "Beneficio disponible")}</small></div></div>` : ""}
        ${renderCouponBox()}
        <section class="sl-checkout-section">
          <div class="sl-section-title">
            <span class="sl-section-icon">⌂</span>
            <div><strong>Datos de entrega</strong><small>Te contactaremos para coordinar el envio</small></div>
          </div>
          <div class="sl-checkout">
            <label>Nombre completo
              <input data-shoplink-customer="customer_name" value="${h(state.customer.customer_name || "")}" placeholder="Tu nombre">
            </label>
            <label>Telefono / WhatsApp
              <input data-shoplink-customer="customer_phone" value="${h(state.customer.customer_phone || "")}" placeholder="+57 300 000 0000" inputmode="tel">
            </label>
            <label>Ciudad
              <input data-shoplink-customer="customer_city" value="${h(state.customer.customer_city || "")}" placeholder="Ciudad">
            </label>
            <label>Direccion
              <input data-shoplink-customer="customer_address" value="${h(state.customer.customer_address || "")}" placeholder="Direccion de entrega">
            </label>
            <label class="wide">Nota para el pedido
              <textarea data-shoplink-customer="customer_note" placeholder="Talla, color, referencia o comentario">${h(state.customer.customer_note || "")}</textarea>
            </label>
          </div>
        </section>
        <section class="sl-checkout-section">
          <div class="sl-section-title">
            <span class="sl-section-icon">◇</span>
            <div><strong>Como quieres pagar</strong><small>Selecciona una opcion para continuar</small></div>
          </div>
          <div class="sl-payment-methods">
            ${methods.map((method) => `
              <button class="${state.paymentMethod === method ? "selected" : ""}" type="button" data-shoplink-payment="${h(method)}" aria-pressed="${state.paymentMethod === method}">
                <span>${h(paymentIcon(method))}</span><strong>${h(method)}</strong><i>${state.paymentMethod === method ? "✓" : ""}</i>
              </button>
            `).join("")}
          </div>
          ${s.delivery_notes ? `<p class="sl-delivery-note">${h(s.delivery_notes)}</p>` : ""}
        </section>
        ${state.checkoutError ? `<div class="sl-error">${h(state.checkoutError)}</div>` : ""}
        <button class="sl-btn sl-checkout-cta" type="button" data-shoplink-place-order ${state.cart.length && !state.placing ? "" : "disabled"}>
          <span>${state.placing ? "Procesando pedido..." : "Confirmar pedido"}</span>
          <strong>${h(money(cartPayableTotal(), s.currency))} →</strong>
        </button>
        <div class="sl-trust-row"><span>✓ Compra protegida</span><span>✓ Factura automatica</span><span>✓ Soporte directo</span></div>
      </div>
    `;
  }

  function cartItemVisual(item) {
    const image = productImages(item)[0];
    return image
      ? `<img src="${h(image)}" alt="${h(item.name || "Producto")}">`
      : `<span>${h(String(item.name || "P").slice(0, 1).toUpperCase())}</span>`;
  }

  function renderCart() {
    const s = settings();
    const discount = campaignDiscount();
    const subtotal = cartTotal();
    return `
      <aside class="sl-cart ${state.cartOpen ? "open" : ""}" aria-label="Carrito y pago">
        <div class="sl-cart-head">
          <div><span class="sl-eyebrow">Checkout seguro</span><h2>Tu carrito <b>${h(cartItemsCount())}</b></h2></div>
          <button class="sl-cart-close" type="button" data-shoplink-cart-close aria-label="Cerrar carrito">×</button>
        </div>
        <div class="sl-cart-list">
          ${state.cart.length ? state.cart.map((item) => `
            <article class="sl-cart-item">
              <div class="sl-cart-thumb">${cartItemVisual(item)}</div>
              <div class="sl-cart-copy">
                <strong>${h(item.name)}</strong>
                <small>${h([item.size, item.color].filter(Boolean).join(" · ") || item.category || "Producto")}</small>
                <b>${h(money(Number(item.price || 0) * Number(item.qty || 1), s.currency))}</b>
              </div>
              <div class="sl-qty">
                <button type="button" data-shoplink-qty="${h(item.id)}" data-delta="-1" aria-label="Restar">−</button>
                <span>${h(item.qty)}</span>
                <button type="button" data-shoplink-qty="${h(item.id)}" data-delta="1" aria-label="Sumar">+</button>
              </div>
              <button class="sl-remove" type="button" data-shoplink-remove="${h(item.id)}" aria-label="Quitar ${h(item.name)}">×</button>
            </article>
          `).join("") : `<div class="sl-empty sl-cart-empty"><span>＋</span><strong>Tu carrito esta listo para estrenar</strong><small>Agrega productos y vuelve aqui para finalizar.</small></div>`}
        </div>
        <section class="sl-order-summary">
          <div><span>Subtotal</span><strong>${h(money(subtotal, s.currency))}</strong></div>
          ${discount ? `<div class="discount"><span>Descuento aplicado</span><strong>-${h(money(discount, s.currency))}</strong></div>` : ""}
          <div><span>Envio</span><strong>Por confirmar</strong></div>
          <div class="total"><span>Total</span><strong>${h(money(cartPayableTotal(), s.currency))}</strong></div>
        </section>
        ${state.order ? renderOrderSuccess() : renderCheckoutForm()}
        <button class="sl-clear-cart" type="button" data-shoplink-clear ${state.cart.length ? "" : "disabled"}>Vaciar carrito</button>
      </aside>
    `;
  }

  function renderMobileCartDock() {
    if (!state.cart.length || state.order) return "";
    return `
      <button class="sl-cart-dock" type="button" data-shoplink-cart-open>
        <span><b>${h(cartItemsCount())}</b> ${cartItemsCount() === 1 ? "producto" : "productos"}</span>
        <strong>Ver carrito · ${h(money(cartPayableTotal(), settings().currency))}</strong>
      </button>
    `;
  }

  function render() {
    if (!state.data) return;
    applyStoreTheme();
    app().innerHTML = `
      <div class="sl-shell">
        ${renderTopbar()}
        ${renderHero()}
        ${renderFeatured()}
        <div class="sl-layout">
          ${renderProducts()}
          ${renderCart()}
        </div>
        ${state.cartOpen ? `<button class="sl-cart-overlay" type="button" data-shoplink-cart-close aria-label="Cerrar carrito"></button>` : ""}
        ${renderMobileCartDock()}
      </div>
    `;
  }

  function renderError(message) {
    app().innerHTML = `
      <div class="sl-shell">
        <section class="sl-panel">
          <div class="sl-eyebrow">CLONEXA ShopLink</div>
          <h1>No se pudo cargar la tienda</h1>
          <p>${h(message)}</p>
        </section>
      </div>
    `;
  }

  async function validateCoupon() {
    const code = state.couponDraft.trim().toUpperCase();
    if (!code || !state.cart.length || state.coupon.status === "checking") return;
    state.couponDraft = code;
    state.coupon = { status: "checking", code: "", discountAmount: 0, message: "Comprobando beneficio..." };
    state.checkoutError = "";
    render();
    try {
      const companyId = companyIdFromUrl();
      const result = await api(`/shoplink/public/${encodeURIComponent(companyId)}/coupons/validate`, {
        method: "POST",
        body: JSON.stringify({
          campaign_slug: campaign()?.slug || campaignSlugFromUrl(),
          coupon_code: code,
          items: state.cart.map((item) => ({ product_id: item.id, qty: item.qty })),
        }),
      });
      if (result.valid) {
        state.coupon = {
          status: "valid",
          code: result.coupon_code || code,
          discountAmount: Number(result.discount_amount || 0),
          message: `${result.message || "Cupon aplicado."} Ahorras ${money(result.discount_amount, settings().currency)}.`,
        };
        state.appliedCampaign = result.campaign || state.appliedCampaign;
      } else {
        state.coupon = { status: "invalid", code: "", discountAmount: 0, message: result.message || "El cupon no es valido." };
      }
    } catch (error) {
      state.coupon = { status: "invalid", code: "", discountAmount: 0, message: error.message || "No se pudo validar el cupon." };
    } finally {
      render();
    }
  }

  async function placeOrder() {
    if (!state.cart.length || state.placing) return;
    document.querySelectorAll("[data-shoplink-customer]").forEach((input) => {
      state.customer[input.dataset.shoplinkCustomer] = input.value || "";
    });
    if (!String(state.customer.customer_name || "").trim() || !String(state.customer.customer_phone || "").trim()) {
      state.checkoutError = "Completa tu nombre y telefono para continuar.";
      render();
      return;
    }
    if (paymentMethods().length && !state.paymentMethod) {
      state.checkoutError = "Selecciona como quieres pagar para confirmar el pedido.";
      render();
      return;
    }
    state.placing = true;
    state.checkoutError = "";
    render();
    try {
      const companyId = companyIdFromUrl();
      const payload = {
        ...state.customer,
        campaign_slug: campaign()?.slug || campaignSlugFromUrl(),
        coupon_code: state.coupon.status === "valid" ? state.coupon.code : "",
        payment_method: state.paymentMethod,
        items: state.cart.map((item) => ({ product_id: item.id, qty: item.qty })),
      };
      const saved = await api(`/shoplink/public/${encodeURIComponent(companyId)}/orders`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      state.order = saved;
      if (!saved.owner_alert_delivery?.ok) openOwnerAlert(saved);
      state.cart = [];
    } catch (error) {
      state.checkoutError = error.message || "No se pudo crear el pedido.";
    } finally {
      state.placing = false;
      render();
    }
  }

  document.addEventListener("click", (event) => {
    const zoom = event.target.closest("[data-shoplink-zoom]");
    if (zoom) {
      openImageZoom(zoom.getAttribute("data-shoplink-zoom") || "", zoom.getAttribute("data-shoplink-zoom-title") || "");
      return;
    }

    if (event.target.closest("[data-shoplink-zoom-close]") || event.target.matches("[data-shoplink-zoom-modal]")) {
      closeImageZoom();
      return;
    }

    const category = event.target.closest("[data-shoplink-category]");
    if (category) {
      state.category = category.dataset.shoplinkCategory || "Todos";
      render();
      return;
    }

    const add = event.target.closest("[data-shoplink-add]");
    if (add) {
      addToCart(add.dataset.shoplinkAdd);
      return;
    }

    const qty = event.target.closest("[data-shoplink-qty]");
    if (qty) {
      setQty(qty.dataset.shoplinkQty, Number(qty.dataset.delta || 0));
      return;
    }

    const remove = event.target.closest("[data-shoplink-remove]");
    if (remove) {
      removeFromCart(remove.dataset.shoplinkRemove);
      return;
    }

    if (event.target.closest("[data-shoplink-clear]")) {
      state.cart = [];
      state.order = null;
      state.checkoutError = "";
      state.couponDraft = "";
      state.coupon = { status: "idle", code: "", discountAmount: 0, message: "" };
      state.appliedCampaign = null;
      render();
      return;
    }

    if (event.target.closest("[data-shoplink-apply-coupon]")) {
      validateCoupon();
      return;
    }

    if (event.target.closest("[data-shoplink-remove-coupon]")) {
      state.couponDraft = "";
      state.coupon = { status: "idle", code: "", discountAmount: 0, message: "" };
      state.appliedCampaign = null;
      render();
      return;
    }

    const payment = event.target.closest("[data-shoplink-payment]");
    if (payment) {
      state.paymentMethod = payment.dataset.shoplinkPayment || "";
      state.checkoutError = "";
      render();
      return;
    }

    if (event.target.closest("[data-shoplink-cart-open]")) {
      state.cartOpen = true;
      render();
      return;
    }

    if (event.target.closest("[data-shoplink-cart-close]")) {
      state.cartOpen = false;
      render();
      return;
    }

    if (event.target.closest("[data-shoplink-place-order]")) {
      placeOrder();
      return;
    }

    const invoice = event.target.closest("[data-shoplink-open-invoice]");
    if (invoice) {
      window.open(invoice.getAttribute("data-shoplink-open-invoice") || "", "_blank", "noopener");
      return;
    }

    if (event.target.closest("[data-shoplink-owner-alert]")) {
      openOwnerAlert(state.order || {});
      return;
    }

    if (event.target.closest("[data-shoplink-support]")) {
      window.open(supportUrl(), "_blank", "noopener");
    }
  });

  document.addEventListener("input", (event) => {
    const search = event.target.closest("[data-shoplink-search]");
    if (search) {
      state.query = search.value || "";
      window.clearTimeout(window.__shoplinkSearchTimer);
      window.__shoplinkSearchTimer = window.setTimeout(refreshProductResults, 80);
      return;
    }

    const customer = event.target.closest("[data-shoplink-customer]");
    if (customer) {
      state.customer[customer.dataset.shoplinkCustomer] = customer.value || "";
      return;
    }

    const coupon = event.target.closest("[data-shoplink-coupon]");
    if (coupon) {
      state.couponDraft = coupon.value || "";
      const applyButton = document.querySelector("[data-shoplink-apply-coupon]");
      if (applyButton) applyButton.disabled = !state.cart.length || !state.couponDraft.trim();
      if (state.coupon.status === "invalid") {
        state.coupon = { status: "idle", code: "", discountAmount: 0, message: "" };
        document.querySelector(".sl-coupon-status")?.remove();
      }
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeImageZoom();
      if (state.cartOpen) {
        state.cartOpen = false;
        render();
      }
    }
    if (event.key === "Enter" && event.target.closest("[data-shoplink-coupon]")) {
      event.preventDefault();
      validateCoupon();
    }
  });

  async function boot() {
    const companyId = companyIdFromUrl();
    if (!companyId) {
      renderError("Falta company_id en el enlace publico.");
      return;
    }
    try {
      const campaignSlug = campaignSlugFromUrl();
      state.data = await api(`/shoplink/public/${encodeURIComponent(companyId)}${campaignSlug ? `?campaign=${encodeURIComponent(campaignSlug)}` : ""}`);
      state.couponDraft = "";
      state.paymentMethod = "";
      render();
    } catch (error) {
      renderError(error.message || "Error cargando ShopLink.");
    }
  }

  boot();
})();
