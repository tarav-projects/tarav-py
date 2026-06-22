from __future__ import annotations

from pathlib import Path

import pytest

from agentos._core.errors import CliError
from agentos.agent.account_registry import (
    append_verification,
    archive_account_registry,
    read_verifications,
    write_accounts,
)
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


def test_archive_account_registry_copies_and_does_not_clobber(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)

    write_accounts("codex", {"provider": "codex", "accounts": {"tk": {"provider": "codex", "account": "tk"}}})
    from agentos._core.project import agentos_home_dir

    accounts_root = agentos_home_dir() / "accounts"
    original = (accounts_root / "codex" / "accounts.json").read_text(encoding="utf-8")

    first = archive_account_registry(label="t1")
    archived = agentos_home_dir() / "archive" / "accounts-t1"
    assert first["status"] == "archived"
    assert (archived / "codex" / "accounts.json").read_text(encoding="utf-8") == original

    # original untouched
    assert (accounts_root / "codex" / "accounts.json").read_text(encoding="utf-8") == original

    # re-run with the same label must not clobber the existing archive
    (archived / "marker.txt").write_text("keep", encoding="utf-8")
    second = archive_account_registry(label="t1")
    assert second["status"] == "exists"
    assert (archived / "marker.txt").read_text(encoding="utf-8") == "keep"


def test_archive_account_registry_skips_when_no_registry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)

    result = archive_account_registry(label="t1")
    assert result["status"] == "empty"


def test_load_account_accepts_old_and_new_shape(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agentos.agent.account_registry import load_account

    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)

    write_accounts(
        "codex",
        {
            "provider": "codex",
            "accounts": {
                # old shape — account-level auth_kind
                "old": {"provider": "codex", "account": "old", "auth_kind": "auth-json"},
                # new shape — no account-level auth_kind, nested auth_methods instead
                "new": {
                    "provider": "codex",
                    "account": "new",
                    "auth_methods": {"auth-json": {"active_artifact_id": None}},
                },
            },
        },
    )

    assert load_account("codex", "old")["auth_kind"] == "auth-json"
    new_record = load_account("codex", "new")
    assert "auth_methods" in new_record
