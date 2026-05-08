from pathlib import Path
import re

web_js = Path("app/web/client_day_closing.js")
router_path = Path("app/api/v1/router.py")
endpoint_path = Path("app/api/v1/endpoints/day_closing.py")

endpoint_code = r'''
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()


async def _ensure_day_closing_storage(db: AsyncSession) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS day_closures (
            id uuid PRIMARY KEY,
            company_id uuid NOT NULL,
            closure_type varchar(60) NOT NULL DEFAULT 'day_closing',
            closure_date date NOT NULL,
            start_time varchar(8) NOT NULL,
            end_time varchar(8) NOT NULL,
            responsible text NULL,
            status varchar(40) NOT NULL DEFAULT 'draft',
            notes text NULL,
            summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            source_modules jsonb NOT NULL DEFAULT '[]'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_day_closures_company_date
        ON day_closures (company_id, closure_date DESC, start_time, end_time)
    """))
    await db.commit()


async def _table_exists(db: AsyncSession, table_name: str) -> bool:
    result = await db.execute(
        text("SELECT to_regclass(:name) AS exists"),
        {"name": table_name},
    )
    return bool(result.scalar())


async def _columns(db: AsyncSession, table_name: str) -> set[str]:
    result = await db.execute(
        text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = :table_name
        """),
        {"table_name": table_name},
    )
    return {str(row[0]) for row in result.all()}


async def _company_has_module(db: AsyncSession, company_id: UUID, code: str) -> bool:
    """
    Validación flexible para no romper esquemas existentes.
    Si no logra detectar la relación, permite continuar porque el frontend
    ya oculta módulos no activos. Si detecta relación y no está activo, bloquea.
    """
    if not await _table_exists(db, "company_modules"):
        return True

    cm_cols = await _columns(db, "company_modules")
    active_clause = ""
    if "enabled" in cm_cols:
        active_clause = " AND COALESCE(cm.enabled, true) IS TRUE "
    elif "is_active" in cm_cols:
        active_clause = " AND COALESCE(cm.is_active, true) IS TRUE "
    elif "active" in cm_cols:
        active_clause = " AND COALESCE(cm.active, true) IS TRUE "

    if "module_code" in cm_cols:
        result = await db.execute(
            text(f"""
                SELECT 1
                FROM company_modules cm
                WHERE cm.company_id = :company_id
                  AND cm.module_code = :code
                  {active_clause}
                LIMIT 1
            """),
            {"company_id": str(company_id), "code": code},
        )
        return result.scalar() is not None

    if "code" in cm_cols:
        result = await db.execute(
            text(f"""
                SELECT 1
                FROM company_modules cm
                WHERE cm.company_id = :company_id
                  AND cm.code = :code
                  {active_clause}
                LIMIT 1
            """),
            {"company_id": str(company_id), "code": code},
        )
        return result.scalar() is not None

    joins = [
        ("modules", "module_id"),
        ("global_modules", "global_module_id"),
    ]

    for table_name, fk in joins:
        if fk not in cm_cols:
            continue
        if not await _table_exists(db, table_name):
            continue
        mod_cols = await _columns(db, table_name)
        if "id" not in mod_cols or "code" not in mod_cols:
            continue

        result = await db.execute(
            text(f"""
                SELECT 1
                FROM company_modules cm
                JOIN {table_name} m ON m.id = cm.{fk}
                WHERE cm.company_id = :company_id
                  AND m.code = :code
                  {active_clause}
                LIMIT 1
            """),
            {"company_id": str(company_id), "code": code},
        )
        return result.scalar() is not None

    return True


def _validate_time(value: Any, field: str) -> str:
    value = str(value or "").strip()
    if not re_match_time(value):
        raise HTTPException(status_code=422, detail=f"{field} inválido. Usa HH:MM.")
    return value[:5]


def re_match_time(value: str) -> bool:
    import re
    return bool(re.match(r"^\d{2}:\d{2}(:\d{2})?$", value or ""))


@router.post("/companies/{company_id}/closures")
async def save_day_closure(
    company_id: UUID,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_day_closing_storage(db)

    if not await _company_has_module(db, company_id, "day_closing"):
        raise HTTPException(status_code=403, detail="day_closing no está activo para esta empresa.")

    raw_date = payload.get("date") or payload.get("closure_date")
    try:
        closure_date = date.fromisoformat(str(raw_date))
    except Exception:
        raise HTTPException(status_code=422, detail="Fecha inválida.")

    start_time = _validate_time(payload.get("start_time"), "start_time")
    end_time = _validate_time(payload.get("end_time"), "end_time")

    closure_id = uuid4()
    status_value = str(payload.get("status") or "draft").strip()[:40]
    responsible = str(payload.get("responsible") or "").strip() or None
    notes = str(payload.get("notes") or "").strip() or None
    summary_json = payload.get("summary") or {}
    source_modules = payload.get("source_modules") or []

    await db.execute(
        text("""
            INSERT INTO day_closures (
                id,
                company_id,
                closure_type,
                closure_date,
                start_time,
                end_time,
                responsible,
                status,
                notes,
                summary_json,
                source_modules,
                created_at,
                updated_at
            )
            VALUES (
                :id,
                :company_id,
                'day_closing',
                :closure_date,
                :start_time,
                :end_time,
                :responsible,
                :status,
                :notes,
                CAST(:summary_json AS jsonb),
                CAST(:source_modules AS jsonb),
                now(),
                now()
            )
        """),
        {
            "id": str(closure_id),
            "company_id": str(company_id),
            "closure_date": closure_date.isoformat(),
            "start_time": start_time,
            "end_time": end_time,
            "responsible": responsible,
            "status": status_value,
            "notes": notes,
            "summary_json": __import__("json").dumps(summary_json, ensure_ascii=False),
            "source_modules": __import__("json").dumps(source_modules, ensure_ascii=False),
        },
    )
    await db.commit()

    return {
        "id": str(closure_id),
        "company_id": str(company_id),
        "date": closure_date.isoformat(),
        "start_time": start_time,
        "end_time": end_time,
        "status": status_value,
        "saved_at": datetime.utcnow().isoformat() + "Z",
    }


@router.get("/companies/{company_id}/closures")
async def list_day_closures(
    company_id: UUID,
    limit: int = 30,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    await _ensure_day_closing_storage(db)

    limit = max(1, min(int(limit or 30), 100))

    result = await db.execute(
        text("""
            SELECT
                id,
                company_id,
                closure_date,
                start_time,
                end_time,
                responsible,
                status,
                notes,
                summary_json,
                source_modules,
                created_at,
                updated_at
            FROM day_closures
            WHERE company_id = :company_id
            ORDER BY closure_date DESC, created_at DESC
            LIMIT :limit
        """),
        {"company_id": str(company_id), "limit": limit},
    )

    return [dict(row) for row in result.mappings().all()]
'''

endpoint_path.write_text(endpoint_code, encoding="utf-8")

router = router_path.read_text(encoding="utf-8-sig")
if "day_closing_router" not in router and "endpoints import day_closing" not in router:
    router += '''

# CLONEXA 022B day closing router
from app.api.v1.endpoints import day_closing as day_closing_router
api_router.include_router(day_closing_router.router, prefix="/day-closing", tags=["day_closing"])
'''
router_path.write_text(router, encoding="utf-8")

js_code = r'''
(function clonexaDayClosingJourney022BR2() {
  "use strict";

  if (window.__CLONEXA_022B_R2_DAY_CLOSING__) return;
  window.__CLONEXA_022B_R2_DAY_CLOSING__ = true;

  const API = "/api/v1";
  const LANG_KEY = "clonexa_client_language";

  const TXT = {
    es: {
      dashboard: "Dashboard",
      activeTenant: "Tenant activo",
      eyebrow: "Módulo cierre operativo",
      title: "Cierre de día",
      subtitle: "Genera el cierre operativo por fecha y jornada laboral. CLONEXA resume eventos reales, personal, GPS, materiales, inventario, nómina y cierres enviados por el equipo.",
      live: "CIERRE POR JORNADA",

      back: "Volver",
      generate: "Generar cierre",
      save: "Guardar cierre",
      pdf: "PDF",
      csv: "CSV",
      refresh: "Actualizar",

      control: "Control de jornada",
      date: "Fecha",
      startTime: "Hora inicio",
      endTime: "Hora fin",
      responsible: "Responsable",
      status: "Estado",
      generated: "Generado",
      notes: "Observaciones del cierre",
      notesPlaceholder: "Observaciones generales, novedades, pendientes o decisiones del cierre...",
      source: "Fuente: eventos reales filtrados por empresa, fecha y rango horario.",

      summary: "Resumen ejecutivo",
      workedPeople: "Personas con actividad",
      shiftStarts: "Turnos iniciados",
      shiftEnds: "Turnos cerrados",
      breaks: "Pausas",
      gpsEvents: "GPS enviados",
      materialEvents: "Solicitudes material",
      totalEvents: "Eventos del rango",

      chartTitle: "Actividad por tipo",
      peopleTitle: "Resumen por persona",
      closureSummaries: "Cierres enviados por el equipo",
      moduleBlocks: "Bloques por módulo activo",

      employee: "Empleado",
      role: "Rol",
      events: "Eventos",
      firstEvent: "Primer evento",
      lastEvent: "Último evento",
      summaryText: "Resumen de gestión",
      noSummary: "Sin resumen escrito en el rango.",
      noData: "Sin datos para esta jornada.",

      workforce: "Workforce",
      gps: "GPS",
      materials: "Materiales",
      inventory: "Inventario",
      payroll: "Nómina",
      bots: "Bots",
      future: "Bloques futuros",
      futureHelp: "Producción, Retail, Campo y Cierre Comercial aparecerán aquí cuando esos módulos estén activos y construidos.",

      saved: "Cierre guardado en PostgreSQL.",
      saveError: "No se pudo guardar el cierre.",
      loadError: "No se pudo generar el cierre.",
      inactiveTitle: "Módulo no activo",
      inactiveMsg: "Cierre de día no está activo para esta empresa.",
      activateFromAdmin: "Actívalo desde Admin V2 > Empresa > Módulos."
    },

    en: {
      dashboard: "Dashboard",
      activeTenant: "Active tenant",
      eyebrow: "Operational closing module",
      title: "Day closing",
      subtitle: "Generate the operational close by date and work shift. CLONEXA summarizes real events, staff, GPS, materials, inventory, payroll and team closing summaries.",
      live: "SHIFT CLOSING",

      back: "Back",
      generate: "Generate closing",
      save: "Save closing",
      pdf: "PDF",
      csv: "CSV",
      refresh: "Refresh",

      control: "Shift control",
      date: "Date",
      startTime: "Start time",
      endTime: "End time",
      responsible: "Responsible",
      status: "Status",
      generated: "Generated",
      notes: "Closing notes",
      notesPlaceholder: "General notes, updates, pending items or closing decisions...",
      source: "Source: real events filtered by company, date and time range.",

      summary: "Executive summary",
      workedPeople: "People with activity",
      shiftStarts: "Shift starts",
      shiftEnds: "Shift ends",
      breaks: "Breaks",
      gpsEvents: "GPS sent",
      materialEvents: "Material requests",
      totalEvents: "Range events",

      chartTitle: "Activity by type",
      peopleTitle: "Summary by person",
      closureSummaries: "Team closing summaries",
      moduleBlocks: "Blocks by active module",

      employee: "Employee",
      role: "Role",
      events: "Events",
      firstEvent: "First event",
      lastEvent: "Last event",
      summaryText: "Work summary",
      noSummary: "No written summary in this range.",
      noData: "No data for this shift.",

      workforce: "Workforce",
      gps: "GPS",
      materials: "Materials",
      inventory: "Inventory",
      payroll: "Payroll",
      bots: "Bots",
      future: "Future blocks",
      futureHelp: "Production, Retail, Field and Commercial Closing will appear here when those modules are active and built.",

      saved: "Closing saved in PostgreSQL.",
      saveError: "Could not save closing.",
      loadError: "Could not generate closing.",
      inactiveTitle: "Module not active",
      inactiveMsg: "Day closing is not active for this company.",
      activateFromAdmin: "Activate it from Admin V2 > Company > Modules."
    },

    fr: {
      dashboard: "Tableau de bord",
      activeTenant: "Tenant actif",
      eyebrow: "Module de clôture opérationnelle",
      title: "Clôture du jour",
      subtitle: "Générez la clôture opérationnelle par date et journée de travail. CLONEXA résume les événements réels, le personnel, le GPS, les matériaux, l’inventaire, la paie et les résumés de clôture de l’équipe.",
      live: "CLÔTURE DE JOURNÉE",

      back: "Retour",
      generate: "Générer la clôture",
      save: "Enregistrer la clôture",
      pdf: "PDF",
      csv: "CSV",
      refresh: "Actualiser",

      control: "Contrôle de journée",
      date: "Date",
      startTime: "Heure début",
      endTime: "Heure fin",
      responsible: "Responsable",
      status: "Statut",
      generated: "Généré",
      notes: "Notes de clôture",
      notesPlaceholder: "Notes générales, nouveautés, éléments en attente ou décisions de clôture...",
      source: "Source : événements réels filtrés par entreprise, date et plage horaire.",

      summary: "Résumé exécutif",
      workedPeople: "Personnes avec activité",
      shiftStarts: "Services commencés",
      shiftEnds: "Services clôturés",
      breaks: "Pauses",
      gpsEvents: "GPS envoyés",
      materialEvents: "Demandes de matériaux",
      totalEvents: "Événements de la plage",

      chartTitle: "Activité par type",
      peopleTitle: "Résumé par personne",
      closureSummaries: "Résumés de clôture de l’équipe",
      moduleBlocks: "Blocs par module actif",

      employee: "Employé",
      role: "Rôle",
      events: "Événements",
      firstEvent: "Premier événement",
      lastEvent: "Dernier événement",
      summaryText: "Résumé de gestion",
      noSummary: "Aucun résumé écrit dans cette plage.",
      noData: "Aucune donnée pour cette journée.",

      workforce: "Workforce",
      gps: "GPS",
      materials: "Matériaux",
      inventory: "Inventaire",
      payroll: "Paie",
      bots: "Bots",
      future: "Blocs futurs",
      futureHelp: "Production, Retail, Terrain et Clôture commerciale apparaîtront lorsque ces modules seront actifs et construits.",

      saved: "Clôture enregistrée dans PostgreSQL.",
      saveError: "Impossible d’enregistrer la clôture.",
      loadError: "Impossible de générer la clôture.",
      inactiveTitle: "Module non actif",
      inactiveMsg: "La clôture du jour n’est pas active pour cette entreprise.",
      activateFromAdmin: "Activez-le depuis Admin V2 > Entreprise > Modules."
    }
  };

  const MODULE_TITLES = {
    day_closing: ["Cierre de día", "Day closing", "Clôture du jour"],
    commercial_closing: ["Cierre comercial", "Commercial closing", "Clôture commerciale"],
    workforce: ["Personal", "Staff", "Personnel"],
    gps: ["GPS", "GPS", "GPS"],
    payroll: ["Nómina", "Payroll", "Paie"],
    bots: ["Bots", "Bots", "Bots"],
    inventory: ["Inventario", "Inventory", "Inventaire"],
    materials: ["Materiales", "Materials", "Matériaux"],
    crm: ["CRM Campo", "Field CRM", "CRM terrain"],
    kpis: ["KPIs", "KPIs", "KPIs"],
    reports: ["Reportes", "Reports", "Rapports"]
  };

  let lastReport = null;

  function lang() {
    const value = String(localStorage.getItem(LANG_KEY) || "es").toLowerCase();
    return ["es", "en", "fr"].includes(value) ? value : "es";
  }

  function t(key) {
    return TXT[lang()][key] || TXT.es[key] || key;
  }

  function moduleTitle(code, fallback) {
    const index = lang() === "en" ? 1 : lang() === "fr" ? 2 : 0;
    return MODULE_TITLES[code] ? MODULE_TITLES[code][index] : fallback || code;
  }

  function h(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function n(value) {
    const num = Number(value || 0);
    return Number.isFinite(num) ? num.toLocaleString() : "0";
  }

  function today() {
    return new Date().toISOString().slice(0, 10);
  }

  function companyIdFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return params.get("company_id") || params.get("companyId") || "";
  }

  function toRangeIso(date, time) {
    return `${date}T${String(time || "00:00").slice(0, 5)}:00`;
  }

  function eventTime(row) {
    return String(row.occurred_at || row.created_at || row.updated_at || row.date || "");
  }

  function isInRange(row, startIso, endIso) {
    const value = eventTime(row);
    if (!value) return true;
    const ts = new Date(value).getTime();
    const start = new Date(startIso).getTime();
    const end = new Date(endIso).getTime();
    if (!Number.isFinite(ts) || !Number.isFinite(start) || !Number.isFinite(end)) return true;
    return ts >= start && ts <= end;
  }

  async function api(path, options = {}) {
    const response = await fetch(`${API}${path}`, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options
    });
    if (!response.ok) {
      let detail = "";
      try {
        detail = (await response.json()).detail || "";
      } catch (_) {}
      throw new Error(detail || `${response.status} ${response.statusText}`);
    }
    if (response.status === 204) return null;
    return response.json();
  }

  function normalizeModule(row) {
    const source = row.module || row.module_ref || row.global_module || row;
    const code = String(source.code || source.module_code || row.module_code || row.code || "").trim();
    const enabled = row.enabled ?? source.enabled ?? row.is_active ?? source.is_active ?? true;
    return {
      code,
      enabled: !!enabled,
      title: source.name || source.title || code,
      raw: row
    };
  }

  async function loadContext(companyId) {
    const [companiesResult, modulesResult] = await Promise.allSettled([
      api("/companies"),
      api(`/companies/${encodeURIComponent(companyId)}/modules`)
    ]);

    const companies = companiesResult.status === "fulfilled" && Array.isArray(companiesResult.value)
      ? companiesResult.value
      : [];

    const company = companies.find((item) => item.id === companyId || item.company_id === companyId) || {
      id: companyId,
      company_id: companyId,
      name: document.querySelector(".client-company-name")?.textContent || "CLONEXA",
      slug: "tenant"
    };

    const modules = modulesResult.status === "fulfilled" && Array.isArray(modulesResult.value)
      ? modulesResult.value.map(normalizeModule).filter((item) => item.code && item.enabled)
      : [];

    return {
      company,
      modules,
      codes: new Set(modules.map((item) => item.code))
    };
  }

  async function loadAttendanceEvents(companyId, date, startTime, endTime) {
    const startIso = toRangeIso(date, startTime);
    const endIso = toRangeIso(date, endTime);

    const query = new URLSearchParams({
      company_id: companyId,
      date_from: date,
      date_to: date,
      limit: "1000"
    });

    const urls = [
      `/employees/attendance/history?${query.toString()}`,
      `/employees/attendance?${query.toString()}`
    ];

    for (const url of urls) {
      try {
        const payload = await api(url);
        const rows = Array.isArray(payload)
          ? payload
          : Array.isArray(payload?.items)
            ? payload.items
            : Array.isArray(payload?.events)
              ? payload.events
              : Array.isArray(payload?.rows)
                ? payload.rows
                : [];

        return rows.filter((row) => isInRange(row, startIso, endIso));
      } catch (_) {}
    }

    return [];
  }

  async function loadMaterials(companyId, date, startTime, endTime, codes) {
    if (!codes.has("materials")) return [];
    const startIso = toRangeIso(date, startTime);
    const endIso = toRangeIso(date, endTime);

    try {
      const payload = await api(`/materials/companies/${encodeURIComponent(companyId)}/requests?limit=1000`);
      const rows = Array.isArray(payload) ? payload : Array.isArray(payload?.requests) ? payload.requests : [];
      return rows.filter((row) => {
        const raw = row.created_at || row.requested_at || row.updated_at || "";
        if (!raw) return true;
        return String(raw).slice(0, 10) === date && isInRange(row, startIso, endIso);
      });
    } catch (_) {
      return [];
    }
  }

  async function loadInventory(companyId, codes) {
    if (!codes.has("inventory")) return [];
    try {
      const payload = await api(`/inventory/companies/${encodeURIComponent(companyId)}/items?include_inactive=true&limit=1000`);
      return Array.isArray(payload) ? payload : Array.isArray(payload?.items) ? payload.items : [];
    } catch (_) {
      return [];
    }
  }

  function eventLabel(row) {
    return String(row.event_label || row.event_type || row.action || row.status || "").trim();
  }

  function eventEmployee(row) {
    return String(row.employee_name || row.employee || row.name || "Sin nombre").trim();
  }

  function eventRole(row) {
    return String(row.employee_role || row.role || "").trim();
  }

  function eventDetail(row) {
    const payload = row.payload_json || row.payload || {};
    return String(
      payload.summary ||
      payload.end_shift_summary ||
      payload.management_summary ||
      row.notes ||
      row.detail ||
      row.description ||
      ""
    ).trim();
  }

  function isShiftStart(row) {
    const text = `${eventLabel(row)} ${eventDetail(row)}`.toLowerCase();
    return text.includes("inicio") || text.includes("shift_started") || text.includes("start") || text.includes("entrada");
  }

  function isShiftEnd(row) {
    const text = `${eventLabel(row)} ${eventDetail(row)}`.toLowerCase();
    return text.includes("finalizar") || text.includes("turno finalizado") || text.includes("shift_ended") || text.includes("checked_out") || text.includes("end shift");
  }

  function isBreak(row) {
    const text = `${eventLabel(row)} ${eventDetail(row)}`.toLowerCase();
    return text.includes("pausa") || text.includes("break") || text.includes("on_break");
  }

  function isGps(row) {
    const text = `${eventLabel(row)} ${eventDetail(row)} ${row.module_code || ""}`.toLowerCase();
    return text.includes("gps") || text.includes("ubicación") || text.includes("location");
  }

  function isMaterial(row) {
    const text = `${eventLabel(row)} ${eventDetail(row)} ${row.module_code || ""}`.toLowerCase();
    return text.includes("material") || text.includes("materials");
  }

  function buildReport({ company, modules, codes, date, startTime, endTime, events, materials, inventory }) {
    const people = new Map();

    events.forEach((row) => {
      const name = eventEmployee(row);
      if (!people.has(name)) {
        people.set(name, {
          name,
          role: eventRole(row),
          events: [],
          summaries: []
        });
      }

      const person = people.get(name);
      person.events.push(row);

      const detail = eventDetail(row);
      if (isShiftEnd(row) && detail && !/^(shift ended|turno finalizado|finalizar turno)$/i.test(detail)) {
        person.summaries.push({
          time: eventTime(row),
          text: detail
        });
      }
    });

    const personRows = Array.from(people.values()).map((person) => {
      const sorted = [...person.events].sort((a, b) => new Date(eventTime(a)) - new Date(eventTime(b)));
      return {
        ...person,
        first: eventTime(sorted[0]),
        last: eventTime(sorted[sorted.length - 1])
      };
    });

    const gpsCount = events.filter(isGps).length;
    const materialEventCount = events.filter(isMaterial).length + materials.length;

    const inventoryLow = inventory.filter((item) => Number(item.current_stock || 0) <= Number(item.min_stock || 0) && Number(item.min_stock || 0) > 0).length;
    const inventoryZero = inventory.filter((item) => Number(item.current_stock || 0) <= 0).length;

    const metrics = {
      people: personRows.length,
      totalEvents: events.length,
      shiftStarts: events.filter(isShiftStart).length,
      shiftEnds: events.filter(isShiftEnd).length,
      breaks: events.filter(isBreak).length,
      gps: gpsCount,
      materials: materialEventCount,
      inventoryItems: inventory.length,
      inventoryLow,
      inventoryZero
    };

    return {
      company,
      modules,
      source_modules: modules.map((m) => m.code),
      codes: Array.from(codes),
      date,
      start_time: startTime,
      end_time: endTime,
      events,
      materials,
      inventory,
      people: personRows,
      metrics
    };
  }

  function card(label, value) {
    return `
      <div class="client-kpi">
        <span>${h(label)}</span>
        <strong>${h(value)}</strong>
      </div>
    `;
  }

  function bar(label, value, max) {
    const pct = max > 0 ? Math.max(2, Math.round((Number(value || 0) / max) * 100)) : 2;
    return `
      <div class="cx-day-bar-row">
        <span>${h(label)}</span>
        <div class="cx-day-bar"><i style="width:${pct}%"></i></div>
        <strong>${h(n(value))}</strong>
      </div>
    `;
  }

  function fmtTime(value) {
    if (!value) return "—";
    try {
      return new Date(value).toLocaleString();
    } catch (_) {
      return String(value);
    }
  }

  function peopleTable(report) {
    if (!report.people.length) {
      return `<p class="client-muted">${h(t("noData"))}</p>`;
    }

    return `
      <div class="client-table-wrap">
        <table class="client-table">
          <thead>
            <tr>
              <th>${h(t("employee"))}</th>
              <th>${h(t("role"))}</th>
              <th>${h(t("events"))}</th>
              <th>${h(t("firstEvent"))}</th>
              <th>${h(t("lastEvent"))}</th>
            </tr>
          </thead>
          <tbody>
            ${report.people.map((person) => `
              <tr>
                <td>${h(person.name)}</td>
                <td>${h(person.role || "—")}</td>
                <td>${h(n(person.events.length))}</td>
                <td>${h(fmtTime(person.first))}</td>
                <td>${h(fmtTime(person.last))}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function summariesBlock(report) {
    const summaries = report.people.flatMap((person) =>
      person.summaries.map((item) => ({ ...item, name: person.name, role: person.role }))
    );

    if (!summaries.length) {
      return `<p class="client-muted">${h(t("noSummary"))}</p>`;
    }

    return summaries.map((item) => `
      <article class="cx-day-summary-note">
        <strong>${h(item.name)}</strong>
        <span>${h(item.role || "")} · ${h(fmtTime(item.time))}</span>
        <p>${h(item.text)}</p>
      </article>
    `).join("");
  }

  function moduleBlocks(report) {
    const codes = new Set(report.codes);
    const blocks = [];

    if (codes.has("workforce")) {
      blocks.push(["workforce", t("workforce"), [
        [t("workedPeople"), report.metrics.people],
        [t("shiftStarts"), report.metrics.shiftStarts],
        [t("shiftEnds"), report.metrics.shiftEnds],
        [t("breaks"), report.metrics.breaks]
      ]]);
    }

    if (codes.has("gps")) {
      blocks.push(["gps", t("gps"), [[t("gpsEvents"), report.metrics.gps]]]);
    }

    if (codes.has("materials")) {
      blocks.push(["materials", t("materials"), [[t("materialEvents"), report.metrics.materials]]]);
    }

    if (codes.has("inventory")) {
      blocks.push(["inventory", t("inventory"), [
        ["Items", report.metrics.inventoryItems],
        ["Low stock", report.metrics.inventoryLow],
        ["Zero stock", report.metrics.inventoryZero]
      ]]);
    }

    blocks.push(["future", t("future"), [[t("futureHelp"), ""]]]);

    return blocks.map(([code, title, rows]) => `
      <section class="cx-day-block">
        <div class="client-eyebrow">${h(title)}</div>
        <h2>${h(title)}</h2>
        <div class="cx-day-list">
          ${rows.map(([label, value]) => `
            <div class="cx-day-row">
              <span>${h(label)}</span>
              <strong>${h(value)}</strong>
            </div>
          `).join("")}
        </div>
      </section>
    `).join("");
  }

  function sidebar(company, modules, activeCode = "day_closing") {
    const visible = modules.filter((m) => !["core", "core_settings", "settings"].includes(m.code));

    return `
      <aside class="client-sidebar">
        <div class="client-logo">${h((company.name || "CLONEXA").slice(0, 2).toUpperCase())}</div>
        <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
        <div class="client-muted">${h(company.slug || "tenant")}</div>

        <nav class="client-nav">
          <button type="button" data-clx-day-dashboard>${h(t("dashboard"))}</button>
          ${visible.map((module) => `
            <button class="${module.code === activeCode ? "active" : ""}" type="button" data-client-module="${h(module.code)}">
              ${h(moduleTitle(module.code, module.title))}
            </button>
          `).join("")}
        </nav>

        <div class="client-footer-id">
          <strong>${h(t("activeTenant"))}</strong><br>${h(company.id || company.company_id || companyIdFromUrl())}
        </div>
      </aside>
    `;
  }

  function ensureStyles() {
    if (document.getElementById("clx-day-closing-r2-styles")) return;

    const style = document.createElement("style");
    style.id = "clx-day-closing-r2-styles";
    style.textContent = `
      .cx-day-toolbar {
        display:grid;
        grid-template-columns: repeat(4, minmax(140px, 1fr));
        gap:14px;
        align-items:end;
        margin-top:18px;
      }
      .cx-day-toolbar label,
      .cx-day-notes-label {
        display:grid;
        gap:8px;
        color:rgba(255,255,255,.72);
        font-weight:900;
        letter-spacing:.08em;
        text-transform:uppercase;
        font-size:12px;
      }
      .cx-day-toolbar input,
      .cx-day-notes-label textarea {
        width:100%;
        border:1px solid rgba(255,255,255,.14);
        background:rgba(0,0,0,.28);
        color:white;
        border-radius:16px;
        padding:13px 14px;
        font-weight:800;
        outline:none;
      }
      .cx-day-notes-label textarea {
        min-height:88px;
        resize:vertical;
      }
      .cx-day-grid {
        display:grid;
        grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
        gap:16px;
        margin-top:18px;
      }
      .cx-day-block {
        border:1px solid rgba(255,255,255,.11);
        background:linear-gradient(135deg,rgba(255,255,255,.07),rgba(255,0,180,.08));
        border-radius:24px;
        padding:22px;
        box-shadow:0 18px 48px rgba(0,0,0,.18);
      }
      .cx-day-list {
        display:grid;
        gap:10px;
      }
      .cx-day-row {
        display:flex;
        justify-content:space-between;
        gap:12px;
        align-items:center;
        border:1px solid rgba(255,255,255,.08);
        background:rgba(255,255,255,.06);
        padding:12px 14px;
        border-radius:14px;
      }
      .cx-day-row span {
        color:rgba(255,255,255,.76);
        font-weight:800;
      }
      .cx-day-row strong {
        color:white;
        font-weight:1000;
      }
      .cx-day-chart {
        display:grid;
        gap:12px;
      }
      .cx-day-bar-row {
        display:grid;
        grid-template-columns: 160px 1fr 55px;
        gap:12px;
        align-items:center;
      }
      .cx-day-bar-row span {
        font-weight:900;
        color:rgba(255,255,255,.82);
      }
      .cx-day-bar {
        height:13px;
        border-radius:999px;
        background:rgba(255,255,255,.12);
        overflow:hidden;
      }
      .cx-day-bar i {
        display:block;
        height:100%;
        border-radius:999px;
        background:linear-gradient(90deg,#22e39f,#ff21bd);
      }
      .cx-day-summary-note {
        border:1px solid rgba(255,255,255,.10);
        background:rgba(255,255,255,.06);
        border-radius:18px;
        padding:16px;
        margin-bottom:10px;
      }
      .cx-day-summary-note strong {
        display:block;
        color:white;
        font-size:16px;
      }
      .cx-day-summary-note span {
        display:block;
        color:rgba(255,255,255,.62);
        margin-top:4px;
        font-size:12px;
        font-weight:800;
      }
      .cx-day-summary-note p {
        margin:10px 0 0;
        color:rgba(255,255,255,.86);
        line-height:1.45;
      }
      @media (max-width: 980px) {
        .cx-day-toolbar {
          grid-template-columns:1fr;
        }
      }
      @media print {
        body * { visibility:hidden !important; }
        [data-day-closing-root], [data-day-closing-root] * { visibility:visible !important; }
        [data-day-closing-root] { position:absolute; inset:0; background:white !important; color:black !important; }
        .client-sidebar, .client-actions { display:none !important; }
        .client-main { width:100% !important; }
      }
    `;
    document.head.appendChild(style);
  }

  async function generateReportFromForm(context) {
    const companyId = companyIdFromUrl();
    const date = document.querySelector("[data-day-date]")?.value || today();
    const startTime = document.querySelector("[data-day-start]")?.value || "07:00";
    const endTime = document.querySelector("[data-day-end]")?.value || "18:00";

    const [events, materials, inventory] = await Promise.all([
      loadAttendanceEvents(companyId, date, startTime, endTime),
      loadMaterials(companyId, date, startTime, endTime, context.codes),
      loadInventory(companyId, context.codes)
    ]);

    lastReport = buildReport({
      company: context.company,
      modules: context.modules,
      codes: context.codes,
      date,
      startTime,
      endTime,
      events,
      materials,
      inventory
    });

    renderReport(context, lastReport);
  }

  function renderReport(context, report) {
    const max = Math.max(
      report.metrics.shiftStarts,
      report.metrics.shiftEnds,
      report.metrics.breaks,
      report.metrics.gps,
      report.metrics.materials,
      1
    );

    const chart = [
      bar(t("shiftStarts"), report.metrics.shiftStarts, max),
      bar(t("shiftEnds"), report.metrics.shiftEnds, max),
      bar(t("breaks"), report.metrics.breaks, max),
      bar(t("gpsEvents"), report.metrics.gps, max),
      bar(t("materialEvents"), report.metrics.materials, max)
    ].join("");

    const target = document.querySelector("[data-day-report]");
    if (!target) return;

    target.innerHTML = `
      <section class="client-panel">
        <div style="display:flex;justify-content:space-between;gap:16px;align-items:flex-start">
          <div>
            <div class="client-eyebrow">${h(t("summary"))}</div>
            <h2>${h(t("summary"))}</h2>
            <p class="client-muted">${h(report.date)} · ${h(report.start_time)} - ${h(report.end_time)}</p>
          </div>
          <span class="client-badge">${h(n(report.metrics.totalEvents))} ${h(t("events"))}</span>
        </div>

        <div class="client-kpis">
          ${card(t("workedPeople"), n(report.metrics.people))}
          ${card(t("shiftStarts"), n(report.metrics.shiftStarts))}
          ${card(t("shiftEnds"), n(report.metrics.shiftEnds))}
          ${card(t("breaks"), n(report.metrics.breaks))}
          ${card(t("gpsEvents"), n(report.metrics.gps))}
          ${card(t("materialEvents"), n(report.metrics.materials))}
        </div>
      </section>

      <section class="client-panel">
        <div class="client-eyebrow">${h(t("chartTitle"))}</div>
        <h2>${h(t("chartTitle"))}</h2>
        <div class="cx-day-chart">${chart}</div>
      </section>

      <section class="client-panel">
        <div class="client-eyebrow">${h(t("peopleTitle"))}</div>
        <h2>${h(t("peopleTitle"))}</h2>
        ${peopleTable(report)}
      </section>

      <section class="client-panel">
        <div class="client-eyebrow">${h(t("closureSummaries"))}</div>
        <h2>${h(t("closureSummaries"))}</h2>
        ${summariesBlock(report)}
      </section>

      <section class="client-panel">
        <div class="client-eyebrow">${h(t("moduleBlocks"))}</div>
        <h2>${h(t("moduleBlocks"))}</h2>
        <div class="cx-day-grid">${moduleBlocks(report)}</div>
      </section>
    `;
  }

  function renderInactive(company, modules) {
    const app = document.getElementById("app");
    if (!app) return;

    app.innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          ${sidebar(company, modules, "dashboard")}
          <section class="client-main">
            <section class="client-panel" style="max-width:900px;margin:12vh auto">
              <div class="client-eyebrow">${h(t("eyebrow"))}</div>
              <h1>${h(t("inactiveTitle"))}</h1>
              <p>${h(t("inactiveMsg"))}</p>
              <p class="client-muted">${h(t("activateFromAdmin"))}</p>
              <div class="client-actions">
                <button class="client-btn" type="button" data-clx-day-dashboard>${h(t("back"))}</button>
              </div>
            </section>
          </section>
        </div>
      </main>
    `;
  }

  async function renderDayClosing() {
    ensureStyles();

    const companyId = companyIdFromUrl();
    const context = await loadContext(companyId);

    if (!context.codes.has("day_closing")) {
      renderInactive(context.company, context.modules);
      return;
    }

    const app = document.getElementById("app");
    if (!app) return;

    app.innerHTML = `
      <main class="client-shell" data-day-closing-root>
        <div class="client-layout">
          ${sidebar(context.company, context.modules, "day_closing")}

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">${h(t("eyebrow"))}</div>
              <h1 class="client-title">${h(t("title"))}</h1>
              <p class="client-muted">${h(t("subtitle"))}</p>
              <span class="client-badge" style="position:absolute;right:28px;top:28px">${h(t("live"))}</span>

              <div class="client-actions">
                <button class="client-btn" type="button" data-day-generate>${h(t("generate"))}</button>
                <button class="client-btn" type="button" data-day-save>${h(t("save"))}</button>
                <button class="client-btn" type="button" data-day-pdf>${h(t("pdf"))}</button>
                <button class="client-btn" type="button" data-day-csv>${h(t("csv"))}</button>
                <button class="client-btn" type="button" data-clx-day-dashboard>${h(t("back"))}</button>
              </div>
            </header>

            <section class="client-panel">
              <div class="client-eyebrow">${h(t("control"))}</div>
              <h2>${h(t("control"))}</h2>

              <div class="cx-day-toolbar">
                <label>${h(t("date"))}<input type="date" data-day-date value="${h(today())}"></label>
                <label>${h(t("startTime"))}<input type="time" data-day-start value="07:00"></label>
                <label>${h(t("endTime"))}<input type="time" data-day-end value="18:00"></label>
                <label>${h(t("responsible"))}<input type="text" data-day-responsible value="${h(context.company.name || "")}"></label>
              </div>

              <div style="margin-top:18px">
                <label class="cx-day-notes-label">
                  ${h(t("notes"))}
                  <textarea data-day-notes placeholder="${h(t("notesPlaceholder"))}"></textarea>
                </label>
              </div>

              <p class="client-muted" style="margin-top:14px">${h(t("source"))}</p>
            </section>

            <div data-day-report></div>
          </section>
        </div>
      </main>
    `;

    window.__clxDayClosingContext = context;
    await generateReportFromForm(context);
  }

  function showNotice(message, error = false) {
    const panel = document.querySelector("[data-day-closing-root] .client-panel");
    if (!panel) return;
    const box = document.createElement("div");
    box.className = `personal-toast ${error ? "error" : ""}`;
    box.textContent = message;
    panel.prepend(box);
    setTimeout(() => box.remove(), 3200);
  }

  function reportPayload() {
    const context = window.__clxDayClosingContext;
    const report = lastReport;
    if (!context || !report) return null;

    return {
      date: report.date,
      start_time: report.start_time,
      end_time: report.end_time,
      responsible: document.querySelector("[data-day-responsible]")?.value || "",
      notes: document.querySelector("[data-day-notes]")?.value || "",
      status: "generated",
      source_modules: report.source_modules,
      summary: {
        metrics: report.metrics,
        people: report.people.map((person) => ({
          name: person.name,
          role: person.role,
          events: person.events.length,
          first: person.first,
          last: person.last,
          summaries: person.summaries
        })),
        materials: report.materials.length,
        inventory: {
          items: report.metrics.inventoryItems,
          low_stock: report.metrics.inventoryLow,
          zero_stock: report.metrics.inventoryZero
        }
      }
    };
  }

  async function saveReport() {
    const payload = reportPayload();
    if (!payload) return;

    try {
      const companyId = companyIdFromUrl();
      const response = await api(`/day-closing/companies/${encodeURIComponent(companyId)}/closures`, {
        method: "POST",
        body: JSON.stringify(payload)
      });
      showNotice(`${t("saved")} ID: ${response.id}`);
    } catch (error) {
      showNotice(`${t("saveError")} ${error.message || ""}`, true);
    }
  }

  function downloadCsv() {
    const payload = reportPayload();
    if (!payload) return;

    const rows = [
      ["company_id", companyIdFromUrl()],
      ["date", payload.date],
      ["start_time", payload.start_time],
      ["end_time", payload.end_time],
      ["responsible", payload.responsible],
      ["notes", payload.notes],
      [],
      ["metric", "value"],
      ...Object.entries(payload.summary.metrics),
      [],
      ["employee", "role", "events", "first", "last", "summaries"],
      ...payload.summary.people.map((person) => [
        person.name,
        person.role,
        person.events,
        person.first,
        person.last,
        (person.summaries || []).map((item) => item.text).join(" | ")
      ])
    ];

    const csv = rows.map((row) => row.map((cell) => `"${String(cell ?? "").replaceAll('"', '""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `clonexa_day_closing_${payload.date}_${payload.start_time.replace(":", "")}_${payload.end_time.replace(":", "")}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function printPdf() {
    if (!lastReport) return;
    window.print();
  }

  document.addEventListener("click", async (event) => {
    const moduleButton = event.target.closest && event.target.closest('[data-client-module="day_closing"]');
    if (moduleButton) {
      event.preventDefault();
      event.stopPropagation();
      if (event.stopImmediatePropagation) event.stopImmediatePropagation();
      await renderDayClosing();
      return;
    }

    if (event.target.closest && event.target.closest("[data-clx-day-dashboard]")) {
      event.preventDefault();
      window.location.href = `/client?company_id=${encodeURIComponent(companyIdFromUrl())}`;
      return;
    }

    if (event.target.closest && event.target.closest("[data-day-generate]")) {
      event.preventDefault();
      await generateReportFromForm(window.__clxDayClosingContext || await loadContext(companyIdFromUrl()));
      return;
    }

    if (event.target.closest && event.target.closest("[data-day-save]")) {
      event.preventDefault();
      await saveReport();
      return;
    }

    if (event.target.closest && event.target.closest("[data-day-csv]")) {
      event.preventDefault();
      downloadCsv();
      return;
    }

    if (event.target.closest && event.target.closest("[data-day-pdf]")) {
      event.preventDefault();
      printPdf();
      return;
    }
  }, true);

  window.CLONEXA_RENDER_DAY_CLOSING = renderDayClosing;
})();
'''

web_js.write_text(js_code, encoding="utf-8")

print("PATCH_OK: 022B-R2 Day Closing Journey Engine installed")
