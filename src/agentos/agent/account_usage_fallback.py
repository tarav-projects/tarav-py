from __future__ import annotations

import datetime
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos.agent.account_status import (
    AccountLimit,
    AccountStatusError,
    registry_fallback_usage_record_metadata,
)
from agentos.agent.monitor_log import append_monitor_log_event
from agentos.agent.session_utils import string_or_none
from agentos.agent.usage_registry import latest_usage_record

AccountUsageReadResult = tuple[
    tuple[AccountLimit, ...],
    tuple[AccountStatusError, ...],
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
]


def account_usage_registry_fallback(
    *,
    provider: str,
    account: str,
    home: Path | None,
    source: str,
    parser: Callable[[Mapping[str, Any]], tuple[AccountLimit, ...]],
    live_error: AccountStatusError,
    fallback_to_usage_registry: bool,
) -> AccountUsageReadResult:
    def _log_refresh_error(reason: str) -> None:
        _emit_event(
            "target_refresh_error",
            provider=provider,
            account=account,
            home=home,
            payload={
                "source": source,
                "error_type": live_error.error_type,
                "message": live_error.message,
                "reason": reason,
            },
        )

    if not fallback_to_usage_registry:
        _log_refresh_error("fallback_disabled")
        return (), (live_error,), None, None, None
    if home is None:
        _log_refresh_error("home_missing")
        return (), (live_error,), None, None, None
    record = latest_usage_record(
        provider=provider,
        account=account,
        home=home,
        source=source,
    )
    if record is None:
        _log_refresh_error("no_registry_record")
        return (), (live_error,), None, None, None
    payload = record.get("payload")
    if not isinstance(payload, dict):
        _log_refresh_error("invalid_registry_record")
        return (), (live_error,), None, None, None
    try:
        limits = parser(payload)
    except (CliError, OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        fallback_error = AccountStatusError(
            error_type="invalid_registry_payload",
            message=str(exc),
        )
        _log_refresh_error("invalid_registry_payload")
        return (), (live_error, fallback_error), None, None, None
    recorded_at = string_or_none(record.get("recorded_at"))
    _emit_event(
        "stale_fallback_served",
        provider=provider,
        account=account,
        home=home,
        payload={
            "source": source,
            "recorded_at": recorded_at,
            "age_sec": _record_age_sec(recorded_at),
            "live_error_type": live_error.error_type,
            "live_error_message": live_error.message,
        },
    )
    return (
        limits,
        (),
        payload,
        None,
        registry_fallback_usage_record_metadata(
            source=source,
            recorded_at=recorded_at,
            live_error=live_error.summary(),
        ),
    )


def _emit_event(
    event: str,
    *,
    provider: str,
    account: str,
    home: Path | None,
    payload: dict[str, Any],
) -> None:
    append_monitor_log_event(
        event=event,
        provider=provider,
        account=account,
        home=home,
        payload=payload,
    )


def _record_age_sec(recorded_at: str | None) -> float | None:
    if recorded_at is None:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.UTC)
    now = datetime.datetime.now(tz=datetime.UTC)
    return max(0.0, (now - parsed).total_seconds())


__all__ = ["AccountUsageReadResult", "account_usage_registry_fallback"]
