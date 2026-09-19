"""CLI coverage for the promoted Tarav.Archive surface."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess

import pytest

from tarav.cli.cli import build_parser, main


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(repo), *args),
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def _source_repository(path: Path, *, branch: str = "main") -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", branch)
    (path / "chat.jsonl").write_text('{"role":"user"}\n', encoding="utf-8")
    _git(path, "add", "chat.jsonl")
    _git(
        path,
        "-c",
        "user.name=Archive Test",
        "-c",
        "user.email=archive-test@example.invalid",
        "commit",
        "-q",
        "-m",
        "initial",
    )
    return path


def test_promoted_tarav_domains_are_top_level_commands(
    capsys: pytest.CaptureFixture[str],
) -> None:
    help_text = build_parser().format_help()
    assert "archive" in help_text
    assert "diagram" in help_text
    assert "tarav2" not in help_text
    assert "anchory" not in help_text
    assert "reference" not in help_text
    assert "indexlab" not in help_text
    assert "mission" not in help_text
    assert "canvas" not in help_text
    with pytest.raises(SystemExit, match="0"):
        main(["archive", "--help"])
    output = capsys.readouterr().out
    assert "artifact" in output
    assert "reference" in output
    assert "repository" in output

    with pytest.raises(SystemExit, match="0"):
        main(["stdlib", "--help"])
    assert "bloberia" not in capsys.readouterr().out


def test_retired_wayfinder_cli_is_absent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit, match="2"):
        main(["wayfinder"])

    assert "invalid choice" in capsys.readouterr().err


def test_archive_init_creates_records_and_repository_roots(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "archive"

    assert main(["archive", "init", "--archive", str(root), "--json"]) == 0

    assert json.loads(capsys.readouterr().out) == {
        "status": "ok",
        "command": "tarav archive init",
        "archive": str(root.resolve()),
    }
    assert (root / "records" / ".git").is_dir()
    assert (root / "repositories").is_dir()


def test_repository_registration_and_generic_artifact_show(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    source = _source_repository(tmp_path / "chatlas")
    expected_archive = home / "Documents" / "tarav" / "archive"

    assert (
        main(
            [
                "archive",
                "repository",
                "register",
                "--location",
                str(source),
                "--name",
                "tarav.chatlas",
                "--json",
            ]
        )
        == 0
    )
    registered = json.loads(capsys.readouterr().out)
    repository = registered["artifact"]
    assert re.fullmatch(r"[0-9a-f]{64}", repository["id"])
    assert registered == {
        "status": "ok",
        "command": "tarav archive repository register",
        "archive": str(expected_archive.resolve()),
        "location": str(source.resolve()),
        "branch": "main",
        "artifact": {
            "id": repository["id"],
            "kind": "git-repository",
            "name": "tarav.chatlas",
            "recorded_at": repository["recorded_at"],
        },
    }

    assert (
        main(
            [
                "archive",
                "artifact",
                "show",
                "--artifact",
                "tarav.chatlas",
                "--json",
            ]
        )
        == 0
    )
    shown = json.loads(capsys.readouterr().out)
    assert shown["command"] == "tarav archive artifact show"
    assert shown["artifact"] == repository
    assert set(shown["records"]) == {
        "registration.json",
        "locators.jsonl",
        "git-hint.json",
    }


def test_cli_materializes_one_requested_git_artifact(tmp_path: Path, capsys) -> None:
    root = tmp_path / "archive"
    source = _source_repository(tmp_path / "chatlas")
    commit = _git(source, "rev-parse", "HEAD")
    assert (
        main(
            [
                "archive",
                "repository",
                "register",
                "--location",
                str(source),
                "--name",
                "tarav.chatlas",
                "--archive",
                str(root),
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "archive",
                "repository",
                "materialize",
                "--repository",
                "tarav.chatlas",
                "--commit",
                commit,
                "--path",
                "chat.jsonl",
                "--archive",
                str(root),
                "--json",
            ]
        )
        == 0
    )
    materialized = json.loads(capsys.readouterr().out)
    assert materialized["command"] == "tarav archive repository materialize"
    assert materialized["artifact"]["kind"] == "git-file-version"
    assert re.fullmatch(r"[0-9a-f]{64}", materialized["artifact"]["id"])
    assert len(list((root / "records" / "artifacts").iterdir())) == 2


def test_repository_register_accepts_an_explicit_hint_branch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "archive"
    source = _source_repository(tmp_path / "chatlas", branch="trunk")

    assert (
        main(
            [
                "archive",
                "repository",
                "register",
                "--location",
                str(source),
                "--name",
                "tarav.chatlas",
                "--branch",
                "trunk",
                "--archive",
                str(root),
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["branch"] == "trunk"
    object_root = root / "records" / "artifacts" / payload["artifact"]["id"]
    assert json.loads((object_root / "git-hint.json").read_text())["branch"] == "trunk"


def test_cli_registers_repoless_artifacts_and_external_descriptors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "archive"
    for name, kind, location in (
        ("video", "Video", "https://example.test/video"),
        ("transcript", "File", "https://example.test/transcript"),
    ):
        assert (
            main(
                [
                    "archive",
                    "artifact",
                    "register",
                    "--locator",
                    location,
                    "--name",
                    name,
                    "--kind",
                    kind,
                    "--archive",
                    str(root),
                    "--json",
                ]
            )
            == 0
        )
        capsys.readouterr()

    assert (
        main(
            [
                "archive",
                "artifact",
                "descriptor",
                "add",
                "--artifact",
                "video",
                "--descriptor",
                "transcript",
                "--attribution",
                "user:pereiro",
                "--archive",
                str(root),
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["created"] is True
    assert payload["artifact"]["name"] == "video"
    assert payload["descriptor"]["name"] == "transcript"


def test_cli_rejects_positional_data_inputs(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="2"):
        main(
            [
                "archive",
                "artifact",
                "register",
                "https://example.test/video",
                "--archive",
                str(tmp_path / "archive"),
            ]
        )


def test_cli_produces_bare_kind_defined_reference_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "archive"
    source = _source_repository(tmp_path / "chatlas")
    commit = _git(source, "rev-parse", "HEAD")
    assert (
        main(
            [
                "archive",
                "repository",
                "register",
                "--location",
                str(source),
                "--name",
                "tarav.chatlas",
                "--archive",
                str(root),
                "--json",
            ]
        )
        == 0
    )
    registered = json.loads(capsys.readouterr().out)["artifact"]

    assert (
        main(
            [
                "archive",
                "reference",
                "repository",
                "--locator",
                str(source),
                "--archive",
                str(root),
            ]
        )
        == 0
    )
    repository_reference = json.loads(capsys.readouterr().out)
    assert repository_reference["type"] == "Tarav.Archive.Reference"
    assert repository_reference["locator"]["doi"] == registered["id"]
    assert repository_reference["hints"]["path"] == str(source)

    assert (
        main(
            [
                "archive",
                "reference",
                "git-file",
                "--repository",
                "tarav.chatlas",
                "--commit",
                commit,
                "--locator",
                "chat.jsonl",
                "--archive",
                str(root),
            ]
        )
        == 0
    )
    git_file_reference = json.loads(capsys.readouterr().out)
    assert git_file_reference["type"] == "Tarav.Archive.Reference"
    assert git_file_reference["locator"]["doi"] != registered["id"]
    assert git_file_reference["hints"]["path"] == "chat.jsonl"
    assert git_file_reference["check"]["git_oid"]

    external_file = tmp_path / "report.txt"
    external_file.write_text("report\n", encoding="utf-8")
    assert (
        main(
            [
                "archive",
                "reference",
                "file",
                "--locator",
                str(external_file),
                "--archive",
                str(root),
            ]
        )
        == 0
    )
    file_reference = json.loads(capsys.readouterr().out)
    assert file_reference["type"] == "Tarav.Archive.Reference"
    assert file_reference["hints"]["path"] == str(external_file)
    assert file_reference["hints"]["recorded_at"]
