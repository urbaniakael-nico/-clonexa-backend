"""Oficina 3D · Recepcion con Nexa (diseno aprobado recepcion.html / recepcion.png).

- oficina_ajustes.piso_recepcion = 'aprobado' enciende la planta baja nueva (Nexa recepcionista + interesados reales
  de hoy). Es un piso interno de Clonexa (no de una empresa): el dueno lo pidio. Sin la fila, la recepcion clasica.
Aditiva: no crea tablas ni guarda datos pesados (la recepcion lee lo que ya existe: wa_contacts, prospects, n8n).
"""
from __future__ import annotations

from alembic import op

revision = "025n_oficina_recepcion"
down_revision = "025m_oficina_pisos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS oficina_ajustes (
            clave varchar(40) PRIMARY KEY,
            valor varchar(40) NOT NULL DEFAULT '',
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("INSERT INTO oficina_ajustes (clave, valor) VALUES ('piso_recepcion', 'aprobado') ON CONFLICT (clave) DO NOTHING")


def downgrade() -> None:
    op.execute("DELETE FROM oficina_ajustes WHERE clave = 'piso_recepcion'")
