// Vista previa de la Cola de hoy para la prueba de diseño: la consola v2+ real (admin_v2plus.html y sus JS)
// con fetch simulado, abierta en #cola. Mide desbordes, columnas, tamaño de botones y contraste en <pre id="layout">.
(() => {
  const P = new URLSearchParams(location.search);
  const json = (b, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
  const T = (name, kind = "inicial", net = "instagram") => `${kind === "seguimiento" ? "¡Hola de nuevo, " + name + "! 👋\nSomos CLONEXA. Les dejamos otro ejemplo de bar en vivo en 3D 👆\nSi quieren verlo con su negocio, respondan SÍ y se lo mostramos en 2 minutos 🙌\nSi no, no les escribimos más."
    : "¡Qué más, " + name + "! 🍻\nSomos CLONEXA 🚀\n¿Se imaginan ver su bar funcionando EN VIVO EN 3D? 🎮 Mesas, barra y pedidos en tiempo real, desde el celular o el TV 📺 Así 👆\n\n📲 Pedidos por QR desde la mesa\n🧾 Cuenta exacta por mesa, cero peleas al pagar\n🎶 Piden canciones desde el celular\n\n👉 clonexa.com.co/b/SXFB3W\n📲 Síganos: @clonexaapp\n¿Les mostramos cómo se vería el suyo? 😎\nSi no quieren más mensajes, respondan NO."}`;
  const item = (id, name, over = {}) => ({ id, kind: "inicial", status: "pendiente", network: "instagram", name, nicho: "Bares", niche: "bar", zona: "Techo", text: T(name),
    profile_url: "https://www.instagram.com/alwayspub/", app_url: "instagram://user?username=alwayspub", liked: false, video: "/admin-v2plus/bumeranes/bar.mp4",
    sent_at: null, replied: false, no_contactar: false, ...over });
  const data = { ok: true, fecha: "2026-11-13", fecha_label: "Jueves 13 nov", limite: 15, total: 15, enviados: 3, por_enviar: 12, motivo: "", horario: true,
    pendientes: [item(1, "Always Pub"), item(2, "Excalibur Centro de Eventos Gastrobar y Discoteca Internacional", { network: "facebook", profile_url: "https://www.facebook.com/excalibur",
      app_url: "fb://facewebmodal/f?href=https%3A%2F%2Fwww.facebook.com%2Fexcalibur" }), item(3, "Confecciones Rubí", { nicho: "Talleres y fábricas", zona: "Puente Aranda", niche: "taller",
      video: "/admin-v2plus/bumeranes/taller.mp4" }), item(4, "Minimercado La Esquina", { nicho: "Tiendas y minimercados", niche: "tienda", video: "" })],
    seguimientos: [item(5, "Bar La 80", { kind: "seguimiento", text: T("Bar La 80", "seguimiento") })],
    archivados: [item(6, "Bar La 80", { status: "enviado", sent_at: "2026-11-13T14:12:00Z" }), item(7, "Gastrobar El Molino", { status: "saltado" })] };
  window.fetch = async (url) => {
    const u = String(url);
    if (u.startsWith("/admin-v2/api/overview")) return json({ ok: true, companies: [], totals: {}, health: {} });
    if (u.startsWith("/admin-v2/api/billing/alerts")) return json({ alerts: [] });
    if (u.startsWith("/api/v1/prospecting/admin/cola/pendientes")) return json({ ok: true, pendientes: 12 });
    if (u.startsWith("/api/v1/prospecting/admin/cola")) return json(data);
    return json({});
  };
  try { history.replaceState(null, "", `${location.pathname}${location.search}#cola`); } catch (_) {}

  function rgb(v) { const m = String(v || "").match(/rgba?\(([^)]+)\)/); if (!m) return null; const [r, g, b, a = 1] = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return { r, g, b, a }; }
  function lum({ r, g, b }) { const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); }
  function bgOf(el) {
    const layers = [];
    for (let n = el; n; n = n.parentElement) { const c = rgb(getComputedStyle(n).backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } }
    let base = { r: 5, g: 2, b: 4 };
    for (let i = layers.length - 1; i >= 0; i -= 1) { const l = layers[i]; base = { r: l.r * l.a + base.r * (1 - l.a), g: l.g * l.a + base.g * (1 - l.a), b: l.b * l.a + base.b * (1 - l.a) }; }
    return base;
  }
  const ratio = (el) => { const fg = rgb(getComputedStyle(el).color); const a = lum(fg) + 0.05; const b = lum(bgOf(el)) + 0.05; return Math.round((Math.max(a, b) / Math.min(a, b)) * 100) / 100; };

  function measure() {
    const out = document.createElement("pre");
    out.id = "layout";
    const root = document.querySelector(".vp-cola");
    if (!root) { out.textContent = JSON.stringify({ mounted: false }); document.body.appendChild(out); return; }
    const bad = [];
    root.querySelectorAll("*").forEach((el) => {
      if (el.offsetParent === null) return;
      const cs = getComputedStyle(el);
      if (/auto|scroll/.test(cs.overflowX + cs.overflowY) || el.tagName === "PROGRESS") return;
      if (el.scrollWidth > el.clientWidth + 1) bad.push({ cls: String(el.className || ""), text: (el.textContent || "").trim().slice(0, 30) });
    });
    const cards = [...root.querySelectorAll(".vp-cola-card")];
    const lefts = [...new Set(cards.map((c) => Math.round(c.getBoundingClientRect().left)))];
    const btns = [...root.querySelectorAll(".vp-cola-btn")].filter((b) => b.offsetParent !== null);
    const low = [...root.querySelectorAll(".vp-cola-btn, .vp-cola-text, .vp-cola-card-head h2, .vp-cola-card-head p, .vp-cola-tab, .vp-cola-progress b")]
      .filter((el) => el.offsetParent !== null).map((el) => ({ cls: String(el.className || el.tagName), r: ratio(el) })).filter((x) => x.r < 4.5);
    const navBadge = document.querySelector("[data-cola-badge]");
    out.textContent = JSON.stringify({
      mounted: true, width: window.innerWidth, page_overflow: document.documentElement.scrollWidth > window.innerWidth + 1, bad,
      cards: cards.length, columns: lefts.length, min_btn_h: Math.min(...btns.map((b) => Math.round(b.getBoundingClientRect().height))),
      min_btn_w: Math.min(...btns.map((b) => Math.round(b.getBoundingClientRect().width))), low, badge: navBadge ? navBadge.textContent : "",
      nav_active: (document.querySelector(".vp-nav-item.is-active") || {}).textContent || "",
    });
    document.body.appendChild(out);
  }
  const go = (n = 0) => {
    if (!document.querySelector(".vp-cola-card") && n < 80) return setTimeout(() => go(n + 1), 150);
    setTimeout(measure, 800);
  };
  window.addEventListener("load", () => go());
})();
