"""waiter ordering fase 2

Revision ID: 021d_waiter_ordering_p2
Revises: 021c_waiter_ordering_ttm
Create Date: 2026-09-23

Fase 2 mesero -> cocina -> caja (roles, porciones, imagenes con tope,
anulacion/correccion, cierre de turno). Per decision explicita del usuario:
estas tablas/columnas quedan en el historial de alembic (no creadas al
vuelo como en Fase 1), para tener rastro claro si un despliegue falla.

hospitality_categories y mini_panel_work_sessions YA EXISTEN en produccion
(creadas de forma perezosa por Fase 1 y por el mini-panel operativo
respectivamente). Sus CREATE TABLE IF NOT EXISTS de aqui son solo una red
de seguridad para una base nueva que nunca las creo -- en produccion son
no-ops. Downgrade NUNCA borra esas dos tablas (tienen datos reales de
varias empresas); solo revierte lo que esta migracion agrego.
"""
from __future__ import annotations

from alembic import op

revision = "021d_waiter_ordering_p2"
down_revision = "021c_waiter_ordering_ttm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    # Red de seguridad: mismo esquema que ya crea Fase 1 (waiter_ordering.py
    # ensure_waiter_ordering_storage). No-op si ya existe.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS hospitality_categories (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            category_key VARCHAR(120) NOT NULL,
            label VARCHAR(160) NOT NULL DEFAULT '',
            station VARCHAR(80) NOT NULL DEFAULT '',
            quick_notes JSONB NOT NULL DEFAULT '[]'::jsonb,
            image_bytes BYTEA NULL,
            image_content_type VARCHAR(80) NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (company_id, category_key)
        );
        """
    )
    op.execute(
        "ALTER TABLE hospitality_categories ADD COLUMN IF NOT EXISTS requires_term BOOLEAN NOT NULL DEFAULT FALSE;"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS hospitality_product_portions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            product_group_key VARCHAR(160) NOT NULL,
            group_label VARCHAR(160) NOT NULL DEFAULT '',
            inventory_item_id UUID NOT NULL,
            portion_label VARCHAR(40) NOT NULL,
            position INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (company_id, inventory_item_id)
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_hospitality_product_portions_group
        ON hospitality_product_portions (company_id, product_group_key, position);
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS hospitality_product_images (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            inventory_item_id UUID NOT NULL,
            image_bytes BYTEA NULL,
            image_content_type VARCHAR(80) NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (company_id, inventory_item_id)
        );
        """
    )

    # Red de seguridad: mismo esquema que ya crea company_users.py
    # (_cx_mp_work_ensure_019f). No-op si ya existe.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mini_panel_work_sessions (
            id uuid PRIMARY KEY,
            company_id uuid NOT NULL,
            user_id uuid NOT NULL,
            employee_id uuid NULL,
            panel_type text NOT NULL,
            status text NOT NULL DEFAULT 'active',
            location_label text NOT NULL DEFAULT 'Trabajo',
            started_at timestamptz NOT NULL DEFAULT now(),
            ended_at timestamptz NULL,
            active_seconds integer NOT NULL DEFAULT 0,
            break_seconds integer NOT NULL DEFAULT 0,
            active_started_at timestamptz NULL,
            current_break_started_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mini_panel_work_sessions_company_user_type
        ON mini_panel_work_sessions (company_id, user_id, panel_type, started_at DESC);
        """
    )
    op.execute(
        "ALTER TABLE mini_panel_work_sessions ADD COLUMN IF NOT EXISTS closed_reason TEXT NOT NULL DEFAULT '';"
    )


def downgrade() -> None:
    # Solo lo que esta migracion agrego. hospitality_categories y
    # mini_panel_work_sessions existian antes con datos reales -- nunca se
    # borran aqui, solo se les revierte la columna nueva.
    op.execute("ALTER TABLE mini_panel_work_sessions DROP COLUMN IF EXISTS closed_reason;")
    op.execute("DROP TABLE IF EXISTS hospitality_product_images;")
    op.execute("DROP INDEX IF EXISTS ix_hospitality_product_portions_group;")
    op.execute("DROP TABLE IF EXISTS hospitality_product_portions;")
    op.execute("ALTER TABLE hospitality_categories DROP COLUMN IF EXISTS requires_term;")
