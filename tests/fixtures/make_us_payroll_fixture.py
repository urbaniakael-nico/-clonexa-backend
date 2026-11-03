"""Genera tests/fixtures/us_payroll_caso.json: la salida REAL del servidor (snapshot de
Nomina e insights de Reportes) para las marcaciones de Caso del 2 nov 2026, con ids
fijos. Las pruebas de pantalla (Node) usan este archivo: mismas cifras que el servidor.

Uso: py -3.11 tests/fixtures/make_us_payroll_fixture.py   (necesita pgserver)
tests/test_us_payroll_pg.py verifica que el archivo siga igual a lo que calcula el servidor."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import uuid
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "tests" / "fixtures" / "us_payroll_caso.json"


def normalize(value, ids: dict):
    if isinstance(value, dict):
        return {k: normalize(v, ids) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v, ids) for v in value]
    if isinstance(value, str) and value in ids:
        return ids[value]
    return value


async def build(db) -> dict:
    from app.api.v1.endpoints import payroll as core
    from app.services import reports_v2
    from tests import test_us_payroll_pg as t

    cid = await t._company(db, us=True)
    va = await t._place(db, cid, "Virginia", "America/New_York")
    yes = await t._person(db, cid, "Colaboradora Caso 2 Nov", va)
    await t._caso(db, cid, yes)
    snap = await core.calculate_period_snapshot(db, uuid.UUID(cid), date(2026, 11, 1), date(2026, 11, 7))
    payload = {"summary": {"period": {"start": "2026-11-01", "end": "2026-11-07"}},
               "details": {"payroll": snap["rows"], "employees": [{"id": yes, "full_name": "Colaboradora Caso 2 Nov", "status": "active"}]}}
    ins = await reports_v2.insights_for(db, cid, payload, now=datetime.fromisoformat("2026-11-03T00:00:00+00:00"))
    ids = {cid: "company-voltage", yes: "emp-caso"}
    out = json.loads(json.dumps({"snapshot": snap, "insights_v2": ins}, default=str))
    return normalize(out, ids)


async def main() -> None:
    import pgserver
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from tests import test_us_payroll_pg as t

    server = pgserver.get_server(tempfile.mkdtemp(prefix="cx_pg_fix_"), cleanup_mode="stop")
    engine = create_async_engine(server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1))
    async with engine.begin() as conn:
        for stmt in [s for s in t.SCHEMA.split(";") if s.strip()]:
            await conn.execute(text(stmt))
        for code in ("payroll", "reports", "workforce"):
            await conn.execute(text("INSERT INTO modules (code, name) VALUES (:c, :c)"), {"c": code})
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
        data = await build(db)
    await engine.dispose()
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("escrito", OUT, os.path.getsize(OUT), "bytes")


if __name__ == "__main__":
    asyncio.run(main())
