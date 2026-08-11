# $kw: --from Account.Management
"""Filesystem paths for the account store — provider-agnostic, credential-free.

These are pure location helpers under ``~/.agentos/accounts/`` shared by the new
model (`auth_registry`). They carry no credential logic, so they outlive the
old credential machinery.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from agentos._core.path_validation import validate_string_for_path
from agentos._core.project import agentos_home_dir


def account_registry_root() -> Path:
    return agentos_home_dir() / "accounts"


def account_archive_root() -> Path:
    return agentos_home_dir() / "archive"


def account_provider_root(provider: str) -> Path:
    return account_registry_root() / validate_string_for_path(provider, field_name="provider")


def archive_account_registry(*, label: str | None = None) -> dict[str, object]:
    """Back up the whole account store tree. Append-only and idempotent."""

    source = account_registry_root()
    archive_label = label or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = account_archive_root() / f"accounts-{archive_label}"
    if not source.exists():
        return {"status": "empty", "source": str(source), "destination": str(destination)}
    if destination.exists():
        return {"status": "exists", "source": str(source), "destination": str(destination)}
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)
    return {"status": "archived", "source": str(source), "destination": str(destination)}


__all__ = [
    "account_registry_root",
    "account_archive_root",
    "account_provider_root",
    "archive_account_registry",
]
