"""The developer migration preserves DOI identity and recoverable old bytes."""

import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

from tarav.archive import Archive


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def test_explicit_migration_preserves_identity_payload_and_history(tmp_path):
    source = Path(__file__).parents[2] / "tooling/migrate_793_archive_records.py"
    spec = importlib.util.spec_from_file_location("archive_migration", source)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    archive = Archive.create(tmp_path / "archive")
    payload = tmp_path / "evidence.txt"
    payload.write_text("original evidence")
    doi = archive.reference_file(str(payload))["locator"]["doi"]
    records = archive.records_root
    # Retain a real previous-schema checkpoint, including JSONL observations.
    for path in records.rglob("*"):
        if path.suffix not in {".json", ".jsonl"} or ".git" in path.parts:
            continue
        values = (
            [json.loads(line) for line in path.read_text().splitlines()]
            if path.suffix == ".jsonl"
            else [json.loads(path.read_text())]
        )
        for value in values:
            value["class"] = value.pop("type")
            value["schema_version"] = 1
            value.pop("contract", None)
        path.write_text("".join(json.dumps(v) + "\n" for v in values))
    git(records, "add", ".")
    git(
        records,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-m",
        "Previous schema evidence",
    )
    before = (records / "main.json").read_bytes()
    plan = migration.migrate(archive.root)
    assert plan["changed_files"] >= 4
    assert (records / "main.json").read_bytes() == before
    result = migration.migrate(archive.root, apply=True)
    assert result["checkpoint"] == git(records, "rev-parse", "HEAD")
    assert git(records, "show", "HEAD:main.json") == before.decode().strip()
    retained = Archive.open(archive.root).record(doi)
    assert retained.doi == doi
    assert retained.contract["kind"] == "file-version"
    assert payload.read_text() == "original evidence"
    with pytest.raises(ValueError, match="clean recoverable Git checkpoint"):
        migration.migrate(archive.root, apply=True)
