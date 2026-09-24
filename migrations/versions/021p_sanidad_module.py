"""sanidad module: daily sanitation checklist

Revision ID: 021p_sanidad_module
Revises: 021o_hsp_business_day_ttm
Create Date: 2026-09-24

Creates the general "sanidad" module (catalog row in `modules`, so Admin V2
lists it and can switch it on for any company with one click) and enables it
only for ASADERO EL SOCIO. Every other company gets no company_modules row,
so the module is off for them.

Tables (small rows, text/JSON only -- no files or images):
- sanitation_items: each company's own checklist (sections, order, active,
  optional numeric field such as a fridge temperature).
- sanitation_sheets: one sheet per company and day; once closed it is
  immutable (snapshot of the items, responsible, compliance, who closed).
- sanitation_sheet_notes: later notes on a closed sheet (who and when).
"""
from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = "021p_sanidad_module"
down_revision = "021o_hsp_business_day_ttm"
branch_labels = None
depends_on = None

TARGET_COMPANY_ID = "7625872c-f941-4479-a27b-f8443be953c5"
MODULE_CODE = "sanidad"
DEFAULT_SETTINGS = {"alert_hour": "22:00"}

_SELECT_MODULE = sa.text("SELECT id FROM modules WHERE code = :code LIMIT 1")
_INSERT_MODULE = sa.text(
    """
    INSERT INTO modules (id, code, name, description, category, is_active, created_at, updated_at)
    VALUES (CAST(:id AS uuid), :code, :name, :description, :category, TRUE, NOW(), NOW())
    """
)
_SELECT_COMPANY_MODULE = sa.text(
    "SELECT id FROM company_modules WHERE company_id = :company_id AND module_id = :module_id LIMIT 1"
)
_INSERT_COMPANY_MODULE = sa.text(
    """
    INSERT INTO company_modules (id, company_id, module_id, enabled, settings, activated_at, created_at, updated_at)
    VALUES (CAST(:id AS uuid), CAST(:company_id AS uuid), :module_id, TRUE, CAST(:settings AS jsonb), NOW(), NOW(), NOW())
    """
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sanitation_items (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            section varchar(80) NOT NULL,
            label varchar(240) NOT NULL,
            requires_value boolean NOT NULL DEFAULT false,
            value_label varchar(40) NOT NULL DEFAULT '',
            position integer NOT NULL DEFAULT 0,
            active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_sanitation_items_company ON sanitation_items (company_id, position)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sanitation_sheets (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            sheet_date date NOT NULL,
            status varchar(20) NOT NULL DEFAULT 'open',
            responsible_employee_id varchar(64) NOT NULL DEFAULT '',
            responsible_name varchar(160) NOT NULL DEFAULT '',
            entries jsonb NOT NULL DEFAULT '[]'::jsonb,
            compliance numeric(5,2) NOT NULL DEFAULT 0,
            closed_at timestamptz NULL,
            closed_by varchar(160) NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_sanitation_sheet_day UNIQUE (company_id, sheet_date)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sanitation_sheet_notes (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            sheet_id uuid NOT NULL REFERENCES sanitation_sheets(id) ON DELETE CASCADE,
            note varchar(1000) NOT NULL,
            author_name varchar(160) NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    bind = op.get_bind()
    module_row = bind.execute(_SELECT_MODULE, {"code": MODULE_CODE}).mappings().first()
    if module_row:
        module_id = module_row["id"]
    else:
        module_id = str(uuid.uuid4())
        bind.execute(_INSERT_MODULE, {
            "id": module_id,
            "code": MODULE_CODE,
            "name": "Sanidad",
            "description": "Planilla diaria de limpieza y logistica para inspecciones de Sanidad.",
            "category": "operations",
        })
    if not bind.execute(_SELECT_COMPANY_MODULE, {"company_id": TARGET_COMPANY_ID, "module_id": module_id}).mappings().first():
        bind.execute(_INSERT_COMPANY_MODULE, {
            "id": str(uuid.uuid4()),
            "company_id": TARGET_COMPANY_ID,
            "module_id": module_id,
            "settings": json.dumps(DEFAULT_SETTINGS),
        })


def downgrade() -> None:
    bind = op.get_bind()
    module_row = bind.execute(_SELECT_MODULE, {"code": MODULE_CODE}).mappings().first()
    if module_row:
        bind.execute(
            sa.text("DELETE FROM company_modules WHERE module_id = :module_id"),
            {"module_id": module_row["id"]},
        )
        bind.execute(sa.text("DELETE FROM modules WHERE id = :module_id"), {"module_id": module_row["id"]})
    op.execute("DROP TABLE IF EXISTS sanitation_sheet_notes")
    op.execute("DROP TABLE IF EXISTS sanitation_sheets")
    op.execute("DROP TABLE IF EXISTS sanitation_items")
