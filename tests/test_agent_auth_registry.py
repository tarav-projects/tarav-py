from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.agent.account_status import AccountIdentity
from agentos.agent.auth_method import AuthData
from agentos.agent.auth_registry import (
    UNKNOWN_ACCOUNT,
    active_artifact_id,
    append_capture,
    capture_target,
    load_active,
    method_class,
    orphan_captures,
    resolve_account_by_identity,
    set_active,
    store_artifact,
)
from agentos.testing import AgentosTestEnvironment


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    AgentosTestEnvironment.create(tmp_path).apply_environment(monkeypatch.setenv)


def _write_settings(provider_root: Path) -> None:
    provider_root.mkdir(parents=True, exist_ok=True)
    (provider_root / "accounts.json").write_text(
        json.dumps(
            {
                "provider": "claude-code",
                "accounts": {
                    "om": {
                        "identity": {
                            "account_uuid": "973c403b-615a-47da-bc34-32ddc13a2e65",
                            "email": "ocabrerabarrera@gmail.com",
                        },
                        "auth_methods": {"browser": {"class": "ambient-browser-login"}},
                    }
                },
            }
        )
    )


def test_resolve_account_by_identity_matches_claude_account_uuid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos._core.project import agentos_home_dir

    _write_settings(agentos_home_dir() / "accounts" / "claude-code")

    identity = AccountIdentity(provider_account_id="973c403b-615a-47da-bc34-32ddc13a2e65")
    assert resolve_account_by_identity("claude-code", identity) == "om"
    assert method_class("claude-code", "om", "browser") == "ambient-browser-login"

    unknown = AccountIdentity(provider_account_id="not-a-known-uuid")
    assert resolve_account_by_identity("claude-code", unknown) is None


def test_capture_target_known_identity_routes_to_account_method(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos._core.project import agentos_home_dir

    _write_settings(agentos_home_dir() / "accounts" / "claude-code")

    known = AccountIdentity(provider_account_id="973c403b-615a-47da-bc34-32ddc13a2e65")
    assert capture_target("claude-code", known, "ambient-browser-login") == ("om", "browser")


def test_capture_target_orphan_routes_to_unknown_bucket(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)

    unmatched = AccountIdentity(provider_account_id="not-a-known-uuid")
    assert capture_target("claude-code", unmatched, "ambient-browser-login") == (
        UNKNOWN_ACCOUNT,
        "ambient-browser-login",
    )
    # a None identity is still an orphan, never a rejection
    assert capture_target("claude-code", None, "auth-json") == (UNKNOWN_ACCOUNT, "auth-json")


def test_active_pointer_round_trip_keyed_by_account_method(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)

    auth = AuthData(payload={"claudeAiOauth": {"accessToken": "x"}, "oauthAccount": {"accountUuid": "u"}})
    artifact_id = store_artifact("claude-code", auth)
    set_active("claude-code", "om", "browser", artifact_id)

    assert active_artifact_id("claude-code", "om", "browser") == artifact_id
    assert load_active("claude-code") == {"om/browser": artifact_id}
    # live-read content_id of an identical payload equals the stored artifact id
    assert auth.content_id() == artifact_id


def test_orphan_captures_returns_only_unknown_bucket_records(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)

    known_ref = AccountIdentity(provider_account_id="u", email="e@example.com")
    orphan_ref = AccountIdentity(provider_account_id="stray", email="s@example.com")
    append_capture(
        "claude-code", account="om", method="browser",
        auth_class="ambient-browser-login", auth_ref=known_ref, artifact_id="known",
    )
    append_capture(
        "claude-code", account=UNKNOWN_ACCOUNT, method="ambient-browser-login",
        auth_class="ambient-browser-login", auth_ref=orphan_ref, artifact_id="orphan",
    )

    orphans = orphan_captures("claude-code")
    assert len(orphans) == 1
    assert orphans[0]["artifact_id"] == "orphan"
    # the extracted identity is preserved for later adoption
    assert orphans[0]["auth_ref"]["provider_account_id"] == "stray"


def test_orphan_captures_empty_when_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    assert orphan_captures("claude-code") == []


def test_unknown_bucket_is_not_a_runnable_account(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos.agent.auth_registry import account_exists

    assert account_exists("claude-code", UNKNOWN_ACCOUNT) is False


def test_set_active_rejects_unknown_bucket(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos._core.errors import CliError

    with pytest.raises(CliError):
        set_active("claude-code", UNKNOWN_ACCOUNT, "ambient-browser-login", "abc")


def test_append_capture_records_every_auth_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos.agent.auth_registry import captures_path

    ref = AccountIdentity(provider_account_id="u", email="e@example.com")
    append_capture(
        "claude-code", account="om", method="browser",
        auth_class="ambient-browser-login", auth_ref=ref, artifact_id="abc",
    )
    lines = captures_path("claude-code").read_text().strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["account"] == "om" and rec["artifact_id"] == "abc"
    assert rec["auth_ref"]["provider_account_id"] == "u"
