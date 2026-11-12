"""Oficina 3D: pisos aprobados de Clonexa, Velvet, Asadero El Socio y VOLTAGE + genero en el editor

Revision ID: 025m_oficina_pisos
Revises: 025l_oficina_bar
Create Date: 2026-11-11

Solo interno de Clonexa (Admin V2): ninguna empresa cliente ve nada. Aditiva e idempotente.
- oficina_pisos.estilo acepta 'aprobado' (motor por plantilla: taller, restaurante, campo). Se enciende SOLO
  para Velvet, ASADERO EL SOCIO y VOLTAGE (si existen). The Time Machine sigue con 'bar'.
- oficina_ajustes: interruptores de la oficina que no son de una empresa. 'piso_clonexa' = 'aprobado' enciende
  el piso futurista de Clonexa (el dueño lo pidio); sin la fila, el piso clasico de siempre.
- oficina_personajes: genero (hombre/mujer), personaje de Mixamo, tunica, barba y color de barba.
"""
from __future__ import annotations

from alembic import op

revision = "025m_oficina_pisos"
down_revision = "025l_oficina_bar"
branch_labels = None
depends_on = None

FLOORS = ("d63cf68c-be5b-4a30-aee4-341973018db1",   # Velvet
          "7625872c-f941-4479-a27b-f8443be953c5",   # ASADERO EL SOCIO
          "f1e8f774-f052-49ca-880a-268805f07db0")   # VOLTAGE


def upgrade() -> None:
    op.execute("ALTER TABLE oficina_pisos DROP CONSTRAINT IF EXISTS ck_oficina_pisos_estilo")
    op.execute("ALTER TABLE oficina_pisos ADD CONSTRAINT ck_oficina_pisos_estilo CHECK (estilo IN ('clasico', 'realista', 'bar', 'aprobado'))")
    ids = ", ".join(f"CAST('{c}' AS uuid)" for c in FLOORS)
    op.execute(f"""
        INSERT INTO oficina_pisos (company_id, estilo, updated_by)
        SELECT id, 'aprobado', 'migracion 025m' FROM companies WHERE id IN ({ids})
        ON CONFLICT (company_id) DO UPDATE SET estilo = 'aprobado', updated_at = now()
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS oficina_ajustes (
            clave varchar(40) PRIMARY KEY,
            valor varchar(40) NOT NULL DEFAULT '',
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("INSERT INTO oficina_ajustes (clave, valor) VALUES ('piso_clonexa', 'aprobado') ON CONFLICT (clave) DO NOTHING")
    for col, size in (("genero", 6), ("personaje", 20), ("tunica", 3), ("barba", 3), ("color_barba", 7)):
        op.execute(f"ALTER TABLE oficina_personajes ADD COLUMN IF NOT EXISTS {col} varchar({size}) NOT NULL DEFAULT ''")


def downgrade() -> None:
    for col in ("genero", "personaje", "tunica", "barba", "color_barba"):
        op.execute(f"ALTER TABLE oficina_personajes DROP COLUMN IF EXISTS {col}")
    op.execute("DROP TABLE IF EXISTS oficina_ajustes")
    op.execute("UPDATE oficina_pisos SET estilo = 'clasico' WHERE estilo = 'aprobado'")
    op.execute("ALTER TABLE oficina_pisos DROP CONSTRAINT IF EXISTS ck_oficina_pisos_estilo")
    op.execute("ALTER TABLE oficina_pisos ADD CONSTRAINT ck_oficina_pisos_estilo CHECK (estilo IN ('clasico', 'realista', 'bar'))")
