"""Board de gerencia de Reportes y perimetros por lugar (interruptor reports_board).

Todas las rutas exigen sesion desde el primer dia: Admin V2 o un usuario de ESA empresa con
un rol permitido, validado aqui. Sin sesion 401, otra empresa o rol sin acceso 403,
interruptor apagado 404. Un supervisor solo recibe la operacion de su lugar (sin lugar, las
dos). Perimetros y supervisores: solo dueno / admin.
- GET  ""                         todo el Board (?start&end) o solo el estado en vivo (?part=live)
- GET  "/export.pdf|marks.csv|notes.csv"
- GET  "/places"                  perimetros, supervisores y alerta de overtime
- PUT  "/places/{id}"             guardar perimetros y supervisores de un lugar
- POST "/places/{id}/suggest"     centro sugerido (NO guarda nada)
- POST "/places/{id}/recalculate" volver a medir marcas viejas (no cambia horas)
- PUT  "/settings"                alerta de overtime (horas)
"""
from __future__ import annotations

import gzip
import json
from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import reports_board as svc
from app.services import reports_board_export as export
from app.services import us_time, work_location_geo as geo, work_locations

router = APIRouter()
OFF = "El Board de gerencia no está activo para esta empresa."


async def actor(company_id: UUID, request: Request, authorization: Optional[str] = Header(default=None),
                db: AsyncSession = Depends(get_db)) -> dict:
    from app.web.admin_v2_routes import _active_session

    if await _active_session(request, db):
        who = {"role": "owner", "name": "Admin V2", "email": "", "places": None, "no_place": False}
    else:
        from app.api.deps import require_company_user_for_tenant

        user = await require_company_user_for_tenant(db, authorization, company_id)
        role = work_locations.role_of(getattr(user, "role", ""))
        who = {"role": role, "name": str(getattr(user, "full_name", "") or getattr(user, "email", "") or "usuario"),
               "email": str(getattr(user, "email", "") or ""), "places": None, "no_place": False}
        if role not in svc.ACCESS_ROLES:
            raise HTTPException(status_code=403, detail="Tu rol no tiene acceso al Board de gerencia.")
    if not await geo.is_on(db, company_id):
        raise HTTPException(status_code=404, detail=OFF)
    if who["role"] not in svc.ALL_PLACES_ROLES:
        places = await geo.supervisor_places(db, company_id, who["email"], who["name"])
        # Sin lugar: ve las dos operaciones y la pantalla lo avisa.
        who["places"] = places or None
        who["no_place"] = not places
    return who


def manager(who: dict = Depends(actor)) -> dict:
    if who["role"] not in svc.MANAGE_ROLES:
        raise HTTPException(status_code=403, detail="Solo el dueño o el administrador de la empresa administra perímetros y supervisores.")
    return who


def _json_response(request: Request, data: Any) -> Response:
    """Con 60 a 100 personas y un mes, la respuesta pesa: va comprimida si el navegador puede."""
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    headers = {"Cache-Control": "no-store", "Vary": "Accept-Encoding"}
    if len(body) > 1024 and "gzip" in request.headers.get("accept-encoding", "").lower():
        body = gzip.compress(body, compresslevel=5)
        headers["Content-Encoding"] = "gzip"
    return Response(content=body, media_type="application/json", headers=headers)


def _period(start: Optional[date], end: Optional[date]) -> tuple[date, date]:
    try:
        return svc.parse_period(start, end, datetime.now(timezone.utc).date())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


async def _board(db: AsyncSession, company_id: UUID, who: dict, start: Optional[date], end: Optional[date]) -> dict:
    first, last = _period(start, end)
    board = await svc.build(db, company_id, first, last, places=who["places"])
    board["scope"] = {"limited": who["places"] is not None, "supervisor_no_place": who["no_place"]}
    board["can_manage"] = who["role"] in svc.MANAGE_ROLES
    return board


@router.get("/companies/{company_id}")
async def get_board(company_id: UUID, request: Request, start: Optional[date] = Query(None), end: Optional[date] = Query(None),
                    part: Optional[str] = Query(None), who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> Response:
    if part == "live":
        return _json_response(request, await svc.live_block(db, company_id, places=who["places"]))
    return _json_response(request, await _board(db, company_id, who, start, end))


def _download(body: bytes, media: str, name: str) -> Response:
    return Response(content=body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


@router.get("/companies/{company_id}/export.pdf")
async def get_pdf(company_id: UUID, start: Optional[date] = Query(None), end: Optional[date] = Query(None),
                  who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> Response:
    board = await _board(db, company_id, who, start, end)
    return _download(export.build_pdf(board), "application/pdf", f"board_{board['period']['start']}_{board['period']['end']}.pdf")


@router.get("/companies/{company_id}/marks.csv")
async def get_marks_csv(company_id: UUID, start: Optional[date] = Query(None), end: Optional[date] = Query(None),
                        who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> Response:
    board = await _board(db, company_id, who, start, end)
    return _download(export.build_marks_csv(board).encode("utf-8"), "text/csv; charset=utf-8", f"marcaciones_{board['period']['start']}_{board['period']['end']}.csv")


@router.get("/companies/{company_id}/notes.csv")
async def get_notes_csv(company_id: UUID, start: Optional[date] = Query(None), end: Optional[date] = Query(None),
                        who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> Response:
    board = await _board(db, company_id, who, start, end)
    return _download(export.build_notes_csv(board).encode("utf-8"), "text/csv; charset=utf-8", f"notas_{board['period']['start']}_{board['period']['end']}.csv")


def _bad(exc: geo.Invalid) -> HTTPException:
    return HTTPException(status_code=422, detail=exc.message)


@router.get("/companies/{company_id}/places")
async def get_places(company_id: UUID, who: dict = Depends(manager), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    locations = await work_locations.list_locations(db, company_id)
    perimeters = await geo.perimeters_by_place(db, company_id)
    supervisors = await geo.supervisors_by_place(db, company_id)
    settings = await geo.module_settings(db, company_id)
    return {
        "ok": True, "default_radius_m": geo.DEFAULT_RADIUS_M, "near_ot_hours": geo.near_ot_minutes(settings) / 60,
        "places": [{**loc, "abbr": us_time.abbr(loc["timezone"]), "perimeters": perimeters.get(loc["id"], []), "supervisors": supervisors.get(loc["id"], [])} for loc in locations],
        "employees": [{"id": e["id"], "name": e["name"], "role": e["role"]} for e in await geo.active_employees(db, company_id)],
    }


@router.put("/companies/{company_id}/places/{location_id}")
async def put_place(company_id: UUID, location_id: UUID, body: dict = Body(...), who: dict = Depends(manager), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    try:
        return {"ok": True, **await geo.save_place(db, company_id, location_id, body, who["name"])}
    except geo.Invalid as exc:
        await db.rollback()
        raise _bad(exc) from None


@router.post("/companies/{company_id}/places/{location_id}/suggest")
async def post_suggest(company_id: UUID, location_id: UUID, who: dict = Depends(manager), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    try:
        return {"ok": True, **await geo.suggestion(db, company_id, location_id)}
    except geo.Invalid as exc:
        raise _bad(exc) from None


@router.post("/companies/{company_id}/places/{location_id}/recalculate")
async def post_recalculate(company_id: UUID, location_id: UUID, who: dict = Depends(manager), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    try:
        return {"ok": True, **await geo.recalculate(db, company_id, location_id)}
    except geo.Invalid as exc:
        await db.rollback()
        raise _bad(exc) from None


@router.put("/companies/{company_id}/settings")
async def put_settings(company_id: UUID, body: dict = Body(...), who: dict = Depends(manager), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    try:
        return {"ok": True, "near_ot_hours": await geo.save_near_ot(db, company_id, body.get("near_ot_hours"))}
    except geo.Invalid as exc:
        await db.rollback()
        raise _bad(exc) from None
