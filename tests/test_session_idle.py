"""Cierre automatico de sesiones sin actividad (TODAS las empresas).

- Apagado por defecto (CLONEXA_SESSION_IDLE_HOURS vacio, 0 o invalido).
- Nunca por debajo de la vida del token (8 h).
- Cierra SOLO sesiones 'active' sin actividad en N horas, con el motivo
  'expirada_por_inactividad'; no toca otras empresas ni otros estados.
- Corre como mucho una vez por hora y un fallo nunca frena el corte diario.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import session_cutoff, session_idle

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


class SessionsDb:
    """Tabla clonexa_access_sessions en memoria; aplica el WHERE de cada consulta."""

    def __init__(self):
        s = lambda key, cid, scope, status, hours: {"session_key": key, "company_id": cid, "scope": scope, "status": status,  # noqa: E731
                                                    "last_seen_at": NOW - timedelta(hours=hours), "closed_at": None, "closed_reason": ""}
        self.rows = [
            s("activa-hoy", "ttm", "client", "active", 2),
            s("activa-ayer", "ttm", "client", "active", 30),
            s("vieja-portal", "ttm", "client", "active", 100),
            s("vieja-mini", "asadero", "mini_panel", "active", 80),
            s("vieja-admin", None, "admin_v2", "active", 500),
            s("ya-cerrada", "ttm", "client", "closed", 900),
            s("justo-72", "velvet", "client", "active", 72),
        ]
        self.commits = 0
        self.sql = []

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.sql.append(sql)
        hit = [r for r in self.rows if r["status"] == "active" and r["last_seen_at"] < params["cutoff"]]
        if sql.startswith("UPDATE"):
            assert "WHERE status = 'active' AND last_seen_at < :cutoff" in sql
            for r in hit:
                r.update(status="closed", closed_at=params["now"], closed_reason=params["reason"])
            return SimpleNamespace(rowcount=len(hit))
        groups = {}
        for r in hit:
            groups[(r["company_id"], r["scope"])] = groups.get((r["company_id"], r["scope"]), 0) + 1
        rows = [{"company_id": c, "scope": sc, "sessions": n} for (c, sc), n in groups.items()]
        return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))

    async def commit(self):
        self.commits += 1


@pytest.mark.parametrize("raw, hours", [("", None), ("0", None), ("-5", None), ("abc", None), ("72", 72), ("24", 24), ("2", 8), ("72.0", 72)])
def test_switch_is_off_by_default_and_never_below_token_life(monkeypatch, raw, hours):
    monkeypatch.setenv(session_idle.ENV, raw)
    assert session_idle.idle_hours() == hours


def test_switch_unset_is_off(monkeypatch):
    monkeypatch.delenv(session_idle.ENV, raising=False)
    assert session_idle.idle_hours() is None


@pytest.mark.asyncio
async def test_closes_only_active_sessions_idle_for_more_than_n_hours():
    db = SessionsDb()
    closed = await session_idle.close_idle_sessions(db, 72, NOW)
    by = {r["session_key"]: r for r in db.rows}
    assert closed == 3
    for key in ("vieja-portal", "vieja-mini", "vieja-admin"):
        assert by[key]["status"] == "closed" and by[key]["closed_reason"] == "expirada_por_inactividad"
        assert by[key]["closed_at"] == NOW
    for key in ("activa-hoy", "activa-ayer", "justo-72"):
        assert by[key]["status"] == "active", f"{key}: con actividad dentro de las 72 h"
    assert by["ya-cerrada"]["closed_reason"] == "" and by["ya-cerrada"]["closed_at"] is None, "no reescribe las ya cerradas"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_preview_counts_without_closing():
    db = SessionsDb()
    preview = await session_idle.preview_idle_sessions(db, 72, NOW)
    assert sorted((p["company_id"] or "-", p["scope"], p["sessions"]) for p in preview) == [
        ("-", "admin_v2", 1), ("asadero", "mini_panel", 1), ("ttm", "client", 1)]
    assert all(r["status"] != "closed" or r["session_key"] == "ya-cerrada" for r in db.rows)
    assert not any(q.startswith("UPDATE") for q in db.sql)
    assert sum(p["sessions"] for p in await session_idle.preview_idle_sessions(db, 24, NOW)) == 5, "con 24 h entran tambien las de ayer"


@pytest.mark.asyncio
async def test_runs_at_most_once_per_hour_and_not_when_off(monkeypatch):
    monkeypatch.setattr(session_idle, "_last_run", None)
    monkeypatch.delenv(session_idle.ENV, raising=False)
    db = SessionsDb()
    assert await session_idle.maybe_close_idle_sessions(db, NOW) is None
    assert db.sql == [], "apagado: ni siquiera consulta"
    monkeypatch.setenv(session_idle.ENV, "72")
    assert await session_idle.maybe_close_idle_sessions(db, NOW) == 3
    assert await session_idle.maybe_close_idle_sessions(db, NOW + timedelta(minutes=30)) is None
    assert await session_idle.maybe_close_idle_sessions(db, NOW + timedelta(minutes=61)) == 1, "justo-72 ya pasa de 72 h"


@pytest.mark.asyncio
async def test_a_failure_never_stops_the_daily_cutoff(monkeypatch):
    """El paso nuevo va en try/except dentro del ciclo del corte diario."""
    import inspect

    source = inspect.getsource(session_cutoff.cutoff_loop)
    assert "maybe_close_idle_sessions" in source
    step = source[source.index("maybe_close_idle_sessions"):]
    assert "except Exception" in step and "await db.rollback()" in step
    assert source.index("run_all_cutoffs") < source.index("maybe_close_idle_sessions"), "el corte diario va primero"
