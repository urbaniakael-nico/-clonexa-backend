"""hospitality business day: the time machine

Revision ID: 021o_hsp_business_day_ttm
Revises: 021n_qr_table_guests
Create Date: 2026-09-24

Turns ON the scheduled business day ("jornada por horario") for THE TIME
MACHINE only: 18:00 to 04:00 of the next day. Every sale belongs to the
jornada of the day it opened (a sale at 02:00 on the 24th belongs to the
23rd), instead of to whatever happened between two "Generar cierre".
Reports are computed from the orders at read time, so the history is
recalculated with no data changes.

Absent (= off, today's closure-based reports) for every other company.
companies.settings_json only; downgrade removes exactly this key.
"""
from __future__ import annotations

from alembic import op

revision = "021o_hsp_business_day_ttm"
down_revision = "021n_qr_table_guests"
branch_labels = None
depends_on = None

TARGET_COMPANY_ID = "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4"

SETTINGS_PATCH = '{"hospitality_business_day": {"open": "18:00", "close": "04:00"}}'


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE companies
        SET settings_json = COALESCE(settings_json, '{{}}'::jsonb) || '{SETTINGS_PATCH}'::jsonb
        WHERE id = '{TARGET_COMPANY_ID}'::uuid
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE companies
        SET settings_json = COALESCE(settings_json, '{{}}'::jsonb) - 'hospitality_business_day'
        WHERE id = '{TARGET_COMPANY_ID}'::uuid
        """
    )
