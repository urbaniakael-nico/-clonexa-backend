"""links cortos /c/CODIGO para mini paneles y domicilios (049Y)

Revision ID: 022m_short_links
Revises: 022l_cash_close_incidents
Create Date: 2026-09-30

Tabla short_links (codigo corto -> ruta interna /mini-panel de la empresa) y
el interruptor short_links del modulo waiter_ordering, encendido solo para
ASADERO EL SOCIO (la empresa que lo pidio). Ausente (= apagado) para las
demas: sus links siguen siendo los largos. Los links largos siguen
funcionando para todas. Filas pequeñas de texto.
"""
from __future__ import annotations

from alembic import op

revision = "022m_short_links"
down_revision = "022l_cash_close_incidents"
branch_labels = None
depends_on = None

TARGET_COMPANY_ID = "7625872c-f941-4479-a27b-f8443be953c5"
SETTINGS_PATCH = '{"short_links": true}'


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS short_links (
            code varchar(16) PRIMARY KEY,
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            kind varchar(20) NOT NULL DEFAULT 'mini_panel',
            target varchar(500) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_short_links_target UNIQUE (company_id, target)
        )
        """
    )
    op.execute(
        f"""
        UPDATE company_modules cm
        SET settings = COALESCE(cm.settings, '{{}}'::jsonb) || '{SETTINGS_PATCH}'::jsonb,
            updated_at = NOW()
        FROM modules m
        WHERE cm.module_id = m.id
          AND m.code = 'waiter_ordering'
          AND cm.company_id = '{TARGET_COMPANY_ID}'::uuid
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE company_modules cm
        SET settings = COALESCE(cm.settings, '{{}}'::jsonb) - 'short_links',
            updated_at = NOW()
        FROM modules m
        WHERE cm.module_id = m.id
          AND m.code = 'waiter_ordering'
          AND cm.company_id = '{TARGET_COMPANY_ID}'::uuid
        """
    )
    op.execute("DROP TABLE IF EXISTS short_links")
