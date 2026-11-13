"""iconos de carta clonexa (piloto the time machine)

Revision ID: 025r_iconos_carta
Revises: 025q_nexus_radar
Create Date: 2026-11-13

Aditiva e idempotente:
- inventory_items.icono_key (texto, opcional): el ícono elegido a mano en
  "Cambiar ícono". Vacío = automático (por la primera palabra del nombre).
- carta_icon_misses: empresa + palabra que cae en el ícono genérico + número
  de artículos (para la lista "Palabras sin ícono" de la consola v2+). Solo
  palabras, ningún dato personal.
- Enciende iconos_carta_clonexa SOLO para THE TIME MACHINE (ajustes de su
  módulo QR, como qr_bar_menu en 021m). Las demás empresas no cambian.
Downgrade quita exactamente la clave del ajuste; la columna y la tabla se
quedan (no se borran datos).
"""
from __future__ import annotations

from alembic import op

revision = "025r_iconos_carta"
down_revision = "025q_nexus_radar"
branch_labels = None
depends_on = None

TARGET_COMPANY_ID = "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4"  # THE TIME MACHINE (igual que 021m)
QR_MODULE_CODES = "('qr', 'mesa_qr', 'mesas_qr', 'qr_mesas', 'hospitality_qr', 'voting_qr')"


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
          IF to_regclass('public.inventory_items') IS NOT NULL THEN
            ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS icono_key VARCHAR(40);
          END IF;
        END $$;
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS carta_icon_misses (
          company_id UUID NOT NULL,
          word VARCHAR(40) NOT NULL,
          items INTEGER NOT NULL DEFAULT 0,
          first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
          last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (company_id, word)
        )
    """)
    op.execute(f"""
        UPDATE company_modules cm
        SET settings = COALESCE(cm.settings, '{{}}'::jsonb) || '{{"iconos_carta_clonexa": true}}'::jsonb,
            updated_at = NOW()
        FROM modules m
        WHERE cm.module_id = m.id
          AND m.code IN {QR_MODULE_CODES}
          AND cm.company_id = '{TARGET_COMPANY_ID}'::uuid
    """)


def downgrade() -> None:
    op.execute(f"""
        UPDATE company_modules cm
        SET settings = COALESCE(cm.settings, '{{}}'::jsonb) - 'iconos_carta_clonexa',
            updated_at = NOW()
        FROM modules m
        WHERE cm.module_id = m.id
          AND m.code IN {QR_MODULE_CODES}
          AND cm.company_id = '{TARGET_COMPANY_ID}'::uuid
    """)
