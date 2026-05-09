from pathlib import Path

path = Path("app/web/client.js")
src = path.read_text(encoding="utf-8-sig")

if "CX_PRODUCTION_01_START" in src:
    print("PRODUCTION_01 client already applied")
    raise SystemExit(0)

marker = "  async function renderClientModulePlaceholder(code) {"
if marker not in src:
    raise SystemExit("No encontré renderClientModulePlaceholder en client.js")

block = r'''
  /* CX_PRODUCTION_01_START */
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
              ${productionClosuresTable(data?.closures_period || [])}
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
      if (moduleTrigger && isClientModuleActive("production")) {
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
  /* CX_PRODUCTION_01_END */

'''

src = src.replace(marker, block + "\n" + marker, 1)

src = src.replace(
'''        if (code === "reports" && isClientModuleActive("reports")) {
          await renderAdaptiveReportsModule();
          return;
        }

''',
'''        if (code === "reports" && isClientModuleActive("reports")) {
          await renderAdaptiveReportsModule();
          return;
        }

        if (code === "production" && isClientModuleActive("production")) {
          await renderProductionModule();
          return;
        }

''',
1
)

path.write_text(src, encoding="utf-8")
print("PRODUCTION_01_CLIENT_OK")
