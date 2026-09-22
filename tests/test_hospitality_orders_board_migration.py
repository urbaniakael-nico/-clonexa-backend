import importlib.util
import json
import uuid
from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "migrations" / "versions" / "021b_hsp_board_ttm.py"
)


class FakeResult:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


class FakeBind:
    def __init__(self, row):
        self.row = row
        self.calls = []

    def execute(self, stmt, params=None):
        text = str(stmt)
        self.calls.append((text, params))
        if "SELECT" in text:
            return FakeResult(self.row)
        return None


class FakeOp:
    def __init__(self, bind):
        self._bind = bind

    def get_bind(self):
        return self._bind


def load_migration():
    spec = importlib.util.spec_from_file_location("hsp_board_ttm", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_target_company_is_the_time_machine_only():
    module = load_migration()
    assert module.TARGET_COMPANY_ID == "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4"


def test_revision_chains_onto_the_latest_migration():
    module = load_migration()
    assert module.revision == "021b_hsp_board_ttm"
    assert module.down_revision == "021a_mini_panel_quotes_module"


def test_upgrade_only_queries_and_updates_the_time_machine_company(monkeypatch):
    module = load_migration()
    row_id = uuid.uuid4()
    row = {"id": row_id, "settings": {"qr_config": {"mode": "hospitality", "max_capacity": 50}}}
    bind = FakeBind(row)
    monkeypatch.setattr(module, "op", FakeOp(bind))

    module.upgrade()

    assert len(bind.calls) == 2
    select_text, select_params = bind.calls[0]
    assert "company_modules" in select_text
    assert select_params == {"company_id": module.TARGET_COMPANY_ID}

    update_text, update_params = bind.calls[1]
    assert "UPDATE company_modules" in update_text
    assert update_params["id"] == row_id
    settings = json.loads(update_params["settings"])
    assert settings["qr_config"]["orders_board"] == "mesas"
    assert settings["qr_config"]["max_capacity"] == 50, "existing qr_config keys must survive the switch"


def test_upgrade_is_a_noop_when_the_company_has_no_qr_module(monkeypatch):
    module = load_migration()
    bind = FakeBind(None)
    monkeypatch.setattr(module, "op", FakeOp(bind))

    module.upgrade()

    assert len(bind.calls) == 1, "no UPDATE should run when the SELECT finds nothing"


def test_downgrade_removes_only_the_orders_board_key(monkeypatch):
    module = load_migration()
    row_id = uuid.uuid4()
    row = {"id": row_id, "settings": {"qr_config": {"orders_board": "mesas", "mode": "hospitality"}}}
    bind = FakeBind(row)
    monkeypatch.setattr(module, "op", FakeOp(bind))

    module.downgrade()

    _, update_params = bind.calls[1]
    settings = json.loads(update_params["settings"])
    assert "orders_board" not in settings["qr_config"]
    assert settings["qr_config"]["mode"] == "hospitality"
