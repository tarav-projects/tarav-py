"""Limits-tracking workflow: usage refresh, transition logging, and limit row rendering."""

from __future__ import annotations

import datetime
import json
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
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
    "codex": 15.7,
    "claude-code": 9.0,
}


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

    def _write_frame_block(
        self,
        frame: MonitorFrame,
        *,
        state: MonitorState,
        workflow_state: LimitsWorkflowState,
    ) -> None:
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
        limit_rows = _account_limit_rows(account_status, provider=target.provider)
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
    account_status: dict[str, Any], *, provider: str
) -> list[MonitorRow]:
    limits = account_status.get("limits")
    if not isinstance(limits, list):
        return []

    rows: list[MonitorRow] = []
    now = datetime.datetime.now(tz=datetime.UTC)
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
            rows.append(
                MonitorResetRow(
                    label="        resets",
                    value=reset_columns[0],
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
) -> dict[str, object] | None:
    weekly_burst_percent = _WEEKLY_BURST_PERCENT_BY_PROVIDER.get(provider)
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


def _is_weekly_limit(
    limit: dict[str, Any], usage_over_time: dict[str, object]
) -> bool:
    limit_id = _string_value(limit.get("limit_id"))
    if limit_id == "weekly":
        return True
    return _int_value(usage_over_time.get("period_duration_mins")) == 10_080


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
