from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.cli import main
from agentos.forum.core import (
    append_forum_event,
    forum_project_events_path,
    forum_project_manifest_path,
)


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


def _patch_forum_times(monkeypatch, values: list[str]) -> None:
    iterator = iter(values)
    monkeypatch.setattr("agentos.forum.core.utc_now_iso", lambda: next(iterator))


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


def test_forum_feed_filters_by_channel_without_local_project(
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
    _patch_forum_times(
        monkeypatch,
        [
            "2026-04-19T12:00:00Z",
            "2026-04-19T12:00:01Z",
            "2026-04-19T12:00:02Z",
            "2026-04-19T12:00:03Z",
        ],
    )
    project_a_id = _project_id(project_a)

    assert main(["forum", "post", "--project", str(project_a), "--json", "Thread root"]) == 0
    post_payload = json.loads(capsys.readouterr().out)
    post = post_payload["event"]

    assert (
        main(
            [
                "forum",
                "reply",
                "--project",
                str(project_b),
                "--json",
                str(post["event_id"]),
                "Reply from B",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(["forum", "feed", "--channel", project_a_id, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "forum feed"
    assert payload["event_count"] == 2
    assert [item["event"]["event_type"] for item in payload["events"]] == ["post", "reply"]
    assert {item["event"]["channel_project_id"] for item in payload["events"]} == {project_a_id}


def test_forum_thread_returns_full_thread_from_target_event(
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
    _patch_forum_times(
        monkeypatch,
        [
            "2026-04-19T13:00:00Z",
            "2026-04-19T13:00:01Z",
            "2026-04-19T13:00:02Z",
            "2026-04-19T13:00:03Z",
            "2026-04-19T13:00:04Z",
            "2026-04-19T13:00:05Z",
        ],
    )

    assert main(["forum", "post", "--project", str(project_a), "--json", "Thread root"]) == 0
    post_payload = json.loads(capsys.readouterr().out)
    post = post_payload["event"]

    assert (
        main(
            [
                "forum",
                "reply",
                "--project",
                str(project_b),
                "--json",
                str(post["event_id"]),
                "Reply from B",
            ]
        )
        == 0
    )
    reply_payload = json.loads(capsys.readouterr().out)
    reply = reply_payload["event"]

    assert (
        main(
            [
                "forum",
                "react",
                "--project",
                str(project_a),
                "--json",
                str(reply["event_id"]),
                "--reaction",
                "watch",
            ]
        )
        == 0
    )
    reaction_payload = json.loads(capsys.readouterr().out)
    reaction = reaction_payload["event"]

    assert main(["forum", "thread", str(reply["event_id"]), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "forum thread"
    assert payload["thread_root_post_id"] == post["event_id"]
    assert payload["target_event_id"] == reply["event_id"]
    assert [item["event"]["event_id"] for item in payload["events"]] == [
        post["event_id"],
        reply["event_id"],
        reaction["event_id"],
    ]


def test_forum_history_supports_explicit_project_id_without_local_project(
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
    project_b_id = _project_id(project_b)

    assert main(["forum", "post", "--project", str(project_a), "--json", "Thread root"]) == 0
    post_payload = json.loads(capsys.readouterr().out)
    post = post_payload["event"]

    assert (
        main(
            [
                "forum",
                "reply",
                "--project",
                str(project_b),
                "--json",
                str(post["event_id"]),
                "Reply from B",
            ]
        )
        == 0
    )
    reply_payload = json.loads(capsys.readouterr().out)
    reply = reply_payload["event"]

    assert main(["forum", "history", "--project-id", project_b_id, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "forum history"
    assert payload["project_id"] == project_b_id
    assert payload["event_count"] == 1
    assert payload["events"][0]["event"]["event_id"] == reply["event_id"]


def test_forum_history_uses_explicit_local_project(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = tmp_path / "agentos-home"
    project_a = tmp_path / "project-a"
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _init_project(project_a, capsys)
    monkeypatch.chdir(project_a)
    project_a_id = _project_id(project_a)

    assert main(["forum", "post", "--project", "--json", "Hello from A"]) == 0
    post_payload = json.loads(capsys.readouterr().out)
    post = post_payload["event"]

    assert main(["forum", "history", "--project", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["project_id"] == project_a_id
    assert payload["event_count"] == 1
    assert payload["events"][0]["event"]["event_id"] == post["event_id"]


def test_forum_history_requires_project_context_or_project_id(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)

    assert main(["forum", "history"]) == 1
    assert (
        "forum history requires --project-id, --project, or --project-base"
        in capsys.readouterr().err
    )


def test_forum_post_accepts_project_base(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_root = tmp_path / "project"
    _init_project(project_root, capsys)
    monkeypatch.chdir(project_root)

    assert main(["forum", "post", "--project-base", "project", "--json", "Hello"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["event"]["author_project_id"] == _project_id(project_root)


def test_forum_feed_limit_returns_most_recent_matching_events(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = tmp_path / "agentos-home"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    monkeypatch.chdir(workspace)

    project_a_id = "00000000-0000-4000-8000-0000000000a1"
    project_b_id = "00000000-0000-4000-8000-0000000000b2"
    project_c_id = "00000000-0000-4000-8000-0000000000c3"

    append_forum_event(
        project_a_id,
        {
            "event_id": "00000000-0000-4000-8000-000000000011",
            "event_type": "post",
            "created_at": "2026-04-19T14:00:00Z",
            "author_project_id": project_a_id,
            "channel_project_id": project_a_id,
            "thread_root_post_id": "00000000-0000-4000-8000-000000000011",
            "body": "Root",
        },
    )
    append_forum_event(
        project_b_id,
        {
            "event_id": "00000000-0000-4000-8000-000000000012",
            "event_type": "reply",
            "created_at": "2026-04-19T14:00:01Z",
            "author_project_id": project_b_id,
            "channel_project_id": project_a_id,
            "thread_root_post_id": "00000000-0000-4000-8000-000000000011",
            "parent_post_id": "00000000-0000-4000-8000-000000000011",
            "body": "Reply 1",
        },
    )
    append_forum_event(
        project_c_id,
        {
            "event_id": "00000000-0000-4000-8000-000000000013",
            "event_type": "reply",
            "created_at": "2026-04-19T14:00:02Z",
            "author_project_id": project_c_id,
            "channel_project_id": project_a_id,
            "thread_root_post_id": "00000000-0000-4000-8000-000000000011",
            "parent_post_id": "00000000-0000-4000-8000-000000000012",
            "body": "Reply 2",
        },
    )

    assert main(["forum", "feed", "--channel", project_a_id, "--limit", "2", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert [item["event"]["event_id"] for item in payload["events"]] == [
        "00000000-0000-4000-8000-000000000012",
        "00000000-0000-4000-8000-000000000013",
    ]


def test_forum_help_describes_append_only_channel_model(capsys) -> None:
    with pytest.raises(SystemExit, match="0"):
        main(["forum", "--help"])

    output = capsys.readouterr().out
    assert "~/.agentos/forum" in output
    assert "append-only log" in output
    assert "target thread's channel" in output
    assert "agentos forum history --project-id <project-id>" in output


def test_forum_history_help_documents_headless_project_id_mode(capsys) -> None:
    with pytest.raises(SystemExit, match="0"):
        main(["forum", "history", "--help"])

    output = capsys.readouterr().out
    assert "append-only log" in output
    assert "--project-id PROJECT_ID" in output
    assert "headless reads outside a project checkout" in output
