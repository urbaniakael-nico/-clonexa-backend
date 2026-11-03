"""El limite de turno sale del valor de cada empresa (workforce_session_policy.alert_after_hours),
contra Postgres REAL: con 15 h (VOLTAGE) un turno de 13 h no avisa, no queda "por confirmar" y no
se cierra desde el portal; uno de 16 h si. Otra empresa sigue con su valor. Si pgserver no esta
instalado, se salta."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytest.importorskip("pgserver")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.api.v1.endpoints import open_shifts as routes  # noqa: E402
from app.api.v1.endpoints import payroll as core  # noqa: E402
from app.services import open_shift_alert, session_cutoff  # noqa: E402
from tests.test_bot_punch_open_shift_pg import _company, _employee, _open_shift, maker, pg_url  # noqa: E402,F401

ROOT = Path(__file__).resolve().parents[1]
BOSS = {"role": "supervisor", "name": "Sofía (supervisor)", "user_id": None}


async def _setup(maker, limit: float | None):  # noqa: F811
    cid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    async with maker() as db:
        await _company(db, cid, {"open_shift_alert": True})
        if limit is not None:
            await db.execute(text("INSERT INTO workforce_session_policy (company_id, alert_after_hours) VALUES (CAST(:c AS uuid), :h)"), {"c": cid, "h": limit})
            await db.commit()
        people = {}
        for name, hours, tg in (("Trece", 13, "1301"), ("Dieciseis", 16, "1601")):
            people[name] = await _employee(db, cid, name, tg=tg)
            await _open_shift(db, cid, people[name], now - timedelta(hours=hours))
    return cid, people, now


async def _alerted(db, cid) -> set[str]:
    sent: list[str] = []

    async def send(chat, _message):
        sent.append(chat)

    async def language_of(_tg):
        return "es"

    await open_shift_alert.run_company(db, cid, send=send, language_of=language_of)
    return set(sent)


async def _verdict(db, cid, hours: int) -> str:
    ctx = await core._cx_verification_context_049D(db, cid)
    start = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    return core._cx_check_shift_049D(ctx, "attendance", str(uuid.uuid4()), start, start + timedelta(hours=hours), False)[0]


async def test_con_15_h_el_de_13_no_avisa_ni_queda_por_confirmar_y_el_de_16_si(maker):  # noqa: F811
    cid, people, now = await _setup(maker, 15)
    async with maker() as db:
        assert await open_shift_alert.alert_hours(db, cid) == 15
        assert await _alerted(db, cid) == {"1601"}, "solo el de 16 h"
        assert await _verdict(db, cid, 13) == "pay" and await _verdict(db, cid, 15) == "pay", "13 y 15 h cuentan normal"
        assert await _verdict(db, cid, 16) == "hold", "16 h queda por confirmar"
        listed = await routes.get_open_shifts(uuid.UUID(cid), who=BOSS, db=db)
        assert listed["alert_hours"] == 15 and [s["employee_name"] for s in listed["shifts"]] == ["Dieciseis"]
        with pytest.raises(HTTPException) as exc:
            await routes.post_close(uuid.UUID(cid), uuid.UUID(people["Trece"]), body={"end_at": now.isoformat(), "note": "Olvidó finalizar"}, who=BOSS, db=db)
        assert exc.value.status_code == 400 and exc.value.detail == "Este turno aún no supera 15 horas"
        done = await routes.post_close(uuid.UUID(cid), uuid.UUID(people["Dieciseis"]), body={"end_at": (now - timedelta(hours=1)).isoformat(), "note": "Olvidó finalizar"}, who=BOSS, db=db)
        assert done["ok"]


@pytest.mark.parametrize("limit,expected", [(None, 12), (10, 10)])
async def test_otra_empresa_sigue_con_su_valor(maker, limit, expected):  # noqa: F811
    await _setup(maker, 15)  # VOLTAGE con 15 no cambia a nadie mas
    cid, _people, _now = await _setup(maker, limit)
    async with maker() as db:
        assert await open_shift_alert.alert_hours(db, cid) == expected
        assert await _alerted(db, cid) == {"1301", "1601"}, "13 h ya pasa su limite"
        assert await _verdict(db, cid, 13) == "hold"
        assert await _verdict(db, cid, 9) == "pay"
        assert (await routes.get_open_shifts(uuid.UUID(cid), who=BOSS, db=db))["alert_hours"] == expected


def test_no_queda_un_limite_escrito_a_mano():
    assert open_shift_alert.DEFAULT_HOURS == session_cutoff.DEFAULT_ALERT_HOURS, "un solo valor por defecto"
    assert re.search(r"^DEFAULT_HOURS = DEFAULT_ALERT_HOURS$", (ROOT / "app/services/open_shift_alert.py").read_text(encoding="utf-8"), re.M)
    registry = json.loads((ROOT / "app/services/switch_registry.json").read_text(encoding="utf-8"))
    for switch in registry["switches"]:
        if switch["key"] in ("reports_board", "open_shift_alert", "us_payroll"):
            assert not re.search(r"\b12 ?h\b", json.dumps(switch, ensure_ascii=False)), switch["key"]
    for path in ("app/web/open_shifts.js", "app/web/reports_board.js", "app/web/payroll_v2.js", "app/services/reports_board_export.py",
                 "app/services/us_payroll_export.py", "app/services/reports_board.py", "app/services/open_shift_alert.py"):
        assert not re.search(r"\b12 ?(h|horas|hours)\b", (ROOT / path).read_text(encoding="utf-8")), path
