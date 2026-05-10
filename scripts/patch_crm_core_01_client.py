from pathlib import Path

path = Path("app/web/client.js")
src = path.read_text(encoding="utf-8-sig")

if "CX_CRM_CORE_ADAPTERS_01_START" in src:
    print("CRM_CORE_ADAPTERS_01 already exists")
    raise SystemExit(0)

marker = "  async function renderClientModulePlaceholder(code) {"
if marker not in src:
    raise SystemExit("No encontré renderClientModulePlaceholder en client.js")

block = r'''
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

'''

src = src.replace(marker, block + "\n" + marker, 1)

src = src.replace(
'''        if (code === "crm" && isClientModuleActive("crm")) {
          await renderCrmLiveModule();
          return;
        }''',
'''        if (code === "crm" && isClientModuleActive("crm")) {
          await renderCrmCoreModule();
          return;
        }'''
)

src = src.replace(
'''        if (code === "crm" && isClientModuleActive("crm")) {
          await renderCrmModule();
          return;
        }''',
'''        if (code === "crm" && isClientModuleActive("crm")) {
          await renderCrmCoreModule();
          return;
        }'''
)

path.write_text(src, encoding="utf-8")
print("CRM_CORE_01_CLIENT_OK")
