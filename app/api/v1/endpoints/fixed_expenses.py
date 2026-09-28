"""Gastos fijos del modulo Inventario (049M) - TODAS las empresas con Inventario.

Boton "Gastos fijos" junto a Crear material, Modificar material y CSV:
servicios publicos, arriendo y otros gastos (con conceptos propios). Cada
registro: concepto, mes, valor, observacion y recibo (foto comprimida por
media_storage, 200 KB por recibo y cupo por empresa: la base es de 500 MB).
La tabla mes a mes suma por concepto y en total, y el estado de resultados
de Reportes descuenta estos gastos (fixed_expenses_for_period).

Todos los endpoints exigen sesion de la empresa (o Admin V2) y el modulo
Inventario; los paneles de mesero, cocina y caja no los usan.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_company_user_for_tenant, require_enabled_module
from app.services import fixed_expenses as engine
from app.services import media_storage
from app.web.admin_v2_routes import _active_session as active_admin_v2_session

router = APIRouter()
MODULE_CODE = "inventory"
PANEL_ROLES = {"mesero", "cocina", "caja", "cajero", "cajera", "bartender", "domiciliario"}
RECEIPTS_QUOTA_BYTES = 20 * 1024 * 1024  # por empresa
MAX_UPLOAD_BYTES = 12 * 1024 * 1024


def _clean(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").split())[:limit]


async def require_fixed_user(company_id: uuid.UUID, request: Request, authorization: str | None = Header(default=None),
                             db: AsyncSession = Depends(get_db)) -> str:
    await require_enabled_module(db, company_id, MODULE_CODE)
    if await active_admin_v2_session(request, db):
        return "Admin V2"
    user = await require_company_user_for_tenant(db, authorization, company_id)
    if str(getattr(user, "role", "") or "").strip().lower() in PANEL_ROLES:
        raise HTTPException(status_code=403, detail="role_not_allowed")
    return _clean(getattr(user, "full_name", "") or getattr(user, "email", "") or "Usuario", 180)


async def _table_exists(db: AsyncSession, name: str) -> bool:
    row = (await db.execute(text("SELECT to_regclass(:t) IS NOT NULL AS exists"), {"t": f"public.{name}"})).mappings().first()
    return bool(row and row.get("exists"))


async def load_concepts(db: AsyncSession, company_id: Any) -> dict[str, dict]:
    concepts = {key: {"key": key, "label": label, "group": group, "preset": True} for key, label, group in engine.PRESET_CONCEPTS}
    rows = (await db.execute(text("""
        SELECT key, label, group_key FROM fixed_expense_concepts WHERE company_id = CAST(:c AS uuid) ORDER BY lower(label)
    """), {"c": str(company_id)})).mappings().all()
    for row in rows:
        concepts.setdefault(row["key"], {"key": row["key"], "label": row["label"], "group": row["group_key"], "preset": False})
    return concepts


async def _records(db: AsyncSession, company_id: Any, first: date, last: date) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT e.id, e.concept_key, e.concept_label, e.group_key, e.month, e.amount, e.observation, e.source,
               e.created_by_name, e.created_at, (r.expense_id IS NOT NULL AND r.image_bytes IS NOT NULL) AS has_receipt
        FROM fixed_expenses e
        LEFT JOIN fixed_expense_receipts r ON r.company_id = e.company_id AND r.expense_id = e.id
        WHERE e.company_id = CAST(:c AS uuid) AND e.month BETWEEN :first AND :last
        ORDER BY e.month DESC, e.created_at DESC
    """), {"c": str(company_id), "first": first, "last": last})).mappings().all()
    return [dict(r) for r in rows]


def _record_payload(row: dict) -> dict:
    return {"id": str(row["id"]), "concept_key": row["concept_key"], "concept_label": row["concept_label"],
            "group": row["group_key"], "month": engine.month_label(row["month"]), "amount": float(engine.money(row["amount"])),
            "observation": row.get("observation") or "", "source": row.get("source") or "manual",
            "created_by_name": row.get("created_by_name") or "", "has_receipt": bool(row.get("has_receipt"))}


async def _payload(db: AsyncSession, company_id: uuid.UUID, until: date | None, months: int) -> dict:
    today = date.today()
    last = until or date(today.year, today.month, 1)
    window = engine.months_back(last, max(1, min(24, months)))
    concepts = await load_concepts(db, company_id)
    records = await _records(db, company_id, window[0], window[-1])
    return {
        "groups": engine.GROUPS,
        "concepts": list(concepts.values()),
        "records": [_record_payload(r) for r in records],
        "table": engine.monthly_table(records, window, concepts),
    }


@router.get("/companies/{company_id}")
async def get_fixed_expenses(company_id: uuid.UUID, until: str | None = None, months: int = 6,
                             db: AsyncSession = Depends(get_db), _u: str = Depends(require_fixed_user)) -> dict:
    try:
        last = engine.parse_month(until) if until else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Mes inválido.") from exc
    return await _payload(db, company_id, last, months)


class RecordIn(BaseModel):
    concept_key: str = Field(..., min_length=1, max_length=60)
    month: str = Field(..., min_length=7, max_length=10)
    amount: float = Field(..., gt=0, le=10_000_000_000)
    observation: str = Field(default="", max_length=1000)


async def _check_record(db: AsyncSession, company_id: uuid.UUID, payload: RecordIn) -> dict:
    concepts = await load_concepts(db, company_id)
    concept = concepts.get(payload.concept_key)
    if not concept:
        raise HTTPException(status_code=400, detail="Elige un concepto de la lista o agrega uno propio.")
    try:
        month = engine.parse_month(payload.month)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Elige el mes al que corresponde el gasto.") from exc
    return {"concept_key": concept["key"], "concept_label": concept["label"], "group_key": concept["group"], "month": month,
            "amount": engine.money(payload.amount), "observation": _clean(payload.observation, 1000)}


@router.post("/companies/{company_id}/records")
async def create_record(company_id: uuid.UUID, payload: RecordIn, db: AsyncSession = Depends(get_db),
                        user: str = Depends(require_fixed_user)) -> dict:
    values = await _check_record(db, company_id, payload)
    new_id = str(uuid.uuid4())
    await db.execute(text("""
        INSERT INTO fixed_expenses (id, company_id, concept_key, concept_label, group_key, month, amount, observation, created_by_name)
        VALUES (CAST(:id AS uuid), CAST(:c AS uuid), :concept_key, :concept_label, :group_key, :month, :amount, :observation, :by)
    """), {**values, "id": new_id, "c": str(company_id), "by": user})
    await db.commit()
    return {**await _payload(db, company_id, None, 6), "created_id": new_id}


@router.put("/companies/{company_id}/records/{record_id}")
async def update_record(company_id: uuid.UUID, record_id: uuid.UUID, payload: RecordIn, db: AsyncSession = Depends(get_db),
                        _u: str = Depends(require_fixed_user)) -> dict:
    values = await _check_record(db, company_id, payload)
    result = await db.execute(text("""
        UPDATE fixed_expenses SET concept_key = :concept_key, concept_label = :concept_label, group_key = :group_key,
               month = :month, amount = :amount, observation = :observation, updated_at = now()
        WHERE id = CAST(:id AS uuid) AND company_id = CAST(:c AS uuid)
    """), {**values, "id": str(record_id), "c": str(company_id)})
    if not getattr(result, "rowcount", 1):
        raise HTTPException(status_code=404, detail="Gasto no encontrado.")
    await db.commit()
    return await _payload(db, company_id, None, 6)


@router.delete("/companies/{company_id}/records/{record_id}")
async def delete_record(company_id: uuid.UUID, record_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                        _u: str = Depends(require_fixed_user)) -> dict:
    await db.execute(text("DELETE FROM fixed_expense_receipts WHERE company_id = CAST(:c AS uuid) AND expense_id = CAST(:id AS uuid)"),
                     {"id": str(record_id), "c": str(company_id)})
    result = await db.execute(text("DELETE FROM fixed_expenses WHERE id = CAST(:id AS uuid) AND company_id = CAST(:c AS uuid)"),
                              {"id": str(record_id), "c": str(company_id)})
    if not getattr(result, "rowcount", 1):
        raise HTTPException(status_code=404, detail="Gasto no encontrado.")
    await db.commit()
    return await _payload(db, company_id, None, 6)


class ConceptIn(BaseModel):
    label: str = Field(..., min_length=1, max_length=80)
    group: str = Field(default="otros", max_length=20)


@router.post("/companies/{company_id}/concepts")
async def add_concept(company_id: uuid.UUID, payload: ConceptIn, db: AsyncSession = Depends(get_db),
                      _u: str = Depends(require_fixed_user)) -> dict:
    label = _clean(payload.label, 80)
    key = engine.concept_key(label)
    if not key:
        raise HTTPException(status_code=400, detail="Escribe el nombre del concepto.")
    group = payload.group if payload.group in engine.GROUPS else "otros"
    if key in await load_concepts(db, company_id):
        raise HTTPException(status_code=409, detail=f"Ya existe {label}.")
    await db.execute(text("""
        INSERT INTO fixed_expense_concepts (company_id, key, label, group_key) VALUES (CAST(:c AS uuid), :key, :label, :group)
    """), {"c": str(company_id), "key": key, "label": label, "group": group})
    await db.commit()
    return {**await _payload(db, company_id, None, 6), "created_key": key}


@router.post("/companies/{company_id}/records/{record_id}/receipt")
async def upload_receipt(company_id: uuid.UUID, record_id: uuid.UUID, image: UploadFile = File(...),
                         db: AsyncSession = Depends(get_db), _u: str = Depends(require_fixed_user)) -> dict:
    exists = (await db.execute(text("SELECT 1 AS ok FROM fixed_expenses WHERE id = CAST(:id AS uuid) AND company_id = CAST(:c AS uuid)"),
                               {"id": str(record_id), "c": str(company_id)})).mappings().first()
    if not exists:
        raise HTTPException(status_code=404, detail="Gasto no encontrado.")
    raw = await image.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="El archivo es demasiado grande.")
    used = (await db.execute(text("""
        SELECT COALESCE(SUM(size_bytes), 0) AS used FROM fixed_expense_receipts
        WHERE company_id = CAST(:c AS uuid) AND expense_id <> CAST(:id AS uuid)
    """), {"c": str(company_id), "id": str(record_id)})).mappings().first()
    if int((used or {}).get("used") or 0) + media_storage.MAX_IMAGE_BYTES > RECEIPTS_QUOTA_BYTES:
        raise HTTPException(status_code=409, detail="Se llenó el espacio para recibos de esta empresa.")
    await db.execute(text("""
        INSERT INTO fixed_expense_receipts (company_id, expense_id) VALUES (CAST(:c AS uuid), CAST(:id AS uuid))
        ON CONFLICT (company_id, expense_id) DO NOTHING
    """), {"c": str(company_id), "id": str(record_id)})
    await media_storage.save_image(db, table="fixed_expense_receipts",
                                   key_columns={"company_id": str(company_id), "expense_id": str(record_id)},
                                   raw=raw, content_type=(image.content_type or "").lower())
    await db.execute(text("""
        UPDATE fixed_expense_receipts SET size_bytes = COALESCE(octet_length(image_bytes), 0)
        WHERE company_id = CAST(:c AS uuid) AND expense_id = CAST(:id AS uuid)
    """), {"c": str(company_id), "id": str(record_id)})
    await db.commit()
    return await _payload(db, company_id, None, 6)


@router.get("/companies/{company_id}/records/{record_id}/receipt")
async def get_receipt(company_id: uuid.UUID, record_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                      _u: str = Depends(require_fixed_user)) -> Response:
    found = await media_storage.get_image(db, table="fixed_expense_receipts",
                                          key_columns={"company_id": str(company_id), "expense_id": str(record_id)})
    if not found:
        raise HTTPException(status_code=404, detail="Sin recibo.")
    content, content_type = found
    return Response(content=content, media_type=content_type)


async def fixed_expenses_for_period(db: AsyncSession, company_id: Any, start: date, end: date) -> dict:
    """Para el estado de resultados de Reportes: gastos fijos del periodo
    (cada mes repartido por dias). Sin la tabla o sin registros, cero."""
    if not await _table_exists(db, "fixed_expenses"):
        return {"total": engine.money(0), "by_concept": []}
    first = date(start.year, start.month, 1)
    rows = (await db.execute(text("""
        SELECT concept_key, concept_label, group_key, month, amount FROM fixed_expenses
        WHERE company_id = CAST(:c AS uuid) AND month BETWEEN :first AND :last
    """), {"c": str(company_id), "first": first, "last": end})).mappings().all()
    return engine.prorated([dict(r) for r in rows], start, end)
