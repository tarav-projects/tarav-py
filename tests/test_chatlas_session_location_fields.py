from __future__ import annotations

import json
from pathlib import Path

from agentos.claude.session import discover_claude_session_refs, read_claude_project_session
from agentos.codex.session import read_codex_rollout_session_ref
from agentos.copilot.session import discover_copilot_session_refs, read_copilot_session
from agentos.pi.session import discover_pi_session_refs, read_pi_session


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_codex_rollout_ref_preserves_session_meta_cwd(tmp_path: Path) -> None:
    rollout_path = tmp_path / "rollout-2026-session-1.jsonl"
    _write(
        rollout_path,
        json.dumps(
            {
                "timestamp": "2026-03-08T01:08:59.089Z",
                "type": "session_meta",
                "payload": {
                    "id": "session-1",
                    "cwd": "/work/codex",
                },
            }
        )
        + "\n",
    )

    session_ref = read_codex_rollout_session_ref(rollout_path)

    assert session_ref is not None
    assert session_ref.native_ref_metadata()["cwd"] == "/work/codex"
    assert session_ref.to_session().cwd == "/work/codex"


def test_claude_project_session_preserves_top_level_cwd(tmp_path: Path) -> None:
    artifact_path = tmp_path / "session-1.jsonl"
    _write(
        artifact_path,
        json.dumps(
            {
                "sessionId": "session-1",
                "timestamp": "2026-03-08T01:08:59.089Z",
                "cwd": "/work/claude",
            }
        )
        + "\n",
    )

    session = read_claude_project_session(artifact_path)
    session_refs = discover_claude_session_refs(targets=(tmp_path,))

    assert session is not None
    assert session.cwd == "/work/claude"
    assert len(session_refs) == 1
    assert session_refs[0].native_ref_metadata()["cwd"] == "/work/claude"


def test_copilot_session_prefers_git_root_over_cwd(tmp_path: Path) -> None:
    events_path = tmp_path / "session-1" / "events.jsonl"
    _write(
        events_path,
        json.dumps(
            {
                "type": "session.start",
                "data": {
                    "context": {
                        "cwd": "/work/copilot/cwd",
                        "gitRoot": "/work/copilot/git",
                    }
                },
            }
        )
        + "\n",
    )

    session = read_copilot_session(events_path.parent)
    session_refs = discover_copilot_session_refs(targets=(tmp_path,))

    assert session is not None
    assert session.project_path == "/work/copilot/git"
    assert len(session_refs) == 1
    assert session_refs[0].native_ref_metadata()["project_path"] == "/work/copilot/git"


def test_copilot_session_falls_back_to_cwd(tmp_path: Path) -> None:
    events_path = tmp_path / "events.jsonl"
    _write(
        events_path,
        json.dumps(
            {
                "type": "session.start",
                "data": {"context": {"cwd": "/work/copilot/cwd"}},
            }
        )
        + "\n",
    )

    session = read_copilot_session(events_path)

    assert session is not None
    assert session.project_path == "/work/copilot/cwd"


def test_pi_session_ref_already_exposes_cwd_native_metadata(tmp_path: Path) -> None:
    artifact_path = tmp_path / "session-1.jsonl"
    _write(
        artifact_path,
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "session",
                        "id": "session-1",
                        "cwd": "/work/pi",
                        "timestamp": "2026-03-08T01:08:59.089Z",
                    }
                ),
                json.dumps(
                    {
                        "type": "model_change",
                        "provider": "openai",
                        "modelId": "gpt-5.4",
                    }
                ),
            ]
        )
        + "\n",
    )

    session = read_pi_session(artifact_path)
    session_refs = discover_pi_session_refs(targets=(tmp_path,))

    assert session is not None
    assert session.cwd == "/work/pi"
    assert len(session_refs) == 1
    assert session_refs[0].native_ref_metadata()["cwd"] == "/work/pi"
