from pathlib import Path
import re

html_path = Path("app/web/client.html")
js_path = Path("app/web/client_inventory_i18n_safe.js")

html = html_path.read_text(encoding="utf-8-sig")

js = r'''
(function clonexaSafeInventoryI18n020FR1() {
  "use strict";

  if (window.__CLONEXA_020F_R1_INVENTORY_I18N__) return;
  window.__CLONEXA_020F_R1_INVENTORY_I18N__ = true;

  const LANG_KEY = "clonexa_client_language";

  const DICT = {
    es: {
      settings: "Ajustes",
      logout: "Cerrar sesión",

      moduleEyebrow: "Módulo Inventario",
      moduleTitle: "Inventario",
      moduleSubtitle: "Catálogo operativo, mínimos y stock actual de solo lectura. Materiales descontará o devolverá stock en la siguiente integración.",

      back: "Volver",
      refresh: "Actualizar",
      csv: "CSV",

      summary: "Resumen",
      inventoryStatus: "Estado del inventario",
      active: "Activo",
      activePlural: "Activos",
      inactive: "Inactivo",
      inactivePlural: "Inactivos",
      lowStock: "Stock bajo",
      totalRecords: "Total registros",

      createMaterialProduct: "Crear material / producto",
      modifyMaterial: "Modificar material",
      newInventoryRecord: "Nuevo registro de inventario",
      createHelp: "El stock actual se crea desde la cantidad inicial como movimiento. Luego solo cambia por entradas, entregas y devoluciones.",

      nameReference: "Nombre / referencia",
      size: "Tamaño",
      color: "Color",
      initialQuantity: "Cantidad inicial",
      minimumAlert: "Mínimo alerta",
      create: "Crear",

      modifyEyebrow: "Modificar material",
      searchUpdate: "Buscar y actualizar",
      modifyHelp: "El stock actual es solo lectura. Para sumar stock usa “Ingresar” y CLONEXA crea movimiento de inventario.",
      searchPlaceholder: "🔎 Buscar por nombre, referencia, tamaño o color...",

      currentStock: "Stock actual",
      alert: "Alerta",
      status: "Estado",
      enterQuantity: "Ingresar cantidad",
      quantity: "Cantidad",
      actions: "Acciones",

      save: "Guardar",
      enter: "Ingresar",
      disable: "Deshabilitar",

      noMaterials: "No hay materiales en inventario.",
      requiredName: "Nombre / referencia es obligatorio.",
      materialCreated: "Material creado en inventario.",
      materialUpdated: "Material actualizado.",
      quantityGreaterZero: "Ingresa una cantidad mayor a cero.",
      entryRegistered: "Entrada registrada. Stock actualizado.",
      materialDisabled: "Material deshabilitado.",

      exampleCable: "Ej: Cable UTP",
      exampleSize: "Ej: 20m / M / 1kg",
      exampleColor: "Ej: Azul"
    },

    en: {
      settings: "Settings",
      logout: "Log out",

      moduleEyebrow: "Inventory module",
      moduleTitle: "Inventory",
      moduleSubtitle: "Operational catalog, minimum levels and read-only current stock. Materials will deduct or return stock in the next integration.",

      back: "Back",
      refresh: "Refresh",
      csv: "CSV",

      summary: "Summary",
      inventoryStatus: "Inventory status",
      active: "Active",
      activePlural: "Active",
      inactive: "Inactive",
      inactivePlural: "Inactive",
      lowStock: "Low stock",
      totalRecords: "Total records",

      createMaterialProduct: "Create material / product",
      modifyMaterial: "Modify material",
      newInventoryRecord: "New inventory record",
      createHelp: "Current stock is created from the initial quantity as a movement. After that it only changes through entries, deliveries and returns.",

      nameReference: "Name / reference",
      size: "Size",
      color: "Color",
      initialQuantity: "Initial quantity",
      minimumAlert: "Minimum alert",
      create: "Create",

      modifyEyebrow: "Modify material",
      searchUpdate: "Search and update",
      modifyHelp: "Current stock is read-only. To add stock use “Enter” and CLONEXA will create an inventory movement.",
      searchPlaceholder: "🔎 Search by name, reference, size or color...",

      currentStock: "Current stock",
      alert: "Alert",
      status: "Status",
      enterQuantity: "Enter quantity",
      quantity: "Quantity",
      actions: "Actions",

      save: "Save",
      enter: "Enter",
      disable: "Disable",

      noMaterials: "There are no materials in inventory.",
      requiredName: "Name / reference is required.",
      materialCreated: "Material created in inventory.",
      materialUpdated: "Material updated.",
      quantityGreaterZero: "Enter a quantity greater than zero.",
      entryRegistered: "Entry registered. Stock updated.",
      materialDisabled: "Material disabled.",

      exampleCable: "E.g.: UTP cable",
      exampleSize: "E.g.: 20m / M / 1kg",
      exampleColor: "E.g.: Blue"
    },

    fr: {
      settings: "Configuration",
      logout: "Quitter",

      moduleEyebrow: "Module inventaire",
      moduleTitle: "Inventaire",
      moduleSubtitle: "Catalogue opérationnel, niveaux minimums et stock actuel en lecture seule. Les matériaux déduiront ou retourneront le stock lors de la prochaine intégration.",

      back: "Retour",
      refresh: "Actualiser",
      csv: "CSV",

      summary: "Résumé",
      inventoryStatus: "État de l’inventaire",
      active: "Actif",
      activePlural: "Actifs",
      inactive: "Inactif",
      inactivePlural: "Inactifs",
      lowStock: "Stock faible",
      totalRecords: "Total des enregistrements",

      createMaterialProduct: "Créer matériau / produit",
      modifyMaterial: "Modifier matériau",
      newInventoryRecord: "Nouvel enregistrement d’inventaire",
      createHelp: "Le stock actuel est créé à partir de la quantité initiale comme mouvement. Ensuite il ne change que par entrées, livraisons et retours.",

      nameReference: "Nom / référence",
      size: "Taille",
      color: "Couleur",
      initialQuantity: "Quantité initiale",
      minimumAlert: "Alerte minimum",
      create: "Créer",

      modifyEyebrow: "Modifier matériau",
      searchUpdate: "Rechercher et mettre à jour",
      modifyHelp: "Le stock actuel est en lecture seule. Pour ajouter du stock, utilisez “Entrer” et CLONEXA créera un mouvement d’inventaire.",
      searchPlaceholder: "🔎 Rechercher par nom, référence, taille ou couleur...",

      currentStock: "Stock actuel",
      alert: "Alerte",
      status: "Statut",
      enterQuantity: "Entrer quantité",
      quantity: "Quantité",
      actions: "Actions",

      save: "Enregistrer",
      enter: "Entrer",
      disable: "Désactiver",

      noMaterials: "Aucun matériau dans l’inventaire.",
      requiredName: "Nom / référence requis.",
      materialCreated: "Matériau créé dans l’inventaire.",
      materialUpdated: "Matériau mis à jour.",
      quantityGreaterZero: "Entrez une quantité supérieure à zéro.",
      entryRegistered: "Entrée enregistrée. Stock mis à jour.",
      materialDisabled: "Matériau désactivé.",

      exampleCable: "Ex. : câble UTP",
      exampleSize: "Ex. : 20m / M / 1kg",
      exampleColor: "Ex. : Bleu"
    }
  };

  const ALIASES = {};

  Object.keys(DICT).forEach((language) => {
    Object.keys(DICT[language]).forEach((key) => {
      ALIASES[norm(DICT[language][key])] = key;
    });
  });

  [
    ["Modulo Inventario", "moduleEyebrow"],
    ["Módulo Inventario", "moduleEyebrow"],
    ["MODULO INVENTARIO", "moduleEyebrow"],
    ["Inventario", "moduleTitle"],
    ["Catálogo operativo, mínimos y stock actual de solo lectura. Materiales descontará o devolverá stock en la siguiente integración.", "moduleSubtitle"],
    ["Catalogo operativo, minimos y stock actual de solo lectura. Materiales descontara o devolvera stock en la siguiente integracion.", "moduleSubtitle"],

    ["Volver", "back"],
    ["Actualizar", "refresh"],
    ["CSV", "csv"],

    ["Resumen", "summary"],
    ["Estado del inventario", "inventoryStatus"],
    ["Activo", "active"],
    ["Activos", "activePlural"],
    ["Inactivo", "inactive"],
    ["Inactivos", "inactivePlural"],
    ["Stock bajo", "lowStock"],
    ["Total registros", "totalRecords"],

    ["Crear material / producto", "createMaterialProduct"],
    ["Modificar material", "modifyMaterial"],
    ["Nuevo registro de inventario", "newInventoryRecord"],
    ["El stock actual se crea desde la cantidad inicial como movimiento. Luego solo cambia por entradas, entregas y devoluciones.", "createHelp"],

    ["Nombre / referencia", "nameReference"],
    ["Tamaño", "size"],
    ["Tamano", "size"],
    ["Color", "color"],
    ["Cantidad inicial", "initialQuantity"],
    ["Mínimo alerta", "minimumAlert"],
    ["Minimo alerta", "minimumAlert"],
    ["Crear", "create"],

    ["Buscar y actualizar", "searchUpdate"],
    ["El stock actual es solo lectura. Para sumar stock usa “Ingresar” y CLONEXA crea movimiento de inventario.", "modifyHelp"],
    ["El stock actual es solo lectura. Para sumar stock usa \"Ingresar\" y CLONEXA crea movimiento de inventario.", "modifyHelp"],
    ["🔎 Buscar por nombre, referencia, tamaño o color...", "searchPlaceholder"],
    ["Buscar por nombre, referencia, tamaño o color...", "searchPlaceholder"],

    ["Stock actual", "currentStock"],
    ["Alerta", "alert"],
    ["Estado", "status"],
    ["Ingresar cantidad", "enterQuantity"],
    ["Cantidad", "quantity"],
    ["Acciones", "actions"],

    ["Guardar", "save"],
    ["Ingresar", "enter"],
    ["Deshabilitar", "disable"],

    ["No hay materiales en inventario.", "noMaterials"],
    ["Nombre / referencia es obligatorio.", "requiredName"],
    ["Material creado en inventario.", "materialCreated"],
    ["Material actualizado.", "materialUpdated"],
    ["Ingresa una cantidad mayor a cero.", "quantityGreaterZero"],
    ["Entrada registrada. Stock actualizado.", "entryRegistered"],
    ["Material deshabilitado.", "materialDisabled"],

    ["Ej: Cable UTP", "exampleCable"],
    ["Ej: 20m / M / 1kg", "exampleSize"],
    ["Ej: Azul", "exampleColor"],

    ["Ajustes", "settings"],
    ["Cerrar sesión", "logout"],
    ["Cerrar sesion", "logout"]
  ].forEach(([text, key]) => {
    ALIASES[norm(text)] = key;
  });

  function lang() {
    const value = String(localStorage.getItem(LANG_KEY) || "es").toLowerCase();
    return ["es", "en", "fr"].includes(value) ? value : "es";
  }

  function norm(value) {
    return String(value || "")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();
  }

  function t(key) {
    return (DICT[lang()] && DICT[lang()][key]) || DICT.es[key] || key;
  }

  function shouldSkipText(value) {
    const raw = String(value || "").trim();
    if (!raw) return true;
    if (/^[\d\s.,:$%#@/_-]+$/.test(raw)) return true;
    if (raw.includes("@")) return true;
    if (/^[a-f0-9-]{20,}$/i.test(raw)) return true;
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

  function isInventoryVisible() {
    const app = document.getElementById("app");
    if (!app) return false;

    if (app.querySelector(".cx-inv-form")) return true;
    if (app.querySelector(".cx-inv-table")) return true;
    if (app.querySelector("[data-inventory-create]")) return true;
    if (app.querySelector("[data-inventory-mode]")) return true;
    if (app.querySelector("[data-inventory-search]")) return true;

    const text = app.textContent || "";
    return (
      text.includes("Modulo Inventario") ||
      text.includes("Módulo Inventario") ||
      text.includes("Inventory module") ||
      text.includes("Module inventaire") ||
      text.includes("Estado del inventario") ||
      text.includes("Inventory status") ||
      text.includes("État de l’inventaire")
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

  function translateInventory() {
    try {
      if (!isInventoryVisible()) return;

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
      console.warn("CLONEXA inventory i18n skipped:", error);
    }
  }

  let timer = null;

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(translateInventory, 140);
  }

  function burst() {
    let count = 0;
    const id = setInterval(() => {
      count += 1;
      translateInventory();
      if (count >= 8) clearInterval(id);
    }, 220);
  }

  document.addEventListener("click", () => {
    schedule();
    setTimeout(schedule, 450);
    setTimeout(schedule, 1000);
  }, true);

  document.addEventListener("input", schedule, true);
  document.addEventListener("change", schedule, true);

  const observer = new MutationObserver(schedule);

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
      console.warn("CLONEXA inventory i18n init skipped:", error);
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

# Quitar versiones previas del script
html = re.sub(
    r'\s*<script[^>]+src=["\'][^"\']*client_inventory_i18n_safe\.js[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE,
)

# Insertar después de dashboard_i18n_safe si existe; si no, después de core_settings
dashboard_matches = list(re.finditer(
    r'<script[^>]+src=["\']([^"\']*client_dashboard_i18n_safe\.js[^"\']*)["\'][^>]*>\s*</script>',
    html,
    flags=re.IGNORECASE,
))

if dashboard_matches:
    last = dashboard_matches[-1]
    src = last.group(1)
    safe_src = re.sub(r'client_dashboard_i18n_safe\.js(?:\?v=[^"\']*)?', 'client_inventory_i18n_safe.js?v=020FR1', src)
    html = html[:last.end()] + f'\n<script src="{safe_src}"></script>\n' + html[last.end():]
else:
    core_matches = list(re.finditer(
        r'<script[^>]+src=["\']([^"\']*client_core_settings\.js[^"\']*)["\'][^>]*>\s*</script>',
        html,
        flags=re.IGNORECASE,
    ))
    if core_matches:
        last = core_matches[-1]
        src = last.group(1)
        safe_src = re.sub(r'client_core_settings\.js(?:\?v=[^"\']*)?', 'client_inventory_i18n_safe.js?v=020FR1', src)
        html = html[:last.end()] + f'\n<script src="{safe_src}"></script>\n' + html[last.end():]
    else:
        html = html.replace("</body>", '<script src="/client-static/client_inventory_i18n_safe.js?v=020FR1"></script>\n</body>')

html_path.write_text(html, encoding="utf-8")

print("PATCH_OK: 020F-R1 safe external inventory i18n added")
