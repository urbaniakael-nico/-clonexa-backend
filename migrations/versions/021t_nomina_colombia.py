"""nomina_colombia: normativa laboral colombiana en Nomina (049A)

Revision ID: 021t_nomina_colombia
Revises: 021s_domicilios_whatsapp
Create Date: 2026-09-25

Crea el modulo general "nomina_colombia" (fila del catalogo `modules`, para
que Admin V2 lo liste como el interruptor "APLICAR NORMATIVA LABORAL
COLOMBIANA" de cada empresa). No se activa para ninguna empresa: sin fila en
company_modules la nomina calcula exactamente como hoy.

Tablas (filas pequenas, solo numeros/JSON):
- payroll_co_params: parametros de ley por año (SMMLV, auxilio, jornada,
  recargos, aportes, provisiones) con sus cambios fechados dentro del año.
  Se editan desde Admin V2; aqui solo se carga 2026.
- payroll_co_company: nivel de riesgo ARL y exoneracion por empresa.
- payroll_co_employee: salario base mensual (y ARL propia) por empleado.
"""
from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = "021t_nomina_colombia"
down_revision = "021s_domicilios_whatsapp"
branch_labels = None
depends_on = None

MODULE_CODE = "nomina_colombia"

# 2026: SMMLV Decreto 1469 de 2025, auxilio Decreto 1470 de 2025. Jornada
# (Ley 2101 de 2021): 44 h desde el 15/07/2025 y 42 h desde el 15/07/2026.
# Recargos (Ley 2466 de 2025): nocturno 35% desde las 19:00, dominical 80%
# hasta el 30/06/2026, 90% desde el 01/07/2026 y 100% desde el 01/07/2027.
PARAMS_2026 = {
    "smmlv": 1750905,
    "transport_allowance": 249095,
    "transport_cap_smmlv": 2,
    "weekly_hours": 44,
    "monthly_hours_per_weekly_hour": 5,
    "daily_ordinary_hours": 8,
    "night_start": "19:00",
    "night_end": "06:00",
    "night_pct": 35,
    "extra_day_pct": 25,
    "extra_night_pct": 75,
    "sunday_holiday_pct": 80,
    "max_extra_daily_hours": 2,
    "max_extra_weekly_hours": 12,
    "health_employee_pct": 4,
    "pension_employee_pct": 4,
    "fsp_min_smmlv": 4,
    "fsp_brackets": [[4, 1], [16, 1.2], [17, 1.4], [18, 1.6], [19, 1.8], [20, 2]],
    "pension_employer_pct": 12,
    "health_employer_pct": 8.5,
    "exoneration_max_smmlv": 10,
    "arl_pct_by_level": {"1": 0.522, "2": 1.044, "3": 2.436, "4": 4.35, "5": 6.96},
    "ccf_pct": 4,
    "icbf_pct": 3,
    "sena_pct": 2,
    "severance_pct": 8.33,
    "severance_interest_pct": 1,
    "service_bonus_pct": 8.33,
    "vacation_pct": 4.17,
    "extra_holidays": [],
}
CHANGES_2026 = [
    {"from": "2026-07-01", "sunday_holiday_pct": 90},
    {"from": "2026-07-15", "weekly_hours": 42},
    {"from": "2027-07-01", "sunday_holiday_pct": 100},
]

_SELECT_MODULE = sa.text("SELECT id FROM modules WHERE code = :code LIMIT 1")
_INSERT_MODULE = sa.text(
    """
    INSERT INTO modules (id, code, name, description, category, is_active, created_at, updated_at)
    VALUES (CAST(:id AS uuid), :code, :name, :description, :category, TRUE, NOW(), NOW())
    """
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS payroll_co_params (
            year integer PRIMARY KEY,
            params jsonb NOT NULL DEFAULT '{}'::jsonb,
            changes jsonb NOT NULL DEFAULT '[]'::jsonb,
            updated_by varchar(160) NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS payroll_co_company (
            company_id uuid PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
            arl_level integer NOT NULL DEFAULT 1,
            exonerated boolean NOT NULL DEFAULT false,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS payroll_co_employee (
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            monthly_salary numeric(14,2) NOT NULL DEFAULT 0,
            arl_level integer NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (company_id, employee_id)
        )
        """
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO payroll_co_params (year, params, changes, updated_by)
            VALUES (2026, CAST(:params AS jsonb), CAST(:changes AS jsonb), 'migracion 021t')
            ON CONFLICT (year) DO NOTHING
            """
        ),
        {"params": json.dumps(PARAMS_2026), "changes": json.dumps(CHANGES_2026)},
    )
    if not bind.execute(_SELECT_MODULE, {"code": MODULE_CODE}).mappings().first():
        bind.execute(_INSERT_MODULE, {
            "id": str(uuid.uuid4()),
            "code": MODULE_CODE,
            "name": "APLICAR NORMATIVA LABORAL COLOMBIANA",
            "description": "Nomina con recargos, extras, auxilio, aportes y provisiones segun la ley colombiana.",
            "category": "finance",
        })


def downgrade() -> None:
    bind = op.get_bind()
    module_row = bind.execute(_SELECT_MODULE, {"code": MODULE_CODE}).mappings().first()
    if module_row:
        bind.execute(sa.text("DELETE FROM company_modules WHERE module_id = :module_id"), {"module_id": module_row["id"]})
        bind.execute(sa.text("DELETE FROM modules WHERE id = :module_id"), {"module_id": module_row["id"]})
    op.execute("DROP TABLE IF EXISTS payroll_co_employee")
    op.execute("DROP TABLE IF EXISTS payroll_co_company")
    op.execute("DROP TABLE IF EXISTS payroll_co_params")
