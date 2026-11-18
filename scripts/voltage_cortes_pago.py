"""Cortes de pago de VOLTAGE (080A): semana laboral lunes a domingo y corte cada 2 semanas con
ancla el lunes 02/11/2026 (02-15 nov, 16-29 nov, 30 nov-13 dic...). Se guarda como ajuste de la
empresa en us_payroll_rules (settings del modulo payroll): {"week_start_day": "monday",
"pay_period": {"type": "biweekly", "anchor": "2026-11-02"}}. Ninguna otra empresa cambia.

Por defecto solo muestra (conexion de solo lectura). --apply guarda el ajuste con una fila de
auditoria (antes y despues) en admin_audit_log; repetirlo no cambia nada. --undo vuelve a las
reglas de antes desde esa auditoria.
081A: ajuste propio por operacion en us_payroll_rules.places (por id del lugar de trabajo):
Virginia semana domingo a sabado y corte de 2 semanas con ancla el domingo 01/11/2026 (01-14 nov,
15-28 nov, 29 nov-12 dic...). Alabama no tiene ajuste propio: usa el de la empresa (lunes, 02/11).
Uso: railway run -s Postgres py -3.11 scripts/voltage_cortes_pago.py [--apply | --undo]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os

VOLTAGE = "f1e8f774-f052-49ca-880a-268805f07db0"
ACTOR = "Claude (script cortes de pago VOLTAGE 080A)"
PATH = "/scripts/voltage_cortes_pago"
WANTED = {"week_start_day": "monday", "week_start_time": "00:00", "pay_period": {"type": "biweekly", "anchor": "2026-11-02"}}
WANTED_PLACES = {"Virginia": {"week_start_day": "sunday", "week_start_time": "00:00", "pay_period": {"type": "biweekly", "anchor": "2026-11-01"}}}


async def place_ids(c, company_id: str) -> dict:
    from sqlalchemy import text

    rows = (await c.execute(text("SELECT id::text, name FROM work_locations WHERE company_id = CAST(:c AS uuid)"), {"c": company_id})).all()
    by_name: dict = {}
    for pid, name in rows:
        by_name.setdefault(name, []).append(pid)
    out = {}
    for name in WANTED_PLACES:
        ids = by_name.get(name) or []
        if len(ids) > 1:
            raise SystemExit(f"Hay {len(ids)} lugares llamados {name}: revisar a mano.")
        if ids:
            out[ids[0]] = WANTED_PLACES[name]
    return out


async def wanted(c, company_id: str, before: dict) -> dict:
    places = {**(before.get("places") or {}), **await place_ids(c, company_id)}
    return {**before, **WANTED, **({"places": places} if places else {})}


def _json(value):
    if isinstance(value, str):
        try:
            value = json.loads(value or "{}")
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


async def current_rules(c, company_id: str):
    from sqlalchemy import text

    row = (await c.execute(text("""
        SELECT cm.id::text, cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id = CAST(:c AS uuid) AND lower(m.code) = 'payroll' LIMIT 1
    """), {"c": company_id})).first()
    if not row:
        raise SystemExit("La empresa no tiene el modulo de nomina.")
    settings = _json(row[1])
    if settings.get("us_payroll") is not True:
        raise SystemExit("La empresa no tiene us_payroll encendido: no se cambia nada.")
    return row[0], _json(settings.get("us_payroll_rules"))


async def _save(c, module_row: str, company_id: str, rules: dict) -> None:
    from sqlalchemy import text

    await c.execute(text("""
        UPDATE company_modules SET settings = jsonb_set(COALESCE(settings, '{}'::jsonb), '{us_payroll_rules}', CAST(:r AS jsonb), true), updated_at = now()
        WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid)
    """), {"r": json.dumps(rules), "i": module_row, "c": company_id})


async def _audit(c, company_id: str, action: str, detail: dict) -> None:
    from sqlalchemy import text

    await c.execute(text("""
        INSERT INTO admin_audit_log (at, actor, ip, method, path, company_id, status_code, surface, detail)
        VALUES (now(), :a, '', 'POST', :p, CAST(:c AS uuid), 200, 'script', CAST(:d AS jsonb))
    """), {"a": ACTOR, "p": f"{PATH}/{action}", "c": company_id, "d": json.dumps(detail, ensure_ascii=False)})


async def apply(c, company_id: str = VOLTAGE) -> dict:
    module_row, before = await current_rules(c, company_id)
    after = await wanted(c, company_id, before)
    if after == before:
        return {"changed": False, "rules": before}
    await _save(c, module_row, company_id, after)
    await _audit(c, company_id, "apply", {"before": before, "after": after})
    return {"changed": True, "before": before, "after": after}


async def undo(c, company_id: str = VOLTAGE) -> dict:
    from sqlalchemy import text

    row = (await c.execute(text("""
        SELECT detail FROM admin_audit_log WHERE company_id = CAST(:c AS uuid) AND path = :p AND actor = :a ORDER BY at DESC LIMIT 1
    """), {"c": company_id, "p": f"{PATH}/apply", "a": ACTOR})).first()
    if not row:
        return {"undone": False}
    detail = _json(row[0])
    module_row, now_rules = await current_rules(c, company_id)
    if now_rules != detail.get("after"):
        raise SystemExit("Las reglas cambiaron despues del ajuste: revisar a mano antes de deshacer.")
    await _save(c, module_row, company_id, detail.get("before") or {})
    await _audit(c, company_id, "undo", {"before": now_rules, "after": detail.get("before") or {}})
    return {"undone": True, "rules": detail.get("before")}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--undo", action="store_true")
    args = parser.parse_args()
    url = (os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL") or "").replace("postgresql+asyncpg://", "postgresql://", 1)
    if not url:
        raise SystemExit("Falta DATABASE_PUBLIC_URL (corre con: railway run -s Postgres ...)")
    from sqlalchemy.ext.asyncio import create_async_engine

    writes = args.apply or args.undo
    engine = create_async_engine(url.replace("postgresql://", "postgresql+asyncpg://", 1),
                                 connect_args={} if writes else {"server_settings": {"default_transaction_read_only": "on"}})
    try:
        async with engine.begin() as c:
            if args.apply:
                out = await apply(c)
            elif args.undo:
                out = await undo(c)
            else:
                _, rules = await current_rules(c, VOLTAGE)
                out = {"now": rules, "would_be": await wanted(c, VOLTAGE, rules)}
            print(json.dumps(out, ensure_ascii=False))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
