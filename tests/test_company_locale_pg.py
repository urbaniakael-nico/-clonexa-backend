"""Fase A contra Postgres REAL (pgserver + asyncpg).

- Guardar Ajustes (la funcion de siempre) valida la zona y la copia a
  companies.timezone; get_company_locale lee la de Ajustes con respaldo.
- Nomina de una empresa en America/Chicago (VOLTAGE): limites del periodo en su
  zona, turnos que cruzan medianoche y el fin del horario de verano (1 de
  noviembre de 2026: a las 2:00 CDT vuelve a la 1:00 CST, esa noche dura 1 h
  mas). La misma marcacion en una empresa de Bogota da lo de siempre.
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

from app.api.v1.endpoints import core_settings, payroll  # noqa: E402
from app.services import company_locale  # noqa: E402

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
"""


@pytest.fixture(scope="module")
def pg_url():
    folder = tempfile.mkdtemp(prefix="cx_pg_locale_")
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


def run(url, fn):
    async def go():
        engine = create_async_engine(url)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with maker() as db:
                return await fn(db)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def test_saving_settings_validates_and_syncs_companies_timezone(pg_url):
    async def fn(db):
        cid = str(uuid.uuid4())
        await db.execute(text("INSERT INTO companies (id, name) VALUES (CAST(:c AS uuid), 'VOLTAGE')"), {"c": cid})
        await db.commit()
        assert await company_locale.get_company_locale(db, cid) == {"currency": "COP", "timezone": "America/Bogota", "language": "es", "decimals": 0}
        actor = {"admin_v2": True, "role": "admin_v2"}
        body = core_settings.CoreSettingsIn(language="es", session_timeout_minutes=30, currency="USD", timezone="America/Chicago")
        out = await core_settings.update_company_core_settings(cid, body, db, None, actor)
        assert out["currency"] == "USD" and out["timezone"] == "America/Chicago"
        tz = (await db.execute(text("SELECT timezone FROM companies WHERE id = CAST(:c AS uuid)"), {"c": cid})).scalar()
        assert tz == "America/Chicago", "companies.timezone sincronizada"
        assert await company_locale.get_company_locale(db, cid) == {"currency": "USD", "timezone": "America/Chicago", "language": "es", "decimals": 2}
        with pytest.raises(Exception) as bad:
            await core_settings.update_company_core_settings(cid, core_settings.CoreSettingsIn(currency="USD", timezone="Chicago"), db, None, actor)
        assert getattr(bad.value, "status_code", None) == 400
        tz = (await db.execute(text("SELECT timezone FROM companies WHERE id = CAST(:c AS uuid)"), {"c": cid})).scalar()
        assert tz == "America/Chicago", "una zona invalida no se guarda"

    run(pg_url, fn)


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def test_payroll_respects_company_timezone_and_the_end_of_daylight_saving(pg_url):
    async def fn(db):
        snaps = {}
        for name, tzname in (("chicago", "America/Chicago"), ("bogota", "America/Bogota")):
            cid, emp = str(uuid.uuid4()), str(uuid.uuid4())
            await db.execute(text("INSERT INTO companies (id, name, timezone) VALUES (CAST(:c AS uuid), :n, :tz)"), {"c": cid, "n": name, "tz": tzname})
            await db.execute(text("INSERT INTO company_core_settings (company_id, currency, timezone, language) VALUES (CAST(:c AS uuid), 'USD', :tz, 'es')"), {"c": cid, "tz": tzname})
            await db.execute(text("INSERT INTO employees (id, company_id, full_name, role, hourly_rate_regular, hourly_rate_extra) VALUES (CAST(:e AS uuid), CAST(:c AS uuid), 'Ana', 'operario', 10, 15)"),
                             {"e": emp, "c": cid})
            shifts = [
                # 31 oct 22:00 CDT (03:00Z) -> 1 nov 06:00 CST (12:00Z): cruza medianoche y el cambio de hora = 9 h reales.
                ("2026-11-01T03:00:00", "2026-11-01T12:00:00"),
                # 02:00Z -> 05:30Z del 9 nov: en Chicago (CST, UTC-6) es 8 nov 20:00 -> 23:30, DENTRO del periodo;
                # en Bogota (UTC-5) termina el 9 nov a las 00:30, FUERA del periodo.
                ("2026-11-09T02:00:00", "2026-11-09T05:30:00"),
            ]
            for start, end in shifts:
                for kind, at in (("check_in", start), ("check_out", end)):
                    await db.execute(text("INSERT INTO workforce_attendance_events (company_id, employee_id, event_type, status_after, occurred_at) VALUES "
                                          "(CAST(:c AS uuid), CAST(:e AS uuid), :k, :s, :t)"),
                                     {"c": cid, "e": emp, "k": kind, "s": "working" if kind == "check_in" else "checked_out", "t": utc(at)})
            await db.commit()
            snaps[name] = await payroll.calculate_period_snapshot(db, uuid.UUID(cid), date(2026, 10, 26), date(2026, 11, 8))
        chicago = snaps["chicago"]["rows"][0]
        assert [s["start"] for s in chicago["shifts"]] == ["2026-11-01T03:00:00+00:00", "2026-11-09T02:00:00+00:00"], "el dia 8 en hora de Chicago entra"
        assert chicago["shifts"][0]["regular_minutes"] + chicago["shifts"][0]["extra_minutes"] == 540, "9 horas reales la noche del cambio de hora"
        bogota = snaps["bogota"]["rows"][0]
        assert [s["start"] for s in bogota["shifts"]] == ["2026-11-01T03:00:00+00:00"], "en Bogota ese turno termina el 9: no entra"
        assert company_locale.current_zone().key == "America/Bogota", "la zona de la empresa no se queda pegada"

    run(pg_url, fn)
