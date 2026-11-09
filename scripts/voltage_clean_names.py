"""Nombres de Workforce de VOLTAGE con caracteres raros (comillas, comillas invertidas, espacios de
mas) (073A). Por defecto solo muestra (conexion de solo lectura). --apply corrige SOLO esos
caracteres (no cambia mayusculas ni palabras) en una transaccion, con una fila de auditoria por
persona (antes y despues) en admin_audit_log. --undo vuelve a los nombres de antes desde esa auditoria.
Uso: railway run -s Postgres py -3.11 scripts/voltage_clean_names.py [--apply | --undo]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re

VOLTAGE = "f1e8f774-f052-49ca-880a-268805f07db0"
ACTOR = "Claude (script nombres VOLTAGE 073A)"
PATH = "/scripts/voltage_clean_names"


def fixed(name: str) -> str:
    s = re.sub(r"[\"`´“”«»]", "", name or "")
    s = re.sub(r"(?<![A-Za-zÀ-ÿ])'|'(?![A-Za-zÀ-ÿ])", "", s)
    return " ".join(s.split())


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--undo", action="store_true")
    args = parser.parse_args()
    url = (os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL") or "").replace("postgresql+asyncpg://", "postgresql://", 1)
    if not url:
        raise SystemExit("Falta DATABASE_PUBLIC_URL (corre con: railway run -s Postgres ...)")
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    writes = args.apply or args.undo
    engine = create_async_engine(url.replace("postgresql://", "postgresql+asyncpg://", 1),
                                 connect_args={} if writes else {"server_settings": {"default_transaction_read_only": "on"}})
    try:
        async with engine.begin() as c:
            if args.undo:
                rows = (await c.execute(text("""
                    SELECT detail FROM admin_audit_log WHERE company_id = CAST(:c AS uuid) AND path = :p AND actor = :a ORDER BY at DESC
                """), {"c": VOLTAGE, "p": PATH + "/apply", "a": ACTOR})).all()
                for (detail,) in rows:
                    d = detail if isinstance(detail, dict) else json.loads(detail)
                    await c.execute(text("UPDATE employees SET full_name = :b WHERE company_id = CAST(:c AS uuid) AND id = CAST(:e AS uuid) AND full_name = :n"),
                                    {"b": d["before"], "c": VOLTAGE, "e": d["employee_id"], "n": d["after"]})
                print(json.dumps({"undone": len(rows)}))
                return
            people = (await c.execute(text("""
                SELECT id::text, full_name FROM employees WHERE company_id = CAST(:c AS uuid) AND full_name IS NOT NULL ORDER BY full_name
            """), {"c": VOLTAGE})).all()
            changes = [{"employee_id": i, "before": n, "after": fixed(n)} for i, n in people if fixed(n) != n and fixed(n)]
            if args.apply:
                for ch in changes:
                    await c.execute(text("UPDATE employees SET full_name = :n WHERE company_id = CAST(:c AS uuid) AND id = CAST(:e AS uuid)"),
                                    {"n": ch["after"], "c": VOLTAGE, "e": ch["employee_id"]})
                    await c.execute(text("""
                        INSERT INTO admin_audit_log (at, actor, ip, method, path, company_id, status_code, surface, detail)
                        VALUES (now(), :a, '', 'POST', :p, CAST(:c AS uuid), 200, 'script', CAST(:d AS jsonb))
                    """), {"a": ACTOR, "p": PATH + "/apply", "c": VOLTAGE, "d": json.dumps(ch, ensure_ascii=False)})
            print(json.dumps({"applied": bool(args.apply), "changes": [[c["before"], c["after"]] for c in changes]}, ensure_ascii=False))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
