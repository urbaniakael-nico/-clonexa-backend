
(() => {
  "use strict";

  const API = "/api/v1";

  const state = {
    company: null,
    experience: null,
    branding: null,
    companyId: null,
    companyModules: [],
    personalHistoryRows: [],
    dashboardMetrics: {},
  };

  const h = (value) =>
    String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");

  const $ = (id) => document.getElementById(id);

  async function api(path, options = {}) {
    const res = await fetch(`${API}${path}`, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${res.status} ${res.statusText} ${text}`);
    }

    return res.json();
  }

  function companyIdFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return params.get("company_id") || params.get("companyId") || params.get("tenant") || "";
  }

  function validHex(value, fallback) {
    const v = String(value || "").trim();
    return /^#[0-9a-fA-F]{3}$/.test(v) || /^#[0-9a-fA-F]{6}$/.test(v) ? v : fallback;
  }

  function normalizeBranding(raw = {}) {
    const allowedStyles = ["aurora_boreal", "neon_profundo", "holografico", "cyber_grid"];
    const allowedFonts = ["Inter", "Manrope", "Sora", "Space Grotesk", "Rajdhani", "Orbitron", "Poppins", "Montserrat"];
    const allowedCards = ["glass_premium", "neon_border", "soft_solid", "dark_elevated"];

    const backgroundStyle = allowedStyles.includes(String(raw.background_style || "").trim())
      ? String(raw.background_style).trim()
      : "aurora_boreal";

    const fontFamily = allowedFonts.includes(String(raw.font_family || "").trim())
      ? String(raw.font_family).trim()
      : "Inter";

    const cardStyle = allowedCards.includes(String(raw.card_style || "").trim())
      ? String(raw.card_style).trim()
      : "glass_premium";

    return {
      logo_url: String(raw.logo_url || "").trim(),
      primary_color: validHex(raw.primary_color || raw.color_principal, "#ff2bd6"),
      secondary_color: validHex(raw.secondary_color || raw.color_secundario, "#00ff88"),
      background_color: validHex(raw.background_color || raw.color_fondo, "#050509"),
      text_color: validHex(raw.text_color || raw.color_texto, "#f8fafc"),
      visual_preset: "custom",
      background_style: backgroundStyle,
      font_family: fontFamily,
      card_style: cardStyle,
      mode: "dark",
      theme_mode: "dark",
    };
  }

  function brandingBackground(b) {
    if (b.background_style === "holografico") {
      return `
        radial-gradient(circle at 0% 0%, ${b.primary_color}88, transparent 32%),
        radial-gradient(circle at 100% 0%, ${b.secondary_color}66, transparent 34%),
        radial-gradient(circle at 50% 100%, ${b.background_color}88, transparent 40%),
        linear-gradient(135deg, ${b.background_color}, ${b.primary_color})
      `;
    }

    if (b.background_style === "cyber_grid") {
      return `
        linear-gradient(rgba(255,255,255,.055) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,.045) 1px, transparent 1px),
        radial-gradient(circle at 85% 0%, ${b.secondary_color}55, transparent 34%),
        linear-gradient(135deg, ${b.background_color}, #020617)
      `;
    }

    if (b.background_style === "neon_profundo") {
      return `
        radial-gradient(circle at 12% 8%, ${b.primary_color}66, transparent 34%),
        radial-gradient(circle at 88% 12%, ${b.secondary_color}44, transparent 34%),
        linear-gradient(135deg, ${b.background_color}, #050509)
      `;
    }

    return `
      radial-gradient(circle at 0% 0%, ${b.primary_color}55, transparent 32%),
      radial-gradient(circle at 100% 0%, ${b.secondary_color}44, transparent 32%),
      linear-gradient(135deg, ${b.background_color}, ${b.secondary_color}22)
    `;
  }

  function fontProfile(b) {
    const map = {
      Inter: {
        family: "Inter, system-ui, sans-serif",
        spacing: "-.03em",
        label: ".16em",
        weight: "800",
        transform: "none",
        shadow: "none",
        stroke: "0",
        skew: "0deg",
      },
      Manrope: {
        family: "Manrope, Trebuchet MS, system-ui, sans-serif",
        spacing: "-.045em",
        label: ".14em",
        weight: "900",
        transform: "none",
        shadow: `0 12px 38px ${b.primary_color}33`,
        stroke: "0",
        skew: "0deg",
      },
      Sora: {
        family: "Sora, Arial Black, system-ui, sans-serif",
        spacing: ".015em",
        label: ".22em",
        weight: "900",
        transform: "uppercase",
        shadow: `0 0 18px ${b.secondary_color}77`,
        stroke: ".25px",
        skew: "-1deg",
      },
      "Space Grotesk": {
        family: "Courier New, monospace",
        spacing: ".13em",
        label: ".34em",
        weight: "900",
        transform: "uppercase",
        shadow: `0 0 22px ${b.primary_color}, 0 0 46px ${b.secondary_color}55`,
        stroke: ".45px",
        skew: "-2deg",
      },
      Rajdhani: {
        family: "Arial Narrow, Impact, system-ui, sans-serif",
        spacing: ".08em",
        label: ".3em",
        weight: "900",
        transform: "uppercase",
        shadow: `0 0 18px ${b.primary_color}88`,
        stroke: ".35px",
        skew: "-4deg",
      },
      Orbitron: {
        family: "Courier New, monospace",
        spacing: ".2em",
        label: ".42em",
        weight: "900",
        transform: "uppercase",
        shadow: `0 0 14px ${b.secondary_color}, 0 0 34px ${b.primary_color}, 0 0 70px ${b.primary_color}88`,
        stroke: ".9px",
        skew: "-3deg",
      },
      Poppins: {
        family: "Poppins, Segoe UI, system-ui, sans-serif",
        spacing: "-.035em",
        label: ".14em",
        weight: "800",
        transform: "none",
        shadow: `0 10px 32px ${b.primary_color}33`,
        stroke: "0",
        skew: "0deg",
      },
      Montserrat: {
        family: "Montserrat, Impact, Arial Black, sans-serif",
        spacing: ".06em",
        label: ".28em",
        weight: "950",
        transform: "uppercase",
        shadow: `0 0 20px ${b.secondary_color}77`,
        stroke: ".45px",
        skew: "-1deg",
      },
    };

    return map[b.font_family] || map.Inter;
  }

  function cardProfile(b) {
    if (b.card_style === "neon_border") {
      return {
        bg: `linear-gradient(145deg, ${b.primary_color}28, rgba(255,255,255,.075), ${b.secondary_color}1f)`,
        border: `1px solid ${b.primary_color}cc`,
        shadow: `0 0 44px ${b.primary_color}55, 0 28px 92px rgba(0,0,0,.36), inset 0 0 0 1px rgba(255,255,255,.08)`,
      };
    }

    if (b.card_style === "soft_solid") {
      return {
        bg: "linear-gradient(145deg, rgba(255,255,255,.88), rgba(255,255,255,.58))",
        border: "1px solid rgba(255,255,255,.78)",
        shadow: "0 24px 80px rgba(15,23,42,.18)",
      };
    }

    if (b.card_style === "dark_elevated") {
      return {
        bg: "linear-gradient(145deg, rgba(2,6,23,.94), rgba(15,23,42,.78))",
        border: "1px solid rgba(255,255,255,.16)",
        shadow: "0 32px 110px rgba(0,0,0,.55)",
      };
    }

    return {
      bg: "linear-gradient(145deg, rgba(255,255,255,.13), rgba(255,255,255,.045))",
      border: "1px solid rgba(255,255,255,.14)",
      shadow: "0 24px 80px rgba(0,0,0,.28), inset 0 0 0 1px rgba(255,255,255,.035)",
    };
  }

  function logo(company, b) {
    if (b.logo_url) {
      return `<img src="${h(b.logo_url)}" alt="${h(company.name)}" style="width:100%;height:100%;object-fit:contain;display:block" onerror="this.remove()">`;
    }

    return `<span>${h((company.name || "C").slice(0, 1).toUpperCase())}</span>`;
  }

  function applyBranding() {
    const b = normalizeBranding(state.branding || {});
    const fp = fontProfile(b);
    const cp = cardProfile(b);

    let style = $("clientBrandingDynamicStyle");
    if (!style) {
      style = document.createElement("style");
      style.id = "clientBrandingDynamicStyle";
      document.head.appendChild(style);
    }

    style.textContent = `
      :root {
        --cx-primary: ${b.primary_color};
        --cx-secondary: ${b.secondary_color};
        --cx-bg: ${b.background_color};
        --cx-text: ${b.text_color};
      }

      * {
        box-sizing: border-box;
      }

      body {
        margin: 0;
        min-height: 100vh;
        color: ${b.text_color};
        background: ${brandingBackground(b)} !important;
        font-family: ${fp.family} !important;
        overflow-x: hidden;
      }

      #app, #app * {
        font-family: ${fp.family} !important;
      }

      .client-shell {
        min-height: 100vh;
        padding: 24px;
        background:
          radial-gradient(circle at 10% 0%, ${b.primary_color}22, transparent 30%),
          radial-gradient(circle at 90% 0%, ${b.secondary_color}18, transparent 30%);
      }

      .client-layout {
        display: grid;
        grid-template-columns: 260px 1fr;
        gap: 20px;
        max-width: 1760px;
        margin: 0 auto;
      }

      .client-sidebar,
      .client-panel,
      .client-kpi,
      .client-module-card,
      .client-action-card {
        background: ${cp.bg};
        border: ${cp.border};
        box-shadow: ${cp.shadow};
        backdrop-filter: blur(22px) saturate(1.25);
      }

      .client-sidebar {
        min-height: calc(100vh - 48px);
        border-radius: 28px;
        padding: 22px;
        position: sticky;
        top: 24px;
      }

      .client-logo {
        width: 74px;
        height: 74px;
        border-radius: 22px;
        display: grid;
        place-items: center;
        overflow: hidden;
        background: linear-gradient(145deg, ${b.primary_color}, ${b.secondary_color});
        color: #020617;
        font-weight: 1000;
        box-shadow: 0 0 34px ${b.primary_color}66;
      }

      .client-company-name,
      .client-title,
      .client-panel h2,
      .client-kpi strong,
      .client-module-card strong {
        letter-spacing: ${fp.spacing};
        font-weight: ${fp.weight};
        text-transform: ${fp.transform};
        text-shadow: ${fp.shadow};
        -webkit-text-stroke: ${fp.stroke} ${b.secondary_color}99;
        transform: skewX(${fp.skew});
      }

      .client-company-name {
        margin: 18px 0 4px;
        font-size: 26px;
      }

      .client-muted {
        color: rgba(255,255,255,.68);
      }

      .client-nav {
        display: grid;
        gap: 10px;
        margin-top: 28px;
      }

      .client-nav button {
        border: 1px solid rgba(255,255,255,.16);
        background: rgba(255,255,255,.075);
        color: ${b.text_color};
        border-radius: 16px;
        padding: 14px 14px;
        text-align: left;
        cursor: pointer;
        font-weight: 900;
      }

      .client-nav button.active {
        border-color: ${b.secondary_color};
        box-shadow: 0 0 28px ${b.secondary_color}44;
      }

      .client-main {
        display: grid;
        gap: 20px;
      }

      .client-hero {
        border-radius: 30px;
        padding: 28px;
        background:
          radial-gradient(circle at 0% 0%, ${b.primary_color}44, transparent 32%),
          radial-gradient(circle at 100% 0%, ${b.secondary_color}33, transparent 32%),
          rgba(255,255,255,.065);
        border: 1px solid rgba(255,255,255,.16);
        box-shadow: 0 28px 100px rgba(0,0,0,.34);
      }

      .client-eyebrow,
      .client-label,
      .client-module-card small {
        letter-spacing: ${fp.label};
        text-transform: uppercase;
        font-weight: 1000;
        color: ${b.secondary_color};
      }

      .client-title {
        font-size: clamp(40px, 5vw, 76px);
        line-height: .92;
        margin: 12px 0;
      }

      .client-kpi-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(180px, 1fr));
        gap: 16px;
        margin-top: 22px;
      }

      .client-kpi {
        border-radius: 22px;
        padding: 20px;
      }

      .client-kpi span {
        display: block;
        opacity: .72;
        margin-bottom: 10px;
      }

      .client-kpi strong {
        font-size: 34px;
        display: block;
      }

      .client-actions {
        display: flex;
        gap: 12px;
        flex-wrap: wrap;
        margin-top: 24px;
      }

      .client-btn {
        border: 0;
        border-radius: 18px;
        padding: 15px 20px;
        color: #020617;
        background: linear-gradient(135deg, ${b.secondary_color}, ${b.primary_color});
        box-shadow: 0 0 36px ${b.primary_color}55;
        font-weight: 1000;
        cursor: pointer;
      }

      .client-panel {
        border-radius: 28px;
        padding: 24px;
      }

      .client-module-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
        gap: 16px;
      }

      .client-module-card {
        min-height: 132px;
        border-radius: 22px;
        padding: 20px;
        width: 100%;
        color: inherit;
        text-align: left;
        cursor: pointer;
        border: 0;
        font: inherit;
      }

      .client-module-card strong {
        display: block;
        margin-top: 22px;
        font-size: 19px;
      }

      .client-status-list {
        display: grid;
        gap: 12px;
      }

      .client-status-row {
        display: flex;
        justify-content: space-between;
        gap: 16px;
        padding: 14px 0;
        border-bottom: 1px solid rgba(255,255,255,.1);
      }

      .client-badge {
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        padding: 10px 14px;
        background: ${b.secondary_color};
        color: #020617;
        font-weight: 1000;
        box-shadow: 0 0 26px ${b.secondary_color}66;
      }

      .client-footer-id {
        margin-top: auto;
        padding: 14px;
        border-radius: 18px;
        background: rgba(0,0,0,.2);
        border: 1px solid rgba(255,255,255,.1);
        word-break: break-all;
        font-size: 12px;
      }

      @media (max-width: 900px) {
        .client-layout {
          grid-template-columns: 1fr;
        }

        .client-sidebar {
          position: static;
          min-height: auto;
        }

        .client-kpi-grid {
          grid-template-columns: 1fr 1fr;
        }
      }
    `;
  }


  const MODULE_UI = {
    core: ["Core", "base operativa", "COR"],
    workforce: ["Workforce", "personal operativo", "WRK"],
    field: ["Field Ops", "operacion en campo", "FLD"],
    technicians: ["Tecnicos", "inicio turno y estados", "TEC"],
    gps: ["GPS", "ubicacion y rutas", "GPS"],
    tasks: ["Tareas / Solicitudes", "solicitudes operativas", "TSK"],
    requests: ["Solicitudes", "flujo de aprobacion", "REQ"],
    inventory: ["Inventario", "stock y materiales", "INV"],
    materials: ["Materiales", "solicitud y devolucion", "MAT"],
    payroll: ["Nomina", "corte y calculo", "PAY"],
    payroll_biweekly: ["Nomina Quincenal", "corte actual", "PAY"],
    billing: ["Billing", "cobros y facturacion", "BIL"],
    reports: ["Reportes", "metricas y auditoria", "REP"],
    kpis: ["KPIs", "indicadores operativos", "KPI"],
    crm: ["CRM Campo", "operacion en vivo", "CRM"],
    settings: ["Configuracion", "ajustes del tenant", "CFG"],
    production: ["Produccion", "referencias y costos", "PRD"],
    retail: ["Retail", "tiendas y ventas", "RTL"],
    sales: ["Ventas", "actividad comercial", "SAL"],
    stores: ["Tiendas", "puntos de venta", "STR"],
    hospitality: ["Hospitality", "pedidos e inventario", "HSP"],
    bots: ["Bots", "Telegram / WhatsApp", "BOT"],
  };

  function normalizeClientModule(row = {}, index = 0) {
    const source = row.module && typeof row.module === "object" ? row.module : row;

    const code = String(
      source.code ||
      source.module_code ||
      row.module_code ||
      row.code ||
      ""
    ).trim();

    const meta = MODULE_UI[code] || [
      source.name || code || `Modulo ${index + 1}`,
      source.description || source.category || "servicio activo",
      (code || String(index + 1)).slice(0, 3).toUpperCase(),
    ];

    const enabled = row.enabled ?? source.enabled ?? source.is_active ?? true;

    return {
      code,
      title: meta[0],
      subtitle: meta[1],
      badge: meta[2],
      enabled: enabled !== false,
      raw: row,
    };
  }

  function activeClientModules() {
    const rows = Array.isArray(state.companyModules) ? state.companyModules : [];

    const active = rows
      .map((row, index) => normalizeClientModule(row, index))
      .filter((item) => item.enabled && item.code);

    return active;
  }

  function visibleClientModules(modules = activeClientModules()) {
    return (Array.isArray(modules) ? modules : []).filter((item) => item.code !== "core");
  }

  function isClientModuleActive(code) {
    const normalized = String(code || "").trim();
    if (!normalized || normalized === "core") return false;
    return activeClientModules().some((module) => module.code === normalized && module.enabled);
  }

  function clientVisibleModuleCodes(modules = activeClientModules()) {
    return clientModuleCodes(visibleClientModules(modules));
  }

  function moduleLabel(code) {
    const meta = MODULE_UI[String(code || "").trim()];
    return meta ? meta[0] : String(code || "Modulo");
  }



  function clientModuleCodes(modules = []) {
    return new Set(
      (Array.isArray(modules) ? modules : [])
        .map((module) => String(module.code || "").trim())
        .filter(Boolean)
    );
  }

  function hasAnyClientModule(codes, options = []) {
    return options.some((code) => codes.has(code));
  }

  function buildClientHeroKpis(modules = [], company = {}) {
    const visible = visibleClientModules(modules);
    const codes = clientModuleCodes(visible);
    const total = Array.isArray(visible) ? visible.length : 0;
    const metrics = state.dashboardMetrics || {};

    const kpis = [];

    if (hasAnyClientModule(codes, ["workforce"])) {
      kpis.push(["Personal activo", String(metrics.activeEmployees ?? "0")]);
    }

    if (hasAnyClientModule(codes, ["bots"])) {
      const botStatus = String(metrics.botStatus || "").toLowerCase();
      const connected = metrics.botConfigured && !["error", "inactive", "not_configured"].includes(botStatus);
      kpis.push(["Canales", connected ? "ON" : "OFF"]);
    }

    if (hasAnyClientModule(codes, ["reports", "kpis"])) {
      kpis.push(["Reportes", "OK"]);
    }

    if (hasAnyClientModule(codes, ["sales"])) {
      kpis.push(["Ventas", metrics.salesToday ?? "0"]);
    }

    if (hasAnyClientModule(codes, ["stores"])) {
      kpis.push(["Tiendas", metrics.storesActive ?? "OK"]);
    }

    if (!kpis.length) {
      kpis.push(["Empresa", company.name || "Activa"]);
      kpis.push(["Modulos activos", String(total)]);
      kpis.push(["Estado", "LIVE"]);
    }

    return kpis.slice(0, 4);
  }

  function buildClientHeroActions(modules = []) {
    const codes = clientModuleCodes(visibleClientModules(modules));
    const actions = [];

    if (hasAnyClientModule(codes, ["workforce"])) {
      actions.push({ label: "Agregar personal", action: "workforce:add" });
    }

    if (hasAnyClientModule(codes, ["bots"])) {
      actions.push({ label: "Ver bot", action: "bots:open" });
    }

    if (hasAnyClientModule(codes, ["crm"])) {
      actions.push({ label: "Ver CRM", action: "crm:open" });
    }

    if (hasAnyClientModule(codes, ["reports", "kpis"])) {
      actions.push({ label: "Ver reportes", action: "reports:open" });
    }

    if (!actions.length) {
      actions.push({ label: "Ver operacion", action: "dashboard" });
    }

    return actions.slice(0, 3);
  }

  function renderClientHeroKpis(modules = [], company = {}) {
    return buildClientHeroKpis(modules, company)
      .map(([label, value]) => `
        <div class="client-kpi">
          <span>${h(label)}</span>
          <strong>${h(value)}</strong>
        </div>
      `)
      .join("");
  }

  function renderClientHeroActions(modules = []) {
    return buildClientHeroActions(modules)
      .map((item) => `<button class="client-btn" type="button" data-client-action="${h(item.action)}">${h(item.label)}</button>`)
      .join("");
  }

  function renderClientNav(activeCode = "dashboard") {
    const modules = visibleClientModules(activeClientModules());
    const buttons = [`<button class="${activeCode === "dashboard" ? "active" : ""}" type="button" data-client-back-dashboard>Dashboard</button>`];

    modules.forEach((module) => {
      const code = module.code;
      buttons.push(`
        <button class="${activeCode === code ? "active" : ""}" type="button" data-client-module="${h(code)}">
          ${h(module.title)}
        </button>
      `);
    });

    return buttons.join("");
  }



  function ensurePersonalGridStyles() {
    let style = document.getElementById("clientPersonalGridStyles");

    if (!style) {
      style = document.createElement("style");
      style.id = "clientPersonalGridStyles";
      document.head.appendChild(style);
    }

    style.textContent = `
      .personal-toolbar {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        align-items: center;
        justify-content: space-between;
        margin: 18px 0;
      }

      .personal-search {
        min-width: min(460px, 100%);
        border: 1px solid rgba(255,255,255,.16);
        background: rgba(255,255,255,.09);
        color: var(--cx-text, #fff);
        border-radius: 16px;
        padding: 14px 16px;
        font-weight: 900;
        outline: none;
      }

            .personal-grid-wrap {
        width: 100%;
        max-width: 100%;
        overflow-x: auto;
        overflow-y: hidden;
        padding-bottom: 10px;
        scrollbar-gutter: stable both-edges;
        border-radius: 22px;
        border: 1px solid rgba(255,255,255,.14);
        box-shadow: 0 18px 48px rgba(0,0,0,.22);
      }

            .personal-grid {
        min-width: 1520px;
        width: max-content;
        display: grid;
        grid-template-columns:
          160px 110px 105px 160px 120px 105px
          105px 105px 105px 105px 110px 210px;
        align-items: stretch;
      }

      .personal-row {
        display: contents;
      }

            .personal-cell {
        min-height: 56px;
        padding: 8px;
        border-right: 1px solid rgba(255,255,255,.08);
        border-bottom: 1px solid rgba(255,255,255,.08);
        background: rgba(255,255,255,.045);
        display: flex;
        align-items: center;
      }

            .personal-head {
        position: sticky;
        top: 0;
        z-index: 2;
        background: linear-gradient(135deg, var(--cx-primary, #ff2bd6), rgba(255,255,255,.12));
        color: #fff;
        font-weight: 1000;
        letter-spacing: .05em;
        text-transform: uppercase;
        font-size: 12px;
        line-height: 1.12;
      }

            .personal-cell input,
      .personal-cell select {
        width: 100%;
        border: 1px solid rgba(255,255,255,.13);
        background: rgba(0,0,0,.22);
        color: var(--cx-text, #fff);
        border-radius: 10px;
        padding: 9px 8px;
        font-weight: 900;
        font-size: 13px;
        outline: none;
      }

      .personal-cell input::placeholder {
        color: rgba(255,255,255,.45);
      }

      .personal-cell select option {
        color: #020617;
      }

      .personal-row-archived       .personal-cell {
        min-height: 56px;
        padding: 8px;
        border-right: 1px solid rgba(255,255,255,.08);
        border-bottom: 1px solid rgba(255,255,255,.08);
        background: rgba(255,255,255,.045);
        display: flex;
        align-items: center;
      }

            .personal-actions {
        display: flex;
        gap: 6px;
        flex-wrap: wrap;
        justify-content: flex-start;
      }

            .personal-mini-btn {
        border: 1px solid rgba(255,255,255,.14);
        background: rgba(255,255,255,.09);
        color: var(--cx-text, #fff);
        border-radius: 10px;
        padding: 7px 8px;
        font-size: 12px;
        font-weight: 1000;
        line-height: 1;
        white-space: nowrap;
        cursor: pointer;
      }

      .personal-mini-btn.primary {
        background: var(--cx-primary, #ff2bd6);
        color: #fff;
        border-color: transparent;
        box-shadow: 0 14px 34px rgba(0,0,0,.22);
      }

      .personal-mini-btn.danger {
        border-color: rgba(255,80,120,.55);
      }


      .personal-sticky-right {
        position: sticky;
        right: 0;
        z-index: 3;
        background: rgba(24, 24, 40, 0.96);
        backdrop-filter: blur(10px);
        box-shadow: -8px 0 18px rgba(0,0,0,.16);
      }

      .personal-head.personal-sticky-right {
        z-index: 4;
      }

      
      .cx-personal-search-input {
        width: min(420px, 100%);
        min-width: 280px;
        border: 1px solid rgba(255,255,255,.16);
        background: rgba(255,255,255,.08);
        color: var(--cx-text, #fff);
        border-radius: 14px;
        padding: 12px 14px;
        font-weight: 900;
        outline: none;
      }

      .cx-personal-search-input::placeholder {
        color: rgba(255,255,255,.62);
      }

      .personal-sticky-right {
        position: sticky;
        right: 0;
        z-index: 3;
        background: rgba(26, 26, 40, 0.97);
        backdrop-filter: blur(10px);
        box-shadow: -10px 0 18px rgba(0,0,0,.18);
      }

      .personal-head.personal-sticky-right {
        z-index: 4;
      }

      .personal-toast {
        margin-top: 14px;
        padding: 12px 14px;
        border-radius: 16px;
        border: 1px solid rgba(255,255,255,.14);
        background: rgba(0,0,0,.24);
        font-weight: 1000;
      }

      .personal-toast.ok {
        color: #8cffc1;
      }

      .personal-toast.error {
        color: #ff9aae;
      }
    `;
  }

  async function personalApi(path, options = {}) {
    const response = await fetch(`${API}${path}`, {
      method: options.method || "GET",
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      body: options.body,
    });

    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(detail || `${response.status} ${response.statusText}`);
    }

    if (response.status === 204) return null;
    return response.json();
  }

  function personalRoleOptions(selected = "operator") {
    const roles = [
      ["admin_empresa", "Admin empresa"],
      ["supervisor", "Supervisor"],
      ["tecnico", "Tecnico"],
      ["operario", "Operario"],
      ["vendedor", "Vendedor"],
      ["barman", "Barman"],
      ["mesero", "Mesero"],
      ["cajero", "Cajero"],
      ["inventario", "Inventario"],
      ["operator", "Operador"],
    ];

    return roles.map(([value, label]) => `
      <option value="${h(value)}" ${String(selected || "operator") === value ? "selected" : ""}>${h(label)}</option>
    `).join("");
  }

  function personalStatusOptions(selected = "active") {
    const statuses = [
      ["active", "Activo"],
      ["inactive", "Inactivo"],
      ["archived", "Archivado"],
    ];

    return statuses.map(([value, label]) => `
      <option value="${h(value)}" ${String(selected || "active") === value ? "selected" : ""}>${h(label)}</option>
    `).join("");
  }

  function personalGridHeader() {
    return `
      <div class="personal-cell personal-head">Nombre</div>
      <div class="personal-cell personal-head">Rol</div>
      <div class="personal-cell personal-head">Telefono</div>
      <div class="personal-cell personal-head">Correo</div>
      <div class="personal-cell personal-head">Telegram ID</div>
      <div class="personal-cell personal-head">Fecha ingreso</div>
      <div class="personal-cell personal-head">Hora ordinaria</div>
      <div class="personal-cell personal-head">Hora extra</div>
      <div class="personal-cell personal-head">Descuento 1</div>
      <div class="personal-cell personal-head">Descuento 2</div>
      <div class="personal-cell personal-head">Estado</div>
      <div class="personal-cell personal-head personal-sticky-right">Acciones</div>
    `;
  }

  function personalRow(employee = {}) {
    const rowClass = employee.status === "archived" ? "personal-row-archived" : "";
    const id = employee.id || "";

    return `
      <div class="personal-row ${rowClass}" data-personal-row data-employee-id="${h(id)}">
        <div class="personal-cell"><input data-field="full_name" value="${h(employee.full_name || "")}" placeholder="Nombre completo"></div>
        <div class="personal-cell"><select data-field="role">${personalRoleOptions(employee.role || employee.employee_type || "operator")}</select></div>
        <div class="personal-cell"><input data-field="phone" value="${h(employee.phone || "")}" placeholder="Telefono"></div>
        <div class="personal-cell"><input data-field="email" value="${h(employee.email || "")}" placeholder="correo@empresa.com"></div>
        <div class="personal-cell"><input data-field="telegram_user_id" value="${h(employee.telegram_user_id || "")}" placeholder="ID Telegram"></div>
        <div class="personal-cell"><input data-field="hire_date" value="${h(employee.hire_date || "")}" placeholder="YYYY-MM-DD"></div>
        <div class="personal-cell"><input data-field="hourly_rate_regular" type="number" step="0.01" value="${h(employee.hourly_rate_regular ?? 0)}"></div>
        <div class="personal-cell"><input data-field="hourly_rate_extra" type="number" step="0.01" value="${h(employee.hourly_rate_extra ?? 0)}"></div>
        <div class="personal-cell"><input data-field="deduction_1" type="number" step="0.01" value="${h(employee.deduction_1 ?? 0)}"></div>
        <div class="personal-cell"><input data-field="deduction_2" type="number" step="0.01" value="${h(employee.deduction_2 ?? 0)}"></div>
        <div class="personal-cell"><select data-field="status">${personalStatusOptions(employee.status || "active")}</select></div>
        <div class="personal-cell personal-sticky-right">
          <div class="personal-actions">
            <button class="personal-mini-btn primary" type="button" data-personal-save-row>Guardar</button>
            ${id ? `
              <button class="personal-mini-btn" type="button" data-personal-action="activate">Activar</button>
              <button class="personal-mini-btn" type="button" data-personal-action="deactivate">Inactivar</button>
              <button class="personal-mini-btn danger" type="button" data-personal-action="archive">Eliminar</button>
            ` : ""}
          </div>
        </div>
      </div>
    `;
  }

  function payloadFromPersonalRow(row) {
    const payload = { company_id: state.companyId };

    row.querySelectorAll("[data-field]").forEach((field) => {
      const key = field.dataset.field;
      let value = field.value;

      if (["hourly_rate_regular", "hourly_rate_extra", "deduction_1", "deduction_2"].includes(key)) {
        value = value === "" ? 0 : Number(value);
      }

      payload[key] = value === "" ? null : value;
    });

    payload.employee_type = payload.role || "operator";
    return payload;
  }

  async function loadPersonalEmployees() {
    return personalApi(`/employees?company_id=${encodeURIComponent(state.companyId)}&include_archived=true`);
  }


  function ensurePersonalHistoryStyles() {
    if (document.getElementById("clientPersonalHistoryStyles")) return;

    const style = document.createElement("style");
    style.id = "clientPersonalHistoryStyles";
    style.textContent = `
      .personal-history-toolbar {
        display: grid;
        grid-template-columns: 150px 150px minmax(220px, 1fr) 220px auto auto;
        gap: 10px;
        align-items: end;
        margin: 18px 0;
      }

      .personal-history-field {
        display: grid;
        gap: 7px;
      }

      .personal-history-field label {
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: .10em;
        font-weight: 1000;
        color: rgba(255,255,255,.72);
      }

      .personal-history-field input,
      .personal-history-field select {
        border: 1px solid rgba(255,255,255,.16);
        background: rgba(0,0,0,.22);
        color: var(--cx-text, #fff);
        border-radius: 14px;
        padding: 12px 13px;
        font-weight: 900;
        outline: none;
      }

      .personal-history-field select option {
        color: #020617;
      }

      .personal-history-stats {
        display: grid;
        grid-template-columns: repeat(4, minmax(130px, 1fr));
        gap: 12px;
        margin: 18px 0;
      }

      .personal-history-stat {
        border: 1px solid rgba(255,255,255,.13);
        background: rgba(255,255,255,.07);
        border-radius: 18px;
        padding: 14px;
        box-shadow: 0 16px 36px rgba(0,0,0,.18);
      }

      .personal-history-stat span {
        display: block;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: .08em;
        opacity: .72;
        font-weight: 1000;
      }

      .personal-history-stat strong {
        display: block;
        margin-top: 6px;
        font-size: 24px;
        font-weight: 1000;
      }

      .personal-history-wrap {
        width: 100%;
        overflow-x: auto;
        border: 1px solid rgba(255,255,255,.14);
        border-radius: 22px;
        box-shadow: 0 18px 48px rgba(0,0,0,.22);
      }

      .personal-history-grid {
        min-width: 1320px;
        display: grid;
        grid-template-columns: 185px 190px 165px 180px 210px 210px 150px 220px;
        align-items: stretch;
      }

      .personal-history-row {
        display: contents;
      }

      .personal-history-cell {
        min-height: 54px;
        padding: 10px;
        border-right: 1px solid rgba(255,255,255,.08);
        border-bottom: 1px solid rgba(255,255,255,.08);
        background: rgba(255,255,255,.045);
        display: flex;
        align-items: center;
        font-weight: 850;
        overflow-wrap: anywhere;
      }

      .personal-history-head {
        position: sticky;
        top: 0;
        z-index: 2;
        background: linear-gradient(135deg, var(--cx-primary, #ff2bd6), rgba(255,255,255,.12));
        color: #fff;
        font-weight: 1000;
        letter-spacing: .05em;
        text-transform: uppercase;
        font-size: 12px;
      }

      .personal-history-empty {
        padding: 18px;
        border: 1px dashed rgba(255,255,255,.22);
        border-radius: 18px;
        background: rgba(0,0,0,.18);
        font-weight: 1000;
        margin-top: 16px;
      }

      @media (max-width: 1100px) {
        .personal-history-toolbar {
          grid-template-columns: 1fr;
        }

        .personal-history-stats {
          grid-template-columns: repeat(2, minmax(130px, 1fr));
        }
      }
    `;
    document.head.appendChild(style);
  }

  function dateInputValue(date) {
    return date.toISOString().slice(0, 10);
  }

  function defaultHistoryFilters() {
    const to = new Date();
    const from = new Date();
    from.setDate(to.getDate() - 30);

    return {
      date_from: dateInputValue(from),
      date_to: dateInputValue(to),
      search: "",
      event_type: "",
    };
  }

  function readPersonalHistoryFilters() {
    const defaults = defaultHistoryFilters();

    return {
      date_from: document.querySelector("[data-personal-history-from]")?.value || defaults.date_from,
      date_to: document.querySelector("[data-personal-history-to]")?.value || defaults.date_to,
      search: document.querySelector("[data-personal-history-search]")?.value || "",
      event_type: document.querySelector("[data-personal-history-event]")?.value || "",
    };
  }

  function historyEventLabel(value) {
    const labels = {
      employee_baseline: "Registro inicial",
      employee_created: "Empleado creado",
      employee_updated: "Empleado editado",
      employee_activated: "Empleado activado",
      employee_inactivated: "Empleado inactivado",
      employee_archived: "Empleado archivado",
      employee_restored: "Empleado restaurado",
    };
    return labels[value] || value || "Evento";
  }

  function historyFieldLabel(value) {
    const labels = {
      full_name: "Nombre",
      document_id: "Documento",
      phone: "Teléfono",
      email: "Correo",
      status: "Estado",
      employee_type: "Tipo empleado",
      role: "Rol",
      telegram_user_id: "Telegram ID",
      telegram_username: "Telegram usuario",
      hire_date: "Fecha ingreso",
      hourly_rate_regular: "Hora ordinaria",
      hourly_rate_extra: "Hora extra",
      deduction_1: "Descuento 1",
      deduction_2: "Descuento 2",
      notes: "Notas",
      registro: "Registro",
    };
    return labels[value] || value || "Campo";
  }

  function historyValue(value) {
    if (value === null || value === undefined || value === "") return "—";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  }

  function historyDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString("es-CO", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function flattenHistoryRows(items) {
    const rows = [];

    (Array.isArray(items) ? items : []).forEach((item) => {
      const changes = Array.isArray(item.changed_fields_json) && item.changed_fields_json.length
        ? item.changed_fields_json
        : [{ field: "registro", old: "", new: item.event_label || item.event_type }];

      changes.forEach((change) => {
        rows.push({
          created_at: item.created_at,
          employee_name: item.employee_name || "—",
          event_label: item.event_label || historyEventLabel(item.event_type),
          field: change.field || "registro",
          old: change.old,
          new: change.new,
          source: item.source || "client",
          notes: item.notes || "",
        });
      });
    });

    return rows;
  }

  function personalHistoryQuery(filters) {
    const params = new URLSearchParams();
    params.set("company_id", state.companyId);
    params.set("limit", "500");

    if (filters.date_from) params.set("date_from", `${filters.date_from}T00:00:00Z`);
    if (filters.date_to) params.set("date_to", `${filters.date_to}T23:59:59Z`);
    if (filters.search) params.set("search", filters.search);
    if (filters.event_type) params.set("event_type", filters.event_type);

    return params.toString();
  }

  async function loadPersonalHistory(filters) {
    return personalApi(`/employees/history?${personalHistoryQuery(filters)}`);
  }

  function renderPersonalHistoryRows(rows) {
    if (!rows.length) {
      return `
        <div class="personal-history-empty">
          No hay registros de historial para los filtros seleccionados.
        </div>
      `;
    }

    return `
      <div class="personal-history-wrap">
        <div class="personal-history-grid">
          <div class="personal-history-cell personal-history-head">Fecha</div>
          <div class="personal-history-cell personal-history-head">Empleado</div>
          <div class="personal-history-cell personal-history-head">Evento</div>
          <div class="personal-history-cell personal-history-head">Campo</div>
          <div class="personal-history-cell personal-history-head">Valor anterior</div>
          <div class="personal-history-cell personal-history-head">Valor nuevo</div>
          <div class="personal-history-cell personal-history-head">Fuente</div>
          <div class="personal-history-cell personal-history-head">Notas</div>
          ${rows.map((row) => `
            <div class="personal-history-row">
              <div class="personal-history-cell">${h(historyDate(row.created_at))}</div>
              <div class="personal-history-cell">${h(row.employee_name)}</div>
              <div class="personal-history-cell">${h(row.event_label)}</div>
              <div class="personal-history-cell">${h(historyFieldLabel(row.field))}</div>
              <div class="personal-history-cell">${h(historyValue(row.old))}</div>
              <div class="personal-history-cell">${h(historyValue(row.new))}</div>
              <div class="personal-history-cell">${h(row.source)}</div>
              <div class="personal-history-cell">${h(row.notes)}</div>
            </div>
          `).join("")}
        </div>
      </div>
    `;
  }

  function exportPersonalHistoryCsv() {
    const rows = Array.isArray(state.personalHistoryRows) ? state.personalHistoryRows : [];
    const data = [["Fecha", "Empleado", "Evento", "Campo", "Valor anterior", "Valor nuevo", "Fuente", "Notas"]];

    rows.forEach((row) => {
      data.push([
        historyDate(row.created_at),
        row.employee_name,
        row.event_label,
        historyFieldLabel(row.field),
        historyValue(row.old),
        historyValue(row.new),
        row.source,
        row.notes,
      ]);
    });

    const csv = data.map((line) => line.map((value) => `"${String(value ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = `clonexa_personal_historial_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();

    URL.revokeObjectURL(url);
  }

  async function renderPersonalHistoryModule(filters = null) {
    ensurePersonalGridStyles();
    ensurePersonalHistoryStyles();

    const company = state.company || {};
    const activeFilters = filters || defaultHistoryFilters();
    let history = [];
    let loadError = "";

    try {
      history = await loadPersonalHistory(activeFilters);
    } catch (error) {
      history = [];
      loadError = error.message || "No se pudo cargar historial.";
    }

    const rows = flattenHistoryRows(history);
    state.personalHistoryRows = rows;

    const created = history.filter((item) => item.event_type === "employee_created").length;
    const updated = history.filter((item) => item.event_type === "employee_updated").length;
    const archived = history.filter((item) => item.event_type === "employee_archived").length;

    $("app").innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, normalizeBranding(state.branding || {}))}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>

            <nav class="client-nav">
              <button type="button" data-client-back-dashboard>Dashboard</button>
              <button type="button" data-personal-back-list>Personal</button>
              <button class="active" type="button">Historial</button>
            </nav>

            <div class="client-footer-id">
              <strong>Tenant activo</strong><br>
              ${h(state.companyId || "")}
            </div>
          </aside>

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">Modulo Workforce</div>
              <h1 class="client-title">Historial de Personal</h1>
              <p class="client-muted">Consulta registros, ediciones, activaciones, inactivaciones y archivados por rango de fechas.</p>

              <div class="personal-toolbar">
                <div class="client-actions">
                  <button class="client-btn" type="button" data-personal-back-list>Volver a Personal</button>
                  <button class="client-btn" type="button" data-personal-history-export>Exportar CSV</button>
                  <button class="client-btn" type="button" data-client-back-dashboard>Dashboard</button>
                </div>
              </div>

              <div id="personalNotice">${loadError ? `<div class="personal-toast error">${h(loadError)}</div>` : ""}</div>
            </header>

            <section class="client-panel">
              <div class="client-eyebrow">Auditoria operativa</div>
              <h2>Buscar historial</h2>
              <p class="client-muted">Usa estos filtros para validar datos de 15, 20, 30 dias o cualquier rango operativo.</p>

              <div class="personal-history-toolbar">
                <div class="personal-history-field">
                  <label>Desde</label>
                  <input type="date" data-personal-history-from value="${h(activeFilters.date_from)}">
                </div>
                <div class="personal-history-field">
                  <label>Hasta</label>
                  <input type="date" data-personal-history-to value="${h(activeFilters.date_to)}">
                </div>
                <div class="personal-history-field">
                  <label>Buscar</label>
                  <input type="text" data-personal-history-search value="${h(activeFilters.search)}" placeholder="Empleado, evento, rol, estado...">
                </div>
                <div class="personal-history-field">
                  <label>Evento</label>
                  <select data-personal-history-event>
                    <option value="" ${!activeFilters.event_type ? "selected" : ""}>Todos</option>
                    <option value="employee_baseline" ${activeFilters.event_type === "employee_baseline" ? "selected" : ""}>Registro inicial</option>
                    <option value="employee_created" ${activeFilters.event_type === "employee_created" ? "selected" : ""}>Empleado creado</option>
                    <option value="employee_updated" ${activeFilters.event_type === "employee_updated" ? "selected" : ""}>Empleado editado</option>
                    <option value="employee_activated" ${activeFilters.event_type === "employee_activated" ? "selected" : ""}>Empleado activado</option>
                    <option value="employee_inactivated" ${activeFilters.event_type === "employee_inactivated" ? "selected" : ""}>Empleado inactivado</option>
                    <option value="employee_archived" ${activeFilters.event_type === "employee_archived" ? "selected" : ""}>Empleado archivado</option>
                    <option value="employee_restored" ${activeFilters.event_type === "employee_restored" ? "selected" : ""}>Empleado restaurado</option>
                  </select>
                </div>
                <button class="client-btn" type="button" data-personal-history-apply>Buscar</button>
                <button class="client-btn" type="button" data-personal-history-export>CSV</button>
              </div>

              <div class="personal-history-stats">
                <div class="personal-history-stat"><span>Eventos</span><strong>${h(history.length)}</strong></div>
                <div class="personal-history-stat"><span>Creados</span><strong>${h(created)}</strong></div>
                <div class="personal-history-stat"><span>Editados</span><strong>${h(updated)}</strong></div>
                <div class="personal-history-stat"><span>Archivados</span><strong>${h(archived)}</strong></div>
              </div>

              ${renderPersonalHistoryRows(rows)}
            </section>
          </section>
        </div>
      </main>
    `;
  }

  async function savePersonalRow(row) {
    const employeeId = row.dataset.employeeId;
    const payload = payloadFromPersonalRow(row);

    if (!payload.full_name || String(payload.full_name).trim().length < 2) {
      throw new Error("Nombre completo es obligatorio.");
    }

    if (employeeId) {
      return personalApi(`/employees/${employeeId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
    }

    return personalApi("/employees", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  function showPersonalNotice(message, type = "ok") {
    const box = document.getElementById("personalNotice");
    if (!box) return;

    box.innerHTML = `<div class="personal-toast ${type === "error" ? "error" : "ok"}">${h(message)}</div>`;

    window.clearTimeout(window.__personalNoticeTimer);
    window.__personalNoticeTimer = window.setTimeout(() => {
      if (box) box.innerHTML = "";
    }, 2600);
  }

  async function loadClientBotConfig() {
    if (!state.companyId) return null;
    try {
      return await api(`/bots/companies/${state.companyId}/telegram`);
    } catch (error) {
      return { configured: false, status: "error", last_error: error.message || "No se pudo cargar bot" };
    }
  }

  function botStatusLabel(status) {
    const value = String(status || "not_configured").toLowerCase();
    if (value === "listening") return "Escuchando";
    if (["active", "configured", "connected"].includes(value)) return "Conectado";
    if (value === "inactive") return "Inactivo";
    if (value === "error") return "Error";
    if (value === "not_configured") return "No configurado";
    return value;
  }

  async function renderBotsModule() {
    const company = state.company || {};
    const bot = await loadClientBotConfig();
    const configured = !!bot?.configured;
    const status = botStatusLabel(bot?.status);
    const botName = bot?.name || `${company.name || "Empresa"} Bot`;
    const botUsername = bot?.bot_username || "Sin configurar";

    $("app").innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, normalizeBranding(state.branding || {}))}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>

            <nav class="client-nav">
              ${renderClientNav("bots")}
            </nav>

            <div class="client-footer-id">
              <strong>Tenant activo</strong><br>
              ${h(state.companyId || "")}
            </div>
          </aside>

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">Modulo Bots</div>
              <h1 class="client-title">Bots</h1>
              <p class="client-muted">Estado operativo del canal configurado para esta empresa.</p>

              <div class="client-actions">
                <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
              </div>

              <div id="botsNotice"></div>
            </header>

            <section class="client-panel">
              <div class="client-eyebrow">Canal operativo</div>
              <h2>Bot Telegram</h2>
              <p class="client-muted">Configuracion tecnica administrada desde CLONEXA Admin V2.</p>

              <div class="client-kpi-grid">
                <div class="client-kpi">
                  <span>Estado</span>
                  <strong>${h(status)}</strong>
                </div>
                <div class="client-kpi">
                  <span>Canal</span>
                  <strong>Telegram</strong>
                </div>
                <div class="client-kpi">
                  <span>Bot</span>
                  <strong>${h(botUsername)}</strong>
                </div>
              </div>

              <div class="personal-toolbar" style="margin-top:22px">
                <input class="personal-search" data-bot-name value="${h(botName)}" placeholder="Nombre interno del bot" ${configured ? "" : "disabled"}>
                <button class="client-btn" type="button" data-bot-save-name ${configured ? "" : "disabled"}>Guardar nombre</button>
              </div>

              ${bot?.last_error ? `<div class="personal-toast error">${h(bot.last_error)}</div>` : ""}
            </section>
          </section>
        </div>
      </main>
    `;
  }

  function showBotsNotice(message, type = "ok") {
    const box = document.getElementById("botsNotice");
    if (!box) return;
    box.innerHTML = `<div class="personal-toast ${type === "error" ? "error" : "ok"}">${h(message)}</div>`;
  }

  async function saveClientBotName() {
    const input = document.querySelector("[data-bot-name]");
    const name = String(input?.value || "").trim();

    if (name.length < 2) {
      showBotsNotice("Nombre interno obligatorio.", "error");
      return;
    }

    try {
      await api(`/bots/companies/${state.companyId}/telegram`, {
        method: "PUT",
        body: JSON.stringify({ name }),
      });
      await renderBotsModule();
      setTimeout(() => showBotsNotice("Nombre del bot actualizado."), 50);
    } catch (error) {
      showBotsNotice(error.message || "No se pudo guardar el nombre.", "error");
    }
  }

  function crmEventTime(row = {}) {
    return row.occurred_at || row.event_time || row.created_at || row.last_event_at || null;
  }

  function crmDate(row = {}) {
    const raw = crmEventTime(row);
    if (!raw) return null;
    const date = new Date(raw);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function crmDateLabel(row = {}) {
    const date = crmDate(row);
    return date ? date.toLocaleString([], { dateStyle: "short", timeStyle: "short" }) : "-";
  }

  function crmEventLabel(row = {}) {
    const type = String(row.event_type || row.last_event_type || "").toLowerCase();
    const labels = {
      check_in: "Inicio turno",
      break_start: "Pausa",
      break_end: "Retomar",
      check_out: "Fin turno",
      material_request: "Solicitud material",
      observation: "Observacion",
      gps_ping: "Ubicacion",
      task_started: "Tarea iniciada",
      task_completed: "Tarea cerrada",
      sale_created: "Venta",
    };

    return row.event_label || labels[type] || type || "Evento";
  }

  function crmChannelLabel(value) {
    const channel = String(value || "").toLowerCase();
    const labels = {
      telegram: "Telegram",
      panel: "Panel",
      whatsapp: "WhatsApp",
      qr: "QR",
      system: "Sistema",
    };

    return labels[channel] || (channel ? channel : "-");
  }

  function crmStatusFromEvent(row = {}) {
    const type = String(row.event_type || row.last_event_type || "").toLowerCase();
    if (["check_in", "break_end"].includes(type)) return "working";
    if (type === "break_start") return "on_break";
    if (type === "check_out") return "checked_out";

    const status = String(row.status_after || row.status || "").toLowerCase();
    if (["working", "trabajando"].includes(status)) return "working";
    if (["on_break", "break", "pause", "pausa"].includes(status)) return "on_break";
    if (["checked_out", "finished", "turno_finalizado"].includes(status)) return "checked_out";

    return "not_started";
  }

  function crmStatusLabel(status) {
    const normalized = String(status || "").toLowerCase();
    const labels = {
      working: "Activo",
      on_break: "En pausa",
      checked_out: "Fuera de turno",
      not_started: "Sin turno",
      inactive: "Inactivo",
      archived: "Archivado",
    };

    return labels[normalized] || normalized || "-";
  }

  function crmStartOfToday() {
    const date = new Date();
    date.setHours(0, 0, 0, 0);
    return date;
  }

  function crmIsToday(row = {}) {
    const date = crmDate(row);
    return !!date && date >= crmStartOfToday();
  }

  function crmEmployeeName(employee = {}, latest = {}) {
    return employee.full_name || employee.name || latest.employee_name || latest.full_name || "Sin nombre";
  }

  function crmLatestEventByEmployee(events = []) {
    const map = new Map();

    (Array.isArray(events) ? events : []).forEach((event) => {
      const employeeId = event.employee_id || event.employeeId;
      if (!employeeId) return;

      const current = map.get(employeeId);
      const eventDate = crmDate(event)?.getTime() || 0;
      const currentDate = crmDate(current || {})?.getTime() || 0;

      if (!current || eventDate >= currentDate) {
        map.set(employeeId, event);
      }
    });

    return map;
  }

  function crmDurationLabel(ms) {
    if (!Number.isFinite(ms) || ms < 0) return "--:--";
    const totalSeconds = Math.floor(ms / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    if (hours > 0) {
      return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    }

    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }

  function crmEventEmployeeId(row = {}) {
    return row.employee_id || row.employeeId || row.employee?.id || null;
  }

  function crmEventsForEmployee(events = [], employeeId = "") {
    if (!employeeId) return [];
    return (Array.isArray(events) ? events : [])
      .filter((event) => String(crmEventEmployeeId(event) || "") === String(employeeId))
      .filter(crmIsToday)
      .sort((a, b) => (crmDate(a)?.getTime() || 0) - (crmDate(b)?.getTime() || 0));
  }

  function crmShiftMetrics(employeeEvents = []) {
    let startedAt = null;
    let endedAt = null;
    let pauseStartedAt = null;
    let pauseMs = 0;
    let status = "not_started";
    let latest = null;

    employeeEvents.forEach((event) => {
      const date = crmDate(event);
      if (!date) return;

      const type = String(event.event_type || event.last_event_type || "").toLowerCase();
      latest = event;

      if (type === "check_in") {
        startedAt = date;
        endedAt = null;
        pauseStartedAt = null;
        pauseMs = 0;
        status = "working";
        return;
      }

      if (!startedAt) return;

      if (type === "break_start") {
        if (!pauseStartedAt && status !== "checked_out") {
          pauseStartedAt = date;
        }
        status = "on_break";
        return;
      }

      if (type === "break_end") {
        if (pauseStartedAt) {
          pauseMs += Math.max(0, date.getTime() - pauseStartedAt.getTime());
          pauseStartedAt = null;
        }
        status = "working";
        return;
      }

      if (type === "check_out") {
        if (pauseStartedAt) {
          pauseMs += Math.max(0, date.getTime() - pauseStartedAt.getTime());
          pauseStartedAt = null;
        }
        endedAt = date;
        status = "checked_out";
      }
    });

    const now = Date.now();

    if (!startedAt) {
      return {
        status: "not_started",
        startedAt: null,
        endedAt: null,
        latest,
        grossMs: 0,
        pauseMs: 0,
        payableMs: 0,
        timer: "--:--",
      };
    }

    const effectiveEndMs = endedAt ? endedAt.getTime() : now;
    const livePauseMs = pauseStartedAt ? Math.max(0, now - pauseStartedAt.getTime()) : 0;
    const totalPauseMs = pauseMs + livePauseMs;
    const grossMs = Math.max(0, effectiveEndMs - startedAt.getTime());
    const payableMs = Math.max(0, grossMs - totalPauseMs);

    return {
      status,
      startedAt,
      endedAt,
      latest,
      grossMs,
      pauseMs: totalPauseMs,
      payableMs,
      timer: crmDurationLabel(status === "on_break" ? totalPauseMs : payableMs),
    };
  }

  function crmDynamicModuleCodes() {
    const priority = [
      "gps",
      "field",
      "materials",
      "production",
      "sales",
      "stores",
      "retail",
      "inventory",
      "stock",
      "orders",
      "requests",
      "payroll",
      "kpis",
      "reports",
    ];

    const active = clientModuleCodes(visibleClientModules(activeClientModules()));
    const selected = priority.filter((code) => active.has(code)).slice(0, 2);

    while (selected.length < 2) {
      selected.push(selected.length === 0 ? "modules" : "channels");
    }

    return selected;
  }

  function crmModuleDisplay(code) {
    const labels = {
      gps: "GPS",
      field: "Campo",
      materials: "Materiales",
      production: "Produccion",
      sales: "Ventas",
      stores: "Tiendas",
      retail: "Retail",
      inventory: "Inventario",
      stock: "Stock",
      orders: "Pedidos",
      requests: "Solicitudes",
      payroll: "Nomina",
      kpis: "KPIs",
      reports: "Reportes",
      modules: "Modulos",
      channels: "Canales",
    };

    return labels[code] || moduleLabel(code);
  }

  function crmModuleFallback(code) {
    const labels = {
      gps: "Sin ubicacion",
      field: "Sin tarea",
      materials: "Sin solicitud",
      production: "Sin produccion",
      sales: "Sin venta",
      stores: "Sin punto",
      retail: "Sin actividad",
      inventory: "Sin movimiento",
      stock: "Sin alerta",
      orders: "Sin pedido",
      requests: "Sin solicitud",
      payroll: "Sin corte",
      kpis: "Sin metrica",
      reports: "OK",
      modules: "Asignados",
      channels: "Bot",
    };

    return labels[code] || "Sin actividad";
  }

  function crmModuleValueForPerson(code, person = {}) {
    if (code === "modules") return `${visibleClientModules(activeClientModules()).length} activos`;
    if (code === "channels") return isClientModuleActive("bots") ? "Telegram" : "-";

    const event = (person.events || [])
      .slice()
      .reverse()
      .find((item) => String(item.module_code || "workforce").toLowerCase() === code);

    return event ? crmEventLabel(event) : crmModuleFallback(code);
  }

  function crmTopCardValue(code, crm = {}) {
    if (code === "modules") return `${visibleClientModules(activeClientModules()).length}`;
    if (code === "channels") return isClientModuleActive("bots") && crm.bot?.configured ? "ON" : "OFF";

    const count = (crm.todayEvents || [])
      .filter((event) => String(event.module_code || "workforce").toLowerCase() === code)
      .length;

    if (count > 0) return count;

    return isClientModuleActive(code) ? "ON" : "-";
  }

  async function loadClientCrmData() {
    const companyId = state.companyId;
    const [employeesResult, eventsResult, botResult] = await Promise.allSettled([
      isClientModuleActive("workforce")
        ? api(`/employees?company_id=${encodeURIComponent(companyId)}&include_archived=true`)
        : Promise.resolve([]),
      api(`/employees/attendance/history?company_id=${encodeURIComponent(companyId)}&limit=200`),
      isClientModuleActive("bots")
        ? api(`/bots/companies/${encodeURIComponent(companyId)}/telegram`)
        : Promise.resolve(null),
    ]);

    const employees = employeesResult.status === "fulfilled" && Array.isArray(employeesResult.value)
      ? employeesResult.value
      : [];

    const events = eventsResult.status === "fulfilled" && Array.isArray(eventsResult.value)
      ? eventsResult.value
      : [];

    const bot = botResult.status === "fulfilled" ? botResult.value : null;
    const latestByEmployee = crmLatestEventByEmployee(events);
    const todayEvents = events.filter(crmIsToday);
    const peopleMap = new Map();

    employees
      .filter((employee) => !["archived", "inactive"].includes(String(employee.status || "").toLowerCase()))
      .forEach((employee) => {
        const id = employee.id || employee.employee_id;
        if (!id) return;
        peopleMap.set(String(id), {
          employee,
          employeeId: id,
          latest: latestByEmployee.get(id) || null,
        });
      });

    latestByEmployee.forEach((latest, employeeId) => {
      const key = String(employeeId);
      if (!peopleMap.has(key)) {
        peopleMap.set(key, {
          employee: {},
          employeeId,
          latest,
        });
      }
    });

    const people = Array.from(peopleMap.values()).map((item) => {
      const employeeEvents = crmEventsForEmployee(events, item.employeeId);
      const metrics = crmShiftMetrics(employeeEvents);
      const latest = metrics.latest || item.latest || null;

      return {
        employee: item.employee,
        employeeId: item.employeeId,
        latest,
        events: employeeEvents,
        status: metrics.status,
        name: crmEmployeeName(item.employee, latest || {}),
        role: item.employee.role || item.employee.employee_type || latest?.employee_role || "-",
        lastAt: latest ? crmDateLabel(latest) : "-",
        lastEvent: latest ? crmEventLabel(latest) : "-",
        channel: latest ? crmChannelLabel(latest.source_channel) : "-",
        metrics,
      };
    });

    const working = people.filter((person) => person.status === "working");
    const onBreak = people.filter((person) => person.status === "on_break");
    const offShift = people.filter((person) => !["working", "on_break"].includes(person.status));

    return {
      employees,
      events,
      todayEvents,
      people,
      working,
      onBreak,
      offShift,
      bot,
      dynamicModules: crmDynamicModuleCodes(),
    };
  }

  function renderCrmCollaboratorCards(people = [], moduleCodes = []) {
    if (!people.length) {
      return `<div class="personal-empty">No hay colaboradores operativos para mostrar.</div>`;
    }

    return `
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;margin-top:18px">
        ${people.map((person) => `
          <article class="client-kpi" style="padding:20px;min-height:180px">
            <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start">
              <div>
                <span>Colaborador</span>
                <strong style="font-size:22px">${h(person.name)}</strong>
              </div>
              <span class="personal-status-pill">${h(crmStatusLabel(person.status))}</span>
            </div>

            <div style="margin-top:18px">
              <span>Cronometro</span>
              <strong style="font-size:30px">${h(person.metrics.timer)}</strong>
            </div>

            <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:18px">
              ${moduleCodes.slice(0, 2).map((code) => `
                <div style="border:1px solid rgba(255,255,255,.12);border-radius:16px;padding:12px;background:rgba(255,255,255,.045)">
                  <span>${h(crmModuleDisplay(code))}</span>
                  <strong style="font-size:16px">${h(crmModuleValueForPerson(code, person))}</strong>
                </div>
              `).join("")}
            </div>
          </article>
        `).join("")}
      </div>
    `;
  }

  async function renderCrmModule() {
    if (!isClientModuleActive("crm")) {
      render();
      return;
    }

    const company = state.company || {};
    const crm = await loadClientCrmData();
    const moduleCards = crm.dynamicModules || crmDynamicModuleCodes();

    $("app").innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, normalizeBranding(state.branding || {}))}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>

            <nav class="client-nav">
              ${renderClientNav("crm")}
            </nav>

            <div class="client-footer-id">
              <strong>Tenant activo</strong><br>
              ${h(state.companyId || "")}
            </div>
          </aside>

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">Modulo CRM Campo</div>
              <h1 class="client-title">CRM Campo</h1>
              <p class="client-muted">Vista viva de colaboradores en turno, pausas y nucleos activos de la empresa.</p>

              <div class="client-actions">
                <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
                <button class="client-btn" type="button" data-client-module="crm">Actualizar</button>
              </div>
            </header>

            <section class="client-panel">
              <div class="client-eyebrow">Estado operativo actual</div>
              <h2>Operacion en vivo</h2>

              <div class="client-kpi-grid">
                <div class="client-kpi">
                  <span>Activos</span>
                  <strong>${h(crm.working.length)}</strong>
                </div>
                <div class="client-kpi">
                  <span>En pausa</span>
                  <strong>${h(crm.onBreak.length)}</strong>
                </div>
                <div class="client-kpi">
                  <span>${h(crmModuleDisplay(moduleCards[0]))}</span>
                  <strong>${h(crmTopCardValue(moduleCards[0], crm))}</strong>
                </div>
                <div class="client-kpi">
                  <span>${h(crmModuleDisplay(moduleCards[1]))}</span>
                  <strong>${h(crmTopCardValue(moduleCards[1], crm))}</strong>
                </div>
              </div>

              <div class="client-eyebrow" style="margin-top:28px">Colaboradores</div>
              <h2>Estado por colaborador</h2>
              ${renderCrmCollaboratorCards(crm.people, moduleCards)}
            </section>
          </section>
        </div>
      </main>
    `;
  }


  async function renderClientModulePlaceholder(code) {
    const company = state.company || {};
    $("app").innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, normalizeBranding(state.branding || {}))}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>
            <nav class="client-nav">${renderClientNav(code)}</nav>
            <div class="client-footer-id"><strong>Tenant activo</strong><br>${h(state.companyId || "")}</div>
          </aside>
          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">Modulo activo</div>
              <h1 class="client-title">${h(moduleLabel(code))}</h1>
              <p class="client-muted">Este modulo esta asignado a la empresa y se construira como pantalla independiente.</p>
              <div class="client-actions"><button class="client-btn" type="button" data-client-back-dashboard>Volver</button></div>
            </header>
          </section>
        </div>
      </main>
    `;
  }

  async function renderPersonalModule() {
    ensurePersonalGridStyles();

    const company = state.company || {};
    let employees = [];
    let loadError = "";

    try {
      employees = await loadPersonalEmployees();
    } catch (error) {
      employees = [];
      loadError = error.message || "No se pudo cargar personal.";
    }

    const rows = Array.isArray(employees) && employees.length
      ? employees
      : [{ status: "active", role: "operator" }];

    $("app").innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, normalizeBranding(state.branding || {}))}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>

            <nav class="client-nav">
              ${renderClientNav("workforce")}
            </nav>

            <div class="client-footer-id">
              <strong>Tenant activo</strong><br>
              ${h(state.companyId || "")}
            </div>
          </aside>

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">Modulo Workforce</div>
              <h1 class="client-title">Personal</h1>
              <p class="client-muted">Gestiona empleados, tecnicos, supervisores y roles conectados a bot, nomina y operacion.</p>

              <div class="personal-toolbar">
                <div class="client-actions">
                  <button class="client-btn" type="button" data-personal-add-row>+ Agregar fila</button>
                  <button class="client-btn" type="button" data-personal-save-all>Guardar cambios</button>
                  <button class="client-btn" type="button" data-personal-history>Historial</button>
                  <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
                </div>
                <input class="personal-search cx-personal-search-input" data-personal-search placeholder="Buscar por nombre, rol, tel?fono, correo o Telegram...">
              </div>

              <div id="personalNotice">${loadError ? `<div class="personal-toast error">${h(loadError)}</div>` : ""}</div>
            </header>

            <section class="client-panel">
              <div class="client-eyebrow">Tabla editable</div>
              <h2>Registro de personal operativo</h2>
              <p class="client-muted">${h(company.name || "Esta empresa")} administra su personal de forma independiente.</p>

              <div class="personal-grid-wrap">
                <div class="personal-grid" id="personalGrid">
                  ${personalGridHeader()}
                  ${rows.map(personalRow).join("")}
                </div>
              </div>
            </section>
          </section>
        </div>
      </main>
    `;
  }

  function bindPersonalModuleEvents() {
    if (window.__clonexaPersonalModuleEventsBound) return;
    window.__clonexaPersonalModuleEventsBound = true;

    document.addEventListener("click", async (event) => {
      const target = event.target;

      if (target.closest("[data-client-back-dashboard]")) {
        render();
        return;
      }

      if (target.closest("[data-personal-history]")) {
        await renderPersonalHistoryModule();
        return;
      }

      if (target.closest("[data-personal-back-list]")) {
        await renderPersonalModule();
        return;
      }

      if (target.closest("[data-personal-history-apply]")) {
        await renderPersonalHistoryModule(readPersonalHistoryFilters());
        return;
      }

      if (target.closest("[data-personal-history-export]")) {
        exportPersonalHistoryCsv();
        return;
      }

      if (target.closest("[data-personal-add-row]")) {
        const grid = document.getElementById("personalGrid");
        if (grid) {
          grid.insertAdjacentHTML("beforeend", personalRow({ status: "active", role: "operator" }));
          showPersonalNotice("Fila agregada. Completa los datos y guarda.");
        }
        return;
      }

      if (target.closest("[data-personal-save-all]")) {
        const rows = Array.from(document.querySelectorAll("[data-personal-row]"));
        const filledRows = rows.filter((row) => {
          const name = row.querySelector('[data-field="full_name"]')?.value || "";
          return String(name).trim().length >= 2;
        });

        if (!filledRows.length) {
          showPersonalNotice("Agrega al menos un nombre antes de guardar.", "error");
          return;
        }

        try {
          for (const row of filledRows) {
            await savePersonalRow(row);
          }
          await renderPersonalModule();
          setTimeout(() => showPersonalNotice("Personal guardado correctamente."), 50);
        } catch (error) {
          showPersonalNotice(error.message || "No se pudo guardar personal.", "error");
        }
        return;
      }

      if (target.closest("[data-personal-save-row]")) {
        const row = target.closest("[data-personal-row]");
        if (row) {
          try {
            await savePersonalRow(row);
            await renderPersonalModule();
            setTimeout(() => showPersonalNotice("Registro guardado correctamente."), 50);
          } catch (error) {
            showPersonalNotice(error.message || "No se pudo guardar la fila.", "error");
          }
        }
        return;
      }

      const actionButton = target.closest("[data-personal-action]");
      if (actionButton) {
        const row = actionButton.closest("[data-personal-row]");
        const employeeId = row?.dataset.employeeId;
        const action = actionButton.dataset.personalAction;

        if (!employeeId || !action) return;

        if (action === "archive" && !confirm("Eliminar este registro? Se archivara para auditoria.")) return;

        try {
          await personalApi(`/employees/${employeeId}/${action}`, {
            method: "POST",
            body: JSON.stringify({}),
          });

          await renderPersonalModule();
          setTimeout(() => showPersonalNotice("Estado actualizado."), 50);
        } catch (error) {
          showPersonalNotice(error.message || "No se pudo actualizar el registro.", "error");
        }
        return;
      }

      const clientAction = target.closest("[data-client-action]");
      if (clientAction) {
        const action = String(clientAction.dataset.clientAction || "");

        if (action === "workforce:add" && isClientModuleActive("workforce")) {
          await renderPersonalModule();
          setTimeout(() => document.querySelector("[data-personal-add-row]")?.click(), 60);
          return;
        }

        if (action === "bots:open" && isClientModuleActive("bots")) {
          await renderBotsModule();
          return;
        }

        if (action === "crm:open" && isClientModuleActive("crm")) {
          await renderCrmModule();
          return;
        }

        if (action === "reports:open" && isClientModuleActive("reports")) {
          await renderClientModulePlaceholder("reports");
          return;
        }
      }

      const moduleTrigger = target.closest("[data-client-module]");
      if (moduleTrigger) {
        const code = String(moduleTrigger.dataset.clientModule || "").trim();

        if (!isClientModuleActive(code)) return;

        if (code === "workforce") {
          await renderPersonalModule();
          return;
        }

        if (code === "bots") {
          await renderBotsModule();
          return;
        }

        if (code === "crm") {
          await renderCrmModule();
          return;
        }

        await renderClientModulePlaceholder(code);
        return;
      }

      if (target.closest("[data-bot-save-name]")) {
        await saveClientBotName();
        return;
      }
    });

    document.addEventListener("input", (event) => {
      const input = event.target.closest("[data-personal-search]");
      if (!input) return;

      const query = String(input.value || "").toLowerCase().trim();

      document.querySelectorAll("[data-personal-row]").forEach((row) => {
        const text = String(row.textContent || "").toLowerCase();
        row.style.display = !query || text.includes(query) ? "contents" : "none";
      });
    });
  }

  bindPersonalModuleEvents();


  function render() {
    const company = state.company || {};
    const b = normalizeBranding(state.branding || {});
    applyBranding();

    const modules = visibleClientModules(activeClientModules());

    $("app").innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, b)}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>

            <nav class="client-nav">
              ${renderClientNav("dashboard")}
            </nav>

            <div class="client-footer-id">
              <strong>Tenant activo</strong><br>
              ${h(state.companyId || company.id || company.company_id || "")}
            </div>
          </aside>

          <section class="client-main">
            <header class="client-hero">
              <div style="display:flex;justify-content:space-between;gap:16px;align-items:flex-start">
                <div>
                  <div class="client-eyebrow">Sistema operativo empresarial</div>
                  <h1 class="client-title">${h(company.name || "Empresa")}</h1>
                  <p class="client-muted">Panel operativo independiente conectado a sus m?dulos activos.</p>
                </div>
                <span class="client-badge">LIVE</span>
              </div>

              <div class="client-kpi-grid">
                ${renderClientHeroKpis(modules, company)}
              </div>

              <div class="client-actions">
                ${renderClientHeroActions(modules)}
              </div>
            </header>

            <section class="client-panel">
              <div style="display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:18px">
                <div>
                  <div class="client-eyebrow">M?dulos del panel</div>
                  <h2>Servicios activos</h2>
                </div>
                <span class="client-badge">${h(modules.length)} modulos activos</span>
              </div>

              <div class="client-module-grid">
                ${modules.length ? modules.map((module) => `
                  <button class="client-module-card" type="button" data-client-module="${h(module.code)}">
                    <div class="client-badge">${h(module.badge)}</div>
                    <strong>${h(module.title)}</strong>
                    <small>${h(module.subtitle)}</small>
                  </button>
                `).join("") : `
                  <div class="client-module-card">
                    <div class="client-badge">OFF</div>
                    <strong>Sin modulos activos</strong>
                    <small>Activa un paquete desde Admin V2</small>
                  </div>
                `}
              </div>
            </section>
          </section>
        </div>
      </main>
    `;
  }

  function renderError(error) {
    $("app").innerHTML = `
      <main class="client-shell">
        <section class="client-panel" style="max-width:900px;margin:12vh auto">
          <div class="client-eyebrow">CLONEXA</div>
          <h1>No se pudo cargar el panel cliente</h1>
          <p>${h(error?.message || error)}</p>
          <p>Verifica company_id y endpoint /api/v1/companies/{id}/experience.</p>
        </section>
      </main>
    `;
  }


  async function loadClientDashboardMetrics(companyId, modules = []) {
    const codes = clientModuleCodes(visibleClientModules(modules));
    const metrics = {};

    if (codes.has("workforce")) {
      try {
        const employees = await api(`/employees?company_id=${encodeURIComponent(companyId)}&include_archived=true`);
        metrics.activeEmployees = Array.isArray(employees)
          ? employees.filter((employee) => String(employee.status || "").toLowerCase() === "active").length
          : 0;
      } catch (error) {
        metrics.activeEmployees = 0;
      }
    }

    if (codes.has("bots")) {
      try {
        const bot = await api(`/bots/companies/${companyId}/telegram`);
        metrics.botConfigured = !!bot?.configured;
        metrics.botStatus = bot?.status || "not_configured";
      } catch (error) {
        metrics.botConfigured = false;
        metrics.botStatus = "error";
      }
    }

    return metrics;
  }

  async function loadByCompanyId(companyId) {
    const companies = await api("/companies");
    const company = Array.isArray(companies)
      ? companies.find((item) => item.id === companyId || item.company_id === companyId)
      : null;

    if (!company) {
      throw new Error(`Empresa no encontrada: ${companyId}`);
    }

    let experience = {};
    try {
      experience = await api(`/companies/${companyId}/experience`);
    } catch (error) {
      experience = {};
    }

    let companyModules = [];
    try {
      companyModules = await api(`/companies/${companyId}/modules`);
    } catch (error) {
      companyModules = [];
    }

    state.company = company;
    state.companyId = company.id || company.company_id || companyId;
    state.experience = experience || {};
    state.companyModules = Array.isArray(companyModules) ? companyModules : [];
    state.dashboardMetrics = await loadClientDashboardMetrics(state.companyId, activeClientModules());
    state.branding =
      experience?.branding ||
      experience?.company_branding ||
      company?.settings_json?.experience?.branding ||
      company?.settings_json?.branding ||
      company?.company_branding ||
      {};

    return state;
  }


  async function init() {
    try {
      const companyId = companyIdFromUrl();

      if (!companyId) {
        window.location.href = "/login";
        return;
      }

      await loadByCompanyId(companyId);
      render();
    } catch (error) {
      console.error("[CLONEXA Client] init error", error);
      state.branding = normalizeBranding({});
      applyBranding();
      renderError(error);
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();

/* CX_PERSONAL_PHASE2_SEARCH_FIX_START */
(function () {
  if (window.__cxPersonalPhase2SearchFixLoaded) return;
  window.__cxPersonalPhase2SearchFixLoaded = true;

  const COLS = [
    "Nombre",
    "Rol",
    "Telefono",
    "Correo",
    "Telegram ID",
    "Fecha ingreso",
    "Hora ordinaria",
    "Hora extra",
    "Descuento 1",
    "Descuento 2",
    "Estado",
    "Acciones"
  ];

  const state = {
    query: "",
    filter: "all",
    sort: "none"
  };

  function cxNorm(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/\s+/g, " ")
      .trim();
  }

  function ensurePhase2Styles() {
    if (document.getElementById("cxPersonalPhase2Styles")) return;

    const style = document.createElement("style");
    style.id = "cxPersonalPhase2Styles";
    style.textContent = `
      .client-hero .personal-search {
        display: none !important;
      }

      .personal-grid-wrap {
        width: 100% !important;
        max-width: 100% !important;
        overflow-x: auto !important;
        overflow-y: hidden !important;
        padding-bottom: 12px !important;
        scrollbar-gutter: stable both-edges !important;
        border-radius: 22px !important;
      }

      .personal-grid {
        min-width: 1460px !important;
        width: max-content !important;
        grid-template-columns:
          150px
          108px
          108px
          155px
          116px
          108px
          104px
          104px
          104px
          104px
          104px
          205px !important;
      }

      .personal-cell {
        min-height: 54px !important;
        padding: 7px !important;
      }

      .personal-head {
        font-size: 11px !important;
        letter-spacing: .045em !important;
        line-height: 1.12 !important;
      }

      .personal-cell input,
      .personal-cell select {
        font-size: 12px !important;
        padding: 8px 7px !important;
        border-radius: 10px !important;
      }

      .personal-actions {
        gap: 5px !important;
        flex-wrap: wrap !important;
      }

      .personal-mini-btn {
        font-size: 11px !important;
        padding: 7px 7px !important;
        border-radius: 9px !important;
        white-space: nowrap !important;
      }

      .personal-sticky-right {
        position: sticky !important;
        right: 0 !important;
        z-index: 5 !important;
        background: rgba(23, 23, 38, .98) !important;
        backdrop-filter: blur(12px) !important;
        box-shadow: -10px 0 22px rgba(0,0,0,.24) !important;
      }

      .personal-head.personal-sticky-right {
        z-index: 8 !important;
      }

      .cx-personal-phase2 {
        margin: 18px 0 18px;
        display: grid;
        gap: 14px;
      }

      .cx-personal-stats {
        display: grid;
        grid-template-columns: repeat(4, minmax(130px, 1fr));
        gap: 10px;
      }

      .cx-personal-stat {
        border: 1px solid rgba(255,255,255,.13);
        background: rgba(255,255,255,.07);
        border-radius: 16px;
        padding: 13px 14px;
        box-shadow: 0 16px 36px rgba(0,0,0,.18);
      }

      .cx-personal-stat span {
        display: block;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: .08em;
        opacity: .72;
        font-weight: 1000;
      }

      .cx-personal-stat strong {
        display: block;
        margin-top: 5px;
        font-size: 22px;
        font-weight: 1000;
      }

            .cx-personal-tools {
        display: grid;
        grid-template-columns: minmax(320px, 1fr) auto 92px;
        gap: 10px;
        align-items: center;
      }

      .cx-personal-search {
        width: 100%;
        border: 1px solid rgba(255,255,255,.16);
        background: rgba(0,0,0,.20);
        color: var(--cx-text, #fff);
        border-radius: 16px;
        padding: 14px 16px;
        font-weight: 900;
        outline: none;
      }

      .cx-personal-search::placeholder {
        color: rgba(255,255,255,.58);
      }

            .cx-personal-filters,
      .cx-personal-export-actions {
        display: flex;
        flex-wrap: nowrap;
        gap: 8px;
        justify-content: flex-end;
        align-items: center;
      }

      
      .cx-personal-csv-btn {
        min-width: 78px;
        text-align: center;
        border-color: rgba(255,255,255,.65);
      }

      .cx-personal-btn {
        border: 1px solid rgba(255,255,255,.14);
        background: rgba(255,255,255,.08);
        color: var(--cx-text, #fff);
        border-radius: 13px;
        padding: 11px 12px;
        font-weight: 1000;
        cursor: pointer;
      }

      .cx-personal-btn.active {
        background: var(--cx-primary, #ff2bd6);
        color: #fff;
        box-shadow: 0 14px 34px rgba(0,0,0,.22);
      }

      .cx-personal-empty {
        margin-top: 12px;
        padding: 14px 16px;
        border: 1px dashed rgba(255,255,255,.20);
        border-radius: 16px;
        background: rgba(0,0,0,.16);
        font-weight: 900;
        display: none;
      }

      .cx-personal-export-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
        flex-wrap: wrap;
      }

      @media (max-width: 1200px) {
        .cx-personal-tools {
          grid-template-columns: 1fr;
        }

        .cx-personal-filters,
        .cx-personal-export-actions {
          justify-content: flex-start;
          flex-wrap: wrap;
        }

        .cx-personal-stats {
          grid-template-columns: repeat(2, minmax(130px, 1fr));
        }
      }
    `;
    document.head.appendChild(style);
  }

  function getGrid() {
    return document.querySelector("#personalGrid.personal-grid, .personal-grid");
  }

  function getRows() {
    return Array.from(document.querySelectorAll("[data-personal-row]"));
  }

  function getField(row, field) {
    const input = row.querySelector(`[data-field="${field}"]`);
    if (!input) return "";

    if (input.tagName === "SELECT") {
      const selected = input.options && input.selectedIndex >= 0 ? input.options[input.selectedIndex] : null;
      return selected ? selected.textContent || input.value : input.value || "";
    }

    return input.value || "";
  }

  function rowStatus(row) {
    return cxNorm(getField(row, "status") || "active");
  }

  function rowSearchText(row) {
    const values = [
      getField(row, "full_name"),
      getField(row, "role"),
      getField(row, "phone"),
      getField(row, "email"),
      getField(row, "telegram_user_id"),
      getField(row, "hire_date"),
      getField(row, "hourly_rate_regular"),
      getField(row, "hourly_rate_extra"),
      getField(row, "deduction_1"),
      getField(row, "deduction_2"),
      getField(row, "status"),
      row.textContent || ""
    ];

    return cxNorm(values.join(" "));
  }

  function rowMatches(row) {
    const query = cxNorm(state.query);
    const status = rowStatus(row);

    if (state.filter === "active" && status !== "activo" && status !== "active") return false;
    if (state.filter === "inactive" && status !== "inactivo" && status !== "inactive") return false;
    if (state.filter === "archived" && status !== "archivado" && status !== "archived") return false;

    if (!query) return true;

    return rowSearchText(row).includes(query);
  }

  function getSortValue(row) {
    if (state.sort === "name") return cxNorm(getField(row, "full_name"));
    if (state.sort === "role") return cxNorm(getField(row, "role"));
    if (state.sort === "hire_date") return cxNorm(getField(row, "hire_date"));
    return "";
  }

  function sortRows() {
    const grid = getGrid();
    const rows = getRows();
    if (!grid || !rows.length || state.sort === "none") return;

    rows.sort((a, b) => {
      const av = getSortValue(a);
      const bv = getSortValue(b);
      return av.localeCompare(bv);
    });

    rows.forEach((row) => grid.appendChild(row));
  }

  function markStickyActions() {
    const headerCells = Array.from(document.querySelectorAll(".personal-grid > .personal-cell.personal-head"));
    if (headerCells.length >= COLS.length) {
      headerCells[COLS.length - 1].classList.add("personal-sticky-right");
    }

    getRows().forEach((row) => {
      const cells = Array.from(row.querySelectorAll(".personal-cell"));
      if (cells.length >= COLS.length) {
        cells[COLS.length - 1].classList.add("personal-sticky-right");
      }
    });
  }

  function stats() {
    const rows = getRows();
    let active = 0;
    let inactive = 0;
    let archived = 0;

    rows.forEach((row) => {
      const status = rowStatus(row);
      if (status === "archivado" || status === "archived") archived += 1;
      else if (status === "inactivo" || status === "inactive") inactive += 1;
      else active += 1;
    });

    return {
      total: rows.length,
      active,
      inactive,
      archived
    };
  }

  function ensureToolbar() {
    const gridWrap = document.querySelector(".personal-grid-wrap");
    if (!gridWrap) return;

    const panel = gridWrap.closest(".client-panel") || gridWrap.parentElement;
    if (!panel) return;

    if (panel.querySelector(".cx-personal-phase2")) return;

    const toolbar = document.createElement("div");
    toolbar.className = "cx-personal-phase2";
    toolbar.innerHTML = `
      <div class="cx-personal-stats">
        <div class="cx-personal-stat"><span>Total</span><strong data-personal-stat="total">0</strong></div>
        <div class="cx-personal-stat"><span>Activos</span><strong data-personal-stat="active">0</strong></div>
        <div class="cx-personal-stat"><span>Inactivos</span><strong data-personal-stat="inactive">0</strong></div>
        <div class="cx-personal-stat"><span>Archivados</span><strong data-personal-stat="archived">0</strong></div>
      </div>

      <div class="cx-personal-tools">
        <input class="cx-personal-search" data-personal-phase2-search placeholder="Buscar coincidencias: nombre, rol, tel?fono, correo, Telegram, estado...">

        <div class="cx-personal-filters">
          <button class="cx-personal-btn active" type="button" data-personal-filter="all">Todos</button>
          <button class="cx-personal-btn" type="button" data-personal-filter="active">Activos</button>
          <button class="cx-personal-btn" type="button" data-personal-filter="inactive">Inactivos</button>
          <button class="cx-personal-btn" type="button" data-personal-filter="archived">Archivados</button>
        </div>

        <div class="cx-personal-export-actions">
          <button class="cx-personal-btn cx-personal-csv-btn" type="button" data-personal-export>CSV</button>
        </div>
      </div>

      <div class="cx-personal-export-row">
        <p class="client-muted" data-personal-results>Mostrando registros.</p>
      </div>

      <div class="cx-personal-empty" data-personal-empty>
        No hay coincidencias para la b?squeda actual.
      </div>
    `;

    panel.insertBefore(toolbar, gridWrap);
  }

  function updateStatsAndResults(visibleCount) {
    const s = stats();

    const total = document.querySelector('[data-personal-stat="total"]');
    const active = document.querySelector('[data-personal-stat="active"]');
    const inactive = document.querySelector('[data-personal-stat="inactive"]');
    const archived = document.querySelector('[data-personal-stat="archived"]');
    const results = document.querySelector("[data-personal-results]");
    const empty = document.querySelector("[data-personal-empty]");

    if (total) total.textContent = s.total;
    if (active) active.textContent = s.active;
    if (inactive) inactive.textContent = s.inactive;
    if (archived) archived.textContent = s.archived;

    if (results) {
      results.textContent = `Mostrando ${visibleCount} de ${s.total} registros.`;
    }

    if (empty) {
      empty.style.display = visibleCount === 0 && s.total > 0 ? "block" : "none";
    }
  }

  function applyPersonalFilters() {
    ensurePhase2Styles();
    ensureToolbar();
    markStickyActions();

    const rows = getRows();
    let visibleCount = 0;

    rows.forEach((row) => {
      const show = rowMatches(row);
      row.style.display = show ? "contents" : "none";
      if (show) visibleCount += 1;
    });

    updateStatsAndResults(visibleCount);
  }

  function exportCsv() {
    const rows = getRows().filter(rowMatches);
    const data = [COLS.slice(0, -1)];

    rows.forEach((row) => {
      data.push([
        getField(row, "full_name"),
        getField(row, "role"),
        getField(row, "phone"),
        getField(row, "email"),
        getField(row, "telegram_user_id"),
        getField(row, "hire_date"),
        getField(row, "hourly_rate_regular"),
        getField(row, "hourly_rate_extra"),
        getField(row, "deduction_1"),
        getField(row, "deduction_2"),
        getField(row, "status")
      ]);
    });

    const csv = data.map((line) => line.map((value) => `"${String(value ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = `clonexa_personal_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();

    URL.revokeObjectURL(url);
  }

  function bindEvents() {
    if (window.__cxPersonalPhase2EventsBound) return;
    window.__cxPersonalPhase2EventsBound = true;

    document.addEventListener("input", (event) => {
      const search = event.target.closest("[data-personal-phase2-search], [data-personal-search], .personal-search");
      if (!search) return;

      state.query = search.value || "";

      document.querySelectorAll("[data-personal-phase2-search], [data-personal-search], .personal-search").forEach((input) => {
        if (input !== search) input.value = state.query;
      });

      applyPersonalFilters();
    });

    document.addEventListener("click", (event) => {
      const filter = event.target.closest("[data-personal-filter]");
      if (filter) {
        state.filter = filter.dataset.personalFilter || "all";

        document.querySelectorAll("[data-personal-filter]").forEach((btn) => {
          btn.classList.toggle("active", btn === filter);
        });

        applyPersonalFilters();
        return;
      }

      const sort = event.target.closest("[data-personal-sort]");
      if (sort) {
        state.sort = sort.dataset.personalSort || "none";
        sortRows();
        applyPersonalFilters();
        return;
      }

      const exportBtn = event.target.closest("[data-personal-export]");
      if (exportBtn) {
        exportCsv();
      }
    });

    document.addEventListener("change", (event) => {
      if (event.target.closest("[data-personal-row]")) {
        applyPersonalFilters();
      }
    });
  }

  function boot() {
    if (!document.querySelector(".personal-grid")) return;

    ensurePhase2Styles();
    ensureToolbar();
    markStickyActions();
    bindEvents();
    applyPersonalFilters();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  const observer = new MutationObserver(() => {
    window.clearTimeout(window.__cxPersonalPhase2Timer);
    window.__cxPersonalPhase2Timer = window.setTimeout(boot, 80);
  });

  observer.observe(document.body, { childList: true, subtree: true });
})();
/* CX_PERSONAL_PHASE2_SEARCH_FIX_END */


/* CX_WORKFORCE_ASISTENCIA_010B_START */
(function () {
  if (window.__cxWorkforceAsistencia010BLoaded) return;
  window.__cxWorkforceAsistencia010BLoaded = true;

  const API = "/api/v1";

  const h = (value) =>
    String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");

  function companyIdFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return params.get("company_id") || params.get("companyId") || params.get("tenant") || "";
  }

  async function api(path, options = {}) {
    const res = await fetch(`${API}${path}`, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${res.status} ${res.statusText} ${text}`);
    }

    return res.json();
  }

  function asistenciaStyles() {
    if (document.getElementById("cxWorkforceAsistencia010BR2Styles")) return;

    const style = document.createElement("style");
    style.id = "cxWorkforceAsistencia010BR2Styles";
    style.textContent = `
      .cx-bitacora-kpis {
        display: grid;
        grid-template-columns: repeat(6, minmax(130px, 1fr));
        gap: 12px;
        margin: 18px 0;
      }

      .cx-bitacora-kpi {
        border: 1px solid rgba(255,255,255,.13);
        background: rgba(255,255,255,.06);
        border-radius: 18px;
        padding: 14px;
        box-shadow: 0 18px 44px rgba(0,0,0,.18);
      }

      .cx-bitacora-kpi span {
        display: block;
        font-size: 11px;
        letter-spacing: .04em;
        text-transform: uppercase;
        opacity: .76;
        margin-bottom: 8px;
      }

      .cx-bitacora-kpi strong {
        font-size: 24px;
        line-height: 1;
      }

      .cx-bitacora-filters {
        display: grid;
        grid-template-columns: 150px 150px minmax(220px, 1fr) 190px 160px 150px;
        gap: 10px;
        align-items: end;
        margin: 18px 0;
      }

      .cx-bitacora-field label {
        display: block;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: .08em;
        opacity: .75;
        margin: 0 0 7px;
      }

      .cx-bitacora-field input,
      .cx-bitacora-field select {
        width: 100%;
        border: 1px solid rgba(255,255,255,.15);
        background: rgba(0,0,0,.18);
        color: inherit;
        border-radius: 14px;
        padding: 12px 12px;
        outline: none;
      }

      .cx-bitacora-field select option {
        color: #111;
      }

      .cx-bitacora-wrap {
        width: 100%;
        overflow-x: auto;
        border-radius: 20px;
        border: 1px solid rgba(255,255,255,.11);
      }

      .cx-bitacora-grid {
        min-width: 1420px;
        display: grid;
        grid-template-columns: 170px 190px 120px 170px 130px 130px minmax(260px, 1.2fr) 130px;
      }

      .cx-bitacora-cell {
        min-height: 54px;
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 10px 12px;
        border-bottom: 1px solid rgba(255,255,255,.08);
        background: rgba(255,255,255,.03);
        overflow-wrap: anywhere;
      }

      .cx-bitacora-head {
        min-height: 44px;
        font-size: 11px;
        letter-spacing: .08em;
        text-transform: uppercase;
        opacity: .82;
        background: rgba(255,255,255,.08);
        position: sticky;
        top: 0;
        z-index: 1;
      }

      .cx-bitacora-badge {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border-radius: 999px;
        padding: 7px 10px;
        font-size: 12px;
        font-weight: 800;
        border: 1px solid rgba(255,255,255,.16);
        background: rgba(255,255,255,.07);
      }

      .cx-bitacora-badge.check_in { background: rgba(0, 210, 145, .18); }
      .cx-bitacora-badge.check_out { background: rgba(113, 128, 150, .20); }
      .cx-bitacora-badge.break_start,
      .cx-bitacora-badge.break_end { background: rgba(255, 183, 77, .18); }
      .cx-bitacora-badge.material_request { background: rgba(255, 43, 166, .18); }
      .cx-bitacora-badge.observation { background: rgba(125, 92, 255, .18); }

      .cx-bitacora-notice {
        margin-top: 12px;
      }

      .cx-bitacora-toast {
        border-radius: 14px;
        padding: 12px 14px;
        border: 1px solid rgba(255,255,255,.14);
        background: rgba(0, 210, 145, .14);
      }

      .cx-bitacora-toast.error {
        background: rgba(255, 80, 80, .16);
      }

      .cx-bitacora-empty {
        border: 1px dashed rgba(255,255,255,.16);
        border-radius: 18px;
        padding: 18px;
        background: rgba(0,0,0,.14);
      }

      @media (max-width: 1100px) {
        .cx-bitacora-kpis {
          grid-template-columns: repeat(2, minmax(140px, 1fr));
        }

        .cx-bitacora-filters {
          grid-template-columns: 1fr;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function todayIsoDate(offsetDays = 0) {
    const date = new Date();
    date.setDate(date.getDate() + offsetDays);
    return date.toISOString().slice(0, 10);
  }

  function fmtDate(value) {
    if (!value) return "-";
    try {
      return new Intl.DateTimeFormat("es", {
        dateStyle: "short",
        timeStyle: "short",
      }).format(new Date(value));
    } catch (_) {
      return String(value);
    }
  }

  function eventLabel(row) {
    const labels = {
      check_in: "Entrada",
      check_out: "Salida",
      break_start: "Pausa",
      break_end: "Reanudación",
      material_request: "Solicitud material",
      material_return: "Devolución material",
      observation: "Observación",
      gps_ping: "GPS",
      task_started: "Tarea iniciada",
      task_completed: "Tarea cerrada",
    };
    return row.event_label || labels[row.event_type] || row.event_type || "Evento";
  }

  function channelLabel(value) {
    const labels = {
      client: "Panel",
      panel: "Panel",
      api: "API",
      bot: "Bot",
      telegram: "Telegram",
      whatsapp: "WhatsApp",
      qr: "QR",
      system: "Sistema",
    };
    return labels[value] || value || "-";
  }

  function asistenciaNotice(message, type = "ok") {
    const box = document.querySelector("[data-asistencia-notice]");
    if (!box) return;
    box.innerHTML = `<div class="cx-bitacora-toast ${type === "error" ? "error" : ""}">${h(message)}</div>`;
    window.clearTimeout(window.__cxAsistenciaNoticeTimer);
    window.__cxAsistenciaNoticeTimer = window.setTimeout(() => {
      if (box) box.innerHTML = "";
    }, 2800);
  }

  function filtersFromDom() {
    const from = document.querySelector("[data-bitacora-from]")?.value || todayIsoDate(-30);
    const to = document.querySelector("[data-bitacora-to]")?.value || todayIsoDate(0);
    const search = document.querySelector("[data-bitacora-search]")?.value || "";
    const eventType = document.querySelector("[data-bitacora-event]")?.value || "";
    const moduleCode = document.querySelector("[data-bitacora-module]")?.value || "";
    const channel = document.querySelector("[data-bitacora-channel]")?.value || "";

    return { from, to, search, eventType, moduleCode, channel };
  }

  function buildHistoryUrl(companyId, filters = {}) {
    const params = new URLSearchParams();
    params.set("company_id", companyId);
    params.set("limit", "500");

    if (filters.from) params.set("date_from", `${filters.from}T00:00:00`);
    if (filters.to) params.set("date_to", `${filters.to}T23:59:59`);
    if (filters.search) params.set("search", filters.search.trim());
    if (filters.eventType) params.set("event_type", filters.eventType);
    if (filters.moduleCode) params.set("module_code", filters.moduleCode);
    if (filters.channel) params.set("source_channel", filters.channel);

    return `/employees/attendance/history?${params.toString()}`;
  }

  function normalizeRows(payload) {
    if (Array.isArray(payload)) return payload;
    if (Array.isArray(payload?.items)) return payload.items;
    if (Array.isArray(payload?.rows)) return payload.rows;
    return [];
  }

  async function loadBitacora(companyId, filters) {
    return normalizeRows(await api(buildHistoryUrl(companyId, filters)));
  }

  function bitacoraKpis(rows) {
    const total = rows.length;
    const entradas = rows.filter((r) => r.event_type === "check_in").length;
    const salidas = rows.filter((r) => r.event_type === "check_out").length;
    const pausas = rows.filter((r) => ["break_start", "break_end"].includes(r.event_type)).length;
    const solicitudes = rows.filter((r) => String(r.event_type || "").includes("request")).length;
    const bot = rows.filter((r) => ["bot", "telegram", "whatsapp"].includes(r.source_channel || r.source)).length;

    return `
      <div class="cx-bitacora-kpis">
        <div class="cx-bitacora-kpi"><span>Total eventos</span><strong>${h(total)}</strong></div>
        <div class="cx-bitacora-kpi"><span>Entradas</span><strong>${h(entradas)}</strong></div>
        <div class="cx-bitacora-kpi"><span>Salidas</span><strong>${h(salidas)}</strong></div>
        <div class="cx-bitacora-kpi"><span>Pausas</span><strong>${h(pausas)}</strong></div>
        <div class="cx-bitacora-kpi"><span>Solicitudes</span><strong>${h(solicitudes)}</strong></div>
        <div class="cx-bitacora-kpi"><span>Bot</span><strong>${h(bot)}</strong></div>
      </div>
    `;
  }

  function bitacoraFilters(filters) {
    return `
      <div class="cx-bitacora-filters">
        <div class="cx-bitacora-field">
          <label>Desde</label>
          <input type="date" data-bitacora-from value="${h(filters.from)}">
        </div>
        <div class="cx-bitacora-field">
          <label>Hasta</label>
          <input type="date" data-bitacora-to value="${h(filters.to)}">
        </div>
        <div class="cx-bitacora-field">
          <label>Buscar</label>
          <input type="search" data-bitacora-search value="${h(filters.search)}" placeholder="Empleado, evento, detalle, canal...">
        </div>
        <div class="cx-bitacora-field">
          <label>Evento</label>
          <select data-bitacora-event>
            <option value="">Todos</option>
            <option value="check_in" ${filters.eventType === "check_in" ? "selected" : ""}>Entrada</option>
            <option value="check_out" ${filters.eventType === "check_out" ? "selected" : ""}>Salida</option>
            <option value="break_start" ${filters.eventType === "break_start" ? "selected" : ""}>Pausa</option>
            <option value="break_end" ${filters.eventType === "break_end" ? "selected" : ""}>Reanudación</option>
            <option value="material_request" ${filters.eventType === "material_request" ? "selected" : ""}>Solicitud material</option>
            <option value="observation" ${filters.eventType === "observation" ? "selected" : ""}>Observación</option>
          </select>
        </div>
        <div class="cx-bitacora-field">
          <label>Canal</label>
          <select data-bitacora-channel>
            <option value="">Todos</option>
            <option value="client" ${filters.channel === "client" ? "selected" : ""}>Panel</option>
            <option value="bot" ${filters.channel === "bot" ? "selected" : ""}>Bot</option>
            <option value="telegram" ${filters.channel === "telegram" ? "selected" : ""}>Telegram</option>
            <option value="whatsapp" ${filters.channel === "whatsapp" ? "selected" : ""}>WhatsApp</option>
            <option value="qr" ${filters.channel === "qr" ? "selected" : ""}>QR</option>
          </select>
        </div>
        <div class="cx-bitacora-field">
          <label>Módulo</label>
          <select data-bitacora-module>
            <option value="">Todos</option>
            <option value="workforce" ${filters.moduleCode === "workforce" ? "selected" : ""}>Workforce</option>
            <option value="materials" ${filters.moduleCode === "materials" ? "selected" : ""}>Materiales</option>
            <option value="field" ${filters.moduleCode === "field" ? "selected" : ""}>Campo</option>
            <option value="gps" ${filters.moduleCode === "gps" ? "selected" : ""}>GPS</option>
            <option value="production" ${filters.moduleCode === "production" ? "selected" : ""}>Producción</option>
          </select>
        </div>
      </div>
      <div class="client-actions" style="margin-bottom: 16px;">
        <button class="client-btn" type="button" data-bitacora-search-btn>Buscar</button>
        <button class="client-btn" type="button" data-asistencia-export>CSV</button>
      </div>
    `;
  }

  function bitacoraGrid(rows) {
    return `
      <div class="cx-bitacora-wrap">
        <div class="cx-bitacora-grid">
          <div class="cx-bitacora-cell cx-bitacora-head">Fecha / hora</div>
          <div class="cx-bitacora-cell cx-bitacora-head">Empleado</div>
          <div class="cx-bitacora-cell cx-bitacora-head">Rol</div>
          <div class="cx-bitacora-cell cx-bitacora-head">Evento</div>
          <div class="cx-bitacora-cell cx-bitacora-head">Canal</div>
          <div class="cx-bitacora-cell cx-bitacora-head">Módulo</div>
          <div class="cx-bitacora-cell cx-bitacora-head">Detalle</div>
          <div class="cx-bitacora-cell cx-bitacora-head">Estado</div>
          ${rows.map((row) => `
            <div class="cx-bitacora-cell">${h(fmtDate(row.occurred_at || row.created_at))}</div>
            <div class="cx-bitacora-cell">${h(row.employee_name || "-")}</div>
            <div class="cx-bitacora-cell">${h(row.employee_role || "-")}</div>
            <div class="cx-bitacora-cell">
              <span class="cx-bitacora-badge ${h(row.event_type || "")}">${h(eventLabel(row))}</span>
            </div>
            <div class="cx-bitacora-cell">${h(channelLabel(row.source_channel || row.source))}</div>
            <div class="cx-bitacora-cell">${h(row.module_code || "workforce")}</div>
            <div class="cx-bitacora-cell">${h(row.detail || row.notes || "-")}</div>
            <div class="cx-bitacora-cell">${h(row.status_after || row.status || "registered")}</div>
          `).join("")}
        </div>
      </div>
    `;
  }

  async function renderAsistencia(customFilters = null) {
    asistenciaStyles();
    const companyId = companyIdFromUrl();
    const app = document.getElementById("app");
    if (!app) return;

    const filters = customFilters || {
      from: todayIsoDate(-30),
      to: todayIsoDate(0),
      search: "",
      eventType: "",
      moduleCode: "",
      channel: "",
    };

    let rows = [];
    let loadError = "";

    try {
      rows = await loadBitacora(companyId, filters);
    } catch (error) {
      rows = [];
      loadError = error.message || "No se pudo cargar la bitácora operativa.";
    }

    window.__cxAsistenciaRows = rows;
    window.__cxAsistenciaFilters = filters;

    app.innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo"><strong>CLONEXA</strong></div>
            <h2 class="client-company-name">Workforce</h2>
            <div class="client-muted">${h(companyId || "tenant")}</div>

            <nav class="client-nav">
              <button type="button" data-asistencia-dashboard>Dashboard</button>
              <button type="button" data-asistencia-personal>Personal</button>
              <button type="button" data-asistencia-historial>Historial</button>
              <button class="active" type="button">Asistencia</button>
            </nav>

            <div class="client-footer-id">
              <strong>Tenant activo</strong><br>
              ${h(companyId || "")}
            </div>
          </aside>

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">Modulo Workforce</div>
              <h1 class="client-title">Asistencia</h1>
              <p class="client-muted">Bitácora operativa de marcaciones e interacciones del personal: bot, panel, QR, solicitudes, observaciones y eventos por empresa.</p>

              <div class="personal-toolbar">
                <div class="client-actions">
                  <button class="client-btn" type="button" data-asistencia-personal>Volver a Personal</button>
                  <button class="client-btn" type="button" data-asistencia-refresh>Actualizar</button>
                  <button class="client-btn" type="button" data-asistencia-export>CSV</button>
                </div>
              </div>

              <div class="cx-bitacora-notice" data-asistencia-notice>
                ${loadError ? `<div class="cx-bitacora-toast error">${h(loadError)}</div>` : ""}
              </div>
            </header>

            <section class="client-panel">
              <div class="client-eyebrow">Auditoría operativa</div>
              <h2>Bitácora de asistencia e interacciones</h2>
              <p class="client-muted">Consulta registros de 15, 20, 30 días o cualquier rango. CRM, Nómina, KPIs, Materiales y GPS consumirán estos eventos sin mezclarse visualmente.</p>

              ${bitacoraFilters(filters)}
              ${bitacoraKpis(rows)}

              ${rows.length ? bitacoraGrid(rows) : `
                <div class="cx-bitacora-empty">
                  No hay eventos para los filtros seleccionados.
                </div>
              `}
            </section>
          </section>
        </div>
      </main>
    `;
  }

  function injectAsistenciaButton() {
    const toolbar = document.querySelector(".personal-toolbar .client-actions");
    if (!toolbar || toolbar.querySelector("[data-personal-asistencia]")) return;

    const historyBtn = toolbar.querySelector("[data-personal-history]");
    const btn = document.createElement("button");
    btn.className = "client-btn";
    btn.type = "button";
    btn.dataset.personalAsistencia = "true";
    btn.textContent = "Asistencia";

    if (historyBtn && historyBtn.nextSibling) {
      toolbar.insertBefore(btn, historyBtn.nextSibling);
    } else if (historyBtn) {
      historyBtn.insertAdjacentElement("afterend", btn);
    } else {
      toolbar.appendChild(btn);
    }
  }

  function exportAsistenciaCsv() {
    const rows = Array.isArray(window.__cxAsistenciaRows) ? window.__cxAsistenciaRows : [];
    const data = [["Fecha/Hora", "Empleado", "Rol", "Evento", "Canal", "Modulo", "Detalle", "Estado"]];

    rows.forEach((row) => {
      data.push([
        fmtDate(row.occurred_at || row.created_at),
        row.employee_name || "",
        row.employee_role || "",
        eventLabel(row),
        channelLabel(row.source_channel || row.source),
        row.module_code || "workforce",
        row.detail || row.notes || "",
        row.status_after || row.status || "registered",
      ]);
    });

    const csv = data.map((line) => line.map((value) => `"${String(value ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = `clonexa_asistencia_bitacora_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();

    URL.revokeObjectURL(url);
  }

  document.addEventListener("click", async (event) => {
    const asistenciaBtn = event.target.closest("[data-personal-asistencia]");
    if (asistenciaBtn) {
      await renderAsistencia();
      return;
    }

    if (event.target.closest("[data-asistencia-personal]")) {
      window.location.href = `/client?company_id=${encodeURIComponent(companyIdFromUrl())}`;
      return;
    }

    if (event.target.closest("[data-asistencia-dashboard]")) {
      window.location.href = `/client?company_id=${encodeURIComponent(companyIdFromUrl())}`;
      return;
    }

    if (event.target.closest("[data-asistencia-historial]")) {
      window.location.href = `/client?company_id=${encodeURIComponent(companyIdFromUrl())}`;
      return;
    }

    if (event.target.closest("[data-asistencia-refresh]")) {
      await renderAsistencia(window.__cxAsistenciaFilters || filtersFromDom());
      return;
    }

    if (event.target.closest("[data-bitacora-search-btn]")) {
      await renderAsistencia(filtersFromDom());
      return;
    }

    if (event.target.closest("[data-asistencia-export]")) {
      exportAsistenciaCsv();
      return;
    }
  });

  document.addEventListener("keydown", async (event) => {
    if (event.key !== "Enter") return;
    const input = event.target.closest("[data-bitacora-search]");
    if (!input) return;
    event.preventDefault();
    await renderAsistencia(filtersFromDom());
  });

  const observer = new MutationObserver(() => {
    window.clearTimeout(window.__cxAsistenciaInjectTimer);
    window.__cxAsistenciaInjectTimer = window.setTimeout(injectAsistenciaButton, 80);
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      asistenciaStyles();
      injectAsistenciaButton();
      observer.observe(document.body, { childList: true, subtree: true });
    });
  } else {
    asistenciaStyles();
    injectAsistenciaButton();
    observer.observe(document.body, { childList: true, subtree: true });
  }
})();
/* CX_WORKFORCE_ASISTENCIA_010B_END */

