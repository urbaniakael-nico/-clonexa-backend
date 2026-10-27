// Vista previa de QR y piezas (058A) sin servidor: /pedir (Domicilio o Para
// llevar) y /carta-mesero con datos de ejemplo y medios en /__mv/.
// ?kind=domicilio|llevar, ?brand=brasa|azul, ?view=form|done|noconsent|detail,
// ?mesero=1 (&login=0 sin sesion). Mide en <pre id="layout">.
(() => {
  const P = new URLSearchParams(location.search);
  const CID = P.get("company_id") || "58a00000-0000-4000-8000-0000000b4a5a";
  const KIND = P.get("kind") || "domicilio";
  const BRANDS = {
    brasa: { name: "Brasa & Maíz (demo)", theme: { primary: "#e4572e", secondary: "#ffc857", bg: "#1b1220", text: "#ffffff",
      background: "linear-gradient(135deg, #1b1220, #050509)" } },
    azul: { name: "Mar Azul (demo)", theme: { primary: "#1f6feb", secondary: "#0ea5a4", bg: "#eef3f8", text: "#0f172a",
      background: "linear-gradient(135deg, #f8fafc, #e2e8f0)" } },
  };
  const B = BRANDS[P.get("brand") || "brasa"];
  const D = (id, name, price, cat, media, extra = {}) => ({ id, name, price, category_key: cat, category_label: cat.toUpperCase(), subcategory_label: "",
    description: extra.description || "", photo_url: media ? `/__mv/${media}-remaster.webp` : "", video_url: media ? `/__mv/${media}.mp4` : "",
    poster_url: media ? `/__mv/${media}-poster.webp` : "", requires_term: !!extra.term, quick_notes: extra.notes || [], allows_portions: false,
    gallery_urls: extra.gallery || [] });
  const products = [
    D("p1", "Lomo a la parrilla", 46000, "fuertes", "lomo-a-la-parrilla", { description: "300 gr de lomo con verduras salteadas.", term: true,
      gallery: ["/__mv/hamburguesa-de-la-casa-remaster.webp", "/__mv/salmon-a-la-plancha-remaster.webp"] }),
    D("p3", "Salmón a la plancha", 49000, "fuertes", "salmon-a-la-plancha", { description: "Filete de salmón con pimentones asados." }),
    D("p4", "Ceviche de pescado", 24000, "entradas", "ceviche-de-pescado", { description: "Pescado blanco curado en limón." }),
    D("p8", "Torta de chocolate", 14000, "postres", "torta-de-chocolate", { description: "Torta húmeda de chocolate." }),
  ];
  const cats = ["entradas", "fuertes", "postres"].map((k) => ({ key: k, label: k.toUpperCase(), count: products.filter((p) => p.category_key === k).length,
    image_url: (products.find((p) => p.category_key === k) || {}).poster_url || "" }));
  const APP = { company: { id: CID, name: B.name, logo_url: "" }, theme: B.theme, video: true, terms: ["Crudo", "Medio", "3/4", "Bien cocinado"],
    categories: cats, products, top: ["p1", "p4", "p3"], top_source: "ventas", locale: { currency: "COP", language: "es", decimals: 0 } };
  window.__CXP_CALLS__ = [];
  const json = (b, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
  const real = window.fetch.bind(window);
  if (P.get("mesero") === "1" && P.get("login") !== "0") try { localStorage.setItem(`clonexa_waiter_token_${CID}`, "token-mesero"); } catch (_) {}
  if (P.get("login") === "0") {  // sin sesion SOLO en este marco (los marcos comparten localStorage)
    const get = Storage.prototype.getItem;
    Storage.prototype.getItem = function (key) { return String(key).startsWith("clonexa_waiter_token_") ? null : get.call(this, key); };
  }
  window.fetch = async (url, opts = {}) => {
    const u = String(url);
    if (!u.includes("/api/v1")) return real(url, opts);
    const p = u.slice(u.indexOf("/api/v1") + 7).split("?")[0];
    const method = opts.method || "GET";
    if (method !== "GET") window.__CXP_CALLS__.push({ path: p, body: JSON.parse(opts.body || "{}"), auth: (opts.headers || {}).Authorization || "" });
    if (p.startsWith("/carta-links/public/") && p.endsWith("/orders") && method === "POST") {
      return json({ ok: true, kind: KIND, order_id: "o1", order_number: "QR-0101", total: 95000, status: "pendiente", status_text: "Recibido", key: "clave-1234",
        fee_text: KIND === "domicilio" ? "El restaurante te confirma el valor del domicilio." : "" }, 201);
    }
    if (p.startsWith("/carta-links/public/") && p.includes("/orders/")) return json({ ok: true, status: "alistando", status_text: "En preparación" });
    if (p.startsWith("/carta-links/public/")) return json({ ok: true, kind: KIND, label: KIND === "domicilio" ? "Domicilio" : "Para llevar", carta: APP,
      delivery: KIND === "domicilio" ? { module: false, fee: 0, fee_text: "El restaurante te confirma el valor del domicilio." } : null, policy_url: `/politica-de-datos?c=${CID}` });
    if (p === `/carta-links/companies/${CID}/mesero`) {
      if (!(opts.headers || {}).Authorization || (opts.headers || {}).Authorization === "Bearer ") return json({ detail: "No autenticado" }, 401);
      return json({ ok: true, carta: APP, mesero: "Camila", tables: [{ table_number: "Mesa 4", total: 61000, status: "entregada" }, { table_number: "Mesa 7", total: 18000, status: "enviado_a_cocina" }] });
    }
    if (p === `/companies/${CID}/waiter-ordering/orders` && method === "POST") return json({ ok: true, order: { order_number: "M-12" } }, 201);
    return json({});
  };

  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const click = (sel) => { const el = document.querySelector(sel); if (el) el.click(); return !!el; };
  const type = (name, value) => { const el = document.querySelector(`.cxp [name="${name}"]`); if (!el) return; el.value = value; el.dispatchEvent(new Event("input", { bubbles: true })); };

  async function drive() {
    const view = P.get("view") || "form";
    const out = { view };
    for (let i = 0; i < 40 && !document.querySelector(".cxa") && !document.querySelector(".cxp-center"); i += 1) await wait(100);
    out.mounted = !!document.querySelector(".cxa");
    out.stop = (document.querySelector(".cxp-center") || {}).innerText || "";
    if (out.mounted && view === "detail") {
      click('[data-cxa-cat="fuertes"]'); await wait(200); if (!click('[data-cxa-detail="p1"]')) click('[data-cxa-add="p1"]'); await wait(300);
      out.thumbs = document.querySelectorAll(".cxa-sheet [data-cxa-photo]").length;
      click('.cxa-sheet [data-cxa-photo="2"]'); await wait(200);
      out.detail_img = (document.querySelector(".cxa-sheet img") || {}).getAttribute ? document.querySelector(".cxa-sheet img").getAttribute("src") : "";
      out.detail_alt = (document.querySelector(".cxa-sheet img") || {}).alt || "";
    }
    if (out.mounted && view !== "detail") {
      click('[data-cxa-cat="fuertes"]'); await wait(200);
      click('[data-cxa-add="p3"]'); await wait(150); click('[data-cxa-add="p3"]'); await wait(150);
      click('[data-cxa-back], [data-cxa-home]'); await wait(150);
      click("[data-cxa-cart]"); await wait(200);
      const note = document.querySelector("[data-cxa-lnote]");
      if (note) { note.value = "Bien cocido"; note.dispatchEvent(new Event("input", { bubbles: true })); }
      click("[data-cxa-send]"); await wait(400);
      out.form = (document.querySelector(".cxp") || {}).innerText || "";
      out.hp_hidden = (() => { const hp = document.querySelector('.cxp [name="website"]'); if (!hp) return null; const r = hp.getBoundingClientRect(); return r.right < 0 || r.width <= 1; })();
      if (P.get("mesero") === "1") {
        click('[data-cxp-table="Mesa 4"]'); await wait(100); click("[data-cxp-send-table]"); await wait(500);
        out.after = (document.querySelector(".cxa-sheet") || {}).innerText || "";
      } else if (view === "done" || view === "noconsent") {
        type("name", "Laura Gómez"); type("phone", "300 123 4567");
        if (KIND === "domicilio") { type("address", "Calle 10 # 5-20"); type("barrio", "Centro"); type("reference", "Portería"); }
        if (view === "done" && KIND === "domicilio") { const c = document.querySelector('.cxp [name="consent"]'); c.checked = true; c.dispatchEvent(new Event("input", { bubbles: true })); }
        document.querySelector(".cxp [data-cxp-form]").requestSubmit(); await wait(600);
        out.done = (document.querySelector(".cxp") || {}).innerText || "";
      }
    }
    const wide = [...document.querySelectorAll(".cxp *, .cxa *")].filter((el) => { const r = el.getBoundingClientRect(); return r.width && el.offsetParent !== null && !el.closest(".cxp-hp,.cxa-top,.cxa-chips,.cxa-kb,.cxa-thumbs") && (r.right > innerWidth + 1 || r.left < -1); });
    out.overflow_by = wide.slice(0, 4).map((el) => `${el.tagName}.${el.className}`);
    out.page_overflow = wide.length > 0;
    out.calls = window.__CXP_CALLS__;
    document.getElementById("layout").textContent = JSON.stringify(out);
  }
  window.addEventListener("load", () => {
    const pre = document.createElement("pre"); pre.id = "layout"; pre.hidden = true; document.body.appendChild(pre);
    setTimeout(() => drive().catch((e) => { pre.textContent = JSON.stringify({ error: String(e) }); }), 1500);
  });
})();
