import importlib.util
from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "migrations" / "versions" / "021k_inv_allows_portions.py"
)


class FakeOp:
    def __init__(self):
        self.statements = []

    def execute(self, stmt):
        self.statements.append(str(stmt))


def load_migration():
    spec = importlib.util.spec_from_file_location("inv_allows_portions", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_id_fits_and_chains_onto_021j():
    module = load_migration()
    assert len(module.revision) <= 32
    assert module.down_revision == "021j_wo_menu_emojis"


def test_upgrade_adds_the_column_off_by_default_and_turns_on_only_asadero_pollo(monkeypatch):
    module = load_migration()
    fake_op = FakeOp()
    monkeypatch.setattr(module, "op", fake_op)
    module.upgrade()
    sql = "\n".join(fake_op.statements)
    assert "ADD COLUMN IF NOT EXISTS allows_portions boolean NOT NULL DEFAULT false" in sql
    assert "to_regclass('public.inventory_items') IS NOT NULL" in sql      # fresh DB: no-op
    assert module.TARGET_COMPANY_ID == "7625872c-f941-4479-a27b-f8443be953c5"
    assert f"company_id = '{module.TARGET_COMPANY_ID}'::uuid" in sql
    assert "IN ('pollo', 'pollos')" in sql
    assert "split_part(" in sql                                            # first word only
    assert sql.count("SET allows_portions = TRUE") == 1


def test_downgrade_turns_back_off_only_those_products(monkeypatch):
    module = load_migration()
    fake_op = FakeOp()
    monkeypatch.setattr(module, "op", fake_op)
    module.downgrade()
    sql = "\n".join(fake_op.statements)
    assert "SET allows_portions = FALSE" in sql
    assert module.TARGET_COMPANY_ID in sql
    assert "DROP COLUMN" not in sql
