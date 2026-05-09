from pathlib import Path

path = Path("app/api/v1/endpoints/adaptive_kpis_v1.py")
src = path.read_text(encoding="utf-8-sig")

start = src.find("async def production_kpis(")
end = src.find("\n\nasync def payroll_kpis(", start)

if start == -1 or end == -1:
    raise SystemExit("No encontré production_kpis para reemplazar.")

replacement = r'''async def production_kpis(db: AsyncSession, company_id: str, start: date, end: date) -> list[dict[str, Any]]:
    params = {"company_id": company_id, "date_from": start.isoformat(), "date_to": end.isoformat()}

    refs = 0
    bot_active = 0
    initial_qty = 0
    finished_qty = 0
    closures_total = 0
    closures_period = 0
    active_sessions = 0

    if await table_exists(db, "product_references"):
        refs = intval(await safe_scalar(
            db,
            "SELECT count(*) FROM product_references WHERE company_id::text = :company_id",
            params,
        ))
        bot_active = intval(await safe_scalar(
            db,
            "SELECT count(*) FROM product_references WHERE company_id::text = :company_id AND bot_active IS TRUE",
            params,
        ))
        initial_qty = intval(await safe_scalar(
            db,
            "SELECT COALESCE(sum(initial_quantity), 0) FROM product_references WHERE company_id::text = :company_id",
            params,
        ))

    if await table_exists(db, "reference_production_closures"):
        # Producción del módulo = acumulado productivo real.
        # El periodo queda como KPI separado para no ocultar cierres por diferencias de fecha/zona.
        finished_qty = intval(await safe_scalar(
            db,
            """
            SELECT COALESCE(sum(quantity_finished), 0)
            FROM reference_production_closures
            WHERE company_id::text = :company_id
            """,
            params,
        ))

        closures_total = intval(await safe_scalar(
            db,
            """
            SELECT count(*)
            FROM reference_production_closures
            WHERE company_id::text = :company_id
            """,
            params,
        ))

        closures_period = intval(await safe_scalar(
            db,
            """
            SELECT count(*)
            FROM reference_production_closures
            WHERE company_id::text = :company_id
              AND closed_at::date BETWEEN CAST(:date_from AS date) AND CAST(:date_to AS date)
            """,
            params,
        ))

    if await table_exists(db, "reference_work_sessions"):
        active_sessions = intval(await safe_scalar(
            db,
            """
            SELECT count(*)
            FROM reference_work_sessions
            WHERE company_id::text = :company_id
              AND status = 'active'
            """,
            params,
        ))

    pending = max(initial_qty - finished_qty, 0)
    over_finished = max(finished_qty - initial_qty, 0)
    progress = round((finished_qty / initial_qty) * 100, 2) if initial_qty > 0 else 0

    return [
        {"key": "references_total", "label": "Referencias", "value": refs, "module": "Producción"},
        {"key": "references_bot", "label": "Visibles en bot", "value": bot_active, "module": "Producción"},
        {"key": "initial_qty", "label": "Cantidad inicial", "value": initial_qty, "module": "Producción"},
        {"key": "finished_qty", "label": "Terminadas", "value": finished_qty, "module": "Producción"},
        {"key": "pending_qty", "label": "Pendientes", "value": pending, "module": "Producción"},
        {"key": "over_finished_qty", "label": "Sobreproducidas", "value": over_finished, "module": "Producción"},
        {"key": "progress", "label": "Avance", "value": f"{progress}%", "module": "Producción"},
        {"key": "closures", "label": "Cierres producción", "value": closures_total, "module": "Producción"},
        {"key": "closures_period", "label": "Cierres del periodo", "value": closures_period, "module": "Producción"},
        {"key": "active_sessions", "label": "Sesiones activas", "value": active_sessions, "module": "Producción"},
    ]'''

src = src[:start] + replacement + src[end:]
path.write_text(src, encoding="utf-8")
print("PRODUCTION_01_KPIS_OK")
