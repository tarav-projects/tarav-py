from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.agent.account_status import AccountIdentity
from agentos.agent.auth_method import AuthData
from agentos.agent.auth_registry import (
    active_artifact_id,
    append_capture,
    load_active,
    method_class,
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
