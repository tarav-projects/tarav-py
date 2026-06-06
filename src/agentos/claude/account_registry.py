from __future__ import annotations

from pathlib import Path

from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos.agent.account_registry import load_account, record_account_event, upsert_account

CLAUDE_PROVIDER = "claude-code"
CLAUDE_AUTH_KIND = "ambient-browser-login"


def register_claude_account(
    *,
    account: str,
    email: str | None,
    label: str | None = None,
    argv: list[str] | tuple[str, ...] = (),
) -> dict[str, object]:
    normalized_account = validate_string_for_path(account, field_name="account")
    normalized_email = _string_or_none(email)
    if normalized_email is None:
        raise CliError("agent accounts register --provider claude-code requires --email")
    account_record = upsert_account(
        CLAUDE_PROVIDER,
        normalized_account,
        {
            "auth_kinds": [CLAUDE_AUTH_KIND],
            "active_artifact_id": None,
            "email": normalized_email,
            "label": _string_or_none(label),
        },
    )
    record_account_event(
        event_type="agent.accounts.register",
        command="agent accounts register",
        argv=argv,
        status="ok",
        payload={
            "provider": CLAUDE_PROVIDER,
            "account": normalized_account,
            "email": normalized_email,
            "auth_kind": CLAUDE_AUTH_KIND,
        },
    )
    return {
        "status": "ok",
        "command": "agent accounts register",
        "provider": CLAUDE_PROVIDER,
        "account": normalized_account,
        "account_record": account_record,
    }


def link_claude_account_to_home(
    *,
    account: str,
    home: Path,
    force: bool = False,
    argv: list[str] | tuple[str, ...] = (),
) -> dict[str, object]:
    normalized_account = validate_string_for_path(account, field_name="account")
    account_record = load_account(CLAUDE_PROVIDER, normalized_account)
    auth_kinds = account_record.get("auth_kinds")
    if not isinstance(auth_kinds, list) or CLAUDE_AUTH_KIND not in auth_kinds:
        raise CliError(f"agent accounts link is not supported for provider {CLAUDE_PROVIDER} account {normalized_account}")
    normalized_home = home.expanduser().resolve()
    record_account_event(
        event_type="agent.accounts.link",
        command="agent accounts link",
        argv=argv,
        status="ok",
        payload={
            "provider": CLAUDE_PROVIDER,
            "account": normalized_account,
            "home": str(normalized_home),
            "kind": "claimed",
            "force": force,
        },
    )
    return {
        "status": "ok",
        "command": "agent accounts link",
        "provider": CLAUDE_PROVIDER,
        "account": normalized_account,
        "home": str(normalized_home),
        "kind": "claimed",
        "force": force,
    }


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


__all__ = ["link_claude_account_to_home", "register_claude_account"]
