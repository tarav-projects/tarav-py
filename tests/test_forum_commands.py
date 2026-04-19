from __future__ import annotations

import json
from pathlib import Path

from agentos.cli import main
from agentos.forum.core import forum_project_events_path, forum_project_manifest_path


def _init_project(project_root: Path, capsys) -> None:
    project_root.mkdir()
    assert main(["init", "--scope", "project", "--project", str(project_root)]) == 0
    capsys.readouterr()


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _project_id(project_root: Path) -> str:
    payload = json.loads((project_root / ".agentos" / "project.json").read_text(encoding="utf-8"))
    return str(payload["project_id"])


def test_forum_post_supports_explicit_project_target(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = tmp_path / "agentos-home"
    workspace = tmp_path / "workspace"
    project_a = tmp_path / "project-a"
    workspace.mkdir()
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    monkeypatch.chdir(workspace)
    _init_project(project_a, capsys)
    project_a_id = _project_id(project_a)

    assert main(["forum", "post", "--project", str(project_a), "--json", "Hello from A"]) == 0
    payload = json.loads(capsys.readouterr().out)

    event = payload["event"]
    assert payload["command"] == "forum post"
    assert event["event_type"] == "post"
    assert event["author_project_id"] == project_a_id
    assert event["channel_project_id"] == project_a_id
    assert event["thread_root_post_id"] == event["event_id"]
    assert event["body"] == "Hello from A"

    assert forum_project_manifest_path(project_a_id).exists()
    assert _load_jsonl(forum_project_events_path(project_a_id)) == [event]


def test_forum_reply_inherits_target_channel_from_other_project(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = tmp_path / "agentos-home"
    workspace = tmp_path / "workspace"
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    workspace.mkdir()
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    monkeypatch.chdir(workspace)
    _init_project(project_a, capsys)
    _init_project(project_b, capsys)
    project_a_id = _project_id(project_a)
    project_b_id = _project_id(project_b)

    assert main(["forum", "post", "--project", str(project_a), "--json", "Thread root"]) == 0
    post_payload = json.loads(capsys.readouterr().out)
    post = post_payload["event"]

    assert main(
        [
            "forum",
            "reply",
            "--project",
            str(project_b),
            "--json",
            str(post["event_id"]),
            "Reply from B",
        ]
    ) == 0
    reply_payload = json.loads(capsys.readouterr().out)
    reply = reply_payload["event"]

    assert reply["event_type"] == "reply"
    assert reply["author_project_id"] == project_b_id
    assert reply["channel_project_id"] == project_a_id
    assert reply["thread_root_post_id"] == post["event_id"]
    assert reply["parent_post_id"] == post["event_id"]
    assert reply["body"] == "Reply from B"

    assert _load_jsonl(forum_project_events_path(project_b_id))[-1] == reply


def test_forum_react_inherits_target_channel(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = tmp_path / "agentos-home"
    workspace = tmp_path / "workspace"
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    workspace.mkdir()
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    monkeypatch.chdir(workspace)
    _init_project(project_a, capsys)
    _init_project(project_b, capsys)
    project_a_id = _project_id(project_a)
    project_b_id = _project_id(project_b)

    assert main(["forum", "post", "--project", str(project_a), "--json", "Thread root"]) == 0
    post_payload = json.loads(capsys.readouterr().out)
    post = post_payload["event"]

    assert main(
        [
            "forum",
            "react",
            "--project",
            str(project_b),
            "--json",
            str(post["event_id"]),
            "--reaction",
            "ack",
        ]
    ) == 0
    reaction_payload = json.loads(capsys.readouterr().out)
    reaction = reaction_payload["event"]

    assert reaction["event_type"] == "reaction"
    assert reaction["author_project_id"] == project_b_id
    assert reaction["channel_project_id"] == project_a_id
    assert reaction["thread_root_post_id"] == post["event_id"]
    assert reaction["target_post_id"] == post["event_id"]
    assert reaction["reaction"] == "ack"
    assert reaction["body"] is None


def test_forum_reply_rejects_reaction_target(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = tmp_path / "agentos-home"
    workspace = tmp_path / "workspace"
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    workspace.mkdir()
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    monkeypatch.chdir(workspace)
    _init_project(project_a, capsys)
    _init_project(project_b, capsys)

    assert main(["forum", "post", "--project", str(project_a), "--json", "Thread root"]) == 0
    post_payload = json.loads(capsys.readouterr().out)
    post = post_payload["event"]

    assert main(
        [
            "forum",
            "react",
            "--project",
            str(project_b),
            "--json",
            str(post["event_id"]),
            "--reaction",
            "ack",
        ]
    ) == 0
    reaction_payload = json.loads(capsys.readouterr().out)
    reaction = reaction_payload["event"]

    assert (
        main(
            [
                "forum",
                "reply",
                "--project",
                str(project_a),
                str(reaction["event_id"]),
                "Trying to reply to a reaction",
            ]
        )
        == 1
    )
    assert "forum target must be a post or reply" in capsys.readouterr().err


def test_forum_post_requires_existing_project(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)

    assert main(["forum", "post", "hello"]) == 1
    assert "missing .agentos/project.json" in capsys.readouterr().err
