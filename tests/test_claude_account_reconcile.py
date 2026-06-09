from __future__ import annotations

from pathlib import Path

import pytest

import agentos.claude.account_registry as claude_account_registry
import agentos.claude.account_reconcile as claude_account_reconcile
from agentos.agent.account_registry import append_verification
from agentos.agent.account_status import AgentAccountContext
from agentos.agent.primitives import AgentPingConfig
from agentos.agent.run_runtime import AgentRunResult
from agentos.claude.account_registry import (
    inspect_claude_account_home,
    read_claude_ambient_auth_info,
    register_claude_account,
    register_claude_ambient_auth_from_home,
)
from agentos.claude.account_reconcile import (
    discover_claude_reconcile_homes,
    reconcile_claude_accounts,
)
from agentos.testing import AgentosTestEnvironment

from _helpers import read_json_file, read_jsonl_file, write_claude_home


def test_claude_reconcile_registers_fresh_known_home_without_activating(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    monkeypatch.setattr(claude_account_registry.sys, "platform", "linux")
    agentos_home = environment.agentos_home
    configured_home = tmp_path / "claude-br"
    system_home = agentos_home / "agent" / "homes" / "claude-code" / "browser-br"
    write_claude_home(configured_home, email="br@example.com", account_uuid="acc_br")
    environment.write_profiles(
        [
            {
                "id": "claude-br",
                "provider": "claude-code",
                "home": str(configured_home),
                "account": "browser-br",
            }
        ]
    )
    register_claude_account(account="browser-br", email="br@example.com")

    payload = reconcile_claude_accounts(start_path=tmp_path)

    actions = payload["actions"]
    assert isinstance(actions, list)
    assert {action["kind"] for action in actions if isinstance(action, dict)} == {
        "registered_artifact",
    }
    assert [warning["kind"] for warning in payload["warnings"]] == []
    account_payload = read_json_file(
        agentos_home / "accounts" / "claude-code" / "accounts.json"
    )
    artifact_id = read_claude_ambient_auth_info(configured_home).artifact_id
    assert account_payload["accounts"]["browser-br"]["active_artifact_id"] is None
    artifacts = read_jsonl_file(
        agentos_home / "accounts" / "claude-code" / "artifacts.jsonl"
    )
    assert {artifact["artifact_id"] for artifact in artifacts} == {artifact_id}
    system_status = inspect_claude_account_home(home=system_home)
    assert system_status["classification"] == "missing"


def test_claude_reconcile_warns_and_skips_unknown_account_auth(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    monkeypatch.setattr(claude_account_registry.sys, "platform", "linux")
    configured_home = tmp_path / "claude-unknown"
    write_claude_home(
        configured_home,
        email="unknown@example.com",
        account_uuid="acc_unknown",
    )
    environment.write_profiles(
        [
            {
                "id": "claude-unknown",
                "provider": "claude-code",
                "home": str(configured_home),
            }
        ]
    )

    payload = reconcile_claude_accounts(start_path=tmp_path)

    assert payload["action_count"] == 0
    warnings = payload["warnings"]
    assert isinstance(warnings, list)
    assert [warning["kind"] for warning in warnings if isinstance(warning, dict)] == [
        "unknown_account_auth"
    ]
    assert not (
        environment.agentos_home / "accounts" / "claude-code" / "artifacts.jsonl"
    ).exists()


def test_claude_reconcile_check_does_not_mutate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    monkeypatch.setattr(claude_account_registry.sys, "platform", "linux")
    agentos_home = environment.agentos_home
    configured_home = tmp_path / "claude-br"
    write_claude_home(configured_home, email="br@example.com", account_uuid="acc_br")
    environment.write_profiles(
        [
            {
                "id": "claude-br",
                "provider": "claude-code",
                "home": str(configured_home),
                "account": "browser-br",
            }
        ]
    )
    register_claude_account(account="browser-br", email="br@example.com")

    payload = reconcile_claude_accounts(start_path=tmp_path, check=True)

    assert payload["check"] is True
    assert [action["kind"] for action in payload["actions"]] == ["would_register_artifact"]
    account_payload = read_json_file(
        agentos_home / "accounts" / "claude-code" / "accounts.json"
    )
    assert account_payload["accounts"]["browser-br"]["active_artifact_id"] is None
    assert not (agentos_home / "accounts" / "claude-code" / "artifacts.jsonl").exists()


def test_claude_reconcile_dedupes_same_artifact_from_multiple_homes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    monkeypatch.setattr(claude_account_registry.sys, "platform", "linux")
    agentos_home = environment.agentos_home
    configured_home = tmp_path / "claude-br"
    system_home = agentos_home / "agent" / "homes" / "claude-code" / "browser-br"
    write_claude_home(configured_home, email="br@example.com", account_uuid="acc_br")
    write_claude_home(system_home, email="br@example.com", account_uuid="acc_br")
    environment.write_profiles(
        [
            {
                "id": "claude-br",
                "provider": "claude-code",
                "home": str(configured_home),
                "account": "browser-br",
            }
        ]
    )
    register_claude_account(account="browser-br", email="br@example.com")

    payload = reconcile_claude_accounts(start_path=tmp_path, check=True)

    actions = payload["actions"]
    warnings = payload["warnings"]
    assert isinstance(actions, list)
    assert isinstance(warnings, list)
    assert [action["kind"] for action in actions if isinstance(action, dict)] == [
        "would_register_artifact",
    ]
    assert warnings == []


def test_claude_reconcile_activates_verified_artifact_and_syncs_stale_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    monkeypatch.setattr(claude_account_registry.sys, "platform", "linux")
    agentos_home = environment.agentos_home
    configured_home = tmp_path / "claude-br"
    system_home = agentos_home / "agent" / "homes" / "claude-code" / "browser-br"
    write_claude_home(
        configured_home,
        email="br@example.com",
        account_uuid="acc_br",
        access_token="broken-access",
    )
    write_claude_home(
        system_home,
        email="br@example.com",
        account_uuid="acc_br",
        access_token="working-access",
    )
    environment.write_profiles(
        [
            {
                "id": "claude-br",
                "provider": "claude-code",
                "home": str(configured_home),
                "account": "browser-br",
            }
        ]
    )
    register_claude_account(account="browser-br", email="br@example.com")
    registered = register_claude_ambient_auth_from_home(
        home=system_home,
        account="browser-br",
        register_only=True,
    )
    verified_artifact_id = registered["auth"]["artifact_id"]
    append_verification(
        "claude-code",
        {
            "account": "browser-br",
            "artifact_id": verified_artifact_id,
            "auth_kind": "ambient-browser-login",
            "home": str(system_home),
            "source": "agent.ping",
            "verified_at": "2026-06-09T00:00:00Z",
        },
    )

    payload = reconcile_claude_accounts(start_path=tmp_path)

    assert [action["kind"] for action in payload["actions"]] == [
        "registered_artifact",
        "activated_verified_artifact",
        "synced_home",
    ]
    account_payload = read_json_file(
        agentos_home / "accounts" / "claude-code" / "accounts.json"
    )
    assert (
        account_payload["accounts"]["browser-br"]["active_artifact_id"]
        == verified_artifact_id
    )
    configured_status = inspect_claude_account_home(home=configured_home)
    assert configured_status["classification"] == "matching-active"
    assert configured_status["auth"]["artifact_id"] == verified_artifact_id


def test_claude_reconcile_ping_verifies_successful_candidate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    monkeypatch.setattr(claude_account_registry.sys, "platform", "linux")
    home = tmp_path / "claude-br"
    write_claude_home(home, email="br@example.com", account_uuid="acc_br")
    environment.write_profiles(
        [
            {
                "id": "claude-br",
                "provider": "claude-code",
                "home": str(home),
                "account": "browser-br",
            }
        ]
    )
    register_claude_account(account="browser-br", email="br@example.com")
    monkeypatch.setattr(
        claude_account_reconcile,
        "build_registered_account_agent",
        lambda **kwargs: _FakePingAgent(home=Path(kwargs["home"]), stdout="745"),
    )

    payload = reconcile_claude_accounts(start_path=tmp_path, ping=True)

    assert [action["kind"] for action in payload["actions"]] == [
        "registered_artifact",
        "verified_artifact",
        "synced_home",
    ]
    account_payload = read_json_file(
        environment.agentos_home / "accounts" / "claude-code" / "accounts.json"
    )
    artifact_id = read_claude_ambient_auth_info(home).artifact_id
    assert account_payload["accounts"]["browser-br"]["active_artifact_id"] == artifact_id
    verifications = read_jsonl_file(
        environment.agentos_home / "accounts" / "claude-code" / "verifications.jsonl"
    )
    assert verifications[-1]["source"] == "accounts.reconcile.ping"


def test_claude_reconcile_check_ping_does_not_run_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    monkeypatch.setattr(claude_account_registry.sys, "platform", "linux")
    home = tmp_path / "claude-br"
    write_claude_home(home, email="br@example.com", account_uuid="acc_br")
    environment.write_profiles(
        [
            {
                "id": "claude-br",
                "provider": "claude-code",
                "home": str(home),
                "account": "browser-br",
            }
        ]
    )
    register_claude_account(account="browser-br", email="br@example.com")

    def fail_build_registered_account_agent(**kwargs):
        raise AssertionError("check ping must not build a live agent")

    monkeypatch.setattr(
        claude_account_reconcile,
        "build_registered_account_agent",
        fail_build_registered_account_agent,
    )

    payload = reconcile_claude_accounts(start_path=tmp_path, ping=True, check=True)

    assert [action["kind"] for action in payload["actions"]] == [
        "would_register_artifact",
        "would_ping",
    ]
    assert not (
        environment.agentos_home / "accounts" / "claude-code" / "verifications.jsonl"
    ).exists()


def test_claude_reconcile_discovers_configured_and_system_homes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    configured_home = tmp_path / "configured-claude"
    environment.write_profiles(
        [
            {
                "id": "claude-br",
                "provider": "claude-code",
                "home": str(configured_home),
                "account": "browser-br",
            }
        ]
    )
    register_claude_account(account="browser-br", email="br@example.com")

    homes = discover_claude_reconcile_homes(start_path=tmp_path)

    discovered = {home["home"] for home in homes}
    assert discovered == {
        str(configured_home.resolve()),
        str(
            (
                environment.agentos_home
                / "agent"
                / "homes"
                / "claude-code"
                / "browser-br"
            ).resolve()
        ),
    }


class _FakePingAgent:
    provider = "claude-code"
    instance_id = "claude-br"
    account = AgentAccountContext(provider="claude-code", account="browser-br")
    ping = AgentPingConfig(expected_number=745)

    def __init__(self, *, home: Path, stdout: str, exit_code: int = 0) -> None:
        self.home = home
        self.stdout = stdout
        self.exit_code = exit_code

    def run(self, command_config, run_config) -> AgentRunResult:
        return AgentRunResult(exit_code=self.exit_code, stdout=self.stdout)
