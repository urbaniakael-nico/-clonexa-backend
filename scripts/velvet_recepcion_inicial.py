"""Recepcion inicial de las referencias existentes de Velvet (carga inicial automatica, 077A).

Uso (con la base de produccion, p. ej. `railway run -s Postgres`):
    py -3.11 scripts/velvet_recepcion_inicial.py dry-run         # solo lee: imprime el plan
    py -3.11 scripts/velvet_recepcion_inicial.py apply           # idempotente; imprime el lote
    py -3.11 scripts/velvet_recepcion_inicial.py undo <lote>     # anula (no borra) lo de ese lote

- Referencias SIN ningun corte: cada talla con meta recibe su recepcion inicial (cantidad = meta,
  fecha = creacion de la referencia en Bogota), origin 'carga_inicial' y el lote.
- Referencias que ya tienen cortes: lo recibido no se toca.
- Todas reciben "Referencia creada" en su bitacora con su fecha real de creacion (si no la tienen).
- Solo corre si Velvet tiene encendido reference_lifecycle. Correr dos veces no duplica nada.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

COMPANY = "d63cf68c-be5b-4a30-aee4-341973018db1"
TZ = ZoneInfo("America/Bogota")


def show(plan: dict) -> None:
    print("Recepcion inicial a cargar:")
    for x in plan["receptions"]:
        print(f"  {x['name']} · talla {x['size']} · {x['quantity']} · {x['event_date']}")
    print(f"Referencia creada (bitacora): {len(plan['created_events'])}")
    for e in plan["created_events"]:
        print(f"  {e['name']} · {e['at'].astimezone(TZ):%Y-%m-%d %H:%M}" if e["at"] else f"  {e['name']}")
    print("Ya tienen cortes (lo recibido no se toca):", ", ".join(plan["with_cuts"]) or "—")
    print("Tallas combinadas sin carga (revisar a mano):", ", ".join(f"{x['name']} {x['size']} ({x['meta']})" for x in plan["skipped_combined"]) or "—")


async def main(url: str, mode: str, batch: str | None) -> None:
    from app.services import reference_lifecycle, reference_reception

    engine = create_async_engine(url, connect_args={"server_settings": {"default_transaction_read_only": "on"}} if mode == "dry-run" else {})
    async with AsyncSession(engine, expire_on_commit=False) as db:
        if not await reference_lifecycle.is_on(db, COMPANY):
            raise SystemExit("Velvet no tiene reference_lifecycle encendido: no se carga nada.")
        if mode == "undo":
            print(json.dumps(await reference_reception.undo_backfill(db, COMPANY, batch)))
        else:
            plan = await reference_reception.backfill(db, COMPANY, TZ, apply=mode == "apply")
            show(plan)
            print("lote:", plan["batch_id"])
    await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("dry-run", "apply", "undo") or (sys.argv[1] == "undo" and len(sys.argv) < 3):
        raise SystemExit(__doc__)
    _url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ["DATABASE_URL"]
    _url = _url.replace("postgresql://", "postgresql+asyncpg://", 1).replace("postgres://", "postgresql+asyncpg://", 1)
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://x:x@localhost:1/x"  # la app no se conecta sola
    os.environ.setdefault("JWT_SECRET_KEY", "script")
    asyncio.run(main(_url, sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
