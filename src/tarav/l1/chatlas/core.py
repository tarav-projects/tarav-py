from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from tarav.l1.chatlas.delta_scan import ScanScope, chatlas_delta_scan
from tarav.l1.chatlas.session_resolver import resolve_session_index_row


def chatlas_update(
    *,
    providers: tuple[str, ...] | None = None,
    instances: tuple[str, ...] | None = None,
    session_ids: tuple[str, ...] = (),
    chatlas_root: Path | None = None,
    start_path: Path | str = ".",
    cache_enabled: bool = True,
    full_scan: bool = False,
    window_seconds: int | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    return chatlas_delta_scan(
        scope=ScanScope(
            providers=providers,
            instances=instances,
            session_ids=session_ids,
            window_seconds=window_seconds,
        ),
        chatlas_root=chatlas_root,
        start_path=start_path,
        cache_enabled=cache_enabled,
        full_scan=full_scan,
        command_name="chatlas update",
        progress=progress,
    )


def chatlas_raw_sources(
    *,
    identity_hash: str | None = None,
    session_id: str | None = None,
    provider: str | None = None,
    instance: str | None = None,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    row = resolve_session_index_row(
        identity_hash=identity_hash,
        session_id=session_id,
        provider=provider,
        instance=instance,
        chatlas_root=chatlas_root,
    )
    artifacts = row.get("backing_artifacts")
    if not isinstance(artifacts, list):
        primary = row.get("primary_backing_artifact")
        artifacts = [primary] if isinstance(primary, dict) else []
    sources = [
        _raw_source(artifact) for artifact in artifacts if isinstance(artifact, dict)
    ]
    return {
        "session": {
            "provider": row.get("provider"),
            "instance": row.get("instance"),
            "session_id": row.get("session_id"),
            "identity_hash": row.get("identity_hash"),
        },
        "sources": sources,
    }


def _raw_source(artifact: dict[str, Any]) -> dict[str, object]:
    return {
        key: artifact[key]
        for key in ("role", "storage_kind", "path", "locator", "extractable")
        if key in artifact
    }


__all__ = ["chatlas_raw_sources", "chatlas_update"]
