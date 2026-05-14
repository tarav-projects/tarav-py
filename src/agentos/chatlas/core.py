from __future__ import annotations

import base64
from collections.abc import Callable
import json
from pathlib import Path
import stat
from typing import Any

from agentos._core.errors import CliError
from agentos.chatlas.delta_scan import (
    run_chatlas_delta_scan,
    run_chatlas_index_redo,
    run_chatlas_index_reset,
)
from agentos.chatlas.index_query import run_chatlas_index_query
from agentos.chatlas.index_query import select_one_chatlas_index_row
from agentos.chatlas.index_stats import format_chatlas_index_stats_markdown
from agentos.chatlas.index_stats import run_chatlas_index_stats
from agentos.chatlas.query import run_chatlas_query


def chatlas_update(
    *,
    providers: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
    start_path: Path | str = ".",
    scan_cache_enabled: bool = True,
    session_index_cache_enabled: bool = True,
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    index_payload = chatlas_index_update(
        providers=providers,
        chatlas_root=chatlas_root,
        start_path=start_path,
        scan_cache_enabled=scan_cache_enabled,
        session_index_cache_enabled=session_index_cache_enabled,
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
    chatlas_root: Path | None = None,
    start_path: Path | str = ".",
    scan_cache_enabled: bool = True,
    session_index_cache_enabled: bool = True,
    command_name: str = "chatlas index update",
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    return run_chatlas_delta_scan(
        providers=providers,
        chatlas_root=chatlas_root,
        start_path=start_path,
        cache_enabled=scan_cache_enabled and session_index_cache_enabled,
        command_name=command_name,
        progress=progress,
    ).payload


def chatlas_index_reset(
    *,
    chatlas_root: Path | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    return run_chatlas_index_reset(
        chatlas_root=chatlas_root,
        progress=progress,
    ).payload


def chatlas_index_redo(
    *,
    providers: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    return run_chatlas_index_redo(
        providers=providers,
        chatlas_root=chatlas_root,
        progress=progress,
    ).payload


def chatlas_index_query(
    *,
    uri: str | None = None,
    identity_hash: str | None = None,
    providers: tuple[str, ...] | None = None,
    instances: tuple[str, ...] | None = None,
    provider_instance_fingerprint: str | None = None,
    session_id: str | None = None,
    display_name: str | None = None,
    extractable_only: bool = False,
    updated_after: str | None = None,
    sort: str = "lexical",
    limit: int | None = None,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    return run_chatlas_index_query(
        uri=uri,
        identity_hash=identity_hash,
        providers=providers,
        instances=instances,
        provider_instance_fingerprint=provider_instance_fingerprint,
        session_id=session_id,
        display_name=display_name,
        extractable_only=extractable_only,
        updated_after=updated_after,
        sort=sort,
        limit=limit,
        chatlas_root=chatlas_root,
    )


def _chatlas_stub_error(command: str) -> CliError:
    return CliError(f"{command} is under reimplementation")


def chatlas_stats(
    *,
    providers: tuple[str, ...] | None = None,
    full_output: bool = False,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    return run_chatlas_index_stats(
        providers=providers,
        full_output=full_output,
        chatlas_root=chatlas_root,
    )


def format_chatlas_stats_markdown(payload: dict[str, object]) -> str:
    return format_chatlas_index_stats_markdown(payload)


def chatlas_query(
    *,
    uri: str | None = None,
    identity_hash: str | None = None,
    providers: tuple[str, ...] | None = None,
    session_id: str | None = None,
    display_name: str | None = None,
    sort: str = "lexical",
    limit: int | None = None,
    scan_limit: int | None = None,
    extractable_only: bool = False,
    updated_after: str | None = None,
    raw_contains: tuple[str, ...] | None = None,
    user_contains: tuple[str, ...] | None = None,
    assistant_contains: tuple[str, ...] | None = None,
    message_contains: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    return run_chatlas_query(
        uri=uri,
        identity_hash=identity_hash,
        providers=providers,
        session_id=session_id,
        display_name=display_name,
        extractable_only=extractable_only,
        updated_after=updated_after,
        sort=sort,
        scan_limit=scan_limit,
        limit=limit,
        raw_contains=raw_contains,
        user_contains=user_contains,
        assistant_contains=assistant_contains,
        message_contains=message_contains,
        chatlas_root=chatlas_root,
    )


def chatlas_raw_paths(
    *,
    uri: str | None = None,
    identity_hash: str | None = None,
    providers: tuple[str, ...] | None = None,
    instances: tuple[str, ...] | None = None,
    provider_instance_fingerprint: str | None = None,
    session_id: str | None = None,
    display_name: str | None = None,
    extractable_only: bool = False,
    updated_after: str | None = None,
    sort: str = "lexical",
    limit: int | None = None,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    session = select_one_chatlas_index_row(
        command="chatlas raw path",
        uri=uri,
        identity_hash=identity_hash,
        providers=providers,
        instances=instances,
        provider_instance_fingerprint=provider_instance_fingerprint,
        session_id=session_id,
        display_name=display_name,
        extractable_only=extractable_only,
        updated_after=updated_after,
        sort=sort,
        limit=limit,
        chatlas_root=chatlas_root,
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
    providers: tuple[str, ...] | None = None,
    instances: tuple[str, ...] | None = None,
    provider_instance_fingerprint: str | None = None,
    session_id: str | None = None,
    display_name: str | None = None,
    extractable_only: bool = False,
    updated_after: str | None = None,
    sort: str = "lexical",
    limit: int | None = None,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    session = select_one_chatlas_index_row(
        command="chatlas raw export",
        uri=uri,
        identity_hash=identity_hash,
        providers=providers,
        instances=instances,
        provider_instance_fingerprint=provider_instance_fingerprint,
        session_id=session_id,
        display_name=display_name,
        extractable_only=extractable_only,
        updated_after=updated_after,
        sort=sort,
        limit=limit,
        chatlas_root=chatlas_root,
    )
    return {
        "status": "ok",
        "class": "agentos.chatlas.raw_export",
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
    path_text = _string_or_none(source.get("path"))
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
        "updated_at",
        "identity_hash",
    ):
        value = session.get(field_name)
        if value is not None:
            payload[field_name] = value
    return payload


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def resolve_chatlas_sessions(
    *,
    query: str | None = None,
    providers: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
) -> list[dict[str, Any]]:
    _ = query
    _ = providers
    _ = chatlas_root
    raise _chatlas_stub_error("chatlas session resolution")


def chatlas_resolved_session_stats(
    *,
    query: str,
    providers: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    _ = query
    _ = providers
    _ = chatlas_root
    raise _chatlas_stub_error("chatlas session stats")


__all__ = [
    "chatlas_query",
    "chatlas_index_query",
    "chatlas_index_redo",
    "chatlas_index_reset",
    "chatlas_index_update",
    "chatlas_raw_export",
    "chatlas_raw_paths",
    "chatlas_resolved_session_stats",
    "chatlas_stats",
    "chatlas_update",
    "format_chatlas_stats_markdown",
    "resolve_chatlas_sessions",
]
