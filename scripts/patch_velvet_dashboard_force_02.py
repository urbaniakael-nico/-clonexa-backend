from pathlib import Path
import re

path = Path("app/web/client.js")
src = path.read_text(encoding="utf-8-sig")

# Limpia cualquier intento anterior incompleto
src = re.sub(
    r"\n\s*/\*\s*CX_VELVET_DASHBOARD_01_START\s*\*/[\s\S]*?/\*\s*CX_VELVET_DASHBOARD_01_END\s*\*/\s*\n",
    "\n",
    src,
)

src = re.sub(
    r"\n\s*/\*\s*CX_VELVET_DASHBOARD_FORCE_02_START\s*\*/[\s\S]*?/\*\s*CX_VELVET_DASHBOARD_FORCE_02_END\s*\*/\s*\n",
    "\n",
    src,
)

helper = r'''
  /* CX_VELVET_DASHBOARD_FORCE_02_START */
  const CX_VELVET_LAB_COMPANY_ID = "d63cf68c-be5b-4a30-aee4-341973018db1";

  function isVelvetLabTenant() {
    return String(state.companyId || "").toLowerCase() === CX_VELVET_LAB_COMPANY_ID;
  }

  function clientDashboardCompanyName(company = {}) {
    if (isVelvetLabTenant()) return "VELVET LAB";
    return company.name || "Empresa";
  }

  function velvetDashboardPercent(value) {
    const n = Number(value || 0);
    if (!Number.isFinite(n)) return "0%";
    return `${n.toLocaleString("es-CO", { maximumFractionDigits: 2 })}%`;
  }

  async function loadVelvetLabDashboardMetrics() {
    if (!isVelvetLabTenant()) return;

    const metrics = state.dashboardMetrics || {};
    state.dashboardMetrics = metrics;

    const [crmResult, refsResult, prodResult] = await Promise.allSettled([
      api(`/crm-core-v1/companies/${encodeURIComponent(state.companyId)}/snapshot?ts=${Date.now()}`),
      api(`/references-v1/companies/${encodeURIComponent(state.companyId)}/summary?ts=${Date.now()}`),
      api(`/production-v1/companies/${encodeURIComponent(state.companyId)}/summary?preset=7d&view=active&ts=${Date.now()}`),
    ]);

    if (crmResult.status === "fulfilled") {
      metrics.velvetPersonalConnected = Number(crmResult.value?.summary?.active_now || 0);
      metrics.velvetPersonalPaused = Number(crmResult.value?.summary?.on_break || 0);
    }

    if (refsResult.status === "fulfilled") {
      metrics.velvetActiveReferences = Number(
        refsResult.value?.bot_active_total ??
        refsResult.value?.active_total ??
        refsResult.value?.references_active ??
        refsResult.value?.references_total ??
        0
      );
    }

    if (prodResult.status === "fulfilled") {
      metrics.velvetProductionProgress = Number(
        prodResult.value?.totals?.progress_percent ??
        prodResult.value?.summary?.progress_percent ??
        0
      );
    }
  }
  /* CX_VELVET_DASHBOARD_FORCE_02_END */

'''

marker = re.search(r"\n\s*function\s+buildClientHeroKpis\s*\(", src)
if not marker:
    raise SystemExit("No encontré buildClientHeroKpis.")

src = src[:marker.start()] + "\n" + helper + src[marker.start():]

# Reemplaza la función que realmente pinta las tarjetas superiores
pattern = re.compile(
    r"  function\s+buildClientHeroKpis\s*\([^)]*\)\s*\{[\s\S]*?\n  function\s+buildClientHeroActions",
    re.S,
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
        ["Total referencias activas", String(metrics.velvetActiveReferences ?? 0)],
        ["% producción avance", velvetDashboardPercent(metrics.velvetProductionProgress ?? 0)],
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

src2, count = pattern.subn(replacement, src, count=1)
if count != 1:
    raise SystemExit("No pude reemplazar buildClientHeroKpis.")
src = src2

# Nombre visible VELVET LAB en /client sin renombrar la DB
src = src.replace('${h(company.name || "Empresa")}', '${h(clientDashboardCompanyName(company))}')
src = src.replace('${h(state.company?.name || "Empresa")}', '${h(clientDashboardCompanyName(state.company || {}))}')

# Fuerza render principal async y carga métricas antes de pintar dashboard
render_sig = "function render("
idx = src.find(render_sig)
if idx == -1:
    raise SystemExit("No encontré function render().")

if src[max(0, idx - 6):idx] != "async ":
    src = src[:idx] + "async " + src[idx:]
    idx += len("async ")

brace = src.find("{", idx)
if brace == -1:
    raise SystemExit("No encontré apertura de render().")

probe = src[brace:brace + 900]
if "await loadVelvetLabDashboardMetrics();" not in probe:
    src = src[:brace + 1] + "\n    await loadVelvetLabDashboardMetrics();" + src[brace + 1:]

path.write_text(src, encoding="utf-8")
print("VELVET_DASHBOARD_FORCE_02_OK")
