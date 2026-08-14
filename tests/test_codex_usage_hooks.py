from __future__ import annotations

import json
from pathlib import Path

from tarav.agent.providers.codex.usage_hooks import (
    CODEX_SESSION_HOOK_USAGE_SOURCE,
    register_codex_usage_hook_callbacks,
)
from tarav.hooks import HookInvocation, HookRegistry
from tarav.testing import TaravTestEnvironment, codex_auth_json, seed_codex_account

from _helpers import read_jsonl_file, write_text_file


def _rollout(path: Path, *, session_id: str = "session-123") -> Path:
    events = [
        {
            "timestamp": "2026-08-11T12:00:00Z",
            "type": "session_meta",
            "payload": {"id": session_id},
        },
        {
            "timestamp": "2026-08-11T12:01:00Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {"total_token_usage": {"total_tokens": 1234}},
                "rate_limits": {
                    "limit_id": "codex",
                    "primary": {
                        "used_percent": 17.0,
                        "window_minutes": 10080,
                        "resets_at": 1787011287,
                    },
                    "secondary": None,
                    "plan_type": "plus",
                },
            },
        },
    ]
    write_text_file(
        path,
        "".join(json.dumps(event, separators=(",", ":")) + "\n" for event in events),
    )
    return path


def _registry(
    monkeypatch, tmp_path: Path
) -> tuple[TaravTestEnvironment, Path, HookRegistry]:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    codex_home = tmp_path / "codex-home"
    write_text_file(codex_home / "auth.json", codex_auth_json(account_id="account-1"))
    seed_codex_account("br", account_id="account-1")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    registry = HookRegistry()
    register_codex_usage_hook_callbacks(registry)
    return environment, codex_home, registry


def test_codex_turn_stop_records_normalized_account_quota(
    monkeypatch, tmp_path: Path
) -> None:
    environment, codex_home, registry = _registry(monkeypatch, tmp_path)
    transcript = _rollout(
        codex_home / "sessions" / "2026" / "08" / "11" / "rollout-session-123.jsonl"
    )

    registry.dispatch(
        HookInvocation(
            name="agent.turn.stop",
            ctx={"session_id": "session-123", "transcript_path": str(transcript)},
            ctx_type="codex",
        )
    )

    record_path = next(
        (environment.tarav_home / "agent" / "usage-registry").glob("*-usage.jsonl")
    )
    record = read_jsonl_file(record_path)[0]
    assert record["provider"] == "codex"
    assert record["account"] == "br"
    assert record["home"] == str(codex_home.resolve())
    assert record["source"] == CODEX_SESSION_HOOK_USAGE_SOURCE
    assert record["payload"]["rateLimits"] == {
        "limitId": "codex",
        "primary": {
            "usedPercent": 17,
            "windowDurationMins": 10080,
            "resetsAt": 1787011287,
        },
        "secondary": None,
    }
    assert record["payload"]["observation"] == {
        "sessionId": "session-123",
        "observedAt": "2026-08-11T12:01:00Z",
    }
    assert "tokenUsage" not in record["payload"]


def test_codex_turn_stop_locates_session_from_home_when_transcript_path_is_absent(
    monkeypatch, tmp_path: Path
) -> None:
    environment, _codex_home, registry = _registry(monkeypatch, tmp_path)
    _rollout(
        environment.home
        / ".codex"
        / "sessions"
        / "2026"
        / "08"
        / "11"
        / "rollout-session-123.jsonl"
    )

    registry.dispatch(
        HookInvocation(
            name="agent.turn.stop",
            ctx={"session_id": "session-123", "transcript_path": None},
            ctx_type="codex",
        )
    )

    records = list(
        (environment.tarav_home / "agent" / "usage-registry").glob("*-usage.jsonl")
    )
    assert len(records) == 1


def test_codex_quota_callback_ignores_other_context_types(
    monkeypatch, tmp_path: Path
) -> None:
    environment, codex_home, registry = _registry(monkeypatch, tmp_path)
    transcript = _rollout(codex_home / "sessions" / "rollout-session-123.jsonl")

    registry.dispatch(
        HookInvocation(
            name="agent.turn.stop",
            ctx={"session_id": "session-123", "transcript_path": str(transcript)},
            ctx_type="claude-code",
        )
    )

    assert not (environment.tarav_home / "agent" / "usage-registry").exists()
