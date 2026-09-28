/* CLONEXA 049J/049K: carta que abre el QR impreso del local (solo lectura).
 *
 * Misma vista visual del mesero, la caja y los domicilios (CxMenuKit), en
 * tres niveles: categoría (con imagen) -> subcategoría (con imagen, si la
 * categoría tiene) -> platos en texto (nombre, presentación y precio). El
 * botón atrás del celular vuelve un nivel y solo sale desde el inicio. El
 * código ?t= del QR es la única credencial; el servidor nunca devuelve
 * costos ni existencias.
 */
(function () {
  "use strict";
  const Kit = window.CxMenuKit;
  const root = document.getElementById("app");
  const token = new URLSearchParams(window.location.search).get("t") || "";
  const state = { data: null, category: "", sub: "", error: "" };
  let nav = { push() {} };

  function h(value) {
    return Kit ? Kit.h(value) : String(value ?? "");
  }

  function money(value) {
    return Kit ? Kit.money(value) : `$${Math.round(Number(value) || 0).toLocaleString("es-CO")}`;
  }

  function currentCategory() {
    return (state.data?.categories || []).find((c) => c.key === state.category) || null;
  }

  function dishListHtml(products) {
    if (!products.length) return `<div class="cq-empty-list">Sin platos por ahora.</div>`;
    return `<ul class="cq-dishes">${products.map((p) => `
      <li><span>${h(p.name)}</span><b>${p.is_portioned && (p.portions || []).length
        ? (p.portions || []).map((x) => `${h(x.label)} ${h(money(x.price))}`).join(" · ")
        : h(money(p.price))}</b></li>`).join("")}</ul>`;
  }

  function levelHtml(opts) {
    const category = currentCategory();
    if (!category) return Kit.categoryGridHtml(state.data.categories || [], { ...opts, attr: "data-cq-cat" });
    const subs = category.subcategories || [];
    const sub = subs.find((s) => s.key === state.sub);
    if (sub) return `<h2 class="cq-cat-title">${h(sub.label)}</h2>${dishListHtml(sub.products || [])}`;
    const loose = subs.length ? (category.products || []).filter((p) => !p.subcategory_key) : category.products || [];
    return `
      <h2 class="cq-cat-title">${h(category.label)}</h2>
      ${subs.length ? Kit.categoryGridHtml(subs, { ...opts, attr: "data-cq-sub" }) : ""}
      ${loose.length || !subs.length ? dishListHtml(loose) : ""}`;
  }

  function render() {
    if (state.error) {
      root.innerHTML = `<section class="cq-shell"><div class="cq-empty"><strong>${h(state.error)}</strong><p>Pide la carta al personal del local.</p></div></section>`;
      return;
    }
    if (!state.data) return;
    const opts = { companyId: state.data.company_id, emojis: state.data.menu_emojis };
    const inside = Boolean(currentCategory());
    root.innerHTML = `
      <section class="cq-shell">
        <header class="cq-head">
          <h1>${h(state.data.company_name || "Carta")}</h1>
          ${inside ? `<button class="cq-back" type="button" data-cq-back>← Atrás</button>` : `<p>Nuestra carta</p>`}
        </header>
        ${levelHtml(opts)}
      </section>`;
  }

  function show(next) {
    state.category = (next && next.category) || "";
    state.sub = (next && next.sub) || "";
    render();
    window.scrollTo(0, 0);
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
    } catch (error) {
      state.error = error.message || "No se pudo abrir la carta.";
    }
    render();
  }

  document.addEventListener("click", (event) => {
    const cat = event.target.closest("[data-cq-cat]");
    if (cat) {
      show({ category: cat.getAttribute("data-cq-cat"), sub: "" });
      nav.push();
      return;
    }
    const sub = event.target.closest("[data-cq-sub]");
    if (sub) {
      show({ category: state.category, sub: sub.getAttribute("data-cq-sub") });
      nav.push();
      return;
    }
    if (event.target.closest("[data-cq-back]")) window.history.back();
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
    .cq-dishes{list-style:none;margin:0;padding:0;display:grid;gap:8px}
    .cq-dishes li{display:flex;justify-content:space-between;align-items:baseline;gap:12px;padding:14px 16px;border-radius:14px;background:rgba(255,255,255,.06);font-size:16px}
    .cq-dishes li b{color:#ffd166;white-space:nowrap}
    .cq-empty-list{opacity:.7;padding:16px 0}
    .cq-empty{min-height:60vh;display:grid;place-items:center;text-align:center}
    .wtr-grid-cat{padding:0 0 16px}
  `;
  document.head.appendChild(style);
  if (Kit) {
    Kit.injectStyles();
    nav = Kit.backNav({ read: () => ({ category: state.category, sub: state.sub }), apply: show });
  }
  load();
})();
