"""costos: egresos, proveedores, cuentas por pagar, caja chica, recurrentes,
presupuesto y arqueo de caja a ciegas (049I)

Revision ID: 021x_costos_module
Revises: 021w_carta_module
Create Date: 2026-09-27

Modulo "costos" en el catalogo de Admin V2, activado SOLO para ASADERO EL
SOCIO. Filas pequeñas (texto y numeros); los soportes son fotos comprimidas
por media_storage (<= 200 KB) con cupo por empresa.

cash_counts (arqueos): el conteo y lo esperado quedan fijos al registrarse
(trigger). Solo la observacion se completa despues, una vez; cerrado el
arqueo ya no cambia nada.
"""
from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = "021x_costos_module"
down_revision = "021w_carta_module"
branch_labels = None
depends_on = None

TARGET_COMPANY_ID = "7625872c-f941-4479-a27b-f8443be953c5"
MODULE_CODE = "costos"
TABLES = """
CREATE TABLE IF NOT EXISTS cost_centers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    name varchar(120) NOT NULL,
    is_default boolean NOT NULL DEFAULT false,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_cost_center_name UNIQUE (company_id, name)
);
CREATE TABLE IF NOT EXISTS suppliers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    name varchar(180) NOT NULL,
    nit varchar(40) NOT NULL DEFAULT '',
    contact_name varchar(160) NOT NULL DEFAULT '',
    phone varchar(60) NOT NULL DEFAULT '',
    email varchar(160) NOT NULL DEFAULT '',
    payment_terms varchar(240) NOT NULL DEFAULT '',
    credit_days integer NOT NULL DEFAULT 0,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS expenses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    cost_center_id uuid NULL REFERENCES cost_centers(id) ON DELETE SET NULL,
    expense_date date NOT NULL,
    category varchar(40) NOT NULL,
    supplier_id uuid NULL REFERENCES suppliers(id) ON DELETE SET NULL,
    supplier_name varchar(180) NOT NULL DEFAULT '',
    description varchar(1000) NOT NULL DEFAULT '',
    subtotal numeric(14,2) NOT NULL DEFAULT 0,
    iva numeric(14,2) NOT NULL DEFAULT 0,
    retention numeric(14,2) NOT NULL DEFAULT 0,
    total numeric(14,2) NOT NULL DEFAULT 0,
    payment_method varchar(20) NOT NULL DEFAULT 'efectivo',
    paid_from varchar(20) NOT NULL DEFAULT 'banco',
    status varchar(20) NOT NULL DEFAULT 'aprobado',
    due_date date NULL,
    paid_at timestamptz NULL,
    recurring_id uuid NULL,
    cashier_session_id uuid NULL,
    created_by_id varchar(64) NOT NULL DEFAULT '',
    created_by_name varchar(180) NOT NULL DEFAULT '',
    created_by_kind varchar(20) NOT NULL DEFAULT '',
    approved_by_name varchar(180) NOT NULL DEFAULT '',
    approved_at timestamptz NULL,
    rejected_reason varchar(500) NOT NULL DEFAULT '',
    inventory_applied boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_expenses_company_date ON expenses (company_id, expense_date DESC);
CREATE INDEX IF NOT EXISTS ix_expenses_company_status ON expenses (company_id, status);
CREATE INDEX IF NOT EXISTS ix_expenses_session ON expenses (company_id, cashier_session_id);
CREATE TABLE IF NOT EXISTS expense_lines (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    expense_id uuid NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
    inventory_item_id uuid NOT NULL,
    quantity numeric(14,4) NOT NULL,
    purchase_unit varchar(20) NOT NULL DEFAULT 'unidad',
    unit_price numeric(14,4) NOT NULL DEFAULT 0,
    total numeric(14,2) NOT NULL DEFAULT 0,
    consumption_qty numeric(14,4) NOT NULL DEFAULT 0,
    unit_cost numeric(14,4) NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_expense_lines_item ON expense_lines (company_id, inventory_item_id);
CREATE TABLE IF NOT EXISTS expense_attachments (
    company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    expense_id uuid NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
    image_bytes bytea NULL,
    image_content_type varchar(60) NULL,
    size_bytes integer NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, expense_id)
);
CREATE TABLE IF NOT EXISTS petty_cash_funds (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    cost_center_id uuid NULL REFERENCES cost_centers(id) ON DELETE SET NULL,
    name varchar(120) NOT NULL,
    amount numeric(14,2) NOT NULL DEFAULT 0,
    responsible_name varchar(160) NOT NULL DEFAULT '',
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS petty_cash_moves (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    fund_id uuid NOT NULL REFERENCES petty_cash_funds(id) ON DELETE CASCADE,
    amount numeric(14,2) NOT NULL,
    note varchar(500) NOT NULL DEFAULT '',
    created_by_name varchar(180) NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE expenses ADD COLUMN IF NOT EXISTS petty_fund_id uuid NULL;
CREATE TABLE IF NOT EXISTS recurring_expenses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    cost_center_id uuid NULL REFERENCES cost_centers(id) ON DELETE SET NULL,
    category varchar(40) NOT NULL,
    supplier_id uuid NULL REFERENCES suppliers(id) ON DELETE SET NULL,
    supplier_name varchar(180) NOT NULL DEFAULT '',
    description varchar(500) NOT NULL DEFAULT '',
    subtotal numeric(14,2) NOT NULL DEFAULT 0,
    iva numeric(14,2) NOT NULL DEFAULT 0,
    retention numeric(14,2) NOT NULL DEFAULT 0,
    payment_method varchar(20) NOT NULL DEFAULT 'transferencia',
    paid_from varchar(20) NOT NULL DEFAULT 'banco',
    day_of_month integer NOT NULL DEFAULT 1,
    active boolean NOT NULL DEFAULT true,
    last_generated_month varchar(7) NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS budgets (
    company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    category varchar(40) NOT NULL,
    monthly_amount numeric(14,2) NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, category)
);
CREATE TABLE IF NOT EXISTS cash_counts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    cost_center_id uuid NULL REFERENCES cost_centers(id) ON DELETE SET NULL,
    cashier_session_id uuid NOT NULL,
    cashier_user_id varchar(64) NOT NULL DEFAULT '',
    cashier_name varchar(180) NOT NULL DEFAULT '',
    shift_start timestamptz NULL,
    shift_end timestamptz NULL,
    base numeric(14,2) NOT NULL DEFAULT 0,
    cash_sales numeric(14,2) NOT NULL DEFAULT 0,
    drawer_expenses numeric(14,2) NOT NULL DEFAULT 0,
    withdrawals numeric(14,2) NOT NULL DEFAULT 0,
    expected numeric(14,2) NOT NULL DEFAULT 0,
    counted numeric(14,2) NOT NULL DEFAULT 0,
    difference numeric(14,2) NOT NULL DEFAULT 0,
    denominations jsonb NOT NULL DEFAULT '{}'::jsonb,
    observation varchar(1000) NOT NULL DEFAULT '',
    status varchar(30) NOT NULL DEFAULT 'cerrado',
    blind boolean NOT NULL DEFAULT true,
    performed_by_name varchar(180) NOT NULL DEFAULT '',
    performed_by_kind varchar(20) NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    closed_at timestamptz NULL,
    CONSTRAINT uq_cash_count_session UNIQUE (company_id, cashier_session_id)
);
CREATE INDEX IF NOT EXISTS ix_cash_counts_company_date ON cash_counts (company_id, created_at DESC)
"""


def upgrade() -> None:
    for statement in [s.strip() for s in TABLES.split(";") if s.strip()]:
        op.execute(statement)
    op.execute(
        """
        CREATE OR REPLACE FUNCTION cx_cash_count_lock() RETURNS trigger AS $$
        BEGIN
            IF OLD.status = 'cerrado' THEN
                RAISE EXCEPTION 'cash_count_locked';
            END IF;
            IF NEW.counted <> OLD.counted OR NEW.expected <> OLD.expected OR NEW.difference <> OLD.difference THEN
                RAISE EXCEPTION 'cash_count_amounts_locked';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_cash_count_lock ON cash_counts")
    op.execute("CREATE TRIGGER trg_cash_count_lock BEFORE UPDATE ON cash_counts FOR EACH ROW EXECUTE FUNCTION cx_cash_count_lock()")

    bind = op.get_bind()
    module = bind.execute(sa.text("SELECT id FROM modules WHERE code = :code LIMIT 1"), {"code": MODULE_CODE}).mappings().first()
    module_id = module["id"] if module else str(uuid.uuid4())
    if not module:
        bind.execute(sa.text("""
            INSERT INTO modules (id, code, name, description, category, is_active, created_at, updated_at)
            VALUES (CAST(:id AS uuid), :code, 'Costos', :description, 'finance', TRUE, NOW(), NOW())
        """), {"id": module_id, "code": MODULE_CODE,
               "description": "Egresos, proveedores, cuentas por pagar, caja chica, presupuesto y arqueo de caja."})
    if not bind.execute(sa.text("SELECT id FROM companies WHERE id = CAST(:id AS uuid)"), {"id": TARGET_COMPANY_ID}).first():
        return
    if not bind.execute(sa.text("SELECT id FROM company_modules WHERE company_id = CAST(:c AS uuid) AND module_id = :m"),
                        {"c": TARGET_COMPANY_ID, "m": module_id}).first():
        bind.execute(sa.text("""
            INSERT INTO company_modules (id, company_id, module_id, enabled, settings, activated_at, created_at, updated_at)
            VALUES (CAST(:id AS uuid), CAST(:c AS uuid), :m, TRUE, CAST(:s AS jsonb), NOW(), NOW(), NOW())
        """), {"id": str(uuid.uuid4()), "c": TARGET_COMPANY_ID, "m": module_id, "s": json.dumps({})})
    bind.execute(sa.text("""
        INSERT INTO cost_centers (company_id, name, is_default) VALUES (CAST(:c AS uuid), 'Principal', true)
        ON CONFLICT (company_id, name) DO NOTHING
    """), {"c": TARGET_COMPANY_ID})


def downgrade() -> None:
    bind = op.get_bind()
    module = bind.execute(sa.text("SELECT id FROM modules WHERE code = :code LIMIT 1"), {"code": MODULE_CODE}).mappings().first()
    if module:
        bind.execute(sa.text("DELETE FROM company_modules WHERE module_id = :m"), {"m": module["id"]})
        bind.execute(sa.text("DELETE FROM modules WHERE id = :m"), {"m": module["id"]})
    op.execute("DROP TRIGGER IF EXISTS trg_cash_count_lock ON cash_counts")
    op.execute("DROP FUNCTION IF EXISTS cx_cash_count_lock()")
    for table in ("cash_counts", "budgets", "recurring_expenses", "petty_cash_moves", "expense_attachments",
                  "expense_lines", "expenses", "petty_cash_funds", "suppliers", "cost_centers"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
