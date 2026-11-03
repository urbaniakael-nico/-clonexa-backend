"""Nomina con reglas de EE. UU. - PDF y CSV (interruptor us_payroll del modulo payroll).

Rutas en /us-payroll/companies/{company_id}/...; todas exigen sesion valida desde el
primer dia: Admin V2 o un usuario de ESA empresa con rol de dueno o direccion (validado
aqui, no en la pantalla). Sin el interruptor: 404.
- GET "/export.pdf?period_start=&period_end=[&employee_id=]"
- GET "/export.csv?period_start=&period_end=[&employee_id=]"
Mismas cifras que Nomina, Reportes y el bot: salen de calculate_period_snapshot.
"""
from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import reports_v2, us_payroll, us_payroll_export

router = APIRouter()
OFF = "Nómina con reglas de EE. UU. no está activa para esta empresa."
MAX_DAYS = 62


async def reader(company_id: UUID, request: Request, authorization: Optional[str] = Header(default=None),
                 db: AsyncSession = Depends(get_db)) -> str:
    """Sin sesion: 401. Otra empresa: 403. Rol sin acceso: 403. Interruptor apagado: 404."""
    from app.web.admin_v2_routes import _active_session

    if await _active_session(request, db):
        who = "Admin V2"
    else:
        from app.api.deps import require_company_user_for_tenant

        user = await require_company_user_for_tenant(db, authorization, company_id)
        if not reports_v2.role_allowed(getattr(user, "role", "")):
            raise HTTPException(status_code=403, detail="La nómina es solo del dueño y del director.")
        who = str(getattr(user, "full_name", "") or "usuario")
    if not await us_payroll.is_on(db, company_id):
        raise HTTPException(status_code=404, detail=OFF)
    return who


def _period(period_start: str, period_end: str) -> tuple[date, date]:
    try:
        start, end = date.fromisoformat(period_start[:10]), date.fromisoformat(period_end[:10])
    except ValueError:
        raise HTTPException(status_code=422, detail="Fechas no válidas (AAAA-MM-DD).") from None
    if end < start:
        raise HTTPException(status_code=422, detail="La fecha final es antes de la inicial.")
    if (end - start).days > MAX_DAYS:
        raise HTTPException(status_code=422, detail=f"Máximo {MAX_DAYS} días por archivo.")
    return start, end


async def _snapshot(db: AsyncSession, company_id: UUID, start: date, end: date, employee_id: Optional[UUID]) -> dict:
    from app.api.v1.endpoints.payroll import calculate_period_snapshot

    snap = await calculate_period_snapshot(db, company_id, start, end)
    if employee_id:
        snap = {**snap, "rows": [r for r in snap.get("rows") or [] if str(r.get("employee_id")) == str(employee_id)]}
    return snap


async def _documents(db: AsyncSession, company_id: UUID) -> dict:
    """063A: documento de cada persona para el CSV (solo de ESTA empresa)."""
    try:
        rows = (await db.execute(text("SELECT id::text AS id, COALESCE(document_id, '') AS doc FROM employees WHERE company_id = CAST(:c AS uuid)"),
                                 {"c": str(company_id)})).mappings().all()
    except Exception:
        await db.rollback()
        return {}
    return {r["id"]: r["doc"] for r in rows if r["doc"]}


async def _company_name(db: AsyncSession, company_id: UUID) -> str:
    return str((await db.execute(text("SELECT name FROM companies WHERE id = CAST(:c AS uuid)"), {"c": str(company_id)})).scalar() or "")


@router.get("/companies/{company_id}/export.pdf")
async def export_pdf(company_id: UUID, period_start: str = Query(...), period_end: str = Query(...), employee_id: Optional[UUID] = Query(default=None),
                     disposition: str = Query(default="attachment"), who: str = Depends(reader), db: AsyncSession = Depends(get_db)) -> Response:
    start, end = _period(period_start, period_end)
    snap = await _snapshot(db, company_id, start, end, employee_id)
    pdf = us_payroll_export.build_pdf(snap, await _company_name(db, company_id))
    mode = "inline" if disposition == "inline" else "attachment"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'{mode}; filename="nomina_{start}_{end}.pdf"', "Cache-Control": "no-store"})


@router.get("/companies/{company_id}/export.csv")
async def export_csv(company_id: UUID, period_start: str = Query(...), period_end: str = Query(...), employee_id: Optional[UUID] = Query(default=None),
                     who: str = Depends(reader), db: AsyncSession = Depends(get_db)) -> Response:
    start, end = _period(period_start, period_end)
    snap = await _snapshot(db, company_id, start, end, employee_id)
    return Response(us_payroll_export.build_csv(snap, await _documents(db, company_id)), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="nomina_{start}_{end}.csv"', "Cache-Control": "no-store"})
