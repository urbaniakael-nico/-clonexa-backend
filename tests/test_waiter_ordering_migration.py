import importlib.util
import uuid
from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "migrations" / "versions" / "021c_waiter_ordering_ttm.py"
)


class FakeResult:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


class FakeBind:
    def __init__(self, responses):
        # responses: list of rows/None returned in order by successive SELECTs.
        self._responses = list(responses)
        self.calls = []

    def execute(self, stmt, params=None):
        text = str(stmt)
        self.calls.append((text, params))
        if "SELECT" in text:
            row = self._responses.pop(0) if self._responses else None
            return FakeResult(row)
        return None


class FakeOp:
    def __init__(self, bind):
        self._bind = bind

    def get_bind(self):
        return self._bind


def load_migration():
    spec = importlib.util.spec_from_file_location("waiter_ordering_ttm", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_target_company_is_asadero_el_socio_only():
    module = load_migration()
    assert module.TARGET_COMPANY_ID == "7625872c-f941-4479-a27b-f8443be953c5"


def test_revision_chains_onto_the_previous_hospitality_migration():
    module = load_migration()
    assert module.revision == "021c_waiter_ordering_ttm"
    assert module.down_revision == "021b_hsp_board_ttm"
    assert len(module.revision) <= 32


def test_upgrade_creates_the_module_once_and_scopes_company_modules_to_asadero(monkeypatch):
    module = load_migration()
    module_id = uuid.uuid4()
    # 1st SELECT: modules by code -> not found. 2nd SELECT: company_modules row -> not found.
    bind = FakeBind([None, None])
    monkeypatch.setattr(module, "op", FakeOp(bind))

    module.upgrade()

    insert_module_call = next(c for c in bind.calls if "INSERT INTO modules" in c[0])
    assert insert_module_call[1]["code"] == "waiter_ordering"

    insert_company_module_call = next(c for c in bind.calls if "INSERT INTO company_modules" in c[0])
    assert insert_company_module_call[1]["company_id"] == module.TARGET_COMPANY_ID
    import json
    settings = json.loads(insert_company_module_call[1]["settings"])
    assert settings["kitchen_user_limit"] == 2
    assert settings["cashier_user_limit"] == 1
    assert settings["stations"] == ["parrilla", "freidora", "bebidas", "otros"]


def test_upgrade_is_idempotent_when_the_company_module_already_exists(monkeypatch):
    module = load_migration()
    module_id = uuid.uuid4()
    existing_module = {"id": module_id}
    existing_company_module = {"id": uuid.uuid4()}
    bind = FakeBind([existing_module, existing_company_module])
    monkeypatch.setattr(module, "op", FakeOp(bind))

    module.upgrade()

    assert not any("INSERT INTO modules" in c[0] for c in bind.calls)
    assert not any("INSERT INTO company_modules" in c[0] for c in bind.calls)


def test_upgrade_reuses_the_module_when_it_already_exists_for_another_feature(monkeypatch):
    module = load_migration()
    module_id = uuid.uuid4()
    bind = FakeBind([{"id": module_id}, None])
    monkeypatch.setattr(module, "op", FakeOp(bind))

    module.upgrade()

    assert not any("INSERT INTO modules" in c[0] for c in bind.calls)
    insert_company_module_call = next(c for c in bind.calls if "INSERT INTO company_modules" in c[0])
    assert insert_company_module_call[1]["module_id"] == module_id


def test_downgrade_disables_only_the_target_company_and_leaves_the_module_if_shared(monkeypatch):
    module = load_migration()
    module_id = uuid.uuid4()
    # 1st SELECT: module by code found. 2nd SELECT (inside DELETE's NOT EXISTS) not modeled here,
    # DELETE is not a SELECT so FakeBind just records it.
    bind = FakeBind([{"id": module_id}])
    monkeypatch.setattr(module, "op", FakeOp(bind))

    module.downgrade()

    disable_call = next(c for c in bind.calls if "UPDATE company_modules" in c[0])
    assert disable_call[1]["company_id"] == module.TARGET_COMPANY_ID
    assert disable_call[1]["module_id"] == module_id
    assert any("DELETE FROM modules" in c[0] for c in bind.calls)
