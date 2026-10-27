"""Menu video v3: 2 caminos (subir video o subir foto) y galeria de "Detalle".

Revision ID: 024u_menu_media_v3
Revises: 024t_menu_media_v2
Create Date: 2026-10-27

- menu_dish_media.mode: "foto" (Camino 2, se anima la foto principal) o
  "video" (Camino 1, el video real del plato).
- menu_dish_media.video_original: el video subido (bucket, nunca Postgres).
- menu_dish_media.gallery: "Más fotos (galería)" del boton Detalle, lista de
  {"original": id, "remaster": id}. NUNCA se mezclan en el video.
- menu_dish_media.options: estilo, fondo, velocidad y tramo elegidos.

Fotos ya subidas (ninguna se pierde): "frente" pasa a ser la foto principal
(columnas front_*); si el plato no tenia frente, la primera que haya (desde
arriba, luego perfil). Las demas pasan a la galeria en ese orden.
"""
from __future__ import annotations

from alembic import op

revision = "024u_menu_media_v3"
down_revision = "024t_menu_media_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE menu_dish_media ADD COLUMN IF NOT EXISTS mode varchar(10) NOT NULL DEFAULT 'foto'")
    op.execute("ALTER TABLE menu_dish_media ADD COLUMN IF NOT EXISTS video_original uuid NULL")
    op.execute("ALTER TABLE menu_dish_media ADD COLUMN IF NOT EXISTS gallery jsonb NOT NULL DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE menu_dish_media ADD COLUMN IF NOT EXISTS options jsonb NOT NULL DEFAULT '{}'::jsonb")
    # sin frente: la primera que haya pasa a principal
    op.execute("""
        UPDATE menu_dish_media SET front_original = top_original, front_remaster = top_remaster,
               top_original = NULL, top_remaster = NULL
        WHERE front_original IS NULL AND top_original IS NOT NULL
    """)
    op.execute("""
        UPDATE menu_dish_media SET front_original = side_original, front_remaster = side_remaster,
               side_original = NULL, side_remaster = NULL
        WHERE front_original IS NULL AND side_original IS NOT NULL
    """)
    # las demas, a la galeria (desde arriba -> perfil)
    op.execute("""
        UPDATE menu_dish_media SET gallery = gallery
               || CASE WHEN top_original IS NOT NULL THEN jsonb_build_array(jsonb_build_object(
                      'original', top_original::text, 'remaster', COALESCE(top_remaster::text, ''))) ELSE '[]'::jsonb END
               || CASE WHEN side_original IS NOT NULL THEN jsonb_build_array(jsonb_build_object(
                      'original', side_original::text, 'remaster', COALESCE(side_remaster::text, ''))) ELSE '[]'::jsonb END,
               top_original = NULL, top_remaster = NULL, side_original = NULL, side_remaster = NULL
        WHERE top_original IS NOT NULL OR side_original IS NOT NULL
    """)


def downgrade() -> None:
    # Aditiva: bajar no borra fotos ni videos.
    pass
