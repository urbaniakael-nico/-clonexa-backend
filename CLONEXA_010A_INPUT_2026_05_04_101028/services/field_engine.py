from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.field import (
    FieldBillingProject,
    FieldMaterial,
    FieldMaterialMovement,
    FieldMaterialRequest,
    FieldMaterialRequestItem,
    FieldTechnician,
    FieldTechnicianMaterialStock,
)


def _payload_dict(payload: Any) -> dict:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_unset=True)
    if isinstance(payload, dict):
        return {k: v for k, v in payload.items() if v is not None}
    return {k: v for k, v in vars(payload).items() if v is not None}


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


async def _get_or_404(db: AsyncSession, model, company_id: UUID, object_id: UUID, label: str):
    result = await db.execute(select(model).where(model.company_id == company_id, model.id == object_id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail=f"{label} no existe.")
    return obj


async def list_billing_projects(db: AsyncSession, company_id: UUID):
    result = await db.execute(
        select(FieldBillingProject)
        .where(FieldBillingProject.company_id == company_id)
        .order_by(FieldBillingProject.created_at.desc())
    )
    return result.scalars().all()


async def create_billing_project(db: AsyncSession, company_id: UUID, payload):
    project = FieldBillingProject(company_id=company_id, **_payload_dict(payload))
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


async def update_billing_project(db: AsyncSession, company_id: UUID, billing_id: UUID, payload):
    project = await _get_or_404(db, FieldBillingProject, company_id, billing_id, "Billing/proyecto")
    for key, value in _payload_dict(payload).items():
        setattr(project, key, value)
    project.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(project)
    return project


async def list_technicians(db: AsyncSession, company_id: UUID):
    result = await db.execute(
        select(FieldTechnician)
        .where(FieldTechnician.company_id == company_id)
        .order_by(FieldTechnician.created_at.desc())
    )
    return result.scalars().all()


async def get_technician_or_404(db: AsyncSession, company_id: UUID, technician_id: UUID):
    return await _get_or_404(db, FieldTechnician, company_id, technician_id, "Técnico")


async def create_technician(db: AsyncSession, company_id: UUID, payload):
    data = _payload_dict(payload)
    if data.get("default_billing_project_id"):
        await _get_or_404(db, FieldBillingProject, company_id, data["default_billing_project_id"], "Billing/proyecto")
    technician = FieldTechnician(company_id=company_id, **data)
    db.add(technician)
    await db.commit()
    await db.refresh(technician)
    return technician


async def update_technician(db: AsyncSession, company_id: UUID, technician_id: UUID, payload):
    technician = await get_technician_or_404(db, company_id, technician_id)
    data = _payload_dict(payload)
    if data.get("default_billing_project_id"):
        await _get_or_404(db, FieldBillingProject, company_id, data["default_billing_project_id"], "Billing/proyecto")
    for key, value in data.items():
        setattr(technician, key, value)
    technician.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(technician)
    return technician


async def list_materials(db: AsyncSession, company_id: UUID):
    result = await db.execute(
        select(FieldMaterial)
        .where(FieldMaterial.company_id == company_id)
        .order_by(FieldMaterial.created_at.desc())
    )
    return result.scalars().all()


async def get_material_or_404(db: AsyncSession, company_id: UUID, material_id: UUID):
    return await _get_or_404(db, FieldMaterial, company_id, material_id, "Material")


async def create_material(db: AsyncSession, company_id: UUID, payload):
    material = FieldMaterial(company_id=company_id, **_payload_dict(payload))
    db.add(material)
    await db.commit()
    await db.refresh(material)
    return material


async def update_material(db: AsyncSession, company_id: UUID, material_id: UUID, payload):
    material = await get_material_or_404(db, company_id, material_id)
    for key, value in _payload_dict(payload).items():
        setattr(material, key, value)
    material.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(material)
    return material


async def get_or_create_technician_material_stock(db: AsyncSession, company_id: UUID, technician_id: UUID, material_id: UUID):
    result = await db.execute(
        select(FieldTechnicianMaterialStock).where(
            FieldTechnicianMaterialStock.company_id == company_id,
            FieldTechnicianMaterialStock.technician_id == technician_id,
            FieldTechnicianMaterialStock.material_id == material_id,
        )
    )
    stock = result.scalar_one_or_none()
    if stock:
        return stock
    stock = FieldTechnicianMaterialStock(
        company_id=company_id,
        technician_id=technician_id,
        material_id=material_id,
        quantity=Decimal("0"),
    )
    db.add(stock)
    await db.flush()
    return stock


def assert_no_negative_stock(value: Decimal, label: str):
    if _to_decimal(value) < 0:
        raise HTTPException(status_code=400, detail=f"Stock insuficiente: {label}.")


async def create_material_request(db: AsyncSession, company_id: UUID, payload):
    data = _payload_dict(payload)
    items_data = data.pop("items", [])
    technician = await get_technician_or_404(db, company_id, data["requested_by_technician_id"])
    if not technician.is_supervisor:
        raise HTTPException(status_code=403, detail="Solo supervisores pueden solicitar material.")
    if data.get("billing_project_id"):
        await _get_or_404(db, FieldBillingProject, company_id, data["billing_project_id"], "Billing/proyecto")

    request = FieldMaterialRequest(company_id=company_id, **data)
    db.add(request)
    await db.flush()

    for item_data in items_data:
        if hasattr(item_data, "model_dump"):
            item_data = item_data.model_dump()
        await get_material_or_404(db, company_id, item_data["material_id"])
        item = FieldMaterialRequestItem(company_id=company_id, request_id=request.id, **item_data)
        db.add(item)
        db.add(FieldMaterialMovement(
            company_id=company_id,
            material_id=item.material_id,
            technician_id=technician.id,
            billing_project_id=request.billing_project_id,
            request_id=request.id,
            movement_type="request",
            quantity=item.quantity_requested,
            unit_cost=Decimal("0"),
            notes=request.notes,
        ))

    await db.commit()
    result = await db.execute(
        select(FieldMaterialRequest)
        .where(FieldMaterialRequest.id == request.id)
        .options(selectinload(FieldMaterialRequest.items))
    )
    return result.scalar_one()


async def list_material_requests(db: AsyncSession, company_id: UUID):
    result = await db.execute(
        select(FieldMaterialRequest)
        .where(FieldMaterialRequest.company_id == company_id)
        .options(selectinload(FieldMaterialRequest.items))
        .order_by(FieldMaterialRequest.created_at.desc())
    )
    return result.scalars().all()


async def _get_request_or_404(db: AsyncSession, company_id: UUID, request_id: UUID):
    result = await db.execute(
        select(FieldMaterialRequest)
        .where(FieldMaterialRequest.company_id == company_id, FieldMaterialRequest.id == request_id)
        .options(selectinload(FieldMaterialRequest.items))
    )
    request = result.scalar_one_or_none()
    if not request:
        raise HTTPException(status_code=404, detail="Solicitud de material no existe.")
    return request


async def approve_material_request(db: AsyncSession, company_id: UUID, request_id: UUID):
    request = await _get_request_or_404(db, company_id, request_id)
    if request.status not in {"pending", "approved"}:
        raise HTTPException(status_code=400, detail="La solicitud no se puede aprobar en su estado actual.")
    request.status = "approved"
    request.approved_at = datetime.now(timezone.utc)
    request.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(request)
    return request


async def deliver_material_request(db: AsyncSession, company_id: UUID, request_id: UUID):
    request = await _get_request_or_404(db, company_id, request_id)
    if request.status not in {"pending", "approved"}:
        raise HTTPException(status_code=400, detail="La solicitud no se puede entregar en su estado actual.")
    for item in request.items:
        remaining = _to_decimal(item.quantity_requested) - _to_decimal(item.quantity_delivered)
        if remaining <= 0:
            continue
        await _issue_material_no_commit(db, company_id, {
            "technician_id": request.requested_by_technician_id,
            "material_id": item.material_id,
            "billing_project_id": request.billing_project_id,
            "request_id": request.id,
            "quantity": remaining,
            "notes": f"Entrega solicitud {request.id}",
        })
        item.quantity_delivered = _to_decimal(item.quantity_delivered) + remaining

    request.status = "delivered"
    request.delivered_at = datetime.now(timezone.utc)
    request.updated_at = datetime.now(timezone.utc)
    await db.commit()
    result = await db.execute(
        select(FieldMaterialRequest)
        .where(FieldMaterialRequest.id == request.id)
        .options(selectinload(FieldMaterialRequest.items))
    )
    return result.scalar_one()


async def _issue_material_no_commit(db: AsyncSession, company_id: UUID, payload):
    data = _payload_dict(payload)
    technician = await get_technician_or_404(db, company_id, data["technician_id"])
    material = await get_material_or_404(db, company_id, data["material_id"])
    if data.get("billing_project_id"):
        await _get_or_404(db, FieldBillingProject, company_id, data["billing_project_id"], "Billing/proyecto")

    quantity = _to_decimal(data["quantity"])
    assert_no_negative_stock(_to_decimal(material.stock_available) - quantity, material.name)

    stock = await get_or_create_technician_material_stock(db, company_id, technician.id, material.id)
    material.stock_available = _to_decimal(material.stock_available) - quantity
    material.stock_in_field = _to_decimal(material.stock_in_field) + quantity
    material.updated_at = datetime.now(timezone.utc)
    stock.quantity = _to_decimal(stock.quantity) + quantity
    stock.updated_at = datetime.now(timezone.utc)

    movement = FieldMaterialMovement(
        company_id=company_id,
        material_id=material.id,
        technician_id=technician.id,
        billing_project_id=data.get("billing_project_id"),
        request_id=data.get("request_id"),
        movement_type="issued",
        quantity=quantity,
        unit_cost=material.unit_cost or Decimal("0"),
        notes=data.get("notes"),
    )
    db.add(movement)
    await db.flush()
    return movement


async def issue_material(db: AsyncSession, company_id: UUID, payload):
    movement = await _issue_material_no_commit(db, company_id, payload)
    await db.commit()
    await db.refresh(movement)
    return movement


async def use_material(db: AsyncSession, company_id: UUID, payload):
    data = _payload_dict(payload)
    technician = await get_technician_or_404(db, company_id, data["technician_id"])
    material = await get_material_or_404(db, company_id, data["material_id"])
    if data.get("billing_project_id"):
        await _get_or_404(db, FieldBillingProject, company_id, data["billing_project_id"], "Billing/proyecto")
    quantity = _to_decimal(data["quantity"])
    stock = await get_or_create_technician_material_stock(db, company_id, technician.id, material.id)
    assert_no_negative_stock(_to_decimal(stock.quantity) - quantity, f"{technician.full_name} / {material.name}")
    assert_no_negative_stock(_to_decimal(material.stock_in_field) - quantity, f"global campo / {material.name}")
    stock.quantity = _to_decimal(stock.quantity) - quantity
    stock.updated_at = datetime.now(timezone.utc)
    material.stock_in_field = _to_decimal(material.stock_in_field) - quantity
    material.updated_at = datetime.now(timezone.utc)
    movement = FieldMaterialMovement(company_id=company_id, material_id=material.id, technician_id=technician.id, billing_project_id=data.get("billing_project_id"), movement_type="used", quantity=quantity, unit_cost=material.unit_cost or Decimal("0"), notes=data.get("notes"))
    db.add(movement)
    await db.commit()
    await db.refresh(movement)
    return movement


async def return_material(db: AsyncSession, company_id: UUID, payload):
    data = _payload_dict(payload)
    condition = data.get("condition") or "good"
    if condition not in {"good", "damaged"}:
        raise HTTPException(status_code=400, detail="condition debe ser good o damaged.")
    technician = await get_technician_or_404(db, company_id, data["technician_id"])
    material = await get_material_or_404(db, company_id, data["material_id"])
    if data.get("billing_project_id"):
        await _get_or_404(db, FieldBillingProject, company_id, data["billing_project_id"], "Billing/proyecto")
    quantity = _to_decimal(data["quantity"])
    stock = await get_or_create_technician_material_stock(db, company_id, technician.id, material.id)
    assert_no_negative_stock(_to_decimal(stock.quantity) - quantity, f"{technician.full_name} / {material.name}")
    assert_no_negative_stock(_to_decimal(material.stock_in_field) - quantity, f"global campo / {material.name}")
    stock.quantity = _to_decimal(stock.quantity) - quantity
    stock.updated_at = datetime.now(timezone.utc)
    material.stock_in_field = _to_decimal(material.stock_in_field) - quantity
    if condition == "good":
        material.stock_available = _to_decimal(material.stock_available) + quantity
        movement_type = "returned"
    else:
        material.stock_damaged = _to_decimal(material.stock_damaged) + quantity
        movement_type = "damaged"
    material.updated_at = datetime.now(timezone.utc)
    movement = FieldMaterialMovement(company_id=company_id, material_id=material.id, technician_id=technician.id, billing_project_id=data.get("billing_project_id"), movement_type=movement_type, quantity=quantity, unit_cost=material.unit_cost or Decimal("0"), condition=condition, notes=data.get("notes"))
    db.add(movement)
    await db.commit()
    await db.refresh(movement)
    return movement


async def lost_material(db: AsyncSession, company_id: UUID, payload):
    data = _payload_dict(payload)
    technician = await get_technician_or_404(db, company_id, data["technician_id"])
    material = await get_material_or_404(db, company_id, data["material_id"])
    if data.get("billing_project_id"):
        await _get_or_404(db, FieldBillingProject, company_id, data["billing_project_id"], "Billing/proyecto")
    quantity = _to_decimal(data["quantity"])
    stock = await get_or_create_technician_material_stock(db, company_id, technician.id, material.id)
    assert_no_negative_stock(_to_decimal(stock.quantity) - quantity, f"{technician.full_name} / {material.name}")
    assert_no_negative_stock(_to_decimal(material.stock_in_field) - quantity, f"global campo / {material.name}")
    stock.quantity = _to_decimal(stock.quantity) - quantity
    stock.updated_at = datetime.now(timezone.utc)
    material.stock_in_field = _to_decimal(material.stock_in_field) - quantity
    material.updated_at = datetime.now(timezone.utc)
    movement = FieldMaterialMovement(company_id=company_id, material_id=material.id, technician_id=technician.id, billing_project_id=data.get("billing_project_id"), movement_type="lost", quantity=quantity, unit_cost=material.unit_cost or Decimal("0"), notes=data.get("notes"))
    db.add(movement)
    await db.commit()
    await db.refresh(movement)
    return movement


async def list_material_movements(db: AsyncSession, company_id: UUID, limit: int = 200):
    result = await db.execute(
        select(FieldMaterialMovement)
        .where(FieldMaterialMovement.company_id == company_id)
        .order_by(FieldMaterialMovement.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


async def get_field_dashboard_summary(db: AsyncSession, company_id: UUID):
    async def scalar(stmt, default=0):
        value = (await db.execute(stmt)).scalar()
        return value if value is not None else default

    technicians_total = await scalar(select(func.count()).select_from(FieldTechnician).where(FieldTechnician.company_id == company_id))
    technicians_active = await scalar(select(func.count()).select_from(FieldTechnician).where(FieldTechnician.company_id == company_id, FieldTechnician.status == "active"))
    supervisors_total = await scalar(select(func.count()).select_from(FieldTechnician).where(FieldTechnician.company_id == company_id, FieldTechnician.is_supervisor.is_(True)))
    materials_total = await scalar(select(func.count()).select_from(FieldMaterial).where(FieldMaterial.company_id == company_id))
    stock_low_count = await scalar(select(func.count()).select_from(FieldMaterial).where(FieldMaterial.company_id == company_id, FieldMaterial.stock_available <= FieldMaterial.stock_min))
    stock_available_total = await scalar(select(func.coalesce(func.sum(FieldMaterial.stock_available), 0)).where(FieldMaterial.company_id == company_id), Decimal("0"))
    stock_in_field_total = await scalar(select(func.coalesce(func.sum(FieldMaterial.stock_in_field), 0)).where(FieldMaterial.company_id == company_id), Decimal("0"))
    stock_damaged_total = await scalar(select(func.coalesce(func.sum(FieldMaterial.stock_damaged), 0)).where(FieldMaterial.company_id == company_id), Decimal("0"))
    material_requests_pending = await scalar(select(func.count()).select_from(FieldMaterialRequest).where(FieldMaterialRequest.company_id == company_id, FieldMaterialRequest.status == "pending"))
    billing_projects_active = await scalar(select(func.count()).select_from(FieldBillingProject).where(FieldBillingProject.company_id == company_id, FieldBillingProject.status == "active"))
    inventory_movements_total = await scalar(select(func.count()).select_from(FieldMaterialMovement).where(FieldMaterialMovement.company_id == company_id))

    return {
        "technicians_total": int(technicians_total),
        "technicians_active": int(technicians_active),
        "supervisors_total": int(supervisors_total),
        "materials_total": int(materials_total),
        "stock_low_count": int(stock_low_count),
        "stock_available_total": _to_decimal(stock_available_total),
        "stock_in_field_total": _to_decimal(stock_in_field_total),
        "stock_damaged_total": _to_decimal(stock_damaged_total),
        "material_requests_pending": int(material_requests_pending),
        "billing_projects_active": int(billing_projects_active),
        "inventory_movements_total": int(inventory_movements_total),
    }
