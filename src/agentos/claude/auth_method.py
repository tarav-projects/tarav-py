"""Claude-code `Auth.Method` subclass — the `ambient-browser-login` credential class.

`Auth.Data` for claude spans two home locations: the secret lives in secure
storage (macOS Keychain, falling back to ``<home>/.credentials.json``) as
``{claudeAiOauth: {...}}``, and the identity lives in ``<home>/.claude.json``
under ``oauthAccount``. This class composes both into one self-contained
``AuthData`` payload so ``content_id`` covers the whole credential and
``extract_identity`` works off the payload alone.

Read-side only. ``materialize`` is intentionally unimplemented — this credential
class is observed read-only from the home's perspective.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import ClassVar

from agentos._core.errors import CliError
from agentos._core.process import run_process
from agentos.agent.account_status import AccountIdentity
from agentos.agent.auth_method import AuthData, AuthMethod
from agentos.claude.account_registry import (
    DEFAULT_CLAUDE_KEYCHAIN_TIMEOUT_SEC,
    claude_keychain_service_names,
)


def _read_oauth_account(home: Path) -> dict[str, object] | None:
    path = home.expanduser() / ".claude.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    oauth_account = payload.get("oauthAccount")
    return oauth_account if isinstance(oauth_account, dict) else None


def _read_home_secret(home: Path) -> dict[str, object] | None:
    """Read the secure-storage secret scoped to THIS home only.

    Uses the hash-specific Keychain service (tied to the home path) and the
    in-home ``.credentials.json`` — deliberately NOT the cross-home generic
    ``Claude Code-credentials`` service, so a logged-out home reads as absent
    rather than picking up another home's credential.
    """

    normalized = home.expanduser().resolve()
    if sys.platform == "darwin":
        service_name = claude_keychain_service_names(normalized)[0]  # hash-specific only
        result = run_process(
            (
                "security",
                "find-generic-password",
                "-a",
                os.environ.get("USER", ""),
                "-s",
                service_name,
                "-w",
            ),
            mode="capture",
            timeout_sec=DEFAULT_CLAUDE_KEYCHAIN_TIMEOUT_SEC,
        )
        if result.exit_code == 0 and (result.stdout or "").strip():
            try:
                payload = json.loads(result.stdout)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                return payload
    credentials_path = normalized / ".credentials.json"
    if credentials_path.is_file():
        try:
            payload = json.loads(credentials_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CliError(f"invalid claude-code credentials file: {credentials_path}") from exc
        if isinstance(payload, dict):
            return payload
    return None


class ClaudeAuthMethod(AuthMethod):
    name: ClassVar[str] = "ambient-browser-login"
    provider: ClassVar[str] = "claude-code"
    materializable: ClassVar[bool] = True

    def read_auth_data(self, home: Path) -> AuthData | None:
        oauth_account = _read_oauth_account(home)
        if oauth_account is None:
            return None
        secret = _read_home_secret(home)
        if not isinstance(secret, dict) or "claudeAiOauth" not in secret:
            return None
        payload: dict[str, object] = dict(secret)
        payload["oauthAccount"] = oauth_account
        return AuthData(payload=payload)

    def extract_identity(self, auth_data: AuthData) -> AccountIdentity | None:
        oauth_account = auth_data.payload.get("oauthAccount")
        if not isinstance(oauth_account, dict):
            return None
        account_uuid = _str(oauth_account.get("accountUuid"))
        if account_uuid is None:
            return None
        return AccountIdentity(
            provider_account_id=account_uuid,
            email=_str(oauth_account.get("emailAddress")),
            label=_str(oauth_account.get("displayName")),
            raw=oauth_account,
        )

    def materialize(self, auth_data: AuthData, home: Path) -> None:
        raise NotImplementedError(
            "ClaudeAuthMethod.materialize is out of scope — account management is read-only here"
        )


def _str(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


__all__ = ["ClaudeAuthMethod"]
