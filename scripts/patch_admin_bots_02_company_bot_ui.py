from pathlib import Path
import re

admin_path = Path("app/web/admin_v2.js")
client_path = Path("app/web/client.js")

def fix_mojibake(src: str) -> str:
    replacements = {
        "rÃ¡pidos": "rápidos",
        "rÃ¡pidas": "rápidas",
        "RÃ¡pidos": "Rápidos",
        "MÃ³dulos": "Módulos",
        "mÃ³dulos": "módulos",
        "MÃ³dulo": "Módulo",
        "mÃ³dulo": "módulo",
        "Ãšltima actualizaciÃ³n": "Última actualización",
        "Ultima validacion": "Última validación",
        "validacion": "validación",
        "conexion": "conexión",
        "Configuracion": "Configuración",
        "configuracion": "configuración",
        "Documentacion": "Documentación",
        "Catalogo": "Catálogo",
        "catalogo": "catálogo",
        "Fidelizacion": "Fidelización",
        "Creacion": "Creación",
        "Operacion": "Operación",
        "Nomina": "Nómina",
        "Produccion": "Producción",
    }

    for bad, good in replacements.items():
        src = src.replace(bad, good)

    return src


# =========================
# ADMIN V2
# =========================
src = admin_path.read_text(encoding="utf-8-sig")
src = fix_mojibake(src)

# 1) loadTelegramBotConfig: merge old bot config + dedicated webhook status.
old_load = '''      const data = await apiGet(`${API}/bots/companies/${companyId}/telegram`);
      state.companyBotConfigs.set(key, data || {});
      return data || {};
'''
new_load = '''      const baseConfig = await apiGet(`${API}/bots/companies/${companyId}/telegram`);
      let data = baseConfig || {};

      try {
        const webhookStatus = await apiGet(`${API}/company-bots-v1/companies/${companyId}/telegram/status`);
        data = { ...data, ...(webhookStatus || {}) };
      } catch (statusError) {
        // El endpoint dedicado puede no existir en instalaciones antiguas.
      }

      state.companyBotConfigs.set(key, data || {});
      return data || {};
'''

if old_load in src:
    src = src.replace(old_load, new_load, 1)

# 2) Bot flow helpers before renderCompanyAccessPanel.
helper_marker = "  function renderCompanyAccessPanel(company) {"

helpers = r'''
  function botFlowLabel(value) {
    const code = String(value || "base").toLowerCase();

    const labels = {
      base: "Base / Workforce",
      velvet_references: "Velvet / Referencias producción",
      field_operations: "Campo / GPS / Materiales",
      retail_sales: "Retail / Ventas",
      hospitality_orders: "Hospitality / Pedidos",
    };

    return labels[code] || code;
  }

  function suggestedBotFlow(company) {
    const codes = moduleCodesForCompany(company.id);

    if (codes.includes("references") && codes.includes("workforce")) return "velvet_references";
    if (codes.includes("gps") || codes.includes("materials") || codes.includes("field")) return "field_operations";
    if (codes.includes("sales") || codes.includes("stores") || codes.includes("retail")) return "retail_sales";
    if (codes.includes("hospitality") || codes.includes("orders") || codes.includes("tables")) return "hospitality_orders";

    return "base";
  }

  function botFlowOptions(company, selected) {
    const codes = moduleCodesForCompany(company.id);
    const options = [
      ["base", "Base / Workforce"],
    ];

    if (codes.includes("references") && codes.includes("workforce")) {
      options.push(["velvet_references", "Velvet / Referencias producción"]);
    }

    if (codes.includes("gps") || codes.includes("materials") || codes.includes("field")) {
      options.push(["field_operations", "Campo / GPS / Materiales"]);
    }

    if (codes.includes("sales") || codes.includes("stores") || codes.includes("retail")) {
      options.push(["retail_sales", "Retail / Ventas"]);
    }

    if (codes.includes("hospitality") || codes.includes("orders") || codes.includes("tables")) {
      options.push(["hospitality_orders", "Hospitality / Pedidos"]);
    }

    const unique = new Map(options);
    const selectedValue = selected || suggestedBotFlow(company);

    return [...unique.entries()]
      .map(([value, label]) => `<option value="${escapeHtml(value)}" ${value === selectedValue ? "selected" : ""}>${escapeHtml(label)}</option>`)
      .join("");
  }

  function botWebhookLabel(config) {
    const mode = String(config?.webhook_mode || "").toLowerCase();

    if (mode === "dedicated") return "Webhook dedicado";
    if (config?.configured) return "Pendiente de activar";

    return "Sin configurar";
  }

'''

if helpers.strip() not in src:
    if helper_marker not in src:
        raise SystemExit("No encontré renderCompanyAccessPanel en admin_v2.js")
    src = src.replace(helper_marker, helpers + "\n" + helper_marker, 1)

# 3) Insert flow constants inside renderCompanyAccessPanel.
old_consts = '''    const config = telegramConfig(company.id);
    const botsEnabled = moduleCodesForCompany(company.id).includes("bots");
    const botStatus = config?.loading
'''

new_consts = '''    const config = telegramConfig(company.id);
    const botModuleCodes = moduleCodesForCompany(company.id);
    const botsEnabled = botModuleCodes.includes("bots");
    const botFlowCode = config?.flow_code || suggestedBotFlow(company);
    const botWebhookMode = botWebhookLabel(config);
    const botWebhookUrl = config?.webhook_url || "";
    const botStatus = config?.loading
'''

if old_consts in src:
    src = src.replace(old_consts, new_consts, 1)

# 4) Add flow/webhook fields in Bot Telegram card.
old_bot_kv = '''          <div class="cx-kv"><span>Usuario bot</span><strong>${escapeHtml(config?.bot_username ? `@${config.bot_username}` : "Sin validar")}</strong></div>
          <div class="cx-kv"><span>Última validación</span><strong>${escapeHtml(config?.last_validated_at || "Sin validar")}</strong></div>
          <div class="cx-kv"><span>Error</span><strong>${escapeHtml(config?.last_error || "Sin error")}</strong></div>
'''

if old_bot_kv not in src:
    old_bot_kv = '''          <div class="cx-kv"><span>Usuario bot</span><strong>${escapeHtml(config?.bot_username ? `@${config.bot_username}` : "Sin validar")}</strong></div>
          <div class="cx-kv"><span>Ultima validacion</span><strong>${escapeHtml(config?.last_validated_at || "Sin validar")}</strong></div>
          <div class="cx-kv"><span>Error</span><strong>${escapeHtml(config?.last_error || "Sin error")}</strong></div>
'''

new_bot_kv = '''          <div class="cx-kv"><span>Usuario bot</span><strong>${escapeHtml(config?.bot_username ? `@${config.bot_username}` : "Sin validar")}</strong></div>
          <div class="cx-kv"><span>Flujo</span><strong>${escapeHtml(botFlowLabel(botFlowCode))}</strong></div>
          <div class="cx-kv"><span>Webhook</span><strong>${escapeHtml(botWebhookMode)}</strong></div>
          <div class="cx-kv"><span>Última validación</span><strong>${escapeHtml(config?.last_validated_at || "Sin validar")}</strong></div>
          <div class="cx-kv"><span>Error</span><strong>${escapeHtml(config?.last_error || "Sin error")}</strong></div>
'''

if old_bot_kv in src and "botFlowLabel(botFlowCode)" not in src:
    src = src.replace(old_bot_kv, new_bot_kv, 1)

# 5) Add flow selector after token input.
old_token_label = '''          <label>Token Telegram BotFather
            <input name="token" type="password" autocomplete="off" placeholder="${config?.configured ? "Pega un token nuevo solo si quieres reemplazarlo" : "Pega aqui el token de BotFather"}" />
          </label>
'''

new_token_label = '''          <label>Token Telegram BotFather
            <input name="token" type="password" autocomplete="off" placeholder="${config?.configured ? "Pega un token nuevo solo si quieres reemplazarlo" : "Pega aquí el token de BotFather"}" />
          </label>
          <label>Flujo del bot
            <select name="flow_code" data-bot-flow-company="${escapeHtml(company.id)}">
              ${botFlowOptions(company, botFlowCode)}
            </select>
            <small>El flujo se sugiere según los módulos activos de esta empresa.</small>
          </label>
          ${botWebhookUrl ? `<div class="cx-alert" style="display:block;margin:10px 0"><strong>Webhook dedicado:</strong><br>${escapeHtml(botWebhookUrl)}</div>` : ""}
'''

if old_token_label in src and 'data-bot-flow-company="${escapeHtml(company.id)}"' not in src:
    src = src.replace(old_token_label, new_token_label, 1)

# 6) Button label: activate/reinstall webhook, not listener.
src = re.sub(
    r'\$\{config\?\.configured \? `<button class="cx-btn(?: cx-btn-primary)?" type="button" data-start-telegram-listener="\$\{escapeHtml\(company\.id\)\}">[^<]*</button>` : ""\}',
    '${config?.configured ? `<button class="cx-btn cx-btn-primary" type="button" data-start-telegram-listener="${escapeHtml(company.id)}">${config?.webhook_mode === "dedicated" ? "Reinstalar webhook dedicado" : "Activar webhook dedicado"}</button>` : ""}',
    src,
    count=1,
)

# 7) saveTelegramBotConfig: do not send flow_code to legacy token endpoint.
old_save_lines = '''    body.token = String(body.token || "").trim();
    body.name = String(body.name || "").trim();
'''

new_save_lines = '''    body.token = String(body.token || "").trim();
    body.name = String(body.name || "").trim();
    delete body.flow_code;
'''

if old_save_lines in src and "delete body.flow_code;" not in src:
    src = src.replace(old_save_lines, new_save_lines, 1)

# 8) Replace startTelegramBotListener implementation.
start_marker = "  async function startTelegramBotListener(companyId) {"
end_marker = "  async function deactivateTelegramBotConfig(companyId) {"

if start_marker not in src or end_marker not in src:
    raise SystemExit("No encontré startTelegramBotListener/deactivateTelegramBotConfig")

start_idx = src.index(start_marker)
end_idx = src.index(end_marker)

new_start_fn = '''  async function startTelegramBotListener(companyId) {
    try {
      const flowSelect = [...document.querySelectorAll("[data-bot-flow-company]")]
        .find((node) => node.dataset.botFlowCompany === companyId);

      const flowCode = String(flowSelect?.value || telegramConfig(companyId)?.flow_code || "base").trim();

      const data = await apiPost(`${API}/company-bots-v1/companies/${companyId}/telegram/activate-webhook`, {
        flow_code: flowCode,
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

src = src[:start_idx] + new_start_fn + src[end_idx:]

admin_path.write_text(src, encoding="utf-8")


# =========================
# CLIENT PORTAL
# =========================
client = client_path.read_text(encoding="utf-8-sig")
client = fix_mojibake(client)

# Merge client bot config with dedicated status.
old_client_load = '''  async function loadClientBotConfig() {
    if (!state.companyId) return null;
    try {
      return await api(`/bots/companies/${state.companyId}/telegram`);
    } catch (error) {
      return { configured: false, status: "error", last_error: error.message || "No se pudo cargar bot" };
    }
  }
'''

new_client_load = '''  async function loadClientBotConfig() {
    if (!state.companyId) return null;
    try {
      const baseConfig = await api(`/bots/companies/${state.companyId}/telegram`);
      try {
        const webhookStatus = await api(`/company-bots-v1/companies/${state.companyId}/telegram/status`);
        return { ...(baseConfig || {}), ...(webhookStatus || {}) };
      } catch (statusError) {
        return baseConfig;
      }
    } catch (error) {
      return { configured: false, status: "error", last_error: error.message || "No se pudo cargar bot" };
    }
  }
'''

if old_client_load in client:
    client = client.replace(old_client_load, new_client_load, 1)

# Add client flow label helper.
client_helper_marker = "  function botStatusLabel(status) {"
client_flow_helper = r'''
  function clientBotFlowLabel(value) {
    const code = String(value || "base").toLowerCase();

    const labels = {
      base: "Base / Workforce",
      velvet_references: "Velvet / Referencias producción",
      field_operations: "Campo / GPS / Materiales",
      retail_sales: "Retail / Ventas",
      hospitality_orders: "Hospitality / Pedidos",
    };

    return labels[code] || code;
  }

'''

if "function clientBotFlowLabel(value)" not in client:
    if client_helper_marker not in client:
        raise SystemExit("No encontré botStatusLabel en client.js")
    client = client.replace(client_helper_marker, client_flow_helper + client_helper_marker, 1)

# Add flow KPI to client Bot module.
old_client_bot_kpi = '''                <div class="client-kpi">
                  <span>Bot</span>
                  <strong>${h(botUsername)}</strong>
                </div>
'''

new_client_bot_kpi = '''                <div class="client-kpi">
                  <span>Bot</span>
                  <strong>${h(botUsername)}</strong>
                </div>
                <div class="client-kpi">
                  <span>Flujo</span>
                  <strong>${h(clientBotFlowLabel(config?.flow_code))}</strong>
                </div>
                <div class="client-kpi">
                  <span>Webhook</span>
                  <strong>${h(config?.webhook_mode === "dedicated" ? "Dedicado" : "Pendiente")}</strong>
                </div>
'''

if old_client_bot_kpi in client and "clientBotFlowLabel(config?.flow_code)" not in client:
    client = client.replace(old_client_bot_kpi, new_client_bot_kpi, 1)

client_path.write_text(client, encoding="utf-8")

print("ADMIN_BOTS_02_PATCH_OK")
