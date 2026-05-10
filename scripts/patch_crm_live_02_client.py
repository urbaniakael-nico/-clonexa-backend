from pathlib import Path

path = Path("app/web/client.js")
src = path.read_text(encoding="utf-8-sig")

def replace_between(source: str, start_marker: str, end_marker: str, replacement: str) -> str:
    start = source.find(start_marker)
    end = source.find(end_marker)

    if start == -1 or end == -1 or end < start:
        raise SystemExit(f"No encontré bloque {start_marker} / {end_marker}")

    end += len(end_marker)
    return source[:start] + replacement + source[end:]


block = r'''/* CX_CRM_LIVE_01_START */
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

    return [
      String(hours).padStart(2, "0"),
      String(minutes).padStart(2, "0"),
      String(seconds).padStart(2, "0"),
    ].join(":");
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

    document.querySelectorAll("[data-live-since]").forEach((node) => {
      const startedAt = crmLiveParseDate(node.dataset.liveSince || "");
      if (!startedAt) {
        node.textContent = "00:00:00";
        return;
      }

      node.textContent = crmLiveFormatDuration(Date.now() - startedAt.getTime());
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
      `;
    }

    if (status === "working") {
      return `
        <div style="display:grid;grid-template-columns:1fr auto;gap:16px;align-items:center;padding:14px 0;border-top:1px solid rgba(255,255,255,.1)">
          <div>
            <strong>Turno iniciado</strong>
            <div class="client-muted">Cronómetro de jornada</div>
          </div>
          <strong style="font-size:26px" data-live-since="${h(row.shift_started_at || row.status_started_at || "")}">00:00:00</strong>
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
          ${timeline.map((item) => `
            <div style="display:grid;grid-template-columns:1fr auto;gap:16px;align-items:center;padding:12px;border-radius:16px;background:${item.is_active ? "rgba(0,255,180,.10)" : "rgba(255,255,255,.06)"};border:1px solid ${item.is_active ? "rgba(0,255,180,.25)" : "rgba(255,255,255,.1)"}">
              <div>
                <strong>${h(item.reference_name || "Referencia")}</strong>
                <div class="client-muted">${item.is_active ? "Referencia activa" : "Referencia cerrada"}</div>
              </div>
              <strong style="font-size:22px" ${item.is_active ? `data-live-since="${h(item.started_at || "")}"` : `data-live-seconds="${h(item.duration_seconds || 0)}"`}>00:00:00</strong>
            </div>
          `).join("")}
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
                Vista viva de colaboradores, turno, pausa, referencia actual y tiempos de producción.
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

    window.__cxCrmLiveRefreshInterval = setInterval(async () => {
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
  /* CX_CRM_LIVE_01_END */'''

src = replace_between(src, "/* CX_CRM_LIVE_01_START */", "/* CX_CRM_LIVE_01_END */", block)

path.write_text(src, encoding="utf-8")
print("CRM_LIVE_02_CLIENT_OK")
