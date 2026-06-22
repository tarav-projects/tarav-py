"""`Credential.Capture` — the one automatic, additive path.

Detect `Auth.Data` in a live source, extract its `Account.Identity`, classify it
against the registry, and append it as an `Auth.Data.Artifact`. Capture never
rejects: an identifiable orphan lands in the per-provider `Unknown.Account`
bucket; an unrecognizable credential is parked, not stored. The `_safe` wrapper
guarantees capture never raises into a host command.

See the `Account.Management` appendix in `agentos-pkg`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agentos.agent.account_model import (
    find_account_by_provider_account_id,
    store_artifact,
    upsert_account_identity,
)
from agentos.agent.auth_method import AuthMethod

# Reserved per-provider bucket for identifiable orphans (capture never rejects).
UNKNOWN_ACCOUNT = "__unknown__"

CaptureStatus = Literal["known", "unknown", "unrecognized", "empty", "error"]


@dataclass(frozen=True)
class CaptureResult:
    status: CaptureStatus
    provider: str
    auth_method: str
    account: str | None = None
    artifact_id: str | None = None
    provider_account_id: str | None = None
    error: str | None = None


def capture_from_home(method: AuthMethod, home: Path) -> CaptureResult:
    """Capture whatever credential ``method`` finds in ``home``. May raise — see ``_safe``."""

    auth_data = method.read_auth_data(home)
    if auth_data is None:
        return CaptureResult(status="empty", provider=method.provider, auth_method=method.name)

    identity = method.extract_identity(auth_data)
    if identity is None or not identity.provider_account_id:
        # Weak-binding case: recognizable credential but no stable identity. Park it.
        return CaptureResult(status="unrecognized", provider=method.provider, auth_method=method.name)

    provider_account_id = identity.provider_account_id
    account = find_account_by_provider_account_id(method.provider, provider_account_id)
    if account is not None:
        artifact_id = store_artifact(method.provider, account, method.name, auth_data)
        return CaptureResult(
            status="known",
            provider=method.provider,
            auth_method=method.name,
            account=account,
            artifact_id=artifact_id,
            provider_account_id=provider_account_id,
        )

    # Identifiable orphan -> Unknown.Account bucket, keeping the extracted identity.
    upsert_account_identity(method.provider, UNKNOWN_ACCOUNT)
    artifact_id = store_artifact(
        method.provider,
        UNKNOWN_ACCOUNT,
        method.name,
        auth_data,
        history_extra={"extracted_provider_account_id": provider_account_id},
    )
    return CaptureResult(
        status="unknown",
        provider=method.provider,
        auth_method=method.name,
        account=UNKNOWN_ACCOUNT,
        artifact_id=artifact_id,
        provider_account_id=provider_account_id,
    )


def capture_from_home_safe(method: AuthMethod, home: Path) -> CaptureResult:
    """Best-effort capture: never raises. Capture must never fail a host command."""

    try:
        return capture_from_home(method, home)
    except Exception as exc:  # noqa: BLE001 - capture is intentionally total
        return CaptureResult(
            status="error",
            provider=getattr(method, "provider", "unknown"),
            auth_method=getattr(method, "name", "unknown"),
            error=str(exc),
        )


__all__ = ["UNKNOWN_ACCOUNT", "CaptureResult", "capture_from_home", "capture_from_home_safe"]
