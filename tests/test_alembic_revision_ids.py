import ast
from pathlib import Path

import pytest

VERSIONS_DIR = Path(__file__).resolve().parent.parent / "migrations" / "versions"
# alembic_version.version_num is VARCHAR(32); a longer revision id makes
# `alembic upgrade` fail in production with StringDataRightTruncationError
# after the migration's own SQL already ran (see commit 38399a4's Railway
# deploy failure on "021b_hsp_orders_board_time_machine", 34 chars).
MAX_REVISION_ID_LENGTH = 32


def _revision_id(path: Path) -> str | None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "revision" for target in node.targets
        ):
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return value.value
    return None


def _migration_files():
    return sorted(VERSIONS_DIR.glob("*.py"))


@pytest.mark.parametrize("path", _migration_files(), ids=lambda p: p.name)
def test_revision_id_fits_alembic_version_column(path):
    revision = _revision_id(path)
    assert revision is not None, f"{path.name} has no `revision = ...` assignment"
    assert len(revision) <= MAX_REVISION_ID_LENGTH, (
        f"{path.name}: revision id {revision!r} is {len(revision)} chars, "
        f"must be <= {MAX_REVISION_ID_LENGTH} (alembic_version.version_num is VARCHAR(32))"
    )
