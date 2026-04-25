from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos._core.errors import CliError
from agentos.cli import main
from agentos.forum.core import (
    append_forum_event,
    current_author_project,
    forum_project_events_path,
    forum_project_manifest_path,
    forum_projects_dir,
    forum_root,
    iter_all_forum_events,
    load_forum_event,
    load_or_register_forum_project,
)


def _init_project(tmp_path: Path, monkeypatch, capsys) -> Path:
    project_root = tmp_path / "project"
    project_root.mkdir()
    assert main(["init", "--scope", "project", "--project", str(project_root)]) == 0
    capsys.readouterr()
    monkeypatch.chdir(project_root)
    return project_root


def _patch_forum_times(monkeypatch, values: list[str]) -> None:
    iterator = iter(values)
    monkeypatch.setattr("agentos.forum.core.utc_now_iso", lambda: next(iterator))


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_forum_root_uses_agentos_home_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    agentos_home = tmp_path / "agentos-home"
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    assert forum_root() == agentos_home / "forum"
    assert forum_projects_dir() == agentos_home / "forum" / "projects"


def test_load_or_register_forum_project_creates_and_updates_manifest(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = tmp_path / "agentos-home"
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    project_root = _init_project(tmp_path, monkeypatch, capsys)
    _patch_forum_times(
        monkeypatch,
        [
            "2026-04-19T12:00:00Z",
            "2026-04-19T12:05:00Z",
        ],
    )

    identity = current_author_project()
    manifest = load_or_register_forum_project(identity)

    manifest_path = forum_project_manifest_path(str(identity["project_id"]))
    assert manifest_path.exists()
    assert manifest["project_id"] == identity["project_id"]
    assert manifest["display_name"] == "project"
    assert manifest["source_root"] == str(project_root.resolve())
    assert manifest["created_at"] == "2026-04-19T12:00:00Z"
    assert manifest["last_seen_at"] == "2026-04-19T12:00:00Z"

    updated = load_or_register_forum_project(
        {
            "project_id": identity["project_id"],
            "project_root": project_root,
            "display_name": "agentos-renamed",
        }
    )
    assert updated["created_at"] == "2026-04-19T12:00:00Z"
    assert updated["last_seen_at"] == "2026-04-19T12:05:00Z"
    assert updated["display_name"] == "agentos-renamed"

    on_disk = _load_json(manifest_path)
    assert on_disk["display_name"] == "agentos-renamed"
    assert on_disk["last_seen_at"] == "2026-04-19T12:05:00Z"


def test_append_forum_event_writes_and_loads_post(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = tmp_path / "agentos-home"
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _init_project(tmp_path, monkeypatch, capsys)
    _patch_forum_times(monkeypatch, ["2026-04-19T12:10:00Z"])

    identity = current_author_project()
    project_id = str(identity["project_id"])
    event = append_forum_event(
        project_id,
        {
            "event_type": "post",
            "author_project_id": project_id,
            "channel_project_id": project_id,
            "thread_root_post_id": "00000000-0000-4000-8000-000000000010",
            "event_id": "00000000-0000-4000-8000-000000000010",
            "body": "Changed the Agentos.Project contract.",
        },
    )

    events_path = forum_project_events_path(project_id)
    assert _read_jsonl(events_path) == [event]

    loaded = load_forum_event("00000000-0000-4000-8000-000000000010")
    assert loaded.source_file == events_path
    assert loaded.line_no == 1
    assert loaded.event == event


def test_iter_all_forum_events_reads_multiple_project_logs(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = tmp_path / "agentos-home"
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    project_root = _init_project(tmp_path, monkeypatch, capsys)
    _patch_forum_times(
        monkeypatch,
        [
            "2026-04-19T12:10:00Z",
            "2026-04-19T12:11:00Z",
            "2026-04-19T12:12:00Z",
            "2026-04-19T12:13:00Z",
        ],
    )

    identity = current_author_project()
    project_a = str(identity["project_id"])
    project_b = "00000000-0000-4000-8000-0000000000b2"

    load_or_register_forum_project(identity)
    load_or_register_forum_project(
        {
            "project_id": project_b,
            "project_root": project_root.parent / "project-b",
            "display_name": "project-b",
        }
    )

    append_forum_event(
        project_a,
        {
            "event_type": "post",
            "author_project_id": project_a,
            "channel_project_id": project_a,
            "thread_root_post_id": "00000000-0000-4000-8000-000000000010",
            "event_id": "00000000-0000-4000-8000-000000000010",
            "body": "Thread start.",
        },
    )
    append_forum_event(
        project_b,
        {
            "event_type": "reply",
            "author_project_id": project_b,
            "channel_project_id": project_a,
            "thread_root_post_id": "00000000-0000-4000-8000-000000000010",
            "parent_post_id": "00000000-0000-4000-8000-000000000010",
            "event_id": "00000000-0000-4000-8000-000000000011",
            "body": "Following up from project B.",
        },
    )

    events = list(iter_all_forum_events())
    events_by_id = {str(item.event["event_id"]): item for item in events}
    assert set(events_by_id) == {
        "00000000-0000-4000-8000-000000000010",
        "00000000-0000-4000-8000-000000000011",
    }
    reply = events_by_id["00000000-0000-4000-8000-000000000011"]
    assert reply.event["channel_project_id"] == project_a
    assert reply.event["author_project_id"] == project_b


def test_append_forum_event_validates_top_level_channel_ownership(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = tmp_path / "agentos-home"
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _init_project(tmp_path, monkeypatch, capsys)
    _patch_forum_times(monkeypatch, ["2026-04-19T12:10:00Z"])

    identity = current_author_project()
    project_id = str(identity["project_id"])

    with pytest.raises(CliError, match="own main channel"):
        append_forum_event(
            project_id,
            {
                "event_type": "post",
                "author_project_id": project_id,
                "channel_project_id": "00000000-0000-4000-8000-0000000000a2",
                "thread_root_post_id": "00000000-0000-4000-8000-000000000010",
                "event_id": "00000000-0000-4000-8000-000000000010",
                "body": "Invalid top-level post.",
            },
        )


def test_append_forum_event_validates_reaction_fields(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = tmp_path / "agentos-home"
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _init_project(tmp_path, monkeypatch, capsys)
    _patch_forum_times(monkeypatch, ["2026-04-19T12:10:00Z"])

    identity = current_author_project()
    project_id = str(identity["project_id"])

    with pytest.raises(CliError, match="reaction must be one of"):
        append_forum_event(
            project_id,
            {
                "event_type": "reaction",
                "author_project_id": project_id,
                "channel_project_id": project_id,
                "thread_root_post_id": "00000000-0000-4000-8000-000000000010",
                "target_post_id": "00000000-0000-4000-8000-000000000010",
                "event_id": "00000000-0000-4000-8000-000000000012",
                "reaction": "fire",
            },
        )
