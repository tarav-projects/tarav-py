from __future__ import annotations

from pathlib import Path

import pytest

from agentos._core.errors import CliError
from agentos.agent.account_registry import append_verification, read_verifications
from agentos.testing import AgentosTestEnvironment


def test_account_verification_ledger_appends_safe_records(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)

    record = append_verification(
        "claude-code",
        {
            "account": "browser-br",
            "artifact_id": "abc123",
            "auth_kind": "ambient-browser-login",
            "home": str(tmp_path / "claude-br"),
            "source": "agent.ping",
        },
    )

    assert record["provider"] == "claude-code"
    assert record["account"] == "browser-br"
    assert record["artifact_id"] == "abc123"
    assert "verified_at" in record
    assert read_verifications("claude-code") == [record]


def test_account_verification_ledger_rejects_secret_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)

    with pytest.raises(CliError, match="secret-bearing field"):
        append_verification(
            "claude-code",
            {
                "account": "browser-br",
                "artifact_id": "abc123",
                "auth_kind": "ambient-browser-login",
                "source": "agent.ping",
                "secure_storage": {"claudeAiOauth": {"refreshToken": "secret"}},
            },
        )
