"""acceso maestro con huella (llaves de acceso WebAuthn) para la Consola v2+

Revision ID: 022p_admin_passkeys
Revises: 022o_delivery_print
Create Date: 2026-10-01

Una fila por equipo registrado (Windows Hello, Touch ID, huella del celular):
solo el identificador de la llave y su llave PUBLICA. La huella nunca sale del
equipo. Es del acceso maestro (no de una empresa), por eso no lleva company_id.
Filas pequeñas.
"""
from __future__ import annotations

from alembic import op

revision = "022p_admin_passkeys"
down_revision = "022o_delivery_print"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_v2_passkeys (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            credential_id varchar(512) NOT NULL UNIQUE,
            public_key bytea NOT NULL,
            sign_count bigint NOT NULL DEFAULT 0,
            label varchar(120) NOT NULL DEFAULT '',
            transports jsonb NOT NULL DEFAULT '[]'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            last_used_at timestamptz NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS admin_v2_passkeys")
