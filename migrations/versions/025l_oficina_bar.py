"""Oficina 3D: piso del bar aprobado (personajes de Mixamo) para The Time Machine

Revision ID: 025l_oficina_bar
Revises: 025k_oficina_real
Create Date: 2026-11-11

Solo interno de Clonexa (Admin V2): ninguna empresa cliente ve nada.
- oficina_pisos.estilo acepta 'bar' (el bar aprobado: oficina_bar.js) ademas de 'clasico' y 'realista'.
- Se enciende SOLO para The Time Machine (21a3065e-...), si existe. Las demas empresas quedan como estaban.
Idempotente: se puede correr dos veces.
"""
from __future__ import annotations

from alembic import op

revision = "025l_oficina_bar"
down_revision = "025k_oficina_real"
branch_labels = None
depends_on = None

TTM = "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4"


def upgrade() -> None:
    op.execute("ALTER TABLE oficina_pisos DROP CONSTRAINT IF EXISTS ck_oficina_pisos_estilo")
    op.execute("ALTER TABLE oficina_pisos ADD CONSTRAINT ck_oficina_pisos_estilo CHECK (estilo IN ('clasico', 'realista', 'bar'))")
    op.execute(f"""
        INSERT INTO oficina_pisos (company_id, estilo, updated_by)
        SELECT id, 'bar', 'migracion 025l' FROM companies WHERE id = CAST('{TTM}' AS uuid)
        ON CONFLICT (company_id) DO UPDATE SET estilo = 'bar', updated_at = now()
    """)


def downgrade() -> None:
    op.execute("UPDATE oficina_pisos SET estilo = 'realista' WHERE estilo = 'bar'")
    op.execute("ALTER TABLE oficina_pisos DROP CONSTRAINT IF EXISTS ck_oficina_pisos_estilo")
    op.execute("ALTER TABLE oficina_pisos ADD CONSTRAINT ck_oficina_pisos_estilo CHECK (estilo IN ('clasico', 'realista'))")
