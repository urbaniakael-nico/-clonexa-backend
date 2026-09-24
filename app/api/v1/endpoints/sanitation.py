"""Modulo SANIDAD: planilla diaria de limpieza y logistica (048K).

Capacidad general, reutilizable por cualquier empresa: se activa desde el
catalogo de modulos de Admin V2 (codigo "sanidad"); hoy solo ASADERO EL
SOCIO lo tiene (migracion 021p). Cada empresa arma su propia lista de items
por secciones (con una lista base sugerida la primera vez), diligencia una
planilla por dia con responsable de Workforce, y al cerrarla queda firmada e
inmutable; las correcciones posteriores son notas con autor y hora. El
historial se ve, descarga e imprime en PDF con el logo y los datos de la
empresa.

Todos los endpoints exigen una sesion valida de la empresa (o Admin V2) y el
modulo activo; toda consulta filtra por company_id.
"""
from __future__ import annotations

import io
import json
import uuid
from datetime import date as calendar_date
from datetime import datetime, time as dt_time, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ADMIN_ROLES, get_db, require_company_user_for_tenant, require_enabled_module
from app.api.v1.endpoints.hospitality import (
    _hospitality_company_identity,
    _hsp_report_logo_reader,
    _hsp_report_zone,
)
from app.services import media_storage
from app.web.admin_v2_routes import _active_session as active_admin_v2_session

router = APIRouter()

MODULE_CODE = "sanidad"
SANIDAD_ADMIN_ROLES = ADMIN_ROLES | {
    "manager", "gerencia", "gerente", "dueno", "dueño", "owner", "propietario", "administrador",
}
DEFAULT_ALERT_HOUR = "22:00"
# Adjuntos (048L): solo fotos por ahora (los PDF esperan un bucket de
# objetos). media_storage las deja en <= 800 px y <= 200 KB; ademas un tope
# de lo que se acepta subir y un cupo total por empresa (ajustable en el
# modulo con attachments_quota_mb) para cuidar los 500 MB de la base.
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
DEFAULT_QUOTA_MB = 40

# Lista base sugerida (se carga una sola vez, cuando la empresa aun no tiene items).
BASE_ITEMS: list[tuple[str, str, bool, str]] = [
    ("Cocina", "Mesones y superficies limpios y desinfectados", False, ""),
    ("Cocina", "Utensilios y equipos lavados y guardados", False, ""),
    ("Cocina", "Pisos, paredes y desagües limpios", False, ""),
    ("Cocina", "Campana extractora y filtros sin grasa acumulada", False, ""),
    ("Neveras y temperaturas", "Temperatura de la nevera (0 a 4 °C)", True, "°C"),
    ("Neveras y temperaturas", "Temperatura del congelador (-18 °C o menos)", True, "°C"),
    ("Neveras y temperaturas", "Alimentos rotulados con fecha y tapados", False, ""),
    ("Neveras y temperaturas", "Sin productos vencidos ni en mal estado", False, ""),
    ("Manipulación de alimentos", "Personal con uniforme, gorro y tapabocas", False, ""),
    ("Manipulación de alimentos", "Lavado de manos al ingresar y entre tareas", False, ""),
    ("Manipulación de alimentos", "Crudos separados de cocidos", False, ""),
    ("Manipulación de alimentos", "Agua potable disponible", False, ""),
    ("Baños", "Baños limpios y desinfectados", False, ""),
    ("Baños", "Jabón, papel y toallas disponibles", False, ""),
    ("Áreas comunes", "Mesas, sillas y salón limpios", False, ""),
    ("Áreas comunes", "Sin evidencia de plagas", False, ""),
    ("Residuos", "Residuos separados en canecas con tapa", False, ""),
    ("Residuos", "Canecas vaciadas y lavadas", False, ""),
    ("Residuos", "Aceite usado almacenado para disposición", False, ""),
]


def _clean(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").split())[:limit]


# ---------------------------------------------------------------- auth ---
async def _actor(
    company_id: uuid.UUID, request: Request, authorization: str | None, db: AsyncSession, roles: set[str] | None,
) -> dict[str, Any]:
    await require_enabled_module(db, company_id, MODULE_CODE)
    if await active_admin_v2_session(request, db):
        return {"id": "", "name": "Admin V2"}
    user = await require_company_user_for_tenant(db, authorization, company_id, allowed_roles=roles)
    return {"id": str(user.id), "name": _clean(getattr(user, "full_name", "") or getattr(user, "email", "") or "Usuario", 160)}


async def require_sanidad_user(
    company_id: uuid.UUID, request: Request,
    authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Any logged-in user of THIS company (or Admin V2), module enabled."""
    return await _actor(company_id, request, authorization, db, None)


async def require_sanidad_admin(
    company_id: uuid.UUID, request: Request,
    authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Configuring the checklist: company admins/owners (or Admin V2)."""
    return await _actor(company_id, request, authorization, db, SANIDAD_ADMIN_ROLES)


# -------------------------------------------------------------- items ---
def _item_payload(row: Any) -> dict[str, Any]:
    data = dict(row)
    return {
        "id": str(data["id"]),
        "section": data["section"],
        "label": data["label"],
        "requires_value": bool(data["requires_value"]),
        "value_label": data.get("value_label") or "",
        "requires_support": bool(data.get("requires_support")),
        "position": int(data.get("position") or 0),
        "active": bool(data["active"]),
    }


async def _items(db: AsyncSession, company_id: uuid.UUID, *, include_inactive: bool = True) -> list[dict[str, Any]]:
    result = await db.execute(
        text(f"""
            SELECT * FROM sanitation_items
            WHERE company_id = :company_id {"" if include_inactive else "AND active IS TRUE"}
            ORDER BY position, created_at
        """),
        {"company_id": str(company_id)},
    )
    return [_item_payload(row) for row in result.mappings().all()]


async def _seed_base_items(db: AsyncSession, company_id: uuid.UUID) -> None:
    for position, (section, label, requires_value, value_label) in enumerate(BASE_ITEMS, start=1):
        await db.execute(
            text("""
                INSERT INTO sanitation_items (company_id, section, label, requires_value, value_label, position)
                VALUES (:company_id, :section, :label, :requires_value, :value_label, :position)
            """),
            {"company_id": str(company_id), "section": section, "label": label,
             "requires_value": requires_value, "value_label": value_label, "position": position * 10},
        )
    await db.commit()


class ItemIn(BaseModel):
    section: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=240)
    requires_value: bool = False
    value_label: str = Field(default="", max_length=40)
    requires_support: bool = False
    active: bool = True


class ItemPatch(BaseModel):
    section: str | None = Field(default=None, min_length=1, max_length=80)
    label: str | None = Field(default=None, min_length=1, max_length=240)
    requires_value: bool | None = None
    value_label: str | None = Field(default=None, max_length=40)
    requires_support: bool | None = None
    active: bool | None = None


class ReorderIn(BaseModel):
    ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)


@router.get("/companies/{company_id}/items")
async def list_items(
    company_id: uuid.UUID, db: AsyncSession = Depends(get_db), _actor_: dict = Depends(require_sanidad_user),
) -> dict[str, Any]:
    items = await _items(db, company_id)
    if not items:
        await _seed_base_items(db, company_id)
        items = await _items(db, company_id)
    return {"ok": True, "items": items}


@router.post("/companies/{company_id}/items", status_code=status.HTTP_201_CREATED)
async def create_item(
    company_id: uuid.UUID, payload: ItemIn, db: AsyncSession = Depends(get_db),
    _actor_: dict = Depends(require_sanidad_admin),
) -> dict[str, Any]:
    result = await db.execute(
        text("""
            INSERT INTO sanitation_items (company_id, section, label, requires_value, value_label, requires_support, position, active)
            VALUES (:company_id, :section, :label, :requires_value, :value_label, :requires_support,
                    COALESCE((SELECT MAX(position) FROM sanitation_items WHERE company_id = :company_id), 0) + 10, :active)
            RETURNING *
        """),
        {"company_id": str(company_id), "section": _clean(payload.section, 80), "label": _clean(payload.label),
         "requires_value": payload.requires_value, "value_label": _clean(payload.value_label, 40),
         "requires_support": payload.requires_support, "active": payload.active},
    )
    row = result.mappings().first()
    await db.commit()
    return {"ok": True, "item": _item_payload(row)}


@router.patch("/companies/{company_id}/items/{item_id}")
async def update_item(
    company_id: uuid.UUID, item_id: uuid.UUID, payload: ItemPatch, db: AsyncSession = Depends(get_db),
    _actor_: dict = Depends(require_sanidad_admin),
) -> dict[str, Any]:
    changes = payload.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Nada que cambiar.")
    for key in ("section", "label", "value_label"):
        if key in changes:
            changes[key] = _clean(changes[key], {"section": 80, "label": 240, "value_label": 40}[key])
    assignments = ", ".join(f"{key} = :{key}" for key in changes)
    result = await db.execute(
        text(f"""
            UPDATE sanitation_items SET {assignments}, updated_at = NOW()
            WHERE id = :item_id AND company_id = :company_id
            RETURNING *
        """),
        {**changes, "item_id": str(item_id), "company_id": str(company_id)},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item no encontrado.")
    await db.commit()
    return {"ok": True, "item": _item_payload(row)}


@router.post("/companies/{company_id}/items/reorder")
async def reorder_items(
    company_id: uuid.UUID, payload: ReorderIn, db: AsyncSession = Depends(get_db),
    _actor_: dict = Depends(require_sanidad_admin),
) -> dict[str, Any]:
    for position, item_id in enumerate(payload.ids, start=1):
        await db.execute(
            text("UPDATE sanitation_items SET position = :position, updated_at = NOW() WHERE id = :item_id AND company_id = :company_id"),
            {"position": position * 10, "item_id": str(item_id), "company_id": str(company_id)},
        )
    await db.commit()
    return {"ok": True, "items": await _items(db, company_id)}


# ------------------------------------------------------------- sheets ---
class EntryIn(BaseModel):
    item_id: uuid.UUID
    checked: bool = False
    observation: str = Field(default="", max_length=240)
    value: float | None = None


class SheetIn(BaseModel):
    responsible_employee_id: str = Field(default="", max_length=64)
    entries: list[EntryIn] = Field(default_factory=list, max_length=500)


class NoteIn(BaseModel):
    note: str = Field(min_length=1, max_length=1000)


def _compliance(entries: list[dict[str, Any]]) -> float:
    if not entries:
        return 0.0
    return round(100 * sum(1 for entry in entries if entry.get("checked")) / len(entries), 2)


def _sheet_payload(row: Any, notes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    data = dict(row)
    entries = data.get("entries")
    if isinstance(entries, str):
        entries = json.loads(entries or "[]")
    closed_at = data.get("closed_at")
    return {
        "id": str(data["id"]) if data.get("id") else None,
        "date": data["sheet_date"].isoformat() if hasattr(data["sheet_date"], "isoformat") else str(data["sheet_date"]),
        "status": data.get("status") or "open",
        "responsible_employee_id": data.get("responsible_employee_id") or "",
        "responsible_name": data.get("responsible_name") or "",
        "entries": entries or [],
        "compliance": float(data.get("compliance") or 0),
        "closed_at": closed_at.isoformat() if hasattr(closed_at, "isoformat") else closed_at,
        "closed_by": data.get("closed_by") or "",
        "notes": notes or [],
    }


async def _company_timezone(db: AsyncSession, company_id: uuid.UUID) -> str:
    result = await db.execute(text("SELECT timezone FROM companies WHERE id = :company_id"), {"company_id": str(company_id)})
    return str(_hsp_report_zone(result.scalar()))


async def _today(db: AsyncSession, company_id: uuid.UUID) -> calendar_date:
    return datetime.now(timezone.utc).astimezone(_hsp_report_zone(await _company_timezone(db, company_id))).date()


async def _sheet_row(db: AsyncSession, company_id: uuid.UUID, day: calendar_date, *, lock: bool = False):
    result = await db.execute(
        text(f"SELECT * FROM sanitation_sheets WHERE company_id = :company_id AND sheet_date = :day {'FOR UPDATE' if lock else ''}"),
        {"company_id": str(company_id), "day": day},
    )
    return result.mappings().first()


async def _notes(db: AsyncSession, company_id: uuid.UUID, sheet_id: Any) -> list[dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT note, author_name, created_at FROM sanitation_sheet_notes
            WHERE company_id = :company_id AND sheet_id = :sheet_id ORDER BY created_at
        """),
        {"company_id": str(company_id), "sheet_id": str(sheet_id)},
    )
    return [
        {"note": row["note"], "author": row["author_name"], "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else row["created_at"]}
        for row in result.mappings().all()
    ]


async def _staff(db: AsyncSession, company_id: uuid.UUID) -> list[dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT id, full_name, role FROM employees
            WHERE company_id = :company_id
              AND lower(COALESCE(status, 'active')) NOT IN ('archived', 'inactive', 'inactivo', 'retirado', 'deleted')
            ORDER BY lower(full_name)
        """),
        {"company_id": str(company_id)},
    )
    return [{"id": str(row["id"]), "name": row["full_name"] or "Empleado", "role": row["role"] or ""} for row in result.mappings().all()]


async def _attachments_meta(db: AsyncSession, company_id: uuid.UUID, day: calendar_date) -> dict[str, dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT item_id, file_name, image_content_type, size_bytes, updated_at FROM sanitation_attachments
            WHERE company_id = :company_id AND sheet_date = :day AND image_bytes IS NOT NULL
        """),
        {"company_id": str(company_id), "day": day},
    )
    return {
        str(row["item_id"]): {
            "name": row["file_name"] or "foto.jpg", "content_type": row["image_content_type"] or "image/jpeg",
            "size": int(row["size_bytes"] or 0),
            "updated_at": row["updated_at"].isoformat() if hasattr(row["updated_at"], "isoformat") else row["updated_at"],
        }
        for row in result.mappings().all()
    }


async def _build_entries(
    db: AsyncSession, company_id: uuid.UUID, submitted: list[EntryIn], day: calendar_date | None = None,
) -> list[dict[str, Any]]:
    """Snapshot of the company's ACTIVE items (label/section as they are now)
    merged with what was filled in and the day's attachments; unknown or
    other-company ids are ignored."""
    by_id = {str(entry.item_id): entry for entry in submitted}
    attachments = await _attachments_meta(db, company_id, day) if day else {}
    entries = []
    for item in await _items(db, company_id, include_inactive=False):
        entry = by_id.get(item["id"])
        entries.append({
            "item_id": item["id"], "section": item["section"], "label": item["label"],
            "requires_value": item["requires_value"], "value_label": item["value_label"],
            "requires_support": item.get("requires_support", False),
            "checked": bool(entry.checked) if entry else False,
            "observation": _clean(entry.observation) if entry else "",
            "value": entry.value if (entry and item["requires_value"]) else None,
            "attachment": attachments.get(item["id"]),
        })
    return entries


async def _responsible_name(db: AsyncSession, company_id: uuid.UUID, employee_id: str) -> str:
    if not employee_id:
        return ""
    try:
        employee_uuid = uuid.UUID(employee_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Responsable invalido.")
    result = await db.execute(
        text("SELECT full_name FROM employees WHERE id = :employee_id AND company_id = :company_id"),
        {"employee_id": str(employee_uuid), "company_id": str(company_id)},
    )
    name = result.scalar()
    if name is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El responsable debe ser del personal de la empresa.")
    return _clean(name, 160)


def _parse_day(value: str) -> calendar_date:
    try:
        return calendar_date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Fecha invalida (AAAA-MM-DD).")


@router.get("/companies/{company_id}/sheets/{day}")
async def get_sheet(
    company_id: uuid.UUID, day: str, db: AsyncSession = Depends(get_db),
    _actor_: dict = Depends(require_sanidad_user),
) -> dict[str, Any]:
    sheet_day = _parse_day(day)
    row = await _sheet_row(db, company_id, sheet_day)
    if row:
        sheet = _sheet_payload(row, await _notes(db, company_id, row["id"]))
        if sheet["status"] != "closed":
            attachments = await _attachments_meta(db, company_id, sheet_day)
            for entry in sheet["entries"]:
                entry["attachment"] = attachments.get(str(entry.get("item_id")))
    else:
        items = await _items(db, company_id, include_inactive=False)
        if not items and not await _items(db, company_id):
            await _seed_base_items(db, company_id)
        sheet = _sheet_payload({"id": None, "sheet_date": sheet_day, "status": "open",
                                "entries": await _build_entries(db, company_id, [], sheet_day)})
    return {"ok": True, "sheet": sheet, "staff": await _staff(db, company_id), "today": (await _today(db, company_id)).isoformat()}


async def _save(db: AsyncSession, company_id: uuid.UUID, sheet_day: calendar_date, payload: SheetIn, *, close_by: str = "") -> dict[str, Any]:
    if sheet_day > await _today(db, company_id):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No se puede diligenciar una planilla de un dia futuro.")
    existing = await _sheet_row(db, company_id, sheet_day, lock=True)
    if existing and existing["status"] == "closed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La planilla ya esta cerrada. Agrega una nota posterior.")
    responsible_id = _clean(payload.responsible_employee_id, 64)
    responsible = await _responsible_name(db, company_id, responsible_id)
    if close_by and not responsible:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Elige el responsable del dia antes de cerrar.")
    entries = await _build_entries(db, company_id, payload.entries, sheet_day)
    missing_support = [entry["label"] for entry in entries if entry["requires_support"] and not entry["attachment"]]
    params = {
        "company_id": str(company_id), "day": sheet_day, "responsible_id": responsible_id, "responsible": responsible,
        "entries": json.dumps(entries, ensure_ascii=False), "compliance": _compliance(entries),
        "status": "closed" if close_by else "open", "closed_by": close_by,
    }
    result = await db.execute(
        text("""
            INSERT INTO sanitation_sheets (company_id, sheet_date, status, responsible_employee_id, responsible_name,
                                           entries, compliance, closed_at, closed_by)
            VALUES (:company_id, :day, :status, :responsible_id, :responsible, CAST(:entries AS jsonb), :compliance,
                    CASE WHEN :status = 'closed' THEN NOW() END, :closed_by)
            ON CONFLICT (company_id, sheet_date) DO UPDATE
            SET status = EXCLUDED.status, responsible_employee_id = EXCLUDED.responsible_employee_id,
                responsible_name = EXCLUDED.responsible_name, entries = EXCLUDED.entries,
                compliance = EXCLUDED.compliance, closed_at = EXCLUDED.closed_at, closed_by = EXCLUDED.closed_by,
                updated_at = NOW()
            WHERE sanitation_sheets.status <> 'closed'
            RETURNING *
        """),
        params,
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La planilla ya esta cerrada. Agrega una nota posterior.")
    await db.commit()
    return {"ok": True, "sheet": _sheet_payload(row), "missing_support": missing_support}


@router.put("/companies/{company_id}/sheets/{day}")
async def save_sheet(
    company_id: uuid.UUID, day: str, payload: SheetIn, db: AsyncSession = Depends(get_db),
    _actor_: dict = Depends(require_sanidad_user),
) -> dict[str, Any]:
    return await _save(db, company_id, _parse_day(day), payload)


@router.post("/companies/{company_id}/sheets/{day}/close")
async def close_sheet(
    company_id: uuid.UUID, day: str, payload: SheetIn, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_sanidad_user),
) -> dict[str, Any]:
    """Signs the day: date, time, responsible, who closed it and compliance.
    From here on the sheet is immutable."""
    return await _save(db, company_id, _parse_day(day), payload, close_by=actor["name"] or "Usuario")


@router.post("/companies/{company_id}/sheets/{day}/notes", status_code=status.HTTP_201_CREATED)
async def add_note(
    company_id: uuid.UUID, day: str, payload: NoteIn, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_sanidad_user),
) -> dict[str, Any]:
    row = await _sheet_row(db, company_id, _parse_day(day))
    if not row or row["status"] != "closed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Las notas posteriores son para planillas cerradas.")
    await db.execute(
        text("""
            INSERT INTO sanitation_sheet_notes (company_id, sheet_id, note, author_name)
            VALUES (:company_id, :sheet_id, :note, :author)
        """),
        {"company_id": str(company_id), "sheet_id": str(row["id"]), "note": _clean(payload.note, 1000), "author": actor["name"]},
    )
    await db.commit()
    return {"ok": True, "sheet": _sheet_payload(row, await _notes(db, company_id, row["id"]))}


@router.get("/companies/{company_id}/sheets")
async def list_sheets(
    company_id: uuid.UUID, limit: int = Query(default=90, ge=1, le=366), db: AsyncSession = Depends(get_db),
    _actor_: dict = Depends(require_sanidad_user),
) -> dict[str, Any]:
    result = await db.execute(
        text("""
            SELECT sheet_date, status, responsible_name, compliance, closed_at, closed_by
            FROM sanitation_sheets
            WHERE company_id = :company_id AND status = 'closed'
            ORDER BY sheet_date DESC LIMIT :limit
        """),
        {"company_id": str(company_id), "limit": limit},
    )
    return {"ok": True, "sheets": [
        {"date": row["sheet_date"].isoformat(), "responsible_name": row["responsible_name"],
         "compliance": float(row["compliance"] or 0),
         "closed_at": row["closed_at"].isoformat() if row["closed_at"] else None, "closed_by": row["closed_by"]}
        for row in result.mappings().all()
    ]}


# ---------------------------------------------------------- attachments ---
async def _open_day_for_attachment(db: AsyncSession, company_id: uuid.UUID, day: str, item_id: uuid.UUID) -> calendar_date:
    sheet_day = _parse_day(day)
    if sheet_day > await _today(db, company_id):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No se puede adjuntar en un dia futuro.")
    row = await _sheet_row(db, company_id, sheet_day)
    if row and row["status"] == "closed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La planilla ya esta cerrada: sus soportes no se pueden cambiar.")
    items = {item["id"] for item in await _items(db, company_id, include_inactive=False)}
    if str(item_id) not in items:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item no encontrado.")
    return sheet_day


async def _quota_bytes(db: AsyncSession, company_id: uuid.UUID) -> int:
    result = await db.execute(
        text("""
            SELECT cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id = :company_id AND m.code = :code LIMIT 1
        """),
        {"company_id": str(company_id), "code": MODULE_CODE},
    )
    settings = result.scalar()
    settings = json.loads(settings) if isinstance(settings, str) else (settings or {})
    try:
        megabytes = float(settings.get("attachments_quota_mb") or DEFAULT_QUOTA_MB)
    except (TypeError, ValueError):
        megabytes = DEFAULT_QUOTA_MB
    return int(megabytes * 1024 * 1024)


@router.post("/companies/{company_id}/sheets/{day}/items/{item_id}/attachment")
async def upload_attachment(
    company_id: uuid.UUID, day: str, item_id: uuid.UUID, file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db), actor: dict = Depends(require_sanidad_user),
) -> dict[str, Any]:
    """Adds or replaces the photo of one item for one day (open sheet only)."""
    sheet_day = await _open_day_for_attachment(db, company_id, day, item_id)
    content_type = (file.content_type or "").lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Por ahora solo se aceptan fotos (JPG, PNG o WEBP). Los PDF llegan con el almacenamiento de archivos.")
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"La foto pesa mas de {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    params = {"company_id": str(company_id), "day": sheet_day, "item_id": str(item_id)}
    used = await db.execute(
        text("""
            SELECT COALESCE(SUM(size_bytes), 0) FROM sanitation_attachments
            WHERE company_id = :company_id AND NOT (sheet_date = :day AND item_id = :item_id)
        """),
        params,
    )
    quota = await _quota_bytes(db, company_id)
    if int(used.scalar() or 0) + media_storage.MAX_IMAGE_BYTES > quota:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Se lleno el espacio de soportes de Sanidad ({quota // (1024 * 1024)} MB). Pide ampliarlo.")
    await db.execute(
        text("""
            INSERT INTO sanitation_attachments (company_id, sheet_date, item_id, file_name, uploaded_by)
            VALUES (:company_id, :day, :item_id, :file_name, :uploaded_by)
            ON CONFLICT (company_id, sheet_date, item_id)
            DO UPDATE SET file_name = EXCLUDED.file_name, uploaded_by = EXCLUDED.uploaded_by, updated_at = NOW()
        """),
        {**params, "file_name": _clean(file.filename or "foto.jpg", 160), "uploaded_by": actor["name"]},
    )
    key_columns = {"company_id": str(company_id), "sheet_date": sheet_day, "item_id": str(item_id)}
    await media_storage.save_image(db, table="sanitation_attachments", key_columns=key_columns, raw=raw, content_type=content_type)
    await db.execute(
        text("""
            UPDATE sanitation_attachments SET size_bytes = COALESCE(octet_length(image_bytes), 0)
            WHERE company_id = :company_id AND sheet_date = :day AND item_id = :item_id
        """),
        params,
    )
    await db.commit()
    meta = (await _attachments_meta(db, company_id, sheet_day)).get(str(item_id))
    return {"ok": True, "attachment": meta}


@router.get("/companies/{company_id}/sheets/{day}/items/{item_id}/attachment")
async def get_attachment(
    company_id: uuid.UUID, day: str, item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), _actor_: dict = Depends(require_sanidad_user),
) -> Response:
    """Any day, open or closed (history)."""
    found = await media_storage.get_image(
        db, table="sanitation_attachments",
        key_columns={"company_id": str(company_id), "sheet_date": _parse_day(day), "item_id": str(item_id)},
    )
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sin soporte adjunto.")
    content, content_type = found
    return Response(content=content, media_type=content_type, headers={"Cache-Control": "private, max-age=300"})


@router.delete("/companies/{company_id}/sheets/{day}/items/{item_id}/attachment")
async def delete_attachment(
    company_id: uuid.UUID, day: str, item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), _actor_: dict = Depends(require_sanidad_user),
) -> dict[str, Any]:
    sheet_day = await _open_day_for_attachment(db, company_id, day, item_id)
    await db.execute(
        text("DELETE FROM sanitation_attachments WHERE company_id = :company_id AND sheet_date = :day AND item_id = :item_id"),
        {"company_id": str(company_id), "day": sheet_day, "item_id": str(item_id)},
    )
    await db.commit()
    return {"ok": True}


async def _attachment_images(db: AsyncSession, company_id: uuid.UUID, day: calendar_date) -> dict[str, dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT item_id, file_name, image_bytes, image_content_type FROM sanitation_attachments
            WHERE company_id = :company_id AND sheet_date = :day AND image_bytes IS NOT NULL
        """),
        {"company_id": str(company_id), "day": day},
    )
    return {str(row["item_id"]): {"name": row["file_name"], "bytes": bytes(row["image_bytes"]),
                                   "content_type": row["image_content_type"]} for row in result.mappings().all()}


# ---------------------------------------------------------------- PDF ---
async def _company_details(db: AsyncSession, company_id: uuid.UUID) -> dict[str, Any]:
    identity = await _hospitality_company_identity(db, company_id)
    details = {"name": identity.get("name") or "Empresa", "logo_url": identity.get("logo_url") or "",
               "nit": "", "address": "", "phone": "", "timezone": identity.get("timezone") or "America/Bogota"}
    try:
        exists = await db.execute(text("SELECT to_regclass('public.sale_document_settings')"))
        if exists.scalar():
            result = await db.execute(text("SELECT config FROM sale_document_settings WHERE company_id = :company_id"),
                                      {"company_id": str(company_id)})
            config = result.scalar() or {}
            config = json.loads(config) if isinstance(config, str) else config
            for key in ("nit", "address", "phone"):
                details[key] = _clean((config or {}).get(key), 120)
            details["name"] = _clean((config or {}).get("trade_name"), 160) or details["name"]
            details["logo_url"] = (config or {}).get("logo_url") or details["logo_url"]
    except Exception:
        await db.rollback()
    return details


def _platypus_image(source: Any, max_width: float, max_height: float):
    """platypus.Image needs a path or a file-like object (an ImageReader
    raises TypeError), so always hand it PNG/JPEG bytes."""
    from reportlab.platypus import Image

    if isinstance(source, (bytes, bytearray)):
        raw = bytes(source)
    else:  # ImageReader from _hsp_report_logo_reader
        pil = getattr(source, "_image", None)
        if pil is None:
            return None
        buffer = io.BytesIO()
        pil.convert("RGBA" if pil.mode in ("RGBA", "LA", "P") else "RGB").save(buffer, format="PNG")
        raw = buffer.getvalue()
    from reportlab.lib.utils import ImageReader

    width, height = ImageReader(io.BytesIO(raw)).getSize()
    ratio = min(max_width / max(width, 1), max_height / max(height, 1))
    return Image(io.BytesIO(raw), width=width * ratio, height=height * ratio)


def build_sheet_pdf(company: dict[str, Any], sheet: dict[str, Any], images: dict[str, dict[str, Any]] | None = None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm,
                            bottomMargin=16 * mm, title=f"Planilla de Sanidad {sheet['date']}", author=company["name"])
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8, leading=10)
    cell = ParagraphStyle("cell", parent=styles["Normal"], fontSize=8.5, leading=10.5)
    story: list[Any] = []

    header = [Paragraph(f"<b>{company['name']}</b>", styles["Title"])]
    extra = " · ".join(value for value in (
        f"NIT {company['nit']}" if company.get("nit") else "", company.get("address") or "", company.get("phone") or "") if value)
    if extra:
        header.append(Paragraph(extra, small))
    logo = None
    try:
        reader = _hsp_report_logo_reader(company.get("logo_url"))
        logo = _platypus_image(reader, 30 * mm, 18 * mm) if reader else None
    except Exception:
        logo = None
    if logo:
        story.append(Table([[logo, header]], colWidths=[36 * mm, None], style=[("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    else:
        story.extend(header)
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("<b>PLANILLA DIARIA DE SANIDAD</b> — limpieza, desinfección y logística", styles["Heading3"]))

    zone = _hsp_report_zone(company.get("timezone"))
    closed = sheet.get("closed_at")
    closed_text = datetime.fromisoformat(closed).astimezone(zone).strftime("%d/%m/%Y %H:%M") if closed else "SIN CERRAR (borrador)"
    story.append(Table([
        ["Fecha", calendar_date.fromisoformat(sheet["date"]).strftime("%d/%m/%Y"), "Responsable", sheet.get("responsible_name") or "-"],
        ["Cumplimiento", f"{sheet.get('compliance', 0):.0f}%", "Cerrada", f"{closed_text}" + (f" · {sheet['closed_by']}" if sheet.get("closed_by") else "")],
    ], colWidths=[28 * mm, 45 * mm, 28 * mm, None], style=[
        ("FONTSIZE", (0, 0), (-1, -1), 9), ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"), ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke), ("BACKGROUND", (2, 0), (2, -1), colors.whitesmoke),
    ]))
    story.append(Spacer(1, 4 * mm))

    rows = [["Sección", "Ítem", "OK", "Valor", "Observación"]]
    styles_rows = [("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                   ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                   ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (2, 1), (3, -1), "CENTER")]
    images = images or {}
    supported = []
    for index, entry in enumerate(sheet.get("entries") or [], start=1):
        value = entry.get("value")
        has_support = bool(entry.get("attachment")) or str(entry.get("item_id")) in images
        observation = entry.get("observation") or ""
        if has_support:
            supported.append(entry)
            observation = f"{observation}<br/><i>Con soporte adjunto</i>" if observation else "<i>Con soporte adjunto</i>"
        rows.append([
            Paragraph(entry.get("section") or "", cell), Paragraph(entry.get("label") or "", cell),
            "✔" if entry.get("checked") else "✘",
            f"{value:g} {entry.get('value_label') or ''}".strip() if isinstance(value, (int, float)) else "",
            Paragraph(observation, cell),
        ])
        if not entry.get("checked"):
            styles_rows.append(("TEXTCOLOR", (2, index), (2, index), colors.HexColor("#b91c1c")))
    story.append(Table(rows, colWidths=[32 * mm, 70 * mm, 10 * mm, 20 * mm, None], repeatRows=1, style=styles_rows))

    if supported:
        story.append(Spacer(1, 5 * mm))
        story.append(Paragraph(f"<b>Soportes del día ({len(supported)})</b>", styles["Heading4"]))
        for number, entry in enumerate(supported, start=1):
            image = images.get(str(entry.get("item_id")))
            name = (entry.get("attachment") or {}).get("name") or (image or {}).get("name") or "foto"
            caption = Paragraph(f"{number}. <b>{entry.get('section') or ''}</b> · {entry.get('label') or ''}<br/>{name}", small)
            picture = ""
            if image:
                try:
                    picture = _platypus_image(image["bytes"], 60 * mm, 45 * mm) or ""
                except Exception:
                    picture = Paragraph("(imagen no disponible)", small)
            story.append(Table([[picture, caption]], colWidths=[64 * mm, None],
                               style=[("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))

    if sheet.get("notes"):
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph("<b>Notas posteriores al cierre</b>", styles["Heading4"]))
        for note in sheet["notes"]:
            when = datetime.fromisoformat(note["created_at"]).astimezone(zone).strftime("%d/%m/%Y %H:%M") if note.get("created_at") else ""
            story.append(Paragraph(f"{when} · {note.get('author') or ''}: {note.get('note') or ''}", small))

    story.append(Spacer(1, 12 * mm))
    story.append(Table([["_" * 38, "_" * 38], ["Firma del responsable", "Firma de quien revisa"]],
                       colWidths=[90 * mm, 90 * mm], style=[("FONTSIZE", (0, 0), (-1, -1), 8.5), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(16 * mm, 9 * mm, f"{company['name']} · Planilla de Sanidad {sheet['date']} · generada por CLONEXA")
        canvas.drawRightString(letter[0] - 16 * mm, 9 * mm, f"Página {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


@router.get("/companies/{company_id}/sheets/{day}/pdf")
async def sheet_pdf(
    company_id: uuid.UUID, day: str, db: AsyncSession = Depends(get_db),
    _actor_: dict = Depends(require_sanidad_user),
) -> StreamingResponse:
    row = await _sheet_row(db, company_id, _parse_day(day))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hay planilla para ese dia.")
    sheet = _sheet_payload(row, await _notes(db, company_id, row["id"]))
    images = await _attachment_images(db, company_id, _parse_day(day))
    pdf = build_sheet_pdf(await _company_details(db, company_id), sheet, images)
    return StreamingResponse(
        iter([pdf]), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="planilla_sanidad_{sheet["date"]}.pdf"'},
    )


# ------------------------------------------------------ dashboard alert ---
@router.get("/companies/{company_id}/status")
async def sanitation_status(
    company_id: uuid.UUID, db: AsyncSession = Depends(get_db),
    _actor_: dict = Depends(require_sanidad_user),
) -> dict[str, Any]:
    """Dashboard alert: the day's sheet was not filled in when the day ends
    (module setting alert_hour, default 22:00), or yesterday's was never
    closed (only for days since the module was activated)."""
    result = await db.execute(
        text("""
            SELECT cm.settings, cm.activated_at FROM company_modules cm JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id = :company_id AND m.code = :code LIMIT 1
        """),
        {"company_id": str(company_id), "code": MODULE_CODE},
    )
    module = result.mappings().first() or {}
    settings = module.get("settings") if isinstance(module.get("settings"), dict) else {}
    zone = _hsp_report_zone(await _company_timezone(db, company_id))
    now_local = datetime.now(timezone.utc).astimezone(zone)
    try:
        hours, minutes = str(settings.get("alert_hour") or DEFAULT_ALERT_HOUR).split(":")[:2]
        alert_at = dt_time(int(hours), int(minutes))
    except Exception:
        alert_at = dt_time(22, 0)
    today = now_local.date()
    activated = module.get("activated_at")
    activated_day = activated.astimezone(zone).date() if hasattr(activated, "astimezone") else today
    closed = await db.execute(
        text("""
            SELECT sheet_date FROM sanitation_sheets
            WHERE company_id = :company_id AND status = 'closed' AND sheet_date IN (:today, :yesterday)
        """),
        {"company_id": str(company_id), "today": today, "yesterday": today.fromordinal(today.toordinal() - 1)},
    )
    closed_days = {row[0] for row in closed.all()}
    pending = []
    yesterday = today.fromordinal(today.toordinal() - 1)
    if yesterday >= activated_day and yesterday not in closed_days:
        pending.append(yesterday.isoformat())
    if now_local.time() >= alert_at and today not in closed_days:
        pending.append(today.isoformat())
    return {
        "ok": True, "today": today.isoformat(), "today_closed": today in closed_days, "alert": bool(pending),
        "pending_dates": pending, "alert_hour": alert_at.strftime("%H:%M"),
        "message": ("Falta diligenciar la planilla de Sanidad del " + " y del ".join(
            calendar_date.fromisoformat(value).strftime("%d/%m") for value in pending) + ".") if pending else "",
    }
