"""Estimated burst limits from weekly usage history.

OpenAI stopped publishing the codex 5h burst window, so the monitor estimates
it from the usage registry's weekly history: flat weekly ranges imply idle 5h
windows, the histogram of weekly deltas over 5h spans carries a burst-sized
peak, and the peak location estimates how much weekly budget one full burst
window consumes. Estimates are guidance only — they are never persisted to the
usage registry and every consumer must keep them flagged as estimated.

The methodology iterates in the ``dev/burst-detection`` testground first; this
module mirrors its ``common`` layer.
"""

from __future__ import annotations

import datetime
import json
import math
from collections import Counter
from typing import Any

from agentos._core.project import agentos_home_dir
from agentos.agent.monitor.workflows._common import (
    _int_value,
    _parse_datetime,
    _string_value,
)

ESTIMATED_BURST_FALLBACK_WEEKLY_PERCENT = 15.8
ESTIMATED_BURST_WINDOW = datetime.timedelta(hours=5)
# Estimator-internal: flat-range delta sampling tolerates baseline records this
# far from the ideal window start. The current-window baseline lookup used for
# rendering has NO tolerance — see nearest_record_at_or_before.
_FLAT_RANGE_START_TOLERANCE = datetime.timedelta(minutes=30)
_FLAT_RANGE_THRESHOLDS = (
    datetime.timedelta(minutes=10),
    datetime.timedelta(minutes=20),
    datetime.timedelta(minutes=30),
    datetime.timedelta(hours=1),
)


def codex_registry_records() -> list[dict[str, object]]:
    """Weekly usage points for all codex targets from the usage registry."""
    registry_dir = agentos_home_dir() / "agent" / "usage-registry"
    if not registry_dir.is_dir():
        return []
    records: list[dict[str, object]] = []
    for record_path in sorted(registry_dir.glob("*-usage.jsonl")):
        if not record_path.is_file():
            continue
        with record_path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict) or record.get("provider") != "codex":
                    continue
                weekly = _weekly_limit_from_payload(record.get("payload"))
                recorded_at = _parse_datetime(_string_value(record.get("recorded_at")))
                if weekly is None or recorded_at is None:
                    continue
                reset_at, used_percent = weekly
                account = _string_value(record.get("account"))
                home = _string_value(record.get("home"))
                if account is None or home is None:
                    continue
                registry_record: dict[str, object] = {
                    "key": f"codex/{account}@{home}",
                    "recorded_at": recorded_at,
                    "reset_at": reset_at,
                    "used_percent": used_percent,
                }
                records.append(registry_record)
    return records


def _weekly_limit_from_payload(payload: object) -> tuple[str, int] | None:
    if not isinstance(payload, dict):
        return None
    snapshots: list[object] = []
    by_limit_id = payload.get("rateLimitsByLimitId")
    if isinstance(by_limit_id, dict):
        snapshots.extend(by_limit_id.values())
    snapshots.append(payload.get("rateLimits"))
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        for window_name in ("primary", "secondary"):
            window = snapshot.get(window_name)
            if not isinstance(window, dict):
                continue
            if _int_value(window.get("windowDurationMins")) != 10_080:
                continue
            reset_at = _int_value(window.get("resetsAt"))
            used_percent = _int_value(window.get("usedPercent"))
            if reset_at is None or used_percent is None:
                continue
            return _timestamp_period_key(reset_at), used_percent
    return None


def _timestamp_period_key(timestamp: int) -> str:
    return datetime.datetime.fromtimestamp(timestamp, tz=datetime.UTC).isoformat()


def estimated_burst_weekly_percent(
    records: list[dict[str, object]],
) -> float | None:
    """Estimate how much weekly budget one full 5h burst window consumes."""
    estimates: list[float] = []
    for threshold in _FLAT_RANGE_THRESHOLDS:
        deltas = _flat_range_deltas(records, min_flat_duration=threshold)
        counts = Counter(delta for delta in deltas if delta > 0)
        estimate = _gaussian_estimate_from_excess(counts)
        if estimate is not None:
            estimates.append(estimate)
    if not estimates:
        return None
    estimates.sort()
    midpoint = len(estimates) // 2
    if len(estimates) % 2:
        return estimates[midpoint]
    return (estimates[midpoint - 1] + estimates[midpoint]) / 2


def fixed_local_5h_window(
    *,
    recorded_at: datetime.datetime,
) -> tuple[datetime.datetime, datetime.datetime]:
    """The local-midnight-aligned 5h bucket containing recorded_at.

    A guidance convention: the provider's real burst windows rolled from first
    use, but fixed local buckets give a stable, explainable reset rhythm.
    """
    local_now = recorded_at.astimezone()
    local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    minutes_since_midnight = int((local_now - local_midnight).total_seconds() // 60)
    bucket_minutes = int(ESTIMATED_BURST_WINDOW.total_seconds() // 60)
    bucket_index = minutes_since_midnight // bucket_minutes
    local_start = local_midnight + datetime.timedelta(
        minutes=bucket_index * bucket_minutes
    )
    local_reset = local_start + ESTIMATED_BURST_WINDOW
    return local_start.astimezone(datetime.UTC), local_reset.astimezone(datetime.UTC)


def records_by_target(
    records: list[dict[str, object]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        key = record.get("key")
        recorded_at = record.get("recorded_at")
        reset_at = record.get("reset_at")
        used_percent = record.get("used_percent")
        if (
            not isinstance(key, str)
            or not isinstance(recorded_at, datetime.datetime)
            or not isinstance(reset_at, str)
            or not isinstance(used_percent, int)
        ):
            continue
        grouped.setdefault(key, []).append(
            {
                "key": key,
                "recorded_at": recorded_at,
                "reset_at": reset_at,
                "used_percent": used_percent,
            }
        )
    for target_records in grouped.values():
        target_records.sort(key=lambda item: item["recorded_at"])
    return grouped


def nearest_record_at_or_before(
    records: list[dict[str, Any]],
    *,
    target: datetime.datetime,
) -> dict[str, Any] | None:
    """Baseline lookup: the newest record not after target, however old.

    No proximity tolerance on purpose: registry records are written while
    agents run, so a gap between the baseline and target means no monitored
    activity — an older reading is still a valid picture of the usage level
    at target time. No record at-or-before target means no observed usage.
    """
    best: dict[str, Any] | None = None
    for record in records:
        recorded_at = record["recorded_at"]
        if recorded_at > target:
            break
        best = record
    return best


def _flat_range_deltas(
    records: list[dict[str, object]],
    *,
    min_flat_duration: datetime.timedelta,
) -> list[int]:
    grouped = records_by_target(records)
    deltas: list[int] = []
    for target_records in grouped.values():
        for flat_start, _flat_end in _flat_ranges(
            target_records,
            min_flat_duration=min_flat_duration,
        ):
            window_start = flat_start["recorded_at"] - ESTIMATED_BURST_WINDOW
            baseline = _nearest_record(target_records, target=window_start)
            if baseline is None:
                continue
            if abs(baseline["recorded_at"] - window_start) > _FLAT_RANGE_START_TOLERANCE:
                continue
            if baseline["reset_at"] != flat_start["reset_at"]:
                continue
            delta = flat_start["used_percent"] - baseline["used_percent"]
            if delta >= 0:
                deltas.append(delta)
    return deltas


def _flat_ranges(
    records: list[dict[str, Any]],
    *,
    min_flat_duration: datetime.timedelta,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    if not records:
        return []
    ranges: list[tuple[dict[str, Any], dict[str, Any]]] = []
    start = records[0]
    previous = records[0]
    for record in records[1:]:
        same_window = record["reset_at"] == previous["reset_at"]
        same_value = record["used_percent"] == previous["used_percent"]
        if same_window and same_value:
            previous = record
            continue
        if previous["recorded_at"] - start["recorded_at"] >= min_flat_duration:
            ranges.append((start, previous))
        start = record
        previous = record
    if previous["recorded_at"] - start["recorded_at"] >= min_flat_duration:
        ranges.append((start, previous))
    return ranges


def _nearest_record(
    records: list[dict[str, Any]],
    *,
    target: datetime.datetime,
) -> dict[str, Any] | None:
    if not records:
        return None
    timestamps = [record["recorded_at"] for record in records]
    index = _bisect_datetimes(timestamps, target)
    candidates: list[dict[str, Any]] = []
    if index < len(records):
        candidates.append(records[index])
    if index > 0:
        candidates.append(records[index - 1])
    return min(candidates, key=lambda item: abs(item["recorded_at"] - target), default=None)


def _bisect_datetimes(
    values: list[datetime.datetime],
    target: datetime.datetime,
) -> int:
    low = 0
    high = len(values)
    while low < high:
        midpoint = (low + high) // 2
        if values[midpoint] < target:
            low = midpoint + 1
        else:
            high = midpoint
    return low


def _gaussian_estimate_from_excess(counts: Counter[int]) -> float | None:
    model = _fit_exponential_background(counts)
    positive = {
        delta: count - model.expected(delta)
        for delta, count in counts.items()
        if count - model.expected(delta) > 0
    }
    if not positive:
        return None
    peak = max(positive, key=positive.get)
    peak_weight = positive[peak]
    local = {
        delta: residual
        for delta, residual in positive.items()
        if abs(delta - peak) <= 3 and residual >= 0.20 * peak_weight
    }
    mass = sum(local.values())
    if mass <= 0:
        return None
    return sum(delta * weight for delta, weight in local.items()) / mass


class _ExponentialBackground:
    def __init__(self, intercept: float, slope: float) -> None:
        self.intercept = intercept
        self.slope = slope

    def expected(self, x: int) -> float:
        return max(0.0, math.exp(self.intercept + self.slope * x))


def _fit_exponential_background(counts: Counter[int]) -> _ExponentialBackground:
    points = sorted((delta, count) for delta, count in counts.items() if count > 0)
    if len(points) < 2:
        return _ExponentialBackground(0.0, 0.0)
    kept = points
    model = _fit_log_linear(kept)
    for _ in range(4):
        residuals = [count - model.expected(delta) for delta, count in kept]
        cutoff = _median(residuals) + 2.5 * _mad(residuals)
        next_kept = [
            (delta, count)
            for delta, count in kept
            if count - model.expected(delta) <= cutoff
        ]
        if len(next_kept) < 2 or len(next_kept) == len(kept):
            break
        kept = next_kept
        model = _fit_log_linear(kept)
    return model


def _fit_log_linear(points: list[tuple[int, int]]) -> _ExponentialBackground:
    xs = [float(delta) for delta, _ in points]
    ys = [math.log(float(count)) for _, count in points]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return _ExponentialBackground(mean_y, 0.0)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    slope /= denominator
    intercept = mean_y - slope * mean_x
    return _ExponentialBackground(intercept, slope)


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    midpoint = len(sorted_values) // 2
    if len(sorted_values) % 2:
        return sorted_values[midpoint]
    return (sorted_values[midpoint - 1] + sorted_values[midpoint]) / 2


def _mad(values: list[float]) -> float:
    center = _median(values)
    return _median([abs(value - center) for value in values]) or 1.0
