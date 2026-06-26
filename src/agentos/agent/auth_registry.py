"""Readers (and minimal writers) for the redesigned `Auth.Registry`.

Settings/state are physically split under ``~/.agentos/accounts/<provider>/``:

- ``accounts.json`` — settings: ``{provider, accounts: {<account-id>: {identity, auth_methods: {<method>: {class}}}}}``.
- ``registry/`` — state: ``active.json`` (``{"<account-id>/<method>": <artifact_id>}``),
  ``captures.jsonl`` (one record per capture), ``artifacts/<sha256>`` (content-addressed payloads, secrets here only).

The pair ``{captures.jsonl record + artifact}`` reconstructs a full `Auth.Data`.
This module is provider-agnostic; provider specifics live in the `Auth.Method`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from agentos._core.clock import utc_now_iso
from agentos._core.errors import CliError
from agentos.agent.account_paths import account_provider_root
from agentos.agent.account_status import AccountIdentity
from agentos.agent.auth_method import AuthData


# The reserved per-provider `Provider.Account` where capture files an
# identifiable orphan it cannot bind to a declared account. Leading ``_`` cannot
# collide with a user account-id. It is a registry-state bucket only: never
# declared in settings, never runnable, never activated.
UNKNOWN_ACCOUNT = "_unknown"


# --- paths ---

def settings_path(provider: str) -> Path:
    return account_provider_root(provider) / "accounts.json"


def registry_root(provider: str) -> Path:
    return account_provider_root(provider) / "registry"


def active_path(provider: str) -> Path:
    return registry_root(provider) / "active.json"


def captures_path(provider: str) -> Path:
    return registry_root(provider) / "captures.jsonl"


def artifact_path(provider: str, artifact_id: str) -> Path:
    return registry_root(provider) / "artifacts" / artifact_id


# --- settings (read) ---

def load_settings(provider: str) -> dict[str, object]:
    path = settings_path(provider)
    if not path.is_file():
        return {"provider": provider, "accounts": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {"provider": provider, "accounts": {}}
    return payload


def _accounts(provider: str) -> dict[str, dict[str, object]]:
    accounts = load_settings(provider).get("accounts")
    if not isinstance(accounts, dict):
        return {}
    return {k: v for k, v in accounts.items() if isinstance(k, str) and isinstance(v, dict)}


def resolve_account_by_identity(provider: str, identity: AccountIdentity) -> str | None:
    """Return the account-id whose settings identity matches, or None (orphan)."""

    target = identity.provider_account_id
    if target is None:
        return None
    for account_id, record in _accounts(provider).items():
        ident = record.get("identity")
        if not isinstance(ident, dict):
            continue
        # provider-shaped id field: codex `provider_account_id`, claude `account_uuid`
        known = ident.get("provider_account_id") or ident.get("account_uuid")
        if known == target:
            return account_id
    return None


def capture_target(
    provider: str, identity: AccountIdentity | None, auth_class: str
) -> tuple[str, str]:
    """Resolve where a captured `Auth.Data` is filed — never rejects.

    Known identity → ``(account_id, method)`` for the declared account. An
    identifiable orphan (``identity`` is None, or extracts but maps to no
    account) → ``(UNKNOWN_ACCOUNT, auth_class)``: the orphan's method axis is the
    auth_class, since no user-given method name exists. Return is never None.
    """

    account = resolve_account_by_identity(provider, identity) if identity is not None else None
    if account is None:
        return (UNKNOWN_ACCOUNT, auth_class)
    return (account, method_for_class(provider, account, auth_class) or auth_class)


def method_class(provider: str, account_id: str, method: str) -> str | None:
    record = _accounts(provider).get(account_id)
    if not isinstance(record, dict):
        return None
    methods = record.get("auth_methods")
    if not isinstance(methods, dict):
        return None
    spec = methods.get(method)
    return spec.get("class") if isinstance(spec, dict) else None


def method_for_class(provider: str, account_id: str, auth_class: str) -> str | None:
    """The method name whose declared class matches — capture routes by class."""

    record = _accounts(provider).get(account_id)
    methods = record.get("auth_methods") if isinstance(record, dict) else None
    if not isinstance(methods, dict):
        return None
    for name, spec in methods.items():
        if isinstance(spec, dict) and spec.get("class") == auth_class:
            return name
    return None


def account_exists(provider: str, account_id: str) -> bool:
    return account_id in _accounts(provider)


def expected_identity(provider: str, account_id: str) -> AccountIdentity | None:
    """The account's declared `Account.Identity` from settings (provider-shaped)."""

    record = _accounts(provider).get(account_id)
    ident = record.get("identity") if isinstance(record, dict) else None
    if not isinstance(ident, dict):
        return None
    return AccountIdentity(
        provider_account_id=ident.get("provider_account_id") or ident.get("account_uuid"),
        email=ident.get("email"),
        label=ident.get("label") or ident.get("display_name"),
        raw=ident,
    )


# --- state (read) ---

def load_active(provider: str) -> dict[str, str]:
    path = active_path(provider)
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return {k: v for k, v in payload.items() if isinstance(k, str) and isinstance(v, str)}


def active_artifact_id(provider: str, account_id: str, method: str) -> str | None:
    return load_active(provider).get(f"{account_id}/{method}")


def read_artifact(provider: str, artifact_id: str) -> AuthData | None:
    path = artifact_path(provider, artifact_id)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return AuthData(payload=payload) if isinstance(payload, dict) else None


# --- state (write) — minimal, for capture/activation ---

def store_artifact(provider: str, auth_data: AuthData) -> str:
    """Content-address and persist a payload blob (mode 600); return its id."""

    artifact_id = auth_data.content_id()
    path = artifact_path(provider, artifact_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(
            json.dumps(dict(auth_data.payload), sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        os.chmod(path, 0o600)
    return artifact_id


def append_capture(
    provider: str,
    *,
    account: str,
    method: str,
    auth_class: str,
    auth_ref: AccountIdentity,
    artifact_id: str | None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "ts": utc_now_iso(),
        "account": account,
        "method": method,
        "class": auth_class,
        "auth_ref": auth_ref.summary(),
        "artifact_id": artifact_id,
    }
    path = captures_path(provider)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":")) + "\n")
    return record


def is_captured(provider: str, account: str, method: str, artifact_id: str) -> bool:
    path = captures_path(provider)
    if not path.is_file():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if (r.get("account"), r.get("method"), r.get("artifact_id")) == (account, method, artifact_id):
            return True
    return False


def orphan_captures(provider: str) -> list[dict[str, object]]:
    """Capture records filed under `Unknown.Account` — the place to check for an
    auth-method that could not be bound to a declared account. Each record keeps
    its extracted ``auth_ref`` identity, the basis for later adoption."""

    path = captures_path(provider)
    if not path.is_file():
        return []
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if isinstance(record, dict) and record.get("account") == UNKNOWN_ACCOUNT:
            records.append(record)
    return records


def set_active(provider: str, account_id: str, method: str, artifact_id: str) -> None:
    if account_id == UNKNOWN_ACCOUNT:
        raise CliError(
            f"the {UNKNOWN_ACCOUNT} bucket cannot be activated — adopt the orphan "
            "into a declared account first"
        )
    active = load_active(provider)
    active[f"{account_id}/{method}"] = artifact_id
    path = active_path(provider)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(active, indent=2, sort_keys=True) + "\n", encoding="utf-8")


__all__ = [
    "UNKNOWN_ACCOUNT",
    "capture_target",
    "settings_path",
    "registry_root",
    "active_path",
    "captures_path",
    "artifact_path",
    "load_settings",
    "resolve_account_by_identity",
    "method_class",
    "load_active",
    "active_artifact_id",
    "read_artifact",
    "store_artifact",
    "append_capture",
    "is_captured",
    "orphan_captures",
    "set_active",
]
