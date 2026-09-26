from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from tarav.runtime import get_runtime


MIGRATION_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "tooling"
    / "migrate_record_archive_workflow_partition.py"
)
spec = importlib.util.spec_from_file_location("partition_migration", MIGRATION_SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
migrate = module.migrate


def test_workflow_partition_migration_moves_the_complete_tree(tmp_path) -> None:
    root = tmp_path / "archive"
    source = root / "test"
    retained = source / "run" / "named" / "objects" / "item.json"
    retained.parent.mkdir(parents=True)
    content = '{"type":"Tarav.Test.Item"}\n'
    retained.write_text(content)

    preview = migrate(root, "test")
    target = root / str(get_runtime().workflows.get("test").id)
    assert preview["target"] == str(target)
    assert source.is_dir()
    assert not target.exists()

    migrate(root, "test", apply=True)
    assert (target / "run" / "named" / "objects" / "item.json").read_text() == content
    assert not source.exists()


def test_workflow_partition_migration_refuses_an_existing_ship_path(tmp_path) -> None:
    root = tmp_path / "archive"
    (root / "test").mkdir(parents=True)
    target = root / str(get_runtime().workflows.get("test").id)
    target.mkdir()

    with pytest.raises(FileExistsError, match="Ship partition already exists"):
        migrate(root, "test", apply=True)
    assert (root / "test").is_dir()
    assert target.is_dir()
