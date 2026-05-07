from pathlib import Path
import re

html_path = Path("app/web/client.html")
i18n_path = Path("app/web/client_i18n.js")

html = html_path.read_text(encoding="utf-8-sig")

js = r"""
(function clonexaClientI18nSafeTranslator() {
  "use strict";

  if (window.__CLONEXA_CLIENT_I18N_SAFE_TRANSLATOR__) return;
  window.__CLONEXA_CLIENT_I18N_SAFE_TRANSLATOR__ = true;

  const LANG_KEY = "clonexa_client_language";

  const D = {
    es: {
      settings: "Configuración",
      logout: "Salir",
      dashboard: "Dashboard",
      inventory: "Inventario",
      fieldCrm: "CRM Campo",
      payroll: "Nómina",
      staff: "Personal",
      materials: "Materiales",
      reports: "Reportes",
      bots: "Bots",
      gps: "GPS",
      kpis: "KPIs",

      businessSystem: "SISTEMA OPERATIVO EMPRESARIAL",
      activeModule: "MÓDULO ACTIVO",
      activeModulesPanel: "MÓDULOS DEL PANEL",
      activeServices: "Servicios activos",
      activeTenant: "Tenant activo",
      activeModules: "módulos activos",
      independentPanel: "Panel operativo independiente conectado a sus módulos activos.",
      moduleAssigned: "Este módulo está asignado a la empresa y se construirá como pantalla independiente.",

      activeNow: "Activos ahora",
      gpsInside: "GPS dentro",
      materialDelivered: "Material entregado",
      lowStock: "Stock bajo",

      stockMaterials: "STOCK Y MATERIALES",
      liveOperation: "OPERACIÓN EN VIVO",
      payrollCalc: "CORTE Y CÁLCULO",
      operationalStaff: "OPERATIONAL STAFF",
      operationalIndicators: "OPERATIONAL INDICATORS",
      locationRoutes: "UBICACIÓN Y RUTAS",
      requestReturn: "SOLICITUD Y DEVOLUCIÓN",
      metricsAudit: "MÉTRICAS Y AUDITORÍA",

      moduleInventory: "MÓDULO INVENTARIO",
      moduleMaterials: "MÓDULO MATERIALES",
      moduleCrm: "MÓDULO CRM CAMPO",
      modulePayroll: "MÓDULO NÓMINA",
      moduleWorkforce: "MÓDULO WORKFORCE",
      moduleReports: "MÓDULO REPORTES",
      moduleGps: "MÓDULO GPS",
      moduleBots: "MÓDULO BOTS",
      moduleKpis: "MÓDULO KPIS",

      back: "Volver",
      refresh: "Actualizar",
      create: "Crear",
      save: "Guardar",
      saveChanges: "Guardar cambios",
      cancel: "Cancelar",
      search: "Buscar",
      detail: "Detalle",
      returnAction: "Devolución",
      consignment: "Consigna",
      approve: "Aprobar",
      reject: "Rechazar",
      deliver: "Entregar",
      update: "Actualizar",
      delete: "Eliminar",
      activate: "Activar",
      deactivate: "Inactivar",
      csv: "CSV",

      summary: "RESUMEN",
      inventoryStatus: "Estado del inventario",
      createMaterialProduct: "Crear material / producto",
      modifyMaterial: "Modificar material",
      newInventoryRecord: "Nuevo registro de inventario",
      inventoryHero: "Catálogo operativo, mínimos y stock actual de solo lectura. Materiales descontará o devolverá stock en la siguiente integración.",
      inventoryHelp: "El stock actual se crea desde la cantidad inicial como movimiento. Luego solo cambia por entradas, entregas y devoluciones.",
      nameReference: "Nombre / referencia",
      nameReferenceUpper: "NOMBRE / REFERENCIA",
      size: "Tamaño",
      sizeUpper: "TAMAÑO",
      color: "Color",
      colorUpper: "COLOR",
      initialQty: "Cantidad inicial",
      initialQtyUpper: "CANTIDAD INICIAL",
      minAlert: "Mínimo alerta",
      minAlertUpper: "MÍNIMO ALERTA",
      stock: "Stock",
      currentStock: "Stock actual",
      lowStock2: "Stock bajo",
      totalRecords: "Total registros",

      crmHero: "Vista viva de colaboradores en turno, pausas y núcleos activos de la empresa.",
      currentStatus: "ESTADO OPERATIVO ACTUAL",
      liveOps: "Operación en vivo",
      collaborators: "Colaboradores",
      collaboratorsUpper: "COLABORADORES",
      collaboratorStatus: "Estado por colaborador",
      collaborator: "Colaborador",
      offShift: "Fuera de turno",
      onBreak: "En pausa",
      timer: "Cronómetro",
      noRequest: "Sin solicitud",
      noTask: "Sin tarea",
      noLocation: "Sin ubicación",

      staffHero: "Gestiona empleados, técnicos, supervisores y roles conectados a bot, nómina y operación.",
      staffRegistry: "Registro de personal operativo",
      staffIndependent: "administra su personal de forma independiente.",
      editableTable: "TABLA EDITABLE",
      addRow: "Agregar fila",
      addStaff: "Agregar personal",
      history: "Historial",
      searchMatches: "Buscar coincidencias: nombre, rol, teléfono, correo, Telegram, estado...",
      all: "Todos",
      active: "Activo",
      activePlural: "Activos",
      inactive: "Inactivo",
      inactivePlural: "Inactivos",
      archived: "Archivado",
      archivedPlural: "Archivados",
      total: "Total",
      totalUpper: "TOTAL",
      showing: "Mostrando",
      records: "registros",

      name: "Nombre",
      nameUpper: "NOMBRE",
      fullName: "Nombre completo",
      role: "Rol",
      roleUpper: "ROL",
      phone: "Teléfono",
      phoneUpper: "TELÉFONO",
      email: "Correo",
      emailUpper: "CORREO",
      telegramId: "Telegram ID",
      hireDate: "Fecha ingreso",
      hireDateUpper: "FECHA INGRESO",
      regularHour: "Hora ordinaria",
      regularHourUpper: "HORA ORDINARIA",
      extraHour: "Hora extra",
      extraHourUpper: "HORA EXTRA",
      discount1: "Descuento 1",
      discount1Upper: "DESCUENTO 1",
      discount2: "Descuento 2",
      discount2Upper: "DESCUENTO 2",
      status: "Estado",
      statusUpper: "ESTADO",
      actions: "Acciones",
      actionsUpper: "ACCIONES",
      supervisor: "Supervisor",
      operator: "Operador",
      technician: "Técnico",
      employee: "Empleado",
      event: "Evento",
      field: "Campo",
      oldValue: "Valor anterior",
      newValue: "Valor nuevo",
      source: "Fuente",
      notes: "Notas",
      noHistory: "No hay registros de historial para los filtros seleccionados.",

      materialsHero: "Órdenes de salida conectadas a Inventario. Entregar descuenta stock; devolver exige número de orden.",
      operationalCycle: "CICLO OPERATIVO",
      materialOrders: "Órdenes de materiales",
      pending: "Pendientes",
      approved: "Aprobadas",
      delivered: "Entregadas",
      returned: "Devueltas",
      order: "Orden",
      orderUpper: "ORDEN",
      requester: "Solicitante",
      requesterUpper: "SOLICITANTE",
      material: "Material",
      materialUpper: "MATERIAL",
      quantity: "Cantidad",
      quantityUpper: "CANTIDAD",
      destination: "Destino",
      destinationUpper: "DESTINO",
      outputManagement: "GESTIÓN DE SALIDA",
      noMaterialOrders: "No hay órdenes de materiales.",
      registerReturn: "Registrar devolución",
      registerConsignment: "Registrar consigna",
      orderNumber: "Número de orden",

      payrollHero: "Nómina consume Workforce, Bot y Asistencia. Al finalizar un corte, exporta CSV para guardar el histórico externo del periodo.",
      calculatePeriod: "Calcular periodo",
      period: "Periodo",
      payrollSummary: "Resumen de nómina",
      ordinaryHours: "Horas ordinarias",
      extraHours: "Horas extra",
      discounts: "Descuentos",
      gross: "Bruto",
      estimatedTotal: "Total estimado",
      estimatedNet: "Total neto estimado",

      kpisHero: "Indicadores ejecutivos calculados desde Workforce, GPS, Materiales, Inventario y Nómina según módulos activos.",
      operationalKpis: "KPIs Operativos",
      executiveIndicators: "Indicadores ejecutivos",
      riskAlerts: "Riesgos operativos",
      smartSearch: "Lupa inteligente",
      noCriticalAlerts: "Sin alertas críticas en el periodo.",

      reportsHero: "Histórico consolidado de Personal, GPS, Materiales, Inventario y Nómina. No modifica datos; solo audita y exporta.",
      executiveSummary: "Resumen ejecutivo",
      operationalDetail: "Detalle operativo",
      auditableTables: "Tablas auditables",
      generalReport: "Reporte general",
      personReport: "Reporte por persona",
      noData: "Sin datos para los filtros seleccionados.",
      noEvents: "No hay eventos para los filtros seleccionados.",

      gpsSummary: "Resumen GPS",
      perimeters: "Perímetros",
      allowedParams: "Parámetros permitidos",
      savePerimeters: "Guardar perímetros",
      pointName: "Nombre punto",
      latFrom: "Latitud desde",
      latTo: "Latitud hasta",
      lngFrom: "Longitud desde",
      lngTo: "Longitud hasta",
      showPanel: "Mostrar en panel",

      botTelegram: "Bot Telegram",
      internalBotName: "Nombre interno del bot",
      saveName: "Guardar nombre",
      operationalChannel: "Canal operativo",
      technicalConfig: "Configuración técnica administrada desde CLONEXA Admin V2."
    },

    en: {
      settings: "Settings",
      logout: "Log out",
      dashboard: "Dashboard",
      inventory: "Inventory",
      fieldCrm: "Field CRM",
      payroll: "Payroll",
      staff: "Staff",
      materials: "Materials",
      reports: "Reports",
      bots: "Bots",
      gps: "GPS",
      kpis: "KPIs",

      businessSystem: "BUSINESS OPERATING SYSTEM",
      activeModule: "ACTIVE MODULE",
      activeModulesPanel: "PANEL MODULES",
      activeServices: "Active services",
      activeTenant: "Active tenant",
      activeModules: "active modules",
      independentPanel: "Independent operations panel connected to its active modules.",
      moduleAssigned: "This module is assigned to the company and will be built as an independent screen.",

      activeNow: "Active now",
      gpsInside: "GPS inside",
      materialDelivered: "Delivered material",
      lowStock: "Low stock",

      stockMaterials: "STOCK AND MATERIALS",
      liveOperation: "LIVE OPERATION",
      payrollCalc: "CUTOFF AND CALCULATION",
      operationalStaff: "OPERATIONAL STAFF",
      operationalIndicators: "OPERATIONAL INDICATORS",
      locationRoutes: "LOCATION AND ROUTES",
      requestReturn: "REQUEST AND RETURN",
      metricsAudit: "METRICS AND AUDIT",

      moduleInventory: "INVENTORY MODULE",
      moduleMaterials: "MATERIALS MODULE",
      moduleCrm: "FIELD CRM MODULE",
      modulePayroll: "PAYROLL MODULE",
      moduleWorkforce: "WORKFORCE MODULE",
      moduleReports: "REPORTS MODULE",
      moduleGps: "GPS MODULE",
      moduleBots: "BOTS MODULE",
      moduleKpis: "KPIS MODULE",

      back: "Back",
      refresh: "Refresh",
      create: "Create",
      save: "Save",
      saveChanges: "Save changes",
      cancel: "Cancel",
      search: "Search",
      detail: "Detail",
      returnAction: "Return",
      consignment: "Consignment",
      approve: "Approve",
      reject: "Reject",
      deliver: "Deliver",
      update: "Refresh",
      delete: "Delete",
      activate: "Activate",
      deactivate: "Deactivate",
      csv: "CSV",

      summary: "SUMMARY",
      inventoryStatus: "Inventory status",
      createMaterialProduct: "Create material / product",
      modifyMaterial: "Modify material",
      newInventoryRecord: "New inventory record",
      inventoryHero: "Operational catalog, minimums and current read-only stock. Materials will deduct or return stock in the next integration.",
      inventoryHelp: "Current stock is created from the initial quantity as a movement. After that, it only changes through entries, deliveries and returns.",
      nameReference: "Name / reference",
      nameReferenceUpper: "NAME / REFERENCE",
      size: "Size",
      sizeUpper: "SIZE",
      color: "Color",
      colorUpper: "COLOR",
      initialQty: "Initial quantity",
      initialQtyUpper: "INITIAL QUANTITY",
      minAlert: "Minimum alert",
      minAlertUpper: "MINIMUM ALERT",
      stock: "Stock",
      currentStock: "Current stock",
      lowStock2: "Low stock",
      totalRecords: "Total records",

      crmHero: "Live view of employees on shift, breaks and active company cores.",
      currentStatus: "CURRENT OPERATING STATUS",
      liveOps: "Live operation",
      collaborators: "Employees",
      collaboratorsUpper: "EMPLOYEES",
      collaboratorStatus: "Status by employee",
      collaborator: "Employee",
      offShift: "Off shift",
      onBreak: "On break",
      timer: "Timer",
      noRequest: "No request",
      noTask: "No task",
      noLocation: "No location",

      staffHero: "Manage employees, technicians, supervisors and roles connected to bot, payroll and operations.",
      staffRegistry: "Operational staff registry",
      staffIndependent: "manages its staff independently.",
      editableTable: "EDITABLE TABLE",
      addRow: "Add row",
      addStaff: "Add staff",
      history: "History",
      searchMatches: "Search matches: name, role, phone, email, Telegram, status...",
      all: "All",
      active: "Active",
      activePlural: "Active",
      inactive: "Inactive",
      inactivePlural: "Inactive",
      archived: "Archived",
      archivedPlural: "Archived",
      total: "Total",
      totalUpper: "TOTAL",
      showing: "Showing",
      records: "records",

      name: "Name",
      nameUpper: "NAME",
      fullName: "Full name",
      role: "Role",
      roleUpper: "ROLE",
      phone: "Phone",
      phoneUpper: "PHONE",
      email: "Email",
      emailUpper: "EMAIL",
      telegramId: "Telegram ID",
      hireDate: "Hire date",
      hireDateUpper: "HIRE DATE",
      regularHour: "Regular hour",
      regularHourUpper: "REGULAR HOUR",
      extraHour: "Extra hour",
      extraHourUpper: "EXTRA HOUR",
      discount1: "Discount 1",
      discount1Upper: "DISCOUNT 1",
      discount2: "Discount 2",
      discount2Upper: "DISCOUNT 2",
      status: "Status",
      statusUpper: "STATUS",
      actions: "Actions",
      actionsUpper: "ACTIONS",
      supervisor: "Supervisor",
      operator: "Operator",
      technician: "Technician",
      employee: "Employee",
      event: "Event",
      field: "Field",
      oldValue: "Old value",
      newValue: "New value",
      source: "Source",
      notes: "Notes",
      noHistory: "No history records match the selected filters.",

      materialsHero: "Outbound orders connected to Inventory. Delivery deducts stock; return requires an order number.",
      operationalCycle: "OPERATING CYCLE",
      materialOrders: "Material orders",
      pending: "Pending",
      approved: "Approved",
      delivered: "Delivered",
      returned: "Returned",
      order: "Order",
      orderUpper: "ORDER",
      requester: "Requester",
      requesterUpper: "REQUESTER",
      material: "Material",
      materialUpper: "MATERIAL",
      quantity: "Quantity",
      quantityUpper: "QUANTITY",
      destination: "Destination",
      destinationUpper: "DESTINATION",
      outputManagement: "OUTPUT MANAGEMENT",
      noMaterialOrders: "There are no material orders.",
      registerReturn: "Register return",
      registerConsignment: "Register consignment",
      orderNumber: "Order number",

      payrollHero: "Payroll uses Workforce, Bot and Attendance. When closing a period, export CSV to keep the external history.",
      calculatePeriod: "Calculate period",
      period: "Period",
      payrollSummary: "Payroll summary",
      ordinaryHours: "Ordinary hours",
      extraHours: "Extra hours",
      discounts: "Discounts",
      gross: "Gross",
      estimatedTotal: "Estimated total",
      estimatedNet: "Estimated net total",

      kpisHero: "Executive indicators calculated from Workforce, GPS, Materials, Inventory and Payroll according to active modules.",
      operationalKpis: "Operational KPIs",
      executiveIndicators: "Executive indicators",
      riskAlerts: "Operational risks",
      smartSearch: "Smart search",
      noCriticalAlerts: "No critical alerts in the period.",

      reportsHero: "Consolidated history of Staff, GPS, Materials, Inventory and Payroll. It does not modify data; it only audits and exports.",
      executiveSummary: "Executive summary",
      operationalDetail: "Operational detail",
      auditableTables: "Auditable tables",
      generalReport: "General report",
      personReport: "Person report",
      noData: "No data for the selected filters.",
      noEvents: "There are no events for the selected filters.",

      gpsSummary: "GPS summary",
      perimeters: "Perimeters",
      allowedParams: "Allowed parameters",
      savePerimeters: "Save perimeters",
      pointName: "Point name",
      latFrom: "Latitude from",
      latTo: "Latitude to",
      lngFrom: "Longitude from",
      lngTo: "Longitude to",
      showPanel: "Show in panel",

      botTelegram: "Telegram Bot",
      internalBotName: "Internal bot name",
      saveName: "Save name",
      operationalChannel: "Operational channel",
      technicalConfig: "Technical configuration managed from CLONEXA Admin V2."
    },

    fr: {
      settings: "Configuration",
      logout: "Quitter",
      dashboard: "Tableau de bord",
      inventory: "Inventaire",
      fieldCrm: "CRM Terrain",
      payroll: "Paie",
      staff: "Personnel",
      materials: "Matériaux",
      reports: "Rapports",
      bots: "Bots",
      gps: "GPS",
      kpis: "KPIs",

      businessSystem: "SYSTÈME OPÉRATIONNEL D’ENTREPRISE",
      activeModule: "MODULE ACTIF",
      activeModulesPanel: "MODULES DU PANNEAU",
      activeServices: "Services actifs",
      activeTenant: "Tenant actif",
      activeModules: "modules actifs",
      independentPanel: "Panneau opérationnel indépendant connecté à ses modules actifs.",
      moduleAssigned: "Ce module est attribué à l’entreprise et sera construit comme écran indépendant.",

      activeNow: "Actifs maintenant",
      gpsInside: "GPS à l’intérieur",
      materialDelivered: "Matériel livré",
      lowStock: "Stock faible",

      stockMaterials: "STOCK ET MATÉRIAUX",
      liveOperation: "OPÉRATION EN DIRECT",
      payrollCalc: "CLÔTURE ET CALCUL",
      operationalStaff: "PERSONNEL OPÉRATIONNEL",
      operationalIndicators: "INDICATEURS OPÉRATIONNELS",
      locationRoutes: "LOCALISATION ET ITINÉRAIRES",
      requestReturn: "DEMANDE ET RETOUR",
      metricsAudit: "MÉTRIQUES ET AUDIT",

      moduleInventory: "MODULE INVENTAIRE",
      moduleMaterials: "MODULE MATÉRIAUX",
      moduleCrm: "MODULE CRM TERRAIN",
      modulePayroll: "MODULE PAIE",
      moduleWorkforce: "MODULE PERSONNEL",
      moduleReports: "MODULE RAPPORTS",
      moduleGps: "MODULE GPS",
      moduleBots: "MODULE BOTS",
      moduleKpis: "MODULE KPIS",

      back: "Retour",
      refresh: "Actualiser",
      create: "Créer",
      save: "Enregistrer",
      saveChanges: "Enregistrer",
      cancel: "Annuler",
      search: "Rechercher",
      detail: "Détail",
      returnAction: "Retour",
      consignment: "Consigne",
      approve: "Approuver",
      reject: "Rejeter",
      deliver: "Livrer",
      update: "Actualiser",
      delete: "Supprimer",
      activate: "Activer",
      deactivate: "Désactiver",
      csv: "CSV",

      summary: "RÉSUMÉ",
      inventoryStatus: "État de l’inventaire",
      createMaterialProduct: "Créer matériau / produit",
      modifyMaterial: "Modifier matériau",
      newInventoryRecord: "Nouvel enregistrement d’inventaire",
      inventoryHero: "Catalogue opérationnel, minimums et stock actuel en lecture seule. Les matériaux déduiront ou retourneront le stock lors de la prochaine intégration.",
      inventoryHelp: "Le stock actuel est créé à partir de la quantité initiale comme mouvement. Ensuite, il ne change que par entrées, livraisons et retours.",
      nameReference: "Nom / référence",
      nameReferenceUpper: "NOM / RÉFÉRENCE",
      size: "Taille",
      sizeUpper: "TAILLE",
      color: "Couleur",
      colorUpper: "COULEUR",
      initialQty: "Quantité initiale",
      initialQtyUpper: "QUANTITÉ INITIALE",
      minAlert: "Alerte minimum",
      minAlertUpper: "ALERTE MINIMUM",
      stock: "Stock",
      currentStock: "Stock actuel",
      lowStock2: "Stock faible",
      totalRecords: "Total des enregistrements",

      crmHero: "Vue en direct des collaborateurs en service, pauses et noyaux actifs de l’entreprise.",
      currentStatus: "ÉTAT OPÉRATIONNEL ACTUEL",
      liveOps: "Opération en direct",
      collaborators: "Collaborateurs",
      collaboratorsUpper: "COLLABORATEURS",
      collaboratorStatus: "Statut par collaborateur",
      collaborator: "Collaborateur",
      offShift: "Hors service",
      onBreak: "En pause",
      timer: "Chronomètre",
      noRequest: "Aucune demande",
      noTask: "Aucune tâche",
      noLocation: "Aucune localisation",

      staffHero: "Gérez les employés, techniciens, superviseurs et rôles connectés au bot, à la paie et aux opérations.",
      staffRegistry: "Registre du personnel opérationnel",
      staffIndependent: "gère son personnel de manière indépendante.",
      editableTable: "TABLEAU MODIFIABLE",
      addRow: "Ajouter une ligne",
      addStaff: "Ajouter du personnel",
      history: "Historique",
      searchMatches: "Rechercher : nom, rôle, téléphone, e-mail, Telegram, statut...",
      all: "Tous",
      active: "Actif",
      activePlural: "Actifs",
      inactive: "Inactif",
      inactivePlural: "Inactifs",
      archived: "Archivé",
      archivedPlural: "Archivés",
      total: "Total",
      totalUpper: "TOTAL",
      showing: "Affichage",
      records: "enregistrements",

      name: "Nom",
      nameUpper: "NOM",
      fullName: "Nom complet",
      role: "Rôle",
      roleUpper: "RÔLE",
      phone: "Téléphone",
      phoneUpper: "TÉLÉPHONE",
      email: "E-mail",
      emailUpper: "E-MAIL",
      telegramId: "Telegram ID",
      hireDate: "Date d’entrée",
      hireDateUpper: "DATE D’ENTRÉE",
      regularHour: "Heure normale",
      regularHourUpper: "HEURE NORMALE",
      extraHour: "Heure supplémentaire",
      extraHourUpper: "HEURE SUPPLÉMENTAIRE",
      discount1: "Remise 1",
      discount1Upper: "REMISE 1",
      discount2: "Remise 2",
      discount2Upper: "REMISE 2",
      status: "Statut",
      statusUpper: "STATUT",
      actions: "Actions",
      actionsUpper: "ACTIONS",
      supervisor: "Superviseur",
      operator: "Opérateur",
      technician: "Technicien",
      employee: "Employé",
      event: "Événement",
      field: "Champ",
      oldValue: "Ancienne valeur",
      newValue: "Nouvelle valeur",
      source: "Source",
      notes: "Notes",
      noHistory: "Aucun historique ne correspond aux filtres sélectionnés.",

      materialsHero: "Ordres de sortie connectés à l’inventaire. La livraison déduit le stock ; le retour exige un numéro d’ordre.",
      operationalCycle: "CYCLE OPÉRATIONNEL",
      materialOrders: "Ordres de matériaux",
      pending: "En attente",
      approved: "Approuvées",
      delivered: "Livrées",
      returned: "Retournées",
      order: "Ordre",
      orderUpper: "ORDRE",
      requester: "Demandeur",
      requesterUpper: "DEMANDEUR",
      material: "Matériel",
      materialUpper: "MATÉRIEL",
      quantity: "Quantité",
      quantityUpper: "QUANTITÉ",
      destination: "Destination",
      destinationUpper: "DESTINATION",
      outputManagement: "GESTION DE SORTIE",
      noMaterialOrders: "Il n’y a pas d’ordres de matériaux.",
      registerReturn: "Enregistrer retour",
      registerConsignment: "Enregistrer consigne",
      orderNumber: "Numéro d’ordre",

      payrollHero: "La paie utilise Workforce, Bot et Assistance. À la clôture d’une période, exportez CSV pour conserver l’historique externe.",
      calculatePeriod: "Calculer période",
      period: "Période",
      payrollSummary: "Résumé de paie",
      ordinaryHours: "Heures ordinaires",
      extraHours: "Heures supplémentaires",
      discounts: "Remises",
      gross: "Brut",
      estimatedTotal: "Total estimé",
      estimatedNet: "Total net estimé",

      kpisHero: "Indicateurs exécutifs calculés depuis Workforce, GPS, Matériaux, Inventaire et Paie selon les modules actifs.",
      operationalKpis: "KPIs opérationnels",
      executiveIndicators: "Indicateurs exécutifs",
      riskAlerts: "Risques opérationnels",
      smartSearch: "Recherche intelligente",
      noCriticalAlerts: "Aucune alerte critique sur la période.",

      reportsHero: "Historique consolidé du personnel, GPS, matériaux, inventaire et paie. Il ne modifie pas les données ; il audite et exporte uniquement.",
      executiveSummary: "Résumé exécutif",
      operationalDetail: "Détail opérationnel",
      auditableTables: "Tableaux auditables",
      generalReport: "Rapport général",
      personReport: "Rapport par personne",
      noData: "Aucune donnée pour les filtres sélectionnés.",
      noEvents: "Aucun événement pour les filtres sélectionnés.",

      gpsSummary: "Résumé GPS",
      perimeters: "Périmètres",
      allowedParams: "Paramètres autorisés",
      savePerimeters: "Enregistrer périmètres",
      pointName: "Nom du point",
      latFrom: "Latitude depuis",
      latTo: "Latitude jusqu’à",
      lngFrom: "Longitude depuis",
      lngTo: "Longitude jusqu’à",
      showPanel: "Afficher dans le panneau",

      botTelegram: "Bot Telegram",
      internalBotName: "Nom interne du bot",
      saveName: "Enregistrer nom",
      operationalChannel: "Canal opérationnel",
      technicalConfig: "Configuration technique gérée depuis CLONEXA Admin V2."
    }
  };

  const aliases = {
    "configuración": "settings", "settings": "settings", "salir": "logout", "log out": "logout",
    "dashboard": "dashboard", "inventario": "inventory", "inventory": "inventory",
    "crm campo": "fieldCrm", "field crm": "fieldCrm", "nómina": "payroll", "nomina": "payroll", "payroll": "payroll",
    "personal": "staff", "staff": "staff", "workforce": "staff", "materiales": "materials", "materials": "materials",
    "reportes": "reports", "reports": "reports", "bots": "bots", "gps": "gps", "kpis": "kpis",

    "sistema operativo empresarial": "businessSystem",
    "modulo activo": "activeModule", "módulo activo": "activeModule",
    "módulos del panel": "activeModulesPanel", "modulos del panel": "activeModulesPanel",
    "servicios activos": "activeServices", "tenant activo": "activeTenant",
    "panel operativo independiente conectado a sus módulos activos.": "independentPanel",
    "panel operativo independiente conectado a sus modulos activos.": "independentPanel",
    "este modulo esta asignado a la empresa y se construira como pantalla independiente.": "moduleAssigned",
    "este módulo está asignado a la empresa y se construirá como pantalla independiente.": "moduleAssigned",

    "activos ahora": "activeNow", "gps dentro": "gpsInside", "material entregado": "materialDelivered", "stock bajo": "lowStock",

    "stock y materiales": "stockMaterials", "operación en vivo": "liveOperation", "operacion en vivo": "liveOperation",
    "corte y cálculo": "payrollCalc", "corte y calculo": "payrollCalc",
    "personal operativo": "operationalStaff", "operational staff": "operationalStaff",
    "indicadores operativos": "operationalIndicators", "operational indicators": "operationalIndicators",
    "ubicación y rutas": "locationRoutes", "ubicacion y rutas": "locationRoutes",
    "solicitud y devolución": "requestReturn", "solicitud y devolucion": "requestReturn",
    "métricas y auditoría": "metricsAudit", "metricas y auditoria": "metricsAudit",

    "módulo inventario": "moduleInventory", "modulo inventario": "moduleInventory",
    "módulo materiales": "moduleMaterials", "modulo materiales": "moduleMaterials",
    "módulo crm campo": "moduleCrm", "modulo crm campo": "moduleCrm",
    "módulo nómina": "modulePayroll", "modulo nomina": "modulePayroll",
    "módulo workforce": "moduleWorkforce", "modulo workforce": "moduleWorkforce",
    "módulo reportes": "moduleReports", "modulo reportes": "moduleReports",
    "módulo gps": "moduleGps", "modulo gps": "moduleGps", "módulo bots": "moduleBots", "modulo bots": "moduleBots",
    "módulo kpis": "moduleKpis", "modulo kpis": "moduleKpis",

    "volver": "back", "back": "back", "actualizar": "refresh", "refresh": "refresh",
    "crear": "create", "guardar": "save", "save": "save", "guardar cambios": "saveChanges", "save changes": "saveChanges",
    "cancelar": "cancel", "buscar": "search", "detalle": "detail", "detail": "detail",
    "devolución": "returnAction", "devolucion": "returnAction", "return": "returnAction",
    "consigna": "consignment", "aprobar": "approve", "rechazar": "reject", "entregar": "deliver",
    "eliminar": "delete", "activar": "activate", "inactivar": "deactivate",

    "resumen": "summary", "estado del inventario": "inventoryStatus",
    "crear material / producto": "createMaterialProduct", "modificar material": "modifyMaterial",
    "nuevo registro de inventario": "newInventoryRecord",
    "catálogo operativo, mínimos y stock actual de solo lectura. materiales descontará o devolverá stock en la siguiente integración.": "inventoryHero",
    "catalogo operativo, minimos y stock actual de solo lectura. materiales descontara o devolvera stock en la siguiente integracion.": "inventoryHero",
    "el stock actual se crea desde la cantidad inicial como movimiento. luego solo cambia por entradas, entregas y devoluciones.": "inventoryHelp",
    "nombre / referencia": "nameReference", "nombre / referencia": "nameReference", "tamaño": "size", "tamano": "size",
    "color": "color", "cantidad inicial": "initialQty", "mínimo alerta": "minAlert", "minimo alerta": "minAlert",
    "stock actual": "currentStock", "total registros": "totalRecords",

    "vista viva de colaboradores en turno, pausas y núcleos activos de la empresa.": "crmHero",
    "vista viva de colaboradores en turno, pausas y nucleos activos de la empresa.": "crmHero",
    "estado operativo actual": "currentStatus", "estado por colaborador": "collaboratorStatus",
    "colaboradores": "collaborators", "colaborador": "collaborator", "fuera de turno": "offShift",
    "en pausa": "onBreak", "cronómetro": "timer", "cronometro": "timer",
    "sin solicitud": "noRequest", "sin tarea": "noTask", "sin ubicación": "noLocation", "sin ubicacion": "noLocation",

    "gestiona empleados, técnicos, supervisores y roles conectados a bot, nómina y operación.": "staffHero",
    "gestiona empleados, tecnicos, supervisores y roles conectados a bot, nomina y operacion.": "staffHero",
    "registro de personal operativo": "staffRegistry", "administra su personal de forma independiente.": "staffIndependent",
    "tabla editable": "editableTable", "agregar fila": "addRow", "agregar personal": "addStaff",
    "historial": "history", "todos": "all", "activo": "active", "activos": "activePlural",
    "inactivo": "inactive", "inactivos": "inactivePlural", "archivado": "archived", "archivados": "archivedPlural",
    "total": "total", "mostrando": "showing", "registros": "records",
    "nombre": "name", "nombre completo": "fullName", "rol": "role", "teléfono": "phone", "telefono": "phone",
    "correo": "email", "telegram id": "telegramId", "fecha ingreso": "hireDate", "hora ordinaria": "regularHour",
    "hora extra": "extraHour", "descuento 1": "discount1", "descuento 2": "discount2",
    "estado": "status", "acciones": "actions", "supervisor": "supervisor", "operador": "operator",
    "técnico": "technician", "tecnico": "technician", "empleado": "employee", "evento": "event",
    "campo": "field", "valor anterior": "oldValue", "valor nuevo": "newValue", "fuente": "source",
    "notas": "notes", "no hay registros de historial para los filtros seleccionados.": "noHistory",

    "órdenes de salida conectadas a inventario. entregar descuenta stock; devolver exige número de orden.": "materialsHero",
    "ordenes de salida conectadas a inventario. entregar descuenta stock; devolver exige numero de orden.": "materialsHero",
    "ciclo operativo": "operationalCycle", "órdenes de materiales": "materialOrders", "ordenes de materiales": "materialOrders",
    "pendientes": "pending", "aprobadas": "approved", "entregadas": "delivered", "devueltas": "returned",
    "orden": "order", "solicitante": "requester", "material": "material", "cantidad": "quantity",
    "destino": "destination", "gestión de salida": "outputManagement", "gestion de salida": "outputManagement",
    "no hay órdenes de materiales.": "noMaterialOrders", "registrar devolución": "registerReturn",
    "registrar devolucion": "registerReturn", "registrar consigna": "registerConsignment", "número de orden": "orderNumber",

    "nómina consume workforce, bot y asistencia. al finalizar un corte, exporta csv para guardar el histórico externo del periodo.": "payrollHero",
    "calcular periodo": "calculatePeriod", "periodo": "period", "resumen de nómina": "payrollSummary",
    "horas ordinarias": "ordinaryHours", "horas extra": "extraHours", "descuentos": "discounts",
    "bruto": "gross", "total estimado": "estimatedTotal", "total neto estimado": "estimatedNet",

    "indicadores ejecutivos calculados desde workforce, gps, materiales, inventario y nómina según módulos activos.": "kpisHero",
    "kpis operativos": "operationalKpis", "indicadores ejecutivos": "executiveIndicators",
    "riesgos operativos": "riskAlerts", "lupa inteligente": "smartSearch", "sin alertas críticas en el periodo.": "noCriticalAlerts",

    "histórico consolidado de personal, gps, materiales, inventario y nómina. no modifica datos; solo audita y exporta.": "reportsHero",
    "resumen ejecutivo": "executiveSummary", "detalle operativo": "operationalDetail", "tablas auditables": "auditableTables",
    "reporte general": "generalReport", "reporte por persona": "personReport",
    "sin datos para los filtros seleccionados.": "noData", "no hay eventos para los filtros seleccionados.": "noEvents",

    "resumen gps": "gpsSummary", "perímetros": "perimeters", "perimetros": "perimeters",
    "parámetros permitidos": "allowedParams", "parametros permitidos": "allowedParams",
    "guardar perímetros": "savePerimeters", "nombre punto": "pointName", "latitud desde": "latFrom",
    "latitud hasta": "latTo", "longitud desde": "lngFrom", "longitud hasta": "lngTo", "mostrar en panel": "showPanel",

    "bot telegram": "botTelegram", "nombre interno del bot": "internalBotName", "guardar nombre": "saveName",
    "canal operativo": "operationalChannel", "configuración técnica administrada desde clonexa admin v2.": "technicalConfig"
  };

  function getLang() {
    const raw = String(localStorage.getItem(LANG_KEY) || document.documentElement.lang || "es").toLowerCase();
    return ["es", "en", "fr"].includes(raw) ? raw : "es";
  }

  function normalized(text) {
    return String(text || "")
      .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .replace(/[“”]/g, '"').replace(/[‘’]/g, "'")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();
  }

  function shouldIgnoreText(text) {
    const s = String(text || "").trim();
    if (!s) return true;
    if (/^[\d\s.,:$%#@/_-]+$/.test(s)) return true;
    if (s.includes("@")) return true;
    if (/^[A-Z]{2,}-\d{4}/.test(s)) return true;
    if (/^[a-f0-9-]{24,}$/i.test(s)) return true;
    if (/^-?\d+(\.\d+)?\s*,\s*-?\d+(\.\d+)?$/.test(s)) return true;
    return false;
  }

  function translate(text) {
    const raw = String(text || "");
    const cleanRaw = raw.replace(/\s+/g, " ").trim();

    if (shouldIgnoreText(cleanRaw)) return raw;

    const lang = getLang();
    const key = aliases[normalized(cleanRaw)];

    if (key && D[lang] && D[lang][key]) {
      return raw.replace(cleanRaw, D[lang][key]);
    }

    const modulesMatch = cleanRaw.match(/^(\d+)\s+(m[oó]dulos activos|active modules|modules actifs)$/i);
    if (modulesMatch) return `${modulesMatch[1]} ${D[lang].activeModules}`;

    const staffMatch = cleanRaw.match(/^(.+?)\s+administra su personal de forma independiente\.?$/i);
    if (staffMatch) return `${staffMatch[1]} ${D[lang].staffIndependent}`;

    const showingMatch = cleanRaw.match(/^Mostrando\s+(.+?)\s+de\s+(.+?)\s+registros\.?$/i);
    if (showingMatch) {
      if (lang === "en") return `Showing ${showingMatch[1]} of ${showingMatch[2]} records.`;
      if (lang === "fr") return `Affichage ${showingMatch[1]} sur ${showingMatch[2]} enregistrements.`;
      return `Mostrando ${showingMatch[1]} de ${showingMatch[2]} registros.`;
    }

    return raw;
  }

  function skipElement(el) {
    if (!el || !el.tagName) return false;
    const tag = el.tagName.toLowerCase();
    if (["script", "style", "code", "pre", "textarea"].includes(tag)) return true;
    if (el.closest && el.closest("[data-clx-no-i18n]")) return true;
    if (el.isContentEditable) return true;
    return false;
  }

  function translateDom(root) {
    const base = root || document.body;
    if (!base) return;

    const walker = document.createTreeWalker(base, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const parent = node.parentElement;
        if (!parent || skipElement(parent)) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });

    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);

    nodes.forEach((node) => {
      const next = translate(node.nodeValue);
      if (next !== node.nodeValue) node.nodeValue = next;
    });

    base.querySelectorAll?.("[placeholder], [title], [aria-label], input[type='button'], input[type='submit']").forEach((el) => {
      if (skipElement(el)) return;

      ["placeholder", "title", "aria-label"].forEach((attr) => {
        if (!el.hasAttribute(attr)) return;
        const current = el.getAttribute(attr);
        const next = translate(current);
        if (next !== current) el.setAttribute(attr, next);
      });

      if (el.matches("input[type='button'], input[type='submit']")) {
        const next = translate(el.value);
        if (next !== el.value) el.value = next;
      }
    });

    const lang = getLang();
    const settings = document.getElementById("clxAccountSettingsBtn");
    const logout = document.getElementById("clxAccountLogoutBtn");
    if (settings) settings.textContent = `⚙ ${D[lang].settings}`;
    if (logout) logout.textContent = `⏻ ${D[lang].logout}`;
    document.documentElement.lang = lang;
  }

  let timer = null;
  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(() => translateDom(document.body), 80);
  }

  function burst() {
    let n = 0;
    const id = setInterval(() => {
      n += 1;
      translateDom(document.body);
      if (n >= 12) clearInterval(id);
    }, 250);
  }

  function setLanguage(lang) {
    const next = String(lang || "es").toLowerCase();
    if (!["es", "en", "fr"].includes(next)) return;
    localStorage.setItem(LANG_KEY, next);
    document.documentElement.lang = next;
    schedule();
    burst();
  }

  window.CLX_CLIENT_TRANSLATOR = {
    run: () => translateDom(document.body),
    setLanguage,
    lang: getLang
  };

  document.addEventListener("change", (event) => {
    const el = event.target;
    if (el && el.id === "clxAccountLanguage") setLanguage(el.value);
    else schedule();
  }, true);

  document.addEventListener("click", () => {
    schedule();
    setTimeout(schedule, 300);
    setTimeout(schedule, 900);
  }, true);

  const observer = new MutationObserver(schedule);

  function init() {
    translateDom(document.body);
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["placeholder", "title", "aria-label", "value"]
    });
    burst();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
"""

i18n_path.write_text(js, encoding="utf-8")

# Quitar script anterior si existía.
html = re.sub(
    r'\s*<script[^>]+src=["\'][^"\']*client_i18n\.js[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE,
)

script_tag = None
matches = list(re.finditer(
    r'<script[^>]+src=["\']([^"\']*client\.js[^"\']*)["\'][^>]*>\s*</script>',
    html,
    flags=re.IGNORECASE,
))

if matches:
    last = matches[-1]
    src = last.group(1)
    i18n_src = re.sub(r'client\.js(?:\?[^"\']*)?', 'client_i18n.js?v=020A6', src)
    script_tag = f'\n<script src="{i18n_src}"></script>\n'
    html = html[:last.end()] + script_tag + html[last.end():]
else:
    script_tag = '\n<script src="/static/client_i18n.js?v=020A6"></script>\n'
    if re.search(r'</body\s*>', html, flags=re.IGNORECASE):
        html = re.sub(r'</body\s*>', script_tag + "\n</body>", html, flags=re.IGNORECASE)
    else:
        html = html.rstrip() + script_tag + "\n"

html_path.write_text(html, encoding="utf-8")

print("PATCH_OK: client_i18n.js creado y cargado desde client.html")
