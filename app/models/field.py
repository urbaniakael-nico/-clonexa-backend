import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base
from app.models.core import Company


class FieldBillingProject(Base):
    __tablename__ = "field_billing_projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(80), nullable=False)
    name = Column(String(255), nullable=False)
    client_name = Column(String(255), nullable=True)
    location = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    budget_amount = Column(Numeric(12, 2), nullable=False, default=0)
    notes = Column(Text, nullable=True)
    settings_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    company = relationship(Company)


class FieldTechnician(Base):
    __tablename__ = "field_technicians"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    default_billing_project_id = Column(UUID(as_uuid=True), ForeignKey("field_billing_projects.id", ondelete="SET NULL"), nullable=True, index=True)
    full_name = Column(String(255), nullable=False)
    phone = Column(String(64), nullable=True)
    role = Column(String(96), nullable=False, default="technician")
    status = Column(String(32), nullable=False, default="active", index=True)
    is_supervisor = Column(Boolean, nullable=False, default=False, index=True)
    hourly_rate_regular = Column(Numeric(12, 2), nullable=False, default=0)
    hourly_rate_extra = Column(Numeric(12, 2), nullable=False, default=0)
    discount_1 = Column(Numeric(12, 2), nullable=False, default=0)
    discount_2 = Column(Numeric(12, 2), nullable=False, default=0)
    notes = Column(Text, nullable=True)
    settings_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    company = relationship(Company)
    default_billing_project = relationship(FieldBillingProject)


class FieldMaterial(Base):
    __tablename__ = "field_materials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    sku = Column(String(96), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    category = Column(String(120), nullable=True)
    unit = Column(String(40), nullable=False, default="unit")
    status = Column(String(32), nullable=False, default="active", index=True)
    stock_available = Column(Numeric(14, 2), nullable=False, default=0)
    stock_min = Column(Numeric(14, 2), nullable=False, default=0)
    stock_in_field = Column(Numeric(14, 2), nullable=False, default=0)
    stock_damaged = Column(Numeric(14, 2), nullable=False, default=0)
    unit_cost = Column(Numeric(12, 2), nullable=False, default=0)
    notes = Column(Text, nullable=True)
    settings_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    company = relationship(Company)


class FieldTechnicianMaterialStock(Base):
    __tablename__ = "field_technician_material_stock"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    technician_id = Column(UUID(as_uuid=True), ForeignKey("field_technicians.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id = Column(UUID(as_uuid=True), ForeignKey("field_materials.id", ondelete="CASCADE"), nullable=False, index=True)
    quantity = Column(Numeric(14, 2), nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    technician = relationship(FieldTechnician)
    material = relationship(FieldMaterial)


class FieldMaterialRequest(Base):
    __tablename__ = "field_material_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_by_technician_id = Column(UUID(as_uuid=True), ForeignKey("field_technicians.id"), nullable=False, index=True)
    billing_project_id = Column(UUID(as_uuid=True), ForeignKey("field_billing_projects.id"), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    notes = Column(Text, nullable=True)
    requested_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    approved_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    requested_by_technician = relationship(FieldTechnician)
    billing_project = relationship(FieldBillingProject)
    items = relationship("FieldMaterialRequestItem", cascade="all, delete-orphan", lazy="selectin")


class FieldMaterialRequestItem(Base):
    __tablename__ = "field_material_request_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(UUID(as_uuid=True), ForeignKey("field_material_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id = Column(UUID(as_uuid=True), ForeignKey("field_materials.id"), nullable=False, index=True)
    quantity_requested = Column(Numeric(14, 2), nullable=False)
    quantity_delivered = Column(Numeric(14, 2), nullable=False, default=0)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    material = relationship(FieldMaterial)


class FieldMaterialMovement(Base):
    __tablename__ = "field_material_movements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id = Column(UUID(as_uuid=True), ForeignKey("field_materials.id"), nullable=False, index=True)
    technician_id = Column(UUID(as_uuid=True), ForeignKey("field_technicians.id"), nullable=True, index=True)
    billing_project_id = Column(UUID(as_uuid=True), ForeignKey("field_billing_projects.id"), nullable=True, index=True)
    request_id = Column(UUID(as_uuid=True), ForeignKey("field_material_requests.id"), nullable=True)
    movement_type = Column(String(32), nullable=False, index=True)
    quantity = Column(Numeric(14, 2), nullable=False)
    unit_cost = Column(Numeric(12, 2), nullable=False, default=0)
    condition = Column(String(32), nullable=True)
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    material = relationship(FieldMaterial)
    technician = relationship(FieldTechnician)
    billing_project = relationship(FieldBillingProject)
