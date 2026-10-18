// Vista previa del tablero de mesas del bar (Pedidos) con qr_welcome_name: cada
// invitado de la mesa tiene "✏️ Corregir nombre" (solo si /qr-guests/config
// responde 200). ?open=1 abre a la persona; ?dialog=1 abre el diálogo. Datos de ejemplo.
(() => {
  const P = new URLSearchParams(location.search);
  const CID = P.get("company_id");
  const branding = { mode: "dark", theme_mode: "dark", font_family: "Poppins", primary_color: "#6b5d00", text_color: "#ffffff", secondary_color: "#aea924",
    background_color: "#14110a", gradient_from: "#14110a", gradient_to: "#2a2410", background_mode: "gradient", card_style: "neon_border", visual_preset: "classic_office" };
  const json = (b, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
  const real = window.fetch.bind(window);
  try { localStorage.setItem("clonexa_access_token", "preview"); } catch (_) {}
  const at = new Date(Date.now() - 42 * 60000).toISOString();
  const beer = { name: "Cerveza Club Colombia", quantity: 4, unit_price: 9000, subtotal: 36000 };
  const cocktail = { name: "Coctel de la casa", quantity: 1, unit_price: 32000, subtotal: 32000 };
  const orders = [
    { id: "o1", order_number: "H-0201", table_number: "Mesa 4", table_key: "mesa 4", source: "qr", status: "entregado", total: 36000, items: [beer], created_at: at, updated_at: at,
      customer_name: "Nicolsa", people: [{ id: "qr_account_a", account_id: "qr_account_a", name: "Nicolsa", total: 36000, items: [beer] }], metadata: { account_id: "qr_account_a", guest_name: "Nicolsa" } },
    { id: "o2", order_number: "H-0202", table_number: "Mesa 4", table_key: "mesa 4", source: "qr", status: "entregado", total: 32000, items: [cocktail], created_at: at, updated_at: at,
      customer_name: "Persona 2", people: [{ id: "qr_account_b", account_id: "qr_account_b", name: "Persona 2", total: 32000, items: [cocktail] }], metadata: { account_id: "qr_account_b", guest_name: "Persona 2" } },
  ];
  window.fetch = async (url, opts) => {
    const u = String(url);
    if (!u.startsWith("/api/v1")) return real(url, opts);
    const p = u.slice(7).split("?")[0];
    if (p.endsWith("/locale")) return json({ currency: "COP", timezone: "America/Bogota", language: "es", decimals: 0 });
    if (p === `/companies/${CID}`) return json({ id: CID, name: "The Time Machine", slug: "ttm", status: "active" });
    if (p === `/companies/${CID}/experience`) return json({ company_id: CID, branding });
    if (p === `/companies/${CID}/modules`) {
      return json([{ id: "cm1", company_id: CID, module_id: "m1", enabled: true, settings: {}, module: { code: "orders", name: "Pedidos" } },
        { id: "cm2", company_id: CID, module_id: "m2", enabled: true, settings: { qr_config: { orders_board: "mesas", table_count: 4 } }, module: { code: "qr", name: "QR" } }]);
    }
    if (p.endsWith("/qr-guests/config")) return P.get("off") === "1" ? json({ detail: "x" }, 404) : json({ ok: true, name_max: 30 });
    if (p.includes("/orders")) return json({ ok: true, orders, summary: { pending: 0, preparing: 0, served: 2 }, song_requests: [] });
    if (p.endsWith("/qr-tables")) return json({ ok: true, tables: [{ label: "Mesa 4", table_key: "mesa 4" }] });
    if (p.includes("/loyalty-games/") || p.includes("/loyalty-retos/")) return json({}, 404);
    return json({});
  };
  const go = (n = 0) => {
    const card = document.querySelector('[data-client-module="orders"]');
    if (!card) return n > 80 ? null : setTimeout(() => go(n + 1), 200);
    card.click();
    const wait = (j = 0) => {
      const btn = document.querySelector("[data-guest-fix-account]");
      if (!btn) return j > 60 ? null : setTimeout(() => wait(j + 1), 200);
      setTimeout(() => {  // despues del primer repintado del tablero
        const openRows = () => document.querySelectorAll(".hsp-table-person-034b, .hsp-account-row-024y").forEach((d) => { if (P.get("open") === "1" || P.get("dialog") === "1") d.open = true; });
        openRows();
        setInterval(openRows, 300);  // el tablero se repinta solo
        const fresh = document.querySelector("[data-guest-fix-account]");
        if (fresh) fresh.scrollIntoView({ block: "center" });
        if (P.get("dialog") === "1" && fresh) fresh.click();
      }, 1500);
      return null;
    };
    setTimeout(wait, 600);
    return null;
  };
  window.addEventListener("load", () => setTimeout(go, 300));
})();
