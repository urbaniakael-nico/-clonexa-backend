"""nomina: periodos por dias de corte, cargados solo para VELVET (049L)

Revision ID: 022a_payroll_cutoffs
Revises: 021z_carta_tree
Create Date: 2026-09-28

- payroll_period_config: dias de corte de la nomina por empresa, corte
  automatico (00:01 del dia siguiente al cierre) y desde cuando aplica.
  La fila es el interruptor: una empresa sin fila sigue exactamente igual
  (periodos y asignacion de turnos de siempre).
- VELVET: cortes 10 y 25 -> del 26 al 10 (cierra el 10) y del 11 al 25
  (cierra el 25), corte automatico a las 00:01 del 11 y del 26. Aplica a
  partir de hoy: los periodos que ya terminaron no se cierran solos.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "022a_payroll_cutoffs"
down_revision = "021z_carta_tree"
branch_labels = None
depends_on = None

TARGET_COMPANY_ID = "d63cf68c-be5b-4a30-aee4-341973018db1"  # VELVET
CUTOFF_DAYS = "[10, 25]"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS payroll_period_config (
            company_id uuid PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
            cutoff_days jsonb NOT NULL DEFAULT '[]'::jsonb,
            auto_close boolean NOT NULL DEFAULT true,
            active_from timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    bind = op.get_bind()
    c = {"c": TARGET_COMPANY_ID}
    if not bind.execute(sa.text("SELECT 1 FROM companies WHERE id = CAST(:c AS uuid)"), c).first():
        return
    bind.execute(sa.text("""
        INSERT INTO payroll_period_config (company_id, cutoff_days, auto_close, active_from)
        VALUES (CAST(:c AS uuid), CAST(:days AS jsonb), true, now())
        ON CONFLICT (company_id) DO UPDATE SET cutoff_days = EXCLUDED.cutoff_days, auto_close = true, updated_at = now()
    """), {**c, "days": CUTOFF_DAYS})


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS payroll_period_config")
