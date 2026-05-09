from pathlib import Path

path = Path("app/web/admin_v2.js")
src = path.read_text(encoding="utf-8-sig")

src = src.replace(
    '${config?.configured ? `<button class="cx-btn" type="button" data-start-telegram-listener="${escapeHtml(company.id)}">Iniciar escucha</button>` : ""}',
    '${config?.configured ? `<button class="cx-btn cx-btn-primary" type="button" data-start-telegram-listener="${escapeHtml(company.id)}">Activar webhook dedicado</button>` : ""}'
)

src = src.replace(
'''  async function startTelegramBotListener(companyId) {
    try {
      const data = await apiPost(`${API}/bots/companies/${companyId}/telegram/listener/start`, {});
      state.companyBotConfigs.set(botConfigKey(companyId, "telegram"), data);
      showToast("Escucha del bot iniciada. Ya no necesitas PowerShell para capturar mensajes.");
      const company = state.companies.find((c) => c.id === companyId);
      if (company) renderCompanyDetailTab(company);
    } catch (error) {
      showToast(`No se pudo iniciar la escucha: ${error.message}`, "error");
    }
  }
''',
'''  async function startTelegramBotListener(companyId) {
    try {
      const data = await apiPost(`${API}/company-bots-v1/companies/${companyId}/telegram/activate-webhook`, {
        flow_code: "velvet_references",
      });
      state.companyBotConfigs.set(botConfigKey(companyId, "telegram"), data);
      showToast("Webhook dedicado activado para esta empresa.");
      const company = state.companies.find((c) => c.id === companyId);
      if (company) renderCompanyDetailTab(company);
    } catch (error) {
      showToast(`No se pudo activar el webhook dedicado: ${error.message}`, "error");
    }
  }
'''
)

path.write_text(src, encoding="utf-8")
print("BOT_CONSOLE_01_ADMIN_OK")
