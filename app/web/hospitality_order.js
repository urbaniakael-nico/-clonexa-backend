(() => {
  "use strict";

  const API = "/api/v1";
  const app = document.getElementById("app");
  const params = new URLSearchParams(window.location.search);
  const state = {
    companyId: params.get("company_id") || params.get("companyId") || "",
    table: params.get("mesa") || params.get("table") || "Mesa",
    company: {},
    branding: {},
    inventory: [],
    cart: new Map(),
    category: "Todos",
    search: "",
    loading: true,
    message: "",
    error: "",
  };

  const h = (value) =>
    String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");

  async function api(path, options = {}) {
    const res = await fetch(`${API}${path}`, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${res.status} ${res.statusText} ${text}`.trim());
    }
    return res.json();
  }

  function money(value) {
    try {
      return new Intl.NumberFormat("es-CO", {
        style: "currency",
        currency: "COP",
        maximumFractionDigits: 0,
      }).format(Number(value || 0));
    } catch (_) {
      return `$ ${Number(value || 0).toLocaleString("es-CO")}`;
    }
  }

  function normalizeText(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .trim();
  }

  function prettyLabel(value) {
    const clean = String(value || "Otros")
      .replace(/[^\w\s\u00c0-\u017f]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    if (!clean) return "Otros";
    return clean
      .split(" ")
      .map((part) => part.slice(0, 1).toUpperCase() + part.slice(1).toLowerCase())
      .join(" ");
  }

  function productCategory(item) {
    const explicit = item.category || item.category_name || item.group || item.family;
    if (explicit) return prettyLabel(explicit);
    const firstWord = String(item.name || "").trim().split(/\s+/)[0] || "Otros";
    return prettyLabel(firstWord);
  }

  function productCategories() {
    const counts = new Map();
    state.inventory.forEach((item) => {
      const category = productCategory(item);
      counts.set(category, (counts.get(category) || 0) + 1);
    });
    const grouped = [...counts.entries()]
      .sort((a, b) => a[0].localeCompare(b[0], "es"))
      .map(([name, count]) => ({ name, count }));
    return [{ name: "Todos", count: state.inventory.length }, ...grouped];
  }

  function visibleProducts() {
    const validCategories = new Set(productCategories().map((item) => item.name));
    if (!validCategories.has(state.category)) state.category = "Todos";
    const query = normalizeText(state.search);
    return state.inventory.filter((item) => {
      const category = productCategory(item);
      const inCategory = state.category === "Todos" || category === state.category;
      if (!inCategory) return false;
      if (!query) return true;
      return normalizeText(`${item.name || ""} ${item.sku || ""} ${category}`).includes(query);
    });
  }

  function brand() {
    const b = state.branding || {};
    return {
      primary: b.primary_color || b.color_principal || "#ff8a1c",
      secondary: b.secondary_color || b.color_secundario || "#f6cf98",
      bg: b.background_color || b.color_fondo || "#120022",
      text: b.text_color || b.color_texto || "#fff7ed",
      logo: b.logo_url || "",
    };
  }

  function injectStyles() {
    const b = brand();
    let style = document.getElementById("hspPublicQrStyles024X");
    if (!style) {
      style = document.createElement("style");
      style.id = "hspPublicQrStyles024X";
      document.head.appendChild(style);
    }
    style.textContent = `
      :root{
        --qr-primary:${b.primary};
        --qr-secondary:${b.secondary};
        --qr-bg:${b.bg};
        --qr-text:${b.text};
        --qr-card:rgba(15,23,42,.72);
        --qr-line:rgba(255,255,255,.14);
        --qr-muted:rgba(255,255,255,.68);
      }
      *{box-sizing:border-box}
      body{
        margin:0;
        min-height:100vh;
        color:var(--qr-text);
        background:
          radial-gradient(circle at 0% 0%, color-mix(in srgb,var(--qr-primary) 45%, transparent), transparent 32%),
          radial-gradient(circle at 100% 0%, color-mix(in srgb,var(--qr-secondary) 35%, transparent), transparent 30%),
          linear-gradient(135deg,var(--qr-bg),#070312 72%);
        font-family:Inter,Segoe UI,system-ui,sans-serif;
      }
      button,input,textarea{font:inherit}
      .qr-shell{min-height:100vh;padding:16px;display:grid;gap:14px;max-width:1180px;margin:0 auto}
      .qr-hero,.qr-card,.qr-cart{
        background:linear-gradient(145deg,rgba(255,255,255,.10),rgba(255,255,255,.035)),var(--qr-card);
        border:1px solid var(--qr-line);
        border-radius:22px;
        box-shadow:0 22px 70px rgba(0,0,0,.28);
        backdrop-filter:blur(20px) saturate(1.2);
      }
      .qr-hero{padding:22px;display:grid;grid-template-columns:1fr auto;gap:14px;align-items:center}
      .qr-logo{width:54px;height:54px;border-radius:16px;display:grid;place-items:center;overflow:hidden;background:linear-gradient(135deg,var(--qr-primary),var(--qr-secondary));color:#111827;font-weight:1000}
      .qr-logo img{width:100%;height:100%;object-fit:contain}
      .qr-eyebrow{margin:0 0 6px;color:var(--qr-primary);font-size:11px;letter-spacing:.16em;text-transform:uppercase;font-weight:1000}
      h1{margin:0;font-size:clamp(30px,8vw,58px);line-height:.95;letter-spacing:-.03em}
      .qr-muted{color:var(--qr-muted);font-weight:750;line-height:1.35}
      .qr-layout{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:14px;align-items:start}
      .qr-menu{display:grid;gap:12px}
      .qr-menu-head{display:grid;grid-template-columns:minmax(0,1fr) minmax(220px,320px);gap:12px;align-items:end}
      .qr-menu-title{margin:0;font-size:22px;line-height:1.05}
      .qr-search{
        width:100%;
        border:1px solid var(--qr-line);
        border-radius:16px;
        background:rgba(2,6,23,.58);
        color:var(--qr-text);
        padding:13px 14px;
        outline:none;
        font-weight:900;
      }
      .qr-search::placeholder{color:rgba(255,255,255,.42)}
      .qr-categories{display:flex;gap:8px;overflow:auto;padding:2px 2px 6px;scrollbar-width:thin}
      .qr-category{
        border:1px solid var(--qr-line);
        border-radius:999px;
        padding:10px 13px;
        min-height:40px;
        white-space:nowrap;
        color:var(--qr-text);
        background:rgba(255,255,255,.075);
        font-weight:1000;
        cursor:pointer;
      }
      .qr-category.active{
        color:#101827;
        border-color:transparent;
        background:linear-gradient(135deg,var(--qr-primary),var(--qr-secondary));
      }
      .qr-category small{opacity:.7;font-size:11px}
      .qr-menu-meta{color:var(--qr-muted);font-size:12px;font-weight:900}
      .qr-products{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}
      .qr-card{padding:14px;display:grid;gap:12px;min-height:176px}
      .qr-product-name{font-size:17px;font-weight:950;line-height:1.1;word-break:break-word}
      .qr-stock{color:var(--qr-muted);font-size:12px;font-weight:850}
      .qr-price{font-size:22px;font-weight:1000;color:var(--qr-secondary)}
      .qr-btn{
        border:0;
        border-radius:14px;
        padding:12px 14px;
        min-height:44px;
        color:#101827;
        background:linear-gradient(135deg,var(--qr-primary),var(--qr-secondary));
        font-weight:1000;
        cursor:pointer;
      }
      .qr-btn.secondary{background:rgba(255,255,255,.09);color:var(--qr-text);border:1px solid var(--qr-line)}
      .qr-cart{position:sticky;top:14px;padding:16px;display:grid;gap:12px}
      .qr-cart h2{margin:0;font-size:22px}
      .qr-field{display:grid;gap:6px}
      .qr-field span{font-size:11px;letter-spacing:.11em;text-transform:uppercase;color:var(--qr-muted);font-weight:1000}
      .qr-field input,.qr-field textarea{
        width:100%;
        border:1px solid var(--qr-line);
        border-radius:14px;
        background:rgba(2,6,23,.58);
        color:var(--qr-text);
        padding:12px;
        outline:none;
        font-weight:850;
      }
      .qr-field textarea{min-height:76px;resize:vertical}
      .qr-line{display:grid;grid-template-columns:1fr auto;gap:8px;padding:10px 0;border-bottom:1px solid rgba(255,255,255,.09)}
      .qr-line-name{font-weight:950;line-height:1.15}
      .qr-qty{display:flex;align-items:center;gap:6px}
      .qr-qty button{width:32px;height:32px;border-radius:10px;border:1px solid var(--qr-line);background:rgba(255,255,255,.08);color:var(--qr-text);font-weight:1000;cursor:pointer}
      .qr-total{display:flex;justify-content:space-between;align-items:center;padding:12px;border-radius:16px;background:rgba(0,0,0,.24);font-weight:1000}
      .qr-total strong{font-size:22px;color:var(--qr-secondary)}
      .qr-msg{padding:12px;border-radius:14px;background:rgba(34,197,94,.13);border:1px solid rgba(34,197,94,.28);color:#bbf7d0;font-weight:900}
      .qr-msg.err{background:rgba(239,68,68,.13);border-color:rgba(239,68,68,.30);color:#fecaca}
      .qr-empty{border:1px dashed rgba(255,255,255,.18);border-radius:16px;padding:18px;text-align:center;color:var(--qr-muted);font-weight:850}
      @media(max-width:860px){
        .qr-hero{grid-template-columns:1fr}
        .qr-layout{grid-template-columns:1fr}
        .qr-menu-head{grid-template-columns:1fr}
        .qr-cart{position:static}
      }
    `;
  }

  function cartRows() {
    const rows = [...state.cart.values()];
    if (!rows.length) return `<div class="qr-empty">Aun no has agregado productos.</div>`;
    return rows.map((item) => `
      <div class="qr-line">
        <div>
          <div class="qr-line-name">${h(item.name)}</div>
          <div class="qr-stock">${Number(item.price || 0) > 0 ? h(money(item.price)) : "Valor por confirmar"}</div>
        </div>
        <div class="qr-qty">
          <button type="button" data-dec="${h(item.id)}">-</button>
          <strong>${h(item.quantity)}</strong>
          <button type="button" data-inc="${h(item.id)}">+</button>
        </div>
      </div>
    `).join("");
  }

  function cartTotal() {
    return [...state.cart.values()].reduce((sum, item) => sum + Number(item.quantity || 0) * Number(item.price || 0), 0);
  }

  function render() {
    injectStyles();
    const b = brand();
    const companyName = state.company.name || state.company.company_name || "CLONEXA";
    document.title = `${companyName} | ${state.table}`;

    if (!state.companyId) {
      app.innerHTML = `<main class="qr-shell"><div class="qr-msg err">Falta company_id en el QR.</div></main>`;
      return;
    }

    if (state.loading) {
      app.innerHTML = `<main class="qr-shell"><section class="qr-hero"><div><p class="qr-eyebrow">Mesa QR</p><h1>${h(state.table)}</h1><p class="qr-muted">Cargando menu...</p></div></section></main>`;
      return;
    }

    const categories = productCategories();
    const products = visibleProducts();
    const categoryButtons = categories.map((item) => `
      <button class="qr-category ${item.name === state.category ? "active" : ""}" type="button" data-category="${h(item.name)}">
        ${h(item.name)} <small>${h(item.count)}</small>
      </button>
    `).join("");
    const productCards = products.length
      ? products.map((item) => `
          <article class="qr-card">
            <div>
              <div class="qr-product-name">${h(item.name)}</div>
              <div class="qr-stock">${h(productCategory(item))}</div>
              <div class="qr-stock">Stock ${h(item.stock ?? 0)}</div>
            </div>
            <div class="qr-price">${Number(item.price || 0) > 0 ? h(money(item.price)) : "Por confirmar"}</div>
            <button class="qr-btn" type="button" data-add="${h(item.id)}">Agregar</button>
          </article>
        `).join("")
      : `<div class="qr-empty">${state.inventory.length ? "No encontramos productos con ese filtro." : "No hay productos activos para esta mesa."}</div>`;

    app.innerHTML = `
      <main class="qr-shell">
        <section class="qr-hero">
          <div>
            <p class="qr-eyebrow">Mesa QR</p>
            <h1>${h(state.table)}</h1>
            <p class="qr-muted">${h(companyName)} - arma tu pedido y queda en pendiente para el barman.</p>
          </div>
          <div class="qr-logo">${b.logo ? `<img src="${h(b.logo)}" alt="${h(companyName)}">` : h(companyName.slice(0, 1).toUpperCase())}</div>
        </section>

        ${state.message ? `<div class="qr-msg">${h(state.message)}</div>` : ""}
        ${state.error ? `<div class="qr-msg err">${h(state.error)}</div>` : ""}

        <section class="qr-layout">
          <div class="qr-menu">
            <div class="qr-menu-head">
              <div>
                <p class="qr-eyebrow">Menu</p>
                <h2 class="qr-menu-title">Elige por categoria</h2>
              </div>
              <input id="qrSearch024X" class="qr-search" placeholder="Buscar producto" value="${h(state.search)}" autocomplete="off">
            </div>
            <div class="qr-categories">${categoryButtons}</div>
            <div class="qr-menu-meta">${h(products.length)} de ${h(state.inventory.length)} productos visibles</div>
            <div class="qr-products">${productCards}</div>
          </div>
          <aside class="qr-cart">
            <h2>Tu pedido</h2>
            <label class="qr-field">
              <span>Nombre</span>
              <input id="qrCustomer024S" placeholder="Ej: Javier" value="${h(document.getElementById("qrCustomer024S")?.value || "")}">
            </label>
            <div id="qrCartLines024S">${cartRows()}</div>
            <label class="qr-field">
              <span>Canciones</span>
              <input id="qrSongs024S" placeholder="Ej: Salsa choque, Provenza" value="${h(document.getElementById("qrSongs024S")?.value || "")}">
            </label>
            <label class="qr-field">
              <span>Notas</span>
              <textarea id="qrNotes024S" placeholder="Sin hielo, poco dulce...">${h(document.getElementById("qrNotes024S")?.value || "")}</textarea>
            </label>
            <div class="qr-total"><span>Total</span><strong>${cartTotal() > 0 ? h(money(cartTotal())) : "Por confirmar"}</strong></div>
            <button class="qr-btn" type="button" data-submit-order>Enviar pedido</button>
            <button class="qr-btn secondary" type="button" data-clear-cart>Limpiar</button>
          </aside>
        </section>
      </main>
    `;
  }

  function addItem(id) {
    const item = state.inventory.find((row) => String(row.id) === String(id));
    if (!item) return;
    const current = state.cart.get(String(id)) || {
      id: String(item.id),
      name: item.name,
      sku: item.sku || "",
      price: Number(item.price || item.unit_price || item.sale_price || 0) || 0,
      quantity: 0,
    };
    current.quantity += 1;
    state.cart.set(String(id), current);
    state.message = "";
    state.error = "";
    render();
  }

  function updateQty(id, delta) {
    const current = state.cart.get(String(id));
    if (!current) return;
    current.quantity += delta;
    if (current.quantity <= 0) state.cart.delete(String(id));
    else state.cart.set(String(id), current);
    render();
  }

  async function submitOrder() {
    const items = [...state.cart.values()].filter((item) => Number(item.quantity || 0) > 0);
    if (!items.length) {
      state.error = "Agrega al menos un producto.";
      state.message = "";
      render();
      return;
    }

    try {
      state.error = "";
      state.message = "Enviando pedido...";
      render();
      const customer = document.getElementById("qrCustomer024S")?.value || "Cliente mesa";
      const songs = document.getElementById("qrSongs024S")?.value || "";
      const notes = document.getElementById("qrNotes024S")?.value || "";
      const payload = {
        table: state.table,
        customer,
        source: "qr",
        songs,
        notes,
        items: items.map((item) => ({
          inventory_item_id: item.id,
          product_id: item.id,
          sku: item.sku || "",
          name: item.name,
          quantity: item.quantity,
          unit_price: item.price,
        })),
      };
      const response = await api(`/hospitality/companies/${encodeURIComponent(state.companyId)}/orders`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      state.cart.clear();
      state.message = `Pedido enviado: ${response.order?.order_number || "recibido"}.`;
      state.error = "";
      render();
    } catch (error) {
      state.error = error.message || "No se pudo enviar el pedido.";
      state.message = "";
      render();
    }
  }

  async function load() {
    try {
      const [company, branding, inventory] = await Promise.all([
        api(`/companies/${encodeURIComponent(state.companyId)}`),
        api(`/companies/${encodeURIComponent(state.companyId)}/branding`).catch(() => ({})),
        api(`/hospitality/companies/${encodeURIComponent(state.companyId)}/inventory-lite?limit=300`),
      ]);
      state.company = company || {};
      state.branding = branding.branding || branding || {};
      state.inventory = Array.isArray(inventory.inventory) ? inventory.inventory : [];
      state.loading = false;
      state.error = "";
    } catch (error) {
      state.loading = false;
      state.error = error.message || "No se pudo cargar la mesa.";
    }
    render();
  }

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;

    const category = target.closest("[data-category]");
    if (category) {
      state.category = category.getAttribute("data-category") || "Todos";
      state.error = "";
      state.message = "";
      render();
      return;
    }
    const add = target.closest("[data-add]");
    if (add) {
      addItem(add.getAttribute("data-add"));
      return;
    }
    const inc = target.closest("[data-inc]");
    if (inc) {
      updateQty(inc.getAttribute("data-inc"), 1);
      return;
    }
    const dec = target.closest("[data-dec]");
    if (dec) {
      updateQty(dec.getAttribute("data-dec"), -1);
      return;
    }
    if (target.closest("[data-clear-cart]")) {
      state.cart.clear();
      state.message = "";
      state.error = "";
      render();
      return;
    }
    if (target.closest("[data-submit-order]")) {
      submitOrder();
    }
  });

  document.addEventListener("input", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) return;
    if (target.id !== "qrSearch024X") return;
    state.search = target.value;
    state.error = "";
    state.message = "";
    render();
    const search = document.getElementById("qrSearch024X");
    if (search instanceof HTMLInputElement) {
      search.focus();
      const end = search.value.length;
      search.setSelectionRange(end, end);
    }
  });

  render();
  load();
})();
