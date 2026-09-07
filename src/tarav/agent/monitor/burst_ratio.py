# $kw: ^account-burst-ratio-measured --from Normalization.Pipeline::Account.Usage.Model --note [DC] weekly budget consumed by one full burst window is measured from the provider's own two windows rather than fixed in code --supp ^c20260811-47u
"""Weekly budget consumed by one full burst window, measured from the registry.

Providers publish both a burst window and a weekly window. Between two
observations inside one window generation, the rise in weekly used-percent
divided by the rise in burst used-percent is how much weekly budget a full
burst consumes. That ratio is a slowly-moving calibration value: measure it
from retained records rather than hardcoding it, because a hardcoded constant
silently drifts away from the plan it was measured on.

The ratio is guidance for the Weekly row's Burst-unit variant. A provider that
publishes only one window yields no samples and therefore no variant.
"""

from __future__ import annotations

import datetime
import statistics
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from tarav._core.errors import CliError
from tarav.agent.account_status import BURST_WINDOW_MINS, WEEKLY_WINDOW_MINS
from tarav.agent.providers.codex.account_status import codex_quota_pool
from tarav.agent.usage_registry import iter_usage_records_since


MEASUREMENT_WINDOW = datetime.timedelta(days=14)
MEASUREMENT_TTL = datetime.timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class _Observation:
    recorded_at: str
    burst_used: float
    burst_reset: str
    weekly_used: float
    weekly_reset: str


def _codex_observation(payload: Mapping[str, Any]) -> tuple[Any, ...] | None:
    """Read both windows of the account's Codex quota pool.

    The ratio only means something inside one pool, so this reads the same
    pool the account model tracks and ignores the account's other budgets.
    """

    try:
        _limit_id, snapshot = codex_quota_pool(payload)
    except CliError:
        return None
    burst: Mapping[str, Any] | None = None
    weekly: Mapping[str, Any] | None = None
    for key in ("primary", "secondary"):
        window = snapshot.get(key)
        if not isinstance(window, dict):
            continue
        duration = window.get("windowDurationMins")
        if duration == BURST_WINDOW_MINS:
            burst = window
        elif duration == WEEKLY_WINDOW_MINS:
            weekly = window
    if burst is None or weekly is None:
        return None
    return (
        burst.get("usedPercent"),
        burst.get("resetsAt"),
        weekly.get("usedPercent"),
        weekly.get("resetsAt"),
    )


def _claude_observation(payload: Mapping[str, Any]) -> tuple[Any, ...] | None:
    rate_limits = payload.get("rate_limits")
    if not isinstance(rate_limits, dict):
        return None
    burst = rate_limits.get("five_hour")
    weekly = rate_limits.get("seven_day")
    if not isinstance(burst, dict) or not isinstance(weekly, dict):
        return None
    return (
        burst.get("used_percentage"),
        burst.get("resets_at"),
        weekly.get("used_percentage"),
        weekly.get("resets_at"),
    )


_OBSERVATION_READERS = {
    "codex": _codex_observation,
    "claude-code": _claude_observation,
}


@dataclass(frozen=True, slots=True)
class BurstRatioMeasurement:
    """Weekly-percent-per-full-burst by account, with per-provider medians."""

    accounts: dict[str, float] = field(default_factory=dict)
    providers: dict[str, float] = field(default_factory=dict)
    sample_counts: dict[str, int] = field(default_factory=dict)
    computed_at: datetime.datetime | None = None

    def weekly_burst_percent(self, *, provider: str, account: str) -> float | None:
        """The account's own measured ratio, else its provider's median."""
        measured = self.accounts.get(_account_key(provider, account))
        if measured is not None:
            return measured
        return self.providers.get(provider)

    def is_stale(self, *, now: datetime.datetime) -> bool:
        if self.computed_at is None:
            return True
        return now - self.computed_at >= MEASUREMENT_TTL

    def payload(self) -> dict[str, object]:
        return {
            "accounts": dict(self.accounts),
            "providers": dict(self.providers),
            "sample_counts": dict(self.sample_counts),
            "computed_at": (
                self.computed_at.isoformat() if self.computed_at is not None else None
            ),
            "window_days": MEASUREMENT_WINDOW.days,
        }


def measure_burst_ratios(
    *,
    now: datetime.datetime | None = None,
    window: datetime.timedelta = MEASUREMENT_WINDOW,
) -> BurstRatioMeasurement:
    """Measure the ratio from usage records inside the measurement window."""
    now = now or datetime.datetime.now(tz=datetime.UTC)
    observations: dict[str, list[_Observation]] = {}
    for record in iter_usage_records_since(now - window):
        observation = _observation_from_record(record)
        if observation is None:
            continue
        key, parsed = observation
        observations.setdefault(key, []).append(parsed)
    return burst_ratios_from_observations(observations, computed_at=now)


def burst_ratios_from_observations(
    observations: Mapping[str, list[_Observation]],
    *,
    computed_at: datetime.datetime,
) -> BurstRatioMeasurement:
    """Reduce per-account observation series to measured ratios."""
    accounts: dict[str, float] = {}
    sample_counts: dict[str, int] = {}
    by_provider: dict[str, list[float]] = {}
    for key, series in observations.items():
        ratio, runs = _account_ratio(series)
        sample_counts[key] = runs
        if ratio is None:
            continue
        accounts[key] = ratio
        by_provider.setdefault(key.split("/", 1)[0], []).append(ratio)
    providers = {
        provider: statistics.median(ratios)
        for provider, ratios in by_provider.items()
        if ratios
    }
    return BurstRatioMeasurement(
        accounts=accounts,
        providers=providers,
        sample_counts=sample_counts,
        computed_at=computed_at,
    )


def _observation_from_record(
    record: Mapping[str, Any],
) -> tuple[str, _Observation] | None:
    provider = record.get("provider")
    account = record.get("account")
    payload = record.get("payload")
    recorded_at = record.get("recorded_at")
    reader = _OBSERVATION_READERS.get(provider) if isinstance(provider, str) else None
    if (
        reader is None
        or not isinstance(account, str)
        or not isinstance(payload, dict)
        or not isinstance(recorded_at, str)
    ):
        return None
    windows = reader(payload)
    if windows is None:
        return None
    burst_used, burst_reset, weekly_used, weekly_reset = windows
    if not isinstance(burst_used, int | float) or isinstance(burst_used, bool):
        return None
    if not isinstance(weekly_used, int | float) or isinstance(weekly_used, bool):
        return None
    if burst_reset is None or weekly_reset is None:
        return None
    return (
        _account_key(provider, account),
        _Observation(
            recorded_at=recorded_at,
            burst_used=float(burst_used),
            burst_reset=str(burst_reset),
            weekly_used=float(weekly_used),
            weekly_reset=str(weekly_reset),
        ),
    )


def _account_ratio(series: list[_Observation]) -> tuple[float | None, int]:
    """Pool telescoped endpoint deltas over every reset-free run in the series.

    Endpoint deltas rather than per-observation deltas: used-percent is reported
    as whole numbers, so summing every step would accumulate truncation error
    while ``last - first`` bounds it to one unit per run.
    """
    total_burst = 0.0
    total_weekly = 0.0
    usable_runs = 0
    for run in _reset_free_runs(series):
        burst_delta = run[-1].burst_used - run[0].burst_used
        weekly_delta = run[-1].weekly_used - run[0].weekly_used
        if burst_delta <= 0 or weekly_delta < 0:
            continue
        total_burst += burst_delta
        total_weekly += weekly_delta
        usable_runs += 1
    if total_burst <= 0:
        return None, usable_runs
    return 100.0 * total_weekly / total_burst, usable_runs


def _reset_free_runs(series: list[_Observation]) -> list[list[_Observation]]:
    """Split the series wherever either window rolled over.

    Reset identity is the split signal, not a used-percent decrease alone: a
    window that resets while idle reads zero on both sides of the boundary, so
    a decrease-only rule would merge across it and pool unrelated windows.
    """
    ordered = sorted(series, key=lambda item: item.recorded_at)
    runs: list[list[_Observation]] = []
    current: list[_Observation] = []
    previous: _Observation | None = None
    for observation in ordered:
        if previous is not None and _rolled_over(previous, observation):
            if len(current) > 1:
                runs.append(current)
            current = []
        current.append(observation)
        previous = observation
    if len(current) > 1:
        runs.append(current)
    return runs


def _rolled_over(previous: _Observation, current: _Observation) -> bool:
    return (
        current.burst_reset != previous.burst_reset
        or current.weekly_reset != previous.weekly_reset
        or current.burst_used < previous.burst_used
        or current.weekly_used < previous.weekly_used
    )


def _account_key(provider: str, account: str) -> str:
    return f"{provider}/{account}"


__all__ = [
    "BurstRatioMeasurement",
    "MEASUREMENT_TTL",
    "MEASUREMENT_WINDOW",
    "burst_ratios_from_observations",
    "measure_burst_ratios",
]
