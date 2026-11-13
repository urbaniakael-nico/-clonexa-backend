"""NEXUS · Radar de innovacion de Clonexa (interno: sin company_id, solo Admin V2 / v2+ y n8n).

Revision ID: 025q_nexus_radar
Revises: 025p_prospect_multicanal
Create Date: 2026-11-13

Aditiva e idempotente. Filas chicas (textos cortos, URLs y fechas); nada de archivos.
- radar_temas: temas que NEXUS vigila (editables desde la consola). Semilla: 5 temas iniciales.
- radar_informes: cada informe (semanal o a pedido) con tokens, busquedas, costo estimado y estado.
- radar_ideas: ideas con fuentes (URL + fecha), impacto/esfuerzo/costo, puntaje, estado y huella para no repetir.
- radar_ignorados: chats de Telegram que escribieron a NEXUS sin ser el del dueno (solo huella SHA-256).
"""
from __future__ import annotations

from alembic import op

revision = "025q_nexus_radar"
down_revision = "025p_prospect_multicanal"
branch_labels = None
depends_on = None

TEMAS = [
    ("herramientas", "Herramientas y APIs que nos sirvan",
     "WhatsApp Cloud API, Meta, Telegram, Railway, n8n, Claude/IA, three.js/3D, pagos en Colombia: novedades, precios y cambios."),
    ("competencia", "Competencia",
     "Sistemas POS y software para restaurantes, bares, talleres y personal en campo en Colombia y LatAm: lanzamientos y precios publicados."),
    ("fondos", "Fondos y convocatorias",
     "Fondos y convocatorias para startups de software en Colombia (iNNpulsa, Fondo Emprender, MinTIC, aceleradoras), con fecha de cierre."),
    ("normas", "Leyes y normas que nos afectan",
     "DIAN (factura electrónica, nómina electrónica), Ley 2300 de 2023 (contacto comercial), protección de datos (Ley 1581)."),
    ("nichos", "Ideas por nicho",
     "Ideas para nuestros clientes y prospectos: restaurantes, bares, talleres y fábricas, empresas de campo, transporte y tiendas."),
]


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS radar_temas (
            id serial PRIMARY KEY,
            clave varchar(40) NOT NULL UNIQUE,
            nombre varchar(120) NOT NULL,
            descripcion varchar(600) NOT NULL DEFAULT '',
            activo boolean NOT NULL DEFAULT true,
            orden smallint NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    for i, (clave, nombre, desc) in enumerate(TEMAS):
        n, d = nombre.replace("'", "''"), desc.replace("'", "''")
        op.execute(f"INSERT INTO radar_temas (clave, nombre, descripcion, orden) VALUES ('{clave}', '{n}', '{d}', {i}) "
                   "ON CONFLICT (clave) DO NOTHING")
    op.execute("""
        CREATE TABLE IF NOT EXISTS radar_informes (
            id serial PRIMARY KEY,
            fecha date NOT NULL,
            tipo varchar(12) NOT NULL DEFAULT 'semanal',
            origen varchar(12) NOT NULL DEFAULT 'cron',
            tema varchar(300) NOT NULL DEFAULT '',
            estado varchar(12) NOT NULL DEFAULT 'corriendo',
            n_ideas smallint NOT NULL DEFAULT 0,
            descartadas smallint NOT NULL DEFAULT 0,
            tokens_in integer NOT NULL DEFAULT 0,
            tokens_out integer NOT NULL DEFAULT 0,
            busquedas smallint NOT NULL DEFAULT 0,
            costo_usd numeric(10, 4) NOT NULL DEFAULT 0,
            modelo varchar(40) NOT NULL DEFAULT '',
            error varchar(300) NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now(),
            terminado_at timestamptz NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_radar_informes_fecha ON radar_informes (fecha DESC, tipo)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS radar_ideas (
            id serial PRIMARY KEY,
            informe_id integer NULL REFERENCES radar_informes(id) ON DELETE SET NULL,
            titulo varchar(160) NOT NULL,
            resumen varchar(600) NOT NULL DEFAULT '',
            por_que varchar(600) NOT NULL DEFAULT '',
            categoria varchar(40) NOT NULL DEFAULT '',
            nicho varchar(30) NOT NULL DEFAULT '',
            fuentes jsonb NOT NULL DEFAULT '[]'::jsonb,
            impacto varchar(6) NOT NULL DEFAULT 'medio',
            esfuerzo varchar(6) NOT NULL DEFAULT 'medio',
            costo varchar(6) NOT NULL DEFAULT 'medio',
            costo_estimado varchar(120) NOT NULL DEFAULT '',
            puntaje smallint NOT NULL DEFAULT 0,
            fecha_limite date NULL,
            estado varchar(14) NOT NULL DEFAULT 'nueva',
            notas varchar(2000) NOT NULL DEFAULT '',
            huella varchar(64) NOT NULL,
            tg_message_id bigint NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_radar_ideas_estado ON radar_ideas (estado, puntaje DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_radar_ideas_huella ON radar_ideas (huella, created_at DESC)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS radar_ignorados (
            id bigserial PRIMARY KEY,
            chat_hash varchar(64) NOT NULL,
            tipo varchar(20) NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    pass
