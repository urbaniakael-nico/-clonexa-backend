"""Escenario del Board de gerencia (datos inventados): lo usan tests/test_reports_board_pg.py y
tests/fixtures/make_reports_board_fixture.py. "Ahora" = jueves 5 nov 2026, 18:00 UTC; semana
laboral dom 1 a sáb 7 nov. Virginia = ET (UTC-5), Alabama = CT (UTC-6)."""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import text

UTC = timezone.utc
NOW = datetime(2026, 11, 5, 18, 0, tzinfo=UTC)
START, END = date(2026, 11, 1), date(2026, 11, 7)
VA_POINT = (38.9000, -77.0000)
FAR_POINT = (38.9500, -77.1000)
SUMMARY = "Etiquetado del rack 9 terminado.\nCables 1-1 y 1-2."
SCHEMA = """
CREATE TABLE companies (id uuid PRIMARY KEY, name text NOT NULL, slug text, status text DEFAULT 'active', settings_json jsonb DEFAULT '{}'::jsonb, timezone text);
CREATE TABLE modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text UNIQUE NOT NULL, name text, category text, is_active boolean DEFAULT true);
CREATE TABLE company_modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid REFERENCES companies(id) ON DELETE CASCADE,
  module_id uuid REFERENCES modules(id), enabled boolean DEFAULT true, settings jsonb DEFAULT '{}'::jsonb);
CREATE TABLE work_locations (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL REFERENCES companies(id),
  name varchar(80) NOT NULL, code varchar(8), timezone varchar(64) NOT NULL DEFAULT 'America/Bogota', is_active boolean NOT NULL DEFAULT true, sort_order int NOT NULL DEFAULT 0);
CREATE TABLE employees (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL REFERENCES companies(id),
  full_name varchar(200), document_id varchar(80), email varchar(180), role varchar(80), status varchar(40) DEFAULT 'active', telegram_user_id varchar(120),
  hourly_rate_regular numeric(12,2) DEFAULT 0, hourly_rate_extra numeric(12,2) DEFAULT 0, deduction_1 numeric(12,2) DEFAULT 0, deduction_2 numeric(12,2) DEFAULT 0,
  work_location_id uuid NULL REFERENCES work_locations(id));
CREATE TABLE work_location_changes (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, employee_id uuid NOT NULL, from_location_id uuid, to_location_id uuid,
  from_name text, to_name text, changed_by text, changed_by_user_id uuid, source text, changed_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE work_location_perimeters (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  location_id uuid NOT NULL REFERENCES work_locations(id) ON DELETE CASCADE, name varchar(80) NOT NULL, latitude numeric(10,7) NOT NULL, longitude numeric(10,7) NOT NULL,
  radius_m integer NOT NULL DEFAULT 300, created_by varchar(200), created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE work_location_supervisors (company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE, location_id uuid NOT NULL REFERENCES work_locations(id) ON DELETE CASCADE,
  employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE, created_by varchar(200), created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (location_id, employee_id));
CREATE TABLE workforce_attendance_events (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, employee_id uuid,
  event_type varchar(80) NOT NULL, event_label varchar(180) NOT NULL, employee_name varchar(180), employee_role varchar(80), status_after varchar(40) NOT NULL,
  source varchar(80) NOT NULL DEFAULT 'client', notes text, module_code varchar(80) NOT NULL DEFAULT 'workforce',
  source_channel varchar(80) NOT NULL DEFAULT 'client', source_ref varchar(180), detail text,
  payload_json jsonb NOT NULL DEFAULT '{}'::jsonb, metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  latitude numeric(12,8), longitude numeric(12,8), occurred_at timestamptz NOT NULL DEFAULT now(), created_at timestamptz DEFAULT now());
CREATE TABLE workforce_session_policy (company_id uuid PRIMARY KEY, cutoff_time varchar(5), alert_after_hours numeric);
CREATE TABLE inventory_items (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, name_reference text, name text, reference text);
CREATE TABLE material_requests (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, employee_id uuid, employee_name text, employee_role text, order_number text,
  material_name text, inventory_item_id uuid, quantity numeric, quantity_returned numeric, unit text, status text, destination text, notes text, source_channel text,
  requested_at timestamptz, approved_at timestamptz, delivered_at timestamptz, returned_at timestamptz, created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now())
"""


def T(s: str) -> datetime:
    return datetime.fromisoformat(f"2026-{s}:00+00:00")


async def create_schema(conn) -> None:
    for stmt in [s for s in SCHEMA.split(";") if s.strip()]:
        await conn.execute(text(stmt))
    for code in ("payroll", "reports", "workforce"):
        await conn.execute(text("INSERT INTO modules (code, name) VALUES (:c, :c)"), {"c": code})


async def company(db, name: str, *, board: bool, cid: str | None = None) -> str:
    cid = cid or str(uuid.uuid4())
    await db.execute(text("INSERT INTO companies (id, name, timezone) VALUES (CAST(:i AS uuid), :n, 'America/Chicago')"), {"i": cid, "n": name})
    for code, settings in (("payroll", {"payroll_v2": True, "us_payroll": True}), ("reports", {"reports_v2": True, **({"reports_board": True} if board else {})}),
                           ("workforce", {"work_locations": True})):
        await db.execute(text("""INSERT INTO company_modules (company_id, module_id, enabled, settings)
                                 SELECT CAST(:c AS uuid), id, true, CAST(:s AS jsonb) FROM modules WHERE code = :m"""),
                         {"c": cid, "s": json.dumps(settings), "m": code})
    await db.commit()
    return cid


async def place(db, cid: str, name: str, code: str, tz: str, order: int) -> str:
    pid = (await db.execute(text("""INSERT INTO work_locations (company_id, name, code, timezone, sort_order)
                                    VALUES (CAST(:c AS uuid), :n, :k, :t, :o) RETURNING id::text"""),
                            {"c": cid, "n": name, "k": code, "t": tz, "o": order})).scalar()
    await db.commit()
    return pid


async def person(db, cid: str, name: str, doc: str | None, where: str | None, role: str = "operario", email: str | None = None, rate: str = "0") -> str:
    eid = (await db.execute(text("""INSERT INTO employees (company_id, full_name, document_id, email, role, work_location_id, hourly_rate_regular)
                                    VALUES (CAST(:c AS uuid), :n, :d, :m, :r, CAST(:p AS uuid), CAST(:rate AS numeric)) RETURNING id::text"""),
                            {"c": cid, "n": name, "d": doc, "m": email, "r": role, "p": where, "rate": rate})).scalar()
    await db.commit()
    return eid


LABEL = {"check_in": "Inicio de turno", "break_start": "Pausa", "break_end": "Retomar labores", "check_out": "Finalizar turno"}
STATUS = {"check_in": "working", "break_start": "on_break", "break_end": "working", "check_out": "checked_out"}


async def ev(db, cid: str, eid: str, kind: str, at: datetime, *, point: tuple | None = None, detail: str | None = None, payload: dict | None = None, channel: str = "telegram") -> None:
    data = dict(payload or {})
    if point:
        data["punch_location"] = {"latitude": point[0], "longitude": point[1], "gps_status": "unconfigured", "gps_status_label": "Sin perímetro"}
        data["gps_status"] = "unconfigured"
    if detail:
        data["args"] = detail
    await db.execute(text("""
        INSERT INTO workforce_attendance_events (company_id, employee_id, event_type, event_label, status_after, source, source_channel,
                                                 detail, notes, payload_json, latitude, longitude, occurred_at)
        VALUES (CAST(:c AS uuid), CAST(:e AS uuid), :k, :l, :s, 'telegram', :ch, :d, :d, CAST(:p AS jsonb), :lat, :lng, :at)
    """), {"c": cid, "e": eid, "k": kind, "l": LABEL[kind], "s": STATUS[kind], "ch": channel, "d": detail, "p": json.dumps(data),
           "lat": point[0] if point else None, "lng": point[1] if point else None, "at": at})


async def shift(db, cid: str, eid: str, start: str, end: str | None, *, pause: tuple | None = None, point: tuple | None = VA_POINT, out_point: tuple | None = None, summary: str | None = None) -> None:
    await ev(db, cid, eid, "check_in", T(start), point=point, detail="Ubicación GPS validada")
    if pause:
        await ev(db, cid, eid, "break_start", T(pause[0]), point=point)
        if pause[1]:
            await ev(db, cid, eid, "break_end", T(pause[1]), point=point)
    if end:
        await ev(db, cid, eid, "check_out", T(end), point=out_point or point, detail=summary)
    await db.commit()


async def seed(db, cid: str | None = None) -> dict:
    cid = await company(db, "VOLTAGE", board=True, cid=cid)
    va = await place(db, cid, "Virginia", "VA", "America/New_York", 1)
    al = await place(db, cid, "Alabama", "AL", "America/Chicago", 2)
    ids: dict = {"company": cid, "va": va, "al": al}
    # Virginia
    ids["angela"] = await person(db, cid, "Ángela Núñez", "VA-100", va, rate="25")
    await shift(db, cid, ids["angela"], "11-02T11:45", "11-02T21:25", pause=("11-02T15:35", "11-02T16:29"), summary=SUMMARY)
    await db.execute(text("""INSERT INTO material_requests (company_id, employee_id, material_name, quantity, unit, status, requested_at)
                             VALUES (CAST(:c AS uuid), CAST(:e AS uuid), 'Cable 6 AWG', 3, 'm', 'requested', :at)"""),
                     {"c": cid, "e": ids["angela"], "at": T("11-02T16:40")})
    ids["bruno"] = await person(db, cid, "Bruno Díaz", "VA-200", va)
    await shift(db, cid, ids["bruno"], "11-05T13:00", None, pause=("11-05T15:00", "11-05T15:20"))
    ids["carla"] = await person(db, cid, "Carla Peña", "VA-300", va)
    await shift(db, cid, ids["carla"], "11-05T14:00", None, pause=("11-05T17:40", None))
    ids["diego"] = await person(db, cid, "Diego Ruiz", "VA-400", va)
    ids["sofia"] = await person(db, cid, "Sofía Mora", "VA-500", va, role="supervisor", email="sofia@voltage.test")
    # Alabama
    ids["elena"] = await person(db, cid, "Elena Gómez", "AL-100", al)
    for d in ("01", "02", "03", "04"):
        await shift(db, cid, ids["elena"], f"11-{d}T12:00", f"11-{d}T21:30", point=None if d == "02" else VA_POINT)
    ids["felipe"] = await person(db, cid, "Felipe Soto", "AL-200", al, rate="20")
    for d in ("01", "02", "03", "04"):  # 11 h x 4 = 44 h: 40 regulares + 4 overtime
        await shift(db, cid, ids["felipe"], f"11-{d}T12:00", f"11-{d}T23:00")
    ids["gabriel"] = await person(db, cid, "Gabriel Luna", "AL-300", al)  # abierto hace 15 h
    await shift(db, cid, ids["gabriel"], "11-05T03:00", None)
    ids["helena"] = await person(db, cid, "Helena Ríos", "AL-400", al)  # cerrado con 15 h: por confirmar
    await shift(db, cid, ids["helena"], "11-03T12:00", "11-04T03:00", summary="Turno largo en el rack 4")
    ids["ivan"] = await person(db, cid, "Iván Mena", "AL-500", al)  # lo cerro un supervisor
    await ev(db, cid, ids["ivan"], "check_in", T("11-04T13:00"))
    await ev(db, cid, ids["ivan"], "check_out", T("11-04T23:00"), channel="portal_manual_close",
             payload={"manual_close": True, "closed_by": "Sofía Mora", "note": "Olvidó marcar la salida", "closed_at": "2026-11-05T01:15:00+00:00"})
    await db.commit()
    # Sin lugar
    ids["jaime"] = await person(db, cid, "Jaime Sol", None, None)
    await shift(db, cid, ids["jaime"], "11-03T14:00", "11-03T20:00")
    return ids
