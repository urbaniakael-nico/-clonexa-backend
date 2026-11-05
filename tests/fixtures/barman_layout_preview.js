// Vista previa del Panel Barman (Pedidos) con datos de ejemplo. Parámetros:
// on=1 enciende barman_music_layout; bar=1 enciende qr_bar_menu; songs=N canciones;
// closed=N mesas cerradas; tables=N mesas. Al terminar deja en #layout las medidas.
(() => {
  const P = new URLSearchParams(location.search);
  const CID = P.get("company_id");
  const on = P.get("on") === "1";
  const nSongs = Number(P.get("songs") || 3);
  const nClosed = Number(P.get("closed") || 8);
  const nTables = Number(P.get("tables") || 12);
  const branding = { mode: "dark", theme_mode: "dark", font_family: "Poppins", primary_color: "#6b5d00", text_color: "#ffffff", secondary_color: "#aea924",
    background_color: "#14110a", gradient_from: "#14110a", gradient_to: "#2a2410", background_mode: "gradient", card_style: "neon_border", visual_preset: "classic_office" };
  const json = (b, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
  const real = window.fetch.bind(window);
  try { localStorage.setItem("clonexa_access_token", "preview"); } catch (_) {}
  const at = (min) => new Date(Date.now() - min * 60000).toISOString();
  const beer = { name: "Cerveza Club Colombia Dorada botella 330 ml", quantity: 4, unit_price: 9000, subtotal: 36000 };
  const orders = [
    { id: "a1", order_number: "H-0201", table_number: "Mesa 4", table_key: "mesa 4", source: "qr", status: "entregado", total: 1236000, items: [beer], created_at: at(42), updated_at: at(40),
      customer_name: "Persona 1", people: [{ id: "p1", name: "Persona 1", total: 1236000, items: [beer] }], metadata: {} },
    { id: "a2", order_number: "H-0202", table_number: "Mesa 5", table_key: "mesa 5", source: "qr", status: "pendiente", total: 36000, items: [beer], created_at: at(2), updated_at: at(2),
      customer_name: "Persona 2", people: [{ id: "p2", name: "Persona 2", total: 36000, items: [beer] }], metadata: {} },
  ];
  // Cerradas: la Mesa 20+i con i=0 es la más reciente; total = 10.000 * (i + 1).
  for (let i = 0; i < nClosed; i += 1) {
    orders.push({ id: `c${i}`, order_number: `H-03${i}`, table_number: `Mesa ${20 + i}`, table_key: `mesa ${20 + i}`, source: "qr", status: "cerrado", payment_method: "cash", payment_label: "Efectivo",
      total: 10000 * (i + 1), items: [beer], created_at: at(300 - i), updated_at: at(10 + i * 10), closed_at: at(10 + i * 10), people: [], metadata: {} });
  }
  // Una archivada (ya pasó por "Generar cierre"): nunca debe contar.
  if (P.get("archived") === "1") orders.push({ id: "z", order_number: "H-9", table_number: "Mesa 99", table_key: "mesa 99", source: "qr", status: "cerrado", total: 999000, items: [], created_at: at(900), closed_at: at(900), archived_at: at(800), people: [], metadata: {} });
  const songs = Array.from({ length: nSongs }, (_, i) => ({ id: `s${i}`, table_number: `Mesa ${(i % 4) + 1}`, song: `Canción de ejemplo ${i} - Artista`, status: "pendiente", created_at: at(60 - i), updated_at: at(60 - i) }));
  window.__archived = [];
  window.__copied = [];
  if (P.get("clip") === "fail") {
    navigatorClipboard(async () => { throw new Error("denegado"); });
    document.execCommand = () => false;
  } else {
    navigatorClipboard(async (text) => { window.__copied.push(text); });
  }
  function navigatorClipboard(writeText) {
    try { Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true }); } catch (_) {}
  }
  window.fetch = async (url, opts) => {
    const u = String(url);
    if (!u.startsWith("/api/v1")) return real(url, opts);
    const p = u.slice(7).split("?")[0];
    if (p.endsWith("/locale")) return json({ currency: "COP", timezone: "America/Bogota", language: "es", decimals: 0 });
    if (p === `/companies/${CID}`) return json({ id: CID, name: "The Time Machine", slug: "ttm", status: "active" });
    if (p === `/companies/${CID}/experience`) return json({ company_id: CID, branding });
    if (p === `/companies/${CID}/modules`) {
      const settings = { qr_config: { orders_board: P.get("board") || "mesas", table_count: nTables } };
      if (on) settings.barman_music_layout = true;
      if (P.get("bar") === "1") settings.qr_bar_menu = true;
      return json([{ id: "cm1", company_id: CID, module_id: "m1", enabled: true, settings: {}, module: { code: "orders", name: "Pedidos" } },
        { id: "cm2", company_id: CID, module_id: "m2", enabled: true, settings, module: { code: "qr", name: "QR" } }]);
    }
    if (p.endsWith("/day-closures") && opts && opts.method === "POST") {
      // Como el servidor: "Generar cierre" archiva lo cerrado y el panel deja de recibirlo.
      window.__closurePosted = true;
      orders.forEach((order) => { if (order.status === "cerrado") order.archived_at = at(0); });
      return json({ ok: true, closure: { closure_number: "C-1" }, closed_table_accesses: 0 });
    }
    const archive = /\/song-requests\/([^/]+)\/archive$/.exec(p);
    if (archive) {
      window.__archived.push(archive[1]);
      const i = songs.findIndex((s) => s.id === archive[1]);
      if (i >= 0) songs.splice(i, 1);
      return json({ ok: true });
    }
    if (p.endsWith("/orders")) return json({ ok: true, orders: orders.filter((o) => !o.archived_at), summary: {}, song_requests: songs });
    if (p.endsWith("/qr-tables")) return json({ ok: true, tables: Array.from({ length: nTables }, (_, i) => ({ label: `Mesa ${i + 1}`, table_key: `mesa ${i + 1}` })) });
    if (p.includes("/qr-guests/") || p.includes("/loyalty-games/") || p.includes("/loyalty-retos/")) return json({ detail: "x" }, 404);
    if (p.includes("/inventory")) return json({ ok: true, inventory: [], items: [] });
    return json({});
  };

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const rect = (el) => (el ? el.getBoundingClientRect() : null);
  async function measure() {
    const q = (s) => document.querySelector(s);
    const qa = (s) => Array.from(document.querySelectorAll(s));
    const out = { mounted: Boolean(q("#hspOrdersRoot024R")) };
    if (!out.mounted) return out;
    const grid = q(".hsp-operations-grid-031d");
    const queue = q(".hsp-song-queue-031c");
    const list = q("#hspSongRequests031C");
    const bar = q(".hsp-bar-workspace-031d");
    const tables = q(".hsp-tables-board-034b");
    const fold = q("#hspClosedFold069A");
    const r = (el) => { const b = rect(el); return b ? { top: Math.round(b.top), bottom: Math.round(b.bottom), left: Math.round(b.left), right: Math.round(b.right), w: Math.round(b.width), h: Math.round(b.height) } : null; };
    out.page_overflow = document.documentElement.scrollWidth > document.documentElement.clientWidth + 1;
    out.switch_class = grid.classList.contains("hsp-barman-grid-069a");
    Object.assign(out, { queue: r(queue), bar: r(bar), tables: r(tables), fold: r(fold), grid: r(grid), list: r(list), shell: r(q("#hspOrdersRoot024R")) });
    out.list_scrolls = list.scrollHeight > list.clientHeight + 1;
    out.list_overflow_y = getComputedStyle(list).overflowY;
    const cards = qa(".hsp-table-card-034b");
    const firstTop = cards[0] ? Math.round(rect(cards[0]).top) : 0;
    out.tables_per_row = cards.filter((c) => Math.abs(Math.round(rect(c).top) - firstTop) < 3).length;
    out.card_w = cards[0] ? Math.round(rect(cards[0]).width) : 0;
    const clipped = [];
    const scan = (root, label) => {
      if (!root) return;
      const box = rect(root);
      root.querySelectorAll("*").forEach((el) => {
        const b = rect(el);
        if (!b.width || !b.height || getComputedStyle(el).position === "fixed") return;
        if (el.closest("datalist") || el.tagName === "OPTION") return;
        if (b.right > box.right + 1 || b.left < box.left - 1) clipped.push(`${label}:${el.tagName}.${String(el.className).slice(0, 30)}:${Math.round(b.right - box.right)}`);
      });
    };
    scan(bar, "bar");
    cards.forEach((c, i) => scan(c, `card${i}`));
    scan(fold, "fold");
    scan(queue, "queue");
    out.clipped = clipped.slice(0, 12);
    const small = cards.flatMap((c) => Array.from(c.querySelectorAll("input"))).filter((el) => rect(el).width && rect(el).width < 40).map((el) => Math.round(rect(el).width));
    out.tiny_inputs = small.slice(0, 5);
    out.song_buttons = Array.from(new Set(qa("#hspSongRequests031C button").map((b) => b.textContent.trim())));
    out.song_controls = { search: Boolean(queue.querySelector("[data-hsp-song-search]")), bulk: Boolean(queue.querySelector("[data-hsp-song-archive-bulk]")) };
    out.song_count = q("#hspSongCount031C")?.textContent;
    if (fold) {
      out.title = q("#hspClosedTitle069A")?.textContent || "";
      const chips = () => qa("#hspClosedStrip034B .hsp-closed-chip-034b b").map((b) => b.textContent);
      const more = () => q("[data-hsp-closed-all]");
      out.open_default = fold.open;
      out.chips_default = chips();
      out.more_label = more()?.textContent || "";
      if (more()) {
        more().click();
        await sleep(50);
        out.chips_all = chips().length;
        out.fold_all_h = r(fold).h;
        const qRect = r(queue);
        out.all_bottom_delta = qRect ? Math.abs(qRect.bottom - r(fold).bottom) : null;
      }
      await sleep(6500); // pasa un refresco automático del panel
      out.chips_after_poll = chips().length;
      if (more()) { more().click(); await sleep(50); }
      out.chips_back = chips().length;
      q("#hspClosedFold069A > summary").click();
      await sleep(50);
      out.closed_after_click = !q("#hspClosedFold069A").open;
      const collapsed = r(q("#hspClosedFold069A"));
      out.collapsed_h = collapsed.h;
      out.collapsed_bottom_delta = Math.abs(r(queue).bottom - collapsed.bottom);
      await sleep(6500);
      out.still_closed = !q("#hspClosedFold069A").open;
    }
    if (P.get("gen") === "1") {
      const before = q("#hspClosedTitle069A")?.textContent || "";
      window.confirm = () => true;
      q("[data-hsp-open-closure]").click();
      await sleep(100);
      q("[data-hsp-generate-closure]").click();
      await sleep(500);
      return { mounted: true, switch_class: out.switch_class, before, after: q("#hspClosedTitle069A")?.textContent || "", posted: Boolean(window.__closurePosted),
        chips: qa("#hspClosedStrip034B .hsp-closed-chip-034b").length, more: Boolean(q("[data-hsp-closed-all]")), fold_open: Boolean(q("#hspClosedFold069A")?.open) };
    }
    const copy = q("[data-hsp-song-copy]");
    if (copy) {
      const id = copy.getAttribute("data-hsp-song-copy");
      out.copy_id = id;
      copy.click();
      await sleep(300);
      out.copied = window.__copied.slice();
      out.archived = window.__archived.slice();
      out.copy_gone = !q(`[data-hsp-song-copy="${id}"]`);
      out.song_count_after = q("#hspSongCount031C")?.textContent;
      out.toast = q("#hspSongToast048B")?.textContent || "";
      await sleep(6500);
      out.copy_still_gone = !q(`[data-hsp-song-copy="${id}"]`);
    }
    return out;
  }
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
      try { finish(await measure()); } catch (error) { finish({ mounted: false, error: String(error) }); }
    }, 1500);
  };
  window.addEventListener("load", () => setTimeout(go, 300));
})();
