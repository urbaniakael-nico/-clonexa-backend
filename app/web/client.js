
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

  // CX_019E_INVENTORY_INVOICE_FRONTEND_START
  async function apiForm(path, formData, options = {}) {
    const res = await fetch(`${API}${path}`, {
      method: options.method || "POST",
      body: formData,
      ...(options.fetchOptions || {}),
    });

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${res.status} ${res.statusText} ${text}`);
    }

    return res.json();
  }
  // CX_019E_INVENTORY_INVOICE_FRONTEND_END


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
    mini_panel: ["Mini Paneles", "links operativos", "MIN"],
    mini_paneles: ["Mini Paneles", "links operativos", "MIN"],
    creacion_minipanel: ["Mini Paneles", "links operativos", "MIN"],
    creacion_mini_panel: ["Mini Paneles", "links operativos", "MIN"],
  };


  const CLIENT_HIDDEN_MODULE_CODES = new Set([
    "core",
    "settings",
    "setting",
    "configuration",
    "configuracion",
    "configuración",
    "ajustes",
    "account",
    "preferences"
  ]);

  function normalizeClientModuleCode(code = "") {
    return String(code || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .trim()
      .toLowerCase();
  }

  function isClientHiddenModuleCode(code = "") {
    return CLIENT_HIDDEN_MODULE_CODES.has(normalizeClientModuleCode(code));
  }

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

  /* CX_017H_HIDE_CORE_SETTINGS_MODULE_START */
  const CX_HIDDEN_CLIENT_MODULE_CODES_017H = new Set([
    "core",
    "settings",
    "core_settings",
    "settings_core",
    "client_settings",
    "tenant_settings",
    "company_settings",
    "configuration",
    "config",
    "configuracion",
    "ajustes"
  ]);

  function cxNormalizeModuleToken017H(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
  }

  function cxIsHiddenClientModule017H(item = {}) {
    const raw = item.raw || {};
    const rawModule = raw.module && typeof raw.module === "object" ? raw.module : {};

    const tokens = [
      item.code,
      item.title,
      item.name,
      raw.code,
      raw.module_code,
      raw.name,
      raw.title,
      rawModule.code,
      rawModule.module_code,
      rawModule.name,
      rawModule.title
    ]
      .map(cxNormalizeModuleToken017H)
      .filter(Boolean);

    return tokens.some((token) =>
      CX_HIDDEN_CLIENT_MODULE_CODES_017H.has(token) ||
      token.includes("core_settings") ||
      token.includes("tenant_settings") ||
      token.includes("company_settings")
    );
  }

  function visibleClientModules(modules = activeClientModules()) {
    return (Array.isArray(modules) ? modules : []).filter((item) => !cxIsHiddenClientModule017H(item));
  }

  function isClientModuleActive(code) {
    const normalized = String(code || "").trim();

    if (!normalized || cxIsHiddenClientModule017H({ code: normalized })) {
      return false;
    }

    return activeClientModules().some((module) =>
      module.code === normalized &&
      module.enabled &&
      !cxIsHiddenClientModule017H(module)
    );
  }
  /* CX_017H_HIDE_CORE_SETTINGS_MODULE_END */


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

    if (typeof cxClientHasUniversalModule021D === "function" && cxClientHasUniversalModule021D(CX_UNIVERSAL_QUOTES_CODES_021D)) {
      actions.push({ label: "Cotizaciones", action: "quotes:open" });
    }

    if (typeof cxClientHasUniversalModule021D === "function" && cxClientHasUniversalModule021D(CX_UNIVERSAL_NOTES_CODES_021D)) {
      actions.push({ label: "Notas / Agenda", action: "notes:open" });
    }

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
    if (code === "channels") return isClientModuleActive("bots") && crm.bot?.configured ? "ON" : "OFF";

    const count = (crm.todayEvents || [])
      .filter((event) => String(event.module_code || "workforce").toLowerCase() === code)
      .length;

    if (count > 0) return count;

    return isClientModuleActive(code) ? "ON" : "-";
  }

  async function loadClientCrmDataLegacy018B() {
    const companyId = state.companyId;
    const [employeesResult, eventsResult, botResult, gpsResult] = await Promise.allSettled([
      isClientModuleActive("workforce")
        ? api(`/employees?company_id=${encodeURIComponent(companyId)}&include_archived=true`)
        : Promise.resolve([]),
      api(`/employees/attendance/history?company_id=${encodeURIComponent(companyId)}&limit=200`),
      isClientModuleActive("bots")
        ? api(`/bots/companies/${encodeURIComponent(companyId)}/telegram`)
        : Promise.resolve(null),
      isClientModuleActive("gps")
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

  
  /* CX_018B_CRM_ADAPTIVE_SINGLE_CONTEXT_START */
  const CX_CRM_TOP_MODULE_PRIORITY_018B = [
    "production",
    "references",
    "gps",
    "materials",
    "field",
    "requests",
    "orders",
    "inventory",
    "stock",
    "retail",
    "stores",
    "hospitality",
    "bots",
    "payroll"
  ];

  const CX_CRM_CONTEXT_MODULE_PRIORITY_018B = [
    "production",
    "references",
    "gps",
    "materials",
    "field",
    "requests",
    "orders",
    "retail",
    "stores",
    "hospitality",
    "bots",
    "payroll"
  ];

  let cxCrmRealtimeTimer018B = null;

  function cxCrmNormalizeCode018B(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
  }

  function cxCrmActiveModuleSet018B() {
    return clientModuleCodes(visibleClientModules(activeClientModules()));
  }

  function crmPickSummaryModules018B(crm = {}) {
    const active = cxCrmActiveModuleSet018B();
    const snapshotModules = new Set((crm.activeModules || crm.snapshot?.active_modules || []).map(cxCrmNormalizeCode018B));

    const has = (code) => active.has(code) || snapshotModules.has(code);
    const selected = [];

    CX_CRM_TOP_MODULE_PRIORITY_018B.forEach((code) => {
      if (selected.length >= 2) return;

      if (code === "references") {
        if ((has("production") || has("references")) && !selected.includes("production")) {
          selected.push("production");
        }
        return;
      }

      if (code === "bots") {
        if ((has("bots") || has("bot")) && !selected.includes("bots")) selected.push("bots");
        return;
      }

      if (has(code) && !selected.includes(code)) selected.push(code);
    });

    while (selected.length < 2) {
      selected.push(selected.length === 0 ? "modules" : "channels");
    }

    return selected.slice(0, 2);
  }

  function crmTopCardValue018B(code, crm = {}) {
    const summary = crm.summary || crm.snapshot?.summary || {};

    if (code === "modules") return `${visibleClientModules(activeClientModules()).length}`;
    if (code === "channels") return isClientModuleActive("bots") && crm.bot?.configured ? "ON" : "OFF";
    if (code === "production") return summary.with_reference !== undefined ? String(summary.with_reference) : crmTopCardValue(code, crm);
    if (code === "gps") return summary.gps_inside !== undefined ? String(summary.gps_inside) : crmTopCardValue(code, crm);
    if (code === "materials") return summary.materials_pending !== undefined ? String(summary.materials_pending) : crmTopCardValue(code, crm);

    return crmTopCardValue(code, crm);
  }

  function crmParseSeconds018B(value) {
    const n = Number(value || 0);
    return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
  }

  function crmDateToMs018B(value) {
    if (!value) return 0;
    const ms = new Date(value).getTime();
    return Number.isFinite(ms) ? ms : 0;
  }

  function crmNormalizeStatus018B(status) {
    const value = cxCrmNormalizeCode018B(status);
    if (["working", "trabajando", "activo", "active"].includes(value)) return "working";
    if (["on_break", "break", "pause", "pausa", "en_pausa"].includes(value)) return "on_break";
    if (["checked_out", "finished", "finalizado", "turno_finalizado", "salida", "out"].includes(value)) return "checked_out";
    return "not_started";
  }

  function crmStatusTone018B(status) {
    const normalized = crmNormalizeStatus018B(status);
    if (normalized === "working") return "active";
    if (normalized === "on_break") return "pause";
    if (normalized === "checked_out") return "out";
    return "idle";
  }

  function crmSingleContextCode018B(person = {}, moduleCodes = []) {
    const active = cxCrmActiveModuleSet018B();
    const personAdapters = new Set((person.adapters || []).map((adapter) => cxCrmNormalizeCode018B(adapter.code || adapter.module || adapter.title)));

    const available = (code) => {
      if (code === "production") {
        return active.has("production") || active.has("references") || personAdapters.has("production") || personAdapters.has("production_references");
      }

      if (code === "gps") return active.has("gps") || personAdapters.has("gps") || !!person.gpsInfo;
      return active.has(code) || personAdapters.has(code);
    };

    const ordered = [
      ...CX_CRM_CONTEXT_MODULE_PRIORITY_018B,
      ...(Array.isArray(moduleCodes) ? moduleCodes : [])
    ].map((code) => code === "references" ? "production" : cxCrmNormalizeCode018B(code));

    return ordered.find((code, index) => code && ordered.indexOf(code) === index && available(code)) || "";
  }

  function crmFindAdapter018B(person = {}, code = "") {
    const wanted = cxCrmNormalizeCode018B(code);
    return (person.adapters || []).find((adapter) => {
      const adapterCode = cxCrmNormalizeCode018B(adapter.code || adapter.module || adapter.title);
      if (wanted === "production") return adapterCode === "production" || adapterCode === "production_references";
      return adapterCode === wanted;
    }) || null;
  }

  function crmFormatSeconds018B(seconds) {
    return crmDurationLabel(crmParseSeconds018B(seconds) * 1000);
  }

  function crmProductionContext018B(person = {}) {
    const adapter = crmFindAdapter018B(person, "production");
    const items = Array.isArray(adapter?.items) ? adapter.items : [];
    const activeItem = items.find((item) => item && (item.is_active || item.running || !item.ended_at)) || items[0] || null;

    if (activeItem) {
      const refName = activeItem.reference_name || activeItem.name || activeItem.reference || "Sin referencia";
      const seconds = crmParseSeconds018B(activeItem.effective_seconds ?? activeItem.duration_seconds);
      const running = Boolean(activeItem.running && crmNormalizeStatus018B(person.status) === "working");
      return {
        code: "production",
        label: "Referencia",
        value: refName,
        meta: seconds ? crmFormatSeconds018B(seconds) : "--:--",
        timer: running ? { seconds, type: "active", running: true } : null,
        tone: running ? "active" : "idle"
      };
    }

    const eventValue = crmModuleValueForPerson("production", person);
    return {
      code: "production",
      label: "Referencia",
      value: eventValue && eventValue !== crmModuleFallback("production") ? eventValue : "Sin referencia",
      meta: "--:--",
      tone: "idle"
    };
  }

  function crmGpsContext018B(person = {}) {
    const gpsInfo = person.gpsInfo || person.snapshotRow?.gps || null;
    let status = "";
    let coords = "";
    let zoneName = "";
    let label = "";

    if (gpsInfo) {
      status = String(gpsInfo.gps_status || gpsInfo.status || "").toLowerCase();
      coords = gpsInfo.coordinates || (
        gpsInfo.latitude !== undefined && gpsInfo.longitude !== undefined
          ? `${Number(gpsInfo.latitude).toFixed(6)}, ${Number(gpsInfo.longitude).toFixed(6)}`
          : ""
      );
      zoneName = String(
        gpsInfo.zone_name ||
        gpsInfo.perimeter_name ||
        gpsInfo.perimeter?.name ||
        gpsInfo.perimeter?.label ||
        ""
      ).trim();
      label = String(gpsInfo.gps_label || "").trim();
    }

    if (!coords) {
      const event = crmGpsLatestEvent(person);
      status = event ? crmGpsStatusFromEvent(event) : status;
      coords = event ? crmGpsCoordinatesFromEvent(event) : coords;

      const payload = event?.payload_json || event?.payload || {};
      const metadata = event?.metadata_json || event?.metadata || {};
      zoneName = zoneName || String(
        payload.zone_name ||
        payload.perimeter_name ||
        payload.perimeter?.name ||
        metadata.zone_name ||
        metadata.perimeter_name ||
        metadata.perimeter?.name ||
        ""
      ).trim();
      label = label || String(payload.gps_label || metadata.gps_label || "").trim();
    }

    const normalized = crmGpsStatusClass(status);
    const stateLabel = label || crmGpsStatusLabel(normalized);

    let value = "Sin ubicación";
    if (normalized === "inside") {
      value = zoneName || "Zona autorizada";
    } else if (normalized === "outside") {
      value = "Fuera de zona autorizada";
    } else if (coords) {
      value = zoneName || "Ubicación recibida";
    }

    return {
      code: "gps",
      label: "Ubicación",
      value,
      meta: [stateLabel, coords].filter(Boolean).join(" · "),
      tone: normalized === "outside" ? "warning" : (normalized === "inside" ? "ok" : "idle")
    };
  }

  function crmGenericContext018B(person = {}, code = "") {
    const adapter = crmFindAdapter018B(person, code);
    const items = Array.isArray(adapter?.items) ? adapter.items : [];
    const first = items[0] || null;
    const labels = {
      materials: "Materiales",
      field: "Tarea",
      requests: "Solicitud",
      orders: "Pedido",
      retail: "Retail",
      stores: "Punto",
      hospitality: "Hospitality",
      bots: "Canal",
      payroll: "NÃ³mina"
    };

    if (first) {
      return {
        code,
        label: labels[code] || crmModuleDisplay(code),
        value: first.title || first.label || first.name || first.status || crmModuleValueForPerson(code, person),
        meta: first.detail || first.meta || "",
        tone: "idle"
      };
    }

    return {
      code,
      label: labels[code] || crmModuleDisplay(code),
      value: crmModuleValueForPerson(code, person),
      meta: "",
      tone: "idle"
    };
  }

  function crmEmployeeContext018B(person = {}, moduleCodes = []) {
    const code = crmSingleContextCode018B(person, moduleCodes);
    if (!code) return null;

    if (code === "production") return crmProductionContext018B(person);
    if (code === "gps") return crmGpsContext018B(person);
    return crmGenericContext018B(person, code);
  }

  function crmContextMarkup018B(person = {}, moduleCodes = []) {
    const ctx = crmEmployeeContext018B(person, moduleCodes);
    if (!ctx) return "";

    const tone = ctx.tone || "idle";
    const timerAttr = ctx.timer
      ? ` data-cx-crm-timer data-base-seconds="${h(ctx.timer.seconds)}" data-timer-kind="${h(ctx.timer.type || "active")}" data-running="${ctx.timer.running ? "1" : "0"}" data-rendered-at="${Date.now()}"`
      : "";

    return `
      <div class="cx-crm-context-card ${h(ctx.code || "")} ${h(tone)}">
        <span>${h(ctx.label)}</span>
        <strong>${h(ctx.value || "-")}</strong>
        ${ctx.meta ? `<small${timerAttr}>${h(ctx.meta)}</small>` : ""}
      </div>
    `;
  }

  function crmTimerData018B(person = {}) {
    const status = crmNormalizeStatus018B(person.status || person.metrics?.status);
    const metrics = person.metrics || {};
    const core = metrics.snapshotCore || person.snapshotRow?.core || {};

    if (status === "on_break") {
      const seconds = crmParseSeconds018B(core.current_pause_seconds ?? core.pause_accumulated_seconds ?? Math.floor((metrics.pauseMs || 0) / 1000));
      return { seconds, kind: "pause", running: true };
    }

    if (status === "working") {
      const seconds = crmParseSeconds018B(core.shift_effective_seconds ?? Math.floor((metrics.payableMs || 0) / 1000));
      return { seconds, kind: "active", running: true };
    }

    const seconds = crmParseSeconds018B(core.shift_effective_seconds ?? Math.floor((metrics.payableMs || 0) / 1000));
    return { seconds, kind: "idle", running: false };
  }

  function crmTimerMarkup018B(person = {}) {
    const timer = crmTimerData018B(person);
    const renderedAt = Date.now();
    const css = timer.kind === "pause" ? "cx-crm-timer pause" : "cx-crm-timer";
    const value = timer.seconds > 0 ? crmFormatSeconds018B(timer.seconds) : "--:--";

    return `
      <strong
        class="${css}"
        data-cx-crm-timer
        data-base-seconds="${h(timer.seconds)}"
        data-timer-kind="${h(timer.kind)}"
        data-running="${timer.running ? "1" : "0"}"
        data-rendered-at="${renderedAt}"
      >${h(value)}</strong>
    `;
  }

  function crmTickRealtimeTimers018B() {
    document.querySelectorAll("[data-cx-crm-timer]").forEach((el) => {
      const base = crmParseSeconds018B(el.getAttribute("data-base-seconds"));
      const renderedAt = Number(el.getAttribute("data-rendered-at") || Date.now());
      const running = el.getAttribute("data-running") === "1";
      const kind = el.getAttribute("data-timer-kind") || "active";
      const extra = running ? Math.max(0, Math.floor((Date.now() - renderedAt) / 1000)) : 0;
      const seconds = base + extra;

      el.textContent = seconds > 0 ? crmFormatSeconds018B(seconds) : "--:--";
      el.classList.toggle("pause", kind === "pause");
    });
  }

  function crmStartRealtimeTimers018B() {
    if (cxCrmRealtimeTimer018B) {
      clearInterval(cxCrmRealtimeTimer018B);
      cxCrmRealtimeTimer018B = null;
    }

    crmTickRealtimeTimers018B();

    if (document.querySelector("[data-cx-crm-timer]")) {
      cxCrmRealtimeTimer018B = setInterval(crmTickRealtimeTimers018B, 1000);
    }
  }

  async function crmTrySnapshotEndpoint018B(companyId, path) {
    try {
      const data = await api(path.replace("{company_id}", encodeURIComponent(companyId)));
      if (data && data.ok && Array.isArray(data.employees)) return data;
    } catch (error) {
      return null;
    }

    return null;
  }

  async function crmLoadAdaptiveSnapshot018B() {
    const companyId = state.companyId;
    if (!companyId) return null;

    const paths = [
      "/crm-core-v1/companies/{company_id}/snapshot",
      "/crm-live-v1/companies/{company_id}/snapshot",
      "/crm-core/companies/{company_id}/snapshot",
      "/crm-live/companies/{company_id}/snapshot",
      "/crm/companies/{company_id}/snapshot"
    ];

    for (const path of paths) {
      const data = await crmTrySnapshotEndpoint018B(companyId, path);
      if (data) return data;
    }

    return null;
  }

  function crmNormalizeSnapshot018B(snapshot = {}) {
    const employees = Array.isArray(snapshot.employees) ? snapshot.employees : [];
    const activeModules = (snapshot.active_modules || []).map(cxCrmNormalizeCode018B);

    const people = employees.map((row) => {
      const core = row.core || {};
      const status = crmNormalizeStatus018B(core.status || row.work_status);
      const name = row.employee_name || row.name || "Empleado";
      const role = row.employee_role || row.role || "";
      const person = {
        employee: {
          id: row.employee_id,
          full_name: name,
          role,
          employee_type: role,
        },
        employeeId: row.employee_id,
        name,
        role,
        status,
        events: [],
        latest: null,
        adapters: Array.isArray(row.adapters) ? row.adapters : [],
        snapshotRow: row,
        gpsInfo: row.gps || null,
        metrics: {
          status,
          latest: null,
          snapshotCore: core,
          grossMs: crmParseSeconds018B(core.shift_gross_seconds || core.shift_effective_seconds) * 1000,
          pauseMs: crmParseSeconds018B(core.current_pause_seconds || core.pause_accumulated_seconds) * 1000,
          payableMs: crmParseSeconds018B(core.shift_effective_seconds) * 1000,
          timer: "--:--",
        },
      };

      return person;
    });

    return {
      employees,
      events: [],
      todayEvents: [],
      people,
      working: people.filter((person) => person.status === "working"),
      onBreak: people.filter((person) => person.status === "on_break"),
      offShift: people.filter((person) => !["working", "on_break"].includes(person.status)),
      bot: null,
      gpsSummary: null,
      snapshot,
      summary: snapshot.summary || {},
      activeModules,
      dynamicModules: crmPickSummaryModules018B({ snapshot, activeModules }),
    };
  }


  /* CX_018F_CRM_REFERENCE_LIVE_BINDING_START */
  function crmHasUsefulProductionContext018F(person = {}) {
    const adapter = crmFindAdapter018B(person, "production");
    const items = Array.isArray(adapter?.items) ? adapter.items : [];

    return items.some((item) => {
      const name = String(item?.reference_name || item?.name || item?.reference || "").trim();
      return name && !/^sin\s+referencia$/i.test(name);
    });
  }

  function crmReferenceFallbackSeconds018F(person = {}, session = {}) {
    const startedAt = crmDateToMs018B(session.started_at || session.created_at);
    if (!startedAt) return 0;

    const raw = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
    const status = crmNormalizeStatus018B(person.status || person.metrics?.status);
    const core = person.metrics?.snapshotCore || person.snapshotRow?.core || {};
    const currentPause = status === "on_break"
      ? crmParseSeconds018B(core.current_pause_seconds ?? Math.floor((person.metrics?.pauseMs || 0) / 1000))
      : 0;

    return Math.max(raw - currentPause, 0);
  }

  function crmAttachProductionSession018F(person = {}, session = {}) {
    if (!person || !session) return person;

    const referenceName = String(session.reference_name || session.name || session.reference || "").trim();
    if (!referenceName) return person;

    const status = crmNormalizeStatus018B(person.status || person.metrics?.status);
    const seconds = crmReferenceFallbackSeconds018F(person, session);
    const running = status === "working";

    const item = {
      session_id: session.id || session.session_id || "",
      employee_id: session.employee_id || person.employeeId || person.employee?.id || "",
      employee_name: session.employee_name || person.name || person.employee?.full_name || "",
      telegram_user_id: session.telegram_user_id || person.employee?.telegram_user_id || "",
      reference_id: session.reference_id || "",
      reference_name: referenceName,
      started_at: session.started_at || session.created_at || "",
      ended_at: session.ended_at || "",
      status: session.status || "active",
      is_active: true,
      effective_seconds: seconds,
      duration_seconds: seconds,
      running,
      source: "references_v1_active_session",
      label: running ? "Active reference" : "Paused reference",
    };

    const adapters = Array.isArray(person.adapters) ? person.adapters : [];
    let adapter = adapters.find((entry) => {
      const code = cxCrmNormalizeCode018B(entry?.code || entry?.module || entry?.title);
      return code === "production" || code === "production_references";
    });

    if (!adapter) {
      adapter = {
        code: "production_references",
        title: "Production",
        enabled: true,
        items: [],
      };
      adapters.push(adapter);
    }

    adapter.code = "production_references";
    adapter.enabled = true;
    adapter.items = [item];

    person.adapters = adapters;
    return person;
  }

  async function crmHydrateProductionSessions018F(crm = {}) {
    if (!crm || !state.companyId) return crm;

    const active = cxCrmActiveModuleSet018B();
    if (!active.has("production") && !active.has("references")) return crm;

    const people = Array.isArray(crm.people) ? crm.people : [];

    await Promise.all(people.map(async (person) => {
      try {
        if (crmHasUsefulProductionContext018F(person)) return;

        const employeeId = person.employeeId || person.employee?.id;
        if (!employeeId) return;

        const data = await api(`/references-v1/companies/${encodeURIComponent(state.companyId)}/flow/active-session?employee_id=${encodeURIComponent(employeeId)}`);

        if (data && data.active && data.session) {
          crmAttachProductionSession018F(person, data.session);
        }
      } catch (error) {
        // Do not break CRM if the optional live production source is unavailable.
      }
    }));

    if (crm.summary) {
      crm.summary.with_reference = people.filter((person) => crmHasUsefulProductionContext018F(person)).length;
    }

    return crm;
  }
  /* CX_018F_CRM_REFERENCE_LIVE_BINDING_END */


  async function loadClientCrmData() {
    const snapshot = await crmLoadAdaptiveSnapshot018B();

    if (snapshot) {
      const normalized = crmNormalizeSnapshot018B(snapshot);
      return await crmHydrateProductionSessions018F(normalized);
    }

    const legacy = await loadClientCrmDataLegacy018B();
    legacy.dynamicModules = crmPickSummaryModules018B(legacy);
    return await crmHydrateProductionSessions018F(legacy);
  }
  /* CX_018B_CRM_ADAPTIVE_SINGLE_CONTEXT_END */

  function renderCrmCollaboratorCards(people = [], moduleCodes = []) {
    if (!people.length) {
      return `<div class="personal-empty">No hay colaboradores operativos para mostrar.</div>`;
    }

    return `
      <style>
        .cx-crm-people-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
          gap: 16px;
          margin-top: 18px;
        }
        .cx-crm-person-card {
          padding: 20px;
          min-height: 198px;
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        .cx-crm-person-head {
          display: flex;
          justify-content: space-between;
          gap: 12px;
          align-items: flex-start;
        }
        .cx-crm-timer-wrap span,
        .cx-crm-context-card span {
          display: block;
          margin-bottom: 6px;
          font-size: 12px;
          letter-spacing: .08em;
          text-transform: uppercase;
          opacity: .76;
          font-weight: 950;
        }
        .cx-crm-timer {
          display: block;
          font-size: 30px;
          line-height: 1;
          letter-spacing: .02em;
        }
        .cx-crm-timer.pause {
          color: #ff9b21;
          text-shadow: 0 0 18px rgba(255,155,33,.35);
        }
        .cx-crm-context-card {
          border: 1px solid rgba(255,255,255,.12);
          border-radius: 16px;
          padding: 13px 14px;
          background: rgba(255,255,255,.045);
        }
        .cx-crm-context-card strong {
          display: block;
          font-size: 17px;
          line-height: 1.12;
          overflow-wrap: anywhere;
        }
        .cx-crm-context-card small {
          display: block;
          margin-top: 8px;
          font-weight: 950;
          opacity: .88;
        }
        .cx-crm-context-card.ok {
          border-color: rgba(92, 255, 164, .42);
          background: rgba(92, 255, 164, .11);
        }
        .cx-crm-context-card.warning {
          border-color: rgba(255, 155, 33, .52);
          background: rgba(255, 155, 33, .13);
        }
        .cx-crm-context-card.gps.ok strong {
          color: #5cff9f;
          text-shadow: 0 0 18px rgba(92,255,159,.22);
        }
        .cx-crm-context-card.gps.warning strong {
          color: #ff9b21;
          text-shadow: 0 0 18px rgba(255,155,33,.28);
        }
      </style>
      <div class="cx-crm-people-grid">
        ${people.map((person) => `
          <article class="client-kpi cx-crm-person-card">
            <div class="cx-crm-person-head">
              <div>
                <span>Colaborador</span>
                <strong style="font-size:22px">${h(person.name)}</strong>
              </div>
              <span class="personal-status-pill ${h(crmStatusTone018B(person.status))}">${h(crmStatusLabel(person.status))}</span>
            </div>

            <div class="cx-crm-timer-wrap">
              <span>${crmNormalizeStatus018B(person.status) === "on_break" ? "Tiempo en pausa" : "Tiempo activo"}</span>
              ${crmTimerMarkup018B(person)}
            </div>

            ${crmContextMarkup018B(person, moduleCodes)}
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

    if (isClientModuleActive("gps")) ensureGpsStyles();

    const company = state.company || {};
    const crm = await loadClientCrmData();
    const moduleCards = crmPickSummaryModules018B(crm);

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
                  <strong>${h(crmTopCardValue018B(moduleCards[0], crm))}</strong>
                </div>
                <div class="client-kpi">
                  <span>${h(crmModuleDisplay(moduleCards[1]))}</span>
                  <strong>${h(crmTopCardValue018B(moduleCards[1], crm))}</strong>
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

    crmStartRealtimeTimers018B();
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
    if (!isClientModuleActive("gps")) {
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
              <div class="client-eyebrow">Modulo GPS</div>
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


      .cx-inv-invoice-input {
        min-width: 180px;
        max-width: 220px;
      }
      .cx-inv-invoice-picker {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 155px;
        border: 1px dashed rgba(255,255,255,.28);
        background: rgba(255,255,255,.07);
        border-radius: 12px;
        padding: 10px 12px;
        cursor: pointer;
        font-weight: 1000;
        text-align: center;
      }
      .cx-inv-invoice-picker input {
        display: none;
      }
      .cx-inv-invoice-picker:hover {
        border-color: rgba(255,255,255,.48);
        background: rgba(255,255,255,.11);
      }
      .cx-inv-history {
        margin-top: 22px;
        border: 1px solid rgba(255,255,255,.12);
        border-radius: 22px;
        overflow: hidden;
        background: rgba(0,0,0,.12);
      }
      .cx-inv-history-grid {
        min-width: 1180px;
        display: grid;
        grid-template-columns: 150px minmax(210px,1fr) 90px 100px 100px minmax(190px,1fr) 160px;
      }
      .cx-inv-history-cell {
        padding: 12px 13px;
        border-bottom: 1px solid rgba(255,255,255,.08);
        border-right: 1px solid rgba(255,255,255,.06);
        font-weight: 850;
      }
      .cx-inv-history-head {
        background: rgba(255,255,255,.08);
        text-transform: uppercase;
        letter-spacing: .10em;
        font-size: 11px;
        opacity: .76;
        font-weight: 1000;
      }
      .cx-inv-file-link {
        display: inline-flex;
        align-items: center;
        border-radius: 12px;
        padding: 9px 10px;
        border: 1px solid rgba(255,255,255,.14);
        background: rgba(255,255,255,.08);
        color: inherit;
        text-decoration: none;
        font-weight: 1000;
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

  async function loadInventoryMovements(itemId = "") {
    if (!state.companyId) return { movements: [] };
    const qs = itemId ? `&item_id=${encodeURIComponent(itemId)}` : "";
    return api(`/inventory/companies/${encodeURIComponent(state.companyId)}/movements?limit=10&include_archived=false${qs}`);
  }

  async function archiveInventoryMovements(movementIds = []) {
    if (!state.companyId) return { archived: 0 };
    const ids = (Array.isArray(movementIds) ? movementIds : []).map((id) => String(id || "").trim()).filter(Boolean);
    if (!ids.length) return { archived: 0 };
    return api(`/inventory/companies/${encodeURIComponent(state.companyId)}/movements/archive-exported`, {
      method: "POST",
      body: JSON.stringify({ movement_ids: ids }),
    });
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

    const entrySaved = await addInventoryEntry(itemId, { noRender: true, optional: true });

    await renderInventoryModule();
    setTimeout(() => showInventoryNotice(entrySaved ? "Material actualizado. Entrada registrada y stock actualizado." : "Material actualizado."), 80);
  }

  async function addInventoryEntry(itemId, options = {}) {
    const input = document.querySelector(`[data-inventory-entry-qty="${CSS.escape(String(itemId))}"]`);
    const invoiceInput = document.querySelector(`[data-inventory-entry-invoice="${CSS.escape(String(itemId))}"]`);
    const quantity = inventoryNumber(input?.value || 0);

    if (quantity <= 0) {
      if (!options.optional) showInventoryNotice("Ingresa una cantidad mayor a cero.", "error");
      return false;
    }

    const invoiceFile = invoiceInput?.files && invoiceInput.files.length ? invoiceInput.files[0] : null;

    if (invoiceFile) {
      const form = new FormData();
      form.append("quantity", String(quantity));
      form.append("notes", "Entrada desde Inventario");
      form.append("invoice", invoiceFile);
      await apiForm(`/inventory/items/${encodeURIComponent(itemId)}/entry-with-invoice`, form);
    } else {
      await api(`/inventory/items/${encodeURIComponent(itemId)}/entry`, {
        method: "POST",
        body: JSON.stringify({ quantity, notes: "Entrada desde Inventario" }),
      });
    }

    if (!options.noRender) {
      await renderInventoryModule();
      setTimeout(() => showInventoryNotice(invoiceFile ? "Entrada registrada con factura. Stock actualizado." : "Entrada registrada. Stock actualizado."), 80);
    }

    return true;
  }

  async function disableInventoryItem(itemId) {
    await api(`/inventory/items/${encodeURIComponent(itemId)}/disable`, { method: "POST" });
    await renderInventoryModule();
    setTimeout(() => showInventoryNotice("Material deshabilitado."), 80);
  }

  async function exportInventoryCsv() {
    const movements = Array.isArray(window.__cxInventoryMovements) ? window.__cxInventoryMovements : [];

    if (!movements.length) {
      showInventoryNotice("No hay entradas visibles para exportar.", "error");
      return;
    }

    const headers = ["Fecha", "Material", "Tamano", "Color", "Cantidad", "Stock anterior", "Stock nuevo", "Notas", "Factura"];
    const csvRows = [headers].concat(movements.map((row) => [
      inventoryMovementDate(row.created_at),
      row.name_reference || "",
      row.size || "",
      row.color || "",
      row.quantity_delta ?? row.quantity ?? 0,
      row.stock_before ?? 0,
      row.stock_after ?? 0,
      row.notes || "",
      row.invoice_original_name || "",
    ]));

    const csv = csvRows
      .map((items) => items.map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`).join(","))
      .join("\n");

    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `clonexa_inventario_ingresos_${state.companyId || "empresa"}_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);

    const movementIds = movements.map((row) => row.id).filter(Boolean);
    if (movementIds.length) {
      await archiveInventoryMovements(movementIds);
      await renderInventoryModule();
      setTimeout(() => showInventoryNotice("CSV exportado. Entradas archivadas de la vista principal."), 80);
    }
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
          <label class="cx-inv-invoice-picker">
            <input data-inventory-entry-invoice="${h(row.id)}" type="file" accept="image/jpeg,image/png,image/webp,application/pdf">
            <span>Adjuntar factura</span>
          </label>
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

  function renderInventoryModifyPanel(rows = [], movements = []) {
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
                <th>Factura</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              ${rows.length ? rows.map(renderInventoryRow).join("") : `<tr><td colspan="10">No hay materiales en inventario.</td></tr>`}
            </tbody>
          </table>
        </div>

        ${renderInventoryHistoryPanel(movements)}
      </section>
    `;
  }

  function inventoryMovementDate(raw) {
    if (!raw) return "-";
    const date = new Date(raw);
    return Number.isNaN(date.getTime()) ? "-" : date.toLocaleString([], { dateStyle: "short", timeStyle: "short" });
  }

  function renderInventoryMovementRow(row = {}) {
    const qty = Number(row.quantity_delta ?? row.quantity ?? 0);
    const invoiceUrl = String(row.invoice_file_url || "");
    return `
      <div class="cx-inv-history-cell">${h(inventoryMovementDate(row.created_at))}</div>
      <div class="cx-inv-history-cell">
        <strong>${h(row.name_reference || "Material")}</strong><br>
        <span class="client-muted">${h([row.size, row.color].filter(Boolean).join(" · ") || "")}</span>
      </div>
      <div class="cx-inv-history-cell"><strong>${h(inventoryQtyLabel(qty))}</strong></div>
      <div class="cx-inv-history-cell">${h(inventoryQtyLabel(row.stock_before || 0))}</div>
      <div class="cx-inv-history-cell">${h(inventoryQtyLabel(row.stock_after || 0))}</div>
      <div class="cx-inv-history-cell">${h(row.notes || "-")}</div>
      <div class="cx-inv-history-cell">
        ${invoiceUrl ? `<a class="cx-inv-file-link" href="${h(invoiceUrl)}" target="_blank" rel="noopener">Ver factura</a><br><small class="client-muted">${h(row.invoice_original_name || "")}</small>` : `<span class="client-muted">Sin factura</span>`}
      </div>
    `;
  }

  function renderInventoryHistoryPanel(movements = []) {
    const rows = (Array.isArray(movements) ? movements : []).slice(0, 10);
    return `
      <div class="cx-inv-history">
        <div style="padding:16px 16px 4px">
          <div class="client-eyebrow">Historial de ingresos</div>
          <h3 style="margin:6px 0 10px">Ultimas 10 entradas y facturas</h3>
          <p class="client-muted">Cada ingreso queda auditado. Al exportar CSV, estas entradas se archivan visualmente sin borrar la base de datos.</p>
        </div>
        <div style="overflow-x:auto">
          <div class="cx-inv-history-grid">
            <div class="cx-inv-history-cell cx-inv-history-head">Fecha</div>
            <div class="cx-inv-history-cell cx-inv-history-head">Material</div>
            <div class="cx-inv-history-cell cx-inv-history-head">Cantidad</div>
            <div class="cx-inv-history-cell cx-inv-history-head">Antes</div>
            <div class="cx-inv-history-cell cx-inv-history-head">Después</div>
            <div class="cx-inv-history-cell cx-inv-history-head">Notas</div>
            <div class="cx-inv-history-cell cx-inv-history-head">Factura</div>
            ${rows.length ? rows.map(renderInventoryMovementRow).join("") : `<div class="cx-inv-history-cell" style="grid-column:1 / -1">No hay ingresos registrados todavía.</div>`}
          </div>
        </div>
      </div>
    `;
  }

  async function renderInventoryModule() {
    if (!isClientModuleActive("inventory")) {
      render();
      return;
    }

    ensureInventoryStyles();

    const company = state.company || {};
    let data = { summary: {}, items: [] };
    let movementsData = { movements: [] };
    let loadError = "";

    try {
      data = await loadInventoryItems();
      movementsData = await loadInventoryMovements();
    } catch (error) {
      loadError = error.message || "No se pudo cargar Inventario.";
    }

    const rows = Array.isArray(data.items) ? data.items : [];
    const movements = Array.isArray(movementsData.movements) ? movementsData.movements : [];
    const summary = data.summary || {};
    window.__cxInventoryRows = rows;
    window.__cxInventoryMovements = movements;
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
              <div class="client-eyebrow">Modulo Inventario</div>
              <h1 class="client-title">Inventario</h1>
              <p class="client-muted">Catálogo operativo, mínimos y stock actual de solo lectura. Materiales descontará o devolverá stock en la siguiente integración.</p>
              <div class="client-actions">
                <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
                <button class="client-btn" type="button" data-inventory-refresh>Actualizar</button>
                <button class="client-btn" type="button" data-inventory-export>CSV + archivar</button>
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
                <button type="button" data-inventory-export>CSV + archivar</button>
              </div>
            </section>

            ${mode === "create" ? renderInventoryCreatePanel() : renderInventoryModifyPanel(rows, movements)}
          </section>
        </div>
      </main>
    `;
  }

  /* CX_019E_R1_INVENTORY_HISTORY_ARCHIVE_CLIENT */
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
    if (!isClientModuleActive("materials")) {
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
    window.clearTimeout(window.__materialsDailyRefreshTimer);
    window.__materialsDailyRefreshTimer = window.setTimeout(() => {
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
              <div class="client-eyebrow">Modulo Materiales</div>
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
          <span>Colaboradores con tiempo</span>
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
      return `<div class="cx-payroll-empty">No hay tiempos de nómina para el periodo seleccionado.</div>`;
    }

    return `
      <div class="cx-payroll-table-wrap">
        <table class="cx-payroll-table">
          <thead>
            <tr>
              <th>Colaborador</th>
              <th>Turnos / sesiones</th>
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
    a.download = `clonexa_nomina_${period.from}_${period.to}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();

    URL.revokeObjectURL(url);
  }

  async function renderPayrollModule(period = payrollDefaultPeriod(), options = {}) {
    if (!isClientModuleActive("payroll")) {
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
              <div class="client-eyebrow">Modulo Nómina</div>
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
        <section class="cx-kpis-block" data-kpi-searchable="nomina nómina payroll horas ordinarias extra descuentos bruto neto total estimado corte">
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
    if (!isClientModuleActive("kpis")) {
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
    setupKpisAutoRefresh();
  }

  function setupKpisAutoRefresh() {
    if (window.__cxKpisAutoRefresh) {
      clearInterval(window.__cxKpisAutoRefresh);
      window.__cxKpisAutoRefresh = null;
    }
    window.__cxKpisAutoRefresh = setInterval(async () => {
      if (!document.querySelector("[data-kpis-root]")) {
        clearInterval(window.__cxKpisAutoRefresh);
        window.__cxKpisAutoRefresh = null;
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



  /* CX_018E_PRODUCTION_ANALYTICS_MODULE_START */
  const CX_PROD_I18N_018E = {
    es: {
      eyebrow: "MÃ³dulo ProducciÃ³n",
      title: "ProducciÃ³n",
      subtitle: "Tiempos, referencias, cierres, cantidades y productividad por empresa.",
      back: "Volver",
      refresh: "Actualizar",
      csv: "CSV",
      period: "Periodo",
      from: "Desde",
      to: "Hasta",
      preset: "Rango",
      view: "Vista",
      apply: "Aplicar",
      active: "Activas",
      all: "Todas",
      archived: "Archivadas",
      today: "Hoy",
      sevenDays: "7 dÃ­as",
      month: "Mes",
      thirtyDays: "30 dÃ­as",
      custom: "Personalizado",
      summary: "Resumen productivo",
      referencesActive: "Referencias activas",
      totalTime: "Tiempo productivo",
      closedQuantity: "Cantidad cerrada",
      avgProgress: "Avance promedio",
      activeSessions: "Sesiones activas",
      referenceProgress: "Avance por referencia",
      timeByReference: "Tiempo por referencia",
      timeByCollaborator: "Tiempo por colaborador y referencia",
      referenceDetail: "Detalle por referencia",
      closures: "Cierres de referencia",
      reference: "Referencia",
      size: "Talla / variante",
      initialQuantity: "Cantidad total",
      finishedQuantity: "Cantidad cerrada",
      pendingQuantity: "Pendiente",
      overQuantity: "Sobreproducida",
      progress: "Avance",
      collaborators: "Colaboradores",
      sessions: "Sesiones",
      status: "Estado",
      collaborator: "Colaborador",
      time: "Tiempo",
      closedAt: "Fecha cierre",
      channel: "Canal",
      notes: "Notas",
      empty: "Sin datos productivos todavÃ­a.",
      noClosures: "Sin cierres en este periodo.",
      noTime: "Sin tiempos productivos en este periodo.",
      error: "No se pudo cargar ProducciÃ³n.",
      moduleInactive: "El mÃ³dulo ProducciÃ³n no estÃ¡ activo para esta empresa."
    },
    en: {
      eyebrow: "Production module",
      title: "Production",
      subtitle: "Times, references, closures, quantities and productivity by company.",
      back: "Back",
      refresh: "Refresh",
      csv: "CSV",
      period: "Period",
      from: "From",
      to: "To",
      preset: "Range",
      view: "View",
      apply: "Apply",
      active: "Active",
      all: "All",
      archived: "Archived",
      today: "Today",
      sevenDays: "7 days",
      month: "Month",
      thirtyDays: "30 days",
      custom: "Custom",
      summary: "Production summary",
      referencesActive: "Active references",
      totalTime: "Production time",
      closedQuantity: "Closed quantity",
      avgProgress: "Average progress",
      activeSessions: "Active sessions",
      referenceProgress: "Reference progress",
      timeByReference: "Time by reference",
      timeByCollaborator: "Time by collaborator and reference",
      referenceDetail: "Reference detail",
      closures: "Reference closures",
      reference: "Reference",
      size: "Size / variant",
      initialQuantity: "Total quantity",
      finishedQuantity: "Closed quantity",
      pendingQuantity: "Pending",
      overQuantity: "Overproduced",
      progress: "Progress",
      collaborators: "Collaborators",
      sessions: "Sessions",
      status: "Status",
      collaborator: "Collaborator",
      time: "Time",
      closedAt: "Closed at",
      channel: "Channel",
      notes: "Notes",
      empty: "No production data yet.",
      noClosures: "No closures in this period.",
      noTime: "No production time in this period.",
      error: "Could not load Production.",
      moduleInactive: "Production module is not active for this company."
    },
    fr: {
      eyebrow: "Module production",
      title: "Production",
      subtitle: "Temps, rÃ©fÃ©rences, clÃ´tures, quantitÃ©s et productivitÃ© par entreprise.",
      back: "Retour",
      refresh: "Actualiser",
      csv: "CSV",
      period: "PÃ©riode",
      from: "Depuis",
      to: "Jusqu'Ã ",
      preset: "Plage",
      view: "Vue",
      apply: "Appliquer",
      active: "Actives",
      all: "Toutes",
      archived: "ArchivÃ©es",
      today: "Aujourd'hui",
      sevenDays: "7 jours",
      month: "Mois",
      thirtyDays: "30 jours",
      custom: "PersonnalisÃ©",
      summary: "RÃ©sumÃ© de production",
      referencesActive: "RÃ©fÃ©rences actives",
      totalTime: "Temps de production",
      closedQuantity: "QuantitÃ© clÃ´turÃ©e",
      avgProgress: "Progression moyenne",
      activeSessions: "Sessions actives",
      referenceProgress: "Progression par rÃ©fÃ©rence",
      timeByReference: "Temps par rÃ©fÃ©rence",
      timeByCollaborator: "Temps par collaborateur et rÃ©fÃ©rence",
      referenceDetail: "DÃ©tail par rÃ©fÃ©rence",
      closures: "ClÃ´tures de rÃ©fÃ©rence",
      reference: "RÃ©fÃ©rence",
      size: "Taille / variante",
      initialQuantity: "QuantitÃ© totale",
      finishedQuantity: "QuantitÃ© clÃ´turÃ©e",
      pendingQuantity: "Restant",
      overQuantity: "Surproduction",
      progress: "Progression",
      collaborators: "Collaborateurs",
      sessions: "Sessions",
      status: "Ã‰tat",
      collaborator: "Collaborateur",
      time: "Temps",
      closedAt: "Date de clÃ´ture",
      channel: "Canal",
      notes: "Notes",
      empty: "Aucune donnÃ©e de production.",
      noClosures: "Aucune clÃ´ture dans cette pÃ©riode.",
      noTime: "Aucun temps de production dans cette pÃ©riode.",
      error: "Impossible de charger Production.",
      moduleInactive: "Le module Production n'est pas actif pour cette entreprise."
    },
    pt: {
      eyebrow: "MÃ³dulo produÃ§Ã£o",
      title: "ProduÃ§Ã£o",
      subtitle: "Tempos, referÃªncias, fechamentos, quantidades e produtividade por empresa.",
      back: "Voltar",
      refresh: "Atualizar",
      csv: "CSV",
      period: "PerÃ­odo",
      from: "Desde",
      to: "AtÃ©",
      preset: "Intervalo",
      view: "Vista",
      apply: "Aplicar",
      active: "Ativas",
      all: "Todas",
      archived: "Arquivadas",
      today: "Hoje",
      sevenDays: "7 dias",
      month: "MÃªs",
      thirtyDays: "30 dias",
      custom: "Personalizado",
      summary: "Resumo de produÃ§Ã£o",
      referencesActive: "ReferÃªncias ativas",
      totalTime: "Tempo de produÃ§Ã£o",
      closedQuantity: "Quantidade fechada",
      avgProgress: "Progresso mÃ©dio",
      activeSessions: "SessÃµes ativas",
      referenceProgress: "Progresso por referÃªncia",
      timeByReference: "Tempo por referÃªncia",
      timeByCollaborator: "Tempo por colaborador e referÃªncia",
      referenceDetail: "Detalhe por referÃªncia",
      closures: "Fechamentos de referÃªncia",
      reference: "ReferÃªncia",
      size: "Tamanho / variante",
      initialQuantity: "Quantidade total",
      finishedQuantity: "Quantidade fechada",
      pendingQuantity: "Pendente",
      overQuantity: "Sobreproduzida",
      progress: "Progresso",
      collaborators: "Colaboradores",
      sessions: "SessÃµes",
      status: "Estado",
      collaborator: "Colaborador",
      time: "Tempo",
      closedAt: "Data fechamento",
      channel: "Canal",
      notes: "Notas",
      empty: "Ainda sem dados de produÃ§Ã£o.",
      noClosures: "Sem fechamentos neste perÃ­odo.",
      noTime: "Sem tempo de produÃ§Ã£o neste perÃ­odo.",
      error: "NÃ£o foi possÃ­vel carregar ProduÃ§Ã£o.",
      moduleInactive: "O mÃ³dulo ProduÃ§Ã£o nÃ£o estÃ¡ ativo para esta empresa."
    }
  };

  function cxProdSafeText018E(value) {
    return String(value ?? "");
  }

  function cxProdLang018E(settings = {}) {
    const candidates = [
      settings.language,
      settings.client_settings && settings.client_settings.language,
      window.CLONEXA_CLIENT_SETTINGS && window.CLONEXA_CLIENT_SETTINGS.language,
      window.clonexaClientSettings && window.clonexaClientSettings.language,
      document.documentElement.getAttribute("lang")
    ];

    for (const candidate of candidates) {
      const code = cxProdSafeText018E(candidate).trim().toLowerCase().slice(0, 2);
      if (CX_PROD_I18N_018E[code]) return code;
    }

    return "es";
  }

  function cxProdT018E(settings, key) {
    const lang = cxProdLang018E(settings || {});
    return (CX_PROD_I18N_018E[lang] && CX_PROD_I18N_018E[lang][key]) || CX_PROD_I18N_018E.es[key] || key;
  }

  async function cxProdLoadSettings018E() {
    try {
      if (window.CLONEXA_SETTINGS_PAYROLL && typeof window.CLONEXA_SETTINGS_PAYROLL.get === "function") {
        const settings = await window.CLONEXA_SETTINGS_PAYROLL.get(false);
        if (settings && typeof settings === "object") return settings;
      }
    } catch (error) {}

    try {
      if (!state.companyId) return {};
      return await api(`/companies/${encodeURIComponent(state.companyId)}/client-settings`);
    } catch (error) {
      return {};
    }
  }

  function cxProdNum018E(value, decimals = 0) {
    const number = Number(value || 0);
    if (!Number.isFinite(number)) return decimals ? "0.00" : "0";
    return number.toLocaleString(undefined, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals
    });
  }

  function cxProdPercent018E(value) {
    const number = Math.max(0, Math.min(100, Number(value || 0)));
    return `${cxProdNum018E(number, number % 1 === 0 ? 0 : 1)}%`;
  }

  function cxProdSeconds018E(value) {
    const seconds = Math.max(0, Math.floor(Number(value || 0)));
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (hours <= 0) return `${minutes}m`;
    return `${hours}h ${String(minutes).padStart(2, "0")}m`;
  }

  function cxProdDate018E(value) {
    const raw = cxProdSafeText018E(value);
    if (!raw) return "-";
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return raw.slice(0, 19);
    return date.toLocaleString();
  }

  function cxProdRefKey018E(referenceName, size, referenceId = "") {
    const id = cxProdSafeText018E(referenceId).trim();
    if (id) return `id:${id}`;
    return `${cxProdSafeText018E(referenceName).trim().toLowerCase()}__${cxProdSafeText018E(size).trim().toLowerCase()}`;
  }

  function cxProdBuildTimeMap018E(summary = {}) {
    const map = new Map();
    const rows = Array.isArray(summary.time_by_reference) ? summary.time_by_reference : [];

    rows.forEach((row) => {
      const keyById = cxProdRefKey018E(row.reference_name, row.size, row.reference_id);
      const keyByName = cxProdRefKey018E(row.reference_name, row.size, "");
      map.set(keyById, row);
      map.set(keyByName, row);
    });

    return map;
  }

  function cxProdReferenceTime018E(row = {}, timeMap = new Map()) {
    return timeMap.get(cxProdRefKey018E(row.name, row.size, row.id)) ||
      timeMap.get(cxProdRefKey018E(row.name, row.size, "")) ||
      {};
  }

  function cxProdDownloadUrl018E(filters = {}) {
    const params = new URLSearchParams();
    params.set("preset", filters.preset || "7d");
    params.set("view", filters.view || "active");
    if (filters.date_from) params.set("date_from", filters.date_from);
    if (filters.date_to) params.set("date_to", filters.date_to);

    return `${API}/production-v1/companies/${encodeURIComponent(state.companyId)}/export.csv?${params.toString()}`;
  }

  function cxProdDefaultFilters018E() {
    const now = new Date();
    const to = now.toISOString().slice(0, 10);
    const fromDate = new Date(now);
    fromDate.setDate(fromDate.getDate() - 6);
    return {
      preset: "7d",
      date_from: fromDate.toISOString().slice(0, 10),
      date_to: to,
      view: "active"
    };
  }

  function cxProdReadFilters018E() {
    return {
      preset: document.querySelector("[data-production-preset]")?.value || "7d",
      date_from: document.querySelector("[data-production-from]")?.value || "",
      date_to: document.querySelector("[data-production-to]")?.value || "",
      view: document.querySelector("[data-production-view]")?.value || "active"
    };
  }

  async function cxProdLoadSummary018E(filters = cxProdDefaultFilters018E()) {
    const params = new URLSearchParams();
    params.set("preset", filters.preset || "7d");
    params.set("view", filters.view || "active");
    if (filters.date_from) params.set("date_from", filters.date_from);
    if (filters.date_to) params.set("date_to", filters.date_to);

    return await api(`/production-v1/companies/${encodeURIComponent(state.companyId)}/summary?${params.toString()}`);
  }

  function cxProdCard018E(label, value, meta = "") {
    return `
      <div class="client-kpi cx-prod-kpi">
        <span>${h(label)}</span>
        <strong>${h(value)}</strong>
        ${meta ? `<small>${h(meta)}</small>` : ""}
      </div>
    `;
  }

  function cxProdBar018E(label, value, max, meta = "") {
    const safeMax = Math.max(1, Number(max || 1));
    const safeValue = Math.max(0, Number(value || 0));
    const percent = Math.min(100, Math.round((safeValue / safeMax) * 100));
    return `
      <div class="cx-prod-bar-row">
        <div class="cx-prod-bar-head">
          <strong>${h(label || "-")}</strong>
          <span>${h(meta || cxProdNum018E(safeValue))}</span>
        </div>
        <div class="cx-prod-bar-track">
          <div class="cx-prod-bar-fill" style="width:${percent}%"></div>
        </div>
      </div>
    `;
  }

  function cxProdTableCell018E(value, className = "") {
    return `<div class="cx-prod-cell ${className}">${h(value ?? "")}</div>`;
  }

  function cxProdProgressCell018E(value) {
    return `<div class="cx-prod-cell"><span class="cx-prod-progress-pill">${h(cxProdPercent018E(value))}</span></div>`;
  }

  function cxProdEnsureStyles018E() {
    let style = document.getElementById("cxProductionAnalyticsStyles018E");
    if (style) return;

    style = document.createElement("style");
    style.id = "cxProductionAnalyticsStyles018E";
    document.head.appendChild(style);

    style.textContent = `
      .cx-prod-filters {
        display: grid;
        grid-template-columns: repeat(5, minmax(140px, 1fr));
        gap: 12px;
        margin-top: 18px;
        align-items: end;
      }
      .cx-prod-field label {
        display: block;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: .12em;
        opacity: .78;
        font-weight: 1000;
        margin-bottom: 6px;
      }
      .cx-prod-field input,
      .cx-prod-field select {
        width: 100%;
        border: 1px solid rgba(255,255,255,.16);
        background: rgba(0,0,0,.22);
        color: inherit;
        border-radius: 14px;
        padding: 12px 12px;
        outline: none;
        font-weight: 900;
      }
      .cx-prod-kpi small {
        display:block;
        margin-top: 8px;
        opacity: .72;
        font-weight: 900;
      }
      .cx-prod-charts {
        display: grid;
        grid-template-columns: repeat(2, minmax(260px, 1fr));
        gap: 18px;
        margin-top: 18px;
      }
      .cx-prod-chart {
        border-radius: 24px;
        padding: 18px;
        border: 1px solid rgba(255,255,255,.12);
        background: rgba(0,0,0,.12);
      }
      .cx-prod-chart h3 {
        margin: 0 0 14px;
        font-size: 18px;
      }
      .cx-prod-bar-row {
        display: grid;
        gap: 8px;
        margin: 12px 0;
      }
      .cx-prod-bar-head {
        display: flex;
        justify-content: space-between;
        gap: 16px;
        font-size: 13px;
      }
      .cx-prod-bar-track {
        height: 12px;
        border-radius: 999px;
        overflow: hidden;
        background: rgba(255,255,255,.12);
      }
      .cx-prod-bar-fill {
        height: 100%;
        border-radius: 999px;
        background: linear-gradient(90deg, var(--cx-secondary, #00ff88), var(--cx-primary, #ff2bd6));
        box-shadow: 0 0 18px rgba(255,255,255,.25);
      }
      .cx-prod-table-wrap {
        width: 100%;
        overflow-x: auto;
        border-radius: 22px;
        border: 1px solid rgba(255,255,255,.13);
        margin-top: 14px;
      }
      .cx-prod-grid {
        min-width: 1180px;
        display: grid;
        grid-template-columns: 1.5fr .9fr .8fr .8fr .8fr .8fr .8fr .9fr .8fr;
      }
      .cx-prod-operator-grid {
        min-width: 960px;
        display: grid;
        grid-template-columns: 1.2fr 1.4fr .8fr .8fr .8fr;
      }
      .cx-prod-closures-grid {
        min-width: 980px;
        display: grid;
        grid-template-columns: 1.1fr 1.1fr 1.5fr .8fr .8fr .8fr 1.4fr;
      }
      .cx-prod-cell {
        padding: 13px 12px;
        border-bottom: 1px solid rgba(255,255,255,.09);
        background: rgba(0,0,0,.08);
        font-weight: 850;
      }
      .cx-prod-head {
        text-transform: uppercase;
        letter-spacing: .08em;
        font-size: 11px;
        opacity: .82;
        background: rgba(0,0,0,.22);
      }
      .cx-prod-progress-pill {
        display: inline-flex;
        min-width: 70px;
        justify-content: center;
        border-radius: 999px;
        padding: 6px 10px;
        color: #020617;
        background: linear-gradient(135deg, var(--cx-secondary, #00ff88), var(--cx-primary, #ff2bd6));
        font-weight: 1000;
      }
      .cx-prod-empty {
        padding: 18px;
        border-radius: 18px;
        background: rgba(0,0,0,.12);
        border: 1px solid rgba(255,255,255,.1);
        opacity: .8;
        font-weight: 900;
      }
      @media (max-width: 1000px) {
        .cx-prod-filters,
        .cx-prod-charts {
          grid-template-columns: 1fr;
        }
      }
    `;
  }

  function cxProdReferenceRows018E(summary, settings) {
    const refs = Array.isArray(summary.references) ? summary.references : [];
    const timeMap = cxProdBuildTimeMap018E(summary);

    if (!refs.length) {
      return `<div class="cx-prod-empty">${h(cxProdT018E(settings, "empty"))}</div>`;
    }

    const rows = refs.map((row) => {
      const time = cxProdReferenceTime018E(row, timeMap);
      const progress = Number(row.progress_percent || 0);
      const stateLabel = row.archived ? cxProdT018E(settings, "archived") : cxProdT018E(settings, "active");

      return [
        cxProdTableCell018E(row.name || "-"),
        cxProdTableCell018E(row.size || "-"),
        cxProdTableCell018E(cxProdNum018E(row.initial_quantity)),
        cxProdTableCell018E(cxProdNum018E(row.finished_quantity)),
        cxProdTableCell018E(cxProdNum018E(row.pending_quantity)),
        cxProdTableCell018E(cxProdNum018E(row.over_finished_quantity)),
        cxProdProgressCell018E(progress),
        cxProdTableCell018E(time.total_effective_label || cxProdSeconds018E(time.total_effective_seconds || 0)),
        cxProdTableCell018E(`${cxProdNum018E(time.operators_count || 0)} / ${stateLabel}`)
      ].join("");
    }).join("");

    return `
      <div class="cx-prod-table-wrap">
        <div class="cx-prod-grid">
          ${cxProdTableCell018E(cxProdT018E(settings, "reference"), "cx-prod-head")}
          ${cxProdTableCell018E(cxProdT018E(settings, "size"), "cx-prod-head")}
          ${cxProdTableCell018E(cxProdT018E(settings, "initialQuantity"), "cx-prod-head")}
          ${cxProdTableCell018E(cxProdT018E(settings, "finishedQuantity"), "cx-prod-head")}
          ${cxProdTableCell018E(cxProdT018E(settings, "pendingQuantity"), "cx-prod-head")}
          ${cxProdTableCell018E(cxProdT018E(settings, "overQuantity"), "cx-prod-head")}
          ${cxProdTableCell018E(cxProdT018E(settings, "progress"), "cx-prod-head")}
          ${cxProdTableCell018E(cxProdT018E(settings, "time"), "cx-prod-head")}
          ${cxProdTableCell018E(cxProdT018E(settings, "collaborators"), "cx-prod-head")}
          ${rows}
        </div>
      </div>
    `;
  }

  function cxProdOperatorRows018E(summary, settings) {
    const rows = Array.isArray(summary.time_by_operator_reference) ? summary.time_by_operator_reference : [];

    if (!rows.length) {
      return `<div class="cx-prod-empty">${h(cxProdT018E(settings, "noTime"))}</div>`;
    }

    return `
      <div class="cx-prod-table-wrap">
        <div class="cx-prod-operator-grid">
          ${cxProdTableCell018E(cxProdT018E(settings, "collaborator"), "cx-prod-head")}
          ${cxProdTableCell018E(cxProdT018E(settings, "reference"), "cx-prod-head")}
          ${cxProdTableCell018E(cxProdT018E(settings, "size"), "cx-prod-head")}
          ${cxProdTableCell018E(cxProdT018E(settings, "time"), "cx-prod-head")}
          ${cxProdTableCell018E(cxProdT018E(settings, "sessions"), "cx-prod-head")}
          ${rows.slice(0, 120).map((row) => `
            ${cxProdTableCell018E(row.employee_name || row.telegram_user_id || "-")}
            ${cxProdTableCell018E(row.reference_name || "-")}
            ${cxProdTableCell018E(row.size || "-")}
            ${cxProdTableCell018E(row.effective_label || cxProdSeconds018E(row.effective_seconds || 0))}
            ${cxProdTableCell018E(cxProdNum018E(row.sessions_count || 0))}
          `).join("")}
        </div>
      </div>
    `;
  }

  function cxProdClosureRows018E(summary, settings) {
    const rows = Array.isArray(summary.closures_period) && summary.closures_period.length
      ? summary.closures_period
      : (Array.isArray(summary.closures_display) ? summary.closures_display : []);

    if (!rows.length) {
      return `<div class="cx-prod-empty">${h(cxProdT018E(settings, "noClosures"))}</div>`;
    }

    return `
      <div class="cx-prod-table-wrap">
        <div class="cx-prod-closures-grid">
          ${cxProdTableCell018E(cxProdT018E(settings, "closedAt"), "cx-prod-head")}
          ${cxProdTableCell018E(cxProdT018E(settings, "collaborator"), "cx-prod-head")}
          ${cxProdTableCell018E(cxProdT018E(settings, "reference"), "cx-prod-head")}
          ${cxProdTableCell018E(cxProdT018E(settings, "size"), "cx-prod-head")}
          ${cxProdTableCell018E(cxProdT018E(settings, "finishedQuantity"), "cx-prod-head")}
          ${cxProdTableCell018E(cxProdT018E(settings, "channel"), "cx-prod-head")}
          ${cxProdTableCell018E(cxProdT018E(settings, "notes"), "cx-prod-head")}
          ${rows.slice(0, 160).map((row) => `
            ${cxProdTableCell018E(cxProdDate018E(row.closed_at))}
            ${cxProdTableCell018E(row.employee_name || row.telegram_user_id || "-")}
            ${cxProdTableCell018E(row.reference_name || "-")}
            ${cxProdTableCell018E(row.size || "-")}
            ${cxProdTableCell018E(cxProdNum018E(row.quantity_finished || 0))}
            ${cxProdTableCell018E(row.source_channel || "-")}
            ${cxProdTableCell018E(row.notes || "")}
          `).join("")}
        </div>
      </div>
    `;
  }

  function cxProdCharts018E(summary, settings) {
    const refs = Array.isArray(summary.references) ? summary.references : [];
    const timeRows = Array.isArray(summary.time_by_reference) ? summary.time_by_reference : [];
    const maxTime = Math.max(1, ...timeRows.map((row) => Number(row.total_effective_seconds || 0)));

    return `
      <div class="cx-prod-charts">
        <section class="cx-prod-chart">
          <h3>${h(cxProdT018E(settings, "referenceProgress"))}</h3>
          ${
            refs.length
              ? refs.slice(0, 10).map((row) => cxProdBar018E(`${row.name || "-"} ${row.size ? "/ " + row.size : ""}`, row.progress_percent || 0, 100, cxProdPercent018E(row.progress_percent || 0))).join("")
              : `<div class="cx-prod-empty">${h(cxProdT018E(settings, "empty"))}</div>`
          }
        </section>

        <section class="cx-prod-chart">
          <h3>${h(cxProdT018E(settings, "timeByReference"))}</h3>
          ${
            timeRows.length
              ? timeRows.slice(0, 10).map((row) => cxProdBar018E(`${row.reference_name || "-"} ${row.size ? "/ " + row.size : ""}`, row.total_effective_seconds || 0, maxTime, row.total_effective_label || cxProdSeconds018E(row.total_effective_seconds || 0))).join("")
              : `<div class="cx-prod-empty">${h(cxProdT018E(settings, "noTime"))}</div>`
          }
        </section>
      </div>
    `;
  }

  async function renderProductionModule(filters = cxProdDefaultFilters018E()) {
    if (!isClientModuleActive("production")) {
      render();
      return;
    }

    cxProdEnsureStyles018E();

    const company = state.company || {};
    const settings = await cxProdLoadSettings018E();
    let summary = null;
    let loadError = "";

    try {
      summary = await cxProdLoadSummary018E(filters);
    } catch (error) {
      summary = null;
      loadError = error.message || cxProdT018E(settings, "error");
    }

    const totals = (summary && summary.totals) || {};
    const references = Array.isArray(summary && summary.references) ? summary.references : [];
    const progressValues = references.map((row) => Number(row.progress_percent || 0)).filter((value) => Number.isFinite(value));
    const avgProgress = progressValues.length ? progressValues.reduce((sum, value) => sum + value, 0) / progressValues.length : Number(totals.progress_percent || 0);

    $("app").innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, normalizeBranding(state.branding || {}))}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>
            <nav class="client-nav">${renderClientNav("production")}</nav>
            <div class="client-footer-id"><strong>Tenant activo</strong><br>${h(state.companyId || "")}</div>
          </aside>

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">${h(cxProdT018E(settings, "eyebrow"))}</div>
              <h1 class="client-title">${h(cxProdT018E(settings, "title"))}</h1>
              <p class="client-muted">${h(cxProdT018E(settings, "subtitle"))}</p>

              <div class="client-actions">
                <button class="client-btn" type="button" data-client-back-dashboard>${h(cxProdT018E(settings, "back"))}</button>
                <button class="client-btn" type="button" data-production-refresh>${h(cxProdT018E(settings, "refresh"))}</button>
                <button class="client-btn" type="button" data-production-export>${h(cxProdT018E(settings, "csv"))}</button>
              </div>
            </header>

            <section class="client-panel">
              <div class="client-eyebrow">${h(cxProdT018E(settings, "period"))}</div>
              <h2>${h(cxProdT018E(settings, "summary"))}</h2>

              <div class="cx-prod-filters">
                <div class="cx-prod-field">
                  <label>${h(cxProdT018E(settings, "preset"))}</label>
                  <select data-production-preset>
                    <option value="today" ${filters.preset === "today" ? "selected" : ""}>${h(cxProdT018E(settings, "today"))}</option>
                    <option value="7d" ${filters.preset === "7d" ? "selected" : ""}>${h(cxProdT018E(settings, "sevenDays"))}</option>
                    <option value="30d" ${filters.preset === "30d" ? "selected" : ""}>${h(cxProdT018E(settings, "thirtyDays"))}</option>
                    <option value="month" ${filters.preset === "month" ? "selected" : ""}>${h(cxProdT018E(settings, "month"))}</option>
                    <option value="custom" ${filters.preset === "custom" ? "selected" : ""}>${h(cxProdT018E(settings, "custom"))}</option>
                  </select>
                </div>
                <div class="cx-prod-field">
                  <label>${h(cxProdT018E(settings, "from"))}</label>
                  <input type="date" data-production-from value="${h(filters.date_from || "")}">
                </div>
                <div class="cx-prod-field">
                  <label>${h(cxProdT018E(settings, "to"))}</label>
                  <input type="date" data-production-to value="${h(filters.date_to || "")}">
                </div>
                <div class="cx-prod-field">
                  <label>${h(cxProdT018E(settings, "view"))}</label>
                  <select data-production-view>
                    <option value="active" ${filters.view === "active" ? "selected" : ""}>${h(cxProdT018E(settings, "active"))}</option>
                    <option value="all" ${filters.view === "all" ? "selected" : ""}>${h(cxProdT018E(settings, "all"))}</option>
                    <option value="archived" ${filters.view === "archived" ? "selected" : ""}>${h(cxProdT018E(settings, "archived"))}</option>
                  </select>
                </div>
                <div class="cx-prod-field">
                  <button class="client-btn" type="button" data-production-apply>${h(cxProdT018E(settings, "apply"))}</button>
                </div>
              </div>

              ${loadError ? `<div class="personal-toast error" style="margin-top:14px">${h(loadError)}</div>` : ""}
            </section>

            <section class="client-panel">
              <div class="client-kpi-grid">
                ${cxProdCard018E(cxProdT018E(settings, "referencesActive"), cxProdNum018E(totals.references_total || references.length))}
                ${cxProdCard018E(cxProdT018E(settings, "totalTime"), totals.effective_label_period || cxProdSeconds018E(totals.effective_seconds_period || 0))}
                ${cxProdCard018E(cxProdT018E(settings, "closedQuantity"), cxProdNum018E(totals.finished_quantity_total || 0), `${cxProdT018E(settings, "closedQuantity")} / ${cxProdT018E(settings, "initialQuantity")}`)}
                ${cxProdCard018E(cxProdT018E(settings, "avgProgress"), cxProdPercent018E(avgProgress), `${cxProdT018E(settings, "activeSessions")}: ${cxProdNum018E(totals.active_sessions || 0)}`)}
              </div>

              ${summary ? cxProdCharts018E(summary, settings) : ""}
            </section>

            <section class="client-panel">
              <div class="client-eyebrow">${h(cxProdT018E(settings, "referenceDetail"))}</div>
              <h2>${h(cxProdT018E(settings, "referenceDetail"))}</h2>
              ${summary ? cxProdReferenceRows018E(summary, settings) : `<div class="cx-prod-empty">${h(cxProdT018E(settings, "empty"))}</div>`}
            </section>

            <section class="client-panel">
              <div class="client-eyebrow">${h(cxProdT018E(settings, "timeByCollaborator"))}</div>
              <h2>${h(cxProdT018E(settings, "timeByCollaborator"))}</h2>
              ${summary ? cxProdOperatorRows018E(summary, settings) : `<div class="cx-prod-empty">${h(cxProdT018E(settings, "noTime"))}</div>`}
            </section>

            <section class="client-panel">
              <div class="client-eyebrow">${h(cxProdT018E(settings, "closures"))}</div>
              <h2>${h(cxProdT018E(settings, "closures"))}</h2>
              ${summary ? cxProdClosureRows018E(summary, settings) : `<div class="cx-prod-empty">${h(cxProdT018E(settings, "noClosures"))}</div>`}
            </section>
          </section>
        </div>
      </main>
    `;
  }
  /* CX_018E_PRODUCTION_ANALYTICS_MODULE_END */



  /* CLONEXA_019B_CLIENT_MINI_PANEL_LINKS_START */
  const CX_MINI_PANEL_MODULE_CODES_019B = new Set([
    "mini_panel",
    "mini_paneles",
    "creacion_minipanel",
    "creacion_mini_panel"
  ]);

  const CX_MINI_PANEL_TYPES_019B = {
    store: {
      label: { es: "Tiendas", en: "Stores", fr: "Boutiques", pt: "Lojas" },
      description: {
        es: "Link base para mini paneles de tienda.",
        en: "Base link for store mini panels.",
        fr: "Lien de base pour les mini panneaux de boutique.",
        pt: "Link base para mini paineis de loja."
      }
    },
    sales: {
      label: { es: "Ventas", en: "Sales", fr: "Ventes", pt: "Vendas" },
      description: {
        es: "Link base para mini paneles de vendedores.",
        en: "Base link for sales mini panels.",
        fr: "Lien de base pour les mini panneaux de vente.",
        pt: "Link base para mini paineis de vendas."
      }
    },
    logistics: {
      label: { es: "Logistica", en: "Logistics", fr: "Logistique", pt: "Logistica" },
      description: {
        es: "Link base para mini paneles de logistica.",
        en: "Base link for logistics mini panels.",
        fr: "Lien de base pour les mini panneaux de logistique.",
        pt: "Link base para mini paineis de logistica."
      }
    },
    inventory: {
      label: { es: "Inventarios", en: "Inventory", fr: "Inventaires", pt: "Inventarios" },
      description: {
        es: "Link base para mini paneles de inventario.",
        en: "Base link for inventory mini panels.",
        fr: "Lien de base pour les mini panneaux d'inventaire.",
        pt: "Link base para mini paineis de inventario."
      }
    },
    other: {
      label: { es: "Otros", en: "Other", fr: "Autres", pt: "Outros" },
      description: {
        es: "Link base para mini paneles personalizados.",
        en: "Base link for custom mini panels.",
        fr: "Lien de base pour les mini panneaux personnalises.",
        pt: "Link base para mini paineis personalizados."
      }
    }
  };

  const CX_MINI_PANEL_I18N_019B = {
    es: {
      eyebrow: "Modulo Mini Paneles",
      title: "Mini Paneles",
      subtitle: "Enlaces operativos habilitados desde Admin V2 segun el paquete asignado a esta empresa.",
      back: "Volver",
      refresh: "Actualizar",
      package: "Paquete",
      inherited: "Capacidad heredada del paquete",
      enabled: "Habilitado",
      disabled: "Deshabilitado",
      usersAllowed: "Usuarios permitidos",
      link: "Link de acceso",
      copy: "Copiar enlace",
      copied: "Copiado",
      noPackage: "No se encontro el paquete asignado a esta empresa.",
      noSettings: "El paquete no tiene mini_panel habilitado.",
      noTypes: "No hay tipos de mini panel habilitados para este paquete.",
      moduleInactive: "El modulo Mini Paneles no esta activo para esta empresa.",
      source: "Fuente",
      pending: "Los usuarios se asignaran en el modulo Usuarios.",
      error: "No se pudieron cargar los mini paneles.",
      needMore: "Si necesitas mas usuarios, comunicate con el administrador de CLONEXA.",
      linkFor: "Link para"
    },
    en: {
      eyebrow: "Mini Panels Module",
      title: "Mini Panels",
      subtitle: "Operational links enabled from Admin V2 according to this company's package.",
      back: "Back",
      refresh: "Refresh",
      package: "Package",
      inherited: "Capability inherited from package",
      enabled: "Enabled",
      disabled: "Disabled",
      usersAllowed: "Allowed users",
      link: "Access link",
      copy: "Copy link",
      copied: "Copied",
      noPackage: "The package assigned to this company was not found.",
      noSettings: "The package does not have mini_panel enabled.",
      noTypes: "There are no mini panel types enabled for this package.",
      moduleInactive: "The Mini Panels module is not active for this company.",
      source: "Source",
      pending: "Users will be assigned in the Users module.",
      error: "Mini panels could not be loaded.",
      needMore: "If you need more users, contact the CLONEXA administrator.",
      linkFor: "Link for"
    },
    fr: {
      eyebrow: "Module Mini Panneaux",
      title: "Mini Panneaux",
      subtitle: "Liens operationnels actives depuis Admin V2 selon le paquet de cette entreprise.",
      back: "Retour",
      refresh: "Actualiser",
      package: "Paquet",
      inherited: "Capacite heritee du paquet",
      enabled: "Active",
      disabled: "Desactive",
      usersAllowed: "Utilisateurs autorises",
      link: "Lien d'acces",
      copy: "Copier le lien",
      copied: "Copie",
      noPackage: "Le paquet assigne a cette entreprise est introuvable.",
      noSettings: "Le paquet n'a pas mini_panel active.",
      noTypes: "Aucun type de mini panneau n'est active pour ce paquet.",
      moduleInactive: "Le module Mini Panneaux n'est pas actif pour cette entreprise.",
      source: "Source",
      pending: "Les utilisateurs seront assignes dans le module Utilisateurs.",
      error: "Impossible de charger les mini panneaux.",
      needMore: "Si vous avez besoin de plus d utilisateurs, contactez l administrateur CLONEXA.",
      linkFor: "Lien pour"
    },
    pt: {
      eyebrow: "Modulo Mini Paineis",
      title: "Mini Paineis",
      subtitle: "Links operacionais habilitados no Admin V2 conforme o pacote desta empresa.",
      back: "Voltar",
      refresh: "Atualizar",
      package: "Pacote",
      inherited: "Capacidade herdada do pacote",
      enabled: "Habilitado",
      disabled: "Desabilitado",
      usersAllowed: "Usuarios permitidos",
      link: "Link de acesso",
      copy: "Copiar link",
      copied: "Copiado",
      noPackage: "O pacote atribuido a esta empresa nao foi encontrado.",
      noSettings: "O pacote nao tem mini_panel habilitado.",
      noTypes: "Nao ha tipos de mini painel habilitados para este pacote.",
      moduleInactive: "O modulo Mini Paineis nao esta ativo para esta empresa.",
      source: "Fonte",
      pending: "Os usuarios serao atribuidos no modulo Usuarios.",
      error: "Nao foi possivel carregar os mini paineis.",
      needMore: "Se precisar de mais usuarios, fale com o administrador da CLONEXA.",
      linkFor: "Link para"
    }
  };

  let cxMiniPanelClientSettingsCache019B = null;

  function cxIsMiniPanelModuleCode019B(code) {
    return CX_MINI_PANEL_MODULE_CODES_019B.has(String(code || "").trim());
  }

  function cxMiniPanelText019B(settings, key) {
    const lang = cxMiniPanelLang019B(settings);
    return (CX_MINI_PANEL_I18N_019B[lang] && CX_MINI_PANEL_I18N_019B[lang][key])
      || CX_MINI_PANEL_I18N_019B.es[key]
      || key;
  }

  function cxMiniPanelLang019B(settings = {}) {
    const candidates = [
      settings.language,
      settings.client_settings && settings.client_settings.language,
      state.company && state.company.settings_json && state.company.settings_json.language,
      state.company && state.company.settings_json && state.company.settings_json.client_settings && state.company.settings_json.client_settings.language,
      window.CLONEXA_CLIENT_SETTINGS && window.CLONEXA_CLIENT_SETTINGS.language,
      window.clonexaClientSettings && window.clonexaClientSettings.language,
      document.documentElement.getAttribute("lang")
    ];

    for (const candidate of candidates) {
      const code = String(candidate || "").trim().toLowerCase().slice(0, 2);
      if (CX_MINI_PANEL_I18N_019B[code]) return code;
    }

    return "es";
  }

  async function cxMiniPanelClientSettings019B(force = false) {
    if (!force && cxMiniPanelClientSettingsCache019B) return cxMiniPanelClientSettingsCache019B;

    try {
      if (!state.companyId) return {};
      cxMiniPanelClientSettingsCache019B = await api(`/companies/${encodeURIComponent(state.companyId)}/client-settings`);
      return cxMiniPanelClientSettingsCache019B || {};
    } catch (error) {
      cxMiniPanelClientSettingsCache019B = {};
      return {};
    }
  }

  function cxMiniPanelEnsureStyles019B() {
    if (document.getElementById("cxMiniPanelLinks019BStyles")) return;

    const style = document.createElement("style");
    style.id = "cxMiniPanelLinks019BStyles";
    style.textContent = `
      .cx-mini-links-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 16px;
        margin-top: 18px;
      }

      .cx-mini-link-card {
        border: 1px solid rgba(255,255,255,.14);
        background:
          radial-gradient(circle at 0% 0%, rgba(255,255,255,.12), transparent 34%),
          rgba(255,255,255,.065);
        border-radius: 24px;
        padding: 18px;
        box-shadow: 0 24px 70px rgba(0,0,0,.22);
        overflow: hidden;
      }

      .cx-mini-link-card h3 {
        margin: 8px 0 8px;
        font-size: 24px;
      }

      .cx-mini-link-meta {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin: 12px 0;
      }

      .cx-mini-link-pill {
        border: 1px solid rgba(255,255,255,.16);
        background: rgba(255,255,255,.08);
        color: var(--cx-text, #fff);
        border-radius: 999px;
        padding: 7px 10px;
        font-size: 12px;
        font-weight: 1000;
      }

      .cx-mini-link-box {
        border: 1px solid rgba(255,255,255,.14);
        background: rgba(0,0,0,.22);
        border-radius: 16px;
        padding: 12px;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 12px;
        line-height: 1.45;
        overflow-wrap: anywhere;
        color: rgba(255,255,255,.82);
      }

      .cx-mini-link-actions {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        margin-top: 14px;
      }

      .cx-mini-empty {
        border: 1px dashed rgba(255,255,255,.18);
        background: rgba(255,255,255,.055);
        border-radius: 24px;
        padding: 24px;
        color: rgba(255,255,255,.74);
      }
    `;
    document.head.appendChild(style);
  }

  function cxMiniPanelPackageKey019B(company = {}) {
    return String(
      company.package_code ||
      company.package ||
      company.plan_code ||
      company.plan ||
      company.package_id ||
      company.saas_package_id ||
      ""
    ).trim();
  }

  function cxMiniPanelFindPackage019B(packages = [], company = {}) {
    const key = cxMiniPanelPackageKey019B(company).toLowerCase();
    if (!key) return null;

    return (Array.isArray(packages) ? packages : []).find((item) => {
      const candidates = [
        item.id,
        item.code,
        item.name,
        item.slug
      ].map((value) => String(value || "").trim().toLowerCase());

      return candidates.includes(key);
    }) || null;
  }

  function cxMiniPanelAbsoluteUrl019B(pathOrUrl) {
    const raw = String(pathOrUrl || "").trim();
    if (!raw) return "";

    try {
      return new URL(raw, window.location.origin).href;
    } catch (error) {
      return raw;
    }
  }

  function cxMiniPanelLink019B(typeCode, typeData = {}) {
    const template = String(typeData.login_template || "").trim()
      || `/mini-panel/login?company_id={company_id}&type=${encodeURIComponent(typeCode)}`;

    const replaced = template
      .replaceAll("{company_id}", encodeURIComponent(state.companyId || ""))
      .replaceAll("{type}", encodeURIComponent(typeCode));

    return cxMiniPanelAbsoluteUrl019B(replaced);
  }

  function cxMiniPanelPackageSearchScore019B(pkg = {}, company = {}) {
    const companyTokens = [
      company.id,
      company.company_id,
      company.name,
      company.slug,
      company.plan,
      company.package,
      company.package_code,
      company.plan_code
    ]
      .map((value) => String(value || "").trim().toLowerCase())
      .filter(Boolean);

    const packageText = [
      pkg.id,
      pkg.code,
      pkg.name,
      pkg.slug,
      pkg.description
    ]
      .map((value) => String(value || "").trim().toLowerCase())
      .join(" ");

    let score = 0;

    companyTokens.forEach((token) => {
      if (!token) return;
      if (packageText.includes(token)) score += 20;
      const compact = token.replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
      if (compact && packageText.includes(compact)) score += 10;
    });

    const packageKey = cxMiniPanelPackageKey019B(company).toLowerCase();
    if (packageKey) {
      const directTokens = [pkg.id, pkg.code, pkg.name, pkg.slug]
        .map((value) => String(value || "").trim().toLowerCase());
      if (directTokens.includes(packageKey)) score += 1000;
    }

    return score;
  }

  async function cxMiniPanelFetchPackageSettings019B(packageId) {
    if (!packageId) return null;

    const data = await api(`/packages/${encodeURIComponent(packageId)}/mini-panel-settings`);
    return data && data.mini_panel ? data.mini_panel : data;
  }

  async function cxMiniPanelFindEnabledPackage019B(packages = [], company = {}, directPackage = null) {
    const rows = Array.isArray(packages) ? packages : [];
    const candidates = [];

    const ordered = [...rows].sort((a, b) => {
      const aDirect = directPackage && a.id === directPackage.id ? 1 : 0;
      const bDirect = directPackage && b.id === directPackage.id ? 1 : 0;
      if (aDirect !== bDirect) return bDirect - aDirect;
      return cxMiniPanelPackageSearchScore019B(b, company) - cxMiniPanelPackageSearchScore019B(a, company);
    });

    for (const pkg of ordered) {
      if (!pkg || !pkg.id) continue;

      try {
        const packageSettings = await cxMiniPanelFetchPackageSettings019B(pkg.id);
        const types = cxMiniPanelEnabledTypes019B(packageSettings);
        if (packageSettings && packageSettings.enabled === true && types.length) {
          candidates.push({
            selectedPackage: pkg,
            packageSettings,
            score: cxMiniPanelPackageSearchScore019B(pkg, company),
          });
        }
      } catch (error) {
        // Un paquete sin configuracion mini_panel no debe romper el modulo cliente.
      }
    }

    if (!candidates.length) {
      return { selectedPackage: directPackage || null, packageSettings: null };
    }

    candidates.sort((a, b) => b.score - a.score);

    if (candidates[0].score > 0) {
      return candidates[0];
    }

    if (candidates.length === 1) {
      return candidates[0];
    }

    return { selectedPackage: directPackage || null, packageSettings: null };
  }

  async function cxLoadMiniPanelPackage019B(force = false) {
    const company = state.company || {};
    const settings = await cxMiniPanelClientSettings019B(force);
    let packages = [];
    let selectedPackage = null;
    let packageSettings = null;
    let error = "";

    try {
      packages = await api("/packages");
      selectedPackage = cxMiniPanelFindPackage019B(packages, company);

      if (selectedPackage && selectedPackage.id) {
        try {
          packageSettings = await cxMiniPanelFetchPackageSettings019B(selectedPackage.id);
        } catch (err) {
          packageSettings = null;
        }
      }

      if (!packageSettings || packageSettings.enabled !== true || !cxMiniPanelEnabledTypes019B(packageSettings).length) {
        const fallback = await cxMiniPanelFindEnabledPackage019B(packages, company, selectedPackage);
        if (fallback && fallback.selectedPackage && fallback.packageSettings) {
          selectedPackage = fallback.selectedPackage;
          packageSettings = fallback.packageSettings;
        }
      }
    } catch (err) {
      error = err.message || cxMiniPanelText019B(settings, "error");
    }

    return {
      settings,
      packages,
      selectedPackage,
      packageSettings,
      error
    };
  }

  function cxMiniPanelEnabledTypes019B(packageSettings = {}) {
    const source = packageSettings && packageSettings.mini_panel ? packageSettings.mini_panel : packageSettings;
    if (!source || source.enabled !== true) return [];

    const rawTypes = source.types && typeof source.types === "object" ? source.types : {};

    return Object.entries(rawTypes)
      .filter(([, value]) => value && value.enabled === true)
      .map(([code, value]) => ({
        code,
        ...value,
        users_allowed: Number(value.users_allowed || 0)
      }))
      .filter((item) => item.users_allowed > 0);
  }

  function cxMiniPanelTypeLabel019B(code, item = {}, settings = {}) {
    const lang = cxMiniPanelLang019B(settings);
    const meta = CX_MINI_PANEL_TYPES_019B[code] || {};
    const translated = meta.label && (meta.label[lang] || meta.label.es);
    return item.label || translated || code;
  }

  function cxMiniPanelTypeDescription019B(code, settings = {}) {
    const lang = cxMiniPanelLang019B(settings);
    const meta = CX_MINI_PANEL_TYPES_019B[code] || {};
    return meta.description && (meta.description[lang] || meta.description.es) || "";
  }

  function cxMiniPanelCards019B(types = [], settings = {}) {
    return types.map((item) => {
      const label = cxMiniPanelTypeLabel019B(item.code, item, settings);
      const link = cxMiniPanelLink019B(item.code, item);
      const linkFor = cxMiniPanelText019B(settings, "linkFor");

      return `
        <article class="cx-mini-link-card">
          <div class="client-eyebrow">${h(cxMiniPanelText019B(settings, "enabled"))}</div>
          <h3>${h(linkFor)} ${h(label)}</h3>
          <p class="client-muted">${h(cxMiniPanelTypeDescription019B(item.code, settings))}</p>

          <div class="cx-mini-link-meta">
            <span class="cx-mini-link-pill">${h(cxMiniPanelText019B(settings, "usersAllowed"))}: ${h(item.users_allowed)}</span>
            <span class="cx-mini-link-pill">type=${h(item.code)}</span>
          </div>

          <div class="client-label">${h(cxMiniPanelText019B(settings, "link"))}</div>
          <div class="cx-mini-link-box">${h(link)}</div>

          <div class="cx-mini-link-actions">
            <button class="client-btn" type="button" data-minipanel-copy-link="${h(link)}">${h(cxMiniPanelText019B(settings, "copy"))}</button>
          </div>
        </article>
      `;
    }).join("");
  }

  async function renderMiniPanelLinksModule019B(force = false) {
    cxMiniPanelEnsureStyles019B();

    const company = state.company || {};
    const moduleActive = ["mini_panel", "mini_paneles", "creacion_minipanel", "creacion_mini_panel"].some((code) => isClientModuleActive(code));
    const data = await cxLoadMiniPanelPackage019B(force);
    const settings = data.settings || {};
    const selectedPackage = data.selectedPackage;
    const packageSettings = data.packageSettings || {};
    const types = cxMiniPanelEnabledTypes019B(packageSettings);

    let body = "";

    if (!moduleActive) {
      body = `<div class="cx-mini-empty">${h(cxMiniPanelText019B(settings, "moduleInactive"))}</div>`;
    } else if (!selectedPackage) {
      body = `<div class="cx-mini-empty">${h(cxMiniPanelText019B(settings, "noPackage"))}</div>`;
    } else if (!packageSettings || packageSettings.enabled !== true) {
      body = `<div class="cx-mini-empty">${h(cxMiniPanelText019B(settings, "noSettings"))}</div>`;
    } else if (!types.length) {
      body = `<div class="cx-mini-empty">${h(cxMiniPanelText019B(settings, "noTypes"))}</div>`;
    } else {
      body = `<div class="cx-mini-links-grid">${cxMiniPanelCards019B(types, settings)}</div><div class="cx-mini-empty" style="margin-top:16px">${h(cxMiniPanelText019B(settings, "needMore"))}</div>`;
    }

    $("app").innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, normalizeBranding(state.branding || {}))}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>
            <nav class="client-nav">${renderClientNav("mini_panel")}</nav>
            <div class="client-footer-id"><strong>Tenant activo</strong><br>${h(state.companyId || "")}</div>
          </aside>

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">${h(cxMiniPanelText019B(settings, "eyebrow"))}</div>
              <h1 class="client-title">${h(cxMiniPanelText019B(settings, "title"))}</h1>
              <p class="client-muted">${h(cxMiniPanelText019B(settings, "subtitle"))}</p>
              <div class="client-actions">
                <button class="client-btn" type="button" data-client-back-dashboard>${h(cxMiniPanelText019B(settings, "back"))}</button>
                <button class="client-btn" type="button" data-minipanel-refresh>${h(cxMiniPanelText019B(settings, "refresh"))}</button>
              </div>
            </header>

            <section class="client-panel">
              <div class="client-eyebrow">${h(cxMiniPanelText019B(settings, "inherited"))}</div>
              <h2>${h(cxMiniPanelText019B(settings, "package"))}: ${h(selectedPackage ? (selectedPackage.name || selectedPackage.code || selectedPackage.id) : cxMiniPanelPackageKey019B(company) || "-")}</h2>
              <p class="client-muted">${h(cxMiniPanelText019B(settings, "pending"))}</p>
              ${data.error ? `<div class="personal-toast error" style="margin-top:14px">${h(data.error)}</div>` : ""}
              ${body}
            </section>
          </section>
        </div>
      </main>
    `;
  }
  /* CLONEXA_019B_CLIENT_MINI_PANEL_LINKS_END */



  /* CLONEXA_019C_SALES_MINIPANEL_USERS_FRONTEND_START */
  const CX_SALES_ROLE_TOKENS_019C = new Set([
    "vendedor",
    "ventas",
    "sales",
    "comercial",
    "asesor_comercial",
    "asesor comercial"
  ]);

  function cxSalesEnsureStyles019C() {
    if (document.getElementById("cxSalesMiniPanelStyles019C")) return;

    const style = document.createElement("style");
    style.id = "cxSalesMiniPanelStyles019C";
    style.textContent = `
      .cx-sales-access-grid {
        display: grid;
        gap: 12px;
        margin-top: 16px;
      }
      .cx-sales-access-row {
        display: grid;
        grid-template-columns: minmax(190px, 1.2fr) minmax(130px, .7fr) minmax(180px, 1fr) minmax(220px, 1fr) minmax(240px, 1fr);
        gap: 10px;
        align-items: center;
        padding: 14px;
        border: 1px solid rgba(255,255,255,.12);
        border-radius: 18px;
        background: rgba(255,255,255,.06);
      }
      .cx-sales-access-row strong { display:block; }
      .cx-sales-muted { color: rgba(255,255,255,.68); font-size: 12px; }
      .cx-sales-chip {
        display:inline-flex;
        align-items:center;
        gap:6px;
        border-radius:999px;
        padding:6px 10px;
        border:1px solid rgba(255,255,255,.16);
        background: rgba(255,255,255,.08);
        font-size:12px;
      }
      .cx-sales-code {
        overflow:hidden;
        text-overflow:ellipsis;
        white-space:nowrap;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size:12px;
      }
      .cx-sales-password {
        margin-top: 8px;
        padding: 10px;
        border-radius: 14px;
        background: rgba(34,197,94,.12);
        border: 1px solid rgba(34,197,94,.25);
      }
      .cx-sales-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        align-items: center;
      }
      .cx-sales-password strong {
        user-select: all;
      }
      .cx-sales-command-grid {
        display: grid;
        grid-template-columns: minmax(220px, .7fr) minmax(260px, 1.3fr);
        gap: 12px;
        margin: 16px 0;
      }
      .cx-sales-command-card {
        padding: 14px;
        border-radius: 18px;
        border: 1px solid rgba(255,255,255,.12);
        background: rgba(255,255,255,.06);
      }
      .cx-sales-command-card strong {
        font-size: 28px;
        line-height: 1;
      }
      .cx-sales-input,
      .cx-sales-textarea {
        width: 100%;
        border: 1px solid rgba(255,255,255,.14);
        border-radius: 14px;
        background: rgba(5,8,18,.72);
        color: inherit;
        font-weight: 800;
        padding: 12px 14px;
        outline: none;
      }
      .cx-sales-textarea {
        min-height: 78px;
        resize: vertical;
      }
      .cx-sales-goal-box {
        display: grid;
        gap: 8px;
      }
      @media (max-width: 1100px) {
        .cx-sales-access-row { grid-template-columns: 1fr; }
        .cx-sales-command-grid { grid-template-columns: 1fr; }
      }
    `;
    document.head.appendChild(style);
  }

  function cxNormalizeRole019C(value = "") {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
  }

  function cxIsSalesEmployee019C(employee = {}) {
    const tokens = [
      employee.role,
      employee.employee_type,
      employee.position,
      employee.job_title
    ].map(cxNormalizeRole019C).filter(Boolean);

    return tokens.some((token) =>
      CX_SALES_ROLE_TOKENS_019C.has(token) ||
      token.includes("vendedor") ||
      token.includes("ventas") ||
      token.includes("comercial")
    );
  }

  function cxSalesEmployeeKey019C(employee = {}) {
    return String(employee.id || employee.employee_id || "");
  }

  async function cxLoadSalesMiniPanelUsers019C() {
    if (!state.companyId) return [];
    try {
      const rows = await api(`/companies/${encodeURIComponent(state.companyId)}/mini-panel-users?panel_type=sales`);
      return Array.isArray(rows) ? rows : [];
    } catch (error) {
      return [];
    }
  }

  async function cxCreateSalesMiniPanelUser019C(employeeId, link) {
    return api(`/companies/${encodeURIComponent(state.companyId)}/mini-panel-users/sales/from-employee`, {
      method: "POST",
      body: JSON.stringify({
        employee_id: employeeId,
        link: link || ""
      })
    });
  }

  /* CLONEXA_019D_R2_SALES_RESET_PASSWORD_FRONTEND_START */
  async function cxResetSalesMiniPanelPassword019DR2(userId) {
    return api(`/companies/${encodeURIComponent(state.companyId)}/mini-panel-users/${encodeURIComponent(userId)}/reset-password`, {
      method: "POST"
    });
  }

  async function cxSaveSalesMiniPanelGoal023P(userId, monthlyGoal, currency = "COP") {
    return api(`/companies/${encodeURIComponent(state.companyId)}/mini-panel-users/${encodeURIComponent(userId)}/sales-goal`, {
      method: "PUT",
      body: JSON.stringify({
        monthly_goal: Number(monthlyGoal || 0),
        goal_currency: currency || "COP"
      })
    });
  }

  async function cxLoadSalesMiniPanelMessage023P() {
    if (!state.companyId) return { message: "", promotions: [] };
    try {
      return await api(`/companies/${encodeURIComponent(state.companyId)}/mini-panel-sales-message`);
    } catch (error) {
      return { message: "", promotions: [], error: error.message || "No se pudo cargar el mensaje." };
    }
  }

  async function cxSaveSalesMiniPanelMessage023P(message) {
    return api(`/companies/${encodeURIComponent(state.companyId)}/mini-panel-sales-message`, {
      method: "PUT",
      body: JSON.stringify({ message: message || "" })
    });
  }

  function cxSalesMoney023P(value) {
    const number = Number(value || 0);
    try {
      return new Intl.NumberFormat("es-CO", {
        style: "currency",
        currency: "COP",
        maximumFractionDigits: 0
      }).format(number);
    } catch (_) {
      return `$ ${Math.round(number).toLocaleString("es-CO")}`;
    }
  }

  async function cxCopyText019DR2(value, label = "Texto") {
    const text = String(value || "");
    if (!text) return false;
    try {
      await navigator.clipboard.writeText(text);
      cxSalesNotice019DR1(`${label} copiado.`);
      return true;
    } catch (error) {
      window.prompt(`Copia ${label.toLowerCase()}:`, text);
      return false;
    }
  }
  /* CLONEXA_019D_R2_SALES_RESET_PASSWORD_FRONTEND_END */

  async function cxGetSalesMiniPanelLink019C() {
    try {
      const data = await cxLoadMiniPanelPackage019B(false);
      const settings = data.packageSettings || {};
      const types = cxMiniPanelEnabledTypes019B(settings);
      const sales = types.find((item) => String(item.code || "") === "sales");
      if (!sales) return null;
      return {
        link: cxMiniPanelLink019B("sales", sales),
        users_allowed: Number(sales.users_allowed || 0),
        label: cxMiniPanelTypeLabel019B("sales", sales, data.settings || {}),
      };
    } catch (error) {
      return null;
    }
  }

  function cxSalesUsersByEmployee019C(users = []) {
    const map = new Map();
    (Array.isArray(users) ? users : []).forEach((user) => {
      const employeeId = String(user.employee_id || "");
      if (employeeId) map.set(employeeId, user);
    });
    return map;
  }

  function cxSalesAccessRow019C(employee, assigned, salesLink) {
    const employeeId = cxSalesEmployeeKey019C(employee);
    const assignedUser = assigned ? (assigned.username || assigned.email || "") : "";
    const assignedId = assigned ? String(assigned.id || "") : "";
    const statusText = assigned ? (assigned.status || "active") : "pendiente";
    const link = assigned && assigned.link ? assigned.link : (salesLink ? salesLink.link : "");
    const monthlyGoal = assigned ? Number(assigned.monthly_goal || 0) : 0;

    return `
      <div class="cx-sales-access-row" data-sales-employee-id="${h(employeeId)}">
        <div>
          <strong>${h(employee.full_name || employee.name || "Sin nombre")}</strong>
          <div class="cx-sales-muted">${h(employee.phone || "Sin telefono")}</div>
        </div>
        <div>
          <span class="cx-sales-chip">${h(employee.role || employee.employee_type || "vendedor")}</span>
        </div>
        <div>
          <div class="cx-sales-muted">Link ventas</div>
          <div class="cx-sales-code">${h(link || "No disponible")}</div>
        </div>
        <div>
          <div class="cx-sales-muted">Usuario mini panel</div>
          <strong>${h(assignedUser || "Sin usuario")}</strong>
          <div class="cx-sales-muted">Estado: ${h(statusText)}</div>
        </div>
        <div>
          ${
            assigned
              ? `<div class="cx-sales-actions">
                  <span class="cx-sales-chip">Activo</span>
                  <button class="client-btn" type="button" data-sales-minipanel-reset="${h(assignedId)}" data-sales-minipanel-username="${h(assignedUser)}">Regenerar clave</button>
                </div>`
              : `<button class="client-btn" type="button" data-sales-minipanel-create="${h(employeeId)}" data-sales-minipanel-link="${h(link || "")}" ${!salesLink ? "disabled" : ""}>Generar usuario</button>`
          }
          ${assigned ? `
            <div class="cx-sales-goal-box" style="margin-top:10px">
              <div class="cx-sales-muted">Asignar meta</div>
              <input class="cx-sales-input" type="number" min="0" step="1000" value="${h(monthlyGoal)}" data-sales-goal-input="${h(assignedId)}" placeholder="Meta de ventas">
              <button class="client-btn" type="button" data-sales-goal-save="${h(assignedId)}">Guardar meta</button>
            </div>
          ` : ""}
        </div>
      </div>
    `;
  }

  async function renderSalesModule019C() {
    cxSalesEnsureStyles019C();

    const company = state.company || {};
    let employees = [];
    let users = [];
    let salesMessage = { message: "", promotions: [] };
    let loadError = "";
    let lastCreated = window.__cxSalesMiniPanelLastCreated019C || null;

    try {
      employees = await loadPersonalEmployees();
      users = await cxLoadSalesMiniPanelUsers019C();
      salesMessage = await cxLoadSalesMiniPanelMessage023P();
    } catch (error) {
      loadError = error.message || "No se pudo cargar ventas.";
    }

    const salesLink = await cxGetSalesMiniPanelLink019C();
    const sellers = (Array.isArray(employees) ? employees : []).filter((employee) =>
      String(employee.status || "active") !== "archived" && cxIsSalesEmployee019C(employee)
    );
    const assignedByEmployee = cxSalesUsersByEmployee019C(users);
    const totalSalesGoal = (Array.isArray(users) ? users : [])
      .filter((user) => String(user.panel_type || "") === "sales")
      .reduce((sum, user) => sum + Number(user.monthly_goal || 0), 0);
    const sellersWithGoal = (Array.isArray(users) ? users : []).filter((user) => Number(user.monthly_goal || 0) > 0).length;

    const rows = sellers.length
      ? sellers.map((employee) => cxSalesAccessRow019C(employee, assignedByEmployee.get(cxSalesEmployeeKey019C(employee)), salesLink)).join("")
      : `<div class="cx-mini-empty">No hay vendedores en Workforce. Crea personal con rol Vendedor para asignar acceso.</div>`;

    $("app").innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, normalizeBranding(state.branding || {}))}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>
            <nav class="client-nav">${renderClientNav("sales")}</nav>
            <div class="client-footer-id"><strong>Tenant activo</strong><br>${h(state.companyId || "")}</div>
          </aside>

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">Modulo Ventas</div>
              <h1 class="client-title">Ventas</h1>
              <p class="client-muted">Asigna accesos de mini panel a vendedores creados en Workforce.</p>
              <div class="client-actions">
                <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
                <button class="client-btn" type="button" data-sales-refresh>Actualizar</button>
              </div>
            </header>

            <section class="client-panel">
              <div class="client-eyebrow">Accesos de vendedores</div>
              <h2>Usuarios mini panel ventas</h2>
              <p class="client-muted">Fuente: Workforce. Rol requerido: vendedor, ventas, comercial o asesor comercial.</p>

              <div class="cx-sales-command-grid">
                <article class="cx-sales-command-card">
                  <div class="client-eyebrow">Meta total ventas</div>
                  <strong>${h(cxSalesMoney023P(totalSalesGoal))}</strong>
                  <p class="cx-sales-muted">${h(sellersWithGoal)} vendedor(es) con meta asignada.</p>
                </article>
                <article class="cx-sales-command-card">
                  <div class="client-eyebrow">Mensaje a mini paneles</div>
                  <textarea class="cx-sales-textarea" data-sales-message-input maxlength="280" placeholder="Promocion, campana o instruccion para vendedores...">${h(salesMessage.message || "")}</textarea>
                  <div class="cx-sales-actions" style="margin-top:10px">
                    <button class="client-btn" type="button" data-sales-message-save>Enviar mensaje</button>
                    <span class="cx-sales-muted">${h((salesMessage.message || "").length)}/280</span>
                  </div>
                </article>
              </div>

              ${loadError ? `<div class="personal-toast error" style="margin-top:14px">${h(loadError)}</div>` : ""}
              ${!salesLink ? `<div class="personal-toast error" style="margin-top:14px">El paquete no tiene link de Ventas habilitado desde Admin V2.</div>` : `
                <div class="cx-mini-empty" style="margin-top:14px">
                  Link ventas: <strong>${h(salesLink.link)}</strong><br>
                  Usuarios permitidos por paquete: <strong>${h(salesLink.users_allowed)}</strong>
                </div>
              `}
              ${lastCreated ? `
                <div class="cx-sales-password">
                  Usuario: <strong>${h(lastCreated.username || lastCreated.email)}</strong><br>
                  ${lastCreated.temporary_password
                    ? `Clave temporal: <strong>${h(lastCreated.temporary_password)}</strong><br><span class="cx-sales-muted">Guarda esta clave. Solo se muestra una vez.</span>`
                    : `<span class="cx-sales-muted">Usuario activo. Para entregar una clave nueva usa Regenerar clave.</span>`
                  }
                </div>
              ` : ""}

              <div class="cx-sales-access-grid">
                ${rows}
              </div>
            </section>
          </section>
        </div>
      </main>
    `;
  }

  /* CLONEXA_019D_R1_SALES_GENERATE_USER_CLICK_FIX_START */
  function cxSalesNotice019DR1(message, isError = false) {
    const panel = document.querySelector(".cx-sales-access-grid") || document.querySelector(".client-panel");
    if (!panel) {
      if (message) window.alert(message);
      return;
    }

    const existing = document.getElementById("cxSalesMiniPanelNotice019DR1");
    if (existing) existing.remove();

    const notice = document.createElement("div");
    notice.id = "cxSalesMiniPanelNotice019DR1";
    notice.className = `personal-toast ${isError ? "error" : ""}`;
    notice.style.margin = "14px 0";
    notice.textContent = message || "";
    panel.insertAdjacentElement("beforebegin", notice);
  }

  document.addEventListener("click", async (event) => {
    const refreshButton = event.target.closest("[data-sales-refresh]");
    if (refreshButton) {
      event.preventDefault();
      event.stopPropagation();
      await renderSalesModule019C();
      return;
    }

    const messageButton = event.target.closest("[data-sales-message-save]");
    if (messageButton) {
      event.preventDefault();
      event.stopPropagation();
      const input = document.querySelector("[data-sales-message-input]");
      const originalText = messageButton.textContent || "Enviar mensaje";
      try {
        messageButton.disabled = true;
        messageButton.textContent = "Enviando...";
        await cxSaveSalesMiniPanelMessage023P(input?.value || "");
        await renderSalesModule019C();
        cxSalesNotice019DR1("Mensaje enviado a los mini paneles de ventas.");
      } catch (error) {
        messageButton.disabled = false;
        messageButton.textContent = originalText;
        cxSalesNotice019DR1(error.message || "No se pudo enviar el mensaje.", true);
      }
      return;
    }

    const goalButton = event.target.closest("[data-sales-goal-save]");
    if (goalButton) {
      event.preventDefault();
      event.stopPropagation();
      const userId = goalButton.getAttribute("data-sales-goal-save") || "";
      const input = document.querySelector(`[data-sales-goal-input="${userId}"]`);
      const originalText = goalButton.textContent || "Guardar meta";
      if (!userId) {
        cxSalesNotice019DR1("No se encontro el usuario para asignar meta.", true);
        return;
      }
      try {
        goalButton.disabled = true;
        goalButton.textContent = "Guardando...";
        await cxSaveSalesMiniPanelGoal023P(userId, input?.value || 0);
        await renderSalesModule019C();
        cxSalesNotice019DR1("Meta asignada. El mini panel la vera en Ventas vs meta.");
      } catch (error) {
        goalButton.disabled = false;
        goalButton.textContent = originalText;
        cxSalesNotice019DR1(error.message || "No se pudo guardar la meta.", true);
      }
      return;
    }

    const resetButton = event.target.closest("[data-sales-minipanel-reset]");
    if (resetButton) {
      event.preventDefault();
      event.stopPropagation();

      const userId = resetButton.getAttribute("data-sales-minipanel-reset") || "";
      const originalText = resetButton.textContent || "Regenerar clave";

      if (!userId) {
        cxSalesNotice019DR1("No se encontro el usuario mini panel para regenerar clave.", true);
        return;
      }

      try {
        resetButton.disabled = true;
        resetButton.textContent = "Regenerando...";

        const updated = await cxResetSalesMiniPanelPassword019DR2(userId);
        window.__cxSalesMiniPanelLastCreated019C = updated || null;

        await renderSalesModule019C();

        const username = updated?.username || updated?.email || "usuario";
        const tempPassword = updated?.temporary_password || "";
        cxSalesNotice019DR1(
          tempPassword
            ? `Clave regenerada para ${username}: ${tempPassword}`
            : `Clave regenerada para ${username}.`
        );
      } catch (error) {
        resetButton.disabled = false;
        resetButton.textContent = originalText;
        cxSalesNotice019DR1(error.message || "No se pudo regenerar la clave.", true);
      }
      return;
    }

    const button = event.target.closest("[data-sales-minipanel-create]");
    if (!button) return;

    event.preventDefault();
    event.stopPropagation();

    const employeeId = button.getAttribute("data-sales-minipanel-create") || "";
    const link = button.getAttribute("data-sales-minipanel-link") || "";
    const originalText = button.textContent || "Generar usuario";

    if (!employeeId) {
      cxSalesNotice019DR1("No se encontro el empleado de Workforce para generar el usuario.", true);
      return;
    }

    try {
      button.disabled = true;
      button.textContent = "Generando...";

      const created = await cxCreateSalesMiniPanelUser019C(employeeId, link);
      window.__cxSalesMiniPanelLastCreated019C = created || null;

      await renderSalesModule019C();

      const username = created?.username || created?.email || "usuario generado";
      const tempPassword = created?.temporary_password || "";
      cxSalesNotice019DR1(
        tempPassword
          ? `Usuario generado: ${username}. Clave temporal: ${tempPassword}`
          : `Usuario ya existente: ${username}. Usa Regenerar clave para crear una clave nueva.`
      );
    } catch (error) {
      button.disabled = false;
      button.textContent = originalText;
      cxSalesNotice019DR1(error.message || "No se pudo generar el usuario mini panel.", true);
    }
  }, true);
  /* CLONEXA_019D_R1_SALES_GENERATE_USER_CLICK_FIX_END */

  /* CLONEXA_019C_SALES_MINIPANEL_USERS_FRONTEND_END */



  /* CLONEXA_021D_UNIVERSAL_MODULE_RENDER_ADAPTER_START */
  const CX_UNIVERSAL_QUOTES_CODES_021D = new Set([
    "cotizacion",
    "cotizaciones",
    "cotizar",
    "quote",
    "quotes",
    "quotation",
    "quotations",
    "presupuesto",
    "presupuestos"
  ]);

  const CX_UNIVERSAL_NOTES_CODES_021D = new Set([
    "notes",
    "notas",
    "nota",
    "agenda",
    "notas_o_agenda",
    "recordatorio",
    "recordatorios",
    "reminder",
    "reminders",
    "calendar",
    "calendario"
  ]);

  function cxNormUniversalModule021D(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
  }

  function cxIsQuotesUniversalCode021D(code) {
    return CX_UNIVERSAL_QUOTES_CODES_021D.has(cxNormUniversalModule021D(code));
  }

  function cxIsNotesUniversalCode021D(code) {
    return CX_UNIVERSAL_NOTES_CODES_021D.has(cxNormUniversalModule021D(code));
  }

  function cxUniversalModuleTitle021D(code) {
    if (cxIsQuotesUniversalCode021D(code)) return "Cotizaciones";
    if (cxIsNotesUniversalCode021D(code)) return "Notas / Agenda";
    return moduleLabel(code);
  }

  function cxClientHasUniversalModule021D(codeSet) {
    const modules = activeClientModules();
    return modules.some((module) => codeSet.has(cxNormUniversalModule021D(module.code || module.title || module.name || "")));
  }

  function cxUniversalMoney021D(value) {
    const number = Number(value || 0);
    try {
      return number.toLocaleString("es-CO", {
        style: "currency",
        currency: "COP",
        maximumFractionDigits: 0,
      });
    } catch (_) {
      return `$ ${Math.round(number).toLocaleString("es-CO")}`;
    }
  }

  function cxUniversalTodayIso021D() {
    const now = new Date();
    const yyyy = now.getFullYear();
    const mm = String(now.getMonth() + 1).padStart(2, "0");
    const dd = String(now.getDate()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd}`;
  }

  function cxUniversalTimeNow021D() {
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, "0");
    const mm = String(now.getMinutes()).padStart(2, "0");
    return `${hh}:${mm}`;
  }

  async function cxUniversalApi021D(path, options = {}) {
    const response = await fetch(`${API}${path}`, {
      method: options.method || "GET",
      headers: {
        "Content-Type": "application/json",
        "X-CLONEXA-CLIENT-MODULE": "1",
        ...(options.headers || {}),
      },
      body: options.body,
    });

    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(`${response.status} ${response.statusText} ${detail}`);
    }

    const type = response.headers.get("content-type") || "";
    if (type.includes("application/json")) return response.json();
    return response.text();
  }

  function cxUniversalPanelType021D() {
    return "client";
  }

  function cxUniversalShell021D(activeCode, eyebrow, title, subtitle, bodyHtml) {
    const company = state.company || {};
    $("app").innerHTML = `
      <main class="client-shell cx-universal-shell-021d">
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, normalizeBranding(state.branding || {}))}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>
            <nav class="client-nav">${renderClientNav(activeCode)}</nav>
            <div class="client-footer-id"><strong>Tenant activo</strong><br>${h(state.companyId || "")}</div>
          </aside>

          <section class="client-main cx-universal-main-021d">
            <header class="client-hero cx-universal-hero-021d">
              <div>
                <div class="client-eyebrow">${h(eyebrow)}</div>
                <h1 class="client-title">${h(title)}</h1>
                <p class="client-muted">${h(subtitle)}</p>
              </div>
              <div class="client-actions">
                <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
              </div>
            </header>

            ${bodyHtml}
          </section>
        </div>
      </main>
    `;
  }

  function ensureUniversalModuleStyles021D() {
    let style = document.getElementById("cxUniversalModuleStyles021D");
    if (!style) {
      style = document.createElement("style");
      style.id = "cxUniversalModuleStyles021D";
      document.head.appendChild(style);
    }

    style.textContent = `
      .cx-universal-main-021d {
        display: flex;
        flex-direction: column;
        gap: 18px;
      }

      .cx-universal-hero-021d {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 18px;
      }

      .cx-universal-grid-021d {
        display: grid;
        grid-template-columns: minmax(0, 1.45fr) minmax(360px, .85fr);
        gap: 18px;
        align-items: start;
      }

      .cx-universal-card-021d {
        border: 1px solid rgba(255,255,255,.14);
        background:
          radial-gradient(circle at 12% 4%, rgba(255,34,184,.18), transparent 30%),
          linear-gradient(145deg, rgba(255,255,255,.10), rgba(255,255,255,.045));
        border-radius: 24px;
        padding: 20px;
        box-shadow: 0 20px 60px rgba(0,0,0,.24);
      }

      .cx-universal-card-021d h2,
      .cx-universal-card-021d h3 {
        margin: 0 0 12px;
      }

      .cx-universal-form-021d {
        display: grid;
        gap: 14px;
      }

      .cx-field-grid-021d {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 12px;
      }

      .cx-field-grid-021d.three {
        grid-template-columns: 1.4fr .55fr .75fr auto;
        align-items: end;
      }

      .cx-field-021d {
        display: grid;
        gap: 6px;
      }

      .cx-field-021d label {
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: .09em;
        color: rgba(255,255,255,.74);
        font-weight: 1000;
      }

      .cx-field-021d input,
      .cx-field-021d select,
      .cx-field-021d textarea {
        width: 100%;
        border: 1px solid rgba(255,255,255,.15);
        border-radius: 15px;
        background: rgba(5,8,24,.48);
        color: var(--cx-text, #fff);
        padding: 12px 13px;
        outline: none;
        font-weight: 800;
      }

      .cx-field-021d textarea {
        min-height: 84px;
        resize: vertical;
      }

      .cx-actions-021d {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        justify-content: flex-end;
        align-items: center;
      }

      .cx-mini-btn-021d {
        border: 1px solid rgba(255,255,255,.14);
        border-radius: 14px;
        background: rgba(255,255,255,.10);
        color: var(--cx-text, #fff);
        padding: 11px 14px;
        font-weight: 1000;
        cursor: pointer;
      }

      .cx-mini-btn-021d.primary {
        background: linear-gradient(135deg, #ff22b8, #8b5cf6 58%, #38bdf8);
        border-color: rgba(255,255,255,.20);
      }

      .cx-mini-btn-021d.danger {
        border-color: rgba(244,63,94,.45);
        background: rgba(244,63,94,.16);
      }

      .cx-summary-pills-021d {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
      }

      .cx-pill-021d {
        border: 1px solid rgba(255,255,255,.14);
        border-radius: 999px;
        padding: 9px 12px;
        background: rgba(255,255,255,.08);
        font-weight: 1000;
      }

      .cx-list-021d {
        display: grid;
        gap: 12px;
        margin-top: 12px;
      }

      .cx-row-021d {
        border: 1px solid rgba(255,255,255,.13);
        border-radius: 18px;
        padding: 14px;
        background: rgba(255,255,255,.07);
      }

      .cx-row-head-021d {
        display: flex;
        justify-content: space-between;
        gap: 14px;
        align-items: flex-start;
      }

      .cx-row-head-021d strong {
        display: block;
        font-size: 18px;
      }

      .cx-row-head-021d small {
        display: block;
        color: rgba(255,255,255,.68);
        margin-top: 4px;
      }

      .cx-muted-021d {
        color: rgba(255,255,255,.68);
        font-weight: 800;
      }

      .cx-notice-021d {
        min-height: 22px;
        font-weight: 900;
        color: #86efac;
      }

      .cx-notice-021d.error {
        color: #fca5a5;
      }

      .cx-quote-item-021d {
        margin-bottom: 10px;
      }

      .cx-signature-preview-021d {
        min-height: 68px;
        border: 1px dashed rgba(255,255,255,.22);
        border-radius: 16px;
        display: grid;
        place-items: center;
        background: rgba(0,0,0,.16);
        overflow: hidden;
      }

      .cx-signature-preview-021d img {
        max-width: 100%;
        max-height: 92px;
        object-fit: contain;
      }


      /* CLONEXA_021E_CLIENT_QUOTES_ACTIONS_FIX_STYLES_START */
      .cx-detail-overlay-021e {
        position: fixed;
        inset: 0;
        z-index: 9999;
        display: grid;
        place-items: center;
        padding: 24px;
        background: rgba(4, 6, 18, .74);
        backdrop-filter: blur(16px);
      }

      .cx-detail-card-021e {
        width: min(980px, calc(100vw - 32px));
        max-height: calc(100vh - 48px);
        overflow: auto;
        border: 1px solid rgba(255,255,255,.18);
        border-radius: 28px;
        padding: 24px;
        color: var(--cx-text, #fff);
        background:
          radial-gradient(circle at 10% 8%, rgba(255,34,184,.24), transparent 32%),
          radial-gradient(circle at 100% 0%, rgba(56,189,248,.16), transparent 34%),
          linear-gradient(145deg, rgba(20,14,48,.98), rgba(8,13,35,.98));
        box-shadow: 0 40px 110px rgba(0,0,0,.58);
      }

      .cx-detail-head-021e,
      .cx-detail-grid-021e {
        display: grid;
        grid-template-columns: 1fr auto;
        gap: 16px;
        align-items: start;
      }

      .cx-detail-grid-021e {
        grid-template-columns: repeat(2, minmax(0, 1fr));
        margin: 18px 0;
      }

      .cx-detail-card-021e h2,
      .cx-detail-card-021e h3 {
        margin: 0 0 10px;
      }

      .cx-detail-card-021e p {
        margin: 6px 0;
        color: rgba(255,255,255,.78);
        font-weight: 800;
      }

      .cx-detail-table-wrap-021e {
        overflow: auto;
        border: 1px solid rgba(255,255,255,.12);
        border-radius: 18px;
        margin: 10px 0 18px;
      }

      .cx-detail-table-021e {
        width: 100%;
        border-collapse: collapse;
        min-width: 620px;
      }

      .cx-detail-table-021e th,
      .cx-detail-table-021e td {
        padding: 12px;
        border-bottom: 1px solid rgba(255,255,255,.10);
        text-align: left;
        color: rgba(255,255,255,.82);
      }

      .cx-detail-table-021e th {
        color: rgba(255,255,255,.62);
        text-transform: uppercase;
        letter-spacing: .08em;
        font-size: 11px;
      }

      .cx-detail-discounts-021e {
        display: grid;
        gap: 10px;
        margin-bottom: 16px;
      }

      .cx-detail-pill-021e {
        display: grid;
        grid-template-columns: 1fr 1.4fr auto;
        gap: 10px;
        align-items: center;
        padding: 12px;
        border: 1px solid rgba(255,255,255,.12);
        border-radius: 16px;
        background: rgba(255,255,255,.07);
      }
      /* CLONEXA_021E_CLIENT_QUOTES_ACTIONS_FIX_STYLES_END */

      @media (max-width: 1120px) {
        .cx-universal-grid-021d,
        .cx-field-grid-021d,
        .cx-field-grid-021d.three {
          grid-template-columns: 1fr;
        }
      }
    `;
  }

  function cxClientModuleEnabled021D(kind) {
    return kind === "quotes"
      ? cxClientHasUniversalModule021D(CX_UNIVERSAL_QUOTES_CODES_021D)
      : cxClientHasUniversalModule021D(CX_UNIVERSAL_NOTES_CODES_021D);
  }

  async function renderClientUniversalNotesModule021D(activeCode = "notas") {
    ensureUniversalModuleStyles021D();

    const selectedDate = window.__cxUniversalNotesDate021D || cxUniversalTodayIso021D();
    let payload = { day_items: [], upcoming: [] };
    let error = "";

    try {
      payload = await cxUniversalApi021D(`/mini-panel-notes/companies/${encodeURIComponent(state.companyId)}?panel_type=${encodeURIComponent(cxUniversalPanelType021D())}&date=${encodeURIComponent(selectedDate)}`);
    } catch (err) {
      error = err.message || "No se pudo cargar Notas.";
    }

    const dayItems = Array.isArray(payload.day_items) ? payload.day_items : [];
    const upcoming = Array.isArray(payload.upcoming) ? payload.upcoming : [];

    const renderNote = (item) => `
      <article class="cx-row-021d">
        <div class="cx-row-head-021d">
          <div>
            <strong>${h(item.title || "Nota")}</strong>
            <small>${h(item.note_date || "")} · ${h(item.display_time || item.note_time || "")} · ${h(item.note_type || "recordatorio")}</small>
            <p class="cx-muted-021d">${h(item.description || "Sin detalle")}</p>
          </div>
          <div class="cx-actions-021d">
            <button class="cx-mini-btn-021d" type="button" data-client-note-complete="${h(item.id)}">Completar</button>
            <button class="cx-mini-btn-021d danger" type="button" data-client-note-archive="${h(item.id)}">Archivar</button>
          </div>
        </div>
      </article>
    `;

    cxUniversalShell021D(
      activeCode,
      "Módulo universal",
      "Notas / Agenda",
      "Agenda operativa funcional para panel principal y mini paneles.",
      `
        <section class="cx-universal-grid-021d">
          <article class="cx-universal-card-021d">
            <h2>Nueva nota / recordatorio</h2>
            <form class="cx-universal-form-021d" data-client-notes-form>
              <div class="cx-field-grid-021d">
                <div class="cx-field-021d">
                  <label>Fecha</label>
                  <input type="date" name="note_date" value="${h(selectedDate)}" required>
                </div>
                <div class="cx-field-021d">
                  <label>Hora</label>
                  <input type="time" name="note_time" value="${h(cxUniversalTimeNow021D())}" required>
                </div>
              </div>

              <div class="cx-field-grid-021d">
                <div class="cx-field-021d">
                  <label>Tipo</label>
                  <select name="note_type">
                    <option value="reminder">Recordatorio</option>
                    <option value="note">Nota</option>
                  </select>
                </div>
                <div class="cx-field-021d">
                  <label>Título</label>
                  <input name="title" placeholder="Ej: llamar cliente, enviar propuesta..." required>
                </div>
              </div>

              <div class="cx-field-021d">
                <label>Detalle</label>
                <textarea name="description" placeholder="Detalle interno opcional"></textarea>
              </div>

              <div class="cx-actions-021d">
                <button class="cx-mini-btn-021d primary" type="submit">Guardar nota</button>
              </div>
              <div class="cx-notice-021d ${error ? "error" : ""}" data-client-notes-notice>${h(error)}</div>
            </form>
          </article>

          <article class="cx-universal-card-021d">
            <h2>Próximos 5</h2>
            <div class="cx-list-021d">
              ${upcoming.length ? upcoming.slice(0, 5).map(renderNote).join("") : `<div class="cx-row-021d cx-muted-021d">Sin próximos recordatorios.</div>`}
            </div>
          </article>

          <article class="cx-universal-card-021d" style="grid-column: 1 / -1;">
            <div class="cx-row-head-021d">
              <div>
                <h2>Día seleccionado</h2>
                <p class="cx-muted-021d">${h(selectedDate)} · ${dayItems.length} recordatorios</p>
              </div>
              <div class="cx-field-021d" style="min-width:220px;">
                <label>Cambiar día</label>
                <input type="date" data-client-notes-date value="${h(selectedDate)}">
              </div>
            </div>

            <div class="cx-list-021d">
              ${dayItems.length ? dayItems.map(renderNote).join("") : `<div class="cx-row-021d cx-muted-021d">No hay recordatorios en este día.</div>`}
            </div>
          </article>
        </section>
      `
    );

    const dateInput = document.querySelector("[data-client-notes-date]");
    dateInput?.addEventListener("change", async () => {
      window.__cxUniversalNotesDate021D = dateInput.value || cxUniversalTodayIso021D();
      await renderClientUniversalNotesModule021D(activeCode);
    });

    document.querySelector("[data-client-notes-form]")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const notice = form.querySelector("[data-client-notes-notice]");
      const formData = new FormData(form);
      const payload = {
        title: String(formData.get("title") || "").trim(),
        description: String(formData.get("description") || "").trim(),
        note_date: String(formData.get("note_date") || selectedDate),
        note_time: String(formData.get("note_time") || cxUniversalTimeNow021D()),
        note_type: String(formData.get("note_type") || "reminder"),
      };

      try {
        if (notice) {
          notice.classList.remove("error");
          notice.textContent = "Guardando...";
        }
        await cxUniversalApi021D(`/mini-panel-notes/companies/${encodeURIComponent(state.companyId)}?panel_type=${encodeURIComponent(cxUniversalPanelType021D())}`, {
          method: "POST",
          body: JSON.stringify(payload),
        });
        window.__cxUniversalNotesDate021D = payload.note_date;
        await renderClientUniversalNotesModule021D(activeCode);
      } catch (err) {
        if (notice) {
          notice.classList.add("error");
          notice.textContent = err.message || "No se pudo guardar la nota.";
        }
      }
    });
  }


  /* CLONEXA_021F_R1_CLIENT_QUOTES_SCOPE_START */
  function cxClientQuotesScope021F() {
    // En /client el modulo Cotizaciones debe leer todo lo creado por la empresa,
    // sin importar si nacio en sales, stores, inventory, other o client.
    return "all";
  }

  function cxClientQuotePanelForAction021F(quoteId) {
    const quotes = Array.isArray(window.__cxUniversalQuotesCache021E)
      ? window.__cxUniversalQuotesCache021E
      : [];
    const quote = quotes.find((item) => String(item.id) === String(quoteId));
    return quote && quote.panel_type ? String(quote.panel_type) : cxClientQuotesScope021F();
  }
  /* CLONEXA_021F_R1_CLIENT_QUOTES_SCOPE_END */

  /* CLONEXA_022B_CLIENT_QUOTES_CONSOLIDATION_SOURCE_START */
  function cxClientQuotesSourceScope022B() {
    return "all";
  }

  function cxClientQuoteCleanText023D(value) {
    let text = String(value ?? "");
    for (let i = 0; i < 2 && /[ÃÂ]/.test(text); i += 1) {
      try {
        const repaired = decodeURIComponent(escape(text));
        if (!repaired || repaired === text) break;
        text = repaired;
      } catch (_) {
        break;
      }
    }
    return text;
  }

  async function cxClientQuoteReferences023C() {
    try {
      const data = await cxReferencesApi022E(`/references-v1/companies/${encodeURIComponent(state.companyId)}`);
      const rows = Array.isArray(data?.items)
        ? data.items
        : Array.isArray(data?.references)
          ? data.references
          : Array.isArray(data)
            ? data
            : [];
      return rows
        .filter((item) => item && item.archived !== true)
        .map((item) => ({
          id: String(item.id || ""),
          name: cxClientQuoteCleanText023D(item.name || item.reference_name || ""),
          category: cxClientQuoteCleanText023D(item.category || item.reference_category || ""),
          size: cxClientQuoteCleanText023D(item.size || item.reference_size || ""),
          color: cxClientQuoteCleanText023D(item.color || item.reference_color || ""),
          sku: cxClientQuoteCleanText023D(item.sku || item.code || ""),
          unit_price: Number(item.unit_price ?? item.price ?? 0) || 0,
        }))
        .filter((item) => item.name);
    } catch (_) {
      return [];
    }
  }

  function cxClientQuoteReferenceLabel023C(ref = {}) {
    return [ref.name, ref.size, ref.color, ref.sku ? `SKU ${ref.sku}` : ""].filter(Boolean).join(" · ");
  }

  function cxClientQuoteReferenceOptions023C(references = [], selectedId = "") {
    const options = references.map((ref) => `
      <option
        value="${h(ref.id)}"
        data-ref-name="${h(ref.name)}"
        data-ref-label="${h(cxClientQuoteReferenceLabel023C(ref))}"
        data-ref-price="${h(ref.unit_price)}"
        data-ref-sku="${h(ref.sku)}"
        ${String(selectedId || "") === String(ref.id || "") ? "selected" : ""}
      >${h(cxClientQuoteReferenceLabel023C(ref))}</option>
    `).join("");
    return `<option value="">Manual / sin referencia</option>${options}`;
  }

  function cxClientQuoteItemRow023C(item = {}, references = []) {
    const selectedId = item.reference_id || item.id || "";
    return `
      <div class="cx-field-grid-021d three cx-quote-item-021d" data-client-quote-item>
        <div class="cx-field-021d">
          <label>Concepto</label>
          <select data-client-quote-reference>
            ${cxClientQuoteReferenceOptions023C(references, selectedId)}
          </select>
          <input name="item_description" value="${h(item.description || "")}" placeholder="Servicio, producto, referencia..." required>
        </div>
        <div class="cx-field-021d">
          <label>Cantidad</label>
          <input name="item_quantity" type="number" step="0.01" min="0" value="${h(item.quantity ?? 1)}">
        </div>
        <div class="cx-field-021d">
          <label>Valor unitario</label>
          <input name="item_unit_price" type="number" step="0.01" min="0" value="${h(item.unit_price ?? 0)}">
        </div>
        <button class="cx-mini-btn-021d danger" type="button" data-client-quote-remove-item>Quitar</button>
      </div>
    `;
  }

  function cxClientQuoteApplyReference023C(select) {
    const option = select?.selectedOptions?.[0];
    const row = select?.closest("[data-client-quote-item]");
    if (!option || !row || !option.value) return;
    const description = row.querySelector('[name="item_description"]');
    const unitPrice = row.querySelector('[name="item_unit_price"]');
    if (description) description.value = option.dataset.refLabel || option.dataset.refName || option.textContent || "";
    if (unitPrice) unitPrice.value = String(Number(option.dataset.refPrice || 0) || 0);
  }

  function cxClientQuoteIsArchived022B(quote) {
    return String(quote?.status || "").toLowerCase() === "archived";
  }

  function cxClientQuoteDocumentType022B(quote) {
    const explicit = String(quote?.document_type || "").toLowerCase();
    if (explicit === "account") return "account";
    return String(quote?.status || "").toLowerCase() === "converted" ? "account" : "quote";
  }

  function cxClientQuotePanelLabel022B(value) {
    const raw = String(value || "").toLowerCase();
    const map = {
      sales: "Mini Panel Ventas",
      venta: "Mini Panel Ventas",
      ventas: "Mini Panel Ventas",
      stores: "Mini Panel Tiendas",
      store: "Mini Panel Tiendas",
      tiendas: "Mini Panel Tiendas",
      tienda: "Mini Panel Tiendas",
      inventory: "Mini Panel Inventario",
      inventario: "Mini Panel Inventario",
      logistics: "Mini Panel Logística",
      logistica: "Mini Panel Logística",
      other: "Mini Panel Otro",
      otro: "Mini Panel Otro",
    };
    return map[raw] || (raw ? `Mini Panel ${raw}` : "Mini Panel");
  }

  // CLONEXA_022C_CLIENT_ORIGIN_USER_LABEL_START
  function cxClientQuoteUserLabel022C(quote) {
    const rawPanel = String(quote?.panel_type || quote?.source_panel_type || "").toLowerCase();
    const rawUser = String(
      quote?.source_user_label ||
      quote?.created_by_label ||
      quote?.created_by_name ||
      quote?.mini_panel_user_name ||
      quote?.mini_panel_username ||
      quote?.username ||
      ""
    ).trim();

    if (rawUser && rawUser.toLowerCase() !== "usuario mini panel") {
      return rawUser;
    }

    if (["store", "stores", "tienda", "tiendas"].includes(rawPanel)) {
      return "Proximamente";
    }

    if (["sales", "sale", "venta", "ventas"].includes(rawPanel)) {
      return "Usuario de ventas no identificado";
    }

    return "Usuario no identificado";
  }

  function cxClientQuoteOriginLabel022B(quote) {
    const panel = quote?.source_panel_label || cxClientQuotePanelLabel022B(quote?.panel_type || quote?.source_panel_type);
    const user = cxClientQuoteUserLabel022C(quote);
    return `${panel} · ${user}`;
  }
  // CLONEXA_022C_CLIENT_ORIGIN_USER_LABEL_END

  function cxClientQuoteVisibleByFilter022B(quote, filter) {
    const archived = cxClientQuoteIsArchived022B(quote);
    const docType = cxClientQuoteDocumentType022B(quote);

    if (filter === "archived") return archived;
    if (archived) return false;
    if (filter === "quotes") return docType === "quote";
    if (filter === "accounts") return docType === "account";
    return true;
  }
  /* CLONEXA_022B_CLIENT_QUOTES_CONSOLIDATION_SOURCE_END */

  async function renderClientUniversalQuotesModule021D(activeCode = "cotizaciones") {
    ensureUniversalModuleStyles021D();

    let filter = window.__cxUniversalQuotesFilter021D || "active";
    let query = window.__cxUniversalQuotesQuery021D || "";
    let payload = { quotes: [] };
    let summary = { active_count: 0, total_amount: 0 };
    let error = "";

    try {
      const docFilter = filter === "quotes" ? "&document_type=quote" : filter === "accounts" ? "&document_type=account" : "";
      payload = await cxUniversalApi021D(`/mini-panel-quotes/companies/${encodeURIComponent(state.companyId)}?panel_type=${encodeURIComponent(cxClientQuotesScope021F())}&source_scope=${encodeURIComponent(cxClientQuotesSourceScope022B())}&include_archived=true&q=${encodeURIComponent(query)}${docFilter}`);
      summary = await cxUniversalApi021D(`/mini-panel-quotes/companies/${encodeURIComponent(state.companyId)}/summary?panel_type=${encodeURIComponent(cxClientQuotesScope021F())}&source_scope=${encodeURIComponent(cxClientQuotesSourceScope022B())}`);
    } catch (err) {
      error = err.message || "No se pudieron cargar cotizaciones.";
    }

    /* CLONEXA_021E_CLIENT_QUOTES_ACTIONS_FIX_START */
    const rawQuotes = Array.isArray(payload.quotes)
      ? payload.quotes
      : Array.isArray(payload.items)
        ? payload.items
        : Array.isArray(payload)
          ? payload
          : [];

    const quotes = rawQuotes.filter((quote) => cxClientQuoteVisibleByFilter022B(quote, filter));
    window.__cxUniversalQuotesCache021E = quotes;
    /* CLONEXA_021E_CLIENT_QUOTES_ACTIONS_FIX_END */
    const quoteReferences = await cxClientQuoteReferences023C();

    const renderQuote = (quote) => {
      const isAccount = String(quote.document_type || quote.status || "").toLowerCase() === "account" || String(quote.status || "").toLowerCase() === "converted";
      const displayNumber = quote.document_number || (isAccount ? quote.account_number : quote.quote_number) || quote.quote_number || "";
      return `
        <article class="cx-row-021d">
          <div class="cx-row-head-021d">
            <div>
              <strong>${h(quote.client_name || "Cliente")}</strong>
              <small>${h(displayNumber)} · ${h(isAccount ? "Cuenta de cobro" : "Cotización")}${cxClientQuoteIsArchived022B(quote) ? " · Archivada" : ""}</small>
              <small>${h(quote.created_at ? String(quote.created_at).slice(0, 10) : "")}</small>
              <small>Origen: ${h(cxClientQuoteOriginLabel022B(quote))}</small>
            </div>
            <div><strong>${h(cxUniversalMoney021D(quote.total || 0))}</strong></div>
          </div>
          <div class="cx-actions-021d" style="margin-top:12px;">
            <button class="cx-mini-btn-021d" type="button" data-client-quote-detail="${h(quote.id)}">Detalle</button>
            <button class="cx-mini-btn-021d primary" type="button" data-client-quote-pdf="${h(quote.id)}" data-document-type="${isAccount ? "account" : "quote"}">${h(isAccount ? "PDF cuenta de cobro" : "PDF cotización")}</button>
            ${isAccount ? `<button class="cx-mini-btn-021d" type="button" data-client-quote-pdf="${h(quote.id)}" data-document-type="quote">PDF cotización</button>` : `<button class="cx-mini-btn-021d" type="button" data-client-quote-convert="${h(quote.id)}">Pasar a cuenta de cobro</button>`}
            <button class="cx-mini-btn-021d danger" type="button" data-client-quote-archive="${h(quote.id)}">Archivar</button>
          </div>
        </article>
      `;
    };

    cxUniversalShell021D(
      activeCode,
      "Módulo universal",
      "Cotizaciones",
      "Consolidado de cotizaciones capturadas desde mini paneles. El Panel Cliente solo visualiza, controla y archiva información de su empresa.",
      `
        <section class="cx-universal-grid-021d">
          <article class="cx-universal-card-021d">
            <div class="cx-row-head-021d">
              <div>
                <h2>Formulario de cotización</h2>
                <p class="cx-muted-021d">Datos comerciales, conceptos, descuentos, pago y firma.</p>
              </div>
              <div class="cx-summary-pills-021d">
                <span class="cx-pill-021d">Retención: <strong data-client-quote-retention>${h(cxUniversalMoney021D(0))}</strong></span>
                <span class="cx-pill-021d">Total: <strong data-client-quote-total>${h(cxUniversalMoney021D(0))}</strong></span>
              </div>
            </div>

            <form class="cx-universal-form-021d" data-client-quotes-form>
              <div class="cx-field-grid-021d">
                <div class="cx-field-021d">
                  <label>Nombre o razón social</label>
                  <input name="client_name" placeholder="Cliente / empresa" required>
                </div>
                <div class="cx-field-021d">
                  <label>CC / NIT</label>
                  <input name="client_document" placeholder="Documento">
                </div>
                <div class="cx-field-021d">
                  <label>Teléfono</label>
                  <input name="client_phone" placeholder="Teléfono">
                </div>
                <div class="cx-field-021d">
                  <label>Dirección</label>
                  <input name="client_address" placeholder="Dirección">
                </div>
                <div class="cx-field-021d">
                  <label>Correo</label>
                  <input name="client_email" placeholder="correo@cliente.com">
                </div>
              </div>

              <div class="cx-universal-card-021d" style="padding:14px;">
                <div class="cx-row-head-021d">
                  <h3>Conceptos</h3>
                  <button class="cx-mini-btn-021d" type="button" data-client-quote-add-item>Agregar línea</button>
                </div>
                <div data-client-quote-items>
                  ${cxClientQuoteItemRow023C({}, quoteReferences)}
                </div>
              </div>

              <div class="cx-field-grid-021d">
                <div class="cx-universal-card-021d" style="padding:14px;">
                  <h3>Descuento</h3>
                  <div class="cx-field-021d"><label>Nombre</label><input name="discount_1_name" placeholder="Ej: pronto pago"></div>
                  <div class="cx-field-021d"><label>Descripción</label><input name="discount_1_description" placeholder="Detalle del descuento"></div>
                  <div class="cx-field-021d"><label>Valor</label><input name="discount_1_value" type="number" step="0.01" min="0" value="0"></div>
                </div>
                <div class="cx-universal-card-021d" style="padding:14px;">
                  <h3>Retención</h3>
                  <div class="cx-field-021d"><label>Nombre</label><input name="retention_name" value="Retención" placeholder="Ej: retefuente"></div>
                  <div class="cx-field-021d"><label>Descripción</label><input name="retention_description" placeholder="Detalle de la retención"></div>
                  <div class="cx-field-021d"><label>Porcentaje</label><input name="retention_percent" type="number" step="0.01" min="0" max="100" value="0"></div>
                </div>
              </div>

              <div class="cx-field-grid-021d">
                <div class="cx-field-021d">
                  <label>Detalle pago 1</label>
                  <input name="payment_detail" placeholder="Anticipo, saldo, contado...">
                </div>
                <div class="cx-field-021d">
                  <label>Nombre</label>
                  <input name="payment_name" placeholder="Responsable / banco / referencia">
                </div>
                <div class="cx-field-021d">
                  <label>Forma</label>
                  <select name="payment_method">
                    <option value="efectivo">Efectivo</option>
                    <option value="transferencia" selected>Transferencia</option>
                    <option value="cheque">Cheque</option>
                    <option value="otro">Otro</option>
                  </select>
                </div>
                <div class="cx-field-021d">
                  <label>Datos de pago</label>
                  <input name="payment_data" placeholder="Cuenta, referencia, vencimiento...">
                </div>
              </div>

              <div class="cx-field-021d">
                <label>Observaciones / condiciones</label>
                <textarea name="notes" placeholder="Validez de oferta, garantías, tiempos de entrega..."></textarea>
              </div>

              <div class="cx-field-021d">
                <label>Adjuntar firma digital</label>
                <input type="file" accept="image/*" data-client-quote-signature-file>
                <input type="hidden" name="signature_data_url" data-client-quote-signature-data>
                <div class="cx-signature-preview-021d" data-client-quote-signature-preview><span class="cx-muted-021d">Sin firma adjunta.</span></div>
              </div>

              <div class="cx-actions-021d">
                <button class="cx-mini-btn-021d" type="reset">Nuevo</button>
                <button class="cx-mini-btn-021d primary" type="submit">Guardar cotización</button>
              </div>
              <div class="cx-notice-021d ${error ? "error" : ""}" data-client-quotes-notice>${h(error)}</div>
            </form>
          </article>

          <article class="cx-universal-card-021d">
            <h2>Historial</h2>
            <div class="cx-field-grid-021d" style="grid-template-columns: 1fr 170px;">
              <div class="cx-field-021d"><label>Buscar</label><input data-client-quotes-search placeholder="Nombre, NIT, correo o número" value="${h(query)}"></div>
              <div class="cx-field-021d"><label>Tipo</label>
                <select data-client-quotes-filter>
                  <option value="active" ${filter === "active" ? "selected" : ""}>Activas</option>
                  <option value="quotes" ${filter === "quotes" ? "selected" : ""}>Cotizaciones</option>
                  <option value="accounts" ${filter === "accounts" ? "selected" : ""}>Cuentas de cobro</option>
                  <option value="archived" ${filter === "archived" ? "selected" : ""}>Archivadas</option>
                </select>
              </div>
            </div>

            <div class="cx-summary-pills-021d" style="margin-top:12px;">
              <span class="cx-pill-021d">Activas: ${h(summary.active_count || 0)}</span>
              <span class="cx-pill-021d">Monto: ${h(cxUniversalMoney021D(summary.total_amount || 0))}</span>
            </div>

            <div class="cx-list-021d">
              ${quotes.length ? quotes.map(renderQuote).join("") : `<div class="cx-row-021d cx-muted-021d">Sin cotizaciones registradas.</div>`}
            </div>
          </article>
        </section>
      `
    );

    const form = document.querySelector("[data-client-quotes-form]");
    const recalc = () => {
      let subtotal = 0;
      form?.querySelectorAll("[data-client-quote-item]").forEach((row) => {
        const qty = Number(row.querySelector('[name="item_quantity"]')?.value || 0);
        const price = Number(row.querySelector('[name="item_unit_price"]')?.value || 0);
        subtotal += qty * price;
      });
      const d1 = Number(form?.querySelector('[name="discount_1_value"]')?.value || 0);
      const retentionPercent = Math.min(100, Math.max(0, Number(form?.querySelector('[name="retention_percent"]')?.value || 0)));
      const retentionAmount = Math.max(0, subtotal) * retentionPercent / 100;
      const total = Math.max(0, subtotal - d1);
      const retentionTarget = document.querySelector("[data-client-quote-retention]");
      const target = document.querySelector("[data-client-quote-total]");
      if (retentionTarget) retentionTarget.textContent = cxUniversalMoney021D(retentionAmount);
      if (target) target.textContent = cxUniversalMoney021D(total);
    };

    form?.addEventListener("input", recalc);
    recalc();

    document.querySelector("[data-client-quote-add-item]")?.addEventListener("click", () => {
      const wrap = document.querySelector("[data-client-quote-items]");
      const first = wrap?.querySelector("[data-client-quote-item]");
      if (!wrap || !first) return;
      const clone = first.cloneNode(true);
      clone.querySelectorAll("input").forEach((input) => {
        if (input.name === "item_quantity") input.value = "1";
        else if (input.name === "item_unit_price") input.value = "0";
        else input.value = "";
      });
      clone.querySelectorAll("select").forEach((select) => { select.value = ""; });
      wrap.appendChild(clone);
      recalc();
    });

    document.querySelector("[data-client-quote-items]")?.addEventListener("change", (event) => {
      const select = event.target.closest("[data-client-quote-reference]");
      if (!select) return;
      cxClientQuoteApplyReference023C(select);
      recalc();
    });

    document.querySelector("[data-client-quote-items]")?.addEventListener("click", (event) => {
      const remove = event.target.closest("[data-client-quote-remove-item]");
      if (!remove) return;
      const rows = Array.from(document.querySelectorAll("[data-client-quote-item]"));
      if (rows.length <= 1) return;
      remove.closest("[data-client-quote-item]")?.remove();
      recalc();
    });

    document.querySelector("[data-client-quote-signature-file]")?.addEventListener("change", (event) => {
      const file = event.target.files && event.target.files[0];
      const hidden = document.querySelector("[data-client-quote-signature-data]");
      const preview = document.querySelector("[data-client-quote-signature-preview]");
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        const dataUrl = String(reader.result || "");
        if (hidden) hidden.value = dataUrl;
        if (preview) preview.innerHTML = `<img src="${h(dataUrl)}" alt="Firma">`;
      };
      reader.readAsDataURL(file);
    });

    form?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const notice = form.querySelector("[data-client-quotes-notice]");
      const fd = new FormData(form);

      const items = Array.from(form.querySelectorAll("[data-client-quote-item]"))
        .map((row) => {
          const refSelect = row.querySelector("[data-client-quote-reference]");
          const refOption = refSelect?.selectedOptions?.[0];
          return {
            description: String(row.querySelector('[name="item_description"]')?.value || "").trim(),
            quantity: Number(row.querySelector('[name="item_quantity"]')?.value || 0),
            unit_price: Number(row.querySelector('[name="item_unit_price"]')?.value || 0),
            reference_id: String(refSelect?.value || ""),
            sku: String(refOption?.dataset?.refSku || ""),
          };
        })
        .filter((item) => item.description);

      const discounts = [
        {
          type: "discount",
          kind: "discount",
          affects_total: true,
          name: String(fd.get("discount_1_name") || "").trim(),
          description: String(fd.get("discount_1_description") || "").trim(),
          value: Number(fd.get("discount_1_value") || 0),
        },
        {
          type: "retention",
          kind: "retention",
          affects_total: false,
          name: String(fd.get("retention_name") || "Retención").trim(),
          description: String(fd.get("retention_description") || "").trim(),
          percent: Number(fd.get("retention_percent") || 0),
          value: Number(fd.get("retention_percent") || 0),
        },
      ];

      const body = {
        client_name: String(fd.get("client_name") || "").trim(),
        client_document: String(fd.get("client_document") || "").trim(),
        client_address: String(fd.get("client_address") || "").trim(),
        client_phone: String(fd.get("client_phone") || "").trim(),
        client_email: String(fd.get("client_email") || "").trim(),
        items,
        discounts,
        payment: {
          detail: String(fd.get("payment_detail") || "").trim(),
          name: String(fd.get("payment_name") || "").trim(),
          method: String(fd.get("payment_method") || "transferencia"),
          data: String(fd.get("payment_data") || "").trim(),
        },
        notes: String(fd.get("notes") || "").trim(),
        signature_data_url: String(fd.get("signature_data_url") || "").trim(),
      };

      try {
        if (notice) {
          notice.classList.remove("error");
          notice.textContent = "Guardando cotización...";
        }
        await cxUniversalApi021D(`/mini-panel-quotes/companies/${encodeURIComponent(state.companyId)}?panel_type=${encodeURIComponent(cxUniversalPanelType021D())}`, {
          method: "POST",
          body: JSON.stringify(body),
        });
        await renderClientUniversalQuotesModule021D(activeCode);
      } catch (err) {
        if (notice) {
          notice.classList.add("error");
          notice.textContent = err.message || "No se pudo guardar la cotización.";
        }
      }
    });

    document.querySelector("[data-client-quotes-search]")?.addEventListener("change", async (event) => {
      window.__cxUniversalQuotesQuery021D = event.target.value || "";
      await renderClientUniversalQuotesModule021D(activeCode);
    });

    document.querySelector("[data-client-quotes-filter]")?.addEventListener("change", async (event) => {
      window.__cxUniversalQuotesFilter021D = event.target.value || "active";
      await renderClientUniversalQuotesModule021D(activeCode);
    });
  }


  /* CLONEXA_021E_CLIENT_QUOTES_DETAIL_MODAL_START */
  function cxClientQuoteDetailModal021E(quoteId) {
    const quotes = Array.isArray(window.__cxUniversalQuotesCache021E) ? window.__cxUniversalQuotesCache021E : [];
    const quote = quotes.find((item) => String(item.id) === String(quoteId));
    if (!quote) {
      alert("No se encontró el detalle de la cotización en la vista actual.");
      return;
    }

    const isAccount = String(quote.document_type || quote.status || "").toLowerCase() === "account" || String(quote.status || "").toLowerCase() === "converted";
    const number = quote.document_number || (isAccount ? quote.account_number : quote.quote_number) || quote.quote_number || "";
    const items = Array.isArray(quote.items) ? quote.items : [];
    const discounts = Array.isArray(quote.discounts) ? quote.discounts : [];
    const payment = quote.payment && typeof quote.payment === "object" ? quote.payment : {};

    const itemsHtml = items.length
      ? items.map((item) => `
          <tr>
            <td>${h(item.description || "")}</td>
            <td>${h(item.quantity ?? "")}</td>
            <td>${h(cxUniversalMoney021D(item.unit_price || 0))}</td>
            <td>${h(cxUniversalMoney021D(item.total || (Number(item.quantity || 0) * Number(item.unit_price || 0))))}</td>
          </tr>
        `).join("")
      : `<tr><td colspan="4">Sin conceptos registrados.</td></tr>`;

    const discountsHtml = discounts
      .filter((discount) => Number(discount.value || 0) > 0 || discount.name || discount.description)
      .map((discount) => {
        const isRetention = ["retention", "retencion"].includes(String(discount.type || discount.kind || "").toLowerCase());
        const percent = discount.percent ? ` · ${h(discount.percent)}%` : "";
        return `
          <div class="cx-detail-pill-021e">
            <strong>${h(discount.name || (isRetention ? "Retención" : "Descuento"))}${isRetention ? percent : ""}</strong>
            <span>${h(discount.description || (isRetention ? "No descuenta el total de la cotización." : ""))}</span>
            <b>${h(cxUniversalMoney021D(discount.value || 0))}</b>
          </div>
        `;
      }).join("");

    const existing = document.querySelector("[data-cx-quote-detail-modal-021e]");
    existing?.remove();

    const overlay = document.createElement("div");
    overlay.className = "cx-detail-overlay-021e";
    overlay.setAttribute("data-cx-quote-detail-modal-021e", "1");
    overlay.innerHTML = `
      <section class="cx-detail-card-021e">
        <header class="cx-detail-head-021e">
          <div>
            <div class="client-eyebrow">${h(isAccount ? "CUENTA DE COBRO" : "COTIZACIÓN")}</div>
            <h2>${h(number)}</h2>
            <p>${h(quote.client_name || "Cliente")} · ${h(quote.client_document || "Sin documento")}</p>
          </div>
          <button class="cx-mini-btn-021d" type="button" data-cx-close-quote-detail-021e>Cerrar</button>
        </header>

        <div class="cx-detail-grid-021e">
          <div>
            <h3>Cliente</h3>
            <p><strong>Nombre:</strong> ${h(quote.client_name || "")}</p>
            <p><strong>Documento:</strong> ${h(quote.client_document || "")}</p>
            <p><strong>Teléfono:</strong> ${h(quote.client_phone || "")}</p>
            <p><strong>Correo:</strong> ${h(quote.client_email || "")}</p>
            <p><strong>Dirección:</strong> ${h(quote.client_address || "")}</p>
          </div>
          <div>
            <h3>Totales</h3>
            <p><strong>Subtotal:</strong> ${h(cxUniversalMoney021D(quote.subtotal || 0))}</p>
            <p><strong>Descuentos:</strong> ${h(cxUniversalMoney021D(quote.discount_total || 0))}</p>
            <p><strong>Total:</strong> ${h(cxUniversalMoney021D(quote.total || 0))}</p>
            <p><strong>Estado:</strong> ${h(quote.document_label || (isAccount ? "Cuenta de cobro" : "Cotización"))}</p>
          </div>
        </div>

        <h3>Conceptos</h3>
        <div class="cx-detail-table-wrap-021e">
          <table class="cx-detail-table-021e">
            <thead>
              <tr><th>Detalle</th><th>Cant.</th><th>Valor unit.</th><th>Total</th></tr>
            </thead>
            <tbody>${itemsHtml}</tbody>
          </table>
        </div>

        ${discountsHtml ? `<h3>Descuentos</h3><div class="cx-detail-discounts-021e">${discountsHtml}</div>` : ""}

        <h3>Pago</h3>
        <p><strong>Detalle:</strong> ${h(payment.detail || "")}</p>
        <p><strong>Nombre:</strong> ${h(payment.name || "")}</p>
        <p><strong>Forma:</strong> ${h(payment.method || "")}</p>
        <p><strong>Datos:</strong> ${h(payment.data || "")}</p>

        ${quote.notes ? `<h3>Observaciones</h3><p>${h(quote.notes)}</p>` : ""}

        <footer class="cx-actions-021d">
          <button class="cx-mini-btn-021d primary" type="button" data-client-quote-pdf="${h(quote.id)}" data-document-type="${isAccount ? "account" : "quote"}">${h(isAccount ? "PDF cuenta de cobro" : "PDF cotización")}</button>
          ${isAccount ? `<button class="cx-mini-btn-021d" type="button" data-client-quote-pdf="${h(quote.id)}" data-document-type="quote">PDF cotización</button>` : `<button class="cx-mini-btn-021d" type="button" data-client-quote-convert="${h(quote.id)}">Pasar a cuenta de cobro</button>`}
          <button class="cx-mini-btn-021d danger" type="button" data-client-quote-archive="${h(quote.id)}">Archivar</button>
        </footer>
      </section>
    `;

    document.body.appendChild(overlay);
  }
  /* CLONEXA_021E_CLIENT_QUOTES_DETAIL_MODAL_END */

  document.addEventListener("click", async (event) => {
    const noteComplete = event.target.closest("[data-client-note-complete]");
    if (noteComplete) {
      await cxUniversalApi021D(`/mini-panel-notes/companies/${encodeURIComponent(state.companyId)}/${encodeURIComponent(noteComplete.dataset.clientNoteComplete)}/complete?panel_type=${encodeURIComponent(cxUniversalPanelType021D())}`, { method: "POST", body: JSON.stringify({}) });
      await renderClientUniversalNotesModule021D("notas");
      return;
    }

    const noteArchive = event.target.closest("[data-client-note-archive]");
    if (noteArchive) {
      await cxUniversalApi021D(`/mini-panel-notes/companies/${encodeURIComponent(state.companyId)}/${encodeURIComponent(noteArchive.dataset.clientNoteArchive)}?panel_type=${encodeURIComponent(cxUniversalPanelType021D())}`, { method: "DELETE" });
      await renderClientUniversalNotesModule021D("notas");
      return;
    }

    const quotePdf = event.target.closest("[data-client-quote-pdf]");
    if (quotePdf) {
      const id = quotePdf.dataset.clientQuotePdf;
      const docType = quotePdf.dataset.documentType || "quote";
      window.open(`${API}/mini-panel-quotes/companies/${encodeURIComponent(state.companyId)}/${encodeURIComponent(id)}/pdf?panel_type=${encodeURIComponent(cxClientQuotePanelForAction021F(id))}&document_type=${encodeURIComponent(docType)}`, "_blank", "noopener");
      return;
    }

    const quoteConvert = event.target.closest("[data-client-quote-convert]");
    if (quoteConvert) {
      const id = quoteConvert.dataset.clientQuoteConvert;
      await cxUniversalApi021D(`/mini-panel-quotes/companies/${encodeURIComponent(state.companyId)}/${encodeURIComponent(id)}/convert?panel_type=${encodeURIComponent(cxClientQuotePanelForAction021F(id))}`, { method: "POST", body: JSON.stringify({}) });
      window.open(`${API}/mini-panel-quotes/companies/${encodeURIComponent(state.companyId)}/${encodeURIComponent(id)}/pdf?panel_type=${encodeURIComponent(cxClientQuotePanelForAction021F(id))}&document_type=account`, "_blank", "noopener");
      await renderClientUniversalQuotesModule021D("cotizaciones");
      return;
    }

    const quoteArchive = event.target.closest("[data-client-quote-archive]");
    if (quoteArchive) {
      const id = quoteArchive.dataset.clientQuoteArchive;
      await cxUniversalApi021D(`/mini-panel-quotes/companies/${encodeURIComponent(state.companyId)}/${encodeURIComponent(id)}/archive?panel_type=${encodeURIComponent(cxClientQuotePanelForAction021F(id))}`, { method: "POST", body: JSON.stringify({}) });
      await renderClientUniversalQuotesModule021D("cotizaciones");
      return;
    }

    const detailClose = event.target.closest("[data-cx-close-quote-detail-021e]");
    if (detailClose) {
      detailClose.closest("[data-cx-quote-detail-modal-021e]")?.remove();
      return;
    }

    const quoteDetail = event.target.closest("[data-client-quote-detail]");
    if (quoteDetail) {
      cxClientQuoteDetailModal021E(quoteDetail.dataset.clientQuoteDetail);
      return;
    }
  }, true);
  /* CLONEXA_021D_UNIVERSAL_MODULE_RENDER_ADAPTER_END */



  /* CLONEXA_022M_REFERENCES_CLEAN_CATALOG_SKU_PRICE_START */
  function cxIsReferencesCode022E(code) {
    return [
      "references",
      "reference",
      "referencias",
      "referencia",
      "ref",
      "production_references",
      "production_reference",
      "referencias_produccion",
      "referencias_producción"
    ].includes(String(code || "").trim().toLowerCase());
  }

  /* CLONEXA_022E_R6_RESTORE_PRODUCTION_KEEP_REFERENCES */
  function cxActiveReferencesNavCode022E() {
    const referenceCodes = [
      "references",
      "reference",
      "referencias",
      "referencia",
      "ref",
      "production_references",
      "production_reference",
      "referencias_produccion",
      "referencias_producción"
    ];
    const module = activeClientModules().find((item) =>
      referenceCodes.includes(String(item?.code || "").trim().toLowerCase())
    );
    return module?.code || "";
  }

  function cxReferenceChannelLabel022E(channel, row = {}) {
    const value = String(channel || row.channel || "").trim().toLowerCase();
    if (value === "system" || row.system_active === true) return "Sistema";
    if (value === "both") return "Ambos";
    return "Bot";
  }

  function cxReferenceChannelValue022E(row = {}) {
    const value = String(row.channel || "").trim().toLowerCase();
    if (["system", "bot", "both"].includes(value)) return value;
    if (row.system_active === true && row.bot_active === true) return "both";
    if (row.system_active === true) return "system";
    return "bot";
  }

  async function cxReferencesApi022E(path, options = {}) {
    return api(path, options);
  }

  function cxReferencesQuery022E() {
    const params = new URLSearchParams();
    const q = String(document.getElementById("refSearch022E")?.value || "").trim();
    const from = String(document.getElementById("refDateFrom022E")?.value || "").trim();
    const to = String(document.getElementById("refDateTo022E")?.value || "").trim();
    const channel = String(document.getElementById("refChannelFilter022E")?.value || "").trim();
    if (q) params.set("q", q);
    if (from) params.set("date_from", from);
    if (to) params.set("date_to", to);
    if (channel) params.set("channel", channel);
    return params.toString();
  }

  async function cxLoadReferences022E() {
    const query = cxReferencesQuery022E();
    const suffix = query ? `?${query}` : "";
    return cxReferencesApi022E(`/references-v1/companies/${encodeURIComponent(state.companyId)}${suffix}`);
  }

  async function cxLoadReferencesSummary022E() {
    return { by_reference_size: [] };
  }

  function cxReferencesNumber022E(value) {
    const number = Number(value || 0);
    return Number.isFinite(number) ? Math.round(number).toLocaleString("es-CO") : "0";
  }

  function cxReferencesMoney022M(value) {
    const number = Number(value || 0);
    return Number.isFinite(number) ? number.toLocaleString("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 }) : "$ 0";
  }

  function cxReferenceReadCreatePayload022E() {
    return {
      category: String(document.getElementById("refCreateCategory022E")?.value || "").trim(),
      name: String(document.getElementById("refCreateName022E")?.value || "").trim(),
      size: String(document.getElementById("refCreateSize022E")?.value || "").trim(),
      color: String(document.getElementById("refCreateColor022E")?.value || "").trim(),
      sku: String(document.getElementById("refCreateSku022M")?.value || "").trim(),
      unit_price: Number(document.getElementById("refCreateUnitPrice022M")?.value || 0) || 0,
      initial_quantity: Number(document.getElementById("refCreateMeta022M")?.value || 0) || 0,
      channel: String(document.getElementById("refCreateChannel022E")?.value || "system").trim()
    };
  }

  function cxReferenceReadRowPayload022E(row) {
    return {
      category: String(row.querySelector('[data-ref-field="category"]')?.value || "").trim(),
      name: String(row.querySelector('[data-ref-field="name"]')?.value || "").trim(),
      size: String(row.querySelector('[data-ref-field="size"]')?.value || "").trim(),
      color: String(row.querySelector('[data-ref-field="color"]')?.value || "").trim(),
      sku: String(row.querySelector('[data-ref-field="sku"]')?.value || "").trim(),
      unit_price: Number(row.querySelector('[data-ref-field="unit_price"]')?.value || 0) || 0,
      initial_quantity: Number(row.querySelector('[data-ref-field="initial_quantity"]')?.value || 0) || 0,
      channel: String(row.querySelector('[data-ref-field="channel"]')?.value || "system").trim()
    };
  }

  function cxReferenceMergeRows022E(items = [], summary = {}) {
    return (Array.isArray(items) ? items : []).map((item) => ({
      ...item,
      sku: item.sku || item.code || item.barcode || "",
      unit_price: Number(item.unit_price ?? item.price ?? 0) || 0,
      channel: item.channel || (item.bot_active ? "bot" : "system"),
      system_active: item.system_active ?? false
    }));
  }

  function cxReferenceRow022E(row = {}) {
    const channel = cxReferenceChannelValue022E(row);
    return `
      <tr data-reference-row="${h(row.id || "")}">
        <td><input data-ref-field="name" value="${h(row.name || "")}" placeholder="Ej: Funda iPhone"></td>
        <td><input data-ref-field="category" value="${h(row.category || "")}" placeholder="Ej: Funda Celular"></td>
        <td><input data-ref-field="size" value="${h(row.size || "")}" placeholder="Ej: 14 Pro Max / SM"></td>
        <td><input data-ref-field="color" value="${h(row.color || "")}" placeholder="Ej: negro"></td>
        <td><input data-ref-field="sku" value="${h(row.sku || row.code || row.barcode || "")}" placeholder="SKU / código"></td>
        <td><input data-ref-field="unit_price" type="number" min="0" step="100" value="${h(row.unit_price ?? 0)}"></td>
        <td><input data-ref-field="initial_quantity" type="number" min="0" step="1" value="${h(row.initial_quantity ?? 0)}"></td>
        <td>
          <select data-ref-field="channel">
            <option value="system" ${channel === "system" ? "selected" : ""}>Sistema</option>
            <option value="bot" ${channel === "bot" ? "selected" : ""}>Bot</option>
            <option value="both" ${channel === "both" ? "selected" : ""}>Ambos</option>
          </select>
        </td>
        <td>
          <div class="cx-ref-actions-022m">
            <button class="client-btn" type="button" data-reference-save="${h(row.id || "")}">Guardar</button>
            <button class="client-btn" type="button" data-reference-delete="${h(row.id || "")}">Archivar</button>
          </div>
        </td>
      </tr>
    `;
  }

  function cxReferencesTable022E(rows = []) {
    return `
      <div class="cx-ref-table-wrap">
        <table class="cx-ref-table">
          <thead>
            <tr>
              <th>Nombre referencia</th>
              <th>Categoría</th>
              <th>Talla / modelo</th>
              <th>Color</th>
              <th>SKU</th>
              <th>Precio unidad</th>
              <th>Meta operativa</th>
              <th>Canal de uso</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            ${rows.length ? rows.map(cxReferenceRow022E).join("") : `<tr><td colspan="9">Sin referencias para este filtro.</td></tr>`}
          </tbody>
        </table>
      </div>
    `;
  }

  function cxReferencesStyles022E() {
    if (document.getElementById("cxReferences022EStyles")) return;
    const style = document.createElement("style");
    style.id = "cxReferences022EStyles";
    style.textContent = `
      .cx-ref-toolbar,
      .cx-ref-create {
        display: grid;
        gap: 12px;
        align-items: end;
        margin-top: 16px;
      }
      .cx-ref-toolbar {
        grid-template-columns: minmax(260px,1.4fr) 150px 150px 170px auto auto;
      }
      .cx-ref-create {
        grid-template-columns: minmax(220px,1.2fr) minmax(160px,.8fr) 140px 130px 150px 150px 160px 150px auto;
      }
      .cx-ref-field {
        display: grid;
        gap: 7px;
      }
      .cx-ref-field label {
        text-transform: uppercase;
        font-size: 11px;
        letter-spacing: .1em;
        font-weight: 1000;
        opacity: .82;
      }
      .cx-ref-field input,
      .cx-ref-field select,
      .cx-ref-table input,
      .cx-ref-table select {
        width: 100%;
        border: 1px solid rgba(255,255,255,.16);
        background: rgba(0,0,0,.24);
        color: inherit;
        border-radius: 16px;
        padding: 12px 13px;
        font-weight: 900;
        outline: none;
      }
      .cx-ref-table-wrap {
        width: 100%;
        overflow-x: auto;
        margin-top: 18px;
        border: 1px solid rgba(255,255,255,.12);
        border-radius: 22px;
        background: rgba(0,0,0,.10);
      }
      .cx-ref-table {
        width: 100%;
        border-collapse: collapse;
        min-width: 1320px;
      }
      .cx-ref-table th,
      .cx-ref-table td {
        padding: 13px 12px;
        border-bottom: 1px solid rgba(255,255,255,.09);
        text-align: left;
        vertical-align: middle;
      }
      .cx-ref-table th {
        text-transform: uppercase;
        font-size: 11px;
        letter-spacing: .1em;
        background: rgba(40,45,85,.55);
      }
      .cx-ref-table td { font-weight: 850; }
      .cx-ref-actions-022m { display:flex; gap:8px; flex-wrap:wrap; }
      .cx-ref-section-head-022m {
        display:flex;
        justify-content:space-between;
        align-items:flex-end;
        gap:14px;
        flex-wrap:wrap;
      }
      @media (max-width: 1280px) {
        .cx-ref-toolbar,
        .cx-ref-create {
          grid-template-columns: repeat(2,minmax(0,1fr));
        }
      }
      @media (max-width: 760px) {
        .cx-ref-toolbar,
        .cx-ref-create {
          grid-template-columns: 1fr;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function cxReferencesNotice022E(message, type = "ok") {
    const box = document.getElementById("referencesNotice022E");
    if (!box) return;
    box.innerHTML = `<div class="personal-toast ${type === "error" ? "error" : "ok"}">${h(message)}</div>`;
    window.clearTimeout(window.__cxReferencesNotice022E);
    window.__cxReferencesNotice022E = window.setTimeout(() => {
      if (box) box.innerHTML = "";
    }, 3600);
  }

  async function renderReferencesModule022E() {
    const activeReferencesNavCode022E = cxActiveReferencesNavCode022E();
    if (!activeReferencesNavCode022E) {
      render();
      return;
    }
    cxReferencesStyles022E();
    const company = state.company || {};
    let payload = { items: [] };
    let loadError = "";
    try {
      payload = await cxLoadReferences022E();
    } catch (error) {
      loadError = error.message || "No se pudieron cargar referencias.";
    }
    const rows = cxReferenceMergeRows022E(payload.items || []);
    window.__cxReferencesRows022E = rows;
    $("app").innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, normalizeBranding(state.branding || {}))}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>
            <nav class="client-nav">${renderClientNav(activeReferencesNavCode022E)}</nav>
            <div class="client-footer-id"><strong>Tenant activo</strong><br>${h(state.companyId || "")}</div>
          </aside>
          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">Módulo Referencias</div>
              <h1 class="client-title">Referencias</h1>
              <p class="client-muted">Catálogo maestro comercial para ventas, bots y mini paneles. El stock real queda para Inventario.</p>
              <div class="client-actions">
                <button class="client-btn" type="button" data-references-refresh>Actualizar</button>
                <button class="client-btn" type="button" data-references-save-all>Guardar cambios</button>
                <button class="client-btn" type="button" data-references-export>Exportar CSV</button>
                <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
              </div>
              <div id="referencesNotice022E">${loadError ? `<div class="personal-toast error">${h(loadError)}</div>` : ""}</div>
            </header>

            <section class="client-panel">
              <div class="client-eyebrow">Crear referencia</div>
              <h2>Catálogo comercial</h2>
              <p class="client-muted">Crea productos base con categoría, SKU, precio unidad, canal de uso y meta operativa.</p>
              <div class="cx-ref-create">
                <div class="cx-ref-field"><label>Nombre referencia</label><input id="refCreateName022E" placeholder="Ej: Funda iPhone"></div>
                <div class="cx-ref-field"><label>Categoría</label><input id="refCreateCategory022E" placeholder="Ej: Funda Celular"></div>
                <div class="cx-ref-field"><label>Talla / modelo</label><input id="refCreateSize022E" placeholder="Ej: 14 Pro Max / SM"></div>
                <div class="cx-ref-field"><label>Color</label><input id="refCreateColor022E" placeholder="Ej: negro"></div>
                <div class="cx-ref-field"><label>SKU</label><input id="refCreateSku022M" placeholder="Código interno / barras"></div>
                <div class="cx-ref-field"><label>Precio unidad</label><input id="refCreateUnitPrice022M" type="number" min="0" step="100" value="0"></div>
                <div class="cx-ref-field">
                  <label>Canal de uso</label>
                  <select id="refCreateChannel022E">
                    <option value="system">Sistema</option>
                    <option value="bot">Bot</option>
                    <option value="both">Ambos</option>
                  </select>
                </div>
                <div class="cx-ref-field"><label>Meta operativa</label><input id="refCreateMeta022M" type="number" min="0" step="1" value="0"></div>
                <button class="client-btn" type="button" data-reference-create>Crear</button>
              </div>
            </section>

            <section class="client-panel">
              <div class="cx-ref-section-head-022m">
                <div>
                  <div class="client-eyebrow">Referencias creadas</div>
                  <h2>Buscar y administrar</h2>
                  <p class="client-muted">Busca por nombre, categoría, talla/modelo, color, SKU o canal de uso.</p>
                </div>
              </div>
              <div class="cx-ref-toolbar">
                <div class="cx-ref-field"><label>Buscar</label><input id="refSearch022E" placeholder="Buscar referencia, categoría, talla, color, SKU o canal..."></div>
                <div class="cx-ref-field"><label>Desde</label><input id="refDateFrom022E" type="date"></div>
                <div class="cx-ref-field"><label>Hasta</label><input id="refDateTo022E" type="date"></div>
                <div class="cx-ref-field">
                  <label>Canal de uso</label>
                  <select id="refChannelFilter022E">
                    <option value="">Todas</option>
                    <option value="system">Sistema</option>
                    <option value="bot">Bot</option>
                    <option value="both">Ambos</option>
                  </select>
                </div>
                <button class="client-btn" type="button" data-references-refresh>Buscar</button>
                <button class="client-btn" type="button" data-references-export>Exportar CSV</button>
              </div>
              ${cxReferencesTable022E(rows)}
            </section>
          </section>
        </div>
      </main>
    `;
  }

  document.addEventListener("click", async (event) => {
    if (event.target.closest("[data-references-refresh]")) {
      await renderReferencesModule022E();
      return;
    }

    if (event.target.closest("[data-reference-create]")) {
      const payload = cxReferenceReadCreatePayload022E();
      if (!payload.name || !payload.size) {
        cxReferencesNotice022E("Nombre y talla/modelo son obligatorios.", "error");
        return;
      }
      await cxReferencesApi022E(`/references-v1/companies/${encodeURIComponent(state.companyId)}`, {
        method: "POST",
        body: JSON.stringify(payload)
      });
      await renderReferencesModule022E();
      setTimeout(() => cxReferencesNotice022E("Referencia creada."), 80);
      return;
    }

    const saveOne = event.target.closest("[data-reference-save]");
    if (saveOne) {
      const row = saveOne.closest("[data-reference-row]");
      const id = saveOne.dataset.referenceSave;
      if (!row || !id) return;
      await cxReferencesApi022E(`/references-v1/companies/${encodeURIComponent(state.companyId)}/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: JSON.stringify(cxReferenceReadRowPayload022E(row))
      });
      await renderReferencesModule022E();
      setTimeout(() => cxReferencesNotice022E("Referencia actualizada."), 80);
      return;
    }

    if (event.target.closest("[data-references-save-all]")) {
      const rows = Array.from(document.querySelectorAll("[data-reference-row]"));
      for (const row of rows) {
        const id = row.dataset.referenceRow;
        if (!id) continue;
        await cxReferencesApi022E(`/references-v1/companies/${encodeURIComponent(state.companyId)}/${encodeURIComponent(id)}`, {
          method: "PATCH",
          body: JSON.stringify(cxReferenceReadRowPayload022E(row))
        });
      }
      await renderReferencesModule022E();
      setTimeout(() => cxReferencesNotice022E("Cambios guardados."), 80);
      return;
    }

    const archive = event.target.closest("[data-reference-delete]");
    if (archive) {
      const id = archive.dataset.referenceDelete;
      if (!id || !confirm("¿Archivar esta referencia? No se borrará físicamente.")) return;
      await cxReferencesApi022E(`/references-v1/companies/${encodeURIComponent(state.companyId)}/${encodeURIComponent(id)}`, { method: "DELETE" });
      await renderReferencesModule022E();
      setTimeout(() => cxReferencesNotice022E("Referencia archivada."), 80);
      return;
    }

    if (event.target.closest("[data-references-export]")) {
      const query = cxReferencesQuery022E();
      const suffix = query ? `?${query}` : "";
      const a = document.createElement("a");
      a.href = `${API}/references-v1/companies/${encodeURIComponent(state.companyId)}/export.csv${suffix}`;
      a.download = `clonexa_referencias_${state.companyId || "empresa"}_${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      return;
    }
  }, true);
  /* CLONEXA_022M_REFERENCES_CLEAN_CATALOG_SKU_PRICE_END */

  /* CLONEXA_023K_CLIENT_COMMERCIAL_CLOSING_CONSOLE_START */
  const CX_COMMERCIAL_CLOSING_CODES_023K = new Set([
    "commercial_closing",
    "cierre_comercial",
    "cierres_comerciales",
    "cierre",
    "cierres",
    "day_closing",
    "daily_closing",
    "closing"
  ]);

  function cxClosingNorm023K(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
  }

  function cxIsCommercialClosingCode023K(code) {
    return CX_COMMERCIAL_CLOSING_CODES_023K.has(cxClosingNorm023K(code));
  }

  function cxClosingMoney023K(value) {
    if (typeof cxSalesMoney022F === "function") return cxSalesMoney022F(value);
    const number = Number(value || 0);
    return `$ ${Math.round(number).toLocaleString("es-CO")}`;
  }

  function cxClosingDateInput023K(daysAgo = 0) {
    const date = new Date();
    date.setDate(date.getDate() - daysAgo);
    const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
    return local.toISOString().slice(0, 10);
  }

  function cxClosingDateLabel023K(value) {
    const raw = String(value || "").trim();
    if (!raw) return "Sin fecha";
    return raw.slice(0, 10);
  }

  function cxClosingDateTimeLabel023K(value) {
    const raw = String(value || "").trim();
    if (!raw) return "Sin registro";
    return raw.replace("T", " ").slice(0, 16);
  }

  function cxClosingPanelLabel023K(value) {
    const panel = cxClosingNorm023K(value || "sales");
    const labels = {
      sales: "Ventas",
      venta: "Ventas",
      ventas: "Ventas",
      stores: "Tiendas",
      store: "Tiendas",
      tienda: "Tiendas",
      tiendas: "Tiendas",
      inventory: "Inventario",
      logistics: "Logistica",
      other: "Operativo"
    };
    return labels[panel] || String(value || "Operativo").replace(/_/g, " ");
  }

  function cxClosingStatusLabel023K(value) {
    const status = cxClosingNorm023K(value || "submitted");
    const labels = {
      submitted: "Enviado",
      reviewed: "Guardado",
      archived: "Archivado",
      open: "Abierto"
    };
    return labels[status] || String(value || "Enviado");
  }

  function cxClosingStatusClass023K(value) {
    const status = cxClosingNorm023K(value || "submitted");
    if (status === "archived") return "muted";
    if (status === "reviewed") return "ok";
    return "live";
  }

  async function cxClosingApi023K(path, options = {}) {
    return api(`/day-closing/companies/${encodeURIComponent(state.companyId)}${path}`, options);
  }

  function cxClosingStyles023K() {
    if (document.getElementById("cxClosingStyles023K")) return;
    const style = document.createElement("style");
    style.id = "cxClosingStyles023K";
    style.textContent = `
      .cx-closing-shell{display:grid;gap:18px}
      .cx-closing-toolbar{display:grid;grid-template-columns:repeat(5,minmax(120px,1fr)) auto;gap:12px;align-items:end}
      .cx-closing-field label{display:block;margin:0 0 7px;font-size:11px;font-weight:950;letter-spacing:.16em;text-transform:uppercase;color:rgba(255,255,255,.66)}
      .cx-closing-field input,.cx-closing-field select,.cx-closing-field textarea{width:100%;box-sizing:border-box;border:1px solid rgba(255,255,255,.16);border-radius:16px;background:rgba(4,8,22,.62);color:#fff;padding:13px 14px;font-weight:850;outline:none}
      .cx-closing-field textarea{min-height:90px;resize:vertical}
      .cx-closing-btn{border:0;border-radius:17px;background:linear-gradient(135deg,#ff24b8,#7552ff);color:#fff;font-weight:950;padding:13px 16px;cursor:pointer;box-shadow:0 16px 38px rgba(189,44,255,.22)}
      .cx-closing-btn.secondary{background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.14);box-shadow:none}
      .cx-closing-btn.danger{background:rgba(255,70,118,.16);border:1px solid rgba(255,70,118,.42);box-shadow:none}
      .cx-closing-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
      .cx-closing-kpi,.cx-closing-card{border:1px solid rgba(255,255,255,.13);border-radius:26px;background:linear-gradient(135deg,rgba(255,255,255,.12),rgba(255,255,255,.045));box-shadow:0 22px 70px rgba(0,0,0,.26);padding:20px}
      .cx-closing-kpi span,.cx-closing-kicker{display:block;font-size:11px;font-weight:950;letter-spacing:.20em;text-transform:uppercase;color:#ff45d2;margin-bottom:10px}
      .cx-closing-kpi strong{display:block;font-size:28px;line-height:1.05;color:#fff}
      .cx-closing-kpi small,.cx-closing-muted{display:block;margin-top:8px;color:rgba(255,255,255,.70);font-weight:800}
      .cx-closing-main{display:grid;grid-template-columns:minmax(360px,.92fr) minmax(420px,1.08fr);gap:18px;align-items:start}
      .cx-closing-report-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;align-items:start}
      .cx-closing-rank-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;align-items:start}
      .cx-closing-list{display:grid;gap:12px;max-height:680px;overflow:auto;padding-right:4px}
      .cx-closing-item{border:1px solid rgba(255,255,255,.12);border-radius:22px;background:rgba(255,255,255,.065);padding:16px;display:grid;gap:12px}
      .cx-closing-item.active{border-color:rgba(255,52,210,.68);box-shadow:0 0 0 1px rgba(255,52,210,.15),0 20px 55px rgba(182,47,255,.18)}
      .cx-closing-item-head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}
      .cx-closing-item-title{font-size:17px;font-weight:950;color:#fff}
      .cx-closing-pill{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:7px 10px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.09);font-size:12px;font-weight:950;color:#fff}
      .cx-closing-pill.live{border-color:rgba(41,255,187,.34);background:rgba(41,255,187,.12);color:#8fffd8}
      .cx-closing-pill.ok{border-color:rgba(126,255,85,.34);background:rgba(126,255,85,.11);color:#c8ff9e}
      .cx-closing-pill.muted{color:rgba(255,255,255,.62)}
      .cx-closing-mini{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
      .cx-closing-mini div{border:1px solid rgba(255,255,255,.10);border-radius:16px;background:rgba(6,9,24,.35);padding:11px}
      .cx-closing-mini span{display:block;font-size:10px;font-weight:950;letter-spacing:.12em;text-transform:uppercase;color:rgba(255,255,255,.58);margin-bottom:5px}
      .cx-closing-mini strong{display:block;color:#fff;font-size:15px}
      .cx-closing-actions{display:flex;gap:8px;flex-wrap:wrap}
      .cx-closing-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:14px}
      .cx-closing-users{display:grid;gap:10px;margin-top:14px}
      .cx-closing-user{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center;border:1px solid rgba(255,255,255,.10);border-radius:16px;background:rgba(4,8,22,.38);padding:12px}
      .cx-closing-user strong{color:#fff}
      .cx-closing-user small{color:rgba(255,255,255,.66);font-weight:800}
      .cx-closing-stores{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
      .cx-closing-store-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:12px}
      .cx-closing-empty{border:1px dashed rgba(255,255,255,.18);border-radius:20px;padding:22px;color:rgba(255,255,255,.70);font-weight:850;text-align:center}
      .cx-closing-modal-backdrop{position:fixed;inset:0;z-index:9999;background:rgba(2,4,14,.76);backdrop-filter:blur(12px);display:flex;align-items:center;justify-content:center;padding:22px}
      .cx-closing-modal{width:min(1080px,96vw);max-height:88vh;overflow:auto;border:1px solid rgba(255,255,255,.16);border-radius:28px;background:linear-gradient(145deg,rgba(26,20,43,.98),rgba(8,12,28,.98));box-shadow:0 35px 120px rgba(0,0,0,.55);padding:24px}
      .cx-closing-modal-head{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;margin-bottom:16px}
      .cx-closing-modal-close{min-width:48px;height:48px;border-radius:16px;border:1px solid rgba(255,255,255,.16);background:rgba(255,255,255,.10);color:#fff;font-size:22px;font-weight:950;cursor:pointer}
      .cx-closing-json{white-space:pre-wrap;word-break:break-word;max-height:260px;overflow:auto;border:1px solid rgba(255,255,255,.12);border-radius:18px;background:rgba(0,0,0,.26);padding:14px;color:rgba(255,255,255,.78);font-size:12px}
      @media(max-width:1200px){.cx-closing-toolbar,.cx-closing-main,.cx-closing-kpis,.cx-closing-stores,.cx-closing-report-grid,.cx-closing-rank-grid{grid-template-columns:1fr}.cx-closing-mini,.cx-closing-detail-grid{grid-template-columns:1fr}}
    `;
    document.head.appendChild(style);
  }

  function cxClosingFilters023K(options = {}) {
    return {
      from: options.from || cxClosingDateInput023K(30),
      to: options.to || cxClosingDateInput023K(0),
      panel_type: options.panel_type || "all",
      status: options.status || "active",
      q: options.q || "",
      selected_id: options.selected_id || ""
    };
  }

  function cxClosingReadFilters023K(current = {}) {
    return {
      from: document.getElementById("cxClosingFrom023K")?.value || current.from || cxClosingDateInput023K(30),
      to: document.getElementById("cxClosingTo023K")?.value || current.to || cxClosingDateInput023K(0),
      panel_type: document.getElementById("cxClosingPanel023K")?.value || current.panel_type || "all",
      status: document.getElementById("cxClosingStatus023K")?.value || current.status || "active",
      q: document.getElementById("cxClosingSearch023K")?.value || "",
      selected_id: current.selected_id || ""
    };
  }

  function cxClosingQuery023K(filters) {
    const params = new URLSearchParams();
    params.set("from", filters.from || cxClosingDateInput023K(30));
    params.set("to", filters.to || cxClosingDateInput023K(0));
    params.set("panel_type", filters.panel_type || "all");
    params.set("status", filters.status || "active");
    if (String(filters.q || "").trim()) params.set("q", filters.q.trim());
    params.set("limit", "180");
    return params.toString();
  }

  function cxClosingUserList023K(users = [], empty = "Sin vendedores reportados en este cierre.") {
    const rows = Array.isArray(users) ? users : [];
    if (!rows.length) return `<div class="cx-closing-empty">${h(empty)}</div>`;
    return rows.slice(0, 12).map((user) => `
      <div class="cx-closing-user">
        <div>
          <strong>${h(user.label || user.full_name || user.email || "Sin usuario")}</strong>
          <small>${Number(user.sales_count || 0)} ventas · ${Number(user.quotes_count || 0)} cotizaciones · ${Number(user.requests_count || 0)} solicitudes</small>
        </div>
        <strong>${h(cxClosingMoney023K(user.total_amount || 0))}</strong>
      </div>
    `).join("");
  }

  function cxClosingIsPanel023M(item, panel) {
    return cxClosingNorm023K(item?.panel_type || "") === panel;
  }

  function cxClosingPanelItems023M(items = [], panel) {
    const rows = Array.isArray(items) ? items : [];
    return rows.filter((item) => cxClosingIsPanel023M(item, panel));
  }

  function cxClosingAggregateUsers023M(items = []) {
    const rows = Array.isArray(items) ? items : [];
    const users = new Map();
    rows.forEach((item) => {
      const itemUsers = Array.isArray(item?.users) ? item.users : [];
      itemUsers.forEach((user) => {
        if (!user || typeof user !== "object") return;
        const label = user.label || user.full_name || user.email || "Sin usuario";
        const key = String(user.user_id || user.id || label).toLowerCase();
        const current = users.get(key) || {
          label,
          sales_count: 0,
          quotes_count: 0,
          requests_count: 0,
          total_amount: 0,
          cash_amount: 0,
          transfer_amount: 0
        };
        current.sales_count += Number(user.sales_count || 0);
        current.quotes_count += Number(user.quotes_count || 0);
        current.requests_count += Number(user.requests_count || 0);
        current.total_amount += Number(user.total_amount || 0);
        current.cash_amount += Number(user.cash_amount || 0);
        current.transfer_amount += Number(user.transfer_amount || 0);
        users.set(key, current);
      });
    });
    return Array.from(users.values()).sort((a, b) => Number(b.total_amount || 0) - Number(a.total_amount || 0));
  }

  function cxClosingStoreRows023M(stores = [], empty = "Aun no hay cierres enviados desde paneles de tienda.") {
    const rows = Array.isArray(stores) ? stores : [];
    if (!rows.length) return `<div class="cx-closing-empty">${h(empty)}</div>`;
    return rows.slice(0, 12).map((store) => `
      <div class="cx-closing-user">
        <div>
          <strong>${h(store.label || "Tienda")}</strong>
          <small>${Number(store.closures_count || 0)} cierres · ${Number(store.sales_count || 0)} ventas · ${Number((store.users || []).length)} colaboradores</small>
        </div>
        <strong>${h(cxClosingMoney023K(store.total_amount || 0))}</strong>
      </div>
    `).join("");
  }

  function cxClosingTopCollaborator023N(group) {
    const users = Array.isArray(group?.users) ? group.users : [];
    const ranked = users
      .filter((user) => user && typeof user === "object")
      .slice()
      .sort((a, b) => Number(b.total_amount || 0) - Number(a.total_amount || 0));
    const top = ranked[0];
    return top?.label || top?.full_name || top?.email || top?.username || "";
  }

  function cxClosingRankingRows023M(groups = [], empty = "Sin datos consolidados para comparar ventas y tiendas.") {
    const rows = Array.isArray(groups) ? groups : [];
    if (!rows.length) return `<div class="cx-closing-empty">${h(empty)}</div>`;
    return rows.slice(0, 10).map((group, index) => `
      <div class="cx-closing-user">
        <div>
          <strong>#${index + 1} ${h(group.label || cxClosingPanelLabel023K(group.panel_type))}${cxClosingTopCollaborator023N(group) ? ` - ${h(cxClosingTopCollaborator023N(group))}` : ""}</strong>
          ${cxClosingTopCollaborator023N(group) ? `<small>Colaborador: ${h(cxClosingTopCollaborator023N(group))}</small>` : ""}
          <small>${Number(group.closures_count || 0)} cierres · ${Number(group.sales_count || 0)} ventas · ${Number(group.quotes_count || 0)} cotizaciones</small>
        </div>
        <strong>${h(cxClosingMoney023K(group.total_amount || 0))}</strong>
      </div>
    `).join("");
  }

  function cxClosingReportColumn023M(title, kicker, items, selectedId, empty) {
    return `
      <article class="cx-closing-card">
        <div class="cx-closing-kicker">${h(kicker)}</div>
        <h2>${h(title)}</h2>
        <div class="cx-closing-list">
          ${(items || []).map((item) => cxClosingItemCard023K(item, selectedId)).join("") || `<div class="cx-closing-empty">${h(empty)}</div>`}
        </div>
      </article>
    `;
  }

  function cxClosingItemCard023K(item, selectedId) {
    const totals = item?.totals || {};
    const isSelected = String(item?.id || "") === String(selectedId || "");
    return `
      <article class="cx-closing-item ${isSelected ? "active" : ""}">
        <div class="cx-closing-item-head">
          <div>
            <div class="cx-closing-item-title">${h(cxClosingPanelLabel023K(item.panel_type))} · ${h(cxClosingDateLabel023K(item.closure_date))}</div>
            <div class="cx-closing-muted">Enviado por ${h(item.submitted_by_label || "Panel principal")} · ${h(cxClosingDateTimeLabel023K(item.submitted_at))}</div>
          </div>
          <span class="cx-closing-pill ${h(cxClosingStatusClass023K(item.status))}">${h(cxClosingStatusLabel023K(item.status))}</span>
        </div>
        <div class="cx-closing-mini">
          <div><span>Recaudo</span><strong>${h(cxClosingMoney023K(totals.total_amount || 0))}</strong></div>
          <div><span>Efectivo</span><strong>${h(cxClosingMoney023K(totals.cash_amount || 0))}</strong></div>
          <div><span>Registros</span><strong>${Number(totals.sales_count || totals.quotes_count || totals.requests_count || 0)}</strong></div>
        </div>
        <div class="cx-closing-actions">
          <button class="cx-closing-btn secondary" type="button" data-cx-closing-open="${h(item.id)}">Abrir</button>
          ${cxClosingNorm023K(item.status) !== "archived" ? `<button class="cx-closing-btn danger" type="button" data-cx-closing-save-archive="${h(item.id)}">Guardar y archivar</button>` : ""}
        </div>
      </article>
    `;
  }

  function cxClosingModal023M(item) {
    if (!item) return "";
    const totals = item.totals || {};
    const snapshot = {
      totals,
      users: item.users || [],
      connection_snapshot: item.connection_snapshot || {},
      snapshot: item.snapshot || {}
    };
    return `
      <div class="cx-closing-modal-backdrop" data-cx-closing-close>
        <article class="cx-closing-modal" role="dialog" aria-modal="true" aria-label="Detalle del cierre" onclick="event.stopPropagation()">
          <div class="cx-closing-modal-head">
            <div>
              <div class="cx-closing-kicker">Detalle completo enviado</div>
              <h2>${h(cxClosingPanelLabel023K(item.panel_type))} · ${h(cxClosingDateLabel023K(item.closure_date))}</h2>
              <p class="cx-closing-muted">Responsable: ${h(item.submitted_by_label || "Panel principal")} · Estado: ${h(cxClosingStatusLabel023K(item.status))} · Enviado ${h(cxClosingDateTimeLabel023K(item.submitted_at))}</p>
            </div>
            <button class="cx-closing-modal-close" type="button" data-cx-closing-close>×</button>
          </div>
          <div class="cx-closing-detail-grid">
            <div class="cx-closing-kpi"><span>Total recaudado</span><strong>${h(cxClosingMoney023K(totals.total_amount || 0))}</strong><small>${Number(totals.sales_count || 0)} ventas · ${Number(totals.invoices_count || 0)} facturas</small></div>
            <div class="cx-closing-kpi"><span>Efectivo</span><strong>${h(cxClosingMoney023K(totals.cash_amount || 0))}</strong><small>Transferencias ${h(cxClosingMoney023K(totals.transfer_amount || 0))}</small></div>
            <div class="cx-closing-kpi"><span>Cotizaciones</span><strong>${Number(totals.quotes_count || 0)}</strong><small>${h(cxClosingMoney023K(totals.quotes_amount || 0))}</small></div>
            <div class="cx-closing-kpi"><span>Solicitudes</span><strong>${Number(totals.requests_count || 0)}</strong><small>Cheque ${h(cxClosingMoney023K(totals.check_amount || 0))} · Otro ${h(cxClosingMoney023K(totals.other_amount || 0))}</small></div>
          </div>
          ${item.notes ? `<p class="cx-closing-muted" style="margin-top:14px">${h(item.notes)}</p>` : ""}
          <div class="cx-closing-kicker" style="margin-top:18px">Vendedores / colaboradores</div>
          <div class="cx-closing-users">${cxClosingUserList023K(item.users || [])}</div>
          <details style="margin-top:18px">
            <summary class="cx-closing-muted" style="cursor:pointer">Ver paquete tecnico del cierre</summary>
            <pre class="cx-closing-json">${h(JSON.stringify(snapshot, null, 2))}</pre>
          </details>
        </article>
      </div>
    `;
  }

  function cxClosingDetail023K(item) {
    if (!item) {
      return `
        <article class="cx-closing-card">
          <div class="cx-closing-kicker">Detalle</div>
          <h2>Selecciona un cierre</h2>
          <p class="cx-closing-muted">Cuando un vendedor o tienda envie cierre desde el mini panel, podras abrirlo aqui.</p>
        </article>
      `;
    }
    const totals = item.totals || {};
    return `
      <article class="cx-closing-card">
        <div class="cx-closing-kicker">Detalle del cierre</div>
        <h2>${h(cxClosingPanelLabel023K(item.panel_type))} · ${h(cxClosingDateLabel023K(item.closure_date))}</h2>
        <p class="cx-closing-muted">Responsable: ${h(item.submitted_by_label || "Panel principal")} · Estado: ${h(cxClosingStatusLabel023K(item.status))}</p>
        <div class="cx-closing-detail-grid">
          <div class="cx-closing-kpi"><span>Total recaudado</span><strong>${h(cxClosingMoney023K(totals.total_amount || 0))}</strong><small>${Number(totals.sales_count || 0)} ventas</small></div>
          <div class="cx-closing-kpi"><span>Efectivo</span><strong>${h(cxClosingMoney023K(totals.cash_amount || 0))}</strong><small>Transferencia ${h(cxClosingMoney023K(totals.transfer_amount || 0))}</small></div>
          <div class="cx-closing-kpi"><span>Cotizaciones</span><strong>${Number(totals.quotes_count || 0)}</strong><small>${h(cxClosingMoney023K(totals.quotes_amount || 0))}</small></div>
          <div class="cx-closing-kpi"><span>Solicitudes</span><strong>${Number(totals.requests_count || 0)}</strong><small>${Number(totals.invoices_count || 0)} facturas</small></div>
        </div>
        ${item.notes ? `<p class="cx-closing-muted" style="margin-top:14px">${h(item.notes)}</p>` : ""}
        <div class="cx-closing-kicker" style="margin-top:18px">Vendedores del cierre</div>
        <div class="cx-closing-users">${cxClosingUserList023K(item.users || [])}</div>
      </article>
    `;
  }

  function cxClosingStoreCard023K(store) {
    return `
      <article class="cx-closing-card">
        <div class="cx-closing-store-head">
          <div>
            <div class="cx-closing-kicker">Tienda / panel</div>
            <h3>${h(store.label || "Tienda")}</h3>
            <p class="cx-closing-muted">${Number(store.closures_count || 0)} cierres · ultimo ${h(cxClosingDateLabel023K(store.last_closure_date))}</p>
          </div>
          <strong>${h(cxClosingMoney023K(store.total_amount || 0))}</strong>
        </div>
        <div class="cx-closing-users">${cxClosingUserList023K(store.users || [], "Sin colaboradores reportados para esta tienda.")}</div>
        <div class="cx-closing-actions" style="margin-top:12px">
          <button class="cx-closing-btn secondary" type="button" data-cx-closing-store="${h(store.panel_type || "stores")}">Ver tienda</button>
        </div>
      </article>
    `;
  }

  async function renderCommercialClosingModule023K(options = {}) {
    cxClosingStyles023K();
    const filters = cxClosingFilters023K(options);
    const company = state.company || {};
    let data = { items: [], summary: {}, stores: [], sellers: [], groups: [] };
    let loadError = "";

    try {
      data = await cxClosingApi023K(`/client-console?${cxClosingQuery023K(filters)}`);
    } catch (error) {
      loadError = error.message || "No se pudo cargar cierre comercial.";
    }

    const items = Array.isArray(data.items) ? data.items : [];
    const summary = data.summary || {};
    const selected = items.find((item) => String(item.id || "") === String(filters.selected_id || "")) || null;
    const selectedId = selected?.id || "";
    const bestSeller = summary.best_seller || {};
    const bestStore = summary.best_store || {};
    const stores = Array.isArray(data.stores) ? data.stores : [];
    const sellers = Array.isArray(data.sellers) ? data.sellers : [];
    const groups = Array.isArray(data.groups) ? data.groups : [];
    const salesItems = cxClosingPanelItems023M(items, "sales");
    const storeItems = cxClosingPanelItems023M(items, "stores");
    const salesSellers = cxClosingAggregateUsers023M(salesItems);

    $("app").innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, normalizeBranding(state.branding || {}))}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>
            <nav class="client-nav">${renderClientNav("commercial_closing")}</nav>
            <div class="client-footer-id"><strong>Tenant activo</strong><br>${h(state.companyId || "")}</div>
          </aside>

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">Modulo Cierre Comercial</div>
              <h1 class="client-title">Cierre comercial</h1>
              <p class="client-muted">Consolidado de cierres diarios reportados desde mini paneles asociados a esta empresa.</p>
              <div class="client-actions">
                <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
                <button class="client-btn" type="button" data-cx-closing-refresh>Actualizar</button>
              </div>
            </header>

            <section class="cx-closing-shell">
              ${loadError ? `<div class="personal-toast error">${h(loadError)}</div>` : ""}

              <article class="cx-closing-card">
                <div class="cx-closing-toolbar">
                  <div class="cx-closing-field"><label>Desde</label><input id="cxClosingFrom023K" type="date" value="${h(filters.from)}"></div>
                  <div class="cx-closing-field"><label>Hasta</label><input id="cxClosingTo023K" type="date" value="${h(filters.to)}"></div>
                  <div class="cx-closing-field">
                    <label>Panel</label>
                    <select id="cxClosingPanel023K">
                      <option value="all" ${filters.panel_type === "all" ? "selected" : ""}>Todos</option>
                      <option value="sales" ${filters.panel_type === "sales" ? "selected" : ""}>Ventas</option>
                      <option value="stores" ${filters.panel_type === "stores" ? "selected" : ""}>Tiendas</option>
                    </select>
                  </div>
                  <div class="cx-closing-field">
                    <label>Estado</label>
                    <select id="cxClosingStatus023K">
                      <option value="active" ${filters.status === "active" ? "selected" : ""}>Activos</option>
                      <option value="all" ${filters.status === "all" ? "selected" : ""}>Todos</option>
                      <option value="submitted" ${filters.status === "submitted" ? "selected" : ""}>Enviados</option>
                      <option value="reviewed" ${filters.status === "reviewed" ? "selected" : ""}>Guardados</option>
                      <option value="archived" ${filters.status === "archived" ? "selected" : ""}>Archivados</option>
                    </select>
                  </div>
                  <div class="cx-closing-field"><label>Buscar</label><input id="cxClosingSearch023K" value="${h(filters.q)}" placeholder="Vendedor, tienda, fecha o estado"></div>
                  <button class="cx-closing-btn" type="button" data-cx-closing-apply>Buscar</button>
                </div>
              </article>

              <section class="cx-closing-kpis">
                <article class="cx-closing-kpi"><span>Cierres recibidos</span><strong>${Number(summary.closures_count || 0)}</strong><small>${Number(summary.submitted_count || 0)} enviados · ${Number(summary.reviewed_count || 0)} guardados</small></article>
                <article class="cx-closing-kpi"><span>Dinero recolectado</span><strong>${h(cxClosingMoney023K(summary.total_amount || 0))}</strong><small>Efectivo ${h(cxClosingMoney023K(summary.cash_amount || 0))}</small></article>
                <article class="cx-closing-kpi"><span>Mejor vendedor</span><strong>${h(bestSeller.label || "Sin datos")}</strong><small>${h(cxClosingMoney023K(bestSeller.total_amount || 0))} · ${Number(bestSeller.sales_count || 0)} ventas</small></article>
                <article class="cx-closing-kpi"><span>Mejor tienda</span><strong>${h(bestStore.label || "Sin cierres")}</strong><small>${h(cxClosingMoney023K(bestStore.total_amount || 0))} · ${Number(bestStore.closures_count || 0)} cierres</small></article>
              </section>

              <section class="cx-closing-report-grid">
                ${cxClosingReportColumn023M("Reportes de ventas", "Cierres recibidos", salesItems, selectedId, "No hay cierres de ventas para este filtro.")}
                ${cxClosingReportColumn023M("Reportes de tiendas", "Cierres por tienda", storeItems, selectedId, "Aun no hay cierres enviados desde paneles de tienda.")}
              </section>

              <section class="cx-closing-rank-grid">
                <article class="cx-closing-card">
                  <div class="cx-closing-kicker">Ventas</div>
                  <h2>Recaudo por vendedor</h2>
                  <div class="cx-closing-users">${cxClosingUserList023K(salesSellers, "Sin recaudos de vendedores en los cierres de ventas.")}</div>
                </article>
                <article class="cx-closing-card">
                  <div class="cx-closing-kicker">Tiendas</div>
                  <h2>Recaudo por tienda</h2>
                  <div class="cx-closing-users">${cxClosingStoreRows023M(stores)}</div>
                </article>
              </section>

              <section class="cx-closing-card">
                <div class="cx-closing-kicker">Ranking total</div>
                <h2>Consolidado ventas / tiendas</h2>
                <div class="cx-closing-users">${cxClosingRankingRows023M(groups)}</div>
              </section>
            </section>
          </section>
        </div>
        ${cxClosingModal023M(selected)}
      </main>
    `;

    document.querySelector("[data-cx-closing-refresh]")?.addEventListener("click", () => renderCommercialClosingModule023K({ ...filters, selected_id: selectedId }));
    document.querySelector("[data-cx-closing-apply]")?.addEventListener("click", () => renderCommercialClosingModule023K(cxClosingReadFilters023K(filters)));
    document.getElementById("cxClosingSearch023K")?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") renderCommercialClosingModule023K(cxClosingReadFilters023K(filters));
    });

    document.querySelectorAll("[data-cx-closing-open]").forEach((button) => {
      button.addEventListener("click", () => {
        renderCommercialClosingModule023K({ ...cxClosingReadFilters023K(filters), selected_id: button.getAttribute("data-cx-closing-open") || "" });
      });
    });

    document.querySelectorAll("[data-cx-closing-close]").forEach((button) => {
      button.addEventListener("click", () => {
        renderCommercialClosingModule023K({ ...cxClosingReadFilters023K(filters), selected_id: "" });
      });
    });

    document.querySelectorAll("[data-cx-closing-save-archive]").forEach((button) => {
      button.addEventListener("click", async () => {
        const id = button.getAttribute("data-cx-closing-save-archive");
        if (!id) return;
        if (!confirm("Guardar y archivar este cierre? No se borrara; quedara disponible en archivados.")) return;
        await cxClosingApi023K(`/client-console/${encodeURIComponent(id)}/review`, {
          method: "POST",
          body: JSON.stringify({})
        });
        await cxClosingApi023K(`/client-console/${encodeURIComponent(id)}/archive`, {
          method: "POST",
          body: JSON.stringify({})
        });
        await renderCommercialClosingModule023K({ ...cxClosingReadFilters023K(filters), selected_id: "" });
      });
    });

    document.querySelectorAll("[data-cx-closing-store]").forEach((button) => {
      button.addEventListener("click", () => {
        renderCommercialClosingModule023K({ ...cxClosingReadFilters023K(filters), panel_type: button.getAttribute("data-cx-closing-store") || "stores" });
      });
    });
  }
  /* CLONEXA_023K_CLIENT_COMMERCIAL_CLOSING_CONSOLE_END */

  async function renderClientModulePlaceholder(code) {
    /* CLONEXA_021D_R1_FORCE_UNIVERSAL_PLACEHOLDER_ROUTER_START */
    const cxUniversalPlaceholderCode021DR1 = String(code || "").trim();

    if (
      typeof cxIsReferencesCode022E === "function" &&
      cxIsReferencesCode022E(cxUniversalPlaceholderCode021DR1) &&
      typeof renderReferencesModule022E === "function"
    ) {
      return renderReferencesModule022E();
    }

    if (
      typeof cxIsQuotesUniversalCode021D === "function" &&
      cxIsQuotesUniversalCode021D(cxUniversalPlaceholderCode021DR1) &&
      typeof renderClientUniversalQuotesModule021D === "function"
    ) {
      return renderClientUniversalQuotesModule021D(cxUniversalPlaceholderCode021DR1 || "cotizaciones");
    }

    if (
      typeof cxIsNotesUniversalCode021D === "function" &&
      cxIsNotesUniversalCode021D(cxUniversalPlaceholderCode021DR1) &&
      typeof renderClientUniversalNotesModule021D === "function"
    ) {
      return renderClientUniversalNotesModule021D(cxUniversalPlaceholderCode021DR1 || "notas");
    }

    if (
      typeof cxIsCommercialClosingCode023K === "function" &&
      cxIsCommercialClosingCode023K(cxUniversalPlaceholderCode021DR1) &&
      typeof renderCommercialClosingModule023K === "function"
    ) {
      return renderCommercialClosingModule023K();
    }
    /* CLONEXA_021D_R1_FORCE_UNIVERSAL_PLACEHOLDER_ROUTER_END */
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

    
  /* CLONEXA_022F_CLIENT_REGISTRO_VENTA_CONSOLIDADO_START */
  function cxSalesRegisterNorm022F(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
  }

  function cxIsSalesRegisterCode022F(code) {
    return new Set([
      "registro_venta",
      "registro_ventas",
      "registro_de_venta",
      "sales_register",
      "register_sale",
      "register_sales",
      "venta_registro"
    ]).has(cxSalesRegisterNorm022F(code));
  }

  function cxSalesMoney022F(value) {
    const number = Number(value || 0);
    try {
      return number.toLocaleString("es-CO", {
        style: "currency",
        currency: "COP",
        maximumFractionDigits: 0
      });
    } catch (_) {
      return `$ ${Math.round(number).toLocaleString("es-CO")}`;
    }
  }

  function cxSalesStyles022F() {
    if (document.getElementById("cxSalesStyles022F")) return;
    const style = document.createElement("style");
    style.id = "cxSalesStyles022F";
    style.textContent = `
      .cx-sales22-grid{display:grid;grid-template-columns:1.1fr .9fr;gap:18px}
      .cx-sales22-card{border:1px solid rgba(255,255,255,.12);border-radius:28px;background:linear-gradient(135deg,rgba(255,255,255,.12),rgba(255,255,255,.04));box-shadow:0 20px 70px rgba(0,0,0,.25);padding:22px}
      .cx-sales22-kicker{font-size:11px;font-weight:950;letter-spacing:.28em;text-transform:uppercase;color:#ff39d0}
      .cx-sales22-title{font-size:38px;margin:8px 0 8px}
      .cx-sales22-muted{color:rgba(255,255,255,.72);font-weight:750}
      .cx-sales22-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
      .cx-sales22-field label{display:block;font-size:11px;font-weight:950;text-transform:uppercase;letter-spacing:.12em;margin:0 0 7px;color:rgba(255,255,255,.68)}
      .cx-sales22-field input,.cx-sales22-field select,.cx-sales22-field textarea{width:100%;box-sizing:border-box;border:1px solid rgba(255,255,255,.16);border-radius:16px;background:rgba(3,7,22,.55);color:#fff;padding:13px 14px;font-weight:850}
      .cx-sales22-btn{border:0;border-radius:17px;background:linear-gradient(135deg,#ff24b8,#7357ff);color:#fff;font-weight:950;padding:13px 16px;cursor:pointer}
      .cx-sales22-btn.secondary{background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.14)}
      .cx-sales22-list{display:grid;gap:12px;margin-top:14px;max-height:560px;overflow:auto}
      .cx-sales22-sale{border:1px solid rgba(255,255,255,.12);border-radius:20px;background:rgba(255,255,255,.06);padding:15px}
      .cx-sales22-sale strong{display:flex;justify-content:space-between;gap:14px;font-size:16px}
      .cx-sales22-filters{display:grid;grid-template-columns:1fr 170px 140px;gap:10px;margin-top:14px}
      .cx-sales22-mini-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:14px}
      .cx-sales22-stat{border:1px solid rgba(255,255,255,.12);border-radius:20px;background:rgba(255,255,255,.07);padding:14px;min-height:88px}
      .cx-sales22-stat span{display:block;font-size:11px;font-weight:950;text-transform:uppercase;letter-spacing:.12em;color:rgba(255,255,255,.66);margin-bottom:7px}
      .cx-sales22-stat strong{display:block;font-size:18px;color:#fff}
      .cx-sales22-stat small{display:block;margin-top:7px;color:rgba(255,255,255,.68);font-weight:800}
      .cx-sales22-section-head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;flex-wrap:wrap}
      .cx-sales22-section-head .cx-sales22-filters{margin-top:0;min-width:min(760px,100%)}
      .cx-sales22-invoice{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:6px 10px;background:rgba(41,255,187,.12);border:1px solid rgba(41,255,187,.24);color:#8fffd8;font-size:12px;font-weight:950;margin-bottom:8px}
      .cx-sales22-cut-actions{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:end;margin-top:14px}
      @media(max-width:1100px){.cx-sales22-grid,.cx-sales22-row,.cx-sales22-filters,.cx-sales22-mini-grid,.cx-sales22-cut-actions{grid-template-columns:1fr}}
    `;
    document.head.appendChild(style);
  }

  async function cxSalesApi022F(path, options = {}) {
    return api(`/mini-panel-sales/companies/${encodeURIComponent(state.companyId)}${path}`, options);
  }

  async function renderClientSalesRegisterModule022F(options = {}) {
    cxSalesStyles022F();

    let config = { occupation: "technology", custom_categories: [] };
    let salesData = { items: [], active_count: 0, total_amount: 0 };
    let categories = { items: [] };
    let loadError = "";

    try {
      config = await cxSalesApi022F("/config");
      salesData = await cxSalesApi022F(`/sales?panel_type=all&include_archived=${options.include_archived ? "true" : "false"}&q=${encodeURIComponent(options.q || "")}`);
      categories = await cxSalesApi022F("/categories?panel_type=all");
    } catch (error) {
      loadError = error.message || "No se pudo cargar Registro Venta.";
    }

    const company = state.company || {};
    const items = Array.isArray(salesData.items) ? salesData.items : [];
    const categoriesText = (Array.isArray(categories.items) ? categories.items : [])
      .map((item) => item.category)
      .filter(Boolean)
      .join(", ");

    $("app").innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, normalizeBranding(state.branding || {}))}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>
            <nav class="client-nav">${renderClientNav("registro_venta")}</nav>
            <div class="client-footer-id"><strong>Tenant activo</strong><br>${h(state.companyId || "")}</div>
          </aside>

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">Módulo Registro Venta</div>
              <h1 class="client-title">Registro Venta</h1>
              <p class="client-muted">Configura la ocupación comercial y revisa el consolidado de ventas capturadas desde mini paneles.</p>
              <div class="client-actions">
                <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
                <button class="client-btn" type="button" data-cx-sales22-refresh>Actualizar</button>
              </div>
            </header>

            ${loadError ? `<div class="personal-toast error">${h(loadError)}</div>` : ""}

            <section class="cx-sales22-grid">
              <article class="cx-sales22-card">
                <div class="cx-sales22-kicker">Configuración por empresa</div>
                <h2 class="cx-sales22-title">Ocupación comercial</h2>
                <p class="cx-sales22-muted">Esta regla define las categorías visuales del mini panel cuando no existan categorías creadas en Referencias.</p>

                <div class="cx-sales22-row" style="margin-top:16px">
                  <div class="cx-sales22-field">
                    <label>Ocupación</label>
                    <select id="cxSalesOccupation022F">
                      <option value="technology" ${config.occupation === "technology" ? "selected" : ""}>Tecnología</option>
                      <option value="ropa" ${config.occupation === "ropa" ? "selected" : ""}>Ropa</option>
                      <option value="accesorios" ${config.occupation === "accesorios" ? "selected" : ""}>Accesorios</option>
                      <option value="servicios" ${config.occupation === "servicios" ? "selected" : ""}>Servicios</option>
                      <option value="custom" ${config.occupation === "custom" ? "selected" : ""}>Otro / personalizado</option>
                    </select>
                  </div>
                  <div class="cx-sales22-field">
                    <label>Categorías personalizadas</label>
                    <input id="cxSalesCustomCategories022F" value="${h((config.custom_categories || []).join(", "))}" placeholder="Ej: Celulares, Cables, Otros" />
                  </div>
                </div>

                <button class="cx-sales22-btn" type="button" data-cx-sales22-save-config style="margin-top:14px">Guardar configuración</button>
                <div class="cx-sales22-muted" style="margin-top:14px">Categorías actuales: ${h(categoriesText || "Sin categorías. Usa Referencias o configura ocupación.")}</div>
                <div id="cxSalesMsg022F" class="cx-sales22-muted" style="margin-top:10px"></div>
              </article>

              <article class="cx-sales22-card">
                <div class="cx-sales22-kicker">Consolidado</div>
                <h2 class="cx-sales22-title">${h(cxSalesMoney022F(salesData.total_amount || 0))}</h2>
                <p class="cx-sales22-muted">${Number(salesData.active_count || 0)} ventas activas capturadas desde mini paneles.</p>
                <div class="cx-sales22-filters">
                  <input id="cxSalesFilter022F" value="${h(options.q || "")}" placeholder="Buscar referencia, usuario o categoría..." />
                  <select id="cxSalesArchived022F">
                    <option value="false">Activas</option>
                    <option value="true" ${options.include_archived ? "selected" : ""}>Incluye archivadas</option>
                  </select>
                  <button class="cx-sales22-btn secondary" type="button" data-cx-sales22-apply>Buscar</button>
                </div>
              </article>
            </section>

            <section class="cx-sales22-card" style="margin-top:18px">
              <div class="cx-sales22-kicker">Ventas desde mini paneles</div>
              <div class="cx-sales22-list">
                ${items.map((item) => `
                  <article class="cx-sales22-sale">
                    <strong>
                      <span>${h(item.reference_name || "Venta")}</span>
                      <span>${h(cxSalesMoney022F(item.total || 0))}</span>
                    </strong>
                    <div class="cx-sales22-muted">${h(item.reference_category || "Sin categoría")} · ${h(item.reference_size || "")} ${h(item.reference_color || "")}</div>
                    <div class="cx-sales22-muted">Origen: ${h(item.source_panel_label || item.panel_type || "Mini Panel")} · ${h(item.source_user_label || item.created_by_label || "Usuario")}</div>
                    <div class="cx-sales22-muted">${h(item.created_at || "")} · ${h(item.payment_method || "")}</div>
                    ${item.status !== "archived" ? `<button class="cx-sales22-btn secondary" type="button" data-cx-sales22-archive="${h(item.id)}" style="margin-top:10px">Archivar</button>` : `<span class="cx-sales22-muted">Archivada</span>`}
                  </article>
                `).join("") || `<div class="cx-sales22-muted">Sin ventas registradas desde mini paneles.</div>`}
              </div>
            </section>
          </section>
        </div>
      </main>
    `;
  }

  /* CLONEXA_022G_CLIENT_SALES_PIPELINE_GUIDE_START */
  function cxSalesPipelineStyles022G() {
    cxSalesStyles022F();
    if (document.getElementById("cxSalesPipelineStyles022G")) return;
    const style = document.createElement("style");
    style.id = "cxSalesPipelineStyles022G";
    style.textContent = `
      .cx-sales22-status{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
      .cx-sales22-pill{display:inline-flex;border-radius:999px;padding:7px 10px;background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.14);font-size:12px;font-weight:950;color:#fff}
      .cx-sales22-pill.ok{background:rgba(41,255,187,.13);border-color:rgba(41,255,187,.32);color:#8fffd8}
      .cx-sales22-pill.warn{background:rgba(255,211,77,.12);border-color:rgba(255,211,77,.32);color:#ffe08a}
      .cx-sales22-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
      .cx-sales22-file{display:inline-flex;align-items:center;justify-content:center;border-radius:14px;padding:10px 12px;background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.16);font-weight:950;cursor:pointer;font-size:12px;color:#fff}
      .cx-sales22-file input{display:none}
      .cx-sales22-btn.danger{background:rgba(255,74,124,.18);border:1px solid rgba(255,74,124,.45)}
    `;
    document.head.appendChild(style);
  }

  function cxSalesFileToDataUrl022G(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(new Error("No se pudo leer el archivo."));
      reader.readAsDataURL(file);
    });
  }

  function cxSalesOpenFile022G(file) {
    if (!file?.file_data) return;
    const win = window.open("", "_blank");
    if (!win) return;
    const src = file.file_data;
    const isPdf = String(file.file_type || "").includes("pdf");
    win.document.write(isPdf
      ? `<iframe src="${src}" style="width:100%;height:100vh;border:0"></iframe>`
      : `<img src="${src}" style="max-width:100%;height:auto;display:block;margin:auto" />`);
  }

  function cxSalesDownloadFile022G(file, fallbackName = "archivo") {
    if (!file?.file_data) return;
    const a = document.createElement("a");
    a.href = file.file_data;
    a.download = file.file_name || fallbackName;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  function cxSalesStatusHtml022G(item) {
    const archived = String(item?.status || "").toLowerCase() === "archived";
    return `
      <div class="cx-sales22-status">
        <span class="cx-sales22-pill ok">Venta registrada</span>
        <span class="cx-sales22-pill ${item?.is_prepared ? "ok" : "warn"}">${item?.is_prepared ? "Alistado" : "Pendiente alistar"}</span>
        <span class="cx-sales22-pill ${item?.has_support ? "ok" : "warn"}">${item?.has_support ? "Soporte adjunto" : "Sin soporte"}</span>
        <span class="cx-sales22-pill ${item?.has_guide ? "ok" : "warn"}">${item?.has_guide ? "Guía enviada" : "Sin guía"}</span>
        ${archived ? `<span class="cx-sales22-pill">Archivada</span>` : ""}
      </div>
    `;
  }

  async function renderClientSalesRegisterModule022F(options = {}) {
    cxSalesPipelineStyles022G();

    let config = { occupation: "technology", custom_categories: [] };
    let salesData = { items: [], active_count: 0, total_amount: 0, cut: {} };
    let categories = { items: [] };
    let cutData = { total_amount: 0, active_count: 0, period_type: "weekly", period_label: "Semanal", top_seller: {}, top_store: {} };
    let loadError = "";

    try {
      config = await cxSalesApi022F("/config");
      cutData = await cxSalesApi022F("/cut?panel_type=all");
      salesData = await cxSalesApi022F(`/sales?panel_type=all&include_archived=${options.include_archived ? "true" : "false"}&q=${encodeURIComponent(options.q || "")}`);
      categories = await cxSalesApi022F("/categories?panel_type=all");
    } catch (error) {
      loadError = error.message || "No se pudo cargar Registro Venta.";
    }

    const company = state.company || {};
    const items = Array.isArray(salesData.items) ? salesData.items : [];
    const itemMap = new Map(items.map((item) => [String(item.id), item]));
    const categoriesText = (Array.isArray(categories.items) ? categories.items : [])
      .map((item) => item.category)
      .filter(Boolean)
      .join(", ");
    const cut = cutData && typeof cutData === "object" ? cutData : (salesData.cut || {});
    const topSeller = cut.top_seller || {};
    const topStore = cut.top_store || {};
    const periodType = options.period_type || cut.period_type || "weekly";
    const totalConsolidated = Number(cut.total_amount ?? salesData.total_amount ?? 0);
    const activeCount = Number(cut.active_count ?? salesData.active_count ?? 0);

    $("app").innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, normalizeBranding(state.branding || {}))}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>
            <nav class="client-nav">${renderClientNav("registro_venta")}</nav>
            <div class="client-footer-id"><strong>Tenant activo</strong><br>${h(state.companyId || "")}</div>
          </aside>

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">Módulo Registro Venta</div>
              <h1 class="client-title">Registro Venta</h1>
              <p class="client-muted">Consolida ventas de mini paneles, valida alistamiento, revisa soportes y envía guías.</p>
              <div class="client-actions">
                <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
                <button class="client-btn" type="button" data-cx-sales22-refresh>Actualizar</button>
              </div>
            </header>

            ${loadError ? `<div class="personal-toast error">${h(loadError)}</div>` : ""}

            <section class="cx-sales22-grid">
              <article class="cx-sales22-card">
                <div class="cx-sales22-kicker">Configuración por empresa</div>
                <h2 class="cx-sales22-title">Ocupación comercial</h2>
                <p class="cx-sales22-muted">Define categorías visuales y el tipo de corte comercial activo.</p>

                <div class="cx-sales22-row" style="margin-top:16px">
                  <div class="cx-sales22-field">
                    <label>Ocupación</label>
                    <select id="cxSalesOccupation022F">
                      <option value="technology" ${config.occupation === "technology" ? "selected" : ""}>Tecnología</option>
                      <option value="ropa" ${config.occupation === "ropa" ? "selected" : ""}>Ropa</option>
                      <option value="accesorios" ${config.occupation === "accesorios" ? "selected" : ""}>Accesorios</option>
                      <option value="servicios" ${config.occupation === "servicios" ? "selected" : ""}>Servicios</option>
                      <option value="custom" ${config.occupation === "custom" ? "selected" : ""}>Otro / personalizado</option>
                    </select>
                  </div>
                  <div class="cx-sales22-field">
                    <label>Categorías personalizadas</label>
                    <input id="cxSalesCustomCategories022F" value="${h((config.custom_categories || []).join(", "))}" placeholder="Ej: Celulares, Cables, Otros" />
                  </div>
                </div>

                <button class="cx-sales22-btn" type="button" data-cx-sales22-save-config style="margin-top:14px">Guardar configuración</button>
                <div class="cx-sales22-muted" style="margin-top:14px">Categorías actuales: ${h(categoriesText || "Sin categorías. Usa Referencias o configura ocupación.")}</div>

                <div class="cx-sales22-cut-actions">
                  <div class="cx-sales22-field">
                    <label>Corte comercial</label>
                    <select id="cxSalesCutPeriod022L">
                      <option value="weekly" ${periodType === "weekly" ? "selected" : ""}>Semanal</option>
                      <option value="biweekly" ${periodType === "biweekly" ? "selected" : ""}>Quincenal</option>
                      <option value="monthly" ${periodType === "monthly" ? "selected" : ""}>Mensual</option>
                    </select>
                  </div>
                  <button class="cx-sales22-btn" type="button" data-cx-sales22-generate-cut>Generar corte</button>
                </div>
                <div class="cx-sales22-muted" style="margin-top:10px">
                  Corte activo: ${h(cut.period_label || "Semanal")} · Desde: ${h(cut.period_started_at || "primer registro")}
                </div>
                <div id="cxSalesMsg022F" class="cx-sales22-muted" style="margin-top:10px"></div>
              </article>

              <article class="cx-sales22-card">
                <div class="cx-sales22-kicker">Consolidado actual</div>
                <h2 class="cx-sales22-title">${h(cxSalesMoney022F(totalConsolidated))}</h2>
                <p class="cx-sales22-muted">${activeCount} ventas activas en el corte actual.</p>
                <div class="cx-sales22-mini-grid">
                  <div class="cx-sales22-stat">
                    <span>Top vendedor</span>
                    <strong>${h(topSeller.label || "Sin ventas")}</strong>
                    <small>${h(cxSalesMoney022F(topSeller.amount || 0))} · ${Number(topSeller.count || 0)} ventas</small>
                  </div>
                  <div class="cx-sales22-stat">
                    <span>Top tienda</span>
                    <strong>${h(topStore.label || "Próximamente")}</strong>
                    <small>${h(cxSalesMoney022F(topStore.amount || 0))}${topStore.status === "pending" ? " · módulo tiendas próximo" : ""}</small>
                  </div>
                </div>
              </article>
            </section>

            <section class="cx-sales22-card" style="margin-top:18px">
              <div class="cx-sales22-section-head">
                <div>
                  <div class="cx-sales22-kicker">Ventas desde mini paneles</div>
                  <p class="cx-sales22-muted">${items.length} registros visibles del corte actual. Busca por factura, usuario, referencia, categoría, pago o estado.</p>
                </div>
                <div class="cx-sales22-filters">
                  <input id="cxSalesFilter022F" value="${h(options.q || "")}" placeholder="Buscar factura, usuario, referencia, categoría..." />
                  <select id="cxSalesArchived022F">
                    <option value="false">Activas</option>
                    <option value="true" ${options.include_archived ? "selected" : ""}>Incluye archivadas</option>
                  </select>
                  <button class="cx-sales22-btn secondary" type="button" data-cx-sales22-apply>Buscar</button>
                </div>
              </div>

              <div class="cx-sales22-list">
                ${items.map((item) => `
                  <article class="cx-sales22-sale">
                    <div class="cx-sales22-invoice">${h(item.invoice_number || `FV-${String(item.id || "").slice(0, 8).toUpperCase()}`)}</div>
                    <strong>
                      <span>${h(item.reference_name || "Venta")}</span>
                      <span>${h(cxSalesMoney022F(item.total_payable ?? item.total ?? 0))}</span>
                    </strong>
                    <div class="cx-sales22-muted">${h(item.reference_category || "Sin categoría")} · ${h(item.reference_size || "")} ${h(item.reference_color || "")}</div>
                    <div class="cx-sales22-muted">Origen: ${h(item.source_panel_label || item.panel_type || "Mini Panel")} · ${h(item.source_user_label || item.created_by_label || "Usuario")}</div>
                    <div class="cx-sales22-muted">${h(item.created_at || "")} · ${h(item.payment_method || "")}</div>
                    ${item.adjustment_type && item.adjustment_type !== "none" ? `
                      <div class="cx-sales22-muted">Ajuste: ${h(item.adjustment_label || "Ajuste")} ${Number(item.adjustment_percent || 0)}% · ${h(cxSalesMoney022F(item.adjustment_amount || 0))} · Total a pagar ${h(cxSalesMoney022F(item.total_payable ?? item.total ?? 0))}</div>
                    ` : ""}
                    ${cxSalesStatusHtml022G(item)}
                    <div class="cx-sales22-actions">
                      ${item.has_support ? `
                        <button class="cx-sales22-btn secondary" type="button" data-cx-sales22-open-support="${h(item.id)}">Ver soporte</button>
                        <button class="cx-sales22-btn secondary" type="button" data-cx-sales22-download-support="${h(item.id)}">Descargar soporte</button>
                      ` : ""}
                      ${item.has_guide ? `
                        <button class="cx-sales22-btn secondary" type="button" data-cx-sales22-open-guide="${h(item.id)}">Ver guía</button>
                        <button class="cx-sales22-btn secondary" type="button" data-cx-sales22-download-guide="${h(item.id)}">Descargar guía</button>
                      ` : ""}
                      ${item.status !== "archived" ? `
                        <label class="cx-sales22-file">Adjuntar guía
                          <input type="file" accept="image/*,.pdf" data-cx-sales22-guide-file="${h(item.id)}">
                        </label>
                        <button class="cx-sales22-btn danger" type="button" data-cx-sales22-archive="${h(item.id)}">Archivar</button>
                      ` : `<span class="cx-sales22-muted">Archivada</span>`}
                    </div>
                  </article>
                `).join("") || `<div class="cx-sales22-muted">Sin ventas registradas desde mini paneles en este corte.</div>`}
              </div>
            </section>
          </section>
        </div>
      </main>
    `;

    document.querySelector("[data-cx-sales22-refresh]")?.addEventListener("click", () => renderClientSalesRegisterModule022F(options));

    document.getElementById("cxSalesCutPeriod022L")?.addEventListener("change", async () => {
      const msg = document.getElementById("cxSalesMsg022F");
      try {
        const period = document.getElementById("cxSalesCutPeriod022L")?.value || "weekly";
        if (msg) msg.textContent = "Guardando tipo de corte...";
        await cxSalesApi022F("/cut/config", {
          method: "POST",
          body: JSON.stringify({ period_type: period })
        });
        if (msg) msg.textContent = "Tipo de corte guardado. El acumulado sigue vigente hasta generar corte.";
      } catch (error) {
        if (msg) msg.textContent = error.message || "No se pudo guardar el corte.";
      }
    });

    document.querySelector("[data-cx-sales22-generate-cut]")?.addEventListener("click", async () => {
      const period = document.getElementById("cxSalesCutPeriod022L")?.value || "weekly";
      if (!confirm("Generar corte ahora? Se archivará el acumulado actual y el nuevo acumulado iniciará en $0. No se borrarán ventas.")) return;
      const msg = document.getElementById("cxSalesMsg022F");
      try {
        if (msg) msg.textContent = "Generando corte...";
        await cxSalesApi022F("/cut/generate?panel_type=all", {
          method: "POST",
          body: JSON.stringify({ period_type: period })
        });
        await renderClientSalesRegisterModule022F({ ...options, q: "", include_archived: false, period_type: period });
      } catch (error) {
        if (msg) msg.textContent = error.message || "No se pudo generar el corte.";
      }
    });

    document.querySelector("[data-cx-sales22-save-config]")?.addEventListener("click", async () => {
      const msg = document.getElementById("cxSalesMsg022F");
      try {
        if (msg) msg.textContent = "Guardando configuración...";
        const occupation = document.getElementById("cxSalesOccupation022F")?.value || "technology";
        const customCategories = String(document.getElementById("cxSalesCustomCategories022F")?.value || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean);
        await cxSalesApi022F("/config", {
          method: "POST",
          body: JSON.stringify({ occupation, custom_categories: customCategories })
        });
        if (msg) msg.textContent = "Configuración guardada.";
        await renderClientSalesRegisterModule022F(options);
      } catch (error) {
        if (msg) msg.textContent = error.message || "No se pudo guardar.";
      }
    });

    document.querySelector("[data-cx-sales22-apply]")?.addEventListener("click", async () => {
      await renderClientSalesRegisterModule022F({
        q: document.getElementById("cxSalesFilter022F")?.value || "",
        include_archived: document.getElementById("cxSalesArchived022F")?.value === "true",
        period_type: document.getElementById("cxSalesCutPeriod022L")?.value || periodType
      });
    });

    document.querySelectorAll("[data-cx-sales22-archive]").forEach((button) => {
      button.addEventListener("click", async () => {
        const id = button.getAttribute("data-cx-sales22-archive");
        if (!id) return;
        if (!confirm("Archivar esta venta? Saldrá de la vista principal y seguirá consultable con el buscador.")) return;
        await cxSalesApi022F(`/sales/${encodeURIComponent(id)}/archive`, {
          method: "POST",
          body: JSON.stringify({})
        });
        await renderClientSalesRegisterModule022F(options);
      });
    });

    document.querySelectorAll("[data-cx-sales22-guide-file]").forEach((input) => {
      input.addEventListener("change", async () => {
        const file = input.files && input.files[0];
        const id = input.getAttribute("data-cx-sales22-guide-file");
        if (!file || !id) return;
        const dataUrl = await cxSalesFileToDataUrl022G(file);
        await cxSalesApi022F(`/sales/${encodeURIComponent(id)}/guide`, {
          method: "POST",
          body: JSON.stringify({
            file_name: file.name || "guia_envio",
            file_type: file.type || "application/octet-stream",
            file_data: dataUrl
          })
        });
        await renderClientSalesRegisterModule022F(options);
      });
    });

    document.querySelectorAll("[data-cx-sales22-open-support]").forEach((button) => {
      button.addEventListener("click", () => cxSalesOpenFile022G(itemMap.get(button.getAttribute("data-cx-sales22-open-support"))?.support));
    });

    document.querySelectorAll("[data-cx-sales22-download-support]").forEach((button) => {
      button.addEventListener("click", () => cxSalesDownloadFile022G(itemMap.get(button.getAttribute("data-cx-sales22-download-support"))?.support, "soporte"));
    });

    document.querySelectorAll("[data-cx-sales22-open-guide]").forEach((button) => {
      button.addEventListener("click", () => cxSalesOpenFile022G(itemMap.get(button.getAttribute("data-cx-sales22-open-guide"))?.guide));
    });

    document.querySelectorAll("[data-cx-sales22-download-guide]").forEach((button) => {
      button.addEventListener("click", () => cxSalesDownloadFile022G(itemMap.get(button.getAttribute("data-cx-sales22-download-guide"))?.guide, "guia_envio"));
    });
  }

  /* CLONEXA_022G_CLIENT_SALES_PIPELINE_GUIDE_END */

  /* CLONEXA_022F_CLIENT_REGISTRO_VENTA_CONSOLIDADO_END */


document.addEventListener("click", async (event) => {
      const target = event.target;

      const miniPanelCopyBtn = target.closest("[data-minipanel-copy-link]");
      if (miniPanelCopyBtn) {
        const value = String(miniPanelCopyBtn.dataset.minipanelCopyLink || "");
        try {
          if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(value);
          } else {
            const input = document.createElement("textarea");
            input.value = value;
            input.setAttribute("readonly", "readonly");
            input.style.position = "fixed";
            input.style.opacity = "0";
            document.body.appendChild(input);
            input.select();
            document.execCommand("copy");
            input.remove();
          }
          const previous = miniPanelCopyBtn.textContent;
          miniPanelCopyBtn.textContent = "Copiado";
          setTimeout(() => { miniPanelCopyBtn.textContent = previous; }, 1400);
        } catch (error) {
          alert(value);
        }
        return;
      }

      if (target.closest("[data-minipanel-refresh]")) {
        await renderMiniPanelLinksModule019B(true);
        return;
      }

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

        if (action === "quotes:open" && cxClientHasUniversalModule021D(CX_UNIVERSAL_QUOTES_CODES_021D)) {
          await renderClientUniversalQuotesModule021D("cotizaciones");
          return;
        }

        if (action === "notes:open" && cxClientHasUniversalModule021D(CX_UNIVERSAL_NOTES_CODES_021D)) {
          await renderClientUniversalNotesModule021D("notas");
          return;
        }

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

        if (action === "payroll:open" && isClientModuleActive("payroll")) {
          await renderPayrollModule();
          return;
        }

        if (action === "production:open" && isClientModuleActive("production")) {
          await renderProductionModule();
          return;
        }

        if (action === "inventory:open" && isClientModuleActive("inventory")) {
          await renderInventoryModule();
          return;
        }

        if (action === "materials:open" && isClientModuleActive("materials")) {
          await renderMaterialsModule();
          return;
        }

        if (action === "gps:open" && isClientModuleActive("gps")) {
          await renderGpsModule();
          return;
        }

        if (action === "kpis:open" && isClientModuleActive("kpis")) {
          await renderKpisModule();
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

        if (typeof cxIsSalesRegisterCode022F === "function" && cxIsSalesRegisterCode022F(code)) {
          await renderClientSalesRegisterModule022F();
          return;
        }

        if (typeof cxIsCommercialClosingCode023K === "function" && cxIsCommercialClosingCode023K(code)) {
          await renderCommercialClosingModule023K();
          return;
        }

        if (cxIsQuotesUniversalCode021D(code)) {
          await renderClientUniversalQuotesModule021D(code);
          return;
        }

        if (cxIsNotesUniversalCode021D(code)) {
          await renderClientUniversalNotesModule021D(code);
          return;
        }

        if (typeof cxIsReferencesCode022E === "function" && cxIsReferencesCode022E(code)) {
          await renderReferencesModule022E();
          return;
        }


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

        if (code === "production") {
          await renderProductionModule();
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
          await renderKpisModule();
          return;
        }

        if (code === "sales") {
          await renderSalesModule019C();
          return;
        }

        if (cxIsMiniPanelModuleCode019B(code)) {
          await renderMiniPanelLinksModule019B();
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

      if (target.closest("[data-production-apply]") || target.closest("[data-production-refresh]")) {
        await renderProductionModule(cxProdReadFilters018E());
        return;
      }

      if (target.closest("[data-production-export]")) {
        const filters = cxProdReadFilters018E();
        const a = document.createElement("a");
        a.href = cxProdDownloadUrl018E(filters);
        a.download = `clonexa_production_${state.companyId || "company"}.csv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
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
        try {
          await exportInventoryCsv();
        } catch (error) {
          showInventoryNotice(error.message || "No se pudo exportar CSV.", "error");
        }
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
    return n.toLocaleString("es", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
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
        ["total_nomina", "Total nómina"],
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
    if (["gross_amount", "discount_amount", "net_amount", "total_nomina"].includes(key)) return fmtMoney(row[key]);
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
    window.__cxReportsActiveTab = activeTab;

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
      await renderReports(filters, window.__cxReportsActiveTab || "employee_summary");
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
    await renderReports(reportsReadFilters(), window.__cxReportsActiveTab || "employee_summary");
  });
})();
/* CX_REPORTS_016B_END */

/* CX_017I_PAYROLL_SETTINGS_FINAL_START */
(function () {
  "use strict";

  if (window.__cx017iPayrollSettingsFinalLoaded) return;
  window.__cx017iPayrollSettingsFinalLoaded = true;

  const API = "/api/v1";
  const DEFAULT_ORDINARY_HOURS = 48;
  const CARD_SELECTOR = "#cxTenantPayrollSettingsCard,[data-cx-payroll-settings-card],.cx-tenant-payroll-settings-card";

  const DICT = {
    es: {
      eyebrow: "NÃ³mina",
      title: "ConfiguraciÃ³n de nÃ³mina",
      description: "Hasta este total semanal se calcula como hora ordinaria. A partir de ese total se calcula como hora extra. Las pausas no cuentan.",
      label: "Total de horas ordinarias semanales",
      save: "Guardar regla de nÃ³mina",
      saving: "Guardando...",
      saved: "Regla guardada para esta empresa.",
      invalid: "Ingresa un total vÃ¡lido entre 1 y 168 horas.",
      error: "No se pudo guardar.",
      example: "Ejemplo: 40, 48 o 49 segÃºn la legislaciÃ³n/configuraciÃ³n de esta empresa."
    },
    en: {
      eyebrow: "Payroll",
      title: "Payroll settings",
      description: "Up to this weekly total is calculated as ordinary time. After this total, time is calculated as overtime. Breaks do not count.",
      label: "Weekly ordinary hours",
      save: "Save payroll rule",
      saving: "Saving...",
      saved: "Rule saved for this company.",
      invalid: "Enter a valid total between 1 and 168 hours.",
      error: "Could not save.",
      example: "Example: 40, 48 or 49 depending on this company configuration."
    },
    fr: {
      eyebrow: "Paie",
      title: "ParamÃ¨tres de paie",
      description: "Jusquâ€™Ã  ce total hebdomadaire, le temps est calculÃ© comme heures ordinaires. Au-delÃ , il est calculÃ© comme heures supplÃ©mentaires. Les pauses ne comptent pas.",
      label: "Heures ordinaires hebdomadaires",
      save: "Enregistrer la rÃ¨gle de paie",
      saving: "Enregistrement...",
      saved: "RÃ¨gle enregistrÃ©e pour cette entreprise.",
      invalid: "Saisissez un total valide entre 1 et 168 heures.",
      error: "Impossible dâ€™enregistrer.",
      example: "Exemple : 40, 48 ou 49 selon la configuration de cette entreprise."
    },
    pt: {
      eyebrow: "Folha",
      title: "ConfiguraÃ§Ã£o da folha",
      description: "AtÃ© este total semanal, o tempo Ã© calculado como hora ordinÃ¡ria. ApÃ³s esse total, Ã© calculado como hora extra. Pausas nÃ£o contam.",
      label: "Horas ordinÃ¡rias semanais",
      save: "Salvar regra da folha",
      saving: "Salvando...",
      saved: "Regra salva para esta empresa.",
      invalid: "Insira um total vÃ¡lido entre 1 e 168 horas.",
      error: "NÃ£o foi possÃ­vel salvar.",
      example: "Exemplo: 40, 48 ou 49 conforme a configuraÃ§Ã£o desta empresa."
    }
  };

  let settingsCache = null;
  let settingsCacheAt = 0;
  let settingsPromise = null;

  function cxCompanyId() {
    try {
      return new URLSearchParams(window.location.search).get("company_id") || "";
    } catch (error) {
      return "";
    }
  }

  function cxText(value) {
    return String(value ?? "");
  }

  function cxEscape(value) {
    return cxText(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function cxNorm(value) {
    return cxText(value)
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/\s+/g, " ")
      .trim();
  }

  function cxLang(settings) {
    const candidates = [
      settings && settings.language,
      window.CLONEXA_CLIENT_SETTINGS && window.CLONEXA_CLIENT_SETTINGS.language,
      window.clonexaClientSettings && window.clonexaClientSettings.language,
      document.documentElement.getAttribute("lang")
    ];

    for (const candidate of candidates) {
      const code = cxText(candidate).trim().toLowerCase().slice(0, 2);
      if (DICT[code]) return code;
    }

    return "es";
  }

  function cxT(settings, key) {
    const lang = cxLang(settings);
    return (DICT[lang] && DICT[lang][key]) || DICT.es[key] || key;
  }

  function cxOrdinaryHours(settings) {
    const raw =
      settings?.payroll_regular_hours_limit ??
      settings?.payroll?.ordinary_hours_limit ??
      settings?.client_settings?.payroll?.ordinary_hours_limit ??
      settings?.client_settings?.payroll_regular_hours_limit ??
      DEFAULT_ORDINARY_HOURS;

    const value = Number(raw);
    return Number.isFinite(value) && value > 0 && value <= 168 ? value : DEFAULT_ORDINARY_HOURS;
  }

  async function cxFetchSettings(force = false) {
    const now = Date.now();

    if (!force && settingsCache && now - settingsCacheAt < 5000) {
      return settingsCache;
    }

    if (!force && settingsPromise) {
      return settingsPromise;
    }

    const companyId = cxCompanyId();
    if (!companyId) return {};

    settingsPromise = fetch(`${API}/companies/${encodeURIComponent(companyId)}/client-settings`, {
      headers: { "Accept": "application/json" }
    })
      .then(async (response) => {
        if (!response.ok) return {};
        return response.json();
      })
      .then((settings) => {
        settingsCache = settings || {};
        settingsCacheAt = Date.now();
        window.CLONEXA_CLIENT_SETTINGS = settingsCache;
        return settingsCache;
      })
      .finally(() => {
        settingsPromise = null;
      });

    return settingsPromise;
  }

  async function cxSavePayrollHours(value) {
    const companyId = cxCompanyId();
    if (!companyId) throw new Error("company_id no disponible.");

    const hours = Number(value);
    if (!Number.isFinite(hours) || hours <= 0 || hours > 168) {
      const settings = settingsCache || {};
      throw new Error(cxT(settings, "invalid"));
    }

    const response = await fetch(`${API}/companies/${encodeURIComponent(companyId)}/client-settings`, {
      method: "PUT",
      headers: {
        "Accept": "application/json",
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        payroll_regular_hours_limit: hours,
        payroll: { ordinary_hours_limit: hours }
      })
    });

    if (!response.ok) {
      const text = await response.text().catch(() => "");
      throw new Error(text || `settings_save_failed_${response.status}`);
    }

    const saved = await response.json();
    settingsCache = saved || {};
    settingsCacheAt = Date.now();
    window.CLONEXA_CLIENT_SETTINGS = settingsCache;
    return settingsCache;
  }

  function cxFindSettingsModal() {
    const selectors = [
      "#clx-account-modal",
      "#cx-account-modal",
      ".clx-account-modal",
      ".cx-account-modal",
      "[role='dialog']",
      ".modal",
      ".settings-modal"
    ];

    const preferred = [];
    selectors.forEach((selector) => {
      document.querySelectorAll(selector).forEach((element) => preferred.push(element));
    });

    const candidates = preferred.length ? preferred : Array.from(document.body.querySelectorAll("section, article, div"));
    let best = null;
    let bestScore = -1;

    for (const element of candidates) {
      if (!element || element.id === "app") continue;

      const style = window.getComputedStyle(element);
      if (style.display === "none" || style.visibility === "hidden") continue;

      const rect = element.getBoundingClientRect();
      if (rect.width < 280 || rect.height < 180) continue;

      const text = cxNorm(element.innerText || "");
      if (!text) continue;

      let score = 0;
      if (element.id === "clx-account-modal" || element.id === "cx-account-modal") score += 20;
      if (text.includes("settings") || text.includes("ajustes") || text.includes("configuracion") || text.includes("reglages") || text.includes("parametros")) score += 6;
      if (text.includes("panel preferences") || text.includes("preferencias del panel") || text.includes("preferencias") || text.includes("currency") || text.includes("moneda")) score += 6;
      if (text.includes("change password") || text.includes("cambiar contrasena") || text.includes("changer le mot de passe") || text.includes("alterar senha")) score += 4;
      if (text.includes("log out") || text.includes("cerrar sesion") || text.includes("session") || text.includes("sessao")) score += 3;

      if (score > bestScore) {
        bestScore = score;
        best = element;
      }
    }

    return bestScore >= 7 ? best : null;
  }

  function cxFindPreferencesCard(modal) {
    const nodes = Array.from(modal.querySelectorAll("section, article, div, form"));
    let best = null;
    let bestScore = -1;

    for (const node of nodes) {
      if (node.matches(CARD_SELECTOR) || node.querySelector(CARD_SELECTOR)) continue;

      const text = cxNorm(node.innerText || "");
      if (!text) continue;

      let score = 0;
      if (text.includes("panel preferences") || text.includes("preferencias del panel")) score += 8;
      if (text.includes("language") || text.includes("idioma") || text.includes("langue") || text.includes("idioma")) score += 3;
      if (text.includes("currency") || text.includes("moneda") || text.includes("devise") || text.includes("moeda")) score += 3;
      if (text.includes("time zone") || text.includes("zona horaria") || text.includes("fuseau horaire") || text.includes("fuso horario")) score += 2;

      if (score > bestScore) {
        bestScore = score;
        best = node;
      }
    }

    return bestScore >= 7 ? best : null;
  }

  function cxPayrollCardHtml(settings) {
    const hours = cxOrdinaryHours(settings);
    const lang = cxLang(settings);

    return `
      <section
        id="cxTenantPayrollSettingsCard"
        data-cx-payroll-settings-card="1"
        data-cx-card-lang="${cxEscape(lang)}"
        data-cx-hours="${cxEscape(hours)}"
        class="client-panel cx-tenant-payroll-settings-card"
        style="margin-top:16px"
      >
        <div class="client-eyebrow">${cxEscape(cxT(settings, "eyebrow"))}</div>
        <h2>${cxEscape(cxT(settings, "title"))}</h2>
        <p class="client-muted">${cxEscape(cxT(settings, "description"))}</p>

        <label class="cx-tenant-payroll-label" style="display:block;margin-top:14px">
          <span style="display:block;font-size:12px;font-weight:1000;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px">
            ${cxEscape(cxT(settings, "label"))}
          </span>
          <input
            id="cxTenantOrdinaryHoursInput"
            type="number"
            min="1"
            max="168"
            step="0.25"
            value="${cxEscape(hours)}"
            style="width:100%;border:1px solid rgba(255,255,255,.16);background:rgba(0,0,0,.26);color:inherit;border-radius:16px;padding:14px 16px;font-weight:900;outline:none"
          >
        </label>

        <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:14px">
          <button class="client-btn" type="button" data-cx-save-payroll-settings>${cxEscape(cxT(settings, "save"))}</button>
          <span class="client-muted" data-cx-payroll-settings-status>${cxEscape(cxT(settings, "example"))}</span>
        </div>
      </section>
    `;
  }

  function cxCleanDuplicateCards(modal) {
    const cards = Array.from(document.querySelectorAll(CARD_SELECTOR));
    let first = null;

    cards.forEach((card) => {
      if (!first && modal.contains(card)) {
        first = card;
      } else {
        card.remove();
      }
    });

    return first;
  }

  async function cxMountPayrollSettingsCard(force = false) {
    const modal = cxFindSettingsModal();
    if (!modal) return false;

    const preferencesCard = cxFindPreferencesCard(modal);
    if (!preferencesCard) return false;

    const settings = await cxFetchSettings(force);
    const lang = cxLang(settings);
    const hours = cxOrdinaryHours(settings);
    const existing = cxCleanDuplicateCards(modal);

    if (
      existing &&
      existing.getAttribute("data-cx-card-lang") === lang &&
      Number(existing.getAttribute("data-cx-hours")) === Number(hours)
    ) {
      return true;
    }

    if (existing) {
      existing.outerHTML = cxPayrollCardHtml(settings);
    } else {
      preferencesCard.insertAdjacentHTML("afterend", cxPayrollCardHtml(settings));
    }

    return true;
  }

  function cxInstallPayrollSettingsFinal() {
    const run = (force = false) => {
      window.clearTimeout(window.__cx017iPayrollMountTimer);
      window.__cx017iPayrollMountTimer = window.setTimeout(() => {
        cxMountPayrollSettingsCard(force).catch(() => {});
      }, 80);
    };

    document.addEventListener("click", () => {
      window.setTimeout(() => run(false), 80);
      window.setTimeout(() => run(false), 300);
      window.setTimeout(() => run(false), 900);
    }, true);

    const observer = new MutationObserver(() => run(false));
    observer.observe(document.body, { childList: true, subtree: true });

    run(true);
  }

  document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-cx-save-payroll-settings]");
    if (!button) return;

    event.preventDefault();

    const card = button.closest("#cxTenantPayrollSettingsCard");
    const input = card ? card.querySelector("#cxTenantOrdinaryHoursInput") : null;
    const status = card ? card.querySelector("[data-cx-payroll-settings-status]") : null;
    const currentSettings = settingsCache || {};

    try {
      button.disabled = true;
      if (status) status.textContent = cxT(currentSettings, "saving");

      const saved = await cxSavePayrollHours(input ? input.value : DEFAULT_ORDINARY_HOURS);
      const nextValue = cxOrdinaryHours(saved);

      if (input) input.value = nextValue;
      if (status) status.textContent = cxT(saved, "saved");

      await cxMountPayrollSettingsCard(true);
    } catch (error) {
      if (status) status.textContent = error.message || cxT(currentSettings, "error");
    } finally {
      button.disabled = false;
    }
  }, true);

  window.CLONEXA_SETTINGS_PAYROLL = {
    mount: cxMountPayrollSettingsCard,
    get: cxFetchSettings,
    savePayrollHours: cxSavePayrollHours
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", cxInstallPayrollSettingsFinal);
  } else {
    cxInstallPayrollSettingsFinal();
  }
})();
/* CX_017I_PAYROLL_SETTINGS_FINAL_END */
