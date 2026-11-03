"""Genera tests/fixtures/reports_board_caso.json: la salida REAL del servidor (reports_board.build)
para el escenario de reports_board_seed.py, con ids fijos. Las pruebas de pantalla (Node) usan
este archivo: misma forma y mismas cifras que el servidor.

Uso: py -3.11 tests/fixtures/make_reports_board_fixture.py   (necesita pgserver)"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "fixtures"))
os.environ.setdefault("JWT_SECRET_KEY", "fixture")
OUT = ROOT / "tests" / "fixtures" / "reports_board_caso.json"


async def main() -> None:
    import pgserver
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    import reports_board_seed as seed
    from app.services import reports_board as svc
    from app.services import work_location_geo as geo

    server = pgserver.get_server(tempfile.mkdtemp(prefix="cx_pg_rbfix_"), cleanup_mode="stop")
    engine = create_async_engine(server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1))
    async with engine.begin() as conn:
        await seed.create_schema(conn)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as db:
        ids = await seed.seed(db, cid="f1e8f774-f052-49ca-880a-268805f07db0")
        # Virginia con perimetro y marcas medidas (dentro / fuera); Alabama sin configurar.
        await geo.save_place(db, ids["company"], ids["va"], {"perimeters": [{"name": "Bodega", "latitude": seed.VA_POINT[0], "longitude": seed.VA_POINT[1]}], "supervisors": [ids["sofia"]]}, "fixture")
        await seed.ev(db, ids["company"], ids["diego"], "check_in", seed.T("11-04T13:00"), point=seed.FAR_POINT)
        await seed.ev(db, ids["company"], ids["diego"], "check_out", seed.T("11-04T14:00"), point=seed.VA_POINT, detail="Revisión del rack 12 con cliente; se dejó pendiente la prueba final de cables y etiquetas porque faltó material.")
        await db.commit()
        await geo.recalculate(db, ids["company"], ids["va"])
        board = await svc.build(db, ids["company"], seed.START, seed.END, now=seed.NOW)
    board["scope"] = {"limited": False, "supervisor_no_place": False}
    board["can_manage"] = True
    # Ids fijos en lugar de los aleatorios de cada corrida.
    raw = json.dumps(board, ensure_ascii=False, indent=1, default=str)
    for key, value in ids.items():
        if key != "company":
            raw = raw.replace(value, f"id-{key}")
    OUT.write_text(raw + "\n", encoding="utf-8")
    await engine.dispose()
    print("escrito", OUT, len(raw))


if __name__ == "__main__":
    asyncio.run(main())
