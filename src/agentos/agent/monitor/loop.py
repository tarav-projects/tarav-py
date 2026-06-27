from __future__ import annotations

import math
import time
import datetime
from collections.abc import Callable
from dataclasses import dataclass
from threading import Condition, Event, Thread
from typing import Protocol

from agentos._core.errors import CliError
from agentos.agent.monitor.clock import (
    ACCOUNT_ROTATION_PERIODIC_ALARM,
    AUTO_PRIME_ZERO_LIMITS_PERIODIC_ALARM,
    LIMITS_TRACKING_PERIODIC_ALARM,
    MONITOR_ENTER_ALARM,
    MONITOR_MATERIALIZE_ALARM,
    MONITOR_STARTUP_ALARM,
    MONITOR_USAGE_VARIANT_TOGGLE_ALARM,
    MonitorClock,
    MonitorClockSnapshot,
)
from agentos.agent.monitor.models import (
    MonitorFrame,
    MonitorState,
    MonitorUsageVariant,
)
from agentos.agent.monitor_log import append_monitor_log_event


@dataclass
class _AdaptivePeriodicAlarmState:
    baseline_sec: float
    current_sec: float


class MonitorWorkflow(Protocol):
    name: str

    def setup(
        self,
        state: MonitorState,
        frame: MonitorFrame,
    ) -> None:
        ...

    def loop(
        self,
        state: MonitorState,
        frame: MonitorFrame,
        trigger: MonitorClockSnapshot,
    ) -> None:
        ...


class MonitorLoop:
    # Frame ownership is transferred, not shared. The workflow thread owns
    # working_frame after taking a trigger and until it sets
    # working_frame_ready. The main thread owns visible_frame, and swaps only
    # after working_frame_ready signals that workflow ownership was released.
    # That trigger/ready handshake is why frame access does not need a lock.
    def __init__(
        self,
        *,
        workflows: tuple[MonitorWorkflow, ...],
        interval_sec: float,
        max_ticks: int | None,
        config_fingerprint: str | None = None,
        config_fingerprint_loader: Callable[[], str] | None = None,
    ) -> None:
        if max_ticks is not None and max_ticks < 1:
            raise CliError("--max-ticks must be greater than 0")
        if interval_sec < 0:
            raise CliError("--interval-sec must be greater than or equal to 0")
        self.workflows = workflows
        self.interval_sec = interval_sec
        self.max_ticks = max_ticks
        self.config_fingerprint = config_fingerprint
        self.config_fingerprint_loader = config_fingerprint_loader
        self.clock = MonitorClock()
        self.state = MonitorState()
        self.visible_frame = MonitorFrame()
        self.working_frame = MonitorFrame()
        self.working_frame_ready = Event()
        self.stop_requested = Event()
        self._workflow_thread: Thread | None = None
        self._workflow_condition = Condition()
        self._pending_workflow_snapshot: MonitorClockSnapshot | None = None
        self._workflow_active_count = 0
        self._clock_snapshot = self.clock.snapshot()
        self._has_visible_frame = False
        self._limits_tracking_adaptive_alarm: _AdaptivePeriodicAlarmState | None = None
        self._configure_initial_alarms()
        self._initialize_display_state()
        self._write_monitor_setup_state()

    def run(
        self,
        *,
        on_tick: Callable[[MonitorFrame, MonitorState], None] | None = None,
        wait_for_first_frame: bool = False,
    ) -> tuple[MonitorFrame, MonitorState]:
        self._start_workflow_thread()
        ticks_run = 0
        try:
            while self.max_ticks is None or ticks_run < self.max_ticks:
                started_at = time.monotonic()
                self._clock_snapshot = self._apply_adaptive_alarm_policy(
                    self.clock.step()
                )
                self.state.tick = self._clock_snapshot.tick
                self._check_config_fingerprint()
                workflow_alarm_names = _workflow_alarm_names(
                    self._clock_snapshot.fired_alarm_names
                )
                if workflow_alarm_names:
                    self._queue_workflow_snapshot(
                        self._snapshot_with_fired(workflow_alarm_names)
                    )
                if wait_for_first_frame and self.visible_frame.tick == 0:
                    self.working_frame_ready.wait()
                self._publish_working_frame_if_ready()
                self._prepare_visible_frame_for_render()
                self._apply_display_alarms(self._clock_snapshot)

                if on_tick is not None:
                    on_tick(self.visible_frame, self.state)
                    self.visible_frame.step_animations()

                ticks_run += 1
                if self.max_ticks is None or ticks_run < self.max_ticks:
                    elapsed = time.monotonic() - started_at
                    sleep_for = max(0.0, self.interval_sec - elapsed)
                    if sleep_for:
                        time.sleep(sleep_for)
            self._publish_working_frame_if_ready()
            return self.visible_frame, self.state
        finally:
            self._stop_workflow_thread()

    def set_alarm(self, name: str, *, remaining_ticks: int = 0) -> None:
        self.clock.set_one_shot(name, remaining_ticks=remaining_ticks)

    def _queue_workflow_snapshot(self, snapshot: MonitorClockSnapshot) -> None:
        with self._workflow_condition:
            self._pending_workflow_snapshot = snapshot
            self._workflow_condition.notify()

    def _start_workflow_thread(self) -> None:
        if self._workflow_thread is not None and self._workflow_thread.is_alive():
            return
        self.stop_requested.clear()
        self.working_frame_ready.clear()
        with self._workflow_condition:
            self._pending_workflow_snapshot = None
        self._workflow_thread = Thread(
            target=self._run_workflow_loop,
            name="agentos-monitor-workflows",
            daemon=True,
        )
        self._workflow_thread.start()

    def _publish_working_frame_if_ready(self) -> None:
        if not self.working_frame_ready.is_set():
            return
        self.working_frame.inherit_animation_state_from(self.visible_frame)
        self.visible_frame, self.working_frame = self.working_frame, self.visible_frame
        self._has_visible_frame = True
        self.working_frame_ready.clear()
        with self._workflow_condition:
            self._workflow_condition.notify()

    def _prepare_visible_frame_for_render(self) -> None:
        status_lines: list[str] = []
        if self._workflow_is_active():
            status_lines.append("workflow: fetching account data")
        if not self._has_visible_frame:
            self.visible_frame.prepare(tick=self.state.tick)
            self.visible_frame.status_lines = [
                *status_lines,
                "waiting for workflow frame",
            ]
            return
        self.visible_frame.tick = self.state.tick
        self.visible_frame.status_lines = status_lines
        self._apply_clock_feedback_to_visible_frame()

    def _apply_clock_feedback_to_visible_frame(self) -> None:
        for block in self.visible_frame.blocks:
            data = block.get("data")
            if not isinstance(data, dict):
                continue
            workflow_name = data.get("workflow")
            alarm_name = data.get("periodic_alarm_name")
            if not isinstance(workflow_name, str) or not isinstance(alarm_name, str):
                continue
            alarm = self._clock_snapshot.alarms.get(alarm_name)
            if alarm is None or not alarm.armed:
                block["title"] = workflow_name
                continue
            block["title"] = _workflow_clock_title(
                workflow_name,
                remaining_ticks=alarm.remaining_ticks,
                period_ticks=alarm.period_ticks,
            )

    def _apply_display_alarms(self, snapshot: MonitorClockSnapshot) -> None:
        if snapshot.fired(MONITOR_USAGE_VARIANT_TOGGLE_ALARM):
            self._toggle_usage_variant()
        if snapshot.fired(MONITOR_MATERIALIZE_ALARM):
            # `m` keystroke: full reconcile (writes homes), inline on the UI thread.
            from agentos.agent.monitor.account_rotation import materialize_sweep

            materialize_sweep(self.state)

    def _initialize_display_state(self) -> None:
        self._monitor_display_state()

    def _current_usage_variant(self) -> MonitorUsageVariant:
        display_state = self._monitor_display_state()
        variant = display_state.get("usage_variant")
        if variant == "left":
            return "left"
        return "used"

    def _toggle_usage_variant(self) -> None:
        display_state = self._monitor_display_state()
        display_state["usage_variant"] = (
            "left" if self._current_usage_variant() == "used" else "used"
        )

    def _monitor_display_state(self) -> dict[str, object]:
        display_state = self.state.data.get("monitor_display")
        if not isinstance(display_state, dict):
            display_state = {}
            self.state.data["monitor_display"] = display_state
        if display_state.get("usage_variant") not in {"used", "left"}:
            display_state["usage_variant"] = "used"
        return display_state

    def _workflow_is_active(self) -> bool:
        with self._workflow_condition:
            return self._workflow_active_count > 0

    def _stop_workflow_thread(self) -> None:
        self.stop_requested.set()
        with self._workflow_condition:
            self._workflow_condition.notify()
        thread = self._workflow_thread
        if thread is not None:
            thread.join(timeout=1.0)

    def _run_workflow_loop(self) -> None:
        self._run_workflow_setup()
        while not self.stop_requested.is_set():
            snapshot = self._take_workflow_snapshot()
            if snapshot is None:
                return

            self._set_workflow_active(True)
            frame = self.working_frame
            frame.prepare(tick=snapshot.tick)
            frame.status_lines = [f"tick: {snapshot.tick}"]

            try:
                for workflow in self.workflows:
                    try:
                        workflow.loop(self.state, frame, snapshot)
                    except Exception as exc:
                        self._record_unexpected_workflow_error(
                            frame=frame, workflow=workflow, error=exc, phase="loop"
                        )
            except Exception as exc:
                frame.add_error(
                    f"unexpected workflow loop error: {type(exc).__name__}: {exc}"
                )
            finally:
                self._set_workflow_active(False)

            self.working_frame_ready.set()
            with self._workflow_condition:
                self._workflow_condition.notify()

    def _run_workflow_setup(self) -> None:
        frame = self.working_frame
        frame.prepare(tick=self.state.tick)
        frame.status_lines = [f"tick: {self.state.tick}"]

        try:
            for workflow in self.workflows:
                try:
                    workflow.setup(self.state, frame)
                except Exception as exc:
                    self._record_unexpected_workflow_error(
                        frame=frame, workflow=workflow, error=exc, phase="setup"
                    )
        except Exception as exc:
            frame.add_error(
                f"unexpected workflow setup error: {type(exc).__name__}: {exc}"
            )

        self.working_frame_ready.set()
        with self._workflow_condition:
            self._workflow_condition.notify()

    def _set_workflow_active(self, active: bool) -> None:
        with self._workflow_condition:
            if active:
                self._workflow_active_count += 1
            else:
                self._workflow_active_count = max(0, self._workflow_active_count - 1)

    def _take_workflow_snapshot(self) -> MonitorClockSnapshot | None:
        with self._workflow_condition:
            while not self.stop_requested.is_set():
                if (
                    self._pending_workflow_snapshot is not None
                    and not self.working_frame_ready.is_set()
                ):
                    snapshot = self._pending_workflow_snapshot
                    self._pending_workflow_snapshot = None
                    return snapshot
                self._workflow_condition.wait()
            return None

    def _record_unexpected_workflow_error(
        self,
        *,
        frame: MonitorFrame,
        workflow: MonitorWorkflow,
        error: Exception,
        phase: str,
    ) -> None:
        message = (
            f"unexpected workflow {phase} error: "
            f"{workflow.name}: {type(error).__name__}: {error}"
        )
        frame.add_error(message)
        workflow_errors = self.state.data.setdefault("workflow_errors", [])
        if isinstance(workflow_errors, list):
            workflow_errors.append(
                {
                    "tick": frame.tick,
                    "workflow": workflow.name,
                    "phase": phase,
                    "error_type": type(error).__name__,
                    "message": str(error),
                }
            )
        append_monitor_log_event(
            event="workflow_error",
            tick=frame.tick,
            payload={
                "workflow": workflow.name,
                "phase": phase,
                "error_type": type(error).__name__,
                "message": str(error),
            },
        )

    def _configure_initial_alarms(self) -> None:
        self.clock.set_one_shot(MONITOR_STARTUP_ALARM, remaining_ticks=0)
        period_sec = _workflow_period_seconds(
            workflows=self.workflows,
            alarm_name=LIMITS_TRACKING_PERIODIC_ALARM,
        )
        self._arm_fixed_periodic_alarm(AUTO_PRIME_ZERO_LIMITS_PERIODIC_ALARM)
        self._arm_fixed_periodic_alarm(ACCOUNT_ROTATION_PERIODIC_ALARM)
        if period_sec is None:
            return
        self._limits_tracking_adaptive_alarm = _AdaptivePeriodicAlarmState(
            baseline_sec=period_sec,
            current_sec=period_sec,
        )
        self._arm_limits_tracking_periodic_alarm()

    def _write_monitor_setup_state(self) -> None:
        workflow_names = [workflow.name for workflow in self.workflows]
        self.state.data["monitor_setup"] = {
            "loaded_at": datetime.datetime.now(tz=datetime.UTC).isoformat(),
            "workflow_names": workflow_names,
            "config_fingerprint": self.config_fingerprint,
            "config_stale": False,
        }
        append_monitor_log_event(
            event="monitor_start",
            payload={
                "workflow_names": workflow_names,
                "config_fingerprint": self.config_fingerprint,
            },
        )

    def _check_config_fingerprint(self) -> None:
        if self.config_fingerprint is None or self.config_fingerprint_loader is None:
            return
        try:
            current_fingerprint = self.config_fingerprint_loader()
        except Exception as exc:
            self.state.data["monitor_config_warning"] = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
            return
        if current_fingerprint == self.config_fingerprint:
            return
        setup = self.state.data.get("monitor_setup")
        if isinstance(setup, dict):
            if not setup.get("config_stale"):
                append_monitor_log_event(
                    event="config_stale",
                    tick=self.state.tick,
                    payload={
                        "config_fingerprint": self.config_fingerprint,
                        "current_config_fingerprint": current_fingerprint,
                    },
                )
            setup["config_stale"] = True
            setup["current_config_fingerprint"] = current_fingerprint
            setup["warning"] = "monitor config changed; restart required to reload workflows"

    def _apply_adaptive_alarm_policy(
        self, snapshot: MonitorClockSnapshot
    ) -> MonitorClockSnapshot:
        alarm_state = self._limits_tracking_adaptive_alarm
        if alarm_state is None:
            return snapshot
        if snapshot.fired(MONITOR_ENTER_ALARM):
            alarm_state.current_sec = alarm_state.baseline_sec
            self._arm_limits_tracking_periodic_alarm()
            return self._snapshot_with_fired(snapshot.fired_alarm_names)
        if snapshot.fired(LIMITS_TRACKING_PERIODIC_ALARM):
            alarm_state.current_sec += 1.0
            self._arm_limits_tracking_periodic_alarm()
            return self._snapshot_with_fired(snapshot.fired_alarm_names)
        return snapshot

    def _arm_limits_tracking_periodic_alarm(self) -> None:
        alarm_state = self._limits_tracking_adaptive_alarm
        if alarm_state is None:
            return
        self.clock.set_periodic(
            LIMITS_TRACKING_PERIODIC_ALARM,
            period_ticks=_period_ticks_from_seconds(
                alarm_state.current_sec,
                interval_sec=self.interval_sec,
            ),
        )

    def _arm_fixed_periodic_alarm(self, alarm_name: str) -> None:
        period_sec = _workflow_period_seconds(
            workflows=self.workflows,
            alarm_name=alarm_name,
        )
        if period_sec is None:
            return
        self.clock.set_periodic(
            alarm_name,
            period_ticks=_period_ticks_from_seconds(
                period_sec,
                interval_sec=self.interval_sec,
            ),
        )

    def _snapshot_with_fired(
        self, fired_alarm_names: tuple[str, ...]
    ) -> MonitorClockSnapshot:
        current = self.clock.snapshot()
        return MonitorClockSnapshot(
            tick=current.tick,
            alarms=current.alarms,
            fired_alarm_names=fired_alarm_names,
        )


def _workflow_period_seconds(
    *,
    workflows: tuple[MonitorWorkflow, ...],
    alarm_name: str,
) -> float | None:
    for workflow in workflows:
        if getattr(workflow, "periodic_alarm_name", None) != alarm_name:
            continue
        refresh_interval_sec = getattr(workflow, "refresh_interval_sec", None)
        if isinstance(refresh_interval_sec, int | float):
            return float(refresh_interval_sec)
    return None


def _workflow_alarm_names(fired_alarm_names: tuple[str, ...]) -> tuple[str, ...]:
    display_only = {MONITOR_USAGE_VARIANT_TOGGLE_ALARM, MONITOR_MATERIALIZE_ALARM}
    return tuple(name for name in fired_alarm_names if name not in display_only)


def _period_ticks_from_seconds(period_sec: float, *, interval_sec: float) -> int:
    cadence_sec = interval_sec if interval_sec > 0 else 1.0
    return max(1, math.ceil(period_sec / cadence_sec))


def _workflow_clock_title(
    workflow_name: str,
    *,
    remaining_ticks: int,
    period_ticks: int | None,
) -> str:
    title = f"{workflow_name} | next in {remaining_ticks} ticks"
    if period_ticks is None:
        return title
    ticks_since_reset = max(0, period_ticks - remaining_ticks)
    return f"{title} | reset {ticks_since_reset} ticks ago"
