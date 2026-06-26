"""`Auth.Data.Rotation` — activate the head-of-line captured artifact.

Pure-pool `Auth.Registry`-only `Auth.Data.Activation`: the rotation ranks the
captured artifacts for an ``account/method`` by the provider's head-of-line rule
(`AuthMethod.rotation_rank`, reading registry-resident data only) and points
`Active.Auth.Data` at the head. It reads the capture log + stored artifact
payloads + the current active pointer, and writes only the active pointer — never
a home, never the provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from agentos.agent import auth_registry as R
from agentos.agent.auth_method_registry import auth_method_for_class


@dataclass(frozen=True)
class RotateResult:
    provider: str
    account: str
    method: str
    previous_active: str | None  # the previously active ref_id
    new_active: str | None  # the head-of-line ref_id
    changed: bool
    skipped: bool


def _epoch(ts: object) -> float:
    if not isinstance(ts, str) or not ts:
        return 0.0
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def rotate(provider: str, account: str, method: str, *, dry_run: bool = False) -> RotateResult:
    """Point `Active.Auth.Data` for ``account/method`` at the head-of-line artifact.

    Skipped (active untouched) when the pool is empty or no candidate ranks.
    """

    previous = R.active_ref(provider, account, method)
    auth_class = R.method_class(provider, account, method)
    auth_method = auth_method_for_class(provider, auth_class) if auth_class else None

    # Collapse the capture pool to one entry per ref_id (the activation pointer),
    # keeping its most recent capture time, capture-sequence index (file order) as
    # a deterministic tie-break, and the artifact key to resolve its payload.
    seen: dict[str, tuple[float, int, str | None]] = {}
    for seq, record in enumerate(R.captures_for(provider, account, method)):
        ref_id = R.record_ref_id(record)
        if ref_id is None:
            continue
        artifact_id = record.get("artifact_id")
        seen[ref_id] = (_epoch(record.get("ts")), seq, artifact_id if isinstance(artifact_id, str) else None)

    ranked: list[tuple[float, int, str]] = []
    if auth_method is not None:
        for ref_id, (captured_at, seq, artifact_id) in seen.items():
            auth = R.read_artifact(provider, artifact_id) if artifact_id is not None else None
            if auth is None:
                continue
            rank = auth_method.rotation_rank(auth, captured_at)
            if rank is None:
                continue
            ranked.append((rank, seq, ref_id))

    if not ranked:
        return RotateResult(provider, account, method, previous, previous, changed=False, skipped=True)

    head = max(ranked, key=lambda item: (item[0], item[1]))[2]
    changed = head != previous
    if changed and not dry_run:
        R.set_active(provider, account, method, head)
    return RotateResult(provider, account, method, previous, head, changed=changed, skipped=False)


def rotate_all(provider: str, *, dry_run: bool = False) -> list[RotateResult]:
    """Rotate every declared ``account/method`` for ``provider`` (from settings).

    `_unknown` is not a settings account, so the bucket is never rotated.
    """

    results: list[RotateResult] = []
    accounts = R.load_settings(provider).get("accounts")
    if not isinstance(accounts, dict):
        return results
    for account_id, record in accounts.items():
        methods = record.get("auth_methods") if isinstance(record, dict) else None
        if not isinstance(methods, dict):
            continue
        for method in methods:
            results.append(rotate(provider, account_id, method, dry_run=dry_run))
    return results


__all__ = ["RotateResult", "rotate", "rotate_all"]
