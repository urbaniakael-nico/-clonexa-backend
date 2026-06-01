(() => {
  "use strict";

  const API = "/api/v1";
  const app = document.getElementById("app");
  const params = new URLSearchParams(window.location.search);
  const state = {
    companyId: params.get("company_id") || params.get("companyId") || "",
    table: params.get("mesa") || params.get("table") || "Mesa",
    company: {},
    branding: {},
    inventory: [],
    cart: new Map(),
    category: "Todos",
    search: "",
    campaign: null,
    participant: null,
    scoreCampaign: null,
    scorePrediction: null,
    voteCampaign: null,
    voteResponse: null,
    campaignDismissed: false,
    campaignEndRefreshKey: "",
    access: { active: false, unlocked: false, code: "", expires_at: "" },
    qrMode: "hospitality",
    assemblyPublic: null,
    assemblyEvent: null,
    assemblyFields: [],
    assemblyAttendee: null,
    assemblySummary: {},
    assemblyVotes: [],
    assemblyQuestions: [],
    assemblyResponses: {},
    assemblyParticipantQuestions: {},
    loading: true,
    message: "",
    error: "",
  };

  const h = (value) =>
    String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");

  async function api(path, options = {}) {
    const res = await fetch(`${API}${path}`, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${res.status} ${res.statusText} ${text}`.trim());
    }
    return res.json();
  }

  function money(value) {
    try {
      return new Intl.NumberFormat("es-CO", {
        style: "currency",
        currency: "COP",
        maximumFractionDigits: 0,
      }).format(Number(value || 0));
    } catch (_) {
      return `$ ${Number(value || 0).toLocaleString("es-CO")}`;
    }
  }

  function normalizeText(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .trim();
  }

  function qrModeNorm() {
    return normalizeText(state.qrMode || state.assemblyPublic?.qr?.mode || "hospitality").replace(/[^a-z0-9]+/g, "_");
  }

  function isAssemblyMode() {
    return ["voting", "vote", "votacion", "participantes", "participants", "assembly", "asamblea", "assemblies", "asambleas"].includes(qrModeNorm());
  }

  function assemblyAccessLabel() {
    return isAssemblyMode() ? "Participante QR" : "Mesa QR";
  }

  function assemblyActionLabel() {
    return isAssemblyMode() ? "Activar acceso" : "Activar pedido";
  }

  function prettyLabel(value) {
    const clean = String(value || "Otros")
      .replace(/[^\w\s\u00c0-\u017f]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    if (!clean) return "Otros";
    return clean
      .split(" ")
      .map((part) => part.slice(0, 1).toUpperCase() + part.slice(1).toLowerCase())
      .join(" ");
  }

  function productCategory(item) {
    const explicit = item.category || item.category_name || item.group || item.family;
    if (explicit) return prettyLabel(explicit);
    const firstWord = String(item.name || "").trim().split(/\s+/)[0] || "Otros";
    return prettyLabel(firstWord);
  }

  function productCategories() {
    const counts = new Map();
    state.inventory.forEach((item) => {
      const category = productCategory(item);
      counts.set(category, (counts.get(category) || 0) + 1);
    });
    const grouped = [...counts.entries()]
      .sort((a, b) => a[0].localeCompare(b[0], "es"))
      .map(([name, count]) => ({ name, count }));
    return [{ name: "Todos", count: state.inventory.length }, ...grouped];
  }

  function visibleProducts() {
    const validCategories = new Set(productCategories().map((item) => item.name));
    if (!validCategories.has(state.category)) state.category = "Todos";
    const query = normalizeText(state.search);
    return state.inventory.filter((item) => {
      const category = productCategory(item);
      const inCategory = state.category === "Todos" || category === state.category;
      if (!inCategory) return false;
      if (!query) return true;
      return normalizeText(`${item.name || ""} ${item.sku || ""} ${category}`).includes(query);
    });
  }

  function brand() {
    const b = state.branding || {};
    return {
      primary: b.primary_color || b.color_principal || "#ff8a1c",
      secondary: b.secondary_color || b.color_secundario || "#f6cf98",
      bg: b.background_color || b.color_fondo || "#120022",
      text: b.text_color || b.color_texto || "#fff7ed",
      logo: b.logo_url || "",
    };
  }

  function injectStyles() {
    const b = brand();
    let style = document.getElementById("hspPublicQrStyles024X");
    if (!style) {
      style = document.createElement("style");
      style.id = "hspPublicQrStyles024X";
      document.head.appendChild(style);
    }
    style.textContent = `
      :root{
        --qr-primary:${b.primary};
        --qr-secondary:${b.secondary};
        --qr-bg:${b.bg};
        --qr-text:${b.text};
        --qr-card:rgba(15,23,42,.72);
        --qr-line:rgba(255,255,255,.14);
        --qr-muted:rgba(255,255,255,.68);
      }
      *{box-sizing:border-box}
      body{
        margin:0;
        min-height:100vh;
        color:var(--qr-text);
        background:
          radial-gradient(circle at 0% 0%, color-mix(in srgb,var(--qr-primary) 45%, transparent), transparent 32%),
          radial-gradient(circle at 100% 0%, color-mix(in srgb,var(--qr-secondary) 35%, transparent), transparent 30%),
          linear-gradient(135deg,var(--qr-bg),#070312 72%);
        font-family:Inter,Segoe UI,system-ui,sans-serif;
      }
      button,input,textarea{font:inherit}
      .qr-shell{min-height:100vh;padding:16px;display:grid;gap:14px;max-width:1180px;margin:0 auto}
      .qr-shell-locked{align-content:start;max-width:980px}
      .qr-hero,.qr-card,.qr-cart{
        background:linear-gradient(145deg,rgba(255,255,255,.10),rgba(255,255,255,.035)),var(--qr-card);
        border:1px solid var(--qr-line);
        border-radius:22px;
        box-shadow:0 22px 70px rgba(0,0,0,.28);
        backdrop-filter:blur(20px) saturate(1.2);
      }
      .qr-hero{padding:22px;display:grid;grid-template-columns:1fr auto;gap:14px;align-items:center}
      .qr-hero-locked{padding:18px 20px}
      .qr-hero-locked h1{font-size:clamp(32px,7vw,54px)}
      .qr-logo{width:54px;height:54px;border-radius:16px;display:grid;place-items:center;overflow:hidden;background:linear-gradient(135deg,var(--qr-primary),var(--qr-secondary));color:#111827;font-weight:1000}
      .qr-logo img{width:100%;height:100%;object-fit:contain}
      .qr-eyebrow{margin:0 0 6px;color:var(--qr-primary);font-size:11px;letter-spacing:.16em;text-transform:uppercase;font-weight:1000}
      h1{margin:0;font-size:clamp(30px,8vw,58px);line-height:.95;letter-spacing:-.03em}
      .qr-muted{color:var(--qr-muted);font-weight:750;line-height:1.35}
      .qr-layout{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:14px;align-items:start}
      .qr-menu{display:grid;gap:12px}
      .qr-menu-head{display:grid;grid-template-columns:minmax(0,1fr) minmax(220px,320px);gap:12px;align-items:end}
      .qr-menu-title{margin:0;font-size:22px;line-height:1.05}
      .qr-search{
        width:100%;
        border:1px solid var(--qr-line);
        border-radius:16px;
        background:rgba(2,6,23,.58);
        color:var(--qr-text);
        padding:13px 14px;
        outline:none;
        font-weight:900;
      }
      .qr-search::placeholder{color:rgba(255,255,255,.42)}
      .qr-categories{display:flex;gap:8px;overflow:auto;padding:2px 2px 6px;scrollbar-width:thin}
      .qr-category{
        border:1px solid var(--qr-line);
        border-radius:999px;
        padding:10px 13px;
        min-height:40px;
        white-space:nowrap;
        color:var(--qr-text);
        background:rgba(255,255,255,.075);
        font-weight:1000;
        cursor:pointer;
      }
      .qr-category.active{
        color:#101827;
        border-color:transparent;
        background:linear-gradient(135deg,var(--qr-primary),var(--qr-secondary));
      }
      .qr-category small{opacity:.7;font-size:11px}
      .qr-menu-meta{color:var(--qr-muted);font-size:12px;font-weight:900}
      .qr-products{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}
      .qr-card{padding:14px;display:grid;gap:12px;min-height:176px}
      .qr-product-name{font-size:17px;font-weight:950;line-height:1.1;word-break:break-word}
      .qr-stock{color:var(--qr-muted);font-size:12px;font-weight:850}
      .qr-price{font-size:22px;font-weight:1000;color:var(--qr-secondary)}
      .qr-btn{
        border:0;
        border-radius:14px;
        padding:12px 14px;
        min-height:44px;
        color:#101827;
        background:linear-gradient(135deg,var(--qr-primary),var(--qr-secondary));
        font-weight:1000;
        cursor:pointer;
      }
      .qr-btn.secondary{background:rgba(255,255,255,.09);color:var(--qr-text);border:1px solid var(--qr-line)}
      .qr-btn:disabled{opacity:.48;cursor:not-allowed;filter:grayscale(.35)}
      .qr-cart{position:sticky;top:14px;padding:16px;display:grid;gap:12px}
      .qr-cart h2{margin:0;font-size:22px}
      .qr-field{display:grid;gap:6px}
      .qr-field span{font-size:11px;letter-spacing:.11em;text-transform:uppercase;color:var(--qr-muted);font-weight:1000}
      .qr-field input,.qr-field textarea{
        width:100%;
        border:1px solid var(--qr-line);
        border-radius:14px;
        background:rgba(2,6,23,.58);
        color:var(--qr-text);
        padding:12px;
        outline:none;
        font-weight:850;
      }
      .qr-field textarea{min-height:76px;resize:vertical}
      .qr-line{display:grid;grid-template-columns:1fr auto;gap:8px;padding:10px 0;border-bottom:1px solid rgba(255,255,255,.09)}
      .qr-line-name{font-weight:950;line-height:1.15}
      .qr-qty{display:flex;align-items:center;gap:6px}
      .qr-qty button{width:32px;height:32px;border-radius:10px;border:1px solid var(--qr-line);background:rgba(255,255,255,.08);color:var(--qr-text);font-weight:1000;cursor:pointer}
      .qr-total{display:flex;justify-content:space-between;align-items:center;padding:12px;border-radius:16px;background:rgba(0,0,0,.24);font-weight:1000}
      .qr-total strong{font-size:22px;color:var(--qr-secondary)}
      .qr-msg{padding:12px;border-radius:14px;background:rgba(34,197,94,.13);border:1px solid rgba(34,197,94,.28);color:#bbf7d0;font-weight:900}
      .qr-msg.err{background:rgba(239,68,68,.13);border-color:rgba(239,68,68,.30);color:#fecaca}
      .qr-empty{border:1px dashed rgba(255,255,255,.18);border-radius:16px;padding:18px;text-align:center;color:var(--qr-muted);font-weight:850}
      .qr-access-gate{
        background:
          linear-gradient(145deg,rgba(255,255,255,.14),rgba(255,255,255,.045)),
          radial-gradient(circle at 8% 0%, color-mix(in srgb,var(--qr-primary) 25%, transparent), transparent 34%),
          var(--qr-card);
        border:1px solid color-mix(in srgb,var(--qr-secondary) 34%, var(--qr-line));
        border-radius:22px;
        padding:18px;
        display:grid;
        gap:14px;
        align-content:start;
        box-shadow:0 18px 54px rgba(0,0,0,.24);
      }
      .qr-access-top{display:grid;gap:7px}
      .qr-access-gate h2{margin:0;font-size:clamp(26px,5.5vw,42px);line-height:1.02;color:var(--qr-secondary)}
      .qr-access-gate .qr-muted{margin:0;max-width:720px}
      .qr-access-form{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:end}
      .qr-access-form input{
        width:100%;
        border:1px solid var(--qr-line);
        border-radius:16px;
        background:rgba(2,6,23,.58);
        color:var(--qr-text);
        min-height:58px;
        padding:15px 16px;
        outline:none;
        font-weight:1000;
        font-size:22px;
        letter-spacing:.12em;
        text-transform:uppercase;
      }
      .qr-access-form input::placeholder{color:rgba(255,255,255,.44)}
      .qr-access-form .qr-btn{min-height:58px;padding-inline:22px}
      .qr-access-note{border:1px solid rgba(255,255,255,.11);border-radius:16px;background:rgba(3,7,18,.30);padding:12px;color:var(--qr-muted);font-weight:850;line-height:1.32}
      .qr-campaign{
        display:grid;
        grid-template-columns:minmax(0,1fr) minmax(240px,360px);
        gap:12px;
        background:linear-gradient(145deg,rgba(255,255,255,.12),rgba(255,255,255,.04)),var(--qr-card);
        border:1px solid var(--qr-line);
        border-radius:22px;
        padding:16px;
        box-shadow:0 18px 54px rgba(0,0,0,.24);
      }
      .qr-campaign h2{margin:0 0 8px;font-size:26px;line-height:1.05}
      .qr-campaign-main{display:grid;gap:10px}
      .qr-campaign-prize,.qr-campaign-clock,.qr-campaign-ok{
        display:flex;
        justify-content:space-between;
        gap:12px;
        align-items:center;
        padding:10px 12px;
        border-radius:15px;
        background:rgba(3,7,18,.34);
        border:1px solid rgba(255,255,255,.10);
        font-weight:1000;
      }
      .qr-campaign-prize strong,.qr-campaign-clock strong{color:var(--qr-secondary);font-size:20px}
      .qr-campaign-join{display:grid;grid-template-columns:1fr minmax(150px,1fr) auto auto;gap:8px;align-items:end}
      .qr-campaign-join strong{display:block}
      .qr-campaign-join span{display:block;color:var(--qr-muted);font-size:11px;font-weight:900;text-transform:uppercase;letter-spacing:.08em;margin-top:4px}
      .qr-campaign-join input{width:100%;border:1px solid var(--qr-line);border-radius:14px;background:rgba(2,6,23,.58);color:var(--qr-text);padding:12px;font-weight:900;outline:none}
      .qr-campaign-rank{display:grid;gap:8px;align-content:start}
      .qr-rank-row{display:grid;grid-template-columns:28px 1fr;gap:9px;align-items:center;background:rgba(3,7,18,.30);border:1px solid rgba(255,255,255,.10);border-radius:14px;padding:9px}
      .qr-rank-row span{font-weight:1000;color:var(--qr-secondary)}
      .qr-rank-row strong{display:block}
      .qr-rank-row small{display:block;color:var(--qr-muted);font-size:11px;font-weight:850}
      .qr-rank-row i{display:block;height:7px;border-radius:999px;background:rgba(255,255,255,.10);overflow:hidden;margin-top:6px}
      .qr-rank-row b{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,var(--qr-primary),var(--qr-secondary))}
      .qr-score-form{display:grid;gap:10px}
      .qr-score-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;align-items:end}
      .qr-score-grid label{display:grid;gap:5px;color:var(--qr-muted);font-size:11px;font-weight:1000;letter-spacing:.08em;text-transform:uppercase}
      .qr-score-grid input,.qr-score-name{
        width:100%;
        border:1px solid var(--qr-line);
        border-radius:14px;
        background:rgba(2,6,23,.58);
        color:var(--qr-text);
        padding:12px;
        outline:none;
        font-weight:950;
      }
      .qr-score-grid input{text-align:center;font-size:20px}
      .qr-vote-options{display:grid;gap:8px}
      .qr-vote-choice{display:flex;align-items:center;justify-content:space-between;gap:10px;border:1px solid var(--qr-line);border-radius:14px;background:rgba(2,6,23,.42);padding:12px;color:var(--qr-text);font-weight:1000;cursor:pointer}
      .qr-vote-choice input{width:18px;height:18px;accent-color:var(--qr-secondary)}
      .qr-vote-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center;background:rgba(3,7,18,.30);border:1px solid rgba(255,255,255,.10);border-radius:14px;padding:9px}
      .qr-vote-row strong{display:block}
      .qr-vote-row small{display:block;color:var(--qr-muted);font-size:11px;font-weight:850}
      .qr-vote-row em{font-style:normal;color:var(--qr-secondary);font-weight:1000}
      .qr-vote-row i{display:block;height:7px;border-radius:999px;background:rgba(255,255,255,.10);overflow:hidden;margin-top:6px}
      .qr-vote-row b{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,var(--qr-primary),var(--qr-secondary))}
      .qr-assembly{
        display:grid;
        grid-template-columns:minmax(0,1fr) minmax(240px,330px);
        gap:14px;
        align-items:start;
      }
      .qr-assembly-card{
        background:linear-gradient(145deg,rgba(255,255,255,.12),rgba(255,255,255,.04)),var(--qr-card);
        border:1px solid var(--qr-line);
        border-radius:22px;
        padding:16px;
        box-shadow:0 18px 54px rgba(0,0,0,.24);
      }
      .qr-assembly-card.is-wide{grid-column:1/-1}
      .qr-assembly-card h2{margin:0 0 8px;font-size:26px;color:var(--qr-secondary)}
      .qr-assembly-form{display:grid;gap:10px;margin-top:12px}
      .qr-assembly-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
      .qr-assembly-field{display:grid;gap:6px}
      .qr-assembly-field.full{grid-column:1/-1}
      .qr-assembly-field span{font-size:11px;letter-spacing:.11em;text-transform:uppercase;color:var(--qr-muted);font-weight:1000}
      .qr-assembly-field input,.qr-assembly-field textarea{
        width:100%;
        border:1px solid var(--qr-line);
        border-radius:14px;
        background:rgba(2,6,23,.58);
        color:var(--qr-text);
        padding:12px;
        outline:none;
        font-weight:900;
      }
      .qr-assembly-field textarea{min-height:88px;resize:vertical}
      .qr-assembly-summary{display:grid;gap:9px}
      .qr-assembly-chip{display:flex;justify-content:space-between;gap:12px;border:1px solid rgba(255,255,255,.10);border-radius:15px;background:rgba(3,7,18,.34);padding:11px 12px;font-weight:1000}
      .qr-assembly-chip strong{color:var(--qr-secondary)}
      .qr-assembly-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:12px 0}
      .qr-assembly-kpi{border:1px solid var(--qr-line);border-radius:16px;background:rgba(3,7,18,.34);padding:12px;font-weight:1000}
      .qr-assembly-kpi span{display:block;color:var(--qr-muted);font-size:10px;letter-spacing:.10em;text-transform:uppercase}
      .qr-assembly-kpi strong{display:block;margin-top:6px;color:var(--qr-secondary);font-size:24px}
      .qr-vote-list{display:grid;gap:12px}
      .qr-asm-vote-card{border:1px solid var(--qr-line);border-radius:18px;background:rgba(3,7,18,.30);padding:14px;display:grid;gap:11px}
      .qr-asm-vote-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}
      .qr-asm-vote-head h3{margin:0;font-size:22px;color:var(--qr-secondary)}
      .qr-asm-clock{white-space:nowrap;border:1px solid rgba(255,255,255,.10);border-radius:999px;background:rgba(255,255,255,.07);padding:7px 10px;font-weight:1000}
      .qr-asm-options{display:grid;gap:8px}
      .qr-asm-choice{border:1px solid var(--qr-line);border-radius:14px;background:rgba(2,6,23,.48);padding:10px;display:grid;gap:8px;cursor:pointer}
      .qr-asm-choice-top{display:flex;justify-content:space-between;gap:10px;font-weight:1000}
      .qr-asm-choice input{accent-color:var(--qr-secondary)}
      .qr-asm-bar{height:8px;border-radius:999px;background:rgba(255,255,255,.10);overflow:hidden}
      .qr-asm-bar i{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,var(--qr-primary),var(--qr-secondary));width:0}
      .qr-asm-question{display:grid;gap:6px}
      .qr-asm-question textarea{width:100%;min-height:76px;border:1px solid var(--qr-line);border-radius:14px;background:rgba(2,6,23,.58);color:var(--qr-text);padding:12px;font-weight:850;resize:vertical}
      .qr-asm-participation{border:1px solid rgba(255,255,255,.10);border-radius:18px;background:rgba(3,7,18,.34);padding:14px;margin-top:12px;display:grid;gap:8px}
      .qr-asm-split{display:grid;grid-template-columns:minmax(0,1fr) minmax(260px,360px);gap:12px;align-items:start}
      .qr-asm-side{display:grid;gap:8px}
      .qr-asm-summary-list{display:grid;gap:8px;margin-top:8px}
      @media(max-width:860px){
        .qr-hero{grid-template-columns:1fr}
        .qr-layout,.qr-assembly,.qr-asm-split{grid-template-columns:1fr}
        .qr-menu-head{grid-template-columns:1fr}
        .qr-campaign,.qr-campaign-join,.qr-access-form,.qr-score-grid,.qr-assembly-grid,.qr-assembly-kpis{grid-template-columns:1fr}
        .qr-cart{position:static}
      }
    `;
  }

  function accessStorageKey() {
    return `clonexa_hsp_table_access_${state.companyId}_${normalizeText(state.table).replace(/[^a-z0-9]+/g, "_")}`;
  }

  function accessGateHtml() {
    const active = state.access?.active === true;
    const assembly = isAssemblyMode();
    return `
      <section class="qr-access-gate">
        <div class="qr-access-top">
          <p class="qr-eyebrow">${assembly ? "Acceso de participante" : "Acceso de mesa"}</p>
          <h2>Ingresa clave de activacion</h2>
          <p class="qr-muted">${active ? (assembly ? "Escribe la clave entregada por el operador para abrir el formulario de la asamblea." : "Escribe la clave que te entrego el personal del bar para abrir el menu de pedidos.") : (assembly ? "Si aun no tienes clave, pide al operador activar este participante QR." : "Si aun no tienes clave, pide al personal del bar activar esta mesa.")}</p>
        </div>
        <div class="qr-access-form">
          <input id="qrAccessCode025B" maxlength="12" autocomplete="one-time-code" placeholder="CLAVE" autofocus>
          <button class="qr-btn" type="button" data-access-verify>${assemblyActionLabel()}</button>
        </div>
        <div class="qr-access-note">${active ? "Solo se solicita una vez en este dispositivo. Si la jornada cambia, se genera una nueva clave." : "La clave se genera desde el panel QR con el boton Activar."}</div>
      </section>
    `;
  }

  function cartRows() {
    const rows = [...state.cart.values()];
    if (!rows.length) return `<div class="qr-empty">Aun no has agregado productos.</div>`;
    return rows.map((item) => `
      <div class="qr-line">
        <div>
          <div class="qr-line-name">${h(item.name)}</div>
          <div class="qr-stock">${Number(item.price || 0) > 0 ? h(money(item.price)) : "Valor por confirmar"}</div>
        </div>
        <div class="qr-qty">
          <button type="button" data-dec="${h(item.id)}">-</button>
          <strong>${h(item.quantity)}</strong>
          <button type="button" data-inc="${h(item.id)}">+</button>
        </div>
      </div>
    `).join("");
  }

  function cartTotal() {
    return [...state.cart.values()].reduce((sum, item) => sum + Number(item.quantity || 0) * Number(item.price || 0), 0);
  }

  function countdown(value = 0) {
    const total = Math.max(0, Number(value || 0));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = Math.floor(total % 60);
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }

  function secondsUntil(value = "") {
    if (!value) return 0;
    const time = new Date(value).getTime();
    if (!Number.isFinite(time)) return 0;
    return Math.max(0, Math.floor((time - Date.now()) / 1000));
  }

  function assemblyEventStorageKey(suffix = "continue") {
    const eventId = state.assemblyEvent?.id || "sin_evento";
    const tableKey = normalizeText(state.table).replace(/[^a-z0-9]+/g, "_");
    return `clonexa_assembly_${suffix}_${state.companyId}_${eventId}_${tableKey}`;
  }

  function assemblyActUrl() {
    const settings = state.assemblyEvent?.settings || {};
    return settings.act_url || settings.minutes_file_url || settings.document_url || "";
  }

  function assemblyPublicReportUrl() {
    const eventId = state.assemblyEvent?.id || "";
    if (!eventId || !state.companyId) return "";
    return `${API}/assemblies/companies/${encodeURIComponent(state.companyId)}/events/${encodeURIComponent(eventId)}/report?mode=basic`;
  }

  function assemblyActRead() {
    const url = assemblyActUrl();
    return !url || localStorage.getItem(assemblyEventStorageKey("acta")) === "ok";
  }

  function assemblyCanShowDecisions() {
    return state.assemblyAttendee?.id && localStorage.getItem(assemblyEventStorageKey("continue")) === "ok";
  }

  function assemblyDecisionTotals() {
    const totals = { favor: 0, against: 0, abstain: 0, all: 0 };
    (state.assemblyVotes || []).forEach((vote) => {
      (vote.options || []).forEach((option) => {
        const key = String(option.key || "");
        const count = Number(option.count || 0);
        if (["favor", "yes", "true"].includes(key)) totals.favor += count;
        else if (["against", "no", "false"].includes(key)) totals.against += count;
        else if (["abstain", "no_participa", "none"].includes(key)) totals.abstain += count;
        totals.all += count;
      });
    });
    const pct = (value) => totals.all ? Math.round((value / totals.all) * 100) : 0;
    return { ...totals, favorPct: pct(totals.favor), againstPct: pct(totals.against), abstainPct: pct(totals.abstain) };
  }

  function assemblyVoteDomId(value = "") {
    return String(value || "vote").replace(/[^a-zA-Z0-9_-]+/g, "_");
  }

  function campaignHtml() {
    const campaign = state.campaign;
    if (!campaign) return "";
    const rows = Array.isArray(campaign.leaderboard) ? campaign.leaderboard : [];
    const open = campaign.registration_open === true;
    const participant = state.participant;
    const winner = campaign.winner || null;
    const tournamentPhase = campaign.tournament_phase || "open";
    const tournamentLabel = tournamentPhase === "closed" ? "Torneo finalizado" : tournamentPhase === "scheduled" ? "Torneo inicia en" : "Torneo cierra en";
    const form = open && !participant && !state.campaignDismissed ? `
      <div class="qr-campaign-join">
        <div>
          <strong>Te animas a participar?</strong>
          <span>Nombre del equipo</span>
        </div>
        <input id="qrTeam024Z" placeholder="Ej: Equipo Mesa 1" value="${h(document.getElementById("qrTeam024Z")?.value || "")}">
        <button class="qr-btn" type="button" data-campaign-join>Si, participar</button>
        <button class="qr-btn secondary" type="button" data-campaign-dismiss>No participar</button>
      </div>
    ` : "";
    const joined = participant ? `<div class="qr-campaign-ok">Participando como <strong>${h(participant.team_name)}</strong></div>` : "";
    const closedSignup = !open && !participant && !winner ? `<div class="qr-campaign-ok">Inscripcion cerrada para esta ronda.</div>` : "";
    const winnerHtml = winner ? `<div class="qr-campaign-ok">Equipo ganador: <strong>${h(winner.team_name)}</strong> - ${h(winner.table_number)}</div>` : "";
    return `
      <section class="qr-campaign">
        <div class="qr-campaign-main">
          <p class="qr-eyebrow">Sorteo activo</p>
          <h2>${h(campaign.title || "Reto de consumo")}</h2>
          <p class="qr-muted">${h(campaign.description || "La mesa con mas consumo dentro del tiempo gana el premio.")}</p>
          <div class="qr-campaign-prize"><span>Premio</span><strong>${h(campaign.prize || "Por definir")}</strong></div>
          <div class="qr-campaign-clock"><span>Inscripcion cierra en</span><strong id="qrSignupClock025A">${h(countdown(campaign.signup_seconds_left))}</strong></div>
          <div class="qr-campaign-clock"><span>${h(tournamentLabel)}</span><strong id="qrTournamentClock025A">${h(countdown(campaign.tournament_seconds_left))}</strong></div>
          ${joined}
          ${closedSignup}
          ${winnerHtml}
          ${form}
        </div>
        <div class="qr-campaign-rank">
          ${rows.length ? rows.slice(0, 5).map((row) => `
            <div class="qr-rank-row">
              <span>${h(row.rank)}</span>
              <div>
                <strong>${h(row.team_name)}</strong>
                <small>${h(row.table_number)} - ${h(row.orders_count)} pedido(s)</small>
                <i><b style="width:${Math.min(100, Math.max(0, Number(row.percent || 0)))}%"></b></i>
              </div>
            </div>
          `).join("") : `<div class="qr-empty">Se el primero en participar.</div>`}
        </div>
      </section>
    `;
  }

  function campaignHtml025G() {
    const campaign = state.campaign;
    if (!campaign) return "";
    const rows = Array.isArray(campaign.leaderboard) ? campaign.leaderboard : [];
    const open = campaign.registration_open === true;
    const participant = state.participant;
    const winner = campaign.winner || null;
    const tournamentPhase = campaign.tournament_phase || "open";
    const tournamentLabel = tournamentPhase === "closed" ? "Torneo finalizado" : tournamentPhase === "scheduled" ? "Torneo inicia en" : "Torneo cierra en";
    const form = open && !participant && !state.campaignDismissed ? `
      <div class="qr-campaign-join">
        <div>
          <strong>Te animas a participar?</strong>
          <span>Nombre del equipo</span>
        </div>
        <input id="qrTeam024Z" placeholder="Ej: Equipo Mesa 1" value="${h(document.getElementById("qrTeam024Z")?.value || "")}">
        <button class="qr-btn" type="button" data-campaign-join>Si, participar</button>
        <button class="qr-btn secondary" type="button" data-campaign-dismiss>No participar</button>
      </div>
    ` : "";
    const joined = participant ? `<div class="qr-campaign-ok">Participando como <strong>${h(participant.team_name)}</strong></div>` : "";
    const closedSignup = !open && !participant && !winner ? `<div class="qr-campaign-ok">Inscripcion cerrada para esta ronda.</div>` : "";
    const winnerHtml = winner ? `<div class="qr-campaign-ok">Equipo ganador: <strong>${h(winner.team_name)}</strong> - ${h(winner.table_number)}</div>` : "";
    return `
      <section class="qr-campaign">
        <div class="qr-campaign-main">
          <p class="qr-eyebrow">Sorteo activo</p>
          <h2>${h(campaign.title || "Reto de consumo")}</h2>
          <p class="qr-muted">${h(campaign.description || "La mesa con mas consumo dentro del tiempo gana el premio.")}</p>
          <div class="qr-campaign-prize"><span>Premio</span><strong>${h(campaign.prize || "Por definir")}</strong></div>
          <div class="qr-campaign-clock"><span>Inscripcion cierra en</span><strong id="qrSignupClock025A">${h(countdown(campaign.signup_seconds_left))}</strong></div>
          <div class="qr-campaign-clock"><span>${h(tournamentLabel)}</span><strong id="qrTournamentClock025A">${h(countdown(campaign.tournament_seconds_left))}</strong></div>
          ${joined}
          ${closedSignup}
          ${winnerHtml}
          ${form}
        </div>
        <div class="qr-campaign-rank">
          ${rows.length ? rows.slice(0, 5).map((row) => `
            <div class="qr-rank-row">
              <span>${h(row.rank)}</span>
              <div>
                <strong>${h(row.team_name)}</strong>
                <small>${h(row.table_number)} - ${h(row.orders_count)} pedido(s)</small>
                <i><b style="width:${Math.min(100, Math.max(0, Number(row.percent || 0)))}%"></b></i>
              </div>
            </div>
          `).join("") : `<div class="qr-empty">Se el primero en participar.</div>`}
        </div>
      </section>
    `;
  }

  function scorePoolHtml025G() {
    const campaign = state.scoreCampaign;
    if (!campaign) return "";
    const prediction = state.scorePrediction || {};
    const rows = Array.isArray(campaign.predictions) ? campaign.predictions : [];
    const currentName = document.getElementById("qrScoreName025G")?.value || prediction.team_name || "";
    const scoreA = document.getElementById("qrScoreA025G")?.value ?? (prediction.score_a ?? "");
    const scoreB = document.getElementById("qrScoreB025G")?.value ?? (prediction.score_b ?? "");
    return `
      <section class="qr-campaign">
        <div class="qr-campaign-main">
          <p class="qr-eyebrow">Polla activa</p>
          <h2>${h(campaign.title || "Polla de marcador")}</h2>
          <p class="qr-muted">${h(campaign.description || "Coloca tu marcador y participa por el premio.")}</p>
          <div class="qr-campaign-prize"><span>Premio</span><strong>${h(campaign.prize || "Por definir")}</strong></div>
          <div class="qr-score-form">
            <input id="qrScoreName025G" class="qr-score-name" placeholder="Nombre o equipo" value="${h(currentName)}">
            <div class="qr-score-grid">
              <label>${h(campaign.team_a || "Equipo A")}<input id="qrScoreA025G" type="number" min="0" max="99" inputmode="numeric" value="${h(scoreA)}"></label>
              <label>${h(campaign.team_b || "Equipo B")}<input id="qrScoreB025G" type="number" min="0" max="99" inputmode="numeric" value="${h(scoreB)}"></label>
            </div>
            <button class="qr-btn" type="button" data-score-submit>Enviar marcador</button>
          </div>
          ${prediction.id ? `<div class="qr-campaign-ok">Marcador registrado: <strong>${h(prediction.score_a)} - ${h(prediction.score_b)}</strong></div>` : ""}
        </div>
        <div class="qr-campaign-rank">
          ${rows.length ? rows.slice(0, 6).map((row) => `
            <div class="qr-rank-row">
              <span>${h(row.table_number || "")}</span>
              <div>
                <strong>${h(row.team_name || row.table_number || "Mesa")}</strong>
                <small>${h(campaign.team_a || "Equipo A")} ${h(row.score_a)} - ${h(row.score_b)} ${h(campaign.team_b || "Equipo B")}</small>
              </div>
            </div>
          `).join("") : `<div class="qr-empty">Aun no hay marcadores.</div>`}
        </div>
      </section>
    `;
  }

  function voteModeLabel025O(mode = "") {
    const labels = {
      registration: "Inscripcion",
      true_false: "Verdadero / Falso",
      yes_no: "Si / No",
      participants: "Participantes",
    };
    return labels[String(mode || "").trim()] || "Concurso";
  }

  function votePollHtml025O() {
    const campaign = state.voteCampaign;
    if (!campaign) return "";
    const response = state.voteResponse || {};
    const results = Array.isArray(campaign.results) ? campaign.results : [];
    const options = Array.isArray(campaign.options) ? campaign.options : [];
    const isClosed = campaign.phase === "closed" || Number(campaign.seconds_left || 0) <= 0;
    const currentName = document.getElementById("qrVoteName025O")?.value || response.voter_name || "";
    const currentAnswer = document.querySelector("input[name='qrVoteOption025O']:checked")?.value || response.answer_key || "";
    const form = !isClosed && !response.id ? `
      <div class="qr-score-form">
        <input id="qrVoteName025O" class="qr-score-name" placeholder="Nombre o equipo" value="${h(currentName)}">
        ${campaign.vote_mode === "registration" ? "" : `
          <div class="qr-vote-options">
            ${options.map((option) => `
              <label class="qr-vote-choice">
                <span>${h(option.label)}</span>
                <input type="radio" name="qrVoteOption025O" value="${h(option.key)}" ${option.key === currentAnswer ? "checked" : ""}>
              </label>
            `).join("")}
          </div>
        `}
        <button class="qr-btn" type="button" data-vote-submit>${campaign.vote_mode === "registration" ? "Inscribirme" : "Enviar respuesta"}</button>
      </div>
    ` : "";
    const already = response.id ? `<div class="qr-campaign-ok">Respuesta registrada: <strong>${h(response.answer_label || "Inscrito")}</strong></div>` : "";
    const closed = isClosed && !response.id ? `<div class="qr-campaign-ok">Concurso cerrado.</div>` : "";
    return `
      <section class="qr-campaign">
        <div class="qr-campaign-main">
          <p class="qr-eyebrow">${h(voteModeLabel025O(campaign.vote_mode))}</p>
          <h2>${h(campaign.title || "Concurso")}</h2>
          <p class="qr-muted">${h(campaign.description || "Participa desde esta mesa.")}</p>
          <div class="qr-campaign-prize"><span>Premio</span><strong>${h(campaign.prize || "Por definir")}</strong></div>
          <div class="qr-campaign-clock"><span>Cierra en</span><strong id="qrVoteClock025O">${h(countdown(campaign.seconds_left))}</strong></div>
          ${already}
          ${closed}
          ${form}
        </div>
        <div class="qr-campaign-rank">
          ${results.length ? results.map((row) => `
            <div class="qr-vote-row">
              <div>
                <strong>${h(row.label)}</strong>
                <small>${h(row.count)} respuesta(s)</small>
                <i><b style="width:${Math.min(100, Math.max(0, Number(row.percent || 0)))}%"></b></i>
              </div>
              <em>${h(row.percent || 0)}%</em>
            </div>
          `).join("") : `<div class="qr-empty">Aun no hay respuestas.</div>`}
        </div>
      </section>
    `;
  }

  function assemblyFieldId(key = "") {
    return `qrAsm025V_${String(key || "field").replace(/[^a-zA-Z0-9_-]+/g, "_")}`;
  }

  function assemblyCurrentValue(field = {}) {
    const id = assemblyFieldId(field.key);
    const live = document.getElementById(id);
    if (live && "value" in live) return live.value;
    const attendee = state.assemblyAttendee || {};
    if (field.key === "attendee_name") return attendee.attendee_name || "";
    if (field.key === "document_ref") return attendee.document_ref || "";
    const meta = attendee.metadata || {};
    return meta[field.key] || "";
  }

  function assemblyPublicFormHtml() {
    const event = state.assemblyEvent || null;
    const publicData = state.assemblyPublic || {};
    const fields = Array.isArray(state.assemblyFields) && state.assemblyFields.length
      ? state.assemblyFields
      : [
          { key: "attendee_name", label: "Nombre completo", type: "text", required: true, placeholder: "Ej: Maria Perez" },
          { key: "document_ref", label: "Documento / ID", type: "text", required: true, placeholder: "Identificacion" },
        ];
    if (!event?.id) {
      return `
        <section class="qr-assembly">
          <div class="qr-assembly-card">
            <p class="qr-eyebrow">Asamblea</p>
            <h2>No hay asamblea activa</h2>
            <p class="qr-muted">El QR ya esta en modo votacion / participantes, pero aun falta crear o activar la asamblea desde el panel cliente.</p>
          </div>
        </section>
      `;
    }
    const settings = event.settings || {};
    const registered = state.assemblyAttendee?.id ? `<div class="qr-msg">Registro recibido. Ya quedaste habilitado para esta asamblea.</div>` : "";
    if (state.assemblyAttendee?.id) {
      if (String(event.status || "").toLowerCase() === "closed") return assemblyDecisionBoardHtml();
      return assemblyCanShowDecisions() ? assemblyDecisionBoardHtml() : assemblyActaGateHtml();
    }
    const fieldHtml = fields.map((field) => {
      const key = String(field.key || "");
      const type = String(field.type || "text").toLowerCase();
      const full = type === "textarea" || key === "notes";
      const required = field.required ? "required" : "";
      const value = assemblyCurrentValue(field);
      if (type === "textarea") {
        return `
          <label class="qr-assembly-field full">
            <span>${h(field.label || key)}</span>
            <textarea id="${h(assemblyFieldId(key))}" data-assembly-field="${h(key)}" placeholder="${h(field.placeholder || "")}" ${required}>${h(value)}</textarea>
          </label>
        `;
      }
      return `
        <label class="qr-assembly-field ${full ? "full" : ""}">
          <span>${h(field.label || key)}</span>
          <input id="${h(assemblyFieldId(key))}" data-assembly-field="${h(key)}" type="${h(type || "text")}" placeholder="${h(field.placeholder || "")}" value="${h(value)}" ${required}>
        </label>
      `;
    }).join("");
    return `
      <section class="qr-assembly">
        <div class="qr-assembly-card">
          <p class="qr-eyebrow">Formulario de participante</p>
          <h2>${h(event.title || "Asamblea")}</h2>
          <p class="qr-muted">${h(settings.public_note || event.description || "Completa tus datos para quedar registrado en la asamblea.")}</p>
          ${registered}
          <div class="qr-assembly-form">
            <div class="qr-assembly-grid">${fieldHtml}</div>
            <button class="qr-btn" type="button" data-assembly-submit>${state.assemblyAttendee?.id ? "Actualizar registro" : "Enviar registro"}</button>
          </div>
        </div>
        <aside class="qr-assembly-card qr-assembly-summary">
          <p class="qr-eyebrow">Contexto</p>
          <h2>${h(publicData.assembly_type_label || "Asamblea")}</h2>
          <div class="qr-assembly-chip"><span>QR asignado</span><strong>${h(state.table)}</strong></div>
          <div class="qr-assembly-chip"><span>Estado</span><strong>${h(event.status || "active")}</strong></div>
          <div class="qr-assembly-chip"><span>Quorum base</span><strong>${h(event.quorum_total || 0)}</strong></div>
          <div class="qr-access-note">Este registro alimenta el modulo Asambleas para asistentes, acta y PDF. El modulo QR solo controla cantidad, clave y acceso.</div>
        </aside>
      </section>
    `;
  }

  function assemblyActaGateHtml() {
    const event = state.assemblyEvent || {};
    const settings = event.settings || {};
    const url = assemblyActUrl();
    const read = assemblyActRead();
    return `
      <section class="qr-assembly">
        <div class="qr-assembly-card">
          <p class="qr-eyebrow">Acta previa</p>
          <h2>${h(event.title || "Asamblea")}</h2>
          <p class="qr-muted">${h(event.description || settings.public_note || "Lee el acta o documento adjunto antes de continuar a las decisiones.")}</p>
          <div class="qr-msg">Registro recibido. Antes de votar, revisa el acta adjunta.</div>
          <div class="qr-assembly-summary" style="margin-top:12px">
            <div class="qr-assembly-chip"><span>Participante</span><strong>${h(state.assemblyAttendee?.attendee_name || state.table)}</strong></div>
            <div class="qr-assembly-chip"><span>Documento</span><strong>${h(state.assemblyAttendee?.document_ref || "Registrado")}</strong></div>
          </div>
          <div class="qr-assembly-form">
            ${url ? `<button class="qr-btn secondary" type="button" data-assembly-acta-download="${h(url)}">Descargar acta</button>` : `<div class="qr-access-note">Aun no hay acta adjunta desde el panel. Puedes continuar cuando el operador la publique o avanzar sin adjunto.</div>`}
            <button class="qr-btn" type="button" data-assembly-continue ${read ? "" : "disabled"}>${read ? "Continuar a decisiones" : "Descarga el acta para continuar"}</button>
          </div>
        </div>
        <aside class="qr-assembly-card qr-assembly-summary">
          <p class="qr-eyebrow">Contexto</p>
          <h2>${h(state.assemblyPublic?.assembly_type_label || "Asamblea")}</h2>
          <div class="qr-assembly-chip"><span>QR</span><strong>${h(state.table)}</strong></div>
          <div class="qr-assembly-chip"><span>Participantes</span><strong>${h(state.assemblySummary?.present || state.assemblySummary?.attendees || 0)}</strong></div>
          <div class="qr-assembly-chip"><span>Quorum</span><strong>${h(state.assemblySummary?.quorum_percent || 0)}%</strong></div>
        </aside>
      </section>
    `;
  }

  function assemblyVoteClosed(vote = {}) {
    return String(state.assemblyEvent?.status || "").toLowerCase() === "closed" || vote.status === "closed" || (vote.closes_at && secondsUntil(vote.closes_at) <= 0);
  }

  function assemblyDecisionBoardHtml() {
    const event = state.assemblyEvent || {};
    const settings = event.settings || {};
    const summary = state.assemblySummary || {};
    const votes = Array.isArray(state.assemblyVotes) ? state.assemblyVotes : [];
    const totals = assemblyDecisionTotals();
    const answered = votes.filter((vote) => state.assemblyResponses?.[vote.id]).length;
    const reportUrl = assemblyPublicReportUrl();
    const isClosed = String(event.status || "").toLowerCase() === "closed";
    const voteCards = votes.length ? votes.map((vote, index) => assemblyVoteCardHtml(vote, index + 1)).join("") : `<div class="qr-empty">Aun no hay decisiones publicadas. Cuando el panel active una pregunta, aparecera aqui.</div>`;
    const responseList = votes
      .map((vote) => {
        const response = state.assemblyResponses?.[vote.id];
        if (!response) return "";
        return `<div class="qr-assembly-chip"><span>${h(vote.title || "Decision")}</span><strong>${h(response.choice_label || response.choice_key)}</strong></div>`;
      })
      .filter(Boolean)
      .join("");
    return `
      <section class="qr-assembly-card is-wide" data-assembly-live>
        <p class="qr-eyebrow">Asamblea en curso</p>
        <h2>${h(event.title || "Asamblea")}</h2>
        <p class="qr-muted">${h(event.description || settings.public_note || "Responde las decisiones activas desde este QR.")}</p>
        <div class="qr-assembly-kpis">
          <div class="qr-assembly-kpi"><span>Participantes</span><strong>${h(summary.present || summary.attendees || 0)}</strong></div>
          <div class="qr-assembly-kpi"><span>A favor</span><strong>${h(totals.favorPct)}%</strong></div>
          <div class="qr-assembly-kpi"><span>En desacuerdo</span><strong>${h(totals.againstPct)}%</strong></div>
          <div class="qr-assembly-kpi"><span>No participa</span><strong>${h(totals.abstainPct)}%</strong></div>
        </div>
        <div class="qr-asm-split">
          <div class="qr-vote-list">${voteCards}</div>
          <aside class="qr-asm-side">
            <div class="qr-asm-participation">
              <div class="qr-assembly-chip"><span>Tu participacion</span><strong>${h(answered)} / ${h(votes.length)} decisiones</strong></div>
              <div class="qr-assembly-chip"><span>QR</span><strong>${h(state.table)}</strong></div>
              <div class="qr-assembly-chip"><span>Asistente</span><strong>${h(state.assemblyAttendee?.attendee_name || "Registrado")}</strong></div>
              <div class="qr-asm-summary-list">${responseList || `<div class="qr-access-note">Tus respuestas quedaran registradas aqui durante la asamblea.</div>`}</div>
              ${isClosed && reportUrl ? `<button class="qr-btn secondary" type="button" data-assembly-public-report>Descargar acta publica</button>` : ""}
            </div>
          </aside>
        </div>
      </section>
    `;
  }

  function assemblyVoteCardHtml(vote = {}, position = 1) {
    const options = Array.isArray(vote.options) ? vote.options : [];
    const response = state.assemblyResponses?.[vote.id] || null;
    const question = state.assemblyParticipantQuestions?.[vote.id] || null;
    const closed = assemblyVoteClosed(vote);
    const domId = assemblyVoteDomId(vote.id);
    const currentChoice = document.querySelector(`input[name="asmVoteChoice_${domId}"]:checked`)?.value || response?.choice_key || "";
    const currentQuestion = document.getElementById(`asmVoteQuestion_${domId}`)?.value ?? question?.question ?? "";
    return `
      <article class="qr-asm-vote-card">
        <div class="qr-asm-vote-head">
          <div>
            <p class="qr-eyebrow">Decision ${h(position)}</p>
            <h3>${h(vote.title || "Pregunta de asamblea")}</h3>
          </div>
          <div class="qr-asm-clock" data-asm-clock="${h(vote.closes_at || "")}">${closed ? "Tiempo cerrado" : `Cierra en ${h(countdown(secondsUntil(vote.closes_at)))}`}</div>
        </div>
        <div class="qr-asm-options">
          ${options.map((option) => `
            <label class="qr-asm-choice">
              <div class="qr-asm-choice-top">
                <span><input type="radio" name="asmVoteChoice_${h(domId)}" value="${h(option.key)}" ${currentChoice === option.key ? "checked" : ""} ${closed ? "disabled" : ""}> ${h(option.label)}</span>
                <b>${h(option.percent || 0)}%</b>
              </div>
              <div class="qr-asm-bar"><i style="width:${Math.min(100, Math.max(0, Number(option.percent || 0)))}%"></i></div>
            </label>
          `).join("")}
        </div>
        <label class="qr-asm-question">
          <span>Pregunta u observacion maximo 300 caracteres</span>
          <textarea id="asmVoteQuestion_${h(domId)}" maxlength="300" placeholder="Escribe tu pregunta para esta decision..." ${closed ? "disabled" : ""}>${h(currentQuestion)}</textarea>
        </label>
        ${response ? `<div class="qr-msg">Respuesta registrada: ${h(response.choice_label || response.choice_key)}${question?.question ? " - Pregunta enviada" : ""}</div>` : ""}
        <button class="qr-btn" type="button" data-assembly-vote-submit="${h(vote.id)}" ${closed ? "disabled" : ""}>${response ? "Actualizar respuesta" : "Enviar respuesta"}</button>
      </article>
    `;
  }

  function paintCampaignHost() {
    const host = document.getElementById("qrCampaignHost025F");
    if (host) host.innerHTML = `${campaignHtml025G()}${scorePoolHtml025G()}${votePollHtml025O()}`;
  }

  function render() {
    injectStyles();
    const b = brand();
    const companyName = state.company.name || state.company.company_name || "CLONEXA";
    document.title = `${companyName} | ${state.table}`;

    if (!state.companyId) {
      app.innerHTML = `<main class="qr-shell"><div class="qr-msg err">Falta company_id en el QR.</div></main>`;
      return;
    }

    if (state.loading) {
      app.innerHTML = `<main class="qr-shell"><section class="qr-hero"><div><p class="qr-eyebrow">${h(assemblyAccessLabel())}</p><h1>${h(state.table)}</h1><p class="qr-muted">Cargando acceso...</p></div></section></main>`;
      return;
    }

    if (!state.access?.unlocked) {
      app.innerHTML = `
        <main class="qr-shell qr-shell-locked">
          <section class="qr-hero qr-hero-locked">
            <div>
              <p class="qr-eyebrow">${h(assemblyAccessLabel())}</p>
              <h1>${h(state.table)}</h1>
              <p class="qr-muted">${h(companyName)} - ${isAssemblyMode() ? "acceso protegido para participar en esta asamblea." : "acceso protegido para ordenar desde esta mesa."}</p>
            </div>
            <div class="qr-logo">${b.logo ? `<img src="${h(b.logo)}" alt="${h(companyName)}">` : h(companyName.slice(0, 1).toUpperCase())}</div>
          </section>
          ${state.message ? `<div class="qr-msg">${h(state.message)}</div>` : ""}
          ${state.error ? `<div class="qr-msg err">${h(state.error)}</div>` : ""}
          ${accessGateHtml()}
        </main>
      `;
      setTimeout(() => document.getElementById("qrAccessCode025B")?.focus(), 0);
      return;
    }

    if (isAssemblyMode()) {
      app.innerHTML = `
        <main class="qr-shell">
          <section class="qr-hero">
            <div>
              <p class="qr-eyebrow">Participante QR</p>
              <h1>${h(state.table)}</h1>
              <p class="qr-muted">${h(companyName)} - completa tu registro para la asamblea.</p>
            </div>
            <div class="qr-logo">${b.logo ? `<img src="${h(b.logo)}" alt="${h(companyName)}">` : h(companyName.slice(0, 1).toUpperCase())}</div>
          </section>
          ${state.message ? `<div class="qr-msg">${h(state.message)}</div>` : ""}
          ${state.error ? `<div class="qr-msg err">${h(state.error)}</div>` : ""}
          ${assemblyPublicFormHtml()}
        </main>
      `;
      return;
    }

    const categories = productCategories();
    const products = visibleProducts();
    const categoryButtons = categories.map((item) => `
      <button class="qr-category ${item.name === state.category ? "active" : ""}" type="button" data-category="${h(item.name)}">
        ${h(item.name)} <small>${h(item.count)}</small>
      </button>
    `).join("");
    const productCards = products.length
      ? products.map((item) => `
          <article class="qr-card">
            <div>
              <div class="qr-product-name">${h(item.name)}</div>
              <div class="qr-stock">${h(productCategory(item))}</div>
              <div class="qr-stock">Stock ${h(item.stock ?? 0)}</div>
            </div>
            <div class="qr-price">${Number(item.price || 0) > 0 ? h(money(item.price)) : "Por confirmar"}</div>
            <button class="qr-btn" type="button" data-add="${h(item.id)}">Agregar</button>
          </article>
        `).join("")
      : `<div class="qr-empty">${state.inventory.length ? "No encontramos productos con ese filtro." : "No hay productos activos para esta mesa."}</div>`;

    app.innerHTML = `
      <main class="qr-shell">
        <section class="qr-hero">
          <div>
            <p class="qr-eyebrow">Mesa QR</p>
            <h1>${h(state.table)}</h1>
            <p class="qr-muted">${h(companyName)} - arma tu pedido y queda en pendiente para el barman.</p>
          </div>
          <div class="qr-logo">${b.logo ? `<img src="${h(b.logo)}" alt="${h(companyName)}">` : h(companyName.slice(0, 1).toUpperCase())}</div>
        </section>

        ${state.message ? `<div class="qr-msg">${h(state.message)}</div>` : ""}
        ${state.error ? `<div class="qr-msg err">${h(state.error)}</div>` : ""}
        <div id="qrCampaignHost025F">${campaignHtml025G()}${scorePoolHtml025G()}${votePollHtml025O()}</div>

        <section class="qr-layout">
          <div class="qr-menu">
            <div class="qr-menu-head">
              <div>
                <p class="qr-eyebrow">Menu</p>
                <h2 class="qr-menu-title">Elige por categoria</h2>
              </div>
              <input id="qrSearch024X" class="qr-search" placeholder="Buscar producto" value="${h(state.search)}" autocomplete="off">
            </div>
            <div class="qr-categories">${categoryButtons}</div>
            <div class="qr-menu-meta">${h(products.length)} de ${h(state.inventory.length)} productos visibles</div>
            <div class="qr-products">${productCards}</div>
          </div>
          <aside class="qr-cart">
            <h2>Tu pedido</h2>
            <label class="qr-field">
              <span>Nombre</span>
              <input id="qrCustomer024S" placeholder="Ej: Javier" value="${h(document.getElementById("qrCustomer024S")?.value || "")}">
            </label>
            <div id="qrCartLines024S">${cartRows()}</div>
            <label class="qr-field">
              <span>Canciones</span>
              <input id="qrSongs024S" placeholder="Ej: Salsa choque, Provenza" value="${h(document.getElementById("qrSongs024S")?.value || "")}">
            </label>
            <label class="qr-field">
              <span>Notas</span>
              <textarea id="qrNotes024S" placeholder="Sin hielo, poco dulce...">${h(document.getElementById("qrNotes024S")?.value || "")}</textarea>
            </label>
            <div class="qr-total"><span>Total</span><strong>${cartTotal() > 0 ? h(money(cartTotal())) : "Por confirmar"}</strong></div>
            <button class="qr-btn" type="button" data-submit-order>Enviar pedido</button>
            <button class="qr-btn secondary" type="button" data-clear-cart>Limpiar</button>
          </aside>
        </section>
      </main>
    `;
  }

  function addItem(id) {
    const item = state.inventory.find((row) => String(row.id) === String(id));
    if (!item) return;
    const current = state.cart.get(String(id)) || {
      id: String(item.id),
      name: item.name,
      sku: item.sku || "",
      price: Number(item.price || item.unit_price || item.sale_price || 0) || 0,
      quantity: 0,
    };
    current.quantity += 1;
    state.cart.set(String(id), current);
    state.message = "";
    state.error = "";
    render();
  }

  function updateQty(id, delta) {
    const current = state.cart.get(String(id));
    if (!current) return;
    current.quantity += delta;
    if (current.quantity <= 0) state.cart.delete(String(id));
    else state.cart.set(String(id), current);
    render();
  }

  async function submitOrder() {
    if (!state.access?.unlocked) {
      state.error = "Activa la mesa con la clave antes de enviar pedidos.";
      state.message = "";
      render();
      return;
    }
    const items = [...state.cart.values()].filter((item) => Number(item.quantity || 0) > 0);
    if (!items.length) {
      state.error = "Agrega al menos un producto.";
      state.message = "";
      render();
      return;
    }

    try {
      state.error = "";
      state.message = "Enviando pedido...";
      render();
      const customer = document.getElementById("qrCustomer024S")?.value || "Cliente mesa";
      const songs = document.getElementById("qrSongs024S")?.value || "";
      const notes = document.getElementById("qrNotes024S")?.value || "";
      const payload = {
        table: state.table,
        customer,
        source: "qr",
        access_code: state.access.code || sessionStorage.getItem(accessStorageKey()) || "",
        songs,
        notes,
        items: items.map((item) => ({
          inventory_item_id: item.id,
          product_id: item.id,
          sku: item.sku || "",
          name: item.name,
          quantity: item.quantity,
          unit_price: item.price,
        })),
      };
      const response = await api(`/hospitality/companies/${encodeURIComponent(state.companyId)}/orders`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      state.cart.clear();
      await refreshCampaign().catch(() => {});
      state.message = `Tu pedido fue recibido. El barman ya lo tiene en pantalla: ${response.order?.order_number || "OK"}.`;
      state.error = "";
      render();
    } catch (error) {
      if (String(error.message || "").includes("403")) {
        sessionStorage.removeItem(accessStorageKey());
        state.access.unlocked = false;
        state.access.code = "";
      }
      state.error = error.message || "No se pudo enviar el pedido.";
      state.message = "";
      render();
    }
  }

  async function submitAssemblyRegistration() {
    if (!state.access?.unlocked) {
      state.error = "Activa el acceso con la clave antes de registrar tus datos.";
      state.message = "";
      render();
      return;
    }
    const event = state.assemblyEvent || {};
    if (!event.id) {
      state.error = "No hay asamblea activa para recibir registros.";
      state.message = "";
      render();
      return;
    }
    const fields = Array.isArray(state.assemblyFields) ? state.assemblyFields : [];
    const values = {};
    for (const field of fields) {
      const key = String(field.key || "").trim();
      if (!key) continue;
      const value = String(document.getElementById(assemblyFieldId(key))?.value || "").trim();
      if (field.required && !value) {
        state.error = `Completa ${field.label || key}.`;
        state.message = "";
        render();
        return;
      }
      values[key] = value;
    }
    const attendeeName = values.attendee_name || values.name || values.nombre || state.table;
    const documentRef = values.document_ref || values.document || values.documento || "";
    try {
      state.error = "";
      state.message = "Guardando registro...";
      render();
      await api(`/assemblies/companies/${encodeURIComponent(state.companyId)}/events/${encodeURIComponent(event.id)}/attendees`, {
        method: "POST",
        body: JSON.stringify({
          attendee_name: attendeeName,
          document_ref: documentRef,
          qr_key: state.table,
          present: true,
          metadata: values,
        }),
      });
      const fresh = await api(`/assemblies/companies/${encodeURIComponent(state.companyId)}/public?participant=${encodeURIComponent(state.table)}`).catch(() => ({}));
      applyAssemblyPublic(fresh);
      state.message = "Registro recibido. Ya quedaste habilitado para esta asamblea.";
      state.error = "";
      render();
    } catch (error) {
      state.error = error.message || "No se pudo guardar el registro.";
      state.message = "";
      render();
    }
  }

  async function refreshCampaign() {
    const campaign = await api(`/hospitality/companies/${encodeURIComponent(state.companyId)}/loyalty-campaigns/active?table=${encodeURIComponent(state.table)}`);
    state.campaign = campaign.campaign || null;
    state.participant = campaign.participant || null;
    state.scoreCampaign = campaign.score_campaign || null;
    state.scorePrediction = campaign.score_prediction || null;
    state.voteCampaign = campaign.vote_campaign || null;
    state.voteResponse = campaign.vote_response || null;
    return campaign;
  }

  async function refreshCampaignView() {
    await refreshCampaign();
    const host = document.getElementById("qrCampaignHost025F");
    if (host && host.contains(document.activeElement)) return;
    paintCampaignHost();
  }

  function applyAssemblyPublic(data = {}) {
    state.assemblyPublic = data || null;
    state.qrMode = data?.qr?.mode || state.qrMode || "hospitality";
    state.assemblyEvent = data?.event || null;
    state.assemblyFields = Array.isArray(data?.fields) ? data.fields : [];
    state.assemblyAttendee = data?.attendee || null;
    state.assemblySummary = data?.summary || {};
    state.assemblyVotes = Array.isArray(data?.votes) ? data.votes : [];
    state.assemblyQuestions = Array.isArray(data?.questions) ? data.questions : [];
    state.assemblyResponses = data?.participant_responses || {};
    state.assemblyParticipantQuestions = data?.participant_questions || {};
  }

  async function refreshAssemblyPublic() {
    const fresh = await api(`/assemblies/companies/${encodeURIComponent(state.companyId)}/public?participant=${encodeURIComponent(state.table)}`);
    applyAssemblyPublic(fresh || {});
    return fresh;
  }

  function assemblyLiveHasFocus() {
    const active = document.activeElement;
    return !!(active && document.querySelector("[data-assembly-live]")?.contains(active));
  }

  async function refreshAssemblyPublicView() {
    await refreshAssemblyPublic();
    if (assemblyLiveHasFocus()) return;
    render();
  }

  async function submitAssemblyVote(voteId = "") {
    const vote = state.assemblyVotes.find((item) => String(item.id) === String(voteId));
    if (!vote?.id) return;
    if (assemblyVoteClosed(vote)) {
      state.error = "El tiempo de respuesta para esta decision ya cerro.";
      state.message = "";
      render();
      return;
    }
    const domId = assemblyVoteDomId(vote.id);
    const choice = document.querySelector(`input[name="asmVoteChoice_${domId}"]:checked`)?.value || "";
    if (!choice) {
      state.error = "Selecciona una respuesta antes de enviar.";
      state.message = "";
      render();
      return;
    }
    const selectedOption = (vote.options || []).find((option) => String(option.key) === String(choice)) || {};
    const question = String(document.getElementById(`asmVoteQuestion_${domId}`)?.value || "").trim().slice(0, 300);
    try {
      await api(`/assemblies/companies/${encodeURIComponent(state.companyId)}/votes/${encodeURIComponent(vote.id)}/responses`, {
        method: "POST",
        body: JSON.stringify({
          qr_key: state.table,
          voter_name: state.assemblyAttendee?.attendee_name || state.table,
          choice_key: choice,
          choice_label: selectedOption.label || choice,
        }),
      });
      if (question && state.assemblyEvent?.id) {
        await api(`/assemblies/companies/${encodeURIComponent(state.companyId)}/events/${encodeURIComponent(state.assemblyEvent.id)}/questions`, {
          method: "POST",
          body: JSON.stringify({
            vote_id: vote.id,
            participant_name: state.assemblyAttendee?.attendee_name || state.table,
            qr_key: state.table,
            question,
            status: "pending",
          }),
        });
      }
      await refreshAssemblyPublic();
      state.message = "Respuesta registrada. La asamblea ya recibio tu decision.";
      state.error = "";
      render();
    } catch (error) {
      state.error = error.message || "No se pudo registrar la respuesta.";
      state.message = "";
      render();
    }
  }

  async function load() {
    try {
      const [company, branding, access, assemblyPublic] = await Promise.all([
        api(`/companies/${encodeURIComponent(state.companyId)}`),
        api(`/companies/${encodeURIComponent(state.companyId)}/branding`).catch(() => ({})),
        api(`/hospitality/companies/${encodeURIComponent(state.companyId)}/qr-tables/access?table=${encodeURIComponent(state.table)}`).catch(() => ({})),
        api(`/assemblies/companies/${encodeURIComponent(state.companyId)}/public?participant=${encodeURIComponent(state.table)}`).catch(() => ({})),
      ]);
      state.company = company || {};
      state.branding = branding.branding || branding || {};
      applyAssemblyPublic(assemblyPublic || {});
      if (isAssemblyMode()) {
        state.inventory = [];
        state.campaign = null;
        state.participant = null;
        state.scoreCampaign = null;
        state.scorePrediction = null;
        state.voteCampaign = null;
        state.voteResponse = null;
      } else {
        const [inventory, campaign] = await Promise.all([
          api(`/hospitality/companies/${encodeURIComponent(state.companyId)}/inventory-lite?limit=300`),
          api(`/hospitality/companies/${encodeURIComponent(state.companyId)}/loyalty-campaigns/active?table=${encodeURIComponent(state.table)}`).catch(() => ({})),
        ]);
        state.inventory = Array.isArray(inventory.inventory) ? inventory.inventory : [];
        state.campaign = campaign.campaign || null;
        state.participant = campaign.participant || null;
        state.scoreCampaign = campaign.score_campaign || null;
        state.scorePrediction = campaign.score_prediction || null;
        state.voteCampaign = campaign.vote_campaign || null;
        state.voteResponse = campaign.vote_response || null;
      }
      state.access = {
        active: access.access?.active === true,
        unlocked: false,
        code: "",
        expires_at: access.access?.expires_at || "",
      };
      const storedCode = sessionStorage.getItem(accessStorageKey()) || "";
      if (state.access.active && storedCode) {
        try {
          await verifyTableAccess(storedCode, { silent: true });
        } catch (_) {
          sessionStorage.removeItem(accessStorageKey());
        }
      }
      state.loading = false;
      state.error = "";
    } catch (error) {
      state.loading = false;
      state.error = error.message || "No se pudo cargar la mesa.";
    }
    render();
  }

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;

    if (target.closest("[data-campaign-dismiss]")) {
      state.campaignDismissed = true;
      render();
      return;
    }
    if (target.closest("[data-campaign-join]")) {
      joinCampaign();
      return;
    }
    if (target.closest("[data-score-submit]")) {
      submitScorePrediction();
      return;
    }
    if (target.closest("[data-vote-submit]")) {
      submitVotePoll025O();
      return;
    }
    if (target.closest("[data-assembly-submit]")) {
      submitAssemblyRegistration();
      return;
    }
    const actaButton = target.closest("[data-assembly-acta-download]");
    if (actaButton) {
      const url = actaButton.getAttribute("data-assembly-acta-download") || assemblyActUrl();
      if (url) window.open(url, "_blank", "noopener,noreferrer");
      localStorage.setItem(assemblyEventStorageKey("acta"), "ok");
      state.message = "Acta descargada. Ya puedes continuar a las decisiones.";
      state.error = "";
      render();
      return;
    }
    if (target.closest("[data-assembly-continue]")) {
      if (!assemblyActRead()) {
        state.error = "Primero descarga el acta adjunta para continuar.";
        state.message = "";
        render();
        return;
      }
      localStorage.setItem(assemblyEventStorageKey("continue"), "ok");
      state.message = "Ya puedes responder las decisiones publicadas.";
      state.error = "";
      refreshAssemblyPublic().catch(() => {}).finally(() => render());
      return;
    }
    if (target.closest("[data-assembly-public-report]")) {
      const url = assemblyPublicReportUrl();
      if (url) window.open(url, "_blank", "noopener,noreferrer");
      return;
    }
    const assemblyVoteButton = target.closest("[data-assembly-vote-submit]");
    if (assemblyVoteButton) {
      submitAssemblyVote(assemblyVoteButton.getAttribute("data-assembly-vote-submit") || "");
      return;
    }
    if (target.closest("[data-access-verify]")) {
      verifyTableAccess(document.getElementById("qrAccessCode025B")?.value || "").catch((error) => {
        state.error = error.message || "Clave de mesa invalida.";
        state.message = "";
        render();
      });
      return;
    }
    const category = target.closest("[data-category]");
    if (category) {
      state.category = category.getAttribute("data-category") || "Todos";
      state.error = "";
      state.message = "";
      render();
      return;
    }
    const add = target.closest("[data-add]");
    if (add) {
      addItem(add.getAttribute("data-add"));
      return;
    }
    const inc = target.closest("[data-inc]");
    if (inc) {
      updateQty(inc.getAttribute("data-inc"), 1);
      return;
    }
    const dec = target.closest("[data-dec]");
    if (dec) {
      updateQty(dec.getAttribute("data-dec"), -1);
      return;
    }
    if (target.closest("[data-clear-cart]")) {
      state.cart.clear();
      state.message = "";
      state.error = "";
      render();
      return;
    }
    if (target.closest("[data-submit-order]")) {
      submitOrder();
    }
  });

  document.addEventListener("input", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) return;
    if (target.id !== "qrSearch024X") return;
    state.search = target.value;
    state.error = "";
    state.message = "";
    render();
    const search = document.getElementById("qrSearch024X");
    if (search instanceof HTMLInputElement) {
      search.focus();
      const end = search.value.length;
      search.setSelectionRange(end, end);
    }
  });

  document.addEventListener("keydown", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) return;
    if (target.id === "qrAccessCode025B" && event.key === "Enter") {
      event.preventDefault();
      verifyTableAccess(target.value || "").catch((error) => {
        state.error = error.message || "Clave de mesa invalida.";
        state.message = "";
        render();
      });
    }
  });

  async function verifyTableAccess(code, options = {}) {
    const cleanCode = String(code || "").trim().toUpperCase();
    if (!cleanCode) {
      state.error = "Ingresa la clave de la mesa.";
      state.message = "";
      if (!options.silent) render();
      throw new Error(state.error);
    }
    let data;
    try {
      data = await api(`/hospitality/companies/${encodeURIComponent(state.companyId)}/qr-tables/access/verify`, {
        method: "POST",
        body: JSON.stringify({ table: state.table, access_code: cleanCode }),
      });
    } catch (error) {
      const raw = String(error.message || "");
      if (raw.includes("mesa_no_activada")) throw new Error("Esta mesa aun no tiene clave activa. Pide al bar activar mesa.");
      if (raw.includes("clave_de_mesa_invalida")) throw new Error("Clave incorrecta. Revisa el codigo entregado por el bar.");
      throw error;
    }
    state.access = {
      active: data.access?.active === true,
      unlocked: true,
      code: cleanCode,
      expires_at: data.access?.expires_at || "",
    };
    sessionStorage.setItem(accessStorageKey(), cleanCode);
    state.error = "";
    if (!options.silent) state.message = isAssemblyMode() ? "Acceso activado. Completa tus datos para participar." : "Mesa activada. Ya puedes realizar tu pedido.";
    if (!options.silent) render();
    return data;
  }

  async function joinCampaign() {
    if (!state.campaign?.id) return;
    try {
      state.error = "";
      const teamName = document.getElementById("qrTeam024Z")?.value || `Equipo ${state.table}`;
      const data = await api(`/hospitality/companies/${encodeURIComponent(state.companyId)}/loyalty-campaigns/${encodeURIComponent(state.campaign.id)}/participants`, {
        method: "POST",
        body: JSON.stringify({ table: state.table, team_name: teamName, accepted: true }),
      });
      state.campaign = data.campaign || state.campaign;
      state.participant = data.participant || null;
      state.message = "Inscripcion recibida. Tu mesa ya participa en el sorteo.";
      render();
    } catch (error) {
      state.error = error.message || "No se pudo inscribir la mesa.";
      render();
    }
  }

  async function submitScorePrediction() {
    if (!state.scoreCampaign?.id) return;
    if (!state.access?.unlocked) {
      state.error = "Activa la mesa con la clave antes de enviar marcador.";
      state.message = "";
      render();
      return;
    }
    try {
      const scoreA = Number(document.getElementById("qrScoreA025G")?.value || 0);
      const scoreB = Number(document.getElementById("qrScoreB025G")?.value || 0);
      const teamName = document.getElementById("qrScoreName025G")?.value || state.table;
      const data = await api(`/hospitality/companies/${encodeURIComponent(state.companyId)}/loyalty-score-pools/${encodeURIComponent(state.scoreCampaign.id)}/predictions`, {
        method: "POST",
        body: JSON.stringify({
          table: state.table,
          team_name: teamName,
          score_a: Number.isFinite(scoreA) ? scoreA : 0,
          score_b: Number.isFinite(scoreB) ? scoreB : 0,
          access_code: state.access.code || sessionStorage.getItem(accessStorageKey()) || "",
        }),
      });
      state.campaign = data.campaign || state.campaign;
      state.participant = data.participant || state.participant;
      state.scoreCampaign = data.score_campaign || state.scoreCampaign;
      state.scorePrediction = data.score_prediction || null;
      state.message = "Marcador registrado para la polla.";
      state.error = "";
      render();
    } catch (error) {
      state.error = error.message || "No se pudo enviar el marcador.";
      state.message = "";
      render();
    }
  }

  async function submitVotePoll025O() {
    if (!state.voteCampaign?.id) return;
    if (!state.access?.unlocked) {
      state.error = "Activa la mesa con la clave antes de participar.";
      state.message = "";
      render();
      return;
    }
    try {
      const mode = state.voteCampaign.vote_mode || "registration";
      const selected = mode === "registration"
        ? "registered"
        : document.querySelector("input[name='qrVoteOption025O']:checked")?.value || "";
      if (!selected) {
        state.error = "Selecciona una respuesta.";
        state.message = "";
        render();
        return;
      }
      const voterName = document.getElementById("qrVoteName025O")?.value || state.table;
      const data = await api(`/hospitality/companies/${encodeURIComponent(state.companyId)}/loyalty-vote-polls/${encodeURIComponent(state.voteCampaign.id)}/votes`, {
        method: "POST",
        body: JSON.stringify({
          table: state.table,
          voter_name: voterName,
          answer_key: selected,
          access_code: state.access.code || sessionStorage.getItem(accessStorageKey()) || "",
        }),
      });
      state.campaign = data.campaign || state.campaign;
      state.participant = data.participant || state.participant;
      state.scoreCampaign = data.score_campaign || state.scoreCampaign;
      state.scorePrediction = data.score_prediction || state.scorePrediction;
      state.voteCampaign = data.vote_campaign || state.voteCampaign;
      state.voteResponse = data.vote_response || null;
      state.message = mode === "registration" ? "Inscripcion recibida." : "Respuesta registrada.";
      state.error = "";
      render();
    } catch (error) {
      state.error = error.message || "No se pudo enviar el concurso.";
      state.message = "";
      render();
    }
  }

  setInterval(() => {
    if (state.campaign && Number.isFinite(Number(state.campaign.signup_seconds_left))) {
      state.campaign.signup_seconds_left = Math.max(0, Number(state.campaign.signup_seconds_left || 0) - 1);
      const signupClock = document.getElementById("qrSignupClock025A");
      if (signupClock) signupClock.textContent = countdown(state.campaign.signup_seconds_left);
      if (state.campaign.signup_seconds_left === 0 && state.campaign.registration_open) {
        state.campaign.registration_open = false;
        if (state.access?.unlocked) render();
      }
    }
    if (state.campaign && Number.isFinite(Number(state.campaign.tournament_seconds_left))) {
      state.campaign.tournament_seconds_left = Math.max(0, Number(state.campaign.tournament_seconds_left || 0) - 1);
      const tournamentClock = document.getElementById("qrTournamentClock025A");
      if (tournamentClock) tournamentClock.textContent = countdown(state.campaign.tournament_seconds_left);
      const campaignKey = String(state.campaign.id || "sin-campana");
      if (state.campaign.tournament_seconds_left === 0 && state.campaignEndRefreshKey !== campaignKey) {
        state.campaignEndRefreshKey = campaignKey;
        state.campaign._endRefreshDone = true;
        refreshCampaign().then(() => {
          if (state.campaign) state.campaign._endRefreshDone = true;
          if (state.access?.unlocked) paintCampaignHost();
        }).catch(() => {});
      }
    }
    if (state.voteCampaign && Number.isFinite(Number(state.voteCampaign.seconds_left))) {
      state.voteCampaign.seconds_left = Math.max(0, Number(state.voteCampaign.seconds_left || 0) - 1);
      const voteClock = document.getElementById("qrVoteClock025O");
      if (voteClock) voteClock.textContent = countdown(state.voteCampaign.seconds_left);
      if (state.voteCampaign.seconds_left === 0 && state.voteCampaign.phase !== "closed") {
        state.voteCampaign.phase = "closed";
        if (state.access?.unlocked && !document.getElementById("qrCampaignHost025F")?.contains(document.activeElement)) {
          paintCampaignHost();
        }
      }
    }
    if (isAssemblyMode() && state.access?.unlocked && assemblyCanShowDecisions()) {
      document.querySelectorAll("[data-asm-clock]").forEach((clock) => {
        const value = clock.getAttribute("data-asm-clock") || "";
        const seconds = secondsUntil(value);
        clock.textContent = seconds > 0 ? `Cierra en ${countdown(seconds)}` : "Tiempo cerrado";
      });
    }
  }, 1000);

  setInterval(() => {
    if ((!state.campaign && !state.scoreCampaign && !state.voteCampaign) || !state.access?.unlocked) return;
    refreshCampaignView().catch(() => {});
  }, 6000);

  setInterval(() => {
    if (!isAssemblyMode() || !state.access?.unlocked || !assemblyCanShowDecisions()) return;
    if (assemblyLiveHasFocus()) return;
    refreshAssemblyPublicView().catch(() => {});
  }, 6000);

  render();
  load();
})();
