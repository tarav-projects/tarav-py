from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from agentos.chatlas.delta_scan import SESSION_INDEX_ROOT, default_chatlas_root


@dataclass(frozen=True)
class ChatlasSessionIndexRows:
    chatlas_root: Path
    session_index_root: Path
    rows: list[dict[str, Any]]
    scanned_row_count: int
    skipped_row_count: int
    partition_count: int


def load_chatlas_session_index_rows(*, chatlas_root: Path | None = None) -> ChatlasSessionIndexRows:
    chatlas_root_path = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    session_index_root = chatlas_root_path / SESSION_INDEX_ROOT
    rows, scanned_row_count, skipped_row_count, partition_count = _load_session_index_rows(session_index_root)
    return ChatlasSessionIndexRows(
        chatlas_root=chatlas_root_path,
        session_index_root=session_index_root,
        rows=rows,
        scanned_row_count=scanned_row_count,
        skipped_row_count=skipped_row_count,
        partition_count=partition_count,
    )


def _load_session_index_rows(session_index_root: Path) -> tuple[list[dict[str, Any]], int, int, int]:
    if not session_index_root.is_dir():
        return [], 0, 0, 0

    rows: list[dict[str, Any]] = []
    scanned_row_count = 0
    skipped_row_count = 0
    partition_count = 0
    for path in sorted(session_index_root.rglob("*.jsonl")):
        if not path.is_file():
            continue
        partition_count += 1
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            skipped_row_count += 1
            continue
        for line in lines:
            scanned_row_count += 1
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
    return rows, scanned_row_count, skipped_row_count, partition_count


__all__ = ["ChatlasSessionIndexRows", "load_chatlas_session_index_rows"]
