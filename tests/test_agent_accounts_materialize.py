from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

from agentos.agent.auth_method import AuthData
from agentos.agent.commands.accounts import _cmd_agent_accounts_materialize
from agentos.testing import AgentosTestEnvironment


@pytest.fixture(autouse=True)
def _no_keychain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")  # force .credentials.json path


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    AgentosTestEnvironment.create(tmp_path).apply_environment(monkeypatch.setenv)
    from agentos._core.project import agentos_home_dir

    prov = agentos_home_dir() / "accounts" / "claude-code"
    prov.mkdir(parents=True, exist_ok=True)
    (prov / "accounts.json").write_text(json.dumps({
        "provider": "claude-code",
        "accounts": {"om": {"identity": {"account_uuid": "u-om"},
                            "auth_methods": {"browser": {"class": "ambient-browser-login"}}}},
    }))


def _args(**kw: object) -> argparse.Namespace:
    base = dict(provider="claude-code", account="om/browser", home=None,
               check=False, json=False, _agentos_argv=[])
    base.update(kw)
    return argparse.Namespace(**base)


def _active_artifact() -> AuthData:
    return AuthData(payload={
        "claudeAiOauth": {"accessToken": "NEW", "refreshToken": "r"},
        "oauthAccount": {"accountUuid": "u-om", "emailAddress": "om@x.com", "displayName": "Omar"},
    })


def _home_with(home: Path, *, token: str, uuid: str) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / ".claude.json").write_text(json.dumps({"oauthAccount": {"accountUuid": uuid, "emailAddress": "om@x.com", "displayName": "Omar"}}))
    (home / ".credentials.json").write_text(json.dumps({"claudeAiOauth": {"accessToken": token}}))


def test_materialize_writes_active_and_aligns(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    from agentos.agent import auth_registry as R
    from agentos.claude.auth_method import ClaudeAuthMethod

    active = _active_artifact()
    active_id = R.store_artifact("claude-code", active)
    R.set_active("claude-code", "om", "browser", active_id)

    home = tmp_path / "drifted"
    _home_with(home, token="OLD", uuid="u-om")  # drifted: holds an old token

    assert _cmd_agent_accounts_materialize(_args(home=str(home))) == 0

    back = ClaudeAuthMethod().read_auth_data(home)
    assert back is not None and back.content_id() == active_id  # now aligned


def test_materialize_captures_first(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    from agentos.agent import auth_registry as R
    from agentos.claude.auth_method import ClaudeAuthMethod

    active_id = R.store_artifact("claude-code", _active_artifact())
    R.set_active("claude-code", "om", "browser", active_id)

    home = tmp_path / "drifted"
    _home_with(home, token="OLD", uuid="u-om")
    old_id = ClaudeAuthMethod().read_auth_data(home).content_id()

    _cmd_agent_accounts_materialize(_args(home=str(home)))

    # the home's prior (unregistered) snapshot was captured before being overwritten
    caps = R.captures_path("claude-code").read_text()
    assert old_id in caps
    assert old_id != active_id


def test_materialize_check_is_read_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    from agentos.agent import auth_registry as R
    from agentos.claude.auth_method import ClaudeAuthMethod

    active_id = R.store_artifact("claude-code", _active_artifact())
    R.set_active("claude-code", "om", "browser", active_id)

    home = tmp_path / "drifted"
    _home_with(home, token="OLD", uuid="u-om")
    before = ClaudeAuthMethod().read_auth_data(home).content_id()

    assert _cmd_agent_accounts_materialize(_args(home=str(home), check=True)) == 0

    after = ClaudeAuthMethod().read_auth_data(home).content_id()
    assert after == before  # home unchanged under --check


def test_materialize_errors_without_active(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    from agentos._core.errors import CliError

    home = tmp_path / "h"
    _home_with(home, token="X", uuid="u-om")
    with pytest.raises(CliError):
        _cmd_agent_accounts_materialize(_args(home=str(home)))  # no active set
