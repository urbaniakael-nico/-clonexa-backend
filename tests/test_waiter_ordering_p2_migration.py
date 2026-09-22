import importlib.util
from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "migrations" / "versions" / "021d_waiter_ordering_p2.py"
)


class FakeOp:
    def __init__(self):
        self.statements = []

    def execute(self, stmt):
        self.statements.append(str(stmt))


def load_migration():
    spec = importlib.util.spec_from_file_location("waiter_ordering_p2", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_id_is_at_most_32_chars_and_chains_onto_ttm():
    module = load_migration()
    assert len(module.revision) <= 32
    assert module.revision == "021d_waiter_ordering_p2"
    assert module.down_revision == "021c_waiter_ordering_ttm"


def test_upgrade_creates_new_tables_and_columns(monkeypatch):
    module = load_migration()
    fake_op = FakeOp()
    monkeypatch.setattr(module, "op", fake_op)

    module.upgrade()

    joined = "\n".join(fake_op.statements)
    assert "CREATE TABLE IF NOT EXISTS hospitality_product_portions" in joined
    assert "CREATE TABLE IF NOT EXISTS hospitality_product_images" in joined
    assert "ALTER TABLE hospitality_categories ADD COLUMN IF NOT EXISTS requires_term" in joined
    assert "ALTER TABLE mini_panel_work_sessions ADD COLUMN IF NOT EXISTS closed_reason" in joined


def test_downgrade_never_drops_the_pre_existing_tables(monkeypatch):
    module = load_migration()
    fake_op = FakeOp()
    monkeypatch.setattr(module, "op", fake_op)

    module.downgrade()

    joined = "\n".join(fake_op.statements)
    assert "DROP TABLE IF EXISTS hospitality_categories" not in joined
    assert "DROP TABLE IF EXISTS mini_panel_work_sessions" not in joined
    # Only this migration's own additions come down.
    assert "DROP TABLE IF EXISTS hospitality_product_portions" in joined
    assert "DROP TABLE IF EXISTS hospitality_product_images" in joined
    assert "DROP COLUMN IF EXISTS requires_term" in joined
    assert "DROP COLUMN IF EXISTS closed_reason" in joined
