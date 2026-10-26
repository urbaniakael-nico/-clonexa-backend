// Carta en video del QR de la mesa (interruptor carta_video, por empresa).
// Platos en pantalla completa vertical que se pasan deslizando; el video
// arranca solo, sin sonido y en bucle; nombre, precio y "Agregar" siempre
// visibles; arriba las categorías para saltar. "Agregar" llama a la MISMA
// función del carrito de la carta en lista (quien monta pasa onAdd).
// Rendimiento: solo el video visible y el siguiente tienen src (portada
// primero); con "ahorro de datos" o "reducir movimiento", solo fotos.
// Plato sin video: su foto con movimiento suave; sin foto: tarjeta con nombre
// y precio (nunca un hueco). Capas: encima de la lista y su barra (900), debajo
// del panel del pedido (999/1000) y de la bienvenida (2000).
(() => {
  "use strict";

  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");

  function lite() {
    try {
      if (navigator.connection && navigator.connection.saveData === true) return true;
    } catch (_) {}
    try {
      return Boolean(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    } catch (_) {
      return false;
    }
  }

  function injectStyles() {
    if (document.getElementById("cxMvFeedStyles")) return;
    const style = document.createElement("style");
    style.id = "cxMvFeedStyles";
    style.textContent = `
      .cxmv-feed{position:fixed;inset:0;z-index:950;background:#000;color:#fff;font-family:inherit;display:block}
      .cxmv-feed[hidden]{display:none}
      .cxmv-scroll{position:absolute;inset:0;overflow-y:auto;scroll-snap-type:y mandatory;overscroll-behavior:contain;-webkit-overflow-scrolling:touch;scrollbar-width:none}
      .cxmv-scroll::-webkit-scrollbar{display:none}
      .cxmv-slide{position:relative;height:100%;min-height:100%;scroll-snap-align:start;scroll-snap-stop:always;overflow:hidden;background:#000}
      .cxmv-media{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;background:#000}
      .cxmv-kb{animation:cxmv-kb 7s ease-in-out infinite alternate;transform-origin:50% 55%}
      @keyframes cxmv-kb{from{transform:scale(1) translate3d(0,0,0)}to{transform:scale(1.12) translate3d(-2%,-1%,0)}}
      .cxmv-card{position:absolute;inset:0;display:grid;place-items:center;padding:32px;text-align:center;background:radial-gradient(circle at 50% 35%,var(--cxmv-accent,#7c3aed) 0,#0b0716 70%)}
      .cxmv-card strong{font-size:clamp(28px,9vw,44px);line-height:1.1;text-shadow:0 2px 12px rgba(0,0,0,.5)}
      .cxmv-top{position:absolute;top:0;left:0;right:0;z-index:2;display:flex;gap:8px;align-items:center;padding:calc(10px + env(safe-area-inset-top)) 12px 26px;background:linear-gradient(180deg,rgba(0,0,0,.78),transparent)}
      .cxmv-cats{display:flex;gap:8px;overflow-x:auto;flex:1;scrollbar-width:none}
      .cxmv-cats::-webkit-scrollbar{display:none}
      .cxmv-cat{flex:none;min-height:40px;padding:0 14px;border-radius:999px;border:1px solid rgba(255,255,255,.55);background:rgba(0,0,0,.55);color:#fff;font-weight:800;font-size:13px;letter-spacing:.02em;cursor:pointer}
      .cxmv-cat.on{background:#fff;color:#111;border-color:#fff}
      .cxmv-list{flex:none;min-height:40px;padding:0 12px;border-radius:999px;border:1px solid rgba(255,255,255,.55);background:rgba(0,0,0,.55);color:#fff;font-weight:800;font-size:13px;cursor:pointer}
      .cxmv-info{position:absolute;left:0;right:0;bottom:0;z-index:2;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 12px;align-items:end;padding:64px 16px calc(92px + env(safe-area-inset-bottom));background:linear-gradient(0deg,rgba(0,0,0,.9) 0,rgba(0,0,0,.65) 55%,transparent)}
      .cxmv-name{grid-column:1;margin:0;font-size:clamp(22px,6.4vw,30px);line-height:1.12;font-weight:900;text-shadow:0 1px 8px rgba(0,0,0,.6)}
      .cxmv-desc{grid-column:1;margin:0;color:#e4e4e7;font-size:14px;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
      .cxmv-price{grid-column:1;font-size:20px;font-weight:900;color:#fff}
      .cxmv-add{grid-column:2;grid-row:1/span 3;align-self:end;min-height:52px;min-width:120px;padding:0 18px;border-radius:999px;border:0;background:var(--cxmv-accent,#fff);color:var(--cxmv-accent-text,#111);font-size:16px;font-weight:900;cursor:pointer;box-shadow:0 8px 24px rgba(0,0,0,.45)}
      .cxmv-add:focus-visible,.cxmv-cat:focus-visible,.cxmv-list:focus-visible,.cxmv-dock:focus-visible,.cxmv-switch:focus-visible{outline:3px solid #fff;outline-offset:2px}
      .cxmv-add[disabled]{opacity:.55}
      .cxmv-qty{display:inline-grid;place-items:center;min-width:24px;height:24px;margin-left:6px;padding:0 6px;border-radius:999px;background:rgba(0,0,0,.85);color:#fff;font-size:13px}
      .cxmv-dock{position:absolute;left:12px;right:12px;bottom:calc(12px + env(safe-area-inset-bottom));z-index:3;display:flex;justify-content:space-between;align-items:center;gap:10px;min-height:56px;padding:0 18px;border-radius:18px;border:1px solid rgba(255,255,255,.35);background:rgba(10,10,14,.88);color:#fff;font-weight:800;font-size:15px;cursor:pointer;-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px)}
      .cxmv-dock b{font-size:16px}
      .cxmv-toast{position:absolute;left:16px;right:16px;top:calc(70px + env(safe-area-inset-top));z-index:4;padding:12px 14px;border-radius:14px;background:rgba(10,10,14,.92);border:1px solid rgba(255,255,255,.35);font-weight:700}
      .cxmv-toast.err{border-color:#f87171}
      .cxmv-hint{position:absolute;right:16px;bottom:calc(170px + env(safe-area-inset-bottom));z-index:2;font-size:12px;color:#e4e4e7;opacity:.85;pointer-events:none}
      .cxmv-switch{position:fixed;left:12px;bottom:calc(84px + env(safe-area-inset-bottom));z-index:45;min-height:44px;padding:0 16px;border-radius:999px;border:1px solid rgba(255,255,255,.5);background:rgba(10,10,14,.9);color:#fff;font-weight:800;cursor:pointer;box-shadow:0 8px 24px rgba(0,0,0,.4)}
      .cxmv-switch[hidden]{display:none}
      @media (prefers-reduced-motion: reduce){.cxmv-kb{animation:none}.cxmv-scroll{scroll-behavior:auto}}
      @media (min-width:700px){.cxmv-slide .cxmv-media{object-fit:contain}.cxmv-info{padding-left:max(16px,calc(50vw - 300px));padding-right:max(16px,calc(50vw - 300px))}}
    `;
    document.head.appendChild(style);
  }

  // Grupos por categoria en el orden en que llegan los platos.
  function group(items) {
    const order = [];
    const seen = new Set();
    items.forEach((item) => {
      const cat = item.category || "Carta";
      if (!seen.has(cat)) { seen.add(cat); order.push(cat); }
    });
    return order.map((cat) => ({ cat, items: items.filter((i) => (i.category || "Carta") === cat) }));
  }

  function slideHtml(item, index, useVideo) {
    let visual;
    if (useVideo && item.video_url) {
      visual = `<video class="cxmv-media" muted loop playsinline preload="none" poster="${h(item.poster_url || item.photo_url || "")}" data-src="${h(item.video_url)}" aria-hidden="true"></video>`;
    } else if (item.poster_url || item.photo_url) {
      visual = `<img class="cxmv-media cxmv-kb" ${index < 2 ? "" : 'loading="lazy"'} src="${h(item.photo_url || item.poster_url)}" alt="">`;
    } else {
      visual = `<div class="cxmv-card" aria-hidden="true"><strong>${h(item.name)}</strong></div>`;
    }
    return `<section class="cxmv-slide" data-cxmv-index="${index}" data-cxmv-cat="${h(item.category || "Carta")}" aria-label="${h(item.name)}">
      ${visual}
      <div class="cxmv-info">
        <h2 class="cxmv-name">${h(item.name)}</h2>
        ${item.description ? `<p class="cxmv-desc">${h(item.description)}</p>` : ""}
        <span class="cxmv-price" data-cxmv-price></span>
        <button type="button" class="cxmv-add" data-cxmv-add="${h(item.id)}" ${item.active === false ? "disabled" : ""}>${item.active === false ? "Agotado" : "Agregar +"}</button>
      </div>
    </section>`;
  }

  function mount(options) {
    injectStyles();
    const opts = options || {};
    const useVideo = !lite();
    const items = (opts.items || []).filter((i) => i && i.id);
    const groups = group(items);
    const flat = groups.flatMap((g) => g.items);
    const root = document.createElement("div");
    root.className = "cxmv-feed";
    root.setAttribute("role", "region");
    root.setAttribute("aria-label", "Carta en video");
    if (opts.accent) root.style.setProperty("--cxmv-accent", opts.accent);
    if (opts.accentText) root.style.setProperty("--cxmv-accent-text", opts.accentText);
    root.innerHTML = `
      <div class="cxmv-top">
        <nav class="cxmv-cats" aria-label="Categorías">${groups.map((g, i) => `<button type="button" class="cxmv-cat ${i === 0 ? "on" : ""}" data-cxmv-jump="${h(g.cat)}">${h(g.cat)}</button>`).join("")}</nav>
        <button type="button" class="cxmv-list" data-cxmv-list aria-label="Ver la carta en lista">☰ Lista</button>
      </div>
      <div class="cxmv-scroll" data-cxmv-scroll>${flat.map((item, i) => slideHtml(item, i, useVideo)).join("")}</div>
      ${flat.length > 1 ? `<span class="cxmv-hint" data-cxmv-hint>Desliza ↑ para ver más</span>` : ""}
      <div class="cxmv-toast" data-cxmv-toast hidden></div>
      <button type="button" class="cxmv-dock" data-cxmv-cart><span data-cxmv-cart-label>Tu pedido</span><b data-cxmv-cart-total></b></button>`;
    document.body.appendChild(root);

    const scroller = root.querySelector("[data-cxmv-scroll]");
    const slides = Array.from(root.querySelectorAll(".cxmv-slide"));
    let active = 0;

    function setSrc(index, on) {
      const video = slides[index] && slides[index].querySelector("video[data-src]");
      if (!video) return;
      if (on && !video.getAttribute("src")) {
        video.setAttribute("src", video.getAttribute("data-src"));
        video.preload = index === active ? "auto" : "metadata";
      } else if (!on && video.getAttribute("src")) {
        video.pause();
        video.removeAttribute("src");
        try { video.load(); } catch (_) {}
      }
    }

    // Solo el visible y el siguiente: lo demas se descarga (memoria y datos).
    function activate(index) {
      active = Math.max(0, Math.min(slides.length - 1, index));
      slides.forEach((_s, i) => setSrc(i, i === active || i === active + 1));
      slides.forEach((slide, i) => {
        const video = slide.querySelector("video");
        if (!video) return;
        if (i === active && !root.hidden) {
          const play = video.play && video.play();
          if (play && play.catch) play.catch(() => {});
        } else if (video.pause) video.pause();
      });
      const cat = slides[active] && slides[active].getAttribute("data-cxmv-cat");
      root.querySelectorAll("[data-cxmv-jump]").forEach((b) => {
        const on = b.getAttribute("data-cxmv-jump") === cat;
        b.classList.toggle("on", on);
        if (on && b.scrollIntoView && b.parentElement) {
          const box = b.parentElement;
          box.scrollLeft = Math.max(0, b.offsetLeft - box.clientWidth / 2 + b.clientWidth / 2);
        }
      });
      if (active > 0) { const hint = root.querySelector("[data-cxmv-hint]"); if (hint) hint.remove(); }
    }

    let observer = null;
    if (typeof IntersectionObserver === "function") {
      observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting && entry.intersectionRatio >= 0.6) activate(Number(entry.target.getAttribute("data-cxmv-index")));
        });
      }, { root: scroller, threshold: [0.6] });
      slides.forEach((s) => observer.observe(s));
    } else {
      scroller.addEventListener("scroll", () => activate(Math.round(scroller.scrollTop / Math.max(1, scroller.clientHeight))));
    }

    root.addEventListener("click", (event) => {
      const t = event.target;
      if (!t || !t.closest) return;
      const add = t.closest("[data-cxmv-add]");
      if (add && !add.disabled) { if (opts.onAdd) opts.onAdd(add.getAttribute("data-cxmv-add")); return; }
      const jump = t.closest("[data-cxmv-jump]");
      if (jump) {
        const target = slides.find((s) => s.getAttribute("data-cxmv-cat") === jump.getAttribute("data-cxmv-jump"));
        if (target) { scroller.scrollTop = target.offsetTop; activate(Number(target.getAttribute("data-cxmv-index"))); }
        return;
      }
      if (t.closest("[data-cxmv-list]")) { if (opts.onList) opts.onList(); return; }
      if (t.closest("[data-cxmv-cart]") && opts.onCart) opts.onCart();
    });

    function update(state) {
      const s = state || {};
      const money = opts.money || ((v) => String(v));
      slides.forEach((slide, i) => {
        const item = flat[i];
        const price = slide.querySelector("[data-cxmv-price]");
        if (price) price.textContent = Number(item.price || 0) > 0 ? money(item.price) : "Por confirmar";
        const button = slide.querySelector("[data-cxmv-add]");
        const qty = opts.qty ? Number(opts.qty(item.id) || 0) : 0;
        if (button && item.active !== false) button.innerHTML = qty > 0 ? `Agregar +<span class="cxmv-qty" aria-label="${h(qty)} en tu pedido">${h(s.qtyText ? s.qtyText(qty) : qty)}</span>` : "Agregar +";
      });
      const label = root.querySelector("[data-cxmv-cart-label]");
      const total = root.querySelector("[data-cxmv-cart-total]");
      if (label) label.textContent = s.count > 0 ? `Tu pedido · ${s.count} ${s.count === 1 ? "producto" : "productos"}` : "Tu pedido";
      if (total) total.textContent = s.count > 0 ? `${s.total > 0 ? money(s.total) : "Ver"} →` : "Abrir →";
      const toast = root.querySelector("[data-cxmv-toast]");
      if (toast) {
        const text = s.error || s.message || "";
        toast.hidden = !text;
        toast.textContent = text;
        toast.classList.toggle("err", Boolean(s.error));
      }
    }

    // Con la carta en video encima, la lista de fondo no se desplaza.
    function lockPage(on) {
      const html = document.documentElement;
      if (html && html.style) html.style.overflow = on ? "hidden" : "";
    }

    function show() {
      lockPage(true);
      if (!root.hidden) return;
      root.hidden = false;
      activate(active);
    }

    function hide() {
      lockPage(false);
      if (root.hidden) return;
      root.hidden = true;
      slides.forEach((s) => { const v = s.querySelector("video"); if (v && v.pause) v.pause(); });
    }

    function destroy() {
      lockPage(false);
      if (observer) observer.disconnect();
      root.remove();
    }

    lockPage(true);
    activate(0);
    return { root, update, show, hide, destroy, activate, get active() { return active; }, items: flat, useVideo };
  }

  // Boton flotante para volver a la carta en video desde la lista.
  function switchButton(onClick) {
    injectStyles();
    let button = document.querySelector("[data-cxmv-switch]");
    if (!button) {
      button = document.createElement("button");
      button.type = "button";
      button.className = "cxmv-switch";
      button.setAttribute("data-cxmv-switch", "");
      button.textContent = "▶ Carta en video";
      button.addEventListener("click", () => onClick && onClick());
      document.body.appendChild(button);
    }
    return button;
  }

  window.CxMenuVideoFeed = { mount, switchButton, group, lite };
})();
