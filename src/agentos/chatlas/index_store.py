from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import json
from pathlib import Path
from shutil import rmtree
from typing import Any, Callable
from urllib.parse import quote

from agentos.chatlas.paths import SESSION_INDEX_ROOT, default_chatlas_root

SESSION_INDEX_SHARD_PREFIX_LENGTH = 2
SESSION_INDEX_FILENAME = "sessions.index.jsonl"


@dataclass(frozen=True)
class ChatlasSessionIndexRows:
    chatlas_root: Path
    session_index_root: Path
    rows: list[dict[str, Any]]
    scanned_row_count: int
    skipped_row_count: int
    partition_count: int


@dataclass(frozen=True)
class _CachedIndexPartition:
    rows: tuple[dict[str, Any], ...]
    scanned_row_count: int
    skipped_row_count: int


class ChatlasSessionIndexCache:
    """Bounded cache of authoritative JSON index partitions for one operation."""

    def __init__(self, *, capacity: int = 1024) -> None:
        if capacity < 0:
            raise ValueError("Chatlas index cache capacity must be non-negative")
        self.capacity = capacity
        self._partitions: OrderedDict[Path, _CachedIndexPartition] = OrderedDict()

    @property
    def partition_count(self) -> int:
        return len(self._partitions)

    def load_partition(self, path: Path) -> _CachedIndexPartition:
        key = path.resolve()
        cached = self._partitions.pop(key, None)
        if cached is not None:
            self._partitions[key] = cached
            return cached
        partition = _read_session_index_partition(path)
        if self.capacity:
            self._partitions[key] = partition
            while len(self._partitions) > self.capacity:
                self._partitions.popitem(last=False)
        return partition


def load_chatlas_session_index_rows(
    *,
    chatlas_root: Path | None = None,
    identity_hash: str | None = None,
    providers: tuple[str, ...] | None = None,
    cache: ChatlasSessionIndexCache | None = None,
) -> ChatlasSessionIndexRows:
    chatlas_root_path = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    session_index_root = chatlas_root_path / SESSION_INDEX_ROOT
    rows, scanned_row_count, skipped_row_count, partition_count = (
        _load_session_index_rows(
            session_index_root,
            identity_hash=identity_hash,
            providers=providers,
            cache=cache,
        )
    )
    return ChatlasSessionIndexRows(
        chatlas_root=chatlas_root_path,
        session_index_root=session_index_root,
        rows=rows,
        scanned_row_count=scanned_row_count,
        skipped_row_count=skipped_row_count,
        partition_count=partition_count,
    )


def _load_session_index_rows(
    session_index_root: Path,
    *,
    identity_hash: str | None = None,
    providers: tuple[str, ...] | None = None,
    cache: ChatlasSessionIndexCache | None = None,
) -> tuple[list[dict[str, Any]], int, int, int]:
    if not session_index_root.is_dir():
        return [], 0, 0, 0

    rows: list[dict[str, Any]] = []
    scanned_row_count = 0
    skipped_row_count = 0
    paths = _selected_partition_files(
        session_index_root,
        identity_hash=identity_hash,
        providers=providers,
    )
    runtime_cache = cache or ChatlasSessionIndexCache(capacity=0)
    for path in paths:
        partition = runtime_cache.load_partition(path)
        rows.extend(dict(row) for row in partition.rows)
        scanned_row_count += partition.scanned_row_count
        skipped_row_count += partition.skipped_row_count
    return rows, scanned_row_count, skipped_row_count, len(paths)


def _selected_partition_files(
    session_index_root: Path,
    *,
    identity_hash: str | None,
    providers: tuple[str, ...] | None,
) -> list[Path]:
    shard_identity = (
        identity_hash
        if identity_hash is not None
        and len(identity_hash) >= SESSION_INDEX_SHARD_PREFIX_LENGTH
        else None
    )
    if providers is None:
        return iter_session_index_partition_files(
            session_index_root,
            identity_hash=shard_identity,
        )
    paths = {
        path
        for provider in providers
        for path in iter_session_index_partition_files(
            session_index_root,
            provider=provider,
            identity_hash=shard_identity,
        )
    }
    return sorted(paths)


def _read_session_index_partition(path: Path) -> _CachedIndexPartition:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return _CachedIndexPartition((), 0, 1)
    rows: list[dict[str, Any]] = []
    skipped_row_count = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            skipped_row_count += 1
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            skipped_row_count += 1
            continue
        if isinstance(payload, dict):
            rows.append(payload)
        else:
            skipped_row_count += 1
    return _CachedIndexPartition(
        rows=tuple(rows),
        scanned_row_count=len(lines),
        skipped_row_count=skipped_row_count,
    )


def session_index_shard_prefix(identity_hash: str) -> str:
    if not identity_hash:
        raise ValueError("identity_hash must be a non-empty string")
    return identity_hash[:SESSION_INDEX_SHARD_PREFIX_LENGTH].lower()


def session_index_shard_path(
    session_index_root: Path,
    *,
    provider: str,
    identity_hash: str,
) -> Path:
    return (
        session_index_root
        / _path_component(provider)
        / session_index_shard_prefix(identity_hash)
        / SESSION_INDEX_FILENAME
    )


def clear_session_index_provider(session_index_root: Path, *, provider: str) -> None:
    provider_index_dir = session_index_root / _path_component(provider)
    if provider_index_dir.exists():
        rmtree(provider_index_dir)


def iter_session_index_partition_files(
    session_index_root: Path,
    *,
    provider: str | None = None,
    identity_hash: str | None = None,
) -> list[Path]:
    if identity_hash is not None:
        if provider is None:
            return sorted(
                path
                for path in (
                    provider_dir
                    / session_index_shard_prefix(identity_hash)
                    / SESSION_INDEX_FILENAME
                    for provider_dir in _provider_dirs(session_index_root)
                )
                if path.is_file()
            )
        path = session_index_shard_path(
            session_index_root,
            provider=provider,
            identity_hash=identity_hash,
        )
        return [path] if path.is_file() else []
    if provider is not None:
        root = session_index_root / _path_component(provider)
        if not root.is_dir():
            return []
        return sorted(
            path for path in root.glob(f"*/{SESSION_INDEX_FILENAME}") if path.is_file()
        )
    if not session_index_root.is_dir():
        return []
    return sorted(
        path
        for path in session_index_root.glob(f"*/*/{SESSION_INDEX_FILENAME}")
        if path.is_file()
    )


def iter_session_index_rows(
    session_index_root: Path,
    *,
    provider: str | None = None,
    identity_hash: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    visit_session_index_rows(
        session_index_root,
        lambda row: rows.append(row) or True,
        provider=provider,
        identity_hash=identity_hash,
    )
    return rows


def visit_session_index_rows(
    session_index_root: Path,
    visitor: Callable[[dict[str, Any]], bool | None],
    *,
    provider: str | None = None,
    identity_hash: str | None = None,
) -> None:
    for path in iter_session_index_partition_files(
        session_index_root,
        provider=provider,
        identity_hash=identity_hash,
    ):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and visitor(payload) is False:
                return


def _provider_dirs(session_index_root: Path) -> list[Path]:
    if not session_index_root.is_dir():
        return []
    return sorted(path for path in session_index_root.iterdir() if path.is_dir())


def _path_component(value: str) -> str:
    return quote(value, safe="")


__all__ = [
    "ChatlasSessionIndexCache",
    "ChatlasSessionIndexRows",
    "clear_session_index_provider",
    "iter_session_index_partition_files",
    "iter_session_index_rows",
    "load_chatlas_session_index_rows",
    "session_index_shard_path",
    "session_index_shard_prefix",
    "visit_session_index_rows",
]
