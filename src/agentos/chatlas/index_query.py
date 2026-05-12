from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from agentos.chatlas.delta_scan import SESSION_INDEX_ROOT, default_chatlas_root

_DEFAULT_LIMIT = 50


def run_chatlas_index_query(
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
    chatlas_root_path = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    session_index_root = chatlas_root_path / SESSION_INDEX_ROOT
    rows, scanned_row_count, skipped_row_count, partition_count = _load_session_index_rows(session_index_root)
    filters = {
        "uri": uri,
        "identity_hash": identity_hash,
        "providers": list(providers) if providers is not None else None,
        "instances": list(instances) if instances is not None else None,
        "provider_instance_fingerprint": provider_instance_fingerprint,
        "session_id": session_id,
        "display_name": display_name,
        "extractable": extractable_only,
        "updated_after": updated_after,
    }
    matched_rows = [
        row
        for row in rows
        if _row_matches(
            row,
            uri=uri,
            identity_hash=identity_hash,
            providers=providers,
            instances=instances,
            provider_instance_fingerprint=provider_instance_fingerprint,
            session_id=session_id,
            display_name=display_name,
            extractable_only=extractable_only,
            updated_after=updated_after,
        )
    ]
    sorted_rows = _sort_rows(matched_rows, sort=sort)
    effective_limit = _DEFAULT_LIMIT if limit is None else limit
    limited_rows = sorted_rows[:effective_limit]
    return {
        "status": "ok",
        "command": "chatlas index query",
        "chatlas_root": str(chatlas_root_path),
        "session_index_root": str(session_index_root),
        "filters": filters,
        "sort": sort,
        "limit": effective_limit,
        "partition_count": partition_count,
        "scanned_row_count": scanned_row_count,
        "skipped_row_count": skipped_row_count,
        "matched_row_count": len(matched_rows),
        "returned_row_count": len(limited_rows),
        "rows": limited_rows,
    }


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


def _row_matches(
    row: dict[str, Any],
    *,
    uri: str | None,
    identity_hash: str | None,
    providers: tuple[str, ...] | None,
    instances: tuple[str, ...] | None,
    provider_instance_fingerprint: str | None,
    session_id: str | None,
    display_name: str | None,
    extractable_only: bool,
    updated_after: str | None,
) -> bool:
    if uri is not None and row.get("uri") != uri:
        return False
    if identity_hash is not None and row.get("identity_hash") != identity_hash:
        return False
    if providers is not None and row.get("provider") not in providers:
        return False
    if instances is not None and row.get("instance") not in instances:
        return False
    if (
        provider_instance_fingerprint is not None
        and row.get("provider_instance_fingerprint") != provider_instance_fingerprint
    ):
        return False
    if session_id is not None and row.get("session_id") != session_id:
        return False
    if display_name is not None and display_name.casefold() not in str(row.get("display_name", "")).casefold():
        return False
    if extractable_only and row.get("extractable") is not True:
        return False
    if updated_after is not None and not _updated_at_is_after(row.get("updated_at"), updated_after):
        return False
    return True


def _sort_rows(rows: list[dict[str, Any]], *, sort: str) -> list[dict[str, Any]]:
    if sort == "newest":
        return sorted(rows, key=lambda row: _timestamp_sort_value(row.get("updated_at")), reverse=True)
    if sort == "oldest":
        return sorted(rows, key=lambda row: _timestamp_sort_value(row.get("updated_at")))
    return sorted(rows, key=lambda row: str(row.get("uri") or row.get("session_id") or ""))


def _updated_at_is_after(value: object, updated_after: str) -> bool:
    timestamp = _parse_timestamp(value)
    threshold = _parse_timestamp(updated_after)
    return timestamp is not None and threshold is not None and timestamp >= threshold


def _timestamp_sort_value(value: object) -> float:
    timestamp = _parse_timestamp(value)
    if timestamp is None:
        return 0.0
    return timestamp.timestamp()


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


__all__ = ["run_chatlas_index_query"]
