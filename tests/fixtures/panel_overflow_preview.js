// Vista previa de 5 paneles del portal con datos de ejemplo (fetch simulado) para medir desbordes:
// ?panel=orders (barra en modo kanban: Pendiente/Alistando/Entregado/Cerrado), materials,
// sales, tqt (Cotizaciones/Tickets) o tp (Tesoreria). Al terminar deja en #layout:
// { mounted, panel, out: [controles fuera de su tarjeta], overlap: [rotulos encimados] }.
// Datos inventados. No guarda capturas.
(() => {
  const P = new URLSearchParams(location.search);
  const CID = P.get("company_id") || "0f0f0f0f-1111-4222-8333-444444444444";
  const PANEL = P.get("panel") || "orders";
  const json = (b, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
  const real = window.fetch.bind(window);
  try { localStorage.setItem("clonexa_access_token", "preview"); } catch (_) {}
  const at = (min) => new Date(Date.now() - min * 60000).toISOString();
  const day = (d) => new Date(Date.now() + d * 86400000).toISOString().slice(0, 10);

  // ---------------------------------------------------------------- barra (kanban)
  const inventory = [
    { id: "i1", name: "Águila", sku: "AG330", category: "Cerveza", unit_price: 6000, stock: 80 },
    { id: "i2", name: "Margarita", sku: "MG01", category: "Cocteles", unit_price: 27000, stock: 40 },
  ];
  const line = (inv, quantity) => ({ inventory_item_id: inv.id, product_id: inv.id, sku: inv.sku, name: inv.name, quantity, unit_price: inv.unit_price, subtotal: inv.unit_price * quantity });
  const orders = [];
  const add = (id, table, status, items, min, extra = {}) => {
    const total = items.reduce((s, it) => s + it.subtotal, 0);
    orders.push({ id, order_number: `H-${id}`, table_number: table, table_key: table.toLowerCase(), source: "qr", status, total, items, created_at: at(min), updated_at: at(min),
      customer_name: "Cliente", people: [{ id: `p-${id}`, name: "Cliente", total, items }], metadata: {}, ...extra });
  };
  add("o1", "Mesa 4", "pendiente", [line(inventory[0], 4), line(inventory[1], 2)], 8);
  add("o2", "Mesa 9", "pendiente", [line(inventory[0], 3)], 5);
  add("o3", "Barra", "alistando", [line(inventory[1], 2)], 12);
  add("o4", "Mesa 2", "alistando", [line(inventory[0], 6)], 15);
  add("o5", "Mesa 7", "entregado", [line(inventory[1], 3)], 40);
  add("o6", "Mesa 1", "entregado", [line(inventory[0], 5), line(inventory[1], 1)], 55);

  // ---------------------------------------------------------------- otros paneles
  const materials = {
    summary: { pending: 1, approved: 1, delivered: 2, consigned: 1, returned: 0 },
    requests: [
      { id: "r1", order_number: "MAT-0214", employee_name: "Jorge Salazar", employee_role: "Técnico", material_name: "Cable UTP categoría 6 exterior", name_reference: "CAB-UTP6", quantity: 2, status: "pending", destination: "Obra Calle 80 con Avenida Boyacá", requested_at: at(90), created_at: at(90) },
      { id: "r2", order_number: "MAT-0213", employee_name: "Sandra Ruiz", employee_role: "Supervisora", material_name: "Canaleta 40x25", name_reference: "CAN-4025", quantity: 30, status: "approved", destination: "Centro comercial Norte", requested_at: at(200), created_at: at(200) },
      { id: "r3", order_number: "MAT-0212", employee_name: "Luis Cárdenas", employee_role: "Técnico", material_name: "Rack 12U", name_reference: "RCK-12U", quantity: 1, status: "delivered", destination: "Bodega Fontibón", requested_at: at(400), created_at: at(400) },
      { id: "r4", order_number: "MAT-0211", employee_name: "Diana Moreno", employee_role: "Técnica", material_name: "Patch cord 3 m", name_reference: "PC-3M", quantity: 12, status: "consigned", destination: "Obra Calle 80", requested_at: at(600), created_at: at(600) },
    ],
  };
  const employees = [
    { id: "e1", full_name: "Laura Méndez", name: "Laura Méndez", role: "vendedor redes", employee_type: "vendedor", phone: "", status: "active" },
    { id: "e2", full_name: "Camilo Ortiz", name: "Camilo Ortiz", role: "vendedor tienda", employee_type: "vendedor", phone: "3000000000", status: "active" },
  ];
  const salesUsers = [
    { id: "u1", employee_id: "e1", username: "laura", panel_type: "sales", status: "active", monthly_goal: 8000000, monthly_sales_total: 6880000, monthly_sales_count: 31 },
    { id: "u2", employee_id: "e2", username: "camilo", panel_type: "sales", status: "active", monthly_goal: 6000000, monthly_sales_total: 2100000, monthly_sales_count: 9 },
  ];
  const contracts = [{ id: "k1", client_name: "Empresa ABC (demo)", contract_code: "CTA-77", client_type: "company", phone: "6010000000", email: "compras@empresa.test", available_balance: 6400000 }];
  const docs = [
    { id: "d1", document_number: "TK-0318", document_type: "ticket", client_name: "Empresa ABC (demo)", contract_code: "CTA-77", account_code: "CTA-ABC-01", origin: "Bogotá", destination: "Medellín", route_detail: "Salida terminal norte · 2 vehículos", service_date: day(5), validity_date: day(10), total_amount: 3480000, ticket_count: 24, status: "en_ruta" },
    { id: "d2", document_number: "CT-0204", document_type: "quote", client_name: "Hotel Las Palmas", contract_code: "", origin: "Cali", destination: "Bogotá", route_detail: "Grupo de 18 personas", service_date: day(9), validity_date: day(20), total_amount: 2640000, ticket_count: 18, status: "aprobada" },
  ];
  const tickets = [
    { id: "t1", document_number: "TK-0318", client_name: "Empresa ABC (demo)", contract_code: "CTA-77", contract_id: "k1", origin: "Bogotá", destination: "Medellín", route_detail: "2 vehículos", service_date: day(-2), total_amount: 3480000, pending_amount: 3480000, paid_amount: 0, status: "pendiente_tesoreria", supervisor_check: true, treasury_check: false, contract_available_balance: 6400000, created_at: at(600), created_by: "Laura" },
  ];

  window.fetch = async (url, opts = {}) => {
    const u = String(url);
    if (!u.startsWith("/api/v1")) return real(url, opts);
    const p = u.slice(7).split("?")[0];
    if (p.endsWith("/locale")) return json({ currency: "COP", timezone: "America/Bogota", language: "es", decimals: 0 });
    if (p === `/companies/${CID}`) return json({ id: CID, name: "Empresa demo", slug: "demo", status: "active" });
    if (p === `/companies/${CID}/experience`) return json({ company_id: CID, branding: { mode: "dark", theme_mode: "dark" } });
    if (p === `/companies/${CID}/modules`) {
      const m = (code, name, settings = {}) => ({ id: `cm-${code}`, company_id: CID, module_id: `m-${code}`, enabled: true, settings, module: { code, name } });
      return json([m("orders", "Pedidos"), m("qr", "QR", { qr_config: { orders_board: "kanban", table_count: 12 }, qr_bar_menu: true }), m("materials", "Materiales"),
        m("sales", "Ventas"), m("transport_quotes_tickets", "Cotizaciones / Tickets"), m("transport_contracts", "Contratos"), m("transport_payments", "Tesoreria"), m("workforce", "Workforce")]);
    }
    if (p.endsWith("/closed-tables-summary")) return json({ ok: true, tables: 0, orders: 0, total: 0 });
    if (p.endsWith(`/hospitality/companies/${CID}/orders`)) return json({ ok: true, orders, summary: {}, song_requests: [] });
    if (p.endsWith("/qr-tables")) return json({ ok: true, tables: Array.from({ length: 12 }, (_, i) => ({ label: `Mesa ${i + 1}`, table_key: `mesa ${i + 1}` })) });
    if (p.endsWith("/inventory-lite")) return json({ ok: true, inventory });
    if (p.includes("/materials/companies/") && p.endsWith("/requests")) return json(materials);
    if (p === "/employees") return json(employees);
    if (p.endsWith("/mini-panel-users")) return json(salesUsers);
    if (p.endsWith("/mini-panel-sales-message")) return json({ message: "", promotions: [] });
    if (p.includes("/transport-contracts/") && p.endsWith("/contracts")) return json({ contracts });
    if (p.includes("/transport-quotes-tickets/")) {
      if (p.endsWith("/summary")) return json({ summary: { quote_count: 2, ticket_count: 3, pending_count: 1, total_amount: 13890000 } });
      if (p.endsWith("/documents")) return json({ documents: docs });
    }
    if (p.includes("/transport-payments/")) {
      if (p.endsWith("/summary")) return json({ summary: { pending_treasury_count: 1, ready_to_bill_count: 12, ticket_total: 9530000, contracts_available_total: 6400000, invoice_pending_total: 5430000, due_soon_count: 2, overdue_invoice_count: 0, paid_total: 0 } });
      if (p.endsWith("/queue")) return json({ tickets });
      if (p.endsWith("/payments")) return json({ payments: [] });
      if (p.endsWith("/invoices")) return json({ invoices: [{ id: "f1", invoice_number: "FV-120", client_name: "Empresa ABC (demo)", contract_code: "CTA-77", total_amount: 5430000, pending_amount: 5430000, due_date: day(4), status: "pendiente" }] });
      if (p.endsWith("/alerts")) return json({ low_balance_contracts: [], due_invoices: [] });
      if (p.endsWith("/mail-settings")) return json({ mail_settings: { sender_name: "Empresa demo", from_email: "", reply_to_email: "tesoreria@empresa.test", cc_email: "", signature: "", provider_configured: false } });
    }
    if (p.includes("/qr-guests/") || p.includes("/loyalty-games/") || p.includes("/loyalty-retos/")) return json({ detail: "x" }, 404);
    return json({});
  };

  // ---------------------------------------------------------------- medicion
  const SKIP_CLIP = /^(auto|scroll|hidden|clip)$/;
  const visible = (el) => { const s = getComputedStyle(el); const r = el.getBoundingClientRect(); return s.display !== "none" && s.visibility !== "hidden" && r.width > 0 && r.height > 0; };
  const isBox = (el) => {
    const s = getComputedStyle(el);
    const bg = s.backgroundColor && !/rgba\(.*,\s*0\)$/.test(s.backgroundColor) && s.backgroundColor !== "transparent";
    return (parseFloat(s.borderTopWidth) > 0 && parseFloat(s.borderLeftWidth) > 0) || bg || (s.backgroundImage && s.backgroundImage !== "none");
  };
  const desc = (el) => `${el.tagName.toLowerCase()}${el.className && typeof el.className === "string" ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".") : ""}${el.textContent ? ` "${el.textContent.trim().replace(/\s+/g, " ").slice(0, 24)}"` : ""}`;
  function measure() {
    const main = document.querySelector(".client-main") || document.body;
    const out = [];
    for (const el of main.querySelectorAll("button, input, select, textarea, .client-btn, a.client-btn")) {
      if (!visible(el) || el.closest("[hidden]")) continue;
      const r = el.getBoundingClientRect();
      let card = null;
      let scroller = false;
      for (let a = el.parentElement; a && a !== main; a = a.parentElement) {
        const s = getComputedStyle(a);
        if (SKIP_CLIP.test(s.overflowX) && a.scrollWidth > a.clientWidth + 1) { scroller = true; break; } // dentro de una tabla con scroll: es a proposito
        if (isBox(a) && a.getBoundingClientRect().width > r.width) { card = a; break; }
      }
      if (scroller) continue;
      // fuera del area principal (la tarjeta entera se sale de la pantalla) o fuera de su tarjeta
      const m = main.getBoundingClientRect();
      const offMain = Math.round(Math.max(r.right - Math.min(m.right, document.documentElement.clientWidth), m.left - r.left));
      if (offMain > 2) { out.push({ el: desc(el), card: "area principal", px: offMain }); continue; }
      if (!card) continue;
      const c = card.getBoundingClientRect();
      const over = Math.round(Math.max(r.right - c.right, c.left - r.left));
      if (over > 2) out.push({ el: desc(el), card: desc(card).slice(0, 60), px: over });
    }
    const overlap = [];
    // Un texto dentro de un <details> cerrado o recortado por un contenedor con overflow no se ve:
    // no cuenta como rotulo encimado.
    const shown = (el) => {
      const d = el.closest("details:not([open])");
      if (d && !el.closest("summary")) return false;
      const r = el.getBoundingClientRect();
      for (let a = el.parentElement; a && a !== main; a = a.parentElement) {
        if (getComputedStyle(a).overflow === "visible") continue;
        const c = a.getBoundingClientRect();
        if (r.top >= c.bottom - 1 || r.bottom <= c.top + 1 || r.left >= c.right - 1 || r.right <= c.left + 1) return false;
      }
      return true;
    };
    const texts = [...main.querySelectorAll("label > span, label, small, .client-eyebrow")].filter((el) => visible(el) && el.children.length <= 1 && shown(el));
    for (let i = 0; i < texts.length; i += 1) {
      for (let j = i + 1; j < texts.length; j += 1) {
        const a = texts[i], b = texts[j];
        if (a.contains(b) || b.contains(a)) continue;
        const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
        const w = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left);
        const hh = Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top);
        if (w > 4 && hh > 4 && w * hh > 0.2 * Math.min(ra.width * ra.height, rb.width * rb.height)) overlap.push(`${desc(a)} / ${desc(b)}`);
      }
    }
    const rows = { sales: main.querySelectorAll('[data-sales-employee], .cx-sales-row-019c, article').length };
    return { rows, out: out.slice(0, 12), n_out: out.length, overlap: overlap.slice(0, 8), n_overlap: overlap.length, page_overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth };
  }

  const finish = (data) => {
    const pre = document.createElement("pre");
    pre.id = "layout";
    pre.style.display = "none";
    pre.textContent = JSON.stringify(data);
    document.body.appendChild(pre);
  };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const MARK = { orders: "#hspOrdersRoot024R", materials: "[data-materials-refresh]", sales: ".client-main", tqt: "#tqtRefresh028N", tp: "#tpRefresh028R" };
  const CODE = { orders: "orders", materials: "materials", sales: "sales", tqt: "transport_quotes_tickets", tp: "transport_payments" };
  const go = async (n = 0) => {
    const btn = document.querySelector(`[data-client-module="${CODE[PANEL]}"]`);
    if (!btn) { if (n > 80) { finish({ mounted: false, panel: PANEL, error: "sin boton" }); return; } setTimeout(() => go(n + 1), 200); return; }
    btn.click();
    for (let i = 0; i < 40 && !document.querySelector(MARK[PANEL]); i += 1) await sleep(200);
    await sleep(1200);
    try {
      if (PANEL === "orders") {
        // como en la captura: pago en efectivo elegido -> se ve "Dinero recibido"
        document.querySelectorAll("[data-hsp-close-payment]").forEach((s) => { s.value = "cash"; s.dispatchEvent(new Event("change", { bubbles: true })); });
        await sleep(300);
      }
      finish({ mounted: Boolean(document.querySelector(MARK[PANEL])), panel: PANEL, ...measure() });
    } catch (error) { finish({ mounted: false, panel: PANEL, error: String(error && error.stack || error) }); }
  };
  window.addEventListener("load", () => setTimeout(go, 300));
})();
