from pathlib import Path

path = Path("app/web/client.js")
src = path.read_text(encoding="utf-8-sig")

if "CX_REPORTS_ADAPTER_01_START" in src:
    print("REPORTS_ADAPTER_01 already applied")
    raise SystemExit(0)

marker = "  async function renderClientModulePlaceholder(code) {"
if marker not in src:
    raise SystemExit("No encontré renderClientModulePlaceholder en client.js")

block = r'''
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
    const from = document.querySelector("[data-adaptive-reports-from]")?.value || range.from;
    const to = document.querySelector("[data-adaptive-reports-to]")?.value || range.to;
    const preset = document.querySelector("[data-adaptive-reports-preset]")?.value || "7d";

    return { from, to, preset };
  }

  function reportsAdapterKpisHtml(items) {
    const rows = Array.isArray(items) ? items : [];

    if (!rows.length) {
      return `<div class="client-muted">Sin indicadores para el periodo.</div>`;
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

  function reportsAdapterBlockHtml(block) {
    const kpis = Array.isArray(block?.kpis) ? block.kpis : [];
    const byDay = Array.isArray(block?.by_day) ? block.by_day : [];
    const byReference = Array.isArray(block?.by_reference) ? block.by_reference : [];

    return `
      <section class="client-panel">
        <div class="client-section-kicker">${h(block?.code || "módulo")}</div>
        <h2>${h(block?.title || "Bloque")}</h2>
        <div class="client-kpi-grid">
          ${kpis.map((item) => `
            <div class="client-kpi">
              <span>${h(item.label || "Indicador")}</span>
              <strong>${h(item.value ?? 0)}</strong>
            </div>
          `).join("") || `<div class="client-muted">Sin indicadores.</div>`}
        </div>

        ${byDay.length ? `
          <div class="client-panel" style="margin-top:14px">
            <h3>Actividad por día</h3>
            ${byDay.map((item) => `
              <div style="display:grid;grid-template-columns:90px 1fr 70px;gap:12px;align-items:center;margin:8px 0">
                <strong>${h(item.label || "")}</strong>
                <div style="height:10px;border-radius:999px;background:rgba(255,255,255,.12);overflow:hidden">
                  <div style="height:100%;width:${Math.min(Number(item.value || 0) * 8, 100)}%;background:linear-gradient(90deg,rgba(0,255,180,.85),rgba(255,0,180,.85));"></div>
                </div>
                <span>${h(item.value ?? 0)}</span>
              </div>
            `).join("")}
          </div>
        ` : ""}

        ${byReference.length ? `
          <div class="client-panel" style="margin-top:14px">
            <h3>Producción por referencia</h3>
            ${byReference.map((item) => `
              <div style="display:grid;grid-template-columns:1fr 90px;gap:12px;align-items:center;margin:8px 0">
                <strong>${h(item.label || "")}</strong>
                <span>${h(item.value ?? 0)}</span>
              </div>
            `).join("")}
          </div>
        ` : ""}
      </section>
    `;
  }

  async function loadAdaptiveReportsSummary() {
    const query = reportsAdapterQuery();
    const qs = new URLSearchParams({
      date_from: query.from,
      date_to: query.to,
      preset: query.preset,
    });

    return await api(`/adaptive-reports-v1/companies/${state.companyId}/summary?${qs.toString()}`);
  }

  async function renderAdaptiveReportsModule() {
    const company = state.company || {};
    const b = normalizeBranding(state.branding || {});
    const range = reportsAdapterDefaultRange();

    let report = null;
    let loadError = "";

    try {
      report = await api(`/adaptive-reports-v1/companies/${state.companyId}/summary?date_from=${range.from}&date_to=${range.to}&preset=7d`);
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
              <h1 class="client-title">Reportes</h1>
              <p class="client-muted">
                Reporte adaptativo por módulos activos. No modifica datos; solo audita, consolida y exporta.
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
              <h2>Indicadores del periodo</h2>
              <p class="client-muted">
                ${h(report?.date_from || range.from)} → ${h(report?.date_to || range.to)}
              </p>
              ${reportsAdapterKpisHtml(report?.executive_kpis || [])}
            </section>

            <section class="client-panel">
              <div class="client-section-kicker">Módulos leídos</div>
              <h2>Fuentes activas de esta empresa</h2>
              <div class="client-module-grid">
                ${(report?.active_modules || []).map((code) => `
                  <div class="client-service-card">
                    <span>${h(code)}</span>
                    <strong>${h(moduleLabel(code))}</strong>
                  </div>
                `).join("") || `<div class="client-muted">Sin módulos activos detectados.</div>`}
              </div>
            </section>

            ${(report?.blocks || []).map(reportsAdapterBlockHtml).join("")}
          </section>
        </div>
      </main>
    `;
  }

  async function refreshAdaptiveReportsModule() {
    let report = null;
    try {
      report = await loadAdaptiveReportsSummary();
    } catch (error) {
      alert(error.message || "No se pudo generar el reporte.");
      return;
    }

    await renderAdaptiveReportsModule();

    const fromInput = document.querySelector("[data-adaptive-reports-from]");
    const toInput = document.querySelector("[data-adaptive-reports-to]");
    if (fromInput) fromInput.value = report.date_from;
    if (toInput) toInput.value = report.date_to;
  }

  function exportAdaptiveReportsCsv() {
    const query = reportsAdapterQuery();
    const qs = new URLSearchParams({
      date_from: query.from,
      date_to: query.to,
      preset: query.preset,
    });

    window.open(`${API}/adaptive-reports-v1/companies/${state.companyId}/export.csv?${qs.toString()}`, "_blank");
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

'''

src = src.replace(marker, block + "\n" + marker, 1)

src = src.replace(
    'await renderClientModulePlaceholder("reports");',
    'await renderAdaptiveReportsModule();'
)

trigger = '        const code = String(moduleTrigger.dataset.clientModule || "").trim();\n'
if trigger in src and 'code === "reports" && isClientModuleActive("reports")' not in src:
    src = src.replace(
        trigger,
        trigger + '''        if (code === "reports" && isClientModuleActive("reports")) {
          await renderAdaptiveReportsModule();
          return;
        }

''',
        1
    )

src = src.replace("Modulo activo", "Módulo activo")
src = src.replace("Este modulo", "Este módulo")
src = src.replace("construira", "construirá")
src = src.replace("operacion", "operación")
src = src.replace("tecnicos", "técnicos")
src = src.replace("nomina", "nómina")

path.write_text(src, encoding="utf-8")
print("REPORTS_ADAPTER_01_CLIENT_OK")
