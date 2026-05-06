from __future__ import annotations

from datetime import datetime

from agentos._core.errors import CliError


def monthly_period_prefix(timestamp: datetime) -> str:
    return timestamp.strftime("%y%m")


def daily_period_prefix(timestamp: datetime) -> str:
    return timestamp.strftime("%y%m%d")


def period_prefix_for_strategy(strategy: str, timestamp: datetime) -> str:
    if strategy == "monthly":
        return monthly_period_prefix(timestamp)
    if strategy == "daily":
        return daily_period_prefix(timestamp)
    raise CliError(f"unsupported naming strategy for period prefix: {strategy}")


def period_prefix_for_rotation(rotation: str, timestamp: datetime) -> str:
    if rotation == "monthly":
        return monthly_period_prefix(timestamp)
    if rotation == "daily":
        return daily_period_prefix(timestamp)
    if rotation == "weekly":
        return f"{timestamp.strftime('%G')}W{timestamp.strftime('%V')}"
    if rotation == "yearly":
        return timestamp.strftime("%Y")
    if rotation == "run":
        return timestamp.strftime("%y%m%d-%H%M%S")
    raise CliError(f"unsupported rotation for period prefix: {rotation}")
