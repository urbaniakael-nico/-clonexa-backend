"""payroll_shift_list: solo con el interruptor (modulo payroll encendido) el
servidor marca ui.shift_list; sin el, period_activity responde igual que siempre."""
from __future__ import annotations

import uuid

import pytest

from app.api.v1.endpoints import payroll_v2


class _Db:
    def __init__(self, row):
        self.row = row

    async def execute(self, statement, params=None):
        row = self.row

        class R:
            def mappings(self):
                return self

            def first(self):
                return row

        return R()


@pytest.mark.asyncio
@pytest.mark.parametrize("row, expected", [
    ({"enabled": True, "settings": {"payroll_shift_list": True}}, True),
    ({"enabled": True, "settings": '{"payroll_shift_list": true}'}, True),
    ({"enabled": False, "settings": {"payroll_shift_list": True}}, False),
    ({"enabled": True, "settings": {"payroll_shift_list": "true"}}, False),
    ({"enabled": True, "settings": {}}, False),
    (None, False),
])
async def test_flag(row, expected):
    assert await payroll_v2.shift_list_on(_Db(row), uuid.uuid4()) is expected


def test_flag_is_registered_and_only_adds_ui():
    from app.services import switch_registry
    import inspect

    sw = next(s for s in switch_registry.registry()["switches"] if s["key"] == "payroll_shift_list")
    assert sw["module"] == "payroll" and payroll_v2.SHIFT_LIST_FLAG == "payroll_shift_list"
    src = inspect.getsource(payroll_v2.period_activity)
    assert 'if await shift_list_on(db, company_id):\n        out["ui"] = {"shift_list": True}' in src
