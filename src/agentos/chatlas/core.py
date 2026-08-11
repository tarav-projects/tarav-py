from __future__ import annotations

import base64
from collections.abc import Callable
import json
from pathlib import Path
import stat
from typing import Any

from agentos.chatlas._payload_helpers import string_or_none
from agentos.chatlas.delta_scan import ScanScope, chatlas_delta_scan
from agentos.chatlas.index_query import select_materialization_row, select_one_chatlas_index_row


def chatlas_update(
    *,
    providers: tuple[str, ...] | None = None,
    instances: tuple[str, ...] | None = None,
    session_ids: tuple[str, ...] = (),
    chatlas_root: Path | None = None,
    start_path: Path | str = ".",
    scan_cache_enabled: bool = True,
    session_index_cache_enabled: bool = True,
    full_scan: bool = False,
    window_seconds: int | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    index_payload = chatlas_index_update(
        providers=providers,
        instances=instances,
        session_ids=session_ids,
        chatlas_root=chatlas_root,
        start_path=start_path,
        scan_cache_enabled=scan_cache_enabled,
        session_index_cache_enabled=session_index_cache_enabled,
        full_scan=full_scan,
        window_seconds=window_seconds,
        progress=progress,
    )
    return {
        **index_payload,
        "command": "chatlas update",
        "phases": {
            "index": index_payload,
        },
    }


def chatlas_index_update(
    *,
    providers: tuple[str, ...] | None = None,
    instances: tuple[str, ...] | None = None,
    session_ids: tuple[str, ...] = (),
    chatlas_root: Path | None = None,
    start_path: Path | str = ".",
    scan_cache_enabled: bool = True,
    session_index_cache_enabled: bool = True,
    full_scan: bool = False,
    window_seconds: int | None = None,
    command_name: str = "chatlas index update",
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    # Scan.Scope: every selection — bulk, provider, instance, session, window —
    # runs the one pipeline; scope narrows candidates, never mechanics.
    return chatlas_delta_scan(
        scope=ScanScope(
            providers=providers,
            instances=instances,
            session_ids=session_ids,
            window_seconds=window_seconds,
        ),
        chatlas_root=chatlas_root,
        start_path=start_path,
        cache_enabled=scan_cache_enabled and session_index_cache_enabled,
        full_scan=full_scan,
        command_name=command_name,
        progress=progress,
    )


def chatlas_raw_paths(
    *,
    uri: str | None = None,
    identity_hash: str | None = None,
    project: str | Path | None = None,
    project_base: str | None = None,
    providers: tuple[str, ...] | None = None,
    instances: tuple[str, ...] | None = None,
    provider_instance_fingerprint: str | None = None,
    session_id: str | None = None,
    display_name: str | None = None,
    extractable_only: bool = False,
    active_after: str | None = None,
    sort: str = "lexical",
    limit: int | None = None,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    session = select_one_chatlas_index_row(
        command="chatlas raw path",
        uri=uri,
        identity_hash=identity_hash,
        project=project,
        project_base=project_base,
        providers=providers,
        instances=instances,
        provider_instance_fingerprint=provider_instance_fingerprint,
        session_id=session_id,
        display_name=display_name,
        extractable_only=extractable_only,
        active_after=active_after,
        sort=sort,
        limit=limit,
        chatlas_root=chatlas_root,
    )
    session = select_materialization_row(
        session,
        uri=uri,
        instances=instances,
        provider_instance_fingerprint=provider_instance_fingerprint,
    )
    sources = _chatlas_raw_source_payloads(session)
    return {
        "status": "ok",
        "command": "chatlas raw path",
        "session": _compact_chatlas_index_row(session),
        "paths": [
            source["path"]
            for source in sources
            if isinstance(source.get("path"), str)
        ],
        "sources": sources,
    }


def chatlas_raw_export(
    *,
    uri: str | None = None,
    identity_hash: str | None = None,
    project: str | Path | None = None,
    project_base: str | None = None,
    providers: tuple[str, ...] | None = None,
    instances: tuple[str, ...] | None = None,
    provider_instance_fingerprint: str | None = None,
    session_id: str | None = None,
    display_name: str | None = None,
    extractable_only: bool = False,
    active_after: str | None = None,
    sort: str = "lexical",
    limit: int | None = None,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    session = select_one_chatlas_index_row(
        command="chatlas raw export",
        uri=uri,
        identity_hash=identity_hash,
        project=project,
        project_base=project_base,
        providers=providers,
        instances=instances,
        provider_instance_fingerprint=provider_instance_fingerprint,
        session_id=session_id,
        display_name=display_name,
        extractable_only=extractable_only,
        active_after=active_after,
        sort=sort,
        limit=limit,
        chatlas_root=chatlas_root,
    )
    session = select_materialization_row(
        session,
        uri=uri,
        instances=instances,
        provider_instance_fingerprint=provider_instance_fingerprint,
    )
    return {
        "status": "ok",
        "class": "agentos_chatlas.raw_export",
        "schema_version": 1,
        "command": "chatlas raw export",
        "session": _compact_chatlas_index_row(session),
        "sources": _chatlas_raw_source_payloads(session, include_content=True),
    }


def _chatlas_raw_source_payloads(
    session: dict[str, Any],
    *,
    include_content: bool = False,
) -> list[dict[str, object]]:
    artifacts = session.get("backing_artifacts")
    if not isinstance(artifacts, list):
        primary = session.get("primary_backing_artifact")
        artifacts = [primary] if isinstance(primary, dict) else []

    sources: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    for index, artifact in enumerate(artifacts, start=1):
        if not isinstance(artifact, dict):
            continue
        source = _chatlas_raw_source_payload(index=index, artifact=artifact)
        identity = (
            source.get("role"),
            source.get("storage_kind"),
            source.get("path"),
            json.dumps(source.get("locator"), sort_keys=True, default=str),
        )
        if identity in seen:
            continue
        seen.add(identity)
        if include_content:
            source.update(_chatlas_raw_source_content(source))
        sources.append(source)
    return sources


def _chatlas_raw_source_payload(*, index: int, artifact: dict[str, Any]) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_index": index,
    }
    for key in (
        "role",
        "storage_kind",
        "path",
        "locator",
        "extractable",
    ):
        value = artifact.get(key)
        if value is not None:
            payload[key] = value
    return payload


def _chatlas_raw_source_content(source: dict[str, object]) -> dict[str, object]:
    path_text = string_or_none(source.get("path"))
    if path_text is None:
        return {
            "content": None,
            "content_encoding": None,
            "content_unavailable_reason": "missing_path",
        }

    path = Path(path_text)
    try:
        path_stat = path.stat()
    except OSError as exc:
        return {
            "content": None,
            "content_encoding": None,
            "content_unavailable_reason": f"stat_failed: {exc}",
        }
    if not stat.S_ISREG(path_stat.st_mode):
        return {
            "content": None,
            "content_encoding": None,
            "content_unavailable_reason": "not_regular_file",
        }

    try:
        raw_content = path.read_bytes()
    except OSError as exc:
        return {
            "content": None,
            "content_encoding": None,
            "content_unavailable_reason": f"read_failed: {exc}",
        }

    try:
        return {
            "content": raw_content.decode("utf-8"),
            "content_encoding": "utf-8",
        }
    except UnicodeDecodeError:
        return {
            "content": base64.b64encode(raw_content).decode("ascii"),
            "content_encoding": "base64",
        }


def _compact_chatlas_index_row(session: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for field_name in (
        "uri",
        "provider",
        "instance",
        "provider_instance_fingerprint",
        "session_id",
        "display_name",
        "last_activity_at",
        "identity_hash",
    ):
        value = session.get(field_name)
        if value is not None:
            payload[field_name] = value
    return payload


__all__ = [
    "chatlas_index_update",
    "chatlas_raw_export",
    "chatlas_raw_paths",
    "chatlas_update",
]
