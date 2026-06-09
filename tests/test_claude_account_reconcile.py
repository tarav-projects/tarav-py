from __future__ import annotations

import json
from pathlib import Path

import pytest

import agentos.claude.account_registry as claude_account_registry
from agentos.claude.account_registry import (
    inspect_claude_account_home,
    register_claude_account,
)
from agentos.claude.account_reconcile import (
    discover_claude_reconcile_homes,
    reconcile_claude_accounts,
)
from agentos.testing import AgentosTestEnvironment

from _helpers import read_json_file, read_jsonl_file, write_text_file


def test_claude_reconcile_registers_fresh_known_home_and_syncs_system_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    monkeypatch.setattr(claude_account_registry.sys, "platform", "linux")
    agentos_home = environment.agentos_home
    configured_home = tmp_path / "claude-br"
    system_home = agentos_home / "agent" / "homes" / "claude-code" / "browser-br"
    _write_claude_home(configured_home, email="br@example.com", account_uuid="acc_br")
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
        "synced_home",
    }
    account_payload = read_json_file(
        agentos_home / "accounts" / "claude-code" / "accounts.json"
    )
    artifact_id = account_payload["accounts"]["browser-br"]["active_artifact_id"]
    artifacts = read_jsonl_file(
        agentos_home / "accounts" / "claude-code" / "artifacts.jsonl"
    )
    assert {artifact["artifact_id"] for artifact in artifacts} == {artifact_id}
    system_status = inspect_claude_account_home(home=system_home)
    assert system_status["classification"] == "matching-active"
    assert system_status["auth"]["artifact_id"] == artifact_id


def test_claude_reconcile_warns_and_skips_unknown_account_auth(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    monkeypatch.setattr(claude_account_registry.sys, "platform", "linux")
    configured_home = tmp_path / "claude-unknown"
    _write_claude_home(
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
    _write_claude_home(configured_home, email="br@example.com", account_uuid="acc_br")
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
    assert payload["action_count"] >= 2
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
    _write_claude_home(configured_home, email="br@example.com", account_uuid="acc_br")
    _write_claude_home(system_home, email="br@example.com", account_uuid="acc_br")
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
        "would_activate_artifact",
    ]
    assert warnings == []


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


def _write_claude_home(
    home: Path,
    *,
    email: str,
    account_uuid: str,
    access_token: str = "secret-access",
    refresh_token: str = "secret-refresh",
) -> None:
    write_text_file(
        home / ".claude.json",
        json.dumps(
            {
                "oauthAccount": {
                    "accountUuid": account_uuid,
                    "emailAddress": email,
                    "displayName": "Browser BR",
                    "organizationUuid": "org_br",
                }
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    write_text_file(
        home / ".credentials.json",
        json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": access_token,
                    "refreshToken": refresh_token,
                }
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
