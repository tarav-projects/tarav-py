from __future__ import annotations

import json
from pathlib import Path

from tarav.l1.agent.primitives import AgentConfig
from tarav.l1.agent.sessions import (
    _discover_direct_provider_sessions,
    _provider_agent_context_from_agent,
)
from tarav.l1.agent.providers.claude_code.agent import ClaudeAgent


def test_linked_claude_projects_target_is_skipped(tmp_path: Path) -> None:
    session_id = "67b706eb-d233-446f-96ce-926f52560eab"
    source_home = tmp_path / "claude"
    linked_home = tmp_path / "claude-br"
    _write_claude_session(source_home, session_id=session_id)
    linked_home.mkdir()
    (linked_home / "projects").symlink_to(source_home / "projects")

    sessions = _discover_direct_provider_sessions(_claude_context(linked_home))

    assert sessions == []


def test_normal_claude_projects_target_is_discovered(tmp_path: Path) -> None:
    session_id = "0553e855-0121-42d9-8624-91bd575dc09c"
    home = tmp_path / "claude"
    transcript_path = _write_claude_session(home, session_id=session_id)

    sessions = _discover_direct_provider_sessions(_claude_context(home))

    assert [session.session_id for session in sessions] == [session_id]
    assert sessions[0].primary_artifact_path() == transcript_path


def test_native_claude_archive_target_is_discovered(tmp_path: Path) -> None:
    session_id = "c8b8c77f-1150-4032-b0f4-5a9f088f9b18"
    home = tmp_path / "claude"
    transcript_path = _write_claude_session_at(
        home / "archive",
        session_id=session_id,
    )

    sessions = _discover_direct_provider_sessions(_claude_context(home))

    assert [session.session_id for session in sessions] == [session_id]
    assert sessions[0].primary_artifact_path() == transcript_path


def test_only_non_linked_claude_direct_targets_are_discovered(tmp_path: Path) -> None:
    linked_session_id = "67b706eb-d233-446f-96ce-926f52560eab"
    normal_session_id = "0553e855-0121-42d9-8624-91bd575dc09c"
    linked_source_home = tmp_path / "linked-source"
    linked_home = tmp_path / "linked-home"
    normal_target = tmp_path / "normal-projects"
    _write_claude_session(linked_source_home, session_id=linked_session_id)
    normal_transcript_path = _write_claude_session_at(normal_target, session_id=normal_session_id)
    linked_home.mkdir()
    (linked_home / "projects").symlink_to(linked_source_home / "projects")

    sessions = _discover_direct_provider_sessions(
        _claude_context(
            linked_home,
            direct_targets=(linked_home / "projects", normal_target),
        )
    )

    assert [session.session_id for session in sessions] == [normal_session_id]
    assert sessions[0].primary_artifact_path() == normal_transcript_path


def _claude_context(home: Path, *, direct_targets: tuple[Path, ...] | None = None):
    if direct_targets is None:
        direct_targets = (home / "projects",)
    agent = ClaudeAgent.from_config(
        AgentConfig(
            provider="claude-code",
            profile_id=home.name,
            home=home,
            direct_targets=direct_targets,
        )
    )
    return _provider_agent_context_from_agent(agent)


def _write_claude_session(home: Path, *, session_id: str) -> Path:
    return _write_claude_session_at(home / "projects", session_id=session_id)


def _write_claude_session_at(projects_root: Path, *, session_id: str) -> Path:
    transcript_path = projects_root / "-Users-pereiro-projects-agentos-project" / f"{session_id}.jsonl"
    transcript_path.parent.mkdir(parents=True)
    transcript_path.write_text(
        json.dumps(
            {
                "type": "user",
                "sessionId": session_id,
                "cwd": "/Users/pereiro/projects/agentos-project",
                "timestamp": "2026-06-09T21:00:00.000Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return transcript_path
