# $kw: --from Account.Management
"""Readers (and minimal writers) for the redesigned `Auth.Registry`.

Settings/state are physically split under ``~/.tarav/accounts/<provider>/``:

- ``accounts.json`` — settings: ``{provider, accounts: {<account-id>: {identity, auth_methods: {<method>: {class}}}}}``.
- ``registry/`` — state: ``active.json`` (``{"<account-id>/<method>": <ref_id>}``),
  ``captures.jsonl`` (one record per capture, joining ``ref_id`` to its ``artifact_id``),
  ``artifacts/<sha256>`` (content-addressed payloads, secrets here only).

The activation pointer is the method-defined `Auth.Ref` ``ref_id``; the artifact
blob is the content-addressed secret store joined to it via the capture record.

The pair ``{captures.jsonl record + artifact}`` reconstructs a full `Auth.Data`.
This module is provider-agnostic; provider specifics live in the `Auth.Method`.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

from tarav.l0._core.clock import utc_now_iso
from tarav.l0._core.errors import CliError
from tarav.l1.agent.account_paths import account_provider_root
from tarav.l1.agent.account_status import AccountIdentity
from tarav.l1.agent.auth_method import AuthData






UNKNOWN_ACCOUNT = "_unknown"




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




def load_active(provider: str) -> dict[str, str]:
    path = active_path(provider)
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return {k: v for k, v in payload.items() if isinstance(k, str) and isinstance(v, str)}


def active_ref(provider: str, account_id: str, method: str) -> str | None:
    """The `ref_id` the registry has designated active for ``account/method``."""

    return load_active(provider).get(f"{account_id}/{method}")


def read_artifact(provider: str, artifact_id: str) -> AuthData | None:
    path = artifact_path(provider, artifact_id)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return AuthData(payload=payload) if isinstance(payload, dict) else None




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
    ref_id: str,
    artifact_id: str | None,
) -> dict[str, object]:



    record: dict[str, object] = {
        "ts": utc_now_iso(),
        "account": account,
        "method": method,
        "class": auth_class,
        "auth_ref": auth_ref.summary(),
        "ref_id": ref_id,
        "artifact_id": artifact_id,
    }
    path = captures_path(provider)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":")) + "\n")
    return record


def record_ref_id(record: dict[str, object]) -> str | None:
    """The capture record's `ref_id`, falling back to its `artifact_id`.

    Records written before `Auth.Ref` carry only `artifact_id` (== the content id
    == the ref for artifact-backed methods), so this backfills them at read time —
    no `captures.jsonl` migration needed."""

    ref_id = record.get("ref_id") or record.get("artifact_id")
    return ref_id if isinstance(ref_id, str) else None


def _iter_capture_records(provider: str) -> Iterator[dict[str, object]]:
    """Yield each parsed `captures.jsonl` record (skipping blanks/non-dicts).

    The single place the capture log is read off disk — every capture-record
    reader filters over this, so the file scan lives in exactly one spot."""

    path = captures_path(provider)
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if isinstance(record, dict):
            yield record


def is_captured(provider: str, account: str, method: str, ref_id: str) -> bool:
    for r in _iter_capture_records(provider):
        if (r.get("account"), r.get("method"), record_ref_id(r)) == (account, method, ref_id):
            return True
    return False


def auth_data_for_ref(provider: str, account: str, method: str, ref_id: str) -> AuthData | None:
    """Resolve an `Auth.Ref` pointer back to its `Auth.Data` payload.

    Finds the capture record carrying ``ref_id`` for ``account/method`` and reads
    the artifact it joins to — the single place a pointer becomes a payload, so a
    method whose ``ref_id`` is not the content id still resolves correctly."""

    for record in captures_for(provider, account, method):
        if record_ref_id(record) != ref_id:
            continue
        artifact_id = record.get("artifact_id")
        return read_artifact(provider, artifact_id) if isinstance(artifact_id, str) else None




    return read_artifact(provider, ref_id)


def orphan_captures(provider: str) -> list[dict[str, object]]:
    """Capture records filed under `Unknown.Account` — the place to check for an
    auth-method that could not be bound to a declared account. Each record keeps
    its extracted ``auth_ref`` identity, the basis for later adoption."""

    return [r for r in _iter_capture_records(provider) if r.get("account") == UNKNOWN_ACCOUNT]


def orphan_groups(provider: str) -> list[dict[str, object]]:
    """Orphan captures (`Unknown.Account`) grouped by identity — the adoption view.

    One group per distinct identity anchor (``auth_ref.provider_account_id``;
    anchorless orphans share the ``None`` group), each carrying the identity, the
    ``auth_class``, and its distinct ``ref_id``s newest-first (with ``artifact_id``
    + ``ts``) plus ``last_seen``. Groups are ordered by ``last_seen`` desc. This is
    the candidate-account view a manual adopter reads — grouping/dedup live here so
    the CLI is a pure formatter."""

    groups: dict[str | None, dict[str, object]] = {}
    for record in orphan_captures(provider):
        ref_id = record_ref_id(record)
        if ref_id is None:
            continue
        auth_ref = record.get("auth_ref")
        identity = auth_ref if isinstance(auth_ref, dict) else {}
        key = identity.get("provider_account_id")
        ts = record.get("ts")
        group = groups.setdefault(key, {
            "identity": identity,
            "auth_class": record.get("class") or record.get("method"),
            "_refs": {},
        })
        refs: dict[str, dict[str, object]] = group["_refs"]  # type: ignore[assignment]
        existing = refs.get(ref_id)
        if existing is None or (isinstance(ts, str) and ts > str(existing.get("ts") or "")):
            refs[ref_id] = {"ref_id": ref_id, "artifact_id": record.get("artifact_id"), "ts": ts}

    result: list[dict[str, object]] = []
    for group in groups.values():
        refs = sorted(group.pop("_refs").values(), key=lambda r: str(r.get("ts") or ""), reverse=True)
        result.append({**group, "refs": refs, "last_seen": refs[0]["ts"] if refs else None})
    result.sort(key=lambda g: str(g.get("last_seen") or ""), reverse=True)
    return result


def captures_for(provider: str, account: str, method: str) -> list[dict[str, object]]:
    """Capture records for one ``account/method``, in capture (file) order.

    The capture pool a rotation ranks over — `_unknown` is reachable only by
    passing it explicitly (callers rotate declared accounts, never the bucket)."""

    return [r for r in _iter_capture_records(provider)
            if r.get("account") == account and r.get("method") == method]


def pool_for(provider: str, account: str, method: str) -> list[dict[str, object]]:
    """The distinct `Auth.Ref`s captured for ``account/method``, recency-ordered.

    One entry per ``ref_id`` (most recent capture ``ts`` kept), newest first — the
    discoverable pool both `list` display and prefix resolution read."""

    latest: dict[str, str] = {}
    for record in captures_for(provider, account, method):
        ref_id = record_ref_id(record)
        ts = record.get("ts")
        if ref_id is None or not isinstance(ts, str):
            continue
        if ref_id not in latest or ts > latest[ref_id]:
            latest[ref_id] = ts
    rows = [{"ref_id": ref_id, "ts": ts} for ref_id, ts in latest.items()]
    rows.sort(key=lambda e: e["ts"], reverse=True)
    return rows


def resolve_ref_prefix(provider: str, account: str, method: str, prefix: str) -> str:
    """Resolve a ``ref_id`` prefix against the ``account/method`` pool.

    Exactly one match → the full ref; >1 → `CliError` naming the collisions; 0 →
    `CliError`. A full ref_id is the trivial unique-prefix case. Scoped to this
    account/method so a short prefix can't collide across accounts."""

    matches = [e["ref_id"] for e in pool_for(provider, account, method)
               if isinstance(e["ref_id"], str) and e["ref_id"].startswith(prefix)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise CliError(f"no captured Auth.Ref matches prefix {prefix!r} for {account}/{method}")
    shown = ", ".join(m[:12] for m in sorted(matches))
    raise CliError(f"ambiguous Auth.Ref prefix {prefix!r} for {account}/{method} — matches: {shown}")


def set_active(provider: str, account_id: str, method: str, ref_id: str) -> None:
    if account_id == UNKNOWN_ACCOUNT:
        raise CliError(
            f"the {UNKNOWN_ACCOUNT} bucket cannot be activated — adopt the orphan "
            "into a declared account first"
        )
    active = load_active(provider)
    active[f"{account_id}/{method}"] = ref_id
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
    "active_ref",
    "read_artifact",
    "auth_data_for_ref",
    "store_artifact",
    "append_capture",
    "is_captured",
    "orphan_captures",
    "orphan_groups",
    "captures_for",
    "pool_for",
    "resolve_ref_prefix",
    "record_ref_id",
    "set_active",
]
