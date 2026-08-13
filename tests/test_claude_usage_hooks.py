from __future__ import annotations

from pathlib import Path

import pytest

import agentos.agent.providers.claude_code.keychain as claude_keychain
from agentos.agent.providers.claude_code.usage_hooks import (
    CLAUDE_STATUSLINE_CONTEXT_HOOK,
    CLAUDE_STATUSLINE_HOOK_USAGE_SOURCE,
    register_claude_usage_hook_callbacks,
)
from agentos.hooks import HookInvocation, HookRegistry
from agentos.runtime import create_runtime
from agentos.testing import (
    AgentosTestEnvironment,
    seed_claude_account,
    write_claude_home,
    write_raw_json,
)

from _helpers import read_jsonl_file


def _registry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[AgentosTestEnvironment, Path, HookRegistry]:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    monkeypatch.setattr(claude_keychain.sys, "platform", "linux")
    home = tmp_path / "claude-home"
    write_claude_home(home, email="om@example.com", account_uuid="account-om")
    seed_claude_account(
        "om",
        account_uuid="account-om",
        email="om@example.com",
    )
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home))
    registry = HookRegistry()
    register_claude_usage_hook_callbacks(registry)
    return environment, home, registry


def _context(*, used_percentage: float = 17.2) -> dict[str, object]:
    return {
        "session_id": "session-123",
        "transcript_path": "/private/session.jsonl",
        "workspace": {"current_dir": "/private/project"},
        "future_secret": "must-not-be-stored",
        "rate_limits": {
            "five_hour": {
                "used_percentage": used_percentage,
                "resets_at": 1787011287,
            },
            "seven_day": {
                "used_percentage": 42,
                "resets_at": 1787529687,
            },
            "future_limit": {
                "used_percentage": 99,
                "resets_at": 1787529687,
            },
        },
    }


def _dispatch(registry: HookRegistry, context: dict[str, object]) -> None:
    registry.dispatch(
        HookInvocation(
            name=CLAUDE_STATUSLINE_CONTEXT_HOOK,
            ctx=context,
            ctx_type="claude-code",
        )
    )


def _usage_records(environment: AgentosTestEnvironment) -> list[dict[str, object]]:
    paths = sorted(
        (environment.agentos_home / "agent" / "usage-registry").glob("*-usage.jsonl")
    )
    return [record for path in paths for record in read_jsonl_file(path)]


def test_claude_statusline_context_records_only_safe_account_quota(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment, home, registry = _registry(monkeypatch, tmp_path)

    _dispatch(registry, _context())

    record = _usage_records(environment)[0]
    assert record["provider"] == "claude-code"
    assert record["account"] == "om"
    assert record["home"] == str(home.resolve())
    assert record["source"] == CLAUDE_STATUSLINE_HOOK_USAGE_SOURCE
    assert record["payload"]["rate_limits"] == {
        "five_hour": {
            "used_percentage": 17.2,
            "resets_at": 1787011287,
        },
        "seven_day": {
            "used_percentage": 42,
            "resets_at": 1787529687,
        },
    }
    assert record["payload"]["observation"]["sessionId"] == "session-123"
    assert record["payload"]["observation"]["observedAt"].endswith("Z")
    assert "workspace" not in record["payload"]
    assert "transcript_path" not in record["payload"]
    assert "future_secret" not in record["payload"]


def test_claude_statusline_context_resolves_identity_without_secure_storage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "claude-home"
    write_raw_json(
        home / ".claude.json",
        {
            "oauthAccount": {
                "accountUuid": "account-om",
                "emailAddress": "om@example.com",
            }
        },
    )
    seed_claude_account(
        "om",
        account_uuid="account-om",
        email="om@example.com",
    )
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home))
    registry = HookRegistry()
    register_claude_usage_hook_callbacks(registry)

    _dispatch(registry, _context())

    assert _usage_records(environment)[0]["account"] == "om"


def test_claude_statusline_context_throttles_unchanged_quota_but_writes_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment, _home, registry = _registry(monkeypatch, tmp_path)

    _dispatch(registry, _context())
    _dispatch(registry, _context())
    _dispatch(registry, _context(used_percentage=18))

    records = _usage_records(environment)
    assert len(records) == 2
    assert records[-1]["payload"]["rate_limits"]["five_hour"]["used_percentage"] == 18


def test_claude_statusline_context_writes_unchanged_heartbeat_after_interval(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import agentos.agent.providers.claude_code.usage_hooks as usage_hooks

    environment, _home, registry = _registry(monkeypatch, tmp_path)
    _dispatch(registry, _context())
    monkeypatch.setattr(usage_hooks, "usage_record_age_sec", lambda value: 60)

    _dispatch(registry, _context())

    assert len(_usage_records(environment)) == 2


def test_claude_statusline_callback_ignores_other_context_types(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment, _home, registry = _registry(monkeypatch, tmp_path)

    registry.dispatch(
        HookInvocation(
            name=CLAUDE_STATUSLINE_CONTEXT_HOOK,
            ctx=_context(),
            ctx_type="codex",
        )
    )

    assert not (environment.agentos_home / "agent" / "usage-registry").exists()


def test_runtime_composes_claude_statusline_context_callback() -> None:
    runtime = create_runtime()

    assert runtime.hooks.has_callbacks(CLAUDE_STATUSLINE_CONTEXT_HOOK)
