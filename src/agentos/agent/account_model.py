"""The nested `Account.Model` read/write layer.

Storage shape (new): ``accounts/<provider>/`` holds

- ``accounts.json`` — ``{provider, accounts: {<name>: account_record}}`` where each
  account_record is a provider-neutral identity header plus an ``auth_methods`` map:
  ``{<method>: {active_artifact_id, artifacts: [<artifact_id>...]}}``
- ``artifacts.jsonl`` — append-only history index (no secrets)
- ``artifacts/<artifact_id>.json`` — the `Auth.Data.Artifact` payload (secrets live here only)

This layer is provider-agnostic. It composes the existing registry storage
primitives; it does not route through the old ``upsert_account`` writer.
See the `Account.Management` appendix in `agentos-pkg`.
"""

from __future__ import annotations

import json
from pathlib import Path

from agentos._core.clock import utc_now_iso
from agentos._core.errors import CliError
from agentos.agent.account_registry import (
    append_artifact,
    artifacts_dir,
    load_accounts,
    write_accounts,
)
from agentos.agent.auth_method import AuthData


def artifact_payload_path(provider: str, artifact_id: str) -> Path:
    return artifacts_dir(provider) / f"{artifact_id}.json"


def upsert_account_identity(
    provider: str,
    account: str,
    *,
    provider_account_id: str | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    """Create or update an account's identity header in the nested shape."""

    container = load_accounts(provider)
    accounts = container["accounts"]
    if not isinstance(accounts, dict):
        accounts = {}
        container["accounts"] = accounts
    record = accounts.get(account)
    if not isinstance(record, dict):
        record = {"provider": provider, "account": account, "created_at": utc_now_iso()}
    record["provider"] = provider
    record["account"] = account
    record["updated_at"] = utc_now_iso()
    if provider_account_id is not None:
        record["provider_account_id"] = provider_account_id
    if metadata:
        existing_meta = record.get("metadata")
        merged = dict(existing_meta) if isinstance(existing_meta, dict) else {}
        merged.update(metadata)
        record["metadata"] = merged
    record.setdefault("auth_methods", {})
    accounts[account] = record
    write_accounts(provider, container)
    return record


def store_artifact(
    provider: str,
    account: str,
    auth_method: str,
    auth_data: AuthData,
    *,
    history_extra: dict[str, object] | None = None,
) -> str:
    """Store an `Auth.Data.Artifact` (content-addressed), append history, return its id.

    Idempotent: an identical payload dedups to the same artifact id and is not
    re-appended to the method's history. ``history_extra`` adds non-secret fields
    to the history index entry (e.g. the extracted identity of an orphan capture).
    """

    artifact_id = auth_data.content_id()
    payload_path = artifact_payload_path(provider, artifact_id)
    if not payload_path.exists():
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        payload_path.write_text(
            json.dumps(dict(auth_data.payload), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    entry: dict[str, object] = {
        "artifact_id": artifact_id,
        "account": account,
        "auth_method": auth_method,
        "captured_at": utc_now_iso(),
    }
    if history_extra:
        entry.update(history_extra)
    append_artifact(provider, entry)
    _append_artifact_to_method(provider, account, auth_method, artifact_id)
    return artifact_id


def find_account_by_provider_account_id(provider: str, provider_account_id: str) -> str | None:
    """Return the account whose `Account.Identity` matches, or None (orphan)."""

    container = load_accounts(provider)
    accounts = container.get("accounts")
    if not isinstance(accounts, dict):
        return None
    for name, record in accounts.items():
        if not isinstance(name, str) or not isinstance(record, dict):
            continue
        if record.get("provider_account_id") == provider_account_id:
            return name
    return None


def read_artifact(provider: str, artifact_id: str) -> AuthData | None:
    payload_path = artifact_payload_path(provider, artifact_id)
    if not payload_path.exists():
        return None
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CliError(f"artifact payload must be a JSON object: {payload_path}")
    return AuthData(payload=payload)


def set_active_artifact(provider: str, account: str, auth_method: str, artifact_id: str) -> dict[str, object]:
    """Set the per-method `Active.Auth.Artifact` pointer. Registry-only; no home write."""

    record, method = _require_method(provider, account, auth_method, create=True)
    artifacts = method.get("artifacts")
    if not isinstance(artifacts, list) or artifact_id not in artifacts:
        raise CliError(
            f"cannot activate unknown artifact {artifact_id} for {provider}.{account}.{auth_method}"
        )
    method["active_artifact_id"] = artifact_id
    _write_record(provider, account, record)
    return record


def active_artifact_id(provider: str, account: str, auth_method: str) -> str | None:
    method = _method_or_none(provider, account, auth_method)
    if method is None:
        return None
    value = method.get("active_artifact_id")
    return value if isinstance(value, str) else None


def method_artifact_ids(provider: str, account: str, auth_method: str) -> list[str]:
    method = _method_or_none(provider, account, auth_method)
    if method is None:
        return []
    artifacts = method.get("artifacts")
    return [a for a in artifacts if isinstance(a, str)] if isinstance(artifacts, list) else []


def _append_artifact_to_method(provider: str, account: str, auth_method: str, artifact_id: str) -> None:
    record, method = _require_method(provider, account, auth_method, create=True)
    artifacts = method.setdefault("artifacts", [])
    if not isinstance(artifacts, list):
        raise CliError(f"auth method artifacts must be a list: {provider}.{account}.{auth_method}")
    if artifact_id not in artifacts:
        artifacts.append(artifact_id)
    method.setdefault("active_artifact_id", None)
    _write_record(provider, account, record)


def _require_method(
    provider: str, account: str, auth_method: str, *, create: bool
) -> tuple[dict[str, object], dict[str, object]]:
    container = load_accounts(provider)
    accounts = container["accounts"]
    if not isinstance(accounts, dict) or not isinstance(accounts.get(account), dict):
        raise CliError(f"account is not registered: {provider}.{account}")
    record = accounts[account]
    methods = record.get("auth_methods")
    if not isinstance(methods, dict):
        methods = {}
        record["auth_methods"] = methods
    method = methods.get(auth_method)
    if not isinstance(method, dict):
        if not create:
            raise CliError(f"auth method not present: {provider}.{account}.{auth_method}")
        method = {"active_artifact_id": None, "artifacts": []}
        methods[auth_method] = method
    return record, method


def _method_or_none(provider: str, account: str, auth_method: str) -> dict[str, object] | None:
    container = load_accounts(provider)
    accounts = container.get("accounts")
    if not isinstance(accounts, dict):
        return None
    record = accounts.get(account)
    if not isinstance(record, dict):
        return None
    methods = record.get("auth_methods")
    if not isinstance(methods, dict):
        return None
    method = methods.get(auth_method)
    return method if isinstance(method, dict) else None


def _write_record(provider: str, account: str, record: dict[str, object]) -> None:
    container = load_accounts(provider)
    accounts = container["accounts"]
    if not isinstance(accounts, dict):
        accounts = {}
        container["accounts"] = accounts
    accounts[account] = record
    write_accounts(provider, container)


__all__ = [
    "active_artifact_id",
    "artifact_payload_path",
    "find_account_by_provider_account_id",
    "method_artifact_ids",
    "read_artifact",
    "set_active_artifact",
    "store_artifact",
    "upsert_account_identity",
]
