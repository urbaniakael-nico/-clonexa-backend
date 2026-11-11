"""Oficina 3D (Consola v2+, interno de Clonexa): personajes y pisos

Revision ID: 025j_oficina
Revises: 025i_prospecting
Create Date: 2026-11-10

Solo aditiva e idempotente. Filas pequenas (textos cortos, colores y claves del bucket); las
imagenes y los modelos .glb van al bucket clonexa-media (privados), nunca a Postgres. Ninguna
empresa cliente ve nada: solo Admin V2 / v2+.

- oficina_personajes: un personaje guardado desde el editor. company_id NULL = Clonexa (agentes y
  plantillas globales de uniforme); con company_id = representante, plantilla propia de esa empresa
  o una persona puntual. Clave unica (empresa o Clonexa, clave).
- oficina_pisos: por empresa, el orden del piso en el ascensor, la plantilla elegida a mano y la
  privacidad del personal (nombre = primer nombre + inicial; cargo = solo el cargo).
"""
from __future__ import annotations

from alembic import op

revision = "025j_oficina"
down_revision = "025i_prospecting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS oficina_personajes (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NULL REFERENCES companies(id) ON DELETE CASCADE,
            clave varchar(80) NOT NULL,
            nombre varchar(80) NOT NULL DEFAULT '',
            rol varchar(40) NOT NULL DEFAULT '',
            tarea varchar(120) NOT NULL DEFAULT '',
            estilo varchar(10) NOT NULL DEFAULT 'anime',
            color_ropa varchar(7) NOT NULL DEFAULT '',
            color_pantalon varchar(7) NOT NULL DEFAULT '',
            color_pelo varchar(7) NOT NULL DEFAULT '',
            color_piel varchar(7) NOT NULL DEFAULT '',
            accesorio varchar(12) NOT NULL DEFAULT '',
            color_accesorio varchar(7) NOT NULL DEFAULT '',
            cara_key varchar(160) NOT NULL DEFAULT '',
            completa_key varchar(160) NOT NULL DEFAULT '',
            modelo_key varchar(160) NOT NULL DEFAULT '',
            archivos_bytes integer NOT NULL DEFAULT 0,
            updated_by varchar(120) NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_oficina_personajes_estilo CHECK (estilo IN ('lego', 'anime', 'real', 'imagen', 'modelo'))
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_oficina_personajes_clave
        ON oficina_personajes ((COALESCE(company_id::text, '')), clave)
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS oficina_pisos (
            company_id uuid PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
            orden integer NULL,
            plantilla varchar(12) NULL,
            privacidad varchar(8) NOT NULL DEFAULT 'nombre',
            updated_by varchar(120) NOT NULL DEFAULT '',
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_oficina_pisos_plantilla CHECK (plantilla IS NULL OR plantilla IN ('taller', 'restaurante', 'bar', 'campo', 'general')),
            CONSTRAINT ck_oficina_pisos_privacidad CHECK (privacidad IN ('nombre', 'cargo'))
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS oficina_pisos")
    op.execute("DROP TABLE IF EXISTS oficina_personajes")
