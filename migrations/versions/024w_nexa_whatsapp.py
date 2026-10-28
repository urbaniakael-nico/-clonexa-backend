"""Nexa por WhatsApp (API oficial de Meta): contactos y mensajes

Revision ID: 024w_nexa_whatsapp
Revises: 024v_billing_bilingual
Create Date: 2026-10-28

Aditiva (tablas nuevas, sin company_id: son conversaciones de ventas de la
propia Clonexa, solo las ve Admin V2). Las llena el webhook de Meta
(/api/v1/nexa-wa/webhook) y n8n (/api/v1/nexa-wa/outbound).
- wa_contacts: un contacto por numero (wa_id) con lo que Nexa detecto y la etapa.
- wa_messages: cada mensaje entrante o saliente, unico por id de Meta, con su
  estado de entrega. Solo texto: fotos, audios y videos no se descargan (raw
  guarda el id de Meta), asi que no suma bytes pesados a Postgres.
"""
from __future__ import annotations

from alembic import op

revision = "024w_nexa_whatsapp"
down_revision = "024v_billing_bilingual"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS wa_contacts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            wa_id varchar(32) NOT NULL,
            profile_name varchar(200) NULL,
            language varchar(8) NULL,
            business_type varchar(120) NULL,
            city varchar(120) NULL,
            size varchar(200) NULL,
            main_pain varchar(500) NULL,
            email varchar(254) NULL,
            stage varchar(20) NOT NULL DEFAULT 'nuevo',
            stage_at timestamptz NULL,
            nexa_paused boolean NOT NULL DEFAULT false,
            consent_seen boolean NOT NULL DEFAULT false,
            first_message_at timestamptz NULL,
            last_message_at timestamptz NULL,
            last_inbound_at timestamptz NULL,
            last_preview varchar(300) NULL,
            demo_at timestamptz NULL,
            demo_link varchar(500) NULL,
            notes text NULL,
            admin_seen_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_wa_contacts_wa_id UNIQUE (wa_id),
            CONSTRAINT ck_wa_contacts_stage CHECK (stage IN ('nuevo', 'calificado', 'demo_agendada', 'pidio_persona', 'no_interesado', 'baja'))
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_wa_contacts_last ON wa_contacts (last_message_at DESC)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS wa_messages (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            meta_id varchar(200) NULL,
            contact_id uuid NOT NULL REFERENCES wa_contacts(id) ON DELETE CASCADE,
            direction varchar(3) NOT NULL,
            msg_type varchar(30) NOT NULL DEFAULT 'text',
            body text NULL,
            reply_id varchar(256) NULL,
            options jsonb NULL,
            status varchar(12) NULL,
            error varchar(500) NULL,
            raw jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            status_at timestamptz NULL,
            CONSTRAINT uq_wa_messages_meta_id UNIQUE (meta_id),
            CONSTRAINT ck_wa_messages_direction CHECK (direction IN ('in', 'out'))
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_wa_messages_contact ON wa_messages (contact_id, created_at)")


def downgrade() -> None:
    # Aditiva: bajar no borra las conversaciones.
    pass
