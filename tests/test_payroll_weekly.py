"""Fase B · limite de horas ordinarias por periodo (como siempre) o por semana.

- Por semana: el limite se aplica a cada semana de lunes a domingo en la zona
  de la empresa (el turno cuenta en la semana en que empezo).
- Por periodo (por defecto): el calculo de siempre, sin ningun cambio.
"""
from __future__ import annotations

import pytest

from app.api.v1.endpoints import payroll
from app.services import company_locale as cl


def shift(start: str, minutes: int) -> dict:
    return {"start": start, "regular_minutes": min(minutes, 480), "extra_minutes": max(minutes - 480, 0)}


# VOLTAGE (Chicago): 6 turnos de 8 h = 48 h; lun 26 oct a vie 30 oct (40 h) + lun 2 nov (8 h).
SHIFTS = [shift(f"2026-10-{d}T14:00:00+00:00", 480) for d in (26, 27, 28, 29, 30)] + [shift("2026-11-02T15:00:00+00:00", 480)]


def test_weekly_split_by_monday_to_sunday_in_company_timezone():
    tokens = cl.use({"currency": "USD", "timezone": "America/Chicago"})
    try:
        assert payroll._weekly_split_052D(SHIFTS, 40 * 60) == (48 * 60, 0), "40 h una semana y 8 h la otra: nada extra"
        assert payroll._weekly_split_052D(SHIFTS, 32 * 60) == (32 * 60 + 8 * 60, 8 * 60), "por semana: 8 h extra"
        # Domingo 1 nov 23:00 en Chicago (05:00Z del lunes 2): sigue siendo de la semana del 26 oct.
        late = SHIFTS[:5] + [shift("2026-11-02T05:00:00+00:00", 120)]
        assert payroll._weekly_split_052D(late, 40 * 60) == (40 * 60, 120)
    finally:
        cl.reset(tokens)


def snapshot():
    row = {"employee_id": "e1", "regular_minutes": 48 * 60, "extra_minutes": 0, "hourly_rate_regular": 10.0, "hourly_rate_extra": 15.0,
           "discount_amount": 0.0, "shifts": SHIFTS}
    return {"rows": [row], "totals": {}}


@pytest.mark.asyncio
@pytest.mark.parametrize("scope,regular,extra", [("period", 40 * 60, 8 * 60), ("week", 48 * 60, 0)])
async def test_rule_by_period_like_always_or_by_week(monkeypatch, scope, regular, extra):
    async def rule(db, company_id):
        return {"enabled": True, "ordinary_hours_limit": 40.0, "ordinary_minutes_limit": 2400}

    async def hours_scope(db, company_id):
        return scope

    monkeypatch.setattr(payroll, "_cx_company_payroll_rule", rule)
    monkeypatch.setattr(payroll, "_payroll_hours_scope_052D", hours_scope)
    tokens = cl.use({"currency": "USD", "timezone": "America/Chicago"})
    try:
        out = await payroll._cx_apply_payroll_config_rule(None, "c1", snapshot())
    finally:
        cl.reset(tokens)
    row = out["rows"][0]
    assert (row["regular_minutes"], row["extra_minutes"]) == (regular, extra)
    assert row["gross_amount"] == round(regular / 60 * 10 + extra / 60 * 15, 2)
    assert out["payroll_rule"]["limit_scope"] == scope


def test_payroll_rule_label_has_no_broken_letters():
    """La etiqueta de la regla ("después") se veia como "despuÃ©s" en Nomina."""
    from pathlib import Path

    source = Path("app/api/v1/endpoints/payroll.py").read_text(encoding="utf-8")
    assert "despuÃ" not in source
    assert source.count("ordinarias; después extra.") == 2
