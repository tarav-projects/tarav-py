"""Provider-neutral account status, usage limits, and usage-record metadata.

An account is metered over two quota windows: a short burst window and a long
weekly window. Providers word them differently -- Codex primary/secondary,
Claude five_hour/seven_day -- and every provider adapter translates into the
neutral vocabulary here, so the monitor, the auto-prime workflow, and the
burst-ratio measurement read one shape regardless of who produced it.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping

from tarav.l0._core.errors import CliError


AccountCheckStatus = Literal["ok", "error"]
AccountUsageStatus = Literal["ok", "error", "unavailable"]
AccountIdentityMatch = Literal["verified", "mismatched", "unknown", "unavailable"]
USAGE_RECORD_STATUS_FRESH = "fresh"
USAGE_RECORD_STATUS_REGISTRY_FALLBACK = "registry_fallback"
USAGE_RECORD_STATUS_REGISTRY_LATEST = "registry_latest"

USAGE_OVER_TIME_LIMIT_CLASS = "usage_over_time"
BURST_LIMIT_ID = "burst"
WEEKLY_LIMIT_ID = "weekly"
BURST_WINDOW_MINS = 300
WEEKLY_WINDOW_MINS = 10_080
USAGE_OVER_TIME_LIMIT_LABELS = {
    BURST_LIMIT_ID: "Burst",
    WEEKLY_LIMIT_ID: "Weekly",
}
USAGE_OVER_TIME_LIMIT_IDS_BY_WINDOW_MINS = {
    BURST_WINDOW_MINS: BURST_LIMIT_ID,
    WEEKLY_WINDOW_MINS: WEEKLY_LIMIT_ID,
}


@dataclass(frozen=True)
class AgentAccountContext:
    provider: str
    account: str

    def summary(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "account": self.account,
        }


@dataclass(frozen=True)
class AccountIdentity:
    provider_account_id: str | None = None
    email: str | None = None
    label: str | None = None
    raw: Mapping[str, object] = field(default_factory=dict)

    def summary(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.provider_account_id is not None:
            payload["provider_account_id"] = self.provider_account_id
        if self.email is not None:
            payload["email"] = self.email
        if self.label is not None:
            payload["label"] = self.label
        if self.raw:
            payload["raw"] = dict(self.raw)
        return payload


class AccountStatusError(Exception):
    def __init__(
        self,
        *,
        error_type: str,
        message: str,
        exit_code: int | None = None,
        detail: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.exit_code = exit_code
        self.detail = {} if detail is None else dict(detail)

    def summary(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "type": self.error_type,
            "message": self.message,
        }
        if self.exit_code is not None:
            payload["exit_code"] = self.exit_code
        if self.detail:
            payload["detail"] = dict(self.detail)
        return payload


def fresh_usage_record_metadata(*, source: str) -> dict[str, Any]:
    return {
        "status": USAGE_RECORD_STATUS_FRESH,
        "recorded_at": None,
        "source": source,
    }


def registry_fallback_usage_record_metadata(
    *,
    source: str,
    recorded_at: str | None,
    live_error: Mapping[str, object],
) -> dict[str, Any]:
    return {
        "status": USAGE_RECORD_STATUS_REGISTRY_FALLBACK,
        "recorded_at": recorded_at,
        "age_sec": usage_record_age_sec(recorded_at),
        "source": source,
        "live_error": dict(live_error),
    }


def registry_latest_usage_record_metadata(
    *,
    source: str,
    recorded_at: str | None,
) -> dict[str, Any]:
    return {
        "status": USAGE_RECORD_STATUS_REGISTRY_LATEST,
        "recorded_at": recorded_at,
        "age_sec": usage_record_age_sec(recorded_at),
        "source": source,
    }


def usage_record_age_sec(recorded_at: str | None) -> int | None:
    if recorded_at is None:
        return None
    try:
        normalized = recorded_at[:-1] + "+00:00" if recorded_at.endswith("Z") else recorded_at
        parsed = datetime.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.UTC)
    return max(0, round((datetime.datetime.now(tz=datetime.UTC) - parsed).total_seconds()))


@dataclass(frozen=True)
class UsageOverTimeLimitData:
    used_percent: int | None
    period_started_at: str | None
    period_ends_at: str | None
    period_duration_mins: int | None = None
    resets_at: str | None = None

    def summary(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "used_percent": self.used_percent,
            "period_started_at": self.period_started_at,
            "period_ends_at": self.period_ends_at,
        }
        if self.period_duration_mins is not None:
            payload["period_duration_mins"] = self.period_duration_mins
        if self.resets_at is not None:
            payload["resets_at"] = self.resets_at
        return payload


@dataclass(frozen=True)
class AccountLimit:
    limit_class: str
    limit_id: str
    limit_name: str
    limit_label: str | None
    usage_over_time: UsageOverTimeLimitData | None = None
    provider_limit: Mapping[str, object] = field(default_factory=dict)

    def summary(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "limit_class": self.limit_class,
            "limit_id": self.limit_id,
            "limit_name": self.limit_name,
            "limit_label": self.limit_label,
        }
        if self.usage_over_time is not None:
            payload["usage_over_time"] = self.usage_over_time.summary()
        if self.provider_limit:
            payload["provider_limit"] = dict(self.provider_limit)
        return payload


def usage_over_time_limit(
    *,
    limit_id: str,
    used_percent: int | None,
    period_started_at: str | None,
    period_ends_at: str | None,
    period_duration_mins: int | None = None,
    resets_at: str | None = None,
    limit_label: str | None = None,
    provider_limit: Mapping[str, object] | None = None,
) -> AccountLimit:
    """Build a usage-over-time limit in the shared provider-neutral shape.

    Every provider adapter names the same windows the same way, so the
    identity of a limit is its neutral id, not the provider wording that
    produced it.
    """

    return AccountLimit(
        limit_class=USAGE_OVER_TIME_LIMIT_CLASS,
        limit_id=limit_id,
        limit_name=limit_id,
        limit_label=limit_label or usage_over_time_limit_label(limit_id),
        usage_over_time=UsageOverTimeLimitData(
            used_percent=used_percent,
            period_started_at=period_started_at,
            period_ends_at=period_ends_at,
            period_duration_mins=period_duration_mins,
            resets_at=resets_at,
        ),
        provider_limit=dict(provider_limit or {}),
    )


def usage_over_time_limit_label(limit_id: str) -> str:
    return USAGE_OVER_TIME_LIMIT_LABELS.get(limit_id, limit_id)


def usage_over_time_limit_id(window_duration_mins: int | None) -> str | None:
    """Classify a provider window by its duration, or None when unrecognized."""

    return USAGE_OVER_TIME_LIMIT_IDS_BY_WINDOW_MINS.get(window_duration_mins)


@dataclass(frozen=True)
class AccountStatus:
    provider: str
    account: str
    home: Path
    check_status: AccountCheckStatus
    usage_status: AccountUsageStatus
    auth_state: str
    expected_identity: AccountIdentity
    fetched_identity: AccountIdentity | None
    identity_match: AccountIdentityMatch
    auth_summary: str | None = None
    usage_summary: str | None = None
    limits: tuple[AccountLimit, ...] = ()
    errors: tuple[AccountStatusError, ...] = ()
    usage_errors: tuple[AccountStatusError, ...] = ()
    raw: Mapping[str, object] = field(default_factory=dict)

    def summary(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "provider": self.provider,
            "account": self.account,
            "home": str(self.home),
            "check_status": self.check_status,
            "usage_status": self.usage_status,
            "auth_state": self.auth_state,
            "expected_identity": self.expected_identity.summary(),
            "fetched_identity": (
                self.fetched_identity.summary()
                if self.fetched_identity is not None
                else None
            ),
            "identity_match": self.identity_match,
            "limits": [limit.summary() for limit in self.limits],
            "errors": [error.summary() for error in self.errors],
            "usage_errors": [error.summary() for error in self.usage_errors],
        }
        if self.auth_summary is not None:
            payload["auth_summary"] = self.auth_summary
        if self.usage_summary is not None:
            payload["usage_summary"] = self.usage_summary
        if self.raw:
            payload["raw"] = dict(self.raw)
        return payload






def limits_summary(limits: tuple[AccountLimit, ...]) -> str | None:
    parts: list[str] = []
    for limit in limits:
        usage = limit.usage_over_time
        if usage is None:
            continue
        if usage.used_percent is None:
            if limit.limit_label is not None:
                parts.append(limit.limit_label)
            continue
        label = limit.limit_label or limit.limit_name
        parts.append(f"{label} {usage.used_percent}%")
    return ", ".join(parts) or None


def string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def optional_int(value: object, *, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise CliError(f"{field_name} must be an integer")
    return value


def parse_iso_datetime(value: str | None) -> datetime.datetime | None:
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


def iso_from_epoch_seconds(epoch_seconds: int | None) -> str | None:
    if epoch_seconds is None:
        return None
    return datetime.datetime.fromtimestamp(
        epoch_seconds,
        tz=datetime.UTC,
    ).isoformat().replace("+00:00", "Z")


def period_bounds_from_reset(
    *,
    resets_at_epoch: int | None,
    period_duration_mins: int | None,
) -> tuple[str | None, str | None]:
    if resets_at_epoch is None or period_duration_mins is None:
        return (None, None)
    period_started_at_epoch = resets_at_epoch - (period_duration_mins * 60)
    return (
        iso_from_epoch_seconds(period_started_at_epoch),
        iso_from_epoch_seconds(resets_at_epoch),
    )


__all__ = [
    "AccountCheckStatus",
    "AccountIdentity",
    "AccountIdentityMatch",
    "AccountLimit",
    "AccountStatus",
    "AccountStatusError",
    "AccountUsageStatus",
    "AgentAccountContext",
    "BURST_LIMIT_ID",
    "BURST_WINDOW_MINS",
    "USAGE_OVER_TIME_LIMIT_CLASS",
    "USAGE_OVER_TIME_LIMIT_IDS_BY_WINDOW_MINS",
    "USAGE_OVER_TIME_LIMIT_LABELS",
    "USAGE_RECORD_STATUS_FRESH",
    "USAGE_RECORD_STATUS_REGISTRY_FALLBACK",
    "USAGE_RECORD_STATUS_REGISTRY_LATEST",
    "UsageOverTimeLimitData",
    "WEEKLY_LIMIT_ID",
    "WEEKLY_WINDOW_MINS",
    "fresh_usage_record_metadata",
    "iso_from_epoch_seconds",
    "limits_summary",
    "optional_int",
    "parse_iso_datetime",
    "period_bounds_from_reset",
    "registry_latest_usage_record_metadata",
    "registry_fallback_usage_record_metadata",
    "string_or_none",
    "usage_over_time_limit",
    "usage_over_time_limit_id",
    "usage_over_time_limit_label",
    "usage_record_age_sec",
]
