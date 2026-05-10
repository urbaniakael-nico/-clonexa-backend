from pathlib import Path
import re

path = Path("app/web/client.js")
src = path.read_text(encoding="utf-8-sig")

# Limpia intentos previos del mismo bloque si existen
src = re.sub(
    r"\n\s*/\*\s*CX_SETTINGS_MODAL_PAYROLL_01_START\s*\*/[\s\S]*?/\*\s*CX_SETTINGS_MODAL_PAYROLL_01_END\s*\*/\s*\n",
    "\n",
    src,
)

block = r'''
  /* CX_SETTINGS_MODAL_PAYROLL_01_START */
  function cxSettingsTextIncludes(node, text) {
    return String(node?.textContent || "").toLowerCase().includes(String(text || "").toLowerCase());
  }

  function cxFindSettingsModal() {
    const candidates = Array.from(document.querySelectorAll("div, section, article, main"));
    return candidates.find((node) => {
      const text = String(node.textContent || "").toLowerCase();
      return text.includes("ajustes") &&
             text.includes("cambiar correo") &&
             text.includes("cambiar contraseña") &&
             text.includes("sesión");
    }) || null;
  }

  function cxFindPanelByTitle(modal, title) {
    const headings = Array.from(modal.querySelectorAll("h1,h2,h3,h4,strong,div,span"))
      .filter((node) => cxSettingsTextIncludes(node, title));

    for (const heading of headings) {
      let node = heading;

      for (let i = 0; i < 8 && node; i += 1) {
        const text = String(node.textContent || "").toLowerCase();

        if (
          text.includes(title.toLowerCase()) &&
          text.includes("nuevo correo") &&
          text.includes("contraseña actual") &&
          !text.includes("cambiar contraseña nueva contraseña")
        ) {
          return node;
        }

        node = node.parentElement;
      }
    }

    return null;
  }

  function cxPayrollSettingsCardHtml(settings = {}) {
    const payroll = settings.payroll || {};
    const cuts = settings.payroll_cuts || {};
    const hours = payroll.ordinary_hours_limit ?? "";

    return `
      <section
        data-cx-settings-payroll-card
        style="
          grid-column: 2 / 3;
          padding: 26px;
          border-radius: 24px;
          background: linear-gradient(135deg, rgba(255,255,255,.08), rgba(255,255,255,.035));
          border: 1px solid rgba(255,255,255,.13);
          box-shadow: 0 18px 40px rgba(0,0,0,.18);
        "
      >
        <h2 style="margin:0 0 16px;font-size:24px">Nómina y cortes</h2>

        <div style="margin-bottom:18px">
          <label style="display:block;font-size:12px;letter-spacing:.14em;text-transform:uppercase;font-weight:900;opacity:.72;margin-bottom:8px">
            Total horas ordinarias hasta
          </label>

          <input
            data-cx-payroll-hours-limit
            type="number"
            min="0.01"
            step="0.25"
            value="${h(hours)}"
            placeholder="Ej: 48"
            style="
              width:100%;
              padding:14px 16px;
              border-radius:16px;
              border:1px solid rgba(255,255,255,.15);
              background:rgba(0,0,0,.28);
              color:inherit;
              font-weight:900;
              outline:none;
            "
          >

          <p style="margin:10px 0 0;opacity:.72;font-size:13px;line-height:1.35">
            Hasta este total se calcula como ordinaria. Después de ese total se calcula como extra. Las pausas no cuentan.
          </p>
        </div>

        <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:18px 0">
          <div style="padding:12px;border-radius:16px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.09)">
            <span style="display:block;font-size:11px;letter-spacing:.12em;text-transform:uppercase;opacity:.68">Cerrar corte</span>
            <strong>${cuts.allow_close === false ? "OFF" : "ON"}</strong>
          </div>
          <div style="padding:12px;border-radius:16px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.09)">
            <span style="display:block;font-size:11px;letter-spacing:.12em;text-transform:uppercase;opacity:.68">Exportar</span>
            <strong>${cuts.allow_export === false ? "OFF" : "ON"}</strong>
          </div>
          <div style="padding:12px;border-radius:16px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.09)">
            <span style="display:block;font-size:11px;letter-spacing:.12em;text-transform:uppercase;opacity:.68">Archivar</span>
            <strong>${cuts.allow_archive === false ? "OFF" : "ON"}</strong>
          </div>
        </div>

        <button
          type="button"
          data-cx-save-payroll-settings
          style="
            border:0;
            border-radius:16px;
            padding:14px 22px;
            font-weight:1000;
            color:white;
            cursor:pointer;
            background:linear-gradient(135deg,#ff1fb8,#8b5cf6);
          "
        >
          Guardar nómina
        </button>

        <div data-cx-payroll-settings-status style="margin-top:12px;font-weight:800;opacity:.78"></div>
      </section>
    `;
  }

  async function cxLoadCompanySettingsForModal() {
    try {
      return await api(`/company-settings-v1/companies/${encodeURIComponent(state.companyId)}`);
    } catch (error) {
      return { ok: false, settings: {} };
    }
  }

  async function cxInjectPayrollSettingsIntoModal() {
    const modal = cxFindSettingsModal();
    if (!modal) return;

    if (modal.querySelector("[data-cx-settings-payroll-card]")) return;

    const emailPanel = cxFindPanelByTitle(modal, "Cambiar correo");
    if (!emailPanel) return;

    const data = await cxLoadCompanySettingsForModal();
    const settings = data.settings || {};

    emailPanel.insertAdjacentHTML("afterend", cxPayrollSettingsCardHtml(settings));
  }

  async function cxSavePayrollSettingsFromModal() {
    const card = document.querySelector("[data-cx-settings-payroll-card]");
    if (!card) return;

    const input = card.querySelector("[data-cx-payroll-hours-limit]");
    const status = card.querySelector("[data-cx-payroll-settings-status]");

    const raw = String(input?.value || "").replace(",", ".");
    const hours = Number(raw);

    if (!Number.isFinite(hours) || hours <= 0) {
      if (status) status.textContent = "Ingresa un total de horas ordinarias válido.";
      return;
    }

    if (status) status.textContent = "Guardando...";

    await api(`/company-settings-v1/companies/${encodeURIComponent(state.companyId)}`, {
      method: "PUT",
      body: JSON.stringify({
        payroll: {
          ordinary_hours_limit: hours,
          pause_policy: "exclude",
        },
        payroll_cuts: {
          allow_close: true,
          allow_export: true,
          allow_archive: true,
        },
      }),
    });

    if (status) status.textContent = "Configuración guardada.";
  }

  function cxSchedulePayrollSettingsModalInjection() {
    setTimeout(cxInjectPayrollSettingsIntoModal, 80);
    setTimeout(cxInjectPayrollSettingsIntoModal, 250);
    setTimeout(cxInjectPayrollSettingsIntoModal, 700);
  }

  if (!window.__cxSettingsModalPayroll01Bound) {
    window.__cxSettingsModalPayroll01Bound = true;

    document.addEventListener("click", async (event) => {
      const save = event.target.closest("[data-cx-save-payroll-settings]");
      if (save) {
        event.preventDefault();
        await cxSavePayrollSettingsFromModal();
        return;
      }

      const text = String(event.target?.textContent || "").toLowerCase();
      const settingsLike =
        event.target.closest("[data-client-settings], [data-open-settings], [data-client-module='settings'], [data-client-module='core_settings']") ||
        text.includes("ajustes") ||
        text.includes("configuración") ||
        text.includes("settings");

      if (settingsLike) {
        cxSchedulePayrollSettingsModalInjection();
      }
    }, true);

    const observer = new MutationObserver(() => {
      if (document.querySelector("[data-cx-settings-payroll-card]")) return;
      const modal = cxFindSettingsModal();
      if (modal) cxSchedulePayrollSettingsModalInjection();
    });

    observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
    });
  }
  /* CX_SETTINGS_MODAL_PAYROLL_01_END */

'''

# Insertar antes del cierre principal IIFE si existe; si no, al final.
inserted = False

for marker in ["})();", "}());"]:
    idx = src.rfind(marker)
    if idx != -1:
      src = src[:idx] + block + "\n" + src[idx:]
      inserted = True
      break

if not inserted:
    src += "\n" + block + "\n"

path.write_text(src, encoding="utf-8")
print("SETTINGS_MODAL_PAYROLL_01_OK")
