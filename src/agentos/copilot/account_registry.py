from __future__ import annotations

from pathlib import Path

from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos.agent.account_registry import (
    load_account,
    record_account_event,
    upsert_account,
)


COPILOT_PROVIDER = "copilot-cli"
COPILOT_AUTH_KIND = "github-cli-token"


def register_copilot_account(
    *,
    account: str,
    account_id: str | None,
    label: str | None = None,
    argv: list[str] | tuple[str, ...] = (),
) -> dict[str, object]:
    normalized_account = validate_string_for_path(account, field_name="account")
    normalized_account_id = _string_or_none(account_id)
    if normalized_account_id is None:
        raise CliError(
            "agent accounts register --provider copilot-cli requires --account-id"
        )
    account_record = upsert_account(
        COPILOT_PROVIDER,
        normalized_account,
        {
            "auth_kind": COPILOT_AUTH_KIND,
            "active_artifact_id": None,
            "account_id": normalized_account_id,
            "label": _string_or_none(label),
        },
    )
    record_account_event(
        event_type="agent.accounts.register",
        command="agent accounts register",
        argv=argv,
        status="ok",
        payload={
            "provider": COPILOT_PROVIDER,
            "account": normalized_account,
            "account_id": normalized_account_id,
            "auth_kind": COPILOT_AUTH_KIND,
        },
    )
    return {
        "status": "ok",
        "command": "agent accounts register",
        "provider": COPILOT_PROVIDER,
        "account": normalized_account,
        "account_record": account_record,
    }


def link_copilot_account_to_home(
    *,
    account: str,
    home: Path,
    force: bool = False,
    argv: list[str] | tuple[str, ...] = (),
) -> dict[str, object]:
    normalized_account = validate_string_for_path(account, field_name="account")
    account_record = load_account(COPILOT_PROVIDER, normalized_account)
    if account_record.get("auth_kind") != COPILOT_AUTH_KIND:
        raise CliError(
            "agent accounts link is not supported for provider "
            f"{COPILOT_PROVIDER} account {normalized_account}"
        )
    normalized_home = home.expanduser().resolve()
    record_account_event(
        event_type="agent.accounts.link",
        command="agent accounts link",
        argv=argv,
        status="ok",
        payload={
            "provider": COPILOT_PROVIDER,
            "account": normalized_account,
            "home": str(normalized_home),
            "kind": "claimed",
            "force": force,
        },
    )
    return {
        "status": "ok",
        "command": "agent accounts link",
        "provider": COPILOT_PROVIDER,
        "account": normalized_account,
        "home": str(normalized_home),
        "kind": "claimed",
        "force": force,
    }


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


__all__ = ["link_copilot_account_to_home", "register_copilot_account"]
