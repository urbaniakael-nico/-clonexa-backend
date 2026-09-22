"""hsp orders board time machine

Revision ID: 021b_hsp_orders_board_time_machine
Revises: 021a_mini_panel_quotes_module
Create Date: 2026-09-22

Turns on the per-table orders board ("mesas") for a single company
(The Time Machine) without touching any other tenant's qr_config.
Every other company keeps orders_board unset, which the panel reads
as the default kanban board.
"""
from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "021b_hsp_orders_board_time_machine"
down_revision = "021a_mini_panel_quotes_module"
branch_labels = None
depends_on = None

TARGET_COMPANY_ID = "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4"

_SELECT_QR_MODULE = sa.text(
    """
    SELECT cm.id, cm.settings
    FROM company_modules cm
    JOIN modules m ON m.id = cm.module_id
    WHERE cm.company_id = :company_id
      AND m.code IN ('qr', 'mesa_qr', 'mesas_qr', 'qr_mesas', 'hospitality_qr', 'voting_qr')
    ORDER BY cm.enabled DESC, cm.updated_at DESC
    LIMIT 1
    """
)

_UPDATE_SETTINGS = sa.text(
    "UPDATE company_modules SET settings = CAST(:settings AS JSONB), updated_at = NOW() WHERE id = :id"
)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _set_orders_board(value: str | None) -> None:
    bind = op.get_bind()
    row = bind.execute(_SELECT_QR_MODULE, {"company_id": TARGET_COMPANY_ID}).mappings().first()
    if not row:
        return
    settings = _as_dict(row["settings"])
    qr_config = dict(_as_dict(settings.get("qr_config")))
    if value is None:
        qr_config.pop("orders_board", None)
    else:
        qr_config["orders_board"] = value
    settings = {**settings, "qr_config": qr_config}
    bind.execute(_UPDATE_SETTINGS, {"settings": json.dumps(settings, ensure_ascii=False), "id": row["id"]})


def upgrade() -> None:
    _set_orders_board("mesas")


def downgrade() -> None:
    _set_orders_board(None)
