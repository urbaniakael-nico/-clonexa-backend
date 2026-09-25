"""domicilios por WhatsApp: module, link sessions and payment QR

Revision ID: 021s_domicilios_whatsapp
Revises: 021r_wa_agent_access
Create Date: 2026-09-24

Module "domicilios_whatsapp" in the Admin V2 catalog (table modules), off
for every company and enabled here ONLY for ASADERO EL SOCIO. Any other
company can get it later with one click.

- whatsapp_delivery_sessions: one row per link the customer line sends
  (sha256 of the code only, phone, 30 min expiry, single use, the order it
  produced and the location pin shared in the chat) and per out-of-hours
  answer (to answer once, not to every message). Text only.
- whatsapp_delivery_payment_qr: the ONE payment QR image per company,
  through media_storage (<= 800 px / 200 KB). Payment receipts are NOT
  stored: they stay in the WhatsApp chat and the caja checks the bank.
Orders themselves live in hospitality_orders (order_type "domicilio",
metadata.delivery), so kitchen, caja, inventory and reports need nothing new.
"""
from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = "021s_domicilios_whatsapp"
down_revision = "021r_wa_agent_access"
branch_labels = None
depends_on = None

TARGET_COMPANY_ID = "7625872c-f941-4479-a27b-f8443be953c5"
MODULE_CODE = "domicilios_whatsapp"
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
# No schedule yet: the bot answers "fuera de horario" until the owner sets
# the days and hours in the portal.
DEFAULT_SETTINGS = {
    "schedule": {day: [] for day in DAYS},
    "delivery_fee": 0,
    "eta_minutes": 45,
    "driver_role": "domiciliario",
}

_SELECT_MODULE = sa.text("SELECT id FROM modules WHERE code = :code LIMIT 1")
_INSERT_MODULE = sa.text(
    """
    INSERT INTO modules (id, code, name, description, category, is_active, created_at, updated_at)
    VALUES (CAST(:id AS uuid), :code, :name, :description, :category, TRUE, NOW(), NOW())
    """
)
_SELECT_COMPANY_MODULE = sa.text(
    "SELECT id FROM company_modules WHERE company_id = :company_id AND module_id = :module_id LIMIT 1"
)
_INSERT_COMPANY_MODULE = sa.text(
    """
    INSERT INTO company_modules (id, company_id, module_id, enabled, settings, activated_at, created_at, updated_at)
    VALUES (CAST(:id AS uuid), CAST(:company_id AS uuid), :module_id, TRUE, CAST(:settings AS jsonb), NOW(), NOW(), NOW())
    """
)
_COMPANY_EXISTS = sa.text("SELECT 1 FROM companies WHERE id = CAST(:company_id AS uuid)")


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS whatsapp_delivery_sessions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            -- phone, or "<id>@lid" for chats WhatsApp delivers without one
            phone varchar(64) NOT NULL,
            kind varchar(10) NOT NULL DEFAULT 'link',
            token_hash varchar(64) NOT NULL,
            expires_at timestamptz NOT NULL,
            used_at timestamptz NULL,
            order_id uuid NULL,
            location jsonb NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_whatsapp_delivery_token ON whatsapp_delivery_sessions (token_hash)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_whatsapp_delivery_phone "
        "ON whatsapp_delivery_sessions (company_id, phone, kind, created_at DESC)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS whatsapp_delivery_payment_qr (
            company_id uuid PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
            image_bytes bytea NULL,
            image_content_type varchar(40) NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    bind = op.get_bind()
    module_row = bind.execute(_SELECT_MODULE, {"code": MODULE_CODE}).mappings().first()
    if module_row:
        module_id = module_row["id"]
    else:
        module_id = str(uuid.uuid4())
        bind.execute(_INSERT_MODULE, {
            "id": module_id,
            "code": MODULE_CODE,
            "name": "Domicilios por WhatsApp",
            "description": "El cliente escribe al WhatsApp y recibe un link a la carta para pedir a domicilio.",
            "category": "hospitality",
        })
    if not bind.execute(_COMPANY_EXISTS, {"company_id": TARGET_COMPANY_ID}).first():
        return
    if not bind.execute(_SELECT_COMPANY_MODULE, {"company_id": TARGET_COMPANY_ID, "module_id": module_id}).mappings().first():
        bind.execute(_INSERT_COMPANY_MODULE, {
            "id": str(uuid.uuid4()),
            "company_id": TARGET_COMPANY_ID,
            "module_id": module_id,
            "settings": json.dumps(DEFAULT_SETTINGS),
        })


def downgrade() -> None:
    bind = op.get_bind()
    module_row = bind.execute(_SELECT_MODULE, {"code": MODULE_CODE}).mappings().first()
    if module_row:
        bind.execute(sa.text("DELETE FROM company_modules WHERE module_id = :module_id"), {"module_id": module_row["id"]})
        bind.execute(sa.text("DELETE FROM modules WHERE id = :module_id"), {"module_id": module_row["id"]})
    op.execute("DROP TABLE IF EXISTS whatsapp_delivery_payment_qr")
    op.execute("DROP TABLE IF EXISTS whatsapp_delivery_sessions")
