
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

  function brandingVolverground(b) {
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
        background: ${brandingVolverground(b)} !important;
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
    field: ["Field Ops", "operación en campo", "FLD"],
    technicians: ["Tecnicos", "inicio turno y estados", "TEC"],
    gps: ["GPS", "ubicacion y rutas", "GPS"],
    tasks: ["Tareas / Solicitudes", "solicitudes operativas", "TSK"],
    requests: ["Solicitudes", "flujo de aprobacion", "REQ"],
    inventory: ["Inventario", "stock y materiales", "INV"],
    materials: ["Materiales", "solicitud y devolucion", "MAT"],
    payroll: ["Nómina", "corte y calculo", "PAY"],
    payroll_biweekly: ["Nómina Quincenal", "corte actual", "PAY"],
    billing: ["Billing", "cobros y facturacion", "BIL"],
    reports: ["Reportes", "metricas y auditoria", "REP"],
    kpis: ["KPIs", "indicadores operativos", "KPI"],
    crm: ["CRM Campo", "operación en vivo", "CRM"],
    settings: ["Configuración", "ajustes del tenant", "CFG"],
    production: ["Producción", "referencias y costos", "PRD"],
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
      source.name || code || `Módulo ${index + 1}`,
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
    return (Array.isArray(modules) ? modules : []).filter((item) => !["core", "core_settings", "settings"].includes(item.code));
  }

  function isClientModuleActivo(code) {
    const normalized = String(code || "").trim();
    if (!normalized || normalized === "core") return false;
    return activeClientModules().some((module) => module.code === normalized && module.enabled);
  }

  function clientVisibleModuleCodes(modules = activeClientModules()) {
    return clientModuleCodes(visibleClientModules(modules));
  }

  function moduleLabel(code) {
    const meta = MODULE_UI[String(code || "").trim()];
    return meta ? meta[0] : String(code || "Módulo");
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

    if (Array.isArray(metrics.kpiDashboardCards) && metrics.kpiDashboardCards.length) {
      return metrics.kpiDashboardCards.slice(0, 4).map((card) => [
        card.label || "KPI",
        String(card.format === "money" ? kpiMoney(card.value) : kpiNumber(card.value, Number(card.value || 0) % 1 === 0 ? 0 : 2))
      ]);
    }

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
      kpis.push(["Tiendas", metrics.storesActivo ?? "OK"]);
    }

    if (!kpis.length) {
      kpis.push(["Empresa", company.name || "Activa"]);
      kpis.push(["Módulos activos", String(total)]);
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

    if (hasAnyClientModule(codes, ["payroll"])) {
      actions.push({ label: "Ver nómina", action: "payroll:open" });
    }

    if (hasAnyClientModule(codes, ["inventory"])) {
      actions.push({ label: "Inventario", action: "inventory:open" });
    }

    if (hasAnyClientModule(codes, ["kpis"])) {
      actions.push({ label: "Ver KPIs", action: "kpis:open" });
    } else if (hasAnyClientModule(codes, ["reports"])) {
      actions.push({ label: "Ver reportes", action: "reports:open" });
    }

    if (!actions.length) {
      actions.push({ label: "Ver operación", action: "dashboard" });
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


      .cx-materials-return-results,
      .cx-materials-return-checklist {
        margin-top: 14px;
        display: grid;
        gap: 10px;
      }
      .cx-materials-order-pick {
        width: 100%;
        text-align: left;
        border: 1px solid rgba(255,255,255,.14);
        background: rgba(255,255,255,.07);
        color: inherit;
        border-radius: 15px;
        padding: 12px 14px;
        cursor: pointer;
        font-weight: 900;
      }
      .cx-materials-order-pick:hover {
        border-color: rgba(255,255,255,.28);
        transform: translateY(-1px);
      }
      .cx-materials-return-summary {
        border: 1px solid rgba(255,255,255,.14);
        background: rgba(255,255,255,.06);
        border-radius: 18px;
        padding: 14px;
        display: grid;
        gap: 5px;
      }
      .cx-materials-return-line {
        border: 1px solid rgba(255,255,255,.12);
        background: rgba(0,0,0,.14);
        border-radius: 18px;
        overflow: hidden;
      }
      .cx-materials-return-line summary {
        cursor: pointer;
        padding: 14px;
        font-weight: 1000;
      }
      .cx-materials-return-units {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
        gap: 8px;
        padding: 0 14px 14px;
      }
      .cx-materials-return-unit {
        display: flex;
        gap: 8px;
        align-items: center;
        padding: 10px 11px;
        border: 1px solid rgba(255,255,255,.10);
        background: rgba(255,255,255,.06);
        border-radius: 13px;
        font-weight: 900;
      }
      .cx-materials-return-unit.disabled {
        opacity: .45;
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
              <div class="client-eyebrow">Módulo Workforce</div>
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
      const baseConfig = await api(`/bots/companies/${state.companyId}/telegram`);
      try {
        const webhookStatus = await api(`/company-bots-v1/companies/${state.companyId}/telegram/status`);
        return { ...(baseConfig || {}), ...(webhookStatus || {}) };
      } catch (statusError) {
        return baseConfig;
      }
    } catch (error) {
      return { configured: false, status: "error", last_error: error.message || "No se pudo cargar bot" };
    }
  }


  function clientBotFlowLabel(value) {
    const code = String(value || "base").toLowerCase();

    const labels = {
      base: "Base / Workforce",
      velvet_references: "Velvet / Referencias producción",
      field_operations: "Campo / GPS / Materiales",
      retail_sales: "Retail / Ventas",
      hospitality_orders: "Hospitality / Pedidos",
    };

    return labels[code] || code;
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
              <div class="client-eyebrow">Módulo Bots</div>
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
              <p class="client-muted">Configuración tecnica administrada desde CLONEXA Admin V2.</p>

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
                <div class="client-kpi">
                  <span>Flujo</span>
                  <strong>${h(clientBotFlowLabel(bot?.flow_code))}</strong>
                </div>
                <div class="client-kpi">
                  <span>Webhook</span>
                  <strong>${h(bot?.webhook_mode === "dedicated" ? "Dedicado" : "Pendiente")}</strong>
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
      production: "Producción",
      sales: "Ventas",
      stores: "Tiendas",
      retail: "Retail",
      inventory: "Inventario",
      stock: "Stock",
      orders: "Pedidos",
      requests: "Solicitudes",
      payroll: "Nómina",
      kpis: "KPIs",
      reports: "Reportes",
      modules: "Módulos",
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
    if (code === "channels") return isClientModuleActivo("bots") ? "Telegram" : "-";

    const event = (person.events || [])
      .slice()
      .reverse()
      .find((item) => String(item.module_code || "workforce").toLowerCase() === code);

    return event ? crmEventLabel(event) : crmModuleFallback(code);
  }

  function crmGpsLatestEvent(person = {}) {
    return (person.events || [])
      .slice()
      .reverse()
      .find((item) => {
        const moduleCode = String(item.module_code || "").toLowerCase();
        const eventType = String(item.event_type || "").toLowerCase();
        return moduleCode === "gps" && ["gps_location", "gps_ping"].includes(eventType);
      });
  }

  function crmGpsStatusFromEvent(event = {}) {
    const payload = event.payload_json || event.payload || {};
    const metadata = event.metadata_json || event.metadata || {};
    return String(
      payload.gps_status ||
      metadata.gps_status ||
      event.gps_status ||
      ""
    ).toLowerCase();
  }

  function crmGpsCoordinatesFromEvent(event = {}) {
    const payload = event.payload_json || event.payload || {};
    const lat = event.latitude ?? payload.latitude;
    const lng = event.longitude ?? payload.longitude;
    if (lat === null || lat === undefined || lng === null || lng === undefined) return "";
    const latNum = Number(lat);
    const lngNum = Number(lng);
    if (!Number.isFinite(latNum) || !Number.isFinite(lngNum)) return `${lat}, ${lng}`;
    return `${latNum.toFixed(6)}, ${lngNum.toFixed(6)}`;
  }

  function crmGpsStatusClass(status = "") {
    const v = String(status || "").toLowerCase();
    if (v === "inside") return "inside";
    if (v === "outside") return "outside";
    return "unconfigured";
  }

  function crmGpsStatusLabel(status = "") {
    const v = String(status || "").toLowerCase();
    if (v === "inside") return "Dentro de perímetro";
    if (v === "outside") return "Fuera de perímetro";
    return "Sin validación";
  }

  function crmGpsChipMarkup(coords = "", status = "") {
    const cleanCoords = String(coords || "").trim();
    if (!cleanCoords) return `<strong style="font-size:16px">${h(crmModuleFallback("gps"))}</strong>`;

    const css = crmGpsStatusClass(status);
    const label = crmGpsStatusLabel(status);
    return `
      <span class="cx-gps-status ${h(css)}" title="${h(label)}">
        <span class="cx-gps-led" aria-hidden="true"></span>
        <span class="cx-gps-coordinates">${h(cleanCoords)}</span>
      </span>
    `;
  }

  function crmModuleValueMarkupForPerson(code, person = {}) {
    if (code !== "gps") return `<strong style="font-size:16px">${h(crmModuleValueForPerson(code, person))}</strong>`;

    const gpsInfo = person.gpsInfo || null;
    if (gpsInfo) {
      const status = String(gpsInfo.gps_status || "").toLowerCase();
      const coords = gpsInfo.coordinates || (
        gpsInfo.latitude !== undefined && gpsInfo.longitude !== undefined
          ? `${Number(gpsInfo.latitude).toFixed(6)}, ${Number(gpsInfo.longitude).toFixed(6)}`
          : ""
      );
      return crmGpsChipMarkup(coords || crmModuleFallback("gps"), status);
    }

    const event = crmGpsLatestEvent(person);
    if (!event) return `<strong style="font-size:16px">${h(crmModuleFallback("gps"))}</strong>`;

    const status = crmGpsStatusFromEvent(event);
    const coords = crmGpsCoordinatesFromEvent(event) || crmEventLabel(event);
    return crmGpsChipMarkup(coords, status);
  }

  function crmTopCardValue(code, crm = {}) {
    if (code === "modules") return `${visibleClientModules(activeClientModules()).length}`;
    if (code === "channels") return isClientModuleActivo("bots") && crm.bot?.configured ? "ON" : "OFF";

    const count = (crm.todayEvents || [])
      .filter((event) => String(event.module_code || "workforce").toLowerCase() === code)
      .length;

    if (count > 0) return count;

    return isClientModuleActivo(code) ? "ON" : "-";
  }

  async function loadClientCrmData() {
    const companyId = state.companyId;
    const [employeesResult, eventsResult, botResult, gpsResult] = await Promise.allSettled([
      isClientModuleActivo("workforce")
        ? api(`/employees?company_id=${encodeURIComponent(companyId)}&include_archived=true`)
        : Promise.resolve([]),
      api(`/employees/attendance/history?company_id=${encodeURIComponent(companyId)}&limit=200`),
      isClientModuleActivo("bots")
        ? api(`/bots/companies/${encodeURIComponent(companyId)}/telegram`)
        : Promise.resolve(null),
      isClientModuleActivo("gps")
        ? api(`/gps/companies/${encodeURIComponent(companyId)}/summary`)
        : Promise.resolve(null),
    ]);

    const employees = employeesResult.status === "fulfilled" && Array.isArray(employeesResult.value)
      ? employeesResult.value
      : [];

    const events = eventsResult.status === "fulfilled" && Array.isArray(eventsResult.value)
      ? eventsResult.value
      : [];

    const bot = botResult.status === "fulfilled" ? botResult.value : null;
    const gpsSummary = gpsResult.status === "fulfilled" && gpsResult.value ? gpsResult.value : null;
    const gpsPeopleMap = new Map((gpsSummary?.people || []).map((item) => [String(item.employee_id || item.employeeId || ""), item]));
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
        gpsInfo: gpsPeopleMap.get(String(item.employeeId)) || null,
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
      gpsSummary,
      dynamicModules: crmDynamicModuleCodes(),
    };
  }

  function renderCrmColaboradorCards(people = [], moduleCodes = []) {
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
                  ${crmModuleValueMarkupForPerson(code, person)}
                </div>
              `).join("")}
            </div>
          </article>
        `).join("")}
      </div>
    `;
  }

  async function renderCrmModule() {
    if (!isClientModuleActivo("crm")) {
      render();
      return;
    }

    if (isClientModuleActivo("gps")) ensureGpsStyles();

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
              <div class="client-eyebrow">Módulo CRM Campo</div>
              <h1 class="client-title">CRM Campo</h1>
              <p class="client-muted">Vista viva de colaboradores en turno, pausas y nucleos activos de la empresa.</p>

              <div class="client-actions">
                <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
                <button class="client-btn" type="button" data-client-module="crm">Actualizar</button>
              </div>
            </header>

            <section class="client-panel">
              <div class="client-eyebrow">Estado operativo actual</div>
              <h2>Operación en vivo</h2>

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
              ${renderCrmColaboradorCards(crm.people, moduleCards)}
            </section>
          </section>
        </div>
      </main>
    `;
  }





  /* CX_GPS_PERIMETERS_014B_START */
  function ensureGpsStyles() {
    if (document.getElementById("cxGpsPerimetersStyles")) return;
    const style = document.createElement("style");
    style.id = "cxGpsPerimetersStyles";
    style.textContent = `
      .cx-gps-grid {
        display: grid;
        grid-template-columns: 70px minmax(160px, 1fr) repeat(4, minmax(130px, 1fr)) 110px;
        gap: 10px;
        align-items: center;
        margin-top: 16px;
      }
      .cx-gps-head {
        font-size: 11px;
        letter-spacing: .12em;
        text-transform: uppercase;
        opacity: .72;
        font-weight: 1000;
      }
      .cx-gps-input {
        width: 100%;
        border: 1px solid rgba(255,255,255,.16);
        background: rgba(0,0,0,.22);
        color: var(--cx-text, #fff);
        border-radius: 14px;
        padding: 12px 13px;
        font-weight: 900;
        outline: none;
      }
      .cx-gps-check {
        display: flex;
        align-items: center;
        justify-content: center;
        min-height: 42px;
        border-radius: 14px;
        background: rgba(255,255,255,.06);
        border: 1px solid rgba(255,255,255,.12);
      }
      .client-kpi .cx-gps-status,
      .cx-gps-status {
        display: inline-grid;
        grid-template-columns: 8px minmax(0, 1fr);
        align-items: center;
        gap: 8px;
        width: 100%;
        max-width: 100%;
        box-sizing: border-box;
        border-radius: 14px;
        padding: 9px 10px;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
        font-size: 12px !important;
        line-height: 1.25;
        font-weight: 850;
        letter-spacing: .01em !important;
        text-transform: none !important;
        text-shadow: none !important;
        -webkit-text-stroke: 0 transparent !important;
        transform: none !important;
        border: 1px solid rgba(255,255,255,.14);
        overflow: hidden;
        white-space: normal;
      }
      .cx-gps-coordinates {
        display: block;
        min-width: 0;
        overflow-wrap: anywhere;
      }
      .cx-gps-led {
        width: 8px;
        height: 8px;
        border-radius: 999px;
        display: inline-block;
        box-shadow: 0 0 12px currentColor;
      }
      .cx-gps-status.inside {
        color: #39f28a !important;
        background: rgba(15,185,95,.13);
        border-color: rgba(57,242,138,.42);
      }
      .cx-gps-status.outside {
        color: #ffb347 !important;
        background: rgba(255,161,38,.13);
        border-color: rgba(255,179,71,.46);
      }
      .cx-gps-status.unconfigured {
        color: rgba(255,255,255,.78) !important;
        background: rgba(255,255,255,.08);
        border-color: rgba(255,255,255,.14);
      }
      .cx-gps-status.inside .cx-gps-led {
        background: #39f28a;
      }
      .cx-gps-status.outside .cx-gps-led {
        background: #ffb347;
      }
      .cx-gps-status.unconfigured .cx-gps-led {
        background: rgba(255,255,255,.58);
      }
      @media (max-width: 1200px) {
        .cx-gps-grid {
          grid-template-columns: 1fr;
        }
        .cx-gps-head {
          display: none;
        }
      }
    `;
    document.head.appendChild(style);
  }

  async function loadGpsPerimeters() {
    if (!state.companyId) return { perimeters: [] };
    return api(`/gps/companies/${encodeURIComponent(state.companyId)}/perimeters`);
  }

  async function loadGpsSummary() {
    if (!state.companyId) return { inside: 0, outside: 0, sent_location: 0, active_people: 0 };
    return api(`/gps/companies/${encodeURIComponent(state.companyId)}/summary`);
  }

  function gpsEmptyPerimeter(slot) {
    return {
      slot,
      name: `Punto ${slot}`,
      latitude_min: "",
      latitude_max: "",
      longitude_min: "",
      longitude_max: "",
      is_active: slot === 1,
    };
  }

  function gpsPerimeterRows(perimeters = []) {
    const bySlot = new Map((perimeters || []).map((item) => [Number(item.slot), item]));
    const rows = [];
    for (let slot = 1; slot <= 5; slot += 1) {
      rows.push({ ...gpsEmptyPerimeter(slot), ...(bySlot.get(slot) || {}) });
    }
    return rows;
  }

  function gpsNumberValue(value) {
    if (value === null || value === undefined || value === "") return "";
    const n = Number(value);
    return Number.isFinite(n) ? String(n) : "";
  }

  function renderGpsPerimeterRow(row = {}) {
    const slot = Number(row.slot || 1);
    return `
      <input type="hidden" data-gps-field="slot" value="${h(slot)}">
      <div><strong>${h(slot)}</strong></div>
      <input class="cx-gps-input" data-gps-field="name" value="${h(row.name || `Punto ${slot}`)}" placeholder="Nombre punto">
      <input class="cx-gps-input" data-gps-field="latitude_min" value="${h(gpsNumberValue(row.latitude_min))}" placeholder="Latitud desde">
      <input class="cx-gps-input" data-gps-field="latitude_max" value="${h(gpsNumberValue(row.latitude_max))}" placeholder="Latitud hasta">
      <input class="cx-gps-input" data-gps-field="longitude_min" value="${h(gpsNumberValue(row.longitude_min))}" placeholder="Longitud desde (-74...)">
      <input class="cx-gps-input" data-gps-field="longitude_max" value="${h(gpsNumberValue(row.longitude_max))}" placeholder="Longitud hasta (-74...)">
      <label class="cx-gps-check">
        <input type="checkbox" data-gps-field="is_active" ${row.is_active === false ? "" : "checked"}>
      </label>
    `;
  }

  function gpsReadPerimetersFromDom() {
    const grid = document.querySelector("[data-gps-perimeters-grid]");
    if (!grid) return [];

    const rows = [];
    const chunks = Array.from(grid.querySelectorAll("[data-gps-row]"));
    chunks.forEach((row) => {
      const get = (field) => row.querySelector(`[data-gps-field="${field}"]`);
      const toNumberOrNull = (value) => {
        const text = String(value ?? "").trim().replace(",", ".");
        if (!text) return null;
        const n = Number(text);
        return Number.isFinite(n) ? n : null;
      };

      rows.push({
        slot: Number(get("slot")?.value || rows.length + 1),
        name: String(get("name")?.value || "").trim(),
        latitude_min: toNumberOrNull(get("latitude_min")?.value),
        latitude_max: toNumberOrNull(get("latitude_max")?.value),
        longitude_min: toNumberOrNull(get("longitude_min")?.value),
        longitude_max: toNumberOrNull(get("longitude_max")?.value),
        is_active: !!get("is_active")?.checked,
      });
    });

    return rows.slice(0, 5);
  }

  function showGpsNotice(message, type = "ok") {
    const box = document.getElementById("gpsNotice");
    if (!box) return;
    box.innerHTML = `<div class="personal-toast ${type === "error" ? "error" : "ok"}">${h(message)}</div>`;
    window.clearTimeout(window.__gpsNoticeTimer);
    window.__gpsNoticeTimer = window.setTimeout(() => {
      if (box) box.innerHTML = "";
    }, 2800);
  }

  async function saveGpsPerimeters() {
    const perimeters = gpsReadPerimetersFromDom();
    await api(`/gps/companies/${encodeURIComponent(state.companyId)}/perimeters`, {
      method: "PUT",
      body: JSON.stringify({ perimeters }),
    });
    await renderGpsModule();
    setTimeout(() => showGpsNotice("Perímetros GPS guardados."), 60);
  }

  async function renderGpsModule() {
    if (!isClientModuleActivo("gps")) {
      render();
      return;
    }

    ensureGpsStyles();

    const company = state.company || {};
    let perimetersData = { perimeters: gpsPerimeterRows([]) };
    let summary = { inside: 0, outside: 0, sent_location: 0, active_people: 0 };
    let loadError = "";

    try {
      [perimetersData, summary] = await Promise.all([loadGpsPerimeters(), loadGpsSummary()]);
    } catch (error) {
      loadError = error.message || "No se pudo cargar GPS.";
    }

    const rows = gpsPerimeterRows(perimetersData.perimeters || []);
    const inside = Number(summary.inside || 0);
    const outside = Number(summary.outside || 0);
    const sent = Number(summary.sent_location || 0);

    $("app").innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, normalizeBranding(state.branding || {}))}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>

            <nav class="client-nav">
              ${renderClientNav("gps")}
            </nav>

            <div class="client-footer-id">
              <strong>Tenant activo</strong><br>
              ${h(state.companyId || "")}
            </div>
          </aside>

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">Módulo GPS</div>
              <h1 class="client-title">GPS</h1>
              <p class="client-muted">Configura hasta 5 perímetros permitidos. CLONEXA valida las ubicaciones recibidas por el bot.</p>

              <div class="client-actions">
                <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
                <button class="client-btn" type="button" data-gps-refresh>Actualizar</button>
              </div>

              <div id="gpsNotice">${loadError ? `<div class="personal-toast error">${h(loadError)}</div>` : ""}</div>
            </header>

            <section class="client-panel">
              <div class="client-eyebrow">Validación operativa</div>
              <h2>Resumen GPS</h2>

              <div class="client-kpi-grid">
                <div class="client-kpi">
                  <span>Ubicaciones enviadas</span>
                  <strong>${h(sent)}</strong>
                </div>
                <div class="client-kpi">
                  <span>Dentro de perímetro</span>
                  <strong>${h(inside)}</strong>
                </div>
                <div class="client-kpi">
                  <span>Fuera de perímetro</span>
                  <strong>${h(outside)}</strong>
                </div>
              </div>

              <div class="client-eyebrow" style="margin-top:28px">Parámetros permitidos</div>
              <h2>Perímetros</h2>
              <p class="client-muted">El bot solo envía ubicación. La validación dentro/fuera la hace CLONEXA con estos parámetros.</p>

              <div class="cx-gps-grid">
                <div class="cx-gps-head">#</div>
                <div class="cx-gps-head">Punto</div>
                <div class="cx-gps-head">Lat desde</div>
                <div class="cx-gps-head">Lat hasta</div>
                <div class="cx-gps-head">Lng desde</div>
                <div class="cx-gps-head">Lng hasta</div>
                <div class="cx-gps-head">Activo</div>
              </div>

              <div data-gps-perimeters-grid>
                ${rows.map((row) => `
                  <div class="cx-gps-grid" data-gps-row>
                    ${renderGpsPerimeterRow(row)}
                  </div>
                `).join("")}
              </div>

              <div class="client-actions" style="margin-top:22px">
                <button class="client-btn" type="button" data-gps-save>Guardar perímetros</button>
              </div>
            </section>
          </section>
        </div>
      </main>
    `;
  }
  /* CX_GPS_PERIMETERS_014B_END */






  /* CX_INVENTORY_BASE_015B_START */
  function ensureInventoryStyles() {
    if (document.getElementById("cxInventoryBaseStyles")) return;
    const style = document.createElement("style");
    style.id = "cxInventoryBaseStyles";
    style.textContent = `
      .cx-inv-modebar {
        display:flex;
        flex-wrap:wrap;
        gap:12px;
        margin:18px 0;
      }
      .cx-inv-modebar button {
        border: 1px solid rgba(255,255,255,.16);
        background: rgba(255,255,255,.08);
        color: inherit;
        border-radius: 16px;
        padding: 12px 16px;
        font-weight: 1000;
        cursor: pointer;
      }
      .cx-inv-modebar button.active {
        background: linear-gradient(135deg, var(--cx-secondary, #00ff88), var(--cx-primary, #ff2bd6));
        color: #050509;
        box-shadow: 0 14px 34px rgba(255,43,214,.18);
      }
      .cx-inv-form {
        display:grid;
        grid-template-columns: repeat(5, minmax(140px, 1fr)) auto;
        gap:12px;
        align-items:end;
        margin: 18px 0 22px;
      }
      .cx-inv-field label {
        display:block;
        font-size:11px;
        text-transform:uppercase;
        letter-spacing:.12em;
        font-weight:1000;
        opacity:.72;
        margin-bottom:7px;
      }
      .cx-inv-field input,
      .cx-inv-field select {
        width:100%;
        border: 1px solid rgba(255,255,255,.16);
        background: rgba(0,0,0,.20);
        color: var(--cx-text, #fff);
        border-radius: 15px;
        padding: 12px 13px;
        font-weight: 900;
        outline: none;
      }
      .cx-inv-search {
        width:min(520px, 100%);
        border:1px solid rgba(255,255,255,.16);
        background: rgba(0,0,0,.20);
        color: var(--cx-text, #fff);
        border-radius: 16px;
        padding: 14px 16px;
        font-weight: 900;
        margin: 8px 0 18px;
        outline:none;
      }
      .cx-inv-table-wrap {
        width:100%;
        max-width:100%;
        overflow-x:auto;
        border: 1px solid rgba(255,255,255,.12);
        border-radius: 22px;
        background: rgba(0,0,0,.12);
        box-shadow: 0 18px 48px rgba(0,0,0,.20);
      }
      .cx-inv-table {
        min-width: 1160px;
        width:100%;
        border-collapse: collapse;
      }
      .cx-inv-table th,
      .cx-inv-table td {
        padding: 13px 12px;
        border-bottom: 1px solid rgba(255,255,255,.08);
        text-align:left;
        vertical-align:middle;
      }
      .cx-inv-table th {
        background: rgba(255,255,255,.07);
        text-transform: uppercase;
        letter-spacing:.10em;
        font-size: 11px;
        opacity:.76;
      }
      .cx-inv-table td {
        font-weight: 850;
      }
      .cx-inv-table input,
      .cx-inv-table select {
        width:100%;
        border:1px solid rgba(255,255,255,.13);
        background: rgba(0,0,0,.20);
        color: inherit;
        border-radius: 12px;
        padding: 10px 10px;
        font-weight: 900;
        outline:none;
      }
      .cx-inv-actions {
        display:flex;
        flex-wrap:wrap;
        gap:8px;
      }
      .cx-inv-action {
        border:1px solid rgba(255,255,255,.14);
        background: rgba(255,255,255,.08);
        color: inherit;
        border-radius: 12px;
        padding: 9px 10px;
        font-weight: 1000;
        cursor:pointer;
      }
      .cx-inv-action.primary {
        background: linear-gradient(135deg, var(--cx-secondary, #00ff88), var(--cx-primary, #ff2bd6));
        color:#050509;
      }
      .cx-inv-stock {
        display:inline-flex;
        align-items:center;
        border-radius:999px;
        padding: 8px 11px;
        font-weight: 1000;
        border:1px solid rgba(255,255,255,.14);
        background: rgba(255,255,255,.08);
      }
      .cx-inv-stock.low {
        color:#ffb45f;
        background: rgba(255,153,0,.14);
        border-color: rgba(255,153,0,.26);
      }
      .cx-inv-status {
        display:inline-flex;
        align-items:center;
        border-radius:999px;
        padding: 8px 11px;
        font-size: 12px;
        font-weight:1000;
        border:1px solid rgba(255,255,255,.14);
        background: rgba(255,255,255,.08);
      }
      .cx-inv-status.active {
        color:#39f28a;
        background: rgba(0,255,136,.12);
      }
      .cx-inv-status.inactive {
        color:#b9b9c6;
      }

      .cx-materials-return-results,
      .cx-materials-return-checklist {
        margin-top: 14px;
        display: grid;
        gap: 10px;
      }
      .cx-materials-order-pick {
        width: 100%;
        text-align: left;
        border: 1px solid rgba(255,255,255,.14);
        background: rgba(255,255,255,.07);
        color: inherit;
        border-radius: 15px;
        padding: 12px 14px;
        cursor: pointer;
        font-weight: 900;
      }
      .cx-materials-order-pick:hover {
        border-color: rgba(255,255,255,.28);
        transform: translateY(-1px);
      }
      .cx-materials-return-summary {
        border: 1px solid rgba(255,255,255,.14);
        background: rgba(255,255,255,.06);
        border-radius: 18px;
        padding: 14px;
        display: grid;
        gap: 5px;
      }
      .cx-materials-return-line {
        border: 1px solid rgba(255,255,255,.12);
        background: rgba(0,0,0,.14);
        border-radius: 18px;
        overflow: hidden;
      }
      .cx-materials-return-line summary {
        cursor: pointer;
        padding: 14px;
        font-weight: 1000;
      }
      .cx-materials-return-units {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
        gap: 8px;
        padding: 0 14px 14px;
      }
      .cx-materials-return-unit {
        display: flex;
        gap: 8px;
        align-items: center;
        padding: 10px 11px;
        border: 1px solid rgba(255,255,255,.10);
        background: rgba(255,255,255,.06);
        border-radius: 13px;
        font-weight: 900;
      }
      .cx-materials-return-unit.disabled {
        opacity: .45;
      }

      @media (max-width: 1100px) {
        .cx-inv-form { grid-template-columns: 1fr; }
        .cx-inv-table { min-width: 980px; }
      }
    `;
    document.head.appendChild(style);
  }

  function inventoryNumber(value) {
    if (value === null || value === undefined || value === "") return 0;
    const n = Number(String(value).replace(",", "."));
    return Number.isFinite(n) ? n : 0;
  }

  function inventoryQtyLabel(value) {
    const n = inventoryNumber(value);
    return n.toLocaleString("es-CO", { maximumFractionDigits: 2 });
  }

  function inventoryStatusLabel(status = "") {
    return String(status || "active").toLowerCase() === "inactive" ? "Inactivo" : "Activo";
  }

  function inventoryMode() {
    return window.__cxInventoryMode || "create";
  }

  function setInventoryMode(mode) {
    window.__cxInventoryMode = ["create", "modify"].includes(mode) ? mode : "create";
  }

  async function loadInventoryItems(query = "") {
    if (!state.companyId) return { summary: {}, items: [] };
    const qs = query ? `&q=${encodeURIComponent(query)}` : "";
    return api(`/inventory/companies/${encodeURIComponent(state.companyId)}/items?include_inactive=true&limit=800${qs}`);
  }

  function showInventoryNotice(message, type = "ok") {
    const box = document.getElementById("inventoryNotice");
    if (!box) return;
    box.innerHTML = `<div class="personal-toast ${type === "error" ? "error" : "ok"}">${h(message)}</div>`;
    window.clearTimeout(window.__inventoryNoticeTimer);
    window.__inventoryNoticeTimer = window.setTimeout(() => {
      if (box) box.innerHTML = "";
    }, 3000);
  }

  function inventoryCreatePayload() {
    return {
      name_reference: String(document.getElementById("inventoryCreateName")?.value || "").trim(),
      size: String(document.getElementById("inventoryCreateSize")?.value || "").trim(),
      color: String(document.getElementById("inventoryCreateColor")?.value || "").trim(),
      initial_quantity: inventoryNumber(document.getElementById("inventoryCreateQty")?.value || 0),
      min_stock: inventoryNumber(document.getElementById("inventoryCreateMin")?.value || 0),
    };
  }

  async function createInventoryItem() {
    const payload = inventoryCreatePayload();
    if (!payload.name_reference) {
      showInventoryNotice("Nombre / referencia es obligatorio.", "error");
      return;
    }
    await api(`/inventory/companies/${encodeURIComponent(state.companyId)}/items`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setInventoryMode("modify");
    await renderInventoryModule();
    setTimeout(() => showInventoryNotice("Material creado en inventario."), 80);
  }

  function inventoryRowPayload(row) {
    return {
      name_reference: String(row.querySelector('[data-inventory-field="name_reference"]')?.value || "").trim(),
      size: String(row.querySelector('[data-inventory-field="size"]')?.value || "").trim(),
      color: String(row.querySelector('[data-inventory-field="color"]')?.value || "").trim(),
      min_stock: inventoryNumber(row.querySelector('[data-inventory-field="min_stock"]')?.value || 0),
      status: String(row.querySelector('[data-inventory-field="status"]')?.value || "active"),
    };
  }

  async function updateInventoryItem(itemId) {
    const row = document.querySelector(`[data-inventory-row="${CSS.escape(String(itemId))}"]`);
    if (!row) return;
    await api(`/inventory/items/${encodeURIComponent(itemId)}`, {
      method: "PATCH",
      body: JSON.stringify(inventoryRowPayload(row)),
    });
    await renderInventoryModule();
    setTimeout(() => showInventoryNotice("Material actualizado."), 80);
  }

  async function addInventoryEntry(itemId) {
    const input = document.querySelector(`[data-inventory-entry-qty="${CSS.escape(String(itemId))}"]`);
    const quantity = inventoryNumber(input?.value || 0);
    if (quantity <= 0) {
      showInventoryNotice("Ingresa una cantidad mayor a cero.", "error");
      return;
    }
    await api(`/inventory/items/${encodeURIComponent(itemId)}/entry`, {
      method: "POST",
      body: JSON.stringify({ quantity, notes: "Entrada desde Inventario" }),
    });
    await renderInventoryModule();
    setTimeout(() => showInventoryNotice("Entrada registrada. Stock actualizado."), 80);
  }

  async function disableInventoryItem(itemId) {
    await api(`/inventory/items/${encodeURIComponent(itemId)}/disable`, { method: "POST" });
    await renderInventoryModule();
    setTimeout(() => showInventoryNotice("Material deshabilitado."), 80);
  }

  function exportInventoryCsv() {
    const rows = Array.isArray(window.__cxInventoryRows) ? window.__cxInventoryRows : [];
    const headers = ["Nombre / referencia", "Tamaño", "Color", "Stock actual", "Stock minimo", "Alerta", "Estado"];
    const csvRows = [headers].concat(rows.map((row) => [
      row.name_reference || "",
      row.size || "",
      row.color || "",
      row.current_stock ?? 0,
      row.min_stock ?? 0,
      row.alert_low ? "Stock bajo" : "",
      inventoryStatusLabel(row.status),
    ]));

    const csv = csvRows
      .map((items) => items.map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`).join(","))
      .join("\n");

    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `clonexa_inventario_${state.companyId || "empresa"}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function renderInventoryCreatePanel() {
    return `
      <section class="client-panel">
        <div class="client-eyebrow">Crear material / producto</div>
        <h2>Nuevo registro de inventario</h2>
        <p class="client-muted">El stock actual se crea desde la cantidad inicial como movimiento. Luego solo cambia por entradas, entregas y devoluciones.</p>

        <div class="cx-inv-form">
          <div class="cx-inv-field">
            <label>Nombre / referencia</label>
            <input id="inventoryCreateName" placeholder="Ej: Cable UTP">
          </div>
          <div class="cx-inv-field">
            <label>Tamaño</label>
            <input id="inventoryCreateSize" placeholder="Ej: 20m / M / 1kg">
          </div>
          <div class="cx-inv-field">
            <label>Color</label>
            <input id="inventoryCreateColor" placeholder="Ej: Azul">
          </div>
          <div class="cx-inv-field">
            <label>Cantidad inicial</label>
            <input id="inventoryCreateQty" type="number" min="0" step="0.01" value="0">
          </div>
          <div class="cx-inv-field">
            <label>Mínimo alerta</label>
            <input id="inventoryCreateMin" type="number" min="0" step="0.01" value="0">
          </div>
          <button class="client-btn" type="button" data-inventory-create>Crear</button>
        </div>
      </section>
    `;
  }

  function renderInventoryRow(row = {}) {
    const status = String(row.status || "active").toLowerCase();
    const low = !!row.alert_low;
    return `
      <tr data-inventory-row="${h(row.id)}">
        <td><input data-inventory-field="name_reference" value="${h(row.name_reference || "")}"></td>
        <td><input data-inventory-field="size" value="${h(row.size || "")}"></td>
        <td><input data-inventory-field="color" value="${h(row.color || "")}"></td>
        <td><span class="cx-inv-stock ${low ? "low" : ""}">${h(inventoryQtyLabel(row.current_stock))}</span></td>
        <td><input data-inventory-field="min_stock" type="number" min="0" step="0.01" value="${h(row.min_stock ?? 0)}"></td>
        <td><span class="cx-inv-status ${h(status)}">${h(inventoryStatusLabel(status))}</span>${low ? `<br><small class="client-muted">Stock bajo</small>` : ""}</td>
        <td>
          <select data-inventory-field="status">
            <option value="active" ${status !== "inactive" ? "selected" : ""}>Activo</option>
            <option value="inactive" ${status === "inactive" ? "selected" : ""}>Inactivo</option>
          </select>
        </td>
        <td>
          <input data-inventory-entry-qty="${h(row.id)}" type="number" min="0" step="0.01" placeholder="Cantidad">
        </td>
        <td>
          <div class="cx-inv-actions">
            <button class="cx-inv-action primary" type="button" data-inventory-update="${h(row.id)}">Guardar</button>
            <button class="cx-inv-action" type="button" data-inventory-entry="${h(row.id)}">Ingresar</button>
            <button class="cx-inv-action" type="button" data-inventory-disable="${h(row.id)}">Deshabilitar</button>
          </div>
        </td>
      </tr>
    `;
  }

  function renderInventoryModifyPanel(rows = []) {
    return `
      <section class="client-panel">
        <div class="client-eyebrow">Modificar material</div>
        <h2>Buscar y actualizar</h2>
        <p class="client-muted">El stock actual es solo lectura. Para sumar stock usa “Ingresar” y CLONEXA crea movimiento de inventario.</p>
        <input class="cx-inv-search" data-inventory-search placeholder="🔎 Buscar por nombre, referencia, tamaño o color...">

        <div class="cx-inv-table-wrap">
          <table class="cx-inv-table">
            <thead>
              <tr>
                <th>Nombre / referencia</th>
                <th>Tamaño</th>
                <th>Color</th>
                <th>Stock actual</th>
                <th>Mínimo alerta</th>
                <th>Alerta</th>
                <th>Estado</th>
                <th>Ingresar cantidad</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              ${rows.length ? rows.map(renderInventoryRow).join("") : `<tr><td colspan="9">No hay materiales en inventario.</td></tr>`}
            </tbody>
          </table>
        </div>
      </section>
    `;
  }

  async function renderInventoryModule() {
    if (!isClientModuleActivo("inventory")) {
      render();
      return;
    }

    ensureInventoryStyles();

    const company = state.company || {};
    let data = { summary: {}, items: [] };
    let loadError = "";

    try {
      data = await loadInventoryItems();
    } catch (error) {
      loadError = error.message || "No se pudo cargar Inventario.";
    }

    const rows = Array.isArray(data.items) ? data.items : [];
    const summary = data.summary || {};
    window.__cxInventoryRows = rows;
    const mode = inventoryMode();

    $("app").innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, normalizeBranding(state.branding || {}))}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>
            <nav class="client-nav">${renderClientNav("inventory")}</nav>
            <div class="client-footer-id"><strong>Tenant activo</strong><br>${h(state.companyId || "")}</div>
          </aside>

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">Módulo Inventario</div>
              <h1 class="client-title">Inventario</h1>
              <p class="client-muted">Catálogo operativo, mínimos y stock actual de solo lectura. Materiales descontará o devolverá stock en la siguiente integración.</p>
              <div class="client-actions">
                <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
                <button class="client-btn" type="button" data-inventory-refresh>Actualizar</button>
                <button class="client-btn" type="button" data-inventory-export>CSV</button>
              </div>
              <div id="inventoryNotice">${loadError ? `<div class="personal-toast error">${h(loadError)}</div>` : ""}</div>
            </header>

            <section class="client-panel">
              <div class="client-eyebrow">Resumen</div>
              <h2>Estado del inventario</h2>
              <div class="client-kpi-grid">
                <div class="client-kpi"><span>Activos</span><strong>${h(summary.active || 0)}</strong></div>
                <div class="client-kpi"><span>Stock bajo</span><strong>${h(summary.low_stock || 0)}</strong></div>
                <div class="client-kpi"><span>Inactivos</span><strong>${h(summary.inactive || 0)}</strong></div>
                <div class="client-kpi"><span>Total registros</span><strong>${h(summary.total || 0)}</strong></div>
              </div>

              <div class="cx-inv-modebar">
                <button class="${mode === "create" ? "active" : ""}" type="button" data-inventory-mode="create">Crear material / producto</button>
                <button class="${mode === "modify" ? "active" : ""}" type="button" data-inventory-mode="modify">Modificar material</button>
                <button type="button" data-inventory-export>CSV</button>
              </div>
            </section>

            ${mode === "create" ? renderInventoryCreatePanel() : renderInventoryModifyPanel(rows)}
          </section>
        </div>
      </main>
    `;
  }
  /* CX_INVENTORY_BASE_015B_END */


  /* CX_MATERIALS_INVENTORY_ORDERS_015C_START */
  function ensureMaterialsStyles() {
    if (document.getElementById("cxMaterialsOrdersStyles")) return;
    const style = document.createElement("style");
    style.id = "cxMaterialsOrdersStyles";
    style.textContent = `
      .cx-materials-table {
        display: grid;
        grid-template-columns: 150px minmax(150px, 1fr) minmax(220px, 1.4fr) 90px 120px minmax(150px, 1fr) minmax(250px, 1.5fr);
        gap: 0;
        border: 1px solid rgba(255,255,255,.10);
        border-radius: 22px;
        overflow: hidden;
        background: rgba(0,0,0,.12);
      }
      .cx-materials-cell {
        padding: 14px 14px;
        border-bottom: 1px solid rgba(255,255,255,.07);
        min-height: 54px;
      }
      .cx-materials-head {
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: .12em;
        font-weight: 1000;
        opacity: .72;
        background: rgba(255,255,255,.08);
      }
      .cx-materials-row-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }
      .cx-materials-action {
        border: 1px solid rgba(255,255,255,.14);
        background: rgba(255,255,255,.08);
        color: inherit;
        border-radius: 13px;
        padding: 9px 10px;
        font-weight: 900;
        cursor: pointer;
      }
      .cx-materials-action.primary {
        background: linear-gradient(135deg, var(--cx-primary, #ff2bbd), rgba(255,255,255,.12));
        border-color: rgba(255,255,255,.24);
      }
      .cx-materials-status {
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        padding: 8px 11px;
        font-weight: 1000;
        font-size: 12px;
        border: 1px solid rgba(255,255,255,.12);
        background: rgba(255,255,255,.08);
      }
      .cx-materials-status.pending { color: #ffe18a; background: rgba(255,210,70,.12); }
      .cx-materials-status.approved { color: #9ee7ff; background: rgba(70,190,255,.12); }
      .cx-materials-status.delivered { color: #39f28a; background: rgba(0,255,136,.12); }
      .cx-materials-status.returned,
      .cx-materials-status.returned_partial { color: #d7c2ff; background: rgba(180,140,255,.12); }
      .cx-materials-status.rejected { color: #ff8f8f; background: rgba(255,70,70,.12); }
      .cx-materials-sheet {
        margin-top: 20px;
        padding: 18px;
        border: 1px solid rgba(255,255,255,.13);
        border-radius: 22px;
        background: rgba(255,255,255,.06);
        box-shadow: 0 22px 60px rgba(0,0,0,.18);
      }
      .cx-materials-sheet-grid {
        display: grid;
        grid-template-columns: 80px minmax(260px,1fr) minmax(220px,1fr);
        border: 1px solid rgba(255,255,255,.12);
        border-radius: 16px;
        overflow: hidden;
        margin-top: 14px;
      }
      .cx-materials-sheet-grid > div {
        padding: 10px 12px;
        border-bottom: 1px solid rgba(255,255,255,.07);
        border-right: 1px solid rgba(255,255,255,.07);
      }
      .cx-materials-sheet-grid .head {
        background: rgba(255,255,255,.09);
        font-weight: 1000;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: .12em;
      }
      .cx-materials-input {
        width: 100%;
        border: 1px solid rgba(255,255,255,.14);
        background: rgba(0,0,0,.18);
        color: inherit;
        border-radius: 13px;
        padding: 11px 12px;
        font-weight: 900;
        outline: none;
      }
      .cx-materials-form-row {
        display: grid;
        grid-template-columns: minmax(220px, 1fr) minmax(260px, 1.4fr) auto;
        gap: 12px;
        align-items: end;
        margin-top: 14px;
      }

      .cx-materials-return-results,
      .cx-materials-return-checklist {
        margin-top: 14px;
        display: grid;
        gap: 10px;
      }
      .cx-materials-order-pick {
        width: 100%;
        text-align: left;
        border: 1px solid rgba(255,255,255,.14);
        background: rgba(255,255,255,.07);
        color: inherit;
        border-radius: 15px;
        padding: 12px 14px;
        cursor: pointer;
        font-weight: 900;
      }
      .cx-materials-order-pick:hover {
        border-color: rgba(255,255,255,.28);
        transform: translateY(-1px);
      }
      .cx-materials-return-summary {
        border: 1px solid rgba(255,255,255,.14);
        background: rgba(255,255,255,.06);
        border-radius: 18px;
        padding: 14px;
        display: grid;
        gap: 5px;
      }
      .cx-materials-return-line {
        border: 1px solid rgba(255,255,255,.12);
        background: rgba(0,0,0,.14);
        border-radius: 18px;
        overflow: hidden;
      }
      .cx-materials-return-line summary {
        cursor: pointer;
        padding: 14px;
        font-weight: 1000;
      }
      .cx-materials-return-units {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
        gap: 8px;
        padding: 0 14px 14px;
      }
      .cx-materials-return-unit {
        display: flex;
        gap: 8px;
        align-items: center;
        padding: 10px 11px;
        border: 1px solid rgba(255,255,255,.10);
        background: rgba(255,255,255,.06);
        border-radius: 13px;
        font-weight: 900;
      }
      .cx-materials-return-unit.disabled {
        opacity: .45;
      }

      @media (max-width: 1100px) {
        .cx-materials-table { grid-template-columns: 1fr; }
        .cx-materials-head { display:none; }
        .cx-materials-cell { border-bottom: 1px solid rgba(255,255,255,.08); }
        .cx-materials-form-row,
        .cx-materials-sheet-grid { grid-template-columns: 1fr; }
      }
    `;
    document.head.appendChild(style);
  }

  function materialsStatusLabel(status = "") {
    const map = {
      pending: "Pendiente",
      approved: "Aprobada",
      rejected: "Rechazada",
      delivered: "Entregada",
      consigned: "Consignada total",
      consigned_partial: "Consignada parcial",
      returned: "Devuelta total",
      returned_partial: "Devuelta parcial",
      cancelled: "Cancelada",
    };
    return map[String(status || "pending").toLowerCase()] || "Pendiente";
  }

  function materialDateLabel(raw) {
    if (!raw) return "-";
    const date = new Date(raw);
    return Number.isNaN(date.getTime()) ? "-" : date.toLocaleString([], { dateStyle: "short", timeStyle: "short" });
  }

  function materialAgeHours(raw) {
    if (!raw) return Infinity;
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return Infinity;
    return (Date.now() - date.getTime()) / 36e5;
  }

  function materialDeliveredAt(row = {}) {
    return row.delivered_at || row.status_updated_at || row.updated_at || row.created_at || null;
  }

  function materialValidOrder(row = {}) {
    const order = String(row.order_number || "").trim();
    return Boolean(order) && order.toLowerCase() !== "sin orden";
  }

  function materialCanReturn(row = {}) {
    const status = String(row.status || "").toLowerCase();
    return materialValidOrder(row)
      && ["delivered", "returned_partial", "consigned", "consigned_partial"].includes(status)
      && materialAgeHours(materialDeliveredAt(row)) <= 48;
  }

  function materialCanConsign(row = {}) {
    const status = String(row.status || "").toLowerCase();
    return materialValidOrder(row)
      && ["delivered", "returned_partial"].includes(status)
      && materialAgeHours(materialDeliveredAt(row)) <= 24;
  }

  function materialQuantity(row = {}) {
    const num = Number(row.quantity ?? 1);
    return Number.isFinite(num) ? num : 1;
  }

  function materialsRequestRow(row = {}) {
    const status = String(row.status || "pending").toLowerCase();
    const delivered = status === "delivered";
    const returned = status === "returned" || status === "returned_partial";
    const rejected = status === "rejected" || status === "cancelled";
    const canReturn = materialCanReturn(row);
    const canConsign = materialCanConsign(row);
    const age = materialAgeHours(materialDeliveredAt(row));
    const timeHint = Number.isFinite(age) && age !== Infinity ? `${Math.max(0, Math.round(age))}h` : "";

    return `
      <div class="cx-materials-cell">
        <strong>${h(row.order_number || "Sin orden")}</strong><br>
        <span class="client-muted">${h(materialDateLabel(row.requested_at || row.created_at))}</span>
      </div>
      <div class="cx-materials-cell">
        <strong>${h(row.employee_name || "Colaborador")}</strong><br>
        <span class="client-muted">${h(row.employee_role || "-")}</span>
      </div>
      <div class="cx-materials-cell">
        <strong>${h(row.name_reference || row.material_name || "Material")}</strong><br>
        <span class="client-muted">${h([row.item_size, row.color].filter(Boolean).join(" · ") || row.notes || "")}</span>
      </div>
      <div class="cx-materials-cell"><strong>${h(materialQuantity(row))}</strong></div>
      <div class="cx-materials-cell"><span class="cx-materials-status ${h(status)}">${h(materialsStatusLabel(status))}</span></div>
      <div class="cx-materials-cell">${h(row.destination || "-")}</div>
      <div class="cx-materials-cell">
        <div class="cx-materials-row-actions">
          ${status === "pending" ? `<button class="cx-materials-action primary" type="button" data-material-approve-open="${h(row.id)}">Aprobar</button>` : ""}
          ${status === "approved" ? `<button class="cx-materials-action primary" type="button" data-material-deliver="${h(row.id)}">Entregar</button>` : ""}
          ${!delivered && !returned && !rejected && !status.startsWith("consigned") ? `<button class="cx-materials-action" type="button" data-material-reject="${h(row.id)}">Rechazar</button>` : ""}
          ${materialValidOrder(row) ? `<button class="cx-materials-action" type="button" data-material-detail-load="${h(row.order_number || "")}">Detalle</button>` : ""}
          ${canConsign ? `<button class="cx-materials-action" type="button" data-material-consign-load="${h(row.order_number || "")}">Consigna</button>` : ""}
          ${canReturn ? `<button class="cx-materials-action" type="button" data-material-return-load="${h(row.order_number || "")}">Devolución</button>` : ""}
          ${(!canReturn && (delivered || status === "returned_partial" || status.startsWith("consigned")) && materialValidOrder(row)) ? `<span class="client-muted" title="Ventana de devolución: 48h. Consigna: 24h.">${h(timeHint ? "Vence / vencida · " + timeHint : "Sin acción")}</span>` : ""}
        </div>
      </div>
    `;
  }

  async function loadMaterialsRequests() {
    if (!state.companyId) return { summary: {}, requests: [] };
    return api(`/materials/companies/${encodeURIComponent(state.companyId)}/requests?limit=400`);
  }

  function showMaterialsNotice(message, type = "ok") {
    const box = document.getElementById("materialsNotice");
    if (!box) return;
    box.innerHTML = `<div class="personal-toast ${type === "error" ? "error" : "ok"}">${h(message)}</div>`;
    window.clearTimeout(window.__materialsNoticeTimer);
    window.__materialsNoticeTimer = window.setTimeout(() => {
      if (box) box.innerHTML = "";
    }, 3200);
  }

  function renderMaterialsApproveSheet(requestId) {
    const rows = Array.isArray(window.__cxMaterialsRows) ? window.__cxMaterialsRows : [];
    const row = rows.find((item) => String(item.id) === String(requestId));
    const box = document.getElementById("materialsSheetBox");
    if (!box || !row) return;

    const qty = Math.max(1, Math.min(500, Math.trunc(materialQuantity(row))));
    const ref = row.name_reference || row.material_name || "Material";

    box.innerHTML = `
      <section class="cx-materials-sheet" data-material-sheet="${h(row.id)}">
        <div class="client-eyebrow">Aprobación de orden</div>
        <h2>${h(row.order_number || "Orden")}</h2>
        <p class="client-muted">Registra un Label/SKU por cada unidad. El destino se define una sola vez para toda la orden.</p>

        <div class="cx-materials-form-row">
          <label>
            <span class="client-muted">Lugar de destino</span>
            <input class="cx-materials-input" data-material-destination value="${h(row.destination || "")}" placeholder="Ej: Obra norte / Técnico Gómez / Bodega cliente">
          </label>
          <label>
            <span class="client-muted">Observación de aprobación</span>
            <input class="cx-materials-input" data-material-approval-notes placeholder="Opcional">
          </label>
          <button class="cx-materials-action primary" type="button" data-material-approve-save="${h(row.id)}">Guardar aprobación</button>
        </div>

        <div class="cx-materials-sheet-grid">
          <div class="head">#</div>
          <div class="head">Nombre / referencia</div>
          <div class="head">Label / SKU salida</div>
          ${Array.from({ length: qty }, (_, index) => `
            <div>${index + 1}</div>
            <div><strong>${h(ref)}</strong></div>
            <div><input class="cx-materials-input" data-material-unit-label data-index="${index + 1}" placeholder="Label/SKU ${index + 1}"></div>
          `).join("")}
        </div>
      </section>
    `;
    box.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function approveMaterialRequest(requestId) {
    const sheet = document.querySelector(`[data-material-sheet="${CSS.escape(String(requestId))}"]`);
    if (!sheet) {
      renderMaterialsApproveSheet(requestId);
      return;
    }
    const destination = sheet.querySelector("[data-material-destination]")?.value || "";
    const notes = sheet.querySelector("[data-material-approval-notes]")?.value || "";
    const units = Array.from(sheet.querySelectorAll("[data-material-unit-label]")).map((input, index) => ({
      unit_index: index + 1,
      label_sku: input.value || "",
    }));

    await api(`/materials/requests/${encodeURIComponent(requestId)}/approve`, {
      method: "POST",
      body: JSON.stringify({ destination, notes, units }),
    });
    await renderMaterialsModule();
    setTimeout(() => showMaterialsNotice("Orden aprobada. Ya puedes entregarla."), 80);
  }

  async function deliverMaterialRequest(requestId) {
    await api(`/materials/requests/${encodeURIComponent(requestId)}/deliver`, { method: "POST" });
    await renderMaterialsModule();
    setTimeout(() => showMaterialsNotice("Orden entregada. Inventario descontado."), 80);
  }

  async function rejectMaterialRequest(requestId) {
    if (!confirm("¿Rechazar esta solicitud de material?")) return;
    await api(`/materials/requests/${encodeURIComponent(requestId)}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status: "rejected" }),
    });
    await renderMaterialsModule();
    setTimeout(() => showMaterialsNotice("Orden rechazada."), 80);
  }

  function renderMaterialReturnSearchResults(orders = []) {
    const box = document.querySelector("[data-material-return-results]");
    if (!box) return;
    if (!orders.length) {
      box.innerHTML = "";
      return;
    }
    box.innerHTML = orders.map((order) => `
      <button class="cx-materials-order-pick" type="button" data-material-return-order-pick="${h(order.order_number)}">
        <strong>${h(order.order_number)}</strong>
        <span class="client-muted"> · ${h(order.employee_name || "Colaborador")} · ${h(order.lines_count || 0)} materiales · pendientes ${h(order.quantity_pending_return || 0)}</span>
      </button>
    `).join("");
  }

  async function searchMaterialReturnOrders(query) {
    const q = String(query || "").trim();
    if (q.length < 4) {
      renderMaterialReturnSearchResults([]);
      return;
    }
    try {
      const mode = String(window.__cxMaterialsOperationMode || "return");
      const data = await api(`/materials/companies/${encodeURIComponent(state.companyId)}/orders/search?q=${encodeURIComponent(q)}&mode=${encodeURIComponent(mode)}&limit=8`);
      renderMaterialReturnSearchResults(Array.isArray(data.orders) ? data.orders : []);
    } catch (_) {
      renderMaterialReturnSearchResults([]);
    }
  }

  function renderMaterialReturnChecklist(data, mode = "return") {
    const box = document.querySelector("[data-material-return-checklist]");
    if (!box) return;

    mode = mode === "consign" ? "consign" : "return";
    window.__cxMaterialsOperationMode = mode;
    const saveBtn = document.querySelector("[data-material-return-save]");
    const observationInput = document.querySelector("[data-material-return-observation]");
    const titleEl = document.querySelector("[data-material-operation-title]");
    const helperEl = document.querySelector("[data-material-operation-helper]");
    if (saveBtn) saveBtn.textContent = mode === "consign" ? "Registrar consigna" : "Registrar devolución";
    if (observationInput) observationInput.placeholder = mode === "consign" ? "Motivo de consigna / responsable / próximo turno" : "Motivo / estado del material";
    if (titleEl) titleEl.textContent = mode === "consign" ? "Registrar consigna por número de orden" : "Registrar devolución por número de orden";
    if (helperEl) helperEl.textContent = mode === "consign"
      ? "Marca los Label/SKU que quedan en consigna. No suma inventario; queda bajo custodia temporal por 24h."
      : "Busca la orden de salida, despliega sus materiales y marca los Label/SKU que vuelven al inventario.";

    if (!data || data.found === false) {
      box.dataset.materialReturnSelectedOrder = "";
      window.__cxMaterialsReturnOrder = "";
      box.innerHTML = `<div class="personal-toast error">${h(data?.message || "Orden de salida no encontrada o fuera de ventana operativa.")}</div>`;
      return;
    }

    const selectedOrder = String(data.order_number || "").trim();
    box.dataset.materialReturnSelectedOrder = selectedOrder;
    box.dataset.materialOperationMode = mode;
    window.__cxMaterialsReturnOrder = selectedOrder;

    const lines = Array.isArray(data.lines) ? data.lines : [];
    box.innerHTML = `
      <div class="cx-materials-return-summary">
        <strong>Orden ${h(data.order_number || "")}</strong>
        <span class="client-muted">Solicitante: ${h(data.employee_name || "-")} · Destino: ${h(data.destination || "-")} · Modo: ${h(mode === "consign" ? "Consigna" : "Devolución")}</span>
      </div>
      ${lines.map((line) => {
        const title = [line.name_reference || line.material_name || "Material", line.item_size].filter(Boolean).join(" · ");
        const units = Array.isArray(line.units) ? line.units : [];
        return `
          <details class="cx-materials-return-line" open>
            <summary>${h(title)} <span class="client-muted">pendiente ${h(line.quantity_pending_return || 0)} de ${h(line.quantity || 0)}</span></summary>
            ${line.notes || line.operation_notes ? `<div class="client-muted" style="padding:0 14px 10px">${h([line.notes, line.operation_notes].filter(Boolean).join(" · "))}</div>` : ""}
            <div class="cx-materials-return-units">
              ${units.length ? units.map((unit) => `
                <label class="cx-materials-return-unit ${unit.available ? "" : "disabled"}">
                  <input type="checkbox" data-material-return-unit="${h(unit.unit_id)}" data-material-return-unit-order="${h(selectedOrder)}" ${unit.available ? "" : "disabled"}>
                  <span>${h(unit.label_sku || ("Unidad " + (unit.unit_index || "")))}</span>
                  <small class="client-muted">${h(unit.available ? (mode === "consign" ? "Disponible para consigna" : "Disponible") : materialsStatusLabel(unit.status))}</small>
                </label>
              `).join("") : `<div class="client-muted">No hay unidades disponibles para esta operación.</div>`}
            </div>
          </details>
        `;
      }).join("")}
    `;
  }

  async function loadMaterialReturnChecklist(orderNumber, mode = "return") {
    const order = String(orderNumber || "").trim();
    mode = mode === "consign" ? "consign" : "return";
    const box = document.querySelector("[data-material-return-checklist]");
    if (!order) {
      window.__cxMaterialsReturnOrder = "";
      if (box) {
        box.dataset.materialReturnSelectedOrder = "";
        box.dataset.materialOperationMode = mode;
        box.innerHTML = "";
      }
      return;
    }
    const data = await api(`/materials/companies/${encodeURIComponent(state.companyId)}/orders/${encodeURIComponent(order)}/return-checklist?mode=${encodeURIComponent(mode)}`);
    renderMaterialReturnChecklist(data, mode);
  }

  async function returnMaterialOrder() {
    const selectedBox = document.querySelector("[data-material-return-checklist]");
    const mode = String(selectedBox?.dataset?.materialOperationMode || window.__cxMaterialsOperationMode || "return") === "consign" ? "consign" : "return";
    const orderFromChecklist = String(selectedBox?.dataset?.materialReturnSelectedOrder || window.__cxMaterialsReturnOrder || "").trim();
    const orderFromInput = String(document.querySelector("[data-material-return-order]")?.value || "").trim();
    const observation = String(document.querySelector("[data-material-return-observation]")?.value || "").trim();
    const checkedUnits = Array.from(document.querySelectorAll("[data-material-return-unit]:checked"));
    const orderFromUnit = String(checkedUnits[0]?.getAttribute("data-material-return-unit-order") || "").trim();
    const orderNumber = orderFromChecklist || orderFromUnit || orderFromInput;
    const unitIds = checkedUnits
      .map((input) => input.getAttribute("data-material-return-unit"))
      .filter(Boolean);

    if (!orderNumber) {
      showMaterialsNotice("Selecciona una orden de salida.", "error");
      return;
    }
    if (!observation) {
      showMaterialsNotice(mode === "consign" ? "Escribe una observación de consigna." : "Escribe una observación de devolución.", "error");
      return;
    }
    if (!unitIds.length) {
      showMaterialsNotice(mode === "consign" ? "Marca al menos un Label/SKU para consignar." : "Marca al menos un Label/SKU para devolver.", "error");
      return;
    }

    const endpoint = mode === "consign"
      ? `/materials/companies/${encodeURIComponent(state.companyId)}/orders/${encodeURIComponent(orderNumber)}/consign-selected`
      : `/materials/companies/${encodeURIComponent(state.companyId)}/orders/${encodeURIComponent(orderNumber)}/return-selected`;

    await api(endpoint, {
      method: "POST",
      body: JSON.stringify({ order_number: orderNumber, observation, unit_ids: unitIds }),
    });
    await renderMaterialsModule();
    setTimeout(() => showMaterialsNotice(mode === "consign" ? "Consigna registrada. Inventario no se movió." : "Devolución registrada. Inventario actualizado."), 80);
  }

  async function fillReturnOrder(orderNumber, mode = "return") {
    const safeOrder = String(orderNumber || "").trim();
    mode = mode === "consign" ? "consign" : "return";
    window.__cxMaterialsReturnOrder = safeOrder;
    window.__cxMaterialsOperationMode = mode;
    const checklist = document.querySelector("[data-material-return-checklist]");
    if (checklist) {
      checklist.dataset.materialReturnSelectedOrder = safeOrder;
      checklist.dataset.materialOperationMode = mode;
    }
    const input = document.querySelector("[data-material-return-order]");
    if (input) {
      input.value = safeOrder;
      input.focus();
    }
    renderMaterialReturnSearchResults([]);
    try {
      await loadMaterialReturnChecklist(safeOrder, mode);
    } catch (error) {
      showMaterialsNotice(error.message || "No se pudo cargar la orden.", "error");
    }
  }

  async function loadMaterialOrderDetail(orderNumber) {
    const safeOrder = String(orderNumber || "").trim();
    if (!safeOrder) return;
    try {
      const data = await api(`/materials/companies/${encodeURIComponent(state.companyId)}/orders/${encodeURIComponent(safeOrder)}/detail`);
      const box = document.getElementById("materialsSheetBox");
      if (!box) return;
      if (!data || data.found === false) {
        box.innerHTML = `<div class="personal-toast error">No se encontró detalle de la orden.</div>`;
        return;
      }
      const lines = Array.isArray(data.lines) ? data.lines : [];
      const events = Array.isArray(data.events) ? data.events : [];
      box.innerHTML = `
        <section class="cx-materials-sheet">
          <div class="client-eyebrow">Detalle / observaciones</div>
          <h2>${h(data.order_number || safeOrder)}</h2>
          <p class="client-muted">Solicitante: ${h(data.employee_name || "-")} · Destino: ${h(data.destination || "-")}</p>
          <div class="cx-materials-table" style="margin-top:16px">
            <div class="cx-materials-cell cx-materials-head">Material</div>
            <div class="cx-materials-cell cx-materials-head">Cantidad</div>
            <div class="cx-materials-cell cx-materials-head">Estado</div>
            <div class="cx-materials-cell cx-materials-head">Observaciones</div>
            ${lines.map((line) => `
              <div class="cx-materials-cell"><strong>${h(line.name_reference || line.material_name || "Material")}</strong><br><span class="client-muted">${h([line.item_size, line.color].filter(Boolean).join(" · "))}</span></div>
              <div class="cx-materials-cell"><strong>${h(line.quantity || 0)}</strong></div>
              <div class="cx-materials-cell"><span class="cx-materials-status ${h(line.status || "")}">${h(materialsStatusLabel(line.status))}</span></div>
              <div class="cx-materials-cell">${h([line.notes, line.operation_notes].filter(Boolean).join("\n") || "-")}</div>
            `).join("")}
          </div>
          <div style="margin-top:18px;display:grid;gap:10px">
            <strong>Eventos / observaciones</strong>
            ${events.length ? events.map((event) => `<div class="cx-materials-return-summary"><strong>${h(event.label || event.type || "Evento")}</strong><span class="client-muted">${h(event.at || "")}</span><div>${h(event.detail || "")}</div></div>`).join("") : `<div class="client-muted">Sin observaciones registradas.</div>`}
          </div>
        </section>
      `;
      box.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      showMaterialsNotice(error.message || "No se pudo cargar detalle.", "error");
    }
  }

  function downloadMaterialsCsv(rows) {
    const headers = ["Orden", "Empleado", "Rol", "Material", "Cantidad", "Estado", "Destino", "Fecha", "Entregado", "Devuelto", "Consignado", "Notas", "Observaciones"];
    const csvRows = [headers].concat(rows.map((row) => [
      row.order_number || "",
      row.employee_name || "",
      row.employee_role || "",
      row.name_reference || row.material_name || "",
      row.quantity || "",
      materialsStatusLabel(row.status),
      row.destination || "",
      row.requested_at || row.created_at || "",
      row.delivered_at || "",
      row.returned_at || "",
      row.consigned_at || "",
      row.notes || "",
      row.operation_notes || "",
    ]));

    const csv = csvRows
      .map((items) => items.map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`).join(","))
      .join("\n");

    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `clonexa_materiales_ordenes_${state.companyId || "empresa"}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  async function exportMaterialsCsv() {
    const rows = Array.isArray(window.__cxMaterialsRows) ? window.__cxMaterialsRows : [];
    downloadMaterialsCsv(rows);

    const shouldPurge = confirm("CSV generado. ¿Deseas depurar órdenes cerradas/no gestionables del panel?\n\nSí: oculta del panel lo ya devuelto/cerrado o vencido.\nNo: conserva la vista actual.");
    if (!shouldPurge) return;

    try {
      const result = await api(`/materials/companies/${encodeURIComponent(state.companyId)}/requests/archive-exported`, {
        method: "POST",
        body: JSON.stringify({ include_open: false }),
      });
      await renderMaterialsModule();
      setTimeout(() => showMaterialsNotice(`Depuración lista. Órdenes ocultas: ${result.archived_count || 0}.`), 80);
    } catch (error) {
      showMaterialsNotice(error.message || "No se pudo depurar después de exportar.", "error");
    }
  }

  async function renderMaterialsModule() {
    if (!isClientModuleActivo("materials")) {
      render();
      return;
    }

    ensureMaterialsStyles();

    const company = state.company || {};
    let data = { summary: {}, requests: [] };
    let loadError = "";

    try {
      data = await loadMaterialsRequests();
    } catch (error) {
      loadError = error.message || "No se pudo cargar Materiales.";
    }

    const rows = Array.isArray(data.requests) ? data.requests : [];
    const summary = data.summary || {};
    window.__cxMaterialsRows = rows;
    window.clearTimeout(window.__materialsDailyActualizarTimer);
    window.__materialsDailyActualizarTimer = window.setTimeout(() => {
      if (document.querySelector("[data-materials-refresh]")) renderMaterialsModule();
    }, 24 * 60 * 60 * 1000);

    $("app").innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, normalizeBranding(state.branding || {}))}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>
            <nav class="client-nav">${renderClientNav("materials")}</nav>
            <div class="client-footer-id"><strong>Tenant activo</strong><br>${h(state.companyId || "")}</div>
          </aside>

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">Módulo Materiales</div>
              <h1 class="client-title">Materiales</h1>
              <p class="client-muted">Órdenes de salida conectadas a Inventario. Entregar descuenta stock; devolver exige número de orden.</p>
              <div class="client-actions">
                <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
                <button class="client-btn" type="button" data-materials-refresh>Actualizar</button>
                <button class="client-btn" type="button" data-materials-export>CSV</button>
              </div>
              <div id="materialsNotice">${loadError ? `<div class="personal-toast error">${h(loadError)}</div>` : ""}</div>
            </header>

            <section class="client-panel">
              <div class="client-eyebrow">Ciclo operativo</div>
              <h2>Órdenes de materiales</h2>

              <div class="client-kpi-grid">
                <div class="client-kpi"><span>Pendientes</span><strong>${h(summary.pending || 0)}</strong></div>
                <div class="client-kpi"><span>Aprobadas</span><strong>${h(summary.approved || 0)}</strong></div>
                <div class="client-kpi"><span>Entregadas</span><strong>${h(summary.delivered || 0)}</strong></div>
                <div class="client-kpi"><span>Consigna</span><strong>${h((summary.consigned || 0) + (summary.consigned_partial || 0))}</strong></div>
                <div class="client-kpi"><span>Devueltas</span><strong>${h((summary.returned || 0) + (summary.returned_partial || 0))}</strong></div>
              </div>

              <div id="materialsSheetBox"></div>

              <div class="cx-materials-table" style="margin-top:22px">
                <div class="cx-materials-cell cx-materials-head">Orden</div>
                <div class="cx-materials-cell cx-materials-head">Solicitante</div>
                <div class="cx-materials-cell cx-materials-head">Material</div>
                <div class="cx-materials-cell cx-materials-head">Cantidad</div>
                <div class="cx-materials-cell cx-materials-head">Estado</div>
                <div class="cx-materials-cell cx-materials-head">Destino</div>
                <div class="cx-materials-cell cx-materials-head">Acciones</div>
                ${rows.length ? rows.map(materialsRequestRow).join("") : `<div class="cx-materials-cell" style="grid-column:1/-1">No hay órdenes de materiales.</div>`}
              </div>
            </section>

            <section class="client-panel">
              <div class="client-eyebrow">Gestión de salida</div>
              <h2 data-material-operation-title>Registrar devolución por número de orden</h2>
              <p class="client-muted" data-material-operation-helper>Busca la orden de salida, despliega sus materiales y marca los Label/SKU que vuelven al inventario.</p>
              <div class="cx-materials-form-row">
                <label>
                  <span class="client-muted">Número de orden</span>
                  <input class="cx-materials-input" data-material-return-order placeholder="Busca MAT-20260506-000003" autocomplete="off">
                </label>
                <label>
                  <span class="client-muted">Observación operativa</span>
                  <input class="cx-materials-input" data-material-return-observation placeholder="Motivo / estado del material">
                </label>
                <button class="cx-materials-action primary" type="button" data-material-return-save>Registrar devolución</button>
              </div>
              <div class="cx-materials-return-results" data-material-return-results></div>
              <div class="cx-materials-return-checklist" data-material-return-checklist></div>
            </section>
          </section>
        </div>
      </main>
    `;
  }
  /* CX_MATERIALS_INVENTORY_ORDERS_015C_END */



  /* CX_PAYROLL_CORE_013_R1_START */
  function ensurePayrollStyles() {
    if (document.getElementById("cxPayrollCoreStyles")) return;

    const style = document.createElement("style");
    style.id = "cxPayrollCoreStyles";
    style.textContent = `
      .cx-payroll-filters {
        display: grid;
        grid-template-columns: 170px 170px auto auto auto;
        gap: 12px;
        align-items: end;
        margin: 20px 0 18px;
      }

      .cx-payroll-field label {
        display: block;
        margin: 0 0 7px;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: .12em;
        opacity: .78;
        font-weight: 1000;
      }

      .cx-payroll-field input {
        width: 100%;
        border: 1px solid rgba(255,255,255,.16);
        background: rgba(255,255,255,.08);
        color: var(--cx-text, #fff);
        border-radius: 15px;
        padding: 13px 14px;
        font-weight: 900;
        outline: none;
      }

      .cx-payroll-status {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        border: 1px solid rgba(255,255,255,.14);
        background: rgba(255,255,255,.08);
        border-radius: 999px;
        padding: 9px 13px;
        font-size: 12px;
        font-weight: 1000;
        letter-spacing: .08em;
        text-transform: uppercase;
      }

      .cx-payroll-status.closed {
        border-color: rgba(0,255,136,.38);
        box-shadow: 0 0 22px rgba(0,255,136,.10);
      }

      .cx-payroll-history {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
        gap: 14px;
        margin: 18px 0 24px;
      }

      .cx-payroll-period-card {
        border: 1px solid rgba(255,255,255,.13);
        background: linear-gradient(135deg, rgba(255,255,255,.09), rgba(255,255,255,.04));
        border-radius: 22px;
        padding: 16px;
        box-shadow: 0 18px 48px rgba(0,0,0,.18);
        cursor: pointer;
        text-align: left;
        color: inherit;
      }

      .cx-payroll-period-card:hover {
        transform: translateY(-1px);
        border-color: rgba(255,255,255,.25);
      }

      .cx-payroll-period-card strong {
        display: block;
        margin-bottom: 6px;
        font-size: 14px;
      }

      .cx-payroll-period-card span {
        display: block;
        opacity: .74;
        font-size: 12px;
        font-weight: 800;
        margin-top: 3px;
      }

      .cx-payroll-table-wrap {
        width: 100%;
        max-width: 100%;
        overflow-x: auto;
        border: 1px solid rgba(255,255,255,.12);
        border-radius: 22px;
        background: rgba(0,0,0,.10);
        box-shadow: 0 18px 48px rgba(0,0,0,.20);
      }

      .cx-payroll-table {
        min-width: 1040px;
        width: 100%;
        border-collapse: collapse;
      }

      .cx-payroll-table th,
      .cx-payroll-table td {
        padding: 15px 14px;
        border-bottom: 1px solid rgba(255,255,255,.08);
        text-align: left;
        vertical-align: middle;
      }

      .cx-payroll-table th {
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: .10em;
        opacity: .76;
        background: rgba(255,255,255,.06);
      }

      .cx-payroll-table td {
        font-weight: 900;
      }

      .cx-payroll-employee {
        display: grid;
        gap: 4px;
      }

      .cx-payroll-employee strong {
        font-size: 15px;
        letter-spacing: .04em;
      }

      .cx-payroll-employee span {
        font-size: 12px;
        opacity: .70;
      }

      .cx-payroll-money {
        white-space: nowrap;
      }

      .cx-payroll-empty {
        padding: 24px;
        border: 1px dashed rgba(255,255,255,.18);
        border-radius: 20px;
        background: rgba(255,255,255,.06);
        font-weight: 900;
      }

      @media (max-width: 1000px) {
        .cx-payroll-filters {
          grid-template-columns: 1fr;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function payrollNumber(value) {
    if (value === null || value === undefined || value === "") return 0;
    const normalized = String(value)
      .replace(/[^\d,.-]/g, "")
      .replace(",", ".");
    const num = Number(normalized);
    return Number.isFinite(num) ? num : 0;
  }

  function payrollMoney(value) {
    const num = payrollNumber(value);
    return num.toLocaleString("es-CO", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function payrollDateOnly(date = new Date()) {
    const d = new Date(date);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function payrollDefaultPeriod() {
    const now = new Date();
    const start = new Date(now.getFullYear(), now.getMonth(), 1);
    return {
      from: payrollDateOnly(start),
      to: payrollDateOnly(now),
    };
  }

  function payrollReadPeriod() {
    const fallback = window.__cxPayrollPeriod || payrollDefaultPeriod();
    return {
      from: document.querySelector("[data-payroll-from]")?.value || fallback.from,
      to: document.querySelector("[data-payroll-to]")?.value || fallback.to,
    };
  }

  function payrollEventDate(event = {}) {
    const raw = event.occurred_at || event.event_time || event.created_at || event.updated_at;
    if (!raw) return null;
    const date = new Date(raw);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function payrollEmployeeIdFromEvent(event = {}) {
    return event.employee_id || event.employeeId || event.employee?.id || null;
  }

  function payrollEventType(event = {}) {
    return String(event.event_type || event.type || event.action || "").toLowerCase();
  }

  function payrollIsCheckIn(type) {
    return ["check_in", "entrada", "start_shift", "shift_start"].includes(type);
  }

  function payrollIsBreakStart(type) {
    return ["break_start", "pausa", "pause", "on_break"].includes(type);
  }

  function payrollIsBreakEnd(type) {
    return ["break_end", "reanudar", "resume", "retomar"].includes(type);
  }

  function payrollIsCheckOut(type) {
    return ["check_out", "salida", "end_shift", "shift_end"].includes(type);
  }

  function payrollDuration(minutes) {
    const total = Math.max(0, Math.round(Number(minutes) || 0));
    const hNum = Math.floor(total / 60);
    const mNum = total % 60;
    return `${hNum}h ${String(mNum).padStart(2, "0")}m`;
  }

  function payrollParsePayload(event = {}) {
    const raw = event.payload_json || event.metadata_json || event.payload || event.metadata || null;
    if (!raw) return {};
    if (typeof raw === "object") return raw;
    try {
      return JSON.parse(raw);
    } catch (_error) {
      return {};
    }
  }

  function payrollProjectionFromPayload(event = {}) {
    const payload = payrollParsePayload(event);
    const projection = payload.payroll_projection || payload.payroll || payload;
    if (!projection || typeof projection !== "object") return null;

    const regularMinutes = payrollNumber(projection.regular_minutes ?? projection.regularMinutes);
    const extraMinutes = payrollNumber(projection.extra_minutes ?? projection.extraMinutes);
    const projectedPay = payrollNumber(projection.projected_pay ?? projection.projectedPay);
    const discountTotal = payrollNumber(projection.discount_total ?? projection.discountTotal);
    const estimatedTotal = payrollNumber(projection.estimated_total ?? projection.estimatedTotal);

    if (!regularMinutes && !extraMinutes && !projectedPay && !estimatedTotal) return null;

    return {
      regularMinutes,
      extraMinutes,
      projectedPay,
      discountTotal,
      estimatedTotal,
    };
  }

  function payrollBuildClosedShifts(events = []) {
    const sorted = (Array.isArray(events) ? events : [])
      .map((event) => ({ event, date: payrollEventDate(event) }))
      .filter((row) => row.date)
      .sort((a, b) => a.date.getTime() - b.date.getTime());

    const open = new Map();
    const shifts = [];

    sorted.forEach(({ event, date }) => {
      const employeeId = payrollEmployeeIdFromEvent(event);
      if (!employeeId) return;

      const type = payrollEventType(event);

      if (payrollIsCheckIn(type)) {
        open.set(employeeId, {
          employeeId,
          start: date,
          end: null,
          pausesMs: 0,
          pauseStart: null,
          checkOutEvent: null,
        });
        return;
      }

      const shift = open.get(employeeId);
      if (!shift) return;

      if (payrollIsBreakStart(type)) {
        if (!shift.pauseStart) shift.pauseStart = date;
        return;
      }

      if (payrollIsBreakEnd(type)) {
        if (shift.pauseStart) {
          shift.pausesMs += Math.max(0, date.getTime() - shift.pauseStart.getTime());
          shift.pauseStart = null;
        }
        return;
      }

      if (payrollIsCheckOut(type)) {
        const pauseUntilEnd = shift.pauseStart
          ? Math.max(0, date.getTime() - shift.pauseStart.getTime())
          : 0;

        shift.end = date;
        shift.pausesMs += pauseUntilEnd;
        shift.pauseStart = null;
        shift.checkOutEvent = event;
        shifts.push(shift);
        open.delete(employeeId);
      }
    });

    return shifts;
  }

  function payrollBuildRows(employees = [], events = [], period = payrollDefaultPeriod()) {
    const employeeMap = new Map(
      (Array.isArray(employees) ? employees : [])
        .map((employee) => [String(employee.id || employee.employee_id || ""), employee])
        .filter(([id]) => id)
    );

    const fromDate = new Date(`${period.from}T00:00:00`);
    const toDate = new Date(`${period.to}T23:59:59.999`);

    const rowsByEmployee = new Map();

    payrollBuildClosedShifts(events)
      .filter((shift) => shift.end && shift.end >= fromDate && shift.end <= toDate)
      .forEach((shift) => {
        const employee = employeeMap.get(String(shift.employeeId)) || {};
        const projection = payrollProjectionFromPayload(shift.checkOutEvent);
        const payableMinutes = projection
          ? Math.max(0, projection.regularMinutes + projection.extraMinutes)
          : Math.max(0, Math.round((shift.end.getTime() - shift.start.getTime() - shift.pausesMs) / 60000));

        const regularMinutes = projection
          ? Math.max(0, Math.round(projection.regularMinutes))
          : Math.min(payableMinutes, 480);

        const extraMinutes = projection
          ? Math.max(0, Math.round(projection.extraMinutes))
          : Math.max(0, payableMinutes - 480);

        const rowId = String(shift.employeeId);
        const existing = rowsByEmployee.get(rowId) || {
          employeeId: rowId,
          name: employee.full_name || shift.checkOutEvent?.employee_name || "Colaborador",
          role: employee.role || shift.checkOutEvent?.employee_role || "",
          shifts: 0,
          regularMinutes: 0,
          extraMinutes: 0,
          regularRate: payrollNumber(employee.hourly_rate_regular),
          extraRate: payrollNumber(employee.hourly_rate_extra),
          deduction1: payrollNumber(employee.deduction_1),
          deduction2: payrollNumber(employee.deduction_2),
          gross: 0,
          discount: 0,
          net: 0,
        };

        const regularValue = projection && projection.projectedPay
          ? 0
          : (regularMinutes / 60) * existing.regularRate;

        const extraValue = projection && projection.projectedPay
          ? 0
          : (extraMinutes / 60) * existing.extraRate;

        existing.shifts += 1;
        existing.regularMinutes += regularMinutes;
        existing.extraMinutes += extraMinutes;
        existing.gross += projection && projection.projectedPay
          ? projection.projectedPay
          : regularValue + extraValue;

        rowsByEmployee.set(rowId, existing);
      });

    const rows = Array.from(rowsByEmployee.values()).map((row) => {
      row.discount = row.shifts > 0 ? row.deduction1 + row.deduction2 : 0;
      row.net = Math.max(0, row.gross - row.discount);
      return row;
    });

    rows.sort((a, b) => String(a.name).localeCompare(String(b.name)));
    return rows;
  }

  function payrollTotals(rows = []) {
    return (Array.isArray(rows) ? rows : []).reduce(
      (acc, row) => {
        acc.people += 1;
        acc.shifts += Number(row.shifts || row.closed_shifts || 0);
        acc.regularMinutes += Number(row.regularMinutes ?? row.regular_minutes ?? 0);
        acc.extraMinutes += Number(row.extraMinutes ?? row.extra_minutes ?? 0);
        acc.gross += payrollNumber(row.gross ?? row.gross_amount ?? 0);
        acc.discount += payrollNumber(row.discount ?? row.discount_amount ?? 0);
        acc.net += payrollNumber(row.net ?? row.net_amount ?? 0);
        return acc;
      },
      { people: 0, shifts: 0, regularMinutes: 0, extraMinutes: 0, gross: 0, discount: 0, net: 0 }
    );
  }

  async function payrollLoadSourceData() {
    const [employees, events] = await Promise.all([
      api(`/employees?company_id=${encodeURIComponent(state.companyId)}&include_archived=true`),
      api(`/employees/attendance/history?company_id=${encodeURIComponent(state.companyId)}&limit=1000`),
    ]);

    return {
      employees: Array.isArray(employees) ? employees : [],
      events: Array.isArray(events) ? events : [],
    };
  }

  function payrollNormalizeRows(rows = []) {
    return (Array.isArray(rows) ? rows : []).map((row) => ({
      employeeId: String(row.employee_id || row.employeeId || row.employeeId || ""),
      name: row.employee_name || row.name || "Colaborador",
      role: row.employee_role || row.role || "",
      shifts: Number(row.closed_shifts ?? row.shifts ?? 0),
      regularMinutes: Number(row.regular_minutes ?? row.regularMinutes ?? 0),
      extraMinutes: Number(row.extra_minutes ?? row.extraMinutes ?? 0),
      regularRate: payrollNumber(row.hourly_rate_regular ?? row.regularRate),
      extraRate: payrollNumber(row.hourly_rate_extra ?? row.extraRate),
      deduction1: payrollNumber(row.deduction_1 ?? row.deduction1),
      deduction2: payrollNumber(row.deduction_2 ?? row.deduction2),
      gross: payrollNumber(row.gross_amount ?? row.gross),
      discount: payrollNumber(row.discount_amount ?? row.discount),
      net: payrollNumber(row.net_amount ?? row.net),
    }));
  }

  function payrollNormalizeTotals(totals = {}, rows = []) {
    if (!totals || typeof totals !== "object") return payrollTotals(rows);
    return {
      people: Number(totals.people ?? totals.collaborators ?? 0),
      shifts: Number(totals.shifts ?? totals.closed_shifts ?? 0),
      regularMinutes: Number(totals.regular_minutes ?? totals.regularMinutes ?? 0),
      extraMinutes: Number(totals.extra_minutes ?? totals.extraMinutes ?? 0),
      gross: payrollNumber(totals.gross_amount ?? totals.gross ?? 0),
      discount: payrollNumber(totals.discount_amount ?? totals.discount ?? 0),
      net: payrollNumber(totals.net_amount ?? totals.net ?? 0),
    };
  }

  async function payrollCalculatePeriod(period = payrollDefaultPeriod()) {
    try {
      const payload = await api(`/payroll/companies/${encodeURIComponent(state.companyId)}/periods/calculate`, {
        method: "POST",
        body: JSON.stringify({
          period_start: period.from,
          period_end: period.to,
        }),
      });
      const rows = payrollNormalizeRows(payload.rows || payload.items || []);
      return {
        rows,
        totals: payrollNormalizeTotals(payload.totals || {}, rows),
        period: {
          from: payload.period?.period_start || payload.period_start || period.from,
          to: payload.period?.period_end || payload.period_end || period.to,
        },
        source: "api",
      };
    } catch (error) {
      const source = await payrollLoadSourceData();
      const rows = payrollBuildRows(source.employees, source.events, period);
      return {
        rows,
        totals: payrollTotals(rows),
        period,
        source: "fallback",
        warning: error.message || "No se pudo usar el endpoint de nómina.",
      };
    }
  }

  async function payrollListPeriods() {
    try {
      const rows = await api(`/payroll/companies/${encodeURIComponent(state.companyId)}/periods`);
      return Array.isArray(rows) ? rows : [];
    } catch (_error) {
      return [];
    }
  }

  async function payrollGetPeriod(periodId) {
    return api(`/payroll/companies/${encodeURIComponent(state.companyId)}/periods/${encodeURIComponent(periodId)}`);
  }

  function payrollCards(totals = {}) {
    return `
      <div class="client-kpi-grid">
        <div class="client-kpi">
          <span>Colaboradores con cierre</span>
          <strong>${h(totals.people || 0)}</strong>
        </div>
        <div class="client-kpi">
          <span>Horas ordinarias</span>
          <strong>${h(payrollDuration(totals.regularMinutes || 0))}</strong>
        </div>
        <div class="client-kpi">
          <span>Horas extra</span>
          <strong>${h(payrollDuration(totals.extraMinutes || 0))}</strong>
        </div>
        <div class="client-kpi">
          <span>Total neto estimado</span>
          <strong>${h(payrollMoney(totals.net || 0))}</strong>
        </div>
      </div>
    `;
  }

  function payrollExportOnlyNotice(period = payrollDefaultPeriod()) {
    return `
      <div class="cx-payroll-empty">
        Corte calculado del ${h(period.from)} al ${h(period.to)}. Para conservar este corte, usa <strong>Exportar CSV</strong>.
        El archivo queda como histórico externo del periodo sin bloquear la operación.
      </div>
    `;
  }

  function payrollRowsTable(rows = []) {
    if (!rows.length) {
      return `<div class="cx-payroll-empty">No hay turnos cerrados para el periodo seleccionado.</div>`;
    }

    return `
      <div class="cx-payroll-table-wrap">
        <table class="cx-payroll-table">
          <thead>
            <tr>
              <th>Colaborador</th>
              <th>Turnos cerrados</th>
              <th>Ordinarias</th>
              <th>Extras</th>
              <th>Bruto</th>
              <th>Descuento corte</th>
              <th>Total estimado</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map((row) => `
              <tr>
                <td>
                  <div class="cx-payroll-employee">
                    <strong>${h(row.name)}</strong>
                    <span>${h(row.role || "Sin rol")}</span>
                  </div>
                </td>
                <td>${h(row.shifts)}</td>
                <td>${h(payrollDuration(row.regularMinutes))}</td>
                <td>${h(payrollDuration(row.extraMinutes))}</td>
                <td class="cx-payroll-money">${h(payrollMoney(row.gross))}</td>
                <td class="cx-payroll-money">${h(payrollMoney(row.discount))}</td>
                <td class="cx-payroll-money">${h(payrollMoney(row.net))}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function exportPayrollCsv() {
    const rows = Array.isArray(window.__cxPayrollRows) ? window.__cxPayrollRows : [];
    const totals = window.__cxPayrollTotals || payrollTotals(rows);
    const period = window.__cxPayrollPeriod || payrollDefaultPeriod();
    const mode = window.__cxPayrollMode || "abierto";
    const data = [
      ["Empresa", state.company?.name || ""],
      ["Periodo", `${period.from} / ${period.to}`],
      ["Modo", mode],
      [],
      ["Colaborador", "Rol", "Turnos cerrados", "Ordinarias", "Extras", "Bruto", "Descuento corte", "Total estimado"],
      ...rows.map((row) => [
        row.name,
        row.role || "",
        row.shifts,
        payrollDuration(row.regularMinutes),
        payrollDuration(row.extraMinutes),
        payrollMoney(row.gross),
        payrollMoney(row.discount),
        payrollMoney(row.net),
      ]),
      [],
      ["TOTAL", "", totals.shifts, payrollDuration(totals.regularMinutes), payrollDuration(totals.extraMinutes), payrollMoney(totals.gross), payrollMoney(totals.discount), payrollMoney(totals.net)],
    ];

    const csv = data.map((line) => line.map((value) => `"${String(value ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = `clonexa_nómina_${period.from}_${period.to}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();

    URL.revokeObjectURL(url);
  }

  async function renderPayrollModule(period = payrollDefaultPeriod(), options = {}) {
    if (!isClientModuleActivo("payroll")) {
      render();
      return;
    }

    ensurePayrollStyles();

    const company = state.company || {};
    let rows = [];
    let totals = payrollTotals([]);
    let loadError = "";
    let loadWarning = "";
    let mode = "Periodo abierto";

    try {
      const calculated = await payrollCalculatePeriod(period);
      rows = calculated.rows;
      totals = calculated.totals;
      period = calculated.period || period;
      loadWarning = calculated.warning || "";
    } catch (error) {
      rows = [];
      totals = payrollTotals([]);
      loadError = error.message || "No se pudo cargar nómina.";
    }

    window.__cxPayrollRows = rows;
    window.__cxPayrollTotals = totals;
    window.__cxPayrollPeriod = period;
    window.__cxPayrollMode = mode;

    $("app").innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, normalizeBranding(state.branding || {}))}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>

            <nav class="client-nav">
              ${renderClientNav("payroll")}
            </nav>

            <div class="client-footer-id">
              <strong>Tenant activo</strong><br>
              ${h(state.companyId || "")}
            </div>
          </aside>

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">Módulo Nómina</div>
              <h1 class="client-title">Nómina</h1>
              <p class="client-muted">Consulta cortes por periodo y conserva el resultado exportando CSV.</p>

              <div class="client-actions">
                <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
                <button class="client-btn" type="button" data-payroll-refresh>Actualizar</button>
                <button class="client-btn" type="button" data-payroll-export>CSV</button>
              </div>

              ${loadError ? `<div class="personal-toast error">${h(loadError)}</div>` : ""}
              ${loadWarning ? `<div class="personal-toast">${h(loadWarning)}</div>` : ""}
            </header>

            <section class="client-panel">
              <div class="client-eyebrow">Periodo</div>
              <h2>Resumen de nómina</h2>
              <p class="client-muted">Nómina consume Workforce, Bot y Asistencia. Al finalizar un corte, exporta CSV para guardar el histórico externo del periodo.</p>

              <div class="cx-payroll-status">
                ${h(mode)}
              </div>

              <div class="cx-payroll-filters">
                <div class="cx-payroll-field">
                  <label>Desde</label>
                  <input type="date" data-payroll-from value="${h(period.from)}">
                </div>
                <div class="cx-payroll-field">
                  <label>Hasta</label>
                  <input type="date" data-payroll-to value="${h(period.to)}">
                </div>
                <button class="client-btn" type="button" data-payroll-apply>Calcular periodo</button>
                <button class="client-btn" type="button" data-payroll-export>Exportar CSV</button>
              </div>

              ${payrollCards(totals)}

              <div class="client-eyebrow" style="margin-top:28px">Detalle por colaborador</div>
              <h2>Periodo calculado</h2>
              ${payrollRowsTable(rows)}

              <div class="client-eyebrow" style="margin-top:32px">Cierre del corte</div>
              <h2>Exportación</h2>
              ${payrollExportOnlyNotice(period)}
            </section>
          </section>
        </div>
      </main>
    `;
  }
  /* CX_PAYROLL_CORE_013_R1_END */


  /* CX_KPIS_OPERATIVOS_016A_START */
  function ensureKpisStyles() {
    if (document.getElementById("cxKpis016AStyles")) return;
    const style = document.createElement("style");
    style.id = "cxKpis016AStyles";
    style.textContent = `
      .cx-kpis-toolbar {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        align-items: end;
        justify-content: space-between;
        margin-top: 18px;
      }
      .cx-kpis-filters {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        align-items: end;
      }
      .cx-kpis-field {
        display: grid;
        gap: 6px;
      }
      .cx-kpis-field span {
        font-size: 11px;
        letter-spacing: .11em;
        text-transform: uppercase;
        opacity: .72;
        font-weight: 1000;
      }
      .cx-kpis-field input,
      .cx-kpis-field select {
        border: 1px solid rgba(255,255,255,.16);
        background: rgba(255,255,255,.08);
        color: var(--cx-text, #fff);
        border-radius: 14px;
        padding: 12px 13px;
        min-height: 44px;
        outline: none;
        font-weight: 900;
      }
      .cx-kpis-section-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(180px, 1fr));
        gap: 14px;
        margin-top: 18px;
      }
      .cx-kpis-card {
        border: 1px solid rgba(255,255,255,.14);
        background: rgba(255,255,255,.065);
        border-radius: 22px;
        padding: 18px;
        box-shadow: 0 18px 44px rgba(0,0,0,.20);
      }
      .cx-kpis-card span {
        display: block;
        color: rgba(255,255,255,.68);
        font-size: 12px;
        letter-spacing: .08em;
        text-transform: uppercase;
        font-weight: 1000;
      }
      .cx-kpis-card strong {
        display: block;
        margin-top: 8px;
        font-size: clamp(28px, 4vw, 48px);
        line-height: .95;
      }
      .cx-kpis-card small {
        color: rgba(255,255,255,.62);
        font-weight: 800;
      }
      .cx-kpis-blocks {
        display: grid;
        grid-template-columns: repeat(2, minmax(260px, 1fr));
        gap: 18px;
        margin-top: 22px;
      }
      .cx-kpis-block {
        border: 1px solid rgba(255,255,255,.14);
        background: rgba(255,255,255,.055);
        border-radius: 24px;
        padding: 20px;
      }
      .cx-kpis-list {
        display: grid;
        gap: 10px;
        margin-top: 12px;
      }
      .cx-kpis-row {
        display: flex;
        justify-content: space-between;
        gap: 14px;
        align-items: center;
        padding: 12px 14px;
        border-radius: 16px;
        background: rgba(255,255,255,.06);
        border: 1px solid rgba(255,255,255,.09);
      }
      .cx-kpis-row strong {
        font-size: 18px;
      }
      .cx-kpis-alert {
        border-color: rgba(251,191,36,.35);
        background: rgba(251,191,36,.10);
      }
      .cx-kpis-alert.critical {
        border-color: rgba(248,113,113,.38);
        background: rgba(248,113,113,.11);
      }
      .cx-kpis-empty {
        padding: 18px;
        border-radius: 18px;
        border: 1px dashed rgba(255,255,255,.18);
        color: rgba(255,255,255,.68);
      }

      .cx-kpis-search {
        min-width: min(440px, 100%);
        flex: 1 1 280px;
      }
      .cx-kpis-search input {
        width: 100%;
        padding-left: 42px;
        background:
          linear-gradient(90deg, rgba(255,255,255,.08), rgba(255,255,255,.04)),
          rgba(255,255,255,.08);
      }
      .cx-kpis-search-wrap {
        position: relative;
      }
      .cx-kpis-search-wrap::before {
        content: "⌕";
        position: absolute;
        left: 14px;
        top: 50%;
        transform: translateY(-50%);
        opacity: .75;
        font-size: 20px;
        pointer-events: none;
      }
      .cx-kpis-pin {
        margin-top: 14px;
        border: 1px solid rgba(255,255,255,.14);
        background: rgba(255,255,255,.08);
        color: var(--cx-text, #fff);
        border-radius: 14px;
        padding: 9px 12px;
        cursor: pointer;
        font-weight: 900;
      }
      .cx-kpis-pin.is-on {
        border-color: rgba(34,197,94,.38);
        background: rgba(34,197,94,.13);
      }
      .cx-kpis-hidden {
        display: none !important;
      }
      .cx-kpis-live {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        color: rgba(255,255,255,.68);
        font-size: 12px;
        font-weight: 900;
        margin-top: 10px;
      }
      @media (max-width: 1100px) {
        .cx-kpis-section-grid,
        .cx-kpis-blocks {
          grid-template-columns: 1fr;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function kpisDefaultPeriod() {
    const now = new Date();
    const to = now.toISOString().slice(0, 10);
    const fromDate = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    return { preset: "7d", start_date: fromDate.toISOString().slice(0, 10), end_date: to, search: "" };
  }

  function kpisReadPeriod() {
    const fallback = window.__cxKpisPeriod || kpisDefaultPeriod();
    const preset = document.querySelector("[data-kpis-preset]")?.value || fallback.preset || "7d";
    const start_date = document.querySelector("[data-kpis-start]")?.value || fallback.start_date || "";
    const end_date = document.querySelector("[data-kpis-end]")?.value || fallback.end_date || "";
    const search = document.querySelector("[data-kpis-search]")?.value ?? fallback.search ?? window.__cxKpisSearch ?? "";
    window.__cxKpisSearch = search;
    return { preset, start_date, end_date, search };
  }

  function kpisQuery(period = kpisDefaultPeriod()) {
    const params = new URLSearchParams();
    params.set("preset", period.preset || "7d");
    if (period.start_date) params.set("start_date", period.start_date);
    if (period.end_date) params.set("end_date", period.end_date);
    return params.toString();
  }

  async function fetchKpisSummary(period = kpisDefaultPeriod()) {
    if (!state.companyId) throw new Error("Empresa no cargada.");
    return api(`/kpis/companies/${encodeURIComponent(state.companyId)}/summary?${kpisQuery(period)}`);
  }

  async function saveKpisDashboardCards(keys = []) {
    if (!state.companyId) throw new Error("Empresa no cargada.");
    return api(`/kpis/companies/${encodeURIComponent(state.companyId)}/dashboard-cards`, {
      method: "POST",
      body: JSON.stringify({ cards: keys.map((key) => ({ key, enabled: true })) }),
    });
  }

  function kpiNumber(value, decimals = 0) {
    const n = Number(value || 0);
    if (!Number.isFinite(n)) return decimals ? "0.00" : "0";
    return decimals ? n.toFixed(decimals) : String(Math.round(n));
  }

  function kpiMoney(value) {
    const n = Number(value || 0);
    if (!Number.isFinite(n)) return "$0";
    return `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  }

  function kpiNormalizeText(value) {
    return String(value || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9ñ\s._-]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function kpiSearchText(...parts) {
    return kpiNormalizeText(parts.filter(Boolean).join(" "));
  }

  function applyKpisSearchFilter() {
    const input = document.querySelector("[data-kpis-search]");
    const query = kpiNormalizeText(input?.value || "");
    window.__cxKpisSearch = input?.value || "";
    document.querySelectorAll("[data-kpi-searchable]").forEach((el) => {
      const haystack = kpiNormalizeText(el.getAttribute("data-kpi-searchable") || "");
      const visible = !query || haystack.includes(query);
      el.classList.toggle("cx-kpis-hidden", !visible);
    });
  }

  function kpiCard(label, value, hint = "", key = "", showOnDashboard = false) {
    const searchable = kpiSearchText(label, value, hint, key, moduleLabel(hint), "indicador kpi");
    return `
      <div class="cx-kpis-card" data-kpi-searchable="${h(searchable)}">
        <span>${h(label)}</span>
        <strong>${h(value)}</strong>
        ${hint ? `<small>${h(hint)}</small>` : ""}
        ${key ? `
          <button class="cx-kpis-pin ${showOnDashboard ? "is-on" : ""}" type="button" data-kpi-dashboard-toggle="${h(key)}">
            ${showOnDashboard ? "Visible en panel" : "Mostrar en panel"}
          </button>
        ` : ""}
      </div>
    `;
  }

  function kpiCardValue(card) {
    const format = String(card.format || "").toLowerCase();
    if (format === "money") return kpiMoney(card.value);
    return kpiNumber(card.value, Number(card.value || 0) % 1 === 0 ? 0 : 2);
  }

  function kpiRow(label, value, extra = "") {
    const searchable = kpiSearchText(label, value, extra);
    return `
      <div class="cx-kpis-row" data-kpi-searchable="${h(searchable)}">
        <span>${h(label)}</span>
        <strong>${h(value)}</strong>
        ${extra ? `<small>${h(extra)}</small>` : ""}
      </div>
    `;
  }

  function kpiAlertRow(alert) {
    const level = String(alert.level || "info").toLowerCase();
    return `
      <div class="cx-kpis-row cx-kpis-alert ${h(level)}" data-kpi-searchable="${h(kpiSearchText(alert.title || "Alerta", alert.module || "", alert.value ?? "", "alerta riesgo"))}">
        <span>${h(alert.title || "Alerta")}</span>
        <strong>${h(alert.value ?? "")}</strong>
        <small>${h(moduleLabel(alert.module || ""))}</small>
      </div>
    `;
  }

  function renderKpisFilters(period = kpisDefaultPeriod()) {
    return `
      <div class="cx-kpis-toolbar">
        <div class="cx-kpis-filters">
          <label class="cx-kpis-field">
            <span>Periodo</span>
            <select data-kpis-preset>
              <option value="today" ${period.preset === "today" ? "selected" : ""}>Hoy</option>
              <option value="7d" ${period.preset === "7d" ? "selected" : ""}>7 días</option>
              <option value="15d" ${period.preset === "15d" ? "selected" : ""}>15 días</option>
              <option value="month" ${period.preset === "month" ? "selected" : ""}>Mes</option>
              <option value="custom" ${period.preset === "custom" ? "selected" : ""}>Personalizado</option>
            </select>
          </label>
          <label class="cx-kpis-field">
            <span>Desde</span>
            <input type="date" data-kpis-start value="${h(period.start_date || "")}">
          </label>
          <label class="cx-kpis-field">
            <span>Hasta</span>
            <input type="date" data-kpis-end value="${h(period.end_date || "")}">
          </label>
          <label class="cx-kpis-field cx-kpis-search">
            <span>Buscar KPI</span>
            <div class="cx-kpis-search-wrap">
              <input type="search" data-kpis-search placeholder="Buscar: nómina, horas, gps, stock, materiales, devueltas..." value="${h(period.search || window.__cxKpisSearch || "")}">
            </div>
          </label>
        </div>
        <div class="client-actions">
          <button class="client-btn" type="button" data-kpis-apply>Actualizar</button>
          <button class="client-btn" type="button" data-kpis-export>CSV</button>
          <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
        </div>
      </div>
    `;
  }

  function renderKpisBlocks(summary = {}) {
    const employees = summary.employees || {};
    const attendance = summary.attendance || {};
    const gps = summary.gps || {};
    const inventory = summary.inventory || {};
    const materials = summary.materials || {};
    const payroll = summary.payroll || {};
    const modules = new Set(Array.isArray(summary.modules) ? summary.modules : []);

    const blocks = [];

    blocks.push(`
      <section class="cx-kpis-block" data-kpi-searchable="personal workforce activos pausa eventos asistencia turnos">
        <div class="client-eyebrow">Personal / Workforce</div>
        <h2>Estado operativo</h2>
        <div class="cx-kpis-list">
          ${kpiRow("Personal activo", kpiNumber(employees.active))}
          ${kpiRow("Activos ahora", kpiNumber(attendance.active_now))}
          ${kpiRow("En pausa", kpiNumber(attendance.paused_now))}
          ${kpiRow("Eventos del periodo", kpiNumber(attendance.events))}
        </div>
      </section>
    `);

    if (modules.has("gps")) {
      blocks.push(`
        <section class="cx-kpis-block" data-kpi-searchable="gps ubicacion ubicaciones perimetro dentro fuera coordenadas">
          <div class="client-eyebrow">GPS</div>
          <h2>Ubicación y perímetros</h2>
          <div class="cx-kpis-list">
            ${kpiRow("Ubicaciones enviadas", kpiNumber(gps.locations))}
            ${kpiRow("Dentro de perímetro", kpiNumber(gps.inside))}
            ${kpiRow("Fuera de perímetro", kpiNumber(gps.outside))}
            ${kpiRow("Perímetros activos", kpiNumber(gps.perimeters))}
          </div>
        </section>
      `);
    }

    if (modules.has("materials")) {
      blocks.push(`
        <section class="cx-kpis-block" data-kpi-searchable="materiales solicitudes ordenes entregadas devueltas consignas pendientes">
          <div class="client-eyebrow">Materiales</div>
          <h2>Órdenes y movimientos</h2>
          <div class="cx-kpis-list">
            ${kpiRow("Solicitudes del periodo", kpiNumber(materials.total))}
            ${kpiRow("Entregadas", kpiNumber(materials.delivered))}
            ${kpiRow("Devueltas", kpiNumber((materials.returned || 0) + (materials.returned_partial || 0)))}
            ${kpiRow("En consigna", kpiNumber((materials.consigned || 0) + (materials.consigned_partial || 0)))}
          </div>
        </section>
      `);
    }

    if (modules.has("inventory") || modules.has("stock")) {
      blocks.push(`
        <section class="cx-kpis-block" data-kpi-searchable="inventario stock items bajo cero salidas unidades">
          <div class="client-eyebrow">Inventario</div>
          <h2>Disponibilidad</h2>
          <div class="cx-kpis-list">
            ${kpiRow("Items activos", kpiNumber(inventory.active))}
            ${kpiRow("Stock bajo", kpiNumber(inventory.low_stock))}
            ${kpiRow("Stock en cero", kpiNumber(inventory.zero_stock))}
            ${kpiRow("Unidades en stock", kpiNumber(inventory.total_stock_units))}
          </div>
        </section>
      `);
    }

    if (modules.has("payroll")) {
      blocks.push(`
        <section class="cx-kpis-block" data-kpi-searchable="nómina nómina payroll horas ordinarias extra descuentos bruto neto total estimado corte">
          <div class="client-eyebrow">Nómina</div>
          <h2>Estimado del periodo</h2>
          <div class="cx-kpis-list">
            ${kpiRow("Horas ordinarias", kpiNumber((payroll.regular_minutes || 0) / 60, 1))}
            ${kpiRow("Horas extra", kpiNumber((payroll.extra_minutes || 0) / 60, 1))}
            ${kpiRow("Turnos con corte", kpiNumber(payroll.closed_shifts || 0))}
            ${kpiRow("Bruto", kpiMoney(payroll.gross_amount))}
            ${kpiRow("Descuentos", kpiMoney(payroll.discount_amount))}
            ${kpiRow("Total estimado", kpiMoney(payroll.net_amount))}
            ${payroll.source ? kpiRow("Fuente", payroll.source) : ""}
          </div>
        </section>
      `);
    }

    const top = Array.isArray(materials.top_requested) ? materials.top_requested : [];
    blocks.push(`
      <section class="cx-kpis-block" data-kpi-searchable="top operativo materiales mas solicitados ranking">
        <div class="client-eyebrow">Top operativo</div>
        <h2>Materiales más solicitados</h2>
        <div class="cx-kpis-list">
          ${top.length ? top.map((item) => kpiRow(
            `${item.name_reference || "Material"}${item.item_size ? ` · ${item.item_size}` : ""}`,
            kpiNumber(item.quantity)
          )).join("") : `<div class="cx-kpis-empty">Sin solicitudes en el periodo.</div>`}
        </div>
      </section>
    `);

    return `<div class="cx-kpis-blocks">${blocks.join("")}</div>`;
  }

  function renderKpisAlerts(summary = {}) {
    const alerts = Array.isArray(summary.alerts) ? summary.alerts : [];
    return `
      <section class="cx-kpis-block" data-kpi-searchable="alertas riesgos operativos criticas stock gps pendientes">
        <div class="client-eyebrow">Alertas</div>
        <h2>Riesgos operativos</h2>
        <div class="cx-kpis-list">
          ${alerts.length ? alerts.map(kpiAlertRow).join("") : `<div class="cx-kpis-empty">Sin alertas críticas en el periodo.</div>`}
        </div>
      </section>
    `;
  }

  async function renderKpisModule(period = kpisDefaultPeriod()) {
    if (!isClientModuleActivo("kpis")) {
      render();
      return;
    }

    ensureKpisStyles();

    const company = state.company || {};
    window.__cxKpisPeriod = period;

    let summary = null;
    let loadError = "";

    try {
      summary = await fetchKpisSummary(period);
      window.__cxKpisSummary = summary;
    } catch (error) {
      loadError = error.message || "No se pudieron cargar KPIs.";
      summary = { cards: [], alerts: [], modules: [] };
      window.__cxKpisSummary = summary;
    }

    const cards = Array.isArray(summary.cards) ? summary.cards : [];
    const mainCards = cards;

    $("app").innerHTML = `
      <main class="client-shell" data-kpis-root>
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, normalizeBranding(state.branding || {}))}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>
            <nav class="client-nav">${renderClientNav("kpis")}</nav>
            <div class="client-footer-id"><strong>Tenant activo</strong><br>${h(state.companyId || "")}</div>
          </aside>

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">Módulo KPIs</div>
              <h1 class="client-title">KPIs Operativos</h1>
              <p class="client-muted">Indicadores ejecutivos calculados desde Workforce, GPS, Materiales, Inventario y Nómina según módulos activos.</p>
              ${renderKpisFilters(period)}
              <div class="cx-kpis-live">Actualización automática cada 60s · Fuente: datos reales por módulo</div>
              ${loadError ? `<div class="personal-toast error" style="margin-top:14px">${h(loadError)}</div>` : ""}
            </header>

            <section class="client-panel">
              <div style="display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:18px">
                <div>
                  <div class="client-eyebrow">Resumen ejecutivo</div>
                  <h2>Voltage / Operación viva</h2>
                </div>
                <span class="client-badge">${h((summary.modules || []).length)} módulos activos</span>
              </div>

              <div class="cx-kpis-section-grid">
                ${mainCards.map((card) => kpiCard(card.label, kpiCardValue(card), moduleLabel(card.module), card.key, !!card.show_on_dashboard)).join("")}
              </div>

              ${renderKpisBlocks(summary)}

              <div class="cx-kpis-blocks">
                ${renderKpisAlerts(summary)}
              </div>
            </section>
          </section>
        </div>
      </main>
    `;

    applyKpisSearchFilter();
    setupKpisAutoActualizar();
  }

  function setupKpisAutoActualizar() {
    if (window.__cxKpisAutoActualizar) {
      clearInterval(window.__cxKpisAutoActualizar);
      window.__cxKpisAutoActualizar = null;
    }
    window.__cxKpisAutoActualizar = setInterval(async () => {
      if (!document.querySelector("[data-kpis-root]")) {
        clearInterval(window.__cxKpisAutoActualizar);
        window.__cxKpisAutoActualizar = null;
        return;
      }
      try {
        await renderKpisModule(kpisReadPeriod());
      } catch (error) {
        console.warn("CLONEXA KPIs auto-refresh", error);
      }
    }, 60000);
  }

  if (!window.__cxKpisInputBound) {
    window.__cxKpisInputBound = true;
    document.addEventListener("input", (event) => {
      const target = event.target;
      if (target && target.matches && target.matches("[data-kpis-search]")) {
        applyKpisSearchFilter();
      }
    });
  }

  function exportKpisCsv() {
    const summary = window.__cxKpisSummary || {};
    const rows = [["Grupo", "Indicador", "Valor"]];

    (summary.cards || []).forEach((card) => {
      rows.push(["Resumen", card.label || "", card.value ?? 0]);
    });

    const sections = [
      ["Personal", summary.employees || {}],
      ["Asistencia", summary.attendance || {}],
      ["GPS", summary.gps || {}],
      ["Inventario", summary.inventory || {}],
      ["Materiales", summary.materials || {}],
      ["Nómina", summary.payroll || {}],
    ];

    sections.forEach(([group, data]) => {
      Object.entries(data || {}).forEach(([key, value]) => {
        if (Array.isArray(value) || (value && typeof value === "object")) return;
        rows.push([group, key, value]);
      });
    });

    (summary.alerts || []).forEach((alert) => {
      rows.push(["Alerta", `${alert.module || ""} - ${alert.title || ""}`, alert.value ?? ""]);
    });

    const csv = rows.map((line) => line.map((value) => `"${String(value ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `clonexa_kpis_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }
  /* CX_KPIS_OPERATIVOS_016A_END */



  /* CX_REPORTS_ADAPTER_01_START */
  function reportsAdapterDefaultRange() {
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - 6);

    return {
      from: start.toISOString().slice(0, 10),
      to: end.toISOString().slice(0, 10),
    };
  }

  function reportsAdapterQuery() {
    const range = reportsAdapterDefaultRange();

    return {
      from: document.querySelector("[data-adaptive-reports-from]")?.value || range.from,
      to: document.querySelector("[data-adaptive-reports-to]")?.value || range.to,
      preset: document.querySelector("[data-adaptive-reports-preset]")?.value || "7d",
    };
  }

  function reportsDataBar(value, max) {
    const width = max > 0 ? Math.min((Number(value || 0) / max) * 100, 100) : 0;

    return `
      <div style="height:11px;border-radius:999px;background:rgba(255,255,255,.12);overflow:hidden">
        <div style="height:100%;width:${width}%;background:linear-gradient(90deg,rgba(0,255,180,.85),rgba(255,0,180,.85));"></div>
      </div>
    `;
  }

  function reportSummaryCards(items) {
    const rows = Array.isArray(items) ? items : [];

    if (!rows.length) {
      return `<div class="client-muted">Sin datos consolidados para este periodo.</div>`;
    }

    return `
      <div class="client-kpi-grid">
        ${rows.map((item) => `
          <div class="client-kpi">
            <span>${h(item.label || "Indicador")}</span>
            <strong>${h(item.value ?? 0)}</strong>
            <small>${h(item.module || "")}</small>
          </div>
        `).join("")}
      </div>
    `;
  }

  function reportChartHtml(chart) {
    const rows = Array.isArray(chart) ? chart : [];

    if (!rows.length) {
      return `<div class="client-muted">Sin datos para graficar.</div>`;
    }

    const max = Math.max(...rows.map((item) => Number(item.value || 0)), 1);

    return `
      <div class="client-report-bars">
        ${rows.map((item) => `
          <div style="display:grid;grid-template-columns:180px 1fr 70px;gap:12px;align-items:center;margin:10px 0">
            <strong>${h(item.label || "Sin clasificar")}</strong>
            ${reportsDataBar(item.value, max)}
            <span>${h(item.value ?? 0)}</span>
          </div>
        `).join("")}
      </div>
    `;
  }

  function reportTableHtml(section) {
    const cols = Array.isArray(section?.columns) ? section.columns : [];
    const rows = Array.isArray(section?.rows) ? section.rows : [];

    if (!cols.length || !rows.length) {
      return `<div class="client-muted">Sin registros detallados para esta sección.</div>`;
    }

    return `
      <div style="overflow:auto;margin-top:14px">
        <table class="client-table" style="width:100%;border-collapse:collapse">
          <thead>
            <tr>
              ${cols.map((col) => `<th style="text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,.12)">${h(col)}</th>`).join("")}
            </tr>
          </thead>
          <tbody>
            ${rows.slice(0, 80).map((row) => `
              <tr>
                ${cols.map((col) => `<td style="padding:10px;border-bottom:1px solid rgba(255,255,255,.08);vertical-align:top">${h(row[col] ?? "")}</td>`).join("")}
              </tr>
            `).join("")}
          </tbody>
        </table>
        ${rows.length > 80 ? `<p class="client-muted">Mostrando 80 de ${h(rows.length)} registros. Usa CSV para descargar completo.</p>` : ""}
      </div>
    `;
  }

  function reportSectionHtml(section) {
    const summary = Array.isArray(section?.summary) ? section.summary : [];

    return `
      <section class="client-panel">
        <div class="client-section-kicker">${h(section?.code || "sección")}</div>
        <h2>${h(section?.title || "Reporte")}</h2>

        ${summary.length ? reportSummaryCards(summary.map((item) => ({ ...item, module: section?.title || "" }))) : ""}

        <div class="client-panel" style="margin-top:14px">
          <h3>Distribución</h3>
          ${reportChartHtml(section?.chart || [])}
        </div>

        <div class="client-panel" style="margin-top:14px">
          <h3>Detalle recolectado</h3>
          ${reportTableHtml(section)}
        </div>
      </section>
    `;
  }

  async function loadAdaptiveReportsDetail() {
    const query = reportsAdapterQuery();
    const qs = new URLSearchParams({
      date_from: query.from,
      date_to: query.to,
      preset: query.preset,
    });

    return await api(`/adaptive-reports-detail-v1/companies/${state.companyId}/detail?${qs.toString()}`);
  }

  async function renderAdaptiveReportsModule() {
    const company = state.company || {};
    const b = normalizeBranding(state.branding || {});
    const range = reportsAdapterDefaultRange();

    let report = null;
    let loadError = "";

    try {
      report = await api(`/adaptive-reports-detail-v1/companies/${state.companyId}/detail?date_from=${range.from}&date_to=${range.to}&preset=7d`);
    } catch (error) {
      loadError = error.message || "No se pudo cargar Reportes.";
      report = null;
    }

    $("app").innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, b)}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>
            <nav class="client-nav">${renderClientNav("reports")}</nav>
            <div class="client-footer-id"><strong>Tenant activo</strong><br>${h(state.companyId || "")}</div>
            <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
          </aside>

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">Módulo transversal</div>
              <h1 class="client-title">Reporte operativo</h1>
              <p class="client-muted">
                Consolida la información real recolectada en el periodo: jornadas, producción, materiales, inventario y operación activa según módulos de esta empresa.
              </p>

              <div class="client-actions" style="display:grid;grid-template-columns:repeat(5,minmax(140px,1fr));gap:10px;align-items:end">
                <label>Desde
                  <input type="date" data-adaptive-reports-from value="${h(report?.date_from || range.from)}">
                </label>
                <label>Hasta
                  <input type="date" data-adaptive-reports-to value="${h(report?.date_to || range.to)}">
                </label>
                <label>Periodo
                  <select data-adaptive-reports-preset>
                    <option value="7d" selected>7 días</option>
                    <option value="30d">30 días</option>
                    <option value="month">Mes actual</option>
                    <option value="today">Hoy</option>
                  </select>
                </label>
                <button class="client-btn client-btn-primary" type="button" data-adaptive-reports-generate>Generar</button>
                <button class="client-btn" type="button" data-adaptive-reports-export>CSV</button>
              </div>
            </header>

            ${loadError ? `<div class="client-panel"><strong>${h(loadError)}</strong></div>` : ""}

            <section class="client-panel">
              <div class="client-section-kicker">Resumen ejecutivo</div>
              <h2>Información consolidada</h2>
              <p class="client-muted">
                ${h(report?.date_from || range.from)} → ${h(report?.date_to || range.to)} · ${h(report?.total_rows || 0)} registros detallados.
              </p>
              ${reportSummaryCards(report?.executive_kpis || [])}
            </section>

            ${(report?.sections || []).map(reportSectionHtml).join("") || `
              <section class="client-panel">
                <h2>Sin registros para este periodo</h2>
                <p class="client-muted">No se encontraron datos detallados en los módulos activos.</p>
              </section>
            `}
          </section>
        </div>
      </main>
    `;
  }

  async function refreshAdaptiveReportsModule() {
    await renderAdaptiveReportsModule();
  }

  function exportAdaptiveReportsCsv() {
    const query = reportsAdapterQuery();
    const qs = new URLSearchParams({
      date_from: query.from,
      date_to: query.to,
      preset: query.preset,
    });

    window.open(`${API}/adaptive-reports-detail-v1/companies/${state.companyId}/detail.csv?${qs.toString()}`, "_blank");
  }

  if (!window.__cxReportsAdapter01Bound) {
    window.__cxReportsAdapter01Bound = true;
    document.addEventListener("click", async (event) => {
      const generate = event.target.closest("[data-adaptive-reports-generate]");
      if (generate) {
        event.preventDefault();
        await refreshAdaptiveReportsModule();
        return;
      }

      const exportButton = event.target.closest("[data-adaptive-reports-export]");
      if (exportButton) {
        event.preventDefault();
        exportAdaptiveReportsCsv();
      }
    });
  }
  /* CX_REPORTS_ADAPTER_01_END */



  /* CX_KPIS_ADAPTER_01_START */
  function kpisAdapterDefaultRange() {
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - 6);

    return {
      from: start.toISOString().slice(0, 10),
      to: end.toISOString().slice(0, 10),
    };
  }

  function kpisAdapterQuery() {
    const range = kpisAdapterDefaultRange();

    return {
      from: document.querySelector("[data-adaptive-kpis-from]")?.value || range.from,
      to: document.querySelector("[data-adaptive-kpis-to]")?.value || range.to,
      preset: document.querySelector("[data-adaptive-kpis-preset]")?.value || "7d",
    };
  }

  function formatAdaptiveKpiValue(item, currency) {
    if (item?.format === "currency") {
      const value = Number(item.value || 0);
      return `${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 }).format(value)} ${item.currency || currency || "COP"}`;
    }

    return String(item?.value ?? 0);
  }

  function adaptiveKpiCards(items, currency, options = {}) {
    const rows = Array.isArray(items) ? items : [];
    const allowToggle = Boolean(options.allowToggle);

    if (!rows.length) {
      return `<div class="client-muted">Sin indicadores para los módulos activos.</div>`;
    }

    return `
      <div class="client-kpi-grid">
        ${rows.map((item) => `
          <div class="client-kpi">
            <span>${h(item.label || "Indicador")}</span>
            <strong>${h(formatAdaptiveKpiValue(item, currency))}</strong>
            <small>${h(item.module || "")}</small>
            ${allowToggle ? `
              <button
                class="client-btn"
                type="button"
                data-kpi-panel-toggle="${h(item.key || "")}"
                data-kpi-panel-visible="${item.panel_visible ? "false" : "true"}"
                style="margin-top:10px"
              >
                ${item.panel_visible ? "Quitar del panel" : "Mostrar en panel"}
              </button>
            ` : ""}
          </div>
        `).join("")}
      </div>
    `;
  }

  function adaptiveKpiSection(section, currency) {
    return `
      <section class="client-panel">
        <div class="client-section-kicker">${h(section?.code || "módulo")}</div>
        <h2>${h(section?.title || "Indicadores")}</h2>
        ${adaptiveKpiCards(section?.items || [], currency, { allowToggle: true })}
      </section>
    `;
  }

  async function loadAdaptiveKpisPanel() {
    const query = kpisAdapterQuery();
    const qs = new URLSearchParams({
      date_from: query.from,
      date_to: query.to,
      preset: query.preset,
    });

    return await api(`/adaptive-kpis-panel-v1/companies/${state.companyId}/panel?${qs.toString()}`);
  }

  async function renderAdaptiveKpisModule() {
    const company = state.company || {};
    const b = normalizeBranding(state.branding || {});
    const range = kpisAdapterDefaultRange();

    let kpis = null;
    let loadError = "";

    try {
      kpis = await api(`/adaptive-kpis-panel-v1/companies/${state.companyId}/panel?date_from=${range.from}&date_to=${range.to}&preset=7d`);
    } catch (error) {
      loadError = error.message || "No se pudieron cargar KPIs.";
      kpis = null;
    }

    const companyName = kpis?.company_name || company.name || "Empresa";
    const currency = kpis?.currency || "COP";
    const selectedCount = Array.isArray(kpis?.selected_keys) ? kpis.selected_keys.length : 0;
    const maxPanel = kpis?.max_panel_kpis || 4;

    $("app").innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, b)}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>
            <nav class="client-nav">${renderClientNav("kpis")}</nav>
            <div class="client-footer-id"><strong>Tenant activo</strong><br>${h(state.companyId || "")}</div>
            <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
          </aside>

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">Módulo transversal</div>
              <h1 class="client-title">Data Board KPIs</h1>
              <p class="client-muted">
                Indicadores adaptativos de ${h(companyName)}. Configura hasta ${h(maxPanel)} tarjetas visibles en el panel principal. Moneda: ${h(currency)}.
              </p>

              <div class="client-actions" style="display:grid;grid-template-columns:repeat(4,minmax(140px,1fr));gap:10px;align-items:end">
                <label>Desde
                  <input type="date" data-adaptive-kpis-from value="${h(kpis?.date_from || range.from)}">
                </label>
                <label>Hasta
                  <input type="date" data-adaptive-kpis-to value="${h(kpis?.date_to || range.to)}">
                </label>
                <label>Periodo
                  <select data-adaptive-kpis-preset>
                    <option value="7d" selected>7 días</option>
                    <option value="30d">30 días</option>
                    <option value="month">Mes actual</option>
                    <option value="today">Hoy</option>
                  </select>
                </label>
                <button class="client-btn client-btn-primary" type="button" data-adaptive-kpis-generate>Actualizar</button>
              </div>
            </header>

            ${loadError ? `<div class="client-panel"><strong>${h(loadError)}</strong></div>` : ""}

            <section class="client-panel">
              <div class="client-section-kicker">Panel principal</div>
              <h2>Tarjetas visibles (${h(selectedCount)} / ${h(maxPanel)})</h2>
              <p class="client-muted">Estas son las tarjetas configuradas para el tablero principal de la empresa.</p>
              ${adaptiveKpiCards(kpis?.top_cards || [], currency)}
            </section>

            <section class="client-panel">
              <div class="client-section-kicker">Configuración</div>
              <h2>Activar o desactivar KPIs del panel</h2>
              <p class="client-muted">Máximo ${h(maxPanel)} tarjetas principales. Los demás indicadores siguen disponibles aquí.</p>
              ${adaptiveKpiCards(kpis?.items || [], currency, { allowToggle: true })}
            </section>

            ${(kpis?.sections || []).map((section) => adaptiveKpiSection(section, currency)).join("")}
          </section>
        </div>
      </main>
    `;
  }

  async function refreshAdaptiveKpisModule() {
    await renderAdaptiveKpisModule();
  }

  async function toggleKpiPanelItem(button) {
    const key = String(button?.dataset?.kpiPanelToggle || "").trim();
    const visible = String(button?.dataset?.kpiPanelVisible || "false") === "true";

    if (!key) return;

    try {
      await api(`/adaptive-kpis-panel-v1/companies/${state.companyId}/panel/toggle`, {
        method: "POST",
        body: JSON.stringify({ key, visible }),
      });
      await renderAdaptiveKpisModule();
    } catch (error) {
      alert(error.message || "No se pudo actualizar el panel.");
    }
  }

  if (!window.__cxKpisAdapter01Bound) {
    window.__cxKpisAdapter01Bound = true;

    document.addEventListener("click", async (event) => {
      const generate = event.target.closest("[data-adaptive-kpis-generate]");
      if (generate) {
        event.preventDefault();
        await refreshAdaptiveKpisModule();
        return;
      }

      const toggle = event.target.closest("[data-kpi-panel-toggle]");
      if (toggle) {
        event.preventDefault();
        await toggleKpiPanelItem(toggle);
      }
    });
  }

  if (!window.__cxReportsKpisHardCutover01Bound) {
    window.__cxReportsKpisHardCutover01Bound = true;

    document.addEventListener("click", async (event) => {
      const moduleTrigger = event.target.closest("[data-client-module]");
      const actionTrigger = event.target.closest("[data-client-action]");

      const moduleCode = String(moduleTrigger?.dataset?.clientModule || "").trim();
      const actionCode = String(actionTrigger?.dataset?.clientAction || "").trim();

      if ((moduleCode === "kpis" || actionCode === "kpis:open") && isClientModuleActivo("kpis")) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        await renderAdaptiveKpisModule();
        return;
      }

      if ((moduleCode === "reports" || actionCode === "reports:open") && isClientModuleActivo("reports")) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        await renderAdaptiveReportsModule();
      }
    }, true);
  }
  /* CX_KPIS_ADAPTER_01_END */



  /* CX_PRODUCCIÓN_01_START */
  function productionDefaultRange() {
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - 6);

    return {
      from: start.toISOString().slice(0, 10),
      to: end.toISOString().slice(0, 10),
    };
  }

  function productionQuery() {
    const range = productionDefaultRange();

    return {
      from: document.querySelector("[data-production-from]")?.value || range.from,
      to: document.querySelector("[data-production-to]")?.value || range.to,
      preset: document.querySelector("[data-production-preset]")?.value || "7d",
    };
  }

  function productionProgressBar(value) {
    const width = Math.min(Number(value || 0), 100);

    return `
      <div style="height:12px;border-radius:999px;background:rgba(255,255,255,.12);overflow:hidden">
        <div style="height:100%;width:${width}%;background:linear-gradient(90deg,rgba(0,255,180,.85),rgba(255,0,180,.85));"></div>
      </div>
    `;
  }

  function productionKpiCards(totals) {
    const cards = [
      ["Referencias", totals?.references_total ?? 0],
      ["Inicial", totals?.initial_quantity_total ?? 0],
      ["Terminadas", totals?.finished_quantity_total ?? 0],
      ["Pendientes", totals?.pending_quantity_total ?? 0],
      ["Avance", `${totals?.progress_percent ?? 0}%`],
      ["Cierres", totals?.closures_total ?? 0],
      ["Sesiones activas", totals?.active_sessions ?? 0],
      ["Minutos periodo", totals?.minutes_period ?? 0],
    ];

    return `
      <div class="client-kpi-grid">
        ${cards.map(([label, value]) => `
          <div class="client-kpi">
            <span>${h(label)}</span>
            <strong>${h(value)}</strong>
            <small>Producción</small>
          </div>
        `).join("")}
      </div>
    `;
  }

  function productionReferencesTable(rows) {
    const items = Array.isArray(rows) ? rows : [];

    if (!items.length) {
      return `<div class="client-muted">Sin referencias productivas registradas.</div>`;
    }

    return `
      <div style="overflow:auto">
        <table class="client-table" style="width:100%;border-collapse:collapse">
          <thead>
            <tr>
              <th style="text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,.12)">Referencia</th>
              <th style="text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,.12)">Talla</th>
              <th style="text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,.12)">Inicial</th>
              <th style="text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,.12)">Terminada</th>
              <th style="text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,.12)">Pendiente</th>
              <th style="text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,.12)">Avance</th>
              <th style="text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,.12)">Bot</th>
            </tr>
          </thead>
          <tbody>
            ${items.map((row) => `
              <tr>
                <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,.08)">${h(row.name || "")}</td>
                <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,.08)">${h(row.size || "")}</td>
                <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,.08)">${h(row.initial_quantity ?? 0)}</td>
                <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,.08)">${h(row.finished_quantity ?? 0)}</td>
                <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,.08)">${h(row.pending_quantity ?? 0)}</td>
                <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,.08);min-width:160px">
                  <strong>${h(row.progress_percent ?? 0)}%</strong>
                  ${productionProgressBar(row.progress_percent)}
                  ${Number(row.over_finished_quantity || 0) > 0 ? `<small>Sobreproducción: ${h(row.over_finished_quantity)}</small>` : ""}
                </td>
                <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,.08)">
                  ${row.bot_active ? "Visible" : "Oculta"}
                </td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function productionClosuresTable(rows) {
    const items = Array.isArray(rows) ? rows : [];

    if (!items.length) {
      return `<div class="client-muted">Sin cierres de producción en este periodo.</div>`;
    }

    return `
      <div style="overflow:auto">
        <table class="client-table" style="width:100%;border-collapse:collapse">
          <thead>
            <tr>
              <th style="text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,.12)">Fecha</th>
              <th style="text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,.12)">Empleado</th>
              <th style="text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,.12)">Referencia</th>
              <th style="text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,.12)">Talla</th>
              <th style="text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,.12)">Total</th>
              <th style="text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,.12)">Canal</th>
            </tr>
          </thead>
          <tbody>
            ${items.slice(0, 120).map((row) => `
              <tr>
                <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,.08)">${h(row.closed_at || "")}</td>
                <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,.08)">${h(row.employee_name || "")}</td>
                <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,.08)">${h(row.reference_name || "")}</td>
                <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,.08)">${h(row.size || "")}</td>
                <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,.08)"><strong>${h(row.quantity_finished ?? 0)}</strong></td>
                <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,.08)">${h(row.source_channel || "")}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function productionBars(rows, labelKey, valueKey) {
    const items = Array.isArray(rows) ? rows : [];

    if (!items.length) {
      return `<div class="client-muted">Sin datos para graficar.</div>`;
    }

    const max = Math.max(...items.map((item) => Number(item[valueKey] || 0)), 1);

    return items.map((item) => {
      const value = Number(item[valueKey] || 0);
      const width = Math.min((value / max) * 100, 100);

      return `
        <div style="display:grid;grid-template-columns:190px 1fr 70px;gap:12px;align-items:center;margin:10px 0">
          <strong>${h(item[labelKey] || "Sin dato")}</strong>
          <div style="height:11px;border-radius:999px;background:rgba(255,255,255,.12);overflow:hidden">
            <div style="height:100%;width:${width}%;background:linear-gradient(90deg,rgba(0,255,180,.85),rgba(255,0,180,.85));"></div>
          </div>
          <span>${h(value)}</span>
        </div>
      `;
    }).join("");
  }

  async function renderProductionModule() {
    const company = state.company || {};
    const b = normalizeBranding(state.branding || {});
    const range = productionDefaultRange();

    let data = null;
    let loadError = "";

    try {
      data = await api(`/production-v1/companies/${state.companyId}/summary?date_from=${range.from}&date_to=${range.to}&preset=7d`);
    } catch (error) {
      loadError = error.message || "No se pudo cargar Producción.";
      data = null;
    }

    $("app").innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, b)}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>
            <nav class="client-nav">${renderClientNav("production")}</nav>
            <div class="client-footer-id"><strong>Tenant activo</strong><br>${h(state.companyId || "")}</div>
            <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
          </aside>

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">Módulo operativo</div>
              <h1 class="client-title">Producción</h1>
              <p class="client-muted">
                Control de referencias, cierres del bot, cantidades terminadas, pendientes, avance y tiempos productivos.
              </p>

              <div class="client-actions" style="display:grid;grid-template-columns:repeat(5,minmax(140px,1fr));gap:10px;align-items:end">
                <label>Desde
                  <input type="date" data-production-from value="${h(data?.date_from || range.from)}">
                </label>
                <label>Hasta
                  <input type="date" data-production-to value="${h(data?.date_to || range.to)}">
                </label>
                <label>Periodo
                  <select data-production-preset>
                    <option value="7d" selected>7 días</option>
                    <option value="30d">30 días</option>
                    <option value="month">Mes actual</option>
                    <option value="today">Hoy</option>
                  </select>
                </label>
                <button class="client-btn client-btn-primary" type="button" data-production-refresh>Actualizar</button>
                <button class="client-btn" type="button" data-production-export>CSV</button>
              </div>
            </header>

            ${loadError ? `<div class="client-panel"><strong>${h(loadError)}</strong></div>` : ""}

            ${data && !data.module_active ? `
              <section class="client-panel">
                <strong>Producción no está activa para esta empresa.</strong>
                <p class="client-muted">Actívala desde Admin V2 → Empresa → Módulos → Producción.</p>
              </section>
            ` : ""}

            <section class="client-panel">
              <div class="client-section-kicker">Resumen operativo</div>
              <h2>Estado productivo</h2>
              ${productionKpiCards(data?.totals || {})}
            </section>

            <section class="client-panel">
              <div class="client-section-kicker">Referencias</div>
              <h2>Avance por referencia y talla</h2>
              ${productionReferencesTable(data?.references || [])}
            </section>

            <section class="client-panel">
              <div class="client-section-kicker">Periodo</div>
              <h2>Producción por empleado</h2>
              ${productionBars(data?.by_employee_period || [], "employee", "finished_quantity")}
            </section>

            <section class="client-panel">
              <div class="client-section-kicker">Periodo</div>
              <h2>Producción por referencia</h2>
              ${productionBars(data?.by_reference_period || [], "reference", "finished_quantity")}
            </section>

            <section class="client-panel">
              <div class="client-section-kicker">Cierres</div>
              <h2>Cierres de producción del periodo</h2>
              ${productionClosuresTable(data?.closures_display || data?.closures_period || [])}
            </section>
          </section>
        </div>
      </main>
    `;
  }

  async function refreshProductionModule() {
    const query = productionQuery();
    const qs = new URLSearchParams({
      date_from: query.from,
      date_to: query.to,
      preset: query.preset,
    });

    const company = state.company || {};
    const b = normalizeBranding(state.branding || {});
    let data = null;

    try {
      data = await api(`/production-v1/companies/${state.companyId}/summary?${qs.toString()}`);
    } catch (error) {
      alert(error.message || "No se pudo actualizar Producción.");
      return;
    }

    await renderProductionModule();

    const fromInput = document.querySelector("[data-production-from]");
    const toInput = document.querySelector("[data-production-to]");
    if (fromInput) fromInput.value = data.date_from;
    if (toInput) toInput.value = data.date_to;
  }

  function exportProductionCsv() {
    const query = productionQuery();
    const qs = new URLSearchParams({
      date_from: query.from,
      date_to: query.to,
      preset: query.preset,
    });

    window.open(`${API}/production-v1/companies/${state.companyId}/export.csv?${qs.toString()}`, "_blank");
  }

  if (!window.__cxProduction01Bound) {
    window.__cxProduction01Bound = true;

    document.addEventListener("click", async (event) => {
      const moduleTrigger = event.target.closest('[data-client-module="production"]');
      if (moduleTrigger && isClientModuleActivo("production")) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        await renderProductionModule();
        return;
      }

      const refresh = event.target.closest("[data-production-refresh]");
      if (refresh) {
        event.preventDefault();
        await refreshProductionModule();
        return;
      }

      const exportBtn = event.target.closest("[data-production-export]");
      if (exportBtn) {
        event.preventDefault();
        exportProductionCsv();
      }
    }, true);
  }
  /* CX_PRODUCCIÓN_01_END */



  /* CX_CRM_LIVE_01_START */
  function crmLiveParseDate(value) {
    if (!value) return null;

    let raw = String(value).trim();
    if (!raw) return null;

    raw = raw.replace(" ", "T");
    raw = raw.replace(/(\.\d{3})\d+/, "$1");
    raw = raw.replace(/([+-]\d{2})$/, "$1:00");

    if (!/[zZ]|[+-]\d{2}:?\d{2}$/.test(raw)) {
      raw = `${raw}Z`;
    }

    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return null;

    return date;
  }

  function crmLiveFormatDuration(ms) {
    if (!Number.isFinite(ms) || ms < 0) ms = 0;

    const totalSeconds = Math.floor(ms / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    return [
      String(hours).padStart(2, "0"),
      String(minutes).padStart(2, "0"),
      String(seconds).padStart(2, "0"),
    ].join(":");
  }

  function crmLiveStopTimers() {
    if (window.__cxCrmLiveActualizarInterval) {
      clearInterval(window.__cxCrmLiveActualizarInterval);
      window.__cxCrmLiveActualizarInterval = null;
    }

    if (window.__cxCrmLiveTimerInterval) {
      clearInterval(window.__cxCrmLiveTimerInterval);
      window.__cxCrmLiveTimerInterval = null;
    }
  }

  function crmLiveUpdateTimers() {
    const root = document.querySelector("[data-crm-live-root]");
    if (!root) {
      crmLiveStopTimers();
      return;
    }

    document.querySelectorAll("[data-live-since]").forEach((node) => {
      const startedAt = crmLiveParseDate(node.dataset.liveSince || "");
      if (!startedAt) {
        node.textContent = "00:00:00";
        return;
      }

      node.textContent = crmLiveFormatDuration(Date.now() - startedAt.getTime());
    });

    document.querySelectorAll("[data-effective-counter]").forEach((node) => {
      const baseSeconds = Number(node.dataset.effectiveCounter || 0);
      const running = String(node.dataset.effectiveRunning || "false") === "true";
      const sync = crmLiveParseDate(node.dataset.effectiveSync || "");

      let seconds = baseSeconds;

      if (running && sync) {
        seconds += Math.max(Math.floor((Date.now() - sync.getTime()) / 1000), 0);
      }

      node.textContent = crmLiveFormatDuration(seconds * 1000);
    });

    document.querySelectorAll("[data-live-seconds]").forEach((node) => {
      const seconds = Number(node.dataset.liveSeconds || 0);
      node.textContent = crmLiveFormatDuration(seconds * 1000);
    });
  }

  function crmStatusBadge(row) {
    const status = String(row.work_status || "").toLowerCase();

    if (status === "working") {
      return `<span style="padding:8px 12px;border-radius:999px;background:rgba(0,255,180,.14);border:1px solid rgba(0,255,180,.35);color:#adffe8">Activo</span>`;
    }

    if (status === "on_break") {
      return `<span style="padding:8px 12px;border-radius:999px;background:rgba(255,172,28,.16);border:1px solid rgba(255,172,28,.4);color:#ffd58a">En pausa</span>`;
    }

    return `<span style="padding:8px 12px;border-radius:999px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.16);color:#dbe7ff">Fuera de turno</span>`;
  }

  function crmLiveKpis(summary) {
    const cards = [
      ["Activos", summary?.active_now ?? 0],
      ["En pausa", summary?.on_break ?? 0],
      ["Con referencia", summary?.with_active_reference ?? 0],
      ["Sesiones ref.", summary?.active_reference_sessions ?? 0],
      ["Producción", summary?.production_enabled ? "ON" : "OFF"],
    ];

    return `
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px">
        ${cards.map(([label, value]) => `
          <div style="padding:16px;border-radius:18px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12)">
            <div style="font-size:12px;opacity:.75;text-transform:uppercase;letter-spacing:.08em">${h(label)}</div>
            <strong style="display:block;margin-top:8px;font-size:30px;line-height:1">${h(value)}</strong>
          </div>
        `).join("")}
      </div>
    `;
  }

  function crmEffectiveCounterMarkup(seconds, running) {
    return `
      <strong
        style="font-size:26px"
        data-effective-counter="${h(seconds || 0)}"
        data-effective-running="${running ? "true" : "false"}"
        data-effective-sync="${h(new Date().toISOString())}"
      >00:00:00</strong>
    `;
  }

  function crmTurnRow(row) {
    const status = String(row.work_status || "").toLowerCase();

    if (status === "on_break") {
      return `
        <div style="display:grid;grid-template-columns:1fr auto;gap:16px;align-items:center;padding:14px 0;border-top:1px solid rgba(255,255,255,.1)">
          <div>
            <strong style="color:#ffd58a">Pausa activa</strong>
            <div class="client-muted">Tiempo en pausa</div>
          </div>
          <strong style="font-size:26px;color:#ffd58a" data-live-since="${h(row.pause_started_at || row.status_started_at || "")}">00:00:00</strong>
        </div>

        <div style="display:grid;grid-template-columns:1fr auto;gap:16px;align-items:center;padding:14px 0;border-top:1px solid rgba(255,255,255,.1)">
          <div>
            <strong>Turno efectivo</strong>
            <div class="client-muted">Congelado durante la pausa</div>
          </div>
          ${crmEffectiveCounterMarkup(row.shift_effective_seconds || 0, false)}
        </div>
      `;
    }

    if (status === "working") {
      return `
        <div style="display:grid;grid-template-columns:1fr auto;gap:16px;align-items:center;padding:14px 0;border-top:1px solid rgba(255,255,255,.1)">
          <div>
            <strong>Turno efectivo</strong>
            <div class="client-muted">Tiempo pagable / productivo</div>
          </div>
          ${crmEffectiveCounterMarkup(row.shift_effective_seconds || 0, true)}
        </div>
      `;
    }

    return `
      <div style="display:grid;grid-template-columns:1fr auto;gap:16px;align-items:center;padding:14px 0;border-top:1px solid rgba(255,255,255,.1)">
        <div>
          <strong>Fuera de turno</strong>
          <div class="client-muted">Sin jornada activa</div>
        </div>
        <strong style="font-size:26px">00:00:00</strong>
      </div>
    `;
  }

  function crmReferenceTimeline(row) {
    const timeline = Array.isArray(row.reference_timeline) ? row.reference_timeline : [];
    const isPaused = String(row.work_status || "").toLowerCase() === "on_break";
    const isWorking = String(row.work_status || "").toLowerCase() === "working";

    if (!timeline.length) {
      return `
        <div style="padding:14px 0;border-top:1px solid rgba(255,255,255,.1)">
          <strong>Producción actual</strong>
          <div class="client-muted">Sin referencia activa</div>
        </div>
      `;
    }

    return `
      <div style="padding:14px 0;border-top:1px solid rgba(255,255,255,.1)">
        <strong>Producción del turno</strong>
        <div style="margin-top:10px;display:grid;gap:10px">
          ${timeline.map((item) => {
            const active = !!item.is_active;
            const running = active && isWorking;
            const label = active
              ? (isPaused ? "Referencia activa · pausada" : "Referencia activa · corriendo")
              : "Referencia cerrada";

            const counter = active
              ? crmEffectiveCounterMarkup(item.effective_seconds || 0, running)
              : `<strong style="font-size:22px" data-live-seconds="${h(item.effective_seconds || item.duration_seconds || 0)}">00:00:00</strong>`;

            return `
              <div style="display:grid;grid-template-columns:1fr auto;gap:16px;align-items:center;padding:12px;border-radius:16px;background:${active ? "rgba(0,255,180,.10)" : "rgba(255,255,255,.06)"};border:1px solid ${active ? "rgba(0,255,180,.25)" : "rgba(255,255,255,.1)"}">
                <div>
                  <strong>${h(item.reference_name || "Referencia")}</strong>
                  <div class="client-muted">${h(label)}</div>
                </div>
                ${counter}
              </div>
            `;
          }).join("")}
        </div>
      </div>
    `;
  }

  function crmLiveEmployeeCard(row) {
    return `
      <article style="padding:20px;border-radius:26px;background:linear-gradient(135deg,rgba(255,255,255,.11),rgba(255,255,255,.045));border:1px solid rgba(255,255,255,.14);box-shadow:0 20px 45px rgba(0,0,0,.22)">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:14px">
          <div>
            <div class="client-muted">Colaborador</div>
            <h2 style="margin:4px 0 4px;font-size:28px;letter-spacing:.04em">${h(row.employee_name || "Empleado")}</h2>
            ${row.employee_role ? `<div class="client-muted">${h(row.employee_role)}</div>` : ""}
          </div>
          ${crmStatusBadge(row)}
        </div>

        ${crmTurnRow(row)}
        ${crmReferenceTimeline(row)}
      </article>
    `;
  }

  async function loadCrmLiveSnapshot() {
    return await api(`/crm-live-v1/companies/${state.companyId}/snapshot`);
  }

  async function renderCrmLiveModule() {
    crmLiveStopTimers();

    const company = state.company || {};
    const b = normalizeBranding(state.branding || {});

    let snapshot = null;
    let loadError = "";

    try {
      snapshot = await loadCrmLiveSnapshot();
    } catch (error) {
      loadError = error.message || "No se pudo cargar CRM en vivo.";
      snapshot = null;
    }

    $("app").innerHTML = `
      <main class="client-shell" data-crm-live-root>
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, b)}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>
            <nav class="client-nav">${renderClientNav("crm")}</nav>
            <div class="client-footer-id"><strong>Tenant activo</strong><br>${h(state.companyId || "")}</div>
            <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
          </aside>

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">Módulo compartido · tiempo real</div>
              <h1 class="client-title">CRM Campo</h1>
              <p class="client-muted">
                Vista viva de colaboradores, pausa, turno efectivo y referencia sin sumar tiempo muerto.
              </p>
              <div class="client-actions">
                <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
                <button class="client-btn client-btn-primary" type="button" data-crm-live-refresh>Actualizar</button>
              </div>
            </header>

            ${loadError ? `<section class="client-panel"><strong>${h(loadError)}</strong></section>` : ""}

            <section class="client-panel">
              <div class="client-section-kicker">Estado operativo actual</div>
              <h2>Operación en vivo</h2>
              ${crmLiveKpis(snapshot?.summary || {})}
            </section>

            <section class="client-panel">
              <div class="client-section-kicker">Colaboradores</div>
              <h2>Estado por colaborador</h2>
              <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:18px">
                ${(snapshot?.employees || []).map(crmLiveEmployeeCard).join("") || `<div class="client-muted">Sin colaboradores activos.</div>`}
              </div>
            </section>
          </section>
        </div>
      </main>
    `;

    crmLiveUpdateTimers();

    window.__cxCrmLiveTimerInterval = setInterval(crmLiveUpdateTimers, 1000);

    window.__cxCrmLiveActualizarInterval = setInterval(async () => {
      if (!document.querySelector("[data-crm-live-root]")) {
        crmLiveStopTimers();
        return;
      }

      await renderCrmLiveModule();
    }, 20000);
  }

  if (!window.__cxCrmLive01Bound) {
    window.__cxCrmLive01Bound = true;

    document.addEventListener("click", async (event) => {
      const moduleTrigger = event.target.closest('[data-client-module="crm"]');
      const actionTrigger = event.target.closest('[data-client-action="crm:open"]');

      if ((moduleTrigger || actionTrigger) && isClientModuleActive("crm")) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        await renderCrmLiveModule();
        return;
      }

      const refresh = event.target.closest("[data-crm-live-refresh]");
      if (refresh) {
        event.preventDefault();
        await renderCrmLiveModule();
      }
    }, true);
  }
  /* CX_CRM_LIVE_01_END */



  /* CX_CRM_CORE_ADAPTERS_01_START */
  function crmCoreParseDate(value) {
    if (!value) return null;

    let raw = String(value).trim();
    if (!raw) return null;

    raw = raw.replace(" ", "T");
    raw = raw.replace(/(\.\d{3})\d+/, "$1");
    raw = raw.replace(/([+-]\d{2})$/, "$1:00");

    if (!/[zZ]|[+-]\d{2}:?\d{2}$/.test(raw)) {
      raw = `${raw}Z`;
    }

    const date = new Date(raw);

    if (Number.isNaN(date.getTime())) return null;

    return date;
  }

  function crmCoreFormatDuration(ms) {
    if (!Number.isFinite(ms) || ms < 0) ms = 0;

    const totalSeconds = Math.floor(ms / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    return [
      String(hours).padStart(2, "0"),
      String(minutes).padStart(2, "0"),
      String(seconds).padStart(2, "0"),
    ].join(":");
  }

  function crmCoreStopTimers() {
    if (window.__cxCrmCoreTimerInterval) {
      clearInterval(window.__cxCrmCoreTimerInterval);
      window.__cxCrmCoreTimerInterval = null;
    }

    if (window.__cxCrmCoreRefreshInterval) {
      clearInterval(window.__cxCrmCoreRefreshInterval);
      window.__cxCrmCoreRefreshInterval = null;
    }
  }

  function crmCoreUpdateTimers() {
    const root = document.querySelector("[data-crm-core-root]");
    if (!root) {
      crmCoreStopTimers();
      return;
    }

    document.querySelectorAll("[data-crm-core-counter]").forEach((node) => {
      const baseSeconds = Number(node.dataset.crmCoreCounter || 0);
      const running = String(node.dataset.crmCoreRunning || "false") === "true";
      const syncAt = crmCoreParseDate(node.dataset.crmCoreSync || "");

      let seconds = baseSeconds;

      if (running && syncAt) {
        seconds += Math.max(Math.floor((Date.now() - syncAt.getTime()) / 1000), 0);
      }

      node.textContent = crmCoreFormatDuration(seconds * 1000);
    });

    document.querySelectorAll("[data-crm-core-since]").forEach((node) => {
      const startAt = crmCoreParseDate(node.dataset.crmCoreSince || "");
      if (!startAt) {
        node.textContent = "00:00:00";
        return;
      }

      node.textContent = crmCoreFormatDuration(Date.now() - startAt.getTime());
    });
  }

  function crmCoreCounter(seconds, running, size = 26) {
    return `
      <strong
        style="font-size:${size}px"
        data-crm-core-counter="${h(seconds || 0)}"
        data-crm-core-running="${running ? "true" : "false"}"
        data-crm-core-sync="${h(new Date().toISOString())}"
      >00:00:00</strong>
    `;
  }

  function crmCoreStatusBadge(core) {
    const status = String(core?.status || "").toLowerCase();

    if (status === "working") {
      return `<span style="padding:8px 12px;border-radius:999px;background:rgba(0,255,180,.14);border:1px solid rgba(0,255,180,.35);color:#adffe8">Activo</span>`;
    }

    if (status === "on_break") {
      return `<span style="padding:8px 12px;border-radius:999px;background:rgba(255,172,28,.16);border:1px solid rgba(255,172,28,.4);color:#ffd58a">En pausa</span>`;
    }

    return `<span style="padding:8px 12px;border-radius:999px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.16);color:#dbe7ff">Fuera de turno</span>`;
  }

  function crmCoreKpis(summary) {
    const cards = [
      ["Activos", summary?.active_now ?? 0],
      ["En pausa", summary?.on_break ?? 0],
      ["Fuera", summary?.out ?? 0],
      ["Producción", summary?.production_adapter ? "ON" : "OFF"],
      ["GPS", summary?.gps_adapter ? "ON" : "OFF"],
      ["Materiales", summary?.materials_adapter ? "ON" : "OFF"],
    ];

    return `
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px">
        ${cards.map(([label, value]) => `
          <div style="padding:16px;border-radius:18px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12)">
            <div style="font-size:12px;opacity:.75;text-transform:uppercase;letter-spacing:.08em">${h(label)}</div>
            <strong style="display:block;margin-top:8px;font-size:28px;line-height:1">${h(value)}</strong>
          </div>
        `).join("")}
      </div>
    `;
  }

  function crmCoreTimeRows(core) {
    const status = String(core?.status || "").toLowerCase();

    const shiftRow = `
      <div style="display:grid;grid-template-columns:1fr auto;gap:16px;align-items:center;padding:14px 0;border-top:1px solid rgba(255,255,255,.1)">
        <div>
          <strong>Turno efectivo</strong>
          <div class="client-muted">${status === "on_break" ? "Congelado durante la pausa" : "Tiempo pagable / productivo"}</div>
        </div>
        ${crmCoreCounter(core?.shift_effective_seconds || 0, status === "working")}
      </div>
    `;

    const pauseRow = status === "on_break"
      ? `
        <div style="display:grid;grid-template-columns:1fr auto;gap:16px;align-items:center;padding:14px 0;border-top:1px solid rgba(255,255,255,.1)">
          <div>
            <strong style="color:#ffd58a">Pausa activa</strong>
            <div class="client-muted">No suma a nómina ni producción</div>
          </div>
          <strong style="font-size:26px;color:#ffd58a" data-crm-core-since="${h(core?.pause_started_at || "")}">00:00:00</strong>
        </div>
      `
      : `
        <div style="display:grid;grid-template-columns:1fr auto;gap:16px;align-items:center;padding:14px 0;border-top:1px solid rgba(255,255,255,.1)">
          <div>
            <strong>Pausa acumulada</strong>
            <div class="client-muted">Tiempo no pagable</div>
          </div>
          ${crmCoreCounter(core?.pause_accumulated_seconds || 0, false)}
        </div>
      `;

    if (status === "sin_turno" || status === "checked_out") {
      return `
        <div style="display:grid;grid-template-columns:1fr auto;gap:16px;align-items:center;padding:14px 0;border-top:1px solid rgba(255,255,255,.1)">
          <div>
            <strong>Fuera de turno</strong>
            <div class="client-muted">Sin jornada activa</div>
          </div>
          <strong style="font-size:26px">00:00:00</strong>
        </div>
      `;
    }

    return shiftRow + pauseRow;
  }

  function crmProductionAdapter(adapter, core) {
    const items = Array.isArray(adapter?.items) ? adapter.items : [];
    const status = String(core?.status || "").toLowerCase();

    if (!items.length) return "";

    return `
      <div style="padding:14px 0;border-top:1px solid rgba(255,255,255,.1)">
        <strong>${h(adapter.title || "Producción del turno")}</strong>
        <div style="margin-top:10px;display:grid;gap:10px">
          ${items.map((item) => {
            const active = !!item.is_active;
            const running = active && status === "working" && !!item.running;
            const label = active
              ? (status === "on_break" ? "Referencia activa · pausada" : "Referencia activa · corriendo")
              : "Referencia cerrada";

            return `
              <div style="display:grid;grid-template-columns:1fr auto;gap:16px;align-items:center;padding:12px;border-radius:16px;background:${active ? "rgba(0,255,180,.10)" : "rgba(255,255,255,.06)"};border:1px solid ${active ? "rgba(0,255,180,.25)" : "rgba(255,255,255,.1)"}">
                <div>
                  <strong>${h(item.reference_name || "Referencia")}</strong>
                  <div class="client-muted">${h(label)}</div>
                </div>
                ${crmCoreCounter(item.effective_seconds || 0, running, 22)}
              </div>
            `;
          }).join("")}
        </div>
      </div>
    `;
  }

  function crmGenericAdapter(adapter) {
    if (adapter?.code === "production_references") return "";

    return `
      <div style="padding:14px 0;border-top:1px solid rgba(255,255,255,.1)">
        <strong>${h(adapter?.title || adapter?.code || "Adapter")}</strong>
        <div class="client-muted">${h(adapter?.placeholder || "Adapter listo para conectar datos del módulo.")}</div>
      </div>
    `;
  }

  function crmCoreEmployeeCard(row) {
    const core = row.core || {};
    const adapters = Array.isArray(row.adapters) ? row.adapters : [];
    const production = adapters.find((adapter) => adapter.code === "production_references");
    const genericAdapters = adapters.filter((adapter) => adapter.code !== "production_references");

    return `
      <article style="padding:20px;border-radius:26px;background:linear-gradient(135deg,rgba(255,255,255,.11),rgba(255,255,255,.045));border:1px solid rgba(255,255,255,.14);box-shadow:0 20px 45px rgba(0,0,0,.22)">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:14px">
          <div>
            <div class="client-muted">Colaborador</div>
            <h2 style="margin:4px 0 4px;font-size:28px;letter-spacing:.04em">${h(row.employee_name || "Empleado")}</h2>
            ${row.employee_role ? `<div class="client-muted">${h(row.employee_role)}</div>` : ""}
          </div>
          ${crmCoreStatusBadge(core)}
        </div>

        ${crmCoreTimeRows(core)}
        ${production ? crmProductionAdapter(production, core) : ""}
        ${genericAdapters.map(crmGenericAdapter).join("")}
      </article>
    `;
  }

  async function loadCrmCoreSnapshot() {
    return await api(`/crm-core-v1/companies/${state.companyId}/snapshot`);
  }

  async function renderCrmCoreModule() {
    if (typeof crmLiveStopTimers === "function") crmLiveStopTimers();
    crmCoreStopTimers();

    const company = state.company || {};
    const b = normalizeBranding(state.branding || {});

    let snapshot = null;
    let loadError = "";

    try {
      snapshot = await loadCrmCoreSnapshot();
    } catch (error) {
      loadError = error.message || "No se pudo cargar CRM Core.";
      snapshot = null;
    }

    $("app").innerHTML = `
      <main class="client-shell" data-crm-core-root>
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, b)}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>
            <nav class="client-nav">${renderClientNav("crm")}</nav>
            <div class="client-footer-id"><strong>Tenant activo</strong><br>${h(state.companyId || "")}</div>
            <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
          </aside>

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">CRM Core · adapters dinámicos</div>
              <h1 class="client-title">CRM Campo</h1>
              <p class="client-muted">
                Núcleo universal de turno efectivo, pausa y módulos activos por empresa.
              </p>
              <div class="client-actions">
                <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
                <button class="client-btn client-btn-primary" type="button" data-crm-core-refresh>Actualizar</button>
              </div>
            </header>

            ${loadError ? `<section class="client-panel"><strong>${h(loadError)}</strong></section>` : ""}

            <section class="client-panel">
              <div class="client-section-kicker">Estado operativo actual</div>
              <h2>Operación en vivo</h2>
              ${crmCoreKpis(snapshot?.summary || {})}
            </section>

            <section class="client-panel">
              <div class="client-section-kicker">Colaboradores</div>
              <h2>Estado por colaborador</h2>
              <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:18px">
                ${(snapshot?.employees || []).map(crmCoreEmployeeCard).join("") || `<div class="client-muted">Sin colaboradores activos.</div>`}
              </div>
            </section>
          </section>
        </div>
      </main>
    `;

    crmCoreUpdateTimers();

    window.__cxCrmCoreTimerInterval = setInterval(crmCoreUpdateTimers, 1000);

    window.__cxCrmCoreRefreshInterval = setInterval(async () => {
      if (!document.querySelector("[data-crm-core-root]")) {
        crmCoreStopTimers();
        return;
      }

      await renderCrmCoreModule();
    }, 20000);
  }

  if (!window.__cxCrmCoreAdapters01Bound) {
    window.__cxCrmCoreAdapters01Bound = true;

    document.addEventListener("click", async (event) => {
      const moduleTrigger = event.target.closest('[data-client-module="crm"]');
      const actionTrigger = event.target.closest('[data-client-action="crm:open"]');

      if ((moduleTrigger || actionTrigger) && isClientModuleActive("crm")) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        await renderCrmCoreModule();
        return;
      }

      const refresh = event.target.closest("[data-crm-core-refresh]");
      if (refresh) {
        event.preventDefault();
        await renderCrmCoreModule();
      }
    }, true);
  }
  /* CX_CRM_CORE_ADAPTERS_01_END */


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
              <div class="client-eyebrow">Módulo activo</div>
              <h1 class="client-title">${h(moduleLabel(code))}</h1>
              <p class="client-muted">Este módulo esta asignado a la empresa y se construirá como pantalla independiente.</p>
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
              <div class="client-eyebrow">Módulo Workforce</div>
              <h1 class="client-title">Personal</h1>
              <p class="client-muted">Gestiona empleados, técnicos, supervisores y roles conectados a bot, nómina y operación.</p>

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

        if (action === "workforce:add" && isClientModuleActivo("workforce")) {
          await renderPersonalModule();
          setTimeout(() => document.querySelector("[data-personal-add-row]")?.click(), 60);
          return;
        }

        if (action === "bots:open" && isClientModuleActivo("bots")) {
          await renderBotsModule();
          return;
        }

        if (action === "crm:open" && isClientModuleActivo("crm")) {
          await renderCrmModule();
          return;
        }

        if (action === "payroll:open" && isClientModuleActivo("payroll")) {
          await renderPayrollModule();
          return;
        }

        if (action === "inventory:open" && isClientModuleActivo("inventory")) {
          await renderInventoryModule();
          return;
        }

        if (action === "materials:open" && isClientModuleActivo("materials")) {
          await renderMaterialsModule();
          return;
        }

        if (action === "gps:open" && isClientModuleActivo("gps")) {
          await renderGpsModule();
          return;
        }

        if (action === "kpis:open" && isClientModuleActivo("kpis")) {
          await renderAdaptiveKpisModule();
          return;
        }

        if (action === "reports:open" && isClientModuleActivo("reports")) {
          await renderAdaptiveReportsModule();
          return;
        }
      }

      const moduleTrigger = target.closest("[data-client-module]");
      if (moduleTrigger) {
        const code = String(moduleTrigger.dataset.clientModule || "").trim();
        if (code === "reports" && isClientModuleActivo("reports")) {
          await renderAdaptiveReportsModule();
          return;
        }

        if (code === "crm" && isClientModuleActivo("crm")) {
          await renderCrmLiveModule();
          return;
        }

        if (code === "production" && isClientModuleActivo("production")) {
          await renderProductionModule();
          return;
        }


        if (!isClientModuleActivo(code)) return;

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

        if (code === "payroll") {
          await renderPayrollModule();
          return;
        }

        if (code === "inventory") {
          await renderInventoryModule();
          return;
        }

        if (code === "materials") {
          await renderMaterialsModule();
          return;
        }

        if (code === "gps") {
          await renderGpsModule();
          return;
        }

        if (code === "kpis") {
          await renderAdaptiveKpisModule();
          return;
        }

        await renderClientModulePlaceholder(code);
        return;
      }

      if (target.closest("[data-payroll-apply]") || target.closest("[data-payroll-refresh]")) {
        await renderPayrollModule(payrollReadPeriod());
        return;
      }

      if (target.closest("[data-payroll-export]")) {
        exportPayrollCsv();
        return;
      }

      if (target.closest("[data-kpis-apply]")) {
        await renderKpisModule(kpisReadPeriod());
        return;
      }

      const kpiDashboardToggle = target.closest("[data-kpi-dashboard-toggle]");
      if (kpiDashboardToggle) {
        const key = String(kpiDashboardToggle.dataset.kpiDashboardToggle || "");
        const summary = window.__cxKpisSummary || {};
        const cards = Array.isArray(summary.cards) ? summary.cards : [];
        const selected = cards
          .filter((card) => !!card.show_on_dashboard)
          .map((card) => String(card.key || ""))
          .filter(Boolean);

        const next = new Set(selected);
        if (next.has(key)) next.delete(key);
        else next.add(key);

        await saveKpisDashboardCards(Array.from(next).slice(0, 4));
        state.dashboardMetrics = await loadClientDashboardMetrics(state.companyId, activeClientModules());
        await renderKpisModule(window.__cxKpisPeriod || kpisDefaultPeriod());
        return;
      }

      if (target.closest("[data-kpis-export]")) {
        exportKpisCsv();
        return;
      }

      if (target.closest("[data-gps-refresh]")) {
        await renderGpsModule();
        return;
      }

      if (target.closest("[data-gps-save]")) {
        try {
          await saveGpsPerimeters();
        } catch (error) {
          showGpsNotice(error.message || "No se pudo guardar GPS.", "error");
        }
        return;
      }

      if (target.closest("[data-inventory-refresh]")) {
        await renderInventoryModule();
        return;
      }

      const inventoryModeBtn = target.closest("[data-inventory-mode]");
      if (inventoryModeBtn) {
        setInventoryMode(String(inventoryModeBtn.dataset.inventoryMode || "create"));
        await renderInventoryModule();
        return;
      }

      if (target.closest("[data-inventory-create]")) {
        try {
          await createInventoryItem();
        } catch (error) {
          showInventoryNotice(error.message || "No se pudo crear el material.", "error");
        }
        return;
      }

      const inventoryUpdateBtn = target.closest("[data-inventory-update]");
      if (inventoryUpdateBtn) {
        try {
          await updateInventoryItem(inventoryUpdateBtn.dataset.inventoryUpdate);
        } catch (error) {
          showInventoryNotice(error.message || "No se pudo actualizar el material.", "error");
        }
        return;
      }

      const inventoryEntryBtn = target.closest("[data-inventory-entry]");
      if (inventoryEntryBtn) {
        try {
          await addInventoryEntry(inventoryEntryBtn.dataset.inventoryEntry);
        } catch (error) {
          showInventoryNotice(error.message || "No se pudo ingresar cantidad.", "error");
        }
        return;
      }

      const inventoryDisableBtn = target.closest("[data-inventory-disable]");
      if (inventoryDisableBtn) {
        try {
          await disableInventoryItem(inventoryDisableBtn.dataset.inventoryDisable);
        } catch (error) {
          showInventoryNotice(error.message || "No se pudo deshabilitar el material.", "error");
        }
        return;
      }

      if (target.closest("[data-inventory-export]")) {
        exportInventoryCsv();
        return;
      }

      if (target.closest("[data-materials-refresh]")) {
        await renderMaterialsModule();
        return;
      }

      if (target.closest("[data-materials-export]")) {
        await exportMaterialsCsv();
        return;
      }

      const materialApproveOpen = target.closest("[data-material-approve-open]");
      if (materialApproveOpen) {
        renderMaterialsApproveSheet(materialApproveOpen.dataset.materialApproveOpen);
        return;
      }

      const materialApproveSave = target.closest("[data-material-approve-save]");
      if (materialApproveSave) {
        try {
          await approveMaterialRequest(materialApproveSave.dataset.materialApproveSave);
        } catch (error) {
          showMaterialsNotice(error.message || "No se pudo aprobar la orden.", "error");
        }
        return;
      }

      const materialDeliver = target.closest("[data-material-deliver]");
      if (materialDeliver) {
        try {
          await deliverMaterialRequest(materialDeliver.dataset.materialDeliver);
        } catch (error) {
          showMaterialsNotice(error.message || "No se pudo entregar la orden.", "error");
        }
        return;
      }

      const materialReject = target.closest("[data-material-reject]");
      if (materialReject) {
        try {
          await rejectMaterialRequest(materialReject.dataset.materialReject);
        } catch (error) {
          showMaterialsNotice(error.message || "No se pudo rechazar la orden.", "error");
        }
        return;
      }

      const materialDetailLoad = target.closest("[data-material-detail-load]");
      if (materialDetailLoad) {
        await loadMaterialOrderDetail(materialDetailLoad.dataset.materialDetailLoad);
        return;
      }

      const materialConsignLoad = target.closest("[data-material-consign-load]");
      if (materialConsignLoad) {
        await fillReturnOrder(materialConsignLoad.dataset.materialConsignLoad, "consign");
        return;
      }

      const materialReturnLoad = target.closest("[data-material-return-load]");
      if (materialReturnLoad) {
        await fillReturnOrder(materialReturnLoad.dataset.materialReturnLoad, "return");
        return;
      }

      const materialReturnPick = target.closest("[data-material-return-order-pick]");
      if (materialReturnPick) {
        await fillReturnOrder(materialReturnPick.dataset.materialReturnOrderPick, window.__cxMaterialsOperationMode || "return");
        return;
      }

      if (target.closest("[data-material-return-save]")) {
        try {
          await returnMaterialOrder();
        } catch (error) {
          showMaterialsNotice(error.message || "No se pudo registrar la devolución.", "error");
        }
        return;
      }

      const materialStatusBtn = target.closest("[data-material-status]");
      if (materialStatusBtn) {
        try {
          await updateMaterialStatus(materialStatusBtn.dataset.materialId, materialStatusBtn.dataset.materialStatus);
        } catch (error) {
          showMaterialsNotice(error.message || "No se pudo actualizar Materiales.", "error");
        }
        return;
      }

      if (target.closest("[data-bot-save-name]")) {
        await saveClientBotName();
        return;
      }
    });

    document.addEventListener("input", (event) => {
      const personalInput = event.target.closest("[data-personal-search]");
      if (personalInput) {
        const query = String(personalInput.value || "").toLowerCase().trim();

        document.querySelectorAll("[data-personal-row]").forEach((row) => {
          const text = String(row.textContent || "").toLowerCase();
          row.style.display = !query || text.includes(query) ? "contents" : "none";
        });
        return;
      }

      const inventoryInput = event.target.closest("[data-inventory-search]");
      if (inventoryInput) {
        const query = String(inventoryInput.value || "").toLowerCase().trim();
        document.querySelectorAll("[data-inventory-row]").forEach((row) => {
          const text = String(row.textContent || "").toLowerCase();
          row.style.display = !query || text.includes(query) ? "" : "none";
        });
        return;
      }

      const materialReturnOrderInput = event.target.closest("[data-material-return-order]");
      if (materialReturnOrderInput) {
        const query = String(materialReturnOrderInput.value || "").trim();
        if (query !== String(window.__cxMaterialsReturnOrder || "")) {
          window.__cxMaterialsReturnOrder = "";
          const checklist = document.querySelector("[data-material-return-checklist]");
          if (checklist) checklist.dataset.materialReturnSelectedOrder = "";
        }
        window.clearTimeout(window.__materialsReturnSearchTimer);
        window.__materialsReturnSearchTimer = window.setTimeout(() => {
          searchMaterialReturnOrders(query);
        }, 220);
        return;
      }
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
                <span class="client-badge">${h(modules.length)} módulos activos</span>
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
                    <strong>Sin módulos activos</strong>
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

    if (codes.has("kpis")) {
      try {
        const summary = await api(`/kpis/companies/${encodeURIComponent(companyId)}/summary?preset=today`);
        metrics.kpiDashboardCards = Array.isArray(summary.dashboard_cards)
          ? summary.dashboard_cards
          : [];
      } catch (error) {
        metrics.kpiDashboardCards = [];
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


      .cx-materials-return-results,
      .cx-materials-return-checklist {
        margin-top: 14px;
        display: grid;
        gap: 10px;
      }
      .cx-materials-order-pick {
        width: 100%;
        text-align: left;
        border: 1px solid rgba(255,255,255,.14);
        background: rgba(255,255,255,.07);
        color: inherit;
        border-radius: 15px;
        padding: 12px 14px;
        cursor: pointer;
        font-weight: 900;
      }
      .cx-materials-order-pick:hover {
        border-color: rgba(255,255,255,.28);
        transform: translateY(-1px);
      }
      .cx-materials-return-summary {
        border: 1px solid rgba(255,255,255,.14);
        background: rgba(255,255,255,.06);
        border-radius: 18px;
        padding: 14px;
        display: grid;
        gap: 5px;
      }
      .cx-materials-return-line {
        border: 1px solid rgba(255,255,255,.12);
        background: rgba(0,0,0,.14);
        border-radius: 18px;
        overflow: hidden;
      }
      .cx-materials-return-line summary {
        cursor: pointer;
        padding: 14px;
        font-weight: 1000;
      }
      .cx-materials-return-units {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
        gap: 8px;
        padding: 0 14px 14px;
      }
      .cx-materials-return-unit {
        display: flex;
        gap: 8px;
        align-items: center;
        padding: 10px 11px;
        border: 1px solid rgba(255,255,255,.10);
        background: rgba(255,255,255,.06);
        border-radius: 13px;
        font-weight: 900;
      }
      .cx-materials-return-unit.disabled {
        opacity: .45;
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
              <div class="client-eyebrow">Módulo Workforce</div>
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
    const data = [["Fecha/Hora", "Empleado", "Rol", "Evento", "Canal", "Módulo", "Detalle", "Estado"]];

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


/* CX_REPORTS_016B_START */
(() => {
  "use strict";

  const API = "/api/v1";

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
      throw new Error(`${res.status} ${res.statusText} ${text}`);
    }
    return res.json();
  }

  function companyIdFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return params.get("company_id") || params.get("companyId") || params.get("tenant") || "";
  }

  function todayIso(offsetDays = 0) {
    const d = new Date();
    d.setDate(d.getDate() + offsetDays);
    return d.toISOString().slice(0, 10);
  }

  function fmt(value) {
    if (value === null || value === undefined || value === "") return "-";
    if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toLocaleString("es", { maximumFractionDigits: 2 });
    return String(value);
  }

  function fmtMoney(value) {
    const n = Number(value || 0);
    return n.toLocaleString("es", { style: "currency", currency: "COP", maximumFractionDigits: 2 });
  }

  function fmtDate(value) {
    if (!value) return "-";
    try {
      return new Intl.DateTimeFormat("es", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
    } catch (_) {
      return String(value);
    }
  }

  function reportStyles() {
    if (document.getElementById("cxReports016BStyles")) return;
    const style = document.createElement("style");
    style.id = "cxReports016BStyles";
    style.textContent = `
      .cx-reports-toolbar {
        display: grid;
        grid-template-columns: 130px 130px 160px 160px 180px minmax(240px, 1fr) auto auto auto;
        gap: 10px;
        align-items: end;
        margin-top: 18px;
      }
      .cx-reports-field span {
        display: block;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: .08em;
        opacity: .72;
        margin-bottom: 7px;
      }
      .cx-reports-field input,
      .cx-reports-field select {
        width: 100%;
        border: 1px solid rgba(255,255,255,.15);
        background: rgba(0,0,0,.18);
        color: inherit;
        border-radius: 14px;
        padding: 12px 12px;
        outline: none;
      }
      .cx-reports-field select option { color: #111; }
      .cx-reports-kpis {
        display: grid;
        grid-template-columns: repeat(5, minmax(150px, 1fr));
        gap: 12px;
        margin: 18px 0;
      }
      .cx-reports-kpi {
        border: 1px solid rgba(255,255,255,.13);
        background: rgba(255,255,255,.06);
        border-radius: 18px;
        padding: 14px;
        box-shadow: 0 18px 44px rgba(0,0,0,.16);
      }
      .cx-reports-kpi span {
        display: block;
        opacity: .72;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: .08em;
        margin-bottom: 7px;
      }
      .cx-reports-kpi strong {
        font-size: 24px;
        line-height: 1;
      }
      .cx-reports-chart-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(260px, 1fr));
        gap: 14px;
        margin: 18px 0;
      }
      .cx-reports-chart {
        border: 1px solid rgba(255,255,255,.12);
        background: rgba(255,255,255,.05);
        border-radius: 20px;
        padding: 16px;
        min-height: 210px;
      }
      .cx-reports-chart h3 {
        margin: 0 0 14px;
        font-size: 16px;
      }
      .cx-report-bar {
        display: grid;
        grid-template-columns: 120px 1fr 56px;
        gap: 10px;
        align-items: center;
        margin: 9px 0;
      }
      .cx-report-bar-label {
        font-size: 12px;
        opacity: .85;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .cx-report-bar-track {
        height: 12px;
        border-radius: 999px;
        background: rgba(255,255,255,.10);
        overflow: hidden;
      }
      .cx-report-bar-fill {
        height: 100%;
        border-radius: 999px;
        background: linear-gradient(90deg, rgba(0,255,136,.85), rgba(255,43,214,.85));
        min-width: 2px;
      }
      .cx-reports-tabs {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin: 18px 0 12px;
      }
      .cx-reports-tab {
        border: 1px solid rgba(255,255,255,.14);
        background: rgba(255,255,255,.06);
        color: inherit;
        border-radius: 999px;
        padding: 10px 13px;
        cursor: pointer;
        font-weight: 800;
      }
      .cx-reports-tab.active {
        background: rgba(0,255,136,.18);
        border-color: rgba(0,255,136,.35);
      }
      .cx-reports-table-wrap {
        width: 100%;
        overflow-x: auto;
        border: 1px solid rgba(255,255,255,.12);
        border-radius: 18px;
      }
      table.cx-reports-table {
        width: 100%;
        min-width: 1180px;
        border-collapse: collapse;
      }
      .cx-reports-table th,
      .cx-reports-table td {
        text-align: left;
        padding: 11px 12px;
        border-bottom: 1px solid rgba(255,255,255,.08);
        font-size: 13px;
        vertical-align: top;
      }
      .cx-reports-table th {
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: .08em;
        opacity: .78;
        background: rgba(255,255,255,.07);
        position: sticky;
        top: 0;
      }
      .cx-report-badge {
        display: inline-flex;
        border-radius: 999px;
        padding: 6px 9px;
        border: 1px solid rgba(255,255,255,.13);
        background: rgba(255,255,255,.07);
        font-weight: 800;
      }
      .cx-report-notice {
        margin-top: 14px;
        border: 1px solid rgba(255,255,255,.12);
        background: rgba(255,255,255,.06);
        border-radius: 16px;
        padding: 13px 14px;
      }
      .cx-report-notice.error { background: rgba(255,80,80,.16); }
      @media (max-width: 1200px) {
        .cx-reports-toolbar { grid-template-columns: 1fr; }
        .cx-reports-kpis { grid-template-columns: repeat(2, minmax(140px, 1fr)); }
        .cx-reports-chart-grid { grid-template-columns: 1fr; }
      }
    `;
    document.head.appendChild(style);
  }

  function reportsReadFilters() {
    const mode = document.querySelector("[data-reports-mode]")?.value || "general";
    const preset = document.querySelector("[data-reports-preset]")?.value || "7d";
    const startDate = document.querySelector("[data-reports-from]")?.value || "";
    const endDate = document.querySelector("[data-reports-to]")?.value || "";
    const employeeId = document.querySelector("[data-reports-employee]")?.value || "";
    const moduleCode = document.querySelector("[data-reports-module]")?.value || "";
    const status = document.querySelector("[data-reports-status]")?.value || "";
    const search = document.querySelector("[data-reports-search]")?.value || "";
    return { mode, preset, startDate, endDate, employeeId, moduleCode, status, search };
  }

  function reportsDefaultFilters() {
    return {
      mode: "general",
      preset: "7d",
      startDate: todayIso(-7),
      endDate: todayIso(0),
      employeeId: "",
      moduleCode: "",
      status: "",
      search: "",
    };
  }

  function reportsUrl(filters = reportsDefaultFilters()) {
    const companyId = companyIdFromUrl();
    const params = new URLSearchParams();
    params.set("preset", filters.preset || "7d");
    if (filters.startDate) params.set("start_date", filters.startDate);
    if (filters.endDate) params.set("end_date", filters.endDate);
    if (filters.employeeId) params.set("employee_id", filters.employeeId);
    if (filters.moduleCode) params.set("module", filters.moduleCode);
    if (filters.status) params.set("status", filters.status);
    if (filters.search) params.set("search", filters.search.trim());
    return `/reports/companies/${encodeURIComponent(companyId)}/general?${params.toString()}`;
  }

  async function loadReports(filters) {
    return api(reportsUrl(filters));
  }

  function chartBars(items = [], labelKey = "label", valueKey = "value") {
    const max = Math.max(1, ...items.map((item) => Number(item[valueKey] || 0)));
    if (!items.length) return `<div class="client-muted">Sin datos para graficar.</div>`;
    return items.map((item) => {
      const label = item[labelKey] ?? "-";
      const value = Number(item[valueKey] || 0);
      const pct = Math.max(2, Math.min(100, (value / max) * 100));
      return `
        <div class="cx-report-bar">
          <div class="cx-report-bar-label">${h(label)}</div>
          <div class="cx-report-bar-track"><div class="cx-report-bar-fill" style="width:${pct}%"></div></div>
          <div>${h(fmt(value))}</div>
        </div>
      `;
    }).join("");
  }

  function activityChart(items = []) {
    const prepared = items.map((item) => ({
      label: String(item.date || "").slice(5),
      value: Number(item.turnos || 0) + Number(item.gps || 0) + Number(item.materiales || 0),
    }));
    return chartBars(prepared);
  }

  function reportsCards(payload = {}) {
    const cards = Array.isArray(payload.cards) ? payload.cards : [];
    return `
      <div class="cx-reports-kpis">
        ${cards.map((card) => `
          <div class="cx-reports-kpi">
            <span>${h(card.label)}</span>
            <strong>${card.format === "money" ? h(fmtMoney(card.value)) : h(fmt(card.value))}</strong>
            <small>${h(card.module || "general")}</small>
          </div>
        `).join("")}
      </div>
    `;
  }

  function reportsCharts(payload = {}) {
    const charts = payload.charts || {};
    return `
      <div class="cx-reports-chart-grid">
        <div class="cx-reports-chart">
          <h3>Actividad por día</h3>
          ${activityChart(charts.activity_by_day || [])}
        </div>
        <div class="cx-reports-chart">
          <h3>Materiales por estado</h3>
          ${chartBars(charts.materials_by_status || [])}
        </div>
        <div class="cx-reports-chart">
          <h3>GPS</h3>
          ${chartBars(charts.gps_distribution || [])}
        </div>
        <div class="cx-reports-chart">
          <h3>Inventario crítico</h3>
          ${chartBars(charts.inventory_status || [])}
        </div>
        <div class="cx-reports-chart">
          <h3>Nómina</h3>
          ${chartBars(charts.payroll_breakdown || [])}
        </div>
        <div class="cx-reports-chart">
          <h3>Movimientos inventario</h3>
          ${chartBars(charts.inventory_movements || [])}
        </div>
      </div>
    `;
  }

  function employeeOptions(payload = {}, selected = "") {
    const rows = payload.details?.employee_summary || [];
    return `
      <option value="">Todos</option>
      ${rows.map((row) => {
        const value = row.employee_id || "";
        if (!value) return "";
        return `<option value="${h(value)}" ${String(selected) === String(value) ? "selected" : ""}>${h(row.employee_name || "Sin nombre")}</option>`;
      }).join("")}
    `;
  }

  function reportsToolbar(filters, payload) {
    return `
      <div class="cx-reports-toolbar">
        <label class="cx-reports-field">
          <span>Tipo</span>
          <select data-reports-mode>
            <option value="general" ${filters.mode === "general" ? "selected" : ""}>General</option>
            <option value="employee" ${filters.mode === "employee" ? "selected" : ""}>Por persona</option>
          </select>
        </label>
        <label class="cx-reports-field">
          <span>Desde</span>
          <input type="date" value="${h(filters.startDate || "")}" data-reports-from>
        </label>
        <label class="cx-reports-field">
          <span>Hasta</span>
          <input type="date" value="${h(filters.endDate || "")}" data-reports-to>
        </label>
        <label class="cx-reports-field">
          <span>Periodo</span>
          <select data-reports-preset>
            <option value="today" ${filters.preset === "today" ? "selected" : ""}>Hoy</option>
            <option value="7d" ${filters.preset === "7d" ? "selected" : ""}>7 días</option>
            <option value="15d" ${filters.preset === "15d" ? "selected" : ""}>15 días</option>
            <option value="month" ${filters.preset === "month" ? "selected" : ""}>Mes</option>
            <option value="custom" ${filters.preset === "custom" ? "selected" : ""}>Personalizado</option>
          </select>
        </label>
        <label class="cx-reports-field">
          <span>Empleado</span>
          <select data-reports-employee>
            ${employeeOptions(payload, filters.employeeId)}
          </select>
        </label>
        <label class="cx-reports-field">
          <span>Lupa inteligente</span>
          <input type="search" placeholder="Buscar empleado, MAT, GPS, stock, nómina..." value="${h(filters.search || "")}" data-reports-search>
        </label>
        <button class="client-btn" type="button" data-reports-generate>Generar</button>
        <button class="client-btn" type="button" data-reports-export>CSV</button>
        <button class="client-btn" type="button" data-reports-dashboard>Volver</button>
      </div>
      <div class="cx-reports-toolbar" style="grid-template-columns: 180px 180px 1fr; margin-top:10px">
        <label class="cx-reports-field">
          <span>Módulo</span>
          <select data-reports-module>
            <option value="">Todos</option>
            <option value="workforce" ${filters.moduleCode === "workforce" ? "selected" : ""}>Workforce</option>
            <option value="gps" ${filters.moduleCode === "gps" ? "selected" : ""}>GPS</option>
            <option value="materials" ${filters.moduleCode === "materials" ? "selected" : ""}>Materiales</option>
            <option value="inventory" ${filters.moduleCode === "inventory" ? "selected" : ""}>Inventario</option>
            <option value="payroll" ${filters.moduleCode === "payroll" ? "selected" : ""}>Nómina</option>
          </select>
        </label>
        <label class="cx-reports-field">
          <span>Estado</span>
          <input type="text" placeholder="delivered, returned, outside..." value="${h(filters.status || "")}" data-reports-status>
        </label>
        <div class="client-muted" style="align-self:end">Reporte general consolida toda la empresa. Por persona filtra al colaborador seleccionado.</div>
      </div>
    `;
  }

  const tableConfigs = {
    employee_summary: {
      title: "Resumen por empleado",
      columns: [
        ["employee_name", "Empleado"],
        ["employee_role", "Rol"],
        ["turnos", "Turnos"],
        ["eventos", "Eventos"],
        ["gps", "GPS"],
        ["gps_fuera", "GPS fuera"],
        ["materiales", "Materiales"],
        ["material_devuelto", "Devueltos"],
        ["consignas", "Consignas"],
        ["horas_ordinarias", "Horas ord."],
        ["horas_extra", "Horas extra"],
        ["total_nómina", "Total nómina"],
        ["alertas", "Alertas"],
      ],
    },
    materials: {
      title: "Materiales",
      columns: [
        ["order_number", "Orden"],
        ["employee_name", "Solicitante"],
        ["material_name", "Material"],
        ["quantity", "Cantidad"],
        ["quantity_returned", "Devuelto"],
        ["status", "Estado"],
        ["destination", "Destino"],
        ["requested_at", "Solicitud"],
        ["delivered_at", "Entrega"],
        ["returned_at", "Devolución"],
        ["notes", "Notas"],
      ],
    },
    inventory_items: {
      title: "Inventario",
      columns: [
        ["name_reference", "Referencia"],
        ["sku", "SKU"],
        ["item_size", "Tamaño"],
        ["color", "Color"],
        ["current_stock", "Stock actual"],
        ["min_stock", "Mínimo"],
        ["status", "Estado"],
        ["updated_at", "Actualizado"],
      ],
    },
    gps: {
      title: "GPS",
      columns: [
        ["employee_name", "Empleado"],
        ["employee_role", "Rol"],
        ["gps_status", "Estado GPS"],
        ["occurred_at", "Fecha/Hora"],
        ["detail", "Detalle"],
        ["status", "Estado"],
      ],
    },
    payroll: {
      title: "Nómina",
      columns: [
        ["employee_name", "Empleado"],
        ["employee_role", "Rol"],
        ["closed_shifts", "Turnos cerrados"],
        ["regular_minutes", "Min. ordinarios"],
        ["extra_minutes", "Min. extra"],
        ["gross_amount", "Bruto"],
        ["discount_amount", "Descuentos"],
        ["net_amount", "Neto"],
      ],
    },
    attendance: {
      title: "Asistencia / Bitácora",
      columns: [
        ["occurred_at", "Fecha/Hora"],
        ["employee_name", "Empleado"],
        ["employee_role", "Rol"],
        ["event_type", "Evento"],
        ["source_channel", "Canal"],
        ["module_code", "Módulo"],
        ["status", "Estado"],
        ["detail", "Detalle"],
      ],
    },
  };

  function tableValue(row, key) {
    if (key.endsWith("_at") || key === "occurred_at" || key === "created_at" || key === "updated_at") return fmtDate(row[key]);
    if (["gross_amount", "discount_amount", "net_amount", "total_nómina"].includes(key)) return fmtMoney(row[key]);
    return fmt(row[key]);
  }

  function reportsTabs(active = "employee_summary") {
    return `
      <div class="cx-reports-tabs">
        ${Object.entries(tableConfigs).map(([key, cfg]) => `
          <button class="cx-reports-tab ${key === active ? "active" : ""}" type="button" data-reports-tab="${h(key)}">${h(cfg.title)}</button>
        `).join("")}
      </div>
    `;
  }

  function reportsTable(payload = {}, active = "employee_summary") {
    const cfg = tableConfigs[active] || tableConfigs.employee_summary;
    const rows = payload.details?.[active] || [];
    return `
      <div class="cx-reports-table-wrap">
        <table class="cx-reports-table">
          <thead>
            <tr>${cfg.columns.map(([, label]) => `<th>${h(label)}</th>`).join("")}</tr>
          </thead>
          <tbody>
            ${rows.length ? rows.map((row) => `
              <tr>
                ${cfg.columns.map(([key]) => `<td>${key === "status" || key === "gps_status" ? `<span class="cx-report-badge">${h(tableValue(row, key))}</span>` : h(tableValue(row, key))}</td>`).join("")}
              </tr>
            `).join("") : `
              <tr><td colspan="${cfg.columns.length}">Sin datos para los filtros seleccionados.</td></tr>
            `}
          </tbody>
        </table>
      </div>
    `;
  }

  function reportWarnings(payload = {}, loadError = "") {
    const errors = Array.isArray(payload.errors) ? payload.errors : [];
    if (loadError) return `<div class="cx-report-notice error">${h(loadError)}</div>`;
    if (!errors.length) return "";
    return `<div class="cx-report-notice">Algunos bloques no tenían datos o no aplican: ${errors.map((e) => h(e.module)).join(", ")}</div>`;
  }

  async function renderReports(filters = null, activeTab = "employee_summary") {
    reportStyles();
    const app = document.getElementById("app");
    if (!app) return;

    const companyId = companyIdFromUrl();
    const nextFilters = filters || reportsDefaultFilters();

    let payload = {};
    let loadError = "";

    try {
      payload = await loadReports(nextFilters);
    } catch (error) {
      loadError = error.message || "No se pudo cargar Reportes.";
      payload = { details: {}, charts: {}, cards: [], errors: [] };
    }

    window.__cxReportsPayload = payload;
    window.__cxReportsFilters = nextFilters;
    window.__cxReportsActivoTab = activeTab;

    const titleMode = nextFilters.employeeId ? "Reporte por persona" : "Reporte general";

    app.innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo"><strong>CLONEXA</strong></div>
            <h2 class="client-company-name">Reportes</h2>
            <div class="client-muted">${h(companyId || "tenant")}</div>
            <nav class="client-nav">
              <button type="button" data-reports-dashboard>Dashboard</button>
              <button class="active" type="button">Reportes</button>
              <button type="button" data-reports-kpis>KPIs</button>
            </nav>
            <div class="client-footer-id">
              <strong>Tenant activo</strong><br>
              ${h(companyId || "")}
            </div>
          </aside>

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">Módulo Reportes</div>
              <h1 class="client-title">${h(titleMode)}</h1>
              <p class="client-muted">Histórico consolidado de Personal, GPS, Materiales, Inventario y Nómina. No modifica datos; solo audita y exporta.</p>
              ${reportsToolbar(nextFilters, payload)}
              ${reportWarnings(payload, loadError)}
            </header>

            <section class="client-panel">
              <div class="client-eyebrow">Resumen ejecutivo</div>
              <h2>Indicadores del periodo</h2>
              ${reportsCards(payload)}
              ${reportsCharts(payload)}
            </section>

            <section class="client-panel" style="margin-top:18px">
              <div class="client-eyebrow">Detalle operativo</div>
              <h2>Tablas auditables</h2>
              ${reportsTabs(activeTab)}
              ${reportsTable(payload, activeTab)}
            </section>
          </section>
        </div>
      </main>
    `;
  }

  async function exportReportsCsv() {
    const filters = window.__cxReportsFilters || reportsReadFilters();
    const companyId = companyIdFromUrl();
    const params = new URLSearchParams();
    params.set("preset", filters.preset || "7d");
    if (filters.startDate) params.set("start_date", filters.startDate);
    if (filters.endDate) params.set("end_date", filters.endDate);
    if (filters.employeeId) params.set("employee_id", filters.employeeId);
    if (filters.moduleCode) params.set("module", filters.moduleCode);
    if (filters.status) params.set("status", filters.status);
    if (filters.search) params.set("search", filters.search.trim());

    const res = await fetch(`${API}/reports/companies/${encodeURIComponent(companyId)}/export.csv?${params.toString()}`);
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${res.status} ${text}`);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `clonexa_reporte_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  document.addEventListener("click", async (event) => {
    const reportModule = event.target.closest('[data-client-module="reports"], [data-reports-open]');
    if (reportModule) {
      event.preventDefault();
      event.stopImmediatePropagation();
      await renderReports();
      return;
    }
  }, true);

  document.addEventListener("click", async (event) => {
    if (event.target.closest("[data-reports-dashboard]")) {
      window.location.href = `/client?company_id=${encodeURIComponent(companyIdFromUrl())}`;
      return;
    }

    if (event.target.closest("[data-reports-kpis]")) {
      const kpiBtn = document.querySelector('[data-client-module="kpis"]');
      if (kpiBtn) kpiBtn.click();
      return;
    }

    if (event.target.closest("[data-reports-generate]")) {
      const filters = reportsReadFilters();
      if (filters.mode === "employee" && !filters.employeeId) {
        const search = document.querySelector("[data-reports-search]");
        if (search) search.placeholder = "Selecciona empleado para reporte por persona";
      }
      await renderReports(filters, window.__cxReportsActivoTab || "employee_summary");
      return;
    }

    if (event.target.closest("[data-reports-export]")) {
      try {
        await exportReportsCsv();
      } catch (error) {
        const box = document.querySelector(".client-hero");
        if (box) box.insertAdjacentHTML("beforeend", `<div class="cx-report-notice error">${h(error.message || "No se pudo exportar CSV.")}</div>`);
      }
      return;
    }

    const tab = event.target.closest("[data-reports-tab]");
    if (tab) {
      await renderReports(window.__cxReportsFilters || reportsReadFilters(), tab.dataset.reportsTab || "employee_summary");
      return;
    }
  });

  document.addEventListener("keydown", async (event) => {
    if (event.key !== "Enter") return;
    const input = event.target.closest("[data-reports-search]");
    if (!input) return;
    event.preventDefault();
    await renderReports(reportsReadFilters(), window.__cxReportsActivoTab || "employee_summary");
  });
})();
/* CX_REPORTS_016B_END */



/* CLONEXA 020A-1 CLIENT ACCOUNT SESSION LAYER */
(function clonexaClientAccountSessionLayer() {
  "use strict";

  const TOKEN_KEY = "clonexa_access_token";
  const COMPANY_KEY = "clonexa_company_id";
  const LEGACY_COMPANY_KEY = "company_id";

  const TEXT = {
    es: {
      settings: "Configuración",
      logout: "Salir",
      title: "Configuración de cuenta",
      firstLogin: "Primer ingreso: cambia tu contraseña",
      account: "Cuenta",
      email: "Correo",
      newEmail: "Nuevo correo",
      currentPassword: "Contraseña actual",
      newPassword: "Nueva contraseña",
      confirmPassword: "Confirmar contraseña",
      language: "Idioma",
      session: "Sesión",
      timeout: "Tiempo de ventana abierta",
      save: "Guardar cambios",
      close: "Cerrar",
      saved: "Configuración guardada.",
      passwordRequired: "Debes cambiar la contraseña para continuar.",
      sessionExpired: "Sesión expirada por inactividad.",
      adminHint: "Panel cliente CLONEXA",
      passwordHelp: "Deja nueva contraseña vacía si no deseas cambiarla.",
      emailHelp: "Deja nuevo correo vacío si no deseas cambiarlo."
    },
    en: {
      settings: "Ajustes",
      logout: "Cerrar sesión",
      title: "Account settings",
      firstLogin: "First login: change your password",
      account: "Account",
      email: "Email",
      newEmail: "New email",
      currentPassword: "Current password",
      newPassword: "New password",
      confirmPassword: "Confirm password",
      language: "Language",
      session: "Session",
      timeout: "Open session window",
      save: "Save changes",
      close: "Close",
      saved: "Ajustes saved.",
      passwordRequired: "You must change your password to continue.",
      sessionExpired: "Session expired due to inactivity.",
      adminHint: "CLONEXA client panel",
      passwordHelp: "Leave new password empty if you do not want to change it.",
      emailHelp: "Leave new email empty if you do not want to change it."
    },
    fr: {
      settings: "Configuration",
      logout: "Quitter",
      title: "Configuration du compte",
      firstLogin: "Première connexion : changez votre mot de passe",
      account: "Compte",
      email: "E-mail",
      newEmail: "Nouvel e-mail",
      currentPassword: "Mot de passe actuel",
      newPassword: "Nouveau mot de passe",
      confirmPassword: "Confirmer le mot de passe",
      language: "Langue",
      session: "Session",
      timeout: "Fenêtre de session ouverte",
      save: "Enregistrer",
      close: "Fermer",
      saved: "Configuration enregistrée.",
      passwordRequired: "Vous devez changer votre mot de passe pour continuer.",
      sessionExpired: "Session expirée pour inactivité.",
      adminHint: "Panneau client CLONEXA",
      passwordHelp: "Laissez le nouveau mot de passe vide si vous ne souhaitez pas le changer.",
      emailHelp: "Laissez le nouvel e-mail vide si vous ne souhaitez pas le changer."
    }
  };

  let account = null;
  let idleTimer = null;
  let forced = false;

  function token() {
    return localStorage.getItem(TOKEN_KEY) || "";
  }

  function companyId() {
    const params = new URLSearchParams(window.location.search);
    return (
      params.get("company_id") ||
      params.get("companyId") ||
      localStorage.getItem(COMPANY_KEY) ||
      localStorage.getItem(LEGACY_COMPANY_KEY) ||
      ""
    );
  }

  function lang() {
    const value = (account && account.language) || localStorage.getItem("clonexa_client_language") || "es";
    return ["es", "en", "fr"].includes(value) ? value : "es";
  }

  function t(key) {
    const pack = TEXT[lang()] || TEXT.es;
    return pack[key] || TEXT.es[key] || key;
  }

  function headers() {
    return {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token()}`
    };
  }

  async function accountApi(path, options) {
    const response = await fetch(`/api/v1/auth${path}`, Object.assign({
      headers: headers()
    }, options || {}));

    let data = {};
    try {
      data = await response.json();
    } catch (_) {
      data = {};
    }

    if (!response.ok) {
      throw new Error(data.detail || data.message || `HTTP ${response.status}`);
    }

    return data;
  }

  function installStyles() {
    if (document.getElementById("clx-account-layer-style")) return;

    const style = document.createElement("style");
    style.id = "clx-account-layer-style";
    style.textContent = `
      .clx-account-bar {
        position: fixed;
        top: 14px;
        right: 14px;
        z-index: 99980;
        display: flex;
        gap: 8px;
        align-items: center;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      .clx-account-pill {
        background: rgba(15, 23, 42, 0.92);
        color: #fff;
        border: 1px solid rgba(255,255,255,0.14);
        border-radius: 999px;
        padding: 9px 13px;
        font-size: 13px;
        box-shadow: 0 12px 30px rgba(0,0,0,0.18);
        cursor: pointer;
      }
      .clx-account-pill.secondary {
        background: rgba(255,255,255,0.96);
        color: #0f172a;
        border-color: rgba(15,23,42,0.12);
      }
      .clx-account-overlay {
        position: fixed;
        inset: 0;
        z-index: 99990;
        background: rgba(15, 23, 42, 0.52);
        display: none;
        align-items: center;
        justify-content: center;
        padding: 24px;
      }
      .clx-account-overlay.open {
        display: flex;
      }
      .clx-account-modal {
        width: min(560px, 96vw);
        max-height: 92vh;
        overflow: auto;
        background: #fff;
        color: #0f172a;
        border-radius: 24px;
        box-shadow: 0 30px 80px rgba(0,0,0,0.35);
        padding: 24px;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      .clx-account-modal h2 {
        margin: 0 0 4px;
        font-size: 22px;
      }
      .clx-account-muted {
        color: #64748b;
        font-size: 13px;
        margin: 0 0 18px;
      }
      .clx-account-grid {
        display: grid;
        grid-template-columns: 1fr;
        gap: 12px;
      }
      .clx-account-grid label {
        display: grid;
        gap: 6px;
        font-size: 13px;
        font-weight: 700;
      }
      .clx-account-grid input,
      .clx-account-grid select {
        width: 100%;
        border: 1px solid #cbd5e1;
        border-radius: 12px;
        padding: 11px 12px;
        font-size: 14px;
      }
      .clx-account-section {
        border: 1px solid #e2e8f0;
        border-radius: 18px;
        padding: 16px;
        margin-top: 14px;
      }
      .clx-account-section h3 {
        margin: 0 0 10px;
        font-size: 15px;
      }
      .clx-account-actions {
        display: flex;
        gap: 10px;
        justify-content: flex-end;
        margin-top: 18px;
      }
      .clx-account-btn {
        border: 0;
        border-radius: 12px;
        padding: 11px 14px;
        font-weight: 800;
        cursor: pointer;
      }
      .clx-account-btn.primary {
        background: #111827;
        color: #fff;
      }
      .clx-account-btn.ghost {
        background: #f1f5f9;
        color: #0f172a;
      }
      .clx-account-status {
        margin-top: 12px;
        font-size: 13px;
        color: #166534;
      }
      .clx-account-status.error {
        color: #b91c1c;
      }
      .clx-account-forced .clx-account-close {
        display: none;
      }
    `;
    document.head.appendChild(style);
  }

  function renderShell() {
    if (document.getElementById("clx-account-bar")) return;

    const bar = document.createElement("div");
    bar.id = "clx-account-bar";
    bar.className = "clx-account-bar";
    bar.innerHTML = `
      <button type="button" class="clx-account-pill secondary" id="clxAccountAjustesBtn">⚙ ${t("settings")}</button>
      <button type="button" class="clx-account-pill" id="clxAccountLogoutBtn">⏻ ${t("logout")}</button>
    `;
    document.body.appendChild(bar);

    const overlay = document.createElement("div");
    overlay.id = "clx-account-overlay";
    overlay.className = "clx-account-overlay";
    overlay.innerHTML = `
      <div class="clx-account-modal" id="clx-account-modal">
        <h2 id="clxAccountTitle">${t("title")}</h2>
        <p class="clx-account-muted" id="clxAccountSubtitle">${t("adminHint")}</p>

        <div class="clx-account-section">
          <h3>${t("account")}</h3>
          <div class="clx-account-grid">
            <label>
              ${t("email")}
              <input id="clxAccountEmail" type="email" disabled>
            </label>
            <p class="clx-account-muted">${t("emailHelp")}</p>
            <label>
              ${t("newEmail")}
              <input id="clxAccountNewEmail" type="email" autocomplete="email">
            </label>
          </div>
        </div>

        <div class="clx-account-section">
          <h3>${t("session")}</h3>
          <div class="clx-account-grid">
            <label>
              ${t("language")}
              <select id="clxAccountLanguage">
                <option value="es">Español</option>
                <option value="en">English</option>
                <option value="fr">Français</option>
              </select>
            </label>
            <label>
              ${t("timeout")}
              <select id="clxAccountTimeout">
                <option value="15">15 min</option>
                <option value="30">30 min</option>
                <option value="60">60 min</option>
              </select>
            </label>
          </div>
        </div>

        <div class="clx-account-section">
          <h3>${t("newPassword")}</h3>
          <p class="clx-account-muted">${t("passwordHelp")}</p>
          <div class="clx-account-grid">
            <label>
              ${t("currentPassword")}
              <input id="clxAccountCurrentPassword" type="password" autocomplete="current-password">
            </label>
            <label>
              ${t("newPassword")}
              <input id="clxAccountNewPassword" type="password" autocomplete="new-password">
            </label>
            <label>
              ${t("confirmPassword")}
              <input id="clxAccountConfirmPassword" type="password" autocomplete="new-password">
            </label>
          </div>
        </div>

        <div id="clxAccountStatus" class="clx-account-status"></div>

        <div class="clx-account-actions">
          <button type="button" class="clx-account-btn ghost clx-account-close" id="clxAccountCloseBtn">${t("close")}</button>
          <button type="button" class="clx-account-btn primary" id="clxAccountSaveBtn">${t("save")}</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    document.getElementById("clxAccountAjustesBtn").addEventListener("click", () => openAjustes(false));
    document.getElementById("clxAccountLogoutBtn").addEventListener("click", () => logout("manual"));
    document.getElementById("clxAccountCloseBtn").addEventListener("click", closeAjustes);
    document.getElementById("clxAccountSaveBtn").addEventListener("click", saveAjustes);
  }

  function refreshTexts() {
    const settingsBtn = document.getElementById("clxAccountAjustesBtn");
    const logoutBtn = document.getElementById("clxAccountLogoutBtn");
    if (settingsBtn) settingsBtn.textContent = `⚙ ${t("settings")}`;
    if (logoutBtn) logoutBtn.textContent = `⏻ ${t("logout")}`;
    document.documentElement.lang = lang();
  }

  function fillForm() {
    if (!account) return;
    const email = document.getElementById("clxAccountEmail");
    const newEmail = document.getElementById("clxAccountNewEmail");
    const langEl = document.getElementById("clxAccountLanguage");
    const timeoutEl = document.getElementById("clxAccountTimeout");
    const status = document.getElementById("clxAccountStatus");

    if (email) email.value = account.email || "";
    if (newEmail) newEmail.value = "";
    if (langEl) langEl.value = account.language || "es";
    if (timeoutEl) timeoutEl.value = String(account.session_timeout_minutes || 30);
    if (status) {
      status.textContent = "";
      status.classList.remove("error");
    }
  }

  function openAjustes(force) {
    forced = Boolean(force);
    const overlay = document.getElementById("clx-account-overlay");
    const modal = document.getElementById("clx-account-modal");
    const title = document.getElementById("clxAccountTitle");
    const subtitle = document.getElementById("clxAccountSubtitle");

    if (!overlay || !modal) return;

    fillForm();

    modal.classList.toggle("clx-account-forced", forced);
    if (title) title.textContent = forced ? t("firstLogin") : t("title");
    if (subtitle) subtitle.textContent = forced ? t("passwordRequired") : t("adminHint");

    overlay.classList.add("open");
  }

  function closeAjustes() {
    if (forced) return;
    const overlay = document.getElementById("clx-account-overlay");
    if (overlay) overlay.classList.remove("open");
  }

  function setStatus(message, isError) {
    const status = document.getElementById("clxAccountStatus");
    if (!status) return;
    status.textContent = message || "";
    status.classList.toggle("error", Boolean(isError));
  }

  async function saveAjustes() {
    try {
      setStatus("", false);

      const currentPassword = document.getElementById("clxAccountCurrentPassword").value || "";
      const newPassword = document.getElementById("clxAccountNewPassword").value || "";
      const confirmPassword = document.getElementById("clxAccountConfirmPassword").value || "";
      const newEmail = (document.getElementById("clxAccountNewEmail").value || "").trim();
      const language = document.getElementById("clxAccountLanguage").value || "es";
      const sessionTimeout = Number(document.getElementById("clxAccountTimeout").value || 30);

      account = await accountApi("/account/preferences", {
        method: "PATCH",
        body: JSON.stringify({
          language: language,
          session_timeout_minutes: sessionTimeout
        })
      });

      localStorage.setItem("clonexa_client_language", account.language || "es");

      if (newEmail) {
        if (!currentPassword) throw new Error(t("currentPassword"));
        account = await accountApi("/account/email", {
          method: "PATCH",
          body: JSON.stringify({
            current_password: currentPassword,
            new_email: newEmail
          })
        });
      }

      if (newPassword || confirmPassword || forced) {
        if (!currentPassword) throw new Error(t("currentPassword"));
        account = await accountApi("/account/password", {
          method: "PATCH",
          body: JSON.stringify({
            current_password: currentPassword,
            new_password: newPassword,
            confirm_password: confirmPassword
          })
        });
      }

      refreshTexts();
      configureIdleTimeout();
      fillForm();
      setStatus(t("saved"), false);

      if (!account.must_change_password && !account.temporary_password) {
        forced = false;
        setTimeout(closeAjustes, 700);
      }
    } catch (error) {
      setStatus(error.message || String(error), true);
    }
  }

  async function logout(reason) {
    try {
      if (token()) {
        await accountApi("/logout", { method: "POST", body: JSON.stringify({}) });
      }
    } catch (_) {}

    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem("clonexa_login_payload");
    localStorage.removeItem("clonexa_company_id");
    localStorage.removeItem("company_id");

    if (reason === "timeout") {
      localStorage.setItem("clonexa_logout_reason", t("sessionExpired"));
    }

    window.location.href = "/login";
  }

  function configureIdleTimeout() {
    if (idleTimer) clearTimeout(idleTimer);

    const minutes = Number((account && account.session_timeout_minutes) || 30);
    const ms = minutes * 60 * 1000;

    const reset = () => {
      if (idleTimer) clearTimeout(idleTimer);
      idleTimer = setTimeout(() => logout("timeout"), ms);
    };

    ["click", "keydown", "scroll", "mousemove", "touchstart"].forEach((eventName) => {
      window.removeEventListener(eventName, reset, { passive: true });
      window.addEventListener(eventName, reset, { passive: true });
    });

    reset();
  }

  async function init() {
    if (!token()) return;

    installStyles();
    renderShell();

    try {
      account = await accountApi("/account", { method: "GET" });
      localStorage.setItem("clonexa_client_language", account.language || "es");
      localStorage.setItem("clonexa_company_id", account.company_id || companyId());
      localStorage.setItem("company_id", account.company_id || companyId());

      refreshTexts();
      configureIdleTimeout();

      if (account.must_change_password || account.temporary_password) {
        openAjustes(true);
      }
    } catch (error) {
      console.warn("CLONEXA account layer disabled:", error);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
