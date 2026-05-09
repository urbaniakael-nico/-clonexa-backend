
(function () {
  "use strict";

  window.CLONEXA_REFERENCES_V1_BUILD = "REF_02D_CLIENT_THEME_SYNC_2026_05_09";

  const MODULE_CODES = new Set(["references", "ref"]);

  const I18N = {
    es: {
      eyebrow: "MÓDULO REFERENCIAS",
      title: "Referencias",
      subtitle: "Administra referencias, tallas, cantidad inicial y disponibilidad para el bot.",
      search: "Buscar referencia o talla...",
      from: "Desde",
      to: "Hasta",
      botFilter: "Bot",
      all: "Todas",
      activeBot: "Activas en bot",
      inactiveBot: "Ocultas del bot",
      refresh: "Actualizar",
      add: "Agregar referencia",
      save: "Guardar cambios",
      export: "Exportar CSV",
      back: "Volver",
      name: "Nombre referencia",
      size: "Talla",
      initial: "Cantidad inicial",
      activation: "Fecha activación",
      botActive: "Bot activo",
      actions: "Acciones",
      activate: "Activar bot",
      deactivate: "Desactivar bot",
      cancel: "Cancelar",
      create: "Crear",
      totalRefs: "Referencias",
      activeRefs: "Activas en bot",
      initialTotal: "Cantidad inicial",
      pendingTotal: "Pendiente",
      progress: "Avance",
      finished: "Terminadas",
      noRows: "Sin referencias para este filtro.",
      loading: "Cargando referencias...",
      saved: "Cambios guardados.",
      created: "Referencia creada.",
      errorLoad: "No se pudieron cargar referencias.",
      errorSave: "No se pudieron guardar cambios.",
      errorCreate: "No se pudo crear la referencia.",
      required: "Nombre, talla y cantidad inicial son requeridos.",
      addTitle: "Nueva referencia",
      botOn: "Visible en bot",
      botOff: "Oculta del bot"
    },
    en: {
      eyebrow: "REFERENCES MODULE",
      title: "References",
      subtitle: "Manage references, sizes, initial quantity and bot availability.",
      search: "Search reference or size...",
      from: "From",
      to: "To",
      botFilter: "Bot",
      all: "All",
      activeBot: "Active in bot",
      inactiveBot: "Hidden from bot",
      refresh: "Refresh",
      add: "Add reference",
      save: "Save changes",
      export: "Export CSV",
      back: "Back",
      name: "Reference name",
      size: "Size",
      initial: "Initial quantity",
      activation: "Activation date",
      botActive: "Bot active",
      actions: "Actions",
      activate: "Activate bot",
      deactivate: "Deactivate bot",
      cancel: "Cancel",
      create: "Create",
      totalRefs: "References",
      activeRefs: "Active in bot",
      initialTotal: "Initial quantity",
      pendingTotal: "Pending",
      progress: "Progress",
      finished: "Finished",
      noRows: "No references for this filter.",
      loading: "Loading references...",
      saved: "Changes saved.",
      created: "Reference created.",
      errorLoad: "Could not load references.",
      errorSave: "Could not save changes.",
      errorCreate: "Could not create reference.",
      required: "Name, size and initial quantity are required.",
      addTitle: "New reference",
      botOn: "Visible in bot",
      botOff: "Hidden from bot"
    },
    fr: {
      eyebrow: "MODULE RÉFÉRENCES",
      title: "Références",
      subtitle: "Gérez les références, tailles, quantité initiale et disponibilité dans le bot.",
      search: "Rechercher référence ou taille...",
      from: "Depuis",
      to: "Jusqu’à",
      botFilter: "Bot",
      all: "Toutes",
      activeBot: "Actives dans le bot",
      inactiveBot: "Masquées du bot",
      refresh: "Actualiser",
      add: "Ajouter référence",
      save: "Enregistrer",
      export: "Exporter CSV",
      back: "Retour",
      name: "Nom référence",
      size: "Taille",
      initial: "Quantité initiale",
      activation: "Date d’activation",
      botActive: "Bot actif",
      actions: "Actions",
      activate: "Activer bot",
      deactivate: "Désactiver bot",
      cancel: "Annuler",
      create: "Créer",
      totalRefs: "Références",
      activeRefs: "Actives dans le bot",
      initialTotal: "Quantité initiale",
      pendingTotal: "Restant",
      progress: "Avancement",
      finished: "Terminées",
      noRows: "Aucune référence pour ce filtre.",
      loading: "Chargement des références...",
      saved: "Modifications enregistrées.",
      created: "Référence créée.",
      errorLoad: "Impossible de charger les références.",
      errorSave: "Impossible d’enregistrer.",
      errorCreate: "Impossible de créer la référence.",
      required: "Nom, taille et quantité initiale sont obligatoires.",
      addTitle: "Nouvelle référence",
      botOn: "Visible dans le bot",
      botOff: "Masquée du bot"
    }
  };

  const state = {
    mounted: false,
    root: null,
    companyId: "",
    items: [],
    summary: null,
    dirty: new Map(),
    loading: false,
    message: "",
    error: "",
    showAdd: false,
    filters: {
      q: "",
      date_from: "",
      date_to: "",
      bot_active: ""
    }
  };

  function getLanguage() {
    try {
      if (typeof window.CLX_GET_LANGUAGE === "function") {
        const lang = String(window.CLX_GET_LANGUAGE() || "").toLowerCase();
        if (lang.startsWith("es")) return "es";
        if (lang.startsWith("fr")) return "fr";
        if (lang.startsWith("en")) return "en";
      }
    } catch (_) {}

    const keys = [
      "clonexa_language",
      "CLONEXA_LANGUAGE",
      "clx_language",
      "CLX_LANGUAGE",
      "client_language",
      "language"
    ];

    for (const key of keys) {
      const value = String(localStorage.getItem(key) || "").toLowerCase();
      if (value.startsWith("es")) return "es";
      if (value.startsWith("fr")) return "fr";
      if (value.startsWith("en")) return "en";
    }

    try {
      const raw = localStorage.getItem("clonexa_core_settings") || localStorage.getItem("CLX_CORE_SETTINGS");
      if (raw) {
        const parsed = JSON.parse(raw);
        const lang = String(parsed.language || parsed.lang || "").toLowerCase();
        if (lang.startsWith("es")) return "es";
        if (lang.startsWith("fr")) return "fr";
        if (lang.startsWith("en")) return "en";
      }
    } catch (_) {}

    const htmlLang = String(document.documentElement.lang || navigator.language || "es").toLowerCase();
    if (htmlLang.startsWith("fr")) return "fr";
    if (htmlLang.startsWith("en")) return "en";
    return "es";
  }

  function t(key) {
    const lang = getLanguage();
    return (I18N[lang] && I18N[lang][key]) || I18N.es[key] || key;
  }

  function firstColor(values, fallback) {
    for (const value of values) {
      const raw = String(value || "").trim();
      if (!raw) continue;
      if (/^#([0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/i.test(raw)) return raw;
      if (/^rgb\(/i.test(raw) || /^rgba\(/i.test(raw) || /^hsl\(/i.test(raw)) return raw;
    }
    return fallback;
  }

  function readJsonStorage(keys) {
    for (const key of keys) {
      try {
        const raw = localStorage.getItem(key);
        if (!raw) continue;
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === "object") return parsed;
      } catch (_) {}
    }
    return {};
  }

  function deepFindColor(obj, names) {
    if (!obj || typeof obj !== "object") return "";
    const wanted = new Set(names.map((x) => String(x).toLowerCase()));

    for (const [key, value] of Object.entries(obj)) {
      const k = String(key).toLowerCase();

      if (wanted.has(k) && typeof value === "string") return value;

      if (value && typeof value === "object") {
        const found = deepFindColor(value, names);
        if (found) return found;
      }
    }

    return "";
  }

  function detectTheme() {
    const rootStyle = getComputedStyle(document.documentElement);
    const bodyStyle = getComputedStyle(document.body);

    const stored = readJsonStorage([
      "clonexa_company",
      "clonexa_current_company",
      "clonexa_company_settings",
      "clonexa_theme",
      "CLONEXA_COMPANY",
      "CLONEXA_THEME",
      "clonexa_core_settings",
      "CLX_CORE_SETTINGS"
    ]);

    const primary = firstColor([
      rootStyle.getPropertyValue("--clx-primary"),
      rootStyle.getPropertyValue("--clx-brand-primary"),
      rootStyle.getPropertyValue("--clx-company-primary"),
      rootStyle.getPropertyValue("--tenant-primary"),
      rootStyle.getPropertyValue("--brand-primary"),
      rootStyle.getPropertyValue("--primary-color"),
      rootStyle.getPropertyValue("--accent-color"),
      bodyStyle.getPropertyValue("--clx-primary"),
      bodyStyle.getPropertyValue("--clx-brand-primary"),
      bodyStyle.getPropertyValue("--tenant-primary"),
      deepFindColor(stored, [
        "primary",
        "primaryColor",
        "primary_color",
        "brandColor",
        "brand_color",
        "accent",
        "accentColor",
        "accent_color"
      ])
    ], "var(--ref-primary)");

    const secondary = firstColor([
      rootStyle.getPropertyValue("--clx-secondary"),
      rootStyle.getPropertyValue("--clx-brand-secondary"),
      rootStyle.getPropertyValue("--clx-company-secondary"),
      rootStyle.getPropertyValue("--tenant-secondary"),
      rootStyle.getPropertyValue("--brand-secondary"),
      rootStyle.getPropertyValue("--secondary-color"),
      bodyStyle.getPropertyValue("--clx-secondary"),
      bodyStyle.getPropertyValue("--tenant-secondary"),
      deepFindColor(stored, [
        "secondary",
        "secondaryColor",
        "secondary_color",
        "brandSecondary",
        "brand_secondary"
      ])
    ], "var(--ref-secondary)");

    const surface = firstColor([
      rootStyle.getPropertyValue("--clx-surface"),
      rootStyle.getPropertyValue("--clx-card"),
      rootStyle.getPropertyValue("--surface-color"),
      rootStyle.getPropertyValue("--card-color"),
      bodyStyle.getPropertyValue("--clx-surface"),
      deepFindColor(stored, [
        "surface",
        "surfaceColor",
        "surface_color",
        "card",
        "cardColor",
        "card_color"
      ])
    ], "rgba(10,14,25,.94)");

    return { primary, secondary, surface };
  }

  function applyTheme() {
    if (!state.root) return;

    const theme = detectTheme();

    state.root.style.setProperty("--ref-primary", theme.primary);
    state.root.style.setProperty("--ref-secondary", theme.secondary);
    state.root.style.setProperty("--ref-surface", theme.surface);
    state.root.style.setProperty("--ref-primary-soft", `color-mix(in srgb, ${theme.primary} 38%, transparent)`);
    state.root.style.setProperty("--ref-secondary-soft", `color-mix(in srgb, ${theme.secondary} 42%, transparent)`);
    state.root.style.setProperty("--ref-primary-border", `color-mix(in srgb, ${theme.primary} 70%, white 10%)`);
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function getCompanyId() {
    const params = new URLSearchParams(window.location.search);
    return (
      params.get("company_id") ||
      params.get("companyId") ||
      document.body.getAttribute("data-company-id") ||
      state.companyId ||
      ""
    );
  }

  function apiBase() {
    return `/api/v1/references-v1/companies/${encodeURIComponent(state.companyId)}`;
  }

  async function apiJson(url, options) {
    const response = await fetch(url, {
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        ...(options && options.headers ? options.headers : {})
      },
      ...(options || {})
    });

    const text = await response.text();
    let data = null;

    try {
      data = text ? JSON.parse(text) : null;
    } catch (_) {
      data = { detail: text };
    }

    if (!response.ok) {
      const detail = data && (data.detail || data.message) ? (data.detail || data.message) : `HTTP ${response.status}`;
      throw new Error(detail);
    }

    return data;
  }

  function injectStyles() {
    if (document.getElementById("clx-references-v1-styles")) return;

    const style = document.createElement("style");
    style.id = "clx-references-v1-styles";
    style.textContent = `
      .clx-ref-page{width:100%;min-height:100vh;padding:28px;color:#fff;font-family:inherit}
      .clx-ref-hero{border:1px solid rgba(255,255,255,.14);border-radius:28px;padding:28px;background:linear-gradient(135deg,rgba(8,13,24,.96),var(--ref-primary-soft));box-shadow:0 24px 70px rgba(0,0,0,.25);margin-bottom:20px}
      .clx-ref-eyebrow{letter-spacing:.34em;color:var(--ref-primary);font-weight:900;font-size:13px;text-transform:uppercase;margin-bottom:10px}
      .clx-ref-title{font-size:clamp(44px,6vw,82px);line-height:.9;font-weight:950;margin:0 0 14px}
      .clx-ref-subtitle{color:rgba(255,255,255,.72);font-size:16px;max-width:980px}
      .clx-ref-actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:22px}
      .clx-ref-btn{border:0;border-radius:18px;padding:13px 18px;background:linear-gradient(135deg,var(--ref-primary),var(--ref-secondary));color:#080912;font-weight:900;cursor:pointer;box-shadow:0 14px 28px rgba(0,0,0,.25)}
      .clx-ref-btn.secondary{background:rgba(255,255,255,.11);color:#fff;border:1px solid rgba(255,255,255,.12)}
      .clx-ref-btn.danger{background:color-mix(in srgb, var(--ref-primary) 20%, transparent);color:#fff;border:1px solid color-mix(in srgb, var(--ref-primary) 55%, transparent)}
      .clx-ref-card{border:1px solid rgba(255,255,255,.12);border-radius:26px;padding:22px;background:linear-gradient(135deg,var(--ref-surface),var(--ref-secondary-soft));margin-bottom:18px}
      .clx-ref-grid{display:grid;grid-template-columns:repeat(5,minmax(140px,1fr));gap:12px;margin-top:16px}
      .clx-ref-kpi{border:1px solid rgba(255,255,255,.12);border-radius:20px;padding:16px;background:rgba(255,255,255,.08)}
      .clx-ref-kpi label{display:block;color:rgba(255,255,255,.66);font-size:12px;font-weight:900;margin-bottom:8px}
      .clx-ref-kpi strong{font-size:30px}
      .clx-ref-filters{display:grid;grid-template-columns:2fr 150px 150px 180px auto auto;gap:10px;align-items:end}
      .clx-ref-field label{display:block;font-size:11px;font-weight:900;letter-spacing:.08em;color:rgba(255,255,255,.66);text-transform:uppercase;margin-bottom:6px}
      .clx-ref-input,.clx-ref-select{width:100%;height:44px;border-radius:15px;border:1px solid rgba(255,255,255,.13);background:rgba(0,0,0,.32);color:#fff;padding:0 13px;font-weight:800;outline:none}
      .clx-ref-add{display:grid;grid-template-columns:2fr 120px 150px 160px auto auto;gap:10px;align-items:end;margin-top:16px;padding-top:16px;border-top:1px solid rgba(255,255,255,.1)}
      .clx-ref-table-wrap{overflow:auto;border-radius:22px;border:1px solid rgba(255,255,255,.12)}
      .clx-ref-table{width:100%;border-collapse:collapse;min-width:980px}
      .clx-ref-table th{background:rgba(80,95,135,.32);text-align:left;padding:14px;font-size:12px;letter-spacing:.06em;text-transform:uppercase}
      .clx-ref-table td{padding:10px 12px;border-top:1px solid rgba(255,255,255,.07);vertical-align:middle}
      .clx-ref-row-input{width:100%;height:38px;border-radius:12px;border:1px solid rgba(255,255,255,.12);background:rgba(0,0,0,.28);color:#fff;padding:0 10px;font-weight:800}
      .clx-ref-pill{display:inline-flex;align-items:center;border-radius:999px;padding:7px 10px;font-size:12px;font-weight:900;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.09)}
      .clx-ref-pill.on{background:rgba(30,220,140,.22);border-color:rgba(30,220,140,.5)}
      .clx-ref-pill.off{background:rgba(255,255,255,.07)}
      .clx-ref-msg{margin:12px 0;font-weight:900}
      .clx-ref-msg.error{color:#ff7aa9}
      .clx-ref-msg.ok{color:#8cffcc}
      @media(max-width:1100px){.clx-ref-grid{grid-template-columns:repeat(2,1fr)}.clx-ref-filters,.clx-ref-add{grid-template-columns:1fr 1fr}.clx-ref-title{font-size:48px}}
    `;
    document.head.appendChild(style);
  }

  function isReferencesScreen() {
    // Anti-bloqueo: NO leer document.body.innerText.
    // Solo detectamos pantalla por H1/H2 exacto del placeholder.
    const headers = Array.from(document.querySelectorAll("h1,h2"));
    return headers.some((node) => {
      const value = (node.textContent || "").trim().toLowerCase();
      return value === "references" || value === "referencias" || value === "références";
    });
  }

  function findMountTarget() {
    const headers = Array.from(document.querySelectorAll("h1,h2"));
    const header = headers.find((node) => {
      const value = (node.textContent || "").trim().toLowerCase();
      return value === "references" || value === "referencias" || value === "références";
    });

    if (!header) return null;

    let node = header.parentElement;

    for (let i = 0; i < 10 && node && node !== document.body; i += 1) {
      const tag = (node.tagName || "").toLowerCase();
      const id = (node.id || "").toLowerCase();
      const klass = String(node.className || "").toLowerCase();
      const text = (node.textContent || "").toLowerCase();

      const forbidden =
        tag === "body" ||
        tag === "html" ||
        tag === "main" ||
        id === "app" ||
        klass.includes("client-shell") ||
        text.includes("tenant activo") ||
        text.includes("active tenant") ||
        text.includes("cerrar sesión") ||
        text.includes("log out") ||
        text.includes("ajustes") ||
        text.includes("settings");

      const hasReferenceTitle =
        text.includes("references") ||
        text.includes("referencias") ||
        text.includes("références");

      const hasPlaceholder =
        text.includes("módulo activo") ||
        text.includes("modulo activo") ||
        text.includes("module active") ||
        text.includes("este módulo está asignado") ||
        text.includes("este modulo esta asignado") ||
        text.includes("this module is assigned");

      const widthOk = (node.offsetWidth || 0) > 420;

      if (!forbidden && hasReferenceTitle && hasPlaceholder && widthOk) {
        return node;
      }

      node = node.parentElement;
    }

    // Seguridad: si no encontramos contenedor limpio, no montamos.
    return null;
  }

  function render() {
    if (!state.root) return;
    applyTheme();

    const summary = state.summary || {};
    const items = state.items || [];

    state.root.innerHTML = `
      <div class="clx-ref-page">
        <section class="clx-ref-hero">
          <div class="clx-ref-eyebrow">${t("eyebrow")}</div>
          <h1 class="clx-ref-title">${t("title")}</h1>
          <div class="clx-ref-subtitle">${t("subtitle")}</div>
          <div class="clx-ref-actions">
            <button class="clx-ref-btn" data-ref-action="refresh">${t("refresh")}</button>
            <button class="clx-ref-btn" data-ref-action="toggle-add">${t("add")}</button>
            <button class="clx-ref-btn" data-ref-action="save">${t("save")}</button>
            <button class="clx-ref-btn secondary" data-ref-action="export">${t("export")}</button>
            <button class="clx-ref-btn secondary" data-ref-action="back">${t("back")}</button>
          </div>
        </section>

        <section class="clx-ref-card">
          <div class="clx-ref-grid">
            <div class="clx-ref-kpi"><label>${t("totalRefs")}</label><strong>${summary.references_total || 0}</strong></div>
            <div class="clx-ref-kpi"><label>${t("activeRefs")}</label><strong>${summary.bot_active_total || 0}</strong></div>
            <div class="clx-ref-kpi"><label>${t("initialTotal")}</label><strong>${summary.initial_quantity_total || 0}</strong></div>
            <div class="clx-ref-kpi"><label>${t("pendingTotal")}</label><strong>${summary.pending_quantity_total || 0}</strong></div>
            <div class="clx-ref-kpi"><label>${t("progress")}</label><strong>${summary.progress_percent || 0}%</strong></div>
          </div>
        </section>

        <section class="clx-ref-card">
          <div class="clx-ref-filters">
            <div class="clx-ref-field">
              <label>${t("search")}</label>
              <input class="clx-ref-input" data-ref-filter="q" value="${escapeHtml(state.filters.q)}" placeholder="${t("search")}">
            </div>
            <div class="clx-ref-field">
              <label>${t("from")}</label>
              <input type="date" class="clx-ref-input" data-ref-filter="date_from" value="${escapeHtml(state.filters.date_from)}">
            </div>
            <div class="clx-ref-field">
              <label>${t("to")}</label>
              <input type="date" class="clx-ref-input" data-ref-filter="date_to" value="${escapeHtml(state.filters.date_to)}">
            </div>
            <div class="clx-ref-field">
              <label>${t("botFilter")}</label>
              <select class="clx-ref-select" data-ref-filter="bot_active">
                <option value="" ${state.filters.bot_active === "" ? "selected" : ""}>${t("all")}</option>
                <option value="true" ${state.filters.bot_active === "true" ? "selected" : ""}>${t("activeBot")}</option>
                <option value="false" ${state.filters.bot_active === "false" ? "selected" : ""}>${t("inactiveBot")}</option>
              </select>
            </div>
            <button class="clx-ref-btn" data-ref-action="refresh">${t("refresh")}</button>
            <button class="clx-ref-btn secondary" data-ref-action="export">${t("export")}</button>
          </div>

          ${state.showAdd ? `
            <div class="clx-ref-add">
              <div class="clx-ref-field">
                <label>${t("name")}</label>
                <input class="clx-ref-input" data-ref-new="name">
              </div>
              <div class="clx-ref-field">
                <label>${t("size")}</label>
                <input class="clx-ref-input" data-ref-new="size">
              </div>
              <div class="clx-ref-field">
                <label>${t("initial")}</label>
                <input type="number" min="0" class="clx-ref-input" data-ref-new="initial_quantity">
              </div>
              <div class="clx-ref-field">
                <label>${t("botActive")}</label>
                <select class="clx-ref-select" data-ref-new="bot_active">
                  <option value="true">${t("botOn")}</option>
                  <option value="false">${t("botOff")}</option>
                </select>
              </div>
              <button class="clx-ref-btn" data-ref-action="create">${t("create")}</button>
              <button class="clx-ref-btn secondary" data-ref-action="toggle-add">${t("cancel")}</button>
            </div>
          ` : ""}

          ${state.error ? `<div class="clx-ref-msg error">${escapeHtml(state.error)}</div>` : ""}
          ${state.message ? `<div class="clx-ref-msg ok">${escapeHtml(state.message)}</div>` : ""}
        </section>

        <section class="clx-ref-card">
          <div class="clx-ref-table-wrap">
            <table class="clx-ref-table">
              <thead>
                <tr>
                  <th>${t("name")}</th>
                  <th>${t("size")}</th>
                  <th>${t("initial")}</th>
                  <th>${t("activation")}</th>
                  <th>${t("finished")}</th>
                  <th>${t("pendingTotal")}</th>
                  <th>${t("botActive")}</th>
                  <th>${t("actions")}</th>
                </tr>
              </thead>
              <tbody>
                ${items.length ? items.map(rowHtml).join("") : `
                  <tr><td colspan="8">${state.loading ? t("loading") : t("noRows")}</td></tr>
                `}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    `;
  }

  function summaryFor(item) {
    const rows = (state.summary && state.summary.by_reference_size) || [];
    return rows.find((row) => row.id === item.id) || {};
  }

  function rowHtml(item) {
    const s = summaryFor(item);
    const active = Boolean(item.bot_active);

    return `
      <tr data-ref-id="${escapeHtml(item.id)}">
        <td><input class="clx-ref-row-input" data-ref-edit="name" value="${escapeHtml(item.name)}"></td>
        <td><input class="clx-ref-row-input" data-ref-edit="size" value="${escapeHtml(item.size)}"></td>
        <td><input type="number" min="0" class="clx-ref-row-input" data-ref-edit="initial_quantity" value="${escapeHtml(item.initial_quantity)}"></td>
        <td>${escapeHtml((item.activation_date || "").split(".")[0])}</td>
        <td>${escapeHtml(s.finished_quantity || 0)}</td>
        <td>${escapeHtml(s.pending_quantity == null ? item.initial_quantity : s.pending_quantity)}</td>
        <td><span class="clx-ref-pill ${active ? "on" : "off"}">${active ? t("botOn") : t("botOff")}</span></td>
        <td>
          <button class="clx-ref-btn secondary" data-ref-action="toggle-bot" data-ref-id="${escapeHtml(item.id)}">
            ${active ? t("deactivate") : t("activate")}
          </button>
        </td>
      </tr>
    `;
  }

  function buildQuery() {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(state.filters)) {
      if (value !== "") params.set(key, value);
    }
    const q = params.toString();
    return q ? `?${q}` : "";
  }

  async function loadData() {
    if (!state.companyId) return;

    state.loading = true;
    state.error = "";
    render();

    try {
      const [list, summary] = await Promise.all([
        apiJson(`${apiBase()}${buildQuery()}`),
        apiJson(`${apiBase()}/summary`)
      ]);

      state.items = list.items || [];
      state.summary = summary || {};
      state.dirty.clear();
    } catch (error) {
      state.error = `${t("errorLoad")} ${error.message || error}`;
    } finally {
      state.loading = false;
      render();
    }
  }

  function collectRow(id) {
    const tr = state.root.querySelector(`tr[data-ref-id="${CSS.escape(id)}"]`);
    if (!tr) return null;

    const data = {};
    tr.querySelectorAll("[data-ref-edit]").forEach((input) => {
      const field = input.getAttribute("data-ref-edit");
      data[field] = field === "initial_quantity" ? Number(input.value || 0) : input.value.trim();
    });

    return data;
  }

  async function saveChanges() {
    const ids = Array.from(state.dirty.keys());

    if (!ids.length) {
      state.message = t("saved");
      state.error = "";
      render();
      return;
    }

    try {
      for (const id of ids) {
        const payload = collectRow(id);
        if (!payload) continue;

        await apiJson(`${apiBase()}/${encodeURIComponent(id)}`, {
          method: "PATCH",
          body: JSON.stringify(payload)
        });
      }

      state.message = t("saved");
      state.error = "";
      await loadData();
    } catch (error) {
      state.error = `${t("errorSave")} ${error.message || error}`;
      state.message = "";
      render();
    }
  }

  async function toggleBot(id) {
    const item = state.items.find((row) => row.id === id);
    if (!item) return;

    try {
      await apiJson(`${apiBase()}/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: item.name,
          size: item.size,
          initial_quantity: Number(item.initial_quantity || 0),
          bot_active: !item.bot_active
        })
      });

      await loadData();
    } catch (error) {
      state.error = `${t("errorSave")} ${error.message || error}`;
      render();
    }
  }

  async function createReference() {
    const name = (state.root.querySelector("[data-ref-new='name']") || {}).value || "";
    const size = (state.root.querySelector("[data-ref-new='size']") || {}).value || "";
    const initial = (state.root.querySelector("[data-ref-new='initial_quantity']") || {}).value || "";
    const bot = (state.root.querySelector("[data-ref-new='bot_active']") || {}).value || "true";

    if (!name.trim() || !size.trim() || initial === "") {
      state.error = t("required");
      state.message = "";
      render();
      return;
    }

    try {
      await apiJson(apiBase(), {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          size: size.trim(),
          initial_quantity: Number(initial || 0),
          bot_active: bot === "true"
        })
      });

      state.showAdd = false;
      state.message = t("created");
      state.error = "";
      await loadData();
    } catch (error) {
      state.error = `${t("errorCreate")} ${error.message || error}`;
      state.message = "";
      render();
    }
  }

  function exportCsv() {
    window.open(`${apiBase()}/export.csv${buildQuery()}`, "_blank", "noopener,noreferrer");
  }

  function bindEvents() {
    if (window.__CLONEXA_REFERENCES_V1_EVENTS_BOUND__) return;
    window.__CLONEXA_REFERENCES_V1_EVENTS_BOUND__ = true;

    document.addEventListener("input", (event) => {
      if (!state.root || !state.root.contains(event.target)) return;

      const filter = event.target.getAttribute("data-ref-filter");
      if (filter) {
        state.filters[filter] = event.target.value;
        clearTimeout(window.__CLX_REF_FILTER_TIMER__);
        window.__CLX_REF_FILTER_TIMER__ = setTimeout(loadData, 350);
        return;
      }

      const edit = event.target.getAttribute("data-ref-edit");
      if (edit) {
        const tr = event.target.closest("tr[data-ref-id]");
        if (tr) state.dirty.set(tr.getAttribute("data-ref-id"), true);
      }
    });

    document.addEventListener("change", (event) => {
      if (!state.root || !state.root.contains(event.target)) return;

      const filter = event.target.getAttribute("data-ref-filter");
      if (filter) {
        state.filters[filter] = event.target.value;
        loadData();
      }
    });

    document.addEventListener("click", (event) => {
      const btn = event.target.closest("[data-ref-action]");
      if (!btn || !state.root || !state.root.contains(btn)) return;

      const action = btn.getAttribute("data-ref-action");
      const id = btn.getAttribute("data-ref-id");

      if (action === "refresh") loadData();
      if (action === "toggle-add") {
        state.showAdd = !state.showAdd;
        state.error = "";
        state.message = "";
        render();
      }
      if (action === "create") createReference();
      if (action === "save") saveChanges();
      if (action === "toggle-bot") toggleBot(id);
      if (action === "export") exportCsv();
      if (action === "back") {
        const dashboard = Array.from(document.querySelectorAll("button,a")).find((node) => {
          return (node.textContent || "").trim().toLowerCase() === "dashboard";
        });
        if (dashboard) dashboard.click();
        else history.back();
      }
    });
  }

  function mount() {
    try {
      if (!isReferencesScreen()) return;

      const target = findMountTarget();

      if (!target) {
        console.warn("[CLONEXA References] Safe mount skipped: no clean module container found.");
        return;
      }

      if (target.getAttribute("data-clx-references-v1-mounted") === "1") return;

      injectStyles();

      state.companyId = getCompanyId();
      state.root = target;
      state.root.setAttribute("data-clx-references-v1-mounted", "1");

      bindEvents();
      applyTheme();
      render();
      loadData();
    } catch (error) {
      console.error("[CLONEXA References] mount failed safely:", error);
    }
  }

  window.CLONEXA_RENDER_REFERENCES_V1 = mount;

  const observer = new MutationObserver(() => {
    clearTimeout(window.__CLX_REF_MOUNT_TIMER__);
    window.__CLX_REF_MOUNT_TIMER__ = setTimeout(() => {
      if (document.body) mount();
    }, 120);
  });

  function start() {
    mount();
    if (document.body) {
      observer.observe(document.body, { childList: true, subtree: true });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
