(() => {
  "use strict";

  const API = "/api/v1";
  const state = {
    data: null,
    category: "Todos",
    query: "",
    cart: [],
  };

  const h = (value) =>
    String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");

  const app = () => document.getElementById("shoplinkApp");

  function money(value, currency = "COP") {
    const number = Number(value || 0);
    if (!number) return "Consultar";
    return `$ ${Math.round(number).toLocaleString("es-CO")}`;
  }

  function companyIdFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return params.get("company_id") || params.get("companyId") || params.get("tenant") || "";
  }

  async function api(path) {
    const res = await fetch(`${API}${path}`);
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${res.status} ${res.statusText} ${text}`);
    }
    return res.json();
  }

  function visibleProducts() {
    const data = state.data || {};
    const q = state.query.trim().toLowerCase();
    return (data.products || []).filter((product) => {
      const categoryOk = state.category === "Todos" || String(product.category || "General") === state.category;
      const text = `${product.name || ""} ${product.category || ""} ${product.size || ""} ${product.color || ""} ${product.sku || ""}`.toLowerCase();
      return categoryOk && (!q || text.includes(q));
    });
  }

  function addToCart(productId) {
    const product = (state.data?.products || []).find((item) => String(item.id) === String(productId));
    if (!product) return;
    const existing = state.cart.find((item) => item.id === product.id);
    if (existing) existing.qty += 1;
    else state.cart.push({ ...product, qty: 1 });
    render();
  }

  function removeFromCart(productId) {
    state.cart = state.cart.filter((item) => String(item.id) !== String(productId));
    render();
  }

  function cartTotal() {
    return state.cart.reduce((total, item) => total + Number(item.price || 0) * Number(item.qty || 1), 0);
  }

  function whatsappUrl() {
    const settings = state.data?.settings || {};
    const phone = String(settings.whatsapp_number || "").replace(/[^0-9+]/g, "");
    const store = settings.store_name || state.data?.company?.name || "Tienda";
    const lines = [
      `${settings.cta_message || "Hola, quiero hacer este pedido:"}`,
      `Tienda: ${store}`,
      "",
      ...state.cart.map((item) => `- ${item.qty} x ${item.name}${item.size ? ` / ${item.size}` : ""}${item.color ? ` / ${item.color}` : ""} - ${money(Number(item.price || 0) * Number(item.qty || 1))}`),
      "",
      `Total estimado: ${money(cartTotal())}`,
    ];
    const text = encodeURIComponent(lines.join("\n"));
    return phone ? `https://wa.me/${phone.replace(/^\+/, "")}?text=${text}` : `https://wa.me/?text=${text}`;
  }

  function renderHero() {
    const data = state.data || {};
    const settings = data.settings || {};
    const logo = settings.logo_url || "";
    return `
      <section class="sl-hero">
        <div>
          <div class="sl-eyebrow">CLONEXA ShopLink</div>
          <h1>${h(settings.store_name || data.company?.name || "Tienda")}</h1>
          <p>${h(settings.headline || "Catálogo público")}</p>
          <p>${h(settings.description || "Explora productos y consulta disponibilidad por WhatsApp.")}</p>
          <div class="sl-meta">
            <span class="sl-pill">${h((data.products || []).length)} productos</span>
            <span class="sl-pill">${h((data.categories || []).length)} categorías</span>
            <span class="sl-pill">${settings.public_enabled === false ? "Privada" : "Disponible"}</span>
          </div>
        </div>
        <div class="sl-logo">${logo ? `<img src="${h(logo)}" alt="">` : h((settings.store_name || data.company?.name || "S").slice(0, 1).toUpperCase())}</div>
      </section>
    `;
  }

  function renderProducts() {
    const data = state.data || {};
    const settings = data.settings || {};
    const categories = ["Todos", ...(data.categories || [])];
    const rows = visibleProducts();
    return `
      <section class="sl-panel">
        <div class="sl-toolbar">
          <div>
            <div class="sl-eyebrow">Catálogo</div>
            <h2>Elige por categoría</h2>
            <div class="sl-muted">${h(rows.length)} de ${h((data.products || []).length)} productos visibles</div>
          </div>
          <input class="sl-search" data-shoplink-search placeholder="Buscar producto" value="${h(state.query)}">
        </div>
        <div class="sl-tabs">
          ${categories.map((category) => `
            <button class="sl-tab ${category === state.category ? "active" : ""}" type="button" data-shoplink-category="${h(category)}">
              ${h(category)}
            </button>
          `).join("")}
        </div>
        <div class="sl-products">
          ${rows.length ? rows.map((product) => `
            <article class="sl-card">
              <div>
                <h3>${h(product.name || "Producto")}</h3>
                <small>${h(product.category || "General")}${product.size ? ` · ${h(product.size)}` : ""}${product.color ? ` · ${h(product.color)}` : ""}</small>
              </div>
              <div>
                <div class="sl-price">${settings.show_prices === false ? "Consultar" : h(money(product.price, settings.currency))}</div>
                <small>${settings.show_stock === false ? h(product.status || "Disponible") : `Stock ${h(product.stock ?? 0)} · ${h(product.status || "Disponible")}`}</small>
              </div>
              <button class="sl-btn" type="button" data-shoplink-add="${h(product.id)}">Agregar</button>
            </article>
          `).join("") : `<div class="sl-empty">No hay productos visibles para este filtro.</div>`}
        </div>
      </section>
    `;
  }

  function renderCart() {
    const settings = state.data?.settings || {};
    return `
      <aside class="sl-cart">
        <h2>Tu pedido</h2>
        <div class="sl-muted">Arma la lista y envíala por WhatsApp.</div>
        <div class="sl-cart-list">
          ${state.cart.length ? state.cart.map((item) => `
            <div class="sl-cart-item">
              <div>
                <strong>${h(item.qty)} x ${h(item.name)}</strong><br>
                <small>${h(money(Number(item.price || 0) * Number(item.qty || 1), settings.currency))}</small>
              </div>
              <button type="button" data-shoplink-remove="${h(item.id)}">Quitar</button>
            </div>
          `).join("") : `<div class="sl-empty">Aún no has agregado productos.</div>`}
        </div>
        <div class="sl-total"><span>Total</span><strong>${h(money(cartTotal(), settings.currency))}</strong></div>
        <button class="sl-btn" type="button" data-shoplink-whatsapp ${state.cart.length ? "" : "disabled"}>Enviar por WhatsApp</button>
        <button class="sl-btn secondary" type="button" data-shoplink-clear>Limpiar</button>
      </aside>
    `;
  }

  function render() {
    if (!state.data) return;
    app().innerHTML = `
      <div class="sl-shell">
        ${renderHero()}
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
          <p class="sl-muted">${h(message)}</p>
        </section>
      </div>
    `;
  }

  document.addEventListener("click", (event) => {
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
    const remove = event.target.closest("[data-shoplink-remove]");
    if (remove) {
      removeFromCart(remove.dataset.shoplinkRemove);
      return;
    }
    if (event.target.closest("[data-shoplink-clear]")) {
      state.cart = [];
      render();
      return;
    }
    if (event.target.closest("[data-shoplink-whatsapp]")) {
      if (!state.cart.length) return;
      window.open(whatsappUrl(), "_blank", "noopener");
    }
  });

  document.addEventListener("input", (event) => {
    const search = event.target.closest("[data-shoplink-search]");
    if (!search) return;
    state.query = search.value || "";
    window.clearTimeout(window.__shoplinkSearchTimer);
    window.__shoplinkSearchTimer = window.setTimeout(render, 120);
  });

  async function boot() {
    const companyId = companyIdFromUrl();
    if (!companyId) {
      renderError("Falta company_id en el enlace público.");
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
