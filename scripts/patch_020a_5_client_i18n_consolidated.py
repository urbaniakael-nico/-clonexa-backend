from pathlib import Path

path = Path("app/web/client.js")
text = path.read_text(encoding="utf-8-sig")

def remove_iife_by_marker(src: str, marker: str) -> str:
    pos = src.find(marker)
    if pos < 0:
        return src

    # Buscar inicio real del bloque/IIFE antes del marker.
    start_candidates = [
        src.rfind("/*", 0, pos),
        src.rfind("(function", 0, pos),
        src.rfind("(() =>", 0, pos),
    ]
    start_candidates = [x for x in start_candidates if x >= 0]
    start = min(start_candidates) if start_candidates else pos

    end = src.find("})();", pos)
    if end < 0:
        raise SystemExit(f"No pude cerrar bloque para marker: {marker}")

    end += len("})();")
    return src[:start].rstrip() + "\n\n" + src[end:].lstrip()

# Limpiar motores parciales previos para que no compitan.
for marker in [
    "CLONEXA 020A-2 CLIENT GLOBAL I18N + BRANDING BINDING",
    "CLONEXA 020A-3 FULL CLIENT MODULE I18N",
    "CLONEXA 020A-4 FULL CLIENT RUNTIME I18N ENGINE",
]:
    text = remove_iife_by_marker(text, marker)

marker = "/* CLONEXA 020A-5 CLIENT I18N CONSOLIDATED ENGINE */"
if marker in text:
    print("OK: 020A-5 ya existe.")
    path.write_text(text, encoding="utf-8")
    raise SystemExit(0)

engine = r'''

/* CLONEXA 020A-5 CLIENT I18N CONSOLIDATED ENGINE */
(function clonexaClientI18nConsolidatedEngine() {
  "use strict";

  const LANG_KEY = "clonexa_client_language";

  const TX = {
    es: {
      "initializingCompanyPanel": "Inicializando Panel Empresa",
      "connectingBos": "Conectando con el sistema operativo empresarial...",
      "businessOperatingSystem": "SISTEMA OPERATIVO EMPRESARIAL",
      "independentPanel": "Panel operativo independiente conectado a sus módulos activos.",
      "panelModules": "MÓDULOS DEL PANEL",
      "activeServices": "Servicios activos",
      "activeTenant": "Tenant activo",
      "activeNow": "Activos ahora",
      "gpsInside": "GPS dentro",
      "deliveredMaterial": "Material entregado",
      "lowStock": "Stock bajo",
      "activeModules": "módulos activos",

      "dashboard": "Dashboard",
      "inventory": "Inventario",
      "fieldCrm": "CRM Campo",
      "payroll": "Nómina",
      "staff": "Personal",
      "workforce": "Workforce",
      "kpis": "KPIs",
      "gps": "GPS",
      "bots": "Bots",
      "materials": "Materiales",
      "reports": "Reportes",

      "stockMaterials": "STOCK Y MATERIALES",
      "liveOperationUpper": "OPERACIÓN EN VIVO",
      "payrollCalc": "CORTE Y CÁLCULO",
      "operationalStaff": "PERSONAL OPERATIVO",
      "operationalIndicators": "INDICADORES OPERATIVOS",
      "locationRoutes": "UBICACIÓN Y RUTAS",
      "requestReturn": "SOLICITUD Y DEVOLUCIÓN",
      "metricsAudit": "MÉTRICAS Y AUDITORÍA",
      "activePackage": "Activa un paquete desde Admin V2",

      "moduleInventory": "MÓDULO INVENTARIO",
      "moduleMaterials": "MÓDULO MATERIALES",
      "moduleCrm": "MÓDULO CRM CAMPO",
      "moduleWorkforce": "MÓDULO WORKFORCE",
      "modulePayroll": "MÓDULO NÓMINA",
      "moduleReports": "MÓDULO REPORTES",
      "moduleKpis": "MÓDULO KPIS",
      "moduleGps": "MÓDULO GPS",
      "moduleBots": "MÓDULO BOTS",

      "back": "Volver",
      "refresh": "Actualizar",
      "csv": "CSV",
      "create": "Crear",
      "save": "Guardar",
      "saveChanges": "Guardar cambios",
      "cancel": "Cancelar",
      "search": "Buscar",
      "detail": "Detalle",
      "returnAction": "Devolución",
      "consignment": "Consigna",
      "approve": "Aprobar",
      "reject": "Rechazar",
      "deliver": "Entregar",
      "disable": "Deshabilitar",
      "exportCsv": "Exportar CSV",

      "summary": "RESUMEN",
      "inventoryStatus": "Estado del inventario",
      "active": "Activo",
      "activePlural": "Activos",
      "inactive": "Inactivo",
      "inactivePlural": "Inactivos",
      "archived": "Archivado",
      "archivedPlural": "Archivados",
      "total": "Total",
      "totalUpper": "TOTAL",
      "totalRecords": "Total registros",
      "created": "Creados",
      "edited": "Editados",
      "available": "Disponibilidad",
      "stock": "Stock",
      "currentStock": "Stock actual",
      "minimumStock": "Stock mínimo",

      "inventoryHero": "Catálogo operativo, mínimos y stock actual de solo lectura. Materiales descontará o devolverá stock en la siguiente integración.",
      "createMaterialProduct": "Crear material / producto",
      "modifyMaterial": "Modificar material",
      "createMaterialProductUpper": "CREAR MATERIAL / PRODUCTO",
      "newInventoryRecord": "Nuevo registro de inventario",
      "inventoryCreateHelp": "El stock actual se crea desde la cantidad inicial como movimiento. Luego solo cambia por entradas, entregas y devoluciones.",
      "nameReference": "NOMBRE / REFERENCIA",
      "nameReferenceMixed": "Nombre / referencia",
      "nameReferenceRequired": "Nombre / referencia es obligatorio.",
      "size": "TAMAÑO",
      "color": "COLOR",
      "initialQuantity": "CANTIDAD INICIAL",
      "minimumAlert": "MÍNIMO ALERTA",
      "enterQuantity": "Ingresar cantidad",
      "entry": "Entrada",
      "entries": "Entradas",
      "outputs": "Salidas",
      "inventoryMovements": "Movimientos inventario",
      "criticalInventory": "Inventario crítico",

      "crmHero": "Vista viva de colaboradores en turno, pausas y núcleos activos de la empresa.",
      "currentOperationalStatus": "ESTADO OPERATIVO ACTUAL",
      "operationLive": "Operación en vivo",
      "onBreak": "En pausa",
      "collaboratorsUpper": "COLABORADORES",
      "collaboratorStatus": "Estado por colaborador",
      "collaborator": "Colaborador",
      "collaborators": "Colaboradores",
      "offShift": "Fuera de turno",
      "timer": "Cronómetro",
      "noRequest": "Sin solicitud",
      "noTask": "Sin tarea",
      "noShift": "Sin turno",
      "noLocation": "Sin ubicación",
      "gpsStatus": "Estado GPS",
      "insidePerimeter": "Dentro de perímetro",
      "outsidePerimeter": "Fuera de perímetro",

      "staffHero": "Gestiona empleados, técnicos, supervisores y roles conectados a bot, nómina y operación.",
      "staffTitle": "Registro de personal operativo",
      "staffSubtitle": "administra su personal de forma independiente.",
      "editableTable": "TABLA EDITABLE",
      "addRow": "Agregar fila",
      "addStaff": "Agregar personal",
      "history": "Historial",
      "searchMatches": "Buscar coincidencias: nombre, rol, teléfono, correo, Telegram, estado...",
      "all": "Todos",
      "showing": "Mostrando",
      "records": "registros",
      "name": "Nombre",
      "nameUpper": "NOMBRE",
      "fullName": "Nombre completo",
      "role": "Rol",
      "roleUpper": "ROL",
      "phone": "Teléfono",
      "phoneUpper": "TELÉFONO",
      "email": "Correo",
      "emailUpper": "CORREO",
      "telegramId": "Telegram ID",
      "telegramIdUpper": "TELEGRAM ID",
      "hireDate": "Fecha ingreso",
      "hireDateUpper": "FECHA INGRESO",
      "regularHour": "Hora ordinaria",
      "regularHourUpper": "HORA ORDINARIA",
      "extraHour": "Hora extra",
      "extraHourUpper": "HORA EXTRA",
      "discount1": "Descuento 1",
      "discount1Upper": "DESCUENTO 1",
      "discount2": "Descuento 2",
      "discount2Upper": "DESCUENTO 2",
      "status": "Estado",
      "statusUpper": "ESTADO",
      "actions": "Acciones",
      "actionsUpper": "ACCIONES",
      "activate": "Activar",
      "deactivate": "Inactivar",
      "delete": "Eliminar",
      "supervisor": "Supervisor",
      "operator": "Operador",
      "technician": "Técnico",
      "adminCompany": "Admin empresa",
      "employee": "Empleado",
      "event": "Evento",
      "field": "Campo",
      "oldValue": "Valor anterior",
      "newValue": "Valor nuevo",
      "source": "Fuente",
      "notes": "Notas",
      "noHistoryRecords": "No hay registros de historial para los filtros seleccionados.",
      "personalSaved": "Personal guardado correctamente.",
      "employeeCreated": "Empleado creado",
      "employeeEdited": "Empleado editado",
      "employeeActivated": "Empleado activado",
      "employeeDeactivated": "Empleado inactivado",
      "employeeArchived": "Empleado archivado",
      "employeeRestored": "Empleado restaurado",

      "materialsHero": "Órdenes de salida conectadas a Inventario. Entregar descuenta stock; devolver exige número de orden.",
      "operationalCycle": "CICLO OPERATIVO",
      "materialOrders": "Órdenes de materiales",
      "pending": "Pendientes",
      "approved": "Aprobadas",
      "delivered": "Entregadas",
      "returned": "Devueltas",
      "order": "Orden",
      "orderUpper": "ORDEN",
      "requester": "Solicitante",
      "requesterUpper": "SOLICITANTE",
      "material": "Material",
      "materialUpper": "MATERIAL",
      "quantity": "Cantidad",
      "quantityUpper": "CANTIDAD",
      "destination": "Destino",
      "destinationUpper": "DESTINO",
      "outputManagement": "GESTIÓN DE SALIDA",
      "materialStatus": "Materiales por estado",
      "requestedMaterials": "Materiales más solicitados",
      "orderApproval": "Aprobación de orden",
      "approvalObservation": "Observación de aprobación",
      "saveApproval": "Guardar aprobación",
      "registerConsignment": "Registrar consigna",
      "registerReturn": "Registrar devolución",
      "returnByOrder": "Registrar devolución por número de orden",
      "consignmentByOrder": "Registrar consigna por número de orden",
      "orderNumber": "Número de orden",
      "destinationPlace": "Lugar de destino",
      "reasonState": "Motivo / estado del material",
      "consignmentReason": "Motivo de consigna / responsable / próximo turno",
      "delivery": "Entrega",
      "deliveredOne": "Entregado",
      "returnedOne": "Devuelto",
      "partialReturned": "Devuelta parcial",
      "totalReturned": "Devuelta total",
      "partialConsigned": "Consignada parcial",
      "totalConsigned": "Consignada total",
      "noMaterialOrders": "No hay órdenes de materiales.",

      "payrollHero": "Nómina consume Workforce, Bot y Asistencia. Al finalizar un corte, exporta CSV para guardar el histórico externo del periodo.",
      "calculatePeriod": "Calcular periodo",
      "period": "Periodo",
      "periodCalculated": "Periodo calculado",
      "cutClose": "Cierre del corte",
      "payrollSummary": "Resumen de nómina",
      "ordinaryHours": "Horas ordinarias",
      "extraHours": "Horas extra",
      "discounts": "Descuentos",
      "gross": "Bruto",
      "estimatedTotal": "Total estimado",
      "estimatedNetTotal": "Total neto estimado",
      "payrollTotal": "Total nómina",
      "closedShifts": "Colaboradores con cierre",
      "noClosedShifts": "No hay turnos cerrados para el periodo seleccionado.",
      "exportOnlyNotice": "Consulta cortes por periodo y conserva el resultado exportando CSV.",

      "kpisHero": "Indicadores ejecutivos calculados desde Workforce, GPS, Materiales, Inventario y Nómina según módulos activos.",
      "operationalKpis": "KPIs Operativos",
      "executiveIndicators": "Indicadores ejecutivos",
      "periodIndicators": "Indicadores del periodo",
      "riskAlerts": "Riesgos operativos",
      "topOperation": "Top operativo",
      "smartSearch": "Lupa inteligente",
      "autoRefresh": "Actualización automática cada 60s · Fuente: datos reales por módulo",
      "searchKpi": "Buscar KPI",
      "noCriticalAlerts": "Sin alertas críticas en el periodo.",

      "reportsHero": "Histórico consolidado de Personal, GPS, Materiales, Inventario y Nómina. No modifica datos; solo audita y exporta.",
      "executiveSummary": "Resumen ejecutivo",
      "operationalDetail": "Detalle operativo",
      "auditableTables": "Tablas auditables",
      "generalReport": "Reporte general",
      "personReport": "Reporte por persona",
      "byPerson": "Por persona",
      "general": "General",
      "selectEmployeeReport": "Selecciona empleado para reporte por persona",
      "auditOperation": "Auditoría operativa",
      "assistance": "Asistencia",
      "bitacora": "Bitácora operativa de marcaciones e interacciones del personal: bot, panel, QR, solicitudes, observaciones y eventos por empresa.",
      "noEvents": "No hay eventos para los filtros seleccionados.",
      "noDataFilters": "Sin datos para los filtros seleccionados.",
      "noDataChart": "Sin datos para graficar.",

      "gpsSummary": "Resumen GPS",
      "perimeters": "Perímetros",
      "allowedParameters": "Parámetros permitidos",
      "savePerimeters": "Guardar perímetros",
      "gpsSaved": "Perímetros GPS guardados.",
      "pointName": "Nombre punto",
      "latFrom": "Latitud desde",
      "latTo": "Latitud hasta",
      "lngFrom": "Longitud desde",
      "lngTo": "Longitud hasta",
      "showInPanel": "Mostrar en panel",
      "gpsConfigHelp": "Configura hasta 5 perímetros permitidos. CLONEXA valida las ubicaciones recibidas por el bot.",
      "botOnlyLocation": "El bot solo envía ubicación. La validación dentro/fuera la hace CLONEXA con estos parámetros.",

      "botTelegram": "Bot Telegram",
      "botInternalName": "Nombre interno del bot",
      "saveName": "Guardar nombre",
      "botNameUpdated": "Nombre del bot actualizado.",
      "technicalConfig": "Configuración técnica administrada desde CLONEXA Admin V2.",
      "channelStatus": "Estado operativo del canal configurado para esta empresa.",
      "operationalChannel": "Canal operativo",

      "settings": "Configuración",
      "logout": "Salir",
      "language": "Idioma",
      "session": "Sesión",
      "account": "Cuenta"
    },

    en: {
      "initializingCompanyPanel": "Initializing Company Panel",
      "connectingBos": "Connecting to the business operating system...",
      "businessOperatingSystem": "BUSINESS OPERATING SYSTEM",
      "independentPanel": "Independent operations panel connected to its active modules.",
      "panelModules": "PANEL MODULES",
      "activeServices": "Active services",
      "activeTenant": "Active tenant",
      "activeNow": "Active now",
      "gpsInside": "GPS inside",
      "deliveredMaterial": "Delivered material",
      "lowStock": "Low stock",
      "activeModules": "active modules",

      "dashboard": "Dashboard",
      "inventory": "Inventory",
      "fieldCrm": "Field CRM",
      "payroll": "Payroll",
      "staff": "Staff",
      "workforce": "Workforce",
      "kpis": "KPIs",
      "gps": "GPS",
      "bots": "Bots",
      "materials": "Materials",
      "reports": "Reports",

      "stockMaterials": "STOCK AND MATERIALS",
      "liveOperationUpper": "LIVE OPERATION",
      "payrollCalc": "CUTOFF AND CALCULATION",
      "operationalStaff": "OPERATIONAL STAFF",
      "operationalIndicators": "OPERATIONAL INDICATORS",
      "locationRoutes": "LOCATION AND ROUTES",
      "requestReturn": "REQUEST AND RETURN",
      "metricsAudit": "METRICS AND AUDIT",
      "activePackage": "Activate a package from Admin V2",

      "moduleInventory": "INVENTORY MODULE",
      "moduleMaterials": "MATERIALS MODULE",
      "moduleCrm": "FIELD CRM MODULE",
      "moduleWorkforce": "WORKFORCE MODULE",
      "modulePayroll": "PAYROLL MODULE",
      "moduleReports": "REPORTS MODULE",
      "moduleKpis": "KPIS MODULE",
      "moduleGps": "GPS MODULE",
      "moduleBots": "BOTS MODULE",

      "back": "Back",
      "refresh": "Refresh",
      "csv": "CSV",
      "create": "Create",
      "save": "Save",
      "saveChanges": "Save changes",
      "cancel": "Cancel",
      "search": "Search",
      "detail": "Detail",
      "returnAction": "Return",
      "consignment": "Consignment",
      "approve": "Approve",
      "reject": "Reject",
      "deliver": "Deliver",
      "disable": "Disable",
      "exportCsv": "Export CSV",

      "summary": "SUMMARY",
      "inventoryStatus": "Inventory status",
      "active": "Active",
      "activePlural": "Active",
      "inactive": "Inactive",
      "inactivePlural": "Inactive",
      "archived": "Archived",
      "archivedPlural": "Archived",
      "total": "Total",
      "totalUpper": "TOTAL",
      "totalRecords": "Total records",
      "created": "Created",
      "edited": "Edited",
      "available": "Availability",
      "stock": "Stock",
      "currentStock": "Current stock",
      "minimumStock": "Minimum stock",

      "inventoryHero": "Operational catalog, minimums and current read-only stock. Materials will deduct or return stock in the next integration.",
      "createMaterialProduct": "Create material / product",
      "modifyMaterial": "Modify material",
      "createMaterialProductUpper": "CREATE MATERIAL / PRODUCT",
      "newInventoryRecord": "New inventory record",
      "inventoryCreateHelp": "Current stock is created from the initial quantity as a movement. After that, it only changes through entries, deliveries and returns.",
      "nameReference": "NAME / REFERENCE",
      "nameReferenceMixed": "Name / reference",
      "nameReferenceRequired": "Name / reference is required.",
      "size": "SIZE",
      "color": "COLOR",
      "initialQuantity": "INITIAL QUANTITY",
      "minimumAlert": "MINIMUM ALERT",
      "enterQuantity": "Enter quantity",
      "entry": "Entry",
      "entries": "Entries",
      "outputs": "Outputs",
      "inventoryMovements": "Inventory movements",
      "criticalInventory": "Critical inventory",

      "crmHero": "Live view of employees on shift, breaks and active company cores.",
      "currentOperationalStatus": "CURRENT OPERATING STATUS",
      "operationLive": "Live operation",
      "onBreak": "On break",
      "collaboratorsUpper": "EMPLOYEES",
      "collaboratorStatus": "Status by employee",
      "collaborator": "Employee",
      "collaborators": "Employees",
      "offShift": "Off shift",
      "timer": "Timer",
      "noRequest": "No request",
      "noTask": "No task",
      "noShift": "No shift",
      "noLocation": "No location",
      "gpsStatus": "GPS status",
      "insidePerimeter": "Inside perimeter",
      "outsidePerimeter": "Outside perimeter",

      "staffHero": "Manage employees, technicians, supervisors and roles connected to bot, payroll and operations.",
      "staffTitle": "Operational staff registry",
      "staffSubtitle": "manages its staff independently.",
      "editableTable": "EDITABLE TABLE",
      "addRow": "Add row",
      "addStaff": "Add staff",
      "history": "History",
      "searchMatches": "Search matches: name, role, phone, email, Telegram, status...",
      "all": "All",
      "showing": "Showing",
      "records": "records",
      "name": "Name",
      "nameUpper": "NAME",
      "fullName": "Full name",
      "role": "Role",
      "roleUpper": "ROLE",
      "phone": "Phone",
      "phoneUpper": "PHONE",
      "email": "Email",
      "emailUpper": "EMAIL",
      "telegramId": "Telegram ID",
      "telegramIdUpper": "TELEGRAM ID",
      "hireDate": "Hire date",
      "hireDateUpper": "HIRE DATE",
      "regularHour": "Regular hour",
      "regularHourUpper": "REGULAR HOUR",
      "extraHour": "Extra hour",
      "extraHourUpper": "EXTRA HOUR",
      "discount1": "Discount 1",
      "discount1Upper": "DISCOUNT 1",
      "discount2": "Discount 2",
      "discount2Upper": "DISCOUNT 2",
      "status": "Status",
      "statusUpper": "STATUS",
      "actions": "Actions",
      "actionsUpper": "ACTIONS",
      "activate": "Activate",
      "deactivate": "Deactivate",
      "delete": "Delete",
      "supervisor": "Supervisor",
      "operator": "Operator",
      "technician": "Technician",
      "adminCompany": "Company admin",
      "employee": "Employee",
      "event": "Event",
      "field": "Field",
      "oldValue": "Old value",
      "newValue": "New value",
      "source": "Source",
      "notes": "Notes",
      "noHistoryRecords": "No history records match the selected filters.",
      "personalSaved": "Staff saved successfully.",
      "employeeCreated": "Employee created",
      "employeeEdited": "Employee edited",
      "employeeActivated": "Employee activated",
      "employeeDeactivated": "Employee deactivated",
      "employeeArchived": "Employee archived",
      "employeeRestored": "Employee restored",

      "materialsHero": "Outbound orders connected to Inventory. Delivery deducts stock; return requires an order number.",
      "operationalCycle": "OPERATING CYCLE",
      "materialOrders": "Material orders",
      "pending": "Pending",
      "approved": "Approved",
      "delivered": "Delivered",
      "returned": "Returned",
      "order": "Order",
      "orderUpper": "ORDER",
      "requester": "Requester",
      "requesterUpper": "REQUESTER",
      "material": "Material",
      "materialUpper": "MATERIAL",
      "quantity": "Quantity",
      "quantityUpper": "QUANTITY",
      "destination": "Destination",
      "destinationUpper": "DESTINATION",
      "outputManagement": "OUTPUT MANAGEMENT",
      "materialStatus": "Materials by status",
      "requestedMaterials": "Most requested materials",
      "orderApproval": "Order approval",
      "approvalObservation": "Approval note",
      "saveApproval": "Save approval",
      "registerConsignment": "Register consignment",
      "registerReturn": "Register return",
      "returnByOrder": "Register return by order number",
      "consignmentByOrder": "Register consignment by order number",
      "orderNumber": "Order number",
      "destinationPlace": "Destination place",
      "reasonState": "Material reason / status",
      "consignmentReason": "Consignment reason / responsible / next shift",
      "delivery": "Delivery",
      "deliveredOne": "Delivered",
      "returnedOne": "Returned",
      "partialReturned": "Partially returned",
      "totalReturned": "Fully returned",
      "partialConsigned": "Partially consigned",
      "totalConsigned": "Fully consigned",
      "noMaterialOrders": "There are no material orders.",

      "payrollHero": "Payroll uses Workforce, Bot and Attendance. When closing a period, export CSV to keep the external history.",
      "calculatePeriod": "Calculate period",
      "period": "Period",
      "periodCalculated": "Period calculated",
      "cutClose": "Cutoff close",
      "payrollSummary": "Payroll summary",
      "ordinaryHours": "Ordinary hours",
      "extraHours": "Extra hours",
      "discounts": "Discounts",
      "gross": "Gross",
      "estimatedTotal": "Estimated total",
      "estimatedNetTotal": "Estimated net total",
      "payrollTotal": "Payroll total",
      "closedShifts": "Employees with checkout",
      "noClosedShifts": "There are no closed shifts for the selected period.",
      "exportOnlyNotice": "Query periods and keep the result by exporting CSV.",

      "kpisHero": "Executive indicators calculated from Workforce, GPS, Materials, Inventory and Payroll according to active modules.",
      "operationalKpis": "Operational KPIs",
      "executiveIndicators": "Executive indicators",
      "periodIndicators": "Period indicators",
      "riskAlerts": "Operational risks",
      "topOperation": "Operational top",
      "smartSearch": "Smart search",
      "autoRefresh": "Automatic refresh every 60s · Source: real module data",
      "searchKpi": "Search KPI",
      "noCriticalAlerts": "No critical alerts in the period.",

      "reportsHero": "Consolidated history of Staff, GPS, Materials, Inventory and Payroll. It does not modify data; it only audits and exports.",
      "executiveSummary": "Executive summary",
      "operationalDetail": "Operational detail",
      "auditableTables": "Auditable tables",
      "generalReport": "General report",
      "personReport": "Person report",
      "byPerson": "By person",
      "general": "General",
      "selectEmployeeReport": "Select employee for person report",
      "auditOperation": "Operational audit",
      "assistance": "Attendance",
      "bitacora": "Operational log of staff check-ins and interactions: bot, panel, QR, requests, notes and company events.",
      "noEvents": "There are no events for the selected filters.",
      "noDataFilters": "No data for the selected filters.",
      "noDataChart": "No data to chart.",

      "gpsSummary": "GPS summary",
      "perimeters": "Perimeters",
      "allowedParameters": "Allowed parameters",
      "savePerimeters": "Save perimeters",
      "gpsSaved": "GPS perimeters saved.",
      "pointName": "Point name",
      "latFrom": "Latitude from",
      "latTo": "Latitude to",
      "lngFrom": "Longitude from",
      "lngTo": "Longitude to",
      "showInPanel": "Show in panel",
      "gpsConfigHelp": "Configure up to 5 allowed perimeters. CLONEXA validates bot locations with these parameters.",
      "botOnlyLocation": "The bot only sends location. CLONEXA validates inside/outside using these parameters.",

      "botTelegram": "Telegram Bot",
      "botInternalName": "Internal bot name",
      "saveName": "Save name",
      "botNameUpdated": "Bot name updated.",
      "technicalConfig": "Technical configuration managed from CLONEXA Admin V2.",
      "channelStatus": "Operational status of the channel configured for this company.",
      "operationalChannel": "Operational channel",

      "settings": "Settings",
      "logout": "Log out",
      "language": "Language",
      "session": "Session",
      "account": "Account"
    },

    fr: {
      "initializingCompanyPanel": "Initialisation du panneau entreprise",
      "connectingBos": "Connexion au système opérationnel d’entreprise...",
      "businessOperatingSystem": "SYSTÈME OPÉRATIONNEL D’ENTREPRISE",
      "independentPanel": "Panneau opérationnel indépendant connecté à ses modules actifs.",
      "panelModules": "MODULES DU PANNEAU",
      "activeServices": "Services actifs",
      "activeTenant": "Tenant actif",
      "activeNow": "Actifs maintenant",
      "gpsInside": "GPS à l’intérieur",
      "deliveredMaterial": "Matériel livré",
      "lowStock": "Stock faible",
      "activeModules": "modules actifs",

      "dashboard": "Tableau de bord",
      "inventory": "Inventaire",
      "fieldCrm": "CRM Terrain",
      "payroll": "Paie",
      "staff": "Personnel",
      "workforce": "Workforce",
      "kpis": "KPIs",
      "gps": "GPS",
      "bots": "Bots",
      "materials": "Matériaux",
      "reports": "Rapports",

      "stockMaterials": "STOCK ET MATÉRIAUX",
      "liveOperationUpper": "OPÉRATION EN DIRECT",
      "payrollCalc": "CLÔTURE ET CALCUL",
      "operationalStaff": "PERSONNEL OPÉRATIONNEL",
      "operationalIndicators": "INDICATEURS OPÉRATIONNELS",
      "locationRoutes": "LOCALISATION ET ITINÉRAIRES",
      "requestReturn": "DEMANDE ET RETOUR",
      "metricsAudit": "MÉTRIQUES ET AUDIT",
      "activePackage": "Activez un forfait depuis Admin V2",

      "moduleInventory": "MODULE INVENTAIRE",
      "moduleMaterials": "MODULE MATÉRIAUX",
      "moduleCrm": "MODULE CRM TERRAIN",
      "moduleWorkforce": "MODULE PERSONNEL",
      "modulePayroll": "MODULE PAIE",
      "moduleReports": "MODULE RAPPORTS",
      "moduleKpis": "MODULE KPIS",
      "moduleGps": "MODULE GPS",
      "moduleBots": "MODULE BOTS",

      "back": "Retour",
      "refresh": "Actualiser",
      "csv": "CSV",
      "create": "Créer",
      "save": "Enregistrer",
      "saveChanges": "Enregistrer",
      "cancel": "Annuler",
      "search": "Rechercher",
      "detail": "Détail",
      "returnAction": "Retour",
      "consignment": "Consigne",
      "approve": "Approuver",
      "reject": "Rejeter",
      "deliver": "Livrer",
      "disable": "Désactiver",
      "exportCsv": "Exporter CSV",

      "summary": "RÉSUMÉ",
      "inventoryStatus": "État de l’inventaire",
      "active": "Actif",
      "activePlural": "Actifs",
      "inactive": "Inactif",
      "inactivePlural": "Inactifs",
      "archived": "Archivé",
      "archivedPlural": "Archivés",
      "total": "Total",
      "totalUpper": "TOTAL",
      "totalRecords": "Total des enregistrements",
      "created": "Créés",
      "edited": "Modifiés",
      "available": "Disponibilité",
      "stock": "Stock",
      "currentStock": "Stock actuel",
      "minimumStock": "Stock minimum",

      "inventoryHero": "Catalogue opérationnel, minimums et stock actuel en lecture seule. Les matériaux déduiront ou retourneront le stock lors de la prochaine intégration.",
      "createMaterialProduct": "Créer matériau / produit",
      "modifyMaterial": "Modifier matériau",
      "createMaterialProductUpper": "CRÉER MATÉRIAU / PRODUIT",
      "newInventoryRecord": "Nouvel enregistrement d’inventaire",
      "inventoryCreateHelp": "Le stock actuel est créé à partir de la quantité initiale comme mouvement. Ensuite, il ne change que par entrées, livraisons et retours.",
      "nameReference": "NOM / RÉFÉRENCE",
      "nameReferenceMixed": "Nom / référence",
      "nameReferenceRequired": "Nom / référence obligatoire.",
      "size": "TAILLE",
      "color": "COULEUR",
      "initialQuantity": "QUANTITÉ INITIALE",
      "minimumAlert": "ALERTE MINIMUM",
      "enterQuantity": "Saisir quantité",
      "entry": "Entrée",
      "entries": "Entrées",
      "outputs": "Sorties",
      "inventoryMovements": "Mouvements inventaire",
      "criticalInventory": "Inventaire critique",

      "crmHero": "Vue en direct des collaborateurs en service, pauses et noyaux actifs de l’entreprise.",
      "currentOperationalStatus": "ÉTAT OPÉRATIONNEL ACTUEL",
      "operationLive": "Opération en direct",
      "onBreak": "En pause",
      "collaboratorsUpper": "COLLABORATEURS",
      "collaboratorStatus": "Statut par collaborateur",
      "collaborator": "Collaborateur",
      "collaborators": "Collaborateurs",
      "offShift": "Hors service",
      "timer": "Chronomètre",
      "noRequest": "Aucune demande",
      "noTask": "Aucune tâche",
      "noShift": "Aucun service",
      "noLocation": "Aucune localisation",
      "gpsStatus": "Statut GPS",
      "insidePerimeter": "Dans le périmètre",
      "outsidePerimeter": "Hors périmètre",

      "staffHero": "Gérez les employés, techniciens, superviseurs et rôles connectés au bot, à la paie et aux opérations.",
      "staffTitle": "Registre du personnel opérationnel",
      "staffSubtitle": "gère son personnel de manière indépendante.",
      "editableTable": "TABLEAU MODIFIABLE",
      "addRow": "Ajouter une ligne",
      "addStaff": "Ajouter du personnel",
      "history": "Historique",
      "searchMatches": "Rechercher : nom, rôle, téléphone, e-mail, Telegram, statut...",
      "all": "Tous",
      "showing": "Affichage",
      "records": "enregistrements",
      "name": "Nom",
      "nameUpper": "NOM",
      "fullName": "Nom complet",
      "role": "Rôle",
      "roleUpper": "RÔLE",
      "phone": "Téléphone",
      "phoneUpper": "TÉLÉPHONE",
      "email": "E-mail",
      "emailUpper": "E-MAIL",
      "telegramId": "Telegram ID",
      "telegramIdUpper": "TELEGRAM ID",
      "hireDate": "Date d’entrée",
      "hireDateUpper": "DATE D’ENTRÉE",
      "regularHour": "Heure normale",
      "regularHourUpper": "HEURE NORMALE",
      "extraHour": "Heure supplémentaire",
      "extraHourUpper": "HEURE SUPPLÉMENTAIRE",
      "discount1": "Remise 1",
      "discount1Upper": "REMISE 1",
      "discount2": "Remise 2",
      "discount2Upper": "REMISE 2",
      "status": "Statut",
      "statusUpper": "STATUT",
      "actions": "Actions",
      "actionsUpper": "ACTIONS",
      "activate": "Activer",
      "deactivate": "Désactiver",
      "delete": "Supprimer",
      "supervisor": "Superviseur",
      "operator": "Opérateur",
      "technician": "Technicien",
      "adminCompany": "Admin entreprise",
      "employee": "Employé",
      "event": "Événement",
      "field": "Champ",
      "oldValue": "Ancienne valeur",
      "newValue": "Nouvelle valeur",
      "source": "Source",
      "notes": "Notes",
      "noHistoryRecords": "Aucun historique ne correspond aux filtres sélectionnés.",
      "personalSaved": "Personnel enregistré correctement.",
      "employeeCreated": "Employé créé",
      "employeeEdited": "Employé modifié",
      "employeeActivated": "Employé activé",
      "employeeDeactivated": "Employé désactivé",
      "employeeArchived": "Employé archivé",
      "employeeRestored": "Employé restauré",

      "materialsHero": "Ordres de sortie connectés à l’inventaire. La livraison déduit le stock ; le retour exige un numéro d’ordre.",
      "operationalCycle": "CYCLE OPÉRATIONNEL",
      "materialOrders": "Ordres de matériaux",
      "pending": "En attente",
      "approved": "Approuvées",
      "delivered": "Livrées",
      "returned": "Retournées",
      "order": "Ordre",
      "orderUpper": "ORDRE",
      "requester": "Demandeur",
      "requesterUpper": "DEMANDEUR",
      "material": "Matériel",
      "materialUpper": "MATÉRIEL",
      "quantity": "Quantité",
      "quantityUpper": "QUANTITÉ",
      "destination": "Destination",
      "destinationUpper": "DESTINATION",
      "outputManagement": "GESTION DE SORTIE",
      "materialStatus": "Matériaux par statut",
      "requestedMaterials": "Matériaux les plus demandés",
      "orderApproval": "Approbation de l’ordre",
      "approvalObservation": "Note d’approbation",
      "saveApproval": "Enregistrer approbation",
      "registerConsignment": "Enregistrer consigne",
      "registerReturn": "Enregistrer retour",
      "returnByOrder": "Enregistrer retour par numéro d’ordre",
      "consignmentByOrder": "Enregistrer consigne par numéro d’ordre",
      "orderNumber": "Numéro d’ordre",
      "destinationPlace": "Lieu de destination",
      "reasonState": "Motif / statut du matériel",
      "consignmentReason": "Motif de consigne / responsable / prochain service",
      "delivery": "Livraison",
      "deliveredOne": "Livré",
      "returnedOne": "Retourné",
      "partialReturned": "Retour partiel",
      "totalReturned": "Retour total",
      "partialConsigned": "Consigne partielle",
      "totalConsigned": "Consigne totale",
      "noMaterialOrders": "Il n’y a pas d’ordres de matériaux.",

      "payrollHero": "La paie utilise Workforce, Bot et Assistance. À la clôture d’une période, exportez CSV pour conserver l’historique externe.",
      "calculatePeriod": "Calculer période",
      "period": "Période",
      "periodCalculated": "Période calculée",
      "cutClose": "Clôture de période",
      "payrollSummary": "Résumé de paie",
      "ordinaryHours": "Heures ordinaires",
      "extraHours": "Heures supplémentaires",
      "discounts": "Remises",
      "gross": "Brut",
      "estimatedTotal": "Total estimé",
      "estimatedNetTotal": "Total net estimé",
      "payrollTotal": "Total paie",
      "closedShifts": "Collaborateurs avec sortie",
      "noClosedShifts": "Il n’y a pas de services clôturés pour la période sélectionnée.",
      "exportOnlyNotice": "Consultez les périodes et conservez le résultat en exportant CSV.",

      "kpisHero": "Indicateurs exécutifs calculés depuis Workforce, GPS, Matériaux, Inventaire et Paie selon les modules actifs.",
      "operationalKpis": "KPIs opérationnels",
      "executiveIndicators": "Indicateurs exécutifs",
      "periodIndicators": "Indicateurs de période",
      "riskAlerts": "Risques opérationnels",
      "topOperation": "Top opérationnel",
      "smartSearch": "Recherche intelligente",
      "autoRefresh": "Actualisation automatique toutes les 60s · Source : données réelles par module",
      "searchKpi": "Rechercher KPI",
      "noCriticalAlerts": "Aucune alerte critique sur la période.",

      "reportsHero": "Historique consolidé du personnel, GPS, matériaux, inventaire et paie. Il ne modifie pas les données ; il audite et exporte uniquement.",
      "executiveSummary": "Résumé exécutif",
      "operationalDetail": "Détail opérationnel",
      "auditableTables": "Tableaux auditables",
      "generalReport": "Rapport général",
      "personReport": "Rapport par personne",
      "byPerson": "Par personne",
      "general": "Général",
      "selectEmployeeReport": "Sélectionner un employé pour le rapport par personne",
      "auditOperation": "Audit opérationnel",
      "assistance": "Assistance",
      "bitacora": "Journal opérationnel des pointages et interactions du personnel : bot, panneau, QR, demandes, notes et événements d’entreprise.",
      "noEvents": "Aucun événement pour les filtres sélectionnés.",
      "noDataFilters": "Aucune donnée pour les filtres sélectionnés.",
      "noDataChart": "Aucune donnée à afficher.",

      "gpsSummary": "Résumé GPS",
      "perimeters": "Périmètres",
      "allowedParameters": "Paramètres autorisés",
      "savePerimeters": "Enregistrer périmètres",
      "gpsSaved": "Périmètres GPS enregistrés.",
      "pointName": "Nom du point",
      "latFrom": "Latitude depuis",
      "latTo": "Latitude jusqu’à",
      "lngFrom": "Longitude depuis",
      "lngTo": "Longitude jusqu’à",
      "showInPanel": "Afficher dans le panneau",
      "gpsConfigHelp": "Configurez jusqu’à 5 périmètres autorisés. CLONEXA valide les localisations du bot avec ces paramètres.",
      "botOnlyLocation": "Le bot envoie uniquement la localisation. CLONEXA valide intérieur/extérieur avec ces paramètres.",

      "botTelegram": "Bot Telegram",
      "botInternalName": "Nom interne du bot",
      "saveName": "Enregistrer nom",
      "botNameUpdated": "Nom du bot mis à jour.",
      "technicalConfig": "Configuration technique gérée depuis CLONEXA Admin V2.",
      "channelStatus": "Statut opérationnel du canal configuré pour cette entreprise.",
      "operationalChannel": "Canal opérationnel",

      "settings": "Configuration",
      "logout": "Quitter",
      "language": "Langue",
      "session": "Session",
      "account": "Compte"
    }
  };

  const ALIASES = {
    "Inicializando Panel Empresa": "initializingCompanyPanel",
    "Conectando con el sistema operativo empresarial...": "connectingBos",
    "Sistema operativo empresarial": "businessOperatingSystem",
    "SISTEMA OPERATIVO EMPRESARIAL": "businessOperatingSystem",
    "Panel operativo independiente conectado a sus módulos activos.": "independentPanel",
    "Panel operativo independiente conectado a sus m?dulos activos.": "independentPanel",
    "Panel operativo independiente conectado a sus mÃ³dulos activos.": "independentPanel",
    "MÓDULOS DEL PANEL": "panelModules",
    "M?DULOS DEL PANEL": "panelModules",
    "MÃ³DULOS DEL PANEL": "panelModules",
    "Servicios activos": "activeServices",
    "Tenant activo": "activeTenant",
    "Activos ahora": "activeNow",
    "GPS dentro": "gpsInside",
    "Material entregado": "deliveredMaterial",
    "Stock bajo": "lowStock",

    "Dashboard": "dashboard",
    "Inventario": "inventory",
    "Inventory": "inventory",
    "CRM Campo": "fieldCrm",
    "Field CRM": "fieldCrm",
    "Nómina": "payroll",
    "Nomina": "payroll",
    "Payroll": "payroll",
    "Personal": "staff",
    "Staff": "staff",
    "Workforce": "staff",
    "KPIs": "kpis",
    "GPS": "gps",
    "Bots": "bots",
    "Materiales": "materials",
    "Materials": "materials",
    "Reportes": "reports",
    "Reports": "reports",

    "STOCK Y MATERIALES": "stockMaterials",
    "OPERACION EN VIVO": "liveOperationUpper",
    "OPERACIÓN EN VIVO": "liveOperationUpper",
    "CORTE Y CALCULO": "payrollCalc",
    "CORTE Y CÁLCULO": "payrollCalc",
    "PERSONAL OPERATIVO": "operationalStaff",
    "OPERATIONAL STAFF": "operationalStaff",
    "INDICADORES OPERATIVOS": "operationalIndicators",
    "OPERATIONAL INDICATORS": "operationalIndicators",
    "UBICACION Y RUTAS": "locationRoutes",
    "UBICACIÓN Y RUTAS": "locationRoutes",
    "SOLICITUD Y DEVOLUCION": "requestReturn",
    "SOLICITUD Y DEVOLUCIÓN": "requestReturn",
    "METRICAS Y AUDITORIA": "metricsAudit",
    "MÉTRICAS Y AUDITORÍA": "metricsAudit",
    "Activa un paquete desde Admin V2": "activePackage",

    "Modulo Inventario": "moduleInventory",
    "Módulo Inventario": "moduleInventory",
    "MODULO INVENTARIO": "moduleInventory",
    "MÓDULO INVENTARIO": "moduleInventory",
    "Modulo Materiales": "moduleMaterials",
    "Módulo Materiales": "moduleMaterials",
    "MODULO MATERIALES": "moduleMaterials",
    "MÓDULO MATERIALES": "moduleMaterials",
    "Modulo CRM Campo": "moduleCrm",
    "Módulo CRM Campo": "moduleCrm",
    "MODULO CRM CAMPO": "moduleCrm",
    "MÓDULO CRM CAMPO": "moduleCrm",
    "Modulo Workforce": "moduleWorkforce",
    "Módulo Workforce": "moduleWorkforce",
    "MODULO WORKFORCE": "moduleWorkforce",
    "MÓDULO WORKFORCE": "moduleWorkforce",
    "Modulo Nómina": "modulePayroll",
    "Módulo Nómina": "modulePayroll",
    "MÃ³dulo NÃ³mina": "modulePayroll",
    "MODULO NÓMINA": "modulePayroll",
    "MÓDULO NÓMINA": "modulePayroll",
    "Modulo Reportes": "moduleReports",
    "Módulo Reportes": "moduleReports",
    "MÃ³dulo Reportes": "moduleReports",
    "MODULO REPORTES": "moduleReports",
    "MÓDULO REPORTES": "moduleReports",
    "Módulo KPIs": "moduleKpis",
    "MODULO KPIS": "moduleKpis",
    "MÓDULO KPIS": "moduleKpis",
    "Modulo GPS": "moduleGps",
    "Módulo GPS": "moduleGps",
    "MODULO GPS": "moduleGps",
    "MÓDULO GPS": "moduleGps",
    "Modulo Bots": "moduleBots",
    "Módulo Bots": "moduleBots",
    "MODULO BOTS": "moduleBots",
    "MÓDULO BOTS": "moduleBots",

    "Volver": "back",
    "Back": "back",
    "Actualizar": "refresh",
    "Refresh": "refresh",
    "CSV": "csv",
    "Crear": "create",
    "Guardar": "save",
    "Save": "save",
    "Guardar cambios": "saveChanges",
    "Save changes": "saveChanges",
    "Cancelar": "cancel",
    "Buscar": "search",
    "Detalle": "detail",
    "Detail": "detail",
    "Devolución": "returnAction",
    "Devolucion": "returnAction",
    "Return": "returnAction",
    "Consigna": "consignment",
    "Aprobar": "approve",
    "Rechazar": "reject",
    "Entregar": "deliver",
    "Deshabilitar": "disable",
    "Exportar CSV": "exportCsv",

    "Resumen": "summary",
    "RESUMEN": "summary",
    "Estado del inventario": "inventoryStatus",
    "Activo": "active",
    "Active": "active",
    "Activos": "activePlural",
    "Inactivo": "inactive",
    "Inactive": "inactive",
    "Inactivos": "inactivePlural",
    "Archivado": "archived",
    "Archived": "archived",
    "Archivados": "archivedPlural",
    "Total": "total",
    "TOTAL": "totalUpper",
    "Total registros": "totalRecords",
    "Creados": "created",
    "Editados": "edited",
    "Disponibilidad": "available",
    "Stock": "stock",
    "Stock actual": "currentStock",
    "Stock minimo": "minimumStock",
    "Stock mínimo": "minimumStock",

    "Catálogo operativo, mínimos y stock actual de solo lectura. Materiales descontará o devolverá stock en la siguiente integración.": "inventoryHero",
    "Catalogo operativo, minimos y stock actual de solo lectura. Materiales descontara o devolvera stock en la siguiente integracion.": "inventoryHero",
    "Crear material / producto": "createMaterialProduct",
    "Modificar material": "modifyMaterial",
    "CREAR MATERIAL / PRODUCTO": "createMaterialProductUpper",
    "Nuevo registro de inventario": "newInventoryRecord",
    "El stock actual se crea desde la cantidad inicial como movimiento. Luego solo cambia por entradas, entregas y devoluciones.": "inventoryCreateHelp",
    "NOMBRE / REFERENCIA": "nameReference",
    "Nombre / referencia": "nameReferenceMixed",
    "Nombre / referencia es obligatorio.": "nameReferenceRequired",
    "TAMAÑO": "size",
    "TAMANO": "size",
    "Tamaño": "size",
    "COLOR": "color",
    "Color": "color",
    "CANTIDAD INICIAL": "initialQuantity",
    "Cantidad inicial": "initialQuantity",
    "MÍNIMO ALERTA": "minimumAlert",
    "MINIMO ALERTA": "minimumAlert",
    "Mínimo alerta": "minimumAlert",
    "Ingresar cantidad": "enterQuantity",
    "Entrada": "entry",
    "Entradas": "entries",
    "Salidas": "outputs",
    "Movimientos inventario": "inventoryMovements",
    "Inventario crítico": "criticalInventory",

    "Vista viva de colaboradores en turno, pausas y núcleos activos de la empresa.": "crmHero",
    "Vista viva de colaboradores en turno, pausas y nucleos activos de la empresa.": "crmHero",
    "ESTADO OPERATIVO ACTUAL": "currentOperationalStatus",
    "Estado operativo actual": "currentOperationalStatus",
    "Operación en vivo": "operationLive",
    "Operacion en vivo": "operationLive",
    "En pausa": "onBreak",
    "COLABORADORES": "collaboratorsUpper",
    "Colaboradores": "collaborators",
    "Estado por colaborador": "collaboratorStatus",
    "Colaborador": "collaborator",
    "Fuera de turno": "offShift",
    "Cronómetro": "timer",
    "Cronometro": "timer",
    "Sin solicitud": "noRequest",
    "Sin tarea": "noTask",
    "Sin turno": "noShift",
    "Sin ubicacion": "noLocation",
    "Sin ubicación": "noLocation",
    "Estado GPS": "gpsStatus",
    "Dentro de perímetro": "insidePerimeter",
    "Fuera de perímetro": "outsidePerimeter",

    "Gestiona empleados, técnicos, supervisores y roles conectados a bot, nómina y operación.": "staffHero",
    "Gestiona empleados, tecnicos, supervisores y roles conectados a bot, nomina y operacion.": "staffHero",
    "Registro de personal operativo": "staffTitle",
    "TABLA EDITABLE": "editableTable",
    "Tabla editable": "editableTable",
    "+ Agregar fila": "addRow",
    "Agregar fila": "addRow",
    "Agregar personal": "addStaff",
    "Historial": "history",
    "Buscar coincidencias: nombre, rol, teléfono, correo, Telegram, estado...": "searchMatches",
    "Buscar coincidencias: nombre, rol, tel?fono, correo, Telegram, estado...": "searchMatches",
    "Todos": "all",
    "Mostrando": "showing",
    "registros": "records",
    "Nombre": "name",
    "NOMBRE": "nameUpper",
    "Nombre completo": "fullName",
    "Rol": "role",
    "ROL": "roleUpper",
    "Telefono": "phone",
    "Teléfono": "phone",
    "TELEFONO": "phoneUpper",
    "TELÉFONO": "phoneUpper",
    "Correo": "email",
    "CORREO": "emailUpper",
    "Telegram ID": "telegramId",
    "TELEGRAM ID": "telegramIdUpper",
    "Fecha ingreso": "hireDate",
    "FECHA INGRESO": "hireDateUpper",
    "Hora ordinaria": "regularHour",
    "HORA ORDINARIA": "regularHourUpper",
    "Hora extra": "extraHour",
    "HORA EXTRA": "extraHourUpper",
    "Descuento 1": "discount1",
    "DESCUENTO 1": "discount1Upper",
    "Descuento 2": "discount2",
    "DESCUENTO 2": "discount2Upper",
    "Estado": "status",
    "ESTADO": "statusUpper",
    "STATUS": "statusUpper",
    "Acciones": "actions",
    "ACCIONES": "actionsUpper",
    "Activar": "activate",
    "Inactivar": "deactivate",
    "Eliminar": "delete",
    "Supervisor": "supervisor",
    "Operador": "operator",
    "Tecnico": "technician",
    "Técnico": "technician",
    "Admin empresa": "adminCompany",
    "Empleado": "employee",
    "Evento": "event",
    "Campo": "field",
    "Valor anterior": "oldValue",
    "Valor nuevo": "newValue",
    "Fuente": "source",
    "Notas": "notes",
    "No hay registros de historial para los filtros seleccionados.": "noHistoryRecords",
    "Personal guardado correctamente.": "personalSaved",
    "Empleado creado": "employeeCreated",
    "Empleado editado": "employeeEdited",
    "Empleado activado": "employeeActivated",
    "Empleado inactivado": "employeeDeactivated",
    "Empleado archivado": "employeeArchived",
    "Empleado restaurado": "employeeRestored",

    "Órdenes de salida conectadas a Inventario. Entregar descuenta stock; devolver exige número de orden.": "materialsHero",
    "Ordenes de salida conectadas a Inventario. Entregar descuenta stock; devolver exige numero de orden.": "materialsHero",
    "CICLO OPERATIVO": "operationalCycle",
    "Órdenes de materiales": "materialOrders",
    "Ordenes de materiales": "materialOrders",
    "Pendientes": "pending",
    "Aprobadas": "approved",
    "Entregadas": "delivered",
    "Devueltas": "returned",
    "Orden": "order",
    "ORDEN": "orderUpper",
    "Solicitante": "requester",
    "SOLICITANTE": "requesterUpper",
    "Material": "material",
    "MATERIAL": "materialUpper",
    "Cantidad": "quantity",
    "CANTIDAD": "quantityUpper",
    "Destino": "destination",
    "DESTINO": "destinationUpper",
    "GESTIÓN DE SALIDA": "outputManagement",
    "GESTION DE SALIDA": "outputManagement",
    "Materiales por estado": "materialStatus",
    "Materiales más solicitados": "requestedMaterials",
    "Aprobación de orden": "orderApproval",
    "Observación de aprobación": "approvalObservation",
    "Guardar aprobación": "saveApproval",
    "Registrar consigna": "registerConsignment",
    "Registrar devolución": "registerReturn",
    "Registrar devolucion": "registerReturn",
    "Registrar devolución por número de orden": "returnByOrder",
    "Registrar consigna por número de orden": "consignmentByOrder",
    "Número de orden": "orderNumber",
    "Lugar de destino": "destinationPlace",
    "Motivo / estado del material": "reasonState",
    "Motivo de consigna / responsable / próximo turno": "consignmentReason",
    "Entrega": "delivery",
    "Entregado": "deliveredOne",
    "Devuelto": "returnedOne",
    "Devuelta parcial": "partialReturned",
    "Devuelta total": "totalReturned",
    "Consignada parcial": "partialConsigned",
    "Consignada total": "totalConsigned",
    "No hay órdenes de materiales.": "noMaterialOrders",

    "Nómina consume Workforce, Bot y Asistencia. Al finalizar un corte, exporta CSV para guardar el histórico externo del periodo.": "payrollHero",
    "Calcular periodo": "calculatePeriod",
    "Periodo": "period",
    "Periodo calculado": "periodCalculated",
    "Cierre del corte": "cutClose",
    "Resumen de nómina": "payrollSummary",
    "Horas ordinarias": "ordinaryHours",
    "Horas ord.": "ordinaryHours",
    "Horas extra": "extraHours",
    "Descuentos": "discounts",
    "Bruto": "gross",
    "Total estimado": "estimatedTotal",
    "Total neto estimado": "estimatedNetTotal",
    "Total nómina": "payrollTotal",
    "Total nomina": "payrollTotal",
    "Colaboradores con cierre": "closedShifts",
    "No hay turnos cerrados para el periodo seleccionado.": "noClosedShifts",
    "Consulta cortes por periodo y conserva el resultado exportando CSV.": "exportOnlyNotice",

    "Indicadores ejecutivos calculados desde Workforce, GPS, Materiales, Inventario y Nómina según módulos activos.": "kpisHero",
    "KPIs Operativos": "operationalKpis",
    "Indicadores ejecutivos": "executiveIndicators",
    "Indicadores del periodo": "periodIndicators",
    "Riesgos operativos": "riskAlerts",
    "Top operativo": "topOperation",
    "Lupa inteligente": "smartSearch",
    "Actualización automática cada 60s · Fuente: datos reales por módulo": "autoRefresh",
    "Buscar KPI": "searchKpi",
    "Sin alertas críticas en el periodo.": "noCriticalAlerts",

    "Histórico consolidado de Personal, GPS, Materiales, Inventario y Nómina. No modifica datos; solo audita y exporta.": "reportsHero",
    "HistÃ³rico consolidado de Personal, GPS, Materiales, Inventario y NÃ³mina. No modifica datos; solo audita y exporta.": "reportsHero",
    "Resumen ejecutivo": "executiveSummary",
    "Detalle operativo": "operationalDetail",
    "Tablas auditables": "auditableTables",
    "Reporte general": "generalReport",
    "Reporte por persona": "personReport",
    "Por persona": "byPerson",
    "General": "general",
    "Selecciona empleado para reporte por persona": "selectEmployeeReport",
    "Auditoría operativa": "auditOperation",
    "Auditoria operativa": "auditOperation",
    "Asistencia": "assistance",
    "Bitácora operativa de marcaciones e interacciones del personal: bot, panel, QR, solicitudes, observaciones y eventos por empresa.": "bitacora",
    "No hay eventos para los filtros seleccionados.": "noEvents",
    "Sin datos para los filtros seleccionados.": "noDataFilters",
    "Sin datos para graficar.": "noDataChart",

    "Resumen GPS": "gpsSummary",
    "Perímetros": "perimeters",
    "Perimetros": "perimeters",
    "Parámetros permitidos": "allowedParameters",
    "Parametros permitidos": "allowedParameters",
    "Guardar perímetros": "savePerimeters",
    "Perímetros GPS guardados.": "gpsSaved",
    "Nombre punto": "pointName",
    "Latitud desde": "latFrom",
    "Latitud hasta": "latTo",
    "Lng desde": "lngFrom",
    "Lng hasta": "lngTo",
    "Mostrar en panel": "showInPanel",
    "Configura hasta 5 perímetros permitidos. CLONEXA valida las ubicaciones recibidas por el bot.": "gpsConfigHelp",
    "El bot solo envía ubicación. La validación dentro/fuera la hace CLONEXA con estos parámetros.": "botOnlyLocation",

    "Bot Telegram": "botTelegram",
    "Nombre interno del bot": "botInternalName",
    "Guardar nombre": "saveName",
    "Nombre del bot actualizado.": "botNameUpdated",
    "Configuracion tecnica administrada desde CLONEXA Admin V2.": "technicalConfig",
    "Configuración técnica administrada desde CLONEXA Admin V2.": "technicalConfig",
    "Estado operativo del canal configurado para esta empresa.": "channelStatus",
    "Canal operativo": "operationalChannel",

    "Configuración": "settings",
    "Settings": "settings",
    "Salir": "logout",
    "Log out": "logout",
    "Idioma": "language",
    "Sesión": "session",
    "Cuenta": "account"
  };

  function lang() {
    const raw = String(localStorage.getItem(LANG_KEY) || document.documentElement.lang || "es").toLowerCase();
    return ["es", "en", "fr"].includes(raw) ? raw : "es";
  }

  function clean(value) {
    return String(value || "")
      .replace(/\s+/g, " ")
      .replace(/[“”]/g, '"')
      .replace(/[‘’]/g, "'")
      .trim();
  }

  function target(key) {
    const pack = TX[lang()] || TX.es;
    return pack[key] || TX.es[key] || key;
  }

  function translateText(value) {
    const raw = String(value || "");
    const c = clean(raw);

    if (!c) return raw;
    if (/^[\d\s.,:$%#@/_-]+$/.test(c)) return raw;
    if (c.includes("@")) return raw;
    if (/^[A-Z]{2,}-\d{4}/.test(c)) return raw;
    if (/^[a-f0-9-]{24,}$/i.test(c)) return raw;

    let key = ALIASES[c];

    if (!key) {
      const modules = c.match(/^(\d+)\s+(módulos activos|modulos activos|m\?dulos activos|active modules|modules actifs)$/i);
      if (modules) return `${modules[1]} ${target("activeModules")}`;

      const staffCompany = c.match(/^(.+?)\s+administra su personal de forma independiente\.?$/i);
      if (staffCompany) return `${staffCompany[1]} ${target("staffSubtitle")}`;

      const showing = c.match(/^Mostrando\s+(.+?)\s+de\s+(.+?)\s+registros\.?$/i);
      if (showing) {
        if (lang() === "en") return `Showing ${showing[1]} of ${showing[2]} records.`;
        if (lang() === "fr") return `Affichage ${showing[1]} sur ${showing[2]} enregistrements.`;
        return `Mostrando ${showing[1]} de ${showing[2]} registros.`;
      }

      return raw;
    }

    return raw.replace(c, target(key));
  }

  function skip(el) {
    if (!el || !el.tagName) return false;
    const tag = el.tagName.toLowerCase();
    if (["script", "style", "code", "pre", "textarea"].includes(tag)) return true;
    if (el.closest && el.closest("[data-clx-no-i18n]")) return true;
    return false;
  }

  function translateDom(root) {
    const base = root || document.body;
    if (!base) return;

    if (base.nodeType === Node.TEXT_NODE) {
      const next = translateText(base.nodeValue);
      if (next !== base.nodeValue) base.nodeValue = next;
      return;
    }

    if (base.nodeType !== Node.ELEMENT_NODE && base.nodeType !== Node.DOCUMENT_FRAGMENT_NODE) return;
    if (base.nodeType === Node.ELEMENT_NODE && skip(base)) return;

    const walker = document.createTreeWalker(base, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const parent = node.parentElement;
        if (!parent || skip(parent)) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });

    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);

    nodes.forEach((node) => {
      const next = translateText(node.nodeValue);
      if (next !== node.nodeValue) node.nodeValue = next;
    });

    if (base.querySelectorAll) {
      base.querySelectorAll("[placeholder], [title], [aria-label], input[type='button'], input[type='submit']").forEach((el) => {
        if (skip(el)) return;

        ["placeholder", "title", "aria-label"].forEach((attr) => {
          if (el.hasAttribute(attr)) {
            const current = el.getAttribute(attr);
            const next = translateText(current);
            if (next !== current) el.setAttribute(attr, next);
          }
        });

        if (el.matches("input[type='button'], input[type='submit']")) {
          const next = translateText(el.value);
          if (next !== el.value) el.value = next;
        }
      });
    }

    const settings = document.getElementById("clxAccountSettingsBtn");
    const logout = document.getElementById("clxAccountLogoutBtn");

    if (settings) settings.textContent = `⚙ ${target("settings")}`;
    if (logout) logout.textContent = `⏻ ${target("logout")}`;

    document.documentElement.lang = lang();
  }

  let timer = null;
  let burstTimer = null;

  function run() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => translateDom(document.body), 40);
  }

  function burst() {
    let ticks = 0;
    if (burstTimer) clearInterval(burstTimer);

    burstTimer = setInterval(() => {
      ticks += 1;
      translateDom(document.body);
      if (ticks >= 28) clearInterval(burstTimer);
    }, 250);
  }

  function setLanguage(value) {
    const selected = String(value || "es").toLowerCase();
    if (!["es", "en", "fr"].includes(selected)) return;

    localStorage.setItem(LANG_KEY, selected);
    document.documentElement.lang = selected;
    run();
    burst();
  }

  window.CLX_I18N_020A5 = {
    run,
    burst,
    setLanguage,
    t: target,
    lang
  };

  document.addEventListener("change", (event) => {
    const targetEl = event.target;
    if (targetEl && targetEl.id === "clxAccountLanguage") {
      setLanguage(targetEl.value);
    } else {
      run();
    }
  }, true);

  document.addEventListener("click", () => {
    run();
    setTimeout(run, 300);
    setTimeout(run, 900);
  }, true);

  const observer = new MutationObserver(run);

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
'''

text = text.rstrip() + "\n\n" + engine + "\n"
path.write_text(text, encoding="utf-8")

print("PATCH_OK: 020A-5 consolidated i18n engine applied")
