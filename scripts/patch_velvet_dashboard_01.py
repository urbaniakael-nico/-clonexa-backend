from pathlib import Path
import re

path = Path("app/web/client.js")
src = path.read_text(encoding="utf-8-sig")

VELVET_ID = "d63cf68c-be5b-4a30-aee4-341973018db1"

helper = r'''
  /* CX_VELVET_DASHBOARD_01_START */
  const VELVET_LAB_COMPANY_ID = "d63cf68c-be5b-4a30-aee4-341973018db1";

  function isVelvetLabTenant() {
    return String(state.companyId || "").toLowerCase() === VELVET_LAB_COMPANY_ID;
  }

  function clientDisplayCompanyName(company = {}) {
    if (isVelvetLabTenant()) return "VELVET LAB";
    return company.name || "Empresa";
  }

  async function loadVelvetLabDashboardMetrics() {
    if (!isVelvetLabTenant()) return;

    const metrics = state.dashboardMetrics || {};
    state.dashboardMetrics = metrics;

    try {
      const crm = await api(`/crm-core-v1/companies/${state.companyId}/snapshot?ts=${Date.now()}`);
      metrics.velvetPersonalConnected = Number(crm?.summary?.active_now || 0);
      metrics.velvetPersonalPaused = Number(crm?.summary?.on_break || 0);
    } catch (error) {
      metrics.velvetPersonalConnected = metrics.velvetPersonalConnected ?? 0;
      metrics.velvetPersonalPaused = metrics.velvetPersonalPaused ?? 0;
    }

    try {
      const refs = await api(`/references-v1/companies/${state.companyId}/summary?ts=${Date.now()}`);
      metrics.velvetActiveReferences = Number(refs?.bot_active_total ?? refs?.references_total ?? 0);
    } catch (error) {
      metrics.velvetActiveReferences = metrics.velvetActiveReferences ?? 0;
    }

    try {
      const prod = await api(`/production-v1/companies/${state.companyId}/summary?preset=7d&view=active&ts=${Date.now()}`);
      metrics.velvetProductionProgress = Number(prod?.totals?.progress_percent ?? 0);
    } catch (error) {
      metrics.velvetProductionProgress = metrics.velvetProductionProgress ?? 0;
    }
  }
  /* CX_VELVET_DASHBOARD_01_END */

'''

if "CX_VELVET_DASHBOARD_01_START" not in src:
    marker = "  function buildClientHeroKpis("
    if marker not in src:
        raise SystemExit("No encontré buildClientHeroKpis para insertar helpers Velvet.")
    src = src.replace(marker, helper + "\n" + marker, 1)

# Replace buildClientHeroKpis with tenant-aware version while keeping generic behavior.
pattern = re.compile(
    r"  function buildClientHeroKpis\(modules = \[\], company = \{\}\) \{.*?\n  function buildClientHeroActions",
    re.S
)

replacement = r'''  function buildClientHeroKpis(modules = [], company = {}) {
    const visible = visibleClientModules(modules);
    const codes = clientModuleCodes(visible);
    const total = Array.isArray(visible) ? visible.length : 0;
    const metrics = state.dashboardMetrics || {};

    if (isVelvetLabTenant()) {
      return [
        ["Personal conectado", String(metrics.velvetPersonalConnected ?? 0)],
        ["Personal pausa", String(metrics.velvetPersonalPaused ?? 0)],
        ["Referencias activas", String(metrics.velvetActiveReferences ?? 0)],
        ["Producción avance", `${kpiNumber(metrics.velvetProductionProgress ?? 0, 2)}%`],
      ];
    }

    if (Array.isArray(metrics.kpiDashboardCards) && metrics.kpiDashboardCards.length) {
      return metrics.kpiDashboardCards.slice(0, 4).map((card) => [
        card.label || "KPI",
        String(card.format === "money" ? kpiMoney(card.value) : kpiNumber(card.value, Number(card.value || 0) % 1 === 0 ? 0 : 2))
      ]);
    }

    const kpis = [];

    if (hasAnyClientModule(codes, ["workforce"])) {
      kpis.push(["Personal activo", String(metrics.activeEmployees ?? "0")]);
    }

    if (hasAnyClientModule(codes, ["bots"])) {
      const botStatus = String(metrics.botStatus || "").toLowerCase();
      const connected = metrics.botConfigured && !["error", "inactive", "not_configured"].includes(botStatus);
      kpis.push(["Canales", connected ? "ON" : "OFF"]);
    }

    if (hasAnyClientModule(codes, ["reports", "kpis"])) {
      kpis.push(["Reportes", "OK"]);
    }

    if (hasAnyClientModule(codes, ["sales"])) {
      kpis.push(["Ventas", metrics.salesToday ?? "0"]);
    }

    if (hasAnyClientModule(codes, ["inventory", "stock"])) {
      kpis.push(["Stock bajo", metrics.lowStock ?? "0"]);
    }

    if (!kpis.length) {
      kpis.push(["Empresa", company.name || "Activa"]);
      kpis.push(["Módulos activos", String(total)]);
      kpis.push(["Estado", "LIVE"]);
    }

    return kpis.slice(0, 4);
  }

  function buildClientHeroActions'''

src2 = pattern.sub(replacement, src, count=1)
if src2 == src:
    raise SystemExit("No pude reemplazar buildClientHeroKpis.")
src = src2

# Force display name only in dashboard-visible text without renaming DB tenant.
src = src.replace(
    'company.name || "Empresa"',
    'clientDisplayCompanyName(company)'
)

src = src.replace(
    'state.company?.name || "Empresa"',
    'clientDisplayCompanyName(state.company || {})'
)

src = src.replace(
    '${h(company.name || "Empresa")}',
    '${h(clientDisplayCompanyName(company))}'
)

src = src.replace(
    '${h(state.company?.name || "Empresa")}',
    '${h(clientDisplayCompanyName(state.company || {}))}'
)

# Ensure dashboard loads Velvet live metrics before rendering hero.
render_names = [
    "renderClientDashboard",
    "renderDashboard",
    "renderClientHome",
]

patched_render = False

for name in render_names:
    idx = src.find(f"async function {name}(")
    if idx == -1:
        continue

    brace = src.find("{", idx)
    if brace == -1:
        continue

    insert_at = brace + 1
    snippet = "\n    await loadVelvetLabDashboardMetrics();"
    if snippet.strip() not in src[idx:idx + 1200]:
        src = src[:insert_at] + snippet + src[insert_at:]
    patched_render = True
    break

if not patched_render:
    raise SystemExit("No encontré render dashboard async para cargar métricas Velvet.")

path.write_text(src, encoding="utf-8")
print("VELVET_DASHBOARD_01_OK")
