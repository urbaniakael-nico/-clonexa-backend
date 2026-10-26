"""Menu video (interruptor carta_video del modulo carta): fotos, clips, cola,
lectura de la carta y cupo mensual.

Revision ID: 024s_menu_video
Revises: 024r_social_metrics
Create Date: 2026-10-26

Aditiva: tablas nuevas y dos columnas nuevas en carta_items con valor por
defecto (ninguna empresa cambia). Los bytes de fotos y videos van al bucket
(clonexa-media), nunca a Postgres: aqui solo la llave y el peso.
- menu_media_assets: cada archivo del bucket (original, remasterizada, clip,
  portada) con su empresa y el plato (dish_ref) al que pertenece.
- menu_dish_media: lo que usa cada plato (frente/perfil, original o
  remasterizada, clip y portada). dish_ref = id del plato de la Carta o, en
  la consola, el id del plato en la tabla importada (borrador).
- menu_media_jobs: cola simple (en_cola, procesando, listo, error).
- menu_video_imports: lectura de la carta (n8n + Claude) y su tabla editable.
- menu_video_quota_log: cupo mensual (nuevo, cambio) y solicitudes de mas cupo.
- carta_items.description y carta_items.recipe_pending ("receta pendiente").
"""
from __future__ import annotations

from alembic import op

revision = "024s_menu_video"
down_revision = "024r_social_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE carta_items ADD COLUMN IF NOT EXISTS description varchar(600) NULL")
    op.execute("ALTER TABLE carta_items ADD COLUMN IF NOT EXISTS recipe_pending boolean NOT NULL DEFAULT false")
    op.execute("""
        CREATE TABLE IF NOT EXISTS menu_media_assets (
            id uuid PRIMARY KEY,
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            dish_ref uuid NULL,
            role varchar(10) NOT NULL DEFAULT 'front',
            variant varchar(12) NOT NULL,
            storage_key varchar(200) NOT NULL,
            content_type varchar(40) NOT NULL,
            size_bytes integer NOT NULL DEFAULT 0,
            width integer NULL,
            height integer NULL,
            source_name varchar(200) NULL,
            meta jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_menu_media_assets_company ON menu_media_assets (company_id, dish_ref)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS menu_dish_media (
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            dish_ref uuid NOT NULL,
            front_original uuid NULL,
            front_remaster uuid NULL,
            side_original uuid NULL,
            side_remaster uuid NULL,
            use_remaster boolean NOT NULL DEFAULT true,
            clip_asset uuid NULL,
            poster_asset uuid NULL,
            clip_style varchar(20) NULL,
            status varchar(12) NOT NULL DEFAULT 'sin_video',
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (company_id, dish_ref)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS menu_media_jobs (
            id uuid PRIMARY KEY,
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            dish_ref uuid NOT NULL,
            style varchar(20) NOT NULL DEFAULT 'auto',
            status varchar(12) NOT NULL DEFAULT 'en_cola',
            error varchar(300) NULL,
            attempts integer NOT NULL DEFAULT 0,
            result jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            started_at timestamptz NULL,
            finished_at timestamptz NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_menu_media_jobs_queue ON menu_media_jobs (status, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_menu_media_jobs_dish ON menu_media_jobs (company_id, dish_ref, created_at DESC)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS menu_video_imports (
            id uuid PRIMARY KEY,
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            status varchar(12) NOT NULL DEFAULT 'leyendo',
            source varchar(20) NOT NULL DEFAULT 'manual',
            files jsonb NOT NULL DEFAULT '[]'::jsonb,
            table_data jsonb NOT NULL DEFAULT '{}'::jsonb,
            error varchar(400) NULL,
            summary jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            read_at timestamptz NULL,
            published_at timestamptz NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_menu_video_imports_company ON menu_video_imports (company_id, created_at DESC)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS menu_video_quota_log (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            month char(7) NOT NULL,
            kind varchar(12) NOT NULL,
            carta_item_id uuid NULL,
            detail varchar(300) NULL,
            actor varchar(160) NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_menu_video_quota_month ON menu_video_quota_log (company_id, month, kind)")


def downgrade() -> None:
    # Aditiva: bajar no borra fotos, clips ni el registro del cupo.
    pass
