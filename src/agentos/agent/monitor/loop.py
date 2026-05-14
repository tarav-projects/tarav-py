from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

from agentos._core.errors import CliError
from agentos.agent.monitor.models import MonitorFrame, MonitorState


class MonitorWorkflow(Protocol):
    name: str

    def run(self, state: MonitorState, frame: MonitorFrame) -> None:
        ...


class MonitorLoop:
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
        self.frame = MonitorFrame()

    def run(
        self,
        *,
        on_tick: Callable[[MonitorFrame, MonitorState], None] | None = None,
    ) -> tuple[MonitorFrame, MonitorState]:
        ticks_run = 0
        while self.max_ticks is None or ticks_run < self.max_ticks:
            started_at = time.monotonic()
            self.state.tick += 1
            self.frame.tick = self.state.tick
            self.frame.status_lines = [f"tick: {self.state.tick}"]

            for workflow in self.workflows:
                try:
                    workflow.run(self.state, self.frame)
                except Exception as exc:
                    self._record_unexpected_workflow_error(workflow=workflow, error=exc)

            if on_tick is not None:
                on_tick(self.frame, self.state)

            ticks_run += 1
            if self.max_ticks is None or ticks_run < self.max_ticks:
                elapsed = time.monotonic() - started_at
                sleep_for = max(0.0, self.interval_sec - elapsed)
                if sleep_for:
                    time.sleep(sleep_for)
        return self.frame, self.state

    def _record_unexpected_workflow_error(self, *, workflow: MonitorWorkflow, error: Exception) -> None:
        message = f"unexpected workflow error: {workflow.name}: {type(error).__name__}: {error}"
        self.frame.add_error(message)
        workflow_errors = self.state.data.setdefault("workflow_errors", [])
        if isinstance(workflow_errors, list):
            workflow_errors.append(
                {
                    "tick": self.frame.tick,
                    "workflow": workflow.name,
                    "error_type": type(error).__name__,
                    "message": str(error),
                }
            )
