from __future__ import annotations

from pathlib import Path

import pytest

import tarav.agent.providers.claude_code.keychain as claude_keychain
from tarav.agent.providers.claude_code.usage_hooks import (
    CLAUDE_STATUSLINE_CONTEXT_HOOK,
    CLAUDE_STATUSLINE_HOOK_USAGE_SOURCE,
    register_claude_usage_hook_callbacks,
    report_claude_usage_from_hook,
)
from tarav.hooks import HookError, HookInvocation, HookRegistry
from tarav.runtime import create_runtime
from tarav.testing import (
    TaravTestEnvironment,
    seed_claude_account,
    write_claude_home,
    write_raw_json,
)

from _helpers import read_jsonl_file


def _registry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[TaravTestEnvironment, Path, HookRegistry]:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    monkeypatch.setattr(claude_keychain.sys, "platform", "linux")
    home = tmp_path / "claude-home"
    write_claude_home(home, email="om@example.com", account_uuid="account-om")
    seed_claude_account(
        "om",
        account_uuid="account-om",
        email="om@example.com",
    )
    _decoy_env_home(monkeypatch, tmp_path)
    registry = HookRegistry()
    register_claude_usage_hook_callbacks(registry)
    return environment, home, registry


def _decoy_env_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the environment at a home the hook must never read.

    Attribution comes from the invocation context alone, so a stale or absent
    ``CLAUDE_CONFIG_DIR`` must not influence which account a record lands under.
    """

    decoy = tmp_path / "decoy-home"
    write_claude_home(decoy, email="jp@example.com", account_uuid="account-jp")
    seed_claude_account("jp", account_uuid="account-jp", email="jp@example.com")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(decoy))
    return decoy


def _transcript_path(home: Path) -> str:
    return str(home / "projects" / "-private-project" / "session-123.jsonl")


def _context(home: Path, *, used_percentage: float = 17.2) -> dict[str, object]:
    return {
        "session_id": "session-123",
        "transcript_path": _transcript_path(home),
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


def _invocation(context: dict[str, object]) -> HookInvocation:
    return HookInvocation(
        name=CLAUDE_STATUSLINE_CONTEXT_HOOK,
        ctx=context,
        ctx_type="claude-code",
    )


def _dispatch(registry: HookRegistry, context: dict[str, object]) -> None:
    registry.dispatch(_invocation(context))


def _usage_records(environment: TaravTestEnvironment) -> list[dict[str, object]]:
    paths = sorted(
        (environment.tarav_home / "agent" / "usage-registry").glob("*-usage.jsonl")
    )
    return [record for path in paths for record in read_jsonl_file(path)]


def test_claude_statusline_context_records_only_safe_account_quota(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment, home, registry = _registry(monkeypatch, tmp_path)

    _dispatch(registry, _context(home))

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
    environment = TaravTestEnvironment.create(tmp_path)
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
    _decoy_env_home(monkeypatch, tmp_path)
    registry = HookRegistry()
    register_claude_usage_hook_callbacks(registry)

    _dispatch(registry, _context(home))

    assert _usage_records(environment)[0]["account"] == "om"


def test_claude_statusline_context_throttles_unchanged_quota_but_writes_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment, home, registry = _registry(monkeypatch, tmp_path)

    _dispatch(registry, _context(home))
    _dispatch(registry, _context(home))
    _dispatch(registry, _context(home, used_percentage=18))

    records = _usage_records(environment)
    assert len(records) == 2
    assert records[-1]["payload"]["rate_limits"]["five_hour"]["used_percentage"] == 18


def test_claude_statusline_context_writes_unchanged_heartbeat_after_interval(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import tarav.agent.providers.claude_code.usage_hooks as usage_hooks

    environment, home, registry = _registry(monkeypatch, tmp_path)
    _dispatch(registry, _context(home))
    monkeypatch.setattr(usage_hooks, "usage_record_age_sec", lambda value: 60)

    _dispatch(registry, _context(home))

    assert len(_usage_records(environment)) == 2


def test_claude_statusline_callback_ignores_other_context_types(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment, home, registry = _registry(monkeypatch, tmp_path)

    registry.dispatch(
        HookInvocation(
            name=CLAUDE_STATUSLINE_CONTEXT_HOOK,
            ctx=_context(home),
            ctx_type="codex",
        )
    )

    assert not (environment.tarav_home / "agent" / "usage-registry").exists()


def test_runtime_composes_claude_statusline_context_callback() -> None:
    runtime = create_runtime()

    assert runtime.hooks.has_callbacks(CLAUDE_STATUSLINE_CONTEXT_HOOK)


def test_claude_statusline_context_attributes_the_home_that_produced_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Two homes reporting concurrently must not collapse onto one account.

    The regression: the hook read the home from ``CLAUDE_CONFIG_DIR`` with a
    fallback to ``~/.claude``. Claude Code does not pass that variable to the
    statusLine child process, so every session's usage was filed under whichever
    account owned the default home.
    """

    environment, om_home, registry = _registry(monkeypatch, tmp_path)
    br_home = tmp_path / "claude-home-br"
    write_claude_home(br_home, email="br@example.com", account_uuid="account-br")
    seed_claude_account("br", account_uuid="account-br", email="br@example.com")

    _dispatch(registry, _context(om_home, used_percentage=17.2))
    _dispatch(registry, _context(br_home, used_percentage=88))

    records = _usage_records(environment)
    by_account = {record["account"]: record for record in records}
    assert set(by_account) == {"om", "br"}
    assert by_account["om"]["home"] == str(om_home.resolve())
    assert by_account["br"]["home"] == str(br_home.resolve())
    assert by_account["om"]["payload"]["rate_limits"]["five_hour"][
        "used_percentage"
    ] == 17.2
    assert by_account["br"]["payload"]["rate_limits"]["five_hour"][
        "used_percentage"
    ] == 88


def test_claude_statusline_context_refuses_a_context_without_a_transcript(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment, home, _registry_unused = _registry(monkeypatch, tmp_path)
    context = _context(home)
    del context["transcript_path"]

    with pytest.raises(HookError, match="transcript_path"):
        report_claude_usage_from_hook(_invocation(context))

    assert not (environment.tarav_home / "agent" / "usage-registry").exists()


def test_claude_statusline_context_refuses_a_transcript_outside_a_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment, home, _registry_unused = _registry(monkeypatch, tmp_path)
    context = _context(home)
    context["transcript_path"] = "/private/session.jsonl"

    with pytest.raises(HookError, match="not under a provider home"):
        report_claude_usage_from_hook(_invocation(context))

    assert not (environment.tarav_home / "agent" / "usage-registry").exists()
