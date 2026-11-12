"""Negocio en vivo 3D (modulo vendible live3d, categoria Complementos).

Revision ID: 025o_live3d
Revises: 025n_oficina_recepcion
Create Date: 2026-11-12

- Modulo "live3d" en el catalogo (apagado para todas las empresas). Se enciende SOLO para The Time Machine (piloto).
- Ajustes del modulo en la MISMA fila de la Oficina 3D (oficina_pisos, una sola fuente): quien_ve, roles_ve, modo_tv,
  liviano. Plantilla y privacidad ya estaban ahi.
- live3d_consumo: bytes servidos y pico de pantallas por empresa y mes (filas chicas, sin datos pesados). La imagen
  de vista previa del piso va al bucket privado, nunca a Postgres.
Aditiva e idempotente: se puede correr dos veces.
"""
from __future__ import annotations

from alembic import op

revision = "025o_live3d"
down_revision = "025n_oficina_recepcion"
branch_labels = None
depends_on = None

TTM = "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4"


def upgrade() -> None:
    op.execute("ALTER TABLE oficina_pisos ADD COLUMN IF NOT EXISTS quien_ve varchar(20) NOT NULL DEFAULT 'dueno_admin'")
    op.execute("ALTER TABLE oficina_pisos ADD COLUMN IF NOT EXISTS roles_ve jsonb NOT NULL DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE oficina_pisos ADD COLUMN IF NOT EXISTS modo_tv boolean NOT NULL DEFAULT true")
    op.execute("ALTER TABLE oficina_pisos ADD COLUMN IF NOT EXISTS liviano varchar(12) NOT NULL DEFAULT 'auto'")
    op.execute("""
        CREATE TABLE IF NOT EXISTS live3d_consumo (
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            mes date NOT NULL,
            bytes bigint NOT NULL DEFAULT 0,
            pantallas_max integer NOT NULL DEFAULT 0,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (company_id, mes)
        )
    """)
    op.execute("""
        INSERT INTO modules (id, code, name, description, category, is_active, created_at, updated_at)
        SELECT gen_random_uuid(), 'live3d', 'Negocio en vivo 3D',
               'El cliente ve su negocio en 3D con sus datos reales. Solo su propio piso.', 'Complementos', TRUE, now(), now()
        WHERE NOT EXISTS (SELECT 1 FROM modules WHERE lower(code) = 'live3d')
    """)
    op.execute(f"""
        INSERT INTO company_modules (id, company_id, module_id, enabled, settings, activated_at, created_at, updated_at)
        SELECT gen_random_uuid(), c.id, m.id, TRUE, '{{}}'::jsonb, now(), now(), now()
        FROM companies c JOIN modules m ON lower(m.code) = 'live3d'
        WHERE c.id = CAST('{TTM}' AS uuid)
          AND NOT EXISTS (SELECT 1 FROM company_modules x WHERE x.company_id = c.id AND x.module_id = m.id)
    """)
    op.execute(f"""
        INSERT INTO oficina_pisos (company_id, estilo, updated_by)
        SELECT id, 'bar', 'migracion 025o' FROM companies WHERE id = CAST('{TTM}' AS uuid)
        ON CONFLICT (company_id) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM company_modules WHERE module_id IN (SELECT id FROM modules WHERE lower(code) = 'live3d')")
    op.execute("DELETE FROM modules WHERE lower(code) = 'live3d'")
    op.execute("DROP TABLE IF EXISTS live3d_consumo")
    for col in ("quien_ve", "roles_ve", "modo_tv", "liviano"):
        op.execute(f"ALTER TABLE oficina_pisos DROP COLUMN IF EXISTS {col}")
