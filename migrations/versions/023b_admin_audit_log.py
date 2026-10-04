"""auditoria de la consola maestra (admin_audit_log)

Revision ID: 023b_admin_audit_log
Revises: 023a_company_kind
Create Date: 2026-10-04

Una fila por escritura (POST/PUT/PATCH/DELETE) hecha con sesion de Admin V2:
quien, IP, metodo, ruta, empresa, codigo de respuesta y consola. Sin cuerpos
de peticion ni claves; detail es un JSON corto solo para las acciones nuevas
(cambiar tipo, clonar, eliminar definitivo). Filas pequeñas y retencion de
180 dias. company_id sin llave foranea: el registro sobrevive a la empresa.
"""
from __future__ import annotations

from alembic import op

revision = "023b_admin_audit_log"
down_revision = "023a_company_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_audit_log (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            at timestamptz NOT NULL DEFAULT now(),
            actor varchar(200) NOT NULL DEFAULT '',
            ip varchar(120) NOT NULL DEFAULT '',
            method varchar(10) NOT NULL,
            path varchar(500) NOT NULL,
            company_id uuid NULL,
            status_code integer NOT NULL,
            surface varchar(20) NOT NULL DEFAULT '',
            detail jsonb NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_admin_audit_log_at ON admin_audit_log (at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_admin_audit_log_company_at ON admin_audit_log (company_id, at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS admin_audit_log")
