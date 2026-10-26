"""Cierre de nomina contra Postgres REAL con la tabla payroll_periods COMO EN
PRODUCCION (migracion 0001: period_type, starts_at, ends_at y created_at NOT
NULL, unicidad por empresa y rango).

Antes ningun cierre se guardaba ("null value in column period_type"). Ahora:
- el corte automatico de una empresa con dias de corte (Velvet: 10 y 25)
  cierra el periodo 26 sep - 10 oct UNA sola vez, period_type "cutoff",
  con los mismos totales que muestra Nomina (calculate_period_snapshot);
- correrlo otra vez no crea otro cierre;
- un cierre manual con otras fechas queda period_type "manual".
Si pgserver no esta instalado la prueba se salta.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import uuid
from datetime import date, datetime, timezone

import pytest

pgserver = pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.api.v1.endpoints import payroll  # noqa: E402

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (id uuid PRIMARY KEY, name text NOT NULL, timezone varchar(64) NOT NULL DEFAULT 'America/Bogota', settings_json jsonb DEFAULT '{}'::jsonb);
CREATE TABLE IF NOT EXISTS company_core_settings (company_id uuid PRIMARY KEY, language varchar(8), session_timeout_minutes integer, currency varchar(8), timezone varchar(80),
  created_at timestamptz, updated_at timestamptz);
CREATE TABLE IF NOT EXISTS modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text UNIQUE NOT NULL, is_active boolean DEFAULT true);
CREATE TABLE IF NOT EXISTS company_modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid, module_id uuid, enabled boolean DEFAULT true, settings jsonb DEFAULT '{}'::jsonb);
CREATE TABLE IF NOT EXISTS employees (id uuid PRIMARY KEY, company_id uuid, full_name text, role text, hourly_rate_regular numeric DEFAULT 0, hourly_rate_extra numeric DEFAULT 0,
  deduction_1 numeric DEFAULT 0, deduction_2 numeric DEFAULT 0, status text DEFAULT 'active');
CREATE TABLE IF NOT EXISTS workforce_attendance_events (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid, employee_id uuid, event_type varchar(60), event_label text,
  employee_name text, employee_role text, status_after text, source text, module_code text, source_channel text, detail text, notes text,
  payload_json jsonb DEFAULT '{}'::jsonb, metadata_json jsonb DEFAULT '{}'::jsonb, occurred_at timestamptz, created_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS payroll_period_config (company_id uuid PRIMARY KEY, cutoff_days jsonb, auto_close boolean, active_from timestamptz);
CREATE TABLE IF NOT EXISTS payroll_periods (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL REFERENCES companies(id), name varchar NOT NULL, period_type varchar NOT NULL,
  starts_at timestamptz NOT NULL, ends_at timestamptz NOT NULL, status varchar NOT NULL, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
  period_start date, period_end date, currency varchar, totals_json jsonb, snapshot_json jsonb, closed_at timestamptz,
  CONSTRAINT uq_payroll_periods_company_range UNIQUE (company_id, starts_at, ends_at));
CREATE TABLE IF NOT EXISTS payroll_period_items (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), period_id uuid REFERENCES payroll_periods(id), company_id uuid, employee_id uuid,
  employee_name varchar NOT NULL DEFAULT 'Sin nombre', employee_role varchar, closed_shifts integer NOT NULL DEFAULT 0, regular_minutes integer NOT NULL DEFAULT 0,
  extra_minutes integer NOT NULL DEFAULT 0, hourly_rate_regular numeric NOT NULL DEFAULT 0, hourly_rate_extra numeric NOT NULL DEFAULT 0, deduction_1 numeric NOT NULL DEFAULT 0,
  deduction_2 numeric NOT NULL DEFAULT 0, gross_amount numeric NOT NULL DEFAULT 0, discount_amount numeric NOT NULL DEFAULT 0, net_amount numeric NOT NULL DEFAULT 0,
  item_json jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now());
"""


@pytest.fixture(scope="module")
def pg_url():
    folder = tempfile.mkdtemp(prefix="cx_pg_close_")
    server = pgserver.get_server(folder, cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            for stmt in [s for s in SCHEMA.split(";") if s.strip()]:
                await conn.execute(text(stmt))
        await engine.dispose()

    asyncio.run(setup())
    yield url


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def test_auto_close_saves_once_with_the_same_totals_and_period_type(pg_url, monkeypatch):
    # Las tablas ya existen como en produccion; ensure_payroll_storage pide pgcrypto, que este Postgres no trae.
    async def no_storage(db):
        return None

    monkeypatch.setattr(payroll, "ensure_payroll_storage", no_storage)

    async def run():
        engine = create_async_engine(pg_url)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with maker() as db:
                cid = str(uuid.uuid4())
                await db.execute(text("INSERT INTO companies (id, name) VALUES (CAST(:c AS uuid), 'Velvet')"), {"c": cid})
                await db.execute(text("INSERT INTO payroll_period_config VALUES (CAST(:c AS uuid), '[10, 25]'::jsonb, true, :a)"), {"c": cid, "a": utc("2026-09-28T16:26:13")})
                for n in range(4):
                    emp = str(uuid.uuid4())
                    await db.execute(text("INSERT INTO employees (id, company_id, full_name, role, hourly_rate_regular, hourly_rate_extra) VALUES "
                                          "(CAST(:e AS uuid), CAST(:c AS uuid), :n, 'operaria', 7500, 9000)"), {"e": emp, "c": cid, "n": f"Persona {n}"})
                    for day in (29, 30):
                        for kind, hour in (("check_in", 12), ("check_out", 20)):
                            await db.execute(text("INSERT INTO workforce_attendance_events (company_id, employee_id, event_type, status_after, occurred_at) VALUES "
                                                  "(CAST(:c AS uuid), CAST(:e AS uuid), :k, :s, :t)"),
                                             {"c": cid, "e": emp, "k": kind, "s": "working" if kind == "check_in" else "checked_out", "t": utc(f"2026-09-{day}T{hour}:00:00")})
                await db.commit()

                shown = await payroll.calculate_period_snapshot(db, uuid.UUID(cid), date(2026, 9, 26), date(2026, 10, 10))
                done = await payroll.run_payroll_autoclose_049L(db, now_utc=utc("2026-10-12T02:00:00"))
                assert [d["status"] for d in done] == ["closed"], done
                again = await payroll.run_payroll_autoclose_049L(db, now_utc=utc("2026-10-12T02:05:00"))
                assert again == [], "correrlo otra vez no cierra de nuevo"

                rows = (await db.execute(text("SELECT period_type, starts_at, ends_at, period_start, period_end, status, totals_json, currency FROM payroll_periods"))).mappings().all()
                assert len(rows) == 1
                row = rows[0]
                assert row["period_type"] == "cutoff" and row["status"] == "closed" and row["currency"] == "COP"
                assert (row["period_start"], row["period_end"]) == (date(2026, 9, 26), date(2026, 10, 10))
                assert row["starts_at"] == utc("2026-09-26T05:00:00") and row["ends_at"].isoformat().startswith("2026-10-11T04:59:59"), "limites en hora de Bogota"
                totals = row["totals_json"] if isinstance(row["totals_json"], dict) else json.loads(row["totals_json"])
                for key in ("people", "closed_shifts", "regular_minutes", "extra_minutes", "gross_amount", "discount_amount", "net_amount"):
                    assert totals[key] == shown["totals"][key], key
                assert totals["people"] == 4 and totals["closed_shifts"] == 8
                items = (await db.execute(text("SELECT count(*) FROM payroll_period_items"))).scalar()
                assert items == 4

                manual = await payroll.close_period_core_049L(db, uuid.UUID(cid), date(2026, 9, 29), date(2026, 9, 29), name="Prueba", currency="COP")
                kind = (await db.execute(text("SELECT period_type FROM payroll_periods WHERE id = CAST(:i AS uuid)"), {"i": manual})).scalar()
                assert kind == "manual"
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_056L_turno_trae_conectado_pausas_y_trabajado_sin_cambiar_el_pago(pg_url, monkeypatch):
    """Solo presentacion: Conectado | Pausas | Trabajado (trabajado = conectado - pausas)
    en cada turno; ordinarias, extra y valor siguen saliendo del calculo de siempre."""
    async def no_storage(db):
        return None

    monkeypatch.setattr(payroll, "ensure_payroll_storage", no_storage)

    async def run():
        engine = create_async_engine(pg_url)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with maker() as db:
                cid, emp = str(uuid.uuid4()), str(uuid.uuid4())
                await db.execute(text("INSERT INTO companies (id, name) VALUES (CAST(:c AS uuid), 'Tiempos')"), {"c": cid})
                await db.execute(text("INSERT INTO employees (id, company_id, full_name, role, hourly_rate_regular, hourly_rate_extra) VALUES "
                                      "(CAST(:e AS uuid), CAST(:c AS uuid), 'Katerine', 'operaria', 6000, 9000)"), {"e": emp, "c": cid})
                # 12:00 -> 22:30 UTC conectada (10 h 30), pausas 14:00-14:30 y 18:00-18:15 (45 min).
                for kind, at, st in (("check_in", "2026-10-20T12:00:00", "working"), ("break_start", "2026-10-20T14:00:00", "on_break"),
                                     ("break_end", "2026-10-20T14:30:00", "working"), ("break_start", "2026-10-20T18:00:00", "on_break"),
                                     ("break_end", "2026-10-20T18:15:00", "working"), ("check_out", "2026-10-20T22:30:00", "checked_out")):
                    await db.execute(text("INSERT INTO workforce_attendance_events (company_id, employee_id, event_type, status_after, occurred_at) VALUES "
                                          "(CAST(:c AS uuid), CAST(:e AS uuid), :k, :s, :t)"), {"c": cid, "e": emp, "k": kind, "s": st, "t": utc(at)})
                await db.commit()
                snap = await payroll.calculate_period_snapshot(db, uuid.UUID(cid), date(2026, 10, 19), date(2026, 10, 21))
                row = next(r for r in snap["rows"] if str(r["employee_id"]) == emp)
                [shift] = row["shifts"]
                assert (shift["connected_minutes"], shift["pause_minutes"], shift["worked_minutes"]) == (630, 45, 585)
                assert shift["regular_minutes"] + shift["extra_minutes"] == shift["worked_minutes"], "se paga el tiempo trabajado (pausas excluidas)"
                assert (shift["regular_minutes"], shift["extra_minutes"]) == (480, 105)
                assert shift["gross_amount"] == "63750.00", "8 h x 6000 + 1 h 45 x 9000: el pago no cambia"
        finally:
            await engine.dispose()

    asyncio.run(run())
