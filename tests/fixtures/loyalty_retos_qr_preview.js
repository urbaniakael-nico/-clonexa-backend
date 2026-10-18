// Vista previa del QR de la mesa (hospitality_order.html real) con la polla de
// Retos para las mesas en sus cuatro momentos: ?qr=open|closed|tie|win, como Mesa 4.
// Datos de ejemplo (sin servidor). Mide desbordes y contraste en <pre id="layout">.
// ?theme=light (tema claro), ?long=1 (nombres largos en la lista de pronosticos),
// ?welcome=1 (bienvenida con nombre: qr_welcome_name), ?named=Laura (ya puso su nombre).
(() => {
  const P = new URLSearchParams(location.search);
  const CID = P.get("company_id");
  const CASE = P.get("qr") || "open";
  const json = (b, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
  const real = window.fetch.bind(window);
  try {
    localStorage.setItem(`clonexa_hsp_table_access_${CID}_mesa_4`, "ABC12");
    if (P.get("named")) localStorage.setItem(`clonexa_hospitality_account_${CID}_mesa_4_ABC12_customer`, P.get("named"));
  } catch (_) {}
  const LIGHT = P.get("theme") === "light";
  const WELCOME = P.get("welcome") === "1" || !!P.get("named");
  const now = Date.now();
  const iso = (ms) => new Date(now + ms).toISOString();
  const base = { id: "p1", campaign_type: "score_pool", title: "Polla · Colombia vs Argentina", prize: "Botella de aguardiente", team_a: "Colombia", team_b: "Argentina",
    description: "Adivina el marcador exacto y participa por el premio.", status: "active", rules_version: 2, predictions_close_at: iso(1800000),
    predictions_seconds_left: 1800, predictions_open: true, result_status: "", winner: null, final_score: null, tied_tables: [], phase: "registration_open", seconds_left: 0,
    predictions: P.get("long") === "1"
      ? [{ id: "x1", table_key: "mesa 12", table_number: "Mesa 12", team_name: "Los del fondo con un nombre larguísimo que no cabe", score_a: 1, score_b: 1 },
        { id: "x2", table_key: "terraza vip 3", table_number: "Terraza VIP 3", team_name: "María de los Ángeles y sus amigas del trabajo", score_a: 2, score_b: 1 },
        { id: "x9", table_key: "mesa 9", table_number: "Mesa 9", team_name: "Mesa 9", score_a: 2, score_b: 1 }]
      : [{ id: "x1", table_key: "mesa 1", table_number: "Mesa 1", team_name: "Las chicas", score_a: 1, score_b: 1 }, { id: "x9", table_key: "mesa 9", table_number: "Mesa 9", team_name: "Mesa 9", score_a: 2, score_b: 1 }] };
  const mine = { id: "x4", table_key: "mesa 4", table_number: "Mesa 4", team_name: "Los parceros", score_a: 2, score_b: 1 };
  const cases = {
    open: { score_campaign: base, score_prediction: null },
    closed: { score_campaign: { ...base, predictions_open: false, predictions_seconds_left: 0 }, score_prediction: mine },
    tie: { score_campaign: { ...base, predictions_open: false, result_status: "tie", final_score: { score_a: 2, score_b: 1 }, tied_tables: [{ table_key: "mesa 4", table_number: "Mesa 4" }, { table_key: "mesa 9", table_number: "Mesa 9" }] }, score_prediction: mine },
    win: { score_campaign: { ...base, status: "closed", predictions_open: false, result_status: "winner", final_score: { score_a: 2, score_b: 1 },
      winner: { kind: "table", table_key: "mesa 4", table_number: "Mesa 4", team_name: "Los parceros", player_name: "Camila" } }, score_prediction: mine },
  };
  window.fetch = async (url, opts) => {
    const u = String(url);
    if (!u.includes("/api/v1")) return real(url, opts);
    const p = u.slice(u.indexOf("/api/v1") + 7).split("?")[0];
    if (p === `/companies/${CID}`) return json({ id: CID, name: "The Time Machine" });
    if (p === `/companies/${CID}/branding`) return json({ branding: LIGHT ? { primary_color: "#ff8a1c", secondary_color: "#0f766e", background_color: "#ffffff", text_color: "#111827" }
      : { primary_color: "#6b5d00", secondary_color: "#aea924", background_color: "#14110a", text_color: "#ffffff" } });
    if (p.endsWith("/qr-tables/access")) return json({ ok: true, access: { active: true, expires_at: iso(3600000) }, company_name: "The Time Machine",
      ui: WELCOME ? { bar_menu: false, welcome_name: true, welcome_text: "¡Bienvenido a [bar]! 🎶 Qué bueno tenerte esta noche. ¿Cómo te llamas?", welcome_custom: false, language: "es", name_max: 30 } : { bar_menu: false } });
    if (p.endsWith("/qr-tables/account")) return json({ ok: true, account: { total: 0, orders_count: 0, accounts: [], items: [], current_account: P.get("named") ? { name: P.get("named") } : null } });
    if (p.endsWith("/qr-tables/access/verify")) return json({ ok: true, access: { active: true, expires_at: iso(3600000) } });
    if (p.includes("/inventory-lite")) return json({ inventory: [{ id: "i1", name: "Cerveza Club Colombia", price: 9000, stock: 40, category: "Cervezas" }, { id: "i2", name: "Aguardiente media", price: 48000, stock: 10, category: "Licores" }] });
    if (p.includes("/loyalty-campaigns/active")) return json({ ok: true, campaign: null, participant: null, vote_campaign: null, vote_response: null, ...cases[CASE] });
    return json({});
  };

  function rgb(value) {
    const srgb = String(value || "").match(/color\(srgb ([^)]+)\)/);
    if (srgb) { const [r, g, b, a = 1] = srgb[1].split(/[ /]+/).filter(Boolean).map(Number); return { r: r * 255, g: g * 255, b: b * 255, a }; }
    const m = String(value || "").match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const [r, g, b, a = 1] = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
    return { r, g, b, a };
  }
  function lum({ r, g, b }) { const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); }
  function bgOf(el) {
    const layers = [];
    for (let n = el; n; n = n.parentElement) { const c = rgb(getComputedStyle(n).backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } }
    let base2 = { r: 8, g: 7, b: 18 };
    for (let i = layers.length - 1; i >= 0; i -= 1) { const l = layers[i]; base2 = { r: l.r * l.a + base2.r * (1 - l.a), g: l.g * l.a + base2.g * (1 - l.a), b: l.b * l.a + base2.b * (1 - l.a) }; }
    return base2;
  }
  function ratio(el) { const fg = rgb(getComputedStyle(el).color); const bg = bgOf(el); const a = lum(fg) + 0.05; const b = lum(bg) + 0.05; return Math.round((Math.max(a, b) / Math.min(a, b)) * 100) / 100; }

  function measure() {
    const host = document.getElementById("qrCampaignHost025F");
    const out = document.createElement("pre");
    out.id = "layout";
    out.style.display = "none";
    const bad = [], low = [];
    (host ? host.querySelectorAll("*") : []).forEach((el) => {
      if (/^(INPUT|SELECT|OPTION)$/.test(el.tagName) || el.offsetParent === null) return;
      // Los textos que se cortan con "…" a proposito no cuentan como desborde.
      const ellipsis = getComputedStyle(el).textOverflow === "ellipsis" && getComputedStyle(el).overflow === "hidden";
      if (!ellipsis && el.scrollWidth > el.clientWidth + 1) bad.push({ cls: String(el.className || ""), text: (el.textContent || "").trim().slice(0, 40) });
      const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
      if (own && !el.closest(".qr-btn")) { const r = ratio(el); if (r < 4.5) low.push({ cls: String(el.className || ""), text: el.textContent.trim().slice(0, 30), ratio: r }); }
    });
    // Lista de pronosticos: el circulo de la mesa y el nombre nunca se tapan.
    const overlaps = [...document.querySelectorAll(".qr-rank-row")].filter((row) => {
      const badge = row.querySelector(":scope > span");
      const body = row.querySelector(":scope > div");
      return badge && body && badge.getBoundingClientRect().right > body.getBoundingClientRect().left + 0.5;
    }).length;
    const eyebrow = document.querySelector("#qrCampaignHost025F .qr-eyebrow");
    const dlg = document.getElementById("qrWelcome056B");
    const welcomeLow = dlg ? [...dlg.querySelectorAll("*")].filter((el) => [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()) && !el.closest(".qr-btn") && !el.closest(".qr-logo"))
      .map((el) => ({ text: el.textContent.trim().slice(0, 24), ratio: ratio(el) })).filter((x) => x.ratio < 4.5) : [];
    out.textContent = JSON.stringify({ mounted: !!host, page_overflow: document.documentElement.scrollWidth > window.innerWidth + 1, bad, low_contrast: low, overlaps,
      eyebrow: eyebrow ? { text: eyebrow.textContent.trim(), ratio: ratio(eyebrow) } : null, welcome: !!dlg, welcome_text: dlg ? dlg.textContent.replace(/\s+/g, " ").trim() : "",
      welcome_low: welcomeLow, chip: (document.querySelector(".qr-welcome-chip") || {}).textContent || "",
      text: host ? host.textContent.replace(/\s+/g, " ").trim().slice(0, 600) : "" });
    document.body.appendChild(out);
    if (host && P.get("scroll") !== "0") host.scrollIntoView({ block: "start" });
  }
  const ready = (n = 0) => {
    const wantWelcome = P.get("welcome") === "1";
    if (n < 40 && (!document.getElementById("qrCampaignHost025F") || (wantWelcome && !document.getElementById("qrWelcome056B")))) return setTimeout(() => ready(n + 1), 250);
    return setTimeout(measure, 600);
  };
  window.addEventListener("load", () => setTimeout(ready, 1500));
})();
