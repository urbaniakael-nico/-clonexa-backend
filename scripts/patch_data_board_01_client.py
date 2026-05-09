from pathlib import Path
import re

path = Path("app/web/client.js")
src = path.read_text(encoding="utf-8-sig")


def replace_between(source: str, start_marker: str, end_marker: str, replacement: str) -> str:
    start = source.find(start_marker)
    end = source.find(end_marker)

    if start == -1 or end == -1 or end < start:
        raise SystemExit(f"No encontré bloque {start_marker} / {end_marker}")

    end += len(end_marker)
    return source[:start] + replacement + source[end:]


reports_block = r'''/* CX_REPORTS_ADAPTER_01_START */
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
  /* CX_REPORTS_ADAPTER_01_END */'''


kpis_block = r'''/* CX_KPIS_ADAPTER_01_START */
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
  /* CX_KPIS_ADAPTER_01_END */'''

src = replace_between(src, "/* CX_REPORTS_ADAPTER_01_START */", "/* CX_REPORTS_ADAPTER_01_END */", reports_block)
src = replace_between(src, "/* CX_KPIS_ADAPTER_01_START */", "/* CX_KPIS_ADAPTER_01_END */", kpis_block)

# Limpieza visible de módulos leídos en caso de plantillas viejas.
src = src.replace("Módulos leídos", "Fuentes de datos")
src = src.replace("Fuentes activas de esta empresa", "Fuentes usadas por el reporte")

path.write_text(src, encoding="utf-8")
print("DATA_BOARD_01_CLIENT_OK")
