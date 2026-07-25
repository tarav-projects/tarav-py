# $kw: ^test-edition-history --from Skw.Edition.History.Service --note [DF] service and command-boundary coverage for edition/session history ^c20260725-7u
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pytest

from agentos.bloberia import BloberiaDepot
from agentos.skillware.edition_history import (
    EditionFile,
    EditionHistoryError,
    EditionHistoryService,
)
from agentos.skillware.commands import register_skillware_commands


PROJECT_ID = "b49973ef-a0d1-47d2-b2dc-f12bbbf424a4"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _project(tmp_path: Path) -> tuple[Path, Path, str]:
    root = tmp_path / "project"
    (root / ".agentos").mkdir(parents=True)
    (root / ".agentos" / "project.json").write_text(
        json.dumps(
            {
                "class": "agentos.project",
                "schema_version": 1,
                "project_id": PROJECT_ID,
            }
        ),
        encoding="utf-8",
    )
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "tests@example.com")
    _git(root, "config", "user.name", "Tests")
    source = root / "src" / "example.py"
    source.parent.mkdir()
    source.write_text("first = 1\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(
        root,
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-q",
        "-m",
        "first",
    )
    commit = _git(root, "rev-parse", "HEAD")
    return root, source, commit


def test_resolve_file_uses_project_identity_and_relative_path(tmp_path: Path) -> None:
    _root, source, _commit = _project(tmp_path)

    assert EditionFile.resolve(source) == EditionFile(
        project_id=PROJECT_ID,
        path="src/example.py",
    )


def test_record_is_idempotent_and_list_groups_deterministically(
    tmp_path: Path,
) -> None:
    root, source, first_commit = _project(tmp_path)
    source.write_text("first = 1\nsecond = 2\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(
        root,
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-q",
        "-m",
        "second",
    )
    second_commit = _git(root, "rev-parse", "HEAD")
    service = EditionHistoryService(BloberiaDepot(tmp_path / "bloberia"))

    first = service.record(
        source,
        first_commit[:12],
        "session-b",
        session_started_at="2026-07-25T10:00:00Z",
        evidence={"method": "chatlas-file-write"},
    )
    repeated = service.record(
        source,
        first_commit,
        "session-b",
        session_started_at="2026-07-25T10:00:00Z",
        evidence={"method": "chatlas-file-write"},
    )
    service.record(source, second_commit, "session-c")
    service.record(
        source,
        first_commit,
        "session-a",
        session_started_at="2026-07-25T09:00:00+00:00",
    )

    assert first.created is True
    assert repeated.created is False
    assert repeated.record_id == first.record_id

    history = service.list(source)
    assert history.file == EditionFile(PROJECT_ID, "src/example.py")
    assert len(history.editions) == 2
    first_edition = next(
        edition for edition in history.editions if edition.commit == first_commit
    )
    assert [session.session_id for session in first_edition.sessions] == [
        "session-a",
        "session-b",
    ]
    assert first_edition.sessions[0].started_at == "2026-07-25T09:00:00Z"
    assert first_edition.sessions[1].evidence == {
        "method": "chatlas-file-write"
    }


def test_record_rejects_invalid_session_metadata(tmp_path: Path) -> None:
    _root, source, commit = _project(tmp_path)
    service = EditionHistoryService(BloberiaDepot(tmp_path / "bloberia"))

    with pytest.raises(EditionHistoryError, match="session id"):
        service.record(source, commit, " ")
    with pytest.raises(EditionHistoryError, match="session_started_at"):
        service.record(source, commit, "session", session_started_at="yesterday")
    with pytest.raises(EditionHistoryError, match="evidence"):
        service.record(source, commit, "session", evidence=["not", "an", "object"])  # type: ignore[arg-type]


def test_list_rejects_malformed_matching_record(tmp_path: Path) -> None:
    _root, source, _commit = _project(tmp_path)
    depot = BloberiaDepot(tmp_path / "bloberia")
    depot.create(
        {
            "kind": "skw.edition-session",
            "schema_version": 2,
            "file": {"project_id": PROJECT_ID, "path": "src/example.py"},
            "edition": {
                "commit": "a" * 40,
                "committed_at": "2026-07-25T10:00:00Z",
            },
            "session": {"id": "session", "started_at": None},
            "evidence": {},
        }
    )

    with pytest.raises(EditionHistoryError, match="invalid edition-history record"):
        EditionHistoryService(depot).list(source)


def test_check_requires_history_for_each_explicit_target(tmp_path: Path) -> None:
    root, source, commit = _project(tmp_path)
    other = root / "src" / "other.py"
    other.write_text("other = 1\n", encoding="utf-8")
    service = EditionHistoryService(BloberiaDepot(tmp_path / "bloberia"))
    service.record(source, commit, "session")

    result = service.check([source, other])

    assert result.ok is False
    assert [(finding.code, finding.target) for finding in result.findings] == [
        ("missing-edition-history", "src/other.py")
    ]
    assert service.check([source]).ok is True


def test_check_reports_duplicate_and_malformed_associations(
    tmp_path: Path,
) -> None:
    _root, source, commit = _project(tmp_path)
    depot = BloberiaDepot(tmp_path / "bloberia")
    service = EditionHistoryService(depot)
    service.record(source, commit, "session")
    valid_record = depot.query(
        {
            "value": {
                "kind": "skw.edition-session",
                "file": {
                    "project_id": PROJECT_ID,
                    "path": "src/example.py",
                },
            }
        }
    )[0]
    depot.create(valid_record.value)
    depot.create(
        {
            "kind": "skw.edition-session",
            "schema_version": 1,
            "file": {"project_id": PROJECT_ID, "path": "src/example.py"},
            "edition": {"commit": commit},
            "session": {"id": "broken"},
            "evidence": {},
        }
    )

    result = service.check([source])

    assert {finding.code for finding in result.findings} == {
        "duplicate-edition-session",
        "invalid-edition-history-record",
    }


def test_check_surfaces_bloberia_corruption(tmp_path: Path) -> None:
    _root, source, _commit = _project(tmp_path)
    depot_root = tmp_path / "bloberia"
    records = depot_root / "records"
    records.mkdir(parents=True)
    (records / "not-a-uuid.json").write_text("{}\n", encoding="utf-8")

    result = EditionHistoryService(BloberiaDepot(depot_root)).check([source])

    assert result.ok is False
    assert [finding.code for finding in result.findings] == [
        "bloberia-invalid-record-filename"
    ]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentos")
    register_skillware_commands(parser.add_subparsers(dest="command"))
    return parser


def test_cli_record_list_and_check_round_trip(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, source, commit = _project(tmp_path)
    depot = tmp_path / "bloberia"
    parser = _parser()

    record_args = [
        "skw",
        "edition-history",
        "record",
        "--file",
        str(source),
        "--commit",
        commit,
        "--session",
        "session-1",
        "--session-started-at",
        "2026-07-25T10:00:00Z",
        "--evidence-json",
        '{"method":"chatlas-file-write"}',
        "--depot",
        str(depot),
    ]
    args = parser.parse_args(record_args)
    assert args.handler(args) == 0
    assert json.loads(capsys.readouterr().out)["result"]["created"] is True

    args = parser.parse_args(record_args)
    assert args.handler(args) == 0
    assert json.loads(capsys.readouterr().out)["result"]["created"] is False

    args = parser.parse_args(
        [
            "skillware",
            "edition-history",
            "list",
            "--file",
            str(source),
            "--depot",
            str(depot),
        ]
    )
    assert args.handler(args) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["summary"] == {"editions": 1, "sessions": 1}
    assert listed["editions"][0]["sessions"][0]["id"] == "session-1"

    missing = root / "src" / "missing.py"
    missing.write_text("missing = 1\n", encoding="utf-8")
    args = parser.parse_args(
        [
            "skw",
            "edition-history",
            "check",
            "--target",
            str(source),
            "--target",
            str(missing),
            "--depot",
            str(depot),
        ]
    )
    assert args.handler(args) == 1
    checked = json.loads(capsys.readouterr().out)
    assert checked["status"] == "error"
    assert checked["findings"][0]["code"] == "missing-edition-history"


def test_cli_requires_explicit_depot(tmp_path: Path) -> None:
    _root, source, _commit = _project(tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        _parser().parse_args(
            ["skw", "edition-history", "list", "--file", str(source)]
        )

    assert exc_info.value.code == 2
