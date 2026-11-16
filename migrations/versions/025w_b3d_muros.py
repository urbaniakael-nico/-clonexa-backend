"""biblioteca 3d: muros interiores (campo inner) recuperados en los 2 borradores de la fase 1

Revision ID: 025w_b3d_muros
Revises: 025v_biblioteca3d
Create Date: 2026-11-16

Aditiva e idempotente. La 025v convirtió los planos de la fase 1 cuando el prototipo aún no tenía muros interiores, y
las paredes interiores se quedaron fuera. Solo había 2 borradores (nunca publicados): ASADERO EL SOCIO (plantilla
Restaurante) y Velvet (plantilla Taller). Sus muros interiores se regeneraron desde las plantillas de la fase 1
(historial de git, app/services/constructor_plano.py en c5e8104) con constructor_v2.from_v1 y quedan aquí fijos.
Solo se escriben si el borrador aún no tiene muros interiores y el local conserva la medida de la plantilla.
"""
from __future__ import annotations

import json

from alembic import op
from sqlalchemy import text

revision = "025w_b3d_muros"
down_revision = "025v_biblioteca3d"
branch_labels = None
depends_on = None

ASADERO = "7625872c-f941-4479-a27b-f8443be953c5"
VELVET = "d63cf68c-be5b-4a30-aee4-341973018db1"
# empresa -> (ancho, fondo de la plantilla, muros interiores)
RECOVER = {
    ASADERO: (20.0, 15.0, [
        {"id": "w5", "x1": -10.0, "z1": -2.5, "x2": -1.0, "z2": -2.5, "kind": "alto", "door": {"pos": 0.5, "width": 0.9, "type": "puerta"},
         "t": 0.12, "mat": "azulejo", "color": "#ffffff"},
        {"id": "w6", "x1": 4.0, "z1": -2.5, "x2": 4.0, "z2": 1.5, "kind": "vidrio", "door": None, "t": 0.06, "color": "#bfe3ff"},
    ]),
    VELVET: (24.0, 14.0, [
        {"id": "w5", "x1": 4.0, "z1": 3.0, "x2": 12.0, "z2": 3.0, "kind": "vidrio", "door": {"pos": 0.214, "width": 1.0, "type": "vidrio"},
         "t": 0.06, "color": "#bfe3ff"},
    ]),
}


def _rows(result):
    if result is None:
        return []
    if isinstance(result, list):
        return result
    return [dict(r) for r in result.mappings().all()]


def upgrade() -> None:
    bind = op.get_bind()
    for cid, (w, d, inner) in RECOVER.items():
        rows = _rows(bind.execute(text("""SELECT id::text AS id, plano FROM constructor_planos WHERE company_id = CAST(:c AS uuid)
            AND diseno_id = 'principal' AND estado = 'borrador'"""), {"c": cid}))
        for r in rows:
            plano = r["plano"] if isinstance(r["plano"], dict) else json.loads(r["plano"])
            room = plano.get("room") or {}
            if plano.get("inner") or float(room.get("w") or 0) != w or float(room.get("d") or 0) != d:
                continue
            ids = {o.get("id") for o in (plano.get("objects") or []) + (plano.get("openings") or [])}
            plano["inner"] = [dict(iw, id=iw["id"] if iw["id"] not in ids else "m" + iw["id"]) for iw in inner]
            bind.execute(text("UPDATE constructor_planos SET plano = CAST(:p AS jsonb) WHERE id = CAST(:i AS uuid)"), {"p": json.dumps(plano), "i": r["id"]})


def downgrade() -> None:
    pass
