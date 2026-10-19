"""Cotizaciones v2 (interruptor quotes_v2): cierres cobrados y firmas en el bucket

Revision ID: 024q_quotes_v2
Revises: 024p_crm_lab
Create Date: 2026-10-19

Aditiva (tablas nuevas; no toca mini_panel_quotes ni los cierres):
- quote_closure_charges: que cierre de produccion (reference_production_closures)
  quedo cobrado en que cuenta de cobro. Un cierre solo puede estar en UNA cuenta
  vigente (indice unico parcial); al archivar la cuenta se libera (released_at),
  la fila queda como historial.
- quote_signatures: firmas NUEVAS. La imagen vive en el bucket (zona privada);
  aqui solo la clave, nunca base64 en Postgres.
"""
from __future__ import annotations

from alembic import op

revision = "024q_quotes_v2"
down_revision = "024p_crm_lab"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS quote_closure_charges (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            quote_id uuid NOT NULL,
            closure_id text NOT NULL,
            quantity integer NOT NULL DEFAULT 0,
            created_by varchar(200) NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now(),
            released_at timestamptz NULL,
            released_reason varchar(40) NULL
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_quote_closure_charges_live
        ON quote_closure_charges (company_id, closure_id) WHERE released_at IS NULL
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_quote_closure_charges_quote ON quote_closure_charges (company_id, quote_id)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS quote_signatures (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            storage_key text NOT NULL,
            content_type varchar(40) NOT NULL DEFAULT 'image/png',
            size_bytes integer NOT NULL DEFAULT 0,
            created_by varchar(200) NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_quote_signatures_company ON quote_signatures (company_id, created_at DESC)")


def downgrade() -> None:
    # Solo aditivo: bajar no borra cobros ni firmas.
    pass
