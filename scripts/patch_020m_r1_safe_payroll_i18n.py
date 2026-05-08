from pathlib import Path
import re

html_path = Path("app/web/client.html")
js_path = Path("app/web/client_payroll_i18n_safe.js")

html = html_path.read_text(encoding="utf-8-sig")

js = r'''
(function clonexaSafePayrollI18n020MR1() {
  "use strict";

  if (window.__CLONEXA_020M_R1_PAYROLL_I18N__) return;
  window.__CLONEXA_020M_R1_PAYROLL_I18N__ = true;

  const LANG_KEY = "clonexa_client_language";

  const ENTRIES = {
    settings: { es:"Ajustes", en:"Settings", fr:"Configuration", aliases:["Ajustes","Settings","Configuration"] },
    logout: { es:"Cerrar sesión", en:"Log out", fr:"Quitter", aliases:["Cerrar sesión","Cerrar sesion","Log out","Quitter"] },

    activeTenant: { es:"Tenant activo", en:"Active tenant", fr:"Tenant actif", aliases:["Tenant activo","Active tenant","Tenant actif"] },

    moduleEyebrow: {
      es:"Módulo Nómina",
      en:"Payroll module",
      fr:"Module paie",
      aliases:["Modulo Nómina","Modulo Nomina","Módulo Nómina","MÓDULO NÓMINA","MODULO NOMINA","Payroll module","PAYROLL MODULE"]
    },
    moduleTitle: {
      es:"Nómina",
      en:"Payroll",
      fr:"Paie",
      aliases:["Nómina","Nomina","Payroll","PAYROLL","Paie"]
    },
    moduleSubtitle: {
      es:"Consulta cortes por periodo y conserva el resultado exportando CSV.",
      en:"Review cutoffs by period and keep the result by exporting CSV.",
      fr:"Consultez les clôtures par période et conservez le résultat en exportant CSV.",
      aliases:[
        "Consulta cortes por periodo y conserva el resultado exportando CSV.",
        "Review cutoffs by period and keep the result by exporting CSV."
      ]
    },

    back:{ es:"Volver", en:"Back", fr:"Retour", aliases:["Volver","Back","Retour"] },
    refresh:{ es:"Actualizar", en:"Refresh", fr:"Actualiser", aliases:["Actualizar","Refresh","Actualiser"] },
    csv:{ es:"CSV", en:"CSV", fr:"CSV", aliases:["CSV"] },
    exportCsv:{ es:"Exportar CSV", en:"Export CSV", fr:"Exporter CSV", aliases:["Exportar CSV","Export CSV","Exporter CSV"] },

    period:{ es:"Periodo", en:"Period", fr:"Période", aliases:["Periodo","PERIODO","PERÍODO","Period","PERIOD"] },
    payrollSummary:{ es:"Resumen de nómina", en:"Payroll summary", fr:"Résumé de paie", aliases:["Resumen de nómina","Resumen de nomina","Payroll summary"] },
    payrollHelp:{
      es:"Nómina consume Workforce, Bot y Asistencia. Al finalizar un corte, exporta CSV para guardar el histórico externo del periodo.",
      en:"Payroll uses Workforce, Bot and Attendance. At the end of a cutoff, export CSV to keep the external history for the period.",
      fr:"La paie utilise Workforce, Bot et Assistance. À la fin d’une clôture, exportez CSV pour conserver l’historique externe de la période.",
      aliases:[
        "Nómina consume Workforce, Bot y Asistencia. Al finalizar un corte, exporta CSV para guardar el histórico externo del periodo.",
        "Nomina consume Workforce, Bot y Asistencia. Al finalizar un corte, exporta CSV para guardar el historico externo del periodo.",
        "Payroll uses Workforce, Bot and Attendance. At the end of a cutoff, export CSV to keep the external history for the period."
      ]
    },

    from:{ es:"Desde", en:"From", fr:"De", aliases:["Desde","DESDE","From","FROM"] },
    to:{ es:"Hasta", en:"To", fr:"À", aliases:["Hasta","HASTA","To","TO"] },
    calculatePeriod:{ es:"Calcular periodo", en:"Calculate period", fr:"Calculer la période", aliases:["Calcular periodo","Calculate period"] },

    open:{ es:"Abierto", en:"Open", fr:"Ouvert", aliases:["abierto","Abierto","ABIERTO","open","Open"] },
    closed:{ es:"Cerrado", en:"Closed", fr:"Clôturé", aliases:["cerrado","Cerrado","CERRADO","closed","Closed"] },
    calculated:{ es:"Calculado", en:"Calculated", fr:"Calculé", aliases:["calculado","Calculado","Calculated"] },
    draft:{ es:"Borrador", en:"Draft", fr:"Brouillon", aliases:["borrador","Borrador","Draft"] },

    collaborators:{ es:"Colaboradores", en:"Collaborators", fr:"Collaborateurs", aliases:["Colaboradores","Collaborators"] },
    collaboratorsCount:{ es:"Colaboradores", en:"Collaborators", fr:"Collaborateurs", aliases:["COLABORADORES","Collaborators"] },
    closedShifts:{ es:"Turnos cerrados", en:"Closed shifts", fr:"Services clôturés", aliases:["Turnos cerrados","TURNOS CERRADOS","Closed shifts"] },
    regularHours:{ es:"Horas ordinarias", en:"Regular hours", fr:"Heures normales", aliases:["Horas ordinarias","HORAS ORDINARIAS","Regular hours","REGULAR HOURS"] },
    extraHours:{ es:"Horas extra", en:"Extra hours", fr:"Heures supplémentaires", aliases:["Horas extra","HORAS EXTRA","Extra hours","EXTRA HOURS"] },
    estimatedNetTotal:{ es:"Total neto estimado", en:"Estimated net total", fr:"Total net estimé", aliases:["Total neto estimado","TOTAL NETO ESTIMADO","Estimated net total"] },

    detailByCollaborator:{ es:"Detalle por colaborador", en:"Detail by collaborator", fr:"Détail par collaborateur", aliases:["Detalle por colaborador","Detail by collaborator"] },
    calculatedPeriod:{ es:"Periodo calculado", en:"Calculated period", fr:"Période calculée", aliases:["Periodo calculado","Calculated period"] },

    cutoffClosing:{ es:"Cierre del corte", en:"Cutoff closing", fr:"Clôture de la période", aliases:["Cierre del corte","Cutoff closing"] },
    exportation:{ es:"Exportación", en:"Export", fr:"Exportation", aliases:["Exportación","Exportacion","Export"] },

    collaborator:{ es:"Colaborador", en:"Collaborator", fr:"Collaborateur", aliases:["Colaborador","COLABORADOR","Collaborator"] },
    employee:{ es:"Empleado", en:"Employee", fr:"Employé", aliases:["Empleado","Employee"] },
    role:{ es:"Rol", en:"Role", fr:"Rôle", aliases:["Rol","Role"] },
    shifts:{ es:"Turnos", en:"Shifts", fr:"Services", aliases:["Turnos","Shifts"] },
    regular:{ es:"Ordinarias", en:"Regular", fr:"Normales", aliases:["Ordinarias","ORDINARIAS","Regular"] },
    extras:{ es:"Extras", en:"Extra", fr:"Supplémentaires", aliases:["Extras","EXTRAS","Extra"] },
    gross:{ es:"Bruto", en:"Gross", fr:"Brut", aliases:["Bruto","BRUTO","Gross","GROSS"] },
    cutoffDiscount:{ es:"Descuento corte", en:"Cutoff discount", fr:"Remise de clôture", aliases:["Descuento corte","DESCUENTO CORTE","Cutoff discount"] },
    estimatedTotal:{ es:"Total estimado", en:"Estimated total", fr:"Total estimé", aliases:["Total estimado","TOTAL ESTIMADO","Estimated total"] },
    netTotal:{ es:"Total neto", en:"Net total", fr:"Total net", aliases:["Total neto","Net total"] },
    discount:{ es:"Descuento", en:"Discount", fr:"Remise", aliases:["Descuento","Discount"] },

    company:{ es:"Empresa", en:"Company", fr:"Entreprise", aliases:["Empresa","Company"] },
    mode:{ es:"Modo", en:"Mode", fr:"Mode", aliases:["Modo","Mode"] },

    noPayrollData:{ es:"Sin datos de nómina para el periodo.", en:"No payroll data for the period.", fr:"Aucune donnée de paie pour la période.", aliases:["Sin datos de nómina para el periodo.","Sin datos de nomina para el periodo.","No payroll data for the period."] },
    noRows:{ es:"No hay colaboradores con corte calculado.", en:"No collaborators with calculated cutoff.", fr:"Aucun collaborateur avec clôture calculée.", aliases:["No hay colaboradores con corte calculado.","No collaborators with calculated cutoff."] },

    exportOnlyTitle:{ es:"Exporta el corte para conservar histórico.", en:"Export the cutoff to keep history.", fr:"Exportez la clôture pour conserver l’historique.", aliases:["Exporta el corte para conservar histórico.","Exporta el corte para conservar historico.","Export the cutoff to keep history."] },
    exportOnlyHelp:{
      es:"CLONEXA calcula el periodo en vivo. Para cerrar administrativamente, exporta CSV y conserva el archivo externo del corte.",
      en:"CLONEXA calculates the period live. To close administratively, export CSV and keep the external cutoff file.",
      fr:"CLONEXA calcule la période en direct. Pour clôturer administrativement, exportez CSV et conservez le fichier externe de clôture.",
      aliases:[
        "CLONEXA calcula el periodo en vivo. Para cerrar administrativamente, exporta CSV y conserva el archivo externo del corte.",
        "CLONEXA calculates the period live. To close administratively, export CSV and keep the external cutoff file."
      ]
    },

    loadError:{ es:"No se pudo cargar nómina.", en:"Could not load payroll.", fr:"Impossible de charger la paie.", aliases:["No se pudo cargar nómina.","No se pudo cargar nomina.","Could not load payroll."] },
    exportError:{ es:"No se pudo exportar CSV.", en:"Could not export CSV.", fr:"Impossible d’exporter CSV.", aliases:["No se pudo exportar CSV.","Could not export CSV."] },

    workforce:{ es:"Workforce", en:"Workforce", fr:"Workforce", aliases:["Workforce"] },
    bot:{ es:"Bot", en:"Bot", fr:"Bot", aliases:["Bot"] },
    attendance:{ es:"Asistencia", en:"Attendance", fr:"Assistance", aliases:["Asistencia","Attendance"] },
    history:{ es:"Histórico", en:"History", fr:"Historique", aliases:["Histórico","Historico","History"] }
  };

  const ALIASES = {};

  function norm(value) {
    return String(value || "")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();
  }

  function addAlias(text, key) {
    if (!text) return;
    ALIASES[norm(text)] = key;
    ALIASES[norm(String(text).toUpperCase())] = key;
  }

  Object.keys(ENTRIES).forEach((key) => {
    const entry = ENTRIES[key];
    addAlias(entry.es, key);
    addAlias(entry.en, key);
    addAlias(entry.fr, key);
    (entry.aliases || []).forEach((alias) => addAlias(alias, key));
  });

  function lang() {
    const value = String(localStorage.getItem(LANG_KEY) || "es").toLowerCase();
    return ["es", "en", "fr"].includes(value) ? value : "es";
  }

  function t(key) {
    const entry = ENTRIES[key];
    return entry ? entry[lang()] || entry.es || key : key;
  }

  function shouldSkipText(value) {
    const raw = String(value || "").trim();
    if (!raw) return true;
    if (/^[\d\s.,:$%#@/_-]+$/.test(raw)) return true;
    if (/^[a-f0-9-]{20,}$/i.test(raw)) return true;
    if (raw.includes("@")) return true;
    if (/^\d{4}-\d{2}-\d{2}/.test(raw)) return true;
    if (/^\d{1,2}:\d{2}/.test(raw)) return true;
    if (/^\$?\d+([.,]\d+)?(\s?[A-Z]{2,4})?$/.test(raw)) return true;
    return false;
  }

  function translateText(value) {
    const raw = String(value || "");
    const clean = raw.replace(/\s+/g, " ").trim();

    if (shouldSkipText(clean)) return raw;

    const key = ALIASES[norm(clean)];
    if (!key) return raw;

    return raw.replace(clean, t(key));
  }

  function isPayrollVisible() {
    const app = document.getElementById("app");
    if (!app) return false;

    if (app.querySelector("[data-payroll-from]")) return true;
    if (app.querySelector("[data-payroll-to]")) return true;
    if (app.querySelector("[data-payroll-apply]")) return true;
    if (app.querySelector("[data-payroll-refresh]")) return true;
    if (app.querySelector("[data-payroll-export]")) return true;
    if (app.querySelector(".cx-payroll-filters")) return true;
    if (app.querySelector(".cx-payroll-status")) return true;
    if (app.querySelector(".cx-payroll-table")) return true;

    const text = app.textContent || "";
    return (
      text.includes("Modulo Nómina") ||
      text.includes("Modulo Nomina") ||
      text.includes("Módulo Nómina") ||
      text.includes("Payroll module") ||
      text.includes("Resumen de nómina") ||
      text.includes("Payroll summary") ||
      text.includes("Detalle por colaborador") ||
      text.includes("Detail by collaborator")
    );
  }

  function skipElement(el) {
    if (!el || !el.tagName) return true;
    const tag = el.tagName.toLowerCase();
    if (["script", "style", "code", "pre"].includes(tag)) return true;
    if (el.closest && el.closest("[data-clx-no-i18n]")) return true;
    return false;
  }

  function translateAttributes(base) {
    base.querySelectorAll("[placeholder], [title], [aria-label], input[type='button'], input[type='submit']").forEach((el) => {
      if (skipElement(el)) return;

      ["placeholder", "title", "aria-label"].forEach((attr) => {
        if (!el.hasAttribute(attr)) return;
        const current = el.getAttribute(attr);
        const next = translateText(current);
        if (next !== current) el.setAttribute(attr, next);
      });

      if (el.matches("input[type='button'], input[type='submit']")) {
        const next = translateText(el.value);
        if (next !== el.value) el.value = next;
      }
    });
  }

  function translatePayroll() {
    try {
      if (!isPayrollVisible()) return;

      const app = document.getElementById("app");
      if (!app) return;

      const walker = document.createTreeWalker(app, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
          const parent = node.parentElement;
          if (!parent || skipElement(parent)) return NodeFilter.FILTER_REJECT;
          return NodeFilter.FILTER_ACCEPT;
        }
      });

      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);

      nodes.forEach((node) => {
        const next = translateText(node.nodeValue);
        if (next !== node.nodeValue) node.nodeValue = next;
      });

      translateAttributes(app);

      const settings = document.getElementById("clxOpenCoreSettings");
      const logout = document.getElementById("clxCoreLogout");

      if (settings) settings.textContent = `⚙ ${t("settings")}`;
      if (logout) logout.textContent = `⏻ ${t("logout")}`;

      document.documentElement.lang = lang();
    } catch (error) {
      console.warn("CLONEXA Payroll i18n skipped:", error);
    }
  }

  let timer = null;

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(translatePayroll, 100);
  }

  function burst() {
    let count = 0;
    const id = setInterval(() => {
      count += 1;
      translatePayroll();
      if (count >= 18) clearInterval(id);
    }, 170);
  }

  document.addEventListener("click", () => {
    schedule();
    setTimeout(schedule, 300);
    setTimeout(schedule, 750);
    setTimeout(schedule, 1300);
    setTimeout(schedule, 2200);
  }, true);

  document.addEventListener("input", schedule, true);
  document.addEventListener("change", schedule, true);
  document.addEventListener("keydown", schedule, true);

  const observer = new MutationObserver(schedule);

  setInterval(() => {
    if (isPayrollVisible()) translatePayroll();
  }, 1500);

  function init() {
    try {
      if (document.body) {
        observer.observe(document.body, {
          childList: true,
          subtree: true
        });
      }
      schedule();
      burst();
    } catch (error) {
      console.warn("CLONEXA Payroll i18n init skipped:", error);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
'''

js_path.write_text(js, encoding="utf-8")

html = re.sub(
    r'\s*<script[^>]+src=["\'][^"\']*client_payroll_i18n_safe\.js[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE,
)

materials_matches = list(re.finditer(
    r'<script[^>]+src=["\']([^"\']*client_materials_i18n_safe\.js[^"\']*)["\'][^>]*>\s*</script>',
    html,
    flags=re.IGNORECASE,
))

if materials_matches:
    last = materials_matches[-1]
    src = last.group(1)
    safe_src = re.sub(r'client_materials_i18n_safe\.js(?:\?v=[^"\']*)?', 'client_payroll_i18n_safe.js?v=020MR1', src)
    html = html[:last.end()] + f'\n<script src="{safe_src}"></script>\n' + html[last.end():]
else:
    kpis_matches = list(re.finditer(
        r'<script[^>]+src=["\']([^"\']*client_kpis_i18n_safe\.js[^"\']*)["\'][^>]*>\s*</script>',
        html,
        flags=re.IGNORECASE,
    ))
    if kpis_matches:
        last = kpis_matches[-1]
        src = last.group(1)
        safe_src = re.sub(r'client_kpis_i18n_safe\.js(?:\?v=[^"\']*)?', 'client_payroll_i18n_safe.js?v=020MR1', src)
        html = html[:last.end()] + f'\n<script src="{safe_src}"></script>\n' + html[last.end():]
    else:
        html = html.replace("</body>", '<script src="/client-static/client_payroll_i18n_safe.js?v=020MR1"></script>\n</body>')

html_path.write_text(html, encoding="utf-8")

print("PATCH_OK: 020M-R1 safe external Payroll i18n super dictionary added")
