"""Redes sociales de Nexa (consola v2+ -> Landing): cifras diarias y publicaciones

Revision ID: 024r_social_metrics
Revises: 024q_quotes_v2
Create Date: 2026-10-21

Aditiva (tablas nuevas, sin company_id: son datos de la propia Clonexa, solo
los ve Admin V2). Las llena n8n (Nexa) por POST /api/v1/social-metrics/ingest.
- social_daily_metrics: una fila por red y dia de Bogota.
- social_posts: una fila por publicacion (red + id externo).
"""
from __future__ import annotations

from alembic import op

revision = "024r_social_metrics"
down_revision = "024q_quotes_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS social_daily_metrics (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            network varchar(20) NOT NULL,
            metric_date date NOT NULL,
            followers integer NULL,
            impressions integer NULL,
            reach integer NULL,
            views integer NULL,
            engagements integer NULL,
            posts_count integer NULL,
            raw jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_social_daily_network_date UNIQUE (network, metric_date)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS social_posts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            network varchar(20) NOT NULL,
            external_id varchar(200) NOT NULL,
            url text NULL,
            published_at timestamptz NULL,
            tema varchar(300) NULL,
            caption varchar(600) NULL,
            video_id_heygen varchar(200) NULL,
            utm_campaign varchar(220) NULL,
            views integer NULL,
            likes integer NULL,
            comments integer NULL,
            shares integer NULL,
            saves integer NULL,
            reach integer NULL,
            raw jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_social_posts_network_external UNIQUE (network, external_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_social_posts_published ON social_posts (published_at DESC)")


def downgrade() -> None:
    # Aditiva: bajar no borra las cifras.
    pass
