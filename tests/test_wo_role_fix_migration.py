import importlib.util
from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "migrations" / "versions" / "021f_wo_role_fix.py"
)


class FakeOp:
    def __init__(self):
        self.statements = []

    def execute(self, stmt):
        self.statements.append(str(stmt))


def load_migration():
    spec = importlib.util.spec_from_file_location("wo_role_fix", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_id_is_at_most_32_chars_and_chains_onto_segs():
    module = load_migration()
    assert len(module.revision) <= 32
    assert module.revision == "021f_wo_role_fix"
    assert module.down_revision == "021e_waiter_ordering_segs"


def test_upgrade_repairs_only_mesero_cocina_caja_rows_for_asadero(monkeypatch):
    module = load_migration()
    fake_op = FakeOp()
    monkeypatch.setattr(module, "op", fake_op)

    module.upgrade()

    joined = "\n".join(fake_op.statements)
    assert module.TARGET_COMPANY_ID in joined
    assert "UPDATE company_users" in joined
    assert "role = settings_json->'mini_panel'->>'type'" in joined
    assert "IN ('mesero', 'cocina', 'caja')" in joined
    assert "role <> settings_json->'mini_panel'->>'type'" in joined


def test_downgrade_is_a_safe_noop(monkeypatch):
    module = load_migration()
    fake_op = FakeOp()
    monkeypatch.setattr(module, "op", fake_op)

    module.downgrade()

    assert fake_op.statements == []
