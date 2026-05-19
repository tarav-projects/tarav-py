from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.cli import main
from _helpers import captured_json, read_json_file


def _init_project(project_root: Path, capsys: pytest.CaptureFixture[str]) -> str:
    project_root.mkdir()
    assert main(["init", "--scope", "project", "--project", str(project_root)]) == 0
    capsys.readouterr()
    return str(read_json_file(project_root / ".agentos" / "project.json")["project_id"])


def test_forum_post_reply_react_and_feed_cross_project_threads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("AGENTOS_HOME", str(tmp_path / "agentos-home"))
    workspace = tmp_path / "workspace"
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    project_a_id = _init_project(project_a, capsys)
    project_b_id = _init_project(project_b, capsys)

    assert main(["future", "forum", "post", "--project", str(project_a), "--json", "Thread root"]) == 0
    post = captured_json(capsys)["event"]
    assert post["event_type"] == "post"
    assert post["author_project_id"] == project_a_id
    assert post["channel_project_id"] == project_a_id

    assert main(["future", "forum", "reply", "--project", str(project_b), "--json", post["event_id"], "Reply from B"]) == 0
    reply = captured_json(capsys)["event"]
    assert reply["event_type"] == "reply"
    assert reply["author_project_id"] == project_b_id
    assert reply["channel_project_id"] == project_a_id
    assert reply["parent_post_id"] == post["event_id"]

    assert main(["future", "forum", "react", "--project", str(project_b), "--json", post["event_id"], "--reaction", "ack"]) == 0
    reaction = captured_json(capsys)["event"]
    assert reaction["event_type"] == "reaction"
    assert reaction["target_post_id"] == post["event_id"]
    assert reaction["reaction"] == "ack"

    assert main(["future", "forum", "feed", "--json"]) == 0
    feed = captured_json(capsys)
    assert {item["event"]["event_id"] for item in feed["events"]} >= {post["event_id"], reply["event_id"], reaction["event_id"]}


def test_forum_rejects_invalid_thread_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("AGENTOS_HOME", str(tmp_path / "agentos-home"))
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    _init_project(project_a, capsys)
    _init_project(project_b, capsys)

    assert main(["future", "forum", "post", "--project", str(project_a), "--json", "Thread root"]) == 0
    post = captured_json(capsys)["event"]
    assert main(["future", "forum", "react", "--project", str(project_b), "--json", post["event_id"], "--reaction", "ack"]) == 0
    reaction = captured_json(capsys)["event"]

    assert main(["future", "forum", "reply", "--project", str(project_b), "--json", reaction["event_id"], "bad reply"]) == 1
    assert "forum target must be a post or reply" in capsys.readouterr().err


def test_forum_help_is_nested_under_future(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["future", "--help"])
    assert exc_info.value.code == 0
    assert "forum" in capsys.readouterr().out

    with pytest.raises(SystemExit) as exc_info:
        main(["forum", "--help"])
    assert exc_info.value.code == 2
    assert "invalid choice: 'forum'" in capsys.readouterr().err
