from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Mapping


AccountCheckStatus = Literal["ok", "error"]
AccountUsageStatus = Literal["ok", "error", "unavailable"]
AccountIdentityMatch = Literal["verified", "mismatched", "unknown", "unavailable"]


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
    limit_name: str
    limit_label: str | None
    usage_over_time: UsageOverTimeLimitData | None = None
    provider_limit: Mapping[str, object] = field(default_factory=dict)

    def summary(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "limit_class": self.limit_class,
            "limit_name": self.limit_name,
            "limit_label": self.limit_label,
        }
        if self.usage_over_time is not None:
            payload["usage_over_time"] = self.usage_over_time.summary()
        if self.provider_limit:
            payload["provider_limit"] = dict(self.provider_limit)
        return payload


@dataclass(frozen=True)
class AccountStatus:
    provider: str
    account: str
    home: Path
    check_status: AccountCheckStatus
    usage_status: AccountUsageStatus
    link_state: str
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
            "link_state": self.link_state,
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


__all__ = [
    "AccountCheckStatus",
    "AccountIdentity",
    "AccountIdentityMatch",
    "AccountLimit",
    "AccountStatus",
    "AccountStatusError",
    "AccountUsageStatus",
    "AgentAccountContext",
    "UsageOverTimeLimitData",
]
