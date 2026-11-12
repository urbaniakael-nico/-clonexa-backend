"""Prospeccion de Nexa ampliada y multicanal (interno de Clonexa, sin company_id; solo Admin V2 / v2+).

Revision ID: 025p_prospect_multicanal
Revises: 025o_live3d
Create Date: 2026-11-12

Aditiva e idempotente (se puede correr dos veces). Filas pequenas: textos cortos, fechas y contadores; nada de
imagenes ni archivos (el volante en PDF se arma al pedirlo y no se guarda).

- prospects: nicho, vigencia (activo / por_verificar / sin_dato) con su motivo y la ultima actividad vista,
  numero de resenas y si publica horario (datos de Google), canales publicos (jsonb: correo, Instagram, Facebook,
  TikTok, WhatsApp publicado, web y telefono, cada uno con la URL de donde salio), contadores de la cola asistida
  (Instagram/Facebook, a mano) y de visitas.
- prospect_zones.niches: que nichos se buscan en la zona ([] = los tipos de siempre: restaurantes y comidas,
  bares y talleres en Kennedy/Techo/Hipotecho). Semilla: las 19 localidades de Bogota para talleres y fabricas,
  empresas de campo, transporte, tiendas y bares.
- prospect_niche_chains: cadenas a excluir por nicho (ademas de prospect_chains, que aplica a todos).
- prospect_contacts.local_date: dia (Bogota) de la cola asistida y de la ruta de visitas.
- prospect_api_usage: llamadas a Google Places por SKU, nicho y zona por dia (limites diarios y reporte semanal).
- wa_contacts.zone y origin: la zona que dijo el contacto y de donde llego (prospecto, leads DEMO, directo).
"""
from __future__ import annotations

from alembic import op

revision = "025p_prospect_multicanal"
down_revision = "025o_live3d"
branch_labels = None
depends_on = None

NEW_NICHES = '["taller", "campo", "transporte", "tienda", "bar"]'

# slug, nombre, lat, lng, radio (m): localidades de Bogota (centro aproximado)
LOCALIDADES = [
    ("bogota-usaquen", "Usaquén", 4.70300, -74.03000, 3500),
    ("bogota-chapinero", "Chapinero", 4.64500, -74.06300, 2500),
    ("bogota-santa-fe", "Santa Fe", 4.60400, -74.06800, 2000),
    ("bogota-san-cristobal", "San Cristóbal", 4.56000, -74.08500, 2500),
    ("bogota-usme", "Usme", 4.49000, -74.11500, 3500),
    ("bogota-tunjuelito", "Tunjuelito", 4.57500, -74.13500, 2000),
    ("bogota-bosa", "Bosa", 4.61900, -74.18800, 3000),
    ("bogota-kennedy", "Kennedy (localidad)", 4.63000, -74.15000, 3500),
    ("bogota-fontibon", "Fontibón", 4.67300, -74.14500, 3000),
    ("bogota-engativa", "Engativá", 4.70700, -74.11000, 3500),
    ("bogota-suba", "Suba", 4.74000, -74.08300, 4000),
    ("bogota-barrios-unidos", "Barrios Unidos", 4.66800, -74.07300, 1800),
    ("bogota-teusaquillo", "Teusaquillo", 4.64000, -74.08500, 2000),
    ("bogota-los-martires", "Los Mártires", 4.60500, -74.09000, 1500),
    ("bogota-antonio-narino", "Antonio Nariño", 4.59000, -74.10000, 1500),
    ("bogota-puente-aranda", "Puente Aranda", 4.61500, -74.11000, 2500),
    ("bogota-la-candelaria", "La Candelaria", 4.59600, -74.07300, 800),
    ("bogota-rafael-uribe", "Rafael Uribe Uribe", 4.57000, -74.11500, 2000),
    ("bogota-ciudad-bolivar", "Ciudad Bolívar", 4.53000, -74.15000, 3500),
]

NICHE_CHAINS = {
    "tienda": ["Surtimax", "Super Inter", "Colsubsidio", "Jumbo", "Metro", "Makro", "Alkosto", "PriceSmart", "Dollarcity",
               "Tiendas Euro", "Mercacentro", "Megatiendas", "Cooratiendas", "Farmatodo", "Cruz Verde", "La Rebaja", "Locatel"],
    "transporte": ["Servientrega", "Coordinadora", "Interrapidísimo", "Inter Rapidísimo", "Envía", "TCC", "Deprisa", "DHL",
                   "FedEx", "Rappi", "4-72", "Saferbo", "Domina", "Mensajeros Urbanos", "Picap", "Uber", "DiDi", "Cabify"],
    "campo": ["Claro", "Movistar", "Tigo", "ETB", "Enel", "Codensa", "Vanti", "Securitas", "Prosegur", "G4S", "Seguridad Atlas",
              "Brinks", "ISS", "Casalimpia", "Amarilo", "Constructora Bolívar", "Cusezar", "Colpatria", "Conconcreto",
              "Homecenter", "Sodimac", "Easy"],
    "taller": ["Offcorss", "Gef", "Punto Blanco", "Leonisa", "Pat Primo", "Tennis", "Vélez", "Bosi", "Ela", "Zara", "H&M",
               "Adidas", "Nike", "Falabella"],
    "bar": ["Andrés DC", "La Villa", "Theatron", "El Coq", "Armando Records"],
}


def upgrade() -> None:
    cols = [
        ("niche", "varchar(20) NOT NULL DEFAULT ''"),
        ("vigencia", "varchar(16) NOT NULL DEFAULT 'sin_dato'"),
        ("vigencia_reason", "varchar(160) NOT NULL DEFAULT ''"),
        ("vigencia_at", "timestamptz NULL"),
        ("last_activity_at", "timestamptz NULL"),
        ("rating_count", "integer NULL"),
        ("has_hours", "boolean NULL"),
        ("channels", "jsonb NOT NULL DEFAULT '{}'::jsonb"),
        ("assisted_count", "smallint NOT NULL DEFAULT 0"),
        ("assisted_first_at", "timestamptz NULL"),
        ("assisted_followup_at", "timestamptz NULL"),
        ("visit_count", "smallint NOT NULL DEFAULT 0"),
        ("last_visit_at", "timestamptz NULL"),
    ]
    for name, ddl in cols:
        op.execute(f"ALTER TABLE prospects ADD COLUMN IF NOT EXISTS {name} {ddl}")
    op.execute("""
        UPDATE prospects SET niche = CASE
            WHEN business_type IN ('restaurante', 'comidas_rapidas', 'cafe', 'panaderia') THEN 'restaurante'
            WHEN business_type = 'bar' THEN 'bar'
            WHEN business_type IN ('taller', 'fabrica') THEN 'taller'
            ELSE 'restaurante' END
        WHERE niche = ''
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_prospects_niche ON prospects (niche, zone_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_prospects_vigencia ON prospects (vigencia)")

    op.execute("ALTER TABLE prospect_zones ADD COLUMN IF NOT EXISTS niches jsonb NOT NULL DEFAULT '[]'::jsonb")
    for i, (slug, name, lat, lng, radius) in enumerate(LOCALIDADES):
        safe = name.replace("'", "''")
        op.execute(
            "INSERT INTO prospect_zones (slug, name, group_name, center_lat, center_lng, radius_m, sort, niches) "
            f"VALUES ('{slug}', '{safe}', 'Bogotá', {lat}, {lng}, {radius}, {100 + i}, '{NEW_NICHES}'::jsonb) "
            "ON CONFLICT (slug) DO NOTHING"
        )

    op.execute("""
        CREATE TABLE IF NOT EXISTS prospect_niche_chains (
            id serial PRIMARY KEY,
            niche varchar(20) NOT NULL,
            name varchar(120) NOT NULL,
            active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_prospect_niche_chains UNIQUE (niche, name)
        )
    """)
    for niche, names in NICHE_CHAINS.items():
        for n in names:
            safe = n.replace("'", "''")
            op.execute(f"INSERT INTO prospect_niche_chains (niche, name) VALUES ('{niche}', '{safe}') ON CONFLICT (niche, name) DO NOTHING")

    op.execute("ALTER TABLE prospect_contacts ADD COLUMN IF NOT EXISTS local_date date NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_prospect_contacts_day ON prospect_contacts (local_date, channel) WHERE local_date IS NOT NULL")

    op.execute("""
        CREATE TABLE IF NOT EXISTS prospect_api_usage (
            day date NOT NULL,
            kind varchar(24) NOT NULL,
            niche varchar(20) NOT NULL DEFAULT '',
            zone_id integer NOT NULL DEFAULT 0,
            calls integer NOT NULL DEFAULT 0,
            units bigint NOT NULL DEFAULT 0,
            PRIMARY KEY (day, kind, niche, zone_id)
        )
    """)

    for column, ddl in (("zone", "varchar(120) NULL"), ("origin", "varchar(30) NULL")):
        op.execute(f"""
            DO $$ BEGIN
                IF to_regclass('public.wa_contacts') IS NOT NULL THEN
                    ALTER TABLE wa_contacts ADD COLUMN IF NOT EXISTS {column} {ddl};
                END IF;
            END $$;
        """)


def downgrade() -> None:
    # Aditiva: nada se borra al bajar (la lista de exclusion y el registro de contactos deben sobrevivir).
    pass
