// Carta QR nueva (057C): la carta que ve el cliente en el QR impreso
// (/carta-qr), en la mesa (/ordenar) y en domicilios (/domicilio) de las
// empresas con Carta. Mobile-first, con la MARCA de cada empresa (la misma del
// portal: fondo branding_background, colores, logo y tipografia) y contraste
// AA calculado. Inicio (buscador, "Lo mas pedido", categorias con imagen),
// modo video (un plato por pantalla), lista y pedido.
//
// No hace pedidos por su cuenta: quien la monta pasa un `adapter` que usa el
// MISMO envio de siempre (mesa: el pedido del QR -> Cocina y cuenta en Caja;
// domicilio: su checkout). Opciones del plato: SOLO las que la Carta tiene
// (termino de coccion y notas rapidas de su categoria).
(() => {
  "use strict";

  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const GOOGLE_FONTS = { Inter: "Inter", Manrope: "Manrope", Poppins: "Poppins", Montserrat: "Montserrat", Sora: "Sora" };

  // ------------------------------------------------------------ color
  function rgbOf(value) {
    const raw = String(value || "").trim();
    let m = raw.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
    if (m) {
      const full = m[1].length === 3 ? m[1].split("").map((c) => c + c).join("") : m[1];
      return [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16));
    }
    m = raw.match(/rgba?\(([^)]+)\)/i);
    if (m) return m[1].split(/[ ,/]+/).slice(0, 3).map(Number);
    return null;
  }
  function lum(rgb) {
    const f = (c) => { const v = c / 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(rgb[0]) + 0.7152 * f(rgb[1]) + 0.0722 * f(rgb[2]);
  }
  function ratio(a, b) {
    const x = lum(a) + 0.05; const y = lum(b) + 0.05;
    return Math.max(x, y) / Math.min(x, y);
  }
  const WHITE = [255, 255, 255];
  const INK = [17, 17, 20];
  const hex = (rgb) => `#${rgb.map((c) => Math.round(Math.max(0, Math.min(255, c))).toString(16).padStart(2, "0")).join("")}`;
  function mix(a, b, t) { return a.map((c, i) => c + (b[i] - c) * t); }

  // Texto sobre un color: blanco o casi negro, el de mas contraste.
  function textOn(rgb) { return ratio(rgb, WHITE) >= ratio(rgb, INK) ? WHITE : INK; }

  // Un color de marca usable como fondo de boton con texto AA (>= 4.5).
  function buttonColors(primary) {
    let base = rgbOf(primary) || [124, 58, 237];
    for (let i = 0; i <= 20; i += 1) {
      const t = textOn(base);
      if (ratio(base, t) >= 4.5) return { bg: hex(base), fg: hex(t) };
      base = mix(base, t === WHITE ? [0, 0, 0] : WHITE, 0.08);
    }
    return { bg: hex(base), fg: hex(textOn(base)) };
  }

  // Paleta de la pantalla: texto segun el fondo de la marca y tarjetas de
  // vidrio que lo garantizan AA aunque el degradado varie.
  function palette(theme) {
    const t = theme || {};
    const base = rgbOf(t.bg) || [12, 10, 20];
    const dark = textOn(base) === WHITE;
    const text = dark ? WHITE : INK;
    const card = dark ? [10, 10, 16] : [255, 255, 255];
    const cardAlpha = 0.66;
    const cardOver = mix(base, card, cardAlpha);
    const muted = mix(text, cardOver, 0.28);
    const btn = buttonColors(t.primary || "#7c3aed");
    const accent = rgbOf(t.secondary) || rgbOf(t.primary) || [124, 58, 237];
    return {
      dark, text: hex(text), muted: hex(ratio(muted, cardOver) >= 4.5 ? muted : text), base: hex(base),
      card: `rgba(${card.join(",")},${cardAlpha})`, cardSolid: hex(cardOver), line: dark ? "rgba(255,255,255,.16)" : "rgba(17,17,20,.14)",
      primary: btn.bg, onPrimary: btn.fg, accent: hex(accent),
      background: t.background || `linear-gradient(160deg, ${hex(base)}, ${hex(mix(base, [0, 0, 0], 0.4))})`,
      font: t.font || "system-ui, -apple-system, Segoe UI, sans-serif",
      ratios: { text: Math.round(ratio(text, cardOver) * 100) / 100, button: Math.round(ratio(rgbOf(btn.bg), rgbOf(btn.fg)) * 100) / 100 },
    };
  }

  // ------------------------------------------------------------ utilidades
  function money(value, locale) {
    const cur = (locale && locale.currency) || "COP";
    const dec = Number((locale && locale.decimals) ?? (cur === "COP" ? 0 : 2));
    try {
      return new Intl.NumberFormat(cur === "COP" ? "es-CO" : undefined, { style: "currency", currency: cur, maximumFractionDigits: dec, minimumFractionDigits: dec }).format(Number(value || 0));
    } catch (_) {
      return `$${Math.round(Number(value || 0)).toLocaleString("es-CO")}`;
    }
  }
  function norm(value) {
    return String(value || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }
  function lite() {
    try { if (navigator.connection && navigator.connection.saveData === true) return true; } catch (_) {}
    return false;
  }
  function reducedMotion() {
    try { return Boolean(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches); } catch (_) { return false; }
  }

  function injectStyles(p) {
    let style = document.getElementById("cxaStyles057C");
    if (!style) {
      style = document.createElement("style");
      style.id = "cxaStyles057C";
      document.head.appendChild(style);
    }
    style.textContent = `
      .cxa{--cxa-text:${p.text};--cxa-muted:${p.muted};--cxa-card:${p.card};--cxa-card-solid:${p.cardSolid};--cxa-line:${p.line};--cxa-primary:${p.primary};--cxa-on-primary:${p.onPrimary};--cxa-accent:${p.accent};
        position:fixed;inset:0;z-index:950;overflow:hidden;color:var(--cxa-text);font-family:${p.font};background:${p.base};-webkit-font-smoothing:antialiased}
      .cxa *{box-sizing:border-box}
      .cxa[hidden]{display:none}
      .cxa-bg{position:absolute;inset:0;background:${p.background};background-size:cover;background-attachment:fixed}
      .cxa-scroll{position:absolute;inset:0;overflow-y:auto;overscroll-behavior:contain;-webkit-overflow-scrolling:touch}
      .cxa-col{position:relative;max-width:480px;margin:0 auto;padding:calc(12px + env(safe-area-inset-top)) 16px calc(104px + env(safe-area-inset-bottom))}
      .cxa-glass{background:var(--cxa-card);-webkit-backdrop-filter:blur(10px) saturate(1.2);backdrop-filter:blur(10px) saturate(1.2);border:1px solid var(--cxa-line)}
      @supports not ((backdrop-filter:blur(1px)) or (-webkit-backdrop-filter:blur(1px))){.cxa-glass{background:var(--cxa-card-solid)}}
      .cxa-head{display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:20px}
      .cxa-logo{width:48px;height:48px;border-radius:14px;object-fit:contain;background:rgba(255,255,255,.9);flex:none}
      .cxa-logo-fb{display:grid;place-items:center;width:48px;height:48px;border-radius:14px;flex:none;background:var(--cxa-primary);color:var(--cxa-on-primary);font-weight:900;font-size:22px}
      .cxa-name{flex:1;min-width:0;margin:0;font-size:19px;line-height:1.15;font-weight:800;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .cxa-where{flex:none;padding:7px 12px;border-radius:999px;background:var(--cxa-primary);color:var(--cxa-on-primary);font-weight:800;font-size:13px}
      .cxa-search{position:relative;display:block;margin:14px 0 6px}
      .cxa-search input{width:100%;min-height:48px;padding:0 16px 0 44px;border-radius:16px;font:inherit;font-size:16px;color:var(--cxa-text);outline:none}
      .cxa-search input::placeholder{color:var(--cxa-muted)}
      .cxa-search input:focus-visible{outline:3px solid var(--cxa-accent);outline-offset:2px}
      .cxa-search svg{position:absolute;left:14px;top:50%;transform:translateY(-50%);width:20px;height:20px;fill:none;stroke:var(--cxa-text);stroke-width:2;opacity:.85}
      .cxa-h2{margin:22px 4px 10px;font-size:18px;font-weight:800;display:flex;justify-content:space-between;align-items:baseline;gap:8px}
      .cxa-h2 small{font-size:13px;font-weight:600;color:var(--cxa-muted)}
      .cxa-top{display:flex;gap:10px;overflow-x:auto;scroll-snap-type:x mandatory;padding:2px 2px 6px;margin:0 -2px;scrollbar-width:none}
      .cxa-top::-webkit-scrollbar{display:none}
      .cxa-tcard{position:relative;flex:none;width:132px;aspect-ratio:9/15;border-radius:18px;overflow:hidden;scroll-snap-align:start;border:0;padding:0;color:#fff;background:#111;cursor:pointer;text-align:left}
      .cxa-tcard img,.cxa-tcard video{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
      .cxa-tcard span{position:absolute;left:0;right:0;bottom:0;padding:34px 10px 10px;background:linear-gradient(0deg,rgba(0,0,0,.88),rgba(0,0,0,.55) 60%,transparent);display:grid;gap:2px}
      .cxa-tcard b{font-size:14px;line-height:1.15;color:#fff}
      .cxa-tcard i{font-style:normal;font-size:13px;font-weight:800;color:#fff}
      .cxa-cats{display:grid;grid-template-columns:1fr 1fr;gap:12px}
      .cxa-cat{position:relative;aspect-ratio:1/1;border-radius:20px;overflow:hidden;border:0;padding:0;cursor:pointer;background:var(--cxa-card-solid);color:#fff;text-align:left}
      .cxa-cat img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
      .cxa-cat span{position:absolute;left:0;right:0;bottom:0;padding:40px 12px 12px;background:linear-gradient(0deg,rgba(0,0,0,.86),rgba(0,0,0,.5) 55%,transparent);display:grid;gap:2px}
      .cxa-cat b{font-size:16px;letter-spacing:.02em;color:#fff}
      .cxa-cat i{font-style:normal;font-size:13px;color:#f4f4f5}
      .cxa-cat.noimg span{position:absolute;inset:0;align-content:end;background:linear-gradient(150deg,var(--cxa-primary),var(--cxa-accent))}
      .cxa-cat.noimg b,.cxa-cat.noimg i{color:var(--cxa-on-primary)}
      .cxa-btn{min-height:48px;padding:0 16px;border-radius:16px;border:1px solid var(--cxa-line);font:inherit;font-weight:800;font-size:15px;cursor:pointer;color:var(--cxa-text);background:var(--cxa-card)}
      .cxa-btn.primary{background:var(--cxa-primary);color:var(--cxa-on-primary);border-color:transparent}
      .cxa-btn:focus-visible,.cxa-cat:focus-visible,.cxa-tcard:focus-visible,.cxa-chip:focus-visible,.cxa-ic:focus-visible{outline:3px solid var(--cxa-accent);outline-offset:2px}
      .cxa-btn[disabled]{opacity:.55;cursor:not-allowed}
      .cxa-bar{position:absolute;left:0;right:0;bottom:0;z-index:5;padding:10px 16px calc(12px + env(safe-area-inset-bottom));pointer-events:none}
      .cxa-bar-in{max-width:480px;margin:0 auto;display:flex;gap:10px;pointer-events:auto;padding:8px;border-radius:22px}
      .cxa-bar-in .cxa-btn{flex:1}
      .cxa-bar-in .cxa-btn.primary{flex:1.3;display:flex;justify-content:space-between;align-items:center;gap:8px}
      .cxa-count{display:inline-grid;place-items:center;min-width:26px;height:26px;padding:0 7px;border-radius:999px;background:var(--cxa-on-primary);color:var(--cxa-primary);font-size:13px}
      .cxa-chips{display:flex;gap:8px;overflow-x:auto;scrollbar-width:none;padding:2px}
      .cxa-chips::-webkit-scrollbar{display:none}
      .cxa-row1 .cxa-chips{flex:1;min-width:0}
      .cxa-chip{flex:none;min-height:40px;padding:0 14px;border-radius:999px;border:1px solid var(--cxa-line);background:var(--cxa-card);color:var(--cxa-text);font:inherit;font-weight:700;font-size:14px;cursor:pointer}
      .cxa-chip.on{background:var(--cxa-primary);color:var(--cxa-on-primary);border-color:transparent}
      .cxa-topbar{position:sticky;top:0;z-index:3;display:grid;gap:10px;padding:calc(10px + env(safe-area-inset-top)) 0 10px;margin:calc(-12px - env(safe-area-inset-top)) -16px 8px;padding-left:16px;padding-right:16px}
      .cxa-row1{display:flex;align-items:center;gap:10px}
      .cxa-ic{flex:none;width:44px;height:44px;border-radius:14px;border:1px solid var(--cxa-line);background:var(--cxa-card);color:var(--cxa-text);font-size:20px;font-weight:800;cursor:pointer;display:grid;place-items:center}
      .cxa-title{flex:1;margin:0;font-size:18px;font-weight:800}
      .cxa-list{display:grid;gap:10px}
      .cxa-sec{margin:16px 4px 8px;font-size:15px;font-weight:800;letter-spacing:.04em}
      .cxa-item{display:grid;grid-template-columns:96px minmax(0,1fr) auto;gap:12px;align-items:start;padding:10px;border-radius:18px}
      .cxa-item img,.cxa-item .cxa-ph{width:96px;height:96px;border-radius:14px;object-fit:cover;display:block;background:var(--cxa-card-solid)}
      .cxa-ph{display:grid!important;place-items:center;font-weight:900;font-size:26px;color:var(--cxa-on-primary);background:linear-gradient(150deg,var(--cxa-primary),var(--cxa-accent))!important}
      .cxa-item h3{margin:2px 0 4px;font-size:16px;line-height:1.2}
      .cxa-item p{margin:0;font-size:13px;line-height:1.35;color:var(--cxa-muted);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
      .cxa-side{display:grid;gap:8px;justify-items:end;align-content:space-between;height:100%}
      .cxa-price{font-weight:900;font-size:15px;white-space:nowrap}
      .cxa-plus{width:44px;height:44px;border-radius:14px;border:0;background:var(--cxa-primary);color:var(--cxa-on-primary);font-size:24px;font-weight:900;cursor:pointer}
      .cxa-thumbs{display:flex;gap:8px;overflow-x:auto;padding:2px 0}
      .cxa-thumb{flex:0 0 auto;width:64px;height:64px;padding:0;border-radius:12px;border:2px solid transparent;overflow:hidden;background:var(--cxa-card);cursor:pointer}
      .cxa-thumb.on{border-color:var(--cxa-primary)}
      .cxa-thumb img{width:100%;height:100%;object-fit:cover;display:block}
      .cxa-empty{padding:24px;text-align:center;border-radius:18px}
      /* 057D: mientras carga (o si falla) una foto se ve el color de la marca, nunca blanco */
      .cxa-item img,.cxa-tcard img,.cxa-cat img{background:linear-gradient(150deg,var(--cxa-primary),var(--cxa-accent));color:transparent}
      @media (min-width:900px){.cxa-col.wide{max-width:960px}.cxa-col.wide .cxa-list{grid-template-columns:1fr 1fr}}
      /* modo video */
      .cxa-video{position:absolute;inset:0;z-index:6;background:#000}
      .cxa-vscroll{position:absolute;inset:0;overflow-y:auto;scroll-snap-type:y mandatory;overscroll-behavior:contain;scrollbar-width:none}
      .cxa-vscroll::-webkit-scrollbar{display:none}
      .cxa-slide{position:relative;height:100%;scroll-snap-align:start;scroll-snap-stop:always;overflow:hidden;background:#000}
      .cxa-media{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
      .cxa-kb{animation:cxa-kb 7s ease-in-out infinite alternate;transform-origin:50% 55%}
      @keyframes cxa-kb{from{transform:scale(1)}to{transform:scale(1.12) translate3d(-2%,-1%,0)}}
      .cxa-card0{position:absolute;inset:0;display:grid;place-items:center;padding:32px;text-align:center;background:linear-gradient(150deg,var(--cxa-primary),var(--cxa-accent));color:var(--cxa-on-primary);font-size:clamp(26px,8vw,40px);font-weight:900}
      .cxa-vtop{position:absolute;top:0;left:0;right:0;z-index:2;padding:calc(8px + env(safe-area-inset-top)) 12px 26px;background:linear-gradient(180deg,rgba(0,0,0,.72),transparent);display:grid;grid-template-columns:minmax(0,1fr);gap:8px}
      .cxa-prog{display:flex;gap:3px;height:4px}
      .cxa-prog i{flex:1;border-radius:4px;background:rgba(255,255,255,.35)}
      .cxa-prog i.on{background:#fff}
      .cxa-vtop .cxa-chip{min-height:36px;background:rgba(0,0,0,.5);color:#fff;border-color:rgba(255,255,255,.5)}
      .cxa-vtop .cxa-chip.on{background:var(--cxa-primary);color:var(--cxa-on-primary);border-color:transparent}
      .cxa-vtop .cxa-ic{background:rgba(0,0,0,.55);color:#fff;border-color:rgba(255,255,255,.5)}
      .cxa-vcard{position:absolute;left:12px;right:12px;bottom:calc(12px + env(safe-area-inset-bottom));z-index:2;max-width:456px;margin:0 auto;border-radius:22px;padding:14px;display:grid;gap:8px}
      .cxa-vcard h2{margin:0;font-size:22px;line-height:1.15}
      .cxa-vcard p{margin:0;font-size:14px;line-height:1.35;color:var(--cxa-muted);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
      .cxa-opts{display:flex;flex-wrap:wrap;gap:6px}
      .cxa-opts .cxa-chip{min-height:36px;font-size:13px}
      .cxa-buy{display:flex;align-items:center;gap:10px}
      .cxa-qty{display:flex;align-items:center;gap:6px}
      .cxa-qty button{width:40px;height:40px;border-radius:12px;border:1px solid var(--cxa-line);background:transparent;color:var(--cxa-text);font-size:20px;font-weight:900;cursor:pointer}
      .cxa-qty output{min-width:22px;text-align:center;font-weight:900}
      .cxa-buy .cxa-btn.primary{flex:1;display:flex;justify-content:space-between;align-items:center}
      .cxa-side-btn{position:absolute;right:12px;z-index:2;bottom:calc(260px + env(safe-area-inset-bottom));min-height:44px;padding:0 14px;border-radius:999px;border:1px solid rgba(255,255,255,.55);background:rgba(0,0,0,.55);color:#fff;font:inherit;font-weight:800;cursor:pointer}
      .cxa-req{font-size:12px;font-weight:700;color:var(--cxa-muted)}
      /* hojas */
      .cxa-sheet-back{position:absolute;inset:0;z-index:20;background:rgba(0,0,0,.55);display:grid;align-items:end}
      .cxa-sheet{max-width:520px;width:100%;margin:0 auto;max-height:88%;overflow-y:auto;border-radius:24px 24px 0 0;padding:18px 16px calc(18px + env(safe-area-inset-bottom));display:grid;gap:12px;background:var(--cxa-card-solid)}
      .cxa-sheet h2{margin:0;font-size:20px}
      .cxa-line{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:6px 10px;padding:10px 0;border-bottom:1px solid var(--cxa-line)}
      .cxa-line small{color:var(--cxa-muted)}
      .cxa-line input{grid-column:1/-1;min-height:44px;border-radius:12px;padding:0 12px;font:inherit;color:var(--cxa-text);background:transparent;border:1px solid var(--cxa-line)}
      .cxa-total{display:flex;justify-content:space-between;font-size:18px;font-weight:900}
      .cxa-msg{padding:12px 14px;border-radius:14px;font-weight:700}
      .cxa-msg.err{outline:2px solid #f87171}
      .cxa-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
      @media (prefers-reduced-motion: reduce){.cxa-kb{animation:none}.cxa *{scroll-behavior:auto!important}}
    `;
  }

  function loadFont(theme) {
    const family = String((theme && theme.font) || "").split(",")[0].trim();
    if (!GOOGLE_FONTS[family] || document.getElementById("cxaFont057C")) return;
    const link = document.createElement("link");
    link.id = "cxaFont057C";
    link.rel = "stylesheet";
    link.href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(GOOGLE_FONTS[family])}:wght@400;600;800;900&display=swap`;
    document.head.appendChild(link);
  }

  // ------------------------------------------------------------ app
  function mount(options) {
    const opts = options || {};
    const adapter = opts.adapter || { canOrder: false };
    let data = opts.data || {};
    const pal = palette(data.theme);
    injectStyles(pal);
    loadFont(data.theme);
    const S = { view: "home", category: "", query: "", index: 0, sheet: null, detail: "", msg: "", err: false, busy: false, pick: {} };
    const cart = new Map(); // key -> {id, name, price, quantity, term, quick_notes, note}
    const root = document.createElement("div");
    root.className = "cxa";
    root.setAttribute("lang", "es");
    document.body.appendChild(root);
    const videoOK = () => Boolean(data.video) && !lite() && !reducedMotion();

    const products = () => data.products || [];
    const byId = (id) => products().find((p) => p.id === id);
    const fmt = (v) => money(v, data.locale);
    const cartCount = () => [...cart.values()].reduce((n, l) => n + l.quantity, 0);
    const cartTotal = () => [...cart.values()].reduce((n, l) => n + l.quantity * l.price, 0);

    function picked(p) {
      const st = S.pick[p.id] || (S.pick[p.id] = { qty: 1, term: "", notes: [] });
      return st;
    }

    function headHtml() {
      const c = data.company || {};
      const logo = c.logo_url ? `<img class="cxa-logo" src="${h(c.logo_url)}" alt="" width="48" height="48">` : `<span class="cxa-logo-fb" aria-hidden="true">${h(String(c.name || "C").slice(0, 1).toUpperCase())}</span>`;
      return `<header class="cxa-head cxa-glass">${logo}<h1 class="cxa-name">${h(c.name || "Carta")}</h1>${adapter.where ? `<span class="cxa-where">${h(adapter.where)}</span>` : ""}</header>`;
    }

    function searchHtml() {
      return `<label class="cxa-search"><span class="cxa-sr">Busca un plato</span><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
        <input class="cxa-glass" type="search" placeholder="Busca un plato" value="${h(S.query)}" data-cxa-search autocomplete="off" enterkeyhint="search"></label>`;
    }

    function topHtml() {
      const ids = (data.top || []).filter((id) => byId(id));
      if (!ids.length) return "";
      const title = data.top_source === "ventas" ? "Lo más pedido" : "Para empezar";
      return `<h2 class="cxa-h2">${title}<small>${ids.length} platos</small></h2><div class="cxa-top" role="list">${ids.map((id) => {
        const p = byId(id);
        const img = p.poster_url || p.photo_url;
        return `<button type="button" role="listitem" class="cxa-tcard" data-cxa-play="${h(p.id)}">
          ${img ? `<img src="${h(img)}" alt="" loading="lazy" decoding="async" width="132" height="220">` : `<span class="cxa-card0" aria-hidden="true">${h(p.name.slice(0, 1))}</span>`}
          ${videoOK() && p.video_url ? `<video muted playsinline loop preload="none" poster="${h(img)}" data-src="${h(p.video_url)}" aria-hidden="true"></video>` : ""}
          <span><b>${h(p.name)}</b><i>${h(fmt(p.price))}</i></span></button>`;
      }).join("")}</div>`;
    }

    function catsHtml() {
      const cats = data.categories || [];
      return `<h2 class="cxa-h2">Categorías<small>${cats.length}</small></h2><div class="cxa-cats">${cats.map((c, i) => `
        <button type="button" class="cxa-cat ${c.image_url ? "" : "noimg"}" data-cxa-cat="${h(c.key)}">
          ${c.image_url ? `<img src="${h(c.image_url)}" alt="" ${i < 4 ? 'fetchpriority="high"' : 'loading="lazy"'} decoding="async" width="220" height="220">` : ""}
          <span><b>${h(c.label)}</b><i>${h(c.count)} ${c.count === 1 ? "plato" : "platos"}</i></span></button>`).join("")}</div>`;
    }

    function barHtml() {
      const n = cartCount();
      const order = adapter.canOrder
        ? `<button type="button" class="cxa-btn primary" data-cxa-cart><span>Pedido <span class="cxa-count">${n}</span></span><span>${h(fmt(cartTotal()))}</span></button>`
        : "";
      const playLabel = data.video ? "▶ Ver en video" : "▶ Ver platos";
      return `<nav class="cxa-bar" aria-label="Acciones"><div class="cxa-bar-in cxa-glass">
        <button type="button" class="cxa-btn" data-cxa-video>${playLabel}</button>
        ${adapter.canOrder ? order : `<button type="button" class="cxa-btn" data-cxa-list>☰ Lista</button>`}</div></nav>`;
    }

    let eager = 0; // las primeras fotos visibles de la lista cargan de inmediato
    function itemHtml(p, i = 9) {
      i = eager++;
      const img = p.photo_url || p.poster_url;
      return `<article class="cxa-item cxa-glass">
        ${img ? `<img src="${h(img)}" alt="" ${i < 4 ? "" : 'loading="lazy"'} decoding="async" width="96" height="96">` : `<span class="cxa-ph" aria-hidden="true">${h(p.name.slice(0, 1))}</span>`}
        <div><h3>${h(p.name)}</h3>${p.description ? `<p>${h(p.description)}</p>` : ""}</div>
        <div class="cxa-side"><span class="cxa-price">${h(fmt(p.price))}</span>
          ${adapter.canOrder ? `<button type="button" class="cxa-plus" data-cxa-add="${h(p.id)}" aria-label="Agregar ${h(p.name)}">+</button>` : `<button type="button" class="cxa-plus" data-cxa-detail="${h(p.id)}" aria-label="Ver ${h(p.name)}">›</button>`}</div>
      </article>`;
    }

    function listHtml() {
      eager = 0;
      const q = norm(S.query);
      const cats = data.categories || [];
      const match = (p) => !q || norm(`${p.name} ${p.description}`).includes(q);
      const groups = cats.map((c) => ({ c, items: products().filter((p) => p.category_key === c.key && match(p)) }))
        .filter((g) => g.items.length && (!S.category || q || g.c.key === S.category));
      return `<div class="cxa-col ${S.query ? "" : "wide"}">
        <div class="cxa-topbar cxa-glass">
          <div class="cxa-row1"><button type="button" class="cxa-ic" data-cxa-home aria-label="Volver al inicio">←</button><h2 class="cxa-title">${h(S.query ? "Resultados" : (cats.find((c) => c.key === S.category) || {}).label || "Carta")}</h2>
            <button type="button" class="cxa-ic" data-cxa-video aria-label="Ver en video">▶</button></div>
          ${S.query ? searchHtml() : `<div class="cxa-chips" role="tablist" aria-label="Categorías"><button type="button" role="tab" aria-selected="${!S.category}" class="cxa-chip ${S.category ? "" : "on"}" data-cxa-cat="">Todo</button>${cats.map((c) => `<button type="button" role="tab" aria-selected="${S.category === c.key}" class="cxa-chip ${S.category === c.key ? "on" : ""}" data-cxa-cat="${h(c.key)}">${h(c.label)}</button>`).join("")}</div>`}
        </div>
        ${groups.length ? groups.map((g) => `${S.category && !q ? "" : `<h3 class="cxa-sec">${h(g.c.label)}</h3>`}<div class="cxa-list">${g.items.map((p, i) => itemHtml(p, i)).join("")}</div>`).join("")
          : `<p class="cxa-empty cxa-glass">No encontramos platos con "${h(S.query)}".</p>`}
      </div>`;
    }

    function homeHtml() {
      if (S.query) return listHtml();
      return `<div class="cxa-col">${headHtml()}${searchHtml()}${topHtml()}${catsHtml()}</div>`;
    }

    function optionsHtml(p, compact) {
      if (!adapter.canOrder) return ""; // carta impresa (sin mesa): solo se ve, no se pide
      const st = picked(p);
      const parts = [];
      if (p.requires_term) {
        parts.push(`<div><span class="cxa-req" id="cxa-term-${h(p.id)}">Término (obligatorio)</span><div class="cxa-opts" role="radiogroup" aria-labelledby="cxa-term-${h(p.id)}">${(data.terms || []).map((t) => `<button type="button" role="radio" aria-checked="${st.term === t}" class="cxa-chip ${st.term === t ? "on" : ""}" data-cxa-term="${h(p.id)}" data-v="${h(t)}">${h(t)}</button>`).join("")}</div></div>`);
      }
      if ((p.quick_notes || []).length && !compact) {
        parts.push(`<div><span class="cxa-req" id="cxa-notes-${h(p.id)}">Preferencias (opcional)</span><div class="cxa-opts" role="group" aria-labelledby="cxa-notes-${h(p.id)}">${p.quick_notes.map((n) => `<button type="button" aria-pressed="${st.notes.includes(n)}" class="cxa-chip ${st.notes.includes(n) ? "on" : ""}" data-cxa-note="${h(p.id)}" data-v="${h(n)}">${h(n)}</button>`).join("")}</div></div>`);
      }
      return parts.join("");
    }

    function buyHtml(p) {
      if (!adapter.canOrder) return `<div class="cxa-buy"><span class="cxa-price">${h(fmt(p.price))}</span></div>`;
      const st = picked(p);
      return `<div class="cxa-buy"><div class="cxa-qty"><button type="button" data-cxa-qty="${h(p.id)}" data-d="-1" aria-label="Quitar uno">−</button><output aria-live="polite" aria-label="Cantidad">${st.qty}</output><button type="button" data-cxa-qty="${h(p.id)}" data-d="1" aria-label="Sumar uno">+</button></div>
        <button type="button" class="cxa-btn primary" data-cxa-add="${h(p.id)}"><span>Agregar</span><span>${h(fmt(p.price * st.qty))}</span></button></div>`;
    }

    function slideHtml(p, i) {
      const img = p.poster_url || p.photo_url;
      let media;
      if (videoOK() && p.video_url) media = `<video class="cxa-media" muted playsinline loop autoplay preload="metadata" poster="${h(img)}" data-src="${h(p.video_url)}" aria-hidden="true"></video>`;
      else if (img) media = `<img class="cxa-media ${reducedMotion() ? "" : "cxa-kb"}" src="${h(img)}" alt="" ${i > 1 ? 'loading="lazy"' : ""}>`;
      else media = `<div class="cxa-card0" aria-hidden="true">${h(p.name)}</div>`;
      return `<section class="cxa-slide" data-i="${i}" aria-label="${h(p.name)}">${media}
        <button type="button" class="cxa-side-btn" data-cxa-detail="${h(p.id)}">Detalle</button>
        <div class="cxa-vcard cxa-glass"><h2>${h(p.name)}</h2>${p.description ? `<p>${h(p.description)}</p>` : ""}${optionsHtml(p, true)}${buyHtml(p)}</div></section>`;
    }

    function videoList() {
      const all = products();
      const cats = (data.categories || []).map((c) => c.key);
      return [...all].sort((a, b) => cats.indexOf(a.category_key) - cats.indexOf(b.category_key));
    }

    function videoHtml() {
      const list = videoList();
      const cats = data.categories || [];
      const cur = list[S.index] || list[0];
      const prog = list.length <= 30 ? `<div class="cxa-prog" aria-hidden="true">${list.map((_, i) => `<i class="${i <= S.index ? "on" : ""}"></i>`).join("")}</div>` : "";
      return `<div class="cxa-video" role="region" aria-label="Carta en video">
        <div class="cxa-vscroll" data-cxa-vscroll tabindex="0">${list.map(slideHtml).join("")}</div>
        <div class="cxa-vtop">${prog}<div class="cxa-row1"><button type="button" class="cxa-ic" data-cxa-home aria-label="Cerrar video">✕</button>
          <div class="cxa-chips">${cats.map((c) => `<button type="button" class="cxa-chip ${cur && cur.category_key === c.key ? "on" : ""}" data-cxa-jump="${h(c.key)}">${h(c.label)}</button>`).join("")}</div></div></div>
      </div>`;
    }

    function cartSheet() {
      const lines = [...cart.entries()];
      const account = adapter.account ? adapter.account() : null;
      return `<div class="cxa-sheet-back" data-cxa-close><div class="cxa-sheet" role="dialog" aria-modal="true" aria-label="Tu pedido">
        <div class="cxa-row1"><h2 style="flex:1">Tu pedido</h2><button type="button" class="cxa-ic" data-cxa-close aria-label="Cerrar">✕</button></div>
        ${S.msg ? `<p class="cxa-msg cxa-glass ${S.err ? "err" : ""}" role="status">${h(S.msg)}</p>` : ""}
        ${lines.length ? lines.map(([key, l]) => `<div class="cxa-line"><div><b>${h(l.name)}</b><br><small>${h([l.term, ...(l.quick_notes || [])].filter(Boolean).join(" · ") || "Sin opciones")}</small></div>
            <div class="cxa-qty"><button type="button" data-cxa-lq="${h(key)}" data-d="-1" aria-label="Quitar uno de ${h(l.name)}">−</button><output>${l.quantity}</output><button type="button" data-cxa-lq="${h(key)}" data-d="1" aria-label="Sumar uno de ${h(l.name)}">+</button></div>
            <input data-cxa-lnote="${h(key)}" maxlength="200" placeholder="Nota para este plato (opcional)" aria-label="Nota para ${h(l.name)}" value="${h(l.note || "")}">
            <small style="grid-column:1/-1;text-align:right">${h(fmt(l.price * l.quantity))}</small></div>`).join("")
          : `<p class="cxa-empty">Todavía no has agregado platos.</p>`}
        ${lines.length ? `<div class="cxa-total"><span>Total</span><span>${h(fmt(cartTotal()))}</span></div>` : ""}
        ${lines.length ? `<button type="button" class="cxa-btn primary" data-cxa-send ${S.busy ? "disabled" : ""}>${h(S.busy ? "Enviando…" : adapter.submitLabel || "Enviar a cocina")}</button>` : ""}
        ${account ? `<p class="cxa-req">Cuenta de la mesa: <b>${h(fmt(account.total))}</b> · ${h(account.orders)} ${account.orders === 1 ? "pedido" : "pedidos"}</p>` : ""}
        ${adapter.extra ? `<button type="button" class="cxa-btn" data-cxa-extra>${h(adapter.extra.label)}</button>` : ""}
      </div></div>`;
    }

    // 058A: galería del plato ("Más fotos"): la principal y las demás, una a la vez
    function photosOf(p) {
      const main = p.photo_url || p.poster_url;
      return [main, ...(p.gallery_urls || [])].filter((u, i, all) => u && all.indexOf(u) === i);
    }

    function detailSheet() {
      const p = byId(S.detail);
      if (!p) return "";
      const photos = photosOf(p);
      const at = Math.min(S.photo || 0, Math.max(0, photos.length - 1));
      const img = photos[at];
      const thumbs = photos.length > 1
        ? `<div class="cxa-thumbs" role="group" aria-label="Fotos de ${h(p.name)}">${photos.map((u, i) => `<button type="button" class="cxa-thumb ${i === at ? "on" : ""}" data-cxa-photo="${i}" aria-label="Foto ${i + 1} de ${photos.length}" aria-pressed="${i === at}"><img src="${h(u)}" alt="" loading="lazy"></button>`).join("")}</div>`
        : "";
      return `<div class="cxa-sheet-back" data-cxa-close><div class="cxa-sheet" role="dialog" aria-modal="true" aria-label="${h(p.name)}">
        <div class="cxa-row1"><h2 style="flex:1">${h(p.name)}</h2><button type="button" class="cxa-ic" data-cxa-close aria-label="Cerrar">✕</button></div>
        ${img ? `<img src="${h(img)}" alt="${h(p.name)}${photos.length > 1 ? ` (foto ${at + 1} de ${photos.length})` : ""}" style="width:100%;max-height:260px;object-fit:cover;border-radius:16px">` : ""}${thumbs}
        ${p.description ? `<p style="margin:0;line-height:1.45">${h(p.description)}</p>` : ""}
        ${p.subcategory_label ? `<p class="cxa-req" style="margin:0">${h(p.category_label)} › ${h(p.subcategory_label)}</p>` : ""}
        ${optionsHtml(p, false)}${buyHtml(p)}</div></div>`;
    }

    function render() {
      const scrollBox = root.querySelector(".cxa-scroll");
      const keep = scrollBox ? scrollBox.scrollTop : 0;
      const view = S.view === "list" ? listHtml() : homeHtml();
      root.innerHTML = `<div class="cxa-bg" aria-hidden="true"></div><main class="cxa-scroll">${view}</main>${barHtml()}
        ${S.view === "video" ? videoHtml() : ""}${S.sheet === "cart" ? cartSheet() : ""}${S.sheet === "detail" ? detailSheet() : ""}`;
      const box = root.querySelector(".cxa-scroll");
      if (box && S.view !== "video") box.scrollTop = keep;
      if (S.view === "video") setupVideo();
      else startTopVideos();
    }

    // ------------------------------------------------------------ videos
    let observer = null;
    function setSrc(slide, on) {
      const v = slide && slide.querySelector("video[data-src]");
      if (!v) return;
      if (on && !v.getAttribute("src")) {
        v.addEventListener("error", () => fallback(v), { once: true });
        v.setAttribute("src", v.getAttribute("data-src"));
      } else if (!on && v.getAttribute("src")) {
        v.pause();
        v.removeAttribute("src");
        try { v.load(); } catch (_) {}
      }
    }
    // Si el video falla, queda la portada/foto (nunca un hueco).
    function fallback(v) {
      const img = document.createElement("img");
      img.className = v.className.replace("cxa-media", "cxa-media") || "";
      img.alt = "";
      img.src = v.getAttribute("poster") || "";
      if (!img.src) return;
      if (v.classList.contains("cxa-media")) img.classList.add("cxa-media");
      v.replaceWith(img);
    }
    function activate(index) {
      const slides = [...root.querySelectorAll(".cxa-slide")];
      S.index = Math.max(0, Math.min(slides.length - 1, index));
      slides.forEach((s, i) => setSrc(s, i === S.index || i === S.index + 1));
      slides.forEach((s, i) => {
        const v = s.querySelector("video");
        if (!v || !v.getAttribute("src")) return;
        if (i === S.index) { const pr = v.play && v.play(); if (pr && pr.catch) pr.catch(() => {}); } else if (v.pause) v.pause();
      });
      root.querySelectorAll(".cxa-prog i").forEach((bar, i) => bar.classList.toggle("on", i <= S.index));
      const cur = videoList()[S.index];
      root.querySelectorAll("[data-cxa-jump]").forEach((b) => b.classList.toggle("on", !!cur && b.getAttribute("data-cxa-jump") === cur.category_key));
    }
    function setupVideo() {
      const box = root.querySelector("[data-cxa-vscroll]");
      if (!box) return;
      const slides = [...box.querySelectorAll(".cxa-slide")];
      if (slides[S.index]) box.scrollTop = slides[S.index].offsetTop;
      if (observer) observer.disconnect();
      if (typeof IntersectionObserver === "function") {
        observer = new IntersectionObserver((entries) => entries.forEach((e) => { if (e.isIntersecting && e.intersectionRatio >= 0.6) activate(Number(e.target.getAttribute("data-i"))); }), { root: box, threshold: [0.6] });
        slides.forEach((s) => observer.observe(s));
      }
      activate(S.index);
      box.focus({ preventScroll: true });
    }
    function startTopVideos() {
      if (!videoOK()) return;
      const run = () => root.querySelectorAll(".cxa-tcard video[data-src]").forEach((v) => {
        if (v.getAttribute("src")) return;
        v.addEventListener("error", () => v.remove(), { once: true });
        v.setAttribute("src", v.getAttribute("data-src"));
        const pr = v.play && v.play(); if (pr && pr.catch) pr.catch(() => {});
      });
      // los videos chicos arrancan despues de pintar la carta (abre rapido en 4G)
      (window.requestIdleCallback || ((fn) => setTimeout(fn, 1500)))(() => setTimeout(run, 1200));
    }

    // ------------------------------------------------------------ acciones
    function open(view, extra) {
      Object.assign(S, extra || {});
      S.view = view;
      try { history.pushState({ cxa: view }, ""); } catch (_) {}
      render();
    }
    function addToCart(p) {
      const st = picked(p);
      if (p.requires_term && !st.term) {
        S.msg = `Elige el término de ${p.name}.`;
        S.err = true;
        if (S.sheet !== "detail") { S.detail = p.id; S.sheet = "detail"; }
        render();
        return;
      }
      const key = `${p.id}|${st.term}|${[...st.notes].sort().join(",")}`;
      const line = cart.get(key) || { id: p.id, name: p.name, price: p.price, quantity: 0, term: st.term, quick_notes: [...st.notes], note: "" };
      line.quantity += st.qty;
      cart.set(key, line);
      S.pick[p.id] = { qty: 1, term: "", notes: [] };
      S.msg = `${p.name} agregado.`;
      S.err = false;
      if (S.sheet === "detail") S.sheet = null;
      if (adapter.onChange) adapter.onChange(lines());
      render();
      announce(`${p.name} agregado al pedido. ${cartCount()} productos.`);
    }
    function announce(text) {
      let live = document.getElementById("cxaLive057C");
      if (!live) { live = document.createElement("div"); live.id = "cxaLive057C"; live.className = "cxa-sr"; live.setAttribute("aria-live", "polite"); document.body.appendChild(live); }
      live.textContent = text;
    }
    function lines() { return [...cart.values()].map((l) => ({ ...l })); }

    async function send() {
      if (!adapter.submit || S.busy) return;
      S.busy = true;
      S.msg = "";
      render();
      try {
        const out = await adapter.submit(lines());
        if (out && out.keepCart) { S.busy = false; render(); return; }
        cart.clear();
        S.msg = (out && out.message) || "Tu pedido fue enviado.";
        S.err = false;
      } catch (error) {
        S.msg = (error && error.message) || "No se pudo enviar el pedido.";
        S.err = true;
      }
      S.busy = false;
      render();
    }

    root.addEventListener("click", (event) => {
      const t = event.target;
      if (!t || !t.closest) return;
      const q = (sel) => t.closest(sel);
      let el;
      if ((el = q("[data-cxa-close]")) && (el === t || t.closest("button[data-cxa-close]"))) { S.sheet = null; S.msg = ""; render(); return; }
      if (q("[data-cxa-home]")) { S.view = "home"; S.query = ""; S.category = ""; render(); return; }
      if (q("[data-cxa-video]")) { open("video", { index: 0 }); return; }
      if (q("[data-cxa-list]")) { open("list", { category: "" }); return; }
      if ((el = q("[data-cxa-play]"))) { open("video", { index: Math.max(0, videoList().findIndex((p) => p.id === el.getAttribute("data-cxa-play"))) }); return; }
      if ((el = q("[data-cxa-cat]"))) { open("list", { category: el.getAttribute("data-cxa-cat") }); return; }
      if ((el = q("[data-cxa-jump]"))) {
        const i = videoList().findIndex((p) => p.category_key === el.getAttribute("data-cxa-jump"));
        const box = root.querySelector("[data-cxa-vscroll]");
        const slide = box && box.querySelectorAll(".cxa-slide")[i];
        if (slide) { box.scrollTop = slide.offsetTop; activate(i); }
        return;
      }
      if ((el = q("[data-cxa-detail]"))) { S.detail = el.getAttribute("data-cxa-detail"); S.sheet = "detail"; S.photo = 0; S.msg = ""; render(); return; }
      if ((el = q("[data-cxa-photo]"))) { S.photo = Number(el.getAttribute("data-cxa-photo")) || 0; repaint(); return; }
      if ((el = q("[data-cxa-term]"))) { const p = byId(el.getAttribute("data-cxa-term")); if (p) { picked(p).term = el.getAttribute("data-v"); S.msg = ""; repaint(); } return; }
      if ((el = q("[data-cxa-note]"))) {
        const p = byId(el.getAttribute("data-cxa-note")); const v = el.getAttribute("data-v");
        if (p) { const st = picked(p); st.notes = st.notes.includes(v) ? st.notes.filter((n) => n !== v) : [...st.notes, v]; repaint(); }
        return;
      }
      if ((el = q("[data-cxa-qty]"))) { const p = byId(el.getAttribute("data-cxa-qty")); if (p) { const st = picked(p); st.qty = Math.max(1, Math.min(50, st.qty + Number(el.getAttribute("data-d")))); repaint(); } return; }
      if ((el = q("[data-cxa-add]"))) {
        const p = byId(el.getAttribute("data-cxa-add"));
        if (!p) return;
        if (S.view !== "video" && S.sheet !== "detail" && (p.requires_term || (p.quick_notes || []).length)) { S.detail = p.id; S.sheet = "detail"; S.msg = ""; render(); return; }
        addToCart(p);
        return;
      }
      if (q("[data-cxa-cart]")) { S.sheet = "cart"; S.msg = ""; render(); return; }
      if ((el = q("[data-cxa-lq]"))) {
        const key = el.getAttribute("data-cxa-lq"); const l = cart.get(key);
        if (l) { l.quantity += Number(el.getAttribute("data-d")); if (l.quantity <= 0) cart.delete(key); if (adapter.onChange) adapter.onChange(lines()); render(); }
        return;
      }
      if (q("[data-cxa-send]")) { send(); return; }
      if (q("[data-cxa-extra]") && adapter.extra) { S.sheet = null; adapter.extra.run(); }
    });
    // Repinta el modo video sin reiniciar el scroll ni los videos.
    function repaint() {
      if (S.view === "video" && S.sheet !== "detail") {
        const slide = root.querySelectorAll(".cxa-slide")[S.index];
        const p = videoList()[S.index];
        const card = slide && slide.querySelector(".cxa-vcard");
        if (card && p) { card.innerHTML = `<h2>${h(p.name)}</h2>${p.description ? `<p>${h(p.description)}</p>` : ""}${optionsHtml(p, true)}${buyHtml(p)}`; return; }
      }
      if (S.sheet === "detail") {
        const sheet = root.querySelector(".cxa-sheet-back");
        if (sheet) { sheet.outerHTML = detailSheet(); return; }
      }
      render();
    }
    // una foto que no carga deja ver el color de la marca (nunca el icono de imagen rota)
    root.addEventListener("error", (event) => {
      const t = event.target;
      if (t && t.tagName === "IMG" && !t.classList.contains("cxa-media") && t.getAttribute("src")) { t.classList.add("cxa-broken"); t.removeAttribute("src"); }
    }, true);
    root.addEventListener("input", (event) => {
      const t = event.target;
      if (t.matches && t.matches("[data-cxa-search]")) {
        S.query = t.value;
        const pos = t.selectionStart;
        render();
        const again = root.querySelector("[data-cxa-search]");
        if (again) { again.focus(); try { again.setSelectionRange(pos, pos); } catch (_) {} }
        return;
      }
      if (t.matches && t.matches("[data-cxa-lnote]")) { const l = cart.get(t.getAttribute("data-cxa-lnote")); if (l) l.note = t.value.slice(0, 200); }
    });
    root.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        if (S.sheet) { S.sheet = null; render(); } else if (S.view !== "home") { S.view = "home"; render(); }
        return;
      }
      if (S.view !== "video" || S.sheet) return;
      const box = root.querySelector("[data-cxa-vscroll]");
      if (!box) return;
      const step = { ArrowDown: 1, PageDown: 1, j: 1, ArrowUp: -1, PageUp: -1, k: -1 }[event.key];
      if (!step) return;
      event.preventDefault();
      const slides = box.querySelectorAll(".cxa-slide");
      const next = Math.max(0, Math.min(slides.length - 1, S.index + step));
      box.scrollTop = slides[next].offsetTop;
      activate(next);
    });
    window.addEventListener("popstate", () => { if (S.sheet) S.sheet = null; else if (S.view !== "home") S.view = "home"; render(); });

    render();
    return {
      root, palette: pal,
      update(next) {
        data = next || data;
        const ids = new Set(products().map((p) => p.id));
        // agotado en vivo: lo que ya no esta en la carta sale tambien del pedido sin enviar
        for (const [key, l] of cart) if (!ids.has(l.id)) cart.delete(key);
        if (S.view === "video") return; // no interrumpe el plato que se esta viendo
        render();
      },
      show() { root.hidden = false; try { document.documentElement.style.overflow = "hidden"; } catch (_) {} },
      hide() { root.hidden = true; try { document.documentElement.style.overflow = ""; } catch (_) {} root.querySelectorAll("video").forEach((v) => v.pause && v.pause()); },
      openCart() { S.sheet = "cart"; render(); },
      clearCart() { cart.clear(); render(); },
      lines, state: S,
      destroy() { if (observer) observer.disconnect(); root.remove(); },
    };
  }

  window.CxCartaApp = { mount, palette, buttonColors, textOn, ratio, rgbOf, money };
})();
