from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos.chatlas.delta_scan import run_chatlas_delta_scan


def chatlas_update(
    *,
    providers: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
    start_path: Path | str = ".",
    scan_cache_enabled: bool = True,
    session_index_cache_enabled: bool = True,
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    # The new update path has one phase for now: Chatlas.Delta.Scan / index-only.
    # The old scan/session-index cache flags both govern the private derivation cache.
    return run_chatlas_delta_scan(
        providers=providers,
        chatlas_root=chatlas_root,
        start_path=start_path,
        cache_enabled=scan_cache_enabled and session_index_cache_enabled,
        progress=progress,
    ).payload


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
    "chatlas_raw_export",
    "chatlas_raw_paths",
    "chatlas_resolved_session_stats",
    "chatlas_stats",
    "chatlas_update",
    "format_chatlas_stats_markdown",
    "resolve_chatlas_sessions",
]
