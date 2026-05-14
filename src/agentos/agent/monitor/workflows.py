from __future__ import annotations

from agentos._core.errors import CliError
from agentos.agent.monitor.loop import MonitorWorkflow
from agentos.agent.monitor.models import MonitorFrame, MonitorState, MonitorWorkflowConfig


class LimitsTrackingWorkflow:
    name = "limits-tracking"

    def __init__(self, config: MonitorWorkflowConfig) -> None:
        self.config = config
        self._frame_block_index: int | None = None

    def run(self, state: MonitorState, frame: MonitorFrame) -> None:
        run_count = state.workflow_run_counts.get(self.name, 0) + 1
        state.workflow_run_counts[self.name] = run_count
        state.data[self.name] = {
            "status": "under construction",
            "last_tick": frame.tick,
            "run_count": run_count,
            "target_count": len(self.config.targets),
        }
        self._write_frame_block(
            frame,
            run_count=run_count,
        )

    def _write_frame_block(self, frame: MonitorFrame, *, run_count: int) -> None:
        lines = [
            "status: under construction",
            f"tick: {frame.tick}",
            f"targets: {len(self.config.targets)}",
        ]
        data = {
            "status": "under construction",
            "run_count": run_count,
            "targets": [target.summary() for target in self.config.targets],
        }
        if self._frame_block_index is None:
            self._frame_block_index = len(frame.blocks)
            frame.add_block(self.name, lines, data=data)
            return
        frame.replace_block(self._frame_block_index, title=self.name, lines=lines, data=data)


def build_monitor_workflows(configs: tuple[MonitorWorkflowConfig, ...]) -> tuple[MonitorWorkflow, ...]:
    workflows: list[MonitorWorkflow] = []
    for config in configs:
        if config.name == "limits-tracking":
            workflows.append(LimitsTrackingWorkflow(config))
            continue
        raise CliError(f"unknown monitor workflow {config.name!r}")
    return tuple(workflows)
