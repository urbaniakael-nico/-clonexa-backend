"""Prospeccion por ubicacion de Nexa (interno de Clonexa, sin company_id) + ubicacion de visitas

Revision ID: 025i_prospecting
Revises: 025h_wa_group_reports
Create Date: 2026-11-10

Solo aditiva e idempotente. Filas pequenas (textos cortos, coordenadas, fechas y estados); nada de
imagenes ni archivos. No es una funcion de ninguna empresa cliente: lo ve solo Admin V2 / v2+.

- prospect_zones: zonas de prospeccion (circulo o poligono). Semilla: Kennedy (Kennedy Central,
  Castilla, Americas, Timiza), Techo e Hipotecho en Bogota.
- prospect_chains: lista editable de cadenas que NO se prospectan.
- prospects: un negocio por place_id de Google (sin duplicados). Datos de Google se refrescan cada
  30 dias (place_refreshed_at); el correo solo si el negocio lo publica en su web (email_source_url).
- prospect_zone_scans: por zona y tipo, cuando se busco y el token de la pagina siguiente.
- prospect_batches: el lote diario de correos que el dueno aprueba por Telegram.
- prospect_contacts: registro de contactos (correo inicial, seguimiento, respuesta, baja, apertura de
  la landing, WhatsApp). Los correos del lote se guardan aqui con su estado.
- prospect_exclusions: lista de exclusion permanente (correo, dominio o place_id).
- prospect_settings: remitente, firma y limites (una fila).
- landing_visit_events: ubicacion aproximada por IP (lat/lng de la ciudad), hash de la IP y el
  prospecto cuando la visita trae su codigo. La tabla la crea el endpoint; aqui solo se agregan
  columnas si ya existe.
"""
from __future__ import annotations

from alembic import op

revision = "025i_prospecting"
down_revision = "025h_wa_group_reports"
branch_labels = None
depends_on = None

ZONES = [
    # slug, nombre, grupo, lat, lng, radio (m)
    ("kennedy-central", "Kennedy Central", "Kennedy", 4.62171, -74.15262, 750),
    ("castilla", "Castilla", "Kennedy", 4.63950, -74.14014, 750),
    ("americas", "Américas", "Kennedy", 4.62419, -74.14208, 650),
    ("timiza", "Timiza", "Kennedy", 4.61551, -74.15409, 700),
    ("techo", "Techo", "Techo", 4.62563, -74.13662, 650),
    ("hipotecho", "Hipotecho", "Hipotecho", 4.61850, -74.13100, 650),
]

CHAINS = [
    "El Corral", "Corral Gourmet", "Frisby", "KFC", "McDonald's", "Crepes & Waffles", "Juan Valdez", "Presto",
    "Subway", "Domino's", "Burger King", "Jeno's Pizza", "Papa John's", "Pizza Hut", "Little Caesars",
    "Starbucks", "Tostao", "OMA", "Dunkin", "Kokoriko", "Sandwich Qbano", "Archie's", "PPC", "Hornitos",
    "Home Burgers", "Mimo's", "Sr. Wok", "Andrés Carne de Res", "Bogotá Beer Company", "BBC",
    "Pan Pa' Ya", "Ventolini", "Dogger", "Buffalo Wings", "Popsy", "Brasa Roja", "Cosechas", "Taco Bell",
    "Carl's Jr", "Wendy's", "Tierra Querida", "Café Quindío", "La Brasa Roja", "Mister Pollo", "Frutto Fresh",
    "Hamburguesas El Corral", "Qbano", "Pollos Mario", "Piqueteadero Doña Segunda", "D1", "Ara", "Éxito",
    "Carulla", "Olímpica", "Oxxo", "Justo & Bueno", "Isimo", "Arturo Calle", "Studio F", "Koaj", "Totto",
]


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS prospect_zones (
            id serial PRIMARY KEY,
            slug varchar(60) NOT NULL UNIQUE,
            name varchar(120) NOT NULL,
            group_name varchar(120) NOT NULL DEFAULT '',
            city varchar(80) NOT NULL DEFAULT 'Bogotá',
            kind varchar(10) NOT NULL DEFAULT 'circle',
            center_lat double precision NOT NULL,
            center_lng double precision NOT NULL,
            radius_m integer NOT NULL DEFAULT 700,
            polygon jsonb NULL,
            active boolean NOT NULL DEFAULT true,
            sort smallint NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    for i, (slug, name, group, lat, lng, radius) in enumerate(ZONES):
        op.execute(
            "INSERT INTO prospect_zones (slug, name, group_name, center_lat, center_lng, radius_m, sort) "
            f"VALUES ('{slug}', '{name}', '{group}', {lat}, {lng}, {radius}, {i}) ON CONFLICT (slug) DO NOTHING"
        )

    op.execute("""
        CREATE TABLE IF NOT EXISTS prospect_chains (
            id serial PRIMARY KEY,
            name varchar(120) NOT NULL UNIQUE,
            active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    for name in CHAINS:
        safe = name.replace("'", "''")
        op.execute(f"INSERT INTO prospect_chains (name) VALUES ('{safe}') ON CONFLICT (name) DO NOTHING")

    op.execute("""
        CREATE TABLE IF NOT EXISTS prospects (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            place_id varchar(300) NOT NULL UNIQUE,
            code varchar(12) NOT NULL UNIQUE,
            unsub_token varchar(64) NOT NULL UNIQUE,
            name varchar(200) NOT NULL,
            business_type varchar(30) NOT NULL,
            primary_type varchar(80) NOT NULL DEFAULT '',
            google_types jsonb NOT NULL DEFAULT '[]'::jsonb,
            address varchar(300) NOT NULL DEFAULT '',
            locality varchar(120) NOT NULL DEFAULT '',
            neighborhood varchar(120) NOT NULL DEFAULT '',
            zone_id integer NULL REFERENCES prospect_zones(id) ON DELETE SET NULL,
            lat double precision NULL,
            lng double precision NULL,
            phone varchar(60) NOT NULL DEFAULT '',
            website varchar(500) NOT NULL DEFAULT '',
            email varchar(200) NOT NULL DEFAULT '',
            email_source_url varchar(500) NOT NULL DEFAULT '',
            email_status varchar(20) NOT NULL DEFAULT 'pendiente',
            email_checked_at timestamptz NULL,
            business_status varchar(40) NOT NULL DEFAULT '',
            status varchar(20) NOT NULL DEFAULT 'nuevo',
            is_test boolean NOT NULL DEFAULT false,
            contact_count smallint NOT NULL DEFAULT 0,
            first_contacted_at timestamptz NULL,
            last_contacted_at timestamptz NULL,
            followup_sent_at timestamptz NULL,
            opened_at timestamptz NULL,
            replied_at timestamptz NULL,
            demo_at timestamptz NULL,
            client_at timestamptz NULL,
            unsubscribed_at timestamptz NULL,
            wa_consent_at timestamptz NULL,
            wa_consent_source varchar(40) NOT NULL DEFAULT '',
            wa_contact_id varchar(64) NOT NULL DEFAULT '',
            place_refreshed_at timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_prospects_status ON prospects (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_prospects_zone ON prospects (zone_id, business_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_prospects_email ON prospects (lower(email)) WHERE email <> ''")
    op.execute("CREATE INDEX IF NOT EXISTS ix_prospects_refresh ON prospects (place_refreshed_at)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS prospect_zone_scans (
            zone_id integer NOT NULL REFERENCES prospect_zones(id) ON DELETE CASCADE,
            business_type varchar(30) NOT NULL,
            last_scanned_at timestamptz NULL,
            next_page_token text NOT NULL DEFAULT '',
            pages smallint NOT NULL DEFAULT 0,
            last_found smallint NOT NULL DEFAULT 0,
            last_new smallint NOT NULL DEFAULT 0,
            PRIMARY KEY (zone_id, business_type)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS prospect_batches (
            id serial PRIMARY KEY,
            local_date date NOT NULL UNIQUE,
            status varchar(20) NOT NULL DEFAULT 'pendiente',
            item_count smallint NOT NULL DEFAULT 0,
            preview_token varchar(64) NOT NULL,
            approved_at timestamptz NULL,
            decided_by varchar(40) NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS prospect_contacts (
            id bigserial PRIMARY KEY,
            prospect_id uuid NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
            channel varchar(16) NOT NULL,
            kind varchar(24) NOT NULL,
            status varchar(16) NOT NULL DEFAULT 'registrado',
            batch_id integer NULL REFERENCES prospect_batches(id) ON DELETE SET NULL,
            to_email varchar(200) NOT NULL DEFAULT '',
            subject varchar(300) NOT NULL DEFAULT '',
            gmail_message_id varchar(120) NOT NULL DEFAULT '',
            gmail_thread_id varchar(120) NOT NULL DEFAULT '',
            claimed_at timestamptz NULL,
            sent_at timestamptz NULL,
            detail jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_prospect_contacts_prospect ON prospect_contacts (prospect_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_prospect_contacts_batch ON prospect_contacts (batch_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_prospect_contacts_thread ON prospect_contacts (gmail_thread_id) WHERE gmail_thread_id <> ''")
    op.execute("CREATE INDEX IF NOT EXISTS ix_prospect_contacts_sent ON prospect_contacts (sent_at DESC) WHERE sent_at IS NOT NULL")

    op.execute("""
        CREATE TABLE IF NOT EXISTS prospect_exclusions (
            id serial PRIMARY KEY,
            kind varchar(10) NOT NULL,
            value varchar(300) NOT NULL,
            reason varchar(40) NOT NULL DEFAULT 'baja',
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_prospect_exclusions UNIQUE (kind, value)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS prospect_settings (
            id smallint PRIMARY KEY DEFAULT 1,
            config jsonb NOT NULL DEFAULT '{}'::jsonb,
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_prospect_settings_one CHECK (id = 1)
        )
    """)
    op.execute("INSERT INTO prospect_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING")

    # Visitas de la landing: la tabla la crea el endpoint (CREATE IF NOT EXISTS); si ya existe,
    # se agregan las columnas nuevas. Si no existe, el endpoint las crea con la tabla.
    for column, ddl in (
        ("ip_hash", "varchar(64) NOT NULL DEFAULT ''"),
        ("lat", "double precision NULL"),
        ("lng", "double precision NULL"),
        ("geo_source", "varchar(20) NOT NULL DEFAULT ''"),
        ("prospect_id", "uuid NULL"),
    ):
        op.execute(f"""
            DO $$ BEGIN
                IF to_regclass('public.landing_visit_events') IS NOT NULL THEN
                    ALTER TABLE landing_visit_events ADD COLUMN IF NOT EXISTS {column} {ddl};
                END IF;
            END $$;
        """)


def downgrade() -> None:
    # Aditiva: no se borra nada al bajar (los datos de prospeccion y la lista de exclusion
    # deben sobrevivir; la exclusion es permanente por ley).
    pass
