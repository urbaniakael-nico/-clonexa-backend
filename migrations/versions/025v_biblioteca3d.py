"""biblioteca 3d: varios disenos por empresa, uniformes, personaje del prototipo y planos de la fase 1 convertidos

Revision ID: 025v_biblioteca3d
Revises: 025u_constructor
Create Date: 2026-11-15

Aditiva e idempotente.
- constructor_planos: diseno_id ('principal' para lo que ya existia), nombre y miniatura (clave del bucket privado:
  la imagen NO se guarda en Postgres). Los indices unicos pasan a ser por diseno.
- oficina_pisos.plano_diseno (que diseno esta en vivo) y b3d_uniformes (ya se sembraron los uniformes iniciales).
- oficina_personajes.look: el personaje del prototipo {toon, human, uniform, custom} en la MISMA fila de la persona.
- constructor_uniformes: uniformes por empresa {nombre, toon, human}.
- Los planos de la fase 1 (formato con "sala") se convierten al JSON del prototipo (constructor_v2.from_v1).
"""
from __future__ import annotations

import json

from alembic import op
from sqlalchemy import text

revision = "025v_biblioteca3d"
down_revision = "025u_constructor"
branch_labels = None
depends_on = None


def _rows(result):
    if result is None:
        return []
    if isinstance(result, list):
        return result
    return [dict(r) for r in result.mappings().all()]


def upgrade() -> None:
    op.execute("ALTER TABLE constructor_planos ADD COLUMN IF NOT EXISTS diseno_id TEXT NOT NULL DEFAULT 'principal'")
    op.execute("ALTER TABLE constructor_planos ADD COLUMN IF NOT EXISTS nombre TEXT NOT NULL DEFAULT 'Mi local'")
    op.execute("ALTER TABLE constructor_planos ADD COLUMN IF NOT EXISTS miniatura TEXT NULL")
    op.execute("DROP INDEX IF EXISTS uq_constructor_borrador")
    op.execute("DROP INDEX IF EXISTS uq_constructor_version")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_constructor_borrador_d ON constructor_planos (company_id, diseno_id) WHERE estado = 'borrador'")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_constructor_version_d ON constructor_planos (company_id, diseno_id, version) WHERE estado = 'publicado'")
    op.execute("ALTER TABLE oficina_pisos ADD COLUMN IF NOT EXISTS plano_diseno TEXT NULL")
    op.execute("ALTER TABLE oficina_pisos ADD COLUMN IF NOT EXISTS b3d_uniformes BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE oficina_personajes ADD COLUMN IF NOT EXISTS look JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("""
        CREATE TABLE IF NOT EXISTS constructor_uniformes (
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            id TEXT NOT NULL,
            nombre TEXT NOT NULL,
            descripcion TEXT NOT NULL DEFAULT '',
            toon JSONB NOT NULL DEFAULT '{}'::jsonb,
            human JSONB NOT NULL DEFAULT '{}'::jsonb,
            orden INTEGER NOT NULL DEFAULT 0,
            updated_by TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (company_id, id)
        )
    """)
    from app.services import constructor_v2 as c2

    bind = op.get_bind()
    glb = {r["id"] for r in _rows(bind.execute(text("SELECT id FROM constructor_catalogo WHERE origen IN ('recurso', 'bucket')")))}
    for r in _rows(bind.execute(text("SELECT id::text AS id, plano FROM constructor_planos WHERE (plano->'sala') IS NOT NULL"))):
        plano = r["plano"] if isinstance(r["plano"], dict) else json.loads(r["plano"])
        bind.execute(text("UPDATE constructor_planos SET plano = CAST(:p AS jsonb) WHERE id = CAST(:i AS uuid)"),
                     {"p": json.dumps(c2.from_v1(plano, glb)), "i": r["id"]})


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS constructor_uniformes")
    op.execute("ALTER TABLE oficina_personajes DROP COLUMN IF EXISTS look")
    op.execute("ALTER TABLE oficina_pisos DROP COLUMN IF EXISTS b3d_uniformes")
    op.execute("ALTER TABLE oficina_pisos DROP COLUMN IF EXISTS plano_diseno")
    op.execute("DROP INDEX IF EXISTS uq_constructor_version_d")
    op.execute("DROP INDEX IF EXISTS uq_constructor_borrador_d")
    op.execute("ALTER TABLE constructor_planos DROP COLUMN IF EXISTS miniatura")
    op.execute("ALTER TABLE constructor_planos DROP COLUMN IF EXISTS nombre")
    op.execute("ALTER TABLE constructor_planos DROP COLUMN IF EXISTS diseno_id")
