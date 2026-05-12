from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentos.chatlas.index_store import load_chatlas_session_index_rows


def run_chatlas_index_stats(
    *,
    providers: tuple[str, ...] | None = None,
    full_output: bool = False,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    index = load_chatlas_session_index_rows(chatlas_root=chatlas_root)
    rows = [
        row
        for row in index.rows
        if providers is None or row.get("provider") in providers
    ]
    provider_stats: dict[str, dict[str, Any]] = {}
    instance_stats: dict[str, dict[str, Any]] = {}
    for row in rows:
        provider = _string_or_none(row.get("provider")) or "<unknown>"
        instance = _string_or_none(row.get("instance")) or "<unknown>"
        _update_stats_bucket(provider_stats.setdefault(provider, _empty_provider_stats()), row)
        _update_instance_bucket(
            instance_stats.setdefault(
                f"{provider}/{instance}",
                {
                    "provider": provider,
                    "instance": instance,
                    **_empty_session_stats(),
                },
            ),
            row,
        )

    if full_output and providers is not None:
        for provider in providers:
            provider_stats.setdefault(provider, _empty_provider_stats())

    for bucket in provider_stats.values():
        bucket["non_extractable_session_count"] = bucket["session_count"] - bucket["extractable_session_count"]
        bucket["instance_count"] = len(bucket.pop("_instances"))
    for bucket in instance_stats.values():
        bucket["non_extractable_session_count"] = bucket["session_count"] - bucket["extractable_session_count"]

    stats = _stats_totals(rows)
    stats.update(
        {
            "provider_count": len({row.get("provider") for row in rows if _string_or_none(row.get("provider"))}),
            "instance_count": len(
                {
                    (row.get("provider"), row.get("instance"))
                    for row in rows
                    if _string_or_none(row.get("provider")) and _string_or_none(row.get("instance"))
                }
            ),
            "partition_count": index.partition_count,
            "scanned_row_count": index.scanned_row_count,
            "skipped_row_count": index.skipped_row_count,
        }
    )
    return {
        "status": "ok",
        "command": "chatlas stats",
        "chatlas_root": str(index.chatlas_root),
        "session_index_root": str(index.session_index_root),
        "filters": {
            "providers": list(providers) if providers is not None else None,
        },
        "stats": stats,
        "by_provider": dict(sorted(provider_stats.items())),
        "by_instance": dict(sorted(instance_stats.items())),
    }


def format_chatlas_index_stats_markdown(payload: dict[str, object]) -> str:
    stats = payload.get("stats")
    if not isinstance(stats, dict):
        stats = {}
    lines = [
        "Chatlas session index",
        "",
        f"Sessions: {stats.get('session_count', 0)}",
        f"Extractable: {stats.get('extractable_session_count', 0)}",
        f"Non-extractable: {stats.get('non_extractable_session_count', 0)}",
        f"Providers: {stats.get('provider_count', 0)}",
        f"Instances: {stats.get('instance_count', 0)}",
        f"Index shards: {stats.get('partition_count', 0)}",
        f"Scanned rows: {stats.get('scanned_row_count', 0)}",
        f"Skipped rows: {stats.get('skipped_row_count', 0)}",
        f"Updated range: {_format_updated_range(stats)}",
    ]
    by_provider = payload.get("by_provider")
    if isinstance(by_provider, dict) and by_provider:
        lines.extend(["", "Providers:"])
        for provider, provider_stats in by_provider.items():
            if not isinstance(provider_stats, dict):
                continue
            lines.append(
                f"- {provider}: {provider_stats.get('session_count', 0)} sessions, "
                f"{provider_stats.get('instance_count', 0)} instances"
            )
    return "\n".join(lines)


def _stats_totals(rows: list[dict[str, Any]]) -> dict[str, object]:
    timestamps = sorted(
        timestamp
        for row in rows
        if (timestamp := _parse_timestamp(row.get("updated_at"))) is not None
    )
    session_count = len(rows)
    extractable_session_count = sum(1 for row in rows if row.get("extractable") is True)
    return {
        "session_count": session_count,
        "extractable_session_count": extractable_session_count,
        "non_extractable_session_count": session_count - extractable_session_count,
        "oldest_updated_at": _format_timestamp(timestamps[0]) if timestamps else None,
        "latest_updated_at": _format_timestamp(timestamps[-1]) if timestamps else None,
    }


def _empty_provider_stats() -> dict[str, Any]:
    return {
        **_empty_session_stats(),
        "instance_count": 0,
        "_instances": set(),
    }


def _empty_session_stats() -> dict[str, Any]:
    return {
        "session_count": 0,
        "extractable_session_count": 0,
        "non_extractable_session_count": 0,
        "oldest_updated_at": None,
        "latest_updated_at": None,
    }


def _update_stats_bucket(bucket: dict[str, Any], row: dict[str, Any]) -> None:
    _update_session_counts(bucket, row)
    instance = _string_or_none(row.get("instance"))
    if instance is not None:
        bucket["_instances"].add(instance)


def _update_instance_bucket(bucket: dict[str, Any], row: dict[str, Any]) -> None:
    _update_session_counts(bucket, row)


def _update_session_counts(bucket: dict[str, Any], row: dict[str, Any]) -> None:
    bucket["session_count"] += 1
    if row.get("extractable") is True:
        bucket["extractable_session_count"] += 1
    _update_timestamp_range(bucket, row.get("updated_at"))


def _update_timestamp_range(bucket: dict[str, Any], value: object) -> None:
    timestamp = _parse_timestamp(value)
    if timestamp is None:
        return
    formatted = _format_timestamp(timestamp)
    oldest = _parse_timestamp(bucket.get("oldest_updated_at"))
    latest = _parse_timestamp(bucket.get("latest_updated_at"))
    if oldest is None or timestamp < oldest:
        bucket["oldest_updated_at"] = formatted
    if latest is None or timestamp > latest:
        bucket["latest_updated_at"] = formatted


def _format_updated_range(stats: dict[object, object]) -> str:
    oldest = stats.get("oldest_updated_at")
    latest = stats.get("latest_updated_at")
    if oldest is None and latest is None:
        return "<none>"
    return f"{oldest or '<none>'} .. {latest or '<none>'}"


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


def _format_timestamp(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


__all__ = ["format_chatlas_index_stats_markdown", "run_chatlas_index_stats"]
