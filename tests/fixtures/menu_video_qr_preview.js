// Vista previa del QR de la mesa (hospitality_order.html real) con la carta en
// video (carta_video) como Mesa 4, sin servidor: datos y medios de ejemplo en
// /__mv/ (tests/fixtures/menu_video). Mide en <pre id="layout"> que el feed
// ocupe la pantalla, que nombre/precio/Agregar se vean, el contraste, que solo
// el video visible y el siguiente tengan src y que Agregar sume al pedido.
// ?video=0 (interruptor apagado), ?add=1 (toca Agregar en el primer plato).
(() => {
  const P = new URLSearchParams(location.search);
  const CID = P.get("company_id");
  const VIDEO = P.get("video") !== "0";
  const json = (b, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
  const real = window.fetch.bind(window);
  try { localStorage.setItem(`clonexa_hsp_table_access_${CID}_mesa_4`, "ABC12"); } catch (_) {}
  const iso = (ms) => new Date(Date.now() + ms).toISOString();
  const INVENTORY = [
    { id: "d1", name: "Lomo al trapo", price: 42000, category_label: "FUERTES", description: "Lomo de res asado envuelto en tela con sal gruesa, papa criolla y chimichurri.",
      photo_url: "/__mv/d1-poster.webp", video_url: "/__mv/d1.mp4", poster_url: "/__mv/d1-poster.webp", active: true },
    { id: "d2", name: "Ajiaco santafereño", price: 28000, category_label: "SOPAS", description: "Pollo, tres papas, guascas, mazorca, crema y alcaparras.",
      photo_url: "/__mv/d2-poster.webp", video_url: "/__mv/d2.mp4", poster_url: "/__mv/d2-poster.webp", active: true },
    { id: "d3", name: "Limonada de coco", price: 12000, category_label: "BEBIDAS", photo_url: "/__mv/d3.webp", video_url: "", poster_url: "", active: true },
    { id: "d4", name: "Torta de chocolate de la abuela con helado de vainilla", price: 15000, category_label: "POSTRES", photo_url: "", video_url: "", poster_url: "", active: true },
  ];
  window.fetch = async (url, opts) => {
    const u = String(url);
    if (!u.includes("/api/v1")) return real(url, opts);
    const p = u.slice(u.indexOf("/api/v1") + 7).split("?")[0];
    if (p === `/companies/${CID}`) return json({ id: CID, name: "Brasa & Maíz" });
    if (p === `/companies/${CID}/branding`) return json({ branding: { primary_color: "#e4572e", secondary_color: "#ffc857", background_color: "#1b1220", text_color: "#ffffff" } });
    if (p.endsWith("/qr-tables/access")) return json({ ok: true, access: { active: true, expires_at: iso(3600000) }, company_name: "Brasa & Maíz", ui: { bar_menu: false } });
    if (p.endsWith("/qr-tables/access/verify")) return json({ ok: true, access: { active: true, expires_at: iso(3600000) } });
    if (p.endsWith("/qr-tables/account")) return json({ ok: true, account: { total: 0, orders_count: 0, accounts_count: 0, items: [], accounts: [] } });
    if (p.includes("/inventory-lite")) return json({ inventory: INVENTORY, carta_video: VIDEO });
    if (p.includes("/loyalty-campaigns/active")) return json({ ok: true, campaign: null });
    return json({});
  };

  function rgb(value) {
    const m = String(value || "").match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const [r, g, b, a = 1] = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
    return { r, g, b, a };
  }
  function lum({ r, g, b }) { const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); }
  function contrast(a, b) { const x = lum(a) + 0.05; const y = lum(b) + 0.05; return Math.round((Math.max(x, y) / Math.min(x, y)) * 100) / 100; }

  function measure() {
    const feed = document.querySelector(".cxmv-feed");
    const out = { mounted: !!feed && !feed.hidden, vw: innerWidth, vh: innerHeight };
    out.page_overflow = document.documentElement.scrollWidth > innerWidth + 1;
    out.list_photo = !!document.querySelector(".qr-product-photo-057b");
    if (!feed) { document.getElementById("layout").textContent = JSON.stringify(out); return; }
    const slide = feed.querySelector(".cxmv-slide");
    const r = slide.getBoundingClientRect();
    out.slide = { w: Math.round(r.width), h: Math.round(r.height) };
    const vis = (el) => { const b = el.getBoundingClientRect(); return b.width > 0 && b.height > 0 && b.top >= 0 && b.bottom <= innerHeight + 0.5 && b.left >= 0 && b.right <= innerWidth + 0.5; };
    const name = slide.querySelector(".cxmv-name");
    const price = slide.querySelector(".cxmv-price");
    const add = slide.querySelector(".cxmv-add");
    const dock = feed.querySelector(".cxmv-dock");
    out.visible = { name: vis(name), price: vis(price), add: vis(add), dock: vis(dock), cats: vis(feed.querySelector(".cxmv-cat")) };
    out.text = { name: name.textContent, price: price.textContent, add: add.textContent, dock: dock.textContent.replace(/\s+/g, " ").trim() };
    const ab = add.getBoundingClientRect();
    const db = dock.getBoundingClientRect();
    out.add_over_dock = !(ab.bottom <= db.top || ab.top >= db.bottom);
    out.add_size = { w: Math.round(ab.width), h: Math.round(ab.height) };
    // contraste del boton (texto sobre su fondo) y del texto blanco sobre lo mas claro del degradado (negro al 65 % sobre blanco)
    out.add_ratio = contrast(rgb(getComputedStyle(add).color), rgb(getComputedStyle(add).backgroundColor));
    out.info_ratio = contrast(rgb(getComputedStyle(name).color), { r: 89, g: 89, b: 89 });
    const videos = Array.from(feed.querySelectorAll("video"));
    out.videos = videos.map((v) => !!v.getAttribute("src"));
    out.slides = feed.querySelectorAll(".cxmv-slide").length;
    out.card = !!feed.querySelector(".cxmv-card");
    out.kenburns = !!feed.querySelector("img.cxmv-kb");
    out.cats = Array.from(feed.querySelectorAll(".cxmv-cat")).map((c) => c.textContent);
    out.playing = videos[0] ? !videos[0].paused : null;
    out.muted = videos[0] ? videos[0].muted && videos[0].loop && videos[0].hasAttribute("playsinline") : null;
    document.getElementById("layout").textContent = JSON.stringify(out);
  }

  window.addEventListener("load", () => {
    const pre = document.createElement("pre");
    pre.id = "layout";
    pre.hidden = true;
    document.body.appendChild(pre);
    setTimeout(() => {
      if (P.get("add") === "1") document.querySelector(".cxmv-add")?.click();
      setTimeout(measure, 600);
    }, 2500);
  });
})();
