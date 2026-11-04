"""enlaces cortos del Lider de operacion de VOLTAGE (064C)

Revision ID: 025b_lider_short_links
Revises: 025a_attendance_adjustments
Create Date: 2026-11-04

Dos filas pequenas de texto en short_links, una por operacion, solo para VOLTAGE. El codigo no es
una credencial: lleva a la pantalla de ingreso, que sigue pidiendo usuario y clave. Si una empresa u
operacion no los tiene, la consola v2+ crea el suyo al abrir la tarjeta. Si la empresa no existe, no
inserta nada.
"""
from __future__ import annotations

from alembic import op

revision = "025b_lider_short_links"
down_revision = "025a_attendance_adjustments"
branch_labels = None
depends_on = None

VOLTAGE = "f1e8f774-f052-49ca-880a-268805f07db0"
LINKS = {"virginia": "8AWXZJSY", "alabama": "2M496FCU"}


def upgrade() -> None:
    for lugar, code in LINKS.items():
        target = f"/mini-panel/login?company_id={VOLTAGE}&type=lider_operacion&lugar={lugar}"
        op.execute(
            f"""
            INSERT INTO short_links (code, company_id, kind, target)
            SELECT '{code}', id, 'mini_panel', '{target}' FROM companies WHERE id = '{VOLTAGE}'::uuid
            ON CONFLICT DO NOTHING
            """
        )


def downgrade() -> None:
    codes = ", ".join(f"'{code}'" for code in LINKS.values())
    op.execute(f"DELETE FROM short_links WHERE company_id = '{VOLTAGE}'::uuid AND code IN ({codes})")
