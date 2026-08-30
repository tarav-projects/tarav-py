"""Tarav.Bloberia hosts arbitrary Agent-managed JSON without adding a schema."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from tarav.cli.cli import main
from tarav.bloberia import (
    InvalidTaravBloberiaInputError,
    TaravBloberia,
)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(root), *args),
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def _git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Tarav Bloberia Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "bloberia@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Tarav Bloberia Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "bloberia@example.invalid")


def test_create_initializes_one_git_tracked_files_depot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _git_identity(monkeypatch)
    root = tmp_path / "bloberia"

    bloberia = TaravBloberia.create(root)

    assert bloberia.root == root.resolve()
    assert json.loads((root / "bloberia.json").read_text()) == {
        "class": "Tarav.Bloberia",
        "schema_version": 1,
    }
    assert json.loads((root / "meta.json").read_text()) == {
        "git": ".",
        "git_interval_seconds": 0,
        "schema": "tarav.opaque-record-depot.v1",
        "type": "files",
    }
    assert (root / ".git").is_dir()
    assert _git(root, "status", "--porcelain") == ""


def test_write_preserves_arbitrary_json_without_adding_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _git_identity(monkeypatch)
    bloberia = TaravBloberia.create(tmp_path / "bloberia")
    record = {
        "relationship": "implemented_by",
        "block": "Agent.Hint",
        "code_class": "tarav.bloberia.hosted.TaravBloberia",
        "details": {"confidence": "tentative"},
    }

    assert bloberia.write(record) == record
    assert bloberia.records() == (record,)
    assert "id" not in bloberia.records()[0]


def test_write_accepts_duplicates_and_every_json_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _git_identity(monkeypatch)
    bloberia = TaravBloberia.create(tmp_path / "bloberia")

    for record in ("remember this", ["one", 2], None, {"same": True}, {"same": True}):
        bloberia.write(record)

    records = bloberia.records()
    assert len(records) == 5
    assert "remember this" in records
    assert ["one", 2] in records
    assert None in records
    assert records.count({"same": True}) == 2


def test_search_matches_all_json_content_without_a_consumer_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _git_identity(monkeypatch)
    bloberia = TaravBloberia.create(tmp_path / "bloberia")
    first = {
        "relationship": "implemented_by",
        "block": "Agent.Hint",
        "code_class": "tarav.bloberia.hosted.TaravBloberia",
    }
    bloberia.write(first)
    bloberia.write({"migration_origin": {"anchor": "c20260813-2u"}})

    assert bloberia.search("CODE_CLASS") == (first,)
    assert bloberia.search("tarav.bloberia.hosted") == (first,)
    assert len(bloberia.search("anchor")) == 1
    with pytest.raises(InvalidTaravBloberiaInputError, match="non-empty"):
        bloberia.search("  ")


def test_cli_writes_and_queries_the_default_tarav_data_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _git_identity(monkeypatch)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    assert (
        main(
            [
                "bloberia",
                "write",
                "--record-json",
                '{"block":"Agent.Hint","code_class":"Bloberia"}',
            ]
        )
        == 0
    )
    written = json.loads(capsys.readouterr().out)
    expected_root = home / "Documents" / "tarav" / "bloberia"
    assert written["bloberia"] == str(expected_root.resolve())
    assert written["record"] == {
        "block": "Agent.Hint",
        "code_class": "Bloberia",
    }

    assert main(["bloberia", "query", "--text", "code_class"]) == 0
    queried = json.loads(capsys.readouterr().out)
    assert queried["count"] == 1
    assert queried["records"] == [written["record"]]

    assert main(["bloberia", "query"]) == 0
    all_records = json.loads(capsys.readouterr().out)
    assert all_records["records"] == queried["records"]
    assert _git(expected_root, "status", "--porcelain") == ""


def test_cli_accepts_non_object_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _git_identity(monkeypatch)
    root = tmp_path / "bloberia"

    assert (
        main(
            [
                "bloberia",
                "write",
                "--bloberia",
                str(root),
                "--record-json",
                '["free", "form"]',
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["record"] == ["free", "form"]
