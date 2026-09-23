import importlib.util
import json
from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "migrations" / "versions" / "021e_waiter_ordering_segs.py"
)


class FakeOp:
    def __init__(self):
        self.statements = []

    def execute(self, stmt):
        self.statements.append(str(stmt))


def load_migration():
    spec = importlib.util.spec_from_file_location("waiter_ordering_segs", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_id_is_at_most_32_chars_and_chains_onto_p2():
    module = load_migration()
    assert len(module.revision) <= 32
    assert module.revision == "021e_waiter_ordering_segs"
    assert module.down_revision == "021d_waiter_ordering_p2"


def test_target_company_is_asadero_el_socio_only():
    module = load_migration()
    assert module.TARGET_COMPANY_ID == "7625872c-f941-4479-a27b-f8443be953c5"


def test_upgrade_turns_on_all_three_segments_with_the_requested_maximums(monkeypatch):
    module = load_migration()
    fake_op = FakeOp()
    monkeypatch.setattr(module, "op", fake_op)

    module.upgrade()

    joined = "\n".join(fake_op.statements)
    assert module.TARGET_COMPANY_ID in joined
    assert "m.code = 'waiter_ordering'" in joined
    patch = json.loads(module.SEGMENTS_PATCH)
    assert patch["segments"]["mesero"]["enabled"] is True
    assert patch["segments"]["cocina"]["enabled"] is True
    assert patch["segments"]["caja"]["enabled"] is True
    assert patch["waiter_user_limit"] == 5


def test_downgrade_only_removes_what_this_migration_added(monkeypatch):
    module = load_migration()
    fake_op = FakeOp()
    monkeypatch.setattr(module, "op", fake_op)

    module.downgrade()

    joined = "\n".join(fake_op.statements)
    assert "- 'segments'" in joined
    assert "- 'waiter_user_limit'" in joined
    # Fase 2's own fields must never be touched by this migration.
    assert "stations" not in joined
    assert "timer_thresholds" not in joined
    assert "shift_max_hours" not in joined
    assert "kitchen_user_limit" not in joined
    assert "cashier_user_limit" not in joined
