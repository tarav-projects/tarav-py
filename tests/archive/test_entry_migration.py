"""Archive entry-name migration preserves Records and prior Git evidence."""

import importlib.util
from pathlib import Path
import subprocess

import pytest

from tarav.l1.archive import Archive, ArchiveError


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_archive_directory_entries_migrate_to_main_json(tmp_path: Path) -> None:
    source = Path(__file__).parents[2] / "tooling/migrate_archive_directory_entries.py"
    spec = importlib.util.spec_from_file_location("archive_entry_migration", source)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    archive = Archive.create(tmp_path / "archive")
    artifact = archive.register_artifact(locator="https://example.com/evidence")
    records = archive.records_root
    artifact_root = archive.artifacts_root / artifact.id
    archive_record = (records / "main.json").read_bytes()
    artifact_record = (artifact_root / "main.json").read_bytes()

    (records / "main.json").rename(records / "archive.json")
    (artifact_root / "main.json").rename(artifact_root / "registration.json")
    git(records, "add", ".")
    git(
        records,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-m",
        "Retain legacy Archive entry names",
    )

    with pytest.raises(ArchiveError, match="main.json"):
        Archive.open(archive.root)
    plan = migration.migrate(archive.root)
    assert plan["moved_files"] == 2
    assert not (records / "main.json").exists()

    result = migration.migrate(archive.root, apply=True)
    assert result["checkpoint"] == git(records, "rev-parse", "HEAD")
    assert not (records / "archive.json").exists()
    assert not (artifact_root / "registration.json").exists()
    assert (records / "main.json").read_bytes() == archive_record
    assert (artifact_root / "main.json").read_bytes() == artifact_record
    assert git(records, "show", "HEAD:archive.json")
    assert git(records, "show", f"HEAD:artifacts/{artifact.id}/registration.json")
    assert Archive.open(archive.root).record(artifact.id).doi == artifact.id
