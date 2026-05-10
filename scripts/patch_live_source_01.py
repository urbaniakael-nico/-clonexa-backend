from pathlib import Path
import re

crm_path = Path("app/api/v1/endpoints/crm_live_v1.py")
prod_path = Path("app/api/v1/endpoints/production_v1.py")
client_path = Path("app/web/client.js")

# =========================
# CRM LIVE BACKEND FIX
# =========================
crm_src = crm_path.read_text(encoding="utf-8-sig")

crm_src = re.sub(
r'''async def reference_timeline\(
    db: AsyncSession,
    company_id: str,
    employee_id: str,
    shift_started_at: str \| None,
\) -> list\[dict\[str, Any\]\]:
.*?
    return \[
        \{
            "session_id": row.get\("id"\),
            "reference_id": row.get\("reference_id"\),
            "reference_name": clean\(row.get\("reference_name"\)\),
            "started_at": row.get\("started_at"\),
            "ended_at": row.get\("ended_at"\),
            "status": clean\(row.get\("status"\)\),
            "is_active": clean\(row.get\("status"\)\).lower\(\) == "active",
            "duration_seconds": intval\(row.get\("duration_seconds"\)\),
        \}
        for row in rows
    \]
''',
r'''async def reference_timeline(
    db: AsyncSession,
    company_id: str,
    employee_id: str,
    shift_started_at: str | None,
    telegram_user_id: str | None = None,
    employee_name: str | None = None,
) -> list[dict[str, Any]]:
    """
    Fuente de verdad productiva:
    - Primero intenta por employee_id.
    - Si el bot guardó telegram_user_id, también empata por telegram.
    - Si quedaron sesiones antiguas por nombre, empata por employee_name.
    - La sesión activa es status='active' o ended_at IS NULL.
    """
    if not await table_exists(db, "reference_work_sessions"):
        return []

    rows = await safe_rows(
        db,
        """
        SELECT
            id,
            employee_id,
            COALESCE(employee_name, '') AS employee_name,
            COALESCE(telegram_user_id, '') AS telegram_user_id,
            COALESCE(reference_id, '') AS reference_id,
            COALESCE(reference_name, '') AS reference_name,
            started_at::text AS started_at,
            ended_at::text AS ended_at,
            COALESCE(status, '') AS status,
            CASE
                WHEN lower(COALESCE(status, '')) = 'active' OR ended_at IS NULL
                    THEN EXTRACT(EPOCH FROM (now() - started_at))::int
                ELSE GREATEST(COALESCE(duration_minutes, 0) * 60, 0)::int
            END AS duration_seconds
        FROM reference_work_sessions
        WHERE company_id::text = :company_id
          AND (
                employee_id::text = :employee_id
                OR (:telegram_user_id IS NOT NULL AND telegram_user_id::text = :telegram_user_id)
                OR (:employee_name IS NOT NULL AND lower(COALESCE(employee_name, '')) = lower(:employee_name))
          )
          AND (:shift_started_at IS NULL OR started_at >= CAST(:shift_started_at AS timestamptz))
        ORDER BY started_at ASC
        LIMIT 50
        """,
        {
            "company_id": company_id,
            "employee_id": employee_id,
            "telegram_user_id": telegram_user_id or None,
            "employee_name": employee_name or None,
            "shift_started_at": shift_started_at or None,
        },
    )

    output = []

    for row in rows:
        status = clean(row.get("status")).lower()
        ended_at = row.get("ended_at")
        is_active = status == "active" or not ended_at

        output.append({
            "session_id": row.get("id"),
            "reference_id": row.get("reference_id"),
            "reference_name": clean(row.get("reference_name")),
            "started_at": row.get("started_at"),
            "ended_at": ended_at,
            "status": status,
            "is_active": is_active,
            "duration_seconds": intval(row.get("duration_seconds")),
        })

    return output
''',
crm_src,
flags=re.S
)

# Agrega telegram_user_id al snapshot de empleados si la tabla employees lo tiene.
crm_src = crm_src.replace(
'''    role_expr = "COALESCE(e.role, '')" if "role" in employee_cols else "''"''',
'''    role_expr = "COALESCE(e.role, '')" if "role" in employee_cols else "''"
    telegram_expr = "COALESCE(e.telegram_user_id::text, '')" if "telegram_user_id" in employee_cols else "''"'''
)

crm_src = crm_src.replace(
'''            e.id::text AS employee_id,
            {name_expr} AS employee_name,
            {role_expr} AS employee_role,
            {status_fields}''',
'''            e.id::text AS employee_id,
            {name_expr} AS employee_name,
            {role_expr} AS employee_role,
            {telegram_expr} AS telegram_user_id,
            {status_fields}'''
)

# Reemplaza la llamada a reference_timeline.
crm_src = crm_src.replace(
'''        timeline = await reference_timeline(db, company_id, employee_id, shift_started_at)''',
'''        timeline = await reference_timeline(
            db,
            company_id,
            employee_id,
            shift_started_at,
            telegram_user_id=clean(employee.get("telegram_user_id")),
            employee_name=clean(employee.get("employee_name")),
        )'''
)

# Si status_started_at viene vacío pero el empleado está activo, usa shift_started_at.
crm_src = crm_src.replace(
'''        if work_status in {"working", "on_break"}:
            shift_started_at = await latest_shift_start(db, company_id, employee_id) or status_started_at''',
'''        if work_status in {"working", "on_break"}:
            shift_started_at = await latest_shift_start(db, company_id, employee_id) or status_started_at
            if not status_started_at:
                status_started_at = shift_started_at'''
)

crm_path.write_text(crm_src, encoding="utf-8")


# =========================
# PRODUCTION PERIOD FALLBACK FIX
# =========================
prod_src = prod_path.read_text(encoding="utf-8-sig")

prod_src = prod_src.replace(
'''    by_employee_map: dict[str, dict[str, Any]] = {}
    by_reference_period: dict[str, dict[str, Any]] = {}

    for row in closures_period:''',
'''    by_employee_map: dict[str, dict[str, Any]] = {}
    by_reference_period: dict[str, dict[str, Any]] = {}

    graph_rows = closures_period if closures_period else closures_all

    for row in graph_rows:'''
)

prod_src = prod_src.replace(
'''        "by_employee_period": sorted(by_employee_map.values(), key=lambda x: x["finished_quantity"], reverse=True),
        "by_reference_period": sorted(by_reference_period.values(), key=lambda x: x["finished_quantity"], reverse=True),''',
'''        "by_employee_period": sorted(by_employee_map.values(), key=lambda x: x["finished_quantity"], reverse=True),
        "by_reference_period": sorted(by_reference_period.values(), key=lambda x: x["finished_quantity"], reverse=True),
        "graph_source": "period" if closures_period else "all_time_fallback",'''
)

prod_path.write_text(prod_src, encoding="utf-8")


# =========================
# CLIENT CRM VISUAL + TIMERS FIX
# =========================
client_src = client_path.read_text(encoding="utf-8-sig")

# Fuerza textos CRM en español. El idioma global se blinda en I18N-01.
replacements = {
    "FIELD CRM": "CRM CAMPO",
    "Back": "Volver",
    "Refresh": "Actualizar",
    "Current operating status": "Estado operativo actual",
    "LIVE OPERATION": "Operación en vivo",
    "ACTIVE": "ACTIVOS",
    "ON BREAK": "EN PAUSA",
    "CON REFERENCIA": "CON REFERENCIA",
    "PRODUCTION": "PRODUCCIÓN",
    "Collaborators": "Colaboradores",
    "STATUS BY COLLABORATOR": "Estado por colaborador",
    "Collaborator": "Colaborador",
    "Off shift": "Fuera de turno",
    "Active": "Activo",
    "Turno iniciado": "Turno iniciado",
    "Cronómetro de jornada": "Cronómetro de jornada",
    "Producción actual": "Producción actual",
    "Sin referencia activa": "Sin referencia activa",
    "Referencia activa": "Referencia activa",
}

for old, new in replacements.items():
    client_src = client_src.replace(old, new)

# Mejora parser de fechas para Postgres timestamptz.
client_src = client_src.replace(
'''  function crmLiveParseDate(value) {
    if (!value) return null;

    const raw = String(value).trim();
    const normalized = raw.includes("T") ? raw : raw.replace(" ", "T");
    const date = new Date(normalized);

    if (Number.isNaN(date.getTime())) return null;

    return date;
  }''',
'''  function crmLiveParseDate(value) {
    if (!value) return null;

    let raw = String(value).trim();

    if (!raw) return null;

    // PostgreSQL: "2026-05-09 19:12:33.123456+00:00"
    // JS Date:   "2026-05-09T19:12:33.123+00:00"
    raw = raw.replace(" ", "T");

    const match = raw.match(/^(.*\\.\\d{3})\\d+(.*)$/);
    if (match) raw = `${match[1]}${match[2]}`;

    if (!/[zZ]|[+-]\\d\\d:?\\d\\d$/.test(raw)) {
      raw = `${raw}Z`;
    }

    const date = new Date(raw);

    if (Number.isNaN(date.getTime())) return null;

    return date;
  }'''
)

# Cambia el texto del resumen y evita secciones vacías visualmente.
client_src = client_src.replace(
'''                <strong>${h(item.reference_name || "Referencia")}</strong>
                <div class="client-muted">${item.is_active ? "Referencia activa" : "Referencia cerrada"}</div>''',
'''                <strong>${h(item.reference_name || "Referencia")}</strong>
                <div class="client-muted">${item.is_active ? "Referencia activa · corriendo" : "Referencia cerrada"}</div>'''
)

# Garantiza cronómetro de turno usando shift_started_at.
client_src = client_src.replace(
'''data-live-since="${h(row.shift_started_at || row.status_started_at || "")}"''',
'''data-live-since="${h(row.shift_started_at || row.status_started_at || row.reference_timeline?.[0]?.started_at || "")}"'''
)

client_path.write_text(client_src, encoding="utf-8")

print("LIVE_SOURCE_01_OK")
