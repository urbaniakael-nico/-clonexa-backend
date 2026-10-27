"""Menu video v2: foto "Desde arriba" y archivos descartados con 30 dias de gracia.

Revision ID: 024t_menu_media_v2
Revises: 024s_menu_video
Create Date: 2026-10-26

Aditiva (columnas nuevas que pueden ir vacias; ninguna empresa cambia):
- menu_dish_media.top_original / top_remaster: tercera foto opcional.
- menu_media_assets.discarded_at: al quitar o cambiar una foto (o un video) el
  archivo NO se borra del bucket de inmediato: queda marcado y se elimina a los
  30 dias (por si hay que recuperarlo). Las originales nunca se pisan.
"""
from __future__ import annotations

from alembic import op

revision = "024t_menu_media_v2"
down_revision = "024s_menu_video"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE menu_dish_media ADD COLUMN IF NOT EXISTS top_original uuid NULL")
    op.execute("ALTER TABLE menu_dish_media ADD COLUMN IF NOT EXISTS top_remaster uuid NULL")
    op.execute("ALTER TABLE menu_media_assets ADD COLUMN IF NOT EXISTS discarded_at timestamptz NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_menu_media_assets_discarded ON menu_media_assets (discarded_at) WHERE discarded_at IS NOT NULL")


def downgrade() -> None:
    # Aditiva: bajar no borra fotos ni marcas.
    pass
