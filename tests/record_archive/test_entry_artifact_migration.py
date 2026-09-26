from __future__ import annotations

import json
import importlib.util
import sys
from pathlib import Path

import pytest

from tarav.archive.records import ArchiveFolder, ArchiveList
from tarav.test_workflow import TestItem as WorkspaceItem

MIGRATION_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "tooling"
    / "migrate_record_archive_artifacts.py"
)
spec = importlib.util.spec_from_file_location(
    "entry_artifact_migration", MIGRATION_SCRIPT
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
migrate = module.migrate


def test_migration_preserves_old_files_and_reopens_dictionary_and_vector(
    tmp_path,
) -> None:
    named = ArchiveFolder.create(tmp_path / "named", constitution="Old named")
    ordered = ArchiveList.create(tmp_path / "ordered", constitution="Old ordered")
    for archive in (named, ordered):
        (archive.root / "objects").mkdir()
        (archive.root / "objects" / "item.json").write_text(
            json.dumps(WorkspaceItem("retained").to_record()) + "\n", encoding="utf-8"
        )
    (named.root / "entries.json").write_text(
        '{"greeting": "objects/item.json"}\n', encoding="utf-8"
    )
    (ordered.root / "entries.json").write_text(
        '["objects/item.json", "objects/item.json"]\n', encoding="utf-8"
    )

    preview = migrate(tmp_path)
    assert preview["archives"] == 2
    assert preview["entries"] == 3
    assert not (named.root / "entries.before-entry-records.json").exists()

    applied = migrate(tmp_path, apply=True)
    assert applied["archives"] == 2
    assert (named.root / "objects" / "item.json").is_file()
    assert (named.root / "entries.before-entry-records.json").is_file()
    assert (named.root / "artifacts" / "item.json").read_bytes() == (
        named.root / "objects" / "item.json"
    ).read_bytes()
    assert (
        ArchiveFolder.from_path(named.root).get("greeting").open().label == "retained"
    )
    restored = ArchiveList.from_path(ordered.root)
    assert [entry.open().label for entry in restored.ls()] == [
        "retained",
        "retained",
    ]
    assert restored.get(0).record_path != restored.get(1).record_path
    assert migrate(tmp_path, apply=True)["archives"] == 0


def test_migration_detects_conflicts_before_replacing_any_index(tmp_path) -> None:
    archive = ArchiveFolder.create(tmp_path / "named", constitution="Old")
    (archive.root / "objects").mkdir()
    (archive.root / "objects" / "item.json").write_text(
        json.dumps(WorkspaceItem("original").to_record()) + "\n", encoding="utf-8"
    )
    old_index = '{"item": "objects/item.json"}\n'
    (archive.root / "entries.json").write_text(old_index, encoding="utf-8")
    (archive.root / "artifacts" / "item.json").write_text(
        json.dumps(WorkspaceItem("conflict").to_record()) + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="Conflicting migrated artifact"):
        migrate(tmp_path, apply=True)
    assert (archive.root / "entries.json").read_text(encoding="utf-8") == old_index
    assert not (archive.root / "entries.before-entry-records.json").exists()
