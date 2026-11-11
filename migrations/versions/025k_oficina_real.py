"""Oficina 3D fase 1.5: piso realista por empresa, distribucion (modo arquitecto) y cuerpo/peinado

Revision ID: 025k_oficina_real
Revises: 025j_oficina
Create Date: 2026-11-11

Solo aditiva e idempotente (interno de Clonexa: ninguna empresa cliente ve nada).
- oficina_pisos.estilo: interruptor por empresa del piso realista, 'clasico' por defecto. Se enciende
  SOLO para The Time Machine (21a3065e-...), si existe.
- oficina_pisos.distribucion: posiciones guardadas en el modo arquitecto ({"items": {clave: [x, z, giro]}}),
  unos pocos KB por empresa.
- oficina_personajes.cuerpo / peinado: variantes del editor nuevo.
Las columnas de imagen/modelo (cara_key, completa_key, modelo_key) se conservan: no se borra nada; la
oficina solo deja de usarlas.
"""
from __future__ import annotations

from alembic import op

revision = "025k_oficina_real"
down_revision = "025j_oficina"
branch_labels = None
depends_on = None

TTM = "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4"


def upgrade() -> None:
    op.execute("ALTER TABLE oficina_pisos ADD COLUMN IF NOT EXISTS estilo varchar(10) NOT NULL DEFAULT 'clasico'")
    op.execute("ALTER TABLE oficina_pisos ADD COLUMN IF NOT EXISTS distribucion jsonb NOT NULL DEFAULT '{}'::jsonb")
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_oficina_pisos_estilo') THEN
                ALTER TABLE oficina_pisos ADD CONSTRAINT ck_oficina_pisos_estilo CHECK (estilo IN ('clasico', 'realista'));
            END IF;
        END $$
    """)
    op.execute("ALTER TABLE oficina_personajes ADD COLUMN IF NOT EXISTS cuerpo varchar(12) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE oficina_personajes ADD COLUMN IF NOT EXISTS peinado varchar(12) NOT NULL DEFAULT ''")
    op.execute(f"""
        INSERT INTO oficina_pisos (company_id, estilo, updated_by)
        SELECT id, 'realista', 'migracion 025k' FROM companies WHERE id = CAST('{TTM}' AS uuid)
        ON CONFLICT (company_id) DO UPDATE SET estilo = 'realista', updated_at = now()
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE oficina_personajes DROP COLUMN IF EXISTS peinado")
    op.execute("ALTER TABLE oficina_personajes DROP COLUMN IF EXISTS cuerpo")
    op.execute("ALTER TABLE oficina_pisos DROP CONSTRAINT IF EXISTS ck_oficina_pisos_estilo")
    op.execute("ALTER TABLE oficina_pisos DROP COLUMN IF EXISTS distribucion")
    op.execute("ALTER TABLE oficina_pisos DROP COLUMN IF EXISTS estilo")
