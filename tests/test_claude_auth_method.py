from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from agentos.agent.auth_method import AuthData
from agentos.claude.auth_method import ClaudeAuthMethod


@pytest.fixture(autouse=True)
def _no_keychain(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the .credentials.json path — never touch the real macOS Keychain."""
    monkeypatch.setattr(sys, "platform", "linux")


def _make_home(tmp_path: Path, *, with_secret: bool = True, with_identity: bool = True) -> Path:
    home = tmp_path / "claude-home"
    home.mkdir()
    if with_identity:
        (home / ".claude.json").write_text(
            json.dumps(
                {
                    "oauthAccount": {
                        "accountUuid": "973c403b-615a-47da-bc34-32ddc13a2e65",
                        "organizationUuid": "ffa0d738-6a33-450d-a695-1dd2803908e1",
                        "emailAddress": "ocabrerabarrera@gmail.com",
                        "displayName": "Omar",
                    }
                }
            )
        )
    if with_secret:
        (home / ".credentials.json").write_text(
            json.dumps({"claudeAiOauth": {"accessToken": "tok", "refreshToken": "ref", "expiresAt": 1}})
        )
    return home


def test_class_attrs() -> None:
    method = ClaudeAuthMethod()
    assert method.name == "ambient-browser-login"
    assert method.provider == "claude-code"
    assert method.materializable is True


def test_read_auth_data_composes_secret_and_identity(tmp_path: Path) -> None:
    method = ClaudeAuthMethod()
    home = _make_home(tmp_path)
    auth = method.read_auth_data(home)
    assert auth is not None
    # payload is self-contained: both the secret and the identity are present
    assert "claudeAiOauth" in auth.payload
    assert "oauthAccount" in auth.payload
    # content_id is stable across reads
    assert auth.content_id() == method.read_auth_data(home).content_id()


def test_extract_identity_from_oauth_account(tmp_path: Path) -> None:
    method = ClaudeAuthMethod()
    auth = method.read_auth_data(_make_home(tmp_path))
    identity = method.extract_identity(auth)
    assert identity is not None
    assert identity.provider_account_id == "973c403b-615a-47da-bc34-32ddc13a2e65"
    assert identity.email == "ocabrerabarrera@gmail.com"
    assert identity.label == "Omar"


def test_read_auth_data_none_when_secret_absent(tmp_path: Path) -> None:
    method = ClaudeAuthMethod()
    assert method.read_auth_data(_make_home(tmp_path, with_secret=False)) is None


def test_read_auth_data_none_when_identity_absent(tmp_path: Path) -> None:
    method = ClaudeAuthMethod()
    assert method.read_auth_data(_make_home(tmp_path, with_identity=False)) is None


def test_materialize_not_implemented(tmp_path: Path) -> None:
    method = ClaudeAuthMethod()
    with pytest.raises(NotImplementedError):
        method.materialize(AuthData(payload={}), tmp_path / "x")
