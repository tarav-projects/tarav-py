# $kw: --from Chatlas.Time.Interface
from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from typing import Any

from agentos._core.errors import CliError


_EVENT_PATTERN_TIMESTAMP_FIELDS = frozenset(
    {"timestamp_after", "timestamp_before"}
)
_EXACT_TIMESTAMP_FIELDS = frozenset({"at", "mtime", "timestamp"})


def parse_interface_timestamp(value: object) -> datetime | None:
    """Parse canonical timestamp data, treating unzoned data as UTC."""
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
    return parsed


def normalize_cli_timestamp(
    value: str | None,
    *,
    field: str,
    local_timezone: tzinfo | None = None,
) -> str | None:
    """Normalize one CLI timestamp to UTC; naive input means local time."""
    if value is None:
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise CliError(f"invalid {field} timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = (
            parsed.replace(tzinfo=local_timezone)
            if local_timezone
            else parsed.astimezone()
        )
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_cli_event_pattern_timestamps(
    value: Any,
    *,
    local_timezone: tzinfo | None = None,
) -> Any:
    """Normalize timestamp predicates in CLI Event.Pattern JSON without mutation."""
    if isinstance(value, list):
        return [
            normalize_cli_event_pattern_timestamps(
                item, local_timezone=local_timezone
            )
            for item in value
        ]
    if not isinstance(value, dict):
        return value
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if key in _EVENT_PATTERN_TIMESTAMP_FIELDS and isinstance(item, str):
            normalized[key] = normalize_cli_timestamp(
                item,
                field=f"Event.Pattern.{key}",
                local_timezone=local_timezone,
            )
        else:
            normalized[key] = normalize_cli_event_pattern_timestamps(
                item, local_timezone=local_timezone
            )
    return normalized


def format_local_timestamp(
    value: object,
    *,
    local_timezone: tzinfo | None = None,
    display_format: str | None = None,
) -> str:
    """Render canonical timestamp data in local time with an explicit offset."""
    parsed = parse_interface_timestamp(value)
    if parsed is None:
        return str(value)
    localized = parsed.astimezone(local_timezone)
    if display_format is not None:
        return localized.strftime(display_format)
    return localized.isoformat(timespec="seconds")


def is_timestamp_field(field: str) -> bool:
    normalized = field.casefold()
    return (
        normalized in _EXACT_TIMESTAMP_FIELDS
        or normalized.endswith("_at")
        or normalized.endswith("_time")
        or normalized.endswith("_timestamp")
    )


__all__ = [
    "format_local_timestamp",
    "is_timestamp_field",
    "normalize_cli_event_pattern_timestamps",
    "normalize_cli_timestamp",
    "parse_interface_timestamp",
]
