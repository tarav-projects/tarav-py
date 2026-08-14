# $kw: ^test-e2e-edition-history --from Skw.Edition.History.Service --note [DF] umbrella CLI coverage for required and Chatlas-resolved Skillware edition history ^c20260725-12u --supp schema migration authorized ^c20260725-14u --supp live Chatlas resolution authorized ^c20260725-15u --supp project policy integration authorized ^c20260725-25u --supp Git-complete history output authorized ^c20260725-32u
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tarav.cli.cli import build_parser, main


PROJECT_ID = "344da31c-376e-4141-a9cb-853590db8cc1"


def _support(session: str) -> str:
    return json.dumps(
        {
            "app": "chatlas",
            "schema": "chatlas.support-set.v3",
            "hint": "The session edited this file.",
            "members": [
                {
                    "session": session,
                    "turn_id": "turn-1",
                    "turn_hash": "a" * 64,
                    "at": "2026-07-25T10:00:00.123Z",
                }
            ],
        }
    )


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
    source.write_text("value = 1\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(
        root,
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-q",
        "-m",
        "edition",
    )
    return root, source, _git(root, "rev-parse", "HEAD")


def _captured_json(capsys: object) -> dict[str, object]:
    return json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]


def test_edition_history_cli_round_trip(
    tmp_path: Path,
    capsys: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tarav.chatlas.anchory.resolve_event_support_set_record",
        lambda _support: (),
    )
    root, source, commit = _project(tmp_path)
    assert "skw" in build_parser().format_help()

    command = [
        "skw",
        "edition-history",
        "record",
        "--file",
        str(source),
        "--commit",
        commit,
        "--session",
        "session-1",
        "--support-json",
        _support("session-1"),
    ]
    assert main(command) == 0
    assert _captured_json(capsys)["result"]["created"] is True  # type: ignore[index]
    assert main(command) == 0
    assert _captured_json(capsys)["result"]["created"] is False  # type: ignore[index]

    assert (
        main(
            [
                "skillware",
                "edition-history",
                "list",
                "--file",
                str(source),
            ]
        )
        == 0
    )
    assert _captured_json(capsys)["summary"] == {
        "editions": 1,
        "supported_editions": 1,
        "unsupported_editions": 0,
        "sessions": 1,
    }

    missing = root / "src" / "missing.py"
    missing.write_text("missing = 1\n", encoding="utf-8")
    assert (
        main(
            [
                "skw",
                "edition-history",
                "check",
                "--target",
                str(source),
                "--target",
                str(missing),
            ]
        )
        == 1
    )
    poi = _captured_json(capsys)["pois"][0]  # type: ignore[index]
    assert poi["evidence"]["kind"] == "missing-edition-history"


def test_project_check_enforces_edition_history_policy(
    tmp_path: Path,
    capsys: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tarav.chatlas.anchory.resolve_event_support_set_record",
        lambda _support: (),
    )
    root, source, commit = _project(tmp_path)
    (root / ".skw").mkdir()
    (root / ".skw" / "skw.json").write_text(
        json.dumps({"edition_history": {"targets": ["src/*.py"]}}),
        encoding="utf-8",
    )
    monkeypatch.chdir(root)

    assert main(["skw", "check", "--json"]) == 1
    payload = _captured_json(capsys)
    project_poi = next(
        poi
        for poi in payload["pois"]
        if poi["evidence"]["kind"] == "missing-edition-history"
    )
    assert project_poi["instance_id"] in payload["domain"]["project_poi_ids"]

    assert (
        main(
            [
                "skw",
                "edition-history",
                "record",
                "--file",
                str(source),
                "--commit",
                commit,
                "--session",
                "session-1",
                "--support-json",
                _support("session-1"),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["skw", "check", "--json"]) == 0
    payload = _captured_json(capsys)
    assert payload["domain"]["project_poi_ids"] == []
    assert payload["pois"] == []
