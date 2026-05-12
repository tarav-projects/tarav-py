from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos.chatlas.delta_scan import (
    run_chatlas_delta_scan,
    run_chatlas_index_redo,
    run_chatlas_index_reset,
)
from agentos.chatlas.index_query import run_chatlas_index_query


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
    _ = providers
    _ = full_output
    _ = chatlas_root
    raise _chatlas_stub_error("chatlas stats")


def format_chatlas_stats_markdown(payload: dict[str, object]) -> str:
    _ = payload
    raise _chatlas_stub_error("chatlas stats")


def chatlas_query(
    *,
    query: str | None = None,
    providers: tuple[str, ...] | None = None,
    instances: tuple[str, ...] | None = None,
    sort: str = "lexical",
    limit: int | None = None,
    extractable_only: bool = False,
    updated_after: object = None,
    include_match: bool = False,
    include_artifacts: bool = False,
    include_provider_stats: bool = False,
    compact: bool = False,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    _ = query
    _ = providers
    _ = instances
    _ = sort
    _ = limit
    _ = extractable_only
    _ = updated_after
    _ = include_match
    _ = include_artifacts
    _ = include_provider_stats
    _ = compact
    _ = chatlas_root
    raise _chatlas_stub_error("chatlas query")


def chatlas_raw_paths(
    *,
    query: str,
    providers: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    _ = query
    _ = providers
    _ = chatlas_root
    raise _chatlas_stub_error("chatlas raw path")


def chatlas_raw_export(
    *,
    query: str,
    providers: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    _ = query
    _ = providers
    _ = chatlas_root
    raise _chatlas_stub_error("chatlas raw export")


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
