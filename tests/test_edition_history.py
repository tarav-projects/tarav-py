# $kw: ^test-edition-history --from Skw.Edition.History.Service --note [DF] service and command-boundary coverage for required, resolvable edition/session support ^c20260725-12u --supp schema migration authorized ^c20260725-14u --supp live Chatlas resolution authorized ^c20260725-15u --supp project policy integration authorized ^c20260725-25u --supp completeness and amendment coverage authorized ^c20260725-32u
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pytest

from tarav.bloberia.depot_v1 import BloberiaDepot
from tarav.skillware.edition_history import (
    DEFAULT_EDITION_HISTORY_DEPOT,
    EditionFile,
    EditionHistoryError,
    EditionHistoryService,
    default_edition_history_depot,
)
from tarav.skillware.commands import register_skillware_commands


PROJECT_ID = "b49973ef-a0d1-47d2-b2dc-f12bbbf424a4"


def _accept_support(_support: dict[str, object]) -> None:
    return None


def _service(depot: BloberiaDepot) -> EditionHistoryService:
    return EditionHistoryService(
        depot,
        support_resolver=_accept_support,
    )


def _support(
    session: str,
    *,
    turn_id: str = "turn-1",
    turn_hash: str = "a" * 64,
    at: str = "2026-07-25T10:00:00.123Z",
) -> dict[str, object]:
    return {
        "app": "chatlas",
        "schema": "chatlas.support-set.v3",
        "hint": "The session edited this file.",
        "members": [
            {
                "session": session,
                "turn_id": turn_id,
                "turn_hash": turn_hash,
                "at": at,
            }
        ],
    }


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
    (root / ".tarav").mkdir(parents=True)
    (root / ".tarav" / "project.json").write_text(
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
    root, source, _commit = _project(tmp_path)

    assert EditionFile.resolve(source) == EditionFile(
        project_id=PROJECT_ID,
        path="src/example.py",
    )
    assert default_edition_history_depot(source) == (
        root / DEFAULT_EDITION_HISTORY_DEPOT
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
    service = _service(BloberiaDepot(tmp_path / "bloberia"))

    first = service.record(
        source,
        first_commit[:12],
        "session-b",
        session_started_at="2026-07-25T10:00:00Z",
        support=_support("session-b"),
    )
    repeated = service.record(
        source,
        first_commit,
        "session-b",
        session_started_at="2026-07-25T10:00:00Z",
        support=_support("session-b"),
    )
    service.record(
        source,
        second_commit,
        "session-c",
        support=_support("session-c"),
    )
    service.record(
        source,
        first_commit,
        "session-a",
        session_started_at="2026-07-25T09:00:00+00:00",
        support=_support("session-a", turn_id="event-2"),
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
    assert first_edition.sessions[1].support == _support("session-b")


def test_list_keeps_git_editions_without_session_support(tmp_path: Path) -> None:
    root, source, first_commit = _project(tmp_path)
    source.write_text("first = 1\nsecond = 2\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "second")
    second_commit = _git(root, "rev-parse", "HEAD")
    service = _service(BloberiaDepot(tmp_path / "bloberia"))
    service.record(
        source,
        second_commit,
        "session",
        support=_support("session"),
    )

    history = service.list(source)

    assert [edition.commit for edition in history.editions] == [
        first_commit,
        second_commit,
    ]
    assert [edition.supported for edition in history.editions] == [False, True]
    assert history.supported_editions == 1
    assert history.unsupported_editions == 1


def test_amend_replaces_support_and_session_start_time(tmp_path: Path) -> None:
    _root, source, commit = _project(tmp_path)
    depot = BloberiaDepot(tmp_path / "bloberia")
    service = _service(depot)
    recorded = service.record(
        source,
        commit,
        "session",
        support=_support("session"),
    )

    result = service.amend(
        source,
        recorded.record_id,
        support=_support("session", turn_id="event-2"),
        session_started_at="2026-07-25T09:30:00Z",
    )

    assert result.record_id == recorded.record_id
    assert result.amended is True
    assert result.revision == 2
    session = service.list(source).editions[0].sessions[0]
    assert session.support == _support("session", turn_id="event-2")
    assert session.started_at == "2026-07-25T09:30:00Z"

    repeated = service.amend(
        source,
        recorded.record_id,
        support=_support("session", turn_id="event-2"),
        session_started_at="2026-07-25T09:30:00Z",
    )
    assert repeated.amended is False
    assert repeated.revision == 2


def test_amend_rejects_wrong_file_without_mutation(tmp_path: Path) -> None:
    root, source, commit = _project(tmp_path)
    other = root / "src" / "other.py"
    other.write_text("other = 1\n", encoding="utf-8")
    depot = BloberiaDepot(tmp_path / "bloberia")
    service = _service(depot)
    recorded = service.record(
        source,
        commit,
        "session",
        support=_support("session"),
    )

    with pytest.raises(EditionHistoryError, match="does not belong"):
        service.amend(
            other,
            recorded.record_id,
            support=_support("session", turn_id="event-2"),
        )

    assert depot.get(recorded.record_id).revision == 1


def test_record_rejects_invalid_session_metadata(tmp_path: Path) -> None:
    _root, source, commit = _project(tmp_path)
    service = _service(BloberiaDepot(tmp_path / "bloberia"))

    with pytest.raises(EditionHistoryError, match="session id"):
        service.record(source, commit, " ", support=_support("session"))
    with pytest.raises(EditionHistoryError, match="session_started_at"):
        service.record(
            source,
            commit,
            "session",
            session_started_at="yesterday",
            support=_support("session"),
        )


def test_record_requires_support(tmp_path: Path) -> None:
    _root, source, commit = _project(tmp_path)
    service = _service(BloberiaDepot(tmp_path / "bloberia"))

    with pytest.raises(TypeError, match="support"):
        service.record(source, commit, "session")


@pytest.mark.parametrize(
    ("support", "message"),
    [
        (["not", "an", "object"], "support must contain exactly"),
        (
            {
                "app": "chatlas",
                "schema": "chatlas.support-set.v3",
                "hint": "Proof.",
                "members": [],
            },
            "members must be a non-empty list",
        ),
        (
            {
                **_support("session"),
                "members": _support("session")["members"] * 2,  # type: ignore[operator]
            },
            "duplicate",
        ),
        (_support("other-session"), "must include associated session"),
        (_support("session", at="yesterday"), "support.members\\[0\\].at"),
    ],
)
def test_record_rejects_invalid_support(
    tmp_path: Path,
    support: object,
    message: str,
) -> None:
    _root, source, commit = _project(tmp_path)
    service = _service(BloberiaDepot(tmp_path / "bloberia"))

    with pytest.raises(EditionHistoryError, match=message):
        service.record(source, commit, "session", support=support)  # type: ignore[arg-type]


def test_record_requires_resolvable_support(tmp_path: Path) -> None:
    _root, source, commit = _project(tmp_path)
    depot = BloberiaDepot(tmp_path / "bloberia")

    with pytest.raises(EditionHistoryError, match="support resolver is required"):
        EditionHistoryService(depot).record(
            source,
            commit,
            "session",
            support=_support("session"),
        )

    assert depot.query({"value": {"kind": "skw.edition-session"}}) == ()


def test_list_rejects_and_check_reports_unresolvable_support(
    tmp_path: Path,
) -> None:
    _root, source, commit = _project(tmp_path)
    depot = BloberiaDepot(tmp_path / "bloberia")
    _service(depot).record(
        source,
        commit,
        "session",
        support=_support("session"),
    )

    def reject_support(_support: dict[str, object]) -> None:
        raise RuntimeError("event is unavailable")

    service = EditionHistoryService(
        depot,
        support_resolver=reject_support,
    )
    with pytest.raises(EditionHistoryError, match="event is unavailable"):
        service.list(source)

    result = service.check([source])

    assert [finding.code for finding in result.findings] == [
        "unresolvable-edition-support"
    ]
    assert "event is unavailable" in result.findings[0].message


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
            "support": _support("session"),
        }
    )

    with pytest.raises(EditionHistoryError, match="invalid edition-history record"):
        _service(depot).list(source)


def test_check_requires_history_for_each_explicit_target(tmp_path: Path) -> None:
    root, source, commit = _project(tmp_path)
    other = root / "src" / "other.py"
    other.write_text("other = 1\n", encoding="utf-8")
    service = _service(BloberiaDepot(tmp_path / "bloberia"))
    service.record(source, commit, "session", support=_support("session"))

    result = service.check([source, other])

    assert result.ok is False
    assert [(finding.code, finding.target) for finding in result.findings] == [
        ("missing-edition-history", "src/other.py")
    ]
    assert service.check([source]).ok is True


def test_complete_check_reports_each_unsupported_git_edition(
    tmp_path: Path,
) -> None:
    root, source, first_commit = _project(tmp_path)
    source.write_text("first = 1\nsecond = 2\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "second")
    second_commit = _git(root, "rev-parse", "HEAD")
    service = _service(BloberiaDepot(tmp_path / "bloberia"))
    service.record(
        source,
        second_commit,
        "session",
        support=_support("session"),
    )

    assert service.check([source]).ok is True
    complete = service.check([source], require_complete=True)

    assert [(finding.code, finding.target) for finding in complete.findings] == [
        ("unsupported-git-edition", "src/example.py")
    ]
    assert first_commit in complete.findings[0].message


def test_check_reports_duplicate_and_malformed_associations(
    tmp_path: Path,
) -> None:
    _root, source, commit = _project(tmp_path)
    depot = BloberiaDepot(tmp_path / "bloberia")
    service = _service(depot)
    service.record(source, commit, "session", support=_support("session"))
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

    result = _service(BloberiaDepot(depot_root)).check([source])

    assert result.ok is False
    assert [finding.code for finding in result.findings] == [
        "bloberia-invalid-record-filename"
    ]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tarav")
    register_skillware_commands(
        parser.add_subparsers(dest="command"),
        edition_history_support_resolver=_accept_support,
    )
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
        "--support-json",
        json.dumps(_support("session-1")),
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
    assert listed["summary"] == {
        "editions": 1,
        "supported_editions": 1,
        "unsupported_editions": 0,
        "sessions": 1,
    }
    assert listed["editions"][0]["sessions"][0]["id"] == "session-1"

    amend_args = parser.parse_args(
        [
            "skw",
            "edition-history",
            "amend",
            "--file",
            str(source),
            "--record",
            listed["editions"][0]["sessions"][0]["record_id"],
            "--support-json",
            json.dumps(_support("session-1", turn_id="event-2")),
            "--depot",
            str(depot),
        ]
    )
    assert amend_args.handler(amend_args) == 0
    amended = json.loads(capsys.readouterr().out)
    assert amended["result"]["revision"] == 2

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
    assert checked["domain"]["status"] == "error"
    assert checked["pois"][0]["evidence"]["kind"] == "missing-edition-history"


def test_cli_uses_project_default_depot(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, source, commit = _project(tmp_path)
    parser = _parser()
    args = parser.parse_args(
        [
            "skw",
            "edition-history",
            "record",
            "--file",
            str(source),
            "--commit",
            commit,
            "--session",
            "session",
            "--support-json",
            json.dumps(_support("session")),
        ]
    )

    assert args.handler(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert Path(payload["depot"]) == root / DEFAULT_EDITION_HISTORY_DEPOT

    args = parser.parse_args(["skw", "edition-history", "list", "--file", str(source)])
    assert args.handler(args) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["sessions"] == 1


def test_project_check_enforces_configured_edition_history(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source, commit = _project(tmp_path)
    (root / ".skw").mkdir()
    (root / ".skw" / "skw.json").write_text(
        json.dumps(
            {
                "edition_history": {
                    "targets": ["src/*.py"],
                    "exclude": ["src/excluded.py"],
                }
            }
        ),
        encoding="utf-8",
    )
    excluded = root / "src" / "excluded.py"
    excluded.write_text("excluded = True\n", encoding="utf-8")
    monkeypatch.chdir(root)
    parser = _parser()

    args = parser.parse_args(["skw", "check", "--json"])
    assert args.handler(args) == 1
    payload = json.loads(capsys.readouterr().out)
    project_poi = next(
        poi
        for poi in payload["pois"]
        if poi["evidence"]["kind"] == "missing-edition-history"
    )
    assert project_poi["instance_id"] in payload["domain"]["project_poi_ids"]
    assert project_poi["target"]["path"] == "src/example.py"

    args = parser.parse_args(
        ["skw", "check", "--json", "--skip", "missing-edition-history"]
    )
    assert args.handler(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["domain"]["project_poi_ids"] == []
    assert payload["pois"] == []

    source.write_text("value = 2\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "second")
    second_commit = _git(root, "rev-parse", "HEAD")
    service = _service(BloberiaDepot(root / DEFAULT_EDITION_HISTORY_DEPOT))
    service.record(
        source,
        second_commit,
        "session",
        support=_support("session"),
    )
    args = parser.parse_args(["skw", "check", "--json"])
    assert args.handler(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["domain"]["project_poi_ids"] == []
    assert payload["summary"]["poi_count"] == 0

    args = parser.parse_args(
        ["skw", "check", "--json", "--check", "unsupported-git-edition"]
    )
    assert args.handler(args) == 1
    payload = json.loads(capsys.readouterr().out)
    project_poi = next(
        poi
        for poi in payload["pois"]
        if poi["evidence"]["kind"] == "unsupported-git-edition"
    )
    assert project_poi["instance_id"] in payload["domain"]["project_poi_ids"]
    assert commit in project_poi["situation"]


def test_project_check_without_policy_does_not_require_history(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _source, _commit = _project(tmp_path)
    monkeypatch.chdir(root)
    args = _parser().parse_args(["skw", "check", "--json"])

    assert args.handler(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["domain"]["project_poi_ids"] == []
    assert payload["pois"] == []


def test_cli_record_requires_support(tmp_path: Path) -> None:
    _root, source, commit = _project(tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        _parser().parse_args(
            [
                "skw",
                "edition-history",
                "record",
                "--file",
                str(source),
                "--commit",
                commit,
                "--session",
                "session",
                "--depot",
                str(tmp_path / "bloberia"),
            ]
        )

    assert exc_info.value.code == 2
