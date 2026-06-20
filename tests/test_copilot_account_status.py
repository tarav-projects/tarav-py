from __future__ import annotations

from pathlib import Path

import pytest

import agentos.copilot.account_status as copilot_account_status
from agentos.agent.account_status import AgentAccountContext, fresh_usage_record_metadata
from agentos.copilot.account_registry import register_copilot_account
from agentos.copilot.agent import CopilotAgent
from agentos.testing import AgentosTestEnvironment

from _helpers import read_json_file


def _accounts_file(environment: AgentosTestEnvironment) -> Path:
    return environment.agentos_home / "accounts" / "copilot-cli" / "accounts.json"


def _provider_root(environment: AgentosTestEnvironment) -> Path:
    return environment.agentos_home / "accounts" / "copilot-cli"


def _register(environment, monkeypatch, tmp_path) -> Path:
    environment.apply_environment(monkeypatch.setenv)
    register_copilot_account(account="jp", account_id="josePereiro", label="Copilot jp")
    home = tmp_path / "copilot-jp"
    home.mkdir(parents=True, exist_ok=True)
    return home


def _stub_usage(monkeypatch, *, payload, errors=()):
    def _fake(agent):
        if errors:
            return (), tuple(errors), None, None, None
        return (
            (),
            (),
            payload,
            payload,
            fresh_usage_record_metadata(
                source=copilot_account_status.COPILOT_INTERNAL_USER_USAGE_SOURCE
            ),
        )

    monkeypatch.setattr(copilot_account_status, "_account_usage_internal_user", _fake)


def test_successful_status_stamps_freshness_trail_without_artifact(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    home = _register(environment, monkeypatch, tmp_path)
    _stub_usage(monkeypatch, payload={"login": "josePereiro", "name": "Jose"})

    status = CopilotAgent(
        home=home,
        account=AgentAccountContext(provider="copilot-cli", account="jp"),
    ).account_status(record_usage=False)

    assert status.usage_status == "ok"
    record = read_json_file(_accounts_file(environment))["accounts"]["jp"]
    assert record["account_id"] == "josePereiro"
    assert record["last_verified_source"] == "account.status"
    assert isinstance(record["last_verified_at"], str) and record["last_verified_at"]
    # Metadata-only: no token, no artifact, nothing materialized.
    assert record["active_artifact_id"] is None
    assert not (_provider_root(environment) / "artifacts.jsonl").exists()
    assert not (_provider_root(environment) / "artifacts").exists()
    assert not (_provider_root(environment) / "verifications.jsonl").exists()


def test_failed_status_does_not_stamp_freshness_trail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    home = _register(environment, monkeypatch, tmp_path)
    from agentos.agent.account_status import AccountStatusError

    _stub_usage(
        monkeypatch,
        payload=None,
        errors=(AccountStatusError(error_type="timeout", message="boom"),),
    )

    CopilotAgent(
        home=home,
        account=AgentAccountContext(provider="copilot-cli", account="jp"),
    ).account_status(record_usage=False, fallback_to_usage_registry=False)

    record = read_json_file(_accounts_file(environment))["accounts"]["jp"]
    assert "last_verified_at" not in record
    assert "last_verified_source" not in record


def test_account_uses_gh_auth_token_auth_kind(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from agentos.copilot.account_registry import COPILOT_AUTH_KIND

    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    register_copilot_account(account="jp", account_id="josePereiro")

    assert COPILOT_AUTH_KIND == "gh-auth-token"
    record = read_json_file(_accounts_file(environment))["accounts"]["jp"]
    assert record["auth_kind"] == "gh-auth-token"
