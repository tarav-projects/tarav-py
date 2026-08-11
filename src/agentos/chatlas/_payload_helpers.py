from __future__ import annotations

from datetime import datetime, timezone
import json


DEFAULT_SUMMARY_TEXT_CHARS = 500


def string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def compact_text(value: str, *, max_chars: int = DEFAULT_SUMMARY_TEXT_CHARS) -> str:
    if max_chars < 4:
        raise ValueError("compact text limit must be at least 4 characters")
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3] + "..."


def dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def parse_event_timestamp(value: str) -> datetime | None:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def int_or_zero(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    return 0


def copy_present_fields(
    target: dict[str, object],
    source: dict,
    field_map: tuple[tuple[str, str], ...],
) -> None:
    for source_key, target_key in field_map:
        value = source.get(source_key)
        if value is not None:
            target[target_key] = value


def dedupe_dicts(values: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped: list[dict[str, object]] = []
    seen: set[str] = set()
    for value in values:
        identity = json.dumps(value, sort_keys=True, default=str)
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(value)
    return deduped


def jsonable_identity(value: object) -> str:
    return repr(value)
