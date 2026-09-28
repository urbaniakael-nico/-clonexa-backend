"""gastos fijos en Inventario, arqueo al panel de caja y desmonte de Costos (049M)

Revision ID: 022c_fixed_expenses
Revises: 022b_inventory_size
Create Date: 2026-09-28

1. Gastos fijos (TODAS las empresas con Inventario):
   fixed_expense_concepts (conceptos propios), fixed_expenses (concepto,
   mes, valor, observacion) y fixed_expense_receipts (recibo comprimido por
   media_storage).
2. Datos del modulo Costos (hoy solo ASADERO), sin perder nada:
   - egresos que son gasto fijo (arriendo, servicios, internet, aseo,
     mantenimiento, seguros, impuestos, emergencia, otros; no rechazados) ->
     fixed_expenses del mes de su fecha, con su recibo (el recibo se MUEVE,
     no se duplica: la base va por la mitad). Las compras de insumos y los
     retiros del dueño NO son gastos fijos (ya cuentan en el costo de la
     mercancia / no son gasto): se quedan en la tabla expenses.
   - arqueos: siguen en cash_counts (misma tabla, mismo candado). Donde
     Costos estaba activo se enciende el arqueo del panel de caja
     (waiter_ordering.settings.cash_count) con la misma base del cajon.
   - el modulo "costos" sale del catalogo de Admin V2 y de todo el codigo.
     Ninguna de sus tablas se borra (ni las vacias): quedan en la base, fuera
     de toda pantalla, y el log dice cuantas filas tiene cada una para
     decidir despues si se borran.
Cada paso imprime lo que encontro y lo que movio (queda en el log del
despliegue).
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "022c_fixed_expenses"
down_revision = "022b_inventory_size"
branch_labels = None
depends_on = None

# categoria de Costos -> (concepto, etiqueta, grupo, es_propio)
CATEGORY_MAP = {
    "arriendo": ("arriendo", "Arriendo", "arriendo", False),
    "internet": ("internet", "Internet", "servicios", False),
    "aseo": ("aseo", "Aseo", "otros", False),
    "mantenimiento": ("mantenimiento", "Mantenimiento", "otros", False),
    "servicios": ("servicios_publicos", "Servicios públicos", "servicios", True),
    "seguros": ("seguros", "Seguros", "otros", True),
    "impuestos": ("impuestos", "Impuestos", "otros", True),
    "emergencia": ("compra_emergencia", "Compra de emergencia", "otros", True),
    "otros": ("otros", "Otros", "otros", True),
}
NOT_FIXED = ("compras", "retiro_dueno")
# tablas de Costos que ya no usa ningun codigo (se informan, no se borran);
# cash_counts (arqueos) sigue en uso por el panel de caja
LEGACY_TABLES = ["expenses", "expense_lines", "expense_attachments", "suppliers", "petty_cash_funds", "petty_cash_moves",
                 "recurring_expenses", "budgets", "cost_centers"]

TABLES = """
CREATE TABLE IF NOT EXISTS fixed_expense_concepts (
    company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    key varchar(60) NOT NULL,
    label varchar(80) NOT NULL,
    group_key varchar(20) NOT NULL DEFAULT 'otros',
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, key)
);
CREATE TABLE IF NOT EXISTS fixed_expenses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    concept_key varchar(60) NOT NULL,
    concept_label varchar(80) NOT NULL,
    group_key varchar(20) NOT NULL DEFAULT 'otros',
    month date NOT NULL,
    amount numeric(14,2) NOT NULL,
    observation varchar(1000) NOT NULL DEFAULT '',
    source varchar(20) NOT NULL DEFAULT 'manual',
    source_ref uuid NULL,
    created_by_name varchar(180) NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_fixed_expenses_company_month ON fixed_expenses (company_id, month);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fixed_expenses_source ON fixed_expenses (company_id, source, source_ref) WHERE source_ref IS NOT NULL;
CREATE TABLE IF NOT EXISTS fixed_expense_receipts (
    company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    expense_id uuid NOT NULL REFERENCES fixed_expenses(id) ON DELETE CASCADE,
    image_bytes bytea NULL,
    image_content_type varchar(60) NULL,
    size_bytes integer NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, expense_id)
)
"""


def _exists(bind, table: str) -> bool:
    return bool(bind.execute(sa.text("SELECT to_regclass(:t) IS NOT NULL"), {"t": f"public.{table}"}).scalar())


def _count(bind, table: str) -> int:
    return int(bind.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar() or 0)


def upgrade() -> None:
    for statement in [s.strip() for s in TABLES.split(";") if s.strip()]:
        op.execute(statement)
    bind = op.get_bind()
    report: dict = {}

    # --- 2a. egresos de Costos -> gastos fijos
    if _exists(bind, "expenses"):
        report["egresos_encontrados"] = _count(bind, "expenses")
        rows = bind.execute(sa.text("""
            SELECT id, company_id, category, expense_date, total, description, supplier_name, status, created_by_name
            FROM expenses WHERE status <> 'rechazado' AND category NOT IN ('compras', 'retiro_dueno')
        """)).mappings().all()
        moved = 0
        for row in rows:
            key, label, group, custom = CATEGORY_MAP.get(row["category"], CATEGORY_MAP["otros"])
            if custom:
                bind.execute(sa.text("""
                    INSERT INTO fixed_expense_concepts (company_id, key, label, group_key) VALUES (:c, :key, :label, :group)
                    ON CONFLICT (company_id, key) DO NOTHING
                """), {"c": row["company_id"], "key": key, "label": label, "group": group})
            notes = " · ".join(p for p in [row["description"] or "", row["supplier_name"] or ""] if p.strip())
            tag = "migrado de Costos" + (", estaba pendiente de aprobación" if row["status"] == "pendiente" else "")
            result = bind.execute(sa.text("""
                INSERT INTO fixed_expenses (company_id, concept_key, concept_label, group_key, month, amount, observation,
                                            source, source_ref, created_by_name)
                VALUES (:c, :key, :label, :group, date_trunc('month', CAST(:day AS date))::date, :amount, :obs,
                        'costos', :ref, :by)
                ON CONFLICT (company_id, source, source_ref) WHERE source_ref IS NOT NULL DO NOTHING
            """), {"c": row["company_id"], "key": key, "label": label, "group": group, "day": row["expense_date"],
                   "amount": row["total"], "obs": f"{notes} ({tag})".strip()[:1000], "ref": row["id"],
                   "by": row["created_by_name"] or ""})
            moved += result.rowcount or 0
        report["egresos_pasados_a_gastos_fijos"] = moved
        report["egresos_que_se_quedan_(compras/retiros/rechazados)"] = report["egresos_encontrados"] - len(rows)

        if _exists(bind, "expense_attachments"):
            result = bind.execute(sa.text("""
                INSERT INTO fixed_expense_receipts (company_id, expense_id, image_bytes, image_content_type, size_bytes)
                SELECT a.company_id, f.id, a.image_bytes, a.image_content_type, COALESCE(octet_length(a.image_bytes), 0)
                FROM expense_attachments a
                JOIN fixed_expenses f ON f.company_id = a.company_id AND f.source = 'costos' AND f.source_ref = a.expense_id
                WHERE a.image_bytes IS NOT NULL
                ON CONFLICT (company_id, expense_id) DO NOTHING
            """))
            report["recibos_movidos"] = result.rowcount or 0
            # movido, no duplicado: el recibo ya vive en fixed_expense_receipts
            bind.execute(sa.text("""
                UPDATE expense_attachments a SET image_bytes = NULL, size_bytes = 0
                FROM fixed_expenses f
                WHERE f.company_id = a.company_id AND f.source = 'costos' AND f.source_ref = a.expense_id
                  AND EXISTS (SELECT 1 FROM fixed_expense_receipts r WHERE r.company_id = f.company_id AND r.expense_id = f.id
                              AND r.image_bytes IS NOT NULL)
            """))

    # --- 2b. arqueo al panel de caja donde Costos estaba activo
    if _exists(bind, "cash_counts"):
        report["arqueos_conservados_en_cash_counts"] = _count(bind, "cash_counts")
    costos = bind.execute(sa.text("SELECT id FROM modules WHERE LOWER(code) = 'costos' LIMIT 1")).mappings().first()
    enabled_for = []
    if costos:
        rows = bind.execute(sa.text("""
            SELECT company_id, settings FROM company_modules WHERE module_id = :m AND enabled IS TRUE
        """), {"m": costos["id"]}).mappings().all()
        for row in rows:
            settings = row["settings"] or {}
            if isinstance(settings, str):
                settings = json.loads(settings or "{}")
            patch = {"cash_count": True, "cash_count_drawer_base": float(settings.get("drawer_base") or 0),
                     "costos_legacy_settings": settings}
            result = bind.execute(sa.text("""
                UPDATE company_modules SET settings = COALESCE(settings, '{}'::jsonb) || CAST(:s AS jsonb), updated_at = now()
                WHERE company_id = :c AND module_id = (SELECT id FROM modules WHERE LOWER(code) = 'waiter_ordering' LIMIT 1)
            """), {"s": json.dumps(patch), "c": row["company_id"]})
            if result.rowcount:
                enabled_for.append(str(row["company_id"]))
        # --- 2c. Costos sale del catalogo de Admin V2
        report["empresas_con_costos"] = len(rows)
        bind.execute(sa.text("DELETE FROM company_modules WHERE module_id = :m"), {"m": costos["id"]})
        bind.execute(sa.text("DELETE FROM modules WHERE id = :m"), {"m": costos["id"]})
    report["arqueo_en_caja_activado_para"] = enabled_for

    # --- 2d. tablas de Costos: ninguna se borra; se informa cuantas filas
    # tiene cada una (vacias o con datos) para decidir despues.
    legacy = {table: _count(bind, table) for table in LEGACY_TABLES if _exists(bind, table)}
    report["tablas_de_costos_conservadas_(filas)"] = legacy
    report["tablas_de_costos_vacias"] = [table for table, rows in legacy.items() if rows == 0]
    print(f"[022c_fixed_expenses] {json.dumps(report, ensure_ascii=False, default=str)}")


def downgrade() -> None:
    # Los gastos fijos se conservan en sus tablas; volver a Costos requiere
    # la migracion 021x (el modulo se recrea alli). No se borra nada aqui.
    pass
