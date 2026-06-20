from __future__ import annotations

from pathlib import Path

from agentos._core.clock import utc_now_iso
from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos.agent.account_registry import (
    load_account,
    record_account_event,
    upsert_account,
)


COPILOT_PROVIDER = "copilot-cli"
COPILOT_AUTH_KIND = "gh-auth-token"


def record_copilot_account_verified(
    *,
    account: str,
    login: str,
    name: str | None = None,
    source: str = "account.status",
    verified_at: str | None = None,
) -> dict[str, object]:
    """Stamp a metadata-only freshness trail onto a copilot account record.

    Copilot auth is ambient via ``gh`` and is never materialized, so there is
    no artifact to promote. A successful live status leaves only useful,
    non-secret metadata on the account record: the observed ``login`` plus
    ``last_verified_at`` / ``last_verified_source``. No token, no artifact, no
    ``verifications.jsonl`` entry (that ledger is artifact-keyed).
    """
    normalized_account = validate_string_for_path(account, field_name="account")
    normalized_login = _string_or_none(login)
    if normalized_login is None:
        raise CliError("copilot account verification requires a login identity")
    updates: dict[str, object] = {
        "auth_kind": COPILOT_AUTH_KIND,
        "account_id": normalized_login,
        "last_verified_at": verified_at or utc_now_iso(),
        "last_verified_source": source,
    }
    display_name = _string_or_none(name)
    if display_name is not None:
        updates["display_name"] = display_name
    return upsert_account(COPILOT_PROVIDER, normalized_account, updates)


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


def materialize_copilot_account_to_home(
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
            "agent accounts materialize is not supported for provider "
            f"{COPILOT_PROVIDER} account {normalized_account}"
        )
    normalized_home = home.expanduser().resolve()
    record_account_event(
        event_type="account.auth.materialized",
        command="agent accounts materialize",
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
        "command": "agent accounts materialize",
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


__all__ = [
    "materialize_copilot_account_to_home",
    "record_copilot_account_verified",
    "register_copilot_account",
]
