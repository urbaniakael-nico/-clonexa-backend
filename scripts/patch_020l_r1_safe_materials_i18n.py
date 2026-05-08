from pathlib import Path
import re

html_path = Path("app/web/client.html")
js_path = Path("app/web/client_materials_i18n_safe.js")

html = html_path.read_text(encoding="utf-8-sig")

js = r'''
(function clonexaSafeMaterialsI18n020LR1() {
  "use strict";

  if (window.__CLONEXA_020L_R1_MATERIALS_I18N__) return;
  window.__CLONEXA_020L_R1_MATERIALS_I18N__ = true;

  const LANG_KEY = "clonexa_client_language";

  const ENTRIES = {
    settings: { es:"Ajustes", en:"Settings", fr:"Configuration", aliases:["Ajustes","Settings","Configuration"] },
    logout: { es:"Cerrar sesión", en:"Log out", fr:"Quitter", aliases:["Cerrar sesión","Cerrar sesion","Log out","Quitter"] },

    moduleEyebrow: {
      es:"Módulo Materiales",
      en:"Materials module",
      fr:"Module matériaux",
      aliases:["Modulo Materiales","Módulo Materiales","MATERIALS MODULE","Materials module"]
    },
    moduleTitle: {
      es:"Materiales",
      en:"Materials",
      fr:"Matériaux",
      aliases:["Materiales","Materials","MATERIALS","Matériaux"]
    },
    moduleSubtitle: {
      es:"Órdenes de salida conectadas a Inventario. Entregar descuenta stock; devolver exige número de orden.",
      en:"Outbound orders connected to Inventory. Delivery deducts stock; returns require an order number.",
      fr:"Ordres de sortie connectés à l’inventaire. La livraison déduit le stock; le retour exige un numéro de commande.",
      aliases:[
        "Órdenes de salida conectadas a Inventario. Entregar descuenta stock; devolver exige número de orden.",
        "Ordenes de salida conectadas a Inventario. Entregar descuenta stock; devolver exige numero de orden.",
        "Outbound orders connected to Inventory. Delivery deducts stock; returns require an order number."
      ]
    },

    back:{ es:"Volver", en:"Back", fr:"Retour", aliases:["Volver","Back","Retour"] },
    refresh:{ es:"Actualizar", en:"Refresh", fr:"Actualiser", aliases:["Actualizar","Refresh","Actualiser"] },
    csv:{ es:"CSV", en:"CSV", fr:"CSV", aliases:["CSV"] },

    operationalCycle:{ es:"Ciclo operativo", en:"Operating cycle", fr:"Cycle opérationnel", aliases:["Ciclo operativo","Operating cycle"] },
    materialOrders:{ es:"Órdenes de materiales", en:"Material orders", fr:"Commandes de matériaux", aliases:["Órdenes de materiales","Ordenes de materiales","Material orders"] },

    pendingPlural:{ es:"Pendientes", en:"Pending", fr:"En attente", aliases:["Pendientes","Pending","PENDING"] },
    approvedPlural:{ es:"Aprobadas", en:"Approved", fr:"Approuvées", aliases:["Aprobadas","Approved","APPROVED"] },
    deliveredPlural:{ es:"Entregadas", en:"Delivered", fr:"Livrées", aliases:["Entregadas","Delivered","DELIVERED"] },
    consignment:{ es:"Consigna", en:"Consignment", fr:"Consigne", aliases:["Consigna","Consignment"] },
    returnedPlural:{ es:"Devueltas", en:"Returned", fr:"Retournées", aliases:["Devueltas","Returned","RETURNED"] },

    order:{ es:"Orden", en:"Order", fr:"Commande", aliases:["ORDEN","Orden","ORDER","Order"] },
    requester:{ es:"Solicitante", en:"Requester", fr:"Demandeur", aliases:["SOLICITANTE","Solicitante","REQUESTER","Requester"] },
    material:{ es:"Material", en:"Material", fr:"Matériau", aliases:["MATERIAL","Material"] },
    quantity:{ es:"Cantidad", en:"Quantity", fr:"Quantité", aliases:["CANTIDAD","Cantidad","QUANTITY","Quantity"] },
    status:{ es:"Estado", en:"Status", fr:"Statut", aliases:["STATUS","Status","ESTADO","Estado"] },
    destination:{ es:"Destino", en:"Destination", fr:"Destination", aliases:["DESTINO","Destino","DESTINATION","Destination"] },
    actions:{ es:"Acciones", en:"Actions", fr:"Actions", aliases:["ACTIONS","Actions","ACCIONES","Acciones"] },

    approve:{ es:"Aprobar", en:"Approve", fr:"Approuver", aliases:["Aprobar","Approve","Approuver"] },
    deliver:{ es:"Entregar", en:"Deliver", fr:"Livrer", aliases:["Entregar","Deliver","Livrer"] },
    reject:{ es:"Rechazar", en:"Reject", fr:"Rejeter", aliases:["Rechazar","Reject","Rejeter"] },
    detail:{ es:"Detalle", en:"Detail", fr:"Détail", aliases:["Detalle","Detail","Détail"] },
    consign:{ es:"Consigna", en:"Consign", fr:"Consigner", aliases:["Consignar","Consigna","Consign","Consigner"] },
    returnAction:{ es:"Devolución", en:"Return", fr:"Retour", aliases:["Devolución","Devolucion","Return","Retour"] },

    statusPending:{ es:"Pendiente", en:"Pending", fr:"En attente", aliases:["Pendiente","pending","Pending"] },
    statusApproved:{ es:"Aprobada", en:"Approved", fr:"Approuvée", aliases:["Aprobada","approved","Approved"] },
    statusRejected:{ es:"Rechazada", en:"Rejected", fr:"Rejetée", aliases:["Rechazada","rejected","Rejected"] },
    statusDelivered:{ es:"Entregada", en:"Delivered", fr:"Livrée", aliases:["Entregada","delivered","Delivered"] },
    statusConsignedTotal:{ es:"Consignada total", en:"Fully consigned", fr:"Consignée totale", aliases:["Consignada total","consigned","Fully consigned"] },
    statusConsignedPartial:{ es:"Consignada parcial", en:"Partially consigned", fr:"Consignée partielle", aliases:["Consignada parcial","consigned_partial","Partially consigned"] },
    statusReturnedTotal:{ es:"Devuelta total", en:"Fully returned", fr:"Retournée totale", aliases:["Devuelta total","returned","Fully returned"] },
    statusReturnedPartial:{ es:"Devuelta parcial", en:"Partially returned", fr:"Retournée partielle", aliases:["Devuelta parcial","returned_partial","Partially returned"] },
    statusCancelled:{ es:"Cancelada", en:"Cancelled", fr:"Annulée", aliases:["Cancelada","cancelled","Cancelled"] },

    noOrder:{ es:"Sin orden", en:"No order", fr:"Sans commande", aliases:["Sin orden","No order"] },
    collaborator:{ es:"Colaborador", en:"Collaborator", fr:"Collaborateur", aliases:["Colaborador","Collaborator"] },

    outputManagement:{ es:"Gestión de salida", en:"Outbound management", fr:"Gestion de sortie", aliases:["Gestión de salida","Gestion de salida","Outbound management"] },
    registerReturnByOrder:{ es:"Registrar devolución por número de orden", en:"Register return by order number", fr:"Enregistrer un retour par numéro de commande", aliases:["Registrar devolución por número de orden","Registrar devolucion por numero de orden","Register return by order number"] },
    returnHelper:{
      es:"Busca la orden de salida, despliega sus materiales y marca los Label/SKU que vuelven al inventario.",
      en:"Search the outbound order, expand its materials and check the Label/SKU items returning to inventory.",
      fr:"Recherchez l’ordre de sortie, affichez ses matériaux et cochez les Label/SKU qui reviennent à l’inventaire.",
      aliases:[
        "Busca la orden de salida, despliega sus materiales y marca los Label/SKU que vuelven al inventario.",
        "Search the outbound order, expand its materials and check the Label/SKU items returning to inventory."
      ]
    },
    orderNumber:{ es:"Número de orden", en:"Order number", fr:"Numéro de commande", aliases:["Número de orden","Numero de orden","Order number"] },
    operationalObservation:{ es:"Observación operativa", en:"Operational observation", fr:"Observation opérationnelle", aliases:["Observación operativa","Observacion operativa","Operational observation"] },
    searchMatPlaceholder:{ es:"Busca MAT-20260506-000003", en:"Search MAT-20260506-000003", fr:"Rechercher MAT-20260506-000003", aliases:["Busca MAT-20260506-000003","Search MAT-20260506-000003"] },
    reasonPlaceholder:{ es:"Motivo / estado del material", en:"Reason / material condition", fr:"Motif / état du matériau", aliases:["Motivo / estado del material","Reason / material condition"] },
    registerReturn:{ es:"Registrar devolución", en:"Register return", fr:"Enregistrer le retour", aliases:["Registrar devolución","Registrar devolucion","Register return"] },

    registerConsignment:{ es:"Registrar consigna por número de orden", en:"Register consignment by order number", fr:"Enregistrer une consigne par numéro de commande", aliases:["Registrar consigna por número de orden","Register consignment by order number"] },
    consignmentHelper:{
      es:"Busca la orden de salida, despliega sus materiales y marca los Label/SKU que quedan en consigna.",
      en:"Search the outbound order, expand its materials and check the Label/SKU items kept in consignment.",
      fr:"Recherchez l’ordre de sortie, affichez ses matériaux et cochez les Label/SKU conservés en consigne.",
      aliases:["Busca la orden de salida, despliega sus materiales y marca los Label/SKU que quedan en consigna.","Search the outbound order, expand its materials and check the Label/SKU items kept in consignment."]
    },
    registerConsign:{ es:"Registrar consigna", en:"Register consignment", fr:"Enregistrer la consigne", aliases:["Registrar consigna","Register consignment"] },

    selectOrder:{ es:"Selecciona una orden", en:"Select an order", fr:"Sélectionnez une commande", aliases:["Selecciona una orden","Select an order"] },
    selectMaterials:{ es:"Selecciona materiales", en:"Select materials", fr:"Sélectionnez les matériaux", aliases:["Selecciona materiales","Select materials"] },
    labelsSkus:{ es:"Labels/SKU", en:"Labels/SKU", fr:"Labels/SKU", aliases:["Labels/SKU","Label/SKU"] },
    units:{ es:"Unidades", en:"Units", fr:"Unités", aliases:["Unidades","Units"] },
    selected:{ es:"Seleccionados", en:"Selected", fr:"Sélectionnés", aliases:["Seleccionados","Selected"] },

    orderApprovedNotice:{ es:"Orden aprobada. Ya puedes entregarla.", en:"Order approved. You can now deliver it.", fr:"Commande approuvée. Vous pouvez maintenant la livrer.", aliases:["Orden aprobada. Ya puedes entregarla.","Order approved. You can now deliver it."] },
    orderDeliveredNotice:{ es:"Orden entregada. Inventario descontado.", en:"Order delivered. Inventory deducted.", fr:"Commande livrée. Inventaire déduit.", aliases:["Orden entregada. Inventario descontado.","Order delivered. Inventory deducted."] },
    orderRejectedNotice:{ es:"Orden rechazada.", en:"Order rejected.", fr:"Commande rejetée.", aliases:["Orden rechazada.","Order rejected."] },
    returnRegisteredNotice:{ es:"Devolución registrada. Inventario actualizado.", en:"Return registered. Inventory updated.", fr:"Retour enregistré. Inventaire mis à jour.", aliases:["Devolución registrada. Inventario actualizado.","Devolucion registrada. Inventario actualizado.","Return registered. Inventory updated."] },
    consignRegisteredNotice:{ es:"Consigna registrada. Inventario no se movió.", en:"Consignment registered. Inventory was not moved.", fr:"Consigne enregistrée. L’inventaire n’a pas bougé.", aliases:["Consigna registrada. Inventario no se movió.","Consigna registrada. Inventario no se movio.","Consignment registered. Inventory was not moved."] },
    cleanupNotice:{ es:"Depuración lista. Órdenes ocultas:", en:"Cleanup ready. Hidden orders:", fr:"Nettoyage prêt. Commandes masquées :", aliases:["Depuración lista. Órdenes ocultas:","Depuracion lista. Ordenes ocultas:","Cleanup ready. Hidden orders:"] },

    noRequests:{ es:"No hay órdenes de materiales.", en:"There are no material orders.", fr:"Aucune commande de matériaux.", aliases:["No hay órdenes de materiales.","No hay ordenes de materiales.","There are no material orders."] },
    noResults:{ es:"Sin resultados.", en:"No results.", fr:"Aucun résultat.", aliases:["Sin resultados.","No results."] },
    noMaterials:{ es:"Sin materiales.", en:"No materials.", fr:"Aucun matériau.", aliases:["Sin materiales.","No materials."] },

    inventory:{ es:"Inventario", en:"Inventory", fr:"Inventaire", aliases:["Inventario","Inventory"] },
    stock:{ es:"Stock", en:"Stock", fr:"Stock", aliases:["Stock"] },
    history:{ es:"Historial", en:"History", fr:"Historique", aliases:["Historial","History"] },
    notes:{ es:"Notas", en:"Notes", fr:"Notes", aliases:["Notas","Notes"] },
    size:{ es:"Tamaño", en:"Size", fr:"Taille", aliases:["Tamaño","Tamano","Size"] },
    color:{ es:"Color", en:"Color", fr:"Couleur", aliases:["Color","Couleur"] },
    employee:{ es:"Empleado", en:"Employee", fr:"Employé", aliases:["Empleado","Employee"] },
    role:{ es:"Rol", en:"Role", fr:"Rôle", aliases:["Rol","Role"] },
    requestedAt:{ es:"Solicitada", en:"Requested", fr:"Demandée", aliases:["Solicitada","Requested"] },
    deliveredAt:{ es:"Entregada", en:"Delivered", fr:"Livrée", aliases:["Entregada","Delivered"] },
    updatedAt:{ es:"Actualizada", en:"Updated", fr:"Mise à jour", aliases:["Actualizada","Updated"] },

    loadError:{ es:"No se pudo cargar Materiales.", en:"Could not load Materials.", fr:"Impossible de charger les matériaux.", aliases:["No se pudo cargar Materiales.","Could not load Materials."] }
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
    if (/^MAT-\d{8}-\d+$/i.test(raw)) return true;
    if (/^[A-Z0-9_-]{5,}$/.test(raw) && !ALIASES[norm(raw)]) return true;
    if (raw.includes("@")) return true;
    if (/^[a-f0-9-]{20,}$/i.test(raw)) return true;
    if (/^\d{4}-\d{2}-\d{2}/.test(raw)) return true;
    if (/^\d{1,2}:\d{2}/.test(raw)) return true;
    return false;
  }

  function translateText(value) {
    const raw = String(value || "");
    const clean = raw.replace(/\s+/g, " ").trim();

    if (shouldSkipText(clean)) return raw;

    const cleanup = clean.match(/^(Depuración lista\. Órdenes ocultas:|Depuracion lista\. Ordenes ocultas:|Cleanup ready\. Hidden orders:)\s*(\d+)$/i);
    if (cleanup) return raw.replace(clean, `${t("cleanupNotice")} ${cleanup[2]}`);

    const key = ALIASES[norm(clean)];
    if (!key) return raw;

    return raw.replace(clean, t(key));
  }

  function isMaterialsVisible() {
    const app = document.getElementById("app");
    if (!app) return false;

    if (app.querySelector("[data-materials-refresh]")) return true;
    if (app.querySelector("[data-materials-export]")) return true;
    if (app.querySelector("[data-material-return-order]")) return true;
    if (app.querySelector("[data-material-return-save]")) return true;
    if (app.querySelector("[data-material-approve-open]")) return true;
    if (app.querySelector(".cx-materials-table")) return true;
    if (app.querySelector(".cx-materials-status")) return true;
    if (app.querySelector(".cx-materials-return-results")) return true;

    const text = app.textContent || "";
    return (
      text.includes("Modulo Materiales") ||
      text.includes("Módulo Materiales") ||
      text.includes("Materials module") ||
      text.includes("Órdenes de materiales") ||
      text.includes("Material orders") ||
      text.includes("Gestión de salida") ||
      text.includes("Outbound management")
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

  function translateMaterials() {
    try {
      if (!isMaterialsVisible()) return;

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
      console.warn("CLONEXA Materials i18n skipped:", error);
    }
  }

  let timer = null;

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(translateMaterials, 100);
  }

  function burst() {
    let count = 0;
    const id = setInterval(() => {
      count += 1;
      translateMaterials();
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
    if (isMaterialsVisible()) translateMaterials();
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
      console.warn("CLONEXA Materials i18n init skipped:", error);
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
    r'\s*<script[^>]+src=["\'][^"\']*client_materials_i18n_safe\.js[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE,
)

kpis_matches = list(re.finditer(
    r'<script[^>]+src=["\']([^"\']*client_kpis_i18n_safe\.js[^"\']*)["\'][^>]*>\s*</script>',
    html,
    flags=re.IGNORECASE,
))

if kpis_matches:
    last = kpis_matches[-1]
    src = last.group(1)
    safe_src = re.sub(r'client_kpis_i18n_safe\.js(?:\?v=[^"\']*)?', 'client_materials_i18n_safe.js?v=020LR1', src)
    html = html[:last.end()] + f'\n<script src="{safe_src}"></script>\n' + html[last.end():]
else:
    reports_matches = list(re.finditer(
        r'<script[^>]+src=["\']([^"\']*client_reports_i18n_safe\.js[^"\']*)["\'][^>]*>\s*</script>',
        html,
        flags=re.IGNORECASE,
    ))
    if reports_matches:
        last = reports_matches[-1]
        src = last.group(1)
        safe_src = re.sub(r'client_reports_i18n_safe\.js(?:\?v=[^"\']*)?', 'client_materials_i18n_safe.js?v=020LR1', src)
        html = html[:last.end()] + f'\n<script src="{safe_src}"></script>\n' + html[last.end():]
    else:
        html = html.replace("</body>", '<script src="/client-static/client_materials_i18n_safe.js?v=020LR1"></script>\n</body>')

html_path.write_text(html, encoding="utf-8")

print("PATCH_OK: 020L-R1 safe external Materials i18n super dictionary added")
