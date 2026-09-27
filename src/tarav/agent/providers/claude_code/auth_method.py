# $kw: ^agentos-provider-claude-code-auth-method --from Account.Management --from Provider.Instance --from Agent.Navigable.Codebase --note [DF] provider-specific behavior lives beneath the agent provider namespace --note [DC] non-secret home identity can bind provider observations without reading secure credential storage --supp ^c20260811-62u ^c20260813-26u
"""Claude-code `Auth.Method` subclass — the `ambient-browser-login` credential class.

`Auth.Data` for claude spans two home locations: the secret lives in secure
storage (macOS Keychain, falling back to ``<home>/.credentials.json``) as
``{claudeAiOauth: {...}}``, and the identity lives in ``<home>/.claude.json``
under ``oauthAccount``. This class composes both into one self-contained
``AuthData`` payload so ``content_id`` covers the whole credential and
``extract_identity`` works off the payload alone.

``materialize`` writes both halves back — the secret to secure storage and
``oauthAccount`` to ``.claude.json`` — so a materialized home reads back the same
``content_id``. The class is ``materializable``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import ClassVar

from tarav.l0._core.errors import CliError
from tarav.l0._core.process import run_process
from tarav.agent.account_status import AccountIdentity
from tarav.agent.auth_method import AuthData, AuthMethod
from tarav.agent.providers.claude_code.keychain import (
    DEFAULT_CLAUDE_KEYCHAIN_TIMEOUT_SEC,
    claude_keychain_service_names,
    write_claude_secure_storage,
)


def _write_oauth_account(home: Path, oauth_account: dict[str, object]) -> None:
    """Set oauthAccount in <home>/.claude.json, preserving the file's other keys."""
    path = home / ".claude.json"
    cfg: dict[str, object] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                cfg = loaded
        except (OSError, ValueError):
            cfg = {}
    cfg["oauthAccount"] = oauth_account
    tmp = path.with_name(path.name + ".tarav-tmp")
    tmp.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


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
        service_name = claude_keychain_service_names(normalized)[0]
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
            raise CliError(
                f"invalid claude-code credentials file: {credentials_path}"
            ) from exc
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
        return _identity_from_oauth_account(oauth_account)

    def materialize(self, auth_data: AuthData, home: Path) -> None:

        home = home.expanduser()
        home.mkdir(parents=True, exist_ok=True)
        oauth_account = auth_data.payload.get("oauthAccount")
        secret = {k: v for k, v in auth_data.payload.items() if k != "oauthAccount"}
        write_claude_secure_storage(home=home, payload=secret)
        if isinstance(oauth_account, dict):
            _write_oauth_account(home, oauth_account)

    def ref_id(self, auth_data: AuthData) -> str:
        return auth_data.content_id()

    def rotation_rank(self, auth_data: AuthData, captured_at: float) -> float | None:

        oauth = auth_data.payload.get("claudeAiOauth")
        expires_at = oauth.get("expiresAt") if isinstance(oauth, dict) else None
        return float(expires_at) if isinstance(expires_at, int | float) else None


def _str(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def read_claude_home_identity(home: Path) -> AccountIdentity | None:
    oauth_account = _read_oauth_account(home)
    if oauth_account is None:
        return None
    return _identity_from_oauth_account(oauth_account)


def _identity_from_oauth_account(
    oauth_account: dict[str, object],
) -> AccountIdentity | None:
    account_uuid = _str(oauth_account.get("accountUuid"))
    if account_uuid is None:
        return None
    return AccountIdentity(
        provider_account_id=account_uuid,
        email=_str(oauth_account.get("emailAddress")),
        label=_str(oauth_account.get("displayName")),
        raw=oauth_account,
    )


__all__ = ["ClaudeAuthMethod", "read_claude_home_identity"]
