from __future__ import annotations

import json
from pathlib import Path

from agentos.agent.primitives import AgentConfig
from agentos.agent.sessions import (
    _discover_direct_provider_sessions,
    _provider_agent_context_from_agent,
)
from agentos.claude.agent import ClaudeAgent


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


def _claude_context(home: Path):
    agent = ClaudeAgent.from_config(
        AgentConfig(
            provider="claude-code",
            instance_id=home.name,
            home=home,
            direct_targets=(home / "projects",),
        )
    )
    return _provider_agent_context_from_agent(agent)


def _write_claude_session(home: Path, *, session_id: str) -> Path:
    transcript_path = home / "projects" / "-Users-pereiro-projects-agentos-project" / f"{session_id}.jsonl"
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
