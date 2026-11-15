"""modo constructor fase 1: planos con versiones, catalogo de objetos e interruptores del piso

Revision ID: 025u_constructor
Revises: 025t_cola_de_hoy
Create Date: 2026-11-15

Aditiva e idempotente.
- constructor_planos: plano (JSON en metros, docs/constructor/PLANO.md) por empresa; una fila 'borrador'
  (autoguardado) y una 'publicado' por version. Siempre con company_id.
- constructor_catalogo: catalogo de objetos (sin bytes pesados: los GLB y miniaturas viven en el bucket privado o
  en el repo). Se siembra con app/services/constructor_catalogo.json (123 objetos).
- oficina_pisos.usa_plano (interruptor por empresa, APAGADO para todas: el plano publicado dibuja el piso solo si
  esta encendido) y oficina_pisos.estilo_escena ('humano' por defecto | 'caricatura').
"""
from __future__ import annotations

import json
from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "025u_constructor"
down_revision = "025t_cola_de_hoy"
branch_labels = None
depends_on = None

CATALOG = Path(__file__).resolve().parents[2] / "app" / "services" / "constructor_catalogo.json"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS constructor_planos (
            id UUID PRIMARY KEY,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            version INTEGER NOT NULL DEFAULT 1,
            estado TEXT NOT NULL CHECK (estado IN ('borrador', 'publicado')),
            plano JSONB NOT NULL,
            creado_por TEXT NULL,
            nota TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_constructor_borrador ON constructor_planos (company_id) WHERE estado = 'borrador'")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_constructor_version ON constructor_planos (company_id, version) WHERE estado = 'publicado'")
    op.execute("""
        CREATE TABLE IF NOT EXISTS constructor_catalogo (
            id TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            categoria TEXT NOT NULL,
            zonas JSONB NOT NULL DEFAULT '[]'::jsonb,
            origen TEXT NOT NULL DEFAULT 'clonexa',
            forma TEXT NOT NULL DEFAULT 'glb',
            archivo TEXT NULL,
            miniatura TEXT NULL,
            medidas JSONB NOT NULL DEFAULT '{}'::jsonb,
            variantes JSONB NOT NULL DEFAULT '[]'::jsonb,
            conectable TEXT NULL,
            capa TEXT NOT NULL DEFAULT 'muebles',
            icono TEXT NULL,
            licencia TEXT NOT NULL,
            fuente TEXT NULL,
            autor TEXT NULL,
            atribucion TEXT NULL,
            estado TEXT NOT NULL DEFAULT 'publicado',
            bytes INTEGER NOT NULL DEFAULT 0,
            poligonos INTEGER NOT NULL DEFAULT 0,
            notas TEXT NULL,
            creado_por TEXT NULL,
            aprobado_por TEXT NULL,
            aprobado_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("ALTER TABLE oficina_pisos ADD COLUMN IF NOT EXISTS usa_plano BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE oficina_pisos ADD COLUMN IF NOT EXISTS estilo_escena TEXT NOT NULL DEFAULT 'humano'")
    bind = op.get_bind()
    for it in json.loads(CATALOG.read_text(encoding="utf-8"))["items"]:
        recurso = it.get("o") == "recurso"
        bind.execute(text("""
            INSERT INTO constructor_catalogo (id, nombre, categoria, zonas, origen, forma, archivo, medidas, variantes, conectable, capa, icono,
                                              licencia, fuente, autor, atribucion, estado, creado_por)
            VALUES (:id, :n, :c, CAST(:z AS jsonb), :o, :f, :a, CAST(:m AS jsonb), CAST(:v AS jsonb), :k, :l, :i, :lic, :src, :au, :at, 'publicado', 'semilla 025u')
            ON CONFLICT (id) DO NOTHING
        """), {"id": it["id"], "n": it["n"], "c": it["c"], "z": json.dumps(it.get("z", [])), "o": "recurso" if recurso else "clonexa",
               "f": it["f"], "a": it.get("a"), "m": json.dumps({"w": it["s"][0], "d": it["s"][1], "h": it["s"][2]}),
               "v": json.dumps(it.get("v", [])), "k": it.get("k"), "l": it.get("l", "muebles"), "i": it.get("i"),
               "lic": "CC0 1.0" if recurso else "Propio (Clonexa)", "src": it.get("src") or ("Poly Haven" if recurso else "Clonexa · generado por código"),
               "au": it.get("au") or ("" if recurso else "Clonexa"), "at": None})


def downgrade() -> None:
    op.execute("ALTER TABLE oficina_pisos DROP COLUMN IF EXISTS estilo_escena")
    op.execute("ALTER TABLE oficina_pisos DROP COLUMN IF EXISTS usa_plano")
    op.execute("DROP TABLE IF EXISTS constructor_catalogo")
    op.execute("DROP TABLE IF EXISTS constructor_planos")
