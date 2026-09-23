import importlib.util
import json
from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "migrations" / "versions" / "021i_wo_kitchen_roster.py"
)


class FakeOp:
    def __init__(self):
        self.statements = []

    def execute(self, stmt):
        self.statements.append(str(stmt))


def load_migration():
    spec = importlib.util.spec_from_file_location("wo_kitchen_roster", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_id_fits_and_chains_onto_021h():
    module = load_migration()
    assert len(module.revision) <= 32
    assert module.down_revision == "021h_wo_cashier_direct"


def test_upgrade_turns_the_switch_on_for_asadero_el_socio_only(monkeypatch):
    module = load_migration()
    fake_op = FakeOp()
    monkeypatch.setattr(module, "op", fake_op)
    module.upgrade()
    joined = "\n".join(fake_op.statements)
    assert module.TARGET_COMPANY_ID == "7625872c-f941-4479-a27b-f8443be953c5"
    assert f"cm.company_id = '{module.TARGET_COMPANY_ID}'::uuid" in joined
    assert "COALESCE(cm.settings, '{}'::jsonb) ||" in joined
    assert json.loads(module.SETTINGS_PATCH) == {"kitchen_roster": True}


def test_downgrade_removes_only_that_key(monkeypatch):
    module = load_migration()
    fake_op = FakeOp()
    monkeypatch.setattr(module, "op", fake_op)
    module.downgrade()
    joined = "\n".join(fake_op.statements)
    assert "- 'kitchen_roster'" in joined
    assert "kitchen_board_columns" not in joined
