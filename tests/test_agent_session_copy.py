from __future__ import annotations

import json
from pathlib import Path
import argparse

import pytest

from tarav._core.errors import CliError
from tarav.agent.commands import register_agent_commands
from tarav.agent.session_copy import copy_agent_session


def test_claude_session_copy_check_reports_plan_without_mutating(tmp_path: Path) -> None:
    source = _write_claude_session(tmp_path / "claude-br")
    to_home = tmp_path / "claude"

    payload = copy_agent_session(
        provider="claude-code",
        from_home=source.home,
        to_home=to_home,
        session_id=source.session_id,
        check=True,
    )

    destination = to_home / source.relative_path
    assert payload["status"] == "ok"
    assert payload["command"] == "agent sessions copy"
    assert payload["provider"] == "claude-code"
    assert payload["session_id"] == source.session_id
    assert payload["from_home"] == str(source.home.resolve())
    assert payload["to_home"] == str(to_home.resolve())
    assert payload["actions"] == [
        {
            "kind": "copy",
            "status": "planned",
            "role": "transcript",
            "source_path": str(source.path.resolve()),
            "destination_path": str(destination.resolve()),
        }
    ]
    assert not destination.exists()


def test_claude_session_copy_copies_transcript_and_preserves_mtime(
    tmp_path: Path,
) -> None:
    source = _write_claude_session(tmp_path / "claude-br")
    to_home = tmp_path / "claude"
    source.path.touch()
    source_mtime = source.path.stat().st_mtime_ns

    payload = copy_agent_session(
        provider="claude-code",
        from_home=source.home,
        to_home=to_home,
        session_id=source.session_id,
    )

    destination = to_home / source.relative_path
    assert payload["actions"] == [
        {
            "kind": "copy",
            "status": "copied",
            "role": "transcript",
            "source_path": str(source.path.resolve()),
            "destination_path": str(destination.resolve()),
        }
    ]
    assert destination.read_text(encoding="utf-8") == source.path.read_text(
        encoding="utf-8"
    )
    assert destination.stat().st_mtime_ns == source_mtime


def test_claude_session_copy_existing_identical_destination_is_noop(
    tmp_path: Path,
) -> None:
    source = _write_claude_session(tmp_path / "claude-br")
    destination = tmp_path / "claude" / source.relative_path
    destination.parent.mkdir(parents=True)
    destination.write_text(source.path.read_text(encoding="utf-8"), encoding="utf-8")

    payload = copy_agent_session(
        provider="claude-code",
        from_home=source.home,
        to_home=tmp_path / "claude",
        session_id=source.session_id,
    )

    assert payload["actions"][0]["kind"] == "noop"
    assert payload["actions"][0]["status"] == "identical"


def test_claude_session_copy_refuses_existing_different_destination(
    tmp_path: Path,
) -> None:
    source = _write_claude_session(tmp_path / "claude-br")
    destination = tmp_path / "claude" / source.relative_path
    destination.parent.mkdir(parents=True)
    destination.write_text("different\n", encoding="utf-8")

    with pytest.raises(CliError, match="already exists"):
        copy_agent_session(
            provider="claude-code",
            from_home=source.home,
            to_home=tmp_path / "claude",
            session_id=source.session_id,
        )

    assert destination.read_text(encoding="utf-8") == "different\n"


def test_claude_session_copy_force_overwrites_existing_destination(
    tmp_path: Path,
) -> None:
    source = _write_claude_session(tmp_path / "claude-br")
    destination = tmp_path / "claude" / source.relative_path
    destination.parent.mkdir(parents=True)
    destination.write_text("different\n", encoding="utf-8")

    payload = copy_agent_session(
        provider="claude-code",
        from_home=source.home,
        to_home=tmp_path / "claude",
        session_id=source.session_id,
        force=True,
    )

    assert payload["actions"][0]["kind"] == "overwrite"
    assert payload["actions"][0]["status"] == "copied"
    assert destination.read_text(encoding="utf-8") == source.path.read_text(
        encoding="utf-8"
    )


def test_claude_session_copy_missing_source_errors(tmp_path: Path) -> None:
    with pytest.raises(CliError, match="session not found"):
        copy_agent_session(
            provider="claude-code",
            from_home=tmp_path / "claude-br",
            to_home=tmp_path / "claude",
            session_id="missing",
        )


def test_claude_session_copy_ambiguous_source_errors(tmp_path: Path) -> None:
    source = _write_claude_session(tmp_path / "claude-br")
    duplicate = (
        source.home
        / "projects"
        / "-Users-pereiro-projects-other"
        / f"{source.session_id}.jsonl"
    )
    duplicate.parent.mkdir(parents=True)
    duplicate.write_text(source.path.read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(CliError, match="multiple claude-code sessions matched"):
        copy_agent_session(
            provider="claude-code",
            from_home=source.home,
            to_home=tmp_path / "claude",
            session_id=source.session_id,
        )


def test_agent_sessions_copy_cli_check_outputs_human_plan(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _write_claude_session(tmp_path / "claude-br")
    parser = _agent_parser()
    args = parser.parse_args(
        [
            "agent",
            "sessions",
            "copy",
            "--provider",
            "claude-code",
            "--from-home",
            str(source.home),
            "--to-home",
            str(tmp_path / "claude"),
            "--session",
            source.session_id,
            "--check",
        ]
    )

    assert args.handler(args) == 0

    output = capsys.readouterr().out
    assert "Planned claude-code session copy" in output
    assert str(source.path.resolve()) in output
    assert str((tmp_path / "claude" / source.relative_path).resolve()) in output


def test_agent_sessions_copy_cli_outputs_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _write_claude_session(tmp_path / "claude-br")
    parser = _agent_parser()
    args = parser.parse_args(
        [
            "agent",
            "sessions",
            "copy",
            "--provider",
            "claude-code",
            "--from-home",
            str(source.home),
            "--to-home",
            str(tmp_path / "claude"),
            "--session",
            source.session_id,
            "--check",
            "--json",
        ]
    )

    assert args.handler(args) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "agent sessions copy"
    assert payload["actions"][0]["status"] == "planned"


def test_agent_sessions_copy_cli_help_is_registered(capsys: pytest.CaptureFixture[str]) -> None:
    parser = _agent_parser()

    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["agent", "sessions", "copy", "--help"])

    assert excinfo.value.code == 0
    help_text = capsys.readouterr().out
    assert "--from-home" in help_text
    assert "--to-home" in help_text
    assert "--session" in help_text


class _ClaudeSessionFixture:
    def __init__(self, *, home: Path, path: Path, session_id: str) -> None:
        self.home = home
        self.path = path
        self.session_id = session_id

    @property
    def relative_path(self) -> Path:
        return self.path.relative_to(self.home)


def _write_claude_session(home: Path) -> _ClaudeSessionFixture:
    session_id = "67b706eb-d233-446f-96ce-926f52560eab"
    encoded_project = "-Users-pereiro-projects-miacad-project"
    path = home / "projects" / encoded_project / f"{session_id}.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "type": "user",
                "sessionId": session_id,
                "cwd": "/Users/pereiro/projects/miacad-project",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return _ClaudeSessionFixture(home=home, path=path, session_id=session_id)


def _agent_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    register_agent_commands(subparsers)
    return parser
