from pathlib import Path
import re

path = Path("app/web/client.js")
src = path.read_text(encoding="utf-8-sig")

# Limpiar intento anterior por MutationObserver
src = re.sub(
    r"\n\s*/\*\s*CX_SETTINGS_MODAL_PAYROLL_01_START\s*\*/[\s\S]*?/\*\s*CX_SETTINGS_MODAL_PAYROLL_01_END\s*\*/\s*\n",
    "\n",
    src,
)

# Limpiar este patch si ya existía
src = re.sub(
    r"\n\s*/\*\s*CX_ACCOUNT_SETTINGS_PAYROLL_FINAL_START\s*\*/[\s\S]*?/\*\s*CX_ACCOUNT_SETTINGS_PAYROLL_FINAL_END\s*\*/\s*\n",
    "\n",
    src,
)

block = r'''
  /* CX_ACCOUNT_SETTINGS_PAYROLL_FINAL_START */
  async function cxAccountLoadPayrollSettings() {
    try {
      return await api(`/company-settings-v1/companies/${encodeURIComponent(state.companyId)}?ts=${Date.now()}`);
    } catch (error) {
      return {
        ok: false,
        settings: {
          payroll: {},
          payroll_cuts: {
            allow_close: true,
            allow_export: true,
            allow_archive: true,
          },
        },
        error: error.message || String(error),
      };
    }
  }

  function cxAccountFindEmailPanel() {
    const modal = document.getElementById("clx-account-modal");
    if (!modal) return null;

    const changeEmailButton = Array.from(modal.querySelectorAll("button"))
      .find((btn) => String(btn.textContent || "").toLowerCase().includes("cambiar correo"));

    if (changeEmailButton) {
      let node = changeEmailButton.parentElement;
      let fallback = changeEmailButton.parentElement;

      for (let i = 0; i < 10 && node && node !== modal; i += 1) {
        const text = String(node.textContent || "").toLowerCase();

        if (
          text.includes("cambiar correo") &&
          text.includes("nuevo correo") &&
          text.includes("contraseña actual") &&
          !text.includes("cambiar contraseña")
        ) {
          return node;
        }

        if (
          text.includes("cambiar correo") &&
          text.includes("nuevo correo") &&
          !text.includes("nueva contraseña") &&
          !text.includes("confirmar nueva contraseña")
        ) {
          fallback = node;
        }

        node = node.parentElement;
      }

      return fallback;
    }

    const newEmail = document.getElementById("clxAccountNewEmail");
    if (!newEmail) return null;

    let node = newEmail.parentElement;
    let fallback = newEmail.parentElement;

    for (let i = 0; i < 10 && node && node !== modal; i += 1) {
      const text = String(node.textContent || "").toLowerCase();

      if (
        text.includes("cambiar correo") &&
        text.includes("nuevo correo") &&
        !text.includes("nueva contraseña")
      ) {
        fallback = node;
      }

      node = node.parentElement;
    }

    return fallback;
  }

  function cxAccountPayrollCard(settings = {}) {
    const payroll = settings.payroll || {};
    const cuts = settings.payroll_cuts || {};
    const hours = payroll.ordinary_hours_limit ?? "";

    return `
      <div id="clxPayrollSettingsCard"
        style="
          margin-top:22px;
          padding-top:22px;
          border-top:1px solid rgba(255,255,255,.14);
        "
      >
        <h3 style="margin:0 0 14px;font-size:22px;font-weight:1000">Nómina y cortes</h3>

        <label style="display:block;margin-bottom:14px">
          <span style="display:block;margin-bottom:8px;font-size:12px;letter-spacing:.14em;text-transform:uppercase;font-weight:1000;opacity:.72">
            Total horas ordinarias hasta
          </span>

          <input
            id="clxPayrollOrdinaryHoursLimit"
            type="number"
            min="0.01"
            step="0.25"
            value="${h(hours)}"
            placeholder="Ej: 48"
            style="
              width:100%;
              border:1px solid rgba(255,255,255,.16);
              background:rgba(0,0,0,.28);
              color:inherit;
              border-radius:16px;
              padding:14px 16px;
              font-weight:1000;
              outline:none;
            "
          >
        </label>

        <p style="margin:0 0 14px;opacity:.72;font-weight:800;line-height:1.35">
          Hasta este total se calcula como hora ordinaria. Después de ese total se calcula como extra. Las pausas no cuentan.
        </p>

        <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:16px 0">
          <div style="padding:12px;border-radius:15px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.10)">
            <span style="display:block;font-size:11px;letter-spacing:.12em;text-transform:uppercase;opacity:.68">Cerrar corte</span>
            <strong>${cuts.allow_close === false ? "OFF" : "ON"}</strong>
          </div>

          <div style="padding:12px;border-radius:15px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.10)">
            <span style="display:block;font-size:11px;letter-spacing:.12em;text-transform:uppercase;opacity:.68">Exportar</span>
            <strong>${cuts.allow_export === false ? "OFF" : "ON"}</strong>
          </div>

          <div style="padding:12px;border-radius:15px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.10)">
            <span style="display:block;font-size:11px;letter-spacing:.12em;text-transform:uppercase;opacity:.68">Archivar</span>
            <strong>${cuts.allow_archive === false ? "OFF" : "ON"}</strong>
          </div>
        </div>

        <button
          id="clxPayrollSettingsSaveBtn"
          type="button"
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

        <div id="clxPayrollSettingsStatus" style="margin-top:12px;font-weight:900;opacity:.78"></div>
      </div>
    `;
  }

  async function cxAccountInjectPayrollSettings() {
    const modal = document.getElementById("clx-account-modal");
    if (!modal) return;

    const emailPanel = cxAccountFindEmailPanel();
    if (!emailPanel) return;

    const data = await cxAccountLoadPayrollSettings();
    const settings = data.settings || {};

    const existing = document.getElementById("clxPayrollSettingsCard");
    if (existing) existing.remove();

    emailPanel.insertAdjacentHTML("beforeend", cxAccountPayrollCard(settings));
  }

  async function cxAccountSavePayrollSettings() {
    const input = document.getElementById("clxPayrollOrdinaryHoursLimit");
    const status = document.getElementById("clxPayrollSettingsStatus");

    const hours = Number(String(input?.value || "").replace(",", "."));

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

  if (!window.__cxAccountSettingsPayrollFinalBound) {
    window.__cxAccountSettingsPayrollFinalBound = true;

    document.addEventListener("click", async (event) => {
      const savePayroll = event.target.closest("#clxPayrollSettingsSaveBtn");
      if (savePayroll) {
        event.preventDefault();
        event.stopPropagation();
        await cxAccountSavePayrollSettings();
      }
    }, true);
  }
  /* CX_ACCOUNT_SETTINGS_PAYROLL_FINAL_END */

'''

marker = "  function openAjustes(force) {"
if marker not in src:
    raise SystemExit("No encontré function openAjustes(force).")

src = src.replace(marker, block + "\n" + marker, 1)

old = '''    overlay.classList.add("open");
  }'''

new = '''    overlay.classList.add("open");
    cxAccountInjectPayrollSettings();
  }'''

if old not in src:
    raise SystemExit("No encontré overlay.classList.add(\"open\") dentro de openAjustes.")

src = src.replace(old, new, 1)

path.write_text(src, encoding="utf-8")
print("ACCOUNT_SETTINGS_PAYROLL_FINAL_OK")
