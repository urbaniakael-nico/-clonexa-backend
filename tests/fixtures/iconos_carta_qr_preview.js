// Vista previa de la pantalla QR del bar (hospitality_order.html real) con la
// galería de íconos de Clonexa (iconos_carta_clonexa), como Mesa 4 de The Time
// Machine. Datos de ejemplo (sin servidor). ?off=1: sin el interruptor.
// ?prod=Aguardiente abre esa categoría. Mide la grilla en <pre id="layout">.
(() => {
  const P = new URLSearchParams(location.search);
  const CID = P.get("company_id");
  const OFF = P.get("off") === "1";
  const json = (b, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
  const real = window.fetch.bind(window);
  try { localStorage.setItem(`clonexa_hsp_table_access_${CID}_mesa_4`, "ABC12"); } catch (_) {}
  const url = (k) => `/assets/iconos-carta/${k === "bebida" ? "bebida-generica" : k}.svg?v=ic1`;
  const CATS = [["Agua", "agua", 1], ["Aguardiente", "aguardiente", 5], ["Cerveza", "cerveza", 12], ["Chiclets", "chiclets", 1], ["Cigarrillo", "cigarrillo", 7],
    ["Gaseosa", "gaseosa", 2], ["Hidratante", "hidratante", 1], ["Paquete", "paquete", 2], ["Ron", "ron", 2], ["Shot", "shot", 9], ["Tequila", "tequila", 1],
    ["Tiket", "tiket", 1], ["Vodka", "vodka", 3], ["Whiskey", "whiskey", 5]];
  const inventory = [];
  CATS.forEach(([cat, key, n]) => {
    for (let i = 0; i < n; i += 1) {
      const icon = { source: "auto", key, url: url(key), word: cat.toLowerCase(), auto: { key, url: url(key), word: cat.toLowerCase(), recognized: true } };
      inventory.push({ id: `${key}-${i}`, name: `${cat} ${["clásico", "media botella de 375 ml", "litro"][i % 3]} ${i + 1}`, price: 5000 + i * 1000, stock: 10, ...(OFF ? {} : { icon }) });
    }
  });
  window.fetch = async (u0, opts) => {
    const u = String(u0);
    if (!u.includes("/api/v1")) return real(u0, opts);
    const p = u.slice(u.indexOf("/api/v1") + 7).split("?")[0];
    if (p === `/companies/${CID}`) return json({ id: CID, name: "The Time Machine" });
    if (p === `/companies/${CID}/branding`) return json({ branding: { primary_color: "#6b5d00", secondary_color: "#aea924", background_color: "#14110a", text_color: "#ffffff" } });
    if (p.endsWith("/qr-tables/access")) return json({ ok: true, access: { active: true }, company_name: "The Time Machine", ui: { bar_menu: true } });
    if (p.endsWith("/qr-tables/access/verify")) return json({ ok: true, access: { active: true } });
    if (p.endsWith("/qr-tables/account")) return json({ ok: true, account: { total: 0, orders_count: 0, accounts_count: 0, items: [], accounts: [] } });
    if (p.includes("/inventory-lite")) return json({ inventory, ...(OFF ? {} : { iconos_carta: true }) });
    return json({});
  };

  const box = (el) => { const r = el.getBoundingClientRect(); return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height), r: Math.round(r.right), b: Math.round(r.bottom) }; };
  function measure() {
    const out = document.createElement("pre");
    out.id = "layout";
    out.style.display = "none";
    const tiles = [...document.querySelectorAll(".qrb-cat, .qrb-product")];
    const imgs = [...document.querySelectorAll(".qrb-cat-icon img, .qrb-product-icon img")];
    const icons = [...document.querySelectorAll(".qrb-cat-icon, .qrb-product-icon")];
    const overflow = tiles.filter((t) => t.scrollWidth > t.clientWidth + 1 || t.scrollHeight > t.clientHeight + 1).map((t) => t.textContent.trim().slice(0, 30));
    const outside = imgs.filter((img) => { const a = box(img); const t = box(img.closest(".qrb-cat, .qrb-product")); return a.x < t.x - 1 || a.r > t.r + 1 || a.y < t.y - 1 || a.b > t.b + 1; }).length;
    const rows = {};
    tiles.forEach((t) => { const b = box(t); (rows[b.y] = rows[b.y] || []).push(b.h); });
    out.textContent = JSON.stringify({
      mounted: tiles.length > 0, tiles: tiles.length, imgs: imgs.length,
      loaded: imgs.filter((i) => i.complete && i.naturalWidth > 0).length,
      img_sizes: [...new Set(imgs.map((i) => `${box(i).w}x${box(i).h}`))],
      icon_heights: [...new Set(icons.map((i) => box(i).h))],
      per_row: Object.values(rows).map((r) => r.length), uneven_rows: Object.values(rows).filter((r) => Math.max(...r) - Math.min(...r) > 1).length,
      overflow, outside, page_overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
      alts: imgs.slice(0, 3).map((i) => i.alt),
    });
    document.body.appendChild(out);
  }
  const ready = (n = 0) => {
    if (n < 60 && !document.querySelector(".qrb-cat, .qrb-product")) return setTimeout(() => ready(n + 1), 250);
    const prod = P.get("prod");
    if (prod) { const b = document.querySelector(`[data-bar-cat="${prod}"]`); if (b) b.click(); }
    return setTimeout(measure, 1500);
  };
  window.addEventListener("load", () => setTimeout(ready, 1000));
})();
