"""tipo de empresa (demo | registrada) en companies.settings_json.kind

Revision ID: 023a_company_kind
Revises: 022p_admin_passkeys
Create Date: 2026-10-04

Migracion SOLO DE DATOS (sin cambiar el esquema) para la Consola v2+:
- "registrada" para las tres empresas vivas (_CLONEXA_LIVE_COMPANY_IDS en
  app/main.py: ASADERO EL SOCIO, The Time Machine, Velvet).
- "demo" para todas las demas.
Idempotente: solo llena las empresas que aun no tienen un kind valido; nunca
pisa uno que ya se haya puesto a mano desde la consola.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "023a_company_kind"
down_revision = "022p_admin_passkeys"
branch_labels = None
depends_on = None

LIVE_COMPANY_IDS = (
    "7625872c-f941-4479-a27b-f8443be953c5",  # ASADERO EL SOCIO
    "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4",  # The Time Machine
    "d63cf68c-be5b-4a30-aee4-341973018db1",  # Velvet
)

SET_KIND = """
    UPDATE companies
    SET settings_json = jsonb_set(COALESCE(settings_json, '{}'::jsonb), '{kind}', to_jsonb(CAST(:kind AS text)), true)
    WHERE COALESCE(settings_json->>'kind', '') NOT IN ('demo', 'registrada')
      AND (id::text = ANY(CAST(:live AS text[]))) = :is_live
"""


def upgrade() -> None:
    bind = op.get_bind()
    live = list(LIVE_COMPANY_IDS)
    bind.execute(sa.text(SET_KIND), {"kind": "registrada", "live": live, "is_live": True})
    bind.execute(sa.text(SET_KIND), {"kind": "demo", "live": live, "is_live": False})


def downgrade() -> None:
    op.execute("UPDATE companies SET settings_json = settings_json - 'kind' WHERE settings_json ? 'kind'")
