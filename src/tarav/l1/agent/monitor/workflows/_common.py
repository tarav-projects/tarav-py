"""Shared value parsing, formatting, and target-key helpers for monitor workflows."""

from __future__ import annotations

import datetime

from tarav.l1.agent.monitor.models import MonitorTarget


def _target_key(target: MonitorTarget) -> str:
    return f"{target.provider}/{target.account}@{target.home}"


def _format_remaining_duration(diff_seconds: int) -> str:
    if diff_seconds <= 0:
        return "0m"
    total_minutes = diff_seconds // 60
    if total_minutes == 0:
        total_minutes = 1
    days, remaining_minutes = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(remaining_minutes, 60)
    parts: list[str] = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    return " ".join(parts) or "0m"


def _format_age_duration(diff_seconds: int) -> str:
    return _format_remaining_duration(max(0, diff_seconds))


def _parse_datetime(value: str | None) -> datetime.datetime | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=datetime.UTC)
    return parsed.astimezone(datetime.UTC)


def _int_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _float_value(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _string_value(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None
