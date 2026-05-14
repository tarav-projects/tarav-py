from __future__ import annotations

from pathlib import Path

from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos.agent.account_registry import write_account_manifest

CLAUDE_PROVIDER = "claude-code"
CLAUDE_AUTH_KIND = "ambient-browser-login"


def register_claude_account(
    *,
    account: str,
    home: Path,
    email: str | None,
    label: str | None = None,
) -> dict[str, object]:
    normalized_account = validate_string_for_path(account, field_name="account")
    normalized_email = _string_or_none(email)
    if normalized_email is None:
        raise CliError("agent accounts register --provider claude-code requires --email")
    manifest = write_account_manifest(
        provider=CLAUDE_PROVIDER,
        account=normalized_account,
        auth_kind=CLAUDE_AUTH_KIND,
        capabilities={
            "register": True,
            "link": False,
            "status": True,
            "monitor": True,
        },
        email=normalized_email,
        label=label,
        home=home,
    )
    return {
        "status": "ok",
        "command": "agent accounts register",
        "provider": CLAUDE_PROVIDER,
        "account": normalized_account,
        "manifest": manifest,
    }


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


__all__ = ["register_claude_account"]
