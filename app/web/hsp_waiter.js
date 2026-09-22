(() => {
  "use strict";

  const root = document.getElementById("app");
  const params = new URLSearchParams(window.location.search);
  const companyId = params.get("company_id") || params.get("companyId") || "";
  const PANEL_TYPE = "mesero";
  const storageKey = `clonexa_waiter_token_${companyId}`;

  const state = {
    screen: "login",
    error: "",
    busy: false,
    session: null,
    tables: [],
    table: "",
    menu: [],
    category: null,
    cart: [],
    sending: false,
    lastOrderOk: "",
  };

  function h(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function money(value) {
    const number = Number(value || 0);
    try {
      return new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 }).format(number);
    } catch (_) {
      return `$${Math.round(number).toLocaleString("es-CO")}`;
    }
  }

  function token() {
    return sessionStorage.getItem(storageKey) || "";
  }

  function setToken(value) {
    if (value) sessionStorage.setItem(storageKey, value);
    else sessionStorage.removeItem(storageKey);
  }

  async function api(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    const tok = token();
    if (tok) headers.Authorization = `Bearer ${tok}`;
    const response = await fetch(path, { ...options, headers });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = data.detail || data.message || "Solicitud rechazada.";
      if (response.status === 401 && /otro dispositivo/i.test(String(message))) {
        setToken("");
        state.session = null;
        state.screen = "login";
        state.error = "Tu sesión se abrió en otro dispositivo.";
        render();
      }
      throw new Error(message);
    }
    return data;
  }

  function hspApi(path, options) {
    return api(`/api/v1/hospitality/companies/${encodeURIComponent(companyId)}${path}`, options);
  }

  function waiterApi(path, options) {
    return api(`/api/v1/companies/${encodeURIComponent(companyId)}/waiter-ordering${path}`, options);
  }

  async function doLogin(username, password) {
    state.busy = true;
    state.error = "";
    render();
    try {
      const data = await api(`/api/v1/companies/${encodeURIComponent(companyId)}/mini-panel-login`, {
        method: "POST",
        body: JSON.stringify({ username, password, panel_type: PANEL_TYPE }),
      });
      setToken(data.access_token || "");
      state.session = data;
      state.screen = "table";
      await Promise.all([loadTables(), loadMenu()]);
    } catch (error) {
      state.error = error.message || "No se pudo iniciar sesión.";
    } finally {
      state.busy = false;
      render();
    }
  }

  async function loadTables() {
    try {
      const data = await hspApi("/qr-tables?count=30&include_bar=false");
      state.tables = Array.isArray(data.tables) ? data.tables : [];
    } catch (_) {
      state.tables = [];
    }
  }

  async function loadMenu() {
    try {
      const data = await waiterApi("/menu");
      state.menu = Array.isArray(data.categories) ? data.categories : [];
    } catch (error) {
      state.error = error.message || "No se pudo cargar el menú.";
    }
  }

  function cartTotal() {
    return state.cart.reduce((sum, item) => sum + Number(item.unit_price || 0) * Number(item.quantity || 0), 0);
  }

  function addToCart(product, quantity, observations, quickNotes) {
    state.cart.push({
      inventory_item_id: product.id,
      name: product.name,
      unit_price: product.price,
      quantity,
      observations,
      quick_notes: quickNotes,
    });
  }

  async function submitOrder() {
    if (!state.table || !state.cart.length) return;
    state.sending = true;
    render();
    try {
      await waiterApi("/orders", {
        method: "POST",
        body: JSON.stringify({
          table: state.table,
          items: state.cart.map((item) => ({
            inventory_item_id: item.inventory_item_id,
            quantity: item.quantity,
            observations: item.observations,
            quick_notes: item.quick_notes,
          })),
        }),
      });
      state.lastOrderOk = `Pedido enviado a ${state.table}.`;
      state.cart = [];
      state.category = null;
      state.screen = "table";
    } catch (error) {
      state.error = error.message || "No se pudo enviar el pedido.";
    } finally {
      state.sending = false;
      render();
    }
  }

  function screenLogin() {
    return `
      <section class="wtr-login">
        <div class="wtr-login-card">
          <div class="wtr-brand">CLONEXA</div>
          <h1>Panel Mesero</h1>
          ${state.error ? `<div class="wtr-alert">${h(state.error)}</div>` : ""}
          <form id="wtrLoginForm">
            <label>Usuario<input name="username" autocomplete="username" required /></label>
            <label>Clave<input name="password" type="password" autocomplete="current-password" required /></label>
            <button type="submit" class="wtr-btn wtr-btn-primary" ${state.busy ? "disabled" : ""}>${state.busy ? "Entrando..." : "Entrar"}</button>
          </form>
        </div>
      </section>`;
  }

  function screenTable() {
    const tables = state.tables.length
      ? state.tables.map((t) => t.label)
      : Array.from({ length: 20 }, (_, i) => `Mesa ${i + 1}`);
    return `
      <section class="wtr-shell">
        ${header("Elige la mesa")}
        ${state.lastOrderOk ? `<div class="wtr-toast">${h(state.lastOrderOk)}</div>` : ""}
        <div class="wtr-grid-tables">
          ${tables.map((label) => `<button class="wtr-tile" type="button" data-wtr-table="${h(label)}">${h(label)}</button>`).join("")}
        </div>
      </section>`;
  }

  function screenCategories() {
    return `
      <section class="wtr-shell">
        ${header(`Mesa ${h(state.table)}`, true)}
        <div class="wtr-grid-cat">
          ${state.menu.map((cat) => `
            <button class="wtr-cat-tile" type="button" data-wtr-cat="${h(cat.key)}">
              <div class="wtr-cat-img" style="background-image:url('/api/v1/companies/${encodeURIComponent(companyId)}/waiter-ordering/categories/${encodeURIComponent(cat.key)}/image')">${cat.has_image ? "" : "🍽️"}</div>
              <span>${h(cat.label)}</span>
            </button>`).join("") || `<div class="wtr-empty">Sin categorías todavía.</div>`}
        </div>
      </section>`;
  }

  function screenProducts() {
    const category = state.menu.find((cat) => cat.key === state.category);
    const products = category ? category.products : [];
    return `
      <section class="wtr-shell">
        ${header(category ? category.label : "Productos", true)}
        <div class="wtr-grid-prod">
          ${products.map((product) => `
            <button class="wtr-prod-tile" type="button" data-wtr-product="${h(product.id)}">
              <span>${h(product.name)}</span>
              <strong>${h(money(product.price))}</strong>
            </button>`).join("") || `<div class="wtr-empty">Sin productos en esta categoría.</div>`}
        </div>
        ${state.cart.length ? `<button class="wtr-btn wtr-btn-cart" type="button" data-wtr-goto-cart>Ver pedido (${state.cart.length}) · ${h(money(cartTotal()))}</button>` : ""}
      </section>`;
  }

  function screenCart() {
    return `
      <section class="wtr-shell">
        ${header("Revisar pedido", true)}
        <div class="wtr-cart-list">
          ${state.cart.map((item, index) => `
            <div class="wtr-cart-row">
              <div>
                <b>${h(item.quantity)} x ${h(item.name)}</b>
                ${item.observations ? `<div class="wtr-cart-note">${h(item.observations)}</div>` : ""}
                ${item.quick_notes.length ? `<div class="wtr-cart-note">${item.quick_notes.map(h).join(" · ")}</div>` : ""}
              </div>
              <div class="wtr-cart-row-actions">
                <strong>${h(money(item.unit_price * item.quantity))}</strong>
                <button type="button" data-wtr-remove="${index}" aria-label="Quitar">✕</button>
              </div>
            </div>`).join("") || `<div class="wtr-empty">Todavía no agregaste productos.</div>`}
        </div>
        <div class="wtr-cart-total"><span>Total</span><strong>${h(money(cartTotal()))}</strong></div>
        <button class="wtr-btn wtr-btn-primary" type="button" data-wtr-send ${state.sending || !state.cart.length ? "disabled" : ""}>
          ${state.sending ? "Enviando..." : "Enviar pedido"}
        </button>
      </section>`;
  }

  function header(title, showBack = false) {
    return `
      <header class="wtr-header">
        ${showBack ? `<button class="wtr-back" type="button" data-wtr-back aria-label="Volver">‹</button>` : ""}
        <h1>${h(title)}</h1>
        <button class="wtr-logout" type="button" data-wtr-logout aria-label="Salir">⏻</button>
      </header>`;
  }

  function render() {
    let html = "";
    if (state.screen === "login") html = screenLogin();
    else if (state.screen === "table") html = screenTable();
    else if (state.screen === "categories") html = screenCategories();
    else if (state.screen === "products") html = screenProducts();
    else if (state.screen === "cart") html = screenCart();
    root.innerHTML = html;
    if (state.error && state.screen !== "login") {
      const banner = document.createElement("div");
      banner.className = "wtr-alert wtr-alert-floating";
      banner.textContent = state.error;
      root.appendChild(banner);
      window.setTimeout(() => { state.error = ""; }, 4000);
    }
  }

  document.addEventListener("submit", (event) => {
    const form = event.target.closest("#wtrLoginForm");
    if (!form) return;
    event.preventDefault();
    const data = new FormData(form);
    doLogin(String(data.get("username") || ""), String(data.get("password") || ""));
  });

  document.addEventListener("click", (event) => {
    const target = event.target;

    const logout = target.closest("[data-wtr-logout]");
    if (logout) {
      setToken("");
      state.session = null;
      state.screen = "login";
      render();
      return;
    }

    const back = target.closest("[data-wtr-back]");
    if (back) {
      if (state.screen === "cart") state.screen = "products";
      else if (state.screen === "products") state.screen = "categories";
      else if (state.screen === "categories") state.screen = "table";
      render();
      return;
    }

    const tableBtn = target.closest("[data-wtr-table]");
    if (tableBtn) {
      state.table = tableBtn.getAttribute("data-wtr-table") || "";
      state.screen = "categories";
      render();
      return;
    }

    const catBtn = target.closest("[data-wtr-cat]");
    if (catBtn) {
      state.category = catBtn.getAttribute("data-wtr-cat") || "";
      state.screen = "products";
      render();
      return;
    }

    const gotoCart = target.closest("[data-wtr-goto-cart]");
    if (gotoCart) {
      state.screen = "cart";
      render();
      return;
    }

    const removeBtn = target.closest("[data-wtr-remove]");
    if (removeBtn) {
      const index = Number(removeBtn.getAttribute("data-wtr-remove"));
      state.cart.splice(index, 1);
      render();
      return;
    }

    const sendBtn = target.closest("[data-wtr-send]");
    if (sendBtn && !sendBtn.disabled) {
      submitOrder();
      return;
    }

    const productBtn = target.closest("[data-wtr-product]");
    if (productBtn) {
      const category = state.menu.find((cat) => cat.key === state.category);
      const product = (category ? category.products : []).find((item) => item.id === productBtn.getAttribute("data-wtr-product"));
      if (!product) return;
      const quickOptions = (category && category.quick_notes) || [];
      openProductSheet(product, quickOptions);
    }
  });

  function openProductSheet(product, quickOptions) {
    const sheet = document.createElement("div");
    sheet.className = "wtr-sheet-backdrop";
    sheet.innerHTML = `
      <div class="wtr-sheet">
        <h2>${h(product.name)}</h2>
        <label>Cantidad<input id="wtrSheetQty" type="number" min="1" step="1" value="1" /></label>
        ${quickOptions.length ? `
          <div class="wtr-quick-notes">
            ${quickOptions.map((note, i) => `<button type="button" class="wtr-quick-note" data-note-index="${i}">${h(note)}</button>`).join("")}
          </div>` : ""}
        <label>Observaciones<textarea id="wtrSheetObs" rows="2" placeholder="Ej: sin sal, bien asado..."></textarea></label>
        <div class="wtr-sheet-actions">
          <button type="button" class="wtr-btn" data-sheet-cancel>Cancelar</button>
          <button type="button" class="wtr-btn wtr-btn-primary" data-sheet-add>Agregar</button>
        </div>
      </div>`;
    document.body.appendChild(sheet);
    const selectedNotes = new Set();
    sheet.querySelectorAll("[data-note-index]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = Number(btn.getAttribute("data-note-index"));
        const note = quickOptions[idx];
        if (selectedNotes.has(note)) { selectedNotes.delete(note); btn.classList.remove("is-active"); }
        else { selectedNotes.add(note); btn.classList.add("is-active"); }
      });
    });
    sheet.querySelector("[data-sheet-cancel]").addEventListener("click", () => sheet.remove());
    sheet.querySelector("[data-sheet-add]").addEventListener("click", () => {
      const qty = Math.max(1, Number(sheet.querySelector("#wtrSheetQty").value || 1));
      const obs = String(sheet.querySelector("#wtrSheetObs").value || "");
      addToCart(product, qty, obs, Array.from(selectedNotes));
      sheet.remove();
      render();
    });
  }

  const style = document.createElement("style");
  style.textContent = `
    :root{color-scheme:dark}
    *{box-sizing:border-box}
    body{margin:0;background:#080712;color:#f5f3ff;font-family:Inter,system-ui,sans-serif}
    .wtr-login{min-height:100vh;display:grid;place-items:center;padding:20px;
      background:radial-gradient(circle at 20% 15%,rgba(247,37,133,.25),transparent 35%),linear-gradient(135deg,#0a0714,#0d1522 70%,#150019)}
    .wtr-login-card{width:100%;max-width:360px;padding:28px 22px;border-radius:22px;border:1px solid rgba(255,255,255,.12);background:rgba(15,12,28,.85)}
    .wtr-brand{font-size:12px;font-weight:900;letter-spacing:.2em;color:#ff2d95}
    .wtr-login-card h1{margin:6px 0 18px;font-size:26px}
    .wtr-login-card form{display:grid;gap:14px}
    .wtr-login-card label{display:grid;gap:6px;font-size:13px;font-weight:800;color:#c9c3e6}
    .wtr-login-card input{padding:14px;border-radius:14px;border:1px solid rgba(255,255,255,.16);background:rgba(3,7,18,.6);color:#fff;font-size:16px}
    .wtr-btn{min-height:52px;border-radius:16px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#fff;font-size:16px;font-weight:900;cursor:pointer}
    .wtr-btn-primary{border:none;background:linear-gradient(135deg,#ff7a18,#ff2d95 55%,#a855f7);width:100%}
    .wtr-btn-primary:disabled{opacity:.6}
    .wtr-alert{margin-top:10px;padding:10px 12px;border-radius:12px;background:rgba(239,68,68,.16);color:#fecaca;font-size:13px;font-weight:800}
    .wtr-alert-floating{position:fixed;left:16px;right:16px;bottom:16px;z-index:50}
    .wtr-toast{margin:0 16px 10px;padding:10px 12px;border-radius:12px;background:rgba(34,197,94,.16);color:#bbf7d0;font-weight:800}
    .wtr-shell{min-height:100vh;padding-bottom:24px}
    .wtr-header{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:10px;padding:16px;background:rgba(8,7,18,.92);backdrop-filter:blur(6px);border-bottom:1px solid rgba(255,255,255,.08)}
    .wtr-header h1{flex:1;margin:0;font-size:20px}
    .wtr-back,.wtr-logout{width:44px;height:44px;border-radius:14px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#fff;font-size:20px}
    .wtr-grid-tables{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:12px;padding:16px}
    .wtr-tile{min-height:72px;border-radius:18px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#fff;font-size:16px;font-weight:900}
    .wtr-grid-cat{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:14px;padding:16px}
    .wtr-cat-tile{display:grid;gap:8px;border-radius:20px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.05);color:#fff;padding:0 0 12px;overflow:hidden}
    .wtr-cat-img{height:100px;display:grid;place-items:center;font-size:34px;background-size:cover;background-position:center;background-color:rgba(255,255,255,.06)}
    .wtr-cat-tile span{font-size:15px;font-weight:900}
    .wtr-grid-prod{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;padding:16px}
    .wtr-prod-tile{min-height:76px;display:grid;gap:6px;align-content:center;border-radius:18px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.05);color:#fff;padding:12px;text-align:left}
    .wtr-prod-tile strong{color:#ffd166}
    .wtr-btn-cart{position:fixed;left:16px;right:16px;bottom:16px}
    .wtr-cart-list{display:grid;gap:10px;padding:16px}
    .wtr-cart-row{display:flex;justify-content:space-between;gap:10px;padding:12px;border-radius:16px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.04)}
    .wtr-cart-note{font-size:12px;color:#ffb3d9}
    .wtr-cart-row-actions{display:flex;align-items:center;gap:10px}
    .wtr-cart-row-actions button{width:32px;height:32px;border-radius:10px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#fff}
    .wtr-cart-total{display:flex;justify-content:space-between;padding:0 16px;font-size:18px;font-weight:900;margin-bottom:14px}
    .wtr-shell > .wtr-btn-primary{margin:0 16px;width:calc(100% - 32px)}
    .wtr-empty{padding:20px;color:#8f8aa8;text-align:center}
    .wtr-sheet-backdrop{position:fixed;inset:0;background:rgba(0,0,0,.6);display:grid;align-items:end;z-index:60}
    .wtr-sheet{background:#120e20;border-radius:24px 24px 0 0;padding:22px;display:grid;gap:14px}
    .wtr-sheet h2{margin:0}
    .wtr-sheet label{display:grid;gap:6px;font-size:13px;font-weight:800;color:#c9c3e6}
    .wtr-sheet input,.wtr-sheet textarea{padding:12px;border-radius:12px;border:1px solid rgba(255,255,255,.16);background:rgba(3,7,18,.6);color:#fff;font:inherit}
    .wtr-quick-notes{display:flex;flex-wrap:wrap;gap:8px}
    .wtr-quick-note{padding:8px 12px;border-radius:999px;border:1px solid rgba(255,255,255,.18);background:rgba(255,255,255,.05);color:#fff;font-size:12px;font-weight:800}
    .wtr-quick-note.is-active{background:linear-gradient(135deg,#ff7a18,#ff2d95);border-color:transparent}
    .wtr-sheet-actions{display:flex;gap:10px}
    .wtr-sheet-actions .wtr-btn{flex:1}
  `;
  document.head.appendChild(style);

  if (!companyId) {
    root.innerHTML = `<section style="min-height:100vh;display:grid;place-items:center;background:#080712;color:#fff"><p>Falta company_id en el enlace.</p></section>`;
  } else if (token()) {
    state.screen = "table";
    Promise.all([loadTables(), loadMenu()]).then(render);
    render();
  } else {
    render();
  }
})();
