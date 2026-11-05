"""Cierre administrativo de los turnos viejos de Velvet (mayo a septiembre 2026, nominas ya pagadas).

Uso (con la base de produccion, p. ej. `railway run -s Postgres`):
    py -3.11 scripts/velvet_cierre_administrativo.py dry-run         # solo lee: imprime la tabla
    py -3.11 scripts/velvet_cierre_administrativo.py apply           # idempotente; imprime el lote
    py -3.11 scripts/velvet_cierre_administrativo.py undo <lote>     # borra solo las filas de ese lote

- Salida = la ultima marca real del turno en el dia de su entrada. Si la unica marca es la
  entrada, la salida habitual de esa persona (mediana de sus turnos normales), marcada estimado.
- Cada turno queda como una fila de workforce_session_closures con status 'admin_closed': no entra a
  ninguna nomina y no sale como turno por confirmar. Los eventos de asistencia no se tocan.
- Solo turnos retenidos y sin cierre, con entrada antes de LIMITE. No toca turnos abiertos ni confirmados.
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

COMPANY = "d63cf68c-be5b-4a30-aee4-341973018db1"
TZ = ZoneInfo("America/Bogota")
LIMITE = datetime(2026, 10, 1, tzinfo=TZ)
EXPECTED = 38
STATUS = "admin_closed"
REASON = "cierre_administrativo"
NOTE = "Nóminas ya pagadas, cierre de turnos olvidados (autorizado por el dueño de Clonexa)"
ACTOR = "Cierre administrativo · ya pagado"


def local_minutes(value: datetime) -> int:
    local = value.astimezone(TZ)
    return local.hour * 60 + local.minute


def habitual_exits(shifts_by_employee: dict) -> dict[str, int]:
    """Mediana de la hora de salida de los turnos normales de cada persona, en minutos del dia."""
    out = {}
    for employee, shifts in shifts_by_employee.items():
        normal = [local_minutes(s["end"]) for s in shifts if s["end"] and s["verdict"] == "pay" and s["end"].astimezone(TZ).date() == s["start"].astimezone(TZ).date()]
        if normal:
            out[employee] = int(statistics.median(normal))
    return out


def proposal(shift: dict, marks: list[dict], habitual: dict[str, int], employee: str) -> dict:
    """Marcas del turno en el dia de su entrada; funcion pura."""
    day = shift["start"].astimezone(TZ).date()
    same_day = [m for m in marks if shift["start"] <= m["at"] <= shift["end"] and m["at"].astimezone(TZ).date() == day]
    last = max(same_day, key=lambda m: m["at"]) if same_day else None
    if last and last["at"] > shift["start"]:
        return {"end": last["at"], "estimated": False, "mark": last["kind"], "review": False}
    minutes = habitual.get(employee)
    if minutes is None:
        return {"end": None, "estimated": True, "mark": "sin habitual", "review": True}
    local = shift["start"].astimezone(TZ).replace(hour=minutes // 60, minute=minutes % 60, second=0, microsecond=0)
    if local <= shift["start"]:
        return {"end": None, "estimated": True, "mark": "habitual antes de la entrada", "review": True}
    return {"end": local.astimezone(timezone.utc), "estimated": True, "mark": "salida habitual", "review": False}


async def plan(db: AsyncSession, company: str = COMPANY) -> list[dict]:
    from app.api.v1.endpoints import payroll as core
    from app.services import reference_time as rt

    classify, _ = rt._classifier()
    events = [dict(r) for r in (await db.execute(text("""
        SELECT id, employee_id, employee_name, event_type, event_label, status_after, detail, payload_json, metadata_json,
               COALESCE(occurred_at, created_at) AS occurred_at
        FROM workforce_attendance_events WHERE company_id = CAST(:c AS uuid)
    """), {"c": company})).mappings().all()]
    verification = await core._cx_verification_context_049D(db, company)
    shifts = rt.build_shifts(events, classify, core._cx_check_shift_049D, core._cx_event_system_cutoff_049D, verification)
    habitual = habitual_exits(shifts)
    marks: dict[str, list[dict]] = {}
    names: dict[str, str] = {}
    for ev in events:
        emp = str(ev.get("employee_id") or "")
        names[emp] = ev.get("employee_name") or names.get(emp, "")
        if str(ev.get("event_type") or "").lower() != "voided" and rt.as_utc(ev["occurred_at"]):
            marks.setdefault(emp, []).append({"at": rt.as_utc(ev["occurred_at"]), "kind": str(ev["event_type"]).lower()})
    sessions = (await db.execute(text("""
        SELECT employee_id, reference_name, started_at, ended_at FROM reference_work_sessions WHERE company_id = :c AND ended_at IS NOT NULL
    """), {"c": company})).mappings().all()
    out = []
    for emp, items in shifts.items():
        for s in items:
            if s["verdict"] != "hold" or not s["end"] or s["start"] >= LIMITE or (("attendance", s["ref"]) in verification["closures"]):
                continue
            p = proposal(s, marks.get(emp, []), habitual, emp)
            pauses = sum((b - a).total_seconds() for a, b in s["breaks"] if b and p["end"] and b <= p["end"])
            net = (p["end"] - s["start"]).total_seconds() - pauses if p["end"] else None
            refs = sorted({str(r["reference_name"]) for r in sessions if str(r["employee_id"]) == emp and r["started_at"] < s["end"] and r["ended_at"] > s["start"]})
            out.append({"ref": s["ref"], "employee_id": emp, "employee": names.get(emp) or emp, "references": refs, "start": s["start"], "system_end": s["end"], **p, "net_seconds": net})
    return sorted(out, key=lambda x: x["start"])


def table(items: list[dict]) -> None:
    def at(v):
        return v.astimezone(TZ).strftime("%d-%b %H:%M") if v else "REVISAR"

    def hm(v):
        return "—" if v is None else f"{int(v) // 3600}:{int(v) % 3600 // 60:02d}"

    for i, x in enumerate(items, 1):
        print(f"{i} | {x['employee']} | {', '.join(x['references'])} | {at(x['start'])} | {at(x['system_end'])} | {at(x['end'])} | {x['mark']} | {'ESTIMADO' if x['estimated'] else ''}{' REVISAR' if x['review'] else ''} | {hm(x['net_seconds'])}")
    print("turnos:", len(items), "estimados:", sum(x["estimated"] for x in items), "por revisar:", sum(x["review"] for x in items),
          "horas:", hm(sum(x["net_seconds"] or 0 for x in items)))


async def apply_plan(db: AsyncSession, items: list[dict], company: str = COMPANY, expected: int | None = EXPECTED) -> dict:
    """Idempotente: lo ya cerrado no vuelve al plan y ON CONFLICT no repite filas."""
    if any(x["review"] for x in items):
        raise ValueError("Hay turnos por revisar: no se aplica nada.")
    if items and expected is not None and len(items) != expected:
        raise ValueError(f"Se esperaban {expected} turnos y hay {len(items)}: no se aplica nada.")
    batch = str(uuid.uuid4())
    count = 0
    for x in items:
        done = await db.execute(text("""
            INSERT INTO workforce_session_closures (company_id, employee_id, employee_name, source, session_ref, panel_type, reason, started_at, system_end_at,
                status, real_end_at, real_end_note, confirmed_by_name, confirmed_by_user_id, confirmed_at)
            VALUES (CAST(:c AS uuid), CAST(:e AS uuid), :n, 'attendance', :ref, 'asistencia', :r, :s, :sys, :st, :end, :note, :by, :b, now())
            ON CONFLICT (company_id, source, session_ref) DO NOTHING
        """), {"c": company, "e": x["employee_id"], "n": str(x["employee"])[:180], "ref": x["ref"], "r": REASON, "s": x["start"], "sys": x["system_end"], "st": STATUS,
               "end": x["end"], "note": (NOTE + (" · hora estimada" if x["estimated"] else ""))[:300], "by": ACTOR, "b": batch})
        count += done.rowcount
    await db.commit()
    return {"applied": count, "batch": batch if count else None}


async def undo(db: AsyncSession, batch: str, company: str = COMPANY) -> dict:
    """Borra solo las filas de ese lote: los turnos vuelven a por confirmar, como estaban."""
    done = await db.execute(text("""
        DELETE FROM workforce_session_closures
        WHERE company_id = CAST(:c AS uuid) AND status = :s AND reason = :r AND confirmed_by_user_id = :b
    """), {"c": company, "s": STATUS, "r": REASON, "b": batch})
    await db.commit()
    return {"undo": batch, "rows": done.rowcount}


async def main(url: str, mode: str, batch: str | None) -> None:
    engine = create_async_engine(url, connect_args={"server_settings": {"default_transaction_read_only": "on"}} if mode == "dry-run" else {})
    async with AsyncSession(engine, expire_on_commit=False) as db:
        if mode == "undo":
            print(json.dumps(await undo(db, batch)))
        else:
            items = await plan(db)
            table(items)
            if mode == "apply":
                print(json.dumps(await apply_plan(db, items)))
    await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("dry-run", "apply", "undo") or (sys.argv[1] == "undo" and len(sys.argv) < 3):
        raise SystemExit(__doc__)
    _url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ["DATABASE_URL"]
    _url = _url.replace("postgresql://", "postgresql+asyncpg://", 1).replace("postgres://", "postgresql+asyncpg://", 1)
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://x:x@localhost:1/x"  # la app no se conecta sola
    os.environ.setdefault("JWT_SECRET_KEY", "script")
    asyncio.run(main(_url, sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
