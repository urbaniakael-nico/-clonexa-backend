"""facturacion de Clonexa a sus clientes (contratos, cuotas, pagos, comprobantes)

Revision ID: 024d_billing
Revises: 024c_brand_share_links
Create Date: 2026-10-05

- billing_contract_types: lista editable de tipos de contrato.
- billing_contracts: un contrato por empresa (inicio, minimo de meses,
  moneda, ventana de pago dia desde/hasta, estado, notas).
- billing_price_tiers: tramos de precio (desde el mes N hasta el mes M).
- billing_installments: cuotas mes a mes (se generan solas).
- billing_payments: pagos registrados (por validar, validado, anulado).
- billing_receipts: comprobantes con numero consecutivo de una SECUENCIA de
  Postgres: nunca se repite ni se reutiliza (ni con validaciones al mismo
  tiempo, ni si se anula, ni si se borra la empresa).
- billing_contract_files: versiones del contrato en PDF (bytes en el bucket,
  zona privada; aqui solo el indice).
No se guardan numeros de tarjeta ni de cuentas bancarias.
"""
from __future__ import annotations

from alembic import op

revision = "024d_billing"
down_revision = "024c_brand_share_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS billing_contract_types (
            code varchar(40) PRIMARY KEY,
            label varchar(80) NOT NULL,
            active boolean NOT NULL DEFAULT true,
            sort integer NOT NULL DEFAULT 100
        )
        """
    )
    op.execute(
        """
        INSERT INTO billing_contract_types (code, label, sort) VALUES
            ('mensual', 'Mensual', 1), ('minimo', 'Mínimo de meses', 2), ('anual', 'Anual', 3), ('prueba', 'Prueba', 4)
        ON CONFLICT (code) DO NOTHING
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS billing_contracts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL UNIQUE REFERENCES companies(id) ON DELETE CASCADE,
            contract_type varchar(40) NOT NULL REFERENCES billing_contract_types(code),
            start_date date NOT NULL,
            min_months integer NOT NULL DEFAULT 0 CHECK (min_months >= 0 AND min_months <= 120),
            currency varchar(3) NOT NULL DEFAULT 'COP',
            pay_day_from smallint NOT NULL CHECK (pay_day_from BETWEEN 1 AND 28),
            pay_day_to smallint NOT NULL CHECK (pay_day_to BETWEEN 1 AND 28),
            notes text NOT NULL DEFAULT '',
            status varchar(12) NOT NULL DEFAULT 'vigente' CHECK (status IN ('vigente', 'pausado', 'terminado')),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CHECK (pay_day_to >= pay_day_from)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS billing_price_tiers (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            contract_id uuid NOT NULL REFERENCES billing_contracts(id) ON DELETE CASCADE,
            month_from integer NOT NULL CHECK (month_from >= 1),
            month_to integer NULL CHECK (month_to IS NULL OR month_to >= month_from),
            amount numeric(14, 2) NOT NULL CHECK (amount >= 0)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS billing_installments (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            contract_id uuid NOT NULL REFERENCES billing_contracts(id) ON DELETE CASCADE,
            seq integer NOT NULL,
            period date NOT NULL,
            amount numeric(14, 2) NOT NULL,
            due_from date NOT NULL,
            due_date date NOT NULL,
            status varchar(16) NOT NULL DEFAULT 'pendiente',
            voided boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (contract_id, seq)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_billing_installments_company ON billing_installments (company_id, period)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS billing_payments (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            installment_id uuid NOT NULL REFERENCES billing_installments(id) ON DELETE CASCADE,
            amount numeric(14, 2) NOT NULL CHECK (amount > 0),
            paid_on date NOT NULL,
            method varchar(20) NOT NULL,
            reference varchar(80) NOT NULL DEFAULT '',
            note text NOT NULL DEFAULT '',
            status varchar(12) NOT NULL DEFAULT 'por_validar' CHECK (status IN ('por_validar', 'validado', 'anulado')),
            created_by varchar(200) NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now(),
            validated_by varchar(200) NULL,
            validated_at timestamptz NULL,
            void_reason text NULL,
            voided_by varchar(200) NULL,
            voided_at timestamptz NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_billing_payments_company ON billing_payments (company_id, created_at DESC)")
    op.execute("CREATE SEQUENCE IF NOT EXISTS billing_receipt_number_seq START 1")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS billing_receipts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            number bigint NOT NULL UNIQUE DEFAULT nextval('billing_receipt_number_seq'),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            payment_id uuid NOT NULL UNIQUE REFERENCES billing_payments(id) ON DELETE CASCADE,
            status varchar(10) NOT NULL DEFAULT 'vigente' CHECK (status IN ('vigente', 'anulado')),
            storage_key text NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            voided_at timestamptz NULL,
            void_reason text NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS billing_contract_files (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            version integer NOT NULL,
            size_bytes integer NOT NULL,
            original_name varchar(200) NOT NULL DEFAULT '',
            is_current boolean NOT NULL DEFAULT true,
            created_by varchar(200) NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (company_id, version)
        )
        """
    )


def downgrade() -> None:
    for table in ("billing_contract_files", "billing_receipts", "billing_payments", "billing_installments", "billing_price_tiers",
                  "billing_contracts", "billing_contract_types"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
    op.execute("DROP SEQUENCE IF EXISTS billing_receipt_number_seq")
