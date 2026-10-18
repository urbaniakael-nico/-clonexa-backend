// Vista previa de Reportes › Búsqueda de eventos en el portal real (client.html +
// client.js), con datos de ejemplo y el interruptor qr_welcome_name: cada evento
// muestra sus invitados ("Laura · Mesa 4") y se busca por nombre. ?q=laura escribe
// en la búsqueda. Sin servidor ni datos reales.
(() => {
  const P = new URLSearchParams(location.search);
  const CID = P.get("company_id");
  const branding = { mode: "dark", theme_mode: "dark", font_family: "Poppins", primary_color: "#6b5d00", text_color: "#ffffff", secondary_color: "#aea924",
    background_color: "#14110a", gradient_from: "#14110a", gradient_to: "#2a2410", background_mode: "gradient", card_style: "neon_border", visual_preset: "classic_office" };
  const json = (b, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
  const real = window.fetch.bind(window);
  try { localStorage.setItem("clonexa_access_token", "preview"); } catch (_) {}
  const day = "2026-10-17";
  const item = (name, q, p) => ({ name, quantity: q, unit_price: p, subtotal: q * p });
  const events = [
    { id: "e1", type: "qr", label: "Mesa 4", location: "Mesa 4", customer_name: "Laura", activation_number: 2, active: false, started_at: "2026-10-18T01:10:00Z", ended_at: "2026-10-18T05:40:00Z",
      orders_count: 4, order_numbers: ["H-0101", "H-0104", "H-0110"], items: [item("Cerveza Club Colombia", 6, 9000), item("Aguardiente media", 1, 48000)], total: 102000, payment_label: "Efectivo",
      guest_names: ["Laura", "Persona 2", "Juan Pablo"] },
    { id: "e2", type: "qr", label: "Mesa 7", location: "Mesa 7", customer_name: "Andrés", activation_number: 1, active: true, started_at: "2026-10-18T02:30:00Z", ended_at: null,
      orders_count: 2, order_numbers: ["H-0107"], items: [item("Coctel de la casa", 2, 28000)], total: 56000, payment_label: "Tarjeta", guest_names: ["Andrés"] },
    { id: "e3", type: "bar", label: "Camila", location: "Barra", customer_name: "Camila", activation_number: null, active: false, started_at: "2026-10-18T03:00:00Z", ended_at: "2026-10-18T03:20:00Z",
      orders_count: 1, order_numbers: ["H-0112"], items: [item("Shot de tequila", 2, 15000)], total: 30000, payment_label: "Transferencia" },
  ];
  const period = (key) => ({ key, label: key, total: 188000, orders: 7 });
  const analytics = { days: { periods: [period(day)], totals: { total: 188000, orders: 7 } }, weeks: { periods: [period("2026-W42")], totals: { total: 188000, orders: 7 } },
    months: { periods: [period("2026-10")], totals: { total: 188000, orders: 7 } } };
  window.fetch = async (url, opts) => {
    const u = String(url);
    if (!u.startsWith("/api/v1")) return real(url, opts);
    const p = u.slice(7).split("?")[0];
    if (p.endsWith("/locale")) return json({ currency: "COP", timezone: "America/Bogota", language: "es", decimals: 0 });
    if (p === `/companies/${CID}`) return json({ id: CID, name: "The Time Machine", slug: "ttm", status: "active" });
    if (p === `/companies/${CID}/experience`) return json({ company_id: CID, branding });
    if (p === `/companies/${CID}/modules`) return json([{ id: "cm1", company_id: CID, module_id: "m1", enabled: true, settings: {}, module: { code: "hospitality", name: "Reportes" } }]);
    if (p.endsWith("/analytics")) {
      return json({ ok: true, company_id: CID, timezone: "America/Bogota", today: day, generated_at: new Date().toISOString(), analytics,
        event_search: { date: day, events, summary: { events: 3, qr_events: 2, bar_events: 1, total: 188000, orders: 7, reconciled: true }, guest_search: P.get("off") !== "1" } });
    }
    if (p.includes("/loyalty-retos/") || p.includes("/loyalty-games/")) return json({}, 404);
    return json({});
  };
  const go = (n = 0) => {
    const card = document.querySelector('[data-client-module="hospitality"]');
    if (!card) return n > 80 ? null : setTimeout(() => go(n + 1), 200);
    card.click();
    const wait = (j = 0) => {
      const box = document.querySelector(".hspdash-events-033b");
      if (!box) return j > 60 ? null : setTimeout(() => wait(j + 1), 200);
      box.scrollIntoView({ block: "start" });
      const q = P.get("q");
      const input = document.querySelector("[data-hsp-dash-guest-filter]");
      if (q && input) { input.value = q; input.dispatchEvent(new Event("input", { bubbles: true })); }
      const out = document.createElement("pre");
      out.id = "layout";
      out.style.display = "none";
      out.textContent = JSON.stringify({ mounted: true, filter: !!input, cards: document.querySelectorAll(".hspdash-event-card-033b").length,
        guests: [...document.querySelectorAll(".hspdash-event-guests-056b b")].map((b) => b.textContent),
        page_overflow: document.documentElement.scrollWidth > window.innerWidth + 1 });
      document.body.appendChild(out);
      return null;
    };
    setTimeout(wait, 600);
    return null;
  };
  window.addEventListener("load", () => setTimeout(go, 300));
})();
