// Vista previa de la carta QR nueva (057C) sin servidor: /carta-qr y /ordenar
// (Mesa 4) con datos de ejemplo y medios en /__mv/ (tests/fixtures/menu_video).
// ?brand=brasa|azul (dos marcas distintas), ?video=0 (carta_video apagado),
// ?broken=1 (el primer video no existe: debe quedar su portada),
// ?view=home|video|list|cart|detail. Mide en <pre id="layout">.
(() => {
  const P = new URLSearchParams(location.search);
  const CID = P.get("company_id") || "57c00000-0000-4000-8000-0000000b4a5a";
  const VIDEO = P.get("video") !== "0";
  const BRANDS = {
    brasa: { name: "Brasa & Maíz (demo)", theme: { primary: "#e4572e", secondary: "#ffc857", bg: "#1b1220", text: "#ffffff", font: "Manrope, Trebuchet MS, system-ui, sans-serif",
      background: "radial-gradient(circle at 12% 8%, #e4572e66, transparent 34%), radial-gradient(circle at 88% 12%, #ffc85744, transparent 34%), linear-gradient(135deg, #1b1220, #050509)" } },
    azul: { name: "Mar Azul (demo)", theme: { primary: "#1f6feb", secondary: "#0ea5a4", bg: "#eef3f8", text: "#0f172a", font: "Inter, system-ui, sans-serif",
      background: "radial-gradient(circle at 0% 0%, #0ea5a422, transparent 32%), radial-gradient(circle at 100% 0%, #1f6feb12, transparent 32%), linear-gradient(135deg, #f8fafc, #e2e8f0)" } },
  };
  const B = BRANDS[P.get("brand") || "brasa"];
  const D = (id, name, price, cat, media, extra = {}) => ({ id, name, price, category_key: cat, category_label: cat.toUpperCase(), subcategory_label: "",
    description: extra.description || "", photo_url: media ? `/__mv/${media}-remaster.webp` : "", video_url: VIDEO && media ? `/__mv/${media}.mp4` : "",
    poster_url: VIDEO && media ? `/__mv/${media}-poster.webp` : "", requires_term: !!extra.term, quick_notes: extra.notes || [], allows_portions: false });
  const products = [
    D("p1", "Lomo a la parrilla", 46000, "fuertes", "lomo-a-la-parrilla", { description: "300 gr de lomo con verduras salteadas y salsa de pimienta.", term: true, notes: ["Sin sal", "Salsa aparte"] }),
    D("p2", "Hamburguesa de la casa", 32000, "fuertes", "hamburguesa-de-la-casa", { description: "Doble carne, queso cheddar, tocineta y salsa de la casa.", term: true }),
    D("p3", "Salmón a la plancha", 49000, "fuertes", "salmon-a-la-plancha", { description: "Filete de salmón con pimentones asados y crema de eneldo." }),
    D("p4", "Ceviche de pescado", 24000, "entradas", "ceviche-de-pescado", { description: "Pescado blanco curado en limón con cebolla morada, cilantro y ají." }),
    D("p5", "Nachos con guacamole", 21000, "entradas", "nachos-con-guacamole", { description: "Totopos crocantes, queso fundido, pico de gallo y guacamole." }),
    D("p6", "Limonada de pepino", 9500, "bebidas", "limonada-de-hierbabuena", { description: "Limonada natural con pepino y hierbabuena." }),
    D("p7", "Capuchino", 7000, "bebidas", "capuchino", { description: "Café de origen con leche espumada." }),
    D("p8", "Torta de chocolate", 14000, "postres", "torta-de-chocolate", { description: "Torta húmeda de chocolate con cobertura de frutos rojos." }),
    D("p9", "Agua con gas", 5000, "bebidas", null, {}),
  ];
  if (P.get("broken") === "1") products[3].video_url = "/__mv/no-existe.mp4"; // el primero que se ve (ENTRADAS)
  const cover = (k) => { const p = products.find((x) => x.category_key === k && (x.poster_url || x.photo_url)); return p ? (p.poster_url || p.photo_url) : ""; };
  const cats = ["entradas", "fuertes", "bebidas", "postres"].map((k) => ({ key: k, label: k.toUpperCase(), count: products.filter((p) => p.category_key === k).length, image_url: cover(k) }));
  const APP = { company: { id: CID, name: B.name, logo_url: "" }, theme: B.theme, video: VIDEO, terms: ["Crudo", "Medio", "3/4", "Bien cocinado"],
    categories: cats, products, top: ["p1", "p4", "p2", "p8"], top_source: "ventas", locale: { currency: "COP", language: "es", decimals: 0 } };
  window.__CXA_ORDERS__ = [];
  const json = (b, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
  const real = window.fetch.bind(window);
  try { localStorage.setItem(`clonexa_hsp_table_access_${CID}_mesa_4`, "ABC12"); } catch (_) {}
  const iso = (ms) => new Date(Date.now() + ms).toISOString();
  window.fetch = async (url, opts = {}) => {
    const u = String(url);
    if (!u.includes("/api/v1")) return real(url, opts);
    const p = u.slice(u.indexOf("/api/v1") + 7).split("?")[0];
    if (p.startsWith("/carta/public/")) return json({ company_id: CID, company_name: B.name, categories: [], app: APP });
    if (p === `/domicilios/public/${CID}`) return json({ ok: true, company_name: B.name, categories: [], quantity_buttons: [], menu_emojis: false, delivery_fee: 4000,
      eta_minutes: 40, has_payment_qr: false, expires_at: iso(1800000), phone_hint: "***1234", whatsapp_location: false, checkout_v2: true, app: APP });
    if (p === `/menu-video/qr/${CID}/carta`) return json({ ...APP, table: "Mesa 4" });
    if (p === `/companies/${CID}`) return json({ id: CID, name: B.name });
    if (p === `/companies/${CID}/branding`) return json({ branding: { primary_color: B.theme.primary } });
    if (p.endsWith("/qr-tables/access")) return json({ ok: true, access: { active: true, expires_at: iso(3600000) }, company_name: B.name, ui: { bar_menu: false } });
    if (p.endsWith("/qr-tables/access/verify")) return json({ ok: true, access: { active: true, expires_at: iso(3600000) } });
    if (p.endsWith("/qr-tables/account")) return json({ ok: true, account: { total: 61000, orders_count: 2, accounts_count: 1, items: [], accounts: [] } });
    if (p.includes("/inventory-lite")) return json({ inventory: products.map((x) => ({ ...x, active: true })), carta_video: VIDEO, carta_app: true });
    if (p.endsWith("/orders") && (opts.method || "GET") === "POST") { window.__CXA_ORDERS__.push({ path: p, body: JSON.parse(opts.body) }); return json({ order: { order_number: "QR-21" } }); }
    if (p.includes("/loyalty-campaigns/active")) return json({ ok: true, campaign: null });
    return json({});
  };

  function rgb(v) { const m = String(v || "").match(/rgba?\(([^)]+)\)/); if (!m) return null; const [r, g, b, a = 1] = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return { r, g, b, a }; }
  function L({ r, g, b }) { const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); }
  function bgOf(el) {
    const layers = [];
    for (let n = el; n; n = n.parentElement) { const c = rgb(getComputedStyle(n).backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } }
    const base = rgb(getComputedStyle(document.querySelector(".cxa")).backgroundColor) || { r: 0, g: 0, b: 0 };
    let out = base;
    for (let i = layers.length - 1; i >= 0; i -= 1) { const l = layers[i]; out = { r: l.r * l.a + out.r * (1 - l.a), g: l.g * l.a + out.g * (1 - l.a), b: l.b * l.a + out.b * (1 - l.a) }; }
    return out;
  }
  function ratioOf(el) { const fg = rgb(getComputedStyle(el).color); const bg = bgOf(el); const a = L(fg) + 0.05; const b = L(bg) + 0.05; return Math.round((Math.max(a, b) / Math.min(a, b)) * 100) / 100; }
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const click = (sel) => { const el = document.querySelector(sel); if (el) el.click(); return !!el; };

  async function drive() {
    const view = P.get("view") || "home";
    const out = { view, vw: innerWidth };
    for (let i = 0; i < 40 && !document.querySelector(".cxa"); i += 1) await wait(100);
    const app = document.querySelector(".cxa");
    out.mounted = !!app;
    if (!app) { document.getElementById("layout").textContent = JSON.stringify(out); return; }
    if (view === "video") { click("[data-cxa-video]"); await wait(1500); }
    if (view === "list") { click('[data-cxa-cat="fuertes"]'); await wait(300); }
    if (view === "detail") { click("[data-cxa-video]"); await wait(400); click('[data-cxa-detail="p1"]'); await wait(300); }
    if (view === "cart") {
      click('[data-cxa-cat="fuertes"]'); await wait(200);
      click('[data-cxa-add="p1"]'); await wait(200); // pide el término
      click('[data-cxa-term="p1"][data-v="3/4"]'); await wait(100);
      click('[data-cxa-note="p1"][data-v="Salsa aparte"]'); await wait(100);
      click('.cxa-sheet [data-cxa-add="p1"]'); await wait(200);
      click('[data-cxa-add="p3"]'); await wait(200);
      click("[data-cxa-cart]"); await wait(200);
      const note = document.querySelector("[data-cxa-lnote]");
      if (note) { note.value = "Bien caliente"; note.dispatchEvent(new Event("input", { bubbles: true })); }
      if (P.get("send") === "1") { click("[data-cxa-send]"); await wait(800); }
    }
    // lo que ve el cliente es la carta (encima de la pagina de siempre): se mide ella
    const box = document.querySelector(".cxa .cxa-scroll");
    const wide = [...document.querySelectorAll(".cxa *")].filter((el) => { const r = el.getBoundingClientRect(); return r.width && !el.closest(".cxa-top,.cxa-chips,.cxa-kb") && (r.right > innerWidth + 1 || r.left < -1); });
    out.overflow_by = wide.slice(0, 4).map((el) => `${el.tagName}.${el.className}`);
    out.page_overflow = wide.length > 0 || (box ? box.scrollWidth > box.clientWidth + 1 : false);
    out.text = document.querySelector(".cxa").innerText.replace(/\s+/g, " ").slice(0, 900);
    const dom = document.querySelector(".dom-shell");
    out.dom = dom && dom.offsetParent !== null ? dom.innerText.replace(/\s+/g, " ").slice(0, 400) : "";
    if (out.dom) out.page_overflow = false; // en domicilio, tras "Continuar" se ve el checkout de siempre
    out.app_hidden = document.querySelector(".cxa").hidden;
    const sheetEl = document.querySelector(".cxa-sheet");
    out.sheet = sheetEl ? sheetEl.innerText.replace(/\s+/g, " ") : "";
    const pick = (sel) => { const el = document.querySelector(sel); return el ? ratioOf(el) : null; };
    out.ratios = { name: pick(".cxa-name"), h2: pick(".cxa-h2"), search: pick(".cxa-search input"), chip: pick(".cxa-chip"), item_h3: pick(".cxa-item h3"),
      item_p: pick(".cxa-item p"), price: pick(".cxa-price"), primary: pick(".cxa-btn.primary") || pick(".cxa-plus"), where: pick(".cxa-where"), vcard: pick(".cxa-vcard h2"), sheet: pick(".cxa-sheet h2"), line: pick(".cxa-line b") };
    out.cats = [...document.querySelectorAll(".cxa-cat")].map((c) => ({ label: c.querySelector("b").textContent, img: !!c.querySelector("img") }));
    out.top = document.querySelectorAll(".cxa-tcard").length;
    const img = document.querySelector(".cxa-item img");
    out.list_img = img ? Math.round(img.getBoundingClientRect().width) : null;
    const item = document.querySelector(".cxa-item");
    if (item) { const h3 = item.querySelector("h3").getBoundingClientRect(); const ib = item.getBoundingClientRect(); out.list_title_top = Math.round(h3.top - ib.top); out.list_title_align = getComputedStyle(item.querySelector("h3")).textAlign; }
    const vids = [...document.querySelectorAll(".cxa-slide video")];
    out.video_attrs = vids[0] ? ["muted", "playsinline", "loop", "autoplay"].every((a) => vids[0].hasAttribute(a)) && vids[0].getAttribute("preload") === "metadata" && !!vids[0].getAttribute("poster") : null;
    out.video_src = vids.map((v) => !!v.getAttribute("src"));
    out.slide0 = (() => { const s = document.querySelector(".cxa-slide"); if (!s) return null; const m = s.querySelector(".cxa-media"); return m ? m.tagName : "CARD"; })();
    out.slides = document.querySelectorAll(".cxa-slide").length;
    const vc = document.querySelector(".cxa-vcard");
    if (vc) { const r = vc.getBoundingClientRect(); out.vcard_visible = r.top >= 0 && r.bottom <= innerHeight + 1; }
    const shell = document.querySelector(".cxa-col");
    out.col_width = shell ? Math.round(shell.getBoundingClientRect().width) : null;
    out.orders = window.__CXA_ORDERS__;
    out.palette = window.CxCartaApp && window.CxCartaApp.palette(B.theme).ratios;
    document.getElementById("layout").textContent = JSON.stringify(out);
  }
  window.addEventListener("load", () => {
    const pre = document.createElement("pre"); pre.id = "layout"; pre.hidden = true; document.body.appendChild(pre);
    setTimeout(() => drive().catch((e) => { pre.textContent = JSON.stringify({ error: String(e) }); }), 1500);
  });
})();
