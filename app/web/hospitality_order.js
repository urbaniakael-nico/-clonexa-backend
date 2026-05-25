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
    campaign: null,
    participant: null,
    campaignDismissed: false,
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
      .qr-campaign{
        display:grid;
        grid-template-columns:minmax(0,1fr) minmax(240px,360px);
        gap:12px;
        background:linear-gradient(145deg,rgba(255,255,255,.12),rgba(255,255,255,.04)),var(--qr-card);
        border:1px solid var(--qr-line);
        border-radius:22px;
        padding:16px;
        box-shadow:0 18px 54px rgba(0,0,0,.24);
      }
      .qr-campaign h2{margin:0 0 8px;font-size:26px;line-height:1.05}
      .qr-campaign-main{display:grid;gap:10px}
      .qr-campaign-prize,.qr-campaign-clock,.qr-campaign-ok{
        display:flex;
        justify-content:space-between;
        gap:12px;
        align-items:center;
        padding:10px 12px;
        border-radius:15px;
        background:rgba(3,7,18,.34);
        border:1px solid rgba(255,255,255,.10);
        font-weight:1000;
      }
      .qr-campaign-prize strong,.qr-campaign-clock strong{color:var(--qr-secondary);font-size:20px}
      .qr-campaign-join{display:grid;grid-template-columns:1fr minmax(150px,1fr) auto auto;gap:8px;align-items:end}
      .qr-campaign-join strong{display:block}
      .qr-campaign-join span{display:block;color:var(--qr-muted);font-size:11px;font-weight:900;text-transform:uppercase;letter-spacing:.08em;margin-top:4px}
      .qr-campaign-join input{width:100%;border:1px solid var(--qr-line);border-radius:14px;background:rgba(2,6,23,.58);color:var(--qr-text);padding:12px;font-weight:900;outline:none}
      .qr-campaign-rank{display:grid;gap:8px;align-content:start}
      .qr-rank-row{display:grid;grid-template-columns:28px 1fr;gap:9px;align-items:center;background:rgba(3,7,18,.30);border:1px solid rgba(255,255,255,.10);border-radius:14px;padding:9px}
      .qr-rank-row span{font-weight:1000;color:var(--qr-secondary)}
      .qr-rank-row strong{display:block}
      .qr-rank-row small{display:block;color:var(--qr-muted);font-size:11px;font-weight:850}
      .qr-rank-row i{display:block;height:7px;border-radius:999px;background:rgba(255,255,255,.10);overflow:hidden;margin-top:6px}
      .qr-rank-row b{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,var(--qr-primary),var(--qr-secondary))}
      @media(max-width:860px){
        .qr-hero{grid-template-columns:1fr}
        .qr-layout{grid-template-columns:1fr}
        .qr-menu-head{grid-template-columns:1fr}
        .qr-campaign,.qr-campaign-join{grid-template-columns:1fr}
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

  function countdown(value = 0) {
    const total = Math.max(0, Number(value || 0));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = Math.floor(total % 60);
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }

  function campaignProducts(row = {}) {
    const products = Array.isArray(row.products) ? row.products : [];
    if (!products.length) return "";
    return products.slice(0, 2).map((item) => {
      const qty = Number(item.quantity || 0);
      const qtyLabel = Number.isInteger(qty) ? String(qty) : qty.toFixed(1);
      return `${item.name || "Producto"} x ${qtyLabel}`;
    }).join(" · ");
  }

  function campaignHtml() {
    const campaign = state.campaign;
    if (!campaign) return "";
    const rows = Array.isArray(campaign.leaderboard) ? campaign.leaderboard : [];
    const open = campaign.registration_open === true;
    const participant = state.participant;
    const winner = campaign.winner || null;
    const tournamentPhase = campaign.tournament_phase || "open";
    const tournamentLabel = tournamentPhase === "closed" ? "Torneo finalizado" : tournamentPhase === "scheduled" ? "Torneo inicia en" : "Torneo cierra en";
    const form = open && !participant && !state.campaignDismissed ? `
      <div class="qr-campaign-join">
        <div>
          <strong>Te animas a participar?</strong>
          <span>Nombre del equipo</span>
        </div>
        <input id="qrTeam024Z" placeholder="Ej: Equipo Mesa 1" value="${h(document.getElementById("qrTeam024Z")?.value || "")}">
        <button class="qr-btn" type="button" data-campaign-join>Si, participar</button>
        <button class="qr-btn secondary" type="button" data-campaign-dismiss>No participar</button>
      </div>
    ` : "";
    const joined = participant ? `<div class="qr-campaign-ok">Participando como <strong>${h(participant.team_name)}</strong></div>` : "";
    const closedSignup = !open && !participant && !winner ? `<div class="qr-campaign-ok">Inscripcion cerrada para esta ronda.</div>` : "";
    const winnerHtml = winner ? `<div class="qr-campaign-ok">Equipo ganador: <strong>${h(winner.team_name)}</strong> · ${h(winner.table_number)} · ${h(money(winner.total || 0))}</div>` : "";
    return `
      <section class="qr-campaign">
        <div class="qr-campaign-main">
          <p class="qr-eyebrow">Sorteo activo</p>
          <h2>${h(campaign.title || "Reto de consumo")}</h2>
          <p class="qr-muted">${h(campaign.description || "La mesa con mas consumo dentro del tiempo gana el premio.")}</p>
          <div class="qr-campaign-prize"><span>Premio</span><strong>${h(campaign.prize || "Por definir")}</strong></div>
          <div class="qr-campaign-clock"><span>Inscripcion cierra en</span><strong id="qrSignupClock025A">${h(countdown(campaign.signup_seconds_left))}</strong></div>
          <div class="qr-campaign-clock"><span>${h(tournamentLabel)}</span><strong id="qrTournamentClock025A">${h(countdown(campaign.tournament_seconds_left))}</strong></div>
          ${joined}
          ${closedSignup}
          ${winnerHtml}
          ${form}
        </div>
        <div class="qr-campaign-rank">
          ${rows.length ? rows.slice(0, 5).map((row) => `
            <div class="qr-rank-row">
              <span>${h(row.rank)}</span>
              <div>
                <strong>${h(row.team_name)}</strong>
                <small>${h(row.table_number)} - ${h(money(row.total || 0))}</small>
                ${campaignProducts(row) ? `<small>${h(campaignProducts(row))}</small>` : ""}
                <i><b style="width:${Math.min(100, Math.max(0, Number(row.percent || 0)))}%"></b></i>
              </div>
            </div>
          `).join("") : `<div class="qr-empty">Se el primero en participar.</div>`}
        </div>
      </section>
    `;
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
        ${campaignHtml()}

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
      await refreshCampaign().catch(() => {});
      state.message = `Tu pedido fue recibido. El barman ya lo tiene en pantalla: ${response.order?.order_number || "OK"}.`;
      state.error = "";
      render();
    } catch (error) {
      state.error = error.message || "No se pudo enviar el pedido.";
      state.message = "";
      render();
    }
  }

  async function refreshCampaign() {
    const campaign = await api(`/hospitality/companies/${encodeURIComponent(state.companyId)}/loyalty-campaigns/active?table=${encodeURIComponent(state.table)}`);
    state.campaign = campaign.campaign || null;
    state.participant = campaign.participant || null;
    return campaign;
  }

  async function load() {
    try {
      const [company, branding, inventory, campaign] = await Promise.all([
        api(`/companies/${encodeURIComponent(state.companyId)}`),
        api(`/companies/${encodeURIComponent(state.companyId)}/branding`).catch(() => ({})),
        api(`/hospitality/companies/${encodeURIComponent(state.companyId)}/inventory-lite?limit=300`),
        api(`/hospitality/companies/${encodeURIComponent(state.companyId)}/loyalty-campaigns/active?table=${encodeURIComponent(state.table)}`).catch(() => ({})),
      ]);
      state.company = company || {};
      state.branding = branding.branding || branding || {};
      state.inventory = Array.isArray(inventory.inventory) ? inventory.inventory : [];
      state.campaign = campaign.campaign || null;
      state.participant = campaign.participant || null;
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

    if (target.closest("[data-campaign-dismiss]")) {
      state.campaignDismissed = true;
      render();
      return;
    }
    if (target.closest("[data-campaign-join]")) {
      joinCampaign();
      return;
    }
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

  async function joinCampaign() {
    if (!state.campaign?.id) return;
    try {
      state.error = "";
      const teamName = document.getElementById("qrTeam024Z")?.value || `Equipo ${state.table}`;
      const data = await api(`/hospitality/companies/${encodeURIComponent(state.companyId)}/loyalty-campaigns/${encodeURIComponent(state.campaign.id)}/participants`, {
        method: "POST",
        body: JSON.stringify({ table: state.table, team_name: teamName, accepted: true }),
      });
      state.campaign = data.campaign || state.campaign;
      state.participant = data.participant || null;
      state.message = "Inscripcion recibida. Tu mesa ya participa en el sorteo.";
      render();
    } catch (error) {
      state.error = error.message || "No se pudo inscribir la mesa.";
      render();
    }
  }

  setInterval(() => {
    if (!state.campaign) return;
    if (Number.isFinite(Number(state.campaign.signup_seconds_left))) {
      state.campaign.signup_seconds_left = Math.max(0, Number(state.campaign.signup_seconds_left || 0) - 1);
      const signupClock = document.getElementById("qrSignupClock025A");
      if (signupClock) signupClock.textContent = countdown(state.campaign.signup_seconds_left);
      if (state.campaign.signup_seconds_left === 0 && state.campaign.registration_open) {
        state.campaign.registration_open = false;
        render();
      }
    }
    if (Number.isFinite(Number(state.campaign.tournament_seconds_left))) {
      state.campaign.tournament_seconds_left = Math.max(0, Number(state.campaign.tournament_seconds_left || 0) - 1);
      const tournamentClock = document.getElementById("qrTournamentClock025A");
      if (tournamentClock) tournamentClock.textContent = countdown(state.campaign.tournament_seconds_left);
      if (state.campaign.tournament_seconds_left === 0 && !state.campaign._endRefreshDone) {
        state.campaign._endRefreshDone = true;
        refreshCampaign().then(() => render()).catch(() => {});
      }
    }
  }, 1000);

  render();
  load();
})();
