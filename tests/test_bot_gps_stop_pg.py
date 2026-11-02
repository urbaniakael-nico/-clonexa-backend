"""bot_gps_stop contra Postgres REAL (pgserver): el interruptor se lee de los
settings de workforce de ESA empresa, y el recordatorio sale una sola vez por
cierre (también con dos ubicaciones al mismo tiempo); un cierre nuevo vuelve a
avisar; cada empresa lleva lo suyo. Si pgserver no está instalado, se salta."""
from __future__ import annotations

import asyncio
import json
import tempfile
import uuid

import pytest

pgserver = pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.services import bot_gps_stop  # noqa: E402
from tests.test_brand_pg import BASE_SCHEMA  # noqa: E402

VOLTAGE = "f1e8f774-f052-49ca-880a-268805f07db0"
EXTRA = """
ALTER TABLE modules ADD COLUMN IF NOT EXISTS is_active boolean DEFAULT true;
CREATE TABLE IF NOT EXISTS employees (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL REFERENCES companies(id), full_name varchar(200));
CREATE TABLE IF NOT EXISTS company_telegram_pending_actions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    telegram_user_id varchar(120) NOT NULL,
    telegram_username varchar(180) NULL,
    employee_id uuid NULL REFERENCES employees(id) ON DELETE CASCADE,
    action varchar(80) NOT NULL,
    payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    expires_at timestamptz NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_company_telegram_pending_action UNIQUE (company_id, telegram_user_id, action)
)
"""


@pytest.fixture(scope="module")
def pg_url():
    folder = tempfile.mkdtemp(prefix="cx_pg_gps_")
    server = pgserver.get_server(folder, cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            for stmt in [s for s in (BASE_SCHEMA + ";" + EXTRA).split(";") if s.strip()]:
                await conn.execute(text(stmt))
        await engine.dispose()

    asyncio.run(setup())
    yield url


async def _company(db, cid: str, workforce_settings: dict | None, enabled: bool = True) -> str:
    await db.execute(text("INSERT INTO companies (id, name) VALUES (CAST(:i AS uuid), :n) ON CONFLICT DO NOTHING"), {"i": cid, "n": cid[:8]})
    mid = (await db.execute(text("SELECT id::text FROM modules WHERE code = 'workforce'"))).scalar()
    if not mid:
        mid = (await db.execute(text("INSERT INTO modules (code, name) VALUES ('workforce', 'workforce') RETURNING id::text"))).scalar()
    if workforce_settings is not None:
        await db.execute(text("INSERT INTO company_modules (company_id, module_id, enabled, settings) VALUES (CAST(:c AS uuid), CAST(:m AS uuid), :e, CAST(:s AS jsonb))"),
                         {"c": cid, "m": mid, "e": enabled, "s": json.dumps(workforce_settings)})
    emp = (await db.execute(text("INSERT INTO employees (company_id, full_name) VALUES (CAST(:c AS uuid), 'Ana') RETURNING id::text"), {"c": cid})).scalar()
    await db.commit()
    return emp


@pytest.mark.asyncio
async def test_switch_per_company_and_one_reminder_per_close(pg_url):
    engine = create_async_engine(pg_url)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    other, disabled, none = (str(uuid.uuid4()) for _ in range(3))
    try:
        async with Session() as db:
            emp = await _company(db, VOLTAGE, {"workforce_v2": True, "bot_gps_stop": True})
            other_emp = await _company(db, other, {"workforce_v2": True})
            await _company(db, disabled, {"bot_gps_stop": True}, enabled=False)
            await _company(db, none, None)
            assert await bot_gps_stop.is_on(db, VOLTAGE) is True
            assert await bot_gps_stop.is_on(db, other) is False, "otra empresa: apagado"
            assert await bot_gps_stop.is_on(db, disabled) is False, "modulo apagado: apagado"
            assert await bot_gps_stop.is_on(db, none) is False
            assert await bot_gps_stop.is_on(db, "no-es-uuid") is False, "nunca revienta"
            assert await bot_gps_stop.is_on(db, VOLTAGE) is True, "la sesión sigue sana tras un error"

        close_a = "2026-11-01T22:00:00+00:00"

        async def claim(cid, employee, marker):
            async with Session() as s:
                return await bot_gps_stop.claim_reminder(s, cid, "7", employee, marker)

        # Dos ubicaciones en vivo al mismo tiempo: un solo recordatorio.
        results = await asyncio.gather(*(claim(VOLTAGE, emp, close_a) for _ in range(6)))
        assert sorted(results) == [False] * 5 + [True]
        assert await claim(VOLTAGE, emp, close_a) is False, "mismo cierre: no se repite"
        assert await claim(VOLTAGE, emp, "2026-11-02T22:00:00+00:00") is True, "cierre nuevo: avisa otra vez"
        assert await claim(other, other_emp, close_a) is True, "otra empresa, mismo Telegram: lo suyo"

        # 059D: "botón atendido" es otra marca del mismo turno; tocarlo varias veces cuenta una.
        async def press(marker):
            async with Session() as s:
                return await bot_gps_stop.claim_reminder(s, VOLTAGE, "7", emp, marker, action=bot_gps_stop.ATTENDED_ACTION)

        presses = await asyncio.gather(*(press("2026-11-02T22:00:00+00:00") for _ in range(4)))
        assert sorted(presses) == [False, False, False, True]
        assert await claim(VOLTAGE, emp, "2026-11-02T22:00:00+00:00") is False, "el botón no reabre el recordatorio"

        async with Session() as db:
            attended = (await db.execute(text("""SELECT count(*) FROM company_telegram_pending_actions
                WHERE action = 'gps_stop_attended' AND company_id = CAST(:c AS uuid)"""), {"c": VOLTAGE})).scalar()
            assert attended == 1
            rows = (await db.execute(text("""SELECT company_id::text AS c, payload_json->>'close' AS close FROM company_telegram_pending_actions
                WHERE action = 'gps_stop_reminded' ORDER BY c"""))).mappings().all()
        assert sorted((r["c"], r["close"]) for r in rows) == sorted([(VOLTAGE, "2026-11-02T22:00:00+00:00"), (other, close_a)])
    finally:
        await engine.dispose()
