from pathlib import Path
import re

path = Path("app/web/client.js")
text = path.read_text(encoding="utf-8-sig")

marker = "/* CLONEXA 020D DASHBOARD NATIVE I18N */"

if marker not in text:
    block = r'''
/* CLONEXA 020D DASHBOARD NATIVE I18N */
const CLX_DASHBOARD_I18N = {
  es: {
    "dashboard.eyebrow": "SISTEMA OPERATIVO EMPRESARIAL",
    "dashboard.subtitle": "Panel operativo independiente conectado a sus módulos activos.",
    "dashboard.panel_eyebrow": "MÓDULOS DEL PANEL",
    "dashboard.services_active": "Servicios activos",
    "dashboard.modules_active": "módulos activos",
    "dashboard.active_now": "Activos ahora",
    "dashboard.gps_inside": "GPS dentro",
    "dashboard.material_delivered": "Material entregado",
    "dashboard.low_stock": "Stock bajo",
    "dashboard.add_staff": "Agregar personal",
    "dashboard.view_bot": "Ver bot",
    "dashboard.view_crm": "Ver CRM",
    "dashboard.view_payroll": "Ver nómina",
    "dashboard.inventory": "Inventario",
    "nav.dashboard": "Dashboard",

    "module.core.title": "Núcleo",
    "module.core.subtitle": "base operativa",
    "module.workforce.title": "Workforce",
    "module.workforce.subtitle": "personal operativo",
    "module.field.title": "Operación en campo",
    "module.field.subtitle": "field",
    "module.gps.title": "GPS",
    "module.gps.subtitle": "ubicación y rutas",
    "module.inventory.title": "Inventario",
    "module.inventory.subtitle": "stock y materiales",
    "module.materials.title": "Materiales",
    "module.materials.subtitle": "solicitud y devolución",
    "module.payroll.title": "Nómina",
    "module.payroll.subtitle": "corte y cálculo",
    "module.bots.title": "Bots",
    "module.bots.subtitle": "telegram / whatsapp",
    "module.crm.title": "CRM Campo",
    "module.crm.subtitle": "operación en vivo",
    "module.kpis.title": "KPIs",
    "module.kpis.subtitle": "indicadores operativos",
    "module.reports.title": "Reportes",
    "module.reports.subtitle": "métricas y auditoría"
  },

  en: {
    "dashboard.eyebrow": "BUSINESS OPERATING SYSTEM",
    "dashboard.subtitle": "Independent operations panel connected to its active modules.",
    "dashboard.panel_eyebrow": "PANEL MODULES",
    "dashboard.services_active": "Active services",
    "dashboard.modules_active": "active modules",
    "dashboard.active_now": "Active now",
    "dashboard.gps_inside": "GPS inside",
    "dashboard.material_delivered": "Delivered material",
    "dashboard.low_stock": "Low stock",
    "dashboard.add_staff": "Add staff",
    "dashboard.view_bot": "View bot",
    "dashboard.view_crm": "View CRM",
    "dashboard.view_payroll": "View payroll",
    "dashboard.inventory": "Inventory",
    "nav.dashboard": "Dashboard",

    "module.core.title": "Core",
    "module.core.subtitle": "operating base",
    "module.workforce.title": "Workforce",
    "module.workforce.subtitle": "operational staff",
    "module.field.title": "Field Ops",
    "module.field.subtitle": "field operation",
    "module.gps.title": "GPS",
    "module.gps.subtitle": "location and routes",
    "module.inventory.title": "Inventory",
    "module.inventory.subtitle": "stock and materials",
    "module.materials.title": "Materials",
    "module.materials.subtitle": "requests and returns",
    "module.payroll.title": "Payroll",
    "module.payroll.subtitle": "cutoff and calculation",
    "module.bots.title": "Bots",
    "module.bots.subtitle": "telegram / whatsapp",
    "module.crm.title": "Field CRM",
    "module.crm.subtitle": "live operation",
    "module.kpis.title": "KPIs",
    "module.kpis.subtitle": "operational indicators",
    "module.reports.title": "Reports",
    "module.reports.subtitle": "metrics and audit"
  },

  fr: {
    "dashboard.eyebrow": "SYSTÈME OPÉRATIONNEL D’ENTREPRISE",
    "dashboard.subtitle": "Panneau opérationnel indépendant connecté à ses modules actifs.",
    "dashboard.panel_eyebrow": "MODULES DU PANNEAU",
    "dashboard.services_active": "Services actifs",
    "dashboard.modules_active": "modules actifs",
    "dashboard.active_now": "Actifs maintenant",
    "dashboard.gps_inside": "GPS à l’intérieur",
    "dashboard.material_delivered": "Matériel livré",
    "dashboard.low_stock": "Stock faible",
    "dashboard.add_staff": "Ajouter du personnel",
    "dashboard.view_bot": "Voir bot",
    "dashboard.view_crm": "Voir CRM",
    "dashboard.view_payroll": "Voir paie",
    "dashboard.inventory": "Inventaire",
    "nav.dashboard": "Tableau de bord",

    "module.core.title": "Noyau",
    "module.core.subtitle": "base opérationnelle",
    "module.workforce.title": "Workforce",
    "module.workforce.subtitle": "personnel opérationnel",
    "module.field.title": "Opération terrain",
    "module.field.subtitle": "opération terrain",
    "module.gps.title": "GPS",
    "module.gps.subtitle": "localisation et itinéraires",
    "module.inventory.title": "Inventaire",
    "module.inventory.subtitle": "stock et matériaux",
    "module.materials.title": "Matériaux",
    "module.materials.subtitle": "demandes et retours",
    "module.payroll.title": "Paie",
    "module.payroll.subtitle": "clôture et calcul",
    "module.bots.title": "Bots",
    "module.bots.subtitle": "telegram / whatsapp",
    "module.crm.title": "CRM Terrain",
    "module.crm.subtitle": "opération en direct",
    "module.kpis.title": "KPIs",
    "module.kpis.subtitle": "indicateurs opérationnels",
    "module.reports.title": "Rapports",
    "module.reports.subtitle": "métriques et audit"
  }
};

function clxDashboardLanguage() {
  const value = String(localStorage.getItem("clonexa_client_language") || "es").toLowerCase();
  return ["es", "en", "fr"].includes(value) ? value : "es";
}

function clxDashboardText(key, params = {}) {
  const lang = clxDashboardLanguage();
  const pack = CLX_DASHBOARD_I18N[lang] || CLX_DASHBOARD_I18N.es;
  let value = pack[key] || CLX_DASHBOARD_I18N.es[key] || key;

  Object.keys(params || {}).forEach((paramKey) => {
    value = value.replaceAll(`{${paramKey}}`, String(params[paramKey]));
  });

  return value;
}

function clxDashboardModuleMeta(code, source = {}, index = 0) {
  const safeCode = String(code || "").trim();
  const fallback = MODULE_UI[safeCode] || [
    source.name || safeCode || `Modulo ${index + 1}`,
    source.description || source.category || "servicio activo",
    (safeCode || String(index + 1)).slice(0, 3).toUpperCase(),
  ];

  return [
    clxDashboardText(`module.${safeCode}.title`) === `module.${safeCode}.title`
      ? fallback[0]
      : clxDashboardText(`module.${safeCode}.title`),
    clxDashboardText(`module.${safeCode}.subtitle`) === `module.${safeCode}.subtitle`
      ? fallback[1]
      : clxDashboardText(`module.${safeCode}.subtitle`),
    fallback[2],
  ];
}
/* END CLONEXA 020D DASHBOARD NATIVE I18N */
'''

    text = text.replace("  const MODULE_UI = {", block + "\n\n  const MODULE_UI = {", 1)

# 1) Usar metadata localizada para módulos.
text = re.sub(
    r'''const meta = MODULE_UI\[code\] \|\| \[\s*
\s*source\.name \|\| code \|\| `Modulo \$\{index \+ 1\}`,\s*
\s*source\.description \|\| source\.category \|\| "servicio activo",\s*
\s*\(code \|\| String\(index \+ 1\)\)\.slice\(0, 3\)\.toUpperCase\(\),\s*
\s*\];''',
    "const meta = clxDashboardModuleMeta(code, source, index);",
    text,
    flags=re.MULTILINE,
)

# 2) moduleLabel localizado.
text = re.sub(
    r'''function moduleLabel\(code\) \{\s*
\s*const meta = MODULE_UI\[String\(code \|\| ""\)\.trim\(\)\];\s*
\s*return meta \? meta\[0\] : String\(code \|\| "Modulo"\);\s*
\s*\}''',
    '''function moduleLabel(code) {
    const safeCode = String(code || "").trim();
    const meta = clxDashboardModuleMeta(safeCode, {}, 0);
    return meta ? meta[0] : String(code || "Modulo");
  }''',
    text,
    flags=re.MULTILINE,
)

# 3) Acciones del hero.
text = text.replace('actions.push({ label: "Agregar personal", action: "workforce:add" });',
                    'actions.push({ label: clxDashboardText("dashboard.add_staff"), action: "workforce:add" });')
text = text.replace('actions.push({ label: "Ver bot", action: "bots:open" });',
                    'actions.push({ label: clxDashboardText("dashboard.view_bot"), action: "bots:open" });')
text = text.replace('actions.push({ label: "Ver CRM", action: "crm:open" });',
                    'actions.push({ label: clxDashboardText("dashboard.view_crm"), action: "crm:open" });')
text = text.replace('actions.push({ label: "Ver nómina", action: "payroll:open" });',
                    'actions.push({ label: clxDashboardText("dashboard.view_payroll"), action: "payroll:open" });')
text = text.replace('actions.push({ label: "Inventario", action: "inventory:open" });',
                    'actions.push({ label: clxDashboardText("dashboard.inventory"), action: "inventory:open" });')

# 4) Nav Dashboard.
text = text.replace(
    'data-client-back-dashboard>Dashboard</button>`];',
    'data-client-back-dashboard>${h(clxDashboardText("nav.dashboard"))}</button>`];'
)

# 5) Textos base del dashboard principal.
text = re.sub(
    r'<div class="client-eyebrow">Sistema operativo empresarial</div>',
    '<div class="client-eyebrow">${h(clxDashboardText("dashboard.eyebrow"))}</div>',
    text,
    flags=re.IGNORECASE,
)

text = re.sub(
    r'<p class="client-muted">Panel operativo independiente conectado a sus m(?:\?|ó|Ã³|o)dulos activos\.</p>',
    '<p class="client-muted">${h(clxDashboardText("dashboard.subtitle"))}</p>',
    text,
    flags=re.IGNORECASE,
)

text = re.sub(
    r'<div class="client-eyebrow">M(?:\?|ó|Ã³|o)dulos del panel</div>',
    '<div class="client-eyebrow">${h(clxDashboardText("dashboard.panel_eyebrow"))}</div>',
    text,
    flags=re.IGNORECASE,
)

text = text.replace('<h2>Servicios activos</h2>', '<h2>${h(clxDashboardText("dashboard.services_active"))}</h2>')

text = re.sub(
    r'<span class="client-badge">\$\{h\(modules\.length\)\} modulos activos</span>',
    '<span class="client-badge">${h(modules.length)} ${h(clxDashboardText("dashboard.modules_active"))}</span>',
    text,
)

text = re.sub(
    r'<span class="client-badge">\$\{h\(modules\.length\)\} módulos activos</span>',
    '<span class="client-badge">${h(modules.length)} ${h(clxDashboardText("dashboard.modules_active"))}</span>',
    text,
)

# 6) KPI labels del dashboard. Reemplazos seguros por string literal.
replacements = {
    '"Activos ahora"': 'clxDashboardText("dashboard.active_now")',
    '"GPS dentro"': 'clxDashboardText("dashboard.gps_inside")',
    '"Material entregado"': 'clxDashboardText("dashboard.material_delivered")',
    '"Stock bajo"': 'clxDashboardText("dashboard.low_stock")',
}

for old, new in replacements.items():
    text = text.replace(old, new)

path.write_text(text, encoding="utf-8")

print("PATCH_OK: 020D Dashboard native i18n applied")
