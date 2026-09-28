/* CLONEXA 049J: carta que abre el QR impreso del local (solo lectura).
 *
 * Misma vista visual del mesero, la caja y los domicilios (CxMenuKit):
 * categorías con su foto y platos con foto y precio. El código ?t= del QR es
 * la única credencial; el servidor nunca devuelve costos ni existencias.
 */
(function () {
  "use strict";
  const Kit = window.CxMenuKit;
  const root = document.getElementById("app");
  const token = new URLSearchParams(window.location.search).get("t") || "";
  const state = { data: null, category: "", error: "" };

  function h(value) {
    return Kit ? Kit.h(value) : String(value ?? "");
  }

  function money(value) {
    return Kit ? Kit.money(value) : `$${Math.round(Number(value) || 0).toLocaleString("es-CO")}`;
  }

  function productsOf(key) {
    const cat = (state.data?.categories || []).find((c) => c.key === key);
    return cat ? cat.products : [];
  }

  function detailHtml(product) {
    if (!product.is_portioned || !(product.portions || []).length) return "";
    return `<div class="cq-portions">${product.portions.map((p) => `<span>${h(p.label)} · ${h(money(p.price))}</span>`).join("")}</div>`;
  }

  function render() {
    if (state.error) {
      root.innerHTML = `<section class="cq-shell"><div class="cq-empty"><strong>${h(state.error)}</strong><p>Pide la carta al personal del local.</p></div></section>`;
      return;
    }
    if (!state.data) return;
    const opts = { companyId: state.data.company_id, emojis: state.data.menu_emojis };
    const categories = state.data.categories || [];
    const current = state.category;
    root.innerHTML = `
      <section class="cq-shell">
        <header class="cq-head">
          <h1>${h(state.data.company_name || "Carta")}</h1>
          ${current ? `<button class="cq-back" type="button" data-cq-back>← Categorías</button>` : `<p>Nuestra carta</p>`}
        </header>
        ${current
          ? `<h2 class="cq-cat-title">${h((categories.find((c) => c.key === current) || {}).label || "")}</h2>
             ${Kit.productGridHtml(productsOf(current), { ...opts, attr: "data-cq-product" })}
             ${productsOf(current).map((p) => detailHtml(p) ? `<div class="cq-detail"><b>${h(p.name)}</b>${detailHtml(p)}</div>` : "").join("")}`
          : Kit.categoryGridHtml(categories, { ...opts, attr: "data-cq-cat" })}
      </section>`;
  }

  async function load() {
    if (!token) {
      state.error = "Este código QR no es válido.";
      render();
      return;
    }
    try {
      const res = await fetch(`/api/v1/carta/public/${encodeURIComponent(token)}`);
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Esta carta ya no está disponible.");
      state.data = await res.json();
      if ((state.data.categories || []).length === 1) state.category = state.data.categories[0].key;
    } catch (error) {
      state.error = error.message || "No se pudo abrir la carta.";
    }
    render();
  }

  document.addEventListener("click", (event) => {
    const cat = event.target.closest("[data-cq-cat]");
    if (cat) {
      state.category = cat.getAttribute("data-cq-cat");
      render();
      window.scrollTo(0, 0);
      return;
    }
    if (event.target.closest("[data-cq-back]")) {
      state.category = "";
      render();
    }
  });

  const style = document.createElement("style");
  style.textContent = `
    body{background:#080712;color:#fff;font-family:system-ui,-apple-system,Segoe UI,sans-serif}
    .cq-shell{max-width:980px;margin:0 auto;padding:18px 16px 40px}
    .cq-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:14px}
    .cq-head h1{margin:0;font-size:24px}
    .cq-head p{margin:0;opacity:.75}
    .cq-back{min-height:44px;padding:8px 14px;border-radius:999px;border:1px solid rgba(255,255,255,.25);background:rgba(255,255,255,.08);color:#fff;font-weight:800}
    .cq-cat-title{margin:6px 0 12px;font-size:20px}
    .cq-detail{margin-top:10px;padding:10px 12px;border-radius:12px;background:rgba(255,255,255,.06)}
    .cq-portions{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px}
    .cq-portions span{padding:4px 10px;border-radius:999px;background:rgba(255,209,102,.14);color:#ffd166;font-weight:800;font-size:13px}
    .cq-empty{min-height:60vh;display:grid;place-items:center;text-align:center}
    .wtr-prod-tile{cursor:default}
  `;
  document.head.appendChild(style);
  if (Kit) Kit.injectStyles();
  load();
})();
