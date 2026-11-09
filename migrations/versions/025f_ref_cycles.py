"""Referencias: Terminar ciclo en vez de cerrar talla (076A)

Revision ID: 025f_ref_cycles
Revises: 025e_work_schedule
Create Date: 2026-11-09

Solo aditiva e idempotente; filas pequenas (texto corto, enteros y fechas; nada de imagenes ni
archivos). No borra nada.

- reference_finished_cycles: cada ciclo terminado de una talla (cantidad, quien, cuando). La
  cantidad se suma a lo producido con una fila source_channel 'ciclo_terminado' en
  reference_production_closures (closure_id apunta a ella).
- reference_size_closes: converted_at / converted_cycle_id. Cada cierre guardado (vigente o
  reabierto) pasa a ser un ciclo terminado con la misma cantidad, fecha y persona, y queda marcado
  como convertido (la fila original no se toca en lo demas). Un cierre vigente que habia apagado
  el bot lo devuelve como estaba: la talla queda activa. Correr dos veces no duplica nada.
"""
from __future__ import annotations

from alembic import op

revision = "025f_ref_cycles"
down_revision = "025e_work_schedule"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS reference_finished_cycles (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id text NOT NULL,
            ref_key text NOT NULL,
            reference_id text NOT NULL,
            reference_name text NOT NULL,
            size text NOT NULL,
            quantity integer NOT NULL,
            actor varchar(200) NOT NULL,
            closure_id text NOT NULL,
            source_close_id uuid NULL,
            note varchar(40) NULL,
            finished_at timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_ref_finished_cycles_company ON reference_finished_cycles (company_id, ref_key, finished_at DESC)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_ref_finished_cycles_source ON reference_finished_cycles (source_close_id) WHERE source_close_id IS NOT NULL")
    op.execute("ALTER TABLE reference_size_closes ADD COLUMN IF NOT EXISTS converted_at timestamptz NULL")
    op.execute("ALTER TABLE reference_size_closes ADD COLUMN IF NOT EXISTS converted_cycle_id uuid NULL")
    # 1) Un cierre vigente que apago el bot: la talla vuelve como estaba (queda activa).
    op.execute("""
        UPDATE product_references pr
        SET bot_active = true, channel = COALESCE(c.prev_channel, 'bot'), system_active = (COALESCE(c.prev_channel, 'bot') <> 'bot'), updated_at = now()
        FROM reference_size_closes c
        WHERE c.converted_at IS NULL AND c.reopened_at IS NULL AND c.prev_bot_active IS TRUE
          AND COALESCE(c.reference_id, '') <> '' AND pr.id::text = c.reference_id AND pr.company_id::text = c.company_id
    """)
    # 2) Cada cierre con prendas pasa a ciclo terminado: misma cantidad, fecha y persona.
    op.execute("""
        WITH src AS MATERIALIZED (
            SELECT c.id, c.company_id, c.ref_key, c.reference_id, c.size, c.closed_qty, c.actor, c.closed_at, c.reason_code, pr.name AS reference_name,
                   gen_random_uuid() AS cycle_id, gen_random_uuid()::text AS closure_id
            FROM reference_size_closes c
            JOIN product_references pr ON pr.id::text = c.reference_id AND pr.company_id::text = c.company_id
            WHERE c.converted_at IS NULL AND c.closed_qty > 0
              AND NOT EXISTS (SELECT 1 FROM reference_finished_cycles f WHERE f.source_close_id = c.id)
        ), closures AS (
            INSERT INTO reference_production_closures (id, company_id, employee_id, employee_name, telegram_user_id, reference_id, reference_name, size,
                quantity_finished, notes, closed_at, source_channel, created_at)
            SELECT closure_id, company_id, '', actor, '', reference_id, reference_name, size, closed_qty, 'Ciclo terminado (antes cierre de talla)', closed_at, 'ciclo_terminado', now()
            FROM src RETURNING id
        ), cycles AS (
            INSERT INTO reference_finished_cycles (id, company_id, ref_key, reference_id, reference_name, size, quantity, actor, closure_id, source_close_id, note, finished_at)
            SELECT cycle_id, company_id, ref_key, reference_id, reference_name, size, closed_qty, actor, closure_id, id, reason_code, closed_at FROM src RETURNING id
        )
        UPDATE reference_size_closes c SET converted_at = now(), converted_cycle_id = src.cycle_id FROM src WHERE c.id = src.id
    """)
    # 3) Los cierres sin prendas o sin fila tampoco cuentan ya como cierre.
    op.execute("UPDATE reference_size_closes SET converted_at = now() WHERE converted_at IS NULL")


def downgrade() -> None:
    # Nada se borra: los ciclos convertidos son produccion registrada.
    pass
