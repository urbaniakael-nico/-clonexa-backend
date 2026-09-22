"""waiter ordering time machine

Revision ID: 021c_waiter_ordering_ttm
Revises: 021b_hsp_board_ttm
Create Date: 2026-09-22

Creates the "waiter_ordering" module (Fase 1: mesero -> cocina -> caja) and
enables it only for ASADERO EL SOCIO (7625872c-f941-4479-a27b-f8443be953c5).
Every other company gets no company_modules row for it, so
require_enabled_module(..., "waiter_ordering") 403s them automatically and
the new mesero/cocina/caja mini panels, endpoints and Admin V2 UI stay
invisible everywhere else.
"""
from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = "021c_waiter_ordering_ttm"
down_revision = "021b_hsp_board_ttm"
branch_labels = None
depends_on = None

TARGET_COMPANY_ID = "7625872c-f941-4479-a27b-f8443be953c5"
MODULE_CODE = "waiter_ordering"

DEFAULT_SETTINGS = {
    "stations": ["parrilla", "freidora", "bebidas", "otros"],
    "kitchen_user_limit": 2,
    "cashier_user_limit": 1,
    "timer_thresholds": {"green_max_minutes": 10, "yellow_max_minutes": 20},
}

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

_DISABLE_COMPANY_MODULE = sa.text(
    "UPDATE company_modules SET enabled = FALSE, updated_at = NOW() WHERE company_id = :company_id AND module_id = :module_id"
)

_DELETE_MODULE_IF_UNUSED = sa.text(
    """
    DELETE FROM modules
    WHERE code = :code
      AND NOT EXISTS (SELECT 1 FROM company_modules WHERE module_id = modules.id)
    """
)


def upgrade() -> None:
    bind = op.get_bind()

    module_row = bind.execute(_SELECT_MODULE, {"code": MODULE_CODE}).mappings().first()
    if module_row:
        module_id = module_row["id"]
    else:
        module_id = str(uuid.uuid4())
        bind.execute(
            _INSERT_MODULE,
            {
                "id": module_id,
                "code": MODULE_CODE,
                "name": "Pedidos por mesero",
                "description": "Mesero -> cocina -> caja para hospitality (Fase 1).",
                "category": "hospitality",
            },
        )

    existing = bind.execute(
        _SELECT_COMPANY_MODULE,
        {"company_id": TARGET_COMPANY_ID, "module_id": module_id},
    ).mappings().first()
    if existing:
        return

    bind.execute(
        _INSERT_COMPANY_MODULE,
        {
            "id": str(uuid.uuid4()),
            "company_id": TARGET_COMPANY_ID,
            "module_id": module_id,
            "settings": json.dumps(DEFAULT_SETTINGS, ensure_ascii=False),
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    module_row = bind.execute(_SELECT_MODULE, {"code": MODULE_CODE}).mappings().first()
    if not module_row:
        return
    module_id = module_row["id"]
    bind.execute(_DISABLE_COMPANY_MODULE, {"company_id": TARGET_COMPANY_ID, "module_id": module_id})
    bind.execute(_DELETE_MODULE_IF_UNUSED, {"code": MODULE_CODE})
