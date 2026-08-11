"""Minimal raw-artifact parsing helpers for the experimental extractor pipeline.

These are intentionally local to ``normalization`` so the extractor layer owns its
own raw access (the ``Raw.Normalizer`` encapsulation invariant): nothing
downstream of an extractor touches native formats. The logic mirrors the current
provider readers in ``agentos`` so the parallel system can reproduce their output.
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path


def coerce_timestamp(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        timestamp = float(value)
        if timestamp > 1_000_000_000_000:
            return timestamp / 1000.0
        if timestamp > 1_000_000_000:
            return timestamp
        return None
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return coerce_timestamp(float(value))
    except ValueError:
        pass
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        return None


def string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def iter_jsonl_objects(path: Path):
    """Decodable JSON objects in a JSONL file (any record type)."""
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    yield obj
    except OSError:
        return


def read_first_jsonl_object(path: Path) -> dict[str, object] | None:
    """First decodable JSON object in a JSONL file (any record type)."""
    return next(iter_jsonl_objects(path), None)


def read_first_jsonl_value(path: Path, field: str) -> str | None:
    """Value of ``field`` from the first JSONL record that carries a non-empty string
    for it (not just record 0 — a leading non-message record may lack it)."""
    for obj in iter_jsonl_objects(path):
        value = string_or_none(obj.get(field))
        if value is not None:
            return value
    return None


def read_codex_session_meta(path: Path) -> dict[str, object] | None:
    """First ``session_meta`` record carrying a payload id in a Codex rollout."""
    for obj in iter_jsonl_objects(path):
        if obj.get("type") != "session_meta":
            continue
        payload = obj.get("payload")
        if not isinstance(payload, dict):
            continue
        if string_or_none(payload.get("id")) is None:
            continue
        return obj
    return None


def format_stats_timestamp(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    from datetime import timezone

    return (
        datetime.fromtimestamp(timestamp, tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
