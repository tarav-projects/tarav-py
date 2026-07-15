"""Limits-tracking workflow: usage refresh, transition logging, and limit row rendering."""

from __future__ import annotations

import datetime
import json
import math
import time
from collections import Counter
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos._core.project import agentos_home_dir
from agentos.agent.account_status import (
    AccountIdentity,
    AccountLimit,
    AccountStatus,
    USAGE_RECORD_STATUS_FRESH,
    USAGE_RECORD_STATUS_REGISTRY_FALLBACK,
    USAGE_RECORD_STATUS_REGISTRY_LATEST,
    registry_latest_usage_record_metadata,
)
from agentos.agent.monitor.clock import (
    LIMITS_TRACKING_PERIODIC_ALARM,
    MONITOR_ENTER_ALARM,
    MONITOR_STARTUP_ALARM,
    MonitorClockSnapshot,
)
from agentos.agent.monitor.models import (
    LIMITS_TRACKING_WORKFLOW,
    MonitorAccountRow,
    MonitorColumnVariant,
    MonitorFrame,
    MonitorInfoRow,
    MonitorResetRow,
    MonitorRow,
    MonitorState,
    MonitorTarget,
    MonitorTextRow,
    MonitorUsageTimeRow,
    MonitorWorkflowConfig,
)
from agentos.agent.monitor.workflows._common import (
    _format_age_duration,
    _format_remaining_duration,
    _int_value,
    _parse_datetime,
    _string_value,
    _target_key,
)
from agentos.agent.monitor.workflows.auto_prime import (
    _auto_prime_status_part,
    _auto_prime_target_state,
)
from agentos.agent.monitor.workflows.state import (
    AutoPrimeTargetState,
    LimitsTargetState,
    LimitsWorkflowState,
)
from agentos.agent.monitor_log import append_monitor_log_event
from agentos.agent.providers import resolve_account_runtime_agent
from agentos.agent.usage_registry import latest_usage_record
from agentos.claude.account_status import (
    CLAUDE_STATUSLINE_USAGE_SOURCE,
    claude_statusline_usage_record_limits,
)
from agentos.codex.account_status import (
    CODEX_APP_SERVER_USAGE_SOURCE,
    codex_usage_record_limits,
)
from agentos.copilot.account_status import (
    COPILOT_INTERNAL_USER_USAGE_SOURCE,
    copilot_usage_record_limits,
)


# Fallback staleness threshold when no refresh interval is available. A usage
# record older than this counts as "stale" for target_transition logging.
_DEFAULT_STALE_THRESHOLD_SEC = 600.0
# While an error/fallback condition persists, re-log it at most once per this
# interval (a heartbeat), so a stuck account does not spam one line per tick.
_ERROR_HEARTBEAT_SEC = 3600.0
_WEEKLY_BURST_PERCENT_BY_PROVIDER = {
    "claude-code": 9.0,
}
_CODEX_ESTIMATED_BURST_FALLBACK_WEEKLY_PERCENT = 15.8
_CODEX_ESTIMATED_BURST_WINDOW = datetime.timedelta(hours=5)
_CODEX_ESTIMATED_BURST_START_TOLERANCE = datetime.timedelta(minutes=30)
_CODEX_ESTIMATED_BURST_THRESHOLDS = (
    datetime.timedelta(minutes=10),
    datetime.timedelta(minutes=20),
    datetime.timedelta(minutes=30),
    datetime.timedelta(hours=1),
)


class LimitsTrackingWorkflow:
    name = LIMITS_TRACKING_WORKFLOW
    periodic_alarm_name = LIMITS_TRACKING_PERIODIC_ALARM

    def __init__(self, config: MonitorWorkflowConfig) -> None:
        self.config = config
        self.refresh_interval_sec = config.refresh_interval_sec
        # Wall clock for the error heartbeat; injectable so tests do not sleep.
        self._error_clock = time.time

    def setup(
        self,
        state: MonitorState,
        frame: MonitorFrame,
    ) -> None:
        workflow_state = self._workflow_state(state)
        workflow_state.setup_tick = frame.tick
        workflow_state.refresh_interval_sec = self.config.refresh_interval_sec
        for target in self.config.targets:
            target_state = self._target_state(
                workflow_state, target=target, target_key=_target_key(target)
            )
            self._prime_target_from_usage_registry(target_state, target=target)
            self._maybe_log_error(target, target_state, tick=frame.tick)
        self._refresh_codex_estimated_burst_state(workflow_state)

        self._write_frame_block(frame, state=state, workflow_state=workflow_state)

    def loop(
        self,
        state: MonitorState,
        frame: MonitorFrame,
        trigger: MonitorClockSnapshot,
    ) -> None:
        run_count = state.workflow_run_counts.get(self.name, 0) + 1
        state.workflow_run_counts[self.name] = run_count
        workflow_state = self._workflow_state(state)
        workflow_state.last_tick = frame.tick
        workflow_state.run_count = run_count
        workflow_state.refresh_interval_sec = self.config.refresh_interval_sec
        workflow_state.fired_alarms = list(trigger.fired_alarm_names)

        should_refresh = bool(
            {
                MONITOR_STARTUP_ALARM,
                MONITOR_ENTER_ALARM,
                LIMITS_TRACKING_PERIODIC_ALARM,
            }.intersection(trigger.fired_alarm_names)
        )
        for target in self.config.targets:
            target_state = self._target_state(
                workflow_state, target=target, target_key=_target_key(target)
            )
            if should_refresh:
                prior = self._effective_target_state(target_state)
                self._refresh_target(target_state, target=target, tick=frame.tick)
                new = self._effective_target_state(target_state)
                self._maybe_log_transition(
                    target, prior=prior, new=new, tick=frame.tick
                )
                self._maybe_log_error(target, target_state, tick=frame.tick)
        if should_refresh:
            self._refresh_codex_estimated_burst_state(workflow_state)

        self._write_frame_block(frame, state=state, workflow_state=workflow_state)

    def _stale_threshold_sec(self) -> float:
        interval = self.config.refresh_interval_sec
        if isinstance(interval, int | float) and interval > 0:
            return 2.0 * float(interval)
        return _DEFAULT_STALE_THRESHOLD_SEC

    def _effective_target_state(
        self, target_state: LimitsTargetState
    ) -> dict[str, object]:
        return {
            "status": target_state.status,
            "has_error": target_state.error is not None,
            "staleness": self._staleness_class(target_state.account_status),
        }

    def _staleness_class(self, account_status: object) -> str | None:
        # Classify from the usage record's status, not age alone: a successful
        # live fetch ("fresh") carries no age_sec, so age-only classification
        # would mislabel it None and flap on every refresh. Age is only
        # meaningful for the registry-backed records that carry it.
        if not isinstance(account_status, dict):
            return None
        raw = account_status.get("raw")
        usage_record = raw.get("usage_record") if isinstance(raw, dict) else None
        if not isinstance(usage_record, dict):
            return None
        record_status = _string_value(usage_record.get("status"))
        if record_status == USAGE_RECORD_STATUS_FRESH:
            return "fresh"
        if record_status in (
            USAGE_RECORD_STATUS_REGISTRY_LATEST,
            USAGE_RECORD_STATUS_REGISTRY_FALLBACK,
        ):
            age_sec = _int_value(usage_record.get("age_sec"))
            if age_sec is None:
                return None
            return "stale" if age_sec > self._stale_threshold_sec() else "fresh"
        return None

    def _maybe_log_transition(
        self,
        target: MonitorTarget,
        *,
        prior: dict[str, object],
        new: dict[str, object],
        tick: int,
    ) -> None:
        if new == prior:
            return
        append_monitor_log_event(
            event="target_transition",
            tick=tick,
            provider=target.provider,
            account=target.account,
            home=target.home,
            payload={"from": prior, "to": new},
        )

    def _maybe_log_error(
        self,
        target: MonitorTarget,
        target_state: LimitsTargetState,
        *,
        tick: int,
    ) -> None:
        # Log error/fallback conditions on change + heartbeat, not every tick.
        signature, event, payload = self._error_signal(target_state)
        last = target_state.last_error_emit
        if signature is None:
            if last is not None:
                target_state.last_error_emit = None
            return
        now = self._error_clock()
        if last is not None and last.get("signature") == signature:
            last_at = last.get("at")
            if isinstance(last_at, int | float) and (now - last_at) < _ERROR_HEARTBEAT_SEC:
                return
        append_monitor_log_event(
            event=event,
            tick=tick,
            provider=target.provider,
            account=target.account,
            home=target.home,
            payload=payload,
        )
        target_state.last_error_emit = {"signature": signature, "at": now}

    def _error_signal(
        self, target_state: LimitsTargetState
    ) -> tuple[tuple[str, str | None] | None, str, dict[str, object]]:
        # A hard refresh exception captured on the target.
        error = target_state.error
        if isinstance(error, dict):
            error_type = _string_value(error.get("type"))
            return (
                ("refresh_error", error_type),
                "target_refresh_error",
                {
                    "source": "account_status",
                    "error_type": error_type,
                    "message": _string_value(error.get("message")),
                },
            )
        account_status = target_state.account_status
        if not isinstance(account_status, dict):
            return (None, "", {})
        raw = account_status.get("raw")
        usage_record = raw.get("usage_record") if isinstance(raw, dict) else None
        if isinstance(usage_record, dict):
            record_status = _string_value(usage_record.get("status"))
            if record_status == USAGE_RECORD_STATUS_REGISTRY_FALLBACK:
                live_error = usage_record.get("live_error")
                live_error = live_error if isinstance(live_error, dict) else {}
                error_type = _string_value(live_error.get("type"))
                return (
                    ("stale_fallback", error_type),
                    "stale_fallback_served",
                    {
                        "source": _string_value(usage_record.get("source")),
                        "age_sec": _int_value(usage_record.get("age_sec")),
                        "live_error_type": error_type,
                        "live_error_message": _string_value(live_error.get("message")),
                    },
                )
        if _string_value(account_status.get("usage_status")) == "error":
            return (
                ("refresh_error", "usage_error"),
                "target_refresh_error",
                {"source": "account_status", "error_type": "usage_error", "message": None},
            )
        return (None, "", {})

    def _prime_target_from_usage_registry(
        self,
        target_state: LimitsTargetState,
        *,
        target: MonitorTarget,
    ) -> None:
        source = _usage_record_source_for_target(target)
        record = (
            latest_usage_record(
                provider=target.provider,
                account=target.account,
                home=target.home,
                source=source,
            )
            if source is not None
            else None
        )
        if record is None:
            target_state.status = "pending"
            target_state.setup_message = "waiting for first fetch"
            target_state.account_status = None
            target_state.error = None
            return
        try:
            account_status = _account_status_summary_from_usage_record(
                target=target,
                source=source,
                record=record,
            )
        except (CliError, json.JSONDecodeError, TypeError, ValueError) as exc:
            target_state.status = "error"
            target_state.setup_message = None
            target_state.account_status = None
            target_state.error = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
            return
        target_state.status = "ok"
        target_state.setup_message = None
        target_state.account_status = account_status
        target_state.error = None

    def _workflow_state(self, state: MonitorState) -> LimitsWorkflowState:
        existing = state.data.get(self.name)
        if isinstance(existing, LimitsWorkflowState):
            return existing
        workflow_state = LimitsWorkflowState()
        state.data[self.name] = workflow_state
        return workflow_state

    def _target_state(
        self,
        workflow_state: LimitsWorkflowState,
        *,
        target: MonitorTarget,
        target_key: str,
    ) -> LimitsTargetState:
        existing = workflow_state.targets.get(target_key)
        if existing is not None:
            return existing
        target_state = _new_target_state(target, start_path=self.config.start_path)
        workflow_state.targets[target_key] = target_state
        return target_state

    def _refresh_target(
        self,
        target_state: LimitsTargetState,
        *,
        target: MonitorTarget,
        tick: int,
    ) -> None:
        target_state.last_refresh_tick = tick
        target_state.refresh_count += 1
        try:
            agent = resolve_account_runtime_agent(
                provider=target.provider,
                account=target.account,
                home=target.home,
                profile=target.profile,
                start_path=_runtime_start_path(self.config.start_path),
            )
            account_status = agent.account_status()
        except Exception as exc:
            target_state.status = "error"
            target_state.account_status = None
            target_state.error = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
            return
        target_state.status = "ok"
        target_state.account_status = account_status.summary()
        target_state.error = None

    def _refresh_codex_estimated_burst_state(
        self,
        workflow_state: LimitsWorkflowState,
    ) -> None:
        codex_targets = [
            target for target in self.config.targets if target.provider == "codex"
        ]
        if not codex_targets:
            workflow_state.codex_estimated_burst = None
            workflow_state.codex_estimated_burst_targets.clear()
            return
        registry_records = _codex_usage_registry_records()
        estimate = _codex_estimated_burst_weekly_percent(registry_records)
        if estimate is None:
            estimate = _CODEX_ESTIMATED_BURST_FALLBACK_WEEKLY_PERCENT
        now = datetime.datetime.now(tz=datetime.UTC)
        window_start, reset_at = _fixed_local_5h_window(recorded_at=now)
        workflow_state.codex_estimated_burst = {
            "weekly_percent": estimate,
            "computed_at": now.isoformat(),
            "source": "usage-registry",
            "window": "fixed-local-5h",
            "window_start_at": window_start.isoformat(),
            "reset_at": reset_at.isoformat(),
        }
        workflow_state.codex_estimated_burst_targets = (
            _codex_estimated_burst_target_states(
                targets=codex_targets,
                workflow_state=workflow_state,
                records=registry_records,
                burst_weekly_percent=estimate,
                recorded_at=now,
                window_start=window_start,
                reset_at=reset_at,
            )
        )

    def _write_frame_block(
        self,
        frame: MonitorFrame,
        *,
        state: MonitorState,
        workflow_state: LimitsWorkflowState,
    ) -> None:
        _sync_weekly_usage_baselines(
            workflow_state=workflow_state,
            targets=self.config.targets,
            recorded_at=datetime.datetime.now(tz=datetime.UTC),
        )
        rows: list[MonitorRow] = []
        target_summaries: list[dict[str, object]] = []
        for index, target in enumerate(self.config.targets):
            if index > 0:
                rows.append(MonitorTextRow(""))
            target_key = _target_key(target)
            target_state = workflow_state.targets.get(target_key)
            if target_state is None:
                target_state = _new_target_state(
                    target, start_path=self.config.start_path
                )
            auto_prime_target_state = _auto_prime_target_state(
                state, target_key=target_key
            )
            target_summaries.append(target_state.payload())
            rows.extend(
                _target_rows(
                    target=target,
                    target_state=target_state,
                    target_key=target_key,
                    workflow_state=workflow_state,
                    auto_prime_target_state=auto_prime_target_state,
                )
            )
        data = {
            "workflow": self.name,
            "periodic_alarm_name": LIMITS_TRACKING_PERIODIC_ALARM,
            "refresh_interval_sec": self.config.refresh_interval_sec,
            "run_count": workflow_state.run_count,
            "targets": target_summaries,
        }
        frame.add_block(self.name, rows=rows, data=data)


def _new_target_state(
    target: MonitorTarget, *, start_path: Path | None = None
) -> LimitsTargetState:
    return LimitsTargetState(
        provider=target.provider,
        account=target.account,
        home=str(target.home),
        profile=target.profile,
        start_path=str(start_path) if start_path is not None else None,
    )


def _runtime_start_path(start_path: Path | None) -> Path:
    if start_path is not None:
        return start_path
    return Path.cwd().resolve()


def _usage_record_source_for_target(target: MonitorTarget) -> str | None:
    if target.provider == "codex":
        return CODEX_APP_SERVER_USAGE_SOURCE
    if target.provider == "claude-code":
        return CLAUDE_STATUSLINE_USAGE_SOURCE
    if target.provider == "copilot-cli":
        return COPILOT_INTERNAL_USER_USAGE_SOURCE
    return None


def _usage_record_limit_parser(
    source: str,
) -> Callable[[Mapping[str, Any]], tuple[AccountLimit, ...]]:
    if source == CODEX_APP_SERVER_USAGE_SOURCE:
        return codex_usage_record_limits
    if source == CLAUDE_STATUSLINE_USAGE_SOURCE:
        return claude_statusline_usage_record_limits
    if source == COPILOT_INTERNAL_USER_USAGE_SOURCE:
        return copilot_usage_record_limits
    raise CliError(f"unsupported monitor usage record source {source!r}")


def _codex_usage_registry_records() -> list[dict[str, object]]:
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
                weekly = _codex_weekly_limit_from_payload(record.get("payload"))
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


def _codex_weekly_limit_from_payload(payload: object) -> tuple[str, int] | None:
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


def _codex_estimated_burst_weekly_percent(
    records: list[dict[str, object]],
) -> float | None:
    estimates: list[float] = []
    for threshold in _CODEX_ESTIMATED_BURST_THRESHOLDS:
        deltas = _codex_flat_range_deltas(records, min_flat_duration=threshold)
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


def _codex_estimated_burst_target_states(
    *,
    targets: list[MonitorTarget],
    workflow_state: LimitsWorkflowState,
    records: list[dict[str, object]],
    burst_weekly_percent: float,
    recorded_at: datetime.datetime,
    window_start: datetime.datetime,
    reset_at: datetime.datetime,
) -> dict[str, dict[str, object]]:
    grouped = _codex_records_by_target(records)
    target_states: dict[str, dict[str, object]] = {}
    for target in targets:
        target_key = _target_key(target)
        target_state = workflow_state.targets.get(target_key)
        if target_state is None or not isinstance(target_state.account_status, dict):
            continue
        current = _weekly_usage_point(target_state.account_status)
        if current is None:
            continue
        period_key, current_used_percent = current
        target_records = [
            record
            for record in grouped.get(target_key, [])
            if record["reset_at"] == period_key
        ]
        baseline = _nearest_codex_record(
            target_records,
            target=window_start,
        )
        if baseline is None:
            continue
        if (
            abs(baseline["recorded_at"] - window_start)
            > _CODEX_ESTIMATED_BURST_START_TOLERANCE
        ):
            continue
        weekly_delta = max(0, current_used_percent - baseline["used_percent"])
        estimated_used = round((weekly_delta / burst_weekly_percent) * 100)
        elapsed_percent = _estimated_burst_elapsed_percent(
            recorded_at=recorded_at,
            reset_at=reset_at,
        )
        target_states[target_key] = {
            "used_percent": estimated_used,
            "elapsed_percent": elapsed_percent,
            "weekly_delta": weekly_delta,
            "burst_weekly_percent": burst_weekly_percent,
            "baseline_recorded_at": baseline["recorded_at"].isoformat(),
            "baseline_used_percent": baseline["used_percent"],
            "reset_value": reset_at.astimezone().strftime("%a %m-%d %H:%M"),
            "reset_suffix": _format_remaining_duration(
                int((reset_at - recorded_at).total_seconds())
            ),
        }
    return target_states


def _fixed_local_5h_window(
    *,
    recorded_at: datetime.datetime,
) -> tuple[datetime.datetime, datetime.datetime]:
    local_now = recorded_at.astimezone()
    local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    minutes_since_midnight = int((local_now - local_midnight).total_seconds() // 60)
    bucket_minutes = int(_CODEX_ESTIMATED_BURST_WINDOW.total_seconds() // 60)
    bucket_index = minutes_since_midnight // bucket_minutes
    local_start = local_midnight + datetime.timedelta(
        minutes=bucket_index * bucket_minutes
    )
    local_reset = local_start + _CODEX_ESTIMATED_BURST_WINDOW
    return local_start.astimezone(datetime.UTC), local_reset.astimezone(datetime.UTC)


def _estimated_burst_elapsed_percent(
    *,
    recorded_at: datetime.datetime,
    reset_at: datetime.datetime,
) -> int:
    start_at = reset_at - _CODEX_ESTIMATED_BURST_WINDOW
    elapsed = (recorded_at - start_at).total_seconds()
    duration = _CODEX_ESTIMATED_BURST_WINDOW.total_seconds()
    return round(max(0.0, min(1.0, elapsed / duration)) * 100)


def _codex_flat_range_deltas(
    records: list[dict[str, object]],
    *,
    min_flat_duration: datetime.timedelta,
) -> list[int]:
    grouped = _codex_records_by_target(records)
    deltas: list[int] = []
    for target_records in grouped.values():
        for flat_start, _flat_end in _codex_flat_ranges(
            target_records,
            min_flat_duration=min_flat_duration,
        ):
            baseline = _nearest_codex_record(
                target_records,
                target=flat_start["recorded_at"] - _CODEX_ESTIMATED_BURST_WINDOW,
            )
            if baseline is None:
                continue
            if (
                abs(baseline["recorded_at"] - (flat_start["recorded_at"] - _CODEX_ESTIMATED_BURST_WINDOW))
                > _CODEX_ESTIMATED_BURST_START_TOLERANCE
            ):
                continue
            if baseline["reset_at"] != flat_start["reset_at"]:
                continue
            delta = flat_start["used_percent"] - baseline["used_percent"]
            if delta >= 0:
                deltas.append(delta)
    return deltas


def _codex_records_by_target(
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


def _codex_flat_ranges(
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


def _nearest_codex_record(
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


def _account_status_summary_from_usage_record(
    *,
    target: MonitorTarget,
    source: str,
    record: Mapping[str, Any],
) -> dict[str, object]:
    payload = record.get("payload")
    if not isinstance(payload, dict):
        raise CliError("usage registry record payload must be an object")
    limits = _usage_record_limit_parser(source)(payload)
    status = AccountStatus(
        provider=target.provider,
        account=target.account,
        home=target.home,
        check_status="ok",
        usage_status="ok",
        auth_state="registry_latest",
        expected_identity=AccountIdentity(),
        fetched_identity=None,
        identity_match="unknown",
        usage_summary=_limits_summary(
            {"limits": [limit.summary() for limit in limits]}
        ),
        limits=limits,
        raw={
            "usage": payload,
            "usage_record": registry_latest_usage_record_metadata(
                source=source,
                recorded_at=_string_value(record.get("recorded_at")),
            ),
        },
    )
    return status.summary()


def _target_rows(
    *,
    target: MonitorTarget,
    target_state: LimitsTargetState,
    target_key: str | None = None,
    workflow_state: LimitsWorkflowState | None = None,
    auto_prime_target_state: AutoPrimeTargetState | None = None,
) -> list[MonitorRow]:
    account_status = target_state.account_status
    status_parts = _account_status_parts(
        target_state=target_state,
        account_status=account_status,
        auto_prime_target_state=auto_prime_target_state,
    )
    rows: list[MonitorRow] = [
        MonitorAccountRow(
            label=f"  {_target_title(target)}",
            status=" · ".join(status_parts) if status_parts else None,
        )
    ]
    if target_state.status == "error":
        rows.append(
            MonitorInfoRow(label="    error", value=_error_message(target_state))
        )
        return rows
    if isinstance(account_status, dict):
        limit_rows = _account_limit_rows(
            account_status,
            provider=target.provider,
            target_key=target_key,
            workflow_state=workflow_state,
        )
        if limit_rows:
            rows.extend(limit_rows)
            fetch_error_row = _fetch_error_row(account_status)
            if fetch_error_row is not None:
                rows.append(fetch_error_row)
            return rows
        rows.append(
            MonitorInfoRow(label="    usage", value=_limits_summary(account_status))
        )
        return rows
    if target_state.setup_message:
        rows.append(MonitorInfoRow(label="    usage", value=target_state.setup_message))
    return rows


def _target_title(target: MonitorTarget) -> str:
    prefix = "⬢ " if target.provider == "codex" else ""
    return f"{prefix}{target.provider}/{target.account}:"


def _error_message(target_state: LimitsTargetState) -> str:
    error = target_state.error
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message:
            return message
    return "unknown error"


def _account_status_parts(
    *,
    target_state: LimitsTargetState,
    account_status: dict[str, Any] | None,
    auto_prime_target_state: AutoPrimeTargetState | None,
) -> tuple[str, ...]:
    parts: list[str] = []
    fetch_part = _usage_refresh_status_part(
        target_state=target_state,
        account_status=account_status,
    )
    if fetch_part is not None:
        parts.append(fetch_part)
    auto_prime_part = _auto_prime_status_part(auto_prime_target_state)
    if auto_prime_part is not None:
        parts.append(auto_prime_part)
    return tuple(parts)


def _account_limit_rows(
    account_status: dict[str, Any],
    *,
    provider: str,
    target_key: str | None = None,
    workflow_state: LimitsWorkflowState | None = None,
) -> list[MonitorRow]:
    limits = account_status.get("limits")
    if not isinstance(limits, list):
        return []

    rows: list[MonitorRow] = []
    now = datetime.datetime.now(tz=datetime.UTC)
    has_reported_burst = _has_reported_burst_limit(limits)
    for limit in limits:
        if not isinstance(limit, dict):
            continue
        usage_over_time = limit.get("usage_over_time")
        if not isinstance(usage_over_time, dict):
            continue
        used_percent = _int_value(usage_over_time.get("used_percent"))
        elapsed_percent = _elapsed_percent(usage_over_time, recorded_at=now)
        if used_percent is None or elapsed_percent is None:
            continue
        label = _limit_label(limit, usage_over_time)
        estimated_burst = _codex_estimated_burst_row_data(
            provider=provider,
            target_key=target_key,
            workflow_state=workflow_state,
            usage_over_time=usage_over_time,
            has_reported_burst=has_reported_burst,
        )
        if estimated_burst is not None:
            rows.extend(_codex_estimated_burst_rows(estimated_burst))
        ratio = _usage_time_ratio(used_percent, elapsed_percent)
        value = _usage_time_value(
            used_percent=used_percent,
            elapsed_percent=elapsed_percent,
            ratio=ratio,
        )
        row_label = "    usage/time"
        variants: tuple[MonitorColumnVariant, ...] = ()
        burst_unit = _weekly_burst_unit_summary(
            provider=provider,
            limit=limit,
            usage_over_time=usage_over_time,
            used_percent=used_percent,
            recorded_at=now,
            target_key=target_key,
            workflow_state=workflow_state,
        )
        if burst_unit is not None:
            burst_value = burst_unit.get("value")
            if isinstance(burst_value, str):
                variants = (
                    MonitorColumnVariant(
                        label="    usage/time [used]",
                        value=value,
                    ),
                    MonitorColumnVariant(
                        label="    time/usage [left]",
                        value=burst_value,
                    ),
                )
                row_label = variants[0].label
        rows.append(
            MonitorUsageTimeRow(
                label=row_label,
                value=value,
                suffix=label,
                used_percent=max(0, min(100, used_percent)),
                elapsed_percent=max(0, min(100, elapsed_percent)),
                ratio=ratio,
                variants=variants,
                burst_unit=burst_unit,
            )
        )
        reset_columns = _reset_columns(usage_over_time, recorded_at=now)
        if reset_columns is not None:
            marker_percent = (
                max(0, min(100, used_percent))
                if used_percent > elapsed_percent
                else None
            )
            reset_value = reset_columns[0]
            delta_marker = (
                _weekly_usage_delta_marker(
                    usage_over_time=usage_over_time,
                    target_key=target_key,
                    workflow_state=workflow_state,
                    used_percent=used_percent,
                )
                if _is_weekly_limit(limit, usage_over_time)
                else None
            )
            if delta_marker is not None:
                reset_value = f"{reset_value} {delta_marker}"
            rows.append(
                MonitorResetRow(
                    label="        resets",
                    value=reset_value,
                    suffix=reset_columns[1],
                    elapsed_percent=max(0, min(100, elapsed_percent)),
                    marker_percent=marker_percent,
                )
            )
    return rows


def _usage_refresh_status_part(
    *,
    target_state: LimitsTargetState,
    account_status: dict[str, Any] | None,
) -> str | None:
    if target_state.status == "error":
        return "error"
    if account_status is None:
        return None
    raw = account_status.get("raw")
    if not isinstance(raw, dict):
        return None
    usage_record = raw.get("usage_record")
    if not isinstance(usage_record, dict):
        return None
    status = usage_record.get("status")
    if status == USAGE_RECORD_STATUS_FRESH:
        return "fresh"
    if status not in {
        USAGE_RECORD_STATUS_REGISTRY_FALLBACK,
        USAGE_RECORD_STATUS_REGISTRY_LATEST,
    }:
        return None
    recorded_at = _parse_datetime(_string_value(usage_record.get("recorded_at")))
    if recorded_at is None:
        return None
    age_sec = _int_value(usage_record.get("age_sec"))
    if age_sec is None:
        age_sec = int(
            (datetime.datetime.now(tz=datetime.UTC) - recorded_at).total_seconds()
        )
    label = (
        "fallback"
        if status == USAGE_RECORD_STATUS_REGISTRY_FALLBACK
        else "latest"
    )
    return f"{label} {_format_age_duration(age_sec)} ago"


def _fetch_error_row(account_status: dict[str, Any]) -> MonitorInfoRow | None:
    raw = account_status.get("raw")
    if not isinstance(raw, dict):
        return None
    usage_record = raw.get("usage_record")
    if not isinstance(usage_record, dict):
        return None
    if usage_record.get("status") != USAGE_RECORD_STATUS_REGISTRY_FALLBACK:
        return None
    live_error = usage_record.get("live_error")
    if not isinstance(live_error, dict):
        return None
    message = live_error.get("message")
    if not isinstance(message, str) or not message:
        return None
    retry_suffix = _fetch_error_retry_suffix(live_error)
    if retry_suffix is not None:
        message = f"{message} [{retry_suffix}]"
    return MonitorInfoRow(label="        fetch error", value=message)


def _fetch_error_retry_suffix(live_error: dict[str, object]) -> str | None:
    detail = live_error.get("detail")
    if not isinstance(detail, dict):
        return None
    remaining_sec = _int_value(detail.get("retry_after_remaining_sec"))
    if remaining_sec is None:
        retry_after_until = _parse_datetime(
            _string_value(detail.get("retry_after_until"))
        )
        if retry_after_until is None:
            return None
        remaining_sec = int(
            (retry_after_until - datetime.datetime.now(tz=datetime.UTC)).total_seconds()
        )
    if remaining_sec <= 0:
        return None
    return f"retry in {_format_age_duration(remaining_sec)}"


def _usage_time_value(
    *, used_percent: int, elapsed_percent: int, ratio: float | None
) -> str:
    return (
        f"{_format_usage_percent_plain(used_percent)} / {_format_usage_percent_plain(elapsed_percent)}"
        f" = {_format_usage_time_ratio_text(ratio)} [%]"
    )


def _weekly_burst_unit_summary(
    *,
    provider: str,
    limit: dict[str, Any],
    usage_over_time: dict[str, object],
    used_percent: int,
    recorded_at: datetime.datetime,
    target_key: str | None = None,
    workflow_state: LimitsWorkflowState | None = None,
) -> dict[str, object] | None:
    weekly_burst_percent = _weekly_burst_percent(
        provider=provider,
        target_key=target_key,
        workflow_state=workflow_state,
    )
    if weekly_burst_percent is None or not _is_weekly_limit(limit, usage_over_time):
        return None
    time_burst_units_left = _remaining_burst_windows(
        usage_over_time,
        recorded_at=recorded_at,
    )
    if time_burst_units_left is None:
        return None
    usage_burst_units_left = max(0, 100 - min(100, used_percent)) / weekly_burst_percent
    left_ratio = _usage_time_left_ratio(
        usage_burst_units_left=usage_burst_units_left,
        time_burst_units_left=time_burst_units_left,
    )
    return {
        "unit": "Burst",
        "weekly_burst_percent": weekly_burst_percent,
        "usage_burst_units_left": usage_burst_units_left,
        "time_burst_units_left": time_burst_units_left,
        "left_ratio": left_ratio,
        "value": _usage_time_burst_unit_value(
            usage_burst_units_left=usage_burst_units_left,
            time_burst_units_left=time_burst_units_left,
            ratio=left_ratio,
        ),
    }


def _weekly_burst_percent(
    *,
    provider: str,
    target_key: str | None,
    workflow_state: LimitsWorkflowState | None,
) -> float | None:
    if provider == "codex":
        if target_key is None or workflow_state is None:
            return None
        estimate = workflow_state.codex_estimated_burst
        if not isinstance(estimate, dict):
            return None
        weekly_percent = estimate.get("weekly_percent")
        if isinstance(weekly_percent, int | float) and weekly_percent > 0:
            return float(weekly_percent)
        return None
    return _WEEKLY_BURST_PERCENT_BY_PROVIDER.get(provider)


def _is_weekly_limit(
    limit: dict[str, Any], usage_over_time: dict[str, object]
) -> bool:
    limit_id = _string_value(limit.get("limit_id"))
    if limit_id == "weekly":
        return True
    return _int_value(usage_over_time.get("period_duration_mins")) == 10_080


def _sync_weekly_usage_baselines(
    *,
    workflow_state: LimitsWorkflowState,
    targets: tuple[MonitorTarget, ...],
    recorded_at: datetime.datetime,
) -> None:
    active_keys: set[str] = set()
    observed_target_keys: set[str] = set()
    for target in targets:
        target_key = _target_key(target)
        target_state = workflow_state.targets.get(target_key)
        if target_state is None or not isinstance(target_state.account_status, dict):
            continue
        point = _weekly_usage_point(target_state.account_status)
        if point is None:
            continue
        period_key, used_percent = point
        baseline_key = _weekly_usage_baseline_key(
            target_key=target_key,
            period_key=period_key,
        )
        observed_target_keys.add(target_key)
        active_keys.add(baseline_key)
        workflow_state.weekly_usage_baselines.setdefault(
            baseline_key,
            {
                "used_percent": used_percent,
                "recorded_at": recorded_at.isoformat(),
            },
        )

    stale_keys = [
        key
        for key in workflow_state.weekly_usage_baselines
        if key not in active_keys
        and _weekly_usage_baseline_target_key(key) in observed_target_keys
    ]
    for key in stale_keys:
        del workflow_state.weekly_usage_baselines[key]


def _weekly_usage_delta_marker(
    *,
    usage_over_time: dict[str, object],
    target_key: str | None,
    workflow_state: LimitsWorkflowState | None,
    used_percent: int,
) -> str | None:
    if target_key is None or workflow_state is None:
        return None
    period_key = _weekly_usage_period_key(usage_over_time)
    if period_key is None:
        return None
    baseline = workflow_state.weekly_usage_baselines.get(
        _weekly_usage_baseline_key(target_key=target_key, period_key=period_key)
    )
    if baseline is None:
        return None
    baseline_used = _int_value(baseline.get("used_percent"))
    if baseline_used is None:
        return None
    return f"[{used_percent - baseline_used:+d}%]"


def _codex_estimated_burst_row_data(
    *,
    provider: str,
    target_key: str | None,
    workflow_state: LimitsWorkflowState | None,
    usage_over_time: dict[str, object],
    has_reported_burst: bool,
) -> dict[str, object] | None:
    if provider != "codex" or target_key is None or workflow_state is None:
        return None
    if has_reported_burst:
        return None
    if _int_value(usage_over_time.get("period_duration_mins")) != 10_080:
        return None
    target = workflow_state.codex_estimated_burst_targets.get(target_key)
    if not isinstance(target, dict):
        return None
    return target


def _has_reported_burst_limit(limits: list[object]) -> bool:
    for limit in limits:
        if not isinstance(limit, dict):
            continue
        usage_over_time = limit.get("usage_over_time")
        if not isinstance(usage_over_time, dict):
            continue
        if _int_value(usage_over_time.get("period_duration_mins")) == 300:
            return True
    return False


def _codex_estimated_burst_rows(data: dict[str, object]) -> list[MonitorRow]:
    used_percent = _int_value(data.get("used_percent"))
    elapsed_percent = _int_value(data.get("elapsed_percent"))
    reset_value = _string_value(data.get("reset_value"))
    reset_suffix = _string_value(data.get("reset_suffix"))
    if used_percent is None or elapsed_percent is None or reset_value is None:
        return []
    ratio = _usage_time_ratio(used_percent, elapsed_percent)
    return [
        MonitorUsageTimeRow(
            label="    usage/time",
            value=_usage_time_value(
                used_percent=used_percent,
                elapsed_percent=elapsed_percent,
                ratio=ratio,
            ),
            suffix="~Burst",
            used_percent=max(0, min(100, used_percent)),
            elapsed_percent=max(0, min(100, elapsed_percent)),
            ratio=ratio,
        ),
        MonitorResetRow(
            label="        resets",
            value=reset_value,
            suffix=reset_suffix,
            elapsed_percent=max(0, min(100, elapsed_percent)),
            marker_percent=max(0, min(100, used_percent))
            if used_percent > elapsed_percent
            else None,
        ),
    ]


def _weekly_usage_point(account_status: dict[str, Any]) -> tuple[str, int] | None:
    limits = account_status.get("limits")
    if not isinstance(limits, list):
        return None
    for limit in limits:
        if not isinstance(limit, dict):
            continue
        usage_over_time = limit.get("usage_over_time")
        if not isinstance(usage_over_time, dict):
            continue
        if not _is_weekly_limit(limit, usage_over_time):
            continue
        used_percent = _int_value(usage_over_time.get("used_percent"))
        period_key = _weekly_usage_period_key(usage_over_time)
        if used_percent is not None and period_key is not None:
            return period_key, used_percent
    return None


def _weekly_usage_period_key(usage_over_time: dict[str, object]) -> str | None:
    period_end = _parse_datetime(_string_value(usage_over_time.get("period_ends_at")))
    if period_end is None:
        period_end = _parse_datetime(_string_value(usage_over_time.get("resets_at")))
    if period_end is None:
        return None
    return period_end.isoformat()


def _weekly_usage_baseline_key(*, target_key: str, period_key: str) -> str:
    return f"{target_key}|weekly|{period_key}"


def _weekly_usage_baseline_target_key(baseline_key: str) -> str:
    return baseline_key.split("|weekly|", 1)[0]


def _usage_time_burst_unit_value(
    *,
    usage_burst_units_left: float,
    time_burst_units_left: float,
    ratio: float | None,
) -> str:
    return (
        f"{time_burst_units_left:.1f} / {usage_burst_units_left:.1f}"
        f" = {_format_usage_time_ratio_text(ratio)} [Burst]"
    )


def _remaining_burst_windows(
    usage_over_time: dict[str, object], *, recorded_at: datetime.datetime
) -> float | None:
    period_ends_at = _parse_datetime(_string_value(usage_over_time.get("period_ends_at")))
    if period_ends_at is None:
        period_ends_at = _parse_datetime(_string_value(usage_over_time.get("resets_at")))
    if period_ends_at is None:
        return None
    remaining_seconds = max(0.0, (period_ends_at - recorded_at).total_seconds())
    return remaining_seconds / (300 * 60)


def _usage_time_left_ratio(
    *,
    usage_burst_units_left: float,
    time_burst_units_left: float,
) -> float | None:
    if usage_burst_units_left <= 0:
        return None
    return time_burst_units_left / usage_burst_units_left


def _limits_summary(account_status: dict[str, Any]) -> str:
    usage_summary = account_status.get("usage_summary")
    if isinstance(usage_summary, str) and usage_summary:
        return usage_summary
    usage_error = _usage_error_message(account_status)
    if usage_error is not None:
        return f"error | {usage_error}"
    limits = account_status.get("limits")
    if not isinstance(limits, list) or not limits:
        return "none"
    summaries: list[str] = []
    for limit in limits:
        if not isinstance(limit, dict):
            continue
        label = limit.get("limit_label") or limit.get("limit_name")
        usage = limit.get("usage_over_time")
        if isinstance(label, str) and isinstance(usage, dict):
            used_percent = usage.get("used_percent")
            if isinstance(used_percent, int | float):
                summaries.append(f"{label} {used_percent}%")
    if summaries:
        return ", ".join(summaries)
    return "unknown"


def _usage_error_message(account_status: dict[str, Any]) -> str | None:
    usage_errors = account_status.get("usage_errors")
    if not isinstance(usage_errors, list) or not usage_errors:
        return None
    first_error = usage_errors[0]
    if not isinstance(first_error, dict):
        return "unknown usage error"
    message = first_error.get("message")
    if isinstance(message, str) and message:
        return message
    error_type = first_error.get("type")
    if isinstance(error_type, str) and error_type:
        return error_type
    return "unknown usage error"


def _limit_label(limit: dict[str, Any], usage_over_time: dict[str, object]) -> str:
    duration_mins = _int_value(usage_over_time.get("period_duration_mins"))
    if duration_mins == 300:
        return "Burst"
    if duration_mins == 10_080:
        return "Weekly"
    label = limit.get("limit_label") or limit.get("limit_name")
    if isinstance(label, str) and label:
        return label
    return "usage"


def _reset_columns(
    usage_over_time: dict[str, object], *, recorded_at: datetime.datetime
) -> tuple[str, str | None] | None:
    reset_at = _parse_datetime(_string_value(usage_over_time.get("resets_at")))
    if reset_at is None:
        reset_at = _parse_datetime(_string_value(usage_over_time.get("period_ends_at")))
    if reset_at is None:
        return None
    reset_display = reset_at.astimezone().strftime("%a %m-%d %H:%M")
    remaining_display = _format_remaining_duration(
        int((reset_at - recorded_at).total_seconds())
    )
    return reset_display, remaining_display


def _elapsed_percent(
    usage_over_time: dict[str, object], *, recorded_at: datetime.datetime
) -> int | None:
    period_started_at = _parse_datetime(
        _string_value(usage_over_time.get("period_started_at"))
    )
    period_ends_at = _parse_datetime(
        _string_value(usage_over_time.get("period_ends_at"))
    )
    if period_started_at is None:
        duration_mins = _int_value(usage_over_time.get("period_duration_mins"))
        if duration_mins is not None and period_ends_at is not None:
            period_started_at = period_ends_at - datetime.timedelta(
                minutes=duration_mins
            )
    if period_ends_at is None:
        period_ends_at = _parse_datetime(
            _string_value(usage_over_time.get("resets_at"))
        )
    if (
        period_started_at is None
        or period_ends_at is None
        or period_ends_at <= period_started_at
    ):
        return None
    duration_seconds = (period_ends_at - period_started_at).total_seconds()
    if duration_seconds <= 0:
        return None
    elapsed_seconds = (recorded_at - period_started_at).total_seconds()
    elapsed_ratio = max(0.0, min(1.0, elapsed_seconds / duration_seconds))
    return round(elapsed_ratio * 100)


def _format_usage_percent_plain(value: int) -> str:
    return f"{max(0, min(100, value))}%".rjust(3)


def _usage_time_ratio(used_percent: int, elapsed_percent: int) -> float | None:
    clamped_elapsed_percent = max(0, min(100, elapsed_percent))
    if clamped_elapsed_percent == 0:
        return None
    clamped_used_percent = max(0, min(100, used_percent))
    return clamped_used_percent / clamped_elapsed_percent


def _format_usage_time_ratio_text(ratio: float | None) -> str:
    if ratio is None:
        return "n/a"
    return f"{ratio:.1f}"
