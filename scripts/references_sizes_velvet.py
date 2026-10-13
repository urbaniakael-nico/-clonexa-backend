"""Referencias v2 · conversion de tallas (S, M, L) y meta = suma de cortes, para UNA empresa.

Uso (con la base de produccion, p. ej. `railway run -s Postgres`):
    py -3.11 scripts/references_sizes_velvet.py <company_id> dry-run   # solo calcula, no escribe
    py -3.11 scripts/references_sizes_velvet.py <company_id> apply     # convierte e iguala metas
    py -3.11 scripts/references_sizes_velvet.py <company_id> revert <batch_id>

- La conversion corre en UNA transaccion y compara la suma de meta y producido
  por referencia antes y despues; si no cuadra, no aplica nada.
- Cada cambio queda en reference_change_log con su valor viejo (batch_id):
  `revert <batch_id>` lo deshace exacto, en orden inverso.
- Escribe el informe JSON en REPORT_DIR (por defecto, la carpeta temporal).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if os.environ.get("DATABASE_PUBLIC_URL") and "asyncpg" not in os.environ.get("DATABASE_URL", ""):
    os.environ["DATABASE_URL"] = os.environ["DATABASE_PUBLIC_URL"].replace("postgresql://", "postgresql+asyncpg://", 1)

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

ACTOR = "conversion tallas S/M/L (script)"


async def main(company_id: str, mode: str, batch: str | None) -> dict:
    from app.services import references_v2 as rv2

    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    out: dict = {"company_id": company_id, "mode": mode, "at": datetime.now(timezone.utc).isoformat()}
    try:
        async with maker() as db:
            if mode == "revert":
                out["reverted"] = await rv2.revert_batch(db, company_id, batch)
                return out
            out["conversion"] = await rv2.convert_sizes(db, company_id, ACTOR, apply=(mode == "apply"))
        if mode == "apply" and out["conversion"]["applied"]:
            async with maker() as db:
                out["meta"] = await rv2.sync_meta(db, company_id, ACTOR, "igualar_meta_inicial")
        elif mode == "dry-run":
            async with maker() as db:  # que se igualaria si la conversion ya estuviera aplicada: se ve despues de aplicar
                out["meta_preview_without_conversion"] = await rv2.sync_meta(db, company_id, ACTOR, apply=False)
    finally:
        await engine.dispose()
    return out


if __name__ == "__main__":
    cid, mode = sys.argv[1], sys.argv[2]
    batch = sys.argv[3] if len(sys.argv) > 3 else None
    if mode not in ("dry-run", "apply", "revert") or (mode == "revert" and not batch):
        raise SystemExit(__doc__)
    result = asyncio.run(main(cid, mode, batch))
    folder = Path(os.environ.get("REPORT_DIR") or tempfile.gettempdir())
    folder.mkdir(exist_ok=True)
    path = folder / f"references_sizes_{cid}_{mode}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, default=str, indent=1), encoding="utf-8")
    print(path)
    conv = result.get("conversion") or {}
    print(json.dumps({"applied": conv.get("applied"), "ok": conv.get("ok"), "batch": conv.get("batch_id"),
                      "renames": len((conv.get("plan") or {}).get("renames", [])), "merges": len((conv.get("plan") or {}).get("merges", [])),
                      "review": len((conv.get("plan") or {}).get("review", [])), "mismatch": conv.get("mismatch"),
                      "meta": (result.get("meta") or {}).get("batch_id"), "reverted": result.get("reverted")}, ensure_ascii=False))
