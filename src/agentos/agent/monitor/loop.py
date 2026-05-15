from __future__ import annotations

import time
from threading import Event, Thread
from collections.abc import Callable
from typing import Protocol

from agentos._core.errors import CliError
from agentos.agent.monitor.models import MonitorFrame, MonitorState


class MonitorWorkflow(Protocol):
    name: str

    def run(self, state: MonitorState, frame: MonitorFrame) -> None:
        ...


class MonitorLoop:
    # Frame ownership is transferred, not shared. The workflow thread owns
    # working_frame after working_frame_available is set and until it sets
    # working_frame_ready. The main thread owns visible_frame, and swaps only
    # after working_frame_ready signals that workflow ownership was released.
    # That Event handshake is why frame access does not need a lock.
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
        self.state = MonitorState()
        self.visible_frame = MonitorFrame()
        self.working_frame = MonitorFrame()
        self.working_frame_available = Event()
        self.working_frame_ready = Event()
        self.stop_requested = Event()
        self._workflow_thread: Thread | None = None
        self._workflow_started = False

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
                self.state.tick += 1
                self._start_workflow_cycle()
                if wait_for_first_frame and self.visible_frame.tick == 0:
                    self.working_frame_ready.wait()
                start_next_cycle = (
                    self.max_ticks is None or ticks_run + 1 < self.max_ticks
                )
                self._publish_working_frame_if_ready(
                    start_next_cycle=start_next_cycle
                )
                self._prepare_visible_frame_for_render()

                if on_tick is not None:
                    on_tick(self.visible_frame, self.state)

                ticks_run += 1
                if self.max_ticks is None or ticks_run < self.max_ticks:
                    elapsed = time.monotonic() - started_at
                    sleep_for = max(0.0, self.interval_sec - elapsed)
                    if sleep_for:
                        time.sleep(sleep_for)
            self._publish_working_frame_if_ready(start_next_cycle=False)
            return self.visible_frame, self.state
        finally:
            self._stop_workflow_thread()

    def _start_workflow_thread(self) -> None:
        if self._workflow_thread is not None and self._workflow_thread.is_alive():
            return
        self.stop_requested.clear()
        self.working_frame_ready.clear()
        self.working_frame_available.clear()
        self._workflow_started = False
        self._workflow_thread = Thread(
            target=self._run_workflow_loop,
            name="agentos-monitor-workflows",
            daemon=True,
        )
        self._workflow_thread.start()

    def _start_workflow_cycle(self) -> None:
        if self._workflow_started:
            return
        self._workflow_started = True
        self.working_frame_available.set()

    def _publish_working_frame_if_ready(self, *, start_next_cycle: bool) -> None:
        if not self.working_frame_ready.is_set():
            return
        self.visible_frame, self.working_frame = self.working_frame, self.visible_frame
        self.working_frame_ready.clear()
        self._workflow_started = False
        if start_next_cycle and not self.stop_requested.is_set():
            self.working_frame_available.set()
            self._workflow_started = True

    def _prepare_visible_frame_for_render(self) -> None:
        if self.visible_frame.tick == 0:
            self.visible_frame.prepare(tick=self.state.tick)
            self.visible_frame.status_lines = [
                f"tick: {self.state.tick}",
                "waiting for workflow frame",
            ]
            return
        self.visible_frame.tick = self.state.tick
        self.visible_frame.status_lines = [f"tick: {self.state.tick}"]

    def _stop_workflow_thread(self) -> None:
        self.stop_requested.set()
        self.working_frame_available.set()
        thread = self._workflow_thread
        if thread is not None:
            thread.join(timeout=1.0)

    def _run_workflow_loop(self) -> None:
        while not self.stop_requested.is_set():
            self.working_frame_available.wait()
            if self.stop_requested.is_set():
                return
            self.working_frame_available.clear()

            frame = self.working_frame
            frame.prepare(tick=self.state.tick)
            frame.status_lines = [f"tick: {self.state.tick}"]

            try:
                for workflow in self.workflows:
                    try:
                        workflow.run(self.state, frame)
                    except Exception as exc:
                        self._record_unexpected_workflow_error(
                            frame=frame, workflow=workflow, error=exc
                        )
            except Exception as exc:
                frame.add_error(
                    f"unexpected workflow loop error: {type(exc).__name__}: {exc}"
                )

            self.working_frame_ready.set()

    def _record_unexpected_workflow_error(
        self, *, frame: MonitorFrame, workflow: MonitorWorkflow, error: Exception
    ) -> None:
        message = f"unexpected workflow error: {workflow.name}: {type(error).__name__}: {error}"
        frame.add_error(message)
        workflow_errors = self.state.data.setdefault("workflow_errors", [])
        if isinstance(workflow_errors, list):
            workflow_errors.append(
                {
                    "tick": frame.tick,
                    "workflow": workflow.name,
                    "error_type": type(error).__name__,
                    "message": str(error),
                }
            )
