# $kw: --from Chatlas.Time.Interface
from __future__ import annotations

from datetime import datetime, timezone


def parse_chatlas_index_timestamp(value: object) -> datetime | None:
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


def format_chatlas_index_timestamp(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def chatlas_index_timestamp_sort_value(value: object) -> float:
    timestamp = parse_chatlas_index_timestamp(value)
    if timestamp is None:
        return 0.0
    return timestamp.timestamp()


__all__ = [
    "chatlas_index_timestamp_sort_value",
    "format_chatlas_index_timestamp",
    "parse_chatlas_index_timestamp",
]
