from __future__ import annotations

from pathlib import Path

import pytest

import tarav.agent.providers.claude_code.keychain as claude_keychain
import tarav.agent.providers.claude_code.account_status as claude_account_status
from tarav.agent.account_status import (
    AccountLimit,
    AgentAccountContext,
    fresh_usage_record_metadata,
)
from tarav.agent.providers.claude_code.agent import ClaudeAgent
from tarav.testing import TaravTestEnvironment

from tarav.testing import seed_claude_account, write_claude_home
from _helpers import read_jsonl_file


def test_claude_statusline_env_does_not_author_policy_env() -> None:
    env = claude_account_status._claude_statusline_process_environment(
        {"CLAUDE_CONFIG_DIR": "/tmp/claude-home"}
    )

    assert env["CLAUDE_CONFIG_DIR"] == "/tmp/claude-home"
    assert "CLAUDE_CODE_DISABLE_AUTO_MEMORY" not in env
    assert "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC" not in env


def test_claude_statusline_env_preserves_config_declared_policy_env() -> None:
    env = claude_account_status._claude_statusline_process_environment(
        {
            "CLAUDE_CONFIG_DIR": "/tmp/claude-home",
            "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "0",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "configured",
        }
    )

    assert env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "0"
    assert env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "configured"


def test_claude_account_status_is_read_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # account_status must not mutate: no active-promote, no verification write.
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    monkeypatch.setattr(claude_keychain.sys, "platform", "linux")
    home = tmp_path / "claude-br"
    write_claude_home(home, email="br@example.com", account_uuid="acc_br")
    seed_claude_account("browser-br", account_uuid="acc_br", email="br@example.com")

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
    # read-only: no active-promote ran
    assert status.raw["auth_artifact_record"] is None
    # status wrote no verification evidence
    verifications_path = (
        environment.tarav_home / "accounts" / "claude-code" / "verifications.jsonl"
    )
    status_verifications = (
        [v for v in read_jsonl_file(verifications_path) if v.get("source") == "account.status"]
        if verifications_path.exists()
        else []
    )
    assert status_verifications == []


