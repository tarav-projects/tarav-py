from __future__ import annotations

import stat
from pathlib import Path

import pytest

import agentos.claude.account_registry as claude_account_registry
from agentos._core.errors import CliError
from agentos.claude.account_registry import (
    link_claude_account_to_home,
    register_claude_account,
    register_claude_ambient_auth_from_home,
)
from agentos.testing import AgentosTestEnvironment

from _helpers import read_json_file, read_jsonl_file, write_claude_home


def test_claude_ambient_auth_registration_stores_artifact_and_safe_registry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    monkeypatch.setattr(claude_account_registry.sys, "platform", "linux")
    home = tmp_path / "claude-br"
    write_claude_home(home, email="br@example.com", account_uuid="acc_br")
    register_claude_account(account="browser-br", email="br@example.com")

    payload = register_claude_ambient_auth_from_home(
        home=home,
        account="browser-br",
    )

    account_payload = read_json_file(
        environment.agentos_home / "accounts" / "claude-code" / "accounts.json"
    )
    account = account_payload["accounts"]["browser-br"]
    artifact_id = account["active_artifact_id"]
    assert account["auth_kind"] == "ambient-browser-login"
    assert account["artifact_file"] == f"artifacts/{artifact_id}.ambient-auth.json"
    assert account["email"] == "br@example.com"
    assert account["account_uuid"] == "acc_br"
    artifact_path = (
        environment.agentos_home
        / "accounts"
        / "claude-code"
        / "artifacts"
        / f"{artifact_id}.ambient-auth.json"
    )
    assert stat.S_IMODE(artifact_path.stat().st_mode) == 0o600
    artifact_payload = read_json_file(artifact_path)
    assert artifact_payload["secure_storage"]["claudeAiOauth"]["refreshToken"] == (
        "secret-refresh"
    )
    artifacts = read_jsonl_file(
        environment.agentos_home / "accounts" / "claude-code" / "artifacts.jsonl"
    )
    assert artifacts == [
        {
            **artifacts[0],
            "account": "browser-br",
            "artifact_id": artifact_id,
            "auth_kind": "ambient-browser-login",
            "email": "br@example.com",
            "account_uuid": "acc_br",
            "storage_kind": "credentials-json",
            "source_home": str(home.resolve()),
        }
    ]
    assert "secure_storage" not in artifacts[0]
    assert "secure_storage" not in payload["auth"]


def test_claude_ambient_auth_duplicate_registration_reuses_artifact_entry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    monkeypatch.setattr(claude_account_registry.sys, "platform", "linux")
    home = tmp_path / "claude-br"
    write_claude_home(home, email="br@example.com", account_uuid="acc_br")
    register_claude_account(account="browser-br", email="br@example.com")

    first = register_claude_ambient_auth_from_home(home=home, account="browser-br")
    second = register_claude_ambient_auth_from_home(home=home, account="browser-br")

    artifacts = read_jsonl_file(
        environment.agentos_home / "accounts" / "claude-code" / "artifacts.jsonl"
    )
    assert len(artifacts) == 1
    assert first["artifact_entry"] == second["artifact_entry"]
    assert second["artifact_appended"] is False


def test_claude_ambient_auth_registration_rejects_identity_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    monkeypatch.setattr(claude_account_registry.sys, "platform", "linux")
    home = tmp_path / "claude-br"
    write_claude_home(home, email="other@example.com", account_uuid="acc_other")
    register_claude_account(account="browser-br", email="br@example.com")

    with pytest.raises(CliError, match="email br@example.com"):
        register_claude_ambient_auth_from_home(home=home, account="browser-br")


def test_claude_link_materializes_active_ambient_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    monkeypatch.setattr(claude_account_registry.sys, "platform", "linux")
    source_home = tmp_path / "claude-br"
    target_home = tmp_path / "managed-claude-br"
    write_claude_home(source_home, email="br@example.com", account_uuid="acc_br")
    register_claude_account(account="browser-br", email="br@example.com")
    registered = register_claude_ambient_auth_from_home(
        home=source_home,
        account="browser-br",
    )

    payload = link_claude_account_to_home(home=target_home, account="browser-br")

    assert payload["kind"] == "artifact"
    assert payload["artifact_id"] == registered["auth"]["artifact_id"]
    target_credentials = read_json_file(target_home / ".credentials.json")
    assert target_credentials["claudeAiOauth"]["accessToken"] == "secret-access"
    assert target_credentials["claudeAiOauth"]["refreshToken"] == "secret-refresh"
    target_config = read_json_file(target_home / ".claude.json")
    assert target_config["oauthAccount"]["emailAddress"] == "br@example.com"
    assert target_config["oauthAccount"]["accountUuid"] == "acc_br"


def test_claude_link_rejects_target_identity_mismatch_without_force(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    monkeypatch.setattr(claude_account_registry.sys, "platform", "linux")
    source_home = tmp_path / "claude-br"
    target_home = tmp_path / "managed-claude-br"
    write_claude_home(source_home, email="br@example.com", account_uuid="acc_br")
    write_claude_home(target_home, email="other@example.com", account_uuid="acc_other")
    register_claude_account(account="browser-br", email="br@example.com")
    register_claude_ambient_auth_from_home(home=source_home, account="browser-br")

    with pytest.raises(CliError, match="without --force"):
        link_claude_account_to_home(home=target_home, account="browser-br")
