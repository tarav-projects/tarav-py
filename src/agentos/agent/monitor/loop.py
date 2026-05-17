from __future__ import annotations

import math
import time
from threading import Condition, Event, Thread
from collections.abc import Callable
from typing import Protocol

from agentos._core.errors import CliError
from agentos.agent.monitor.clock import (
    LIMITS_TRACKING_PERIODIC_ALARM,
    MONITOR_STARTUP_ALARM,
    MonitorClock,
    MonitorClockSnapshot,
)
from agentos.agent.monitor.models import (
    MonitorFrame,
    MonitorState,
)


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
    ) -> None:
        if max_ticks is not None and max_ticks < 1:
            raise CliError("--max-ticks must be greater than 0")
        if interval_sec < 0:
            raise CliError("--interval-sec must be greater than or equal to 0")
        self.workflows = workflows
        self.interval_sec = interval_sec
        self.max_ticks = max_ticks
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
        self._configure_initial_alarms()

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
                self._clock_snapshot = self.clock.step()
                self.state.tick = self._clock_snapshot.tick
                if self._clock_snapshot.fired_alarm_names:
                    self._queue_workflow_snapshot(self._clock_snapshot)
                if wait_for_first_frame and self.visible_frame.tick == 0:
                    self.working_frame_ready.wait()
                self._publish_working_frame_if_ready()
                self._prepare_visible_frame_for_render()

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
        status_lines = [f"tick: {self.state.tick}"]
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
            block["title"] = (
                f"{workflow_name} | next in {alarm.remaining_ticks} ticks"
            )

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

    def _configure_initial_alarms(self) -> None:
        self.clock.set_one_shot(MONITOR_STARTUP_ALARM, remaining_ticks=0)
        period_ticks = _workflow_period_ticks(
            workflows=self.workflows,
            interval_sec=self.interval_sec,
            alarm_name=LIMITS_TRACKING_PERIODIC_ALARM,
        )
        if period_ticks is not None:
            self.clock.set_periodic(
                LIMITS_TRACKING_PERIODIC_ALARM,
                period_ticks=period_ticks,
            )


def _workflow_period_ticks(
    *,
    workflows: tuple[MonitorWorkflow, ...],
    interval_sec: float,
    alarm_name: str,
) -> int | None:
    cadence_sec = interval_sec if interval_sec > 0 else 1.0
    for workflow in workflows:
        if getattr(workflow, "periodic_alarm_name", None) != alarm_name:
            continue
        refresh_interval_sec = getattr(workflow, "refresh_interval_sec", None)
        if isinstance(refresh_interval_sec, int | float):
            return max(1, math.ceil(float(refresh_interval_sec) / cadence_sec))
    return None
