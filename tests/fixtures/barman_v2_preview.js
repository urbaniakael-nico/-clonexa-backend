// Vista previa del Panel Barman v2 (barman_music_layout) con datos de ejemplo:
// 12 mesas configuradas, 10 activas (Mesa 3 y Mesa 8 con pedido nuevo), 2 libres
// y 9 cuentas de barra. Parámetros: on=1 enciende el interruptor; sc=escenario
// (layout, add, panel, live, filters, tablet, song, off); songs=N canciones.
// Al terminar deja en #layout las medidas. No guarda capturas.
(() => {
  const P = new URLSearchParams(location.search);
  const CID = P.get("company_id");
  const on = P.get("on") === "1";
  const sc = P.get("sc") || "layout";
  const nSongs = Number(P.get("songs") || 6);
  const branding = { mode: "dark", theme_mode: "dark", font_family: "Poppins", primary_color: "#6b5d00", text_color: "#ffffff", secondary_color: "#aea924",
    background_color: "#14110a", gradient_from: "#14110a", gradient_to: "#2a2410", background_mode: "gradient", card_style: "neon_border", visual_preset: "classic_office" };
  const json = (b, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
  const real = window.fetch.bind(window);
  try {
    localStorage.setItem("clonexa_access_token", "preview");
    if (P.get("visual") === "off") localStorage.setItem(`clonexa_hospitality_alerts_${CID}_visual`, "disabled");
  } catch (_) {}
  const at = (min) => new Date(Date.now() - min * 60000).toISOString();
  const inventory = [
    { id: "i1", name: "Águila", sku: "AG330", category: "Cerveza", unit_price: 6000, stock: 80 },
    { id: "i2", name: "Poker", sku: "PK330", category: "Cerveza", unit_price: 5500, stock: 60 },
    { id: "i3", name: "Aguardiente Antioqueño media", sku: "AA375", category: "Licores", unit_price: 48000, stock: 12 },
  ];
  const line = (inv, quantity) => ({ inventory_item_id: inv.id, product_id: inv.id, sku: inv.sku, name: inv.name, quantity, unit_price: inv.unit_price, subtotal: inv.unit_price * quantity });
  const orders = [];
  let seq = 0;
  const addOrder = (table, status, items, minutesAgo, extra = {}) => {
    seq += 1;
    const total = items.reduce((s, it) => s + it.subtotal, 0);
    const order = { id: extra.id || `o${seq}`, order_number: `H-${1000 + seq}`, table_number: table, table_key: table.toLowerCase(), source: "qr", status, total, items,
      created_at: at(minutesAgo), updated_at: at(minutesAgo), customer_name: "Cliente", people: [{ id: `p${seq}`, name: "Cliente", total, items }], metadata: {}, ...extra };
    orders.push(order);
    return order;
  };
  // Mesas 1..10 activas; la 5 tiene el pedido "a5" que recibe el "+".
  for (let n = 1; n <= 10; n += 1) {
    if (n === 3 || n === 8) {
      addOrder(`Mesa ${n}`, "pendiente", [line(inventory[0], 2)], 3 + n, { id: `a${n}` });
    } else {
      addOrder(`Mesa ${n}`, "entregado", [line(inventory[n % 2], n), line(inventory[2], 1)], 20 + n * 7, { id: `a${n}` });
    }
  }
  const barNames = ["José Barra", "Laura", "Andrés", "Camila", "Barra 5", "Pipe", "Mónica", "Juan Pablo", "Sofía"];
  barNames.forEach((name, i) => {
    seq += 1;
    const items = [line(inventory[i % 2], i + 1)];
    orders.push({ id: `b${i + 1}`, order_number: `B-${200 + i}`, table_number: "Barra", table_key: "barra", source: "bar_account", type: "bar_account", status: "entregado",
      customer_name: name, total: items.reduce((s, it) => s + it.subtotal, 0), items, created_at: at(90 - i * 5), updated_at: at(90 - i * 5), people: [], metadata: {} });
  });
  for (let i = 0; i < 6; i += 1) {
    orders.push({ id: `c${i}`, order_number: `H-30${i}`, table_number: `Mesa ${20 + i}`, table_key: `mesa ${20 + i}`, source: "qr", status: "cerrado", payment_method: "cash",
      total: 10000 * (i + 1), items: [], created_at: at(300 - i), updated_at: at(10 + i * 10), closed_at: at(10 + i * 10), people: [], metadata: {} });
  }
  const songs = Array.from({ length: nSongs }, (_, i) => ({ id: `s${i}`, table_number: `Mesa ${(i % 4) + 1}`, song: `Canción ${i} - Artista`, status: "pendiente", created_at: at(60 - i), updated_at: at(60 - i) }));
  window.__calls = [];
  const recalc = (order) => {
    order.total = order.items.reduce((s, it) => s + (it.subtotal || it.quantity * it.unit_price), 0);
    order.updated_at = new Date().toISOString();
    if (order.people && order.people[0]) { order.people[0].items = order.items; order.people[0].total = order.total; }
  };
  // Llegadas en vivo (escenarios live y song).
  window.__arrive = () => {
    addOrder("Mesa 2", "pendiente", [line(inventory[1], 3)], 0, { id: "live1" });
  };
  window.__song = () => {
    songs.push({ id: "s-new", table_number: "Mesa 9", song: "Canción nueva - Artista", status: "pendiente", created_at: new Date().toISOString(), updated_at: new Date().toISOString() });
  };

  window.fetch = async (url, opts = {}) => {
    const u = String(url);
    if (!u.startsWith("/api/v1")) return real(url, opts);
    const p = u.slice(7).split("?")[0];
    const method = String(opts.method || "GET").toUpperCase();
    const body = opts.body ? JSON.parse(opts.body) : null;
    if (method !== "GET") window.__calls.push({ method, path: p.replace(`/hospitality/companies/${CID}`, ""), body });
    if (p.endsWith("/locale")) return json({ currency: "COP", timezone: "America/Bogota", language: "es", decimals: 0 });
    if (p === `/companies/${CID}`) return json({ id: CID, name: on ? "The Time Machine" : "Otra empresa", slug: "ttm", status: "active" });
    if (p === `/companies/${CID}/experience`) return json({ company_id: CID, branding });
    if (p === `/companies/${CID}/modules`) {
      const settings = { qr_config: { orders_board: "mesas", table_count: 12 }, qr_bar_menu: true };
      if (on) settings.barman_music_layout = true;
      return json([{ id: "cm1", company_id: CID, module_id: "m1", enabled: true, settings: {}, module: { code: "orders", name: "Pedidos" } },
        { id: "cm2", company_id: CID, module_id: "m2", enabled: true, settings, module: { code: "qr", name: "QR" } }]);
    }
    if (p.endsWith("/closed-tables-summary")) {
      const live = orders.filter((o) => o.status === "cerrado" && !o.archived_at);
      return json({ ok: true, tables: new Set(live.map((o) => o.table_key)).size, orders: live.length, total: live.reduce((s, o) => s + o.total, 0) });
    }
    let m = /\/orders\/([^/]+)\/items$/.exec(p);
    if (m && method === "POST") {
      const order = orders.find((o) => o.id === m[1]);
      order.items = order.items.concat(body.items.map((it) => ({ ...it, subtotal: it.quantity * it.unit_price })));
      recalc(order);
      return json({ ok: true, order });
    }
    m = /\/bar-accounts\/([^/]+)\/items$/.exec(p);
    if (m && method === "POST") {
      const order = orders.find((o) => o.id === m[1]);
      order.items = order.items.concat(body.items.map((it) => ({ ...it, subtotal: it.quantity * it.unit_price })));
      recalc(order);
      return json({ ok: true, order });
    }
    m = /\/orders\/([^/]+)\/close-table$/.exec(p);
    if (m && method === "POST") {
      const order = orders.find((o) => o.id === m[1]);
      order.status = "cerrado";
      order.payment_method = body.payment_method;
      order.closed_at = new Date().toISOString();
      order.updated_at = order.closed_at;
      return json({ ok: true, order });
    }
    m = /\/orders\/([^/]+)\/status$/.exec(p);
    if (m && method === "PATCH") {
      const order = orders.find((o) => o.id === m[1]);
      if (order) { order.status = body.status; order.updated_at = new Date().toISOString(); }
      return json({ ok: true, order });
    }
    if (p.endsWith("/orders") && method === "POST") {
      const inv = inventory.find((i) => i.id === body.items[0].product_id) || inventory[0];
      const order = addOrder(body.table, "pendiente", [line(inv, body.items[0].quantity)], 0, { id: `new${seq + 1}`, source: body.source });
      return json({ ok: true, order });
    }
    const archive = /\/song-requests\/([^/]+)\/archive$/.exec(p);
    if (archive) {
      const i = songs.findIndex((s) => s.id === archive[1]);
      if (i >= 0) songs.splice(i, 1);
      return json({ ok: true });
    }
    if (p.endsWith("/orders")) return json({ ok: true, orders: orders.filter((o) => !o.archived_at), summary: {}, song_requests: songs });
    if (p.endsWith("/qr-tables")) return json({ ok: true, tables: Array.from({ length: 12 }, (_, i) => ({ label: `Mesa ${i + 1}`, table_key: `mesa ${i + 1}` })) });
    if (p.endsWith("/inventory-lite")) return json({ ok: true, inventory });
    if (p.includes("/qr-guests/") || p.includes("/loyalty-games/") || p.includes("/loyalty-retos/")) return json({ detail: "x" }, 404);
    return json({});
  };

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const q = (s) => document.querySelector(s);
  const qa = (s) => Array.from(document.querySelectorAll(s));
  const rr = (el) => {
    if (!el) return null;
    const b = el.getBoundingClientRect();
    return { top: Math.round(b.top), bottom: Math.round(b.bottom), left: Math.round(b.left), right: Math.round(b.right), w: Math.round(b.width), h: Math.round(b.height) };
  };
  const visible = (el) => Boolean(el) && getComputedStyle(el).display !== "none" && el.getBoundingClientRect().height > 0;
  const cardsOf = (group) => qa(`[data-hsp-v2-group="${group}"] .hsp-v2-card-070a`);
  const names = (group) => cardsOf(group).map((c) => c.querySelector(".hsp-v2-name-070a").textContent);
  const totalOf = (label) => {
    const card = qa(".hsp-v2-card-070a").find((c) => c.querySelector(".hsp-v2-name-070a").textContent === label);
    return card ? card.querySelector(".hsp-v2-total-070a").textContent : null;
  };
  const rows = (cards) => {
    const tops = [...new Set(cards.map((c) => Math.round(c.getBoundingClientRect().top)))].sort((a, b) => a - b);
    return tops.map((t) => cards.filter((c) => Math.round(c.getBoundingClientRect().top) === t).length);
  };
  const type = (el, value) => {
    el.focus();
    el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
  };
  const key = (el, k) => el.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true }));
  const choose = (select, value) => {
    select.value = value;
    select.dispatchEvent(new Event("change", { bubbles: true }));
  };
  const calls = () => window.__calls.map((c) => `${c.method} ${c.path}`);
  const plus = (ref) => q(`[data-hsp-v2-plus="${ref}"]`);
  const open = (ref) => q(`[data-hsp-v2-open="${ref}"]`);

  async function layout() {
    const out = {};
    const live = q(".hsp-v2-live-070a");
    const queue = q("#hspV2Music070A");
    const list = q("#hspSongRequests031C");
    out.title = q("#hspV2Title070A")?.textContent || "";
    out.filters = qa("[data-hsp-v2-filter]").map((b) => b.textContent.replace(/\s+/g, " ").trim());
    out.tables = names("tables");
    out.bars = names("bar");
    out.free = qa("[data-hsp-v2-group=free] button").map((b) => b.textContent.trim());
    out.table_rows = rows(cardsOf("tables"));
    out.bar_rows = rows(cardsOf("bar"));
    out.heights = [...new Set(qa(".hsp-v2-card-070a").map((c) => Math.round(c.getBoundingClientRect().height)))];
    out.first_badge = cardsOf("tables")[0]?.querySelector(".hsp-v2-badge-070a").textContent;
    out.mesa5 = cardsOf("tables").find((c) => c.textContent.includes("Mesa 5"))?.querySelector(".hsp-v2-meta-070a").textContent.replace(/\s+/g, " ").trim();
    out.page_overflow = document.documentElement.scrollWidth > document.documentElement.clientWidth + 1;
    out.clipped = qa(".hsp-v2-card-070a *").filter((el) => {
      if (el.matches(".hsp-v2-name-070a")) return false; // el nombre largo se corta con "…" a propósito
      return el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).overflow !== "visible";
    }).map((el) => el.className).slice(0, 5);
    out.total_overflow = qa(".hsp-v2-total-070a").filter((el) => el.getBoundingClientRect().right > el.closest(".hsp-v2-card-070a").getBoundingClientRect().right + 1).length;
    out.small_buttons = qa("#hspV2Grid070A button").filter(visible).filter((b) => {
      const box = b.getBoundingClientRect();
      return box.height < 40 || box.width < 40;
    }).map((b) => `${b.className}:${Math.round(b.getBoundingClientRect().height)}`).slice(0, 6);
    out.music_btn_visible = visible(q("[data-hsp-v2-music]"));
    out.queue_visible = visible(queue);
    out.queue_before = rr(queue);
    out.live = rr(live);
    out.list_scrolls = list.scrollHeight > list.clientHeight + 1;
    out.song_count = q("#hspSongCount031C")?.textContent;
    out.music_count = q("#hspV2MusicCount070A")?.textContent;
    window.scrollTo(0, document.documentElement.scrollHeight);
    await sleep(200);
    out.scrolled = window.scrollY;
    out.queue_after = rr(queue);
    out.fold_after = rr(q("#hspClosedFold069A"));
    out.vh = window.innerHeight;
    out.fold_title = q("#hspClosedTitle069A")?.textContent || "";
    out.copy_buttons = [...new Set(qa("#hspSongRequests031C button").map((b) => b.textContent.trim()))];
    window.scrollTo(0, 0);
    return out;
  }

  async function addFlow() {
    const out = {};
    // "+" en Mesa 5: Enter agrega 2 × Águila.
    out.before = totalOf("Mesa 5");
    plus("table:mesa_5").click();
    await sleep(50);
    const pop = q("#hspV2Pop070A");
    out.pop_open = visible(pop);
    out.pop_focus = document.activeElement?.hasAttribute("data-hsp-v2-pop-search") || false;
    const pr = rr(pop);
    const ar = rr(plus("table:mesa_5"));
    out.pop_near = Math.abs(pr.top - ar.bottom) <= 12 || Math.abs(pr.bottom - ar.top) <= 12;
    out.qty_default = pop.querySelector("[data-hsp-v2-pop-qty]").value;
    pop.querySelector("[data-hsp-v2-pop-qty]").value = "2";
    type(pop.querySelector("[data-hsp-v2-pop-search]"), "aguila");
    key(pop.querySelector("[data-hsp-v2-pop-search]"), "Enter");
    await sleep(600);
    out.calls_add = calls();
    out.add_body = window.__calls[0]?.body;
    out.pop_closed = !q("#hspV2Pop070A");
    out.toast = q("#hspV2Toast070A")?.textContent || "";
    out.after = totalOf("Mesa 5");
    // Esc cancela sin enviar nada.
    window.__calls.length = 0;
    plus("table:mesa_6").click();
    await sleep(50);
    type(q("[data-hsp-v2-pop-search]"), "poker");
    key(q("[data-hsp-v2-pop-search]"), "Escape");
    await sleep(100);
    out.esc_closed = !q("#hspV2Pop070A");
    out.esc_calls = calls();
    // Producto que no existe: se queda abierto con el error.
    plus("table:mesa_6").click();
    await sleep(50);
    type(q("[data-hsp-v2-pop-search]"), "zzzz");
    q("[data-hsp-v2-pop-add]").click();
    await sleep(100);
    out.bad_open = Boolean(q("#hspV2Pop070A"));
    out.bad_msg = q("[data-hsp-v2-pop-msg]")?.textContent || "";
    out.bad_calls = calls();
    q("[data-hsp-v2-pop-cancel]").click();
    await sleep(50);
    // "+" en una cuenta de barra.
    const bar = cardsOf("bar").find((c) => c.textContent.includes("Laura"));
    const barRef = bar.getAttribute("data-hsp-v2-card");
    out.bar_before = totalOf("Laura");
    plus(barRef).click();
    await sleep(50);
    type(q("[data-hsp-v2-pop-search]"), "Águila");
    q("[data-hsp-v2-pop-add]").click();
    await sleep(600);
    out.bar_calls = calls();
    out.bar_after = totalOf("Laura");
    out.bar_toast = q("#hspV2Toast070A")?.textContent || "";
    // Mesa con solo pedido nuevo (Mesa 3): entra como pedido de mesa entregado, igual que hoy.
    window.__calls.length = 0;
    plus("table:mesa_3").click();
    await sleep(50);
    type(q("[data-hsp-v2-pop-search]"), "poker");
    key(q("[data-hsp-v2-pop-search]"), "Enter");
    await sleep(600);
    out.pending_calls = calls();
    out.pending_body = window.__calls[0]?.body;
    return out;
  }

  async function panelFlow() {
    const out = {};
    open("table:mesa_5").click();
    await sleep(100);
    const panel = q("#hspV2Panel070A");
    out.panel_open = visible(panel);
    out.panel_title = q("#hspV2PanelTitle070A")?.textContent;
    out.panel_kind = q("#hspV2PanelKind070A")?.textContent;
    out.panel = rr(panel);
    out.queue = rr(q("#hspV2Music070A"));
    out.panel_lines = qa("#hspV2PanelBody070A .hsp-table-line-034b").map((l) => l.textContent.replace(/\s+/g, " ").trim());
    out.panel_has_add = Boolean(panel.querySelector("[data-hsp-quick-add-search]"));
    const close = panel.querySelector("[data-hsp-close-ids]");
    out.close_disabled = close.disabled;
    // Un solo panel: abrir otra mesa lo reemplaza.
    open("table:mesa_6").click();
    await sleep(100);
    out.panels = qa(".hsp-v2-panel-070a").length;
    out.replaced_title = q("#hspV2PanelTitle070A")?.textContent;
    open("table:mesa_5").click();
    await sleep(100);
    // Agregar desde el panel (el buscador de siempre de la tarjeta).
    const add = q("#hspV2PanelBody070A [data-hsp-quick-add-search]");
    type(add, "poker");
    q("#hspV2PanelBody070A [data-hsp-quick-add]").click();
    await sleep(700);
    out.panel_add_calls = calls();
    out.panel_after_add = rr(q("#hspV2Panel070A")) ? q("#hspV2PanelTitle070A").textContent : null;
    // Pago obligatorio y cierre.
    window.__calls.length = 0;
    const select = q("#hspV2PanelBody070A [data-hsp-close-payment]");
    choose(select, "cash");
    out.close_enabled = !q("#hspV2PanelBody070A [data-hsp-close-ids]").disabled;
    out.cash_visible = !q("#hspV2PanelBody070A [data-hsp-close-cash-wrap]").hidden;
    q("#hspV2PanelBody070A [data-hsp-close-ids]").click();
    await sleep(800);
    out.close_calls = calls();
    out.close_body = window.__calls[0]?.body;
    out.panel_gone = !q("#hspV2Panel070A");
    out.close_toast = q("#hspV2Toast070A")?.textContent || "";
    out.tables_after = names("tables");
    // Cuenta de barra: sin pago no cierra; con pago, sí.
    window.__calls.length = 0;
    const bar = cardsOf("bar").find((c) => c.textContent.includes("Andrés"));
    const ref = bar.getAttribute("data-hsp-v2-card");
    open(ref).click();
    await sleep(100);
    out.bar_title = q("#hspV2PanelTitle070A")?.textContent;
    out.bar_kind = q("#hspV2PanelKind070A")?.textContent;
    q("#hspV2PanelBody070A [data-hsp-bar-close]").click();
    await sleep(100);
    out.bar_no_pay_calls = calls();
    out.bar_no_pay_msg = q("#hspV2PanelMsg070A")?.textContent || "";
    window.confirm = () => true;
    choose(q("#hspV2PanelBody070A [data-hsp-bar-payment]"), "transfer");
    q("#hspV2PanelBody070A [data-hsp-bar-close]").click();
    await sleep(800);
    out.bar_close_calls = calls();
    out.bar_close_body = window.__calls[0]?.body;
    out.bar_panel_gone = !q("#hspV2Panel070A");
    out.bars_after = names("bar");
    // ✕ y Esc cierran.
    open("table:mesa_6").click();
    await sleep(100);
    q("[data-hsp-v2-panel-close]").click();
    await sleep(50);
    out.x_closed = !q("#hspV2Panel070A");
    open("table:mesa_6").click();
    await sleep(100);
    key(document.activeElement || document.body, "Escape");
    await sleep(50);
    out.esc_closed = !q("#hspV2Panel070A");
    // Mesa libre: abre su panel para cargar el primer producto.
    window.__calls.length = 0;
    q('[data-hsp-v2-group=free] [data-hsp-v2-open="table:mesa_11"]').click();
    await sleep(100);
    out.free_title = q("#hspV2PanelTitle070A")?.textContent;
    out.free_kind = q("#hspV2PanelKind070A")?.textContent;
    type(q("#hspV2PanelBody070A [data-hsp-quick-add-search]"), "aguila");
    q("#hspV2PanelBody070A [data-hsp-quick-add]").click();
    await sleep(900);
    out.free_calls = calls();
    out.free_body = window.__calls[0]?.body;
    out.free_panel_kind = q("#hspV2PanelKind070A")?.textContent || null;
    out.free_now_active = names("tables").includes("Mesa 11");
    return out;
  }

  async function liveFlow() {
    const out = {};
    open("table:mesa_7").click();
    await sleep(100);
    const input = q("#hspV2PanelBody070A [data-hsp-quick-add-search]");
    type(input, "pok");
    window.__arrive();
    await sleep(7000);
    out.open_while_typing = Boolean(q("#hspV2Panel070A"));
    out.value_kept = q("#hspV2PanelBody070A [data-hsp-quick-add-search]")?.value;
    // Sin nada escrito, la llegada se pinta y el panel sigue abierto.
    const again = q("#hspV2PanelBody070A [data-hsp-quick-add-search]");
    again.value = "";
    again.blur();
    document.body.focus();
    await sleep(12000);
    out.open_after = Boolean(q("#hspV2Panel070A"));
    out.title_after = q("#hspV2PanelTitle070A")?.textContent;
    out.first_tables = names("tables").slice(0, 3);
    out.mesa2_badge = cardsOf("tables").find((c) => c.querySelector(".hsp-v2-name-070a").textContent === "Mesa 2")?.querySelector(".hsp-v2-badge-070a").textContent;
    return out;
  }

  async function filtersFlow() {
    const out = {};
    const click = (k) => q(`[data-hsp-v2-filter="${k}"]`).click();
    const groups = () => qa("[data-hsp-v2-group]").map((g) => g.getAttribute("data-hsp-v2-group"));
    click("bar");
    await sleep(50);
    out.bar_groups = groups();
    out.bar_cards = qa(".hsp-v2-card-070a").length;
    click("tables");
    await sleep(50);
    out.tables_groups = groups();
    click("new");
    await sleep(50);
    out.new_groups = groups();
    out.new_cards = names("tables");
    out.new_pressed = q('[data-hsp-v2-filter="new"]').getAttribute("aria-pressed");
    click("all");
    await sleep(50);
    const search = q("[data-hsp-v2-search]");
    type(search, "JOSE");
    await sleep(50);
    out.jose = qa(".hsp-v2-card-070a .hsp-v2-name-070a").map((n) => n.textContent);
    type(search, "mónica");
    await sleep(50);
    out.monica = qa(".hsp-v2-card-070a .hsp-v2-name-070a").map((n) => n.textContent);
    type(search, "mesa 1");
    await sleep(50);
    out.mesa1 = qa(".hsp-v2-card-070a .hsp-v2-name-070a").map((n) => n.textContent);
    out.mesa1_free = qa("[data-hsp-v2-group=free] button").map((b) => b.textContent.trim());
    type(search, "nadie");
    await sleep(50);
    out.none_text = q("#hspV2Lists070A")?.textContent.replace(/\s+/g, " ").trim();
    // "+ Cuenta de barra" abre el formulario de siempre.
    out.form_hidden = q("#hspV2Form070A").hidden;
    q("[data-hsp-v2-form]").click();
    await sleep(50);
    out.form_open = !q("#hspV2Form070A").hidden && visible(q("#hspBarCustomer031D"));
    window.__calls.length = 0;
    type(q("#hspBarCustomer031D"), "Nuevo cliente");
    type(q("#hspBarProductSearch031F"), "poker");
    q("[data-hsp-bar-create]").click();
    await sleep(700);
    out.create_calls = calls();
    return out;
  }

  async function tabletFlow() {
    const out = {};
    const btn = q("[data-hsp-v2-music]");
    out.btn_visible = visible(btn);
    out.btn_text = btn.textContent.replace(/\s+/g, " ").trim();
    out.btn = rr(btn);
    out.queue_hidden = !visible(q("#hspV2Music070A"));
    out.table_rows = rows(cardsOf("tables"));
    out.page_overflow = document.documentElement.scrollWidth > document.documentElement.clientWidth + 1;
    btn.click();
    await sleep(50);
    out.queue_shown = visible(q("#hspV2Music070A"));
    out.queue = rr(q("#hspV2Music070A"));
    out.copy = qa("#hspSongRequests031C button").length;
    key(document.body, "Escape");
    await sleep(50);
    out.queue_closed = !visible(q("#hspV2Music070A"));
    out.small_buttons = qa("#hspV2Grid070A button").filter(visible).filter((b) => b.getBoundingClientRect().height < 40).length;
    return out;
  }

  async function songFlow() {
    const out = {};
    const first = q("#hspV2Music070A");
    out.before = first.classList.contains("is-new-song-070a");
    out.count_before = q("#hspSongCount031C").textContent;
    window.__song();
    await sleep(4500);
    const queue = q("#hspV2Music070A");
    out.same_node = queue === first;
    out.after = queue.classList.contains("is-new-song-070a");
    out.count_after = q("#hspSongCount031C").textContent;
    out.item_marked = Boolean(q(".hsp-song-item-048b.is-new-song-070a"));
    queue.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
    await sleep(50);
    out.cleared = !queue.classList.contains("is-new-song-070a");
    return out;
  }

  async function offFlow() {
    return {
      v2: Boolean(q("#hspV2Grid070A")),
      bar_cards_classic: qa("#hspBarAccounts031D .hsp-bar-card-031d").length,
      table_cards_classic: qa("#hspTablesGrid034B .hsp-table-card-034b").length,
      song_search: Boolean(q("[data-hsp-song-search]")),
      music_btn: Boolean(q("[data-hsp-v2-music]")),
    };
  }

  const FLOWS = { layout, add: addFlow, panel: panelFlow, live: liveFlow, filters: filtersFlow, tablet: tabletFlow, song: songFlow, off: offFlow };
  const finish = (data) => {
    const pre = document.createElement("pre");
    pre.id = "layout";
    pre.style.display = "none";
    pre.textContent = JSON.stringify(data);
    document.body.appendChild(pre);
  };
  const go = (n = 0) => {
    const card = document.querySelector('[data-client-module="orders"]');
    if (!card) { if (n > 80) { finish({ mounted: false }); return; } setTimeout(() => go(n + 1), 200); return; }
    card.click();
    setTimeout(async () => {
      try {
        const mounted = Boolean(q("#hspOrdersRoot024R"));
        finish({ mounted, ...(mounted ? await FLOWS[sc]() : {}) });
      } catch (error) { finish({ mounted: false, error: String(error && error.stack || error) }); }
    }, 1500);
  };
  window.addEventListener("load", () => setTimeout(go, 300));
})();
