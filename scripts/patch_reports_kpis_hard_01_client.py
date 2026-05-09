from pathlib import Path

path = Path("app/web/client.js")
src = path.read_text(encoding="utf-8-sig")

if "CX_KPIS_ADAPTER_01_START" in src:
    print("KPIS adapter already applied")
else:
    marker = "  async function renderClientModulePlaceholder(code) {"
    if marker not in src:
        raise SystemExit("No encontré renderClientModulePlaceholder.")

    block = r'''
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

  function adaptiveKpiCards(items, currency) {
    const rows = Array.isArray(items) ? items : [];

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
        ${adaptiveKpiCards(section?.items || [], currency)}
      </section>
    `;
  }

  async function loadAdaptiveKpisSummary() {
    const query = kpisAdapterQuery();
    const qs = new URLSearchParams({
      date_from: query.from,
      date_to: query.to,
      preset: query.preset,
    });

    return await api(`/adaptive-kpis-v1/companies/${state.companyId}/summary?${qs.toString()}`);
  }

  async function renderAdaptiveKpisModule() {
    const company = state.company || {};
    const b = normalizeBranding(state.branding || {});
    const range = kpisAdapterDefaultRange();

    let kpis = null;
    let loadError = "";

    try {
      kpis = await api(`/adaptive-kpis-v1/companies/${state.companyId}/summary?date_from=${range.from}&date_to=${range.to}&preset=7d`);
    } catch (error) {
      loadError = error.message || "No se pudieron cargar KPIs.";
      kpis = null;
    }

    const companyName = kpis?.company_name || company.name || "Empresa";
    const currency = kpis?.currency || "COP";

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
              <h1 class="client-title">KPIs operativos</h1>
              <p class="client-muted">
                Indicadores adaptativos de ${h(companyName)} calculados según los módulos activos. Moneda: ${h(currency)}.
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
              <div class="client-section-kicker">Resumen ejecutivo</div>
              <h2>${h(companyName)}</h2>
              <p class="client-muted">
                ${h(kpis?.date_from || range.from)} → ${h(kpis?.date_to || range.to)} · Moneda ${h(currency)}
              </p>
              ${adaptiveKpiCards(kpis?.items || [], currency)}
            </section>

            <section class="client-panel">
              <div class="client-section-kicker">Módulos leídos</div>
              <h2>Fuentes activas de esta empresa</h2>
              <div class="client-module-grid">
                ${(kpis?.active_modules || []).map((code) => `
                  <div class="client-service-card">
                    <span>${h(code)}</span>
                    <strong>${h(moduleLabel(code))}</strong>
                  </div>
                `).join("") || `<div class="client-muted">Sin módulos activos detectados.</div>`}
              </div>
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

  if (!window.__cxKpisAdapter01Bound) {
    window.__cxKpisAdapter01Bound = true;

    document.addEventListener("click", async (event) => {
      const generate = event.target.closest("[data-adaptive-kpis-generate]");
      if (generate) {
        event.preventDefault();
        await refreshAdaptiveKpisModule();
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

      if ((moduleCode === "kpis" || actionCode === "kpis:open") && isClientModuleActive("kpis")) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        await renderAdaptiveKpisModule();
        return;
      }

      if ((moduleCode === "reports" || actionCode === "reports:open") && isClientModuleActive("reports")) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        await renderAdaptiveReportsModule();
      }
    }, true);
  }
  /* CX_KPIS_ADAPTER_01_END */

'''

    src = src.replace(marker, block + "\n" + marker, 1)

replacements = {
    'await renderClientModulePlaceholder("kpis");': 'await renderAdaptiveKpisModule();',
    'await renderKpisModule();': 'await renderAdaptiveKpisModule();',
    'renderKpisModule();': 'renderAdaptiveKpisModule();',
    'await renderClientModulePlaceholder("reports");': 'await renderAdaptiveReportsModule();',
    'await renderReportsModule();': 'await renderAdaptiveReportsModule();',
    'renderReportsModule();': 'renderAdaptiveReportsModule();',
}

for old, new in replacements.items():
    src = src.replace(old, new)

# Limpieza de textos viejos visibles si quedaron en plantillas antiguas.
src = src.replace("VOLTAGE / OPERACIÓN VIVA", "Indicadores adaptativos")
src = src.replace("VOLTAGE", "Empresa")
src = src.replace("US$ Nómina", "Nómina")
src = src.replace("USD", "COP")

path.write_text(src, encoding="utf-8")
print("REPORTS_KPIS_HARD_01_CLIENT_OK")
