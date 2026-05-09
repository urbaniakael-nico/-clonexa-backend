from pathlib import Path

path = Path("app/web/client.js")
src = path.read_text(encoding="utf-8-sig")

if "CX_CRM_LIVE_01_START" in src:
    print("CRM_LIVE_01 client already applied")
    raise SystemExit(0)

marker = "  async function renderClientModulePlaceholder(code) {"
if marker not in src:
    raise SystemExit("No encontré renderClientModulePlaceholder en client.js")

block = r'''
  /* CX_CRM_LIVE_01_START */
  function crmLiveParseDate(value) {
    if (!value) return null;

    const raw = String(value).trim();
    const normalized = raw.includes("T") ? raw : raw.replace(" ", "T");
    const date = new Date(normalized);

    if (Number.isNaN(date.getTime())) return null;

    return date;
  }

  function crmLiveFormatDuration(ms) {
    if (!Number.isFinite(ms) || ms < 0) ms = 0;

    const totalSeconds = Math.floor(ms / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    const hh = String(hours).padStart(2, "0");
    const mm = String(minutes).padStart(2, "0");
    const ss = String(seconds).padStart(2, "0");

    return `${hh}:${mm}:${ss}`;
  }

  function crmLiveStopTimers() {
    if (window.__cxCrmLiveRefreshInterval) {
      clearInterval(window.__cxCrmLiveRefreshInterval);
      window.__cxCrmLiveRefreshInterval = null;
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

    document.querySelectorAll("[data-crm-live-timer]").forEach((node) => {
      const startedAt = crmLiveParseDate(node.dataset.crmLiveTimer || "");
      if (!startedAt) {
        node.textContent = "00:00:00";
        return;
      }

      node.textContent = crmLiveFormatDuration(Date.now() - startedAt.getTime());
    });
  }

  function crmLiveStatusClass(status) {
    const value = String(status || "").toLowerCase();

    if (value === "working") return "Activo";
    if (value === "on_break") return "En pausa";
    if (value === "checked_out") return "Fuera de turno";

    return "Fuera de turno";
  }

  function crmLiveKpis(summary) {
    const cards = [
      ["Activos", summary?.active_now ?? 0],
      ["En pausa", summary?.on_break ?? 0],
      ["Con referencia", summary?.with_active_reference ?? 0],
      ["Producción", summary?.production_enabled ? "ON" : "OFF"],
      ["Referencias", summary?.references_enabled ? "ON" : "OFF"],
      ["Nómina", summary?.payroll_enabled ? "ON" : "OFF"],
    ];

    return `
      <div class="client-kpi-grid">
        ${cards.map(([label, value]) => `
          <div class="client-kpi">
            <span>${h(label)}</span>
            <strong>${h(value)}</strong>
          </div>
        `).join("")}
      </div>
    `;
  }

  function crmLiveEmployeeCard(row) {
    const status = crmLiveStatusClass(row.work_status);
    const statusStartedAt = row.status_started_at || "";
    const referenceStartedAt = row.reference_started_at || "";

    return `
      <article class="client-panel">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:14px">
          <div>
            <span class="client-muted">Colaborador</span>
            <h2 style="margin:6px 0 0">${h(row.employee_name || "Empleado")}</h2>
            ${row.employee_role ? `<p class="client-muted">${h(row.employee_role)}</p>` : ""}
          </div>
          <strong>${h(status)}</strong>
        </div>

        <div class="client-kpi-grid" style="margin-top:14px">
          <div class="client-kpi">
            <span>Cronómetro turno</span>
            <strong data-crm-live-timer="${h(statusStartedAt)}">${statusStartedAt ? "00:00:00" : "00:00:00"}</strong>
            <small>${h(status)}</small>
          </div>

          <div class="client-kpi">
            <span>Producción actual</span>
            <strong>${row.has_active_reference ? h(row.reference_name || "Referencia") : "SIN PRODUCCIÓN"}</strong>
            <small>${row.has_active_reference ? "Referencia activa" : "Sin referencia activa"}</small>
          </div>

          <div class="client-kpi">
            <span>Tiempo en referencia</span>
            <strong data-crm-live-timer="${h(referenceStartedAt)}">${referenceStartedAt ? "00:00:00" : "00:00:00"}</strong>
            <small>${row.has_active_reference ? "Corriendo" : "Sin producción"}</small>
          </div>
        </div>
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
                Vista viva de colaboradores, turno, pausa, referencia actual y tiempo corriendo por módulo activo.
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
              <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:16px">
                ${(snapshot?.employees || []).map(crmLiveEmployeeCard).join("") || `<div class="client-muted">Sin colaboradores activos.</div>`}
              </div>
            </section>
          </section>
        </div>
      </main>
    `;

    crmLiveUpdateTimers();

    window.__cxCrmLiveTimerInterval = setInterval(crmLiveUpdateTimers, 1000);

    window.__cxCrmLiveRefreshInterval = setInterval(async () => {
      if (!document.querySelector("[data-crm-live-root]")) {
        crmLiveStopTimers();
        return;
      }

      await renderCrmLiveModule();
    }, 15000);
  }

  if (!window.__cxCrmLive01Bound) {
    window.__cxCrmLive01Bound = true;

    document.addEventListener("click", async (event) => {
      const moduleTrigger = event.target.closest('[data-client-module="crm"]');
      if (moduleTrigger && isClientModuleActive("crm")) {
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

        if (code === "crm" && isClientModuleActive("crm")) {
          await renderCrmLiveModule();
          return;
        }

''',
1
)

path.write_text(src, encoding="utf-8")
print("CRM_LIVE_01_CLIENT_OK")
