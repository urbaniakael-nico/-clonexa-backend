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

  async function api(path, options = {}) {
    const res = await fetch(`${API}${path}`, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${res.status} ${res.statusText} ${text}`);
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
    state.order = null;
    state.checkoutError = "";
    render();
  }

  function setQty(productId, delta) {
    const item = state.cart.find((row) => String(row.id) === String(productId));
    if (!item) return;
    item.qty = Math.max(1, Number(item.qty || 1) + delta);
    render();
  }

  function removeFromCart(productId) {
    state.cart = state.cart.filter((item) => String(item.id) !== String(productId));
    render();
  }

  function cartTotal() {
    return state.cart.reduce((total, item) => total + Number(item.price || 0) * Number(item.qty || 1), 0);
  }

  function supportUrl() {
    const s = settings();
    const phone = String(s.whatsapp_number || "").replace(/[^0-9+]/g, "");
    const store = s.store_name || state.data?.company?.name || "Tienda";
    const text = encodeURIComponent(`${s.cta_message || "Hola, necesito ayuda con mi pedido:"}\nTienda: ${store}`);
    return phone ? `https://wa.me/${phone.replace(/^\+/, "")}?text=${text}` : `https://wa.me/?text=${text}`;
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
    const heroStyle = s.hero_image_url ? ` style="background-image:linear-gradient(90deg,rgba(10,12,18,.72),rgba(10,12,18,.18)),url('${h(s.hero_image_url)}')"` : "";
    return `
      <section class="sl-hero"${heroStyle}>
        <div>
          ${s.announcement ? `<div class="sl-announcement">${h(s.announcement)}</div>` : ""}
          <div class="sl-eyebrow">Tienda online</div>
          <h1>${h(s.headline || s.store_name || data.company?.name || "Compra en linea")}</h1>
          <p>${h(s.description || "Explora productos, arma tu carrito y haz tu pedido en la web.")}</p>
          <div class="sl-meta">
            <span>${h(products().length)} productos</span>
            <span>${h((data.categories || []).length)} categorias</span>
            <span>${s.checkout_enabled === false ? "Solo vitrina" : "Checkout web"}</span>
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
            <h2>Vitrina principal</h2>
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
    return `
      <div class="sl-success">
        <strong>Pedido recibido</strong>
        <p>Codigo ${h(state.order.order_code)}. La tienda ya registro tu compra y el equipo la gestionara.</p>
        <small>Total: ${h(money(state.order.total_amount, s.currency))}</small>
      </div>
    `;
  }

  function renderCheckoutForm() {
    const s = settings();
    if (s.checkout_enabled === false) {
      return `<div class="sl-empty">La tienda esta en modo vitrina. Los pedidos web estan desactivados.</div>`;
    }
    return `
      <div class="sl-checkout">
        <label>Nombre
          <input data-shoplink-customer="customer_name" value="${h(state.customer.customer_name || "")}" placeholder="Tu nombre">
        </label>
        <label>Telefono
          <input data-shoplink-customer="customer_phone" value="${h(state.customer.customer_phone || "")}" placeholder="+57...">
        </label>
        <label>Ciudad
          <input data-shoplink-customer="customer_city" value="${h(state.customer.customer_city || "")}" placeholder="Ciudad">
        </label>
        <label>Direccion
          <input data-shoplink-customer="customer_address" value="${h(state.customer.customer_address || "")}" placeholder="Direccion de entrega">
        </label>
        <label class="wide">Nota
          <textarea data-shoplink-customer="customer_note" placeholder="Talla, color, referencia o comentario">${h(state.customer.customer_note || "")}</textarea>
        </label>
        ${state.checkoutError ? `<div class="sl-error">${h(state.checkoutError)}</div>` : ""}
        <button class="sl-btn" type="button" data-shoplink-place-order ${state.cart.length && !state.placing ? "" : "disabled"}>
          ${state.placing ? "Enviando pedido..." : "Finalizar pedido"}
        </button>
      </div>
      <div class="sl-payment-note">
        <strong>Pagos</strong>
        <span>${h((s.payment_methods || ["Efectivo", "Transferencia", "Tarjeta"]).join(" / "))}</span>
        ${s.delivery_notes ? `<small>${h(s.delivery_notes)}</small>` : ""}
      </div>
    `;
  }

  function renderCart() {
    const s = settings();
    return `
      <aside class="sl-cart">
        <h2>Carrito</h2>
        <div class="sl-cart-list">
          ${state.cart.length ? state.cart.map((item) => `
            <div class="sl-cart-item">
              <div>
                <strong>${h(item.name)}</strong>
                <small>${h(money(Number(item.price || 0) * Number(item.qty || 1), s.currency))}</small>
              </div>
              <div class="sl-qty">
                <button type="button" data-shoplink-qty="${h(item.id)}" data-delta="-1">-</button>
                <span>${h(item.qty)}</span>
                <button type="button" data-shoplink-qty="${h(item.id)}" data-delta="1">+</button>
              </div>
              <button class="sl-remove" type="button" data-shoplink-remove="${h(item.id)}">Quitar</button>
            </div>
          `).join("") : `<div class="sl-empty">Agrega productos para iniciar tu pedido.</div>`}
        </div>
        <div class="sl-total"><span>Total</span><strong>${h(money(cartTotal(), s.currency))}</strong></div>
        ${state.order ? renderOrderSuccess() : renderCheckoutForm()}
        <button class="sl-btn secondary" type="button" data-shoplink-clear ${state.cart.length ? "" : "disabled"}>Limpiar carrito</button>
      </aside>
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

  async function placeOrder() {
    if (!state.cart.length || state.placing) return;
    state.placing = true;
    state.checkoutError = "";
    document.querySelectorAll("[data-shoplink-customer]").forEach((input) => {
      state.customer[input.dataset.shoplinkCustomer] = input.value || "";
    });
    render();
    try {
      const companyId = companyIdFromUrl();
      const payload = {
        ...state.customer,
        items: state.cart.map((item) => ({ product_id: item.id, qty: item.qty })),
      };
      const saved = await api(`/shoplink/public/${encodeURIComponent(companyId)}/orders`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      state.order = saved;
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
      render();
      return;
    }

    if (event.target.closest("[data-shoplink-place-order]")) {
      placeOrder();
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
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeImageZoom();
  });

  async function boot() {
    const companyId = companyIdFromUrl();
    if (!companyId) {
      renderError("Falta company_id en el enlace publico.");
      return;
    }
    try {
      state.data = await api(`/shoplink/public/${encodeURIComponent(companyId)}`);
      render();
    } catch (error) {
      renderError(error.message || "Error cargando ShopLink.");
    }
  }

  boot();
})();
