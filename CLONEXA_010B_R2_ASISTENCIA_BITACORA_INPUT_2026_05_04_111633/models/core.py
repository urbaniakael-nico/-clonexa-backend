import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(180), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="America/Bogota")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    plan: Mapped[str] = mapped_column(String(50), nullable=False, default="starter")
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    employees = relationship("Employee", back_populates="company")


class Employee(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "employees"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    full_name: Mapped[str] = mapped_column(String(180), nullable=False)
    document_id: Mapped[str | None] = mapped_column(String(80))
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(180))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    employee_type: Mapped[str] = mapped_column(String(50), nullable=False, default="operator")
    role: Mapped[str] = mapped_column(String(80), nullable=False, default="operator")
    telegram_user_id: Mapped[str | None] = mapped_column(String(120))
    telegram_username: Mapped[str | None] = mapped_column(String(120))
    hire_date: Mapped[str | None] = mapped_column(String(20))
    hourly_rate_regular: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    hourly_rate_extra: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    deduction_1: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    deduction_2: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text)

    company = relationship("Company", back_populates="employees")

    __table_args__ = (
        Index("ix_employees_company_status", "company_id", "status"),
        UniqueConstraint("company_id", "document_id", name="uq_employees_company_document_id"),
        UniqueConstraint("company_id", "phone", name="uq_employees_company_phone"),
    )


class Role(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "roles"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    permissions_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_roles_company_code"),
    )


class EmployeeRole(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "employee_roles"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "employee_id", "role_id", name="uq_employee_roles_company_employee_role"),
    )


class BotUser(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bot_users"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    external_user_id: Mapped[str] = mapped_column(String(120), nullable=False)
    chat_id: Mapped[str | None] = mapped_column(String(120))
    username: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("company_id", "channel", "external_user_id", name="uq_bot_users_company_channel_external"),
        Index("ix_bot_users_company_employee", "company_id", "employee_id"),
    )


class WorkEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "work_events"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    employee_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"))
    event_id: Mapped[str] = mapped_column(String(160), nullable=False)
    module: Mapped[str] = mapped_column(String(50), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_channel: Mapped[str] = mapped_column(String(50), nullable=False, default="api")
    source_ref: Mapped[str | None] = mapped_column(String(180))
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="received")
    error_message: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("company_id", "event_id", name="uq_work_events_company_event_id"),
        Index("ix_work_events_company_type_time", "company_id", "event_type", "occurred_at"),
        Index("ix_work_events_company_employee_time", "company_id", "employee_id", "occurred_at"),
        Index("ix_work_events_company_module_time", "company_id", "module", "occurred_at"),
        Index("ix_work_events_company_status", "company_id", "status"),
    )


class WorkSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "work_sessions"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)
    start_event_db_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("work_events.id"))
    end_event_db_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("work_events.id"))
    module: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    work_type: Mapped[str | None] = mapped_column(String(80))
    reference_type: Mapped[str | None] = mapped_column(String(80))
    reference_id: Mapped[str | None] = mapped_column(String(120))
    location_id: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_work_sessions_company_employee_started", "company_id", "employee_id", "started_at"),
        Index("ix_work_sessions_company_module_status", "company_id", "module", "status"),
        Index("ix_work_sessions_company_status", "company_id", "status"),
        Index("ix_work_sessions_company_started", "company_id", "started_at"),
        Index("ix_work_sessions_company_ended", "company_id", "ended_at"),
        Index(
            "uq_work_sessions_one_active_per_employee",
            "company_id",
            "employee_id",
            unique=True,
            postgresql_where=(status == "active"),
        ),
    )


class EmployeeCurrentStatus(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "employee_current_status"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)
    active_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("work_sessions.id"))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="idle")
    module: Mapped[str | None] = mapped_column(String(50))
    active_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_id: Mapped[str | None] = mapped_column(String(160))
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("company_id", "employee_id", name="uq_employee_current_status_company_employee"),
        Index("ix_employee_current_status_company_status", "company_id", "status"),
        Index("ix_employee_current_status_company_module_status", "company_id", "module", "status"),
    )


class InventoryItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "inventory_items"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    sku: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    category: Mapped[str | None] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(40), nullable=False, default="unit")
    cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    min_stock: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")

    __table_args__ = (
        UniqueConstraint("company_id", "sku", name="uq_inventory_items_company_sku"),
        Index("ix_inventory_items_company_category", "company_id", "category"),
        Index("ix_inventory_items_company_status", "company_id", "status"),
    )


class InventoryLocation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "inventory_locations"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    module: Mapped[str | None] = mapped_column(String(50))
    reference_id: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")

    __table_args__ = (
        Index("ix_inventory_locations_company_type", "company_id", "type"),
        Index("ix_inventory_locations_company_module", "company_id", "module"),
    )


class InventoryMovement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "inventory_movements"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("inventory_items.id"), nullable=False)
    from_location_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("inventory_locations.id"))
    to_location_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("inventory_locations.id"))
    event_db_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("work_events.id"))
    movement_type: Mapped[str] = mapped_column(String(50), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    reason: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_inventory_movements_company_item_time", "company_id", "item_id", "occurred_at"),
        Index("ix_inventory_movements_company_type", "company_id", "movement_type"),
        Index("ix_inventory_movements_company_from", "company_id", "from_location_id"),
        Index("ix_inventory_movements_company_to", "company_id", "to_location_id"),
        Index("ix_inventory_movements_company_time", "company_id", "occurred_at"),
    )


class PayrollPeriod(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payroll_periods"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    period_type: Mapped[str] = mapped_column(String(40), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")

    __table_args__ = (
        UniqueConstraint("company_id", "starts_at", "ends_at", name="uq_payroll_periods_company_range"),
        Index("ix_payroll_periods_company_range", "company_id", "starts_at", "ends_at"),
    )


class PayrollEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payroll_entries"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("payroll_periods.id"), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)
    regular_minutes: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    overtime_minutes: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    deductions: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    adjustments: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")

    __table_args__ = (
        UniqueConstraint("company_id", "period_id", "employee_id", name="uq_payroll_entries_company_period_employee"),
        Index("ix_payroll_entries_company_employee", "company_id", "employee_id"),
        Index("ix_payroll_entries_company_status", "company_id", "status"),
    )
