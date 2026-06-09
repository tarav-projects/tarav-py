from __future__ import annotations

import json
from pathlib import Path

import pytest

import agentos.claude.agent as claude_agent_module
import agentos.claude.account_registry as claude_account_registry
import agentos.claude.account_status as claude_account_status
from agentos.agent.account_status import (
    AccountLimit,
    AgentAccountContext,
    fresh_usage_record_metadata,
)
from agentos.agent.run_runtime import AgentCommandConfig, AgentRunConfig, AgentRunResult
from agentos.claude.account_registry import register_claude_account
from agentos.claude.agent import ClaudeAgent
from agentos.testing import AgentosTestEnvironment

from _helpers import read_json_file, write_text_file


def test_claude_account_status_success_refreshes_ambient_auth_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    monkeypatch.setattr(claude_account_registry.sys, "platform", "linux")
    home = tmp_path / "claude-br"
    _write_claude_home(home, email="br@example.com", account_uuid="acc_br")
    register_claude_account(account="browser-br", email="br@example.com")

    monkeypatch.setattr(
        claude_account_status,
        "_account_usage_statusline",
        lambda agent, cleanup_transcript=False: (
            (
                AccountLimit(
                    limit_class="usage",
                    limit_id="test",
                    limit_name="Test",
                    limit_label="Test",
                ),
            ),
            (),
            {"limits": []},
            {"limits": []},
            fresh_usage_record_metadata(
                source=claude_account_status.CLAUDE_STATUSLINE_USAGE_SOURCE
            ),
        ),
    )

    status = ClaudeAgent(
        home=home,
        account=AgentAccountContext(provider="claude-code", account="browser-br"),
    ).account_status(record_usage=False)

    assert status.usage_status == "ok"
    auth_record = status.raw["auth_artifact_record"]
    assert isinstance(auth_record, dict)
    assert auth_record["status"] == "ok"
    account_payload = read_json_file(
        environment.agentos_home / "accounts" / "claude-code" / "accounts.json"
    )
    artifact_id = account_payload["accounts"]["browser-br"]["active_artifact_id"]
    assert auth_record["artifact_id"] == artifact_id


def test_claude_successful_run_refreshes_ambient_auth_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    monkeypatch.setattr(claude_account_registry.sys, "platform", "linux")
    home = tmp_path / "claude-br"
    _write_claude_home(home, email="br@example.com", account_uuid="acc_br")
    register_claude_account(account="browser-br", email="br@example.com")
    monkeypatch.setattr(
        claude_agent_module,
        "execute_agent_command",
        lambda command, *, run_config: AgentRunResult(exit_code=0, stdout="ok"),
    )

    result = ClaudeAgent(
        home=home,
        cli_command=("claude",),
        account=AgentAccountContext(provider="claude-code", account="browser-br"),
    ).run(
        AgentCommandConfig(prompt="hello", interaction_mode="non_interactive"),
        AgentRunConfig(cwd=tmp_path),
    )

    assert result.exit_code == 0
    account_payload = read_json_file(
        environment.agentos_home / "accounts" / "claude-code" / "accounts.json"
    )
    assert account_payload["accounts"]["browser-br"]["active_artifact_id"] is not None


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
