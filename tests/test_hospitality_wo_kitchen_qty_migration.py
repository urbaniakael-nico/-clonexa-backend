import importlib.util
import json
from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "migrations" / "versions" / "021g_wo_kitchen_qty_btns.py"
)


class FakeOp:
    def __init__(self):
        self.statements = []

    def execute(self, stmt):
        self.statements.append(str(stmt))


def load_migration():
    spec = importlib.util.spec_from_file_location("wo_kitchen_qty_btns", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_id_fits_and_chains_onto_the_role_fix():
    module = load_migration()
    assert len(module.revision) <= 32
    assert module.down_revision == "021f_wo_role_fix"


def test_upgrade_turns_both_switches_on_for_asadero_el_socio_only(monkeypatch):
    module = load_migration()
    fake_op = FakeOp()
    monkeypatch.setattr(module, "op", fake_op)

    module.upgrade()

    joined = "\n".join(fake_op.statements)
    assert module.TARGET_COMPANY_ID == "7625872c-f941-4479-a27b-f8443be953c5"
    assert f"cm.company_id = '{module.TARGET_COMPANY_ID}'::uuid" in joined
    assert "m.code = 'waiter_ordering'" in joined
    # jsonb merge: stations/timers/segments already stored are kept.
    assert "COALESCE(cm.settings, '{}'::jsonb) ||" in joined
    patch = json.loads(module.SETTINGS_PATCH)
    assert patch == {
        "kitchen_board_columns": True,
        "quantity_buttons_enabled": True,
        "quantity_buttons": ["1/4", "1/2", "3/4", "1", "2"],
    }


def test_downgrade_removes_only_the_three_new_keys(monkeypatch):
    module = load_migration()
    fake_op = FakeOp()
    monkeypatch.setattr(module, "op", fake_op)

    module.downgrade()

    joined = "\n".join(fake_op.statements)
    for key in ("kitchen_board_columns", "quantity_buttons_enabled", "quantity_buttons"):
        assert f"- '{key}'" in joined
    assert "segments" not in joined
    assert module.TARGET_COMPANY_ID in joined
