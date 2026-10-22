"""Auto-prime workflow: ping each configured target whose burst window is not running."""

from __future__ import annotations

import datetime
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l1.agent.account_status import BURST_LIMIT_ID
from tarav.l1.agent.monitor.clock import (
    AUTO_PRIME_ZERO_LIMITS_PERIODIC_ALARM,
    MonitorClockSnapshot,
)
from tarav.l1.agent.monitor.models import (
    AUTO_PRIME_DEFAULT_THRESHOLD_PERCENT,
    AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
    LIMITS_TRACKING_WORKFLOW,
    MonitorFrame,
    MonitorInfoRow,
    MonitorRow,
    MonitorState,
    MonitorWorkflowConfig,
)
from tarav.l1.agent.monitor.workflows.state import (
    AutoPrimeTargetState,
    AutoPrimeWorkflowState,
    LimitsTargetState,
    LimitsWorkflowState,
)
from tarav.l1.agent.monitor.workflows._common import (
    _format_age_duration,
    _int_value,
    _parse_datetime,
    _string_value,
    _target_key,
)
from tarav.l1.agent.monitor_log import append_monitor_log_event
from tarav.l1.agent.ping import AgentPingResult
from tarav.l1.agent.providers.registry import resolve_account_runtime_agent


# tarav.breadcrumb cbc3ba5f3f3c
class AutoPrimeZeroLimitsWorkflow:
    """Every interval, ping each target whose burst window is not running.

    The reading is the limits-tracking state for the same target; a target without
    an ok burst reading is skipped. A window is not running when it has no reset,
    its reset has passed, or less than ``threshold_percent`` of its duration has
    elapsed (an idle window that keeps sliding forward). After a ping starts the
    window, elapsed time grows past the threshold and the target is left alone
    until the window resets."""

    name = AUTO_PRIME_ZERO_LIMITS_WORKFLOW
    periodic_alarm_name = AUTO_PRIME_ZERO_LIMITS_PERIODIC_ALARM

    def __init__(self, config: MonitorWorkflowConfig) -> None:
        self.config = config
        self.refresh_interval_sec = config.refresh_interval_sec
        self.threshold_percent = (
            config.threshold_percent
            if config.threshold_percent is not None
            else AUTO_PRIME_DEFAULT_THRESHOLD_PERCENT
        )

    def setup(self, state: MonitorState, frame: MonitorFrame) -> None:
        workflow_state = self._workflow_state(state)
        workflow_state.setup_tick = frame.tick
        self._write_frame_block(frame, workflow_state=workflow_state)

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
        workflow_state.fired_alarms = list(trigger.fired_alarm_names)

        if trigger.fired(AUTO_PRIME_ZERO_LIMITS_PERIODIC_ALARM):
            self._scan_and_prime(state, workflow_state=workflow_state, tick=frame.tick)

        self._write_frame_block(frame, workflow_state=workflow_state)

    def _workflow_state(self, state: MonitorState) -> AutoPrimeWorkflowState:
        existing = state.data.get(self.name)
        if isinstance(existing, AutoPrimeWorkflowState):
            return existing
        workflow_state = AutoPrimeWorkflowState(
            interval_sec=self.refresh_interval_sec,
            threshold_percent=self.threshold_percent,
            loaded_at=self.config.loaded_at,
            config_fingerprint=self.config.config_fingerprint,
            target_summary=[target.summary() for target in self.config.targets],
        )
        state.data[self.name] = workflow_state
        return workflow_state

    def _scan_and_prime(
        self,
        state: MonitorState,
        *,
        workflow_state: AutoPrimeWorkflowState,
        tick: int,
    ) -> None:
        limits_state = state.data.get(LIMITS_TRACKING_WORKFLOW)
        readings = (
            limits_state.targets if isinstance(limits_state, LimitsWorkflowState) else {}
        )
        now = datetime.datetime.now(tz=datetime.UTC)
        pinged = 0
        failed = 0
        for target in self.config.targets:
            target_key = _target_key(target)
            target_state = workflow_state.targets.get(target_key)
            if target_state is None:
                target_state = AutoPrimeTargetState(
                    provider=target.provider,
                    account=target.account,
                    home=str(target.home),
                    profile=target.profile,
                )
                workflow_state.targets[target_key] = target_state
            reading = readings.get(target_key)
            elapsed_percent = _burst_elapsed_percent(reading, now=now)
            target_state.burst_elapsed_percent = elapsed_percent
            if reading is None or elapsed_percent is None:
                continue
            if elapsed_percent >= self.threshold_percent:
                continue
            if self._ping_target(target_state, reading=reading, tick=tick):
                pinged += 1
            else:
                failed += 1
        workflow_state.last_scan = {"tick": tick, "pinged": pinged, "failed": failed}

    def _ping_target(
        self,
        target_state: AutoPrimeTargetState,
        *,
        reading: LimitsTargetState,
        tick: int,
    ) -> bool:
        target_state.last_attempt_tick = tick
        target_state.last_ping_at = datetime.datetime.now(tz=datetime.UTC).isoformat()
        payload: dict[str, object] = {
            "burst_elapsed_percent": target_state.burst_elapsed_percent,
            "threshold_percent": self.threshold_percent,
        }
        try:
            result = _run_account_prime_ping(reading)
        except Exception as exc:
            error = {"message": str(exc), "error_type": type(exc).__name__}
        else:
            payload["ping_model"] = result.model
            payload["ping_elapsed_ms"] = result.elapsed_ms
            error = (
                None
                if result.ok
                else {
                    "message": result.failure or "agent ping failed",
                    "error_type": "ping-failed",
                }
            )
        target_state.last_error = error
        if error is None:
            target_state.last_success_tick = tick
        else:
            payload.update(error)
        append_monitor_log_event(
            event="auto_prime_pinged" if error is None else "auto_prime_failed",
            tick=tick,
            provider=target_state.provider,
            account=target_state.account,
            home=target_state.home,
            payload=payload,
        )
        return error is None

    def _write_frame_block(
        self, frame: MonitorFrame, *, workflow_state: AutoPrimeWorkflowState
    ) -> None:
        rows: list[MonitorRow] = []
        last_scan = workflow_state.last_scan
        if last_scan is not None:
            pinged = _int_value(last_scan.get("pinged"))
            failed = _int_value(last_scan.get("failed"))
            if pinged:
                rows.append(
                    MonitorInfoRow(label="    auto-prime", value=f"pinged {pinged}")
                )
            if failed:
                rows.append(
                    MonitorInfoRow(label="    auto-prime", value=f"failed {failed}")
                )
        for target_state in workflow_state.targets.values():
            last_error = target_state.last_error
            if not isinstance(last_error, dict):
                continue
            message = _string_value(last_error.get("message")) or "unknown error"
            rows.append(
                MonitorInfoRow(
                    label="    auto-prime",
                    value=f"{_target_state_name(target_state)} failed: {message}",
                )
            )
        if not rows and workflow_state.setup_tick is None and last_scan is None:
            return
        data = {
            "workflow": self.name,
            "periodic_alarm_name": AUTO_PRIME_ZERO_LIMITS_PERIODIC_ALARM,
            **workflow_state.payload(),
        }
        frame.add_block(self.name, rows=rows, data=data)


def _burst_elapsed_percent(
    reading: LimitsTargetState | None, *, now: datetime.datetime
) -> float | None:
    """Percent of the burst window elapsed at ``now``; 0 when no window is running."""
    usage_over_time = _burst_usage_over_time(reading)
    if usage_over_time is None:
        return None
    resets_at = _parse_datetime(
        _string_value(usage_over_time.get("resets_at"))
        or _string_value(usage_over_time.get("period_ends_at"))
    )
    if resets_at is None or resets_at <= now:
        return 0.0
    duration_mins = _int_value(usage_over_time.get("period_duration_mins"))
    if not duration_mins:
        return None
    started_at = resets_at - datetime.timedelta(minutes=duration_mins)
    elapsed_sec = max((now - started_at).total_seconds(), 0.0)
    return round(elapsed_sec / (duration_mins * 60) * 100, 1)


def _burst_usage_over_time(
    reading: LimitsTargetState | None,
) -> dict[str, object] | None:
    if reading is None or reading.status != "ok":
        return None
    account_status = reading.account_status
    if not isinstance(account_status, dict):
        return None
    limits = account_status.get("limits")
    if not isinstance(limits, list):
        return None
    for limit in limits:
        if not isinstance(limit, dict) or limit.get("limit_id") != BURST_LIMIT_ID:
            continue
        usage_over_time = limit.get("usage_over_time")
        return usage_over_time if isinstance(usage_over_time, dict) else None
    return None


def _auto_prime_target_state(
    state: MonitorState, *, target_key: str
) -> AutoPrimeTargetState | None:
    workflow_state = state.data.get(AUTO_PRIME_ZERO_LIMITS_WORKFLOW)
    if not isinstance(workflow_state, AutoPrimeWorkflowState):
        return None
    return workflow_state.targets.get(target_key)


def _auto_prime_status_part(target_state: AutoPrimeTargetState | None) -> str | None:
    if target_state is None:
        return None
    pinged_at = _parse_datetime(target_state.last_ping_at)
    if pinged_at is None:
        return None
    age_sec = int((datetime.datetime.now(tz=datetime.UTC) - pinged_at).total_seconds())
    outcome = "ping ok" if target_state.last_error is None else "ping failed"
    age = "just now" if age_sec < 60 else f"{_format_age_duration(age_sec)} ago"
    return f"{outcome} {age}"


def _run_account_prime_ping(reading: LimitsTargetState) -> AgentPingResult:
    agent = resolve_account_runtime_agent(
        provider=_required_target_string(reading.provider, "provider"),
        account=_required_target_string(reading.account, "account"),
        home=Path(_required_target_string(reading.home, "home")),
        profile=reading.profile,
        start_path=Path(reading.start_path or "."),
    )
    return agent.ping(cwd=Path.cwd().resolve())


def _required_target_string(value: str | None, key: str) -> str:
    if not value:
        raise CliError(f"limits-tracking target state is missing {key}")
    return value


def _target_state_name(target_state: AutoPrimeTargetState) -> str:
    provider = target_state.provider or "unknown"
    account = target_state.account or "unknown"
    return f"{provider}/{account}"
