(() => {
  "use strict";

  const root = document.getElementById("app");
  const params = new URLSearchParams(window.location.search);
  const companyId = params.get("company_id") || params.get("companyId") || "";
  const PANEL_TYPE = "mesero";
  const storageKey = `clonexa_waiter_token_${companyId}`;
  const cartKey = `clonexa_waiter_cart_${companyId}`;
  const TERM_STOPS = ["Crudo", "Medio", "3/4", "Bien cocinado"];

  const state = {
    screen: "login",
    stack: ["home"],
    error: "",
    busy: false,
    session: null,
    companyName: "",
    mesero: "",
    tables: [],
    table: "",
    menu: [],
    category: null,
    cart: [],
    sending: false,
    sendError: "",
    lastOrderOk: "",
    shiftExpanded: false,
    operational: null,
    ventasHoy: null,
    misMesas: [],
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

  function formatHMS(totalSeconds) {
    const seconds = Math.max(0, Number(totalSeconds || 0));
    const h2 = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h2 > 0) return `${h2}h ${String(m).padStart(2, "0")}m`;
    return `${m}m`;
  }

  function token() {
    return sessionStorage.getItem(storageKey) || "";
  }

  function setToken(value) {
    if (value) sessionStorage.setItem(storageKey, value);
    else sessionStorage.removeItem(storageKey);
  }

  // ---------------------------------------------------------------------
  // Cart resilience: mirrored to sessionStorage on every change so a failed
  // send (or a reload) never loses what the mesero already built.
  // ---------------------------------------------------------------------
  function persistCart() {
    try {
      sessionStorage.setItem(cartKey, JSON.stringify({ table: state.table, cart: state.cart }));
    } catch (_) {}
  }

  function restoreCart() {
    try {
      const raw = sessionStorage.getItem(cartKey);
      if (!raw) return;
      const data = JSON.parse(raw);
      if (data && Array.isArray(data.cart) && data.cart.length) {
        state.table = data.table || "";
        state.cart = data.cart;
      }
    } catch (_) {}
  }

  function clearPersistedCart() {
    try {
      sessionStorage.removeItem(cartKey);
    } catch (_) {}
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

  function mpApi(path, options) {
    return api(`/api/v1/companies/${encodeURIComponent(companyId)}${path}`, options);
  }

  // ---------------------------------------------------------------------
  // Nav stack: home is the root; every other screen pushes on top of it so
  // "back" always lands somewhere sensible regardless of how a screen was
  // reached (Tomar pedido -> mesa -> categorias, or Mis mesas -> categorias
  // directly).
  // ---------------------------------------------------------------------
  function goto(screen) {
    state.stack.push(screen);
    state.screen = screen;
    render();
  }

  function back() {
    if (state.stack.length > 1) state.stack.pop();
    state.screen = state.stack[state.stack.length - 1];
    render();
  }

  function resetToHome() {
    state.stack = ["home"];
    state.screen = "home";
    render();
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
      state.companyName = (data.company && data.company.name) || "CLONEXA";
      state.mesero = (data.user && data.user.full_name) || "Mesero";
      restoreCart();
      await enterHome();
      startHomeRefresh();
    } catch (error) {
      state.error = error.message || "No se pudo iniciar sesión.";
    } finally {
      state.busy = false;
      render();
    }
  }

  async function enterHome() {
    state.stack = ["home"];
    state.screen = "home";
    await Promise.all([loadTables(), loadMenu(), loadOperational(), loadVentasHoy(), loadMisMesas()]);
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

  async function loadOperational() {
    try {
      const data = await mpApi(`/mini-panel-operational-session?panel_type=${PANEL_TYPE}`);
      state.operational = data.operational_session || null;
    } catch (_) {
      state.operational = null;
    }
  }

  async function loadVentasHoy() {
    try {
      state.ventasHoy = await waiterApi("/mesero/ventas-hoy");
    } catch (_) {
      state.ventasHoy = null;
    }
  }

  async function loadMisMesas() {
    try {
      const data = await waiterApi("/mesero/mis-mesas");
      state.misMesas = Array.isArray(data.tables) ? data.tables : [];
    } catch (_) {
      state.misMesas = [];
    }
  }

  async function refreshHomeWidgets() {
    await Promise.all([loadOperational(), loadVentasHoy(), loadMisMesas()]);
    if (state.screen === "home") render();
  }

  async function shiftAction(action) {
    try {
      const data = await mpApi(`/mini-panel-operational-session/${action}?panel_type=${PANEL_TYPE}`, { method: "POST" });
      state.operational = data.operational_session || null;
      render();
    } catch (error) {
      state.error = error.message || "No se pudo actualizar el turno.";
      render();
    }
  }

  async function changePassword(currentPassword, newPassword, confirmPassword) {
    return mpApi(`/mini-panel-change-password?panel_type=${PANEL_TYPE}`, {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword, confirm_password: confirmPassword }),
    });
  }

  function cartTotal() {
    return state.cart.reduce((sum, item) => sum + Number(item.unit_price || 0) * Number(item.quantity || 0), 0);
  }

  function addOrUpdateCartLine(line, editIndex) {
    if (editIndex === null || editIndex === undefined) state.cart.push(line);
    else state.cart[editIndex] = line;
    persistCart();
  }

  function removeCartLine(index) {
    state.cart.splice(index, 1);
    persistCart();
  }

  async function submitOrder() {
    if (!state.table || !state.cart.length) return;
    state.sending = true;
    state.sendError = "";
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
            term: item.term || "",
          })),
        }),
      });
      state.lastOrderOk = `Pedido enviado a Mesa ${state.table}.`;
      state.cart = [];
      state.category = null;
      clearPersistedCart();
      resetToHome();
      refreshHomeWidgets();
    } catch (error) {
      // Cart is intentionally NOT cleared here: it stays in state and in
      // sessionStorage so the mesero can just tap "Enviar pedido" again.
      state.sendError = error.message || "No se pudo enviar el pedido. Revisa la conexión e intenta de nuevo.";
    } finally {
      state.sending = false;
      render();
    }
  }

  // ---------------------------------------------------------------------
  // Screens
  // ---------------------------------------------------------------------

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

  function screenShiftPanel() {
    const op = state.operational;
    const status = op ? op.status : "active";
    return `
      <div class="wtr-shift-panel">
        <div class="wtr-shift-times">
          <div><span>Activo</span><strong data-wtr-active-timer>${formatHMS(op ? op.active_seconds : 0)}</strong></div>
          <div><span>Pausa</span><strong data-wtr-break-timer>${formatHMS(op ? op.break_seconds : 0)}</strong></div>
        </div>
        <div class="wtr-shift-actions">
          ${status === "break"
            ? `<button class="wtr-btn" type="button" data-wtr-shift-resume>Retomar</button>`
            : `<button class="wtr-btn" type="button" data-wtr-shift-pause>Pausa</button>`}
          <button class="wtr-btn" type="button" data-wtr-shift-finish>Finalizar turno</button>
          <button class="wtr-btn" type="button" data-wtr-change-password>Cambiar contraseña</button>
          <button class="wtr-btn wtr-btn-quiet" type="button" data-wtr-logout>Cerrar sesión</button>
        </div>
      </div>`;
  }

  function screenHome() {
    const goal = state.ventasHoy || {};
    const pct = Math.max(0, Math.min(100, Number(goal.goal_progress_percent || 0)));
    const op = state.operational;
    return `
      <section class="wtr-shell wtr-home">
        <header class="wtr-home-header">
          <div class="wtr-home-titles">
            <span class="wtr-company-name">${h(state.companyName)}</span>
            <span class="wtr-user-name">${h(state.mesero)}</span>
          </div>
          <button class="wtr-shift-toggle" type="button" data-wtr-shift-toggle>
            ${h(formatHMS(op ? op.active_seconds : 0))} ${state.shiftExpanded ? "▲" : "▾"}
          </button>
        </header>
        ${state.shiftExpanded ? screenShiftPanel() : ""}
        ${state.lastOrderOk ? `<div class="wtr-toast">${h(state.lastOrderOk)}</div>` : ""}
        <div class="wtr-goal-card">
          <div class="wtr-goal-row"><span>Meta de hoy</span><strong>${h(money(goal.total_today || 0))} / ${h(money(goal.daily_goal || 0))}</strong></div>
          <div class="wtr-goal-bar"><div class="wtr-goal-fill" style="width:${pct}%"></div></div>
        </div>
        <button class="wtr-btn wtr-btn-primary wtr-btn-huge" type="button" data-wtr-new-order>Tomar pedido</button>
        <h2 class="wtr-section-title">Mis mesas</h2>
        <div class="wtr-mesas-list">
          ${state.misMesas.length ? state.misMesas.map((t) => `
            <button class="wtr-mesa-row" type="button" data-wtr-mesa="${h(t.table_number)}">
              <span>Mesa ${h(t.table_number)}</span>
              <span class="wtr-mesa-status ${t.status === "listo_para_llevar" ? "is-ready" : "is-sent"}">
                ${t.status === "listo_para_llevar" ? "Lista para llevar" : "Enviado a cocina"}
              </span>
            </button>`).join("") : `<div class="wtr-empty">Todavía no tienes mesas activas.</div>`}
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
        <div class="wtr-grid-tables">
          ${tables.map((label) => `<button class="wtr-tile" type="button" data-wtr-table="${h(label)}">${h(label)}</button>`).join("")}
        </div>
      </section>`;
  }

  function screenCategories() {
    return `
      <section class="wtr-shell">
        ${header(`Mesa ${h(state.table)}`)}
        <div class="wtr-grid-cat">
          ${state.menu.map((cat) => `
            <button class="wtr-cat-tile" type="button" data-wtr-cat="${h(cat.key)}">
              <div class="wtr-cat-img" style="background-image:url('/api/v1/companies/${encodeURIComponent(companyId)}/waiter-ordering/categories/${encodeURIComponent(cat.key)}/image')">${cat.has_image ? "" : "🍽️"}</div>
              <span>${h(cat.label)}</span>
            </button>`).join("") || `<div class="wtr-empty">Sin categorías todavía.</div>`}
        </div>
        ${cartFloatingButton()}
      </section>`;
  }

  function screenProducts() {
    const category = state.menu.find((cat) => cat.key === state.category);
    const products = category ? category.products : [];
    return `
      <section class="wtr-shell">
        ${header(category ? category.label : "Productos")}
        <div class="wtr-grid-prod">
          ${products.map((product) => `
            <button class="wtr-prod-tile" type="button" data-wtr-product="${h(product.id)}">
              ${product.has_image ? `<div class="wtr-prod-img" style="background-image:url('/api/v1/companies/${encodeURIComponent(companyId)}/waiter-ordering/products/${encodeURIComponent(product.id)}/image')"></div>` : ""}
              <span>${h(product.name)}</span>
              ${product.is_portioned
                ? `<strong>Elegir porción</strong>`
                : `<strong>${h(money(product.price))}</strong>`}
            </button>`).join("") || `<div class="wtr-empty">Sin productos en esta categoría.</div>`}
        </div>
        ${cartFloatingButton()}
      </section>`;
  }

  function cartFloatingButton() {
    if (!state.cart.length) return "";
    return `<button class="wtr-btn wtr-btn-cart" type="button" data-wtr-goto-cart>Ver pedido (${state.cart.length}) · ${h(money(cartTotal()))}</button>`;
  }

  function cartLineLabel(item) {
    const parts = [`${h(item.quantity)} x ${h(item.name)}`];
    return parts.join("");
  }

  function screenCart() {
    return `
      <section class="wtr-shell">
        ${header("Revisar pedido")}
        ${state.sendError ? `<div class="wtr-alert" style="margin:0 16px 10px">${h(state.sendError)}</div>` : ""}
        <div class="wtr-cart-list">
          ${state.cart.map((item, index) => `
            <button class="wtr-cart-row" type="button" data-wtr-edit="${index}">
              <div>
                <b>${cartLineLabel(item)}</b>
                ${item.term ? `<div class="wtr-cart-note wtr-cart-term">${h(item.term)}</div>` : ""}
                ${item.observations ? `<div class="wtr-cart-note">${h(item.observations)}</div>` : ""}
                ${item.quick_notes && item.quick_notes.length ? `<div class="wtr-cart-note">${item.quick_notes.map(h).join(" · ")}</div>` : ""}
              </div>
              <div class="wtr-cart-row-actions">
                <strong>${h(money(item.unit_price * item.quantity))}</strong>
                <span class="wtr-cart-remove" data-wtr-remove="${index}" aria-label="Quitar">✕</span>
              </div>
            </button>`).join("") || `<div class="wtr-empty">Todavía no agregaste productos.</div>`}
        </div>
        <div class="wtr-cart-total"><span>Total</span><strong>${h(money(cartTotal()))}</strong></div>
        <button class="wtr-btn wtr-btn-primary" type="button" data-wtr-send ${state.sending || !state.cart.length ? "disabled" : ""}>
          ${state.sending ? "Enviando..." : state.sendError ? "Reintentar envío" : "Confirmar y enviar"}
        </button>
      </section>`;
  }

  function header(title) {
    return `
      <header class="wtr-header">
        <button class="wtr-back" type="button" data-wtr-back aria-label="Volver">‹</button>
        <h1>${h(title)}</h1>
      </header>`;
  }

  function render() {
    let html = "";
    if (state.screen === "login") html = screenLogin();
    else if (state.screen === "home") html = screenHome();
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

    const back2 = target.closest("[data-wtr-back]");
    if (back2) { back(); return; }

    const shiftToggle = target.closest("[data-wtr-shift-toggle]");
    if (shiftToggle) { state.shiftExpanded = !state.shiftExpanded; render(); return; }

    const shiftPause = target.closest("[data-wtr-shift-pause]");
    if (shiftPause) { shiftAction("pause"); return; }

    const shiftResume = target.closest("[data-wtr-shift-resume]");
    if (shiftResume) { shiftAction("resume"); return; }

    const shiftFinish = target.closest("[data-wtr-shift-finish]");
    if (shiftFinish) {
      if (window.confirm("¿Finalizar tu turno?")) shiftAction("finish");
      return;
    }

    const changePasswordBtn = target.closest("[data-wtr-change-password]");
    if (changePasswordBtn) { openChangePasswordSheet(); return; }

    const newOrder = target.closest("[data-wtr-new-order]");
    if (newOrder) { goto("table"); return; }

    const mesaRow = target.closest("[data-wtr-mesa]");
    if (mesaRow) {
      state.table = mesaRow.getAttribute("data-wtr-mesa") || "";
      goto("categories");
      return;
    }

    const tableBtn = target.closest("[data-wtr-table]");
    if (tableBtn) {
      state.table = tableBtn.getAttribute("data-wtr-table") || "";
      goto("categories");
      return;
    }

    const catBtn = target.closest("[data-wtr-cat]");
    if (catBtn) {
      state.category = catBtn.getAttribute("data-wtr-cat") || "";
      goto("products");
      return;
    }

    const gotoCart = target.closest("[data-wtr-goto-cart]");
    if (gotoCart) { goto("cart"); return; }

    const removeBtn = target.closest("[data-wtr-remove]");
    if (removeBtn) {
      event.stopPropagation();
      removeCartLine(Number(removeBtn.getAttribute("data-wtr-remove")));
      render();
      return;
    }

    const editBtn = target.closest("[data-wtr-edit]");
    if (editBtn) {
      const index = Number(editBtn.getAttribute("data-wtr-edit"));
      const line = state.cart[index];
      if (line) {
        const category = state.menu.find((cat) => cat.key === state.category) || findCategoryForLine(line);
        openConfigureSheet({ id: line.inventory_item_id, name: line.name, price: line.unit_price }, category, line.portion_label || null, line, index);
      }
      return;
    }

    const sendBtn = target.closest("[data-wtr-send]");
    if (sendBtn && !sendBtn.disabled) { submitOrder(); return; }

    const productBtn = target.closest("[data-wtr-product]");
    if (productBtn) {
      const category = state.menu.find((cat) => cat.key === state.category);
      const product = (category ? category.products : []).find((item) => item.id === productBtn.getAttribute("data-wtr-product"));
      if (!product) return;
      if (product.is_portioned) openPortionSheet(product, category);
      else openConfigureSheet(product, category, null);
    }
  });

  function findCategoryForLine(_line) {
    return null;
  }

  function openChangePasswordSheet() {
    const sheet = document.createElement("div");
    sheet.className = "wtr-sheet-backdrop";
    sheet.innerHTML = `
      <div class="wtr-sheet">
        <h2>Cambiar contraseña</h2>
        <label>Contraseña actual<input id="wtrPwCurrent" type="password" autocomplete="current-password" /></label>
        <label>Nueva contraseña<input id="wtrPwNew" type="password" autocomplete="new-password" /></label>
        <label>Confirmar nueva contraseña<input id="wtrPwConfirm" type="password" autocomplete="new-password" /></label>
        <div class="wtr-sheet-status" id="wtrPwStatus"></div>
        <div class="wtr-sheet-actions">
          <button type="button" class="wtr-btn" data-sheet-cancel>Cancelar</button>
          <button type="button" class="wtr-btn wtr-btn-primary" data-sheet-save-pw>Guardar</button>
        </div>
      </div>`;
    document.body.appendChild(sheet);
    sheet.querySelector("[data-sheet-cancel]").addEventListener("click", () => sheet.remove());
    sheet.querySelector("[data-sheet-save-pw]").addEventListener("click", async () => {
      const statusEl = sheet.querySelector("#wtrPwStatus");
      const current = sheet.querySelector("#wtrPwCurrent").value;
      const next = sheet.querySelector("#wtrPwNew").value;
      const confirm = sheet.querySelector("#wtrPwConfirm").value;
      try {
        await changePassword(current, next, confirm);
        sheet.remove();
      } catch (error) {
        statusEl.textContent = error.message || "No se pudo cambiar la contraseña.";
      }
    });
  }

  function openPortionSheet(group, category) {
    const sheet = document.createElement("div");
    sheet.className = "wtr-sheet-backdrop";
    sheet.innerHTML = `
      <div class="wtr-sheet">
        <h2>${h(group.name)}</h2>
        <div class="wtr-portion-grid">
          ${(group.portions || []).map((portion, i) => `
            <button type="button" class="wtr-portion-btn" data-portion-index="${i}">
              <span>${h(portion.label)}</span>
              <strong>${h(money(portion.price))}</strong>
            </button>`).join("")}
        </div>
        <div class="wtr-sheet-actions">
          <button type="button" class="wtr-btn" data-sheet-cancel>Cancelar</button>
        </div>
      </div>`;
    document.body.appendChild(sheet);
    sheet.querySelector("[data-sheet-cancel]").addEventListener("click", () => sheet.remove());
    sheet.querySelectorAll("[data-portion-index]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const portion = group.portions[Number(btn.getAttribute("data-portion-index"))];
        sheet.remove();
        openConfigureSheet(
          { id: portion.inventory_item_id, name: `${group.name} ${portion.label}`, price: portion.price },
          category,
          portion.label,
        );
      });
    });
  }

  function openConfigureSheet(product, category, portionLabel, prefill, editIndex) {
    const requiresTerm = Boolean(category && category.requires_term);
    const quickOptions = (category && category.quick_notes) || [];
    const initialTermIndex = requiresTerm && prefill && prefill.term
      ? Math.max(0, TERM_STOPS.indexOf(prefill.term))
      : 0;

    const sheet = document.createElement("div");
    sheet.className = "wtr-sheet-backdrop";
    sheet.innerHTML = `
      <div class="wtr-sheet">
        <h2>${h(product.name)}</h2>
        <label>Cantidad<input id="wtrSheetQty" type="number" min="1" step="1" value="${prefill ? Number(prefill.quantity || 1) : 1}" /></label>
        ${requiresTerm ? `
          <div class="wtr-term-block">
            <span class="wtr-term-caption">Término de cocción</span>
            <input id="wtrSheetTerm" type="range" min="0" max="${TERM_STOPS.length - 1}" step="1" value="${initialTermIndex}" />
            <div class="wtr-term-labels" id="wtrTermLabels">
              ${TERM_STOPS.map((t, i) => `<span class="${i === initialTermIndex ? "is-active" : ""}" data-term-label="${i}">${h(t)}</span>`).join("")}
            </div>
          </div>` : ""}
        ${quickOptions.length ? `
          <div class="wtr-quick-notes">
            ${quickOptions.map((note, i) => `<button type="button" class="wtr-quick-note ${prefill && (prefill.quick_notes || []).includes(note) ? "is-active" : ""}" data-note-index="${i}">${h(note)}</button>`).join("")}
          </div>` : ""}
        <label>Observaciones<textarea id="wtrSheetObs" rows="2" placeholder="Ej: sin sal, bien asado...">${h(prefill ? prefill.observations || "" : "")}</textarea></label>
        <div class="wtr-sheet-actions">
          <button type="button" class="wtr-btn" data-sheet-cancel>Cancelar</button>
          <button type="button" class="wtr-btn wtr-btn-primary" data-sheet-add>${prefill ? "Guardar cambios" : "Agregar al pedido"}</button>
        </div>
      </div>`;
    document.body.appendChild(sheet);

    const selectedNotes = new Set(prefill ? prefill.quick_notes || [] : []);
    sheet.querySelectorAll("[data-note-index]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = Number(btn.getAttribute("data-note-index"));
        const note = quickOptions[idx];
        if (selectedNotes.has(note)) { selectedNotes.delete(note); btn.classList.remove("is-active"); }
        else { selectedNotes.add(note); btn.classList.add("is-active"); }
      });
    });

    const termInput = sheet.querySelector("#wtrSheetTerm");
    if (termInput) {
      termInput.addEventListener("input", () => {
        const idx = Number(termInput.value);
        sheet.querySelectorAll("[data-term-label]").forEach((el) => {
          el.classList.toggle("is-active", Number(el.getAttribute("data-term-label")) === idx);
        });
      });
    }

    sheet.querySelector("[data-sheet-cancel]").addEventListener("click", () => sheet.remove());
    sheet.querySelector("[data-sheet-add]").addEventListener("click", () => {
      const qty = Math.max(1, Number(sheet.querySelector("#wtrSheetQty").value || 1));
      const obs = String(sheet.querySelector("#wtrSheetObs").value || "");
      const term = requiresTerm ? TERM_STOPS[Number(sheet.querySelector("#wtrSheetTerm").value || 0)] : "";
      addOrUpdateCartLine(
        {
          inventory_item_id: product.id,
          name: product.name,
          unit_price: product.price,
          quantity: qty,
          portion_label: portionLabel || "",
          term,
          observations: obs,
          quick_notes: Array.from(selectedNotes),
        },
        editIndex,
      );
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
    .wtr-btn-quiet{background:transparent;border-color:rgba(255,255,255,.08);color:#a79fcf}
    .wtr-btn-huge{margin:14px 16px;height:64px;font-size:19px}
    .wtr-alert{margin-top:10px;padding:10px 12px;border-radius:12px;background:rgba(239,68,68,.16);color:#fecaca;font-size:13px;font-weight:800}
    .wtr-alert-floating{position:fixed;left:16px;right:16px;bottom:16px;z-index:50}
    .wtr-toast{margin:0 16px 10px;padding:10px 12px;border-radius:12px;background:rgba(34,197,94,.16);color:#bbf7d0;font-weight:800}
    .wtr-shell{min-height:100vh;padding-bottom:24px}
    .wtr-header{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:10px;padding:16px;background:rgba(8,7,18,.92);backdrop-filter:blur(6px);border-bottom:1px solid rgba(255,255,255,.08)}
    .wtr-header h1{flex:1;margin:0;font-size:20px}
    .wtr-back{width:44px;height:44px;border-radius:14px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#fff;font-size:20px}
    .wtr-home-header{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:18px 16px 6px}
    .wtr-home-titles{display:flex;flex-direction:column;gap:2px}
    .wtr-company-name{font-size:12px;font-weight:900;letter-spacing:.14em;text-transform:uppercase;color:#ff2d95}
    .wtr-user-name{font-size:22px;font-weight:900}
    .wtr-shift-toggle{border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#c9c3e6;border-radius:999px;padding:8px 14px;font-size:12px;font-weight:800;min-height:auto}
    .wtr-shift-panel{margin:0 16px 12px;padding:14px;border-radius:18px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.04);display:grid;gap:12px}
    .wtr-shift-times{display:flex;gap:20px}
    .wtr-shift-times div{display:flex;flex-direction:column;gap:2px;font-size:12px;color:#8f8aa8}
    .wtr-shift-times strong{font-size:18px;color:#fff}
    .wtr-shift-actions{display:grid;grid-template-columns:1fr 1fr;gap:8px}
    .wtr-shift-actions .wtr-btn{min-height:44px;font-size:13px}
    .wtr-goal-card{margin:6px 16px 4px;padding:14px;border-radius:18px;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.03)}
    .wtr-goal-row{display:flex;justify-content:space-between;font-size:13px;font-weight:800;color:#c9c3e6;margin-bottom:8px}
    .wtr-goal-bar{height:10px;border-radius:999px;background:rgba(255,255,255,.08);overflow:hidden}
    .wtr-goal-fill{height:100%;background:linear-gradient(90deg,#ff7a18,#ff2d95,#a855f7);transition:width .3s}
    .wtr-section-title{margin:18px 16px 8px;font-size:14px;color:#8f8aa8;text-transform:uppercase;letter-spacing:.1em}
    .wtr-mesas-list{display:grid;gap:8px;padding:0 16px}
    .wtr-mesa-row{display:flex;justify-content:space-between;align-items:center;padding:14px 16px;border-radius:16px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.04);color:#fff;font-weight:800}
    .wtr-mesa-status{font-size:12px;font-weight:900;padding:4px 10px;border-radius:999px}
    .wtr-mesa-status.is-sent{background:rgba(250,204,21,.18);color:#fde68a}
    .wtr-mesa-status.is-ready{background:rgba(34,197,94,.18);color:#bbf7d0}
    .wtr-grid-tables{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:12px;padding:16px}
    .wtr-tile{min-height:72px;border-radius:18px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#fff;font-size:16px;font-weight:900}
    .wtr-grid-cat{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:14px;padding:16px}
    .wtr-cat-tile{display:grid;gap:8px;border-radius:20px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.05);color:#fff;padding:0 0 12px;overflow:hidden}
    .wtr-cat-img{height:100px;display:grid;place-items:center;font-size:34px;background-size:cover;background-position:center;background-color:rgba(255,255,255,.06)}
    .wtr-cat-tile span{font-size:15px;font-weight:900}
    .wtr-grid-prod{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;padding:16px}
    .wtr-prod-tile{min-height:76px;display:grid;gap:6px;align-content:center;border-radius:18px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.05);color:#fff;padding:12px;text-align:left;overflow:hidden}
    .wtr-prod-img{height:70px;margin:-12px -12px 4px;background-size:cover;background-position:center}
    .wtr-prod-tile strong{color:#ffd166}
    .wtr-btn-cart{position:fixed;left:16px;right:16px;bottom:16px}
    .wtr-cart-list{display:grid;gap:10px;padding:16px}
    .wtr-cart-row{display:flex;justify-content:space-between;gap:10px;padding:12px;border-radius:16px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.04);color:#fff;text-align:left;width:100%}
    .wtr-cart-note{font-size:12px;color:#ffb3d9}
    .wtr-cart-term{color:#ffd166;font-weight:800}
    .wtr-cart-row-actions{display:flex;align-items:center;gap:10px}
    .wtr-cart-remove{width:32px;height:32px;border-radius:10px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#fff;display:grid;place-items:center}
    .wtr-cart-total{display:flex;justify-content:space-between;padding:0 16px;font-size:18px;font-weight:900;margin-bottom:14px}
    .wtr-shell > .wtr-btn-primary{margin:0 16px;width:calc(100% - 32px)}
    .wtr-empty{padding:20px;color:#8f8aa8;text-align:center}
    .wtr-sheet-backdrop{position:fixed;inset:0;background:rgba(0,0,0,.6);display:grid;align-items:end;z-index:60}
    .wtr-sheet{background:#120e20;border-radius:24px 24px 0 0;padding:22px;display:grid;gap:14px;max-height:90vh;overflow:auto}
    .wtr-sheet h2{margin:0}
    .wtr-sheet label{display:grid;gap:6px;font-size:13px;font-weight:800;color:#c9c3e6}
    .wtr-sheet input,.wtr-sheet textarea{padding:12px;border-radius:12px;border:1px solid rgba(255,255,255,.16);background:rgba(3,7,18,.6);color:#fff;font:inherit}
    .wtr-sheet-status{color:#fecaca;font-size:13px;font-weight:800;min-height:16px}
    .wtr-quick-notes{display:flex;flex-wrap:wrap;gap:8px}
    .wtr-quick-note{padding:8px 12px;border-radius:999px;border:1px solid rgba(255,255,255,.18);background:rgba(255,255,255,.05);color:#fff;font-size:12px;font-weight:800}
    .wtr-quick-note.is-active{background:linear-gradient(135deg,#ff7a18,#ff2d95);border-color:transparent}
    .wtr-term-block{display:grid;gap:8px}
    .wtr-term-caption{font-size:13px;font-weight:800;color:#c9c3e6}
    .wtr-term-block input[type=range]{width:100%}
    .wtr-term-labels{display:flex;justify-content:space-between;font-size:11px;color:#8f8aa8;font-weight:800}
    .wtr-term-labels span.is-active{color:#ffd166}
    .wtr-sheet-actions{display:flex;gap:10px}
    .wtr-sheet-actions .wtr-btn{flex:1}
    .wtr-portion-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:10px}
    .wtr-portion-btn{display:grid;gap:4px;padding:14px;border-radius:16px;border:1px solid rgba(255,255,255,.16);background:rgba(255,255,255,.05);color:#fff;font-weight:900}
    .wtr-portion-btn strong{color:#ffd166}
  `;
  document.head.appendChild(style);

  let homeRefreshHandle = null;
  function startHomeRefresh() {
    if (homeRefreshHandle) return;
    homeRefreshHandle = window.setInterval(() => {
      if (state.screen === "home") refreshHomeWidgets();
    }, 20000);
  }

  if (!companyId) {
    root.innerHTML = `<section style="min-height:100vh;display:grid;place-items:center;background:#080712;color:#fff"><p>Falta company_id en el enlace.</p></section>`;
  } else if (token()) {
    restoreCart();
    enterHome().then(render);
    render();
    startHomeRefresh();
  } else {
    render();
  }
})();
