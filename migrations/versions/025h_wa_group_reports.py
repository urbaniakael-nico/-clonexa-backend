"""Avisos automaticos por WhatsApp a grupos, supervisor y duenos (whatsapp_group_reports, 072A)

Revision ID: 025h_wa_group_reports
Revises: 025g_ref_initial_cut
Create Date: 2026-11-09

Solo aditiva e idempotente; filas pequenas (textos cortos, fechas y estados; nada de imagenes ni
archivos: los PDF/Excel se generan al momento y las fotos de timesheet van a Google Drive). No toca
ninguna fila existente.

- wa_report_config: la configuracion editable de UNA empresa (destinatarios, horas, modo prueba).
- wa_report_notices: un aviso por (empresa, clave). La clave unica (tipo + operacion + fecha +
  franja) es lo que impide duplicados al reiniciar o redesplegar.
- wa_report_deliveries: un envio por destino (historial de avisos: fecha, tipo, destino, estado,
  intentos). Se purgan a los 120 dias.
- wa_timesheet_receipts: fotos de timesheet que n8n guardo en Drive (para no mandar el
  recordatorio de las 9:00).
- wa_autoreplies: la respuesta automatica sale una vez al dia por persona.
"""
from __future__ import annotations

from alembic import op

revision = "025h_wa_group_reports"
down_revision = "025g_ref_initial_cut"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS wa_report_config (
            company_id uuid PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
            config jsonb NOT NULL DEFAULT '{}'::jsonb,
            updated_by varchar(200) NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS wa_report_notices (
            id bigserial PRIMARY KEY,
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            dedupe_key varchar(160) NOT NULL,
            kind varchar(40) NOT NULL,
            location_id uuid NULL,
            local_date date NULL,
            slot smallint NOT NULL DEFAULT 0,
            test boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_wa_report_notices_key UNIQUE (company_id, dedupe_key)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_wa_report_notices_company_date ON wa_report_notices (company_id, local_date)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS wa_report_deliveries (
            id bigserial PRIMARY KEY,
            notice_id bigint NOT NULL REFERENCES wa_report_notices(id) ON DELETE CASCADE,
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            kind varchar(40) NOT NULL,
            channel varchar(16) NOT NULL,
            destination varchar(200) NOT NULL,
            target varchar(400) NOT NULL DEFAULT '',
            subject varchar(300) NULL,
            body text NOT NULL DEFAULT '',
            attachments jsonb NOT NULL DEFAULT '[]'::jsonb,
            test boolean NOT NULL DEFAULT false,
            status varchar(16) NOT NULL DEFAULT 'pending',
            attempts smallint NOT NULL DEFAULT 0,
            next_attempt_at timestamptz NOT NULL DEFAULT now(),
            last_error varchar(300) NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            sent_at timestamptz NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_wa_report_deliveries_due ON wa_report_deliveries (status, next_attempt_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_wa_report_deliveries_company ON wa_report_deliveries (company_id, created_at DESC)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS wa_timesheet_receipts (
            id bigserial PRIMARY KEY,
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id uuid NULL,
            source varchar(16) NOT NULL,
            sender varchar(200) NULL,
            file_name varchar(300) NULL,
            drive_url varchar(600) NULL,
            received_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_wa_timesheet_receipts_company ON wa_timesheet_receipts (company_id, received_at DESC)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS wa_autoreplies (
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            sender varchar(80) NOT NULL,
            local_date date NOT NULL,
            PRIMARY KEY (company_id, sender, local_date)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS wa_autoreplies")
    op.execute("DROP TABLE IF EXISTS wa_timesheet_receipts")
    op.execute("DROP TABLE IF EXISTS wa_report_deliveries")
    op.execute("DROP TABLE IF EXISTS wa_report_notices")
    op.execute("DROP TABLE IF EXISTS wa_report_config")
