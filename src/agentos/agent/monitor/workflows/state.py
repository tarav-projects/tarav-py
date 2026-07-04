"""Typed per-workflow monitor state stored in ``MonitorState.data``.

The limits-tracking and auto-prime workflows keep their tick-to-tick state in
these dataclasses. ``payload()`` is the JSON boundary: the monitor result
payload serializes state through it. Innermost data rows (observations,
primed periods, decisions) stay plain dicts — they are JSON-shaped records
written and read only by their owning workflow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LimitsTargetState:
    provider: str
    account: str
    home: str
    profile: str | None = None
    start_path: str | None = None
    status: str = "pending"
    refresh_count: int = 0
    setup_message: str | None = None
    account_status: dict[str, Any] | None = None
    error: dict[str, object] | None = None
    last_refresh_tick: int | None = None
    last_error_emit: dict[str, object] | None = None

    def payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "provider": self.provider,
            "account": self.account,
            "home": self.home,
            "status": self.status,
            "refresh_count": self.refresh_count,
            "setup_message": self.setup_message,
            "account_status": self.account_status,
            "error": self.error,
            "last_refresh_tick": self.last_refresh_tick,
        }
        if self.profile is not None:
            payload["profile"] = self.profile
        if self.start_path is not None:
            payload["start_path"] = self.start_path
        if self.last_error_emit is not None:
            payload["last_error_emit"] = self.last_error_emit
        return payload


@dataclass
class LimitsWorkflowState:
    targets: dict[str, LimitsTargetState] = field(default_factory=dict)
    setup_tick: int | None = None
    last_tick: int | None = None
    run_count: int | None = None
    refresh_interval_sec: float | None = None
    fired_alarms: list[str] = field(default_factory=list)

    def payload(self) -> dict[str, object]:
        return {
            "targets": {
                key: target.payload() for key, target in self.targets.items()
            },
            "setup_tick": self.setup_tick,
            "last_tick": self.last_tick,
            "run_count": self.run_count,
            "refresh_interval_sec": self.refresh_interval_sec,
            "fired_alarms": list(self.fired_alarms),
        }


@dataclass
class AutoPrimeTargetState:
    provider: str | None = None
    account: str | None = None
    home: str | None = None
    profile: str | None = None
    start_path: str | None = None
    observations: dict[str, dict[str, object]] = field(default_factory=dict)
    primed_periods: dict[str, dict[str, object]] = field(default_factory=dict)
    last_decisions: list[dict[str, object]] = field(default_factory=list)
    last_decision: dict[str, object] | None = None
    retry_after_monotonic: float | None = None
    last_error: dict[str, object] | None = None
    last_attempt_tick: int | None = None
    last_success_tick: int | None = None

    def payload(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "account": self.account,
            "home": self.home,
            "observations": self.observations,
            "primed_periods": self.primed_periods,
            "last_decisions": list(self.last_decisions),
            "last_decision": self.last_decision,
            "retry_after_monotonic": self.retry_after_monotonic,
            "last_error": self.last_error,
            "last_attempt_tick": self.last_attempt_tick,
            "last_success_tick": self.last_success_tick,
        }


@dataclass
class AutoPrimeWorkflowState:
    targets: dict[str, AutoPrimeTargetState] = field(default_factory=dict)
    last_scan: dict[str, object] | None = None
    setup_tick: int | None = None
    last_tick: int | None = None
    run_count: int | None = None
    interval_sec: float | None = None
    retry_cooldown_sec: float | None = None
    fired_alarms: list[str] = field(default_factory=list)
    loaded_at: str | None = None
    config_fingerprint: str | None = None
    target_summary: list[dict[str, str]] = field(default_factory=list)
    target_limit_ids: dict[str, tuple[str, ...]] = field(default_factory=dict)
    triggers: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def payload(self) -> dict[str, object]:
        return {
            "targets": {
                key: target.payload() for key, target in self.targets.items()
            },
            "last_scan": self.last_scan,
            "setup_tick": self.setup_tick,
            "last_tick": self.last_tick,
            "run_count": self.run_count,
            "interval_sec": self.interval_sec,
            "retry_cooldown_sec": self.retry_cooldown_sec,
            "fired_alarms": list(self.fired_alarms),
            "loaded_at": self.loaded_at,
            "config_fingerprint": self.config_fingerprint,
            "target_summary": list(self.target_summary),
            "target_limit_ids": dict(self.target_limit_ids),
            "triggers": dict(self.triggers),
        }


def monitor_state_payload(data: dict[str, object]) -> dict[str, object]:
    """Serialize ``MonitorState.data`` for the JSON monitor payload."""
    return {
        key: value.payload()
        if isinstance(value, LimitsWorkflowState | AutoPrimeWorkflowState)
        else value
        for key, value in data.items()
    }
