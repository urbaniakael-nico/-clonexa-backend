"""Enciende whatsapp_group_reports SOLO para VOLTAGE y guarda su configuracion en MODO PRUEBA (072A).

Por defecto solo muestra (conexion de solo lectura): operaciones, interruptores y configuracion.
--apply: en UNA transaccion
  - settings del modulo workforce de VOLTAGE: whatsapp_group_reports = true (las demas llaves igual);
  - wa_report_config: destinatarios leidos de referencias\\voltage-avisos-config.json (fuera del
    repo), operaciones Virginia y Alabama, supervisor en Alabama, timesheet semanal de Virginia,
    carpetas de Drive y test_mode = true. Lo ya guardado (IDs de grupos) se conserva;
  - fila de auditoria en admin_audit_log.
--off: apaga el interruptor (la configuracion queda guardada).
Uso: railway run -s Postgres py -3.11 scripts/voltage_group_reports_on.py [--apply | --off]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

VOLTAGE = "f1e8f774-f052-49ca-880a-268805f07db0"
ACTOR = "Claude (script Avisos WhatsApp 072A)"
DATA = Path(r"C:\Users\valef\Desktop\referencias\voltage-avisos-config.json")
DRIVE = {"Alabama": "1QqD0iuyUOw1gKyu6B3OpLl62MKe8qJam", "Virginia": "1dmJ5PxpDt1_TOsi5Txag_5WO4HMTeLDE",
         "_other": "1GOz_ERLTwErm8n-Zcq66cbXSzLWWnlTb"}


async def run(db, mode: str) -> dict:
    from sqlalchemy import text

    from app.services import group_reports as gr
    from app.services import work_schedule as ws

    locs = await gr.locations(db, VOLTAGE)
    by = {}
    for loc in locs:
        for name in ("Virginia", "Alabama"):
            if name.lower() in str(loc["name"] or "").lower():
                by[name] = loc
    raw = (await db.execute(text("""
        SELECT cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id = CAST(:c AS uuid) AND lower(m.code) = 'workforce'
    """), {"c": VOLTAGE})).scalar()
    settings = ws.settings_dict(raw)
    out = {"operations": {k: v["id"] for k, v in by.items()}, "work_schedule": settings.get("work_schedule") is True,
           "switch_before": settings.get(gr.KEY) is True}
    if mode == "show":
        cfg = await gr.get_config(db, VOLTAGE)
        out["config"] = {"test_mode": cfg["test_mode"], "operations": len(cfg["operations"]), "owners": len(cfg["owners"]),
                         "groups_with_id": sum(1 for o in cfg["operations"] if o.get("group_jid"))}
        return out
    if mode == "off":
        await db.execute(text("""
            UPDATE company_modules SET settings = COALESCE(settings::jsonb, '{}'::jsonb) || jsonb_build_object(CAST(:k AS text), false)
             WHERE company_id = CAST(:c AS uuid) AND module_id = (SELECT id FROM modules WHERE lower(code) = 'workforce')
        """), {"c": VOLTAGE, "k": gr.KEY})
        await _audit(db, "off", out)
        await db.commit()
        return {**out, "switch_after": False}
    if set(by) != {"Virginia", "Alabama"}:
        raise SystemExit(f"No encontre Virginia y Alabama en VOLTAGE: {sorted(by)}")
    data = json.loads(DATA.read_text("utf-8"))
    current = await gr.get_config(db, VOLTAGE)
    old_ops = {o["location_id"]: o for o in current.get("operations") or []}
    body = {**current, "test_mode": True, "own_number": data["own_number"], "clonexa_email": data["clonexa_email"],
            "operations": [{"location_id": by[n]["id"], "group_jid": (old_ops.get(by[n]["id"]) or {}).get("group_jid", ""),
                            "group_name": (old_ops.get(by[n]["id"]) or {}).get("group_name", "")} for n in ("Virginia", "Alabama")],
            "supervisor": {**data["supervisor"], "location_id": by["Alabama"]["id"]},
            "owners": data["owners"], "weekly_location_id": by["Virginia"]["id"],
            "drive_folders": {by["Alabama"]["id"]: DRIVE["Alabama"], by["Virginia"]["id"]: DRIVE["Virginia"], "_other": DRIVE["_other"]}}
    locations = {loc["id"] for loc in locs}
    cfg = gr.clean_config(body, locations)
    await db.execute(text("""
        INSERT INTO wa_report_config (company_id, config, updated_by, updated_at) VALUES (CAST(:c AS uuid), CAST(:j AS jsonb), :by, now())
        ON CONFLICT (company_id) DO UPDATE SET config = EXCLUDED.config, updated_by = EXCLUDED.updated_by, updated_at = now()
    """), {"c": VOLTAGE, "j": json.dumps(cfg), "by": ACTOR})
    await db.execute(text("""
        UPDATE company_modules SET settings = COALESCE(settings::jsonb, '{}'::jsonb) || jsonb_build_object(CAST(:k AS text), true)
         WHERE company_id = CAST(:c AS uuid) AND module_id = (SELECT id FROM modules WHERE lower(code) = 'workforce')
    """), {"c": VOLTAGE, "k": gr.KEY})
    await _audit(db, "apply", {**out, "test_mode": True, "owners": len(cfg["owners"])})
    await db.commit()
    return {**out, "switch_after": True, "test_mode": cfg["test_mode"], "owners": len(cfg["owners"])}


async def _audit(db, action: str, detail: dict) -> None:
    from sqlalchemy import text

    await db.execute(text("""
        INSERT INTO admin_audit_log (at, actor, ip, method, path, company_id, status_code, surface, detail)
        VALUES (now(), :a, '', 'POST', :p, CAST(:c AS uuid), 200, 'script', CAST(:d AS jsonb))
    """), {"a": ACTOR, "p": f"/scripts/voltage_group_reports_on/{action}", "c": VOLTAGE, "d": json.dumps(detail)})


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--off", action="store_true")
    args = parser.parse_args()
    public = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL") or ""
    if not public:
        raise SystemExit("Falta DATABASE_PUBLIC_URL (corre con: railway run -s Postgres ...)")
    os.environ["DATABASE_URL"] = public.replace("postgresql+asyncpg://", "postgresql://", 1).replace("postgresql://", "postgresql+asyncpg://", 1)
    os.environ.setdefault("JWT_SECRET_KEY", "solo-script")
    os.environ.setdefault("SECRET_KEY", "solo-script")
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    mode = "apply" if args.apply else ("off" if args.off else "show")
    connect = {} if mode != "show" else {"server_settings": {"default_transaction_read_only": "on"}}
    engine = create_async_engine(os.environ["DATABASE_URL"], connect_args=connect)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            print(json.dumps(await run(db, mode), ensure_ascii=False))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
