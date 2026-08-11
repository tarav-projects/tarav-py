"""Codex `Auth.Method` subclass — the `auth-json` credential class.

Identity is extracted from the **access_token** `chatgpt_account_id` claim, which
is the authoritative account anchor. The id_token must not be trusted for this:
it has been observed to carry a stale id (see the session that drove the
`Account.Management` rebuild). `auth-json` is materializable.
"""

# $kw: ^agentos-provider-codex-auth-method --from Agent.Navigable.Codebase --note [DF] provider-specific behavior lives beneath the agent provider namespace --supp ^c20260811-62u
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import ClassVar

from agentos.agent.account_status import AccountIdentity
from agentos.agent.auth_method import AuthData, AuthMethod

CODEX_AUTH_FILENAME = "auth.json"
_OPENAI_AUTH_CLAIM = "https://api.openai.com/auth"
_OPENAI_PROFILE_CLAIM = "https://api.openai.com/profile"


class CodexAuthMethod(AuthMethod):
    name: ClassVar[str] = "auth-json"
    provider: ClassVar[str] = "codex"
    materializable: ClassVar[bool] = True

    def read_auth_data(self, home: Path) -> AuthData | None:
        path = home / CODEX_AUTH_FILENAME
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        return AuthData(payload=payload)

    def extract_identity(self, auth_data: AuthData) -> AccountIdentity | None:
        tokens = auth_data.payload.get("tokens")
        if not isinstance(tokens, dict):
            return None
        claims = _access_token_claims(tokens)
        auth_claim = claims.get(_OPENAI_AUTH_CLAIM)
        account_id = None
        if isinstance(auth_claim, dict):
            account_id = _str(auth_claim.get("chatgpt_account_id"))
        account_id = account_id or _str(tokens.get("account_id"))
        if account_id is None:
            return None
        return AccountIdentity(provider_account_id=account_id, email=_identity_email(claims))

    def materialize(self, auth_data: AuthData, home: Path) -> None:
        home.mkdir(parents=True, exist_ok=True)
        (home / CODEX_AUTH_FILENAME).write_text(
            json.dumps(dict(auth_data.payload), indent=2) + "\n", encoding="utf-8"
        )

    def ref_id(self, auth_data: AuthData) -> str:
        return auth_data.content_id()

    def rotation_rank(self, auth_data: AuthData, captured_at: float) -> float | None:
        # Head-of-line by the access-token expiry — monotonic across refreshes.
        tokens = auth_data.payload.get("tokens")
        if not isinstance(tokens, dict):
            return None
        exp = _access_token_claims(tokens).get("exp")
        return float(exp) if isinstance(exp, int | float) else None


def _access_token_claims(tokens: dict[str, object]) -> dict[str, object]:
    token = _str(tokens.get("access_token"))
    return _decode_jwt_payload(token) if token else {}


def _identity_email(claims: dict[str, object]) -> str | None:
    email = _str(claims.get("email"))
    if email:
        return email
    profile = claims.get(_OPENAI_PROFILE_CLAIM)
    return _str(profile.get("email")) if isinstance(profile, dict) else None


def _decode_jwt_payload(token: str) -> dict[str, object]:
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode((payload + padding).encode("ascii"))
        parsed = json.loads(decoded.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _str(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


__all__ = ["CodexAuthMethod"]
