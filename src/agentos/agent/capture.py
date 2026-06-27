"""The `Auth.Data.Capture` primitive and its global sweep.

`capture_home` is the singular primitive: read the `Auth.Data` present in one
home and archive it, never rejecting (a known identity files under its
account/method, an identifiable orphan under `Unknown.Account`). It contains no
scan machinery. `capture_all_homes` is the sweep — it loops the profile homes
`status` already collects and calls `capture_home` per home.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentos.agent import auth_registry as R
from agentos.agent.account_status_report import collect_home_targets
from agentos.agent.accounts_log import append_account_event
from agentos.agent.auth_method_registry import read_home_auth


@dataclass(frozen=True)
class CaptureResult:
    provider: str
    home: Path
    account: str
    method: str
    ref_id: str  # the activation pointer (the Auth.Ref id)
    artifact_id: str  # the content-addressed storage key for the secret blob
    is_new: bool  # a fresh capture-log append vs an already-present ref


def capture_home(provider: str, home: Path, *, dry_run: bool = False) -> CaptureResult | None:
    """Capture the first readable `Auth.Data` in ``home`` — None if nothing reads.

    Read-only on the home. Capture never rejects: the target account/method is
    resolved by `auth_registry.capture_target`, filing orphans under
    `Unknown.Account`. With ``dry_run`` it also writes nothing to the registry —
    the same `CaptureResult` is computed (the artifact id is the payload's content
    id, ``is_new`` from the capture log) but neither the artifact blob nor the
    capture-log line is persisted.
    """

    found = read_home_auth(provider, home)
    if found is None:
        return None
    auth_method, auth, identity = found.method, found.auth, found.identity
    account, method = R.capture_target(provider, identity, auth_method.name)
    ref_id = auth_method.ref_id(auth)
    artifact_id = auth.content_id() if dry_run else R.store_artifact(provider, auth)
    is_new = not R.is_captured(provider, account, method, ref_id)
    if is_new and not dry_run:
        R.append_capture(
            provider, account=account, method=method, auth_class=auth_method.name,
            auth_ref=identity, ref_id=ref_id, artifact_id=artifact_id,
        )
        append_account_event(
            event="capture", provider=provider, account=account, method=method,
            home=home, payload={"ref_id": ref_id, "artifact_id": artifact_id},
        )
    return CaptureResult(
        provider=provider, home=home, account=account, method=method,
        ref_id=ref_id, artifact_id=artifact_id, is_new=is_new,
    )


def capture_all_homes(provider: str, *, dry_run: bool = False) -> list[CaptureResult]:
    """Sweep every profile home for ``provider``, capturing what each holds.

    Homes with no readable `Auth.Data` are skipped (no result). The home source
    is the same profile-home union `status` reports over. ``dry_run`` makes the
    sweep read-only on the registry — a "what would a sweep do?" preview.
    """

    results: list[CaptureResult] = []
    for target in collect_home_targets(provider):
        result = capture_home(provider, target.home, dry_run=dry_run)
        if result is not None:
            results.append(result)
    return results


__all__ = ["CaptureResult", "capture_home", "capture_all_homes"]
